// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.pages["student-attendance-tool"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Student Attendance Tool"),
		single_column: true,
	});

	$("<style>")
		.prop("type", "text/css")
		.html(
			`
			.student-list-container table tbody { display: table-row-group; }
			.student-list-container table thead,
			.student-list-container table tbody,
			.student-list-container table tr { width: 100%; table-layout: fixed; }
			.student-list-container table { display: table; width: 100%; }
			.student-row:hover { background-color: #f5f5f5; }
			.faculty-banner {
				background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf1 100%);
				border: 1px solid #bee5eb;
				border-radius: 6px;
				padding: 12px 18px;
				margin-bottom: 16px;
				display: flex;
				align-items: center;
				gap: 12px;
			}
			.faculty-banner .faculty-avatar {
				width: 40px; height: 40px; border-radius: 50%;
				background: #17a2b8; color: #fff;
				display: flex; align-items: center; justify-content: center;
				font-size: 18px; font-weight: bold; flex-shrink: 0;
			}
			.faculty-banner .faculty-info { flex: 1; }
			.faculty-banner .faculty-name { font-weight: 600; font-size: 15px; color: #0c5460; }
			.faculty-banner .faculty-sub { font-size: 12px; color: #555; margin-top: 2px; }
			.faculty-banner .faculty-badge {
				background: #17a2b8; color: #fff;
				border-radius: 12px; padding: 2px 10px; font-size: 11px;
			}
		`
		)
		.appendTo("head");

	let attendance_tool = new StudentAttendanceTool(page);
	page.attendance_tool = attendance_tool;
};

class StudentAttendanceTool {
	constructor(page) {
		this.page = page;
		this.students = [];
		this.selected_students = new Set();
		this.faculty_context = null;
		this.init();
	}

	init() {
		// Load faculty context first, then build the UI
		frappe.call({
			method: "slcm.api.bulk_attendance.get_faculty_context",
			callback: (r) => {
				this.faculty_context = r.message || {};
				this.make_faculty_banner();
				this.make_form();
				this.make_student_list();
			},
		});
	}

	make_faculty_banner() {
		let ctx = this.faculty_context;
		let html = "";

		if (ctx.is_faculty && ctx.faculty_name) {
			let initials = (ctx.faculty_full_name || ctx.faculty_name)
				.split(" ")
				.map((w) => w[0])
				.join("")
				.toUpperCase()
				.slice(0, 2);
			let class_count = (ctx.assigned_classes || []).length;
			let group_label =
				class_count === 1
					? "1 Class assigned"
					: `${class_count} Classes assigned`;

			html = `
				<div class="faculty-banner">
					<div class="faculty-avatar">${initials}</div>
					<div class="faculty-info">
						<div class="faculty-name">${ctx.faculty_full_name || ctx.faculty_name}</div>
						<div class="faculty-sub">
							Faculty ID: <strong>${ctx.faculty_name}</strong> &nbsp;|&nbsp; ${group_label}
						</div>
					</div>
					<span class="faculty-badge">Faculty</span>
				</div>
			`;
		} else if (ctx.is_admin) {
			html = `
				<div class="faculty-banner" style="background: linear-gradient(135deg, #fff3cd 0%, #ffeeba 100%); border-color: #ffc107;">
					<div class="faculty-avatar" style="background: #ffc107; color: #333;">
						<i class="fa fa-shield"></i>
					</div>
					<div class="faculty-info">
						<div class="faculty-name" style="color: #856404;">Admin / Programme Chair View</div>
						<div class="faculty-sub" style="color: #555;">All classes are visible</div>
					</div>
					<span class="faculty-badge" style="background: #ffc107; color: #333;">Admin</span>
				</div>
			`;
		}

		if (html) {
			let banner = $(html);
			this.page.main.append(banner);
		}
	}

