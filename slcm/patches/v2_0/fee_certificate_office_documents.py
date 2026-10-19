import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import DEFAULT_PURPOSES

# Set from the office's final documents; they replace earlier wording on the
# three standard purposes (custom purposes are untouched).
FIELDS = (
	"heading",
	"body_text",
	"applicant_body_text",
	"total_label",
	"bank_details_text",
	"show_paid_rows",
	"paid_row_label",
	"outstanding_row_label",
)


def execute():
	"""Word-for-word wording from "Existing student Certificate.docx" and
	"Applicant Stage Certificates.docx" for all three standard purposes."""
	frappe.reload_doc("slcm", "doctype", "fee_certificate_purpose_template")
	frappe.reload_doc("slcm", "print_format", "fee_certificate", force=True)
	defaults = {p["purpose"]: p for p in DEFAULT_PURPOSES}
	for row in frappe.get_all(
		"Fee Certificate Purpose Template", filters={"parent": "Fee Certificate Settings"}, fields=["name", "purpose"]
	):
		default = defaults.get(row.purpose)
		if default:
			frappe.db.set_value(
				"Fee Certificate Purpose Template",
				row.name,
				{f: default.get(f, 0 if f == "show_paid_rows" else "") for f in FIELDS},
				update_modified=False,
			)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
