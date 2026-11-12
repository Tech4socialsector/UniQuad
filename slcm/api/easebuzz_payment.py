"""
Easebuzz checkout for Student / Parent Portal payments
======================================================
Fee Demands (single or Pay All), Fee Invoices, re-exam, improvement-exam and transcript fees
whose configured gateway is Easebuzz (see slcm.slcm.fee.payment_gateway) are paid here.

Flow
----
1. A portal "create order" endpoint calls ``start_checkout()``. It stores what is being paid
   (the *intent*: flow, student, demands / registration / invoice / request, amount, return page)
   on an Integration Request whose name is the Easebuzz ``txnid``, and returns the hosted
   checkout URL. The browser goes there (full-page redirect, no popup).
2. Easebuzz POSTs the result to ``complete`` (surl / furl) and, separately, to ``webhook``.
   Both verify the response hash, then ``_settle()`` records the payment exactly once.
3. ``complete`` redirects back to the portal page with ``?payment_ref=<txnid>``; the page
   calls ``get_payment_result`` to show the outcome.
4. ``reconcile_pending`` (scheduler) asks Easebuzz about checkouts that never came back.

Security
--------
* Amounts come from the server-side intent only; the callback amount must match it.
* Callbacks are trusted only after hash verification (Easebuzz Settings.verify_response_hash);
  the retrieve API is a server-to-server call authenticated with our Salt.
* The return POST arrives without the portal session (SameSite cookies), so settlement relies
  on the stored intent, never on the session. Records are written as the payer's user.
* Settlement locks the Integration Request row and is idempotent on the Easebuzz payment id.
"""

import json
import re
from contextlib import contextmanager
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import add_to_date, flt, get_url, now_datetime, today

from slcm.slcm.fee.payment_gateway import EASEBUZZ, ensure_ready

SERVICE = EASEBUZZ
RETURN_METHOD = "/api/method/slcm.api.easebuzz_payment.complete"

# Easebuzz transaction status → outcome
_SUCCESS = {"success"}
_CANCELLED = {"usercancelled", "dropped"}
_PENDING = {"pending", "initiated", ""}

# Portal pages a checkout may return to (open-redirect guard)
_RETURN_PATHS = (
	"/student-portal/fees",
	"/student-portal/re-exam",
	"/student-portal/results",
	"/student-portal/transcript-request",
	"/student-portal/support",
	"/parent-portal/fees",
)


# ── Checkout ───────────────────────────────────────────────────────────────


def _clean_text(value, limit=100, fallback="Fee Payment"):
	"""Easebuzz rejects most punctuation in productinfo / firstname."""
	text = re.sub(r"[^A-Za-z0-9 .,\-]", " ", str(value or ""))
	text = re.sub(r"\s+", " ", text).strip()[:limit]
	return text or fallback


def _clean_phone(*values):
	for value in values:
		digits = re.sub(r"\D", "", str(value or ""))
		if len(digits) >= 10:
			return digits[-10:]
	return ""


def payer_details(student, paid_by_role="Student"):
	"""(name, email, phone) to prefill checkout — the parent's own name/email when a parent pays."""
	sm = frappe.db.get_value(
		"Student Master",
		student,
		["first_name", "last_name", "email", "official_email_id", "phone", "alternate_phone"],
		as_dict=True,
	) or frappe._dict()
	phone = _clean_phone(sm.phone, sm.alternate_phone)
	if paid_by_role == "Parent":
		user = frappe.db.get_value("User", frappe.session.user, ["full_name", "email", "mobile_no"], as_dict=True) or {}
		return (
			user.get("full_name") or frappe.session.user,
			user.get("email") or frappe.session.user,
			_clean_phone(user.get("mobile_no")) or phone,
		)
	name = " ".join(filter(None, [sm.first_name, sm.last_name])) or student
	return name, sm.official_email_id or sm.email or frappe.session.user, phone


