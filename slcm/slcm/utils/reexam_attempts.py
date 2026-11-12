# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Re-exam attempts: a student writes the re-exam again and again until they pass.

Attempt 1 is the re-exam of the Exam Plan the course was taught in. When the
student fails it (or never wrote it), the next attempt is the re-exam of a later
Exam Plan: the student gets a Student Course Marks record there with their
regular marks (internals and end term) carried over, so the re-exam again
replaces only what the Evaluation Schema says it replaces. That record is
graded a fail until the re-exam marks come in, so the later plan's Re Exam
screens, re-exam timetable and the student portal pick the course up.

Once the latest record of a course has a pass grade the student is done: no
further registration or carry forward.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate


def _failed_grades(exam_plan, course):
	schema = frappe.db.get_value("Course Schema Assignment", {"exam_plan": exam_plan, "course": course}, "grade_schema")
	return set(frappe.get_all("Grading Schema Component", filters={"parent": schema, "failed": 1}, pluck="grade")) if schema else set()


def _reexam_keys(exam_plan, course):
	"""(component, assessment_type) of the schema's re-exam rows."""
	schema = frappe.db.get_value("Course Schema Assignment", {"exam_plan": exam_plan, "course": course}, "evaluation_schema")
	if not schema:
		return set()
	return {(r.component or "", r.assessment_type or "") for r in frappe.get_all(
		"Schema Reexam Config", filters={"parent": schema, "parenttype": "Evaluation Schema"},
		fields=["component", "assessment_type"])}


def _term_start(exam_plan):
	term = frappe.db.get_value("Exam Plan", exam_plan, "term")
	start = frappe.db.get_value("Academic Term", term, "term_start_date") if term else None
	return getdate(start) if start else getdate("1900-01-01")


def course_attempts(student, course):
	"""The student's records of the course, oldest plan first: exam plan, term,
	regular and final marks and grades, re-exam marks, failed, registered."""
	rows = frappe.get_all(
		"Student Course Marks", filters={"student": student, "course": course},
		fields=["name", "exam_plan", "academic_term", "total_marks", "grade", "updated_final_marks", "updated_grade"],
	)
	for r in rows:
		r.start = _term_start(r.exam_plan)
		grade = r.updated_grade or r.grade
		r.result_grade = grade or ""
		# absent ("Ab") hasn't passed either
		r.failed = bool(grade) and (grade == "Ab" or grade in _failed_grades(r.exam_plan, course))
		keys = _reexam_keys(r.exam_plan, course)
		reexam = [e for e in frappe.get_all("Student Marks Entry", filters={"parent": r.name, "parenttype": "Student Course Marks"},
		                                    fields=["component", "assessment_type", "marks"])
		          if ((e.component or ""), (e.assessment_type or "")) in keys and e.marks is not None]
		r.reexam_marks = sum(flt(e.marks) for e in reexam) if reexam else None
		r.registered = bool(frappe.db.exists("Re Exam Registration", {
			"student": student, "course": course, "exam_plan": r.exam_plan, "status": ["!=", "Cancelled"]}))
	rows.sort(key=lambda r: (r.start, r.exam_plan))
	return rows


def latest(student, course):
	rows = course_attempts(student, course)
	return rows[-1] if rows else None


def has_passed(student, course):
	"""The latest record of the course is graded and not a fail grade."""
	last = latest(student, course)
	return bool(last and last.result_grade and not last.failed)


