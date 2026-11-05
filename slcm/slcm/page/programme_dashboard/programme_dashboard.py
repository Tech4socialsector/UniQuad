# Programme Dashboard: count cards for the academic calendar, programme structure,
# students, classes, the time table and promotion runs. Built like the Attendance
# Dashboard and shares its helpers, so every count is permission-checked and a
# doctype the user can't read is left out.

import csv
import io

import frappe
from frappe import _
from frappe.utils import add_days, cint, today

from slcm.slcm.page.attendance_dashboard.attendance_dashboard import (
	_card,
	_count,
	_group,
	clean_filters,
	current_term,
	drilldown,
)

EXPORT_LIMIT = 20000

# Records view inside the drill-down: the columns shown (after ID) for each doctype
RECORD_FIELDS = {
	"Academic Year": ["academic_year_name", "year_start_date", "year_end_date", "status", "is_current_year"],
	"Academic Term": ["academic_year", "term_start_date", "term_end_date", "status"],
	"Programme": ["program_name", "level_of_study", "program_duration", "program_status"],
	"SLCM Batch": ["batch_name", "batch_code", "academic_year", "status", "total_enrolled_count"],
	"Section": ["section_name"],
	"Course": ["course_name", "course_code", "course_type", "credit_value", "status"],
	"Student Master": ["first_name", "registration_id", "programme_of_study", "section", "batch", "student_status"],
	"Student Enrollment": ["student", "student_name", "program", "section", "batch", "status", "enrollment_date"],
	"Classes": ["course_name", "programme", "academic_term", "section", "class_type", "faculty_name", "total_students"],
	"Time Table": ["schedule_date", "from_time", "to_time", "course", "section", "programme", "instructor_name", "venue", "session_status"],
	"Promotion Run": ["program", "source_term", "target_term", "status", "total_students", "promoted_count", "skipped_count", "run_on"],
}

# Drill-down: how a card's records split up. doctype -> (group by, split columns by, group label)
DRILL = {
	"Academic Year": ("name", "status", ("Academic year", "academic years")),
	"Academic Term": ("academic_year", "status", ("Academic year", "academic years")),
	"Programme": ("level_of_study", "program_status", ("Level", "levels")),
	"SLCM Batch": ("academic_year", "status", ("Academic year", "academic years")),
	"Section": ("name", None, ("Section", "sections")),
	"Course": ("course_type", "status", ("Course type", "course types")),
	"Student Master": ("programme_of_study", "student_status", ("Programme", "programmes")),
	"Student Enrollment": ("program", "status", ("Programme", "programmes")),
	"Classes": ("programme", "class_type", ("Programme", "programmes")),
	"Time Table": ("class_name", "session_status", ("Class", "classes")),
	"Promotion Run": ("program", "status", ("Programme", "programmes")),
}


@frappe.whitelist()
def get_drilldown(doctype, filters=None):
	return drilldown(DRILL, doctype, filters)


def _check(doctype):
	if doctype not in DRILL or not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _columns(doctype):
	"""ID plus the RECORD_FIELDS the user may read (field-level permissions applied)."""
	meta = frappe.get_meta(doctype)
	permitted = set(meta.get_permitted_fieldnames())
	cols = [{"fieldname": "name", "label": _("ID"), "fieldtype": "Data"}]
	for f in RECORD_FIELDS.get(doctype, []):
		df = meta.get_field(f)
		if df and f in permitted:
			cols.append({"fieldname": f, "label": _(df.label), "fieldtype": df.fieldtype})
	return cols


def _records(doctype, filters, sort_by, sort_order, start, page_length):
	cols = _columns(doctype)
	if sort_by not in {c["fieldname"] for c in cols} | {"modified"}:
		sort_by = "modified"
	sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"
	t = f"`tab{doctype}`"
	rows = frappe.get_list(doctype, filters=filters, fields=[c["fieldname"] for c in cols],
		order_by=f"{t}.`{sort_by}` {sort_order}, {t}.`name` {sort_order}", start=start, page_length=page_length)
	return cols, rows, sort_by, sort_order


@frappe.whitelist()
def get_records(doctype, filters=None, sort_by=None, sort_order="desc", start=0, page_length=50):
	"""One page of the records behind a drill-down number, with the user's permissions applied."""
	_check(doctype)
	filters = clean_filters(doctype, filters)
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length), 1), 500)
	cols, rows, sort_by, sort_order = _records(doctype, filters, sort_by, sort_order, start, page_length)
	return {"columns": cols, "rows": rows, "total": _count(doctype, filters), "start": start,
		"page_length": page_length, "sort_by": sort_by, "sort_order": sort_order}


def _cell(v):
	"""CSV value; text that a spreadsheet would run as a formula is prefixed with a quote."""
	if v is None:
		return ""
	if isinstance(v, (int, float)):
		return v
	v = str(v)
	return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


