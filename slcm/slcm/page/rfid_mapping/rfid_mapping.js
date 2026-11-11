// Copyright (c) 2026, Nishanth and contributors
// RFID Card Management — NLSIU theme (#920C24 + Merriweather), British spelling.
// People only ever see/type the Student ID (registration_id, e.g. L26001);
// the system name (STUD-2026-xxxxx) is used internally for links only.

const RF_API = "slcm.slcm.page.rfid_mapping.rfid_mapping.";
const RF_REFRESH_SECS = 30;
const RF_FEED_MAX = 200;

frappe.pages["rfid-mapping"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: "RFID Card Management", single_column: true });

	if (!document.getElementById("er-theme-font")) {
		$("head").append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	if (!document.getElementById("rfid-mapping-css")) {
		$("head").append(`<style id="rfid-mapping-css">${rf_css()}</style>`);
	}

	wrapper._rfid = { live_interval: null, countdown_interval: null, countdown: RF_REFRESH_SECS, last_swipe_time: null, busy: false };

	const $body = $(wrapper).find(".page-content, .layout-main-section").first();
	$(rf_html()).appendTo($body);

	rf_init_tables(wrapper);
	rf_bind(wrapper);
	rf_full_load(wrapper);
	rf_start_timers(wrapper);
};

frappe.pages["rfid-mapping"].on_page_show = function (wrapper) {
	if (wrapper._rfid && !wrapper._rfid.live_interval) rf_start_timers(wrapper);
};

frappe.pages["rfid-mapping"].on_page_hide = function (wrapper) {
	if (!wrapper._rfid) return;
	clearInterval(wrapper._rfid.live_interval);
	clearInterval(wrapper._rfid.countdown_interval);
	wrapper._rfid.live_interval = wrapper._rfid.countdown_interval = null;
};

function rf_start_timers(wrapper) {
	const st = wrapper._rfid;
	st.countdown = RF_REFRESH_SECS;
	$(wrapper).find("#rf-countdown").text(st.countdown);
	st.live_interval = setInterval(() => rf_live_refresh(wrapper), RF_REFRESH_SECS * 1000);
	st.countdown_interval = setInterval(() => {
		st.countdown = st.countdown <= 1 ? RF_REFRESH_SECS : st.countdown - 1;
		$(wrapper).find("#rf-countdown").text(st.countdown);
	}, 1000);
}

// ─────────────────────────────────────────────────────────────────
// Data loading
// ─────────────────────────────────────────────────────────────────
function rf_full_load(wrapper) {
	rf_set_status(wrapper, "syncing");
	frappe.call({
		method: RF_API + "get_rfid_summary",
		callback(r) {
			const d = r.message;
			if (!d) return;
			rf_render_stats(wrapper, d.stats, d.student_stats);
			wrapper._rfid.unassigned.refresh(d.unlinked_cards || []);
			wrapper._rfid.linked.refresh(d.linked_students || []);
			wrapper._rfid.feed.refresh(d.recent_logs || []);
			rf_set_count(wrapper, "unassigned", (d.unlinked_cards || []).length);
			rf_set_count(wrapper, "linked", (d.linked_students || []).length);
			wrapper._rfid.last_swipe_time = d.stats.last_swipe || null;
			wrapper._rfid.countdown = RF_REFRESH_SECS;
			rf_set_status(wrapper, "live");
		},
		error: () => rf_set_status(wrapper, "error"),
	});
}

function rf_live_refresh(wrapper) {
	if (wrapper._rfid.busy) return;
	wrapper._rfid.busy = true;
	rf_set_status(wrapper, "syncing");
	frappe.call({
		method: RF_API + "get_live_feed",
		args: { since_swipe_time: wrapper._rfid.last_swipe_time || "" },
		callback(r) {
			const d = r.message;
			if (!d) return;
			rf_render_stats(wrapper, d.stats, null);
			const added = wrapper._rfid.feed.prepend(d.new_logs || []);
			if (d.stats.last_swipe) wrapper._rfid.last_swipe_time = d.stats.last_swipe;
			if (added) frappe.show_alert({ message: __("{0} new swipe(s)", [added]), indicator: "green" }, 4);
			wrapper._rfid.countdown = RF_REFRESH_SECS;
			rf_set_status(wrapper, "live");
		},
		error: () => rf_set_status(wrapper, "error"),
		always: () => (wrapper._rfid.busy = false),
	});
}

function rf_refresh_now(wrapper) {
	const $btn = $(wrapper).find("#rf-refresh");
	$btn.prop("disabled", true).addClass("is-loading");
	rf_set_status(wrapper, "syncing");
	frappe.call({
		method: RF_API + "pull_now",
		callback(r) {
			const m = r.message || {};
			if (m.success) frappe.show_alert({ message: m.message, indicator: "green" }, 5);
			else frappe.msgprint({ title: __("Refresh failed"), message: m.message || __("Unknown error."), indicator: "red" });
			rf_full_load(wrapper);
		},
		error: () => rf_set_status(wrapper, "error"),
		always: () => $btn.prop("disabled", false).removeClass("is-loading"),
	});
}

// ─────────────────────────────────────────────────────────────────
// Stats & status
// ─────────────────────────────────────────────────────────────────
function rf_render_stats(wrapper, s, ss) {
	const $w = $(wrapper);
	const total = cint(s.total_logs), linked = cint(s.linked_logs), unlinked = cint(s.unlinked_logs);
	$w.find("#st-total").text(rf_fmt(total));
	$w.find("#st-linked").text(rf_fmt(linked));
	$w.find("#st-unlinked").text(rf_fmt(unlinked));
	rf_meter($w.find("#mt-swipes"), linked, total, __("of swipes identified"));
	$w.find("#st-last-swipe").text(s.last_swipe ? frappe.datetime.prettyDate(s.last_swipe) : "—");

	if (!ss) return;
	const students = cint(ss.total_students), withc = cint(ss.students_with_rfid), noid = cint(ss.students_without_id);
	$w.find("#st-students").text(rf_fmt(students));
	$w.find("#st-with-card").text(rf_fmt(withc));
	$w.find("#st-no-card").text(rf_fmt(cint(ss.students_without_rfid)));
	rf_meter($w.find("#mt-students"), withc, students, __("of students carry a card"));

	const $warn = $w.find("#rf-noid");
	if (noid > 0) {
		$warn.find(".rf-noid-count").text(rf_fmt(noid));
		$warn.show();
	} else $warn.hide();
}

function rf_meter($m, part, whole, label) {
	const pct = whole ? Math.round((part / whole) * 100) : 0;
	$m.find(".rf-meter-fill").css("width", pct + "%");
	$m.find(".rf-meter-lbl").text(`${pct}% ${label}`);
}

