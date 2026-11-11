"""'Create SLCM Fee Ledgers' on the Company form. Idempotent: existing records are reused, never overwritten.

Creates, in ERPNext only:
- one ledger per distinct Fee Component "Ledger" (income; deposits as liabilities), plus the few bridge ledgers;
- Mode of Payment rows for SLCM's payment / refund modes, each with this company's account;
- a Bank + company Bank Account for every SLCM "University Bank Account", matched later by account number;
- empty values in the Company's "SLCM Fee Accounting" section (and its default bank, if blank).
"""

import re

import frappe
from frappe.utils import getdate, today

from slcm.erpnext_bridge.config import EXAM_FEE_NAMES, component_ledger_name

DEPOSIT_TYPES = ("Student Refundable Deposit",)
ONLINE_MODES = ("Online Payment", "Online")


def setup_fee_accounting(company):
	"""Returns what was created: {"Account": [...], "Mode of Payment": [...], "Bank Account": [...],
	"mapped_chart": bool} - for the button's message."""
	frappe.flags.slcm_created = created = {"Account": [], "Mode of Payment": [], "Bank Account": []}
	cdoc = frappe.get_cached_doc("Company", company)
	liabilities = _group(company, "Current Liabilities", "Liability")

	# A chart that maps SLCM names onto its own accounts (Account "SLCM Fee Components", e.g. NLSIU's) gets no
	# per-component ledgers: an account named like a Ledger would take precedence over that mapping.
	mapped_chart = bool(_uses_fee_component_mapping(company))
	if not mapped_chart:
		fee_income = _account(
			company, "SLCM Fee Income", "Income", _group(company, "Direct Income", "Income"), is_group=1
		)
		for comp in frappe.get_all("Fee Component", fields=["name", "component_type"], order_by="name"):
			name = component_ledger_name(comp.name)
			if comp.component_type in DEPOSIT_TYPES or "deposit" in comp.name.lower():
				_account(company, name, "Liability", liabilities)
			else:
				_account(company, name, "Income", fee_income)
		# PACE and FLE income, matched by these names (see builders).
		for fee_type in _options("PACE Receipt", "fee_type"):
			_account(company, f"PACE {fee_type}", "Income", fee_income)
		_account(company, "FLE Course Fee", "Income", fee_income)
		# Re-exam, improvement exam and transcript fees (no Fee Component), matched by these names.
		for name in EXAM_FEE_NAMES.values():
			_account(company, name, "Income", fee_income)

	banks_group = _group(company, "Bank Accounts", "Asset")
	bank_ledgers = [_bank_account(company, label, banks_group) for label in _university_bank_accounts()]
	default_bank = cdoc.default_bank_account or (bank_ledgers[0] if bank_ledgers else None) or _account(
		company, "SLCM Fee Collection Bank", "Asset", banks_group, account_type="Bank"
	)
	default_cash = cdoc.default_cash_account or _account(
		company, "Cash", "Asset", _group(company, "Cash In Hand", "Asset"), account_type="Cash"
	)
	clearing = _account(company, "Payment Gateway Clearing", "Asset", _group(company, "Current Assets", "Asset"))
	for mode in _slcm_modes():
		if mode == "Cash":
			_mode_of_payment(company, mode, "Cash", default_cash)
		elif mode in ONLINE_MODES:
			_mode_of_payment(company, mode, "General", clearing)
		else:
			_mode_of_payment(company, mode, "Bank", default_bank)

	def expenses():
		return _group(company, "Indirect Expenses", "Expense")

	# Ledgers are made only for settings still blank (lambdas), so a configured company gains no unused accounts.
	defaults = {
		"slcm_submit_journal_entries": 1,
		"slcm_posting_from_date": lambda: _fiscal_year_start(company),
		"slcm_default_fee_income_account": lambda: _account(
			company,
			"Other Fee Income",
			"Income",
			_account(company, "SLCM Fee Income", "Income", _group(company, "Direct Income", "Income"), is_group=1),
		),
		# Money held for students (advances, excess) until applied to a due or refunded: a liability, not income.
		"slcm_unallocated_fee_account": lambda: _account(company, "Unallocated Fee Receipts", "Liability", liabilities),
		"slcm_output_gst_account": lambda: _account(
			company, "Output GST on Fees", "Liability", _group(company, "Duties and Taxes", "Liability"), account_type="Tax"
		),
		"slcm_fee_refund_account": lambda: _account(company, "Fee Refunds", "Expense", expenses()),
		"slcm_gateway_charges_account": lambda: _account(company, "Payment Gateway Charges", "Expense", expenses()),
		"slcm_gateway_gst_account": lambda: _account(
			company, "Input GST on Gateway Charges", "Asset", _group(company, "Tax Assets", "Asset"), account_type="Tax"
		),
		"slcm_stipend_account": lambda: _account(company, "Student Stipends", "Expense", expenses()),
		"default_bank_account": default_bank,
		"default_cash_account": default_cash,
	}
	current = frappe.db.get_value("Company", company, list(defaults), as_dict=True)
	# Only fill blanks: never overwrite what an accountant already chose. db_set avoids re-running Company's
	# heavy on_update (it would recreate default records).
	updates = {}
	for fieldname, value in defaults.items():
		if not current.get(fieldname):
			value = value() if callable(value) else value
			if value:
				updates[fieldname] = value
	if updates:
		frappe.db.set_value("Company", company, updates)
	frappe.clear_document_cache("Company", company)
	frappe.flags.slcm_created = None
	return {**created, "mapped_chart": mapped_chart, "settings": list(updates)}


