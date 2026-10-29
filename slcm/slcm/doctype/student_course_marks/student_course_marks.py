# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class StudentCourseMarks(Document):
	def validate(self):
		self._calculate_total()
		self._assign_grade()

	def _calculate_total(self):
		total = 0.0
		for row in self.marks_entries:
			total += float(row.moderated_marks or row.marks or 0)
		self.total_marks = total

	def _assign_grade(self):
		# Only auto-assign if grade not manually set via update fields
		if self.updated_grade:
			return

		# Don't assign a grade (e.g. "F") until marks have actually been
		# entered — otherwise every student is treated as graded/failed
		# from the moment their record is created.
		if not self._has_marks_entered():
			self.grade = ""
			return

		schema_name = self._resolve_grading_schema()
		if not schema_name:
			return

		try:
			schema = frappe.get_doc("Grading Schema", schema_name)
		except frappe.DoesNotExistError:
			return

		effective_marks = float(self.updated_final_marks or self.total_marks or 0)
		self.grade = schema.get_grade(effective_marks) or self.grade
		if not self.grade:
			return

		# Reflect failed status in enrollment_status if not already set
		if schema.is_failed(effective_marks) and not self.enrollment_status:
			pass  # enrollment_status is set by admin, not auto

	def _has_marks_entered(self):
		if self.updated_final_marks not in (None, ""):
			return True
		for row in self.marks_entries:
			if row.marks not in (None, "") or row.moderated_marks not in (None, ""):
				return True
		return False

	def _resolve_grading_schema(self):
		"""Return grading schema name via Course Schema Assignment (exam_plan + course)."""
		if self.exam_plan and self.course:
			schema = frappe.db.get_value(
				"Course Schema Assignment",
				{"exam_plan": self.exam_plan, "course": self.course},
				"grade_schema",
			)
			if schema:
				return schema
		return None


@frappe.whitelist()
def bulk_assign_grades(exam_plan):
	"""Recalculate and assign grades for all StudentCourseMarks in an exam plan."""
	if not frappe.has_permission("Student Course Marks", "write"):
		frappe.throw("Not permitted")

	records = frappe.get_all(
		"Student Course Marks",
		filters={"exam_plan": exam_plan},
		fields=["name"],
	)
	updated = 0
	for r in records:
		try:
			doc = frappe.get_doc("Student Course Marks", r.name)
			doc.save(ignore_permissions=True)
			updated += 1
		except Exception as e:
			frappe.log_error(f"bulk_assign_grades: {r.name} — {e}", "Grade Assignment")

	return {"updated": updated, "total": len(records)}
