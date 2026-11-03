frappe.pages['exam-barcode-sheet'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Exam Barcode Sheet',
		single_column: true
	});
	$(wrapper).addClass('er-theme');
	if (!document.getElementById('er-theme-font')) {
		$('head').append(
			'<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">'
		);
	}
	frappe.require('/assets/slcm/css/exam_results_theme.css');
	new ExamBarcodeSheet(wrapper);
};

class ExamBarcodeSheet {
	constructor(wrapper) {
		this.$body = $(wrapper).find('.page-content');
		this.$body.css({ padding: '0', background: '#f6f4f4' });
		this.exam_plan = null;
		this.courses   = [];
		this.$toolbar  = null;
		this._inject_styles();
		this._build_ui();
	}

	// ── Global styles ──────────────────────────────────────────────────────────
	_inject_styles() {
		if ($('#eas-styles').length) return;
		$(`<style id="eas-styles">
		/* ─── Base ─────────────────────────────────────────────────────── */
		.eas-page { padding: 20px 24px; font-family: var(--er-font, Georgia, serif); }
		.eas-page button, .eas-page input, .eas-page select { font-family: inherit; }

		/* ─── Filter / header bar ───────────────────────────────────────── */
		.eas-filter {
			display:flex; align-items:center; gap:16px; flex-wrap:wrap;
			padding:18px 24px; margin-bottom:20px;
			background:#fff; border-radius:14px;
			border:1px solid #e2e8f0; border-left:4px solid #920C24;
			box-shadow:0 2px 8px rgba(15,23,42,.06);
		}
		.eas-filter-icon {
			width:44px; height:44px; border-radius:11px; flex-shrink:0;
			background:linear-gradient(135deg,#920C24,#920C24);
			display:flex; align-items:center; justify-content:center;
			color:#fff; font-size:18px;
			box-shadow:0 3px 10px rgba(146,12,36,.35);
		}
		.eas-filter-text .flt-sup {
			font-size:10px; font-weight:700; text-transform:uppercase;
			letter-spacing:.6px; color:#94a3b8;
		}
		.eas-filter-text .flt-title {
			font-size:15px; font-weight:700; color:#0f172a; line-height:1.2;
		}
		.eas-filter .eas-plan-wrap { flex:1; min-width:220px; max-width:360px; }
		.eas-load-btn {
			height:36px !important; padding:0 22px !important;
			font-size:13px !important; font-weight:600 !important;
			border-radius:9px !important; border:none !important;
			background:linear-gradient(135deg,#920C24,#920C24) !important;
			box-shadow:0 3px 10px rgba(146,12,36,.3) !important;
			transition:box-shadow .2s,transform .1s !important;
		}
		.eas-load-btn:hover:not(:disabled) {
			box-shadow:0 5px 14px rgba(146,12,36,.4) !important;
			transform:translateY(-1px) !important;
		}

		/* ─── Stat cards ────────────────────────────────────────────────── */
		.eas-stats-row {
			display:grid; grid-template-columns:repeat(4,1fr);
			gap:14px; margin-bottom:20px;
		}
		@media(max-width:900px){ .eas-stats-row { grid-template-columns:repeat(2,1fr); } }
		@media(max-width:560px){ .eas-stats-row { grid-template-columns:1fr; } }

		.eas-stat-card {
			background:#fff; border:1px solid #e2e8f0; border-radius:14px;
			padding:18px 20px 16px; position:relative; overflow:hidden;
			box-shadow:0 2px 8px rgba(15,23,42,.05);
		}
		.eas-stat-card::before {
			content:''; position:absolute; top:0; left:0; right:0;
			height:3px; border-radius:14px 14px 0 0;
		}
		.sc-plan::before   { background:linear-gradient(90deg,#920C24,#920C24); }
		.sc-count::before  { background:linear-gradient(90deg,#920C24,#C4566A); }
		.sc-bc::before     { background:linear-gradient(90deg,#059669,#34d399); }
		.sc-status::before { background:linear-gradient(90deg,#f59e0b,#fbbf24); }
		.sc-status.all-ready::before { background:linear-gradient(90deg,#059669,#34d399); }

		.eas-stat-icon {
			width:40px; height:40px; border-radius:10px; float:right;
			display:flex; align-items:center; justify-content:center;
			font-size:17px; margin:-2px -4px 6px 8px;
		}
		.sc-plan  .eas-stat-icon { background:#FBEEF0; color:#920C24; }
		.sc-count .eas-stat-icon { background:#FBEEF0; color:#920C24; }
		.sc-bc    .eas-stat-icon { background:#dcfce7; color:#059669; }
		.sc-status .eas-stat-icon { background:#fef3c7; color:#d97706; }
		.sc-status.all-ready .eas-stat-icon { background:#dcfce7; color:#059669; }

		.eas-stat-label {
			font-size:10.5px; font-weight:700; text-transform:uppercase;
			letter-spacing:.6px; color:#94a3b8; margin-bottom:7px;
		}
		.eas-stat-val { font-size:28px; font-weight:800; color:#0f172a; line-height:1; }
		.eas-stat-val.sv-text { font-size:14px; font-weight:700; margin-top:5px; }
		.eas-stat-sub { font-size:11.5px; color:#94a3b8; margin-top:4px; }

		/* ─── Action bar ─────────────────────────────────────────────────── */
		.eas-actions {
			display:flex; align-items:center; gap:8px; flex-wrap:wrap;
			padding:13px 20px; margin-bottom:20px;
			background:#fff; border-radius:12px;
			border:1px solid #e2e8f0;
			box-shadow:0 2px 6px rgba(15,23,42,.05);
		}
		.eas-actions .divider { width:1px; height:24px; background:#e2e8f0; margin:0 4px; }
		.eas-actions .act-label {
			font-size:11px; font-weight:700; text-transform:uppercase;
			letter-spacing:.5px; color:#94a3b8;
		}
		.eas-btn-gen-all {
			height:34px; padding:0 18px; font-size:12.5px; font-weight:600;
			border-radius:8px; border:none; cursor:pointer;
			display:inline-flex; align-items:center; gap:7px;
			background:linear-gradient(135deg,#6E091B,#920C24); color:#fff;
			box-shadow:0 2px 8px rgba(146,12,36,.3);
			transition:box-shadow .2s,transform .1s;
		}
		.eas-btn-gen-all:hover {
			box-shadow:0 4px 12px rgba(146,12,36,.4); transform:translateY(-1px);
		}
		.eas-btn-dl-date {
			height:34px; padding:0 16px; font-size:12.5px; font-weight:600;
			border-radius:8px; border:none; cursor:pointer;
			display:inline-flex; align-items:center; gap:7px;
			background:linear-gradient(135deg,#920C24,#920C24); color:#fff;
			box-shadow:0 2px 8px rgba(146,12,36,.3);
			transition:box-shadow .2s,transform .1s;
		}
		.eas-btn-dl-date:hover:not(:disabled) {
			box-shadow:0 4px 12px rgba(146,12,36,.4); transform:translateY(-1px);
		}
		.eas-btn-dl-course {
			height:34px; padding:0 16px; font-size:12.5px; font-weight:600;
			border-radius:8px; cursor:pointer;
			display:inline-flex; align-items:center; gap:7px;
			background:#fff; color:#920C24; border:1.5px solid #E8B4BE;
			transition:background .15s,border-color .15s,transform .1s;
		}
		.eas-btn-dl-course:hover:not(:disabled) {
			background:#FBEEF0; border-color:#C4566A; transform:translateY(-1px);
		}
		.eas-btn-gen-all:disabled,
		.eas-btn-dl-date:disabled,
		.eas-btn-dl-course:disabled { opacity:.45; cursor:not-allowed; transform:none; }

		/* ─── Date section ───────────────────────────────────────────────── */
		.eas-date-section { margin-bottom:24px; }
		.eas-date-hdr {
			display:flex; align-items:center; gap:12px;
			padding:12px 18px; margin-bottom:10px;
			background:#fff; border:1px solid #E8B4BE;
			border-radius:12px;
			box-shadow:0 1px 4px rgba(146,12,36,.06);
		}
		.eas-date-icon {
			width:38px; height:38px; border-radius:9px; flex-shrink:0;
			background:linear-gradient(135deg,#920C24,#920C24);
			display:flex; align-items:center; justify-content:center;
			color:#fff; font-size:14px;
			box-shadow:0 2px 6px rgba(146,12,36,.3);
		}
		.eas-date-text .dt-sup {
			font-size:10px; font-weight:700; text-transform:uppercase;
			letter-spacing:.6px; color:#64748b;
		}
		.eas-date-text .dt-val { font-size:15px; font-weight:700; color:#920C24; }
		.eas-date-pill {
			background:#920C24; color:#fff; border-radius:20px;
			padding:3px 13px; font-size:11px; font-weight:700; margin-left:auto;
		}

		/* ─── Course table ───────────────────────────────────────────────── */
		.eas-tbl-wrap {
			border-radius:12px; overflow:hidden;
			border:1px solid #e2e8f0;
			box-shadow:0 2px 8px rgba(15,23,42,.06);
		}
		.eas-tbl { width:100%; margin:0; border-collapse:collapse; font-size:13px; }
		.eas-tbl thead th {
			background:#f8fafc; padding:11px 14px;
			font-size:10px; font-weight:700; text-transform:uppercase;
			letter-spacing:.5px; color:#64748b; white-space:nowrap;
			border-bottom:1px solid #e2e8f0; border-top:none;
		}
		.eas-tbl tbody tr { transition:background .12s; }
		.eas-tbl tbody tr.eas-course-tr:hover { background:#FBEEF0; }
		.eas-tbl tbody td {
			padding:13px 14px; vertical-align:middle;
			border-bottom:1px solid #f6f4f4; border-top:none;
		}
		.eas-tbl tbody tr:last-child td { border-bottom:none; }

		/* Course name cell */
		.eas-cname { display:flex; align-items:center; gap:10px; }
		.eas-course-dot {
			width:10px; height:10px; border-radius:50%; flex-shrink:0;
			background:linear-gradient(135deg,#920C24,#920C24);
			box-shadow:0 0 0 3px #F5D9DE;
		}
		.eas-clink {
			color:#920C24; cursor:pointer; text-decoration:none;
			font-weight:600; font-size:13.5px;
		}
		.eas-clink:hover { color:#920C24; text-decoration:underline; }
		.eas-chevron {
			font-size:9px; color:#c0c8d8; margin-left:4px;
			transition:transform .2s ease; display:inline-block;
		}
		.eas-code {
			font-family:Consolas,monospace; font-size:11.5px; color:#64748b;
			background:#f6f4f4; border:1px solid #e2e8f0;
			padding:2px 8px; border-radius:5px;
		}

		/* Status badges */
		.eas-status-ready {
			display:inline-flex; align-items:center; gap:5px;
			background:#dcfce7; color:#15803d; border:1px solid #bbf7d0;
			border-radius:20px; padding:3px 11px; font-size:11.5px; font-weight:700;
		}
		.eas-status-partial {
			display:inline-flex; align-items:center; gap:5px;
			background:#fef9c3; color:#854d0e; border:1px solid #fde68a;
			border-radius:20px; padding:3px 11px; font-size:11.5px; font-weight:700;
		}
		.eas-status-none {
			display:inline-flex; align-items:center; gap:5px;
			background:#f6f4f4; color:#94a3b8; border:1px solid #e2e8f0;
			border-radius:20px; padding:3px 11px; font-size:11.5px; font-weight:600;
		}

		/* Row action buttons */
		.eas-row-acts { display:flex; gap:6px; justify-content:flex-end; }
		.eas-btn-gen-row {
			height:30px; padding:0 11px; font-size:11.5px; font-weight:600;
			border-radius:7px; border:1.5px solid #e2e8f0; background:#fff;
			color:#374151; cursor:pointer;
			display:inline-flex; align-items:center; gap:4px;
			transition:border-color .12s,background .12s;
		}
		.eas-btn-gen-row:hover { background:#f8fafc; border-color:#cbd5e1; }
		.eas-btn-dl-row {
			height:30px; padding:0 11px; font-size:11.5px; font-weight:600;
			border-radius:7px; border:none;
			background:linear-gradient(135deg,#920C24,#920C24); color:#fff; cursor:pointer;
			display:inline-flex; align-items:center; gap:4px;
			box-shadow:0 2px 6px rgba(146,12,36,.25);
			transition:box-shadow .15s,transform .1s;
		}
		.eas-btn-dl-row:hover:not(:disabled) {
			box-shadow:0 4px 10px rgba(146,12,36,.35); transform:translateY(-1px);
		}
		.eas-btn-dl-row:disabled { opacity:.4; cursor:not-allowed; transform:none; }

		/* ─── Student detail panel ───────────────────────────────────────── */
		.eas-detail-row td { padding:0 !important; border:none !important; }
		.eas-panel { background:#f6f4f4; border-top:2px solid #E8B4BE; }
		.eas-panel-inner { padding:18px 20px 20px; }

		/* Panel header */
		.eas-panel-header {
			display:flex; align-items:center; justify-content:space-between;
			flex-wrap:wrap; gap:14px; margin-bottom:0;
			padding:16px 18px; background:#fff; border-radius:10px;
			border:1px solid #e2e8f0; border-left:4px solid #920C24;
			box-shadow:0 1px 4px rgba(146,12,36,.06);
		}
		.eas-panel-left { display:flex; align-items:center; gap:14px; }
		.eas-panel-course-icon {
			width:46px; height:46px; border-radius:12px; flex-shrink:0;
			background:linear-gradient(135deg,#920C24,#920C24);
			display:flex; align-items:center; justify-content:center;
			color:#fff; font-size:20px;
			box-shadow:0 3px 10px rgba(146,12,36,.3);
		}
		.eas-panel-course-name { font-size:15px; font-weight:700; color:#0f172a; }
		.eas-panel-course-code {
			font-family:Consolas,monospace; font-size:11.5px;
			color:#64748b; margin-top:2px;
		}

		/* Panel stats */
		.eas-panel-stats { display:flex; align-items:center; gap:0; }
		.eas-pstat {
			text-align:center; padding:6px 20px;
			border-right:1px solid #e2e8f0;
		}
		.eas-pstat:last-child { border-right:none; }
		.eas-pstat-val { font-size:22px; font-weight:800; line-height:1; }
		.pv-total { color:#0f172a; }
		.pv-done  { color:#059669; }
		.pv-pend  { color:#d97706; }
		.eas-pstat-label {
			font-size:9.5px; font-weight:700; text-transform:uppercase;
			letter-spacing:.5px; color:#94a3b8; margin-top:3px;
		}

		/* Progress bar */
		.eas-prog-row { display:flex; align-items:center; gap:10px; margin-top:10px; }
		.eas-prog {
			height:6px; background:#e2e8f0; border-radius:3px;
			overflow:hidden; width:160px;
		}
		.eas-prog-fill { height:100%; border-radius:3px; transition:width .5s ease; }
		.eas-prog-pct { font-size:11.5px; font-weight:700; color:#64748b; }

		/* ─── Student table toolbar ──────────────────────────────────────── */
		.eas-stbl-toolbar {
			display:flex; align-items:center; gap:10px;
			margin-top:18px; margin-bottom:10px; flex-wrap:wrap;
			padding:10px 14px; background:#fff; border-radius:10px;
			border:1px solid #e2e8f0;
		}
		.eas-search-wrap {
			position:relative; flex:1; min-width:180px; max-width:280px;
		}
		.eas-search-wrap .eas-search-ico {
			position:absolute; left:10px; top:50%; transform:translateY(-50%);
			color:#94a3b8; font-size:12px; pointer-events:none;
		}
		.eas-stbl-search {
			width:100%; height:34px; font-size:12.5px; border-radius:8px;
			border:1.5px solid #e2e8f0; padding:0 10px 0 32px; background:#f8fafc;
			transition:border-color .15s,box-shadow .15s;
		}
		.eas-stbl-search:focus {
			outline:none; border-color:#C4566A; background:#fff;
			box-shadow:0 0 0 3px rgba(146,12,36,.1);
		}
		.eas-stbl-count {
			font-size:12px; color:#64748b; white-space:nowrap;
			background:#f6f4f4; padding:4px 10px; border-radius:20px;
			font-weight:600; border:1px solid #e2e8f0;
		}
		.eas-stbl-hint {
			margin-left:auto; font-size:11.5px; color:#94a3b8; white-space:nowrap;
			display:flex; align-items:center; gap:5px;
		}
		/* ─── Student data table ────────────────────────────────────────────── */
		.eas-stbl-wrap {
			border:1px solid #E8B4BE; border-radius:12px;
			overflow:hidden; max-height:420px; overflow-y:auto;
			box-shadow:0 4px 12px rgba(146,12,36,.08);
		}
		.eas-stbl-wrap::-webkit-scrollbar { width:6px; }
		.eas-stbl-wrap::-webkit-scrollbar-track { background:#f8fafc; }
		.eas-stbl-wrap::-webkit-scrollbar-thumb { background:#C4566A; border-radius:3px; }
		.eas-stbl-wrap::-webkit-scrollbar-thumb:hover { background:#C4566A; }

		.eas-stbl { width:100%; margin:0; border-collapse:separate; border-spacing:0; font-size:13px; }

		/* Sticky header — background must be on th, not tr, for sticky to paint correctly */
		.eas-stbl thead th {
			position:sticky; top:0; z-index:10;
			padding:13px 14px; font-size:10.5px; font-weight:700; text-transform:uppercase;
			letter-spacing:.7px; color:#fff; white-space:nowrap; user-select:none;
			background:linear-gradient(135deg,#920C24 0%,#6E091B 60%,#920C24 100%);
			border-bottom:2px solid rgba(255,255,255,.18); border-top:none;
			box-shadow:0 2px 6px rgba(146,12,36,.18);
		}
		.eas-stbl thead th.sortable { cursor:pointer; }
		.eas-stbl thead th.sortable:hover { background:linear-gradient(135deg,#6E091B,#6E091B,#6E091B); color:#fff; }
		.eas-stbl thead th .sort-ico {
			display:inline-flex; flex-direction:column; gap:2px;
			vertical-align:middle; margin-left:5px; opacity:.5;
		}
		.eas-stbl thead th.sort-asc  .sort-ico,
		.eas-stbl thead th.sort-desc .sort-ico { opacity:1; }
		.eas-stbl thead th .s-up,.eas-stbl thead th .s-dn {
			display:block; width:0; height:0;
			border-left:4px solid transparent; border-right:4px solid transparent;
		}
		.eas-stbl thead th .s-up { border-bottom:5px solid #fff; }
		.eas-stbl thead th .s-dn { border-top:5px solid #fff; }
		.eas-stbl thead th.sort-asc  .s-dn { opacity:.25; }
		.eas-stbl thead th.sort-desc .s-up { opacity:.25; }

		/* Body rows */
		.eas-stbl tbody tr.eas-stbl-student-row { cursor:pointer; transition:background .12s; }
		.eas-stbl tbody tr.eas-stbl-student-row:nth-child(odd) { background:#fff; }
		.eas-stbl tbody tr.eas-stbl-student-row:nth-child(even) { background:#f8fafd; }
		.eas-stbl tbody tr.eas-stbl-student-row:hover { background:#FBEEF0 !important; }
		.eas-stbl tbody tr.eas-stbl-student-row:hover .eas-view-btn { opacity:1 !important; background:#F5D9DE; border-color:#C4566A; color:#920C24; }
		.eas-stbl tbody td {
			padding:13px 14px; border-bottom:1px solid #eef2f8;
			border-top:none; border-left:none; border-right:none; vertical-align:middle;
		}

		/* Footer summary row */
		.eas-stbl tfoot td {
			padding:10px 14px; background:linear-gradient(90deg,#f8fafc,#FBEEF0);
			border-top:2px solid #E8B4BE; font-size:12px; color:#64748b; font-weight:600;
		}

		/* Row avatar */
		.eas-stbl-name-cell { display:flex; align-items:center; gap:10px; }
		.eas-row-avatar {
			width:36px; height:36px; border-radius:50%; flex-shrink:0;
			display:flex; align-items:center; justify-content:center;
			font-size:13px; font-weight:800; color:#fff;
			box-shadow:0 2px 6px rgba(0,0,0,.18);
		}
		.eas-student-name-text { font-weight:700; color:#920C24; font-size:13.5px; line-height:1.2; }
		.eas-student-num {
			font-size:11px; color:#94a3b8; font-weight:700;
			background:#f6f4f4; width:24px; height:24px;
			border-radius:50%; display:inline-flex; align-items:center;
			justify-content:center; border:1px solid #e2e8f0;
		}

		/* Badges */
		.eas-reg-badge {
			display:inline-block; font-family:Consolas,monospace;
			font-size:11.5px; color:#475569;
			background:#f6f4f4; border:1px solid #e2e8f0;
			padding:3px 9px; border-radius:7px;
		}
		.eas-sec-badge {
			display:inline-block; background:#F5D9DE; color:#6E091B;
			font-size:11px; font-weight:700; border-radius:7px;
			padding:3px 10px;
		}
		.eas-bc-ok {
			display:inline-flex; align-items:center; gap:6px;
			background:#dcfce7; color:#15803d; border:1px solid #bbf7d0;
			border-radius:8px; padding:5px 12px;
			font-weight:800; font-size:13px; letter-spacing:2px;
			font-family:Consolas,monospace;
		}
		.eas-bc-ok .bc-dot {
			width:7px; height:7px; border-radius:50%; background:#22c55e;
		}
		.eas-bc-pend {
			display:inline-flex; align-items:center; gap:5px;
			background:#fef9c3; color:#92400e; border:1px solid #fde68a;
			border-radius:8px; padding:5px 10px;
			font-size:11.5px; font-weight:600;
		}

		/* View-details button — always slightly visible, full on hover */
		.eas-view-btn {
			width:30px; height:30px; border-radius:8px;
			border:1px solid #e2e8f0; background:#f8fafc; color:#64748b; cursor:pointer;
			display:inline-flex; align-items:center; justify-content:center;
			font-size:13px; opacity:0.55; transition:opacity .15s,background .12s,color .12s,border-color .12s,transform .1s;
		}
		.eas-view-btn:hover { background:#F5D9DE; color:#920C24; opacity:1; transform:scale(1.1); border-color:#C4566A; }

		/* ─── Empty / loading ────────────────────────────────────────────── */
		.eas-empty {
			text-align:center; padding:60px 24px; color:#94a3b8;
			background:#fff; border-radius:14px; border:1px solid #e2e8f0;
		}
		.eas-empty-icon {
			width:68px; height:68px; border-radius:18px;
			background:#f6f4f4; display:flex; align-items:center; justify-content:center;
			font-size:30px; color:#cbd5e1; margin:0 auto 16px;
		}
		.eas-empty-title { font-size:16px; font-weight:700; color:#475569; margin-bottom:6px; }
		.eas-empty-sub { font-size:13px; color:#94a3b8; line-height:1.7; }

		/* ─── Responsive ─────────────────────────────────────────────────── */
		@media(max-width:768px){
			.eas-page { padding:12px 14px; }
			.eas-tbl thead th, .eas-tbl tbody td { padding:9px 10px; }
		}

		/* ─── Dialog: date-range ─────────────────────────────────────────── */
		.eas-avail-box {
			background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;
			padding:14px 16px; margin-bottom:4px;
		}
		.eas-avail-box .av-title {
			font-size:10.5px; font-weight:700; text-transform:uppercase;
			letter-spacing:.5px; color:#64748b; margin-bottom:10px;
			display:flex; align-items:center; gap:6px;
		}
		.eas-avail-box .av-row {
			display:flex; align-items:center; gap:8px;
			font-size:12.5px; color:#374151;
			padding:5px 0; border-bottom:1px solid #f6f4f4;
		}
		.eas-avail-box .av-row:last-child { border-bottom:none; }
		.eas-avail-box .av-row i { color:#920C24; width:14px; text-align:center; }
		.eas-avail-box .av-row .av-cnt { color:#94a3b8; font-size:11.5px; margin-left:auto; }

		/* ─── Dialog: course picker ──────────────────────────────────────── */
		.eas-pick-header {
			display:flex; align-items:center; justify-content:space-between;
			margin-bottom:10px; padding-bottom:10px; border-bottom:1px solid #e2e8f0;
		}
		.eas-pick-header .eas-sel-all {
			font-size:12px; font-weight:700; color:#920C24; cursor:pointer;
			text-decoration:none; display:flex; align-items:center; gap:5px;
		}
		.eas-pick-header .eas-sel-all:hover { text-decoration:underline; }
		.eas-pick-header .eas-pick-count { font-size:12px; color:#94a3b8; }
		.eas-pick-list { display:flex; flex-direction:column; gap:5px; }
		.eas-pick-item {
			display:flex; align-items:center; gap:10px;
			padding:10px 14px; border-radius:9px; cursor:pointer;
			border:1.5px solid #e2e8f0; background:#fff; transition:all .12s;
		}
		.eas-pick-item:hover { background:#FBEEF0; border-color:#E8B4BE; }
		.eas-pick-item.is-checked { background:#FBEEF0; border-color:#C4566A; }
		.eas-pick-item input[type=checkbox] {
			width:15px; height:15px; accent-color:#920C24;
			cursor:pointer; flex-shrink:0;
		}
		.eas-pick-item .pi-name { font-size:13px; font-weight:600; color:#0f172a; flex:1; }
		.eas-pick-item .pi-code {
			font-family:Consolas,monospace; font-size:11px; color:#64748b;
			background:#f6f4f4; border:1px solid #e2e8f0;
			padding:1px 6px; border-radius:4px;
		}
		.eas-pick-item .pi-badge { font-size:11px; font-weight:700; border-radius:20px; padding:2px 9px; }
		.eas-pick-item .pi-ready { background:#dcfce7; color:#15803d; border:1px solid #bbf7d0; }
		.eas-pick-item .pi-none  { background:#f6f4f4; color:#94a3b8; border:1px solid #e2e8f0; }

		/* ─── Student detail dialog ──────────────────────────────────────── */
		.eas-std-detail { padding:4px 0; }
		.eas-std-header {
			display:flex; align-items:center; gap:18px; padding:22px 24px;
			background:linear-gradient(135deg,#920C24 0%,#920C24 100%);
			border-radius:14px; margin-bottom:18px;
		}
		.eas-std-avatar {
			width:66px; height:66px; border-radius:50%; flex-shrink:0; overflow:hidden;
			background:rgba(255,255,255,.2); color:#fff;
			display:flex; align-items:center; justify-content:center;
			font-size:26px; font-weight:800;
			border:2.5px solid rgba(255,255,255,.4);
		}
		.eas-std-avatar img { width:66px; height:66px; object-fit:cover; }
		.eas-std-main-info { flex:1; min-width:0; }
		.eas-std-name { font-size:19px; font-weight:800; color:#fff; }
		.eas-std-regid {
			font-size:12.5px; color:rgba(255,255,255,.75);
			margin-top:3px; font-family:Consolas,monospace;
		}
		.eas-std-program-tag {
			display:inline-block; margin-top:7px;
			background:rgba(255,255,255,.18); color:#fff;
			border:1px solid rgba(255,255,255,.3);
			border-radius:20px; padding:2px 11px;
			font-size:11px; font-weight:600;
		}
		.eas-std-bc-badge {
			flex-shrink:0; text-align:center; padding:13px 20px;
			background:rgba(255,255,255,.95); border-radius:12px;
			box-shadow:0 2px 10px rgba(0,0,0,.15);
		}
		.eas-std-bc-badge .bc-label {
			font-size:9.5px; font-weight:700; text-transform:uppercase;
			letter-spacing:.7px; color:#15803d; margin-bottom:5px;
		}
		.eas-std-bc-badge .bc-val {
			font-size:24px; font-weight:800; color:#15803d;
			letter-spacing:4px; font-family:Consolas,monospace;
		}
		.eas-std-bc-badge.bc-pending .bc-label,
		.eas-std-bc-badge.bc-pending .bc-val { color:#94a3b8; }

		.eas-std-section-title {
			font-size:10.5px; font-weight:700; text-transform:uppercase;
			letter-spacing:.7px; color:#94a3b8; margin-bottom:10px; margin-top:2px;
			display:flex; align-items:center; gap:8px;
		}
		.eas-std-section-title::after {
			content:''; flex:1; height:1px; background:#e2e8f0;
		}
		.eas-std-grid {
			display:grid; grid-template-columns:1fr 1fr;
			gap:10px; margin-bottom:16px;
		}
		.eas-std-field {
			background:#f8fafc; border:1px solid #e2e8f0;
			border-radius:10px; padding:12px 16px; transition:border-color .15s;
		}
		.eas-std-field:hover { border-color:#E8B4BE; }
		.eas-std-field label {
			font-size:10px; font-weight:700; text-transform:uppercase;
			letter-spacing:.5px; color:#94a3b8; display:block; margin-bottom:4px;
		}
		.eas-std-field span { font-size:14px; color:#0f172a; font-weight:500; }
		.eas-std-field .empty {
			color:#d1d5db; font-style:italic; font-weight:400; font-size:13px;
		}
		.eas-std-exam-info {
			background:linear-gradient(90deg,#FBEEF0,#FBEEF0);
			border:1px solid #E8B4BE; border-radius:10px;
			padding:12px 16px; font-size:12.5px; color:#920C24;
			display:flex; align-items:center; gap:10px; margin-bottom:4px;
		}
		</style>`).appendTo('head');
	}

