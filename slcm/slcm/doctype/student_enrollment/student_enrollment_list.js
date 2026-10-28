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
 * "Action" DROPDOWN: PROMOTION + CREATE CLASS
 *****************************************************/
const ACTION_GROUP = __("Action");

function add_promotion_buttons(listview) {
	const allowed_roles = ["System Manager", "slcm_Academic Incharge"];
	const can_promote = frappe.user_roles.some((r) => allowed_roles.includes(r));
	const can_create_class = frappe.model.can_create("Classes");
	if (!can_promote && !can_create_class) return;

	inject_promotion_button_css();

	if (can_promote) {
		listview.page.add_inner_button(__("Promote Students"), () => {
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
		}, ACTION_GROUP);
		listview.page.add_inner_button(__("View Promotion Log"), () => {
			frappe.set_route("List", "Promotion Run");
		}, ACTION_GROUP);
	}

	if (can_create_class) {
		listview.page.add_inner_button(__("Create Class"), () => {
			open_create_class_dialog(listview);
		}, ACTION_GROUP);
	}

	listview.page
		.get_inner_group_button(ACTION_GROUP)
		.children(":not(.dropdown-menu)")
		.addClass("promotion-btn promotion-btn-primary");
}

/*****************************************************
 * CREATE CLASS
 * One Classes record per course picked, all with the same students.
 * Section: students of one programme section. Group: students picked from any
 * programme / year / section via "Find Students".
 *****************************************************/
