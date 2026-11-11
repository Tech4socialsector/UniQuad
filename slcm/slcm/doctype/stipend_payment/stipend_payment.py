# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class StipendPayment(Document):
	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero."))

	def on_submit(self):
		self.db_set("status", "Submitted", update_modified=False)
		self._log_to_student("Submitted")

	def on_cancel(self):
		self.db_set("status", "Cancelled", update_modified=False)
		self._log_to_student("Cancelled")

	def on_trash(self):
		# Drop this payment's rows from the Student Master stipend log; a dangling
		# Link would otherwise block every later save of that Student Master.
		frappe.db.delete(
			"Student Stipend Log",
			{"stipend_payment": self.name, "parenttype": "Student Master", "parentfield": "stipend_log"},
		)

	def _log_to_student(self, status):
		from slcm.slcm.doctype.student_master.student_master import _append_stipend_log

		_append_stipend_log(self.student, self, status)
