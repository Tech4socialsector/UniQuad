/*****************************************************
 * LIST VIEW CONFIGURATION
 *****************************************************/
frappe.listview_settings["Student Enrollment"] = {
	onload(listview) {
		$("span.sidebar-toggle-btn").hide();
		$(".col-lg-2.layout-side-section").hide();
		inject_enrollment_status_css();
		add_listview_status_actions(listview);
		add_promotion_buttons(listview);
	},

	get_indicator(doc) {
		if (doc.status === "Enrolled") {
			return [__("Enrolled"), "green", "status,=,Enrolled"];
		}

		if (doc.status === "Dropped") {
			return [__("Dropped"), "red", "status,=,Dropped"];
		}

		if (doc.status === "Completed") {
			return [__("Completed"), "blue", "status,=,Completed"];
		}

		if (doc.status === "Pending") {
			return [__("Pending"), "yellow", "status,=,Pending"];
		}

		return [__(doc.status), "gray"];
	},
};

/* --------------------------------------------------
   List View → Actions → Status (Bulk Update)
-------------------------------------------------- */
function add_listview_status_actions(listview) {
	const statuses = [
		{ label: __("Enrolled"), value: "Enrolled" },
		{ label: __("Dropped"), value: "Dropped" },
		{ label: __("Completed"), value: "Completed" },
		{ label: __("Pending"), value: "Pending" },
	];

	statuses.forEach((status) => {
		listview.page.add_action_item(status.label, () => {
			update_listview_status(listview, status.value);
		});
	});
}

/* --------------------------------------------------
   Bulk status update logic
-------------------------------------------------- */
function update_listview_status(listview, status) {
	const selected = listview.get_checked_items();

	if (!selected.length) {
		frappe.msgprint({
			title: __("No Records Selected"),
			message: __("Please select at least one Student Enrollment."),
			indicator: "orange",
		});
		return;
	}

	frappe.confirm(
		__("Are you sure you want to change status to <b>{0}</b> for {1} record(s)?", [
			status,
			selected.length,
		]),
		() => {
			frappe.call({
				method: "slcm.slcm.doctype.student_enrollment.student_enrollment.bulk_update_enrollment_status",
				args: {
					names: selected.map((doc) => doc.name),
					status: status,
				},
				freeze: true,
				callback: (r) => {
					const { updated = [], failed = [] } = r.message || {};

					if (updated.length) {
						frappe.show_alert(
							{
								message: __("Status updated to {0} for {1} record(s)", [status, updated.length]),
								indicator: "green",
							},
							5
						);
					}

					if (failed.length) {
						frappe.msgprint({
							title: __("Some records could not be updated"),
							indicator: "red",
							message: failed
								.map((f) => `${f.name}: ${f.error}`)
								.join("<br>"),
						});
					}

					listview.refresh();
				},
			});
		}
	);
}

/*****************************************************
 * BULK PROMOTION
 *****************************************************/
function add_promotion_buttons(listview) {
	const allowed_roles = ["System Manager", "slcm_Academic Incharge"];
	if (!frappe.user_roles.some((r) => allowed_roles.includes(r))) return;

	inject_promotion_button_css();

	const $promote_btn = listview.page.add_inner_button(__("Promote Students"), () => {
		const selected = listview.get_checked_items();
		if (!selected.length) {
			frappe.msgprint({
				title: __("No Students Selected"),
				message: __("Check one or more Student Enrollment rows in the list before promoting."),
				indicator: "orange",
			});
			return;
		}
		open_promote_students_dialog(listview, selected);
	});
	const $log_btn = listview.page.add_inner_button(__("View Promotion Log"), () => {
		frappe.set_route("List", "Promotion Run");
	});

	$promote_btn.addClass("promotion-btn promotion-btn-primary").prepend('<span class="promotion-btn-icon">&#8613;</span> ');
	$log_btn.addClass("promotion-btn promotion-btn-secondary").prepend('<span class="promotion-btn-icon">&#128203;</span> ');
}

