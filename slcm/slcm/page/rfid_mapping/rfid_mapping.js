// Copyright (c) 2026, Nishanth and contributors
// RFID Card Management — NLS theme (#920C24 + Merriweather), British spelling

frappe.pages["rfid-mapping"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: "RFID Card Management",
		single_column: true,
	});
	if (!document.getElementById("er-theme-font")) {
		$("head").append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}

	wrapper._rfid = {
		live_interval:      null,
		countdown_interval: null,
		countdown_val:      30,
		last_swipe_time:    null,
		unassigned_dt:      null,
		linked_dt:          null,
		feed_dt:            null,
	};

	$(build_html()).appendTo($(wrapper).find(".page-content, .layout-main-section").first());
	bind_events(wrapper);
	full_load(wrapper);

	wrapper._rfid.live_interval      = setInterval(() => live_refresh(wrapper), 30000);
	wrapper._rfid.countdown_interval = setInterval(() => tick(wrapper), 1000);
};

frappe.pages["rfid-mapping"].on_page_show = function (wrapper) {
	if (!wrapper._rfid) return;
	if (!wrapper._rfid.live_interval) {
		wrapper._rfid.countdown_val      = 30;
		wrapper._rfid.live_interval      = setInterval(() => live_refresh(wrapper), 30000);
		wrapper._rfid.countdown_interval = setInterval(() => tick(wrapper), 1000);
	}
	// Always reset display countdown on page show
	$(wrapper).find("#next-refresh").text(wrapper._rfid.countdown_val || 30);
};

frappe.pages["rfid-mapping"].on_page_hide = function (wrapper) {
	if (!wrapper._rfid) return;
	clearInterval(wrapper._rfid.live_interval);
	clearInterval(wrapper._rfid.countdown_interval);
	wrapper._rfid.live_interval      = null;
	wrapper._rfid.countdown_interval = null;
};

// ─────────────────────────────────────────────────────────────────
// Data loading
// ─────────────────────────────────────────────────────────────────
function full_load(wrapper) {
	set_dot(wrapper, "syncing");
	frappe.call({
		method: "slcm.slcm.page.rfid_mapping.rfid_mapping.get_rfid_summary",
		callback(r) {
			if (!r.message) return;
			const d = r.message;
			render_stats(wrapper, d.stats, d.student_stats);
			render_unassigned(wrapper, d.unlinked_cards);
			render_student_cards(wrapper, d.linked_students);
			render_feed(wrapper, d.recent_logs, true);
			wrapper._rfid.last_swipe_time = d.stats.last_swipe || null;
			set_dot(wrapper, "live");
			wrapper._rfid.countdown_val = 30;
		},
	});
}

function live_refresh(wrapper) {
	set_dot(wrapper, "syncing");
	frappe.call({
		method: "slcm.slcm.page.rfid_mapping.rfid_mapping.get_live_feed",
		args: { since_swipe_time: wrapper._rfid.last_swipe_time || "" },
		callback(r) {
			if (!r.message) return;
			const d = r.message;
			render_stats(wrapper, d.stats, null);
			if (d.new_logs && d.new_logs.length) {
				wrapper._rfid.feed_dt.prepend(d.new_logs);
				wrapper._rfid.last_swipe_time = d.stats.last_swipe;
				frappe.show_alert({ message: `${d.new_logs.length} new swipe(s)`, indicator: "green" }, 4);
			}
			set_dot(wrapper, "live");
			wrapper._rfid.countdown_val = 30;
		},
	});
}

// ─────────────────────────────────────────────────────────────────
// Stats
// ─────────────────────────────────────────────────────────────────
function render_stats(wrapper, s, ss) {
	const $w = $(wrapper);
	$w.find("#st-total").text(fmt(s.total_logs));
	$w.find("#st-linked").text(fmt(s.linked_logs));
	$w.find("#st-unlinked").text(fmt(s.unlinked_logs));

	if (ss) {
		$w.find("#st-students").text(fmt(ss.total_students));
		$w.find("#st-with-card").text(fmt(ss.students_with_rfid));
		$w.find("#st-no-card").text(fmt(ss.students_without_rfid));
	}

	// Update tab badges independently
	const u = parseInt(s.unlinked_logs) || 0;
	$w.find("#count-unassigned").text(u).toggle(u > 0);
	const l = parseInt(s.linked_logs) || 0;
	$w.find("#count-linked").text(l).toggle(l > 0);
}

// ─────────────────────────────────────────────────────────────────
// Tab switching
// ─────────────────────────────────────────────────────────────────
function bind_events(wrapper) {
	const $w = $(wrapper);

	$w.on("click", ".r-tab", function () {
		$w.find(".r-tab").removeClass("r-tab-active");
		$(this).addClass("r-tab-active");
		$w.find(".r-panel").hide();
		$w.find("#panel-" + $(this).data("tab")).show();
	});

	$w.on("click", ".btn-assign",        function () { show_assign_dialog($(this).data("uid"), wrapper); });
	$w.on("click", "#btn-export-vendor", () => do_export(wrapper));
	$w.on("click", "#btn-bulk-import",   () => show_import_dialog(wrapper));
	$w.on("click", "#btn-refresh-now",   () => refresh_now(wrapper));
}

// ─────────────────────────────────────────────────────────────────
// Manual "Refresh Now" — force an immediate SQL Server pull
// ─────────────────────────────────────────────────────────────────
function refresh_now(wrapper) {
	const $btn = $(wrapper).find("#btn-refresh-now");
	$btn.prop("disabled", true).find(".btn-refresh-label").text("Refreshing…");
	set_dot(wrapper, "syncing");

	frappe.call({
		method: "slcm.slcm.utils.rfid_sql_poller.poll_now",
		callback(r) {
			$btn.prop("disabled", false).find(".btn-refresh-label").text("Refresh Now");
			if (r.message && r.message.success) {
				frappe.show_alert({ message: r.message.message, indicator: "green" }, 5);
			} else {
				frappe.msgprint({
					title: "Refresh Failed",
					message: r.message ? r.message.message : "Unknown error.",
					indicator: "red",
				});
			}
			full_load(wrapper);
		},
		error() {
			$btn.prop("disabled", false).find(".btn-refresh-label").text("Refresh Now");
			set_dot(wrapper, "live");
		},
	});
}