def carry_forward(student, course, target_plan):
	"""Student Course Marks for the next re-exam attempt in target_plan, with the
	regular marks of the student's latest record. Returns (name, status)."""
	existing = frappe.db.get_value("Student Course Marks", {"student": student, "course": course, "exam_plan": target_plan}, "name")
	if existing:
		return existing, "existing"
	last = latest(student, course)
	if not last:
		frappe.throw(_("{0} has no marks for {1} yet.").format(student, course))
	if last.result_grade and not last.failed:
		frappe.throw(_("{0} has already passed {1} ({2} in {3}).").format(student, course, last.result_grade, last.exam_plan))
	if _term_start(target_plan) <= last.start:
		frappe.throw(_("The next attempt must be in a later Exam Plan than {0}.").format(last.exam_plan))

	target_term = frappe.db.get_value("Exam Plan", target_plan, "term")
	if not target_term:
		frappe.throw(_("Exam Plan {0} has no Academic Term.").format(target_plan))
	src = frappe.db.get_value("Course Schema Assignment", {"exam_plan": last.exam_plan, "course": course},
	                          ["evaluation_schema", "grade_schema"], as_dict=True) or {}
	if src and not frappe.db.exists("Course Schema Assignment", {"exam_plan": target_plan, "course": course}):
		frappe.get_doc({
			"doctype": "Course Schema Assignment", "exam_plan": target_plan, "course": course, "academic_term": target_term,
			"evaluation_schema": src.get("evaluation_schema") or "", "grade_schema": src.get("grade_schema") or "",
		}).insert(ignore_permissions=True)

	source = frappe.get_doc("Student Course Marks", last.name)
	keys = _reexam_keys(last.exam_plan, course)
	doc = frappe.new_doc("Student Course Marks")
	doc.update({
		"student": student, "course": course, "exam_plan": target_plan, "academic_term": target_term,
		"evaluation_schema": src.get("evaluation_schema") or source.evaluation_schema or "",
		"student_id": source.student_id, "consider_for_sgpa": source.consider_for_sgpa,
		"remark": _("Re-exam attempt {0}: regular marks carried over from {1}").format(
			sum(1 for r in course_attempts(student, course) if r.registered) + 1, last.exam_plan),
	})
	for e in source.marks_entries:
		if ((e.component or ""), (e.assessment_type or "")) in keys:
			continue   # the earlier attempt's re-exam marks don't carry over
		doc.append("marks_entries", {k: e.get(k) for k in (
			"component", "assessment_type", "label", "marks", "revaluation_marks", "moderated_marks")})
	doc.flags.recalculate_result = True
	doc.insert(ignore_permissions=True)
	return doc.name, "created"


def students_to_carry(target_plan):
	"""(student, course) whose latest record is a fail in an earlier Exam Plan."""
	start = _term_start(target_plan)
	pairs = frappe.db.sql(
		"""SELECT DISTINCT student, course FROM `tabStudent Course Marks`
		   WHERE IFNULL(grade, '') != '' AND exam_plan != %s""",
		target_plan,
	)
	out = []
	for student, course in pairs:
		last = latest(student, course)
		if last and last.failed and last.start < start and last.exam_plan != target_plan:
			out.append((student, course, last.exam_plan))
	return out


def superseded_records(student, upto_plan=None):
	"""Names of the student's Student Course Marks replaced by a later attempt of the same course.

	A failed course carried forward to a later Exam Plan has one record per attempt; only the
	latest attempt counts for CGPA, transcripts and backlogs. With ``upto_plan`` only attempts
	up to that plan's term are considered (results as they stood at that point).
	Ordering matches course_attempts(): term start date, then exam plan name.
	"""
	rows = frappe.db.sql(
		"""SELECT scm.name, scm.course, scm.exam_plan, at.term_start_date AS start
		   FROM `tabStudent Course Marks` scm
		   LEFT JOIN `tabExam Plan` ep ON ep.name = scm.exam_plan
		   LEFT JOIN `tabAcademic Term` at ON at.name = ep.term
		   WHERE scm.student = %s""",
		student, as_dict=True,
	)
	floor = getdate("1900-01-01")
	limit = _term_start(upto_plan) if upto_plan else None
	by_course = {}
	for r in rows:
		r.start = getdate(r.start) if r.start else floor
		if limit is not None and r.start > limit:
			continue
		by_course.setdefault(r.course, []).append(r)
	out = set()
	for attempts in by_course.values():
		attempts.sort(key=lambda r: (r.start, r.exam_plan or ""))
		out.update(r.name for r in attempts[:-1])
	return out
