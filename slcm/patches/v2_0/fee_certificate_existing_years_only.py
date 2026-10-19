import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import MULTI_YEAR


def execute():
	"""Multi-year certificates now only show Academic Years that exist; drop the
	projected future-year rows (no Academic Year link) by rebuilding the table."""
	for name in frappe.get_all("Fee Certificate Request", filters={"certificate_type": MULTI_YEAR}, pluck="name"):
		doc = frappe.get_doc("Fee Certificate Request", name)
		doc.set("years", [])  # refilled by validate()
		doc.flags.ignore_permissions = True
		doc.save()
