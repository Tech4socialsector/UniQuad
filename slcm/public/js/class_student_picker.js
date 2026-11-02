// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

// Add / Remove Students wizard, used by the Classes form and the Create Class
// dialog.
//   1. Add Students: find Enrolled students with the filters (any academic
//      year), tick and Add; students already in the class are marked, not
//      selectable. The students added so far are listed underneath.
//   2. Review Class: everyone in the class (Existing / New / To Remove) with
//      summary, search and status filter; Remove / Undo per student.
//   3. Summary: who is added and who is removed; Apply asks to confirm.
// Server side: slcm.slcm.doctype.classes.classes.get_enrollment_students

frappe.provide("slcm.class_students");

const CSP_STEPS = [
	{ label: __("Add Students"), sections: ["s1", "s1_list"] },
	{ label: __("Review Class"), sections: ["s2"] },
	{ label: __("Summary"), sections: ["s3"] },
];

/** opts: {current: [{student_enrollment, student_name, section, program, year_no}],
 * programme, academic_year, year_no, section} (the filters' starting values).
 * Resolves to the class's rows after the changes (without those removed), or
 * null when closed without applying. */
slcm.class_students.pick = (opts) =>
	new Promise((resolve) => {
		const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		const matches = (r, q) => !q || [r.student_enrollment, r.student_name].some((x) => (x || "").toLowerCase().includes(q));
		const current = new Set((opts.current || []).map((r) => r.student_enrollment));
		const in_class = new Map((opts.current || []).map((r) => [r.student_enrollment, r]));
		const removed = new Set(); // existing students marked To Remove
		const found = new Map();
		const picked = new Set();
		let step = 0;
		let found_search = "";
		let class_search = "";
		let class_status = "";
		let applied = false;

		const d = new frappe.ui.Dialog({
			title: __("Add / Remove Students"),
			size: "extra-large",
			fields: [
				{ fieldtype: "HTML", fieldname: "steps_html" },

				// 1. Add Students
				{ fieldtype: "Section Break", fieldname: "s1" },
				{ fieldtype: "Link", fieldname: "programme", label: __("Programme"), options: "Programme" },
				{ fieldtype: "Link", fieldname: "academic_year", label: __("Academic Year"), options: "Academic Year",
					description: __("Leave empty for students of any year.") },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Select", fieldname: "year_no", label: __("Year"), options: ["", "1", "2", "3", "4", "5"] },
				{ fieldtype: "Link", fieldname: "section", label: __("Section"), options: "Section" },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Button", fieldname: "find", label: __("Find Students"), click: () => find() },
				{ fieldtype: "Section Break", fieldname: "s1_list" },
				{ fieldtype: "HTML", fieldname: "found_html" },
				{ fieldtype: "HTML", fieldname: "added_html" },

				// 2. Review Class
				{ fieldtype: "Section Break", fieldname: "s2" },
				{ fieldtype: "HTML", fieldname: "review_html" },

				// 3. Summary
				{ fieldtype: "Section Break", fieldname: "s3" },
				{ fieldtype: "HTML", fieldname: "summary_html" },
			],
			secondary_action_label: __("Back"),
			secondary_action: () => show_step(step - 1),
			on_hide: () => !applied && resolve(null),
		});
		d.set_values({
			programme: opts.programme || "",
			academic_year: opts.academic_year || "",
			year_no: opts.year_no ? String(opts.year_no) : "",
			section: opts.section || "",
		});

		const $found = d.fields_dict.found_html.$wrapper;
		const $added = d.fields_dict.added_html.$wrapper;
		const $review = d.fields_dict.review_html.$wrapper;
		const $summary = d.fields_dict.summary_html.$wrapper;
		const head = `<th>${__("Student ID")}</th><th>${__("Name")}</th><th>${__("Programme")}</th><th>${__("Year")}</th><th>${__("Section")}</th>`;
		const cells = (r) => `<td>${esc(r.student_enrollment)}</td><td>${esc(r.student_name)}</td>
			<td>${esc(r.program)}</td><td>${esc(r.year_no || "")}</td><td>${esc(r.section)}</td>`;
		const empty_row = (cols, msg) => `<tr><td colspan="${cols}" class="csp-empty">${msg}</td></tr>`;
		const chip = (label, value, cls) => `<div class="csp-chip ${cls || ""}"><span>${label}</span><b>${value}</b></div>`;
		const added_rows = () => [...in_class.values()].filter((r) => !current.has(r.student_enrollment));
		const removed_rows = () => [...in_class.values()].filter((r) => removed.has(r.student_enrollment));
		const status_of = (name) => (removed.has(name) ? "To Remove" : current.has(name) ? "Existing" : "New");
		const status_tag = (status) => `<span class="csp-tag csp-tag-${status.replace(" ", "-").toLowerCase()}">${__(status)}</span>`;

		$found.html(`
			<div class="csp-toolbar">
				<input type="text" class="form-control csp-search csp-found-search" placeholder="${__("Search name or ID")}">
				<span class="csp-count csp-found-count"></span>
				<span class="csp-actions">
					<button class="btn btn-xs btn-default csp-clear">${__("Clear List")}</button>
					<button class="btn btn-xs btn-primary csp-add-btn"></button>
				</span>
			</div>
			<div class="csp-wrap"><table class="csp-table">
				<thead><tr><th class="csp-check-col"><input type="checkbox" class="csp-all"></th>${head}<th></th></tr></thead>
				<tbody class="csp-found-body"></tbody>
			</table></div>`);

		$added.html(`
			<div class="csp-subhead csp-added-head"></div>
			<div class="csp-wrap csp-wrap-sm"><table class="csp-table">
				<thead><tr>${head}<th></th></tr></thead>
				<tbody class="csp-added-body"></tbody>
			</table></div>`);

		$review.html(`
			<div class="csp-summary"></div>
			<div class="csp-toolbar">
				<input type="text" class="form-control csp-search csp-class-search" placeholder="${__("Search name or ID")}">
				<select class="form-control csp-status">
					<option value="">${__("All Statuses")}</option>
					<option value="Existing">${__("Existing")}</option>
					<option value="New">${__("New")}</option>
					<option value="To Remove">${__("To Remove")}</option>
				</select>
				<span class="csp-count csp-class-count"></span>
			</div>
			<div class="csp-wrap"><table class="csp-table">
				<thead><tr>${head}<th>${__("Status")}</th><th></th></tr></thead>
				<tbody class="csp-class-body"></tbody>
			</table></div>`);

		/* ---------------- navigation ---------------- */

		function show_step(n) {
			step = n;
			CSP_STEPS.forEach((s, i) => s.sections.forEach((fn) => {
				const sec = d.fields_dict[fn];
				const $w = sec && (sec.wrapper || sec.$wrapper);
				if ($w) $($w).toggle(i === step);
			}));
			d.fields_dict.steps_html.$wrapper.html(`<div class="csp-steps">${CSP_STEPS.map((s, i) => `
				<div class="csp-step ${i < step ? "done" : i === step ? "active" : ""}">
					<span class="csp-step-no">${i < step ? "&#10003;" : i + 1}</span>
					<span class="csp-step-label">${s.label}</span>
				</div>`).join(`<div class="csp-step-line"></div>`)}</div>`);
			d.get_secondary_btn().toggle(step > 0);
			d.set_primary_action(step === CSP_STEPS.length - 1 ? __("Apply") : __("Next"),
				() => (step === CSP_STEPS.length - 1 ? confirm_apply() : show_step(step + 1)));
			if (step === 0) render_step1();
			if (step === 1) render_review();
			if (step === 2) render_summary();
			d.$wrapper.find(".modal-body").scrollTop(0);
		}

		function confirm_apply() {
			const n_added = added_rows().length;
			const n_removed = removed.size;
			const msg = n_added || n_removed
				? __("Add {0} student(s) to and remove {1} student(s) from the class?", [n_added, n_removed])
				: __("No students were added or removed. Close without changes?");
			frappe.confirm(msg, () => {
				applied = true;
				d.hide();
				resolve([...in_class.values()].filter((r) => !removed.has(r.student_enrollment)));
			});
		}

		/* ---------------- 1. Add Students ---------------- */

		function find() {
			const v = d.get_values(true);
			frappe.call({
				method: "slcm.slcm.doctype.classes.classes.get_enrollment_students",
				args: { programme: v.programme, academic_year: v.academic_year, year_no: v.year_no, section: v.section },
				freeze: true,
				freeze_message: __("Finding students..."),
			}).then(({ message }) => {
				found.clear();
				picked.clear();
				(message || []).forEach((s) => found.set(s.name, {
					student_enrollment: s.name, student_name: s.student_name, section: s.section,
					program: s.program, year_no: s.year_no,
				}));
				const n_new = [...found.keys()].filter((n) => !in_class.has(n)).length;
				frappe.show_alert({ message: __("{0} student(s) found, {1} not in the class.", [found.size, n_new]),
					indicator: n_new ? "green" : "orange" });
				render_step1();
			});
		}

		function visible_found() {
			const q = found_search.trim().toLowerCase();
			return [...found.values()].filter((r) => matches(r, q));
		}

		function render_step1() {
			const list = visible_found();
			const pickable = list.filter((r) => !in_class.has(r.student_enrollment));
			$found.find(".csp-found-body").html(list.length ? list.map((r) => {
				const name = r.student_enrollment;
				const note = !in_class.has(name) ? ""
					: removed.has(name) ? `<span class="csp-tag csp-tag-to-remove">${__("In class · To Remove")}</span>`
					: current.has(name) ? `<span class="csp-tag">${__("In class")}</span>`
					: `<span class="csp-tag csp-tag-new">${__("Added")}</span>`;
				return `<tr class="${note ? "csp-row-muted" : ""}">
					<td class="csp-check-col"><input type="checkbox" class="csp-check" data-name="${esc(name)}"
						${note ? "disabled" : ""} ${picked.has(name) ? "checked" : ""}></td>
					${cells(r)}<td class="csp-note-col">${note}</td>
				</tr>`;
			}).join("") : empty_row(7, found.size
				? __("No students match the search.")
				: __("No students yet. Set the filters and click Find Students.")));
			$found.find(".csp-all")
				.prop("disabled", !pickable.length)
				.prop("checked", pickable.length > 0 && pickable.every((r) => picked.has(r.student_enrollment)));
			$found.find(".csp-found-count").text(__("{0} found · {1} selected", [found.size, picked.size]));
			$found.find(".csp-add-btn").text(__("Add ({0})", [picked.size])).prop("disabled", !picked.size);
			$found.find(".csp-clear").prop("disabled", !found.size);

			const added = added_rows();
			$added.find(".csp-added-head").text(__("Added Students ({0})", [added.length]));
			$added.find(".csp-added-body").html(added.length ? added.map((r) => `<tr>${cells(r)}
				<td class="csp-action-col"><button class="btn btn-xs btn-default csp-unadd" data-name="${esc(r.student_enrollment)}">${__("Remove")}</button></td>
			</tr>`).join("") : empty_row(6, __("No students added yet. Tick students above and click Add.")));
		}

		$found.on("input", ".csp-found-search", (e) => {
			found_search = e.target.value;
			render_step1();
		});
		$found.on("change", ".csp-check", (e) => {
			const name = $(e.target).attr("data-name");
			e.target.checked ? picked.add(name) : picked.delete(name);
			render_step1();
		});
		$found.on("change", ".csp-all", (e) => {
			visible_found().filter((r) => !in_class.has(r.student_enrollment))
				.forEach((r) => (e.target.checked ? picked.add(r.student_enrollment) : picked.delete(r.student_enrollment)));
			render_step1();
		});
		$found.on("click", ".csp-add-btn", () => {
			picked.forEach((name) => in_class.set(name, found.get(name)));
			frappe.show_alert({ message: __("{0} student(s) added.", [picked.size]), indicator: "green" });
			picked.clear();
			render_step1();
		});
		$found.on("click", ".csp-clear", () => {
			found.clear();
			picked.clear();
			render_step1();
		});
		$added.on("click", ".csp-unadd", (e) => {
			in_class.delete($(e.currentTarget).attr("data-name"));
			render_step1();
		});

		/* ---------------- 2. Review Class ---------------- */

		function render_review() {
			const all = [...in_class.values()];
			const q = class_search.trim().toLowerCase();
			const list = all.filter((r) => matches(r, q) && (!class_status || status_of(r.student_enrollment) === class_status));
			$review.find(".csp-summary").html(
				chip(__("In Class after Apply"), all.length - removed.size)
				+ chip(__("Existing"), current.size)
				+ chip(__("New"), added_rows().length, "csp-chip-new")
				+ chip(__("To Remove"), removed.size, "csp-chip-remove"));
			$review.find(".csp-class-count").text(__("Showing {0} of {1}", [list.length, all.length]));
			$review.find(".csp-class-body").html(list.length ? list.map((r) => {
				const name = r.student_enrollment;
				const status = status_of(name);
				const action = status === "To Remove"
					? `<button class="btn btn-xs btn-default csp-undo" data-name="${esc(name)}">${__("Undo")}</button>`
					: `<button class="btn btn-xs btn-default csp-remove-btn" data-name="${esc(name)}">${__("Remove")}</button>`;
				return `<tr class="${status === "To Remove" ? "csp-row-removed" : ""}">${cells(r)}
					<td>${status_tag(status)}</td>
					<td class="csp-action-col">${action}</td>
				</tr>`;
			}).join("") : empty_row(7, all.length
				? __("No students match the search or status.")
				: __("No students in the class yet. Go Back and add students.")));
		}

		$review.on("input", ".csp-class-search", (e) => {
			class_search = e.target.value;
			render_review();
		});
		$review.on("change", ".csp-status", (e) => {
			class_status = e.target.value;
			render_review();
		});
		$review.on("click", ".csp-remove-btn", (e) => {
			const name = $(e.currentTarget).attr("data-name");
			// An existing student is marked To Remove; a new one is simply taken back out.
			current.has(name) ? removed.add(name) : in_class.delete(name);
			render_review();
		});
		$review.on("click", ".csp-undo", (e) => {
			removed.delete($(e.currentTarget).attr("data-name"));
			render_review();
		});

		/* ---------------- 3. Summary ---------------- */

		function render_summary() {
			const added = added_rows();
			const gone = removed_rows();
			const table = (title, rows, msg, cls) => `
				<div class="csp-subhead ${cls}">${title} (${rows.length})</div>
				<div class="csp-wrap csp-wrap-sm"><table class="csp-table">
					<thead><tr>${head}</tr></thead>
					<tbody>${rows.length ? rows.map((r) => `<tr>${cells(r)}</tr>`).join("") : empty_row(5, msg)}</tbody>
				</table></div>`;
			$summary.html(`
				<div class="csp-summary">
					${chip(__("In Class before"), current.size)}
					${chip(__("Added"), added.length, "csp-chip-new")}
					${chip(__("Removed"), gone.length, "csp-chip-remove")}
					${chip(__("In Class after Apply"), in_class.size - removed.size)}
				</div>
				${table(__("Added Students"), added, __("No students added."), "csp-subhead-new")}
				${table(__("Removed Students"), gone, __("No students removed."), "csp-subhead-remove")}`);
		}

		csp_inject_css();
		d.$wrapper.addClass("csp-dialog");
		show_step(0);
		d.show();
	});

