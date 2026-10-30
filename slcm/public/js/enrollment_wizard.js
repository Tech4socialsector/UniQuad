// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

/*****************************************************
 * STUDENT MASTER → Action → Enroll
 * Step-by-step dialog:
 *   1. Academic Setup  academic year (current by default), term,
 *                      programme, batch, year
 *   2. Students        registration Completed, not yet enrolled
 *   3. Student ID      format like M26####, numbered alphabetically
 *   4. Sections        Mid-off / One-by-one (split by room capacity),
 *                      Manual or Upload
 *   5. Summary         enroll
 * Server side: slcm/slcm/doctype/student_master/enrollment_wizard.py
 *****************************************************/
frappe.provide("slcm.enrollment");

const WIZARD_API = "slcm.slcm.doctype.student_master.enrollment_wizard.";

const WIZARD_STEPS = [
	{ label: __("Academic Setup"), sections: ["s1"] },
	{ label: __("Students"), sections: ["s2"] },
	{ label: __("Student ID"), sections: ["s3", "s3_preview"] },
	{ label: __("Sections"), sections: ["s4", "s4_rows", "s4_upload", "s4_preview"] },
	{ label: __("Summary"), sections: ["s5"] },
];

slcm.enrollment.open_wizard = function (listview) {
	const preselected = (listview && listview.get_checked_items()) || [];
	new slcm.enrollment.EnrollmentWizard(listview, preselected);
};