// ─────────────────────────────────────────────────────────────────
// Generic lightweight DataTable
// ─────────────────────────────────────────────────────────────────
function make_datatable(config) {
	const {
		wrapper,
		data: initial_data,
		columns,
		page_size = 25,
		empty_msg = "No records found.",
		on_action,
	} = config;

	let _data        = initial_data ? initial_data.slice() : [];
	let _filtered    = _data.slice();
	let _sort_col    = null;
	let _sort_dir    = "asc";   // "asc" or "desc"
	let _page        = 0;       // 0-indexed current page
	let _query       = "";

	// ── DOM refs ──
	const $toolbar   = wrapper.find(".dt-toolbar");
	const $search    = wrapper.find(".dt-search");
	const $page_info = wrapper.find(".dt-page-info");
	const $btn_prev  = wrapper.find(".dt-btn-prev");
	const $btn_next  = wrapper.find(".dt-btn-next");
	const $tbody     = wrapper.find("tbody");
	const $thead     = wrapper.find("thead tr");

	// ── Wire up column headers ──
	$thead.find("th").each(function (i) {
		const col = columns[i];
		if (!col || col.sortable === false) return;
		$(this).addClass("th-sort").on("click", function () {
			if (_sort_col === i) {
				_sort_dir = _sort_dir === "asc" ? "desc" : "asc";
			} else {
				_sort_col = i;
				_sort_dir = "asc";
			}
			_page = 0;
			_apply_sort();
			_render();
		});
	});

	// ── Wire up search ──
	$search.on("input", function () {
		_query = $(this).val().toLowerCase();
		_page  = 0;
		_apply_filter();
		_render();
	});

	// ── Wire up pagination ──
	$btn_prev.on("click", function () {
		if (_page > 0) { _page--; _render(); }
	});
	$btn_next.on("click", function () {
		const max_page = Math.max(0, Math.ceil(_filtered.length / page_size) - 1);
		if (_page < max_page) { _page++; _render(); }
	});

	// ── Internal: apply text filter ──
	function _apply_filter() {
		if (!_query) {
			_filtered = _data.slice();
		} else {
			_filtered = _data.filter(row => {
				return columns.some(col => {
					if (col.searchable === false) return false;
					const val = row[col.key];
					return val && String(val).toLowerCase().indexOf(_query) !== -1;
				});
			});
		}
		_apply_sort_in_place();
	}

	// ── Internal: sort _filtered in place ──
	function _apply_sort_in_place() {
		if (_sort_col === null) return;
		const col = columns[_sort_col];
		if (!col || col.sortable === false) return;
		const key = col.sort_key || col.key;
		_filtered.sort((a, b) => {
			const av = a[key] == null ? "" : a[key];
			const bv = b[key] == null ? "" : b[key];
			let cmp;
			if (typeof av === "number" && typeof bv === "number") {
				cmp = av - bv;
			} else {
				cmp = String(av).localeCompare(String(bv));
			}
			return _sort_dir === "asc" ? cmp : -cmp;
		});
	}

	// ── Internal: apply sort then re-filter ──
	function _apply_sort() {
		_apply_sort_in_place();
	}

	// ── Internal: render current page ──
	function _render() {
		// Update sort indicators on headers
		$thead.find("th").each(function (i) {
			$(this).removeClass("asc desc");
			if (i === _sort_col) {
				$(this).addClass(_sort_dir);
			}
		});

		const total  = _filtered.length;
		const start  = _page * page_size;
		const end    = Math.min(start + page_size, total);
		const page_rows = _filtered.slice(start, end);

		// Update pagination info
		if (total === 0) {
			$page_info.text("No results");
		} else {
			$page_info.text(`Showing ${start + 1}–${end} of ${total}`);
		}

		const max_page = Math.max(0, Math.ceil(total / page_size) - 1);
		$btn_prev.prop("disabled", _page === 0);
		$btn_next.prop("disabled", _page >= max_page);

		// Render rows
		$tbody.empty();
		if (!page_rows.length) {
			const colspan = columns.length;
			$tbody.append(`<tr><td colspan="${colspan}">${empty_msg}</td></tr>`);
			return;
		}

		page_rows.forEach(row => {
			const cells = columns.map(col => {
				const html = col.render ? col.render(row) : esc(row[col.key] != null ? row[col.key] : "—");
				return `<td>${html}</td>`;
			}).join("");
			$tbody.append(`<tr>${cells}</tr>`);
		});

		// Re-bind action buttons (on_action callback)
		if (on_action) {
			$tbody.find("[data-action]").on("click", function () {
				const $el  = $(this);
				const action = $el.data("action");
				const key_val = $el.data("row-key");
				const row = _filtered.find(r => String(r[config.row_key || "_key"]) === String(key_val)) || null;
				on_action(action, row, $el);
			});
		}
	}

	// ── Public API ──
	function refresh(new_data) {
		_data     = new_data ? new_data.slice() : [];
		_page     = 0;
		_apply_filter();
		_render();
	}

	function prepend(rows) {
		if (!rows || !rows.length) return;

		// Dedup by rfid_uid|swipe_time key
		const existing_keys = new Set(
			_data.map(r => (r.rfid_uid || "") + "|" + (r.swipe_time || r.swipe_time || ""))
		);

		const new_rows = rows.filter(r => {
			const k = (r.rfid_uid || "") + "|" + (r.swipe_time || "");
			if (existing_keys.has(k)) return false;
			existing_keys.add(k);
			return true;
		});

		if (!new_rows.length) return;

		_data = new_rows.concat(_data);
		// Trim to 200 max
		if (_data.length > 200) _data = _data.slice(0, 200);

		_apply_filter();
		_render();

		// Gold flash on newly prepended rows (first N rows in tbody)
		const flash_count = Math.min(new_rows.length, page_size);
		$tbody.find("tr").slice(0, flash_count).each(function () {
			const $tds = $(this).find("td");
			$tds.css({ background: "#d0d4e8", transition: "" });
			setTimeout(() => $tds.css({ background: "", transition: "background 3s" }), 100);
			setTimeout(() => $tds.css("background", ""), 3100);
		});
	}

	// Initial render (with default sort if set by config)
	if (config.default_sort_col !== undefined) {
		_sort_col = config.default_sort_col;
		_sort_dir = config.default_sort_dir || "desc";
		_apply_sort_in_place();
	}
	_render();

	return { refresh, prepend };
}

