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
				},
				{ fieldtype: "Int", fieldname: "year_no", label: __("Year"), default: 1, reqd: 1, non_negative: 1 },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Link", fieldname: "programme", label: __("Programme"), options: "Programme", reqd: 1 },
				{
					fieldtype: "Link", fieldname: "batch", label: __("Batch"), options: "Batch", reqd: 1,
					get_query: () => me.year_filter(),
					description: __("Set on every selected student."),
				},

				// 2. Students
				{ fieldtype: "Section Break", fieldname: "s2" },
				{ fieldtype: "HTML", fieldname: "students_html" },

				// 3. Student ID
				{ fieldtype: "Section Break", fieldname: "s3" },
				{
					fieldtype: "Data", fieldname: "id_format", label: __("Student ID Format"),
					description: __("Use # for the running number, e.g. M26#### gives M260001, M260002 ..."),
					onchange: () => me.mark_ids_stale(),
				},
				{
					fieldtype: "Int", fieldname: "start_from", label: __("Start From"), non_negative: 1,
					description: __("Leave empty to continue after the highest number already used with this format."),
					onchange: () => me.mark_ids_stale(),
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Check", fieldname: "renumber_existing", label: __("Re-number students who already have a Student ID"),
					onchange: () => me.mark_ids_stale(),
				},
				{ fieldtype: "Button", fieldname: "order_btn", label: __("Order Alphabetically & Preview IDs"), click: () => me.preview_ids() },
				{ fieldtype: "Section Break", fieldname: "s3_preview" },
				{ fieldtype: "HTML", fieldname: "id_preview_html" },

				// 4. Sections
				{ fieldtype: "Section Break", fieldname: "s4" },
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
	}

	on_academic_year_change() {
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
		this.d.get_secondary_btn().toggle(step > 0);
		this.d.set_primary_action(step === WIZARD_STEPS.length - 1 ? __("Enroll") : __("Next"), () => this.next());
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
		return JSON.stringify([v.id_format || "", v.start_from || 0, v.renumber_existing || 0, [...this.selected].sort()]);
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
		if (!v.id_format) {
			// No format needed when everyone already has a Student ID and keeps it.
			const chosen = this.students.filter((s) => this.selected.has(s.name));
			if (v.renumber_existing || chosen.some((s) => !s.registration_id)) {
				frappe.msgprint(__("Enter the Student ID format first, e.g. M26####."));
				return;
			}
			this.ids = chosen.map((s) => ({
				student: s.name, student_name: s.student_name, current_id: s.registration_id,
				student_id: s.registration_id, is_new: false,
			}));
			this.ids_key = this.current_ids_key();
			this.render_id_preview();
			return;
		}
		const { message } = await frappe.call({
			method: WIZARD_API + "preview_student_ids",
			args: {
				students: [...this.selected],
				id_format: v.id_format,
				start_from: v.start_from || null,
				renumber_existing: v.renumber_existing || 0,
			},
			freeze: true,
		});
		this.ids = message || [];
		this.ids_key = this.current_ids_key();
		this.render_id_preview();
	}

	render_id_preview() {
		const esc = frappe.utils.escape_html;
		const fresh = this.ids.filter((r) => r.is_new);
		const range = fresh.length ? `${esc(fresh[0].student_id)} – ${esc(fresh[fresh.length - 1].student_id)}` : __("none");
		this.d.fields_dict.id_preview_html.$wrapper.html(`
			<div class="ew-summary-line">
				${__("{0} students in alphabetical order. New IDs: {1} ({2}).", [`<b>${this.ids.length}</b>`, `<b>${fresh.length}</b>`, range])}
				<span class="ew-stale"></span>
			</div>
			<div class="ew-table-wrap">
				<table class="ew-table">
					<thead><tr><th>#</th><th>${__("Student")}</th><th>${__("Current ID")}</th><th>${__("New Student ID")}</th></tr></thead>
					<tbody>${this.ids.map((r, i) => `
						<tr>
							<td class="ew-muted">${i + 1}</td>
							<td><div class="ew-name">${esc(r.student_name || r.student)}</div><div class="ew-sub">${esc(r.student)}</div></td>
							<td>${r.current_id ? esc(r.current_id) : `<span class="ew-muted">—</span>`}</td>
							<td><span class="ew-id ${r.is_new ? "new" : ""}">${esc(r.student_id || "—")}</span></td>
						</tr>`).join("")}
					</tbody>
				</table>
			</div>`);
	}

	leave_ids() {
		if (!this.ids.length || this.ids_key !== this.current_ids_key()) {
			frappe.msgprint(__("Click <b>Order Alphabetically & Preview IDs</b> to build the Student IDs for the selected students."));
			return false;
		}
		if (this.ids.some((r) => !r.student_id)) {
			frappe.msgprint(__("Every student needs a Student ID."));
			return false;
		}
		return true;
	}

	/* ---------------- 4. sections ---------------- */

	on_assignment_type_change() {
		const type = this.d.get_value("assignment_type");
		const by_rows = ["Mid-off", "One-by-one"].includes(type);
		if (this.step === 3) {
			$(this.d.fields_dict.s4_rows.wrapper).toggle(by_rows);
			$(this.d.fields_dict.s4_upload.wrapper).toggle(type === "Upload");
		}
		const help = {
			"Mid-off": __("Students, in alphabetical order, are cut into consecutive blocks: the first block to the first section, the next block to the second, and so on. Blocks are as even as the room capacities allow."),
			"One-by-one": __("Students, in alphabetical order, are dealt out in turn: 1st to the first section, 2nd to the second, ... and round again, skipping full rooms."),
			Manual: __("Pick the section for each student in the list below."),
			Upload: __("Download the template, fill in the Section column and upload it back."),
		}[type];
		this.d.fields_dict.assignment_help.$wrapper.html(`<div class="ew-help">${help || ""}</div>`);

		// The sections chosen belong to one method: switching starts over.
		if (this._last_type && this._last_type !== type) {
			this.sections = {};
		}
		this._last_type = type;
		this.render_section_preview();
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
		const students = this.ids.map((r) => r.student);
		const counts = this.section_counts(rows, students.length);

		this.sections = {};
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
		this.sections_key = JSON.stringify([type, rows, this.ids_key]);
		this.render_section_preview();
	}

	download_template() {
		frappe.call({
			method: WIZARD_API + "download_section_template",
			args: { rows: this.ids.map((r) => ({ ...r, section: this.sections[r.student] || "" })) },
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
		this.sections = {};
		this.ids.forEach((r) => {
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

		if (type !== "Manual" && !Object.keys(counts).length) {
			$w.html(`<div class="ew-empty">${
				type === "Upload" ? __("Upload the filled template to see the sections.") : __("Add the sections and click Split & Preview.")
			}</div>`);
			return;
		}

		const options = (this.section_rows().length ? this.section_rows().map((r) => r.section) : this.all_sections);
		const cell = (r) => {
			const s = this.sections[r.student] || "";
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
		if (["Mid-off", "One-by-one"].includes(type)) {
			const key = JSON.stringify([type, this.section_rows(), this.ids_key]);
			if (this.sections_key !== key) {
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
				${item(__("Section Assignment"), esc(v.assignment_type))}
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