	make_form() {
		let me = this;
		let ctx = this.faculty_context || {};

		this.form_container = $(`
			<div class="attendance-form-container" style="padding: 20px; background: #fff; border-radius: 4px; margin-bottom: 20px;">
				<div class="row">
					<div class="col-md-12">
						<h4>Attendance Configuration</h4>
					</div>
				</div>
				<div class="row" style="margin-top: 15px;">
					<div class="col-md-3">
						<div class="form-group">
							<label>Based On <span class="text-danger">*</span></label>
							<select class="form-control" id="based_on" required>
								<option value="">Select...</option>
								<option value="Class">Class</option>
							</select>
						</div>
					</div>
					<div class="col-md-3" id="class_schedule_container">
						<div class="form-group">
							<label>Time Table <span class="text-danger">*</span></label>
							<div id="class_schedule_field"></div>
						</div>
					</div>
				</div>
				<div class="row" style="margin-top: 15px;">
					<div class="col-md-3">
						<div class="form-group">
							<label>Academic Year</label>
							<div id="academic_year_field"></div>
						</div>
					</div>
					<div class="col-md-3">
						<div class="form-group">
							<label>Academic Term</label>
							<div id="academic_term_field"></div>
						</div>
					</div>
					<div class="col-md-3">
						<div class="form-group">
							<label>Date <span class="text-danger">*</span></label>
							<input type="date" class="form-control" id="attendance_date" required>
						</div>
					</div>
					<div class="col-md-3">
						<div class="form-group">
							<label style="display: block; margin-bottom: 10px;">&nbsp;</label>
							<button class="btn btn-primary" id="get_students_btn" onclick="return false;">
								Get Students
							</button>
						</div>
					</div>
				</div>
			</div>
		`);

		this.page.main.append(this.form_container);

		$("#attendance_date").val(frappe.datetime.get_today());

		// --- Time Table link field (class periods) ---
		// Faculty can only pick entries belonging to their assigned classes
		let tt_get_query = () => {
			let filters = { based_on: "Class" };
			if (ctx.is_faculty && ctx.assigned_classes && ctx.assigned_classes.length > 0) {
				filters.class_name = ["in", ctx.assigned_classes.map((c) => c.name)];
			} else if (ctx.is_faculty) {
				filters.name = ["=", "__no_classes__"];
			}
			return { filters };
		};

		this.class_schedule_field = frappe.ui.form.make_control({
			parent: $("#class_schedule_field"),
			df: {
				fieldtype: "Link",
				fieldname: "class_schedule",
				options: "Time Table",
				placeholder: "Select Time Table",
				get_query: tt_get_query,
				change: () => {
					me.load_class_schedule_details();
				},
			},
		});
		this.class_schedule_field.refresh();

		this.class_name_field = frappe.ui.form.make_control({
			parent: $("#class_name_field"),
			df: {
				fieldtype: "Link",
				fieldname: "class_name",
				options: "Classes",
				placeholder: "Select Class",
			},
		});
		this.class_name_field.refresh();

		this.academic_year_field = frappe.ui.form.make_control({
			parent: $("#academic_year_field"),
			df: {
				fieldtype: "Link",
				fieldname: "academic_year",
				options: "Academic Year",
				read_only: 1,
			},
		});
		this.academic_year_field.refresh();

		this.academic_term_field = frappe.ui.form.make_control({
			parent: $("#academic_term_field"),
			df: {
				fieldtype: "Link",
				fieldname: "academic_term",
				options: "Academic Term",
				read_only: 1,
			},
		});
		this.academic_term_field.refresh();

		// --- Event handlers ---
		$("#based_on").on("change", function () {
			me.class_name_field.set_value("");
			me.clear_students();
		});

		$("#get_students_btn").on("click", function () {
			me.get_students();
		});
	}

	load_class_schedule_details() {
		let class_schedule = this.class_schedule_field.get_value();
		if (!class_schedule) {
			this.academic_year_field.set_value("");
			this.academic_term_field.set_value("");
			return;
		}

		frappe.db.get_value("Time Table", class_schedule,
			["academic_year", "academic_term"], (r) => {
				if (r && r.academic_year) this.academic_year_field.set_value(r.academic_year);
				if (r && r.academic_term) this.academic_term_field.set_value(r.academic_term);
			});
	}

