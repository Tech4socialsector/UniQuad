# Programme Dashboard: count cards for the academic calendar, programme structure,
# students, classes, the time table and promotion runs. Built like the Attendance
# Dashboard and shares its helpers, so every count is permission-checked and a
# doctype the user can't read is left out.

import frappe
from frappe import _
from frappe.utils import add_days, today

from slcm.slcm.page.attendance_dashboard.attendance_dashboard import _card, _group, current_term, drilldown

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


@frappe.whitelist()
def get_filter_options():
	return {
		"years": frappe.get_list("Academic Year", fields=["name", "is_current_year"], order_by="year_start_date desc", limit=100),
		"programmes": frappe.get_list("Programme", pluck="name", order_by="name asc", limit=500),
		"terms": frappe.get_list("Academic Term", fields=["name", "academic_year"], order_by="term_start_date desc", limit=200),
		"current_term": (current_term() or {}).get("name"),
	}


def _f(**pairs):
	"""Filters from field=value pairs, skipping the empty ones."""
	return {k: v for k, v in pairs.items() if v}


@frappe.whitelist()
def get_dashboard(programme=None, academic_year=None, academic_term=None):
	d = today()
	if academic_term and not academic_year:
		academic_year = frappe.db.get_value("Academic Term", academic_term, "academic_year")
	term_now = (current_term() or {}).get("name")
	# the "This term" card only makes sense when the current term is in the chosen year
	if term_now and academic_year and frappe.db.get_value("Academic Term", term_now, "academic_year") != academic_year:
		term_now = None

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
				term_now or _("no term covers today")),
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
