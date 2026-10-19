frappe.pages['term-result'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Term Result',
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
	if (!document.getElementById('tr-style')) {
		var style = document.createElement('style');
		style.id  = 'tr-style';
		style.textContent = `
		/* shared layout */
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

		/* Filter card */
		.tr-filter-card  { background:#fff; border-radius:12px; padding:14px 20px; margin-bottom:14px;
		                   box-shadow:0 1px 3px rgba(0,0,0,.06); display:flex; gap:14px;
		                   align-items:flex-end; flex-wrap:wrap; }
		.tr-fgroup       { display:flex; flex-direction:column; min-width:220px; flex:1; max-width:320px; }
		.tr-flabel       { font-size:11px; color:#94a3b8; font-weight:700; margin-bottom:5px;
		                   text-transform:uppercase; letter-spacing:.6px; }
		.tr-select       { height:36px; border:1.5px solid #e2e8f0; border-radius:8px;
		                   padding:0 12px; font-size:13px; background:#fff; color:#1e293b;
		                   outline:none; cursor:pointer; transition:border-color .2s; }
		.tr-select:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }

		/* Action bar */
		.tr-actbar       { display:flex; align-items:center; gap:8px; flex-wrap:wrap;
		                   margin-bottom:12px; }
		.tr-srch         { flex:1; min-width:200px; max-width:380px; position:relative; }
		.tr-srch input   { width:100%; height:36px; border:1.5px solid #e2e8f0; border-radius:8px;
		                   padding:0 12px 0 36px; font-size:13px; outline:none; color:#1e293b;
		                   background:#fff; transition:border-color .2s; box-sizing:border-box; }
		.tr-srch input:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }
		.tr-srch-ico     { position:absolute; left:10px; top:10px; color:#94a3b8; }
		.tr-btn          { height:36px; padding:0 14px; border-radius:7px; border:1.5px solid #e2e8f0;
		                   background:#fff; cursor:pointer; font-size:12.5px; font-weight:600;
		                   color:#475569; display:inline-flex; align-items:center; gap:5px;
		                   white-space:nowrap; transition:all .15s; }
		.tr-btn:hover    { background:#f8fafc; border-color:#cbd5e1; color:#1e293b; }
		.tr-btn.primary  { background:#920C24;
		                   border-color:transparent; color:#fff; }
		.tr-btn.primary:hover { opacity:.9; }
		.tr-btn.outline-indigo { border-color:#E8B4BE; color:#920C24; background:#FBEEF0; }
		.tr-btn.outline-indigo:hover { background:#F5D9DE; }

		/* Dropdown buttons */
		.tr-btn-dd       { position:relative; display:inline-flex; }
		.tr-btn-dd .dd-menu { display:none; position:absolute; top:calc(100% + 4px); left:0; z-index:999;
		                   background:#fff; border:1.5px solid #e2e8f0; border-radius:9px;
		                   box-shadow:0 8px 24px rgba(0,0,0,.12); min-width:160px; padding:5px; }
		.tr-btn-dd.open .dd-menu { display:block; }
		.dd-item         { padding:8px 12px; font-size:12.5px; cursor:pointer; color:#475569;
		                   border-radius:6px; font-weight:500; }
		.dd-item:hover   { background:#f1f5f9; color:#1e293b; }

		/* Summary stat cards */
		.tr-stat-cards   { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
		.tr-stat-card    { background:#fff; border-radius:12px; padding:14px 18px; flex:1;
		                   min-width:140px; box-shadow:0 1px 3px rgba(0,0,0,.06);
		                   border-top:3px solid var(--sc-color,#920C24); display:flex;
		                   align-items:center; gap:12px; }
		.tr-sc-icon      { width:38px; height:38px; border-radius:9px; flex-shrink:0;
		                   display:flex; align-items:center; justify-content:center;
		                   font-size:17px; background:var(--sc-bg,#FBEEF0); }
		.tr-sc-val       { font-size:22px; font-weight:800; color:var(--sc-color,#920C24); line-height:1.1; }
		.tr-sc-lbl       { font-size:10px; color:#94a3b8; font-weight:700; text-transform:uppercase;
		                   letter-spacing:.6px; margin-top:2px; }

		/* Stats / table header row */
		.tr-tbl-header   { display:flex; align-items:center; gap:10px; margin-bottom:10px; padding:0 2px; }
		.tr-count-lbl    { font-size:13px; font-weight:700; color:#0f172a; }
		.tr-sort-wrap    { display:flex; align-items:center; gap:6px; font-size:12px; color:#64748b;
		                   margin-left:auto; }
		.tr-sort-select  { height:28px; border:1.5px solid #e2e8f0; border-radius:6px;
		                   padding:0 8px; font-size:12px; background:#fff; color:#334155;
		                   outline:none; cursor:pointer; }

		/* Table card — allow horizontal scroll */
		.tr-table-card   { background:#fff; border-radius:12px;
		                   box-shadow:0 1px 3px rgba(0,0,0,.06);
		                   overflow:hidden; }
		.tr-table-scroll { overflow-x:auto; }
		.tr-table        { width:100%; border-collapse:collapse; font-size:13px; min-width:1100px; }
		.tr-table thead tr { background:#f8fafc; }
		.tr-table th     { padding:10px 14px; text-align:left; font-size:11px; font-weight:700;
		                   color:#475569; border-bottom:1.5px solid #e2e8f0; white-space:nowrap;
		                   text-transform:uppercase; letter-spacing:.4px; cursor:pointer;
		                   user-select:none; background:#f8fafc; position:sticky; top:0; z-index:5; }
		.tr-table th:hover { color:#920C24; background:#f1f5f9; }
		.tr-table th.center { text-align:center; }
		.tr-table th .sort-ico { font-size:10px; margin-left:3px; opacity:.4; }
		.tr-table th.sort-active { color:#920C24; }
		.tr-table th.sort-active .sort-ico { opacity:1; color:#920C24; }
		.tr-table td     { padding:0 14px; border-bottom:1.5px solid #f1f5f9; vertical-align:middle;
		                   white-space:nowrap; }
		.tr-table tbody tr { height:72px; }
		.tr-table tbody tr:hover td { background:#FDF8F9; }
		.tr-table tbody tr:last-child td { border-bottom:none; }

		/* Student cell */
		.tr-savatar      { width:40px; height:40px; border-radius:10px; flex-shrink:0;
		                   display:flex; align-items:center; justify-content:center;
		                   font-size:14px; font-weight:700; color:#fff; overflow:hidden; }
		.tr-savatar img  { width:100%; height:100%; object-fit:cover; }
		.tr-sinfo        { min-width:0; }
		.tr-sname        { font-size:13px; font-weight:700; color:#0f172a; }
		.tr-sreg         { font-size:11px; color:#920C24; font-weight:600; margin-top:2px;
		                   background:#FBEEF0; border-radius:4px; padding:1px 6px;
		                   display:inline-block; }
		.tr-semail       { font-size:11px; color:#94a3b8; font-weight:400; margin-top:3px; }

		/* GPA / percentage values */
		.tr-val-pill     { display:inline-flex; align-items:center; gap:5px; }
		.tr-val-num      { font-size:13px; font-weight:700; color:#0f172a; }
		.tr-val-ng       { font-size:12.5px; color:#920C24; font-weight:600; }
		.tr-val-na       { font-size:12.5px; color:#cbd5e1; font-weight:500; }

		/* View link */
		.tr-view-link    { font-size:12px; font-weight:700; color:#920C24; cursor:pointer;
		                   border-bottom:1px dashed #E8B4BE; text-decoration:none; }
		.tr-view-link:hover { color:#6E091B; }

		/* Badge */
		.tr-badge        { font-size:10px; font-weight:700; padding:2px 8px; border-radius:20px; }
		.tr-badge.active   { background:#d1fae5; color:#065f46; }
		.tr-badge.inactive { background:#F5D9DE; color:#6E091B; }

		/* Pagination */
		.tr-pag-bar      { display:flex; align-items:center; justify-content:space-between;
		                   padding:12px 16px; border-top:1.5px solid #f1f5f9; }
		.tr-pag-info     { font-size:12.5px; color:#64748b; }
		.tr-pag-btns     { display:flex; gap:4px; }
		.tr-pag-btn      { width:30px; height:30px; border:1.5px solid #e2e8f0; border-radius:7px;
		                   background:#fff; cursor:pointer; font-size:14px; display:inline-flex;
		                   align-items:center; justify-content:center; color:#64748b;
		                   transition:all .15s; }
		.tr-pag-btn:hover:not(:disabled) { background:#FBEEF0; border-color:#E8B4BE; color:#920C24; }
		.tr-pag-btn:disabled { opacity:.35; cursor:default; }

		/* Empty state */
		.tr-empty        { padding:80px 20px; display:flex; flex-direction:column;
		                   align-items:center; justify-content:center; text-align:center; }
		.tr-empty-icon   { width:56px; height:56px; border-radius:14px; background:#f1f5f9;
		                   display:flex; align-items:center; justify-content:center; margin-bottom:14px; }
		.tr-empty-txt    { font-size:14px; font-weight:700; color:#94a3b8; }
		.tr-empty-sub    { font-size:12px; color:#cbd5e1; margin-top:4px; }

		/* Loading */
		.tr-loading      { padding:60px; text-align:center; color:#94a3b8; font-size:13px; }

		/* Avatar colours */
		.av-0{background:#920C24;}
		.av-1{background:#920C24;}
		.av-2{background:#920C24;}
		.av-3{background:#920C24;}
		.av-4{background:#920C24;}
		.av-5{background:#920C24;}
		.av-6{background:#920C24;}
		.av-7{background:#920C24;}

		/* Courses dialog */
		.tr-dlg-profile  { display:flex; align-items:center; gap:14px; padding:14px 18px;
		                   background:#f8fafc; border-radius:10px; margin-bottom:16px; }
		.tr-dlg-avatar   { width:56px; height:56px; border-radius:12px; flex-shrink:0;
		                   object-fit:cover; border:2px solid #e2e8f0; background:#e2e8f0; }
		.tr-dlg-sname    { font-size:15px; font-weight:800; color:#920C24; }
		.tr-dlg-sreg     { font-size:12px; color:#64748b; font-weight:600; margin-top:1px; }
		.tr-dlg-semail   { font-size:12px; color:#94a3b8; margin-top:1px; }
		.tr-dlg-sprog    { font-size:12px; color:#475569; font-weight:500; margin-top:1px; }
		.tr-dlg-section  { font-size:13px; font-weight:800; color:#0f172a; margin:14px 0 8px; }
		.tr-dlg-section .tr-dlg-cnt { color:#920C24; margin-left:4px; }
		.tr-dlg-section .tr-dlg-cnt.regular { color:#920C24; }
		.tr-cdlg-table   { width:100%; border-collapse:collapse; font-size:12.5px; }
		.tr-cdlg-table th { background:#f8fafc; padding:8px 10px; text-align:center; font-size:10.5px;
		                    font-weight:700; color:#475569; border-bottom:1.5px solid #e2e8f0;
		                    white-space:nowrap; text-transform:uppercase; letter-spacing:.3px; }
		.tr-cdlg-table th.left { text-align:left; }
		.tr-cdlg-table td { padding:10px 10px; border-bottom:1.5px solid #f1f5f9;
		                    vertical-align:middle; color:#334155; text-align:center; }
		.tr-cdlg-table td.left { text-align:left; }
		.tr-cdlg-table tbody tr:last-child td { border-bottom:none; }
		.tr-cdlg-table tbody tr:hover td { background:#FDF8F9; }
		.tr-cdlg-cname   { font-size:13px; font-weight:700; color:#0f172a; }
		.tr-cdlg-code    { font-size:11px; color:#64748b; margin-top:1px; }
		.tr-cdlg-backlog { font-size:10px; font-weight:700; color:#920C24; background:#FBEEF0;
		                   border:1px solid #E8B4BE; border-radius:4px; padding:1px 6px;
		                   display:inline-block; margin-top:3px; }
		.tr-cdlg-result  { line-height:1.5; }
		.tr-cdlg-grade-pill { font-size:12px; font-weight:800; }
		.tr-cdlg-grade-pill.fail  { color:#920C24; }
		.tr-cdlg-grade-pill.pass  { color:#059669; }
		.tr-cdlg-marks   { font-size:11px; color:#64748b; }
		.tr-cdlg-dash    { color:#cbd5e1; font-size:13px; font-weight:600; }

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
		.xif-close   { width:30px; height:30px; border-radius:8px; border:none;
		               background:#f1f5f9; cursor:pointer; display:flex;
		               align-items:center; justify-content:center; color:#64748b;
		               font-size:16px; transition:all .15s; }
		.xif-close:hover { background:#F5D9DE; color:#920C24; }
		.xif-body    { display:flex; flex:1; overflow:hidden; }
		.xif-types   { width:190px; flex-shrink:0; border-right:1.5px solid #f1f5f9;
		               padding:8px; background:#FDF8F9; }
		.xif-type    { padding:10px 14px; border-radius:8px; font-size:13px; font-weight:600;
		               color:#475569; cursor:pointer; margin-bottom:2px;
		               transition:all .15s; display:flex; align-items:center; gap:8px; }
		.xif-type:hover { background:#f1f5f9; color:#1e293b; }
		.xif-type.active { background:#FBEEF0; color:#920C24; }
		.xif-type-badge { min-width:18px; height:18px; border-radius:20px;
		                  background:#920C24; color:#fff; font-size:10px; font-weight:700;
		                  display:inline-flex; align-items:center; justify-content:center;
		                  padding:0 5px; margin-left:auto; }
		.xif-panel   { flex:1; display:flex; flex-direction:column; overflow:hidden; }
		.xif-ph      { padding:14px 16px 8px; border-bottom:1.5px solid #f1f5f9; }
		.xif-ph-title{ font-size:13px; font-weight:700; color:#1e293b; margin-bottom:8px; }
		.xif-search  { width:100%; height:32px; border:1.5px solid #e2e8f0; border-radius:8px;
		               padding:0 10px 0 30px; font-size:12.5px; outline:none; color:#1e293b;
		               background:#f8fafc url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2.5'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cline x1='21' y1='21' x2='16.65' y2='16.65'/%3E%3C/svg%3E") no-repeat 9px center;
		               box-sizing:border-box; transition:border-color .2s; }
		.xif-search:focus { border-color:#920C24; background-color:#fff; }
		.xif-opts    { flex:1; overflow-y:auto; padding:8px; }
		.xif-opt     { display:flex; align-items:center; gap:10px; padding:9px 12px;
		               border-radius:8px; cursor:pointer; font-size:13px; font-weight:500;
		               color:#334155; transition:background .12s; }
		.xif-opt:hover { background:#f8fafc; }
		.xif-opt.checked { background:#FBEEF0; color:#6E091B; }
		.xif-opt input[type="checkbox"] { width:15px; height:15px; accent-color:#920C24;
		                                  cursor:pointer; flex-shrink:0; }
		.xif-empty-opts { padding:32px; text-align:center; color:#cbd5e1; font-size:13px; }
		.xif-footer  { display:flex; align-items:center; justify-content:space-between;
		               padding:12px 16px; border-top:1.5px solid #f1f5f9; background:#FDF8F9; }
		.xif-status  { font-size:12.5px; color:#64748b; font-weight:500; }
		.xif-status strong { color:#920C24; }
		.xif-actions { display:flex; gap:8px; }
		.xif-clear   { padding:0 14px; height:32px; border-radius:7px;
		               border:1.5px solid #e2e8f0; background:#fff; color:#64748b;
		               font-size:12.5px; font-weight:600; cursor:pointer; transition:all .15s; }
		.xif-clear:hover { border-color:#920C24; color:#920C24; background:#FBEEF0; }
		.xif-apply   { padding:0 18px; height:32px; border-radius:7px; border:none;
		               background:#920C24; color:#fff;
		               font-size:12.5px; font-weight:700; cursor:pointer; transition:opacity .15s; }
		.xif-apply:hover { opacity:.88; }
		.xif-btn-active { background:linear-gradient(135deg,#FBEEF0,#F5D9DE) !important;
		                  border-color:#E8B4BE !important; color:#6E091B !important; }
		`;
		document.head.appendChild(style);
	}

	// ── State ─────────────────────────────────────────────────────────────────
	var S = {
		exam_plan:    null,
		students:     [],
		total:        0,
		page:         1,
		page_length:  20,
		search:       '',
		sort_by:      'registration_id',
		sort_order:   'asc',
		loading:      false,
		search_timer: null,
		inst_filter:  { programmes: [], batches: [] },
		inst_options: null,
		select_all_matching: false,
		excluded_students:   {},
	};

	// ── Render shell ──────────────────────────────────────────────────────────
	var $body = $(page.main);
	$body.html(`
		<div class="er2-wrap" style="padding:20px 24px;">

			<!-- Page header -->
			<div class="er2-page-header">
				<div class="er2-page-icon" style="background:#920C24;">
					<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2">
						<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
						<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
					</svg>
				</div>
				<div>
					<div class="er2-page-title">Term Results</div>
					<div class="er2-page-sub">Consolidated term-wise academic results, SGPA/CGPA and semester performance</div>
				</div>
			</div>

			<!-- Page navigation -->
			<div class="er2-page-nav">
				<button class="er2-pnav-btn" onclick="frappe.set_route('examination-result')">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
					Course Results
				</button>
				<button class="er2-pnav-btn active">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
					Term Results
				</button>
				<button class="er2-pnav-btn" onclick="frappe.set_route('publish-result')">
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

			<!-- Filter card: Exam Plan only -->
			<div class="tr-filter-card">
				<div class="tr-fgroup">
					<span class="tr-flabel">
						<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/></svg>
						Exam Plan
					</span>
					<select class="tr-select" id="tr-exam-plan">
						<option value="">Choose Exam Plan</option>
					</select>
				</div>
			</div>

			<!-- Content area -->
			<div id="tr-content" style="display:none;">

				<!-- Action bar -->
				<div class="tr-actbar">
					<div class="tr-srch">
						<svg class="tr-srch-ico" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
						<input id="tr-search" type="text" placeholder="Search by student name or id">
					</div>
					<div style="margin-left:auto;display:flex;gap:8px;align-items:center;">
						<button class="tr-btn" id="tr-inst-filter-btn">
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
							Institutional Filter
						</button>

						<div class="tr-btn-dd" id="tr-generate-dd">
							<button class="tr-btn outline-indigo" id="tr-generate-btn">
								<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
								Generate
								<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"/></svg>
							</button>
							<div class="dd-menu">
								<div class="dd-item" id="tr-gen-term-gpa">Term GPA</div>
								<div class="dd-item" id="tr-gen-cum-gpa">Cumulative GPA</div>
								<div class="dd-item" id="tr-gen-term-pct">Term Percentage</div>
								<div class="dd-item" id="tr-gen-cum-pct">Cumulative Percentage</div>

							</div>
						</div>

						</div>
					</div>
				</div>

				<!-- Summary stat cards -->
				<div class="tr-stat-cards" id="tr-stat-cards" style="display:none;"></div>

				<!-- Table header row -->
				<div class="tr-tbl-header">
					<span id="tr-count-lbl" class="tr-count-lbl">Students (0)</span>
					<span class="tr-sort-wrap">
						Sort by:
						<select class="tr-sort-select" id="tr-sort-by">
							<option value="registration_id">Registration Id</option>
							<option value="name">Name</option>
							<option value="programme">Programme</option>
						</select>
						<button id="tr-sort-dir" title="Toggle sort direction"
						  style="border:1.5px solid #e2e8f0;border-radius:6px;background:#fff;
						         padding:4px 8px;cursor:pointer;font-size:13px;color:#64748b;
						         display:inline-flex;align-items:center;gap:3px;">
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>
						</button>
					</span>
				</div>

				<!-- Table (horizontally scrollable) -->
				<div class="tr-table-card">
					<div class="tr-select-banner" id="tr-select-banner" style="display:none;padding:8px 16px;background:#FBEEF0;border-bottom:1px solid #F5D9DE;font-size:12.5px;color:#6E091B;align-items:center;gap:6px;">
						<span id="tr-select-banner-text"></span>
						<a href="javascript:void(0)" id="tr-select-all-link" style="font-weight:700;text-decoration:underline;"></a>
						<a href="javascript:void(0)" id="tr-select-clear-link" style="margin-left:auto;font-weight:700;text-decoration:underline;">Clear selection</a>
					</div>
					<div class="tr-table-scroll">
						<div id="tr-table-body"></div>
					</div>
					<div class="tr-pag-bar" id="tr-pag-bar" style="display:none;">
						<span id="tr-pag-info" class="tr-pag-info"></span>
						<div class="tr-pag-btns">
							<button class="tr-pag-btn" id="tr-prev" disabled>&#8592;</button>
							<button class="tr-pag-btn" id="tr-next" disabled>&#8594;</button>
						</div>
					</div>
				</div>

			</div><!-- /tr-content -->

		</div>
	`);

	// ── DOM refs ──────────────────────────────────────────────────────────────
	var $examPlan   = $body.find('#tr-exam-plan');
	var $content    = $body.find('#tr-content');
	var $search     = $body.find('#tr-search');
	var $tableBody  = $body.find('#tr-table-body');
	var $countLbl   = $body.find('#tr-count-lbl');
	var $pagBar     = $body.find('#tr-pag-bar');
	var $pagInfo    = $body.find('#tr-pag-info');
	var $prev       = $body.find('#tr-prev');
	var $next       = $body.find('#tr-next');
	var $sortBy     = $body.find('#tr-sort-by');
	var $sortDir    = $body.find('#tr-sort-dir');
	var $statCards  = $body.find('#tr-stat-cards');
	var $selBanner     = $body.find('#tr-select-banner');
	var $selBannerText = $body.find('#tr-select-banner-text');
	var $selAllLink    = $body.find('#tr-select-all-link');
	var $selClearLink  = $body.find('#tr-select-clear-link');

	// ── Load Exam Plans ───────────────────────────────────────────────────────
	frappe.call({
		method: 'slcm.slcm.page.term_result.term_result.get_exam_plans',
		callback: function (r) {
			if (!r.message) return;
			r.message.forEach(function (ep) {
				$examPlan.append(
					'<option value="' + ep.name + '">' +
					frappe.utils.escape_html(ep.exam_name || ep.name) +
					(ep.status === 'Active' ? ' [Active]' : '') + '</option>'
				);
			});
		},
	});

	// ── Exam Plan change ──────────────────────────────────────────────────────
	$examPlan.on('change', function () {
		S.exam_plan   = $(this).val();
		S.page        = 1;
		S.search      = '';
		S.inst_filter = { programmes: [], batches: [] };
		S.inst_options = null;
		resetSelection();
		$search.val('');
		$body.find('#tr-inst-filter-btn').removeClass('xif-btn-active').find('.xif-count').remove();
		if (S.exam_plan) {
			$content.show();
			loadStats();
			loadStudents();
		} else {
			$content.hide();
			$statCards.hide();
		}
	});

	// ── Search ────────────────────────────────────────────────────────────────
	$search.on('input', function () {
		clearTimeout(S.search_timer);
		S.search_timer = setTimeout(function () {
			S.search = $search.val().trim();
			S.page = 1;
			resetSelection();
			loadStudents();
		}, 350);
	});

	// ── Sort ──────────────────────────────────────────────────────────────────
	$sortBy.on('change', function () {
		S.sort_by = $(this).val();
		S.page = 1;
		if (S.exam_plan) loadStudents();
	});
	$sortDir.on('click', function () {
		S.sort_order = S.sort_order === 'asc' ? 'desc' : 'asc';
		var isAsc = S.sort_order === 'asc';
		$sortDir.html(isAsc
			? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>'
			: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>');
		if (S.exam_plan) loadStudents();
	});

	// ── Dropdown toggles ──────────────────────────────────────────────────────
	['tr-generate-dd', 'tr-actions-dd', 'tr-download-dd'].forEach(function (id) {
		$body.find('#' + id + ' button').first().on('click', function (e) {
			e.stopPropagation();
			var $dd = $(this).closest('.tr-btn-dd');
			var wasOpen = $dd.hasClass('open');
			$body.find('.tr-btn-dd').removeClass('open');
			if (!wasOpen) $dd.addClass('open');
		});
	});
	$(document).on('click.tr_dd', function () {
		$body.find('.tr-btn-dd').removeClass('open');
	});

	// ── Generate actions ─────────────────────────────────
	function generateResults(action, actionName) {
		if (!S.exam_plan) {
			frappe.show_alert({message:'Please select an Exam Plan first.', indicator:'orange'});
			return;
		}

		if (S.select_all_matching) {
			var matchCount = Math.max(0, S.total - Object.keys(S.excluded_students).length);
			frappe.confirm('Are you sure you want to generate ' + actionName + ' for ' + matchCount + ' student(s) matching the current filters?', function() {
				frappe.call({
					method: 'slcm.slcm.page.term_result.term_result.generate_term_results',
					args: {
						exam_plan:        S.exam_plan,
						student_names:    '[]',
						action:           action,
						select_all:       1,
						exclude_students: JSON.stringify(Object.keys(S.excluded_students)),
						search:           S.search,
						inst_programmes:  JSON.stringify(S.inst_filter.programmes),
						inst_batches:     JSON.stringify(S.inst_filter.batches),
					},
					freeze: true,
					freeze_message: 'Generating ' + actionName + '...',
					callback: function(r) {
						frappe.show_alert({message: actionName + ' generated successfully!', indicator:'green'});
						loadStudents();
					}
				});
			});
			return;
		}

		var selected = [];
		$tableBody.find('.tr-row-chk:checked').each(function() {
			selected.push($(this).data('student'));
		});
		if (!selected.length) {
			frappe.confirm('No students selected. Do you want to generate ' + actionName + ' for ALL students in this exam plan?', function() {
				frappe.call({
					method: 'slcm.slcm.page.term_result.term_result.generate_term_results',
					args: {
						exam_plan: S.exam_plan,
						student_names: '[]',
						action: action
					},
					freeze: true,
					freeze_message: 'Generating ' + actionName + '...',
					callback: function(r) {
						frappe.show_alert({message: actionName + ' generated successfully for all students!', indicator:'green'});
						loadStudents();
					}
				});
			});
			return;
		}

		frappe.confirm('Are you sure you want to generate ' + actionName + ' for ' + selected.length + ' student(s)?', function() {
			frappe.call({
				method: 'slcm.slcm.page.term_result.term_result.generate_term_results',
				args: {
					exam_plan: S.exam_plan,
					student_names: JSON.stringify(selected),
					action: action
				},
				freeze: true,
				freeze_message: 'Generating ' + actionName + '...',
				callback: function(r) {
					frappe.show_alert({message: actionName + ' generated successfully!', indicator:'green'});
					loadStudents();
				}
			});
		});
	}

	$body.find('#tr-gen-term-gpa').on('click',  function () { generateResults('term_gpa', 'Term GPA'); });
	$body.find('#tr-gen-cum-gpa').on('click',   function () { generateResults('cumulative_gpa', 'Cumulative GPA'); });
	$body.find('#tr-gen-term-pct').on('click',  function () { generateResults('term_percentage', 'Term Percentage'); });
	$body.find('#tr-gen-cum-pct').on('click',   function () { generateResults('cumulative_percentage', 'Cumulative Percentage'); });


	// Insert CGPA Scale button into UI
	$body.find('#tr-inst-filter-btn').before(
		'<button class="tr-btn outline-indigo" id="tr-cgpa-scale-btn" style="margin-right: 8px;">' +
		'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">' +
		'<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>' +
		'<line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>' +
		'<line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>' +
		'</svg> CGPA % Scale</button>'
	);
	$body.find('#tr-cgpa-scale-btn').on('click', function () {
		frappe.set_route('cgpa-scale-page');
	});

	// Insert Notes button into UI
	$body.find('#tr-inst-filter-btn').before('<button class="tr-btn outline-indigo" id="tr-note-btn" style="margin-right: 8px;"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>Notes / Formulas</button>');
	$body.find('#tr-note-btn').on('click', function() {
		var d = new frappe.ui.Dialog({
			title: 'Calculation Formulas',
			fields: [
				{
					fieldname: 'help_html',
					fieldtype: 'HTML',
					options: `
					<div style="padding: 10px; font-size: 13px; line-height: 1.6; color: #334155;">
						<b>Term GPA Calculation</b><br>
						<span>Formula: &Sigma; (Course Grade Point &times; Course Credit) / &Sigma; (Course Credits)</span>
						<p style="margin-top:4px; font-size: 12px; color: #64748b;">Calculated only for courses considered for SGPA in the selected term.</p>
						<hr style="border:0; border-top:1px solid #e2e8f0; margin:12px 0;">
						
						<b>Term Percentage Calculation</b><br>
						<span>Formula: (Total Marks Obtained / Maximum Marks) &times; 100</span>
						<p style="margin-top:4px; font-size: 12px; color: #64748b;">Calculated across all graded courses in the selected term.</p>
						<hr style="border:0; border-top:1px solid #e2e8f0; margin:12px 0;">
						
						<b>Cumulative GPA Calculation</b><br>
						<span>Formula: &Sigma; (All Course Grade Points &times; Credits) / &Sigma; (All Course Credits)</span>
						<p style="margin-top:4px; font-size: 12px; color: #64748b;">Calculated across all terms up to the present.</p>
						<hr style="border:0; border-top:1px solid #e2e8f0; margin:12px 0;">
						
						<b>Cumulative Percentage Calculation</b><br>
						<span>Formula: (Total Marks Obtained across all terms / Maximum Marks across all terms) &times; 100</span>
					</div>
					`
				}
			],
			primary_action_label: 'Close',
			primary_action: function() { d.hide(); }
		});
		d.show();
	});

	// ── Download actions ──────────────────────────────────────────────────────
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
				if (v.report_type === 'Course Based' && v.course) {
					args.course_offering = v.course;
				}
				if (!Object.keys(args).length) {
					frappe.msgprint({ message: __('Please select at least one filter.'), indicator: 'orange' });
					return;
				}
				var url = '/api/method/slcm.slcm.page.term_result.term_result.download_consolidated_report?' + $.param(args);
				frappe.show_alert({ message: __('Preparing report…'), indicator: 'blue' });
				d.hide();

				fetch(url, {
					credentials: 'same-origin',
					headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token || '' }
				})
				.then(function(res) {
					if (!res.ok) {
						return res.json().catch(function () { return {}; }).then(function (errBody) {
							var msg = 'Server error: ' + res.status;
							try {
								if (errBody && errBody._server_messages) {
									var arr = JSON.parse(errBody._server_messages);
									if (arr && arr.length) {
										var first = JSON.parse(arr[0]);
										msg = first.message || msg;
									}
								} else if (errBody && errBody.exception) {
									msg = errBody.exception.split(': ').pop();
								}
							} catch (e) { /* fall back to generic message */ }
							throw new Error(msg);
						});
					}
					return res.blob();
				})
				.then(function(blob) {
					var a = document.createElement('a');
					a.href = URL.createObjectURL(blob);
					a.download = 'Consolidated_Report.xlsx';
					document.body.appendChild(a);
					a.click();
					a.remove();
					URL.revokeObjectURL(a.href);
					frappe.show_alert({ message: __('Report downloaded successfully.'), indicator: 'green' });
				})
				.catch(function(err) {
					frappe.msgprint({ title: __('Download Failed'), message: err.message || __('Could not download the report. Please try again.'), indicator: 'red' });
				});
			}
		});
		d.show();
	});

	// ── Institutional Filter ──────────────────────────────────────────────────
	$body.find('#tr-inst-filter-btn').on('click', function () {
		if (!S.exam_plan) { frappe.show_alert({message:'Select an Exam Plan first.', indicator:'orange'}); return; }
		if (S.inst_options) {
			show_inst_filter_dialog(S.inst_options);
		} else {
			frappe.call({
				method: 'slcm.slcm.page.term_result.term_result.get_term_inst_filter_options',
				args:   { exam_plan: S.exam_plan },
				callback: function (r) {
					S.inst_options = r.message || { programmes: [], batches: [] };
					show_inst_filter_dialog(S.inst_options);
				},
			});
		}
	});



	// ── Select All ───────────────────────────────────────────────────────────
	$body.on('click', '#tr-act-select-all', function () {
		$tableBody.find('.tr-row-chk').prop('checked', true);
	});
	$body.on('click', '#tr-act-clear', function () {
		$tableBody.find('.tr-row-chk').prop('checked', false);
	});

	// ── Pagination ────────────────────────────────────────────────────────────
	$prev.on('click', function () {
		if (S.page > 1) { S.page--; loadStudents(); }
	});
	$next.on('click', function () {
		var totalPages = Math.ceil(S.total / S.page_length);
		if (S.page < totalPages) { S.page++; loadStudents(); }
	});

	// ── Load & render stat cards ──────────────────────────────────────────────
	function loadStats() {
		if (!S.exam_plan) return;
		$statCards.html(
			'<div class="tr-stat-card" style="--sc-color:#920C24;--sc-bg:#FBEEF0;">' +
			'<div class="tr-sc-icon">👥</div>' +
			'<div><div class="tr-sc-val">…</div><div class="tr-sc-lbl">Total Students</div></div></div>'
		).show();

		frappe.call({
			method: 'slcm.slcm.page.term_result.term_result.get_term_stats',
			args: { exam_plan: S.exam_plan },
			callback: function (r) {
				if (!r.message) return;
				renderStats(r.message);
			},
		});
	}

	function renderStats(stats) {
		var cards = [
			{
				label: 'Total Students',
				value: stats.total_students || 0,
				icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
				color: '#920C24', bg: '#FBEEF0',
			},
			{
				label: 'Total Courses',
				value: stats.total_courses || 0,
				icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
				color: '#920C24', bg: '#F5D9DE',
			},
			{
				label: 'Graded',
				value: stats.graded || 0,
				icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
				color: '#920C24', bg: '#F5D9DE',
			},
			{
				label: 'Not Graded',
				value: stats.not_graded || 0,
				icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
				color: '#920C24', bg: '#F5D9DE',
			},
			{
				label: 'Avg CGPA',
				value: stats.avg_cgpa != null ? stats.avg_cgpa : '—',
				icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
				color: '#920C24', bg: '#F5D9DE',
			},
		];

		var html = cards.map(function (c) {
			return '<div class="tr-stat-card" style="--sc-color:' + c.color + ';--sc-bg:' + c.bg + ';">' +
				'<div class="tr-sc-icon" style="color:' + c.color + ';">' + c.icon + '</div>' +
				'<div>' +
					'<div class="tr-sc-val">' + c.value + '</div>' +
					'<div class="tr-sc-lbl">' + c.label + '</div>' +
				'</div>' +
			'</div>';
		}).join('');

		$statCards.html(html).show();
	}

	// ── Load students ─────────────────────────────────────────────────────────
	function loadStudents() {
		if (!S.exam_plan || S.loading) return;
		S.loading = true;
		$tableBody.html('<div class="tr-loading"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" style="animation:spin 1s linear infinite;vertical-align:-6px;margin-right:6px;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>Loading students…</div>');

		frappe.call({
			method: 'slcm.slcm.page.term_result.term_result.get_term_students',
			args: {
				exam_plan:        S.exam_plan,
				search:           S.search,
				page:             S.page,
				page_length:      S.page_length,
				sort_by:          S.sort_by,
				sort_order:       S.sort_order,
				inst_programmes:  JSON.stringify(S.inst_filter.programmes),
				inst_batches:     JSON.stringify(S.inst_filter.batches),
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
				$tableBody.html('<div class="tr-empty"><div class="tr-empty-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div><div class="tr-empty-txt">Failed to load students</div></div>');
			},
		});
	}

	// ── Render table ──────────────────────────────────────────────────────────
	function renderTable() {
		$countLbl.text('Students (' + S.total + ')');

		if (!S.students.length) {
			$tableBody.html('<div class="tr-empty"><div class="tr-empty-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg></div><div class="tr-empty-txt">No students found</div><div class="tr-empty-sub">Try a different exam plan or search term</div></div>');
			$pagBar.hide();
			return;
		}

		var rows = S.students.map(function (s, idx) {
			var initials = (s.student_name || 'S').split(' ').map(function (w) { return w[0]; }).join('').substring(0, 2).toUpperCase();
			var avClass  = 'av-' + (idx % 8);
			var avatar   = s.image
				? '<img src="' + frappe.utils.escape_html(s.image) + '" alt="">'
				: initials;

			var badge = s.student_status === 'Active'
				? '<span class="tr-badge active">Active</span>'
				: '<span class="tr-badge inactive">' + frappe.utils.escape_html(s.student_status || 'Unknown') + '</span>';

			var tgpa = s.term_gpa != null
				? '<span class="tr-val-num">' + parseFloat(s.term_gpa).toFixed(2) + '</span>'
				: '<span class="tr-val-ng">Not Generated</span>';

			var cgpa = s.cumulative_gpa != null
				? '<span class="tr-val-num">' + parseFloat(s.cumulative_gpa).toFixed(2) + '</span>'
				: '<span class="tr-val-ng">Not Generated</span>';

			var tpct = s.term_percentage != null
				? '<span class="tr-val-num">' + parseFloat(s.term_percentage).toFixed(2) + '%</span>'
				: '<span class="tr-val-ng">Not Generated</span>';

			var cpct = s.cumulative_percentage != null
				? '<span class="tr-val-num">' + parseFloat(s.cumulative_percentage).toFixed(2) + '%</span>'
				: '<span class="tr-val-ng">Not Generated</span>';

			var prog = frappe.utils.escape_html(s.programme || '—');
			var courses = s.course_count
				? s.course_count + ' &nbsp;<a class="tr-view-link tr-view-courses" data-student="' + frappe.utils.escape_html(s.student) + '" data-name="' + frappe.utils.escape_html(s.student_name) + '">View</a>'
				: '—';

			var rowChecked = S.select_all_matching && !S.excluded_students[s.student];

			return '<tr>' +
				'<td style="width:40px;"><input type="checkbox" class="tr-row-chk" data-student="' + frappe.utils.escape_html(s.student) + '"' + (rowChecked ? ' checked' : '') + ' style="accent-color:#920C24;cursor:pointer;"></td>' +
				'<td style="min-width:200px;">' +
					'<div style="display:flex;align-items:center;gap:10px;">' +
					'<div class="tr-savatar ' + avClass + '">' + avatar + '</div>' +
					'<div class="tr-sinfo">' +
						'<div class="tr-sname">' + frappe.utils.escape_html(s.student_name || s.student) + '</div>' +
						'<div class="tr-sreg">' + frappe.utils.escape_html(s.registration_id || s.student) + '</div>' +
						(s.email ? '<div class="tr-semail">' + frappe.utils.escape_html(s.email) + '</div>' : '') +
					'</div>' +
					'</div>' +
				'</td>' +
				'<td style="min-width:180px;">' + prog + '</td>' +
				'<td style="min-width:100px;text-align:center;">' + courses + '</td>' +
				'<td style="min-width:130px;text-align:center;">' + tgpa + '</td>' +
				'<td style="min-width:130px;text-align:center;">' + cgpa + '</td>' +
				'<td style="min-width:150px;text-align:center;">' + tpct + '</td>' +
				'<td style="min-width:160px;text-align:center;">' + cpct + '</td>' +
			'</tr>';
		});

		var allOnPageChecked = S.students.length > 0 && S.students.every(function (s) {
			return S.select_all_matching && !S.excluded_students[s.student];
		});

		var thead = '<table class="tr-table">' +
			'<thead><tr>' +
			'<th style="width:40px;"><input type="checkbox" id="tr-chk-all"' + (allOnPageChecked ? ' checked' : '') + ' style="accent-color:#920C24;cursor:pointer;"></th>' +
			'<th>Student</th>' +
			'<th>Programme</th>' +
			'<th class="center">Courses</th>' +
			'<th class="center">Term GPA</th>' +
			'<th class="center">Cumulative GPA</th>' +
			'<th class="center">Term Percentage</th>' +
			'<th class="center">Cumulative %</th>' +
			'</tr></thead>' +
			'<tbody>' + rows.join('') + '</tbody>' +
			'</table>';

		$tableBody.html(thead);
		$pagBar.show();

		if (S.select_all_matching) {
			showMatchingBanner();
		} else {
			hideSelectBanner();
		}

		// Select all checkbox (current page)
		$tableBody.find('#tr-chk-all').on('change', function () {
			var checked = $(this).is(':checked');
			$tableBody.find('.tr-row-chk').prop('checked', checked);
			if (checked) {
				S.excluded_students = {};
				if (S.select_all_matching || S.total <= S.students.length) {
					S.select_all_matching = true;
					showMatchingBanner();
				} else {
					showPageSelectedBanner();
				}
			} else {
				resetSelection();
			}
		});

		// Add spin keyframe if not present
		if (!document.getElementById('tr-spin-style')) {
			var ss = document.createElement('style');
			ss.id = 'tr-spin-style';
			ss.textContent = '@keyframes spin{to{transform:rotate(360deg)}}';
			document.head.appendChild(ss);
		}
	}

	// ── Multi-page selection ("select all matching") ────────────────────────
	function resetSelection() {
		S.select_all_matching = false;
		S.excluded_students   = {};
		hideSelectBanner();
	}

	function hideSelectBanner() {
		$selBanner.hide();
	}

	function showPageSelectedBanner() {
		$selBannerText.text('All ' + S.students.length + ' students on this page are selected.');
		$selAllLink.text('Select all ' + S.total + ' students that match this search').show();
		$selBanner.css('display', 'flex');
	}

	function showMatchingBanner() {
		var count = Math.max(0, S.total - Object.keys(S.excluded_students).length);
		$selBannerText.text('All ' + count + ' students that match this search are selected.');
		$selAllLink.hide();
		$selBanner.css('display', 'flex');
	}

	// Row checkbox toggled — delegated so it keeps working across re-renders
	$tableBody.on('change', '.tr-row-chk', function () {
		var student = $(this).data('student');
		var checked = $(this).is(':checked');
		if (S.select_all_matching) {
			if (checked) {
				delete S.excluded_students[student];
			} else {
				S.excluded_students[student] = true;
			}
			showMatchingBanner();
		}
		var $rows = $tableBody.find('.tr-row-chk');
		$tableBody.find('#tr-chk-all').prop('checked', $rows.length > 0 && $rows.length === $rows.filter(':checked').length);
	});

	$selAllLink.on('click', function () {
		S.select_all_matching = true;
		S.excluded_students   = {};
		$tableBody.find('.tr-row-chk').prop('checked', true);
		$tableBody.find('#tr-chk-all').prop('checked', true);
		showMatchingBanner();
	});

	$selClearLink.on('click', function () {
		resetSelection();
		$tableBody.find('.tr-row-chk').prop('checked', false);
		$tableBody.find('#tr-chk-all').prop('checked', false);
	});

	// ── Render pagination ────────────────────────────────────────────────────
	function renderPagination() {
		var totalPages = Math.ceil(S.total / S.page_length);
		var from = Math.min((S.page - 1) * S.page_length + 1, S.total);
		var to   = Math.min(S.page * S.page_length, S.total);
		$pagInfo.text(from + '–' + to + ' of ' + S.total);
		$prev.prop('disabled', S.page <= 1);
		$next.prop('disabled', S.page >= totalPages);
	}

	// ── View courses popup ────────────────────────────────────────────────────
	$body.on('click', '.tr-view-courses', function (e) {
		e.preventDefault();
		var student = $(this).data('student');
		if (!S.exam_plan || !student) return;

		frappe.call({
			method: 'slcm.slcm.page.term_result.term_result.get_student_courses',
			args: { exam_plan: S.exam_plan, student: student },
			callback: function (r) {
				var data    = r.message || {};
				var courses = data.courses || [];
				var sm      = data.student || {};

				if (!courses.length) {
					frappe.show_alert({ message: 'No courses found for this student', indicator: 'orange' });
					return;
				}

				// ── Student profile card ────────────────────────────────────
				var initials = ((sm.first_name || 'S')[0] + (sm.last_name || '')[0]).toUpperCase();
				var avatarHtml = sm.passport_size_photo
					? '<img class="tr-dlg-avatar" src="' + frappe.utils.escape_html(sm.passport_size_photo) + '">'
					: '<div class="tr-dlg-avatar" style="display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:800;color:#fff;background:#920C24;">' + initials + '</div>';

				var fullName = [sm.first_name, sm.middle_name, sm.last_name].filter(Boolean).join(' ');
				var prog     = sm.programme ? frappe.utils.escape_html(sm.programme) : '';
				var batch    = sm.batch_year ? frappe.utils.escape_html(sm.batch_year) : '';

				var profileHtml = '<div class="tr-dlg-profile">' +
					avatarHtml +
					'<div>' +
						'<div class="tr-dlg-sname">' + frappe.utils.escape_html(fullName) + '</div>' +
						'<div class="tr-dlg-sreg">' + frappe.utils.escape_html(sm.registration_id || student) + '</div>' +
						(sm.email ? '<div class="tr-dlg-semail">' + frappe.utils.escape_html(sm.email) + '</div>' : '') +
						(prog ? '<div class="tr-dlg-sprog">' + prog + (batch ? ' &nbsp;·&nbsp; ' + batch : '') + '</div>' : '') +
					'</div>' +
				'</div>';

				// ── Moderation Logs button ─────────────────────────────────
				var modBtn = '<div style="display:flex;justify-content:flex-end;margin-bottom:10px;">' +
					'<button onclick="frappe.show_alert({message:\'Moderation Logs – coming soon\',indicator:\'blue\'})" ' +
					'style="height:30px;padding:0 12px;border:1.5px solid #E8B4BE;border-radius:7px;background:#FBEEF0;' +
					'color:#920C24;font-size:12px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:5px;">' +
					'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">' +
					'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>' +
					'<line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>' +
					'</svg>Moderation Logs</button>' +
				'</div>';

				// ── Build table rows ────────────────────────────────────────
				function dash() { return '<span class="tr-cdlg-dash">--</span>'; }
				function resultCell(grade, marks, maxMarks, isFail) {
					if (!grade && !marks) return dash();
					var gradeHtml = grade
						? '<div class="tr-cdlg-grade-pill ' + (isFail ? 'fail' : 'pass') + '">' + frappe.utils.escape_html(grade) + '</div>'
						: '';
					var marksHtml = '<div class="tr-cdlg-marks">' + parseFloat(marks || 0).toFixed(0) + ' /\u200B' + (maxMarks || 100) + '</div>';
					return '<div class="tr-cdlg-result">' + gradeHtml + marksHtml + '</div>';
				}

				// Separate backlog vs regular
				var backlogRows = [], regularRows = [];
				courses.forEach(function (c) {
					(c.is_failed ? backlogRows : regularRows).push(c);
				});

				function buildRows(list) {
					return list.map(function (c) {
						var isBacklog = !!c.is_failed;
						var courseCell =
							'<div class="tr-cdlg-cname">' + frappe.utils.escape_html(c.course_name || c.course) + '</div>' +
							'<div class="tr-cdlg-code">[' + frappe.utils.escape_html(c.course_code || c.course) + ']</div>' +
							(isBacklog ? '<span class="tr-cdlg-backlog">Backlog</span>' : '');

						var spec   = dash();
						var lpath  = c.course_type ? frappe.utils.escape_html(c.course_type) : dash();
						var creds  = c.credit_value ? c.credit_value : dash();
						var modMks = c.moderation_marks ? parseFloat(c.moderation_marks).toFixed(1) : dash();
						var regRes = resultCell(c.regular_grade, c.regular_marks, c.max_marks, isBacklog);
						var modGrd = c.moderated_grade ? '<span class="tr-cdlg-grade-pill">' + frappe.utils.escape_html(c.moderated_grade) + '</span>' : dash();
						var reRes  = (c.reexam_grade || c.reexam_marks)
							? resultCell(c.reexam_grade, c.reexam_marks, c.max_marks, false)
							: '<div class="tr-cdlg-result">' + dash() + '<div class="tr-cdlg-marks">-- /\u200B' + (c.max_marks || 100) + '</div></div>';
						var sgpa   = '<input type="checkbox" disabled ' + (c.consider_for_sgpa ? 'checked' : '') +
							' style="width:15px;height:15px;accent-color:#920C24;cursor:default;">';

						return '<tr>' +
							'<td class="left" style="min-width:200px;">' + courseCell + '</td>' +
							'<td>' + spec + '</td>' +
							'<td>' + lpath + '</td>' +
							'<td>' + creds + '</td>' +
							'<td>' + modMks + '</td>' +
							'<td>' + regRes + '</td>' +
							'<td>' + modGrd + '</td>' +
							'<td>' + reRes + '</td>' +
							'<td>' + sgpa + '</td>' +
						'</tr>';
					}).join('');
				}

				var tableHead = '<table class="tr-cdlg-table">' +
					'<thead><tr>' +
					'<th class="left">Course</th>' +
					'<th>Specialization</th>' +
					'<th>Learning Pathway</th>' +
					'<th>Credits</th>' +
					'<th>Moderation Marks</th>' +
					'<th>Regular Result</th>' +
					'<th>Moderated Grade</th>' +
					'<th>ReExam Result</th>' +
					'<th>Consider For SGPA</th>' +
					'</tr></thead><tbody>';

				var tableBody = '';
				if (backlogRows.length) {
					tableBody += '<tr><td colspan="9" style="padding:10px 10px 4px;"><span class="tr-dlg-section">Backlog Courses <span class="tr-dlg-cnt">(' + backlogRows.length + ')</span></span></td></tr>';
					tableBody += buildRows(backlogRows);
				}
				if (regularRows.length) {
					tableBody += '<tr><td colspan="9" style="padding:10px 10px 4px;"><span class="tr-dlg-section">Regular Courses <span class="tr-dlg-cnt regular">(' + regularRows.length + ')</span></span></td></tr>';
					tableBody += buildRows(regularRows);
				}
				if (!backlogRows.length && !regularRows.length) {
					tableBody += buildRows(courses);
				}
				tableBody += '</tbody></table>';

				var d = new frappe.ui.Dialog({
					title: 'Registered Courses',
					size: 'extra-large',
				});
				d.$body.css({ padding: '12px 16px', maxHeight: '70vh', overflowY: 'auto' });
				d.$body.html(profileHtml + modBtn + tableHead + tableBody);
				d.show();
			},
		});
	});

	// ── Institutional Filter Dialog ───────────────────────────────────────────
	function show_inst_filter_dialog(opts) {
		var sel = {
			programmes: S.inst_filter.programmes.slice(),
			batches:    S.inst_filter.batches.slice(),
		};
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
					t.icon + ' ' + t.label +
					(cnt ? '<span class="xif-type-badge">' + cnt + '</span>' : '') + '</div>';
			});
			$modal.find('.xif-types').html(html);
			$modal.find('.xif-type').on('click', function () {
				activeType = parseInt($(this).data('idx'));
				render_types(); render_panel();
			});
		}

		function render_panel(sv) {
			var t = TYPES[activeType];
			var items = (t.items || []).filter(function (v) {
				return !sv || String(v).toLowerCase().includes(sv.toLowerCase());
			});
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
			resetSelection();
			var total = count_all();
			var $btn = $body.find('#tr-inst-filter-btn');
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
