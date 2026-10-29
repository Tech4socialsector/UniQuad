import frappe
from frappe.utils import today, add_days, cint, flt
from frappe import _


def create_event_demand(student, fee_component_name, amount, demand_type,
						due_days=30, trigger_doctype=None, trigger_name=None,
						description=None, academic_year=None, programme=None):
	"""
	Shared helper used by all event hooks to create a Fee Demand.
	Returns the created demand name, or None if skipped.
	"""
	if not academic_year:
		academic_year = frappe.get_value("Academic Year", {"is_current_year": 1}, "name")

	due_date = add_days(today(), due_days)

	doc = frappe.get_doc({
		"doctype": "Fee Demand",
		"student": student,
		"academic_year": academic_year,
		"demand_type": demand_type,
		"fee_component": fee_component_name,
		"description": description or fee_component_name,
		"demand_date": today(),
		"due_date": due_date,
		"original_amount": flt(amount),
		"trigger_ref_doctype": trigger_doctype,
		"trigger_ref_name": trigger_name,
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def generate_annual_demands(fee_notification_name):
	"""
	Bulk generator: called from Fee Notification on publish.
	Creates Fee Demands for all eligible students based on
	the notification's component rows.
	Returns a dict with counts for the Generation Log.
	"""
	notification = frappe.get_doc("Fee Notification", fee_notification_name)
	academic_year = notification.academic_year

	results = {"total": 0, "created": 0, "skipped": 0, "errors": 0, "rows": []}

	# Group component rows by fee_component so we can do category matching per student
	for component_row in notification.components:
		fee_component = component_row.fee_component
		batch_year = component_row.batch_year
		program_level = component_row.program_level
		row_category = component_row.student_category or "All"
		amount = component_row.amount

		fee_structure = _get_fee_structure(fee_component, batch_year, program_level, academic_year)

		students = _get_eligible_students(batch_year, program_level, academic_year)

		# Only process students whose category matches this component row
		# "All" rows are fallback — skip them here; they're used when no specific row matches
		if row_category != "All":
			students = [s for s in students if s.get("quota") == row_category]

		results["total"] += len(students)

		for student in students:
			try:
				# Skip hostel fees (handled by hostel allocation hook)
				if _is_hostel_component(fee_component):
					results["skipped"] += 1
					results["rows"].append({
						"student": student.name,
						"status": "Skipped",
						"remarks": "Hostel fee — handled by hostel allocation",
					})
					continue

				# Skip one-time fees for non-first-year students
				if fee_structure and fee_structure.is_one_time:
					if not _is_first_year_student(student.name, academic_year):
						results["skipped"] += 1
						results["rows"].append({
							"student": student.name,
							"status": "Skipped",
							"remarks": "One-time fee — not Year 1 student",
						})
						continue

				# Skip if demand already exists for this student + component (idempotent)
				if _demand_exists(student.name, fee_component, academic_year):
					results["skipped"] += 1
					results["rows"].append({
						"student": student.name,
						"status": "Skipped",
						"remarks": "Demand already exists",
					})
					continue

				due_offset = fee_structure.due_offset_days if fee_structure else 30
				due_date = add_days(notification.effective_from or today(), due_offset)

				demand = frappe.get_doc({
					"doctype": "Fee Demand",
					"student": student.name,
					"academic_year": academic_year,
					"demand_type": fee_structure.demand_type if fee_structure else "Academic",
					"fee_component": fee_component,
					"description": fee_component,
					"demand_date": today(),
					"due_date": due_date,
					"original_amount": flt(amount),
					"trigger_ref_doctype": "Fee Notification",
					"trigger_ref_name": fee_notification_name,
				})
				demand.insert(ignore_permissions=True)

				results["created"] += 1
				results["rows"].append({
					"student": student.name,
					"status": "Created",
					"remarks": demand.name,
				})

			except Exception as e:
				results["errors"] += 1
				results["rows"].append({
					"student": student.name,
					"status": "Error",
					"remarks": str(e),
				})
				frappe.logger().error(f"[fee_demand_utils] Error creating demand for {student.name}: {e}")

	frappe.db.commit()

	# Create generation log
	log = frappe.get_doc({
		"doctype": "Fee Demand Generation Log",
		"fee_notification": fee_notification_name,
		"academic_year": academic_year,
		"generated_on": frappe.utils.now_datetime(),
		"generated_by": frappe.session.user,
		"status": "Failed" if results["errors"] > 0 and results["created"] == 0 else "Completed",
		"total_students": results["total"],
		"success_count": results["created"],
		"skipped_count": results["skipped"],
		"error_count": results["errors"],
		"result_rows": [
			{
				"student": r.get("student"),
				"status": r.get("status"),
				"remarks": r.get("remarks"),
			}
			for r in results["rows"]
		],
	})
	log.insert(ignore_permissions=True)
	frappe.db.commit()

	# Update notification with log reference
	frappe.get_doc("Fee Notification", fee_notification_name).update_generation_log(log.name)

	return results


def _get_fee_structure(fee_component, batch_year, program_level, academic_year, student_category=None):
	filters = {
		"status": "Active",
		"academic_year": academic_year,
		"auto_generate_demand": 1,
	}
	if batch_year:
		filters["batch_year"] = batch_year
	if program_level and program_level != "All":
		filters["program_level"] = program_level

	# Try to find a category-specific structure first
	if student_category and student_category != "All":
		filters["student_category"] = student_category
		name = frappe.get_value("Fee Structure", filters, "name")
		if name:
			return frappe.get_value(
				"Fee Structure", name,
				["name", "demand_type", "due_offset_days", "is_one_time"],
				as_dict=True,
			)
		# Fall back to "All" category
		filters["student_category"] = "All"

	name = frappe.get_value("Fee Structure", filters, "name")
	if name:
		return frappe.get_value(
			"Fee Structure", name,
			["name", "demand_type", "due_offset_days", "is_one_time"],
			as_dict=True,
		)
	return None


def _get_eligible_students(batch_year, program_level, academic_year):
	filters = {"student_status": "Active"}
	if batch_year:
		filters["batch_year"] = batch_year

	students = frappe.get_all(
		"Student Master",
		filters=filters,
		fields=["name", "programme", "batch_year", "quota"],
	)

	# programme_level (UG/PG/PhD) is not a direct field on Student Master.
	# Narrow by joining through the Programme doctype's level_of_study if possible.
	if program_level and program_level != "All":
		level_map = {"UG": "Undergraduate", "PG": "Postgraduate", "PhD": "PhD"}
		level_of_study = level_map.get(program_level)
		if level_of_study:
			matching_programmes = frappe.get_all(
				"Programme",
				filters={"level_of_study": level_of_study},
				pluck="name",
			)
			if matching_programmes:
				students = [s for s in students if s.programme in matching_programmes]

	return students


def _is_first_year_student(student, academic_year):
	# Use year_of_study or current_year — Student Master has no admission_academic_year field
	current_year = frappe.get_value("Student Master", student, "current_year")
	return cint(current_year) == 1


def _demand_exists(student, fee_component, academic_year):
	return frappe.db.exists(
		"Fee Demand",
		{
			"student": student,
			"fee_component": fee_component,
			"academic_year": academic_year,
			"status": ["!=", "Cancelled"],
		},
	)


def _is_hostel_component(fee_component):
	component_type = frappe.get_value("Fee Component", fee_component, "component_type")
	return component_type in ("Housing and Mess Fee", "Off-campus Housing and Mess Fee", "Hostel Fee")