slcm.enrollment.EnrollmentWizard = class EnrollmentWizard {
	constructor(listview, preselected) {
		this.listview = listview;
		this.preselected = new Set(preselected.map((r) => r.name));
		this.step = 0;
		this.students = [];        // candidates from the server, alphabetical
		this.loaded_key = null;    // [programme, academic year] the list was loaded for
		this.selected = new Set();
		this.ids = [];             // Student ID preview rows, alphabetical
		this.ids_key = null;       // inputs the ID preview was built from
		this.id_result = null;     // {summary, all_have_ids} of the preview
		this.assign_new = new Set(); // students with an ID who get a new one anyway
		this.sections = {};        // student -> section
		this.sections_key = null;
		this.all_sections = [];
		this.search = "";

		inject_wizard_css();
		this.make_dialog();
		this.set_defaults();
		this.show_step(0);
		this.d.show();
	}

	make_dialog() {
		const me = this;
		this.d = new frappe.ui.Dialog({
			title: __("Enroll Students"),
			size: "extra-large",
			fields: [
				{ fieldtype: "HTML", fieldname: "steps_html" },

				// 1. Academic Setup
				{ fieldtype: "Section Break", fieldname: "s1" },
				{
					fieldtype: "Link", fieldname: "academic_year", label: __("Academic Year"), options: "Academic Year", reqd: 1,
					onchange: () => me.on_academic_year_change(),
				},
				{
					fieldtype: "Link", fieldname: "academic_term", label: __("Academic Term"), options: "Academic Term", reqd: 1,
					get_query: () => me.year_filter(),
					description: __("Becomes the student's Ongoing term in the Academic Log."),
					onchange: () => me.render_context(),
				},
				{ fieldtype: "Int", fieldname: "year_no", label: __("Year"), default: 1, reqd: 1, non_negative: 1,
					onchange: () => me.render_context() },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Link", fieldname: "programme", label: __("Programme"), options: "Programme", reqd: 1,
					onchange: () => me.render_context() },
				{
					fieldtype: "Link", fieldname: "batch", label: __("Batch"), options: "SLCM Batch", reqd: 1,
					get_query: () => me.year_filter(),
					description: __("Set on every selected student."),
					onchange: () => me.render_context(),
				},

				// 2. Students
				{ fieldtype: "Section Break", fieldname: "s2" },
				{ fieldtype: "HTML", fieldname: "students_html" },

				// 3. Student ID
				{ fieldtype: "Section Break", fieldname: "s3" },
				{
					fieldtype: "Data", fieldname: "id_format", label: __("Student ID Format"),
					description: __("Use # for the running number, e.g. M26### gives M26001, M26002 ... Not needed when every student already has an ID."),
					onchange: () => me.mark_ids_stale(),
				},
				{ fieldtype: "HTML", fieldname: "programme_codes_html" },
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Select", fieldname: "numbering", label: __("Numbering"),
					options: ["Fill gaps", "Continue after highest"].join("\n"), default: "Fill gaps",
					description: __("Fill gaps: lowest free numbers from 001. Continue after highest: after the highest number in use. Numbers already held are always skipped."),
					onchange: () => me.mark_ids_stale(),
				},
				{
					fieldtype: "Int", fieldname: "start_from", label: __("Start From"), non_negative: 1,
					description: __("Optional: first number to try."),
					onchange: () => me.mark_ids_stale(),
				},
				{
					fieldtype: "Check", fieldname: "renumber_existing", label: __("Re-number students who already have a Student ID"),
					description: __("Off: existing Student IDs are kept. Tick a single student in the preview to give only them a new ID."),
					onchange: () => me.on_renumber_change(),
				},
				{ fieldtype: "Button", fieldname: "order_btn", label: __("Order Alphabetically & Preview IDs"), click: () => me.preview_ids() },
				{ fieldtype: "Section Break", fieldname: "s3_preview" },
				{ fieldtype: "HTML", fieldname: "id_preview_html" },

				// 4. Sections
				{ fieldtype: "Section Break", fieldname: "s4" },
				{ fieldtype: "HTML", fieldname: "keep_banner" },
				{
					fieldtype: "Check", fieldname: "keep_sections", label: __("Keep each student's current section"), default: 1,
					description: __("Students who already have a section keep it; only the others are assigned below. Untick to re-assign everyone."),
					onchange: () => me.on_keep_sections_change(),
				},
				{
					fieldtype: "Select", fieldname: "assignment_type", label: __("Section Assignment"),
					options: ["Mid-off", "One-by-one", "Manual", "Upload"].join("\n"), default: "Mid-off", reqd: 1,
					onchange: () => me.on_assignment_type_change(),
				},
				{ fieldtype: "Column Break" },
				{ fieldtype: "HTML", fieldname: "assignment_help" },
				{ fieldtype: "Section Break", fieldname: "s4_rows", label: __("Sections & Room Capacity") },
				{
					fieldtype: "Table", fieldname: "section_rows", label: __("Sections"), in_place_edit: true, data: [],
					fields: [
						{ fieldtype: "Link", fieldname: "section", label: __("Section"), options: "Section", in_list_view: 1, reqd: 1, columns: 5 },
						{ fieldtype: "Int", fieldname: "capacity", label: __("Room Capacity"), in_list_view: 1, columns: 3,
							description: __("Empty = no limit") },
					],
				},
				{ fieldtype: "Button", fieldname: "split_btn", label: __("Split & Preview"), click: () => me.preview_split() },
				{ fieldtype: "Section Break", fieldname: "s4_upload", label: __("Upload Sections") },
				{ fieldtype: "Button", fieldname: "download_tpl", label: __("Download Template"), click: () => me.download_template() },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Attach", fieldname: "section_file", label: __("Upload Filled Template"), onchange: () => me.read_upload() },
				{ fieldtype: "Section Break", fieldname: "s4_preview" },
				{ fieldtype: "HTML", fieldname: "section_preview_html" },

				// 5. Summary
				{ fieldtype: "Section Break", fieldname: "s5" },
				{ fieldtype: "HTML", fieldname: "summary_html" },
			],
			primary_action_label: __("Next"),
			primary_action: () => me.next(),
			secondary_action_label: __("Back"),
			secondary_action: () => me.back(),
		});
		this.d.$wrapper.addClass("enroll-wizard");

		const $students = this.d.fields_dict.students_html.$wrapper;
		$students.on("input", ".ew-search", (e) => {
			me.search = e.target.value || "";
			me.render_students();
		});
		$students.on("change", ".ew-check", (e) => {
			const name = $(e.target).attr("data-name");
			e.target.checked ? me.selected.add(name) : me.selected.delete(name);
			me.render_student_count();
		});
		$students.on("change", ".ew-check-all", (e) => {
			me.visible_students().forEach((s) => (e.target.checked ? me.selected.add(s.name) : me.selected.delete(s.name)));
			me.render_students();
		});
		this.d.fields_dict.id_preview_html.$wrapper.on("change", ".ew-assign-new", (e) => {
			const name = $(e.target).attr("data-name");
			if (e.target.checked && !me.d.get_value("id_format")) {
				e.target.checked = false;
				frappe.msgprint(__("Enter the Student ID format first, e.g. M26###, to give this student a new ID."));
				return;
			}
			e.target.checked ? me.assign_new.add(name) : me.assign_new.delete(name);
			me.preview_ids();
		});
		this.d.fields_dict.section_preview_html.$wrapper.on("change", ".ew-section-select", (e) => {
			me.sections[$(e.target).attr("data-name")] = e.target.value || undefined;
			me.render_section_preview();
		});
	}

	set_defaults() {
		frappe.call(WIZARD_API + "get_wizard_defaults").then(async ({ message }) => {
			const m = message || {};
			// Term and Batch are filtered by the academic year, so it has to be
			// in place before they are set (and validated against it).
			this._setting_defaults = true;
			await this.d.set_value("academic_year", m.academic_year || "");
			this._setting_defaults = false;
			await this.d.set_value("academic_term", m.academic_term || "");
			await this.d.set_value("batch", m.batch || "");
		});
		// Programme of the students checked in the list, when they share one.
		if (this.preselected.size) {
			frappe.db
				.get_list("Student Master", {
					filters: { name: ["in", [...this.preselected]] },
					fields: ["programme_of_study"],
					limit: 0,
				})
				.then((rows) => {
					const programmes = [...new Set(rows.map((r) => r.programme_of_study).filter(Boolean))];
					if (programmes.length === 1) this.d.set_value("programme", programmes[0]);
				});
		}
		frappe.db.get_list("Section", { fields: ["name"], limit: 0, order_by: "name asc" }).then((rows) => {
			this.all_sections = rows.map((r) => r.name);
		});
		frappe.db.get_list("Programme", { fields: ["name", "program_code"], limit: 0, order_by: "program_code asc" }).then((rows) => {
			this.programme_codes = rows.filter((r) => r.program_code);
			this.render_programme_codes();
		});
	}

	/** Key under the Student ID format: {code} - {programme}, the selected one first and highlighted. */
	render_programme_codes() {
		const rows = this.programme_codes || [];
		const $w = this.d.fields_dict.programme_codes_html.$wrapper;
		if (!rows.length) {
			$w.empty();
			return;
		}
		const esc = frappe.utils.escape_html;
		const selected = this.d.get_value("programme");
		const sorted = [...rows].sort((a, b) => (b.name === selected) - (a.name === selected));
		$w.html(`
			<div class="ew-codes">
				<div class="ew-codes-title">${__("Programme codes")}</div>
				<ul>${sorted.map((r) => `
					<li class="${r.name === selected ? "is-selected" : ""}">
						<span class="ew-code">${esc(r.program_code)}</span> – ${esc(r.name)}
						${r.name === selected ? `<span class="ew-codes-tag">${__("Selected")}</span>` : ""}
					</li>`).join("")}
				</ul>
			</div>`);
	}

	on_academic_year_change() {
		this.render_context();
		if (this._setting_defaults) return;
		const academic_year = this.d.get_value("academic_year");
		frappe.call(WIZARD_API + "get_year_defaults", { academic_year }).then(async ({ message }) => {
			const m = message || {};
			await this.d.set_value("academic_term", m.academic_term || "");
			await this.d.set_value("batch", m.batch || "");
		});
	}

	year_filter() {
		const academic_year = this.d.get_value("academic_year");
		return { filters: academic_year ? { academic_year } : {} };
	}

	/* ---------------- navigation ---------------- */

	show_step(step) {
		this.step = step;
		WIZARD_STEPS.forEach((s, i) => {
			s.sections.forEach((fn) => {
				const sec = this.d.fields_dict[fn];
				const $w = sec && (sec.wrapper || sec.$wrapper);
				if ($w) $($w).toggle(i === step);
			});
		});
		this.render_steps();
		this.render_context();
		this.d.get_secondary_btn().toggle(step > 0);
		this.d.set_primary_action(step === WIZARD_STEPS.length - 1 ? __("Enroll") : __("Next"), () => this.next());
		if (step === 2) {
			this.render_programme_codes();
			this.enter_ids_step();
		}
		if (step === 3) this.on_assignment_type_change();
		this.d.$wrapper.find(".modal-body").scrollTop(0);
	}

	render_steps() {
		const html = WIZARD_STEPS.map((s, i) => {
			const state = i < this.step ? "done" : i === this.step ? "active" : "";
			return `<div class="ew-step ${state}">
				<span class="ew-step-no">${i < this.step ? "&#10003;" : i + 1}</span>
				<span class="ew-step-label">${s.label}</span>
			</div>`;
		}).join(`<div class="ew-step-line"></div>`);
		this.d.fields_dict.steps_html.$wrapper.html(`<div class="ew-steps">${html}</div>`);
	}

	/** Bar right under the dialog header: what this enrollment is for, kept
	 * in view on every step. Its own row, so it never crowds the title. */
	render_context() {
		const $header = this.d.$wrapper.find(".modal-header");
		let $ctx = this.d.$wrapper.find(".ew-context");
		if (!$ctx.length) {
			$ctx = $(`<div class="ew-context"></div>`).insertAfter($header);
		}
		const v = this.d.get_values(true) || {};
		const esc = frappe.utils.escape_html;
		const chip = (label, value) => value
			? `<span class="ew-ctx-chip"><span class="ew-ctx-label">${label}:</span> ${esc(String(value))}</span>`
			: "";
		const chips = [
			chip(__("Programme"), v.programme),
			chip(__("Academic Year"), v.academic_year),
			chip(__("Batch"), v.batch),
			chip(__("Term"), v.academic_term && (frappe.utils.get_link_title?.("Academic Term", v.academic_term) || v.academic_term)),
			chip(__("Year"), v.year_no),
		].join("");
		$ctx.html(chips ? `<span class="ew-ctx-title">${__("Enrolling for")}</span>${chips}` : "").toggle(!!chips);
	}

	back() {
		if (this.step > 0) this.show_step(this.step - 1);
	}

	async next() {
		const ok = await [
			() => this.leave_setup(),
			() => this.leave_students(),
			() => this.leave_ids(),
			() => this.leave_sections(),
			() => this.enroll(),
		][this.step]();
		if (ok && this.step < WIZARD_STEPS.length - 1) {
			this.show_step(this.step + 1);
		}
	}

	/* ---------------- 1. academic setup ---------------- */

	async leave_setup() {
		const v = this.d.get_values(true);
		const missing = [
			["academic_year", __("Academic Year")],
			["academic_term", __("Academic Term")],
			["programme", __("Programme")],
			["batch", __("Batch")],
		].filter(([f]) => !v[f]).map(([, l]) => l);
		if (!(v.year_no > 0)) missing.push(__("Year"));
		if (missing.length) {
			frappe.msgprint(__("Please fill: {0}", [missing.join(", ")]));
			return false;
		}
		const key = JSON.stringify([v.programme, v.academic_year]);
		if (this.loaded_key !== key) {
			await this.load_students(v.programme, v.academic_year);
			this.loaded_key = key;
		}
		return true;
	}

	async load_students(programme, academic_year) {
		const { message } = await frappe.call({
			method: WIZARD_API + "get_enrollable_students",
			args: { programme, academic_year },
			freeze: true,
			freeze_message: __("Loading students..."),
		});
		this.students = message || [];
		this.loaded_programme = programme;
		this.loaded_academic_year = academic_year;
		const in_list = this.students.filter((s) => this.preselected.has(s.name));
		this.selected = new Set((in_list.length ? in_list : this.students).map((s) => s.name));
		this.search = "";
		this.render_students();
	}

	/* ---------------- 2. students ---------------- */

	visible_students() {
		const q = this.search.trim().toLowerCase();
		if (!q) return this.students;
		return this.students.filter((s) =>
			[s.student_name, s.registration_id, s.name].some((x) => (x || "").toLowerCase().includes(q))
		);
	}

	render_students() {
		const $w = this.d.fields_dict.students_html.$wrapper;
		if (!this.students.length) {
			$w.html(`<div class="ew-empty">${__(
				"No students with registration status Completed in {0} are waiting to be enrolled in {1}.",
				[frappe.utils.escape_html(this.loaded_academic_year || ""), frappe.utils.escape_html(this.loaded_programme || "")]
			)}</div>`);
			return;
		}
		const rows = this.visible_students();
		const all_checked = rows.length && rows.every((s) => this.selected.has(s.name));
		const esc = frappe.utils.escape_html;
		$w.html(`
			<div class="ew-toolbar">
				<input type="text" class="form-control ew-search" placeholder="${__("Search name or ID")}" value="${esc(this.search)}">
				<span class="ew-count"></span>
			</div>
			<div class="ew-table-wrap">
				<table class="ew-table">
					<thead><tr>
						<th class="ew-col-check"><input type="checkbox" class="ew-check-all" ${all_checked ? "checked" : ""}></th>
						<th>${__("Student")}</th><th>${__("Student ID")}</th><th>${__("Gender")}</th>
						<th>${__("Batch")}</th><th>${__("Section")}</th>
					</tr></thead>
					<tbody>${rows.map((s) => `
						<tr>
							<td class="ew-col-check"><input type="checkbox" class="ew-check" data-name="${esc(s.name)}" ${this.selected.has(s.name) ? "checked" : ""}></td>
							<td><div class="ew-name">${esc(s.student_name || s.name)}</div><div class="ew-sub">${esc(s.name)}</div></td>
							<td>${s.registration_id ? esc(s.registration_id) : `<span class="ew-muted">${__("None")}</span>`}</td>
							<td>${esc(s.gender || "")}</td>
							<td>${esc(s.batch || "")}</td>
							<td>${esc(s.section || "")}</td>
						</tr>`).join("")}
					</tbody>
				</table>
			</div>`);
		// Re-rendering on every keystroke drops focus: put it back.
		if (this.search) {
			const input = $w.find(".ew-search").get(0);
			input.focus();
			input.setSelectionRange(this.search.length, this.search.length);
		}
		this.render_student_count();
	}

	render_student_count() {
		this.d.fields_dict.students_html.$wrapper
			.find(".ew-count")
			.html(__("{0} of {1} selected", [`<b>${this.selected.size}</b>`, this.students.length]));
	}

	leave_students() {
		if (!this.selected.size) {
			frappe.msgprint(__("Select at least one student."));
			return false;
		}
		return true;
	}

	/* ---------------- 3. student id ---------------- */

	current_ids_key() {
		const v = this.d.get_values(true);
		return JSON.stringify([
			v.id_format || "", v.numbering || "", v.start_from || 0, v.renumber_existing || 0,
			[...this.selected].sort(), [...this.assign_new].sort(),
		]);
	}

	/** Entering the step: when every selected student already has an ID
	 * there is nothing to assign, so show that straight away. */
	enter_ids_step() {
		[...this.assign_new].forEach((s) => this.selected.has(s) || this.assign_new.delete(s));
		const chosen = this.students.filter((s) => this.selected.has(s.name));
		const all_have_ids = chosen.length && chosen.every((s) => s.registration_id);
		if (this.ids_key === this.current_ids_key()) return;
		if (all_have_ids && !this.d.get_value("renumber_existing") && !this.assign_new.size) {
			this.preview_ids();
		} else if (this.ids.length) {
			this.mark_ids_stale();
		}
	}

	on_renumber_change() {
		if (this.d.get_value("renumber_existing")) {
			frappe.confirm(
				__("Every selected student, including those who already have a Student ID, will get a new ID in the format. Existing IDs will be replaced. Continue?"),
				() => this.mark_ids_stale(),
				() => this.d.set_value("renumber_existing", 0)
			);
		} else {
			this.mark_ids_stale();
		}
	}

	mark_ids_stale() {
		if (this.ids.length && this.ids_key !== this.current_ids_key()) {
			this.d.fields_dict.id_preview_html.$wrapper
				.find(".ew-stale")
				.html(__("Settings changed: click Order Alphabetically & Preview IDs again."));
		}
	}

	async preview_ids() {
		const v = this.d.get_values(true);
		const key = this.current_ids_key();
		try {
			const { message } = await frappe.call({
				method: WIZARD_API + "preview_student_ids",
				args: {
					students: [...this.selected],
					id_format: v.id_format || null,
					numbering: v.numbering,
					start_from: v.start_from || null,
					renumber_existing: v.renumber_existing || 0,
					assign_new: [...this.assign_new],
				},
				freeze: true,
			});
			const m = message || {};
			this.ids = m.rows || [];
			this.id_result = m;
			this.ids_key = key;
		} catch (e) {
			// The server's message (e.g. format missing) is already shown.
			return;
		}
		this.render_id_preview();
	}

	render_id_preview() {
		const esc = frappe.utils.escape_html;
		const res = this.id_result || {};
		const sum = res.summary || {};
		const fresh = this.ids.filter((r) => r.is_new);
		const range = fresh.length ? ` (${esc(fresh[0].student_id)} – ${esc(fresh[fresh.length - 1].student_id)})` : "";
		const STATUS = {
			new: ["ok", __("New")],
			existing: ["", __("Existing")],
			other_format: ["warn", __("Existing · different format")],
			conflict: ["bad", __("Conflict")],
		};
		const badge = (r) => {
			const [cls, label] = STATUS[r.status] || ["", r.status];
			const extra = r.status === "conflict" && r.conflict_with ? ` ${__("with {0}", [esc(r.conflict_with)])}` : "";
			return `<span class="ew-badge ${cls}">${label}${extra}</span>`;
		};
		// Kept IDs that need attention, and students already ticked, can be given a new ID.
		const tick = (r) => (["other_format", "conflict"].includes(r.status) || r.assign_new)
			? `<label class="ew-assign"><input type="checkbox" class="ew-assign-new" data-name="${esc(r.student)}" ${r.assign_new ? "checked" : ""}> ${__("Assign new ID")}</label>`
			: "";

		const banner = res.all_have_ids && !fresh.length
			? `<div class="ew-banner ok">${__("All {0} selected students already have a Student ID. Nothing will be changed. Click Next to continue.", [this.ids.length])}</div>`
			: "";
		this.d.fields_dict.id_preview_html.$wrapper.html(`
			${banner}
			<div class="ew-summary-line">
				${__("{0} students in alphabetical order", [`<b>${this.ids.length}</b>`])}:
				<b>${sum.new || 0}</b> ${__("new")}${range} ·
				<b>${sum.kept || 0}</b> ${__("kept")}${sum.other_format ? ` (<span class="ew-warn-text">${__("{0} in a different format", [sum.other_format])}</span>)` : ""} ·
				<span class="${sum.conflicts ? "ew-warn" : ""}"><b>${sum.conflicts || 0}</b> ${__("conflicts")}</span>
				<span class="ew-stale"></span>
			</div>
			<div class="ew-table-wrap">
				<table class="ew-table">
					<thead><tr>
						<th>#</th><th>${__("Student")}</th><th>${__("Current ID")}</th><th>${__("Student ID")}</th>
						<th>${__("Status")}</th><th></th>
					</tr></thead>
					<tbody>${this.ids.map((r, i) => `
						<tr class="${r.status === "conflict" ? "ew-row-bad" : r.status === "other_format" ? "ew-row-warn" : ""}">
							<td class="ew-muted">${i + 1}</td>
							<td><div class="ew-name">${esc(r.student_name || r.student)}</div><div class="ew-sub">${esc(r.student)}</div></td>
							<td>${r.current_id ? esc(r.current_id) : `<span class="ew-muted">—</span>`}</td>
							<td><span class="ew-id ${r.is_new ? "new" : ""}">${esc(r.student_id || "—")}</span></td>
							<td>${badge(r)}</td>
							<td>${tick(r)}</td>
						</tr>`).join("")}
					</tbody>
				</table>
			</div>`);
	}

	leave_ids() {
		if (!this.ids.length || this.ids_key !== this.current_ids_key()) {
			frappe.msgprint(__("Click <b>Order Alphabetically & Preview IDs</b> to work out the Student IDs for the selected students."));
			return false;
		}
		const conflicts = this.ids.filter((r) => r.status === "conflict");
		if (conflicts.length) {
			frappe.msgprint(__(
				"{0} student(s) have a Student ID that another student also holds, e.g. {1} ({2}). Tick <b>Assign new ID</b> for them or correct the other student first.",
				[conflicts.length, frappe.utils.escape_html(conflicts[0].student_name), frappe.utils.escape_html(conflicts[0].student_id)]
			));
			return false;
		}
		return true;
	}

	/* ---------------- 4. sections ---------------- */

	/** Student -> current section, for the selected students whose section still
	 * exists, when "Keep each student's current section" is on. */
	kept_sections() {
		if (!this.d.get_value("keep_sections")) return {};
		const current = Object.fromEntries(this.students.map((s) => [s.name, s.section]));
		const kept = {};
		this.ids.forEach((r) => {
			const s = current[r.student];
			if (s && this.all_sections.includes(s)) kept[r.student] = s;
		});
		return kept;
	}

	/** ID rows of the students who still need a section. */
	rows_to_assign() {
		const kept = this.kept_sections();
		return this.ids.filter((r) => !kept[r.student]);
	}

	all_kept() {
		return this.ids.length && !this.rows_to_assign().length;
	}

	on_keep_sections_change() {
		this.sections = { ...this.kept_sections() };
		this.sections_key = null;
		this.on_assignment_type_change();
	}

	on_assignment_type_change() {
		const type = this.d.get_value("assignment_type");
		const by_rows = ["Mid-off", "One-by-one"].includes(type);
		const all_kept = this.all_kept();
		if (this.step === 3) {
			// Nothing to assign: hide the assignment controls altogether.
			this.d.fields_dict.assignment_type.$wrapper.toggle(!all_kept);
			this.d.fields_dict.assignment_help.$wrapper.toggle(!all_kept);
			$(this.d.fields_dict.s4_rows.wrapper).toggle(by_rows && !all_kept);
			$(this.d.fields_dict.s4_upload.wrapper).toggle(type === "Upload" && !all_kept);
		}
		this.render_keep_banner();
		const help = {
			"Mid-off": __("Students, in alphabetical order, are cut into consecutive blocks: the first block to the first section, the next block to the second, and so on. Blocks are as even as the room capacities allow."),
			"One-by-one": __("Students, in alphabetical order, are dealt out in turn: 1st to the first section, 2nd to the second, ... and round again, skipping full rooms."),
			Manual: __("Pick the section for each student in the list below."),
			Upload: __("Download the template, fill in the Section column and upload it back."),
		}[type];
		this.d.fields_dict.assignment_help.$wrapper.html(`<div class="ew-help">${help || ""}</div>`);

		// The sections chosen belong to one method: switching starts over.
		// Kept sections always stay (and are refreshed for the current selection).
		if (this._last_type && this._last_type !== type) {
			this.sections = {};
		}
		this._last_type = type;
		const kept = this.kept_sections();
		Object.keys(this.sections).forEach((s) => this.ids.some((r) => r.student === s) || delete this.sections[s]);
		Object.assign(this.sections, kept);
		this.render_section_preview();
	}

	render_keep_banner() {
		const $w = this.d.fields_dict.keep_banner.$wrapper;
		const kept = Object.keys(this.kept_sections()).length;
		const todo = this.rows_to_assign().length;
		if (!kept) {
			$w.empty();
		} else if (!todo) {
			$w.html(`<div class="ew-banner ok">${__("All {0} selected students already have a section. Their current sections are kept; no new sections are needed. Click Next to continue.", [kept])}</div>`);
		} else {
			$w.html(`<div class="ew-banner">${__("{0} student(s) keep their current section. Assign a section to the other {1} below.", [kept, todo])}</div>`);
		}
	}

	section_rows() {
		return (this.d.get_value("section_rows") || [])
			.filter((r) => r.section)
			.map((r) => ({ section: r.section, capacity: cint(r.capacity) }));
	}

	/** Students per section, as even as the capacities allow (empty capacity = no limit). */
	section_counts(rows, total) {
		const caps = rows.map((r) => (r.capacity > 0 ? r.capacity : Infinity));
		const room = caps.reduce((a, b) => a + b, 0);
		if (room < total) {
			frappe.throw(__("Room capacity ({0}) is short of the {1} students by {2}. Add a section or raise a capacity.", [room, total, total - room]));
		}
		const counts = rows.map(() => 0);
		for (let n = 0; n < total; ) {
			for (let i = 0; i < rows.length && n < total; i++) {
				if (counts[i] < caps[i]) {
					counts[i]++;
					n++;
				}
			}
		}
		return counts;
	}

	preview_split() {
		const type = this.d.get_value("assignment_type");
		const rows = this.section_rows();
		if (!rows.length) {
			frappe.msgprint(__("Add at least one section row."));
			return;
		}
		const names = rows.map((r) => r.section);
		const dupes = names.filter((s, i) => names.indexOf(s) !== i);
		if (dupes.length) {
			frappe.msgprint(__("Section {0} is listed more than once.", [dupes[0]]));
			return;
		}
		const students = this.rows_to_assign().map((r) => r.student);
		const counts = this.section_counts(rows, students.length);

		this.sections = { ...this.kept_sections() };
		if (type === "Mid-off") {
			let start = 0;
			rows.forEach((r, i) => {
				students.slice(start, start + counts[i]).forEach((s) => (this.sections[s] = r.section));
				start += counts[i];
			});
		} else {
			const fill = rows.map(() => 0);
			let i = 0;
			students.forEach((s) => {
				while (fill[i] >= counts[i]) i = (i + 1) % rows.length;
				this.sections[s] = rows[i].section;
				fill[i]++;
				i = (i + 1) % rows.length;
			});
		}
		this.sections_key = this.split_key(type);
		this.render_section_preview();
	}

	split_key(type) {
		return JSON.stringify([type, this.section_rows(), this.ids_key, this.d.get_value("keep_sections") || 0]);
	}

	download_template() {
		frappe.call({
			method: WIZARD_API + "download_section_template",
			args: { rows: this.rows_to_assign().map((r) => ({ ...r, section: this.sections[r.student] || "" })) },
			freeze: true,
			callback: ({ message }) => message && download_base64(message.content, message.filename, message.mime),
		});
	}

	async read_upload() {
		const file_url = this.d.get_value("section_file");
		if (!file_url) return;
		const { message } = await frappe.call({
			method: WIZARD_API + "read_section_upload",
			args: { file_url },
			freeze: true,
			freeze_message: __("Reading file..."),
		});
		const m = message || {};
		this.sections = { ...this.kept_sections() };
		this.rows_to_assign().forEach((r) => {
			if (m.sections && m.sections[r.student]) this.sections[r.student] = m.sections[r.student];
		});
		this.upload_unknown = m.unknown || [];
		this.sections_key = JSON.stringify(["Upload", file_url, this.ids_key]);
		this.render_section_preview();
	}

	render_section_preview() {
		const $w = this.d.fields_dict.section_preview_html.$wrapper;
		const type = this.d.get_value("assignment_type");
		const esc = frappe.utils.escape_html;
		const counts = {};
		this.ids.forEach((r) => {
			const s = this.sections[r.student];
			if (s) counts[s] = (counts[s] || 0) + 1;
		});
		const unassigned = this.ids.filter((r) => !this.sections[r.student]).length;
		const caps = {};
		this.section_rows().forEach((r) => (caps[r.section] = r.capacity));
		const kept = this.kept_sections();
		const assigned_new = this.rows_to_assign().some((r) => this.sections[r.student]);

		if (type !== "Manual" && !assigned_new && !this.all_kept()) {
			$w.html(`<div class="ew-empty">${
				type === "Upload" ? __("Upload the filled template to see the sections.") : __("Add the sections and click Split & Preview.")
			}</div>`);
			return;
		}

		const options = (this.section_rows().length ? this.section_rows().map((r) => r.section) : this.all_sections);
		const cell = (r) => {
			const s = this.sections[r.student] || "";
			if (kept[r.student]) return `<span class="ew-pill">${esc(s)}</span> <span class="ew-muted">${__("current")}</span>`;
			if (type !== "Manual") return s ? `<span class="ew-pill">${esc(s)}</span>` : `<span class="ew-warn">${__("Not assigned")}</span>`;
			return `<select class="form-control input-xs ew-section-select" data-name="${esc(r.student)}">
				<option value=""></option>
				${options.map((o) => `<option value="${esc(o)}" ${o === s ? "selected" : ""}>${esc(o)}</option>`).join("")}
			</select>`;
		};

		const pills = Object.keys(counts).sort().map((s) =>
			`<span class="ew-pill">${esc(s)}: <b>${counts[s]}</b>${caps[s] ? ` / ${caps[s]}` : ""}</span>`
		).join(" ");
		const unknown = (this.upload_unknown || []).length && type === "Upload"
			? `<div class="ew-warn">${__("Sections not found: {0}. Create them or fix the file.", [esc(this.upload_unknown.join(", "))])}</div>` : "";

		$w.html(`
			<div class="ew-summary-line">${pills} ${unassigned ? `<span class="ew-warn">${__("{0} not assigned", [unassigned])}</span>` : ""}</div>
			${unknown}
			<div class="ew-table-wrap">
				<table class="ew-table">
					<thead><tr><th>#</th><th>${__("Student ID")}</th><th>${__("Student")}</th><th>${__("Section")}</th></tr></thead>
					<tbody>${this.ids.map((r, i) => `
						<tr>
							<td class="ew-muted">${i + 1}</td>
							<td><span class="ew-id ${r.is_new ? "new" : ""}">${esc(r.student_id)}</span></td>
							<td>${esc(r.student_name || r.student)}</td>
							<td class="ew-col-section">${cell(r)}</td>
						</tr>`).join("")}
					</tbody>
				</table>
			</div>`);
	}

	leave_sections() {
		const type = this.d.get_value("assignment_type");
		Object.assign(this.sections, this.kept_sections());
		if (this.all_kept()) {
			this.render_summary();
			return true;
		}
		if (["Mid-off", "One-by-one"].includes(type)) {
			if (this.sections_key !== this.split_key(type)) {
				frappe.msgprint(__("Click <b>Split & Preview</b> to apply the sections."));
				return false;
			}
		}
		if (type === "Upload" && (this.upload_unknown || []).length) {
			frappe.msgprint(__("The file has sections that do not exist: {0}", [this.upload_unknown.join(", ")]));
			return false;
		}
		const missing = this.ids.filter((r) => !this.sections[r.student]);
		if (missing.length) {
			frappe.msgprint(__("{0} student(s) have no section yet, e.g. {1}.", [missing.length, frappe.utils.escape_html(missing[0].student_name)]));
			return false;
		}
		this.render_summary();
		return true;
	}

	/* ---------------- 5. summary ---------------- */

	render_summary() {
		const v = this.d.get_values(true);
		const esc = frappe.utils.escape_html;
		const fresh = this.ids.filter((r) => r.is_new);
		const counts = {};
		this.ids.forEach((r) => (counts[this.sections[r.student]] = (counts[this.sections[r.student]] || 0) + 1));
		const item = (label, value) => `<div class="ew-sum-item"><div class="ew-sum-label">${label}</div><div class="ew-sum-value">${value}</div></div>`;

		this.d.fields_dict.summary_html.$wrapper.html(`
			<div class="ew-sum-grid">
				${item(__("Academic Year"), esc(v.academic_year))}
				${item(__("Academic Term"), esc(v.academic_term))}
				${item(__("Programme"), esc(v.programme))}
				${item(__("Batch"), esc(v.batch))}
				${item(__("Year"), esc(String(v.year_no)))}
				${item(__("Students"), `<b>${this.ids.length}</b>`)}
				${item(__("New Student IDs"), fresh.length
					? `${fresh.length} (${esc(fresh[0].student_id)} – ${esc(fresh[fresh.length - 1].student_id)})` : __("None"))}
				${item(__("Section Assignment"), this.section_assignment_label())}
			</div>
			<table class="ew-table ew-sum-table">
				<thead><tr><th>${__("Section")}</th><th>${__("Students")}</th></tr></thead>
				<tbody>${Object.keys(counts).sort().map((s) => `<tr><td>${esc(s)}</td><td>${counts[s]}</td></tr>`).join("")}</tbody>
			</table>
			<div class="ew-help">${__(
				"Enroll sets the Student ID, Section, Batch, Programme and Academic Year on each Student Master and creates a Student Enrollment starting in Year {0}, {1}.",
				[esc(String(v.year_no)), esc(v.academic_term)]
			)}</div>`);
	}

	section_assignment_label() {
		const kept = Object.keys(this.kept_sections()).length;
		const type = frappe.utils.escape_html(this.d.get_value("assignment_type") || "");
		if (!kept) return type;
		if (this.all_kept()) return __("Current sections kept");
		return __("{0} ({1} kept current section)", [type, kept]);
	}

	enroll() {
		const v = this.d.get_values(true);
		frappe.confirm(__("Enroll {0} student(s) in {1}?", [this.ids.length, frappe.utils.escape_html(v.programme)]), () => {
			frappe.call({
				method: WIZARD_API + "enroll_students",
				args: {
					data: {
						academic_year: v.academic_year,
						academic_term: v.academic_term,
						programme: v.programme,
						batch: v.batch,
						year_no: v.year_no,
						rows: this.ids.map((r) => ({
							student: r.student,
							student_id: r.student_id,
							section: this.sections[r.student],
						})),
					},
				},
				freeze: true,
				freeze_message: __("Enrolling students..."),
				callback: ({ message }) => this.show_result(message || {}),
			});
		});
		return false;
	}

	show_result(res) {
		const ok = (res.success || []).length;
		const failed = res.failed || [];
		const names = Object.fromEntries(this.ids.map((r) => [r.student, r.student_name]));
		const esc = frappe.utils.escape_html;
		this.d.hide();
		frappe.msgprint({
			title: __("Enrollment Result"),
			indicator: failed.length ? "orange" : "green",
			message: `${__("Enrolled: {0}", [`<b>${ok}</b>`])}${failed.length ? `<br>${__("Failed: {0}", [`<b>${failed.length}</b>`])}
				<ul>${failed.map((f) => `<li>${esc(names[f.student] || f.student)}: ${esc(f.reason)}</li>`).join("")}</ul>` : ""}`,
		});
		if (this.listview) this.listview.refresh();
	}
};

