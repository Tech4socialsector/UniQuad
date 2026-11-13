// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Attendance Tool", {
	setup(frm) {
		ensure_sat_theme();
		$(frm.page.wrapper).addClass("sat-theme");
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
		// class_schedule/office_hours_group whenever
		// based_on changes, which would otherwise race with this).
		frm.__applying_route_options = true;
		frm.set_value("based_on", opts.based_on || "Class").then(() => {
			return frm.set_value({
				class_schedule: opts.class_schedule || null,
				office_hours_group: opts.office_hours_group || null,
				class_name: null,
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
			// class_name and fetch the roster here instead.
			return frm.set_value("date", opts.date || frappe.datetime.get_today());
		}).then(() => {
			frm.trigger("sync_context");
		});
	},

	/* ---------------- Field Events ---------------- */

	based_on(frm) {
		if (frm.__applying_route_options) return;
		frm.set_value("class_schedule", null);
		frm.set_value("office_hours_group", null);
		frm.set_value("class_name", null);
		frm.students_area.empty();
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

	// Resolve class_name (and section/date where relevant) from
	// whichever link is currently selected, then fetch the roster. Always
	// called explicitly rather than left to individual field "value changed"
	// triggers, since those don't fire when the incoming value matches what
	// this Single doctype already has stored.
	sync_context(frm) {
		if (frm.doc.class_schedule) {
			frappe.db.get_value("Time Table", frm.doc.class_schedule,
				["schedule_date", "repeat_frequency", "class_name", "section", "from_time", "to_time"], (r) => {
					frm.__slot = r || null;
					if (r) {
						if (r.class_name) frm.set_value("class_name", r.class_name);
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
			frm.__slot = null;
			frappe.db.get_value("Student Group", frm.doc.office_hours_group,
				"class_name", (r) => {
					if (r && r.class_name) frm.set_value("class_name", r.class_name);
					frm.trigger("fetch_students");
				});
		} else {
			frm.set_value("class_name", null);
			frm.trigger("fetch_students");
		}
	},

	fetch_students(frm) {
		if (frm.doc.class_schedule || frm.doc.office_hours_group) {
			frm.students_area.html(
				"<div class='sat-empty'>" +
				"<i class='fa fa-spinner fa-spin'></i> Fetching students..." +
				"</div>"
			);

			frappe.call({
				method: "slcm.slcm.doctype.student_attendance_tool.student_attendance_tool.get_student_attendance_records",
				args: {
					based_on: frm.doc.based_on,
					date: frm.doc.date,
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
		// Already marked for this class + date → open locked; corrections need an explicit "Edit".
		this.already_marked = this.students.some((s) => s.marked);
		this.locked = this.already_marked;
		this.saving = false;

		$(this.wrapper).empty();

		if (this.students.length) {
			this.make();
		} else {
			this.show_empty_state();
		}
	}

	make() {
		const me = this;

		let marked_info = "";
		if (this.already_marked) {
			const last = this.students
				.filter((s) => s.marked && s.marked_on)
				.sort((a, b) => (a.marked_on < b.marked_on ? 1 : -1))[0];
			marked_info = last
				? __("Last updated by {0} on {1}.", [
					frappe.utils.escape_html(frappe.user.full_name(last.marked_by) || last.marked_by),
					frappe.datetime.str_to_user(last.marked_on),
				])
				: "";
		}

		const toolbar = $(`
			<div class="sat-toolbar">
				${this.already_marked
					? `<div class="sat-marked-banner">
						<b>${this.slot_label()}</b>
						<span>${marked_info}</span>
						<span class="sat-edit-hint">${__("Click Edit Attendance to make corrections.")}</span>
					</div>`
					: ""}
				<div class="sat-actions">
					<button class="btn btn-xs sat-btn btn-check-all">${__("Check all")}</button>
					<button class="btn btn-xs sat-btn btn-uncheck-all">${__("Uncheck all")}</button>
					<button class="btn btn-xs sat-btn sat-btn-primary btn-edit" style="display:none">${__("Edit Attendance")}</button>
					<button class="btn btn-xs sat-btn sat-btn-primary btn-mark" ${this.is_future_date ? "disabled" : ""}>${this.already_marked ? __("Update Attendance") : __("Mark Attendance")}</button>
				</div>
				<div class="student-count sat-count"></div>
				${this.is_future_date
					? `<div class="sat-warning">${__("Cannot mark attendance for future dates.")}</div>`
					: ""}
			</div>
		`).appendTo(this.wrapper);

		toolbar.find(".btn-edit").on("click", () => {
			me.locked = false;
			me.apply_lock(toolbar);
		});

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

		let html = `
			<div class="sat-list-wrap">
			<table class="sat-list student-attendance-checks">
				<thead><tr>
					<th class="sat-col-check"></th>
					<th class="sat-col-no">#</th>
					<th>${__("Student Name")}</th>
					<th>${__("Student ID")}</th>
					<th class="sat-col-status">${__("Status")}</th>
				</tr></thead>
				<tbody>`;
		this.students.forEach((s, i) => {
			const checked = s.status === "Present" ? "checked" : "";
			const name = frappe.utils.escape_html(s.student_name || s.student);
			const id = frappe.utils.escape_html(s.student);
			html += `
				<tr class="sat-row">
					<td class="sat-col-check"><input type="checkbox"
						data-student="${id}"
						data-name="${name}"
						${checked}></td>
					<td class="sat-col-no">${i + 1}</td>
					<td class="sat-name">${name}</td>
					<td class="sat-meta">${s.registration_id ? frappe.utils.escape_html(String(s.registration_id)) : "–"}</td>
					<td class="sat-col-status"><span class="sat-status"></span></td>
				</tr>`;
		});
		html += "</tbody></table>";
		html += "</div>";

		$(html).appendTo(this.wrapper);

		$(this.wrapper)
			.find("input[type=checkbox]")
			.on("change", () => me.update_count(toolbar));

		$(this.wrapper).find(".sat-row").on("click", function (e) {
			if ($(e.target).is("input")) return;
			const cb = $(this).find("input[type=checkbox]");
			if (cb.prop("disabled")) return;
			cb.prop("checked", !cb.prop("checked")).trigger("change");
		});

		this.update_count(toolbar);
		this.apply_lock(toolbar);
	}

	slot_label() {
		const doc = this.frm.doc;
		const slot = this.frm.__slot;
		const date = frappe.datetime.str_to_user(doc.date);
		if (doc.class_schedule) {
			const fmt = (t) => (t ? String(t).slice(0, 5) : "");
			const timing = slot && slot.from_time && slot.to_time
				? ` (${fmt(slot.from_time)}–${fmt(slot.to_time)})`
				: "";
			return __("Attendance already marked for period {0}{1} on {2}.", [
				frappe.utils.escape_html(doc.class_schedule), timing, date,
			]);
		}
		return __("Attendance already marked for {0} on {1}.", [
			frappe.utils.escape_html(doc.office_hours_group || ""), date,
		]);
	}

	apply_lock(toolbar) {
		const locked = this.locked;
		$(this.wrapper).find("input[type=checkbox]").prop("disabled", locked);
		$(this.wrapper).find(".sat-list-wrap").toggleClass("sat-locked", locked);
		toolbar.find(".btn-check-all, .btn-uncheck-all, .btn-mark").toggle(!locked);
		toolbar.find(".btn-edit").toggle(locked && !this.is_future_date);
		toolbar.find(".sat-edit-hint").toggle(locked);
	}

	update_count(toolbar) {
		const total = this.students.length;
		const present = $(this.wrapper).find("input[type=checkbox]:checked").length;
		const absent = total - present;

		toolbar.find(".student-count").html(`
			<span class="sat-chip">${__("Total")} <b>${total}</b></span>
			<span class="sat-chip sat-chip-present">${__("Present")} <b>${present}</b></span>
			<span class="sat-chip sat-chip-absent">${__("Absent")} <b>${absent}</b></span>`);
	}

	mark_attendance(toolbar) {
		if (this.is_future_date || this.locked || this.saving) {
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

		const summary = __("Present: {0}<br>Absent: {1}", [students_present.length, students_absent.length]);
		frappe.confirm(
			this.already_marked
				? `${this.slot_label()} ${__("Overwrite it?")}<br><br>${summary}`
				: summary,
			() => {
				if (this.saving) return;
				this.saving = true;
				const btn = toolbar.find(".btn-mark").prop("disabled", true);
				frappe.call({
					method: "slcm.api.bulk_attendance.mark_attendance",
					freeze: true,
					args: {
						students_present,
						students_absent,
						class_schedule: this.frm.doc.class_schedule,
						office_hours_group: this.frm.doc.office_hours_group,
						date: this.frm.doc.date,
						based_on: this.frm.doc.based_on,
					},
					always: () => {
						this.saving = false;
						btn.prop("disabled", false);
					},
					callback: () => {
						frappe.show_alert({
							message: this.already_marked ? __("Attendance updated") : __("Attendance marked"),
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
			`<div class="sat-empty">
				${__("No Students found")}
			</div>`
		);
	}
}

/* ================= NLS THEME (#920C24 + Merriweather) ================= */

function ensure_sat_theme() {
	if (!document.getElementById("er-theme-font")) {
		$("head").append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	if (document.getElementById("sat-theme-css")) return;
	$("head").append(`<style id="sat-theme-css">
.sat-theme {
	--sat-brand: #920C24; --sat-brand-dark: #6E091B; --sat-brand-border: #E8B4BE;
	--sat-brand-soft: #F5D9DE; --sat-brand-softest: #FBEEF0;
	--sat-font: "Merriweather", Georgia, "Times New Roman", serif;
}
.sat-theme, .sat-theme .title-text, .sat-theme .navbar-breadcrumbs,
.sat-theme .control-label, .sat-theme .section-head,
.sat-theme input, .sat-theme select, .sat-theme button, .sat-theme .awesomplete li {
	font-family: var(--sat-font);
}
.sat-theme .title-text { color: var(--sat-brand); font-weight: 700; }
.sat-theme .control-label { color: #4a4a55; font-size: 12px; font-weight: 600; }
.sat-theme .form-section .section-head { color: var(--sat-brand); font-weight: 700; }
.sat-theme .form-control:focus {
	box-shadow: 0 0 0 2px var(--sat-brand-soft); border-color: var(--sat-brand-border);
}
.sat-theme .form-section:has(.student-attendance-checks, .sat-empty) {
	border-top: 3px solid var(--sat-brand);
}

/* toolbar */
.sat-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 20px; margin-bottom: 16px; }
.sat-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.sat-btn {
	background: #fff; color: var(--sat-brand); border: 1px solid var(--sat-brand-border);
	border-radius: 6px; padding: 5px 12px; font-weight: 600;
}
.sat-btn:hover { background: var(--sat-brand-softest); color: var(--sat-brand-dark); }
.sat-btn-primary { background: var(--sat-brand); color: #fff; border-color: var(--sat-brand); }
.sat-btn-primary:hover { background: var(--sat-brand-dark); color: #fff; }
.sat-btn:disabled { opacity: .5; cursor: not-allowed; }
.sat-count { display: flex; flex-wrap: wrap; gap: 8px; }
.sat-chip {
	font-size: 12px; padding: 4px 10px; border-radius: 999px;
	background: #f1f1f4; color: #33333d; border: 1px solid #e2e2e8;
}
.sat-chip b { margin-left: 4px; font-variant-numeric: tabular-nums; }
.sat-chip-present { background: #eaf6ee; color: #1f6b3a; border-color: #bfe3cb; }
.sat-chip-absent { background: var(--sat-brand-softest); color: var(--sat-brand); border-color: var(--sat-brand-border); }
.sat-warning {
	flex-basis: 100%; color: var(--sat-brand); background: var(--sat-brand-softest);
	border-left: 3px solid var(--sat-brand); padding: 6px 10px; border-radius: 4px; font-size: 12px;
}

/* student list */
.sat-list-wrap { border: 1px solid #e4e4ea; border-radius: 8px; overflow: auto; max-height: 65vh; }
.sat-list { width: 100%; border-collapse: collapse; font-size: 13px; }
.sat-list thead th {
	position: sticky; top: 0; z-index: 1; background: var(--sat-brand); color: #fff;
	font-weight: 600; font-size: 12px; text-align: left; padding: 9px 12px; white-space: nowrap;
}
.sat-list td { padding: 8px 12px; border-top: 1px solid #efeff3; vertical-align: middle; }
.sat-row { cursor: pointer; transition: background .1s; }
.sat-row:nth-child(even) { background: #fafafb; }
.sat-row:hover { background: var(--sat-brand-softest); }
.sat-col-check, .sat-col-no { width: 1%; white-space: nowrap; }
.sat-col-no { color: #7a7a86; font-variant-numeric: tabular-nums; }
.sat-col-status { width: 1%; text-align: center; }
.sat-list input[type=checkbox] { accent-color: var(--sat-brand); width: 16px; height: 16px; margin: 0; }
.sat-name { font-weight: 600; color: #22222b; }
.sat-meta { color: #6a6a76; font-size: 12px; white-space: nowrap; }
.sat-status {
	display: inline-block; min-width: 68px; padding: 3px 10px; border-radius: 999px;
	font-size: 11px; font-weight: 700; text-align: center;
	background: var(--sat-brand-softest); color: var(--sat-brand); border: 1px solid var(--sat-brand-border);
}
.sat-status::after { content: "${__("Absent")}"; }
.sat-row:has(input:checked) .sat-status { background: #eaf6ee; color: #1f6b3a; border-color: #bfe3cb; }
.sat-row:has(input:checked) .sat-status::after { content: "${__("Present")}"; }
.sat-row:not(:has(input:checked)) { box-shadow: inset 3px 0 0 var(--sat-brand); }
.sat-marked-banner {
	flex-basis: 100%; display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline;
	background: #eaf6ee; border: 1px solid #bfe3cb; border-left: 4px solid #1f6b3a;
	color: #1f4d2e; padding: 8px 12px; border-radius: 6px; font-size: 12px;
}
.sat-list-wrap.sat-locked .sat-row { cursor: default; }
.sat-list-wrap.sat-locked .sat-row:hover { background: inherit; }
.sat-list-wrap.sat-locked input[type=checkbox] { opacity: .7; }
.sat-empty { padding: 2rem; text-align: center; color: #7a7a86; font-family: var(--sat-font); }
</style>`);
}
