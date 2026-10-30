# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SLCMBatch(Document):
	pass


def count_enrolled(batch):
	"""Students enrolled in `batch` (one enrollment each), excluding dropped enrollments."""
	return frappe.db.count(
		"Student Enrollment",
		{
			"batch": batch,
			"status": ["!=", "Dropped"],
		},
	)


def update_enrolled_count(batch):
	"""Recompute SLCM Batch.total_enrolled_count."""
	if not batch or not frappe.db.exists("SLCM Batch", batch):
		return
	frappe.db.set_value(
		"SLCM Batch",
		batch,
		"total_enrolled_count",
		count_enrolled(batch),
		update_modified=False,
	)
