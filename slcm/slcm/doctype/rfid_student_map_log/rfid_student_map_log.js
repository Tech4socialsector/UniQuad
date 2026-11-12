// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

const RSML_API = "slcm.slcm.rfid_sql_agent.student_map.";
const RSML_MANUAL = ["Not Matched", "Conflict", "Skipped", "Failed", "Unmapped"];
const RSML_UNMAP = ["Mapped", "Manually Mapped", "Already Mapped"];
const RSML_SHOW = 100;

frappe.ui.form.on("RFID Student Map Log", {
	refresh(frm) {
		frm.disable_save();
		frappe.require("/assets/slcm/js/rfid_student_map.js", () => rsml_summary(frm));

		if (frm.doc.status === "In Progress") {
			frm.dashboard.set_headline(__("This run is still linking cards — the page refreshes by itself."), "orange");
			clearTimeout(frm._rsml_timer);
			frm._rsml_timer = setTimeout(() => {
				if (frm.doc.status === "In Progress" && cur_frm === frm) frm.reload_doc();
			}, 5000);
			return;
		}

		// Map Manually / Unmap Cards live under one "Update" menu; all buttons dark, same colour on hover / click
		const UPDATE = __("Update");
		const open = (frm.doc.items || []).filter((r) => RSML_MANUAL.includes(r.status));
		if (open.length) {
			frm.add_custom_button(__("Map Manually ({0})", [open.length]), () => rsml_manual_dialog(frm, open), UPDATE);
		}
		const linked = (frm.doc.items || []).filter((r) => RSML_UNMAP.includes(r.status) && r.student);
		if (linked.length) {
			frm.add_custom_button(__("Unmap Cards ({0})", [linked.length]), () =>
				frappe.require("/assets/slcm/js/rfid_unmap.js", () => rsml_unmap_dialog(frm, linked)), UPDATE);
		}
		frm.add_custom_button(__("Run Student Map Again"), () =>
			frappe.require("/assets/slcm/js/rfid_student_map.js", () => slcm.rfid_student_map.open()));
		frm.add_custom_button(__("Card Changes From This Run"), () => rsml_changes_dialog(frm));
		rsml_dark_buttons(frm, UPDATE);

		// the grid pages 50 rows at a time, so "58 of 58" is the page number, not the row count
		const total = (frm.doc.items || []).length;
		frm.set_df_property("items", "description", total > 50
			? __("{0} rows, 50 per page. Use the page arrows or the column filters to find a card.", [total.toLocaleString("en-IN")])
			: "");
	},
});

function rsml_dark_buttons(frm, group) {
	if (!document.getElementById("rsml-btn-css")) {
		$("head").append(`<style id="rsml-btn-css">
			.btn.btn-primary.rsml-btn, .btn.btn-primary.rsml-btn:hover, .btn.btn-primary.rsml-btn:focus,
			.btn.btn-primary.rsml-btn:focus-visible, .btn.btn-primary.rsml-btn:active, .show > .btn.btn-primary.rsml-btn {
				background-color: var(--btn-primary) !important; color: var(--neutral) !important;
				border-color: var(--btn-primary) !important; box-shadow: none !important; }
		</style>`);
	}
	frm.page.inner_toolbar.find("> .btn, .inner-group-button > button").removeClass("btn-default").addClass("btn-primary rsml-btn");
	frm.page.get_inner_group_button(group).find("button").removeClass("btn-default").addClass("btn-primary rsml-btn");
}

