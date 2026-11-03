# Examination Dashboard: count cards of what has been created, for all exam
# plans or one. Each card names the list it opens (doctype + filters).

import frappe
from frappe import _

from slcm.slcm.page.examination_planner import examination_planner as planner

PAID = ["Paid", "Captured", "Authorized"]


def _card(label, doctype, filters=None, hint="", step=None, value=None):
	"""value overrides the count (for child tables, which have no list view)."""
	filters = filters or {}
	return {
		"label": label, "hint": hint, "doctype": doctype, "filters": filters, "step": step,
		"value": frappe.db.count(doctype, filters) if value is None else value,
	}


def _child_count(doctype, plan_filter):
	return frappe.db.count(doctype, dict(plan_filter and {"parent": plan_filter["exam_plan"]} or {}, parenttype="Exam Plan"))


@frappe.whitelist()
def get_dashboard(exam_plan=None):
	planner._check_access()
	plans = frappe.get_all("Exam Plan", fields=["name", "exam_name", "term", "status"], order_by="creation desc")
	if exam_plan and exam_plan not in {p.name for p in plans}:
		exam_plan = None
	f = {"exam_plan": exam_plan} if exam_plan else {}
	failed_grades = frappe.get_all("Grading Schema Component", filters={"failed": 1}, pluck="grade", distinct=True) or ["__none__"]
	plan_f = {"name": exam_plan} if exam_plan else {}

	groups = [
		{"title": _("Setup"), "note": _("shared by every exam plan"), "cards": [
			_card(_("Exam Components"), "Exam Component", hint=_("e.g. Internal, End Term")),
			_card(_("Assessment Types"), "Exam Assessment Type", hint=_("e.g. Quiz, Project")),
			_card(_("Evaluation Schemas"), "Evaluation Schema", hint=_("how a course is marked")),
			_card(_("Grading Schemas"), "Grading Schema", hint=_("marks to grades")),
		]},
		{"title": _("Exam plans"), "cards": [
			_card(_("Exam Plans"), "Exam Plan", plan_f, hint=_("one per term")),
			_card(_("Active plans"), "Exam Plan", dict(plan_f, status="Active")),
			_card(_("Timetables published"), "Exam Plan", dict(plan_f, timetable_published=1), hint=_("visible to students")),
			_card(_("Courses mapped"), "Course Schema Assignment", f, hint=_("course → schemas"), step=0),
		]},
		{"title": _("Schedules"), "cards": [
			_card(_("Exam sittings"), "Exam Course Schedule", value=_child_count("Exam Course Schedule", f), hint=_("courses with an exam slot"), step=1),
			_card(_("Assessment schedules"), "Exam Assessment Schedule", f, hint=_("internal assessments")),
			_card(_("Re-exam sittings"), "Exam Reexam Schedule", value=_child_count("Exam Reexam Schedule", f), step=4),
			_card(_("Barcodes"), "Exam Barcode", f, hint=_("answer-script barcodes"), step=2),
		]},
		{"title": _("Students & marks"), "cards": [
			_card(_("Marks records"), "Student Course Marks", f, hint=_("one per student per course")),
			_card(_("Draft"), "Student Course Marks", dict(f, status="Draft"), hint=_("still being entered")),
			_card(_("Submitted"), "Student Course Marks", dict(f, status="Submitted"), hint=_("final from faculty")),
			_card(_("Locked"), "Student Course Marks", dict(f, status="Locked"), hint=_("frozen")),
			_card(_("Detained"), "Student Course Marks", dict(f, attendance_status="Detained"), hint=_("attendance below minimum")),
			_card(_("Absent"), "Student Course Marks", dict(f, attendance_status="Absent")),
		]},
		{"title": _("Results"), "cards": [
			_card(_("Results generated"), "Student Result Publish", f, hint=_("term GPA calculated")),
			_card(_("Published"), "Student Result Publish", dict(f, is_published=1), hint=_("visible to students")),
			_card(_("Not published"), "Student Result Publish", dict(f, is_published=0)),
			_card(_("Fail grades"), "Student Course Marks", dict(f, grade=["in", failed_grades]), hint=_("before re-exam")),
		]},
		{"title": _("Re-exam & improvement"), "cards": [
			_card(_("Re-exam windows"), "Re Exam Course Setting", f, hint=_("courses open for re-exam")),
			_card(_("Re-exam registrations"), "Re Exam Registration", dict(f, status="Registered")),
			_card(_("Re-exam paid"), "Re Exam Registration", dict(f, status="Registered", payment_status=["in", PAID])),
			_card(_("Improvement windows"), "Improvement Exam Course Setting", f),
			_card(_("Improvement registrations"), "Improvement Exam Registration", dict(f, status="Registered")),
			_card(_("Improvement paid"), "Improvement Exam Registration", dict(f, status="Registered", payment_status=["in", PAID])),
		]},
	]
	return {"plans": plans, "exam_plan": exam_plan, "groups": groups}
