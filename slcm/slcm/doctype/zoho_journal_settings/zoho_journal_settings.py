# Copyright (c) 2026, Azim Premji Foundation and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# Used when the setting is left empty (or the doctype is not installed yet).
DEFAULTS = {
	"regular_application_fee_component": "Application Fee",
	"regular_application_fee_ledger": "Application Fee  - Regular Programmes",
	"regular_bank_account": "UBI Bank General 520101045114133",
	"regular_department": "AAD",
	"pace_application_fee_component": "",
	"pace_application_fee_ledger": "Application Fee - PACE Programmes",
	"pace_bank_account": "UBI Bank PACE 520101045120011",
	"pace_department": "PACE",
}


class ZohoJournalSettings(Document):
	pass


def get_application_fee_config(kind):
	"""Return {ledger, bank_account, department} for kind = "regular" | "pace".

	Ledger comes from the configured Fee Component's ledger, falling back to the default name.
	"""
	values = {}
	if frappe.db.exists("DocType", "Zoho Journal Settings"):
		values = frappe.db.get_singles_dict("Zoho Journal Settings") or {}

	def pick(key):
		return (values.get(f"{kind}_{key}") or "").strip() or DEFAULTS[f"{kind}_{key}"]

	component = pick("application_fee_component")
	ledger = frappe.db.get_value("Fee Component", component, "ledger") if component else None
	return frappe._dict(
		ledger=(ledger or "").strip() or DEFAULTS[f"{kind}_application_fee_ledger"],
		bank_account=pick("bank_account"),
		department=pick("department"),
	)
