"""Read the bridge configuration from ERPNext's own records - no SLCM settings DocType.

	Company (custom "SLCM Fee Accounting" section)  on/off, start date, the few extra ledgers
	Company (native fields)                         cost center, default cash and bank account
	Mode of Payment -> Mode of Payment Account      payment mode -> cash / bank / gateway clearing ledger
	Bank Account (is_company_account)               SLCM "University Bank Account" -> bank ledger (by account no.)
	Account (by name)                               Fee Component "Ledger" (or its name) -> income ledger
	Account (SLCM Fee Components)                   same, for charts whose account names differ from SLCM's
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
# Fees paid on no Fee Payment (re-exam / improvement exam online or at the counter, transcripts online, mess
# payments): the name each one's income ledger is looked up by - an Account of that name, or one listing it under
# SLCM Fee Components.
EXAM_FEE_NAMES = {
	"Re Exam Payment Log": "Re Exam Fee",
	"Improvement Exam Payment Log": "Improvement Exam Fee",
	"Transcript Request": "Transcript Fee",
	"Mess Payment": "Mess Fee",
}
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
	"""Ledger for a Fee Component: the Account named like its Ledger, else the Account listing its Ledger or name
	under SLCM Fee Components, else the default fee income ledger. Returns (account, used_default)."""
	account, _how = resolve_component(cfg, component)
	if account:
		return account, False
	return require(cfg, "slcm_default_fee_income_account", _("Fee Component {0}").format(component or "-")), True


def resolve_component(cfg, component):
	"""(account, how) without falling back to the default ledger; (None, None) when unmapped."""
	name = component_ledger_name(component)
	account = name and _exact_account(cfg, name)
	if account:
		return account, "Same name"
	account = mapped_account(cfg, name) or mapped_account(cfg, component)
	return (account, "SLCM Fee Components") if account else (None, None)


# The bridge posts without a Party, so Receivable / Payable ledgers can never take SLCM postings.
POSTABLE = {"is_group": 0, "disabled": 0, "account_type": ("not in", ("Receivable", "Payable"))}


def _exact_account(cfg, account_name):
	return frappe.db.get_value("Account", {"company": cfg.company, "account_name": account_name, **POSTABLE}, "name")


def mapped_account(cfg, slcm_name):
	"""This company's ledger listing slcm_name (case-insensitive) under SLCM Fee Components, or None."""
	key = (slcm_name or "").strip().lower()
	if not key or not frappe.get_meta("Account").has_field("slcm_fee_components"):
		return None
	rows = frappe.get_all(
		"Account",
		filters={"company": cfg.company, "slcm_fee_components": ("is", "set"), **POSTABLE},
		fields=["name", "slcm_fee_components"],
		order_by="lft",
	)
	for row in rows:
		if key in fee_component_lines(row.slcm_fee_components):
			return row.name
	return None


def fee_component_lines(value):
	"""Lower-cased, de-blanked lines of an Account's SLCM Fee Components."""
	return [line.strip().lower() for line in (value or "").splitlines() if line.strip()]


def slcm_fee_names():
	"""Every SLCM name a posting looks an account up by, as {lower-case: (name, source)}."""
	names = {}
	for comp in frappe.get_all("Fee Component", fields=["name", "ledger"], order_by="name"):
		names.setdefault(comp.name.lower(), (comp.name, _("Fee Component")))
		ledger = normalise_ledger(comp.ledger)
		if ledger:
			names.setdefault(ledger.lower(), (ledger, _("Ledger of {0}").format(comp.name)))
	field = frappe.get_meta("PACE Receipt").get_field("fee_type")
	for fee_type in ((field.options or "") if field else "").split("\n"):
		if fee_type.strip():
			names.setdefault(f"pace {fee_type.strip().lower()}", (f"PACE {fee_type.strip()}", _("PACE Receipt")))
	names.setdefault("fle course fee", ("FLE Course Fee", _("FLE Payment Log")))
	for doctype, name in EXAM_FEE_NAMES.items():
		names.setdefault(name.lower(), (name, _(doctype)))
	return names


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
	"""This company's ledger with that name (e.g. 'PACE Course Fee') or listing it under SLCM Fee Components, or None."""
	return _exact_account(cfg, account_name) or mapped_account(cfg, account_name)


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
