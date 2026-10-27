# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class CourseOffering(Document):
	def validate(self):
		self.validate_term_in_academic_year()
		self.validate_year_no()
		self.validate_duplicate_offering()
		self.validate_faculty_table_sections()
		self.sync_primary_faculty()

	def validate_term_in_academic_year(self):
		term_year = frappe.db.get_value("Academic Term", self.term_name, "academic_year")
		if term_year and term_year != self.academic_year:
			frappe.throw(
				_("Academic Term {0} belongs to {1}, not {2}.").format(
					frappe.bold(self.term_name), term_year, self.academic_year
				)
			)

	def validate_year_no(self):
		if cint(self.year_no) < 1:
			frappe.throw(_("Year No must be 1 or more."))

		duration = cint(frappe.db.get_value("Programme", self.program, "program_duration"))
		if duration and cint(self.year_no) > duration:
			frappe.throw(
				_("Year No {0} is beyond the {1}-year duration of {2}.").format(
					self.year_no, duration, self.program
				)
			)

	def validate_duplicate_offering(self):
		"""One offering per programme + course + academic year + term + year."""
		duplicate = frappe.db.get_value(
			"Course Offering",
			{
				"program": self.program,
				"course_title": self.course_title,
				"academic_year": self.academic_year,
				"term_name": self.term_name,
				"year_no": self.year_no,
				"name": ["!=", self.name],
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("Course Offering {0} already exists for this programme, course, academic year, term and year.").format(
					frappe.bold(duplicate)
				)
			)

	def validate_faculty_table_sections(self):
		"""Each section can have only one Primary faculty; a section with no
		explicit faculty row (section left blank) is treated as "applies to
		the whole offering" and is checked separately."""
		if not self.faculty_table:
			return

		primary_sections = {}
		for row in self.faculty_table:
			if not row.is_primary:
				continue
			key = row.section or None
			if key in primary_sections:
				section_label = row.section or "the whole Course Offering"
				frappe.throw(
					f"Row {row.idx} and Row {primary_sections[key]}: only one faculty can be "
					f"marked Primary for {section_label}."
				)
			primary_sections[key] = row.idx

	def sync_primary_faculty(self):
		"""Keep the legacy `faculty` Link field in sync with the Faculty table.

		`faculty` is read directly (not via the child table) across student
		portal, parent portal, ID cards, timetable, office hours and the
		analytics dashboard, so it must always reflect a sensible value
		instead of being replaced outright by the child table. When faculty
		are split by section, the row with no section (or the first row) is
		used as the offering-level default.
		"""
		if not self.faculty_table:
			return

		unsectioned = [row for row in self.faculty_table if not row.section]
		candidates = unsectioned or self.faculty_table

		primary_rows = [row for row in candidates if row.is_primary]
		primary_row = primary_rows[0] if primary_rows else candidates[0]
		self.faculty = primary_row.faculty
