# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import time_diff_in_hours, get_datetime


@frappe.whitelist()
def get_faculty_context():
	"""Return the logged-in faculty's name and their assigned Course Offerings."""
	user = frappe.session.user
	roles = set(frappe.get_roles(user))

	is_faculty = "slcm_Faculty" in roles
	is_admin = bool(
		{"System Manager", "slcm_Registrar", "slcm_Programme Chair", "Accounts User"} & roles
	)

	faculty_name = None
	faculty_full_name = None
	assigned_offerings = []

	if is_faculty:
		faculty_name = frappe.db.get_value("Faculty", {"user_id": user}, "name")
		if faculty_name:
			fn = frappe.db.get_value("Faculty", faculty_name, ["first_name", "last_name"], as_dict=True) or {}
			faculty_full_name = " ".join(filter(None, [fn.get("first_name"), fn.get("last_name")]))

			primary = frappe.get_all(
				"Course Offering",
				filters={"faculty": faculty_name},
				fields=["name", "course_title", "academic_year", "term_name", "program"],
			)
			seen = {o["name"] for o in primary}

			via_schedule = frappe.get_all(
				"Course Schedule",
				filters={"instructor": faculty_name, "docstatus": ["<", 2]},
				pluck="course_offering",
			)
			via_timetable = frappe.get_all(
				"Time Table",
				filters={"instructor": faculty_name, "docstatus": ["<", 2]},
				pluck="course_offering",
			)
			extra_names = {n for n in (via_schedule + via_timetable) if n and n not in seen}
			if extra_names:
				extra = frappe.get_all(
					"Course Offering",
					filters={"name": ["in", list(extra_names)]},
					fields=["name", "course_title", "academic_year", "term_name", "program"],
				)
				primary.extend(extra)

			assigned_offerings = primary

	return {
		"is_faculty": is_faculty,
		"is_admin": is_admin,
		"faculty_name": faculty_name,
		"faculty_full_name": faculty_full_name,
		"assigned_offerings": assigned_offerings,
	}


def _faculty_display_name(faculty_id):
	"""Return a Faculty's display name, falling back to the raw ID if the
	record has no name on file. Student Attendance's `instructor` field is
	a plain Data field (not a Link), so it needs the resolved name stored
	directly rather than the Faculty ID."""
	if not faculty_id:
		return None
	name = frappe.db.get_value("Faculty", faculty_id, ["first_name", "last_name"], as_dict=True)
	if not name:
		return faculty_id
	full_name = " ".join(filter(None, [name.first_name, name.last_name]))
	return full_name or faculty_id


def _find_course_offering(course, program, academic_year=None):
	"""Look up the Course Offering for a given course/program, optionally filtered by year."""
	if not course or not program:
		return None

	filters = {"course_title": course, "program": program, "docstatus": ["<", 2]}
	if academic_year:
		filters["academic_year"] = academic_year

	offering = frappe.db.get_value("Course Offering", filters, "name")

	if not offering and academic_year:
		# Retry without academic year in case of data mismatch
		filters.pop("academic_year")
		offering = frappe.db.get_value("Course Offering", filters, "name")

	return offering


def _get_or_create_attendance_session(attendance_date, course_offering, based_on):
	"""
	Find or create an Attendance Session for this date/course, so that the
	calculator has a denominator (conducted class hours) for the percentage.
	Returns the session name or None on failure.
	"""
	if not course_offering:
		return None

	filters = {
		"session_date": attendance_date,
		"course_offering": course_offering,
		"session_type": "Lecture",
		"docstatus": ("<", 2),
	}

	existing = frappe.db.exists("Attendance Session", filters)
	if existing:
		return existing

	try:
		sess = frappe.get_doc({
			"doctype": "Attendance Session",
			"session_date": attendance_date,
			"based_on": based_on,
			"course_offering": course_offering,
			"session_start_time": "09:00:00",
			"session_end_time": "10:00:00",
			"duration_hours": 1.0,
			"session_type": "Lecture",
			"session_status": "Conducted",
			"attendance_marked": 1,
		})
		sess.flags.skip_auto_attendance = True
		sess.insert(ignore_permissions=True)
		return sess.name
	except Exception as e:
		frappe.log_error(
			message=f"Failed to create Attendance Session for {course_offering} on {attendance_date}: {e!s}",
			title="Attendance Session Creation Error",
		)
		return None


