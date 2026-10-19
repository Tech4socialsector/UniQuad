// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Attendance Tool", {
	setup(frm) {
		frm.students_area = $("<div>").appendTo(frm.fields_dict.students_html.wrapper);

		// Office Hours Group links to Student Group - only offer Office Hours groups.
		frm.set_query("office_hours_group", () => ({
			filters: { group_based_on: "Office Hours" },
		}));
	},

	refresh(frm) {
		frm.disable_save();

		// This doctype is a Single used purely as a transient UI tool — its
		// stored/local-draft field values persist across completely unrelated
		// visits (e.g. a leftover `course` or `date` from a previous session
		// bleeding into a fresh one). Always start from a clean slate, then
		// layer on whatever came in via frappe.route_options (if anything).
		const opts = frappe.route_options || {};
		frappe.route_options = null;

		// Guard so the `based_on` handler below doesn't wipe the values
		// we're about to set right after (it normally clears
		// course_schedule/class_schedule/office_hours_group whenever
		// based_on changes, which would otherwise race with this).
		frm.__applying_route_options = true;
		frm.set_value("based_on", opts.based_on || "Course Schedule").then(() => {
			return frm.set_value({
				course_schedule: opts.course_schedule || null,
				class_schedule: opts.class_schedule || null,
				office_hours_group: opts.office_hours_group || null,
				course_offering: null,
				course: null,
				section: null,
				academic_year: null,
				academic_term: null,
				batch: null,
			});
		}).then(() => {
			frm.__applying_route_options = false;
			// This doctype is a Single, so its stored field values persist
			// across page loads — if the incoming value already equals
			// what's stored, Frappe's own "value changed" field triggers
			// won't fire. Don't rely on them: explicitly resolve
			// course_offering and fetch the roster here instead.
			return frm.set_value("date", opts.date || frappe.datetime.get_today());
		}).then(() => {
			frm.trigger("sync_context");
		});
	},

	/* ---------------- Field Events ---------------- */

	based_on(frm) {
		if (frm.__applying_route_options) return;
		frm.set_value("course_schedule", null);
		frm.set_value("class_schedule", null);
		frm.set_value("office_hours_group", null);
		frm.set_value("course_offering", null);
		frm.students_area.empty();
	},

	course_schedule(frm) {
		if (frm.__applying_route_options) return;
		frm.trigger("sync_context");
	},

	class_schedule(frm) {
		if (frm.__applying_route_options) return;
		frm.trigger("sync_context");
	},

	office_hours_group(frm) {
		if (frm.__applying_route_options) return;
		frm.trigger("sync_context");
	},

	date(frm) {
		frm.trigger("fetch_students");
	},

	/* ---------------- Data Fetch ---------------- */

	// Resolve course_offering (and section/date where relevant) from
	// whichever link is currently selected, then fetch the roster. Always
	// called explicitly rather than left to individual field "value changed"
	// triggers, since those don't fire when the incoming value matches what
	// this Single doctype already has stored.
	sync_context(frm) {
		if (frm.doc.course_schedule) {
			frappe.db.get_value("Course Schedule", frm.doc.course_schedule,
				["schedule_date", "course_offering"], (r) => {
					if (r) {
						if (r.course_offering) frm.set_value("course_offering", r.course_offering);
						if (r.schedule_date && !frm.doc.date) frm.set_value("date", r.schedule_date);
					}
					frm.trigger("fetch_students");
				});
		} else if (frm.doc.class_schedule) {
			frappe.db.get_value("Time Table", frm.doc.class_schedule,
				["schedule_date", "repeat_frequency", "course_offering", "section"], (r) => {
					if (r) {
						if (r.course_offering) frm.set_value("course_offering", r.course_offering);
						if (r.section) frm.set_value("section", r.section);

						if (!frm.doc.date) {
							// Non-recurring -> use its specific date; recurring -> default to today
							if (!r.repeat_frequency || r.repeat_frequency === "Never") {
								if (r.schedule_date) frm.set_value("date", r.schedule_date);
							} else {
								frm.set_value("date", frappe.datetime.get_today());
							}
						}
					}
					frm.trigger("fetch_students");
				});
		} else if (frm.doc.office_hours_group) {
			frappe.db.get_value("Student Group", frm.doc.office_hours_group,
				"course_offering", (r) => {
					if (r && r.course_offering) frm.set_value("course_offering", r.course_offering);
					frm.trigger("fetch_students");
				});
		} else {
			frm.set_value("course_offering", null);
			frm.trigger("fetch_students");
		}
	},

	fetch_students(frm) {
		if (frm.doc.course_schedule || frm.doc.class_schedule || frm.doc.office_hours_group) {
			frm.students_area.html(
				"<div style='padding:2rem;text-align:center'>" +
				"<i class='fa fa-spinner fa-spin'></i> Fetching students..." +
				"</div>"
			);

			frappe.call({
				method: "slcm.slcm.doctype.student_attendance_tool.student_attendance_tool.get_student_attendance_records",
				args: {
					based_on: frm.doc.based_on,
					date: frm.doc.date,
					course_schedule: frm.doc.course_schedule,
					class_schedule: frm.doc.class_schedule,
					office_hours_group: frm.doc.office_hours_group,
				},
				callback(r) {
					frm.events.get_students(frm, r.message || []);
				},
			});
		} else {
			frm.students_area.empty();
		}
	},

	get_students(frm, students) {
		frm.students_editor = new StudentsEditor(frm, frm.students_area, students);
	},
});

