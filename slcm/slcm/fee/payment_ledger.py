"""SLCM Payment Request for every online student payment (Razorpay or Easebuzz).

Admissions and PACE already create their SLCM Payment Request before checkout. The student and
parent portal flows record money directly on Fee Payment, Re / Improvement Exam Payment Log
and Transcript Request instead. This module adds one submitted SLCM Payment Request per gateway
payment so that every online payment is listed in one place, and so that the Razorpay settlement
sync and the ERPNext settlement posting cover student payments too.

* Key: the gateway payment id (Razorpay ``pay_…`` / Easebuzz ``easepayid``) in ``transaction_id``.
* Reference: the Fee Payment the money was booked on, else the exam log or Transcript Request.
  A "Pay All" payment that also covered re-exams is one Payment Request for the full amount.
* Rebuilt from the records every time (order-independent and idempotent). When no record holds the
  money any more (Fee Payment cancelled, exam fee refunded) the request stays Paid - the gateway did
  capture and settle it - and points at the charge with a note. Never raises into the payment flow.
* Failed attempts get a Failed request with the gateway's reason in ``failure_message``, referencing
  the charge (Fee Demand / Fee Invoice / exam registration / Transcript Request). Razorpay failures
  come from the portal's Student Fee Payment Log and the transcript failure endpoint; Easebuzz
  failures from the verified callback. A Paid request is never turned Failed.
* The order id stays in ``gateway_response``, not ``razorpay_order_id``: the admission webhooks
  look requests up by order id and must keep ignoring student payments.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, now_datetime

from slcm.slcm.fee.payment_gateway import EASEBUZZ, GATEWAYS, RAZORPAY

DOCTYPE = "SLCM Payment Request"
# Most specific first: the first record found becomes the request's reference.
REFERENCE_DOCTYPES = ("Fee Payment", "Re Exam Payment Log", "Improvement Exam Payment Log", "Transcript Request")
# What a failed attempt references: the charge it tried to pay
CHARGE_DOCTYPES = ("Fee Demand", "Fee Invoice", "Re Exam Registration", "Improvement Exam Registration", "Transcript Request")
LEDGER_DOCTYPES = tuple(dict.fromkeys(REFERENCE_DOCTYPES + CHARGE_DOCTYPES))
# gateway_status in each gateway's own vocabulary (first failed status is the default)
PAID_GATEWAY_STATUS = {RAZORPAY: "captured", EASEBUZZ: "success"}
FAILED_GATEWAY_STATUSES = {RAZORPAY: ("failed",), EASEBUZZ: ("failure", "bounced")}
NO_REASON_SUFFIX = " (no reason given)"


def _gateway(gateway, payment_id):
	"""Gateway that collected a payment; None for manual / unknown references (not ours)."""
	if gateway in GATEWAYS:
		return gateway
	return RAZORPAY if payment_id.startswith("pay_") else None


def _transcript_gateway(response):
	try:
		data = json.loads(response or "{}")
	except ValueError:
		data = None
	if not isinstance(data, dict):
		return None, None
	return data.get("gateway"), data.get("order_id")


def _records(payment_id):
	"""Every paid SLCM record carrying this gateway payment id."""
	records = []
	for fp in frappe.get_all(
		"Fee Payment",
		filters={"reference_number": payment_id, "docstatus": 1, "payment_mode": "Online Payment"},
		fields=["name", "student", "amount", "payment_gateway", "payment_date", "creation"],
		order_by="creation asc",
	):
		# payment_date is a date; the portal records the Fee Payment at capture, so its creation has the time
		paid_on = fp.creation if getdate(fp.creation) == getdate(fp.payment_date) else fp.payment_date
		records.append(frappe._dict(
			doctype="Fee Payment", name=fp.name, student=fp.student, amount=flt(fp.amount),
			gateway=_gateway(fp.payment_gateway, payment_id), order_id=None, paid_on=paid_on,
		))
	for log_doctype, reg_doctype, reg_field in (
		("Re Exam Payment Log", "Re Exam Registration", "re_exam_registration"),
		("Improvement Exam Payment Log", "Improvement Exam Registration", "improvement_exam_registration"),
	):
		for log in frappe.get_all(
			log_doctype,
			filters={"razorpay_payment_id": payment_id, "payment_status": "Paid"},
			fields=[
				"name", "student", reg_field, "amount", "payment_gateway", "razorpay_order_id", "transaction_date",
				"payment_method", "transaction_id", "account_number_or_upi_id",
			],
			order_by="creation asc",
		):
			if frappe.db.get_value(reg_doctype, log.get(reg_field), "status") == "Cancelled":
				continue  # a cancelled registration no longer holds its fee: the money is to be refunded
			records.append(frappe._dict(
				doctype=log_doctype, name=log.name,
				student=log.student or frappe.db.get_value(reg_doctype, log.get(reg_field), "student"),
				amount=flt(log.amount), gateway=_gateway(log.payment_gateway, payment_id),
				order_id=log.razorpay_order_id, paid_on=log.transaction_date,
				details={
					"payment_method": log.payment_method, "bank_reference": log.transaction_id,
					# older Razorpay lookups stored the net banking bank code here, not an account
					"payer_account": None if _is_bank_code(log.account_number_or_upi_id) else log.account_number_or_upi_id,
				},
			))
	for tr in frappe.get_all(
		"Transcript Request",
		filters={"payment_reference": payment_id, "payment_status": "Paid"},
		fields=["name", "student", "fee_amount", "razorpay_order_id", "gateway_response", "payment_date"],
		order_by="creation asc",
	):
		gateway, order_id = _transcript_gateway(tr.gateway_response)
		# an Easebuzz-paid request may still carry the Razorpay order of an earlier attempt
		order_id = order_id if gateway == EASEBUZZ else (tr.razorpay_order_id or order_id)
		records.append(frappe._dict(
			doctype="Transcript Request", name=tr.name, student=tr.student, amount=flt(tr.fee_amount),
			gateway=_gateway(gateway, payment_id), order_id=order_id, paid_on=tr.payment_date,
		))
	return [r for r in records if r.gateway and r.amount > 0]


def _easebuzz_summary(txnid):
	"""The verified Easebuzz transaction summary stored on the Integration Request (name = txnid)."""
	row = frappe.db.get_value("Integration Request", txnid, ["output", "error"], as_dict=True) if txnid else None
	for blob in (row.output, row.error) if row else ():
		try:
			data = json.loads(blob or "{}")
		except ValueError:
			continue
		if isinstance(data, dict) and data.get("status"):
			return data
	return {}


def _razorpay_order_amount(order_id):
	"""What a Razorpay portal order charged: the amount on its checkout intent (razorpay_reconcile.attach_intent),
	or 0 when the order has none (admission flows, orders older than intents)."""
	if not order_id or not str(order_id).startswith("order_"):
		return 0
	rows = frappe.get_all(
		"Integration Request",
		filters={"integration_request_service": "Razorpay", "data": ("like", f"%{order_id}%")},
		fields=["data"],
		limit=5,
		ignore_permissions=True,
	)
	for row in rows:
		try:
			intent = (json.loads(row.data or "{}") or {}).get("slcm_intent") or {}
		except (ValueError, AttributeError):
			continue
		if intent.get("order_id") == order_id:
			return flt(intent.get("amount"), 2)
	return 0


def _summary_details(summary):
	return {
		"payment_method": summary.get("mode"),
		"bank_reference": summary.get("bank_ref_num"),
		"payer_account": summary.get("payer"),
		"payer_bank": summary.get("bank_name"),
	}


def _razorpay_bank_name(code):
	"""Bank name for a Razorpay bank / card-issuer code (IFSC prefix, e.g. UTIB → Axis Bank), from Razorpay's
	GET /v1/methods list (cached for a week); the code itself when unknown."""
	if not code:
		return None
	names = frappe.cache().get_value("slcm_razorpay_bank_names")
	if names is None:
		names = {}
		try:
			import requests

			api_key = frappe.db.get_single_value("Razorpay Settings", "api_key") or ""
			if api_key:
				# a public endpoint: authenticated with the key id alone (the key secret is rejected with 401)
				resp = requests.get("https://api.razorpay.com/v1/methods", auth=(api_key, ""), timeout=10)
				if resp.status_code == 200:
					names = (resp.json() or {}).get("netbanking") or {}
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Razorpay bank names lookup failed")
		frappe.cache().set_value("slcm_razorpay_bank_names", names, expires_in_sec=7 * 86400 if names else 3600)
	return names.get(code) or code


def _razorpay_payer(raw):
	"""(payer account, payer bank) from a Razorpay payment: UPI ID / masked card / wallet, and the net banking
	bank or card issuer. Razorpay never shares the payer's bank account number or IFSC."""
	card = raw.get("card") if isinstance(raw.get("card"), dict) else {}
	upi = raw.get("upi") if isinstance(raw.get("upi"), dict) else {}
	masked_card = None
	if card.get("last4"):
		masked_card = " ".join(filter(None, ["XXXX XXXX XXXX " + card["last4"], card.get("network")]))
	account = raw.get("vpa") or upi.get("vpa") or masked_card or raw.get("wallet")
	return account, _razorpay_bank_name(raw.get("bank") or card.get("issuer"))