function csp_inject_css() {
	if (document.getElementById("class-student-picker-css")) return;
	const style = document.createElement("style");
	style.id = "class-student-picker-css";
	style.textContent = `
		.csp-dialog .csp-steps {
			display: flex; align-items: center; padding: 4px 0 16px; margin-bottom: 4px;
			border-bottom: 1px solid var(--border-color); overflow-x: auto;
		}
		.csp-dialog .csp-step { display: flex; align-items: center; gap: 8px; white-space: nowrap; color: var(--text-muted); }
		.csp-dialog .csp-step-no {
			width: 26px; height: 26px; border-radius: 50%;
			display: inline-flex; align-items: center; justify-content: center;
			font-size: 12px; font-weight: 700;
			border: 1px solid var(--border-color); background: var(--control-bg);
		}
		.csp-dialog .csp-step-label { font-size: 13px; font-weight: 600; }
		.csp-dialog .csp-step.active { color: var(--text-color); }
		.csp-dialog .csp-step.active .csp-step-no { background: var(--primary); border-color: var(--primary); color: #fff; }
		.csp-dialog .csp-step.done .csp-step-no { background: var(--green-500, #22c55e); border-color: transparent; color: #fff; }
		.csp-dialog .csp-step-line { flex: 1 1 24px; min-width: 24px; height: 1px; background: var(--border-color); margin: 0 10px; }
		.csp-dialog .csp-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 8px; }
		.csp-dialog .csp-search { max-width: 260px; }
		.csp-dialog .csp-status { max-width: 170px; }
		.csp-dialog .csp-count { font-size: 12.5px; color: var(--text-muted); }
		.csp-dialog .csp-actions { margin-left: auto; display: inline-flex; gap: 8px; }
		.csp-dialog .csp-subhead { margin: 18px 0 8px; font-size: 13px; font-weight: 600; color: var(--text-color); }
		.csp-dialog .csp-subhead-new { color: var(--green-700, #166534); }
		.csp-dialog .csp-subhead-remove { color: var(--red-600, #b02a37); }
		.csp-dialog .csp-summary { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
		.csp-dialog .csp-chip {
			display: flex; flex-direction: column; min-width: 120px; padding: 8px 12px;
			border: 1px solid var(--border-color); border-radius: 8px; font-size: 12px; color: var(--text-muted);
		}
		.csp-dialog .csp-chip b { font-size: 18px; color: var(--text-color); }
		.csp-dialog .csp-chip-new b { color: var(--green-700, #166534); }
		.csp-dialog .csp-chip-remove b { color: var(--red-600, #b02a37); }
		.csp-dialog .csp-wrap { max-height: 40vh; overflow: auto; border: 1px solid var(--border-color); border-radius: 8px; }
		.csp-dialog .csp-wrap-sm { max-height: 28vh; }
		.csp-dialog .csp-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.csp-dialog .csp-table th {
			position: sticky; top: 0; z-index: 1; background: var(--subtle-fg, var(--control-bg));
			font-size: 11.5px; font-weight: 600; text-transform: uppercase; color: var(--text-muted);
		}
		.csp-dialog .csp-table th, .csp-dialog .csp-table td { padding: 6px 10px; border-bottom: 1px solid var(--border-color); text-align: left; }
		.csp-dialog .csp-check-col { width: 36px; }
		.csp-dialog .csp-action-col { width: 80px; text-align: right; }
		.csp-dialog .csp-note-col { white-space: nowrap; }
		.csp-dialog .csp-row-muted td { color: var(--text-muted); }
		.csp-dialog .csp-row-removed td { color: var(--text-muted); text-decoration: line-through; }
		.csp-dialog .csp-row-removed td:nth-last-child(-n+2) { text-decoration: none; }
		.csp-dialog .csp-tag { padding: 1px 8px; border-radius: 20px; font-size: 11px; background: var(--control-bg); color: var(--text-muted); }
		.csp-dialog .csp-tag-new { background: var(--green-100, #dcfce7); color: var(--green-700, #166534); }
		.csp-dialog .csp-tag-to-remove { background: var(--red-100, #fee2e2); color: var(--red-600, #b02a37); }
		.csp-dialog .csp-empty { padding: 24px; text-align: center; color: var(--text-muted); }
	`;
	document.head.appendChild(style);
}
