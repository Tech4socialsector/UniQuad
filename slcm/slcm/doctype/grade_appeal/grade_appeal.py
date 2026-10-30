# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now, today

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
		self._set_fee_amount()
		self._set_revised_result()

	def after_insert(self):
		self._raise_revaluation_fee()

	def _set_course(self):
		"""`course` is required; the term defaults to the exam plan's term."""
		if not self.course:
			frappe.throw("Please select the Course being appealed.")
		if not self.academic_term and self.exam_plan:
			self.academic_term = frappe.db.get_value("Exam Plan", self.exam_plan, "term")

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

	def _set_fee_amount(self):
		"""Re-evaluation is charged per paper (Examination Settings); a Grade
		Appeal is one paper. The fee is fixed once the demand is raised."""
		if self.fee_demand:
			return
		self.fee_amount = (
			flt(frappe.db.get_single_value("Examination Settings", "revaluation_fee_per_paper"))
			if self.appeal_type == "Re-evaluation" else 0
		)

	def _raise_revaluation_fee(self):
		if not flt(self.fee_amount) or self.fee_demand:
			return
		from slcm.slcm.fee.event_hooks import _get_component_by_type, _get_student_data
		from slcm.slcm.fee.fee_demand_utils import create_event_demand

		component = _get_component_by_type("Revaluation Fee")
		if not component:
			frappe.log_error("Fee Component with type 'Revaluation Fee' not found.", "Grade Appeal")
			return
		demand = create_event_demand(
			student=self.student,
			fee_component_name=component,
			amount=self.fee_amount,
			demand_type=frappe.db.get_value("Fee Component", component, "demand_type") or "Academic",
			trigger_doctype="Grade Appeal",
			trigger_name=self.name,
			description=f"Revaluation Fee — {self.course} ({self.exam_plan})",
			academic_year=frappe.db.get_value("Academic Term", self.academic_term, "academic_year") if self.academic_term else None,
			programme=_get_student_data(self.student, ["programme"]).get("programme"),
		)
		self.db_set("fee_demand", demand)

	def _set_revised_result(self):
		"""On Resolved, keep the course's grade/marks after the review next to
		the appealed ones (marks are changed on Course Results / Student Course
		Marks, not here)."""
		if self.status != "Resolved":
			self.revised_grade = None
			self.revised_marks = None
			return
		marks = frappe.db.get_value(
			"Student Course Marks",
			{"student": self.student, "exam_plan": self.exam_plan, "course": self.course},
			["name", "grade", "moderated_grade", "updated_grade", "total_marks", "updated_final_marks"],
			as_dict=True,
		) or frappe._dict()
		self.revised_grade = marks.updated_grade or marks.moderated_grade or marks.grade or ""
		self.revised_marks = marks.updated_final_marks or marks.total_marks or 0


@frappe.whitelist()
def get_marks_record(grade_appeal):
	"""Student Course Marks of the appealed course, for the form's button."""
	doc = frappe.get_doc("Grade Appeal", grade_appeal)
	doc.check_permission("read")
	return frappe.db.get_value(
		"Student Course Marks",
		{"student": doc.student, "exam_plan": doc.exam_plan, "course": doc.course},
		"name",
	)


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
def courses_for_student(doctype, txt, searchfield, start, page_len, filters):
	"""Courses the student has marks for in the exam plan."""
	filters = filters or {}
	return frappe.db.sql(
		"""
		SELECT DISTINCT c.name, c.course_name
		FROM `tabStudent Course Marks` scm
		JOIN `tabCourse` c ON c.name = scm.course
		WHERE scm.student = %(student)s
		  AND scm.exam_plan = %(exam_plan)s
		  AND (c.name LIKE %(txt)s OR c.course_name LIKE %(txt)s)
		ORDER BY c.course_name
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"student": filters.get("student"),
			"exam_plan": filters.get("exam_plan"),
			"txt": f"%{txt}%",
			"start": start,
			"page_len": page_len,
		},
	)
