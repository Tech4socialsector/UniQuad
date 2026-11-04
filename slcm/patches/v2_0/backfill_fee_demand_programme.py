import frappe


def execute():
	"""Stamp Programme / Batch on existing Fee Demands (generators never set them, so
	programme filters such as Fine Imposition's matched nothing), and move Bulk Fee
	Structure Update scopes from the old Programme/Program values to Batch/Programme."""
	from slcm.slcm.fee.fee_demand_utils import _enrolled_programs

	demands = frappe.get_all(
		"Fee Demand",
		filters=[["student", "is", "set"]],
		or_filters=[["program", "is", "not set"], ["programme", "is", "not set"]],
		fields=["name", "student", "program", "programme"],
		limit=0,
	)
	if demands:
		students = {d.student for d in demands}
		masters = {
			s.name: s
			for s in frappe.get_all(
				"Student Master",
				filters={"name": ["in", list(students)]},
				fields=["name", "batch", "programme_of_study"],
				limit=0,
			)
		}
		enrolled = _enrolled_programs(students)
		programmes = set(frappe.get_all("Programme", pluck="name"))
		batches = set(frappe.get_all("SLCM Batch", pluck="name"))

		for d in demands:
			sm = masters.get(d.student)
			if not sm:
				continue
			values = {}
			program = enrolled.get(d.student) or sm.programme_of_study
			if not d.program and program in programmes:
				values["program"] = program
			if not d.programme and sm.batch in batches:
				values["programme"] = sm.batch
			if values:
				frappe.db.set_value("Fee Demand", d.name, values, update_modified=False)

	# Old "Programme" meant the cohort (now Batch); old "Program" is now "Programme".
	table = "`tabBulk Fee Structure Update`"
	frappe.db.sql(f"UPDATE {table} SET target_scope = 'Batch' WHERE target_scope = 'Programme' AND IFNULL(programme, '') != ''")
	frappe.db.sql(f"UPDATE {table} SET target_scope = 'Programme' WHERE target_scope = 'Program'")