function rf_set_count(wrapper, tab, n) {
	$(wrapper).find(`#count-${tab}`).text(rf_fmt(n)).toggle(n > 0);
}

function rf_set_status(wrapper, state) {
	const $s = $(wrapper).find("#rf-status");
	$s.removeClass("is-live is-syncing is-error").addClass("is-" + state);
	$s.find(".rf-status-text").text(
		{ live: __("Live"), syncing: __("Syncing…"), error: __("Connection problem") }[state]
	);
}

// ─────────────────────────────────────────────────────────────────
// Events
// ─────────────────────────────────────────────────────────────────
function rf_bind(wrapper) {
	const $w = $(wrapper);
	$w.on("click", ".rf-tab", function () {
		const tab = $(this).data("tab");
		$w.find(".rf-tab").removeClass("active").attr("aria-selected", "false");
		$(this).addClass("active").attr("aria-selected", "true");
		$w.find(".rf-panel").removeClass("active");
		$w.find("#panel-" + tab).addClass("active");
	});
	$w.on("click", "#rf-refresh", () => rf_refresh_now(wrapper));
	$w.on("click", "#rf-export", () => rf_export());
	$w.on("click", "#rf-import", () => rf_import_dialog(wrapper));
	$w.on("click", "[data-assign]", function () { rf_assign_dialog($(this).attr("data-assign"), wrapper); });
	$w.on("click", "[data-unlink]", function () {
		rf_unlink($(this).attr("data-unlink"), $(this).attr("data-label"), $(this).attr("data-uid"), wrapper);
	});
}