@frappe.whitelist(methods=["POST"])
def export_drilldown(doctype, filters=None, view="records", sort_by=None, sort_order="desc"):
	"""CSV of the drill-down: its records, or its breakdown table. Same permissions as on screen."""
	_check(doctype)
	filters = clean_filters(doctype, filters)
	if view == "breakdown":
		r = drilldown(DRILL, doctype, filters)
		by_class = r["group"] == "class_name"
		header = [r["group_label"]] + ([_("Course"), _("Section"), _("Programme"), _("Trimester")] if by_class else [])
		header += r["splits"] + [_("Total")]
		rows = [[x["value"] or _("Not set")]
			+ ([x.get("course_name"), x.get("section"), x.get("programme"), x.get("academic_term")] if by_class else [])
			+ [x["split"].get(sp, 0) for sp in r["splits"]] + [x["total"]] for x in r["rows"]]
	else:
		if _count(doctype, filters) > EXPORT_LIMIT:
			frappe.throw(_("More than {0} records. Narrow the filters first.").format(EXPORT_LIMIT))
		cols, data, _sort, _order = _records(doctype, filters, sort_by, sort_order, 0, EXPORT_LIMIT)
		header = [c["label"] for c in cols]
		rows = [[d.get(c["fieldname"]) for c in cols] for d in data]

	out = io.StringIO()
	writer = csv.writer(out)
	writer.writerow([_cell(h) for h in header])
	writer.writerows([[_cell(v) for v in row] for row in rows])
	frappe.response["filename"] = f"{doctype} {today()}.csv"
	frappe.response["filecontent"] = "﻿" + out.getvalue()
	frappe.response["type"] = "download"


@frappe.whitelist()
def get_filter_options():
	return {
		"years": frappe.get_list("Academic Year", fields=["name", "is_current_year"], order_by="year_start_date desc", limit=100),
		"programmes": frappe.get_list("Programme", pluck="name", order_by="name asc", limit=500),
		"terms": frappe.get_list("Academic Term", fields=["name", "academic_year"], order_by="term_start_date desc", limit=200),
		"current_term": (current_term() or {}).get("name"),
	}


def _f(**pairs):
	"""Filters from field=values pairs: one value matches it, several match any of them; empty ones are skipped."""
	return {k: (v[0] if len(v) == 1 else ["in", v]) if isinstance(v, list) else v for k, v in pairs.items() if v}


def _values(doctype, value):
	"""A filter sent by the page: a JSON list (or one name) of existing `doctype` records."""
	if not value:
		return []
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value) if value.lstrip().startswith("[") else [value]
		except ValueError:
			value = None
	if not isinstance(value, list) or len(value) > 500 or not all(isinstance(v, str) and v for v in value):
		frappe.throw(_("Invalid filters"), frappe.ValidationError)
	value = list(dict.fromkeys(value))
	if len(frappe.get_all(doctype, filters={"name": ["in", value]}, pluck="name")) != len(value):
		frappe.throw(_("A filter no longer exists: {0}. Reset the filters and try again.").format(_(doctype)))
	return value


