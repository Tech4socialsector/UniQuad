"""One-way, idempotent sync of SLCM fee transactions into ERPNext Journal Entries.

There is no log table: the Journal Entry itself records which SLCM document it was posted for
(slcm_reference_doctype / slcm_reference_name). Syncing compares the SLCM document's current state with its live
Journal Entry and posts, cancels, or does nothing - so it is safe to run any number of times, from doc_events, the
hourly sweeper or by hand. A MariaDB named lock stops two workers posting the same document twice.

Nothing here writes to SLCM documents, and every entry point swallows its own errors: a failure goes to Frappe's
Error Log (once per document per day) and is retried by the hourly sweeper, never raised into the fee flow.
"""

import hashlib
import json

import frappe
from frappe.utils import add_to_date, cint, flt, getdate

from slcm.erpnext_bridge import config as conf
from slcm.erpnext_bridge.builders import build_entry, make_journal_entry
from slcm.slcm.fee.payment_ledger import LEDGER_DOCTYPES

FLE_PAID = ("Authorized", "Captured")
# One FLE payment can log several callbacks (Authorized, then Captured): only the first paid log of a payment posts.
FLE_FIRST_PAID_LOG = """src.payment_status in ('Authorized', 'Captured') and src.paid_amount > 0
	and not exists (select 1 from `tabFLE Payment Log` o where o.reference_no = src.reference_no
		and ifnull(o.transaction_id, '') = ifnull(src.transaction_id, '')
		and o.payment_status in ('Authorized', 'Captured') and o.paid_amount > 0 and o.creation < src.creation)"""
COUNTER_PAID = """src.payment_status = 'Paid' and src.amount > 0
	and ifnull(src.razorpay_payment_id, '') = '' and ifnull(src.payment_gateway, '') = ''"""

