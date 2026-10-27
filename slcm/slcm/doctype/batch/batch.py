# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Batch(Document):
	def before_save(self):
		if not self.is_new() and self.has_value_changed("academic_year"):
			self.total_enrolled_count = count_enrolled(self.name, self.academic_year)


def count_enrolled(batch, academic_year):
	"""Students enrolled in `batch` for `academic_year`, excluding dropped enrollments."""
	return frappe.db.count(
		"Student Enrollment",
		{
			"batch": batch,
			"academic_year": academic_year,
			"status": ["!=", "Dropped"],
		},
	)


def update_enrolled_count(batch):
	"""Recompute Batch.total_enrolled_count for the batch's own academic year."""
	if not batch:
		return
	academic_year = frappe.db.get_value("Batch", batch, "academic_year")
	if academic_year is None:
		return
	frappe.db.set_value(
		"Batch",
		batch,
		"total_enrolled_count",
		count_enrolled(batch, academic_year),
		update_modified=False,
	)
