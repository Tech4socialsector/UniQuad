frappe.pages['improvement-exam'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Improvement Exam',
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

	if (!document.getElementById('ix-style')) {
		var style = document.createElement('style');
		style.id  = 'ix-style';
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

		.ix-filter-card  { background:#fff; border-radius:12px; padding:14px 20px; margin-bottom:14px;
		                   box-shadow:0 1px 3px rgba(0,0,0,.06); display:flex; gap:14px;
		                   align-items:flex-end; flex-wrap:wrap; }
		.ix-fgroup       { display:flex; flex-direction:column; min-width:200px; flex:1; max-width:300px; }
		.ix-fgroup.wide  { max-width:400px; }
		.ix-filter-arrow { display:flex; align-items:flex-end; padding-bottom:9px; color:#cbd5e1; font-size:16px; flex-shrink:0; }
		.ix-flabel       { font-size:11px; color:#94a3b8; font-weight:700; margin-bottom:5px;
		                   text-transform:uppercase; letter-spacing:.6px; }
		.ix-select       { height:36px; border:1.5px solid #e2e8f0; border-radius:8px;
		                   padding:0 12px; font-size:13px; background:#fff; color:#1e293b;
		                   outline:none; cursor:pointer; transition:border-color .2s; }
		.ix-select:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }

		.ix-stat-cards   { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
		.ix-stat-card    { background:#fff; border-radius:12px; padding:14px 18px; flex:1;
		                   min-width:150px; box-shadow:0 1px 3px rgba(0,0,0,.06);
		                   border-top:3px solid var(--sc-color,#920C24);
		                   display:flex; align-items:center; gap:12px; }
		.ix-sc-icon      { width:38px; height:38px; border-radius:9px; flex-shrink:0;
		                   display:flex; align-items:center; justify-content:center;
		                   background:var(--sc-bg,#FBEEF0); color:var(--sc-color,#920C24); }
		.ix-sc-val       { font-size:22px; font-weight:800; color:var(--sc-color,#920C24); line-height:1.1; }
		.ix-sc-lbl       { font-size:10px; color:#94a3b8; font-weight:700; text-transform:uppercase;
		                   letter-spacing:.6px; margin-top:2px; }

		.ix-settings-card { background:#fff; border-radius:12px; padding:18px 22px; margin-bottom:14px;
		                    box-shadow:0 1px 3px rgba(0,0,0,.06); border-left:4px solid #920C24; }
		.ix-settings-title { font-size:13px; font-weight:800; color:#0f172a; margin-bottom:14px;
		                     display:flex; align-items:center; gap:8px; }
		.ix-settings-grid  { display:flex; gap:14px; flex-wrap:wrap; align-items:flex-end; }
		.ix-field-group    { display:flex; flex-direction:column; min-width:180px; flex:1; max-width:260px; }
		.ix-field-label    { font-size:11px; color:#94a3b8; font-weight:700; margin-bottom:5px;
		                     text-transform:uppercase; letter-spacing:.6px; }
		.ix-input          { height:36px; border:1.5px solid #e2e8f0; border-radius:8px;
		                     padding:0 12px; font-size:13px; background:#fff; color:#1e293b;
		                     outline:none; transition:border-color .2s; width:100%; box-sizing:border-box; }
		.ix-input:focus    { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }
		.ix-save-btn       { height:36px; padding:0 20px; border-radius:8px; border:none;
		                     background:#920C24;
		                     color:#fff; font-size:13px; font-weight:700; cursor:pointer;
		                     display:inline-flex; align-items:center; gap:6px; transition:opacity .15s;
		                     white-space:nowrap; }
		.ix-save-btn:hover { opacity:.88; }
		.ix-save-btn:disabled { opacity:.5; cursor:default; }
		.ix-saved-badge    { display:inline-flex; align-items:center; gap:4px; font-size:11px;
		                     font-weight:700; color:#920C24; margin-left:10px;
		                     background:#F5D9DE; border-radius:6px; padding:3px 9px; }
		.ix-bulk-btn       { height:36px; padding:0 16px; border-radius:8px; border:1.5px solid #e2e8f0;
		                     background:#fff; color:#475569; font-size:12px; font-weight:700; cursor:pointer;
		                     display:inline-flex; align-items:center; gap:5px; transition:all .15s;
		                     white-space:nowrap; }
		.ix-bulk-btn:hover { border-color:#920C24; color:#920C24; background:#FBEEF0; }

		.ix-table-card    { background:#fff; border-radius:12px; box-shadow:0 1px 3px rgba(0,0,0,.06);
		                    overflow:hidden; border-top:3px solid #920C24; }
		.ix-table-topbar  { display:flex; align-items:center; justify-content:space-between;
		                    padding:12px 16px 10px; border-bottom:1.5px solid #f1f5f9; }
		.ix-count-lbl     { font-size:13px; font-weight:700; color:#0f172a; }
		.ix-srch          { position:relative; }
		.ix-srch input    { width:260px; height:34px; border:1.5px solid #e2e8f0; border-radius:8px;
		                    padding:0 12px 0 34px; font-size:13px; outline:none; color:#1e293b;
		                    background:#fff; transition:border-color .2s; box-sizing:border-box; }
		.ix-srch input:focus { border-color:#920C24; box-shadow:0 0 0 3px rgba(146,12,36,.1); }
		.ix-srch-ico      { position:absolute; left:10px; top:10px; color:#94a3b8; }

		.ix-tbl-scroll    { overflow-x:auto; }
		.ix-tbl           { width:100%; border-collapse:collapse; font-size:13px; min-width:700px; }
		.ix-tbl thead tr  { background:#f8fafc; }
		.ix-tbl th        { padding:10px 14px; text-align:left; font-size:11px; font-weight:700;
		                    color:#475569; border-bottom:2px solid #e2e8f0; white-space:nowrap;
		                    text-transform:uppercase; letter-spacing:.5px; }
		.ix-tbl th.ix-th-center { text-align:center; }
		.ix-tbl td        { padding:0 14px; border-bottom:1.5px solid #f1f5f9; vertical-align:middle; }
		.ix-tbl tbody tr  { height:64px; transition:background .12s; }
		.ix-tbl tbody tr:hover td { background:#FDF8F9; }
		.ix-tbl tbody tr:last-child td { border-bottom:none; }
		.ix-tbl .ix-td-num { width:42px; text-align:center; font-size:11px; font-weight:700; color:#cbd5e1;
		                     background:#FDF8F9; border-right:1.5px solid #f1f5f9; }
		.ix-tbl .ix-td-center { text-align:center; }

		.ix-s-cell        { display:flex; align-items:center; gap:10px; }
		.ix-savatar       { width:38px; height:38px; border-radius:10px; flex-shrink:0;
		                    display:flex; align-items:center; justify-content:center;
		                    font-size:13px; font-weight:700; color:#fff; overflow:hidden; }
		.ix-savatar img   { width:100%; height:100%; object-fit:cover; }
		.ix-sname         { font-size:13px; font-weight:700; color:#0f172a; line-height:1.3; }
		.ix-semail        { font-size:11px; color:#94a3b8; margin-top:1px; }
		.ix-grade-badge   { display:inline-flex; align-items:center; justify-content:center;
		                    min-width:34px; height:26px; border-radius:7px; font-size:12px;
		                    font-weight:800; background:#FBEEF0; color:#920C24;
		                    border:1.5px solid #E8B4BE; padding:0 8px; }
		.ix-improv-badge  { display:inline-flex; align-items:center; justify-content:center;
		                    min-width:34px; height:26px; border-radius:7px; font-size:12px;
		                    font-weight:800; background:#F5D9DE; color:#920C24;
		                    border:1.5px solid #E8B4BE; padding:0 8px; }

		.ix-st-badge   { display:inline-flex; align-items:center; height:22px; border-radius:6px;
		                 font-size:11px; font-weight:700; padding:0 9px; white-space:nowrap; }
		.ix-st-reg     { background:#FBEEF0; color:#920C24; }
		.ix-st-paid    { background:#d1fae5; color:#059669; }
		.ix-st-none    { background:#f1f5f9; color:#94a3b8; }

		.ix-pay-btn    { height:28px; padding:0 12px; border-radius:6px; border:none;
		                 background:#920C24;
		                 color:#fff; font-size:11px; font-weight:700; cursor:pointer;
		                 transition:opacity .15s; }
		.ix-pay-btn:hover { opacity:.85; }

		.ix-empty         { padding:80px 20px; display:flex; flex-direction:column;
		                    align-items:center; justify-content:center; text-align:center; }
		.ix-empty-icon    { width:56px; height:56px; border-radius:14px; background:#f1f5f9;
		                    display:flex; align-items:center; justify-content:center; margin-bottom:14px; }
		.ix-empty-txt     { font-size:14px; font-weight:700; color:#94a3b8; }
		.ix-empty-sub     { font-size:12px; color:#cbd5e1; margin-top:4px; }

		.av-0{background:#920C24;}
		.av-1{background:#920C24;}
		.av-2{background:#920C24;}
		.av-3{background:#920C24;}
		.av-4{background:#920C24;}
		.av-5{background:#920C24;}
		.av-6{background:#920C24;}
		.av-7{background:#920C24;}
		`;
		document.head.appendChild(style);
	}

	var S = {
		exam_plan: null,
		programme: '',
		course:    '',
		students:  [],
		total:     0,
		search:    '',
		search_timer: null,
	};

	var $body = $(page.main);
	$body.html(`
		<div class="er2-wrap" style="padding:20px 24px;">

			<div class="er2-page-header">
				<div class="er2-page-icon" style="background:#920C24;">
					<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
				</div>
				<div>
					<div class="er2-page-title">Improvement Exam</div>
					<div class="er2-page-sub">Configure improvement exam fees and view eligible students per course</div>
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
				<button class="er2-pnav-btn" onclick="frappe.set_route('re-exam')">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.51"/></svg>
					Re Exam
				</button>
				<button class="er2-pnav-btn active">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
					Improvement Exam
				</button>
				<button class="er2-pnav-btn" id="ix-nav-consolidated">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
					Consolidated Report
				</button>
			</div>

			<!-- Filter card -->
			<div class="ix-filter-card">
				<div class="ix-fgroup">
					<span class="ix-flabel">Exam Plan</span>
					<select class="ix-select" id="ix-exam-plan">
						<option value="">Choose Exam Plan</option>
					</select>
				</div>
				<div class="ix-filter-arrow" id="ix-prog-arrow" style="display:none;">&#8594;</div>
				<div class="ix-fgroup" id="ix-prog-group" style="display:none;">
					<span class="ix-flabel">Programme</span>
					<select class="ix-select" id="ix-prog-select">
						<option value="">All Programmes</option>
					</select>
				</div>
				<div class="ix-filter-arrow" id="ix-course-arrow" style="display:none;">&#8594;</div>
				<div class="ix-fgroup wide" id="ix-course-group" style="display:none;">
					<span class="ix-flabel">Course</span>
					<select class="ix-select" id="ix-course-select">
						<option value="">All Courses</option>
					</select>
				</div>
			</div>

			<!-- Main content -->
			<div id="ix-content" style="display:none;">

				<!-- Stat cards -->
				<div class="ix-stat-cards" id="ix-stat-cards" style="display:none;"></div>

				<!-- Settings card -->
				<div class="ix-settings-card" id="ix-settings-card" style="display:none;">
					<div class="ix-settings-title">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#920C24" stroke-width="2.5"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
						Improvement Exam Settings
						<span id="ix-saved-badge" class="ix-saved-badge" style="display:none;">
							<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
							Saved
						</span>
					</div>
					<div class="ix-settings-grid">
						<div class="ix-field-group">
							<span class="ix-field-label">Improvement Exam Fee (₹)</span>
							<input class="ix-input" type="number" id="ix-fee" placeholder="0.00" step="0.01" min="0">
						</div>
						<div class="ix-field-group">
							<span class="ix-field-label">Registration Limit <span style="font-size:10px;color:#94a3b8;font-weight:400;">(0 = unlimited)</span></span>
							<input class="ix-input" type="number" id="ix-reg-limit" placeholder="Unlimited" step="1" min="0">
						</div>
						<div class="ix-field-group">
							<span class="ix-field-label">Deadline From</span>
							<input class="ix-input" type="date" id="ix-deadline-from">
						</div>
						<div class="ix-field-group">
							<span class="ix-field-label">Deadline To</span>
							<input class="ix-input" type="date" id="ix-deadline-to">
						</div>
						<div style="display:flex;align-items:flex-end;padding-bottom:1px;gap:8px;">
							<button class="ix-save-btn" id="ix-save-settings">
								<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
								Save Settings
							</button>
							<button class="ix-bulk-btn" id="ix-bulk-apply" title="Apply this fee & deadline to every course in the selected Exam Plan">
								<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
								Apply to All Courses
							</button>
						</div>
					</div>
				</div>

				<!-- Students table card -->
				<div class="ix-table-card">
					<div class="ix-table-topbar">
						<span id="ix-count-lbl" class="ix-count-lbl">Paid Students (0)</span>
						<div style="display:flex;align-items:center;gap:8px;">
							<button class="ix-bulk-btn" id="ix-view-regs" title="View all registrations including pending payments">
								<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
								All Registrations
							</button>
							<div class="ix-srch">
								<svg class="ix-srch-ico" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
								<input id="ix-search" type="text" placeholder="Search by name or ID…">
							</div>
						</div>
					</div>

					<div id="ix-placeholder" class="ix-empty">
						<div class="ix-empty-icon">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/></svg>
						</div>
						<div class="ix-empty-txt" id="ix-ph-title">Select an Exam Plan &amp; Course</div>
						<div class="ix-empty-sub" id="ix-ph-sub">Shows students who paid for the improvement exam</div>
					</div>

					<div id="ix-table-wrap" style="display:none;" class="ix-tbl-scroll">
						<table class="ix-tbl" id="ix-tbl">
							<thead>
								<tr>
									<th class="ix-td-num">#</th>
									<th style="min-width:200px;">Student</th>
									<th style="width:130px;">Reg. ID</th>
									<th style="width:110px;">Programme</th>
									<th style="width:70px;" class="ix-th-center">Grade</th>
									<th style="width:110px;" class="ix-th-center">Total Marks</th>
									<th style="width:110px;" class="ix-th-center">Impr. Marks</th>
									<th style="width:90px;" class="ix-th-center">Impr. Grade</th>
									<th style="width:110px;" class="ix-th-center">Registration</th>
									<th style="width:90px;" class="ix-th-center">Payment</th>
									<th style="width:90px;" class="ix-th-center">Action</th>
								</tr>
							</thead>
							<tbody id="ix-tbody"></tbody>
						</table>
					</div>
				</div>

			</div>
		</div>
	`);

	$body.find('#ix-nav-consolidated').on('click', function () {
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

	var $examPlan     = $body.find('#ix-exam-plan');
	var $progGroup    = $body.find('#ix-prog-group');
	var $progArrow    = $body.find('#ix-prog-arrow');
	var $progSelect   = $body.find('#ix-prog-select');
	var $courseArrow  = $body.find('#ix-course-arrow');
	var $courseGroup  = $body.find('#ix-course-group');
	var $courseSelect = $body.find('#ix-course-select');
	var $content      = $body.find('#ix-content');
	var $statCards    = $body.find('#ix-stat-cards');
	var $settingsCard = $body.find('#ix-settings-card');
	var $savedBadge   = $body.find('#ix-saved-badge');
	var $feeInput     = $body.find('#ix-fee');
	var $regLimit     = $body.find('#ix-reg-limit');
	var $dlFrom       = $body.find('#ix-deadline-from');
	var $dlTo         = $body.find('#ix-deadline-to');
	var $saveBtn      = $body.find('#ix-save-settings');
	var $bulkBtn      = $body.find('#ix-bulk-apply');
	var $search       = $body.find('#ix-search');
	var $countLbl     = $body.find('#ix-count-lbl');
	var $placeholder  = $body.find('#ix-placeholder');
	var $tableWrap    = $body.find('#ix-table-wrap');
	var $tbody        = $body.find('#ix-tbody');

	// Load exam plans
	frappe.call({
		method: 'slcm.slcm.page.improvement_exam.improvement_exam.get_exam_plans',
		callback: function (r) {
			if (!r.message) return;
			r.message.forEach(function (ep) {
				$examPlan.append('<option value="' + ep.name + '">' +
					frappe.utils.escape_html(ep.exam_name || ep.name) +
					(ep.status === 'Active' ? ' [Active]' : '') + '</option>');
			});
		},
	});

	$examPlan.on('change', function () {
		S.exam_plan = $(this).val();
		S.programme = '';
		S.course    = '';
		S.search    = '';
		$search.val('');
		$courseSelect.val('');
		$settingsCard.hide();
		clearSettings();
		if (S.exam_plan) {
			$content.show();
			loadProgrammes();
			loadCourses();
		} else {
			$content.hide();
			$statCards.hide();
			$progGroup.hide(); $progArrow.hide();
			$courseGroup.hide(); $courseArrow.hide();
			showPlaceholder('Select an Exam Plan &amp; Course', 'Shows students who paid for the improvement exam');
		}
	});

	$progSelect.on('change', function () {
		S.programme = $(this).val();
		S.course    = '';
		$courseSelect.val('');
		$settingsCard.hide();
		clearSettings();
		loadCourses();
		if (S.course) loadStudents();
		else showPlaceholder('Select a Course', 'Shows students who paid for the improvement exam');
	});

	$courseSelect.on('change', function () {
		S.course = $(this).val();
		$settingsCard.hide();
		clearSettings();
		if (S.course) {
			loadSettings();
			loadStats();
			loadStudents();
			$settingsCard.show();
		} else {
			showPlaceholder('Select a Course', 'Shows students who paid for the improvement exam');
			$statCards.hide();
		}
	});

	$search.on('input', function () {
		S.search = $(this).val();
		clearTimeout(S.search_timer);
		S.search_timer = setTimeout(loadStudents, 350);
	});

	$body.find('#ix-view-regs').on('click', function () {
		if (!S.exam_plan) {
			frappe.show_alert({ message: 'Select an Exam Plan first.', indicator: 'orange' }, 2);
			return;
		}
		ixOpenRegistrationsDialog();
	});

	$saveBtn.on('click', function () {
		if (!S.exam_plan || !S.course) return;
		$saveBtn.prop('disabled', true);
		frappe.call({
			method: 'slcm.slcm.page.improvement_exam.improvement_exam.save_improvement_setting',
			args: {
				exam_plan:          S.exam_plan,
				course:             S.course,
				improvement_fee:    $feeInput.val()    || null,
				registration_limit: $regLimit.val()    || null,
				deadline_from:      $dlFrom.val()      || null,
				deadline_to:        $dlTo.val()        || null,
			},
			callback: function (r) {
				$saveBtn.prop('disabled', false);
				if (r.message) {
					$savedBadge.show();
					setTimeout(function () { $savedBadge.hide(); }, 2500);
					frappe.show_alert({ message: 'Settings saved.', indicator: 'green' }, 2);
				}
			},
			error: function () { $saveBtn.prop('disabled', false); },
		});
	});

	$bulkBtn.on('click', function () {
		if (!S.exam_plan) return;
		frappe.confirm('Apply this fee &amp; deadline to <b>all courses</b> in the selected Exam Plan?', function () {
			frappe.call({
				method: 'slcm.slcm.page.improvement_exam.improvement_exam.bulk_save_improvement_setting',
				args: {
					exam_plan:          S.exam_plan,
					improvement_fee:    $feeInput.val()    || null,
					registration_limit: $regLimit.val()    || null,
					deadline_from:      $dlFrom.val()      || null,
					deadline_to:        $dlTo.val()        || null,
				},
				callback: function (r) {
					if (r.message) {
						frappe.show_alert({ message: 'Applied to ' + r.message.updated + ' courses.', indicator: 'green' }, 3);
					}
				},
			});
		});
	});

	function loadProgrammes() {
		$progSelect.empty().append('<option value="">All Programmes</option>');
		frappe.call({
			method: 'slcm.slcm.page.improvement_exam.improvement_exam.get_programmes_for_exam_plan',
			args: { exam_plan: S.exam_plan },
			callback: function (r) {
				if (!r.message || !r.message.length) { $progGroup.hide(); $progArrow.hide(); return; }
				r.message.forEach(function (p) {
					$progSelect.append('<option value="' + p.programme + '">' +
						frappe.utils.escape_html(p.programme_name || p.programme) + '</option>');
				});
				$progGroup.show(); $progArrow.show();
			},
		});
	}

	function loadCourses() {
		$courseSelect.empty().append('<option value="">All Courses</option>');
		frappe.call({
			method: 'slcm.slcm.page.improvement_exam.improvement_exam.get_courses_for_exam_plan',
			args: { exam_plan: S.exam_plan, programme: S.programme },
			callback: function (r) {
				if (!r.message || !r.message.length) { $courseGroup.hide(); $courseArrow.hide(); return; }
				r.message.forEach(function (c) {
					$courseSelect.append('<option value="' + c.course + '">' +
						frappe.utils.escape_html(c.course_name || c.course) + '</option>');
				});
				$courseGroup.show(); $courseArrow.show();
			},
		});
	}

	function loadSettings() {
		$feeInput.val(''); $regLimit.val(''); $dlFrom.val(''); $dlTo.val('');
		frappe.call({
			method: 'slcm.slcm.page.improvement_exam.improvement_exam.get_improvement_setting',
			args: { exam_plan: S.exam_plan, course: S.course },
			callback: function (r) {
				if (!r.message) return;
				var d = r.message;
				$feeInput.val(d.improvement_fee || '');
				$regLimit.val(d.registration_limit || '');
				$dlFrom.val(d.deadline_from || '');
				$dlTo.val(d.deadline_to || '');
			},
		});
	}

	function clearSettings() {
		$feeInput.val(''); $dlFrom.val(''); $dlTo.val('');
	}

	function loadStats() {
		if (!S.exam_plan || !S.course) return;
		frappe.call({
			method: 'slcm.slcm.page.improvement_exam.improvement_exam.get_improvement_stats',
			args: { exam_plan: S.exam_plan, course: S.course },
			callback: function (r) {
				if (!r.message) return;
				var d = r.message;
				$statCards.html(
					statCard('#920C24','#FBEEF0', '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>', d.total, 'Total Students') +
					statCard('#920C24','#F5D9DE', '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>', d.graded, 'Graded') +
					statCard('#920C24','#F5D9DE', '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/></svg>', d.registered, 'Registered') +
					statCard('#920C24','#FBEEF0', '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/></svg>', d.applied, 'Improvement Applied')
				).show();
			},
		});
	}

	function statCard(color, bg, icon, val, lbl) {
		return '<div class="ix-stat-card" style="--sc-color:' + color + ';--sc-bg:' + bg + ';">' +
			'<div class="ix-sc-icon">' + icon + '</div>' +
			'<div><div class="ix-sc-val">' + val + '</div><div class="ix-sc-lbl">' + lbl + '</div></div></div>';
	}

	function loadStudents() {
		if (!S.exam_plan || !S.course) {
			showPlaceholder('Select a Course', 'Shows students who paid for the improvement exam');
			return;
		}
		frappe.call({
			method: 'slcm.slcm.page.improvement_exam.improvement_exam.get_eligible_students',
			args: { exam_plan: S.exam_plan, course: S.course, search: S.search },
			callback: function (r) {
				if (!r.message) return;
				var d = r.message;
				S.students = d.students || [];
				S.total    = d.total || 0;
				$countLbl.text('Paid Students (' + S.total + ')');
				renderTable();
			},
		});
	}

	function renderTable() {
		if (!S.students.length) {
			showPlaceholder('No paid students found', 'Students who paid appear here after payment');
			return;
		}
		$placeholder.hide();
		$tableWrap.show();

		var rows = '';
		S.students.forEach(function (s, idx) {
			var initials = (s.student_name || 'S').charAt(0).toUpperCase();
			var avCls    = 'av-' + (idx % 8);
			var avatarHtml = s.image
				? '<img src="' + frappe.utils.escape_html(s.image) + '" alt="">'
				: initials;
			var gradeHtml = s.grade
				? '<span class="ix-grade-badge">' + frappe.utils.escape_html(s.grade) + '</span>'
				: '<span style="color:#94a3b8;">—</span>';
			var improvGrade = s.improvement_grade
				? '<span class="ix-improv-badge">' + frappe.utils.escape_html(s.improvement_grade) + (s.improvement_applied ? '<sup style="font-size:8px;">I</sup>' : '') + '</span>'
				: '<span style="color:#94a3b8;">—</span>';
			var improvMarks = s.improvement_marks ? parseFloat(s.improvement_marks).toFixed(2) : '—';
			var regBadge = s.registered
				? '<span class="ix-st-badge ix-st-reg">Registered</span>'
				: '<span class="ix-st-badge ix-st-none">Not Registered</span>';
			var payBadge = s.payment_status
				? '<span class="ix-st-badge ' + (s.payment_status === 'Paid' ? 'ix-st-paid' : 'ix-st-reg') + '">' + frappe.utils.escape_html(s.payment_status) + '</span>'
				: '<span style="color:#94a3b8;">—</span>';
			var actionHtml = (s.registered && s.payment_status !== 'Paid')
				? '<button class="ix-pay-btn ix-mark-paid" data-student="' + frappe.utils.escape_html(s.student) + '">Mark Paid</button>'
				: '';

			rows += '<tr>' +
				'<td class="ix-td-num">' + (idx + 1) + '</td>' +
				'<td><div class="ix-s-cell">' +
					'<div class="ix-savatar ' + avCls + '">' + avatarHtml + '</div>' +
					'<div><div class="ix-sname">' + frappe.utils.escape_html(s.student_name || s.student) + '</div>' +
					'<div class="ix-semail">' + frappe.utils.escape_html(s.email || '') + '</div></div>' +
				'</div></td>' +
				'<td>' + frappe.utils.escape_html(s.registration_id || s.student) + '</td>' +
				'<td>' + frappe.utils.escape_html(s.programme || '—') + '</td>' +
				'<td class="ix-td-center">' + gradeHtml + '</td>' +
				'<td class="ix-td-center" style="font-weight:700;">' + frappe.utils.escape_html(String(s.total_marks || '—')) + '</td>' +
				'<td class="ix-td-center" style="color:#920C24;font-weight:700;">' + frappe.utils.escape_html(String(improvMarks)) + '</td>' +
				'<td class="ix-td-center">' + improvGrade + '</td>' +
				'<td class="ix-td-center">' + regBadge + '</td>' +
				'<td class="ix-td-center">' + payBadge + '</td>' +
				'<td class="ix-td-center">' + actionHtml + '</td>' +
				'</tr>';
		});

		$tbody.html(rows);

		$tbody.find('.ix-mark-paid').on('click', function () {
			var student = $(this).data('student');
			var reg = frappe.db.get_value(
				'Improvement Exam Registration',
				{ exam_plan: S.exam_plan, course: S.course, student: student, status: ['!=', 'Cancelled'] },
				'name',
				function (r) {
					if (!r || !r.name) { frappe.show_alert('No registration found', 'orange'); return; }
					frappe.prompt(
						[{ label: 'Payment Reference', fieldname: 'ref', fieldtype: 'Data' }],
						function (vals) {
							frappe.call({
								method: 'slcm.slcm.page.improvement_exam.improvement_exam.mark_improvement_paid',
								args: { registration_name: r.name, payment_reference: vals.ref || '' },
								callback: function () {
									frappe.show_alert({ message: 'Marked as Paid.', indicator: 'green' }, 2);
									loadStudents(); loadStats();
								},
							});
						},
						'Mark as Paid', 'Confirm'
					);
				}
			);
		});
	}

	function showPlaceholder(title, sub) {
		$placeholder.find('#ix-ph-title').html(title);
		$placeholder.find('#ix-ph-sub').text(sub);
		$placeholder.show();
		$tableWrap.hide();
		$statCards.hide();
	}

	// ── View All Registrations dialog ─────────────────────────────────────────
	$body.find('#ix-stat-cards').on('click', '.ix-stat-card', function () {
		ixOpenRegistrationsDialog();
	});

	window.ixOpenRegistrationsDialog = function () {
		if (!S.exam_plan) {
			frappe.show_alert({ message: 'Select an Exam Plan first.', indicator: 'orange' }, 2);
			return;
		}
		var dlg = new frappe.ui.Dialog({
			title: 'Improvement Exam Registrations',
			fields: [{ fieldname: 'body_html', fieldtype: 'HTML', options: _ixRegLoadingHtml() }],
			size: 'extra-large',
		});
		dlg.show();

		frappe.call({
			method: 'slcm.slcm.page.improvement_exam.improvement_exam.get_improvement_registrations',
			args: { exam_plan: S.exam_plan, course: S.course || '' },
			callback: function (r) {
				var regs = r.message || [];
				var showCourseCol = !S.course;
				dlg.fields_dict.body_html.$wrapper.html(_ixRegDialogHtml(regs, showCourseCol));
			},
		});
	};

	// Also wire the "Registered" stat card to open the dialog
	$body.on('click', '.ix-stat-card', function () {
		ixOpenRegistrationsDialog();
	});

	function _ixRegLoadingHtml() {
		return '<div style="padding:40px;text-align:center;color:#94a3b8;font-size:14px;">' +
			'<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2" style="display:block;margin:0 auto 10px;">' +
			'<path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>Loading…</div>';
	}

	// Payment status colour coding
	function _ixPayStatusClass(ps) {
		if (!ps) return 'ix-ps-none';
		var p = ps.toLowerCase();
		if (p === 'paid' || p === 'captured' || p === 'authorized') return 'ix-ps-paid';
		if (p === 'payment initiated') return 'ix-ps-init';
		if (p === 'payment failed' || p === 'failed') return 'ix-ps-fail';
		if (p === 'refunded') return 'ix-ps-ref';
		if (p === 'cancelled' || p === 'payment cancelled') return 'ix-ps-cancel';
		return 'ix-ps-pend';
	}

	function _ixPayStatusLabel(ps) {
		if (!ps || ps === 'Pending') return 'Pending';
		return ps;
	}

	function _ixRegDialogHtml(regs, showCourseCol) {
		// Inject payment-status badge styles once
		if (!document.getElementById('ix-dlg-style')) {
			var s = document.createElement('style');
			s.id = 'ix-dlg-style';
			s.textContent = `
			.ix-ps-badge  { display:inline-flex;align-items:center;height:22px;border-radius:6px;font-size:11px;font-weight:700;padding:0 9px;white-space:nowrap; }
			.ix-ps-paid   { background:#d1fae5;color:#059669; }
			.ix-ps-init   { background:#F5D9DE;color:#920C24; }
			.ix-ps-fail   { background:#F5D9DE;color:#920C24; }
			.ix-ps-ref    { background:#F5D9DE;color:#920C24; }
			.ix-ps-cancel { background:#f1f5f9;color:#64748b; }
			.ix-ps-pend   { background:#FBEEF0;color:#920C24; }
			.ix-ps-none   { background:#f8fafc;color:#94a3b8; }
			`;
			document.head.appendChild(s);
		}

		if (!regs.length) {
			return '<div style="padding:40px;text-align:center;">' +
				'<div style="font-size:14px;font-weight:700;color:#94a3b8;">No registrations found</div>' +
				'<div style="font-size:12px;color:#cbd5e1;margin-top:4px;">Students will appear here once they register via the portal</div>' +
				'</div>';
		}

		var total = regs.length;
		var paid  = regs.filter(function (r) { return r.payment_status === 'Paid' || r.payment_status === 'Captured'; }).length;
		var auth  = regs.filter(function (r) { return r.payment_status === 'Authorized'; }).length;
		var AV    = ['av-0','av-1','av-2','av-3','av-4','av-5','av-6','av-7'];

		var legend = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap;">' +
			'<span style="font-size:13px;font-weight:700;color:#0f172a;">' + total + ' Registration' + (total !== 1 ? 's' : '') + '</span>' +
			'<span class="ix-ps-badge ix-ps-paid">' + paid + ' Paid</span>' +
			(auth ? '<span class="ix-ps-badge ix-ps-init">' + auth + ' Authorized</span>' : '') +
			'<span class="ix-ps-badge ix-ps-pend">' + (total - paid - auth) + ' Pending/Other</span>' +
			'</div>';

		var courseHeader = showCourseCol
			? '<th style="min-width:160px;padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Course</th>'
			: '';

		var rows = regs.map(function (reg, i) {
			var initials = ((reg.student_name || '').split(' ')
				.map(function (w) { return w[0] || ''; }).join('').slice(0, 2)).toUpperCase() || '?';
			var avatar = '<div class="ix-savatar ' + AV[i % 8] + '" style="width:32px;height:32px;font-size:11px;flex-shrink:0;">' +
				frappe.utils.escape_html(initials) + '</div>';

			var ps      = reg.payment_status || '';
			var isPaid  = ps === 'Paid' || ps === 'Captured';
			var isAuth  = ps === 'Authorized';
			var psClass = _ixPayStatusClass(ps);
			var psLabel = _ixPayStatusLabel(ps);

			var receiptUrl = '/printview?doctype=Improvement%20Exam%20Registration&name=' +
				encodeURIComponent(reg.name) + '&format=Improvement%20Exam%20Receipt&trigger_print=0';

			var action = '';
			if (isPaid || isAuth) {
				action = '<span style="display:flex;align-items:center;gap:6px;">' +
					'<span style="font-size:11px;color:#10b981;font-weight:700;">✓ Paid</span>' +
					'<a href="' + receiptUrl + '" target="_blank" title="Download Receipt" ' +
					'style="font-size:11px;color:#920C24;text-decoration:underline;font-weight:600;">Receipt</a>' +
					'</span>';
			} else {
				action = '<button class="ix-pay-btn" onclick="ixMarkPaidDialog(\'' + frappe.utils.escape_html(reg.name) + '\',this)">Mark Paid</button>';
			}

			var feeHtml = reg.improvement_fee
				? '₹' + parseFloat(reg.improvement_fee).toLocaleString('en-IN')
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
				'<td style="padding:0 14px;border-bottom:1.5px solid #f1f5f9;height:58px;vertical-align:middle;width:130px;text-align:center;">' +
					'<span class="ix-ps-badge ' + psClass + '">' + frappe.utils.escape_html(psLabel) + '</span>' +
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
					'<th style="width:130px;padding:10px 14px;text-align:center;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Payment Status</th>' +
					'<th style="width:90px;padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Fee</th>' +
					'<th style="width:150px;padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Payment Ref</th>' +
					'<th style="width:110px;padding:10px 14px;text-align:center;font-size:11px;font-weight:700;color:#475569;border-bottom:2px solid #e2e8f0;text-transform:uppercase;letter-spacing:.5px;">Action</th>' +
				'</tr></thead>' +
				'<tbody>' + rows + '</tbody>' +
			'</table></div>';
	}

	window.ixMarkPaidDialog = function (registrationName, btn) {
		frappe.prompt(
			[{
				fieldname:   'payment_reference',
				fieldtype:   'Data',
				label:       'Payment Reference',
				description: 'Enter receipt / challan number (optional)',
			}],
			function (vals) {
				frappe.call({
					method: 'slcm.slcm.page.improvement_exam.improvement_exam.mark_improvement_paid',
					args: { registration_name: registrationName, payment_reference: vals.payment_reference || '' },
					callback: function (r) {
						if (r.message && r.message.ok) {
							frappe.show_alert({ message: 'Marked as Paid.', indicator: 'green' }, 2);
							var td = btn.closest('td');
							if (td) {
								var receiptUrl = '/printview?doctype=Improvement%20Exam%20Registration&name=' +
									encodeURIComponent(registrationName) + '&format=Improvement%20Exam%20Receipt&trigger_print=0';
								td.innerHTML = '<span style="display:flex;align-items:center;gap:6px;">' +
									'<span style="font-size:11px;color:#10b981;font-weight:700;">✓ Paid</span>' +
									'<a href="' + receiptUrl + '" target="_blank" style="font-size:11px;color:#920C24;text-decoration:underline;font-weight:600;">Receipt</a>' +
									'</span>';
								var statusTd = td.closest('tr').querySelector('.ix-ps-badge');
								if (statusTd) {
									statusTd.className = 'ix-ps-badge ix-ps-paid';
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
};
