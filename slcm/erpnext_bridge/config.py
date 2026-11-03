"""Read the bridge configuration from ERPNext's own records - no SLCM settings DocType.

	Company (custom "SLCM Fee Accounting" section)  on/off, start date, the few extra ledgers
	Company (native fields)                         cost center, default cash and bank account
	Mode of Payment -> Mode of Payment Account      payment mode -> cash / bank / gateway clearing ledger
	Bank Account (is_company_account)               SLCM "University Bank Account" -> bank ledger (by account no.)
	Account (by name)                               Fee Component "Ledger" (or its name) -> income ledger
"""

import re

import frappe
from frappe import _

from slcm.erpnext_bridge import erpnext_installed

COMPANY_FIELDS = (
	"slcm_enable_fee_posting",
	"slcm_submit_journal_entries",
	"slcm_posting_from_date",
	"slcm_default_fee_income_account",
	"slcm_unallocated_fee_account",
	"slcm_output_gst_account",
	"slcm_fee_refund_account",
	"slcm_gateway_charges_account",
	"slcm_gateway_gst_account",
	"slcm_fees_include_gst",
	"slcm_stipend_account",
)
ACCOUNT_FIELDS = tuple(f for f in COMPANY_FIELDS if f.endswith("_account"))
ONLINE_MODES = ("Online Payment",)
MOVED_FROM_DUE = re.compile(r"^Moved from due (\S+)")


def get_posting_company():
	"""The one Company with SLCM fee posting enabled, or None."""
	if not erpnext_installed():
		return None
	try:
		return frappe.db.get_value("Company", {"slcm_enable_fee_posting": 1}, "name")
	except Exception:
		# custom fields not created yet
		return None


def get_config(company=None):
	company = company or get_posting_company()
	if not company:
		return None
	values = frappe.db.get_value(
		"Company",
		company,
		[*COMPANY_FIELDS, "cost_center", "default_cash_account", "default_bank_account", "abbr", "default_currency"],
		as_dict=True,
	)
	values.company = company
	return values


def require(cfg, fieldname, context=None):
	value = cfg.get(fieldname)
	if not value:
		label = frappe.get_meta("Company").get_label(fieldname)
		msg = _("Set {0} on Company {1} (SLCM Fee Accounting)").format(label, cfg.company)
		if context:
			msg += f" - {context}"
		frappe.throw(msg)
	return value


def normalise_ledger(name):
	name = (name or "").strip()
	# SLCM ledger names carry a "Receivable" suffix from Zoho; in ERPNext these are income ledgers.
	if name.lower().endswith(" receivable"):
		name = name[: -len(" receivable")]
	return name[:140]


def component_ledger_name(component):
	ledger = frappe.db.get_value("Fee Component", component, "ledger") if component else None
	return normalise_ledger(ledger or component or "")


def component_account(cfg, component):
	"""Ledger for a Fee Component: the Account named like its Ledger, else the default fee income ledger.
	Returns (account, used_default)."""
	name = component_ledger_name(component)
	if name:
		account = frappe.db.get_value(
			"Account", {"company": cfg.company, "account_name": name, "is_group": 0, "disabled": 0}, "name"
		)
		if account:
			return account, False
	return require(cfg, "slcm_default_fee_income_account", _("Fee Component {0}").format(component or "-")), True


def mode_of_payment_account(cfg, mode):
	if not mode:
		return None
	return frappe.db.get_value(
		"Mode of Payment Account", {"parent": mode, "company": cfg.company}, "default_account"
	)


def bank_account_for(cfg, slcm_bank_label):
	"""Match SLCM's 'HDFC Bank General 50100508244465' to ERPNext Bank Account by account number."""
	numbers = re.findall(r"\d{6,}", slcm_bank_label or "")
	if not numbers:
		return None
	return frappe.db.get_value(
		"Bank Account",
		{"is_company_account": 1, "company": cfg.company, "bank_account_no": numbers[-1], "disabled": 0},
		"account",
	)


def receipt_cash_account(cfg, payment_mode, slcm_bank_label=None):
	if payment_mode in ONLINE_MODES:
		account = mode_of_payment_account(cfg, payment_mode)
		if not account:
			frappe.throw(
				_("Set the {0} account for Mode of Payment '{1}' (the gateway clearing ledger)").format(
					cfg.company, payment_mode
				)
			)
		return account
	if payment_mode != "Cash":
		account = bank_account_for(cfg, slcm_bank_label)
		if account:
			return account
	account = mode_of_payment_account(cfg, payment_mode)
	if account:
		return account
	if payment_mode == "Cash":
		return require(cfg, "default_cash_account")
	return require(cfg, "default_bank_account")


def gateway_clearing_account(cfg):
	return receipt_cash_account(cfg, ONLINE_MODES[0])


def account_named(cfg, account_name):
	"""This company's ledger with that name (e.g. 'PACE Course Fee'), or None."""
	return frappe.db.get_value(
		"Account", {"company": cfg.company, "account_name": account_name, "is_group": 0, "disabled": 0}, "name"
	)


def payment_out_account(cfg, mode):
	"""Ledger money is paid out from. 'Online' for an outgoing payment means a bank transfer, never the gateway."""
	if mode == "Cash":
		return mode_of_payment_account(cfg, mode) or require(cfg, "default_cash_account")
	if mode in ONLINE_MODES or mode == "Online":
		return require(cfg, "default_bank_account")
	return mode_of_payment_account(cfg, mode) or require(cfg, "default_bank_account")


def fees_include_gst(cfg):
	"""Company setting: students pay GST on taxable Fee Components, so payments are GST-inclusive."""
	value = cfg.get("slcm_fees_include_gst")
	return True if value is None else bool(value)


def credit_note_source_demand(note):
	"""The paid Fee Demand a Student Credit Note's money was moved from, or None.

	Only such notes hold real money (paid fees moved to the student's excess); other credit notes
	(scholarship credit, manual) carry no cash and post nothing on cash basis. Notes created before
	source_fee_demand existed are matched through the remark move_to_excess writes."""
	demand = note.get("source_fee_demand")
	if not demand:
		match = MOVED_FROM_DUE.match(note.get("remarks") or "")
		demand = match.group(1) if match else None
	return demand if demand and frappe.db.exists("Fee Demand", demand) else None


def credit_note_holds_money(note):
	"""Money moved from a paid due, or money received directly and recorded on the note (Received Via)."""
	return bool(credit_note_source_demand(note) or note.get("received_via"))


def credit_note_date(note):
	if not credit_note_source_demand(note) and note.get("received_date"):
		return note.get("received_date")
	return note.get("creation")