def _known(details):
	"""Only values the gateway reported: never blank out what an earlier sync / the Razorpay lookup filled."""
	return {k: str(v).strip()[:140] for k, v in (details or {}).items() if v and str(v).strip()}


def _order_id(payment_id, records):
	for r in records:
		if r.order_id:
			return r.order_id
	# Fee Payments keep only the payment id; the portal's payment log has the order / txnid
	return frappe.db.get_value(
		"Student Fee Payment Log",
		{"razorpay_payment_id": payment_id, "razorpay_order_id": ("is", "set")},
		"razorpay_order_id",
	)


def _student_identity(student):
	"""Student Name (first name) and Student ID (registration id) shown in a request's gateway_response."""
	if not student:
		return {}
	row = frappe.db.get_value("Student Master", student, ["first_name", "registration_id"], as_dict=True)
	if not row:
		return {}
	return {"student_name": row.first_name or "", "registration_id": row.registration_id or ""}


def _student_email(student):
	if not student:
		return None
	row = frappe.db.get_value("Student Master", student, ["email", "official_email_id", "personal_email"], as_dict=True)
	return row and (row.email or row.official_email_id or row.personal_email)


def _ensure_gateway_record(gateway):
	# The Payment Gateway row is created when the gateway's settings are first saved; the request links to it.
	if not frappe.db.exists("Payment Gateway", gateway):
		from payments.utils import create_payment_gateway

		create_payment_gateway(gateway)


def _existing(payment_id):
	"""This module's live request for a gateway payment id (submitted, student reference)."""
	return frappe.db.get_value(
		DOCTYPE,
		{"transaction_id": payment_id, "reference_doctype": ("in", LEDGER_DOCTYPES), "docstatus": 1},
		["name", "status", "docstatus", "reference_doctype"],
		as_dict=True,
	)


def _write(existing, values, student, payment_id):
	"""Update the existing request (changed fields only) or insert + submit a new one."""
	_ensure_gateway_record(values["payment_gateway"])
	if existing:
		current = frappe.db.get_value(DOCTYPE, existing.name, list(values), as_dict=True)
		changed = {k: v for k, v in values.items() if str(current.get(k) or "") != str(v or "")}
		if not frappe.db.get_value(DOCTYPE, existing.name, "email_to"):
			email = _student_email(student)
			if email:
				changed["email_to"] = email
		if changed:
			frappe.db.set_value(DOCTYPE, existing.name, changed)
		return existing.name

	if payment_id and _recorded_elsewhere(payment_id):
		return None

	doc = frappe.get_doc({"doctype": DOCTYPE, "email_to": _student_email(student), **values})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc.name


def _recorded_elsewhere(payment_id):
	"""A live request made by another flow (admission, ERPNext demo data) already holds this payment."""
	return any(
		frappe.db.exists(DOCTYPE, {field: payment_id, "docstatus": ("<", 2)})
		for field in ("transaction_id", "razorpay_payment_id")
	)


