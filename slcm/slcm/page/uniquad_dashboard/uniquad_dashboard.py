"""Uniquad Dashboard — SLCM Operations & Insights.

Security model
--------------
* Every endpoint requires a logged-in user holding one of the page roles (``_check_access``).
* Every number, chart, table row, drilldown row, export row and profile block is read through
  ``frappe.get_list``. That applies DocType read permissions, User Permissions, the SLCM
  ``permission_query_conditions`` hooks (faculty see only their students / sessions, workflow roles
  see only their stage…) and permlevel field restrictions. A card can therefore never count records
  its viewer could not open.
* ``frappe.get_all`` is used only to *resolve filter scope* (e.g. which Course Offerings belong to a
  Programme / Batch) — those names only ever narrow a subsequent permission-checked query; they are never
  returned to the browser.
* The browser sends only a drilldown *key*, filter values and paging/sort/search. Doctypes, fields,
  sort columns and page sizes all come from the server-side registries below and are whitelisted.
* The student profile re-checks that the requested student is inside the caller's list scope
  (not just doc-level ``has_permission``, which ignores query conditions) — this closes IDOR.
"""

import csv
import datetime
import io

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_first_day, get_last_day, getdate, now_datetime, nowdate

PAGE_ROLES = (
	"System Manager",
	"slcm_Registrar",
	"slcm_Programme Chair",
	"Programme Chair",
	"slcm_Academic Incharge",
	"slcm_Faculty",
	"Academic Admin",
	"Academics User",
	"Campus Admin",
	"Admission Admin",
	"Admission Manager",
)

PAGE_SIZES = (10, 25, 50, 100)
EXPORT_LIMIT = 10000
MAX_FILTER_VALUES = 200
MAX_VALUE_LENGTH = 140
NONE = "__uq_no_match__"  # an `in` value that matches nothing, for filters that resolve to an empty set

LIST_FILTERS = (
	"academic_year",
	"academic_term",
	"programme",
	"batch",
	"section",
	"course",
	"faculty",
	"student_status",
	"gender",
)

PRESENT_STATUSES = ("Present", "Late", "OD")
GRADUATED_STATUSES = ("Graduated", "Alumni")
INACTIVE_STATUSES = ("Inactive", "Dropped", "Dormant", "Withdrawn", "Discontinued")
PENDING_CONDONATION = ("Pending", "May Be Approved")
OPEN_DEMAND_STATUSES = ("Pending", "Partially Paid", "Overdue")
APPLICATION_STAGE_ORDER = (
	"Application",
	"Entrance Test",
	"Interview",
	"Merit",
	"Seat Allocation",
	"Offer Letter",
	"Admission Fee",
	"Enrollment",
)

# Which dashboard filters each data source honours — shown on every card so users know what a number means.
Y, T, P, B, S, C, F, ST, G, DR = (
	"Academic Year",
	"Academic Term",
	"Programme",
	"Batch",
	"Section",
	"Course",
	"Faculty",
	"Student Status",
	"Gender",
	"Date Range",
)
SCOPE = {
	"students": [Y, P, B, S, ST, G],
	"offerings": [Y, T, P, B, S, C, F],
	"sessions": [DR, P, B, S, C, F],
	"sessions_nodate": [P, B, S, C, F],
	"attendance": [DR, P, B, S, C],
	"summary": [Y, T, P, B, S, C, F],
	"classes": [DR, P, B, S, C, F],
	"classes_nodate": [P, B, S, C, F],
	"applicants": [Y, P],
	"marks": [T, P, B, C, F],
	"results": [T],
	"condonation": [Y, P, B, C, F],
	"fees": [Y, P, B, S, ST, G],
	"programmes": [P],
	"courses": [C],
	"faculty": [F],
	"batches": [Y, P, B],
	"registered": [DR, Y, P, B, S, ST, G],
	"all_time": [],
}


# ─────────────────────────────────────────────────────────────── access & input validation


def _check_access():
	if frappe.session.user == "Guest":
		raise frappe.PermissionError
	frappe.only_for(PAGE_ROLES)


def _can(doctype):
	return bool(frappe.has_permission(doctype, "read"))


def _clean_list(value):
	if value in (None, "", []):
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.lstrip().startswith("[") else [value]
	if not isinstance(value, (list, tuple)):
		frappe.throw(_("Invalid filter value."))
	out = []
	for v in value:
		if v in (None, ""):
			continue
		if not isinstance(v, (str, int)):
			frappe.throw(_("Invalid filter value."))
		v = str(v).strip()
		if len(v) > MAX_VALUE_LENGTH:
			frappe.throw(_("Filter value is too long."))
		out.append(v)
	if len(out) > MAX_FILTER_VALUES:
		frappe.throw(_("Too many filter values selected (maximum {0}).").format(MAX_FILTER_VALUES))
	return list(dict.fromkeys(out))


def _clean_date(value):
	if not value:
		return None
	try:
		return getdate(value)
	except Exception:
		frappe.throw(_("Invalid date."))


def _clean_text(value, limit=100):
	value = (value or "").strip() if isinstance(value, str) else ""
	return value[:limit]


class Ctx:
	"""Validated dashboard filters plus cached scope resolution."""

	def __init__(self, raw=None):
		raw = frappe.parse_json(raw) if isinstance(raw, str) else (raw or {})
		if not isinstance(raw, dict):
			raw = {}
		for key in LIST_FILTERS:
			setattr(self, key, _clean_list(raw.get(key)))
		self.from_date = _clean_date(raw.get("from_date"))
		self.to_date = _clean_date(raw.get("to_date"))
		if self.from_date and self.to_date and self.from_date > self.to_date:
			self.from_date, self.to_date = self.to_date, self.from_date
		self._cache = {}

	# -- scope resolution (narrowing only; see module docstring)

	def programmes(self):
		"""Programme names selected in the Programme filter, or None when unconstrained."""
		return sorted(self.programme) if self.programme else None

	def offerings(self, period=False, faculty=False):
		"""Course Offerings matching the structural filters (programme / batch), optionally
		also the academic period and faculty. None when nothing constrains the set."""
		key = ("offerings", period, faculty)
		if key not in self._cache:
			f = []
			progs = self.programmes()
			if progs is not None:
				f.append(["program", "in", progs or [NONE]])
			if self.batch:
				f.append(["cohort", "in", self.batch])
			if period and self.academic_year:
				f.append(["academic_year", "in", self.academic_year])
			if period and self.academic_term:
				f.append(["term_name", "in", self.academic_term])
			if faculty and self.faculty:
				f.append(["faculty", "in", self.faculty])
			self._cache[key] = frappe.get_all("Course Offering", filters=f, pluck="name") if f else None
		return self._cache[key]

	def exam_plans(self):
		if "exam_plans" not in self._cache:
			self._cache["exam_plans"] = (
				frappe.get_all("Exam Plan", filters={"term": ["in", self.academic_term]}, pluck="name")
				if self.academic_term
				else None
			)
		return self._cache["exam_plans"]

	def has_student_constraint(self):
		return bool(
			self.programmes() is not None
			or self.batch
			or self.section
			or self.student_status
			or self.gender
		)

	def student_names(self):
		if "students" not in self._cache:
			self._cache["students"] = frappe.get_all("Student Master", filters=f_students(self), pluck="name")
		return self._cache["students"]

	def date_range(self, field):
		if self.from_date and self.to_date:
			return [[field, "between", [self.from_date, self.to_date]]]
		if self.from_date:
			return [[field, ">=", self.from_date]]
		if self.to_date:
			return [[field, "<=", self.to_date]]
		return []


def _in(field, values):
	return [field, "in", values or [NONE]]


# ─────────────────────────────────────────────────────────────── filter builders per data source


def f_students(ctx):
	f = []
	if ctx.academic_year:
		f.append(["academic_year", "in", ctx.academic_year])
	progs = ctx.programmes()
	if progs is not None:
		f.append(_in("programme_of_study", progs))
	if ctx.batch:
		f.append(["batch", "in", ctx.batch])
	if ctx.section:
		f.append(["section", "in", ctx.section])
	if ctx.student_status:
		f.append(["student_status", "in", ctx.student_status])
	if ctx.gender:
		f.append(["gender", "in", ctx.gender])
	return f


def f_offerings(ctx):
	f = []
	if ctx.academic_year:
		f.append(["academic_year", "in", ctx.academic_year])
	if ctx.academic_term:
		f.append(["term_name", "in", ctx.academic_term])
	progs = ctx.programmes()
	if progs is not None:
		f.append(_in("program", progs))
	if ctx.batch:
		f.append(["cohort", "in", ctx.batch])
	if ctx.section:
		f.append(["section", "in", ctx.section])
	if ctx.course:
		f.append(["course_title", "in", ctx.course])
	if ctx.faculty:
		f.append(["faculty", "in", ctx.faculty])
	return f


def _structural(ctx, f, field, faculty=False):
	offs = ctx.offerings(faculty=faculty)
	if offs is not None:
		f.append(_in(field, offs))
	return f


def f_sessions(ctx, with_dates=True):
	f = ctx.date_range("session_date") if with_dates else []
	_structural(ctx, f, "course_offering")
	if ctx.course:
		f.append(["course", "in", ctx.course])
	if ctx.faculty:
		f.append(["instructor", "in", ctx.faculty])
	if ctx.section:
		f.append(["section", "in", ctx.section])
	return f


def f_attendance(ctx):
	f = ctx.date_range("attendance_date")
	_structural(ctx, f, "course_offer")
	if ctx.course:
		f.append(["course", "in", ctx.course])
	if ctx.section:
		f.append(["section", "in", ctx.section])
	return f


def f_summary(ctx):
	f = []
	if ctx.academic_year:
		f.append(["academic_year", "in", ctx.academic_year])
	if ctx.academic_term:
		f.append(["term_name", "in", ctx.academic_term])
	_structural(ctx, f, "course_offering", faculty=True)
	if ctx.course:
		f.append(["course", "in", ctx.course])
	if ctx.section:
		f.append(["section", "in", ctx.section])
	return f


def f_classes(ctx, with_dates=True):
	f = ctx.date_range("schedule_date") if with_dates else []
	_structural(ctx, f, "course_offering")
	if ctx.course:
		f.append(["course", "in", ctx.course])
	if ctx.faculty:
		f.append(["instructor", "in", ctx.faculty])
	if ctx.section:
		f.append(["section", "in", ctx.section])
	return f


def f_applicants(ctx):
	f = []
	if ctx.academic_year:
		f.append(["academic_year", "in", ctx.academic_year])
	progs = ctx.programmes()
	if progs is not None:
		f.append(_in("program", progs))
	return f


def f_marks(ctx):
	f = []
	plans = ctx.exam_plans()
	if plans is not None:
		f.append(_in("exam_plan", plans))
	_structural(ctx, f, "course_offering", faculty=True)
	if ctx.course:
		f.append(["course", "in", ctx.course])
	return f


def f_results(ctx):
	plans = ctx.exam_plans()
	return [_in("exam_plan", plans)] if plans is not None else []


def f_condonation(ctx):
	f = [["docstatus", "<", 2]]
	if ctx.academic_year:
		f.append(["academic_year", "in", ctx.academic_year])
	_structural(ctx, f, "course_offering", faculty=True)
	if ctx.course:
		f.append(["course", "in", ctx.course])
	return f


def f_fees(ctx):
	f = [["status", "!=", "Cancelled"]]
	if ctx.academic_year:
		f.append(["academic_year", "in", ctx.academic_year])
	if ctx.has_student_constraint():
		f.append(_in("student", ctx.student_names()))
	return f


def f_programmes(ctx):
	progs = ctx.programmes()
	return [_in("name", progs)] if progs is not None else []


def f_faculty(ctx):
	f = []
	if ctx.faculty:
		f.append(["name", "in", ctx.faculty])
	return f


def f_batches(ctx):
	f = []
	if ctx.academic_year:
		f.append(["academic_year", "in", ctx.academic_year])
	progs = ctx.programmes()
	if progs is not None:
		f.append(_in("program", progs))
	if ctx.batch:
		f.append(["name", "in", ctx.batch])
	return f


# ─────────────────────────────────────────────────────────────── permission-checked query helpers


def _count(doctype, filters):
	rows = frappe.get_list(doctype, filters=filters, fields=[{"COUNT": "*", "as": "n"}], order_by=None)
	return cint(rows[0].n) if rows else 0


def _distinct_count(doctype, filters, field):
	return len(frappe.get_list(doctype, filters=filters, fields=[field], group_by=field, order_by=None))


def _aggregate(doctype, filters, fn, field):
	rows = frappe.get_list(doctype, filters=filters, fields=[{fn: field, "as": "v"}], order_by=None)
	return flt(rows[0].v) if rows and rows[0].v is not None else None


def _group(doctype, filters, field, fn="COUNT", arg="*"):
	return frappe.get_list(
		doctype,
		filters=filters,
		fields=[field, {fn: arg, "as": "v"}],
		group_by=field,
		order_by=None,
	)


def _threshold():
	value = flt(frappe.db.get_single_value("Attendance Settings", "minimum_attendance_percentage"))
	return value or 75.0


def _active_admission_cycles():
	"""Admission Cycles with status Active — the admission that is currently running."""
	return frappe.get_all("Admission Cycle", filters={"status": "Active"}, pluck="name", order_by="cycle_start_date desc")


def f_current_admission(ctx):
	f = [_in("admission_cycle", _active_admission_cycles())]
	progs = ctx.programmes()
	if progs is not None:
		f.append(_in("program", progs))
	return f


def _current_admission_sub(ctx):
	cycles = _active_admission_cycles()
	if not cycles:
		return _("No admission cycle is active")
	submitted = _count("Applicant", f_current_admission(ctx) + [["status", "!=", "Draft"]])
	return _("{0} · {1} submitted").format(", ".join(cycles), submitted)


def _applicant_status_map():
	return {
		r.name: r
		for r in frappe.get_all("Applicant Status", fields=["name", "status_type", "stage_type"])
	}


def _applicant_statuses(kind):
	"""Applicant Status names for a pipeline bucket, derived from Applicant Status.status_type."""
	statuses = _applicant_status_map()
	if kind == "closed":
		return [n for n, s in statuses.items() if s.status_type == "Closed" or n == "Rejected"]
	if kind == "enrolled":
		return [n for n, s in statuses.items() if n == "Enrolled"]
	if kind == "in_progress":
		closed = set(_applicant_statuses("closed")) | {"Enrolled", "Draft"}
		return [n for n in statuses if n not in closed]
	return list(statuses)


# ─────────────────────────────────────────────────────────────── drilldown registry
# column: (fieldname, label, kind, sortable). kind drives formatting on the client.
# Computed columns (filled by `post`) are never sortable server-side.

STUDENT_COLUMNS = [
	("name", "Student ID", "student", True),
	("first_name", "Student", "text", True),
	("programme_of_study", "Programme", "text", True),
	("batch", "Batch", "text", True),
	("section", "Section", "text", True),
	("student_status", "Status", "badge", True),
	("registration_status", "Registration Stage", "badge", True),
	("modified", "Updated On", "datetime", True),
]
STUDENT_SEARCH = ["name", "first_name", "registration_id", "email"]

SESSION_COLUMNS = [
	("name", "Session", "form", True),
	("course", "Course", "text", True),
	("session_date", "Date", "date", True),
	("session_start_time", "Start", "time", True),
	("instructor_name", "Faculty", "text", False),
	("section", "Section", "text", True),
	("total_students", "Expected", "int", True),
	("present_count", "Present", "int", True),
	("attendance_percentage", "Attendance %", "pct", True),
	("session_status", "Status", "badge", True),
	("marked_label", "Attendance Entry", "badge", False),
]
SESSION_SEARCH = ["name", "course", "course_offering"]

CLASS_COLUMNS = [
	("name", "Class", "form", True),
	("course", "Course", "text", True),
	("schedule_date", "Date", "date", True),
	("from_time", "From", "time", True),
	("to_time", "To", "time", True),
	("instructor_name", "Faculty", "text", False),
	("venue", "Venue", "text", True),
	("section", "Section", "text", True),
	("course_offering", "Course Offering", "text", True),
]
CLASS_SEARCH = ["name", "course", "course_offering", "venue"]

SUMMARY_COLUMNS = [
	("student", "Student ID", "student", True),
	("student_name", "Student", "text", True),
	("course", "Course", "text", True),
	("course_offering", "Course Offering", "text", True),
	("attendance_percentage", "Attendance %", "pct", True),
	("minimum_required_percentage", "Required %", "pct", True),
	("total_class_hours", "Hours Conducted", "float", True),
	("attended_classes", "Hours Attended", "float", True),
	("absent_hours", "Hours Missed", "float", False),
	("academic_year", "Academic Year", "text", True),
	("term_name", "Academic Term", "text", True),
	("eligible_label", "Exam Eligibility", "badge", False),
]
SUMMARY_SEARCH = ["student", "student_name", "course", "course_offering"]

OFFERING_COLUMNS = [
	("name", "Course Offering", "offering", True),
	("course_name", "Course", "text", True),
	("program", "Programme", "text", True),
	("cohort", "Batch", "text", True),
	("section", "Section", "text", True),
	("faculty_name", "Faculty", "text", False),
	("term_name", "Academic Term", "text", True),
	("sessions_held", "Sessions Held", "int", False),
	("sessions_unmarked", "Not Marked", "int", False),
	("avg_attendance", "Avg Attendance %", "pct", False),
	("status", "Status", "badge", True),
]
OFFERING_SEARCH = ["name", "course_name", "course_title", "program", "cohort"]

