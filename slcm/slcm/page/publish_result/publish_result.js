frappe.pages['publish-result'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Publish Results',
		single_column: true,
	});

	// Shared brand theme (#920C24 + Merriweather) for all Examination Result tabs
	$(wrapper).addClass('er-theme');
	if (!document.getElementById('er-theme-font')) {
		$('head').append(
			'<link rel="preconnect" href="https://fonts.googleapis.com">' +
			'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' +
			'<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">'
		);
	}
	frappe.require('/assets/slcm/css/exam_results_theme.css');
	// On narrow screens the tab strip scrolls sideways — bring the active tab into view
	setTimeout(function () {
		var $nav = $(wrapper).find('.er2-page-nav'), $act = $nav.find('.er2-pnav-btn.active');
		if ($nav.length && $act.length) $nav.scrollLeft($act.position().left + $nav.scrollLeft() - 12);
	}, 0);

	// ── CSS ───────────────────────────────────────────────────────────────────
	if (!document.getElementById('pr-style')) {
		var style = document.createElement('style');
		style.id  = 'pr-style';
		style.textContent = `
		.er2-wrap        { font-family:var(--font-stack,'Inter',sans-serif); padding:0; background:#f1f5f9; min-height:100vh; }
		.er2-page-header { background:#fff; border-radius:12px; padding:20px 24px; margin-bottom:16px;
		                   box-shadow:0 1px 3px rgba(0,0,0,.06); display:flex; align-items:center; gap:16px; }
		.er2-page-icon   { width:46px; height:46px; border-radius:12px; flex-shrink:0;
		                   display:flex; align-items:center; justify-content:center; }
		.er2-page-title  { font-size:17px; font-weight:800; color:#0f172a; line-height:1.2; }
		.er2-page-sub    { font-size:12px; color:#94a3b8; margin-top:3px; font-weight:500; }
		.er2-page-nav    { display:flex; gap:4px; margin-bottom:16px; background:#e2e8f0;
		                   border-radius:10px; padding:4px; width:fit-content; }
		.er2-pnav-btn    { padding:8px 18px; cursor:pointer; font-size:13px; font-weight:600;
		                   color:#64748b; border-radius:7px; transition:all .2s; user-select:none;
		                   letter-spacing:.1px; border:none; background:transparent;
		                   display:inline-flex; align-items:center; gap:5px; }
		.er2-pnav-btn:hover  { color:#920C24; background:rgba(146,12,36,.08); }
		.er2-pnav-btn.active { background:#fff; color:#920C24; box-shadow:0 1px 4px rgba(0,0,0,.12); }

		/* Stat cards */
		.pr-stat-cards   { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
		.pr-stat-card    { background:#fff; border-radius:12px; padding:14px 18px; flex:1;
		                   min-width:150px; box-shadow:0 1px 3px rgba(0,0,0,.06);
		                   border-top:3px solid var(--sc-color,#920C24);
		                   display:flex; align-items:center; gap:12px; }
		.pr-sc-icon      { width:38px; height:38px; border-radius:9px; flex-shrink:0;
		                   display:flex; align-items:center; justify-content:center;
		                   background:var(--sc-bg,#FBEEF0); color:var(--sc-color,#920C24); }
		.pr-sc-val       { font-size:22px; font-weight:800; color:var(--sc-color,#920C24); line-height:1.1; }
		.pr-sc-lbl       { font-size:10px; color:#94a3b8; font-weight:700; text-transform:uppercase;
		                   letter-spacing:.6px; margin-top:2px; }

		/* Filter card */
		.pr-filter-card  { background:#fff; border-radius:12px; padding:14px 20px; margin-bottom:14px;
		                   box-shadow:0 1px 3px rgba(0,0,0,.06); display:flex; gap:14px;
		                   align-items:flex-end; flex-wrap:wrap; }
		.pr-fgroup       { display:flex; flex-direction:column; min-width:200px; flex:1; max-width:300px; }
		.pr-fgroup.wide  { max-width:400px; }
		.pr-filter-arrow { display:flex; align-items:flex-end; padding-bottom:9px; color:#cbd5e1; font-size:16px; flex-shrink:0; }
		.pr-active-badge { display:inline-block; border-radius:6px; font-size:10px; font-weight:700;
		                   padding:2px 7px; margin-left:6px; letter-spacing:.3px; vertical-align:middle; }
		.pr-active-badge.prog  { background:#FBEEF0; color:#920C24; }
		.pr-active-badge.course { background:#FBEEF0; color:#920C24; }
		.pr-flabel       { font-size:11px; color:#94a3b8; font-weight:700; margin-bottom:5px;
		                   text-transform:uppercase; letter-spacing:.6px; }
		.pr-select       { height:36px; border:1.5px solid #e2e8f0; border-radius:8px;
		                   padding:0 12px; font-size:13px; background:#fff; color:#1e293b;
		                   outline:none; cursor:pointer; transition:border-color .2s; }
		.pr-select:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }

		/* Action bar */
		.pr-actbar       { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
		.pr-srch         { flex:1; min-width:200px; max-width:380px; position:relative; }
		.pr-srch input   { width:100%; height:36px; border:1.5px solid #e2e8f0; border-radius:8px;
		                   padding:0 12px 0 36px; font-size:13px; outline:none; color:#1e293b;
		                   background:#fff; transition:border-color .2s; box-sizing:border-box; }
		.pr-srch input:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }
		.pr-srch-ico     { position:absolute; left:10px; top:10px; color:#94a3b8; }
		.pr-btn          { height:36px; padding:0 14px; border-radius:7px; border:1.5px solid #e2e8f0;
		                   background:#fff; cursor:pointer; font-size:12.5px; font-weight:600;
		                   color:#475569; display:inline-flex; align-items:center; gap:5px;
		                   white-space:nowrap; transition:all .15s; }
		.pr-btn:hover    { background:#f8fafc; border-color:#cbd5e1; color:#1e293b; }
		.pr-btn.primary  { background:#920C24;
		                   border-color:transparent; color:#fff; }
		.pr-btn.primary:hover { opacity:.9; }

		/* Dropdown */
		.pr-btn-dd       { position:relative; display:inline-flex; }
		.pr-btn-dd .dd-menu { display:none; position:absolute; top:calc(100% + 4px); right:0; z-index:999;
		                   background:#fff; border:1.5px solid #e2e8f0; border-radius:9px;
		                   box-shadow:0 8px 24px rgba(0,0,0,.12); min-width:170px; padding:5px; }
		.pr-btn-dd.open .dd-menu { display:block; }
		.dd-item         { padding:8px 12px; font-size:12.5px; cursor:pointer; color:#475569;
		                   border-radius:6px; font-weight:500; }
		.dd-item:hover   { background:#f1f5f9; color:#1e293b; }

		/* Table */
		.pr-tbl-header   { display:flex; align-items:center; margin-bottom:10px; padding:0 2px; }
		.pr-count-lbl    { font-size:13px; font-weight:700; color:#0f172a; }
		.pr-table-card   { background:#fff; border-radius:12px; box-shadow:0 1px 3px rgba(0,0,0,.06); overflow:hidden; }
		.pr-table-scroll { overflow-x:auto; }
		.pr-table        { width:100%; border-collapse:collapse; font-size:13px; min-width:1050px; }
		.pr-table thead tr { background:#f8fafc; }
		.pr-table th     { padding:10px 14px; text-align:left; font-size:11px; font-weight:700;
		                   color:#475569; border-bottom:1.5px solid #e2e8f0; white-space:nowrap;
		                   text-transform:uppercase; letter-spacing:.4px; background:#f8fafc;
		                   position:sticky; top:0; z-index:5; }
		.pr-table th.center { text-align:center; }
		.pr-table td     { padding:0 14px; border-bottom:1.5px solid #f1f5f9; vertical-align:middle; white-space:nowrap; }
		.pr-table tbody tr { height:72px; }
		.pr-table tbody tr:hover td { background:#FDF8F9; }
		.pr-table tbody tr:last-child td { border-bottom:none; }

		/* Student cell */
		.pr-savatar      { width:40px; height:40px; border-radius:10px; flex-shrink:0;
		                   display:flex; align-items:center; justify-content:center;
		                   font-size:14px; font-weight:700; color:#fff; overflow:hidden; }
		.pr-savatar img  { width:100%; height:100%; object-fit:cover; }
		.pr-sname        { font-size:13px; font-weight:700; color:#0f172a; }
		.pr-sreg         { font-size:11px; color:#920C24; font-weight:600; margin-top:2px;
		                   background:#FBEEF0; border-radius:4px; padding:1px 6px; display:inline-block; }
		.pr-semail       { font-size:11px; color:#94a3b8; margin-top:2px; }

		/* Publish status header filter */
		.pr-status-hdr   { display:inline-flex; align-items:center; gap:4px; cursor:pointer; user-select:none; position:relative; }
		.pr-status-hdr:hover { color:#920C24; }
		.pr-status-dd    { display:none; position:absolute; top:calc(100% + 8px); left:50%;
		                   transform:translateX(-50%); z-index:999; background:#fff;
		                   border:1.5px solid #e2e8f0; border-radius:9px;
		                   box-shadow:0 8px 24px rgba(0,0,0,.12); min-width:140px; padding:5px; }
		.pr-status-hdr.open .pr-status-dd { display:block; }
		.pr-status-dd .dd-item.active { color:#920C24; font-weight:700; background:#FBEEF0; }

		/* Toggle */
		.pr-toggle       { position:relative; display:inline-block; width:44px; height:24px; cursor:pointer; }
		.pr-toggle input { opacity:0; width:0; height:0; }
		.pr-toggle-slider { position:absolute; inset:0; background:#cbd5e1; border-radius:24px; transition:background .2s; }
		.pr-toggle-slider:before { content:''; position:absolute; width:18px; height:18px;
		                           left:3px; bottom:3px; background:#fff; border-radius:50%;
		                           transition:transform .2s; box-shadow:0 1px 3px rgba(0,0,0,.2); }
		.pr-toggle input:checked + .pr-toggle-slider { background:#920C24; }
		.pr-toggle input:checked + .pr-toggle-slider:before { transform:translateX(20px); }
		.pr-toggle.saving .pr-toggle-slider { opacity:.6; }

		/* Published by / unpublished by cells */
		.pr-pub-by       { line-height:1.5; }
		.pr-pub-role     { font-size:11px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:.3px; }
		.pr-pub-name     { font-size:12px; color:#475569; font-weight:500; }
		.pr-pub-date     { font-size:11px; color:#94a3b8; }
		.pr-pub-none     { font-size:12px; color:#cbd5e1; }
		.pr-unpub-name   { font-size:12px; color:#920C24; font-weight:500; }
		.pr-unpub-date   { font-size:11px; color:#E8B4BE; }

		/* Pagination */
		.pr-pag-bar      { display:flex; align-items:center; justify-content:space-between;
		                   padding:12px 16px; border-top:1.5px solid #f1f5f9; }
		.pr-pag-info     { font-size:12.5px; color:#64748b; }
		.pr-pag-btns     { display:flex; gap:4px; }
		.pr-pag-btn      { width:30px; height:30px; border:1.5px solid #e2e8f0; border-radius:7px;
		                   background:#fff; cursor:pointer; font-size:14px; display:inline-flex;
		                   align-items:center; justify-content:center; color:#64748b; transition:all .15s; }
		.pr-pag-btn:hover:not(:disabled) { background:#FBEEF0; border-color:#E8B4BE; color:#920C24; }
		.pr-pag-btn:disabled { opacity:.35; cursor:default; }

		/* Empty / Loading */
		.pr-empty        { padding:80px 20px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; }
		.pr-empty-icon   { width:56px; height:56px; border-radius:14px; background:#f1f5f9; display:flex; align-items:center; justify-content:center; margin-bottom:14px; }
		.pr-empty-txt    { font-size:14px; font-weight:700; color:#94a3b8; }
		.pr-empty-sub    { font-size:12px; color:#cbd5e1; margin-top:4px; }
		.pr-loading      { padding:60px; text-align:center; color:#94a3b8; font-size:13px; }

		/* Avatar colours */
		.av-0{background:#920C24;}
		.av-1{background:#920C24;}
		.av-2{background:#920C24;}
		.av-3{background:#920C24;}
		.av-4{background:#920C24;}
		.av-5{background:#920C24;}
		.av-6{background:#920C24;}
		.av-7{background:#920C24;}

		/* ── Institutional Filter Modal ── */
		.xif-overlay { position:fixed; inset:0; background:rgba(15,23,42,.35);
		               z-index:10000; display:flex; align-items:center; justify-content:center;
		               backdrop-filter:blur(2px); }
		.xif-modal   { background:#fff; border-radius:14px; width:660px; max-width:95vw;
		               max-height:85vh; display:flex; flex-direction:column;
		               box-shadow:0 20px 60px rgba(0,0,0,.18); overflow:hidden; }
		.xif-header  { display:flex; align-items:center; justify-content:space-between;
		               padding:16px 20px; border-bottom:1.5px solid #f1f5f9; }
		.xif-title   { font-size:15px; font-weight:700; color:#0f172a; }
		.xif-close   { width:30px; height:30px; border-radius:8px; border:none; background:#f1f5f9;
		               cursor:pointer; display:flex; align-items:center; justify-content:center;
		               color:#64748b; font-size:16px; transition:all .15s; }
		.xif-close:hover { background:#F5D9DE; color:#920C24; }
		.xif-body    { display:flex; flex:1; overflow:hidden; }
		.xif-types   { width:190px; flex-shrink:0; border-right:1.5px solid #f1f5f9; padding:8px; background:#FDF8F9; }
		.xif-type    { padding:10px 14px; border-radius:8px; font-size:13px; font-weight:600; color:#475569;
		               cursor:pointer; margin-bottom:2px; transition:all .15s; display:flex; align-items:center; gap:8px; }
		.xif-type:hover { background:#f1f5f9; color:#1e293b; }
		.xif-type.active { background:#FBEEF0; color:#920C24; }
		.xif-type-badge { min-width:18px; height:18px; border-radius:20px; background:#920C24; color:#fff;
		                  font-size:10px; font-weight:700; display:inline-flex; align-items:center;
		                  justify-content:center; padding:0 5px; margin-left:auto; }
		.xif-panel   { flex:1; display:flex; flex-direction:column; overflow:hidden; }
		.xif-ph      { padding:14px 16px 8px; border-bottom:1.5px solid #f1f5f9; }
		.xif-ph-title{ font-size:13px; font-weight:700; color:#1e293b; margin-bottom:8px; }
		.xif-search  { width:100%; height:32px; border:1.5px solid #e2e8f0; border-radius:8px;
		               padding:0 10px 0 30px; font-size:12.5px; outline:none; color:#1e293b;
		               background:#f8fafc url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2.5'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cline x1='21' y1='21' x2='16.65' y2='16.65'/%3E%3C/svg%3E") no-repeat 9px center;
		               box-sizing:border-box; transition:border-color .2s; }
		.xif-search:focus { border-color:#920C24; background-color:#fff; }
		.xif-opts    { flex:1; overflow-y:auto; padding:8px; }
		.xif-opt     { display:flex; align-items:center; gap:10px; padding:9px 12px; border-radius:8px;
		               cursor:pointer; font-size:13px; font-weight:500; color:#334155; transition:background .12s; }
		.xif-opt:hover { background:#f8fafc; }
		.xif-opt.checked { background:#FBEEF0; color:#920C24; }
		.xif-opt input[type="checkbox"] { width:15px; height:15px; accent-color:#920C24; cursor:pointer; flex-shrink:0; }
		.xif-empty-opts { padding:32px; text-align:center; color:#cbd5e1; font-size:13px; }
		.xif-footer  { display:flex; align-items:center; justify-content:space-between;
		               padding:12px 16px; border-top:1.5px solid #f1f5f9; background:#FDF8F9; }
		.xif-status  { font-size:12.5px; color:#64748b; font-weight:500; }
		.xif-status strong { color:#920C24; }
		.xif-actions { display:flex; gap:8px; }
		.xif-clear   { padding:0 14px; height:32px; border-radius:7px; border:1.5px solid #e2e8f0;
		               background:#fff; color:#64748b; font-size:12.5px; font-weight:600; cursor:pointer; transition:all .15s; }
		.xif-clear:hover { border-color:#920C24; color:#920C24; background:#FBEEF0; }
		.xif-apply   { padding:0 18px; height:32px; border-radius:7px; border:none;
		               background:#920C24; color:#fff;
		               font-size:12.5px; font-weight:700; cursor:pointer; transition:opacity .15s; }
		.xif-apply:hover { opacity:.88; }
		.xif-btn-active { background:linear-gradient(135deg,#FBEEF0,#F5D9DE) !important;
		                  border-color:#E8B4BE !important; color:#920C24 !important; }
		`;
		document.head.appendChild(style);
	}

	// ── State ─────────────────────────────────────────────────────────────────
	var S = {
		exam_plan:     null,
		programme:     '',
		course:        '',
		students:      [],
		total:         0,
		page:          1,
		page_length:   20,
		search:        '',
		sort_by:       'registration_id',
		sort_order:    'asc',
		status_filter: 'all',
		loading:       false,
		search_timer:  null,
		inst_filter:   { programmes: [], batches: [] },
		inst_options:  null,
	};

	// ── Render shell ──────────────────────────────────────────────────────────
	var $body = $(page.main);
	$body.html(`
		<div class="er2-wrap" style="padding:20px 24px;">

			<div class="er2-page-header">
				<div class="er2-page-icon" style="background:#920C24;">
					<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
				</div>
				<div>
					<div class="er2-page-title">Publish Results</div>
					<div class="er2-page-sub">Control result visibility and publish final results to students</div>
				</div>
			</div>

			<div class="er2-page-nav">
				<button class="er2-pnav-btn" onclick="frappe.set_route('examination-result')">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
					Course Results
				</button>
				<button class="er2-pnav-btn" onclick="frappe.set_route('term-result')">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
					Term Results
				</button>
				<button class="er2-pnav-btn active">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
					Publish Results
				</button>
				<button class="er2-pnav-btn" onclick="frappe.set_route('result-settings')">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
					Settings
				</button>
				<button class="er2-pnav-btn" onclick="frappe.set_route('re-exam')">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.51"/></svg>
					Re Exam
				</button>
				<button class="er2-pnav-btn" onclick="frappe.set_route('improvement-exam')">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
					Improvement Exam
				</button>
				<button class="er2-pnav-btn" id="tr-nav-consolidated">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
					Consolidated Report
				</button>
			</div>

			<!-- Filter card -->
			<div class="pr-filter-card">
				<div class="pr-fgroup">
					<span class="pr-flabel">
						<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/></svg>
						Exam Plan
					</span>
					<select class="pr-select" id="pr-exam-plan">
						<option value="">Choose Exam Plan</option>
					</select>
				</div>

				<div class="pr-filter-arrow" id="pr-prog-arrow" style="display:none;">&#8594;</div>

				<div class="pr-fgroup" id="pr-prog-group" style="display:none;">
					<span class="pr-flabel">
						<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
						Programme
						<span class="pr-active-badge prog" id="pr-prog-badge" style="display:none;">Filtered</span>
					</span>
					<select class="pr-select" id="pr-prog-select">
						<option value="">All Programmes</option>
					</select>
				</div>

				<div class="pr-filter-arrow" id="pr-course-arrow" style="display:none;">&#8594;</div>

				<div class="pr-fgroup wide" id="pr-course-group" style="display:none;">
					<span class="pr-flabel">
						<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
						Course
						<span class="pr-active-badge course" id="pr-course-badge" style="display:none;">Filtered</span>
					</span>
					<select class="pr-select" id="pr-course-select">
						<option value="">All Courses</option>
					</select>
				</div>
			</div>

			<!-- Content -->
			<div id="pr-content" style="display:none;">

				<!-- Stat cards -->
				<div class="pr-stat-cards" id="pr-stat-cards" style="display:none;"></div>

				<!-- Action bar -->
				<div class="pr-actbar">
					<div class="pr-srch">
						<svg class="pr-srch-ico" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
						<input id="pr-search" type="text" placeholder="Search by student name or id">
					</div>
					<div style="margin-left:auto;display:flex;gap:8px;align-items:center;">
						<button class="pr-btn" id="pr-inst-filter-btn">
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
							Institutional Filter
						</button>
						<button class="pr-btn" id="pr-bulk-email-btn">
							<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16v16H4z"/><path d="m4 4 8 8 8-8"/></svg>
							Send Bulk Email
						</button>
						<div class="pr-btn-dd" id="pr-publish-dd">
							<button class="pr-btn primary" id="pr-publish-btn">
								<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
								Publish
								<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"/></svg>
							</button>
							<div class="dd-menu">
								<div class="dd-item" id="pr-pub-selected">Publish Selected</div>
								<div class="dd-item" id="pr-unpub-selected">Unpublish Selected</div>
								<div class="dd-item" id="pr-pub-all" style="border-top:1px solid #f1f5f9;margin-top:4px;padding-top:10px;">Publish All</div>
								<div class="dd-item" id="pr-unpub-all">Unpublish All</div>
							</div>
						</div>
					</div>
				</div>

				<!-- Table header row -->
				<div class="pr-tbl-header">
					<span id="pr-count-lbl" class="pr-count-lbl">Students (0)</span>
				</div>

				<div class="pr-table-card">
					<div class="pr-table-scroll">
						<div id="pr-table-body"></div>
					</div>
					<div class="pr-pag-bar" id="pr-pag-bar" style="display:none;">
						<span id="pr-pag-info" class="pr-pag-info"></span>
						<div class="pr-pag-btns">
							<button class="pr-pag-btn" id="pr-prev" disabled>&#8592;</button>
							<button class="pr-pag-btn" id="pr-next" disabled>&#8594;</button>
						</div>
					</div>
				</div>

			</div>
		</div>
	`);

	// ── DOM refs ──────────────────────────────────────────────────────────────
	var $examPlan     = $body.find('#pr-exam-plan');
	var $progGroup    = $body.find('#pr-prog-group');
	var $progArrow    = $body.find('#pr-prog-arrow');
	var $progSelect   = $body.find('#pr-prog-select');
	var $progBadge    = $body.find('#pr-prog-badge');
	var $courseArrow  = $body.find('#pr-course-arrow');
	var $courseGroup  = $body.find('#pr-course-group');
	var $courseSelect = $body.find('#pr-course-select');
	var $courseBadge  = $body.find('#pr-course-badge');
	var $content      = $body.find('#pr-content');
	var $search       = $body.find('#pr-search');
	var $tableBody    = $body.find('#pr-table-body');
	var $countLbl     = $body.find('#pr-count-lbl');
	var $pagBar       = $body.find('#pr-pag-bar');
	var $pagInfo      = $body.find('#pr-pag-info');
	var $prev         = $body.find('#pr-prev');
	var $next         = $body.find('#pr-next');
	var $statCards    = $body.find('#pr-stat-cards');

	// ── Load Exam Plans ───────────────────────────────────────────────────────
	frappe.call({
		method: 'slcm.slcm.page.publish_result.publish_result.get_exam_plans',
		callback: function (r) {
			if (!r.message) return;
			r.message.forEach(function (ep) {
				$examPlan.append('<option value="' + ep.name + '">' +
					frappe.utils.escape_html(ep.exam_name || ep.name) +
					(ep.status === 'Active' ? ' [Active]' : '') + '</option>');
			});
		},
	});

	// ── Exam Plan change ──────────────────────────────────────────────────────
	$examPlan.on('change', function () {
		S.exam_plan     = $(this).val();
		S.programme     = '';
		S.course        = '';
		S.page          = 1;
		S.search        = '';
		S.status_filter = 'all';
		S.inst_filter   = { programmes: [], batches: [] };
		S.inst_options  = null;
		$search.val('');
		$body.find('#pr-inst-filter-btn').removeClass('xif-btn-active').find('.xif-count').remove();
		$progSelect.val('');  $progBadge.hide();
		$courseSelect.val(''); $courseBadge.hide();
		if (S.exam_plan) {
			$content.show();
			loadProgrammes();
			loadCourses();
			loadStats();
			loadStudents();
		} else {
			$content.hide();
			$statCards.hide();
			$progGroup.hide(); $progArrow.hide();
			$courseGroup.hide(); $courseArrow.hide();
		}
	});

	// ── Programme change ──────────────────────────────────────────────────────
	$progSelect.on('change', function () {
		S.programme = $(this).val();
		S.course    = '';
		S.page      = 1;
		$courseSelect.val(''); $courseBadge.hide();
		$progBadge.toggle(!!S.programme);
		// Re-load courses scoped to this programme
		loadCourses();
		loadStats();
		loadStudents();
	});

	// ── Course change ─────────────────────────────────────────────────────────
	$courseSelect.on('change', function () {
		S.course = $(this).val();
		S.page   = 1;
		$courseBadge.toggle(!!S.course);
		loadStats();
		loadStudents();
	});

	// ── Search ────────────────────────────────────────────────────────────────
	$search.on('input', function () {
		clearTimeout(S.search_timer);
		S.search_timer = setTimeout(function () {
			S.search = $search.val().trim();
			S.page = 1;
			loadStudents();
		}, 350);
	});

	// ── Dropdown ─────────────────────────────────────────────────────────────
	$body.find('#pr-publish-dd button').first().on('click', function (e) {
		e.stopPropagation();
		var $dd = $(this).closest('.pr-btn-dd');
		var wasOpen = $dd.hasClass('open');
		$body.find('.pr-btn-dd').removeClass('open');
		if (!wasOpen) $dd.addClass('open');
	});
	$(document).on('click.pr_dd', function () { $body.find('.pr-btn-dd').removeClass('open'); });

	// ── Consolidated Report Dialog ───────────────────────────────────────────
	$body.find('#tr-nav-consolidated').on('click', function () {
		var d = new frappe.ui.Dialog({
			title: 'Download Consolidated Report',
			fields: [
				{ label: 'Exam Plan',     fieldname: 'exam_plan',     fieldtype: 'Link',   options: 'Exam Plan',     default: S.exam_plan || '' },
				{ fieldtype: 'Column Break' },
				{ label: 'Academic Year', fieldname: 'academic_year', fieldtype: 'Link',   options: 'Academic Year' },
				{ fieldtype: 'Section Break' },
				{ label: 'Programme',     fieldname: 'programme',     fieldtype: 'Link',   options: 'Programme',
					onchange() { d.set_value('trimester', ''); d.set_value('course', ''); } },
				{ fieldtype: 'Column Break' },
				{ label: 'Trimester',     fieldname: 'trimester',     fieldtype: 'Link',   options: 'Academic Term',
					get_query() {
						return {
							query: 'slcm.slcm.page.examination_result.examination_result.trimester_link_query',
							filters: { programme: d.get_value('programme') },
						};
					},
					onchange() { d.set_value('course', ''); } },
				{ fieldtype: 'Section Break' },
				{ label: 'Batch',         fieldname: 'batch',         fieldtype: 'Link', options: 'Batch' },
				{ fieldtype: 'Section Break' },
				{ label: 'Report Type',   fieldname: 'report_type',   fieldtype: 'Select', options: 'Bulk\nCourse Based', default: 'Bulk' },
				{ fieldtype: 'Column Break' },
				{ label: 'Course',        fieldname: 'course',        fieldtype: 'Link',   options: 'Course Offering', depends_on: 'eval:doc.report_type=="Course Based"',
					get_query() {
						var filters = {};
						if (d.get_value('programme')) filters.program = d.get_value('programme');
						if (d.get_value('trimester'))  filters.term_name = d.get_value('trimester');
						return { filters: filters };
					} }
			],
			primary_action_label: 'Download Excel',
			primary_action: function(v) {
				var args = {};
				if (v.exam_plan)     args.exam_plan     = v.exam_plan;
				if (v.academic_year) args.academic_year = v.academic_year;
				if (v.programme)     args.programme     = v.programme;
				if (v.trimester)     args.trimester      = v.trimester;
				if (v.batch)         args.batch          = v.batch;
				if (v.report_type === 'Course Based' && v.course) args.course_offering = v.course;
				if (!Object.keys(args).length) {
					frappe.msgprint('Please select at least one filter.');
					return;
				}
				var url = '/api/method/slcm.slcm.page.term_result.term_result.download_consolidated_report?' + $.param(args);
				window.open(url, '_blank');
				d.hide();
			}
		});
		d.show();
	});

	// ── Send Bulk Email ──────────────────────────────────────────────────────
	$body.find('#pr-bulk-email-btn').on('click', function () {
		if (!S.exam_plan) { frappe.show_alert({ message: 'Select an Exam Plan first.', indicator: 'orange' }); return; }

		var d = new frappe.ui.Dialog({
			title: 'Send Bulk Email',
			fields: [
				{
					fieldtype: 'HTML',
					options: '<div class="text-muted" style="margin-bottom:10px;">' +
						'Sends to every student currently matching the page filters (Programme/Course/search/status) — ' +
						'not just the students visible on this page.' +
						'</div>',
				},
				{ label: 'Email Template', fieldname: 'email_template', fieldtype: 'Link', options: 'Email Template', reqd: 1 },
			],
			primary_action_label: 'Send',
			primary_action: function (v) {
				if (!v.email_template) { frappe.msgprint('Select an Email Template.'); return; }
				d.set_primary_action('Sending…');
				d.disable_primary_action();
				frappe.call({
					method: 'slcm.slcm.page.publish_result.publish_result.send_bulk_publish_email',
					args: {
						exam_plan:       S.exam_plan,
						email_template:  v.email_template,
						search:          S.search,
						status_filter:   S.status_filter,
						inst_programmes: JSON.stringify(S.inst_filter.programmes),
						inst_batches:    JSON.stringify(S.inst_filter.batches),
						programme:       S.programme || '',
						course:          S.course || '',
					},
					callback: function (r) {
						d.hide();
						if (r.message) {
							frappe.show_alert({ message: r.message.message, indicator: 'green' });
						}
					},
					error: function () {
						d.enable_primary_action();
						d.set_primary_action('Send');
					},
				});
			},
		});
		d.show();
	});

	// ── Publish actions ───────────────────────────────────────────────────────
	$body.find('#pr-pub-selected').on('click',   function () { var s = getSelected(); if (!s.length) { frappe.show_alert({message:'No students selected', indicator:'orange'}); return; } bulkPublish(s, 1); });
	$body.find('#pr-unpub-selected').on('click', function () { var s = getSelected(); if (!s.length) { frappe.show_alert({message:'No students selected', indicator:'orange'}); return; } bulkPublish(s, 0); });
	$body.find('#pr-pub-all').on('click',        function () { bulkPublish(S.students.map(function (s) { return s.student; }), 1); });
	$body.find('#pr-unpub-all').on('click',      function () { bulkPublish(S.students.map(function (s) { return s.student; }), 0); });

	// ── Institutional Filter ──────────────────────────────────────────────────
	$body.find('#pr-inst-filter-btn').on('click', function () {
		if (!S.exam_plan) { frappe.show_alert({message:'Select an Exam Plan first.', indicator:'orange'}); return; }
		if (S.inst_options) {
			show_inst_filter_dialog(S.inst_options);
		} else {
			frappe.call({
				method: 'slcm.slcm.page.publish_result.publish_result.get_publish_inst_filter_options',
				args:   { exam_plan: S.exam_plan },
				callback: function (r) {
					S.inst_options = r.message || { programmes: [], batches: [] };
					show_inst_filter_dialog(S.inst_options);
				},
			});
		}
	});

	// ── Pagination ────────────────────────────────────────────────────────────
	$prev.on('click', function () { if (S.page > 1) { S.page--; loadStudents(); } });
	$next.on('click', function () { if (S.page < Math.ceil(S.total / S.page_length)) { S.page++; loadStudents(); } });

	// ── Load Programmes ───────────────────────────────────────────────────────
	function loadProgrammes() {
		if (!S.exam_plan) return;
		frappe.call({
			method: 'slcm.slcm.page.publish_result.publish_result.get_programmes_for_exam_plan',
			args:   { exam_plan: S.exam_plan },
			callback: function (r) {
				var progs = r.message || [];
				$progSelect.empty().append('<option value="">All Programmes</option>');
				progs.forEach(function (p) {
					var label = (p.programme_name && p.programme_name !== p.programme)
						? frappe.utils.escape_html(p.programme_name)
						: frappe.utils.escape_html(p.programme);
					$progSelect.append('<option value="' + frappe.utils.escape_html(p.programme) + '">' + label + '</option>');
				});
				if (progs.length > 0) {
					$progGroup.show(); $progArrow.show();
				} else {
					$progGroup.hide(); $progArrow.hide();
				}
			},
		});
	}

	// ── Load Courses ──────────────────────────────────────────────────────────
	function loadCourses() {
		if (!S.exam_plan) return;
		frappe.call({
			method: 'slcm.slcm.page.publish_result.publish_result.get_courses_for_exam_plan',
			args:   { exam_plan: S.exam_plan, programme: S.programme || '' },
			callback: function (r) {
				var courses = r.message || [];
				$courseSelect.empty().append('<option value="">All Courses</option>');
				courses.forEach(function (c) {
					var label = (c.course_name && c.course_name !== c.course)
						? frappe.utils.escape_html(c.course_name) + ' (' + frappe.utils.escape_html(c.course) + ')'
						: frappe.utils.escape_html(c.course);
					$courseSelect.append('<option value="' + frappe.utils.escape_html(c.course) + '">' + label + '</option>');
				});
				if (courses.length > 0) {
					$courseGroup.show(); $courseArrow.show();
				} else {
					$courseGroup.hide(); $courseArrow.hide();
				}
			},
		});
	}

	// ── Load Stats ────────────────────────────────────────────────────────────
	function loadStats() {
		if (!S.exam_plan) return;
		frappe.call({
			method: 'slcm.slcm.page.publish_result.publish_result.get_publish_stats',
			args:   { exam_plan: S.exam_plan, programme: S.programme || '', course: S.course || '' },
			callback: function (r) {
				if (!r.message) return;
				var d = r.message;
				var cards = [
					{ label:'Total Students', value: d.total         || 0, color:'#920C24', bg:'#FBEEF0',
					  icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>' },
					{ label:'Published',      value: d.published     || 0, color:'#920C24', bg:'#F5D9DE',
					  icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>' },
					{ label:'Not Published',  value: d.not_published || 0, color:'#920C24', bg:'#F5D9DE',
					  icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' },
				];
				var html = cards.map(function (c) {
					return '<div class="pr-stat-card" style="--sc-color:' + c.color + ';--sc-bg:' + c.bg + ';">' +
						'<div class="pr-sc-icon">' + c.icon + '</div>' +
						'<div><div class="pr-sc-val">' + c.value + '</div><div class="pr-sc-lbl">' + c.label + '</div></div></div>';
				}).join('');
				$statCards.html(html).show();
			},
		});
	}

	// ── Load Students ─────────────────────────────────────────────────────────
	function loadStudents() {
		if (!S.exam_plan || S.loading) return;
		S.loading = true;
		$tableBody.html('<div class="pr-loading"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" style="animation:spin 1s linear infinite;vertical-align:-6px;margin-right:6px;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>Loading students…</div>');
		if (!document.getElementById('pr-spin-style')) {
			var ss = document.createElement('style'); ss.id = 'pr-spin-style';
			ss.textContent = '@keyframes spin{to{transform:rotate(360deg)}}';
			document.head.appendChild(ss);
		}
		frappe.call({
			method: 'slcm.slcm.page.publish_result.publish_result.get_publish_students',
			args: {
				exam_plan:       S.exam_plan,
				search:          S.search,
				page:            S.page,
				page_length:     S.page_length,
				status_filter:   S.status_filter,
				sort_by:         S.sort_by,
				sort_order:      S.sort_order,
				inst_programmes: JSON.stringify(S.inst_filter.programmes),
				inst_batches:    JSON.stringify(S.inst_filter.batches),
				programme:       S.programme || '',
				course:          S.course || '',
			},
			callback: function (r) {
				S.loading = false;
				if (!r.message) return;
				S.students = r.message.students || [];
				S.total    = r.message.total    || 0;
				renderTable();
				renderPagination();
			},
			error: function () {
				S.loading = false;
				$tableBody.html('<div class="pr-empty"><div class="pr-empty-icon">⚠</div><div class="pr-empty-txt">Failed to load students</div></div>');
			},
		});
	}

	// ── Render Table ──────────────────────────────────────────────────────────
	function renderTable() {
		var countLabel = 'Students (' + S.total + ')';
		if (S.programme) {
			var progLbl = $progSelect.find('option:selected').text() || S.programme;
			countLabel += ' &nbsp;<span style="font-size:11px;color:#920C24;font-weight:600;background:#FBEEF0;border-radius:5px;padding:2px 8px;">' + frappe.utils.escape_html(progLbl) + '</span>';
		}
		if (S.course) {
			var courseLbl = $courseSelect.find('option:selected').text() || S.course;
			countLabel += ' &nbsp;<span style="font-size:11px;color:#920C24;font-weight:600;background:#FBEEF0;border-radius:5px;padding:2px 8px;">' + frappe.utils.escape_html(courseLbl) + '</span>';
		}
		$countLbl.html(countLabel);
		if (!S.students.length) {
			$tableBody.html('<div class="pr-empty"><div class="pr-empty-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg></div><div class="pr-empty-txt">No students found</div><div class="pr-empty-sub">Try a different exam plan or filter</div></div>');
			$pagBar.hide(); return;
		}

		var sfLabel = S.status_filter === 'published' ? 'Published' : S.status_filter === 'not_published' ? 'Not Published' : 'All';

		function pubByCell(name, date, isUnpub) {
			if (!name) return '<span class="pr-pub-none">—</span>';
			var dt = date ? String(date).substring(0, 19).replace('T', ' ') : '';
			return '<div class="pr-pub-by">' +
				'<div class="pr-pub-role">' + (isUnpub ? 'UNPUBLISHED BY' : 'ADMINISTRATOR') + '</div>' +
				'<div class="' + (isUnpub ? 'pr-unpub-name' : 'pr-pub-name') + '">' + frappe.utils.escape_html(name) + '</div>' +
				(dt ? '<div class="' + (isUnpub ? 'pr-unpub-date' : 'pr-pub-date') + '">' + frappe.utils.escape_html(dt) + '</div>' : '') +
				'</div>';
		}

		var rows = S.students.map(function (s, idx) {
			var initials = (s.student_name || 'S').split(' ').map(function (w) { return w[0]; }).join('').substring(0, 2).toUpperCase();
			var avClass  = 'av-' + (idx % 8);
			var avatar   = s.image ? '<img src="' + frappe.utils.escape_html(s.image) + '" alt="">' : initials;
			var stuEsc   = frappe.utils.escape_html(s.student);

			return '<tr>' +
				'<td style="width:40px;"><input type="checkbox" class="pr-row-chk" data-student="' + stuEsc + '" style="accent-color:#920C24;cursor:pointer;"></td>' +
				'<td style="min-width:220px;">' +
					'<div style="display:flex;align-items:center;gap:10px;">' +
					'<div class="pr-savatar ' + avClass + '">' + avatar + '</div>' +
					'<div>' +
						'<div class="pr-sname">' + frappe.utils.escape_html(s.student_name || s.student) + '</div>' +
						'<div class="pr-sreg">' + frappe.utils.escape_html(s.registration_id || s.student) + '</div>' +
						(s.email ? '<div class="pr-semail">' + frappe.utils.escape_html(s.email) + '</div>' : '') +
					'</div></div>' +
				'</td>' +
				'<td style="min-width:200px;">' + frappe.utils.escape_html(s.programme || '—') + '</td>' +
				'<td style="min-width:120px;text-align:center;">' +
					'<label class="pr-toggle" data-student="' + stuEsc + '">' +
					'<input type="checkbox" class="pr-pub-toggle" ' + (s.is_published ? 'checked' : '') + '>' +
					'<span class="pr-toggle-slider"></span></label>' +
				'</td>' +
				'<td style="min-width:190px;">' + pubByCell(s.published_by_name, s.published_on, false) + '</td>' +
				'<td style="min-width:190px;">' + pubByCell(s.unpublished_by_name, s.unpublished_on, true) + '</td>' +
			'</tr>';
		});

		var thead = '<table class="pr-table"><thead><tr>' +
			'<th style="width:40px;"><input type="checkbox" id="pr-chk-all" style="accent-color:#920C24;cursor:pointer;"></th>' +
			'<th>Student</th>' +
			'<th>Programme</th>' +
			'<th class="center"><span class="pr-status-hdr" id="pr-status-hdr">Publish Status' +
				(S.status_filter !== 'all' ? ' <span style="color:#920C24;">(' + sfLabel + ')</span>' : '') +
				' <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"/></svg>' +
				'<div class="pr-status-dd">' +
				'<div class="dd-item' + (S.status_filter==='all'?' active':'') + '" data-filter="all">All</div>' +
				'<div class="dd-item' + (S.status_filter==='published'?' active':'') + '" data-filter="published">Published</div>' +
				'<div class="dd-item' + (S.status_filter==='not_published'?' active':'') + '" data-filter="not_published">Not Published</div>' +
				'</div></span></th>' +
			'<th>Result Published By</th>' +
			'<th>Unpublished By</th>' +
			'</tr></thead><tbody>' + rows.join('') + '</tbody></table>';

		$tableBody.html(thead);
		$pagBar.show();

		$tableBody.find('#pr-chk-all').on('change', function () {
			$tableBody.find('.pr-row-chk').prop('checked', $(this).is(':checked'));
		});
		$tableBody.on('click', '#pr-status-hdr', function (e) {
			e.stopPropagation(); $(this).toggleClass('open');
		});
		$tableBody.on('click', '.pr-status-dd .dd-item', function (e) {
			e.stopPropagation();
			S.status_filter = $(this).data('filter');
			S.page = 1;
			$tableBody.find('#pr-status-hdr').removeClass('open');
			loadStudents();
		});
		$(document).off('click.pr_stdd').on('click.pr_stdd', function () {
			$tableBody.find('#pr-status-hdr').removeClass('open');
		});
	}

	// ── Render Pagination ─────────────────────────────────────────────────────
	function renderPagination() {
		var totalPages = Math.ceil(S.total / S.page_length);
		var from = Math.min((S.page - 1) * S.page_length + 1, S.total);
		var to   = Math.min(S.page * S.page_length, S.total);
		$pagInfo.text(from + '–' + to + ' of ' + S.total);
		$prev.prop('disabled', S.page <= 1);
		$next.prop('disabled', S.page >= totalPages);
	}

	// ── Toggle publish (single row) ───────────────────────────────────────────
	$body.on('change', '.pr-pub-toggle', function () {
		var $toggle = $(this);
		var $lbl    = $toggle.closest('.pr-toggle');
		var student = $lbl.data('student');
		var publish = $toggle.is(':checked') ? 1 : 0;
		$lbl.addClass('saving'); $toggle.prop('disabled', true);

		frappe.call({
			method: 'slcm.slcm.page.publish_result.publish_result.toggle_publish',
			args:   { exam_plan: S.exam_plan, student: student, publish: publish },
			callback: function (r) {
				$lbl.removeClass('saving'); $toggle.prop('disabled', false);
				var info = r.message || {};
				var $row = $lbl.closest('tr');
				var $cells = $row.find('td');

				function pubCell(name, date, isUnpub) {
					if (!name) return '<span class="pr-pub-none">—</span>';
					var dt = date ? String(date).substring(0, 19).replace('T', ' ') : '';
					return '<div class="pr-pub-by"><div class="pr-pub-role">' + (isUnpub ? 'UNPUBLISHED BY' : 'ADMINISTRATOR') + '</div>' +
						'<div class="' + (isUnpub ? 'pr-unpub-name' : 'pr-pub-name') + '">' + frappe.utils.escape_html(name) + '</div>' +
						(dt ? '<div class="' + (isUnpub ? 'pr-unpub-date' : 'pr-pub-date') + '">' + frappe.utils.escape_html(dt) + '</div>' : '') + '</div>';
				}

				$cells.eq(4).html(pubCell(info.published_by_name,   info.published_on,   false));
				$cells.eq(5).html(pubCell(info.unpublished_by_name, info.unpublished_on, true));

				// Update local state
				var found = S.students.find(function (s) { return s.student === student; });
				if (found) {
					found.is_published         = publish;
					found.published_by_name    = info.published_by_name    || null;
					found.published_on         = info.published_on         || null;
					found.unpublished_by_name  = info.unpublished_by_name  || null;
					found.unpublished_on       = info.unpublished_on       || null;
				}

				frappe.show_alert({ message: publish ? 'Result published' : 'Result unpublished',
				                    indicator: publish ? 'green' : 'orange' });
				loadStats();
			},
			error: function () {
				$lbl.removeClass('saving'); $toggle.prop('checked', !publish); $toggle.prop('disabled', false);
				frappe.show_alert({message:'Failed to update publish status', indicator:'red'});
			},
		});
	});

	// ── Helpers ───────────────────────────────────────────────────────────────
	function getSelected() {
		var sel = [];
		$tableBody.find('.pr-row-chk:checked').each(function () { sel.push($(this).data('student')); });
		return sel;
	}

	function bulkPublish(students, publish) {
		if (!students.length || !S.exam_plan) return;
		frappe.show_alert({message: (publish ? 'Publishing' : 'Unpublishing') + ' ' + students.length + ' student(s)…', indicator:'blue'});
		frappe.call({
			method: 'slcm.slcm.page.publish_result.publish_result.bulk_publish',
			args:   { exam_plan: S.exam_plan, students: JSON.stringify(students), publish: publish },
			callback: function (r) {
				frappe.show_alert({ message: (publish ? 'Published' : 'Unpublished') + ' ' + (r.message || 0) + ' student(s)',
				                    indicator: publish ? 'green' : 'orange' });
				loadStats();
				loadStudents();
			},
		});
	}

	// ── Institutional Filter Dialog ───────────────────────────────────────────
	function show_inst_filter_dialog(opts) {
		var sel = { programmes: S.inst_filter.programmes.slice(), batches: S.inst_filter.batches.slice() };
		var TYPES = [
			{ key: 'programmes', label: 'Programme',
			  icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
			  items: opts.programmes },
			{ key: 'batches', label: 'Batch / Year',
			  icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
			  items: opts.batches },
		];
		var activeType = 0;
		function count_all() { return sel.programmes.length + sel.batches.length; }

		function render_types() {
			var html = '';
			TYPES.forEach(function (t, i) {
				var cnt = sel[t.key].length;
				html += '<div class="xif-type' + (i === activeType ? ' active' : '') + '" data-idx="' + i + '">' +
					t.icon + ' ' + t.label + (cnt ? '<span class="xif-type-badge">' + cnt + '</span>' : '') + '</div>';
			});
			$modal.find('.xif-types').html(html);
			$modal.find('.xif-type').on('click', function () { activeType = parseInt($(this).data('idx')); render_types(); render_panel(); });
		}

		function render_panel(sv) {
			var t = TYPES[activeType];
			var items = (t.items || []).filter(function (v) { return !sv || String(v).toLowerCase().includes(sv.toLowerCase()); });
			$modal.find('.xif-ph-title').text(t.label);
			var html = items.length ? items.map(function (v) {
				var chk = sel[t.key].indexOf(String(v)) !== -1;
				return '<div class="xif-opt' + (chk ? ' checked' : '') + '" data-val="' + frappe.utils.escape_html(String(v)) + '">' +
					'<input type="checkbox"' + (chk ? ' checked' : '') + '><span>' + frappe.utils.escape_html(String(v)) + '</span></div>';
			}).join('') : '<div class="xif-empty-opts">No options available</div>';
			$modal.find('.xif-opts').html(html);
			$modal.find('.xif-opt').on('click', function (e) {
				e.preventDefault();
				var val = $(this).data('val'), key = TYPES[activeType].key;
				var idx = sel[key].indexOf(String(val));
				if (idx === -1) sel[key].push(String(val)); else sel[key].splice(idx, 1);
				render_types(); render_panel($modal.find('.xif-search').val()); update_footer();
			});
		}

		function update_footer() {
			var total = count_all();
			var parts = [];
			if (sel.programmes.length) parts.push(sel.programmes.length + ' Programme(s)');
			if (sel.batches.length)    parts.push(sel.batches.length + ' Batch(es)');
			$modal.find('.xif-status').html(
				total ? '<strong>' + total + ' filter' + (total > 1 ? 's' : '') + '</strong> selected: ' + parts.join(', ')
				      : 'No Filters Applied'
			);
		}

		var $overlay = $('<div class="xif-overlay"></div>');
		var $modal = $('<div class="xif-modal"><div class="xif-header"><span class="xif-title"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2.5" style="vertical-align:-3px;margin-right:6px;"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>Institutional Filter</span><button class="xif-close">&#10005;</button></div><div class="xif-body"><div class="xif-types"></div><div class="xif-panel"><div class="xif-ph"><div class="xif-ph-title"></div><input class="xif-search" type="text" placeholder="Search\u2026"></div><div class="xif-opts"></div></div></div><div class="xif-footer"><span class="xif-status">No Filters Applied</span><div class="xif-actions"><button class="xif-clear">Clear All</button><button class="xif-apply">Apply</button></div></div></div>');
		$overlay.append($modal);
		$('body').append($overlay);
		render_types(); render_panel(); update_footer();

		$modal.find('.xif-search').on('input', function () { render_panel($(this).val()); });
		$modal.find('.xif-clear').on('click', function () {
			sel.programmes = []; sel.batches = [];
			render_types(); render_panel($modal.find('.xif-search').val()); update_footer();
		});
		$modal.find('.xif-apply').on('click', function () {
			S.inst_filter = { programmes: sel.programmes, batches: sel.batches };
			S.page = 1;
			var total = count_all();
			var $btn = $body.find('#pr-inst-filter-btn');
			if (total) {
				$btn.addClass('xif-btn-active').find('.xif-count').remove();
				$btn.append('<span class="xif-count" style="background:#920C24;color:#fff;border-radius:20px;font-size:10px;font-weight:700;padding:1px 6px;margin-left:4px;">' + total + '</span>');
			} else {
				$btn.removeClass('xif-btn-active').find('.xif-count').remove();
			}
			$overlay.remove();
			loadStudents();
		});
		$modal.find('.xif-close').on('click', function () { $overlay.remove(); });
		$overlay.on('click', function (e) { if ($(e.target).is($overlay)) $overlay.remove(); });
	}
};