def _created(doctype, name):
	if frappe.flags.slcm_created is not None and name not in frappe.flags.slcm_created[doctype]:
		frappe.flags.slcm_created[doctype].append(name)


# ── helpers ─────────────────────────────────────────────────────────────────────


def _slcm_modes():
	modes = []
	for doctype, fieldname in (
		("Fee Payment", "payment_mode"),
		("Fee Refund", "refund_mode"),
		("Applicant Payment Receipt", "payment_mode"),
		("Stipend Payment", "payment_mode"),
		("Mess Payment", "mode_of_payment"),
		("Hostel Refund Request", "refund_mode"),
		("Student Credit Note", "received_via"),
	):
		for option in _options(doctype, fieldname):
			if option not in modes:
				modes.append(option)
	return modes


def _options(doctype, fieldname):
	field = frappe.get_meta(doctype).get_field(fieldname)
	return [o.strip() for o in ((field.options or "") if field else "").split("\n") if o.strip()]


def _university_bank_accounts():
	field = frappe.get_meta("Fee Payment").get_field("university_bank_account")
	return [o.strip() for o in ((field.options or "") if field else "").split("\n") if o.strip()]


def _mode_of_payment(company, mode, mode_type, account):
	if frappe.db.exists("Mode of Payment", mode):
		doc = frappe.get_doc("Mode of Payment", mode)
	else:
		doc = frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": mode, "type": mode_type, "enabled": 1})
	if any(row.company == company for row in doc.accounts):
		if doc.is_new():
			doc.insert(ignore_permissions=True)
		return
	doc.append("accounts", {"company": company, "default_account": account})
	doc.flags.ignore_permissions = True
	doc.save()
	_created("Mode of Payment", doc.name)


def _bank_account(company, label, banks_group):
	"""ERPNext Bank + company Bank Account for an SLCM label like 'HDFC Bank General 50100508244465'."""
	numbers = re.findall(r"\d{6,}", label)
	ledger_name = re.sub(r"\s*\d{6,}\s*$", "", label).strip() or label
	ledger = _account(company, label, "Asset", banks_group, account_type="Bank")
	if not numbers:
		return ledger
	number = numbers[-1]
	if frappe.db.exists("Bank Account", {"bank_account_no": number, "company": company, "is_company_account": 1}):
		return frappe.db.get_value(
			"Bank Account", {"bank_account_no": number, "company": company, "is_company_account": 1}, "account"
		) or ledger
	bank = (label.split(" Bank")[0].strip() + " Bank") if " Bank" in label else ledger_name
	if not frappe.db.exists("Bank", bank):
		frappe.get_doc({"doctype": "Bank", "bank_name": bank}).insert(ignore_permissions=True)
	bank_account = frappe.get_doc(
		{
			"doctype": "Bank Account",
			"account_name": ledger_name,
			"bank": bank,
			"account": ledger,
			"is_company_account": 1,
			"company": company,
			"bank_account_no": number,
		}
	).insert(ignore_permissions=True)
	_created("Bank Account", bank_account.name)
	return ledger


def _group(company, account_name, root_type):
	name = frappe.db.get_value(
		"Account", {"company": company, "account_name": account_name, "is_group": 1, "root_type": root_type}, "name"
	)
	if name:
		return name
	# Fall back to the root group of that type (charts differ between companies).
	return frappe.db.get_value(
		"Account",
		{"company": company, "root_type": root_type, "is_group": 1, "parent_account": ("is", "not set")},
		"name",
	)


def _uses_fee_component_mapping(company):
	return frappe.get_meta("Account").has_field("slcm_fee_components") and frappe.db.exists(
		"Account", {"company": company, "slcm_fee_components": ("is", "set")}
	)


def _account(company, account_name, root_type, parent, is_group=0, account_type=None):
	name = frappe.db.get_value("Account", {"company": company, "account_name": account_name}, "name")
	if name:
		return name
	acc = frappe.get_doc(
		{
			"doctype": "Account",
			"company": company,
			"account_name": account_name,
			"parent_account": parent,
			"root_type": root_type,
			"is_group": is_group,
			"account_type": account_type or "",
			"account_currency": frappe.get_cached_value("Company", company, "default_currency"),
		}
	)
	acc.flags.ignore_permissions = True
	acc.insert()
	_created("Account", acc.name)
	return acc.name


def _fiscal_year_start(company):
	from erpnext.accounts.utils import get_fiscal_year

	try:
		return get_fiscal_year(today(), company=company)[1]
	except Exception:
		return getdate(today()).replace(day=1)