/* ================= STUDENTS EDITOR ================= */

class StudentsEditor {
	constructor(frm, wrapper, students) {
		this.frm = frm;
		this.wrapper = wrapper;
		this.students = students || [];
		this.is_future_date = !!(this.frm.doc.date && this.frm.doc.date > frappe.datetime.get_today());

		$(this.wrapper).empty();

		if (this.students.length) {
			this.make();
		} else {
			this.show_empty_state();
		}
	}

	make() {
		const me = this;

		const toolbar = $(`
			<div style="margin-bottom:15px">
				<button class="btn btn-default btn-xs btn-check-all">${__("Check all")}</button>
				<button class="btn btn-default btn-xs btn-uncheck-all">${__("Uncheck all")}</button>
				<button class="btn btn-primary btn-xs btn-mark" ${this.is_future_date ? "disabled" : ""}>${__("Mark Attendance")}</button>
				<span class="student-count" style="margin-left:15px;font-weight:bold"></span>
				${this.is_future_date
					? `<div class="text-danger" style="margin-top:8px;">${__("Cannot mark attendance for future dates.")}</div>`
					: ""}
			</div>
		`).appendTo(this.wrapper);

		toolbar.find(".btn-check-all").on("click", () => {
			$(me.wrapper).find("input[type=checkbox]:not(:disabled)").prop("checked", true);
			me.update_count(toolbar);
		});

		toolbar.find(".btn-uncheck-all").on("click", () => {
			$(me.wrapper).find("input[type=checkbox]").prop("checked", false);
			me.update_count(toolbar);
		});

		if (!this.is_future_date) {
			toolbar.find(".btn-mark").on("click", () => me.mark_attendance(toolbar));
		}

		let html = '<div class="row student-attendance-checks">';
		for (const s of this.students) {
			const checked = s.status === "Present" ? "checked" : "";
			html += `
				<div class="col-sm-3" style="padding:5px">
					<label>
						<input type="checkbox"
							data-student="${s.student}"
							data-name="${s.student_name || s.student}"
							${checked}>
						${s.group_roll_number ? `${s.group_roll_number} - ` : ""}${s.student_name || s.student}
					</label>
				</div>`;
		}
		html += "</div>";

		$(html).appendTo(this.wrapper);

		$(this.wrapper)
			.find("input[type=checkbox]")
			.on("change", () => me.update_count(toolbar));

		this.update_count(toolbar);
	}

	update_count(toolbar) {
		const total = this.students.length;
		const present = $(this.wrapper).find("input[type=checkbox]:checked").length;
		const absent = total - present;

		toolbar
			.find(".student-count")
			.html(__("Total: {0} | Present: {1} | Absent: {2}", [total, present, absent]));
	}

	mark_attendance(toolbar) {
		if (this.is_future_date) {
			return;
		}

		const students_present = [];
		const students_absent = [];

		$(this.wrapper)
			.find("input[type=checkbox]")
			.each(function () {
				const data = $(this).data();
				const entry = {
					student: data.student,
					student_name: data.name,
				};
				(this.checked ? students_present : students_absent).push(entry);
			});

		frappe.confirm(
			__("Present: {0}<br>Absent: {1}", [students_present.length, students_absent.length]),
			() => {
				frappe.call({
					method: "slcm.api.bulk_attendance.mark_attendance",
					freeze: true,
					args: {
						students_present,
						students_absent,
						course_schedule: this.frm.doc.course_schedule,
						class_schedule: this.frm.doc.class_schedule,
						office_hours_group: this.frm.doc.office_hours_group,
						date: this.frm.doc.date,
						based_on: this.frm.doc.based_on,
					},
					callback: () => {
						frappe.show_alert({
							message: __("Attendance marked"),
							indicator: "green",
						});
						this.frm.trigger("fetch_students");
					},
				});
			}
		);
	}

	show_empty_state() {
		$(this.wrapper).html(
			`<div class="text-center text-muted" style="padding:2rem">
				${__("No Students found")}
			</div>`
		);
	}
}
