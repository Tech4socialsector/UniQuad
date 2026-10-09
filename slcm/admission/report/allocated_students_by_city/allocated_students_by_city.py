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
		_("Allocated student counts grouped by city.")
		if data
		else _("No allocated students found.")
	)

	chart = get_chart_data(data)

	return columns, data, message, chart, summary


def get_columns() -> list[dict]:
	return [
		{
			"label": _("City"),
			"fieldname": "city",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Number of Centres"),
			"fieldname": "centre_count",
			"fieldtype": "Int",
			"width": 160,
		},
		{
			"label": _("Allocated Count"),
			"fieldname": "allocated_count",
			"fieldtype": "Int",
			"width": 160,
		},
	]


def get_chart_data(data: list[dict]) -> dict | None:
	if not data:
		return None

	# Exclude the "International Applicant" bucket from the chart (no real city)
	chart_rows = [r for r in data if r.get("city") != "International Applicant"]

	labels = [r["city"] for r in chart_rows]
	values = [r["allocated_count"] for r in chart_rows]

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": _("Allocated Count"),
					"values": values,
				}
			],
		},
		"type": "bar",
		"barOptions": {"horizontal": True, "stacked": False},
		"height": max(280, len(chart_rows) * 28 + 80),
		"colors": ["#2490EF"],
	}


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

	conditions = ["alloc.docstatus < 2"]
	values = {}

	if filters.get("is_international_applicant") or filters.get("show_international_applicant"):
		conditions.append(
			"(alloc.is_international_applicant = 1 OR alloc.entrance_test_provider = 'International Applicant' OR alloc.entrance_test_provider IS NULL OR alloc.entrance_test_provider = '')"
		)
	elif provider_filter:
		conditions.append(
			"(alloc.entrance_test_provider = %(provider)s OR alloc.re_entrance_test_provider = %(provider)s)"
		)
		values["provider"] = provider_filter

	if filters.get("academic_year"):
		conditions.append("alloc.academic_year = %(academic_year)s")
		values["academic_year"] = filters.get("academic_year")

	if filters.get("admission_cycle"):
		conditions.append("alloc.admission_cycle = %(admission_cycle)s")
		values["admission_cycle"] = filters.get("admission_cycle")

	if filters.get("campus"):
		conditions.append("alloc.campus = %(campus)s")
		values["campus"] = filters.get("campus")

	if filters.get("program_level"):
		conditions.append("alloc.program_level = %(program_level)s")
		values["program_level"] = filters.get("program_level")

	if filters.get("program"):
		conditions.append("alloc.program = %(program)s")
		values["program"] = filters.get("program")

	if filters.get("entrance_test_list"):
		conditions.append("alloc.entrance_test_list = %(entrance_test_list)s")
		values["entrance_test_list"] = filters.get("entrance_test_list")

	if filters.get("allocation_date"):
		conditions.append("alloc.allocation_date = %(allocation_date)s")
		values["allocation_date"] = filters.get("allocation_date")

	where_clause = " AND ".join(conditions)

	# effective_provider = re_entrance_test_provider when rescheduled, else entrance_test_provider.
	# City is fetched by joining Entrance Test Provider on that effective provider name.
	# Applicants with no provider (international) are grouped under 'International Applicant'.
	records = frappe.db.sql(
		f"""
		SELECT
			IFNULL(
				NULLIF(prov.city, ''),
				'International Applicant'
			) AS city,
			COUNT(DISTINCT prov.name) AS centre_count,
			COUNT(alloc.name) AS allocated_count
		FROM `tabEntrance Test Seat Allocation` alloc
		LEFT JOIN `tabEntrance Test Provider` prov
			ON prov.name = IFNULL(
				NULLIF(
					IF(
						alloc.is_rescheduled = 1
						AND alloc.re_entrance_test_provider IS NOT NULL
						AND alloc.re_entrance_test_provider != '',
						alloc.re_entrance_test_provider,
						alloc.entrance_test_provider
					),
					''
				),
				NULL
			)
		WHERE {where_clause}
		GROUP BY city
		ORDER BY allocated_count DESC
		""",
		values,
		as_dict=True,
	)

	return records
