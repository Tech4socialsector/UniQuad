// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

// Classes form → Time Table → Create Time Table / View Time Table.
// Server side: slcm.slcm.doctype.classes.class_time_table

frappe.provide("slcm.class_time_table");

const CTT_METHOD = "slcm.slcm.doctype.classes.class_time_table.";

const CTT_STEPS = [
	{ label: __("Schedule"), sections: ["s1", "s1_repeat"] },
	{ label: __("Class Participation"), sections: ["s2", "s2_weeks", "s2_preview"] },
	{ label: __("Summary"), sections: ["s3"] },
];

// Calendar colours by attendance state of a session
const CTT_STATES = {
	marked: { label: __("Attendance marked"), color: "#16a34a" },
	pending: { label: __("Held, not marked"), color: "#d97706" },
	upcoming: { label: __("Upcoming"), color: "#2563eb" },
	cancelled: { label: __("Cancelled"), color: "#9ca3af" },
};

// Class Participation records at most this many class hours per week
const CTT_MAX_CP_HOURS = 6;

const ctt_esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));

function ctt_time(t) {
	if (!t) return "";
	const [h, m] = String(t).split(":").map(Number);
	return `${h % 12 || 12}:${String(m || 0).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

function ctt_date(d) {
	return d ? frappe.datetime.str_to_user(d) : "";
}

function ctt_class_label(cls) {
	return [cls.course_name, cls.section || cls.group_name].filter(Boolean).join(" - ");
}

function ctt_load_info(frm) {
	return frappe
		.call({
			method: CTT_METHOD + "get_class_time_table_info",
			args: { class_name: frm.doc.name },
			freeze: true,
		})
		.then((r) => r.message);
}

slcm.class_time_table.open_create = (frm) => {
	ctt_inject_css();
	ctt_load_info(frm).then((info) => {
		if (!info.students.length) {
			frappe.msgprint(__("Class {0} has no enrolled students yet. Add students before creating its Time Table.", [frm.doc.name]));
			return;
		}
		new slcm.class_time_table.CreateWizard(frm, info);
	});
};

slcm.class_time_table.open_view = (frm) => {
	ctt_inject_css();
	ctt_load_info(frm).then((info) => {
		if (!info.entry_count) {
			frappe.confirm(
				__("Class {0} has no Time Table yet. Create one now?", [frm.doc.name]),
				() => new slcm.class_time_table.CreateWizard(frm, info)
			);
			return;
		}
		new slcm.class_time_table.CalendarView(frm, info);
	});
};

/* ======================= Create Time Table wizard ======================= */

slcm.class_time_table.CreateWizard = class CreateWizard {
	constructor(frm, info) {
		this.frm = frm;
		this.info = info;
		this.cls = info.class;
		this.step = 0;
		this.dates = [];        // series preview rows from the server
		this.schedule_key = null;
		this.weeks = [];        // [{start_date, end_date, students: [row]}]

		this.make_dialog();
		this.set_defaults();
		this.show_step(0);
		this.d.show();
	}

	make_dialog() {
		const me = this;
		this.d = new frappe.ui.Dialog({
			title: __("Create Time Table"),
			size: "extra-large",
			fields: [
				{ fieldtype: "HTML", fieldname: "steps_html" },

				// 1. Schedule
				{ fieldtype: "Section Break", fieldname: "s1" },
				{ fieldtype: "Data", fieldname: "title", label: __("Title"), reqd: 1 },
				{ fieldtype: "Link", fieldname: "instructor", label: __("Faculty"), options: "Faculty",
					description: __("Defaults to the class's faculty.") },
				{ fieldtype: "Link", fieldname: "venue", label: __("Venue"), options: "Venue Master", reqd: 1 },
				{ fieldtype: "Select", fieldname: "class_schedule_color", label: __("Time Table Color"),
					options: ["", "Blue", "Green", "Red", "Yellow", "Orange", "Purple", "Pink", "Gray"].join("\n") },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Date", fieldname: "schedule_date", label: __("Schedule Date"), reqd: 1,
					description: __("Date of the first class."), onchange: () => me.on_schedule_change() },
				{ fieldtype: "Time", fieldname: "from_time", label: __("From Time"), reqd: 1 },
				{ fieldtype: "Time", fieldname: "to_time", label: __("To Time"), reqd: 1 },
				{ fieldtype: "Section Break", fieldname: "s1_repeat", label: __("Repeat") },
				{ fieldtype: "Select", fieldname: "repeat_frequency", label: __("Repeat"),
					options: ["Never", "Daily", "Weekly", "Monthly"].join("\n"), default: "Weekly",
					onchange: () => me.on_schedule_change() },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Date", fieldname: "repeats_till", label: __("Repeats Till"),
					depends_on: "eval:doc.repeat_frequency != 'Never'",
					mandatory_depends_on: "eval:doc.repeat_frequency != 'Never'",
					onchange: () => me.on_schedule_change() },
				{ fieldtype: "Column Break" },
				{ fieldtype: "HTML", fieldname: "term_html" },

				// 2. Class Participation
				{ fieldtype: "Section Break", fieldname: "s2" },
				{ fieldtype: "Select", fieldname: "create_cp", label: __("Create Class Participation?"),
					options: "Yes\nNo", default: "Yes", onchange: () => me.on_cp_toggle() },
				{ fieldtype: "Column Break" },
				{ fieldtype: "HTML", fieldname: "cp_help" },
				{ fieldtype: "Section Break", fieldname: "s2_weeks", label: __("Weeks") },
				{ fieldtype: "Date", fieldname: "cp_start_date", label: __("Start Date"), onchange: () => me.render_weeks() },
				{ fieldtype: "Date", fieldname: "cp_end_date", label: __("End Date"), onchange: () => me.render_weeks() },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Int", fieldname: "cp_weeks", label: __("Number of Weeks"), non_negative: 1,
					description: __("From the schedule duration. Fewer weeks makes each one longer."),
					onchange: () => me.render_weeks() },
				{ fieldtype: "Select", fieldname: "split_method", label: __("Split Students"),
					options: ["Alphabetical blocks", "One-by-one"].join("\n"), default: "Alphabetical blocks",
					description: __("Alphabetical blocks: A–F in week 1, G–L in week 2 ... One-by-one: 1st student to week 1, 2nd to week 2 ..."),
					onchange: () => me.render_weeks() },
				{ fieldtype: "Button", fieldname: "split_btn", label: __("Split Students by Week"), click: () => me.render_weeks(true) },
				{ fieldtype: "Section Break", fieldname: "s2_preview" },
				{ fieldtype: "HTML", fieldname: "cp_preview_html" },

				// 3. Summary
				{ fieldtype: "Section Break", fieldname: "s3" },
				{ fieldtype: "HTML", fieldname: "summary_html" },
			],
			primary_action_label: __("Next"),
			primary_action: () => me.next(),
			secondary_action_label: __("Back"),
			secondary_action: () => me.back(),
		});
		this.d.$wrapper.addClass("ctt-dialog");
	}

	set_defaults() {
		const { term_start_date: start, term_end_date: end } = this.info;
		const today = frappe.datetime.get_today();
		const first = start && today < start ? start : end && today > end ? start : today;
		this.d.set_values({
			title: ctt_class_label(this.cls),
			instructor: this.cls.faculty,
			schedule_date: first,
			repeat_frequency: "Weekly",
			repeats_till: end || "",
		});
		this.d.fields_dict.term_html.$wrapper.html(`<div class="ctt-help">
			${__("Term")}: <b>${ctt_esc(this.info.term_name)}</b><br>
			${start && end ? `${ctt_date(start)} – ${ctt_date(end)}<br>` : ""}
			${__("All classes must fall within the term. Holidays and weekly offs are skipped.")}
		</div>`);
		this.d.fields_dict.cp_help.$wrapper.html(`<div class="ctt-help">
			${__("The class's {0} students are split into one Class Participation group per week. Each week, its group's participation is recorded in that week's classes (up to {1} class hours a week).", [this.info.students.length, CTT_MAX_CP_HOURS])}
		</div>`);
	}

	/* ---------------- navigation ---------------- */

	show_step(step) {
		this.step = step;
		CTT_STEPS.forEach((s, i) => {
			s.sections.forEach((fn) => {
				const sec = this.d.fields_dict[fn];
				const $w = sec && (sec.wrapper || sec.$wrapper);
				if ($w) $($w).toggle(i === step);
			});
		});
		if (step === 1) this.on_cp_toggle();
		this.render_steps();
		this.render_context();
		this.d.get_secondary_btn().toggle(step > 0);
		this.d.set_primary_action(step === CTT_STEPS.length - 1 ? __("Create Time Table") : __("Next"), () => this.next());
		if (step === 2) this.render_summary();
		this.d.$wrapper.find(".modal-body").scrollTop(0);
	}

	render_steps() {
		const html = CTT_STEPS.map((s, i) => {
			const state = i < this.step ? "done" : i === this.step ? "active" : "";
			return `<div class="ctt-step ${state}">
				<span class="ctt-step-no">${i < this.step ? "&#10003;" : i + 1}</span>
				<span class="ctt-step-label">${s.label}</span>
			</div>`;
		}).join(`<div class="ctt-step-line"></div>`);
		this.d.fields_dict.steps_html.$wrapper.html(`<div class="ctt-steps">${html}</div>`);
	}

	/** Which class this is for, kept in view on every step (own row under the header). */
	render_context() {
		let $ctx = this.d.$wrapper.find(".ctt-context");
		if (!$ctx.length) {
			$ctx = $(`<div class="ctt-context"></div>`).insertAfter(this.d.$wrapper.find(".modal-header"));
		}
		$ctx.html(ctt_context_chips(this.cls, this.info));
	}

	back() {
		if (this.step > 0) this.show_step(this.step - 1);
	}

	async next() {
		if (this.step === 0) {
			if (!(await this.validate_schedule())) return;
		} else if (this.step === 1) {
			if (!this.validate_cp()) return;
		} else {
			return this.create();
		}
		this.show_step(this.step + 1);
	}

	/* ---------------- step 1: schedule ---------------- */

	schedule_values() {
		const v = this.d.get_values(true) || {};
		const repeat = v.repeat_frequency || "Never";
		return {
			class_name: this.cls.name,
			title: v.title,
			instructor: v.instructor,
			venue: v.venue,
			class_schedule_color: v.class_schedule_color,
			schedule_date: v.schedule_date,
			from_time: v.from_time,
			to_time: v.to_time,
			repeat_frequency: repeat,
			repeats_till: repeat === "Never" ? null : v.repeats_till,
		};
	}

	last_date(s) {
		return s.repeat_frequency === "Never" ? s.schedule_date : s.repeats_till;
	}

	async validate_schedule() {
		const s = this.schedule_values();
		const missing = [
			[s.title, __("Title")], [s.venue, __("Venue")], [s.schedule_date, __("Schedule Date")],
			[s.from_time, __("From Time")], [s.to_time, __("To Time")],
			[s.repeat_frequency === "Never" || s.repeats_till, __("Repeats Till")],
		].filter(([v]) => !v).map(([, label]) => label);
		if (missing.length) {
			frappe.msgprint(__("Please fill: {0}", [missing.join(", ")]));
			return false;
		}
		if (s.from_time >= s.to_time) {
			frappe.msgprint(__("To Time must be after From Time."));
			return false;
		}
		const last = this.last_date(s);
		if (last < s.schedule_date) {
			frappe.msgprint(__("Repeats Till cannot be before the Schedule Date."));
			return false;
		}
		const { term_start_date: ts, term_end_date: te } = this.info;
		if (ts && te && (s.schedule_date < ts || last > te)) {
			frappe.msgprint({
				title: __("Outside the Academic Term"),
				message: __("{0} runs from {1} to {2}. Schedule Date and Repeats Till must be within those dates.",
					[this.info.term_name, ctt_date(ts), ctt_date(te)]),
				indicator: "red",
			});
			return false;
		}

		const r = await frappe.call({
			method: CTT_METHOD + "preview_class_time_table",
			args: { data: s },
			freeze: true,
			freeze_message: __("Checking dates..."),
		});
		const res = r.message || {};
		if ((res.errors || []).length) {
			frappe.msgprint({ title: __("Time Slot Unavailable"), message: res.errors.join("<br><br>"), indicator: "orange" });
			return false;
		}
		this.dates = res.dates || [];
		if (!this.scheduled_dates().length) {
			frappe.msgprint({
				title: __("Time Slot Unavailable"),
				message: __("None of the sessions in this schedule can be arranged: each date is either a non-teaching day or the venue or faculty is already engaged at this time. Kindly choose another time slot, venue or date range."),
				indicator: "orange",
			});
			return false;
		}

		// A changed schedule resets the participation weeks to its range
		const key = JSON.stringify([s.schedule_date, last, s.repeat_frequency]);
		if (key !== this.schedule_key) {
			this.schedule_key = key;
			const n = this.max_weeks(s.schedule_date, last);
			this.d.set_values({ cp_start_date: s.schedule_date, cp_end_date: last, cp_weeks: n });
		}
		return true;
	}

	on_schedule_change() {
		// Re-checked when leaving the step
		this.dates = [];
	}

	/** Dates a class is actually created on. */
	scheduled_dates() {
		return this.dates.filter((d) => d.status === "ok" || d.status === "faculty_warn").map((d) => d.date);
	}

	/* ---------------- step 2: class participation ---------------- */

	cp_on() {
		return this.d.get_value("create_cp") === "Yes";
	}

	on_cp_toggle() {
		const on = this.cp_on();
		["s2_weeks", "s2_preview"].forEach((fn) => {
			const sec = this.d.fields_dict[fn];
			$(sec.wrapper || sec.$wrapper).toggle(this.step === 1 && on);
		});
		const one_day = this.schedule_values().repeat_frequency === "Never";
		["cp_start_date", "cp_end_date", "cp_weeks"].forEach((f) => this.d.set_df_property(f, "read_only", one_day ? 1 : 0));
		if (on) this.render_weeks();
	}

	max_weeks(start, end) {
		if (!start || !end || end < start) return 0;
		return Math.ceil((frappe.datetime.get_day_diff(end, start) + 1) / 7);
	}

	/** Split start..end into n blocks of whole weeks (7-day blocks when n is
	 * the full number of weeks) and the students into n groups. */
	build_weeks() {
		const start = this.d.get_value("cp_start_date");
		const end = this.d.get_value("cp_end_date");
		const total = this.max_weeks(start, end);
		if (!total) return { error: __("Set a Start Date on or before the End Date.") };
		const s = this.schedule_values();
		const last = this.last_date(s);
		if (start < s.schedule_date || end > last) {
			return {
				error: __("Class Participation dates must be within the schedule: {0} to {1}.",
					[ctt_date(s.schedule_date), ctt_date(last)]),
			};
		}

		const students = this.info.students;
		let n = cint(this.d.get_value("cp_weeks")) || total;
		n = Math.max(1, Math.min(n, total, students.length));

		const weeks = [];
		for (let i = 0; i < n; i++) {
			const w0 = Math.floor((i * total) / n);
			const w1 = Math.floor(((i + 1) * total) / n);
			const e = frappe.datetime.add_days(start, 7 * w1 - 1);
			weeks.push({ start_date: frappe.datetime.add_days(start, 7 * w0), end_date: e > end ? end : e, students: [] });
		}

		if (this.d.get_value("split_method") === "One-by-one") {
			students.forEach((st, i) => weeks[i % n].students.push(st));
		} else {
			const base = Math.floor(students.length / n);
			const extra = students.length % n;
			let at = 0;
			weeks.forEach((w, i) => {
				const size = base + (i < extra ? 1 : 0);
				w.students = students.slice(at, at + size);
				at += size;
			});
		}

		const dates = this.scheduled_dates();
		weeks.forEach((w) => {
			w.classes = dates.filter((d) => d >= w.start_date && d <= w.end_date).length;
		});
		return { weeks, total, n };
	}

	render_weeks() {
		const $out = this.d.fields_dict.cp_preview_html.$wrapper;
		if (!this.cp_on()) {
			$out.empty();
			return;
		}
		const res = this.build_weeks();
		if (res.error) {
			this.weeks = [];
			$out.html(`<div class="ctt-empty ctt-bad-text">${ctt_esc(res.error)}</div>`);
			return;
		}
		this.weeks = res.weeks;
		if (cint(this.d.get_value("cp_weeks")) !== res.n) this.d.set_value("cp_weeks", res.n);

		const rows = res.weeks.map((w, i) => {
			const warn = !w.classes
				? `<span class="ctt-badge bad">${__("No class")}</span>`
				: w.classes > CTT_MAX_CP_HOURS
					? `<span class="ctt-badge warn">${__("Only {0} recorded", [CTT_MAX_CP_HOURS])}</span>`
					: "";
			const names = w.students.map((st) =>
				`<span class="ctt-pill" title="${ctt_esc(st.student_id)}">${ctt_esc(st.student_name || st.student)}</span>`).join("");
			return `<tr class="${w.classes ? "" : "ctt-row-bad"}">
				<td><b>${__("Week {0}", [i + 1])}</b></td>
				<td class="ctt-nowrap">${ctt_date(w.start_date)} – ${ctt_date(w.end_date)}</td>
				<td>${w.classes} ${warn}</td>
				<td><b>${w.students.length}</b></td>
				<td><div class="ctt-names">${names}</div></td>
			</tr>`;
		}).join("");

		const empty = res.weeks.filter((w) => !w.classes).length;
		$out.html(`
			<div class="ctt-muted" style="margin-bottom:8px">
				${__("{0} students split into {1} week(s) of the {2} in this range.", [this.info.students.length, res.n, res.total])}
				${empty ? `<span class="ctt-bad-text">${__("{0} week(s) have no class, so their students get no participation.", [empty])}</span>` : ""}
			</div>
			<div class="ctt-table-wrap"><table class="ctt-table">
				<thead><tr><th>${__("Week")}</th><th>${__("Dates")}</th><th>${__("Classes")}</th><th>${__("Students")}</th><th>${__("Names")}</th></tr></thead>
				<tbody>${rows}</tbody>
			</table></div>`);
	}

	validate_cp() {
		if (!this.cp_on()) return true;
		this.render_weeks();
		if (!this.weeks.length) {
			frappe.msgprint(__("Fix the Class Participation weeks, or choose No."));
			return false;
		}
		return true;
	}

	/* ---------------- step 3: summary + create ---------------- */

	render_summary() {
		const s = this.schedule_values();
		const item = (label, value) => `<div class="ctt-sum-item">
			<div class="ctt-sum-label">${label}</div><div class="ctt-sum-value">${value || "–"}</div></div>`;
		const created = this.scheduled_dates();
		const skipped = this.dates.filter((d) => !(d.status === "ok" || d.status === "faculty_warn"));
		const warned = this.dates.filter((d) => d.status === "faculty_warn");

		const skipped_html = skipped.length
			? `<div class="ctt-sub-title">${__("Sessions not scheduled")}</div>
				<div class="ctt-table-wrap" style="max-height:200px"><table class="ctt-table">
				<tbody>${skipped.map((d) => `<tr><td class="ctt-nowrap">${ctt_esc(d.date_fmt)}</td><td>${ctt_esc(d.note)}</td></tr>`).join("")}</tbody>
				</table></div>`
			: "";
		const warn_html = warned.length
			? `<div class="ctt-banner warn">${__("Please note: on {0} session date(s) the faculty has another session at this time ({1}). These sessions will still be scheduled; kindly confirm the faculty's availability.", [warned.length, ctt_esc(warned[0].note)])}</div>`
			: "";

		const cp_html = this.cp_on()
			? `<div class="ctt-sub-title">${__("Class Participation")}</div>
				<table class="ctt-table ctt-sum-table"><thead><tr><th>${__("Week")}</th><th>${__("Dates")}</th><th>${__("Classes")}</th><th>${__("Students")}</th></tr></thead>
				<tbody>${this.weeks.map((w, i) => `<tr><td>${__("Week {0}", [i + 1])}</td>
					<td class="ctt-nowrap">${ctt_date(w.start_date)} – ${ctt_date(w.end_date)}</td>
					<td>${w.classes}</td><td>${w.students.length}</td></tr>`).join("")}</tbody></table>`
			: `<div class="ctt-muted">${__("No Class Participation groups will be created.")}</div>`;

		this.d.fields_dict.summary_html.$wrapper.html(`
			<div class="ctt-banner ok">${__("{0} class(es) will be created, each with its Attendance Session.", [`<b>${created.length}</b>`])}</div>
			${warn_html}
			<div class="ctt-sum-grid">
				${item(__("Title"), ctt_esc(s.title))}
				${item(__("Faculty"), ctt_esc(this.faculty_label(s.instructor)))}
				${item(__("Venue"), ctt_esc(s.venue))}
				${item(__("Time"), `${ctt_time(s.from_time)} – ${ctt_time(s.to_time)}`)}
				${item(__("Repeat"), s.repeat_frequency === "Never" ? __("Once") : __(s.repeat_frequency))}
				${item(__("Dates"), `${ctt_date(s.schedule_date)} – ${ctt_date(this.last_date(s))}`)}
			</div>
			${skipped_html}
			${cp_html}`);
	}

	faculty_label(instructor) {
		if (!instructor) return "";
		if (instructor === this.cls.faculty && this.cls.faculty_name) return this.cls.faculty_name;
		return frappe.utils.get_link_title?.("Faculty", instructor) || instructor;
	}

	create() {
		const data = this.schedule_values();
		data.cp_weeks = this.cp_on()
			? this.weeks.map((w) => ({ start_date: w.start_date, end_date: w.end_date, students: w.students.map((st) => st.student) }))
			: [];
		const progress = this.show_progress(data.cp_weeks.length > 0);
		frappe.call({
			method: CTT_METHOD + "create_class_time_table",
			args: { data },
			always: () => progress.close(),
			callback: (r) => {
				if (!r.message) return;
				this.d.hide();
				const m = r.message;
				frappe.show_alert({
					message: m.groups.length
						? __("Time Table {0} created with {1} class(es) and {2} Class Participation group(s).", [m.name, m.sessions, m.groups.length])
						: __("Time Table {0} created with {1} class(es).", [m.name, m.sessions]),
					indicator: "green",
				}, 8);
			},
		});
	}

	/** Spinner with an overall percentage over the dialog while the server
	 * works. It reports progress (time_table_bulk_progress) while it makes the
	 * Class Participation groups (first 20% when there are any) and then each
	 * class of the series (the rest). */
	show_progress(with_groups) {
		const $overlay = $(`<div class="ctt-progress">
			<div class="ctt-progress-box">
				<div class="ctt-spinner"></div>
				<div class="ctt-progress-percent">0%</div>
				<div class="ctt-progress-bar"><div class="ctt-progress-fill"></div></div>
				<div class="ctt-progress-label">${__("Preparing...")}</div>
				<div class="ctt-progress-count"></div>
			</div>
		</div>`).appendTo(this.d.$wrapper.find(".modal-content"));
		this.d.$wrapper.find(".modal-footer button, .btn-modal-close").prop("disabled", true);

		let shown = 0;
		const on_progress = (p) => {
			const groups = p.label !== "Scheduling";
			const part = p.total ? p.done / p.total : 1;
			const overall = !with_groups ? part : groups ? part * 0.2 : 0.2 + part * 0.8;
			// Never step backwards (e.g. a late group event after scheduling began)
			shown = Math.max(shown, Math.min(99, Math.round(overall * 100)));
			$overlay.find(".ctt-progress-percent").text(`${shown}%`);
			$overlay.find(".ctt-progress-fill").css("width", `${shown}%`);
			$overlay.find(".ctt-progress-label").text(groups ? __("Creating Class Participation groups...") : __("Creating classes and attendance sessions..."));
			$overlay.find(".ctt-progress-count").text(p.total
				? (groups ? __("Week {0} of {1}", [p.done, p.total]) : __("Class {0} of {1}", [p.done, p.total]))
				: "");
		};
		frappe.realtime.on("time_table_bulk_progress", on_progress);
		return {
			close: () => {
				frappe.realtime.off("time_table_bulk_progress", on_progress);
				this.d.$wrapper.find(".modal-footer button, .btn-modal-close").prop("disabled", false);
				$overlay.remove();
			},
		};
	}
};

/* ======================= View Time Table (calendar) ======================= */

slcm.class_time_table.CalendarView = class CalendarView {
	constructor(frm, info) {
		this.frm = frm;
		this.info = info;
		this.cls = info.class;

		const legend = Object.values(CTT_STATES)
			.map((s) => `<span class="ctt-legend-item"><span class="ctt-dot" style="background:${s.color}"></span>${s.label}</span>`)
			.join("");
		this.d = new frappe.ui.Dialog({
			title: __("Time Table: {0}", [ctt_class_label(this.cls)]),
			size: "extra-large",
			fields: [{
				fieldtype: "HTML", fieldname: "calendar_html",
				options: `<div class="ctt-cal-view">
						<div class="ctt-legend">${legend}<span class="ctt-muted">${__("Click a class to see its attendance and class participation.")}</span></div>
						<div class="ctt-calendar"></div>
					</div>
					<div class="ctt-session-view" style="display:none"></div>`,
			}],
		});
		this.d.$wrapper.addClass("ctt-dialog");
		$(`<div class="ctt-context"></div>`)
			.html(ctt_context_chips(this.cls, info))
			.insertAfter(this.d.$wrapper.find(".modal-header"));
		this.d.show();
		frappe.require("calendar.bundle.js", () => this.render());
	}

	render() {
		const el = this.d.$wrapper.find(".ctt-calendar")[0];
		this.calendar = new frappe.FullCalendar(el, {
			plugins: frappe.FullCalendar.Plugins,
			initialView: "dayGridMonth",
			initialDate: this.info.next_date || this.info.last_date || undefined,
			headerToolbar: { left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek,listMonth" },
			buttonText: { today: __("Today"), month: __("Month"), week: __("Week"), list: __("List") },
			height: 620,
			firstDay: frappe.datetime.get_first_day_of_the_week_index(),
			eventTimeFormat: { hour: "numeric", minute: "2-digit", hour12: true },
			eventDisplay: "block",
			slotMinTime: "07:00:00",
			slotMaxTime: "21:00:00",
			events: (range, success, failure) => {
				frappe.call({
					method: CTT_METHOD + "get_class_schedule_events",
					args: { class_name: this.cls.name, start: range.startStr.slice(0, 10), end: range.endStr.slice(0, 10) },
				}).then((r) => {
					success((r.message || []).map((e) => {
						const color = (CTT_STATES[e.extendedProps.state] || CTT_STATES.upcoming).color;
						return Object.assign(e, { backgroundColor: color, borderColor: color, textColor: "#fff" });
					}));
				}, failure);
			},
			eventDidMount: (arg) => {
				const p = arg.event.extendedProps;
				const att = p.state === "marked" ? ` · ${__("Present")} ${p.present}/${p.total}` : "";
				arg.el.title = `${arg.event.title}${p.venue ? ` · ${p.venue}` : ""} · ${(CTT_STATES[p.state] || {}).label || ""}${att}`;
			},
			eventClick: (arg) => {
				arg.jsEvent.preventDefault();
				this.show_session(arg.event.id);
			},
		});
		this.calendar.render();
		// The modal finishes its open animation after render - size to the final width
		setTimeout(() => this.calendar.updateSize(), 300);
	}

	/* ---- one session: Attendance | Class Participation, in place of the calendar ---- */

	show_session(time_table) {
		frappe.call({
			method: CTT_METHOD + "get_session_details",
			args: { time_table },
			freeze: true,
		}).then((r) => {
			const data = r.message;
			if (!data) return;
			const { info, attendance: att } = data;
			const present = att.counts.Present || 0;
			const $view = this.d.$wrapper.find(".ctt-session-view");

			$view.html(`
				<div class="ctt-session-bar">
					<button class="btn btn-default btn-sm ctt-back">&larr; ${__("Back to calendar")}</button>
					<div class="ctt-session-actions">
						<button class="btn btn-default btn-sm ctt-open-tt">${__("Open Time Table")}</button>
						<button class="btn btn-primary btn-sm ctt-mark">${__("Mark Attendance")}</button>
					</div>
				</div>
				<div class="ctt-session-title">${ctt_esc(info.title || info.name)}</div>
				<div class="ctt-session-head">
					${[
						[__("Date"), info.date_fmt],
						[__("Time"), `${ctt_time(info.from_time)} – ${ctt_time(info.to_time)}`],
						[__("Venue"), info.venue],
						[__("Faculty"), info.faculty],
					].map(([label, value]) => `<div class="ctt-session-item">
						<div class="ctt-session-label">${label}</div>
						<div class="ctt-session-value">${value ? ctt_esc(value) : `<span class="ctt-muted">${__("Not set")}</span>`}</div>
					</div>`).join("")}
				</div>
				<div class="ctt-tabs">
					<button class="ctt-tab active" data-tab="att">${__("Attendance")}
						<span class="ctt-tab-count">${att.marked ? `${present}/${att.students.length}` : __("Not marked")}</span></button>
					<button class="ctt-tab" data-tab="cp">${__("Class Participation")}</button>
				</div>
				<div class="ctt-pane" data-pane="att">${ctt_attendance_html(att)}</div>
				<div class="ctt-pane" data-pane="cp" style="display:none">${ctt_participation_html(data.participation)}</div>`);

			$view.find(".ctt-tab").on("click", function () {
				const tab = $(this).data("tab");
				$view.find(".ctt-tab").removeClass("active");
				$(this).addClass("active");
				$view.find(".ctt-pane").each(function () {
					$(this).toggle($(this).data("pane") === tab);
				});
			});
			$view.find(".ctt-back").on("click", () => this.show_calendar());
			$view.find(".ctt-open-tt").on("click", () => {
				this.d.hide();
				frappe.set_route("Form", "Time Table", info.name);
			});
			$view.find(".ctt-mark").on("click", () => {
				// The Time Table entry's Class gives the roster in the tool
				frappe.route_options = { based_on: "Time Table", class_schedule: info.name, date: info.date };
				this.d.hide();
				frappe.set_route("Form", "Student Attendance Tool");
			});

			this.d.$wrapper.find(".ctt-cal-view").hide();
			$view.show();
			this.d.$wrapper.find(".modal-body").scrollTop(0);
		});
	}

	show_calendar() {
		this.d.$wrapper.find(".ctt-session-view").hide().empty();
		this.d.$wrapper.find(".ctt-cal-view").show();
		this.calendar.updateSize();
		this.calendar.refetchEvents();
	}
};

const CTT_ATT_BADGE = { Present: "ok", Absent: "bad", Late: "warn", Excused: "warn", OD: "warn", "Not Marked": "" };

function ctt_attendance_html(att) {
	let banner = "";
	if (att.session_status === "Cancelled") {
		banner = `<div class="ctt-banner bad">${__("This class was cancelled.")}</div>`;
	} else if (!att.session) {
		banner = `<div class="ctt-banner warn">${__("No Attendance Session exists for this class.")}</div>`;
	} else if (!att.marked) {
		banner = `<div class="ctt-banner warn">${__("Attendance has not been marked yet.")}</div>`;
	}
	if (!att.students.length) {
		return `${banner}<div class="ctt-empty">${__("The class has no students.")}</div>`;
	}
	const counts = ["Present", "Absent", "Late", "Excused", "OD", "Not Marked"]
		.filter((s) => att.counts[s])
		.map((s) => `<span class="ctt-badge ${CTT_ATT_BADGE[s]}">${__(s)}: ${att.counts[s]}</span>`)
		.join(" ");
	const rows = att.students.map((s, i) => `<tr>
		<td class="ctt-muted">${i + 1}</td>
		<td class="ctt-id">${ctt_esc(s.student_id)}</td>
		<td>${ctt_esc(s.student_name || s.student)}</td>
		<td><span class="ctt-badge ${CTT_ATT_BADGE[s.status] || ""}">${__(s.status)}</span></td>
	</tr>`).join("");
	return `${banner}<div class="ctt-counts">${counts}</div>
		<div class="ctt-table-wrap"><table class="ctt-table">
			<thead><tr><th>#</th><th>${__("Student ID")}</th><th>${__("Name")}</th><th>${__("Status")}</th></tr></thead>
			<tbody>${rows}</tbody>
		</table></div>`;
}

function ctt_participation_html(cp) {
	if (!cp.available) {
		return `<div class="ctt-empty">${ctt_esc(cp.reason || __("No class participation for this class."))}</div>`;
	}
	const participated = cp.students.filter((s) => s.participated).length;
	const range = cp.start_date_fmt ? `${ctt_esc(cp.start_date_fmt)} – ${ctt_esc(cp.end_date_fmt)}` : "";
	const rows = cp.students.map((s, i) => `<tr>
		<td class="ctt-muted">${i + 1}</td>
		<td class="ctt-id">${ctt_esc(s.reg_id)}</td>
		<td>${ctt_esc(s.student_name)}</td>
		<td><span class="ctt-badge ${CTT_ATT_BADGE[s.attendance] || ""}">${__(s.attendance)}</span></td>
		<td>${s.participated ? `<span class="ctt-badge ok">&#10003; ${__("Yes")}</span>` : `<span class="ctt-muted">–</span>`}</td>
		<td>${s.participated ? (s.grade ? `${s.grade} / ${cp.max_grade}` : `<span class="ctt-muted">${__("Not graded")}</span>`) : ""}</td>
	</tr>`).join("");
	return `
		<div class="ctt-cp-head">
			<div><b>${ctt_esc(cp.week_name)}</b> <span class="ctt-muted">${range}</span></div>
			<div class="ctt-muted">${__("{0} of {1} class(es) this week", [ctt_esc(cp.slot_label), cp.classes_in_week])} · ${ctt_esc(cp.group)}</div>
		</div>
		${cp.recorded
			? `<div class="ctt-counts"><span class="ctt-badge ok">${__("Participated")}: ${participated}</span>
				<span class="ctt-badge">${__("Group")}: ${cp.students.length}</span></div>`
			: `<div class="ctt-banner warn">${__("Participation has not been recorded for this hour yet.")}</div>`}
		<div class="ctt-table-wrap"><table class="ctt-table">
			<thead><tr><th>#</th><th>${__("Student ID")}</th><th>${__("Name")}</th><th>${__("Attendance")}</th><th>${__("Participated")}</th><th>${__("Mark")}</th></tr></thead>
			<tbody>${rows}</tbody>
		</table></div>`;
}

function ctt_context_chips(cls, info) {
	const chip = (label, value) => value
		? `<span class="ctt-ctx-chip"><span class="ctt-ctx-label">${label}:</span> ${ctt_esc(value)}</span>`
		: "";
	return [
		chip(__("Class"), cls.name),
		chip(__("Course"), cls.course_name),
		cls.section ? chip(__("Section"), cls.section) : chip(__("Group"), cls.group_name),
		chip(__("Programme"), cls.programme),
		chip(__("Term"), info.term_name),
		chip(__("Students"), info.students.length),
	].join("");
}

function ctt_inject_css() {
	if (document.getElementById("class-time-table-css")) return;
	const style = document.createElement("style");
	style.id = "class-time-table-css";
	style.textContent = `
		.ctt-dialog .ctt-context {
			display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 20px;
			border-bottom: 1px solid var(--border-color); background: var(--subtle-fg, var(--control-bg));
		}
		.ctt-dialog .ctt-ctx-chip {
			padding: 2px 10px; border-radius: 20px; font-size: 12px; background: var(--card-bg, #fff);
			border: 1px solid var(--border-color); max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
		}
		.ctt-dialog .ctt-ctx-label { font-weight: 500; color: var(--text-muted); }
		.ctt-dialog .ctt-steps {
			display: flex; align-items: center; padding: 4px 0 16px; margin-bottom: 4px;
			border-bottom: 1px solid var(--border-color); overflow-x: auto;
		}
		.ctt-dialog .ctt-step { display: flex; align-items: center; gap: 8px; white-space: nowrap; color: var(--text-muted); }
		.ctt-dialog .ctt-step-no {
			width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
			font-size: 12px; font-weight: 700; border: 1px solid var(--border-color); background: var(--control-bg);
		}
		.ctt-dialog .ctt-step-label { font-size: 13px; font-weight: 600; }
		.ctt-dialog .ctt-step.active { color: var(--text-color); }
		.ctt-dialog .ctt-step.active .ctt-step-no { background: var(--primary); border-color: var(--primary); color: #fff; }
		.ctt-dialog .ctt-step.done .ctt-step-no { background: var(--green-500, #22c55e); border-color: transparent; color: #fff; }
		.ctt-dialog .ctt-step-line { flex: 1 1 24px; min-width: 24px; height: 1px; background: var(--border-color); margin: 0 10px; }
		.ctt-dialog .ctt-help { color: var(--text-muted); font-size: 12.5px; line-height: 1.6; padding-top: 4px; }
		.ctt-dialog .ctt-muted { color: var(--text-muted); font-size: 12px; }
		.ctt-dialog .ctt-bad-text { color: var(--red-600, #b02a37); font-size: 12px; font-weight: 600; margin-left: 6px; }
		.ctt-dialog .ctt-nowrap { white-space: nowrap; }
		.ctt-dialog .ctt-table-wrap { max-height: 46vh; overflow: auto; border: 1px solid var(--border-color); border-radius: 8px; }
		.ctt-dialog .ctt-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.ctt-dialog .ctt-table th {
			position: sticky; top: 0; z-index: 1; background: var(--subtle-fg, var(--control-bg));
			font-size: 11.5px; font-weight: 600; text-transform: uppercase; color: var(--text-muted);
		}
		.ctt-dialog .ctt-table th, .ctt-dialog .ctt-table td {
			padding: 7px 12px; border-bottom: 1px solid var(--border-color); text-align: left; vertical-align: top;
		}
		.ctt-dialog .ctt-table tbody tr:last-child td { border-bottom: none; }
		.ctt-dialog .ctt-row-bad td { background: var(--red-highlight-color, #fef2f2); }
		.ctt-dialog .ctt-names { display: flex; flex-wrap: wrap; gap: 4px; max-height: 96px; overflow: auto; }
		.ctt-dialog .ctt-pill {
			padding: 1px 8px; border-radius: 20px; font-size: 11.5px;
			background: var(--control-bg); border: 1px solid var(--border-color); white-space: nowrap;
		}
		.ctt-dialog .ctt-id { font-family: var(--font-family-monospace, monospace); font-weight: 600; white-space: nowrap; }
		.ctt-dialog .ctt-badge {
			display: inline-block; padding: 2px 9px; border-radius: 20px; font-size: 11.5px; font-weight: 600;
			background: var(--control-bg); color: var(--text-muted); white-space: nowrap;
		}
		.ctt-dialog .ctt-badge.ok { background: var(--green-highlight-color, #e6f4ea); color: var(--green-700, #166534); }
		.ctt-dialog .ctt-badge.warn { background: var(--yellow-highlight-color, #fef3c7); color: var(--yellow-800, #92400e); }
		.ctt-dialog .ctt-badge.bad { background: var(--red-highlight-color, #fdecea); color: var(--red-600, #b02a37); }
		.ctt-dialog .ctt-banner { padding: 10px 14px; border-radius: 8px; margin-bottom: 10px; font-size: 13px; }
		.ctt-dialog .ctt-banner.ok { background: var(--green-highlight-color, #e6f4ea); color: var(--green-700, #166534); }
		.ctt-dialog .ctt-banner.warn { background: var(--yellow-highlight-color, #fef3c7); color: var(--yellow-800, #92400e); }
		.ctt-dialog .ctt-banner.bad { background: var(--red-highlight-color, #fdecea); color: var(--red-600, #b02a37); }
		.ctt-dialog .ctt-empty {
			padding: 28px 16px; text-align: center; color: var(--text-muted);
			border: 1px dashed var(--border-color); border-radius: 8px;
		}
		.ctt-dialog .ctt-sum-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin-bottom: 14px; }
		.ctt-dialog .ctt-sum-item { border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 12px; }
		.ctt-dialog .ctt-sum-label { font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; }
		.ctt-dialog .ctt-sum-value { font-size: 14px; margin-top: 2px; }
		.ctt-dialog .ctt-sum-table { max-width: 560px; margin-bottom: 12px; border: 1px solid var(--border-color); }
		.ctt-dialog .ctt-sub-title { font-size: 12px; font-weight: 600; text-transform: uppercase; color: var(--text-muted); margin: 14px 0 6px; }
		.ctt-dialog .ctt-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-bottom: 10px; font-size: 12px; }
		.ctt-dialog .ctt-legend-item { display: inline-flex; align-items: center; gap: 6px; }
		.ctt-dialog .ctt-dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
		.ctt-dialog .ctt-calendar .fc-event { cursor: pointer; }
		.ctt-dialog .ctt-calendar .fc .fc-toolbar-title { font-size: 16px; font-weight: 600; }
		.ctt-dialog .ctt-calendar .fc .fc-button-primary {
			background: var(--control-bg); color: var(--text-color); border-color: var(--border-color); box-shadow: none;
			font-size: 12.5px; text-transform: none;
		}
		.ctt-dialog .ctt-calendar .fc .fc-button-primary:not(:disabled).fc-button-active,
		.ctt-dialog .ctt-calendar .fc .fc-button-primary:not(:disabled):active {
			background: var(--primary); border-color: var(--primary); color: #fff;
		}
		.ctt-dialog .ctt-session-bar {
			display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px;
			padding-bottom: 12px; margin-bottom: 12px; border-bottom: 1px solid var(--border-color);
		}
		.ctt-dialog .ctt-session-actions { display: flex; gap: 8px; }
		.ctt-dialog .ctt-session-title { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
		.ctt-dialog .ctt-session-head {
			display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; margin: 8px 0 14px;
		}
		.ctt-dialog .ctt-session-item { border: 1px solid var(--border-color); border-radius: 8px; padding: 8px 12px; min-width: 0; }
		.ctt-dialog .ctt-session-label { font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--text-muted); }
		.ctt-dialog .ctt-session-value { font-size: 13.5px; font-weight: 600; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
		.ctt-dialog .modal-content { position: relative; }
		.ctt-dialog .ctt-progress {
			position: absolute; inset: 0; z-index: 10; display: flex; align-items: center; justify-content: center;
			background: color-mix(in srgb, var(--modal-bg, var(--card-bg, #fff)) 88%, transparent); border-radius: inherit;
		}
		.ctt-dialog .ctt-progress-box { width: min(360px, 90%); text-align: center; }
		.ctt-dialog .ctt-spinner {
			width: 44px; height: 44px; margin: 0 auto 12px; border-radius: 50%;
			border: 4px solid var(--border-color); border-top-color: var(--primary); animation: ctt-spin 0.9s linear infinite;
		}
		@keyframes ctt-spin { to { transform: rotate(360deg); } }
		.ctt-dialog .ctt-progress-percent { font-size: 28px; font-weight: 700; font-variant-numeric: tabular-nums; }
		.ctt-dialog .ctt-progress-bar { height: 8px; border-radius: 8px; background: var(--control-bg); overflow: hidden; margin: 10px 0; }
		.ctt-dialog .ctt-progress-fill { height: 100%; width: 0; background: var(--primary); transition: width 0.3s ease; }
		.ctt-dialog .ctt-progress-label { font-size: 13.5px; font-weight: 600; }
		.ctt-dialog .ctt-progress-count { font-size: 12px; color: var(--text-muted); margin-top: 2px; min-height: 16px; }
		.ctt-dialog .ctt-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border-color); margin-bottom: 12px; }
		.ctt-dialog .ctt-tab {
			background: none; border: none; border-bottom: 2px solid transparent; padding: 8px 12px; margin-bottom: -1px;
			font-size: 13px; font-weight: 600; color: var(--text-muted);
		}
		.ctt-dialog .ctt-tab.active { color: var(--text-color); border-bottom-color: var(--primary); }
		.ctt-dialog .ctt-tab-count { margin-left: 6px; padding: 1px 8px; border-radius: 20px; background: var(--control-bg); font-size: 11px; }
		.ctt-dialog .ctt-counts { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
		.ctt-dialog .ctt-cp-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px; margin-bottom: 10px; font-size: 13px; }
	`;
	document.head.appendChild(style);
}