function download_base64(content, filename, mime) {
	const bytes = Uint8Array.from(atob(content), (c) => c.charCodeAt(0));
	const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
	const a = Object.assign(document.createElement("a"), { href: url, download: filename });
	document.body.appendChild(a);
	a.click();
	a.remove();
	URL.revokeObjectURL(url);
}

function inject_wizard_css() {
	if (document.getElementById("enroll-wizard-css")) return;
	const style = document.createElement("style");
	style.id = "enroll-wizard-css";
	style.innerHTML = `
		.enroll-wizard .modal-body { min-height: 420px; }
		.enroll-wizard .ew-context {
			display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px;
			padding: 10px var(--padding-lg, 20px);
			background: var(--subtle-fg, var(--control-bg));
			border-bottom: 1px solid var(--border-color);
		}
		.enroll-wizard .ew-ctx-title {
			font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
			color: var(--text-muted); margin-right: 4px;
		}
		.enroll-wizard .ew-ctx-chip {
			display: inline-flex; align-items: center; gap: 4px; max-width: 100%; min-width: 0;
			padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; line-height: 1.5;
			background: var(--card-bg, var(--bg-color)); border: 1px solid var(--border-color); color: var(--text-color);
			white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
		}
		.enroll-wizard .ew-ctx-label { font-weight: 500; color: var(--text-muted); }
		.enroll-wizard .ew-codes { border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 14px; margin-top: -4px; }
		.enroll-wizard .ew-codes-title { font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px; }
		.enroll-wizard .ew-codes ul { margin: 0; padding-left: 18px; font-size: 13px; }
		.enroll-wizard .ew-codes li { padding: 2px 0; }
		.enroll-wizard .ew-codes li.is-selected { font-weight: 600; }
		.enroll-wizard .ew-code { font-family: var(--font-family-monospace, monospace); font-weight: 700; color: var(--primary); }
		.enroll-wizard .ew-codes-tag {
			margin-left: 6px; padding: 1px 8px; border-radius: 20px; font-size: 11px; font-weight: 600;
			background: var(--green-highlight-color, #e6f4ea); color: var(--green-700, #166534);
		}
		.enroll-wizard .ew-steps {
			display: flex; align-items: center; gap: 0;
			padding: 4px 0 16px; margin-bottom: 4px;
			border-bottom: 1px solid var(--border-color);
			overflow-x: auto;
		}
		.enroll-wizard .ew-step { display: flex; align-items: center; gap: 8px; white-space: nowrap; color: var(--text-muted); }
		.enroll-wizard .ew-step-no {
			width: 26px; height: 26px; border-radius: 50%;
			display: inline-flex; align-items: center; justify-content: center;
			font-size: 12px; font-weight: 700;
			border: 1px solid var(--border-color); background: var(--control-bg);
		}
		.enroll-wizard .ew-step-label { font-size: 13px; font-weight: 600; }
		.enroll-wizard .ew-step.active { color: var(--text-color); }
		.enroll-wizard .ew-step.active .ew-step-no { background: var(--primary); border-color: var(--primary); color: #fff; }
		.enroll-wizard .ew-step.done .ew-step-no { background: var(--green-500, #22c55e); border-color: transparent; color: #fff; }
		.enroll-wizard .ew-step-line { flex: 1 1 24px; min-width: 24px; height: 1px; background: var(--border-color); margin: 0 10px; }
		.enroll-wizard .ew-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
		.enroll-wizard .ew-toolbar .ew-search { max-width: 320px; }
		.enroll-wizard .ew-count, .enroll-wizard .ew-muted, .enroll-wizard .ew-sub { color: var(--text-muted); font-size: 12px; }
		.enroll-wizard .ew-table-wrap { max-height: 46vh; overflow: auto; border: 1px solid var(--border-color); border-radius: 8px; }
		.enroll-wizard .ew-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.enroll-wizard .ew-table th {
			position: sticky; top: 0; z-index: 1; background: var(--subtle-fg, var(--control-bg));
			font-size: 11.5px; font-weight: 600; text-transform: uppercase; color: var(--text-muted);
		}
		.enroll-wizard .ew-table th, .enroll-wizard .ew-table td { padding: 7px 12px; border-bottom: 1px solid var(--border-color); text-align: left; vertical-align: middle; }
		.enroll-wizard .ew-table tbody tr:last-child td { border-bottom: none; }
		.enroll-wizard .ew-col-check { width: 36px; }
		.enroll-wizard .ew-col-section { width: 200px; }
		.enroll-wizard .ew-name { font-weight: 600; }
		.enroll-wizard .ew-id { font-family: var(--font-family-monospace, monospace); font-weight: 600; }
		.enroll-wizard .ew-id.new { color: var(--primary); }
		.enroll-wizard .ew-pill {
			display: inline-block; padding: 2px 10px; border-radius: 20px; margin: 0 6px 6px 0;
			background: var(--control-bg); border: 1px solid var(--border-color); font-size: 12px;
		}
		.enroll-wizard .ew-warn { color: var(--red-500, #dc2626); font-size: 12px; font-weight: 600; }
		.enroll-wizard .ew-stale { color: var(--orange-500, #d97706); font-size: 12px; margin-left: 8px; }
		.enroll-wizard .ew-summary-line { margin-bottom: 10px; font-size: 13px; }
		.enroll-wizard .ew-banner { padding: 10px 14px; border-radius: 8px; margin-bottom: 10px; font-size: 13px; background: var(--blue-highlight-color, #e8f1fd); color: var(--blue-700, #1e40af); }
		.enroll-wizard .ew-banner.ok { background: var(--green-highlight-color, #e6f4ea); color: var(--green-700, #166534); }
		.enroll-wizard .ew-badge {
			display: inline-block; padding: 2px 9px; border-radius: 20px; font-size: 11.5px; font-weight: 600;
			background: var(--control-bg); color: var(--text-muted); white-space: nowrap;
		}
		.enroll-wizard .ew-badge.ok { background: var(--green-highlight-color, #e6f4ea); color: var(--green-700, #166534); }
		.enroll-wizard .ew-badge.warn { background: var(--yellow-highlight-color, #fef3c7); color: var(--yellow-800, #92400e); }
		.enroll-wizard .ew-badge.bad { background: var(--red-highlight-color, #fdecea); color: var(--red-600, #b02a37); }
		.enroll-wizard .ew-row-warn td { background: var(--yellow-highlight-color, #fffbeb); }
		.enroll-wizard .ew-row-bad td { background: var(--red-highlight-color, #fef2f2); }
		.enroll-wizard .ew-warn-text { color: var(--yellow-800, #92400e); }
		.enroll-wizard .ew-assign { font-size: 12px; font-weight: 500; margin: 0; white-space: nowrap; cursor: pointer; }
		.enroll-wizard .ew-help { color: var(--text-muted); font-size: 12.5px; line-height: 1.5; padding-top: 4px; }
		.enroll-wizard .ew-empty { padding: 28px 16px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: 8px; }
		.enroll-wizard .ew-sum-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin-bottom: 14px; }
		.enroll-wizard .ew-sum-item { border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 12px; }
		.enroll-wizard .ew-sum-label { font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; }
		.enroll-wizard .ew-sum-value { font-size: 14px; margin-top: 2px; }
		.enroll-wizard .ew-sum-table { max-width: 360px; margin-bottom: 12px; border: 1px solid var(--border-color); }
	`;
	document.head.appendChild(style);
}
