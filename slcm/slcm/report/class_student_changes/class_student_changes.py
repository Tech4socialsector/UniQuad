# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Students added to, removed from or changed in status in Classes after the
class was created (Class Student Log), across classes."""

import frappe
from frappe import _
from frappe.utils import add_days, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.from_date and filters.to_date and getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Changed On"), "fieldname": "changed_on", "fieldtype": "Datetime", "width": 160},
		{"label": _("Action"), "fieldname": "action", "fieldtype": "Data", "width": 120},
		{"label": _("Student ID"), "fieldname": "student_enrollment", "fieldtype": "Link", "options": "Student Enrollment", "width": 150},
		{"label": _("Student Name"), "fieldname": "student_name", "fieldtype": "Data", "width": 180},
		{"label": _("From Status"), "fieldname": "from_status", "fieldtype": "Data", "width": 100},
		{"label": _("To Status"), "fieldname": "to_status", "fieldtype": "Data", "width": 100},
		{"label": _("Class"), "fieldname": "class_name", "fieldtype": "Link", "options": "Classes", "width": 170},
		{"label": _("Course"), "fieldname": "course", "fieldtype": "Link", "options": "Course", "width": 220},
		{"label": _("Section / Group"), "fieldname": "section_or_group", "fieldtype": "Data", "width": 110},
		{"label": _("Programme"), "fieldname": "programme", "fieldtype": "Link", "options": "Programme", "width": 200},
		{"label": _("Academic Term"), "fieldname": "academic_term", "fieldtype": "Link", "options": "Academic Term", "width": 170},
		{"label": _("Changed By"), "fieldname": "changed_by_name", "fieldtype": "Data", "width": 160},
	]


def get_data(filters):
	conditions = ["csl.parenttype = 'Classes'"]
	if filters.from_date:
		conditions.append("csl.changed_on >= %(from_date)s")
	if filters.to_date:
		filters.to_date_next = add_days(filters.to_date, 1)
		conditions.append("csl.changed_on < %(to_date_next)s")
	for field in ("academic_term", "programme", "course"):
		if filters.get(field):
			conditions.append(f"cl.{field} = %({field})s")
	if filters.class_name:
		conditions.append("cl.name = %(class_name)s")
	# Only classes the user may read (User Permissions apply)
	filters.readable = tuple(frappe.get_list("Classes", pluck="name", limit_page_length=0)) or ("",)
	conditions.append("cl.name IN %(readable)s")
	if filters.action:
		conditions.append("csl.action = %(action)s")
	if filters.student_enrollment:
		conditions.append("csl.student_enrollment = %(student_enrollment)s")

	rows = frappe.db.sql(
		f"""
		SELECT csl.changed_on, csl.action, csl.student_enrollment, csl.student_name,
			csl.from_status, csl.to_status, csl.changed_by,
			cl.name AS class_name, cl.course, cl.programme, cl.academic_term,
			IFNULL(cl.section, cl.group_name) AS section_or_group
		FROM `tabClass Student Log` csl
		INNER JOIN `tabClasses` cl ON cl.name = csl.parent
		WHERE {" AND ".join(conditions)}
		ORDER BY csl.changed_on DESC, csl.idx DESC
		""",
		filters,
		as_dict=True,
	)
	names = {u.name: u.full_name for u in frappe.get_all(
		"User", filters={"name": ["in", list({r.changed_by for r in rows if r.changed_by}) or [""]]},
		fields=["name", "full_name"],
	)}
	for r in rows:
		r.changed_by_name = names.get(r.changed_by) or r.changed_by
	return rows