// ─────────────────────────────────────────────────────────────────
// TAB 1 — Unassigned Cards
// ─────────────────────────────────────────────────────────────────
function render_unassigned(wrapper, cards) {
	const $w = $(wrapper);
	const uCount = cards ? cards.length : 0;
	$w.find("#count-unassigned").text(uCount).toggle(uCount > 0);

	const columns = [
		{
			key: "rfid_uid", label: "RFID UID (emp_code)",
			sortable: true, searchable: true,
			render: row => `<code class="uid">${esc(row.rfid_uid)}</code>`,
		},
		{
			key: "swipe_count", label: "Total Swipes",
			sortable: true, searchable: false,
			render: row => `<span class="pill-count">${row.swipe_count || 0}</span>`,
		},
		{
			key: "terminal_id", label: "Terminal ID",
			sortable: true, searchable: true,
			render: row => `<span class="muted tc">${esc(row.terminal_id || "—")}</span>`,
		},
		{
			key: "terminal", label: "Terminal / Room",
			sortable: true, searchable: true,
			render: row => `<span class="pill-room">${esc(row.terminal || "—")}</span>`,
		},
		{
			key: "area", label: "Area",
			sortable: true, searchable: true,
			render: row => `<span class="muted">${esc(row.area || "—")}</span>`,
		},
		{
			key: "last_seen", label: "Last Punch Time",
			sort_key: "last_seen",
			sortable: true, searchable: false,
			render: row => `<span class="muted">${row.last_seen ? frappe.datetime.str_to_user(row.last_seen) : "—"}</span>`,
		},
		{
			key: "_action", label: "Action",
			sortable: false, searchable: false,
			render: row => `<button class="btn-assign" data-uid="${esc(row.rfid_uid)}">
				<i class="fa fa-link"></i> Assign Student
			</button>`,
		},
	];

	const empty_html = !cards || !cards.length
		? `<div class="all-ok"><i class="fa fa-check-circle"></i>All RFID cards are assigned to students.</div>`
		: `<div class="tc muted" style="padding:32px">No matching records.</div>`;

	wrapper._rfid.unassigned_dt = make_datatable({
		wrapper:   $w.find("#panel-unassigned"),
		data:      cards || [],
		columns,
		page_size: 25,
		empty_msg: `<div class="tc muted" style="padding:32px">${!cards || !cards.length ? "All RFID cards are assigned to students." : "No matching records."}</div>`,
	});
}

// ─────────────────────────────────────────────────────────────────
// TAB 2 — Student Cards
// ─────────────────────────────────────────────────────────────────
function render_student_cards(wrapper, students) {
	const $w = $(wrapper);
	const lCount = students ? students.length : 0;
	$w.find("#count-linked").text(lCount).toggle(lCount > 0);

	const columns = [
		{
			key: "student_name", label: "Student",
			sortable: true, searchable: true,
			render: row => `<a class="stud-link" href="/app/student-master/${esc(row.student_id)}" target="_blank">
				${esc(row.student_name || row.student_id)}
			</a>
			<div class="sub-id">${esc(row.student_id)}</div>`,
		},
		{
			key: "rfid_uid", label: "RFID UID",
			sortable: true, searchable: true,
			render: row => `<code class="uid">${esc(row.rfid_uid)}</code>`,
		},
		{
			key: "programme", label: "Programme",
			sortable: true, searchable: true,
			render: row => esc(row.programme || "—"),
		},
		{
			key: "batch_year", label: "Batch",
			sortable: true, searchable: false,
			render: row => esc(row.batch_year || "—"),
		},
		{
			key: "department", label: "Department",
			sortable: true, searchable: true,
			render: row => esc(row.department || "—"),
		},
		{
			key: "total_swipes", label: "Total Swipes",
			sortable: true, searchable: false,
			render: row => `<span class="pill-count">${row.total_swipes || 0}</span>`,
		},
		{
			key: "last_swipe", label: "Last Punch Time",
			sort_key: "last_swipe",
			sortable: true, searchable: false,
			render: row => `<span class="muted">${row.last_swipe ? frappe.datetime.str_to_user(row.last_swipe) : "Never"}</span>`,
		},
	];

	wrapper._rfid.linked_dt = make_datatable({
		wrapper:   $w.find("#panel-linked"),
		data:      students || [],
		columns,
		page_size: 25,
		empty_msg: `<div class="tc muted" style="padding:32px">No students have cards assigned yet.</div>`,
	});
}