def precheck(student, paid_by_role="Student"):
	"""Everything that can stop an Easebuzz checkout before it starts — call it before marking
	anything "Payment Initiated", so a refusal leaves no in-flight status behind.
	Returns (payer_name, payer_email, payer_phone)."""
	ensure_ready(SERVICE)
	payer_name, payer_email, payer_phone = payer_details(student, paid_by_role)
	if not payer_phone:
		frappe.throw(
			_("A 10-digit mobile number is needed for online payment. Please update your phone number in your profile or contact the Student Office."),
			title=_("Mobile Number Required"),
		)
	return payer_name, payer_email, payer_phone


def start_checkout(flow, student, amount, intent, productinfo, return_path, paid_by_role="Student", reference=None):
	"""Create the Easebuzz checkout for *intent* and return the payload the portal JS expects.

	``intent`` holds the flow-specific references (demand_names, registration, invoice, …).
	``reference`` is an optional (doctype, name) shown on the Integration Request.
	"""
	amount = flt(amount, 2)
	if amount <= 0:
		frappe.throw(_("Nothing to pay."))
	if not return_path.split("?")[0] in _RETURN_PATHS:
		frappe.throw(_("Invalid return page."))

	payer_name, payer_email, payer_phone = precheck(student, paid_by_role)

	data = {
		"gateway": SERVICE,
		"flow": flow,
		"student": student,
		"amount": amount,
		"user": frappe.session.user,
		"paid_by_role": paid_by_role,
		"paid_by_name": payer_name,
		"return_path": return_path,
		**intent,
	}
	ref_doctype, ref_name = reference or (None, None)
	ir = frappe.get_doc({
		"doctype": "Integration Request",
		"integration_request_service": SERVICE,
		"status": "Queued",
		"data": json.dumps(data, default=str),
		"reference_doctype": ref_doctype,
		"reference_docname": ref_name,
		"request_description": f"Portal {flow} payment",
	}).insert(ignore_permissions=True)

	settings = frappe.get_single("Easebuzz Settings")
	callback = get_url(RETURN_METHOD)
	try:
		access_key = settings.initiate_payment(
			txnid=ir.name,
			amount=amount,
			productinfo=_clean_text(productinfo),
			firstname=_clean_text(payer_name, 60, "Student"),
			email=payer_email,
			phone=payer_phone,
			surl=callback,
			furl=callback,
			udf1=flow,
			udf2=_clean_text(student, 40, ""),
		)
	except Exception:
		ir.db_set("status", "Failed", update_modified=False)
		frappe.db.commit()
		raise

	frappe.db.commit()
	return {
		"gateway": SERVICE,
		"checkout_url": settings.get_checkout_url(access_key),
		"txnid": ir.name,
		"integration_request": ir.name,
		"amount": amount,
	}


# ── Callbacks ──────────────────────────────────────────────────────────────


def _verified(params):
	"""True when the POSTed response carries a valid Easebuzz hash."""
	try:
		return frappe.get_single("Easebuzz Settings").verify_response_hash(params)
	except Exception:
		return False


@frappe.whitelist(allow_guest=True, methods=["POST"])
def complete(**params):
	"""Easebuzz surl / furl: settle, then send the payer back to their portal page."""
	params.pop("cmd", None)
	txnid = str(params.get("txnid") or "")
	path = "/student-portal/fees"
	data = _intent(txnid)
	if data:
		path = data.get("return_path") or path
		if _verified(params):
			try:
				_settle(txnid, params, source="return")
			except Exception:
				frappe.db.rollback()
				frappe.log_error(frappe.get_traceback(), f"Easebuzz return settle failed — {txnid}")
		else:
			frappe.log_error(f"txnid: {txnid}", "Easebuzz return hash mismatch")

	sep = "&" if "?" in path else "?"
	_keep_browser_session()
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = get_url(path + sep + urlencode({"payment_ref": txnid}))


