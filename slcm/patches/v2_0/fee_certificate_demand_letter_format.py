import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import DEFAULT_PURPOSES

OLD_BANK_TEXT = (
	"<p>The amount sanctioned towards fees may be remitted to the University bank account provided below:</p>"
	"<p>Name - {{ bank_account_name }}, A/c No – {{ bank_account_no }}, IFSC - {{ bank_ifsc_code }}, "
	"Bank &amp; branch - {{ bank_branch }}</p>"
)
DEMAND_LETTER = "Fee Demand Letter for Education Loan/others"
# Demand Letter fields and their previous defaults; only untouched values are replaced.
OLD_DEMAND = {
	"heading": "FEE CERTIFICATE",
	"total_label": "Total",
	"body_text": (
		"<p>This is to certify that <strong>{{ student_name }}</strong> (Student ID : <strong>{{ student_id }}</strong>) "
		"studying in {{ current_year }} year {{ programme }} programme for the Academic Year (AY) "
		"{{ academic_year }} in this University is required to pay the following course fee "
		"for {{ current_year }} year i.e. AY {{ academic_year }}.</p>"
	),
	"applicant_body_text": (
		"<p>This is to certify that <strong>{{ student_name }}</strong> (admit card number : "
		"<strong>{{ admit_card_number }},</strong> application number : <strong>{{ application_number }}</strong>) "
		"has applied for {{ programme_duration }} {{ programme }} programme for the Academic Year (AY) "
		"{{ academic_year }} in this University and is required to pay following fee.</p>"
		"<p>The fee structure for {{ programme }} is shown below.</p>"
	),
}


def execute():
	"""Office's Fee Demand Letter format: new heading / wording / total label, and
	bank details as a label-value list with Bank Name and Account Type."""
	frappe.reload_doc("slcm", "doctype", "fee_certificate_settings")
	new = next(p for p in DEFAULT_PURPOSES if p["purpose"] == DEMAND_LETTER)
	for row in frappe.get_all(
		"Fee Certificate Purpose Template",
		filters={"parent": "Fee Certificate Settings"},
		fields=["name", "purpose", "bank_details_text", *OLD_DEMAND],
	):
		updates = {}
		if (row.bank_details_text or "").strip() == OLD_BANK_TEXT:
			updates["bank_details_text"] = new["bank_details_text"]
		if row.purpose == DEMAND_LETTER:
			for field, old in OLD_DEMAND.items():
				if (row.get(field) or "").strip() == old:
					updates[field] = new[field]
		if updates:
			frappe.db.set_value("Fee Certificate Purpose Template", row.name, updates, update_modified=False)

	# Split the old combined "HDFC, Basaveshwaranagar, Bengaluru" into bank + branch.
	settings = frappe.get_single("Fee Certificate Settings")
	if not settings.bank_name and (settings.bank_branch or "").strip() == "HDFC, Basaveshwaranagar, Bengaluru":
		frappe.db.set_single_value("Fee Certificate Settings", "bank_name", "HDFC BANK")
		frappe.db.set_single_value("Fee Certificate Settings", "bank_branch", "Basaveshwaranagar Branch, Bengaluru- 560079")
	if not settings.bank_account_type:
		frappe.db.set_single_value("Fee Certificate Settings", "bank_account_type", "Savings")
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
