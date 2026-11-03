# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Time Table for a Class, from the Classes form (public/js/class_time_table.js).

Create Time Table: one Time Table series for the class and, optionally, its
Class Participation - the class's students split into one Class-Participation
Student Group per week, mapped onto the series' Class Participation Week table
(see slcm.slcm.utils.class_participation).

View Time Table: the class's sessions on a calendar; a session shows its
attendance and the class participation recorded for it.
"""

import base64
import io
import json

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import cint, flt, formatdate, get_datetime, getdate, now_datetime, to_timedelta

from slcm.slcm.doctype.classes.classes import get_class_students
from slcm.slcm.doctype.time_table.time_table import format_time_12h, publish_bulk_progress

# Progress labels shown by the Create Time Table dialog
CP_PROGRESS_LABEL = "Creating Class Participation groups"
UPLOAD_PROGRESS_LABEL = "Reading"

REPEAT_STEP = {
	"Daily": relativedelta(days=1),
	"Weekly": relativedelta(weeks=1),
	"Monthly": relativedelta(months=1),
}


def _get_class(class_name):
	cls = frappe.db.get_value(
		"Classes",
		class_name,
		["name", "class_type", "course", "course_name", "programme", "section", "group_name",
		 "academic_year", "academic_term", "faculty", "faculty_name"],
		as_dict=True,
	)
	if not cls:
		frappe.throw(_("Class {0} does not exist.").format(class_name))
	return cls


def _class_roster(class_name):
	"""Class students with their Student ID, alphabetical."""
	students = get_class_students(class_name)
	ids = dict(frappe.get_all(
		"Student Master",
		filters={"name": ["in", [s.student for s in students] or [""]]},
		fields=["name", "registration_id"],
		as_list=True,
	))
	for s in students:
		s.student_id = ids.get(s.student) or ""
	return students


@frappe.whitelist()
def get_class_time_table_info(class_name):
	"""What both dialogs start from: the class, its term dates, its students
	and the Time Table entries it already has."""
	frappe.has_permission("Time Table", "read", throw=True)
	cls = _get_class(class_name)
	term = frappe.db.get_value(
		"Academic Term", cls.academic_term, ["term_name", "term_start_date", "term_end_date"], as_dict=True
	) or frappe._dict()

	entries = frappe.get_all(
		"Time Table",
		filters={"class_name": class_name, "docstatus": ["<", 2]},
		fields=["schedule_date"],
		order_by="schedule_date asc",
	)
	today = getdate()
	upcoming = [e.schedule_date for e in entries if getdate(e.schedule_date) >= today]

	return {
		"class": cls,
		"term_name": term.term_name or cls.academic_term,
		"term_start_date": term.term_start_date,
		"term_end_date": term.term_end_date,
		"holidays": _term_holidays(term.term_start_date, term.term_end_date),
		"students": _class_roster(class_name),
		"entry_count": len(entries),
		"first_date": entries[0].schedule_date if entries else None,
		"last_date": entries[-1].schedule_date if entries else None,
		"next_date": upcoming[0] if upcoming else None,
	}


def _term_holidays(start, end):
	"""Institutional Calendar holidays overlapping the term; classes on them are
	skipped (see _check_dates)."""
	if not (start and end):
		return []
	return frappe.get_all(
		"Institutional Calendar",
		filters={
			"entry_type": "Holiday",
			"start_date": ["<=", end],
			"end_date": [">=", start],
			"status": ["!=", "Inactive"],
			"docstatus": ["<", 2],
		},
		fields=["name1", "start_date", "end_date"],
		order_by="start_date asc",
	)


def _series_dates(schedule_date, repeat_frequency, repeats_till):
	start = getdate(schedule_date)
	step = REPEAT_STEP.get(repeat_frequency)
	if not step or not repeats_till:
		return [start]
	till, dates, i = getdate(repeats_till), [], 0
	while start + step * i <= till:
		dates.append(start + step * i)
		i += 1
	return dates


def _overlaps(start1, end1, start2, end2):
	return to_timedelta(start1) < to_timedelta(end2) and to_timedelta(end1) > to_timedelta(start2)


@frappe.whitelist()
def preview_class_time_table(data):
	"""Every date the series would have, and what happens to it: created, or
	skipped for a holiday / weekly off, a venue booking or the faculty's other
	class (the same rules Time Table applies when it creates the series). A
	problem on the first date blocks the whole series, so it is an error."""
	data = frappe._dict(json.loads(data) if isinstance(data, str) else data)
	frappe.has_permission("Time Table", "read", throw=True)
	if not (data.schedule_date and data.from_time and data.to_time):
		return {"dates": [], "errors": []}
	return _check_dates(_series_dates(data.schedule_date, data.repeat_frequency, data.repeats_till), data)


def _check_dates(dates, data, exclude=()):
	"""Status of each date for data's venue, faculty and time; Time Table
	entries named in `exclude` (the ones being edited) do not count as taken."""
	from slcm.slcm.doctype.institutional_calendar.institutional_calendar import (
		get_non_teaching_dates_in_range,
	)

	dates = sorted(getdate(d) for d in dates)
	if not dates:
		return {"dates": [], "errors": []}
	non_teaching = get_non_teaching_dates_in_range(dates[0], dates[-1])

	busy = {}
	for field in ("venue", "instructor"):
		if not data.get(field):
			continue
		# A cancelled session has given up its slot
		filters = {field: data.get(field), "schedule_date": ["between", [dates[0], dates[-1]]], "docstatus": ["<", 2], "is_cancelled": 0}
		if exclude:
			filters["name"] = ["not in", list(exclude)]
		for row in frappe.get_all(
			"Time Table",
			filters=filters,
			fields=["schedule_date", "from_time", "to_time", "course", "title"],
		):
			if _overlaps(data.from_time, data.to_time, row.from_time, row.to_time):
				busy.setdefault((field, getdate(row.schedule_date)), row)
	if data.get("venue"):
		# Exams booked in the room count like another session
		from slcm.slcm.utils.exam_timetable import exam_bookings_by_date

		for day, rows in exam_bookings_by_date(data.venue, dates[0], dates[-1]).items():
			for row in rows:
				if _overlaps(data.from_time, data.to_time, row.from_time, row.to_time):
					busy.setdefault(("venue", day), row)

	def slot(row):
		return f"{format_time_12h(row.from_time)} – {format_time_12h(row.to_time)}"

	def session(row):
		return row.title or row.course or _("another session")

	rows, errors = [], []
	for i, d in enumerate(dates):
		status, note = "ok", ""
		day = formatdate(d, "EEEE, dd MMMM yyyy")
		if d in non_teaching:
			status, note = "holiday", _("Non-teaching day: {0}").format(non_teaching[d])
			if i == 0:
				errors.append(_(
					"{0} is a non-teaching day ({1}) as per the Institutional Calendar. "
					"Kindly choose a working day for the first session of this class."
				).format(frappe.bold(day), non_teaching[d]))
		elif (clash := busy.get(("venue", d))):
			status = "venue"
			note = _("Venue already reserved for {0} ({1})").format(session(clash), slot(clash))
			if i == 0:
				errors.append(_(
					"The venue {0} is already reserved on {1} for the {2} time slot ({3}). "
					"Kindly choose a different date, time slot or venue for this class."
				).format(frappe.bold(data.venue), frappe.bold(day), slot(clash), frappe.bold(session(clash))))
		elif (clash := busy.get(("instructor", d))):
			# Only a venue clash blocks a date; the faculty's other session is a
			# warning (the session is still created, as in Time Table).
			status = "faculty_warn"
			note = _("Faculty already engaged in {0} ({1})").format(session(clash), slot(clash))
		rows.append({"date": str(d), "date_fmt": formatdate(d, "EEE, dd MMM yyyy"), "status": status, "note": note})
	return {"dates": rows, "errors": errors}


@frappe.whitelist()
def create_class_time_table(data):
	"""Create the class's Time Table series and, when asked, its Class
	Participation groups (one Student Group per week) in one go - if anything
	fails nothing is kept.

	data: class_name, schedule_date, from_time, to_time, venue, instructor,
	repeat_frequency, repeats_till, title, color, and
	cp_weeks: [{start_date, end_date, students: [Student Master]}]."""
	data = frappe._dict(json.loads(data) if isinstance(data, str) else data)
	frappe.has_permission("Time Table", "create", throw=True)
	cls = _get_class(data.class_name)

	doc = frappe.get_doc({
		"doctype": "Time Table",
		"based_on": "Class",
		"class_name": cls.name,
		"instructor": data.instructor or cls.faculty,
		"schedule_date": data.schedule_date,
		"from_time": data.from_time,
		"to_time": data.to_time,
		"venue": data.venue,
		"repeat_frequency": data.repeat_frequency or "Never",
		"repeats_till": data.repeats_till if data.repeat_frequency not in (None, "", "Never") else None,
		"title": data.title,
		"color": data.color,
	})

	groups = []
	weeks = [w for w in (data.cp_weeks or []) if w.get("students")]
	if weeks:
		roster = {s.student: s.student_id for s in _class_roster(cls.name)}
		label = " ".join(filter(None, [cls.course_name, cls.section or cls.group_name]))
		publish_bulk_progress(CP_PROGRESS_LABEL, 0, len(weeks))
		for i, week in enumerate(weeks, start=1):
			week = frappe._dict(week)
			outside = [s for s in week.students if s not in roster]
			if outside:
				frappe.throw(_("Week {0}: {1} is not a student of class {2}.").format(i, outside[0], cls.name))
			group = frappe.get_doc({
				"doctype": "Student Group",
				"group_based_on": "Class-Participation",
				"academic_year": cls.academic_year,
				"academic_term": cls.academic_term,
				"programme": cls.programme,
				"class_name": cls.name,
				"week_name": f"{label} - Week {i}",
				"students": [{"student": s, "student_id": roster[s] or s} for s in week.students],
			})
			# Time Table create permission was checked above; Student Group itself
			# is System Manager only.
			group.insert(ignore_permissions=True)
			groups.append(group.name)
			doc.append("class_participation_week_group", {
				"week": group.name,
				"start_date": week.start_date,
				"end_date": week.end_date,
			})
			publish_bulk_progress(CP_PROGRESS_LABEL, i, len(weeks))

	# after_insert creates the rest of the series and every Attendance Session,
	# publishing "Scheduling" progress as it goes
	doc.insert(ignore_permissions=True)
	occurrences = frappe.db.count("Time Table", {"parent_schedule": doc.name})
	return {"name": doc.name, "sessions": occurrences + 1, "groups": groups}


@frappe.whitelist()
def download_cp_template(class_name, weeks):
	"""xlsx to split the class's students into Class Participation weeks by
	hand: one row per student with the week number to fill in (pre-filled
	with the dialog's current split), and a Weeks sheet with each week's dates.

	weeks: [{start_date, end_date, students: [Student Master]}]."""
	frappe.has_permission("Time Table", "create", throw=True)
	import openpyxl
	from openpyxl.styles import Font, PatternFill

	weeks = frappe.parse_json(weeks) if isinstance(weeks, str) else weeks or []
	week_of = {s: i for i, w in enumerate(weeks, start=1) for s in (w.get("students") or [])}

	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "Students"
	_xlsx_header(ws, ["Row Key", "Student ID", "Student Name", "Week No"], Font, PatternFill)
	for s in _class_roster(class_name):
		ws.append([s.student, s.student_id, s.student_name, week_of.get(s.student)])
	ws.column_dimensions["A"].hidden = True
	for col, width in zip("BCD", [16, 34, 12]):
		ws.column_dimensions[col].width = width

	ref = wb.create_sheet("Weeks")
	_xlsx_header(ref, ["Week No", "Start Date", "End Date"], Font, PatternFill)
	for i, w in enumerate(weeks, start=1):
		ref.append([i, formatdate(w.get("start_date")), formatdate(w.get("end_date"))])
	for col, width in zip("ABC", [10, 14, 14]):
		ref.column_dimensions[col].width = width

	output = io.BytesIO()
	wb.save(output)
	return {
		"filename": f"class_participation_{frappe.scrub(class_name)}.xlsx",
		"content": base64.b64encode(output.getvalue()).decode("utf-8"),
		"mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	}


def _xlsx_header(ws, headers, Font, PatternFill):
	ws.append(headers)
	for ci in range(1, len(headers) + 1):
		cell = ws.cell(row=1, column=ci)
		cell.font = Font(bold=True, color="FFFFFF")
		cell.fill = PatternFill("solid", fgColor="3949AB")


@frappe.whitelist()
def read_cp_upload(class_name, file_url, week_count):
	"""{student: week no} from a filled-in Class Participation template, with
	the rows that could not be used. Rows are matched by the hidden key, else
	by Student ID; the week must be 1..week_count. Reports progress
	(time_table_bulk_progress, label "Reading") as it goes."""
	frappe.has_permission("Time Table", "create", throw=True)
	import openpyxl

	file_doc = frappe.get_doc("File", {"file_url": file_url})
	file_doc.check_permission("read")
	ws = openpyxl.load_workbook(file_doc.get_full_path(), data_only=True).worksheets[0]

	roster = _class_roster(class_name)
	by_key = {s.student: s for s in roster}
	by_id = {str(s.student_id).strip().upper(): s for s in roster if s.student_id}
	week_count = cint(week_count)

	rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if r and any(v not in (None, "") for v in r)]
	assign, problems = {}, []
	step = max(1, len(rows) // 20)
	publish_bulk_progress(UPLOAD_PROGRESS_LABEL, 0, len(rows))
	for n, row in enumerate(rows, start=1):
		key, student_id, name, week = (list(row) + [None] * 4)[:4]
		s = by_key.get(str(key or "").strip()) or by_id.get(str(student_id or "").strip().upper())
		label = student_id or name or key
		if not s:
			problems.append(_("Row {0}: {1} is not a student of this class.").format(n + 1, label))
		elif week in (None, ""):
			problems.append(_("Row {0}: {1} has no Week No.").format(n + 1, s.student_name))
		elif not str(week).strip().isdigit() or not 1 <= cint(week) <= week_count:
			problems.append(_("Row {0}: Week No {1} for {2} must be between 1 and {3}.").format(
				n + 1, week, s.student_name, week_count))
		elif s.student in assign:
			problems.append(_("Row {0}: {1} is listed more than once.").format(n + 1, s.student_name))
		else:
			assign[s.student] = cint(week)
		if n % step == 0 or n == len(rows):
			publish_bulk_progress(UPLOAD_PROGRESS_LABEL, n, len(rows))

	missing = [s.student_name for s in roster if s.student not in assign]
	return {"assign": assign, "problems": problems, "missing": missing}


@frappe.whitelist()
def get_class_schedule_events(class_name, start, end):
	"""The class's Time Table entries between start and end, for the calendar.
	Each carries its attendance state: marked / pending (held, not marked) /
	upcoming / cancelled."""
	frappe.has_permission("Time Table", "read", throw=True)
	rows = frappe.get_all(
		"Time Table",
		filters={
			"class_name": class_name,
			"schedule_date": ["between", [getdate(start), getdate(end)]],
			"docstatus": ["<", 2],
		},
		fields=["name", "title", "course", "schedule_date", "from_time", "to_time", "venue", "instructor", "color", "is_cancelled"],
		order_by="schedule_date asc, from_time asc",
	)
	sessions = {
		s.class_schedule: s
		for s in frappe.get_all(
			"Attendance Session",
			filters={"class_schedule": ["in", [r.name for r in rows] or [""]]},
			fields=["class_schedule", "attendance_marked", "session_status", "present_count", "total_students"],
		)
	}
	now = now_datetime()
	events = []
	for r in rows:
		s = sessions.get(r.name) or frappe._dict()
		start_dt = f"{r.schedule_date} {str(r.from_time).zfill(8)}"
		if r.is_cancelled or s.session_status == "Cancelled":
			state = "cancelled"
		elif cint(s.attendance_marked):
			state = "marked"
		elif get_datetime(start_dt) <= now:
			state = "pending"
		else:
			state = "upcoming"
		events.append({
			"id": r.name,
			"title": r.title or r.course or r.name,
			"start": start_dt,
			"end": f"{r.schedule_date} {str(r.to_time).zfill(8)}",
			"extendedProps": {
				"state": state,
				"color": r.color,
				"venue": r.venue,
				"present": cint(s.present_count),
				"total": cint(s.total_students),
			},
		})
	return events


@frappe.whitelist()
def get_session_details(time_table):
	"""One session of the class: its attendance (every class student and their
	status) and the class participation recorded for its hour."""
	from slcm.slcm.utils.class_participation import get_participation_context, get_participation_roster

	tt = frappe.get_doc("Time Table", time_table)
	tt.check_permission("read")

	faculty = ""
	if tt.instructor:
		f = frappe.db.get_value("Faculty", tt.instructor, ["first_name", "last_name"], as_dict=True)
		faculty = " ".join(filter(None, [f.first_name, f.last_name])) if f else tt.instructor

	info = {
		"name": tt.name,
		"title": tt.title or tt.course,
		"class_name": tt.class_name,
		"date": str(tt.schedule_date),
		"date_fmt": formatdate(tt.schedule_date, "EEEE, dd MMM yyyy"),
		"from_time": str(tt.from_time),
		"to_time": str(tt.to_time),
		"venue": tt.venue,
		"faculty": faculty,
		"is_cancelled": cint(tt.is_cancelled),
		"cancellation_reason": tt.cancellation_reason,
		"is_past": getdate(tt.schedule_date) < getdate(),
	}

	session = None
	session_name = frappe.db.get_value("Attendance Session", {"class_schedule": tt.name}, "name")
	if session_name:
		session = frappe.get_doc("Attendance Session", session_name)

	# Attendance: the class roster, plus anyone already marked who has since left it
	marked = {
		a.student: a.status
		for a in frappe.get_all(
			"Student Attendance",
			filters={"class_schedule": tt.name, "docstatus": ["<", 2]},
			fields=["student", "status"],
		)
	}
	students = _class_roster(tt.class_name) if tt.class_name else []
	in_class = {s.student for s in students}
	extra = [s for s in marked if s not in in_class]
	if extra:
		for m in frappe.get_all(
			"Student Master",
			filters={"name": ["in", extra]},
			fields=["name", "first_name", "last_name", "registration_id"],
		):
			students.append(frappe._dict(
				student=m.name,
				student_name=" ".join(filter(None, [m.first_name, m.last_name])),
				student_id=m.registration_id or "",
			))
	for s in students:
		s.status = marked.get(s.student) or "Not Marked"

	counts = {}
	for s in students:
		counts[s.status] = counts.get(s.status, 0) + 1

	attendance = {
		"session": session_name,
		"session_status": session.session_status if session else None,
		"marked": cint(session.attendance_marked) if session else 0,
		"students": students,
		"counts": counts,
	}

	# Class participation for this session's hour
	participation = {"available": False, "reason": _("This session has no Attendance Session yet.")}
	if session:
		ctx = get_participation_context(session)
		participation = {"available": ctx.available, "reason": ctx.reason}
		if ctx.available:
			roster = get_participation_roster(ctx)
			participation.update(
				group=ctx.group,
				week_name=ctx.week_name,
				slot_label=ctx.slot_label,
				classes_in_week=ctx.classes_in_week,
				start_date_fmt=ctx.get("start_date_fmt"),
				end_date_fmt=ctx.get("end_date_fmt"),
				max_grade=ctx.max_grade,
				recorded=roster["slot_recorded"],
				students=[
					{**s, "attendance": marked.get(s["student"]) or "Not Marked",
					 "grade": flt(s["grade"]) if s["grade"] is not None else None}
					for s in roster["students"]
				],
			)

	return {"info": info, "attendance": attendance, "participation": participation}


# ── Edit one session / this and the following sessions ───────────────────────

EDIT_FIELDS = ("title", "instructor", "venue", "color", "from_time", "to_time")


def _series(tt):
	"""The series root of a Time Table entry and the names of all its entries."""
	root = tt.parent_schedule or tt.name
	names = [root] + frappe.get_all("Time Table", filters={"parent_schedule": root}, pluck="name")
	return frappe.get_doc("Time Table", root), names


@frappe.whitelist()
def get_session_for_edit(time_table):
	"""What the Edit dialog is filled with: the entry's own values, and its
	series' repeat and range (an occurrence itself is stored as 'Never')."""
	tt = frappe.get_doc("Time Table", time_table)
	tt.check_permission("read")
	if tt.is_cancelled:
		frappe.throw(_("This session is cancelled and cannot be edited."))
	root, names = _series(tt)
	dates = frappe.get_all(
		"Time Table", filters={"name": ["in", names], "docstatus": ["<", 2]}, pluck="schedule_date"
	)
	return {
		"name": tt.name,
		"class_name": tt.class_name,
		"title": tt.title,
		"instructor": tt.instructor,
		"venue": tt.venue,
		"color": tt.color,
		"schedule_date": str(tt.schedule_date),
		"from_time": str(tt.from_time).zfill(8),
		"to_time": str(tt.to_time).zfill(8),
		"repeat_frequency": root.repeat_frequency or "Never",
		"repeats_till": str(root.repeats_till) if root.repeats_till else None,
		"series_start": str(min(dates)) if dates else None,
		"series_end": str(max(dates)) if dates else None,
		"following": len([d for d in dates if getdate(d) >= getdate(tt.schedule_date)]),
	}


@frappe.whitelist()
def update_class_time_table(time_table, data, scope):
	"""Save the Edit dialog (scope "this" or "future", see _plan_update). The
	same checks as check_class_time_table_update run again; any problem stops
	the save before anything changes."""
	from slcm.slcm.doctype.time_table.time_table import _apply_updates_to_rows, quiet_bulk_operation

	from slcm.slcm.doctype.class_schedule_log.class_schedule_log import add_log, no_schedule_log

	data = frappe._dict(json.loads(data) if isinstance(data, str) else data)
	tt = frappe.get_doc("Time Table", time_table)
	tt.check_permission("write")
	if tt.is_cancelled:
		frappe.throw(_("This session is cancelled and cannot be edited."))
	plan = _plan_update(tt, data, scope)
	if plan.errors:
		frappe.throw("<br>".join(plan.errors), title=_("Time Slot Unavailable"))
	if plan.cp_outside and not plan.drop_weeks:
		frappe.throw("<br>".join(
			_("Class Participation week {0} ({1}) would fall outside the new schedule.").format(w["idx"], w["dates"])
			for w in plan.cp_outside), title=_("Class Participation Weeks Outside the Schedule"))

	before = {f: tt.get(f) for f in ("schedule_date", "from_time", "to_time", "venue", "instructor", "title")}
	with no_schedule_log():
		if not plan.rebuild:
			_apply_updates_to_rows(plan.following, plan.updates)
		else:
			with quiet_bulk_operation():
				_rebuild_series(tt, plan)
	summary = _plan_summary(plan)
	changes = "; ".join(
		f"{f.replace('_', ' ').title()}: {before[f] or '–'} → {plan.updates[f]}"
		for f in before if f in plan.updates and str(before[f] or "") != str(plan.updates[f] or "")
	)
	if plan.rebuild:
		detail = _("This and following sessions rebuilt: {0} scheduled, {1} kept.").format(summary["create"], summary["keep"])
	elif scope == "this":
		detail = _("This session only.")
	else:
		detail = _("This and the following {0} session(s).").format(summary["update"])
	add_log(tt.class_name, "Edited", tt.name, tt.schedule_date, f"{detail} {changes}".strip())
	frappe.db.commit()
	return summary


def _marked(names):
	"""Names of the Time Table entries whose attendance is marked."""
	return {
		s.class_schedule
		for s in frappe.get_all(
			"Attendance Session",
			filters={"class_schedule": ["in", list(names) or [""]], "attendance_marked": 1},
			fields=["class_schedule"],
		)
	}


def _plan_update(tt, data, scope):
	"""What saving the Edit dialog would do, worked out without changing
	anything; check_class_time_table_update shows it, update_class_time_table
	carries it out.

	this                     - the one entry, on its (new) date.
	future, same dates       - the entry and every later one of its series, on
	                           their dates.
	future, new Schedule Date, Repeat or Repeats Till - the series is rebuilt
	                           from the new start: later entries are replaced by
	                           new ones (non-teaching days and booked venues
	                           skipped). Entries with marked attendance are kept
	                           as they are, and no new entry is made on their date.
	Every date is checked for the venue (not counting the entries being
	replaced), the faculty and the Institutional Calendar."""
	root, names = _series(tt)
	updates = {f: data.get(f) for f in EDIT_FIELDS if f in data}
	slot = frappe._dict(tt.as_dict())
	slot.update(updates)
	plan = frappe._dict(scope=scope, root=root, names=names, updates=updates, rebuild=False,
		following=[], keep=[], rows=[], errors=[], create=[], cp_outside=[], drop_weeks=[])

	if scope == "this":
		new_date = getdate(data.schedule_date or tt.schedule_date)
		plan.updates["schedule_date"] = new_date
		plan.following = [tt.name]
		plan.rows = _check_dates([new_date], slot, exclude=[tt.name])["dates"]
	else:
		# Cancelled sessions stay as they are (and no new session goes on their date)
		following = frappe.get_all(
			"Time Table",
			filters={"name": ["in", names], "schedule_date": [">=", tt.schedule_date], "docstatus": ["<", 2], "is_cancelled": 0},
			fields=["name", "schedule_date"],
			order_by="schedule_date asc",
		)
		cancelled_dates = {getdate(d) for d in frappe.get_all(
			"Time Table",
			filters={"name": ["in", names], "schedule_date": [">=", tt.schedule_date], "is_cancelled": 1},
			pluck="schedule_date",
		)}
		plan.following = [r.name for r in following]
		freq = data.repeat_frequency or "Never"
		start = getdate(data.schedule_date or tt.schedule_date)
		till = getdate(data.repeats_till) if freq != "Never" and data.repeats_till else None
		old_freq = root.repeat_frequency or "Never"
		old_till = getdate(root.repeats_till) if old_freq != "Never" and root.repeats_till else None
		plan.rebuild = start != getdate(tt.schedule_date) or freq != old_freq or till != old_till

		if not plan.rebuild:
			plan.rows = _check_dates([r.schedule_date for r in following], slot, exclude=plan.following)["dates"]
		else:
			plan.update(freq=freq, till=till, start=start)
			if till and till < start:
				plan.errors.append(_("Repeats Till cannot be before the Schedule Date."))
				return plan
			# Sessions before this one stay; the new start may not reach back to them
			earlier = [getdate(d) for d in frappe.get_all(
				"Time Table",
				filters={"name": ["in", names], "schedule_date": ["<", tt.schedule_date], "docstatus": ["<", 2]},
				pluck="schedule_date",
			)]
			if earlier and start <= max(earlier):
				plan.errors.append(_(
					"The Schedule Date must be after the previous session of this series ({0}). "
					"To move earlier sessions, edit the series from its first session."
				).format(formatdate(max(earlier))))
				return plan
			marked = _marked(plan.following)
			plan.keep = [r for r in following if r.name in marked]
			kept_dates = {getdate(r.schedule_date) for r in plan.keep}
			if root.name in marked and start < getdate(root.schedule_date):
				plan.errors.append(_(
					"Attendance is marked for the first session ({0}), so the series cannot start before it."
				).format(formatdate(root.schedule_date)))
				return plan
			plan.rows = _check_dates(_series_dates(start, freq, till), slot, exclude=plan.following)["dates"]
			for row in plan.rows:
				if getdate(row["date"]) in kept_dates:
					row["status"], row["note"] = "kept", _("Session with marked attendance is kept as it is")
				elif getdate(row["date"]) in cancelled_dates:
					row["status"], row["note"] = "kept", _("Cancelled session: no new session on this date")
			plan.create = [r["date"] for r in plan.rows if r["status"] in ("ok", "faculty_warn")]
			first = plan.rows[0] if plan.rows else None
			if first and first["status"] in ("holiday", "venue"):
				plan.errors.append(_("The first session ({0}) cannot be scheduled: {1}. Kindly choose another Schedule Date, time or venue.").format(
					first["date_fmt"], first["note"]))
			elif not plan.create:
				plan.errors.append(_("None of the sessions can be scheduled. Kindly choose another date range, time or venue."))
			else:
				# The series' range afterwards (a first session that moves starts it
				# at its new date); Class Participation weeks are fitted into it
				root_moves = root.name in plan.following and root.name not in marked
				plan.range = (
					getdate(plan.create[0]) if root_moves else getdate(root.schedule_date),
					max([getdate(d) for d in plan.create] + list(kept_dates) + earlier),
				)
				# Class Participation weeks the new range no longer reaches: listed
				# for the user to delete (data.drop_cp_weeks) or to change the dates
				outside = [
					row for row in root.get("class_participation_week_group") or []
					if row.start_date and row.end_date and (
						getdate(row.end_date) < plan.range[0] or getdate(row.start_date) > plan.range[1])
				]
				plan.cp_outside = _cp_week_rows(outside)
				if plan.cp_outside and cint(data.get("drop_cp_weeks")):
					locked = [w for w in plan.cp_outside if w["recorded"]]
					if locked:
						plan.errors.append(_(
							"Participation is already recorded for Class Participation week {0}, so it cannot be deleted. "
							"Kindly choose dates that still cover it."
						).format(", ".join(str(w["idx"]) for w in locked)))
					plan.drop_weeks = [w["week"] for w in plan.cp_outside]
			return plan

	# Same dates (one entry, or this and the following): every one must be free
	for row in plan.rows:
		if row["status"] in ("holiday", "venue"):
			plan.errors.append(f"{row['date_fmt']}: {row['note']}")
	return plan


def _cp_recorded(group):
	"""Participation (an hour ticked or a grade given) is recorded in this
	Class-Participation Student Group."""
	from slcm.slcm.utils.class_participation import HOURS, hour_fields

	fields = [f for slot in range(1, len(HOURS) + 1) for f in hour_fields(slot)]
	for row in frappe.get_all("Student Group Student", filters={"parent": group, "parenttype": "Student Group"},
			fields=fields):
		if any(flt(row.get(f)) for f in fields):
			return True
	return False


def _cp_week_rows(rows):
	"""Class Participation week rows as shown in the Edit dialog's table."""
	out = []
	for row in rows:
		out.append({
			"idx": row.idx,
			"week": row.week,
			"week_name": frappe.db.get_value("Student Group", row.week, "week_name") or row.week,
			"start_date": str(row.start_date),
			"end_date": str(row.end_date),
			"dates": "{0} – {1}".format(formatdate(row.start_date), formatdate(row.end_date)),
			"students": frappe.db.count("Student Group Student", {"parent": row.week, "parenttype": "Student Group"}),
			"recorded": _cp_recorded(row.week),
		})
	return out


def _drop_cp_weeks(names, weeks):
	"""Take Class Participation weeks off every entry of the series and delete
	their Student Groups (nothing was recorded in them; a group still linked
	elsewhere is left as it is)."""
	if not weeks:
		return
	frappe.db.delete("Class Participation Week", {
		"parenttype": "Time Table", "parent": ["in", list(names) or [""]], "week": ["in", list(weeks)]})
	for week in weeks:
		try:
			frappe.delete_doc("Student Group", week, ignore_permissions=True)
		except frappe.LinkExistsError:
			frappe.clear_last_message()


def _plan_summary(plan):
	return {
		"rebuild": plan.rebuild,
		"rows": plan.rows,
		"errors": plan.errors,
		"cp_outside": [] if plan.drop_weeks else plan.cp_outside,
		"drop_weeks": plan.drop_weeks,
		"update": 0 if plan.rebuild else len(plan.following),
		"replace": len(plan.following) - len(plan.keep) if plan.rebuild else 0,
		"create": len(plan.create),
		"keep": len(plan.keep),
	}


@frappe.whitelist()
def check_class_time_table_update(time_table, data, scope):
	"""Dry run of the Edit dialog's Save: availability of every date and what
	would change, so it can be confirmed first."""
	data = frappe._dict(json.loads(data) if isinstance(data, str) else data)
	tt = frappe.get_doc("Time Table", time_table)
	tt.check_permission("write")
	return _plan_summary(_plan_update(tt, data, scope))


def _fit_cp_weeks(doc, start, end):
	for row in doc.get("class_participation_week_group") or []:
		if row.start_date and getdate(row.start_date) < start:
			row.start_date = start
		if row.end_date and getdate(row.end_date) > end:
			row.end_date = end


def _rebuild_series(tt, plan):
	"""Replace this and the following entries (except marked ones) with entries
	on plan.create, all in one series under the root."""
	root = plan.root
	keep = {r.name for r in plan.keep}
	reuse_root = root.name in plan.following and root.name not in keep and plan.create
	template = frappe.copy_doc(tt)
	template.update(plan.updates)

	for name in reversed(plan.following):
		if name in keep or (reuse_root and name == root.name):
			continue
		frappe.delete_doc("Time Table", name, force=1, ignore_permissions=True)

	# Dates, not "YYYY-MM-DD" strings: validate compares them with saved dates
	dates = [getdate(d) for d in plan.create]
	# The root's range must cover the whole series before entries are added to
	# it (a reused root moves, so its old date does not count)
	remaining = [getdate(d) for d in frappe.get_all(
		"Time Table",
		filters={"name": ["in", [n for n in plan.names if not (reuse_root and n == root.name)] or [""]], "docstatus": ["<", 2]},
		pluck="schedule_date",
	)]
	last = max([getdate(d) for d in dates] + remaining)
	root.reload()
	if reuse_root:
		root.update(plan.updates)
		root.schedule_date = dates.pop(0)
	single = plan.freq == "Never" and last == getdate(root.schedule_date)
	root.repeat_frequency = "Never" if single else (plan.freq if plan.freq != "Never" else root.repeat_frequency)
	root.repeats_till = None if single else last
	# Class Participation weeks the user chose to delete go first; those
	# overlapping the new range's edges are trimmed to it
	start = getdate(root.schedule_date)
	drop = set(plan.drop_weeks or [])
	for doc in (root, template):
		if drop:
			doc.set("class_participation_week_group",
				[r for r in doc.get("class_participation_week_group") or [] if r.week not in drop])
		_fit_cp_weeks(doc, start, last)
	root.save(ignore_permissions=True)

	for d in dates:
		new = frappe.copy_doc(template)
		new.schedule_date = d
		new.parent_schedule = root.name
		new.repeat_frequency = "Never"
		new.repeats_till = None
		new.insert(ignore_permissions=True)

	if drop:
		series = [root.name] + frappe.get_all("Time Table", filters={"parent_schedule": root.name}, pluck="name")
		_drop_cp_weeks(series, drop)


# ── Delete sessions (Edit dialog) ─────────────────────────────────────────────

def _with_attendance(names):
	"""Entries in which attendance was taken; Delete keeps them."""
	from slcm.slcm.doctype.time_table.time_table import session_has_attendance

	names = list(names) or [""]
	sessions = frappe.get_all("Attendance Session", filters={"class_schedule": ["in", names]},
		fields=["name", "class_schedule"])
	taken = {s.class_schedule for s in sessions if session_has_attendance(s.name)}
	taken.update(frappe.get_all("Student Attendance", filters={"class_schedule": ["in", names]},
		pluck="class_schedule", distinct=True))
	return taken


def _plan_delete(tt, scope):
	"""What Delete would do, worked out without changing anything.

	this    - the one entry.
	future  - the entry and every later one of its series (cancelled ones too).
	Entries in which attendance was taken are kept. The rest of the series
	stays one series: when its first entry goes, the next remaining entry
	becomes the first and carries the series' Repeat and Class Participation
	weeks; Repeats Till becomes the last remaining date, and Class
	Participation weeks with no class left are taken off the schedule."""
	root, names = _series(tt)
	entries = frappe.get_all(
		"Time Table",
		filters={"name": ["in", names], "docstatus": ["<", 2]},
		fields=["name", "schedule_date", "from_time", "to_time", "venue", "is_cancelled"],
		order_by="schedule_date asc, from_time asc",
	)
	if scope == "this":
		targets = [e for e in entries if e.name == tt.name]
	else:
		targets = [e for e in entries if getdate(e.schedule_date) >= getdate(tt.schedule_date)]
	taken = _with_attendance([e.name for e in targets])

	plan = frappe._dict(scope=scope, root=root, delete=[], keep=[], rows=[], errors=[], warnings=[],
		new_root=None, survivors=[], range=None, cp_drop=[])
	for e in targets:
		kept = e.name in taken
		(plan.keep if kept else plan.delete).append(e.name)
		plan.rows.append({
			"name": e.name,
			"date_fmt": formatdate(e.schedule_date, "EEE, dd MMM yyyy"),
			"time": "{0} – {1}".format(format_time_12h(e.from_time), format_time_12h(e.to_time)),
			"venue": e.venue or "",
			"status": "kept" if kept else "delete",
			"note": _("Attendance taken: kept") if kept else (_("Cancelled session") if e.is_cancelled else ""),
		})

	if tt.name in taken:
		plan.errors.append(_("Attendance was taken in the session on {0}, so it cannot be deleted.").format(
			formatdate(tt.schedule_date)))
		return plan
	if not plan.delete:
		plan.errors.append(_("Attendance was taken in every session from here on, so there is nothing to delete."))
		return plan

	gone = set(plan.delete)
	survivors = [e for e in entries if e.name not in gone]
	plan.survivors = [e.name for e in survivors]
	if survivors:
		if root.name in gone:
			plan.new_root = survivors[0].name
		plan.range = (getdate(survivors[0].schedule_date), getdate(survivors[-1].schedule_date))
		for row in root.get("class_participation_week_group") or []:
			if row.start_date and row.end_date and (
				getdate(row.end_date) < plan.range[0] or getdate(row.start_date) > plan.range[1]
			):
				plan.cp_drop.append(row.name)
				plan.warnings.append(_("Class Participation week {0} ({1} – {2}) has no class left and is taken off the schedule; its student group is not deleted.").format(
					row.idx, formatdate(row.start_date), formatdate(row.end_date)))
	elif root.get("class_participation_week_group"):
		plan.warnings.append(_("This deletes every session of the series. Its Class Participation student groups are not deleted."))
	return plan


def _delete_summary(plan):
	return {
		"rows": plan.rows,
		"errors": plan.errors,
		"warnings": plan.warnings,
		"delete": len(plan.delete),
		"keep": len(plan.keep),
		"remaining": len(plan.survivors),
	}


@frappe.whitelist()
def check_class_time_table_delete(time_table, scope):
	"""Dry run of Delete in the Edit dialog: the sessions that would go."""
	tt = frappe.get_doc("Time Table", time_table)
	tt.check_permission("delete")
	return _delete_summary(_plan_delete(tt, scope))


@frappe.whitelist(methods=["POST"])
def delete_class_time_table(time_table, scope):
	"""Delete this session (scope "this") or this and the following sessions
	of its series (scope "future"), see _plan_delete. Each deleted entry takes
	its Attendance Session and Google Calendar event with it."""
	from slcm.slcm.doctype.class_schedule_log.class_schedule_log import add_log, no_schedule_log
	from slcm.slcm.doctype.time_table.time_table import quiet_bulk_operation

	tt = frappe.get_doc("Time Table", time_table)
	tt.check_permission("delete")
	if scope not in ("this", "future"):
		frappe.throw(_("Choose this session or this and the following sessions."))
	plan = _plan_delete(tt, scope)
	if plan.errors:
		frappe.throw("<br>".join(plan.errors), title=_("Cannot Delete"))

	root = plan.root
	with no_schedule_log(), quiet_bulk_operation():
		if plan.new_root:
			# The next remaining entry heads the series before the first one goes
			for name in plan.survivors:
				frappe.db.set_value("Time Table", name, "parent_schedule",
					None if name == plan.new_root else plan.new_root, update_modified=False)
		total = len(plan.delete)
		publish_bulk_progress("Deleting", 0, total)
		for done, name in enumerate(reversed(plan.delete), start=1):
			frappe.delete_doc("Time Table", name, force=1, ignore_permissions=True)
			publish_bulk_progress("Deleting", done, total)

		if plan.survivors:
			head = frappe.get_doc("Time Table", plan.new_root or root.name)
			start, last = plan.range
			if plan.new_root:
				head.set("class_participation_week_group", [
					{"week": r.week, "start_date": r.start_date, "end_date": r.end_date}
					for r in root.get("class_participation_week_group") or [] if r.name not in plan.cp_drop
				])
			else:
				head.set("class_participation_week_group", [
					r for r in head.get("class_participation_week_group") or [] if r.name not in plan.cp_drop
				])
			single = start == last
			head.repeat_frequency = "Never" if single else (root.repeat_frequency or "Weekly")
			head.repeats_till = None if single else last
			_fit_cp_weeks(head, start, last)
			head.save(ignore_permissions=True)

	if scope == "this":
		detail = _("This session deleted.")
	else:
		detail = _("This and the following sessions: {0} deleted").format(len(plan.delete))
		if plan.keep:
			detail += _(", {0} kept (attendance taken)").format(len(plan.keep))
		detail += "."
	add_log(tt.class_name, "Deleted", tt.name, tt.schedule_date, f"{detail} {_slot_text(tt)}")
	frappe.db.commit()
	return _delete_summary(plan)


# ── Cancel / swap one session ─────────────────────────────────────────────────

def _slot_text(row):
	return "{0}, {1} – {2}, {3}".format(
		formatdate(row.schedule_date, "dd MMM yyyy"), format_time_12h(row.from_time),
		format_time_12h(row.to_time), row.venue or _("no venue"))


def _changeable(tt, action):
	"""A session can be cancelled or swapped while it is active and its
	attendance is not marked."""
	if tt.is_cancelled:
		frappe.throw(_("This session is already cancelled."))
	if _marked([tt.name]):
		frappe.throw(_("Attendance is marked for the session on {0}, so it cannot be {1}.").format(
			formatdate(tt.schedule_date), action))


@frappe.whitelist()
def cancel_class_session(time_table, reason):
	"""Cancel this one session: it stays on the calendar as Cancelled (with its
	Attendance Session), and its venue and faculty slot is free for other
	classes. Removed from Google Calendar."""
	from slcm.slcm.doctype.class_schedule_log.class_schedule_log import add_log
	from slcm.slcm.doctype.time_table.google_calendar_sync import delete_linked_google_event

	tt = frappe.get_doc("Time Table", time_table)
	tt.check_permission("write")
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Enter the reason for cancelling the session."))
	_changeable(tt, _("cancelled"))

	tt.db_set({"is_cancelled": 1, "cancellation_reason": reason})
	session = frappe.db.get_value("Attendance Session", {"class_schedule": tt.name}, "name")
	if session:
		frappe.db.set_value("Attendance Session", session,
			{"session_status": "Cancelled", "cancellation_reason": reason})
	if tt.linked_google_event:
		delete_linked_google_event(tt)
		tt.db_set("linked_google_event", None)

	add_log(tt.class_name, "Cancelled", tt.name, tt.schedule_date,
		_("{0}. Reason: {1}. The venue and faculty slot is free for other classes.").format(_slot_text(tt), reason))
	return {"name": tt.name}


def _swap_filters(tt):
	"""Sessions of other classes for the same students: same term and
	programme, and the same section for a section class."""
	filters = {
		"based_on": "Class",
		"class_name": ["!=", tt.class_name],
		"academic_term": tt.academic_term,
		"is_cancelled": 0,
		"docstatus": ["<", 2],
		"schedule_date": [">=", tt.schedule_date],
	}
	if tt.programme:
		filters["programme"] = tt.programme
	if tt.section:
		filters["section"] = tt.section
	return filters


@frappe.whitelist()
def get_swap_candidates(time_table):
	"""Sessions this one can swap its slot with: other courses of the same
	students on the same day or later, not cancelled, attendance not marked."""
	tt = frappe.get_doc("Time Table", time_table)
	tt.check_permission("write")
	_changeable(tt, _("swapped"))
	if getdate(tt.schedule_date) < getdate():
		frappe.throw(_("Only today's or upcoming sessions can be swapped."))

	rows = frappe.get_all(
		"Time Table",
		filters=_swap_filters(tt),
		fields=["name", "class_name", "title", "course", "section", "schedule_date", "from_time", "to_time", "venue", "instructor"],
		order_by="schedule_date asc, from_time asc",
		limit=500,
	)
	marked = _marked([r.name for r in rows])
	faculty = {f.name: " ".join(filter(None, [f.first_name, f.last_name])) for f in frappe.get_all(
		"Faculty", filters={"name": ["in", list({r.instructor for r in rows if r.instructor}) or [""]]},
		fields=["name", "first_name", "last_name"],
	)}
	return [{
		"name": r.name,
		"class_name": r.class_name,
		"title": r.title or r.course,
		"section": r.section,
		"date": str(r.schedule_date),
		"date_fmt": formatdate(r.schedule_date, "EEE, dd MMM yyyy"),
		"from_time": str(r.from_time),
		"to_time": str(r.to_time),
		"venue": r.venue,
		"faculty": faculty.get(r.instructor) or r.instructor or "",
	} for r in rows if r.name not in marked]


def _plan_swap(a, b):
	"""Each session takes the other's date, time and venue; faculty stay with
	their course. Checked like any new slot (holiday, venue, the faculty's
	other classes), not counting the two sessions themselves."""
	errors, warnings = [], []
	_changeable(a, _("swapped"))
	if b.is_cancelled or _marked([b.name]):
		errors.append(_("The session of {0} on {1} is cancelled or has marked attendance.").format(
			b.title or b.course, formatdate(b.schedule_date)))
	if getdate(a.schedule_date) < getdate():
		errors.append(_("Only today's or upcoming sessions can be swapped."))
	allowed = _swap_filters(a)
	if (b.class_name == a.class_name or b.academic_term != a.academic_term
			or (allowed.get("programme") and b.programme != allowed["programme"])
			or (allowed.get("section") and b.section != allowed["section"])
			or getdate(b.schedule_date) < getdate(a.schedule_date)):
		errors.append(_("{0} cannot be swapped with this session: it must be another course of the same students on the same day or later.").format(
			b.title or b.course))

	moves = []
	for doc, slot in ((a, b), (b, a)):
		new = frappe._dict(schedule_date=slot.schedule_date, from_time=slot.from_time, to_time=slot.to_time, venue=slot.venue)
		check = _check_dates([new.schedule_date], frappe._dict(new, instructor=doc.instructor), exclude=[a.name, b.name])
		row = check["dates"][0] if check["dates"] else {"status": "ok", "note": ""}
		label = doc.title or doc.course
		if row["status"] in ("holiday", "venue"):
			errors.append(f"{label}: {row['note']}")
		elif row["status"] == "faculty_warn":
			warnings.append(f"{label}: {row['note']}")
		moves.append({"name": doc.name, "class_name": doc.class_name, "title": label,
			"before": _slot_text(doc), "after": _slot_text(frappe._dict(new)), "new": new})
	return frappe._dict(errors=errors, warnings=warnings, moves=moves)


@frappe.whitelist()
def check_swap(time_table, other):
	"""Dry run of swap_class_sessions: what moves where, and any problem."""
	a = frappe.get_doc("Time Table", time_table)
	b = frappe.get_doc("Time Table", other)
	a.check_permission("write")
	b.check_permission("write")
	plan = _plan_swap(a, b)
	return {"errors": plan.errors, "warnings": plan.warnings,
		"moves": [{k: m[k] for k in ("name", "class_name", "title", "before", "after")} for m in plan.moves]}


@frappe.whitelist()
def swap_class_sessions(time_table, other):
	"""Swap the date, time and venue of two sessions (see _plan_swap); their
	Attendance Sessions and Google Calendar events follow. Logged on both
	classes."""
	from slcm.slcm.doctype.class_schedule_log.class_schedule_log import add_log
	from slcm.slcm.doctype.time_table.google_calendar_sync import sync_time_table_to_google_calendar
	from slcm.slcm.doctype.time_table.time_table import quiet_bulk_operation

	a = frappe.get_doc("Time Table", time_table)
	b = frappe.get_doc("Time Table", other)
	a.check_permission("write")
	b.check_permission("write")
	plan = _plan_swap(a, b)
	if plan.errors:
		frappe.throw("<br>".join(plan.errors), title=_("Cannot Swap"))

	# Written directly: saving one first would clash with the other still in its slot
	docs = {a.name: a, b.name: b}
	for m in plan.moves:
		doc = docs[m["name"]]
		doc.update(m["new"])
		doc.calculate_duration()
		doc.db_update()
	with quiet_bulk_operation():
		for doc in docs.values():
			doc.update_attendance_session()
			sync_time_table_to_google_calendar(doc)

	ma, mb = plan.moves
	for m, other_move in ((ma, mb), (mb, ma)):
		add_log(m["class_name"], "Swapped", m["name"], m["new"].schedule_date,
			_("Swapped with {0} ({1}): {2} → {3}").format(other_move["title"], other_move["class_name"], m["before"], m["after"]))
	return {"moves": [{k: m[k] for k in ("name", "title", "before", "after")} for m in plan.moves]}
