# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class StudentCourseMarks(Document):
	def validate(self):
		# Results loaded by Bulk Import Marks carry their own total and grade
		if self.flags.keep_imported_result:
			return
		if not self._has_marks_entered():
			self.total_marks = 0
			self.grade = ""
			return
		# Only recalculate when something the result depends on changed, so a
		# grade set by grade upload / grade override survives e.g. a remark edit
		if self.is_new() or self.flags.recalculate_result or self._result_inputs_changed():
			self._recalculate()

	def _recalculate(self):
		"""Same rules as Course Results (compute_student_result): weighted
		marks, component pass marks, re-exam and improvement."""
		from slcm.slcm.page.examination_result.examination_result import compute_student_result

		values, _result = compute_student_result(
			self.course,
			self.exam_plan,
			[row.as_dict() for row in self.marks_entries],
			attendance_status=self.attendance_status,
			improvement_marks=self.improvement_marks,
			stored_total=self.total_marks,
		)
		self.update(values)

	def _result_inputs(self, doc):
		entries = sorted(
			(
				row.component or "",
				row.assessment_type or "",
				flt(row.marks),
				flt(row.moderated_marks),
				flt(row.revaluation_marks),
			)
			for row in doc.marks_entries
		)
		return (
			entries,
			doc.attendance_status or "",
			flt(doc.improvement_marks),
			doc.evaluation_schema or "",
			doc.exam_plan or "",
			doc.course or "",
		)

	def _result_inputs_changed(self):
		before = self.get_doc_before_save()
		return not before or self._result_inputs(before) != self._result_inputs(self)

	def _has_marks_entered(self):
		if self.improvement_marks not in (None, "", 0):
			return True
		for row in self.marks_entries:
			if row.marks not in (None, "") or row.moderated_marks not in (None, ""):
				return True
		return (self.attendance_status or "").lower() == "absent"


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
			doc.flags.recalculate_result = True
			doc.save(ignore_permissions=True)
			updated += 1
		except Exception as e:
			frappe.log_error(f"bulk_assign_grades: {r.name} — {e}", "Grade Assignment")

	return {"updated": updated, "total": len(records)}
