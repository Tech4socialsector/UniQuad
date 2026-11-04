const TT_STATUS_COLORS = { Scheduled: "blue", Completed: "green", Cancelled: "red", Swapped: "purple" };

frappe.query_reports["Time Table Report"] = {
	filters: [
		{
			fieldname: "time_table",
			label: __("ID"),
			fieldtype: "Data",
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
		{
			fieldname: "academic_year",
			label: __("Academic Year"),
			fieldtype: "Link",
			options: "Academic Year",
		},
		{
			fieldname: "academic_term",
			label: __("Academic Term"),
			fieldtype: "Link",
			options: "Academic Term",
		},
		{
			fieldname: "programme",
			label: __("Programme"),
			fieldtype: "Link",
			options: "Programme",
		},
		{
			fieldname: "course",
			label: __("Course"),
			fieldtype: "Link",
			options: "Course",
		},
		{
			fieldname: "instructor",
			label: __("Faculty"),
			fieldtype: "Link",
			options: "Faculty",
		},
		{
			fieldname: "section",
			label: __("Section"),
			fieldtype: "Link",
			options: "Section",
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
			fieldname: "based_on",
			label: __("Based On"),
			fieldtype: "Select",
			options: ["", "Class", "Time Table", "Office Hours"],
		},
		{
			fieldname: "session_status",
			label: __("Session Status"),
			fieldtype: "Select",
			options: ["", "Scheduled", "Completed", "Cancelled", "Swapped"],
		},
		{
			fieldname: "is_cancelled",
			label: __("Cancelled"),
			fieldtype: "Check",
		},
	],

	onload(report) {
		if (!frappe.model.can_export("Time Table")) return;
		const group = __("Export");
		report.page.add_inner_button(__("Excel"), () => export_time_table_report(report, "Excel"), group);
		report.page.add_inner_button(__("CSV"), () => export_time_table_report(report, "CSV"), group);
	},

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "session_status" && data && data.session_status) {
			const color = TT_STATUS_COLORS[data.session_status] || "gray";
			return `<span class="indicator-pill ${color}">${frappe.utils.escape_html(
				__(data.session_status)
			)}</span>`;
		}
		return default_formatter(value, row, column, data);
	},
};

// One-click export of exactly what is on screen: the report filters plus any
// column filters typed into the grid.
function export_time_table_report(report, file_format) {
	const visible_idx = report.datatable?.bodyRenderer.visibleRowIndices || [];
	if (!report.data?.length || !visible_idx.length) {
		frappe.msgprint(__("There are no records to export."));
		return;
	}

	report.make_access_log("Export", file_format);
	open_url_post(frappe.request.url, {
		cmd: "frappe.desk.query_report.export_query",
		report_name: report.report_name,
		custom_columns: [],
		file_format_type: file_format,
		filters: report.get_filter_values(true),
		visible_idx,
		csv_delimiter: ",",
		csv_quoting: 2, // csv.QUOTE_NONNUMERIC, Frappe's default
		csv_decimal_sep: ".",
		include_filters: 0,
		export_in_background: 0,
	});
}
