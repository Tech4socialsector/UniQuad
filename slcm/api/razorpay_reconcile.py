"""
Server-side recovery for student / parent Razorpay fee payments.

The portal records a Fee Payment only when the browser comes back and calls a
``confirm_*`` endpoint. If the tab is closed after the money is captured (a UPI
collect approved later, a crash, a lost connection) the dues stayed unpaid.

1. ``attach_intent`` stores what an order pays for (flow, student, demands /
   re-exams / invoice, amount, order id) on the order's Integration Request,
   right after the order is created.
2. ``reconcile_pending`` (scheduler, every 15 min) asks Razorpay about orders
   that are still open, and records any captured payment exactly the way the
   confirm endpoints do. Orders with no capture after 3 days are closed.

Recording is idempotent on the Razorpay payment id (Fee Payment.reference_number)
and serialised on the Integration Request row lock, so a late browser confirm
and the reconciler can never both create a Fee Payment.
"""

import json

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, flt, now_datetime, today

INTENT_KEY = "slcm_intent"
GRACE_MINUTES = 10  # give the browser confirm a head start
GIVE_UP_DAYS = 3  # Razorpay orders accept retries for a while; stop polling after this


# ── 1. Intent ──────────────────────────────────────────────────────────────


def attach_intent(order, flow, student, amount, paid_by_role="Student", **refs):
	"""Record what the Razorpay ``order`` (create_order() response) pays for.

	flow: "demands" (refs: demand_names, re_exam_registrations) or "invoice" (refs: invoice_name).
	Never raises: a failure here must not block the checkout.
	"""
	try:
		ir_name = (order or {}).get("integration_request")
		if not ir_name:
			return
		data = json.loads(frappe.db.get_value("Integration Request", ir_name, "data") or "{}")
		data[INTENT_KEY] = {
			"flow": flow,
			"order_id": order.get("id"),
			"student": student,
			"amount": flt(amount, 2),
			"user": frappe.session.user,
			"paid_by_role": paid_by_role,
			**refs,
		}
		frappe.db.set_value(
			"Integration Request", ir_name, "data", json.dumps(data, default=str), update_modified=False
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Razorpay attach_intent (non-fatal)")


def get_intent(ir_name):
	try:
		data = json.loads(frappe.db.get_value("Integration Request", ir_name, "data") or "{}")
	except Exception:
		return None
	intent = data.get(INTENT_KEY)
	return frappe._dict(intent) if intent else None


def lock_intent(ir_name):
	"""Serialise browser confirm and reconciler on this order. Returns the intent (or None)."""
	if not ir_name:
		return None
	# Start a fresh transaction first: under REPEATABLE READ, reads made earlier would pin a
	# snapshot in which a payment the other path just recorded is still invisible.
	frappe.db.commit()
	frappe.db.sql("SELECT name FROM `tabIntegration Request` WHERE name = %s FOR UPDATE", ir_name)
	return get_intent(ir_name)


def _payment(payment_id):
	"""The payment as Razorpay reports it (raises on network / API errors)."""
	settings = frappe.get_single("Razorpay Settings")
	secret = settings.get_password(fieldname="api_secret", raise_exception=False)
	resp = requests.get(
		f"https://api.razorpay.com/v1/payments/{payment_id}",
		auth=(settings.api_key, secret),
		timeout=15,
	)
	resp.raise_for_status()
	return resp.json()


def verify_order(integration_request, order_id, payment_id, student, flow, demand_names=None,
                 invoice_name=None, registration=None, re_exam_registrations=None):
	"""Browser confirm, after the signature check: bind the payment to what its order was for.

	A valid signature only proves Razorpay took *some* payment on ``order_id``. Without this a
	student could pay a small order and then confirm it against larger dues. Returns the intent;
	``intent.amount`` is what the order charged, the most that may be recorded.
	Orders created before intents existed are checked against Razorpay instead.
	"""
	intent = get_intent(integration_request)
	if intent:
		problems = []
		if intent.order_id != order_id:
			problems.append("order id")
		if intent.student != student:
			problems.append("student")
		if intent.flow != flow:
			problems.append("flow")
		if demand_names is not None and not set(demand_names) <= set(intent.get("demand_names") or []):
			problems.append("fee demands")
		if re_exam_registrations and not set(re_exam_registrations) <= set(intent.get("re_exam_registrations") or []):
			problems.append("re-exam registrations")
		if invoice_name is not None and intent.get("invoice_name") != invoice_name:
			problems.append("invoice")
		if registration is not None and intent.get("registration") != registration:
			problems.append("registration")
		if problems:
			frappe.log_error(
				f"integration request: {integration_request}\norder: {order_id}\npayment: {payment_id}\n"
				f"student: {student}\nmismatch: {', '.join(problems)}\nuser: {frappe.session.user}",
				"Razorpay confirm: order does not match",
			)
			frappe.throw(_("This payment does not belong to the selected dues. Please contact the Bursar's Office."),
				frappe.PermissionError)
		return intent

	# Legacy order (no intent stored): Razorpay must confirm the payment is on this order.
	try:
		payment = _payment(payment_id)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Razorpay confirm: could not fetch payment")
		frappe.throw(_("Could not verify the payment with Razorpay. Please try again in a few minutes."))
	if payment.get("order_id") != order_id or payment.get("status") not in ("captured", "authorized"):
		frappe.throw(_("This payment does not belong to the selected dues. Please contact the Bursar's Office."),
			frappe.PermissionError)
	return frappe._dict({
		"flow": flow, "order_id": order_id, "student": student, "legacy": True,
		"amount": flt(payment.get("amount")) / 100,
		"demand_names": demand_names or [], "invoice_name": invoice_name, "registration": registration,
		"re_exam_registrations": re_exam_registrations or [],
	})


def cap_fee_payment(fp, cap):
	"""Never record more on ``fp`` than the order charged: allocations are filled in order up to
	``cap`` and rows left at zero dropped. Returns False when nothing is left to record."""
	cap = flt(cap, 2)
	asked = flt(fp.amount, 2)
	if fp.get("payment_demands"):
		remaining, rows = cap, []
		for row in fp.payment_demands:
			alloc = min(flt(row.amount_allocated, 2), flt(remaining, 2))
			if alloc <= 0:
				continue
			row.amount_allocated = alloc
			remaining -= alloc
			rows.append(row)
		fp.set("payment_demands", rows)
		fp.amount = flt(sum(flt(r.amount_allocated) for r in rows), 2)
	else:
		fp.amount = min(asked, cap)
	if asked - flt(fp.amount, 2) > 0.01:
		frappe.log_error(
			f"student: {fp.student}\npayment: {fp.reference_number}\n"
			f"dues ₹{asked:,.2f}, order charged ₹{cap:,.2f}: recorded ₹{flt(fp.amount):,.2f}",
			"Razorpay confirm: dues exceed amount paid",
		)
	return flt(fp.amount) > 0


# ── 2. Recording a captured payment ───────────────────────────────────────


def record_demands_payment(intent, payment_id, captured_amount, source):
	"""Create the Fee Payment for a captured demands order. Idempotent on payment_id.

	The captured amount is spread over the intent's demands (re-exam fees first); anything
	that cannot be allocated (dues settled elsewhere meanwhile) is logged for the Bursar.
	"""
	from slcm.api.student_payment import _mark_re_exams_paid
	from slcm.slcm.doctype.student_master.student_master import _append_payment_log

	student = intent.student
	order_id = intent.order_id
	re_paid = _mark_re_exams_paid(intent.get("re_exam_registrations") or [], student, payment_id, order_id)
	budget = flt(captured_amount, 2) - sum(flt(r["amount"]) for r in re_paid)

	if frappe.db.exists("Fee Payment", {"reference_number": payment_id, "student": student, "docstatus": 1}):
		return "already_recorded"

	rows, allocated = [], 0.0
	for name in intent.get("demand_names") or []:
		d = frappe.db.get_value(
			"Fee Demand",
			{"name": name, "student": student},
			["name", "fee_component", "description", "status", "outstanding_amount"],
			as_dict=True,
		)
		if not d or d.status in ("Paid", "Waived", "Cancelled") or flt(d.outstanding_amount) <= 0:
			continue
		alloc = min(flt(d.outstanding_amount), flt(budget - allocated, 2))
		if alloc <= 0:
			break
		rows.append({
			"fee_demand": name,
			"demand_description": d.fee_component or d.description or "",
			"outstanding_amount": flt(d.outstanding_amount),
			"amount_allocated": alloc,
		})
		allocated += alloc

	excess = flt(budget - allocated, 2)
	if excess > 0.01:
		frappe.log_error(
			f"order: {order_id}\npayment: {payment_id}\nstudent: {student}\n"
			f"₹{excess:,.2f} captured but could not be allocated (demands already settled). "
			"Needs refund or manual allocation.",
			"Razorpay payment needs manual allocation",
		)

	if not rows:
		return "nothing_to_allocate"

	role = intent.get("paid_by_role") or "Student"
	fp = frappe.get_doc({
		"doctype": "Fee Payment",
		"student": student,
		"payment_date": today(),
		"payment_mode": "Online Payment",
		"payment_gateway": "Razorpay",
		"amount": flt(allocated, 2),
		"reference_number": payment_id,
		"remarks": f"{role} portal payment — Razorpay order {order_id} — {len(rows)} demand(s) ({source})",
		"payment_demands": rows,
	})
	fp.insert(ignore_permissions=True)
	fp.submit()

	for row in rows:
		_append_payment_log(
			student,
			"Captured",
			amount=row["amount_allocated"],
			fee_demand=row["fee_demand"],
			payment_mode="Online Payment",
			paid_by_role=role,
			razorpay_payment_id=payment_id,
			razorpay_order_id=order_id,
			webhook_status="Not Applicable" if source == "browser" else "Processed",
			to_status="Paid",
			remarks=f"Payment captured via Razorpay ({source}) — order {order_id}",
		)
	return "recorded"


def record_invoice_payment(intent, payment_id, captured_amount, source):
	"""Create the Fee Payment for a captured Fee Invoice order. Idempotent on payment_id."""
	from slcm.slcm.doctype.student_master.student_master import _append_payment_log

	invoice = intent.get("invoice_name")
	if not invoice or not frappe.db.exists("Fee Invoice", invoice):
		return "no_invoice"
	if frappe.db.exists("Fee Payment", {"reference_number": payment_id, "docstatus": 1}):
		return "already_recorded"

	outstanding = flt(frappe.db.get_value("Fee Invoice", invoice, "outstanding_amount"))
	amount = min(flt(captured_amount, 2), outstanding)
	if flt(captured_amount, 2) - amount > 0.01:
		frappe.log_error(
			f"order: {intent.order_id}\npayment: {payment_id}\ninvoice: {invoice}\n"
			f"captured ₹{flt(captured_amount):,.2f}, outstanding ₹{outstanding:,.2f}. Needs refund or manual allocation.",
			"Razorpay payment needs manual allocation",
		)
	if amount <= 0:
		return "nothing_to_allocate"

	fp = frappe.get_doc({
		"doctype": "Fee Payment",
		"fee_invoice": invoice,
		"student": intent.student,
		"amount": amount,
		"payment_date": today(),
		"payment_mode": "Online Payment",
		"reference_number": payment_id,
		"payment_gateway": "Razorpay",
		"remarks": f"{intent.get('paid_by_role') or 'Student'} portal payment — Razorpay order {intent.order_id} ({source})",
	})
	fp.insert(ignore_permissions=True)
	fp.submit()
	frappe.db.set_value("Fee Invoice", invoice, "payment_status", "Captured", update_modified=False)

	_append_payment_log(
		intent.student,
		"Captured",
		amount=amount,
		invoice=invoice,
		payment_mode="Online Payment",
		paid_by_role=intent.get("paid_by_role") or "Student",
		razorpay_payment_id=payment_id,
		razorpay_order_id=intent.order_id,
		webhook_status="Not Applicable" if source == "browser" else "Processed",
		to_status=frappe.db.get_value("Fee Invoice", invoice, "status"),
		remarks=f"Payment captured via Razorpay ({source}) — order {intent.order_id}",
	)
	return "recorded"


def _exam_recorder(doctype, log_doctype, link_field, fee_field):
	"""Recorder for a captured re-exam / improvement exam order: the payment log and the registration's Paid
	mark, exactly what the browser confirm writes. Idempotent on the payment id."""

	def record(intent, payment_id, captured_amount, source):
		reg = frappe.db.get_value(
			doctype, {"name": intent.get("registration"), "student": intent.student},
			["name", "status", "payment_status", fee_field], as_dict=True,
		)
		if not reg:
			return "no_registration"
		if frappe.db.exists(log_doctype, {"razorpay_payment_id": payment_id}):
			return "already_recorded"
		if reg.payment_status in ("Paid", "Captured") or reg.status == "Cancelled":
			# paid by another payment, or cancelled meanwhile: record_unbooked_captures flags this one for a refund
			return "nothing_to_allocate"
		fee = flt(reg.get(fee_field))
		if flt(captured_amount, 2) + 0.01 < fee:
			frappe.log_error(
				f"order: {intent.order_id}\npayment: {payment_id}\n{doctype}: {reg.name}\n"
				f"captured ₹{flt(captured_amount):,.2f} does not cover the fee ₹{fee:,.2f}. Needs manual review.",
				"Razorpay exam payment short",
			)
			return "short"
		frappe.get_doc({
			"doctype": log_doctype,
			link_field: reg.name,
			"razorpay_payment_id": payment_id,
			"razorpay_order_id": intent.order_id,
			"payment_gateway": "Razorpay",
			"payment_status": "Paid",
			"amount": fee,
			"settlement_amount": fee,
			"transaction_date": now_datetime(),
			"gateway_response": json.dumps({
				"razorpay_payment_id": payment_id, "razorpay_order_id": intent.order_id, "source": source,
			}, indent=2),
		}).insert(ignore_permissions=True)
		frappe.db.set_value(doctype, reg.name, {"payment_status": "Paid", "payment_reference": payment_id})
		return "recorded"

	return record


def record_transcript_payment(intent, payment_id, captured_amount, source):
	"""Recorder for a captured transcript order: marks the request paid the way the browser confirm does
	(mark_request_paid also records a second payment of an already-paid request for a refund)."""
	from slcm.api.transcript_request import mark_request_paid

	name = intent.get("request_name")
	req = frappe.db.get_value(
		"Transcript Request", name, ["student", "status", "payment_reference", "fee_amount"], as_dict=True
	) if name else None
	if not req or req.student != intent.student:
		return "no_request"
	if req.payment_reference == payment_id:
		return "already_recorded"
	if req.status == "Cancelled":
		return "nothing_to_allocate"  # record_unbooked_captures flags it for a refund
	if flt(captured_amount, 2) + 0.01 < flt(req.fee_amount):
		frappe.log_error(
			f"order: {intent.order_id}\npayment: {payment_id}\nrequest: {name}\n"
			f"captured ₹{flt(captured_amount):,.2f} does not cover the fee ₹{flt(req.fee_amount):,.2f}.",
			"Razorpay transcript payment short",
		)
		return "short"
	mark_request_paid(name, intent.student, payment_id, intent.order_id)
	return "recorded"


RECORDERS = {
	"demands": record_demands_payment,
	"invoice": record_invoice_payment,
	"re_exam": _exam_recorder("Re Exam Registration", "Re Exam Payment Log", "re_exam_registration", "re_exam_fee"),
	"improvement": _exam_recorder(
		"Improvement Exam Registration", "Improvement Exam Payment Log", "improvement_exam_registration", "improvement_fee"
	),
	"transcript": record_transcript_payment,
}


# ── 3. Scheduler ──────────────────────────────────────────────────────────


def _order_payments(order_id):
	"""Payments Razorpay holds for this order. Raises on network / API errors."""
	settings = frappe.get_single("Razorpay Settings")
	secret = settings.get_password(fieldname="api_secret", raise_exception=False)
	if not settings.api_key or not secret:
		raise frappe.ValidationError("Razorpay Settings are incomplete")
	resp = requests.get(
		f"https://api.razorpay.com/v1/orders/{order_id}/payments",
		auth=(settings.api_key, secret),
		timeout=15,
	)
	resp.raise_for_status()
	return resp.json().get("items") or []


def _close(ir_name, status, note):
	frappe.db.set_value(
		"Integration Request", ir_name,
		{"status": status, "output": json.dumps({"slcm_reconcile": note})},
		update_modified=False,
	)


def reconcile_one(ir_name):
	"""Check one order with Razorpay and record a capture. Returns a short outcome string."""
	intent = get_intent(ir_name)
	if not intent or not intent.get("order_id") or intent.get("flow") not in RECORDERS:
		return "skipped"

	payments = _order_payments(intent.order_id)  # network call before taking the row lock
	captured = next((p for p in payments if p.get("status") == "captured"), None)

	intent = lock_intent(ir_name)
	if not captured:
		return "no_capture"

	outcome = RECORDERS[intent.flow](intent, captured["id"], flt(captured.get("amount")) / 100, "reconciler")
	_close(ir_name, "Completed", f"{outcome}: {captured['id']}")
	frappe.db.commit()
	return outcome


def _candidates():
	"""Open Razorpay orders that carry an SLCM intent, between GRACE_MINUTES and GIVE_UP_DAYS old."""
	now = now_datetime()
	return frappe.db.sql(
		"""
		SELECT name, creation FROM `tabIntegration Request`
		WHERE integration_request_service = 'Razorpay'
		  AND status != 'Completed'
		  AND data LIKE %(key)s
		  AND (output IS NULL OR output NOT LIKE %(closed)s)
		  AND creation BETWEEN %(oldest)s AND %(newest)s
		ORDER BY creation ASC
		LIMIT 200
		""",
		{
			"key": f'%"{INTENT_KEY}"%',
			"closed": "%slcm_reconcile%",
			"oldest": add_to_date(now, days=-GIVE_UP_DAYS - 1),
			"newest": add_to_date(now, minutes=-GRACE_MINUTES),
		},
		as_dict=True,
	)


def reconcile_pending():
	"""Scheduler: record Razorpay fee payments whose browser confirm never arrived."""
	give_up_before = add_to_date(now_datetime(), days=-GIVE_UP_DAYS)
	for row in _candidates():
		try:
			outcome = reconcile_one(row.name)
			if outcome == "no_capture" and row.creation < give_up_before:
				_close(row.name, "Cancelled", "expired: no capture")
		except requests.RequestException:
			# Razorpay unreachable (offline / DNS): try the whole batch again next run, no log spam
			frappe.db.rollback()
			break
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"Razorpay reconcile failed — {row.name}")
		# end this row's transaction so a browser confirm never waits on the rest of the run
		frappe.db.commit()


