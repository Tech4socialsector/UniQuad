# Attendance Dashboard: count cards for sessions, marks, RFID swipes and approvals,
# for a chosen period. Each card names the list it opens (doctype + filters).
# Counts go through DatabaseQuery, so DocPerm, User Permissions and SLCM's
# permission_query_conditions apply; a doctype the user can't read is left out.

import frappe
from frappe import _
from frappe.model.db_query import DatabaseQuery
from frappe.utils import add_days, getdate, today

MATCHED = ["Matched", "Manually Synced"]


def _count(doctype, filters=None):
	if not frappe.has_permission(doctype, "read"):
		return None
	sql = DatabaseQuery(doctype).execute(fields=[f"`tab{doctype}`.name"], filters=filters or {}, run=0)
	return frappe.db.sql(f"select count(*) from ({sql}) t")[0][0]


def _card(label, doctype, filters=None, hint=""):
	value = _count(doctype, filters)
	if value is None:
		return None
	return {"label": label, "hint": hint, "doctype": doctype, "filters": filters or {}, "value": value}


def _group(title, cards, note=""):
	cards = [c for c in cards if c]
	return {"title": title, "note": note, "cards": cards} if cards else None


def current_term():
	d = today()
	return frappe.db.get_value(
		"Academic Term",
		{"term_start_date": ["<=", d], "term_end_date": [">=", d]},
		["name", "term_start_date", "term_end_date"],
		as_dict=True,
		order_by="term_start_date desc",
	)


def period_range(period, term=None, from_date=None, to_date=None):
	"""(from, to, label) for a period key; from/to are None for all time.
	"This term" uses the chosen trimester's dates, or the current term's.
	"custom" uses from_date..to_date (swapped if reversed)."""
	d = getdate(today())
	if period == "custom":
		if not (from_date and to_date):
			frappe.throw(_("Pick both a From and a To date for a custom range."))
		start, end = sorted([getdate(from_date), getdate(to_date)])
		return start, end, _("Custom range")
	if period == "today":
		return d, d, _("Today")
	if period == "7d":
		return add_days(d, -6), d, _("Last 7 days")
	if period == "30d":
		return add_days(d, -29), d, _("Last 30 days")
	if period == "term":
		t = frappe.db.get_value("Academic Term", term, ["name", "term_start_date", "term_end_date"], as_dict=True) if term else current_term()
		if t and t.term_start_date and t.term_end_date:
			return getdate(t.term_start_date), getdate(t.term_end_date), t.name
		return add_days(d, -29), d, _("Last 30 days (no current term)")
	return None, None, _("All time")


def _dated(field, start, end, is_datetime=False, **extra):
	f = dict(extra)
	if start:
		f[field] = ["between", [str(start), f"{end} 23:59:59" if is_datetime else str(end)]]
	return f


def _scope(programme=None, academic_term=None, class_name=None):
	"""Classes in scope of the filters, or None when nothing is filtered.
	Only used to narrow the counts below, which are permission-checked themselves."""
	if not (programme or academic_term or class_name):
		return None
	f = {}
	if programme:
		f["programme"] = programme
	if academic_term:
		f["academic_term"] = academic_term
	if class_name:
		f["name"] = class_name
	return frappe.get_all("Classes", filters=f, pluck="name") or ["__none__"]


# Drill-down: how a card's records split up. doctype -> (group by, split columns by, group label)
DRILL = {
	"Attendance Session": ("class_name", "session_status", ("Class", "classes")),
	"Student Attendance": ("class_name", "status", ("Class", "classes")),
	"Student Attendance Condonation": ("class_name", "final_status", ("Class", "classes")),
	"Attendance Summary": ("class_name", "eligible_for_exam", ("Class", "classes")),
	"FA MFA Application": ("course", "status", ("Course", "courses")),
	"RFID SQL Punch Log": ("terminal_alias", "sync_status", ("Terminal", "terminals")),
	"Attendance Log": ("terminal_alias", "match_status", ("Terminal", "terminals")),
	"Student Master": ("programme_of_study", None, ("Programme", "programmes")),
	"Student RFID Card": ("card_status", None, ("Card status", "card statuses")),
	"RFID Device": ("location", None, ("Location", "locations")),
	"RFID Device Room Mapping": ("room", None, ("Room", "rooms")),
}


