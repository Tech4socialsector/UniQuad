// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.query_reports["Test Center-wise Candidate Detail Report"] = {
	filters: [
		{
			fieldname: "entrance_test_provider",
			label: __("Entrance Test Provider / Test Centre"),
			fieldtype: "Link",
			options: "Entrance Test Provider"
		},
		{
			fieldname: "city",
			label: __("Test City"),
			fieldtype: "Link",
			options: "City"
		},
		{
			fieldname: "academic_year",
			label: __("Academic Year"),
			fieldtype: "Link",
			options: "Academic Year"
		},
		{
			fieldname: "admission_cycle",
			label: __("Admission Cycle"),
			fieldtype: "Link",
			options: "Admission Cycle"
		},
		{
			fieldname: "program_level",
			label: __("Programme Level"),
			fieldtype: "Select",
			options: "\nUndergraduate\nPostgraduate\nResearch Course"
		},
		{
			fieldname: "program",
			label: __("Programme"),
			fieldtype: "Link",
			options: "Programme"
		},
		{
			fieldname: "allocation_date",
			label: __("Entrance Test Date"),
			fieldtype: "Date"
		},
		{
			fieldname: "entrance_test_status",
			label: __("Attendance / Status"),
			fieldtype: "Select",
			options: "\nAttended\nAbsent\nScheduled\nRescheduled\nNot Scheduled"
		},
		{
			fieldname: "is_pwd_only",
			label: __("Is PWD Only"),
			fieldtype: "Check",
			default: 0
		},
		{
			fieldname: "scribe_required_only",
			label: __("Scribe Required Only"),
			fieldtype: "Check",
			default: 0
		}
	],
	onload: function(report) {
		// Scoping for Entrance Test Provider role
		if (frappe.user_roles.includes("Entrance Test Provider") &&
			!frappe.user_roles.includes("System Manager") &&
			!frappe.user_roles.includes("Entrance Test Admin")) {
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Entrance Test Provider",
					filters: { user: frappe.session.user },
					fieldname: "name"
				},
				callback: function(r) {
					if (r.message && r.message.name) {
						report.set_filter_value("entrance_test_provider", r.message.name);
						const field = report.get_filter("entrance_test_provider");
						if (field) {
							field.df.read_only = 1;
							field.refresh();
						}
					}
				}
			});
		}

		// Add custom Download button at the top
		const $dl_btn = report.page.add_inner_button(__("Download Excel"), function() {
			open_download_modal(report);
		});
		$dl_btn.addClass("btn-primary");
	}
};

function open_download_modal(report) {
	const filters = report.get_values() || {};
	const center_text = filters.entrance_test_provider || __("All Test Centres");
	const pwd_text = filters.is_pwd_only ? __("PWD Candidates Only") : __("All Applicants");
	const prog_text = filters.program || filters.program_level || __("All Programmes");

	const d = new frappe.ui.Dialog({
		title: __("Download Candidate Detail Report"),
		fields: [
			{
				fieldname: "summary_html",
				fieldtype: "HTML",
				options: `
					<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px 16px; margin-bottom: 16px; font-size: 13px;">
						<div style="font-weight: 600; color: #1e293b; margin-bottom: 8px;">${__("Active Filter Summary")}</div>
						<div style="display: grid; grid-template-columns: 140px 1fr; gap: 6px; color: #475569;">
							<div><b>${__("Test Centre")}:</b></div><div>${frappe.utils.escape_html(center_text)}</div>
							<div><b>${__("Programme")}:</b></div><div>${frappe.utils.escape_html(prog_text)}</div>
							<div><b>${__("Candidate Scope")}:</b></div><div>${frappe.utils.escape_html(pwd_text)}</div>
						</div>
					</div>
				`
			},
			{
				fieldname: "download_type",
				label: __("Select Download Option"),
				fieldtype: "Select",
				options: [
					{ label: __("Download Overall (Single Excel file for all candidates)"), value: "overall" },
					{ label: __("Download Center-wise (ZIP containing individual Excel file per center)"), value: "center_wise" }
				],
				default: "overall",
				reqd: 1
			}
		],
		primary_action_label: `<span style="display:inline-flex; align-items:center; gap:6px;">
			<i class="fa fa-download"></i> ${__("Download")}
		</span>`,
		primary_action: function(values) {
			d.hide();
			trigger_download(report, values.download_type);
		}
	});

	d.show();
}

function trigger_download(report, download_type) {
	const filters = report.get_values() || {};
	const is_zip = download_type === "center_wise";
	const action_label = is_zip ? __("Center-wise ZIP") : __("Overall Excel");

	frappe.show_progress(__("Preparing Download"), 30, 100, __("Generating {0}...", [action_label]));

	frappe.call({
		method: "slcm.admission.report.test_center_wise_candidate_detail_report.test_center_wise_candidate_detail_report.download_candidate_detail_excel",
		args: {
			filters: JSON.stringify(filters),
			download_type: download_type
		},
		callback: function(r) {
			frappe.show_progress(__("Preparing Download"), 100, 100, __("Done"));
			setTimeout(() => frappe.hide_progress(), 600);

			if (r.message && r.message.file_url) {
				const { file_url, filename, total_centres, total_records } = r.message;
				const a = document.createElement("a");
				a.href = file_url;
				a.download = filename;
				document.body.appendChild(a);
				a.click();
				document.body.removeChild(a);

				if (is_zip) {
					frappe.show_alert({
						message: __("✅ Downloaded ZIP folder with <b>{0}</b> center file(s) for <b>{1}</b> candidate(s).", [
							total_centres || 0,
							total_records || 0
						]),
						indicator: "green"
					}, 7);
				} else {
					frappe.show_alert({
						message: __("✅ Downloaded Overall Excel for <b>{0}</b> candidate(s).", [
							total_records || 0
						]),
						indicator: "green"
					}, 7);
				}
			}
		},
		error: function() {
			frappe.hide_progress();
		}
	});
}
