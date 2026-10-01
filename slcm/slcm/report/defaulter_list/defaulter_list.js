frappe.query_reports["Defaulter List"] = {
	filters: [
		{
			fieldname: "academic_year",
			label: __("Academic Year"),
			fieldtype: "Link",
			options: "Academic Year",
		},
		{
			fieldname: "demand_type",
			label: __("Demand Type"),
			fieldtype: "Select",
			options: "\nAcademic\nNon Academic",
		},
		{
			fieldname: "student",
			label: __("Student"),
			fieldtype: "Link",
			options: "Student Master",
		},
		{
			fieldname: "as_of_date",
			label: __("As of Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