@frappe.whitelist()
def get_dashboard(programme=None, academic_year=None, academic_term=None):
	"""Each filter is a JSON list of names (or one name); empty means all."""
	d = today()
	programme = _values("Programme", programme)
	academic_year = _values("Academic Year", academic_year)
	academic_term = _values("Academic Term", academic_term)
	# trimesters must belong to the chosen years; with no year chosen, the trimesters' own years apply
	if academic_term:
		term_years = dict(frappe.get_all("Academic Term", filters={"name": ["in", academic_term]}, fields=["name", "academic_year"], as_list=True))
		if academic_year:
			academic_term = [t for t in academic_term if term_years.get(t) in academic_year]
			if not academic_term:
				frappe.throw(_("The selected trimesters are not in the selected academic years."))
		else:
			academic_year = sorted({y for y in term_years.values() if y})
	term_now = (current_term() or {}).get("name")
	# the "This term" card only makes sense when the current term is in a chosen year
	if term_now and academic_year and frappe.db.get_value("Academic Term", term_now, "academic_year") not in academic_year:
		term_now = None

	# name the running term only when it is among the terms counted
	if term_now and (not academic_term or term_now in academic_term):
		running_hint = term_now
	else:
		running_hint = _("current term is not in the filters") if (academic_term or academic_year) else _("no term covers today")

	year = _f(name=academic_year)
	term = _f(academic_year=academic_year, name=academic_term)
	prog = _f(name=programme)
	batch = _f(academic_year=academic_year)
	# Student Master's academic_year is the year of admission, so a year filter would hide current students
	stu = lambda **x: dict(_f(programme_of_study=programme), **x)
	enr = lambda **x: dict(_f(program=programme), **x)
	cls = lambda **x: dict(_f(programme=programme, academic_year=academic_year, academic_term=academic_term), **x)
	tt = lambda **x: dict(_f(programme=programme, academic_year=academic_year, academic_term=academic_term), **x)
	run = lambda **x: dict(_f(program=programme, source_academic_year=academic_year, source_term=academic_term), **x)
	not_cancelled = ["not in", ["Cancelled"]]

	groups = [
		_group(_("Academic calendar"), [
			_card(_("Academic years"), "Academic Year", year),
			_card(_("Current year"), "Academic Year", dict(year, is_current_year=1), _("marked as current")),
			_card(_("Academic terms"), "Academic Term", term),
			_card(_("Running now"), "Academic Term", dict(term, term_start_date=["<=", d], term_end_date=[">=", d]),
				running_hint),
			_card(_("Upcoming terms"), "Academic Term", dict(term, term_start_date=[">", d]), _("not started yet")),
		], _("follows the academic year and trimester")),
		_group(_("Programme structure"), [
			_card(_("Programmes"), "Programme", prog),
			_card(_("Active programmes"), "Programme", dict(prog, program_status="Active")),
			_card(_("Undergraduate"), "Programme", dict(prog, level_of_study="Undergraduate")),
			_card(_("Postgraduate"), "Programme", dict(prog, level_of_study="Postgraduate")),
			_card(_("Research"), "Programme", dict(prog, level_of_study="Research Course"), _("Ph.D")),
			_card(_("Sections"), "Section", {}),
		], _("programme filter only")),
		_group(_("Batches & courses"), [
			_card(_("Active batches"), "SLCM Batch", dict(batch, status="Active")),
			_card(_("Planned batches"), "SLCM Batch", dict(batch, status="Planned"), _("not started yet")),
			_card(_("Completed batches"), "SLCM Batch", dict(batch, status="Completed")),
			_card(_("Active courses"), "Course", {"status": "Active"}),
			_card(_("Core courses"), "Course", {"status": "Active", "course_type": "Core"}),
			_card(_("Elective courses"), "Course", {"status": "Active", "course_type": "Elective"}),
		], _("batches follow the academic year; courses are not filtered")),
		_group(_("Students & enrollment"), [
			_card(_("Active students"), "Student Master", stu(student_status="Active")),
			_card(_("Inactive / on hold"), "Student Master", stu(student_status=["in", ["Inactive", "Dormant", "Deferral"]]),
				_("inactive, dormant or deferred")),
			_card(_("Dropped / withdrawn"), "Student Master", stu(student_status=["in", ["Dropped", "Withdrawn"]])),
			_card(_("Graduated"), "Student Master", stu(student_status=["in", ["Graduated", "Alumni"]]), _("incl. alumni")),
			_card(_("No section"), "Student Master", stu(student_status="Active", section=["is", "not set"]), _("active students")),
			_card(_("No batch"), "Student Master", stu(student_status="Active", batch=["is", "not set"]), _("active students")),
			_card(_("Enrolled"), "Student Enrollment", enr(status="Enrolled"), _("enrollment records")),
			_card(_("Enrollment pending"), "Student Enrollment", enr(status="Pending")),
		], _("programme filter only")),
		_group(_("Classes"), [
			_card(_("Classes"), "Classes", cls(), _("one per course per section or group")),
			_card(_("This term"), "Classes", cls(academic_term=term_now), term_now) if term_now and not academic_term else None,
			_card(_("Section classes"), "Classes", cls(class_type="Section")),
			_card(_("Group classes"), "Classes", cls(class_type="Group")),
			_card(_("No faculty"), "Classes", cls(faculty=["is", "not set"]), _("needs a faculty member")),
			_card(_("No students"), "Classes", cls(total_students=["<", 1]), _("nobody enrolled yet")),
		]),
		_group(_("Time table"), [
			_card(_("Time table entries"), "Time Table", tt(), _("one per class meeting")),
			_card(_("Today"), "Time Table", tt(schedule_date=d, session_status=not_cancelled), _("classes today")),
			_card(_("Next 7 days"), "Time Table", tt(schedule_date=["between", [d, add_days(d, 6)]], session_status="Scheduled")),
			_card(_("Completed"), "Time Table", tt(session_status="Completed")),
			_card(_("Cancelled"), "Time Table", tt(session_status="Cancelled")),
			_card(_("Swapped"), "Time Table", tt(session_status="Swapped")),
			_card(_("Past, still scheduled"), "Time Table", tt(schedule_date=["<", d], session_status="Scheduled"),
				_("status was not updated")),
			_card(_("No venue"), "Time Table", tt(venue=["is", "not set"], session_status=not_cancelled), _("room not set")),
		]),
		_group(_("Promotion runs"), [
			_card(_("Runs"), "Promotion Run", run()),
			_card(_("Running"), "Promotion Run", run(status=["in", ["Queued", "In Progress"]]), _("queued or in progress")),
			_card(_("Completed"), "Promotion Run", run(status="Completed")),
			_card(_("With errors"), "Promotion Run", run(status=["in", ["Completed with Errors", "Error"]]), _("check the run log")),
		], _("follows the source year and trimester")),
	]
	return {
		"filters": {"programme": programme, "academic_year": academic_year, "academic_term": academic_term},
		"groups": [g for g in groups if g],
	}
