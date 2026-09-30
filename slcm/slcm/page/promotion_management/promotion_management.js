frappe.pages['promotion-management'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Promotion Management',
		single_column: true,
	});

	var API = 'slcm.slcm.page.promotion_management.promotion_management.';
	var PRO = ['Promoted', 'Override - Promoted'];
	var NOT = ['Not Promoted', 'Override - Not Promoted'];

	// ── CSS: NLS maroon as the single accent, neutral greys for everything else ──
	if (!document.getElementById('pm-style-v9')) {
		var style = document.createElement('style');
		style.id = 'pm-style-v9';
		style.textContent = `
		.pm-wrap {
			--m:#920c24; --m-dark:#6e0919; --m-text:#920c24;
			--card:var(--card-bg,#fff); --text:var(--text-color,#1f2937); --muted:var(--text-muted,#6b7280);
			--line:var(--border-color,#e5e7eb); --subtle:var(--subtle-fg,#f7f7f8); --control:var(--control-bg,#f4f5f6);
			--ok:#15803d; --bad:#b91c1c; --warn:#b45309;
			font-family:var(--font-stack,'Inter',sans-serif); color:var(--text); padding-bottom:48px;
		}
		[data-theme="dark"] .pm-wrap { --m-text:#f08a9c; --ok:#22c55e; --bad:#ef4444; --warn:#f59e0b; }
		.pm-wrap *, .pm-wrap *::before, .pm-wrap *::after { box-sizing:border-box; }
		.pm-hidden { display:none !important; }

		.pm-head { background:var(--m); color:#fff; border-radius:12px; padding:16px 20px; margin-bottom:14px;
			display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
		.pm-head-title { font-size:17px; font-weight:700; }
		.pm-head-sub { font-size:12px; margin-top:2px; }
		.pm-head-sub a { color:#fff; text-decoration:underline; }
		.pm-head-actions { margin-left:auto; display:flex; gap:8px; }
		.pm-head-btn { height:32px; padding:0 12px; border-radius:7px; border:1px solid #fff; background:transparent; color:#fff;
			font-size:12.5px; font-weight:600; cursor:pointer; display:inline-flex; align-items:center; text-decoration:none; }
		.pm-head-btn:hover { background:#fff; color:var(--m); text-decoration:none; }

		.pm-card { background:var(--card); border:1px solid var(--line); border-radius:12px; margin-bottom:14px; }
		.pm-card-body { padding:18px 20px; }
		.pm-card-foot { padding:12px 20px; border-top:1px solid var(--line); display:flex; gap:12px; align-items:center; flex-wrap:wrap; }

		.pm-grid { display:grid; gap:12px 14px; align-items:end;
			grid-template-columns:minmax(190px,1.3fr) minmax(150px,1fr) minmax(230px,1.6fr) 96px 96px; }
		@media (max-width:1100px) { .pm-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
		@media (max-width:560px)  { .pm-grid { grid-template-columns:1fr; } }
		.pm-fl { font-size:11px; color:var(--muted); font-weight:600; margin-bottom:6px; text-transform:uppercase; letter-spacing:.4px; }
		.pm-sel, .pm-inp { height:38px; width:100%; border:1px solid var(--line); border-radius:8px; padding:0 11px; font-size:13px;
			background:var(--card); color:var(--text); outline:none; }
		.pm-sel:focus, .pm-inp:focus { border-color:var(--m); box-shadow:0 0 0 1px var(--m); }
		.pm-sel:disabled { background:var(--control); cursor:not-allowed; }

		.pm-checks { margin-top:14px; font-size:12.5px; color:var(--muted); display:flex; flex-wrap:wrap; gap:6px 16px; align-items:center; }
		.pm-checks b { color:var(--text); font-weight:600; }
		.pm-check-on { color:var(--text); cursor:help; }
		.pm-check-on::before { content:'✓ '; color:var(--m-text); font-weight:700; }
		.pm-link { color:var(--m-text); font-weight:600; cursor:pointer; text-decoration:underline; }
		.pm-help { margin-top:10px; border:1px solid var(--line); border-radius:8px; font-size:12px; overflow:hidden; }
		.pm-help table { width:100%; border-collapse:collapse; }
		.pm-help td { padding:8px 12px; border-top:1px solid var(--line); vertical-align:top; }
		.pm-help tr:first-child td { border-top:none; }
		.pm-help td:first-child { font-weight:600; white-space:nowrap; width:210px; }

		.pm-notice { margin-top:12px; padding:9px 12px; border-radius:8px; font-size:12.5px; border:1px solid var(--line);
			border-left:3px solid var(--warn); background:var(--card); }
		.pm-notice.err { border-left-color:var(--bad); }

		.pm-steps { display:flex; align-items:center; gap:6px; font-size:12.5px; color:var(--muted); flex-wrap:wrap; }
		.pm-step { display:inline-flex; align-items:center; gap:6px; }
		.pm-step i { font-style:normal; width:20px; height:20px; border-radius:50%; border:1px solid var(--line);
			display:inline-flex; align-items:center; justify-content:center; font-size:11px; font-weight:700; }
		.pm-step.done { color:var(--text); } .pm-step.done i { background:var(--m); border-color:var(--m); color:#fff; }
		.pm-step.active { color:var(--m-text); font-weight:700; } .pm-step.active i { border:2px solid var(--m); color:var(--m-text); }
		.pm-step-sep { width:18px; height:1px; background:var(--line); }
		.pm-status { flex:1; min-width:260px; font-size:12.5px; color:var(--muted); }
		.pm-status b { color:var(--text); }

		.pm-btn { height:36px; padding:0 14px; border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--text);
			cursor:pointer; font-size:13px; font-weight:600; display:inline-flex; align-items:center; gap:6px; white-space:nowrap; }
		.pm-btn:hover { border-color:var(--m); color:var(--m-text); }
		.pm-btn:disabled { opacity:.5; cursor:not-allowed; pointer-events:none; }
		.pm-btn.primary { background:var(--m); border-color:var(--m); color:#fff; }
		.pm-btn.primary:hover { background:var(--m-dark); border-color:var(--m-dark); color:#fff; }
		.pm-btn.sm { height:30px; padding:0 11px; font-size:12px; }
		.pm-btn.xs { height:26px; padding:0 9px; font-size:11.5px; border-radius:6px; }

		.pm-tabs { display:flex; gap:20px; border-bottom:1px solid var(--line); margin:4px 0 14px; }
		.pm-tab { padding:9px 2px; font-size:13.5px; font-weight:600; color:var(--muted); cursor:pointer; border-bottom:2px solid transparent;
			margin-bottom:-1px; user-select:none; }
		.pm-tab:hover { color:var(--text); }
		.pm-tab.active { color:var(--m-text); border-bottom-color:var(--m); }
		.pm-tab .n { font-weight:500; color:var(--muted); margin-left:5px; }

		.pm-bar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; padding:12px 16px; border-bottom:1px solid var(--line); }
		.pm-bar-title { font-size:14px; font-weight:700; }
		.pm-bar-meta { font-size:12px; color:var(--muted); margin-top:2px; }
		.pm-spacer { flex:1; }
		.pm-chips { display:flex; gap:4px; flex-wrap:wrap; }
		.pm-chip { padding:4px 10px; border-radius:6px; font-size:12.5px; color:var(--muted); cursor:pointer; user-select:none; }
		.pm-chip:hover { color:var(--text); background:var(--subtle); }
		.pm-chip.active { color:var(--m-text); background:var(--subtle); font-weight:700; }
		/* Frappe DataTable — sortable, per-column filters, virtual scrolling for large lists */
		.pm-dt { font-size:13px; }
		.pm-dt .dt-cell__content { font-size:13px; }
		.pm-dt .dt-scrollable { max-height:62vh; }
		.pm-dt .dt-cell--header { background:var(--subtle); }
		.pm-dt .dt-cell--header .dt-cell__content { font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.4px; }
		.pm-dt .dt-row:hover .dt-cell { background:var(--subtle); }
		.pm-dt .dt-filter { font-size:12px; }
		.pm-dt .pm-ell { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; display:block; max-width:100%; }
		.pm-dt .pm-actions { flex-wrap:nowrap; }
		.pm-draftnote { padding:10px 16px; font-size:12.5px; border-bottom:1px solid var(--line); border-left:3px solid var(--m); }

		.pm-menu-wrap { position:relative; }
		.pm-menu { position:absolute; right:0; top:34px; z-index:20; min-width:210px; background:var(--card); border:1px solid var(--line);
			border-radius:8px; box-shadow:0 6px 20px rgba(0,0,0,.12); padding:4px; }
		.pm-menu div { padding:7px 10px; font-size:12.5px; border-radius:6px; cursor:pointer; }
		.pm-menu div:hover { background:var(--subtle); color:var(--m-text); }

		.pm-table-wrap { overflow-x:auto; }
		table.pm-tbl { width:100%; border-collapse:collapse; font-size:13px; }
		table.pm-tbl th { text-align:left; padding:9px 14px; font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase;
			letter-spacing:.4px; background:var(--subtle); border-bottom:1px solid var(--line); white-space:nowrap; }
		table.pm-tbl td { padding:10px 14px; border-bottom:1px solid var(--line); vertical-align:middle; overflow-wrap:anywhere; }
		table.pm-tbl { table-layout:fixed; min-width:820px; }
		table.pm-tbl th.pm-c, table.pm-tbl td.pm-c { text-align:center; }
		table.pm-tbl th.pm-n, table.pm-tbl td.pm-n { text-align:right; }
		table.pm-tbl tr:last-child td { border-bottom:none; }
		table.pm-tbl tbody tr:hover td { background:var(--subtle); }
		.pm-sname { font-weight:600; }
		.pm-sid { font-size:11.5px; color:var(--muted); }
		.pm-sid a, a.pm-sid { color:var(--m-text); }
		.pm-muted { color:var(--muted); font-size:12px; }
		.pm-reason { font-size:12px; color:var(--muted); line-height:1.5; max-width:420px; }
		.pm-ovr { font-size:11.5px; color:var(--muted); font-style:italic; margin-top:3px; }
		.pm-actions { display:flex; gap:6px; flex-wrap:nowrap; }

		.pm-st { display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600; white-space:nowrap; }
		.pm-st::before { content:''; width:8px; height:8px; border-radius:50%; background:var(--dot); }
		.pm-st.ok { --dot:var(--ok); } .pm-st.bad { --dot:var(--bad); } .pm-st.warn { --dot:var(--warn); }
		.pm-tag { display:inline-block; margin-left:6px; padding:0 6px; border:1px solid var(--line); border-radius:4px;
			font-size:10.5px; font-weight:600; color:var(--muted); vertical-align:middle; }
		.pm-pill { display:inline-block; padding:1px 9px; border-radius:20px; font-size:11px; font-weight:700; border:1px solid; vertical-align:middle; }
		.pm-pill.draft { color:var(--m-text); border-color:var(--m); }
		.pm-pill.pub { color:#fff; background:var(--m); border-color:var(--m); }

		.pm-empty { text-align:center; padding:46px 20px; color:var(--muted); font-size:13px; }
		.pm-empty b { display:block; color:var(--text); font-size:14px; margin-bottom:4px; }

		.pm-dlg-sum { display:grid; grid-template-columns:repeat(3,1fr); border:1px solid var(--border-color); border-radius:8px; margin-bottom:12px; }
		.pm-dlg-sum > div { padding:12px; text-align:center; border-left:1px solid var(--border-color); }
		.pm-dlg-sum > div:first-child { border-left:none; }
		.pm-dlg-sum .v { font-size:22px; font-weight:700; }
		.pm-dlg-sum .l { font-size:11.5px; color:var(--text-muted); }
		.pm-dlg-meta { font-size:12.5px; color:var(--text-muted); margin-bottom:10px; line-height:1.6; }
		.pm-dlg-meta b { color:var(--text-color); }
		.pm-dlg-note { font-size:12.5px; padding:9px 12px; border-left:3px solid #920c24; background:var(--subtle-fg,#f7f7f8); border-radius:6px; margin-bottom:10px; }
		.pm-dlg-check { display:flex; gap:9px; align-items:flex-start; font-size:12.5px; cursor:pointer; margin:0; font-weight:400; }
		.pm-dlg-check input { margin-top:3px; }
		.pm-dlg .modal-footer .btn-primary { background:#920c24; border-color:#920c24; }
		.pm-dlg .modal-footer .btn-primary:hover { background:#6e0919; border-color:#6e0919; }
		`;
		document.head.appendChild(style);
	}

	// ── State ─────────────────────────────────────────────────────────────────
	var S = {
		policies: {}, preview: null, previewFilter: 'all',
		logKey: null, log: null, logFilter: 'all',
		history: [], view: 'eval', running: false, helpOpen: false,
	};

	// ── Mount ─────────────────────────────────────────────────────────────────
	var $root = $('<div class="pm-wrap"></div>');
	$(page.main).html('').append($root);

	$root.html(`
		<div class="pm-head">
			<div>
				<div class="pm-head-title">&#127891; Promotion Management</div>
				<div class="pm-head-sub">Year &rarr; Year promotion, checked against the Promotion Policy. Term &rarr; Term moves are done from
					<a href="/app/student-enrollment" target="_blank">Student Enrollment</a> (automatic, no policy check).</div>
			</div>
			<div class="pm-head-actions">
				<a class="pm-head-btn" href="/app/promotion-policy" target="_blank">Policies</a>
				<button class="pm-head-btn" data-act="official-dl">Official Report</button>
			</div>
		</div>

		<div class="pm-card">
			<div class="pm-card-body">
				<div class="pm-grid">
					<div><div class="pm-fl">Programme</div>
						<select class="pm-sel" id="pm-prog"><option value="">Select Programme</option></select></div>
					<div><div class="pm-fl">Academic Year</div>
						<select class="pm-sel" id="pm-ay"><option value="">Select Year</option></select></div>
					<div><div class="pm-fl">Promotion Policy</div>
						<select class="pm-sel" id="pm-policy" disabled><option value="">Select Programme &amp; Academic Year first</option></select></div>
					<div><div class="pm-fl">From Year</div>
						<input type="number" class="pm-inp" id="pm-fy" min="1" max="10" placeholder="1"></div>
					<div><div class="pm-fl">To Year</div>
						<input type="number" class="pm-inp" id="pm-ty" min="2" max="11" placeholder="2"></div>
				</div>
				<div id="pm-checks" class="pm-checks pm-hidden"></div>
				<div id="pm-help" class="pm-help pm-hidden"></div>
				<div id="pm-notice" class="pm-hidden"></div>
			</div>
			<div class="pm-card-foot">
				<div class="pm-steps" id="pm-steps"></div>
				<div class="pm-status" id="pm-status"></div>
				<button class="pm-btn" id="pm-fetch-btn">Preview</button>
				<button class="pm-btn primary" id="pm-run-btn">Run Promotion</button>
			</div>
		</div>

		<div class="pm-tabs">
			<div class="pm-tab active" data-view="eval">Preview<span class="n" id="vc-eval"></span></div>
			<div class="pm-tab" data-view="log">Promotion Log<span class="n" id="vc-log"></span></div>
			<div class="pm-tab" data-view="hist">History<span class="n" id="vc-hist"></span></div>
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
	function when(v) { return v ? frappe.datetime.str_to_user(v) : ''; }
	function bucket(status) {
		if (PRO.indexOf(status) > -1) return 'promoted';
		if (NOT.indexOf(status) > -1) return 'not_promoted';
		return 'conditional';
	}
	function statusPill(status) {
		var b = bucket(status);
		var cls = b === 'promoted' ? 'ok' : b === 'not_promoted' ? 'bad' : 'warn';
		return '<span class="pm-st ' + cls + '">' + esc(statusLabel(status) || '—') + '</span>';
	}
	function statusLabel(status) {
		return { 'Override - Promoted': 'Promoted (override)', 'Override - Not Promoted': 'Not promoted (override)',
			'Not Promoted': 'Not promoted' }[status] || status || '';
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
	function sameKey(a, b) {
		return !!(a && b && a.program === b.program && a.academic_year === b.academic_year
			&& a.policy === b.policy && a.from_year === b.from_year && a.to_year === b.to_year);
	}
	function sameStep(k, f) {
		return !!(k && f && k.policy === f.policy && k.from_year === f.from_year && k.to_year === f.to_year);
	}
	function policyYearProblem(p, f) {
		if (!p) return null;
		if (p.from_year > 10) {
			return { level: 'warn', text: 'This policy\'s years are set as ' + p.from_year + ' → ' + p.to_year
				+ ' (calendar years). Set them to year levels (e.g. 1 → 2) so it applies to the right year.' };
		}
		if (f.from_year && (f.from_year !== p.from_year || (f.to_year && f.to_year !== p.to_year))) {
			return { level: 'block', text: 'This policy is for Year ' + p.from_year + ' → ' + p.to_year
				+ ', but Year ' + f.from_year + ' → ' + (f.to_year || '?') + ' is selected.' };
		}
		return null;
	}
	function filtersComplete(f) {
		if (!(f.program && f.academic_year && f.policy && f.from_year && f.to_year > f.from_year)) return false;
		var prob = policyYearProblem(S.policies[f.policy], f);
		return !(prob && prob.level === 'block');
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
	function historyEntry(f) {
		return (S.history || []).filter(function (h) {
			return h.promotion_policy === f.policy && String(h.current_year) === String(f.from_year)
				&& String(h.target_year) === String(f.to_year);
		})[0];
	}
	function empty(title, sub) {
		return '<div class="pm-card"><div class="pm-empty"><b>' + title + '</b>' + (sub || '') + '</div></div>';
	}
	function switchView(v) {
		S.view = v;
		$root.find('.pm-tab').removeClass('active').filter('[data-view="' + v + '"]').addClass('active');
		$('#pm-view-eval').toggleClass('pm-hidden', v !== 'eval');
		$('#pm-view-log').toggleClass('pm-hidden', v !== 'log');
		$('#pm-view-hist').toggleClass('pm-hidden', v !== 'hist');
		flushGrids();
	}
	function filterRows(rows, filter) {
		return rows.filter(function (r) {
			if (filter === 'enrollment_failed') return r.enrollment_status === 'Failed';
			return filter === 'all' || bucket(r.promotion_status) === filter;
		});
	}
	// One helper for every list on the page: frappe.DataTable with sorting,
	// per-column filters, resizable columns and virtual scrolling.
	var GRIDS = {}, PENDING = {}, LAST = {};
	function renderGrid(key, el, columns, rows, emptyText) {
		if (!el) return;
		// DataTable sizes its columns from the container, so a grid in a hidden
		// tab would collapse to zero width — build it when the tab is shown.
		if (!el.offsetParent) { PENDING[key] = [key, el, columns, rows, emptyText]; return; }
		delete PENDING[key];
		LAST[key] = [key, el, columns, rows, emptyText];
		el.innerHTML = '';
		// Fixed layout with widths scaled to fill the container (DataTable's
		// own "fluid" mode mis-measures here and collapses the columns).
		var avail = Math.max(el.clientWidth - 60, 0);
		var total = columns.reduce(function (t, c) { return t + (c.width || 140); }, 0);
		var scale = total && avail > total ? avail / total : 1;
		GRIDS[key] = new frappe.DataTable(el, {
			columns: columns.map(function (c) {
				return Object.assign({ editable: false, focusable: false, dropdown: c.sortable !== false, resizable: true, align: 'left' }, c,
					{ width: Math.floor((c.width || 140) * scale) });
			}),
			data: rows,
			layout: 'fixed',
			serialNoColumn: true,
			checkboxColumn: false,
			inlineFilters: true,
			cellHeight: 46,
			noDataMessage: emptyText || __('No students match.'),
		});
	}
	function flushGrids() {
		Object.keys(PENDING).forEach(function (k) {
			var a = PENDING[k];
			if (a[1].isConnected && a[1].offsetParent) renderGrid.apply(null, a);
			else if (!a[1].isConnected) delete PENDING[k];
		});
	}
	// Refit visible grids after the window / sidebar changes size.
	var _resizeT = null;
	$(window).off('resize.pmgrid').on('resize.pmgrid', function () {
		clearTimeout(_resizeT);
		_resizeT = setTimeout(function () {
			Object.keys(LAST).forEach(function (k) {
				var a = LAST[k];
				if (a[1].isConnected && a[1].offsetParent) renderGrid.apply(null, a);
			});
		}, 250);
	});
	function textCell(v) { return '<span class="pm-ell" title="' + esc(v) + '">' + esc(v) + '</span>'; }
	function idCell(doctype, v) {
		return v ? '<a class="pm-ell pm-sid" href="/app/' + doctype + '/' + encodeURIComponent(v) + '" target="_blank">' + esc(v) + '</a>' : '—';
	}
	function reasonPlain(remarks, status) {
		var parts = (remarks || '').split(';').map(function (x) { return x.trim(); }).filter(Boolean);
		if (parts.length) return parts.join('; ');
		return PRO.indexOf(status) > -1 ? 'Meets all policy criteria' : '';
	}
	function chipsHtml(active, c, withFailed) {
		var chips = [['all', 'All', c.total], ['promoted', 'Promoted', c.promoted],
			['not_promoted', 'Not promoted', c.not_promoted], ['conditional', 'Conditional', c.conditional]];
		if (withFailed && c.enrollment_failed) chips.push(['enrollment_failed', 'Move failed', c.enrollment_failed]);
		return '<div class="pm-chips">' + chips.map(function (x) {
			return '<span class="pm-chip' + (x[0] === active ? ' active' : '') + '" data-filter="' + x[0] + '">' + x[1] + ' ' + (x[2] || 0) + '</span>';
		}).join('') + '</div>';
	}
	function setCount(id, n) { $('#' + id).text(n ? n : ''); }

	// ── Policy checks (single definition: text, tooltip, help) ────────────────
	function policyChecks(p) {
		var maxShort = (p.max_shortage_courses === null || p.max_shortage_courses === undefined || p.max_shortage_courses === '') ? 2 : p.max_shortage_courses;
		return [
			{ on: p.enable_cgpa_check, name: 'CGPA', rule: 'CGPA ≥ ' + (p.min_cgpa || 0),
				help: 'Current CGPA from published results must be at least ' + (p.min_cgpa || 0) + '.' },
			{ on: p.enable_backlog_check, name: 'Failed courses', rule: 'Failed courses ≤ ' + (p.max_backlogs_allowed || 0),
				help: 'Courses failed in this academic year\'s exams (final grade marked as a fail in the grading schema).' },
			{ on: p.enable_attendance_check, name: 'Attendance', rule: 'Avg attendance ≥ ' + (p.min_attendance_percent || 0) + '%',
				help: 'Average attendance across all courses in this academic year.' },
			{ on: p.enable_course_shortage_check, name: 'Attendance shortage', rule: 'Courses below min. attendance ≤ ' + maxShort,
				help: 'Number of courses where attendance is below that course\'s required minimum.' },
			{ on: p.enable_cf_check, name: 'Carry-forward', rule: 'Still short after FA/MFA ≤ ' + (p.max_cf_fa_shortage || 0),
				help: 'Courses where First Attempt (FA) or Medical First Attempt (MFA) condonation hours were credited, but the student is still not exam-eligible (carried forward).' },
			{ on: p.block_on_fee_due, name: 'Fee due', rule: 'No outstanding fee',
				help: 'Blocks promotion if any Fee Demand is Pending, Partially Paid or Overdue.' },
		];
	}

	function renderChecks() {
		var p = S.policies[$('#pm-policy').val()];
		if (!p) { $('#pm-checks, #pm-help').addClass('pm-hidden').html(''); renderNotice(); return; }
		var checks = policyChecks(p);
		var on = checks.filter(function (c) { return c.on; });
		var h = '<b>Checks:</b>' + (on.length ? on.map(function (c) {
			return '<span class="pm-check-on" title="' + esc(c.help) + '">' + esc(c.rule) + '</span>';
		}).join('') : '<span>none — everyone is eligible</span>');
		if (!p.auto_update_student_year) h += '<span>Auto-update is off (decisions are logged only)</span>';
		h += '<span class="pm-link" data-act="toggle-help">What do these mean?</span>'
			+ '<a class="pm-link" href="/app/promotion-policy/' + encodeURIComponent(p.name) + '" target="_blank">Edit policy</a>';
		$('#pm-checks').html(h).removeClass('pm-hidden');
		$('#pm-help').html('<table>' + checks.map(function (c) {
			return '<tr><td>' + esc(c.name) + (c.on ? '' : ' <span class="pm-muted">(off)</span>') + '</td><td>' + esc(c.help) + '</td></tr>';
		}).join('') + '</table>').toggleClass('pm-hidden', !S.helpOpen);
		renderNotice();
	}

	// One notice slot: missing policy, or a policy/year mismatch.
	var _noPolicyMsg = null;
	function renderNotice() {
		var $n = $('#pm-notice');
		if (_noPolicyMsg) { $n.attr('class', 'pm-notice').html(_noPolicyMsg); return; }
		var prob = policyYearProblem(S.policies[$('#pm-policy').val()], currentFilters());
		if (!prob) { $n.attr('class', 'pm-hidden').html(''); return; }
		$n.attr('class', 'pm-notice' + (prob.level === 'block' ? ' err' : '')).text(prob.text);
	}

	$root.on('click', '[data-act="toggle-help"]', function () {
		S.helpOpen = !S.helpOpen;
		$('#pm-help').toggleClass('pm-hidden', !S.helpOpen);
	});

	// ── Steps, buttons and the single status line ─────────────────────────────
	function stepState() {
		var f = currentFilters();
		var ready = filtersComplete(f);
		var logHere = ready && S.log && sameStep(S.logKey, f) ? S.log : null;
		var h = ready ? historyEntry(f) : null;
		var st = logHere ? (logHere.stages || {}) : {};
		return {
			f: f, ready: ready, hist: h,
			drafts: logHere ? (st.draft || 0) : (h ? h.drafts || 0 : 0),
			pubs: logHere ? (st.published || 0) : (h ? h.published_count || 0 : 0),
			previewed: ready && S.preview && sameKey(S.preview.key, f),
		};
	}

	function updateState() {
		var s = stepState(), f = s.f;
		var saved = s.drafts > 0 || s.pubs > 0;
		var done = [s.ready, s.previewed || saved, saved, s.pubs > 0 && !s.drafts];
		var active = !s.ready ? 0 : s.drafts ? 3 : (done[3] ? -1 : (s.previewed ? 2 : 1));
		var names = ['Select', 'Preview', 'Save draft', 'Publish'];
		$('#pm-steps').html(names.map(function (n, i) {
			var cls = i === active ? 'active' : (done[i] ? 'done' : '');
			return (i ? '<span class="pm-step-sep"></span>' : '')
				+ '<span class="pm-step ' + cls + '"><i>' + (done[i] && i !== active ? '&#10003;' : i + 1) + '</i>' + n + '</span>';
		}).join(''));

		$('#pm-fetch-btn, #pm-run-btn').prop('disabled', !s.ready || S.running);

		var msg;
		if (!f.program || !f.academic_year) msg = 'Select a Programme and Academic Year.';
		else if (!f.policy) msg = 'Select the Promotion Policy.';
		else if (!f.from_year) msg = 'Enter the year students are promoted from.';
		else if (f.to_year <= f.from_year) msg = 'To Year must be greater than From Year.';
		else if (!s.ready) msg = 'The policy does not match the selected years.';
		else if (s.drafts) {
			msg = '<b>Draft saved</b>' + (s.hist && s.hist.last_processed_on ? ' ' + esc(when(s.hist.last_processed_on)) : '')
				+ ' — ' + s.drafts + ' decision(s) not applied yet. <span class="pm-link" data-act="open-current">Review &amp; publish</span>';
		} else if (s.pubs) {
			var hp = s.hist || {};
			msg = '<b>Published</b>' + (hp.last_published_on ? ' ' + esc(when(hp.last_published_on)) : '')
				+ ' — ' + (hp.promoted || 0) + ' promoted, ' + (hp.not_promoted || 0) + ' not promoted. '
				+ '<span class="pm-link" data-act="open-current">View log</span>';
		} else if (s.previewed) {
			msg = 'Preview: <b>' + (S.preview.counts.promoted || 0) + '</b> of <b>' + (S.preview.counts.total || 0) + '</b> eligible.';
		} else {
			msg = 'Run Promotion saves a <b>draft</b> — nothing changes for students until you publish.';
		}
		$('#pm-status').html(msg);
	}

	$root.on('click', '[data-act="open-current"]', function () {
		var f = currentFilters();
		openLog({ policy: f.policy, from_year: f.from_year, to_year: f.to_year });
	});

	// ── Dropdowns ─────────────────────────────────────────────────────────────
	var _loaded = { programs: false, years: false };
	function _checkAutoAction() {
		if (!_loaded.programs || !_loaded.years) return;
		if (new URLSearchParams(window.location.search).get('action') === 'download_report') {
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
			_loaded.programs = true; _checkAutoAction();
		},
	});
	frappe.call({
		method: API + 'get_academic_years',
		callback: function (r) {
			var sel = document.getElementById('pm-ay');
			(r.message || []).forEach(function (a) {
				var o = document.createElement('option'); o.value = a.name; o.text = a.name; sel.appendChild(o);
			});
			_loaded.years = true; _checkAutoAction();
		},
	});

	var _policyReq = 0;
	function loadPolicies() {
		var f = currentFilters();
		var sel = document.getElementById('pm-policy');
		S.policies = {}; sel.value = ''; _noPolicyMsg = null;
		renderChecks();
		if (!f.program || !f.academic_year) {
			sel.innerHTML = '<option value="">Select Programme &amp; Academic Year first</option>';
			sel.disabled = true; onFiltersChanged(); return;
		}
		sel.innerHTML = '<option value="">Loading…</option>'; sel.disabled = true;
		onFiltersChanged();
		var req = ++_policyReq;
		frappe.call({
			method: API + 'get_policies_for_filters',
			args: { program: f.program, academic_year: f.academic_year },
			callback: function (r) {
				if (req !== _policyReq) return;
				var rows = r.message || [];
				if (!rows.length) {
					sel.innerHTML = '<option value="">No Active policy found</option>';
					_noPolicyMsg = 'No Active Promotion Policy for this Programme and Academic Year. '
						+ '<a class="pm-link" target="_blank" href="/app/promotion-policy/new?program=' + encodeURIComponent(f.program)
						+ '&academic_year=' + encodeURIComponent(f.academic_year) + '">Create one</a>, then reselect the Academic Year.';
				} else {
					sel.innerHTML = '<option value="">Select Policy</option>';
					rows.forEach(function (p) {
						S.policies[p.name] = p;
						var o = document.createElement('option');
						o.value = p.name; o.text = p.title + '  (Yr ' + p.from_year + ' → ' + p.to_year + ')';
						sel.appendChild(o);
					});
					if (rows.length === 1) sel.value = rows[0].name;
					sel.disabled = false;
					applyPolicyYears();
				}
				renderChecks();
				onFiltersChanged();
			},
		});
	}
	function applyPolicyYears() {
		var p = S.policies[$('#pm-policy').val()];
		if (p && p.from_year >= 1 && p.from_year <= 10 && p.to_year > p.from_year) {
			$('#pm-fy').val(p.from_year); $('#pm-ty').val(p.to_year);
		}
	}

	$root.on('change', '#pm-prog, #pm-ay', function () { loadPolicies(); loadHistory(); });
	$root.on('change', '#pm-policy', function () { applyPolicyYears(); renderChecks(); onFiltersChanged(); });
	$root.on('input', '#pm-fy', function () {
		var v = parseInt(this.value, 10);
		if (!isNaN(v)) $('#pm-ty').val(v + 1);
		onFiltersChanged();
	});
	$root.on('input', '#pm-ty', onFiltersChanged);

	function onFiltersChanged() {
		if (S.preview && !sameKey(S.preview.key, currentFilters())) { S.preview = null; renderEval(); }
		renderNotice();
		updateState();
	}

	// ── Preview ───────────────────────────────────────────────────────────────
	function fetchPreview(f) {
		S.running = true; updateState();
		return new Promise(function (resolve, reject) {
			var result = null;
			frappe.call({
				method: API + 'fetch_students',
				args: { program: f.program, academic_year: f.academic_year, from_year: f.from_year, policy_name: f.policy },
				callback: function (r) {
					var d = r.message || { students: [] };
					result = { key: f, students: d.students || [], counts: d.counts || {} };
				},
				always: function () {
					// Settles on success, server error and network failure alike.
					S.running = false;
					if (result && sameKey(result.key, currentFilters())) {
						S.preview = result; S.previewFilter = 'all';
						renderEval(); updateState(); resolve(result);
					} else { updateState(); reject(); }
				},
			});
		});
	}

	$root.on('click', '#pm-fetch-btn', function () {
		if (S.running) return;
		var f = currentFilters(), err = validateFilters(f);
		if (err) { frappe.show_alert({ message: err, indicator: 'red' }); return; }
		switchView('eval');
		fetchPreview(f).catch(function () {});
	});

	function renderEval() {
		var $v = $('#pm-view-eval');
		if (!S.preview) {
			setCount('vc-eval', 0);
			$v.html(empty('Nothing previewed', 'Choose the selection and click <b>Preview</b> to see who is eligible. Preview never saves anything.'));
			return;
		}
		var P = S.preview;
		setCount('vc-eval', P.counts.total || 0);
		if (!P.students.length) {
			$v.html(empty('No students in Year ' + esc(P.key.from_year), 'No Active students are in this year for the Programme and Academic Year.'));
			return;
		}
		$v.html('<div class="pm-card"><div class="pm-bar"><span id="pm-eval-chips"></span></div>'
			+ '<div class="pm-dt" id="pm-eval-grid"></div></div>');
		renderEvalRows();
	}

	function renderEvalRows() {
		if (!S.preview) return;
		$('#pm-eval-chips').html(chipsHtml(S.previewFilter, S.preview.counts, false));
		var rows = filterRows(S.preview.students, S.previewFilter).map(function (r) {
			return {
				student: r.student,
				student_name: r.student_name || r.student,
				current_cgpa: Math.round((parseFloat(r.current_cgpa) || 0) * 100) / 100,
				result: statusLabel(r.promotion_status),
				reason: reasonPlain(r.remarks, r.promotion_status),
				_status: r.promotion_status,
			};
		});
		renderGrid('eval', document.getElementById('pm-eval-grid'), [
			{ id: 'student', name: __('Student ID'), width: 150, format: function (v, row, col, d) { return idCell('student-master', d.student); } },
			{ id: 'student_name', name: __('Student Name'), width: 220, format: function (v) { return textCell(v); } },
			{ id: 'current_cgpa', name: __('CGPA'), width: 80, align: 'right', format: function (v) { return num(v, 2); } },
			{ id: 'result', name: __('Result'), width: 170, format: function (v, row, col, d) { return statusPill(d._status); } },
			{ id: 'reason', name: __('Reason'), width: 380, format: function (v) { return textCell(v || '—'); } },
		], rows);
	}

	$root.on('click', '#pm-eval-chips .pm-chip', function () { S.previewFilter = $(this).data('filter'); renderEvalRows(); });

	// ── Run Promotion → Draft ─────────────────────────────────────────────────
	function dialog(title, html, primaryLabel, onPrimary) {
		var d = new frappe.ui.Dialog({
			title: title,
			fields: [{ fieldtype: 'HTML', fieldname: 'body', options: html }],
			primary_action_label: primaryLabel,
			primary_action: function () { onPrimary(d); },
		});
		d.$wrapper.addClass('pm-dlg');
		d.show();
		return d;
	}
	function sumHtml(a, b, c) {
		return '<div class="pm-dlg-sum"><div><div class="v">' + a[0] + '</div><div class="l">' + esc(a[1]) + '</div></div>'
			+ '<div><div class="v">' + b[0] + '</div><div class="l">' + esc(b[1]) + '</div></div>'
			+ '<div><div class="v">' + c[0] + '</div><div class="l">' + esc(c[1]) + '</div></div></div>';
	}
	var NOTIFY_BOX = function (label) {
		return '<label class="pm-dlg-check"><input type="checkbox" class="pm-notify" checked><span>' + label + '</span></label>';
	};

	$root.on('click', '#pm-run-btn', function () {
		if (S.running) return;
		var f = currentFilters(), err = validateFilters(f);
		if (err) { frappe.show_alert({ message: err, indicator: 'red' }); return; }
		// Always evaluate current data right before saving, so the summary matches what is saved.
		fetchPreview(f).then(function (P) {
			if (!P.students.length) {
				switchView('eval');
				frappe.msgprint(__('No Active students are in Year {0} for this selection.', [f.from_year]));
				return;
			}
			var c = P.counts, prior = historyEntry(f), policy = S.policies[f.policy] || {};
			var html = sumHtml([c.promoted || 0, 'Promoted'], [c.not_promoted || 0, 'Not promoted'], [c.conditional || 0, 'Conditional'])
				+ '<div class="pm-dlg-meta"><b>' + esc(f.program) + '</b> · ' + esc(f.academic_year) + ' · ' + esc(policy.title || f.policy)
				+ ' · Year ' + f.from_year + ' → ' + f.to_year + '</div>'
				+ '<div class="pm-dlg-note">This saves a <b>draft</b>. Students see no change and get no email until you publish.'
				+ (prior && prior.drafts ? ' The existing draft for this selection will be replaced.' : '') + '</div>';
			dialog(__('Save promotion draft'), html, __('Save draft'), function (d) {
				d.hide();
				runDraft(f);
			});
		}).catch(function () {});
	});

	function runDraft(k) {
		if (!sameKey(k, currentFilters())) { frappe.msgprint(__('The selection changed. Please run again.')); return; }
		S.running = true; updateState();
		frappe.call({
			method: API + 'confirm_promotion',
			args: { program: k.program, academic_year: k.academic_year, from_year: k.from_year, to_year: k.to_year, policy_name: k.policy },
			freeze: true, freeze_message: __('Saving draft…'),
			callback: function (r) {
				if (!r.message) return;
				frappe.show_alert({ message: __('Draft saved — review it, then publish.'), indicator: 'blue' }, 6);
				openLog({ policy: k.policy, from_year: k.from_year, to_year: k.to_year });
				loadHistory();
			},
			always: function () { S.running = false; updateState(); },
		});
	}

	// ── Promotion Log ─────────────────────────────────────────────────────────
	var _logReq = 0;
	function openLog(key) {
		if (!sameStep(S.logKey, key)) { S.logFilter = 'all'; S.log = null; }
		S.logKey = key;
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
				if (focus) switchView('log');
				updateState();
			},
		});
	}

	function renderLog() {
		var $v = $('#pm-view-log'), L = S.log;
		if (!S.logKey || !L) { setCount('vc-log', 0); $v.html(empty('No log open', 'Run a promotion, or open one from <b>History</b>.')); return; }
		var c = L.counts || {}, g = L.stages || {}, k = S.logKey;
		setCount('vc-log', c.total || 0);
		var title = (L.policy && L.policy.title) || k.policy;
		if (!c.total) { $v.html(empty('Nothing logged', 'No promotion has been run for ' + esc(title) + ', Year ' + k.from_year + ' → ' + k.to_year + '.')); return; }

		var meta = 'Last run ' + esc(when(L.last_processed_on) || '—') + (L.last_published_on ? ' · Published ' + esc(when(L.last_published_on)) : '');
		var right = '<div class="pm-menu-wrap"><button class="pm-btn sm" data-act="dl-menu">Download ▾</button>'
			+ '<div class="pm-menu pm-hidden" id="pm-dl-menu">'
			+ '<div data-dl="promoted">Promoted (' + (c.promoted || 0) + ')</div>'
			+ '<div data-dl="not_promoted">Not promoted (' + (c.not_promoted || 0) + ')</div>'
			+ '<div data-dl="conditional">Conditional (' + (c.conditional || 0) + ')</div>'
			+ (c.enrollment_failed ? '<div data-dl="enrollment_failed">Move failed (' + c.enrollment_failed + ')</div>' : '')
			+ '<div data-dl="all">Full log (' + (c.total || 0) + ')</div></div></div>';
		if (g.draft) {
			right += '<button class="pm-btn sm" data-act="discard-draft">Discard draft</button>'
				+ '<button class="pm-btn sm primary" data-act="publish">Publish</button>';
		} else if (c.enrollment_failed) {
			right += '<button class="pm-btn sm" data-act="retry-all">Retry failed moves (' + c.enrollment_failed + ')</button>';
		}

		$v.html(`
			<div class="pm-card">
				<div class="pm-bar">
					<div>
						<div class="pm-bar-title">${esc(title)} · Year ${esc(k.from_year)} → ${esc(k.to_year)}
							&nbsp;${g.draft ? '<span class="pm-pill draft">Draft</span>' : '<span class="pm-pill pub">Published</span>'}</div>
						<div class="pm-bar-meta">${meta}</div>
					</div>
					<span class="pm-spacer"></span>${right}
				</div>
				${g.draft ? '<div class="pm-draftnote"><b>' + g.draft + ' decision(s) not applied.</b> Students see no change and receive no email until you publish. Changes made here only edit the draft.</div>' : ''}
				${L.policy && !L.policy.auto_update_student_year ? '<div class="pm-draftnote">Auto-update is off on this policy — publishing records decisions but does not move students.</div>' : ''}
				<div class="pm-bar"><span id="pm-log-chips"></span></div>
				<div class="pm-dt" id="pm-log-grid"></div>
			</div>`);
		renderLogRows();
	}

	function nextYearCell(r) {
		if (r.enrollment_status === 'Enrolled') {
			return r.to_enrollment ? '<a class="pm-sid" href="/app/student-enrollment/' + encodeURIComponent(r.to_enrollment) + '" target="_blank">'
				+ esc(r.to_enrollment) + '</a>' : 'Enrolled';
		}
		if (r.enrollment_status === 'Failed') return '<span class="pm-st bad">Move failed</span>';
		if (r.enrollment_status === 'Pending') return '<span class="pm-muted">On publish</span>';
		return '<span class="pm-muted">—</span>';
	}

	function logActions(r) {
		var b = bucket(r.promotion_status), out = [];
		if (b !== 'promoted') out.push('<button class="pm-btn xs" data-row-act="promote" data-row="' + esc(r.name) + '">Promote anyway</button>');
		if (b === 'conditional' || (b === 'promoted' && r.enrollment_status !== 'Enrolled'))
			out.push('<button class="pm-btn xs" data-row-act="hold" data-row="' + esc(r.name) + '">Not promoted</button>');
		if (b === 'promoted' && r.enrollment_status === 'Failed' && r.stage === 'Published')
			out.push('<button class="pm-btn xs" data-row-act="retry" data-row="' + esc(r.name) + '">Retry move</button>');
		return out.length ? '<div class="pm-actions">' + out.join('') + '</div>' : '<span class="pm-muted">—</span>';
	}

	function nextYearText(r) {
		if (r.enrollment_status === 'Enrolled') return r.to_enrollment || 'Enrolled';
		if (r.enrollment_status === 'Failed') return 'Move failed';
		if (r.enrollment_status === 'Pending') return 'On publish';
		return '';
	}

	function renderLogRows() {
		if (!S.log) return;
		$('#pm-log-chips').html(chipsHtml(S.logFilter, S.log.counts || {}, true));
		var g = S.log.stages || {};
		var mixed = g.draft && g.published;
		var rows = filterRows(S.log.records || [], S.logFilter).map(function (r) {
			var reason = r.enrollment_status === 'Failed' ? (r.remarks || 'Move failed')
				: reasonPlain(r.manual_override ? '' : r.remarks, r.promotion_status);
			if (r.manual_override && r.override_reason) reason = (reason ? reason + ' · ' : '') + 'Override: ' + r.override_reason;
			return {
				student: r.student,
				student_name: r.student_name || r.student,
				result: statusLabel(r.promotion_status) + (mixed && r.stage === 'Draft' ? ' (draft)' : ''),
				reason: reason,
				next_year: nextYearText(r),
				action: '',
				_r: r,
			};
		});
		renderGrid('log', document.getElementById('pm-log-grid'), [
			{ id: 'student', name: __('Student ID'), width: 150, format: function (v, row, col, d) { return idCell('student-master', d.student); } },
			{ id: 'student_name', name: __('Student Name'), width: 200, format: function (v) { return textCell(v); } },
			{ id: 'result', name: __('Result'), width: 200, format: function (v, row, col, d) {
				var r = d._r;
				return statusPill(r.promotion_status)
					+ (mixed && r.stage === 'Draft' ? '<span class="pm-tag">Draft</span>' : '')
					+ (r.notified_on ? '<span class="pm-tag" title="Emailed ' + esc(when(r.notified_on)) + '">Emailed</span>' : '');
			} },
			{ id: 'reason', name: __('Reason'), width: 330, format: function (v) { return textCell(v || '—'); } },
			{ id: 'next_year', name: __('Next year'), width: 150, format: function (v, row, col, d) { return nextYearCell(d._r); } },
			{ id: 'action', name: __('Action'), width: 230, sortable: false, format: function (v, row, col, d) { return logActions(d._r); } },
		], rows);
	}

	function findLogRow(name) {
		return ((S.log && S.log.records) || []).filter(function (r) { return r.name === name; })[0];
	}
	function afterLogChange() {
		loadLog();
		loadHistory();
		if (S.preview) { S.preview = null; renderEval(); }
	}

	$root.on('click', '#pm-log-chips .pm-chip', function () { S.logFilter = $(this).data('filter'); renderLogRows(); });

	// Download menu
	$root.on('click', '[data-act="dl-menu"]', function (e) { e.stopPropagation(); $('#pm-dl-menu').toggleClass('pm-hidden'); });
	$(document).off('click.pmmenu').on('click.pmmenu', function () { $('#pm-dl-menu').addClass('pm-hidden'); });
	$root.on('click', '[data-dl]', function () {
		if (!S.logKey) return;
		$('#pm-dl-menu').addClass('pm-hidden');
		window.open('/api/method/' + API + 'download_promotion_list'
			+ '?policy_name=' + encodeURIComponent(S.logKey.policy) + '&list_type=' + encodeURIComponent($(this).data('dl'))
			+ '&from_year=' + encodeURIComponent(S.logKey.from_year) + '&to_year=' + encodeURIComponent(S.logKey.to_year), '_blank');
	});

	// Row actions
	$root.on('click', '[data-row-act]', function () {
		var act = $(this).data('row-act'), r = findLogRow($(this).data('row'));
		if (!r) return;
		if (act === 'retry') { openRetry([r.name]); return; }
		var promote = act === 'promote', draft = r.stage === 'Draft', name = esc(r.student_name || r.student);
		var note = draft
			? (promote ? 'Change the draft decision for <b>' + name + '</b> to <b>Promoted</b>.' : 'Change the draft decision for <b>' + name + '</b> to <b>Not promoted</b>.')
				+ ' Nothing is applied until the draft is published.'
			: (promote ? '<b>' + name + '</b> is promoted to Year ' + esc(r.target_year) + ' <b>now</b>, overriding the policy.'
				: '<b>' + name + '</b> is kept in Year ' + esc(r.current_year) + '.');
		var d = new frappe.ui.Dialog({
			title: promote ? __('Promote anyway') : __('Mark not promoted'),
			fields: [
				{ fieldtype: 'HTML', fieldname: 'note', options: '<div class="pm-dlg-note">' + note + '</div>' },
				{ label: __('Reason'), fieldname: 'reason', fieldtype: 'Small Text', reqd: 1 },
				{ fieldtype: 'HTML', fieldname: 'notify', options: draft ? '' : NOTIFY_BOX('Email the student the updated result') },
			],
			primary_action_label: __('Save'),
			primary_action: function (vals) {
				var notify = !draft && d.$wrapper.find('.pm-notify').is(':checked') ? 1 : 0;
				d.get_primary_btn().prop('disabled', true);
				frappe.call({
					method: API + 'save_override',
					args: { record_name: r.name, new_status: promote ? 'Override - Promoted' : 'Override - Not Promoted', reason: vals.reason, notify: notify },
					callback: function (res) {
						if (!res.message) return;
						d.hide();
						if (res.message.error) {
							frappe.msgprint({ title: __('Promoted, but the move failed'), indicator: 'orange',
								message: esc(res.message.error) + '<br><br>' + __('The student stays in the current year and was not emailed. Use Retry move once fixed.') });
						} else {
							frappe.show_alert({ message: __('Saved') + (res.message.notified_queued ? ' · ' + __('email queued') : ''), indicator: 'green' });
						}
						afterLogChange();
					},
					always: function () { d.get_primary_btn().prop('disabled', false); },
				});
			},
		});
		d.$wrapper.addClass('pm-dlg');
		d.show();
	});

	$root.on('click', '[data-act="retry-all"]', function () {
		var names = ((S.log && S.log.records) || []).filter(function (r) {
			return PRO.indexOf(r.promotion_status) > -1 && r.enrollment_status === 'Failed' && r.stage === 'Published';
		}).map(function (r) { return r.name; });
		if (names.length) openRetry(names);
	});

	function openRetry(names) {
		var html = '<div class="pm-dlg-note">Try again to move ' + names.length + ' student(s) into next year\'s Batch '
			+ '(for example after creating the target Batch).</div>' + NOTIFY_BOX('Email students who are moved now and haven\'t been emailed yet');
		dialog(__('Retry move'), html, __('Retry'), function (d) {
			var notify = d.$wrapper.find('.pm-notify').is(':checked') ? 1 : 0;
			d.hide();
			frappe.call({
				method: API + 'retry_enrollment', args: { record_names: names, notify: notify },
				freeze: true, freeze_message: __('Retrying…'),
				callback: function (r) {
					var m = r.message || { enrolled: [], failed: [] };
					if (m.failed.length) {
						frappe.msgprint({ title: __('{0} moved, {1} still failing', [m.enrolled.length, m.failed.length]), indicator: 'orange',
							message: m.failed.map(function (f) { return '<b>' + esc(f.student) + '</b>: ' + esc(f.error); }).join('<br>') });
					} else {
						frappe.show_alert({ message: __('{0} student(s) moved', [m.enrolled.length])
							+ (m.notified_queued ? ' · ' + __('{0} email(s) queued', [m.notified_queued]) : ''), indicator: 'green' });
					}
					afterLogChange();
				},
			});
		});
	}

	// Publish / discard
	$root.on('click', '[data-act="publish"]', function () {
		if (!S.logKey || !S.log) return;
		var k = S.logKey, L = S.log;
		var drafts = (L.records || []).filter(function (r) { return r.stage === 'Draft'; });
		if (!drafts.length) { frappe.msgprint(__('There is no draft to publish.')); return; }
		var n = { p: 0, x: 0, c: 0 };
		drafts.forEach(function (r) { var b = bucket(r.promotion_status); if (b === 'promoted') n.p++; else if (b === 'not_promoted') n.x++; else n.c++; });
		var auto = L.policy && L.policy.auto_update_student_year;
		var html = sumHtml([n.p, auto ? 'Move to Year ' + k.to_year : 'Promoted'], [n.x, 'Stay in Year ' + k.from_year], [n.c, 'Conditional'])
			+ '<div class="pm-dlg-note">' + (auto
				? 'Publishing <b>applies</b> the decisions: promoted students move to Year ' + k.to_year + ' and are enrolled into next year\'s Batch.'
				: 'Auto-update is off — publishing releases the decisions but does not move students.') + '</div>'
			+ NOTIFY_BOX('<b>Email each student their result</b><br><span style="color:var(--text-muted)">Promoted, not promoted (with reasons) or under review. '
				+ 'Students whose move fails are not emailed until the move succeeds.</span>');
		dialog(__('Publish promotion'), html, __('Publish {0} decision(s)', [drafts.length]), function (d) {
			var notify = d.$wrapper.find('.pm-notify').is(':checked') ? 1 : 0;
			d.hide();
			frappe.call({
				method: API + 'publish_promotion',
				args: { policy_name: k.policy, from_year: k.from_year, to_year: k.to_year, notify: notify },
				freeze: true, freeze_message: __('Publishing…'),
				callback: function (r) {
					if (!r.message) return;
					var m = r.message;
					frappe.show_alert({
						message: __('Published {0} decision(s)', [m.published]) + (notify ? ' · ' + __('{0} email(s) queued', [m.notified_queued]) : ''),
						indicator: 'green',
					}, 8);
					if (m.enrollment_failures && m.enrollment_failures.length) {
						frappe.msgprint({
							title: __('{0} student(s) could not be moved', [m.enrollment_failures.length]), indicator: 'orange',
							message: m.enrollment_failures.map(function (f) { return '<b>' + esc(f.student) + '</b>: ' + esc(f.error); }).join('<br>')
								+ '<br><br>' + __('They stay in their current year and were not emailed. Fix the cause (e.g. create the target Batch) and use <b>Retry failed moves</b>.'),
						});
					}
					afterLogChange();
				},
			});
		});
	});

	$root.on('click', '[data-act="discard-draft"]', function () {
		if (!S.logKey || !S.log) return;
		frappe.confirm(__('Discard the draft ({0} decision(s))? Nothing was applied, so nothing else changes.', [(S.log.stages || {}).draft || 0]), function () {
			frappe.call({
				method: API + 'discard_draft',
				args: { policy_name: S.logKey.policy, from_year: S.logKey.from_year, to_year: S.logKey.to_year },
				freeze: true,
				callback: function (r) {
					frappe.show_alert({ message: __('{0} draft decision(s) discarded', [(r.message || {}).discarded || 0]), indicator: 'orange' });
					afterLogChange();
				},
			});
		});
	});

	// ── History ───────────────────────────────────────────────────────────────
	var _histReq = 0;
	function loadHistory() {
		var f = currentFilters();
		if (!f.program || !f.academic_year) { S.history = []; renderHistory(); updateState(); return; }
		var req = ++_histReq;
		frappe.call({
			method: API + 'get_promotion_history',
			args: { program: f.program, academic_year: f.academic_year },
			callback: function (r) {
				if (req !== _histReq) return;
				S.history = r.message || [];
				renderHistory(); updateState();
			},
		});
	}
	function renderHistory() {
		var $v = $('#pm-view-hist'), H = S.history || [], f = currentFilters();
		setCount('vc-hist', H.length);
		if (!f.program || !f.academic_year) { $v.html(empty('No history', 'Select a Programme and Academic Year.')); return; }
		if (!H.length) { $v.html(empty('No promotions yet', 'Nothing has been run for this Programme and Academic Year.')); return; }
		$v.html('<div class="pm-card"><div class="pm-dt" id="pm-hist-grid"></div></div>');
		var rows = H.map(function (h) {
			return {
				policy: h.policy_title || h.promotion_policy,
				step: h.current_year + ' → ' + h.target_year,
				stage: h.drafts ? 'Draft' : 'Published',
				total: h.total || 0, promoted: h.promoted || 0, not_promoted: h.not_promoted || 0, conditional: h.conditional || 0,
				last_run: h.last_processed_on || '',
				open: '', _h: h,
			};
		});
		var numCol = function (id, name) { return { id: id, name: name, width: 110, align: 'right' }; };
		renderGrid('hist', document.getElementById('pm-hist-grid'), [
			{ id: 'policy', name: __('Policy'), width: 240, format: function (v, row, col, d) {
				return '<span class="pm-ell" title="' + esc(d._h.promotion_policy) + '">' + esc(v) + '</span>';
			} },
			{ id: 'step', name: __('Year'), width: 90 },
			{ id: 'stage', name: __('Stage'), width: 110, format: function (v) {
				return v === 'Draft' ? '<span class="pm-pill draft">Draft</span>' : '<span class="pm-pill pub">Published</span>';
			} },
			numCol('total', __('Students')), numCol('promoted', __('Promoted')),
			numCol('not_promoted', __('Not promoted')), numCol('conditional', __('Conditional')),
			{ id: 'last_run', name: __('Last run'), width: 170, format: function (v) { return esc(when(v) || '—'); } },
			{ id: 'open', name: '', width: 100, sortable: false, format: function (v, row, col, d) {
				var h = d._h;
				return '<button class="pm-btn xs" data-hist-open="' + esc(h.promotion_policy) + '" data-fy="' + esc(h.current_year)
					+ '" data-ty="' + esc(h.target_year) + '">' + (h.drafts ? 'Review' : 'Open') + '</button>';
			} },
		], rows, __('No promotions yet.'));
	}
	$root.on('click', '[data-hist-open]', function () {
		openLog({ policy: String($(this).data('hist-open')), from_year: parseInt($(this).data('fy'), 10) || 0, to_year: parseInt($(this).data('ty'), 10) || 0 });
	});

	$root.on('click', '.pm-tab', function () { switchView($(this).data('view')); });

	// ── Official report ───────────────────────────────────────────────────────
	$root.on('click', '[data-act="official-dl"]', function () { openOfficialDownload(); });
	function openOfficialDownload() {
		var progs = Array.from($('#pm-prog option')).map(function (o) { return o.value; }).filter(Boolean);
		var ays = Array.from($('#pm-ay option')).map(function (o) { return o.value; }).filter(Boolean);
		var f = currentFilters();
		var d = new frappe.ui.Dialog({
			title: __('Official Promotion Report'),
			fields: [
				{ label: __('Programme'), fieldname: 'program', fieldtype: 'Select', reqd: 1, options: [''].concat(progs).join('\n'), default: f.program },
				{ label: __('Academic Year'), fieldname: 'academic_year', fieldtype: 'Select', reqd: 1, options: [''].concat(ays).join('\n'), default: f.academic_year },
				{ label: __('University / Institution Name'), fieldname: 'university_name', fieldtype: 'Data', description: __('Printed at the top (optional)') },
				{ label: __('Include draft (unpublished) decisions'), fieldname: 'include_draft', fieldtype: 'Check', default: 0,
					description: __('For review only — draft rows are marked [DRAFT]. The official list uses published decisions.') },
			],
			primary_action_label: __('Download Excel'),
			primary_action: function (v) {
				d.hide();
				window.open('/api/method/' + API + 'download_formatted_promotion_list'
					+ '?program=' + encodeURIComponent(v.program) + '&academic_year=' + encodeURIComponent(v.academic_year)
					+ '&university_name=' + encodeURIComponent(v.university_name || '') + '&include_draft=' + (v.include_draft ? 1 : 0), '_blank');
			},
		});
		d.$wrapper.addClass('pm-dlg');
		d.show();
	}
	window.pmOfficialDl = openOfficialDownload;

	// ── Initial render ────────────────────────────────────────────────────────
	renderEval();
	renderLog();
	renderHistory();
	updateState();
};