APPLICANT_COLUMNS = [
	("name", "Application", "form", True),
	("candidate_name", "Applicant", "text", True),
	("program", "Programme", "text", True),
	("creation", "Applied On", "date", True),
	("status", "Status", "badge", True),
	("stage", "Stage", "text", False),
	("current_stage", "Current Stage", "text", True),
	("application_fee_status", "Application Fee", "badge", True),
	("modified", "Updated On", "datetime", True),
]
APPLICANT_SEARCH = ["name", "candidate_name", "applicant_id", "mobile_number"]


def _post_student_names(rows, field="student", target="student_name"):
	ids = {r.get(field) for r in rows if r.get(field)}
	if not ids:
		return rows
	names = {
		s.name: s.first_name
		for s in frappe.get_list("Student Master", filters={"name": ["in", list(ids)]}, fields=["name", "first_name"])
	} if _can("Student Master") else {}
	for r in rows:
		if not r.get(target):
			r[target] = names.get(r.get(field)) or ""
	return rows


def _faculty_labels(ids):
	ids = {str(i) for i in ids if i not in (None, "")}
	if not ids:
		return {}
	return {
		str(f.name): " ".join(filter(None, [f.first_name, f.last_name]))
		for f in frappe.get_all("Faculty", filters={"name": ["in", list(ids)]}, fields=["name", "first_name", "last_name"])
	}


def _post_faculty(rows, field, target):
	labels = _faculty_labels(r.get(field) for r in rows)
	for r in rows:
		r[target] = labels.get(str(r.get(field) or ""), r.get(field) or "")
	return rows


def _post_sessions(rows):
	_post_faculty(rows, "instructor", "instructor_name")
	for r in rows:
		r["marked_label"] = "Marked" if cint(r.get("attendance_marked")) else "Not Marked"
	return rows


def _post_summary(rows):
	_post_student_names(rows)
	for r in rows:
		r["absent_hours"] = max(flt(r.get("total_class_hours")) - flt(r.get("attended_classes")), 0)
		r["eligible_label"] = "Eligible" if cint(r.get("eligible_for_exam")) else "Shortage"
	return rows


def _post_offerings(rows):
	_post_faculty(rows, "faculty", "faculty_name")
	names = [r.name for r in rows]
	if names and _can("Attendance Session"):
		held = {
			g.course_offering: g
			for g in frappe.get_list(
				"Attendance Session",
				filters={"course_offering": ["in", names], "session_status": "Conducted"},
				fields=["course_offering", {"COUNT": "*", "as": "n"}, {"AVG": "attendance_percentage", "as": "avg"}],
				group_by="course_offering",
				order_by=None,
			)
		}
		unmarked = {
			g.course_offering: g.v
			for g in _group(
				"Attendance Session",
				[
					["course_offering", "in", names],
					["session_status", "!=", "Cancelled"],
					["session_date", "<=", nowdate()],
					["attendance_marked", "=", 0],
				],
				"course_offering",
			)
		}
		for r in rows:
			h = held.get(r.name)
			r["sessions_held"] = cint(h.n) if h else 0
			r["avg_attendance"] = flt(h.avg) if h and h.avg is not None else None
			r["sessions_unmarked"] = cint(unmarked.get(r.name))
	return rows


def _post_applicants(rows):
	statuses = _applicant_status_map()
	for r in rows:
		s = statuses.get(r.get("status"))
		r["stage"] = (s.stage_type if s else "") or ""
	return rows


def _past_open_sessions():
	return [["session_date", "<=", nowdate()], ["session_status", "!=", "Cancelled"]]


def _drill(title, doctype, columns, filters, search, sort, scope, *, post=None, extra_fields=(), description="", all_time=False, params=None, virtual=None):
	return {
		"virtual": virtual,
		"title": title,
		"doctype": doctype,
		"columns": columns,
		"filters": filters,
		"search": search,
		"sort": sort,
		"scope": scope,
		"post": post,
		"extra_fields": list(extra_fields),
		"description": description,
		"all_time": all_time,
		"params": params or {},
	}


def _session_mode_filters(ctx, p):
	f = f_sessions(ctx) + _past_open_sessions()
	if p.get("mode") == "low":
		f.append(["session_status", "=", "Conducted"])
		f.append(["attendance_percentage", "<", _threshold()])
	else:
		f.append(["attendance_marked", "=", 0])
	return f


DRILLDOWNS = {
	# Students
	"students": _drill("Students in Scope", "Student Master", STUDENT_COLUMNS, lambda c, p: f_students(c), STUDENT_SEARCH, ("modified", "desc"), "students"),
	"students_active": _drill("Active Students", "Student Master", STUDENT_COLUMNS, lambda c, p: f_students(c) + [["student_status", "=", "Active"]], STUDENT_SEARCH, ("first_name", "asc"), "students"),
	"students_new": _drill("Newly Registered Students", "Student Master", STUDENT_COLUMNS[:6] + [("date_of_registration", "Registered On", "date", True)], lambda c, p: f_students(c) + c.date_range("date_of_registration"), STUDENT_SEARCH, ("date_of_registration", "desc"), "registered"),
	"students_graduated": _drill("Graduated / Alumni Students", "Student Master", STUDENT_COLUMNS, lambda c, p: f_students(c) + [["student_status", "in", GRADUATED_STATUSES]], STUDENT_SEARCH, ("modified", "desc"), "students"),
	"students_inactive": _drill("Inactive, Dropped or Withdrawn Students", "Student Master", STUDENT_COLUMNS + [("status_remark", "Remark", "text", False)], lambda c, p: f_students(c) + [["student_status", "in", INACTIVE_STATUSES]], STUDENT_SEARCH, ("modified", "desc"), "students"),
	"registration_pending": _drill("Registrations Not Completed", "Student Master", STUDENT_COLUMNS, lambda c, p: f_students(c) + [["registration_status", "!=", "Completed"]], STUDENT_SEARCH, ("registration_status", "asc"), "students", description="Students whose registration workflow has not reached Completed."),
	"id_card_pending": _drill("Active Students Without an ID Card", "Student Master", STUDENT_COLUMNS[:6] + [("id_card_issued", "ID Card Issued", "badge", True), ("rfid_uid", "RFID", "text", True)], lambda c, p: f_students(c) + [["student_status", "=", "Active"], ["id_card_issued", "!=", "Yes"]], STUDENT_SEARCH, ("first_name", "asc"), "students"),
	"recent_students": _drill("Recent Student Activity", "Student Master", STUDENT_COLUMNS, lambda c, p: f_students(c), STUDENT_SEARCH, ("modified", "desc"), "students"),
	# Attendance
	"below_threshold": _drill("Students Below Attendance Threshold", "Attendance Summary", SUMMARY_COLUMNS, lambda c, p: f_summary(c) + [["eligible_for_exam", "=", 0]], SUMMARY_SEARCH, ("attendance_percentage", "asc"), "summary", post=_post_summary, extra_fields=["eligible_for_exam"], description="Student-course records not eligible for exams (attendance below the required %, after condonation and FA/MFA)."),
	"attendance_summary": _drill("Course-wise Attendance Summary", "Attendance Summary", SUMMARY_COLUMNS, lambda c, p: f_summary(c), SUMMARY_SEARCH, ("attendance_percentage", "asc"), "summary", post=_post_summary, extra_fields=["eligible_for_exam"]),
	"offering_attendance": _drill("Student Attendance for Course Offering", "Attendance Summary", SUMMARY_COLUMNS, lambda c, p: [["course_offering", "=", p["course_offering"]]], SUMMARY_SEARCH, ("attendance_percentage", "asc"), "all_time", post=_post_summary, extra_fields=["eligible_for_exam"], params={"course_offering": "text"}),
	"unmarked_sessions": _drill("Sessions With Attendance Not Entered", "Attendance Session", SESSION_COLUMNS, lambda c, p: f_sessions(c) + _past_open_sessions() + [["attendance_marked", "=", 0]], SESSION_SEARCH, ("session_date", "desc"), "sessions", post=_post_sessions, extra_fields=["instructor", "attendance_marked"], description="Past, non-cancelled sessions where attendance has not been marked."),
	"attendance_exceptions": _drill("Attendance Exceptions", "Attendance Session", SESSION_COLUMNS, _session_mode_filters, SESSION_SEARCH, ("session_date", "desc"), "sessions", post=_post_sessions, extra_fields=["instructor", "attendance_marked"], params={"mode": ("unmarked", "low")}),
	"sessions_conducted": _drill("Sessions Conducted", "Attendance Session", SESSION_COLUMNS, lambda c, p: f_sessions(c) + [["session_status", "=", "Conducted"]], SESSION_SEARCH, ("session_date", "desc"), "sessions", post=_post_sessions, extra_fields=["instructor", "attendance_marked"]),
	"sessions_cancelled": _drill("Cancelled / Postponed Sessions", "Attendance Session", SESSION_COLUMNS[:6] + [("session_status", "Status", "badge", True), ("cancellation_reason", "Reason", "text", False)], lambda c, p: f_sessions(c) + [["session_status", "in", ["Cancelled", "Postponed"]]], SESSION_SEARCH, ("session_date", "desc"), "sessions", post=_post_sessions, extra_fields=["instructor", "attendance_marked"]),
	"attendance_records": _drill("Student Attendance Records", "Student Attendance", [("name", "Record", "form", True), ("student", "Student ID", "student", True), ("student_name", "Student", "text", True), ("course", "Course", "text", True), ("attendance_date", "Date", "date", True), ("status", "Status", "badge", True), ("source", "Source", "text", True), ("attendance_session", "Session", "text", True)], lambda c, p: f_attendance(c), ["student", "student_name", "course", "attendance_session"], ("attendance_date", "desc"), "attendance", post=_post_student_names),
	# Classes
	"classes_period": _drill("Scheduled Classes", "Time Table", CLASS_COLUMNS, lambda c, p: f_classes(c), CLASS_SEARCH, ("schedule_date", "asc"), "classes", post=lambda r: _post_faculty(r, "instructor", "instructor_name"), extra_fields=["instructor"]),
	"todays_classes": _drill("Today's Classes", "Time Table", CLASS_COLUMNS, lambda c, p: f_classes(c, False) + [["schedule_date", "=", nowdate()]], CLASS_SEARCH, ("from_time", "asc"), "classes_nodate", post=lambda r: _post_faculty(r, "instructor", "instructor_name"), extra_fields=["instructor"]),
	"upcoming_classes": _drill("Upcoming Classes (Next 7 Days)", "Time Table", CLASS_COLUMNS, lambda c, p: f_classes(c, False) + [["schedule_date", "between", [add_days(nowdate(), 1), add_days(nowdate(), 7)]]], CLASS_SEARCH, ("schedule_date", "asc"), "classes_nodate", post=lambda r: _post_faculty(r, "instructor", "instructor_name"), extra_fields=["instructor"]),
	# Academic structure
	"offerings": _drill("Course Operations", "Course Offering", OFFERING_COLUMNS, lambda c, p: f_offerings(c) + [["status", "=", "Active"]], OFFERING_SEARCH, ("course_name", "asc"), "offerings", post=_post_offerings, extra_fields=["faculty"]),
	"programmes": _drill("Active Programmes", "Programme", [("name", "Programme", "form", True), ("program_name", "Programme Name", "text", True), ("program_code", "Code", "text", True), ("level_of_study", "Level", "text", True), ("program_duration", "Duration (Years)", "int", True), ("program_status", "Status", "badge", True)], lambda c, p: f_programmes(c) + [["program_status", "=", "Active"]], ["name", "program_name", "program_code"], ("program_name", "asc"), "programmes"),
	"courses": _drill("Active Courses", "Course", [("name", "Course", "form", True), ("course_code", "Code", "text", True), ("course_name", "Course Name", "text", True), ("course_type", "Type", "badge", True), ("credit_value", "Credits", "int", True), ("status", "Status", "badge", True)], lambda c, p: ([["name", "in", c.course]] if c.course else []) + [["status", "=", "Active"]], ["name", "course_code", "course_name"], ("course_name", "asc"), "courses"),
	"faculty": _drill("Active Faculty", "Faculty", [("name", "Faculty", "form", True), ("faculty_id", "Faculty ID", "text", True), ("first_name", "First Name", "text", True), ("last_name", "Last Name", "text", True), ("designation", "Designation", "text", True), ("is_hod", "HoD", "int", True), ("status", "Status", "badge", True)], lambda c, p: f_faculty(c) + [["status", "=", "Active"]], ["faculty_id", "first_name", "last_name"], ("first_name", "asc"), "faculty"),
	"batches": _drill("Active Batches", "Batch", [("name", "Batch", "form", True), ("program", "Programme", "text", True), ("academic_year", "Academic Year", "text", True), ("start_date", "Start", "date", True), ("end_date", "End", "date", True), ("total_enrolled_count", "Enrolled", "int", True), ("status", "Status", "badge", True)], lambda c, p: f_batches(c) + [["status", "=", "Active"]], ["name", "program", "batch_code"], ("name", "asc"), "batches"),
	# Admissions
	"admission_current": _drill("Registered in the Current Admission", "Applicant", APPLICANT_COLUMNS, lambda c, p: f_current_admission(c), APPLICANT_SEARCH, ("creation", "desc"), "current_admission", post=_post_applicants),
	# Campus residence (Student Master.campus)
	"students_on_campus": _drill("Active Students On Campus", "Student Master", STUDENT_COLUMNS, lambda c, p: f_students(c) + [["student_status", "=", "Active"], ["campus", "=", "On Campus"]], STUDENT_SEARCH, ("first_name", "asc"), "students"),
	"students_off_campus": _drill("Active Students Off Campus", "Student Master", STUDENT_COLUMNS, lambda c, p: f_students(c) + [["student_status", "=", "Active"], ["campus", "=", "Off Campus"]], STUDENT_SEARCH, ("first_name", "asc"), "students"),
	"applications": _drill("Applications", "Applicant", APPLICANT_COLUMNS, lambda c, p: f_applicants(c), APPLICANT_SEARCH, ("modified", "desc"), "applicants", post=_post_applicants),
	"applications_in_progress": _drill("Applications in Progress", "Applicant", APPLICANT_COLUMNS, lambda c, p: f_applicants(c) + [_in("status", _applicant_statuses("in_progress"))], APPLICANT_SEARCH, ("modified", "desc"), "applicants", post=_post_applicants),
	"applications_enrolled": _drill("Enrolled Applicants", "Applicant", APPLICANT_COLUMNS, lambda c, p: f_applicants(c) + [_in("status", _applicant_statuses("enrolled"))], APPLICANT_SEARCH, ("modified", "desc"), "applicants", post=_post_applicants),
	"applications_closed": _drill("Rejected, Withdrawn or Declined Applications", "Applicant", APPLICANT_COLUMNS + [("rejected_reason", "Reason", "text", False)], lambda c, p: f_applicants(c) + [_in("status", _applicant_statuses("closed"))], APPLICANT_SEARCH, ("modified", "desc"), "applicants", post=_post_applicants),
	"applications_draft": _drill("Draft Applications (Not Submitted)", "Applicant", APPLICANT_COLUMNS, lambda c, p: f_applicants(c) + [["status", "=", "Draft"]], APPLICANT_SEARCH, ("modified", "desc"), "applicants", post=_post_applicants),
	# Examinations
	"marks_draft": _drill("Marks Still in Draft", "Student Course Marks", [("student", "Student ID", "student", True), ("student_name", "Student", "text", False), ("course", "Course", "text", True), ("exam_plan", "Exam", "text", True), ("total_marks", "Total Marks", "float", True), ("grade", "Grade", "text", True), ("status", "Status", "badge", True), ("modified", "Updated On", "datetime", True)], lambda c, p: f_marks(c) + [["status", "=", "Draft"]], ["student", "student_id", "course", "exam_plan"], ("modified", "desc"), "marks", post=_post_student_names),
	"marks_all": _drill("Course Marks Recorded", "Student Course Marks", [("student", "Student ID", "student", True), ("student_name", "Student", "text", False), ("course", "Course", "text", True), ("exam_plan", "Exam", "text", True), ("total_marks", "Total Marks", "float", True), ("grade", "Grade", "text", True), ("status", "Status", "badge", True), ("modified", "Updated On", "datetime", True)], lambda c, p: f_marks(c), ["student", "student_id", "course", "exam_plan"], ("modified", "desc"), "marks", post=_post_student_names),
	"results_published": _drill("Published Results", "Student Result Publish", [("student", "Student ID", "student", True), ("student_name", "Student", "text", False), ("exam_plan", "Exam", "text", True), ("term_gpa", "Term GPA", "float", True), ("cumulative_gpa", "CGPA", "float", True), ("term_percentage", "Term %", "pct", True), ("published_on", "Published On", "datetime", True)], lambda c, p: f_results(c) + [["is_published", "=", 1]], ["student", "exam_plan"], ("published_on", "desc"), "results", post=_post_student_names),
	# Condonation
	"condonation_pending": _drill("Condonation Requests Awaiting Decision", "Student Attendance Condonation", [("name", "Request", "form", True), ("student", "Student ID", "student", True), ("student_name", "Student", "text", True), ("course", "Course", "text", True), ("absence_from_date", "Absent From", "date", True), ("absence_to_date", "Absent To", "date", True), ("number_of_sessions", "Sessions", "int", True), ("number_of_hours", "Hours", "float", True), ("final_status", "Status", "badge", True), ("submitted_date", "Submitted On", "datetime", True)], lambda c, p: f_condonation(c) + [["final_status", "in", PENDING_CONDONATION]], ["name", "student", "student_name", "course"], ("submitted_date", "asc"), "condonation"),
	# Fees
	"fee_overdue": _drill("Overdue Fee Demands", "Fee Demand", [("name", "Demand", "form", True), ("student", "Student ID", "student", True), ("student_name", "Student", "text", True), ("fee_component", "Fee Component", "text", True), ("net_payable", "Net Payable", "currency", True), ("outstanding_amount", "Outstanding", "currency", True), ("due_date", "Due Date", "date", True), ("status", "Status", "badge", True)], lambda c, p: f_fees(c) + [["status", "in", OPEN_DEMAND_STATUSES], ["due_date", "<", nowdate()], ["outstanding_amount", ">", 0]], ["name", "student", "student_name", "fee_component"], ("due_date", "asc"), "fees"),
	"fee_outstanding": _drill("Fee Demands With Outstanding Balance", "Fee Demand", [("name", "Demand", "form", True), ("student", "Student ID", "student", True), ("student_name", "Student", "text", True), ("fee_component", "Fee Component", "text", True), ("net_payable", "Net Payable", "currency", True), ("paid_amount", "Paid", "currency", True), ("outstanding_amount", "Outstanding", "currency", True), ("due_date", "Due Date", "date", True), ("status", "Status", "badge", True)], lambda c, p: f_fees(c) + [["outstanding_amount", ">", 0]], ["name", "student", "student_name", "fee_component"], ("outstanding_amount", "desc"), "fees"),
	# All-time (filters intentionally ignored; still permission-scoped)
	"students_all_time": _drill("All Students Ever Registered", "Student Master", STUDENT_COLUMNS, lambda c, p: [], STUDENT_SEARCH, ("creation", "desc"), "all_time", all_time=True),
	"graduated_all_time": _drill("All Graduated / Alumni Students", "Student Master", STUDENT_COLUMNS, lambda c, p: [["student_status", "in", GRADUATED_STATUSES]], STUDENT_SEARCH, ("modified", "desc"), "all_time", all_time=True),
	"programmes_all_time": _drill("All Programmes", "Programme", [("name", "Programme", "form", True), ("program_name", "Programme Name", "text", True), ("level_of_study", "Level", "text", True), ("program_status", "Status", "badge", True), ("creation", "Created On", "date", True)], lambda c, p: [], ["name", "program_name"], ("creation", "desc"), "all_time", all_time=True),
	"courses_all_time": _drill("All Courses", "Course", [("name", "Course", "form", True), ("course_code", "Code", "text", True), ("course_name", "Course Name", "text", True), ("course_type", "Type", "badge", True), ("credit_value", "Credits", "int", True), ("status", "Status", "badge", True)], lambda c, p: [], ["name", "course_code", "course_name"], ("course_name", "asc"), "all_time", all_time=True),
	"years_all_time": _drill("All Academic Years", "Academic Year", [("name", "Academic Year", "form", True), ("academic_system", "System", "text", True), ("year_start_date", "Start", "date", True), ("year_end_date", "End", "date", True), ("status", "Status", "badge", True)], lambda c, p: [], ["name"], ("year_start_date", "desc"), "all_time", all_time=True),
	"applications_all_time": _drill("All Applications", "Applicant", APPLICANT_COLUMNS, lambda c, p: [], APPLICANT_SEARCH, ("creation", "desc"), "all_time", post=_post_applicants, all_time=True),
	"sessions_all_time": _drill("All Sessions Conducted", "Attendance Session", SESSION_COLUMNS, lambda c, p: [["session_status", "=", "Conducted"]], SESSION_SEARCH, ("session_date", "desc"), "all_time", post=_post_sessions, extra_fields=["instructor", "attendance_marked"], all_time=True),
	"results_all_time": _drill("All Published Results", "Student Result Publish", [("student", "Student ID", "student", True), ("student_name", "Student", "text", False), ("exam_plan", "Exam", "text", True), ("term_gpa", "Term GPA", "float", True), ("cumulative_gpa", "CGPA", "float", True), ("published_on", "Published On", "datetime", True)], lambda c, p: [["is_published", "=", 1]], ["student", "exam_plan"], ("published_on", "desc"), "all_time", post=_post_student_names, all_time=True),
}


