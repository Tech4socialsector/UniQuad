import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import DEFAULT_PAID_LINE

OLD_IDS = (
	"(admit card number : <strong>{{ admit_card_number }},</strong> "
	"application number : <strong>{{ application_number }}</strong>)"
)
NEW_IDS = "(Student ID : <strong>{{ student_id }}</strong>)"
OLD_PAID_LINE = "Academic Year {{ academic_year }} paid amount is Rs. {{ fee_amount }}/-"


def execute():
	"""Certificates identify the student by Student ID instead of admit card and
	application number, and a year with nothing paid reads "NIL". Rows whose
	wording staff have already changed are left alone."""
	frappe.reload_doc("slcm", "print_format", "fee_certificate", force=True)
	for row in frappe.get_all("Fee Certificate Purpose Template", fields=["name", "body_text", "paid_line_text"]):
		updates = {}
		if row.body_text and OLD_IDS in row.body_text:
			updates["body_text"] = row.body_text.replace(OLD_IDS, NEW_IDS)
		if (row.paid_line_text or "").strip() == OLD_PAID_LINE:
			updates["paid_line_text"] = DEFAULT_PAID_LINE
		if updates:
			frappe.db.set_value("Fee Certificate Purpose Template", row.name, updates, update_modified=False)