# Every SLCM source the bridge posts, keyed by the name stored on the Journal Entry (slcm_reference_doctype).
#   table        the DocType holding it, when the key is not a DocType itself
#   date_field   the posting date (Python side); date / active: the same as SQL on `src`, for the hourly sweeper
#   stage        sweeper order: receipts (1) before what clears them (2), and excess adjustments (3) last
SOURCES = {
	# money in
	"Fee Payment": {"date_field": "payment_date", "date": "src.payment_date", "active": "src.docstatus = 1 and src.amount > 0", "stage": 1},
	"Applicant Payment Receipt": {
		"date_field": "payment_date", "date": "src.payment_date", "active": "src.docstatus < 2 and src.net_amount > 0", "stage": 1,
	},
	"PACE Receipt": {"date_field": "payment_date", "date": "src.payment_date", "active": "src.docstatus < 2 and src.amount > 0", "stage": 1},
	"FLE Payment Log": {"date_field": "transaction_date", "date": "date(src.transaction_date)", "active": FLE_FIRST_PAID_LOG, "stage": 1},
	# money out
	"Fee Refund": {"date_field": "refund_date", "date": "src.refund_date", "active": "src.docstatus = 1 and src.refund_amount > 0", "stage": 1},
	"Refund Transaction": {
		"date_field": "processed_at", "date": "date(src.processed_at)",
		"active": "src.status = 'Processed' and src.refund_amount > 0", "stage": 1,
	},
	"Stipend Payment": {"date_field": "payment_date", "date": "src.payment_date", "active": "src.docstatus = 1 and src.amount > 0", "stage": 1},
	# exam fees paid at the counter (no gateway); online ones are booked on their Payment Request (Gateway Receipt)
	"Re Exam Payment Log": {"date_field": "transaction_date", "date": "date(src.transaction_date)", "active": COUNTER_PAID, "stage": 1},
	"Improvement Exam Payment Log": {
		"date_field": "transaction_date", "date": "date(src.transaction_date)", "active": COUNTER_PAID, "stage": 1,
	},
	# hostel and mess office: not submittable, so an edited amount is rebooked ("amount")
	"Mess Payment": {
		"date_field": "payment_date", "date": "src.payment_date", "active": "src.amount > 0", "amount": "src.amount", "stage": 1,
	},
	"Hostel Refund Request": {
		"date_field": "processed_on", "date": "src.processed_on",
		"active": "src.status = 'Processed' and src.amount > 0", "amount": "src.amount", "stage": 1,
	},
	# Razorpay settlements: posted once the receipt they clear is posted
	"SLCM Payment Request": {
		"date_field": "settlement_date", "date": "date(src.settlement_date)",
		"active": "src.docstatus < 2 and src.settlement_status = 'Settled'", "stage": 2,
	},
	"FLE Settlement": {
		"table": "FLE Payment Log", "date_field": "settlement_date", "date": "src.settlement_date",
		"active": "src.settlement_status = 'processed'", "stage": 2,
	},
	# student excess: paid fees moved off a due, or money received and recorded on the note; then applied to a due
	"Student Credit Note": {
		"date_field": None, "date": "coalesce(src.received_date, date(src.creation))",
		"active": """src.docstatus = 1 and src.credit_amount > 0 and (ifnull(src.source_fee_demand, '') != ''
			or src.remarks like 'Moved from due %%' or ifnull(src.received_via, '') != '')""",
		"stage": 2,
	},
	"Credit Adjustment Row": {
		"date_field": "adjusted_on", "date": "src.adjusted_on",
		"active": """src.parenttype = 'Student Credit Note' and ifnull(src.fee_demand, '') != '' and src.amount_adjusted > 0
			and exists (select 1 from `tabStudent Credit Note` note where note.name = src.parent and note.docstatus = 1)
			and exists (select 1 from `tabJournal Entry` nje where nje.slcm_reference_doctype = 'Student Credit Note'
				and nje.slcm_reference_name = src.parent and nje.docstatus < 2)""",
		"stage": 3,
	},
}
# A student's online payment (the SLCM Payment Request the payment ledger keeps per gateway payment) that no
# Fee Payment books: re-exam, improvement exam and transcript fees, and money captured but not applied. What is
# left of the capture after the Fee Payments and the excess entered by hand for the same payment id.
GATEWAY_RECEIPT_AMOUNT = """src.amount
	- coalesce((select sum(fp.amount) from `tabFee Payment` fp where fp.reference_number = src.transaction_id
		and fp.docstatus = 1 and fp.payment_mode = 'Online Payment'), 0)
	- coalesce((select sum(cn.credit_amount) from `tabStudent Credit Note` cn
		where cn.received_reference = src.transaction_id and cn.docstatus = 1
		and ifnull(cn.received_via, '') != '' and ifnull(cn.source_fee_demand, '') = ''), 0)"""
# A refunded payment keeps its Gateway Receipt: a refunded exam / transcript fee is no longer held by its record, so
# the receipt is rebooked from the fee ledger to Unallocated Fee Receipts, and the Gateway Refund below releases it.
GATEWAY_RECEIPT_ACTIVE = f"""src.docstatus = 1 and src.status = 'Paid' and ifnull(src.transaction_id, '') != ''
	and src.reference_doctype in ({", ".join(f"'{dt}'" for dt in LEDGER_DOCTYPES)})
	and ({GATEWAY_RECEIPT_AMOUNT}) > 0.005"""
SOURCES["Gateway Receipt"] = {
	"table": "SLCM Payment Request", "date_field": "paid_on", "date": "date(src.paid_on)",
	"active": GATEWAY_RECEIPT_ACTIVE, "amount": GATEWAY_RECEIPT_AMOUNT, "stage": 1,
}

# Refunds (SLCM records them; they are paid out from the gateway dashboard, never by SLCM).
# What a payment's records still hold of it (re-exam / improvement / transcript fees not cancelled or refunded):
GATEWAY_HELD_AMOUNT = """coalesce((select sum(l.amount) from `tabRe Exam Payment Log` l
		join `tabRe Exam Registration` r on r.name = l.re_exam_registration
		where l.razorpay_payment_id = src.transaction_id and l.payment_status = 'Paid' and r.status != 'Cancelled'), 0)
	+ coalesce((select sum(l.amount) from `tabImprovement Exam Payment Log` l
		join `tabImprovement Exam Registration` r on r.name = l.improvement_exam_registration
		where l.razorpay_payment_id = src.transaction_id and l.payment_status = 'Paid' and r.status != 'Cancelled'), 0)
	+ coalesce((select sum(t.fee_amount) from `tabTranscript Request` t
		where t.payment_reference = src.transaction_id and t.payment_status = 'Paid'), 0)"""
