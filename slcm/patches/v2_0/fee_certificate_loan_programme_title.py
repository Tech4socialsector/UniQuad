import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import _LOAN_BODY, MULTI_YEAR

# The default before this patch (kept literal: _LOAN_BODY has changed since).
PREVIOUS = (
	"<p>This is to certify that <strong>{{ student_name }} (student ID – {{ student_id }})</strong> is studying in "
	"{{ studying_year }} year {{ programme }} programme during the Academic Year (AY) {{ current_academic_year }} "
	"in this University and is now required to pay the course fee for {{ due_year }} year i.e. "
	"AY {{ due_academic_year }}.</p>"
	"<p>Year wise fee structure for {{ programme }} programme shown below.</p>"
)


def execute():
	"""Education Loan certificate text names the programme with its length
	("5-Year LL.B. (Hons.)") via {{ programme_title }}. Only the previous default is changed."""
	for row in frappe.get_all(
		"Fee Certificate Purpose Template",
		filters={"parent": "Fee Certificate Settings", "certificate_type": MULTI_YEAR},
		fields=["name", "body_text"],
	):
		if (row.body_text or "").strip() == PREVIOUS:
			frappe.db.set_value("Fee Certificate Purpose Template", row.name, "body_text", _LOAN_BODY, update_modified=False)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
