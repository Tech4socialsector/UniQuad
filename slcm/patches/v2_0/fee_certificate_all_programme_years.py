import frappe


def execute():
	"""Education Loan certificates now show every programme year (with programme_year set);
	rebuild the year columns of all requests."""
	frappe.reload_doc("slcm", "doctype", "fee_certificate_request_year")
	for name in frappe.get_all("Fee Certificate Request", pluck="name"):
		doc = frappe.get_doc("Fee Certificate Request", name)
		doc.set("years", [])  # refilled by validate()
		doc.flags.ignore_permissions = True
		doc.save()