function rsml_summary(frm) {
	slcm.rfid_student_map.inject_css();
	const doc = frm.doc;
	const tile = (n, label, cls, hint) =>
		`<div class="rsm-kpi static ${cls}"><b>${(parseInt(n, 10) || 0).toLocaleString("en-IN")}</b><span>${label}</span>${hint ? `<small>${hint}</small>` : ""}</div>`;
	const linked = (doc.mapped || 0) + (doc.manually_mapped || 0) + (doc.already_mapped || 0);
	const total = doc.total_records || 0;
	const pct = total ? Math.round((linked / total) * 100) : 0;
	frm.get_field("summary_html").$wrapper.html(`
		<div class="rsm-scope">
			<div class="rsm-meta">
				<span>${__("Run by")} <b>${frappe.utils.escape_html(frappe.user.full_name(doc.run_by) || doc.run_by || "")}</b></span>
				<span>${__("on")} <b>${doc.run_on ? frappe.datetime.str_to_user(doc.run_on) : "—"}</b></span>
				<span class="rsm-tag ${{ Completed: "ok", "Completed with Issues": "warn", Failed: "err" }[doc.status] || "info"}">${frappe.utils.escape_html(__(doc.status || ""))}</span>
				${doc.scope ? `<span class="rsm-tag info"><i class="fa fa-filter"></i> ${frappe.utils.escape_html(doc.scope)}</span>` : ""}
			</div>
			<div class="rsm-kpis">
				${tile(total, __("Device records"), "brand", __("rows read from etpdb"))}
				${tile(doc.mapped, __("Mapped"), "ok", __("by this run"))}
				${tile(doc.manually_mapped, __("Mapped by hand"), "ok", __("from this log"))}
				${tile(doc.already_mapped, __("Already mapped"), "", __("no change"))}
				${tile(doc.not_matched, __("Not matched"), "warn", __("no student with the ID"))}
				${tile(doc.conflicts, __("Conflicts"), "err", __("need a decision"))}
				${tile(doc.skipped, __("Held back"), "warn", __("names differ or removed by hand"))}
				${tile(doc.failed, __("Failed"), "err", __("see Message"))}
				${doc.unmapped ? tile(doc.unmapped, __("Unmapped"), "warn", __("card taken back")) : ""}
			</div>
			<div class="rsm-bar" style="max-width:none;margin:0 0 6px"><div style="width:${pct}%"></div></div>
			<div class="rsm-dim" style="font-size:12px">${__("{0}% of device records are linked to a student", [pct])}</div>
		</div>`);
}

// A row is mapped when it is ticked, or when a student was picked for it by hand. Rows held back for a name
// difference or a conflict come with their matched student filled in; ticking them maps to that student.
// Unmapped rows never get their old student filled in (it may have been the wrong one).
const RSML_PREFILL = ["Skipped", "Conflict"];

