import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import DEFAULT_PURPOSES


def execute():
	"""Fee certificates can now be issued for admission-stage applicants: existing
	requests are campus-student ones, and each purpose gets its applicant wording."""
	for dt in ("fee_certificate_purpose_template", "fee_certificate_request_year", "fee_certificate_request"):
		frappe.reload_doc("slcm", "doctype", dt)
	frappe.db.sql(
		"""UPDATE `tabFee Certificate Request` SET certificate_for = 'Campus Student'
		WHERE IFNULL(certificate_for, '') = ''"""
	)
	defaults = {p["purpose"]: p.get("applicant_body_text") for p in DEFAULT_PURPOSES}
	for row in frappe.get_all(
		"Fee Certificate Purpose Template",
		filters={"parent": "Fee Certificate Settings"},
		fields=["name", "purpose", "certificate_type", "applicant_body_text"],
	):
		if row.applicant_body_text:
			continue
		# Custom purposes borrow the default wording of the same certificate type.
		text = defaults.get(row.purpose) or next(
			(p.get("applicant_body_text") for p in DEFAULT_PURPOSES if p["certificate_type"] == row.certificate_type), None
		)
		if text:
			frappe.db.set_value("Fee Certificate Purpose Template", row.name, "applicant_body_text", text, update_modified=False)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