function inject_promotion_button_css() {
	if (document.getElementById("promotion-btn-css")) return;

	const style = document.createElement("style");
	style.id = "promotion-btn-css";
	style.innerHTML = `
		.promotion-btn {
			font-weight: 600;
			border: none !important;
			box-shadow: none !important;
			transition: filter 0.15s ease, transform 0.05s ease;
		}
		.promotion-btn:active {
			transform: translateY(1px);
		}
		.promotion-btn-icon {
			display: inline-block;
			transform: translateY(-1px);
		}
		.promotion-btn-primary {
			background-color: #1e293b !important;
			color: #ffffff !important;
		}
		.promotion-btn-primary:hover {
			background-color: #0f172a !important;
			color: #ffffff !important;
		}
		.promotion-btn-secondary {
			background-color: #334155 !important;
			color: #e2e8f0 !important;
		}
		.promotion-btn-secondary:hover {
			background-color: #1e293b !important;
			color: #ffffff !important;
		}

		.promote-dialog .modal-dialog {
			max-width: 1100px !important;
			width: 92vw !important;
		}
		.promote-dialog .modal-header {
			background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
			border-radius: 6px 6px 0 0;
			padding: 18px 28px;
		}
		.promote-dialog .modal-header .modal-title {
			color: #ffffff;
			font-size: 17px;
			font-weight: 700;
			display: flex;
			align-items: center;
			gap: 10px;
		}
		.promote-dialog .modal-header .btn-modal-close svg {
			stroke: #ffffff;
		}
		.promote-dialog .modal-body {
			padding: 0;
			max-height: 72vh;
			overflow-y: auto;
		}
		.promote-dialog-intro {
			padding: 14px 28px;
			background: #f1f5f9;
			border-bottom: 1px solid #e2e8f0;
			font-size: 13px;
			line-height: 1.5;
			color: #475569;
			display: flex;
			align-items: flex-start;
			gap: 10px;
		}
		.promote-dialog-intro .info-icon {
			flex-shrink: 0;
			width: 20px;
			height: 20px;
			border-radius: 50%;
			background: #cbd5e1;
			color: #1e293b;
			font-weight: 700;
			font-size: 12px;
			display: flex;
			align-items: center;
			justify-content: center;
			margin-top: 1px;
		}
		.promote-dialog .modal-body form {
			padding: 20px 28px 6px 28px;
		}
		.promote-dialog .frappe-control {
			margin-bottom: 16px;
		}
		.promote-dialog .form-column {
			padding-left: 12px;
			padding-right: 12px;
		}
		.promote-dialog .form-section.promote-section-card {
			background: #f8fafc;
			border: 1px solid #e2e8f0;
			border-radius: 8px;
			padding: 16px 16px 4px 16px;
			margin-bottom: 20px;
		}
		.promote-dialog .form-section.promote-section-card.target {
			background: #f0fdf4;
			border-color: #bbf7d0;
		}
		.promote-dialog .form-section.promote-section-card .section-head {
			font-size: 11.5px;
			font-weight: 700;
			letter-spacing: 0.06em;
			text-transform: uppercase;
			color: #475569;
			border: none;
			padding: 0 0 14px 0;
			margin: 0;
		}
		.promote-dialog .form-section.promote-section-card.target .section-head {
			color: #166534;
		}
		.promote-dialog .form-section:not(.promote-section-card) .section-head {
			display: none;
		}
		.promote-dialog .modal-footer {
			background: #f8fafc;
			border-top: 1px solid #e2e8f0;
			padding: 14px 28px;
		}
		.promote-dialog .modal-footer .btn-primary {
			background-color: #1e293b;
			border: none;
			font-weight: 600;
			padding: 8px 22px;
		}
		.promote-dialog .modal-footer .btn-primary:hover {
			background-color: #0f172a;
		}

		.promote-review-dialog .modal-dialog {
			max-width: 1240px !important;
			width: 92vw !important;
		}
		.promote-review-count {
			font-weight: 400;
			opacity: 0.8;
			font-size: 14px;
		}
		.promote-review-toolbar {
			padding: 14px 32px;
			background: #f8fafc;
			border-bottom: 1px solid #e2e8f0;
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 16px;
			flex-wrap: wrap;
		}
		.promote-review-summary {
			font-size: 12.5px;
			color: #64748b;
			flex: 1;
		}
		.promote-review-summary b {
			color: #1e293b;
		}
		.promote-review-selected-count {
			font-size: 12.5px;
			font-weight: 700;
			color: #1e293b;
			background: #e2e8f0;
			padding: 4px 12px;
			border-radius: 20px;
			white-space: nowrap;
		}
		.promote-review-datatable {
			padding: 16px 32px 8px 32px;
		}
		.promote-review-datatable .dt-scrollable {
			max-height: 55vh;
		}
		.promote-review-datatable .dt-row-highlight,
		.promote-review-datatable .dt-cell:hover {
			background-color: #f8fafc;
		}
		.promote-review-datatable .dt-cell__content {
			padding: 6px 12px;
			display: flex;
			flex-direction: column;
			justify-content: center;
		}
		.promote-row-name {
			font-weight: 600;
			color: #1e293b;
			font-size: 13.5px;
			line-height: 1.3;
			white-space: normal;
		}
		.promote-row-id {
			font-size: 11px;
			line-height: 1.3;
			color: #94a3b8;
			margin-top: 2px;
		}
		.promote-row-tag {
			display: inline-flex;
			align-items: center;
			gap: 5px;
			font-size: 11.5px;
			font-weight: 600;
			padding: 4px 11px;
			border-radius: 20px;
			white-space: nowrap;
			max-width: 280px;
			overflow: hidden;
			text-overflow: ellipsis;
		}
		.promote-row-tag.ok {
			background: #dcfce7;
			color: #166534;
		}
		.promote-row-tag.warn {
			background: #fef3c7;
			color: #92400e;
		}
		.promote-review-dialog .modal-body {
			padding-top: 0;
			padding-bottom: 4px;
		}
		.promote-review-dialog .modal-footer .btn-secondary {
			font-weight: 600;
		}
		.promote-review-dialog .modal-footer {
			background: #f8fafc;
			border-top: 1px solid #e2e8f0;
			padding: 14px 32px;
		}

		.promote-course-preview {
			margin: 4px 28px 20px 28px;
			border: 1px solid #e2e8f0;
			border-radius: 8px;
			overflow: hidden;
		}
		.promote-course-preview .pcp-head {
			padding: 10px 16px;
			background: #f8fafc;
			border-bottom: 1px solid #e2e8f0;
			font-size: 11.5px;
			font-weight: 700;
			letter-spacing: 0.05em;
			text-transform: uppercase;
			color: #475569;
		}
		.promote-course-preview table {
			width: 100%;
			border-collapse: collapse;
			font-size: 13px;
		}
		.promote-course-preview th, .promote-course-preview td {
			padding: 8px 16px;
			text-align: left;
			border-bottom: 1px solid #f1f5f9;
		}
		.promote-course-preview th {
			color: #64748b;
			font-weight: 600;
			font-size: 11.5px;
			text-transform: uppercase;
		}
		.promote-course-preview tbody tr:last-child td {
			border-bottom: none;
		}
		.promote-course-preview .pcp-empty {
			padding: 18px 16px;
			text-align: center;
			color: #94a3b8;
			font-size: 12.5px;
		}
	`;
	document.head.appendChild(style);
}