function rsml_manual_dialog(frm, open) {
	const prefill = {}; // log row name -> student matched by the run
	open.forEach((r) => { if (RSML_PREFILL.includes(r.status) && r.student) prefill[r.name] = r.student; });
	const chosen = { ...prefill }; // log row name -> Student Master name
	const ticked = new Set(); // log row names
	const by_name = Object.fromEntries(open.map((r) => [r.name, r]));
	const statuses = [...new Set(open.map((r) => r.status))];

	const d = new frappe.ui.Dialog({
		title: __("Map cards by hand"),
		size: "extra-large",
		fields: [
			{ fieldname: "help", fieldtype: "HTML", options: `<div class="text-muted small" style="margin-bottom:8px">
				${__("Tick the cards to link and choose the student in <b>Map to student</b> (click the cell, then search by Student ID, name or email). Picking a student also selects that card. Cards held back for a name difference already show the matched student. If the student has a different card, it is replaced and the change is logged.")}</div>` },
			{ fieldname: "q", fieldtype: "Data", label: __("Search rows"), placeholder: __("Card code, name in etpdb, message…") },
			{ fieldname: "cb", fieldtype: "Column Break" },
			{ fieldname: "status", fieldtype: "Select", label: __("Status"), options: [""].concat(statuses) },
			{ fieldname: "sb", fieldtype: "Section Break" },
			{ fieldname: "info", fieldtype: "HTML" },
			{
				fieldname: "rows", fieldtype: "Table", cannot_add_rows: 1, cannot_delete_rows: 1, in_place_edit: 1, data: [],
				fields: [
					{ fieldname: "row", fieldtype: "Data", hidden: 1 },
					{ fieldname: "rfid_uid", fieldtype: "Data", label: __("Card code"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "device_name", fieldtype: "Data", label: __("Name in etpdb"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "status", fieldtype: "Data", label: __("Status"), in_list_view: 1, read_only: 1, columns: 1 },
					{ fieldname: "message", fieldtype: "Data", label: __("Note"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "student", fieldtype: "Link", options: "Student Master", label: __("Map to student"), in_list_view: 1, columns: 3,
					  get_query: () => ({ query: RSML_API + "student_link_query" }) },
				],
			},
		],
		primary_action_label: __("Map"),
		primary_action() {
			harvest();
			const picked_by_hand = Object.keys(chosen).filter((row) => chosen[row] && chosen[row] !== prefill[row]);
			const selected = [...new Set([...ticked, ...picked_by_hand])];
			if (!selected.length) {
				frappe.msgprint({ title: __("Nothing to map"), indicator: "orange",
					message: __("Tick a card and choose its student in <b>Map to student</b>, then click Map.") });
				return;
			}
			const missing = selected.filter((row) => !chosen[row]);
			if (missing.length) {
				const codes = missing.slice(0, 5).map((row) => `<b>${frappe.utils.escape_html(by_name[row]?.rfid_uid || row)}</b>`).join(", ");
				frappe.msgprint({ title: __("Student missing"), indicator: "orange",
					message: __("{0} ticked card(s) have no student: {1}{2}. Click the <b>Map to student</b> cell of each and pick the student, or untick them.",
						[missing.length, codes, missing.length > 5 ? " …" : ""]) });
				return;
			}
			const mappings = selected.map((row) => ({ row, student: chosen[row] }));
			frappe.confirm(__("Link {0} card(s) to the chosen students?", [mappings.length]), () =>
				frappe.call({
					method: RSML_API + "manual_map",
					args: { log_name: frm.doc.name, mappings },
					freeze: true, freeze_message: __("Linking cards…"),
					callback(r) {
						const res = r.message || [];
						const ok = res.filter((x) => x.ok), bad = res.filter((x) => !x.ok);
						const esc = (s) => frappe.utils.escape_html(String(s || ""));
						let html = `<p><b>${__("{0} linked", [ok.length])}</b>${bad.length ? `, <b style="color:var(--red-600)">${__("{0} not linked", [bad.length])}</b>` : ""}</p>`;
						if (bad.length) html += `<ul>${bad.map((x) => `<li>${esc(x.message)}</li>`).join("")}</ul>`;
						frappe.msgprint({ title: __("Manual mapping"), message: html, indicator: bad.length ? "orange" : "green" });
						d.hide();
						frm.reload_doc();
					},
				})
			);
		},
	});

	const grid_field = d.fields_dict.rows;

	function harvest() {
		(grid_field.df.data || []).forEach((r) => {
			if (r.student) chosen[r.row] = r.student;
			else delete chosen[r.row];
			if (r.__checked) ticked.add(r.row);
			else ticked.delete(r.row);
		});
	}

	function refilter() {
		harvest();
		const q = (d.get_value("q") || "").trim().toLowerCase();
		const st = d.get_value("status");
		const rows = open.filter((r) => (!st || r.status === st) && (!q ||
			["rfid_uid", "device_name", "message", "student_id", "student_name"].some((f) => r[f] && String(r[f]).toLowerCase().includes(q))));
		grid_field.df.data = rows.slice(0, RSML_SHOW).map((r) => ({
			row: r.name, rfid_uid: r.rfid_uid, device_name: r.device_name, status: r.status, message: r.message, student: chosen[r.name] || "",
			__checked: ticked.has(r.name) ? 1 : 0,
		}));
		grid_field.grid.refresh();
		const picked = new Set([...ticked, ...Object.keys(chosen).filter((row) => chosen[row] && chosen[row] !== prefill[row])]).size;
		d.fields_dict.info.$wrapper.html(`<div class="text-muted small" style="margin-bottom:6px">
			${rows.length > RSML_SHOW ? __("Showing the first {0} of {1} rows — search to narrow down.", [RSML_SHOW, rows.length]) : __("{0} row(s)", [rows.length])}
			${picked ? ` · <b>${__("{0} selected", [picked])}</b>` : ""}</div>`);
	}

	d.fields_dict.q.$input.on("input", frappe.utils.debounce(refilter, 250));
	d.fields_dict.status.$input.on("change", refilter);
	d.show();
	refilter();
}

// Take cards back off students linked in this log: tick rows (search narrows, "all matching" ticks every
// row the search finds, not only the ones on screen), then choose why.
function rsml_unmap_dialog(frm, linked) {
	const picked = new Set();
	const esc = (v) => frappe.utils.escape_html(String(v ?? ""));
	let shown = [];

	const d = new frappe.ui.Dialog({
		title: __("Unmap cards"),
		size: "extra-large",
		fields: [
			{ fieldname: "help", fieldtype: "HTML", options: `<div class="text-muted small" style="margin-bottom:8px">
				${__("Tick the cards to take off their students, then click Unmap. A row is skipped when the student has since got a different card.")}</div>` },
			{ fieldname: "q", fieldtype: "Data", label: __("Search rows"), placeholder: __("Card code, Student ID, name…") },
			{ fieldname: "cb", fieldtype: "Column Break" },
			{ fieldname: "status", fieldtype: "Select", label: __("Status"), options: [""].concat([...new Set(linked.map((r) => r.status))]) },
			{ fieldname: "sb", fieldtype: "Section Break" },
			{ fieldname: "list", fieldtype: "HTML" },
		],
		primary_action_label: __("Unmap"),
		primary_action() {
			const rows = [...picked];
			if (!rows.length) {
				frappe.show_alert({ message: __("Tick at least one card."), indicator: "orange" });
				return;
			}
			slcm.rfid_unmap.ask({
				what: rows.length === 1 ? __("1 student") : __("{0} students", [rows.length]),
				on_confirm(reason) {
					frappe.call({
						method: RSML_API + "unmap_rows",
						args: { log_name: frm.doc.name, rows, reason },
						freeze: true, freeze_message: __("Removing cards…"),
						callback(r) {
							slcm.rfid_unmap.show_results(r.message);
							d.hide();
							frm.reload_doc();
						},
					});
				},
			});
		},
	});

	function render() {
		const q = (d.get_value("q") || "").trim().toLowerCase();
		const st = d.get_value("status");
		shown = linked.filter((r) => (!st || r.status === st) && (!q ||
			["rfid_uid", "device_name", "student_id", "student_name"].some((f) => r[f] && String(r[f]).toLowerCase().includes(q))));
		const page = shown.slice(0, RSML_SHOW);
		d.fields_dict.list.$wrapper.html(`
			<div class="text-muted small" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
				<label style="margin:0;display:flex;gap:6px;align-items:center">
					<input type="checkbox" class="rsml-all" ${shown.length ? "" : "disabled"}>
					${__("Tick all {0} matching", [shown.length])}</label>
				<span>${shown.length > RSML_SHOW ? __("Showing the first {0} — search to narrow down.", [RSML_SHOW]) : ""}</span>
				<b class="rsml-count"></b>
			</div>
			<div style="max-height:55vh;overflow:auto;border:1px solid var(--border-color);border-radius:8px">
			<table class="table table-sm" style="margin:0">
				<thead><tr><th style="width:36px"></th><th>${__("Card code")}</th><th>${__("Student ID")}</th><th>${__("Student")}</th><th>${__("Status")}</th></tr></thead>
				<tbody>${page.length ? page.map((r) => `<tr>
					<td><input type="checkbox" class="rsml-row" data-row="${esc(r.name)}" ${picked.has(r.name) ? "checked" : ""}
						aria-label="${esc(__("Tick card {0}", [r.rfid_uid]))}"></td>
					<td>${esc(r.rfid_uid)}</td><td>${esc(r.student_id)}</td><td>${esc(r.student_name)}</td><td>${esc(__(r.status))}</td>
				</tr>`).join("") : `<tr><td colspan="5" class="text-muted">${__("Nothing matches your search.")}</td></tr>`}</tbody>
			</table></div>`);
		update_head();
	}

	// counter and "tick all" box only, so ticking a row keeps the list where it is
	function update_head() {
		const $w = d.fields_dict.list.$wrapper;
		$w.find(".rsml-all").prop("checked", shown.length > 0 && shown.every((r) => picked.has(r.name)));
		$w.find(".rsml-count").text(picked.size ? __("{0} ticked", [picked.size]) : "");
	}

	d.fields_dict.list.$wrapper.on("change", ".rsml-row", function () {
		const row = $(this).attr("data-row");
		this.checked ? picked.add(row) : picked.delete(row);
		update_head();
	});
	d.fields_dict.list.$wrapper.on("change", ".rsml-all", function () {
		shown.forEach((r) => (this.checked ? picked.add(r.name) : picked.delete(r.name)));
		render();
	});
	d.fields_dict.q.$input.on("input", frappe.utils.debounce(render, 250));
	d.fields_dict.status.$input.on("change", render);
	d.show();
	d.get_primary_btn().addClass("btn-danger");
	render();
}

// Card changes this log made, every card change of one chosen student, or (This run only off) every card
// change; narrowed by the student's Programme / Batch / Academic Year / Section, the change and the dates.
// 50 per page on screen; Export downloads every matching row as CSV. Rows live in each student's RFID UID Change Log.
const RSML_CHANGES_PAGE = 50;

function rsml_changes_dialog(frm) {
	const esc = (v) => frappe.utils.escape_html(String(v ?? ""));
	const tone = { Assigned: "green", Changed: "blue", Removed: "red" };
	let start = 0, total = 0, seq = 0;
	const reload = () => { start = 0; load(); };

	const d = new frappe.ui.Dialog({
		title: __("Card changes from {0}", [frm.doc.name]),
		size: "extra-large",
		fields: [
			{ fieldname: "student", fieldtype: "Link", options: "Student Master", label: __("Student"),
			  description: __("Choose a student to see all their card changes, from any screen"),
			  get_query: () => ({ query: RSML_API + "student_link_query" }), onchange: reload },
			{ fieldname: "cb1", fieldtype: "Column Break" },
			{ fieldname: "q", fieldtype: "Data", label: __("Search"), placeholder: __("Student ID, name or card code") },
			{ fieldname: "cb2", fieldtype: "Column Break" },
			{ fieldname: "this_run", fieldtype: "Check", label: __("This run only"), default: 1, onchange: reload,
			  description: __("Untick to see card changes from every screen") },
			{ fieldname: "sb1", fieldtype: "Section Break", label: __("Filters"), collapsible: 1 },
			{ fieldname: "programme", fieldtype: "Link", options: "Programme", label: __("Programme"), onchange: reload },
			{ fieldname: "change_type", fieldtype: "Select", label: __("Change"), options: ["", "Assigned", "Changed", "Removed"], onchange: reload },
			{ fieldname: "cb3", fieldtype: "Column Break" },
			{ fieldname: "batch", fieldtype: "Link", options: "SLCM Batch", label: __("Batch"), onchange: reload },
			{ fieldname: "from_date", fieldtype: "Date", label: __("From Date"), onchange: reload },
			{ fieldname: "cb4", fieldtype: "Column Break" },
			{ fieldname: "academic_year", fieldtype: "Link", options: "Academic Year", label: __("Academic Year"), onchange: reload },
			{ fieldname: "to_date", fieldtype: "Date", label: __("To Date"), onchange: reload },
			{ fieldname: "cb5", fieldtype: "Column Break" },
			{ fieldname: "section", fieldtype: "Link", options: "Section", label: __("Section"), onchange: reload },
			{ fieldname: "sb2", fieldtype: "Section Break" },
			{ fieldname: "list", fieldtype: "HTML" },
		],
		primary_action_label: __("Export"),
		primary_action: () => rsml_export_changes(frm, d, filters()),
	});

	function filters() {
		const f = { this_run: d.get_value("this_run") ? 1 : 0 };
		["programme", "batch", "academic_year", "section", "change_type", "from_date", "to_date"].forEach((k) => {
			const v = d.get_value(k);
			if (v) f[k] = v;
		});
		return f;
	}
	const $list = d.fields_dict.list.$wrapper;

	function load() {
		const student = d.get_value("student");
		const mine = ++seq; // ignore answers to older requests
		frappe.call({
			method: RSML_API + "run_card_changes",
			args: { log_name: frm.doc.name, student, txt: d.get_value("q") || "", start, page_len: RSML_CHANGES_PAGE, filters: filters() },
			callback(r) {
				if (mine !== seq) return;
				const { rows = [], total: n = 0 } = r.message || {};
				total = n;
				d.set_title(student ? __("All card changes of {0}", [rows[0]?.student_name || student])
					: d.get_value("this_run") ? __("Card changes from {0}", [frm.doc.name]) : __("All card changes"));
				d.get_primary_btn().prop("disabled", !total).text(total ? __("Export {0}", [total.toLocaleString("en-IN")]) : __("Export"));
				render(rows, student);
			},
		});
	}

	function render(rows, student) {
		const end = Math.min(start + rows.length, total);
		$list.html(`
			<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">
				<span class="text-muted small">${total
					? __("{0}–{1} of {2} change(s), newest first. {3}", [start + 1, end, total,
						student ? __("Clear Student to go back to this run.") : __("Click a student to see all their changes.")])
					: (student ? __("No card changes for this student match these filters.") : __("Nothing matches these filters."))}</span>
				<span>
					<button class="btn btn-default btn-xs rsml-prev" ${start > 0 ? "" : "disabled"}>${__("Previous")}</button>
					<button class="btn btn-default btn-xs rsml-next" ${end < total ? "" : "disabled"}>${__("Next")}</button>
				</span>
			</div>
			${rows.length ? `<div style="max-height:58vh;overflow:auto;border:1px solid var(--border-color);border-radius:8px">
			<table class="table table-sm" style="margin:0">
				<thead><tr><th>${__("Student ID")}</th><th>${__("Student")}</th><th>${__("Change")}</th><th>${__("From")}</th><th>${__("To")}</th>
					<th>${__("Changed On")}</th><th>${__("By")}</th><th>${__("Changed From")}</th></tr></thead>
				<tbody>${rows.map((x) => `<tr>
					<td>${esc(x.student_id)}</td>
					<td><a href="#" class="rsml-student" data-student="${esc(x.log)}">${esc(x.student_name || x.log)}</a></td>
					<td><span class="indicator-pill ${tone[x.change_type] || "gray"}">${esc(__(x.change_type))}</span></td>
					<td>${esc(x.old_rfid_uid)}</td><td>${esc(x.new_rfid_uid)}</td>
					<td style="white-space:nowrap">${esc(x.changed_on ? frappe.datetime.str_to_user(x.changed_on) : "")}</td>
					<td>${esc(frappe.user.full_name(x.changed_by) || x.changed_by)}</td>
					<td class="text-muted small">${esc(x.source)}</td>
				</tr>`).join("")}</tbody>
			</table></div>` : ""}
			${student ? `<div style="margin-top:8px"><a href="/app/rfid-uid-change-log/${encodeURIComponent(student)}">${__("Open this student's RFID UID Change Log")} →</a></div>` : ""}`);
	}

	$list.on("click", ".rsml-prev", () => { start = Math.max(0, start - RSML_CHANGES_PAGE); load(); });
	$list.on("click", ".rsml-next", () => { start += RSML_CHANGES_PAGE; load(); });
	$list.on("click", ".rsml-student", function (e) {
		e.preventDefault();
		d.set_value("student", $(this).attr("data-student")); // triggers reload through the field's change
	});
	d.fields_dict.q.$input.on("input", frappe.utils.debounce(() => { start = 0; load(); }, 300));
	d.show();
	load();
}

// CSV of every card change matching the dialog (not only the page on screen)
function rsml_export_changes(frm, d, filters) {
	const student = d.get_value("student");
	frappe.call({
		method: RSML_API + "export_card_changes",
		args: { log_name: frm.doc.name, student, txt: d.get_value("q") || "", filters },
		freeze: true, freeze_message: __("Preparing export…"),
		callback(r) {
			const { rows = [], total = 0, limit = 0 } = r.message || {};
			if (!rows.length) {
				frappe.show_alert({ message: __("Nothing to export for these filters."), indicator: "orange" });
				return;
			}
			const cols = [
				["changed_on", __("Changed On")], ["student_id", __("Student ID")], ["student_name", __("Student Name")],
				["change_type", __("Change")], ["old_rfid_uid", __("From RFID UID")], ["new_rfid_uid", __("To RFID UID")],
				["changed_by_name", __("Changed By")], ["source", __("Changed From")], ["message", __("Message")],
				["programme", __("Programme")], ["batch", __("Batch")], ["academic_year", __("Academic Year")], ["section", __("Section")],
			];
			const cell = (v) => {
				let t = v == null ? "" : String(v);
				if (/^[=+\-@\t\r]/.test(t)) t = "'" + t; // stop spreadsheet formula injection
				return `"${t.replace(/"/g, '""')}"`;
			};
			const csv = [cols.map(([, label]) => cell(label)).join(",")]
				.concat(rows.map((row) => cols.map(([key]) => cell(row[key])).join(","))).join("\r\n");
			const who = student || (filters.this_run ? frm.doc.name : "all");
			const url = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }));
			const a = Object.assign(document.createElement("a"), { href: url, download: `rfid_card_changes_${who}_${frappe.datetime.get_today()}.csv` });
			document.body.appendChild(a);
			a.click();
			a.remove();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
			if (total > rows.length) {
				frappe.msgprint({ title: __("Export limited"), indicator: "orange",
					message: __("Exported the newest {0} of {1} changes. Narrow the filters to export the rest.", [limit.toLocaleString("en-IN"), total.toLocaleString("en-IN")]) });
			} else {
				frappe.show_alert({ message: __("Exported {0} change(s)", [rows.length]), indicator: "green" }, 5);
			}
		},
	});
}
