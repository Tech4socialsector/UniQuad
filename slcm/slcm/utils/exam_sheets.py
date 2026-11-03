# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""The examination office's two Excel sheets, downloaded and imported as they are.

Exam timetable = "classroom allocation sheet": a title, one header row, then a
day header ("Saturday, 19th September 2026") followed by that day's rooms,
Forenoon on the left (Sl. No., Date, Venue, Year, paper, ID Nos. From / To,
Invigilator) and Afternoon on the right. Each line is one Exam Plan › Course
Schedule row; a course split over rooms has a row per room with its ID range.

Continuing Evaluation Schedule: Subject | Evaluation n/Assessment n, Marks,
Date (×4) | SGD | remarks. Each Evaluation is an Exam Assessment Schedule Item
(of every programme teaching the course); SGD and remarks are its Course Note.

Text the masters don't know is kept as written (Paper, Room, Invigilator, Marks,
Date), so a sheet imported and downloaded again comes back the same.
"""

import math
import re
from collections import Counter
from datetime import date, datetime, timedelta
from io import BytesIO

import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate, to_timedelta
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from slcm.slcm.utils.exam_timetable import _faculty_label, check_exam_schedule

THIN = Side(style="thin")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
GREY = PatternFill("solid", fgColor="D8D8D8")
HEAD_GREY = PatternFill("solid", fgColor="BFBFBF")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
TOP = Alignment(horizontal="center", vertical="top", wrap_text=True)
LEFT = Alignment(vertical="center", wrap_text=True)

SESSIONS = ("Forenoon", "Afternoon")
SESSION_TIMES = {"Forenoon": "10:00", "Afternoon": "14:30"}
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}

# Timetable columns: A Sl. No., B Date, C–H Forenoon, I Date, J–O Afternoon
TT_WIDTHS = {"A": 7, "B": 17.6, "C": 13, "D": 19.6, "E": 43.4, "F": 17.7, "G": 18.3, "H": 18,
             "I": 15.3, "J": 15, "K": 20.4, "L": 40.4, "M": 14.4, "N": 17.3, "O": 18}
SIDE_COL = {"Forenoon": 3, "Afternoon": 10}   # first column (Venue) of each side
CE_WIDTHS = {"A": 19.4, "B": 31.3, "C": 10, "D": 18.7, "E": 22.4, "F": 10, "G": 18, "H": 17.6, "I": 10,
             "J": 23.9, "K": 17.6, "L": 10, "M": 18, "N": 43.3, "O": 23.4}


# ── small helpers ──────────────────────────────────────────────────────────────

def _text(v):
	if v is None:
		return ""
	if isinstance(v, float) and v.is_integer():
		v = int(v)
	return cstr(v).replace("\xa0", " ").strip()


def _key(text):
	"""Room / name key: letters and digits only (OAB - 101 = OAB-101 = oab101)."""
	return re.sub(r"[^A-Z0-9]", "", _text(text).upper())


def _norm(text):
	return " ".join(re.sub(r"[^a-z0-9]+", " ", _text(text).lower()).split())


def _words(text):
	return {w for w in _norm(text).split() if len(w) > 2 and w not in ("the", "and", "for", "with")}


_END_TERM = re.compile(r"\b(end[\s-]*term|end[\s-]*sem\w*|final\s+exam\w*)\b", re.I)


def _is_end_term(*texts):
	"""End-term papers pair only with end-term assessments, internals with internals."""
	return any(_END_TERM.search(_text(t)) for t in texts)


def _ordinal(n):
	return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _long_date(d):
	"""Saturday, 19th September 2026"""
	return f"{d.strftime('%A')}, {_ordinal(d.day)} {d.strftime('%B %Y')}"


def _ampm(t):
	"""10:00 -> 10.00 AM, 14:30 -> 2.30 PM"""
	td = to_timedelta(t)
	h, m = int(td.total_seconds() // 3600), int(td.total_seconds() % 3600 // 60)
	return f"{(h % 12) or 12}.{m:02d} {'AM' if h < 12 else 'PM'}"


def _hhmm(t):
	return str(t or "")[:5].rjust(5, "0") if t else ""


def _session_of(row):
	if row.get("session") in SESSIONS:
		return row.get("session")
	if row.get("start_time"):
		return "Forenoon" if to_timedelta(row.get("start_time")) < timedelta(hours=12) else "Afternoon"
	return "Forenoon"


def _cell(ws, r, c, value=None, bold=False, fill=None, align=CENTER, size=12, font="Bookman Old Style"):
	cell = ws.cell(r, c)
	if value not in (None, ""):
		cell.value = value
	cell.font = Font(name=font, size=size, bold=bold)
	cell.alignment = align
	cell.border = BOX
	if fill:
		cell.fill = fill
	return cell


def _merge(ws, r1, c1, r2, c2):
	if (r1, c1) != (r2, c2):
		ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)


def _fit_heights(ws, first, last, widths, minimum=21, line=15.5):
	"""Excel doesn't grow rows for wrapped text written by openpyxl; estimate it."""
	merged = set()
	for rng in ws.merged_cells.ranges:
		if rng.max_row > rng.min_row:
			merged |= {(r, c) for r in range(rng.min_row, rng.max_row + 1) for c in range(rng.min_col, rng.max_col + 1)}
	for r in range(first, last + 1):
		lines = 1
		for c in range(1, ws.max_column + 1):
			v = ws.cell(r, c).value
			if v is None or (r, c) in merged:
				continue
			width = widths.get(ws.cell(r, c).column_letter, 10)
			per_line = max(4, int(width * 0.95))
			lines = max(lines, sum(max(1, math.ceil(len(part) / per_line)) for part in str(v).split("\n")))
		ws.row_dimensions[r].height = max(minimum, lines * line + 6)