	make_student_list() {
		let me = this;

		this.student_list_container = $(`
			<div class="student-list-container" style="padding: 20px; background: #fff; border-radius: 4px;">
				<div class="row">
					<div class="col-md-12">
						<h4>Bulk Attendance Marking</h4>
					</div>
				</div>
				<div class="row" style="margin-top: 15px; margin-bottom: 15px;">
					<div class="col-md-12">
						<div class="alert alert-info" id="student_stats" style="display: none; padding: 10px 15px;">
							<strong>Total Students:</strong> <span id="total_count">0</span> |
							<strong>Selected (Present):</strong> <span id="selected_count" style="color: green; font-weight: bold;">0</span> |
							<strong>Unselected (Absent):</strong> <span id="unselected_count" style="color: red; font-weight: bold;">0</span>
						</div>
					</div>
				</div>
				<div class="row" style="margin-top: 15px; margin-bottom: 15px;">
					<div class="col-md-12">
						<button class="btn btn-sm btn-success" id="check_all_btn">
							<i class="fa fa-check-square"></i> Check All (Mark All Present)
						</button>
						<button class="btn btn-sm btn-warning" id="uncheck_all_btn" style="margin-left: 5px;">
							<i class="fa fa-square"></i> Uncheck All (Mark All Absent)
						</button>
						<button class="btn btn-sm btn-primary" id="mark_attendance_btn" style="margin-left: 10px;">
							<i class="fa fa-save"></i> Mark Attendance for All Students
						</button>
						<span id="attendance_status" style="margin-left: 15px; font-weight: bold;"></span>
					</div>
				</div>
				<div class="row">
					<div class="col-md-12">
						<div style="border: 1px solid #ddd; border-radius: 4px; overflow: hidden; max-height: 600px; overflow-y: auto;">
							<table class="table table-bordered table-hover" style="margin-bottom: 0; table-layout: fixed;">
								<thead style="background-color: #f5f5f5; position: sticky; top: 0; z-index: 10;">
									<tr>
										<th style="width: 50px; text-align: center;">
											<input type="checkbox" id="select_all_checkbox" title="Select All">
										</th>
										<th style="width: 60px;">S.No</th>
										<th>Student ID</th>
										<th>Student Name</th>
										<th style="width: 100px; text-align: center;">Roll No</th>
										<th style="width: 120px; text-align: center;">Status</th>
									</tr>
								</thead>
								<tbody id="students_list">
									<tr>
										<td colspan="6" class="text-center text-muted" style="padding: 40px;">
											Select configuration above and click "Get Students" to load student list
										</td>
									</tr>
								</tbody>
							</table>
						</div>
					</div>
				</div>
			</div>
		`);

		this.page.main.append(this.student_list_container);

		$("#check_all_btn").on("click", () => me.check_all());
		$("#uncheck_all_btn").on("click", () => me.uncheck_all());
		$("#mark_attendance_btn").on("click", () => me.mark_attendance());
		$("#select_all_checkbox").on("change", function () {
			$(this).is(":checked") ? me.check_all() : me.uncheck_all();
		});
	}

	get_students() {
		let based_on = $("#based_on").val();
		let attendance_date = $("#attendance_date").val();

		if (!based_on) {
			frappe.msgprint(__("Please select 'Based On'"));
			return;
		}
		if (!attendance_date) {
			frappe.msgprint(__("Please select Date"));
			return;
		}
		if (frappe.datetime.get_diff(attendance_date, frappe.datetime.get_today()) > 0) {
			frappe.msgprint(__("Cannot mark attendance for future dates"));
			return;
		}

		if (based_on === "Class") {
			let class_schedule = this.class_schedule_field.get_value();
			if (!class_schedule) {
				frappe.msgprint(__("Please select Time Table"));
				return;
			}
			this.get_students_from_class_schedule(class_schedule, attendance_date);
		}
	}

	get_students_from_class_schedule(class_schedule, attendance_date) {
		let me = this;
		frappe.call({
			method: "slcm.api.bulk_attendance.get_students_from_class_schedule",
			args: { class_schedule, attendance_date },
			callback(r) {
				if (r.message) {
					me.students = r.message;
					me.render_student_list();
				}
			},
		});
	}

	render_student_list() {
		let me = this;
		let html = "";

		if (!this.students || this.students.length === 0) {
			html = `<tr><td colspan="6" class="text-center text-muted" style="padding: 40px;">No students found</td></tr>`;
		} else {
			this.selected_students.clear();
			this.students.forEach((s) => this.selected_students.add(s.student));

			this.students.forEach((student, index) => {
				let is_checked = this.selected_students.has(student.student);
				let badge = is_checked
					? '<span class="badge badge-success">Present</span>'
					: '<span class="badge badge-danger">Absent</span>';

				html += `
					<tr class="student-row" data-student="${student.student}">
						<td style="text-align: center;">
							<input type="checkbox" class="student-checkbox"
								data-student="${student.student}" ${is_checked ? "checked" : ""}>
						</td>
						<td>${index + 1}</td>
						<td><strong>${student.student}</strong></td>
						<td>${student.student_name || student.student}</td>
						<td style="text-align: center;">${student.group_roll_number || "-"}</td>
						<td class="status-cell" style="text-align: center;">${badge}</td>
					</tr>
				`;
			});
		}

		$("#students_list").html(html);
		this.update_statistics();

		$(".student-checkbox").on("change", function () {
			let student = $(this).data("student");
			let statusCell = $(this).closest("tr").find(".status-cell");
			if ($(this).is(":checked")) {
				me.selected_students.add(student);
				statusCell.html('<span class="badge badge-success">Present</span>');
			} else {
				me.selected_students.delete(student);
				statusCell.html('<span class="badge badge-danger">Absent</span>');
			}
			me.update_statistics();
			me.update_select_all_checkbox();
		});
	}