def sync(payment_id):
	"""Create or refresh the SLCM Payment Request of one gateway payment. Returns its name (or None)."""
	payment_id = (payment_id or "").strip()
	if not payment_id:
		return None
	records = _records(payment_id)
	existing = _existing(payment_id)

	if not records:
		if existing and existing.status == "Paid" and existing.reference_doctype in REFERENCE_DOCTYPES:
			_detach(existing.name, payment_id)
		# only a Paid request answers "is this capture recorded?" (a Failed one for the same id does not)
		return existing.name if existing and existing.status == "Paid" else None

	primary = records[0]
	gateway = primary.gateway
	order_id = _order_id(payment_id, records)
	paid_on = min((get_datetime(r.paid_on) for r in records if r.paid_on), default=None)
	allocated = flt(sum(r.amount for r in records), 2)
	summary = _easebuzz_summary(order_id) if gateway == EASEBUZZ else {}
	# What the gateway captured: bookings are capped at the outstanding (the excess is flagged "needs manual
	# allocation"), so the request shows the captured amount, not only what was booked. Easebuzz reports it in
	# its summary; a Razorpay portal order captures exactly the amount its checkout intent charged.
	charged = flt(summary.get("amount"), 2) if gateway == EASEBUZZ else _razorpay_order_amount(order_id)
	captured = max(charged, allocated)
	values = {
		"reference_doctype": primary.doctype,
		"reference_name": primary.name,
		"amount": captured,
		"currency": "INR",
		"status": "Paid",
		"gateway_status": PAID_GATEWAY_STATUS[gateway],
		"payment_gateway": gateway,
		"transaction_id": payment_id,
		"razorpay_payment_id": payment_id if gateway == RAZORPAY else None,
		"gateway_payment_id": payment_id,
		"gateway_order_id": order_id,
		"gateway_error_code": None,
		"paid_on": paid_on or now_datetime(),
		"failure_message": None,  # a late capture of a payment first reported failed
		"gateway_response": json.dumps({
			"gateway": gateway,
			"payment_id": payment_id,
			"order_id": order_id,  # Razorpay order / Easebuzz txnid
			"student": primary.student,
			**_student_identity(primary.student),
			"records": [{"doctype": r.doctype, "name": r.name, "amount": r.amount} for r in records],
			**({"unallocated": flt(captured - allocated, 2)} if captured - allocated > 0.01 else {}),
		}, indent=2, default=str),
	}
	for r in records:
		values.update(_known(r.get("details")))
	values.update(_known(_summary_details(summary)))
	if not order_id:
		del values["gateway_order_id"]
	if existing and not paid_on:
		del values["paid_on"]  # keep the time already stamped on the request
	name = _write(existing, values, primary.student, payment_id)
	if name:
		apply_payer_details(name)
		if gateway == RAZORPAY and not existing:
			# method / bank / payer come from Razorpay's API: fetch right after the payment commits, off the request
			frappe.db.after_commit.add(lambda: _enqueue_enrich(name))
	return name


def _enqueue_enrich(request_name):
	# runs after the payment's commit: a queue outage must not surface to the payer (the hourly sweep catches up)
	try:
		frappe.enqueue("slcm.slcm.fee.payment_ledger.enrich_one", queue="short", request_name=request_name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"SLCM Payment Request enrich not queued: {request_name}")


def _charge_of(doctype, name):
	"""The charge a booked record paid: Fee Payment → its Fee Invoice / first Fee Demand, exam log → registration."""
	if doctype == "Fee Payment":
		invoice = frappe.db.get_value("Fee Payment", name, "fee_invoice")
		if invoice:
			return "Fee Invoice", invoice
		demand = frappe.db.get_value(
			"Fee Payment Demand Row", {"parent": name, "parenttype": "Fee Payment"}, "fee_demand", order_by="idx asc",
		)
		return ("Fee Demand", demand) if demand else (None, None)
	if doctype == "Re Exam Payment Log":
		return "Re Exam Registration", frappe.db.get_value(doctype, name, "re_exam_registration")
	if doctype == "Improvement Exam Payment Log":
		return "Improvement Exam Registration", frappe.db.get_value(doctype, name, "improvement_exam_registration")
	return doctype, name


def _detach(request_name, payment_id):
	"""No record holds this payment any more (Fee Payment cancelled, exam fee / transcript refunded). The gateway
	still captured - and may already have settled - it, so the request stays Paid and submitted (cancelling it
	would reverse a real bank settlement in ERPNext). It now points at the charge, which also frees the
	cancelled record for deletion."""
	pr = frappe.db.get_value(
		DOCTYPE, request_name, ["reference_doctype", "reference_name", "gateway_response", "amount"], as_dict=True
	)
	doctype, name = _charge_of(pr.reference_doctype, pr.reference_name)
	refunded = any(
		frappe.db.exists(dt, {"razorpay_payment_id": payment_id, "payment_status": "Refunded"})
		for dt in ("Re Exam Payment Log", "Improvement Exam Payment Log")
	) or bool(frappe.db.exists(
		# "Refund Pending" (a rejected request) is not refunded yet: the money is still held and owed back
		"Transcript Request", {"payment_reference": payment_id, "payment_status": "Refunded"}
	))
	if refunded:
		note = _("Refunded: the payment was refunded through the gateway.")
	else:
		note = _("No SLCM record holds this payment any more ({0} {1} was cancelled). The money was captured: "
			"re-record or refund it.").format(pr.reference_doctype, pr.reference_name)
	try:
		response = json.loads(pr.gateway_response or "{}")
	except ValueError:
		response = {}
	response.update({"records": [], "note": note, "detached_from": f"{pr.reference_doctype} {pr.reference_name}"})
	update = {"gateway_response": json.dumps(response, indent=2, default=str)}
	if name:
		update.update(reference_doctype=doctype, reference_name=name)
	if refunded:
		update["gateway_status"] = "refunded"
	frappe.db.set_value(DOCTYPE, request_name, update)
	frappe.get_doc(DOCTYPE, request_name).add_comment("Comment", note)
	if refunded and not _refund_log(request_name):
		# the record was marked Refunded (refund made in the gateway dashboard): one refund row for the whole
		# payment, so ERPNext books it (Gateway Refund) like any other recorded refund
		_save_refund_log(request_name, [{
			"refund_id": f"{pr.reference_doctype} {pr.reference_name} marked Refunded", "amount": flt(pr.amount, 2),
			"refunded_on": str(getdate()), "source": f"{pr.reference_doctype} marked Refunded",
		}])


# ── refunds (recorded, not paid out, by SLCM) ─────────────────────────────────


def refundable_amount(request_name):
	"""Money on a paid request that no SLCM record holds - captured but not applied (duplicate payment, dues
	settled meanwhile, cancelled request, Fee Payment cancelled) - less what was already recorded as refunded."""
	pr = frappe.db.get_value(
		DOCTYPE, request_name,
		["status", "docstatus", "amount", "gateway_response", "transaction_id", "refunded_amount", "reference_doctype"],
		as_dict=True,
	)
	if not pr or pr.status != "Paid" or pr.docstatus != 1 or pr.reference_doctype not in LEDGER_DOCTYPES:
		return 0
	try:
		response = json.loads(pr.gateway_response or "{}")
	except ValueError:
		response = {}
	if response.get("records"):
		held = flt(response.get("unallocated"))  # booked in part: only the excess is refundable
	else:
		held = flt(pr.amount)  # no record holds any of it
	return max(flt(held - flt(pr.refunded_amount), 2), 0)