// ─────────────────────────────────────────────────────────────────
// TAB 3 — Live Punch Feed
// ─────────────────────────────────────────────────────────────────
function render_feed(wrapper, logs, clear) {
	const $w = $(wrapper);

	// If already initialised and not a full clear, just add rows
	if (wrapper._rfid.feed_dt && !clear) {
		wrapper._rfid.feed_dt.prepend(logs || []);
		return;
	}

	const columns = [
		{
			key: "rfid_uid", label: "RFID UID (emp_code)",
			sortable: false, searchable: true,
			render: row => `<code class="uid">${esc(row.rfid_uid)}</code>`,
		},
		{
			key: "student_name", label: "Student",
			sortable: false, searchable: true,
			render: row => row.student
				? `<a class="stud-link" href="/app/student-master/${esc(row.student)}" target="_blank">
					<i class="fa fa-user-circle"></i> ${esc(row.student_name || row.student)}</a>`
				: `<span class="unknown-lbl"><i class="fa fa-question-circle"></i> Unknown — assign card</span>`,
		},
		{
			key: "device_id", label: "Terminal ID",
			sortable: false, searchable: true,
			render: row => `<span class="muted tc">${esc(row.device_id || "—")}</span>`,
		},
		{
			key: "terminal_alias", label: "Terminal / Room",
			sortable: false, searchable: true,
			render: row => `<span class="pill-room">${esc(row.terminal_alias || "—")}</span>`,
		},
		{
			key: "area_alias", label: "Area",
			sortable: false, searchable: true,
			render: row => `<span class="muted">${esc(row.area_alias || "—")}</span>`,
		},
		{
			key: "swipe_time", label: "Punch Time",
			sort_key: "swipe_time",
			sortable: true, searchable: false,
			render: row => `<span class="muted">${row.swipe_time ? frappe.datetime.str_to_user(row.swipe_time) : "—"}</span>`,
		},
		{
			key: "processed", label: "Status",
			sortable: false, searchable: false,
			render: row => row.processed
				? `<span class="pill-done">Processed</span>`
				: `<span class="pill-pend">Pending</span>`,
		},
	];

	wrapper._rfid.feed_dt = make_datatable({
		wrapper:          $w.find("#panel-feed"),
		data:             logs || [],
		columns,
		page_size:        25,
		empty_msg:        `<div class="tc muted" style="padding:32px">No swipes yet.</div>`,
		default_sort_col: 5,   // Punch Time column index
		default_sort_dir: "desc",
	});
}

// Legacy wrapper kept so nothing else breaks — now delegates to feed_dt
function prepend_feed(wrapper, logs) {
	if (wrapper._rfid && wrapper._rfid.feed_dt) {
		wrapper._rfid.feed_dt.prepend(logs);
	}
}

// ─────────────────────────────────────────────────────────────────
// Assign Student dialog
// ─────────────────────────────────────────────────────────────────
function show_assign_dialog(rfid_uid, wrapper) {
	const d = new frappe.ui.Dialog({
		title: "Assign Student to RFID Card",
		fields: [
			{
				fieldname: "uid_html", fieldtype: "HTML",
				options: `<div class="dlg-uid-box">
					<div class="dlg-lbl">RFID UID (programmed on card by vendor)</div>
					<div class="dlg-val">${esc(rfid_uid)}</div>
					<div class="dlg-hint">This value is read directly from the physical RFID terminal.</div>
				</div>`,
			},
			{ fieldname: "sb", fieldtype: "Section Break",
			  label: "Which student owns this card?" },
			{
				fieldname: "student", fieldtype: "Link",
				label: "Student", options: "Student Master", reqd: 1,
				get_query: () => ({ filters: [["rfid_uid", "is", "not set"]] }),
				description: "Only students without a card assigned are shown.",
			},
		],
		primary_action_label: "Assign and Save",
		primary_action(val) {
			frappe.call({
				method: "slcm.slcm.page.rfid_mapping.rfid_mapping.link_rfid_to_student",
				args: { rfid_uid, student: val.student },
				freeze: true, freeze_message: "Saving...",
				callback(r) {
					if (r.message && r.message.success) {
						frappe.show_alert({ message: r.message.message, indicator: "green" }, 6);
						d.hide();
						full_load(wrapper);
					} else {
						frappe.msgprint({
							message: r.message ? r.message.message : "Failed.",
							indicator: "red",
						});
					}
				},
			});
		},
	});
	d.show();
}

// ─────────────────────────────────────────────────────────────────
// Export for vendor
// ─────────────────────────────────────────────────────────────────
function do_export(wrapper) {
	frappe.call({
		method: "slcm.slcm.page.rfid_mapping.rfid_mapping.get_export_data",
		callback(r) {
			if (!r.message || !r.message.length) {
				frappe.msgprint("All students already have cards assigned."); return;
			}
			const rows    = r.message;
			const headers = ["student_id", "student_name", "programme",
			                 "batch_year", "department", "email", "rfid_uid"];
			let csv = headers.join(",") + "\n";
			rows.forEach(row => {
				csv += headers.map(h => `"${String(row[h] || "").replace(/"/g, '""')}"`).join(",") + "\n";
			});
			dl_file(csv, "rfid_student_list.csv", "text/csv");
			frappe.show_alert({ message: `Exported ${rows.length} student(s) for vendor`, indicator: "blue" }, 5);
		},
	});
}

