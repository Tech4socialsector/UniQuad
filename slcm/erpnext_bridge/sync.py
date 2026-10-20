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

SOURCES = {
	"Fee Payment": {"date_field": "payment_date", "amount_field": "amount"},
	"Fee Refund": {"date_field": "refund_date", "amount_field": "refund_amount"},
	"SLCM Payment Request": {"date_field": "settlement_date", "amount_field": None},
}
ERROR_TITLE = "SLCM ERPNext posting failed: {0} {1}"


def is_enabled():
	return bool(conf.get_posting_company())


# ── doc_events ──────────────────────────────────────────────────────────────────


def enqueue_sync(doc, method=None):
	"""Fee Payment / Fee Refund on_submit and on_cancel. Queues the posting to run after the SLCM transaction
	commits, so the fee flow never waits on - or fails because of - ERPNext."""
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
		fields=["name", "docstatus"],
		order_by="creation desc",
	)


def live_journal_entry(reference_doctype, reference_name):
	for je in get_journal_entries(reference_doctype, reference_name):
		if je.docstatus in (0, 1):
			return je.name
	return None


def settlement_receipt(razorpay_payment_id):
	if not razorpay_payment_id:
		return None
	return frappe.db.get_value(
		"Fee Payment",
		{"reference_number": razorpay_payment_id, "docstatus": 1, "payment_mode": "Online Payment"},
		"name",
	)


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


def _sync(cfg, dt, dn, repost):
	src = frappe.get_doc(dt, dn) if frappe.db.exists(dt, dn) else None
	entries = get_journal_entries(dt, dn)
	live = next((je.name for je in entries if je.docstatus in (0, 1)), None)
	want = bool(src) and _should_post(cfg, src, already_posted=bool(live))

	if want and not live:
		if entries and not repost:
			# Posted before and the Journal Entry was cancelled in ERPNext while SLCM still has the document
			# active: leave the accountant's decision alone; the Reconciliation report flags it.
			return "Cancelled in ERPNext"
		make_journal_entry(cfg, src, build_entry(cfg, src))
		return "Posted"

	if not want and live:
		_cancel_journal_entry(live)
		return "Cancelled"

	return "Posted" if live else None


def _should_post(cfg, src, already_posted=False):
	conf_ = SOURCES[src.doctype]
	posting_date = src.get(conf_["date_field"])
	if not posting_date or not cfg.slcm_posting_from_date:
		return False
	if getdate(posting_date) < getdate(cfg.slcm_posting_from_date):
		return False

	if src.doctype == "Fee Payment":
		return src.docstatus == 1 and flt(src.amount) > 0
	if src.doctype == "Fee Refund":
		return src.docstatus == 1 and flt(src.refund_amount) > 0
	if src.doctype == "SLCM Payment Request":
		if src.docstatus == 2 or src.settlement_status != "Settled":
			return False
		if not cfg.slcm_gateway_charges_account:
			return False
		if already_posted:
			return True
		# Only settle money the bridge itself parked in the clearing account.
		receipt = settlement_receipt(src.razorpay_payment_id)
		return bool(receipt) and bool(live_journal_entry("Fee Payment", receipt))
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
	"""Hourly safety net: posts anything the doc_events missed, retries failures, and catches
	Razorpay settlements (those are written with db updates, so no doc_event fires for them)."""
	cfg = conf.get_config()
	if not cfg or not cfg.slcm_posting_from_date:
		return None
	params = {"from_date": cfg.slcm_posting_from_date, "limit": cint(limit)}
	posted = """exists (select 1 from `tabJournal Entry` je where je.slcm_reference_doctype = %(dt)s
		and je.slcm_reference_name = src.name and je.docstatus < 2)"""
	ever_posted = """exists (select 1 from `tabJournal Entry` je where je.slcm_reference_doctype = %(dt)s
		and je.slcm_reference_name = src.name)"""

	pending = []
	for dt in ("Fee Payment", "Fee Refund"):
		date_field = SOURCES[dt]["date_field"]
		rows = frappe.db.sql(
			f"""
			select src.name from `tab{dt}` src
			where src.{date_field} >= %(from_date)s
				and ((src.docstatus = 1 and not {ever_posted}) or (src.docstatus = 2 and {posted}))
			order by src.{date_field}
			limit %(limit)s
			""",
			{**params, "dt": dt},
			pluck=True,
		)
		pending += [(dt, name) for name in rows]

	rows = frappe.db.sql(
		f"""
		select src.name from `tabSLCM Payment Request` src
		where src.settlement_date >= %(from_date)s
			and (
				(src.docstatus < 2 and src.settlement_status = 'Settled' and not {ever_posted}
					and exists (
						select 1 from `tabFee Payment` fp
						where fp.reference_number = src.razorpay_payment_id
							and fp.docstatus = 1 and fp.payment_mode = 'Online Payment'
					))
				or ((src.docstatus = 2 or ifnull(src.settlement_status, '') != 'Settled') and {posted})
			)
		order by src.settlement_date
		limit %(limit)s
		""",
		{**params, "dt": "SLCM Payment Request"},
		pluck=True,
	)
	pending += [("SLCM Payment Request", name) for name in rows]

	for dt, name in pending:
		sync_document(dt, name)
	return len(pending)