def _keep_browser_session():
	"""The cross-site POST from Easebuzz arrives without the portal's (SameSite=Lax) session
	cookie, so Frappe treats it as Guest and would answer with Set-Cookie sid=Guest — which the
	browser accepts on this top-level navigation, logging the payer out. Send no cookies."""
	manager = getattr(frappe.local, "cookie_manager", None)
	if manager:
		manager.cookies.clear()
		manager.to_delete.clear()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook(**params):
	"""Easebuzz transaction webhook (configure in the Easebuzz dashboard)."""
	params.pop("cmd", None)
	_keep_browser_session()
	txnid = str(params.get("txnid") or "")
	if not _intent(txnid):
		return "ignored"
	if not _verified(params):
		frappe.local.response["http_status_code"] = 401
		return "invalid hash"
	try:
		_settle(txnid, params, source="webhook")
	except Exception:
		# Answer 200 anyway: Easebuzz would otherwise retry a lasting error until it gives up. The checkout
		# is still Queued, so reconcile_pending settles it from Easebuzz's own record within 15 minutes.
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"Easebuzz webhook settle failed — {txnid}")
		return "logged"
	return "ok"


@frappe.whitelist()
def get_payment_result(payment_ref):
	"""Outcome of a checkout for the portal page it returned to (payer or System Manager only)."""
	data = _intent(payment_ref)
	if not data or (data.get("user") != frappe.session.user and "System Manager" not in frappe.get_roles()):
		frappe.throw(_("Payment not found."), frappe.PermissionError)

	status = frappe.db.get_value("Integration Request", payment_ref, "status")
	settled_now = False
	# Only the payer's own request asks Easebuzz (records are then written as the payer anyway);
	# an admin looking at someone else's checkout just sees its current state.
	if status == "Queued" and data.get("user") == frappe.session.user:
		new_status = _reconcile(payment_ref)
		if new_status and new_status != UNREACHABLE:
			settled_now = new_status == "Completed"
			status = new_status

	outcome = {
		"Completed": "success",
		"Cancelled": "cancelled",
		"Failed": "failed",
	}.get(status, "pending")
	refund = 0
	unrecorded = _unrecorded(payment_ref) if status == "Queued" else None
	if unrecorded:
		outcome = "received"  # money taken, fee record not updated yet: tell the payer not to pay again
	elif status == "Completed" and frappe.db.get_value("Integration Request", payment_ref, "error"):
		# captured but (part) not applied: the fees were paid meanwhile by someone else (or cancelled);
		# the money is recorded as unapplied for a refund (see _demands_success / flow notes)
		refund = _unapplied_amount(payment_ref, flt(data.get("amount")))
		if refund > 0.01:
			outcome = "duplicate"
	refund = refund if outcome == "duplicate" else 0
	return {
		"status": outcome,
		"payment_id": (unrecorded or {}).get("easepayid") or "",
		"refund_amount": refund,
		"formatted_refund": "₹{:,.0f}".format(refund),
		"settled_now": settled_now,
		"flow": data.get("flow"),
		"amount": flt(data.get("amount")),
		"formatted_amount": "₹{:,.0f}".format(flt(data.get("amount"))),
	}


# ── Settlement ─────────────────────────────────────────────────────────────


def _intent(txnid):
	if not txnid or not re.match(r"^[A-Za-z0-9_\-]+$", txnid):
		return None
	row = frappe.db.get_value(
		"Integration Request", txnid, ["integration_request_service", "data"], as_dict=True
	)
	if not row or row.integration_request_service != SERVICE:
		return None
	try:
		return frappe._dict(json.loads(row.data or "{}"))
	except Exception:
		return None


@contextmanager
def _as_user(user):
	"""Write records as the payer. frappe.set_user rewrites the live session object, so the
	caller's session is put back exactly as it was afterwards."""
	import copy

	previous = frappe.session.user
	if not user or user == previous or not frappe.db.exists("User", user):
		yield
		return
	saved_session = copy.deepcopy(frappe.local.session)
	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(previous)
		frappe.local.session = saved_session


