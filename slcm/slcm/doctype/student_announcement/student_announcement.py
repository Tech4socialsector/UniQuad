# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today, nowdate, getdate


class StudentAnnouncement(Document):
	def validate(self):
		if self.expiry_date and self.publish_date and self.expiry_date < self.publish_date:
			frappe.throw("Expiry Date cannot be before Publish Date.")

	def before_save(self):
		if not self.publish_date:
			self.publish_date = today()


@frappe.whitelist(allow_guest=False)
def get_active_announcements(student=None, limit=20):
	"""Return announcements visible to the given student."""
	today_str = nowdate()

	records = frappe.get_all(
		"Student Announcement",
		filters=[["is_active", "=", 1], ["publish_date", "<=", today_str]],
		fields=[
			"name", "title", "content", "announcement_type", "priority",
			"publish_date", "expiry_date", "target_audience",
		],
		order_by="priority desc, publish_date desc",
		limit=int(limit),
		ignore_permissions=True,
	)

	student_data = None
	if student:
		student_data = frappe.db.get_value(
			"Student Master", student, ["programme_of_study"], as_dict=True
		)
		if student_data:
			# Announcement Programme Target.programme links to Programme;
			# Student Master has no batch_year field.
			student_data.programme = student_data.programme_of_study
			student_data.batch_year = None

	visible = []
	today_date = getdate(today_str)
	for r in records:
		if r.expiry_date and getdate(r.expiry_date) < today_date:
			continue

		if r.target_audience == "All Students":
			visible.append(r)
			continue

		if not student_data:
			visible.append(r)
			continue

		if r.target_audience == "Specific Programme(s)":
			target_programmes = frappe.get_all(
				"Announcement Programme Target",
				filters={"parent": r.name},
				fields=["programme"],
				ignore_permissions=True,
			)
			if any(t.programme == student_data.programme for t in target_programmes):
				visible.append(r)

		elif r.target_audience == "Specific Batch Year(s)":
			target_batches = frappe.get_all(
				"Announcement Batch Target",
				filters={"parent": r.name},
				fields=["batch_year"],
				ignore_permissions=True,
			)
			if any(str(t.batch_year) == str(student_data.batch_year or "") for t in target_batches):
				visible.append(r)

	return visible
