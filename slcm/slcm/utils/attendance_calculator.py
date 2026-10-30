# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
Centralized Attendance Calculation Engine
This module contains all attendance calculation logic to ensure consistency
across the system. All attendance calculations should use these functions.
"""

import frappe
from frappe import _
from frappe.utils import flt


def calculate_student_attendance(student, class_name):
	"""
	Calculate attendance for a single student in a specific class.

	Args:
		student: Student ID
		class_name: Classes ID (the taught group)

	Returns:
		dict: Attendance summary with all calculated fields
	"""
	if not class_name:
		return {}
	return _calculate_and_save_summary(student, class_name)


def _calculate_and_save_summary(student, class_name):
	# Get or create attendance summary
	summary = get_or_create_summary(student, class_name)

	# Get Settings
	settings = frappe.get_single("Attendance Settings")

	# Calculate sessions
	sessions_data = calculate_sessions(class_name)

	# Calculate attendance
	attendance_data = calculate_attendance_records(student, class_name)

	# Calculate office hours
	office_hours_data = calculate_office_hours(student, class_name)

	# Update Office Hours Group Student (Office Hours)
	update_office_hours_in_group(student, class_name, office_hours_data['total_hours'])

	# Get condonation
	condonation_data = get_approved_condonation(student, class_name)

	# Get FA/MFA hours
	fa_mfa_data = calculate_fa_mfa_hours(student, class_name)

	# -- Update summary fields --
	# 0. Total Scheduled Class Hours (all planned sessions from Time Table)
	summary.total_scheduled_class_hours = sessions_data['total_hours']

	# 1. Total Sessions (Count — conducted only)
	summary.total_classes = sessions_data['conducted_sessions']

	# 2. Total Class Hours (Conducted)
	summary.total_class_hours = sessions_data['conducted_hours']

	# 3. Total Office Hours
	summary.total_office_hours = office_hours_data['total_hours']

	# 4. Total Condonation Hours
	summary.total_condonation_hours = condonation_data['hours']

	# 5. Total FA/MFA Hours
	summary.total_fa_mfa_hours = fa_mfa_data['total_hours']

	# 6. Basic Attendance (Sessions/Hours Attended)
	# This usually tracks Class Hours attended
	raw_attended = attendance_data['attended_hours']
	summary.total_attended_class_hours = raw_attended

	# 7. Total Hours (Calculated)
	# Sum of Class + Office + Condonation + FA/MFA
	# As requested: "only calculate total attended class, total office hours, total condonation hours, total fa mfa hours"
	total_hours_calculated = raw_attended

	# Add Office Hours
	total_hours_calculated += office_hours_data['total_hours']

	# Add Condonation
	total_hours_calculated += condonation_data['hours']

	# Add FA/MFA
	total_hours_calculated += fa_mfa_data['total_hours']

	# Credits (office hours, condonation, FA/MFA) make up for missed hours;
	# they can't take a student past the class hours actually conducted.
	if summary.total_class_hours > 0:
		total_hours_calculated = min(total_hours_calculated, summary.total_class_hours)

	summary.attended_classes = total_hours_calculated

	# Calculate Percentage
	# Percentage = (Total Hours Calculated / Total Class Hours Conducted) * 100
	# Note: Office hours usually don't add to the denominator unless they are mandatory "sessions".
	# If Office Hours are purely supplementary (bonus), denominator stays as Class Hours.
	# If Office Hours are mandatory, they should be in 'total_classes' (denominator).
	# Assuming standard "Bonus" behavior for now: Denominator = Class Hours.

	denominator = summary.total_class_hours

	if denominator > 0:
		summary.attendance_percentage = (summary.attended_classes / denominator) * 100
	else:
		summary.attendance_percentage = 0

	# Determine eligibility
	minimum_required = flt(settings.minimum_attendance_percentage)
	summary.minimum_required_percentage = minimum_required

	is_eligible = 0
	if summary.attendance_percentage >= minimum_required:
		is_eligible = 1

	# Check FA/MFA status (Override)
	if not is_eligible:
		if check_fa_mfa_eligibility(student, class_name):
			is_eligible = 1
			# Optionally log or mark separate field that it is via FA/MFA

	summary.eligible_for_exam = is_eligible
	# summary.eligibility_status = "Eligible" if is_eligible else "Shortage"

	# Populate Application Lists (Condonation & FA/MFA)
	populate_application_lists(summary, student, class_name)

	# Populate Section
	summary.section = get_student_section(student, class_name)
	summary.last_updated = frappe.utils.now()

	_persist_summary(summary)

	return summary.as_dict()


# Scalar fields written via a lock-free frappe.db.set_value() below — kept
# as an explicit list (rather than looping over every meta field) so a
# future field addition to Attendance Summary doesn't silently start (or
# stop) being persisted here without a deliberate decision.
_SUMMARY_SCALAR_FIELDS = [
	"total_scheduled_class_hours", "total_classes", "total_class_hours",
	"total_office_hours", "total_condonation_hours", "total_fa_mfa_hours",
	"total_attended_class_hours", "attended_classes", "attendance_percentage",
	"minimum_required_percentage", "eligible_for_exam", "section", "last_updated",
]


def _persist_summary(summary):
	"""Write the calculated Attendance Summary without loading-then-saving
	the whole document.

	This calculation can be triggered many times in quick succession for the
	same student+class (queued recalculation jobs racing manual
	saves), and Frappe's normal load -> modify -> doc.save() flow throws
	TimestampMismatchError whenever another writer touches the row in
	between — under heavy contention that can fail every retry attempt.
	frappe.db.set_value() issues a direct UPDATE keyed by document name, with
	no in-memory timestamp to go stale, so concurrent recalculations simply
	each apply their own (idempotent) result instead of fighting over one
	stale copy. Child tables (condonation_list / fa_mfa_list) still need a
	full table rewrite, which we do directly via SQL for the same reason.
	"""
	frappe.db.set_value(
		"Attendance Summary",
		summary.name,
		{field: summary.get(field) for field in _SUMMARY_SCALAR_FIELDS},
		update_modified=True,
	)
	_replace_child_rows(summary, "condonation_list")
	_replace_child_rows(summary, "fa_mfa_list")


def _replace_child_rows(summary, table_fieldname):
	"""Directly rewrite a child table's rows for one parent, without going
	through the parent document's save (and its timestamp check)."""
	rows = summary.get(table_fieldname) or []
	child_doctype = summary.meta.get_field(table_fieldname).options

	frappe.db.delete(child_doctype, {"parent": summary.name, "parenttype": "Attendance Summary"})

	for idx, row in enumerate(rows, start=1):
		row_dict = row.as_dict()
		row_dict.update({
			"parent": summary.name,
			"parenttype": "Attendance Summary",
			"parentfield": table_fieldname,
			"idx": idx,
		})
		row_dict.pop("name", None)
		frappe.get_doc(row_dict).db_insert()