# ...so the money its Gateway Receipt parked in Unallocated Fee Receipts (applied to nothing):
GATEWAY_UNAPPLIED_AMOUNT = f"greatest(({GATEWAY_RECEIPT_AMOUNT}) - ({GATEWAY_HELD_AMOUNT}), 0)"
# Gateway Refund: the recorded refunds, up to that unapplied money. A refund of a fee that WAS applied to a due is
# booked by its Fee Refund (Refund Mode: Payment Gateway) instead, so it is never counted twice.
GATEWAY_REFUND_AMOUNT = f"least(coalesce(src.refunded_amount, 0), {GATEWAY_UNAPPLIED_AMOUNT})"
SOURCES["Gateway Refund"] = {
	"table": "SLCM Payment Request", "date_field": "refunded_on", "date": "src.refunded_on",
	"active": f"""src.docstatus = 1 and src.status = 'Paid' and ifnull(src.transaction_id, '') != ''
		and src.reference_doctype in ({", ".join(f"'{dt}'" for dt in LEDGER_DOCTYPES)})
		and ({GATEWAY_REFUND_AMOUNT}) > 0.005""",
	"amount": GATEWAY_REFUND_AMOUNT, "stage": 2,
}
# Gateway Refund Payout: the refunds a payout deducted (the bank received that much less): Dr Clearing / Cr Bank.
SOURCES["Gateway Refund Payout"] = {
	"table": "SLCM Payment Request", "date_field": "refund_settled_on", "date": "src.refund_settled_on",
	"active": f"""src.docstatus = 1 and src.reference_doctype in ({", ".join(f"'{dt}'" for dt in LEDGER_DOCTYPES)})
		and coalesce(src.refund_settled_amount, 0) > 0.005""",
	"amount": "coalesce(src.refund_settled_amount, 0)", "stage": 2,
}
ERROR_TITLE = "SLCM ERPNext posting failed: {0} {1}"


def table_of(key):
	return SOURCES[key].get("table", key)


def is_enabled():
	return bool(conf.get_posting_company())


# ── doc_events ──────────────────────────────────────────────────────────────────


def enqueue_sync(doc, method=None):
	"""doc_events of every SLCM source. Queues the posting to run after the SLCM transaction commits, so the fee
	flow never waits on - or fails because of - ERPNext."""
	try:
		if not is_enabled():
			return
		reference_doctype, reference_name = doc.doctype, doc.name
		# Not enqueue_after_commit=True: frappe runs after-commit callbacks unguarded, so a Redis outage would
		# surface as an error on an already-saved payment and skip SLCM's own callbacks.
		frappe.db.after_commit.add(lambda: _enqueue_quietly(reference_doctype, reference_name))
	except Exception:
		pass


def _enqueue_quietly(reference_doctype, reference_name):
	try:
		frappe.enqueue(
			"slcm.erpnext_bridge.sync.sync_document",
			queue="short",
			reference_doctype=reference_doctype,
			reference_name=reference_name,
		)
	except Exception:
		# The hourly sweeper picks the document up anyway.
		pass


# ── state ───────────────────────────────────────────────────────────────────────


def get_journal_entries(reference_doctype, reference_name):
	return frappe.get_all(
		"Journal Entry",
		filters={"slcm_reference_doctype": reference_doctype, "slcm_reference_name": reference_name},
		fields=["name", "docstatus", "creation"],
		order_by="creation desc",
	)


def live_journal_entry(reference_doctype, reference_name):
	for je in get_journal_entries(reference_doctype, reference_name):
		if je.docstatus in (0, 1):
			return je.name
	return None


