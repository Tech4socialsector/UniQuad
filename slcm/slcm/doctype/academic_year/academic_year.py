# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, getdate


class AcademicYear(Document):
	def validate(self):
		self.validate_dates()
		self.validate_overlap()
		self.validate_current_year()

	def validate_dates(self):
		if getdate(self.year_end_date) <= getdate(self.year_start_date):
			frappe.throw(_("Year End Date must be after Year Start Date."))

	def validate_overlap(self):
		"""Two date ranges overlap when each one starts on or before the other ends."""
		overlap = frappe.db.get_value(
			"Academic Year",
			{
				"name": ["!=", self.name],
				"year_start_date": ["<=", self.year_end_date],
				"year_end_date": [">=", self.year_start_date],
			},
			["name", "year_start_date", "year_end_date"],
			as_dict=True,
		)
		if overlap:
			frappe.throw(
				_("These dates overlap with Academic Year {0} ({1} to {2}).").format(
					frappe.bold(overlap.name),
					formatdate(overlap.year_start_date),
					formatdate(overlap.year_end_date),
				)
			)

	def validate_current_year(self):
		if not self.is_current_year:
			return

		if self.status != "Active":
			frappe.throw(_("The current Academic Year must have status Active."))

		other = frappe.db.get_value(
			"Academic Year", {"is_current_year": 1, "name": ["!=", self.name]}, "name"
		)
		if other:
			frappe.throw(
				_("{0} is already the current Academic Year. Uncheck Is Current Year on it first.").format(
					frappe.bold(other)
				)
			)


def get_current_academic_year():
	"""The Academic Year marked Is Current Year, or None."""
	return frappe.db.get_value("Academic Year", {"is_current_year": 1}, "name")