def calculate_sessions(class_name):
	"""
	Calculate session statistics for a class.
	Returns total hours from Time Table (all scheduled classes).
	"""
	# Get total scheduled hours from Time Table.
	# Prefer the stored duration_hours; fall back to calculating from from_time/to_time
	# in case duration_hours was never populated on older records.
	scheduled_hours = frappe.db.sql("""
		SELECT
			COUNT(name) as total_schedules,
			COALESCE(SUM(
				CASE
					WHEN duration_hours IS NOT NULL AND duration_hours > 0
						THEN duration_hours
					WHEN from_time IS NOT NULL AND to_time IS NOT NULL AND to_time > from_time
						THEN TIMESTAMPDIFF(MINUTE, from_time, to_time) / 60.0
					ELSE 0
				END
			), 0) as total_hours
		FROM `tabTime Table`
		WHERE class_name = %s
		AND docstatus < 2
	""", class_name, as_dict=True)
	
	# Get conducted sessions count from Attendance Session
	# We still track conducted sessions for reference
	conducted = frappe.db.sql("""
		SELECT 
			COUNT(name) as conducted_sessions,
			COALESCE(SUM(duration_hours), 0) as conducted_hours
		FROM `tabAttendance Session`
		WHERE class_name = %s
		AND session_type IN ('Lecture', 'Tutorial')
		AND session_status = 'Conducted'
	""", class_name, as_dict=True)
	
	result = {
		'total_hours': 0,
		'conducted_hours': 0,
		'conducted_sessions': 0
	}

	sched_total = scheduled_hours[0]['total_hours'] if (scheduled_hours and scheduled_hours[0]) else 0

	if conducted and conducted[0]:
		result['conducted_hours'] = conducted[0]['conducted_hours']
		result['conducted_sessions'] = conducted[0]['conducted_sessions']

	# Use Time Table hours as denominator when available.
	# If no Time Table entry exists yet, fall back to conducted Attendance Session hours
	# so the percentage is not stuck at 0% for the whole term.
	if sched_total and sched_total > 0:
		result['total_hours'] = sched_total
	else:
		result['total_hours'] = result['conducted_hours']

	return result