# ── 4. Captures nothing booked ─────────────────────────────────────────────

UNBOOKED_DAYS = 2
UNBOOKED_AFTER_MINUTES = 30  # leave the browser confirm and reconcile_pending time to book it first


def _intent_reference(intent):
	"""(doctype, name) of the charge an intent was for, for the unapplied SLCM Payment Request."""
	if intent.get("request_name"):
		return "Transcript Request", intent.request_name
	if intent.get("invoice_name"):
		return "Fee Invoice", intent.invoice_name
	if intent.get("registration"):
		return ("Improvement Exam Registration" if intent.flow == "improvement" else "Re Exam Registration"), intent.registration
	if intent.get("demand_names"):
		return "Fee Demand", intent.demand_names[0]
	if intent.get("re_exam_registrations"):
		return "Re Exam Registration", intent.re_exam_registrations[0]
	return None, None


def record_unbooked_captures(days=UNBOOKED_DAYS):
	"""Hourly: a Razorpay portal payment that was captured but never booked is recorded as an unapplied
	SLCM Payment Request (flagged for refund) instead of staying invisible.

	This is the second payment for dues that were settled first: a student and a parent paying together
	in windows opened before slcm.slcm.fee.checkout_guard could stop it, or two tabs. Its browser confirm
	answers "already paid" without booking anything and closes the order, so reconcile_pending never
	looks at it again. Returns how many were recorded."""
	from slcm.slcm.fee import payment_ledger as ledger

	rows = frappe.get_all(
		"Integration Request",
		filters={
			"integration_request_service": "Razorpay",
			"creation": (">", add_to_date(now_datetime(), days=-days)),
			"data": ("like", f"%{INTENT_KEY}%"),
		},
		fields=["name"],
		order_by="creation asc",
		limit=500,
		ignore_permissions=True,
	)
	settled_before = now_datetime().timestamp() - UNBOOKED_AFTER_MINUTES * 60
	recorded = 0
	for row in rows:
		intent = get_intent(row.name)
		if not intent or not intent.get("order_id") or intent.get("legacy"):
			continue
		try:
			payments = _order_payments(intent.order_id)
		except requests.RequestException:
			break  # Razorpay unreachable: try again next hour
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Razorpay unbooked-capture check failed — {row.name}")
			continue
		for p in payments:
			pid = p.get("id")
			if p.get("status") != "captured" or not pid or flt(p.get("created_at")) > settled_before:
				continue
			if ledger._existing(pid):
				continue
			ledger.sync_quietly(pid)  # booked by a record the ledger has not caught up with yet
			if ledger._existing(pid):
				continue
			ref_doctype, ref_name = _intent_reference(intent)
			amount = flt(p.get("amount")) / 100
			note = (
				f"Razorpay payment {pid} (₹{amount:,.2f}, order {intent.order_id}) was captured but no SLCM record "
				"took it (dues already paid by another payment, the charge cancelled, or the payment short of the fee). "
				"Needs refund or manual allocation."
			)
			if ledger.record_unapplied_quietly(
				"Razorpay", pid, intent.order_id, ref_doctype, ref_name, amount, intent.student, note
			):
				frappe.log_error(f"student: {intent.student}\n{note}", "Razorpay duplicate payment needs refund")
				recorded += 1
		frappe.db.commit()
	return recorded