@frappe.whitelist()
def get_drilldown(doctype, filters=None):
	"""Rows of one card grouped by class (or terminal, course...), split by status.
	Only the dashboard's doctypes are allowed; the query applies the user's permissions."""
	if doctype not in DRILL or not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	group, split, group_label = DRILL[doctype]
	filters = frappe.parse_json(filters) or {}
	t = f"`tab{doctype}`"
	fields = [f"{t}.`{group}`", f"{t}.`{split}`" if split else "''", "count(*) as n"]
	sql = DatabaseQuery(doctype).execute(
		fields=fields, filters=filters, order_by=None, run=0,
		group_by=f"{t}.`{group}`" + (f", {t}.`{split}`" if split else ""))

	rows, splits = {}, {}
	for g, sp, n in frappe.db.sql(sql):
		if split == "eligible_for_exam":
			sp = _("Eligible") if sp else _("Not eligible")
		sp = sp if sp not in (None, "") else _("Not set")
		r = rows.setdefault(g, {"value": g, "total": 0, "split": {}})
		r["total"] += n
		r["split"][sp] = r["split"].get(sp, 0) + n
		splits[sp] = splits.get(sp, 0) + n

	if group == "class_name":
		info = {c.name: c for c in frappe.get_all("Classes", filters={"name": ["in", [k for k in rows if k] or ["__none__"]]},
			fields=["name", "course_name", "section", "programme", "academic_term"])}
		for r in rows.values():
			c = info.get(r["value"]) or {}
			r.update(course_name=c.get("course_name"), section=c.get("section"),
				programme=c.get("programme"), academic_term=c.get("academic_term"))

	return {
		"group": group, "group_label": _(group_label[0]), "group_plural": _(group_label[1]), "split": split,
		"splits": sorted(splits, key=lambda k: -splits[k]),
		"total": sum(splits.values()),
		"rows": sorted(rows.values(), key=lambda r: (-r["total"], str(r["value"] or ""))),
	}


@frappe.whitelist()
def get_filter_options():
	return {
		"programmes": frappe.get_list("Programme", pluck="name", order_by="name asc", limit=500),
		"terms": frappe.get_list("Academic Term", fields=["name", "term_start_date", "term_end_date"], order_by="term_start_date desc", limit=100),
		"current_term": (current_term() or {}).get("name"),
	}


@frappe.whitelist()
def get_classes(programme=None, academic_term=None):
	f = {}
	if programme:
		f["programme"] = programme
	if academic_term:
		f["academic_term"] = academic_term
	return frappe.get_list("Classes", filters=f, fields=["name", "course_name", "section", "programme", "academic_term"],
		order_by="course_name asc", limit=1000)


