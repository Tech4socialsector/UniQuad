// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.query_reports["Class Student Changes"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "academic_term", label: __("Academic Term"), fieldtype: "Link", options: "Academic Term" },
		{ fieldname: "programme", label: __("Programme"), fieldtype: "Link", options: "Programme" },
		{ fieldname: "course", label: __("Course"), fieldtype: "Link", options: "Course" },
		{ fieldname: "class_name", label: __("Class"), fieldtype: "Link", options: "Classes" },
		{ fieldname: "action", label: __("Action"), fieldtype: "Select", options: "\nAdded\nRemoved\nStatus Changed" },
		{ fieldname: "student_enrollment", label: __("Student ID"), fieldtype: "Link", options: "Student Enrollment" },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "action" && data) {
			const color = { Added: "green", Removed: "red", "Status Changed": "orange" }[data.action] || "gray";
			value = `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
};
