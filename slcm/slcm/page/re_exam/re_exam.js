frappe.pages['re-exam'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Re Exam',
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
	if (!document.getElementById('rx-style')) {
		var style = document.createElement('style');
		style.id  = 'rx-style';
		style.textContent = `
		.er2-wrap        { font-family:var(--font-stack,'Inter',sans-serif); padding:0; background:#f1f5f9; min-height:100vh; }
		.er2-page-header { background:#fff; border-radius:12px; padding:20px 24px; margin-bottom:16px;
		                   box-shadow:0 1px 3px rgba(0,0,0,.06); display:flex; align-items:center; gap:16px; }
		.er2-page-icon   { width:46px; height:46px; border-radius:12px; flex-shrink:0;
		                   display:flex; align-items:center; justify-content:center; }
		.er2-page-title  { font-size:17px; font-weight:800; color:#0f172a; line-height:1.2; }
		.er2-page-sub    { font-size:12px; color:#94a3b8; margin-top:3px; font-weight:500; }
		.er2-page-nav    { display:flex; gap:4px; margin-bottom:16px; background:#e2e8f0;
		                   border-radius:10px; padding:4px; width:fit-content; flex-wrap:wrap; }
		.er2-pnav-btn    { padding:8px 18px; cursor:pointer; font-size:13px; font-weight:600;
		                   color:#64748b; border-radius:7px; transition:all .2s; user-select:none;
		                   letter-spacing:.1px; border:none; background:transparent;
		                   display:inline-flex; align-items:center; gap:5px; }
		.er2-pnav-btn:hover  { color:#920C24; background:rgba(146,12,36,.08); }
		.er2-pnav-btn.active { background:#fff; color:#920C24; box-shadow:0 1px 4px rgba(0,0,0,.12); }

		/* Filter card */
		.rx-filter-card  { background:#fff; border-radius:12px; padding:14px 20px; margin-bottom:14px;
		                   box-shadow:0 1px 3px rgba(0,0,0,.06); display:flex; gap:14px;
		                   align-items:flex-end; flex-wrap:wrap; }
		.rx-fgroup       { display:flex; flex-direction:column; min-width:200px; flex:1; max-width:300px; }
		.rx-fgroup.wide  { max-width:400px; }
		.rx-filter-arrow { display:flex; align-items:flex-end; padding-bottom:9px; color:#cbd5e1; font-size:16px; flex-shrink:0; }
		.rx-active-badge { display:inline-block; border-radius:6px; font-size:10px; font-weight:700;
		                   padding:2px 7px; margin-left:6px; letter-spacing:.3px; vertical-align:middle; }
		.rx-active-badge.prog   { background:#FBEEF0; color:#920C24; }
		.rx-active-badge.course { background:#FBEEF0; color:#920C24; }
		.rx-flabel       { font-size:11px; color:#94a3b8; font-weight:700; margin-bottom:5px;
		                   text-transform:uppercase; letter-spacing:.6px; }
		.rx-select       { height:36px; border:1.5px solid #e2e8f0; border-radius:8px;
		                   padding:0 12px; font-size:13px; background:#fff; color:#1e293b;
		                   outline:none; cursor:pointer; transition:border-color .2s; }
		.rx-select:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }

		/* Stat cards */
		.rx-stat-cards   { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
		.rx-stat-card    { background:#fff; border-radius:12px; padding:14px 18px; flex:1;
		                   min-width:150px; box-shadow:0 1px 3px rgba(0,0,0,.06);
		                   border-top:3px solid var(--sc-color,#920C24);
		                   display:flex; align-items:center; gap:12px; }
		.rx-sc-icon      { width:38px; height:38px; border-radius:9px; flex-shrink:0;
		                   display:flex; align-items:center; justify-content:center;
		                   background:var(--sc-bg,#FBEEF0); color:var(--sc-color,#920C24); }
		.rx-sc-val       { font-size:22px; font-weight:800; color:var(--sc-color,#920C24); line-height:1.1; }
		.rx-sc-lbl       { font-size:10px; color:#94a3b8; font-weight:700; text-transform:uppercase;
		                   letter-spacing:.6px; margin-top:2px; }

		/* Settings card */
		.rx-settings-card { background:#fff; border-radius:12px; padding:18px 22px; margin-bottom:14px;
		                    box-shadow:0 1px 3px rgba(0,0,0,.06); border-left:4px solid #920C24; }
		.rx-settings-title { font-size:13px; font-weight:800; color:#0f172a; margin-bottom:14px;
		                     display:flex; align-items:center; gap:8px; }
		.rx-settings-grid  { display:flex; gap:14px; flex-wrap:wrap; align-items:flex-end; }
		.rx-field-group    { display:flex; flex-direction:column; min-width:180px; flex:1; max-width:260px; }
		.rx-field-label    { font-size:11px; color:#94a3b8; font-weight:700; margin-bottom:5px;
		                     text-transform:uppercase; letter-spacing:.6px; }
		.rx-input          { height:36px; border:1.5px solid #e2e8f0; border-radius:8px;
		                     padding:0 12px; font-size:13px; background:#fff; color:#1e293b;
		                     outline:none; transition:border-color .2s; width:100%; box-sizing:border-box; }
		.rx-input:focus    { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }
		.rx-save-btn       { height:36px; padding:0 20px; border-radius:8px; border:none;
		                     background:#920C24;
		                     color:#fff; font-size:13px; font-weight:700; cursor:pointer;
		                     display:inline-flex; align-items:center; gap:6px; transition:opacity .15s;
		                     white-space:nowrap; }
		.rx-save-btn:hover { opacity:.88; }
		.rx-save-btn:disabled { opacity:.5; cursor:default; }
		.rx-saved-badge    { display:inline-flex; align-items:center; gap:4px; font-size:11px;
		                     font-weight:700; color:#920C24; margin-left:10px;
		                     background:#F5D9DE; border-radius:6px; padding:3px 9px; }

		/* Students table card */
		.rx-table-card    { background:#fff; border-radius:12px; box-shadow:0 1px 3px rgba(0,0,0,.06);
		                    overflow:hidden; border-top:3px solid #920C24; }
		.rx-table-topbar  { display:flex; align-items:center; justify-content:space-between;
		                    padding:12px 16px 10px; border-bottom:1.5px solid #f1f5f9; }
		.rx-count-lbl     { font-size:13px; font-weight:700; color:#0f172a; }
		.rx-srch          { position:relative; }
		.rx-srch input    { width:260px; height:34px; border:1.5px solid #e2e8f0; border-radius:8px;
		                    padding:0 12px 0 34px; font-size:13px; outline:none; color:#1e293b;
		                    background:#fff; transition:border-color .2s; box-sizing:border-box; }
		.rx-srch input:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }
		.rx-srch-ico      { position:absolute; left:10px; top:10px; color:#94a3b8; }

		/* Custom table */
		.rx-tbl-scroll    { overflow-x:auto; }
		.rx-tbl           { width:100%; border-collapse:collapse; font-size:13px; min-width:780px; }
		.rx-tbl thead tr  { background:#f8fafc; }
		.rx-tbl th        { padding:10px 14px; text-align:left; font-size:11px; font-weight:700;
		                    color:#475569; border-bottom:2px solid #e2e8f0; white-space:nowrap;
		                    text-transform:uppercase; letter-spacing:.5px; }
		.rx-tbl th.rx-th-center { text-align:center; }
		.rx-tbl td        { padding:0 14px; border-bottom:1.5px solid #f1f5f9; vertical-align:middle; }
		.rx-tbl tbody tr  { height:64px; transition:background .12s; }
		.rx-tbl tbody tr:hover td { background:#FDF8F9; }
		.rx-tbl tbody tr:last-child td { border-bottom:none; }
		.rx-tbl .rx-td-num { width:42px; text-align:center; font-size:11px; font-weight:700; color:#cbd5e1;
		                     background:#FDF8F9; border-right:1.5px solid #f1f5f9; }
		.rx-tbl .rx-td-center { text-align:center; }

		/* Student cell */
		.rx-s-cell        { display:flex; align-items:center; gap:10px; }
		.rx-savatar       { width:38px; height:38px; border-radius:10px; flex-shrink:0;
		                    display:flex; align-items:center; justify-content:center;
		                    font-size:13px; font-weight:700; color:#fff; overflow:hidden; }
		.rx-savatar img   { width:100%; height:100%; object-fit:cover; }
		.rx-sname         { font-size:13px; font-weight:700; color:#0f172a; line-height:1.3; }
		.rx-semail        { font-size:11px; color:#94a3b8; margin-top:1px; }
		.rx-grade-badge   { display:inline-flex; align-items:center; justify-content:center;
		                    min-width:34px; height:26px; border-radius:7px; font-size:12px;
		                    font-weight:800; background:#FBEEF0; color:#920C24;
		                    border:1.5px solid #E8B4BE; padding:0 8px; }

		/* Toggle switch */
		.rx-toggle        { position:relative; display:inline-flex; align-items:center; gap:8px;
		                    cursor:pointer; user-select:none; }
		.rx-toggle input  { position:absolute; opacity:0; width:0; height:0; }
		.rx-toggle-track  { position:relative; display:inline-block; width:44px; height:24px;
		                    background:#e2e8f0; border-radius:12px; transition:background .22s;
		                    flex-shrink:0; border:2px solid #e2e8f0; box-sizing:border-box; }
		.rx-toggle-track:before { content:''; position:absolute; width:16px; height:16px;
		                          left:2px; top:2px; background:#fff; border-radius:50%;
		                          transition:transform .22s; box-shadow:0 1px 4px rgba(0,0,0,.2); }
		.rx-toggle input:checked + .rx-toggle-track           { background:#920C24; border-color:#920C24; }
		.rx-toggle input:checked + .rx-toggle-track:before    { transform:translateX(20px); }
		.rx-toggle input:disabled + .rx-toggle-track          { opacity:.5; cursor:not-allowed; }
		.rx-toggle-lbl    { font-size:12px; font-weight:700; min-width:52px; color:#94a3b8;
		                    transition:color .2s; }
		.rx-toggle input:checked ~ .rx-toggle-lbl             { color:#920C24; }
		.rx-toggle:hover .rx-toggle-track                     { border-color:#94a3b8; }
		.rx-toggle input:checked:hover ~ .rx-toggle-lbl       { color:#920C24; }

		/* Empty / Loading */
		.rx-empty         { padding:80px 20px; display:flex; flex-direction:column;
		                    align-items:center; justify-content:center; text-align:center; }
		.rx-empty-icon    { width:56px; height:56px; border-radius:14px; background:#f1f5f9;
		                    display:flex; align-items:center; justify-content:center; margin-bottom:14px; }
		.rx-empty-txt     { font-size:14px; font-weight:700; color:#94a3b8; }
		.rx-empty-sub     { font-size:12px; color:#cbd5e1; margin-top:4px; }

		/* Avatar gradients */
		.av-0{background:#920C24;}
		.av-1{background:#920C24;}
		.av-2{background:#920C24;}
		.av-3{background:#920C24;}
		.av-4{background:#920C24;}
		.av-5{background:#920C24;}
		.av-6{background:#920C24;}
		.av-7{background:#920C24;}

		/* ── Registered stat card CTA highlight ── */
		.rx-stat-card-cta { box-shadow:0 0 0 2px #920C24, 0 4px 16px rgba(146,12,36,.20) !important;
		                    transition:transform .15s, box-shadow .15s; }
		.rx-stat-card-cta:hover { transform:translateY(-2px);
		                          box-shadow:0 0 0 2px #920C24, 0 8px 24px rgba(146,12,36,.28) !important; }
		.rx-cta-hint   { font-size:10px; font-weight:700; color:#920C24; margin-top:4px;
		                 letter-spacing:.4px; display:flex; align-items:center; gap:3px; }
		@keyframes rx-ring { 0%,100%{box-shadow:0 0 0 2px #920C24,0 0 0 5px rgba(146,12,36,.0);}
		                     50%{box-shadow:0 0 0 2px #920C24,0 0 0 7px rgba(146,12,36,.25);} }
		.rx-stat-card-cta { animation:rx-ring 2s ease-in-out infinite; }

		/* Status badges */
		.rx-st-badge   { display:inline-flex; align-items:center; height:22px; border-radius:6px;
		                 font-size:11px; font-weight:700; padding:0 9px; white-space:nowrap; }
		.rx-st-reg     { background:#FBEEF0; color:#920C24; }
		.rx-st-paid    { background:#d1fae5; color:#059669; }
		.rx-st-cancel  { background:#f1f5f9; color:#94a3b8; }

		/* Mark paid button */
		.rx-pay-btn    { height:28px; padding:0 12px; border-radius:6px; border:none;
		                 background:#920C24;
		                 color:#fff; font-size:11px; font-weight:700; cursor:pointer;
		                 transition:opacity .15s; }
		.rx-pay-btn:hover { opacity:.85; }

		/* Export CSV button */
		.rx-export-btn { height:34px; padding:0 14px; border-radius:8px; border:1.5px solid #e2e8f0;
		                 background:#fff; color:#475569; font-size:12px; font-weight:700; cursor:pointer;
		                 display:inline-flex; align-items:center; gap:5px; transition:all .15s; }
		.rx-export-btn:hover { border-color:#920C24; color:#920C24; background:#FBEEF0; }

		/* Apply to all courses button */
		.rx-bulk-btn   { height:36px; padding:0 16px; border-radius:8px; border:1.5px solid #e2e8f0;
		                 background:#fff; color:#475569; font-size:12px; font-weight:700; cursor:pointer;
		                 display:inline-flex; align-items:center; gap:5px; transition:all .15s;
		                 white-space:nowrap; }
		.rx-bulk-btn:hover   { border-color:#920C24; color:#920C24; background:#FBEEF0; }
		.rx-bulk-btn:disabled { opacity:.5; cursor:default; }

		/* Override reason pill */
		.rx-reason-pill { display:inline-block; border-radius:5px; font-size:10px; font-weight:700;
		                  padding:2px 6px; background:#F5D9DE; color:#6E091B; margin-top:3px;
		                  cursor:help; max-width:130px; overflow:hidden; text-overflow:ellipsis;
		                  white-space:nowrap; vertical-align:middle; }

		/* Source selection card */
		.rx-source-card      { background:#fff; border-radius:12px; padding:18px 22px; margin-bottom:14px;
		                       box-shadow:0 1px 3px rgba(0,0,0,.06); border-left:4px solid #920C24; }
		.rx-source-title     { font-size:13px; font-weight:800; color:#0f172a; margin-bottom:14px;
		                       display:flex; align-items:center; gap:8px; }
		.rx-source-opts      { display:flex; gap:12px; flex-wrap:wrap; }
		.rx-source-opt       { flex:1; min-width:200px; cursor:pointer; border:2px solid #e2e8f0;
		                       border-radius:10px; padding:14px; transition:all .18s; background:#fff;
		                       user-select:none; }
		.rx-source-opt-active { border-color:#920C24; background:#FBEEF0; }
		.rx-source-opt-inner  { display:flex; align-items:center; gap:12px; pointer-events:none; }
		.rx-source-opt-icon   { width:38px; height:38px; border-radius:9px; flex-shrink:0;
		                        display:flex; align-items:center; justify-content:center; }
		.rx-source-opt-title  { font-size:13px; font-weight:700; color:#0f172a; }
		.rx-source-opt-sub    { font-size:11px; color:#94a3b8; margin-top:2px; }
		.rx-dl-tpl-btn        { height:34px; padding:0 14px; border-radius:8px; border:1.5px solid #920C24;
		                        background:#fff; color:#920C24; font-size:12px; font-weight:700; cursor:pointer;
		                        display:inline-flex; align-items:center; gap:6px; transition:all .15s; }
		.rx-dl-tpl-btn:hover  { background:#F5D9DE; border-color:#920C24; color:#920C24; }
		.rx-drop-zone         { border:2px dashed #e2e8f0; border-radius:10px; padding:28px 20px;
		                        text-align:center; cursor:pointer; transition:all .18s; background:#FDF8F9;
		                        display:flex; flex-direction:column; align-items:center; gap:6px; }
		.rx-drop-zone:hover, .rx-drop-zone.rx-drag-over { border-color:#920C24; background:#FBEEF0; }
		.rx-dz-title          { font-size:13px; font-weight:600; color:#475569; }
		.rx-dz-link           { color:#920C24; cursor:pointer; text-decoration:underline; }
		.rx-dz-sub            { font-size:11px; color:#94a3b8; }
		`;
		document.head.appendChild(style);
	}

	// ── State ─────────────────────────────────────────────────────────────────
	var S = {
		exam_plan:          null,
		programme:          '',
		course:             '',
		students:           [],
		total:              0,
		search:             '',
		search_timer:       null,
		source:             'tool',   // 'tool' | 'manual'
		uploaded_students:  [],
	};

	// ── Render shell ──────────────────────────────────────────────────────────
	var $body = $(page.main);
	$body.html(`
		<div class="er2-wrap" style="padding:20px 24px;">

			<div class="er2-page-header">
				<div class="er2-page-icon" style="background:#920C24;">
					<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.51"/></svg>
				</div>
				<div>
					<div class="er2-page-title">Re Exam</div>
					<div class="er2-page-sub">Configure re-exam settings and view failed students per course</div>
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
				<button class="er2-pnav-btn" onclick="frappe.set_route('publish-result')">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
					Publish Results
				</button>
				<button class="er2-pnav-btn" onclick="frappe.set_route('result-settings')">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
					Settings
				</button>
				<button class="er2-pnav-btn active">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.51"/></svg>
					Re Exam
				</button>
				<button class="er2-pnav-btn" onclick="frappe.set_route('improvement-exam')">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
					Improvement Exam
				</button>
				<button class="er2-pnav-btn" id="rx-nav-consolidated">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
					Consolidated Report
				</button>
			</div>

			<!-- Filter card -->
			<div class="rx-filter-card">
				<div class="rx-fgroup">
					<span class="rx-flabel">Exam Plan</span>
					<select class="rx-select" id="rx-exam-plan">
						<option value="">Choose Exam Plan</option>
					</select>
				</div>
				<div class="rx-filter-arrow" id="rx-prog-arrow" style="display:none;">&#8594;</div>
				<div class="rx-fgroup" id="rx-prog-group" style="display:none;">
					<span class="rx-flabel">Programme
						<span class="rx-active-badge prog" id="rx-prog-badge" style="display:none;">Filtered</span>
					</span>
					<select class="rx-select" id="rx-prog-select">
						<option value="">All Programmes</option>
					</select>
				</div>
				<div class="rx-filter-arrow" id="rx-course-arrow" style="display:none;">&#8594;</div>
				<div class="rx-fgroup wide" id="rx-course-group" style="display:none;">
					<span class="rx-flabel">Course
						<span class="rx-active-badge course" id="rx-course-badge" style="display:none;">Filtered</span>
					</span>
					<select class="rx-select" id="rx-course-select">
						<option value="">All Courses</option>
					</select>
				</div>
			</div>

			<!-- Main content -->
			<div id="rx-content" style="display:none;">

				<!-- Stat cards -->
				<div class="rx-stat-cards" id="rx-stat-cards" style="display:none;"></div>

				<!-- Settings card -->
				<div class="rx-settings-card" id="rx-settings-card" style="display:none;">
					<div class="rx-settings-title">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2.5"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
						Re-Exam Settings
						<span id="rx-saved-badge" class="rx-saved-badge" style="display:none;">
							<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
							Saved
						</span>
					</div>
					<div class="rx-settings-grid">
						<div class="rx-field-group">
							<span class="rx-field-label">Re-Exam Fee Amount</span>
							<input class="rx-input" type="number" id="rx-fee" placeholder="0.00" step="0.01" min="0">
						</div>
						<div class="rx-field-group">
							<span class="rx-field-label">Deadline From</span>
							<input class="rx-input" type="date" id="rx-deadline-from">
						</div>
						<div class="rx-field-group">
							<span class="rx-field-label">Deadline To</span>
							<input class="rx-input" type="date" id="rx-deadline-to">
						</div>
						<div style="display:flex;align-items:flex-end;padding-bottom:1px;gap:8px;">
							<button class="rx-save-btn" id="rx-save-settings">
								<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
								Save Settings
							</button>
							<button class="rx-bulk-btn" id="rx-bulk-apply" title="Apply this fee &amp; deadline to every course in the selected Exam Plan">
								<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
								Apply to All Courses
							</button>
						</div>
					</div>
				</div>

				<!-- Source selection card -->
				<div class="rx-source-card" id="rx-source-card" style="display:none;">
					<div class="rx-source-title">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2.5"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>
						Failed Student List Source
					</div>
					<div class="rx-source-opts">
						<label class="rx-source-opt rx-source-opt-active" id="rx-src-tool-lbl" onclick="rxSetSource('tool')">
							<input type="radio" name="rx-src" value="tool" id="rx-src-tool" checked style="display:none;">
							<div class="rx-source-opt-inner">
								<div class="rx-source-opt-icon" style="background:#FBEEF0;color:#920C24;">
									<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.51"/></svg>
								</div>
								<div>
									<div class="rx-source-opt-title">Fetch from Tool</div>
									<div class="rx-source-opt-sub">Auto-pull failed students from exam results</div>
								</div>
							</div>
						</label>
						<label class="rx-source-opt" id="rx-src-manual-lbl" onclick="rxSetSource('manual')">
							<input type="radio" name="rx-src" value="manual" id="rx-src-manual" style="display:none;">
							<div class="rx-source-opt-inner">
								<div class="rx-source-opt-icon" style="background:#FBEEF0;color:#920C24;">
									<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
								</div>
								<div>
									<div class="rx-source-opt-title">Upload Manually</div>
									<div class="rx-source-opt-sub">Upload a CSV file with your student list</div>
								</div>
							</div>
						</label>
					</div>
					<!-- Upload panel (visible when Upload Manually selected) -->
					<div id="rx-upload-panel" style="display:none;margin-top:16px;padding-top:16px;border-top:1.5px solid #f1f5f9;">
						<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap;">
							<button class="rx-dl-tpl-btn" id="rx-dl-template">
								<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
								Download Sample Template
							</button>
							<span style="font-size:12px;color:#94a3b8;">Download, fill in student details, then upload below</span>
						</div>
						<div class="rx-drop-zone" id="rx-drop-zone">
							<input type="file" id="rx-csv-input" accept=".csv" style="display:none;">
							<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="1.8"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
							<div class="rx-dz-title">Drop CSV here or <span class="rx-dz-link" id="rx-dz-browse">Browse file</span></div>
							<div class="rx-dz-sub">Accepted: .csv &mdash; use the sample template above</div>
						</div>
						<div id="rx-upload-status" style="display:none;margin-top:10px;align-items:center;gap:10px;">
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2.5" style="flex-shrink:0;"><polyline points="20 6 9 17 4 12"/></svg>
							<span id="rx-upload-filename" style="font-size:13px;font-weight:600;color:#1e293b;"></span>
							<button id="rx-upload-clear" style="height:24px;width:24px;border-radius:6px;border:1.5px solid #e2e8f0;background:#fff;color:#94a3b8;font-size:14px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-weight:700;" title="Clear uploaded file">&times;</button>
						</div>
					</div>
				</div>

				<!-- Warning banner -->
				<div id="rx-warning-banner" style="display:none;background:#F5D9DE;border:1.5px solid #E8B4BE;border-radius:10px;padding:10px 16px;margin-bottom:12px;align-items:center;gap:10px;font-size:12.5px;color:#6E091B;">
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2.5" style="flex-shrink:0;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
					<span><b>No failed grades defined in grading schema.</b> Showing all graded students. Open the <b>Grading Schema</b> and check the <b>Failed</b> checkbox on failing grades (e.g. F) to filter correctly.</span>
				</div>

				<!-- Students table card -->
				<div class="rx-table-card">
					<div class="rx-table-topbar">
						<span id="rx-count-lbl" class="rx-count-lbl">Failed Students (0)</span>
						<div style="display:flex;align-items:center;gap:8px;">
							<button class="rx-export-btn" id="rx-export-btn" style="display:none;" title="Download failed students list as CSV">
								<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
								Export CSV
							</button>
							<div class="rx-srch">
								<svg class="rx-srch-ico" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
								<input id="rx-search" type="text" placeholder="Search by name or ID…">
							</div>
						</div>
					</div>

					<!-- Placeholder -->
					<div id="rx-placeholder" class="rx-empty">
						<div class="rx-empty-icon">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
						</div>
						<div class="rx-empty-txt" id="rx-ph-title">Select an Exam Plan &amp; Course</div>
						<div class="rx-empty-sub" id="rx-ph-sub">Choose filters above to view failed students</div>
					</div>

					<!-- Table -->
					<div id="rx-table-wrap" style="display:none;" class="rx-tbl-scroll">
						<table class="rx-tbl" id="rx-tbl">
							<thead>
								<tr>
									<th class="rx-td-num">#</th>
									<th style="min-width:200px;">Student</th>
									<th style="width:120px;">Reg. ID</th>
									<th style="width:110px;">Programme</th>
									<th style="width:70px;" class="rx-th-center">Grade</th>
									<th style="width:100px;">Total Marks</th>
									<th style="width:140px;" class="rx-th-center">Allow Re-Exam</th>
								</tr>
							</thead>
							<tbody id="rx-tbody"></tbody>
						</table>
					</div>
				</div>

			</div>
		</div>
	`);

	// ── DOM refs ──────────────────────────────────────────────────────────────
	var $examPlan     = $body.find('#rx-exam-plan');
	var $progGroup    = $body.find('#rx-prog-group');
	var $progArrow    = $body.find('#rx-prog-arrow');
	var $progSelect   = $body.find('#rx-prog-select');
	var $progBadge    = $body.find('#rx-prog-badge');
	var $courseArrow  = $body.find('#rx-course-arrow');
	var $courseGroup  = $body.find('#rx-course-group');
	var $courseSelect = $body.find('#rx-course-select');
	var $courseBadge  = $body.find('#rx-course-badge');
	var $content      = $body.find('#rx-content');
	var $statCards    = $body.find('#rx-stat-cards');
	var $settingsCard = $body.find('#rx-settings-card');
	var $savedBadge   = $body.find('#rx-saved-badge');
	var $feeInput     = $body.find('#rx-fee');
	var $dlFrom       = $body.find('#rx-deadline-from');
	var $dlTo         = $body.find('#rx-deadline-to');
	var $saveBtn      = $body.find('#rx-save-settings');
	var $search       = $body.find('#rx-search');
	var $countLbl     = $body.find('#rx-count-lbl');
	var $warning      = $body.find('#rx-warning-banner');
	var $placeholder  = $body.find('#rx-placeholder');
	var $tableWrap    = $body.find('#rx-table-wrap');
	var $tbody        = $body.find('#rx-tbody');
	var $exportBtn      = $body.find('#rx-export-btn');
	var $bulkApplyBtn   = $body.find('#rx-bulk-apply');
	var $sourceCard     = $body.find('#rx-source-card');
	var $uploadPanel    = $body.find('#rx-upload-panel');
	var $uploadStatus   = $body.find('#rx-upload-status');
	var $uploadFilename = $body.find('#rx-upload-filename');
	var $dropZone       = $body.find('#rx-drop-zone');
	var $csvInput       = $body.find('#rx-csv-input');

	// ── Load Exam Plans ───────────────────────────────────────────────────────
	frappe.call({
		method: 'slcm.slcm.page.re_exam.re_exam.get_exam_plans',
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
		S.exam_plan  = $(this).val();
		S.programme  = '';
		S.course     = '';
		S.search     = '';
		$search.val('');
		$progSelect.val(''); $progBadge.hide();
		$courseSelect.val(''); $courseBadge.hide();
		$settingsCard.hide();
		clearSettings();
		// Reset source to 'tool' on exam plan change
		S.source            = 'tool';
		S.uploaded_students = [];
		$body.find('#rx-src-tool').prop('checked', true);
		$body.find('.rx-source-opt').removeClass('rx-source-opt-active');
		$body.find('#rx-src-tool-lbl').addClass('rx-source-opt-active');
		$uploadPanel.hide();
		$uploadStatus.hide();
		if (S.exam_plan) {
			$content.show();
			$sourceCard.show();
			loadProgrammes();
			loadCourses();
			loadStats();
			loadStudents();
		} else {
			$content.hide();
			$sourceCard.hide();
			$statCards.hide();
			$progGroup.hide(); $progArrow.hide();
			$courseGroup.hide(); $courseArrow.hide();
			showPlaceholder('Select an Exam Plan & Course', 'Choose filters above to view failed students');
		}
	});

	// ── Programme change ──────────────────────────────────────────────────────
	$progSelect.on('change', function () {
		S.programme = $(this).val();
		S.course    = '';
		S.search    = '';
		$search.val('');
		$courseSelect.val(''); $courseBadge.hide();
		$progBadge.toggle(!!S.programme);
		$settingsCard.hide();
		clearSettings();
		loadCourses();
		loadStats();
		loadStudents();
	});

	// ── Course change ─────────────────────────────────────────────────────────
	$courseSelect.on('change', function () {
		S.course = $(this).val();
		S.search = '';
		$search.val('');
		$courseBadge.toggle(!!S.course);
		if (S.course) {
			$settingsCard.show();
			loadSettings();
		} else {
			$settingsCard.hide();
			clearSettings();
		}
		loadStats();
		loadStudents();
	});

	// ── Search ────────────────────────────────────────────────────────────────
	$search.on('input', function () {
		clearTimeout(S.search_timer);
		var q = $(this).val().toLowerCase().trim();
		S.search_timer = setTimeout(function () {
			filterTable(q);
		}, 250);
	});

	// ── Save settings ─────────────────────────────────────────────────────────
	$saveBtn.on('click', function () {
		if (!S.exam_plan || !S.course) {
			frappe.show_alert({ message: 'Select Exam Plan and Course first.', indicator: 'orange' });
			return;
		}
		$saveBtn.prop('disabled', true).text('Saving…');
		frappe.call({
			method: 'slcm.slcm.page.re_exam.re_exam.save_re_exam_setting',
			args: {
				exam_plan:     S.exam_plan,
				course:        S.course,
				re_exam_fee:   $feeInput.val()  || null,
				deadline_from: $dlFrom.val()    || null,
				deadline_to:   $dlTo.val()      || null,
			},
			callback: function (r) {
				$saveBtn.prop('disabled', false).html(
					'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Save Settings'
				);
				if (r.message) {
					$savedBadge.show();
					setTimeout(function () { $savedBadge.hide(); }, 2500);
					frappe.show_alert({ message: 'Re-exam settings saved.', indicator: 'green' });
				}
			},
			error: function () {
				$saveBtn.prop('disabled', false).html(
					'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Save Settings'
				);
			},
		});
	});

	// ── Consolidated Report ───────────────────────────────────────────────────
	$body.find('#rx-nav-consolidated').on('click', function () {
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
			primary_action: function (v) {
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
			},
		});
		d.show();
	});

	// ── Helpers ───────────────────────────────────────────────────────────────
	function loadProgrammes() {
		if (!S.exam_plan) return;
		frappe.call({
			method: 'slcm.slcm.page.re_exam.re_exam.get_programmes_for_exam_plan',
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
				if (progs.length) { $progGroup.show(); $progArrow.show(); }
				else { $progGroup.hide(); $progArrow.hide(); }
			},
		});
	}

	function loadCourses() {
		if (!S.exam_plan) return;
		frappe.call({
			method: 'slcm.slcm.page.re_exam.re_exam.get_courses_for_exam_plan',
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
				if (courses.length) { $courseGroup.show(); $courseArrow.show(); }
				else { $courseGroup.hide(); $courseArrow.hide(); }
			},
		});
	}

	function loadStats() {
		if (!S.exam_plan || !S.course) { $statCards.hide(); return; }
		frappe.call({
			method: 'slcm.slcm.page.re_exam.re_exam.get_re_exam_stats',
			args:   { exam_plan: S.exam_plan, course: S.course },
			callback: function (r) {
				if (!r.message) return;
				var d = r.message;
				var cards = [
					{ label: 'Total Students', value: d.total      || 0, color: '#920C24', bg: '#FBEEF0',
					  icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>' },
					{ label: 'Failed',         value: d.failed     || 0, color: '#920C24', bg: '#FBEEF0',
					  icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>' },
					{ label: 'Passed',         value: d.passed     || 0, color: '#920C24', bg: '#F5D9DE',
					  icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/></svg>' },
					{ label: 'Registered',     value: d.registered || 0, color: '#920C24', bg: '#FBEEF0',
					  clickable: true,
					  icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>' },
				];
				$statCards.html(cards.map(function (c) {
					var extra = c.clickable
						? ' id="rx-reg-stat-card" class="rx-stat-card-cta" style="--sc-color:' + c.color + ';--sc-bg:' + c.bg + ';cursor:pointer;" title="Click to view registered students"'
						: ' style="--sc-color:' + c.color + ';--sc-bg:' + c.bg + ';"';
					return '<div class="rx-stat-card"' + extra + '>' +
						'<div class="rx-sc-icon">' + c.icon + '</div>' +
						'<div><div class="rx-sc-val">' + c.value + '</div>' +
						'<div class="rx-sc-lbl">' + c.label + '</div>' +
						(c.clickable ? '<div class="rx-cta-hint"><svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="9 18 15 12 9 6"/></svg> View all</div>' : '') +
						'</div></div>';
				}).join('')).show();
				$body.find('#rx-reg-stat-card').off('click').on('click', function () {
					rxScrollToRegistrations();
				});
			},
		});
	}

	function loadSettings() {
		if (!S.exam_plan || !S.course) return;
		$savedBadge.hide();
		frappe.call({
			method: 'slcm.slcm.page.re_exam.re_exam.get_re_exam_setting',
			args:   { exam_plan: S.exam_plan, course: S.course },
			callback: function (r) {
				var d = r.message || {};
				$feeInput.val(d.re_exam_fee   || '');
				$dlFrom.val(d.deadline_from   || '');
				$dlTo.val(d.deadline_to       || '');
			},
		});
	}

	function clearSettings() {
		$feeInput.val(''); $dlFrom.val(''); $dlTo.val(''); $savedBadge.hide();
	}

	function showPlaceholder(title, sub) {
		$placeholder.find('#rx-ph-title').text(title);
		$placeholder.find('#rx-ph-sub').text(sub);
		$placeholder.show();
		$tableWrap.hide();
		$warning.hide();
		$countLbl.text('Failed Students (0)');
	}

	// ── Load students ─────────────────────────────────────────────────────────
	function loadStudents() {
		// Manual upload mode — do not fetch from DB; wait for CSV upload
		if (S.source === 'manual') {
			if (!S.uploaded_students || !S.uploaded_students.length) {
				showPlaceholder('Upload a CSV file', 'Download the sample template, fill in student details, then upload');
			} else {
				renderTable(S.uploaded_students);
			}
			return;
		}
		if (!S.exam_plan) { showPlaceholder('Select an Exam Plan & Course', 'Choose filters above to view failed students'); return; }
		if (!S.course)    { showPlaceholder('Select a Course', 'Choose a course to view failed students'); return; }

		$placeholder.find('#rx-ph-title').text('Loading…');
		$placeholder.find('#rx-ph-sub').text('');
		$placeholder.show(); $tableWrap.hide();

		frappe.call({
			method: 'slcm.slcm.page.re_exam.re_exam.get_failed_students',
			args: { exam_plan: S.exam_plan, course: S.course, search: '', page: 1, page_length: 500 },
			callback: function (r) {
				var data = r.message || { students: [], total: 0 };
				S.students            = data.students;
				S.total               = data.total;
				S.all_grades_fallback = !!data.all_grades_fallback;
				renderTable(data.students);
			},
		});
	}

	// ── Render table ──────────────────────────────────────────────────────────
	var AV_COLORS = ['av-0','av-1','av-2','av-3','av-4','av-5','av-6','av-7'];

	function renderTable(students) {
		var label = S.all_grades_fallback ? 'Graded Students' : 'Failed Students';
		$countLbl.text(label + ' (' + (students ? students.length : 0) + ')');
		$warning[S.all_grades_fallback ? 'css' : 'hide']('display', S.all_grades_fallback ? 'flex' : 'none');
		if (S.all_grades_fallback) $warning.css('display', 'flex');
		else $warning.hide();

		if (!students || !students.length) {
			$exportBtn.hide();
			showPlaceholder('No Students Found', 'No graded students match the current filters.');
			return;
		}

		$exportBtn.show();
		$placeholder.hide();
		$tableWrap.show();

		var rows = students.map(function (s, i) {
			var initials = ((s.student_name || '').split(' ')
				.map(function (w) { return w[0] || ''; }).join('').slice(0, 2)).toUpperCase() || '?';
			var avClass  = AV_COLORS[i % 8];
			var avatar   = s.image
				? '<div class="rx-savatar" style="overflow:hidden;"><img src="' + frappe.utils.escape_html(s.image) + '" loading="lazy"></div>'
				: '<div class="rx-savatar ' + avClass + '">' + frappe.utils.escape_html(initials) + '</div>';

			var allowed     = s.is_allowed !== false;
			var chk         = allowed ? 'checked' : '';
			var lbl         = allowed ? 'Allowed' : 'Blocked';
			var reasonPill  = (!allowed && s.override_reason)
				? '<span class="rx-reason-pill" title="' + frappe.utils.escape_html(s.override_reason) + '">' + frappe.utils.escape_html(s.override_reason) + '</span>'
				: '';

			return '<tr data-name="' + frappe.utils.escape_html(s.student_name || '') + '" ' +
				       'data-reg="' + frappe.utils.escape_html(s.registration_id || '') + '">' +
				'<td class="rx-td-num">' + (i + 1) + '</td>' +
				'<td>' +
					'<div class="rx-s-cell">' + avatar +
						'<div>' +
							'<div class="rx-sname">' + frappe.utils.escape_html(s.student_name || '—') + '</div>' +
							(s.email ? '<div class="rx-semail">' + frappe.utils.escape_html(s.email) + '</div>' : '') +
						'</div>' +
					'</div>' +
				'</td>' +
				'<td style="font-size:12px;font-weight:600;color:#475569;">' + frappe.utils.escape_html(s.registration_id || '—') + '</td>' +
				'<td style="font-size:12px;color:#64748b;">' + frappe.utils.escape_html(s.programme || '—') + '</td>' +
				'<td class="rx-td-center">' +
					'<span class="rx-grade-badge">' + frappe.utils.escape_html(s.grade || '—') + '</span>' +
				'</td>' +
				'<td style="font-size:13px;font-weight:600;color:#0f172a;">' +
					(s.total_marks !== null && s.total_marks !== undefined ? parseFloat(s.total_marks).toFixed(2) : '—') +
				'</td>' +
				'<td class="rx-td-center">' +
					'<div style="display:inline-flex;flex-direction:column;align-items:center;gap:3px;">' +
						'<label class="rx-toggle" onclick="event.stopPropagation();">' +
							'<input type="checkbox" ' + chk +
								' data-student="' + frappe.utils.escape_html(s.student) + '"' +
								' data-reason="' + frappe.utils.escape_html(s.override_reason || '') + '"' +
								' onchange="rxToggleAllow(this)">' +
							'<span class="rx-toggle-track"></span>' +
							'<span class="rx-toggle-lbl">' + lbl + '</span>' +
						'</label>' +
						reasonPill +
					'</div>' +
				'</td>' +
			'</tr>';
		}).join('');

		$tbody.html(rows);
	}

	// ── Client-side search filter ─────────────────────────────────────────────
	function filterTable(q) {
		if (!q) {
			renderTable(S.students);
			return;
		}
		var filtered = (S.students || []).filter(function (s) {
			var name = (s.student_name || '').toLowerCase();
			var reg  = (s.registration_id || '').toLowerCase();
			return name.indexOf(q) !== -1 || reg.indexOf(q) !== -1;
		});
		renderTable(filtered);
	}

	// ── Toggle allow/block ────────────────────────────────────────────────────
	window.rxToggleAllow = function (checkbox) {
		var student   = checkbox.getAttribute('data-student');
		var isAllowed = checkbox.checked ? 1 : 0;
		var lbl       = checkbox.parentElement.querySelector('.rx-toggle-lbl');

		if (!student || !S.exam_plan || !S.course) return;

		if (!isAllowed) {
			// Revert visually, then prompt for reason before confirming block
			checkbox.checked = true;
			frappe.prompt(
				[
					{
						fieldname: 'reason',
						fieldtype: 'Select',
						label:     'Block Reason',
						options:   'Absent\nMalpractice\nAttendance Shortage\nMedical Leave\nOther',
						reqd:      1,
					},
					{
						fieldname:  'custom_reason',
						fieldtype:  'Data',
						label:      'Specify',
						depends_on: 'eval:doc.reason=="Other"',
					},
				],
				function (vals) {
					var reason = vals.reason === 'Other' ? (vals.custom_reason || 'Other') : vals.reason;
					checkbox.checked = false;
					_doToggle(checkbox, student, 0, reason, lbl);
				},
				'Block Student from Re-Exam',
				'Confirm Block'
			);
			return;
		}

		_doToggle(checkbox, student, 1, '', lbl);
	};

	function _doToggle(checkbox, student, isAllowed, reason, lbl) {
		checkbox.disabled = true;
		frappe.call({
			method: 'slcm.slcm.page.re_exam.re_exam.set_student_re_exam_allowed',
			args: {
				exam_plan:       S.exam_plan,
				course:          S.course,
				student:         student,
				is_allowed:      isAllowed,
				override_reason: reason || '',
			},
			callback: function () {
				checkbox.disabled = false;
				if (lbl) lbl.textContent = isAllowed ? 'Allowed' : 'Blocked';
				// Update local state
				var s = (S.students || []).find(function (x) { return x.student === student; });
				if (s) { s.is_allowed = !!isAllowed; s.override_reason = reason || ''; }
				// Update reason pill
				var wrapper = checkbox.closest('div[style]');
				if (wrapper) {
					var pill = wrapper.querySelector('.rx-reason-pill');
					if (!isAllowed && reason) {
						if (pill) { pill.textContent = reason; pill.title = reason; }
						else {
							pill = document.createElement('span');
							pill.className   = 'rx-reason-pill';
							pill.textContent = reason;
							pill.title       = reason;
							wrapper.appendChild(pill);
						}
					} else if (isAllowed && pill) {
						pill.remove();
					}
				}
				frappe.show_alert({
					message:   isAllowed ? 'Student allowed for re-exam.' : 'Student blocked from re-exam.',
					indicator: isAllowed ? 'green' : 'orange',
				}, 2);
			},
			error: function () {
				checkbox.disabled = false;
				checkbox.checked  = !checkbox.checked;
				if (lbl) lbl.textContent = checkbox.checked ? 'Allowed' : 'Blocked';
				frappe.show_alert({ message: 'Failed to update. Please try again.', indicator: 'red' }, 3);
			},
		});
	}

	// ── Export CSV ────────────────────────────────────────────────────────────
	$exportBtn.on('click', function () {
		if (!S.students || !S.students.length) return;
		var headers = ['#', 'Student Name', 'Registration ID', 'Programme', 'Batch Year', 'Grade', 'Total Marks', 'Re-Exam Allowed', 'Block Reason'];
		var rows = S.students.map(function (s, i) {
			return [
				i + 1,
				s.student_name    || '',
				s.registration_id || '',
				s.programme       || '',
				s.batch_year      || '',
				s.grade           || '',
				(s.total_marks !== null && s.total_marks !== undefined) ? parseFloat(s.total_marks).toFixed(2) : '',
				s.is_allowed !== false ? 'Yes' : 'No',
				s.override_reason || '',
			];
		});
		var csv = [headers].concat(rows).map(function (r) {
			return r.map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(',');
		}).join('\n');
		var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
		var url  = URL.createObjectURL(blob);
		var a    = document.createElement('a');
		a.href   = url;
		a.download = 'failed_students_' + (S.exam_plan || '') + '_' + (S.course || '') + '.csv';
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	});

	// ── Bulk apply settings — course picker dialog ───────────────────────────
	$bulkApplyBtn.on('click', function () {
		if (!S.exam_plan) {
			frappe.show_alert({ message: 'Select an Exam Plan first.', indicator: 'orange' });
			return;
		}
		var fee  = $feeInput.val() || '';
		var from = $dlFrom.val()   || '';
		var to   = $dlTo.val()     || '';

		// Fetch all courses for this exam plan, then show picker
		frappe.call({
			method: 'slcm.slcm.page.re_exam.re_exam.get_courses_for_exam_plan',
			args: { exam_plan: S.exam_plan },
			callback: function (r) {
				var courses = r.message || [];
				if (!courses.length) {
					frappe.show_alert({ message: 'No courses found for this Exam Plan.', indicator: 'orange' });
					return;
				}

				var checkboxHtml = courses.map(function (c) {
					var lbl = (c.course_name && c.course_name !== c.course)
						? frappe.utils.escape_html(c.course_name) + ' <span style="color:#94a3b8;font-size:11px;">(' + frappe.utils.escape_html(c.course) + ')</span>'
						: frappe.utils.escape_html(c.course);
					var isCurrentCourse = (c.course === S.course);
					return '<label style="display:flex;align-items:center;gap:10px;padding:7px 4px;cursor:pointer;border-bottom:1px solid #f1f5f9;' +
						(isCurrentCourse ? 'background:#FBEEF0;border-radius:6px;' : '') + '">' +
						'<input type="checkbox" class="rx-bc-cb" value="' + frappe.utils.escape_html(c.course) + '" checked ' +
						'style="width:15px;height:15px;cursor:pointer;accent-color:#920C24;">' +
						'<span style="font-size:13px;color:#1e293b;line-height:1.4;">' + lbl +
						(isCurrentCourse ? ' <span style="font-size:10px;background:#F5D9DE;color:#6E091B;border-radius:4px;padding:1px 5px;font-weight:700;margin-left:4px;">Current</span>' : '') +
						'</span></label>';
				}).join('');

				var feeLabel  = fee ? '₹' + parseFloat(fee).toLocaleString('en-IN') : '<span style="color:#94a3b8;">None</span>';
				var fromLabel = from || '<span style="color:#94a3b8;">—</span>';
				var toLabel   = to   || '<span style="color:#94a3b8;">—</span>';

				var d = new frappe.ui.Dialog({
					title: 'Apply Settings to Courses',
					fields: [
						{
							fieldname: 'summary_html',
							fieldtype: 'HTML',
							options: '<div style="background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:8px;padding:10px 14px;margin-bottom:4px;font-size:12.5px;color:#475569;display:flex;gap:16px;flex-wrap:wrap;">' +
								'<span>Fee: <b style="color:#0f172a;">' + feeLabel + '</b></span>' +
								'<span>Deadline: <b style="color:#0f172a;">' + fromLabel + '</b> → <b style="color:#0f172a;">' + toLabel + '</b></span>' +
								'</div>',
						},
						{
							fieldname: 'courses_html',
							fieldtype: 'HTML',
							options: '<div style="margin-top:10px;">' +
								'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">' +
									'<span style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.5px;">Select Courses (' + courses.length + ' total)</span>' +
									'<div style="display:flex;gap:12px;">' +
										'<button type="button" onclick="rxBulkSelectAll(true)" style="font-size:11px;color:#920C24;background:none;border:none;cursor:pointer;font-weight:700;padding:0;">Select All</button>' +
										'<button type="button" onclick="rxBulkSelectAll(false)" style="font-size:11px;color:#94a3b8;background:none;border:none;cursor:pointer;font-weight:700;padding:0;">Deselect All</button>' +
									'</div>' +
								'</div>' +
								'<div id="rx-bulk-courses" style="max-height:260px;overflow-y:auto;border:1.5px solid #e2e8f0;border-radius:8px;padding:4px 10px;">' +
									checkboxHtml +
								'</div>' +
								'<p style="font-size:11px;color:#94a3b8;margin-top:8px;">Existing settings for selected courses will be overwritten.</p>' +
							'</div>',
						},
					],
					primary_action_label: 'Apply to Selected',
					primary_action: function () {
						var checked = [];
						document.querySelectorAll('#rx-bulk-courses .rx-bc-cb:checked').forEach(function (cb) {
							checked.push(cb.value);
						});
						if (!checked.length) {
							frappe.show_alert({ message: 'Select at least one course.', indicator: 'orange' });
							return;
						}
						d.hide();
						frappe.call({
							method: 'slcm.slcm.page.re_exam.re_exam.bulk_save_re_exam_setting',
							args: {
								exam_plan:     S.exam_plan,
								re_exam_fee:   fee  || null,
								deadline_from: from || null,
								deadline_to:   to   || null,
								courses:       JSON.stringify(checked),
							},
							callback: function (r) {
								if (r.message) {
									frappe.show_alert({ message: 'Settings applied to ' + r.message.updated + ' course(s).', indicator: 'green' }, 3);
									$savedBadge.show();
									setTimeout(function () { $savedBadge.hide(); }, 2500);
									// Reload current course's settings if it was in the selection
									if (S.course && checked.indexOf(S.course) !== -1) {
										loadSettings();
									}
								}
							},
						});
					},
				});
				d.show();
			},
		});
	});

	// ── Helpers for bulk course picker ────────────────────────────────────────
	window.rxBulkSelectAll = function (checked) {
		document.querySelectorAll('#rx-bulk-courses .rx-bc-cb').forEach(function (cb) {
			cb.checked = checked;
		});
	};

	// ── Registered stat card drill-down dialog ───────────────────────────────
	window.rxScrollToRegistrations = function () {
		if (!S.exam_plan) {
			frappe.show_alert({ message: 'Select an Exam Plan first.', indicator: 'orange' }, 2);
			return;
		}

		// Build dialog with a loading placeholder
		var dlg = new frappe.ui.Dialog({
			title: 'Registered Students',
			fields: [{ fieldname: 'body_html', fieldtype: 'HTML', options: _rxRegLoadingHtml() }],
			size: 'extra-large',
		});
		dlg.show();

		// Fetch registrations — scoped to current course if one is selected, else all
		frappe.call({
			method: 'slcm.slcm.page.re_exam.re_exam.get_re_exam_registrations',
			args: { exam_plan: S.exam_plan, course: S.course || '' },
			callback: function (r) {
				var regs    = r.message || [];
				var showCourseCol = !S.course; // show course column only when viewing all
				dlg.fields_dict.body_html.$wrapper.html(_rxRegDialogHtml(regs, showCourseCol));
			},
		});
	};

	function _rxRegLoadingHtml() {
		return '<div style="padding:40px;text-align:center;color:#94a3b8;font-size:14px;">' +
			'<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2" style="display:block;margin:0 auto 10px;">' +
			'<path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>Loading…</div>';
	}

	function _rxRegDialogHtml(regs, showCourseCol) {
		if (!regs.length) {
			return '<div style="padding:40px;text-align:center;">' +
				'<div style="font-size:14px;font-weight:700;color:#94a3b8;">No registrations found</div>' +
				'<div style="font-size:12px;color:#cbd5e1;margin-top:4px;">Students will appear here once they register via the portal</div>' +
				'</div>';
		}

		var total = regs.length;
		var paid  = regs.filter(function (r) { return r.payment_status === 'Paid' || r.payment_status === 'Captured'; }).length;
		var AV    = ['av-0','av-1','av-2','av-3','av-4','av-5','av-6','av-7'];

		var legend = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">' +
			'<span style="font-size:13px;font-weight:700;color:#0f172a;">' + total + ' Registration' + (total !== 1 ? 's' : '') + '</span>' +
			'<span class="rx-st-badge rx-st-reg" style="font-size:10px;">' + (total - paid) + ' Pending</span>' +
			'<span class="rx-st-badge rx-st-paid" style="font-size:10px;">' + paid + ' Paid</span>' +
			'</div>';

		var courseHeader = showCourseCol
			? '<th style="min-width:160px;padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Course</th>'
			: '';

		var rows = regs.map(function (reg, i) {
			var initials = ((reg.student_name || '').split(' ')
				.map(function (w) { return w[0] || ''; }).join('').slice(0, 2)).toUpperCase() || '?';
			var avatar   = '<div class="rx-savatar ' + AV[i % 8] + '" style="width:32px;height:32px;font-size:11px;flex-shrink:0;">' +
				frappe.utils.escape_html(initials) + '</div>';
			var isPaid   = reg.payment_status === 'Paid' || reg.payment_status === 'Captured';
			var stClass  = isPaid ? 'rx-st-paid' : 'rx-st-reg';
			var receiptUrl = '/printview?doctype=Re%20Exam%20Registration&name=' + encodeURIComponent(reg.name) + '&format=Re%20Exam%20Receipt&trigger_print=0';
			var action   = !isPaid
				? '<button class="rx-pay-btn" onclick="rxMarkPaidDialog(\'' + frappe.utils.escape_html(reg.name) + '\',this)">Mark Paid</button>'
				: '<span style="display:flex;align-items:center;gap:6px;">' +
				  '<span style="font-size:11px;color:#10b981;font-weight:700;">✓ Paid</span>' +
				  '<a href="' + receiptUrl + '" target="_blank" title="Download Receipt" ' +
				  'style="font-size:11px;color:#920C24;text-decoration:underline;font-weight:600;">Receipt</a>' +
				  '</span>';
			var feeHtml  = reg.re_exam_fee
				? '₹' + parseFloat(reg.re_exam_fee).toLocaleString('en-IN')
				: '<span style="color:#94a3b8;font-size:11px;">Free</span>';
			var courseCell = showCourseCol
				? '<td style="font-size:12px;color:#1e293b;font-weight:500;padding:0 14px;border-bottom:1.5px solid #f1f5f9;height:58px;vertical-align:middle;">' +
				  frappe.utils.escape_html(reg.course_name || reg.course || '—') + '</td>'
				: '';

			return '<tr>' +
				'<td style="width:42px;text-align:center;font-size:11px;font-weight:700;color:#cbd5e1;background:#FDF8F9;border-right:1.5px solid #f1f5f9;border-bottom:1.5px solid #f1f5f9;height:58px;vertical-align:middle;">' + (i + 1) + '</td>' +
				'<td style="padding:0 14px;border-bottom:1.5px solid #f1f5f9;height:58px;vertical-align:middle;min-width:200px;">' +
					'<div style="display:flex;align-items:center;gap:10px;">' + avatar +
						'<div>' +
							'<div style="font-size:13px;font-weight:700;color:#0f172a;">' + frappe.utils.escape_html(reg.student_name || '—') + '</div>' +
						'</div>' +
					'</div>' +
				'</td>' +
				'<td style="font-size:12px;font-weight:600;color:#475569;padding:0 14px;border-bottom:1.5px solid #f1f5f9;height:58px;vertical-align:middle;width:130px;">' + frappe.utils.escape_html(reg.registration_id || '—') + '</td>' +
				courseCell +
				'<td style="padding:0 14px;border-bottom:1.5px solid #f1f5f9;height:58px;vertical-align:middle;width:110px;text-align:center;">' +
					'<span class="rx-st-badge ' + stClass + '">' + frappe.utils.escape_html(reg.payment_status || reg.status) + '</span>' +
				'</td>' +
				'<td style="font-size:13px;font-weight:600;color:#0f172a;padding:0 14px;border-bottom:1.5px solid #f1f5f9;height:58px;vertical-align:middle;width:90px;">' + feeHtml + '</td>' +
				'<td style="font-size:12px;color:#64748b;padding:0 14px;border-bottom:1.5px solid #f1f5f9;height:58px;vertical-align:middle;width:150px;">' + frappe.utils.escape_html(reg.payment_reference || '—') + '</td>' +
				'<td style="padding:0 14px;border-bottom:1.5px solid #f1f5f9;height:58px;vertical-align:middle;width:110px;text-align:center;">' + action + '</td>' +
			'</tr>';
		}).join('');

		return legend +
			'<div style="overflow-x:auto;border-radius:10px;border:1.5px solid #e2e8f0;">' +
			'<table style="width:100%;border-collapse:collapse;font-size:13px;">' +
				'<thead><tr style="background:#f8fafc;">' +
					'<th style="width:42px;padding:10px 14px;text-align:center;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;">#</th>' +
					'<th style="min-width:200px;padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Student</th>' +
					'<th style="width:130px;padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Reg. ID</th>' +
					courseHeader +
					'<th style="width:110px;padding:10px 14px;text-align:center;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Status</th>' +
					'<th style="width:90px;padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Fee</th>' +
					'<th style="width:150px;padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Payment Ref</th>' +
					'<th style="width:110px;padding:10px 14px;text-align:center;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Action</th>' +
				'</tr></thead>' +
				'<tbody>' + rows + '</tbody>' +
			'</table></div>';
	}

	// Mark paid from inside the dialog
	window.rxMarkPaidDialog = function (registrationName, btn) {
		frappe.prompt(
			[{
				fieldname:   'payment_reference',
				fieldtype:   'Data',
				label:       'Payment Reference',
				description: 'Enter receipt / challan number (optional)',
			}],
			function (vals) {
				frappe.call({
					method: 'slcm.slcm.page.re_exam.re_exam.mark_re_exam_paid',
					args: { registration_name: registrationName, payment_reference: vals.payment_reference || '' },
					callback: function (r) {
						if (r.message && r.message.ok) {
							frappe.show_alert({ message: 'Marked as Paid.', indicator: 'green' }, 2);
							// Update the row in-place inside the dialog
							var td = btn.closest('td');
							if (td) {
								td.innerHTML = '<span style="font-size:11px;color:#10b981;font-weight:700;">✓ Paid</span>';
								var statusTd = td.closest('tr').querySelector('.rx-st-reg');
								if (statusTd) {
									statusTd.className = 'rx-st-badge rx-st-paid';
									statusTd.textContent = 'Paid';
								}
							}
							loadStats();
						}
					},
				});
			},
			'Mark Registration as Paid',
			'Confirm'
		);
	};

	// ── Source selection ──────────────────────────────────────────────────────
	window.rxSetSource = function (val) {
		S.source = val;
		$body.find('#rx-src-' + val).prop('checked', true);
		$body.find('.rx-source-opt').removeClass('rx-source-opt-active');
		$body.find('#rx-src-' + val + '-lbl').addClass('rx-source-opt-active');

		if (val === 'manual') {
			$uploadPanel.show();
			// Reset DB-fetched data; keep uploaded data if any
			S.students = S.uploaded_students.slice();
			if (!S.uploaded_students.length) {
				showPlaceholder('Upload a CSV file', 'Download the sample template, fill in student details, then upload');
				$exportBtn.hide();
			} else {
				renderTable(S.uploaded_students);
			}
			$statCards.hide();
		} else {
			$uploadPanel.hide();
			if (S.exam_plan) {
				loadStats();
				loadStudents();
			}
		}
	};

	// ── Download sample template ──────────────────────────────────────────────
	$body.find('#rx-dl-template').on('click', function () {
		var headers = ['Registration ID', 'Student Name', 'Programme', 'Batch Year', 'Grade', 'Total Marks'];
		var sample  = [
			['REG001', 'John Doe',   'BA LLB (Hons)', '2023', 'F', '32.50'],
			['REG002', 'Jane Smith', 'BA LLB (Hons)', '2023', 'F', '28.00'],
		];
		var csv  = [headers].concat(sample).map(function (r) {
			return r.map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(',');
		}).join('\n');
		var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
		var url  = URL.createObjectURL(blob);
		var a    = document.createElement('a');
		a.href      = url;
		a.download  = 're_exam_student_template.csv';
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	});

	// ── CSV upload — drag / drop / browse ─────────────────────────────────────
	$dropZone.on('click', function () {
		document.getElementById('rx-csv-input').click();
	});

	$dropZone.on('dragover', function (e) {
		e.preventDefault();
		$(this).addClass('rx-drag-over');
	});

	$dropZone.on('dragleave', function () {
		$(this).removeClass('rx-drag-over');
	});

	$dropZone.on('drop', function (e) {
		e.preventDefault();
		$(this).removeClass('rx-drag-over');
		var files = e.originalEvent.dataTransfer.files;
		if (files && files[0]) rxHandleCsvFile(files[0]);
	});

	$csvInput.on('change', function () {
		if (this.files && this.files[0]) rxHandleCsvFile(this.files[0]);
		this.value = '';
	});

	$body.find('#rx-upload-clear').on('click', function () {
		S.uploaded_students = [];
		S.students          = [];
		$uploadStatus.hide();
		showPlaceholder('Upload a CSV file', 'Download the sample template, fill in student details, then upload');
		$exportBtn.hide();
	});

	function rxHandleCsvFile(file) {
		if (!file.name.toLowerCase().endsWith('.csv')) {
			frappe.show_alert({ message: 'Please upload a .csv file.', indicator: 'red' }, 3);
			return;
		}
		var reader    = new FileReader();
		reader.onload = function (e) {
			var parsed = rxParseCsv(e.target.result);
			if (!parsed.students.length) {
				frappe.show_alert({
					message:   'No valid rows found in the CSV. Check the column headers match the template.',
					indicator: 'orange',
				}, 5);
				return;
			}
			S.uploaded_students  = parsed.students;
			S.students           = parsed.students;
			S.all_grades_fallback = false;
			$uploadFilename.text(file.name + ' — ' + parsed.students.length + ' student(s) loaded');
			$uploadStatus.css('display', 'flex');
			renderTable(parsed.students);
			frappe.show_alert({ message: parsed.students.length + ' students loaded from CSV.', indicator: 'green' }, 3);
		};
		reader.readAsText(file);
	}

	function rxParseCsv(text) {
		var lines = text.split(/\r?\n/).filter(function (l) { return l.trim(); });
		if (!lines.length) return { students: [] };

		var hdr    = rxParseCsvRow(lines[0]).map(function (h) {
			return h.trim().toLowerCase().replace(/[\s._-]+/g, '_');
		});
		var idx = {
			reg:   Math.max(hdr.indexOf('registration_id'), hdr.indexOf('reg_id'), hdr.indexOf('reg')),
			name:  Math.max(hdr.indexOf('student_name'), hdr.indexOf('name')),
			prog:  Math.max(hdr.indexOf('programme'), hdr.indexOf('program')),
			batch: Math.max(hdr.indexOf('batch_year'), hdr.indexOf('batch')),
			grade: hdr.indexOf('grade'),
			marks: Math.max(hdr.indexOf('total_marks'), hdr.indexOf('marks'), hdr.indexOf('total')),
		};

		var students = [];
		for (var i = 1; i < lines.length; i++) {
			var cols = rxParseCsvRow(lines[i]);
			if (!cols.length || cols.every(function (c) { return !c.trim(); })) continue;
			var s = {
				student:         null,
				registration_id: idx.reg   >= 0 ? (cols[idx.reg]   || '').trim() : '',
				student_name:    idx.name  >= 0 ? (cols[idx.name]  || '').trim() : '',
				programme:       idx.prog  >= 0 ? (cols[idx.prog]  || '').trim() : '',
				batch_year:      idx.batch >= 0 ? (cols[idx.batch] || '').trim() : '',
				grade:           idx.grade >= 0 ? (cols[idx.grade] || '').trim() : '',
				total_marks:     idx.marks >= 0 ? (cols[idx.marks] || '').trim() : '',
				is_allowed:      true,
				override_reason: '',
				image:           null,
				email:           '',
			};
			if (s.registration_id || s.student_name) students.push(s);
		}
		return { students: students };
	}

	function rxParseCsvRow(line) {
		var result = [], curr = '', inQ = false;
		for (var i = 0; i < line.length; i++) {
			var ch = line[i];
			if (inQ) {
				if (ch === '"') {
					if (line[i + 1] === '"') { curr += '"'; i++; }
					else inQ = false;
				} else {
					curr += ch;
				}
			} else {
				if (ch === '"')      { inQ = true; }
				else if (ch === ',') { result.push(curr); curr = ''; }
				else                 { curr += ch; }
			}
		}
		result.push(curr);
		return result;
	}

};

