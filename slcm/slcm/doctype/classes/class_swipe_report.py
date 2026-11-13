# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Swipe Report for a Class, from the Time Table pop-up (public/js/class_time_table.js).

The RFID swipes of the class's students around each session's time, as Excel or CSV:

  One session  Students sheet: one row per student - swiped or not, first / last swipe, terminals,
               attendance status - and a Swipes sheet with every swipe in the window.
  Date range   Sessions sheet: one row per student, one column per session with their first swipe
               time (blank = no swipe), plus how many sessions they swiped for; and a Swipes sheet.

A swipe counts for a session when it falls between [start - minutes before] and [end + minutes after],
at any terminal: the Terminal column shows where it was made (readers are not all mapped to rooms yet).
Read only: nothing is created or changed.
"""

import base64
import csv
import io

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, format_datetime, formatdate, get_datetime, getdate, now_datetime

from slcm.slcm.doctype.classes.class_time_table import _class_roster

MAX_DAYS = 186          # a date range covers at most about one term
MAX_SESSIONS = 300
MAX_WINDOW_MINUTES = 120
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _clock(t):
	"""timedelta / str like 9:10:00 -> 09:10:00"""
	return str(t or "0:00:00").split(".")[0].zfill(8)


def _window(tt, before, after):
	start = get_datetime(f"{tt.schedule_date} {_clock(tt.from_time)}")
	end = get_datetime(f"{tt.schedule_date} {_clock(tt.to_time)}")
	return add_to_date(start, minutes=-before), add_to_date(end, minutes=after)


def _session_label(tt):
	return f"{formatdate(tt.schedule_date, 'dd MMM')} {get_datetime(f'2000-01-01 {_clock(tt.from_time)}').strftime('%I:%M %p').lstrip('0')}"


def _hhmm(dt):
	return get_datetime(dt).strftime("%I:%M %p").lstrip("0") if dt else ""


@frappe.whitelist()
def export_class_swipes(class_name, time_table=None, from_date=None, to_date=None, before=20, after=20, file_format="xlsx"):
	"""Swipe Report for one session (time_table) or for every session of the class from_date..to_date."""
	cls = frappe.get_doc("Classes", class_name)
	cls.check_permission("read")
	frappe.has_permission("Attendance Log", "read", throw=True)

	before, after = cint(before), cint(after)
	if not (0 <= before <= MAX_WINDOW_MINUTES and 0 <= after <= MAX_WINDOW_MINUTES):
		frappe.throw(_("Minutes before / after must be between 0 and {0}.").format(MAX_WINDOW_MINUTES))
	file_format = "csv" if file_format == "csv" else "xlsx"

	fields = ["name", "schedule_date", "from_time", "to_time", "venue", "title", "course", "is_cancelled", "class_name"]
	if time_table:
		tt = frappe.get_doc("Time Table", time_table)
		tt.check_permission("read")
		if tt.class_name != class_name:
			frappe.throw(_("Session {0} does not belong to class {1}.").format(time_table, class_name))
		sessions = [frappe._dict({f: tt.get(f) for f in fields})]
	else:
		if not from_date or not to_date:
			frappe.throw(_("Choose a From Date and a To Date."))
		start, end = getdate(from_date), getdate(to_date)
		if start > end:
			frappe.throw(_("From Date cannot be after To Date."))
		if (end - start).days > MAX_DAYS:
			frappe.throw(_("Choose at most {0} days at a time.").format(MAX_DAYS))
		sessions = frappe.get_all(
			"Time Table",
			filters={"class_name": class_name, "schedule_date": ["between", [start, end]],
			         "docstatus": ["<", 2], "is_cancelled": 0},
			fields=fields, order_by="schedule_date asc, from_time asc", limit_page_length=MAX_SESSIONS + 1,
		)
		if not sessions:
			frappe.throw(_("This class has no sessions between {0} and {1}.").format(formatdate(start), formatdate(end)))
		if len(sessions) > MAX_SESSIONS:
			frappe.throw(_("More than {0} sessions in this range - choose a shorter range.").format(MAX_SESSIONS))

	roster = _class_roster(class_name)
	cards = dict(frappe.get_all(
		"Student Master", filters={"name": ["in", [s.student for s in roster] or [""]]},
		fields=["name", "rfid_uid"], as_list=True,
	))
	windows = {s.name: _window(s, before, after) for s in sessions}
	swipes = _swipes([s.student for s in roster], windows)

	# swipes of each student in each session's window
	by_session = {s.name: {} for s in sessions}
	for row in swipes:
		for s in sessions:
			w_start, w_end = windows[s.name]
			if w_start <= get_datetime(row.swipe_time) <= w_end:
				by_session[s.name].setdefault(row.student, []).append(row)

	if time_table:
		sheets = _one_session(sessions[0], roster, cards, by_session[sessions[0].name], before, after)
		name = f"rfid_swipes_{frappe.scrub(class_name)}_{sessions[0].schedule_date}"
	else:
		sheets = _date_range(sessions, roster, cards, by_session, before, after)
		name = f"rfid_swipes_{frappe.scrub(class_name)}_{from_date}_to_{to_date}"
	sheets.append(_swipe_sheet(sessions, roster, by_session))

	if file_format == "csv":
		return {"filename": f"{name}.csv", "mime": "text/csv",
		        "content": base64.b64encode(_csv(sheets[0]).encode("utf-8-sig")).decode()}
	return {"filename": f"{name}.xlsx", "mime": XLSX_MIME, "content": base64.b64encode(_xlsx(sheets)).decode()}


def _swipes(students, windows):
	if not students or not windows:
		return []
	return frappe.db.sql("""
		SELECT student, swipe_time, terminal_alias, device_id, location
		FROM `tabAttendance Log`
		WHERE student IN %(students)s AND swipe_time BETWEEN %(start)s AND %(end)s
		ORDER BY swipe_time ASC
	""", {
		"students": tuple(students),
		"start": min(w[0] for w in windows.values()),
		"end": max(w[1] for w in windows.values()),
	}, as_dict=True)


def _terminals(rows):
	return ", ".join(dict.fromkeys(r.terminal_alias or r.device_id or "" for r in rows if r.terminal_alias or r.device_id))


def _one_session(s, roster, cards, swiped, before, after):
	marked = dict(frappe.get_all(
		"Student Attendance", filters={"class_schedule": s.name, "docstatus": ["<", 2]},
		fields=["student", "status"], as_list=True,
	))
	w_start, w_end = _window(s, before, after)
	info = [
		[_("Class"), s.class_name], [_("Session"), s.title or s.course or s.name],
		[_("Date"), formatdate(s.schedule_date, "EEEE, dd MMM yyyy")],
		[_("Time"), f"{_hhmm(get_datetime(f'{s.schedule_date} {_clock(s.from_time)}'))} - {_hhmm(get_datetime(f'{s.schedule_date} {_clock(s.to_time)}'))}"],
		[_("Venue"), s.venue or ""],
		[_("Swipes counted"), _("{0} to {1} ({2} min before start, {3} min after end), any terminal").format(
			_hhmm(w_start), _hhmm(w_end), before, after)],
		[_("Generated"), format_datetime(now_datetime())],
	]
	head = [_("Student ID"), _("Student Name"), _("RFID Card"), _("Swiped"), _("Swipes"), _("First Swipe"),
	        _("Last Swipe"), _("Terminals"), _("Attendance")]
	rows = []
	for st in roster:
		got = swiped.get(st.student) or []
		card = cards.get(st.student) or ""
		rows.append([
			st.student_id, st.student_name, card,
			_("Yes") if got else (_("No") if card else _("No card")),
			len(got), _hhmm(got[0].swipe_time) if got else "", _hhmm(got[-1].swipe_time) if got else "",
			_terminals(got), marked.get(st.student) or _("Not Marked"),
		])
	return [{"title": "Students", "info": info, "head": head, "rows": rows, "widths": [14, 30, 14, 10, 9, 12, 12, 30, 13]}]


def _date_range(sessions, roster, cards, by_session, before, after):
	info = [
		[_("Class"), sessions[0].class_name],
		[_("Sessions"), _("{0} sessions, {1} to {2} (cancelled sessions left out)").format(
			len(sessions), formatdate(sessions[0].schedule_date), formatdate(sessions[-1].schedule_date))],
		[_("Cell"), _("first swipe time in that session's window; blank = no swipe")],
		[_("Swipes counted"), _("{0} min before start to {1} min after end, any terminal").format(before, after)],
		[_("Generated"), format_datetime(now_datetime())],
	]
	head = [_("Student ID"), _("Student Name"), _("RFID Card"), _("Sessions Swiped"), _("Sessions")] + [_session_label(s) for s in sessions]
	rows = []
	for st in roster:
		cells = []
		for s in sessions:
			got = by_session[s.name].get(st.student)
			cells.append(_hhmm(got[0].swipe_time) if got else "")
		rows.append([st.student_id, st.student_name, cards.get(st.student) or _("No card"),
		             sum(1 for c in cells if c), len(sessions)] + cells)
	return [{"title": "Sessions", "info": info, "head": head, "rows": rows, "widths": [14, 30, 14, 15, 10] + [14] * len(sessions)}]


def _swipe_sheet(sessions, roster, by_session):
	names = {st.student: st for st in roster}
	head = [_("Session"), _("Student ID"), _("Student Name"), _("Swipe Time"), _("Terminal"), _("Device"), _("Location")]
	rows = []
	for s in sessions:  # sessions are in date order; within one, swipes in time order
		got = sorted((g for rows_ in by_session[s.name].values() for g in rows_), key=lambda g: get_datetime(g.swipe_time))
		for g in got:
			st = names.get(g.student) or frappe._dict()
			rows.append([_session_label(s), st.student_id, st.student_name, format_datetime(g.swipe_time),
			             g.terminal_alias or "", g.device_id or "", g.location or ""])
	return {"title": "Swipes", "info": [], "head": head, "rows": rows, "widths": [16, 14, 30, 20, 16, 10, 16]}


def _csv(sheet):
	out = io.StringIO()
	w = csv.writer(out)
	for line in sheet["info"]:
		w.writerow(line)
	if sheet["info"]:
		w.writerow([])
	w.writerow(sheet["head"])
	w.writerows(sheet["rows"])
	return out.getvalue()


def _xlsx(sheets):
	import openpyxl
	from openpyxl.styles import Font, PatternFill
	from openpyxl.utils import get_column_letter

	wb = openpyxl.Workbook()
	wb.remove(wb.active)
	for sheet in sheets:
		ws = wb.create_sheet(sheet["title"])
		for label, value in sheet["info"]:
			ws.append([label, value])
			ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
		if sheet["info"]:
			ws.append([])
		ws.append(sheet["head"])
		head_row = ws.max_row
		for ci in range(1, len(sheet["head"]) + 1):
			cell = ws.cell(row=head_row, column=ci)
			cell.font = Font(bold=True, color="FFFFFF")
			cell.fill = PatternFill("solid", fgColor="3949AB")
		for r in sheet["rows"]:
			ws.append(r)
		for ci, width in enumerate(sheet["widths"], start=1):
			ws.column_dimensions[get_column_letter(ci)].width = width
		ws.freeze_panes = ws.cell(row=head_row + 1, column=3)
	out = io.BytesIO()
	wb.save(out)
	return out.getvalue()


# ── Time Table list: selected sessions, or every session of some classes in a date range ─────────────

MAX_LIST_SESSIONS = 500
MAX_LIST_CLASSES = 50


@frappe.whitelist()
def export_session_swipes(time_tables=None, classes=None, from_date=None, to_date=None, before=20, after=20,
                          file_format="xlsx"):
	"""Swipe Report across classes: the sessions ticked in the Time Table list (time_tables), or every session of
	`classes` between from_date and to_date. One row per student per session, a per-session summary and every
	swipe. Cancelled sessions and sessions without a Class are left out (counted in the Summary)."""
	frappe.has_permission("Attendance Log", "read", throw=True)
	before, after = cint(before), cint(after)
	if not (0 <= before <= MAX_WINDOW_MINUTES and 0 <= after <= MAX_WINDOW_MINUTES):
		frappe.throw(_("Minutes before / after must be between 0 and {0}.").format(MAX_WINDOW_MINUTES))
	file_format = "csv" if file_format == "csv" else "xlsx"

	fields = ["name", "schedule_date", "from_time", "to_time", "venue", "title", "course", "is_cancelled", "class_name"]
	order = "schedule_date asc, from_time asc, class_name asc"
	if time_tables:
		names = list(dict.fromkeys(frappe.parse_json(time_tables) if isinstance(time_tables, str) else time_tables))
		if len(names) > MAX_LIST_SESSIONS:
			frappe.throw(_("Select at most {0} sessions at a time.").format(MAX_LIST_SESSIONS))
		# get_list applies the user's Time Table permissions: every ticked session must be readable
		sessions = frappe.get_list("Time Table", filters={"name": ["in", names]}, fields=fields, order_by=order,
		                           limit_page_length=0)
		if len(sessions) != len(names):
			frappe.throw(_("You cannot read some of the selected sessions."), frappe.PermissionError)
		scope = _("{0} selected sessions").format(len(names))
	else:
		classes = list(dict.fromkeys(frappe.parse_json(classes) if isinstance(classes, str) else (classes or [])))
		if not classes:
			frappe.throw(_("Select at least one Class."))
		if len(classes) > MAX_LIST_CLASSES:
			frappe.throw(_("Select at most {0} classes at a time.").format(MAX_LIST_CLASSES))
		if not from_date or not to_date:
			frappe.throw(_("Choose a From Date and a To Date."))
		start, end = getdate(from_date), getdate(to_date)
		if start > end:
			frappe.throw(_("From Date cannot be after To Date."))
		if (end - start).days > MAX_DAYS:
			frappe.throw(_("Choose at most {0} days at a time.").format(MAX_DAYS))
		sessions = frappe.get_list(
			"Time Table",
			filters={"class_name": ["in", classes], "schedule_date": ["between", [start, end]], "docstatus": ["<", 2]},
			fields=fields, order_by=order, limit_page_length=MAX_LIST_SESSIONS + 1,
		)
		if len(sessions) > MAX_LIST_SESSIONS:
			frappe.throw(_("More than {0} sessions - choose fewer classes or a shorter range.").format(MAX_LIST_SESSIONS))
		scope = _("{0} class(es), {1} to {2}").format(len(classes), formatdate(start), formatdate(end))

	cancelled = [s for s in sessions if cint(s.is_cancelled)]
	no_class = [s for s in sessions if not cint(s.is_cancelled) and not s.class_name]
	sessions = [s for s in sessions if not cint(s.is_cancelled) and s.class_name]
	if not sessions:
		frappe.throw(_("No session to report: the chosen sessions are cancelled or have no Class."))

	# rosters, cards and swipes, one class at a time (each class's own date span)
	by_class = {}
	for s in sessions:
		by_class.setdefault(s.class_name, []).append(s)
	rosters, swiped = {}, {}
	for class_name, class_sessions in by_class.items():
		if not frappe.has_permission("Classes", "read", doc=class_name):
			frappe.throw(_("You cannot read class {0}.").format(class_name), frappe.PermissionError)
		roster = _class_roster(class_name)
		rosters[class_name] = roster
		windows = {s.name: _window(s, before, after) for s in class_sessions}
		got = _swipes([st.student for st in roster], windows)
		for s in class_sessions:
			w_start, w_end = windows[s.name]
			swiped[s.name] = {}
			for g in got:
				if w_start <= get_datetime(g.swipe_time) <= w_end:
					swiped[s.name].setdefault(g.student, []).append(g)

	all_students = {st.student for roster in rosters.values() for st in roster}
	cards = dict(frappe.get_all("Student Master", filters={"name": ["in", list(all_students) or [""]]},
	                            fields=["name", "rfid_uid"], as_list=True))
	marked = {
		(a.class_schedule, a.student): a.status
		for a in frappe.get_all("Student Attendance",
		                        filters={"class_schedule": ["in", [s.name for s in sessions]], "docstatus": ["<", 2]},
		                        fields=["class_schedule", "student", "status"])
	}

	def when(s):
		return (formatdate(s.schedule_date, "dd MMM yyyy"),
		        f"{_hhmm(get_datetime(f'{s.schedule_date} {_clock(s.from_time)}'))} - "
		        f"{_hhmm(get_datetime(f'{s.schedule_date} {_clock(s.to_time)}'))}")

	summary_rows, student_rows, swipe_rows = [], [], []
	for s in sessions:
		date, time = when(s)
		course = s.title or s.course or ""
		yes = no = no_card = 0
		names = {}
		for st in rosters[s.class_name]:
			names[st.student] = st
			got = swiped[s.name].get(st.student) or []
			card = cards.get(st.student) or ""
			state = _("Yes") if got else (_("No") if card else _("No card"))
			yes += bool(got)
			no += (not got and bool(card))
			no_card += (not got and not card)
			student_rows.append([
				date, time, s.class_name, course, s.venue or "", st.student_id, st.student_name, card, state, len(got),
				_hhmm(got[0].swipe_time) if got else "", _hhmm(got[-1].swipe_time) if got else "", _terminals(got),
				marked.get((s.name, st.student)) or _("Not Marked"),
			])
		summary_rows.append([date, time, s.class_name, course, s.venue or "", len(rosters[s.class_name]), yes, no,
		                     no_card, s.name])
		for g in sorted((g for rows_ in swiped[s.name].values() for g in rows_), key=lambda g: get_datetime(g.swipe_time)):
			st = names.get(g.student) or frappe._dict()
			swipe_rows.append([date, time, s.class_name, st.student_id, st.student_name, format_datetime(g.swipe_time),
			                   g.terminal_alias or "", g.device_id or "", g.location or ""])

	info = [
		[_("Sessions"), _("{0} reported ({1})").format(len(sessions), scope)],
		[_("Left out"), _("{0} cancelled, {1} without a Class").format(len(cancelled), len(no_class))],
		[_("Swipes counted"), _("{0} min before start to {1} min after end, any terminal").format(before, after)],
		[_("Generated"), format_datetime(now_datetime())],
	]
	# one sheet per course (class): students down, sessions across, first swipe time in each cell
	class_info = {c.name: c for c in frappe.get_all(
		"Classes", filters={"name": ["in", list(by_class)]}, fields=["name", "course", "course_name", "section"])}
	used_titles = {"Summary", "All Students", "Swipes"}
	course_sheets = []
	for class_name in sorted(by_class, key=lambda c: ((class_info.get(c) or {}).get("course_name") or c, c)):
		ci = class_info.get(class_name) or frappe._dict()
		class_sessions = by_class[class_name]
		course = ci.course_name or ci.course or class_sessions[0].title or class_name
		label = f"{course} - {ci.section}" if ci.section else course
		rows = []
		for st in rosters[class_name]:
			cells = [_hhmm(swiped[s.name][st.student][0].swipe_time) if swiped[s.name].get(st.student) else ""
			         for s in class_sessions]
			rows.append([st.student_id, st.student_name, cards.get(st.student) or _("No card"),
			             sum(1 for c in cells if c), len(class_sessions)] + cells)
		course_sheets.append({
			"title": _sheet_title(label, used_titles),
			"info": [
				[_("Course"), label], [_("Class"), class_name],
				[_("Sessions"), _("{0}, {1} to {2}").format(len(class_sessions), formatdate(class_sessions[0].schedule_date),
				                                        formatdate(class_sessions[-1].schedule_date))],
				[_("Cell"), _("first swipe time in that session ({0} min before start to {1} min after end); blank = no swipe").format(before, after)],
			],
			"head": [_("Student ID"), _("Student Name"), _("RFID Card"), _("Sessions Swiped"), _("Sessions")]
			        + [_session_label(s) for s in class_sessions],
			"rows": rows, "widths": [14, 30, 13, 15, 10] + [14] * len(class_sessions),
		})

	sheets = [
		{"title": "All Students", "info": info,
		 "head": [_("Date"), _("Time"), _("Class"), _("Course"), _("Venue"), _("Student ID"), _("Student Name"),
		          _("RFID Card"), _("Swiped"), _("Swipes"), _("First Swipe"), _("Last Swipe"), _("Terminals"), _("Attendance")],
		 "rows": student_rows, "widths": [13, 19, 22, 28, 12, 14, 28, 13, 9, 8, 11, 11, 24, 12]},
		{"title": "Summary", "info": info,
		 "head": [_("Date"), _("Time"), _("Class"), _("Course"), _("Venue"), _("Students"), _("Swiped"), _("Not Swiped"),
		          _("No Card"), _("Time Table")],
		 "rows": summary_rows, "widths": [13, 19, 22, 28, 12, 10, 9, 11, 9, 18]},
		{"title": "Swipes", "info": [],
		 "head": [_("Date"), _("Time"), _("Class"), _("Student ID"), _("Student Name"), _("Swipe Time"), _("Terminal"),
		          _("Device"), _("Location")],
		 "rows": swipe_rows, "widths": [13, 19, 22, 14, 28, 20, 16, 10, 16]},
	]
	# Excel order: Summary, one sheet per course, then all rows and every swipe. CSV: the all-rows sheet.
	all_rows, summary, swipe_sheet = sheets
	sheets = [summary] + course_sheets + [all_rows, swipe_sheet]
	first, last = sessions[0].schedule_date, sessions[-1].schedule_date
	name = f"rfid_swipes_{len(sessions)}_sessions_{first}" + (f"_to_{last}" if last != first else "")
	if file_format == "csv":
		return {"filename": f"{name}.csv", "mime": "text/csv",
		        "content": base64.b64encode(_csv(all_rows).encode("utf-8-sig")).decode()}
	return {"filename": f"{name}.xlsx", "mime": XLSX_MIME, "content": base64.b64encode(_xlsx(sheets)).decode()}


def _sheet_title(label, used):
	"""A valid, unique Excel sheet name: at most 31 characters, none of [ ] : * ? / \\ ."""
	bad = set("[]:*?/\\")
	base = "".join(ch for ch in (label or "Class") if ch not in bad).strip(" '") or "Class"
	title, n = base[:31], 2
	while title.lower() in {u.lower() for u in used}:
		suffix = f" ({n})"
		title, n = base[:31 - len(suffix)] + suffix, n + 1
	used.add(title)
	return title