	update_statistics() {
		let total = this.students.length;
		let selected = this.selected_students.size;
		let unselected = total - selected;

		$("#total_count").text(total);
		$("#selected_count").text(selected);
		$("#unselected_count").text(unselected);
		total > 0 ? $("#student_stats").show() : $("#student_stats").hide();

		if (total > 0) {
			$("#mark_attendance_btn").html(
				`<i class="fa fa-save"></i> Mark Attendance for All ${total} Students`
			);
		}
	}

	update_select_all_checkbox() {
		let total = this.students.length;
		let selected = this.selected_students.size;
		$("#select_all_checkbox").prop("checked", total > 0 && selected === total);
	}

	check_all() {
		this.selected_students.clear();
		this.students.forEach((s) => this.selected_students.add(s.student));
		$(".student-checkbox").prop("checked", true);
		$(".status-cell").html('<span class="badge badge-success">Present</span>');
		$("#select_all_checkbox").prop("checked", true);
		this.update_statistics();
	}

	uncheck_all() {
		this.selected_students.clear();
		$(".student-checkbox").prop("checked", false);
		$(".status-cell").html('<span class="badge badge-danger">Absent</span>');
		$("#select_all_checkbox").prop("checked", false);
		this.update_statistics();
	}

	mark_attendance() {
		let me = this;
		let based_on = $("#based_on").val();
		let attendance_date = $("#attendance_date").val();

		if (!attendance_date) {
			frappe.msgprint(__("Please select Date"));
			return;
		}
		if (frappe.datetime.get_diff(attendance_date, frappe.datetime.get_today()) > 0) {
			frappe.msgprint(__("Cannot mark attendance for future dates"));
			return;
		}
		if (this.students.length === 0) {
			frappe.msgprint(__("No students to mark attendance for"));
			return;
		}

		let attendance_data = {};
		let present_count = 0;
		let absent_count = 0;

		this.students.forEach((student) => {
			if (this.selected_students.has(student.student)) {
				attendance_data[student.student] = "Present";
				present_count++;
			} else {
				attendance_data[student.student] = "Absent";
				absent_count++;
			}
		});

		let confirm_message = __(
			"Mark attendance for all {0} students?<br><br>" +
				"<strong>Present:</strong> {1} students<br>" +
				"<strong>Absent:</strong> {2} students",
			[this.students.length, present_count, absent_count]
		);

		frappe.confirm(
			confirm_message,
			function () {
				$("#attendance_status").html(
					'<span class="text-info"><i class="fa fa-spinner fa-spin"></i> Processing...</span>'
				);

				if (based_on === "Class") {
					me.mark_class_attendance(
						me.class_schedule_field.get_value(),
						attendance_date,
						attendance_data
					);
				}
			},
			function () {}
		);
	}

	mark_class_attendance(class_schedule, attendance_date, attendance_data) {
		let students_present = [];
		let students_absent = [];
		Object.keys(attendance_data).forEach((student) => {
			(attendance_data[student] === "Present" ? students_present : students_absent).push({ student });
		});

		frappe.call({
			method: "slcm.api.bulk_attendance.mark_attendance",
			args: {
				students_present,
				students_absent,
				class_schedule,
				date: attendance_date,
				based_on: "Class",
			},
			freeze: true,
			freeze_message: __("Marking attendance for all students..."),
			callback(r) {
				if (r.message) {
					let msg = __("Attendance marked successfully");
					let details = `<br><strong>Created:</strong> ${r.message.created || 0}`
						+ ` | <strong>Updated:</strong> ${r.message.updated || 0}`;
					let errors = r.message.errors || [];
					if (errors.length) {
						frappe.msgprint({ title: __("Some records failed"), message: errors.join("<br>"), indicator: "orange" });
					}
					frappe.show_alert({ message: msg + details, indicator: errors.length ? "orange" : "green" }, 8);
					$("#attendance_status").html(
						`<span class="text-success"><i class="fa fa-check-circle"></i> ${msg}</span>`
					);
					setTimeout(() => $("#attendance_status").html(""), 8000);
				}
			},
		});
	}

	clear_students() {
		this.students = [];
		this.selected_students.clear();
		$("#students_list").html(
			'<tr><td colspan="6" class="text-center text-muted" style="padding: 40px;">Select configuration above and click "Get Students" to load student list</td></tr>'
		);
		$("#student_stats").hide();
		$("#attendance_status").html("");
	}
}
