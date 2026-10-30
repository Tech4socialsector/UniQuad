# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _

ACCESS_RESULT_SETTINGS_ROLES = {"System Manager", "Academics User"}


def _check_access():
	"""This page is restricted at the desk UI level, but the whitelisted RPCs
	are directly callable via /api/method/, so mutating actions must enforce
	the same role themselves."""
	if not ACCESS_RESULT_SETTINGS_ROLES & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _to_int(v):
	return 1 if v in (1, "1", True, "true") else 0


# ── Exam Plans ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_exam_plans(search=None):
	"""Return exam plans for the plan selector."""
	filters = {}
	if search:
		filters["exam_name"] = ["like", f"%{search}%"]
	return frappe.get_all(
		"Exam Plan",
		filters=filters,
		fields=["name", "exam_name", "term", "status"],
		order_by="creation desc",
	)


# ── Publish Settings ──────────────────────────────────────────────────────────

@frappe.whitelist()
def get_exam_components():
	"""Return all active exam components."""
	return frappe.get_all(
		"Exam Component",
		filters={"is_active": 1},
		fields=["name", "component_name", "component_type"],
		order_by="component_name asc",
	)


@frappe.whitelist()
def get_publish_setting(exam_plan):
	"""Return the publish setting for the given exam plan, or None if not found."""
	if not exam_plan:
		return None

	name = frappe.db.get_value(
		"Publish Result Setting", {"exam_plan": exam_plan}, "name"
	)
	if not name:
		return None

	doc = frappe.get_doc("Publish Result Setting", name)
	return {
		"name":                 doc.name,
		"exam_plan":            doc.exam_plan,
		"show_total_marks":     doc.show_total_marks,
		"show_sgpa":            doc.show_sgpa,
		"hide_sgpa_for_failed": doc.hide_sgpa_for_failed,
		"show_egradesheet":     doc.show_egradesheet,
		"no_publish_unpaid":    doc.no_publish_unpaid,
		"no_publish_no_feedback": doc.no_publish_no_feedback,
		"components": [
			{"component": row.component, "component_name": row.component_name}
			for row in doc.publish_components
		],
	}


@frappe.whitelist()
def save_publish_setting(exam_plan, components, show_total_marks, show_sgpa,
                         hide_sgpa_for_failed, show_egradesheet,
                         no_publish_unpaid, no_publish_no_feedback):
	"""Save or create the Publish Result Setting for the given exam plan."""
	_check_access()
	if not exam_plan:
		frappe.throw("Exam Plan is required")

	if isinstance(components, str):
		components = json.loads(components)

	name = frappe.db.get_value(
		"Publish Result Setting", {"exam_plan": exam_plan}, "name"
	)
	doc = frappe.get_doc("Publish Result Setting", name) if name \
	      else frappe.new_doc("Publish Result Setting")

	if not name:
		doc.exam_plan = exam_plan

	doc.show_total_marks       = _to_int(show_total_marks)
	doc.show_sgpa              = _to_int(show_sgpa)
	doc.hide_sgpa_for_failed   = _to_int(hide_sgpa_for_failed)
	doc.show_egradesheet       = _to_int(show_egradesheet)
	doc.no_publish_unpaid      = _to_int(no_publish_unpaid)
	doc.no_publish_no_feedback = _to_int(no_publish_no_feedback)

	doc.set("publish_components", [])
	for comp in components:
		doc.append("publish_components", {"component": comp["component"]})

	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "name": doc.name}


# ── Access Results ────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_access_settings(exam_plan):
	"""
	Return all courses in the exam plan with their Access Result Settings.
	Courses are sourced from Student Course Marks (distinct courses for the plan).
	"""
	if not exam_plan:
		return []

	courses = frappe.db.sql(
		"""
		SELECT DISTINCT scm.course,
		       COALESCE(c.course_name, scm.course) AS course_name,
		       COALESCE(c.course_code, '')          AS course_code
		FROM   `tabStudent Course Marks` scm
		LEFT   JOIN `tabCourse` c ON c.name = scm.course
		WHERE  scm.exam_plan = %(exam_plan)s
		ORDER  BY course_name
		""",
		{"exam_plan": exam_plan},
		as_dict=True,
	)

	result = []
	for c in courses:
		name = frappe.db.get_value(
			"Access Result Settings",
			{"exam_plan": exam_plan, "course": c["course"]},
			"name",
		)
		if name:
			doc = frappe.get_doc("Access Result Settings", name)
			result.append({
				"course":                    c["course"],
				"course_name":               c["course_name"],
				"course_code":               c["course_code"],
				"doc_name":                  doc.name,
				"status":                    doc.status or "UNLOCKED",
				"view_access":               doc.view_access,
				"view_deadline":             str(doc.view_deadline) if doc.view_deadline else "",
				"edit_access":               doc.edit_access,
				"edit_deadline":             str(doc.edit_deadline) if doc.edit_deadline else "",
				"auto_generate_grade_access":  doc.auto_generate_grade_access,
				"edit_grade_access":          doc.edit_grade_access,
				"relative_grading_access":    doc.relative_grading_access,
				"mask_student_info":          doc.mask_student_info,
				"generate_grade_report":      doc.generate_grade_report,
				"moderation_policy_access":   doc.moderation_policy_access,
				"evaluators": [
					{
						"evaluator_type":  e.evaluator_type,
						"evaluator_name":  e.evaluator_name,
						"evaluator_email": e.evaluator_email,
					}
					for e in doc.evaluators
				],
				"visible_exams": [
					{"exam_type": v.exam_type} for v in doc.visible_exams
				],
			})
		else:
			result.append({
				"course":                    c["course"],
				"course_name":               c["course_name"],
				"course_code":               c["course_code"],
				"doc_name":                  None,
				"status":                    "UNLOCKED",
				"view_access":               1,
				"view_deadline":             "",
				"edit_access":               1,
				"edit_deadline":             "",
				"auto_generate_grade_access":  0,
				"edit_grade_access":          0,
				"relative_grading_access":    0,
				"mask_student_info":          0,
				"generate_grade_report":      0,
				"moderation_policy_access":   0,
				"evaluators":    [],
				"visible_exams": [],
			})

	return result


