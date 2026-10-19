import frappe


def execute():
	"""Student Promotion gained a Draft → Published workflow.

	Runs before model sync: if the `stage` column doesn't exist yet, every
	row was created by the old flow — which applied decisions immediately —
	so they are all Published. If the column already exists, rows may be
	genuine Drafts from the new flow, so nothing is touched.
	"""
	if not frappe.db.table_exists("Student Promotion"):
		return
	if frappe.db.has_column("Student Promotion", "stage"):
		return
	frappe.reload_doc("slcm", "doctype", "student_promotion")
	frappe.db.sql(
		"""UPDATE `tabStudent Promotion`
		   SET stage = 'Published',
		       published_on = COALESCE(published_on, processed_on),
		       published_by = COALESCE(published_by, processed_by)"""
	)