# ── additional sources ────────────────────────────────────────────────────────


def _venue_range(ctx):
	f = []
	if ctx.from_date:
		f.append(["start_datetime", ">=", ctx.from_date])
	if ctx.to_date:
		f.append(["start_datetime", "<", add_days(ctx.to_date, 1)])
	return f


def _offering_batches(names):
	names = [n for n in names if n]
	if not names or not _can("Course Offering"):
		return {}
	return {o.name: o.cohort for o in frappe.get_list("Course Offering", filters={"name": ["in", names]}, fields=["name", "cohort"])}


def _post_schedule(rows):
	_post_faculty(rows, "instructor", "instructor_name")
	batches = _offering_batches({r.get("course_offering") for r in rows})
	now = now_datetime()
	today = getdate(nowdate())
	for r in rows:
		r["batch"] = batches.get(r.get("course_offering")) or ""
		day = getdate(r.get("schedule_date")) if r.get("schedule_date") else None
		start = (datetime.datetime.combine(day, datetime.time()) + r["from_time"]) if day and isinstance(r.get("from_time"), datetime.timedelta) else None
		end = (datetime.datetime.combine(day, datetime.time()) + r["to_time"]) if day and isinstance(r.get("to_time"), datetime.timedelta) else None
		if day and day < today or (end and end < now):
			r["class_state"] = "Completed"
		elif start and start <= now and (not end or end >= now):
			r["class_state"] = "In Progress"
		else:
			r["class_state"] = "Upcoming"
	return rows


def _virtual_offerings_incomplete(ctx, p):
	"""Course offerings with at least one past, non-cancelled session whose attendance is not marked."""
	if not _can("Attendance Session"):
		raise frappe.PermissionError
	rows = frappe.get_list(
		"Attendance Session",
		filters=DRILLDOWNS["unmarked_sessions"]["filters"](ctx, {}),
		fields=["course_offering", "course", {"COUNT": "*", "as": "n"}, {"MIN": "session_date", "as": "oldest"}, {"MAX": "session_date", "as": "latest"}],
		group_by="course_offering, course",
		order_by=None,
	)
	return [
		frappe._dict(name=r.course_offering or "", course_offering=r.course_offering, course=r.course, sessions_unmarked=cint(r.n), oldest=r.oldest, latest=r.latest)
		for r in rows
	]


def _safe_rows(doctype, **kw):
	"""get_list that degrades to [] for a doctype the user cannot read (used by multi-source lists)."""
	if not _can(doctype):
		return []
	try:
		return frappe.get_list(doctype, **kw)
	except frappe.PermissionError:
		frappe.clear_messages()
		return []


def _virtual_pending_operations(ctx, p):
	"""One queue of open items across modules. Every source is a permission-checked query."""
	out = []
	per = 50
	for r in _safe_rows("Attendance Session", filters=DRILLDOWNS["unmarked_sessions"]["filters"](ctx, {}), fields=["name", "course", "session_date", "instructor"], order_by="session_date asc", limit=per):
		out.append(dict(item=_("Attendance not entered — {0}").format(r.course or r.name), module=_("Attendance"), owner_id=r.instructor, when=r.session_date, status="Not Marked", ref_doctype="Attendance Session", ref_name=r.name))
	for r in _safe_rows("Student Attendance Condonation", filters=DRILLDOWNS["condonation_pending"]["filters"](ctx, {}), fields=["name", "student_name", "student", "course", "final_status", "submitted_date", "creation", "aad_approver", "programme_chair_approver"], order_by="creation asc", limit=per):
		out.append(dict(item=_("Condonation request — {0}, {1}").format(r.student_name or r.student, r.course or ""), module=_("Attendance"), owner=r.aad_approver or r.programme_chair_approver or "", when=r.submitted_date or r.creation, status=r.final_status, ref_doctype="Student Attendance Condonation", ref_name=r.name))
	for r in _safe_rows("Student Master", filters=DRILLDOWNS["registration_pending"]["filters"](ctx, {}), fields=["name", "first_name", "registration_status", "modified"], order_by="modified asc", limit=per):
		out.append(dict(item=_("Registration in progress — {0}").format(r.first_name or r.name), module=_("Student Registration"), owner="", when=r.modified, status=r.registration_status or _("Not started"), ref_doctype="Student Master", ref_name=r.name))
	for r in _safe_rows("Student Master", filters=DRILLDOWNS["students_no_section"]["filters"](ctx, {}), fields=["name", "first_name", "batch", "modified"], order_by="modified asc", limit=per):
		out.append(dict(item=_("No section assigned — {0}").format(r.first_name or r.name), module=_("Student Registration"), owner="", when=r.modified, status=_("Section missing"), ref_doctype="Student Master", ref_name=r.name))
	for r in _safe_rows("Time Table", filters=DRILLDOWNS["classes_no_venue"]["filters"](ctx, {}), fields=["name", "course", "schedule_date", "instructor"], order_by="schedule_date asc", limit=per):
		out.append(dict(item=_("No venue for class — {0}").format(r.course or r.name), module=_("Venue Booking"), owner_id=r.instructor, when=r.schedule_date, status=_("Venue missing"), ref_doctype="Time Table", ref_name=r.name))
	for r in _safe_rows("Venue Booking", filters=[["status", "=", "Pending Allotment"]], fields=["name", "event_name", "requester_name", "start_datetime"], order_by="start_datetime asc", limit=per):
		out.append(dict(item=_("Venue request — {0}").format(r.event_name or r.name), module=_("Venue Booking"), owner=r.requester_name or "", when=r.start_datetime, status="Pending Allotment", ref_doctype="Venue Booking", ref_name=r.name))
	for r in _safe_rows("Student Course Marks", filters=DRILLDOWNS["marks_draft"]["filters"](ctx, {}), fields=["name", "student", "course", "exam_plan", "owner", "modified"], order_by="modified asc", limit=per):
		out.append(dict(item=_("Marks in draft — {0}, {1}").format(r.course or "", r.exam_plan or ""), module=_("Examinations"), owner=r.owner, when=r.modified, status="Draft", ref_doctype="Student Course Marks", ref_name=r.name))
	for r in _safe_rows("Fee Demand", filters=DRILLDOWNS["fee_overdue"]["filters"](ctx, {}), fields=["name", "student_name", "student", "fee_component", "outstanding_amount", "due_date", "status"], order_by="due_date asc", limit=per):
		out.append(dict(item=_("Overdue fee — {0}, ₹{1}").format(r.student_name or r.student, frappe.utils.fmt_money(r.outstanding_amount, precision=0)), module=_("Fees"), owner="", when=r.due_date, status=r.status, ref_doctype="Fee Demand", ref_name=r.name))
	for r in _safe_rows("ID Card Generation", filters=DRILLDOWNS["idcards_error"]["filters"](ctx, {}), fields=["name", "student_name", "student", "owner", "modified"], order_by="modified asc", limit=per):
		out.append(dict(item=_("ID card error — {0}").format(r.student_name or r.student or r.name), module=_("ID Card"), owner=r.owner, when=r.modified, status="Error", ref_doctype="ID Card Generation", ref_name=r.name))
	for r in _safe_rows("PACE Document Verification", filters=DRILLDOWNS["pace_verification_pending"]["filters"](ctx, {}), fields=["name", "applicant_name", "assigned_verifier", "due_date", "status"], order_by="due_date asc", limit=per):
		out.append(dict(item=_("PACE verification — {0}").format(r.applicant_name or r.name), module=_("PACE"), owner=r.assigned_verifier or "", when=r.due_date, status=r.status, ref_doctype="PACE Document Verification", ref_name=r.name))
	for r in _safe_rows("Foundations for a Legal Education", filters=DRILLDOWNS["fle_lms_pending"]["filters"](ctx, {}), fields=["name", "candidate_name", "timestamp"], order_by="timestamp asc", limit=per):
		out.append(dict(item=_("FLE LMS account missing — {0}").format(r.candidate_name or r.name), module=_("FLE"), owner="", when=r.timestamp, status=_("LMS pending"), ref_doctype="Foundations for a Legal Education", ref_name=r.name))
	labels = _faculty_labels(r.get("owner_id") for r in out)
	for i, r in enumerate(out):
		if r.get("owner_id") is not None:
			r["owner"] = labels.get(str(r.pop("owner_id")), "")
		r["owner"] = frappe.utils.get_fullname(r["owner"]) if r.get("owner") and "@" in str(r["owner"]) else r.get("owner", "")
		r["name"] = f"{r['ref_doctype']}::{r['ref_name']}"
	out = _only_modules(out, p)
	return [frappe._dict(r) for r in out]


# Dashboard module key → the module label used on multi-source rows (pending operations, activity).
MODULE_LABELS = {
	"admission": "Admission", "registration": "Student Registration", "programme": "Programme Management",
	"attendance": "Attendance", "idcard": "ID Card", "fees": "Fees", "venue": "Venue Booking",
	"pace": "PACE", "fle": "FLE", "exams": "Examinations",
}


def _only_modules(rows, p):
	"""Narrow multi-source rows to one module (`module`) or the user's chosen set (`modules`, comma list).
	Only whitelisted module keys are honoured; anything else is ignored."""
	p = p or {}
	keys = [p.get("module")] if p.get("module") else [k.strip() for k in (p.get("modules") or "").split(",") if k.strip()]
	labels = {_(MODULE_LABELS[k]) for k in keys if k in MODULE_LABELS}
	return [r for r in rows if r["module"] in labels] if labels else rows


def _created(r):
	return r.get("creation") and r.get("modified") and abs((r.modified - r.creation).total_seconds()) < 5


ACTIVITY_SOURCES = [
	# doctype, module, fields, filter builder, subject, action(created, row)
	("Student Master", "Student Registration", ["first_name", "student_status", "registration_status"], lambda c: f_students(c), lambda r: r.first_name, lambda n, r: _("Student registered") if n else _("Student record updated"), lambda r: r.registration_status or r.student_status),
	("Applicant", "Admission", ["candidate_name", "status"], lambda c: f_applicants(c), lambda r: r.candidate_name, lambda n, r: _("Application created") if n else _("Application updated"), lambda r: r.status),
	("Student Enrollment", "Programme Management", ["student_name", "status", "program"], lambda c: ([_in("program", c.programmes())] if c.programmes() is not None else []) + ([["batch", "in", c.batch]] if c.batch else []), lambda r: r.student_name, lambda n, r: _("Enrolment created") if n else _("Enrolment updated"), lambda r: r.status),
	("Attendance Session", "Attendance", ["course", "session_status", "attendance_marked"], lambda c: f_sessions(c, False), lambda r: r.course, lambda n, r: _("Session scheduled") if n else (_("Attendance marked") if cint(r.attendance_marked) else _("Session updated")), lambda r: r.session_status),
	("Student Attendance", "Attendance", ["student_name", "course", "status"], lambda c: [x for x in f_attendance(c) if x[0] != "attendance_date"], lambda r: r.student_name, lambda n, r: _("Attendance recorded — {0}").format(r.course or ""), lambda r: r.status),
	("Student Attendance Condonation", "Attendance", ["student_name", "course", "final_status"], lambda c: f_condonation(c), lambda r: r.student_name, lambda n, r: _("Condonation requested") if n else _("Condonation updated"), lambda r: r.final_status),
	("Student Course Marks", "Examinations", ["student", "course", "status"], lambda c: f_marks(c), lambda r: r.student, lambda n, r: _("Marks entered — {0}").format(r.course or "") if n else _("Marks updated — {0}").format(r.course or ""), lambda r: r.status),
	("Student Result Publish", "Examinations", ["student", "exam_plan", "is_published"], lambda c: f_results(c), lambda r: r.student, lambda n, r: _("Result published — {0}").format(r.exam_plan or "") if cint(r.is_published) else _("Result updated — {0}").format(r.exam_plan or ""), lambda r: "Published" if cint(r.is_published) else "Unpublished"),
	("Fee Payment", "Fees", ["student_name", "student", "status"], lambda c: ([["academic_year", "in", c.academic_year]] if c.academic_year else []) + ([_in("student", c.student_names())] if c.has_student_constraint() else []), lambda r: r.student_name or r.student, lambda n, r: _("Fee payment recorded") if n else _("Fee payment updated"), lambda r: r.status),
	("Venue Booking", "Venue Booking", ["event_name", "status"], lambda c: [], lambda r: r.event_name, lambda n, r: _("Venue booking requested") if n else _("Venue booking updated"), lambda r: r.status),
	("ID Card Generation", "ID Card", ["student_name", "card_status"], lambda c: f_idcards(c), lambda r: r.student_name, lambda n, r: _("ID card created") if n else _("ID card updated"), lambda r: r.card_status),
	("PACE Application", "PACE", ["applicant_name", "status"], lambda c: f_pace(c), lambda r: r.applicant_name, lambda n, r: _("PACE application created") if n else _("PACE application updated"), lambda r: r.status),
	("Foundations for a Legal Education", "FLE", ["candidate_name", "enrollment_status"], lambda c: [], lambda r: r.candidate_name, lambda n, r: _("FLE registration") if n else _("FLE registration updated"), lambda r: r.enrollment_status),
]


