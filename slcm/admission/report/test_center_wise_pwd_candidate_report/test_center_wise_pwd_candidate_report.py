# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters: dict | None = None):
	if filters is None:
		filters = {}

	columns = get_columns()
	data = get_data(filters)

	total_candidates = len(data)
	pwd_count = sum(1 for d in data if d.get("is_pwd") == "Yes")
	scribe_required_total = sum(1 for d in data if d.get("pwd_required_test") == "Yes")

	nlsiu_scribe_count = 0
	self_scribe_count = 0
	for d in data:
		if d.get("pwd_required_test") == "Yes":
			details = str(d.get("scribe_details", "")).lower()
			if "myself" in details or "self" in details:
				self_scribe_count += 1
			else:
				nlsiu_scribe_count += 1
	attended_count = sum(1 for d in data if d.get("entrance_test_status") == "Attended")
	absent_count = sum(1 for d in data if d.get("entrance_test_status") == "Absent")

	summary = [
		{
			"label": _("Total Candidates"),
			"value": total_candidates,
			"indicator": "Blue",
			"datatype": "Int",
		},
		{
			"label": _("PWD Candidates"),
			"value": pwd_count,
			"indicator": "Purple",
			"datatype": "Int",
		},
		{
			"label": _("Scribe Required"),
			"value": scribe_required_total,
			"indicator": "Orange",
			"datatype": "Int",
		},
		{
			"label": _("University Scribe Required"),
			"value": nlsiu_scribe_count,
			"indicator": "Yellow",
			"datatype": "Int",
		},
		{
			"label": _("Self Scribe Arranged"),
			"value": self_scribe_count,
			"indicator": "Green",
			"datatype": "Int",
		},
		{
			"label": _("Attended"),
			"value": attended_count,
			"indicator": "Green",
			"datatype": "Int",
		},
		{
			"label": _("Absent"),
			"value": absent_count,
			"indicator": "Red",
			"datatype": "Int",
		},
	]

	message = (
		_("Test Center-wise PWD Candidate and Scribe Details Report.")
		if data
		else _("No candidates found matching the selected filters.")
	)

	chart = get_chart_data(data)

	return columns, data, message, chart, summary


def get_chart_data(data: list[dict]) -> dict | None:
	if not data:
		return None

	centre_map = {}
	for row in data:
		centre = row.get("test_centre") or _("Unknown")
		if centre not in centre_map:
			centre_map[centre] = {"univ_scribe": 0, "self_scribe": 0, "no_scribe": 0}

		req = row.get("pwd_required_test")
		details = str(row.get("scribe_details", "")).lower()

		if req == "Yes":
			if "myself" in details or "self" in details:
				centre_map[centre]["self_scribe"] += 1
			else:
				centre_map[centre]["univ_scribe"] += 1
		else:
			centre_map[centre]["no_scribe"] += 1

	sorted_centres = sorted(
		centre_map.keys(),
		key=lambda c: centre_map[c]["univ_scribe"] + centre_map[c]["self_scribe"] + centre_map[c]["no_scribe"],
		reverse=True,
	)[:15]

	labels = sorted_centres
	univ_vals = [centre_map[c]["univ_scribe"] for c in sorted_centres]
	self_vals = [centre_map[c]["self_scribe"] for c in sorted_centres]
	no_vals = [centre_map[c]["no_scribe"] for c in sorted_centres]

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": _("University Scribe Required"),
					"values": univ_vals,
				},
				{
					"name": _("Self Scribe Arranged"),
					"values": self_vals,
				},
				{
					"name": _("No Scribe Required"),
					"values": no_vals,
				},
			],
		},
		"type": "bar",
		"barOptions": {"stacked": True},
		"height": 300,
		"colors": ["#f39c12", "#27ae60", "#2980b9"],
	}