def _settle(txnid, txn, source):
	"""Apply a verified Easebuzz transaction to its intent, exactly once.

	Returns the Integration Request status afterwards (Completed / Failed / Cancelled / Queued).
	"""
	# End the caller's read-only transaction before locking. Under REPEATABLE READ the reads callers made
	# first (_intent, settings) pin a snapshot: after waiting for a concurrent return / webhook to settle
	# this txnid, every plain read below would still see it unsettled and credit the payment twice.
	# Callers have written nothing yet, so this commit only starts a fresh transaction.
	frappe.db.commit()
	rows = frappe.db.sql(
		"SELECT status, data FROM `tabIntegration Request` WHERE name = %s FOR UPDATE", txnid, as_dict=True
	)
	ir = rows[0] if rows else None
	status = (txn.get("status") or "").strip().lower()
	if not ir or ir.status == "Completed":
		return ir and ir.status
	if ir.status in ("Failed", "Cancelled") and status not in _SUCCESS:
		# Already closed; only a late success (captured after a failure / expiry) reopens it.
		return ir.status

	data = frappe._dict(json.loads(ir.data or "{}"))
	flow = FLOWS.get(data.flow)
	if not flow:
		frappe.log_error(f"txnid: {txnid}\nflow: {data.flow}", "Easebuzz settle: unknown flow")
		return ir.status

	payment_id = str(txn.get("easepayid") or "").strip() or txnid
	summary = {
		"source": source,
		"status": status,
		"easepayid": payment_id,
		"mode": txn.get("mode") or "",
		"bank_ref_num": txn.get("bank_ref_num") or "",
		# payer instrument (UPI id / masked card number) and bank (net banking bank / card issuer)
		"payer": txn.get("upi_va") or txn.get("cardnum") or "",
		"bank_name": txn.get("bank_name") or txn.get("issuing_bank") or "",
		"amount": txn.get("amount") or "",
		"addedon": txn.get("addedon") or "",
		"error": (txn.get("error_Message") or txn.get("error") or "")[:200],
	}

	if status in _PENDING:
		return ir.status

	if status in _SUCCESS:
		if str(txn.get("txnid") or "") != txnid or abs(flt(txn.get("amount")) - flt(data.amount)) > 0.01:
			frappe.log_error(
				f"txnid: {txnid}\nexpected: {data.amount}\nreceived: {txn.get('amount')}",
				"Easebuzz settle: amount / txnid mismatch",
			)
			summary["error"] = "amount or txnid mismatch"
			frappe.db.set_value(
				"Integration Request", txnid, {"status": "Failed", "error": json.dumps(summary)}, update_modified=False,
			)
			# the charge was not paid: release it from "Payment Initiated" so it can be paid again
			with _as_user(data.user):
				flow["failure"](data, payment_id, summary, cancelled=False)
			# Easebuzz did capture this money: record it (unapplied) so it is refunded, not lost
			from slcm.slcm.fee.payment_ledger import record_unapplied_capture, _quietly

			_quietly(
				record_unapplied_capture, txnid, data, txnid, payment_id, summary,
				f"Amount / txnid mismatch: expected ₹{flt(data.amount):,.2f} for {txnid}, Easebuzz captured "
				f"₹{flt(txn.get('amount')):,.2f} (txnid {txn.get('txnid')}). Needs refund or manual allocation.",
			)
			frappe.db.commit()
			return "Failed"

		try:
			with _as_user(data.user):
				note = flow["success"](data, payment_id, txnid, summary)
		except Exception:
			_flag_unrecorded(txnid, summary)
			raise
		frappe.db.set_value(
			"Integration Request", txnid,
			{
				"status": "Completed",
				"output": json.dumps(summary),
				"error": note or None,
			},
			update_modified=False,
		)
		from slcm.slcm.fee.payment_ledger import record_easebuzz_capture_quietly

		# after the summary is stored: payment method / bank reference / captured amount
		record_easebuzz_capture_quietly(data, txnid, payment_id, summary, note)
		frappe.db.commit()
		return "Completed"

	new_status = "Cancelled" if status in _CANCELLED else "Failed"
	with _as_user(data.user):
		flow["failure"](data, payment_id, summary, cancelled=new_status == "Cancelled")
	if new_status == "Failed":
		from slcm.slcm.fee.payment_ledger import record_easebuzz_failure_quietly

		record_easebuzz_failure_quietly(data, txnid, payment_id, summary)
	frappe.db.set_value(
		"Integration Request", txnid, {"status": new_status, "error": json.dumps(summary)}, update_modified=False
	)
	frappe.db.commit()
	return new_status