def settlement_receipt(pr):
	"""(doctype, name) of the receipt a Razorpay payment request's money was booked on, or (None, None):
	a Fee Payment (students), Applicant Payment Receipt (admission) or PACE Receipt."""
	ids = [i for i in (pr.get("razorpay_payment_id"), pr.get("transaction_id")) if i]
	if ids:
		name = frappe.db.get_value(
			"Fee Payment", {"reference_number": ("in", ids), "docstatus": 1, "payment_mode": "Online Payment"}, "name"
		)
		if name:
			return "Fee Payment", name
	for dt, link in (("Applicant Payment Receipt", "payment_reference"), ("PACE Receipt", "payment_request")):
		name = frappe.db.get_value(dt, {link: pr.name, "docstatus": ("<", 2)}, "name")
		if not name and ids:
			name = frappe.db.get_value(dt, {"transaction_id": ("in", ids), "docstatus": ("<", 2)}, "name")
		if name:
			return dt, name
	# re-exam / transcript / unapplied money: booked on the request itself
	if pr.get("name") and live_journal_entry("Gateway Receipt", pr.name):
		return "Gateway Receipt", pr.name
	return None, None


def is_counter_payment(log):
	"""An exam fee paid at the counter: Paid, with no gateway and no gateway payment id (see COUNTER_PAID)."""
	return (
		log.payment_status == "Paid" and flt(log.amount) > 0
		and not log.get("razorpay_payment_id") and not log.get("payment_gateway")
	)


def gateway_receipt_amount(pr):
	"""What a student's online payment brought in beyond its Fee Payments (see GATEWAY_RECEIPT_AMOUNT)."""
	value = frappe.db.sql(
		f"select {GATEWAY_RECEIPT_AMOUNT} from `tabSLCM Payment Request` src where src.name = %s", pr.name
	)
	return flt(value[0][0], 2) if value else 0.0


def gateway_refund_amount(pr):
	"""What a Gateway Refund books for a request (see GATEWAY_REFUND_AMOUNT)."""
	value = frappe.db.sql(f"select {GATEWAY_REFUND_AMOUNT} from `tabSLCM Payment Request` src where src.name = %s", pr.name)
	return flt(value[0][0], 2) if value else 0.0


def gateway_unapplied_amount(pr):
	value = frappe.db.sql(f"select {GATEWAY_UNAPPLIED_AMOUNT} from `tabSLCM Payment Request` src where src.name = %s", pr.name)
	return flt(value[0][0], 2) if value else 0.0


def gateway_student(pr):
	"""The student the payment ledger recorded on a request."""
	try:
		data = json.loads(pr.get("gateway_response") or "{}")
	except ValueError:
		return None
	return data.get("student") if isinstance(data, dict) else None


def fle_first_paid_log(log):
	"""The FLE Payment Log that books this payment's receipt (the first paid log of the same payment)."""
	rows = frappe.get_all(
		"FLE Payment Log",
		filters={
			"reference_no": log.reference_no,
			"transaction_id": log.transaction_id or ("is", "not set"),
			"payment_status": ("in", FLE_PAID),
			"paid_amount": (">", 0),
		},
		pluck="name",
		order_by="creation asc",
		limit=1,
	)
	return rows[0] if rows else None


# ── sync ────────────────────────────────────────────────────────────────────────


def sync_document(reference_doctype, reference_name, repost=False):
	"""Bring one SLCM document's ERPNext posting in line with its current state. Commits its own work.

	Returns "Posted", "Cancelled", "Cancelled in ERPNext", "Failed" or None (nothing to post).
	A Journal Entry cancelled by hand in ERPNext is not re-posted unless repost=True.
	"""
	if reference_doctype not in SOURCES:
		return None
	cfg = conf.get_config()
	if not cfg:
		return None
	lock = _lock_name(reference_doctype, reference_name)
	if not cint(frappe.db.sql("select get_lock(%s, 30)", lock)[0][0]):
		return None  # another worker is on it
	try:
		# Start a fresh transaction after taking the lock: under REPEATABLE READ an older snapshot would not see
		# a Journal Entry another worker committed while we waited, and we would post it twice.
		frappe.db.commit()
		status = _sync(cfg, reference_doctype, reference_name, repost)
		frappe.db.commit()
		return status
	except Exception:
		frappe.db.rollback()
		_log_failure(reference_doctype, reference_name)
		frappe.db.commit()
		return "Failed"
	finally:
		frappe.db.sql("select release_lock(%s)", lock)