def get_columns() -> list[dict]:
	return [
		{
			"label": _("Sl No"),
			"fieldname": "sl_no",
			"fieldtype": "Int",
			"width": 70,
		},
		{
			"label": _("Test Centre"),
			"fieldname": "test_centre",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Programme"),
			"fieldname": "program",
			"fieldtype": "Link",
			"options": "Programme",
			"width": 220,
		},
		{
			"label": _("Admit Card Number"),
			"fieldname": "admit_card_number",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Applicant ID"),
			"fieldname": "applicant",
			"fieldtype": "Link",
			"options": "Applicant",
			"width": 140,
		},
		{
			"label": _("Student Name"),
			"fieldname": "candidate_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Is PWD?"),
			"fieldname": "is_pwd",
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"label": _("Scribe Required"),
			"fieldname": "pwd_required_test",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("Scribe Details"),
			"fieldname": "scribe_details",
			"fieldtype": "Data",
			"width": 300,
		},
		{
			"label": _("Attendance / Status"),
			"fieldname": "entrance_test_status",
			"fieldtype": "Data",
			"width": 130,
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

	conditions = ["sa.docstatus < 2", "(sa.pwd = 1 OR app.pwd = 'Yes')"]
	values = {}

	if filters.get("scribe_required_only"):
		conditions.append("(app.pwd_required_test = 'Yes' OR (app.scribe_allotment IS NOT NULL AND app.scribe_allotment != ''))")

	if filters.get("city"):
		conditions.append("(prov.city = %(city)s OR sa.center_name LIKE %(city_like)s OR sa.re_center_name LIKE %(city_like)s)")
		values["city"] = filters.get("city")
		values["city_like"] = f"%{filters.get('city')}%"

	if filters.get("is_international_applicant") or filters.get("show_international_applicant"):
		conditions.append(
			"(sa.is_international_applicant = 1 OR sa.entrance_test_provider = 'International Applicant' OR sa.entrance_test_provider IS NULL OR sa.entrance_test_provider = '')"
		)
	elif provider_filter:
		conditions.append(
			"(sa.entrance_test_provider = %(provider)s OR sa.re_entrance_test_provider = %(provider)s OR sa.center_name = %(provider)s OR sa.re_center_name = %(provider)s)"
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
		conditions.append("sa.program = %(program)s")
		values["program"] = filters.get("program")

	if filters.get("allocation_date"):
		conditions.append("sa.allocation_date = %(allocation_date)s")
		values["allocation_date"] = filters.get("allocation_date")

	if filters.get("entrance_test_status"):
		conditions.append("sa.entrance_test_status = %(entrance_test_status)s")
		values["entrance_test_status"] = filters.get("entrance_test_status")

	where_clause = " AND ".join(conditions)

	sql_query = f"""
		SELECT
			sa.name as sa_name,
			sa.applicant,
			sa.candidate_name,
			sa.program,
			sa.admit_card_number,
			sa.center_name,
			sa.re_center_name,
			sa.entrance_test_provider,
			sa.re_entrance_test_provider,
			sa.is_rescheduled,
			sa.pwd as sa_pwd,
			sa.entrance_test_status,
			app.pwd as app_pwd,
			app.pwd_required_test,
			app.scribe_allotment
		FROM `tabEntrance Test Seat Allocation` sa
		LEFT JOIN `tabApplicant` app ON sa.applicant = app.name
		LEFT JOIN `tabEntrance Test Provider` prov ON prov.name = IFNULL(
			NULLIF(
				IF(
					sa.is_rescheduled = 1
					AND sa.re_entrance_test_provider IS NOT NULL
					AND sa.re_entrance_test_provider != '',
					sa.re_entrance_test_provider,
					sa.entrance_test_provider
				),
				''
			),
			NULL
		)
		WHERE {where_clause}
		ORDER BY
			COALESCE(
				NULLIF(IF(sa.is_rescheduled = 1 AND sa.re_center_name IS NOT NULL AND sa.re_center_name != '', sa.re_center_name, sa.center_name), ''),
				NULLIF(IF(sa.is_rescheduled = 1 AND sa.re_entrance_test_provider IS NOT NULL AND sa.re_entrance_test_provider != '', sa.re_entrance_test_provider, sa.entrance_test_provider), ''),
				'International Applicant'
			) ASC,
			sa.candidate_name ASC
	"""

	records = frappe.db.sql(sql_query, values, as_dict=True)

	data = []
	for idx, r in enumerate(records, start=1):
		# Test centre determination
		if r.get("is_rescheduled") == 1 and (r.get("re_center_name") or r.get("re_entrance_test_provider")):
			centre = r.get("re_center_name") or r.get("re_entrance_test_provider")
		else:
			centre = r.get("center_name") or r.get("entrance_test_provider") or "International Applicant"

		# PWD status determination
		is_pwd_val = "Yes" if (r.get("sa_pwd") == 1 or (r.get("app_pwd") or "").strip().lower() == "yes") else "No"

		# Scribe details determination
		req_scribe = (r.get("pwd_required_test") or "").strip()
		allotment = (r.get("scribe_allotment") or "").strip()

		if req_scribe.lower() == "yes" or allotment:
			scribe_req_disp = "Yes"
			if allotment:
				scribe_info = allotment
			else:
				scribe_info = "Yes (Arrangement Not Specified)"
		elif req_scribe.lower() == "no":
			scribe_req_disp = "No"
			scribe_info = "No Scribe Required"
		else:
			scribe_req_disp = "Not Specified" if is_pwd_val == "Yes" else "No"
			scribe_info = "-" if is_pwd_val == "No" else "Not Specified"

		# Admit Card Number
		admit_card_no = r.get("admit_card_number") or f"AC-{r.get('applicant')}"

		data.append({
			"sl_no": idx,
			"test_centre": centre,
			"program": r.get("program"),
			"admit_card_number": admit_card_no,
			"applicant": r.get("applicant"),
			"candidate_name": r.get("candidate_name"),
			"is_pwd": is_pwd_val,
			"pwd_required_test": scribe_req_disp,
			"scribe_details": scribe_info,
			"entrance_test_status": r.get("entrance_test_status") or "Scheduled",
		})

	return data
