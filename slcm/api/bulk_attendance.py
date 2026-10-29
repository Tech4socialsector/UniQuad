# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import time_diff_in_hours, get_datetime

from slcm.slcm.utils.attendance_lock import assert_session_editable


@frappe.whitelist()
def get_faculty_context():
	"""Return the logged-in faculty's name and their assigned Classes."""
	user = frappe.session.user
	roles = set(frappe.get_roles(user))

	is_faculty = "slcm_Faculty" in roles
	is_admin = bool(
		{"System Manager", "slcm_Registrar", "slcm_Programme Chair", "Accounts User"} & roles
	)

	faculty_name = None
	faculty_full_name = None
	assigned_classes = []

	if is_faculty:
		faculty_name = frappe.db.get_value("Faculty", {"user_id": user}, "name")
		if faculty_name:
			fn = frappe.db.get_value("Faculty", faculty_name, ["first_name", "last_name"], as_dict=True) or {}
			faculty_full_name = " ".join(filter(None, [fn.get("first_name"), fn.get("last_name")]))

			class_fields = ["name", "course", "course_name", "academic_year", "academic_term", "programme"]
			primary = frappe.get_all(
				"Classes",
				filters={"faculty": faculty_name},
				fields=class_fields,
			)
			seen = {c["name"] for c in primary}

			via_schedule = frappe.get_all(
				"Course Schedule",
				filters={"instructor": faculty_name, "docstatus": ["<", 2]},
				pluck="class_name",
			)
			via_timetable = frappe.get_all(
				"Time Table",
				filters={"instructor": faculty_name, "docstatus": ["<", 2]},
				pluck="class_name",
			)
			extra_names = {n for n in (via_schedule + via_timetable) if n and n not in seen}
			if extra_names:
				extra = frappe.get_all(
					"Classes",
					filters={"name": ["in", list(extra_names)]},
					fields=class_fields,
				)
				primary.extend(extra)

			assigned_classes = primary

	return {
		"is_faculty": is_faculty,
		"is_admin": is_admin,
		"faculty_name": faculty_name,
		"faculty_full_name": faculty_full_name,
		"assigned_classes": assigned_classes,
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


def _find_class(course, program, academic_year=None, academic_term=None, section=None):
	"""Look up the Class for a given course/programme, optionally narrowed by
	academic year, term and section. Most specific match wins; the newest
	class is taken when several match."""
	if not course or not program:
		return None

	filters = {"course": course, "programme": program}
	if academic_year:
		filters["academic_year"] = academic_year
	if academic_term:
		filters["academic_term"] = academic_term
	if section:
		filters["section"] = section

	# Relax the narrowing filters one at a time (common data-mismatch sources)
	for drop in (None, "section", "academic_term", "academic_year"):
		if drop:
			filters.pop(drop, None)
		found = frappe.get_all("Classes", filters=filters, pluck="name", order_by="creation desc", limit=1)
		if found:
			return found[0]

	return None


def _get_or_create_attendance_session(attendance_date, class_name, based_on):
	"""
	Find or create an Attendance Session for this date/class, so that the
	calculator has a denominator (conducted class hours) for the percentage.
	Returns the session name or None on failure.
	"""
	if not class_name:
		return None

	filters = {
		"session_date": attendance_date,
		"class_name": class_name,
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
			"class_name": class_name,
			"course": frappe.db.get_value("Classes", class_name, "course"),
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
			message=f"Failed to create Attendance Session for {class_name} on {attendance_date}: {e!s}",
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

	class_name = schedule.class_name
	if not class_name:
		frappe.throw(_("Class is required on the Course Schedule"))

	from slcm.slcm.doctype.classes.classes import get_class_students

	students = [s.student for s in get_class_students(class_name)]

	if not students:
		frappe.throw(_("No active students found"))

	if isinstance(attendance_data, str):
		attendance_data = json.loads(attendance_data)

	# Ensure an Attendance Session exists so the calculator has a denominator
	attendance_session = _get_or_create_attendance_session(
		attendance_date, class_name, "Course Schedule"
	)
	if attendance_session:
		assert_session_editable(attendance_session)

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
				if class_name and not doc.class_name:
					doc.class_name = class_name
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
						"class_name": class_name,
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
	if class_name:
		from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
		for student in students:
			try:
				calculate_student_attendance(student, class_name)
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
		"message": f"Attendance marked. {'Attendance Summary updated.' if class_name else 'Could not find the Class — Attendance Summary not updated.'}",
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
	# has programme / class_name / academic year & term but no instructor -
	# that is resolved from the Class below.
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

	# Determine the Class — prefer the direct link already stored on
	# whichever source doc this came from (Course Schedule / Time Table /
	# Office Hours Group all carry their own class_name field), so we don't
	# depend on program/course being resolved first.
	class_name = None

	if schedule and schedule.class_name:
		class_name = schedule.class_name
	elif class_sched and class_sched.class_name:
		class_name = class_sched.class_name
	elif office_group and office_group.class_name:
		class_name = office_group.class_name

	# Backfill program/course from the resolved Class when the source doc's
	# own fields were blank (e.g. a Time Table entry created without a Class
	# Configuration has no `programme` value).
	if class_name and (not program or not course):
		class_details = frappe.db.get_value(
			"Classes", class_name, ["programme", "course"], as_dict=True
		)
		if class_details:
			program = program or class_details.programme
			course = course or class_details.course

	# Fallback when nothing above resolved a Class: match course + programme,
	# narrowed by the source's academic year / term / section where known.
	if not class_name and course and program:
		class_name = _find_class(
			course,
			program,
			academic_year=(office_group.academic_year if office_group else class_sched.academic_year if class_sched else None),
			academic_term=(office_group.academic_term if office_group else class_sched.academic_term if class_sched else None),
			section=class_sched.section if class_sched else None,
		)

		if not class_name:
			frappe.log_error(
				title="Class Lookup Failed",
				message=f"Could not find the Class.\nCourse: {course}\nProgram: {program}\nOffice Group: {office_hours_group}"
			)

	office_instructor = None
	if office_group and class_name:
		office_instructor = frappe.db.get_value("Classes", class_name, "faculty")

	# ---------------------------------------------------------
	# Ensure Attendance Session Exists and Update It
	# ---------------------------------------------------------
	attendance_session = None
	
	# Lookup Filters
	session_filters = {
		"session_date": date,
		"docstatus": ("<", 2)
	}
	if class_name:
		session_filters["class_name"] = class_name

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

			# The resolved `class_name` is stored on the session below.

		if start_time and end_time:
			sess_doc = frappe.get_doc({
				"doctype": "Attendance Session",
				"session_date": date,
				"based_on": based_on,
				"class_schedule": class_schedule,
				"class_name": class_name,
				"course": course,
				"section": class_sched.section if class_sched else None,
				"course_schedule": course_schedule if based_on == "Course Schedule" else None,
				"office_hours_group": office_hours_group if based_on == "Office Hours" else None,
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

	# Refuse up front: the per-student loop below only collects errors, so a
	# locked session would otherwise come back as "success".
	if attendance_session:
		assert_session_editable(attendance_session)

	# Each record counts the session's hours (as the Faculty Portal does);
	# without this they keep the 1-hour default whatever the session length.
	session_hours = (
		frappe.db.get_value("Attendance Session", attendance_session, "duration_hours") if attendance_session else None
	) or 1.0

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
			doc.hours_counted = session_hours
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
				"class_name": class_name,
				"academic_year": office_group.academic_year if office_group else None,
				"academic_term": office_group.academic_term if office_group else None,
				"attendance_session": attendance_session,
				"instructor": _faculty_display_name(
					schedule.instructor if schedule else class_sched.instructor if class_sched else office_instructor
				),
				"room": schedule.room if schedule else None,
				"source": "Manual",
				"session_type": "Office Hour" if based_on == "Office Hours" else "Lecture",
				"hours_counted": session_hours,
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
	
	# Trigger individual student calculation if the Class is known
	if class_name:
		from slcm.slcm.utils.attendance_calculator import calculate_student_attendance
		for student_id in affected_students:
			try:
				calculate_student_attendance(student_id, class_name)
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
