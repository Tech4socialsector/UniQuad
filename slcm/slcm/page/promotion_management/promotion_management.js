frappe.pages['promotion-management'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Promotion Management',
		single_column: true,
	});

	var API = 'slcm.slcm.page.promotion_management.promotion_management.';
	var PRO = ['Promoted', 'Override - Promoted'];
	var NOT = ['Not Promoted', 'Override - Not Promoted'];

	// ── CSS (NLS maroon) ──────────────────────────────────────────────────────
	if (!document.getElementById('pm-style-v4')) {
		var style = document.createElement('style');
		style.id = 'pm-style-v4';
		style.textContent = `
		/* NLS maroon — solid colours only (no gradients / translucent overlays). */
		.pm-wrap {
			--pm-maroon:#920c24; --pm-maroon-dark:#6e0919; --pm-maroon-deep:#55071a; --pm-maroon-text:#920c24;
			--pm-card:var(--card-bg,#fff); --pm-text:var(--text-color,#1f2937);
			--pm-muted:var(--text-muted,#6b7280); --pm-line:var(--border-color,#e5e7eb);
			--pm-subtle:var(--subtle-fg,#f7f7f7); --pm-control:var(--control-bg,#f4f5f6);
			--pm-green:#15803d; --pm-red:#b91c1c; --pm-amber:#b45309; --pm-blue:#1d4ed8;
			font-family:var(--font-stack,'Inter',sans-serif); color:var(--pm-text); padding-bottom:48px;
		}
		[data-theme="dark"] .pm-wrap { --pm-maroon-text:#f08a9c; --pm-green:#22c55e; --pm-red:#ef4444; --pm-amber:#f59e0b; --pm-blue:#60a5fa; }
		.pm-wrap *, .pm-wrap *::before, .pm-wrap *::after { box-sizing:border-box; }
		.pm-hidden { display:none !important; }

		/* Hero */
		.pm-hero { border-radius:14px; padding:22px 26px 18px; margin-bottom:16px; color:#fff; background:var(--pm-maroon); }
		.pm-hero-row { display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
		.pm-hero-icon { width:50px; height:50px; border-radius:12px; flex-shrink:0; background:var(--pm-maroon-dark);
			display:flex; align-items:center; justify-content:center; font-size:24px; }
		.pm-hero-text { flex:1; min-width:240px; }
		.pm-hero-title { font-size:19px; font-weight:800; }
		.pm-hero-sub { font-size:12.5px; color:#fff; margin-top:3px; }
		.pm-hero-actions { display:flex; gap:8px; flex-wrap:wrap; }
		.pm-hero-btn { height:34px; padding:0 14px; border-radius:8px; border:1px solid #fff; background:var(--pm-maroon-dark);
			color:#fff; font-size:12.5px; font-weight:600; cursor:pointer; display:inline-flex; align-items:center; gap:6px;
			text-decoration:none; white-space:nowrap; }
		.pm-hero-btn:hover { background:var(--pm-maroon-deep); color:#fff; text-decoration:none; }
		.pm-hero-btn.solid { background:#fff; color:#920c24; }
		.pm-hero-btn.solid:hover { background:#f3f4f6; color:#6e0919; }

		/* Stepper */
		.pm-stepper { display:flex; gap:8px; margin-top:18px; flex-wrap:wrap; }
		.pm-stp { flex:1; min-width:150px; display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:10px;
			background:var(--pm-maroon-dark); color:#fff; font-size:12.5px; border:2px solid var(--pm-maroon-dark); }
		.pm-stp-dot { width:24px; height:24px; border-radius:50%; flex-shrink:0; display:inline-flex; align-items:center; justify-content:center;
			font-size:11px; font-weight:800; background:var(--pm-maroon-deep); color:#fff; border:1px solid #fff; }
		.pm-stp b { display:block; color:#fff; font-size:12.5px; }
		.pm-stp small { font-size:11px; color:#fff; }
		.pm-stp.active { background:#fff; border-color:#fff; }
		.pm-stp.active b, .pm-stp.active small { color:#920c24; }
		.pm-stp.active .pm-stp-dot { background:#920c24; color:#fff; border-color:#920c24; }
		.pm-stp.done .pm-stp-dot { background:#15803d; border-color:#15803d; color:#fff; }
		.pm-hero-note { margin-top:12px; font-size:11.5px; color:#fff; }
		.pm-hero-note a { color:#fff; font-weight:700; text-decoration:underline; }

		/* Cards */
		.pm-card { background:var(--pm-card); border:1px solid var(--pm-line); border-radius:12px; padding:18px 20px; margin-bottom:16px; }
		.pm-card.flush { padding:0; overflow:hidden; }
		.pm-card-head { display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
		.pm-card-title { font-size:14px; font-weight:700; }
		.pm-card-sub { font-size:12px; color:var(--pm-muted); }

		/* Filters */
		.pm-grid { display:grid; gap:12px 14px; align-items:end;
			grid-template-columns:minmax(190px,1.3fr) minmax(150px,1fr) minmax(230px,1.6fr) 100px 100px; }
		@media (max-width:1100px) { .pm-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
		@media (max-width:560px)  { .pm-grid { grid-template-columns:1fr; } }
		.pm-fl { font-size:11px; color:var(--pm-muted); font-weight:700; margin-bottom:6px; text-transform:uppercase; letter-spacing:.5px; }
		.pm-fl .req { color:var(--pm-maroon-text); }
		.pm-sel, .pm-inp { height:40px; width:100%; border:1.5px solid var(--pm-line); border-radius:8px;
			padding:0 12px; font-size:13px; background:var(--pm-card); color:var(--pm-text); outline:none; }
		.pm-sel { cursor:pointer; }
		.pm-sel:hover, .pm-inp:hover { border-color:var(--pm-muted); }
		.pm-sel:focus, .pm-inp:focus { border-color:var(--pm-maroon); box-shadow:0 0 0 1px var(--pm-maroon); }
		.pm-sel:disabled { background:var(--pm-control); cursor:not-allowed; }
		.pm-actionbar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:16px; padding-top:14px; border-top:1px solid var(--pm-line); }
		.pm-actionbar .pm-hint { flex:1; min-width:220px; font-size:12px; color:var(--pm-muted); }

		/* Buttons */
		.pm-btn { height:38px; padding:0 16px; border-radius:8px; border:1.5px solid var(--pm-line); background:var(--pm-card);
			cursor:pointer; font-size:13px; font-weight:600; color:var(--pm-text); display:inline-flex; align-items:center;
			justify-content:center; gap:7px; white-space:nowrap; }
		.pm-btn:hover { border-color:var(--pm-maroon); color:var(--pm-maroon-text); }
		.pm-btn:active { transform:translateY(1px); }
		.pm-btn:disabled { background:var(--pm-control); color:var(--pm-muted); cursor:not-allowed; pointer-events:none; }
		.pm-btn.primary { background:#920c24; border-color:#920c24; color:#fff; }
		.pm-btn.primary:hover { background:#6e0919; border-color:#6e0919; color:#fff; }
		.pm-btn.primary:disabled { background:#9ca3af; border-color:#9ca3af; color:#fff; }
		.pm-btn.lg { height:42px; padding:0 20px; font-size:13.5px; }
		.pm-btn.sm { height:32px; padding:0 12px; font-size:12px; border-radius:7px; }
		.pm-btn.xs { height:28px; padding:0 10px; font-size:11.5px; border-radius:6px; }
		.pm-btn.green { background:#15803d; border-color:#15803d; color:#fff; }
		.pm-btn.green:hover { background:#166534; border-color:#166534; color:#fff; }
		.pm-btn.ghost-red { color:var(--pm-red); border-color:var(--pm-red); }
		.pm-btn.ghost-red:hover { background:var(--pm-red); color:#fff; }

		/* Policy checks */
		.pm-policy-strip { margin-top:14px; padding:10px 14px; border-radius:8px; background:var(--pm-card);
			border:1px solid var(--pm-line); border-left:4px solid #920c24; display:flex; gap:7px; flex-wrap:wrap; align-items:center; font-size:12px; }
		.pm-policy-strip .lbl { font-weight:700; color:var(--pm-maroon-text); margin-right:2px; }
		.pm-crit { display:inline-flex; align-items:center; gap:4px; padding:4px 10px; border-radius:6px; font-size:11.5px; font-weight:700; cursor:help; }
		.pm-crit.on  { background:#920c24; color:#fff; }
		.pm-crit.off { background:var(--pm-card); color:var(--pm-muted); border:1px solid var(--pm-line); font-weight:600; }
		.pm-crit.warn{ background:#b45309; color:#fff; }
		.pm-policy-strip a, .pm-policy-strip .pm-link { font-size:11.5px; font-weight:700; color:var(--pm-maroon-text); cursor:pointer; text-decoration:underline; }
		.pm-policy-strip .pm-push { margin-left:auto; display:flex; gap:12px; }
		.pm-help { margin-top:10px; border:1px solid var(--pm-line); border-radius:8px; overflow:hidden; font-size:12px; }
		.pm-help table { width:100%; border-collapse:collapse; }
		.pm-help th { background:#920c24; color:#fff; text-align:left; padding:7px 12px; font-size:11px; text-transform:uppercase; letter-spacing:.4px; }
		.pm-help td { padding:8px 12px; border-top:1px solid var(--pm-line); vertical-align:top; }
		.pm-help td:first-child { font-weight:700; white-space:nowrap; color:var(--pm-maroon-text); }

		/* Notices: white body, solid coloured edge */
		.pm-notice { border-radius:8px; padding:10px 14px; margin-top:12px; font-size:12.5px; display:flex; gap:9px; align-items:flex-start;
			line-height:1.5; background:var(--pm-card); border:1px solid var(--pm-line); border-left:4px solid; }
		.pm-notice.info { border-left-color:#1d4ed8; color:var(--pm-text); }
		.pm-notice.warn { border-left-color:#b45309; color:var(--pm-text); }
		.pm-notice.ok   { border-left-color:#15803d; color:var(--pm-text); }
		.pm-notice.err  { border-left-color:#b91c1c; color:var(--pm-text); }
		.pm-notice a, .pm-notice .pm-link { font-weight:700; color:var(--pm-maroon-text); text-decoration:underline; cursor:pointer; }
		.pm-notice .pm-notice-body { flex:1; }

		/* Tabs */
		.pm-views { display:inline-flex; gap:4px; background:var(--pm-card); border:1px solid var(--pm-line); border-radius:10px; padding:4px; margin:2px 0 16px; flex-wrap:wrap; }
		.pm-view-tab { padding:8px 16px; font-size:13px; font-weight:600; color:var(--pm-text); cursor:pointer; border-radius:7px;
			display:inline-flex; align-items:center; gap:8px; user-select:none; }
		.pm-view-tab:hover { color:var(--pm-maroon-text); }
		.pm-view-tab.active { background:#920c24; color:#fff; }
		.pm-count { min-width:20px; padding:1px 7px; border-radius:10px; font-size:11px; font-weight:700; background:var(--pm-control); color:var(--pm-text); text-align:center; }
		.pm-view-tab.active .pm-count { background:#fff; color:#920c24; }

		/* KPI tiles */
		.pm-kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:16px; }
		.pm-kpi { background:var(--pm-card); border:1px solid var(--pm-line); border-top:4px solid var(--c); border-radius:10px; padding:14px 16px; display:flex; align-items:center; gap:12px; }
		.pm-kpi-ico { width:40px; height:40px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:16px; flex-shrink:0;
			background:var(--c); color:#fff; }
		.pm-kpi-val { font-size:22px; font-weight:800; line-height:1.1; color:var(--pm-text); }
		.pm-kpi-lbl { font-size:11px; color:var(--pm-muted); font-weight:600; margin-top:2px; }

		/* Log band */
		.pm-band { border-radius:14px; padding:20px 22px; margin-bottom:16px; color:#fff; background:#920c24; }
		.pm-band-top { display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
		.pm-band-kicker { font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:#fff; }
		.pm-band-title { font-size:16px; font-weight:700; margin-top:3px; }
		.pm-band-meta { font-size:12px; color:#fff; text-align:right; }
		.pm-band-stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr)); gap:10px; }
		.pm-band-stat { background:#6e0919; border-radius:10px; padding:10px 12px; border-left:4px solid #fff; }
		.pm-band-stat .v { font-size:22px; font-weight:800; line-height:1.1; color:#fff; }
		.pm-band-stat .l { font-size:10.5px; text-transform:uppercase; letter-spacing:.05em; color:#fff; margin-top:3px; }
		.pm-band-stat.g { border-left-color:#22c55e; } .pm-band-stat.r { border-left-color:#ef4444; }
		.pm-band-stat.a { border-left-color:#f59e0b; } .pm-band-stat.b { border-left-color:#60a5fa; }
		.pm-meter { margin-top:14px; height:10px; border-radius:6px; background:#55071a; overflow:hidden; display:flex; }
		.pm-meter span { height:100%; }
		.pm-meter-legend { display:flex; gap:14px; flex-wrap:wrap; margin-top:8px; font-size:11px; color:#fff; }
		.pm-meter-legend i { display:inline-block; width:9px; height:9px; border-radius:2px; margin-right:5px; }

		/* Toolbars */
		.pm-toolbar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; padding:12px 16px; border-bottom:1px solid var(--pm-line); }
		.pm-chips { display:inline-flex; gap:4px; flex-wrap:wrap; }
		.pm-chip { padding:5px 11px; border-radius:7px; font-size:12.5px; font-weight:600; color:var(--pm-text); cursor:pointer;
			user-select:none; display:inline-flex; align-items:center; gap:6px; border:1px solid var(--pm-line); background:var(--pm-card); }
		.pm-chip:hover { border-color:#920c24; color:var(--pm-maroon-text); }
		.pm-chip.active { background:#920c24; border-color:#920c24; color:#fff; }
		.pm-chip .n { font-size:10.5px; font-weight:700; padding:0 6px; border-radius:8px; background:var(--pm-control); color:var(--pm-text); }
		.pm-chip.active .n { background:#fff; color:#920c24; }
		.pm-srch { position:relative; flex:1; min-width:180px; max-width:300px; }
		.pm-srch input { padding-left:34px; height:36px; }
		.pm-srch-ico { position:absolute; left:11px; top:9px; color:var(--pm-muted); font-size:13px; pointer-events:none; }
		.pm-spacer { flex:1; }
		.pm-dl { display:flex; gap:6px; flex-wrap:wrap; align-items:center; padding:11px 16px; border-bottom:1px solid var(--pm-line); background:var(--pm-card); }
		.pm-dl-lbl { font-size:11px; font-weight:700; color:var(--pm-maroon-text); text-transform:uppercase; letter-spacing:.6px; margin-right:4px; }

		/* Tables */
		.pm-table-wrap { overflow-x:auto; }
		table.pm-tbl { width:100%; border-collapse:collapse; font-size:13px; }
		table.pm-tbl th { background:#920c24; color:#fff; font-size:10.5px; font-weight:700; text-transform:uppercase;
			letter-spacing:.5px; padding:10px 12px; white-space:nowrap; text-align:left; cursor:default; }
		table.pm-tbl td { padding:11px 12px; border-bottom:1px solid var(--pm-line); vertical-align:middle; }
		table.pm-tbl tr:last-child td { border-bottom:none; }
		table.pm-tbl tbody tr:hover td { background:var(--pm-subtle); }
		table.pm-tbl td.c, table.pm-tbl th.c { text-align:center; }
		.pm-num { color:var(--pm-muted); font-size:12px; }
		.pm-stu { display:flex; align-items:center; gap:10px; min-width:190px; }
		.pm-av { width:32px; height:32px; border-radius:50%; flex-shrink:0; display:flex; align-items:center; justify-content:center;
			font-size:12px; font-weight:700; color:#fff; background:#920c24; }
		.pm-sname { font-weight:600; color:var(--pm-text); line-height:1.25; }
		.pm-sid { font-size:11.5px; }
		.pm-sid a { color:var(--pm-maroon-text); }
		.pm-muted { color:var(--pm-muted); font-size:12px; }
		.pm-reasons { display:flex; flex-direction:column; gap:3px; max-width:360px; font-size:12px; }
		.pm-reasons .x { color:var(--pm-red); }
		.pm-reasons .ok { color:var(--pm-green); }
		.pm-ovr { font-size:11.5px; color:var(--pm-blue); margin-top:4px; max-width:360px; }
		.pm-actions { display:flex; gap:6px; flex-wrap:wrap; }

		.pm-bdg { display:inline-flex; align-items:center; padding:3px 10px; border-radius:6px; font-size:11px; font-weight:700; white-space:nowrap; color:#fff; }
		.bdg-pro  { background:#15803d; }
		.bdg-not  { background:#b91c1c; }
		.bdg-cond { background:#b45309; }
		.bdg-ovp  { background:#0f766e; }
		.bdg-ovn  { background:#7f1d1d; }
		.bdg-enr  { background:#1d4ed8; }
		.bdg-fail { background:#b91c1c; }
		.chk { display:inline-flex; width:22px; height:22px; border-radius:50%; align-items:center; justify-content:center; font-weight:800; font-size:11px; }
		.chk.pass { background:#15803d; color:#fff; } .chk.fail { background:#b91c1c; color:#fff; }
		.chk.nc { color:var(--pm-muted); }

		/* Empty */
		.pm-empty { text-align:center; padding:52px 20px; color:var(--pm-muted); }
		.pm-empty-ico { width:60px; height:60px; margin:0 auto 12px; border-radius:14px; display:flex; align-items:center; justify-content:center;
			font-size:26px; background:#920c24; color:#fff; }
		.pm-empty-title { font-size:15px; font-weight:700; color:var(--pm-text); margin-bottom:4px; }
		.pm-empty .pm-btn { margin-top:14px; }

		/* Dialogs */
		.pm-run-sum { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:4px 0 14px; }
		.pm-run-tile { border-radius:10px; padding:12px; text-align:center; color:#fff; }
		.pm-run-tile .v { font-size:24px; font-weight:800; line-height:1.1; }
		.pm-run-tile .l { font-size:11px; margin-top:3px; font-weight:600; }
		.pm-run-tile.g { background:#15803d; } .pm-run-tile.r { background:#b91c1c; } .pm-run-tile.a { background:#b45309; }
		.pm-run-meta { display:grid; grid-template-columns:130px 1fr; gap:6px 10px; font-size:12.5px; padding:12px 14px;
			border-radius:8px; border:1px solid var(--border-color); margin-bottom:12px; }
		.pm-run-meta span:nth-child(odd) { color:var(--text-muted); }
		.pm-run-meta span:nth-child(even) { font-weight:600; }
		.pm-run-dialog .modal-header { background:#920c24; }
		.pm-run-dialog .modal-header .modal-title { color:#fff; }
		.pm-run-dialog .modal-header .btn-modal-close svg { stroke:#fff; }
		.pm-run-dialog .modal-footer .btn-primary { background:#920c24; border-color:#920c24; }
		.pm-run-dialog .modal-footer .btn-primary:hover { background:#6e0919; border-color:#6e0919; }
		`;
		document.head.appendChild(style);
	}

	// ── State ─────────────────────────────────────────────────────────────────
	var S = {
		policies: {},          // name -> policy row
		preview: null,         // {key, students, counts}
		previewFilter: 'all', previewSearch: '',
		logKey: null,          // {policy, from_year, to_year}
		log: null,             // {records, counts, policy, last_processed_on}
		lastRun: null,         // {key, result} of the run made in this session
		logFilter: 'all', logSearch: '',
		history: [],
		view: 'eval',
		running: false,
	};

	// ── Mount ─────────────────────────────────────────────────────────────────
	var $root = $('<div class="pm-wrap"></div>');
	$(page.main).html('').append($root);

	$root.html(`
		<div class="pm-hero">
			<div class="pm-hero-row">
				<div class="pm-hero-icon">&#127891;</div>
				<div class="pm-hero-text">
					<div class="pm-hero-title">Promotion Management</div>
					<div class="pm-hero-sub">Year-to-year promotion, checked against the Promotion Policy &mdash; you decide when it runs.</div>
				</div>
				<div class="pm-hero-actions">
					<a class="pm-hero-btn" href="/app/promotion-policy" target="_blank">&#9881; Policies</a>
					<button class="pm-hero-btn solid" data-act="official-dl">&#128203; Official Report</button>
				</div>
			</div>
			<div class="pm-stepper">
				<div class="pm-stp" data-step="1"><span class="pm-stp-dot">1</span><span><b>Select</b><small>Cohort &amp; policy</small></span></div>
				<div class="pm-stp" data-step="2"><span class="pm-stp-dot">2</span><span><b>Preview</b><small>Who is eligible</small></span></div>
				<div class="pm-stp" data-step="3"><span class="pm-stp-dot">3</span><span><b>Run Promotion</b><small>Manual, on your click</small></span></div>
				<div class="pm-stp" data-step="4"><span class="pm-stp-dot">4</span><span><b>Review Log</b><small>Download &amp; resolve</small></span></div>
			</div>
			<div class="pm-hero-note">&#9432; Term &rarr; Term moves are done from
				<a href="/app/student-enrollment" target="_blank">Student Enrollment &rarr; Promote Students</a> (automatic, no policy check).</div>
		</div>

		<div class="pm-card">
			<div class="pm-card-head">
				<div>
					<div class="pm-card-title">Select cohort &amp; policy</div>
					<div class="pm-card-sub">Nothing happens until you click <b>Run Promotion</b>.</div>
				</div>
			</div>
			<div class="pm-grid">
				<div>
					<div class="pm-fl">Programme <span class="req">*</span></div>
					<select class="pm-sel" id="pm-prog"><option value="">Select Programme</option></select>
				</div>
				<div>
					<div class="pm-fl">Academic Year <span class="req">*</span></div>
					<select class="pm-sel" id="pm-ay"><option value="">Select Year</option></select>
				</div>
				<div>
					<div class="pm-fl">Promotion Policy <span class="req">*</span></div>
					<select class="pm-sel" id="pm-policy" disabled><option value="">Select Programme &amp; Academic Year first</option></select>
				</div>
				<div>
					<div class="pm-fl">From Year <span class="req">*</span></div>
					<input type="number" class="pm-inp" id="pm-fy" min="1" max="10" placeholder="1">
				</div>
				<div>
					<div class="pm-fl">To Year</div>
					<input type="number" class="pm-inp" id="pm-ty" min="2" max="11" placeholder="2">
				</div>
			</div>
			<div id="pm-policy-strip" class="pm-policy-strip pm-hidden"></div>
			<div id="pm-filter-notice" class="pm-hidden"></div>
			<div class="pm-actionbar">
				<div class="pm-hint" id="pm-action-hint">Complete the selection to preview or run promotion.</div>
				<button class="pm-btn lg" id="pm-fetch-btn">&#128269; Preview Students</button>
				<button class="pm-btn primary lg" id="pm-run-btn">&#9654; Run Promotion</button>
			</div>
		</div>

		<div class="pm-views">
			<div class="pm-view-tab active" data-view="eval">&#128269; Preview <span class="pm-count" id="vc-eval">0</span></div>
			<div class="pm-view-tab" data-view="log">&#128203; Promotion Log <span class="pm-count" id="vc-log">0</span></div>
			<div class="pm-view-tab" data-view="hist">&#128339; History <span class="pm-count" id="vc-hist">0</span></div>
		</div>

		<div id="pm-view-eval"></div>
		<div id="pm-view-log" class="pm-hidden"></div>
		<div id="pm-view-hist" class="pm-hidden"></div>
	`);

	// ── Helpers ───────────────────────────────────────────────────────────────
	function esc(s) {
		return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
			.replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
	}
	function num(v, d) { var n = parseFloat(v); return isNaN(n) ? '—' : n.toFixed(d); }
	function bucket(status) {
		if (PRO.indexOf(status) > -1) return 'promoted';
		if (NOT.indexOf(status) > -1) return 'not_promoted';
		return 'conditional';
	}
	function badge(s) {
		var cls = {
			'Promoted': 'bdg-pro', 'Not Promoted': 'bdg-not', 'Conditional': 'bdg-cond',
			'Override - Promoted': 'bdg-ovp', 'Override - Not Promoted': 'bdg-ovn',
		}[s] || '';
		return '<span class="pm-bdg ' + cls + '">' + esc(s || '—') + '</span>';
	}
	function chk(v) {
		if (v === 'Pass') return '<span class="chk pass" title="Pass">&#10003;</span>';
		if (v === 'Fail') return '<span class="chk fail" title="Fail">&#10007;</span>';
		return '<span class="chk nc" title="Not checked">—</span>';
	}
	function studentCell(r) {
		var name = (r.student_name || r.student || '').trim();
		var parts = name.split(/\s+/).filter(Boolean);
		var ini = ((parts[0] || '?')[0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
		return '<div class="pm-stu"><span class="pm-av">' + esc(ini) + '</span>'
			+ '<div><div class="pm-sname">' + esc(name || r.student) + '</div>'
			+ '<div class="pm-sid"><a href="/app/student-master/' + encodeURIComponent(r.student) + '" target="_blank">' + esc(r.student) + '</a>'
			+ (r.batch_year ? ' <span class="pm-muted">&middot; ' + esc(r.batch_year) + '</span>' : '') + '</div></div></div>';
	}
	function reasonsHtml(remarks, status) {
		var parts = (remarks || '').split(';').map(function (x) { return x.trim(); }).filter(Boolean);
		if (!parts.length) {
			return status && PRO.indexOf(status) > -1
				? '<div class="pm-reasons"><span class="ok">&#10003; Meets all policy criteria</span></div>'
				: '<span class="pm-muted">—</span>';
		}
		return '<div class="pm-reasons">' + parts.map(function (p) {
			return '<span class="x">&#8226; ' + esc(p) + '</span>';
		}).join('') + '</div>';
	}
	function currentFilters() {
		return {
			program: $('#pm-prog').val() || '',
			academic_year: $('#pm-ay').val() || '',
			policy: $('#pm-policy').val() || '',
			from_year: parseInt($('#pm-fy').val(), 10) || 0,
			to_year: parseInt($('#pm-ty').val(), 10) || 0,
		};
	}
	function filtersComplete(f) {
		if (!(f.program && f.academic_year && f.policy && f.from_year && f.to_year > f.from_year)) return false;
		var prob = policyYearProblem(S.policies[f.policy], f);
		return !(prob && prob.level === 'block');
	}
	function sameKey(a, b) {
		return !!(a && b && a.program === b.program && a.academic_year === b.academic_year
			&& a.policy === b.policy && a.from_year === b.from_year && a.to_year === b.to_year);
	}
	function filterNotice(type, html) {
		if (!type) { $('#pm-filter-notice').addClass('pm-hidden').html(''); return; }
		$('#pm-filter-notice').attr('class', 'pm-notice ' + type).html('<span class="pm-notice-body">' + html + '</span>');
	}
	function emptyState(icon, title, sub, btnHtml) {
		return '<div class="pm-card"><div class="pm-empty"><div class="pm-empty-ico">' + icon + '</div>'
			+ '<div class="pm-empty-title">' + title + '</div><div>' + (sub || '') + '</div>' + (btnHtml || '') + '</div></div>';
	}
	function switchView(v) {
		S.view = v;
		$root.find('.pm-view-tab').removeClass('active').filter('[data-view="' + v + '"]').addClass('active');
		$('#pm-view-eval').toggleClass('pm-hidden', v !== 'eval');
		$('#pm-view-log').toggleClass('pm-hidden', v !== 'log');
		$('#pm-view-hist').toggleClass('pm-hidden', v !== 'hist');
		updateStepper();
	}
	function applyStudentFilter(rows, filter, term, useEnrollment) {
		return rows.filter(function (r) {
			if (filter === 'enrollment_failed') {
				if (!useEnrollment || r.enrollment_status !== 'Failed') return false;
			} else if (filter !== 'all' && bucket(r.promotion_status) !== filter) {
				return false;
			}
			if (!term) return true;
			return (r.student_name || '').toLowerCase().indexOf(term) > -1
				|| (r.student || '').toLowerCase().indexOf(term) > -1;
		});
	}
	function chipsHtml(active, counts, withEnrollment) {
		var chips = [
			['all', 'All', counts.total],
			['promoted', 'Promoted', counts.promoted],
			['not_promoted', 'Not Promoted', counts.not_promoted],
			['conditional', 'Conditional', counts.conditional],
		];
		if (withEnrollment) chips.push(['enrollment_failed', 'Enrollment Failed', counts.enrollment_failed]);
		return '<div class="pm-chips">' + chips.map(function (c) {
			return '<span class="pm-chip' + (c[0] === active ? ' active' : '') + '" data-filter="' + c[0] + '">'
				+ c[1] + ' <span class="n">' + (c[2] || 0) + '</span></span>';
		}).join('') + '</div>';
	}
	function historyEntry(f) {
		return (S.history || []).filter(function (h) {
			return h.promotion_policy === f.policy && String(h.current_year) === String(f.from_year)
				&& String(h.target_year) === String(f.to_year);
		})[0];
	}

	// ── Stepper + action bar state ────────────────────────────────────────────
	function updateStepper() {
		var f = currentFilters();
		var s1 = filtersComplete(f);
		var s2 = s1 && S.preview && sameKey(S.preview.key, f);
		var s3 = s1 && S.lastRun && sameKey(S.lastRun.key, f);
		var active = !s1 ? 1 : (S.view === 'log' && S.log ? 4 : (s3 ? 4 : (s2 ? 3 : 2)));
		$root.find('.pm-stp').each(function () {
			var n = parseInt($(this).data('step'), 10);
			var done = (n === 1 && s1) || (n === 2 && s2) || (n === 3 && s3) || (n === 4 && S.view === 'log' && S.log && S.log.counts && S.log.counts.total);
			$(this).toggleClass('done', !!done && n !== active).toggleClass('active', n === active);
			$(this).find('.pm-stp-dot').html(done && n !== active ? '&#10003;' : n);
		});

		$('#pm-fetch-btn, #pm-run-btn').prop('disabled', !s1 || S.running);
		var hint;
		if (!f.program || !f.academic_year) hint = 'Select a Programme and Academic Year.';
		else if (!f.policy) hint = 'Select the Promotion Policy to apply.';
		else if (!f.from_year) hint = 'Enter the year students are promoted from.';
		else if (f.to_year <= f.from_year) hint = 'To Year must be greater than From Year.';
		else if (!s1) hint = 'The selected policy does not match this year — pick the policy for Year ' + esc(f.from_year) + ' or change the years.';
		else if (s3) hint = '&#10003; Promotion was run for this selection. Run again to re-evaluate students still in Year ' + esc(f.from_year) + '.';
		else if (s2) hint = 'Preview ready — <b>' + (S.preview.counts.promoted || 0) + '</b> of <b>' + (S.preview.counts.total || 0) + '</b> eligible. Click <b>Run Promotion</b> when ready.';
		else hint = 'Ready. <b>Preview</b> to check eligibility first, or <b>Run Promotion</b> directly (you will see a summary before anything changes).';
		$('#pm-action-hint').html(hint);
	}

	function updatePriorRunNotice() {
		var f = currentFilters();
		if (!filtersComplete(f) || !S.policies[f.policy]) {
			if ($('#pm-filter-notice').hasClass('prior')) filterNotice(null);
			return;
		}
		var h = historyEntry(f);
		if (!h) {
			if ($('#pm-filter-notice').hasClass('prior')) filterNotice(null);
			return;
		}
		var when = h.last_processed_on ? frappe.datetime.str_to_user(h.last_processed_on) : '';
		filterNotice('info', '&#128339; This selection was already run' + (when ? ' on <b>' + esc(when) + '</b>' : '')
			+ ' — ' + (h.promoted || 0) + ' promoted, ' + (h.not_promoted || 0) + ' not promoted of ' + (h.total || 0) + '. '
			+ '<span class="pm-link" data-act="open-prior">View that log</span>. Running again only re-evaluates students still in Year ' + esc(f.from_year) + '.');
		$('#pm-filter-notice').addClass('prior');
	}

	// ── Dropdowns ─────────────────────────────────────────────────────────────
	var _loaded = { programs: false, years: false };
	function _checkAutoAction() {
		if (!_loaded.programs || !_loaded.years) return;
		var urlParams = new URLSearchParams(window.location.search);
		if (urlParams.get('action') === 'download_report') {
			setTimeout(openOfficialDownload, 400);
		}
	}

	frappe.call({
		method: API + 'get_programs',
		callback: function (r) {
			var sel = document.getElementById('pm-prog');
			(r.message || []).forEach(function (p) {
				var o = document.createElement('option');
				o.value = p.name;
				o.text = p.name + (p.program_name && p.program_name !== p.name ? ' — ' + p.program_name : '');
				sel.appendChild(o);
			});
			_loaded.programs = true;
			_checkAutoAction();
		},
	});

	frappe.call({
		method: API + 'get_academic_years',
		callback: function (r) {
			var sel = document.getElementById('pm-ay');
			(r.message || []).forEach(function (a) {
				var o = document.createElement('option');
				o.value = a.name;
				o.text = a.name;
				sel.appendChild(o);
			});
			_loaded.years = true;
			_checkAutoAction();
		},
	});

	var _policyReq = 0;
	function loadPolicies() {
		var f = currentFilters();
		var sel = document.getElementById('pm-policy');
		S.policies = {};
		sel.value = '';
		renderPolicyStrip();
		filterNotice(null);
		if (!f.program || !f.academic_year) {
			sel.innerHTML = '<option value="">Select Programme &amp; Academic Year first</option>';
			sel.disabled = true;
			onFiltersChanged();
			return;
		}
		sel.innerHTML = '<option value="">Loading policies…</option>';
		sel.disabled = true;
		onFiltersChanged();
		var req = ++_policyReq;
		frappe.call({
			method: API + 'get_policies_for_filters',
			args: { program: f.program, academic_year: f.academic_year },
			callback: function (r) {
				if (req !== _policyReq) return; // superseded by a newer selection
				var rows = r.message || [];
				if (!rows.length) {
					sel.innerHTML = '<option value="">No Active policy found</option>';
					sel.disabled = true;
					var url = '/app/promotion-policy/new?program=' + encodeURIComponent(f.program)
						+ '&academic_year=' + encodeURIComponent(f.academic_year);
					filterNotice('warn', '&#9888; No <b>Active</b> Promotion Policy for <b>' + esc(f.program) + '</b> / <b>'
						+ esc(f.academic_year) + '</b>. Year-to-year promotion needs one — '
						+ '<a href="' + url + '" target="_blank">create a policy</a> (or activate a Draft), then reselect the Academic Year.');
				} else {
					sel.innerHTML = '<option value="">Select Policy</option>';
					rows.forEach(function (p) {
						S.policies[p.name] = p;
						var o = document.createElement('option');
						o.value = p.name;
						o.text = p.title + '  (Yr ' + p.from_year + ' → ' + p.to_year + ')';
						sel.appendChild(o);
					});
					if (rows.length === 1) sel.value = rows[0].name;
					sel.disabled = false;
					applyPolicyYears();
				}
				renderPolicyStrip();
				onFiltersChanged();
			},
		});
	}

	function applyPolicyYears() {
		var p = S.policies[$('#pm-policy').val()];
		// Some policies store calendar years (e.g. 2026) — only prefill real year levels.
		if (p && p.from_year >= 1 && p.from_year <= 10 && p.to_year > p.from_year) {
			$('#pm-fy').val(p.from_year);
			$('#pm-ty').val(p.to_year);
		}
	}

	// One definition per policy check — used for the chips, tooltips and help panel.
	function policyChecks(p) {
		var maxShort = (p.max_shortage_courses === null || p.max_shortage_courses === undefined || p.max_shortage_courses === '')
			? 2 : p.max_shortage_courses;
		return [
			{ on: p.enable_cgpa_check, name: 'CGPA', rule: 'CGPA ≥ ' + (p.min_cgpa || 0),
				help: 'Current CGPA from published results must be at least ' + (p.min_cgpa || 0) + '.' },
			{ on: p.enable_backlog_check, name: 'Backlogs', rule: 'Failed courses ≤ ' + (p.max_backlogs_allowed || 0),
				help: 'Courses failed in this academic year\'s exams (final grade marked as a fail in the grading schema).' },
			{ on: p.enable_attendance_check, name: 'Attendance', rule: 'Avg attendance ≥ ' + (p.min_attendance_percent || 0) + '%',
				help: 'Average attendance across all courses in this academic year.' },
			{ on: p.enable_course_shortage_check, name: 'Attendance shortage', rule: 'Courses below min. attendance ≤ ' + maxShort,
				help: 'Number of courses where attendance is below that course\'s required minimum.' },
			{ on: p.enable_cf_check, name: 'Carry-forward (after FA/MFA)', rule: 'Still short after FA/MFA ≤ ' + (p.max_cf_fa_shortage || 0) + ' courses',
				help: 'Courses where First Attempt (FA) or Medical First Attempt (MFA) condonation hours were credited, '
					+ 'but the student is still not exam-eligible. These courses are carried forward (CF).' },
			{ on: p.block_on_fee_due, name: 'Fee due', rule: 'No outstanding fee',
				help: 'Blocks promotion if the student has any Fee Demand that is Pending, Partially Paid or Overdue.' },
		];
	}

	// A policy whose years are real year levels (1–10) must match the selection.
	function policyYearProblem(p, f) {
		if (!p) return null;
		if (p.from_year > 10) {
			return { level: 'warn', text: 'This policy\'s years are set as ' + p.from_year + ' → ' + p.to_year
				+ ' (calendar years). Set them to year levels (e.g. 1 → 2) so the policy applies to the right year.' };
		}
		if (f.from_year && (f.from_year !== p.from_year || (f.to_year && f.to_year !== p.to_year))) {
			return { level: 'block', text: 'This policy is for Year ' + p.from_year + ' → ' + p.to_year
				+ ', but Year ' + f.from_year + ' → ' + (f.to_year || '?') + ' is selected.' };
		}
		return null;
	}

	function renderPolicyStrip() {
		var p = S.policies[$('#pm-policy').val()];
		var $s = $('#pm-policy-strip');
		if (!p) { $s.addClass('pm-hidden').html(''); $('#pm-help').remove(); return; }
		var checks = policyChecks(p);
		var h = '<span class="lbl">Checks:</span>';
		checks.forEach(function (c) {
			h += c.on
				? '<span class="pm-crit on" title="' + esc(c.help) + '">&#10003; ' + esc(c.rule) + '</span>'
				: '<span class="pm-crit off" title="Not checked by this policy">' + esc(c.name) + ': off</span>';
		});
		if (!checks.some(function (c) { return c.on; })) h += '<span class="pm-crit warn">No checks enabled — everyone is eligible</span>';
		if (!p.auto_update_student_year) h += '<span class="pm-crit warn">Auto-update OFF — decisions logged only</span>';
		h += '<span class="pm-push"><span class="pm-link" data-act="toggle-help">What do these checks mean?</span>'
			+ '<a href="/app/promotion-policy/' + encodeURIComponent(p.name) + '" target="_blank">Edit policy &#8599;</a></span>';
		$s.html(h).removeClass('pm-hidden');

		$('#pm-help').remove();
		var help = '<div class="pm-help pm-hidden" id="pm-help"><table><thead><tr><th>Check</th><th>Rule in this policy</th><th>What it means</th></tr></thead><tbody>'
			+ checks.map(function (c) {
				return '<tr><td>' + esc(c.name) + '</td><td>' + (c.on ? esc(c.rule) : '<span class="pm-muted">Not checked</span>')
					+ '</td><td>' + esc(c.help) + '</td></tr>';
			}).join('') + '</tbody></table></div>';
		$s.after(help);
		if (S.helpOpen) $('#pm-help').removeClass('pm-hidden');
		updatePolicyYearNotice();
	}

	function updatePolicyYearNotice() {
		var $n = $('#pm-year-notice');
		var prob = policyYearProblem(S.policies[$('#pm-policy').val()], currentFilters());
		if (!prob) { $n.remove(); return; }
		if (!$n.length) { $n = $('<div id="pm-year-notice"></div>'); $('#pm-policy-strip').nextAll('#pm-help').length ? $('#pm-help').after($n) : $('#pm-policy-strip').after($n); }
		$n.attr('class', 'pm-notice ' + (prob.level === 'block' ? 'err' : 'warn'))
			.html('<span class="pm-notice-body">&#9888; ' + esc(prob.text) + '</span>');
	}

	$root.on('click', '[data-act="toggle-help"]', function () {
		S.helpOpen = !S.helpOpen;
		$('#pm-help').toggleClass('pm-hidden', !S.helpOpen);
	});

	// ── Filter events ─────────────────────────────────────────────────────────
	$root.on('change', '#pm-prog, #pm-ay', function () {
		loadPolicies();
		loadHistory();
	});
	$root.on('change', '#pm-policy', function () {
		applyPolicyYears();
		renderPolicyStrip();
		onFiltersChanged();
	});
	$root.on('input', '#pm-fy', function () {
		var v = parseInt(this.value, 10);
		if (!isNaN(v)) $('#pm-ty').val(v + 1);
		onFiltersChanged();
	});
	$root.on('input', '#pm-ty', onFiltersChanged);

	function onFiltersChanged() {
		// A preview is only valid for the exact filters it was fetched with.
		if (S.preview && !sameKey(S.preview.key, currentFilters())) {
			S.preview = null;
			renderEval('stale');
		}
		updatePriorRunNotice();
		updatePolicyYearNotice();
		updateStepper();
	}

	function validateFilters(f) {
		if (!f.program) return __('Please select a Programme.');
		if (!f.academic_year) return __('Please select an Academic Year.');
		if (!f.policy) return __('Please select a Promotion Policy.');
		if (!f.from_year) return __('Please enter From Year (e.g. 1).');
		if (f.to_year <= f.from_year) return __('To Year must be greater than From Year.');
		var prob = policyYearProblem(S.policies[f.policy], f);
		if (prob && prob.level === 'block') return prob.text;
		return null;
	}

	// ── Preview ───────────────────────────────────────────────────────────────
	function fetchPreview(f) {
		S.running = true;
		updateStepper();
		return new Promise(function (resolve, reject) {
			var result = null;
			frappe.call({
				method: API + 'fetch_students',
				args: { program: f.program, academic_year: f.academic_year, from_year: f.from_year, policy_name: f.policy },
				callback: function (r) {
					var data = r.message || { students: [] };
					S.preview = { key: f, students: data.students || [], counts: data.counts || {} };
					S.previewFilter = 'all'; S.previewSearch = '';
					result = S.preview;
				},
				always: function () {
					// Settles on success, server error and network failure alike.
					S.running = false;
					if (result && sameKey(result.key, currentFilters())) {
						renderEval();
						updateStepper();
						resolve(result);
					} else {
						if (result) { S.preview = null; renderEval('stale'); }
						updateStepper();
						reject();
					}
				},
			});
		});
	}

	$root.on('click', '#pm-fetch-btn', function () {
		if (S.running) return;
		var f = currentFilters();
		var err = validateFilters(f);
		if (err) { frappe.show_alert({ message: err, indicator: 'red' }); return; }
		var $btn = $(this);
		$btn.prop('disabled', true).html('Loading…');
		switchView('eval');
		fetchPreview(f).catch(function () {}).then(function () {
			$btn.html('&#128269; Preview Students');
			updateStepper();
		});
	});

	function renderEval(state) {
		var $v = $('#pm-view-eval');
		if (state === 'stale') {
			$('#vc-eval').text(0);
			$v.html(emptyState('&#8635;', 'Selection changed', 'Click <b>Preview Students</b> to evaluate with the current selection.'));
			return;
		}
		if (!S.preview) {
			$('#vc-eval').text(0);
			$v.html(emptyState('&#127891;', 'Nothing previewed yet',
				'Pick a Programme, Academic Year and Promotion Policy, then click <b>Preview Students</b> to see who is eligible.<br>'
				+ 'Promotion itself only happens when you click <b>Run Promotion</b>.'));
			return;
		}
		var P = S.preview, c = P.counts;
		$('#vc-eval').text(c.total || 0);
		if (!P.students.length) {
			$v.html(emptyState('&#128269;', 'No students to promote',
				'No Active students are in Year ' + esc(P.key.from_year) + ' for this Programme and Academic Year.<br>'
				+ 'Already-promoted students appear in the Promotion Log (see <b>History</b>).'));
			return;
		}

		$v.html(`
			<div class="pm-kpis">
				<div class="pm-kpi" style="--c:#920c24"><div class="pm-kpi-ico">&#128101;</div>
					<div><div class="pm-kpi-val">${c.total || 0}</div><div class="pm-kpi-lbl">Students in Year ${esc(P.key.from_year)}</div></div></div>
				<div class="pm-kpi" style="--c:#15803d"><div class="pm-kpi-ico">&#10003;</div>
					<div><div class="pm-kpi-val">${c.promoted || 0}</div><div class="pm-kpi-lbl">Eligible to promote</div></div></div>
				<div class="pm-kpi" style="--c:#b91c1c"><div class="pm-kpi-ico">&#10007;</div>
					<div><div class="pm-kpi-val">${c.not_promoted || 0}</div><div class="pm-kpi-lbl">Not eligible</div></div></div>
				<div class="pm-kpi" style="--c:#b45309"><div class="pm-kpi-ico">&#9201;</div>
					<div><div class="pm-kpi-val">${c.conditional || 0}</div><div class="pm-kpi-lbl">Conditional</div></div></div>
			</div>
			<div class="pm-card flush">
				<div class="pm-toolbar">
					<div>
						<div class="pm-card-title">Eligibility preview</div>
						<div class="pm-card-sub">Nothing has been saved. Review, then run promotion.</div>
					</div>
					<span class="pm-spacer"></span>
					<button class="pm-btn primary" data-act="run">&#9654; Run Promotion &middot; Year ${esc(P.key.from_year)} &rarr; ${esc(P.key.to_year)}</button>
				</div>
				<div class="pm-toolbar">
					<span id="pm-eval-chips"></span>
					<div class="pm-srch"><span class="pm-srch-ico">&#128269;</span>
						<input type="text" class="pm-inp" id="pm-eval-search" placeholder="Search name or ID…" value="${esc(S.previewSearch)}"></div>
				</div>
				<div class="pm-table-wrap">
					<table class="pm-tbl">
						<thead><tr>
							<th>#</th><th>Student</th><th class="c">CGPA</th>
							<th class="c" title="Courses failed this academic year">Failed</th>
							<th class="c" title="Average attendance this academic year">Avg Att</th>
							<th class="c" title="Courses below their minimum attendance">Short courses</th>
							<th class="c" title="Courses still short of attendance even after FA/MFA condonation (carried forward)">Short after FA/MFA</th>
							<th class="c" title="CGPA check">&#10003; CGPA</th><th class="c" title="Backlog (failed courses) check">&#10003; Failed</th>
							<th class="c" title="Average attendance check">&#10003; Att</th><th class="c" title="Attendance shortage check">&#10003; Short</th>
							<th class="c" title="Carry-forward (still short after FA/MFA) check">&#10003; FA/MFA</th><th class="c" title="Fee due check">&#10003; Fee</th>
							<th>Result</th><th>Reason</th>
						</tr></thead>
						<tbody id="pm-eval-tbody"></tbody>
					</table>
				</div>
			</div>
		`);
		renderEvalRows();
	}

	function renderEvalRows() {
		if (!S.preview) return;
		$('#pm-eval-chips').html(chipsHtml(S.previewFilter, S.preview.counts, false));
		var rows = applyStudentFilter(S.preview.students, S.previewFilter, S.previewSearch, false);
		var tb = document.getElementById('pm-eval-tbody');
		if (!tb) return;
		if (!rows.length) {
			tb.innerHTML = '<tr><td colspan="15"><div class="pm-empty"><div>No students match this filter.</div></div></td></tr>';
			return;
		}
		tb.innerHTML = rows.map(function (r, i) {
			return '<tr>'
				+ '<td class="pm-num">' + (i + 1) + '</td>'
				+ '<td>' + studentCell(r) + '</td>'
				+ '<td class="c"><b>' + num(r.current_cgpa, 2) + '</b></td>'
				+ '<td class="c">' + (r.backlog_count != null ? esc(r.backlog_count) : '—') + '</td>'
				+ '<td class="c">' + num(r.attendance_percent, 1) + '%</td>'
				+ '<td class="c">' + (r.shortage_course_count != null ? esc(r.shortage_course_count) : '—') + '</td>'
				+ '<td class="c">' + (r.cf_fa_shortage_count != null ? esc(r.cf_fa_shortage_count) : '—') + '</td>'
				+ '<td class="c">' + chk(r.cgpa_result) + '</td>'
				+ '<td class="c">' + chk(r.backlog_result) + '</td>'
				+ '<td class="c">' + chk(r.attendance_result) + '</td>'
				+ '<td class="c">' + chk(r.shortage_course_result) + '</td>'
				+ '<td class="c">' + chk(r.cf_result) + '</td>'
				+ '<td class="c">' + chk(r.fee_due_result) + '</td>'
				+ '<td>' + badge(r.promotion_status) + '</td>'
				+ '<td>' + reasonsHtml(r.remarks, r.promotion_status) + '</td>'
				+ '</tr>';
		}).join('');
	}

	$root.on('click', '#pm-eval-chips .pm-chip', function () {
		S.previewFilter = $(this).data('filter');
		renderEvalRows();
	});
	$root.on('input', '#pm-eval-search', function () {
		S.previewSearch = (this.value || '').toLowerCase().trim();
		renderEvalRows();
	});

	// ── Run Promotion (manual) ────────────────────────────────────────────────
	$root.on('click', '#pm-run-btn, [data-act="run"]', function () {
		if (S.running) return;
		var f = currentFilters();
		var err = validateFilters(f);
		if (err) { frappe.show_alert({ message: err, indicator: 'red' }); return; }

		var $btn = $('#pm-run-btn');
		// Always evaluate against current data right before running, so the
		// summary the user approves matches what will be saved.
		$btn.prop('disabled', true).html('Evaluating…');
		fetchPreview(f).then(function (P) {
			$btn.html('&#9654; Run Promotion');
			updateStepper();
			if (!P.students.length) {
				switchView('eval');
				frappe.msgprint({
					title: __('No students to promote'), indicator: 'orange',
					message: __('No Active students are in Year {0} for this selection.', [f.from_year]),
				});
				return;
			}
			openRunDialog(P);
		}).catch(function () {
			$btn.html('&#9654; Run Promotion');
			updateStepper();
		});
	});

	function openRunDialog(P) {
		var k = P.key, c = P.counts;
		var policy = S.policies[k.policy] || {};
		var prior = historyEntry(k);
		var html = '<div class="pm-run-sum">'
			+ '<div class="pm-run-tile g"><div class="v">' + (c.promoted || 0) + '</div><div class="l">Will be promoted</div></div>'
			+ '<div class="pm-run-tile r"><div class="v">' + (c.not_promoted || 0) + '</div><div class="l">Not promoted</div></div>'
			+ '<div class="pm-run-tile a"><div class="v">' + (c.conditional || 0) + '</div><div class="l">Conditional (held)</div></div>'
			+ '</div>'
			+ '<div class="pm-run-meta">'
			+ '<span>Programme</span><span>' + esc(k.program) + '</span>'
			+ '<span>Academic Year</span><span>' + esc(k.academic_year) + '</span>'
			+ '<span>Policy</span><span>' + esc(policy.title || k.policy) + '</span>'
			+ '<span>Promotion</span><span>Year ' + esc(k.from_year) + ' &rarr; Year ' + esc(k.to_year) + ' &middot; ' + (c.total || 0) + ' student(s)</span>'
			+ '</div>'
			+ (policy.auto_update_student_year
				? '<div class="pm-notice info" style="margin-top:0"><span class="pm-notice-body">Eligible students will be moved to <b>Year ' + esc(k.to_year)
					+ '</b> and enrolled into next year\'s Batch. Every decision is saved to the Promotion Log.</span></div>'
				: '<div class="pm-notice warn" style="margin-top:0"><span class="pm-notice-body"><b>Auto-update is off on this policy</b> — decisions will be logged, but student years and enrollments will not change.</span></div>')
			+ (prior
				? '<div class="pm-notice warn"><span class="pm-notice-body">This selection was run before. Log entries for these ' + (c.total || 0)
					+ ' student(s) will be replaced; students already promoted keep theirs.</span></div>'
				: '');

		var d = new frappe.ui.Dialog({
			title: __('Run Promotion'),
			fields: [{ fieldtype: 'HTML', fieldname: 'summary', options: html }],
			primary_action_label: __('Run Promotion for {0} student(s)', [c.total || 0]),
			primary_action: function () {
				d.hide();
				runPromotion(k);
			},
			secondary_action_label: __('Review preview first'),
			secondary_action: function () {
				d.hide();
				switchView('eval');
			},
		});
		d.$wrapper.addClass('pm-run-dialog');
		d.show();
	}

	function runPromotion(k) {
		if (!sameKey(k, currentFilters())) {
			frappe.msgprint(__('The selection changed. Please click Run Promotion again.'));
			return;
		}
		S.running = true;
		updateStepper();
		$('#pm-run-btn').html('Running…');
		frappe.call({
			method: API + 'confirm_promotion',
			args: {
				program: k.program, academic_year: k.academic_year,
				from_year: k.from_year, to_year: k.to_year, policy_name: k.policy,
			},
			freeze: true,
			freeze_message: __('Running promotion…'),
			callback: function (r) {
				if (!r.message) return;
				var m = r.message;
				S.lastRun = { key: k, result: m };
				frappe.show_alert({
					message: __('Promotion complete: {0} promoted, {1} not promoted, {2} conditional', [m.promoted, m.not_promoted, m.conditional]),
					indicator: 'green',
				}, 7);
				if (m.enrollment_failures && m.enrollment_failures.length) {
					frappe.msgprint({
						title: __('{0} promoted student(s) could not be enrolled in next year\'s Batch', [m.enrollment_failures.length]),
						indicator: 'orange',
						message: m.enrollment_failures.map(function (f) {
							return '<b>' + esc(f.student) + '</b>: ' + esc(f.error);
						}).join('<br>') + '<br><br>' + __('They are marked Promoted but stay in their current year and Batch until enrollment succeeds. Fix the cause (e.g. create the target Batch) and use <b>Retry Enrollment</b> in the Promotion Log.'),
					});
				}
				// Promoted students have left Year k.from_year; the preview is now out of date.
				S.preview = null;
				renderEval();
				openLog({ policy: k.policy, from_year: k.from_year, to_year: k.to_year });
				loadHistory();
			},
			always: function () {
				S.running = false;
				$('#pm-run-btn').html('&#9654; Run Promotion');
				updateStepper();
			},
		});
	}

	// ── Promotion Log ─────────────────────────────────────────────────────────
	var _logReq = 0;
	function openLog(key) {
		var changed = !S.logKey || S.logKey.policy !== key.policy
			|| S.logKey.from_year !== key.from_year || S.logKey.to_year !== key.to_year;
		S.logKey = key;
		if (changed) { S.logFilter = 'all'; S.logSearch = ''; S.log = null; }
		loadLog(true);
	}

	function loadLog(focus) {
		if (!S.logKey) { renderLog(); return; }
		var req = ++_logReq;
		frappe.call({
			method: API + 'get_promotion_log',
			args: { policy_name: S.logKey.policy, from_year: S.logKey.from_year, to_year: S.logKey.to_year },
			callback: function (r) {
				if (req !== _logReq) return;
				S.log = r.message || null;
				renderLog();
				if (focus) switchView('log'); else updateStepper();
			},
		});
	}

	function renderLog() {
		var $v = $('#pm-view-log');
		var L = S.log;
		if (!S.logKey || !L) {
			$('#vc-log').text(0);
			$v.html(emptyState('&#128203;', 'No log open',
				'Run a promotion to see its log here, or open a past run from <b>History</b>.',
				'<button class="pm-btn sm" data-act="goto-hist">&#128339; Open History</button>'));
			return;
		}
		var c = L.counts || {};
		$('#vc-log').text(c.total || 0);
		var k = S.logKey;
		var title = (L.policy && L.policy.title) || k.policy;
		if (!c.total) {
			$v.html(emptyState('&#128203;', 'Nothing logged yet',
				'No promotion has been run for <b>' + esc(title) + '</b>, Year ' + esc(k.from_year) + ' &rarr; ' + esc(k.to_year) + '.'));
			return;
		}
		var last = L.last_processed_on ? frappe.datetime.str_to_user(L.last_processed_on) : '—';
		var autoOff = L.policy && !L.policy.auto_update_student_year;
		var pct = function (n) { return c.total ? (100 * (n || 0) / c.total).toFixed(2) : 0; };
		var justRan = S.lastRun && S.lastRun.key.policy === k.policy
			&& S.lastRun.key.from_year === k.from_year && S.lastRun.key.to_year === k.to_year;

		$v.html(`
			${justRan ? '<div class="pm-notice ok" style="margin:0 0 14px;"><span class="pm-notice-body">&#10003; <b>Promotion run completed.</b> '
				+ (S.lastRun.result.promoted || 0) + ' promoted, ' + (S.lastRun.result.not_promoted || 0) + ' not promoted, '
				+ (S.lastRun.result.conditional || 0) + ' conditional. Resolve exceptions below or download the lists.</span></div>' : ''}
			<div class="pm-band">
				<div class="pm-band-top">
					<div>
						<div class="pm-band-kicker">Promotion Log &middot; ${esc(k.policy)}</div>
						<div class="pm-band-title">${esc(title)} &nbsp;&middot;&nbsp; Year ${esc(k.from_year)} &rarr; Year ${esc(k.to_year)}</div>
					</div>
					<div class="pm-band-meta">Last processed<br><b>${esc(last)}</b></div>
				</div>
				<div class="pm-band-stats">
					<div class="pm-band-stat"><div class="v">${c.total || 0}</div><div class="l">Total</div></div>
					<div class="pm-band-stat g"><div class="v">${c.promoted || 0}</div><div class="l">Promoted</div></div>
					<div class="pm-band-stat r"><div class="v">${c.not_promoted || 0}</div><div class="l">Not Promoted</div></div>
					<div class="pm-band-stat a"><div class="v">${c.conditional || 0}</div><div class="l">Conditional</div></div>
					<div class="pm-band-stat b"><div class="v">${c.enrolled || 0}</div><div class="l">Enrolled next year</div></div>
					<div class="pm-band-stat r"><div class="v">${c.enrollment_failed || 0}</div><div class="l">Enrollment failed</div></div>
				</div>
				<div class="pm-meter">
					<span style="width:${pct(c.promoted)}%;background:#22c55e"></span>
					<span style="width:${pct(c.conditional)}%;background:#f59e0b"></span>
					<span style="width:${pct(c.not_promoted)}%;background:#ef4444"></span>
				</div>
				<div class="pm-meter-legend">
					<span><i style="background:#22c55e"></i>Promoted ${pct(c.promoted) ? Math.round(pct(c.promoted)) : 0}%</span>
					<span><i style="background:#f59e0b"></i>Conditional ${pct(c.conditional) ? Math.round(pct(c.conditional)) : 0}%</span>
					<span><i style="background:#ef4444"></i>Not promoted ${pct(c.not_promoted) ? Math.round(pct(c.not_promoted)) : 0}%</span>
				</div>
			</div>
			${autoOff ? '<div class="pm-notice warn" style="margin:0 0 14px;"><span class="pm-notice-body">&#9888; Auto-update is off on this policy — decisions are logged, but student years and enrollments were not changed.</span></div>' : ''}
			<div class="pm-card flush">
				<div class="pm-dl">
					<span class="pm-dl-lbl">&#8659; Download Excel</span>
					<button class="pm-btn sm" data-dl="promoted">&#9989; Promoted (${c.promoted || 0})</button>
					<button class="pm-btn sm" data-dl="not_promoted">&#10060; Not Promoted (${c.not_promoted || 0})</button>
					<button class="pm-btn sm" data-dl="conditional">&#9201; Conditional (${c.conditional || 0})</button>
					${c.enrollment_failed ? `<button class="pm-btn sm" data-dl="enrollment_failed">&#9888; Enrollment Failed (${c.enrollment_failed})</button>` : ''}
					<button class="pm-btn sm primary" data-dl="all">&#128196; Full Log (${c.total || 0})</button>
				</div>
				<div class="pm-toolbar">
					<span id="pm-log-chips"></span>
					<div class="pm-srch"><span class="pm-srch-ico">&#128269;</span>
						<input type="text" class="pm-inp" id="pm-log-search" placeholder="Search name or ID…" value="${esc(S.logSearch)}"></div>
					<span class="pm-spacer"></span>
					${c.enrollment_failed ? `<button class="pm-btn sm" data-act="retry-all">&#8635; Retry failed enrollments (${c.enrollment_failed})</button>` : ''}
					<button class="pm-btn sm" data-act="reload-log" title="Refresh">&#8635; Refresh</button>
				</div>
				<div class="pm-table-wrap">
					<table class="pm-tbl">
						<thead><tr>
							<th>#</th><th>Student</th><th class="c">CGPA</th><th>Result</th><th>Reason</th><th>Next-year Enrollment</th><th>Processed</th><th>Action</th>
						</tr></thead>
						<tbody id="pm-log-tbody"></tbody>
					</table>
				</div>
			</div>
		`);
		renderLogRows();
	}

	function enrollmentCell(r) {
		if (r.enrollment_status === 'Enrolled') {
			return '<span class="pm-bdg bdg-enr">Enrolled</span>'
				+ (r.to_enrollment ? '<div class="pm-sid" style="margin-top:4px;"><a href="/app/student-enrollment/'
					+ encodeURIComponent(r.to_enrollment) + '" target="_blank">' + esc(r.to_enrollment) + '</a></div>' : '');
		}
		if (r.enrollment_status === 'Failed') return '<span class="pm-bdg bdg-fail">Failed</span>';
		return '<span class="pm-muted">—</span>';
	}

	function logActions(r) {
		var b = bucket(r.promotion_status);
		var out = [];
		if (b !== 'promoted') {
			out.push('<button class="pm-btn xs green" data-row-act="promote" data-row="' + esc(r.name) + '">&#8613; Promote Anyway</button>');
		}
		if (b === 'conditional' || (b === 'promoted' && r.enrollment_status !== 'Enrolled')) {
			out.push('<button class="pm-btn xs ghost-red" data-row-act="hold" data-row="' + esc(r.name) + '">Mark Not Promoted</button>');
		}
		if (b === 'promoted' && r.enrollment_status === 'Failed') {
			out.push('<button class="pm-btn xs" data-row-act="retry" data-row="' + esc(r.name) + '">&#8635; Retry Enrollment</button>');
		}
		return out.length ? '<div class="pm-actions">' + out.join('') + '</div>' : '<span class="pm-muted">—</span>';
	}

	function renderLogRows() {
		if (!S.log) return;
		$('#pm-log-chips').html(chipsHtml(S.logFilter, S.log.counts || {}, true));
		var rows = applyStudentFilter(S.log.records || [], S.logFilter, S.logSearch, true);
		var tb = document.getElementById('pm-log-tbody');
		if (!tb) return;
		if (!rows.length) {
			tb.innerHTML = '<tr><td colspan="8"><div class="pm-empty"><div>No students match this filter.</div></div></td></tr>';
			return;
		}
		tb.innerHTML = rows.map(function (r, i) {
			var ovr = r.manual_override && r.override_reason
				? '<div class="pm-ovr">&#9998; ' + esc(r.override_reason) + '</div>' : '';
			var reason = r.enrollment_status === 'Failed'
				? '<div class="pm-reasons"><span class="x">&#8226; ' + esc(r.remarks || 'Enrollment failed') + '</span></div>'
				: reasonsHtml(r.manual_override ? '' : r.remarks, r.promotion_status);
			return '<tr>'
				+ '<td class="pm-num">' + (i + 1) + '</td>'
				+ '<td>' + studentCell(r) + '</td>'
				+ '<td class="c"><b>' + num(r.current_cgpa, 2) + '</b></td>'
				+ '<td>' + badge(r.promotion_status) + '</td>'
				+ '<td>' + reason + ovr + '</td>'
				+ '<td>' + enrollmentCell(r) + '</td>'
				+ '<td class="pm-muted">' + (r.processed_on ? esc(frappe.datetime.str_to_user(r.processed_on)) : '—')
				+ (r.processed_by ? '<div>' + esc(r.processed_by) + '</div>' : '') + '</td>'
				+ '<td>' + logActions(r) + '</td>'
				+ '</tr>';
		}).join('');
	}

	function findLogRow(name) {
		return ((S.log && S.log.records) || []).filter(function (r) { return r.name === name; })[0];
	}

	function afterLogChange() {
		loadLog();
		loadHistory();
		// Student years may have changed — any open preview is out of date.
		if (S.preview) { S.preview = null; renderEval('stale'); updateStepper(); }
	}

	$root.on('click', '#pm-log-chips .pm-chip', function () {
		S.logFilter = $(this).data('filter');
		renderLogRows();
	});
	$root.on('input', '#pm-log-search', function () {
		S.logSearch = (this.value || '').toLowerCase().trim();
		renderLogRows();
	});

	$root.on('click', '[data-dl]', function () {
		if (!S.logKey) return;
		window.open('/api/method/' + API + 'download_promotion_list'
			+ '?policy_name=' + encodeURIComponent(S.logKey.policy)
			+ '&list_type=' + encodeURIComponent($(this).data('dl'))
			+ '&from_year=' + encodeURIComponent(S.logKey.from_year)
			+ '&to_year=' + encodeURIComponent(S.logKey.to_year), '_blank');
	});

	$root.on('click', '[data-row-act]', function () {
		var act = $(this).data('row-act');
		var r = findLogRow($(this).data('row'));
		if (!r) return;
		if (act === 'retry') { retryEnrollment([r.name]); return; }

		var promote = act === 'promote';
		var d = new frappe.ui.Dialog({
			title: promote ? __('Promote Anyway') : __('Mark Not Promoted'),
			fields: [
				{
					fieldtype: 'HTML', fieldname: 'info',
					options: '<div class="pm-notice ' + (promote ? 'info' : 'warn') + '" style="margin:0 0 12px;"><span class="pm-notice-body">'
						+ (promote
							? __('<b>{0}</b> will be promoted to Year {1}, overriding the policy result. Their year is updated and they are enrolled in next year\'s Batch (if the policy has auto-update on).', [esc(r.student_name || r.student), esc(r.target_year)])
							: __('<b>{0}</b> will be kept in Year {1}.', [esc(r.student_name || r.student), esc(r.current_year)]))
						+ '</span></div>',
				},
				{ label: __('Reason'), fieldname: 'reason', fieldtype: 'Small Text', reqd: 1 },
			],
			primary_action_label: promote ? __('Promote') : __('Mark Not Promoted'),
			primary_action: function (vals) {
				d.get_primary_btn().prop('disabled', true);
				frappe.call({
					method: API + 'save_override',
					args: {
						record_name: r.name,
						new_status: promote ? 'Override - Promoted' : 'Override - Not Promoted',
						reason: vals.reason,
					},
					callback: function (res) {
						if (!res.message) return;
						d.hide();
						if (res.message.error) {
							frappe.msgprint({
								title: __('Promoted, but enrollment failed'), indicator: 'orange',
								message: esc(res.message.error) + '<br><br>' + __('Use Retry Enrollment once the cause is fixed.'),
							});
						} else {
							frappe.show_alert({ message: __('Override saved'), indicator: 'green' });
						}
						afterLogChange();
					},
					always: function () { d.get_primary_btn().prop('disabled', false); },
				});
			},
		});
		d.$wrapper.addClass('pm-run-dialog');
		d.show();
	});

	$root.on('click', '[data-act="retry-all"]', function () {
		var names = ((S.log && S.log.records) || []).filter(function (r) {
			return PRO.indexOf(r.promotion_status) > -1 && r.enrollment_status === 'Failed';
		}).map(function (r) { return r.name; });
		if (!names.length) return;
		frappe.confirm(__('Retry next-year enrollment for {0} student(s)?', [names.length]), function () {
			retryEnrollment(names);
		});
	});
	$root.on('click', '[data-act="reload-log"]', function () { loadLog(); });
	$root.on('click', '[data-act="goto-hist"]', function () { switchView('hist'); });
	$root.on('click', '[data-act="open-prior"]', function () {
		var f = currentFilters();
		openLog({ policy: f.policy, from_year: f.from_year, to_year: f.to_year });
	});

	function retryEnrollment(names) {
		frappe.call({
			method: API + 'retry_enrollment',
			args: { record_names: names },
			freeze: true,
			freeze_message: __('Retrying enrollment…'),
			callback: function (r) {
				var m = r.message || { enrolled: [], failed: [] };
				if (m.failed.length) {
					frappe.msgprint({
						title: __('{0} enrolled, {1} still failing', [m.enrolled.length, m.failed.length]),
						indicator: 'orange',
						message: m.failed.map(function (f) { return '<b>' + esc(f.student) + '</b>: ' + esc(f.error); }).join('<br>'),
					});
				} else {
					frappe.show_alert({ message: __('{0} student(s) enrolled', [m.enrolled.length]), indicator: 'green' });
				}
				afterLogChange();
			},
		});
	}

	// ── History ───────────────────────────────────────────────────────────────
	var _histReq = 0;
	function loadHistory() {
		var f = currentFilters();
		if (!f.program || !f.academic_year) { S.history = []; renderHistory(); updatePriorRunNotice(); return; }
		var req = ++_histReq;
		frappe.call({
			method: API + 'get_promotion_history',
			args: { program: f.program, academic_year: f.academic_year },
			callback: function (r) {
				if (req !== _histReq) return;
				S.history = r.message || [];
				renderHistory();
				updatePriorRunNotice();
			},
		});
	}

	function renderHistory() {
		var $v = $('#pm-view-hist');
		var H = S.history || [];
		$('#vc-hist').text(H.length);
		var f = currentFilters();
		if (!f.program || !f.academic_year) {
			$v.html(emptyState('&#128339;', 'No history to show', 'Select a Programme and Academic Year to see past promotion runs.'));
			return;
		}
		if (!H.length) {
			$v.html(emptyState('&#128339;', 'No promotion runs yet', 'Nothing has been run for <b>' + esc(f.program) + '</b> / <b>' + esc(f.academic_year) + '</b>.'));
			return;
		}
		$v.html('<div class="pm-card flush"><div class="pm-toolbar"><div><div class="pm-card-title">Promotion runs</div>'
			+ '<div class="pm-card-sub">' + esc(f.program) + ' &middot; ' + esc(f.academic_year) + '</div></div></div>'
			+ '<div class="pm-table-wrap"><table class="pm-tbl"><thead><tr>'
			+ '<th>Policy</th><th>Year step</th><th class="c">Total</th><th class="c">Promoted</th><th class="c">Not Promoted</th><th class="c">Conditional</th><th class="c">Enr. Failed</th><th>Last run</th><th></th>'
			+ '</tr></thead><tbody>'
			+ H.map(function (h) {
				return '<tr>'
					+ '<td><div class="pm-sname">' + esc(h.policy_title || h.promotion_policy) + '</div><div class="pm-sid">'
					+ '<a href="/app/promotion-policy/' + encodeURIComponent(h.promotion_policy) + '" target="_blank">' + esc(h.promotion_policy) + '</a></div></td>'
					+ '<td>Year ' + esc(h.current_year) + ' &rarr; ' + esc(h.target_year) + '</td>'
					+ '<td class="c"><b>' + (h.total || 0) + '</b></td>'
					+ '<td class="c"><span class="pm-bdg bdg-pro">' + (h.promoted || 0) + '</span></td>'
					+ '<td class="c"><span class="pm-bdg bdg-not">' + (h.not_promoted || 0) + '</span></td>'
					+ '<td class="c"><span class="pm-bdg bdg-cond">' + (h.conditional || 0) + '</span></td>'
					+ '<td class="c">' + (h.enrollment_failed ? '<span class="pm-bdg bdg-fail">' + h.enrollment_failed + '</span>' : '<span class="pm-muted">0</span>') + '</td>'
					+ '<td class="pm-muted">' + (h.last_processed_on ? esc(frappe.datetime.str_to_user(h.last_processed_on)) : '—') + '</td>'
					+ '<td><button class="pm-btn xs primary" data-hist-open="' + esc(h.promotion_policy) + '" data-fy="' + esc(h.current_year)
					+ '" data-ty="' + esc(h.target_year) + '">Open Log &rarr;</button></td>'
					+ '</tr>';
			}).join('')
			+ '</tbody></table></div></div>');
	}

	$root.on('click', '[data-hist-open]', function () {
		openLog({
			policy: String($(this).data('hist-open')),
			from_year: parseInt($(this).data('fy'), 10) || 0,
			to_year: parseInt($(this).data('ty'), 10) || 0,
		});
	});

	// ── View tabs ─────────────────────────────────────────────────────────────
	$root.on('click', '.pm-view-tab', function () { switchView($(this).data('view')); });

	// ── Official (course-wise) report ─────────────────────────────────────────
	$root.on('click', '[data-act="official-dl"]', function () { openOfficialDownload(); });

	function openOfficialDownload() {
		var progOptions = Array.from($('#pm-prog option')).map(function (o) { return o.value; }).filter(Boolean);
		var ayOptions = Array.from($('#pm-ay option')).map(function (o) { return o.value; }).filter(Boolean);
		var f = currentFilters();

		var dlDialog = new frappe.ui.Dialog({
			title: __('Download Official Promotion Report'),
			fields: [
				{
					label: __('University / Institution Name'), fieldname: 'university_name', fieldtype: 'Data',
					description: __('Printed at the top of the sheet (optional)'),
				},
				{ fieldtype: 'Column Break' },
				{
					label: __('Programme'), fieldname: 'program', fieldtype: 'Select', reqd: 1,
					options: [''].concat(progOptions).join('\n'), default: f.program,
				},
				{ fieldtype: 'Section Break' },
				{
					label: __('Academic Year'), fieldname: 'academic_year', fieldtype: 'Select', reqd: 1,
					options: [''].concat(ayOptions).join('\n'), default: f.academic_year,
				},
				{ fieldtype: 'Column Break' },
				{
					fieldname: 'info', fieldtype: 'HTML',
					options: '<div style="font-size:12px;color:var(--text-muted);padding-top:18px;">'
						+ '&#9432; One sheet per year level, from the confirmed Promotion Log.<br>'
						+ 'Sections: Promoted &middot; Conditional &middot; Re-admitted (with reason),<br>'
						+ 'term-wise Failed (F) / Attendance-shortage (AS) and C/C+ improvement courses.</div>',
				},
			],
			primary_action_label: __('Download Excel'),
			primary_action: function (vals) {
				if (!vals.program || !vals.academic_year) {
					frappe.msgprint(__('Please select both Programme and Academic Year.'));
					return;
				}
				dlDialog.hide();
				window.open('/api/method/' + API + 'download_formatted_promotion_list'
					+ '?program=' + encodeURIComponent(vals.program)
					+ '&academic_year=' + encodeURIComponent(vals.academic_year)
					+ '&university_name=' + encodeURIComponent(vals.university_name || ''), '_blank');
			},
		});
		dlDialog.$wrapper.addClass('pm-run-dialog');
		dlDialog.show();
	}
	// Kept for any external caller of the old global.
	window.pmOfficialDl = openOfficialDownload;

	// ── Initial render ────────────────────────────────────────────────────────
	renderEval();
	renderLog();
	renderHistory();
	updateStepper();
};
