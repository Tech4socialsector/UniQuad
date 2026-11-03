"""Cleaner "new reply" email to Helpdesk agents, and no "Sent via ERPNext" footer.

The agent notification falls back to helpdesk's plain default when HD Settings
has no content; set it from slcm/templates/emails/helpdesk_reply_to_agent.html
(only when empty, so content edited in Helpdesk settings is kept). The footer
is ERPNext's default_mail_footer hook, switched off by System Settings'
standard "Disable Standard Email Footer".
"""

import frappe


def execute():
	if frappe.db.exists("DocType", "HD Settings") and not (
		frappe.db.get_single_value("HD Settings", "reply_email_to_agent_content") or ""
	).strip():
		path = frappe.get_app_path("slcm", "templates", "emails", "helpdesk_reply_to_agent.html")
		with open(path) as f:
			frappe.db.set_single_value("HD Settings", "reply_email_to_agent_content", f.read())

	# email_body.get_footer reads the default, System Settings keeps both in sync
	frappe.db.set_single_value("System Settings", "disable_standard_email_footer", 1)
	frappe.db.set_default("disable_standard_email_footer", 1)