function open_promote_students_dialog(listview, selected) {
	const programs = [...new Set(selected.map((s) => s.program).filter(Boolean))];

	if (programs.length > 1) {
		frappe.msgprint({
			title: __("Multiple Programmes Selected"),
			indicator: "orange",
			message: __(
				"Selected students belong to multiple Programmes ({0}). Please filter your selection to one Programme at a time before promoting.",
				[programs.join(", ")]
			),
		});
		return;
	}

	const program = programs[0];

	const unbatched = selected.filter((s) => !s.batch);
	const batched = selected.filter((s) => s.batch);

	if (!batched.length) {
		frappe.msgprint({
			title: __("No Batch on Selected Students"),
			indicator: "red",
			message: __("None of the selected students have a Batch on their enrollment, so none can be promoted. Set a Batch on their Student Enrollment record first."),
		});
		return;
	}

	const student_list = batched.map((s) => s.name);

	const proceed = () => open_promote_dialog_body(listview, selected, batched, student_list, program);

	if (unbatched.length) {
		frappe.confirm(
			__(
				"{0} of {1} selected student(s) have no Batch on their enrollment and cannot be promoted: {2}. Continue promoting the remaining {3} student(s)?",
				[
					unbatched.length,
					selected.length,
					unbatched.map((s) => frappe.utils.escape_html(s.student_name || s.name)).join(", "),
					batched.length,
				]
			),
			proceed
		);
	} else {
		proceed();
	}
}

