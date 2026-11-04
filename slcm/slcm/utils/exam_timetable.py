# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Exam timetable rules for Exam Plan › Course Schedules, on the new academic flow.

* Venues are Venue Master rooms, shared with the class Time Table: an exam and a
  class can't use a room at the same time (checked from both sides).
* Several papers may share a room (exam halls usually do) as long as their
  students fit its seats.
* Students of a course are the Enrolled students of the Classes teaching it in
  the plan's Academic Term; two exams of the same students can't overlap.
* A course may sit in several rooms (classroom allocation sheet): a row with
  ID Nos. From / To takes the students whose Student ID is in that range, the
  course's other rows share the students no range covers.
* Exams fall inside the Academic Term and not on a holiday / weekly off of the
  Institutional Calendar.
* The invigilator teaching a class at the same time is only a warning.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, formatdate, getdate, to_timedelta


def _overlaps(start1, end1, start2, end2):
	return to_timedelta(start1) < to_timedelta(end2) and to_timedelta(end1) > to_timedelta(start2)


def _slot(row):
	return f"{str(row.start_time)[:5]}–{str(row.end_time)[:5]}"


# Exam Plan child tables holding exam sittings, by kind
EXAM_TABLES = {"exam": "Exam Course Schedule", "reexam": "Exam Reexam Schedule"}


def get_exam_bookings(venue=None, start_date=None, end_date=None, exclude_plan=None, exclude_kind=None):
	"""Exam and re-exam sittings (with date, times and venue) of every Exam Plan.
	exclude_plan with exclude_kind leaves out that plan's rows of that kind only;
	exclude_plan alone leaves out all of the plan's rows."""
	conditions = ["ecs.parenttype = 'Exam Plan'", "ecs.exam_date IS NOT NULL",
	              "ecs.start_time IS NOT NULL", "ecs.end_time IS NOT NULL", "IFNULL(ecs.venue, '') != ''"]
	values = {}
	if venue:
		conditions.append("ecs.venue = %(venue)s")
		values["venue"] = venue
	if start_date:
		conditions.append("ecs.exam_date >= %(start)s")
		values["start"] = getdate(start_date)
	if end_date:
		conditions.append("ecs.exam_date <= %(end)s")
		values["end"] = getdate(end_date)
	rows = []
	for kind, table in EXAM_TABLES.items():
		cond = list(conditions)
		if exclude_plan and (not exclude_kind or exclude_kind == kind):
			cond.append("ecs.parent != %(plan)s")
			values["plan"] = exclude_plan
		rows += frappe.db.sql(
			f"""
			SELECT ecs.parent AS exam_plan, ecs.name, ecs.idx, ecs.course, ecs.exam_date,
			       ecs.start_time, ecs.end_time, ecs.venue, ecs.invigilator, ep.term, %(kind)s AS kind
			FROM `tab{table}` ecs
			JOIN `tabExam Plan` ep ON ep.name = ecs.parent
			WHERE {" AND ".join(cond)}
			""",
			dict(values, kind=kind),
			as_dict=True,
		)
	return rows


def exam_booking_clash(venue, date, from_time, to_time):
	"""The exam using `venue` at an overlapping time on `date`, else None.
	Used by the class Time Table so classes are not put in an exam room."""
	if not (venue and date and from_time and to_time):
		return None
	for row in get_exam_bookings(venue, date, date):
		if _overlaps(from_time, to_time, row.start_time, row.end_time):
			return row
	return None


def exam_bookings_by_date(venue, start_date, end_date):
	"""{date: [rows with from_time / to_time / course / name]} of exams in a venue,
	shaped like Time Table rows for the recurring-schedule pre-check."""
	out = {}
	for row in get_exam_bookings(venue, start_date, end_date):
		out.setdefault(getdate(row.exam_date), []).append(frappe._dict(
			name=f"Exam: {row.exam_plan}", from_time=row.start_time, to_time=row.end_time,
			course=row.course, title=f"Exam · {row.course}",
		))
	return out


def course_students(course, academic_term):
	"""Students (Student Master) of the Classes teaching the course in the term."""
	return set(frappe.db.sql_list(
		"""
		SELECT DISTINCT se.student
		FROM `tabClasses` cl
		JOIN `tabClass Enrolled Student` ces ON ces.parent = cl.name AND ces.parenttype = 'Classes'
		JOIN `tabStudent Enrollment` se ON se.name = ces.student_enrollment
		WHERE cl.course = %s AND cl.academic_term = %s AND ces.status = 'Enrolled'
		  AND IFNULL(se.student, '') != ''
		""",
		(course, academic_term),
	))


