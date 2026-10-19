import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import DEFAULT_PURPOSES

DEMAND_LETTER = "Fee Demand Letter for Education Loan/others"
# Wording set by fee_certificate_demand_letter_format; replaced only if untouched.
OLD = {
	"body_text": (
		"<p>This is to certify that <strong>{{ student_name }}</strong> (Student ID : <strong>{{ student_id }}</strong>) "
		"studying in {{ current_year }} year {{ programme }} programme for the Academic Year (AY) "
		"{{ academic_year }} in this University and is required to pay following fee "
		"for {{ current_year }} year i.e. AY {{ academic_year }}.</p>"
	),
	"applicant_body_text": (
		"<p>This is to certify that <strong>{{ student_name }}</strong> (application number : "
		"<strong>{{ application_number }}</strong>) has applied for {{ programme_duration }} {{ programme }} "
		"programme for the Academic Year (AY) {{ academic_year }} in this University and "
		"is required to pay following fee.</p>"
	),
}


def execute():
	"""Fee Demand Letter wording exactly as the office's documents: "(student ID: …)" / "(application number: …)"."""
	new = next(p for p in DEFAULT_PURPOSES if p["purpose"] == DEMAND_LETTER)
	name = frappe.db.get_value(
		"Fee Certificate Purpose Template", {"parent": "Fee Certificate Settings", "purpose": DEMAND_LETTER}, "name"
	)
	if not name:
		return
	row = frappe.db.get_value("Fee Certificate Purpose Template", name, list(OLD), as_dict=True)
	updates = {f: new[f] for f, old in OLD.items() if (row.get(f) or "").strip() == old}
	if updates:
		frappe.db.set_value("Fee Certificate Purpose Template", name, updates, update_modified=False)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