	// ── Build page skeleton ────────────────────────────────────────────────────
	_build_ui() {
		this.$page = $('<div class="eas-page"></div>').appendTo(this.$body);

		this.$filter = $(`
			<div class="eas-filter">
				<div class="eas-filter-icon"><i class="fa fa-barcode"></i></div>
				<div class="eas-filter-text">
					<div class="flt-sup">Examination</div>
					<div class="flt-title">Exam Barcode Sheet</div>
				</div>
				<div class="eas-plan-wrap"></div>
				<button class="btn btn-primary eas-load-btn" disabled>
					<i class="fa fa-search"></i>&nbsp; Load Courses
				</button>
			</div>
		`).appendTo(this.$page);

		this.$results = $('<div class="eas-results"></div>').appendTo(this.$page);
		this._build_plan_field();
	}

	// ── Exam Plan link field ───────────────────────────────────────────────────
	_build_plan_field() {
		this._plan_ctrl = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link', fieldname: 'exam_plan',
				options: 'Exam Plan', placeholder: 'Select Exam Plan…'
			},
			parent: this.$filter.find('.eas-plan-wrap')[0],
			render_input: true,
		});
		this._plan_ctrl.refresh();

		const $btn = this.$filter.find('.eas-load-btn');
		const _sync = () => {
			const v = this._plan_value();
			$btn.prop('disabled', !v);
			if (!v) { this.exam_plan = null; this._clear(); }
		};
		this._plan_ctrl.$input.on('input change awesomplete-selectcomplete', _sync);
		const _orig = this._plan_ctrl.set_value.bind(this._plan_ctrl);
		this._plan_ctrl.set_value = v => { _orig(v); _sync(); };
		$btn.on('click', () => {
			const v = this._plan_value();
			if (!v) {
				frappe.show_alert({ message: 'Please select an Exam Plan.', indicator: 'orange' });
				return;
			}
			this.exam_plan = v;
			this._load_courses();
		});
	}

	_plan_value() {
		return (this._plan_ctrl.get_value() || this._plan_ctrl.$input.val() || '').trim();
	}

	_clear() { this.$results.empty(); this.$toolbar = null; }

	_fmt_time(t) {
		if (!t) return '<span style="color:#d1d5db;">—</span>';
		try {
			return `<span style="font-size:12.5px;color:#374151;">${moment(t, 'HH:mm:ss').format('hh:mm A')}</span>`;
		} catch { return t; }
	}

	// ── Load courses ───────────────────────────────────────────────────────────
	_load_courses() {
		this.courses = [];
		this._clear();
		this.$results.html(`
			<div class="eas-empty">
				<div class="eas-empty-icon"><i class="fa fa-spinner fa-spin"></i></div>
				<div class="eas-empty-title">Loading courses…</div>
			</div>`);

		frappe.call({
			method: 'slcm.slcm.page.exam_barcode_sheet.exam_barcode_sheet.get_exam_courses',
			args: { exam_plan: this.exam_plan },
			callback: r => {
				if (r.exc) { this._clear(); return; }
				const data = r.message || [];
				this._clear();
				if (!data.length) {
					this.$results.html(`
						<div class="eas-empty">
							<div class="eas-empty-icon"><i class="fa fa-calendar-times-o"></i></div>
							<div class="eas-empty-title">No courses scheduled</div>
							<div class="eas-empty-sub">
								No course schedules found in <strong>"${this.exam_plan}"</strong>.<br>
								Open the Exam Plan and add course schedules first.
							</div>
						</div>`);
					return;
				}
				this.courses = data;
				this._render_courses();
			}
		});
	}

	// ── Render all courses ─────────────────────────────────────────────────────
	_render_courses() {
		const n_courses  = this.courses.length;
		const n_barcodes = this.courses.reduce((s, c) => s + (c.barcode_count || 0), 0);
		const n_ready    = this.courses.filter(c => c.barcode_count > 0).length;
		const all_ready  = n_ready === n_courses;

		/* ── Stat cards ── */
		const status_color  = all_ready ? '#059669' : n_ready > 0 ? '#d97706' : '#64748b';
		const status_label  = all_ready ? '<i class="fa fa-check-circle"></i>&nbsp; All Ready' : `${n_ready} / ${n_courses} Ready`;
		$(`<div class="eas-stats-row">
			<div class="eas-stat-card sc-plan">
				<div class="eas-stat-icon"><i class="fa fa-clipboard"></i></div>
				<div class="eas-stat-label">Exam Plan</div>
				<div class="eas-stat-val sv-text">${this.exam_plan}</div>
			</div>
			<div class="eas-stat-card sc-count">
				<div class="eas-stat-icon"><i class="fa fa-book"></i></div>
				<div class="eas-stat-label">Total Courses</div>
				<div class="eas-stat-val" style="color:#920C24;">${n_courses}</div>
				<div class="eas-stat-sub">scheduled</div>
			</div>
			<div class="eas-stat-card sc-bc">
				<div class="eas-stat-icon"><i class="fa fa-barcode"></i></div>
				<div class="eas-stat-label">Barcodes Generated</div>
				<div class="eas-stat-val" style="color:#059669;">${n_barcodes}</div>
				<div class="eas-stat-sub">across all courses</div>
			</div>
			<div class="eas-stat-card sc-status${all_ready ? ' all-ready' : ''}">
				<div class="eas-stat-icon"><i class="fa fa-${all_ready ? 'check-circle' : 'clock-o'}"></i></div>
				<div class="eas-stat-label">Status</div>
				<div class="eas-stat-val sv-text" style="color:${status_color};">${status_label}</div>
			</div>
		</div>`).appendTo(this.$results);

		/* ── Action bar ── */
		const dl_off = n_barcodes === 0;
		this.$toolbar = $(`
			<div class="eas-actions">
				<span class="act-label">Actions</span>
				<button class="eas-btn-gen-all">
					<i class="fa fa-qrcode"></i> Generate All Barcodes
				</button>
				<div class="divider"></div>
				<span class="act-label">Download Excel</span>
				<button class="eas-btn-dl-date" ${dl_off ? 'disabled' : ''}>
					<i class="fa fa-calendar"></i> By Date
				</button>
				<button class="eas-btn-dl-course" ${dl_off ? 'disabled' : ''}>
					<i class="fa fa-book"></i> By Course
				</button>
			</div>
		`).appendTo(this.$results);

		this.$toolbar.find('.eas-btn-gen-all').on('click', () =>
			this._generate_barcodes(this.courses.map(c => c.course)));
		this.$toolbar.find('.eas-btn-dl-date').on('click', () => this._show_by_date_dialog());
		this.$toolbar.find('.eas-btn-dl-course').on('click', () => this._show_by_course_dialog());

		/* ── Group by exam date ── */
		const date_groups = {};
		this.courses.forEach(c => {
			const k = c.exam_date || '__nodate__';
			if (!date_groups[k]) date_groups[k] = [];
			date_groups[k].push(c);
		});
		const sorted_dates = Object.keys(date_groups).sort((a, b) => {
			if (a === '__nodate__') return 1;
			if (b === '__nodate__') return -1;
			return a < b ? -1 : 1;
		});

		sorted_dates.forEach(date => {
			const label = date === '__nodate__'
				? 'No Date Scheduled'
				: frappe.datetime.str_to_user(date);
			const count = date_groups[date].length;

			const $section = $('<div class="eas-date-section"></div>').appendTo(this.$results);

			$(`<div class="eas-date-hdr">
				<div class="eas-date-icon"><i class="fa fa-calendar"></i></div>
				<div class="eas-date-text">
					<div class="dt-sup">Exam Date</div>
					<div class="dt-val">${label}</div>
				</div>
				<span class="eas-date-pill">${count} course${count !== 1 ? 's' : ''}</span>
			</div>`).appendTo($section);

			const $wrap = $(`
				<div class="eas-tbl-wrap">
					<table class="eas-tbl">
						<thead>
							<tr>
								<th style="width:38px;text-align:center;">#</th>
								<th>Course Name</th>
								<th style="width:110px;">Code</th>
								<th style="width:95px;">Start</th>
								<th style="width:95px;">End</th>
								<th style="width:150px;">Venue</th>
								<th style="width:115px;">Hall / Room</th>
								<th style="width:140px;text-align:center;">Barcode Status</th>
								<th style="width:170px;text-align:right;padding-right:16px;">Actions</th>
							</tr>
						</thead>
						<tbody></tbody>
					</table>
				</div>
			`).appendTo($section);

			date_groups[date].forEach((c, i) =>
				this._append_course_row(c, i + 1, $wrap.find('tbody')));
		});
	}

	// ── Single course row + inline student panel ───────────────────────────────
	_append_course_row(c, idx, $tbody) {
		const has = c.barcode_count > 0;
		const status_html = has
			? `<span class="eas-status-ready"><i class="fa fa-check-circle"></i> ${c.barcode_count} Ready</span>`
			: `<span class="eas-status-none"><i class="fa fa-circle-o"></i> Not generated</span>`;

		const $tr = $(`
			<tr class="eas-course-tr" data-course="${c.course}">
				<td style="text-align:center;font-size:12px;color:#94a3b8;font-weight:600;">${idx}</td>
				<td>
					<div class="eas-cname">
						<span class="eas-course-dot"></span>
						<span>
							<a class="eas-clink eas-toggle-detail" href="#" title="Click to view enrolled students">
								${c.course_name || c.course}
							</a>
							<i class="fa fa-chevron-right eas-chevron"></i>
						</span>
					</div>
				</td>
				<td><span class="eas-code">${c.course_code || c.course}</span></td>
				<td>${this._fmt_time(c.start_time)}</td>
				<td>${this._fmt_time(c.end_time)}</td>
				<td style="font-size:12.5px;color:#374151;">${c.venue || '<span style="color:#d1d5db;">—</span>'}</td>
				<td style="font-size:12.5px;color:#374151;">${c.hall  || '<span style="color:#d1d5db;">—</span>'}</td>
				<td style="text-align:center;">${status_html}</td>
				<td>
					<div class="eas-row-acts">
						<button class="eas-btn-gen-row" title="Generate barcodes for this course">
							<i class="fa fa-refresh"></i> Generate
						</button>
						<button class="eas-btn-dl-row"
							title="${has ? 'Download barcode sheet for this course' : 'Generate barcodes first'}"
							${!has ? 'disabled' : ''}>
							<i class="fa fa-download"></i> Download
						</button>
					</div>
				</td>
			</tr>
		`).appendTo($tbody);

		const $detail = $(`
			<tr class="eas-detail-row" style="display:none;">
				<td colspan="9"><div class="eas-panel"><div class="eas-panel-inner"></div></div></td>
			</tr>
		`).appendTo($tbody);

		$tr.find('.eas-toggle-detail').on('click', e => {
			e.preventDefault();
			const open = $detail.is(':visible');
			$detail.toggle(!open);
			$tr.find('.eas-chevron').css('transform', open ? '' : 'rotate(90deg)');
			if (!open) this._load_students(c, $detail.find('.eas-panel-inner'));
		});

		$tr.find('.eas-btn-gen-row').on('click', () => this._generate_barcodes([c.course]));
		$tr.find('.eas-btn-dl-row').on('click', () => {
			if (!has) return;
			this._export_excel(c.course, null);
		});
	}

	// ── Load & render student panel ────────────────────────────────────────────
	_load_students(c, $panel) {
		if ($panel.children().length) return;
		$panel.html(`
			<div style="display:flex;align-items:center;gap:10px;color:#64748b;font-size:13px;padding:8px 0;">
				<i class="fa fa-spinner fa-spin" style="color:#920C24;"></i>
				Loading students for <b>${c.course_name || c.course}</b>…
			</div>`);

		frappe.call({
			method: 'slcm.slcm.page.exam_barcode_sheet.exam_barcode_sheet.get_course_students',
			args: { exam_plan: this.exam_plan, course: c.course },
			callback: r => {
				if (r.exc) {
					$panel.html(`
						<div style="color:#dc2626;font-size:13px;">
							<i class="fa fa-exclamation-circle"></i> Failed to load students.
						</div>`);
					return;
				}
				this._render_student_panel($panel, r.message || [], c);
			}
		});
	}

	_render_student_panel($panel, students, c) {
		if (!students.length) {
			$panel.html(`
				<div style="padding:12px 0;color:#64748b;font-size:13px;">
					<i class="fa fa-info-circle" style="color:#C4566A;"></i>
					No students enrolled in <b>${c.course_name || c.course}</b>.
					Check that students are enrolled in this course for the exam plan's term.
				</div>`);
			return;
		}

		const total   = students.length;
		const done    = students.filter(s => s.has_barcode).length;
		const pending = total - done;
		const pct     = Math.round((done / total) * 100);
		const prog_col = pct === 100 ? '#059669' : pct > 50 ? '#920C24' : '#d97706';

		/* Avatar helpers */
		const _initials = name => {
			const p = (name || '').trim().split(/\s+/).filter(Boolean);
			if (p.length >= 2) return (p[0][0] + p[p.length-1][0]).toUpperCase();
			return (name || '?').charAt(0).toUpperCase();
		};
		const _avatar_bg = name => {
			const palette = ['#920C24','#920C24','#059669','#d97706',
			                 '#dc2626','#C4566A','#920C24','#16a34a','#ea580c','#C4566A'];
			let h = 0;
			for (const ch of (name || '')) h = ch.charCodeAt(0) + ((h << 5) - h);
			return palette[Math.abs(h) % palette.length];
		};

		/* Sort state */
		let _sort_col = 'name', _sort_asc = true;

		const _row = (s, i) => {
			const bg  = _avatar_bg(s.student_name || s.student);
			const ini = _initials(s.student_name || s.student);
			return `
				<tr class="eas-stbl-student-row" data-student="${s.student}"
					data-name="${(s.student_name||'').toLowerCase()}"
					data-regid="${(s.registration_id||'').toLowerCase()}"
					data-section="${(s.section||'').toLowerCase()}"
					data-barcode="${s.barcode||''}"
					title="Click to view full student details">
					<td style="width:48px;text-align:center;">
						<span class="eas-student-num">${i+1}</span>
					</td>
					<td>
						<div class="eas-stbl-name-cell">
							<div class="eas-row-avatar" style="background:${bg};">${ini}</div>
							<span class="eas-student-name-text">${s.student_name || s.student}</span>
						</div>
					</td>
					<td>
						${s.registration_id
							? `<span class="eas-reg-badge">${s.registration_id}</span>`
							: '<span style="color:#d1d5db;">—</span>'}
					</td>
					<td style="text-align:center;">
						${s.section
							? `<span class="eas-sec-badge">${s.section}</span>`
							: '<span style="color:#d1d5db;">—</span>'}
					</td>
					<td style="text-align:center;">
						${s.barcode
							? `<span class="eas-bc-ok"><span class="bc-dot"></span>${s.barcode}</span>`
							: `<span class="eas-bc-pend"><i class="fa fa-clock-o"></i> Pending</span>`}
					</td>
					<td style="width:44px;text-align:center;">
						<button class="eas-view-btn" title="View student details">
							<i class="fa fa-eye"></i>
						</button>
					</td>
				</tr>`;
		};

		const _render_rows = (data) =>
			data.map((s, i) => _row(s, i)).join('');

		$panel.html(`
			<div class="eas-panel-header">
				<div class="eas-panel-left">
					<div class="eas-panel-course-icon"><i class="fa fa-graduation-cap"></i></div>
					<div>
						<div class="eas-panel-course-name">${c.course_name || c.course}</div>
						<div class="eas-panel-course-code">${c.course_code || ''}</div>
						<div class="eas-prog-row" style="margin-top:8px;">
							<div class="eas-prog">
								<div class="eas-prog-fill" style="width:${pct}%;background:${prog_col};"></div>
							</div>
							<span class="eas-prog-pct">${pct}%</span>
						</div>
					</div>
				</div>
				<div class="eas-panel-stats">
					<div class="eas-pstat">
						<div class="eas-pstat-val pv-total">${total}</div>
						<div class="eas-pstat-label">Enrolled</div>
					</div>
					<div class="eas-pstat">
						<div class="eas-pstat-val pv-done">${done}</div>
						<div class="eas-pstat-label">Barcoded</div>
					</div>
					<div class="eas-pstat">
						<div class="eas-pstat-val pv-pend">${pending}</div>
						<div class="eas-pstat-label">Pending</div>
					</div>
				</div>
			</div>

			<div class="eas-stbl-toolbar">
				<div class="eas-search-wrap">
					<i class="fa fa-search eas-search-ico"></i>
					<input type="text" class="eas-stbl-search" placeholder="Search by name, ID or barcode…">
				</div>
				<span class="eas-stbl-count">${total} student${total !== 1 ? 's' : ''}</span>
				<span class="eas-stbl-hint">
					<i class="fa fa-eye" style="color:#920C24;"></i> Click a row to view full details
				</span>
			</div>

			<div class="eas-stbl-wrap">
				<table class="eas-stbl">
					<thead>
						<tr>
							<th style="width:42px;text-align:center;">#</th>
							<th class="sortable" data-col="name">
								Student Name
								<span class="sort-ico sort-asc"><span class="s-up"></span><span class="s-dn"></span></span>
							</th>
							<th class="sortable" data-col="regid" style="width:160px;">
								Student ID
								<span class="sort-ico"><span class="s-up"></span><span class="s-dn"></span></span>
							</th>
							<th style="text-align:center;width:80px;">Section</th>
							<th class="sortable" data-col="barcode" style="text-align:center;width:150px;">
								Barcode
								<span class="sort-ico"><span class="s-up"></span><span class="s-dn"></span></span>
							</th>
							<th style="width:44px;"></th>
						</tr>
					</thead>
					<tbody class="eas-stbl-body">${_render_rows(students)}</tbody>
					<tfoot>
						<tr>
							<td colspan="2">
								<i class="fa fa-users" style="color:#920C24;margin-right:4px;"></i>
								${total} student${total !== 1 ? 's' : ''} total
							</td>
							<td colspan="2" style="color:#059669;">
								<i class="fa fa-check-circle" style="margin-right:4px;"></i>
								${done} barcoded
							</td>
							<td colspan="2" style="color:#d97706;">
								<i class="fa fa-clock-o" style="margin-right:4px;"></i>
								${pending} pending
							</td>
						</tr>
					</tfoot>
				</table>
			</div>`);

		/* ── Search filter ── */
		$panel.find('.eas-stbl-search').on('input', function () {
			const q = $(this).val().toLowerCase().trim();
			const $rows = $panel.find('.eas-stbl-body tr');
			let visible = 0;
			$rows.each(function () {
				const $r     = $(this);
				const name   = String($r.attr('data-name')    || '');
				const regid  = String($r.attr('data-regid')   || '');
				const barcode= String($r.attr('data-barcode') || '').toLowerCase();
				const section= String($r.attr('data-section') || '');
				const match  = !q ||
					name.includes(q) ||
					regid.includes(q) ||
					barcode.includes(q) ||
					section.includes(q);
				$r.toggle(match);
				if (match) visible++;
			});
			$panel.find('.eas-stbl-count').text(
				q ? `${visible} of ${total} student${total !== 1 ? 's' : ''}` :
				    `${total} student${total !== 1 ? 's' : ''}`
			);
		});

		/* ── Column sort ── */
		$panel.find('thead th.sortable').on('click', function () {
			const col  = $(this).data('col');
			const asc  = col === _sort_col ? !_sort_asc : true;
			_sort_col  = col; _sort_asc = asc;

			$panel.find('thead th').removeClass('sort-asc sort-desc');
			$(this).addClass(asc ? 'sort-asc' : 'sort-desc');

			const _field_map = { name: 'student_name', regid: 'registration_id', barcode: 'barcode' };
			const sorted = [...students].sort((a, b) => {
				const va = String(a[_field_map[col]] || '').toLowerCase();
				const vb = String(b[_field_map[col]] || '').toLowerCase();
				return asc ? va.localeCompare(vb) : vb.localeCompare(va);
			});
			$panel.find('.eas-stbl-body').html(_render_rows(sorted));

			/* re-bind row clicks after sort re-render */
			$panel.find('.eas-stbl-student-row').on('click', e =>
				this._show_student_details($(e.currentTarget).data('student'), c));
			$panel.find('.eas-view-btn').on('click', e => {
				e.stopPropagation();
				this._show_student_details($(e.currentTarget).closest('tr').data('student'), c);
			});
		}.bind(this));

		/* ── Row click + view button ── */
		$panel.find('.eas-stbl-student-row').on('click', e =>
			this._show_student_details($(e.currentTarget).data('student'), c));
		$panel.find('.eas-view-btn').on('click', e => {
			e.stopPropagation();
			this._show_student_details($(e.currentTarget).closest('tr').data('student'), c);
		});
	}

	// ── Student detail dialog ──────────────────────────────────────────────────
	_show_student_details(student_id, c) {
		frappe.call({
			method: 'slcm.slcm.page.exam_barcode_sheet.exam_barcode_sheet.get_student_details',
			args: { student: student_id, exam_plan: this.exam_plan, course: c.course },
			freeze: true,
			freeze_message: 'Loading student details…',
			callback: r => {
				if (r.exc || !r.message) {
					frappe.show_alert({ message: 'Could not load student details.', indicator: 'red' });
					return;
				}
				const d = r.message;
				const detail_d = new frappe.ui.Dialog({
					title: d.student_name || student_id,
					size: 'large',
					fields: [{ fieldtype: 'HTML', options: this._student_detail_html(d, c) }],
					primary_action_label: '<i class="fa fa-external-link"></i>&nbsp; Open Student Profile',
					primary_action: () => {
						detail_d.hide();
						frappe.set_route('Form', 'Student Master', student_id);
					},
				});
				detail_d.show();
			},
		});
	}

	_student_detail_html(d, c) {
		const _field = (label, val) => `
			<div class="eas-std-field">
				<label>${label}</label>
				<span class="${val ? '' : 'empty'}">${val || 'Not provided'}</span>
			</div>`;

		const initials = ((d.first_name || '').charAt(0) + (d.last_name || '').charAt(0)).toUpperCase() || '?';
		const avatar_html = d.image
			? `<img src="${d.image}" alt="${d.student_name}">`
			: initials;

		const bc_class = d.barcode ? '' : ' bc-pending';
		const bc_html = `
			<div class="eas-std-bc-badge${bc_class}">
				<div class="bc-label">${d.barcode ? 'Barcode' : 'No Barcode'}</div>
				<div class="bc-val">${d.barcode || '—'}</div>
			</div>`;

		const prog_parts = [d.program, d.academic_year].filter(Boolean);
		const prog_tag = prog_parts.length
			? `<span class="eas-std-program-tag">${prog_parts.join(' &nbsp;·&nbsp; ')}</span>`
			: '';

		const personal_fields = [
			_field('Gender',        d.gender),
			_field('Date of Birth', d.date_of_birth),
			_field('Blood Group',   d.blood_group),
			_field('Status',        d.student_status),
			_field('Email',         d.email),
			_field('Phone',         d.phone),
		].join('');

		const exam_info = c ? `
			<div class="eas-std-section-title" style="margin-top:14px;">Exam Context</div>
			<div class="eas-std-exam-info">
				<i class="fa fa-book" style="color:#920C24;"></i>
				<span><b>Course:</b> ${c.course_name || c.course}</span>
				&nbsp;·&nbsp;
				<span><b>Exam Plan:</b> ${this.exam_plan}</span>
			</div>` : '';

		return `
			<div class="eas-std-detail">
				<div class="eas-std-header">
					<div class="eas-std-avatar">${avatar_html}</div>
					<div class="eas-std-main-info">
						<div class="eas-std-name">${d.student_name}</div>
						<div class="eas-std-regid">${d.registration_id}</div>
						${prog_tag}
					</div>
					${bc_html}
				</div>
				<div class="eas-std-section-title">Personal Information</div>
				<div class="eas-std-grid">${personal_fields}</div>
				${exam_info}
			</div>`;
	}

	// ── Generate barcodes ──────────────────────────────────────────────────────
	_generate_barcodes(courses) {
		frappe.prompt(
			[{
				fieldtype: 'Int',
				fieldname: 'copies',
				label: 'Copies per Student',
				description: 'How many times should each student\'s barcode be printed (e.g. one per answer booklet)? The same barcode is repeated — no new barcode is generated per copy.',
				default: 1,
				reqd: 1,
			}],
			values => {
				const copies = values.copies || 1;
				frappe.call({
					method: 'slcm.slcm.page.exam_barcode_sheet.exam_barcode_sheet.generate_barcodes',
					args: { exam_plan: this.exam_plan, courses: JSON.stringify(courses), copies },
					freeze: true,
					freeze_message: 'Generating barcodes…',
					callback: r => {
						if (r.exc) {
							frappe.show_alert({ message: 'Error generating barcodes.', indicator: 'red' });
							return;
						}
						frappe.show_alert({ message: r.message?.message || 'Done.', indicator: 'green' });
						this._load_courses();
					}
				});
			},
			'Generate Barcodes',
			'Generate'
		);
	}

	// ── By-Date dialog ─────────────────────────────────────────────────────────
	_show_by_date_dialog() {
		const date_map = {};
		this.courses.forEach(c => {
			const k = c.exam_date ? String(c.exam_date) : '__nodate__';
			date_map[k] = (date_map[k] || 0) + 1;
		});
		const av_rows = Object.keys(date_map)
			.sort((a, b) => {
				if (a === '__nodate__') return 1;
				if (b === '__nodate__') return -1;
				return a < b ? -1 : 1;
			})
			.map(k => {
				const label = k === '__nodate__'
					? 'No Date Scheduled'
					: frappe.datetime.str_to_user(k);
				const n = date_map[k];
				return `<div class="av-row">
					<i class="fa fa-circle" style="font-size:6px;"></i>
					<span>${label}</span>
					<span class="av-cnt">${n} course${n !== 1 ? 's' : ''}</span>
				</div>`;
			}).join('');

		const d = new frappe.ui.Dialog({
			title: 'Download Barcode Sheet — Select Date Range',
			fields: [
				{
					fieldtype: 'HTML',
					options: `<div class="eas-avail-box">
						<div class="av-title">
							<i class="fa fa-calendar-o"></i>
							Available Exam Dates in "${this.exam_plan}"
						</div>
						${av_rows}
					</div>`,
				},
				{
					fieldtype: 'Date', fieldname: 'from_date', label: 'From Date',
					description: 'Leave blank to start from the earliest scheduled date',
				},
				{
					fieldtype: 'Date', fieldname: 'to_date', label: 'To Date',
					description: 'Leave blank to include up to the latest scheduled date',
				},
			],
			primary_action_label: '<i class="fa fa-download"></i>&nbsp; Download Excel',
			primary_action: values => {
				const from = values.from_date || '';
				const to   = values.to_date   || '';
				if (from && to && from > to) {
					frappe.show_alert({ message: '"From Date" must be on or before "To Date".', indicator: 'orange' });
					return;
				}
				d.hide();
				this._export_excel(null, 'by_date', from, to, '');
			},
		});
		d.show();
	}

	// ── By-Course dialog ───────────────────────────────────────────────────────
	_show_by_course_dialog() {
		const courses = this.courses;
		const items_html = courses.map(c => {
			const has   = c.barcode_count > 0;
			const badge = has
				? `<span class="pi-badge pi-ready">${c.barcode_count} Ready</span>`
				: `<span class="pi-badge pi-none">No barcodes</span>`;
			return `<label class="eas-pick-item is-checked" data-course="${c.course}">
				<input type="checkbox" class="eas-pick-chk" value="${c.course}" checked>
				<span class="pi-name">${c.course_name || c.course}</span>
				<span class="pi-code">${c.course_code || c.course}</span>
				${badge}
			</label>`;
		}).join('');

		const d = new frappe.ui.Dialog({
			title: 'Download Barcode Sheet — Select Courses',
			fields: [{
				fieldtype: 'HTML',
				options: `<div style="margin-bottom:12px;">
					<div class="eas-pick-header">
						<a class="eas-sel-all" href="#" id="eas-sel-all-link">
							<i class="fa fa-check-square-o"></i> Select All
						</a>
						<span class="eas-pick-count eas-pick-counter">${courses.length} of ${courses.length} selected</span>
					</div>
					<div class="eas-pick-list">${items_html}</div>
				</div>`,
			}],
			primary_action_label: '<i class="fa fa-download"></i>&nbsp; Download Excel',
			primary_action: () => {
				const selected = [...d.$wrapper.find('.eas-pick-chk:checked')].map(el => el.value);
				if (!selected.length) {
					frappe.show_alert({ message: 'Please select at least one course.', indicator: 'orange' });
					return;
				}
				d.hide();
				this._export_excel(null, 'by_course', '', '', JSON.stringify(selected));
			},
		});
		d.show();

		const $dlg = d.$wrapper;
		let all_checked = true;
		const _update_counter = () => {
			const total   = $dlg.find('.eas-pick-chk').length;
			const checked = $dlg.find('.eas-pick-chk:checked').length;
			$dlg.find('.eas-pick-counter').text(`${checked} of ${total} selected`);
			$dlg.find('#eas-sel-all-link').html(checked === total
				? '<i class="fa fa-minus-square-o"></i> Deselect All'
				: '<i class="fa fa-check-square-o"></i> Select All');
		};
		$dlg.find('.eas-pick-chk').on('change', function () {
			$(this).closest('.eas-pick-item').toggleClass('is-checked', this.checked);
			_update_counter();
		});
		$dlg.find('#eas-sel-all-link').on('click', e => {
			e.preventDefault();
			all_checked = !all_checked;
			$dlg.find('.eas-pick-chk').prop('checked', all_checked)
				.closest('.eas-pick-item').toggleClass('is-checked', all_checked);
			_update_counter();
		});
	}

	// ── Export Excel ───────────────────────────────────────────────────────────
	_export_excel(course, mode, from_date, to_date, selected_courses) {
		frappe.show_alert({
			message: course ? `Preparing ${course} sheet…` : 'Preparing Excel…',
			indicator: 'blue'
		});
		frappe.call({
			method: 'slcm.slcm.page.exam_barcode_sheet.exam_barcode_sheet.export_attendance_excel',
			args: {
				exam_plan:        this.exam_plan,
				course:           course           || '',
				mode:             mode             || 'by_date',
				from_date:        from_date        || '',
				to_date:          to_date          || '',
				selected_courses: selected_courses || '',
			},
			callback: r => {
				if (r.exc || !r.message) {
					frappe.show_alert({ message: 'Failed to generate Excel.', indicator: 'red' });
					return;
				}
				const { file_content, filename } = r.message;
				const link = document.createElement('a');
				link.href = 'data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,' + file_content;
				link.download = filename;
				document.body.appendChild(link);
				link.click();
				document.body.removeChild(link);
				frappe.show_alert({ message: `Downloaded: ${filename}`, indicator: 'green' });
			}
		});
	}
}