# ------------------------------------------------------------
# STUDENT FETCH HELPERS (called by the Attendance Tool page)
# ------------------------------------------------------------

@frappe.whitelist()
def get_students_from_schedule(course_schedule, attendance_date=None):
	"""Return active students for a Course Schedule with their existing attendance status."""
	from slcm.slcm.doctype.student_attendance_tool.student_attendance_tool import (
		get_student_attendance_records,
	)

	return get_student_attendance_records(
		based_on="Course Schedule",
		date=attendance_date,
		course_schedule=course_schedule,
	)


# ------------------------------------------------------------
# BULK ATTENDANCE FROM COURSE SCHEDULE
# ------------------------------------------------------------
@frappe.whitelist()
def create_bulk_attendance_from_schedule(course_schedule, attendance_date, attendance_data, instructor=None):
	if not course_schedule:
		frappe.throw(_("Course Schedule is required"))

	if not attendance_date:
		frappe.throw(_("Attendance Date is required"))

	if get_datetime(attendance_date) > get_datetime():
		frappe.throw(_("Cannot mark attendance for future dates"))

	schedule = frappe.get_doc("Course Schedule", course_schedule)

	course_offering = schedule.course_offering
	if not course_offering:
		frappe.throw(_("Course Offering is required on the Course Schedule"))

	students = frappe.db.sql("""
		SELECT DISTINCT se.student
		FROM `tabStudent Enrollment` se
		JOIN `tabStudent Enrollment Course` sec ON sec.parent = se.name
		WHERE sec.course_offering = %s
		AND sec.status = 'Enrolled' AND se.status = 'Enrolled' AND se.docstatus = 0
	""", (course_offering,), pluck=True)

	if not students:
		frappe.throw(_("No active students found"))

	if isinstance(attendance_data, str):
		attendance_data = json.loads(attendance_data)

	# Ensure an Attendance Session exists so the calculator has a denominator
	attendance_session = _get_or_create_attendance_session(
		attendance_date, course_offering, "Course Schedule"
	)

	created, updated, errors = 0, 0, []

	for student in students:
		status = attendance_data.get(student, "Absent")

		existing = frappe.db.exists(
			"Student Attendance",
			{
				"student": student,
				"attendance_date": attendance_date,
				"course_schedule": course_schedule,
				"based_on": "Course Schedule",
				"docstatus": ("<", 2),
			},
		)

		try:
			if existing:
				doc = frappe.get_doc("Student Attendance", existing)
				doc.status = status
				if course_offering and not doc.course_offer:
					doc.course_offer = course_offering
				if attendance_session and not doc.attendance_session:
					doc.attendance_session = attendance_session
				doc.save()
				updated += 1
			else:
				frappe.get_doc(
					{
						"doctype": "Student Attendance",
						"student": student,
						"attendance_date": attendance_date,
						"date": attendance_date,
						"status": status,
						"based_on": "Course Schedule",
						"course_schedule": course_schedule,
						"program": schedule.program,
						"course": schedule.course,
						"course_offer": course_offering,
						"attendance_session": attendance_session,
						"instructor": _faculty_display_name(instructor or getattr(schedule, "instructor", None)),
						"room": getattr(schedule, "room", None),
						"source": "Manual",
					}
				).insert()
				created += 1
		except Exception as e:
			errors.append(f"{student}: {e!s}")

	# Trigger Attendance Summary calculation for each affected student
	if course_offering:
		from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
		for student in students:
			try:
				calculate_student_attendance(student, course_offering)
			except Exception as e:
				frappe.log_error(
					message=f"Failed to calculate attendance for {student}: {e!s}",
					title="Attendance Calculation Error",
				)

	return {
		"status": "success",
		"created": created,
		"updated": updated,
		"errors": errors,
		"message": f"Attendance marked. {'Attendance Summary updated.' if course_offering else 'Could not find Course Offering — Attendance Summary not updated.'}",
		"total_processed": len(students),
	}


