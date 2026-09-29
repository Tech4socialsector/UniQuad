# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now, today

ACTIVE_STATUSES = ("Submitted", "Under Review")
CLOSED_STATUSES = ("Resolved", "Rejected")


class GradeAppeal(Document):
	def validate(self):
		if not self.submitted_on:
			self.submitted_on = today()
		if not self.status:
			self.status = "Submitted"

		self._set_course()
		self._validate_marks_exist()
		self._set_current_result()
		self._check_duplicate()
		self._validate_resolution()
		self._set_resolution_audit()

	def _set_course(self):
		"""`course` is fetched from the offering; fall back if the offering has none."""
		if not self.course and self.course_offering:
			self.course = frappe.db.get_value("Course Offering", self.course_offering, "course_title")
		if not self.course:
			frappe.throw("The selected Course Offering is not linked to a Course.")

	def _validate_marks_exist(self):
		if not frappe.db.exists(
			"Student Course Marks",
			{"student": self.student, "exam_plan": self.exam_plan, "course": self.course},
		):
			frappe.throw(
				f"No marks found for {self.student} in {self.course} for exam plan {self.exam_plan}. "
				"An appeal can only be raised against an existing result."
			)

	def _set_current_result(self):
		"""Snapshot the grade/marks being appealed if they weren't provided."""
		if self.current_grade and self.current_marks:
			return
		marks = frappe.db.get_value(
			"Student Course Marks",
			{"student": self.student, "exam_plan": self.exam_plan, "course": self.course},
			["grade", "moderated_grade", "updated_grade", "total_marks", "updated_final_marks"],
			as_dict=True,
		) or frappe._dict()
		if not self.current_grade:
			self.current_grade = marks.updated_grade or marks.moderated_grade or marks.grade or ""
		if not self.current_marks:
			self.current_marks = marks.updated_final_marks or marks.total_marks or 0

	def _check_duplicate(self):
		if self.status not in ACTIVE_STATUSES:
			return
		existing = frappe.db.exists(
			"Grade Appeal",
			{
				"student": self.student,
				"exam_plan": self.exam_plan,
				"course": self.course,
				"appeal_type": self.appeal_type,
				"status": ["in", list(ACTIVE_STATUSES)],
				"name": ["!=", self.name or ""],
			},
		)
		if existing:
			frappe.throw(
				f"An active appeal for this course and appeal type already exists ({existing})."
			)

	def _validate_resolution(self):
		if self.status in CLOSED_STATUSES and not (self.resolution or "").strip():
			frappe.throw(
				f"Please enter the Resolution Details before marking this appeal as {self.status}. "
				"The student sees this explanation in the portal."
			)

	def _set_resolution_audit(self):
		if self.status in CLOSED_STATUSES:
			previous = self.get_doc_before_save()
			if not self.resolved_on or (previous and previous.status != self.status):
				self.resolved_on = now()
				self.resolved_by = frappe.session.user
		else:
			# Re-opened (or still open): clear any stale closure audit
			self.resolved_on = None
			self.resolved_by = None


# ── Link-field queries for the desk form ────────────────────────────────────

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def exam_plans_for_student(doctype, txt, searchfield, start, page_len, filters):
	student = (filters or {}).get("student")
	return frappe.db.sql(
		"""
		SELECT DISTINCT scm.exam_plan, ep.exam_name
		FROM `tabStudent Course Marks` scm
		LEFT JOIN `tabExam Plan` ep ON ep.name = scm.exam_plan
		WHERE scm.student = %(student)s
		  AND (scm.exam_plan LIKE %(txt)s OR ep.exam_name LIKE %(txt)s)
		ORDER BY scm.exam_plan
		LIMIT %(start)s, %(page_len)s
		""",
		{"student": student, "txt": f"%{txt}%", "start": start, "page_len": page_len},
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def offerings_for_student(doctype, txt, searchfield, start, page_len, filters):
	filters = filters or {}
	courses = frappe.get_all(
		"Student Course Marks",
		filters={"student": filters.get("student"), "exam_plan": filters.get("exam_plan")},
		pluck="course",
	)
	if not courses:
		return []
	return frappe.db.sql(
		"""
		SELECT co.name, co.course_name, co.course_title
		FROM `tabCourse Offering` co
		WHERE co.course_title IN %(courses)s
		  AND (co.name LIKE %(txt)s OR co.course_name LIKE %(txt)s)
		ORDER BY co.creation DESC
		LIMIT %(start)s, %(page_len)s
		""",
		{"courses": tuple(courses), "txt": f"%{txt}%", "start": start, "page_len": page_len},
	)
