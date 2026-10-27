# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, formatdate, getdate


class AcademicTerm(Document):
	def autoname(self):
		self.name = f"{self.term_name.strip()} - {self.academic_year}"

	def validate(self):
		self.term_name = (self.term_name or "").strip()
		self.validate_term_no()
		self.validate_dates()
		self.validate_overlap()

	def validate_term_no(self):
		if cint(self.term_no) < 1:
			frappe.throw(_("Term No must be 1 or more."))

		duplicate = frappe.db.get_value(
			"Academic Term",
			{"academic_year": self.academic_year, "term_no": self.term_no, "name": ["!=", self.name]},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("Term No {0} is already used by {1} in {2}.").format(
					self.term_no, frappe.bold(duplicate), self.academic_year
				)
			)

	def validate_dates(self):
		start, end = getdate(self.term_start_date), getdate(self.term_end_date)
		if end <= start:
			frappe.throw(_("Term End Date must be after Term Start Date."))

		year = frappe.db.get_value(
			"Academic Year", self.academic_year, ["year_start_date", "year_end_date"], as_dict=True
		)
		if year and (start < getdate(year.year_start_date) or end > getdate(year.year_end_date)):
			frappe.throw(
				_("Term dates must fall inside Academic Year {0} ({1} to {2}).").format(
					frappe.bold(self.academic_year),
					formatdate(year.year_start_date),
					formatdate(year.year_end_date),
				)
			)

	def validate_overlap(self):
		"""Terms of the same academic year must not overlap."""
		overlap = frappe.db.get_value(
			"Academic Term",
			{
				"academic_year": self.academic_year,
				"name": ["!=", self.name],
				"term_start_date": ["<=", self.term_end_date],
				"term_end_date": [">=", self.term_start_date],
			},
			["name", "term_start_date", "term_end_date"],
			as_dict=True,
		)
		if overlap:
			frappe.throw(
				_("These dates overlap with {0} ({1} to {2}).").format(
					frappe.bold(overlap.name),
					formatdate(overlap.term_start_date),
					formatdate(overlap.term_end_date),
				)
			)


def get_current_term(date=None):
	"""The Active Academic Term whose dates contain `date` (default: today), or None.

	The current term is always worked out from term dates; it is never stored
	on the student or the enrollment."""
	date = getdate(date)
	return frappe.db.get_value(
		"Academic Term",
		{
			"term_start_date": ["<=", date],
			"term_end_date": [">=", date],
			"status": "Active",
		},
		"name",
		order_by="term_start_date desc",
	)
