frappe.pages['examination-result'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Examination Result',
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

	// ── State ─────────────────────────────────────────────────────────────────
	var S = {
		exam_plan:       null,
		programme:       null,
		course:          null,
		info:            null,   // course_info response
		students:        [],
		total:           0,
		page:            1,
		page_length:     20,
		search:          '',
		sort_by:         'registration_id',
		sort_order:      'asc',
		marks:           {},     // student → {entries: {comp|atype → marks}, grade, ...}
		columns:         [],     // assessment config columns
		reexam_columns:  [],     // reexam config columns
		popup_timer:     null,
		popup_student:   null,
		left_collapsed:  false,
		show_status:     false,  // view/hide student assessment status columns
		selected_all:    false,  // select all across pages
		status_filter:   '',     // student status filter
		grade_filter:    '',     // grade drilldown filter
		pass_filter:     '',     // pass/fail/graded/not_graded filter
		inst_filter:     { programmes: [], batches: [], course_types: [] },
		inst_options:    null,   // cached filter options from backend
	};

	// ── Pending marks save state (shared so lock handler can flush) ─────────
	var _saveTimer          = {};   // key → setTimeout id
	var _pendingSaveFns     = {};   // key → function that does the actual frappe.call

	// ── CSS ───────────────────────────────────────────────────────────────────
	if (!document.getElementById('er2-style')) {
		var style = document.createElement('style');
		style.id  = 'er2-style';
		style.textContent = `
		/* ── Base ── */
		.er2-wrap { font-family: var(--font-stack,'Inter',sans-serif); padding:0; background:#f1f5f9; min-height:100vh; }

		/* ── Tabs ── */
		.er2-tabs { display:flex; gap:4px; margin-bottom:18px;
		            background:#e2e8f0; border-radius:10px; padding:4px; width:fit-content; }
		.er2-tab  { padding:8px 20px; cursor:pointer; font-size:13px; font-weight:600;
		            color:#64748b; border-radius:7px; transition:all .2s;
		            user-select:none; letter-spacing:.1px; }
		.er2-tab:hover { color:#920C24; background:rgba(146,12,36,.08); }
		.er2-tab.active { background:#fff; color:#920C24;
		                  box-shadow:0 1px 4px rgba(0,0,0,.12); }

		/* ── Top filter card ── */
		.er2-filter-card { background:#fff; border-radius:12px; padding:16px 20px;
		                   margin-bottom:16px; display:flex; gap:14px; align-items:flex-end;
		                   box-shadow:0 1px 3px rgba(0,0,0,.06); flex-wrap:wrap; }
		.er2-fgroup  { display:flex; flex-direction:column; min-width:200px; flex:1; max-width:300px; }
		.er2-flabel  { font-size:11px; color:#94a3b8; font-weight:600; margin-bottom:5px;
		               text-transform:uppercase; letter-spacing:.6px; }
		.er2-select  { height:36px; border:1.5px solid #e2e8f0; border-radius:8px;
		               padding:0 12px; font-size:13px; background:#fff; color:#1e293b;
		               outline:none; cursor:pointer; transition:border-color .2s; }
		.er2-select:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }

		/* ── Info panel (stat cards) ── */
		.er2-info    { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:16px; }
		.er2-icard   { background:#fff; border-radius:12px; padding:14px 18px; flex:1;
		               min-width:160px; box-shadow:0 1px 3px rgba(0,0,0,.06);
		               border-top:3px solid #920C24; position:relative; overflow:hidden; }
		.er2-icard::after { content:''; position:absolute; right:-12px; top:-12px;
		                    width:60px; height:60px; border-radius:50%;
		                    background:rgba(146,12,36,.05); }
		.er2-icard.teal  { border-top-color:#920C24; }
		.er2-icard.teal::after  { background:rgba(146,12,36,.05); }
		.er2-icard.green { border-top-color:#920C24; }
		.er2-icard.green::after { background:rgba(146,12,36,.05); }
		.er2-icard.amber { border-top-color:#920C24; }
		.er2-icard.amber::after { background:rgba(146,12,36,.05); }
		.er2-icard.rose  { border-top-color:#920C24; }
		.er2-icard.rose::after  { background:rgba(146,12,36,.05); }
		.er2-icard.slate { border-top-color:#64748b; }
		.er2-icard.slate::after { background:rgba(100,116,139,.05); }
		.er2-icard.violet{ border-top-color:#920C24; }
		.er2-icard.violet::after{ background:rgba(146,12,36,.05); }
		.er2-ilabel  { font-size:10px; color:#94a3b8; text-transform:uppercase;
		               letter-spacing:.7px; font-weight:700; margin-bottom:5px; }
		.er2-ival    { font-size:13px; color:#1e293b; font-weight:600; line-height:1.4; }
		.er2-ival a  { color:#920C24; text-decoration:none; border-bottom:1px dashed #E8B4BE; }
		.er2-ival a:hover { color:#6E091B; }
		.er2-ival.green { color:#059669; }
		.er2-ival.orange { color:#920C24; }
		.er2-irow    { display:flex; flex-direction:column; gap:2px; }

		/* ── Action bar ── */
		.er2-actbar  { display:flex; gap:8px; align-items:center; flex-wrap:wrap;
		               margin-bottom:12px; background:#fff; border-radius:10px;
		               padding:10px 14px; box-shadow:0 1px 3px rgba(0,0,0,.06); }
		.er2-srch    { flex:1; min-width:200px; max-width:320px; position:relative; }
		.er2-srch input { width:100%; height:34px; border:1.5px solid #e2e8f0; border-radius:20px;
		                  padding:0 14px 0 36px; font-size:13px; outline:none; color:#1e293b;
		                  background:#f8fafc; transition:border-color .2s, background .2s; }
		.er2-srch input:focus { border-color:#920C24; background:#fff;
		                        box-shadow:0 0 0 3px rgba(146,12,36,.1); }
		.er2-srch-ico { position:absolute; left:11px; top:9px; color:#94a3b8; }

		/* ── Buttons ── */
		.er2-btn     { height:34px; padding:0 14px; border-radius:7px; border:1.5px solid #e2e8f0;
		               background:#fff; cursor:pointer; font-size:12.5px; font-weight:600;
		               color:#475569; display:inline-flex; align-items:center; gap:5px;
		               white-space:nowrap; transition:all .15s; }
		.er2-btn:hover { background:#f8fafc; border-color:#cbd5e1; color:#1e293b; }
		.er2-btn.primary { background:#920C24;
		                   border-color:transparent; color:#fff; }
		.er2-btn.primary:hover { background:linear-gradient(135deg,#6E091B,#920C24); }
		.er2-btn.outline-red { border-color:#E8B4BE; color:#920C24; background:#FBEEF0; }
		.er2-btn.outline-red:hover { background:#F5D9DE; border-color:#C4566A; }
		.er2-btn.outline-indigo { border-color:#E8B4BE; color:#920C24; background:#FBEEF0; }
		.er2-btn.outline-indigo:hover { background:#F5D9DE; }

		/* ── Dropdowns ── */
		.er2-btn-dd  { position:relative; display:inline-flex; }
		.er2-btn-dd .dd-menu { display:none; position:absolute; top:100%; left:0; z-index:999;
		                       background:#fff; border:1.5px solid #e2e8f0; border-radius:9px;
		                       box-shadow:0 8px 24px rgba(0,0,0,.12); min-width:170px;
		                       padding:5px; margin-top:4px; }
		/* Bridge the visual gap above the menu so hovering across it doesn't
		   drop out of .er2-btn-dd and close the menu before a click lands. */
		.er2-btn-dd .dd-menu::before { content:''; position:absolute; left:0; right:0;
		                                top:-4px; height:4px; }
		.er2-btn-dd:hover .dd-menu,
		.er2-btn-dd.open .dd-menu { display:block; }
		.dd-item { padding:8px 12px; font-size:12.5px; cursor:pointer; color:#475569;
		           border-radius:6px; font-weight:500; }
		.dd-item:hover { background:#f1f5f9; color:#1e293b; }
		.dd-item + .dd-item { margin-top:1px; }

		/* ── Filter row ── */
		.er2-filterrow { display:flex; align-items:center; gap:8px; margin-bottom:12px;
		                 background:#fff; border-radius:10px; padding:8px 14px;
		                 box-shadow:0 1px 3px rgba(0,0,0,.06); }
		.er2-pag     { display:flex; align-items:center; gap:6px;
		               font-size:12.5px; color:#64748b; }
		.er2-paglen-wrap { display:flex; align-items:center; gap:6px; font-size:12px; color:#64748b; margin-left:auto; }
		.er2-paglen-wrap label { font-weight:600; white-space:nowrap; }
		.er2-paglen  { height:30px; border:1.5px solid #e2e8f0; border-radius:7px;
		               padding:0 8px; font-size:12px; background:#fff; color:#1e293b;
		               outline:none; cursor:pointer; transition:border-color .2s; }
		.er2-paglen:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }
		.er2-paglen-info { font-size:12px; font-weight:600; color:#475569; white-space:nowrap; padding:0 4px; }
		.er2-pag-btn { width:28px; height:28px; border:1.5px solid #e2e8f0; border-radius:7px;
		               background:#fff; cursor:pointer; font-size:14px; display:inline-flex;
		               align-items:center; justify-content:center; color:#64748b;
		               transition:all .15s; }
		.er2-pag-btn:hover:not(:disabled) { background:#FBEEF0; border-color:#E8B4BE; color:#920C24; }
		.er2-pag-btn:disabled { opacity:.35; cursor:default; }

		/* ── Split panel ── */
		.er2-split   { display:flex; gap:0; border-radius:12px; overflow:hidden;
		               background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.08); }
		.er2-left    { width:320px; flex-shrink:0; overflow-y:auto; overflow-x:hidden;
		               border-right:1.5px solid #f1f5f9; }
		.er2-left.collapsed { width:0; border-right:none; }
		.er2-right   { flex:1; overflow:auto; min-width:0; }

		/* ── Left panel header ── */
		.er2-lhdr    { display:flex; align-items:center; gap:8px; padding:11px 13px;
		               background:#920C24;
		               border-bottom:none; position:sticky; top:0; z-index:10; }
		.er2-lhdr-title { font-size:13px; font-weight:700; color:#fff; flex:1; }
		.er2-lhdr input[type="checkbox"] { accent-color:#fff; width:14px; height:14px; cursor:pointer; }
		.er2-sort-btn { font-size:11px; color:rgba(255,255,255,.85); cursor:pointer; background:none;
		                border:1px solid rgba(255,255,255,.3); border-radius:5px; padding:3px 7px;
		                display:flex; align-items:center; gap:3px; transition:all .15s; }
		.er2-sort-btn:hover { background:rgba(255,255,255,.15); color:#fff; }

		/* ── Student status filter bar ── */
		.er2-status-bar { padding:6px 12px; background:#f8fafc; border-bottom:1.5px solid #f1f5f9;
		                  display:flex; align-items:center; gap:6px; }

		/* ── Student row ── */
		.er2-srow    { display:flex; align-items:center; gap:10px; padding:0 13px;
		               height:64px; min-height:64px; flex-shrink:0; box-sizing:border-box;
		               border-bottom:1.5px solid #f8fafc; cursor:pointer; transition:background .15s; }
		.er2-srow:hover { background:#f8fafc; }
		.er2-srow.selected { background:#FBEEF0; }
		.er2-savatar { width:38px; height:38px; border-radius:10px; flex-shrink:0;
		               display:flex; align-items:center; justify-content:center;
		               font-size:15px; font-weight:700; color:#fff; overflow:hidden; }
		.er2-savatar img { width:100%; height:100%; object-fit:cover; }
		.er2-sinfo   { flex:1; min-width:0; }
		.er2-sname   { font-size:13px; font-weight:700; color:#1e293b; white-space:nowrap;
		               overflow:hidden; text-overflow:ellipsis; }
		.er2-sreg    { font-size:11px; color:#94a3b8; margin-top:1px; font-weight:500; }
		.er2-sbadges { display:flex; gap:4px; margin-top:4px; flex-wrap:wrap; }
		.er2-badge   { font-size:10px; font-weight:700; padding:2px 8px; border-radius:20px;
		               letter-spacing:.2px; }
		.er2-badge.active   { background:#d1fae5; color:#065f46; }
		.er2-badge.inactive { background:#F5D9DE; color:#6E091B; }
		.er2-badge.blocked  { background:#F5D9DE; color:#6E091B; }
		.er2-badge.regular  { background:#F5D9DE; color:#6E091B; }
		.er2-badge.dropped  { background:#F5D9DE; color:#6E091B; }

		/* ── Marks table ── */
		.er2-rtable  { border-collapse:separate; border-spacing:0; min-width:100%; font-size:12px; }
		.er2-rtable th, .er2-rtable td { padding:8px 11px; border-right:1px solid #e8ecf4;
		                                  white-space:nowrap; }
		.er2-rtable th { background:linear-gradient(180deg,#f8fafc 0%,#f1f5f9 100%);
		                 position:sticky; top:0; z-index:5;
		                 font-weight:700; color:#374151; text-align:center;
		                 border-bottom:2px solid #e2e8f0; font-size:11px;
		                 letter-spacing:.25px; box-shadow:0 2px 4px rgba(0,0,0,.04); }
		.er2-rtable th.type-hdr { font-size:12px; font-weight:800; letter-spacing:.4px; }
		.er2-rtable td { text-align:center; color:#1e293b; border-bottom:1px solid #eef2f9;
		                 vertical-align:middle; transition:background .12s; }
		.er2-rtable tbody tr:hover td { background:#FBEEF0; }
		.er2-rtable tbody tr:nth-child(even) td { background:#f8fafd; }
		.er2-rtable tbody tr:nth-child(even):hover td { background:#F5D9DE; }
		.er2-mrow    { height:60px; max-height:60px; }

		/* ── Annotation badges (MFA / AS superscripts) ── */
		.er2-ann-badge { display:inline-block; font-size:9px; font-weight:800;
		                 padding:1px 5px; border-radius:4px; vertical-align:super;
		                 line-height:1.3; letter-spacing:.3px; margin-left:2px; }
		.er2-mfa-badge    { background:#F5D9DE; color:#6E091B; border:1px solid #E8B4BE; }
		.er2-as-badge     { background:#F5D9DE; color:#6E091B; border:1px solid #E8B4BE; }
		.er2-arrear-badge { background:#FBEEF0; color:#6E091B; border:1px solid #E8B4BE; font-style:italic; cursor:pointer; }
		.er2-arrear-badge:hover { background:#E8B4BE; }
		.er2-improved-badge { background:#F5D9DE; color:#6E091B; border:1px solid #C4566A; font-style:normal; font-weight:800; cursor:pointer; }
		.er2-improved-badge:hover { background:#E8B4BE; }
		.er2-improv-badge { background:#F5D9DE; color:#6E091B; border:1px solid #C4566A; font-weight:800; }

		/* Repeat exam dialog */
		#er2-repeat-overlay {
			display:none;position:fixed;inset:0;z-index:9999;
			background:rgba(15,23,42,.55);backdrop-filter:blur(3px);
			align-items:center;justify-content:center;padding:16px;
		}
		#er2-repeat-dialog {
			background:#fff;border-radius:16px;max-width:520px;width:100%;
			box-shadow:0 24px 64px rgba(0,0,0,.22);overflow:hidden;
		}
		#er2-repeat-dialog .rp-hdr {
			background:linear-gradient(135deg,#1e293b,#0f172a);
			padding:20px 24px 16px;
			display:flex;align-items:flex-start;gap:12px;
		}
		#er2-repeat-dialog .rp-hdr-icon { font-size:26px;color:#920C24;flex-shrink:0; }
		#er2-repeat-dialog .rp-hdr-title { font-size:1rem;font-weight:700;color:#f8fafc; }
		#er2-repeat-dialog .rp-hdr-sub { font-size:.78rem;color:#94a3b8;margin-top:3px; }
		#er2-repeat-dialog .rp-body { padding:20px 24px; }
		#er2-repeat-dialog .rp-step {
			display:flex;gap:12px;margin-bottom:14px;
			padding:12px 14px;border-radius:10px;
			background:#f8fafc;border:1px solid #e2e8f0;
		}
		#er2-repeat-dialog .rp-step-num {
			width:24px;height:24px;border-radius:50%;
			background:#920C24;color:#fff;
			font-size:12px;font-weight:800;
			display:flex;align-items:center;justify-content:center;flex-shrink:0;
		}
		#er2-repeat-dialog .rp-step-text { font-size:.83rem;color:#374151;line-height:1.55; }
		#er2-repeat-dialog .rp-step-text strong { color:#1e293b; }
		#er2-repeat-dialog .rp-ep-row {
			display:flex;gap:8px;align-items:center;margin-top:14px;
		}
		#er2-repeat-dialog .rp-ep-select {
			flex:1;border:1.5px solid #d1d5db;border-radius:8px;
			padding:8px 10px;font-size:13px;color:#1f2937;outline:none;
		}
		#er2-repeat-dialog .rp-ep-select:focus { border-color:#920C24;box-shadow:0 0 0 2px rgba(146,12,36,.15); }
		#er2-repeat-dialog .rp-enroll-btn {
			padding:9px 18px;border:none;border-radius:8px;
			background:#920C24;color:#fff;font-size:.85rem;font-weight:700;
			cursor:pointer;white-space:nowrap;transition:background .15s;
		}
		#er2-repeat-dialog .rp-enroll-btn:hover { background:#920C24; }
		#er2-repeat-dialog .rp-enroll-btn:disabled { background:#9ca3af;cursor:not-allowed; }
		#er2-repeat-dialog .rp-footer {
			padding:12px 24px 18px;display:flex;justify-content:flex-end;gap:8px;
		}
		#er2-repeat-dialog .rp-close-btn {
			padding:8px 20px;border-radius:8px;border:1.5px solid #e2e8f0;
			background:#fff;color:#475569;font-size:.85rem;font-weight:600;cursor:pointer;
		}
		#er2-repeat-dialog .rp-status-msg {
			margin-top:10px;padding:10px 12px;border-radius:8px;font-size:.82rem;font-weight:600;display:none;
		}
		#er2-repeat-dialog .rp-status-msg.success { background:#d1fae5;color:#065f46;border:1px solid #6ee7b7; }
		#er2-repeat-dialog .rp-status-msg.error   { background:#F5D9DE;color:#6E091B;border:1px solid #E8B4BE; }

		/* ── Project column highlight ── */
		.er2-rtable td.er2-proj-total-cell { background:#FBEEF0; border-left:2px solid #E8B4BE; font-weight:700; }
		.er2-rtable tbody tr:hover td.er2-proj-total-cell { background:#F5D9DE; }

		/* ── Grade cell ── */
		.er2-rtable td.er2-grade-cell { background:#FBEEF0; border-left:2px solid #E8B4BE; }
		.er2-rtable tbody tr:hover td.er2-grade-cell { background:#F5D9DE; }

		/* ── Total marks cell ── */
		.er2-rtable td.er2-total-cell { background:#FBEEF0; border-left:2px solid #E8B4BE; font-weight:800; color:#920C24; }
		.er2-rtable tbody tr:hover td.er2-total-cell { background:#F5D9DE; }

		/* ── Status column inputs ── */
		.er2-ss { font-size:11px; border:1px solid #e2e8f0 !important; border-radius:5px !important;
		          background:#fff; color:#374151; transition:border-color .15s; }
		.er2-ss:focus { border-color:#920C24 !important; outline:none; box-shadow:0 0 0 2px rgba(146,12,36,.12); }

		/* ── Grade inputs ── */
		.er2-grade-input:focus { border-color:#920C24 !important; box-shadow:0 0 0 2px rgba(146,12,36,.15); }
		.er2-ug-input   { transition:border-color .15s, box-shadow .15s; }
		.er2-ug-input:focus { border-color:#920C24 !important; box-shadow:0 0 0 2px rgba(146,12,36,.15); }

		/* ── Updated Final Result cells ── */
		.er2-rtable td.er2-ufm-cell { background:#FBEEF0; border-left:2px solid #E8B4BE; font-weight:800; color:#920C24; }
		.er2-rtable tbody tr:hover td.er2-ufm-cell { background:#F5D9DE; }
		.er2-rtable td.er2-ug-cell  { background:#FBEEF0; border-left:1px solid #E8B4BE; font-weight:700; color:#6E091B; }
		.er2-rtable tbody tr:hover td.er2-ug-cell { background:#F5D9DE; }

		/* ── Marks input ── */
		.er2-mi { transition:border-color .15s, box-shadow .15s; }
		.er2-mi:focus { box-shadow:0 0 0 2px rgba(146,12,36,.12); }

		/* ── Re-Exam Grade (read-only, boxed like the other grade/marks inputs) ── */
		.er2-rxg-box {
			display:inline-block; min-width:60px; height:26px; line-height:24px;
			border:1.5px solid #E8B4BE; border-radius:6px; padding:0 6px;
			background:#FBEEF0; font-size:12px; font-weight:700; text-align:center;
			color:#920C24;
		}

		/* ── Overall status col header accent ── */
		.er2-rtable th.er2-status-hdr { background:#FBEEF0 !important; }

		/* ── Remark cell ── */
		.er2-remark-cell textarea { font-size:11px; border:1px solid #e2e8f0; border-radius:5px;
		                            background:#fff; resize:vertical; transition:border-color .15s; }
		.er2-remark-cell textarea:focus { border-color:#920C24; outline:none;
		                                  box-shadow:0 0 0 2px rgba(146,12,36,.1); }

		/* ── Collapse button ── */
		.er2-collapse-btn { width:18px; cursor:pointer; display:flex; align-items:center;
		                    justify-content:center; background:#f1f5f9; border:none;
		                    border-left:1.5px solid #e2e8f0; color:#94a3b8; font-size:12px;
		                    align-self:stretch; flex-shrink:0; transition:all .15s; }
		.er2-collapse-btn:hover { background:#F5D9DE; color:#920C24; }

		/* ── Hover popup ── */
		#er2-popup   { display:none; position:fixed; z-index:9999; background:#fff;
		               border:1.5px solid #e2e8f0; border-radius:14px;
		               box-shadow:0 16px 40px rgba(0,0,0,.16); padding:0;
		               min-width:310px; max-width:400px; pointer-events:none;
		               overflow:hidden; }
		.er2-pop-head { background:#920C24; padding:14px 16px; }
		.er2-pop-name { font-size:14px; font-weight:700; color:#fff; }
		.er2-pop-sub  { font-size:11px; color:rgba(255,255,255,.75); margin-top:2px; font-weight:500; }
		.er2-pop-body { padding:12px 16px; }
		.er2-pop-row  { display:flex; gap:8px; margin-bottom:5px; font-size:12.5px; }
		.er2-pop-lbl  { color:#94a3b8; min-width:95px; font-weight:600; flex-shrink:0;
		                font-size:11px; text-transform:uppercase; letter-spacing:.4px; }
		.er2-pop-val  { color:#1e293b; font-weight:600; }
		.er2-pop-divider { border:none; border-top:1.5px solid #f1f5f9; margin:10px 0; }
		.er2-pop-marks-title { font-size:10.5px; font-weight:700; color:#94a3b8; text-transform:uppercase;
		                       letter-spacing:.5px; margin-bottom:8px; }
		.er2-pop-marks-grid { display:flex; flex-wrap:wrap; gap:6px; }
		.er2-pop-mark-chip  { background:#f8fafc; border:1.5px solid #e2e8f0; border-radius:8px;
		                      padding:5px 10px; font-size:11.5px; min-width:80px; text-align:center; }
		.er2-pop-mark-chip .chip-lbl { color:#64748b; font-size:10px; font-weight:600;
		                               text-transform:uppercase; letter-spacing:.3px; display:block; }
		.er2-pop-mark-chip .chip-val { color:#1e293b; font-size:13px; font-weight:700;
		                               display:block; margin-top:2px; }
		.er2-pop-total-row { display:flex; justify-content:space-between; align-items:center;
		                     background:#FBEEF0; border-radius:8px; padding:8px 12px; margin-top:8px; }
		.er2-pop-total-lbl { font-size:11px; color:#920C24; font-weight:700;
		                     text-transform:uppercase; letter-spacing:.4px; }
		.er2-pop-total-val { font-size:18px; font-weight:800; color:#920C24; }
		.er2-pop-grade-badge { background:#920C24; color:#fff; font-size:11px; font-weight:700;
		                       padding:2px 10px; border-radius:20px; margin-left:8px; }

		/* ── Sync btn ── */
		.er2-sync-btn { font-size:10px; background:#920C24;
		                color:#fff; border:none; border-radius:5px; padding:3px 8px;
		                cursor:pointer; margin-top:3px; font-weight:600; }
		.er2-sync-btn:hover { background:linear-gradient(135deg,#6E091B,#920C24); }

		/* ── Toggle wrap ── */
		.er2-toggle-wrap { display:flex; align-items:center; gap:8px; padding:8px 13px;
		                   background:#f8fafc; border-bottom:1.5px solid #f1f5f9;
		                   position:sticky; top:0; z-index:10; }
		.er2-toggle-lbl { font-size:12px; font-weight:600; color:#475569; }
		.er2-toggle  { position:relative; width:36px; height:20px; }
		.er2-toggle input { opacity:0; width:0; height:0; }
		.er2-slider  { position:absolute; inset:0; border-radius:20px; background:#cbd5e1;
		               cursor:pointer; transition:background .2s; }
		.er2-slider:before { content:''; position:absolute; width:14px; height:14px;
		                     left:3px; top:3px; border-radius:50%; background:#fff;
		                     transition:transform .2s;
		                     box-shadow:0 1px 3px rgba(0,0,0,.2); }
		.er2-toggle input:checked + .er2-slider { background:#920C24; }
		.er2-toggle input:checked + .er2-slider:before { transform:translateX(16px); }

		/* ── Empty state ── */
		.er2-empty   { display:flex; flex-direction:column; align-items:center;
		               justify-content:center; padding:80px 20px; color:#cbd5e1; }
		.er2-empty svg { width:80px; height:80px; margin-bottom:20px; }
		.er2-empty-txt { font-size:15px; font-weight:600; color:#94a3b8; }
		.er2-empty-sub { font-size:12.5px; color:#cbd5e1; margin-top:6px; }

		/* ── Avatar colour palette ── */
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
		/* Active filter badge on button */
		.xif-btn-active { background:linear-gradient(135deg,#FBEEF0,#F5D9DE) !important;
		                  border-color:#E8B4BE !important; color:#6E091B !important; }

		/* ── Stat cards (drilldown) ── */
		.er2-stats-panel { background:#fff; border-radius:12px; padding:16px 20px;
		                   margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,.06); }
		.er2-stats-cards { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px; }
		.er2-stat-card   { background:#fff; border-radius:12px; padding:14px 16px; flex:1;
		                   min-width:130px; box-shadow:0 1px 3px rgba(0,0,0,.06);
		                   cursor:pointer; transition:all .18s; border:2px solid transparent;
		                   display:flex; align-items:center; gap:12px; }
		.er2-stat-card:hover { box-shadow:0 4px 12px rgba(0,0,0,.1); transform:translateY(-1px); }
		.er2-stat-card.er2-sc-active { border-color:var(--sc-color,#920C24);
		                               background:var(--sc-bg,#FBEEF0); }
		.er2-stat-icon   { width:38px; height:38px; border-radius:9px; flex-shrink:0;
		                   display:flex; align-items:center; justify-content:center;
		                   font-size:17px; background:var(--sc-bg,#FBEEF0); }
		.er2-stat-body   { flex:1; min-width:0; }
		.er2-stat-val    { font-size:22px; font-weight:800; color:var(--sc-color,#920C24);
		                   line-height:1.1; }
		.er2-stat-lbl    { font-size:10px; color:#94a3b8; font-weight:700; text-transform:uppercase;
		                   letter-spacing:.6px; margin-top:2px; }
		.er2-stats-meta  { display:flex; gap:18px; flex-wrap:wrap; align-items:center; }
		.er2-stats-avg   { font-size:12.5px; color:#475569; font-weight:500; }
		.er2-gd-wrap     { display:flex; gap:5px; flex-wrap:wrap; }
		.er2-gd-badge    { font-size:11px; font-weight:700; padding:3px 10px; border-radius:20px;
		                   background:#f1f5f9; color:#475569; cursor:pointer; transition:all .15s;
		                   border:1.5px solid transparent; }
		.er2-gd-badge:hover  { background:#FBEEF0; color:#920C24; }
		.er2-gd-badge.er2-gd-active { background:#FBEEF0; color:#920C24; border-color:#E8B4BE; }

		/* ── Editable marks input ── */
		.er2-mi { width:68px; height:26px; border:1.5px solid #e2e8f0; border-radius:6px;
		          padding:0 5px; font-size:12px; color:#334155; text-align:center;
		          background:#fff; outline:none; transition:border-color .15s; }
		.er2-mi:focus   { border-color:#920C24; box-shadow:0 0 0 2px rgba(146,12,36,.12); }
		.er2-mi:disabled { background:#f8fafc; color:#94a3b8; cursor:not-allowed; }

		/* ── Lock button states ── */
		.er2-btn.outline-green { border-color:#E8B4BE; color:#920C24; background:#FBEEF0; }
		.er2-btn.outline-green:hover { background:#F5D9DE; border-color:#E8B4BE; }

		/* ── Page header ── */
		.er2-page-header { background:#fff; border-radius:12px; padding:20px 24px;
		                   margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,.06);
		                   display:flex; align-items:center; gap:16px; }
		.er2-page-icon   { width:46px; height:46px; border-radius:12px; flex-shrink:0;
		                   display:flex; align-items:center; justify-content:center; }
		.er2-page-title  { font-size:17px; font-weight:800; color:#0f172a; line-height:1.2; }
		.er2-page-sub    { font-size:12px; color:#94a3b8; margin-top:3px; font-weight:500; }

		/* ── Page nav tabs ── */
		.er2-page-nav    { display:flex; gap:4px; margin-bottom:16px; background:#e2e8f0;
		                   border-radius:10px; padding:4px; width:fit-content; }
		.er2-pnav-btn    { padding:8px 18px; cursor:pointer; font-size:13px; font-weight:600;
		                   color:#64748b; border-radius:7px; transition:all .2s;
		                   user-select:none; letter-spacing:.1px; border:none;
		                   background:transparent; display:inline-flex; align-items:center; gap:5px; }
		.er2-pnav-btn:hover  { color:#920C24; background:rgba(146,12,36,.08); }
		.er2-pnav-btn.active { background:#fff; color:#920C24;
		                       box-shadow:0 1px 4px rgba(0,0,0,.12); }

		/* ── Add Student Modal ── */
		.xas-overlay { position:fixed; inset:0; z-index:10000;
		               background:rgba(15,23,42,.45); backdrop-filter:blur(3px);
		               display:flex; align-items:center; justify-content:center; padding:16px; }
		.xas-modal   { background:#fff; border-radius:14px; width:700px; max-width:95vw;
		               max-height:88vh; display:flex; flex-direction:column;
		               box-shadow:0 24px 64px rgba(0,0,0,.2); overflow:hidden; }
		.xas-header  { display:flex; align-items:center; justify-content:space-between;
		               padding:16px 20px 14px; border-bottom:1.5px solid #f1f5f9; }
		.xas-title   { font-size:15px; font-weight:800; color:#0f172a; }
		.xas-sub     { font-size:12px; color:#94a3b8; margin-top:2px; }
		.xas-close   { width:30px; height:30px; border-radius:8px; border:none;
		               background:#f1f5f9; cursor:pointer; display:flex; align-items:center;
		               justify-content:center; color:#64748b; font-size:18px; transition:all .15s; flex-shrink:0; }
		.xas-close:hover { background:#F5D9DE; color:#920C24; }
		.xas-tabs    { display:flex; gap:3px; padding:10px 16px 0; border-bottom:1.5px solid #f1f5f9; }
		.xas-tab     { padding:8px 18px; border:none; border-radius:7px 7px 0 0;
		               background:transparent; font-size:13px; font-weight:600; color:#64748b;
		               cursor:pointer; display:inline-flex; align-items:center; gap:6px;
		               transition:all .15s; border-bottom:2.5px solid transparent; margin-bottom:-1.5px; }
		.xas-tab:hover  { color:#920C24; background:rgba(146,12,36,.06); }
		.xas-tab.active { color:#920C24; border-bottom-color:#920C24; background:#fff; }
		.xas-panel   { flex:1; display:flex; flex-direction:column; overflow:hidden; min-height:0; }
		.xas-search-bar { display:flex; gap:8px; padding:12px 16px; border-bottom:1.5px solid #f1f5f9;
		                  flex-wrap:wrap; align-items:center; }
		.xas-srch-wrap  { position:relative; flex:1; min-width:200px; }
		.xas-sinput  { width:100%; height:34px; border:1.5px solid #e2e8f0; border-radius:8px;
		               padding:0 10px 0 34px; font-size:13px; outline:none; color:#1e293b;
		               background:#fff; transition:border-color .2s; box-sizing:border-box; }
		.xas-sinput:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }
		.xas-sselect { height:34px; border:1.5px solid #e2e8f0; border-radius:8px;
		               padding:0 10px; font-size:12.5px; color:#1e293b; background:#fff;
		               outline:none; cursor:pointer; transition:border-color .2s; }
		.xas-sselect:focus { border-color:#920C24; }
		.xas-list    { flex:1; overflow-y:auto; padding:8px; min-height:0; max-height:360px; }
		.xas-loading, .xas-empty-list { display:flex; flex-direction:column; align-items:center;
		               justify-content:center; padding:40px 20px; color:#94a3b8; gap:10px;
		               font-size:13px; font-weight:600; text-align:center; }
		.xas-student-row { display:flex; align-items:center; gap:10px; padding:9px 10px;
		                   border-radius:8px; cursor:pointer; margin-bottom:2px;
		                   transition:background .12s; }
		.xas-student-row:hover { background:#FBEEF0; }
		.xas-footer  { display:flex; align-items:center; justify-content:space-between;
		               padding:12px 16px; border-top:1.5px solid #f1f5f9; background:#FDF8F9; }
		.xas-sel-count { font-size:12.5px; font-weight:600; color:#64748b; }
		.xas-cancel-btn { padding:0 16px; height:34px; border-radius:8px;
		                  border:1.5px solid #e2e8f0; background:#fff; color:#475569;
		                  font-size:13px; font-weight:600; cursor:pointer; transition:all .15s; }
		.xas-cancel-btn:hover { border-color:#94a3b8; color:#1e293b; }
		.xas-add-btn { height:34px; padding:0 18px; border-radius:8px; border:none;
		               background:#920C24; color:#fff;
		               font-size:13px; font-weight:700; cursor:pointer;
		               display:inline-flex; align-items:center; gap:6px; transition:opacity .15s; }
		.xas-add-btn:hover { opacity:.88; }
		.xas-add-btn:disabled { opacity:.5; cursor:default; }
		.xas-csv-body { flex:1; padding:16px; overflow-y:auto; }
		.xas-csv-hint { display:flex; align-items:flex-start; gap:8px; padding:10px 14px;
		                background:#FBEEF0; border:1.5px solid #E8B4BE; border-radius:8px;
		                font-size:12.5px; color:#6E091B; margin-bottom:14px; }
		.xas-dl-btn   { height:34px; padding:0 14px; border-radius:8px; border:1.5px solid #920C24;
		                background:#fff; color:#920C24; font-size:12px; font-weight:700; cursor:pointer;
		                display:inline-flex; align-items:center; gap:6px; transition:all .15s; }
		.xas-dl-btn:hover { background:#F5D9DE; }
		.xas-drop-zone { border:2px dashed #e2e8f0; border-radius:10px; padding:24px 20px;
		                 text-align:center; cursor:pointer; transition:all .18s; background:#FDF8F9;
		                 display:flex; flex-direction:column; align-items:center; gap:4px; }
		.xas-drop-zone:hover, .xas-dz-active { border-color:#920C24; background:#FBEEF0; }
		`;
		document.head.appendChild(style);
	}

	// ── Render shell ──────────────────────────────────────────────────────────
	var $body = $(page.main);
	$body.html(`
		<div class="er2-wrap" style="padding:20px 24px;">

			<!-- Page header -->
			<div class="er2-page-header">
				<div class="er2-page-icon" style="background:#920C24;">
					<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2">
						<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
						<rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
					</svg>
				</div>
				<div>
					<div class="er2-page-title">Course Results</div>
					<div class="er2-page-sub">View and manage student marks, grades and assessment results per course</div>
				</div>
			</div>

			<!-- Page navigation -->
			<div class="er2-page-nav">
				<button class="er2-pnav-btn active">
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

			<!-- Course Results -->
			<div id="er2-tab-course">

				<!-- Top filter card -->
				<div class="er2-filter-card">
					<div class="er2-fgroup" style="max-width:240px;">
						<span class="er2-flabel">
							<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/></svg>
							Exam Plan
						</span>
						<select class="er2-select" id="er2-exam-plan">
							<option value="">Choose Exam Plan</option>
						</select>
					</div>
					<div class="er2-fgroup" style="max-width:260px;">
						<span class="er2-flabel">
							<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
							Programme
						</span>
						<select class="er2-select" id="er2-prog">
							<option value="">Choose Programme</option>
						</select>
					</div>
					<div class="er2-fgroup" style="max-width:320px;">
						<span class="er2-flabel">
							<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
							Course
						</span>
						<select class="er2-select" id="er2-course" disabled>
							<option value="">Choose Course</option>
						</select>
					</div>
					<div style="margin-left:auto;display:flex;gap:8px;align-items:flex-end;">
						<div class="er2-btn-dd">
							<button class="er2-btn outline-indigo" id="er2-sync-btn">
								<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
								Sync Students
								<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"/></svg>
							</button>
							<div class="dd-menu">
								<div class="dd-item" id="er2-sync-enroll">
									<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px;color:#920C24;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
									Sync from Enrollment
								</div>
								<div class="dd-item" id="er2-sync-class">
									<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px;color:#920C24;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
									Add Class Students
								</div>
							</div>
						</div>
						<button class="er2-btn outline-green" id="er2-add-student-btn" style="display:none;">
							<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>
							Add Student
						</button>
						<button class="er2-btn outline-red" id="er2-lock-btn">
							<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
							Lock
						</button>
					</div>
				</div>

				<!-- Course info panel (hidden until course selected) -->
				<div id="er2-info-panel" style="display:none;"></div>

				<!-- Statistics panel (hidden until course selected) -->
				<div id="er2-stats-panel" class="er2-stats-panel" style="display:none;"></div>

				<!-- Action bar (hidden until course selected) -->
				<div id="er2-actbar" class="er2-actbar" style="display:none;">
					<div class="er2-srch">
						<span class="er2-srch-ico">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
						</span>
						<input type="text" id="er2-search" placeholder="Search student name or ID…">
					</div>
					<div class="er2-btn-dd" id="er2-grades-dd">
						<button class="er2-btn outline-indigo">
							<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
							Manage Grades
							<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"/></svg>
						</button>
						<div class="dd-menu">
							<div class="dd-item" id="er2-grade-edit">Edit Grades</div>
							<div class="dd-item" id="er2-grade-bulk-upload">Bulk Upload</div>
							<div class="dd-item" id="er2-grade-report">Grade Report</div>
						</div>
					</div>
					<div class="er2-btn-dd" id="er2-marks-dd">
						<button class="er2-btn outline-indigo">
							<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
							Manage Marks
							<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"/></svg>
						</button>
						<div class="dd-menu">
							<div class="dd-item" id="er2-marks-import">
								<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
								Import Marks
							</div>
							<div class="dd-item" id="er2-reexam-import">
								<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
								Import Re-Exam Marks
							</div>
							<div class="dd-item" id="er2-marks-export">
								<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
								Export Marks (Excel)
							</div>
						</div>
					</div>
					<div class="er2-btn-dd" id="er2-status-dd">
						<button class="er2-btn">
							<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
							Manage Status
							<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"/></svg>
						</button>
						<div class="dd-menu">
							<div class="dd-item">Mark as Submitted</div>
							<div class="dd-item">Mark as Draft</div>
							<div class="dd-item">Lock Selected</div>
						</div>
					</div>
				</div>

				<!-- Filter row (hidden until course selected) -->
				<div id="er2-filterrow" class="er2-filterrow" style="display:none;">
					<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2.5"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
					<select class="er2-select" id="er2-exam-filter" style="max-width:190px;height:30px;font-size:12px;">
						<option value="">All Exam Types</option>
					</select>
					<div class="er2-paglen-wrap">
						<label for="er2-paglen">Show</label>
						<select class="er2-paglen" id="er2-paglen">
							<option value="10">10</option>
							<option value="20" selected>20</option>
							<option value="50">50</option>
							<option value="100">100</option>
							<option value="500">500</option>
						</select>
						<label>records</label>
					</div>
					<div class="er2-pag" id="er2-pag">
						<span class="er2-paglen-info" id="er2-pag-info"></span>
						<button class="er2-pag-btn" id="er2-prev">&#8249;</button>
						<button class="er2-pag-btn" id="er2-next">&#8250;</button>
					</div>
					<button class="er2-btn" id="er2-inst-filter" style="margin-left:4px;height:30px;font-size:12px;">
						<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
						Institutional Filter
					</button>
				</div>

				<!-- Empty state -->
				<div id="er2-empty" class="er2-empty">
					<svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
						<circle cx="60" cy="60" r="56" fill="#FBEEF0" stroke="#E8B4BE" stroke-width="2"/>
						<rect x="35" y="30" width="50" height="60" rx="6" fill="#fff" stroke="#E8B4BE" stroke-width="2"/>
						<rect x="43" y="44" width="34" height="3" rx="1.5" fill="#E8B4BE"/>
						<rect x="43" y="53" width="26" height="3" rx="1.5" fill="#F5D9DE"/>
						<rect x="43" y="62" width="30" height="3" rx="1.5" fill="#F5D9DE"/>
						<rect x="43" y="71" width="20" height="3" rx="1.5" fill="#F5D9DE"/>
						<circle cx="84" cy="84" r="18" fill="#920C24"/>
						<path d="M76 84h16M84 76v16" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
					</svg>
					<div class="er2-empty-txt">Select a Programme &amp; Course</div>
					<div class="er2-empty-sub">Choose from the filters above to view examination results</div>
				</div>

				<!-- Split panel -->
				<div id="er2-split" class="er2-split" style="display:none;max-height:calc(100vh - 340px);">
					<!-- Left: student list -->
					<div id="er2-left" class="er2-left">
						<div class="er2-lhdr">
							<input type="checkbox" id="er2-chk-all" title="Select All">
							<div class="er2-btn-dd" id="er2-select-dd" style="flex:1;min-width:0;">
								<span class="er2-lhdr-title" id="er2-student-count-lbl"
								      style="cursor:pointer;user-select:none;">
									Students (0)
									<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="vertical-align:-1px;"><polyline points="6 9 12 15 18 9"/></svg>
								</span>
								<div class="dd-menu" style="min-width:220px;">
									<div class="dd-item" id="er2-sel-page">
										<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
										Select All For This Page
									</div>
									<div class="dd-item" id="er2-sel-all">
										<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><polyline points="20 6 9 17 4 12"/></svg>
										Select All Across All Pages
									</div>
									<div class="dd-item" id="er2-sel-none">
										<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
										Select None
									</div>
								</div>
							</div>
							<button class="er2-sort-btn" id="er2-sort-btn">
								<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M11 5H21M11 9H17M11 13H13"/><path d="M3 7l4-4 4 4M7 3v14"/></svg>
								<span id="er2-sort-lbl">Sort</span>
							</button>
						</div>
						<div class="er2-status-bar">
							<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2.5"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
							<select id="er2-status-filter" style="font-size:11px;font-weight:600;border:1.5px solid #e2e8f0;border-radius:6px;padding:3px 7px;color:#475569;background:#fff;outline:none;cursor:pointer;">
								<option value="">All Students</option>
								<option value="Active">Active</option>
								<option value="Inactive">Inactive</option>
								<option value="Dropped">Dropped</option>
							</select>
						</div>
						<div id="er2-student-list"></div>
					</div>
					<!-- Collapse toggle -->
					<button class="er2-collapse-btn" id="er2-collapse-btn" title="Toggle panel">&#9664;</button>
					<!-- Right: marks grid -->
					<div id="er2-right" class="er2-right">
						<div class="er2-toggle-wrap" style="display:none;">
							<label class="er2-toggle">
								<input type="checkbox" id="er2-internal-toggle">
								<span class="er2-slider"></span>
							</label>
							<span class="er2-toggle-lbl">Internal</span>
						</div>
						<div id="er2-marks-table-wrap"></div>
					</div>
				</div>

			</div><!-- /tab-course -->
		</div>

		<!-- Hover popup -->
		<div id="er2-popup"></div>

		<!-- Repeat Exam Dialog -->
		<div id="er2-repeat-overlay" onclick="if(event.target===this)document.getElementById('er2-repeat-overlay').style.display='none';">
			<div id="er2-repeat-dialog">
				<div class="rp-hdr">
					<span class="rp-hdr-icon">&#9888;</span>
					<div>
						<div class="rp-hdr-title" id="rp-dialog-title">Student Arrear — Next Re-Exam</div>
						<div class="rp-hdr-sub" id="rp-dialog-sub"></div>
					</div>
				</div>
				<div class="rp-body">
					<div class="rp-step">
						<div class="rp-step-num">1</div>
						<div class="rp-step-text">
							<strong>1st Re-Exam marks</strong> → Enter in the <em>Re exam (Re-Exam)</em> column on this same page under the <strong>current Exam Plan</strong>.
						</div>
					</div>
					<div class="rp-step">
						<div class="rp-step-num">2</div>
						<div class="rp-step-text">
							<strong>2nd+ Re-Exam (RR) marks</strong> → Create or select a <strong>new Exam Plan</strong> for the repeat exam period, then enroll the student below. Their marks will be entered under that new plan.
						</div>
					</div>
					<div class="rp-step">
						<div class="rp-step-num">3</div>
						<div class="rp-step-text">
							The grade badge will show <strong>R</strong> (1–2 arrears) or <strong>RR</strong> (3+ arrears) automatically across all exam plans.
						</div>
					</div>

					<div class="rp-ep-row">
						<select class="rp-ep-select" id="rp-exam-plan-select">
							<option value="">— Select target Exam Plan for next attempt —</option>
						</select>
						<button class="rp-enroll-btn" id="rp-enroll-btn">Enroll &amp; Open</button>
					</div>
					<div class="rp-status-msg" id="rp-status-msg"></div>
				</div>
				<div class="rp-footer">
					<button class="rp-close-btn" onclick="document.getElementById('er2-repeat-overlay').style.display='none';">Close</button>
				</div>
			</div>
		</div>
	`);

	// ── DOM refs ──────────────────────────────────────────────────────────────
	var $examPlan = $body.find('#er2-exam-plan');
	var $prog     = $body.find('#er2-prog');
	var $course   = $body.find('#er2-course');
	var $info     = $body.find('#er2-info-panel');
	var $actbar   = $body.find('#er2-actbar');
	var $filterrow= $body.find('#er2-filterrow');
	var $empty    = $body.find('#er2-empty');
	var $split    = $body.find('#er2-split');
	var $left     = $body.find('#er2-left');
	var $right    = $body.find('#er2-right');
	var $slist    = $body.find('#er2-student-list');
	var $mtable   = $body.find('#er2-marks-table-wrap');
	var $search   = $body.find('#er2-search');
	var $prevBtn  = $body.find('#er2-prev');
	var $nextBtn  = $body.find('#er2-next');
	var $pagInfo  = $body.find('#er2-pag-info');
	var $pagLen   = $body.find('#er2-paglen');
	var $cntLbl   = $body.find('#er2-student-count-lbl');
	var $collapse    = $body.find('#er2-collapse-btn');
	var $popup       = $('#er2-popup');
	var $examFilter  = $body.find('#er2-exam-filter');
	var $statsPanel  = $body.find('#er2-stats-panel');

	// ── Collapse left panel ───────────────────────────────────────────────────
	$collapse.on('click', function () {
		S.left_collapsed = !S.left_collapsed;
		$left.toggleClass('collapsed', S.left_collapsed);
		$collapse.html(S.left_collapsed ? '&#9654;' : '&#9664;');
	});

	// ── Action-bar dropdowns (click to open, not hover) ──────────────────────
	// Hover-only dropdowns leave a dead zone between the button and the menu
	// (the 4px margin-top gap) that closes the menu before the pointer reaches
	// it, making the options look unclickable. Click-to-toggle is reliable
	// regardless of pointer path/speed and also works on touch/trackpad.
	$body.on('click', '.er2-btn-dd > .er2-btn', function (e) {
		e.stopPropagation();
		var $dd = $(this).closest('.er2-btn-dd');
		var wasOpen = $dd.hasClass('open');
		$body.find('.er2-btn-dd.open').removeClass('open');
		if (!wasOpen) $dd.addClass('open');
	});
	$body.on('click', '.dd-menu', function (e) {
		e.stopPropagation();
	});
	$body.on('click', '.dd-item', function () {
		$body.find('.er2-btn-dd.open').removeClass('open');
	});
	$(document).off('click.er2-dd').on('click.er2-dd', function () {
		$body.find('.er2-btn-dd.open').removeClass('open');
	});

	// ── Sync vertical scroll ──────────────────────────────────────────────────
	var syncing = false;
	$left[0].addEventListener('scroll', function () {
		if (syncing) return;
		syncing = true;
		$right[0].scrollTop = $left[0].scrollTop;
		syncing = false;
	});
	$right[0].addEventListener('scroll', function () {
		if (syncing) return;
		syncing = true;
		$left[0].scrollTop = $right[0].scrollTop;
		syncing = false;
	});

	// ── Load exam plans ───────────────────────────────────────────────────────
	frappe.call({
		method: 'slcm.slcm.page.examination_result.examination_result.get_exam_plans',
		callback: function (r) {
			(r.message || []).forEach(function (ep) {
				var label = frappe.utils.escape_html(ep.exam_name || ep.name);
				if (ep.status) label += ' [' + frappe.utils.escape_html(ep.status) + ']';
				$examPlan.append('<option value="' + ep.name + '">' + label + '</option>');
			});
		},
	});

	// ── Load programmes ───────────────────────────────────────────────────────
	frappe.call({
		method: 'slcm.slcm.page.examination_result.examination_result.get_programmes',
		callback: function (r) {
			(r.message || []).forEach(function (p) {
				$prog.append('<option value="' + p.name + '">' +
					frappe.utils.escape_html(p.name) + '</option>');
			});
		},
	});

	// ── Exam Plan change ─────────────────────────────────────────────────────
	$examPlan.on('change', function () {
		S.exam_plan  = $(this).val();
		S.programme  = null;
		S.course     = null;
		S.page       = 1;
		$prog.val('').find('option:not(:first)').remove();
		$course.val('').prop('disabled', true).find('option:not(:first)').remove();
		hide_detail();
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.get_programmes',
			args: { exam_plan: S.exam_plan || '' },
			callback: function (r) {
				(r.message || []).forEach(function (p) {
					$prog.append('<option value="' + p.name + '">' +
						frappe.utils.escape_html(p.name) + '</option>');
				});
			},
		});
	});

	// ── Programme change ──────────────────────────────────────────────────────
	$prog.on('change', function () {
		S.programme = $(this).val();
		S.course     = null;
		S.page       = 1;
		$course.val('').prop('disabled', true).find('option:not(:first)').remove();
		hide_detail();
		if (!S.programme) return;
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.get_courses_by_programme',
			args: { programme: S.programme, exam_plan: S.exam_plan || '' },
			callback: function (r) {
				(r.message || []).forEach(function (c) {
					$course.append('<option value="' + c.name + '">' +
						frappe.utils.escape_html(c.course_name) +
						(c.course_code ? ' [' + c.course_code + ']' : '') + '</option>');
				});
				$course.prop('disabled', false);
			},
		});
	});

	// ── Course change ─────────────────────────────────────────────────────────
	$course.on('change', function () {
		S.course       = $(this).val();
		S.page         = 1;
		S.search       = '';
		S.inst_filter  = { programmes: [], batches: [], course_types: [] };
		S.inst_options = null;
		$search.val('');
		$body.find('#er2-inst-filter').removeClass('xif-btn-active').find('.xif-count').remove();
		hide_detail();
		if (!S.course) return;
		load_course_info();
	});

	// ── Search ────────────────────────────────────────────────────────────────
	$search.on('input', frappe.utils.debounce(function () {
		S.search = $search.val().trim();
		S.page   = 1;
		if (S.course) load_students();
	}, 400));

	// ── Page length ──────────────────────────────────────────────────────────
	$pagLen.on('change', function () {
		S.page_length = parseInt($(this).val(), 10) || 20;
		S.page        = 1;
		if (S.course) load_students();
	});

	// ── Pagination ────────────────────────────────────────────────────────────
	$prevBtn.on('click', function () {
		if (S.page > 1) { S.page--; load_students(); }
	});
	$nextBtn.on('click', function () {
		S.page++;
		load_students();
	});

	// ── Sort ──────────────────────────────────────────────────────────────────
	$body.find('#er2-sort-btn').on('click', function () {
		if (S.sort_by === 'registration_id') {
			S.sort_order = S.sort_order === 'asc' ? 'desc' : 'asc';
		} else {
			S.sort_by    = 'registration_id';
			S.sort_order = 'asc';
		}
		S.page = 1;
		if (S.course) load_students();
	});

	// ── Exam type filter ──────────────────────────────────────────────────────
	$examFilter.on('change', function () {
		render_marks_table();
	});

	// ── Student status filter ─────────────────────────────────────────────────
	$body.find('#er2-status-filter').on('change', function () {
		S.status_filter = $(this).val();
		S.page = 1;
		if (S.course) load_students();
	});

	// ── Select dropdown ───────────────────────────────────────────────────────
	$body.find('#er2-sel-page').on('click', function () {
		S.selected_all = false;
		$body.find('.er2-chk').prop('checked', true);
		$body.find('#er2-chk-all').prop('checked', true);
	});
	$body.find('#er2-sel-all').on('click', function () {
		S.selected_all = true;
		$body.find('.er2-chk').prop('checked', true);
		$body.find('#er2-chk-all').prop('checked', true);
		frappe.show_alert({ message: 'All ' + S.total + ' students selected across all pages.', indicator: 'blue' });
	});
	$body.find('#er2-sel-none').on('click', function () {
		S.selected_all = false;
		$body.find('.er2-chk').prop('checked', false);
		$body.find('#er2-chk-all').prop('checked', false);
	});
	$body.find('#er2-chk-all').on('change', function () {
		var checked = $(this).prop('checked');
		$body.find('.er2-chk').prop('checked', checked);
		if (!checked) S.selected_all = false;
	});

	// ── Institutional Filter ──────────────────────────────────────────────────
	$body.find('#er2-inst-filter').on('click', function () {
		if (!S.course) { frappe.show_alert({ message: 'Select a course first.', indicator: 'orange' }); return; }
		if (S.inst_options) {
			show_inst_filter_dialog(S.inst_options);
		} else {
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.get_institutional_filter_options',
				args: { course: S.course },
				callback: function (r) {
					S.inst_options = r.message || { programmes: [], batches: [], course_types: [] };
					show_inst_filter_dialog(S.inst_options);
				},
			});
		}
	});

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
				if (v.trimester)     args.trimester     = v.trimester;
				if (v.batch)         args.batch         = v.batch;
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

	// ── Manage Grades ─────────────────────────────────────────────────────────
	$body.find('#er2-grade-edit').on('click', function () {
		if (!S.course || !S.info) { frappe.msgprint('Select a course first.'); return; }
		var ids = S.students.map(function (s) { return s.student; });
		if (!ids.length) { frappe.msgprint('No students on this page.'); return; }
		frappe.confirm(
			'Auto-calculate grades for all ' + ids.length + ' student(s) on this page using the Grade Schema?',
			function () {
				frappe.show_alert({ message: 'Calculating grades…', indicator: 'blue' });
				frappe.call({
					method: 'slcm.slcm.page.examination_result.examination_result.auto_generate_grades',
					args: {
						course:      S.course,
						exam_plan:   S.info.exam_plan || '',
						student_ids: JSON.stringify(ids),
					},
					error: function () {
						frappe.show_alert({
							message: 'Grade calculation failed. Check the error log.',
							indicator: 'red',
						});
					},
					callback: function (r) {
						var results = r.message || {};
						var done    = Object.keys(results).length;

						// Update in-memory marks state for every recalculated student
						Object.keys(results).forEach(function (sid) {
							var res = results[sid] || {};
							if (!S.marks[sid]) S.marks[sid] = { entries: {} };
							S.marks[sid].total               = res.total;
							S.marks[sid].grade               = res.grade               || '';
							S.marks[sid].updated_final_marks = res.updated_final_marks;
							S.marks[sid].updated_grade       = res.updated_grade       || '';
						});

						render_marks_table();
						load_stats();
						frappe.show_alert({
							message: 'Grades recalculated for ' + done + ' student(s).',
							indicator: 'green',
						});
					},
				});
			}
		);
	});

	$body.find('#er2-grade-report').on('click', function () {
		if (!S.course || !S.info) { frappe.msgprint('Select a course first.'); return; }
		load_stats(true);
	});

	$body.find('#er2-grade-bulk-upload').on('click', function () {
		if (!S.course) { frappe.msgprint('Select a course first.'); return; }

		var include_students = true;

		var d = new frappe.ui.Dialog({
			title: 'Update Grade In Bulk',
			fields: [
				{
					fieldname: 'info',
					fieldtype: 'HTML',
					options: '<p style="margin-bottom:12px;font-size:13px;color:#333;">Update Grade by uploading an excel file.</p>',
				},
				{
					fieldname: 'include_students',
					fieldtype: 'Check',
					label: 'Include students in sample Excel?',
					default: 1,
					onchange: function () {
						include_students = !!d.get_value('include_students');
					},
				},
				{
					fieldname: 'download_sec',
					fieldtype: 'HTML',
					options: '<div style="margin:10px 0 4px;">' +
						'<button class="btn btn-default btn-sm" id="er2-grade-download-sample" style="width:100%;">' +
						'Download Sample Excel</button></div>',
				},
				{
					fieldname: 'upload_file',
					fieldtype: 'Attach',
					label: 'Upload File',
					reqd: 1,
				},
				{
					fieldname: 'notes_sec',
					fieldtype: 'HTML',
					options: '<div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:4px;padding:10px 14px;margin-top:8px;">' +
						'<div style="font-weight:600;margin-bottom:6px;font-size:13px;">Notes</div>' +
						'<ol style="margin:0;padding-left:18px;font-size:12px;color:#555;">' +
						'<li>Either student Registration ID or Email ID should be entered.</li>' +
						'<li>Before updating results, take a backup via Download sample excel.</li>' +
						'</ol></div>',
				},
			],
			primary_action_label: 'Upload File',
			primary_action: function (values) {
				if (!values.upload_file) {
					frappe.msgprint('Please upload a file.');
					return;
				}
				d.hide();
				frappe.call({
					method: 'slcm.slcm.page.examination_result.examination_result.bulk_upload_grades',
					args: {
						course:    S.course,
						exam_plan: S.info.exam_plan || '',
						file_url:  values.upload_file,
					},
					callback: function (r) {
						var res = r.message || {};
						frappe.show_alert({
							message: 'Grades updated: ' + (res.updated || 0) + ' rows processed.',
							indicator: 'green'
						});
						load_students();
					},
				});
			},
		});

		d.show();

		// Wire download button after dialog renders
		setTimeout(function () {
			$('#er2-grade-download-sample').on('click', function () {
				frappe.call({
					method: 'slcm.slcm.page.examination_result.examination_result.download_grade_sample',
					args: {
						course:           S.course,
						exam_plan:        S.info.exam_plan || '',
						include_students: include_students ? 1 : 0,
					},
					callback: function (r) {
						if (r.message && r.message.file_url) {
							window.open(r.message.file_url);
						}
					},
				});
			});
		}, 300);
	});
	$body.find('#er2-lock-btn').on('click', function () {
		if (!S.course || !S.info) { frappe.msgprint('Select a course first.'); return; }

		// Flush any currently focused input so its change event fires
		var $focused = $mtable.find('.er2-mi:focus');
		if ($focused.length) $focused.trigger('change');

		var isLocked = S.info.status === 'LOCKED';
		var msg = isLocked
			? 'Unlock this course to allow marks entry?'
			: 'Lock this course? Faculty will not be able to edit marks after locking.';
		frappe.confirm(msg, function () {
			// Flush all pending (debounced) mark saves before locking
			var pendingKeys = Object.keys(_pendingSaveFns);
			if (pendingKeys.length) {
				frappe.show_alert({ message: 'Saving pending marks…', indicator: 'blue' });
				var promises = pendingKeys.map(function (k) {
					clearTimeout(_saveTimer[k]);
					var fn = _pendingSaveFns[k];
					return fn ? fn() : Promise.resolve();
				});
				Promise.all(promises).then(function () {
					do_toggle_lock();
				});
			} else {
				do_toggle_lock();
			}
		});

		function do_toggle_lock() {
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.toggle_lock',
				args: { course: S.course, exam_plan: S.info.exam_plan || '' },
				callback: function (r) {
					var res = r.message || {};
					S.info.status = res.status;
					update_lock_btn();
					render_marks_table();
					frappe.show_alert({
						message: res.status === 'LOCKED' ? 'Course locked.' : 'Course unlocked.',
						indicator: res.status === 'LOCKED' ? 'red' : 'green',
					});
				},
			});
		}
	});

	// ── Import / Export Marks ─────────────────────────────────────────────────
	$body.find('#er2-marks-export').on('click', function () {
		if (!S.course || !S.info) { frappe.msgprint('Select a course first.'); return; }
		frappe.show_alert({ message: 'Preparing Excel…', indicator: 'blue' });
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.export_marks_excel',
			args: { course: S.course, exam_plan: S.info.exam_plan || '' },
			callback: function (r) {
				if (r.message && r.message.file_url) {
					window.open(r.message.file_url);
				}
			},
		});
	});

	$body.find('#er2-marks-import').on('click', function () {
		if (!S.course || !S.info) { frappe.msgprint('Select a course first.'); return; }
		var d = new frappe.ui.Dialog({
			title: 'Import Marks from Excel',
			fields: [
				{
					fieldname: 'info_html',
					fieldtype: 'HTML',
					options: '<p style="font-size:12px;color:#64748b;margin:0 0 10px;">Upload the filled marks template. Use <b>Export Marks (Excel)</b> first to get the correct column format.</p>',
				},
				{ fieldname: 'upload_file', fieldtype: 'Attach', label: 'Excel File (.xlsx)', reqd: 1 },
				{
					fieldname: 'note',
					fieldtype: 'HTML',
					options: '<div style="background:#FBEEF0;border:1px solid #E8B4BE;border-radius:6px;padding:10px 14px;margin-top:6px;font-size:12px;color:#6E091B;">' +
						'Rows are matched by Registration ID or Email. Existing marks will be overwritten.' +
						'</div>',
				},
			],
			primary_action_label: 'Import',
			primary_action: function (vals) {
				if (!vals.upload_file) { frappe.msgprint('Please attach a file.'); return; }
				d.hide();
				frappe.call({
					method: 'slcm.slcm.page.examination_result.examination_result.import_marks_excel',
					args: { course: S.course, exam_plan: S.info.exam_plan || '', file_url: vals.upload_file },
					callback: function (r) {
						var res = r.message || {};
						var msg = 'Imported: ' + (res.updated || 0) + ' students updated.';
						if (res.errors && res.errors.length) {
							msg += ' Errors: ' + res.errors.slice(0, 5).join(', ');
						}
						frappe.msgprint(msg);
						load_students();
						load_stats();
					},
				});
			},
			secondary_action_label: 'Download Template',
			secondary_action: function () {
				frappe.show_alert({ message: 'Preparing template…', indicator: 'blue' });
				frappe.call({
					method: 'slcm.slcm.page.examination_result.examination_result.export_marks_excel',
					args: { course: S.course, exam_plan: S.info.exam_plan || '' },
					callback: function (r) {
						if (r.message && r.message.file_url) {
							window.open(r.message.file_url);
						}
					},
				});
			},
		});
		d.show();
	});

	$body.find('#er2-reexam-import').on('click', function () {
		if (!S.course || !S.info) { frappe.msgprint('Select a course first.'); return; }
		var d = new frappe.ui.Dialog({
			title: 'Import Re-Exam Marks',
			fields: [
				{
					fieldname: 'info_html',
					fieldtype: 'HTML',
					options: '<p style="font-size:12px;color:#64748b;margin:0 0 10px;">Upload the filled re-exam marks template. Click <b>Download Template</b> below to get the correct format with student details.</p>',
				},
				{ fieldname: 'upload_file', fieldtype: 'Attach', label: 'Excel File (.xlsx)', reqd: 1 },
				{
					fieldname: 'note',
					fieldtype: 'HTML',
					options: '<div style="background:#F5D9DE;border:1px solid #E8B4BE;border-radius:6px;padding:10px 14px;margin-top:6px;font-size:12px;color:#6E091B;">' +
						'<strong>Re-Exam Marks Import:</strong> Enter marks in the "Re Exam Marks" column. Students are matched by Registration ID or Email.' +
						'</div>',
				},
			],
			primary_action_label: 'Import',
			primary_action: function (vals) {
				if (!vals.upload_file) { frappe.msgprint('Please attach a file.'); return; }
				d.hide();
				frappe.call({
					method: 'slcm.slcm.page.examination_result.examination_result.import_reexam_marks_excel',
					args: { course: S.course, exam_plan: S.info.exam_plan || '', file_url: vals.upload_file },
					callback: function (r) {
						var res = r.message || {};
						var msg = 'Imported: ' + (res.updated || 0) + ' students updated.';
						if (res.errors && res.errors.length) {
							msg += '<br>Errors: ' + res.errors.slice(0, 5).join('<br>');
						}
						frappe.msgprint(msg);
						load_students();
						load_stats();
					},
				});
			},
			secondary_action_label: 'Download Template',
			secondary_action: function () {
				frappe.show_alert({ message: 'Preparing re-exam template…', indicator: 'blue' });
				frappe.call({
					method: 'slcm.slcm.page.examination_result.examination_result.export_reexam_template',
					args: { course: S.course, exam_plan: S.info.exam_plan || '' },
					callback: function (r) {
						if (r.message && r.message.file_url) {
							window.open(r.message.file_url);
						}
					},
				});
			},
		});
		d.show();
	});

	$body.find('#er2-sync-btn').on('click', function () {
		if (!S.course) { frappe.msgprint('Select a course first.'); return; }
	});

	$body.find('#er2-sync-enroll').on('click', function () {
		if (!S.course) { frappe.msgprint('Select a course first.'); return; }
		frappe.confirm('Sync students from Student Enrollment for this course?', function () {
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.sync_students_from_enrollment',
				args: { course: S.course },
				callback: function (r) {
					var res = r.message || {};
					frappe.show_alert({
						message: 'Synced: ' + (res.added || 0) + ' added, ' + (res.skipped || 0) + ' already existed.',
						indicator: 'green'
					});
					load_course_info();
				},
			});
		});
	});

	$body.find('#er2-sync-class').on('click', function () {
		if (!S.course) { frappe.msgprint('Select a course first.'); return; }
		var d = new frappe.ui.Dialog({
			title: 'Add Class Students',
			fields: [
				{
					fieldname: 'class_config',
					fieldtype: 'Link',
					label: 'Class',
					options: 'Class Configuration',
					reqd: 1,
					get_query: function () {
						return { filters: { course: S.course } };
					},
				},
				{
					fieldname: 'course_type',
					fieldtype: 'Select',
					label: 'Course Type',
					options: '\nCore\nElective',
					reqd: 1,
				},
			],
			primary_action_label: 'Add Students',
			primary_action: function (values) {
				d.hide();
				frappe.call({
					method: 'slcm.slcm.page.examination_result.examination_result.sync_students_from_class_config',
					args: {
						course:       S.course,
						class_config: values.class_config,
						course_type:  values.course_type,
					},
					callback: function (r) {
						var res = r.message || {};
						frappe.show_alert({
							message: 'Added: ' + (res.added || 0) + ' students, ' + (res.skipped || 0) + ' already existed.',
							indicator: 'green'
						});
						load_course_info();
					},
				});
			},
		});
		d.show();
	});

	// ── Data loaders ──────────────────────────────────────────────────────────
	function load_course_info() {
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.get_course_info',
			args: { course: S.course, exam_plan: S.exam_plan || '' },
			callback: function (r) {
				S.info           = r.message || {};
				S.columns        = S.info.columns || [];
				S.reexam_columns = S.info.reexam_columns || [];
				S.failed_grades  = S.info.failed_grades  || [];
				render_info_panel();
				populate_exam_filter();
				update_lock_btn();
				$info.show();
				$actbar.show();
				$filterrow.show();
				$statsPanel.show();
				$empty.hide();
				$split.show();
				$body.find('#er2-add-student-btn').show();
				$cntLbl.html('Students (' + S.info.student_count + ') <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="vertical-align:-1px;"><polyline points="6 9 12 15 18 9"/></svg>');
				load_students();
				load_stats();
			},
		});
	}

	function update_lock_btn() {
		var isLocked = S.info && S.info.status === 'LOCKED';
		var $btn = $body.find('#er2-lock-btn');
		if (isLocked) {
			$btn.removeClass('outline-red').addClass('outline-indigo').html(
				'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right:4px;"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>' +
				'Unlock'
			);
		} else {
			$btn.removeClass('outline-indigo').addClass('outline-red').html(
				'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right:4px;"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>' +
				'Lock'
			);
		}
	}

	function load_stats(show_panel) {
		if (!S.info || !S.info.exam_plan) return;
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.get_course_statistics',
			args: { course: S.course, exam_plan: S.info.exam_plan },
			callback: function (r) {
				var st = r.message || {};
				var graded = (st.passed || 0) + (st.failed || 0);

				// Build grade dist badges
				var distHtml = '';
				(st.grade_dist || []).forEach(function (g) {
					distHtml += '<span style="display:inline-flex;align-items:center;gap:4px;' +
						'background:#f1f5f9;border-radius:6px;padding:2px 9px;font-size:12px;margin:2px;">' +
						'<b style="color:#1e293b;">' + frappe.utils.escape_html(g.grade || '') + '</b>' +
						'<span style="color:#64748b;">' + (g.count || 0) + '</span></span>';
				});

				// Extra info row
				var extra = '';
				if (st.avg_marks !== undefined) {
					extra += '<span style="font-size:12px;color:#64748b;font-weight:500;margin-right:16px;">&#x2205; Avg: <b>' + st.avg_marks + '</b></span>';
				}
				if (st.topper && st.topper.name) {
					extra += '<span style="font-size:12px;color:#64748b;font-weight:500;">&#127942; Topper: <b>' + frappe.utils.escape_html(st.topper.name) + '</b>' +
						(st.topper.marks ? ' (' + st.topper.marks + ')' : '') + '</span>';
				}

				$statsPanel.html(
					'<div class="er2-stats-cards">' +
					_stat_card('#920C24', '&#127979;', st.total || 0,    'Total Students') +
					_stat_card('#920C24', '&#9998;',   graded,            'Graded') +
					_stat_card('#920C24', '&#10003;',  st.passed || 0,    'Passed') +
					_stat_card('#920C24', '&#10007;',  st.failed || 0,    'Failed') +
					_stat_card('#920C24', '&#8987;',   st.not_graded || 0,'Not Graded') +
					(distHtml ? '<div class="er2-stat-card" style="--sc-color:#920C24;flex:2.5;">' +
						'<div class="er2-stat-icon" style="background:#F5D9DE;color:#920C24;font-size:16px;">&#127775;</div>' +
						'<div class="er2-stat-body">' +
						'<div class="er2-stat-lbl">Grade Distribution</div>' +
						'<div style="display:flex;flex-wrap:wrap;gap:2px;margin-top:4px;">' + distHtml + '</div>' +
						'</div></div>' : '') +
					'</div>' +
					(extra ? '<div class="er2-stats-meta">' + extra + '</div>' : '')
				);

				if (show_panel) {
					$statsPanel[0].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
				}
			},
		});
	}

	function _stat_card(color, icon, num, lbl) {
		return '<div class="er2-stat-card" style="--sc-color:' + color + ';">' +
			'<div class="er2-stat-icon" style="background:' + color + '22;color:' + color + ';font-size:16px;">' + icon + '</div>' +
			'<div class="er2-stat-body">' +
			'<div class="er2-stat-val">' + num + '</div>' +
			'<div class="er2-stat-lbl">' + lbl + '</div>' +
			'</div></div>';
	}

	function load_students() {
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.get_course_students_paged',
			args: {
				course:            S.course,
				exam_plan:         (S.info && S.info.exam_plan) ? S.info.exam_plan : '',
				search:            S.search,
				page:              S.page,
				page_length:       S.page_length,
				sort_by:           S.sort_by,
				sort_order:        S.sort_order,
				status_filter:     S.status_filter,
				inst_programmes:   JSON.stringify(S.inst_filter.programmes),
				inst_batches:      JSON.stringify(S.inst_filter.batches),
				inst_course_types: JSON.stringify(S.inst_filter.course_types),
			},
			callback: function (r) {
				var data   = r.message || {};
				S.students = data.students || [];
				S.total    = data.total || 0;
				render_student_list();
				load_marks();
				update_pagination();
			},
		});
	}

	function load_marks() {
		if (!S.students.length || !S.info.exam_plan) {
			S.marks = {};
			render_marks_table();
			return;
		}
		var ids = S.students.map(function (s) { return s.student; });
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.get_marks_for_students',
			args: {
				course:      S.course,
				exam_plan:   S.info.exam_plan,
				student_ids: JSON.stringify(ids),
			},
			callback: function (r) {
				S.marks = r.message || {};
				// Always recalculate when project columns exist (deduction must be applied)
				// Also recalculate for students with marks but no grade
				var has_project_col = (S.columns || []).some(function(c) {
					return (c.type_name || '').toLowerCase() === 'project';
				});
				var need_recalc = S.students.filter(function(s) {
					var sm = S.marks[s.student] || {};
					return sm.total != null && (!sm.grade || has_project_col);
				}).map(function(s) { return s.student; });
				if (need_recalc.length) {
					frappe.call({
						method: 'slcm.slcm.page.examination_result.examination_result.auto_generate_grades',
						args: {
							course:      S.course,
							exam_plan:   S.info.exam_plan || '',
							student_ids: JSON.stringify(need_recalc),
						},
						callback: function (gr) {
							Object.keys(gr.message || {}).forEach(function (sid) {
								var res = (gr.message || {})[sid] || {};
								if (!S.marks[sid]) S.marks[sid] = { entries: {} };
								S.marks[sid].total               = res.total;
								S.marks[sid].grade               = res.grade               || '';
								S.marks[sid].updated_final_marks = res.updated_final_marks;
								S.marks[sid].updated_grade       = res.updated_grade       || '';
							});
							render_marks_table();
						},
					});
				} else {
					render_marks_table();
				}
			},
		});
	}

	// ── Renderers ────────────────────────────────────────────────────────────
	function render_info_panel() {
		var o = S.info || {};

		function card(accent, icon, label, val) {
			return '<div class="er2-icard ' + accent + '">' +
				'<div class="er2-ilabel">' + icon + ' ' + label + '</div>' +
				'<div class="er2-ival">' + val + '</div>' +
				'</div>';
		}

		var on_badge  = '<span style="display:inline-flex;align-items:center;gap:4px;background:#F5D9DE;color:#6E091B;font-weight:700;padding:2px 9px;border-radius:20px;font-size:11px;">&#9679; ON</span>';
		var off_badge = '<span style="display:inline-flex;align-items:center;gap:4px;background:#f1f5f9;color:#94a3b8;font-weight:700;padding:2px 9px;border-radius:20px;font-size:11px;">&#9675; OFF</span>';

		var view_val = o.view_access ? on_badge : off_badge;
		var edit_val = o.edit_access
			? on_badge + (o.edit_deadline ? '<span style="font-size:11px;color:#64748b;margin-left:6px;">' + frappe.utils.escape_html(o.edit_deadline) + '</span>' : '')
			: off_badge;
		var mask_val = o.mask_student_info
			? on_badge + '<span style="font-size:11px;color:#64748b;margin-left:6px;">Admin Access</span>'
			: off_badge;

		var eval_link = o.evaluation_schema
			? '<a href="#" class="er2-schema-link" data-schema="eval" data-name="' + frappe.utils.escape_html(o.evaluation_schema) + '">' + frappe.utils.escape_html(o.evaluation_schema) + '</a>'
			: '<span style="color:#94a3b8;">—</span>';
		var grade_link = o.grade_schema
			? '<a href="#" class="er2-schema-link" data-schema="grade" data-name="' + frappe.utils.escape_html(o.grade_schema) + '">' + frappe.utils.escape_html(o.grade_schema) + '</a>'
			: '<span style="color:#94a3b8;">—</span>';
		var calc_link = o.evaluation_schema
			? '<a href="#" id="er2-calc-settings-link" style="color:#920C24;font-size:12px;font-weight:600;text-decoration:none;border-bottom:1px dashed #E8B4BE;">Calculation Settings</a>'
			: '<span style="color:#94a3b8;">—</span>';

		var course_lbl = frappe.utils.escape_html((o.course_name || '') + (o.course_code ? ' [' + o.course_code + ']' : ''));

		$info.html(
			'<div class="er2-info">' +
			card('', '&#128100;', 'Students Enrolled',
				'<span style="font-size:22px;font-weight:800;color:#920C24;line-height:1.1;">' + (o.student_count || 0) + '</span>') +
			card('teal', '&#128218;', 'Course',
				'<span style="font-weight:700;color:#920C24;">' + course_lbl + '</span>' +
				'<span style="display:block;font-size:11px;color:#94a3b8;margin-top:2px;font-weight:500;">' +
				(o.credit_value ? o.credit_value + ' Credits' : '') + '</span>') +
			card('green', '&#9999;&#65039;', 'Evaluation Schema', eval_link +
				'<span style="display:block;margin-top:4px;">' + calc_link + '</span>') +
			card('amber', '&#127775;', 'Grade Schema', grade_link) +
			card('rose', '&#128065;&#65039;', 'View Access', view_val) +
			card('slate', '&#9998;', 'Edit Access', edit_val) +
			card('violet', '&#128373;&#65039;', 'Student Masking', mask_val) +
			'</div>'
		);

		// Bind click handlers after rendering
		$info.find('#er2-calc-settings-link').on('click', function (e) {
			e.preventDefault();
			show_calc_settings_popup(S.info.evaluation_schema);
		});
		$info.find('.er2-schema-link').on('click', function (e) {
			e.preventDefault();
			var schema_type = $(this).data('schema');
			var name = $(this).data('name');
			if (schema_type === 'eval') show_eval_schema_popup(name);
			else show_grade_schema_popup(name);
		});
	}

	function populate_exam_filter() {
		$examFilter.find('option:not(:first)').remove();
		var seen = {};
		(S.columns || []).forEach(function (col) {
			var val = col.assessment_type || '';
			if (!val || seen[val]) return;
			seen[val] = true;
			var lbl = col.type_name || col.assessment_type || '';
			$examFilter.append('<option value="' + frappe.utils.escape_html(val) + '">' +
				frappe.utils.escape_html(lbl) + '</option>');
		});
	}

	function render_student_list() {
		var html = '';
		S.students.forEach(function (s, idx) {
			var status_cls = s.account_status === 'Blocked' ? 'blocked' :
				s.student_status === 'Dropped' ? 'dropped' :
				s.student_status === 'Inactive' ? 'inactive' : 'active';
			var status_txt = s.student_status || 'Active';
			var initials   = (s.student_name || 'S').charAt(0).toUpperCase();
			var av_cls     = 'av-' + (idx % 8);
			var dot_color  = status_cls === 'active' ? '#10b981' : status_cls === 'dropped' ? '#920C24' : '#920C24';
			var avatarContent = s.passport_size_photo
				? '<img src="' + frappe.utils.escape_html(s.passport_size_photo) + '" alt="">'
				: initials;
			var isManual  = s.manually_added ? true : false;
			var rowStyle  = isManual ? ' style="background:#FBEEF0;border-left:3px solid #E8B4BE;"' : '';
			var removeBtn = isManual
				? '<button class="er2-remove-student" data-student="' + frappe.utils.escape_html(s.student) + '" ' +
				  'title="Remove this manually added student" ' +
				  'style="flex-shrink:0;margin-left:auto;padding:3px 8px;font-size:11px;border:1px solid #E8B4BE;' +
				  'border-radius:4px;background:#fff;color:#920C24;cursor:pointer;line-height:1.4;">' +
				  'Remove</button>'
				: '';
			var manualBadge = '';
			html +=
				'<div class="er2-srow" data-student="' + frappe.utils.escape_html(s.student) + '"' + rowStyle + '>' +
				'  <input type="checkbox" class="er2-chk" style="flex-shrink:0;accent-color:#920C24;width:14px;height:14px;cursor:pointer;">' +
				'  <div class="er2-savatar ' + av_cls + '">' + avatarContent + '</div>' +
				'  <div class="er2-sinfo">' +
				'    <div class="er2-sname">' + frappe.utils.escape_html(s.student_name || s.student) + '</div>' +
				'    <div class="er2-sreg">' + frappe.utils.escape_html(s.registration_id || s.student || '') + '</div>' +
				'    <div class="er2-sbadges">' +
				'      <span class="er2-badge ' + status_cls + '">' +
				'        <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:' + dot_color + ';margin-right:4px;vertical-align:1px;"></span>' +
				frappe.utils.escape_html(status_txt) + '</span>' +
				'      <span class="er2-badge regular">Regular</span>' +
				manualBadge +
				'    </div>' +
				'  </div>' +
				removeBtn +
				'</div>';
		});
		if (!html) {
			html = '<div style="padding:40px;text-align:center;color:#94a3b8;font-size:12.5px;font-weight:500;">' +
				'<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="1.5" style="display:block;margin:0 auto 10px;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>' +
				'No students found</div>';
		}
		$slist.html(html);
		bind_hover();

		// Bind remove buttons
		$slist.find('.er2-remove-student').on('click', function (e) {
			e.stopPropagation();
			var student = $(this).data('student');
			var row     = $(this).closest('.er2-srow');
			var name    = row.find('.er2-sname').text();
			frappe.confirm(
				'Remove <strong>' + frappe.utils.escape_html(name) + '</strong> from this course? ' +
				'This will delete their marks record.',
				function () {
					frappe.call({
						method: 'slcm.slcm.page.examination_result.examination_result.remove_student_from_course',
						args: { course: S.course, exam_plan: S.info.exam_plan, student: student },
						callback: function (r) {
							if (r.message && r.message.ok) {
								frappe.show_alert({ message: 'Student removed.', indicator: 'green' }, 3);
								_xas_full_refresh();
							}
						},
					});
				}
			);
		});
	}

	function render_marks_table() {
		// Clear any stale pending saves from previous render
		Object.keys(_saveTimer).forEach(function (k) { clearTimeout(_saveTimer[k]); });
		_saveTimer      = {};
		_pendingSaveFns = {};

		var cols         = S.columns || [];
		var reexam_cols  = S.reexam_columns || [];
		var filter_val   = $examFilter.val();
		if (filter_val) {
			cols = cols.filter(function (c) { return c.assessment_type === filter_val; });
		}

		if (!cols.length && !reexam_cols.length) {
			$mtable.html('<div style="padding:40px;text-align:center;color:#adb5bd;font-size:13px;">No assessment columns configured.</div>');
			return;
		}

		// ── Group regular cols by component ──────────────────────────────────────
		var groups = [];
		var group_map = {};
		cols.forEach(function (col) {
			var comp = col.component || '__none__';
			if (!group_map[comp]) {
				group_map[comp] = {
					component:      comp,
					component_name: col.component_name || comp,
					cols:           [],
				};
				groups.push(group_map[comp]);
			}
			group_map[comp].cols.push(col);
		});

		// ── Group reexam cols by component ───────────────────────────────────────
		var rxgroups = [];
		var rxgroup_map = {};
		reexam_cols.forEach(function (col) {
			var comp = col.component || '__rx_none__';
			if (!rxgroup_map[comp]) {
				rxgroup_map[comp] = {
					component:      comp,
					component_name: col.component_name || comp,
					cols:           [],
				};
				rxgroups.push(rxgroup_map[comp]);
			}
			rxgroup_map[comp].cols.push(col);
		});

		// ── Total number of data columns (for empty-row colspan) ─────────────────
		// Project component: 3 sub-cols (Marks, Deduction, Total Marks)
		// Other regular assessments: 1 sub-col (Marks only)
		// After regular cols: Total Marks, Grade (2 cols)
		// Overall Status: 6 cols
		// Each reexam assessment: 1 sub-col (Marks only)
		// Updated Final Result: 2 cols
		var proj_col_count = cols.filter(function (c) { return (c.type_name || c.label || '').toLowerCase() === 'project'; }).length;
		var total_cols = (cols.length - proj_col_count) * 1 + proj_col_count * 3 + 2 + 6 + reexam_cols.length * 1 + (reexam_cols.length ? 1 : 0) + 2 + 2;

		// ── CSS colours ──────────────────────────────────────────────────────────
		var C_COMP   = 'background:#FBEEF0;color:#6E091B;border-bottom:2px solid #C4566A;';
		var C_GRADE  = 'background:#FBEEF0;color:#6E091B;border-bottom:2px solid #C4566A;';
		var C_STATUS = 'background:#FBEEF0;color:#6E091B;border-bottom:2px solid #C4566A;';
		var C_REEXAM = 'background:#FBEEF0;color:#6E091B;border-bottom:2px solid #C4566A;';
		var C_FINAL  = 'background:#FBEEF0;color:#6E091B;border-bottom:2px solid #C4566A;';
		var C_IMPROV = 'background:#FBEEF0;color:#6E091B;border-bottom:2px solid #C4566A;';

		// ── Header row 1: section-level group headers ────────────────────────────
		var th1 = '';
		groups.forEach(function (g) {
			var g_span = g.cols.reduce(function(sum, col) {
				return sum + ((col.type_name || col.label || '').toLowerCase() === 'project' ? 3 : 1);
			}, 0);
			th1 += '<th colspan="' + g_span + '" class="type-hdr" style="text-align:center;' + C_COMP + '">' +
				frappe.utils.escape_html(g.component_name) + '</th>';
		});
		// Total + Grade (span 2)
		th1 += '<th colspan="2" class="type-hdr" style="text-align:center;' + C_GRADE + '">Grade</th>';
		// Overall Status (span 6 — Fairness Status removed, Notes added)
		th1 += '<th colspan="6" class="type-hdr er2-status-hdr" style="text-align:center;' + C_STATUS + '">' +
			'Overall Status</th>';
		// Re-Exam groups — the trailing "Grade" column (one overall value, not
		// per-group) is folded into the LAST group's span so it reads as part
		// of the Re-Exam section instead of a lone floating header.
		rxgroups.forEach(function (g, gi) {
			var is_last  = gi === rxgroups.length - 1;
			var g_span   = g.cols.length + (is_last ? 1 : 0);
			th1 += '<th colspan="' + g_span + '" class="type-hdr" style="text-align:center;' + C_REEXAM + '">' +
				frappe.utils.escape_html(g.component_name) + ' (Re-Exam)</th>';
		});
		// Improvement Exam (span 2)
		th1 += '<th colspan="2" class="type-hdr" style="text-align:center;' + C_IMPROV + '">Improvement Exam</th>';
		// Updated Final Result (span 2)
		th1 += '<th colspan="2" class="type-hdr" style="text-align:center;' + C_FINAL + '">Updated Final Result</th>';

		// ── Header row 2: assessment labels + max marks ──────────────────────────
		var th2 = '';
		groups.forEach(function (g) {
			g.cols.forEach(function (col) {
				var isProj   = (col.type_name || col.label || '').toLowerCase() === 'project';
				var lbl      = frappe.utils.escape_html(col.label || col.type_name || col.assessment_type || '');
				var max      = col.maximum_marks ? 'Max. ' + parseFloat(col.maximum_marks).toFixed(2) : '';
				var col_span = isProj ? 3 : 1;
				th2 += '<th colspan="' + col_span + '" class="type-hdr" style="text-align:center;">' +
					lbl +
					(max ? '<br><span style="font-size:10px;color:#6c757d;font-weight:400;">' + max + '</span>' : '') + '</th>';
			});
		});
		// Grade section row 2 labels
		th2 += '<th style="font-size:11px;color:#6c757d;min-width:60px;">Total<br>Marks</th>' +
			'<th style="font-size:11px;color:#6c757d;min-width:60px;">Grade</th>';
		// Overall Status row 2 labels (Fairness Status removed)
		th2 += '<th class="er2-status-col" style="font-size:11px;color:#6c757d;min-width:90px;">Enrollment<br>Status</th>' +
			'<th class="er2-status-col" style="font-size:11px;color:#6c757d;min-width:90px;">Attendance<br>Status</th>' +
			'<th class="er2-status-col" style="font-size:11px;color:#6c757d;min-width:60px;">MFA</th>' +
			'<th class="er2-status-col" style="font-size:11px;color:#6c757d;min-width:60px;">SGPA</th>' +
			'<th class="er2-status-col" style="font-size:11px;color:#6c757d;min-width:120px;">Remarks</th>' +
		'<th class="er2-status-col" style="font-size:11px;color:#6c757d;min-width:160px;">Notes</th>';
		// Re-Exam row 2 labels
		rxgroups.forEach(function (g) {
			g.cols.forEach(function (col) {
				var lbl = frappe.utils.escape_html(col.label || col.type_name || col.assessment_type || '');
				var max = col.maximum_marks ? 'Max. ' + parseFloat(col.maximum_marks).toFixed(2) : '';
				th2 += '<th class="type-hdr" style="text-align:center;">' +
					lbl + (max ? '<br><span style="font-size:10px;color:#6c757d;font-weight:400;">' + max + '</span>' : '') + '</th>';
			});
		});
		// Re-Exam Grade row 2 label (matches Improvement Grade's placement)
		if (reexam_cols.length) {
			th2 += '<th style="font-size:11px;color:#6c757d;min-width:70px;">Re-Exam<br>Grade</th>';
		}
		// Improvement Exam row 2 labels, then Updated Final Result
		th2 += '<th style="font-size:11px;color:#6c757d;min-width:80px;">Improvement<br>Marks</th>' +
			'<th style="font-size:11px;color:#6c757d;min-width:80px;">Improvement<br>Grade</th>' +
			'<th style="font-size:11px;color:#6c757d;min-width:80px;">Updated<br>Final Marks</th>' +
			'<th style="font-size:11px;color:#6c757d;min-width:70px;">Updated<br>Grade</th>';

		// ── Header row 3: sub-column labels ──────────────────────────────────────
		var th3 = '';
		groups.forEach(function (g) {
			g.cols.forEach(function (col) {
				var isProj = (col.type_name || col.label || '').toLowerCase() === 'project';
				if (isProj) {
					th3 += '<th style="font-size:11px;color:#6c757d;min-width:70px;">Marks</th>' +
						'<th style="font-size:11px;color:#6c757d;min-width:80px;">Deduction</th>' +
						'<th style="font-size:11px;color:#6c757d;min-width:80px;">Total<br>Marks</th>';
				} else {
					th3 += '<th style="font-size:11px;color:#6c757d;min-width:70px;">Marks</th>';
				}
			});
		});
		// Grade section row 3 (empty — already set in row 2)
		th3 += '<th></th><th></th>';
		// Overall Status row 3 (empty, 6 cols — Fairness Status removed, Notes added)
		th3 += '<th class="er2-status-col"></th>' +
			'<th class="er2-status-col"></th>' +
			'<th class="er2-status-col"></th>' +
			'<th class="er2-status-col"></th>' +
			'<th class="er2-status-col"></th>' +
			'<th class="er2-status-col"></th>';
		// Re-Exam sub-column labels
		reexam_cols.forEach(function () {
			th3 += '<th style="font-size:11px;color:#6c757d;min-width:70px;">Marks</th>';
		});
		// Re-Exam Grade row 3 (empty)
		if (reexam_cols.length) th3 += '<th></th>';
		// Improvement Exam row 3 (empty)
		th3 += '<th></th><th></th>';
		// Updated Final Result row 3 (empty)
		th3 += '<th></th><th></th>';

		// ── Data rows ─────────────────────────────────────────────────────────────
		var rows = '';
		S.students.forEach(function (s) {
			var sm        = S.marks[s.student] || {};
			var entries   = sm.entries || {};
			var isAbsent  = sm.attendance_status === 'Absent';
			var total     = (!isAbsent && sm.total != null) ? parseFloat(sm.total).toFixed(2) : '—';
			var cells     = '';

			var canEdit = S.info && S.info.edit_access && S.info.status !== 'LOCKED';

			// Regular assessment cells
			groups.forEach(function (g) {
				g.cols.forEach(function (col) {
					var isProj = (col.type_name || col.label || '').toLowerCase() === 'project';
					if (isAbsent) {
						var colCount = isProj ? 3 : 1;
						for (var i = 0; i < colCount; i++) {
							cells += '<td style="text-align:center;color:#9ca3af;font-style:italic;">—</td>';
						}
						return;
					}
					var key  = (col.component || '') + '|' + (col.assessment_type || '');
					var e    = entries[key] || {};
					var mVal = e.marks             != null ? parseFloat(e.marks).toFixed(2)             : '';
					var rvVal= e.revaluation_marks  != null ? parseFloat(e.revaluation_marks).toFixed(2) : '';
					var comp = frappe.utils.escape_html(col.component       || '');
					var atyp = frappe.utils.escape_html(col.assessment_type || '');
					var stu  = frappe.utils.escape_html(s.student);
					if (isProj) {
						var mRaw    = e.marks             != null ? parseFloat(e.marks)             : 0;
						var dRaw    = e.revaluation_marks != null ? Math.min(parseFloat(e.revaluation_marks), mRaw) : 0;
						var projTot = (mRaw - dRaw).toFixed(2);
						if (canEdit) {
							cells += '<td style="padding:4px 6px;">' +
								'<input type="number" step="0.01" min="0" class="er2-mi" data-is-project="1" ' +
								'data-student="' + stu + '" data-comp="' + comp + '" data-atype="' + atyp + '" data-field="marks" ' +
								'value="' + frappe.utils.escape_html(mVal) + '" placeholder="—" ' +
								'style="width:70px;height:26px;border:1.5px solid #e2e8f0;border-radius:6px;padding:0 6px;font-size:12px;font-weight:600;text-align:center;outline:none;">' +
								'</td>' +
								'<td style="padding:4px 6px;">' +
								'<input type="number" step="0.01" min="0" class="er2-mi" data-is-project="1" ' +
								'data-student="' + stu + '" data-comp="' + comp + '" data-atype="' + atyp + '" data-field="revaluation_marks" ' +
								'value="' + frappe.utils.escape_html(rvVal) + '" placeholder="—" ' +
								'style="width:70px;height:26px;border:1.5px solid #F5D9DE;border-radius:6px;padding:0 6px;font-size:12px;font-weight:600;text-align:center;outline:none;">' +
								'</td>' +
								'<td class="er2-proj-total-cell" data-comp="' + comp + '" data-atype="' + atyp + '" data-student="' + stu + '" ' +
								'style="font-weight:700;text-align:center;color:#920C24;min-width:80px;">' + projTot + '</td>';
						} else {
							cells += '<td>' + (mVal || '—') + '</td>' +
								'<td>' + (rvVal || '—') + '</td>' +
								'<td style="font-weight:700;color:#920C24;">' + projTot + '</td>';
						}
					} else {
						if (canEdit) {
							cells += '<td style="padding:4px 6px;">' +
								'<input type="number" step="0.01" min="0" class="er2-mi" ' +
								'data-student="' + stu + '" data-comp="' + comp + '" data-atype="' + atyp + '" data-field="marks" ' +
								'value="' + frappe.utils.escape_html(mVal) + '" placeholder="—" ' +
								'style="width:70px;height:26px;border:1.5px solid #e2e8f0;border-radius:6px;padding:0 6px;font-size:12px;font-weight:600;text-align:center;outline:none;">' +
								'</td>';
						} else {
							cells += '<td>' + (mVal || '—') + '</td>';
						}
					}
				});
			});

			var mfaStr    = sm.mfa === 'Yes' ? ' <sup class="er2-ann-badge er2-mfa-badge">MFA</sup>' : '';
			var improvedStr = (sm.arrear_marker === 'I') ? ' <sup class="er2-ann-badge er2-improved-badge">I</sup>' : '';
			var arrearStr = (sm.arrear_marker && sm.arrear_marker !== 'I' && sm.mfa !== 'Yes')
				? ' <sup class="er2-ann-badge er2-arrear-badge">' + frappe.utils.escape_html(sm.arrear_marker) + '</sup>' : '';

			// Grade section — attendance shortage (computed from Attendance
			// Summary against Attendance Settings.minimum_attendance_percentage)
			// replaces the grade entirely with "AS" instead of just annotating it.
			var isAS       = !isAbsent && (!!sm.attendance_shortage || sm.attendance_status === 'Attendance Shortage');
			var gradeVal   = isAbsent ? 'Ab' : (isAS ? 'AS' : (sm.grade || ''));
			var isFailed   = gradeVal && (S.failed_grades || []).indexOf(gradeVal) !== -1;
			var gradeColor = isAS ? '#920C24' : (isFailed ? '#920C24' : '#059669');
			var gradeBorderColor = isAS ? '#E8B4BE' : (isFailed ? '#E8B4BE' : '#a7f3d0');
			cells += '<td style="font-weight:700;" class="er2-total-cell" data-student="' + frappe.utils.escape_html(s.student) + '">' + total + '</td>';
			if (canEdit) {
				cells += '<td style="padding:4px 6px;" class="er2-grade-cell" data-student="' + frappe.utils.escape_html(s.student) + '">' +
					'<span style="white-space:nowrap;">' +
					'<input type="text" class="er2-grade-input" data-student="' + frappe.utils.escape_html(s.student) + '" ' +
					'value="' + frappe.utils.escape_html(gradeVal) + '" placeholder="—" ' + (isAS ? 'readonly title="Grade withheld — attendance below the required minimum (see Attendance Settings)"' : '') + ' ' +
					'style="width:60px;height:26px;border:1.5px solid ' + gradeBorderColor + ';border-radius:6px;padding:0 6px;font-size:12px;font-weight:700;text-align:center;outline:none;color:' + gradeColor + ';' + (isAS ? 'background:#FBEEF0;' : '') + '">' +
					(sm.mfa === 'Yes' ? '<sup class="er2-ann-badge er2-mfa-badge">MFA</sup>' : '') +
					(sm.arrear_marker && sm.arrear_marker !== 'I' && sm.mfa !== 'Yes' ? '<sup class="er2-ann-badge er2-arrear-badge">' + frappe.utils.escape_html(sm.arrear_marker) + '</sup>' : '') +
					'</span></td>';
			} else {
				cells += '<td style="font-weight:700;color:' + gradeColor + ';" class="er2-grade-cell" data-student="' + frappe.utils.escape_html(s.student) + '" title="' + (isAS ? 'Grade withheld — attendance below the required minimum' : '') + '">' + frappe.utils.escape_html(gradeVal || '—') + mfaStr + arrearStr + '</td>';
			}

			// Overall Status (Fairness Status removed from display)
			var es   = sm.enrollment_status  || 'Enrolled';
			var at   = sm.attendance_status  || 'Present';
			var mfa_v= sm.mfa                || 'No';
			var sg   = sm.consider_for_sgpa  ? '<span style="color:#28a745;font-weight:700;">&#10003;</span>' : '—';
			var rmk  = frappe.utils.escape_html(sm.remark || '');

			if (canEdit) {
				var ssAttrs = 'class="er2-ss" data-student="' + frappe.utils.escape_html(s.student) + '" style="width:100%;font-size:11px;border:1px solid #dee2e6;border-radius:3px;padding:3px;outline:none;"';
				var esHtml = '<select ' + ssAttrs + ' data-field="enrollment_status">' +
					'<option value="">—</option>' +
					['Enrolled','Dropped','Detained','Migrated'].map(function(o){ return '<option value="'+o+'" '+(es===o?'selected':'')+'>'+o+'</option>'; }).join('') +
					'</select>';
				var atHtml = '<select ' + ssAttrs + ' data-field="attendance_status">' +
					'<option value="">—</option>' +
					['Present','Absent','Detained','Attendance Shortage'].map(function(o){ return '<option value="'+o+'" '+(at===o?'selected':'')+'>'+o+'</option>'; }).join('') +
					'</select>';
				var mfaHtml = '<select ' + ssAttrs + ' data-field="mfa">' +
					['No','Yes'].map(function(o){ return '<option value="'+o+'" '+(mfa_v===o?'selected':'')+'>'+o+'</option>'; }).join('') +
					'</select>';
				cells += '<td class="er2-status-col" style="padding:4px 6px;">' + esHtml + '</td>' +
					'<td class="er2-status-col" style="padding:4px 6px;">' + atHtml + '</td>' +
					'<td class="er2-status-col" style="padding:4px 6px;">' + mfaHtml + '</td>';
			} else {
				cells += '<td class="er2-status-col">' + frappe.utils.escape_html(es || '—') + '</td>' +
					'<td class="er2-status-col">' + frappe.utils.escape_html(at || '—') + '</td>' +
					'<td class="er2-status-col">' + frappe.utils.escape_html(mfa_v || '—') + '</td>';
			}

			cells += '<td class="er2-status-col" style="text-align:center;">' + sg + '</td>' +
				'<td class="er2-status-col er2-remark-cell" style="text-align:left;min-width:140px;">' +
				'<textarea class="er2-remark-input" data-student="' + frappe.utils.escape_html(s.student) + '" ' +
				'placeholder="Add remarks" style="width:100%;font-size:11px;border:1px solid #dee2e6;' +
				'border-radius:3px;padding:3px 5px;resize:vertical;min-height:36px;background:#fff;" ' + (canEdit ? '':'readonly') + '>' +
				rmk + '</textarea>' +
				(canEdit ? '<span class="er2-remark-save" data-student="' + frappe.utils.escape_html(s.student) + '" ' +
				'style="font-size:10px;color:#920C24;cursor:pointer;display:none;">&#9998; Save</span>' : '') +
				'</td>';

			// Notes cell — explains arrear/MFA override situation
			var notesTxt = '';
			if (sm.arrear_marker && sm.arrear_marker !== 'I' && sm.mfa === 'Yes') {
				notesTxt = 'Arrear (' + frappe.utils.escape_html(sm.arrear_marker) + ') exists; MFA applied';
			} else if (sm.arrear_marker && sm.arrear_marker !== 'I') {
				notesTxt = 'Arrear (' + frappe.utils.escape_html(sm.arrear_marker) + ') pending';
			}
			cells += '<td class="er2-status-col" style="text-align:left;min-width:160px;font-size:11px;color:' +
				(sm.arrear_marker && sm.arrear_marker !== 'I' && sm.mfa === 'Yes' ? '#6E091B' : (sm.arrear_marker && sm.arrear_marker !== 'I') ? '#6E091B' : '#64748b') + ';' +
				(sm.arrear_marker && sm.arrear_marker !== 'I' && sm.mfa === 'Yes' ? 'background:#F5D9DE;' : (sm.arrear_marker && sm.arrear_marker !== 'I') ? 'background:#FBEEF0;' : '') +
				'">' + notesTxt + '</td>';

			// Re-Exam cells
			reexam_cols.forEach(function (col) {
				var key  = (col.component || '') + '|' + (col.assessment_type || '');
				var e    = entries[key] || {};
				var mVal = e.marks != null ? parseFloat(e.marks).toFixed(2) : '';
				var comp = frappe.utils.escape_html(col.component       || '');
				var atyp = frappe.utils.escape_html(col.assessment_type || '');
				var stu  = frappe.utils.escape_html(s.student);
				if (canEdit) {
					cells +=
						'<td style="padding:4px 6px;"><input type="number" step="0.01" min="0" class="er2-mi" ' +
						'data-student="' + stu + '" data-comp="' + comp + '" data-atype="' + atyp + '" data-field="marks" ' +
						'value="' + frappe.utils.escape_html(mVal) + '" placeholder="—" ' +
						'style="width:70px;height:26px;border:1.5px solid #F5D9DE;border-radius:6px;padding:0 6px;font-size:12px;font-weight:600;text-align:center;outline:none;"></td>';
				} else {
					cells += '<td>' + (mVal || '—') + '</td>';
				}
			});

			// Re-Exam Grade — read-only, computed server-side alongside Updated Grade
			if (reexam_cols.length) {
				var rxGradeVal = sm.re_exam_grade || '';
				cells += '<td style="padding:4px 6px;text-align:center;" class="er2-rxg-cell" data-student="' +
					frappe.utils.escape_html(s.student) + '">' +
					'<span class="er2-rxg-box">' + frappe.utils.escape_html(rxGradeVal || '—') + '</span>' +
					improvedStr +
					'</td>';
			}

			var stu_ug  = frappe.utils.escape_html(s.student);

			// Improvement Exam cells (before Updated Final Result)
			var impMarksVal = sm.improvement_marks != null ? parseFloat(sm.improvement_marks).toFixed(2) : '';
			var impGradeVal = sm.improvement_grade || '';
			var impApplied  = sm.improvement_applied;
			var impStr = impApplied ? ' <sup class="er2-ann-badge er2-improv-badge">I</sup>' : '';
			if (canEdit) {
				cells += '<td style="padding:4px 6px;text-align:center;" class="er2-imp-marks-cell" data-student="' + stu_ug + '">' +
					'<input type="number" step="0.01" min="0" class="er2-imp-mi" data-student="' + stu_ug + '" ' +
					'value="' + frappe.utils.escape_html(impMarksVal) + '" placeholder="—" ' +
					'style="width:70px;height:26px;border:1.5px solid #E8B4BE;border-radius:6px;padding:0 6px;font-size:12px;font-weight:600;text-align:center;outline:none;color:#920C24;">' +
					'</td>';
				cells += '<td style="padding:4px 6px;font-weight:700;text-align:center;color:#6E091B;" class="er2-imp-grade-cell" data-student="' + stu_ug + '">' +
					frappe.utils.escape_html(impGradeVal || '—') + impStr +
					'</td>';
			} else {
				cells += '<td style="font-weight:700;text-align:center;color:#920C24;">' + frappe.utils.escape_html(impMarksVal || '—') + '</td>';
				cells += '<td style="font-weight:700;text-align:center;color:#6E091B;">' + frappe.utils.escape_html(impGradeVal || '—') + impStr + '</td>';
			}

			// Updated Final Result
			var ufmVal  = sm.updated_final_marks != null ? parseFloat(sm.updated_final_marks).toFixed(2) : '—';
			// Fallback: if updated_grade not set yet, show regular grade;
			// attendance shortage replaces it outright with "AS" (see Grade column).
			var ugRaw   = isAS ? 'AS' : (sm.updated_grade || sm.grade || '');
			var ugVal   = ugRaw || '—';
			cells += '<td style="font-weight:700;text-align:center;" class="er2-ufm-cell" data-student="' + stu_ug + '">' + frappe.utils.escape_html(ufmVal) + '</td>';
			if (canEdit) {
				cells += '<td style="padding:4px 6px;text-align:center;" class="er2-ug-cell" data-student="' + stu_ug + '">' +
					'<span style="white-space:nowrap;">' +
					'<input type="text" class="er2-ug-input" data-student="' + stu_ug + '" ' +
					'value="' + frappe.utils.escape_html(ugRaw) + '" placeholder="—" ' + (isAS ? 'readonly' : '') + ' ' +
					'style="width:60px;height:26px;border:1.5px solid #E8B4BE;border-radius:6px;padding:0 6px;font-size:12px;font-weight:700;text-align:center;outline:none;color:#6E091B;' + (isAS ? 'background:#FBEEF0;' : '') + '">' +
					mfaStr + arrearStr + impStr + improvedStr +
					'</span></td>';
			} else {
				cells += '<td style="font-weight:700;color:#6E091B;text-align:center;" class="er2-ug-cell" data-student="' + stu_ug + '">' + frappe.utils.escape_html(ugVal) + mfaStr + arrearStr + impStr + improvedStr + '</td>';
			}

			rows += '<tr class="er2-mrow" data-student="' + frappe.utils.escape_html(s.student) + '">' + cells + '</tr>';
		});

		if (!rows) {
			rows = '<tr><td colspan="' + total_cols + '" style="text-align:center;padding:40px;color:#adb5bd;">No students found.</td></tr>';
		}

		$mtable.html(
			'<table class="er2-rtable">' +
			'<thead>' +
			'<tr>' + th1 + '</tr>' +
			'<tr style="background:#fafbfc;">' + th2 + '</tr>' +
			'<tr style="background:#f4f5f7;">' + th3 + '</tr>' +
			'</thead>' +
			'<tbody>' + rows + '</tbody>' +
			'</table>'
		);

		// ── Inline marks entry ─────────────────────────────────────────────────
		$mtable.find('.er2-mi').on('focus', function () {
			$(this).css('border-color', '#920C24');
		}).on('blur', function () {
			var $self = $(this);
			var defaultBorder = $self.data('field') === 'revaluation_marks' && $self.data('is-project') ? '#F5D9DE' : '#e2e8f0';
			$self.css('border-color', defaultBorder);
		}).on('change', function () {
			var $inp    = $(this);
			var student = $inp.data('student');
			var comp    = $inp.data('comp')  || '';
			var atype   = $inp.data('atype') || '';
			var field   = $inp.data('field');
			var val     = $inp.val().trim();
			var $tr     = $mtable.find('tr[data-student="' + student + '"]');
			var key     = student + field + comp + atype;

			// Live-update Project sub-column Total Marks = Marks − Deduction
			if ($inp.data('is-project')) {
				var $mInp  = $tr.find('.er2-mi[data-comp="' + comp + '"][data-atype="' + atype + '"][data-field="marks"]');
				var $dInp  = $tr.find('.er2-mi[data-comp="' + comp + '"][data-atype="' + atype + '"][data-field="revaluation_marks"]');
				var mNum   = parseFloat($mInp.val()) || 0;
				var dNum   = parseFloat($dInp.val()) || 0;
				// Deduction cannot exceed marks — cap and warn
				if (dNum > mNum) {
					$dInp.val(mNum.toFixed(2));
					$dInp.css('border-color', '#920C24');
					frappe.show_alert({ message: 'Deduction cannot exceed Marks (' + mNum.toFixed(2) + '). Capped automatically.', indicator: 'orange' });
					dNum = mNum;
					// Restore border after 2 s
					setTimeout(function () { $dInp.css('border-color', '#F5D9DE'); }, 2000);
				}
				var pTotal = (mNum - dNum).toFixed(2);
				$tr.find('.er2-proj-total-cell[data-comp="' + comp + '"][data-atype="' + atype + '"]').text(pTotal);
			}

			// Yellow flash while pending
			$tr.css('background', '#FBEEF0');
			clearTimeout(_saveTimer[key]);

			// Store the save function so we can flush it immediately on demand
			_pendingSaveFns[key] = function () {
				delete _saveTimer[key];
				delete _pendingSaveFns[key];
				return new Promise(function (resolve) {
					frappe.call({
						method: 'slcm.slcm.page.examination_result.examination_result.save_marks',
						args: {
							course:          S.course,
							exam_plan:       S.info.exam_plan || '',
							student:         student,
							component:       comp,
							assessment_type: atype,
							marks_field:     field,
							value:           val === '' ? null : parseFloat(val),
						},
						callback: function (r) {
							$tr.css('background', '');
							if (r.message) {
								var total = r.message.total;
								var grade = r.message.grade;
								var ufm = r.message.updated_final_marks;
								var ug = r.message.updated_grade;
								var sm_ref    = S.marks[student] || {};
								var isMFA2    = sm_ref.mfa === 'Yes';
								var isAS2     = !!sm_ref.attendance_shortage || sm_ref.attendance_status === 'Attendance Shortage';
								var mStr      = isMFA2 ? ' <sup class="er2-ann-badge er2-mfa-badge">MFA</sup>' : '';
								var arrStr    = (sm_ref.arrear_marker && sm_ref.arrear_marker !== 'I')
									? ' <sup class="er2-ann-badge er2-arrear-badge">' + frappe.utils.escape_html(sm_ref.arrear_marker) + '</sup>' : '';
								var impStrNew = (sm_ref.arrear_marker === 'I')
									? ' <sup class="er2-ann-badge er2-improved-badge">I</sup>' : '';
								// Attendance shortage replaces the grade text itself with "AS"
								// (rather than annotating it) — see render_marks_table().
								var gradeDisp = isAS2 ? 'AS' : (grade || '');
								// Update in-place
								$mtable.find('.er2-total-cell[data-student="' + student + '"]')
									.text(total != null ? parseFloat(total).toFixed(2) : '—');
								var $gc = $mtable.find('.er2-grade-cell[data-student="' + student + '"]');
								var $gi = $gc.find('.er2-grade-input');
								if ($gi.length) {
									$gi.val(gradeDisp);
									$gi.prop('readonly', isAS2);
									$gc.find('sup').remove();
									if (isMFA2) $gi.after('<sup class="er2-ann-badge er2-mfa-badge">MFA</sup>');
									if (sm_ref.arrear_marker && sm_ref.arrear_marker !== 'I') $gi.after('<sup class="er2-ann-badge er2-arrear-badge">' + frappe.utils.escape_html(sm_ref.arrear_marker) + '</sup>');
								} else {
									$gc.html(frappe.utils.escape_html(gradeDisp || '—') + mStr + arrStr);
								}
								$mtable.find('.er2-ufm-cell[data-student="' + student + '"]')
									.text(ufm != null ? parseFloat(ufm).toFixed(2) : '—');
								var $ugCell  = $mtable.find('.er2-ug-cell[data-student="' + student + '"]');
								var $ugInput = $ugCell.find('.er2-ug-input');
								var ugDisp   = isAS2 ? 'AS' : (ug || (S.marks[student] && S.marks[student].grade) || '');
								if ($ugInput.length) {
									$ugInput.val(ugDisp);
									$ugInput.prop('readonly', isAS2);
									$ugCell.find('sup').remove();
									if (isMFA2) $ugInput.after('<sup class="er2-ann-badge er2-mfa-badge">MFA</sup>');
									if (sm_ref.arrear_marker && sm_ref.arrear_marker !== 'I') $ugInput.after('<sup class="er2-ann-badge er2-arrear-badge">' + frappe.utils.escape_html(sm_ref.arrear_marker) + '</sup>');
								if (sm_ref.arrear_marker === 'I') $ugInput.after('<sup class="er2-ann-badge er2-improved-badge">I</sup>');
								} else {
									$ugCell.html(frappe.utils.escape_html(ugDisp || '—') + mStr + arrStr);
								}
								var rxGrade = r.message.re_exam_grade;
								var $rxgCell = $mtable.find('.er2-rxg-cell[data-student="' + student + '"]');
								$rxgCell.find('.er2-rxg-box').text(rxGrade || '—');
								$rxgCell.find('.er2-improved-badge').remove();
								if (sm_ref.arrear_marker === 'I') {
									$rxgCell.append(impStrNew);
								}
								// Update state
								if (!S.marks[student]) S.marks[student] = { entries: {} };
								if (!S.marks[student].entries) S.marks[student].entries = {};
								// Update the raw entry value so render_marks_table() shows correct data after re-render
								var entryKey = (comp || '') + '|' + (atype || '');
								if (!S.marks[student].entries[entryKey]) S.marks[student].entries[entryKey] = {};
								S.marks[student].entries[entryKey][field] = val === '' ? null : parseFloat(val);
								S.marks[student].total = total;
								S.marks[student].grade = grade;
								S.marks[student].updated_final_marks = ufm;
								S.marks[student].updated_grade = ug;
								S.marks[student].re_exam_grade = rxGrade;
								// Refresh stats bar
								load_stats();
							}
							resolve();
						},
						error: function () {
							$tr.css('background', '#FBEEF0');
							resolve();
						},
					});
				});
			};

			_saveTimer[key] = setTimeout(function () {
				if (_pendingSaveFns[key]) _pendingSaveFns[key]();
			}, 500);
		});

		// ── Inline Status Update ────────────────────────────────────────────────
		$mtable.find('.er2-ss').on('change', function () {
			var $select = $(this);
			var student = $select.data('student');
			var field   = $select.data('field');
			var val     = $select.val();
			var $tr     = $mtable.find('tr[data-student="' + student + '"]');

			$tr.css('background', '#FBEEF0');
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.save_status',
				args: {
					course:    S.course,
					exam_plan: S.info.exam_plan || '',
					student:   student,
					field:     field,
					value:     val
				},
				callback: function (r) {
					$tr.css('background', '');
					if (r.message && !r.exc) {
						if (!S.marks[student]) S.marks[student] = {};
						S.marks[student][field] = val;
						frappe.show_alert({ message: 'Status updated', indicator: 'green' });
						if (field === 'attendance_status') {
							// Absent/un-absent changes affect marks display — full re-render
							if (val === 'Absent') {
								S.marks[student].grade = 'Ab';
								S.marks[student].total = null;
							}
							render_marks_table();
						} else if (field === 'mfa') {
							var isMFA  = S.marks[student].mfa === 'Yes';
							var isAS   = !!S.marks[student].attendance_shortage || S.marks[student].attendance_status === 'Attendance Shortage';
							var arrMk  = S.marks[student].arrear_marker || '';
							var mStr   = isMFA  ? ' <sup class="er2-ann-badge er2-mfa-badge">MFA</sup>' : '';
							var arStr  = (arrMk && arrMk !== 'I') ? ' <sup class="er2-ann-badge er2-arrear-badge">' + frappe.utils.escape_html(arrMk) + '</sup>' : '';
							var impStrN2 = (arrMk === 'I') ? ' <sup class="er2-ann-badge er2-improved-badge">I</sup>' : '';
							var tg    = isAS ? 'AS' : (S.marks[student].grade || '—');
							var ug    = isAS ? 'AS' : (S.marks[student].updated_grade || '—');
							var $gc2  = $tr.find('.er2-grade-cell');
							var $gi2  = $gc2.find('.er2-grade-input');
							if ($gi2.length) {
								$gi2.val(tg);
								$gi2.prop('readonly', isAS);
								$gc2.find('sup').remove();
								if (isMFA) $gi2.after('<sup class="er2-ann-badge er2-mfa-badge">MFA</sup>');
								if (arrMk && arrMk !== 'I') $gi2.after('<sup class="er2-ann-badge er2-arrear-badge">' + frappe.utils.escape_html(arrMk) + '</sup>');
							} else {
								$gc2.html(frappe.utils.escape_html(tg) + mStr + arStr);
							}
							var $ugC = $tr.find('.er2-ug-cell');
							var $ugI = $ugC.find('.er2-ug-input');
							if ($ugI.length) {
								$ugI.val(ug);
								$ugI.prop('readonly', isAS);
								$ugC.find('sup').remove();
								if (isMFA) $ugI.after('<sup class="er2-ann-badge er2-mfa-badge">MFA</sup>');
								if (arrMk && arrMk !== 'I') $ugI.after('<sup class="er2-ann-badge er2-arrear-badge">' + frappe.utils.escape_html(arrMk) + '</sup>');
								if (arrMk === 'I') $ugI.after('<sup class="er2-ann-badge er2-improved-badge">I</sup>');
							} else {
								$ugC.html(frappe.utils.escape_html(ug) + mStr + arStr);
							}
						}
					}
				},
				error: function() {
					$tr.css('background', '#FBEEF0');
				}
			});
		});

		// ── Improvement Marks entry ────────────────────────────────────────────
		$mtable.find('.er2-imp-mi').on('change', function () {
			var $inp    = $(this);
			var student = $inp.data('student');
			var val     = $inp.val().trim();
			var $tr     = $mtable.find('tr[data-student="' + student + '"]');
			$tr.css('background', '#FBEEF0');
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.save_improvement_marks',
				args: {
					course:            S.course,
					exam_plan:         S.info.exam_plan || '',
					student:           student,
					improvement_marks: val === '' ? null : parseFloat(val),
				},
				callback: function (r) {
					$tr.css('background', '');
					if (r.message) {
						var impGrade   = r.message.improvement_grade || '';
						var impApplied = r.message.improvement_applied;
						var impBadge   = impApplied ? ' <sup class="er2-ann-badge er2-improv-badge">I</sup>' : '';
						$mtable.find('.er2-imp-grade-cell[data-student="' + student + '"]')
							.html(frappe.utils.escape_html(impGrade || '—') + impBadge);

						// Update Updated Final Marks & Grade cells if improvement was applied
						if (impApplied) {
							var ufm = r.message.updated_final_marks != null
								? parseFloat(r.message.updated_final_marks).toFixed(2) : '—';
							var ug  = r.message.updated_grade || '—';
							$mtable.find('.er2-ufm-cell[data-student="' + student + '"]')
								.text(ufm);
							var $ugCell = $mtable.find('.er2-ug-cell[data-student="' + student + '"]');
							var $ugInput = $ugCell.find('.er2-ug-input');
							// Remove any existing improv badge from the ug cell before re-adding
							$ugCell.find('.er2-improv-badge').remove();
							if ($ugInput.length) {
								$ugInput.val(r.message.updated_grade || '');
								if (impApplied) {
									$ugInput.closest('span').append(impBadge);
								}
							} else {
								// read-only cell — preserve other badges, update text node
								$ugCell.contents().filter(function () {
									return this.nodeType === 3;
								}).first().replaceWith(frappe.utils.escape_html(ug));
								if (impApplied) {
									$ugCell.append(impBadge);
								}
							}
						}

						if (!S.marks[student]) S.marks[student] = {};
						S.marks[student].improvement_grade    = impGrade;
						S.marks[student].improvement_applied  = impApplied;
						S.marks[student].improvement_marks    = val === '' ? null : parseFloat(val);
						S.marks[student].updated_final_marks  = r.message.updated_final_marks;
						S.marks[student].updated_grade        = r.message.updated_grade || '';
						frappe.show_alert({ message: 'Improvement marks saved.', indicator: 'green' }, 2);
					}
				},
				error: function () { $tr.css('background', '#FBEEF0'); },
			});
		});

		// ── Arrear badge click → repeat exam dialog ───────────────────────────
		$mtable.on('click', '.er2-arrear-badge', function () {
			var $badge  = $(this);
			var $td     = $badge.closest('td[data-student]');
			var student = $td.data('student') || '';
			var sm      = S.marks[student] || {};
			var sInfo   = (S.students || []).find(function(s){ return s.student === student; }) || {};
			var marker  = sm.arrear_marker || $badge.text().trim();
			var sName   = (sInfo.student_name || student);
			var course  = S.course || '';
			var examPlan = S.exam_plan || '';

			// Populate dialog header
			document.getElementById('rp-dialog-title').textContent =
				sName + ' — Arrear ' + marker;
			document.getElementById('rp-dialog-sub').textContent =
				'Course: ' + (S.info && S.info.course_name || course) + ' | Current grade: ' + (sm.updated_grade || sm.grade || '—');

			// Load exam plans into select (exclude current)
			var $sel = $('#rp-exam-plan-select');
			$sel.html('<option value="">Loading…</option>');
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.get_exam_plans',
				args: {},
				callback: function(r) {
					var opts = '<option value="">— Select target Exam Plan —</option>';
					(r.message || []).forEach(function(ep) {
						if (ep.name !== examPlan) {
							opts += '<option value="' + frappe.utils.escape_html(ep.name) + '">'
								+ frappe.utils.escape_html(ep.exam_name || ep.name) + '</option>';
						}
					});
					$sel.html(opts);
				}
			});

			// Reset status
			var $msg = document.getElementById('rp-status-msg');
			$msg.style.display = 'none';
			$msg.className = 'rp-status-msg';

			// Enroll button
			var $btn = document.getElementById('rp-enroll-btn');
			$btn.disabled = false;
			$btn.textContent = 'Enroll & Open';
			$btn.onclick = function() {
				var tgtPlan = $sel.val();
				if (!tgtPlan) { frappe.show_alert({message:'Please select a target Exam Plan', indicator:'orange'}); return; }
				$btn.disabled = true;
				$btn.textContent = 'Enrolling…';
				frappe.call({
					method: 'slcm.slcm.page.examination_result.examination_result.setup_repeat_exam_marks',
					args: { student: student, course: course, source_exam_plan: examPlan, target_exam_plan: tgtPlan },
					callback: function(r) {
						var d = r && r.message;
						$btn.disabled = false;
						$btn.textContent = 'Enroll & Open';
						if (d) {
							var status = d.status === 'existing' ? 'Already enrolled' : 'Enrolled successfully';
							$msg.textContent = status + ' in the selected exam plan. Navigate to that plan to enter marks.';
							$msg.className = 'rp-status-msg success';
							$msg.style.display = 'block';
						}
					},
					error: function(err) {
						$btn.disabled = false;
						$btn.textContent = 'Enroll & Open';
						$msg.textContent = 'Error: ' + (err || 'Could not enroll. Please try again.');
						$msg.className = 'rp-status-msg error';
						$msg.style.display = 'block';
					}
				});
			};

			document.getElementById('er2-repeat-overlay').style.display = 'flex';
		});

		// ── Inline Grade Edit ──────────────────────────────────────────────────
		$mtable.find('.er2-grade-input').on('focus', function () {
			$(this).css('border-color', '#920C24');
		}).on('blur', function () {
			$(this).css('border-color', '#E8B4BE');
		}).on('change', function () {
			var $inp    = $(this);
			var student = $inp.data('student');
			var val     = $inp.val().trim();
			var $tr     = $mtable.find('tr[data-student="' + student + '"]');
			$tr.css('background', '#FBEEF0');
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.save_status',
				args: {
					course:    S.course,
					exam_plan: S.info.exam_plan || '',
					student:   student,
					field:     'grade',
					value:     val,
				},
				callback: function (r) {
					$tr.css('background', '');
					if (r.message) {
						if (!S.marks[student]) S.marks[student] = {};
						S.marks[student].grade = val;
						frappe.show_alert({ message: 'Grade updated', indicator: 'green' });
					}
				},
				error: function () {
					$tr.css('background', '#FBEEF0');
					frappe.show_alert({ message: 'Failed to save grade', indicator: 'red' });
				},
			});
		});

		// ── Inline Updated Grade Edit ─────────────────────────────────────────────
		$mtable.find('.er2-ug-input').on('focus', function () {
			$(this).css('border-color', '#920C24');
		}).on('blur', function () {
			$(this).css('border-color', '#E8B4BE');
		}).on('change', function () {
			var $inp    = $(this);
			var student = $inp.data('student');
			var val     = $inp.val().trim();
			var $tr     = $mtable.find('tr[data-student="' + student + '"]');
			$tr.css('background', '#FBEEF0');
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.save_status',
				args: {
					course:    S.course,
					exam_plan: S.info.exam_plan || '',
					student:   student,
					field:     'updated_grade',
					value:     val,
				},
				callback: function (r) {
					$tr.css('background', '');
					if (r.message) {
						if (!S.marks[student]) S.marks[student] = {};
						S.marks[student].updated_grade = val;
						frappe.show_alert({ message: 'Updated Grade saved', indicator: 'green' });
					}
				},
				error: function () {
					$tr.css('background', '#FBEEF0');
					frappe.show_alert({ message: 'Failed to save updated grade', indicator: 'red' });
				},
			});
		});

		// Remarks: show save button on typing
		$mtable.find('.er2-remark-input').on('input', function () {
			$(this).siblings('.er2-remark-save').show();
		});
		$mtable.find('.er2-remark-save').on('click', function () {
			var student = $(this).data('student');
			var $inp    = $(this).siblings('.er2-remark-input');
			var remark  = $inp.val();
			var $btn    = $(this);
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.save_student_remark',
				args: {
					course:    S.course,
					exam_plan: S.info.exam_plan || '',
					student:   student,
					remark:    remark,
				},
				callback: function () {
					$btn.hide();
					frappe.show_alert({ message: 'Remark saved.', indicator: 'green' });
				},
			});
		});

		// ── Sync student-list top offset with marks thead height ──────────────────
		// After the table renders (with sticky 3-row thead), measure the total
		// non-scrollable header area in both panels and add a spacer so that
		// student row[i] aligns pixel-perfectly with marks data row[i].
		setTimeout(function () {
			var $thead   = $mtable.find('table thead');
			var theadH   = $thead.length ? $thead.outerHeight(true) : 0;
			var lhdrH    = $left.find('.er2-lhdr').outerHeight(true)      || 0;
			var stbarH   = $left.find('.er2-status-bar').outerHeight(true) || 0;
			var leftHdrH = lhdrH + stbarH;
			var spacerH  = Math.max(0, theadH - leftHdrH);
			$slist.find('.er2-align-spacer').remove();
			if (spacerH > 0) {
				$slist.prepend(
					'<div class="er2-align-spacer" style="height:' + spacerH + 'px;flex-shrink:0;"></div>'
				);
			}
		}, 30);
	}

	function update_pagination() {
		var from     = S.total ? (S.page - 1) * S.page_length + 1 : 0;
		var to       = Math.min(S.page * S.page_length, S.total);
		var totalPgs = S.total ? Math.ceil(S.total / S.page_length) : 1;
		if (S.total) {
			$pagInfo.html(
				from + '&ndash;' + to + ' of <strong>' + S.total + '</strong>' +
				(totalPgs > 1 ? ' &nbsp;(Page ' + S.page + '/' + totalPgs + ')' : '')
			);
		} else {
			$pagInfo.text('0 students');
		}
		$prevBtn.prop('disabled', S.page <= 1);
		$nextBtn.prop('disabled', to >= S.total);
	}

	// ── Hover popup ───────────────────────────────────────────────────────────
	function bind_hover() {
		$slist.find('.er2-srow')
			.on('mouseenter', function (e) {
				var student = $(this).data('student');
				clearTimeout(S.popup_timer);
				S.popup_student = student;
				S.popup_timer = setTimeout(function () {
					show_popup(student, e.clientX, e.clientY);
				}, 300);
			})
			.on('mouseleave', function () {
				clearTimeout(S.popup_timer);
				$popup.hide();
			})
			.on('mousemove', function (e) {
				position_popup(e.clientX, e.clientY);
			});
	}

	function position_popup(x, y) {
		var pw  = $popup.outerWidth(true)  || 340;
		var ph  = $popup.outerHeight(true) || 200;
		var vw  = window.innerWidth;
		var vh  = window.innerHeight;
		var left = (x + pw + 20 > vw) ? x - pw - 10 : x + 16;
		var top  = (y + ph + 10 > vh) ? y - ph - 10 : y + 8;
		left = Math.max(8, Math.min(left, vw - pw - 8));
		top  = Math.max(8, top);
		$popup.css({ top: top, left: left });
	}

	function show_popup(student, x, y) {
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.get_student_hover_info',
			args: { student: student, course: S.course },
			callback: function (r) {
				var s = r.message || {};
				if (S.popup_student !== student) return; // stale

				function prow(lbl, val) {
					if (!val && val !== 0) return '';
					return '<div class="er2-pop-row">' +
						'<span class="er2-pop-lbl">' + lbl + '</span>' +
						'<span class="er2-pop-val">' + frappe.utils.escape_html(String(val)) + '</span>' +
						'</div>';
				}

				// ── Student info section ──
				var infoHtml =
					prow('Student ID',   s.registration_id) +
					prow('Programme',    s.programme) +
					prow('Batch',        s.batch) +
					prow('Term',         s.current_term) +
					prow('Section',      s.section);

				$popup.html(
					'<div class="er2-pop-head">' +
					'<div class="er2-pop-name">' + frappe.utils.escape_html(s.student_name || student) + '</div>' +
					'<div class="er2-pop-sub">' + frappe.utils.escape_html(s.registration_id || '') + '</div>' +
					'</div>' +
					'<div class="er2-pop-body">' + infoHtml + '</div>'
				);
				$popup.css('max-width', '340px');
				position_popup(x, y);
				$popup.show();
			},
		});
	}

	// ── Popup dialogs ────────────────────────────────────────────────────────
	function show_calc_settings_popup(evaluation_schema) {
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.get_calc_settings',
			args: { evaluation_schema: evaluation_schema },
			callback: function (r) {
				var s = r.message || {};
				var d = new frappe.ui.Dialog({
					title: 'Calculation Settings',
					fields: [
						{
							fieldname: 'calc_higher_revaluation',
							fieldtype: 'Check',
							label: 'Consider higher marks for an assessment between regular marks and revaluation marks',
							default: s.calc_higher_revaluation || 0,
						},
						{
							fieldname: 'calc_higher_makeup',
							fieldtype: 'Check',
							label: 'Consider higher marks for an assessment or component between regular evaluation marks and MakeUp Exams',
							default: s.calc_higher_makeup || 0,
						},
						{
							fieldname: 'calc_higher_reexam',
							fieldtype: 'Check',
							label: 'Consider higher marks for an assessment or component between regular evaluation marks and Re-Exam',
							default: s.calc_higher_reexam || 0,
						},
					],
					primary_action_label: 'Save',
					primary_action: function () {
						var vals = d.get_values();
						frappe.call({
							method: 'slcm.slcm.page.examination_result.examination_result.save_calc_settings',
							args: {
								evaluation_schema:     evaluation_schema,
								calc_higher_revaluation: vals.calc_higher_revaluation ? 1 : 0,
								calc_higher_makeup:    vals.calc_higher_makeup ? 1 : 0,
								calc_higher_reexam:    vals.calc_higher_reexam ? 1 : 0,
							},
							callback: function () {
								d.hide();
								frappe.show_alert({ message: 'Calculation settings saved.', indicator: 'green' });
							},
						});
					},
				});
				d.show();
			},
		});
	}

	function show_eval_schema_popup(name) {
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.get_evaluation_schema_details',
			args: { name: name },
			callback: function (r) {
				var s = r.message || {};
				var html = '<div style="font-size:13px;">';
				html += '<div style="margin-bottom:12px;"><b>' + frappe.utils.escape_html(s.schema_name || name) + '</b>';
				if (s.description) html += '<div style="color:#6c757d;margin-top:4px;">' + frappe.utils.escape_html(s.description) + '</div>';
				html += '</div>';
				html += '<div style="display:flex;gap:24px;margin-bottom:14px;">' +
					'<div><span style="color:#8d99ae;font-size:11px;text-transform:uppercase;">Total Marks</span><div style="font-size:15px;font-weight:700;">' + (s.total_marks || 0) + '</div></div>' +
					'<div><span style="color:#8d99ae;font-size:11px;text-transform:uppercase;">Passing Marks</span><div style="font-size:15px;font-weight:700;">' + (s.passing_marks || 0) + '</div></div>' +
					'</div>';
				if (s.components && s.components.length) {
					html += '<div style="font-weight:600;margin-bottom:6px;color:#333;font-size:12px;">Components</div>' +
						'<table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:14px;">' +
						'<thead><tr style="background:#f0f2f5;">' +
						'<th style="padding:6px 8px;text-align:left;border:1px solid #dee2e6;">Component</th>' +
						'<th style="padding:6px 8px;text-align:right;border:1px solid #dee2e6;">Max Marks</th>' +
						'<th style="padding:6px 8px;text-align:right;border:1px solid #dee2e6;">Weightage</th>' +
						'<th style="padding:6px 8px;text-align:right;border:1px solid #dee2e6;">Passing</th>' +
						'</tr></thead><tbody>';
					(s.components || []).forEach(function (c) {
						html += '<tr>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;">' + frappe.utils.escape_html(c.component_name || c.component) + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right;">' + (c.effective_max_marks || '—') + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right;">' + (c.weightage != null ? c.weightage + '%' : '—') + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right;">' + (c.passing_marks || '—') + '</td>' +
							'</tr>';
					});
					html += '</tbody></table>';
				}
				if (s.assessments && s.assessments.length) {
					html += '<div style="font-weight:600;margin-bottom:6px;color:#333;font-size:12px;">Assessment Configuration</div>' +
						'<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
						'<thead><tr style="background:#f0f2f5;">' +
						'<th style="padding:6px 8px;text-align:left;border:1px solid #dee2e6;">Component</th>' +
						'<th style="padding:6px 8px;text-align:left;border:1px solid #dee2e6;">Assessment Type</th>' +
						'<th style="padding:6px 8px;text-align:left;border:1px solid #dee2e6;">Label</th>' +
						'<th style="padding:6px 8px;text-align:right;border:1px solid #dee2e6;">Max Marks</th>' +
						'<th style="padding:6px 8px;text-align:right;border:1px solid #dee2e6;">Effective</th>' +
						'<th style="padding:6px 8px;text-align:center;border:1px solid #dee2e6;">Enrollment</th>' +
						'</tr></thead><tbody>';
					(s.assessments || []).forEach(function (a) {
						html += '<tr>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;">' + frappe.utils.escape_html(a.component_name || a.component || '') + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;">' + frappe.utils.escape_html(a.type_name || a.assessment_type || '') + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;">' + frappe.utils.escape_html(a.label || '') + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right;">' + (a.maximum_marks || '—') + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right;">' + (a.effective_marks || '—') + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;text-align:center;">' + frappe.utils.escape_html(a.enrollment || '') + '</td>' +
							'</tr>';
					});
					html += '</tbody></table>';
				}
				html += '</div>';
				var d = new frappe.ui.Dialog({
					title: 'Evaluation Schema: ' + frappe.utils.escape_html(name),
					fields: [{ fieldname: 'schema_html', fieldtype: 'HTML', options: html }],
				});
				d.show();
			},
		});
	}

	function show_grade_schema_popup(name) {
		frappe.call({
			method: 'slcm.slcm.page.examination_result.examination_result.get_grading_schema_details',
			args: { name: name },
			callback: function (r) {
				var s = r.message || {};
				var html = '<div style="font-size:13px;">';
				html += '<div style="margin-bottom:12px;"><b>' + frappe.utils.escape_html(s.schema_name || name) + '</b>';
				if (s.description) html += '<div style="color:#6c757d;margin-top:4px;">' + frappe.utils.escape_html(s.description) + '</div>';
				html += '</div>';
				html += '<div style="display:flex;gap:24px;margin-bottom:14px;">' +
					'<div><span style="color:#8d99ae;font-size:11px;text-transform:uppercase;">Max Marks</span><div style="font-size:15px;font-weight:700;">' + (s.maximum_marks || 0) + '</div></div>' +
					'<div><span style="color:#8d99ae;font-size:11px;text-transform:uppercase;">Type</span><div style="font-size:15px;font-weight:700;">' + frappe.utils.escape_html(s.grading_type || '') + '</div></div>' +
					'</div>';
				if (s.grades && s.grades.length) {
					html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
						'<thead><tr style="background:#f0f2f5;">' +
						'<th style="padding:6px 8px;text-align:left;border:1px solid #dee2e6;">Grade</th>' +
						'<th style="padding:6px 8px;text-align:left;border:1px solid #dee2e6;">Meaning</th>' +
						'<th style="padding:6px 8px;text-align:center;border:1px solid #dee2e6;">Range</th>' +
						'<th style="padding:6px 8px;text-align:right;border:1px solid #dee2e6;">Grade Point</th>' +
						'<th style="padding:6px 8px;text-align:center;border:1px solid #dee2e6;">Failed</th>' +
						'<th style="padding:6px 8px;text-align:center;border:1px solid #dee2e6;">For SGPA</th>' +
						'</tr></thead><tbody>';
					(s.grades || []).forEach(function (g) {
						var range      = (g.from_operator || '>=') + ' ' + (g.marks_from || 0) + ' &amp; ' + (g.to_operator || '<') + ' ' + (g.marks_to || 0);
						var failedBadge = g.failed ? '<span style="color:#920C24;font-weight:600;">Yes</span>' : '<span style="color:#920C24;">No</span>';
						var sgpaBadge   = g.consider_for_sgpa ? '<span style="color:#28a745;">Yes</span>' : '<span style="color:#6c757d;">No</span>';
						html += '<tr>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;font-weight:700;">' + frappe.utils.escape_html(g.grade || '') + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;">' + frappe.utils.escape_html(g.qualitative_meaning || '') + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;text-align:center;">' + range + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right;">' + (g.grade_point || 0) + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;text-align:center;">' + failedBadge + '</td>' +
							'<td style="padding:5px 8px;border:1px solid #dee2e6;text-align:center;">' + sgpaBadge + '</td>' +
							'</tr>';
					});
					html += '</tbody></table>';
				}
				html += '</div>';
				var d = new frappe.ui.Dialog({
					title: 'Grading Schema: ' + frappe.utils.escape_html(name),
					fields: [{ fieldname: 'schema_html', fieldtype: 'HTML', options: html }],
				});
				d.show();
			},
		});
	}

	// ── Institutional Filter Dialog ───────────────────────────────────────────
	function show_inst_filter_dialog(opts) {
		// Working copy of selections (deep copy)
		var sel = {
			programmes:   S.inst_filter.programmes.slice(),
			batches:      S.inst_filter.batches.slice(),
			course_types: S.inst_filter.course_types.slice(),
		};

		var TYPES = [
			{ key: 'programmes',   label: 'Programme',
			  icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
			  items: opts.programmes },
			{ key: 'batches',      label: 'Batch',
			  icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
			  items: opts.batches },
			{ key: 'course_types', label: 'Course Type',
			  icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
			  items: opts.course_types },
		];

		var activeType = 0;

		function count_all() {
			return sel.programmes.length + sel.batches.length + sel.course_types.length;
		}

		function render_types() {
			var html = '';
			TYPES.forEach(function (t, i) {
				var cnt = sel[t.key].length;
				html += '<div class="xif-type' + (i === activeType ? ' active' : '') + '" data-idx="' + i + '">' +
					t.icon + ' ' + t.label +
					(cnt ? '<span class="xif-type-badge">' + cnt + '</span>' : '') +
					'</div>';
			});
			$modal.find('.xif-types').html(html);
			$modal.find('.xif-type').on('click', function () {
				activeType = parseInt($(this).data('idx'));
				render_types();
				render_panel();
			});
		}

		function render_panel(search_val) {
			var t     = TYPES[activeType];
			var items = (t.items || []).filter(function (v) {
				return !search_val || String(v).toLowerCase().includes(search_val.toLowerCase());
			});
			$modal.find('.xif-ph-title').text(t.label);
			var html = '';
			if (!items.length) {
				html = '<div class="xif-empty-opts">No options available</div>';
			} else {
				items.forEach(function (v) {
					var checked = sel[t.key].indexOf(String(v)) !== -1;
					html += '<div class="xif-opt' + (checked ? ' checked' : '') + '" data-val="' + frappe.utils.escape_html(String(v)) + '">' +
						'<input type="checkbox"' + (checked ? ' checked' : '') + '>' +
						'<span>' + frappe.utils.escape_html(String(v)) + '</span>' +
						'</div>';
				});
			}
			$modal.find('.xif-opts').html(html);
			$modal.find('.xif-opt').on('click', function (e) {
				e.preventDefault();
				var val = $(this).data('val');
				var key = TYPES[activeType].key;
				var idx = sel[key].indexOf(String(val));
				if (idx === -1) sel[key].push(String(val));
				else            sel[key].splice(idx, 1);
				render_types();
				render_panel($modal.find('.xif-search').val());
				update_footer();
			});
		}

		function update_footer() {
			var total = count_all();
			var parts = [];
			if (sel.programmes.length)   parts.push(sel.programmes.length + ' Programme(s)');
			if (sel.batches.length)      parts.push(sel.batches.length + ' Batch(es)');
			if (sel.course_types.length) parts.push(sel.course_types.length + ' Course Type(s)');
			$modal.find('.xif-status').html(
				total ? '<strong>' + total + ' filter' + (total > 1 ? 's' : '') + '</strong> selected: ' + parts.join(', ')
				      : 'No Filters Applied'
			);
		}

		// Build modal HTML
		var $overlay = $('<div class="xif-overlay"></div>');
		var $modal = $(`
			<div class="xif-modal">
				<div class="xif-header">
					<span class="xif-title">
						<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2.5" style="vertical-align:-3px;margin-right:6px;"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
						Filter by
					</span>
					<button class="xif-close">&#10005;</button>
				</div>
				<div class="xif-body">
					<div class="xif-types"></div>
					<div class="xif-panel">
						<div class="xif-ph">
							<div class="xif-ph-title"></div>
							<input class="xif-search" type="text" placeholder="Search…">
						</div>
						<div class="xif-opts"></div>
					</div>
				</div>
				<div class="xif-footer">
					<span class="xif-status">No Filters Applied</span>
					<div class="xif-actions">
						<button class="xif-clear">Clear All</button>
						<button class="xif-apply">Apply</button>
					</div>
				</div>
			</div>
		`);

		$overlay.append($modal);
		$('body').append($overlay);

		render_types();
		render_panel();
		update_footer();

		// Search
		$modal.find('.xif-search').on('input', function () {
			render_panel($(this).val());
		});

		// Clear all
		$modal.find('.xif-clear').on('click', function () {
			sel.programmes   = [];
			sel.batches      = [];
			sel.course_types = [];
			render_types();
			render_panel($modal.find('.xif-search').val());
			update_footer();
		});

		// Apply
		$modal.find('.xif-apply').on('click', function () {
			S.inst_filter = { programmes: sel.programmes, batches: sel.batches, course_types: sel.course_types };
			S.page = 1;
			// Update button badge
			var total = count_all();
			var $btn = $body.find('#er2-inst-filter');
			if (total) {
				$btn.addClass('xif-btn-active').find('.xif-count').remove();
				$btn.append('<span class="xif-count" style="background:#920C24;color:#fff;border-radius:20px;font-size:10px;font-weight:700;padding:1px 6px;margin-left:4px;">' + total + '</span>');
			} else {
				$btn.removeClass('xif-btn-active').find('.xif-count').remove();
			}
			$overlay.remove();
			load_students();
		});

		// Close
		$modal.find('.xif-close').on('click', function () { $overlay.remove(); });
		$overlay.on('click', function (e) {
			if ($(e.target).is($overlay)) $overlay.remove();
		});
	}

	// ── Add Student button ────────────────────────────────────────────────────
	function _xas_full_refresh() {
		// Reset any active stat-card / grade drilldown filters so the new student is visible
		S.page         = 1;
		S.pass_filter  = '';
		S.grade_filter = '';
		S.search       = '';
		$body.find('#er2-search').val('');
		$body.find('.er2-stat-card').removeClass('er2-sc-active');
		$body.find('.er2-gd-badge').removeClass('er2-gd-active');
		load_course_info(); // full refresh: updates info panel, student count, marks table
	}

	$body.find('#er2-add-student-btn').on('click', function () {
		if (!S.course || !S.info) {
			frappe.show_alert({ message: 'Select a course first.', indicator: 'orange' });
			return;
		}
		show_add_student_dialog();
	});

	function show_add_student_dialog() {
		var mode             = 'existing';
		var selected_students = {};
		var csv_students      = [];
		var search_timer      = null;
		var AV = ['av-0','av-1','av-2','av-3','av-4','av-5','av-6','av-7'];

		$('body').append(
			'<div class="xas-overlay" id="xas-overlay">' +
				'<div class="xas-modal">' +
					'<div class="xas-header">' +
						'<div style="display:flex;align-items:center;gap:10px;">' +
							'<div style="width:36px;height:36px;border-radius:9px;background:#920C24;display:flex;align-items:center;justify-content:center;flex-shrink:0;">' +
								'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>' +
							'</div>' +
							'<div>' +
								'<div class="xas-title">Add Student</div>' +
								'<div class="xas-sub">Add to <b>' + frappe.utils.escape_html(S.course) + '</b> &mdash; ' + frappe.utils.escape_html((S.info && S.info.exam_plan) || '') + '</div>' +
							'</div>' +
						'</div>' +
						'<button class="xas-close" id="xas-close">&times;</button>' +
					'</div>' +
					'<div class="xas-tabs">' +
						'<button class="xas-tab active" id="xas-tab-existing">' +
							'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>' +
							'From Existing Records' +
						'</button>' +
						'<button class="xas-tab" id="xas-tab-csv">' +
							'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>' +
							'Upload CSV' +
						'</button>' +
					'</div>' +
					// Existing Records panel
					'<div id="xas-panel-existing" class="xas-panel">' +
						'<div class="xas-search-bar">' +
							'<div class="xas-srch-wrap">' +
								'<svg style="position:absolute;left:10px;top:10px;pointer-events:none;" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>' +
								'<input id="xas-search" type="text" placeholder="Search by name or registration ID…" class="xas-sinput">' +
							'</div>' +
							'<select id="xas-prog-filter" class="xas-sselect"><option value="">All Programmes</option></select>' +
							'<select id="xas-batch-filter" class="xas-sselect"><option value="">All Batches</option></select>' +
						'</div>' +
						'<div id="xas-student-list" class="xas-list">' +
							'<div class="xas-loading"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>Loading…</div>' +
						'</div>' +
						'<div class="xas-footer">' +
							'<span class="xas-sel-count" id="xas-sel-count">0 selected</span>' +
							'<div style="display:flex;gap:8px;">' +
								'<button class="xas-cancel-btn" id="xas-cancel-existing">Cancel</button>' +
								'<button class="xas-add-btn" id="xas-do-add" disabled>' +
									'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>' +
									'Add Student(s)' +
								'</button>' +
							'</div>' +
						'</div>' +
					'</div>' +
					// Upload CSV panel
					'<div id="xas-panel-csv" class="xas-panel" style="display:none;">' +
						'<div class="xas-csv-body">' +
							'<div class="xas-csv-hint">' +
								'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2.5" style="flex-shrink:0;margin-top:1px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' +
								'Download the template, fill in the <b>Registration ID</b> for each student, then upload.' +
							'</div>' +
							'<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap;">' +
								'<button class="xas-dl-btn" id="xas-dl-template">' +
									'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
									'Download Template' +
								'</button>' +
								'<span style="font-size:12px;color:#94a3b8;">Columns: Registration ID, Student Name (optional)</span>' +
							'</div>' +
							'<div class="xas-drop-zone" id="xas-drop-zone">' +
								'<input type="file" id="xas-csv-input" accept=".csv" style="display:none;">' +
								'<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="1.8"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>' +
								'<div style="font-size:13px;font-weight:600;color:#475569;margin-top:6px;">Drop CSV here or <span style="color:#920C24;text-decoration:underline;cursor:pointer;">Browse file</span></div>' +
								'<div style="font-size:11px;color:#94a3b8;margin-top:3px;">Accepted: .csv — use the template above</div>' +
							'</div>' +
							'<div id="xas-csv-preview" style="display:none;margin-top:14px;">' +
								'<div id="xas-csv-info" style="font-size:12.5px;font-weight:700;color:#1e293b;margin-bottom:8px;display:flex;align-items:center;gap:6px;">' +
									'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>' +
									'<span id="xas-csv-info-txt"></span>' +
								'</div>' +
								'<div id="xas-csv-table-wrap" style="max-height:200px;overflow-y:auto;border:1.5px solid #e2e8f0;border-radius:8px;"></div>' +
							'</div>' +
						'</div>' +
						'<div class="xas-footer">' +
							'<span id="xas-csv-count" style="font-size:12.5px;color:#64748b;font-weight:600;"></span>' +
							'<div style="display:flex;gap:8px;">' +
								'<button class="xas-cancel-btn" id="xas-cancel-csv">Cancel</button>' +
								'<button class="xas-add-btn" id="xas-do-import" disabled>' +
									'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>' +
									'Import' +
								'</button>' +
							'</div>' +
						'</div>' +
					'</div>' +
				'</div>' +
			'</div>'
		);

		var $overlay = $('#xas-overlay');

		// ── Load filter options ──────────────────────────────────────────────────
		function load_filter_options() {
			var opts = S.inst_options;
			if (opts) { populate_filters(opts); return; }
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.get_institutional_filter_options',
				args: { course: S.course },
				callback: function (r) {
					S.inst_options = r.message || { programmes: [], batches: [] };
					populate_filters(S.inst_options);
				},
			});
		}
		function populate_filters(opts) {
			var $prog  = $overlay.find('#xas-prog-filter');
			var $batch = $overlay.find('#xas-batch-filter');
			(opts.programmes || []).forEach(function (p) {
				$prog.append('<option value="' + frappe.utils.escape_html(p) + '">' + frappe.utils.escape_html(p) + '</option>');
			});
			(opts.batches || []).forEach(function (b) {
				$batch.append('<option value="' + frappe.utils.escape_html(String(b)) + '">' + frappe.utils.escape_html(String(b)) + '</option>');
			});
		}

		// ── Fetch & render students ──────────────────────────────────────────────
		function load_existing_students(search_val, prog_val, batch_val) {
			$overlay.find('#xas-student-list').html(
				'<div class="xas-loading"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>Loading…</div>'
			);
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.search_students_for_add',
				args: {
					course:    S.course,
					exam_plan: S.info.exam_plan || '',
					search:    search_val || '',
					programme: prog_val   || '',
					batch:     batch_val  || '',
				},
				callback: function (r) { render_student_list(r.message || []); },
			});
		}

		function render_student_list(students) {
			if (!students.length) {
				$overlay.find('#xas-student-list').html(
					'<div class="xas-empty-list">No students found.<br><span style="font-size:11px;color:#cbd5e1;">They may already be enrolled in this course, or try a different filter.</span></div>'
				);
				return;
			}
			var html = students.map(function (s, i) {
				var initials = ((s.student_name || '').split(' ').map(function (w) { return w[0] || ''; }).join('').slice(0, 2)).toUpperCase() || '?';
				var avCls    = AV[i % 8];
				var avatar   = s.image
					? '<div style="width:34px;height:34px;border-radius:9px;overflow:hidden;flex-shrink:0;"><img src="' + frappe.utils.escape_html(s.image) + '" style="width:100%;height:100%;object-fit:cover;"></div>'
					: '<div class="' + avCls + '" style="width:34px;height:34px;border-radius:9px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;">' + frappe.utils.escape_html(initials) + '</div>';
				var meta = [s.registration_id, s.programme, s.batch_year ? String(s.batch_year) : ''].filter(Boolean).join(' · ');
				return '<label class="xas-student-row">' +
					'<input type="checkbox" class="xas-stchk" ' + (selected_students[s.student] ? 'checked' : '') +
					' data-student="' + frappe.utils.escape_html(s.student) + '"' +
					' data-sname="'  + frappe.utils.escape_html(s.student_name || '') + '"' +
					' data-regid="'  + frappe.utils.escape_html(s.registration_id || '') + '"' +
					' style="width:15px;height:15px;accent-color:#920C24;cursor:pointer;flex-shrink:0;">' +
					avatar +
					'<div style="flex:1;min-width:0;">' +
						'<div style="font-size:13px;font-weight:700;color:#0f172a;">' + frappe.utils.escape_html(s.student_name || '—') + '</div>' +
						'<div style="font-size:11px;color:#94a3b8;margin-top:1px;">' + frappe.utils.escape_html(meta) + '</div>' +
					'</div>' +
				'</label>';
			}).join('');
			$overlay.find('#xas-student-list').html(html);
			$overlay.find('.xas-stchk').on('change', function () {
				var st = $(this).data('student');
				if ($(this).prop('checked')) {
					selected_students[st] = { student: st, student_name: $(this).data('sname'), registration_id: $(this).data('regid') };
				} else {
					delete selected_students[st];
				}
				update_sel_count();
			});
		}
		function update_sel_count() {
			var cnt = Object.keys(selected_students).length;
			$overlay.find('#xas-sel-count').text(cnt + ' student' + (cnt !== 1 ? 's' : '') + ' selected');
			$overlay.find('#xas-do-add').prop('disabled', cnt === 0);
		}

		// ── Init existing panel ──────────────────────────────────────────────────
		load_filter_options();
		load_existing_students('', '', '');

		// Search + filter change
		$overlay.find('#xas-search').on('input', function () {
			clearTimeout(search_timer);
			var v = $(this).val();
			search_timer = setTimeout(function () {
				load_existing_students(v, $overlay.find('#xas-prog-filter').val(), $overlay.find('#xas-batch-filter').val());
			}, 350);
		});
		$overlay.find('#xas-prog-filter, #xas-batch-filter').on('change', function () {
			load_existing_students($overlay.find('#xas-search').val(), $overlay.find('#xas-prog-filter').val(), $overlay.find('#xas-batch-filter').val());
		});

		// ── Tabs ─────────────────────────────────────────────────────────────────
		$overlay.find('#xas-tab-existing').on('click', function () {
			mode = 'existing';
			$(this).addClass('active'); $overlay.find('#xas-tab-csv').removeClass('active');
			$overlay.find('#xas-panel-existing').show(); $overlay.find('#xas-panel-csv').hide();
		});
		$overlay.find('#xas-tab-csv').on('click', function () {
			mode = 'csv';
			$(this).addClass('active'); $overlay.find('#xas-tab-existing').removeClass('active');
			$overlay.find('#xas-panel-csv').show(); $overlay.find('#xas-panel-existing').hide();
		});

		// ── Close ─────────────────────────────────────────────────────────────────
		function close_modal() { $overlay.remove(); }
		$overlay.find('#xas-close, #xas-cancel-existing, #xas-cancel-csv').on('click', close_modal);
		$overlay.on('click', function (e) { if ($(e.target).is($overlay)) close_modal(); });

		// ── Add from existing ─────────────────────────────────────────────────────
		$overlay.find('#xas-do-add').on('click', function () {
			var students = Object.keys(selected_students);
			if (!students.length) return;
			$(this).prop('disabled', true).text('Adding…');
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.add_students_to_course',
				args: {
					course:    S.course,
					exam_plan: S.info.exam_plan || '',
					students:  JSON.stringify(students),
				},
				callback: function (r) {
					var res = r.message || {};
					close_modal();
					frappe.show_alert({
						message: res.added + ' student(s) added' + (res.skipped ? ', ' + res.skipped + ' already existed.' : '.'),
						indicator: res.added > 0 ? 'green' : 'orange',
					}, 4);
					if (res.added > 0) { _xas_full_refresh(); }
				},
				error: function () {
					$overlay.find('#xas-do-add').prop('disabled', false).html('<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Add Student(s)');
				},
			});
		});

		// ── Download template ─────────────────────────────────────────────────────
		$overlay.find('#xas-dl-template').on('click', function () {
			var csv  = '"Registration ID","Student Name"\n"REG001","John Doe"\n"REG002","Jane Smith"\n';
			var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
			var url  = URL.createObjectURL(blob);
			var a    = document.createElement('a');
			a.href = url; a.download = 'add_student_template.csv';
			document.body.appendChild(a); a.click();
			document.body.removeChild(a); URL.revokeObjectURL(url);
		});

		// ── CSV drop / browse ─────────────────────────────────────────────────────
		$overlay.find('#xas-drop-zone').on('click', function () {
			document.getElementById('xas-csv-input').click();
		});
		$overlay.find('#xas-drop-zone').on('dragover', function (e) {
			e.preventDefault(); $(this).addClass('xas-dz-active');
		});
		$overlay.find('#xas-drop-zone').on('dragleave', function () {
			$(this).removeClass('xas-dz-active');
		});
		$overlay.find('#xas-drop-zone').on('drop', function (e) {
			e.preventDefault(); $(this).removeClass('xas-dz-active');
			var f = e.originalEvent.dataTransfer.files;
			if (f && f[0]) handle_csv_upload(f[0]);
		});
		$overlay.find('#xas-csv-input').on('change', function () {
			if (this.files && this.files[0]) handle_csv_upload(this.files[0]);
			this.value = '';
		});

		function handle_csv_upload(file) {
			if (!file.name.toLowerCase().endsWith('.csv')) {
				frappe.show_alert({ message: 'Please upload a .csv file.', indicator: 'red' }, 3);
				return;
			}
			var reader = new FileReader();
			reader.onload = function (e) {
				csv_students = xas_parse_csv(e.target.result);
				xas_render_preview(file.name, csv_students);
			};
			reader.readAsText(file);
		}

		function xas_parse_csv(text) {
			var lines = text.split(/\r?\n/).filter(function (l) { return l.trim(); });
			if (!lines.length) return [];
			var hdr = xas_parse_row(lines[0]).map(function (h) {
				return h.trim().toLowerCase().replace(/[\s._-]+/g, '_');
			});
			var ri = Math.max(hdr.indexOf('registration_id'), hdr.indexOf('reg_id'), hdr.indexOf('reg'));
			var ni = Math.max(hdr.indexOf('student_name'), hdr.indexOf('name'));
			var out = [];
			for (var i = 1; i < lines.length; i++) {
				var cols = xas_parse_row(lines[i]);
				if (!cols.length || cols.every(function (c) { return !c.trim(); })) continue;
				var reg = ri >= 0 ? (cols[ri] || '').trim() : '';
				if (!reg) continue;
				out.push({ registration_id: reg, student_name: ni >= 0 ? (cols[ni] || '').trim() : '' });
			}
			return out;
		}
		function xas_parse_row(line) {
			var result = [], curr = '', inQ = false;
			for (var i = 0; i < line.length; i++) {
				var ch = line[i];
				if (inQ) {
					if (ch === '"') { if (line[i+1] === '"') { curr += '"'; i++; } else inQ = false; }
					else curr += ch;
				} else {
					if (ch === '"') inQ = true;
					else if (ch === ',') { result.push(curr); curr = ''; }
					else curr += ch;
				}
			}
			result.push(curr);
			return result;
		}

		function xas_render_preview(filename, students) {
			if (!students.length) {
				frappe.show_alert({ message: 'No valid rows found. Check that the Registration ID column is present.', indicator: 'orange' }, 4);
				return;
			}
			$overlay.find('#xas-csv-info-txt').text(filename + ' — ' + students.length + ' student(s)');
			var rows = students.slice(0, 25).map(function (s, i) {
				return '<tr>' +
					'<td style="padding:5px 10px;border-bottom:1px solid #f1f5f9;font-size:11px;color:#94a3b8;text-align:center;">' + (i+1) + '</td>' +
					'<td style="padding:5px 10px;border-bottom:1px solid #f1f5f9;font-size:12px;font-weight:600;color:#1e293b;">' + frappe.utils.escape_html(s.registration_id) + '</td>' +
					'<td style="padding:5px 10px;border-bottom:1px solid #f1f5f9;font-size:12px;color:#475569;">' + frappe.utils.escape_html(s.student_name || '—') + '</td>' +
				'</tr>';
			}).join('');
			$overlay.find('#xas-csv-table-wrap').html(
				'<table style="width:100%;border-collapse:collapse;">' +
				'<thead><tr style="background:#f8fafc;">' +
					'<th style="padding:6px 10px;font-size:10px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;width:36px;">#</th>' +
					'<th style="padding:6px 10px;font-size:10px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-align:left;">REG. ID</th>' +
					'<th style="padding:6px 10px;font-size:10px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-align:left;">Name (from CSV)</th>' +
				'</tr></thead><tbody>' + rows + '</tbody></table>' +
				(students.length > 25 ? '<div style="text-align:center;font-size:11px;color:#94a3b8;padding:6px;">… and ' + (students.length - 25) + ' more</div>' : '')
			);
			$overlay.find('#xas-csv-preview').show();
			$overlay.find('#xas-csv-count').text(students.length + ' student(s) ready to import');
			$overlay.find('#xas-do-import').prop('disabled', false);
		}

		// ── Import from CSV ───────────────────────────────────────────────────────
		$overlay.find('#xas-do-import').on('click', function () {
			if (!csv_students.length) return;
			var reg_ids = csv_students.map(function (s) { return s.registration_id; });
			$(this).prop('disabled', true).text('Importing…');
			frappe.call({
				method: 'slcm.slcm.page.examination_result.examination_result.add_students_by_registration_ids',
				args: {
					course:           S.course,
					exam_plan:        S.info.exam_plan || '',
					registration_ids: JSON.stringify(reg_ids),
				},
				callback: function (r) {
					var res = r.message || {};
					close_modal();
					var msg = res.added + ' student(s) added';
					if (res.skipped)                           msg += ', ' + res.skipped + ' already existed';
					if (res.not_found && res.not_found.length) msg += ', ' + res.not_found.length + ' ID(s) not found: ' + res.not_found.slice(0, 5).join(', ');
					frappe.show_alert({ message: msg, indicator: res.added > 0 ? 'green' : 'orange' }, 5);
					if (res.added > 0) { _xas_full_refresh(); }
				},
				error: function () {
					$overlay.find('#xas-do-import').prop('disabled', false).text('Import');
				},
			});
		});
	}

	// ── Helpers ───────────────────────────────────────────────────────────────
	function hide_detail() {
		$info.hide().empty();
		$actbar.hide();
		$filterrow.hide();
		$statsPanel.hide().empty();
		$split.hide();
		$popup.hide();
		$empty.show();
		$body.find('#er2-add-student-btn').hide();
		S.students        = [];
		S.marks           = {};
		S.info            = null;
		S.columns         = [];
		S.reexam_columns  = [];
		S.failed_grades   = [];
	}

	// Close popup on outside click
	$(document).on('click.er2popup', function (e) {
		if (!$(e.target).closest('.er2-srow, #er2-popup').length) {
			$popup.hide();
		}
	});
};