function open_create_class_dialog(listview) {
	const course_fields = [
		{ fieldname: "course", fieldtype: "Link", options: "Course", label: __("Course"), in_list_view: 1, reqd: 1, columns: 4,
			get_query: () => ({ filters: { status: "Active" } }),
			// Picking a course brings its type and credit; faculty is chosen by hand
			onchange() {
				const row = this.doc;
				if (!row || !row.course) return;
				frappe.db.get_value("Course", row.course, ["course_name", "course_type", "credit_value"]).then(({ message: c }) => {
					Object.assign(row, { course_name: c.course_name, course_type: c.course_type, credit: c.credit_value });
					dialog.fields_dict.courses.grid.refresh();
				});
			},
		},
		{ fieldname: "course_name", fieldtype: "Data", label: __("Course Name"), read_only: 1 },
		{ fieldname: "course_type", fieldtype: "Data", label: __("Course Type"), in_list_view: 1, read_only: 1, columns: 2 },
		{ fieldname: "credit", fieldtype: "Int", label: __("Credit"), in_list_view: 1, read_only: 1, columns: 1 },
		{ fieldname: "faculty", fieldtype: "Link", options: "Faculty", label: __("Faculty"), in_list_view: 1, columns: 3 },
	];
	const student_fields = [
		{ fieldname: "student_enrollment", fieldtype: "Link", options: "Student Enrollment", label: __("Student ID"), in_list_view: 1, read_only: 1, columns: 2 },
		{ fieldname: "student_name", fieldtype: "Data", label: __("Name"), in_list_view: 1, read_only: 1, columns: 3 },
		{ fieldname: "section", fieldtype: "Data", label: __("Section"), in_list_view: 1, read_only: 1, columns: 1 },
		{ fieldname: "program", fieldtype: "Data", label: __("Programme"), in_list_view: 1, read_only: 1, columns: 3 },
		{ fieldname: "year_no", fieldtype: "Int", label: __("Year"), in_list_view: 1, read_only: 1, columns: 1 },
	];
	const is_group = () => dialog.get_value("class_type") === "Group";

	const dialog = new frappe.ui.Dialog({
		title: __("Create Class"),
		size: "extra-large",
		fields: [
			{
				fieldname: "class_type", fieldtype: "Select", label: __("Class Type"), options: "Section\nGroup", default: "Section", reqd: 1,
				description: __("Section: students of one section. Group: pick students from any section, year or programme."),
				onchange: () => {
					set_students([]);
					load_section_students();
				},
			},
			{ fieldname: "academic_year", fieldtype: "Link", options: "Academic Year", label: __("Academic Year"), reqd: 1,
				onchange: () => {
					dialog.set_value("academic_term", null);
					load_section_students();
				},
			},
			{ fieldname: "academic_term", fieldtype: "Link", options: "Academic Term", label: __("Academic Term"), reqd: 1,
				get_query: () => ({ filters: { academic_year: dialog.get_value("academic_year") } }),
			},
			{ fieldname: "cb_1", fieldtype: "Column Break" },
			{ fieldname: "programme", fieldtype: "Link", options: "Programme", label: __("Programme"), reqd: 1,
				onchange: () => load_section_students(),
			},
			{ fieldname: "year_no", fieldtype: "Int", label: __("Year No"), default: 1, reqd: 1,
				onchange: () => load_section_students(),
			},
			{ fieldname: "section", fieldtype: "Link", options: "Section", label: __("Section"),
				depends_on: "eval:doc.class_type!='Group'", mandatory_depends_on: "eval:doc.class_type!='Group'",
				onchange: () => load_section_students(),
			},
			{ fieldname: "group_name", fieldtype: "Data", label: __("Group Name"),
				depends_on: "eval:doc.class_type=='Group'", mandatory_depends_on: "eval:doc.class_type=='Group'",
			},

			{ fieldname: "sb_courses", fieldtype: "Section Break", label: __("Courses"),
				description: __("Add the courses to create a class for, one class per course. Course type and credit come from the course; pick the faculty for each.") },
			{ fieldname: "courses", fieldtype: "Table", label: __("Courses"), in_place_edit: 1, data: [], fields: course_fields },

			{ fieldname: "sb_find", fieldtype: "Section Break", label: __("Find Students"), depends_on: "eval:doc.class_type=='Group'",
				description: __("Leave a filter empty to match all. Students found are added to the list below.") },
			{ fieldname: "f_programme", fieldtype: "Link", options: "Programme", label: __("Programme") },
			{ fieldname: "f_academic_year", fieldtype: "Link", options: "Academic Year", label: __("Academic Year") },
			{ fieldname: "cb_2", fieldtype: "Column Break" },
			{ fieldname: "f_year_no", fieldtype: "Int", label: __("Year No") },
			{ fieldname: "f_section", fieldtype: "Link", options: "Section", label: __("Section") },
			{ fieldname: "f_add", fieldtype: "Button", label: __("Add Students"), click: () => add_group_students() },

			{ fieldname: "sb_students", fieldtype: "Section Break", label: __("Students"),
				description: __("Every student listed is added to each class. Select rows and delete to leave students out.") },
			{ fieldname: "students", fieldtype: "Table", label: __("Students"), cannot_add_rows: 1, in_place_edit: 0, data: [], fields: student_fields },
		],
		primary_action_label: __("Create Class"),
		primary_action(values) {
			const courses = (values.courses || [])
				.filter((r) => r.course)
				.map((r) => ({ course: r.course, faculty: r.faculty, credit: r.credit }));
			const students = (values.students || []).map((r) => r.student_enrollment).filter(Boolean);
			if (!courses.length) {
				frappe.msgprint(__("Add at least one course to create a class for."));
				return;
			}
			const seen = new Set();
			const repeated = courses.find((c) => seen.has(c.course) || !seen.add(c.course));
			if (repeated) {
				frappe.msgprint(__("Course {0} is listed twice.", [repeated.course]));
				return;
			}
			if (!students.length) {
				frappe.msgprint(__("Add at least one student."));
				return;
			}
			frappe.call({
				method: "slcm.slcm.doctype.classes.classes.create_classes",
				args: {
					data: {
						class_type: values.class_type,
						academic_year: values.academic_year,
						academic_term: values.academic_term,
						programme: values.programme,
						year_no: values.year_no,
						section: values.section,
						group_name: values.group_name,
						courses,
						students,
					},
				},
				freeze: true,
				freeze_message: __("Creating classes..."),
				callback({ message }) {
					const { created = [], skipped = [] } = message || {};
					dialog.hide();
					const link = (n) => frappe.utils.get_form_link("Classes", n, true);
					let html = created.length
						? __("Created {0} class(es) with {1} student(s):", [created.length, students.length]) + "<br>" + created.map(link).join("<br>")
						: __("No class was created.");
					if (skipped.length) {
						html += "<br><br>" + __("Skipped — a class already exists for this section:") + "<br>" +
							skipped.map((s) => `${frappe.utils.escape_html(s.course)} → ${link(s.class)}`).join("<br>");
					}
					frappe.msgprint({ title: __("Create Class"), message: html, indicator: created.length ? "green" : "orange" });
				},
			});
		},
	});

	function set_table(fieldname, rows) {
		const field = dialog.fields_dict[fieldname];
		field.df.data = rows;
		field.grid.refresh();
	}

	function set_students(rows) {
		set_table("students", rows);
	}

	function to_student_rows(list) {
		return list.map((s) => ({
			student_enrollment: s.name,
			student_name: s.student_name,
			section: s.section,
			program: s.program,
			year_no: s.year_no,
		}));
	}

	function load_section_students() {
		if (is_group()) return;
		const { academic_year, programme, year_no, section } = dialog.get_values(true);
		if (!academic_year || !programme || !section) {
			set_students([]);
			return;
		}
		frappe.call({
			method: "slcm.slcm.doctype.classes.classes.get_enrollment_students",
			args: { programme, academic_year, year_no, section },
			callback: ({ message }) => set_students(to_student_rows(message || [])),
		});
	}

	function add_group_students() {
		const v = dialog.get_values(true);
		frappe.call({
			method: "slcm.slcm.doctype.classes.classes.get_enrollment_students",
			args: { programme: v.f_programme, academic_year: v.f_academic_year, year_no: v.f_year_no, section: v.f_section },
			callback: ({ message }) => {
				const current = dialog.fields_dict.students.df.data || [];
				const existing = new Set(current.map((r) => r.student_enrollment));
				const added = to_student_rows((message || []).filter((s) => !existing.has(s.name)));
				set_students(current.concat(added));
				frappe.show_alert({ message: __("Added {0} student(s)", [added.length]), indicator: added.length ? "green" : "orange" });
			},
		});
	}

	dialog.show();
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
					<span>${__("Promoting {0} selected student(s){1} to the next year of study. Each enrollment's Academic Log gets Year + 1 in the target academic year, with that year's courses added; the current year is marked Completed.", [
						`<b>${batched.length}</b>`,
						program ? __(" in <b>{0}</b>", [frappe.utils.escape_html(program)]) : "",
					])}<br>${__("No Promotion Policy is checked here. Policy-checked promotion is done from the <b>Promotion Management</b> page.")}</span>
				</div>`,
			},
			{ fieldname: "target_academic_year", label: __("Target Academic Year"), fieldtype: "Link", options: "Academic Year", reqd: 1 },

			{ fieldname: "sb_courses", fieldtype: "Section Break", label: `&#128218; ${__("Courses in the Next Year")}` },
			{
				fieldname: "course_preview_html",
				fieldtype: "HTML",
				options: `<div class="promote-course-preview"><div class="pcp-empty">${__("Choose a Target Academic Year above to preview its courses.")}</div></div>`,
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
		const $box = dialog.$wrapper.find(".promote-course-preview");

		if (!target_academic_year) {
			$box.html(`<div class="pcp-empty">${__("Choose a Target Academic Year above to preview its courses.")}</div>`);
			return;
		}

		frappe.call({
			method: "slcm.slcm.doctype.promotion_run.promotion_run.get_target_term_courses",
			args: { student_list, target_academic_year },
			callback: (r) => {
				const courses = (r.message && r.message.courses) || [];
				const target_years = (r.message && r.message.target_years) || [];
				if (!courses.length) {
					$box.html(`<div class="pcp-empty">${__("No classes have been created yet for {0} in {1}. Promotion is not blocked by this.", [
						frappe.utils.escape_html(target_years.join(", ") || __("the next year")),
						frappe.utils.escape_html(target_academic_year),
					])}</div>`);
					return;
				}
				const rows = courses
					.map(
						(c) => `<tr>
							<td>${frappe.utils.escape_html(c.course_name || c.course || "—")}</td>
							<td>${c.credits != null ? c.credits : "—"}</td>
							<td>${__("Year {0}", [c.year_no])}</td>
						</tr>`
					)
					.join("");
				$box.html(`
					<div class="pcp-head">${__("{0} course(s) with classes for the next year", [courses.length])}</div>
					<table>
						<thead><tr>
							<th>${__("Course")}</th><th>${__("Credits")}</th><th>${__("Year")}</th>
						</tr></thead>
						<tbody>${rows}</tbody>
					</table>
				`);
			},
		});
	};

	dialog.fields_dict.target_academic_year.df.onchange = refresh_course_preview;

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
	// (Frappe clears custom buttons on every refresh; clearing here too would
	// also drop buttons other refresh handlers add, e.g. Change Section.)
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