// ─────────────────────────────────────────────────────────────────
// Bulk Import dialog — file upload + paste
// ─────────────────────────────────────────────────────────────────
function show_import_dialog(wrapper) {
	const d = new frappe.ui.Dialog({
		title: "Bulk Import RFID Assignments",
		fields: [
			{
				fieldname: "how_html", fieldtype: "HTML",
				options: `<div class="import-info">
					<div class="import-title">How to use</div>
					<ol class="import-steps">
						<li>Click <strong>Export for Vendor</strong> — downloads a CSV with all student IDs and names.</li>
						<li>Send the CSV to the vendor. They fill the <code>rfid_uid</code> column for each student.</li>
						<li>Upload the completed CSV or Excel (.xlsx) here, or paste it below.</li>
					</ol>
					<div style="margin-top:10px">
						<strong>Required columns:</strong>
						<code class="uid" style="margin-left:6px">student_id</code>
						<code class="uid" style="margin-left:6px">rfid_uid</code>
						&nbsp;·&nbsp; Accepts <strong>.csv</strong> or <strong>.xlsx</strong>
					</div>
					<button class="btn-outline" id="dl-template" style="margin-top:12px; font-size:.8rem; padding:5px 12px">
						<i class="fa fa-download"></i> Download Sample Template
					</button>
				</div>`,
			},
			{ fieldname: "sb1", fieldtype: "Section Break", label: "Upload CSV File" },
			{
				fieldname: "file_upload", fieldtype: "Attach",
				label: "Choose File",
				description: "Upload the CSV or Excel (.xlsx) file returned by the vendor.",
			},
			{ fieldname: "sb2", fieldtype: "Section Break",
			  label: "— or Paste CSV Content Directly —" },
			{
				fieldname: "csv_paste", fieldtype: "Code",
				label: "Paste CSV here", options: "None",
				description: "Format: student_id,rfid_uid — one row per student.",
			},
		],
		primary_action_label: "Import",
		primary_action(val) {
			const pasted = (val.csv_paste || "").trim();
			if (val.file_upload) {
				// Read file content server-side to handle both private and public files
				frappe.call({
					method: "slcm.slcm.page.rfid_mapping.rfid_mapping.read_uploaded_file",
					args: { file_url: val.file_upload },
					callback(fr) {
						if (fr.message && fr.message.success) {
							run_import(fr.message.content, d, wrapper);
						} else {
							frappe.msgprint(fr.message ? fr.message.error : "Failed to read uploaded file.");
						}
					},
				});
			} else if (pasted) {
				run_import(pasted, d, wrapper);
			} else {
				frappe.msgprint("Please upload a CSV file or paste CSV content.");
			}
		},
	});

	d.show();
	setTimeout(() => {
		d.$wrapper.find("#dl-template").on("click", () => {
			const csv = "student_id,rfid_uid\nSTUD-2026-00001,B23012\nSTUD-2026-00002,LLB/2699/2020\n";
			dl_file(csv, "rfid_import_template.csv", "text/csv");
		});
	}, 300);
}

function run_import(csv_text, dialog, wrapper) {
	frappe.call({
		method: "slcm.slcm.page.rfid_mapping.rfid_mapping.bulk_import_rfid",
		args: { csv_data: csv_text },
		freeze: true, freeze_message: "Importing...",
		callback(r) {
			dialog.hide();
			if (!r.message) return;
			const res = r.message;
			let html = `<p style="font-size:1rem; margin-bottom:12px">${res.message}</p>`;

			if (res.results.linked.length) {
				html += `<p class="result-ok"><i class="fa fa-check-circle"></i> Linked (${res.results.linked.length})</p><ul>`;
				res.results.linked.forEach(row =>
					html += `<li>${esc(row.student_name)} &mdash; <code>${esc(row.rfid_uid)}</code></li>`);
				html += "</ul>";
			}
			if (res.results.skipped.length) {
				html += `<p class="result-skip"><i class="fa fa-minus-circle"></i> Skipped (${res.results.skipped.length})</p><ul>`;
				res.results.skipped.forEach(row =>
					html += `<li>Row ${row.row}: ${esc(row.reason)}</li>`);
				html += "</ul>";
			}
			if (res.results.errors.length) {
				html += `<p class="result-err"><i class="fa fa-times-circle"></i> Errors (${res.results.errors.length})</p><ul>`;
				res.results.errors.forEach(row =>
					html += `<li>Row ${row.row}: ${esc(row.reason)} &mdash; <code>${esc(row.rfid_uid)}</code></li>`);
				html += "</ul>";
			}
			frappe.msgprint({ title: "Import Results", message: html });
			full_load(wrapper);
		},
	});
}

// ─────────────────────────────────────────────────────────────────
// Sync dot and countdown
// ─────────────────────────────────────────────────────────────────
function set_dot(wrapper, state) {
	const $d = $(wrapper).find("#sync-dot");
	const $t = $(wrapper).find("#sync-text");
	$d.removeClass("dot-live dot-syncing");
	if (state === "live") {
		$d.addClass("dot-live");
		$t.text("Live — SQL Server syncs automatically every minute");
	} else {
		$d.addClass("dot-syncing");
		$t.text("Syncing…");
	}
}

function tick(wrapper) {
	if (!wrapper._rfid) return;
	wrapper._rfid.countdown_val = (wrapper._rfid.countdown_val || 30) - 1;
	if (wrapper._rfid.countdown_val <= 0) wrapper._rfid.countdown_val = 30;
	$(wrapper).find("#next-refresh").text(wrapper._rfid.countdown_val);
}

// ─────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────
const esc = s => frappe.utils.escape_html(String(s || ""));
const fmt = n => parseInt(n || 0).toLocaleString();
function dl_file(content, name, mime) {
	const a = document.createElement("a");
	a.href = URL.createObjectURL(new Blob([content], { type: mime }));
	a.download = name; a.click();
	URL.revokeObjectURL(a.href);
}

