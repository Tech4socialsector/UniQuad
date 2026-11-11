// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

// Taking RFID cards off students: the shared "why" dialog and result message used by
// RFID Card Management, the Student Map Log and the Student Master list.
// Server side: slcm.slcm.utils.rfid_cards.unmap_card.

frappe.provide("slcm.rfid_unmap");

slcm.rfid_unmap.REASONS = [
	{
		value: "Wrong student",
		label: __("Given to the wrong student"),
		help: __("Undoes the link completely. The card's past swipes go back to Unassigned and the card can be given to the right student."),
	},
	{
		value: "Lost",
		label: __("Lost"),
		help: __("Keeps the card history and past attendance. The card stops counting and cannot be given to anyone else."),
	},
	{
		value: "Damaged",
		label: __("Damaged"),
		help: __("Keeps the card history and past attendance. The card stops counting and cannot be given to anyone else."),
	},
	{
		value: "Blocked",
		label: __("Blocked (student left, card withdrawn)"),
		help: __("Keeps the card history and past attendance. The card stops counting and cannot be given to anyone else."),
	},
];

// ask({ what: "3 students", on_confirm(reason) })
slcm.rfid_unmap.ask = function ({ what, on_confirm }) {
	const by_value = Object.fromEntries(slcm.rfid_unmap.REASONS.map((r) => [r.value, r]));
	const d = new frappe.ui.Dialog({
		title: __("Remove RFID card"),
		fields: [
			{ fieldname: "intro", fieldtype: "HTML",
			  options: `<p>${__("Remove the card from {0}.", [`<b>${frappe.utils.escape_html(what)}</b>`])}</p>` },
			{ fieldname: "reason", fieldtype: "Select", label: __("Why"), reqd: 1,
			  options: [{ value: "", label: "" }].concat(slcm.rfid_unmap.REASONS.map((r) => ({ value: r.value, label: r.label }))) },
			{ fieldname: "help", fieldtype: "HTML" },
		],
		primary_action_label: __("Remove card"),
		primary_action(values) {
			if (!values.reason) return;
			d.hide();
			on_confirm(values.reason);
		},
	});
	const show_help = () => {
		const r = by_value[d.get_value("reason")];
		d.fields_dict.help.$wrapper.html(r ? `<div class="text-muted small">${r.help}</div>` : "");
	};
	d.fields_dict.reason.$input.on("change", show_help);
	d.show();
	d.get_primary_btn().addClass("btn-danger");
};

// results: [{ ok, message }] from unmap_cards / unmap_rows
slcm.rfid_unmap.show_results = function (results) {
	const esc = (s) => frappe.utils.escape_html(String(s || ""));
	const ok = (results || []).filter((r) => r.ok), bad = (results || []).filter((r) => !r.ok);
	if (!bad.length) {
		frappe.show_alert({ message: __("{0} card(s) removed", [ok.length]), indicator: "green" }, 6);
		return;
	}
	frappe.msgprint({
		title: __("Remove RFID card"),
		indicator: ok.length ? "orange" : "red",
		message: `<p><b>${__("{0} removed", [ok.length])}</b>, <b style="color:var(--red-600)">${__("{0} not removed", [bad.length])}</b></p>
			<ul>${bad.map((r) => `<li>${esc(r.message)}</li>`).join("")}</ul>`,
	});
};