def _unapplied_amount(txnid, amount):
	"""How much of a completed checkout no record took (to be refunded): its amount less what Fee Payments
	and re-exam / improvement payment logs booked on its Easebuzz payment id."""
	try:
		payment_id = json.loads(frappe.db.get_value("Integration Request", txnid, "output") or "{}").get("easepayid")
	except ValueError:
		payment_id = None
	if not payment_id:
		return flt(amount, 2)
	booked = flt(frappe.db.sql(
		"select sum(amount) from `tabFee Payment` where reference_number = %s and docstatus = 1", payment_id
	)[0][0])
	for log in ("Re Exam Payment Log", "Improvement Exam Payment Log"):
		booked += flt(frappe.db.sql(
			f"select sum(amount) from `tab{log}` where razorpay_payment_id = %s and payment_status = 'Paid'", payment_id
		)[0][0])
	return max(flt(amount - booked, 2), 0)


def _unrecorded(txnid):
	"""Summary of a captured payment whose booking failed (see _flag_unrecorded), or None."""
	error = frappe.db.get_value("Integration Request", txnid, "error") or ""
	try:
		row = json.loads(error) if error.startswith("{") else {}
	except ValueError:
		row = {}
	return row if row.get("booking_failed") else None


def _flag_unrecorded(txnid, summary):
	"""Easebuzz captured the money but recording it failed. The checkout stays Queued, so the return,
	webhook and reconciler keep retrying; the flag tells the payer their money arrived (instead of
	"being confirmed by the bank") and is cleared when a retry records the payment."""
	frappe.db.rollback()
	first = not _unrecorded(txnid)
	frappe.db.set_value(
		"Integration Request", txnid, "error", json.dumps({**summary, "booking_failed": 1}), update_modified=False
	)
	frappe.db.commit()
	if first:
		frappe.log_error(
			f"txnid: {txnid}\nEasebuzz payment {summary.get('easepayid')} of ₹{summary.get('amount')} was received "
			"but could not be recorded in SLCM. It is retried automatically every 15 minutes; the "
			"\"Easebuzz … settle failed\" error log for this txnid has the cause.",
			"Easebuzz payment received but not recorded",
		)


def _retrieve(txnid):
	"""The transaction as Easebuzz reports it now, or None."""
	response = frappe.get_single("Easebuzz Settings").retrieve_transaction(txnid)
	if not isinstance(response, dict):
		return None
	payload = response.get("msg") if "msg" in response else response.get("data")
	rows = payload if isinstance(payload, list) else [payload]
	rows = [r for r in rows if isinstance(r, dict) and str(r.get("txnid") or "") == txnid]

	# one txnid can carry several attempts (a failed try, then a successful retry): the capture wins
	def rank(row):
		status = str(row.get("status") or "").strip().lower()
		return 0 if status in _SUCCESS else 1 if status in _PENDING else 2

	return min(rows, key=rank) if rows else None


# _reconcile result when Easebuzz could not be asked (network / API error): never expire on it
UNREACHABLE = "unreachable"


def _reconcile(txnid):
	try:
		txn = _retrieve(txnid)
		if txn:
			return _settle(txnid, txn, source="retrieve")
	except Exception:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"Easebuzz reconcile failed — {txnid}")
		return UNREACHABLE
	return None


