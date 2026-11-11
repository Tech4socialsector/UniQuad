// Copyright (c) 2026, SLCM and contributors
// For license information, please see license.txt

frappe.query_reports["Student Admission Fee Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
		},
		{
			fieldname: "admission_cycle",
			label: __("Admission Cycle"),
			fieldtype: "Link",
			options: "Admission Cycle",
		},
		{
			fieldname: "admission_year",
			label: __("Admission Year"),
			fieldtype: "Link",
			options: "Admission Year",
		},
		{
			fieldname: "program",
			label: __("Programme"),
			fieldtype: "Link",
			options: "Programme",
		},
		{
			fieldname: "fee_component",
			label: __("Fee Component"),
			fieldtype: "Select",
			options: "\nConfirmation Fee\nAdmission Fee",
		},
		{
			fieldname: "status",
			label: __("Payment Status"),
			fieldtype: "Select",
			options: "\nPaid\nRequested\nFailed\nDraft\nCancelled",
		},
		{
			fieldname: "settlement_status",
			label: __("Settlement Status"),
			fieldtype: "Select",
			options: "\nSettled\nProcessing\nNot settled yet\nFailed",
		},
		{
			fieldname: "applicant",
			label: __("Applicant"),
			fieldtype: "Link",
			options: "Applicant",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "payment_status" && data.payment_status) {
			const color = { Paid: "green", Requested: "orange", Failed: "red", Cancelled: "grey" }[data.payment_status] || "grey";
			value = `<span class="indicator-pill ${color}">${value}</span>`;
		}
		if (column.fieldname === "settlement_status" && data.settlement_status) {
			const color = { Settled: "green", Processing: "blue", Failed: "red" }[data.settlement_status] || "orange";
			value = `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
	onload: function (report) {
		report.page.add_inner_button(__("Download Excel"), function () {
			frappe.query_report.export_report("Excel");
		}, __("Export"));
		report.page.add_inner_button(__("Download CSV"), function () {
			frappe.query_report.export_report("CSV");
		}, __("Export"));
	},
};
