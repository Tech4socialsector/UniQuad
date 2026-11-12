import frappe


def execute():
	"""
	Class XII Status is asked only for Undergraduate programmes. Postgraduate and Research Course
	applicants are always "Completed", but the portal's hidden-field cleanup saved it as empty.
	Applicants of any level with an empty value get the "Completed" default.
	"""
	frappe.db.sql(
		"""
		UPDATE `tabApplicant`
		SET class_xii_status = 'Completed'
		WHERE IFNULL(class_xii_status, '') != 'Completed'
		  AND (
		    IFNULL(program_level, '') IN ('Postgraduate', 'Research Course')
		    OR IFNULL(class_xii_status, '') = ''
		  )
		"""
	)
