frappe.pages['result-settings'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Result Settings',
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
	if (!document.getElementById('rs-style')) {
		var style = document.createElement('style');
		style.id  = 'rs-style';
		style.textContent = `
		/* ── Layout ── */
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

		/* ── Plan selector ── */
		.rs-plan-card  { background:#fff; border-radius:12px; padding:14px 20px; margin-bottom:16px;
		                 box-shadow:0 1px 3px rgba(0,0,0,.06); display:flex; align-items:flex-end; gap:14px; flex-wrap:wrap; }
		.rs-fgroup     { display:flex; flex-direction:column; min-width:240px; flex:1; max-width:360px; }
		.rs-flabel     { font-size:11px; color:#94a3b8; font-weight:700; margin-bottom:5px;
		                 text-transform:uppercase; letter-spacing:.6px; }
		.rs-select     { height:36px; border:1.5px solid #e2e8f0; border-radius:8px;
		                 padding:0 12px; font-size:13px; background:#fff; color:#1e293b;
		                 outline:none; cursor:pointer; transition:border-color .2s; }
		.rs-select:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }

		/* ── Sub-tab bar ── */
		.rs-subtab-bar { display:flex; align-items:center; border-bottom:2px solid #e2e8f0;
		                 margin-bottom:20px; gap:0; overflow-x:auto; }
		.rs-subtab     { padding:10px 20px; font-size:13px; font-weight:600; color:#64748b;
		                 border-bottom:2px solid transparent; margin-bottom:-2px; cursor:pointer;
		                 white-space:nowrap; transition:all .18s; user-select:none; }
		.rs-subtab:hover  { color:#1e293b; }
		.rs-subtab.active { color:#920C24; border-bottom-color:#920C24; }

		/* ── Generic buttons ── */
		.rs-btn        { height:34px; padding:0 18px; border-radius:7px; border:1.5px solid #e2e8f0;
		                 background:#fff; cursor:pointer; font-size:13px; font-weight:600;
		                 color:#475569; transition:all .15s; white-space:nowrap; }
		.rs-btn:hover  { background:#f8fafc; border-color:#cbd5e1; color:#1e293b; }
		.rs-btn.primary{ background:#920C24;
		                 border-color:transparent; color:#fff; }
		.rs-btn.primary:hover { opacity:.9; }
		.rs-btn.danger { background:#920C24;
		                 border-color:transparent; color:#fff; }
		.rs-btn.danger:hover { opacity:.9; }
		.rs-btn:disabled { opacity:.5; cursor:default; }
		.rs-icon-btn   { width:30px; height:30px; border-radius:7px; border:1.5px solid #e2e8f0;
		                 background:#fff; cursor:pointer; display:inline-flex; align-items:center;
		                 justify-content:center; color:#64748b; transition:all .15s; flex-shrink:0; }
		.rs-icon-btn:hover { background:#FBEEF0; border-color:#E8B4BE; color:#920C24; }

		/* ── Publish section cards ── */
		.rs-section     { background:#fff; border-radius:12px; padding:24px 28px;
		                  box-shadow:0 1px 3px rgba(0,0,0,.06); margin-bottom:16px; }
		.rs-sec-title   { font-size:14px; font-weight:800; color:#0f172a; margin-bottom:18px;
		                  padding-bottom:12px; border-bottom:1.5px solid #f1f5f9; }
		.rs-content-hdr { display:flex; align-items:center; justify-content:flex-end;
		                  gap:8px; margin-bottom:16px; }

		/* ── Component tags (Publish tab) ── */
		.rs-tags-wrap { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
		.rs-tag       { display:inline-flex; align-items:center; gap:6px; padding:5px 10px 5px 12px;
		                border-radius:20px; font-size:12.5px; font-weight:700; color:#fff; }
		.rs-tag-x     { width:16px; height:16px; border-radius:50%; background:rgba(255,255,255,.25);
		                display:inline-flex; align-items:center; justify-content:center;
		                cursor:pointer; font-size:10px; line-height:1; transition:background .15s; }
		.rs-tag-x:hover { background:rgba(255,255,255,.45); }
		.rs-add-wrap  { position:relative; display:inline-block; }
		.rs-add-btn   { display:inline-flex; align-items:center; gap:6px; padding:5px 14px;
		                border-radius:20px; border:1.5px dashed #cbd5e1; background:#fff;
		                cursor:pointer; font-size:12.5px; font-weight:600; color:#64748b;
		                transition:all .15s; }
		.rs-add-btn:hover { border-color:#920C24; color:#6E091B; background:#FBEEF0; }
		.rs-add-dd    { display:none; position:absolute; top:calc(100% + 6px); left:0; z-index:999;
		                background:#fff; border:1.5px solid #e2e8f0; border-radius:10px;
		                box-shadow:0 8px 24px rgba(0,0,0,.12); min-width:200px; padding:5px; }
		.rs-add-wrap.open .rs-add-dd { display:block; }
		.rs-add-item  { padding:8px 12px; font-size:12.5px; cursor:pointer; color:#475569;
		                border-radius:7px; font-weight:500; transition:background .12s; }
		.rs-add-item:hover { background:#f1f5f9; color:#1e293b; }
		.rs-add-none  { padding:10px 12px; font-size:12px; color:#94a3b8; }

		/* ── Setting rows (Publish tab) ── */
		.rs-setting-row  { display:flex; align-items:center; gap:16px; padding:14px 0;
		                   border-bottom:1.5px solid #f8fafc; }
		.rs-setting-row:last-child  { border-bottom:none; padding-bottom:0; }
		.rs-setting-row:first-child { padding-top:0; }
		.rs-setting-lbl  { flex:1; font-size:13.5px; color:#1e293b; font-weight:500; }
		.rs-setting-ctrl { display:flex; align-items:center; gap:12px; flex-shrink:0; }
		.rs-toggle       { position:relative; display:inline-block; width:44px; height:24px;
		                   cursor:pointer; flex-shrink:0; }
		.rs-toggle input { opacity:0; width:0; height:0; position:absolute; }
		.rs-toggle-sl    { position:absolute; inset:0; background:#cbd5e1; border-radius:24px;
		                   transition:background .2s; }
		.rs-toggle-sl:before { content:''; position:absolute; width:18px; height:18px;
		                       left:3px; bottom:3px; background:#fff; border-radius:50%;
		                       transition:transform .2s; box-shadow:0 1px 3px rgba(0,0,0,.2); }
		.rs-toggle input:checked + .rs-toggle-sl { background:#920C24; }
		.rs-toggle input:checked + .rs-toggle-sl:before { transform:translateX(20px); }
		.rs-inline-chk   { display:flex; align-items:center; gap:6px; font-size:12.5px;
		                   color:#475569; font-weight:500; cursor:pointer; user-select:none; }
		.rs-inline-chk input { width:15px; height:15px; accent-color:#920C24; cursor:pointer; flex-shrink:0; }

		/* ── Access Results table ── */
		.rs-ar-toolbar { display:flex; align-items:center; gap:10px; margin-bottom:12px; flex-wrap:wrap; }
		.rs-ar-search  { flex:1; min-width:200px; max-width:320px; position:relative; }
		.rs-ar-search input { width:100%; height:34px; border:1.5px solid #e2e8f0; border-radius:8px;
		                      padding:0 10px 0 34px; font-size:13px; outline:none; color:#1e293b;
		                      background:#fff; transition:border-color .2s; box-sizing:border-box; }
		.rs-ar-search input:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }
		.rs-ar-search-ico { position:absolute; left:9px; top:9px; color:#94a3b8; pointer-events:none; }
		.rs-ar-count   { font-size:13px; font-weight:700; color:#0f172a; margin-right:auto; }

		.rs-ar-card    { background:#fff; border-radius:12px; box-shadow:0 1px 3px rgba(0,0,0,.06);
		                 overflow:hidden; }
		.rs-ar-scroll  { overflow-x:auto; }
		.rs-ar-tbl     { width:100%; border-collapse:collapse; font-size:13px; min-width:980px; }
		.rs-ar-tbl thead tr { background:#f8fafc; }
		.rs-ar-tbl th  { padding:10px 14px; text-align:left; font-size:11px; font-weight:700;
		                 color:#475569; border-bottom:1.5px solid #e2e8f0; white-space:nowrap;
		                 text-transform:uppercase; letter-spacing:.4px; }
		.rs-ar-tbl th.center { text-align:center; }
		.rs-ar-tbl td  { padding:12px 14px; border-bottom:1.5px solid #f1f5f9;
		                 vertical-align:middle; white-space:nowrap; }
		.rs-ar-tbl tbody tr:hover td { background:#FDF8F9; }
		.rs-ar-tbl tbody tr:last-child td { border-bottom:none; }
		.rs-ar-tbl tbody tr.rs-ar-saving td { opacity:.6; pointer-events:none; }

		/* course name cell */
		.rs-cname      { font-size:13px; font-weight:700; color:#0f172a; }
		.rs-ccode      { display:inline-block; margin-top:3px; font-size:11px; font-weight:700;
		                 color:#920C24; background:#FBEEF0; border-radius:4px; padding:1px 6px; }

		/* status pill */
		.rs-status-pill { display:inline-flex; align-items:center; gap:5px; padding:4px 10px;
		                  border-radius:20px; font-size:11.5px; font-weight:700; cursor:pointer;
		                  transition:all .15s; user-select:none; border:none; }
		.rs-status-pill.unlocked { background:#d1fae5; color:#065f46; }
		.rs-status-pill.unlocked:hover { background:#a7f3d0; }
		.rs-status-pill.locked   { background:#F5D9DE; color:#6E091B; }
		.rs-status-pill.locked:hover { background:#E8B4BE; }

		/* small toggle (inline table) */
		.rs-sm-toggle  { position:relative; display:inline-block; width:38px; height:20px; cursor:pointer; }
		.rs-sm-toggle input { opacity:0; width:0; height:0; position:absolute; }
		.rs-sm-toggle-sl { position:absolute; inset:0; background:#cbd5e1; border-radius:20px; transition:background .2s; }
		.rs-sm-toggle-sl:before { content:''; position:absolute; width:15px; height:15px;
		                          left:2.5px; bottom:2.5px; background:#fff; border-radius:50%;
		                          transition:transform .2s; box-shadow:0 1px 2px rgba(0,0,0,.2); }
		.rs-sm-toggle input:checked + .rs-sm-toggle-sl { background:#920C24; }
		.rs-sm-toggle input:checked + .rs-sm-toggle-sl:before { transform:translateX(18px); }

		/* deadline input */
		.rs-deadline   { height:28px; border:1.5px solid #e2e8f0; border-radius:6px; padding:0 8px;
		                 font-size:12px; color:#1e293b; outline:none; background:#fff;
		                 transition:border-color .18s; max-width:160px; }
		.rs-deadline:focus { border-color:#920C24; }
		.rs-deadline.rs-dirty { border-color:#920C24; background:#FBEEF0; }

		/* grade access mini-badges */
		.rs-ga-wrap    { display:flex; gap:3px; flex-wrap:wrap; min-width:110px; }
		.rs-ga-chip    { display:inline-flex; padding:2px 6px; border-radius:4px; font-size:10px;
		                 font-weight:800; letter-spacing:.3px; }
		.rs-ga-chip.on  { background:#F5D9DE; color:#6E091B; }
		.rs-ga-chip.off { background:#f1f5f9; color:#cbd5e1; }

		/* empty state */
		.rs-empty      { padding:64px 20px; display:flex; flex-direction:column;
		                 align-items:center; justify-content:center; text-align:center; }
		.rs-empty-icon { width:52px; height:52px; border-radius:12px; background:#f1f5f9;
		                 display:flex; align-items:center; justify-content:center; margin-bottom:12px; }
		.rs-empty-txt  { font-size:14px; font-weight:700; color:#94a3b8; }
		.rs-empty-sub  { font-size:12px; color:#cbd5e1; margin-top:4px; }

		/* loading */
		.rs-loading    { padding:48px; text-align:center; color:#94a3b8; font-size:13px; }
		@keyframes rs-spin { to { transform:rotate(360deg); } }
		.rs-spin       { animation:rs-spin 1s linear infinite; display:inline-block; vertical-align:-6px; margin-right:6px; }

		/* dirty row indicator */
		.rs-row-dirty  { background:linear-gradient(90deg,rgba(146,12,36,.07) 0, transparent 6px) !important; }
		.rs-row-dirty td:first-child { border-left:3px solid #920C24; }

		/* ── Configure Modal ── */
		.rs-modal-overlay { position:fixed; inset:0; background:rgba(15,23,42,.35);
		                    z-index:10000; display:flex; align-items:center; justify-content:center;
		                    backdrop-filter:blur(2px); }
		.rs-modal      { background:#fff; border-radius:16px; width:680px; max-width:96vw;
		                 max-height:88vh; display:flex; flex-direction:column;
		                 box-shadow:0 20px 60px rgba(0,0,0,.18); overflow:hidden; }
		.rs-modal-hdr  { display:flex; align-items:center; justify-content:space-between;
		                 padding:18px 22px 14px; border-bottom:1.5px solid #f1f5f9; flex-shrink:0; }
		.rs-modal-title { font-size:15px; font-weight:800; color:#0f172a; }
		.rs-modal-sub  { font-size:12px; color:#94a3b8; margin-top:2px; }
		.rs-modal-close { width:28px; height:28px; border-radius:7px; border:none; background:#f1f5f9;
		                  cursor:pointer; display:flex; align-items:center; justify-content:center;
		                  color:#64748b; font-size:15px; transition:all .15s; flex-shrink:0; }
		.rs-modal-close:hover { background:#F5D9DE; color:#920C24; }
		.rs-modal-body { flex:1; overflow-y:auto; padding:18px 22px; }
		.rs-modal-ftr  { display:flex; align-items:center; justify-content:flex-end; gap:8px;
		                 padding:14px 22px; border-top:1.5px solid #f1f5f9; flex-shrink:0;
		                 background:#FDF8F9; }

		/* modal sections */
		.rs-msec       { margin-bottom:22px; }
		.rs-msec:last-child { margin-bottom:0; }
		.rs-msec-title { font-size:12px; font-weight:800; color:#475569; text-transform:uppercase;
		                 letter-spacing:.5px; margin-bottom:12px; padding-bottom:8px;
		                 border-bottom:1.5px solid #f1f5f9; }
		.rs-chk-grid   { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
		.rs-chk-row    { display:flex; align-items:flex-start; gap:8px; padding:8px 10px;
		                 border-radius:8px; transition:background .12s; cursor:pointer; }
		.rs-chk-row:hover { background:#f8fafc; }
		.rs-chk-row input { width:15px; height:15px; accent-color:#920C24; cursor:pointer;
		                    flex-shrink:0; margin-top:1px; }
		.rs-chk-row-lbl { font-size:12.5px; color:#334155; font-weight:500; line-height:1.4; }

		/* evaluator table in modal */
		.rs-ev-tbl     { width:100%; border-collapse:collapse; }
		.rs-ev-tbl td  { padding:4px 6px; vertical-align:middle; }
		.rs-ev-sel     { height:30px; border:1.5px solid #e2e8f0; border-radius:6px; padding:0 8px;
		                 font-size:12.5px; color:#1e293b; outline:none; background:#fff;
		                 transition:border-color .15s; width:100%; }
		.rs-ev-sel:focus { border-color:#920C24; }
		.rs-ev-inp     { height:30px; border:1.5px solid #e2e8f0; border-radius:6px; padding:0 8px;
		                 font-size:12.5px; color:#1e293b; outline:none; background:#fff;
		                 transition:border-color .15s; width:100%; box-sizing:border-box; }
		.rs-ev-inp:focus { border-color:#920C24; }
		.rs-ev-del     { width:24px; height:24px; border-radius:5px; border:none; background:#F5D9DE;
		                 cursor:pointer; color:#920C24; font-size:13px; display:flex;
		                 align-items:center; justify-content:center; flex-shrink:0; transition:background .12s; }
		.rs-ev-del:hover { background:#E8B4BE; }
		.rs-add-row-btn { display:inline-flex; align-items:center; gap:5px; margin-top:8px;
		                  padding:5px 12px; border-radius:6px; border:1.5px dashed #cbd5e1;
		                  background:#fff; cursor:pointer; font-size:12px; font-weight:600;
		                  color:#64748b; transition:all .15s; }
		.rs-add-row-btn:hover { border-color:#920C24; color:#920C24; background:#FBEEF0; }

		/* faculty autocomplete */
		.rs-ac-wrap    { position:relative; width:100%; }
		.rs-ac-dd      { display:none; position:absolute; top:calc(100% + 2px); left:0; right:0;
		                 z-index:1000; background:#fff; border:1.5px solid #e2e8f0; border-radius:8px;
		                 box-shadow:0 6px 20px rgba(0,0,0,.1); max-height:180px; overflow-y:auto; }
		.rs-ac-wrap.open .rs-ac-dd { display:block; }
		.rs-ac-opt     { padding:8px 12px; font-size:12.5px; cursor:pointer; color:#334155;
		                 transition:background .1s; }
		.rs-ac-opt:hover { background:#FBEEF0; color:#920C24; }

		/* visible exams checkboxes */
		.rs-ve-grid    { display:flex; flex-wrap:wrap; gap:6px; }
		.rs-ve-chip    { display:inline-flex; align-items:center; gap:5px; padding:5px 10px;
		                 border-radius:8px; border:1.5px solid #e2e8f0; font-size:12.5px;
		                 font-weight:500; color:#475569; cursor:pointer; transition:all .15s;
		                 user-select:none; }
		.rs-ve-chip:hover { border-color:#920C24; color:#920C24; }
		.rs-ve-chip.selected { border-color:#920C24; background:#FBEEF0; color:#920C24; font-weight:700; }
		.rs-ve-chip input { width:13px; height:13px; accent-color:#920C24; cursor:pointer; }

		/* ── Coming soon ── */
		.rs-coming-card  { background:#fff; border-radius:16px; padding:60px 40px;
		                   box-shadow:0 1px 3px rgba(0,0,0,.06); display:flex;
		                   flex-direction:column; align-items:center; text-align:center; }
		.rs-coming-icon  { width:72px; height:72px; border-radius:18px; display:flex;
		                   align-items:center; justify-content:center; margin-bottom:16px; }
		.rs-coming-title { font-size:18px; font-weight:800; color:#0f172a; margin-bottom:8px; }
		.rs-coming-desc  { font-size:13px; color:#64748b; max-width:380px; line-height:1.6; }
		.rs-coming-badge { display:inline-flex; align-items:center; gap:6px; margin-top:18px;
		                   background:#f1f5f9; border:1.5px solid #e2e8f0; border-radius:20px;
		                   padding:6px 14px; font-size:12px; font-weight:700; color:#64748b; }
		`;
		document.head.appendChild(style);
	}

	// ── State ─────────────────────────────────────────────────────────────────
	var S = {
		exam_plan:        null,
		// Publish tab
		all_components:   [],
		components:       [],
		pub_settings: {
			show_total_marks: 0, show_sgpa: 0, hide_sgpa_for_failed: 0,
			show_egradesheet: 0, no_publish_unpaid: 0, no_publish_no_feedback: 0,
		},
		// Access Results tab
		access_settings:  [],   // [{course, course_name, course_code, status, ...}]
		ar_search:        '',
		ar_dirty:         {},   // {course_id: true} dirty tracking
		ar_saving:        false,
		// Shared
		active_subtab:    'publish',
		exam_types:       [],   // Exam Assessment Types for visible exams
	};

	// ── Shell HTML ────────────────────────────────────────────────────────────
	var $body = $(page.main);
	$body.html(`
		<div class="er2-wrap" style="padding:20px 24px;">
			<div class="er2-page-header">
				<div class="er2-page-icon" style="background:#920C24;">
					<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2">
						<circle cx="12" cy="12" r="3"/>
						<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
					</svg>
				</div>
				<div>
					<div class="er2-page-title">Result Settings</div>
					<div class="er2-page-sub">Configure access rules, grading schemas, and result display preferences</div>
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
				<button class="er2-pnav-btn active">
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
			<div class="rs-plan-card">
				<div class="rs-fgroup">
					<span class="rs-flabel">
						<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/></svg>
						Exam Plan
					</span>
					<select class="rs-select" id="rs-exam-plan">
						<option value="">Choose Exam Plan</option>
					</select>
				</div>
			</div>
			<div id="rs-content" style="display:none;">
				<div class="rs-subtab-bar">
					<div class="rs-subtab active" data-tab="access_results">Access Results</div>
					<div class="rs-subtab" data-tab="publish">Publish</div>
				</div>
				<div id="rs-tab-panel"></div>
			</div>
		</div>
	`);

	// ── DOM refs ──────────────────────────────────────────────────────────────
	var $examPlan = $body.find('#rs-exam-plan');
	var $content  = $body.find('#rs-content');
	var $tabPanel = $body.find('#rs-tab-panel');

	// default active tab in state matches the DOM
	S.active_subtab = 'access_results';

	// ── Boot: load exam plans + exam components + assessment types ────────────
	frappe.call({
		method: 'slcm.slcm.page.result_settings.result_settings.get_exam_plans',
		callback: function (r) {
			(r.message || []).forEach(function (ep) {
				$examPlan.append('<option value="' + ep.name + '">' +
					frappe.utils.escape_html(ep.exam_name || ep.name) +
					(ep.status === 'Active' ? ' [Active]' : '') + '</option>');
			});
		},
	});

	frappe.call({
		method: 'slcm.slcm.page.result_settings.result_settings.get_exam_components',
		callback: function (r) { S.all_components = r.message || []; },
	});

	frappe.call({
		method: 'slcm.slcm.page.result_settings.result_settings.get_exam_assessment_types',
		callback: function (r) { S.exam_types = r.message || []; },
	});

	// ── Exam Plan change ──────────────────────────────────────────────────────
	$examPlan.on('change', function () {
		S.exam_plan  = $(this).val();
		S.ar_dirty   = {};
		S.ar_search  = '';
		if (!S.exam_plan) { $content.hide(); return; }
		$content.show();
		loadForCurrentTab();
	});

	// ── Sub-tab switch ────────────────────────────────────────────────────────
	$body.on('click', '.rs-subtab', function () {
		var tab = $(this).data('tab');
		if (tab === S.active_subtab) return;
		S.active_subtab = tab;
		$body.find('.rs-subtab').removeClass('active');
		$(this).addClass('active');
		if (S.exam_plan) loadForCurrentTab();
	});

	// ── Dispatch loader ───────────────────────────────────────────────────────
	function loadForCurrentTab() {
		if      (S.active_subtab === 'access_results') loadAccessSettings();
		else if (S.active_subtab === 'publish')        loadPublishSetting();
	}

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
				// The endpoint streams the Excel file directly as an attachment
				// response, so it must be hit via a plain GET, not frappe.call.
				var url = '/api/method/slcm.slcm.page.term_result.term_result.download_consolidated_report?' + $.param(args);
				window.open(url, '_blank');
				d.hide();
			}
		});
		d.show();
	});

	// ══════════════════════════════════════════════════════════════════════════
	//  ACCESS RESULTS TAB
	// ══════════════════════════════════════════════════════════════════════════

	function loadAccessSettings() {
		$tabPanel.html(loadingHtml('Loading course access settings…'));
		S.ar_dirty = {};
		frappe.call({
			method: 'slcm.slcm.page.result_settings.result_settings.get_access_settings',
			args:   { exam_plan: S.exam_plan },
			callback: function (r) {
				S.access_settings = r.message || [];
				renderAccessResultsTab();
			},
			error: function () {
				$tabPanel.html('<div class="rs-empty"><div class="rs-empty-icon">⚠</div>' +
					'<div class="rs-empty-txt">Failed to load settings</div></div>');
			},
		});
	}

	function renderAccessResultsTab() {
		var dirty_count = Object.keys(S.ar_dirty).length;
		$tabPanel.html(`
			<div>
				<div class="rs-ar-toolbar">
					<div class="rs-ar-search">
						<svg class="rs-ar-search-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
						<input type="text" id="rs-ar-search-inp" placeholder="Search course…" value="${frappe.utils.escape_html(S.ar_search)}">
					</div>
					<span class="rs-ar-count" id="rs-ar-count"></span>
					<button class="rs-btn" id="rs-ar-cancel" ${dirty_count ? '' : 'disabled'}>Cancel</button>
					<button class="rs-btn primary" id="rs-ar-save" ${dirty_count ? '' : 'disabled'}>
						Save${dirty_count ? ' (' + dirty_count + ')' : ''}
					</button>
				</div>
				<div class="rs-ar-card">
					<div class="rs-ar-scroll">
						<table class="rs-ar-tbl">
							<thead>
								<tr>
									<th style="min-width:220px;">Course</th>
									<th style="min-width:110px;">Status</th>
									<th class="center" style="min-width:90px;">View Access</th>
									<th style="min-width:170px;">View Deadline</th>
									<th class="center" style="min-width:90px;">Edit Access</th>
									<th style="min-width:170px;">Edit Deadline</th>
									<th style="min-width:130px;">Grade Access</th>
									<th class="center" style="width:60px;">Config</th>
								</tr>
							</thead>
							<tbody id="rs-ar-tbody"></tbody>
						</table>
					</div>
				</div>
			</div>
		`);

		renderAccessRows();

		// Search
		$tabPanel.find('#rs-ar-search-inp').on('input', function () {
			S.ar_search = $(this).val().trim().toLowerCase();
			renderAccessRows();
		});

		// Cancel
		$tabPanel.find('#rs-ar-cancel').on('click', function () {
			loadAccessSettings();
		});

		// Save All
		$tabPanel.find('#rs-ar-save').on('click', function () {
			if (S.ar_saving) return;
			saveAllDirtyRows();
		});
	}

	function renderAccessRows() {
		var rows = S.access_settings.filter(function (r) {
			if (!S.ar_search) return true;
			return (r.course_name || '').toLowerCase().includes(S.ar_search) ||
			       (r.course_code || '').toLowerCase().includes(S.ar_search) ||
			       (r.course      || '').toLowerCase().includes(S.ar_search);
		});

		$tabPanel.find('#rs-ar-count').text('Courses (' + rows.length + ')');

		var $tbody = $tabPanel.find('#rs-ar-tbody');
		if (!rows.length) {
			$tbody.html('<tr><td colspan="8"><div class="rs-empty">' +
				'<div class="rs-empty-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg></div>' +
				'<div class="rs-empty-txt">No courses found</div>' +
				'<div class="rs-empty-sub">' + (S.ar_search ? 'Try a different search term' : 'No student course marks found for this exam plan') + '</div>' +
				'</div></td></tr>');
			return;
		}

		var html = '';
		rows.forEach(function (r) {
			var isDirty    = !!S.ar_dirty[r.course];
			var isLocked   = r.status === 'LOCKED';
			var statusCls  = isLocked ? 'locked' : 'unlocked';
			var statusIcon = isLocked
				? '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
				: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>';

			var deadlineVal = function (v) { return v ? v.substring(0, 16) : ''; };
			var gaChips     = buildGaChips(r);

			html += `<tr class="${isDirty ? 'rs-row-dirty' : ''}" data-course="${frappe.utils.escape_html(r.course)}">
				<td>
					<div class="rs-cname">${frappe.utils.escape_html(r.course_name || r.course)}</div>
					${r.course_code ? '<span class="rs-ccode">' + frappe.utils.escape_html(r.course_code) + '</span>' : ''}
				</td>
				<td>
					<button class="rs-status-pill ${statusCls}" data-course="${frappe.utils.escape_html(r.course)}">
						${statusIcon} ${isLocked ? 'LOCKED' : 'UNLOCKED'}
					</button>
				</td>
				<td style="text-align:center;">
					<label class="rs-sm-toggle">
						<input type="checkbox" class="rs-view-toggle" data-course="${frappe.utils.escape_html(r.course)}" ${r.view_access ? 'checked' : ''}>
						<span class="rs-sm-toggle-sl"></span>
					</label>
				</td>
				<td>
					<input type="datetime-local" class="rs-deadline rs-view-dl" data-course="${frappe.utils.escape_html(r.course)}"
					       value="${deadlineVal(r.view_deadline)}" ${!r.view_access ? 'disabled' : ''}>
				</td>
				<td style="text-align:center;">
					<label class="rs-sm-toggle">
						<input type="checkbox" class="rs-edit-toggle" data-course="${frappe.utils.escape_html(r.course)}" ${r.edit_access ? 'checked' : ''}>
						<span class="rs-sm-toggle-sl"></span>
					</label>
				</td>
				<td>
					<input type="datetime-local" class="rs-deadline rs-edit-dl" data-course="${frappe.utils.escape_html(r.course)}"
					       value="${deadlineVal(r.edit_deadline)}" ${!r.edit_access ? 'disabled' : ''}>
				</td>
				<td><div class="rs-ga-wrap">${gaChips}</div></td>
				<td style="text-align:center;">
					<button class="rs-icon-btn rs-configure-btn" data-course="${frappe.utils.escape_html(r.course)}" title="Configure">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<circle cx="12" cy="12" r="3"/>
							<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
						</svg>
					</button>
				</td>
			</tr>`;
		});

		$tbody.html(html);
		bindAccessRowEvents($tbody);
	}

	function buildGaChips(r) {
		var chips = [
			{ key: 'auto_generate_grade_access', label: 'AG' },
			{ key: 'edit_grade_access',          label: 'EG' },
			{ key: 'relative_grading_access',    label: 'RG' },
			{ key: 'mask_student_info',          label: 'MI' },
			{ key: 'generate_grade_report',      label: 'GR' },
			{ key: 'moderation_policy_access',   label: 'MP' },
		];
		return chips.map(function (c) {
			var on = !!r[c.key];
			return '<span class="rs-ga-chip ' + (on ? 'on' : 'off') + '" title="' +
				c.key.replace(/_/g, ' ') + '">' + c.label + '</span>';
		}).join('');
	}

	function bindAccessRowEvents($tbody) {
		// Status pill toggle
		$tbody.on('click', '.rs-status-pill', function () {
			var course   = $(this).data('course');
			var row      = getCourseRow(course);
			if (!row) return;
			row.status   = row.status === 'LOCKED' ? 'UNLOCKED' : 'LOCKED';
			markDirty(course);
			renderAccessRows();
		});

		// View Access toggle
		$tbody.on('change', '.rs-view-toggle', function () {
			var course = $(this).data('course');
			var row    = getCourseRow(course);
			if (!row) return;
			row.view_access = $(this).is(':checked') ? 1 : 0;
			markDirty(course);
			// enable/disable deadline input
			var $tr = $tbody.find('tr[data-course="' + course + '"]');
			$tr.find('.rs-view-dl').prop('disabled', !row.view_access);
		});

		// Edit Access toggle
		$tbody.on('change', '.rs-edit-toggle', function () {
			var course = $(this).data('course');
			var row    = getCourseRow(course);
			if (!row) return;
			row.edit_access = $(this).is(':checked') ? 1 : 0;
			// Business rule: revoking edit access auto-locks (mirror server validate())
			if (!row.edit_access) row.status = 'LOCKED';
			markDirty(course);
			var $tr = $tbody.find('tr[data-course="' + course + '"]');
			$tr.find('.rs-edit-dl').prop('disabled', !row.edit_access);
			renderAccessRows();  // re-render to update status pill
		});

		// Deadline inputs (mark dirty on change)
		$tbody.on('change', '.rs-view-dl', function () {
			var course = $(this).data('course');
			var row    = getCourseRow(course);
			if (!row) return;
			row.view_deadline = $(this).val() || '';
			markDirty(course);
		});
		$tbody.on('change', '.rs-edit-dl', function () {
			var course = $(this).data('course');
			var row    = getCourseRow(course);
			if (!row) return;
			row.edit_deadline = $(this).val() || '';
			markDirty(course);
		});

		// Configure button
		$tbody.on('click', '.rs-configure-btn', function () {
			var course = $(this).data('course');
			openConfigureModal(course);
		});
	}

	// ── Save all dirty rows ───────────────────────────────────────────────────
	function saveAllDirtyRows() {
		var dirty = Object.keys(S.ar_dirty);
		if (!dirty.length) return;

		S.ar_saving = true;
		var $saveBtn = $tabPanel.find('#rs-ar-save');
		$saveBtn.prop('disabled', true).text('Saving…');

		var pending = dirty.slice();
		var errors  = [];

		function saveNext() {
			if (!pending.length) {
				S.ar_saving = false;
				S.ar_dirty  = {};
				if (errors.length) {
					frappe.show_alert({ message: 'Saved with ' + errors.length + ' error(s): ' + errors.join(', '), indicator: 'orange' });
				} else {
					frappe.show_alert({ message: 'Access settings saved', indicator: 'green' });
				}
				// Re-render toolbar to reset Save button state
				renderAccessResultsTab();
				return;
			}
			var course = pending.shift();
			var row    = getCourseRow(course);
			if (!row) { saveNext(); return; }

			callSaveAccessSetting(row, function (saved) {
				if (saved) mergeAccessRowFromServer(course, saved);
				else       errors.push(row.course_name || course);
				saveNext();
			});
		}

		saveNext();
	}

	function callSaveAccessSetting(row, callback) {
		frappe.call({
			method: 'slcm.slcm.page.result_settings.result_settings.save_access_setting',
			args: {
				exam_plan:                  S.exam_plan,
				course:                     row.course,
				status:                     row.status,
				view_access:                row.view_access,
				view_deadline:              row.view_deadline || '',
				edit_access:                row.edit_access,
				edit_deadline:              row.edit_deadline || '',
				auto_generate_grade_access: row.auto_generate_grade_access,
				edit_grade_access:          row.edit_grade_access,
				relative_grading_access:    row.relative_grading_access,
				mask_student_info:          row.mask_student_info,
				generate_grade_report:      row.generate_grade_report,
				moderation_policy_access:   row.moderation_policy_access,
				evaluators:                 JSON.stringify(row.evaluators || []),
				visible_exams:              JSON.stringify(row.visible_exams || []),
			},
			callback: function (r) { callback(r.message && r.message.success ? r.message : null); },
			error:    function ()   { callback(null); },
		});
	}

	function mergeAccessRowFromServer(course, saved) {
		var row = getCourseRow(course);
		if (!row || !saved) return;
		// Server may have mutated values (validate/before_save)
		Object.assign(row, {
			doc_name:                    saved.doc_name,
			status:                      saved.status,
			view_access:                 saved.view_access,
			view_deadline:               saved.view_deadline || '',
			edit_access:                 saved.edit_access,
			edit_deadline:               saved.edit_deadline || '',
			auto_generate_grade_access:  saved.auto_generate_grade_access,
			edit_grade_access:           saved.edit_grade_access,
			relative_grading_access:     saved.relative_grading_access,
			mask_student_info:           saved.mask_student_info,
			generate_grade_report:       saved.generate_grade_report,
			moderation_policy_access:    saved.moderation_policy_access,
		});
	}

	// ── Configure Modal ───────────────────────────────────────────────────────
	function openConfigureModal(course) {
		var row = getCourseRow(course);
		if (!row) return;

		// Deep clone for local modal state
		var modal_row = JSON.parse(JSON.stringify(row));

		function renderEvaluatorRows() {
			var html = '';
			modal_row.evaluators.forEach(function (ev, idx) {
				html += `<tr>
					<td style="width:130px;">
						<select class="rs-ev-sel" data-ev-idx="${idx}" data-field="evaluator_type">
							<option value="Class Faculty" ${ev.evaluator_type === 'Class Faculty' ? 'selected' : ''}>Class Faculty</option>
							<option value="Custom"        ${ev.evaluator_type === 'Custom'        ? 'selected' : ''}>Custom</option>
						</select>
					</td>
					<td>
						<div class="rs-ac-wrap">
							<input type="text" class="rs-ev-inp rs-faculty-inp" data-ev-idx="${idx}"
							       placeholder="Faculty name…" value="${frappe.utils.escape_html(ev.evaluator_name || '')}">
							<div class="rs-ac-dd"></div>
						</div>
					</td>
					<td style="width:200px;">
						<input type="text" class="rs-ev-inp" data-ev-idx="${idx}" data-field="evaluator_email"
						       placeholder="Email" value="${frappe.utils.escape_html(ev.evaluator_email || '')}">
					</td>
					<td style="width:32px;">
						<button class="rs-ev-del" data-ev-idx="${idx}">&#10005;</button>
					</td>
				</tr>`;
			});
			$modal.find('#rs-ev-tbody').html(html);
			bindEvaluatorEvents();
		}

		function renderVisibleExams() {
			var selected = modal_row.visible_exams.map(function (v) { return v.exam_type; });
			var html = S.exam_types.length ? S.exam_types.map(function (et) {
				var checked = selected.indexOf(et.name) !== -1;
				return `<label class="rs-ve-chip ${checked ? 'selected' : ''}">
					<input type="checkbox" value="${frappe.utils.escape_html(et.name)}" ${checked ? 'checked' : ''}>
					${frappe.utils.escape_html(et.type_name || et.name)}
				</label>`;
			}).join('') : '<span style="font-size:12px;color:#94a3b8;">No exam types found</span>';
			$modal.find('#rs-ve-area').html(html);
			$modal.find('.rs-ve-chip input').on('change', function () {
				var val     = $(this).val();
				var checked = $(this).is(':checked');
				if (checked) {
					if (!modal_row.visible_exams.find(function (v) { return v.exam_type === val; })) {
						modal_row.visible_exams.push({ exam_type: val });
					}
				} else {
					modal_row.visible_exams = modal_row.visible_exams.filter(function (v) { return v.exam_type !== val; });
				}
				$(this).closest('.rs-ve-chip').toggleClass('selected', checked);
			});
		}

		function bindEvaluatorEvents() {
			// Type select
			$modal.find('.rs-ev-sel').on('change', function () {
				var idx   = parseInt($(this).data('ev-idx'));
				var field = $(this).data('field');
				modal_row.evaluators[idx][field] = $(this).val();
			});
			// Email input
			$modal.find('input[data-field="evaluator_email"]').on('input', function () {
				var idx = parseInt($(this).data('ev-idx'));
				modal_row.evaluators[idx].evaluator_email = $(this).val();
			});
			// Faculty name autocomplete
			$modal.find('.rs-faculty-inp').on('input', function () {
				var $inp = $(this);
				var idx  = parseInt($inp.data('ev-idx'));
				var q    = $inp.val().trim();
				modal_row.evaluators[idx].evaluator_name = q;
				var $wrap = $inp.closest('.rs-ac-wrap');
				var $dd   = $wrap.find('.rs-ac-dd');
				if (q.length < 2) { $dd.empty(); $wrap.removeClass('open'); return; }
				frappe.call({
					method: 'slcm.slcm.page.result_settings.result_settings.get_faculty_list',
					args:   { search: q },
					callback: function (r) {
						var opts = r.message || [];
						if (!opts.length) { $dd.empty(); $wrap.removeClass('open'); return; }
						$dd.html(opts.map(function (f) {
							return '<div class="rs-ac-opt" data-name="' + frappe.utils.escape_html(f.name) +
								'" data-label="' + frappe.utils.escape_html(f.label) +
								'" data-email="' + frappe.utils.escape_html(f.email) + '">' +
								frappe.utils.escape_html(f.label) +
								(f.email ? ' <span style="color:#94a3b8;font-size:11px;">— ' + frappe.utils.escape_html(f.email) + '</span>' : '') +
								'</div>';
						}).join(''));
						$wrap.addClass('open');
						$dd.find('.rs-ac-opt').on('click', function () {
							var name  = $(this).data('name');
							var label = $(this).data('label');
							var email = $(this).data('email');
							modal_row.evaluators[idx].evaluator_name  = name;
							modal_row.evaluators[idx].evaluator_email = email;
							$inp.val(label);
							$wrap.find('input[data-field="evaluator_email"]').val(email);
							$dd.empty(); $wrap.removeClass('open');
						});
					},
				});
			});
			// Delete row
			$modal.find('.rs-ev-del').on('click', function () {
				var idx = parseInt($(this).data('ev-idx'));
				modal_row.evaluators.splice(idx, 1);
				renderEvaluatorRows();
			});
		}

		// Grade access checkboxes config
		var GA_FIELDS = [
			{ key: 'auto_generate_grade_access',  label: 'Auto Generate Grade Access' },
			{ key: 'edit_grade_access',            label: 'Edit Grade Access (Manually / Bulk Upload)' },
			{ key: 'relative_grading_access',      label: 'Complete Relative Grading – Manual Schema Access' },
			{ key: 'mask_student_info',            label: 'Mask Student Information' },
			{ key: 'generate_grade_report',        label: 'Generate Grade Report' },
			{ key: 'moderation_policy_access',     label: 'Moderation Policy Access' },
		];

		var gaHtml = GA_FIELDS.map(function (f) {
			return `<label class="rs-chk-row">
				<input type="checkbox" data-ga-field="${f.key}" ${modal_row[f.key] ? 'checked' : ''}>
				<span class="rs-chk-row-lbl">${f.label}</span>
			</label>`;
		}).join('');

		var $overlay = $('<div class="rs-modal-overlay"></div>');
		var $modal   = $(`
			<div class="rs-modal">
				<div class="rs-modal-hdr">
					<div>
						<div class="rs-modal-title">${frappe.utils.escape_html(row.course_name || row.course)}</div>
						<div class="rs-modal-sub">${row.course_code ? frappe.utils.escape_html(row.course_code) + ' · ' : ''}Course Access Configuration</div>
					</div>
					<button class="rs-modal-close">&#10005;</button>
				</div>
				<div class="rs-modal-body">

					<!-- Grade / Schema Access -->
					<div class="rs-msec">
						<div class="rs-msec-title">Grade / Schema Access</div>
						<div class="rs-chk-grid">${gaHtml}</div>
					</div>

					<!-- Evaluators -->
					<div class="rs-msec">
						<div class="rs-msec-title">Evaluators</div>
						<table class="rs-ev-tbl">
							<thead>
								<tr>
									<td><span style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;">Type</span></td>
									<td><span style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;">Name</span></td>
									<td><span style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;">Email</span></td>
									<td></td>
								</tr>
							</thead>
							<tbody id="rs-ev-tbody"></tbody>
						</table>
						<button class="rs-add-row-btn" id="rs-add-evaluator">
							<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
							Add Evaluator
						</button>
					</div>

					<!-- Visible Exams -->
					<div class="rs-msec">
						<div class="rs-msec-title">Visible Exams</div>
						<div class="rs-ve-grid" id="rs-ve-area"></div>
					</div>

				</div>
				<div class="rs-modal-ftr">
					<button class="rs-btn" id="rs-modal-cancel">Cancel</button>
					<button class="rs-btn primary" id="rs-modal-save">Save</button>
				</div>
			</div>
		`);
		$overlay.append($modal);
		$('body').append($overlay);

		renderEvaluatorRows();
		renderVisibleExams();

		// Grade access field changes
		$modal.on('change', 'input[data-ga-field]', function () {
			var field = $(this).data('ga-field');
			modal_row[field] = $(this).is(':checked') ? 1 : 0;
		});

		// Add evaluator
		$modal.find('#rs-add-evaluator').on('click', function () {
			modal_row.evaluators.push({ evaluator_type: 'Class Faculty', evaluator_name: '', evaluator_email: '' });
			renderEvaluatorRows();
		});

		// Close dropdown on outside click
		$('body').on('click.rs_ac_modal', function (e) {
			if (!$(e.target).closest('.rs-ac-wrap').length) {
				$modal.find('.rs-ac-wrap').removeClass('open');
			}
		});

		// Cancel / close
		function closeModal() {
			$('body').off('click.rs_ac_modal');
			$overlay.remove();
		}
		$modal.find('#rs-modal-cancel').on('click', closeModal);
		$modal.find('.rs-modal-close').on('click', closeModal);
		$overlay.on('click', function (e) { if ($(e.target).is($overlay)) closeModal(); });

		// Save
		$modal.find('#rs-modal-save').on('click', function () {
			var $btn = $(this);
			$btn.prop('disabled', true).text('Saving…');

			callSaveAccessSetting(modal_row, function (saved) {
				$btn.prop('disabled', false).text('Save');
				if (!saved) {
					frappe.show_alert({ message: 'Failed to save', indicator: 'red' });
					return;
				}
				// Merge saved server state back into main access_settings
				var mainRow = getCourseRow(course);
				if (mainRow) {
					Object.assign(mainRow, modal_row);
					mergeAccessRowFromServer(course, saved);
					// Remove dirty flag since we just saved this row
					delete S.ar_dirty[course];
				}
				frappe.show_alert({ message: 'Access settings saved', indicator: 'green' });
				closeModal();
				renderAccessResultsTab();
			});
		});
	}

	// ── Access Results helpers ────────────────────────────────────────────────
	function getCourseRow(course) {
		return S.access_settings.find(function (r) { return r.course === course; }) || null;
	}

	function markDirty(course) {
		S.ar_dirty[course] = true;
		// Update Save/Cancel button state
		var dirty_count = Object.keys(S.ar_dirty).length;
		$tabPanel.find('#rs-ar-save').prop('disabled', false).text('Save (' + dirty_count + ')');
		$tabPanel.find('#rs-ar-cancel').prop('disabled', false);
	}

	// ══════════════════════════════════════════════════════════════════════════
	//  PUBLISH TAB
	// ══════════════════════════════════════════════════════════════════════════

	function loadPublishSetting() {
		$tabPanel.html(loadingHtml('Loading publish settings…'));
		frappe.call({
			method: 'slcm.slcm.page.result_settings.result_settings.get_publish_setting',
			args:   { exam_plan: S.exam_plan },
			callback: function (r) {
				var d = r.message || {};
				S.pub_settings = {
					show_total_marks:       d.show_total_marks       || 0,
					show_sgpa:              d.show_sgpa              || 0,
					hide_sgpa_for_failed:   d.hide_sgpa_for_failed   || 0,
					show_egradesheet:       d.show_egradesheet       || 0,
					no_publish_unpaid:      d.no_publish_unpaid      || 0,
					no_publish_no_feedback: d.no_publish_no_feedback || 0,
				};
				S.components = (d.components || []).map(function (c) {
					var full = S.all_components.find(function (a) { return a.name === c.component; });
					return {
						component:      c.component,
						component_name: c.component_name || c.component,
						component_type: full ? full.component_type : 'Custom',
					};
				});
				renderPublishTab();
			},
		});
	}

	function renderPublishTab() {
		var ps = S.pub_settings;
		$tabPanel.html(`
			<div>
				<div class="rs-content-hdr">
					<button class="rs-btn" id="rs-cancel-btn">Cancel</button>
					<button class="rs-btn primary" id="rs-save-btn">Save</button>
				</div>
				<div class="rs-section">
					<div class="rs-sec-title">Component Settings</div>
					<div class="rs-setting-row" style="border-bottom:none;padding:0;">
						<div class="rs-setting-lbl">Publish Marks For Components</div>
						<div class="rs-setting-ctrl" style="flex:2;justify-content:flex-start;flex-wrap:wrap;gap:8px;" id="rs-components-area"></div>
					</div>
				</div>
				<div class="rs-section">
					<div class="rs-sec-title">Exam Settings</div>
					<div class="rs-setting-row">
						<div class="rs-setting-lbl">Show Total Marks</div>
						<div class="rs-setting-ctrl">
							<label class="rs-toggle"><input type="checkbox" id="rs-show-total" ${ps.show_total_marks ? 'checked' : ''}><span class="rs-toggle-sl"></span></label>
						</div>
					</div>
					<div class="rs-setting-row">
						<div class="rs-setting-lbl">Show SGPA</div>
						<div class="rs-setting-ctrl">
							<label class="rs-toggle"><input type="checkbox" id="rs-show-sgpa" ${ps.show_sgpa ? 'checked' : ''}><span class="rs-toggle-sl"></span></label>
							<label class="rs-inline-chk" id="rs-sgpa-hide-wrap" style="${ps.show_sgpa ? '' : 'display:none;'}">
								<input type="checkbox" id="rs-hide-sgpa-failed" ${ps.hide_sgpa_for_failed ? 'checked' : ''}>
								Hide SGPA for Student(s) who have failed in one or more courses in this term
							</label>
						</div>
					</div>
					<div class="rs-setting-row">
						<div class="rs-setting-lbl">Show E-GradeSheet Download Option</div>
						<div class="rs-setting-ctrl">
							<label class="rs-toggle"><input type="checkbox" id="rs-show-egradesheet" ${ps.show_egradesheet ? 'checked' : ''}><span class="rs-toggle-sl"></span></label>
						</div>
					</div>
					<div class="rs-setting-row">
						<div class="rs-setting-lbl">Do not Publish Result for Student who have not paid Fees</div>
						<div class="rs-setting-ctrl">
							<label class="rs-toggle"><input type="checkbox" id="rs-no-publish-unpaid" ${ps.no_publish_unpaid ? 'checked' : ''}><span class="rs-toggle-sl"></span></label>
						</div>
					</div>
					<div class="rs-setting-row">
						<div class="rs-setting-lbl">Do not Publish Result for Student(s) who have not given faculty feedback</div>
						<div class="rs-setting-ctrl">
							<label class="rs-toggle"><input type="checkbox" id="rs-no-publish-feedback" ${ps.no_publish_no_feedback ? 'checked' : ''}><span class="rs-toggle-sl"></span></label>
						</div>
					</div>
				</div>
			</div>
		`);

		renderComponentTags();

		$tabPanel.find('#rs-show-sgpa').on('change', function () {
			$(this).is(':checked') ? $tabPanel.find('#rs-sgpa-hide-wrap').show()
			                       : $tabPanel.find('#rs-sgpa-hide-wrap').hide().find('#rs-hide-sgpa-failed').prop('checked', false);
		});
		$tabPanel.find('#rs-cancel-btn').on('click', loadPublishSetting);
		$tabPanel.find('#rs-save-btn').on('click',   savePublishSetting);
	}

	function renderComponentTags() {
		var $area = $tabPanel.find('#rs-components-area');
		if (!$area.length) return;

		var html = S.components.map(function (c, idx) {
			var col = componentColor(c.component_type);
			return '<span class="rs-tag" style="background:' + col + ';" data-idx="' + idx + '">' +
				frappe.utils.escape_html(c.component_name) +
				'<span class="rs-tag-x" title="Remove">&#10005;</span></span>';
		}).join('');

		var available = S.all_components.filter(function (a) {
			return !S.components.find(function (c) { return c.component === a.name; });
		});
		var ddItems = available.length
			? available.map(function (c) {
				return '<div class="rs-add-item" data-comp="' + frappe.utils.escape_html(c.name) + '">' +
					frappe.utils.escape_html(c.component_name) + '</div>';
			  }).join('')
			: '<div class="rs-add-none">All components added</div>';

		html += '<div class="rs-add-wrap" id="rs-add-wrap">' +
			'<button class="rs-add-btn" id="rs-add-comp-btn">' +
				'<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>' +
				'Add New Component' +
				'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"/></svg>' +
			'</button><div class="rs-add-dd">' + ddItems + '</div></div>';

		$area.html(html);

		$area.find('.rs-tag-x').on('click', function () {
			S.components.splice($(this).closest('.rs-tag').data('idx'), 1);
			renderComponentTags();
		});
		$area.find('#rs-add-comp-btn').on('click', function (e) {
			e.stopPropagation();
			$area.find('#rs-add-wrap').toggleClass('open');
		});
		$area.find('.rs-add-item').on('click', function (e) {
			e.stopPropagation();
			var compName = $(this).data('comp');
			var full = S.all_components.find(function (a) { return a.name === compName; });
			if (full) {
				S.components.push({ component: full.name, component_name: full.component_name, component_type: full.component_type });
				renderComponentTags();
			}
		});
		$(document).off('click.rs_add').on('click.rs_add', function () {
			$area.find('#rs-add-wrap').removeClass('open');
		});
	}

	function savePublishSetting() {
		var $btn = $tabPanel.find('#rs-save-btn');
		$btn.prop('disabled', true).text('Saving…');

		var settings = {
			show_total_marks:       $tabPanel.find('#rs-show-total').is(':checked')         ? 1 : 0,
			show_sgpa:              $tabPanel.find('#rs-show-sgpa').is(':checked')           ? 1 : 0,
			hide_sgpa_for_failed:   $tabPanel.find('#rs-hide-sgpa-failed').is(':checked')   ? 1 : 0,
			show_egradesheet:       $tabPanel.find('#rs-show-egradesheet').is(':checked')   ? 1 : 0,
			no_publish_unpaid:      $tabPanel.find('#rs-no-publish-unpaid').is(':checked')  ? 1 : 0,
			no_publish_no_feedback: $tabPanel.find('#rs-no-publish-feedback').is(':checked') ? 1 : 0,
		};

		frappe.call({
			method: 'slcm.slcm.page.result_settings.result_settings.save_publish_setting',
			args: Object.assign({ exam_plan: S.exam_plan,
				components: JSON.stringify(S.components.map(function (c) { return { component: c.component }; })) },
				settings),
			callback: function (r) {
				$btn.prop('disabled', false).text('Save');
				if (r.message && r.message.success) {
					Object.assign(S.pub_settings, settings);
					frappe.show_alert({ message: 'Publish settings saved', indicator: 'green' });
				} else {
					frappe.show_alert({ message: 'Failed to save settings', indicator: 'red' });
				}
			},
			error: function () {
				$btn.prop('disabled', false).text('Save');
				frappe.show_alert({ message: 'Error saving settings', indicator: 'red' });
			},
		});
	}

	function componentColor(type) {
		if (type === 'Re Exam') return '#920C24';
		if (type === 'Makeup')  return '#920C24';
		return '#920C24';
	}

	// ── Shared helpers ────────────────────────────────────────────────────────
	function loadingHtml(msg) {
		return '<div class="rs-loading"><svg class="rs-spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.22-8.56"/></svg>' +
			frappe.utils.escape_html(msg || 'Loading…') + '</div>';
	}
};