def reconcile_pending():
	"""Scheduler: settle checkouts whose return / webhook never arrived; expire abandoned ones."""
	now = now_datetime()
	queued = frappe.get_all(
		"Integration Request",
		filters={
			"integration_request_service": SERVICE,
			"status": "Queued",
			"creation": ["<", add_to_date(now, minutes=-10)],
		},
		fields=["name", "creation"],
		order_by="creation asc",
		limit=200,
	)
	expire_before = add_to_date(now, days=-2)
	for row in queued:
		status = _reconcile(row.name)
		if status in (None, "Queued") and row.creation < expire_before:
			try:
				_settle(row.name, {"status": "dropped", "txnid": row.name}, source="expired")
			except Exception:
				frappe.db.rollback()
				frappe.log_error(frappe.get_traceback(), f"Easebuzz expire failed — {row.name}")
		# End this row's transaction: releases the Integration Request lock _settle took, so a
		# return / webhook for it never waits on the rest of this run.
		frappe.db.commit()


# ── Flow handlers: success(data, payment_id, txnid, summary) → note | None ──


# Easebuzz mode → Student Fee Payment Log "Payment Method" option (a raw "NB" / "CC" fails the Select
# validation, and _append_payment_log then silently drops the audit row)
_LOG_METHODS = {"UPI": "UPI", "NB": "Netbanking", "CC": "Card", "DC": "Card", "CARD": "Card", "MW": "Wallet",
	"WALLET": "Wallet", "EMI": "EMI"}


def _log(student, event, **kwargs):
	from slcm.slcm.doctype.student_master.student_master import _append_payment_log

	if kwargs.get("payment_method"):
		kwargs["payment_method"] = _LOG_METHODS.get(str(kwargs["payment_method"]).strip().upper(), "Other")
	_append_payment_log(student, event, payment_mode="Online Payment", **kwargs)