def _virtual_recent_activity(ctx, p):
	"""Latest changes across SLCM modules, each source read through the caller's permissions."""
	out = []
	for doctype, module, fields, fb, subject, action, status in ACTIVITY_SOURCES:
		rows = _safe_rows(doctype, filters=fb(ctx), fields=["name", "creation", "modified", "modified_by", *fields], order_by="modified desc", limit=25)
		for r in rows:
			out.append(frappe._dict(
				name=f"{doctype}::{r.name}", when=r.modified, subject=subject(r) or r.name, action=action(_created(r), r),
				module=_(module), status=status(r) or "", by=frappe.utils.get_fullname(r.modified_by), ref_doctype=doctype, ref_name=r.name,
			))
	out.sort(key=lambda r: r.when or datetime.datetime.min, reverse=True)
	return _only_modules(out, p)[:200]


def _current_terms(ctx):
	f = [["status", "!=", "Inactive"], ["term_start_date", "<=", nowdate()], ["term_end_date", ">=", nowdate()]]
	if ctx.academic_year:
		f.append(["academic_year", "in", ctx.academic_year])
	return f


PENDING_COLUMNS = [
	("item", "Item", "text", True),
	("module", "Module", "text", True),
	("owner", "Owner / Responsible", "text", True),
	("when", "Date", "date", True),
	("status", "Status", "badge", True),
	("ref_name", "Open", "record", False),
]
ACTIVITY_COLUMNS = [
	("when", "When", "datetime", True),
	("subject", "Record", "text", True),
	("action", "Action", "text", True),
	("module", "Module", "text", True),
	("status", "Status", "badge", True),
	("by", "By", "text", True),
	("ref_name", "Open", "record", False),
]
SCHEDULE_COLUMNS = [
	("from_time", "From", "time", True),
	("to_time", "To", "time", True),
	("course", "Course", "text", True),
	("instructor_name", "Faculty", "text", False),
	("venue", "Venue", "text", True),
	("batch", "Batch", "text", False),
	("section", "Section", "text", True),
	("class_state", "Status", "badge", False),
	("name", "Class", "form", True),
]

DRILLDOWNS.update({
	"years_active": _drill("Active Academic Years", "Academic Year", [("name", "Academic Year", "form", True), ("academic_system", "System", "text", True), ("year_start_date", "Start", "date", True), ("year_end_date", "End", "date", True), ("status", "Status", "badge", True)], lambda c, p: [["status", "=", "Active"]] + ([["name", "in", c.academic_year]] if c.academic_year else []), ["name"], ("year_start_date", "desc"), "years"),
	"terms_current": _drill("Current Academic Terms", "Academic Term", [("name", "Academic Term", "form", True), ("academic_year", "Academic Year", "text", True), ("system", "System", "text", True), ("term_start_date", "Start", "date", True), ("term_end_date", "End", "date", True), ("status", "Status", "badge", True)], lambda c, p: _current_terms(c), ["name", "academic_year"], ("term_start_date", "desc"), "years", description="Active terms whose dates include today."),
	"calendar_upcoming": _drill("Upcoming Academic Calendar (Next 30 Days)", "Institutional Calendar", [("name", "Entry", "form", True), ("name1", "Title", "text", True), ("entry_type", "Type", "badge", True), ("start_date", "Start", "date", True), ("end_date", "End", "date", True), ("academic_year", "Academic Year", "text", True)], lambda c, p: [["status", "!=", "Inactive"], ["end_date", ">=", nowdate()], ["start_date", "<=", add_days(nowdate(), 30)]] + ([["academic_year", "in", c.academic_year]] if c.academic_year else []), ["name1", "entry_type"], ("start_date", "asc"), "years"),
	"students_no_section": _drill("Active Students Without a Section", "Student Master", STUDENT_COLUMNS, lambda c, p: f_students(c) + [["student_status", "=", "Active"], ["section", "is", "not set"]], STUDENT_SEARCH, ("first_name", "asc"), "students"),
	"classes_no_venue": _drill("Upcoming Classes Without a Venue (Next 14 Days)", "Time Table", CLASS_COLUMNS, lambda c, p: f_classes(c, False) + [["schedule_date", "between", [nowdate(), add_days(nowdate(), 14)]], ["venue", "is", "not set"]], CLASS_SEARCH, ("schedule_date", "asc"), "classes_nodate", post=lambda r: _post_faculty(r, "instructor", "instructor_name"), extra_fields=["instructor"]),
	"venue_pending": _drill("Venue Requests Pending Allotment", "Venue Booking", [("name", "Booking", "form", True), ("event_name", "Event", "text", True), ("venue", "Venue", "text", True), ("start_datetime", "Starts", "datetime", True), ("end_datetime", "Ends", "datetime", True), ("requester_type", "Requested By", "text", True), ("requester_name", "Requester", "text", True), ("status", "Status", "badge", True)], lambda c, p: [["status", "=", "Pending Allotment"]], ["name", "event_name", "venue", "requester_name"], ("start_datetime", "asc"), "all_time"),
	"venue_bookings": _drill("Allotted Venue Bookings", "Venue Booking", [("name", "Booking", "form", True), ("event_name", "Event", "text", True), ("venue", "Venue", "text", True), ("building", "Building", "text", True), ("start_datetime", "Starts", "datetime", True), ("end_datetime", "Ends", "datetime", True), ("expected_attendees", "Attendees", "int", True), ("status", "Status", "badge", True)], lambda c, p: _venue_range(c) + [["status", "=", "Allotted"]], ["name", "event_name", "venue"], ("start_datetime", "asc"), "venues"),
	"todays_schedule": _drill("Today's Schedule", "Time Table", SCHEDULE_COLUMNS, lambda c, p: f_classes(c, False) + [["schedule_date", "=", nowdate()]], CLASS_SEARCH, ("from_time", "asc"), "classes_nodate", post=_post_schedule, extra_fields=["instructor", "course_offering", "schedule_date"]),
	"offerings_incomplete": _drill("Course Offerings With Attendance Not Entered", None, [("course_offering", "Course Offering", "offering", True), ("course", "Course", "text", True), ("sessions_unmarked", "Sessions Not Marked", "int", True), ("oldest", "Oldest", "date", True), ("latest", "Latest", "date", True)], None, ["course_offering", "course"], ("sessions_unmarked", "desc"), "sessions", virtual=_virtual_offerings_incomplete, description="Grouped from past, non-cancelled sessions without attendance."),
	"pending_operations": _drill("Pending Operations", None, PENDING_COLUMNS, None, ["item", "module", "owner", "status"], ("when", "asc"), "pending", virtual=_virtual_pending_operations, description="Open items across modules, oldest first. Up to 50 per source; each source respects your permissions.", params={"module": "optional", "modules": "optional"}),
	"recent_activity": _drill("Recent Activity", None, ACTIVITY_COLUMNS, None, ["subject", "action", "module", "status", "by"], ("when", "desc"), "activity", virtual=_virtual_recent_activity, description="Latest changes across SLCM modules you can access (up to 200).", params={"modules": "optional"}),
})

# ── module-specific sources: ID Card · Fees · Venue Booking · PACE · FLE ─────────


def _date_range_on(ctx, field, is_datetime=False):
	f = []
	if ctx.from_date:
		f.append([field, ">=", ctx.from_date])
	if ctx.to_date:
		f.append([field, "<" if is_datetime else "<=", add_days(ctx.to_date, 1) if is_datetime else ctx.to_date])
	return f


def f_idcards(ctx):
	f = [["card_type", "=", "Student"]]
	if ctx.academic_year:
		f.append(["academic_year", "in", ctx.academic_year])
	if ctx.programmes() is not None:
		f.append(_in("programme", ctx.programmes()))
	if ctx.batch:
		f.append(["batch", "in", ctx.batch])
	return f


def f_idprints(ctx):
	f = _date_range_on(ctx, "printed_on", True)
	if ctx.academic_year:
		f.append(["academic_year", "in", ctx.academic_year])
	if ctx.programmes() is not None:
		f.append(_in("program", ctx.programmes()))
	if ctx.batch:
		f.append(["batch", "in", ctx.batch])
	return f


def f_student_linked(ctx, year_field="academic_year"):
	f = []
	if ctx.academic_year and year_field:
		f.append([year_field, "in", ctx.academic_year])
	if ctx.has_student_constraint():
		f.append(_in("student", ctx.student_names()))
	return f


def f_payments(ctx):
	return [["docstatus", "=", 1]] + _date_range_on(ctx, "payment_date") + f_student_linked(ctx)


def f_refunds(ctx):
	return [["docstatus", "=", 1], ["status", "=", "Approved"]] + _date_range_on(ctx, "refund_date") + f_student_linked(ctx, None)


def f_concessions(ctx):
	return [["docstatus", "=", 1], ["status", "=", "Approved"]] + _date_range_on(ctx, "concession_date") + f_student_linked(ctx)


def f_pace(ctx):
	return [["academic_year", "in", ctx.academic_year]] if ctx.academic_year else []


def _pace_statuses(kind):
	rows = frappe.get_all("PACE Application Status", fields=["name", "status_type", "stage_type"])
	if kind == "closed":
		return [r.name for r in rows if r.status_type == "Closed"]
	if kind == "enrolled":
		return [r.name for r in rows if (r.stage_type or "").startswith("Enrol")]
	closed = {r.name for r in rows if r.status_type == "Closed" or (r.stage_type or "").startswith("Enrol")}
	return [r.name for r in rows if r.name not in closed]


def f_fle(ctx):
	return _date_range_on(ctx, "timestamp", True)


ID_COLUMNS = [("name", "Card", "form", True), ("student", "Student ID", "student", True), ("student_name", "Student", "text", True), ("programme", "Programme", "text", True), ("batch", "Batch", "text", True), ("academic_year", "Academic Year", "text", True), ("card_status", "Status", "badge", True), ("issue_date", "Issued", "date", True), ("expiry_date", "Expires", "date", True), ("print_count", "Prints", "int", True)]
PAYMENT_COLUMNS = [("name", "Payment", "form", True), ("student", "Student ID", "student", True), ("student_name", "Student", "text", True), ("fee_component", "Fee Component", "text", True), ("paid_amount", "Amount", "currency", True), ("payment_mode", "Mode", "text", True), ("payment_date", "Paid On", "date", True), ("receipt", "Receipt", "text", True)]
VENUE_COLUMNS = [("name", "Booking", "form", True), ("event_name", "Event", "text", True), ("venue", "Venue", "text", True), ("building", "Building", "text", True), ("start_datetime", "Starts", "datetime", True), ("end_datetime", "Ends", "datetime", True), ("requester_type", "Requested By", "text", True), ("requester_name", "Requester", "text", True), ("status", "Status", "badge", True)]
PACE_COLUMNS = [("name", "Application", "form", True), ("applicant_name", "Applicant", "text", True), ("programme", "PACE Programme", "text", True), ("academic_year", "Academic Year", "text", True), ("submission_date", "Submitted", "date", True), ("status", "Status", "badge", True), ("modified", "Updated On", "datetime", True)]
FLE_COLUMNS = [("name", "Registration", "form", True), ("candidate_name", "Candidate", "text", True), ("candidate_email_id", "Email", "text", True), ("last_class_attended", "Last Class", "text", True), ("timestamp", "Registered", "datetime", True), ("enrollment_status", "Enrolment", "badge", True), ("payment_status", "Payment", "badge", True), ("paid_amount", "Paid", "currency", True)]
TICKET_COLUMNS = [("name", "Ticket", "form", True), ("subject", "Subject", "text", True), ("raised_by", "Raised By", "text", True), ("ticket_type", "Type", "text", True), ("agent_group", "Team", "text", True), ("priority", "Priority", "text", True), ("opening_date", "Opened", "date", True), ("status", "Status", "badge", True)]
TICKET_SEARCH = ["name", "subject", "raised_by"]
# Chart bars pass one of these as a drilldown param; each maps 1:1 to an equality filter on that field.
TICKET_PARAMS = ("status", "agent_group", "ticket_type", "raised_by")
VENUE_PARAMS = ("status", "requester_type", "replied_by", "swap_status")
TICKET_CLOSED_CATEGORIES = ("Resolved", "Closed")
REQUESTER_KINDS = ("Student", "Faculty", "Other")


def _param_filters(p, names):
	return [[k, "=", p[k]] for k in names if p.get(k)]


def f_tickets(ctx):
	return _date_range_on(ctx, "opening_date")


def _open_tickets():
	return [["status_category", "not in", TICKET_CLOSED_CATEGORIES]]


def _people_emails():
	"""(student emails, faculty emails), lower-cased. Used only to classify who raised a ticket —
	never returned. Cached per request."""
	if not getattr(frappe.local, "uq_people_emails", None):
		def collect(doctype, fields):
			out = set()
			for r in frappe.get_all(doctype, fields=fields):
				out.update((r.get(f) or "").strip().lower() for f in fields)
			out.discard("")
			return out

		frappe.local.uq_people_emails = (
			collect("Student Master", ["email", "official_email_id", "personal_email", "user"]),
			collect("Faculty", ["email", "official_email_id", "user_id"]),
		)
	return frappe.local.uq_people_emails


def _requester_kind(email):
	email = (email or "").strip().lower()
	students, faculty = _people_emails()
	return "Student" if email in students else "Faculty" if email in faculty else "Other"


def _ticket_kind_filter(p):
	kind = p.get("kind")
	if kind not in REQUESTER_KINDS:
		return []
	students, faculty = _people_emails()
	if kind == "Other":
		known = sorted(students | faculty)
		return [["raised_by", "not in", known]] if known else []
	return [["raised_by", "in", sorted(students if kind == "Student" else faculty) or [NONE]]]

