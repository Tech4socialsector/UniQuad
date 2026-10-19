// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

const TRANSCRIPT_TYPE_DISPLAY_LABELS = {
	"Final Transcript": __("Provisional Transcript"),
};
function transcript_type_label(value) {
	return TRANSCRIPT_TYPE_DISPLAY_LABELS[value] || value;
}

frappe.pages["transcript-management-page"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Transcript Management"),
		single_column: true,
	});

	const _origWrapper = wrapper;

	// ── State ──────────────────────────────────────────────────────────────────
	const state = {
		search:         "",
		programme:      "",
		course:         "",
		academic_year:  "",
		batch:          "",
		student_status: "",
		department:     "",
		page:           1,
		page_length:    50,
		total:          0,
		sort_by:        "registration_id",
		sort_order:     "asc",
		loading:        false,
		selected:       new Set(),
		filter_options: null,
		_prog_labels:   {},
		_dept_labels:   {},
	};

	// ── Requests tab state ────────────────────────────────────────────────────
	const active_tab = { value: "students" };
	const req_state = {
		search:           "",
		status:           "",
		transcript_type:  "",
		payment_status:   "",
		page:             1,
		page_length:      50,
		total:            0,
		loading:          false,
		selected:         new Set(),
		rows:             [],
	};

	// ── Inject CSS ─────────────────────────────────────────────────────────────
	if (!document.getElementById("tm-styles")) {
		const style = document.createElement("style");
		style.id = "tm-styles";
		style.textContent = `
			@keyframes tm-spin { to { transform: rotate(360deg); } }

			/* Layout */
			.tm-wrap { padding: 20px 24px 80px; background: #f7f8fa; min-height: 100%; }

			/* ── Tabs ── */
			.tm-tabs {
				display: flex; gap: 4px; margin-bottom: 18px;
				border-bottom: 1px solid #e4e7ea;
			}
			.tm-tab-btn {
				background: none; border: none; cursor: pointer;
				padding: 10px 4px; margin-right: 22px;
				font-size: 14px; font-weight: 600; color: #888;
				border-bottom: 2.5px solid transparent;
				transition: color 0.15s, border-color 0.15s;
			}
			.tm-tab-btn:hover { color: #c84630; }
			.tm-tab-btn.active { color: #c84630; border-color: #c84630; }

			/* ── Requests status chart ── */
			.tm-req-chart { display: flex; flex-direction: column; gap: 10px; }
			.tm-req-chart-row { display: flex; align-items: center; gap: 10px; }
			.tm-req-chart-label { width: 130px; flex-shrink: 0; font-size: 12px; color: #555; font-weight: 500; }
			.tm-req-chart-track { flex: 1; height: 16px; background: #f0f1f3; border-radius: 8px; overflow: hidden; }
			.tm-req-chart-fill { height: 100%; border-radius: 8px; transition: width 0.3s; }
			.tm-req-chart-count { width: 34px; text-align: right; font-size: 12px; font-weight: 700; color: #333; }

			/* ── Payment info button ── */
			.tm-pay-btn {
				width: 28px; height: 28px; border-radius: 6px; border: 1.5px solid #d1d8dd;
				background: #fff; cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
				color: #666; transition: border-color 0.15s, color 0.15s;
			}
			.tm-pay-btn:hover { border-color: #c84630; color: #c84630; }

			/* ── Payment details dialog table ── */
			.tm-pay-detail-row { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid #f0f1f3; font-size: 13px; }
			.tm-pay-detail-row:last-child { border-bottom: none; }
			.tm-pay-detail-label { color: #888; }
			.tm-pay-detail-value { color: #222; font-weight: 600; text-align: right; }
			.tm-pay-gateway-json {
				background: #f7f8fa; border: 1px solid #e4e7ea; border-radius: 6px;
				padding: 10px; font-family: monospace; font-size: 11.5px; white-space: pre-wrap;
				max-height: 240px; overflow: auto; margin-top: 10px; color: #444;
			}

			/* ── Stats bar ── */
			.tm-stats-bar {
				display: flex;
				gap: 12px;
				margin-bottom: 16px;
				flex-wrap: wrap;
			}
			.tm-stat-card {
				flex: 1;
				min-width: 150px;
				background: #fff;
				border: 1px solid #e4e7ea;
				border-radius: 10px;
				padding: 14px 16px;
				display: flex;
				align-items: center;
				gap: 12px;
				box-shadow: 0 1px 4px rgba(0,0,0,0.04);
				transition: box-shadow 0.15s;
			}
			.tm-stat-card:hover { box-shadow: 0 3px 12px rgba(0,0,0,0.08); }
			.tm-stat-icon {
				width: 40px; height: 40px;
				border-radius: 10px;
				display: flex; align-items: center; justify-content: center;
				flex-shrink: 0;
			}
			.tm-stat-icon-total    { background: #eff3ff; color: #3b5bdb; }
			.tm-stat-icon-interim  { background: #fff3cd; color: #b45309; }
			.tm-stat-icon-final    { background: #e6f4ea; color: #1a7a36; }
			.tm-stat-icon-pending  { background: #fdecea; color: #c84630; }
			.tm-stat-body { flex: 1; min-width: 0; }
			.tm-stat-value {
				font-size: 22px; font-weight: 700; color: #1a1a2e; line-height: 1;
				transition: color 0.2s;
			}
			.tm-stat-label { font-size: 11px; color: #888; margin-top: 3px; font-weight: 500; }

			/* ── Toolbar ── */
			.tm-toolbar {
				display: flex;
				align-items: center;
				gap: 10px;
				flex-wrap: wrap;
				margin-bottom: 16px;
			}
			.tm-search-box {
				flex: 1;
				min-width: 260px;
				max-width: 420px;
				position: relative;
			}
			.tm-search-box svg {
				position: absolute; left: 11px; top: 50%;
				transform: translateY(-50%); pointer-events: none;
			}
			.tm-search-input {
				width: 100%; padding: 8px 12px 8px 34px;
				border: 1px solid #d1d8dd; border-radius: 6px;
				font-size: 13px; outline: none; box-sizing: border-box;
				background: #fff; color: #333;
				transition: border-color 0.15s, box-shadow 0.15s;
				height: 34px;
			}
			.tm-search-input:focus {
				border-color: #c84630;
				box-shadow: 0 0 0 3px rgba(200,70,48,0.1);
			}
			.tm-search-input::placeholder { color: #aab; }

			/* Action buttons group */
			.tm-actions { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

			/* Base button reset */
			.tm-btn {
				display: inline-flex; align-items: center; gap: 6px;
				padding: 0 14px; height: 34px;
				font-size: 13px; font-weight: 600; border-radius: 6px;
				cursor: pointer;
				transition: background 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s;
				white-space: nowrap; border: 1.5px solid transparent; line-height: 1;
			}
			.tm-btn:focus { outline: none; }

			/* Outline / ghost variant */
			.tm-btn-outline {
				background: #fff; border-color: #c84630; color: #c84630;
			}
			.tm-btn-outline:hover {
				background: #c84630; color: #fff;
				box-shadow: 0 2px 8px rgba(200,70,48,0.2);
			}
			.tm-btn-outline:hover svg { stroke: #fff; }

			/* Primary filled */
			.tm-btn-primary { background: #c84630; border-color: #c84630; color: #fff; }
			.tm-btn-primary:hover {
				background: #a83828; border-color: #a83828;
				box-shadow: 0 2px 8px rgba(200,70,48,0.3);
			}

			/* Default/neutral */
			.tm-btn-default { background: #fff; border-color: #d1d8dd; color: #444; }
			.tm-btn-default:hover {
				border-color: #c84630; color: #c84630; background: #fff8f7;
			}

			/* Split button group */
			.tm-split-group { display: inline-flex; }
			.tm-split-group .tm-btn { border-radius: 0; }
			.tm-split-group .tm-btn:first-child { border-radius: 6px 0 0 6px; border-right: none; }
			.tm-split-group .tm-btn:last-child  { border-radius: 0 6px 6px 0; padding: 0 10px; border-left: 1px solid rgba(255,255,255,0.3); }
			.tm-split-group .tm-btn-outline:last-child { border-left-color: rgba(200,70,48,0.4); }

			/* Dropdown */
			.tm-dropdown { position: relative; display: inline-flex; }
			.tm-dropdown-menu {
				display: none; position: absolute;
				top: calc(100% + 4px); right: 0; z-index: 1050;
				background: #fff; border: 1px solid #e0e4e8;
				border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,0.12);
				min-width: 220px; padding: 6px 0;
				list-style: none; margin: 0;
			}
			.tm-dropdown-menu.open { display: block; }
			.tm-dropdown-menu li a {
				display: flex; align-items: center; gap: 8px;
				padding: 8px 16px; font-size: 13px; color: #333;
				text-decoration: none; transition: background 0.1s;
			}
			.tm-dropdown-menu li a:hover { background: #fdf5f5; color: #c84630; }
			.tm-dropdown-menu .tm-divider { height: 1px; background: #f0f1f3; margin: 4px 0; }
			.tm-dropdown-menu .tm-menu-label {
				padding: 6px 16px 4px; font-size: 10px; font-weight: 700;
				text-transform: uppercase; letter-spacing: 0.06em; color: #aaa;
			}

			/* Icon button */
			.tm-icon-btn {
				width: 34px; height: 34px; padding: 0; border-radius: 6px;
				background: #fff; border: 1.5px solid #d1d8dd; cursor: pointer;
				display: inline-flex; align-items: center; justify-content: center;
				transition: border-color 0.15s, background 0.15s; color: #666;
			}
			.tm-icon-btn:hover { border-color: #c84630; color: #c84630; background: #fff8f7; }
			.tm-icon-btn:focus { outline: none; }

			/* Filter badge on button */
			.tm-filter-badge {
				display: inline-flex; align-items: center; justify-content: center;
				background: #c84630; color: #fff; border-radius: 50%;
				font-size: 10px; font-weight: 700; width: 16px; height: 16px; margin-left: 2px;
			}

			/* Filter panel */
			.tm-filter-panel {
				background: #fff; border: 1px solid #e4e7ea; border-radius: 8px;
				padding: 18px 20px 16px; margin-bottom: 16px;
				box-shadow: 0 2px 8px rgba(0,0,0,0.04);
			}
			.tm-filter-panel-title {
				font-size: 11px; font-weight: 700; text-transform: uppercase;
				letter-spacing: 0.06em; color: #888; margin-bottom: 14px;
			}
			.tm-filter-grid {
				display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 14px;
			}
			.tm-filter-field label {
				display: block; font-size: 11px; font-weight: 600;
				color: #555; margin-bottom: 5px; letter-spacing: 0.02em;
			}
			.tm-filter-select {
				width: 100%; padding: 7px 10px; border: 1px solid #d1d8dd;
				border-radius: 5px; font-size: 13px; background: #fafbfc; color: #333;
				outline: none; transition: border-color 0.15s, box-shadow 0.15s;
				height: 34px; cursor: pointer; appearance: auto;
			}
			.tm-filter-select:focus {
				border-color: #c84630; box-shadow: 0 0 0 3px rgba(200,70,48,0.1); background: #fff;
			}
			.tm-filter-actions {
				margin-top: 16px; display: flex; gap: 8px; align-items: center;
				border-top: 1px solid #f0f1f3; padding-top: 14px;
			}

			/* Active filter tags */
			.tm-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
			.tm-tag {
				display: inline-flex; align-items: center; gap: 4px;
				padding: 3px 6px 3px 10px; background: #fff0ee;
				border: 1px solid #fcc; border-radius: 20px;
				font-size: 11px; color: #c84630; font-weight: 500;
			}
			.tm-tag-remove {
				background: none; border: none; padding: 0 2px; line-height: 1;
				cursor: pointer; color: #e08070; font-size: 12px;
				display: inline-flex; align-items: center; border-radius: 50%;
				transition: color 0.1s, background 0.1s;
			}
			.tm-tag-remove:hover { color: #c84630; background: rgba(200,70,48,0.1); }

			/* Table card */
			.tm-table-card {
				background: #fff; border: 1px solid #dee2e6; border-radius: 6px;
				overflow: hidden; box-shadow: 0 1px 6px rgba(0,0,0,0.05);
			}

			/* DataTables top bar */
			.tm-dt-topbar {
				display: flex; align-items: center; justify-content: space-between;
				padding: 10px 14px; border-bottom: 1px solid #dee2e6;
				background: #f8f9fa;
			}
			.tm-dt-entries {
				font-size: 12px; color: #555;
				display: flex; align-items: center; gap: 6px;
			}
			.tm-dt-select {
				padding: 2px 6px; border: 1px solid #ced4da; border-radius: 3px;
				font-size: 12px; background: #fff; cursor: pointer;
				height: 26px; color: #333;
			}
			.tm-dt-topbar-right { font-size: 12px; color: #888; }

			/* DataTables bottom bar */
			.tm-dt-bottombar {
				display: flex; align-items: center; justify-content: space-between;
				padding: 10px 14px; border-top: 1px solid #dee2e6;
				background: #f8f9fa; flex-wrap: wrap; gap: 8px;
			}
			.tm-page-info { font-size: 12px; color: #6c757d; }
			.tm-page-controls { display: flex; align-items: center; }
			.tm-page-btn {
				padding: 0 10px; height: 28px;
				border: 1px solid #dee2e6; border-right: none;
				background: #fff; font-size: 12px; font-weight: 500;
				color: #495057; cursor: pointer; transition: all 0.12s;
				display: inline-flex; align-items: center;
			}
			.tm-page-btn:first-child { border-radius: 3px 0 0 3px; }
			.tm-page-btn:last-child  { border-right: 1px solid #dee2e6; border-radius: 0 3px 3px 0; }
			.tm-page-btn:hover:not(:disabled) { background: #e9ecef; color: #c84630; border-color: #c84630; z-index: 1; }
			.tm-page-btn:disabled { opacity: 0.45; cursor: not-allowed; background: #f8f9fa; }
			.tm-page-num {
				padding: 0 10px; height: 28px;
				border: 1px solid #dee2e6; border-right: none;
				background: #fff; font-size: 12px; color: #495057;
				cursor: pointer; display: inline-flex; align-items: center;
				transition: all 0.12s;
			}
			.tm-page-num:hover { background: #e9ecef; color: #c84630; }
			.tm-page-num.active {
				background: #c84630; color: #fff; border-color: #c84630;
				font-weight: 700; z-index: 1; position: relative;
			}
			.tm-page-ellipsis {
				padding: 0 8px; height: 28px;
				border: 1px solid #dee2e6; border-right: none;
				background: #fff; font-size: 12px; color: #aaa;
				display: inline-flex; align-items: center;
			}

			/* DataTables table */
			.tm-table { width: 100%; border-collapse: collapse; margin: 0; }
			.tm-table thead tr { background: #f2f4f6; }
			.tm-table thead th {
				font-size: 11px; font-weight: 700; text-transform: uppercase;
				letter-spacing: 0.04em; color: #495057;
				padding: 9px 12px; white-space: nowrap;
				border-bottom: 2px solid #dee2e6;
				border-right: 1px solid #e4e7ea;
			}
			.tm-table thead th:last-child { border-right: none; }
			.tm-table thead th.tm-col-accent { color: #c84630; }
			.tm-table thead th.tm-sortable { cursor: pointer; user-select: none; }
			.tm-table thead th.tm-sortable:hover { background: #e8eaed; }
			.tm-table tbody tr { transition: background 0.08s; }
			.tm-table tbody tr:nth-child(even) { background: #f9fafb; }
			.tm-table tbody tr:hover { background: #fff3f0 !important; }
			.tm-table tbody td {
				padding: 9px 12px; vertical-align: middle;
				border-bottom: 1px solid #e9ecef;
				border-right: 1px solid #e9ecef;
			}
			.tm-table tbody td:last-child { border-right: none; }
			.tm-table tbody tr:last-child td { border-bottom: none; }

			/* Sort indicator */
			.tm-sort-icon { font-size: 10px; color: #ccc; margin-left: 3px; }
			.tm-sort-icon.asc  { color: #c84630; }
			.tm-sort-icon.desc { color: #c84630; }

			/* Avatar */
			.tm-avatar {
				width: 36px; height: 36px; border-radius: 50%;
				object-fit: cover; flex-shrink: 0; border: 2px solid #f0f0f0;
			}
			.tm-avatar-initials {
				width: 36px; height: 36px; border-radius: 50%;
				display: inline-flex; align-items: center; justify-content: center;
				background: linear-gradient(135deg, #c84630, #e06040);
				color: #fff; font-weight: 700; font-size: 14px; flex-shrink: 0;
			}

			/* Student name link */
			.tm-student-link {
				font-weight: 600; color: #c84630; font-size: 13px; text-decoration: none;
			}
			.tm-student-link:hover { text-decoration: underline; }

			/* Transcript interactive badges */
			.tm-badge {
				display: inline-flex; align-items: center; gap: 4px;
				padding: 3px 10px; border-radius: 20px;
				font-size: 11px; font-weight: 600; white-space: nowrap;
			}
			.tm-badge-generated {
				background: #e6f4ea; color: #1a7a36; border: 1px solid #b7dfc5;
				cursor: pointer; transition: box-shadow 0.12s, background 0.12s;
			}
			.tm-badge-generated:hover {
				background: #d0edda; box-shadow: 0 2px 8px rgba(26,122,54,0.2);
			}
			.tm-badge-revoked {
				background: #fdecea; color: #c0392b; border: 1px solid #f5c0bb;
				cursor: pointer; transition: box-shadow 0.12s;
			}
			.tm-badge-revoked:hover {
				background: #fad7d4; box-shadow: 0 2px 8px rgba(192,57,43,0.15);
			}
			.tm-badge-pending { background: #fff3cd; color: #856404; border: 1px solid #ffe69c; }
			.tm-badge-na { color: #ccc; font-weight: 400; }

			/* Clickable "generate" dash badge */
			.tm-gen-badge {
				display: inline-flex; align-items: center; gap: 4px;
				padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 500;
				border: 1.5px dashed #d1d8dd; color: #bbb;
				background: none; cursor: pointer;
				transition: border-color 0.15s, color 0.15s, background 0.15s;
				white-space: nowrap;
			}
			.tm-gen-badge:hover {
				border-color: #c84630; color: #c84630; background: #fff0ee;
			}

			/* Student status pill */
			.tm-status-pill {
				display: inline-block; padding: 2px 8px; border-radius: 20px;
				font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
			}
			.tm-status-active    { background: #e6f4ea; color: #1a7a36; }
			.tm-status-inactive  { background: #f0f1f3; color: #666; }
			.tm-status-graduated { background: #e8f0fe; color: #1a5ccb; }
			.tm-status-dropped   { background: #fdecea; color: #c0392b; }
			.tm-status-alumni    { background: #fef3e6; color: #b45309; }
			.tm-status-dormant   { background: #f5effe; color: #6b21a8; }

			/* (pagination styles moved to DataTables bottom bar section above) */

			/* Loading spinner */
			.tm-spinner {
				width: 28px; height: 28px;
				border: 3px solid #f0f0f0; border-top-color: #c84630;
				border-radius: 50%; animation: tm-spin 0.8s linear infinite;
				margin: 0 auto 10px;
			}

			/* Checkbox styling */
			.tm-checkbox { width: 15px; height: 15px; cursor: pointer; accent-color: #c84630; }

			/* ── Selection action bar (fixed at bottom) ── */
			.tm-sel-bar {
				position: fixed; bottom: 0; left: 0; right: 0;
				background: #1e2a3a; color: #fff;
				padding: 0 28px;
				display: flex; align-items: center; gap: 10px;
				z-index: 1100;
				height: 56px;
				box-shadow: 0 -4px 20px rgba(0,0,0,0.22);
				transform: translateY(100%);
				transition: transform 0.22s cubic-bezier(.4,0,.2,1);
			}
			.tm-sel-bar.tm-sel-bar--visible { transform: translateY(0); }
			.tm-sel-count {
				font-weight: 700; font-size: 13px; color: #fff;
				background: rgba(255,255,255,0.12);
				padding: 4px 12px; border-radius: 20px; margin-right: 4px;
			}
			.tm-sel-label { font-size: 13px; color: rgba(255,255,255,0.7); }
			.tm-sel-divider { width: 1px; height: 24px; background: rgba(255,255,255,0.15); margin: 0 4px; }
			.tm-sel-clear {
				margin-left: auto;
				background: none; border: 1.5px solid rgba(255,255,255,0.2);
				color: rgba(255,255,255,0.6); padding: 5px 12px; border-radius: 6px;
				font-size: 12px; cursor: pointer; transition: all 0.15s;
			}
			.tm-sel-clear:hover { border-color: rgba(255,255,255,0.5); color: #fff; }
		`;
		document.head.appendChild(style);
	}

	// ── Build page HTML ────────────────────────────────────────────────────────
	$(wrapper).find(".page-content").html(`
		<div class="tm-wrap">

			<!-- Tab Switcher -->
			<div class="tm-tabs">
				<button class="tm-tab-btn active" id="tm-tab-students" data-tab="students">
					${__("Students")}
				</button>
				<button class="tm-tab-btn" id="tm-tab-requests" data-tab="requests">
					${__("Requests")}
				</button>
			</div>

			<!-- ══════════════ STUDENTS TAB ══════════════ -->
			<div id="tm-panel-students" class="tm-panel">

			<!-- Toolbar -->
			<div class="tm-toolbar">
				<div class="tm-search-box">
					<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
						fill="none" stroke="#999" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
						<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
					</svg>
					<input id="tm-search" type="text" class="tm-search-input"
						placeholder="${__("Search by Student Name, Registration ID, Email")}" />
				</div>

				<div class="tm-actions">
					<!-- Filter button -->
					<button id="tm-filter-btn" class="tm-btn tm-btn-outline">
						<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
							<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
						</svg>
						${__("Filter")}
						<span id="tm-filter-count" class="tm-filter-badge" style="display:none;">0</span>
					</button>

					<!-- Compact transcript download -->
					<button type="button" class="tm-btn tm-btn-outline" id="tm-dl-compact"
						title="${__("Download Compact Transcript")}">
						<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
							<polyline points="7 10 12 15 17 10"/>
							<line x1="12" y1="15" x2="12" y2="3"/>
						</svg>
						${__("Download Compact")}
					</button>

					<!-- Templates / Settings -->
					<button id="tm-settings-btn" class="tm-btn tm-btn-default"
						title="${__("Transcript Templates")}">
						<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
							<rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
						</svg>
						${__("Templates")}
					</button>
				</div>
			</div>

			<!-- Stats Bar -->
			<div class="tm-stats-bar">
				<div class="tm-stat-card">
					<div class="tm-stat-icon tm-stat-icon-total">
						<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
							<circle cx="9" cy="7" r="4"/>
							<path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
							<path d="M16 3.13a4 4 0 0 1 0 7.75"/>
						</svg>
					</div>
					<div class="tm-stat-body">
						<div class="tm-stat-value" id="tm-stat-total">—</div>
						<div class="tm-stat-label">${__("Total Students")}</div>
					</div>
				</div>
				<div class="tm-stat-card">
					<div class="tm-stat-icon tm-stat-icon-interim">
						<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
							<polyline points="14 2 14 8 20 8"/>
							<line x1="8" y1="13" x2="16" y2="13"/>
							<line x1="8" y1="17" x2="14" y2="17"/>
						</svg>
					</div>
					<div class="tm-stat-body">
						<div class="tm-stat-value" id="tm-stat-interim">—</div>
						<div class="tm-stat-label">${__("Interim Generated")}</div>
					</div>
				</div>
				<div class="tm-stat-card">
					<div class="tm-stat-icon tm-stat-icon-final">
						<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
							<polyline points="14 2 14 8 20 8"/>
							<polyline points="8 17 10 19 14 15"/>
						</svg>
					</div>
					<div class="tm-stat-body">
						<div class="tm-stat-value" id="tm-stat-final">—</div>
						<div class="tm-stat-label">${__("Final Generated")}</div>
					</div>
				</div>
				<div class="tm-stat-card">
					<div class="tm-stat-icon tm-stat-icon-pending">
						<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<circle cx="12" cy="12" r="10"/>
							<polyline points="12 6 12 12 16 14"/>
						</svg>
					</div>
					<div class="tm-stat-body">
						<div class="tm-stat-value" id="tm-stat-pending">—</div>
						<div class="tm-stat-label">${__("Pending Final")}</div>
					</div>
				</div>
			</div>

			<!-- Filter Panel -->
			<div id="tm-filter-panel" class="tm-filter-panel" style="display:none;">
				<div class="tm-filter-panel-title">${__("Filter Students")}</div>
				<div class="tm-filter-grid">
					<div class="tm-filter-field">
						<label>${__("Programme")}</label>
						<select id="tm-f-programme" class="tm-filter-select tm-filter-sel">
							<option value="">${__("All Programmes")}</option>
						</select>
					</div>
					<div class="tm-filter-field">
						<label>${__("Department")}</label>
						<select id="tm-f-department" class="tm-filter-select tm-filter-sel">
							<option value="">${__("All Departments")}</option>
						</select>
					</div>
					<div class="tm-filter-field">
						<label>${__("Course")}</label>
						<select id="tm-f-course" class="tm-filter-select tm-filter-sel">
							<option value="">${__("All Courses")}</option>
						</select>
					</div>
					<div class="tm-filter-field">
						<label>${__("Academic Year")}</label>
						<select id="tm-f-academic-year" class="tm-filter-select tm-filter-sel">
							<option value="">${__("All Years")}</option>
						</select>
					</div>
					<div class="tm-filter-field">
						<label>${__("Batch")}</label>
						<select id="tm-f-batch" class="tm-filter-select tm-filter-sel">
							<option value="">${__("All Batches")}</option>
						</select>
					</div>
					<div class="tm-filter-field">
						<label>${__("Academic Status")}</label>
						<select id="tm-f-status" class="tm-filter-select tm-filter-sel">
							<option value="">${__("All Statuses")}</option>
						</select>
					</div>
				</div>
				<div class="tm-filter-actions">
					<button id="tm-apply-filter" class="tm-btn tm-btn-primary">
						<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
							<polyline points="20 6 9 17 4 12"/>
						</svg>
						${__("Apply Filters")}
					</button>
					<button id="tm-clear-filter" class="tm-btn tm-btn-default">
						<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
							<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
						</svg>
						${__("Clear All")}
					</button>
				</div>
			</div>

			<!-- Active Filter Tags -->
			<div id="tm-active-tags" class="tm-tags"></div>

			<!-- DataTable Card -->
			<div class="tm-table-card">

				<!-- Top bar: show-entries selector -->
				<div class="tm-dt-topbar">
					<div class="tm-dt-entries">
						${__("Show")}
						<select id="tm-page-length" class="tm-dt-select">
							<option value="10">10</option>
							<option value="25">25</option>
							<option value="50" selected>50</option>
							<option value="100">100</option>
						</select>
						${__("entries")}
					</div>
					<div class="tm-dt-topbar-right" id="tm-count-badge"></div>
				</div>

				<table class="tm-table">
					<thead>
						<tr>
							<th style="width:38px; padding:9px 12px;">
								<input type="checkbox" id="tm-select-all" class="tm-checkbox"
									title="${__("Select / deselect all on this page")}" />
							</th>
							<th class="tm-sortable" data-sort="student_name" style="min-width:180px;">
								${__("Student")}
								<span class="tm-sort-icon" data-col="student_name">↕</span>
							</th>
							<th style="min-width:140px;">${__("Learning Pathway(s)")}</th>
							<th class="tm-sortable" data-sort="registration_id" style="min-width:110px;">
								${__("Reg. ID")}
								<span class="tm-sort-icon" data-col="registration_id">↓</span>
							</th>
							<th style="text-align:center; width:90px;">${__("Credits")}</th>
							<th class="tm-sortable tm-col-accent" data-sort="cgpa" style="text-align:center; width:80px;">
								${__("CGPA")}
								<span class="tm-sort-icon" data-col="cgpa">↕</span>
							</th>
							<th class="tm-col-accent" style="text-align:center; width:120px;">${__("Interim")}</th>
							<!-- FINAL column hidden: <th style="text-align:center; width:120px;">\${__("Final")}</th> -->
						</tr>
					</thead>
					<tbody id="tm-tbody">
						<tr>
							<td colspan="7" style="text-align:center; padding:48px; color:#aaa;">
								<div class="tm-spinner"></div>
								${__("Loading students...")}
							</td>
						</tr>
					</tbody>
				</table>

				<!-- Bottom bar: info + page navigation -->
				<div class="tm-dt-bottombar">
					<span id="tm-page-info" class="tm-page-info"></span>
					<div class="tm-page-controls" id="tm-page-controls"></div>
				</div>

			</div>

			</div> <!-- /tm-panel-students -->

			<!-- ══════════════ REQUESTS TAB ══════════════ -->
			<div id="tm-panel-requests" class="tm-panel" style="display:none;">

				<!-- Analytics -->
				<div class="tm-stats-bar" id="tm-req-stats">
					<div class="tm-stat-card">
						<div class="tm-stat-icon tm-stat-icon-total">
							<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
								fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
							</svg>
						</div>
						<div class="tm-stat-body">
							<div class="tm-stat-value" id="tm-rstat-total">—</div>
							<div class="tm-stat-label">${__("Total Requests")}</div>
						</div>
					</div>
					<div class="tm-stat-card">
						<div class="tm-stat-icon tm-stat-icon-pending">
							<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
								fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
							</svg>
						</div>
						<div class="tm-stat-body">
							<div class="tm-stat-value" id="tm-rstat-review">—</div>
							<div class="tm-stat-label">${__("Under Review")}</div>
						</div>
					</div>
					<div class="tm-stat-card">
						<div class="tm-stat-icon tm-stat-icon-final">
							<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
								fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<polyline points="20 6 9 17 4 12"/>
							</svg>
						</div>
						<div class="tm-stat-body">
							<div class="tm-stat-value" id="tm-rstat-generated">—</div>
							<div class="tm-stat-label">${__("Generated / Delivered")}</div>
						</div>
					</div>
					<div class="tm-stat-card">
						<div class="tm-stat-icon tm-stat-icon-interim" style="font-size:18px; font-weight:700;">₹</div>
						<div class="tm-stat-body">
							<div class="tm-stat-value" id="tm-rstat-revenue">—</div>
							<div class="tm-stat-label">${__("Revenue Collected")}</div>
						</div>
					</div>
					<div class="tm-stat-card">
						<div class="tm-stat-icon tm-stat-icon-pending">
							<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
								fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
							</svg>
						</div>
						<div class="tm-stat-body">
							<div class="tm-stat-value" id="tm-rstat-rejected">—</div>
							<div class="tm-stat-label">${__("Rejected")}</div>
						</div>
					</div>
				</div>

				<!-- Status distribution bar chart -->
				<div class="tm-table-card" style="padding:16px 20px; margin-bottom:16px;">
					<div class="tm-filter-panel-title" style="margin-bottom:10px;">${__("Requests by Status")}</div>
					<div id="tm-req-chart" class="tm-req-chart"></div>
				</div>

				<!-- Toolbar -->
				<div class="tm-toolbar">
					<div class="tm-search-box">
						<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
							fill="none" stroke="#999" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
							<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
						</svg>
						<input id="tm-req-search" type="text" class="tm-search-input"
							placeholder="${__("Search by Student Name, Reg ID, Request ID")}" />
					</div>
					<div class="tm-actions">
						<select id="tm-req-f-status" class="tm-dt-select" style="height:34px;">
							<option value="">${__("All Statuses")}</option>
							<option value="Payment Pending">${__("Payment Pending")}</option>
							<option value="Submitted">${__("Submitted")}</option>
							<option value="Under Review">${__("Under Review")}</option>
							<option value="Approved">${__("Approved")}</option>
							<option value="Generated">${__("Generated")}</option>
							<option value="Delivered">${__("Delivered")}</option>
							<option value="Rejected">${__("Rejected")}</option>
							<option value="Cancelled">${__("Cancelled")}</option>
						</select>
						<select id="tm-req-f-type" class="tm-dt-select" style="height:34px;">
							<option value="">${__("All Types")}</option>
							<option value="Interim Transcript">${__("Interim Transcript")}</option>
							<option value="Final Transcript">${transcript_type_label("Final Transcript")}</option>
							<option value="Consolidated Marksheet">${__("Consolidated Marksheet")}</option>
							<option value="Duplicate Transcript">${__("Duplicate Transcript")}</option>
							<option value="Digital Transcript">${__("Digital Transcript")}</option>
						</select>
						<select id="tm-req-f-payment" class="tm-dt-select" style="height:34px;">
							<option value="">${__("All Payment Status")}</option>
							<option value="Not Required">${__("Not Required")}</option>
							<option value="Pending">${__("Pending")}</option>
							<option value="Paid">${__("Paid")}</option>
							<option value="Payment Failed">${__("Payment Failed")}</option>
							<option value="Refunded">${__("Refunded")}</option>
						</select>
						<button id="tm-req-refresh" class="tm-btn tm-btn-default" title="${__("Refresh")}">
							<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
								fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
								<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
							</svg>
							${__("Refresh")}
						</button>
					</div>
				</div>

				<!-- Requests Table -->
				<div class="tm-table-card">
					<div class="tm-dt-topbar">
						<div class="tm-dt-entries">
							${__("Show")}
							<select id="tm-req-page-length" class="tm-dt-select">
								<option value="10">10</option>
								<option value="25">25</option>
								<option value="50" selected>50</option>
								<option value="100">100</option>
							</select>
							${__("entries")}
						</div>
						<div class="tm-dt-topbar-right" id="tm-req-count-badge"></div>
					</div>

					<table class="tm-table">
						<thead>
							<tr>
								<th style="width:38px; padding:9px 12px;">
									<input type="checkbox" id="tm-req-select-all" class="tm-checkbox"
										title="${__("Select / deselect all on this page")}" />
								</th>
								<th style="min-width:80px;">${__("ID")}</th>
								<th style="min-width:160px;">${__("Student")}</th>
								<th style="min-width:130px;">${__("Type")}</th>
								<th style="min-width:100px;">${__("Status")}</th>
								<th style="min-width:110px;">${__("Payment")}</th>
								<th style="text-align:right; width:90px;">${__("Fee")}</th>
								<th style="min-width:100px;">${__("Requested")}</th>
								<th style="width:70px; text-align:center;">${__("Payment Info")}</th>
							</tr>
						</thead>
						<tbody id="tm-req-tbody">
							<tr>
								<td colspan="9" style="text-align:center; padding:48px; color:#aaa;">
									<div class="tm-spinner"></div>
									${__("Loading requests...")}
								</td>
							</tr>
						</tbody>
					</table>

					<div class="tm-dt-bottombar">
						<span id="tm-req-page-info" class="tm-page-info"></span>
						<div class="tm-page-controls" id="tm-req-page-controls"></div>
					</div>
				</div>

			</div> <!-- /tm-panel-requests -->

		</div>

		<!-- Selection Action Bar (fixed bottom, Students tab) -->
		<div id="tm-sel-bar" class="tm-sel-bar">
			<span id="tm-sel-count" class="tm-sel-count">0</span>
			<span class="tm-sel-label">${__("selected")}</span>
			<div class="tm-sel-divider"></div>
			<button id="tm-sel-clear" class="tm-sel-clear">✕ ${__("Clear selection")}</button>
		</div>

		<!-- Selection Action Bar (fixed bottom, Requests tab) -->
		<div id="tm-req-sel-bar" class="tm-sel-bar">
			<span id="tm-req-sel-count" class="tm-sel-count">0</span>
			<span class="tm-sel-label">${__("selected")}</span>
			<div class="tm-sel-divider"></div>
			<button id="tm-req-bulk-approve" class="tm-btn tm-btn-primary" style="height:30px;">
				${__("Approve & Generate")}
			</button>
			<button id="tm-req-bulk-reject" class="tm-btn tm-btn-outline" style="height:30px; border-color:#fff; color:#fff;">
				${__("Reject")}
			</button>
			<button id="tm-req-sel-clear" class="tm-sel-clear">✕ ${__("Clear selection")}</button>
		</div>
	`);

	// ── Event Bindings ─────────────────────────────────────────────────────────

	// Tab switching
	$(wrapper).on("click", ".tm-tab-btn", function () {
		const tab = $(this).data("tab");
		if (tab === active_tab.value) return;
		active_tab.value = tab;
		$(wrapper).find(".tm-tab-btn").removeClass("active");
		$(this).addClass("active");

		if (tab === "students") {
			$(wrapper).find("#tm-panel-requests").hide();
			$(wrapper).find("#tm-panel-students").show();
			$(wrapper).find("#tm-req-sel-bar").removeClass("tm-sel-bar--visible");
			update_selection_bar();
		} else {
			$(wrapper).find("#tm-panel-students").hide();
			$(wrapper).find("#tm-panel-requests").show();
			$(wrapper).find("#tm-sel-bar").removeClass("tm-sel-bar--visible");
			load_request_stats();
			load_requests();
		}
	});

	// Search debounce
	let searchTimer;
	$(wrapper).on("input", "#tm-search", function () {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => {
			state.search = $(this).val().trim();
			state.page = 1;
			load_students();
		}, 350);
	});

	// Filter panel toggle
	$(wrapper).on("click", "#tm-filter-btn", function () {
		$(wrapper).find("#tm-filter-panel").slideToggle(180);
	});

	// Apply filters
	$(wrapper).on("click", "#tm-apply-filter", function () {
		state.programme      = $(wrapper).find("#tm-f-programme").val();
		state.department     = $(wrapper).find("#tm-f-department").val();
		state.course         = $(wrapper).find("#tm-f-course").val();
		state.academic_year  = $(wrapper).find("#tm-f-academic-year").val();
		state.batch          = $(wrapper).find("#tm-f-batch").val();
		state.student_status = $(wrapper).find("#tm-f-status").val();
		state.page = 1;
		render_active_tags();
		update_filter_count_badge();
		load_students();
	});

	// Clear filters
	$(wrapper).on("click", "#tm-clear-filter", function () {
		$(wrapper).find(".tm-filter-sel").val("");
		state.programme = state.department = state.course =
		state.academic_year = state.batch = state.student_status = "";
		state.page = 1;
		render_active_tags();
		update_filter_count_badge();
		load_students();
	});

	// Select all (current page)
	$(wrapper).on("change", "#tm-select-all", function () {
		const checked = $(this).is(":checked");
		$(wrapper).find(".tm-row-check").prop("checked", checked).each(function () {
			const sid = $(this).data("student");
			if (checked) state.selected.add(sid);
			else         state.selected.delete(sid);
		});
		update_selection_bar();
	});

	// Row checkboxes
	$(wrapper).on("change", ".tm-row-check", function () {
		const sid = $(this).data("student");
		if ($(this).is(":checked")) state.selected.add(sid);
		else                        state.selected.delete(sid);
		const total = $(wrapper).find(".tm-row-check").length;
		const sel   = $(wrapper).find(".tm-row-check:checked").length;
		$(wrapper).find("#tm-select-all")
			.prop("indeterminate", sel > 0 && sel < total)
			.prop("checked", sel === total && total > 0);
		update_selection_bar();
	});

	// Year-based dropdown action
	$(wrapper).on("click", "#tm-dl-compact", function () { handle_compact_download(); });

	// Settings / Templates
	$(wrapper).on("click", "#tm-settings-btn", function () {
		frappe.set_route("transcript-template-page");
	});

	// Sort columns
	$(wrapper).on("click", ".tm-sortable", function () {
		const col = $(this).data("sort");
		if (state.sort_by === col) {
			state.sort_order = state.sort_order === "asc" ? "desc" : "asc";
		} else {
			state.sort_by    = col;
			state.sort_order = "asc";
		}
		state.page = 1;
		update_sort_indicators();
		load_students();
	});

	// Page-length selector
	$(wrapper).on("change", "#tm-page-length", function () {
		state.page_length = parseInt($(this).val());
		state.page = 1;
		load_students();
	});

	// ── Inline badge actions ───────────────────────────────────────────────────

	// Click "—" / "Revoked" badge → generate transcript for that student
	$(wrapper).on("click", ".tm-inline-gen", function (e) {
		e.stopPropagation();
		const student = $(this).data("student");
		const type    = $(this).data("type");
		frappe.confirm(
			__("Generate {0} Transcript for this student?", [type]),
			function () { do_generate([student], type); }
		);
	});

	// Click "Generated" badge → download transcript for that student
	$(wrapper).on("click", ".tm-inline-dl", function (e) {
		e.stopPropagation();
		const student = $(this).data("student");
		const type    = $(this).data("type");
		handle_download_single(student, type);
	});

	// ── Selection bar actions ──────────────────────────────────────────────────
	$(wrapper).on("click", "#tm-sel-clear", function () {
		state.selected.clear();
		$(wrapper).find(".tm-row-check").prop("checked", false);
		$(wrapper).find("#tm-select-all").prop("checked", false).prop("indeterminate", false);
		update_selection_bar();
	});

	// ── Requests tab: event bindings ────────────────────────────────────────────

	let reqSearchTimer;
	$(wrapper).on("input", "#tm-req-search", function () {
		clearTimeout(reqSearchTimer);
		reqSearchTimer = setTimeout(() => {
			req_state.search = $(this).val().trim();
			req_state.page = 1;
			load_requests();
		}, 350);
	});

	$(wrapper).on("change", "#tm-req-f-status", function () {
		req_state.status = $(this).val();
		req_state.page = 1;
		load_requests();
	});
	$(wrapper).on("change", "#tm-req-f-type", function () {
		req_state.transcript_type = $(this).val();
		req_state.page = 1;
		load_requests();
	});
	$(wrapper).on("change", "#tm-req-f-payment", function () {
		req_state.payment_status = $(this).val();
		req_state.page = 1;
		load_requests();
	});
	$(wrapper).on("change", "#tm-req-page-length", function () {
		req_state.page_length = parseInt($(this).val());
		req_state.page = 1;
		load_requests();
	});
	$(wrapper).on("click", "#tm-req-refresh", function () {
		load_request_stats();
		load_requests();
	});

	$(wrapper).on("change", "#tm-req-select-all", function () {
		const checked = $(this).is(":checked");
		$(wrapper).find(".tm-req-row-check").prop("checked", checked).each(function () {
			const name = $(this).data("name");
			if (checked) req_state.selected.add(name);
			else         req_state.selected.delete(name);
		});
		update_req_selection_bar();
	});

	$(wrapper).on("change", ".tm-req-row-check", function () {
		const name = $(this).data("name");
		if ($(this).is(":checked")) req_state.selected.add(name);
		else                        req_state.selected.delete(name);
		const total = $(wrapper).find(".tm-req-row-check").length;
		const sel   = $(wrapper).find(".tm-req-row-check:checked").length;
		$(wrapper).find("#tm-req-select-all")
			.prop("indeterminate", sel > 0 && sel < total)
			.prop("checked", sel === total && total > 0);
		update_req_selection_bar();
	});

	$(wrapper).on("click", "#tm-req-sel-clear", function () {
		req_state.selected.clear();
		$(wrapper).find(".tm-req-row-check").prop("checked", false);
		$(wrapper).find("#tm-req-select-all").prop("checked", false).prop("indeterminate", false);
		update_req_selection_bar();
	});

	$(wrapper).on("click", ".tm-pay-btn", function () {
		show_payment_details($(this).data("name"));
	});

	$(wrapper).on("click", "#tm-req-bulk-approve", function () {
		const names = [...req_state.selected];
		if (!names.length) return;
		frappe.confirm(
			__("Approve & generate transcripts for {0} selected request(s)?", [names.length]),
			function () { bulk_approve(names); }
		);
	});

	$(wrapper).on("click", "#tm-req-bulk-reject", function () {
		const names = [...req_state.selected];
		if (!names.length) return;
		frappe.prompt(
			{
				fieldname: "rejection_reason",
				label: __("Rejection Reason"),
				fieldtype: "Small Text",
				reqd: 1,
			},
			(values) => bulk_reject(names, values.rejection_reason),
			__("Reject {0} Request(s)", [names.length])
		);
	});

	// ── Functions ──────────────────────────────────────────────────────────────

	function update_selection_bar() {
		const count = state.selected.size;
		const bar   = $(wrapper).find("#tm-sel-bar");
		$(wrapper).find("#tm-sel-count").text(count);
		if (count > 0) {
			bar.addClass("tm-sel-bar--visible");
		} else {
			bar.removeClass("tm-sel-bar--visible");
		}
	}

	function load_stats() {
		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.get_transcript_stats",
			args: {
				search:         state.search,
				programme:      state.programme,
				course:         state.course,
				academic_year:  state.academic_year,
				batch:          state.batch,
				student_status: state.student_status,
				department:     state.department,
			},
			callback: function (r) {
				if (!r.message) return;
				const s = r.message;
				$(wrapper).find("#tm-stat-total").text(s.total_students || 0);
				$(wrapper).find("#tm-stat-interim").text(s.interim_generated || 0);
				$(wrapper).find("#tm-stat-final").text(s.final_generated || 0);
				const pending = (s.total_students || 0) - (s.final_generated || 0);
				$(wrapper).find("#tm-stat-pending").text(pending > 0 ? pending : 0);
			},
		});
	}

	function load_filter_options() {
		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.get_filter_options",
			callback: function (r) {
				if (!r.message) return;
				state.filter_options = r.message;

				const prog_sel   = $(wrapper).find("#tm-f-programme");
				const dept_sel   = $(wrapper).find("#tm-f-department");
				const course_sel = $(wrapper).find("#tm-f-course");
				const yr_sel     = $(wrapper).find("#tm-f-academic-year");
				const bat_sel    = $(wrapper).find("#tm-f-batch");
				const stat_sel   = $(wrapper).find("#tm-f-status");

				(r.message.programmes || []).forEach(p => {
					const label = p.program_name || p.name;
					state._prog_labels[p.name] = label;
					prog_sel.append(`<option value="${p.name}">${frappe.utils.escape_html(label)}</option>`);
				});
				(r.message.departments || []).forEach(d => {
					const label = d.department_name || d.name;
					state._dept_labels[d.name] = label;
					dept_sel.append(`<option value="${d.name}">${frappe.utils.escape_html(label)}</option>`);
				});
				(r.message.courses || []).forEach(c => {
					const label = c.course_name + (c.course_code ? ` (${c.course_code})` : "");
					course_sel.append(`<option value="${c.name}">${frappe.utils.escape_html(label)}</option>`);
				});
				(r.message.academic_years || []).forEach(y => {
					yr_sel.append(`<option value="${y}">${frappe.utils.escape_html(y)}</option>`);
				});
				(r.message.batches || []).forEach(b => {
					const label = b.batch_name || b.name;
					bat_sel.append(`<option value="${b.name}">${frappe.utils.escape_html(label)}</option>`);
				});
				(r.message.student_statuses || []).forEach(s => {
					stat_sel.append(`<option value="${s}">${frappe.utils.escape_html(s)}</option>`);
				});

				prog_sel.val(state.programme);
				dept_sel.val(state.department);
				course_sel.val(state.course);
				yr_sel.val(state.academic_year);
				bat_sel.val(state.batch);
				stat_sel.val(state.student_status);
			}
		});
	}

	function load_students() {
		if (state.loading) return;
		state.loading = true;

		$(wrapper).find("#tm-tbody").html(`
			<tr>
				<td colspan="7" style="text-align:center; padding:48px; color:#aaa;">
					<div class="tm-spinner"></div>
					${__("Loading students...")}
				</td>
			</tr>`);

		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.get_students",
			args: {
				search:         state.search,
				programme:      state.programme,
				course:         state.course,
				academic_year:  state.academic_year,
				batch:          state.batch,
				student_status: state.student_status,
				department:     state.department,
				page:           state.page,
				page_length:    state.page_length,
				sort_by:        state.sort_by,
				sort_order:     state.sort_order,
			},
			callback: function (r) {
				state.loading = false;
				if (!r.message) return;
				const { students, total } = r.message;
				state.total = total;
				render_table(students, total);
				render_pagination();
				load_stats();
			},
			error: function () {
				state.loading = false;
				$(wrapper).find("#tm-tbody").html(`
					<tr><td colspan="7" style="text-align:center; padding:32px; color:#c84630;">
						<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
							style="display:block;margin:0 auto 8px;opacity:.6;">
							<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
						</svg>
						${__("Error loading students. Please try again.")}
					</td></tr>`);
			}
		});
	}

	function render_table(students, total) {
		const tbody = $(wrapper).find("#tm-tbody");
		$(wrapper).find("#tm-count-badge").text(total ? `${total} ${__("record(s) found")}` : "");

		if (!students || students.length === 0) {
			tbody.html(`
				<tr><td colspan="7" style="text-align:center; padding:56px; color:#bbb;">
					<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24"
						fill="none" stroke="#ddd" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
						style="display:block;margin:0 auto 12px;">
						<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
						<circle cx="9" cy="7" r="4"/>
						<path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
						<path d="M16 3.13a4 4 0 0 1 0 7.75"/>
					</svg>
					<div style="font-size:14px;font-weight:600;color:#aaa;margin-bottom:4px;">${__("No students found")}</div>
					<div style="font-size:12px;">${__("Try adjusting your filters or search query.")}</div>
				</td></tr>`);
			return;
		}

		const rows = students.map((s) => {
			const name   = frappe.utils.escape_html(s.student_name || "");
			const regId  = frappe.utils.escape_html(s.registration_id || "—");
			const email  = frappe.utils.escape_html(s.email || "");
			const prog   = frappe.utils.escape_html(s.programme_name || s.programme || "");
			const batch  = frappe.utils.escape_html(s.batch_year || "");
			const acYear = frappe.utils.escape_html(s.academic_year || "");
			const checked = state.selected.has(s.student) ? "checked" : "";

			const initials = (name.trim()[0] || "?").toUpperCase();
			const photoSrc = s.photo
				? `<img src="${s.photo}" class="tm-avatar" onerror="this.outerHTML='<div class=\\'tm-avatar-initials\\'>${initials}</div>'">`
				: `<div class="tm-avatar-initials">${initials}</div>`;

			// Learning pathways
			let pathwayHtml = `<span style="color:#ccc;">—</span>`;
			if (s.learning_pathways && s.learning_pathways.length) {
				pathwayHtml = s.learning_pathways.map(p => {
					const type  = frappe.utils.escape_html(p.type || "Major");
					const pname = frappe.utils.escape_html(p.program_name || p.program || "");
					return `<div style="line-height:1.5;">
						<span style="font-size:10px;color:#aaa;font-weight:600;text-transform:uppercase;letter-spacing:.04em;">${type}</span>
						<span style="color:#bbb;"> · </span>
						<span style="font-size:12px;font-weight:600;color:#333;">${pname}</span>
					</div>`;
				}).join("");
			}

			// Credits
			const earned  = s.earned_credits || 0;
			const total_c = s.total_credits  || 0;
			const credHtml = `<span style="font-weight:700;font-size:13px;">${earned}</span>`
				+ `<span style="color:#ccc;margin:0 2px;">/</span>`
				+ `<span style="color:#888;font-size:12px;">${total_c}</span>`;

			// CGPA
			let cgpaHtml = `<span style="color:#ccc;">—</span>`;
			if (s.cgpa !== null && s.cgpa !== undefined && s.cgpa !== "") {
				const v = parseFloat(s.cgpa);
				const color = v >= 7.0 ? "#1a7a36" : v >= 5.0 ? "#b45309" : "#c84630";
				const bg    = v >= 7.0 ? "#e6f4ea" : v >= 5.0 ? "#fef3e6" : "#fdecea";
				cgpaHtml = `<span style="font-weight:700;color:${color};background:${bg};padding:3px 10px;border-radius:20px;font-size:12px;">${v.toFixed(2)}</span>`;
			}

			// Status pill
			const statusPill = s.student_status ? status_pill(s.student_status) : "";

			// Sub-info
			const subParts = [prog, batch ? `Batch ${batch}` : "", acYear].filter(Boolean);
			const subInfo = subParts.join(" · ");

			return `
				<tr data-student="${s.student}">
					<td style="padding:11px 14px;">
						<input type="checkbox" class="tm-row-check tm-checkbox" data-student="${s.student}" ${checked} />
					</td>
					<td>
						<div style="display:flex;align-items:flex-start;gap:10px;">
							${photoSrc}
							<div>
								<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
									<a href="/app/student-master/${s.student}" class="tm-student-link">${name}</a>
									${statusPill}
								</div>
								<div style="font-size:11px;color:#bbb;margin-top:1px;">${email}</div>
								${subInfo ? `<div style="font-size:11px;color:#888;margin-top:2px;">${subInfo}</div>` : ""}
							</div>
						</div>
					</td>
					<td>${pathwayHtml}</td>
					<td style="font-size:12px;color:#555;white-space:nowrap;">${regId}</td>
					<td style="text-align:center;">${credHtml}</td>
					<td style="text-align:center;">${cgpaHtml}</td>
					<td style="text-align:center;">${interactive_badge(s.interim_transcript, s.student, "Interim")}</td>
					<!-- FINAL column hidden: <td style="text-align:center;">\${interactive_badge(s.final_transcript, s.student, "Final")}</td> -->
				</tr>`;
		});

		tbody.html(rows.join(""));

		// Restore select-all state
		const total_rows = $(wrapper).find(".tm-row-check").length;
		const sel_rows   = $(wrapper).find(".tm-row-check:checked").length;
		$(wrapper).find("#tm-select-all")
			.prop("indeterminate", sel_rows > 0 && sel_rows < total_rows)
			.prop("checked", sel_rows === total_rows && total_rows > 0);
	}

	/**
	 * Returns an interactive HTML badge for a transcript status cell.
	 * - Empty/null → dashed "Generate" button
	 * - "Generated" → clickable green badge → downloads transcript
	 * - "Revoked"   → clickable red badge → re-generates
	 */
	function interactive_badge(status, student, type) {
		const sid = frappe.utils.escape_html(student);
		if (!status) {
			return `<button class="tm-gen-badge tm-inline-gen"
				data-student="${sid}" data-type="${type}"
				title="${__("Click to generate {0} transcript", [type])}">
				+ ${__("Generate")}
			</button>`;
		}
		const s = status.toLowerCase();
		if (s === "generated") {
			return `<button class="tm-badge tm-badge-generated tm-inline-dl"
				data-student="${sid}" data-type="${type}"
				title="${__("Click to download {0} transcript", [type])}">
				<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24"
					fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
					<polyline points="20 6 9 17 4 12"/>
				</svg>
				${__("Generated")}
			</button>`;
		}
		if (s === "revoked") {
			return `<button class="tm-badge tm-badge-revoked tm-inline-gen"
				data-student="${sid}" data-type="${type}"
				title="${__("Click to re-generate {0} transcript", [type])}">
				<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24"
					fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
					<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
				</svg>
				${__("Revoked")}
			</button>`;
		}
		return `<span class="tm-badge tm-badge-pending">${frappe.utils.escape_html(status)}</span>`;
	}

	function status_pill(status) {
		const s   = (status || "").toLowerCase();
		const cls = {
			active:    "tm-status-active",
			inactive:  "tm-status-inactive",
			graduated: "tm-status-graduated",
			dropped:   "tm-status-dropped",
			alumni:    "tm-status-alumni",
			dormant:   "tm-status-dormant",
		}[s] || "tm-status-inactive";
		return `<span class="tm-status-pill ${cls}">${frappe.utils.escape_html(status)}</span>`;
	}

	function render_pagination() {
		const total_pages = Math.ceil(state.total / state.page_length) || 1;
		const from = state.total ? (state.page - 1) * state.page_length + 1 : 0;
		const to   = Math.min(state.page * state.page_length, state.total);

		// Info text (bottom-left, DataTables style)
		$(wrapper).find("#tm-page-info").text(
			state.total
				? `${__("Showing")} ${from} ${__("to")} ${to} ${__("of")} ${state.total} ${__("entries")}`
				: __("No entries found")
		);

		// Page number buttons (bottom-right)
		const controls = $(wrapper).find("#tm-page-controls");
		controls.empty();

		// Previous button
		const prev = $(`<button class="tm-page-btn"${state.page <= 1 ? " disabled" : ""}>‹ ${__("Previous")}</button>`);
		prev.on("click", function () { if (state.page > 1) { state.page--; load_students(); } });
		controls.append(prev);

		// Determine visible page window (max 5 pages shown)
		const win = 5;
		let start = Math.max(1, state.page - Math.floor(win / 2));
		let end   = Math.min(total_pages, start + win - 1);
		if (end - start < win - 1) start = Math.max(1, end - win + 1);

		if (start > 1) {
			const b1 = $(`<button class="tm-page-num">1</button>`);
			b1.on("click", function () { state.page = 1; load_students(); });
			controls.append(b1);
			if (start > 2) controls.append(`<span class="tm-page-ellipsis">…</span>`);
		}

		for (let i = start; i <= end; i++) {
			const pg  = i;
			const btn = $(`<button class="tm-page-num${i === state.page ? " active" : ""}">${i}</button>`);
			btn.on("click", function () { state.page = pg; load_students(); });
			controls.append(btn);
		}

		if (end < total_pages) {
			if (end < total_pages - 1) controls.append(`<span class="tm-page-ellipsis">…</span>`);
			const blast = $(`<button class="tm-page-num">${total_pages}</button>`);
			blast.on("click", function () { state.page = total_pages; load_students(); });
			controls.append(blast);
		}

		// Next button
		const next = $(`<button class="tm-page-btn"${state.page >= total_pages ? " disabled" : ""}>${__("Next")} ›</button>`);
		next.on("click", function () { if (state.page < total_pages) { state.page++; load_students(); } });
		controls.append(next);
	}

	// Filter key → select element ID map
	const FILTER_KEY_TO_ID = {
		programme:      "tm-f-programme",
		department:     "tm-f-department",
		course:         "tm-f-course",
		academic_year:  "tm-f-academic-year",
		batch:          "tm-f-batch",
		student_status: "tm-f-status",
	};

	function get_filter_label(key, value) {
		if (!value) return null;
		const prefix = {
			programme:      __("Programme"),
			department:     __("Department"),
			course:         __("Course"),
			academic_year:  __("Year"),
			batch:          __("Batch"),
			student_status: __("Status"),
		}[key] || key;
		let display = value;
		if (key === "programme" && state._prog_labels[value]) display = state._prog_labels[value];
		if (key === "department" && state._dept_labels[value]) display = state._dept_labels[value];
		return `${prefix}: ${display}`;
	}

	function render_active_tags() {
		const container = $(wrapper).find("#tm-active-tags");
		container.empty();
		const keys = ["programme", "department", "course", "academic_year", "batch", "student_status"];
		keys.forEach(key => {
			const value = state[key];
			const label = get_filter_label(key, value);
			if (!label) return;
			const tag = $(`
				<span class="tm-tag">
					${frappe.utils.escape_html(label)}
					<button class="tm-tag-remove" data-key="${key}" title="${__("Remove filter")}">
						<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
							<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
						</svg>
					</button>
				</span>`);
			tag.find("button").on("click", function () {
				const k = $(this).data("key");
				state[k] = "";
				const sid = FILTER_KEY_TO_ID[k];
				if (sid) $(wrapper).find(`#${sid}`).val("");
				render_active_tags();
				update_filter_count_badge();
				state.page = 1;
				load_students();
			});
			container.append(tag);
		});
	}

	function update_filter_count_badge() {
		const keys = ["programme", "department", "course", "academic_year", "batch", "student_status"];
		const active = keys.filter(k => !!state[k]).length;
		const badge = $(wrapper).find("#tm-filter-count");
		if (active > 0) {
			badge.text(active).show();
		} else {
			badge.hide();
		}
	}

	function update_sort_indicators() {
		$(wrapper).find(".tm-sort-icon").removeClass("asc desc").text("↕");
		const ind = $(wrapper).find(`.tm-sort-icon[data-col="${state.sort_by}"]`);
		if (state.sort_order === "asc") {
			ind.addClass("asc").text("↑");
		} else {
			ind.addClass("desc").text("↓");
		}
	}

	function get_selected_students() {
		return [...state.selected];
	}

	function do_generate(students, type) {
		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.generate_transcript",
			args: {
				students:        JSON.stringify(students),
				transcript_type: type,
			},
			freeze: true,
			freeze_message: __("Generating transcripts..."),
			callback: function (r) {
				if (!r.message) return;
				const ok  = r.message.filter(x => x.success).length;
				const err = r.message.filter(x => !x.success).length;
				frappe.show_alert({
					message:   ok + " " + __("transcript(s) generated.") + (err ? "  " + err + " " + __("failed.") : ""),
					indicator: err ? "orange" : "green",
				}, 5);
				state.selected.clear();
				update_selection_bar();
				load_students();
			}
		});
	}

	function handle_download(type) {
		const students = get_selected_students();
		if (!students.length) {
			frappe.msgprint(__("Please select a student to download the transcript."));
			return;
		}
		if (students.length > 1) {
			frappe.msgprint(__("Please select only one student at a time for download."));
			return;
		}
		handle_download_single(students[0], type);
	}

	function handle_download_single(student, type) {
		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.download_transcript",
			args: { student, transcript_type: type },
			callback: function (r) {
				if (!r.message) return;
				const info = r.message;
				if (info.print_url) {
					window.open(info.print_url, "_blank");
				} else {
					frappe.msgprint({
						title:   __("Transcript Info"),
						message: `${__("Type")}: ${info.transcript_type}<br>${__("Status")}: ${info.status}<br>${__("Generated on")}: ${info.generation_date}`,
					});
				}
			},
			error: function () {
				frappe.msgprint({
					title:     __("Transcript Not Found"),
					message:   __("No {0} transcript exists for this student. Please generate it first.", [type]),
					indicator: "orange",
				});
			}
		});
	}

	function handle_compact_download() {
		const students = get_selected_students();
		if (!students.length) {
			frappe.msgprint(__("Please select a student to download the compact transcript."));
			return;
		}
		if (students.length > 1) {
			frappe.msgprint(__("Please select only one student at a time for compact transcript download."));
			return;
		}

		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.download_compact_transcript",
			args: { student: students[0] },
			callback: function (r) {
				if (r.message && r.message.print_url) {
					window.open(r.message.print_url, "_blank");
				}
			},
			error: function (r) {
				const msg = (r && r.message) || __("No approved Final or Interim Transcript Request found for this student. The student must submit and get a transcript request approved before downloading the compact transcript.");
				frappe.msgprint({
					title: __("Compact Transcript"),
					message: msg,
					indicator: "orange",
				});
			}
		});
	}

	// ── Requests tab: functions ─────────────────────────────────────────────────

	const REQ_STATUS_COLORS = {
		"Payment Pending": "#c8632f",
		"Submitted":       "#3b5bdb",
		"Under Review":    "#b45309",
		"Approved":        "#0f8a5f",
		"Generated":       "#1a7a36",
		"Delivered":       "#1a7a36",
		"Rejected":        "#c84630",
		"Cancelled":       "#888",
	};

	const REQ_STATUS_PILL_CLASS = {
		"Payment Pending": "tm-status-dropped",
		"Submitted":       "tm-status-active",
		"Under Review":    "tm-status-dormant",
		"Approved":        "tm-status-graduated",
		"Generated":       "tm-status-graduated",
		"Delivered":       "tm-status-graduated",
		"Rejected":        "tm-status-dropped",
		"Cancelled":       "tm-status-inactive",
	};

	function req_status_pill(status) {
		const cls = REQ_STATUS_PILL_CLASS[status] || "tm-status-inactive";
		return `<span class="tm-status-pill ${cls}">${frappe.utils.escape_html(status || "")}</span>`;
	}

	function req_payment_pill(status) {
		const map = {
			"Paid":             "tm-status-graduated",
			"Pending":          "tm-status-dropped",
			"Payment Initiated":"tm-status-dormant",
			"Authorized":       "tm-status-dormant",
			"Payment Failed":   "tm-status-dropped",
			"Payment Cancelled":"tm-status-inactive",
			"Refunded":         "tm-status-alumni",
			"Not Required":     "tm-status-inactive",
		};
		const cls = map[status] || "tm-status-inactive";
		return `<span class="tm-status-pill ${cls}">${frappe.utils.escape_html(status || "")}</span>`;
	}

	function load_request_stats() {
		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.get_request_stats",
			callback: function (r) {
				const s = r.message || {};
				$(wrapper).find("#tm-rstat-total").text(s.total || 0);
				$(wrapper).find("#tm-rstat-review").text(s.under_review || 0);
				$(wrapper).find("#tm-rstat-generated").text(s.generated || 0);
				$(wrapper).find("#tm-rstat-rejected").text(s.rejected || 0);
				$(wrapper).find("#tm-rstat-revenue").text(
					s.revenue ? format_currency(s.revenue) : format_currency(0)
				);
				render_req_chart(s);
			},
		});
	}

	function format_currency(amount) {
		try {
			return frappe.utils.fmt_money(amount || 0, {}, "INR");
		} catch (e) {
			return "₹" + (Math.round((amount || 0) * 100) / 100).toLocaleString();
		}
	}

	function render_req_chart(s) {
		const rows = [
			{ label: __("Payment Pending"), value: s.payment_pending || 0, color: REQ_STATUS_COLORS["Payment Pending"] },
			{ label: __("Under Review"),    value: s.under_review || 0,    color: REQ_STATUS_COLORS["Under Review"] },
			{ label: __("Approved"),        value: s.approved || 0,        color: REQ_STATUS_COLORS["Approved"] },
			{ label: __("Generated"),       value: s.generated || 0,       color: REQ_STATUS_COLORS["Generated"] },
			{ label: __("Rejected"),        value: s.rejected || 0,        color: REQ_STATUS_COLORS["Rejected"] },
		];
		const max = Math.max(1, ...rows.map(r => r.value));
		const container = $(wrapper).find("#tm-req-chart");
		container.html(rows.map(r => `
			<div class="tm-req-chart-row">
				<span class="tm-req-chart-label">${frappe.utils.escape_html(r.label)}</span>
				<div class="tm-req-chart-track">
					<div class="tm-req-chart-fill" style="width:${(r.value / max) * 100}%; background:${r.color};"></div>
				</div>
				<span class="tm-req-chart-count">${r.value}</span>
			</div>
		`).join(""));
	}

	function load_requests() {
		if (req_state.loading) return;
		req_state.loading = true;
		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.get_requests",
			args: {
				search:          req_state.search,
				status:          req_state.status,
				transcript_type: req_state.transcript_type,
				payment_status:  req_state.payment_status,
				page:            req_state.page,
				page_length:     req_state.page_length,
			},
			callback: function (r) {
				req_state.loading = false;
				const data = r.message || { requests: [], total: 0 };
				req_state.rows  = data.requests || [];
				req_state.total = data.total || 0;
				render_requests_table(req_state.rows);
				render_requests_pagination();
				$(wrapper).find("#tm-req-count-badge").text(
					req_state.total ? __("{0} requests", [req_state.total]) : ""
				);
			},
			error: function () {
				req_state.loading = false;
			},
		});
	}

	function render_requests_table(rows) {
		const tbody = $(wrapper).find("#tm-req-tbody");
		if (!rows.length) {
			tbody.html(`
				<tr><td colspan="9" style="text-align:center; padding:48px; color:#aaa;">
					${__("No transcript requests found.")}
				</td></tr>
			`);
			return;
		}

		const html = rows.map(row => {
			const checked = req_state.selected.has(row.name) ? "checked" : "";
			const name = frappe.utils.escape_html(row.name);
			const sname = frappe.utils.escape_html(row.student_name || row.student || "");
			const fee = row.payment_required ? format_currency(row.fee_amount || 0) : "—";
			const requested = row.requested_on
				? frappe.datetime.str_to_user(row.requested_on)
				: "—";
			return `
				<tr>
					<td style="padding:9px 12px;">
						<input type="checkbox" class="tm-checkbox tm-req-row-check" data-name="${name}" ${checked} />
					</td>
					<td>
						<a href="/app/transcript-request/${encodeURIComponent(row.name)}" target="_blank"
							style="color:#c84630; font-weight:600; text-decoration:none;">${name}</a>
					</td>
					<td>${sname}<br><span style="color:#999; font-size:11px;">${frappe.utils.escape_html(row.registration_id || "")}</span></td>
					<td>${frappe.utils.escape_html(transcript_type_label(row.transcript_type) || "")}</td>
					<td>${req_status_pill(row.status)}</td>
					<td>${req_payment_pill(row.payment_status)}</td>
					<td style="text-align:right;">${fee}</td>
					<td>${requested}</td>
					<td style="text-align:center;">
						<button class="tm-pay-btn" data-name="${name}" title="${__("View payment details")}">
							<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
								fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>
							</svg>
						</button>
					</td>
				</tr>
			`;
		}).join("");
		tbody.html(html);

		const total = $(wrapper).find(".tm-req-row-check").length;
		const sel   = $(wrapper).find(".tm-req-row-check:checked").length;
		$(wrapper).find("#tm-req-select-all")
			.prop("indeterminate", sel > 0 && sel < total)
			.prop("checked", sel === total && total > 0);
	}

	function render_requests_pagination() {
		const total_pages = Math.ceil(req_state.total / req_state.page_length) || 1;
		const from = req_state.total ? (req_state.page - 1) * req_state.page_length + 1 : 0;
		const to   = Math.min(req_state.page * req_state.page_length, req_state.total);

		$(wrapper).find("#tm-req-page-info").text(
			req_state.total
				? `${__("Showing")} ${from} ${__("to")} ${to} ${__("of")} ${req_state.total} ${__("entries")}`
				: __("No entries found")
		);

		const controls = $(wrapper).find("#tm-req-page-controls");
		controls.empty();

		const prev = $(`<button class="tm-page-btn"${req_state.page <= 1 ? " disabled" : ""}>‹ ${__("Previous")}</button>`);
		prev.on("click", function () { if (req_state.page > 1) { req_state.page--; load_requests(); } });
		controls.append(prev);

		const win = 5;
		let start = Math.max(1, req_state.page - Math.floor(win / 2));
		let end   = Math.min(total_pages, start + win - 1);
		if (end - start < win - 1) start = Math.max(1, end - win + 1);

		if (start > 1) {
			const b1 = $(`<button class="tm-page-num">1</button>`);
			b1.on("click", function () { req_state.page = 1; load_requests(); });
			controls.append(b1);
			if (start > 2) controls.append(`<span class="tm-page-ellipsis">…</span>`);
		}
		for (let i = start; i <= end; i++) {
			const pg  = i;
			const btn = $(`<button class="tm-page-num${i === req_state.page ? " active" : ""}">${i}</button>`);
			btn.on("click", function () { req_state.page = pg; load_requests(); });
			controls.append(btn);
		}
		if (end < total_pages) {
			if (end < total_pages - 1) controls.append(`<span class="tm-page-ellipsis">…</span>`);
			const blast = $(`<button class="tm-page-num">${total_pages}</button>`);
			blast.on("click", function () { req_state.page = total_pages; load_requests(); });
			controls.append(blast);
		}
		const next = $(`<button class="tm-page-btn"${req_state.page >= total_pages ? " disabled" : ""}>${__("Next")} ›</button>`);
		next.on("click", function () { if (req_state.page < total_pages) { req_state.page++; load_requests(); } });
		controls.append(next);
	}

	function update_req_selection_bar() {
		const count = req_state.selected.size;
		const bar   = $(wrapper).find("#tm-req-sel-bar");
		$(wrapper).find("#tm-req-sel-count").text(count);
		if (count > 0) {
			bar.addClass("tm-sel-bar--visible");
		} else {
			bar.removeClass("tm-sel-bar--visible");
		}
	}

	function show_payment_details(name) {
		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.get_payment_details",
			args: { request_name: name },
			freeze: true,
			callback: function (r) {
				if (!r.message) return;
				const d = r.message;
				const gw = d.gateway_response
					? (typeof d.gateway_response === "string" ? d.gateway_response : JSON.stringify(d.gateway_response, null, 2))
					: null;

				const dialog = new frappe.ui.Dialog({
					title: __("Payment Details — {0}", [d.request_name]),
					fields: [{ fieldname: "html", fieldtype: "HTML" }],
				});

				dialog.fields_dict.html.$wrapper.html(`
					<div class="tm-pay-detail-row">
						<span class="tm-pay-detail-label">${__("Student")}</span>
						<span class="tm-pay-detail-value">${frappe.utils.escape_html(d.student_name || d.student || "")}</span>
					</div>
					<div class="tm-pay-detail-row">
						<span class="tm-pay-detail-label">${__("Payment Required")}</span>
						<span class="tm-pay-detail-value">${d.payment_required ? __("Yes") : __("No")}</span>
					</div>
					<div class="tm-pay-detail-row">
						<span class="tm-pay-detail-label">${__("Fee Amount")}</span>
						<span class="tm-pay-detail-value">${format_currency(d.fee_amount || 0)}</span>
					</div>
					<div class="tm-pay-detail-row">
						<span class="tm-pay-detail-label">${__("Payment Status")}</span>
						<span class="tm-pay-detail-value">${req_payment_pill(d.payment_status)}</span>
					</div>
					<div class="tm-pay-detail-row">
						<span class="tm-pay-detail-label">${__("Razorpay Status")}</span>
						<span class="tm-pay-detail-value">${frappe.utils.escape_html(d.razorpay_payment_status || "—")}</span>
					</div>
					<div class="tm-pay-detail-row">
						<span class="tm-pay-detail-label">${__("Razorpay Order ID")}</span>
						<span class="tm-pay-detail-value">${frappe.utils.escape_html(d.razorpay_order_id || "—")}</span>
					</div>
					<div class="tm-pay-detail-row">
						<span class="tm-pay-detail-label">${__("Payment Reference")}</span>
						<span class="tm-pay-detail-value">${frappe.utils.escape_html(d.payment_reference || "—")}</span>
					</div>
					<div class="tm-pay-detail-row">
						<span class="tm-pay-detail-label">${__("Payment Date")}</span>
						<span class="tm-pay-detail-value">${d.payment_date ? frappe.datetime.str_to_user(d.payment_date) : "—"}</span>
					</div>
					${d.payment_failure_reason ? `
					<div class="tm-pay-detail-row">
						<span class="tm-pay-detail-label">${__("Failure Reason")}</span>
						<span class="tm-pay-detail-value" style="color:#c0392b;">${frappe.utils.escape_html(d.payment_failure_reason)}</span>
					</div>` : ""}
					${gw ? `<div class="tm-pay-detail-label" style="margin-top:12px;">${__("Gateway Response")}</div>
						<div class="tm-pay-gateway-json">${frappe.utils.escape_html(gw)}</div>` : ""}
				`);
				dialog.show();
			},
		});
	}

	function bulk_approve(names) {
		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.bulk_approve_requests",
			args: { request_names: JSON.stringify(names) },
			freeze: true,
			freeze_message: __("Approving & generating transcripts..."),
			callback: function (r) {
				if (!r.message) return;
				const { succeeded, failed, results } = r.message;
				frappe.show_alert({
					message: `${succeeded} ${__("approved.")}` + (failed ? `  ${failed} ${__("failed.")}` : ""),
					indicator: failed ? "orange" : "green",
				}, 6);
				if (failed) {
					const errs = results.filter(x => !x.success)
						.map(x => `${x.name}: ${frappe.utils.escape_html(x.error || "")}`).join("<br>");
					frappe.msgprint({ title: __("Some requests failed"), message: errs, indicator: "orange" });
				}
				req_state.selected.clear();
				update_req_selection_bar();
				load_request_stats();
				load_requests();
			},
			error: function () {
				frappe.show_alert({
					message: __("Approval request failed. Please try again."),
					indicator: "red",
				}, 6);
			},
		});
	}

	function bulk_reject(names, reason) {
		frappe.call({
			method: "slcm.slcm.page.transcript_management_page.transcript_management_page.bulk_reject_requests",
			args: { request_names: JSON.stringify(names), rejection_reason: reason },
			freeze: true,
			freeze_message: __("Rejecting requests..."),
			callback: function (r) {
				if (!r.message) return;
				const { succeeded, failed, results } = r.message;
				frappe.show_alert({
					message: `${succeeded} ${__("rejected.")}` + (failed ? `  ${failed} ${__("failed.")}` : ""),
					indicator: failed ? "orange" : "green",
				}, 6);
				if (failed) {
					const errs = results.filter(x => !x.success)
						.map(x => `${x.name}: ${frappe.utils.escape_html(x.error || "")}`).join("<br>");
					frappe.msgprint({ title: __("Some requests failed"), message: errs, indicator: "orange" });
				}
				req_state.selected.clear();
				update_req_selection_bar();
				load_request_stats();
				load_requests();
			},
			error: function () {
				frappe.show_alert({
					message: __("Rejection request failed. Please try again."),
					indicator: "red",
				}, 6);
			},
		});
	}

	// ── Initial Load ───────────────────────────────────────────────────────────
	update_sort_indicators();
	load_filter_options();
	load_students();

	// Deep-link support: /app/transcript-management-page/requests opens directly
	// on the Requests tab (used by the "Transcript Requests Queue" workspace shortcut).
	const route = frappe.get_route();
	if (route && route[1] === "requests") {
		$(wrapper).find(`.tm-tab-btn[data-tab="requests"]`).trigger("click");
	}

};