// ─────────────────────────────────────────────────────────────────
// HTML — NLS colours only (#920C24 scale), Merriweather
// British spelling throughout
// ─────────────────────────────────────────────────────────────────
function build_html() {
	return `
<style>
/* ── Colour tokens ── */
:root {
	--navy:   #920C24;
	--maroon: #920C24;
	--gold:   #C4566A;
	--navy-lt:#FBEEF0;
	--navy-mid:#6E091B;
	--bg:     #f8fafc;
	--white:  #ffffff;
	--border: #E8B4BE;
}

.rfid-wrap { padding:20px 24px; background:var(--bg); min-height:100vh; font-family:"Merriweather", Georgia, "Times New Roman", serif; }
.rfid-wrap button, .rfid-wrap input, .rfid-wrap select { font-family:inherit; }

/* ── Status bar ── */
.rfid-status {
	display:flex; align-items:center; gap:10px;
	padding:10px 16px; background:var(--white);
	border-left:4px solid var(--navy); border-radius:6px;
	box-shadow:0 1px 3px rgba(146,12,36,.1);
	margin-bottom:20px; font-size:.84rem; color:var(--navy);
}
.sync-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
.dot-live    { background:#28a745; box-shadow:0 0 0 3px rgba(40,167,69,.25); }
.dot-syncing { background:var(--gold); animation:blink 1s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
.cdown { margin-left:auto; font-size:.78rem; color:var(--navy-mid); }

/* ── Section label ── */
.sec-lbl {
	font-size:.68rem; font-weight:700; letter-spacing:.08em;
	color:var(--navy); text-transform:uppercase;
	border-left:3px solid var(--navy); padding-left:8px;
	margin-bottom:10px;
}

/* ── Stat cards grid ── */
.stats-grid { display:grid; gap:14px; margin-bottom:18px; }
.g4 { grid-template-columns:repeat(4,1fr); }
.g3 { grid-template-columns:repeat(3,1fr); }

.stat-card {
	background:var(--white); border-radius:8px; padding:16px 18px;
	border-top:4px solid var(--border);
	box-shadow:0 1px 4px rgba(146,12,36,.08);
}
.sc-navy   { border-top-color:var(--navy);   }
.sc-maroon { border-top-color:var(--maroon); }
.sc-gold   { border-top-color:var(--gold);   }
.sc-mid    { border-top-color:var(--navy-mid); }

.stat-num  { font-size:1.8rem; font-weight:700; line-height:1.1; margin-bottom:3px; }
.sn-navy   { color:var(--navy);   }
.sn-maroon { color:var(--maroon); }
.sn-gold   { color:var(--gold);   }
.sn-mid    { color:var(--navy-mid); }

.stat-lbl  { font-size:.78rem; color:#777; }
.stat-sub  { font-size:.7rem;  color:#bbb; margin-top:2px; }

/* ── Tabs ── */
.rfid-tabs {
	display:flex; border-bottom:3px solid var(--navy); margin-bottom:0; gap:0;
}
.r-tab {
	padding:10px 22px; border:none; background:none; cursor:pointer;
	font-size:.88rem; font-weight:500; color:var(--navy-mid);
	border-radius:6px 6px 0 0; transition:background .15s, color .15s;
}
.r-tab:hover { background:var(--navy-lt); color:var(--navy); }
.r-tab.r-tab-active { background:var(--navy); color:var(--white); font-weight:700; }
.badge-unlinked {
	display:inline-block; background:var(--maroon); color:var(--white);
	border-radius:10px; padding:1px 8px; font-size:.7rem; margin-left:5px;
	vertical-align:middle; font-weight:700;
}

/* ── Panels ── */
.r-panel {
	display:none; background:var(--white);
	border-radius:0 8px 8px 8px;
	box-shadow:0 2px 8px rgba(146,12,36,.08);
	padding:20px;
}

/* ── Panel header ── */
.panel-hdr {
	display:flex; justify-content:space-between; align-items:flex-start;
	gap:14px; flex-wrap:wrap; margin-bottom:16px;
}
.panel-title { font-size:1rem; font-weight:700; color:var(--navy); }
.panel-hint  { font-size:.82rem; color:#777; margin-top:3px; line-height:1.6; }
.panel-actions { display:flex; gap:8px; flex-shrink:0; }

/* ── Feed info box ── */
.feed-info {
	background:var(--navy-lt); border-left:4px solid var(--navy);
	border-radius:6px; padding:14px 16px; margin-bottom:16px;
	font-size:.85rem; color:#444; line-height:1.7;
}
.feed-info strong { color:var(--navy); }
.feed-info code   { background:#d8daea; padding:1px 6px; border-radius:4px;
                    color:var(--navy); font-size:.82rem; }

/* ── Tables ── */
.tbl-outer { overflow-x:auto; border:1px solid var(--border); border-radius:8px; }
.tbl-scroll { overflow-x:auto; overflow-y:auto; max-height:500px;
              border:1px solid var(--border); border-radius:8px; }

.rfid-tbl { font-size:.85rem; margin:0; width:100%; border-collapse:collapse; }
.rfid-tbl thead th {
	background:var(--navy); color:var(--white);
	font-size:.75rem; font-weight:700; text-transform:uppercase;
	letter-spacing:.05em; padding:11px 13px; white-space:nowrap; position:sticky; top:0; z-index:1;
}
.rfid-tbl tbody tr { border-bottom:1px solid #eeeef3; }
.rfid-tbl tbody tr:hover { background:var(--navy-lt); }
.rfid-tbl tbody td { padding:10px 13px; vertical-align:middle; }

/* ── Inline elements ── */
.uid {
	background:#eeeef4; color:var(--navy); padding:3px 9px;
	border-radius:4px; font-family:monospace; font-size:.82rem; font-weight:600;
}
.pill-room {
	background:var(--navy-lt); color:var(--navy);
	padding:3px 10px; border-radius:12px; font-size:.78rem; font-weight:600;
}
.pill-count {
	background:var(--navy); color:var(--white);
	padding:2px 10px; border-radius:12px; font-size:.8rem; font-weight:700;
}
.pill-done {
	background:#d4edda; color:#155724;
	padding:2px 10px; border-radius:12px; font-size:.75rem; font-weight:600;
}
.pill-pend {
	background:#fef3cd; color:#856404;
	padding:2px 10px; border-radius:12px; font-size:.75rem; font-weight:600;
}
.unknown-lbl { color:var(--maroon); font-size:.84rem; font-weight:600; }
.muted { color:#888; font-size:.82rem; }
.tc { text-align:center; }
.stud-link { color:var(--navy); font-weight:600; text-decoration:none; }
.stud-link:hover { color:var(--maroon); text-decoration:underline; }
.sub-id { font-size:.72rem; color:#aaa; }
.tbl-footer { font-size:.74rem; color:#aaa; margin-top:6px; padding:0 4px; }

/* ── Buttons ── */
.btn-navy {
	background:var(--navy); color:var(--white);
	border:none; border-radius:6px; padding:7px 14px;
	font-size:.83rem; font-weight:600; cursor:pointer;
}
.btn-navy:hover { background:var(--navy-mid); }

.btn-outline {
	background:var(--white); color:var(--navy);
	border:1.5px solid var(--navy); border-radius:6px; padding:6px 14px;
	font-size:.83rem; font-weight:600; cursor:pointer;
}
.btn-outline:hover { background:var(--navy-lt); }

.btn-assign {
	background:var(--maroon); color:var(--white);
	border:none; border-radius:6px; padding:5px 13px;
	font-size:.8rem; font-weight:600; cursor:pointer; white-space:nowrap;
}
.btn-assign:hover { background:#6E091B; }

/* ── All-assigned message ── */
.all-ok {
	text-align:center; padding:48px 20px;
	background:#f0fff4; border:2px dashed #28a745;
	border-radius:10px; color:#28a745;
	font-size:1rem; font-weight:600;
}
.all-ok i { font-size:2.2rem; display:block; margin-bottom:10px; }

/* ── Import info box ── */
.import-info { background:var(--navy-lt); border-radius:8px; padding:14px 16px; }
.import-title { font-weight:700; color:var(--navy); margin-bottom:8px; }
.import-steps { margin:0; padding-left:20px; color:#444;
                font-size:.87rem; line-height:1.9; }

/* ── Assign dialog ── */
.dlg-uid-box {
	background:var(--navy-lt); border-left:4px solid var(--navy);
	border-radius:6px; padding:14px 16px;
}
.dlg-lbl  { font-size:.72rem; font-weight:700; text-transform:uppercase;
            letter-spacing:.06em; color:var(--navy-mid); }
.dlg-val  { font-size:1.35rem; font-weight:700; font-family:monospace;
            color:var(--navy); margin:5px 0 3px; }
.dlg-hint { font-size:.78rem; color:#aaa; }

/* ── Import results ── */
.result-ok   { color:#155724; font-weight:600; margin-bottom:4px; }
.result-skip { color:var(--navy-mid); font-weight:600; margin-bottom:4px; }
.result-err  { color:var(--maroon); font-weight:600; margin-bottom:4px; }

/* ── DataTable toolbar ── */
.dt-toolbar {
	display:flex; align-items:center; justify-content:space-between;
	gap:12px; flex-wrap:wrap; margin-bottom:10px;
}
.dt-search {
	flex:1; min-width:180px; max-width:320px;
	padding:6px 12px; font-size:.84rem;
	border:1.5px solid var(--border); border-radius:6px;
	color:var(--navy); background:var(--white); outline:none;
}
.dt-search:focus { border-color:var(--navy); box-shadow:0 0 0 2px rgba(146,12,36,.12); }
.dt-search::placeholder { color:#bbb; }
.dt-pagination { display:flex; align-items:center; gap:8px; flex-shrink:0; }
.dt-page-info { font-size:.78rem; color:#888; white-space:nowrap; }
.dt-btn {
	background:var(--white); color:var(--navy);
	border:1.5px solid var(--navy); border-radius:6px;
	padding:4px 12px; font-size:.8rem; font-weight:600; cursor:pointer;
}
.dt-btn:hover:not(:disabled) { background:var(--navy-lt); }
.dt-btn:disabled { color:#bbb; border-color:#ddd; cursor:default; }

/* ── Sortable header indicators ── */
.th-sort { cursor:pointer; user-select:none; }
.th-sort:hover { background:var(--navy-mid); }
.th-sort.asc::after  { content:" ▲"; font-size:.65rem; opacity:.85; }
.th-sort.desc::after { content:" ▼"; font-size:.65rem; opacity:.85; }
</style>

<div class="rfid-wrap">

	<!-- Status bar -->
	<div class="rfid-status">
		<div class="sync-dot dot-live" id="sync-dot"></div>
		<span id="sync-text">Live — SQL Server syncs automatically every minute</span>
		<span class="cdown">Display refreshes in <strong id="next-refresh">30</strong>s</span>
		<button class="btn-outline" id="btn-refresh-now" style="margin-left:14px">
			<i class="fa fa-refresh"></i> <span class="btn-refresh-label">Refresh Now</span>
		</button>
	</div>

	<!-- Swipe log stats (matches SQL Server columns) -->
	<div class="sec-lbl">Swipe Log Statistics</div>
	<div class="stats-grid g3" style="margin-bottom:22px">
		<div class="stat-card sc-navy">
			<div class="stat-num sn-navy" id="st-total">—</div>
			<div class="stat-lbl">Total Swipes Imported</div>
			<div class="stat-sub">
				from dbo.iclock_trans_ajim &nbsp;·&nbsp;
				<a href="/app/attendance-log" target="_blank" style="color:var(--navy-mid); font-size:.72rem">
					View Log →
				</a>
			</div>
		</div>
		<div class="stat-card sc-gold">
			<div class="stat-num sn-gold" id="st-linked">—</div>
			<div class="stat-lbl">Swipes Identified</div>
			<div class="stat-sub">card matched to a known student</div>
		</div>
		<div class="stat-card sc-maroon">
			<div class="stat-num sn-maroon" id="st-unlinked">—</div>
			<div class="stat-lbl">Swipes Unidentified</div>
			<div class="stat-sub">card not yet assigned — resolve below</div>
		</div>
	</div>

	<!-- Student card stats -->
	<div class="sec-lbl">Student RFID Card Status</div>
	<div class="stats-grid g3" style="margin-bottom:28px">
		<div class="stat-card sc-navy">
			<div class="stat-num sn-navy" id="st-students">—</div>
			<div class="stat-lbl">Total Students</div>
		</div>
		<div class="stat-card sc-gold">
			<div class="stat-num sn-gold" id="st-with-card">—</div>
			<div class="stat-lbl">Cards Assigned</div>
		</div>
		<div class="stat-card sc-maroon">
			<div class="stat-num sn-maroon" id="st-no-card">—</div>
			<div class="stat-lbl">No Card Assigned Yet</div>
		</div>
	</div>

	<!-- Tabs -->
	<div class="rfid-tabs">
		<button class="r-tab r-tab-active" data-tab="unassigned">
			<i class="fa fa-id-card"></i>&nbsp;
			Unassigned Cards
			<span class="badge-unlinked" style="display:none" id="count-unassigned">0</span>
		</button>
		<button class="r-tab" data-tab="linked">
			<i class="fa fa-users"></i>&nbsp;
			Student Cards
			<span class="badge-unlinked" style="background:var(--gold); display:none" id="count-linked">0</span>
		</button>
		<button class="r-tab" data-tab="feed">
			<i class="fa fa-rss"></i>&nbsp;
			Live Punch Feed
		</button>
	</div>

	<!-- ══ TAB 1: Unassigned ══ -->
	<div class="r-panel" id="panel-unassigned" style="display:block">
		<div class="panel-hdr">
			<div>
				<div class="panel-title">Unassigned RFID Cards</div>
				<div class="panel-hint">
					These RFID UIDs are coming from the readers but no student is linked yet.<br>
					<strong>One at a time:</strong> click <em>Assign Student</em> for each card.&nbsp;
					<strong>In bulk:</strong> Export → vendor fills UIDs → Import back.
				</div>
			</div>
			<div class="panel-actions">
				<button class="btn-outline" id="btn-export-vendor">
					<i class="fa fa-download"></i> Export for Vendor
				</button>
				<button class="btn-navy" id="btn-bulk-import">
					<i class="fa fa-upload"></i> Bulk Import CSV
				</button>
			</div>
		</div>
		<div class="dt-toolbar">
			<input class="dt-search" type="search" placeholder="Search RFID UID, terminal, area…">
			<div class="dt-pagination">
				<span class="dt-page-info"></span>
				<button class="dt-btn dt-btn-prev" disabled>&#8592; Previous</button>
				<button class="dt-btn dt-btn-next" disabled>Next &#8594;</button>
			</div>
		</div>
		<div class="tbl-scroll">
			<table class="rfid-tbl">
				<thead>
					<tr>
						<th>RFID UID (emp_code)</th>
						<th class="tc">Total Swipes</th>
						<th class="tc">Terminal ID (terminal_id)</th>
						<th>Terminal / Room (terminal_alias)</th>
						<th>Area (area_alias)</th>
						<th>Last Punch Time</th>
						<th style="width:155px">Action</th>
					</tr>
				</thead>
				<tbody id="tbody-unassigned">
					<tr><td colspan="7" class="tc muted" style="padding:32px">Loading…</td></tr>
				</tbody>
			</table>
		</div>
	</div>

	<!-- ══ TAB 2: Student Cards ══ -->
	<div class="r-panel" id="panel-linked">
		<div class="panel-hdr">
			<div>
				<div class="panel-title">Student Cards Assigned</div>
				<div class="panel-hint">
					Each student below has an RFID card. Their punches are automatically
					linked to attendance records.
				</div>
			</div>
		</div>
		<div class="dt-toolbar">
			<input class="dt-search" type="search" placeholder="Search student, RFID, programme, department…">
			<div class="dt-pagination">
				<span class="dt-page-info"></span>
				<button class="dt-btn dt-btn-prev" disabled>&#8592; Previous</button>
				<button class="dt-btn dt-btn-next" disabled>Next &#8594;</button>
			</div>
		</div>
		<div class="tbl-scroll">
			<table class="rfid-tbl">
				<thead>
					<tr>
						<th>Student</th>
						<th>RFID UID (emp_code)</th>
						<th>Programme</th>
						<th>Batch</th>
						<th>Department</th>
						<th class="tc">Total Swipes</th>
						<th>Last Punch Time</th>
					</tr>
				</thead>
				<tbody id="tbody-linked">
					<tr><td colspan="7" class="tc muted" style="padding:32px">Loading…</td></tr>
				</tbody>
			</table>
		</div>
	</div>

	<!-- ══ TAB 3: Live Punch Feed ══ -->
	<div class="r-panel" id="panel-feed">
		<div class="feed-info">
			<strong>What is the Live Punch Feed?</strong><br>
			Every time a student swipes their RFID card at a classroom terminal,
			the machine logs it in the SQL Server database (<code>dbo.iclock_trans_ajim</code>)
			with the columns: <code>emp_code</code>, <code>punch_time</code>,
			<code>terminal_alias</code>, <code>area_alias</code>.<br><br>
			SLCM pulls those records every <strong>minute</strong> automatically in the background,
			or immediately if you click <strong>Refresh Now</strong> above.
			This page refreshes the display every <strong>30 seconds</strong> —
			new rows appear at the <strong>top</strong>, highlighted briefly.
			A student showing <em>Unknown</em> means that card is not yet assigned —
			go to the <strong>Unassigned Cards</strong> tab to fix it.
		</div>
		<div class="dt-toolbar">
			<input class="dt-search" type="search" placeholder="Search RFID UID, student, terminal, area…">
			<div class="dt-pagination">
				<span class="dt-page-info"></span>
				<button class="dt-btn dt-btn-prev" disabled>&#8592; Previous</button>
				<button class="dt-btn dt-btn-next" disabled>Next &#8594;</button>
			</div>
		</div>
		<div class="tbl-scroll">
			<table class="rfid-tbl">
				<thead>
					<tr>
						<th>RFID UID (emp_code)</th>
						<th>Student</th>
						<th class="tc">Terminal ID (terminal_id)</th>
						<th>Terminal / Room (terminal_alias)</th>
						<th>Area (area_alias)</th>
						<th>Punch Time</th>
						<th>Status</th>
					</tr>
				</thead>
				<tbody id="tbody-feed">
					<tr><td colspan="7" class="tc muted" style="padding:32px">Loading…</td></tr>
				</tbody>
			</table>
		</div>
		<div class="tbl-footer">
			All records are in the Attendance Log doctype. Use the search box to filter.
		</div>
	</div>

</div>`;
}