# ------------------------------------------------------------
# MAIN STUDENT ATTENDANCE TOOL API
# ------------------------------------------------------------
@frappe.whitelist()
def mark_attendance(
	students_present=None,
	students_absent=None,
	course_schedule=None,
	class_schedule=None,
	date=None,
	based_on=None,
	office_hours_group=None,
):
	if not date:
		frappe.throw(_("Date is required"))

	if get_datetime(date) > get_datetime():
		frappe.throw(_("Cannot mark attendance for future dates"))

	if not based_on:
		frappe.throw(_("Based On is required"))

	if isinstance(students_present, str):
		students_present = json.loads(students_present)
	if isinstance(students_absent, str):
		students_absent = json.loads(students_absent)

	students_present = students_present or []
	students_absent = students_absent or []

	schedule = frappe.get_doc("Course Schedule", course_schedule) if course_schedule else None
	class_sched = frappe.get_doc("Time Table", class_schedule) if class_schedule else None
	# Office Hours Group is a Student Group (group_based_on = Office Hours). It
	# has programme / course_offering / academic year & term but no course or
	# instructor - those are resolved from the Course Offering below.
	office_group = frappe.get_doc("Student Group", office_hours_group) if office_hours_group else None

	program = None
	if schedule:
		program = schedule.program
	elif class_sched:
		program = class_sched.programme
	elif office_group:
		program = office_group.programme

	# Determine Course
	course = None
	if schedule:
		course = schedule.course
	elif class_sched:
		course = class_sched.course

	# Determine Course Offering — prefer the direct link already stored on
	# whichever source doc this came from (Course Schedule / Time Table /
	# Office Hours Group all carry their own course_offering field now), so
	# we don't depend on program/course being resolved first.
	course_offering = None

	if schedule and schedule.course_offering:
		course_offering = schedule.course_offering
	elif class_sched and class_sched.course_offering:
		course_offering = class_sched.course_offering
	elif office_group and office_group.course_offering:
		course_offering = office_group.course_offering

	# Backfill program/course from the resolved Course Offering when the
	# source doc's own fields were blank (e.g. a Time Table entry created
	# without a Class Configuration has no `programme` value).
	if course_offering and (not program or not course):
		co_details = frappe.db.get_value(
			"Course Offering", course_offering, ["program", "course_title"], as_dict=True
		)
		if co_details:
			program = program or co_details.program
			course = course or co_details.course_title

	# Priority 1: Strict match with Academic Year and Term (if available) —
	# only needed as a fallback when nothing above resolved a Course Offering.
	if not course_offering and course and program:
		filters = {"course_title": course, "program": program, "docstatus": ["<", 2]}

		# Add Academic Year/Term from Office Hours Group
		if office_group:
			if office_group.academic_year:
				filters["academic_year"] = office_group.academic_year
			if office_group.academic_term:
				filters["term_name"] = office_group.academic_term
			
		# Note: Course Offering has 'term_name' data field, might be risky to filter strictly if naming differs.
		# We'll stick to Year for strictness first.
		
		# Try fetching with Year
		course_offering = frappe.db.get_value("Course Offering", filters, "name")
		
		# Strategy 2: If fail, try removing Term (common mismatch source)
		if not course_offering:
			filters.pop("term_name", None)
			course_offering = frappe.db.get_value("Course Offering", filters, "name")

		# Strategy 3: If fail, try removing Academic Year (maybe data mismatch)
		if not course_offering:
			filters.pop("academic_year", None)
			course_offering = frappe.db.get_value("Course Offering", filters, "name")
			
		# Strategy 4: If still fail, try finding *any* Open/Active offering for this Course+Program
		# Sort by creation desc to get the most recent one
		if not course_offering:
			final_filters = {"course_title": course, "program": program, "docstatus": ["<", 2]}
			offerings = frappe.get_all(
				"Course Offering",
				filters=final_filters,
				fields=["name"],
				order_by="creation desc",
				limit=1
			)
			if offerings:
				course_offering = offerings[0].name

		if not course_offering:
			frappe.log_error(
				title="Course Offering Lookup Failed",
				message=f"Could not find Course Offering.\nCourse: {course}\nProgram: {program}\nOffice Group: {office_hours_group}\nFilters tried: {filters}"
			)

	office_instructor = None
	if office_group and course_offering:
		office_instructor = frappe.db.get_value("Course Offering", course_offering, "faculty")

	# ---------------------------------------------------------
	# Ensure Attendance Session Exists and Update It
	# ---------------------------------------------------------
	attendance_session = None
	
	# Lookup Filters
	session_filters = {
		"session_date": date,
		"course_offering": course_offering,
		"docstatus": ("<", 2)
	}

	if based_on == "Time Table" and class_schedule:
		session_filters["class_schedule"] = class_schedule
	elif based_on == "Course Schedule" and course_schedule:
		session_filters["course_schedule"] = course_schedule
	elif based_on == "Office Hours" and office_hours_group:
		session_filters["office_hours_group"] = office_hours_group
		session_filters["session_type"] = "Office Hour"
	
	# Try finding existing session
	# Try finding existing session
	session_name = frappe.db.exists("Attendance Session", session_filters)
	
	if session_name:
		attendance_session = session_name
		# Status update is deferred to the final save after the student loop

	else:
		# Create new Attendance Session if not found (Fallback)
		start_time = None
		end_time = None
		duration = 0
		instructor = None

		if class_sched and class_sched.from_time and class_sched.to_time:
			# Calculate duration
			start_dt = frappe.utils.get_datetime(f"{date} {class_sched.from_time}")
			end_dt = frappe.utils.get_datetime(f"{date} {class_sched.to_time}")
			duration = frappe.utils.time_diff_in_hours(end_dt, start_dt)
			start_time = class_sched.from_time
			end_time = class_sched.to_time
			instructor = class_sched.instructor
		
		# Fallback for Office Hours (default 1 hour?)
		elif based_on == "Office Hours" and office_hours_group:
			# Use current time or default? Let's use 09:00 - 10:00 as placeholder
			start_time = "09:00:00"
			end_time = "10:00:00"
			duration = 1.0
			instructor = office_instructor

			# Ensure we store the course offering if we found one!
			# (Code logic handles it via locals or logic below?)
			# Yes, `course_offering` variable is available.

		if start_time and end_time:
			sess_doc = frappe.get_doc({
				"doctype": "Attendance Session",
				"session_date": date,
				"based_on": based_on,
				"class_schedule": class_schedule,
				"course_schedule": course_schedule if based_on == "Course Schedule" else None,
				"office_hours_group": office_hours_group if based_on == "Office Hours" else None,
				"course_offering": course_offering,
				"session_start_time": start_time,
				"session_end_time": end_time,
				"duration_hours": duration,
				"session_type": "Office Hour" if based_on == "Office Hours" else "Lecture",
				"instructor": instructor,
				"session_status": "Conducted",
				"attendance_marked": 1
			})
			sess_doc.flags.skip_auto_attendance = True
			sess_doc.insert(ignore_permissions=True)
			attendance_session = sess_doc.name

	# ---------------------------------------------------------

	def upsert(student_id, status):
		if attendance_session:
			existing = frappe.db.exists(
				"Student Attendance",
				{"student": student_id, "attendance_session": attendance_session, "docstatus": ("<", 2)},
			)
		else:
			existing = frappe.db.exists(
				"Student Attendance",
				{
					"student": student_id,
					"attendance_date": date,
					"based_on": based_on,
					"course_schedule": course_schedule,
					"class_schedule": class_schedule,
					"office_hours_group": office_hours_group,
					"docstatus": ("<", 2),
				},
			)

		if existing:
			doc = frappe.get_doc("Student Attendance", existing)
			doc.status = status
			doc.source = "Manual"  # Upgrade from Auto placeholder to explicitly marked
			doc.save()
			return "updated"

		frappe.get_doc(
			{
				"doctype": "Student Attendance",
				"student": student_id,
				"attendance_date": date,
				"date": date,
				"status": status,
				"based_on": based_on,
				"attendance_based_on": based_on,
				"course_schedule": course_schedule,
				"class_schedule": class_schedule,
				"office_hours_group": office_hours_group,
				"program": program,
				"course": course,
				"course_offer": course_offering,
				"academic_year": office_group.academic_year if office_group else None,
				"academic_term": office_group.academic_term if office_group else None,
				"attendance_session": attendance_session,
				"instructor": _faculty_display_name(
					schedule.instructor if schedule else class_sched.instructor if class_sched else office_instructor
				),
				"room": schedule.room if schedule else None,
				"source": "Manual",
				"session_type": "Office Hour" if based_on == "Office Hours" else "Lecture",
			}
		).insert()
		return "created"

	created, updated, errors = 0, 0, []
	affected_students = set()

	for row in students_present:
		try:
			student_id = row.get("student")
			result = upsert(student_id, "Present")
			created += result == "created"
			updated += result == "updated"
			affected_students.add(student_id)
		except Exception as e:
			errors.append(f"{row.get('student')}: {e!s}")

	for row in students_absent:
		try:
			student_id = row.get("student")
			result = upsert(student_id, "Absent")
			created += result == "created"
			updated += result == "updated"
			affected_students.add(student_id)
		except Exception as e:
			errors.append(f"{row.get('student')}: {e!s}")

	# ---------------------------------------------------------
	# Trigger Session Summary Update AND Student Calculation
	# ---------------------------------------------------------
	if attendance_session:
		try:
			session_doc = frappe.get_doc("Attendance Session", attendance_session)
			if session_doc.session_status != "Conducted":
				session_doc.session_status = "Conducted"
			session_doc.flags.from_student_attendance = True
			session_doc.update_attendance_summary()
			session_doc.save(ignore_permissions=True)
		except Exception as e:
			# Don't fail the whole request if summary update fails, just log it
			frappe.log_error(message=f"Failed to update summary for session {attendance_session}: {e!s}", title="Update Session Summary Error")
	
	# Trigger individual student calculation if Course Offering is known
	if course_offering:
		from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
		for student_id in affected_students:
			try:
				calculate_student_attendance(student_id, course_offering)
			except Exception as e:
				frappe.log_error(message=f"Failed to calculate attendance for {student_id}: {e!s}", title="Attendance Calculation Error")

	# ---------------------------------------------------------

	return {
		"status": "success",
		"created": created,
		"updated": updated,
		"errors": errors,
	}


@frappe.whitelist()
def get_students_from_class_schedule(class_schedule, attendance_date=None):
	"""Return active students for a Time Table entry with their existing attendance status."""
	from slcm.slcm.doctype.student_attendance_tool.student_attendance_tool import (
		get_student_attendance_records,
	)
	return get_student_attendance_records(
		based_on="Time Table",
		date=attendance_date,
		class_schedule=class_schedule,
	)


@frappe.whitelist()
def get_students_from_office_hours(office_hours_group, attendance_date=None):
	"""Return active students for an Office Hours Group with their existing attendance status."""
	from slcm.slcm.doctype.student_attendance_tool.student_attendance_tool import (
		get_student_attendance_records,
	)
	return get_student_attendance_records(
		based_on="Office Hours",
		date=attendance_date,
		office_hours_group=office_hours_group,
	)
