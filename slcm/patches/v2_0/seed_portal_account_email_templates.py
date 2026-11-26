"""Applicant Portal Config: register / password reset Email Templates per portal.

Start the NLSAT Domestic and International fields with the templates those portals
used until now, so candidates get the same emails right after migrate:
register -> "Applicant Registration Email", reset -> System Settings' Reset Password
Template, else "Reset Password Template". PACE fields are left empty (PACE used a
built-in email): they fall back to System Settings until set.

Fixtures sync after this patch runs, so the two templates are first imported from
the fixture when missing (a new site). Fields already set are kept."""

import json
import os

import frappe

DT = "Applicant Portal Config"
REGISTER_TEMPLATE = "Applicant Registration Email"
RESET_TEMPLATE = "Reset Password Template"


def execute():
	meta = frappe.get_meta(DT)
	if not meta.has_field("nlsat_register_email_template"):
		return

	import_fixture_templates([REGISTER_TEMPLATE, RESET_TEMPLATE])

	def existing(*names):
		return next((n for n in names if n and frappe.db.exists("Email Template", n)), None)

	register = existing(REGISTER_TEMPLATE)
	reset = existing(frappe.db.get_system_setting("reset_password_template"), RESET_TEMPLATE)

	values = {
		"nlsat_register_email_template": register,
		"intl_register_email_template": register,
		"nlsat_reset_password_template": reset,
		"intl_reset_password_template": reset,
	}
	for field, value in values.items():
		if value and not frappe.db.get_single_value(DT, field):
			frappe.db.set_single_value(DT, field, value)


def import_fixture_templates(names):
	"""Insert the named Email Templates from slcm/fixtures/email_template.json when missing."""
	path = frappe.get_app_path("slcm", "fixtures", "email_template.json")
	if not os.path.exists(path):
		return
	# A fixed file inside the app; no user input in the path.
	with open(path) as f:  # nosemgrep: frappe-security-file-traversal
		records = json.load(f)
	for record in records:
		if record.get("name") in names and not frappe.db.exists("Email Template", record["name"]):
			frappe.get_doc(record).insert(ignore_permissions=True)
