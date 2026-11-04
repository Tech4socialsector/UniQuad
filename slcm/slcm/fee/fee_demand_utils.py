import frappe
from frappe.utils import today, add_days, cint, flt, getdate
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


# Fee Notification's level labels → Programme.level_of_study values
LEVEL_MAP = {"UG": "Undergraduate", "PG": "Postgraduate", "PhD": "Research Course"}
GENERAL_CATEGORIES = ("", "All", None)


def parse_year_no(value):
	"""Year of study as an int from Student Master.current_year ("1", "1st Year", ...); 0 if unknown."""
	digits = "".join(ch for ch in str(value or "") if ch.isdigit())
	return cint(digits)


def is_foreign_national(nationality):
	"""Blank or Indian nationality → Indian fee table; anything else → foreign table."""
	return (nationality or "").strip().lower() not in ("", "indian", "india")


def _enrolled_programs(students=None):
	"""{student: program} from each student's latest Enrolled Student Enrollment."""
	filters = {"status": "Enrolled"}
	if students is not None:
		if not students:
			return {}
		filters["student"] = ["in", list(students)]
	rows = frappe.get_all(
		"Student Enrollment",
		filters=filters,
		fields=["student", "program"],
		order_by="enrollment_date desc, creation desc",
	)
	result = {}
	for r in rows:
		if r.program:
			result.setdefault(r.student, r.program)
	return result


def get_student_fee_profiles(filters=None, active_only=True):
	"""Active students with what fees depend on: programme, batch, year, category, nationality.

	Programme follows the latest Enrolled Student Enrollment, falling back to
	Student Master.programme_of_study (same rule as the Student Master fee sync).
	"""
	f = {"student_status": "Active"} if active_only else {}
	f.update(filters or {})
	students = frappe.get_all(
		"Student Master",
		filters=f,
		fields=["name", "batch", "programme_of_study", "current_year", "quota", "nationality"],
		limit=0,
	)
	enrolled = _enrolled_programs([s.name for s in students])
	levels = dict(frappe.get_all("Programme", fields=["name", "level_of_study"], as_list=True))
	profiles = []
	for s in students:
		program = enrolled.get(s.name) or s.programme_of_study or None
		profiles.append(frappe._dict(
			name=s.name,
			program=program,
			level=levels.get(program),
			batch=s.batch,
			year_no=parse_year_no(s.current_year),
			category=s.quota or "",
			is_foreign=is_foreign_national(s.nationality),
		))
	return profiles


def get_student_fee_profile(student):
	profiles = get_student_fee_profiles({"name": student}, active_only=False)
	return profiles[0] if profiles else None


def _structure_covers_year(fs, year_no):
	if cint(fs.phd_year_from) and cint(fs.phd_year_to):
		return cint(fs.phd_year_from) <= cint(year_no) <= cint(fs.phd_year_to)
	return cint(fs.year_no) == cint(year_no)


def find_fee_structure(program, academic_year=None, year_no=None, category=None, on_date=None):
	"""The Active Student Fee Structure for a programme / year / category, valid on `on_date`.

	A structure for the student's own category wins over an "All" (or blank) one.
	`year_no` None skips the year match (used where no student is known).
	Returns a dict (name, demand_type, due_offset_days, is_one_time, totals) or None.
	"""
	if not program:
		return None
	filters = {"program": program, "status": "Active", "applicable": "Student"}
	if academic_year:
		filters["academic_year"] = academic_year
	on_date = getdate(on_date or today())
	rows = frappe.get_all(
		"Fee Structure",
		filters=filters,
		fields=[
			"name", "year_no", "phd_year_from", "phd_year_to", "student_category",
			"valid_from", "valid_until", "demand_type", "due_offset_days", "is_one_time",
			"total_amount_for_indian", "total_amount_for_foreign",
		],
		order_by="valid_from desc, creation desc",
	)
	rows = [
		r for r in rows
		if (not r.valid_from or getdate(r.valid_from) <= on_date)
		and (not r.valid_until or getdate(r.valid_until) >= on_date)
		and (year_no is None or _structure_covers_year(r, year_no))
	]
	if category and category not in GENERAL_CATEGORIES:
		own = [r for r in rows if r.student_category == category]
		if own:
			return own[0]
	general = [r for r in rows if r.student_category in GENERAL_CATEGORIES]
	return general[0] if general else None


def structure_total(fs, is_foreign):
	"""Indian or foreign total of a structure; foreign falls back to Indian when it has no foreign fees."""
	if is_foreign and flt(fs.total_amount_for_foreign):
		return flt(fs.total_amount_for_foreign)
	return flt(fs.total_amount_for_indian)


