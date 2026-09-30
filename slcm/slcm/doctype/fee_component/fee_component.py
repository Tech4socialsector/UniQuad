# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FeeComponent(Document):
	pass


DEFAULT_FEE_COMPONENTS = [
	{"component_name": "Admission Fee", "component_type": "Admission Fee", "ledger": "Admission Fee Receivable", "demand_type": "Academic"},
	{"component_name": "Tuition and Facilities Fee", "component_type": "Tuition and Facilities Fee", "ledger": "Tuition and Facilities Fee Receivable", "demand_type": "Academic"},
	{"component_name": "Hostel Residential and Mess Charges", "component_type": "Housing and Mess Fee", "ledger": "Hostel Residential and Mess Charges Receivable", "demand_type": "Academic"},
	{"component_name": "Student Refundable Deposit", "component_type": "Student Refundable Deposit", "ledger": "Student Refundable Deposit", "demand_type": "Academic"},
	{"component_name": "Deferral Fee", "component_type": "Gap Year Fee", "ledger": "Gap Year Fee", "demand_type": "Non Academic"},
	{"component_name": "Re-admission Fee", "component_type": "Re-admission Fee", "ledger": "Readmn Fee Receivable", "demand_type": "Academic"},
	{"component_name": "Fine - Mobile Phone, Other Disciplinary Things", "component_type": "Fine - Disciplinary", "ledger": "Fine-Mobile Phone,Other Disciplinary Things", "demand_type": "Non Academic"},
	{"component_name": "Reregistration Tuition Fee", "component_type": "Re-registration Tuition Fee", "ledger": "Reregistration Tuition Fee Receivable", "demand_type": "Academic"},
	{"component_name": "Mess Charges - Others", "component_type": "Mess Charges", "ledger": "Mess Charges - Lunch", "demand_type": "Non Academic"},
	{"component_name": "Continuation / Extension Fee", "component_type": "Continuation Fee (PhD)", "ledger": "Continuation / Extension Fee Receivable", "demand_type": "Academic"},
	{"component_name": "Fines - Regular Programmes", "component_type": "Fine - Late Payment", "ledger": "Fines - Regular Programmes", "demand_type": "Non Academic"},
	{"component_name": "Convocation Fee", "component_type": "Convocation Fee", "ledger": "Convocation Fee - Regular Programmes", "demand_type": "Non Academic"},
	{"component_name": "Application Fee", "component_type": "Application Fee", "ledger": "Application Fee - Regular Programmes", "demand_type": "Non Academic"},
	{"component_name": "Final Presentation Fee", "component_type": "Examination Fee", "ledger": "Examination Fee - Regular Programmes", "demand_type": "Non Academic"},
	{"component_name": "Examination Fee", "component_type": "Examination Fee", "ledger": "Examination Fee - Regular Programmes", "demand_type": "Non Academic"},
	{"component_name": "Re-submission of thesis", "component_type": "Examination Fee", "ledger": "Examination Fee - Regular Programmes", "demand_type": "Non Academic"},
	{"component_name": "Annual Fee", "component_type": "Annual Fee (PhD)", "ledger": "Annual Fee Receivable", "demand_type": "Academic"},
	{"component_name": "Course Work Fee", "component_type": "Course Work Fee (PhD)", "ledger": "Course Work Fee", "demand_type": "Academic"},
	{"component_name": "Registration Fee", "component_type": "Registration Fee (PhD)", "ledger": "Registration Fee", "demand_type": "Academic"},
	{"component_name": "Electric Appliance Usage Charges", "component_type": "Electrical Appliance Charges", "ledger": "Electricity & Power Charges", "demand_type": "Non Academic"},
	{"component_name": "Laundry Charges", "component_type": "Laundry Charges", "ledger": "Laundry Charges Hostel", "demand_type": "Non Academic"},
	{"component_name": "Postage Charges", "component_type": "Other", "ledger": "Postage Charges", "demand_type": "Non Academic"},
	{"component_name": "Duplicate ID Card", "component_type": "ID Card Fee", "ledger": "ID Cards Receipts - Regular Programmes", "demand_type": "Non Academic"},
	{"component_name": "Provisional Transcript", "component_type": "Provisional Degree Certificate", "ledger": "Provisional Degree Certificate - Regular Programmes", "demand_type": "Non Academic"},
]


# Old component names that were corrected; renamed in place so links follow.
RENAMED_FEE_COMPONENTS = {
	"Electric Applicance Usage Charges": "Electric Appliance Usage Charges",
}

# Fields kept in sync on already-existing components.
SYNCED_FIELDS = ("ledger", "demand_type")


@frappe.whitelist()
def create_default_fee_components():
	"""Create the standard Fee Components (with Zoho ledger and demand type) if missing,
	and sync ledger/demand type on the ones that already exist."""
	frappe.only_for("System Manager")

	for old_name, new_name in RENAMED_FEE_COMPONENTS.items():
		if frappe.db.exists("Fee Component", old_name) and not frappe.db.exists("Fee Component", new_name):
			frappe.rename_doc("Fee Component", old_name, new_name, force=True)
			frappe.db.set_value("Fee Component", new_name, "component_name", new_name)

	created = []
	updated = []
	skipped = []

	for row in DEFAULT_FEE_COMPONENTS:
		name = row["component_name"]
		if frappe.db.exists("Fee Component", name):
			current = frappe.db.get_value("Fee Component", name, SYNCED_FIELDS, as_dict=True)
			changes = {f: row[f] for f in SYNCED_FIELDS if current.get(f) != row[f]}
			if changes:
				frappe.db.set_value("Fee Component", name, changes)
				updated.append(name)
			else:
				skipped.append(name)
			continue

		doc = frappe.new_doc("Fee Component")
		doc.update(row)
		doc.insert(ignore_permissions=True)
		created.append(name)

	return {"created": created, "updated": updated, "skipped": skipped}
