# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

MULTI_YEAR = "Multi Year Fee Structure"
SINGLE_YEAR_DEMAND = "Single Year Fee Demand"
SINGLE_YEAR_RECEIPT = "Single Year Fee Receipt"

# Wording is word for word from the office's documents "Existing student
# Certificate.docx" (campus students) and "Applicant Stage Certificates.docx"
# (applicants: application number only), one page per purpose.
_STUDENT = (
	"<p>This is to certify that <strong>{{ student_name }}</strong> (student ID: <strong>{{ student_id }}</strong>) "
	"studying in {{ current_year }} year {{ programme }} programme for the Academic Year (AY) {{ academic_year }} "
	"in this University "
)
_APPLICANT = (
	"<p>This is to certify that <strong>{{ student_name }}</strong> (application number: "
	"<strong>{{ application_number }}</strong>) has applied for {{ programme_duration }} {{ programme }} "
	"programme for the Academic Year (AY) {{ academic_year }} in this University "
)
_FEE_STRUCTURE = "<p>The fee structure for {{ programme }} is shown below.</p>"

_BANK_DETAILS = (
	"<p>The amount sanctioned towards fees may be remitted to the University bank account provided below:</p>"
	"{{ bank_table }}"
)

DEFAULT_PAID_LINE = (
	"Academic Year {{ academic_year }} paid amount is "
	"{% if is_paid %}Rs. {{ fee_amount }}/-{% else %}NIL{% endif %}"
)

# Seeded into the Purposes table (by patch, or the "Restore Default Purposes"
# button). Everything here is editable from the settings form afterwards.
DEFAULT_PURPOSES = [
	{
		"purpose": "Fee Certificate for Education Loan",
		"certificate_type": MULTI_YEAR,
		"enabled": 1,
		"include_bank_details": 1,
		"heading": "Fee Demand Letter",
		"body_text": _STUDENT
		+ "is now required to pay the course fee for {{ due_year }} year i.e. "
		+ "<strong>AY {{ due_academic_year }}</strong>.</p>"
		+ _FEE_STRUCTURE,
		"applicant_body_text": _APPLICANT + "and is required to pay following fee.</p>" + _FEE_STRUCTURE,
		"total_label": "Total fee payable",
		"show_paid_rows": 1,
		"paid_row_label": "Total Fee paid",
		"outstanding_row_label": "Outstanding fee",
		"bank_details_text": _BANK_DETAILS,
		"closing_text": "",
		"paid_line_text": DEFAULT_PAID_LINE,
	},
	{
		"purpose": "Fee Demand Letter for Education Loan/others",
		"certificate_type": SINGLE_YEAR_DEMAND,
		"enabled": 1,
		"include_bank_details": 1,
		"heading": "Fee Demand Letter",
		"body_text": _STUDENT
		+ "and is required to pay following fee for {{ current_year }} year i.e. AY {{ academic_year }}.</p>",
		"applicant_body_text": _APPLICANT + "and is required to pay following fee.</p>",
		"total_label": "Total fee payable",
		"bank_details_text": _BANK_DETAILS,
		"closing_text": "",
		"paid_line_text": DEFAULT_PAID_LINE,
	},
	{
		"purpose": "Fee Certificate/ Receipt for Scholarship/others",
		"certificate_type": SINGLE_YEAR_RECEIPT,
		"enabled": 1,
		"include_bank_details": 0,
		"require_full_payment": 1,
		"heading": "Fee Receipt",
		"body_text": _STUDENT
		+ "and has paid the following course fee for {{ current_year }} year i.e. AY {{ academic_year }}.</p>",
		"applicant_body_text": _APPLICANT + "and has paid the following fee.</p>",
		"total_label": "Total fee paid",
		"bank_details_text": _BANK_DETAILS,
		"closing_text": "",
		"paid_line_text": DEFAULT_PAID_LINE,
	},
]


class FeeCertificateSettings(Document):
	def validate(self):
		seen = set()
		for row in self.purposes:
			row.purpose = (row.purpose or "").strip()
			key = row.purpose.lower()
			if key in seen:
				frappe.throw(_("Row {0}: Purpose {1} is listed more than once").format(row.idx, frappe.bold(row.purpose)))
			seen.add(key)


def get_purpose_template(purpose):
	"""The settings row for this purpose label, or None."""
	if not purpose:
		return None
	settings = frappe.get_cached_doc("Fee Certificate Settings")
	return next((row for row in settings.purposes if row.purpose == purpose), None)


@frappe.whitelist()
def get_purpose_options():
	settings = frappe.get_cached_doc("Fee Certificate Settings")
	return [
		{
			"purpose": row.purpose,
			"certificate_type": row.certificate_type,
			"include_bank_details": row.include_bank_details,
			"require_full_payment": row.require_full_payment,
		}
		for row in settings.purposes
		if row.enabled
	]


@frappe.whitelist()
def restore_default_purposes():
	"""Re-add any default purpose that's missing and reset the content of the
	ones that exist (matched by purpose label). Custom purposes are left alone."""
	frappe.only_for("System Manager")
	settings = frappe.get_doc("Fee Certificate Settings")
	apply_default_purposes(settings, overwrite=True)
	settings.save()


def apply_default_purposes(settings, overwrite=False):
	existing = {row.purpose: row for row in settings.purposes}
	for default in DEFAULT_PURPOSES:
		row = existing.get(default["purpose"])
		if not row:
			settings.append("purposes", default)
		elif overwrite:
			row.update(default)