def course_student_ids(course, academic_term):
	"""{student: Student ID} of the Classes teaching the course in the term."""
	return dict(frappe.db.sql(
		"""
		SELECT DISTINCT se.student, IFNULL(sm.registration_id, '')
		FROM `tabClasses` cl
		JOIN `tabClass Enrolled Student` ces ON ces.parent = cl.name AND ces.parenttype = 'Classes'
		JOIN `tabStudent Enrollment` se ON se.name = ces.student_enrollment
		LEFT JOIN `tabStudent Master` sm ON sm.name = se.student
		WHERE cl.course = %s AND cl.academic_term = %s AND ces.status = 'Enrolled'
		  AND IFNULL(se.student, '') != ''
		""",
		(course, academic_term),
	))


# A Student ID at the start of an "ID Nos." cell: B26001, L25112 & Re-admitted…, LLB/2845/22
_ID = re.compile(r"[A-Za-z]*[/-]?\d[A-Za-z0-9/-]*")


def id_token(text):
	m = _ID.match((text or "").strip())
	return m.group(0).upper() if m else None


def _in_range(student_id, lo, hi):
	sid = (student_id or "").strip().upper()
	if not sid:
		return False
	if hi:
		return lo <= sid <= hi
	# "From" only (e.g. "B24266, Re-admitted students"): that ID onwards, same ID pattern
	prefix = re.match(r"[A-Z/]*", lo).group(0)
	return sid >= lo and sid.startswith(prefix) and len(sid) == len(lo)


def split_by_id_range(rows, student_ids):
	"""Students of each row of one course, in row order: a row whose ID Nos.
	From starts with a Student ID gets the students in From–To; the other rows
	(All students, PWD students…) share the students no range covers."""
	out, ranged = [], set()
	for r in rows:
		lo, hi = id_token(r.get("id_from")), id_token(r.get("id_to"))
		if lo and hi and hi < lo:
			lo, hi = hi, lo
		if lo:
			got = {s for s, sid in student_ids.items() if _in_range(sid, lo, hi)}
			ranged |= got
			out.append(got)
		else:
			out.append(None)
	rest = set(student_ids) - ranged
	return [rest if got is None else got for got in out]


def reexam_students(exam_plan, course):
	"""Students registered (not cancelled) for the course's re-exam or improvement
	exam in the plan: both sit to the re-exam timetable."""
	students = set()
	for doctype in ("Re Exam Registration", "Improvement Exam Registration"):
		students |= set(frappe.get_all(
			doctype, filters={"exam_plan": exam_plan, "course": course, "status": "Registered"}, pluck="student"))
	return students


def reexam_student_ids(exam_plan, course):
	"""{student: Student ID} of the students registered for the course's re-exam."""
	students = list(reexam_students(exam_plan, course))
	return dict(frappe.get_all("Student Master", filters={"name": ["in", students or [""]]},
	                           fields=["name", "registration_id"], as_list=True))


def _faculty_label(faculty):
	if not faculty:
		return ""
	first, last = frappe.db.get_value("Faculty", faculty, ["first_name", "last_name"]) or (None, None)
	return " ".join(filter(None, [first, last])) or str(faculty)


