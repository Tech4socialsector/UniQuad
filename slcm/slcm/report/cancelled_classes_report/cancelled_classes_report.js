frappe.query_reports["Cancelled Classes Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "programme",
			label: __("Programme"),
			fieldtype: "Link",
			options: "Programme",
		},
		{
			fieldname: "academic_term",
			label: __("Academic Term"),
			fieldtype: "Link",
			options: "Academic Term",
		},
		{
			fieldname: "class_name",
			label: __("Class"),
			fieldtype: "Link",
			options: "Classes",
			get_query: () => {
				const programme = frappe.query_report.get_filter_value("programme");
				return programme ? { filters: { programme } } : {};
			},
		},
	],
};