def _send(wb, filename):
	buf = BytesIO()
	wb.save(buf)
	frappe.response["filename"] = filename
	frappe.response["filecontent"] = buf.getvalue()
	frappe.response["type"] = "binary"


def _safe_filename(text):
	return re.sub(r"[^A-Za-z0-9 _.-]+", "", text).strip() or "sheet"


def file_content(file_url):
	if not file_url:
		frappe.throw(_("Attach the Excel sheet first."))
	return frappe.get_doc("File", {"file_url": file_url}).get_content()


def _grid(content):
	"""Cell values as a list of rows (15+ columns); a cell merged down a column
	(Sl. No., Date, Venue, Year…) carries its value into every row it covers."""
	try:
		wb = load_workbook(BytesIO(content), data_only=True)
	except Exception:
		frappe.throw(_("This is not an Excel (.xlsx) file."))
	ws = wb.active
	width = max(ws.max_column, 15)
	grid = [list(r) + [None] * (width - len(r)) for r in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=width, values_only=True)]
	for rng in ws.merged_cells.ranges:
		if rng.min_col == rng.max_col and rng.max_row > rng.min_row:
			v = grid[rng.min_row - 1][rng.min_col - 1]
			for r in range(rng.min_row, rng.max_row):
				grid[r][rng.min_col - 1] = v
	return grid


