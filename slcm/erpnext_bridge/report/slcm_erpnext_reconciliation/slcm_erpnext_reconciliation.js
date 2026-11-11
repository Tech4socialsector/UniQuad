// Copyright (c) 2026, Azim Premji Foundation and contributors
// For license information, please see license.txt

frappe.query_reports["SLCM ERPNext Reconciliation"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: window.erpnext?.utils
				? erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1]
				: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "source",
			label: __("SLCM Type"),
			fieldtype: "Select",
			options: [
				"",
				"Fee Payment",
				"Fee Refund",
				"Applicant Payment Receipt",
				"PACE Receipt",
				"FLE Payment Log",
				"Stipend Payment",
				"Refund Transaction",
				"Re Exam Payment Log",
				"Improvement Exam Payment Log",
				"Mess Payment",
				"Hostel Refund Request",
				"Gateway Receipt",
				"SLCM Payment Request",
				"FLE Settlement",
				"Student Credit Note",
			],
		},
		{
			fieldname: "student",
			label: __("Student"),
			fieldtype: "Link",
			options: "Student Master",
		},
		{
			fieldname: "only_exceptions",
			label: __("Only Exceptions"),
			fieldtype: "Check",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "remark" && data) {
			const color = data.exception ? "var(--red-600)" : "var(--green-600)";
			value = `<span style="color:${color}">${value}</span>`;
		}
		return value;
	},
	onload(report) {
		report.page.add_inner_button(__("Post Pending Now"), () =>
			frappe
				.call("slcm.erpnext_bridge.company.post_pending_now")
				.then((r) => frappe.show_alert({ message: r.message, indicator: "green" }))
		);
		report.page.add_inner_button(__("Re-post Document"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Re-post an SLCM document whose Journal Entry was cancelled in ERPNext"),
				fields: [
					{
						fieldname: "reference_doctype",
						label: __("SLCM Type"),
						fieldtype: "Select",
						options: [
							"Fee Payment",
							"Fee Refund",
							"Applicant Payment Receipt",
							"PACE Receipt",
							"FLE Payment Log",
							"Stipend Payment",
							"Refund Transaction",
							"Re Exam Payment Log",
							"Improvement Exam Payment Log",
							"Mess Payment",
							"Hostel Refund Request",
							"Gateway Receipt",
							"SLCM Payment Request",
							"Student Credit Note",
						],
						reqd: 1,
						// a Gateway Receipt is posted for an SLCM Payment Request
						onchange: () =>
							d.set_value(
								"link_doctype",
								d.get_value("reference_doctype") === "Gateway Receipt"
									? "SLCM Payment Request"
									: d.get_value("reference_doctype")
							),
					},
					{ fieldname: "link_doctype", fieldtype: "Data", hidden: 1 },
					{
						fieldname: "reference_name",
						label: __("SLCM Document"),
						fieldtype: "Dynamic Link",
						options: "link_doctype",
						reqd: 1,
					},
				],
				primary_action_label: __("Re-post"),
				primary_action(values) {
					const args = { reference_doctype: values.reference_doctype, reference_name: values.reference_name };
					frappe
						.call({ method: "slcm.erpnext_bridge.company.repost", args, freeze: true })
						.then((r) => {
							d.hide();
							frappe.show_alert({ message: __("Result: {0}", [r.message]), indicator: "green" });
							report.refresh();
						});
				},
			});
			d.show();
		});
	},
};