def _sync(cfg, key, dn, repost):
	table = table_of(key)
	src = frappe.get_doc(table, dn) if frappe.db.exists(table, dn) else None
	entries = get_journal_entries(key, dn)
	if src and src.get("creation"):
		# Deleting the latest record of a naming series winds the series back, so a new record can reuse the name.
		# Entries older than the record belong to its namesake: retire them and ignore them.
		for je in entries:
			if je.creation < src.creation and je.docstatus in (0, 1):
				_cancel_journal_entry(je.name)
		entries = [je for je in entries if je.creation >= src.creation]
	live = next((je.name for je in entries if je.docstatus in (0, 1)), None)
	want = bool(src) and _should_post(cfg, key, src, already_posted=bool(live))

	if want and live and SOURCES[key].get("amount") and _entry_changed(cfg, key, src, live):
		# The money behind it moved (a Fee Payment took part of it, a record was refunded or attached): rebook.
		_cancel_journal_entry(live)
		make_journal_entry(cfg, src, build_entry(cfg, src, key), key)
		return "Posted"

	if want and not live:
		if entries and not repost:
			# Posted before and the Journal Entry was cancelled in ERPNext while SLCM still has the document
			# active: leave the accountant's decision alone; the Reconciliation report flags it.
			return "Cancelled in ERPNext"
		make_journal_entry(cfg, src, build_entry(cfg, src, key), key)
		return "Posted"

	if not want and live:
		_cancel_journal_entry(live)
		return "Cancelled"

	return "Posted" if live else None


def _entry_changed(cfg, key, src, journal_entry):
	"""True when the live Journal Entry no longer books what the source would post now (per account, net)."""
	want = {}
	for account, debit, credit in build_entry(cfg, src, key)["lines"]:
		want[account] = flt(want.get(account, 0) + flt(debit) - flt(credit), 2)
	have = {}
	for row in frappe.get_all(
		"Journal Entry Account", filters={"parent": journal_entry}, fields=["account", "debit", "credit"]
	):
		have[row.account] = flt(have.get(row.account, 0) + flt(row.debit) - flt(row.credit), 2)
	return {a: v for a, v in want.items() if v} != {a: v for a, v in have.items() if v}


def posting_date(key, src):
	if key == "Student Credit Note":
		return conf.credit_note_date(src)
	return src.get(SOURCES[key]["date_field"])


