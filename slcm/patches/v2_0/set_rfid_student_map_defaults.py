# Copyright (c) 2026, Nishanth and contributors
"""Fill the new Student Map settings with their defaults once (Single DocType
fields added later are stored empty, and Check fields would read as 0)."""

import frappe

DEFAULTS = {
	"map_source_table": "personnel_employee",
	"map_code_column": "emp_code",
	"map_name_columns": "first_name,last_name",
	"map_student_field": "registration_id",
	"map_ignore_case": 1,
	"map_include_name_mismatch": 0,
}


def execute():
	dt = "RFID SQL Agent Settings"
	saved = {r.field for r in frappe.db.sql("SELECT field FROM `tabSingles` WHERE doctype = %s", dt, as_dict=True)}
	for field, value in DEFAULTS.items():
		if field not in saved or (field != "map_include_name_mismatch" and not frappe.db.get_single_value(dt, field)):
			frappe.db.set_single_value(dt, field, value)