@frappe.whitelist()
def get_dashboard(period="all", programme=None, academic_term=None, class_name=None, from_date=None, to_date=None):
	start, end, label = period_range(period, academic_term, from_date, to_date)
	classes = _scope(programme, academic_term, class_name)
	in_cls = {"class_name": ["in", classes]} if classes is not None else {}
	# Student Attendance and Attendance Summary carry the programme and term themselves
	def direct(prog_field):
		f = {}
		if programme:
			f[prog_field] = programme
		if academic_term:
			f["academic_term"] = academic_term
		if class_name:
			f["class_name"] = class_name
		return f
	ses = lambda **x: _dated("session_date", start, end, **dict(in_cls, **x))
	att = lambda **x: _dated("attendance_date", start, end, **dict(direct("program"), **x))
	summ = direct("programme")
	pun = lambda **x: _dated("punch_time", start, end, True, **x)
	log = lambda **x: _dated("swipe_time", start, end, True, **x)
	past = str(min(getdate(end), getdate(today()))) if end else today()
	cond = dict(in_cls)
	fa = {"academic_term": academic_term} if academic_term else {}
	filtered = classes is not None

	groups = [
		_group(_("Classes & sessions"), [
			_card(_("Sessions"), "Attendance Session", ses(), _("one per class meeting")),
			_card(_("Scheduled"), "Attendance Session", ses(session_status="Scheduled")),
			_card(_("Conducted"), "Attendance Session", ses(session_status="Conducted")),
			_card(_("Cancelled / postponed"), "Attendance Session", ses(session_status=["in", ["Cancelled", "Postponed"]])),
			_card(_("Attendance marked"), "Attendance Session", ses(attendance_marked=1)),
			_card(_("Not marked yet"), "Attendance Session",
				dict(ses(attendance_marked=0, session_status=["not in", ["Cancelled", "Postponed"]]),
					**({"session_date": ["between", [str(start), past]]} if start else {"session_date": ["<=", past]})),
				_("past sessions with no attendance")),
		]),
		_group(_("Student attendance"), [
			_card(_("Records"), "Student Attendance", att(), _("one per student per session")),
			_card(_("Present"), "Student Attendance", att(status="Present")),
			_card(_("Absent"), "Student Attendance", att(status="Absent")),
			_card(_("Late"), "Student Attendance", att(status="Late")),
			_card(_("OD"), "Student Attendance", att(status="OD"), _("on duty")),
			_card(_("Excused"), "Student Attendance", att(status="Excused")),
			_card(_("Marked by RFID"), "Student Attendance", att(source="RFID")),
			_card(_("Marked manually"), "Student Attendance", att(source="Manual")),
		]),
		_group(_("RFID swipes"), [
			_card(_("Swipes received"), "RFID SQL Punch Log", pun(), _("pulled from the SQL Server")),
			_card(_("Swipe logs"), "Attendance Log", log(), _("copied in for matching")),
			_card(_("Matched to a class"), "Attendance Log", log(match_status=["in", MATCHED]), _("became attendance")),
			_card(_("Unknown card"), "Attendance Log", log(match_status="Unmatched - Unknown Card"), _("card not linked to a student")),
			_card(_("No device mapping"), "Attendance Log", log(match_status="Unmatched - No Device Mapping"), _("device not mapped to a room")),
			_card(_("No session found"), "Attendance Log", log(match_status="Unmatched - No Session"), _("no class in that room then")),
		], _("all programmes and classes") if filtered else ""),
		_group(_("RFID setup"), [
			_card(_("Students with a card"), "Student Master", {"rfid_uid": ["is", "set"], "student_status": "Active"}, _("active students")),
			_card(_("Students without a card"), "Student Master", {"rfid_uid": ["is", "not set"], "student_status": "Active"}, _("their swipes can't match")),
			_card(_("RFID cards"), "Student RFID Card", {"is_active": 1}, _("active cards")),
			_card(_("RFID devices"), "RFID Device", {"is_active": 1}, _("active readers")),
			_card(_("Device room mappings"), "RFID Device Room Mapping", {}, _("reader → room")),
		], _("not affected by the filters")),
		_group(_("Applications & approvals"), [
			_card(_("Condonation pending"), "Student Attendance Condonation", dict(cond, final_status=["in", ["Pending", "May Be Approved"]], docstatus=["<", 2])),
			_card(_("Condonation approved"), "Student Attendance Condonation", dict(cond, final_status="Approved")),
			_card(_("Condonation rejected"), "Student Attendance Condonation", dict(cond, final_status="Rejected")),
			_card(_("FA / MFA pending"), "FA MFA Application", dict(fa, status="Pending", docstatus=["<", 2])),
			_card(_("FA / MFA approved"), "FA MFA Application", dict(fa, status="Approved")),
			_card(_("FA / MFA rejected"), "FA MFA Application", dict(fa, status="Rejected")),
		], _("any date; FA / MFA follows the trimester only")),
		_group(_("Eligibility"), [
			_card(_("Attendance summaries"), "Attendance Summary", dict(summ), _("one per student per course")),
			_card(_("Eligible for exam"), "Attendance Summary", dict(summ, eligible_for_exam=1)),
			_card(_("Not eligible"), "Attendance Summary", dict(summ, eligible_for_exam=0), _("below the minimum")),
		], _("any date")),
	]
	return {
		"period": period, "label": label,
		"from": str(start) if start else None, "to": str(end) if end else None,
		"filters": {"programme": programme, "academic_term": academic_term, "class_name": class_name},
		"groups": [g for g in groups if g],
	}


@frappe.whitelist()
def get_home():
	"""Numbers for the Attendance workspace home block: today, setup and attention items."""
	d = today()
	c = _count
	return {
		"today": {
			"sessions": c("Attendance Session", {"session_date": d}),
			"marked": c("Attendance Session", {"session_date": d, "attendance_marked": 1}),
			"present": c("Student Attendance", {"attendance_date": d, "status": ["in", ["Present", "Late", "OD"]]}),
			"absent": c("Student Attendance", {"attendance_date": d, "status": "Absent"}),
			"swipes": c("RFID SQL Punch Log", {"punch_time": ["between", [d, f"{d} 23:59:59"]]}),
			"unmatched": c("Attendance Log", {"swipe_time": ["between", [d, f"{d} 23:59:59"]], "match_status": ["like", "Unmatched%"]}),
		},
		"setup": {
			"Attendance Period": c("Attendance Period"),
			"Room": c("Room"),
			"RFID Device": c("RFID Device", {"is_active": 1}),
			"RFID Device Room Mapping": c("RFID Device Room Mapping"),
			"Student Master": c("Student Master", {"rfid_uid": ["is", "set"], "student_status": "Active"}),
			"rfid_agent": frappe.db.get_single_value("RFID SQL Agent Settings", "enabled")
			if frappe.has_permission("RFID SQL Agent Settings", "read") else None,
		},
		"attention": {
			"condonation": c("Student Attendance Condonation", {"final_status": ["in", ["Pending", "May Be Approved"]], "docstatus": ["<", 2]}),
			"fa_mfa": c("FA MFA Application", {"status": "Pending", "docstatus": ["<", 2]}),
			"not_marked": c("Attendance Session", {"session_date": ["<", d], "attendance_marked": 0,
				"session_status": ["not in", ["Cancelled", "Postponed"]]}),
			"unmatched": c("Attendance Log", {"match_status": ["like", "Unmatched%"]}),
		},
	}