def _should_post(cfg, key, src, already_posted=False):
	date = posting_date(key, src)
	if not date or not cfg.slcm_posting_from_date:
		return False
	if getdate(date) < getdate(cfg.slcm_posting_from_date):
		return False

	if key in ("Fee Payment", "Stipend Payment"):
		return src.docstatus == 1 and flt(src.amount) > 0
	if key == "Fee Refund":
		return src.docstatus == 1 and flt(src.refund_amount) > 0
	if key == "Applicant Payment Receipt":
		return src.docstatus < 2 and flt(src.net_amount) > 0
	if key == "PACE Receipt":
		return src.docstatus < 2 and flt(src.amount) > 0
	if key == "FLE Payment Log":
		return src.payment_status in FLE_PAID and flt(src.paid_amount) > 0 and fle_first_paid_log(src) == src.name
	if key == "Refund Transaction":
		return src.status == "Processed" and flt(src.refund_amount) > 0
	if key in ("Re Exam Payment Log", "Improvement Exam Payment Log"):
		return is_counter_payment(src)
	if key == "Mess Payment":
		return flt(src.amount) > 0
	if key == "Hostel Refund Request":
		return src.status == "Processed" and flt(src.amount) > 0
	if key == "Gateway Receipt":
		return (
			src.docstatus == 1 and src.status == "Paid" and bool(src.transaction_id)
			and src.reference_doctype in LEDGER_DOCTYPES and gateway_receipt_amount(src) > 0.005
		)
	if key == "Gateway Refund":
		return (
			src.docstatus == 1 and src.status == "Paid" and bool(src.transaction_id)
			and src.reference_doctype in LEDGER_DOCTYPES and gateway_refund_amount(src) > 0.005
		)
	if key == "Gateway Refund Payout":
		return src.docstatus == 1 and src.reference_doctype in LEDGER_DOCTYPES and flt(src.refund_settled_amount) > 0.005
	if key == "SLCM Payment Request":
		if src.docstatus == 2 or src.settlement_status != "Settled":
			return False
		if not cfg.slcm_gateway_charges_account:
			return False
		if already_posted:
			return True
		# Only settle money the bridge itself parked in the clearing account.
		receipt_dt, receipt = settlement_receipt(src)
		if not (receipt and live_journal_entry(receipt_dt, receipt)):
			return False
		return receipt_dt not in ("Fee Payment", "Gateway Receipt") or _student_settlement_matches(src)
	if key == "FLE Settlement":
		if src.settlement_status != "processed" or not cfg.slcm_gateway_charges_account:
			return False
		if already_posted:
			return True
		receipt = fle_first_paid_log(src)
		return bool(receipt) and bool(live_journal_entry("FLE Payment Log", receipt))
	if key == "Student Credit Note":
		return src.docstatus == 1 and flt(src.credit_amount) > 0 and conf.credit_note_holds_money(src)
	if key == "Credit Adjustment Row":
		# Only adjustments to a due (refunds from excess also write rows here, without a due; Fee Refund posts those).
		if src.parenttype != "Student Credit Note" or not src.fee_demand or flt(src.amount_adjusted) <= 0:
			return False
		if frappe.db.get_value("Student Credit Note", src.parent, "docstatus") != 1:
			return False
		# Only release money the bridge itself put into Unallocated Fee Receipts.
		return bool(live_journal_entry("Student Credit Note", src.parent))
	return False


def _student_settlement_matches(pr):
	"""A student payment's settlement clears the gateway's full capture: only post it once everything that capture
	brought in is parked in the clearing account - its Fee Payments, excess entered by hand for it and its own
	Gateway Receipt (re-exam / transcript / unapplied money). Until then it waits (flagged once a day)."""
	ids = [i for i in (pr.get("razorpay_payment_id"), pr.get("transaction_id")) if i]
	booked = flt(frappe.db.sql(
		"""select sum(amount) from `tabFee Payment`
		where reference_number in %(ids)s and docstatus = 1 and payment_mode = 'Online Payment'""",
		{"ids": ids or [""]},
	)[0][0])
	booked += flt(frappe.db.sql(
		"""select sum(credit_amount) from `tabStudent Credit Note` where received_reference in %(ids)s
		and docstatus = 1 and ifnull(received_via, '') != '' and ifnull(source_fee_demand, '') = ''""",
		{"ids": ids or [""]},
	)[0][0])
	receipt = live_journal_entry("Gateway Receipt", pr.name)
	if receipt:
		booked += flt(frappe.db.get_value("Journal Entry", receipt, "total_debit"))
	if abs(booked - flt(pr.amount)) <= 0.01:
		return True
	flag = f"slcm_erp_settlement_mismatch:{pr.name}"
	if not frappe.cache().get_value(flag):
		frappe.cache().set_value(flag, 1, expires_in_sec=86400)
		frappe.log_error(
			f"{pr.name}: payment ₹{flt(pr.amount):,.2f}, booked in ERPNext ₹{booked:,.2f} (Fee Payments and the "
			"request's Gateway Receipt). The settlement waits: check the receipts on the SLCM ERPNext Reconciliation "
			"report; it posts on the next hourly sync once they add up.",
			"SLCM ERPNext settlement needs manual posting",
		)
	return False


