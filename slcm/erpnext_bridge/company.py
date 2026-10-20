"""The "SLCM Fee Accounting" section on ERPNext's Company form: validation and its buttons."""

import frappe
from frappe import _

from slcm.erpnext_bridge import erpnext_installed
from slcm.erpnext_bridge.config import ACCOUNT_FIELDS

MANAGERS = ("System Manager", "Accounts Manager")


def validate_company(doc, method=None):
	"""Company.validate (doc_event). Only acts when the SLCM section is in use."""
	if not doc.get("slcm_enable_fee_posting"):
		return
	if not doc.get("slcm_posting_from_date"):
		frappe.throw(_("SLCM Fee Accounting: set 'Post SLCM Fees Dated On/After'."))
	other = frappe.db.get_value(
		"Company", {"slcm_enable_fee_posting": 1, "name": ("!=", doc.name)}, "name"
	)
	if other:
		frappe.throw(
			_("SLCM fee posting is already enabled for {0}. SLCM fees can post to one company only.").format(other)
		)
	for fieldname in ACCOUNT_FIELDS:
		if doc.get(fieldname):
			_validate_account(doc, doc.get(fieldname), doc.meta.get_label(fieldname))


def _validate_account(company, account, label):
	acc = frappe.db.get_value("Account", account, ["company", "is_group", "account_type", "disabled"], as_dict=True)
	if not acc:
		frappe.throw(_("{0}: Account {1} does not exist").format(label, account))
	if acc.company != company.name:
		frappe.throw(_("{0}: Account {1} does not belong to Company {2}").format(label, account, company.name))
	if acc.is_group:
		frappe.throw(_("{0}: Account {1} is a group account").format(label, account))
	if acc.disabled:
		frappe.throw(_("{0}: Account {1} is disabled").format(label, account))
	# Receivable / Payable ledgers need a Party on every Journal Entry row; the bridge posts without parties.
	if acc.account_type in ("Receivable", "Payable"):
		frappe.throw(_("{0}: Account {1} is a {2} account. Use a non-party ledger.").format(label, account, acc.account_type))


@frappe.whitelist()
def create_fee_ledgers(company):
	frappe.only_for(MANAGERS)
	if not erpnext_installed():
		frappe.throw(_("ERPNext is not installed on this site."))
	from slcm.erpnext_bridge.setup_accounts import setup_fee_accounting

	setup_fee_accounting(company)
	return _("SLCM fee ledgers, payment modes and bank accounts are set up for {0}. Review them, then tick 'Enable SLCM Fee Posting'.").format(company)


@frappe.whitelist()
def post_pending_now():
	frappe.only_for(MANAGERS)
	frappe.enqueue("slcm.erpnext_bridge.sync.sync_pending", queue="long")
	return _("Queued. Pending SLCM fee documents will be posted in a minute.")


@frappe.whitelist()
def repost(reference_doctype, reference_name):
	"""Re-post one SLCM document whose Journal Entry was cancelled in ERPNext."""
	frappe.only_for(MANAGERS)
	from slcm.erpnext_bridge.sync import last_error, sync_document

	status = sync_document(reference_doctype, reference_name, repost=True)
	if status == "Failed":
		frappe.throw(last_error(reference_doctype, reference_name) or _("Posting failed; see Error Log."))
	return status
