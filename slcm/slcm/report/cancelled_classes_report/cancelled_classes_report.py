# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate

from slcm.slcm.doctype.time_table.time_table import format_time_12h


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("Select the From Date and To Date."))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "schedule_date", "fieldtype": "Date", "width": 105},
		{"label": _("From Time"), "fieldname": "from_time", "fieldtype": "Data", "width": 95},
		{"label": _("To Time"), "fieldname": "to_time", "fieldtype": "Data", "width": 95},
		{"label": _("Programme"), "fieldname": "programme", "fieldtype": "Link", "options": "Programme", "width": 220},
		{"label": _("Academic Term"), "fieldname": "academic_term", "fieldtype": "Link", "options": "Academic Term", "width": 120},
		{"label": _("Class"), "fieldname": "class_name", "fieldtype": "Link", "options": "Classes", "width": 160},
		{"label": _("Course"), "fieldname": "course", "fieldtype": "Link", "options": "Course", "width": 240},
		{"label": _("Section"), "fieldname": "section", "fieldtype": "Data", "width": 90},
		{"label": _("Faculty Name"), "fieldname": "faculty_name", "fieldtype": "Data", "width": 160},
		{"label": _("Venue"), "fieldname": "venue", "fieldtype": "Data", "width": 100},
		{"label": _("Cancellation Reason"), "fieldname": "cancellation_reason", "fieldtype": "Data", "width": 240},
		{"label": _("Cancelled By"), "fieldname": "cancelled_by", "fieldtype": "Data", "width": 180},
		{"label": _("Cancelled On"), "fieldname": "cancelled_on", "fieldtype": "Datetime", "width": 160},
		{"label": _("Time Table"), "fieldname": "time_table", "fieldtype": "Link", "options": "Time Table", "width": 140},
	]


def get_data(filters):
	conditions = ["tt.is_cancelled = 1", "tt.docstatus < 2", "tt.schedule_date BETWEEN %(from_date)s AND %(to_date)s"]
	for field in ("programme", "academic_term", "class_name"):
		if filters.get(field):
			conditions.append(f"tt.{field} = %({field})s")

	rows = frappe.db.sql(
		f"""
		SELECT
			tt.name AS time_table, tt.schedule_date, tt.from_time, tt.to_time,
			tt.programme, tt.academic_term, tt.class_name, tt.course, tt.section, tt.venue,
			tt.cancellation_reason,
			TRIM(CONCAT_WS(' ', f.first_name, f.last_name)) AS faculty_name
		FROM `tabTime Table` tt
		LEFT JOIN `tabFaculty` f ON f.name = tt.instructor
		WHERE {" AND ".join(conditions)}
		ORDER BY tt.programme, tt.schedule_date, tt.from_time
		""",
		filters,
		as_dict=True,
	)

	# Who cancelled and when: the latest "Cancelled" entry of the Class Schedule Log
	logs = {}
	if rows:
		for log in frappe.get_all(
			"Class Schedule Log",
			filters={"action": "Cancelled", "time_table": ["in", [r.time_table for r in rows]]},
			fields=["time_table", "changed_by", "changed_on"],
			order_by="changed_on asc",
		):
			logs[log.time_table] = log

	for r in rows:
		r.from_time = format_time_12h(r.from_time)
		r.to_time = format_time_12h(r.to_time)
		log = logs.get(r.time_table)
		if log:
			r.cancelled_by = log.changed_by
			r.cancelled_on = log.changed_on
	return rows
