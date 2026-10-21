import frappe
from frappe import _

def execute(filters=None):
	if not filters:
		filters = {}
		
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	
	return columns, data, None, chart

def get_columns():
	return [
		{
			"label": _("Marketing Source"),
			"fieldname": "source_of_information",
			"fieldtype": "Data",
			"width": 300
		},
		{
			"label": _("Total Applications"),
			"fieldname": "total_applications",
			"fieldtype": "Int",
			"width": 150
		}
	]

def get_data(filters):
	conditions = []
	values = {}
	
	if filters.get("source_of_information"):
		conditions.append("source_of_information = %(source_of_information)s")
		values["source_of_information"] = filters.get("source_of_information")
		
	where_clause = ""
	if conditions:
		where_clause = " AND " + " AND ".join(conditions)
		
	query = f"""
		SELECT 
			IFNULL(NULLIF(source_of_information, ''), 'Not Specified') as source_of_information, 
			COUNT(name) as total_applications
		FROM `tabApplicant`
		WHERE docstatus < 2
		{where_clause}
		GROUP BY IFNULL(NULLIF(source_of_information, ''), 'Not Specified')
		ORDER BY total_applications DESC
	"""
	
	return frappe.db.sql(query, values, as_dict=True)

def get_chart(data):
	if not data:
		return None
		
	labels = []
	values = []
	
	for row in data:
		labels.append(row.source_of_information)
		values.append(row.total_applications)
		
	colors = ["#4f46e5", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#06b6d4", "#64748b"]
	chart_colors = [colors[i % len(colors)] for i in range(len(labels))]

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": _("Applications"),
					"values": values
				}
			]
		},
		"type": "bar",
		"colors": chart_colors
	}
