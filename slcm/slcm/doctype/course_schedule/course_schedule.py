# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CourseSchedule(Document):
	def validate(self):
		if not self.class_name:
			self.class_name = self.get_class_name()

	def after_insert(self):
		self.create_attendance_session()

	def create_attendance_session(self):
		if not self.schedule_date or not self.from_time or not self.to_time:
			return

		# Check if session already exists
		exists = frappe.db.exists("Attendance Session", {
			"course_schedule": self.name,
			"session_date": self.schedule_date,
			"session_start_time": self.from_time
		})

		if exists:
			return

		class_name = self.class_name or self.get_class_name()
		if not class_name:
			frappe.log_error(f"Could not find the Class for Course Schedule {self.name}")
			return

		doc = frappe.get_doc({
			"doctype": "Attendance Session",
			"based_on": "Course Schedule",
			"course_schedule": self.name,
			"class_name": class_name,
			"course": self.course,
			"instructor": self.instructor, # Note: Course Schedule has instructor link
			"room": self.room,
			"session_date": self.schedule_date,
			"session_start_time": self.from_time,
			"session_end_time": self.to_time,
			"session_type": "Lecture",
			"session_status": "Scheduled"
		})
		doc.insert(ignore_permissions=True)

	def get_class_name(self):
		# Try to find the newest class for this course and programme
		if not self.course:
			return None
		filters = {"course": self.course}
		if self.program:
			filters["programme"] = self.program

		classes = frappe.get_all("Classes", filters=filters, limit=1, order_by="creation desc")
		if classes:
			return classes[0].name

		# Fallback: try without programme
		if self.program:
			del filters["programme"]
			classes = frappe.get_all("Classes", filters=filters, limit=1, order_by="creation desc")
			if classes:
				return classes[0].name

		return None


@frappe.whitelist()
def get_events(start, end, filters=None):
	"""Returns events for Calendar view"""
	if not frappe.has_permission("Course Schedule", "read"):
		raise frappe.PermissionError

	if filters:
		filters = frappe.parse_json(filters)

	if not isinstance(filters, dict):
		filters = {}

	# Filter by date range
	filters["schedule_date"] = ["between", [start, end]]

	events = frappe.get_list(
		"Course Schedule",
		fields=[
			"name",
			"class_name",
			"course",
			"instructor_name",
			"room",
			"schedule_date",
			"from_time",
			"to_time",
			"color",
			"class_schedule_color",
		],
		filters=filters,
	)

	result = []
	for e in events:
		# Construct title
		title = e.course
		if e.room:
			title += f" ({e.room})"

		# Handle color
		color = e.color or e.class_schedule_color

		# Construct datetimes
		start_dt = f"{e.schedule_date} {e.from_time}"
		end_dt = f"{e.schedule_date} {e.to_time}"

		result.append(
			{
				"name": e.name,
				"doctype": "Course Schedule",
				"start": start_dt,
				"end": end_dt,
				"title": title,
				"allDay": 0,
				"color": color,
			}
		)

	return result