def calculate_fa_mfa_hours(student, class_name):
	"""
	Calculate approved FA/MFA hours for a student in a class (FA/MFA is per course).
	"""
	# Get Course ID from the Class
	course_id = frappe.db.get_value("Classes", class_name, "course")
	
	if not course_id:
		return {'total_hours': 0}

	fa_mfa = frappe.db.sql("""
		SELECT 
			COALESCE(SUM(granted_hours), 0) as total_hours
		FROM `tabFA MFA Application`
		WHERE student = %s
		AND course = %s
		AND status = 'Approved'
		AND docstatus = 1
	""", (student, course_id), as_dict=True)
	
	if fa_mfa:
		return fa_mfa[0]
	
	return {'total_hours': 0}


def _get_class_context(class_name):
	"""Fetch course and academic_year for a Class."""
	course = None
	academic_year = None
	if class_name:
		cls = frappe.db.get_value(
			"Classes", class_name,
			["course", "academic_year"], as_dict=True
		)
		if cls:
			course = cls.course
			academic_year = cls.academic_year
	return course, academic_year


def calculate_attendance_records(student, class_name):
	"""
	Calculate attendance for Regular Class (Lecture/Tutorial).
	Returns total hours attended across ALL sources (RFID + Manual + Auto).

	Two-tier match:
	  1. class_name = class  (RFID / Auto / well-formed Manual)
	  2. class_name is NULL but course matches  (older manual records)

	NOTE: a third tier matching solely on academic_year was removed because it caused
	every null-class record to be counted against ALL classes in the same year,
	resulting in inflated attendance figures (ghost double-counting).
	"""
	course, _academic_year = _get_class_context(class_name)

	attendance = frappe.db.sql("""
		SELECT
			COALESCE(SUM(CASE
				WHEN status IN ('Present', 'Late', 'Excused') THEN hours_counted
				ELSE 0
			END), 0) AS attended_hours
		FROM `tabStudent Attendance`
		WHERE student = %s
		AND (
			class_name = %s
			OR (
				(class_name IS NULL OR class_name = '')
				AND course = %s
			)
		)
		AND session_type IN ('Lecture', 'Tutorial')
		AND docstatus < 2
	""", (student, class_name, course), as_dict=True)

	if attendance:
		return attendance[0]
	return {'attended_hours': 0}


def calculate_office_hours(student, class_name):
	"""
	Calculate office hours attendance for a student.
	Same two-tier match as calculate_attendance_records.
	"""
	course, _academic_year = _get_class_context(class_name)

	office_hours = frappe.db.sql("""
		SELECT
			COALESCE(SUM(hours_counted), 0) AS total_hours
		FROM `tabStudent Attendance`
		WHERE student = %s
		AND (
			class_name = %s
			OR (
				(class_name IS NULL OR class_name = '')
				AND course = %s
			)
		)
		AND session_type = 'Office Hour'
		AND status IN ('Present', 'Late', 'Excused')
		AND docstatus < 2
	""", (student, class_name, course), as_dict=True)

	if office_hours:
		return office_hours[0]
	return {'total_hours': 0}


