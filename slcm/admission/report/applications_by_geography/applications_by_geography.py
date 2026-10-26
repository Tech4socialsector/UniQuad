import frappe
from frappe import _

def execute(filters=None):
	if not filters:
		filters = {}
		
	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart(data, filters)
	summary = get_summary(data, filters)
	
	return columns, data, None, chart, summary

def get_columns(filters):
	if filters.get("state"):
		return [
			{
				"label": _("Country"),
				"fieldname": "country",
				"fieldtype": "Link",
				"options": "Country",
				"width": 140
			},
			{
				"label": _("State"),
				"fieldname": "state",
				"fieldtype": "Link",
				"options": "State",
				"width": 180
			},
			{
				"label": _("City"),
				"fieldname": "city",
				"fieldtype": "Data",
				"width": 180
			},
			{
				"label": _("Total Applications"),
				"fieldname": "total_applications",
				"fieldtype": "Int",
				"width": 160
			}
		]
	else:
		return [
			{
				"label": _("Country"),
				"fieldname": "country",
				"fieldtype": "Link",
				"options": "Country",
				"width": 150
			},
			{
				"label": _("State"),
				"fieldname": "state",
				"fieldtype": "Link",
				"options": "State",
				"width": 220
			},
			{
				"label": _("Total Applications"),
				"fieldname": "total_applications",
				"fieldtype": "Int",
				"width": 180
			}
		]

def get_data(filters):
	conditions = []
	values = {}
	
	if filters.get("country"):
		conditions.append("country = %(country)s")
		values["country"] = filters.get("country")
		
	if filters.get("state"):
		conditions.append("state = %(state)s")
		values["state"] = filters.get("state")

	if filters.get("academic_year"):
		conditions.append("academic_year = %(academic_year)s")
		values["academic_year"] = filters.get("academic_year")

	if filters.get("admission_cycle"):
		conditions.append("admission_cycle = %(admission_cycle)s")
		values["admission_cycle"] = filters.get("admission_cycle")

	if filters.get("program"):
		conditions.append("program = %(program)s")
		values["program"] = filters.get("program")
		
	where_clause = ""
	if conditions:
		where_clause = " AND " + " AND ".join(conditions)
		
	if filters.get("state"):
		query = f"""
			SELECT 
				IFNULL(NULLIF(country, ''), 'Unknown') as country, 
				IFNULL(NULLIF(state, ''), 'Unknown') as state, 
				IFNULL(NULLIF(city, ''), 'Not Specified') as city, 
				COUNT(name) as total_applications
			FROM `tabApplicant`
			WHERE docstatus < 2
			{where_clause}
			GROUP BY country, state, city
			ORDER BY total_applications DESC, city ASC
		"""
	else:
		query = f"""
			SELECT 
				IFNULL(NULLIF(country, ''), 'Unknown') as country, 
				IFNULL(NULLIF(state, ''), 'Unknown') as state, 
				COUNT(name) as total_applications
			FROM `tabApplicant`
			WHERE docstatus < 2
			{where_clause}
			GROUP BY country, state
			ORDER BY total_applications DESC, state ASC
		"""
	
	return frappe.db.sql(query, values, as_dict=True)

def get_chart(data, filters):
	if not data:
		return None
		
	labels = []
	values = []

	if filters.get("state"):
		for row in data[:25]:
			labels.append(row.city or _("Not Specified"))
			values.append(row.total_applications)
		dataset_name = _("Applications in {0}").format(filters.get("state"))
	else:
		for row in data[:25]:
			labels.append(row.state or _("Unknown"))
			values.append(row.total_applications)
		country_name = filters.get("country")
		if country_name:
			dataset_name = _("Applications in {0}").format(country_name)
		else:
			dataset_name = _("Applications by State")
		
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": dataset_name,
					"values": values
				}
			]
		},
		"type": "bar",
		"colors": ["#48C774"]
	}

def get_summary(data, filters):
	if not data:
		return []

	total_apps = sum(r.get("total_applications", 0) for r in data)
	
	if filters.get("state"):
		unique_cities = len([r for r in data if r.get("city") and r.get("city") != "Not Specified"])
		return [
			{
				"value": total_apps,
				"indicator": "Blue",
				"label": _("Total Applications"),
				"datatype": "Int"
			},
			{
				"value": unique_cities,
				"indicator": "Green",
				"label": _("Total Cities"),
				"datatype": "Int"
			}
		]
	else:
		unique_states = len([r for r in data if r.get("state") and r.get("state") != "Unknown"])
		return [
			{
				"value": total_apps,
				"indicator": "Blue",
				"label": _("Total Applications"),
				"datatype": "Int"
			},
			{
				"value": unique_states,
				"indicator": "Green",
				"label": _("Total States"),
				"datatype": "Int"
			}
		]