def _refund_log(request_name):
	try:
		log = json.loads(frappe.db.get_value(DOCTYPE, request_name, "refund_log") or "[]")
	except ValueError:
		log = []
	return log if isinstance(log, list) else []


def _save_refund_log(request_name, log, comment=None):
	"""Store the refund log and the summary fields read by reports and the ERPNext bridge:
	refunded_* = every refund recorded (bridge: Gateway Refund), refund_settled_* = the part a payout deducted
	(bridge: Gateway Refund Payout)."""
	settled = [r for r in log if r.get("payout")]
	frappe.db.set_value(DOCTYPE, request_name, {
		"refund_log": json.dumps(log, indent=1, default=str),
		"refunded_amount": flt(sum(flt(r.get("amount")) for r in log), 2),
		"refunded_on": max((getdate(r["refunded_on"]) for r in log if r.get("refunded_on")), default=None),
		"refund_reference": ", ".join(str(r.get("refund_id")) for r in log if r.get("refund_id"))[:140],
		"refund_settled_amount": flt(sum(flt(r.get("amount")) for r in settled), 2),
		"refund_settled_on": max((getdate(r["payout_date"]) for r in settled if r.get("payout_date")), default=None),
		"refund_settlement_reference": ", ".join(str(r["payout"]) for r in settled)[:140],
	})
	if comment:
		frappe.get_doc(DOCTYPE, request_name).add_comment("Comment", comment)


def record_gateway_refund(payment_id, refund_id, amount, refunded_on=None, source="settlement",
		payout=None, payout_date=None):
	"""A refund the gateway reports (payout refund line, refund webhook): record it on the payment's request, once
	per refund id. ``payout`` / ``payout_date`` say it was taken off that payout (ERPNext: Dr Gateway Clearing /
	Cr Bank). A refund recorded earlier by hand with the same amount and no payout is the same refund: it gets the
	payout instead of a second row. Returns the request name when something changed, else None."""
	payment_id, refund_id, amount = (payment_id or "").strip(), str(refund_id or "").strip(), flt(amount, 2)
	if not payment_id or not refund_id or amount <= 0:
		return None
	name = frappe.db.get_value(
		DOCTYPE,
		{"transaction_id": payment_id, "docstatus": 1, "status": "Paid", "reference_doctype": ("in", LEDGER_DOCTYPES)},
		"name",
	)
	if not name:
		return None
	frappe.db.sql(f"SELECT name FROM `tab{DOCTYPE}` WHERE name = %s FOR UPDATE", name)
	log = _refund_log(name)
	row = next((r for r in log if r.get("refund_id") == refund_id or r.get("gateway_refund_id") == refund_id), None)
	if not row:
		# the same refund recorded earlier without the gateway's id: by hand, or a record marked Refunded
		row = next((r for r in log if not r.get("gateway_refund_id") and abs(flt(r.get("amount")) - amount) <= 0.01
		            and (r.get("source") == "recorded by hand" or str(r.get("source") or "").endswith("marked Refunded"))),
		           None)
		if row:
			row["gateway_refund_id"] = refund_id
			if not payout:
				_save_refund_log(name, log)
				return name
	if row:
		if not payout or row.get("payout"):
			return None
		row.update(payout=payout, payout_date=str(getdate(payout_date)) if payout_date else str(getdate()))
		_save_refund_log(name, log, _("Refund {0} of ₹{1} was deducted from payout {2}.").format(
			refund_id, f"{amount:,.2f}", payout))
		return name
	log.append({
		"refund_id": refund_id, "amount": amount,
		"refunded_on": str(getdate(refunded_on)) if refunded_on else str(getdate()), "source": source,
		**({"payout": payout, "payout_date": str(getdate(payout_date)) if payout_date else str(getdate())} if payout else {}),
	})
	_save_refund_log(name, log, _("Refund {0} of ₹{1} reported by the gateway ({2}).").format(
		refund_id, f"{amount:,.2f}", source))
	return name


def remove_gateway_refund(payment_id, refund_id):
	"""A refund the gateway reports as failed: drop it from the request (the money stayed with the university)."""
	name = frappe.db.get_value(DOCTYPE, {"transaction_id": payment_id, "docstatus": 1, "status": "Paid"}, "name")
	if not name or not refund_id:
		return None
	log = _refund_log(name)
	kept = [r for r in log if refund_id not in (r.get("refund_id"), r.get("gateway_refund_id"))]
	if len(kept) == len(log):
		return None
	_save_refund_log(name, kept, _("Refund {0} failed at the gateway: removed.").format(refund_id))
	return name


@frappe.whitelist()
def get_refundable(request_name):
	frappe.has_permission(DOCTYPE, "read", request_name, throw=True)
	return refundable_amount(request_name)


