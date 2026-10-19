import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import DEFAULT_PAID_LINE

OLD_DEFAULT = "Academic Year {{ academic_year }} paid amount is Rs. {{ paid_amount }}/-"


def execute():
	"""Year-wise lines now show the original fee (matching the table) by default;
	only rows still on the old untouched default are switched."""
	settings = frappe.get_doc("Fee Certificate Settings")
	changed = False
	for row in settings.purposes:
		if row.paid_line_text == OLD_DEFAULT:
			row.paid_line_text = DEFAULT_PAID_LINE
			changed = True
	if changed:
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)
