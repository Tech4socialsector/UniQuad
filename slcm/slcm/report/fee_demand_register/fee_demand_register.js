frappe.query_reports["Fee Demand Register"] = {
	filters: [
		{
			fieldname: "academic_year",
			label: __("Academic Year"),
			fieldtype: "Link",
			options: "Academic Year",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nPending\nPartially Paid\nPaid\nOverdue\nWaived\nMoved to Excess\nCancelled",
		},
		{
			fieldname: "demand_type",
			label: __("Demand Type"),
			fieldtype: "Select",
			options: "\nAcademic\nNon Academic",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "student",
			label: __("Student"),
			fieldtype: "Link",
			options: "Student Master",
		},
	],
};
