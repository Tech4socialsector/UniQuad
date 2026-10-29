# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Exam timetable rules for Exam Plan › Course Schedules, on the new academic flow.

* Venues are Venue Master rooms, shared with the class Time Table: an exam and a
  class can't use a room at the same time (checked from both sides).
* Several papers may share a room (exam halls usually do) as long as their
  students fit its seats.
* Students of a course are the Enrolled students of the Classes teaching it in
  the plan's Academic Term; two exams of the same students can't overlap.
* Exams fall inside the Academic Term and not on a holiday / weekly off of the
  Institutional Calendar.
* The invigilator teaching a class at the same time is only a warning.
"""

import frappe
from frappe import _
from frappe.utils import cint, formatdate, getdate, to_timedelta


def _overlaps(start1, end1, start2, end2):
	return to_timedelta(start1) < to_timedelta(end2) and to_timedelta(end1) > to_timedelta(start2)


def _slot(row):
	return f"{str(row.start_time)[:5]}–{str(row.end_time)[:5]}"


def get_exam_bookings(venue=None, start_date=None, end_date=None, exclude_plan=None):
	"""Exam Course Schedule rows (with date, times and venue) of every Exam Plan."""
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
	if exclude_plan:
		conditions.append("ecs.parent != %(plan)s")
		values["plan"] = exclude_plan
	return frappe.db.sql(
		f"""
		SELECT ecs.parent AS exam_plan, ecs.name, ecs.idx, ecs.course, ecs.exam_date,
		       ecs.start_time, ecs.end_time, ecs.venue, ecs.invigilator, ep.term
		FROM `tabExam Course Schedule` ecs
		JOIN `tabExam Plan` ep ON ep.name = ecs.parent
		WHERE {" AND ".join(conditions)}
		""",
		values,
		as_dict=True,
	)


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


def _faculty_label(faculty):
	if not faculty:
		return ""
	first, last = frappe.db.get_value("Faculty", faculty, ["first_name", "last_name"]) or (None, None)
	return " ".join(filter(None, [first, last])) or str(faculty)


def check_exam_schedule(plan):
	"""Check an Exam Plan's course schedule rows. Returns {"errors": [...],
	"warnings": [...]}; each item is {"row", "course", "message"}."""
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

	rows = [r for r in plan.course_schedules if r.course]
	timed = []
	for row in rows:
		if row.start_time and row.end_time and to_timedelta(row.end_time) <= to_timedelta(row.start_time):
			add(errors, row, _("End time must be after start time."))
			continue
		if row.exam_date and term_start and term_end and not (getdate(term_start) <= getdate(row.exam_date) <= getdate(term_end)):
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

	def students_of(course, term):
		key = (course, term)
		if key not in students:
			students[key] = course_students(course, term) if term else set()
		return students[key]

	# Exams of other plans in the same dates (rooms, students, invigilators)
	others = [
		frappe._dict(r, idx=None, other=True)
		for r in get_exam_bookings(start_date=dates[0], end_date=dates[-1], exclude_plan=plan.name)
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
				filters={"venue": row.venue, "schedule_date": row.exam_date, "docstatus": ["<", 2]},
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
			needed = len(students_of(row.course, plan.term).union(
				*[students_of(r.course, r.term if r.get("other") else plan.term) for r in sharing]))
			if seats and needed > seats:
				together = _(" together with {0}").format(", ".join(sorted({r.course for r in sharing}))) if sharing else ""
				add(errors, row, _("{0} students{1} but {2} has {3} seats.").format(needed, together, row.venue, seats))

		if row.invigilator:
			for tt in frappe.get_all(
				"Time Table",
				filters={"instructor": row.invigilator, "schedule_date": row.exam_date, "docstatus": ["<", 2]},
				fields=["from_time", "to_time", "course", "title"],
			):
				if _overlaps(row.start_time, row.end_time, tt.from_time, tt.to_time):
					add(warnings, row, _("Invigilator {0} teaches {1} at {2}–{3}.").format(
						_faculty_label(row.invigilator), tt.title or tt.course, str(tt.from_time)[:5], str(tt.to_time)[:5]))
					break

	# Same students in two exams at the same time (this plan, and other plans of the term)
	pool = timed + [o for o in others if o.term == plan.term]
	for i, a in enumerate(timed):
		for b in pool[i + 1:]:
			if getdate(a.exam_date) != getdate(b.exam_date) or a.course == b.course:
				continue
			if not _overlaps(a.start_time, a.end_time, b.start_time, b.end_time):
				continue
			common = students_of(a.course, plan.term) & students_of(b.course, plan.term)
			if common:
				where = _(" (Exam Plan {0})").format(b.exam_plan) if b.get("other") else ""
				add(errors, a, _("{0} student(s) also sit {1}{2} at {3} on {4}.").format(
					len(common), b.course, where, _slot(b), formatdate(b.exam_date)))
			if a.invigilator and a.invigilator == b.invigilator:
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
