// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.query_reports["Primary Program Choice"] = {
	filters: [
		{
			"fieldname": "admission_year",
			"label": __("Admission Year"),
			"fieldtype": "Link",
			"options": "Admission Year",
			"reqd": 1,
			"default": frappe.defaults.get_user_default("admission_year")
		},
		{
			"fieldname": "admission_cycle",
			"label": __("Admission Cycle"),
			"fieldtype": "Link",
			"options": "Admission Cycle"
		},
		{
			"fieldname": "program_level",
			"label": __("Program Level"),
			"fieldtype": "Select",
			"options": "\nUG\nPG\nResearch Course"
		},
		{
			"fieldname": "program",
			"label": __("Programme"),
			"fieldtype": "Link",
			"options": "Programme",
			"get_query": function () {
				var program_level = frappe.query_report.get_filter_value('program_level');
			}
		},
		{
			"fieldname": "campus",
			"label": __("Campus"),
			"fieldtype": "Link",
			"options": "Campus"
		},
		{
			"fieldname": "status",
			"label": __("Application Status"),
			"fieldtype": "Link",
			"options": "Applicant Status"
		}
	],
};
