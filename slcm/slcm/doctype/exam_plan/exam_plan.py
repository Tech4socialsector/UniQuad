# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ExamPlan(Document):
	def validate(self):
		self.validate_one_plan_per_term()
		self.fill_seat_capacity()
		self.validate_course_schedules()

	def fill_seat_capacity(self):
		for row in self.course_schedules:
			if row.venue and not row.seat_capacity:
				row.seat_capacity = frappe.db.get_value("Venue Master", row.venue, "capacity") or 0

	def validate_one_plan_per_term(self):
		if not self.term or frappe.db.get_single_value("Examination Settings", "allow_multiple_plans_per_term"):
			return
		other = frappe.db.get_value("Exam Plan", {"term": self.term, "name": ["!=", self.name]}, "name")
		if other:
			frappe.throw(
				_("{0} already has the Exam Plan {1}. Use that plan, or turn on "
				  "Examination Settings › Allow more than one Exam Plan per term.").format(
					frappe.bold(self.term), frappe.bold(other)
				)
			)

	def validate_course_schedules(self):
		"""Exam timetable rules (term dates, holidays, rooms shared with the class
		Time Table, seats, student clashes): see slcm.slcm.utils.exam_timetable."""
		from slcm.slcm.utils.exam_timetable import check_exam_schedule

		result = check_exam_schedule(self)
		if result["errors"]:
			frappe.throw(
				"<br>".join(_("Row {0} ({1}): {2}").format(e["row"], frappe.bold(e["course"]), e["message"]) for e in result["errors"]),
				title=_("Exam timetable"),
			)
		for w in result["warnings"]:
			frappe.msgprint(_("Row {0} ({1}): {2}").format(w["row"], w["course"], w["message"]), indicator="orange", alert=True)