def get_component_amount(fee_structure, fee_component, is_foreign=False, category=None):
	"""Tax-inclusive amount for one component in a structure's Indian or foreign table.

	Rows for the student's category win over "All" rows. Foreign students use the
	Indian table when the structure has no foreign rows. None = not in the structure.
	"""
	tables = ["fee_components_for_foreign", "fee_components_for_indian"] if is_foreign else ["fee_components_for_indian"]
	for table in tables:
		rows = frappe.get_all(
			"Fee Component Child",
			filters={"parent": fee_structure, "parenttype": "Fee Structure", "parentfield": table},
			fields=["fee_component", "student_category", "amount", "total_amount"],
		)
		if not rows:
			continue
		matching = [r for r in rows if r.fee_component == fee_component]
		own = [r for r in matching if category and category not in GENERAL_CATEGORIES and r.student_category == category]
		picked = own or [r for r in matching if r.student_category in GENERAL_CATEGORIES]
		if not picked:
			return None
		return sum(flt(r.total_amount or r.amount) for r in picked)
	return None


def _row_students(row, profiles):
	"""Students a Fee Notification row applies to. A filter that matches nothing means nobody."""
	result = profiles
	if row.get("program"):
		result = [p for p in result if p.program == row.program]
	if row.get("batch"):
		result = [p for p in result if p.batch == row.batch]
	if row.get("year_no"):
		result = [p for p in result if p.year_no == cint(row.year_no)]
	if row.program_level and row.program_level != "All":
		level = LEVEL_MAP.get(row.program_level, row.program_level)
		result = [p for p in result if p.level == level]
	if row.student_category and row.student_category != "All":
		result = [p for p in result if p.category == row.student_category]
	return result


def generate_annual_demands(fee_notification_name):
	"""
	Bulk generator: called from Fee Notification on publish.
	Creates Fee Demands for all eligible students based on the notification's
	component rows. Each student's amount comes from their own Fee Structure
	(programme + year + category, Indian or foreign table); the row's Fallback
	Amount is used only when no structure lists the component.
	Returns a dict with counts for the Generation Log.
	"""
	notification = frappe.get_doc("Fee Notification", fee_notification_name)
	academic_year = notification.academic_year
	effective_from = notification.effective_from or today()

	results = {"total": 0, "created": 0, "skipped": 0, "errors": 0, "rows": []}

	def log(student, status, remarks):
		results["skipped" if status == "Skipped" else "created" if status == "Created" else "errors"] += 1
		results["rows"].append({"student": student, "status": status, "remarks": remarks})

	profiles = get_student_fee_profiles()

	# Category-specific rows first; an "All" row then covers only students no
	# specific row of the same component already matched.
	rows = sorted(notification.components, key=lambda r: (r.student_category or "All") == "All")
	covered = set()

	for component_row in rows:
		fee_component = component_row.fee_component
		is_general_row = (component_row.student_category or "All") == "All"
		hostel = _is_hostel_component(fee_component)

		students = _row_students(component_row, profiles)
		results["total"] += len(students)

		for student in students:
			key = (student.name, fee_component)
			if is_general_row and key in covered:
				log(student.name, "Skipped", f"{fee_component}: covered by a {student.category} row")
				continue
			covered.add(key)

			try:
				# Skip hostel fees (handled by hostel allocation hook)
				if hostel:
					log(student.name, "Skipped", "Hostel fee — handled by hostel allocation")
					continue

				if component_row.fee_structure:
					fee_structure = frappe.get_value(
						"Fee Structure", component_row.fee_structure,
						["name", "demand_type", "due_offset_days", "is_one_time"], as_dict=True,
					)
				else:
					fee_structure = find_fee_structure(
						student.program, academic_year, student.year_no, student.category, effective_from,
					)

				amount = None
				if fee_structure:
					amount = get_component_amount(
						fee_structure.name, fee_component, student.is_foreign, student.category,
					)
				if amount is None and flt(component_row.amount):
					amount = flt(component_row.amount)
				if not amount:
					log(student.name, "Skipped", _(
						"No Fee Structure lists {0} for {1}, year {2}, category {3}"
					).format(fee_component, student.program or "—", student.year_no or "—", student.category or "—"))
					continue

				# Skip one-time fees for non-first-year students
				if fee_structure and fee_structure.is_one_time and student.year_no != 1:
					log(student.name, "Skipped", "One-time fee — not Year 1 student")
					continue

				# Skip if demand already exists for this student + component (idempotent)
				if _demand_exists(student.name, fee_component, academic_year):
					log(student.name, "Skipped", "Demand already exists")
					continue

				due_offset = cint(fee_structure.due_offset_days) if fee_structure else 30
				demand = frappe.get_doc({
					"doctype": "Fee Demand",
					"student": student.name,
					"academic_year": academic_year,
					"fee_component": fee_component,
					"description": fee_component,
					"demand_date": today(),
					"due_date": add_days(effective_from, due_offset),
					"original_amount": amount,
					"trigger_ref_doctype": "Fee Notification",
					"trigger_ref_name": fee_notification_name,
				})
				demand.insert(ignore_permissions=True)
				log(student.name, "Created", demand.name)

			except Exception as e:
				log(student.name, "Error", str(e))
				frappe.logger().error(f"[fee_demand_utils] Error creating demand for {student.name}: {e}")

	frappe.db.commit()

	# Create generation log
	log_doc = frappe.get_doc({
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
		"result_rows": results["rows"],
	})
	log_doc.insert(ignore_permissions=True)
	frappe.db.commit()

	# Update notification with log reference
	frappe.get_doc("Fee Notification", fee_notification_name).update_generation_log(log_doc.name)

	return results


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
