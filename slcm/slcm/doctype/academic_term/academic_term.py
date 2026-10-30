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
		self.validate_term_mapping()

	def on_update(self):
		apply_term_mapping(self.name)

	def validate_term_mapping(self):
		"""One row per year and batch (a row without a batch covers the year's
		other batches)."""
		seen = {}
		for row in self.get("term_mapping") or []:
			if cint(row.year_no) < 1:
				frappe.throw(_("Term Mapping row {0}: Year must be 1 or more.").format(row.idx))
			key = (cint(row.year_no), row.batch or "")
			if key in seen:
				frappe.throw(_("Term Mapping row {0}: Year {1}{2} is already mapped in row {3}.").format(
					row.idx, row.year_no, f" ({row.batch})" if row.batch else "", seen[key]))
			seen[key] = row.idx

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


def get_programme_term(academic_term, year_no, batch=None):
	"""The Term Master (programme term, e.g. Trimester IV) that students of
	`year_no` (and `batch`) are in during `academic_term`, from its Term
	Mapping: the row for that year and batch, else the year's row without a
	batch. None when it is not mapped."""
	if not (academic_term and cint(year_no)):
		return None
	rows = frappe.get_all(
		"Academic Term Mapping",
		filters={"parenttype": "Academic Term", "parent": academic_term, "year_no": cint(year_no)},
		fields=["batch", "term"],
	)
	exact = next((r.term for r in rows if batch and r.batch == batch), None)
	return exact or next((r.term for r in rows if not r.batch), None)


def apply_term_mapping(academic_term):
	"""After the Term Mapping of `academic_term` changes: refresh the Programme
	Term on the Academic Log rows of that term, and Current Term on the Student
	Master of students for whom it is the Ongoing term."""
	rows = frappe.db.sql(
		"""SELECT l.name, l.year_no, l.status, l.term, se.batch, se.student
		   FROM `tabStudent Academic Log` l
		   JOIN `tabStudent Enrollment` se ON se.name = l.parent
		   WHERE l.parenttype = 'Student Enrollment' AND l.academic_term = %s""",
		academic_term,
		as_dict=True,
	)
	for row in rows:
		term = get_programme_term(academic_term, row.year_no, row.batch)
		if term != row.term:
			frappe.db.set_value("Student Academic Log", row.name, "term", term, update_modified=False)
		if row.status == "Ongoing":
			frappe.db.set_value("Student Master", row.student, "current_term", term, update_modified=False)


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