def get_approved_condonation(student, class_name):
	"""Get approved condonation sessions for a student"""
	try:
		condonation = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(number_of_sessions), 0) as sessions,
				COALESCE(SUM(number_of_hours), 0) as hours
			FROM `tabStudent Attendance Condonation`
			WHERE student = %s
			AND class_name = %s
			AND final_status = 'Approved'
			AND docstatus = 1
		""", (student, class_name), as_dict=True)
		
		if condonation and condonation[0]['sessions']:
			return condonation[0]
	except Exception:
		# Table might not exist yet in Phase 1
		pass
	
	return {'sessions': 0, 'hours': 0}


def get_or_create_summary(student, class_name):
	"""Get existing summary or create new one"""
	summary_name = frappe.db.exists("Attendance Summary", {
		"student": student,
		"class_name": class_name
	})
	
	if summary_name:
		return frappe.get_doc("Attendance Summary", summary_name)
	
	# Create new summary
	summary = frappe.new_doc("Attendance Summary")
	summary.student = student
	summary.class_name = class_name
	
	try:
		summary.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# Race condition: Record created concurrently
		# Re-fetch using the deterministic name logic or filters
		# Re-calculate name logic to find it
		import hashlib
		class_hash = hashlib.md5(class_name.encode("utf-8")).hexdigest()[:10]
		name = f"ASU-{student}-{class_hash}"
		summary = frappe.get_doc("Attendance Summary", name)
		
	return summary


@frappe.whitelist()
def calculate_course_attendance(class_name):
	"""Calculate attendance for all students in a class.
	Uses the same two-tier match as calculate_attendance_records so that
	Manual records with NULL class_name are included.
	"""
	course, academic_year = _get_class_context(class_name)

	students = frappe.db.sql("""
		SELECT DISTINCT student
		FROM `tabStudent Attendance`
		WHERE (
			class_name = %s
			OR (
				(class_name IS NULL OR class_name = '')
				AND course = %s
			)
		)
		AND docstatus < 2
	""", (class_name, course), as_dict=True)

	results = []
	for student_row in students:
		result = calculate_student_attendance(student_row.student, class_name)
		results.append(result)

	return results


@frappe.whitelist()
def calculate_term_attendance(student, academic_term):
	"""Calculate attendance for all classes in a term for a student"""
	classes = frappe.db.sql("""
		SELECT DISTINCT class_name
		FROM `tabStudent Attendance`
		WHERE student = %s
		AND academic_term = %s
		AND IFNULL(class_name, '') != ''
	""", (student, academic_term), as_dict=True)

	results = []
	for class_row in classes:
		result = calculate_student_attendance(student, class_row.class_name)
		results.append(result)
	
	return results


@frappe.whitelist()
def recalculate_all_summaries():
	"""Recalculate all attendance summaries (scheduled job)"""
	summaries = frappe.get_all("Attendance Summary", fields=["student", "class_name"])
	
	count = 0
	for summary in summaries:
		try:
			calculate_student_attendance(summary.student, summary.class_name)
			count += 1
		except Exception as e:
			frappe.log_error(message=f"Error calculating attendance for {summary.student}: {str(e)}", title="Attendance Calculation Error")
	
	return {"success": True, "recalculated": count}


@frappe.whitelist()
def get_shortage_students(class_name, threshold=None):
	"""Get students below attendance threshold"""
	if not threshold:
		settings = frappe.get_single("Attendance Settings")
		threshold = flt(settings.minimum_attendance_percentage)
	
	shortage_students = frappe.db.sql("""
		SELECT 
			student,
			student_name,
			attendance_percentage,
			eligible_for_exam
		FROM `tabAttendance Summary`
		WHERE class_name = %s
		AND attendance_percentage < %s
		ORDER BY attendance_percentage ASC
	""", (class_name, threshold), as_dict=True)
	
	return shortage_students


@frappe.whitelist()
def get_eligibility_list(class_name):
	"""Get list of eligible students for exams"""
	eligible_students = frappe.db.sql("""
		SELECT 
			student,
			student_name,
			attendance_percentage,
			eligible_for_exam
		FROM `tabAttendance Summary`
		WHERE class_name = %s
		AND eligible_for_exam = 1
		ORDER BY student_name ASC
	""", class_name, as_dict=True)
	
	return eligible_students


@frappe.whitelist()
def check_fa_mfa_eligibility(student, class_name):
	"""Check if student has an approved FA/MFA application for this class's course"""
	# Get Course ID from the Class
	course_id = frappe.db.get_value("Classes", class_name, "course")
	
	if not course_id:
		return False

	exists = frappe.db.exists("FA MFA Application", {
		"student": student,
		"course": course_id,
		"status": "Approved",
		"docstatus": 1
	})
	
	return True if exists else False