function open_promote_dialog_body(listview, selected, batched, student_list, program) {
	const dialog = new frappe.ui.Dialog({
		title: `<span>&#8613;</span> ${__("Promote Students")}`,
		fields: [
			{
				fieldname: "intro_html",
				fieldtype: "HTML",
				options: `<div class="promote-dialog-intro">
					<span class="info-icon">i</span>
					<span>${__("Promoting {0} selected student(s){1} to the next term. Choose where they're being promoted to.", [
						`<b>${batched.length}</b>`,
						program ? __(" in <b>{0}</b>", [frappe.utils.escape_html(program)]) : "",
					])}<br>${__("Term-to-term promotion is automatic — no Promotion Policy is checked. Year-to-year promotion (with policy check) is done from the <b>Promotion Management</b> page.")}</span>
				</div>`,
			},
			{ fieldname: "target_academic_year", label: __("Target Academic Year"), fieldtype: "Link", options: "Academic Year", reqd: 1 },
			{ fieldname: "target_term", label: __("Target Term"), fieldtype: "Link", options: "Academic Term", reqd: 1,
				description: __("Required — the target Academic Year can have more than one term (e.g. multiple trimesters), so this pins down exactly which Batch to promote students into.") },

			{ fieldname: "sb_courses", fieldtype: "Section Break", label: `&#128218; ${__("Courses in Target Term")}` },
			{
				fieldname: "course_preview_html",
				fieldtype: "HTML",
				options: `<div class="promote-course-preview"><div class="pcp-empty">${__("Choose a Target Academic Year and Target Term above to preview its courses.")}</div></div>`,
			},
		],
		size: "extra-large",
		primary_action_label: __("Promote"),
		primary_action(values) {
			frappe.confirm(
				__("Start a promotion run for {0} selected student(s)?", [batched.length]),
				() => {
					dialog.hide();
					frappe.call({
						method: "slcm.slcm.doctype.promotion_run.promotion_run.create_and_queue",
						args: {
							student_list,
							target_academic_year: values.target_academic_year,
							target_term: values.target_term,
						},
						freeze: true,
						freeze_message: __("Queuing promotion run..."),
						callback: (r) => {
							if (!r.message) return;
							const run_name = r.message;
							frappe.show_alert({ message: __("Promotion Run {0} started", [run_name]), indicator: "blue" }, 6);
							watch_promotion_run(run_name, listview);
						},
					});
				}
			);
		},
	});

	dialog.$wrapper.find(".modal-dialog").addClass("promote-dialog");

	const refresh_course_preview = () => {
		const target_academic_year = dialog.get_value("target_academic_year");
		const target_term = dialog.get_value("target_term");
		const $box = dialog.$wrapper.find(".promote-course-preview");

		if (!target_academic_year) {
			$box.html(`<div class="pcp-empty">${__("Choose a Target Academic Year and Target Term above to preview its courses.")}</div>`);
			return;
		}

		frappe.call({
			method: "slcm.slcm.doctype.promotion_run.promotion_run.get_target_term_courses",
			args: { student_list, target_academic_year, target_term },
			callback: (r) => {
				const courses = (r.message && r.message.courses) || [];
				const target_batches = (r.message && r.message.target_batches) || [];
				if (!target_batches.length) {
					$box.html(`<div class="pcp-empty">${__("No target Batch exists yet for the selected students' next term — create it first, or check back after doing so. Promotion is not blocked by this.")}</div>`);
					return;
				}
				if (!courses.length) {
					$box.html(`<div class="pcp-empty">${__("No active Course Offerings found yet for the target Batch(es): {0}. Promotion is not blocked by this.", [target_batches.join(", ")])}</div>`);
					return;
				}
				const rows = courses
					.map(
						(c) => `<tr>
							<td>${frappe.utils.escape_html(c.course_name || c.course || "—")}</td>
							<td>${c.credits != null ? c.credits : "—"}</td>
							<td>${frappe.utils.escape_html(c.batch || "—")}</td>
						</tr>`
					)
					.join("");
				$box.html(`
					<div class="pcp-head">${__("{0} active course offering(s) in the target Batch(es)", [courses.length])}</div>
					<table>
						<thead><tr>
							<th>${__("Course")}</th><th>${__("Credits")}</th><th>${__("Batch")}</th>
						</tr></thead>
						<tbody>${rows}</tbody>
					</table>
				`);
			},
		});
	};

	dialog.fields_dict.target_academic_year.df.onchange = refresh_course_preview;
	dialog.fields_dict.target_term.df.onchange = refresh_course_preview;

	dialog.show();
}

