# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, getdate

from slcm.slcm.doctype.time_table.time_table import format_time_12h

# Report filter -> Time Table field, matched with "="
EQUALS_FILTERS = (
	"class_name",
	"academic_year",
	"academic_term",
	"programme",
	"course",
	"instructor",
	"section",
	"based_on",
	"session_status",
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.from_date and filters.to_date and getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))
	show_cancellation = is_cancelled_view(filters)
	return get_columns(show_cancellation), get_data(filters, show_cancellation)


def is_cancelled_view(filters):
	# Cancellation details only make sense when looking at cancelled classes
	return bool(cint(filters.is_cancelled)) or filters.session_status == "Cancelled"


def get_columns(show_cancellation=False):
	# Same columns as the Time Table list view
	columns = [
		{"label": _("ID"), "fieldname": "name", "fieldtype": "Link", "options": "Time Table", "width": 150},
		{"label": _("Status"), "fieldname": "session_status", "fieldtype": "Data", "width": 105},
		{"label": _("Based On"), "fieldname": "based_on", "fieldtype": "Data", "width": 105},
		{"label": _("Class"), "fieldname": "class_name", "fieldtype": "Link", "options": "Classes", "width": 190},
		{"label": _("Course"), "fieldname": "course", "fieldtype": "Link", "options": "Course", "width": 260},
		{"label": _("Faculty"), "fieldname": "faculty_name", "fieldtype": "Data", "width": 170},
		{"label": _("Schedule Date"), "fieldname": "schedule_date", "fieldtype": "Date", "width": 115},
		{"label": _("From Time"), "fieldname": "from_time", "fieldtype": "Data", "width": 95},
		{"label": _("To Time"), "fieldname": "to_time", "fieldtype": "Data", "width": 95},
		{"label": _("Section"), "fieldname": "section", "fieldtype": "Link", "options": "Section", "width": 100},
		{"label": _("Venue"), "fieldname": "venue", "fieldtype": "Link", "options": "Venue Master", "width": 120},
	]
	if show_cancellation:
		columns += [
			{"label": _("Cancellation Reason"), "fieldname": "cancellation_reason", "fieldtype": "Data", "width": 240},
			{"label": _("Cancelled By"), "fieldname": "cancelled_by", "fieldtype": "Link", "options": "User", "width": 180},
			{"label": _("Cancelled On"), "fieldname": "cancelled_on", "fieldtype": "Datetime", "width": 160},
		]
	return columns


def get_filters(filters):
	conditions = {"docstatus": ["<", 2]}
	if filters.time_table:
		conditions["name"] = ["like", f"%{filters.time_table.strip()}%"]
	for field in EQUALS_FILTERS:
		if filters.get(field):
			conditions[field] = filters.get(field)
	if cint(filters.is_cancelled):
		conditions["is_cancelled"] = 1

	if filters.from_date and filters.to_date:
		conditions["schedule_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.from_date:
		conditions["schedule_date"] = [">=", filters.from_date]
	elif filters.to_date:
		conditions["schedule_date"] = ["<=", filters.to_date]
	return conditions


def get_data(filters, show_cancellation=False):
	# get_list (not raw SQL) so the report honours the same permissions as the list view
	rows = frappe.get_list(
		"Time Table",
		filters=get_filters(filters),
		fields=[
			"name",
			"session_status",
			"based_on",
			"class_name",
			"course",
			"instructor",
			"instructor_name",
			"schedule_date",
			"from_time",
			"to_time",
			"section",
			"venue",
			"cancellation_reason",
		],
		order_by="schedule_date asc, from_time asc, name asc",
		limit_page_length=0,
	)

	# instructor_name is blank on older rows - fall back to the Faculty record
	missing = list({r.instructor for r in rows if r.instructor and not r.instructor_name})
	faculty_names = {}
	if missing:
		for f in frappe.get_all(
			"Faculty", filters={"name": ["in", missing]}, fields=["name", "first_name", "last_name"]
		):
			faculty_names[f.name] = " ".join(filter(None, [f.first_name, f.last_name]))

	# Who cancelled and when: the latest "Cancelled" entry of the Class Schedule Log
	logs = {}
	if show_cancellation and rows:
		for log in frappe.get_all(
			"Class Schedule Log",
			filters={"action": "Cancelled", "time_table": ["in", [r.name for r in rows]]},
			fields=["time_table", "changed_by", "changed_on"],
			order_by="changed_on asc",
		):
			logs[log.time_table] = log

	for r in rows:
		log = logs.get(r.name)
		if log:
			r.cancelled_by = log.changed_by
			r.cancelled_on = log.changed_on
		r.session_status = r.session_status or "Scheduled"
		r.faculty_name = r.instructor_name or faculty_names.get(r.instructor) or r.instructor
		r.from_time = format_time_12h(r.from_time) if r.from_time else ""
		r.to_time = format_time_12h(r.to_time) if r.to_time else ""
	return rows
