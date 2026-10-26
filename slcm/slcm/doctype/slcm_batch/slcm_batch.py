# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff


class SLCMBatch(Document):
	def before_save(self):
		self._calculate_term_duration()

	def validate(self):
		self._validate_dates()

	def _validate_dates(self):
		if self.start_date and self.end_date and self.end_date < self.start_date:
			frappe.throw(_("Term End Date cannot be before Term Start Date"))

	def _calculate_term_duration(self):
		if self.start_date and self.end_date:
			days = date_diff(self.end_date, self.start_date)
			self.term_days = days
			self.term_weeks = days // 7