@frappe.whitelist()
def save_access_setting(exam_plan, course, status, view_access, view_deadline,
                        edit_access, edit_deadline, auto_generate_grade_access,
                        edit_grade_access, relative_grading_access,
                        mask_student_info, generate_grade_report,
                        moderation_policy_access, evaluators, visible_exams):
	"""Save or create an Access Result Settings record for one course."""
	_check_access()
	if not exam_plan or not course:
		frappe.throw("Exam Plan and Course are required")

	if isinstance(evaluators, str):
		evaluators = json.loads(evaluators)
	if isinstance(visible_exams, str):
		visible_exams = json.loads(visible_exams)

	name = frappe.db.get_value(
		"Access Result Settings",
		{"exam_plan": exam_plan, "course": course},
		"name",
	)
	doc = frappe.get_doc("Access Result Settings", name) if name \
	      else frappe.new_doc("Access Result Settings")

	if not name:
		if not frappe.db.exists("Course Schema Assignment", {"exam_plan": exam_plan, "course": course}):
			frappe.throw(
				f"Course '{course}' is not mapped in exam plan '{exam_plan}'. "
				"Map a Course Schema Assignment for it first."
			)
		doc.exam_plan       = exam_plan
		doc.course          = course
		doc.academic_term   = frappe.db.get_value("Exam Plan", exam_plan, "term")

	doc.status                   = status or "UNLOCKED"
	doc.view_access              = _to_int(view_access)
	doc.view_deadline            = view_deadline or None
	doc.edit_access              = _to_int(edit_access)
	doc.edit_deadline            = edit_deadline or None
	doc.auto_generate_grade_access = _to_int(auto_generate_grade_access)
	doc.edit_grade_access          = _to_int(edit_grade_access)
	doc.relative_grading_access    = _to_int(relative_grading_access)
	doc.mask_student_info          = _to_int(mask_student_info)
	doc.generate_grade_report      = _to_int(generate_grade_report)
	doc.moderation_policy_access   = _to_int(moderation_policy_access)

	doc.set("evaluators", [])
	for ev in evaluators:
		if ev.get("evaluator_name") or ev.get("evaluator_email"):
			doc.append("evaluators", {
				"evaluator_type":  ev.get("evaluator_type", "Class Faculty"),
				"evaluator_name":  ev.get("evaluator_name") or None,
				"evaluator_email": ev.get("evaluator_email") or None,
			})

	doc.set("visible_exams", [])
	for ve in visible_exams:
		if ve.get("exam_type"):
			doc.append("visible_exams", {"exam_type": ve["exam_type"]})

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	# Return the saved doc state (server may have mutated some fields via validate/before_save)
	doc.reload()
	return {
		"success":                   True,
		"doc_name":                  doc.name,
		"status":                    doc.status,
		"view_access":               doc.view_access,
		"view_deadline":             str(doc.view_deadline) if doc.view_deadline else "",
		"edit_access":               doc.edit_access,
		"edit_deadline":             str(doc.edit_deadline) if doc.edit_deadline else "",
		"auto_generate_grade_access":  doc.auto_generate_grade_access,
		"edit_grade_access":          doc.edit_grade_access,
		"relative_grading_access":    doc.relative_grading_access,
		"mask_student_info":          doc.mask_student_info,
		"generate_grade_report":      doc.generate_grade_report,
		"moderation_policy_access":   doc.moderation_policy_access,
	}


@frappe.whitelist()
def get_faculty_list(search=None):
	"""Return faculty for the evaluator autocomplete."""
	filters = {"status": "Active"} if frappe.db.has_column("Faculty", "status") else {}
	if search:
		filters["first_name"] = ["like", f"%{search}%"]
	rows = frappe.get_all(
		"Faculty",
		filters=filters,
		fields=["name", "first_name", "last_name", "email"],
		order_by="first_name asc",
		limit=20,
	)
	return [
		{
			"name":       r["name"],
			"label":      f'{r["first_name"]} {r["last_name"] or ""}'.strip(),
			"email":      r["email"] or "",
		}
		for r in rows
	]


@frappe.whitelist()
def get_exam_assessment_types():
	"""Return all active exam assessment types for Visible Exams selection."""
	return frappe.get_all(
		"Exam Assessment Type",
		filters={"is_active": 1},
		fields=["name", "type_name", "assessment_type"],
		order_by="type_name asc",
	)