def _parse_date(value, ref=None):
	"""19.09.2026 / a date cell / Monday, 21st September 2026 / 8th Sept 2026."""
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	text = _text(value)
	if not text or not re.search(r"\d", text):
		return None
	m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", text)
	if m:
		d, mth, y = (int(x) for x in m.groups())
		try:
			return date(y + 2000 if y < 100 else y, mth, d)
		except ValueError:
			return None
	if not re.search(r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", text, re.I):
		return None
	from dateutil import parser

	ref = getdate(ref) if ref else getdate()
	try:
		return parser.parse(text, fuzzy=True, dayfirst=True, default=datetime(ref.year, ref.month, 1)).date()
	except (ValueError, OverflowError):
		return None


def _course_index(term):
	"""Normalized course name / code / ID -> Course; courses taught in the term win."""
	index = {}
	taught = set(frappe.get_all("Classes", filters={"academic_term": term}, pluck="course", distinct=True)) if term else set()
	courses = frappe.get_all("Course", fields=["name", "course_name", "course_code"])
	for c in sorted(courses, key=lambda c: c.name in taught):
		for k in (c.course_name, c.course_code, c.name):
			if _norm(k):
				index[_norm(k)] = c.name
	return index


def _faculty_index():
	index = {}
	for f in frappe.get_all("Faculty", fields=["name", "first_name", "last_name", "faculty_id"]):
		for k in (" ".join(filter(None, [f.first_name, f.last_name])), f.faculty_id, str(f.name)):
			if _norm(k):
				index[_norm(k)] = f.name
	return index


def _year_labels(term):
	"""Course -> "<Programme> <year> Year" from its Classes, for rows without a Year."""
	out = {}
	if term:
		for c in frappe.get_all("Classes", filters={"academic_term": term}, fields=["course", "programme", "year_no"], order_by="programme"):
			if c.course not in out and c.programme:
				year = ROMAN.get(c.year_no) or (str(c.year_no) if c.year_no else "")
				out[c.course] = f"{c.programme} {year} Year" if year else c.programme
	return out


# ── Exam timetable (classroom allocation sheet) ───────────────────────────────

def timetable_entries(plan):
	"""The plan's course schedule rows as sheet lines, by date and session."""
	term = plan.term
	names = dict(frappe.get_all("Course", filters={"name": ["in", [r.course for r in plan.course_schedules if r.course] or [""]]},
	                            fields=["name", "course_name"], as_list=True))
	years = _year_labels(term)
	out = []
	for r in plan.course_schedules:
		if not r.exam_date:
			continue
		out.append(frappe._dict(
			exam_date=getdate(r.exam_date), session=_session_of(r), start_time=r.start_time, idx=r.idx,
			venue=r.venue or r.hall or "", year=r.programme_year or years.get(r.course, ""),
			paper=r.paper or names.get(r.course) or r.course or "",
			id_from=r.id_from or "", id_to=r.id_to or "",
			invigilator=_faculty_label(r.invigilator) if r.invigilator else (r.invigilator_name or ""),
		))
	out.sort(key=lambda e: (e.exam_date, SESSIONS.index(e.session), e.idx))
	return out


def _date_span(days):
	a, b = days[0], days[-1]
	if a == b:
		return f"{_ordinal(a.day)} {a.strftime('%B %Y')}"
	if (a.year, a.month) == (b.year, b.month):
		return f"{_ordinal(a.day)} to {_ordinal(b.day)} {b.strftime('%B %Y')}"
	return f"{_ordinal(a.day)} {a.strftime('%B')} to {_ordinal(b.day)} {b.strftime('%B %Y')}"


def timetable_workbook(exam_plan):
	plan = frappe.get_doc("Exam Plan", exam_plan)
	entries = timetable_entries(plan)
	days = sorted({e.exam_date for e in entries})

	wb = Workbook()
	ws = wb.active
	ws.title = "Sheet1"
	for col, w in TT_WIDTHS.items():
		ws.column_dimensions[col].width = w
	last_col = 15

	# 1 blank band, 2 title, 3 header
	for c in range(1, last_col + 1):
		_cell(ws, 1, c)
	_merge(ws, 1, 1, 1, last_col)
	ws.row_dimensions[1].height = 22.5
	title = _("{0} End-Term Examination classroom allocation sheet").format(plan.term or plan.exam_name)
	if days:
		title += f" ({_date_span(days)})"
	for c in range(1, last_col + 1):
		_cell(ws, 2, c, bold=True, fill=GREY)
	ws.cell(2, 1).value = title
	_merge(ws, 2, 1, 2, last_col)
	ws.row_dimensions[2].height = 21

	starts = {s: Counter(_hhmm(e.start_time) for e in entries if e.session == s and e.start_time).most_common(1) for s in SESSIONS}
	start = {s: (starts[s][0][0] if starts[s] else SESSION_TIMES[s]) for s in SESSIONS}
	header = ["Sl. No.", "Date", "Venue", "Year", f"Forenoon Session ({_ampm(start['Forenoon'])})", "ID Nos. \nFrom", "ID Nos.\nTo", "Invigilator",
	          "Date", "Venue", "Year", f"Afternoon Session \n({_ampm(start['Afternoon'])})", "ID Nos. \nFrom", "ID Nos.\nTo", "Invigilator"]
	for c, h in enumerate(header, 1):
		_cell(ws, 3, c, h, bold=True, fill=HEAD_GREY)
	ws.row_dimensions[3].height = 38.25
	ws.freeze_panes = "A4"

	r = 4
	for n, day in enumerate(days, 1):
		for c in range(1, last_col + 1):
			_cell(ws, r, c, bold=True, fill=GREY)
		ws.cell(r, 1).value = _long_date(day)
		_merge(ws, r, 1, r, last_col)
		ws.row_dimensions[r].height = 18.75
		r += 1

		sides = {s: [e for e in entries if e.exam_date == day and e.session == s] for s in SESSIONS}
		k = max(1, *(len(v) for v in sides.values()))
		for i in range(k):
			for c in range(1, last_col + 1):
				_cell(ws, r + i, c)
		day_text = f"{day.strftime('%d.%m.%Y')}\n{day.strftime('%A')}"
		for c, v in ((1, n), (2, day_text), (9, day_text)):
			_cell(ws, r, c, v, bold=True, align=TOP)
			_merge(ws, r, c, r + k - 1, c)
		for session, lines in sides.items():
			_write_side(ws, r, k, lines, SIDE_COL[session])
		_fit_heights(ws, r, r + k - 1, TT_WIDTHS)
		r += k

	return wb


def _write_side(ws, r, k, lines, c0):
	"""Venue, Year, paper, From, To, Invigilator of one session; a room spanning
	several lines is one merged Venue cell, "All students" spans From and To."""
	for i, e in enumerate(lines):
		row = r + i
		for j, v in enumerate((e.venue, e.year, e.paper, e.id_from, e.id_to, e.invigilator)):
			if v:
				ws.cell(row, c0 + j).value = v
		if e.id_from and not e.id_to:
			_merge(ws, row, c0 + 3, row, c0 + 4)
	i = 0
	while i < len(lines):
		j = i
		while j + 1 < len(lines) and lines[j + 1].venue and lines[j + 1].venue == lines[i].venue:
			j += 1
		if lines[i].venue:
			_merge(ws, r + i, c0, r + j, c0)
		i = j + 1
	if len(lines) < k:
		_merge(ws, r + len(lines), c0, r + k - 1, c0 + 5)


def parse_timetable(content):
	"""Lines of a classroom allocation sheet: [{sheet_row, exam_date, session,
	start_time, venue, year, paper, id_from, id_to, invigilator}], issues."""
	grid = _grid(content)
	issues, lines = [], []
	head = next((i for i, row in enumerate(grid)
	             if _norm(row[0]).startswith("sl") and any("session" in _norm(v) for v in row)), None)
	if head is None:
		frappe.throw(_("No header row found. The sheet needs the header: Sl. No. | Date | Venue | Year | Forenoon Session (10.00 AM) | ID Nos. From | ID Nos. To | Invigilator | Date | Venue | Year | Afternoon Session (2.30 PM) | …"))

	def header_time(text, default):
		m = re.search(r"(\d{1,2})(?:[.:](\d{2}))?\s*([AaPp])\.?\s*[Mm]", _text(text))
		if not m:
			return default
		h, mi = int(m.group(1)) % 12, int(m.group(2) or 0)
		return f"{h + (12 if m.group(3).lower() == 'p' else 0):02d}:{mi:02d}"

	start = {"Forenoon": header_time(grid[head][4], SESSION_TIMES["Forenoon"]),
	         "Afternoon": header_time(grid[head][11], SESSION_TIMES["Afternoon"])}

	day = None
	last_venue = {}
	previous = {}
	for i in range(head + 1, len(grid)):
		row = [_text(v) if not isinstance(v, (date, datetime)) else v for v in grid[i][:15]]
		if not any(row):
			continue
		if row[0] and not isinstance(grid[i][0], (int, float)) and not any(row[1:]):
			day = _parse_date(row[0]) or day        # "Saturday, 19th September 2026"
			last_venue, previous = {}, {}
			continue
		for session, c0 in SIDE_COL.items():
			venue, year, paper, id_from, id_to, invig = row[c0 - 1:c0 + 5]
			when = _parse_date(row[c0 - 2]) or _parse_date(row[1]) or day
			if not paper:
				if venue:
					last_venue[session] = venue
				continue
			venue = venue or last_venue.get(session, "")
			last_venue[session] = venue
			line = frappe._dict(sheet_row=i + 1, exam_date=when, session=session, start_time=start[session],
			                    venue=venue, year=year, paper=paper, id_from=id_from,
			                    id_to=id_to if id_to != id_from else "", invigilator=invig)
			sig = (when, venue, year, paper, id_from, id_to)
			if previous.get(session) == sig:      # a paper merged down several rows
				continue
			previous[session] = sig
			if not when:
				issues.append({"sheet_row": i + 1, "level": "error", "message": _("{0}: no date for this line, skipped.").format(paper)})
				continue
			lines.append(line)
	return lines, issues


def resolve_timetable(plan, lines, duration_hours=3):
	"""Sheet lines -> Exam Course Schedule rows, matching rooms (Venue Master),
	papers (Course) and invigilators (Faculty); unknown text is kept as written."""
	venues = {_key(v): v for v in frappe.get_all("Venue Master", pluck="name")}
	capacity = dict(frappe.get_all("Venue Master", fields=["name", "capacity"], as_list=True))
	courses = _course_index(plan.term)
	faculty = _faculty_index()
	rows, issues = [], []
	for ln in lines:
		venue_text, year = ln.venue, ln.year
		if _key(venue_text) not in venues and _key(year) in venues:   # Venue and Year typed the other way round
			venue_text, year = year, venue_text
		venue = venues.get(_key(venue_text))
		course = courses.get(_norm(ln.paper))
		invigilator = faculty.get(_norm(ln.invigilator)) if ln.invigilator else None
		end = (datetime.combine(date.today(), datetime.strptime(ln.start_time, "%H:%M").time())
		       + timedelta(hours=flt(duration_hours) or 3)).strftime("%H:%M")
		if venue_text and not venue:
			issues.append({"sheet_row": ln.sheet_row, "level": "warning",
			               "message": _("Room {0} is not in Venue Master: kept as written, not checked for clashes or seats.").format(venue_text)})
		if not course:
			issues.append({"sheet_row": ln.sheet_row, "level": "info",
			               "message": _("{0} is not a Course name: kept as the paper text.").format(ln.paper.replace("\n", " "))})
		if ln.invigilator and not invigilator:
			issues.append({"sheet_row": ln.sheet_row, "level": "info",
			               "message": _("Invigilator {0} is not a Faculty record: kept as written.").format(ln.invigilator)})
		rows.append({
			"course": course, "paper": ln.paper, "programme_year": year, "exam_date": ln.exam_date,
			"session": ln.session, "start_time": ln.start_time, "end_time": end,
			"venue": venue, "hall": None if venue else (venue_text or None),
			"seat_capacity": capacity.get(venue) if venue else None,
			"id_from": ln.id_from or None, "id_to": ln.id_to or None,
			"invigilator": invigilator, "invigilator_name": None if invigilator else (ln.invigilator or None),
			"sheet_row": ln.sheet_row,
		})
	return rows, issues


def _check_rows(plan, rows):
	plan.set("course_schedules", [{k: v for k, v in r.items() if k != "sheet_row"} for r in rows])
	for i, r in enumerate(plan.course_schedules, 1):
		r.idx = i
	return check_exam_schedule(plan)


def _line_text(r):
	"""24.09.2026 Forenoon · NAB-001 · Legal Methods · L26002–L26085"""
	when = " ".join(filter(None, [getdate(r["exam_date"]).strftime("%d.%m.%Y") if r.get("exam_date") else "", r.get("session") or ""]))
	ids = "–".join(filter(None, [r.get("id_from"), r.get("id_to")]))
	return " · ".join(filter(None, [when, r.get("venue") or r.get("hall"), (r.get("paper") or r.get("course") or "").replace("\n", " "), ids]))


def _group(issues):
	"""One note per message, with every sheet row it applies to (for the preview)."""
	grouped = {}
	for x in issues:
		grouped.setdefault((x["level"], x["message"]), []).append(x["sheet_row"])
	order = {"error": 0, "warning": 1, "info": 2}
	return sorted(({"level": lv, "message": msg, "sheet_rows": sorted(set(r)), "sheet_row": min(r)}
	               for (lv, msg), r in grouped.items()), key=lambda x: (order[x["level"]], x["sheet_row"]))


def timetable_issues(exam_plan, content, duration_hours=3):
	"""Sheet lines -> rows and every issue per sheet row (with its line)."""
	plan = frappe.get_doc("Exam Plan", exam_plan)
	lines, issues = parse_timetable(content)
	rows, more = resolve_timetable(plan, lines, duration_hours)
	text = {r["sheet_row"]: _line_text(r) for r in rows}
	issues += more
	check = _check_rows(plan, rows)
	for bucket, level in (("errors", "error"), ("warnings", "warning")):
		for x in check[bucket]:
			issues.append({"sheet_row": rows[x["row"] - 1]["sheet_row"], "level": level, "message": x["message"]})
	for x in issues:
		x.setdefault("line", text.get(x["sheet_row"], ""))
	return plan, rows, issues


def import_timetable(exam_plan, content, duration_hours=3, apply=False, file_url=None):
	"""Read a classroom allocation sheet. Without apply: what would be imported,
	with the timetable checks. With apply: replace the plan's exam timetable with
	the lines that pass the checks; lines with a problem are skipped and every
	import is written to an Exam Sheet Import Log."""
	plan, rows, issues = timetable_issues(exam_plan, content, duration_hours)
	total = len(rows) + sum(1 for x in issues if x["level"] == "error" and x["sheet_row"] not in {r["sheet_row"] for r in rows})
	bad = {x["sheet_row"] for x in issues if x["level"] == "error"}
	keep = [r for r in rows if r["sheet_row"] not in bad]
	summary = {
		"lines": total, "days": len({r["exam_date"] for r in rows}),
		"courses": len({r["course"] for r in rows if r["course"]}),
		"text_only": sum(1 for r in rows if not r["course"]),
		"error_lines": total - len(keep), "valid_lines": len(keep),
		"issues": _group(issues),
	}
	if not apply:
		return summary
	# leaving lines out can't add clashes, but the rest of a shared, over-full room may still fail
	for _ in range(5):
		check = _check_rows(plan, keep)
		if not check["errors"]:
			break
		more = {keep[x["row"] - 1]["sheet_row"] for x in check["errors"]}
		issues += [{"sheet_row": keep[x["row"] - 1]["sheet_row"], "level": "error", "message": x["message"],
		            "line": _line_text(keep[x["row"] - 1])} for x in check["errors"]]
		keep = [r for r in keep if r["sheet_row"] not in more]
	if not keep:
		log = write_import_log("Exam Timetable", exam_plan, file_url, total, 0, issues)
		frappe.db.commit()
		frappe.throw(_("No line of the sheet can be imported. See {0}.").format(
			f'<a href="/desk/exam-sheet-import-log/{log}">{log}</a>'))
	plan.save()
	summary.update(imported=len(keep), skipped=total - len(keep),
	               log=write_import_log("Exam Timetable", exam_plan, file_url, total, len(keep), issues))
	frappe.db.commit()
	return summary


def _row_no(v):
	return int(v) if str(v).isdigit() else 10 ** 9


def write_import_log(sheet, exam_plan, file_url, total, imported, issues):
	log = frappe.new_doc("Exam Sheet Import Log")
	log.update({
		"sheet": sheet, "exam_plan": exam_plan, "import_file": file_url,
		"status": "Failed" if not imported else ("Imported with skipped lines" if imported < total else "Imported"),
		"imported_by": frappe.session.user, "imported_on": frappe.utils.now_datetime(),
		"total_lines": total, "imported_lines": imported, "skipped_lines": total - imported,
	})
	order = {"error": 0, "warning": 1, "info": 2}
	# errors and warnings only: "kept as text" notes would bury them
	for x in sorted((x for x in issues if x["level"] != "info"), key=lambda x: (order[x["level"]], _row_no(x["sheet_row"]))):
		log.append("issues", {"sheet_row": str(x["sheet_row"]), "level": x["level"], "line": x.get("line", ""), "message": x["message"]})
	log.insert(ignore_permissions=True)
	return log.name


def issues_workbook(issues, title):
	"""Problems of an import, one line per sheet row: Sheet row | Level | Line | Problem."""
	wb = Workbook()
	ws = wb.active
	ws.title = "Problems"
	widths = {"A": 11, "B": 10, "C": 70, "D": 80}
	for col, w in widths.items():
		ws.column_dimensions[col].width = w
	_cell(ws, 1, 1, title, bold=True, size=12, align=LEFT)
	ws.merge_cells("A1:D1")
	for c, h in enumerate(("Sheet row", "Level", "Line", "Problem"), 1):
		_cell(ws, 2, c, h, bold=True, fill=HEAD_GREY, size=11)
	order = {"error": 0, "warning": 1, "info": 2}
	rows = sorted((x for x in issues if x["level"] != "info"), key=lambda x: (order.get(x["level"], 3), _row_no(x["sheet_row"])))
	for r, x in enumerate(rows, 3):
		for c, v in enumerate((x["sheet_row"], x["level"], x.get("line", ""), x["message"]), 1):
			_cell(ws, r, c, v, size=10, align=LEFT)
		if x["level"] == "error":
			ws.cell(r, 2).fill = PatternFill("solid", fgColor="FDE6E8")
	ws.freeze_panes = "A3"
	_fit_heights(ws, 3, len(rows) + 2, widths, minimum=15, line=13)
	return wb


# ── Continuing Evaluation Schedule ────────────────────────────────────────────

def _reexam_components():
	return set(frappe.get_all("Exam Component", filters={"component_type": "Re Exam"}, pluck="name"))


def _schema_configs(course, exam_plan):
	from slcm.slcm.doctype.exam_assessment_schedule.exam_assessment_schedule import _get_mapped_schema

	schema = _get_mapped_schema(course, exam_plan)
	return frappe.get_all(
		"Schema Assessment Config", filters={"parent": schema, "parenttype": "Evaluation Schema"},
		fields=["label", "component", "assessment_type", "maximum_marks"], order_by="idx asc",
	) if schema else []


def _marks_text(value):
	return f"{flt(value):g} marks" if flt(value) else ""


def _date_text(value):
	if not value:
		return ""
	d = getdate(value)
	return f"{_ordinal(d.day)} {d.strftime('%b %Y')}"


def _plan_schedules(plan):
	"""Active Exam Assessment Schedules of the plan's term (this plan's or no plan's)."""
	return [s for s in frappe.get_all(
		"Exam Assessment Schedule", filters={"term": plan.term, "status": "Active"},
		fields=["name", "programme", "exam_plan"], order_by="programme asc, creation asc",
	) if s.exam_plan in (None, "", plan.name)] if plan.term else []


def assessment_grid(exam_plan):
	"""One line per course, as on the sheet: evaluations (label, marks, date),
	SGD and remarks. A course taught in several programmes shows once.
	Mapped courses without assessments yet show their schema's (suggested)."""
	plan = frappe.get_doc("Exam Plan", exam_plan)
	reexam = _reexam_components()
	lines = {}
	for s in _plan_schedules(plan):
		doc = frappe.get_doc("Exam Assessment Schedule", s.name)
		configs = {}
		for it in doc.assessments:
			if it.component in reexam:
				continue
			line = lines.setdefault(it.course, frappe._dict(course=it.course, programmes=[], evaluations=[], sgd="", remarks="", source=doc.name))
			if s.programme not in line.programmes:
				line.programmes.append(s.programme)
			if line.source != doc.name:
				continue
			if it.course not in configs:
				configs[it.course] = {(c.component, c.assessment_type): c.maximum_marks for c in _schema_configs(it.course, exam_plan)}
			line.evaluations.append({
				"label": it.assessment_label or "",
				"marks": it.marks_text or _marks_text(configs[it.course].get((it.component, it.assessment_type))),
				"date": it.date_text or _date_text(it.assessment_date),
			})
		for n in doc.get("course_notes") or []:
			if n.course in lines and lines[n.course].source == doc.name:
				lines[n.course].sgd, lines[n.course].remarks = n.sgd or "", n.remarks or ""

	mapped = frappe.get_all("Course Schema Assignment", filters={"exam_plan": exam_plan}, pluck="course")
	for course in mapped:
		if course not in lines:
			lines[course] = frappe._dict(course=course, programmes=[], sgd="", remarks="", suggested=1, evaluations=[
				{"label": c.label or c.assessment_type or c.component, "marks": _marks_text(c.maximum_marks), "date": ""}
				for c in _schema_configs(course, exam_plan) if c.component not in reexam
			])
	names = dict(frappe.get_all("Course", filters={"name": ["in", list(lines) or [""]]}, fields=["name", "course_name"], as_list=True))
	out = []
	for line in lines.values():
		line.course_name = names.get(line.course, line.course)
		line.pop("source", None)
		out.append(line)
	out.sort(key=lambda x: _norm(x.course_name))
	return out


def _term_programmes(course, term):
	return frappe.get_all("Classes", filters={"course": course, "academic_term": term, "programme": ["is", "set"]},
	                      pluck="programme", distinct=True, order_by="programme")


def save_assessment_grid(exam_plan, lines):
	"""Write sheet lines into the Exam Assessment Schedule of every programme
	teaching each course (made when missing). Evaluations keep their schema
	assessment (component / type) by label, then by order; assessments that
	already have marks are never removed."""
	plan = frappe.get_doc("Exam Plan", exam_plan)
	if not plan.term:
		frappe.throw(_("Set the Exam Plan's Academic Term first."))
	academic_year = frappe.db.get_value("Academic Term", plan.term, "academic_year")
	term_start = frappe.db.get_value("Academic Term", plan.term, "term_start_date")
	reexam = _reexam_components()
	docs, warnings, saved = {}, [], 0

	def schedule_for(programme):
		if programme not in docs:
			name = frappe.db.get_value("Exam Assessment Schedule", {"term": plan.term, "programme": programme, "status": "Active"}, "name")
			doc = frappe.get_doc("Exam Assessment Schedule", name) if name else frappe.new_doc("Exam Assessment Schedule")
			if not name:
				doc.update({"academic_year": academic_year, "term": plan.term, "programme": programme, "status": "Active"})
			doc.exam_plan = doc.exam_plan or exam_plan
			docs[programme] = doc
		return docs[programme]

	course_names = {}
	for line in lines:
		course = line.get("course")
		if not course:
			continue
		course_names[course] = course_names.get(course) or frappe.db.get_value("Course", course, "course_name")
		programmes = _term_programmes(course, plan.term)
		if not programmes:
			warnings.append(_("{0}: no Class teaches it in {1}, not saved.").format(course_names[course] or course, plan.term))
			continue
		for p in programmes:
			warnings += _apply_course(schedule_for(p), course, course_names[course], line, reexam, term_start)
		saved += 1
	for doc in docs.values():
		doc.save()
	frappe.db.commit()
	return {"courses": saved, "schedules": sorted(d.name for d in docs.values()), "warnings": sorted(set(warnings))}


def _apply_course(doc, course, course_name, line, reexam, term_start):
	evals = [e for e in (line.get("evaluations") or []) if _text(e.get("label")) not in ("", "-")]
	mine = [it for it in doc.assessments if it.course == course and it.component not in reexam]
	used, matched, warnings = set(), {}, []
	end_term = {id(it): _is_end_term(it.component, it.assessment_type, it.assessment_label) for it in mine}
	same_kind = lambda e, it: _is_end_term(e["label"]) == end_term[id(it)]

	def take(i, it):
		matched[i] = it
		used.add(id(it))

	for i, e in enumerate(evals):                      # same label
		it = next((it for it in mine if id(it) not in used and _norm(it.assessment_label) == _norm(e["label"])), None)
		if it:
			take(i, it)
	for i, e in enumerate(evals):                      # shares 2+ words, e.g. End-term examination ~ End Term Paper
		if i in matched:
			continue
		scored = [(len(_words(e["label"]) & (_words(it.assessment_label) | _words(it.assessment_type))), it) for it in mine
		          if id(it) not in used and same_kind(e, it)]
		best = max(scored, key=lambda x: x[0], default=(0, None))
		if best[0] >= 2:
			take(i, best[1])
	for i, e in enumerate(evals):                      # then in order
		if i not in matched:
			it = next((it for it in mine if id(it) not in used and same_kind(e, it)), None)
			if it:
				take(i, it)

	ordered = []
	for i, e in enumerate(evals):
		it = matched.get(i) or doc.append("assessments", {"course": course, "course_name": course_name})
		date_text = _text(e.get("date"))
		date_text = "" if date_text == "-" else date_text
		if it.date_text != date_text or not it.name:
			parsed = _parse_date(date_text, term_start)
			if parsed or date_text:
				it.assessment_date = datetime.combine(parsed, datetime.min.time()) if parsed else None
		it.assessment_label = _text(e["label"])
		it.marks_text = "" if _text(e.get("marks")) == "-" else _text(e.get("marks"))
		it.date_text = date_text
		if not it.component:
			warnings.append(_("{0} › {1}: no matching assessment in the Evaluation Schema, so marks entered for it are not counted in the result.").format(
				course_name or course, it.assessment_label.split("\n")[0]))
		ordered.append(it)
	for it in mine:
		if id(it) in used:
			continue
		if it.name and frappe.db.exists("Student Assessment Marks", {"schedule_item": it.name}):
			warnings.append(_("{0} › {1} has marks entered, so it was kept.").format(course_name or course, it.assessment_label))
			ordered.append(it)

	# the course's lines in sheet order where the course was; re-exam rows after them
	rows = list(doc.assessments)
	first = next((k for k, it in enumerate(rows) if it.course == course), len(rows))
	before = [it for it in rows[:first] if it.course != course]
	after = [it for it in rows[first:] if it.course != course]
	doc.set("assessments", before + ordered + [it for it in rows if it.course == course and it.component in reexam] + after)
	for k, it in enumerate(doc.assessments, 1):
		it.idx = k

	note = next((n for n in doc.get("course_notes") or [] if n.course == course), None)
	sgd, remarks = (_text(line.get(k)) for k in ("sgd", "remarks"))
	sgd, remarks = ("" if v == "-" else v for v in (sgd, remarks))
	if sgd or remarks:
		note = note or doc.append("course_notes", {"course": course})
		note.sgd, note.remarks = sgd, remarks
	elif note:
		doc.set("course_notes", [n for n in doc.course_notes if n is not note])
	return warnings


def assessment_workbook(exam_plan, blank=False):
	lines = assessment_grid(exam_plan)
	groups = max([4] + [len(x.evaluations) for x in lines])
	wb = Workbook()
	ws = wb.active
	ws.title = "Sheet"
	header = ["Subject"]
	for n in range(1, groups + 1):
		header += [f"Evaluation {n}/Assessment {n}", "Marks", "Date"]
	header += ["SGD", ""]
	widths = dict(CE_WIDTHS)
	if groups > 4:
		from openpyxl.utils import get_column_letter

		widths = {get_column_letter(1): 19.4}
		for n in range(groups):
			for j, w in enumerate((31.3, 10, 18.7)):
				widths[get_column_letter(2 + n * 3 + j)] = w
		widths[get_column_letter(2 + groups * 3)] = 43.3
		widths[get_column_letter(3 + groups * 3)] = 23.4
	for col, w in widths.items():
		ws.column_dimensions[col].width = w
	for c, h in enumerate(header, 1):
		cell = _cell(ws, 1, c, h, bold=True, font="Cambria", align=Alignment(horizontal="center", vertical="center", wrap_text=True))
		if not h:
			cell.border = Border()
	for r, line in enumerate(lines, 2):
		values = [line.course_name]
		for n in range(groups):
			e = line.evaluations[n] if n < len(line.evaluations) and not blank else {}
			values += [e.get("label", ""), e.get("marks", ""), e.get("date", "")]
		values += ["" if blank else line.sgd, "" if blank else line.remarks]
		for c, v in enumerate(values, 1):
			_cell(ws, r, c, v, size=10, align=LEFT)
	if lines:
		_fit_heights(ws, 2, len(lines) + 1, widths, minimum=15, line=13)
	return wb


def parse_assessment_sheet(content):
	"""Lines of a Continuing Evaluation Schedule sheet: [{sheet_row, subject,
	evaluations: [{label, marks, date}], sgd, remarks}]."""
	grid = _grid(content)
	head = next((i for i, row in enumerate(grid) if _norm(row[0]) == "subject"), None)
	if head is None:
		frappe.throw(_("No header row found. The sheet starts with: Subject | Evaluation 1/Assessment 1 | Marks | Date | … | SGD"))
	header = [_norm(v) for v in grid[head]]
	groups, c = [], 1
	while c < len(header) and (header[c].startswith("evaluation") or header[c].startswith("assessment")):
		groups.append(c)
		c += 3
	sgd_col = next((j for j, h in enumerate(header) if h == "sgd"), c)
	lines = []
	for i in range(head + 1, len(grid)):
		row = grid[i]
		subject = _text(row[0])
		if not subject:
			continue
		cell = lambda j: (_date_text(row[j]) if isinstance(row[j], (date, datetime)) else _text(row[j])) if j < len(row) else ""
		evals = [{"label": cell(g), "marks": cell(g + 1), "date": cell(g + 2)} for g in groups]
		lines.append({
			"sheet_row": i + 1, "subject": subject,
			"evaluations": [e for e in evals if e["label"] not in ("", "-")],
			"sgd": cell(sgd_col), "remarks": cell(sgd_col + 1),
		})
	return lines


def assessment_issues(exam_plan, content, mapping=None):
	"""Sheet lines with their Course (name, code or ID; or the mapping
	{subject: course} picked in the preview); a subject without one is an error."""
	plan = frappe.get_doc("Exam Plan", exam_plan)
	lines = parse_assessment_sheet(content)
	index = _course_index(plan.term)
	mapping = mapping or {}
	issues = []
	for line in lines:
		line["course"] = mapping.get(line["subject"]) or index.get(_norm(line["subject"]))
		if not line["course"]:
			issues.append({"sheet_row": line["sheet_row"], "level": "error", "line": line["subject"],
			               "message": _("{0} is not a Course of this term: skipped. Pick the course in the import preview.").format(line["subject"])})
	return plan, lines, issues


def import_assessment_sheet(exam_plan, content, mapping=None, apply=False, file_url=None):
	"""Preview, or (apply) save the subjects that have a Course; the others are
	skipped and the import is written to an Exam Sheet Import Log."""
	plan, lines, issues = assessment_issues(exam_plan, content, mapping)
	unmatched = [{"sheet_row": x["sheet_row"], "subject": x["line"]} for x in issues]
	out = {"lines": len(lines), "matched": sum(1 for x in lines if x["course"]), "unmatched": unmatched,
	       "rows": [{k: x[k] for k in ("sheet_row", "subject", "course")} | {"evaluations": len(x["evaluations"])} for x in lines]}
	if apply:
		good = [x for x in lines if x["course"]]
		if not good:
			frappe.throw(_("No subject of the sheet is matched to a course. Pick the courses in the preview."))
		out.update(save_assessment_grid(exam_plan, good))
		issues += [{"sheet_row": "", "level": "warning", "line": "", "message": w} for w in out["warnings"]]
		out.update(saved=1, imported=len(good), skipped=len(lines) - len(good),
		           log=write_import_log("Continuing Evaluation Schedule", exam_plan, file_url, len(lines), len(good), issues))
		frappe.db.commit()
	else:
		taught = frappe.get_all("Classes", filters={"academic_term": plan.term}, pluck="course", distinct=True) if plan.term else []
		out["courses"] = frappe.get_all("Course", filters={"name": ["in", taught or [""]]}, fields=["name", "course_name"], order_by="course_name")
	return out