def _demands_success(data, payment_id, txnid, summary):
	from slcm.api.student_payment import _mark_re_exams_paid

	student = data.student
	note = None
	re_paid = _mark_re_exams_paid(
		data.get("re_exam_registrations") or [], student, payment_id, txnid, payment_gateway=EASEBUZZ
	)
	budget = flt(data.amount) - sum(flt(r["amount"]) for r in re_paid)

	if frappe.db.exists("Fee Payment", {"reference_number": payment_id, "student": student, "docstatus": 1}):
		return note

	rows, allocated = [], 0.0
	for name in data.get("demand_names") or []:
		d = frappe.db.get_value(
			"Fee Demand", {"name": name, "student": student},
			["name", "fee_component", "description", "status", "outstanding_amount"], as_dict=True,
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
		# A demand was settled elsewhere between checkout and payment: keep the money traceable.
		note = f"₹{excess:,.2f} of Easebuzz payment {payment_id} could not be allocated (demands already settled)."
		frappe.log_error(f"txnid: {txnid}\nstudent: {student}\n{note}", "Easebuzz payment needs manual allocation")

	if not rows:
		return note

	role = data.get("paid_by_role") or "Student"
	fp = frappe.get_doc({
		"doctype": "Fee Payment",
		"student": student,
		"payment_date": today(),
		"payment_mode": "Online Payment",
		"payment_gateway": EASEBUZZ,
		"amount": flt(allocated, 2),
		"reference_number": payment_id,
		"remarks": f"{'Parent' if role == 'Parent' else 'Student'} portal payment — Easebuzz txn {txnid} — {len(rows)} demand(s)",
		"payment_demands": rows,
	})
	fp.insert(ignore_permissions=True)
	fp.submit()

	for row in rows:
		_log(
			student, "Captured",
			amount=row["amount_allocated"], fee_demand=row["fee_demand"],
			paid_by_role=role, paid_by_name=data.get("paid_by_name") or "",
			payment_method=summary.get("mode") or "",
			razorpay_payment_id=payment_id, razorpay_order_id=txnid,
			transaction_id=summary.get("bank_ref_num") or "",
			webhook_status="Not Applicable" if summary["source"] == "return" else "Processed",
			to_status="Paid",
			remarks=f"Payment captured via Easebuzz ({summary['source']}) — txn {txnid}",
		)
	return note


def _demands_failure(data, payment_id, summary, cancelled):
	from slcm.api.student_payment import _reset_re_exams

	student = data.student
	_reset_re_exams(data.get("re_exam_registrations") or [], student, "Pending" if cancelled else "Payment Failed")
	for name in data.get("demand_names") or []:
		status = frappe.db.get_value("Fee Demand", {"name": name, "student": student}, "status")
		if not status or status in ("Paid", "Waived"):
			continue
		_log(
			student, "Payment Cancelled" if cancelled else "Payment Failed",
			fee_demand=name,
			paid_by_role=data.get("paid_by_role") or "Student",
			paid_by_name=data.get("paid_by_name") or "",
			razorpay_payment_id=payment_id,
			from_status=status, to_status=status,
			error_message=summary.get("error") or "",
			remarks=f"Easebuzz {summary['status'] or 'abandoned'} ({summary['source']})",
		)


def _invoice_success(data, payment_id, txnid, summary):
	student, invoice = data.student, data.invoice
	note = None
	if not frappe.db.exists("Fee Payment", {"reference_number": payment_id, "fee_invoice": invoice, "docstatus": 1}):
		inv = frappe.get_doc("Fee Invoice", invoice)
		amount = min(flt(data.amount), max(flt(inv.outstanding_amount), 0))
		if flt(data.amount) - amount > 0.01:
			note = f"₹{flt(data.amount) - amount:,.2f} of Easebuzz payment {payment_id} exceeds invoice {invoice} outstanding."
			frappe.log_error(f"txnid: {txnid}\nstudent: {student}\n{note}", "Easebuzz payment needs manual allocation")
		if amount > 0:
			fp = frappe.get_doc({
				"doctype": "Fee Payment",
				"fee_invoice": invoice,
				"student": student,
				"amount": amount,
				"payment_date": today(),
				"payment_mode": "Online Payment",
				"payment_gateway": EASEBUZZ,
				"reference_number": payment_id,
				"remarks": f"{'Paid by parent via Parent Portal' if data.get('paid_by_role') == 'Parent' else 'Student portal payment'} — Easebuzz txn {txnid}",
			})
			fp.insert(ignore_permissions=True)
			fp.submit()

	frappe.db.set_value("Fee Invoice", invoice, "payment_status", "Captured", update_modified=False)
	after = frappe.db.get_value("Fee Invoice", invoice, ["paid_amount", "status"], as_dict=True) or {}
	_log(
		student, "Captured",
		amount=flt(after.get("paid_amount")), invoice=invoice,
		paid_by_role=data.get("paid_by_role") or "Student", paid_by_name=data.get("paid_by_name") or "",
		payment_method=summary.get("mode") or "",
		razorpay_payment_id=payment_id, razorpay_order_id=txnid,
		transaction_id=summary.get("bank_ref_num") or "",
		from_status="Payment Initiated", to_status=after.get("status") or "",
		remarks=f"Payment captured via Easebuzz ({summary['source']}) — txn {txnid}",
	)
	return note


def _invoice_failure(data, payment_id, summary, cancelled):
	from slcm.api.student_payment import _revert_sm_if_in_flight

	_revert_sm_if_in_flight(data.invoice, data.student)
	# a parent's checkout never sets the Student Master in flight: release the invoice itself too
	if frappe.db.get_value("Fee Invoice", data.invoice, "payment_status") == "Payment Initiated":
		frappe.db.set_value(
			"Fee Invoice", data.invoice, "payment_status", "Pending" if cancelled else "Payment Failed",
			update_modified=False,
		)


def _exam_success(doctype, log_doctype, link_field, fee_field):
	def handler(data, payment_id, txnid, summary):
		reg = frappe.db.get_value(
			doctype, {"name": data.registration, "student": data.student},
			["name", "payment_status", fee_field, "exam_plan", "course"], as_dict=True,
		)
		if not reg:
			return f"{doctype} {data.registration} no longer exists."
		note = None
		if reg.payment_status in ("Paid", "Captured"):
			ref = frappe.db.get_value(doctype, reg.name, "payment_reference")
			if ref and ref != payment_id:
				# Paid twice (two tabs, or Pay All + the exam page): keep both, flag for refund
				note = f"{reg.name} was already paid ({ref}); Easebuzz payment {payment_id} is a duplicate."
				frappe.log_error(f"txnid: {txnid}\n{note}", "Easebuzz duplicate payment needs refund")
		if not frappe.db.exists(log_doctype, {"razorpay_payment_id": payment_id}):
			frappe.get_doc({
				"doctype": log_doctype,
				link_field: reg.name,
				"razorpay_payment_id": payment_id,
				"razorpay_order_id": txnid,
				"payment_gateway": EASEBUZZ,
				"payment_status": "Paid",
				"amount": flt(data.amount),
				"settlement_amount": flt(data.amount),
				"payment_method": summary.get("mode") or "",
				"transaction_id": summary.get("bank_ref_num") or "",
				"transaction_date": now_datetime(),
				"gateway_response": json.dumps(summary, indent=2),
			}).insert(ignore_permissions=True)
		if reg.payment_status not in ("Paid", "Captured"):
			frappe.db.set_value(
				doctype, reg.name, {"payment_status": "Paid", "payment_reference": payment_id}, update_modified=True
			)
		return note

	return handler


def _exam_failure(doctype):
	def handler(data, payment_id, summary, cancelled):
		current = frappe.db.get_value(doctype, {"name": data.registration, "student": data.student}, "payment_status")
		if current == "Payment Initiated":
			frappe.db.set_value(
				doctype, data.registration, "payment_status",
				"Payment Cancelled" if cancelled else "Payment Failed", update_modified=False,
			)

	return handler


def _transcript_success(data, payment_id, txnid, summary):
	from slcm.api.transcript_request import mark_request_paid

	current = frappe.db.get_value(
		"Transcript Request", data.request_name, ["payment_status", "payment_reference", "status"], as_dict=True
	)
	if current and current.payment_status == "Paid" and current.payment_reference != payment_id:
		note = f"{data.request_name} was already paid ({current.payment_reference}); Easebuzz payment {payment_id} is a duplicate."
		frappe.log_error(f"txnid: {txnid}\n{note}", "Easebuzz duplicate payment needs refund")
		return note
	if current and current.status == "Cancelled":
		# Money arrived after the student cancelled the request: record it, don't revive the request
		note = f"{data.request_name} is Cancelled; Easebuzz payment {payment_id} needs a refund."
		frappe.log_error(f"txnid: {txnid}\n{note}", "Easebuzz payment for cancelled request")
		return note
	mark_request_paid(data.request_name, data.student, payment_id, txnid, gateway=EASEBUZZ)


def _transcript_failure(data, payment_id, summary, cancelled):
	from slcm.api.transcript_request import _set_payment_fields

	status = frappe.db.get_value("Transcript Request", data.request_name, ["payment_status", "status"], as_dict=True)
	# Never touch a paid request, or one the student cancelled / staff moved on meanwhile
	if not status or status.payment_status == "Paid" or status.status not in ("Draft", "Payment Pending"):
		return
	_set_payment_fields(
		data.request_name, "cancelled" if cancelled else "failed",
		gateway_response={"gateway": EASEBUZZ, **summary},
		extra={
			"status": "Payment Pending",
			"payment_failure_reason": "" if cancelled else (summary.get("error") or "Payment failed at gateway"),
		},
	)


FLOWS = {
	"demands": {"success": _demands_success, "failure": _demands_failure},
	"invoice": {"success": _invoice_success, "failure": _invoice_failure},
	"re_exam": {
		"success": _exam_success("Re Exam Registration", "Re Exam Payment Log", "re_exam_registration", "re_exam_fee"),
		"failure": _exam_failure("Re Exam Registration"),
	},
	"improvement_exam": {
		"success": _exam_success(
			"Improvement Exam Registration", "Improvement Exam Payment Log",
			"improvement_exam_registration", "improvement_fee",
		),
		"failure": _exam_failure("Improvement Exam Registration"),
	},
	"transcript": {"success": _transcript_success, "failure": _transcript_failure},
}