def check_exam_schedule(plan, reexam=False):
	"""Check an Exam Plan's course schedule rows (or, with reexam, its re-exam
	rows). Returns {"errors": [...], "warnings": [...]}; each item is
	{"row", "course", "message"}. Re-exams usually fall after the term, so the
	term-dates rule is skipped for them, and their students are the ones
	registered for the re-exam."""
	from slcm.slcm.doctype.institutional_calendar.institutional_calendar import (
		get_non_teaching_dates_in_range,
	)

	errors, warnings = [], []

	def add(bucket, row, message):
		bucket.append({"row": row.idx, "course": row.course, "message": message})

	term_start = term_end = None
	if plan.term:
		term_start, term_end = frappe.db.get_value(
			"Academic Term", plan.term, ["term_start_date", "term_end_date"]
		) or (None, None)

	kind = "reexam" if reexam else "exam"
	rows = [r for r in (plan.reexam_schedules if reexam else plan.course_schedules) if r.course]
	timed = []
	for row in rows:
		if row.start_time and row.end_time and to_timedelta(row.end_time) <= to_timedelta(row.start_time):
			add(errors, row, _("End time must be after start time."))
			continue
		if not reexam and row.exam_date and term_start and term_end and not (getdate(term_start) <= getdate(row.exam_date) <= getdate(term_end)):
			add(errors, row, _("{0} is outside {1} ({2} – {3}).").format(
				formatdate(row.exam_date), plan.term, formatdate(term_start), formatdate(term_end)))
			continue
		if row.exam_date and row.start_time and row.end_time:
			timed.append(row)

	if not timed:
		return {"errors": errors, "warnings": warnings}

	dates = sorted(getdate(r.exam_date) for r in timed)
	non_teaching = get_non_teaching_dates_in_range(dates[0], dates[-1])
	students = {}

	def students_of(course, term, row_kind=kind, exam_plan=plan.name):
		key = (course, term, row_kind, exam_plan)
		if key not in students:
			if row_kind == "reexam":
				students[key] = reexam_students(exam_plan, course)
			else:
				students[key] = course_students(course, term) if term else set()
		return students[key]

	# This plan's rows: a course split over rooms by Student ID range
	by_course, row_students = {}, {}
	if reexam or plan.term:
		for r in timed:
			by_course.setdefault(r.course, []).append(r)
		for course, group in by_course.items():
			ids = reexam_student_ids(plan.name, course) if reexam else course_student_ids(course, plan.term)
			for r, got in zip(group, split_by_id_range(group, ids)):
				row_students[id(r)] = got

	def students_of_row(r):
		if r.get("other"):
			return students_of(r.course, r.term, r.kind, r.exam_plan)
		if id(r) in row_students:
			return row_students[id(r)]
		return students_of(r.course, plan.term)

	# Other sittings on the same dates: other plans, and this plan's other kind (rooms, students, invigilators)
	others = [
		frappe._dict(r, idx=None, other=True)
		for r in get_exam_bookings(start_date=dates[0], end_date=dates[-1], exclude_plan=plan.name, exclude_kind=kind)
	]

	for row in timed:
		day = getdate(row.exam_date)
		if day in non_teaching:
			add(errors, row, _("{0} is a non-teaching day ({1}) in the Institutional Calendar.").format(
				formatdate(row.exam_date), non_teaching[day]))

		if row.venue:
			# A class in the room at the same time
			for tt in frappe.get_all(
				"Time Table",
				filters={"venue": row.venue, "schedule_date": row.exam_date, "docstatus": ["<", 2], "is_cancelled": 0},
				fields=["name", "from_time", "to_time", "course", "title"],
			):
				if _overlaps(row.start_time, row.end_time, tt.from_time, tt.to_time):
					add(errors, row, _("{0} has a class ({1}, {2}–{3}) at this time.").format(
						row.venue, tt.title or tt.course, str(tt.from_time)[:5], str(tt.to_time)[:5]))
					break

			# Seats: every paper sitting in the room at an overlapping time
			sharing = [r for r in timed + others
			           if r is not row and r.venue == row.venue and getdate(r.exam_date) == day
			           and _overlaps(row.start_time, row.end_time, r.start_time, r.end_time)]
			seats = cint(row.seat_capacity) or cint(frappe.db.get_value("Venue Master", row.venue, "capacity"))
			needed = len(students_of_row(row).union(*[students_of_row(r) for r in sharing]))
			if seats and needed > seats:
				together = _(" together with {0}").format(", ".join(sorted({r.course for r in sharing}))) if sharing else ""
				add(errors, row, _("{0} students{1} but {2} has {3} seats.").format(needed, together, row.venue, seats))

		if row.invigilator:
			for tt in frappe.get_all(
				"Time Table",
				filters={"instructor": row.invigilator, "schedule_date": row.exam_date, "docstatus": ["<", 2], "is_cancelled": 0},
				fields=["from_time", "to_time", "course", "title"],
			):
				if _overlaps(row.start_time, row.end_time, tt.from_time, tt.to_time):
					add(warnings, row, _("Invigilator {0} teaches {1} at {2}–{3}.").format(
						_faculty_label(row.invigilator), tt.title or tt.course, str(tt.from_time)[:5], str(tt.to_time)[:5]))
					break

	# Same students in two exams at the same time (this plan, and other plans of the term)
	pool = timed + [o for o in others if o.term == plan.term or o.kind == "reexam" or reexam]
	for i, a in enumerate(timed):
		for b in pool[i + 1:]:
			if getdate(a.exam_date) != getdate(b.exam_date):
				continue
			if not _overlaps(a.start_time, a.end_time, b.start_time, b.end_time):
				continue
			common = students_of_row(a) & students_of_row(b) if a.course != b.course else None
			if common:
				where = (_(" (re-exam)") if b.get("kind") == "reexam" else "") + (
					_(" (Exam Plan {0})").format(b.exam_plan) if b.get("other") and b.exam_plan != plan.name else "")
				add(errors, a, _("{0} student(s) also sit {1}{2} at {3} on {4}.").format(
					len(common), b.course, where, _slot(b), formatdate(b.exam_date)))
			# one invigilator may watch every paper in a room, not two rooms
			if a.invigilator and a.invigilator == b.invigilator and a.venue != b.venue:
				add(errors, a, _("Invigilator {0} is also on duty for {1} at {2}.").format(
					_faculty_label(a.invigilator), b.course, _slot(b)))

	return {"errors": errors, "warnings": warnings}


@frappe.whitelist()
def preview_exam_schedule(exam_plan, rows=None):
	"""Check unsaved schedule rows for the Exam Plan page (nothing is saved)."""
	import json

	frappe.has_permission("Exam Plan", "read", doc=exam_plan, throw=True)
	plan = frappe.get_doc("Exam Plan", exam_plan)
	if rows is not None:
		plan.set("course_schedules", json.loads(rows) if isinstance(rows, str) else rows)
		for i, r in enumerate(plan.course_schedules, 1):
			r.idx = i
	return check_exam_schedule(plan)