// No students ticked: pick them here (only students who have a card), then ask why and remove.
// pick({ on_done() })
slcm.rfid_unmap.pick = function ({ on_done } = {}) {
	const API = "slcm.slcm.page.rfid_mapping.rfid_mapping.";
	const esc = (v) => frappe.utils.escape_html(String(v ?? ""));
	const picked = new Map(); // Student Master name -> label
	let shown = [], seq = 0, loaded_key = null;
	// Programme / Batch / Academic Year / Section: pick one or several values in each
	const FILTERS = [
		["programme", "Programme", __("Programme")],
		["batch", "SLCM Batch", __("Batch")],
		["academic_year", "Academic Year", __("Academic Year")],
		["section", "Section", __("Section")],
	];
	const filter_fields = [];
	FILTERS.forEach(([fieldname, doctype, label]) => {
		filter_fields.push({ fieldname: `cb_${fieldname}`, fieldtype: "Column Break" });
		filter_fields.push({ fieldname, fieldtype: "MultiSelectList", label, placeholder: __("Any"),
			get_data: (txt) => frappe.db.get_link_options(doctype, txt) });
	});

	const d = new frappe.ui.Dialog({
		title: __("Remove RFID card"),
		size: "extra-large",
		fields: [
			{ fieldname: "q", fieldtype: "Data", label: __("Search"), placeholder: __("Student ID, name, email or card") },
			...filter_fields,
			{ fieldname: "sb", fieldtype: "Section Break" },
			{ fieldname: "list", fieldtype: "HTML" },
		],
		primary_action_label: __("Remove card"),
		primary_action() {
			const students = [...picked.keys()];
			if (!students.length) {
				frappe.show_alert({ message: __("Tick at least one student."), indicator: "orange" });
				return;
			}
			slcm.rfid_unmap.ask({
				what: students.length === 1 ? [...picked.values()][0] : __("{0} students", [students.length]),
				on_confirm(reason) {
					frappe.call({
						method: API + "unmap_cards",
						args: { students, reason },
						freeze: true, freeze_message: __("Removing cards…"),
						callback(r) {
							slcm.rfid_unmap.show_results(r.message);
							d.hide();
							on_done && on_done();
						},
					});
				},
			});
		},
	});
	const $list = d.fields_dict.list.$wrapper;

	function current_filters() {
		const filters = {};
		FILTERS.forEach(([k]) => {
			const v = (d.fields_dict[k].get_value() || []).filter(Boolean);
			if (v.length) filters[k] = [...v];
		});
		return filters;
	}

	// reload only when the search text or a filter really changed
	function load_if_changed() {
		const key = JSON.stringify([d.get_value("q") || "", current_filters()]);
		if (key !== loaded_key) load();
	}

	function load() {
		const filters = current_filters();
		loaded_key = JSON.stringify([d.get_value("q") || "", filters]);
		const mine = ++seq; // ignore answers to older searches
		frappe.call({
			method: API + "students_with_cards",
			args: { txt: d.get_value("q") || "", filters },
			callback(r) {
				if (mine !== seq) return;
				const { rows = [], total = 0, limit = 0 } = r.message || {};
				shown = rows;
				render(total, limit);
			},
		});
	}

	function render(total, limit) {
		$list.html(`
			<div class="text-muted small" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
				<label style="margin:0;display:flex;gap:6px;align-items:center">
					<input type="checkbox" class="rfu-all" ${shown.length ? "" : "disabled"}> ${__("Tick all {0} shown", [shown.length])}</label>
				<span>${total > shown.length ? __("Showing {0} of {1} students with a card — search or filter to narrow down.", [limit, total])
					: __("{0} student(s) with a card", [total])}</span>
				<b class="rfu-count"></b>
			</div>
			<div style="max-height:52vh;overflow:auto;border:1px solid var(--border-color);border-radius:8px">
			<table class="table table-sm" style="margin:0">
				<thead><tr><th style="width:36px"></th><th>${__("Student ID")}</th><th>${__("Student")}</th><th>${__("RFID UID")}</th>
					<th>${__("Programme")}</th><th>${__("Batch")}</th><th>${__("Section")}</th></tr></thead>
				<tbody>${shown.length ? shown.map((s) => `<tr>
					<td><input type="checkbox" class="rfu-row" data-student="${esc(s.name)}" ${picked.has(s.name) ? "checked" : ""}
						aria-label="${esc(__("Tick {0}", [s.student_name || s.student_id || s.name]))}"></td>
					<td>${esc(s.student_id)}</td><td>${esc(s.student_name)}</td><td>${esc(s.rfid_uid)}</td>
					<td class="text-muted">${esc(s.programme)}</td><td class="text-muted">${esc(s.batch)}</td><td class="text-muted">${esc(s.section)}</td>
				</tr>`).join("") : `<tr><td colspan="7" class="text-muted">${__("No student with a card matches.")}</td></tr>`}</tbody>
			</table></div>`);
		update_head();
	}

	// count and "tick all" only, so ticking keeps the list where it is
	function update_head() {
		$list.find(".rfu-all").prop("checked", shown.length > 0 && shown.every((s) => picked.has(s.name)));
		$list.find(".rfu-count").text(picked.size ? __("{0} ticked", [picked.size]) : "");
		d.get_primary_btn().text(picked.size ? __("Remove card from {0}", [picked.size]) : __("Remove card"));
	}

	const label = (s) => `${s.student_name || s.name}${s.student_id ? ` (${s.student_id})` : ""}`;
	$list.on("change", ".rfu-row", function () {
		const s = shown.find((x) => x.name === $(this).attr("data-student"));
		if (!s) return;
		this.checked ? picked.set(s.name, label(s)) : picked.delete(s.name);
		update_head();
	});
	$list.on("change", ".rfu-all", function () {
		shown.forEach((s) => (this.checked ? picked.set(s.name, label(s)) : picked.delete(s.name)));
		$list.find(".rfu-row").prop("checked", this.checked);
		update_head();
	});
	d.fields_dict.q.$input.on("input", frappe.utils.debounce(load_if_changed, 300));
	// the multi-select keeps its values in one array, so watch its clicks and its closing instead of onchange
	FILTERS.forEach(([k]) => {
		const $w = d.fields_dict[k].$wrapper;
		$w.on("click", ".selectable-item, .select-all-options, .clear-selections", () => setTimeout(load_if_changed, 60));
		$w.on("hidden.bs.dropdown", () => setTimeout(load_if_changed, 60));
	});
	d.show();
	d.get_primary_btn().addClass("btn-danger");
	load();
};
