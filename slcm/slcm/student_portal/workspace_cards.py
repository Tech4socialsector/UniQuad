"""Custom number cards for the Student Portal workspace.

These cards depend on today's date (live announcements, students on leave today),
which static Number Card filters can't express. Each returns the count plus a
list route whose filters match the count exactly, so clicking a card opens the
same records it counted. `frappe.get_list` applies the viewer's permissions.
"""

import frappe
from frappe.utils import today


def _card(doctype, names, route_options=None):
	return {
		"value": len(names),
		"fieldtype": "Int",
		"route": ["List", doctype],
		"route_options": route_options or {"name": ["in", names or [""]]},
	}


def _live_announcements(priority=None):
	filters = {"is_active": 1, "publish_date": ["<=", today()]}
	if priority:
		filters["priority"] = priority
	# expiry_date is optional; an empty one means the announcement never expires.
	names = frappe.get_list(
		"Student Announcement",
		filters=filters,
		or_filters=[["expiry_date", "is", "not set"], ["expiry_date", ">=", today()]],
		pluck="name",
	)
	return _card("Student Announcement", names)


@frappe.whitelist()
def live_announcements(filters=None):
	return _live_announcements()


@frappe.whitelist()
def urgent_announcements(filters=None):
	return _live_announcements(priority="Urgent")


@frappe.whitelist()
def students_on_leave_today(filters=None):
	on_date = today()
	filters = {"status": "Approved", "from_date": ["<=", on_date], "to_date": [">=", on_date]}
	names = frappe.get_list("Student Leave Applications", filters=filters, pluck="name")
	return _card("Student Leave Applications", names, route_options=filters)