DRILLDOWNS.update({
	# ID Card
	"idcards": _drill("Student ID Cards", "ID Card Generation", ID_COLUMNS, lambda c, p: f_idcards(c), ["name", "student", "student_name"], ("modified", "desc"), "idcards"),
	"idcards_generated": _drill("Student ID Cards Generated / Printed", "ID Card Generation", ID_COLUMNS, lambda c, p: f_idcards(c) + [["card_status", "in", ["Generated", "Printed"]]], ["name", "student", "student_name"], ("issue_date", "desc"), "idcards"),
	"idcards_error": _drill("ID Cards With Errors", "ID Card Generation", ID_COLUMNS, lambda c, p: f_idcards(c) + [["card_status", "=", "Error"]], ["name", "student", "student_name"], ("modified", "desc"), "idcards"),
	"idcards_cancelled": _drill("Cancelled / Expired ID Cards", "ID Card Generation", ID_COLUMNS, lambda c, p: f_idcards(c) + [["card_status", "in", ["Cancelled", "Expired"]]], ["name", "student", "student_name"], ("modified", "desc"), "idcards"),
	"idcard_prints": _drill("ID Card Print Runs", "ID Card Print Log", [("name", "Print Log", "form", True), ("print_action_type", "Action", "text", True), ("print_type", "Type", "badge", True), ("total_cards_in_bulk", "Cards", "int", True), ("printed_on", "Printed On", "datetime", True), ("printed_by", "Printed By", "text", True), ("program", "Programme", "text", True), ("batch", "Batch", "text", True)], lambda c, p: f_idprints(c), ["name", "bulk_print_id", "program", "batch"], ("printed_on", "desc"), "idprints"),
	"students_no_rfid": _drill("Active Students Without an RFID Card", "Student Master", STUDENT_COLUMNS[:6] + [("rfid_uid", "RFID", "text", True), ("id_card_issued", "ID Card Issued", "badge", True)], lambda c, p: f_students(c) + [["student_status", "=", "Active"], ["rfid_uid", "is", "not set"]], STUDENT_SEARCH, ("first_name", "asc"), "students"),
	# Fees
	"fee_payments": _drill("Fee Payments Received", "Fee Payment", PAYMENT_COLUMNS, lambda c, p: f_payments(c), ["name", "student", "student_name", "fee_component", "reference_number"], ("payment_date", "desc"), "payments"),
	"fee_refunds": _drill("Approved Fee Refunds", "Fee Refund", [("name", "Refund", "form", True), ("student", "Student ID", "student", True), ("student_name", "Student", "text", True), ("fee_component", "Fee Component", "text", True), ("refund_type", "Type", "text", True), ("refund_amount", "Amount", "currency", True), ("refund_mode", "Mode", "text", True), ("refund_date", "Refunded On", "date", True), ("status", "Status", "badge", True)], lambda c, p: f_refunds(c), ["name", "student", "student_name"], ("refund_date", "desc"), "refunds"),
	"fee_concessions": _drill("Approved Fee Concessions", "Fee Concession", [("name", "Concession", "form", True), ("student", "Student ID", "student", True), ("fee_component", "Fee Component", "text", True), ("concession_type", "Type", "text", True), ("waiver_value", "Waiver", "currency", True), ("concession_date", "Date", "date", True), ("status", "Status", "badge", True)], lambda c, p: f_concessions(c), ["name", "student", "registration_id"], ("concession_date", "desc"), "payments"),
	# Venue booking
	"venue_bookings_all": _drill("Venue Bookings in Date Range", "Venue Booking", VENUE_COLUMNS + [("replied_by", "Decided By", "text", True), ("swap_status", "Swap", "badge", True)], lambda c, p: _venue_range(c) + _param_filters(p, VENUE_PARAMS), ["name", "event_name", "venue", "requester_name"], ("start_datetime", "desc"), "venues", params={k: "optional" for k in VENUE_PARAMS}),
	# Helpdesk
	"tickets_open": _drill("Open Tickets", "HD Ticket", TICKET_COLUMNS, lambda c, p: _open_tickets() + _param_filters(p, TICKET_PARAMS) + _ticket_kind_filter(p), TICKET_SEARCH, ("opening_date", "asc"), "all_time", params={k: "optional" for k in TICKET_PARAMS + ("kind",)}, all_time=True),
	"tickets_range": _drill("Tickets Raised in Date Range", "HD Ticket", TICKET_COLUMNS, lambda c, p: f_tickets(c) + _param_filters(p, TICKET_PARAMS) + _ticket_kind_filter(p), TICKET_SEARCH, ("opening_date", "desc"), "tickets", params={k: "optional" for k in TICKET_PARAMS + ("kind",)}),
	"venue_bookings_closed": _drill("Rejected / Cancelled Venue Bookings", "Venue Booking", VENUE_COLUMNS + [("admin_remarks", "Remarks", "text", False)], lambda c, p: _venue_range(c) + [["status", "in", ["Rejected", "Cancelled"]]], ["name", "event_name", "venue"], ("start_datetime", "desc"), "venues"),
	"venues_active": _drill("Active Venues", "Venue Master", [("name", "Venue", "form", True), ("venue_code", "Code", "text", True), ("venue_type", "Type", "text", True), ("building", "Building", "text", True), ("floor", "Floor", "text", True), ("capacity", "Capacity", "int", True)], lambda c, p: [["is_active", "=", 1]], ["name", "venue_code", "building"], ("name", "asc"), "all_time"),
	# PACE
	"pace_applications": _drill("PACE Applications", "PACE Application", PACE_COLUMNS, lambda c, p: f_pace(c), ["name", "applicant_name", "email_address"], ("modified", "desc"), "pace"),
	"pace_in_progress": _drill("PACE Applications in Progress", "PACE Application", PACE_COLUMNS, lambda c, p: f_pace(c) + [_in("status", _pace_statuses("in_progress"))], ["name", "applicant_name", "email_address"], ("modified", "desc"), "pace"),
	"pace_enrolled": _drill("PACE Applicants Enrolled", "PACE Application", PACE_COLUMNS, lambda c, p: f_pace(c) + [_in("status", _pace_statuses("enrolled"))], ["name", "applicant_name", "email_address"], ("modified", "desc"), "pace"),
	"pace_enquiries_new": _drill("New PACE Enquiries", "PACE Enquiry", [("name", "Enquiry", "form", True), ("full_name", "Name", "text", True), ("email", "Email", "text", True), ("phone", "Phone", "text", True), ("programme_of_interest", "Programme", "text", True), ("submitted_on", "Submitted", "datetime", True), ("status", "Status", "badge", True)], lambda c, p: [["status", "=", "New"]], ["name", "full_name", "email"], ("submitted_on", "desc"), "all_time"),
	"pace_verification_pending": _drill("PACE Document Verifications Pending", "PACE Document Verification", [("name", "Verification", "form", True), ("applicant_name", "Applicant", "text", True), ("programme", "Programme", "text", True), ("assigned_verifier", "Verifier", "text", True), ("due_date", "Due", "date", True), ("is_overdue", "Overdue", "int", True), ("status", "Status", "badge", True)], lambda c, p: f_pace(c) + [["status", "in", ["Pending", "Returned for Correction"]]], ["name", "applicant_name", "application"], ("due_date", "asc"), "pace"),
	# FLE
	"fle_registrations": _drill("FLE Registrations", "Foundations for a Legal Education", FLE_COLUMNS, lambda c, p: f_fle(c), ["name", "candidate_name", "candidate_email_id"], ("timestamp", "desc"), "fle"),
	"fle_enrolled": _drill("FLE Candidates Enrolled", "Foundations for a Legal Education", FLE_COLUMNS, lambda c, p: f_fle(c) + [["enrollment_status", "in", ["Enrolled", "In Progress", "Completed"]]], ["name", "candidate_name", "candidate_email_id"], ("timestamp", "desc"), "fle"),
	"fle_unpaid": _drill("FLE Registrations Without Captured Payment", "Foundations for a Legal Education", FLE_COLUMNS, lambda c, p: f_fle(c) + [["payment_status", "!=", "Captured"]], ["name", "candidate_name", "candidate_email_id"], ("timestamp", "desc"), "fle"),
	"fle_lms_pending": _drill("Paid FLE Candidates Without an LMS Account", "Foundations for a Legal Education", FLE_COLUMNS, lambda c, p: f_fle(c) + [["payment_status", "=", "Captured"], ["lms_account_created", "=", 0]], ["name", "candidate_name", "candidate_email_id"], ("timestamp", "asc"), "fle"),
})
SCOPE.update({
	"idcards": [Y, P, B],
	"idprints": [DR, Y, P, B],
	"payments": [DR, Y, P, B, S, ST, G],
	"refunds": [DR, P, B, S, ST, G],
	"pace": [Y],
	"fle": [DR],
	"years": [Y],
	"venues": [DR],
	"tickets": [DR],
	"current_admission": [P],
	"pending": [Y, T, P, B, S, C, F, ST, G, DR],
	"activity": [Y, T, P, B, S, C, F, ST, G],
})


# ─────────────────────────────────────────────────────────────── cards
# Each card declares its section, the question it answers, its data source, the filters it honours,
# whether it is all-time, and its drilldown. `value` is computed through permission-checked helpers.


def _card(key, section, title, description, doctype, scope, value_fn, *, drill=None, fmt="int", tone="default", action="View details", sub_fn=None, alert=False, all_time=False, icon="chart", headline=False, compare=False):
	return dict(
		compare=compare,
		headline=headline,
		key=key,
		section=section,
		title=title,
		description=description,
		doctype=doctype,
		scope=scope,
		value_fn=value_fn,
		drill=drill,
		fmt=fmt,
		tone=tone,
		action=action,
		sub_fn=sub_fn,
		alert=alert,
		all_time=all_time,
		icon=icon,
	)


def _campus_share(ctx, campus):
	active = _count("Student Master", f_students(ctx) + [["student_status", "=", "Active"]])
	n = _count("Student Master", f_students(ctx) + [["student_status", "=", "Active"], ["campus", "=", campus]])
	unset = _count("Student Master", f_students(ctx) + [["student_status", "=", "Active"], ["campus", "is", "not set"]])
	text = _("{0}% of active students").format(round(100.0 * n / active)) if active else _("no active students")
	return text + (" · " + _("{0} not recorded").format(unset) if unset else "")


def _drill_count(key):
	return lambda c: _count(DRILLDOWNS[key]["doctype"], DRILLDOWNS[key]["filters"](c, {}))


def _below_threshold_students(c):
	return _distinct_count("Attendance Summary", DRILLDOWNS["below_threshold"]["filters"](c, {}), "student")


def _present_rate(c):
	rows = _group("Student Attendance", f_attendance(c), "status")
	total = sum(cint(r.v) for r in rows)
	if not total:
		return None
	return 100.0 * sum(cint(r.v) for r in rows if r.status in PRESENT_STATUSES) / total


def _published_avg_gpa(c):
	return _aggregate("Student Result Publish", f_results(c) + [["is_published", "=", 1]], "AVG", "term_gpa")


def _entry_rate(c):
	past = f_sessions(c) + _past_open_sessions()
	total = _count("Attendance Session", past)
	if not total:
		return None
	return 100.0 * _count("Attendance Session", past + [["attendance_marked", "=", 1]]) / total


def _current_term_value(c):
	names = [t.name for t in frappe.get_list("Academic Term", filters=_current_terms(c), fields=["name"], order_by="term_start_date desc")]
	return ", ".join(names) if names else None


def _current_term_sub(c):
	rows = frappe.get_list("Academic Term", filters=_current_terms(c), fields=["term_start_date", "term_end_date"], order_by="term_start_date desc", limit=1)
	if not rows:
		return _("No term covers today")
	r = rows[0]
	return _("{0} – {1}").format(frappe.utils.formatdate(r.term_start_date), frappe.utils.formatdate(r.term_end_date))


def _virtual_count(key):
	return lambda c: len(DRILLDOWNS[key]["virtual"](c, {}))


def _sum(doctype, filters, field):
	return lambda c: _aggregate(doctype, filters(c), "SUM", field) or 0


