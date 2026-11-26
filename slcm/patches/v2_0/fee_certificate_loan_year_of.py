import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import MULTI_YEAR

OLD = "{{ studying_year }} year {{ programme_title }} programme"
NEW = "{{ studying_year }} year of {{ programme_title }} programme"


def execute():
	"""Education Loan certificate: "is studying in III year of 3-Year LL.B. (Hons.) programme"."""
	for row in frappe.get_all(
		"Fee Certificate Purpose Template",
		filters={"parent": "Fee Certificate Settings", "certificate_type": MULTI_YEAR},
		fields=["name", "body_text"],
	):
		if OLD in (row.body_text or ""):
			frappe.db.set_value(
				"Fee Certificate Purpose Template",
				row.name,
				"body_text",
				row.body_text.replace(OLD, NEW, 1),
				update_modified=False,
			)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