def populate_application_lists(summary, student, class_name):
	"""
	Populate Condonation and FA/MFA application tables in Attendance Summary.
	"""
	# 1. Condonation Applications
	summary.set("condonation_list", [])
	
	try:
		condonation_apps = frappe.get_all("Student Attendance Condonation",
			filters={
				"student": student,
				"class_name": class_name,
				"docstatus": ["<", 2]  # Exclude Cancelled
			},
			fields=["name", "condonation_reason", "number_of_sessions", "number_of_hours", "final_status", "proof_document"],
			order_by="creation desc"
		)
		
		for app in condonation_apps:
			row = summary.append("condonation_list", {})
			row.condonation_application = app.name
			row.condonation_reason = app.condonation_reason
			row.number_of_sessions = app.number_of_sessions
			row.number_of_hours = app.number_of_hours
			row.final_status = app.final_status
			row.proof_document = app.proof_document
			
	except Exception as e:
		frappe.log_error(message=f"Error fetching condonation list: {str(e)}", title="Condonation List Fetch Error")

	# 2. FA/MFA Applications
	summary.set("fa_mfa_list", [])
	
	try:
		# Need Course ID for FA/MFA
		course_id = frappe.db.get_value("Classes", class_name, "course")
		if course_id:
			fa_mfa_apps = frappe.get_all("FA MFA Application",
				filters={
					"student": student,
					"course": course_id,
					"docstatus": ["<", 2]
				},
				fields=["name", "application_type", "reason", "status", "proof_document"],
				order_by="creation desc"
			)
			
			for app in fa_mfa_apps:
				row = summary.append("fa_mfa_list", {})
				row.fa_mfa_application = app.name
				row.application_type = app.application_type
				row.reason = app.reason
				row.status = app.status
				row.proof_document = app.proof_document
				
	except Exception as e:
		frappe.log_error(message=f"Error fetching FA/MFA list: {str(e)}", title="FA/MFA List Fetch Error")


def get_student_section(student, class_name):
	"""Resolve the student's Section for this Class from its enrolled-student roster
	(falls back to the Student Enrollment's section)."""
	section = frappe.db.sql("""
		SELECT COALESCE(NULLIF(ces.section, ''), se.section)
		FROM `tabClass Enrolled Student` ces
		JOIN `tabStudent Enrollment` se ON se.name = ces.student_enrollment
		WHERE ces.parenttype = 'Classes' AND ces.parent = %s
		AND se.student = %s
		ORDER BY (ces.status = 'Enrolled') DESC
		LIMIT 1
	""", (class_name, student))

	return section[0][0] if section else None


def update_office_hours_in_group(student, class_name, total_hours):
	"""
	Update total_office_hours in Office Hours Group Student doc for Office Hours Groups
	"""
	try:
		if not class_name:
			return

		# Find all Office Hours Groups for this class
		office_groups = frappe.get_all("Office Hours Group",
			filters={"class_name": class_name},
			pluck="name"
		)
		
		if not office_groups:
			return

		# Update the child table rows
		rows = frappe.get_all("Office Hours Group Student",
			filters={
				"parent": ["in", office_groups],
				"parenttype": "Office Hours Group",
				"student": student
			},
			fields=["name"]
		)

		for row in rows:
			frappe.db.set_value("Office Hours Group Student", row.name, "total_office_hours", total_hours)
			
	except Exception as e:
		frappe.log_error(message=f"Failed to update office hours group for {student}: {str(e)}", title="Office Hours Update Error")

