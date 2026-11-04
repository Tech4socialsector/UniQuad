frappe.query_reports["Payment Settlement Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 0,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 0,
		},
		{
			fieldname: "payment_gateway",
			label: __("Payment Gateway"),
			fieldtype: "Select",
			options: "\nRazorpay\nEasebuzz",
			reqd: 0,
		},
		{
			fieldname: "settlement_status",
			label: __("Settlement Status"),
			fieldtype: "Select",
			options: "\nSettled\nProcessing\nNot settled yet\nFailed",
			reqd: 0,
		}
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "settlement_status" && data) {
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

		if (frappe.user.has_role(["System Manager", "Accounts Manager"])) {
			report.page.add_inner_button(__("Sync Easebuzz Settlements"), function () {
				const f = report.get_values() || {};
				frappe.call({
					method: "slcm.slcm.fee.easebuzz_settlement.sync_dates",
					args: {
						from_date: f.from_date || frappe.datetime.add_days(frappe.datetime.get_today(), -10),
						to_date: f.to_date && f.to_date < frappe.datetime.get_today() ? f.to_date : frappe.datetime.get_today(),
					},
					freeze: true,
					freeze_message: __("Reading Easebuzz payouts..."),
					callback: function (r) {
						if (r.message) {
							frappe.show_alert({
								message: __("{0} payment(s) settled, {1} already up to date.", [r.message.settled, r.message.unchanged]),
								indicator: "green",
							});
							report.refresh();
						}
					},
				});
			});
		}
	}
};