# Every card belongs to one module (its `section`). `headline` cards appear on the module's tile on the
# home screen; `alert` cards also roll up into the cross-module "Action Required" list.
M = dict(admission="admission", registration="registration", programme="programme", attendance="attendance", idcard="idcard", fees="fees", venue="venue", pace="pace", fle="fle", exams="exams")
CARDS = [
	# ── Admission
	_card("admission_current", "admission", "Registered — Current Admission", "Applicants registered in the admission cycle that is currently active (any status).", "Applicant", "current_admission", _drill_count("admission_current"), drill="admission_current", icon="user-plus", action="View applicants", headline=True, sub_fn=_current_admission_sub),
	_card("applications", "admission", "Applications", "Admission applications for the selected year and programme.", "Applicant", "applicants", _drill_count("applications"), drill="applications", icon="inbox", action="View applications", headline=True),
	_card("applications_in_progress", "admission", "In Progress", "Submitted applications still moving through the pipeline.", "Applicant", "applicants", _drill_count("applications_in_progress"), drill="applications_in_progress", icon="loader", headline=True),
	_card("applications_enrolled", "admission", "Enrolled", "Applicants who completed enrolment.", "Applicant", "applicants", _drill_count("applications_enrolled"), drill="applications_enrolled", icon="user-check", headline=True),
	_card("applications_draft", "admission", "Not Yet Submitted", "Applications saved as Draft.", "Applicant", "applicants", _drill_count("applications_draft"), drill="applications_draft", icon="edit"),
	_card("applications_closed", "admission", "Rejected / Withdrawn", "Applications closed by rejection, withdrawal, decline or expiry.", "Applicant", "applicants", _drill_count("applications_closed"), drill="applications_closed", icon="user-x"),
	# ── Student Registration
	_card("students", "registration", "Total Students", "All students matching the filters, any status.", "Student Master", "students", _drill_count("students"), drill="students", icon="users", action="View students", headline=True),
	_card("active_students", "registration", "Active Students", "Students with status Active in the selected scope.", "Student Master", "students", _drill_count("students_active"), drill="students_active", icon="user-check", action="View students", headline=True,
		sub_fn=lambda c: _("{0}% of students in scope").format(round(100.0 * _count("Student Master", f_students(c) + [["student_status", "=", "Active"]]) / max(_count("Student Master", f_students(c)), 1)))),
	_card("students_on_campus", "registration", "On Campus Students", "Active students whose campus is On Campus.", "Student Master", "students", _drill_count("students_on_campus"), drill="students_on_campus", icon="home", action="View students", headline=True, sub_fn=lambda c: _campus_share(c, "On Campus")),
	_card("students_off_campus", "registration", "Off Campus Students", "Active students whose campus is Off Campus.", "Student Master", "students", _drill_count("students_off_campus"), drill="students_off_campus", icon="building", action="View students", headline=True, sub_fn=lambda c: _campus_share(c, "Off Campus")),
	_card("students_new", "registration", "Newly Registered", "Students whose registration date falls within the date range.", "Student Master", "registered", _drill_count("students_new"), drill="students_new", compare=True, icon="user-plus", action="View students"),
	_card("students_graduated", "registration", "Graduated / Alumni", "Students with status Graduated or Alumni.", "Student Master", "students", _drill_count("students_graduated"), drill="students_graduated", icon="award", action="View students"),
	_card("students_inactive", "registration", "Inactive / Dropped", "Students who are Inactive, Dropped, Dormant or Withdrawn.", "Student Master", "students", _drill_count("students_inactive"), drill="students_inactive", icon="user-x", action="View students"),
	_card("registration_pending", "registration", "Registrations Not Completed", "Students whose registration workflow is still in progress.", "Student Master", "students", _drill_count("registration_pending"), drill="registration_pending", alert=True, action="View students", icon="user-check", headline=True),
	_card("students_no_section", "registration", "Active Students Without a Section", "Active students who have not been placed in a section.", "Student Master", "students", _drill_count("students_no_section"), drill="students_no_section", alert=True, action="View students", icon="users"),
	# ── Programme Management (structure + teaching schedule)
	_card("current_term", "programme", "Current Academic Term", "The active term(s) whose dates include today.", "Academic Term", "years", _current_term_value, drill="terms_current", fmt="text", icon="calendar", action="View terms", sub_fn=_current_term_sub),
	_card("programmes", "programme", "Active Programmes", "Programmes marked Active.", "Programme", "programmes", _drill_count("programmes"), drill="programmes", icon="graduation", action="View programmes", headline=True),
	_card("active_offerings", "programme", "Courses Running", "Active course offerings for the selected year, term and programme.", "Course Offering", "offerings", _drill_count("offerings"), drill="offerings", icon="book", action="View courses", headline=True),
	_card("batches", "programme", "Current Batches", "Batches with status Active.", "Batch", "batches", _drill_count("batches"), drill="batches", icon="layers", action="View batches"),
	_card("courses", "programme", "Active Courses", "Courses in the course catalogue marked Active.", "Course", "courses", _drill_count("courses"), drill="courses", icon="book"),
	_card("faculty", "programme", "Active Faculty", "Faculty members with status Active.", "Faculty", "faculty", _drill_count("faculty"), drill="faculty", icon="briefcase", action="View faculty"),
	_card("years_active", "programme", "Active Academic Years", "Academic years with status Active.", "Academic Year", "years", _drill_count("years_active"), drill="years_active", icon="history"),
	_card("calendar_upcoming", "programme", "Upcoming Calendar Events", "Institutional calendar entries in the next 30 days.", "Institutional Calendar", "years", _drill_count("calendar_upcoming"), drill="calendar_upcoming", icon="flag", action="View calendar"),
	_card("todays_classes", "programme", "Today's Classes", "Classes on today's timetable (date range not applied).", "Time Table", "classes_nodate", _drill_count("todays_classes"), drill="todays_schedule", icon="clock", action="View schedule", headline=True),
	_card("upcoming_classes", "programme", "Upcoming Classes", "Timetabled classes in the next 7 days.", "Time Table", "classes_nodate", _drill_count("upcoming_classes"), drill="upcoming_classes", icon="calendar", action="View schedule"),
	_card("classes_period", "programme", "Classes in Date Range", "Timetabled classes within the selected date range.", "Time Table", "classes", _drill_count("classes_period"), drill="classes_period", compare=True, icon="calendar", action="View schedule"),
	_card("sessions_conducted", "programme", "Completed Sessions", "Sessions marked Conducted in the date range.", "Attendance Session", "sessions", _drill_count("sessions_conducted"), drill="sessions_conducted", compare=True, icon="check"),
	_card("sessions_cancelled", "programme", "Cancelled / Postponed", "Sessions in the date range that were cancelled or postponed.", "Attendance Session", "sessions", _drill_count("sessions_cancelled"), drill="sessions_cancelled", icon="x-circle"),
	# ── Attendance
	_card("avg_attendance", "attendance", "Average Attendance", "Mean attendance % across student-course summaries in scope.", "Attendance Summary", "summary", lambda c: _aggregate("Attendance Summary", f_summary(c), "AVG", "attendance_percentage"), drill="attendance_summary", fmt="pct", icon="check", headline=True,
		sub_fn=lambda c: _("across {0} student-course records").format(_count("Attendance Summary", f_summary(c)))),
	_card("entry_rate", "attendance", "Attendance Entry Rate", "Share of past, non-cancelled sessions in the date range with attendance marked.", "Attendance Session", "sessions", _entry_rate, drill="unmarked_sessions", fmt="pct", icon="clipboard", action="View unmarked", headline=True),
	_card("present_rate", "attendance", "Presence Rate", "Share of marked student attendance records that are Present, Late or OD.", "Student Attendance", "attendance", _present_rate, drill="attendance_records", fmt="pct", icon="activity",
		sub_fn=lambda c: _("from {0} attendance records").format(_count("Student Attendance", f_attendance(c)))),
	_card("summaries_eligible", "attendance", "Exam-Eligible Records", "Student-course records meeting the attendance requirement.", "Attendance Summary", "summary", lambda c: _count("Attendance Summary", f_summary(c) + [["eligible_for_exam", "=", 1]]), drill="attendance_summary", icon="shield"),
	_card("below_threshold", "attendance", "Students Below Attendance Threshold", "Students with at least one course where they are not exam-eligible on attendance.", "Attendance Summary", "summary", _below_threshold_students, drill="below_threshold", alert=True, action="View students", icon="alert", headline=True,
		sub_fn=lambda c: _("{0} course records affected").format(_count("Attendance Summary", DRILLDOWNS["below_threshold"]["filters"](c, {})))),
	_card("unmarked_sessions", "attendance", "Attendance Not Entered", "Past sessions in the date range that are not cancelled and have no attendance marked.", "Attendance Session", "sessions", _drill_count("unmarked_sessions"), drill="unmarked_sessions", alert=True, action="View sessions", icon="clipboard",
		sub_fn=lambda c: _("across {0} course offerings").format(_virtual_count("offerings_incomplete")(c))),
	_card("condonation_pending", "attendance", "Condonation Requests Pending", "Attendance condonation requests awaiting an approval decision.", "Student Attendance Condonation", "condonation", _drill_count("condonation_pending"), drill="condonation_pending", alert=True, action="Review requests", icon="file"),
	# ── ID Card
	_card("idcards_generated", "idcard", "ID Cards Generated", "Student ID cards with status Generated or Printed.", "ID Card Generation", "idcards", _drill_count("idcards_generated"), drill="idcards_generated", icon="card", action="View cards", headline=True),
	_card("idcards_total", "idcard", "ID Card Records", "All student ID card records in scope, any status.", "ID Card Generation", "idcards", _drill_count("idcards"), drill="idcards", icon="layers", action="View cards"),
	_card("idcard_prints", "idcard", "Print Runs", "ID card print runs within the date range.", "ID Card Print Log", "idprints", _drill_count("idcard_prints"), drill="idcard_prints", compare=True, icon="file", action="View prints"),
	_card("idcards_cancelled", "idcard", "Cancelled / Expired", "Student ID cards that were cancelled or have expired.", "ID Card Generation", "idcards", _drill_count("idcards_cancelled"), drill="idcards_cancelled", icon="x-circle", action="View cards"),
	_card("id_card_pending", "idcard", "Active Students Without ID Card", "Active students whose ID card has not been marked as issued.", "Student Master", "students", _drill_count("id_card_pending"), drill="id_card_pending", alert=True, action="View students", icon="card", headline=True),
	_card("idcards_error", "idcard", "ID Cards With Errors", "ID card generations that ended in Error.", "ID Card Generation", "idcards", _drill_count("idcards_error"), drill="idcards_error", alert=True, action="View cards", icon="alert", headline=True),
	_card("students_no_rfid", "idcard", "Active Students Without RFID", "Active students with no RFID card linked — they cannot tap in for attendance.", "Student Master", "students", _drill_count("students_no_rfid"), drill="students_no_rfid", alert=True, action="View students", icon="card"),
	# ── Fees
	_card("fee_outstanding", "fees", "Outstanding Fees", "Unpaid balance on non-cancelled fee demands.", "Fee Demand", "fees", lambda c: _aggregate("Fee Demand", f_fees(c), "SUM", "outstanding_amount") or 0, drill="fee_outstanding", fmt="currency", icon="rupee", headline=True,
		sub_fn=lambda c: _("{0} demands with a balance").format(_count("Fee Demand", DRILLDOWNS["fee_outstanding"]["filters"](c, {})))),
	_card("fee_collected", "fees", "Fees Collected", "Amount paid against non-cancelled fee demands.", "Fee Demand", "fees", lambda c: _aggregate("Fee Demand", f_fees(c), "SUM", "paid_amount") or 0, drill="fee_outstanding", fmt="currency", icon="wallet", headline=True),
	_card("fee_payments", "fees", "Payments Received", "Submitted fee payments dated within the date range.", "Fee Payment", "payments", _sum("Fee Payment", f_payments, "paid_amount"), drill="fee_payments", fmt="currency", compare=True, icon="wallet", action="View payments",
		sub_fn=lambda c: _("{0} payments").format(_count("Fee Payment", f_payments(c)))),
	_card("fee_refunds", "fees", "Refunds Paid", "Approved fee refunds dated within the date range.", "Fee Refund", "refunds", _sum("Fee Refund", f_refunds, "refund_amount"), drill="fee_refunds", fmt="currency", compare=True, icon="undo", action="View refunds",
		sub_fn=lambda c: _("{0} refunds").format(_count("Fee Refund", f_refunds(c)))),
	_card("fee_concessions", "fees", "Concessions Approved", "Approved fee concessions dated within the date range.", "Fee Concession", "payments", _sum("Fee Concession", f_concessions, "waiver_value"), drill="fee_concessions", fmt="currency", icon="award", action="View concessions",
		sub_fn=lambda c: _("{0} concessions").format(_count("Fee Concession", f_concessions(c)))),
	_card("fee_overdue", "fees", "Overdue Fee Demands", "Open fee demands past their due date.", "Fee Demand", "fees", _drill_count("fee_overdue"), drill="fee_overdue", alert=True, action="View demands", icon="rupee", headline=True,
		sub_fn=lambda c: _("₹{0} outstanding").format(frappe.utils.fmt_money(_aggregate("Fee Demand", DRILLDOWNS["fee_overdue"]["filters"](c, {}), "SUM", "outstanding_amount") or 0, precision=0))),
	# ── Venue Booking
	_card("venue_bookings_all", "venue", "Bookings in Date Range", "Venue bookings starting within the date range, any status.", "Venue Booking", "venues", _drill_count("venue_bookings_all"), drill="venue_bookings_all", compare=True, icon="building", action="View bookings", headline=True),
	_card("venue_bookings", "venue", "Allotted Bookings", "Allotted venue bookings starting within the date range.", "Venue Booking", "venues", _drill_count("venue_bookings"), drill="venue_bookings", icon="check", action="View bookings", headline=True),
	_card("venue_bookings_closed", "venue", "Rejected / Cancelled", "Venue bookings in the date range that were rejected or cancelled.", "Venue Booking", "venues", _drill_count("venue_bookings_closed"), drill="venue_bookings_closed", icon="x-circle", action="View bookings"),
	_card("venues_active", "venue", "Active Venues", "Venues available for booking.", "Venue Master", "all_time", _drill_count("venues_active"), drill="venues_active", icon="home", action="View venues"),
	_card("venue_pending", "venue", "Venue Requests Pending", "Venue booking requests awaiting allotment.", "Venue Booking", "all_time", _drill_count("venue_pending"), drill="venue_pending", alert=True, action="Review requests", icon="inbox", headline=True),
	_card("classes_no_venue", "venue", "Upcoming Classes Without a Venue", "Classes in the next 14 days that have no venue assigned.", "Time Table", "classes_nodate", _drill_count("classes_no_venue"), drill="classes_no_venue", alert=True, action="View classes", icon="building"),
	# ── PACE
	_card("pace_applications", "pace", "PACE Applications", "PACE applications for the selected academic year.", "PACE Application", "pace", _drill_count("pace_applications"), drill="pace_applications", icon="inbox", action="View applications", headline=True),
	_card("pace_in_progress", "pace", "In Progress", "PACE applications that are neither enrolled nor closed.", "PACE Application", "pace", _drill_count("pace_in_progress"), drill="pace_in_progress", icon="loader", headline=True),
	_card("pace_enrolled", "pace", "Enrolled", "PACE applicants at the enrolment stage.", "PACE Application", "pace", _drill_count("pace_enrolled"), drill="pace_enrolled", icon="user-check"),
	_card("pace_enquiries_new", "pace", "New Enquiries", "PACE enquiries not yet contacted.", "PACE Enquiry", "all_time", _drill_count("pace_enquiries_new"), drill="pace_enquiries_new", alert=True, action="View enquiries", icon="inbox"),
	_card("pace_verification_pending", "pace", "Document Verifications Pending", "PACE document verifications awaiting a verifier or a correction.", "PACE Document Verification", "pace", _drill_count("pace_verification_pending"), drill="pace_verification_pending", alert=True, action="Review", icon="file", headline=True),
	# ── FLE
	_card("fle_registrations", "fle", "FLE Registrations", "Foundations for a Legal Education registrations in the date range.", "Foundations for a Legal Education", "fle", _drill_count("fle_registrations"), drill="fle_registrations", compare=True, icon="scale", action="View registrations", headline=True),
	_card("fle_enrolled", "fle", "Enrolled", "FLE candidates enrolled, in progress or completed.", "Foundations for a Legal Education", "fle", _drill_count("fle_enrolled"), drill="fle_enrolled", icon="user-check", headline=True),
	_card("fle_collected", "fle", "FLE Fees Collected", "Amount paid on FLE registrations in the date range.", "Foundations for a Legal Education", "fle", _sum("Foundations for a Legal Education", f_fle, "paid_amount"), drill="fle_registrations", fmt="currency", icon="wallet"),
	_card("fle_unpaid", "fle", "Payment Not Captured", "FLE registrations whose payment has not been captured.", "Foundations for a Legal Education", "fle", _drill_count("fle_unpaid"), drill="fle_unpaid", alert=True, action="View registrations", icon="rupee", headline=True),
	_card("fle_lms_pending", "fle", "Paid, No LMS Account", "Paid FLE candidates whose LMS account has not been created.", "Foundations for a Legal Education", "fle", _drill_count("fle_lms_pending"), drill="fle_lms_pending", alert=True, action="View candidates", icon="user-x"),
	# ── Examinations
	_card("marks_all", "exams", "Course Marks Recorded", "Student course-marks entries for the selected term.", "Student Course Marks", "marks", _drill_count("marks_all"), drill="marks_all", icon="edit", headline=True),
	_card("results_published", "exams", "Results Published", "Student results published for the selected term.", "Student Result Publish", "results", _drill_count("results_published"), drill="results_published", icon="award", headline=True),
	_card("avg_gpa", "exams", "Average Term GPA", "Mean term GPA across published results.", "Student Result Publish", "results", _published_avg_gpa, drill="results_published", fmt="gpa", icon="activity"),
	_card("marks_draft", "exams", "Marks Still in Draft", "Course marks entries not yet submitted or locked.", "Student Course Marks", "marks", _drill_count("marks_draft"), drill="marks_draft", alert=True, action="View entries", icon="edit", headline=True),
	# ── All-time (home screen)
	_card("students_all_time", "all_time", "Students Ever Registered", "Every student record since inception.", "Student Master", "all_time", _drill_count("students_all_time"), drill="students_all_time", all_time=True, icon="users"),
	_card("graduated_all_time", "all_time", "Graduates & Alumni", "Students who have graduated since inception.", "Student Master", "all_time", _drill_count("graduated_all_time"), drill="graduated_all_time", all_time=True, icon="award"),
	_card("programmes_all_time", "all_time", "Programmes Created", "All programmes, active or not.", "Programme", "all_time", _drill_count("programmes_all_time"), drill="programmes_all_time", all_time=True, icon="graduation"),
	_card("courses_all_time", "all_time", "Courses Created", "All courses in the catalogue.", "Course", "all_time", _drill_count("courses_all_time"), drill="courses_all_time", all_time=True, icon="book"),
	_card("years_all_time", "all_time", "Academic Years", "Academic years configured.", "Academic Year", "all_time", _drill_count("years_all_time"), drill="years_all_time", all_time=True, icon="calendar"),
	_card("applications_all_time", "all_time", "Applications Received", "Every admission application since inception.", "Applicant", "all_time", _drill_count("applications_all_time"), drill="applications_all_time", all_time=True, icon="inbox"),
	_card("sessions_all_time", "all_time", "Sessions Conducted", "Every attendance session conducted.", "Attendance Session", "all_time", _drill_count("sessions_all_time"), drill="sessions_all_time", all_time=True, icon="check"),
	_card("results_all_time", "all_time", "Results Published", "Every published student result.", "Student Result Publish", "all_time", _drill_count("results_all_time"), drill="results_all_time", all_time=True, icon="award"),
]


def _run(fn, *args):
	"""Evaluate a metric; a permission gap or data error degrades to 'unavailable' without leaking details."""
	try:
		return fn(*args), None
	except frappe.PermissionError:
		return None, "restricted"
	except Exception:
		frappe.log_error(title="Uniquad Dashboard metric failed", message=frappe.get_traceback())
		return None, "error"


# ─────────────────────────────────────────────────────────────── charts


def _bucket_key(d, weekly):
	d = getdate(d)
	return d - datetime.timedelta(days=d.weekday()) if weekly else d


def _bucketed(rows, date_field, weight):
	"""Sum `weight` per week, or per day when the data spans fewer than three weeks."""
	dates = {getdate(r[date_field]) for r in rows if r.get(date_field)}
	weekly = len({_bucket_key(d, True) for d in dates}) >= 3

	def agg(subset):
		out = {}
		for r in subset:
			if r.get(date_field):
				k = _bucket_key(r[date_field], weekly)
				out[k] = out.get(k, 0) + weight(r)
		return out

	return weekly, agg


def _chart_attendance_trend(ctx):
	rows = frappe.get_list(
		"Student Attendance",
		filters=f_attendance(ctx),
		fields=["attendance_date", "status", {"COUNT": "*", "as": "v"}],
		group_by="attendance_date, status",
		order_by=None,
	)
	weekly, agg = _bucketed(rows, "attendance_date", lambda r: cint(r.v))
	total = agg(rows)
	present = agg([r for r in rows if r.status in PRESENT_STATUSES])
	keys = sorted(total)
	return {
		"granularity": "week" if weekly else "day",
		"labels": [frappe.utils.formatdate(k, "dd MMM") for k in keys],
		"values": [round(100.0 * present.get(k, 0) / total[k], 1) for k in keys],
		"counts": [total[k] for k in keys],
		"threshold": _threshold(),
	}


def _chart_classes_weekly(ctx):
	rows = _group("Time Table", f_classes(ctx), "schedule_date")
	weekly, agg = _bucketed(rows, "schedule_date", lambda r: cint(r.v))
	buckets = agg(rows)
	keys = sorted(buckets)
	return {
		"granularity": "week" if weekly else "day",
		"labels": [frappe.utils.formatdate(k, "dd MMM") for k in keys],
		"values": [buckets[k] for k in keys],
	}


def _bars(rows, field, labels=None, limit=10, empty_label="Not set", order=None):
	items = [{"key": r.get(field) or "", "label": (labels or {}).get(r.get(field)) or r.get(field) or empty_label, "value": cint(r.v)} for r in rows if cint(r.v)]
	if order:
		rank = {k: i for i, k in enumerate(order)}
		items.sort(key=lambda i: rank.get(i["key"], len(rank)))
	else:
		items.sort(key=lambda i: -i["value"])
	if len(items) > limit:
		other = sum(i["value"] for i in items[limit - 1 :])
		items = items[: limit - 1] + [{"key": None, "label": "Other", "value": other}]
	return items


def _chart_student_breakdowns(ctx):
	f = f_students(ctx)
	prog_labels = {p.name: p.program_name or p.name for p in frappe.get_all("Programme", fields=["name", "program_name"])}
	return {
		"students_by_status": _bars(_group("Student Master", f, "student_status"), "student_status"),
		"students_by_programme": _bars(_group("Student Master", f, "programme_of_study"), "programme_of_study", prog_labels),
		"students_by_stage": _bars(_group("Student Master", f, "registration_status"), "registration_status"),
		"students_by_gender": _bars(_group("Student Master", f, "gender"), "gender"),
	}


def _chart_course_attendance(ctx):
	rows = frappe.get_list(
		"Attendance Summary",
		filters=f_summary(ctx),
		fields=["course", {"AVG": "attendance_percentage", "as": "avg"}, {"COUNT": "*", "as": "n"}],
		group_by="course",
		order_by=None,
	)
	items = sorted(
		({"key": r.course, "label": r.course or "Not set", "value": round(flt(r.avg), 1), "count": cint(r.n)} for r in rows),
		key=lambda i: i["value"],
	)
	return {"items": items[:10], "threshold": _threshold()}


def _chart_application_stages(ctx):
	statuses = _applicant_status_map()
	rows = _group("Applicant", f_applicants(ctx), "status")
	stages = {}
	for r in rows:
		s = statuses.get(r.status)
		stage = (s.stage_type if s else None) or "Unclassified"
		stages[stage] = stages.get(stage, 0) + cint(r.v)
	return _bars([frappe._dict(stage=k, v=v) for k, v in stages.items()], "stage", order=APPLICATION_STAGE_ORDER + ("Unclassified",), limit=12)


def _chart_tickets(ctx):
	open_f = _open_tickets()
	range_f = f_tickets(ctx)
	# who raised them: label each email with the person's name only when the user can read that record
	raisers = _bars(_group("HD Ticket", range_f, "raised_by"), "raised_by", limit=10, empty_label="Unknown")
	emails = [i["key"] for i in raisers if i["key"]]
	names = {}
	for dt, fields, name_fields in (
		("Faculty", ["email", "official_email_id", "user_id"], ["first_name", "last_name"]),
		("Student Master", ["email", "official_email_id", "personal_email", "user"], ["first_name"]),
	):
		if not emails or not _can(dt):
			continue
		for r in frappe.get_list(dt, or_filters=[[f, "in", emails] for f in fields], fields=name_fields + fields, limit_page_length=0):
			name = " ".join(filter(None, (r.get(n) for n in name_fields)))
			names.update({r.get(f).strip().lower(): name for f in fields if r.get(f)})
	for i in raisers:
		if i["key"]:
			who = names.get(i["key"].strip().lower())
			i["sub"] = _requester_kind(i["key"])
			if who:
				i["label"] = f"{who} ({i['key']})"
	kinds = {}
	for r in _group("HD Ticket", range_f, "raised_by"):
		k = _requester_kind(r.raised_by)
		kinds[k] = kinds.get(k, 0) + cint(r.v)
	return {
		"open_total": frappe.get_list("HD Ticket", filters=open_f, fields=[{"COUNT": "*", "as": "v"}], order_by=None)[0].v or 0,
		"raised_total": frappe.get_list("HD Ticket", filters=range_f, fields=[{"COUNT": "*", "as": "v"}], order_by=None)[0].v or 0,
		"tickets_open_status": _bars(_group("HD Ticket", open_f, "status"), "status"),
		"tickets_open_team": _bars(_group("HD Ticket", open_f, "agent_group"), "agent_group", empty_label="Unassigned"),
		"tickets_raised_kind": _bars([frappe._dict(kind=k, v=v) for k, v in kinds.items()], "kind", order=REQUESTER_KINDS),
		"tickets_top_raisers": raisers,
		"tickets_by_type": _bars(_group("HD Ticket", range_f, "ticket_type"), "ticket_type", empty_label="Uncategorised"),
	}