function watch_promotion_run(run_name, listview) {
	frappe.realtime.on("promotion_run_complete", (data) => {
		if (data.promotion_run !== run_name) return;
		const indicator = data.status === "Completed" ? "green" :
			data.status === "Error" ? "red" : "orange";
		frappe.show_alert({
			message: __("Promotion Run {0}: {1} — {2} promoted, {3} skipped", [
				run_name, data.status, data.promoted || 0, data.skipped || 0,
			]),
			indicator,
		}, 8);
		if (listview) listview.refresh();
		frappe.realtime.off("promotion_run_complete");
		frappe.set_route("Form", "Promotion Run", run_name);
	});
}

/*****************************************************
 * STATUS INDICATOR STYLING (LIST VIEW ONLY)
 *****************************************************/
function inject_enrollment_status_css() {
	if (document.getElementById("enrollment-status-css")) return;

	const style = document.createElement("style");
	style.id = "enrollment-status-css";
	style.innerHTML = `
		.indicator.green {
			background-color: #e6f4ea !important;
			color: #1e7e34 !important;
			font-weight: 600;
		}
		.indicator.red {
			background-color: #fdecea !important;
			color: #b02a37 !important;
			font-weight: 600;
		}
		.indicator.blue {
			background-color: #e7f1ff !important;
			color: #0d6efd !important;
			font-weight: 600;
		}
	`;
	document.head.appendChild(style);
}

/*****************************************************
 * FORM VIEW CONFIGURATION (SINGLE RECORD)
 *****************************************************/
frappe.ui.form.on("Student Enrollment", {
	refresh(frm) {
		// Do not show action buttons for unsaved records
		if (frm.is_new()) return;

		add_form_status_action_buttons(frm);
	},
});

/* --------------------------------------------------
   Form View → Actions → Status
-------------------------------------------------- */
function add_form_status_action_buttons(frm) {
	// Prevent duplicate buttons
	frm.clear_custom_buttons();

	const statuses = [
		{ label: __("Enrolled"), value: "Enrolled" },
		{ label: __("Dropped"), value: "Dropped" },
		{ label: __("Completed"), value: "Completed" },
		{ label: __("Pending"), value: "Pending" },
	];

	statuses.forEach((status) => {
		frm.add_custom_button(
			status.label,
			() => update_form_status(frm, status.value),
			__("Actions")
		);
	});
}

/* --------------------------------------------------
   Single record status update logic
-------------------------------------------------- */
function update_form_status(frm, status) {
	if (frm.doc.status === status) {
		frappe.msgprint({
			title: __("No Change"),
			message: __("Status is already <b>{0}</b>.", [status]),
			indicator: "blue",
		});
		return;
	}

	frappe.confirm(__("Are you sure you want to change status to <b>{0}</b>?", [status]), () => {
		frm.set_value("status", status);

		frm.save().then(() => {
			frappe.show_alert(
				{
					message: __("Status updated to {0}", [status]),
					indicator: "green",
				},
				5
			);
		});
	});
}
