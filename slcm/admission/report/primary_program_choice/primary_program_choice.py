import frappe
from frappe import _


def execute(filters: dict | None = None):
	"""Return columns and data for the report."""
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	report_summary = get_report_summary(data)

	return columns, data, None, chart, report_summary


def get_columns() -> list[dict]:
	"""Return columns for the report."""
	return [
		{
			"label": _("ID"),
			"fieldname": "applicant_id",
			"fieldtype": "Link",
			"options": "Applicant",
			"width": 140
		},
		{
			"label": _("Applicant Name"),
			"fieldname": "applicant_name",
			"fieldtype": "Data",
			"width": 180
		},
		{
			"label": _("Email"),
			"fieldname": "email",
			"fieldtype": "Data",
			"width": 180
		},
		{
			"label": _("Mobile"),
			"fieldname": "mobile_number",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("Program Level"),
			"fieldname": "program_level",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("Programme"),
			"fieldname": "program",
			"fieldtype": "Data",
			"width": 180
		},
		{
			"label": _("Campus"),
			"fieldname": "campus",
			"fieldtype": "Link",
			"options": "Campus",
			"width": 120
		},
		{
			"label": _("Application Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 140
		},
		{
			"label": _("Admission Year"),
			"fieldname": "admission_year",
			"fieldtype": "Link",
			"options": "Admission Year",
			"width": 120
		}
	]


def get_data(filters: dict | None) -> list[dict]:
	"""Return data for the report based on filters."""
	query_filters = {"docstatus": ["<", 2]}
	
	if not filters:
		filters = {}

	if filters.get("admission_year"):
		query_filters["admission_year"] = filters.get("admission_year")
	if filters.get("admission_cycle"):
		query_filters["admission_cycle"] = filters.get("admission_cycle")
	if filters.get("program"):
		query_filters["program"] = filters.get("program")
	if filters.get("program_level"):
		query_filters["program_level"] = filters.get("program_level")
	if filters.get("status"):
		query_filters["status"] = filters.get("status")
	if filters.get("campus"):
		query_filters["campus"] = filters.get("campus")

	data = frappe.get_all(
		"Applicant",
		filters=query_filters,
		fields=[
			"name as applicant_id",
			"candidate_name as applicant_name",
			"email",
			"mobile_number",
			"program_level",
			"program",
			"program.program_name as program_name",
			"campus",
			"status",
			"admission_year",
			"admission_cycle"
		],
		order_by="program asc, applicant_id asc"
	)

	for row in data:
		if row.get("program_name"):
			row["program"] = row["program_name"]

	return data


def get_chart(data: list[dict]) -> dict:
	"""Return chart data."""
	if not data:
		return {}

	program_counts = {}
	for row in data:
		program = row.get("program") or _("Not Specified")
		program_counts[program] = program_counts.get(program, 0) + 1

	# Generate a list of colors for each program
	colors = ['#007bff', '#28a745', '#ffc107', '#dc3545', '#17a2b8', '#6610f2', '#e83e8c', '#fd7e14', '#20c997']
	chart_colors = [colors[i % len(colors)] for i in range(len(program_counts))]

	return {
		"data": {
			"labels": list(program_counts.keys()),
			"datasets": [{"name": _("Applicants"), "values": list(program_counts.values())}],
		},
		"type": "bar",
		"colors": chart_colors
	}


def get_report_summary(data: list[dict]) -> list[dict]:
	"""Return report summary."""
	if not data:
		return []

	return [
		{
			"value": len(data),
			"indicator": "Blue",
			"label": _("Total Applicants"),
			"datatype": "Int",
		}
	]
