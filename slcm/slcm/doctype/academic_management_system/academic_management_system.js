// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Academic Management System", {
	refresh: function (frm) {
		frm.trigger("render_term_ui");
		frm.trigger("render_schedule_ui");
	},

	render_term_ui: function (frm) {
		const $wrapper = frm.get_field("term_ui_container").$wrapper;
		$wrapper.html("<p>Loading Terms...</p>");

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Academic Term",
				fields: [
					"name",
					"term_name",
					"academic_year",
					"term_start_date",
					"term_end_date",
					"system",
					"status",
					"previous_term",
				],
				order_by: "term_start_date desc",
			},
			callback: function (r) {
				const terms = r.message || [];
				let html = `
					<div class="row">
						<div class="col-xs-12 text-right">
							<button class="btn btn-primary btn-add-term">
								${frappe.utils.icon("add", "sm")} Add Term
							</button>
						</div>
					</div>
					<br>
					<table class="table table-bordered">
						<thead>
							<tr>
								<th>Name</th>
								<th>Academic Year</th>
								<th>Starts</th>
								<th>Ends</th>
								<th>System</th>
								<th>Status</th>
								<th>Previous Term</th>
							</tr>
						</thead>
						<tbody>
				`;

				if (terms.length === 0) {
					html += `<tr><td colspan="7" class="text-center">No Terms Found</td></tr>`;
				} else {
					terms.forEach((term) => {
						html += `
							<tr>
								<td><a href="/app/academic-term/${term.name}">${term.term_name}</a></td>
								<td>${term.academic_year}</td>
								<td>${frappe.datetime.str_to_user(term.term_start_date)}</td>
								<td>${frappe.datetime.str_to_user(term.term_end_date)}</td>
								<td>${term.system || ""}</td>
								<td>${term.status || ""}</td>
								<td>${term.previous_term || ""}</td>
							</tr>
						`;
					});
				}

				html += `</tbody></table>`;
				$wrapper.html(html);

				$wrapper.find(".btn-add-term").on("click", function () {
					frm.events.show_add_term_dialog(frm);
				});
			},
		});
	},

	show_add_term_dialog: function (frm) {
		const d = new frappe.ui.Dialog({
			title: "Create Term",
			fields: [
				{
					label: "Term Name",
					fieldname: "term_name",
					fieldtype: "Link",
					options: "Term Master",
					reqd: 1,
				},
				{
					label: "Academic Year",
					fieldname: "academic_year",
					fieldtype: "Link",
					options: "Academic Year",
					reqd: 1,
				},
				{
					fieldname: "col_break1",
					fieldtype: "Column Break",
				},
				{
					label: "Starts",
					fieldname: "term_start_date",
					fieldtype: "Date",
					reqd: 1,
				},
				{
					label: "Ends",
					fieldname: "term_end_date",
					fieldtype: "Date",
					reqd: 1,
				},
				{
					fieldname: "sec_break1",
					fieldtype: "Section Break",
				},
				{
					label: "System",
					fieldname: "system",
					fieldtype: "Select",
					options: "Semester\nTrimester\nQuarter\nYear",
					reqd: 1,
				},
				{
					label: "Status",
					fieldname: "status",
					fieldtype: "Select",
					options: "Active\nInactive",
					default: "Active",
					reqd: 1,
				},
				{
					fieldname: "col_break2",
					fieldtype: "Column Break",
				},
				{
					label: "Previous Term",
					fieldname: "previous_term",
					fieldtype: "Link",
					options: "Academic Term",
				},
			],
			primary_action_label: "Create",
			primary_action: function (values) {
				// Map system to term_type for compatibility
				values.term_type = values.system;

				frappe.call({
					method: "frappe.client.insert",
					args: {
						doc: {
							doctype: "Academic Term",
							...values,
						},
					},
					callback: function (r) {
						if (!r.exc) {
							frappe.msgprint("Term created successfully");
							d.hide();
							frm.trigger("render_term_ui");
						}
					},
				});
			},
		});
		d.show();
	},

	render_schedule_ui: function (frm) {
		const $wrapper = frm.get_field("schedule_ui_container").$wrapper;

		// Simple placeholder for Timetable - better implemented with full calendar library later
		let html = `
			<div class="text-center">
				<p>To view the Time Table, please check the <a href="/app/course-schedule">Course Schedule</a> list or Calendar view.</p>
				<button class="btn btn-default btn-view-calendar">View Calendar</button>
			</div>
		`;
		$wrapper.html(html);

		$wrapper.find(".btn-view-calendar").on("click", function () {
			frappe.set_route("List", "Course Schedule", "Calendar");
		});
	},
});
