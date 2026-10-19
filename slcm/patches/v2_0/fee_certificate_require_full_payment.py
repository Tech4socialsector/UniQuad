import frappe


def execute():
	"""Education Loan certificates can only be downloaded from the portal once fees are fully paid."""
	frappe.reload_doc("slcm", "doctype", "fee_certificate_purpose_template")
	frappe.db.set_value(
		"Fee Certificate Purpose Template",
		{"parent": "Fee Certificate Settings", "purpose": "Fee Certificate for Education Loan"},
		"require_full_payment",
		1,
	)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
