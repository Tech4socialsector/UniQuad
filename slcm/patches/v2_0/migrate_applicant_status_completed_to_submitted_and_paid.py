import frappe


def execute():
	"""
	1. Renames Applicant Status 'Completed' to 'Submitted and Paid' (or creates it if missing).
	2. Migrates existing Applicant records with status 'Completed' to 'Submitted and Paid'.
	3. Updates Notification condition for 'Application Fee Paid'.
	4. Renames 'NLSAT Application Completed Email' template if present.
	"""
	# 1. Handle Applicant Status doctype
	if frappe.db.table_exists("Applicant Status"):
		completed_exists = frappe.db.exists("Applicant Status", "Completed")
		submitted_paid_exists = frappe.db.exists("Applicant Status", "Submitted and Paid")

		if completed_exists and not submitted_paid_exists:
			frappe.rename_doc("Applicant Status", "Completed", "Submitted and Paid", force=True)
		elif not submitted_paid_exists:
			doc = frappe.new_doc("Applicant Status")
			doc.status = "Submitted and Paid"
			doc.stage_type = "Application"
			doc.status_type = "Completed"
			doc.next_step_note = (
				"You have successfully submitted your application and completed your fee payment. "
				"Please follow the instructions provided to proceed with the next stage of the admission process."
			)
			doc.flags.ignore_mandatory = True
			doc.insert(ignore_permissions=True)

	# 2. Update existing Applicant records
	if frappe.db.table_exists("Applicant") and frappe.db.has_column("Applicant", "status"):
		frappe.db.sql(
			"""
			UPDATE `tabApplicant`
			SET `status` = 'Submitted and Paid'
			WHERE `status` = 'Completed'
			"""
		)

	# 3. Update Notification trigger condition
	if frappe.db.table_exists("Notification"):
		frappe.db.sql(
			"""
			UPDATE `tabNotification`
			SET `condition` = 'doc.status=="Submitted and Paid"'
			WHERE `name` = 'Application Fee Paid'
			  AND `condition` = 'doc.status=="Completed"'
			"""
		)

	# 4. Rename Email Template if exists
	if frappe.db.table_exists("Email Template"):
		if frappe.db.exists("Email Template", "NLSAT Application Completed Email") and not frappe.db.exists(
			"Email Template", "NLSAT Application Submitted and Paid Email"
		):
			frappe.rename_doc(
				"Email Template",
				"NLSAT Application Completed Email",
				"NLSAT Application Submitted and Paid Email",
				force=True,
			)
			frappe.db.set_value(
				"Email Template",
				"NLSAT Application Submitted and Paid Email",
				"subject",
				'Application Submitted and Paid - {{ program_name or "Programme" }}',
			)
