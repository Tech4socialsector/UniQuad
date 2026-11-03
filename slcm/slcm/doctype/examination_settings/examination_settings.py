# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ExaminationSettings(Document):
	def validate(self):
		self.validate_max_cgpa_for_improvement()

	def validate_max_cgpa_for_improvement(self):
		"""The limit is a CGPA, so it must fit the grade points of the grading
		schemas (a 4-point value such as 3.0 on a 10-point scale shuts everyone out)."""
		limit = flt(self.max_cgpa_for_improvement)
		if limit < 0:
			frappe.throw(_("Max CGPA for Improvement Exam cannot be negative."))
		top = flt(frappe.db.sql("SELECT MAX(grade_point) FROM `tabGrading Schema Component`")[0][0])
		if limit and top and limit > top:
			frappe.throw(
				_("Max CGPA for Improvement Exam ({0}) is above the highest grade point in your grading schemas ({1}).").format(
					limit, top
				)
			)
