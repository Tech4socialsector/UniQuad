"""
Second half of the Type of Issue migration - see
stash_type_of_issue_assignment_rules (pre_model_sync) for context.

Runs post_model_sync, once "HD Ticket Type Of Issue" exists as a real
doctype. Seeds it from the same option list the old client-side
ISSUE_OPTIONS JS map used to hardcode, carrying over any team override
found in the pre-sync stash of the now-removed assignment-rule child
table. It then rewrites existing HD Ticket rows so their
custom_type_of_issue value (previously a bare string like "Plumbing")
points at the new composite Link name ("Facilities-Plumbing") instead.
"""

import frappe

ISSUE_OPTIONS = {
	"Academics": ["Attendance Discrepancy", "Certificates - Letters", "Examination", "Learning Material", "Projects", "Viva", "FA", "MFA", "Others"],
	"Facilities": ["Carpentry", "Electrical", "House Keeping", "Plumbing", "Security", "Others"],
	"Finance": ["Fees", "Others"],
	"IT": ["Admin Portal", "Gsuite", "Group Creation", "ID Card", "Internet Connectivity", "Learning Platform", "Microsoft Office", "Online Library Access", "Others"],
	"PACE": ["Admission", "Academics", "Degree and Certificate", "Examination/Result", "Fee-related", "Grievance", "Technical Issues", "Transcripts"],
}


def execute():
	if not frappe.db.exists("DocType", "HD Ticket Type Of Issue"):
		return

	old_rule_teams = {}
	if "__type_of_issue_assignment_rule_stash" in frappe.db.get_tables(cached=False):
		for row in frappe.db.sql(
			"SELECT ticket_type, type_of_issue, team FROM `__type_of_issue_assignment_rule_stash`",
			as_dict=True,
		):
			old_rule_teams[(row.ticket_type, row.type_of_issue)] = row.team

	for ticket_type, issues in ISSUE_OPTIONS.items():
		if not frappe.db.exists("HD Ticket Type", ticket_type):
			continue
		for issue_name in issues:
			record_name = f"{ticket_type}-{issue_name}"
			if frappe.db.exists("HD Ticket Type Of Issue", record_name):
				continue
			doc = frappe.new_doc("HD Ticket Type Of Issue")
			doc.issue_name = issue_name
			doc.ticket_type = ticket_type
			doc.team = old_rule_teams.get((ticket_type, issue_name))
			doc.enabled = 1
			doc.insert(ignore_permissions=True)

	# Existing HD Ticket rows stored the raw issue name (e.g. "Plumbing")
	# from the old Select field. Rewrite them to the new composite Link
	# name (e.g. "Facilities-Plumbing") so they still resolve correctly.
	# Skip entirely on sites where the Helpdesk app isn't installed, since
	# `tabHD Ticket` won't exist there.
	if frappe.db.table_exists("HD Ticket") and frappe.db.has_column("HD Ticket", "custom_type_of_issue"):
		for ticket_type, issues in ISSUE_OPTIONS.items():
			for issue_name in issues:
				frappe.db.sql(
					"""
					UPDATE `tabHD Ticket`
					SET custom_type_of_issue = %(record_name)s
					WHERE ticket_type = %(ticket_type)s
					AND custom_type_of_issue = %(issue_name)s
					""",
					{
						"record_name": f"{ticket_type}-{issue_name}",
						"ticket_type": ticket_type,
						"issue_name": issue_name,
					},
				)

	frappe.db.commit()
	frappe.db.sql_ddl("DROP TABLE IF EXISTS `__type_of_issue_assignment_rule_stash`")
