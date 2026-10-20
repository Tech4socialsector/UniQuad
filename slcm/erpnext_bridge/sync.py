"""One-way, idempotent sync of SLCM fee transactions into ERPNext Journal Entries.

There is no log table: the Journal Entry itself records which SLCM document it was posted for
(slcm_reference_doctype / slcm_reference_name). Syncing compares the SLCM document's current state with its live
Journal Entry and posts, cancels, or does nothing - so it is safe to run any number of times, from doc_events, the
hourly sweeper or by hand. A MariaDB named lock stops two workers posting the same document twice.

Nothing here writes to SLCM documents, and every entry point swallows its own errors: a failure goes to Frappe's
Error Log (once per document per day) and is retried by the hourly sweeper, never raised into the fee flow.
"""

import hashlib

import frappe
from frappe.utils import add_to_date, cint, flt, getdate

from slcm.erpnext_bridge import config as conf
from slcm.erpnext_bridge.builders import build_entry, make_journal_entry

FLE_PAID = ("Authorized", "Captured")
# One FLE payment can log several callbacks (Authorized, then Captured): only the first paid log of a payment posts.
FLE_FIRST_PAID_LOG = """src.payment_status in ('Authorized', 'Captured') and src.paid_amount > 0
	and not exists (select 1 from `tabFLE Payment Log` o where o.reference_no = src.reference_no
		and ifnull(o.transaction_id, '') = ifnull(src.transaction_id, '')
		and o.payment_status in ('Authorized', 'Captured') and o.paid_amount > 0 and o.creation < src.creation)"""

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
	return None, None


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
	if key == "SLCM Payment Request":
		if src.docstatus == 2 or src.settlement_status != "Settled":
			return False
		if not cfg.slcm_gateway_charges_account:
			return False
		if already_posted:
			return True
		# Only settle money the bridge itself parked in the clearing account.
		receipt_dt, receipt = settlement_receipt(src)
		return bool(receipt) and bool(live_journal_entry(receipt_dt, receipt))
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
	params = {"from_date": cfg.slcm_posting_from_date, "limit": cint(limit)}

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
	return frappe.db.sql(
		f"""
		select src.name from `tab{table_of(key)}` src
		where {source["date"]} >= %(from_date)s
			and (({active} and not {ever_posted}) or (not {active} and {posted}))
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
