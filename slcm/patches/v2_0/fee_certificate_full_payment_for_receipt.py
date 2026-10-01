import frappe


def execute():
	"""The fully-paid rule applies to the Scholarship Receipt, not the Education Loan certificate."""
	for purpose, value in (
		("Fee Certificate for Education Loan", 0),
		("Fee Certificate/ Receipt for Scholarship/others", 1),
	):
		frappe.db.set_value(
			"Fee Certificate Purpose Template",
			{"parent": "Fee Certificate Settings", "purpose": purpose},
			"require_full_payment",
			value,
		)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