@frappe.whitelist()
def record_refund(request_name, refund_reference, refunded_on, amount):
	"""Record a refund made in the gateway dashboard (SLCM does not call the gateway's refund API)."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	amount = flt(amount, 2)
	refund_reference = (refund_reference or "").strip()
	if not refund_reference:
		frappe.throw(_("Enter the refund id / UTR shown in the gateway dashboard."))
	if amount <= 0:
		frappe.throw(_("Enter the refunded amount."))
	frappe.db.sql(f"SELECT name FROM `tab{DOCTYPE}` WHERE name = %s FOR UPDATE", request_name)
	refundable = refundable_amount(request_name)
	if amount - refundable > 0.01:
		frappe.throw(
			_("Only ₹{0} of this payment is unapplied and can be recorded as refunded here. A refund of fees that "
			  "were applied to dues is recorded with a Fee Refund (Refund Mode: Payment Gateway).").format(f"{refundable:,.2f}")
		)
	log = _refund_log(request_name)
	if any(refund_reference in (r.get("refund_id"), r.get("gateway_refund_id")) for r in log):
		frappe.throw(_("Refund {0} is already recorded on this payment.").format(refund_reference))
	log.append({
		"refund_id": refund_reference, "amount": amount,
		"refunded_on": str(getdate(refunded_on)) if refunded_on else str(getdate()), "source": "recorded by hand",
		"by": frappe.session.user,
	})
	_save_refund_log(request_name, log, _("Refund of ₹{0} recorded (reference {1}) by {2}.").format(
		f"{amount:,.2f}", refund_reference, frappe.session.user))
	return {"refunded_amount": flt(sum(flt(r["amount"]) for r in log), 2), "still_refundable": refundable_amount(request_name)}


# ── failed attempts ─────────────────────────────────────────────────────────────


def record_unapplied(gateway, payment_id, order_id, reference_doctype, reference_name, amount, student, note=None,
		payment_details=None):
	"""Money the gateway captured that no record took (duplicate payment, cancelled transcript request, charges
	settled meanwhile, amount mismatch): still one Paid request, referencing the charge, flagged for refund."""
	payment_id = (payment_id or "").strip()
	amount = flt(amount, 2)
	if gateway not in GATEWAYS or not payment_id or not reference_name or amount <= 0:
		return None
	existing = _existing(payment_id)
	if existing and existing.status == "Paid" and existing.reference_doctype in REFERENCE_DOCTYPES:
		return existing.name  # a record took it after all
	note = note or _("Captured but not applied to any record: needs refund or manual allocation.")
	values = {
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"amount": amount,
		"currency": "INR",
		"status": "Paid",
		"gateway_status": PAID_GATEWAY_STATUS[gateway],
		"payment_gateway": gateway,
		"transaction_id": payment_id,
		"razorpay_payment_id": payment_id if gateway == RAZORPAY else None,
		"gateway_payment_id": payment_id,
		"failure_message": None,  # a late capture of an attempt first reported failed
		"gateway_error_code": None,
		"paid_on": now_datetime(),
		"gateway_response": json.dumps({
			"gateway": gateway, "payment_id": payment_id, "order_id": order_id, "student": student,
			**_student_identity(student),
			"records": [], "unallocated": amount, "note": note,
		}, indent=2, default=str),
		**_known({**(payment_details or {}), "gateway_order_id": order_id}),
	}
	if existing:
		del values["paid_on"]
	name = _write(existing, values, student, payment_id)
	if name and not (existing and existing.status == "Paid"):
		frappe.get_doc(DOCTYPE, name).add_comment("Comment", note)
	return name


def record_unapplied_capture(intent, txnid, payment_id, summary, note=None):
	"""record_unapplied() for a verified Easebuzz success no flow handler booked."""
	doctype, name = _easebuzz_charge(intent)
	return record_unapplied(
		EASEBUZZ, payment_id, txnid, doctype, name, flt(summary.get("amount")) or flt(intent.get("amount")),
		intent.get("student"), note, _summary_details(summary),
	)


def _close_superseded_failure(txnid, payment_id):
	"""An Easebuzz failure reported without an easepayid is keyed on the txnid; once that checkout is captured
	under its real easepayid, the Failed request no longer describes what happened."""
	name = frappe.db.get_value(
		DOCTYPE,
		{"transaction_id": txnid, "gateway_order_id": txnid, "status": "Failed", "docstatus": 1,
			"reference_doctype": ("in", LEDGER_DOCTYPES)},
		"name",
	)
	if name and txnid != payment_id:
		frappe.db.set_value(DOCTYPE, name, "status", "Cancelled")
		frappe.get_doc(DOCTYPE, name).add_comment("Comment", _("Superseded: this checkout was later captured as {0}.").format(payment_id))


def record_failure(gateway, payment_id, reference_doctype, reference_name, amount, student, reason,
		gateway_status=None, order_id=None, details=None, error_code=None, payment_details=None,
		amount_is_estimate=False):
	"""Create or refresh the Failed request of one failed gateway attempt. Returns its name (or None)."""
	payment_id = (payment_id or "").strip()
	amount = flt(amount, 2)
	if gateway not in GATEWAYS or not reference_name or amount <= 0:
		return None
	if payment_id:
		existing = _existing(payment_id)
	else:
		# no gateway payment id reported (e.g. the Helpdesk transcript panel): one Failed request per charge
		existing = frappe.db.get_value(
			DOCTYPE,
			{
				"reference_doctype": reference_doctype, "reference_name": reference_name, "status": "Failed",
				"transaction_id": ("is", "not set"), "docstatus": 1,
			},
			["name", "status", "docstatus"],
			as_dict=True,
		)
	if existing and existing.status != "Failed":
		return existing.name  # already Paid / Cancelled: a stray failure event never downgrades it

	statuses = FAILED_GATEWAY_STATUSES[gateway]
	values = {
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"amount": amount,
		"currency": "INR",
		"status": "Failed",
		"gateway_status": gateway_status if gateway_status in statuses else statuses[0],
		"payment_gateway": gateway,
		"transaction_id": payment_id or None,
		"razorpay_payment_id": payment_id if gateway == RAZORPAY and payment_id else None,
		"gateway_payment_id": payment_id or None,
		"gateway_response": json.dumps({
			"gateway": gateway,
			"payment_id": payment_id or None,
			"order_id": order_id,  # Razorpay order / Easebuzz txnid
			"student": student,
			**_student_identity(student),
			**(details or {}),
		}, indent=2, default=str),
	}
	# Only what this event reported: never blank out a reason / code / order id filled earlier
	values.update(_known({**(payment_details or {}), "gateway_order_id": order_id, "gateway_error_code": error_code}))
	if existing and amount_is_estimate:
		del values["amount"]  # keep the attempt amount Razorpay reported (enrich_razorpay_details)
	reason = (reason or "").strip()[:1000]
	if reason:
		values["failure_message"] = reason
	elif not existing:
		values["failure_message"] = _("Payment failed at {0}").format(gateway) + NO_REASON_SUFFIX
	return _write(existing, values, student, payment_id)


def _charge_amount(doctype, name):
	if doctype == "Fee Demand":
		row = frappe.db.get_value(doctype, name, ["outstanding_amount", "original_amount"], as_dict=True) or {}
		return flt(row.get("outstanding_amount")) or flt(row.get("original_amount"))
	row = frappe.db.get_value(doctype, name, ["outstanding_amount", "final_payable_amount", "total_amount"], as_dict=True) or {}
	return flt(row.get("outstanding_amount")) or flt(row.get("final_payable_amount")) or flt(row.get("total_amount"))


_ERROR_CODE = re.compile(r"Code:\s*([A-Za-z0-9_]+)")
# A bare bank code (IFSC prefix, e.g. SBIN / BARB_R) left by an earlier lookup: replaced by the bank's name
_BANK_CODE = re.compile(r"^[A-Z]{4}(_[A-Z0-9]+)?$")


def _is_bank_code(value):
	return bool(value) and bool(_BANK_CODE.match(str(value).strip()))


def _log_error_code(row):
	# mark_*_payment_failed log "Code: BAD_REQUEST_ERROR — <description>"
	match = _ERROR_CODE.search(row.error_message or "")
	return match.group(1) if match and match.group(1) != "N" else None


def _log_reason(row):
	reason = (row.failure_reason or "").strip()
	if not reason:
		# "Code: BAD_REQUEST_ERROR — Payment failed" → keep only what the gateway said
		reason = (row.error_message or "").strip().rstrip("—").strip()
	return reason


def sync_failed_fee_attempt(payment_id):
	"""Failed Razorpay fee attempt (student / parent portal), rebuilt from its Student Fee Payment Log rows."""
	rows = frappe.get_all(
		"Student Fee Payment Log",
		filters={"event_type": "Payment Failed", "razorpay_payment_id": payment_id},
		fields=["parent", "fee_demand", "invoice", "amount", "razorpay_order_id", "failure_reason", "error_message", "paid_by_role"],
		order_by="creation asc",
	)
	charges, estimated = {}, False
	for row in rows:
		doctype, name = ("Fee Invoice", row.invoice) if row.invoice else ("Fee Demand", row.fee_demand)
		if name and (doctype, name) not in charges:
			# the failure log has no amount: use what is due now (Razorpay's own figure replaces it later)
			estimated = estimated or not flt(row.amount)
			charges[(doctype, name)] = flt(row.amount) or _charge_amount(doctype, name)
	if not charges:
		return None
	(doctype, name), first = next(iter(charges)), rows[0]
	return record_failure(
		RAZORPAY, payment_id, doctype, name, sum(charges.values()), first.parent,
		next((_log_reason(r) for r in rows if _log_reason(r)), None), "failed",
		order_id=next((r.razorpay_order_id for r in rows if r.razorpay_order_id), None),
		error_code=next((_log_error_code(r) for r in rows if _log_error_code(r)), None),
		amount_is_estimate=estimated,
		details={
			"paid_by_role": first.paid_by_role,
			"charges": [{"doctype": dt, "name": dn, "amount": amt} for (dt, dn), amt in charges.items()],
		},
	)


def _easebuzz_charge(intent):
	flow = intent.get("flow")
	if flow == "demands":
		if intent.get("demand_names"):
			return "Fee Demand", intent["demand_names"][0]
		return "Re Exam Registration", (intent.get("re_exam_registrations") or [None])[0]
	if flow == "invoice":
		return "Fee Invoice", intent.get("invoice")
	if flow == "re_exam":
		return "Re Exam Registration", intent.get("registration")
	if flow == "improvement_exam":
		return "Improvement Exam Registration", intent.get("registration")
	if flow == "transcript":
		return "Transcript Request", intent.get("request_name")
	return None, None


def record_easebuzz_failure(intent, txnid, payment_id, summary):
	"""Failed Easebuzz checkout (any flow), from the verified callback / reconciliation."""
	doctype, name = _easebuzz_charge(intent)
	status = summary.get("status") or ""
	return record_failure(
		EASEBUZZ, payment_id, doctype, name, intent.get("amount"), intent.get("student"),
		summary.get("error") or _("Easebuzz reported the payment as {0}").format(status or "failed"), status,
		order_id=txnid,
		details={"flow": intent.get("flow"), "source": summary.get("source")},
		payment_details=_summary_details(summary),
	)


def _quietly(fn, label, *args, **kwargs):
	"""Run a ledger write inside a payment flow: a failure is logged, never raised, and leaves no partial writes."""
	savepoint = "slcm_payment_ledger"
	try:
		frappe.db.savepoint(savepoint)
		return fn(*args, **kwargs)
	except Exception as error:
		try:
			frappe.db.rollback(save_point=savepoint)
		except Exception:
			# the database already rolled the whole transaction back (deadlock / lost connection): the
			# payment's own writes are gone too, so fail the flow cleanly instead of reporting success
			raise error from None
		frappe.log_error(frappe.get_traceback(), f"SLCM Payment Request sync failed: {label}")


def sync_quietly(payment_id):
	return _quietly(sync, payment_id, payment_id)


def record_failure_quietly(*args, **kwargs):
	return _quietly(record_failure, args[1] if len(args) > 1 else "failure", *args, **kwargs)


def record_easebuzz_failure_quietly(intent, txnid, payment_id, summary):
	return _quietly(record_easebuzz_failure, txnid, intent, txnid, payment_id, summary)


def record_easebuzz_capture_quietly(intent, txnid, payment_id, summary, note=None):
	"""After a verified Easebuzz success: the request built from the records, else one for the unapplied money."""
	name = sync_quietly(payment_id) or _quietly(record_unapplied_capture, txnid, intent, txnid, payment_id, summary, note)
	_quietly(_close_superseded_failure, txnid, txnid, payment_id)
	return name


def record_unapplied_quietly(*args, **kwargs):
	return _quietly(record_unapplied, args[1] if len(args) > 1 else "unapplied", *args, **kwargs)


# ── doc_events ──────────────────────────────────────────────────────────────────


def on_fee_payment(doc, method=None):
	if doc.payment_mode == "Online Payment" and doc.reference_number:
		if method == "on_cancel":
			# should the sync below fail, the request must still not block this cancel (the hourly sweep cancels it)
			doc.ignore_linked_doctypes = (*(doc.get("ignore_linked_doctypes") or ()), DOCTYPE)
		sync_quietly(doc.reference_number)


def on_payment_log(doc, method=None):
	"""Student Fee Payment Log rows: "Captured" carries the order id / Easebuzz txnid (written after the
	Fee Payment); "Payment Failed" with a Razorpay id is a failed portal attempt (Easebuzz failures are
	recorded from the callback, which knows the exact amount)."""
	payment_id = (doc.razorpay_payment_id or "").strip()
	if not payment_id:
		return
	if doc.event_type == "Captured":
		sync_quietly(payment_id)
	elif doc.event_type == "Payment Failed" and payment_id.startswith("pay_"):
		_quietly(sync_failed_fee_attempt, payment_id, payment_id)


def on_exam_registration(doc, method=None):
	"""A paid Re Exam / Improvement Exam Registration cancelled: its fee is no longer held, so its request moves
	to the charge with the money listed for a refund (Payments to Refund)."""
	if doc.status == "Cancelled" and doc.get("payment_reference") and doc.has_value_changed("status"):
		sync_quietly(doc.payment_reference)


def on_exam_payment_log(doc, method=None):
	if doc.razorpay_payment_id:
		sync_quietly(doc.razorpay_payment_id)


# ── sweep / backfill ────────────────────────────────────────────────────────────


def _payment_ids(since=None):
	since_filter = {"modified": (">=", since)} if since else {}
	ids = set(frappe.get_all(
		"Fee Payment",
		filters={"payment_mode": "Online Payment", "reference_number": ("is", "set"), "docstatus": ("in", (1, 2)), **since_filter},
		pluck="reference_number",
	))
	for log_doctype in ("Re Exam Payment Log", "Improvement Exam Payment Log"):
		ids.update(frappe.get_all(log_doctype, filters={"razorpay_payment_id": ("is", "set"), **since_filter}, pluck="razorpay_payment_id"))
	ids.update(frappe.get_all(
		"Transcript Request", filters={"payment_reference": ("is", "set"), **since_filter}, pluck="payment_reference",
	))
	return sorted(i.strip() for i in ids if i and i.strip())


def _failed_fee_payment_ids(since=None):
	filters = {"event_type": "Payment Failed", "razorpay_payment_id": ("like", "pay_%")}
	if since:
		filters["modified"] = (">=", since)
	return sorted(set(frappe.get_all("Student Fee Payment Log", filters=filters, pluck="razorpay_payment_id")))


def sync_all(since=None):
	"""Create / refresh the Payment Requests of all student payments and failed Razorpay fee attempts
	(or only those touched since ``since``)."""
	done = failed = 0
	jobs = [(sync, pid) for pid in _payment_ids(since)] + [(sync_failed_fee_attempt, pid) for pid in _failed_fee_payment_ids(since)]
	for fn, payment_id in jobs:
		try:
			fn(payment_id)
			frappe.db.commit()
			done += 1
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"SLCM Payment Request sync failed: {payment_id}")
			failed += 1
	return {"synced": done, "failed": failed}


def fill_student_identity(limit=2000):
	"""Add Student Name and Student ID to the gateway_response of student requests written before it had them."""
	rows = frappe.get_all(
		DOCTYPE,
		filters=[
			["reference_doctype", "in", LEDGER_DOCTYPES],
			["gateway_response", "like", '%"student": "%'],
			["gateway_response", "not like", '%"student_name"%'],
		],
		fields=["name", "gateway_response"],
		limit=limit,
		order_by="creation desc",
	)
	updated = 0
	for row in rows:
		if '"student_name"' in (row.gateway_response or ""):
			continue
		try:
			response = json.loads(row.gateway_response)
		except ValueError:
			continue
		identity = _student_identity(response.get("student"))
		if not identity or not isinstance(response, dict):
			continue
		ordered = {}
		for key, value in response.items():
			ordered[key] = value
			if key == "student":
				ordered.update(identity)
		frappe.db.set_value(
			DOCTYPE, row.name, "gateway_response", json.dumps(ordered, indent=2, default=str), update_modified=False
		)
		updated += 1
	return updated


def fill_common_ids():
	"""Gateway-neutral ids on every request. Admission / PACE flows update the Razorpay-named fields with db_set,
	including a retry on the same request (new order / payment id): the common ids follow them, and payment
	details looked up for the previous attempt are cleared so the next lookup describes the new one."""
	frappe.db.sql(
		"""update `tabSLCM Payment Request`
		set payment_method = if(ifnull(gateway_payment_id, '') = '', payment_method, null),
			bank_reference = if(ifnull(gateway_payment_id, '') = '', bank_reference, null),
			payer_account = if(ifnull(gateway_payment_id, '') = '', payer_account, null),
			payer_bank = if(ifnull(gateway_payment_id, '') = '', payer_bank, null),
			gateway_payment_id = razorpay_payment_id
		where ifnull(razorpay_payment_id, '') != '' and ifnull(gateway_payment_id, '') != razorpay_payment_id"""
	)
	frappe.db.sql(
		"""update `tabSLCM Payment Request` set gateway_payment_id = transaction_id
		where ifnull(gateway_payment_id, '') = '' and ifnull(razorpay_payment_id, '') = '' and transaction_id like 'pay\\_%%'"""
	)
	frappe.db.sql(
		"""update `tabSLCM Payment Request` set gateway_order_id = razorpay_order_id
		where ifnull(razorpay_order_id, '') != '' and ifnull(gateway_order_id, '') != razorpay_order_id"""
	)
	frappe.db.sql(
		"""update `tabSLCM Payment Request` set gateway_order_id = transaction_id
		where ifnull(gateway_order_id, '') = '' and ifnull(razorpay_order_id, '') = '' and transaction_id like 'order\\_%%'"""
	)
	frappe.db.commit()


def enrich_razorpay_details(since=None, limit=200, recheck=False):
	"""Payment method, bank reference (RRN), payer account and order id of Razorpay payments, from GET /v1/payments/{id}.
	Background only (never inside a payment flow); fills empty fields, never overwrites them. A failed attempt's
	amount is set to Razorpay's (the portal's failure log has none); a paid request whose amount differs from
	what Razorpay captured is flagged in the Error Log, never changed. ``recheck`` re-reads rows already filled."""
	from slcm.api.student_payment import _fetch_razorpay_payment_details

	conditions = ["gateway_payment_id like 'pay\\_%%'", "status in ('Paid', 'Failed')",
		"ifnull(payment_gateway, 'Razorpay') = 'Razorpay'", "docstatus < 2"]
	if not recheck:
		conditions.append("""(ifnull(payment_method, '') = '' or ifnull(gateway_order_id, '') = ''
			or (status = 'Failed' and ifnull(gateway_error_code, '') = ''))""")
	values = {"limit": limit}
	if since:
		conditions.append("modified >= %(since)s")
		values["since"] = since
	rows = frappe.db.sql(
		f"""select name, gateway_payment_id, gateway_order_id, payment_method, bank_reference, payer_account,
			payer_bank, gateway_error_code, failure_message, status, amount, reference_doctype
		from `tabSLCM Payment Request` where {" and ".join(conditions)} order by modified desc limit %(limit)s""",
		values,
		as_dict=True,
	)
	filled = 0
	for row in rows:
		filled += _enrich_row(row, _fetch_razorpay_payment_details)
	return filled


def enrich_one(request_name):
	"""Background job queued when a Razorpay request is created: fill its payment details now, not at the next sweep."""
	from slcm.api.student_payment import _fetch_razorpay_payment_details

	row = frappe.db.get_value(
		DOCTYPE, request_name,
		["name", "gateway_payment_id", "gateway_order_id", "payment_method", "bank_reference", "payer_account",
			"payer_bank", "gateway_error_code", "failure_message", "status", "amount", "reference_doctype"],
		as_dict=True,
	)
	if row and (row.gateway_payment_id or "").startswith("pay_"):
		_enrich_row(row, _fetch_razorpay_payment_details)


def _enrich_row(row, fetch):
	"""Fill one Razorpay request from GET /v1/payments/{id}; returns 1 when anything changed."""
	details = fetch(row.gateway_payment_id)
	if not details:
		return 0
	raw = details.get("raw_data") or {}
	account, bank = _razorpay_payer(raw)
	if not account and details.get("account_number_or_upi_id") not in (None, "", raw.get("bank")):
		account = details["account_number_or_upi_id"]
	# rows filled before the Payer Bank field held the net banking bank code as the payer account
	wrong_account = bool(row.payer_account) and row.payer_account == raw.get("bank")
	update = _known({
		"gateway_order_id": None if row.gateway_order_id else raw.get("order_id"),
		"payment_method": None if row.payment_method else details.get("payment_method"),
		"bank_reference": None if row.bank_reference else details.get("transaction_id"),
		"payer_account": None if row.payer_account and not wrong_account else account,
		"payer_bank": None if row.payer_bank and not (_is_bank_code(row.payer_bank) and bank != row.payer_bank) else bank,
		"gateway_error_code": None if row.gateway_error_code or row.status != "Failed" else raw.get("error_code"),
		# failures logged without a reason (old portal code) get Razorpay's own description
		"failure_message": raw.get("error_description")
			if row.status == "Failed" and (row.failure_message or "").endswith(NO_REASON_SUFFIX) else None,
	})
	if wrong_account and not account:
		update["payer_account"] = None
	gateway_amount = flt(raw.get("amount")) / 100
	if gateway_amount > 0 and abs(gateway_amount - flt(row.amount)) > 0.01:
		if row.reference_doctype not in LEDGER_DOCTYPES:
			pass  # admission / PACE requests: their amount is what the next checkout charges - never touched here
		elif row.status == "Failed":
			update["amount"] = gateway_amount
		else:
			frappe.log_error(
				f"{row.name}: recorded ₹{flt(row.amount):,.2f}, Razorpay captured ₹{gateway_amount:,.2f} "
				f"for {row.gateway_payment_id}",
				"SLCM Payment Request amount differs from Razorpay",
			)
	if update:
		frappe.db.set_value(DOCTYPE, row.name, update, update_modified=False)
	apply_payer_details(row.name)
	frappe.db.commit()
	return 1 if update else 0


# Fee Payment / Fee Receipt / Fee Demand fields the payer details fill (only when empty: never over an
# accountant's entry). IFSC stays empty: no gateway shares the payer's bank account or IFSC.
PAYER_FIELDS = ("bank_name", "account_number", "transaction_date")


def apply_payer_details(request_name):
	"""Copy the gateway's payer details onto the Fee Payments of this payment, their Fee Receipts and the Fee
	Demands they paid: Bank Name ← payer bank, Account Number ← UPI ID / masked card, Transaction Date ← paid on."""
	pr = frappe.db.get_value(
		DOCTYPE, request_name, ["status", "gateway_payment_id", "payer_bank", "payer_account", "paid_on"], as_dict=True,
	)
	if not pr or pr.status != "Paid" or not pr.gateway_payment_id:
		return
	source = {
		"bank_name": pr.payer_bank,
		"account_number": pr.payer_account,
		"transaction_date": getdate(pr.paid_on) if pr.paid_on else None,
	}
	source = {k: v for k, v in source.items() if v}
	if not source:
		return
	for fp in frappe.get_all(
		"Fee Payment",
		filters={"reference_number": pr.gateway_payment_id, "docstatus": 1, "payment_mode": "Online Payment"},
		fields=["name", "receipt", *PAYER_FIELDS],
	):
		_fill_empty("Fee Payment", fp, source)
		if fp.receipt:
			receipt = frappe.db.get_value("Fee Receipt", fp.receipt, ["name", "status", *PAYER_FIELDS], as_dict=True)
			if receipt and receipt.status != "Cancelled":
				_fill_empty("Fee Receipt", receipt, source)
		for demand in frappe.get_all(
			"Fee Payment Demand Row", filters={"parent": fp.name, "parenttype": "Fee Payment"}, pluck="fee_demand",
		):
			row = frappe.db.get_value(
				"Fee Demand", {"name": demand, "transaction_number": pr.gateway_payment_id}, ["name", *PAYER_FIELDS], as_dict=True,
			)
			if row:
				_fill_empty("Fee Demand", row, source)


def _fill_empty(doctype, row, source):
	"""Fill empty fields only - plus a bare bank code an earlier run wrote (bank name ← the bank's name; an
	account number that is only a bank code is cleared when the gateway reports no account)."""
	update = {
		k: v for k, v in source.items()
		if not row.get(k) or (k in ("bank_name", "account_number") and _is_bank_code(row.get(k)) and row.get(k) != v)
	}
	if _is_bank_code(row.get("account_number")) and "account_number" not in source:
		update["account_number"] = None
	if update:
		frappe.db.set_value(doctype, row.name, update, update_modified=False)


def sync_recent():
	"""Hourly: catch payments recorded by paths that bypass doc events (direct db writes, imports), and fill the
	common gateway fields of recent requests (admissions included)."""
	since = add_days(now_datetime(), -3)
	result = sync_all(since=since)
	fill_common_ids()
	result["student_identity"] = fill_student_identity()
	result["razorpay_details"] = enrich_razorpay_details(since=since)
	return result


def backfill():
	"""One-off: Payment Requests for every historical student payment, and the common gateway fields of every request.
	bench --site <site> execute slcm.slcm.fee.payment_ledger.backfill"""
	result = sync_all()
	fill_common_ids()
	result["student_identity"] = fill_student_identity(limit=100000)
	result["razorpay_details"] = enrich_razorpay_details(limit=5000, recheck=True)
	return result
