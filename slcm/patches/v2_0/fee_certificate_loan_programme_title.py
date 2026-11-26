import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import _LOAN_BODY, MULTI_YEAR

PREVIOUS = _LOAN_BODY.replace("{{ programme_title }}", "{{ programme }}")


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
