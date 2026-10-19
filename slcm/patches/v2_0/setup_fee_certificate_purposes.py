import os

import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import apply_default_purposes

OLD_TO_NEW_PURPOSE = {
	"Education Loan": "Fee Certificate for Education Loan",
	"Detained Student Fee Structure": "Fee Certificate for Education Loan",
	"Bank Loan": "Fee Demand Letter for Education Loan/others",
	"Other": "Fee Demand Letter for Education Loan/others",
	"Scholarship": "Fee Certificate/ Receipt for Scholarship/others",
}

# Letter head images shipped with the app (from "Letter head with sign.docx").
LETTERHEAD_IMAGES = {
	"letterhead_header_image": "letterhead_header.png",
	"letterhead_footer_image": "letterhead_footer.png",
	"cfo_signature": "cfo_signature.png",
}

DEFAULT_BANK = {
	"bank_account_name": "National Law School of India University",
	"bank_account_no": "50100508244465",
	"bank_ifsc_code": "HDFC0000361",
	"bank_name": "HDFC BANK",
	"bank_branch": "Basaveshwaranagar Branch, Bengaluru- 560079",
	"bank_account_type": "Savings",
}


def execute():
	frappe.reload_doc("slcm", "doctype", "fee_certificate_purpose_template")
	frappe.reload_doc("slcm", "doctype", "fee_certificate_settings")
	frappe.reload_doc("slcm", "doctype", "fee_certificate_request_year")
	frappe.reload_doc("slcm", "doctype", "fee_certificate_request")

	settings = frappe.get_doc("Fee Certificate Settings")
	apply_default_purposes(settings)

	for fieldname, filename in LETTERHEAD_IMAGES.items():
		current = settings.get(fieldname) or ""
		# Only fill blanks and the placeholder files used during development.
		if not current or "dummy" in current.lower():
			settings.set(fieldname, _attach_app_image(filename))
	if settings.seal_image and "dummy" in settings.seal_image.lower():
		settings.seal_image = None
	settings.signature_includes_designation = 1

	for fieldname, value in DEFAULT_BANK.items():
		if not settings.get(fieldname):
			settings.set(fieldname, value)
	if not settings.institute_name:
		settings.institute_name = DEFAULT_BANK["bank_account_name"]

	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")

	for name, purpose in frappe.get_all("Fee Certificate Request", fields=["name", "purpose"], as_list=1):
		new_purpose = OLD_TO_NEW_PURPOSE.get(purpose)
		if not new_purpose:
			continue
		doc = frappe.get_doc("Fee Certificate Request", name)
		doc.purpose = new_purpose
		doc.set("years", [])  # rebuilt for the new purpose in validate()
		doc.flags.ignore_permissions = True
		doc.save()


def _attach_app_image(filename):
	path = frappe.get_app_path("slcm", "public", "images", "fee_certificate", filename)
	existing = frappe.db.get_value(
		"File",
		{"file_name": filename, "attached_to_doctype": "Fee Certificate Settings", "is_private": 0},
		"file_url",
	)
	if existing:
		return existing
	with open(path, "rb") as f:
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": os.path.basename(path),
				"content": f.read(),
				"is_private": 0,
				"attached_to_doctype": "Fee Certificate Settings",
				"attached_to_name": "Fee Certificate Settings",
			}
		).insert(ignore_permissions=True)
	return file_doc.file_url
