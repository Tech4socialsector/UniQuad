// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

// Add / Remove Students: one list of the class's students (ticked) and the
// Enrolled students found with the filters (any academic year); tick to add,
// untick to remove. Used by the Classes form and the Create Class dialog.
// Server side: slcm.slcm.doctype.classes.classes.get_enrollment_students

frappe.provide("slcm.class_students");

/** opts: {current: [{student_enrollment, student_name, section, program, year_no}],
 * programme, academic_year, year_no, section} (the filters' starting values).
 * Resolves to the ticked rows, or null when closed without applying. */
slcm.class_students.pick = (opts) =>
	new Promise((resolve) => {
		const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		const current = new Set((opts.current || []).map((r) => r.student_enrollment));
		const rows = new Map((opts.current || []).map((r) => [r.student_enrollment, r]));
		const ticked = new Set(current);
		let search = "";
		let applied = false;

		const d = new frappe.ui.Dialog({
			title: __("Add / Remove Students"),
			size: "extra-large",
			fields: [
				{ fieldtype: "Link", fieldname: "programme", label: __("Programme"), options: "Programme" },
				{ fieldtype: "Link", fieldname: "academic_year", label: __("Academic Year"), options: "Academic Year",
					description: __("Leave empty for students of any year.") },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Int", fieldname: "year_no", label: __("Year No") },
				{ fieldtype: "Link", fieldname: "section", label: __("Section"), options: "Section" },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Button", fieldname: "find", label: __("Find Students"), click: () => find() },
				{ fieldtype: "Section Break" },
				{ fieldtype: "HTML", fieldname: "list_html" },
			],
			primary_action_label: __("Apply"),
			primary_action() {
				applied = true;
				d.hide();
				resolve([...rows.values()].filter((r) => ticked.has(r.student_enrollment)));
			},
			on_hide: () => !applied && resolve(null),
		});
		d.set_values({
			programme: opts.programme || "",
			academic_year: opts.academic_year || "",
			year_no: opts.year_no || null,
			section: opts.section || "",
		});

		function find() {
			const v = d.get_values(true);
			frappe.call({
				method: "slcm.slcm.doctype.classes.classes.get_enrollment_students",
				args: { programme: v.programme, academic_year: v.academic_year, year_no: v.year_no, section: v.section },
				freeze: true,
				freeze_message: __("Finding students..."),
			}).then(({ message }) => {
				const found = (message || []).filter((s) => !rows.has(s.name));
				found.forEach((s) => rows.set(s.name, {
					student_enrollment: s.name, student_name: s.student_name, section: s.section,
					program: s.program, year_no: s.year_no,
				}));
				frappe.show_alert({ message: __("{0} more student(s) listed; tick them to add.", [found.length]),
					indicator: found.length ? "green" : "orange" });
				render();
			});
		}

		function visible() {
			const q = search.trim().toLowerCase();
			const all = [...rows.values()];
			return q ? all.filter((r) => [r.student_enrollment, r.student_name].some((x) => (x || "").toLowerCase().includes(q))) : all;
		}

		function render() {
			const list = visible();
			const added = [...ticked].filter((n) => !current.has(n)).length;
			const removed = [...current].filter((n) => !ticked.has(n)).length;
			const all_ticked = list.length && list.every((r) => ticked.has(r.student_enrollment));
			const $w = d.fields_dict.list_html.$wrapper;
			$w.html(`
				<div class="csp-toolbar">
					<input type="text" class="form-control csp-search" placeholder="${__("Search name or ID")}" value="${esc(search)}">
					<span class="csp-count">${__("{0} selected", [ticked.size])}
						${added ? `<span class="csp-add">+${added} ${__("to add")}</span>` : ""}
						${removed ? `<span class="csp-remove">−${removed} ${__("to remove")}</span>` : ""}</span>
				</div>
				<div class="csp-wrap"><table class="csp-table">
					<thead><tr>
						<th><input type="checkbox" class="csp-all" ${all_ticked ? "checked" : ""}></th>
						<th>${__("Student ID")}</th><th>${__("Name")}</th><th>${__("Programme")}</th><th>${__("Year")}</th><th>${__("Section")}</th><th></th>
					</tr></thead>
					<tbody>${list.length ? list.map((r) => `<tr>
						<td><input type="checkbox" class="csp-check" data-name="${esc(r.student_enrollment)}" ${ticked.has(r.student_enrollment) ? "checked" : ""}></td>
						<td>${esc(r.student_enrollment)}</td>
						<td>${esc(r.student_name)}</td>
						<td>${esc(r.program)}</td>
						<td>${esc(r.year_no || "")}</td>
						<td>${esc(r.section)}</td>
						<td>${current.has(r.student_enrollment) ? `<span class="csp-tag">${__("In class")}</span>` : ""}</td>
					</tr>`).join("") : `<tr><td colspan="7" class="csp-empty">${__("No students yet. Set the filters and click Find Students.")}</td></tr>`}
					</tbody>
				</table></div>`);
			if (search) {
				const input = $w.find(".csp-search").get(0);
				input.focus();
				input.setSelectionRange(search.length, search.length);
			}
		}

		const $w = d.fields_dict.list_html.$wrapper;
		$w.on("input", ".csp-search", (e) => {
			search = e.target.value;
			render();
		});
		$w.on("change", ".csp-check", (e) => {
			const name = $(e.target).attr("data-name");
			e.target.checked ? ticked.add(name) : ticked.delete(name);
			render();
		});
		$w.on("change", ".csp-all", (e) => {
			visible().forEach((r) => (e.target.checked ? ticked.add(r.student_enrollment) : ticked.delete(r.student_enrollment)));
			render();
		});

		csp_inject_css();
		d.$wrapper.addClass("csp-dialog");
		render();
		d.show();
	});

function csp_inject_css() {
	if (document.getElementById("class-student-picker-css")) return;
	const style = document.createElement("style");
	style.id = "class-student-picker-css";
	style.textContent = `
		.csp-dialog .csp-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 8px; }
		.csp-dialog .csp-search { max-width: 280px; }
		.csp-dialog .csp-count { font-size: 12.5px; color: var(--text-muted); display: inline-flex; gap: 8px; }
		.csp-dialog .csp-add { color: var(--green-700, #166534); font-weight: 600; }
		.csp-dialog .csp-remove { color: var(--red-600, #b02a37); font-weight: 600; }
		.csp-dialog .csp-wrap { max-height: 50vh; overflow: auto; border: 1px solid var(--border-color); border-radius: 8px; }
		.csp-dialog .csp-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.csp-dialog .csp-table th {
			position: sticky; top: 0; z-index: 1; background: var(--subtle-fg, var(--control-bg));
			font-size: 11.5px; font-weight: 600; text-transform: uppercase; color: var(--text-muted);
		}
		.csp-dialog .csp-table th, .csp-dialog .csp-table td { padding: 6px 10px; border-bottom: 1px solid var(--border-color); text-align: left; }
		.csp-dialog .csp-tag { padding: 1px 8px; border-radius: 20px; font-size: 11px; background: var(--control-bg); color: var(--text-muted); }
		.csp-dialog .csp-empty { padding: 24px; text-align: center; color: var(--text-muted); }
	`;
	document.head.appendChild(style);
}