def _chart_venue_decisions(ctx):
	f = _venue_range(ctx)
	rows = frappe.get_list("Venue Booking", filters=f, fields=["status", "requester_type", "replied_by", {"COUNT": "*", "as": "v"}], group_by="status, requester_type, replied_by", order_by=None)

	def split(field, empty_label):
		out = {}
		for r in rows:
			k = r.get(field) or ""
			e = out.setdefault(k, {"key": k, "label": r.get(field) or empty_label, "value": 0, "approved": 0, "rejected": 0, "pending": 0})
			e["value"] += cint(r.v)
			if r.status == "Allotted":
				e["approved"] += cint(r.v)
			elif r.status == "Rejected":
				e["rejected"] += cint(r.v)
			elif r.status == "Pending Allotment":
				e["pending"] += cint(r.v)
		return sorted(out.values(), key=lambda i: -i["value"])[:10]

	approvers = split("replied_by", "Not recorded")
	for a in approvers:
		a["value"] = a["approved"] + a["rejected"]  # an approver's bar is the decisions they made
	return {
		"venue_by_status": _bars(_group("Venue Booking", f, "status"), "status", order=("Pending Allotment", "Allotted", "Rejected", "Cancelled")),
		"venue_by_requester": split("requester_type", "Not set"),
		"venue_by_approver": sorted((a for a in approvers if a["value"]), key=lambda a: -a["value"]),
		"venue_swaps": _bars(_group("Venue Booking", f + [["swap_status", "is", "set"]], "swap_status"), "swap_status", order=("Pending", "Approved", "Rejected")),
	}


CHARTS = [
	("attendance_trend", "Student Attendance", _chart_attendance_trend),
	("tickets", "HD Ticket", _chart_tickets),
	("venue_decisions", "Venue Booking", _chart_venue_decisions),
	("classes_weekly", "Time Table", _chart_classes_weekly),
	("student_breakdowns", "Student Master", _chart_student_breakdowns),
	("course_attendance", "Attendance Summary", _chart_course_attendance),
	("application_stages", "Applicant", _chart_application_stages),
]


# ─────────────────────────────────────────────────────────────── endpoints


# ─────────────────────────────────────────────────────────────── module navigation
# Grouped from the SLCM / Admission / PACE modules actually installed. Entries are (type, name, label).
# get_navigation() drops anything that does not exist or that the current user cannot open, so the
# sidebar never advertises a module the user has no access to.

NAV_GROUPS = [
	("admission", "Admission", "inbox", [
		("DocType", "Applicant", None), ("DocType", "Admission Cycle", None), ("DocType", "Admission Application", None),
		("DocType", "Entrance Test", None), ("DocType", "Interview List", None), ("DocType", "Merit List", None),
		("DocType", "Seat Allocation", None), ("DocType", "Offer Letter", None), ("DocType", "Scholarship Application", None),
		("Page", "admission-flow-dashboard", "Admission Flow Dashboard"), ("Page", "seat-matrix-dashboard", "Seat Matrix Dashboard"),
		("Report", "Admission Funnel Report", None), ("Report", "Application Trends", None),
	]),
	("registration", "Student Registration", "user-check", [
		("DocType", "Student Master", None), ("DocType", "Student Enrollment", None), ("DocType", "Student Leave Applications", None),
		("DocType", "Student Promotion", None), ("DocType", "Promotion Policy", None), ("Page", "promotion-management", "Promotion Management"),
		("DocType", "Student Announcement", None), ("DocType", "Discipline Order", None), ("DocType", "Convocation Registration", None),
	]),
	("programme", "Programme Management", "graduation", [
		("DocType", "Academic Year", None), ("DocType", "Academic Term", None), ("DocType", "Programme", None),
		("DocType", "Programme Master", None), ("DocType", "Batch", None), ("DocType", "Section", None),
		("DocType", "Course", None), ("DocType", "Course Offering", None), ("DocType", "Course List", None),
		("DocType", "Faculty", None), ("DocType", "Time Table", None), ("DocType", "Course Schedule", None),
		("Page", "timetable-configuration", "Timetable Configuration"), ("DocType", "Institutional Calendar", None),
		("Page", "academic-management", "Academic Management"),
	]),
	("attendance", "Attendance", "check", [
		("DocType", "Attendance Session", None), ("DocType", "Student Attendance", None), ("DocType", "Attendance Summary", None),
		("DocType", "Attendance Log", None), ("DocType", "Student Attendance Condonation", None), ("DocType", "FA MFA Application", None),
		("Page", "student-attendance-tool", "Student Attendance Tool"), ("Page", "attendance-quick-view", "Attendance Quick View"),
		("Page", "attendance-sync", "Attendance Sync"), ("Page", "rfid-mapping", "RFID Mapping"),
		("Report", "Comprehensive Attendance Report", None), ("Report", "Daily Absentees", None),
		("Report", "Consecutive Absents", None), ("Report", "RFID Attendance Report", None),
	]),
	("idcard", "ID Card", "card", [
		("DocType", "ID Card Generation", None), ("DocType", "ID Card Generation Tool", "ID Card Generation Tool"),
		("DocType", "Student ID Card", None), ("DocType", "ID Card Template", None), ("DocType", "ID Card Print Log", None),
		("DocType", "Student RFID Card", None), ("DocType", "RFID Device", None),
	]),
	("fees", "Fees", "rupee", [
		("Page", "student-fee-management", "Student Fee Management"),
		("DocType", "Fee Demand", None), ("DocType", "Fee Payment", None), ("DocType", "Fee Receipt", None),
		("DocType", "Fee Concession", None), ("DocType", "Fee Refund", None), ("DocType", "Fee Structure", None),
		("DocType", "Student Credit Note", None), ("DocType", "University Financial Aid", None),
		("DocType", "Fee Certificate Request", None), ("Page", "fee-reminder-tool", "Fee Reminder Tool"),
		("Report", "Fee Demand Register", None), ("Report", "Defaulter List", None), ("Report", "Collection Summary", None),
	]),
	("venue", "Venue Booking", "building", [
		("DocType", "Venue Booking", None), ("DocType", "Venue Master", None), ("DocType", "Venue Type", None),
		("DocType", "Building", None), ("DocType", "Room", None),
		("Report", "Weekly Venue Booking Report", None), ("Report", "Monthly Venue Booking Report", None), ("Report", "Room Availability Checker", None),
	]),
	("pace", "PACE", "layers", [
		("DocType", "PACE Enquiry", None), ("DocType", "PACE Application", None), ("DocType", "PACE Document Verification", None),
		("DocType", "PACE Admission", None), ("DocType", "PACE Programme", None), ("DocType", "PACE Receipt", None),
	]),
	("fle", "FLE", "scale", [
		("DocType", "Foundations for a Legal Education", None), ("DocType", "FLE Payment Log", None),
		("Report", "FLE Applications Report", None), ("Report", "FLE Settlement Report", None),
	]),
	("exams", "Examinations", "award", [
		("Page", "examination-planner", "Examination Planner"), ("DocType", "Exam Plan", None),
		("DocType", "Student Course Marks", None), ("DocType", "Student Result Publish", None),
		("Page", "examination-result", "Examination Result"), ("Page", "publish-result", "Publish Result"),
		("DocType", "Re Exam Registration", None), ("DocType", "Revaluation Request", None),
		("DocType", "Student Transcript", None), ("DocType", "Transcript Request", None),
		("Report", "Academic Performance GPA Report", None),
	]),
]


def _page_allowed(name, roles):
	page_roles = frappe.get_all("Has Role", filters={"parent": name, "parenttype": "Page"}, pluck="role")
	return not page_roles or bool(set(page_roles) & roles) or "System Manager" in roles


def _report_route(name):
	r = frappe.db.get_value("Report", name, ["report_type", "ref_doctype", "disabled"], as_dict=True)
	if not r or r.disabled:
		return None
	if r.ref_doctype and not _can(r.ref_doctype):
		return None
	if r.report_type in ("Query Report", "Script Report"):
		return f"/desk/query-report/{name}"
	return f"/desk/{frappe.scrub(r.ref_doctype or '').replace('_', '-')}/view/report/{name}" if r.ref_doctype else None


@frappe.whitelist()
def get_navigation():
	"""Module menu for the sidebar, filtered to what the caller can actually open."""
	_check_access()
	roles = set(frappe.get_roles())
	groups = []
	for key, label, icon, entries in NAV_GROUPS:
		items = []
		for kind, name, item_label in entries:
			route = None
			if kind == "DocType":
				if frappe.db.exists("DocType", name) and _can(name):
					slug = frappe.scrub(name).replace("_", "-")
					route = f"/desk/{slug}" + ("" if frappe.get_meta(name).issingle else "")
			elif kind == "Page":
				if frappe.db.exists("Page", name) and _page_allowed(name, roles):
					route = f"/desk/{name}"
			elif kind == "Report":
				if frappe.db.exists("Report", name):
					route = _report_route(name)
			if route:
				items.append({"label": _(item_label or name), "type": kind, "route": route, "name": name, "single": kind == "DocType" and bool(frappe.get_meta(name).issingle)})
		if items:
			groups.append({"key": key, "label": _(label), "icon": icon, "items": items})
	return groups


# ─────────────────────────────────────────────────────────────── global search

SEARCH_SOURCES = [
	# doctype, fields searched, label field, extra fields for the subtitle, result kind
	("Student Master", ["name", "first_name", "registration_id", "email"], "first_name", ["programme_of_study", "batch", "student_status"], "student"),
	("Applicant", ["name", "candidate_name", "applicant_id", "email"], "candidate_name", ["program", "status"], "record"),
	("Faculty", ["faculty_id", "first_name", "last_name", "email"], "first_name", ["designation", "status"], "record"),
	("Course", ["name", "course_name", "course_code"], "course_name", ["course_code", "status"], "record"),
	("Programme", ["name", "program_name", "program_code"], "program_name", ["level_of_study", "program_status"], "record"),
	("Venue Booking", ["name", "event_name", "venue"], "event_name", ["venue", "status"], "record"),
	("Fee Demand", ["name", "student_name", "student"], "student_name", ["fee_component", "status"], "record"),
]


@frappe.whitelist()
def global_search(q):
	"""Quick find across key SLCM records. Each source is a permission-checked get_list (max 5 hits)."""
	_check_access()
	q = _clean_text(q, 60)
	if len(q) < 2:
		return []
	out = []
	for doctype, fields, label, extra, kind in SEARCH_SOURCES:
		meta = frappe.get_meta(doctype) if frappe.db.exists("DocType", doctype) else None
		if not meta:
			continue
		fields = [f for f in fields if f == "name" or (meta.get_field(f) and not meta.get_field(f).permlevel)]
		extra = [f for f in extra if meta.get_field(f) and not meta.get_field(f).permlevel]
		rows = _safe_rows(doctype, or_filters=[[f, "like", f"%{q}%"] for f in fields], fields=list(dict.fromkeys(["name", label, *extra])), order_by="modified desc", limit=5)
		for r in rows:
			out.append({
				"doctype": doctype,
				"doctype_label": _(doctype),
				"name": str(r.name),
				"label": str(r.get(label) or r.name),
				"sub": " · ".join(str(r.get(f)) for f in extra if r.get(f)),
				"kind": kind,
			})
	return out


@frappe.whitelist()
def get_filter_options():
	"""Filter options (permission-scoped) with the parent keys the client needs for cascading,
	plus sensible defaults: the current academic year, current term, and that term's date range."""
	_check_access()
	today = getdate(nowdate())

	def safe_list(doctype, **kw):
		return frappe.get_list(doctype, **kw) if _can(doctype) else []

	years = safe_list("Academic Year", fields=["name", "status", "year_start_date", "year_end_date"], order_by="year_start_date desc")
	terms = safe_list("Academic Term", fields=["name", "academic_year", "status", "term_start_date", "term_end_date"], order_by="term_start_date desc")
	programmes = safe_list("Programme", fields=["name", "program_name", "academic_year", "program_status"], order_by="name asc")
	batches = safe_list("Batch", fields=["name", "program", "academic_year", "status"], order_by="name asc")
	sections = safe_list("Section", fields=["name", "batch", "section_name"], order_by="name asc")
	courses = safe_list("Course", fields=["name", "course_name", "course_code", "status"], order_by="course_name asc")
	faculty = safe_list("Faculty", fields=["name", "first_name", "last_name", "status"], order_by="first_name asc")

	# course → programmes / batches / terms it is offered in, so Course can cascade from those filters.
	course_links = {}
	if _can("Course Offering"):
		for o in frappe.get_list("Course Offering", fields=["course_title", "program", "cohort", "term_name", "academic_year", "faculty"]):
			link = course_links.setdefault(o.course_title, {"programme": set(), "batch": set(), "academic_term": set(), "academic_year": set(), "faculty": set()})
			for key, val in (("programme", o.program), ("batch", o.cohort), ("academic_term", o.term_name), ("academic_year", o.academic_year), ("faculty", o.faculty)):
				if val not in (None, ""):
					link[key].add(str(val))

	def pick_current(rows, start, end, status_field="status"):
		current = [r for r in rows if r.get(start) and r.get(end) and getdate(r[start]) <= today <= getdate(r[end])]
		active = [r for r in current if r.get(status_field) != "Inactive"] or current
		return sorted(active, key=lambda r: getdate(r[start]), reverse=True)[0] if active else None

	cur_year = pick_current(years, "year_start_date", "year_end_date") or (years[0] if years else None)
	year_terms = [t for t in terms if not cur_year or t.academic_year == cur_year.name]
	cur_term = pick_current(year_terms, "term_start_date", "term_end_date")
	if cur_term:
		from_date, to_date = cur_term.term_start_date, cur_term.term_end_date
	else:
		from_date, to_date = get_first_day(today), get_last_day(today)

	status_field = frappe.get_meta("Student Master").get_field("student_status")
	return {
		"academic_year": [{"value": y.name, "label": y.name} for y in years],
		"academic_term": [
			{"value": t.name, "label": t.name, "academic_year": t.academic_year, "start": str(t.term_start_date or ""), "end": str(t.term_end_date or "")}
			for t in terms
		],
		"programme": [
			{"value": p.name, "label": p.program_name if p.program_name and p.program_name != p.name else p.name, "hint": p.name if p.program_name and p.program_name != p.name else "", "academic_year": p.academic_year}
			for p in programmes
		],
		"batch": [{"value": b.name, "label": b.name, "programme": b.program, "academic_year": b.academic_year} for b in batches],
		"section": [{"value": s.name, "label": s.name, "batch": s.batch} for s in sections],
		"course": [
			{"value": c.name, "label": c.course_name or c.name, "hint": c.course_code or "", **{k: sorted(v) for k, v in course_links.get(c.name, {}).items()}}
			for c in courses
		],
		"faculty": [
			{"value": str(f.name), "label": " ".join(filter(None, [f.first_name, f.last_name])) or str(f.name)}
			for f in faculty
		],
		"student_status": [{"value": s, "label": s} for s in (status_field.options or "").split("\n") if s] if status_field else [],
		"gender": [{"value": g, "label": g} for g in frappe.get_all("Genders", pluck="name", order_by="name asc")],
		"defaults": {
			"academic_year": [cur_year.name] if cur_year else [],
			"academic_term": [cur_term.name] if cur_term else [],
			"from_date": str(from_date),
			"to_date": str(to_date),
		},
		"current_term": cur_term.name if cur_term else None,
	}


@frappe.whitelist()
def get_dashboard(filters=None):
	"""All cards and charts in one round-trip. Each metric is computed with permission-checked queries;
	cards on doctypes the user cannot read come back flagged `restricted` with no value."""
	_check_access()
	ctx = Ctx(filters)
	all_time_ctx = Ctx({})

	cards = []
	for card in CARDS:
		out = {k: card[k] for k in ("key", "section", "title", "description", "doctype", "drill", "fmt", "tone", "action", "alert", "all_time", "icon", "headline")}
		out["applies"] = SCOPE[card["scope"]]
		if not _can(card["doctype"]):
			out.update(restricted=True, value=None)
		else:
			use = all_time_ctx if card["all_time"] else ctx
			value, err = _run(card["value_fn"], use)
			out.update(value=value, restricted=err == "restricted", error=err == "error")
			if card["sub_fn"] and not err:
				out["sub"], _e = _run(card["sub_fn"], use)
			if card["compare"] and not err and ctx.from_date and ctx.to_date:
				# same-length window immediately before the selected one
				span = (ctx.to_date - ctx.from_date).days + 1
				prev = Ctx(filters)
				prev.from_date, prev.to_date = add_days(ctx.from_date, -span), add_days(ctx.from_date, -1)
				pv, perr = _run(card["value_fn"], prev)
				if not perr and pv is not None:
					out["previous"] = pv
					out["previous_label"] = _("{0} – {1}").format(frappe.utils.formatdate(prev.from_date), frappe.utils.formatdate(prev.to_date))
		cards.append(out)

	charts = {}
	for key, doctype, fn in CHARTS:
		if not _can(doctype):
			charts[key] = {"restricted": True}
			continue
		data, err = _run(fn, ctx)
		charts[key] = data if not err else {"restricted": err == "restricted", "error": err == "error"}

	return {
		"cards": cards,
		"charts": charts,
		"threshold": _threshold(),
		"can_fees": _can("Fee Demand"),
		"generated_at": str(now_datetime()),
		"today": nowdate(),
	}


