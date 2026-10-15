# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters: dict | None = None):
	if filters is None:
		filters = {}

	columns = get_columns()
	data = get_data(filters)

	total_allocated = sum(d.get("allocated_count", 0) for d in data)

	summary = [
		{
			"label": _("Total Allocated Applicants"),
			"value": total_allocated,
			"indicator": "Blue",
			"datatype": "Int",
		}
	]

	message = (
		_("Allocated applicant counts by programme.")
		if data
		else _("No allocated applicants found.")
	)

	return columns, data, message, None, summary


def get_columns() -> list[dict]:
	return [
		{
			"label": _("Programme Name"),
			"fieldname": "program",
			"fieldtype": "Data",
			"width": 250,
		},
		{
			"label": _("Programme ID"),
			"fieldname": "program_id",
			"fieldtype": "Link",
			"options": "Programme",
			"width": 220,
		},
		{
			"label": _("Academic Year"),
			"fieldname": "academic_year",
			"fieldtype": "Link",
			"options": "Academic Year",
			"width": 150,
		},
		{
			"label": _("Admission Cycle"),
			"fieldname": "admission_cycle",
			"fieldtype": "Link",
			"options": "Admission Cycle",
			"width": 150,
		},
		{
			"label": _("Allocated Count"),
			"fieldname": "allocated_count",
			"fieldtype": "Int",
			"width": 160,
		},
	]


def get_data(filters: dict) -> list[dict]:
	user = frappe.session.user
	roles = frappe.get_roles(user)

	provider_filter = None
	if (
		"Entrance Test Provider" in roles
		and "System Manager" not in roles
		and "Entrance Test Admin" not in roles
		and user != "Administrator"
	):
		provider_name = frappe.db.get_value("Entrance Test Provider", {"user": user}, "name")
		if not provider_name:
			return []
		provider_filter = provider_name
	elif filters.get("entrance_test_provider"):
		provider_filter = filters.get("entrance_test_provider")

	conditions = ["sa.docstatus < 2"]
	values = {}

	if filters.get("is_international_applicant") or filters.get("show_international_applicant"):
		conditions.append(
			"(sa.is_international_applicant = 1 OR sa.entrance_test_provider = 'International Applicant' OR sa.entrance_test_provider IS NULL OR sa.entrance_test_provider = '')"
		)
	elif provider_filter:
		conditions.append(
			"(sa.entrance_test_provider = %(provider)s OR sa.re_entrance_test_provider = %(provider)s)"
		)
		values["provider"] = provider_filter

	if filters.get("academic_year"):
		conditions.append("sa.academic_year = %(academic_year)s")
		values["academic_year"] = filters.get("academic_year")

	if filters.get("admission_cycle"):
		conditions.append("sa.admission_cycle = %(admission_cycle)s")
		values["admission_cycle"] = filters.get("admission_cycle")

	if filters.get("campus"):
		conditions.append("sa.campus = %(campus)s")
		values["campus"] = filters.get("campus")

	if filters.get("program_level"):
		conditions.append("sa.program_level = %(program_level)s")
		values["program_level"] = filters.get("program_level")

	if filters.get("program"):
		conditions.append("(sa.program = %(program)s OR p.program_name = %(program)s)")
		values["program"] = filters.get("program")

	if filters.get("entrance_test_list"):
		conditions.append("sa.entrance_test_list = %(entrance_test_list)s")
		values["entrance_test_list"] = filters.get("entrance_test_list")

	if filters.get("allocation_date"):
		conditions.append("sa.allocation_date = %(allocation_date)s")
		values["allocation_date"] = filters.get("allocation_date")

	where_clause = " AND ".join(conditions)

	records = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(p.program_name, ''), sa.program) AS program,
			COALESCE(NULLIF(p.program_name, ''), sa.program) AS program_name,
			COALESCE(MAX(sa.program), '') AS program_id,
			COALESCE(MAX(sa.academic_year), '') AS academic_year,
			COALESCE(MAX(sa.admission_cycle), '') AS admission_cycle,
			COUNT(sa.name) AS allocated_count
		FROM `tabEntrance Test Seat Allocation` sa
		LEFT JOIN `tabProgramme` p ON sa.program = p.name
		WHERE {where_clause}
		GROUP BY COALESCE(NULLIF(p.program_name, ''), sa.program)
		ORDER BY allocated_count DESC
		""",
		values,
		as_dict=True,
	)

	return records
