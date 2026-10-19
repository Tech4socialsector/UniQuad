# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import re
import frappe
from frappe import _


def execute(filters: dict | None = None):
	if filters is None:
		filters = {}

	data, program_fields = get_data(filters)
	columns = get_columns(program_fields)

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
		_("Allocated student counts grouped by city and programme.")
		if data
		else _("No allocated students found.")
	)

	chart = get_chart_data(data, program_fields)

	return columns, data, message, chart, summary


def get_columns(program_fields: list[dict] | None = None) -> list[dict]:
	columns = [
		{
			"label": _("City"),
			"fieldname": "city",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Number of Centres"),
			"fieldname": "centre_count",
			"fieldtype": "Int",
			"width": 140,
		},
	]

	if program_fields:
		for p in program_fields:
			columns.append(
				{
					"label": _(p["label"]),
					"fieldname": p["fieldname"],
					"fieldtype": "Int",
					"width": 160,
				}
			)

	columns.append(
		{
			"label": _("Total Allocated Count"),
			"fieldname": "allocated_count",
			"fieldtype": "Int",
			"width": 160,
		}
	)

	return columns


def get_chart_data(data: list[dict], program_fields: list[dict] | None = None) -> dict | None:
	if not data:
		return None

	# Exclude the "International Applicant" bucket from the chart (no real city)
	chart_rows = [r for r in data if r.get("city") != "International Applicant"]
	if not chart_rows:
		return None

	labels = [r["city"] for r in chart_rows]

	# Filter programme fields to only those that have at least one allocated student in chart rows
	active_programs = []
	if program_fields:
		for p in program_fields:
			if any(r.get(p["fieldname"], 0) > 0 for r in chart_rows):
				active_programs.append(p)

	if active_programs:
		datasets = [
			{
				"name": p["label"],
				"values": [r.get(p["fieldname"], 0) for r in chart_rows],
			}
			for p in active_programs
		]
	else:
		datasets = [
			{
				"name": _("Allocated Count"),
				"values": [r.get("allocated_count", 0) for r in chart_rows],
			}
		]

	palette = [
		"#2490EF",
		"#48C774",
		"#FF9F43",
		"#EA5455",
		"#7367F0",
		"#1E9FF2",
		"#10AC84",
		"#EE5253",
		"#F368E0",
		"#00D2D3",
		"#6C5CE7",
		"#FFA502",
	]

	return {
		"data": {
			"labels": labels,
			"datasets": datasets,
		},
		"type": "bar",
		"barOptions": {
			"stacked": True,
			"spaceRatio": 0.3,
		},
		"height": 360,
		"colors": palette[: max(1, len(datasets))],
		"axisOptions": {
			"xAxisMode": "span",
			"seriesLabelSpaceRatio": 5,
		},
	}


def get_data(filters: dict) -> tuple[list[dict], list[dict]]:
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
			return [], []
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

	# Fetch raw allocation counts grouped by city, program, and provider (centre)
	records = frappe.db.sql(
		f"""
		SELECT
			IFNULL(
				NULLIF(prov.city, ''),
				'International Applicant'
			) AS city,
			IFNULL(
				NULLIF(alloc.program, ''),
				'Unassigned'
			) AS program,
			prov.name AS provider_name,
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
		GROUP BY city, alloc.program, prov.name
		""",
		values,
		as_dict=True,
	)

	if not records:
		return [], []

	# Map programmes to human-readable names and clean labels for chart legend
	prog_names = sorted(list({r["program"] for r in records if r.get("program")}))
	prog_details = frappe.db.sql(
		"SELECT name, program_name, program_code FROM `tabProgramme`",
		as_dict=True,
	)
	prog_info_map = {p["name"]: p for p in prog_details}

	program_fields = []
	used_fieldnames = set()
	for p in prog_names:
		info = prog_info_map.get(p, {})
		p_name = info.get("program_name") or p
		p_code = info.get("program_code") or ""

		if "public policy" in p.lower() or "public policy" in p_name.lower():
			label = "MPP"
		elif p_name and 2 <= len(p_name) <= 14:
			label = p_name
		elif p_code and 2 <= len(p_code) <= 12:
			label = p_code
		elif p_name:
			clean = re.sub(r"-\d{4}\s*-\s*\d{4}.*$", "", p_name).strip()
			label = clean
		else:
			label = p

		slug = re.sub(r"[^a-zA-Z0-9_]+", "_", p).strip("_").lower()
		fieldname = f"prog_{slug[:35]}"
		if fieldname in used_fieldnames:
			idx = 2
			while f"{fieldname}_{idx}" in used_fieldnames:
				idx += 1
			fieldname = f"{fieldname}_{idx}"
		used_fieldnames.add(fieldname)
		program_fields.append({
			"program": p,
			"label": label,
			"full_name": p_name,
			"fieldname": fieldname,
		})

	# Group records per city
	city_map = {}
	for r in records:
		c = r["city"]
		if c not in city_map:
			city_map[c] = {
				"city": c,
				"centre_names": set(),
				"total": 0,
				"prog_counts": {},
			}
		if r.get("provider_name"):
			city_map[c]["centre_names"].add(r["provider_name"])
		cnt = r.get("allocated_count", 0)
		city_map[c]["total"] += cnt
		p = r["program"]
		city_map[c]["prog_counts"][p] = city_map[c]["prog_counts"].get(p, 0) + cnt

	# Build tabular rows
	data = []
	for c, info in city_map.items():
		row = {
			"city": c,
			"centre_count": len(info["centre_names"]),
			"allocated_count": info["total"],
		}
		for pf in program_fields:
			row[pf["fieldname"]] = info["prog_counts"].get(pf["program"], 0)
		data.append(row)

	data.sort(key=lambda x: x["allocated_count"], reverse=True)

	return data, program_fields
