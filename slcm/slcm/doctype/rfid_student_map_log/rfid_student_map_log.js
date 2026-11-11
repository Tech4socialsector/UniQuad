// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

const RSML_API = "slcm.slcm.rfid_sql_agent.student_map.";
const RSML_MANUAL = ["Not Matched", "Conflict", "Skipped", "Failed"];
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

		const open = (frm.doc.items || []).filter((r) => RSML_MANUAL.includes(r.status));
		if (open.length) {
			frm.add_custom_button(__("Map Manually ({0})", [open.length]), () => rsml_manual_dialog(frm, open)).addClass("btn-primary");
		}
		frm.add_custom_button(__("Run Student Map Again"), () =>
			frappe.require("/assets/slcm/js/rfid_student_map.js", () => slcm.rfid_student_map.open()));
		frm.add_custom_button(__("Card Changes From This Run"), () =>
			frappe.set_route("List", "RFID UID Change Log", { source: ["like", `%${frm.doc.name}%`] }));
	},
});

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
			</div>
			<div class="rsm-kpis">
				${tile(total, __("Device records"), "brand", __("rows read from etpdb"))}
				${tile(doc.mapped, __("Mapped"), "ok", __("by this run"))}
				${tile(doc.manually_mapped, __("Mapped by hand"), "ok", __("from this log"))}
				${tile(doc.already_mapped, __("Already mapped"), "", __("no change"))}
				${tile(doc.not_matched, __("Not matched"), "warn", __("no student with the ID"))}
				${tile(doc.conflicts, __("Conflicts"), "err", __("need a decision"))}
				${tile(doc.skipped, __("Held back"), "warn", __("names differ"))}
				${tile(doc.failed, __("Failed"), "err", __("see Message"))}
			</div>
			<div class="rsm-bar" style="max-width:none;margin:0 0 6px"><div style="width:${pct}%"></div></div>
			<div class="rsm-dim" style="font-size:12px">${__("{0}% of device records are linked to a student", [pct])}</div>
		</div>`);
}

function rsml_manual_dialog(frm, open) {
	const chosen = {}; // log row name -> Student Master name
	const statuses = [...new Set(open.map((r) => r.status))];

	const d = new frappe.ui.Dialog({
		title: __("Map cards by hand"),
		size: "extra-large",
		fields: [
			{ fieldname: "help", fieldtype: "HTML", options: `<div class="text-muted small" style="margin-bottom:8px">
				${__("Pick the student for each card you want to link, then click Map. Search a student by Student ID, name or email. If the student already has a different card, it is replaced and the change is logged.")}</div>` },
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
			const mappings = Object.entries(chosen).filter(([, s]) => s).map(([row, student]) => ({ row, student }));
			if (!mappings.length) {
				frappe.show_alert({ message: __("Pick a student for at least one card."), indicator: "orange" });
				return;
			}
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
		}));
		grid_field.grid.refresh();
		const picked = Object.values(chosen).filter(Boolean).length;
		d.fields_dict.info.$wrapper.html(`<div class="text-muted small" style="margin-bottom:6px">
			${rows.length > RSML_SHOW ? __("Showing the first {0} of {1} rows — search to narrow down.", [RSML_SHOW, rows.length]) : __("{0} row(s)", [rows.length])}
			${picked ? ` · <b>${__("{0} picked", [picked])}</b>` : ""}</div>`);
	}

	d.fields_dict.q.$input.on("input", frappe.utils.debounce(refilter, 250));
	d.fields_dict.status.$input.on("change", refilter);
	d.show();
	refilter();
}
