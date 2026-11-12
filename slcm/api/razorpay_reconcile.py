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
		"remarks": f"Razorpay order {intent.order_id} ({source})",
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
		webhook_status="Processed",
		remarks=f"Payment captured via Razorpay ({source}) — order {intent.order_id}",
	)
	return "recorded"


RECORDERS = {"demands": record_demands_payment, "invoice": record_invoice_payment}


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
