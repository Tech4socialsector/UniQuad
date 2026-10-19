import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import (
	DEFAULT_PAID_LINE,
	MULTI_YEAR,
)

FEE_STRUCTURE_LINE = "<p>The fee structure for {{ programme }} is shown below.</p>"


def execute():
	frappe.reload_doc("slcm", "doctype", "fee_certificate_purpose_template")

	settings = frappe.get_doc("Fee Certificate Settings")
	for row in settings.purposes:
		if not row.paid_line_text:
			row.paid_line_text = DEFAULT_PAID_LINE
		# Put the year-wise paid lines before the fee table on multi-year certificates.
		body = row.body_text or ""
		if row.certificate_type == MULTI_YEAR and "paid_summary" not in body and FEE_STRUCTURE_LINE in body:
			row.body_text = body.replace(FEE_STRUCTURE_LINE, "{{ paid_summary }}" + FEE_STRUCTURE_LINE)
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)

	# Rebuild the year columns: earlier requests could carry the same academic
	# year twice, and multi-year ones were sized from Programme.program_duration
	# (often 0) instead of Programme Master's duration.
	for name, certificate_type in frappe.get_all(
		"Fee Certificate Request", fields=["name", "certificate_type"], as_list=1
	):
		doc = frappe.get_doc("Fee Certificate Request", name)
		if certificate_type == MULTI_YEAR:
			doc.set("years", [])  # refilled by validate()
		doc.flags.ignore_permissions = True
		doc.save()
