import frappe


def execute():
	"""
	Fill Student Master.batch for students converted after the field was renamed
	from 'programme' to 'batch'. Applicant conversion kept writing to the old
	fieldname, so 'batch' was left empty and bulk enrollment rejected them.

	1. Copy from the old 'programme' column if it still exists in the table.
	2. Otherwise re-run the conversion lookup: Active Batch for the student's
	   programme_of_study + academic_year.
	"""
	if frappe.db.has_column("Student Master", "programme"):
		frappe.db.sql("""
			UPDATE `tabStudent Master` sm
			INNER JOIN `tabBatch` b ON b.name = sm.programme
			SET sm.batch = sm.programme
			WHERE IFNULL(sm.batch, '') = ''
		""")

	students = frappe.get_all(
		"Student Master",
		filters={
			"batch": ["is", "not set"],
			"programme_of_study": ["is", "set"],
			"academic_year": ["is", "set"],
		},
		fields=["name", "programme_of_study", "academic_year", "academic_term"],
	)

	for s in students:
		batch = frappe.db.get_value(
			"Batch",
			{"program": s.programme_of_study, "academic_year": s.academic_year, "status": "Active"},
			["name", "academic_term"],
			as_dict=True,
		)
		if not batch:
			continue

		values = {"batch": batch.name}
		if batch.academic_term and not s.academic_term:
			values["academic_term"] = batch.academic_term
		frappe.db.set_value("Student Master", s.name, values, update_modified=False)
