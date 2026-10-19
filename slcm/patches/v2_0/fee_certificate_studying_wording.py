import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import DEFAULT_PURPOSES

_OLD_START = (
	"<p>This is to certify that <strong>{{ student_name }}</strong> (Student ID : <strong>{{ student_id }}</strong>) "
	"has applied for {{ programme_duration }} {{ programme }} programme for the Academic Year (AY) "
	"{{ academic_year }} in this University and "
)
_FEE_STRUCTURE = "<p>The fee structure for {{ programme }} is shown below.</p>"

# Previous default body per purpose; only rows still on it are switched.
OLD_BODIES = {
	"Fee Certificate for Education Loan": _OLD_START + "is required to pay following fee.</p>{{ paid_summary }}" + _FEE_STRUCTURE,
	"Fee Demand Letter for Education Loan/others": _OLD_START + "is required to pay following fee.</p>" + _FEE_STRUCTURE,
	"Fee Certificate/ Receipt for Scholarship/others": _OLD_START + "has paid the following fee.</p>",
}


def execute():
	"""Opening paragraph now reads "studying in II year <programme> ... for II year i.e. AY 2026-27"."""
	frappe.reload_doc("slcm", "doctype", "fee_certificate_purpose_template")
	new_bodies = {p["purpose"]: p["body_text"] for p in DEFAULT_PURPOSES}
	for row in frappe.get_all(
		"Fee Certificate Purpose Template", filters={"parent": "Fee Certificate Settings"}, fields=["name", "purpose", "body_text"]
	):
		if row.purpose in OLD_BODIES and (row.body_text or "").strip() == OLD_BODIES[row.purpose]:
			frappe.db.set_value("Fee Certificate Purpose Template", row.name, "body_text", new_bodies[row.purpose], update_modified=False)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