def _validate_params(spec, params):
	params = frappe.parse_json(params) if isinstance(params, str) else (params or {})
	if not isinstance(params, dict):
		params = {}
	out = {"_filters": params.get("_filters") if isinstance(params.get("_filters"), dict) else {}}
	for name, rule in spec["params"].items():
		value = params.get(name)
		if isinstance(rule, tuple):
			out[name] = value if value in rule else rule[0]
		elif rule == "optional":
			out[name] = _clean_text(value, MAX_VALUE_LENGTH) if isinstance(value, str) else ""
		else:
			value = _clean_text(value, MAX_VALUE_LENGTH)
			if not value:
				frappe.throw(_("Missing parameter: {0}").format(name))
			out[name] = value
	return out


# ─────────────────────────────────────────────────────────────── sidebar list previews ("dt:<DocType>")
# A sub-menu click opens a preview of that list before navigating. Only DocTypes listed in NAV_GROUPS
# are accepted (never an arbitrary doctype), rows come from frappe.get_list, and columns are the
# doctype's own list-view fields at permlevel 0.

_PREVIEW_SKIP = {"Table", "Table MultiSelect", "HTML", "Button", "Code", "Text Editor", "Long Text", "Text", "Small Text", "Attach", "Attach Image", "Image", "Signature", "Password", "JSON", "Geolocation", "Section Break", "Column Break", "Tab Break", "Fold", "Heading"}
_STATUS_FIELDS = ("status", "workflow_state", "registration_status", "card_status", "final_status", "session_status", "enrollment_status", "program_status", "student_status", "payment_status", "application_fee_status")


def _nav_doctypes():
	return {name for _k, _l, _i, entries in NAV_GROUPS for kind, name, _lab in entries if kind == "DocType"}


def _preview_status_field(meta):
	for f in _STATUS_FIELDS:
		df = meta.get_field(f)
		if df and df.fieldtype in ("Select", "Data", "Link") and not df.permlevel:
			return f
	return None


def _kind_for(df):
	if df.fieldtype == "Link" and df.options == "Student Master":
		return "student"
	return {"Date": "date", "Datetime": "datetime", "Currency": "currency", "Int": "int", "Float": "float", "Percent": "pct", "Check": "int", "Time": "time"}.get(df.fieldtype, "badge" if df.fieldname in _STATUS_FIELDS else "text")


def _preview_spec(doctype):
	if doctype not in _nav_doctypes() or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("Unknown drilldown."))
	meta = frappe.get_meta(doctype)
	if meta.issingle or meta.istable:
		frappe.throw(_("This item has no list to preview."))
	cols = [("name", _("ID"), "form", True)]
	seen = {"name"}
	title = meta.title_field if meta.title_field and meta.get_field(meta.title_field) else None
	picked = ([meta.get_field(title)] if title else []) + [df for df in meta.fields if df.in_list_view] + [df for df in meta.fields if df.in_standard_filter]
	status = _preview_status_field(meta)
	if status:
		picked.append(meta.get_field(status))
	for df in picked:
		if not df or df.fieldname in seen or df.fieldtype in _PREVIEW_SKIP or df.permlevel or df.hidden:
			continue
		# the project has no Department module — never surface it, even where a doctype still carries the field
		if df.fieldname == "department" or df.options == "Department":
			continue
		cols.append((df.fieldname, _(df.label or df.fieldname), _kind_for(df), True))
		seen.add(df.fieldname)
		if len(cols) >= 8:
			break
	cols.append(("modified", _("Updated On"), "datetime", True))
	search = ["name"] + [f for f in [title] + (meta.search_fields or "").replace(" ", "").split(",") if f and meta.get_field(f) and not meta.get_field(f).permlevel][:3]

	def filters(ctx, p):
		f = []
		if p.get("status") and status:
			f.append([status, "=", p["status"]])
		if p.get("recent") == "range":
			f += _date_range_on(Ctx(p.get("_filters") or {}), "creation", True)
		return f

	spec = _drill(_(doctype), doctype, cols, filters, list(dict.fromkeys(search)), ("modified", "desc"), "all_time", all_time=True, description=_("All {0} records your role can access.").format(_(doctype)))
	spec["params"] = {"status": "optional", "recent": ("", "range")}
	return spec


@frappe.whitelist()
def get_list_preview(doctype, filters=None):
	"""Header facts for a list preview: total, created in the date range, updated this week, status mix."""
	_check_access()
	doctype = _clean_text(doctype, MAX_VALUE_LENGTH)
	spec = _preview_spec(doctype)
	if not _can(doctype):
		return {"restricted": True}
	ctx = Ctx(filters)
	meta = frappe.get_meta(doctype)
	status = _preview_status_field(meta)
	out = {
		"doctype": doctype,
		"title": _(doctype),
		"description": meta.description or "",
		"total": _count(doctype, []),
		"created_in_range": _count(doctype, _date_range_on(ctx, "creation", True)) if (ctx.from_date or ctx.to_date) else None,
		"updated_week": _count(doctype, [["modified", ">=", add_days(nowdate(), -7)]]),
		"status_field": status,
		"status_label": _(meta.get_field(status).label) if status else None,
		"statuses": [],
		"route": "/desk/" + frappe.scrub(doctype).replace("_", "-"),
	}
	if status:
		rows = _group(doctype, [], status)
		out["statuses"] = sorted(({"value": r.get(status) or "", "count": cint(r.v)} for r in rows), key=lambda x: -x["count"])[:8]
	return out


@frappe.whitelist()
def get_item_preview(kind, name):
	"""Preview for a sidebar Tool (Page) or Report: what it is, and the list it is built on."""
	_check_access()
	name = _clean_text(name, MAX_VALUE_LENGTH)
	allowed = {(k, n) for _k, _l, _i, entries in NAV_GROUPS for k, n, _lab in entries}
	if (kind, name) not in allowed:
		frappe.throw(_("Unknown item."))
	if kind == "Page":
		doc = frappe.db.get_value("Page", name, ["title", "module"], as_dict=True) or {}
		if not _page_allowed(name, set(frappe.get_roles())):
			return {"restricted": True}
		return {"kind": "Page", "title": doc.get("title") or name, "module": doc.get("module"), "route": f"/desk/{name}", "ref_doctype": None}
	r = frappe.db.get_value("Report", name, ["report_type", "ref_doctype", "module"], as_dict=True) or {}
	route = _report_route(name)
	if not route:
		return {"restricted": True}
	ref = r.get("ref_doctype") if r.get("ref_doctype") in _nav_doctypes() and _can(r.get("ref_doctype")) else None
	return {"kind": "Report", "title": name, "module": r.get("module"), "report_type": r.get("report_type"), "route": route, "ref_doctype": ref,
		"ref_total": _count(ref, []) if ref else None}


def _query_drill(key, filters, params, search, sort_by, sort_order, offset, limit):
	if isinstance(key, str) and key.startswith("dt:"):
		spec = _preview_spec(key[3:])
		pdict = frappe.parse_json(params) if isinstance(params, str) else (params or {})
		pdict = pdict if isinstance(pdict, dict) else {}
		pdict["_filters"] = frappe.parse_json(filters) if isinstance(filters, str) and filters else (filters or {})
		params = pdict
	else:
		spec = DRILLDOWNS.get(key)
	if not spec:
		frappe.throw(_("Unknown drilldown."))
	doctype = spec["doctype"]
	if doctype and not _can(doctype):
		raise frappe.PermissionError(_("You do not have access to {0}.").format(_(doctype)))

	ctx = Ctx({}) if spec["all_time"] else Ctx(filters)
	p = _validate_params(spec, params)
	search = _clean_text(search)
	sortable = {c[0] for c in spec["columns"] if c[3]}
	field, direction = spec["sort"]
	if sort_by in sortable:
		field = sort_by
		direction = "asc" if sort_order == "asc" else "desc"

	if spec["virtual"]:
		# Multi-source list: every source inside is itself a permission-checked get_list.
		rows = spec["virtual"](ctx, p)
		if search:
			q = search.lower()
			rows = [r for r in rows if any(q in str(r.get(f) or "").lower() for f in spec["search"])]
		present = [r for r in rows if r.get(field) not in (None, "")]
		blank = [r for r in rows if r.get(field) in (None, "")]
		present.sort(key=lambda r: _sort_key(r.get(field)), reverse=direction == "desc")
		rows = present + blank
		return spec, len(rows), rows[offset : offset + limit] if limit else rows, field, direction

	query_filters = spec["filters"](ctx, p)
	or_filters = [[f, "like", f"%{search}%"] for f in spec["search"]] if search else None

	db_fields = ["name"] + [c[0] for c in spec["columns"] if c[3] or frappe.get_meta(doctype).has_field(c[0])] + spec["extra_fields"]
	db_fields = [f for f in dict.fromkeys(db_fields) if f in ("name", "creation", "modified") or frappe.get_meta(doctype).has_field(f)]

	total_rows = frappe.get_list(doctype, filters=query_filters, or_filters=or_filters, fields=[{"COUNT": "*", "as": "n"}], order_by=None)
	total = cint(total_rows[0].n) if total_rows else 0
	rows = frappe.get_list(
		doctype,
		filters=query_filters,
		or_filters=or_filters,
		fields=db_fields,
		order_by=f"{field} {direction}, name asc",
		offset=offset,
		limit=limit,
	)
	if spec["post"] and rows:
		rows = spec["post"](rows)
	return spec, total, rows, field, direction


def _sort_key(value):
	if isinstance(value, datetime.datetime):
		return (0, value)
	if isinstance(value, datetime.date):
		return (0, datetime.datetime.combine(value, datetime.time()))
	if isinstance(value, (int, float)):
		return (1, value)
	return (2, str(value).lower())


def _serialize(value):
	if isinstance(value, datetime.timedelta):
		seconds = int(value.total_seconds())
		return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"
	if isinstance(value, (datetime.date, datetime.datetime)):
		return str(value)
	return value


@frappe.whitelist()
def get_drilldown(key, filters=None, params=None, search=None, sort_by=None, sort_order=None, page=1, page_size=10):
	_check_access()
	page_size = cint(page_size) if cint(page_size) in PAGE_SIZES else 10
	page = max(cint(page), 1)
	try:
		spec, total, rows, field, direction = _query_drill(key, filters, params, search, sort_by, sort_order, (page - 1) * page_size, page_size)
	except frappe.PermissionError:
		frappe.clear_messages()
		return {"restricted": True}
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.log_error(title="Uniquad Dashboard drilldown failed", message=frappe.get_traceback())
		return {"error": True}
	columns = [{"field": c[0], "label": _(c[1]), "kind": c[2], "sortable": c[3]} for c in spec["columns"]]
	keep = {c[0] for c in spec["columns"]} | {"name", "ref_doctype"}
	return {
		"title": _(spec["title"]),
		"description": _(spec["description"]) if spec["description"] else "",
		"doctype": spec["doctype"] or "",
		"all_time": spec["all_time"],
		"applies": SCOPE[spec["scope"]],
		"columns": columns,
		"rows": [{k: _serialize(v) for k, v in r.items() if k in keep} for r in rows],
		"total": total,
		"page": page,
		"page_size": page_size,
		"sort_by": field,
		"sort_order": direction,
	}


def _csv_safe(value):
	value = _serialize(value)
	if value is None:
		return ""
	value = str(value)
	# Neutralise spreadsheet formula injection.
	return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@frappe.whitelist(methods=["POST"])
def export_drilldown(key, filters=None, params=None, search=None, sort_by=None, sort_order=None):
	"""CSV of the same permission-scoped query the drilldown shows, capped at EXPORT_LIMIT rows."""
	_check_access()
	spec, total, rows, _f, _d = _query_drill(key, filters, params, search, sort_by, sort_order, 0, EXPORT_LIMIT)
	buf = io.StringIO()
	writer = csv.writer(buf)
	writer.writerow([_(c[1]) for c in spec["columns"]])
	for r in rows:
		writer.writerow([_csv_safe(r.get(c[0])) for c in spec["columns"]])
	if total > EXPORT_LIMIT:
		writer.writerow([_("Export truncated to the first {0} of {1} rows. Narrow the filters to export the rest.").format(EXPORT_LIMIT, total)])
	frappe.response["filename"] = f"uniquad-{frappe.scrub(key.replace(':', '-'))}-{nowdate()}.csv"
	frappe.response["filecontent"] = "﻿" + buf.getvalue()
	frappe.response["type"] = "download"


@frappe.whitelist()
def get_student_profile(student):
	"""Profile for one student. The student must be inside the caller's Student Master list scope —
	the same rule the Student list applies — otherwise the response is identical to 'not found'."""
	_check_access()
	student = _clean_text(student, MAX_VALUE_LENGTH)
	# Unknown and unauthorised IDs get the same answer, so the endpoint cannot be used to probe IDs.
	denied = {"denied": True}
	if not student or not _can("Student Master"):
		return denied
	rows = frappe.get_list(
		"Student Master",
		filters={"name": student},
		fields=[
			"name", "first_name", "registration_id", "programme_of_study", "batch", "section", "academic_year",
			"academic_term", "current_year", "student_status", "academic_status", "registration_status", "admission_type",
			"gender", "email", "official_email_id", "phone", "date_of_registration", "id_card_issued", "cumulative_percentage",
			"modified",
		],
		limit=1,
	)
	if not rows or not frappe.has_permission("Student Master", "read", doc=student):
		return denied
	profile = rows[0]
	if profile.programme_of_study:
		profile["programme_name"] = frappe.db.get_value("Programme", profile.programme_of_study, "program_name")

	def block(doctype, **kw):
		if not _can(doctype):
			return {"restricted": True}
		try:
			return {"rows": [{k: _serialize(v) for k, v in r.items()} for r in frappe.get_list(doctype, **kw)]}
		except frappe.PermissionError:
			return {"restricted": True}

	attendance = block(
		"Attendance Summary",
		filters={"student": student},
		fields=["course", "course_offering", "academic_year", "term_name", "attendance_percentage", "minimum_required_percentage", "total_class_hours", "attended_classes", "eligible_for_exam", "last_updated"],
		order_by="attendance_percentage asc",
	)
	sessions = block(
		"Student Attendance",
		filters={"student": student},
		fields=["name", "attendance_date", "course", "status", "source", "attendance_session"],
		order_by="attendance_date desc",
		limit=50,
	)
	status_counts = {}
	for r in sessions.get("rows", []):
		status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

	enrollments = block(
		"Student Enrollment",
		filters={"student": student},
		fields=["name", "program", "batch", "section", "academic_year", "term_name", "status", "enrollment_date"],
		order_by="enrollment_date desc",
	)
	if enrollments.get("rows"):
		courses = block(
			"Student Enrollment Course",
			filters={"parent": ["in", [e["name"] for e in enrollments["rows"]]], "parenttype": "Student Enrollment"},
			fields=["parent", "course", "course_offering", "course_type", "credits", "status", "grade"],
			parent_doctype="Student Enrollment",
		)
		by_parent = {}
		for c in courses.get("rows", []):
			by_parent.setdefault(c["parent"], []).append(c)
		for e in enrollments["rows"]:
			e["courses"] = by_parent.get(e["name"], [])

	return {
		"profile": {k: _serialize(v) for k, v in profile.items()},
		"attendance": attendance,
		"sessions": sessions,
		"session_status_counts": status_counts,
		"enrollments": enrollments,
		"marks": block(
			"Student Course Marks",
			filters={"student": student},
			fields=["course", "exam_plan", "total_marks", "grade", "status", "attendance_status", "modified"],
			order_by="modified desc",
		),
		"results": block(
			"Student Result Publish",
			filters={"student": student, "is_published": 1},
			fields=["exam_plan", "term_gpa", "cumulative_gpa", "term_percentage", "cumulative_percentage", "published_on"],
			order_by="published_on desc",
		),
		"condonations": block(
			"Student Attendance Condonation",
			filters={"student": student, "docstatus": ["<", 2]},
			fields=["name", "course", "absence_from_date", "absence_to_date", "number_of_hours", "final_status"],
			order_by="creation desc",
		),
		"fees": block(
			"Fee Demand",
			filters={"student": student, "status": ["!=", "Cancelled"]},
			fields=["name", "fee_component", "net_payable", "paid_amount", "outstanding_amount", "due_date", "status"],
			order_by="due_date asc",
		),
		"can_open_form": True,
	}
