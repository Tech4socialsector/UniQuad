// Copyright (c) 2026, Tech4socialsector and contributors
// For license information, please see license.txt

frappe.query_reports["PACE Daily Application Status Summary"] = {
	"filters": [
		{
			"fieldname": "academic_year",
			"label": __("Academic Year"),
			"fieldtype": "Link",
			"options": "Academic Year"
		},
		{
			"fieldname": "programme",
			"label": __("Programme"),
			"fieldtype": "Link",
			"options": "PACE Programme"
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "date",
			"label": __("Specific Date"),
			"fieldtype": "Date",
			"on_change": function() {
				frappe.query_report.refresh();
			}
		}
	],
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "status") {
			if (value === __("Enrolled") || value === __("Admitted")) {
				value = `<span style="color: #27ae60; font-weight: bold; background-color: #e8f8f5; padding: 3px 8px; border-radius: 12px; display: inline-block;">${value}</span>`;
			} else if (value === __("Verified") || value === __("Fee Paid")) {
				value = `<span style="color: #2980b9; font-weight: bold; background-color: #ebf5fb; padding: 3px 8px; border-radius: 12px; display: inline-block;">${value}</span>`;
			} else if (value === __("Under Verification") || value === __("Submitted")) {
				value = `<span style="color: #d35400; font-weight: bold; background-color: #fef5e7; padding: 3px 8px; border-radius: 12px; display: inline-block;">${value}</span>`;
			} else if (value === __("Returned for Correction") || value === __("Rejected")) {
				value = `<span style="color: #c0392b; font-weight: bold; background-color: #fdedec; padding: 3px 8px; border-radius: 12px; display: inline-block;">${value}</span>`;
			} else if (value === __("Draft")) {
				value = `<span style="color: #7f8c8d; font-weight: bold; background-color: #f4f6f7; padding: 3px 8px; border-radius: 12px; display: inline-block;">${value}</span>`;
			}
		}

		if (column.fieldname === "fee_status") {
			if (value === __("Paid")) {
				value = `<span style="color: #27ae60; font-weight: bold;">✓ ${value}</span>`;
			} else if (value === __("Partially Paid")) {
				value = `<span style="color: #f39c12; font-weight: bold;">⚡ ${value}</span>`;
			} else if (value === __("Pending")) {
				value = `<span style="color: #e74c3c; font-weight: bold;">⏳ ${value}</span>`;
			}
		}

		return value;
	},
	"onload": function(report) {
		// Add prominent Export to Excel button
		report.page.add_inner_button(__("Export to Excel"), function() {
			let visible_idx = report.get_validated_visible_indexes() || [];
			const filters = report.get_filter_values(true);
			const applied_filters = report.get_applied_filters(filters);

			const ignore_visible_idx =
				visible_idx.length ===
				report.data.length - ((report.raw_data && report.raw_data.add_total_row) ? 1 : 0);
			visible_idx = ignore_visible_idx ? [] : visible_idx;

			const args = {
				cmd: "frappe.desk.query_report.export_query",
				report_name: report.report_name,
				custom_columns: report.custom_columns?.length ? report.custom_columns : [],
				file_format_type: "Excel",
				filters: filters,
				applied_filters: applied_filters,
				visible_idx: visible_idx,
				ignore_visible_idx: ignore_visible_idx,
				include_indentation: 0,
				include_filters: 0,
				export_in_background: 0,
				include_hidden_columns: 0,
			};

			frappe.show_progress(__("Exporting to Excel"), 20, 100, __("Preparing report data..."));
			
			setTimeout(() => {
				frappe.show_progress(__("Exporting to Excel"), 60, 100, __("Generating Excel spreadsheet..."));
			}, 500);

			setTimeout(() => {
				frappe.show_progress(__("Exporting to Excel"), 100, 100, __("Download Started!"));
				open_url_post(frappe.request.url, args);

				setTimeout(() => {
					frappe.hide_progress();
				}, 1000);
			}, 1200);
		});
	}
};
