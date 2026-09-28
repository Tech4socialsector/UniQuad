// Copyright (c) 2026, Azim Premji Foundation and contributors
// For license information, please see license.txt

frappe.query_reports["Fee Payment Zoho Journal Upload"] = {
	ignore_prepared_report: true,

	filters: [
		{
			fieldname: "student",
			label: __("Student"),
			fieldtype: "Link",
			options: "Student Master"
		},
		{
			fieldname: "program",
			label: __("Programme"),
			fieldtype: "Link",
			options: "Programme Master"
		},
		{
			fieldname: "transaction_type",
			label: __("Transaction Type"),
			fieldtype: "Select",
			options: ["", "Online", "Offline"],
			default: ""
		},
		{
			fieldname: "from_date",
			label: __("From Date (Journal)"),
			fieldtype: "Date",
			default: frappe.datetime.month_start()
		},
		{
			fieldname: "to_date",
			label: __("To Date (Journal)"),
			fieldtype: "Date",
			default: frappe.datetime.month_end()
		},
		{
			fieldname: "from_settlement_date",
			label: __("From Settlement Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_settlement_date",
			label: __("To Settlement Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "export_mode",
			label: __("Export Mode / View"),
			fieldtype: "Select",
			options: ["Student Level", "Grouped"],
			default: "Student Level",
			on_change: function () { frappe.query_report.refresh(); }
		}
	],
	onload: function (report) {
		report.page.add_inner_button(__("Export with Filter"), function () {
			_fpzju_download(report, "Student Level");
		}, __("Export to Zoho Books"));
		
		report.page.add_inner_button(__("Student Level"), function () {
			_fpzju_download(report, "Student Level");
		}, __("Export to Zoho Books"));

		report.page.add_inner_button(__("Grouped"), function () {
			_fpzju_download(report, "Grouped");
		}, __("Export to Zoho Books"));
	}
};

function _fpzju_download(report, mode) {
	var filters = report.get_filter_values() || {};
	filters.export_mode = mode;

	frappe.call({
		method: "slcm.slcm.report.fee_payment_zoho_journal_upload.fee_payment_zoho_journal_upload.download_zoho_upload_file",
		args:   { filters: filters, file_format: "csv" },
		callback: function (r) {
			if (!r || !r.message || !r.message.content) {
				frappe.msgprint({
					title:     __("Export Failed"),
					message:   __("No data returned."),
					indicator: "red",
				});
				return;
			}
			var msg = r.message;
			var b64 = msg.content;
			var binary = atob(b64);
			var bytes  = new Uint8Array(binary.length);
			for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
			var blob = new Blob([bytes], { type: "text/csv" });
			var url  = URL.createObjectURL(blob);
			var a    = document.createElement("a");
			a.href = url; a.download = msg.filename;
			document.body.appendChild(a); a.click();
			document.body.removeChild(a); URL.revokeObjectURL(url);

			var bal_html = msg.balanced
				? `<span style="color:#2e7d32;font-weight:700;">&#10003; Balanced</span>`
				: `<span style="color:#c62828;font-weight:700;">&#10007; UNBALANCED</span>`;

			frappe.show_alert({
				message: __("&#10003; Downloaded <b>{0}</b> &mdash; {1} rows | {2}", [msg.filename, msg.row_count || 0, bal_html]),
				indicator: "green",
			}, 10);
		}
	});
}
