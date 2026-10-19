"""
Updates the Academics "Type of Issue" list:
- Renames "Attendance" -> "Attendance Discrepancy"
- Adds "FA" and "MFA" as new issue types

See migrate_type_of_issue_to_link_doctype for the original seeding of
"HD Ticket Type Of Issue".
"""

import frappe

NEW_ISSUES = ["FA", "MFA"]


def execute():
	if not frappe.db.exists("DocType", "HD Ticket Type Of Issue"):
		return

	old_name = "Academics-Attendance"
	if frappe.db.exists("HD Ticket Type Of Issue", old_name):
		frappe.rename_doc(
			"HD Ticket Type Of Issue",
			old_name,
			"Academics-Attendance Discrepancy",
			force=True,
		)
		frappe.db.set_value(
			"HD Ticket Type Of Issue",
			"Academics-Attendance Discrepancy",
			"issue_name",
			"Attendance Discrepancy",
		)

		if frappe.db.table_exists("HD Ticket") and frappe.db.has_column("HD Ticket", "custom_type_of_issue"):
			frappe.db.set_value(
				"HD Ticket",
				{"custom_type_of_issue": old_name},
				"custom_type_of_issue",
				"Academics-Attendance Discrepancy",
			)

	if not frappe.db.exists("HD Ticket Type", "Academics"):
		frappe.db.commit()
		return

	for issue_name in NEW_ISSUES:
		record_name = f"Academics-{issue_name}"
		if frappe.db.exists("HD Ticket Type Of Issue", record_name):
			continue
		doc = frappe.new_doc("HD Ticket Type Of Issue")
		doc.issue_name = issue_name
		doc.ticket_type = "Academics"
		doc.enabled = 1
		doc.insert(ignore_permissions=True)

	frappe.db.commit()