// ─────────────────────────────────────────────────────────────────
// Lightweight table: search + sort + pagination. Created once, refreshed with data.
// ─────────────────────────────────────────────────────────────────
function rf_table({ $root, columns, search_keys, page_size = 25, empty_msg, default_sort, row_key }) {
	let data = [], view = [], query = "", page = 0;
	let sort = default_sort ? { ...default_sort } : null;

	const $thead = $root.find("thead tr");
	const $tbody = $root.find("tbody");
	const $info = $root.find(".rf-page-info");
	const $prev = $root.find(".rf-prev");
	const $next = $root.find(".rf-next");

	$thead.html(columns.map((c, i) =>
		`<th data-i="${i}" class="${c.cls || ""} ${c.sortable === false ? "" : "sortable"}">${c.label}</th>`).join(""));

	$thead.on("click", "th.sortable", function () {
		const key = columns[$(this).data("i")].key;
		sort = sort && sort.key === key ? { key, dir: sort.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" };
		page = 0; apply(); render();
	});
	$root.find(".rf-search").on("input", frappe.utils.debounce(function () {
		query = ($(this).val() || "").trim().toLowerCase();
		page = 0; apply(); render();
	}, 150));
	$prev.on("click", () => { if (page > 0) { page--; render(); } });
	$next.on("click", () => { if ((page + 1) * page_size < view.length) { page++; render(); } });

	function apply() {
		view = !query ? data.slice() : data.filter(r =>
			search_keys.some(k => r[k] != null && String(r[k]).toLowerCase().includes(query)));
		if (sort) {
			const { key, dir } = sort;
			view.sort((a, b) => {
				const av = a[key] ?? "", bv = b[key] ?? "";
				const cmp = typeof av === "number" && typeof bv === "number"
					? av - bv : String(av).localeCompare(String(bv), undefined, { numeric: true });
				return dir === "asc" ? cmp : -cmp;
			});
		}
	}

	function render() {
		$thead.find("th").removeClass("asc desc").each(function () {
			if (sort && columns[$(this).data("i")].key === sort.key) $(this).addClass(sort.dir);
		});
		const total = view.length;
		const max_page = Math.max(0, Math.ceil(total / page_size) - 1);
		page = Math.min(page, max_page);
		const start = page * page_size, end = Math.min(start + page_size, total);

		$info.text(total ? __("{0}–{1} of {2}", [rf_fmt(start + 1), rf_fmt(end), rf_fmt(total)]) : "");
		$prev.prop("disabled", page === 0);
		$next.prop("disabled", page >= max_page);

		if (!total) {
			const msg = data.length ? __("Nothing matches your search.") : empty_msg;
			$tbody.html(`<tr class="rf-empty"><td colspan="${columns.length}">${msg}</td></tr>`);
			return;
		}
		$tbody.html(view.slice(start, end).map(row =>
			`<tr>${columns.map(c => `<td class="${c.cls || ""}">${c.render ? c.render(row) : rf_esc(row[c.key])}</td>`).join("")}</tr>`
		).join(""));
	}

	return {
		refresh(rows) { data = (rows || []).slice(); apply(); render(); },
		// add rows to the top (live feed); returns how many were actually new
		prepend(rows) {
			const keys = new Set(data.map(row_key));
			const fresh = (rows || []).filter(r => { const k = row_key(r); if (keys.has(k)) return false; keys.add(k); return true; });
			if (!fresh.length) return 0;
			data = fresh.concat(data).slice(0, RF_FEED_MAX);
			apply(); render();
			const fresh_keys = new Set(fresh.map(row_key));
			$tbody.find("tr").each(function (i) {
				const row = view[page * page_size + i];
				if (row && fresh_keys.has(row_key(row))) $(this).addClass("rf-flash");
			});
			return fresh.length;
		},
	};
}

function rf_init_tables(wrapper) {
	const $w = $(wrapper);
	const st = wrapper._rfid;

	st.unassigned = rf_table({
		$root: $w.find("#panel-unassigned"),
		search_keys: ["rfid_uid", "terminal_id", "terminal", "area"],
		default_sort: { key: "last_seen", dir: "desc" },
		empty_msg: `<div class="rf-allgood"><i class="fa fa-check-circle"></i>${__("Every card seen on the readers belongs to a student.")}</div>`,
		columns: [
			{ key: "rfid_uid", label: __("RFID UID"), render: r => `<span class="rf-uid">${rf_esc(r.rfid_uid)}</span>` },
			{ key: "swipe_count", label: __("Swipes"), cls: "num", render: r => `<span class="rf-num">${rf_fmt(r.swipe_count)}</span>` },
			{ key: "terminal", label: __("Room"), render: r => r.terminal ? `<span class="rf-chip">${rf_esc(r.terminal)}</span>` : rf_dash() },
			{ key: "terminal_id", label: __("Terminal"), render: r => rf_muted(r.terminal_id) },
			{ key: "area", label: __("Area"), render: r => rf_muted(r.area) },
			{ key: "last_seen", label: __("Last seen"), render: r => rf_when(r.last_seen) },
			{ key: "_a", label: "", sortable: false, cls: "act",
			  render: r => `<button class="rf-btn rf-btn-primary rf-btn-sm" data-assign="${rf_esc(r.rfid_uid)}"><i class="fa fa-link"></i> ${__("Assign")}</button>` },
		],
	});

	st.linked = rf_table({
		$root: $w.find("#panel-linked"),
		search_keys: ["student_id", "student_name", "rfid_uid", "programme", "batch_year", "department"],
		default_sort: { key: "student_id", dir: "asc" },
		empty_msg: __("No student has a card yet."),
		columns: [
			{ key: "student_id", label: __("Student ID"), render: r => rf_sid(r.student_id) },
			{ key: "student_name", label: __("Student"),
			  render: r => `<a class="rf-link" href="/app/student-master/${encodeURIComponent(r.student)}" target="_blank" rel="noopener">${rf_esc(r.student_name || r.student_id)}</a>` },
			{ key: "rfid_uid", label: __("RFID UID"), render: r => `<span class="rf-uid">${rf_esc(r.rfid_uid)}</span>` },
			{ key: "programme", label: __("Programme"), render: r => rf_muted(r.programme) },
			{ key: "batch_year", label: __("Batch"), render: r => rf_muted(r.batch_year) },
			{ key: "total_swipes", label: __("Swipes"), cls: "num", render: r => `<span class="rf-num">${rf_fmt(r.total_swipes)}</span>` },
			{ key: "last_swipe", label: __("Last swipe"), render: r => r.last_swipe ? rf_when(r.last_swipe) : rf_muted(__("Never")) },
			{ key: "_a", label: "", sortable: false, cls: "act",
			  render: r => cint(r.has_active_card)
				? `<button class="rf-btn rf-btn-ghost rf-btn-sm" title="${__("Remove a wrongly linked card")}"
					data-unlink="${rf_esc(r.student)}" data-uid="${rf_esc(r.rfid_uid)}"
					data-label="${rf_esc((r.student_name || "") + (r.student_id ? " (" + r.student_id + ")" : ""))}">
					<i class="fa fa-unlink"></i> ${__("Unlink")}</button>`
				: "" },
		],
	});

	st.feed = rf_table({
		$root: $w.find("#panel-feed"),
		search_keys: ["rfid_uid", "student_id", "student_name", "device_id", "terminal_alias", "area_alias"],
		default_sort: { key: "swipe_time", dir: "desc" },
		row_key: r => `${r.rfid_uid || ""}|${r.swipe_time || ""}|${r.device_id || ""}`,
		empty_msg: __("No swipes yet."),
		columns: [
			{ key: "swipe_time", label: __("Time"), render: r => rf_when(r.swipe_time) },
			{ key: "rfid_uid", label: __("RFID UID"), render: r => `<span class="rf-uid">${rf_esc(r.rfid_uid)}</span>` },
			{ key: "student_name", label: __("Student"),
			  render: r => r.student
				? `<a class="rf-link" href="/app/student-master/${encodeURIComponent(r.student)}" target="_blank" rel="noopener">${rf_esc(r.student_name || r.student_id)}</a> ${rf_sid(r.student_id)}`
				: `<span class="rf-unknown"><i class="fa fa-question-circle"></i> ${__("Unassigned card")}</span>` },
			{ key: "terminal_alias", label: __("Room"), render: r => r.terminal_alias ? `<span class="rf-chip">${rf_esc(r.terminal_alias)}</span>` : rf_dash() },
			{ key: "area_alias", label: __("Area"), render: r => rf_muted(r.area_alias) },
			{ key: "processed", label: __("Status"),
			  render: r => cint(r.processed) ? `<span class="rf-tag ok">${__("Processed")}</span>` : `<span class="rf-tag warn">${__("Pending")}</span>` },
		],
	});
}

// ─────────────────────────────────────────────────────────────────
// Assign a card — search by Student ID / name
// ─────────────────────────────────────────────────────────────────
function rf_assign_dialog(rfid_uid, wrapper) {
	let selected = null;
	const d = new frappe.ui.Dialog({
		title: __("Assign card"),
		fields: [
			{ fieldname: "card", fieldtype: "HTML", options: `
				<div class="rf-card-hero">
					<div class="rf-card-chip"><i class="fa fa-id-card-o"></i></div>
					<div>
						<div class="rf-eyebrow">${__("RFID UID read from the terminal")}</div>
						<div class="rf-card-uid">${rf_esc(rfid_uid)}</div>
					</div>
				</div>` },
			{ fieldname: "q", fieldtype: "Data", label: __("Find student"),
			  placeholder: __("Type a Student ID (e.g. L26001) or name") },
			{ fieldname: "results", fieldtype: "HTML" },
		],
		primary_action_label: __("Assign card"),
		primary_action() {
			if (!selected) { frappe.show_alert({ message: __("Pick a student first."), indicator: "orange" }); return; }
			d.get_primary_btn().prop("disabled", true);
			frappe.call({
				method: RF_API + "link_rfid_to_student",
				args: { rfid_uid, student: selected.name },
				freeze: true, freeze_message: __("Linking card…"),
				callback(r) {
					if (r.message && r.message.success) {
						frappe.show_alert({ message: r.message.message, indicator: "green" }, 6);
						d.hide();
						rf_full_load(wrapper);
					}
				},
				always: () => d.get_primary_btn().prop("disabled", false),
			});
		},
	});
	d.$wrapper.addClass("rf-dlg");
	const $res = d.fields_dict.results.$wrapper;
	let seq = 0;

	const search = frappe.utils.debounce(txt => {
		const my = ++seq;
		$res.html(`<div class="rf-pick-empty">${__("Searching…")}</div>`);
		frappe.call({
			method: RF_API + "search_students",
			args: { txt, only_without_card: 1 },
			callback(r) {
				if (my !== seq) return; // a newer search is running
				const rows = r.message || [];
				if (!rows.length) {
					$res.html(`<div class="rf-pick-empty">${txt ? __("No student without a card matches “{0}”.", [rf_esc(txt)]) : __("Every student with a Student ID already has a card.")}</div>`);
					return;
				}
				$res.html(`<div class="rf-pick">${rows.map((s, i) => `
					<button type="button" class="rf-pick-row ${selected && selected.name === s.name ? "on" : ""}" data-i="${i}">
						${rf_sid(s.student_id)}
						<span class="rf-pick-main">
							<span class="rf-pick-name">${rf_esc(s.student_name)}</span>
							<span class="rf-pick-meta">${rf_esc([s.programme, s.batch_year, s.academic_status].filter(Boolean).join(" · "))}</span>
						</span>
						<i class="fa fa-check-circle rf-pick-tick"></i>
					</button>`).join("")}</div>`);
				$res.find(".rf-pick-row").on("click", function () {
					selected = rows[$(this).data("i")];
					$res.find(".rf-pick-row").removeClass("on");
					$(this).addClass("on");
					d.set_title(__("Assign card to {0}", [selected.student_id]));
				});
			},
		});
	}, 250);

	d.fields_dict.q.$input.on("input", function () {
		selected = null;
		d.set_title(__("Assign card"));
		search(($(this).val() || "").trim());
	});
	d.show();
	search("");
	setTimeout(() => d.fields_dict.q.$input.trigger("focus"), 250);
}

function rf_unlink(student, label, uid, wrapper) {
	frappe.confirm(
		__("Remove card {0} from {1}? Their swipes on this card will show as unassigned again.", [`<b>${rf_esc(uid)}</b>`, `<b>${rf_esc(label)}</b>`]),
		() => frappe.call({
			method: RF_API + "unlink_rfid_from_student",
			args: { student },
			freeze: true,
			callback(r) {
				if (!r.message) return;
				frappe.show_alert({ message: r.message.message, indicator: r.message.success ? "green" : "orange" }, 5);
				rf_full_load(wrapper);
			},
		})
	);
}

// ─────────────────────────────────────────────────────────────────
// Export for vendor
// ─────────────────────────────────────────────────────────────────
function rf_export() {
	frappe.call({
		method: RF_API + "get_export_data",
		freeze: true, freeze_message: __("Preparing list…"),
		callback(r) {
			const { rows = [], missing_id = 0 } = r.message || {};
			const skipped = missing_id
				? `<br><br>${__("{0} student(s) without a Student ID were left out — they cannot be matched when the file comes back.", [`<b>${rf_fmt(missing_id)}</b>`])}`
				: "";
			if (!rows.length) {
				frappe.msgprint({ title: __("Nothing to export"), message: __("Every active student with a Student ID already has a card.") + skipped });
				return;
			}
			const headers = ["student_id", "student_name", "programme", "batch_year", "department", "email", "rfid_uid"];
			const csv = [headers.join(",")].concat(rows.map(row => headers.map(h => rf_csv_cell(row[h])).join(","))).join("\r\n");
			rf_download("﻿" + csv, `rfid_vendor_list_${frappe.datetime.get_today()}.csv`, "text/csv;charset=utf-8");
			if (skipped) frappe.msgprint({ title: __("Exported {0} student(s)", [rf_fmt(rows.length)]), message: skipped.slice(8), indicator: "orange" });
			else frappe.show_alert({ message: __("Exported {0} student(s) for the vendor", [rf_fmt(rows.length)]), indicator: "blue" }, 5);
		},
	});
}

// ─────────────────────────────────────────────────────────────────
// Bulk import — upload / paste → preview → confirm
// ─────────────────────────────────────────────────────────────────
function rf_import_dialog(wrapper) {
	const d = new frappe.ui.Dialog({
		title: __("Import card assignments"),
		size: "large",
		fields: [
			{ fieldname: "how", fieldtype: "HTML", options: `
				<ol class="rf-steps">
					<li><b>${__("Export for vendor")}</b><span>${__("CSV of students without a card, keyed by Student ID")}</span></li>
					<li><b>${__("Vendor fills rfid_uid")}</b><span>${__("One card per row — leave the student_id column as it is")}</span></li>
					<li><b>${__("Upload here")}</b><span>${__("Check the preview, then confirm")}</span></li>
				</ol>
				<div class="rf-cols">
					${__("Required columns")}: <span class="rf-uid">student_id</span> <span class="rf-uid">rfid_uid</span>
					<span class="rf-cols-note">${__("student_id is the Student ID, e.g. L26001 · .csv or .xlsx")}</span>
					<a class="rf-textlink" id="rf-template"><i class="fa fa-download"></i> ${__("Sample template")}</a>
				</div>` },
			{ fieldname: "file_upload", fieldtype: "Attach", label: __("Upload file"),
			  options: { restrictions: { allowed_file_types: [".csv", ".xlsx"] } } },
			{ fieldname: "paste_sb", fieldtype: "Section Break", label: __("Or paste CSV"), collapsible: 1 },
			{ fieldname: "csv_paste", fieldtype: "Code", options: "None",
			  description: __("First line: student_id,rfid_uid — then one student per line.") },
		],
		primary_action_label: __("Preview"),
		primary_action(val) {
			const source = val.file_upload ? { file_url: val.file_upload } : { csv_data: (val.csv_paste || "").trim() };
			if (!source.file_url && !source.csv_data) {
				frappe.show_alert({ message: __("Upload a file or paste CSV first."), indicator: "orange" });
				return;
			}
			frappe.call({
				method: RF_API + "bulk_import_rfid",
				args: { ...source, dry_run: 1 },
				freeze: true, freeze_message: __("Checking file…"),
				callback(r) {
					if (!r.message) return;
					d.hide();
					rf_preview_dialog(r.message, source, wrapper, d);
				},
			});
		},
	});
	d.$wrapper.addClass("rf-dlg");
	d.$wrapper.find("#rf-template").on("click", () =>
		rf_download("student_id,rfid_uid\r\nL26001,B24221\r\nL26002,LLB/2690/2020\r\n", "rfid_import_template.csv", "text/csv"));
	d.show();
}

const RF_STATUS = {
	ready:     { label: __("Will link"),  cls: "ok" },
	linked:    { label: __("Linked"),     cls: "ok" },
	unchanged: { label: __("No change"),  cls: "info" },
	skipped:   { label: __("Skipped"),    cls: "info" },
	error:     { label: __("Problem"),    cls: "err" },
};

function rf_result_html(res) {
	const c = res.counts || {};
	const done = c.linked || 0, ready = c.ready || 0, err = c.error || 0, other = (c.unchanged || 0) + (c.skipped || 0);
	const tiles = [
		res.dry_run ? [ready, __("ready to link"), "ok"] : [done, __("linked"), "ok"],
		[err, __("with problems"), "err"],
		[other, __("no change / skipped"), "info"],
	].map(([n, l, cls]) => `<div class="rf-sum ${cls}"><b>${rf_fmt(n)}</b><span>${l}</span></div>`).join("");

	// problems first, then the rest in file order
	const order = { error: 0, ready: 1, linked: 1, unchanged: 2, skipped: 3 };
	const rows = (res.rows || []).slice().sort((a, b) => (order[a.status] - order[b.status]) || a.row - b.row);
	const body = rows.map(r => {
		const s = RF_STATUS[r.status] || RF_STATUS.skipped;
		const note = r.reason ? rf_esc(r.reason)
			: r.replaces ? __("Replaces card {0}", [`<span class="rf-uid">${rf_esc(r.replaces)}</span>`])
			: r.swipes != null ? __("{0} swipe(s) matched", [r.swipes]) : "";
		return `<tr>
			<td class="num rf-dim">${r.row}</td>
			<td>${rf_sid(r.student_id)}</td>
			<td>${rf_esc(r.student_name) || rf_dash()}</td>
			<td>${r.rfid_uid ? `<span class="rf-uid">${rf_esc(r.rfid_uid)}</span>` : rf_dash()}</td>
			<td><span class="rf-tag ${s.cls}">${s.label}</span></td>
			<td class="rf-note">${note}</td>
		</tr>`;
	}).join("");

	return `<div class="rf-sums">${tiles}</div>
		<div class="rf-tablebox rf-tablebox-sm"><table class="rf-table">
			<thead><tr><th class="num">${__("Row")}</th><th>${__("Student ID")}</th><th>${__("Student")}</th><th>${__("RFID UID")}</th><th>${__("Result")}</th><th>${__("Note")}</th></tr></thead>
			<tbody>${body || `<tr class="rf-empty"><td colspan="6">${__("The file has no data rows.")}</td></tr>`}</tbody>
		</table></div>`;
}

function rf_preview_dialog(res, source, wrapper, input_dialog) {
	const ready = (res.counts || {}).ready || 0;
	const d = new frappe.ui.Dialog({
		title: __("Check before importing"),
		size: "extra-large",
		fields: [{ fieldname: "body", fieldtype: "HTML", options: rf_result_html(res) }],
		primary_action_label: ready ? __("Link {0} card(s)", [rf_fmt(ready)]) : __("Nothing to link"),
		primary_action() {
			if (!ready) return;
			frappe.call({
				method: RF_API + "bulk_import_rfid",
				args: { ...source, dry_run: 0 },
				freeze: true, freeze_message: __("Linking cards…"),
				callback(r) {
					if (!r.message) return;
					d.set_title(__("Import finished"));
					d.fields_dict.body.$wrapper.html(rf_result_html(r.message));
					d.get_primary_btn().hide();
					d.set_secondary_action_label(__("Close"));
					d.set_secondary_action(() => d.hide());
					rf_full_load(wrapper);
				},
			});
		},
		secondary_action_label: __("Back"),
		secondary_action() { d.hide(); input_dialog.show(); },
	});
	d.$wrapper.addClass("rf-dlg");
	if (!ready) d.get_primary_btn().prop("disabled", true);
	d.show();
}

// ─────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────
const rf_esc = s => (s == null ? "" : frappe.utils.escape_html(String(s)));
const rf_fmt = n => (parseInt(n, 10) || 0).toLocaleString("en-IN");
const rf_dash = () => `<span class="rf-dim">—</span>`;
const rf_muted = v => (v ? `<span class="rf-dim">${rf_esc(v)}</span>` : rf_dash());
const rf_sid = v => (v ? `<span class="rf-sid">${rf_esc(v)}</span>` : `<span class="rf-sid none">${__("No ID")}</span>`);
const rf_when = v => v
	? `<span class="rf-when">${rf_esc(frappe.datetime.str_to_user(v))}<small>${rf_esc(frappe.datetime.prettyDate(v))}</small></span>`
	: rf_dash();

function rf_csv_cell(v) {
	let s = v == null ? "" : String(v);
	if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; // stop spreadsheet formula injection
	return `"${s.replace(/"/g, '""')}"`;
}

function rf_download(content, name, mime) {
	const url = URL.createObjectURL(new Blob([content], { type: mime }));
	const a = Object.assign(document.createElement("a"), { href: url, download: name });
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ─────────────────────────────────────────────────────────────────
// Markup
// ─────────────────────────────────────────────────────────────────
function rf_toolbar(placeholder) {
	return `<div class="rf-toolbar">
		<label class="rf-searchbox"><i class="fa fa-search"></i><input class="rf-search" type="search" placeholder="${placeholder}"></label>
		<div class="rf-pager">
			<span class="rf-page-info"></span>
			<button class="rf-iconbtn rf-prev" aria-label="${__("Previous page")}" disabled><i class="fa fa-chevron-left"></i></button>
			<button class="rf-iconbtn rf-next" aria-label="${__("Next page")}" disabled><i class="fa fa-chevron-right"></i></button>
		</div>
	</div>
	<div class="rf-tablebox"><table class="rf-table"><thead><tr></tr></thead>
		<tbody><tr class="rf-empty"><td>${__("Loading…")}</td></tr></tbody></table></div>`;
}

function rf_html() {
	return `
<div class="rfid-wrap">
	<header class="rf-head">
		<div>
			<div class="rf-eyebrow">${__("Attendance · RFID")}</div>
			<h1 class="rf-title">${__("RFID Card Management")}</h1>
			<p class="rf-sub">${__("Match cards seen on the classroom readers to students by their Student ID.")}</p>
		</div>
		<div class="rf-head-side">
			<div class="rf-status is-live" id="rf-status" title="${__("SQL Server is pulled every minute in the background")}">
				<span class="rf-dot"></span><span class="rf-status-text">${__("Live")}</span>
				<span class="rf-status-sep"></span>
				<span>${__("refresh in")} <b id="rf-countdown">${RF_REFRESH_SECS}</b>s</span>
			</div>
			<button class="rf-btn rf-btn-ghost" id="rf-refresh"><i class="fa fa-refresh"></i> ${__("Pull now")}</button>
		</div>
	</header>

	<div class="rf-banner" id="rf-noid" style="display:none">
		<i class="fa fa-exclamation-triangle"></i>
		<div>${__("{0} student(s) have no Student ID yet. They are left out of the vendor export and cannot be picked when assigning a card.", ['<b class="rf-noid-count">0</b>'])}
			<a class="rf-textlink" href="/app/student-master?registration_id=%5B%22is%22%2C%22not%20set%22%5D" target="_blank" rel="noopener">${__("Show them")} →</a></div>
	</div>

	<section class="rf-kpis">
		<div class="rf-kpi-group">
			<div class="rf-kpi-head"><span>${__("Swipes")}</span>
				<a class="rf-textlink" href="/app/attendance-log" target="_blank" rel="noopener">${__("Attendance Log")} →</a></div>
			<div class="rf-kpi-row">
				<div class="rf-kpi"><b id="st-total">—</b><span>${__("Imported")}</span></div>
				<div class="rf-kpi"><b id="st-linked">—</b><span>${__("Identified")}</span></div>
				<div class="rf-kpi alert"><b id="st-unlinked">—</b><span>${__("Unidentified")}</span></div>
			</div>
			<div class="rf-meter" id="mt-swipes"><div class="rf-meter-bar"><div class="rf-meter-fill"></div></div>
				<div class="rf-meter-foot"><span class="rf-meter-lbl"></span><span>${__("Last swipe")} <b id="st-last-swipe">—</b></span></div></div>
		</div>
		<div class="rf-kpi-group">
			<div class="rf-kpi-head"><span>${__("Student cards")}</span>
				<a class="rf-textlink" href="/app/student-rfid-card" target="_blank" rel="noopener">${__("Card history")} →</a></div>
			<div class="rf-kpi-row">
				<div class="rf-kpi"><b id="st-students">—</b><span>${__("Students")}</span></div>
				<div class="rf-kpi"><b id="st-with-card">—</b><span>${__("With card")}</span></div>
				<div class="rf-kpi alert"><b id="st-no-card">—</b><span>${__("Without card")}</span></div>
			</div>
			<div class="rf-meter" id="mt-students"><div class="rf-meter-bar"><div class="rf-meter-fill"></div></div>
				<div class="rf-meter-foot"><span class="rf-meter-lbl"></span></div></div>
		</div>
	</section>

	<nav class="rf-tabs" role="tablist">
		<button class="rf-tab active" data-tab="unassigned" role="tab" aria-selected="true">
			${__("Unassigned cards")} <span class="rf-count" id="count-unassigned" style="display:none"></span></button>
		<button class="rf-tab" data-tab="linked" role="tab" aria-selected="false">
			${__("Student cards")} <span class="rf-count" id="count-linked" style="display:none"></span></button>
		<button class="rf-tab" data-tab="feed" role="tab" aria-selected="false">
			<span class="rf-dot sm"></span> ${__("Live feed")}</button>
	</nav>

	<section class="rf-panel active" id="panel-unassigned">
		<div class="rf-panel-head">
			<div>
				<h2>${__("Cards nobody owns yet")}</h2>
				<p>${__("Assign one card at a time, or export the student list for the vendor and import it back filled in.")}</p>
			</div>
			<div class="rf-actions">
				<button class="rf-btn rf-btn-ghost" id="rf-export"><i class="fa fa-download"></i> ${__("Export for vendor")}</button>
				<button class="rf-btn rf-btn-primary" id="rf-import"><i class="fa fa-upload"></i> ${__("Import file")}</button>
			</div>
		</div>
		${rf_toolbar(__("Search card, room, terminal…"))}
	</section>

	<section class="rf-panel" id="panel-linked">
		<div class="rf-panel-head">
			<div>
				<h2>${__("Students with a card")}</h2>
				<p>${__("Swipes on these cards count towards attendance automatically. Unlink only when a card was given to the wrong student.")}</p>
			</div>
		</div>
		${rf_toolbar(__("Search Student ID, name, card, programme…"))}
	</section>

	<section class="rf-panel" id="panel-feed">
		<div class="rf-panel-head">
			<div>
				<h2>${__("Latest swipes")}</h2>
				<p>${__("The last {0} swipes from the readers (SQL Server dbo.iclock_trans_ajim). New swipes appear at the top and are highlighted.", [RF_FEED_MAX])}</p>
			</div>
		</div>
		${rf_toolbar(__("Search card, Student ID, student, room…"))}
	</section>
</div>`;
}

function rf_css() {
	return `
.rfid-wrap, .rf-dlg {
	--rf-brand: #920C24; --rf-brand-dk: #6E091B; --rf-brand-50: #FBF1F3; --rf-brand-100: #F5DDE2;
	--rf-ink: #1F1A1C; --rf-ink-2: #5C5457; --rf-ink-3: #8E8588;
	--rf-surface: #FFFFFF; --rf-canvas: #F7F5F5; --rf-line: #ECE6E7; --rf-line-2: #F4F0F1;
	--rf-ok: #1E7B4C; --rf-ok-bg: #E7F5EE; --rf-warn: #8A5A00; --rf-warn-bg: #FFF4DB;
	--rf-info: #4B5563; --rf-info-bg: #F1F2F4; --rf-err: #B42318; --rf-err-bg: #FDECEA;
	--rf-serif: "Merriweather", Georgia, "Times New Roman", serif;
	--rf-mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
}
[data-theme="dark"] .rfid-wrap, [data-theme="dark"] .rf-dlg {
	--rf-brand: #E0566F; --rf-brand-dk: #F07A8F; --rf-brand-50: #2A1A1E; --rf-brand-100: #3A2228;
	--rf-ink: #F2EDEE; --rf-ink-2: #C2B8BB; --rf-ink-3: #8E8588;
	--rf-surface: #1E1B1C; --rf-canvas: #161314; --rf-line: #332C2E; --rf-line-2: #282223;
	--rf-ok: #5CC995; --rf-ok-bg: #16291F; --rf-warn: #F2C063; --rf-warn-bg: #2E2614;
	--rf-info: #B6BCC6; --rf-info-bg: #24272B; --rf-err: #F28B82; --rf-err-bg: #2E1A18;
}
.rfid-wrap { font-family: var(--rf-serif); color: var(--rf-ink); background: var(--rf-canvas);
	padding: 28px 32px 48px; min-height: 100vh; font-size: 14px; line-height: 1.55; }
.rfid-wrap button, .rfid-wrap input, .rf-dlg .modal-body button, .rf-dlg .modal-body input { font-family: inherit; }
.rf-dlg .modal-content { font-family: var(--rf-serif); }
.rf-dlg .modal-title { font-weight: 700; color: var(--rf-ink); }
.rfid-wrap h1, .rfid-wrap h2 { font-family: var(--rf-serif); margin: 0; color: var(--rf-ink); }

/* header */
.rf-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; flex-wrap: wrap; margin-bottom: 24px; }
.rf-eyebrow { font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: var(--rf-brand); font-weight: 700; margin-bottom: 6px; }
.rf-title { font-size: 28px; font-weight: 800; letter-spacing: -.01em; line-height: 1.2; }
.rf-sub { margin: 6px 0 0; color: var(--rf-ink-2); font-weight: 300; }
.rf-head-side { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rf-status { display: inline-flex; align-items: center; gap: 8px; padding: 7px 14px; border-radius: 999px;
	background: var(--rf-surface); border: 1px solid var(--rf-line); font-size: 12.5px; color: var(--rf-ink-2); }
.rf-status-text { font-weight: 700; color: var(--rf-ink); }
.rf-status-sep { width: 1px; height: 14px; background: var(--rf-line); }
.rf-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--rf-ok); box-shadow: 0 0 0 0 rgba(30,123,76,.5); animation: rf-pulse 2s infinite; }
.rf-dot.sm { width: 7px; height: 7px; display: inline-block; vertical-align: middle; margin-right: 2px; }
.rf-status.is-syncing .rf-dot { background: #D99A00; animation: rf-blink .9s infinite; }
.rf-status.is-error .rf-dot { background: var(--rf-err); animation: none; }
@keyframes rf-pulse { 0% { box-shadow: 0 0 0 0 rgba(30,123,76,.45); } 70% { box-shadow: 0 0 0 7px rgba(30,123,76,0); } 100% { box-shadow: 0 0 0 0 rgba(30,123,76,0); } }
@keyframes rf-blink { 50% { opacity: .3; } }

/* buttons */
.rf-btn { display: inline-flex; align-items: center; gap: 7px; border-radius: 8px; padding: 8px 15px; font-size: 13px;
	font-weight: 700; cursor: pointer; border: 1px solid transparent; transition: background .15s, border-color .15s, color .15s; white-space: nowrap; }
.rf-btn:focus-visible, .rf-iconbtn:focus-visible, .rf-tab:focus-visible, .rf-pick-row:focus-visible { outline: 2px solid var(--rf-brand); outline-offset: 2px; }
.rf-btn:disabled { opacity: .55; cursor: default; }
.rf-btn-primary { background: var(--rf-brand); color: #fff; }
.rf-btn-primary:hover:not(:disabled) { background: var(--rf-brand-dk); }
.rf-btn-ghost { background: var(--rf-surface); color: var(--rf-brand); border-color: var(--rf-line); }
.rf-btn-ghost:hover:not(:disabled) { border-color: var(--rf-brand); background: var(--rf-brand-50); }
.rf-btn-sm { padding: 5px 11px; font-size: 12px; }
.rf-btn.is-loading .fa-refresh { animation: rf-spin .8s linear infinite; }
@keyframes rf-spin { to { transform: rotate(360deg); } }
.rf-iconbtn { width: 32px; height: 32px; border-radius: 8px; border: 1px solid var(--rf-line); background: var(--rf-surface);
	color: var(--rf-ink-2); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
.rf-iconbtn:hover:not(:disabled) { border-color: var(--rf-brand); color: var(--rf-brand); }
.rf-iconbtn:disabled { opacity: .4; cursor: default; }
.rf-textlink { color: var(--rf-brand); font-weight: 700; font-size: 12.5px; cursor: pointer; text-decoration: none; white-space: nowrap; }
.rf-textlink:hover { text-decoration: underline; color: var(--rf-brand-dk); }

/* banner */
.rf-banner { display: flex; gap: 12px; align-items: flex-start; background: var(--rf-warn-bg); color: var(--rf-warn);
	border-radius: 10px; padding: 12px 16px; margin-bottom: 20px; font-size: 13px; }
.rf-banner .fa { margin-top: 3px; }
.rf-banner .rf-textlink { color: var(--rf-warn); margin-left: 6px; }

/* KPIs */
.rf-kpis { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 28px; }
.rf-kpi-group { background: var(--rf-surface); border: 1px solid var(--rf-line); border-radius: 14px; padding: 18px 20px 16px; }
.rf-kpi-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px;
	font-size: 11px; letter-spacing: .12em; text-transform: uppercase; font-weight: 700; color: var(--rf-ink-3); }
.rf-kpi-head .rf-textlink { text-transform: none; letter-spacing: 0; font-size: 12px; }
.rf-kpi-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.rf-kpi b { display: block; font-size: 26px; font-weight: 800; line-height: 1.15; color: var(--rf-ink); font-variant-numeric: tabular-nums; }
.rf-kpi span { font-size: 12.5px; color: var(--rf-ink-2); }
.rf-kpi.alert b { color: var(--rf-brand); }
.rf-meter { margin-top: 16px; }
.rf-meter-bar { height: 6px; background: var(--rf-line-2); border-radius: 999px; overflow: hidden; }
.rf-meter-fill { height: 100%; width: 0; background: var(--rf-brand); border-radius: 999px; transition: width .6s ease; }
.rf-meter-foot { display: flex; justify-content: space-between; gap: 10px; margin-top: 7px; font-size: 12px; color: var(--rf-ink-3); }
.rf-meter-foot b { color: var(--rf-ink-2); font-weight: 700; }

/* tabs */
.rf-tabs { display: inline-flex; gap: 4px; padding: 4px; background: var(--rf-surface); border: 1px solid var(--rf-line);
	border-radius: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.rf-tab { border: 0; background: transparent; padding: 8px 16px; border-radius: 9px; font-size: 13px; font-weight: 700;
	color: var(--rf-ink-2); cursor: pointer; display: inline-flex; align-items: center; gap: 8px; transition: background .15s, color .15s; }
.rf-tab:hover { color: var(--rf-brand); background: var(--rf-brand-50); }
.rf-tab.active { background: var(--rf-brand); color: #fff; }
.rf-count { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 999px; background: var(--rf-brand-100); color: var(--rf-brand); font-variant-numeric: tabular-nums; }
.rf-tab.active .rf-count { background: rgba(255,255,255,.22); color: #fff; }

/* panels */
.rf-panel { display: none; background: var(--rf-surface); border: 1px solid var(--rf-line); border-radius: 14px; padding: 22px 22px 18px; }
.rf-panel.active { display: block; }
.rf-panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }
.rf-panel-head h2 { font-size: 18px; font-weight: 800; }
.rf-panel-head p { margin: 4px 0 0; color: var(--rf-ink-2); font-weight: 300; max-width: 640px; }
.rf-actions { display: flex; gap: 8px; flex-wrap: wrap; }

/* toolbar */
.rf-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.rf-searchbox { position: relative; flex: 1; max-width: 360px; min-width: 200px; margin: 0; }
.rf-searchbox .fa { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--rf-ink-3); font-size: 12px; }
.rf-search { width: 100%; padding: 8px 12px 8px 34px; border: 1px solid var(--rf-line); border-radius: 9px; font-size: 13px;
	background: var(--rf-canvas); color: var(--rf-ink); outline: none; transition: border-color .15s, box-shadow .15s, background .15s; }
.rf-search:focus { border-color: var(--rf-brand); background: var(--rf-surface); box-shadow: 0 0 0 3px var(--rf-brand-100); }
.rf-pager { display: flex; align-items: center; gap: 6px; }
.rf-page-info { font-size: 12.5px; color: var(--rf-ink-3); margin-right: 6px; font-variant-numeric: tabular-nums; }

/* table */
.rf-tablebox { border: 1px solid var(--rf-line); border-radius: 10px; overflow: auto; max-height: 560px; }
.rf-tablebox-sm { max-height: 420px; }
.rf-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; margin: 0; }
.rf-table thead th { position: sticky; top: 0; z-index: 1; background: var(--rf-canvas); color: var(--rf-ink-3);
	font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; text-align: left;
	padding: 10px 14px; border-bottom: 1px solid var(--rf-line); white-space: nowrap; }
.rf-table th.sortable { cursor: pointer; user-select: none; }
.rf-table th.sortable:hover { color: var(--rf-brand); }
.rf-table th.asc::after { content: "↑"; margin-left: 5px; color: var(--rf-brand); }
.rf-table th.desc::after { content: "↓"; margin-left: 5px; color: var(--rf-brand); }
.rf-table td { padding: 11px 14px; border-bottom: 1px solid var(--rf-line-2); vertical-align: middle; color: var(--rf-ink); }
.rf-table tbody tr:last-child td { border-bottom: 0; }
.rf-table tbody tr:hover td { background: var(--rf-brand-50); }
.rf-table .num { text-align: right; }
.rf-table .act { text-align: right; width: 1%; white-space: nowrap; }
.rf-table tr.rf-empty td { text-align: center; padding: 40px 16px; color: var(--rf-ink-3); }
.rf-table tr.rf-flash td { animation: rf-flash 3s ease-out; }
@keyframes rf-flash { from { background: #FFE9A8; } to { background: transparent; } }

/* inline bits */
.rf-uid { font-family: var(--rf-mono); font-size: 12px; font-weight: 600; color: var(--rf-ink); background: var(--rf-line-2);
	border: 1px solid var(--rf-line); padding: 2px 8px; border-radius: 6px; white-space: nowrap; }
.rf-sid { font-family: var(--rf-mono); font-size: 12px; font-weight: 700; color: var(--rf-brand); background: var(--rf-brand-50);
	border: 1px solid var(--rf-brand-100); padding: 2px 8px; border-radius: 6px; white-space: nowrap; }
.rf-sid.none { color: var(--rf-ink-3); background: var(--rf-line-2); border-color: var(--rf-line); font-family: var(--rf-serif); font-weight: 400; }
.rf-chip { font-size: 12px; font-weight: 700; color: var(--rf-ink-2); background: var(--rf-line-2); padding: 3px 10px; border-radius: 999px; white-space: nowrap; }
.rf-num { font-variant-numeric: tabular-nums; font-weight: 700; }
.rf-dim { color: var(--rf-ink-3); }
.rf-link { color: var(--rf-ink); font-weight: 700; text-decoration: none; }
.rf-link:hover { color: var(--rf-brand); text-decoration: underline; }
.rf-when { display: inline-flex; flex-direction: column; line-height: 1.3; white-space: nowrap; font-variant-numeric: tabular-nums; }
.rf-when small { color: var(--rf-ink-3); font-size: 11.5px; }
.rf-unknown { color: var(--rf-brand); font-weight: 700; font-size: 12.5px; }
.rf-tag { display: inline-block; font-size: 11.5px; font-weight: 700; padding: 2px 10px; border-radius: 999px; white-space: nowrap; }
.rf-tag.ok { color: var(--rf-ok); background: var(--rf-ok-bg); }
.rf-tag.warn { color: var(--rf-warn); background: var(--rf-warn-bg); }
.rf-tag.info { color: var(--rf-info); background: var(--rf-info-bg); }
.rf-tag.err { color: var(--rf-err); background: var(--rf-err-bg); }
.rf-allgood { color: var(--rf-ok); font-weight: 700; }
.rf-allgood .fa { display: block; font-size: 28px; margin-bottom: 8px; }

/* assign dialog */
.rf-card-hero { display: flex; align-items: center; gap: 16px; padding: 16px 18px; border-radius: 12px;
	background: linear-gradient(135deg, #920C24, #5A0716); color: #fff; margin-bottom: 4px; }
.rf-card-hero .rf-eyebrow { color: rgba(255,255,255,.75); margin-bottom: 2px; }
.rf-card-chip { width: 44px; height: 44px; border-radius: 10px; background: rgba(255,255,255,.15); display: flex; align-items: center; justify-content: center; font-size: 20px; }
.rf-card-uid { font-family: var(--rf-mono); font-size: 22px; font-weight: 700; letter-spacing: .02em; }
.rf-pick { display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow: auto; padding: 2px; }
.rf-pick-row { display: flex; align-items: center; gap: 12px; width: 100%; text-align: left; padding: 10px 12px; border-radius: 10px;
	border: 1px solid var(--rf-line); background: var(--rf-surface); cursor: pointer; transition: border-color .15s, background .15s; }
.rf-pick-row:hover { border-color: var(--rf-brand-100); background: var(--rf-brand-50); }
.rf-pick-row.on { border-color: var(--rf-brand); background: var(--rf-brand-50); box-shadow: 0 0 0 2px var(--rf-brand-100); }
.rf-pick-main { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.rf-pick-name { font-weight: 700; color: var(--rf-ink); }
.rf-pick-meta { font-size: 12px; color: var(--rf-ink-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rf-pick-tick { color: var(--rf-brand); font-size: 18px; opacity: 0; transition: opacity .15s; }
.rf-pick-row.on .rf-pick-tick { opacity: 1; }
.rf-pick-empty { padding: 20px; text-align: center; color: var(--rf-ink-3); border: 1px dashed var(--rf-line); border-radius: 10px; }

/* import dialog */
.rf-steps { list-style: none; counter-reset: s; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; padding: 0; margin: 0 0 14px; }
.rf-steps li { counter-increment: s; background: var(--rf-canvas); border: 1px solid var(--rf-line); border-radius: 10px; padding: 12px 14px 12px 46px; position: relative; font-size: 13px; }
.rf-steps li::before { content: counter(s); position: absolute; left: 14px; top: 12px; width: 22px; height: 22px; border-radius: 50%;
	background: var(--rf-brand); color: #fff; font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.rf-steps b { display: block; color: var(--rf-ink); }
.rf-steps span { color: var(--rf-ink-3); font-size: 12px; }
.rf-cols { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; color: var(--rf-ink-2); margin-bottom: 6px; }
.rf-cols-note { color: var(--rf-ink-3); font-size: 12px; }
.rf-cols .rf-textlink { margin-left: auto; }
.rf-sums { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 14px; }
.rf-sum { border-radius: 10px; padding: 12px 14px; border: 1px solid var(--rf-line); }
.rf-sum b { display: block; font-size: 24px; font-weight: 800; font-variant-numeric: tabular-nums; }
.rf-sum span { font-size: 12.5px; color: var(--rf-ink-2); }
.rf-sum.ok b { color: var(--rf-ok); } .rf-sum.err b { color: var(--rf-err); } .rf-sum.info b { color: var(--rf-info); }
.rf-note { color: var(--rf-ink-2); font-size: 12.5px; }

@media (max-width: 1100px) { .rf-kpis { grid-template-columns: 1fr; } }
@media (max-width: 720px) {
	.rfid-wrap { padding: 18px 14px 32px; }
	.rf-title { font-size: 22px; }
	.rf-kpi b { font-size: 21px; }
	.rf-steps, .rf-sums { grid-template-columns: 1fr; }
	.rf-searchbox { max-width: none; }
}`;
}
