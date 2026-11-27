"""Fill Applicant.submitted_device for applications submitted before the field existed.

The device comes from the User Activity Log: the row where the applicant's own login changed
Application Status from Draft to Submitted (or Submitted and Paid) carries the browser's
User-Agent. The latest such submit wins, as it does for new submissions. Applications submitted
before the log existed stay empty. Safe to run again: only empty fields are filled.
"""

import frappe

from slcm.admission.utils.submitted_device import USER_AGENT_MAX_LENGTH, device_from_user_agent

# User Activity Log stores changes as JSON: {"field": <label>, "from": <old>, "to": <new>}
SUBMIT_CHANGE = '%"field": "Application Status", "from": "Draft", "to": "Submitted%'


def execute():
	if not frappe.db.has_column("Applicant", "submitted_device") or not frappe.db.table_exists("User Activity Log"):
		return

	rows = frappe.db.sql(
		"""
		SELECT l.reference_name AS applicant, l.user_agent
		FROM `tabUser Activity Log` l
		JOIN `tabApplicant` a ON a.name = l.reference_name
		WHERE l.reference_doctype = 'Applicant'
		  AND l.user = a.owner
		  AND l.changes LIKE %(change)s
		  AND IFNULL(a.submitted_device, '') = ''
		ORDER BY l.creation
		""",
		{"change": SUBMIT_CHANGE},
		as_dict=True,
	)
	latest = {r.applicant: r.user_agent for r in rows}  # ordered by time: the last submit wins
	for applicant, user_agent in latest.items():
		device = device_from_user_agent(user_agent)
		if device:
			frappe.db.set_value(
				"Applicant",
				applicant,
				{"submitted_device": device, "submitted_user_agent": user_agent[:USER_AGENT_MAX_LENGTH]},
				update_modified=False,
			)