def _cancel_journal_entry(journal_entry):
	try:
		je = frappe.get_doc("Journal Entry", journal_entry)
	except frappe.DoesNotExistError:
		frappe.clear_last_message()
		return  # deleted meanwhile (e.g. by hand) - nothing left to cancel
	je.flags.ignore_permissions = True
	if je.docstatus == 1:
		je.cancel()
	elif je.docstatus == 0:
		je.delete()


def _lock_name(dt, dn):
	# MariaDB lock names are limited to 64 characters.
	return "slcm_erp_" + hashlib.md5(f"{dt}|{dn}".encode()).hexdigest()


def _log_failure(dt, dn):
	try:
		title = ERROR_TITLE.format(dt, dn)
		recent = frappe.db.exists(
			"Error Log", {"method": title, "creation": (">", add_to_date(None, hours=-24))}
		)
		if not recent:
			frappe.log_error(title=title)
	except Exception:
		pass


def last_error(dt, dn):
	error = frappe.db.get_value(
		"Error Log", {"method": ERROR_TITLE.format(dt, dn)}, "error", order_by="creation desc"
	)
	lines = [line for line in (error or "").strip().splitlines() if line.strip()]
	return lines[-1][:200] if lines else None


# ── sweeper ─────────────────────────────────────────────────────────────────────


def sync_pending(limit=500):
	"""Hourly safety net: posts anything the doc_events missed, retries failures, reverses what is no longer
	active, and catches Razorpay settlements (those are written with db updates, so no doc_event fires for them).
	Runs in stages so a settlement or adjustment finds its receipt posted in the same run."""
	cfg = conf.get_config()
	if not cfg or not cfg.slcm_posting_from_date:
		return None
	params = {"from_date": cfg.slcm_posting_from_date, "limit": cint(limit), "recent": add_to_date(None, days=-1)}

	total = 0
	for stage in (1, 2, 3):
		pending = []
		for key, source in SOURCES.items():
			if source["stage"] == stage:
				pending += [(key, name) for name in _pending(key, source, params)]
		if stage == 1:
			pending += _orphans(params)
		for key, name in pending:
			sync_document(key, name)
		total += len(pending)
	return total


def _pending(key, source, params):
	"""Active and never posted, or no longer active but still posted."""
	posted = """exists (select 1 from `tabJournal Entry` je where je.slcm_reference_doctype = %(dt)s
		and je.slcm_reference_name = src.name and je.docstatus < 2)"""
	ever_posted = """exists (select 1 from `tabJournal Entry` je where je.slcm_reference_doctype = %(dt)s
		and je.slcm_reference_name = src.name)"""
	active = f"coalesce(({source['active']}), 0)"
	changed = "0"
	if source.get("amount"):
		# Posted, but the amount behind it moved, or the record changed lately (e.g. a capture attached to a
		# re-exam): sync_document compares and rebooks only what really differs.
		latest = """(select {0} from `tabJournal Entry` je where je.slcm_reference_doctype = %(dt)s
			and je.slcm_reference_name = src.name and je.docstatus < 2 order by je.creation desc limit 1)"""
		changed = f"""(abs({latest.format("je.total_debit")} - ({source["amount"]})) > 0.005
			or (src.modified >= %(recent)s and src.modified > {latest.format("je.creation")}))"""
	return frappe.db.sql(
		f"""
		select src.name from `tab{table_of(key)}` src
		where {source["date"]} >= %(from_date)s
			and (({active} and not {ever_posted}) or (not {active} and {posted}) or ({active} and {posted} and {changed}))
		order by {source["date"]}
		limit %(limit)s
		""",
		{**params, "dt": key},
		pluck=True,
	)


def _orphans(params):
	"""Live entries whose SLCM source was deleted (e.g. an adjustment row or receipt removed): cancel them."""
	out = []
	for key in SOURCES:
		rows = frappe.db.sql(
			f"""
			select distinct je.slcm_reference_name from `tabJournal Entry` je
			left join `tab{table_of(key)}` src on src.name = je.slcm_reference_name
			where je.slcm_reference_doctype = %(dt)s and je.docstatus < 2 and src.name is null
			limit %(limit)s
			""",
			{**params, "dt": key},
			pluck=True,
		)
		out += [(key, name) for name in rows]
	return out
