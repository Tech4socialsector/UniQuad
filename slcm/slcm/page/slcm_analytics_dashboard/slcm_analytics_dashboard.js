// Copyright (c) 2026, TFSS and contributors
// SLCM Analytics Dashboard — Premium Enterprise Analytics
'use strict';

frappe.pages['slcm-analytics-dashboard'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'SLCM Analytics Dashboard',
		single_column: true,
	});
	new SLCMAnalyticsDashboard(wrapper);
};

// ── Palette & constants ───────────────────────────────────────────────────────

const PALETTE = {
	primary:   ['#1e3a8a', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe'],
	success:   ['#065f46', '#059669', '#10b981', '#34d399', '#6ee7b7', '#a7f3d0'],
	warning:   ['#92400e', '#d97706', '#f59e0b', '#fbbf24', '#fcd34d', '#fde68a'],
	danger:    ['#7f1d1d', '#dc2626', '#ef4444', '#f87171', '#fca5a5', '#fee2e2'],
	info:      ['#164e63', '#0891b2', '#06b6d4', '#22d3ee', '#67e8f9', '#a5f3fc'],
	neutral:   ['#0f172a', '#1e293b', '#334155', '#475569', '#64748b', '#94a3b8'],
	mixed:     ['#1e3a8a','#059669','#d97706','#dc2626','#0891b2','#7c3aed','#db2777','#ea580c'],
	status: {
		'Active':       '#059669',
		'Inactive':     '#94a3b8',
		'Graduated':    '#1e3a8a',
		'Dropped':      '#dc2626',
		'Dormant':      '#d97706',
		'Present':      '#059669',
		'Absent':       '#dc2626',
		'OD':           '#d97706',
		'Paid':         '#059669',
		'Unpaid':       '#dc2626',
		'Partially Paid': '#d97706',
		'Accepted':     '#059669',
		'Rejected':     '#dc2626',
		'Pending':      '#d97706',
		'Allotted':          '#059669',
		'Pending Allotment': '#d97706',
	},
};

const PAGE_METHOD = 'slcm.slcm.page.slcm_analytics_dashboard.slcm_analytics_dashboard';

// ── Utility helpers ───────────────────────────────────────────────────────────

const fmt_number = (n) => {
	if (n == null || isNaN(n)) return '—';
	if (n >= 1_00_00_000) return (n / 1_00_00_000).toFixed(1) + 'Cr';
	if (n >= 1_00_000)    return (n / 1_00_000).toFixed(1) + 'L';
	if (n >= 1_000)       return (n / 1_000).toFixed(1) + 'K';
	return String(Math.round(n));
};

const fmt_currency = (n) => {
	if (n == null || isNaN(n)) return '₹—';
	if (n >= 1_00_00_000) return '₹' + (n / 1_00_00_000).toFixed(2) + 'Cr';
	if (n >= 1_00_000)    return '₹' + (n / 1_00_000).toFixed(2) + 'L';
	if (n >= 1_000)       return '₹' + (n / 1_000).toFixed(1) + 'K';
	return '₹' + n.toLocaleString('en-IN');
};

const status_color = (label) =>
	PALETTE.status[label] || PALETTE.mixed[Math.abs(label.charCodeAt(0)) % PALETTE.mixed.length];

const labels_and_values = (data, label_key = 'label', value_key = 'value') => ({
	labels: (data || []).map(r => r[label_key] || 'Unknown'),
	datasets: [{ values: (data || []).map(r => r[value_key] || 0) }],
});

const rate_badge = (rate) => {
	const cls = rate >= 75 ? 'badge-success' : rate >= 50 ? 'badge-warning' : 'badge-danger';
	return `<span class="sad-rate-badge ${cls}">${rate}%</span>`;
};

// ── Main Dashboard Class ──────────────────────────────────────────────────────

class SLCMAnalyticsDashboard {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.$body    = this.$wrapper.find('.page-content');
		this.$body.css({ padding: 0, background: 'var(--sad-bg)' });

		this.filters      = { academic_year: null, term: null, program: null, cohort: null, student_status: null };
		this.active_tab   = 'overview';
		this.chart_refs   = {};
		this._drilldown_open = false;
		this._filter_options = null;

		this._inject_styles();
		this._build_layout();
		this._load_filter_options();
	}

	// ── Styles ────────────────────────────────────────────────────────────────

	_inject_styles() {
		if ($('#sad-styles').length) return;
		$(`<style id="sad-styles">
		/* ── Design tokens ───────────────────────────────────────────── */
		:root {
			--sad-bg:        #f0f4f8;
			--sad-surface:   #ffffff;
			--sad-surface2:  #f8fafc;
			--sad-border:    #e2e8f0;
			--sad-primary:   #1e3a8a;
			--sad-primary-l: #2563eb;
			--sad-primary-xl:#dbeafe;
			--sad-success:   #059669;
			--sad-warning:   #d97706;
			--sad-danger:    #dc2626;
			--sad-info:      #0891b2;
			--sad-purple:    #7c3aed;
			--sad-text1:     #0f172a;
			--sad-text2:     #334155;
			--sad-text3:     #64748b;
			--sad-text4:     #94a3b8;
			--sad-radius:    14px;
			--sad-radius-sm: 8px;
			--sad-shadow:    0 1px 4px rgba(15,23,42,.08), 0 4px 16px rgba(15,23,42,.06);
			--sad-shadow-lg: 0 8px 32px rgba(15,23,42,.14);
			--sad-transition: all .22s cubic-bezier(.4,0,.2,1);
		}

		/* ── Page layout ─────────────────────────────────────────────── */
		.sad-page      { padding:20px 24px 80px; min-height:100vh; }
		.sad-header    {
			display:flex; align-items:center; gap:16px;
			margin-bottom:20px;
		}
		.sad-header-icon {
			width:52px; height:52px; border-radius:14px; flex-shrink:0;
			background:linear-gradient(135deg,#1e3a8a,#3b5bdb);
			display:flex; align-items:center; justify-content:center;
			color:#fff; font-size:22px;
			box-shadow:0 4px 14px rgba(30,58,138,.4);
		}
		.sad-header-text .sad-suptitle {
			font-size:10px; font-weight:700; text-transform:uppercase;
			letter-spacing:.8px; color:var(--sad-text3);
		}
		.sad-header-text .sad-title {
			font-size:22px; font-weight:800; color:var(--sad-text1); line-height:1.15;
			letter-spacing:-.4px;
		}
		.sad-header-right { margin-left:auto; display:flex; align-items:center; gap:10px; }
		.sad-refresh-btn {
			display:flex; align-items:center; gap:6px;
			padding:8px 16px; border-radius:8px; border:1px solid var(--sad-border);
			background:var(--sad-surface); color:var(--sad-text2);
			font-size:13px; font-weight:600; cursor:pointer;
			transition:var(--sad-transition);
		}
		.sad-refresh-btn:hover { background:var(--sad-primary); color:#fff; border-color:var(--sad-primary); }
		.sad-last-updated { font-size:11px; color:var(--sad-text4); }

		/* ── Filter bar ──────────────────────────────────────────────── */
		.sad-filter-bar {
			background:var(--sad-surface);
			border-radius:var(--sad-radius);
			border:1px solid var(--sad-border);
			border-left:4px solid var(--sad-primary);
			padding:16px 20px;
			margin-bottom:20px;
			box-shadow:var(--sad-shadow);
			display:flex; align-items:flex-end; gap:14px; flex-wrap:wrap;
		}
		.sad-filter-group { display:flex; flex-direction:column; gap:4px; flex:1; min-width:160px; }
		.sad-filter-label {
			font-size:10px; font-weight:700; text-transform:uppercase;
			letter-spacing:.6px; color:var(--sad-text3);
		}
		.sad-filter-actions { display:flex; gap:8px; align-items:flex-end; padding-bottom:2px; }
		.sad-btn {
			padding:7px 16px; border-radius:7px; font-size:13px; font-weight:600;
			cursor:pointer; border:1px solid transparent; transition:var(--sad-transition);
			display:inline-flex; align-items:center; gap:6px;
		}
		.sad-btn-primary {
			background:var(--sad-primary); color:#fff; border-color:var(--sad-primary);
		}
		.sad-btn-primary:hover { background:#1e40af; }
		.sad-btn-ghost {
			background:transparent; color:var(--sad-text3); border-color:var(--sad-border);
		}
		.sad-btn-ghost:hover { background:var(--sad-surface2); color:var(--sad-text1); }

		/* ── Tab navigation ──────────────────────────────────────────── */
		.sad-tabs {
			display:flex; gap:4px; flex-wrap:wrap;
			background:var(--sad-surface); border-radius:var(--sad-radius);
			padding:6px; margin-bottom:20px;
			border:1px solid var(--sad-border); box-shadow:var(--sad-shadow);
		}
		.sad-tab {
			display:flex; align-items:center; gap:7px;
			padding:8px 16px; border-radius:9px;
			font-size:13px; font-weight:600;
			color:var(--sad-text3); cursor:pointer;
			transition:var(--sad-transition); user-select:none;
			border:1px solid transparent;
		}
		.sad-tab:hover { color:var(--sad-primary); background:var(--sad-primary-xl); }
		.sad-tab.active {
			background:var(--sad-primary); color:#fff;
			box-shadow:0 2px 8px rgba(30,58,138,.3);
		}
		.sad-tab .tab-icon { font-size:14px; }

		/* ── KPI grid ────────────────────────────────────────────────── */
		.sad-kpi-grid {
			display:grid;
			grid-template-columns:repeat(auto-fill, minmax(200px, 1fr));
			gap:14px; margin-bottom:20px;
		}
		.sad-kpi-card {
			background:var(--sad-surface); border-radius:var(--sad-radius);
			padding:20px; border:1px solid var(--sad-border);
			box-shadow:var(--sad-shadow); position:relative; overflow:hidden;
			transition:var(--sad-transition);
		}
		.sad-kpi-card:hover { transform:translateY(-2px); box-shadow:var(--sad-shadow-lg); }
		.sad-kpi-accent {
			position:absolute; top:0; left:0; right:0; height:3px;
			border-radius:var(--sad-radius) var(--sad-radius) 0 0;
		}
		.sad-kpi-icon {
			width:40px; height:40px; border-radius:10px;
			display:flex; align-items:center; justify-content:center;
			font-size:18px; margin-bottom:12px;
		}
		.sad-kpi-label {
			font-size:11px; font-weight:700; text-transform:uppercase;
			letter-spacing:.6px; color:var(--sad-text3); margin-bottom:6px;
		}
		.sad-kpi-value {
			font-size:28px; font-weight:800; color:var(--sad-text1);
			line-height:1; letter-spacing:-.5px; margin-bottom:4px;
		}
		.sad-kpi-sub { font-size:12px; color:var(--sad-text3); }
		.sad-kpi-rate {
			position:absolute; top:20px; right:20px;
			font-size:12px; font-weight:700; padding:3px 8px;
			border-radius:6px;
		}
		.kpi-primary  .sad-kpi-accent { background:var(--sad-primary); }
		.kpi-primary  .sad-kpi-icon   { background:#dbeafe; color:var(--sad-primary); }
		.kpi-success  .sad-kpi-accent { background:var(--sad-success); }
		.kpi-success  .sad-kpi-icon   { background:#d1fae5; color:var(--sad-success); }
		.kpi-warning  .sad-kpi-accent { background:var(--sad-warning); }
		.kpi-warning  .sad-kpi-icon   { background:#fef3c7; color:var(--sad-warning); }
		.kpi-danger   .sad-kpi-accent { background:var(--sad-danger); }
		.kpi-danger   .sad-kpi-icon   { background:#fee2e2; color:var(--sad-danger); }
		.kpi-info     .sad-kpi-accent { background:var(--sad-info); }
		.kpi-info     .sad-kpi-icon   { background:#cffafe; color:var(--sad-info); }
		.kpi-purple   .sad-kpi-accent { background:var(--sad-purple); }
		.kpi-purple   .sad-kpi-icon   { background:#ede9fe; color:var(--sad-purple); }

		/* ── Drillable KPI card ──────────────────────────────────────── */
		.sad-kpi-card.has-drilldown { cursor:pointer; }
		.sad-kpi-card.has-drilldown .sad-kpi-drill-arrow {
			position:absolute; bottom:14px; right:14px;
			width:22px; height:22px; border-radius:6px;
			display:flex; align-items:center; justify-content:center;
			font-size:12px; opacity:.25;
			transition:var(--sad-transition);
			background:currentColor;
		}
		.sad-kpi-card.has-drilldown .sad-kpi-drill-arrow i { color:#fff; }
		.sad-kpi-card.has-drilldown:hover .sad-kpi-drill-arrow { opacity:1; transform:translateX(2px); }
		.sad-kpi-card.has-drilldown:hover { border-color:var(--sad-primary-l); }
		.kpi-primary.has-drilldown:hover  { border-color:var(--sad-primary); }
		.kpi-success.has-drilldown:hover  { border-color:var(--sad-success); }
		.kpi-danger.has-drilldown:hover   { border-color:var(--sad-danger); }
		.kpi-warning.has-drilldown:hover  { border-color:var(--sad-warning); }
		.kpi-info.has-drilldown:hover     { border-color:var(--sad-info); }
		.kpi-purple.has-drilldown:hover   { border-color:var(--sad-purple); }
		.sad-kpi-drill-hint {
			font-size:10px; color:var(--sad-text4); margin-top:5px;
			display:flex; align-items:center; gap:3px; font-weight:600;
		}

		/* ── Chart grid ──────────────────────────────────────────────── */
		.sad-chart-grid {
			display:grid;
			grid-template-columns:repeat(auto-fill, minmax(340px, 1fr));
			gap:16px; margin-bottom:20px;
		}
		.sad-chart-grid-3 {
			grid-template-columns:repeat(auto-fill, minmax(280px, 1fr));
		}
		.sad-chart-wide { grid-column: 1 / -1; }

		.sad-chart-card {
			background:var(--sad-surface); border-radius:var(--sad-radius);
			border:1px solid var(--sad-border); box-shadow:var(--sad-shadow);
			padding:20px; position:relative; overflow:hidden;
			transition:var(--sad-transition);
		}
		.sad-chart-card:hover { box-shadow:var(--sad-shadow-lg); }
		.sad-chart-header {
			display:flex; align-items:center; justify-content:space-between;
			margin-bottom:16px;
		}
		.sad-chart-title-wrap {}
		.sad-chart-title {
			font-size:14px; font-weight:700; color:var(--sad-text1); margin-bottom:2px;
		}
		.sad-chart-subtitle { font-size:11px; color:var(--sad-text3); }
		.sad-chart-badge {
			font-size:11px; font-weight:600; padding:4px 10px;
			border-radius:20px; background:var(--sad-primary-xl); color:var(--sad-primary);
			white-space:nowrap;
		}
		.sad-chart-body { min-height:200px; position:relative; }
		.sad-chart-tip {
			font-size:10px; color:var(--sad-text4); margin-top:8px;
			display:flex; align-items:center; gap:4px;
		}

		/* ── Progress bars ───────────────────────────────────────────── */
		.sad-progress-list { display:flex; flex-direction:column; gap:10px; }
		.sad-progress-item {}
		.sad-progress-label {
			display:flex; justify-content:space-between; align-items:center;
			margin-bottom:5px;
		}
		.sad-progress-name { font-size:13px; font-weight:600; color:var(--sad-text2); }
		.sad-progress-val  { font-size:12px; font-weight:700; color:var(--sad-text1); }
		.sad-progress-track {
			height:7px; background:#f1f5f9; border-radius:4px; overflow:hidden;
		}
		.sad-progress-fill {
			height:100%; border-radius:4px;
			transition:width .6s cubic-bezier(.4,0,.2,1);
		}

		/* ── Rate badge ──────────────────────────────────────────────── */
		.sad-rate-badge {
			font-size:11px; font-weight:700; padding:3px 8px; border-radius:6px;
		}
		.badge-success { background:#d1fae5; color:#065f46; }
		.badge-warning { background:#fef3c7; color:#92400e; }
		.badge-danger  { background:#fee2e2; color:#7f1d1d; }

		/* ── Metric row ──────────────────────────────────────────────── */
		.sad-metric-row {
			display:flex; justify-content:space-between; align-items:center;
			padding:10px 0; border-bottom:1px solid var(--sad-border);
		}
		.sad-metric-row:last-child { border-bottom:none; }
		.sad-metric-name  { font-size:13px; color:var(--sad-text2); font-weight:500; }
		.sad-metric-value { font-size:14px; color:var(--sad-text1); font-weight:700; }

		/* ── Skeleton loader ─────────────────────────────────────────── */
		@keyframes sad-shimmer {
			0%   { background-position:-400px 0; }
			100% { background-position:400px 0; }
		}
		.sad-skeleton {
			background:linear-gradient(90deg, #f0f4f8 25%, #e2e8f0 50%, #f0f4f8 75%);
			background-size:800px 100%;
			animation:sad-shimmer 1.4s infinite;
			border-radius:8px;
		}
		.sad-skeleton-kpi {
			height:130px; border-radius:var(--sad-radius);
			margin-bottom:14px;
		}
		.sad-skeleton-chart {
			height:240px; border-radius:var(--sad-radius);
		}

		/* ── Drilldown panel ─────────────────────────────────────────── */
		.sad-drilldown-overlay {
			position:fixed; inset:0;
			background:rgba(15,23,42,.4); z-index:1050;
			opacity:0; pointer-events:none;
			transition:opacity .25s ease;
		}
		.sad-drilldown-overlay.open { opacity:1; pointer-events:all; }

		.sad-drilldown-panel {
			position:fixed; top:0; right:0; bottom:0;
			width:min(680px, 92vw);
			background:var(--sad-surface);
			box-shadow:-8px 0 40px rgba(15,23,42,.2);
			z-index:1051;
			transform:translateX(100%);
			transition:transform .28s cubic-bezier(.4,0,.2,1);
			display:flex; flex-direction:column;
		}
		.sad-drilldown-panel.open { transform:translateX(0); }

		.sad-drilldown-header {
			display:flex; align-items:center; gap:12px;
			padding:18px 24px; border-bottom:1px solid var(--sad-border);
			flex-shrink:0;
		}
		.sad-drilldown-title { font-size:16px; font-weight:700; color:var(--sad-text1); flex:1; }
		.sad-drilldown-breadcrumb {
			font-size:11px; color:var(--sad-text3); margin-top:2px;
		}
		.sad-drilldown-close {
			width:32px; height:32px; border-radius:8px; border:none;
			background:var(--sad-surface2); color:var(--sad-text2);
			cursor:pointer; font-size:16px;
			display:flex; align-items:center; justify-content:center;
			transition:var(--sad-transition);
		}
		.sad-drilldown-close:hover { background:var(--sad-danger); color:#fff; }

		.sad-drilldown-body {
			flex:1; overflow-y:auto; padding:20px 24px;
		}

		.sad-drilldown-stats {
			display:grid; grid-template-columns:repeat(3, 1fr);
			gap:12px; margin-bottom:20px;
		}
		.sad-drilldown-stat {
			background:var(--sad-surface2); border-radius:10px;
			padding:14px; border:1px solid var(--sad-border); text-align:center;
		}
		.sad-drilldown-stat .dds-value {
			font-size:22px; font-weight:800; color:var(--sad-primary); margin-bottom:3px;
		}
		.sad-drilldown-stat .dds-label {
			font-size:11px; color:var(--sad-text3); font-weight:600;
			text-transform:uppercase; letter-spacing:.5px;
		}

		/* ── Data table ──────────────────────────────────────────────── */
		.sad-table-wrap { overflow-x:auto; border-radius:10px; border:1px solid var(--sad-border); }
		.sad-table {
			width:100%; border-collapse:collapse;
			font-size:12.5px;
		}
		.sad-table thead th {
			background:var(--sad-surface2); color:var(--sad-text3);
			font-size:10px; font-weight:700; text-transform:uppercase;
			letter-spacing:.5px; padding:10px 12px;
			border-bottom:1px solid var(--sad-border);
			position:sticky; top:0; z-index:2;
			white-space:nowrap;
		}
		.sad-table tbody tr { border-bottom:1px solid var(--sad-border); }
		.sad-table tbody tr:last-child { border-bottom:none; }
		.sad-table tbody tr:hover { background:var(--sad-surface2); }
		.sad-table tbody tr.sad-row-link { cursor:pointer; }
		.sad-table tbody tr.sad-row-link:hover td:first-child { color:var(--sad-primary); text-decoration:underline; }
		.sad-table tbody td { padding:9px 12px; color:var(--sad-text2); vertical-align:middle; }
		.sad-table tbody td:first-child { font-weight:600; color:var(--sad-text1); }

		/* ── Pagination ──────────────────────────────────────────────── */
		.sad-pagination {
			display:flex; align-items:center; justify-content:space-between;
			padding:12px 0; margin-top:12px;
			font-size:12px; color:var(--sad-text3);
		}
		.sad-page-btns { display:flex; gap:6px; }
		.sad-page-btn {
			padding:5px 12px; border-radius:6px; border:1px solid var(--sad-border);
			background:var(--sad-surface); cursor:pointer; font-size:12px;
			font-weight:600; color:var(--sad-text2); transition:var(--sad-transition);
		}
		.sad-page-btn:hover:not(:disabled) { background:var(--sad-primary); color:#fff; border-color:var(--sad-primary); }
		.sad-page-btn:disabled { opacity:.4; cursor:not-allowed; }
		.sad-page-size-wrap { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--sad-text3); }
		.sad-page-size-select {
			padding:4px 8px; border-radius:6px; border:1px solid var(--sad-border);
			background:var(--sad-surface); color:var(--sad-text2);
			font-size:12px; font-weight:600; cursor:pointer;
		}
		.sad-page-size-select:focus { outline:none; border-color:var(--sad-primary); }

		/* ── Drilldown search bar ────────────────────────────────────── */
		.sad-drilldown-search-bar {
			padding:12px 24px 8px;
			flex-shrink:0;
			border-bottom:1px solid var(--sad-border);
			display:flex; align-items:center; gap:10px;
		}
		.sad-dd-search-wrap {
			flex:1; position:relative;
		}
		.sad-dd-search-wrap .sad-dd-search-icon {
			position:absolute; left:11px; top:50%; transform:translateY(-50%);
			color:var(--sad-text3); font-size:13px; pointer-events:none;
		}
		.sad-dd-search-input {
			width:100%; padding:7px 12px 7px 32px;
			border:1.5px solid var(--sad-border); border-radius:8px;
			font-size:13px; color:var(--sad-text1);
			background:var(--sad-surface2); outline:none;
			transition:var(--sad-transition);
		}
		.sad-dd-search-input:focus { border-color:var(--sad-primary); background:var(--sad-surface); }
		.sad-dd-search-clear {
			position:absolute; right:9px; top:50%; transform:translateY(-50%);
			background:none; border:none; cursor:pointer;
			color:var(--sad-text3); font-size:14px; padding:2px 4px;
			display:none; line-height:1;
		}
		.sad-dd-search-clear:hover { color:var(--sad-danger); }
		.sad-dd-search-count {
			font-size:11px; color:var(--sad-text3);
			white-space:nowrap; min-width:80px; text-align:right;
		}

		/* ── Section separator ───────────────────────────────────────── */
		.sad-section-title {
			font-size:13px; font-weight:700; color:var(--sad-text3);
			text-transform:uppercase; letter-spacing:.6px;
			margin:24px 0 12px;
			display:flex; align-items:center; gap:8px;
		}
		.sad-section-title::after {
			content:''; flex:1; height:1px; background:var(--sad-border);
		}

		/* ── Collection summary card ─────────────────────────────────── */
		.sad-summary-card {
			background:linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
			border-radius:var(--sad-radius); padding:22px 24px;
			color:#fff; margin-bottom:16px; position:relative; overflow:hidden;
		}
		.sad-summary-card::before {
			content:''; position:absolute; right:-20px; top:-30px;
			width:160px; height:160px; border-radius:50%;
			background:rgba(255,255,255,.06);
		}
		.sad-summary-card::after {
			content:''; position:absolute; right:40px; bottom:-40px;
			width:100px; height:100px; border-radius:50%;
			background:rgba(255,255,255,.04);
		}
		.sad-sc-grid {
			display:grid; grid-template-columns:repeat(3, 1fr); gap:20px;
		}
		.sad-sc-item .sc-label {
			font-size:10px; font-weight:700; text-transform:uppercase;
			letter-spacing:.6px; opacity:.7; margin-bottom:6px;
		}
		.sad-sc-item .sc-value {
			font-size:24px; font-weight:800; letter-spacing:-.5px;
		}
		.sad-sc-item .sc-sub { font-size:11px; opacity:.65; margin-top:3px; }

		/* ── Funnel chart ────────────────────────────────────────────── */
		.sad-funnel {
			display:flex; flex-direction:column; gap:6px; padding:4px 0;
		}
		.sad-funnel-step {
			display:flex; align-items:center; gap:12px; cursor:pointer;
		}
		.sad-funnel-bar-wrap {
			flex:1; height:36px; background:var(--sad-surface2);
			border-radius:6px; overflow:hidden; position:relative;
		}
		.sad-funnel-bar {
			height:100%; border-radius:6px;
			display:flex; align-items:center; padding-left:12px;
			transition:width .6s cubic-bezier(.4,0,.2,1);
			min-width:30px;
		}
		.sad-funnel-bar-label {
			font-size:12px; font-weight:700; color:#fff;
			white-space:nowrap; text-shadow:0 1px 2px rgba(0,0,0,.3);
		}
		.sad-funnel-meta {
			text-align:right; min-width:60px;
			font-size:12px; font-weight:700; color:var(--sad-text2);
		}
		.sad-funnel-name { min-width:120px; font-size:12px; color:var(--sad-text2); font-weight:600; }

		/* ── Occupation meter ────────────────────────────────────────── */
		.sad-gauge-wrap { text-align:center; padding:20px 0; }
		.sad-gauge-ring {
			width:140px; height:140px; margin:0 auto 12px;
			position:relative;
		}
		.sad-gauge-ring svg { width:100%; height:100%; transform:rotate(-90deg); }
		.sad-gauge-bg { fill:none; stroke:#f1f5f9; stroke-width:14; }
		.sad-gauge-fill {
			fill:none; stroke-width:14; stroke-linecap:round;
			transition:stroke-dasharray .8s cubic-bezier(.4,0,.2,1);
		}
		.sad-gauge-text {
			position:absolute; inset:0;
			display:flex; flex-direction:column;
			align-items:center; justify-content:center;
		}
		.sad-gauge-pct  { font-size:26px; font-weight:800; color:var(--sad-text1); }
		.sad-gauge-lbl  { font-size:10px; color:var(--sad-text3); font-weight:600; text-transform:uppercase; }

		/* ── Empty / error states ────────────────────────────────────── */
		.sad-empty {
			display:flex; flex-direction:column; align-items:center;
			justify-content:center; padding:40px 20px; color:var(--sad-text4);
		}
		.sad-empty-icon { font-size:36px; margin-bottom:12px; opacity:.5; }
		.sad-empty-title { font-size:14px; font-weight:600; color:var(--sad-text3); }
		.sad-empty-sub   { font-size:12px; margin-top:4px; }

		/* ── Export button ───────────────────────────────────────────── */
		.sad-export-btn {
			display:inline-flex; align-items:center; gap:6px;
			padding:6px 14px; border-radius:7px; font-size:12px; font-weight:600;
			border:1px solid var(--sad-border); background:var(--sad-surface);
			color:var(--sad-text2); cursor:pointer; transition:var(--sad-transition);
		}
		.sad-export-btn:hover { background:var(--sad-success); color:#fff; border-color:var(--sad-success); }
		.sad-viewlist-btn {
			display:inline-flex; align-items:center; gap:6px;
			padding:6px 14px; border-radius:7px; font-size:12px; font-weight:600;
			border:1px solid var(--sad-primary); background:var(--sad-primary);
			color:#fff; cursor:pointer; transition:var(--sad-transition);
		}
		.sad-viewlist-btn:hover { opacity:.85; }
		.sad-viewlist-btn:disabled, .sad-viewlist-btn[disabled] { opacity:.35; cursor:not-allowed; }

		/* ── Animations ──────────────────────────────────────────────── */
		@keyframes sad-fadein {
			from { opacity:0; transform:translateY(12px); }
			to   { opacity:1; transform:translateY(0); }
		}
		.sad-animate { animation:sad-fadein .3s ease; }

		/* ── Responsive ──────────────────────────────────────────────── */
		@media (max-width:768px) {
			.sad-page { padding:12px 14px 60px; }
			.sad-kpi-grid { grid-template-columns:repeat(2, 1fr); }
			.sad-chart-grid { grid-template-columns:1fr; }
			.sad-tabs { overflow-x:auto; flex-wrap:nowrap; }
			.sad-tab  { flex-shrink:0; }
			.sad-sc-grid { grid-template-columns:1fr; }
			.sad-drilldown-panel { width:100%; }
			.sad-drilldown-stats { grid-template-columns:1fr 1fr; }
		}
		</style>`).appendTo('head');
	}

	// ── Layout skeleton ───────────────────────────────────────────────────────

	_build_layout() {
		this.$body.html(`
		<div class="sad-page">

			<!-- Header -->
			<div class="sad-header">
				<div class="sad-header-icon"><i class="fa fa-line-chart"></i></div>
				<div class="sad-header-text">
					<div class="sad-suptitle">Enterprise Analytics</div>
					<div class="sad-title">SLCM Analytics Dashboard</div>
				</div>
				<div class="sad-header-right">
					<span class="sad-last-updated" id="sad-last-updated"></span>
					<button class="sad-refresh-btn" id="sad-refresh">
						<i class="fa fa-refresh"></i> Refresh
					</button>
				</div>
			</div>

			<!-- Filter bar -->
			<div class="sad-filter-bar" id="sad-filters">
				<div class="sad-filter-group">
					<div class="sad-filter-label">Academic Year</div>
					<div id="sad-f-ay"></div>
				</div>
				<div class="sad-filter-group">
					<div class="sad-filter-label">Term</div>
					<div id="sad-f-term"></div>
				</div>
				<div class="sad-filter-group">
					<div class="sad-filter-label">Program</div>
					<div id="sad-f-prog"></div>
				</div>
				<div class="sad-filter-group">
					<div class="sad-filter-label">Cohort</div>
					<div id="sad-f-cohort"></div>
				</div>
				<div class="sad-filter-group">
					<div class="sad-filter-label">Student Status</div>
					<div id="sad-f-sstatus"></div>
				</div>
				<div class="sad-filter-actions">
					<button class="sad-btn sad-btn-primary" id="sad-apply-filters">
						<i class="fa fa-filter"></i> Apply
					</button>
					<button class="sad-btn sad-btn-ghost" id="sad-reset-filters">
						<i class="fa fa-times"></i> Reset
					</button>
				</div>
			</div>

			<!-- Tabs -->
			<div class="sad-tabs" id="sad-tabs">
				<div class="sad-tab active" data-tab="overview">
					<span class="tab-icon">📊</span> Overview
				</div>
				<div class="sad-tab" data-tab="admission">
					<span class="tab-icon">🎯</span> Admission
				</div>
				<div class="sad-tab" data-tab="students">
					<span class="tab-icon">🎓</span> Students
				</div>
				<div class="sad-tab" data-tab="programme">
					<span class="tab-icon">📚</span> Programme
				</div>
				<div class="sad-tab" data-tab="attendance">
					<span class="tab-icon">📋</span> Attendance
				</div>
				<div class="sad-tab" data-tab="examination">
					<span class="tab-icon">📝</span> Examination
				</div>
				<div class="sad-tab" data-tab="fees">
					<span class="tab-icon">💰</span> Fees
				</div>
				<div class="sad-tab" data-tab="hostel">
					<span class="tab-icon">🏠</span> Hostel
				</div>
				<div class="sad-tab" data-tab="placement">
					<span class="tab-icon">💼</span> Placement
				</div>
				<div class="sad-tab" data-tab="idcard">
					<span class="tab-icon">🪪</span> ID Card
				</div>
				<div class="sad-tab" data-tab="venue">
					<span class="tab-icon">🏛️</span> Venue
				</div>
				<div class="sad-tab" data-tab="promotion">
					<span class="tab-icon">🎖️</span> Promotion
				</div>
				<div class="sad-tab" data-tab="ticketing">
					<span class="tab-icon">🎫</span> Ticketing
				</div>
			</div>

			<!-- Tab content area -->
			<div id="sad-tab-content"></div>

		</div>

		<!-- Drilldown overlay -->
		<div class="sad-drilldown-overlay" id="sad-dd-overlay"></div>

		<!-- Drilldown panel -->
		<div class="sad-drilldown-panel" id="sad-dd-panel">
			<div class="sad-drilldown-header">
				<div>
					<div class="sad-drilldown-title" id="sad-dd-title">Detail View</div>
					<div class="sad-drilldown-breadcrumb" id="sad-dd-breadcrumb"></div>
				</div>
				<button class="sad-viewlist-btn" id="sad-dd-viewlist" style="display:none">
					<i class="fa fa-list"></i> View List
				</button>
				<button class="sad-export-btn" id="sad-dd-export">
					<i class="fa fa-download"></i> Export
				</button>
				<button class="sad-drilldown-close" id="sad-dd-close">✕</button>
			</div>
			<div class="sad-drilldown-search-bar">
				<div class="sad-dd-search-wrap">
					<span class="sad-dd-search-icon">🔍</span>
					<input type="text" id="sad-dd-search" class="sad-dd-search-input" placeholder="Search in results...">
					<button class="sad-dd-search-clear" id="sad-dd-search-clear">✕</button>
				</div>
				<span class="sad-dd-search-count" id="sad-dd-search-count"></span>
			</div>
			<div class="sad-drilldown-body" id="sad-dd-body">
				<div class="sad-empty">
					<div class="sad-empty-icon">📊</div>
					<div class="sad-empty-title">Click a chart segment to drill down</div>
				</div>
			</div>
		</div>
		`);

		this._bind_events();
	}

	_bind_events() {
		const self = this;

		// Tab switching
		this.$body.on('click', '.sad-tab', function () {
			const tab = $(this).data('tab');
			self.$body.find('.sad-tab').removeClass('active');
			$(this).addClass('active');
			self.active_tab = tab;
			self._load_tab(tab);
		});

		// Filters
		$('#sad-apply-filters').on('click', () => this._apply_filters());
		$('#sad-reset-filters').on('click', () => this._reset_filters());
		$('#sad-refresh').on('click', () => this._load_tab(this.active_tab, true));

		// Drilldown panel close
		$('#sad-dd-close, #sad-dd-overlay').on('click', () => this._close_drilldown());

		// Drillable KPI cards
		this.$body.on('click', '.sad-kpi-card.has-drilldown', function () {
			const m   = $(this).data('dd-module');
			const dim = $(this).data('dd-dim');
			const val = $(this).data('dd-val');
			const ttl = $(this).data('dd-title');
			self._open_drilldown(m, dim, val, {}, ttl);
		});

		// View List
		$('#sad-dd-viewlist').on('click', () => {
			const r = this._drilldown_list_route;
			if (r) frappe.set_route('List', r.dt, r.filters);
		});

		// Export
		$('#sad-dd-export').on('click', () => this._export_drilldown());

		// Drilldown search — filter visible rows as user types
		$(document).on('input', '#sad-dd-search', function () {
			const q = $(this).val().toLowerCase().trim();
			let visible = 0;
			const $rows = $('.sad-table tbody tr');
			$rows.each(function () {
				const match = !q || $(this).text().toLowerCase().includes(q);
				$(this).toggle(match);
				if (match) visible++;
			});
			$('#sad-dd-search-count').text(q ? `${visible} / ${$rows.length} shown` : '');
			$('#sad-dd-search-clear').toggle(!!q);
		});

		// Clear search button
		$(document).on('click', '#sad-dd-search-clear', function () {
			$('#sad-dd-search').val('').trigger('input');
		});
	}

	// ── Filter controls ───────────────────────────────────────────────────────

	_load_filter_options() {
		const make_select = (container_id, options, value_key, label_key, placeholder, onchange) => {
			const $el = $('<select class="form-control input-xs"></select>');
			$el.append(`<option value="">${placeholder}</option>`);
			options.forEach(opt => {
				$el.append(`<option value="${opt[value_key]}">${opt[label_key] || opt[value_key]}</option>`);
			});
			$el.on('change', () => onchange && onchange($el.val()));
			$('#' + container_id).html($el);
			return $el;
		};

		frappe.call({
			method: `${PAGE_METHOD}.get_filter_options`,
			callback: (r) => {
				if (r.exc || !r.message) return;
				const opts = r.message;
				this._filter_options = opts;

				this.$ay = make_select('sad-f-ay', opts.academic_years, 'name', 'name', 'All Years', (val) => {
					this.filters.academic_year = val || null;
					this._refresh_cohort_filter();
					this._refresh_term_filter();
				});

				this.$term = make_select('sad-f-term', opts.terms || [], 'name', 'term_name', 'All Terms', (val) => {
					this.filters.term = val || null;
				});

				this.$prog = make_select('sad-f-prog', opts.programs, 'name', 'program_name', 'All Programs', (val) => {
					this.filters.program = val || null;
					this._refresh_cohort_filter();
				});

				this.$cohort = make_select('sad-f-cohort', opts.cohorts, 'name', 'cohort_name', 'All Cohorts', (val) => {
					this.filters.cohort = val || null;
				});

				this.$sstatus = make_select('sad-f-sstatus', opts.student_statuses || [], 'value', 'label', 'All Statuses', (val) => {
					this.filters.student_status = val || null;
				});

				this._load_tab('overview');
			},
		});
	}

	_refresh_cohort_filter() {
		if (!this._filter_options) return;
		const ay   = this.filters.academic_year;

		// Batches are standalone (no programme link) — filter by academic year only
		let cohorts = this._filter_options.cohorts;
		if (ay)   cohorts = cohorts.filter(c => c.academic_year === ay);

		const $sel = this.$cohort;
		$sel.html('<option value="">All Cohorts</option>');
		cohorts.forEach(c => $sel.append(`<option value="${c.name}">${c.cohort_name}</option>`));
		$sel.val('');
		this.filters.cohort = null;
	}

	_refresh_term_filter() {
		if (!this._filter_options) return;
		const ay = this.filters.academic_year;

		let terms = this._filter_options.terms || [];
		if (ay) terms = terms.filter(t => t.academic_year === ay);

		const $sel = this.$term;
		$sel.html('<option value="">All Terms</option>');
		terms.forEach(t => $sel.append(`<option value="${t.name}">${t.term_name || t.name}</option>`));
		$sel.val('');
		this.filters.term = null;
	}

	_apply_filters() {
		this.filters.academic_year  = this.$ay?.val()      || null;
		this.filters.term           = this.$term?.val()    || null;
		this.filters.program        = this.$prog?.val()    || null;
		this.filters.cohort         = this.$cohort?.val()  || null;
		this.filters.student_status = this.$sstatus?.val() || null;
		this._load_tab(this.active_tab, true);
	}

	_reset_filters() {
		this.filters = { academic_year: null, term: null, program: null, cohort: null, student_status: null };
		this.$ay?.val('');
		this.$term?.val('');
		this.$prog?.val('');
		this.$cohort?.val('');
		this.$sstatus?.val('');
		this._refresh_cohort_filter();
		this._refresh_term_filter();
		this._load_tab(this.active_tab, true);
	}

	// ── Tab loader dispatcher ─────────────────────────────────────────────────

	_load_tab(tab, force = false) {
		const $content = $('#sad-tab-content');
		$content.addClass('sad-animate');
		setTimeout(() => $content.removeClass('sad-animate'), 400);

		const loaders = {
			overview:    () => this._load_overview(),
			students:    () => this._load_students(),
			attendance:  () => this._load_attendance(),
			examination: () => this._load_examination(),
			fees:        () => this._load_fees(),
			hostel:      () => this._load_hostel(),
			placement:   () => this._load_placement(),
			admission:   () => this._load_admission(),
			programme:   () => this._load_programme(),
			idcard:      () => this._load_idcard(),
			venue:       () => this._load_venue(),
			promotion:   () => this._load_promotion(),
		ticketing:   () => this._load_ticketing(),
		};

		if (loaders[tab]) loaders[tab]();
		$('#sad-last-updated').text('Updated ' + frappe.datetime.now_time());
	}

	_show_loading(sections = 4) {
		const skeletons = Array(sections).fill(0).map(() =>
			`<div class="sad-skeleton sad-skeleton-chart"></div>`
		).join('');
		const kpis = Array(4).fill(0).map(() =>
			`<div class="sad-skeleton sad-skeleton-kpi"></div>`
		).join('');
		$('#sad-tab-content').html(`
			<div class="sad-kpi-grid">${kpis}</div>
			<div class="sad-chart-grid">${skeletons}</div>
		`);
	}

	// ── Tab: Overview ─────────────────────────────────────────────────────────

	_load_overview() {
		this._show_loading(4);

		frappe.call({
			method: `${PAGE_METHOD}.get_overview_stats`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid" id="sad-ov-adm-kpis">
						<div class="sad-skeleton sad-skeleton-kpi"></div>
						<div class="sad-skeleton sad-skeleton-kpi"></div>
						<div class="sad-skeleton sad-skeleton-kpi"></div>
						<div class="sad-skeleton sad-skeleton-kpi"></div>
						<div class="sad-skeleton sad-skeleton-kpi"></div>
						<div class="sad-skeleton sad-skeleton-kpi"></div>
					</div>

					<div class="sad-section-title">Key Performance Indicators</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-ov-student-status', 'Student Status Distribution', 'Real-time student lifecycle', '', '')}
						${this._chart_card('sad-ov-fee-trend', 'Fee Collection vs Outstanding', 'Financial health snapshot', '', '')}
						${this._rate_card('sad-ov-rates', 'System Performance Rates')}
						${this._chart_card('sad-ov-hostel', 'Hostel Utilization', 'Bed occupancy overview', '', '')}
					</div>
				`);

				this._render_overview_charts(d);
			},
		});
	}

	_render_overview_charts(d) {
		// ── Top 6 KPI cards (admission + institutional highlights) ───────────
		frappe.call({
			method: `${PAGE_METHOD}.get_admission_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) return;
				const ad = r.message;
				const acc_color = ad.acceptance_rate >= 60 ? 'success' : ad.acceptance_rate >= 30 ? 'warning' : 'danger';

				$('#sad-ov-adm-kpis').html(`
					${this._kpi('Total Applicants',  ad.total_applicants,              '🎯', 'primary', `${ad.active_cycles} active cycles`,          { module:'admission', dimension:'app_status',   value:'all' })}
					${this._kpi('Offer Acceptance',  ad.acceptance_rate + '%',         '📨', acc_color, `${ad.accepted_offers} of ${ad.total_offers} offers`, { module:'admission', dimension:'status', value:'Accepted' })}
					${this._kpi('Active Students',   d.active_students,                '🎓', 'success', `${d.total_students} total enrolled`,         { module:'students',  dimension:'student_status', value:'Active' })}
					${this._kpi('Attendance Rate',   d.attendance_rate + '%',          '📋', d.attendance_rate >= 75 ? 'success' : d.attendance_rate >= 50 ? 'warning' : 'danger', `${fmt_number(d.total_attendance_records)} records`, { module:'attendance', dimension:'status', value:'Present' })}
					${this._kpi('Fee Collection',    d.fee_collection_rate + '%',      '💰', d.fee_collection_rate >= 80 ? 'success' : 'warning', fmt_currency(d.total_collected) + ' collected', { module:'fees', dimension:'payment_status', value:'Paid' })}
					${this._kpi('Placement Offers',  d.total_placement_offers,         '💼', 'purple',  `${d.accepted_placement_offers} accepted`,    { module:'placement', dimension:'status', value:'Accepted' })}
				`);

				// Re-bind drilldown for dynamically injected cards
				const self = this;
				$('#sad-ov-adm-kpis').find('.sad-kpi-card.has-drilldown').off('click').on('click', function () {
					self._open_drilldown($(this).data('dd-module'), $(this).data('dd-dim'), $(this).data('dd-val'), {}, $(this).data('dd-title') || '');
				});
			},
		});

		// ── Student status donut ─────────────────────────────────────────────
		frappe.call({
			method: `${PAGE_METHOD}.get_student_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) return;
				const sd = r.message;
				this._render_donut('#sad-ov-student-status .sad-chart-body', sd.status_distribution, 'students', 'student_status');
			},
		});

		// Fee bar chart
		const fee_labels = ['Billed', 'Collected', 'Outstanding'];
		const fee_values = [d.total_billed, d.total_collected, d.total_outstanding];
		this._render_bar('#sad-ov-fee-trend .sad-chart-body', {
			labels: fee_labels,
			datasets: [{ values: fee_values }],
		}, {
			colors: ['#2563eb', '#059669', '#dc2626'],
			format_value: fmt_currency,
		});

		// Performance rates
		$('#sad-ov-rates .sad-chart-body').html(`
			<div class="sad-progress-list" style="padding:8px 0">
				${this._progress_bar('Attendance Rate',      d.attendance_rate,          '#059669')}
				${this._progress_bar('Fee Collection Rate',  d.fee_collection_rate,      '#2563eb')}
				${this._progress_bar('Hostel Occupancy',     d.hostel_occupancy_rate,    '#0891b2')}
				${this._progress_bar('Placement Acceptance', d.placement_acceptance_rate,'#7c3aed')}
			</div>
		`);

		// Hostel gauge
		this._render_gauge(
			'#sad-ov-hostel .sad-chart-body',
			d.hostel_occupancy_rate,
			`${d.hostel_allocated} of ${d.total_beds} beds`,
		);
	}

	// ── Tab: Students ─────────────────────────────────────────────────────────

	_load_students() {
		this._show_loading(5);

		frappe.call({
			method: `${PAGE_METHOD}.get_student_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;

				const total = (d.status_distribution || []).reduce((s, x) => s + (x.value || 0), 0);
				const active_pct = (() => {
					const a = (d.status_distribution || []).find(x => x.label === 'Active');
					return a ? Math.round((a.value / total) * 100) : 0;
				})();

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Total Enrolled', total, '🎓', 'primary', 'across all cohorts', { module:'students', dimension:'student_status', value:'Active' })}
						${this._kpi('Active Rate', active_pct + '%', '✅', active_pct >= 80 ? 'success' : 'warning', 'of all students', { module:'students', dimension:'student_status', value:'Active' })}
						${this._kpi('Programs', d.program_distribution.length, '📚', 'info', 'with enrollments', { module:'students', dimension:'programs_list', value:'all' })}
						${this._kpi('Cohorts', d.cohort_distribution.length, '🗂️', 'purple', 'active cohorts', { module:'students', dimension:'cohorts_list', value:'all' })}
					</div>

					<div class="sad-section-title">Enrollment Breakdown</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-st-status',    'Student Status',         'Lifecycle distribution',   'Click segment to drill down', '')}
						${this._chart_card('sad-st-gender',    'Gender Distribution',    'Demographic breakdown',    'Click to explore', '')}
						${this._chart_card('sad-st-quota',     'Quota Category',         'Reservation breakdown',    '', '')}
						${this._chart_card('sad-st-scholar',   'Scholarship Split',      'Scholarship coverage',     '', '')}
					</div>

					<div class="sad-section-title">Program & Cohort Analysis</div>
					<div class="sad-chart-grid">
						<div class="sad-chart-wide">
							${this._chart_card('sad-st-program', 'Program-wise Enrollment', 'Student count per program', 'Click bar to drill down', '')}
						</div>
					</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-st-admission', 'Admission Type',         'Regular vs PACE vs Other', '', '')}
						${this._chart_card('sad-st-cohort',    'Top Cohorts',            'Enrollment per cohort',    '', '')}
						${this._chart_card('sad-st-regstatus', 'Registration Status',    'Workflow progress',        '', '')}
					</div>
				`);

				this._render_donut('#sad-st-status .sad-chart-body', d.status_distribution, 'students', 'student_status');
				this._render_donut('#sad-st-gender .sad-chart-body', d.gender_distribution, 'students', 'gender');
				this._render_donut('#sad-st-quota .sad-chart-body', d.quota_distribution, 'students', 'quota');
				this._render_donut('#sad-st-scholar .sad-chart-body', d.scholarship_distribution, 'students', 'scholarship');
				this._render_bar_horizontal('#sad-st-program .sad-chart-body', d.program_distribution, { module: 'students', dimension: 'program' });
				this._render_donut('#sad-st-admission .sad-chart-body', d.admission_type, 'students', 'admission_type');
				this._render_bar_horizontal('#sad-st-cohort .sad-chart-body', d.cohort_distribution.slice(0, 8), { module: 'students', dimension: 'cohort' });
				this._render_funnel('#sad-st-regstatus .sad-chart-body', d.registration_status, { module: 'students', dimension: 'reg_status' });
			},
		});
	}

	// ── Tab: Attendance ───────────────────────────────────────────────────────

	_load_attendance() {
		this._show_loading(4);

		frappe.call({
			method: `${PAGE_METHOD}.get_attendance_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;

				const status_map = {};
				(d.status_distribution || []).forEach(x => { status_map[x.label] = x.value; });
				const total    = Object.values(status_map).reduce((a, b) => a + b, 0);
				const present  = status_map['Present']  || 0;
				const absent   = status_map['Absent']   || 0;
				const od       = status_map['OD']       || 0;
				const late     = status_map['Late']     || 0;
				const excused  = status_map['Excused']  || 0;
				const att_rate    = total ? Math.round(present / total * 100) : 0;
				const absent_rate = total ? Math.round(absent  / total * 100) : 0;

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Attendance Rate', att_rate + '%',     '📋', att_rate >= 75 ? 'success' : att_rate >= 60 ? 'warning' : 'danger', `${fmt_number(present)} present of ${fmt_number(total)}`, { module:'attendance', dimension:'status', value:'Present' })}
						${this._kpi('Total Records',   fmt_number(total),  '📊', 'primary', 'across all sessions',         { module:'attendance', dimension:'status', value:'all' })}
						${this._kpi('Absent',          fmt_number(absent), '❌', 'danger',  absent_rate + '% absentee rate',{ module:'attendance', dimension:'status', value:'Absent' })}
						${this._kpi('On Duty (OD)',    fmt_number(od),     '🔄', 'info',    'officially excused',          { module:'attendance', dimension:'status', value:'OD' })}
						${this._kpi('Late',            fmt_number(late),   '⏰', 'warning', 'arrived late',                { module:'attendance', dimension:'status', value:'Late' })}
						${this._kpi('Excused',         fmt_number(excused),'✅', 'success', 'excused absences',            { module:'attendance', dimension:'status', value:'Excused' })}
					</div>

					<div class="sad-section-title">Attendance Patterns</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-att-status',   'Status Distribution',    'Present / Absent / Late / OD / Excused', 'Click to explore records', '')}
						${this._chart_card('sad-att-session',  'Session Type',           'Lecture / Office Hour / Tutorial',       '', '')}
						${this._chart_card('sad-att-source',   'Attendance Source',      'Manual / RFID / QR / Auto',              '', '')}
						${this._chart_card('sad-att-prog',     'Program-wise Rate',      'Attendance % per program',               '', '')}
					</div>

					<div class="sad-section-title">Condonation & FA/MFA</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-att-cond',        'Condonation Status',         'Pending / Approved / Rejected',           '', '')}
						${this._chart_card('sad-att-cond-rec',    'Faculty Recommendation',     'Recommended / Not Recommended / Pending', '', '')}
						${this._chart_card('sad-att-famfa',       'FA / MFA Status',            'Pending / Approved / Rejected',           '', '')}
						${this._chart_card('sad-att-famfa-type',  'FA / MFA Type & Reason',     'Application type and reason breakdown',   '', '')}
					</div>

					<div class="sad-section-title">Trend Analysis</div>
					<div class="sad-chart-grid">
						<div class="sad-chart-wide">
							${this._chart_card('sad-att-trend', 'Monthly Attendance Trend', 'Present vs Absent over last 12 months', '', '')}
						</div>
					</div>
					<div class="sad-chart-grid">
						<div class="sad-chart-wide">
							${this._chart_card('sad-att-daily', 'Daily Attendance (Last 30 Days)', 'Day-by-day attendance rate', '', '')}
						</div>
					</div>
				`);

				this._render_donut('#sad-att-status .sad-chart-body',    d.status_distribution,       'attendance', 'status');
				this._render_donut('#sad-att-session .sad-chart-body',   d.session_type_dist,         'attendance', 'session_type');
				this._render_donut('#sad-att-source .sad-chart-body',    d.source_dist,               'attendance', 'source');
				this._render_program_attendance('#sad-att-prog .sad-chart-body', d.program_attendance);
				this._render_donut('#sad-att-cond .sad-chart-body',      d.condonation_stats,         'attendance', 'condonation');
				this._render_donut('#sad-att-cond-rec .sad-chart-body',  d.condonation_faculty_rec,   'attendance', 'cond_faculty');
				this._render_donut('#sad-att-famfa .sad-chart-body',     d.fa_mfa_stats,              'attendance', 'fa_mfa');
				this._render_donut('#sad-att-famfa-type .sad-chart-body',d.fa_mfa_type_dist,          'attendance', 'fa_mfa_type');
				this._render_monthly_trend('#sad-att-trend .sad-chart-body', d.monthly_trend);
				this._render_daily_trend('#sad-att-daily .sad-chart-body',   d.daily_trend);
			},
		});
	}

	_render_program_attendance($sel, data) {
		if (!data || !data.length) { $('' + $sel).html(this._empty_html()); return; }
		const max_rate = Math.max(...data.map(x => x.attendance_rate || 0));
		const html = data.map(d => `
			<div class="sad-progress-item">
				<div class="sad-progress-label">
					<span class="sad-progress-name" style="max-width:60%">${d.label}</span>
					<span class="sad-progress-val">${rate_badge(d.attendance_rate)}</span>
				</div>
				<div class="sad-progress-track">
					<div class="sad-progress-fill" style="width:${(d.attendance_rate / Math.max(max_rate, 100)) * 100}%; background:${d.attendance_rate >= 75 ? 'var(--sad-success)' : d.attendance_rate >= 60 ? 'var(--sad-warning)' : 'var(--sad-danger)'}"></div>
				</div>
			</div>
		`).join('');
		$('' + $sel).html(`<div class="sad-progress-list" style="max-height:260px;overflow-y:auto;padding:4px 0">${html}</div>`);
	}

	_render_monthly_trend($sel, data) {
		if (!data || !data.length) { $('' + $sel).html(this._empty_html()); return; }
		const container = document.querySelector($sel);
		if (!container) return;
		try {
			const chart = new frappe.Chart(container, {
				data: {
					labels: data.map(d => d.month_label || d.month),
					datasets: [
						{ name: 'Present', values: data.map(d => d.present || 0), chartType: 'bar' },
						{ name: 'Absent',  values: data.map(d => d.absent  || 0), chartType: 'bar' },
						{ name: 'OD',      values: data.map(d => d.od      || 0), chartType: 'line' },
					],
				},
				type: 'axis-mixed',
				height: 260,
				colors: ['#059669', '#dc2626', '#d97706'],
				barOptions: { stacked: false, spaceRatio: 0.5 },
			});
		} catch (e) {
			$('' + $sel).html('<div class="sad-empty"><div class="sad-empty-title">Chart unavailable</div></div>');
		}
	}

	_render_daily_trend($sel, data) {
		if (!data || !data.length) { $('' + $sel).html(this._empty_html()); return; }
		const container = document.querySelector($sel);
		if (!container) return;
		try {
			new frappe.Chart(container, {
				data: {
					labels: data.map(d => d.date || ''),
					datasets: [
						{ name: 'Present', values: data.map(d => d.present || 0), chartType: 'bar' },
						{ name: 'Total',   values: data.map(d => d.total   || 0), chartType: 'line' },
					],
				},
				type: 'axis-mixed',
				height: 220,
				colors: ['#059669', '#2563eb'],
				barOptions: { spaceRatio: 0.3 },
			});
		} catch (e) {
			$('' + $sel).html('<div class="sad-empty"><div class="sad-empty-title">Chart unavailable</div></div>');
		}
	}

	// ── Tab: Examination ──────────────────────────────────────────────────────

	_load_examination() {
		this._show_loading(4);

		frappe.call({
			method: `${PAGE_METHOD}.get_examination_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;

				const total_plans    = d.exam_plans.length;
				const active_plans   = d.exam_plans.filter(p => p.status === 'Active').length;
				const total_enrolled = d.exam_plans.reduce((s, p) => s + (p.enrolled_students || 0), 0);
				const total_marks    = (d.course_marks_status || []).reduce((s, x) => s + (x.value || 0), 0);
				const submitted      = (d.course_marks_status || []).find(x => x.label === 'Submitted');
				const rp             = d.result_publish_stats || {};

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Exam Plans',           total_plans,                              '📝', 'primary', `${active_plans} active`,                    { module:'examination', dimension:'exam_plans',     value:'all' })}
						${this._kpi('Total Enrolled',       fmt_number(total_enrolled),               '🎓', 'info',    'exam enrollments',                           { module:'examination', dimension:'marks_status',   value:'all' })}
						${this._kpi('Marks Submitted',      submitted ? fmt_number(submitted.value) : '0', '✅', 'success', `of ${fmt_number(total_marks)} records`, { module:'examination', dimension:'marks_status',   value:'Submitted' })}
						${this._kpi('Results Published',    fmt_number(rp.published || 0),            '📢', 'success', `${fmt_number(rp.unpublished || 0)} pending`,  { module:'examination', dimension:'result_publish', value:'published' })}
						${this._kpi('Grade Appeals',        fmt_number(d.total_grade_appeals || 0),   '⚖️', 'warning', 'filed by students',                          { module:'examination', dimension:'grade_appeal_status', value:'all' })}
						${this._kpi('Transcripts',          fmt_number(d.total_transcripts || 0),     '📄', 'purple',  `${fmt_number(d.generated_transcripts || 0)} generated`, { module:'examination', dimension:'transcript_status', value:'Generated' })}
						${this._kpi('Exam Barcodes',         fmt_number(d.total_barcodes || 0),        '🔖', 'info',    `${d.barcode_exam_plans || 0} exam plans`,              { module:'examination', dimension:'barcode_list',      value:'all' })}
					</div>

					<div class="sad-section-title">Exam Performance</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-ex-grade',      'Grade Distribution',    'Student grade spread',        'Click to explore', '')}
						${this._chart_card('sad-ex-enrstatus',  'Enrollment Status',     'Pass / Fail / Detained',      '', '')}
						${this._chart_card('sad-ex-markstatus', 'Marks Entry Status',    'Draft / Submitted / Locked',  '', '')}
						${this._chart_card('sad-ex-examstatus', 'Exam Plan Status',      'Active vs Inactive plans',    '', '')}
					</div>

					<div class="sad-section-title">Result Quality</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-ex-fairness',  'Fairness Status',         'Fair / Unfair / Malpractice',  '', '')}
						${this._chart_card('sad-ex-attmarks',  'Attendance in Marks',     'Present / Absent / Detained',  '', '')}
						${this._chart_card('sad-ex-mfa',       'MFA Distribution',        'MFA Granted vs No MFA',        '', '')}
						${this._chart_card('sad-ex-plans',     'Exam Plans Overview',     'Enrollments per exam plan',    '', '')}
					</div>

					<div class="sad-section-title">Re-Examination & Improvement</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-ex-reexam',        'Re-Exam Status',           'Registered / Cancelled',      '', '')}
						${this._chart_card('sad-ex-reexam-pay',    'Re-Exam Payment',          'Payment pipeline status',      '', '')}
						${this._chart_card('sad-ex-improve',       'Improvement Exam Status',  'Registered / Cancelled',      '', '')}
						${this._chart_card('sad-ex-improve-pay',   'Improvement Payment',      'Payment pipeline status',      '', '')}
					</div>

					<div class="sad-section-title">Grade Appeals</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-ex-appeal-type',   'Appeal Type',         'Re-evaluation / Marks Correction / Grade Change', '', '')}
						${this._chart_card('sad-ex-appeal-status', 'Appeal Status',       'Submitted → Under Review → Resolved / Rejected',  'Click to explore', '')}
					</div>

					<div class="sad-section-title">Transcripts</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-ex-trans-type',   'Transcript Type',    'Interim vs Final',          '', '')}
						${this._chart_card('sad-ex-trans-status', 'Transcript Status',  'Generated vs Revoked',      '', '')}
						${this._result_publish_card('sad-ex-result-pub', rp)}
					</div>

					<div class="sad-section-title">Exam Barcodes</div>
					<div class="sad-chart-grid">
						<div class="sad-chart-wide">
							${this._chart_card('sad-ex-barcode-plan', 'Barcodes per Exam Plan', 'Barcode generation per exam', 'Click bar to view students', '')}
						</div>
					</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-ex-barcode-course', 'Barcodes per Course', 'Course-wise barcode count', '', '')}
					</div>
				`);

				this._render_donut('#sad-ex-grade .sad-chart-body',       d.grade_distribution,      'examination', 'grade');
				this._render_donut('#sad-ex-enrstatus .sad-chart-body',   d.enrollment_status,       'examination', 'enrollment_status');
				this._render_donut('#sad-ex-markstatus .sad-chart-body',  d.course_marks_status,     'examination', 'marks_status');
				this._render_donut('#sad-ex-examstatus .sad-chart-body',  d.exam_status,             'examination', 'exam_status');
				this._render_donut('#sad-ex-fairness .sad-chart-body',    d.fairness_dist,           'examination', 'fairness');
				this._render_donut('#sad-ex-attmarks .sad-chart-body',    d.att_in_marks,            'examination', 'att_marks');
				this._render_donut('#sad-ex-mfa .sad-chart-body',         d.mfa_dist,                'examination', 'mfa');
				this._render_exam_plans('#sad-ex-plans .sad-chart-body',  d.exam_plans);
				this._render_donut('#sad-ex-reexam .sad-chart-body',      d.reexam_stats,            'examination', 'reexam');
				this._render_donut('#sad-ex-reexam-pay .sad-chart-body',  d.reexam_payment,          'examination', 'reexam_payment');
				this._render_donut('#sad-ex-improve .sad-chart-body',     d.improvement_stats,       'examination', 'improvement');
				this._render_donut('#sad-ex-improve-pay .sad-chart-body', d.improvement_payment,     'examination', 'improvement_payment');
				this._render_donut('#sad-ex-appeal-type .sad-chart-body', d.grade_appeal_type,       'examination', 'grade_appeal_type');
				this._render_funnel('#sad-ex-appeal-status .sad-chart-body', d.grade_appeal_status,  { module: 'examination', dimension: 'grade_appeal_status' });
				this._render_donut('#sad-ex-trans-type .sad-chart-body',   d.transcript_type_dist,   'examination', 'transcript_type');
				this._render_donut('#sad-ex-trans-status .sad-chart-body', d.transcript_status_dist, 'examination', 'transcript_status');
				this._render_bar_horizontal('#sad-ex-barcode-plan .sad-chart-body',   d.barcode_by_plan,   { module: 'examination', dimension: 'barcode_plan' });
				this._render_bar_horizontal('#sad-ex-barcode-course .sad-chart-body', d.barcode_by_course, { module: 'examination', dimension: 'barcode_course' });
			},
		});
	}

	_render_exam_plans($sel, data) {
		if (!data || !data.length) { $('' + $sel).html(this._empty_html()); return; }
		const top = data.slice(0, 8);
		const max = Math.max(...top.map(x => x.enrolled_students || 0));
		const html = top.map(p => `
			<div class="sad-progress-item">
				<div class="sad-progress-label">
					<span class="sad-progress-name">${p.label}</span>
					<span class="sad-progress-val">${p.enrolled_students || 0}</span>
				</div>
				<div class="sad-progress-track">
					<div class="sad-progress-fill" style="width:${max ? (p.enrolled_students / max * 100) : 0}%; background:var(--sad-primary)"></div>
				</div>
			</div>
		`).join('');
		$('' + $sel).html(`<div class="sad-progress-list" style="padding:4px 0">${html}</div>`);
	}

	// ── Tab: ID Card ──────────────────────────────────────────────────────────

	_load_idcard() {
		this._show_loading(4);
		frappe.call({
			method: `${PAGE_METHOD}.get_idcard_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;
				const gen_pct = d.total_cards ? Math.round((d.generated_cards + d.printed_cards) / d.total_cards * 100) : 0;

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Total ID Cards',   d.total_cards,     '🪪', 'primary', `${d.active_cards} active`,            { module:'idcard', dimension:'card_status', value:'all' })}
						${this._kpi('Generated',        d.generated_cards, '✅', 'success', 'ready to print',                      { module:'idcard', dimension:'card_status', value:'Generated' })}
						${this._kpi('Printed',          d.printed_cards,   '🖨️', 'info',    `${gen_pct}% issuance rate`,           { module:'idcard', dimension:'card_status', value:'Printed' })}
						${this._kpi('Cancelled/Expired',d.cancelled_cards, '❌', 'danger',  'deactivated cards',                   { module:'idcard', dimension:'card_status', value:'Cancelled' })}
					</div>

					<div class="sad-section-title">Card Status & Type</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-id-status',  'Card Status',          'Draft / Generated / Printed / Cancelled / Expired', 'Click to explore', '')}
						${this._chart_card('sad-id-type',    'Card Type',            'Student / Faculty / Driver / Visitor / Non-Faculty', '', '')}
						${this._chart_card('sad-id-dept',    'Cards by Department',  'Department-wise distribution', 'Click bar to drill down', '')}
					</div>

					<div class="sad-section-title">Print & Issuance</div>
					<div class="sad-chart-grid">
						<div class="sad-chart-wide">
							${this._chart_card('sad-id-program', 'Cards by Program / Cohort', 'Cohort-wise card issuance', 'Click bar to drill down', '')}
						</div>
					</div>
				`);

				this._render_donut('#sad-id-status .sad-chart-body',  d.status_dist, 'idcard', 'card_status');
				this._render_donut('#sad-id-type .sad-chart-body',    d.type_dist,   'idcard', 'card_type');
				this._render_bar_horizontal('#sad-id-dept .sad-chart-body',    d.dept_dist,    { module: 'idcard', dimension: 'dept' });
				this._render_bar_horizontal('#sad-id-program .sad-chart-body', d.program_dist, { module: 'idcard', dimension: 'program' });
			},
		});
	}

	// ── Tab: Venue Booking ────────────────────────────────────────────────────

	_load_venue() {
		this._show_loading(4);
		frappe.call({
			method: `${PAGE_METHOD}.get_venue_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Total Bookings',   d.total_bookings,   '🏛️', 'primary', 'all requests',                 { module:'venue', dimension:'booking_status', value:'all' })}
						${this._kpi('Pending Allotment', d.pending_bookings, '⏳', 'warning', 'awaiting decision',            { module:'venue', dimension:'booking_status', value:'Pending Allotment' })}
						${this._kpi('Allotted',         d.approved_bookings,'✅', 'success', 'confirmed bookings',           { module:'venue', dimension:'booking_status', value:'Allotted' })}
						${this._kpi('Rejected/Cancelled',d.rejected_bookings,'❌','danger',  'declined or cancelled',        { module:'venue', dimension:'booking_status', value:'Rejected' })}
					</div>

					<div class="sad-section-title">Booking Overview</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-vn-status',   'Booking Status',      'Pending / Approved / Rejected / Cancelled', 'Click to explore', '')}
						${this._chart_card('sad-vn-vtype',    'Venue Type',          'Classroom / Moot Court / Conference Hall etc.', '', '')}
						${this._chart_card('sad-vn-requester','Requester Type',      'Student / Faculty / Staff / Other', '', '')}
					</div>

					<div class="sad-section-title">Usage Analysis</div>
					<div class="sad-chart-grid">
						<div class="sad-chart-wide">
							${this._chart_card('sad-vn-rooms', 'Top Booked Rooms/Venues', 'Most requested venues', 'Click bar to drill down', '')}
						</div>
					</div>
				`);

				this._render_funnel('#sad-vn-status .sad-chart-body',     d.status_dist,    { module: 'venue', dimension: 'booking_status' });
				this._render_donut('#sad-vn-vtype .sad-chart-body',       d.venue_type_dist,'venue', 'venue_type');
				this._render_donut('#sad-vn-requester .sad-chart-body',   d.requester_dist, 'venue', 'requester_type');
				this._render_bar_horizontal('#sad-vn-rooms .sad-chart-body', d.room_dist,   { module: 'venue', dimension: 'room' });
			},
		});
	}

	// ── Tab: Promotion Policy ─────────────────────────────────────────────────

	_load_promotion() {
		this._show_loading(4);
		frappe.call({
			method: `${PAGE_METHOD}.get_promotion_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;
				const promoted_pct = d.total_promotions
					? Math.round((d.promoted_count / d.total_promotions) * 100) : 0;

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Total Processed',  d.total_promotions,  '🎖️', 'primary', 'promotion decisions',           { module:'promotion', dimension:'promotion_status', value:'all' })}
						${this._kpi('Promoted',         d.promoted_count,    '✅', 'success', `${promoted_pct}% promotion rate`,{ module:'promotion', dimension:'promotion_status', value:'Promoted' })}
						${this._kpi('Not Promoted',     d.not_promoted_count,'❌', 'danger',  'failed criteria',               { module:'promotion', dimension:'promotion_status', value:'Not Promoted' })}
						${this._kpi('Conditional',      d.conditional_count, '⚠️', 'warning', 'pending review',               { module:'promotion', dimension:'promotion_status', value:'Conditional' })}
						${this._kpi('Active Policies',  d.active_policies,   '📋', 'info',    `${d.total_policies} total`,    { module:'promotion', dimension:'policy_status',    value:'Active' })}
					</div>

					<div class="sad-section-title">Promotion Results</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-pr-status',     'Promotion Status',      'Promoted / Not Promoted / Conditional / Override', 'Click to explore', '')}
						${this._chart_card('sad-pr-override',   'Manual Overrides',      'Override-Promoted vs Override-Not Promoted', '', '')}
						${this._chart_card('sad-pr-policy',     'Policy Status',         'Draft / Active / Archived', '', '')}
					</div>

					<div class="sad-section-title">Criteria Check Results</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-pr-cgpa',       'CGPA Check',            'Pass / Fail / Not Checked', '', '')}
						${this._chart_card('sad-pr-backlog',    'Backlog Check',         'Pass / Fail / Not Checked', '', '')}
						${this._chart_card('sad-pr-attendance', 'Attendance Check',      'Pass / Fail / Not Checked', '', '')}
						${this._chart_card('sad-pr-shortage',   'Course Shortage Check', 'Pass / Fail / Not Checked', '', '')}
					</div>

					<div class="sad-section-title">Program-wise Promotions</div>
					<div class="sad-chart-grid">
						<div class="sad-chart-wide">
							${this._chart_card('sad-pr-program', 'Promotion by Program/Cohort', 'Promotion outcomes per cohort', 'Click bar to drill down', '')}
						</div>
					</div>
				`);

				this._render_funnel('#sad-pr-status .sad-chart-body',    d.promotion_status, { module: 'promotion', dimension: 'promotion_status' });
				this._render_donut('#sad-pr-override .sad-chart-body',   d.override_dist,    'promotion', 'override');
				this._render_donut('#sad-pr-policy .sad-chart-body',     d.policy_status,    'promotion', 'policy_status');
				this._render_donut('#sad-pr-cgpa .sad-chart-body',       d.cgpa_result,      'promotion', 'cgpa_result');
				this._render_donut('#sad-pr-backlog .sad-chart-body',    d.backlog_result,   'promotion', 'backlog_result');
				this._render_donut('#sad-pr-attendance .sad-chart-body', d.attendance_result,'promotion', 'attendance_result');
				this._render_donut('#sad-pr-shortage .sad-chart-body',   d.shortage_result,  'promotion', 'shortage_result');
				this._render_bar_horizontal('#sad-pr-program .sad-chart-body', d.cohort_dist,{ module: 'promotion', dimension: 'cohort' });
			},
		});
	}

	_result_publish_card(id, rp) {
		const published   = rp.published   || 0;
		const unpublished = rp.unpublished || 0;
		const total       = rp.total       || (published + unpublished);
		const pct         = total ? Math.round(published / total * 100) : 0;
		const color       = pct >= 80 ? 'var(--sad-success)' : pct >= 50 ? 'var(--sad-warning)' : 'var(--sad-danger)';
		return `
		<div class="sad-chart-card" id="${id}">
			<div class="sad-chart-header">
				<div class="sad-chart-title-wrap">
					<div class="sad-chart-title">Result Publishing</div>
					<div class="sad-chart-subtitle">Published vs pending</div>
				</div>
			</div>
			<div class="sad-chart-body">
				<div style="padding:16px 8px">
					<div class="sad-progress-item" style="margin-bottom:16px">
						<div class="sad-progress-label">
							<span class="sad-progress-name">Published</span>
							<span class="sad-progress-val" style="color:${color};font-weight:700">${pct}%</span>
						</div>
						<div class="sad-progress-track">
							<div class="sad-progress-fill" style="width:${pct}%;background:${color}"></div>
						</div>
					</div>
					<div style="display:flex;gap:16px;justify-content:center;flex-wrap:wrap;font-size:13px">
						<div style="text-align:center"><div style="font-size:22px;font-weight:700;color:var(--sad-success)">${fmt_number(published)}</div><div style="color:var(--sad-text3)">Published</div></div>
						<div style="text-align:center"><div style="font-size:22px;font-weight:700;color:var(--sad-warning)">${fmt_number(unpublished)}</div><div style="color:var(--sad-text3)">Pending</div></div>
						<div style="text-align:center"><div style="font-size:22px;font-weight:700;color:var(--sad-primary)">${rp.avg_term_gpa || '—'}</div><div style="color:var(--sad-text3)">Avg SGPA</div></div>
						<div style="text-align:center"><div style="font-size:22px;font-weight:700;color:var(--sad-info)">${rp.avg_cgpa || '—'}</div><div style="color:var(--sad-text3)">Avg CGPA</div></div>
					</div>
				</div>
			</div>
		</div>`;
	}

	// ── Tab: Fees ─────────────────────────────────────────────────────────────

	_load_fees() {
		this._show_loading(4);

		frappe.call({
			method: `${PAGE_METHOD}.get_fees_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;
				const s = d.collection_summary || {};
				const rate = s.total_billed ? Math.round(s.total_collected / s.total_billed * 100) : 0;

				$('#sad-tab-content').html(`
					<div class="sad-summary-card">
						<div class="sad-sc-grid">
							<div class="sad-sc-item">
								<div class="sc-label">Total Billed</div>
								<div class="sc-value">${fmt_currency(s.total_billed || 0)}</div>
								<div class="sc-sub">${fmt_number(s.total_invoices || 0)} invoices</div>
							</div>
							<div class="sad-sc-item">
								<div class="sc-label">Collected</div>
								<div class="sc-value">${fmt_currency(s.total_collected || 0)}</div>
								<div class="sc-sub">${rate}% collection rate</div>
							</div>
							<div class="sad-sc-item">
								<div class="sc-label">Outstanding</div>
								<div class="sc-value">${fmt_currency(s.total_outstanding || 0)}</div>
								<div class="sc-sub">${fmt_number(s.students_billed || 0)} students billed</div>
							</div>
						</div>
					</div>

					<div class="sad-kpi-grid">
						${this._kpi('Collection Rate', rate + '%', '📈', rate >= 80 ? 'success' : 'warning', 'of total billed', { module:'fees', dimension:'payment_status', value:'Paid' })}
						${this._kpi('Total Invoices', fmt_number(s.total_invoices || 0), '🧾', 'info', 'fee invoices', { module:'fees', dimension:'payment_status', value:'Paid' })}
						${this._kpi('Outstanding', fmt_currency(s.total_outstanding || 0), '⚠️', 'danger', 'pending collection', { module:'fees', dimension:'payment_status', value:'Unpaid' })}
						${this._kpi('Students Billed', fmt_number(s.students_billed || 0), '🎓', 'primary', 'unique students', { module:'fees', dimension:'students_billed', value:'all' })}
					</div>

					<div class="sad-section-title">Payment Analytics</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-fe-paystatus', 'Payment Status Distribution', 'Invoice-level payment breakdown', 'Click to drill down', '')}
						${this._chart_card('sad-fe-smstatus', 'Student Fee Status', 'Student-level payment status', '', '')}
						${this._chart_card('sad-fe-programs',  'Program-wise Fees', 'Collection vs Outstanding', '', '')}
					</div>

					<div class="sad-section-title">Collection Trend</div>
					<div class="sad-chart-grid">
						<div class="sad-chart-wide">
							${this._chart_card('sad-fe-trend', 'Monthly Fee Collection Trend', 'Billed vs Collected over time', '', '')}
						</div>
					</div>
				`);

				this._render_donut('#sad-fe-paystatus .sad-chart-body', d.payment_status_distribution, 'fees', 'payment_status');
				this._render_donut('#sad-fe-smstatus .sad-chart-body', d.student_fee_payment_status, 'fees', 'sm_fee_status');
				this._render_program_fees('#sad-fe-programs .sad-chart-body', d.program_fees);
				this._render_fee_trend('#sad-fe-trend .sad-chart-body', d.monthly_collection);
			},
		});
	}

	_render_program_fees($sel, data) {
		if (!data || !data.length) { $('' + $sel).html(this._empty_html()); return; }
		const max = Math.max(...data.map(x => x.total_billed || 0));
		const html = data.map(d => `
			<div class="sad-progress-item">
				<div class="sad-progress-label">
					<span class="sad-progress-name">${d.label}</span>
					<span class="sad-progress-val">${fmt_currency(d.collected)}</span>
				</div>
				<div class="sad-progress-track">
					<div class="sad-progress-fill" style="width:${max ? (d.collected / max * 100) : 0}%; background:var(--sad-success)"></div>
				</div>
				<div style="display:flex;gap:8px;margin-top:2px">
					<span style="font-size:10px;color:var(--sad-text3)">Outstanding: ${fmt_currency(d.outstanding)}</span>
				</div>
			</div>
		`).join('');
		$('' + $sel).html(`<div class="sad-progress-list" style="max-height:260px;overflow-y:auto;padding:4px 0">${html}</div>`);
	}

	_render_fee_trend($sel, data) {
		if (!data || !data.length) { $('' + $sel).html(this._empty_html()); return; }
		const container = document.querySelector($sel);
		if (!container) return;
		try {
			new frappe.Chart(container, {
				data: {
					labels: data.map(d => d.month_label || d.month),
					datasets: [
						{ name: 'Billed',    values: data.map(d => d.billed    || 0), chartType: 'bar' },
						{ name: 'Collected', values: data.map(d => d.collected || 0), chartType: 'line' },
					],
				},
				type: 'axis-mixed',
				height: 240,
				colors: ['#2563eb', '#059669'],
				tooltipOptions: { formatTooltipY: (v) => fmt_currency(v) },
			});
		} catch (e) {
			$('' + $sel).html('<div class="sad-empty"><div class="sad-empty-title">Chart unavailable</div></div>');
		}
	}

	// ── Tab: Hostel ───────────────────────────────────────────────────────────

	_load_hostel() {
		this._show_loading(4);

		frappe.call({
			method: `${PAGE_METHOD}.get_hostel_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Total Beds', fmt_number(d.total_beds), '🏠', 'primary', 'across all hostels', { module:'hostel', dimension:'all_beds', value:'all' })}
						${this._kpi('Occupied', fmt_number(d.occupied_beds), '✅', 'success', d.occupancy_rate + '% occupancy', { module:'hostel', dimension:'active_allocations', value:'all' })}
						${this._kpi('Available', fmt_number(d.available_beds), '🔲', 'info', 'vacant beds', { module:'hostel', dimension:'available_beds', value:'all' })}
						${this._kpi('Occupancy Rate', d.occupancy_rate + '%', '📊', d.occupancy_rate >= 80 ? 'success' : 'warning', 'current utilization', { module:'hostel', dimension:'active_allocations', value:'all' })}
					</div>

					<div class="sad-section-title">Hostel Analytics</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-ho-gauge',     'Bed Occupancy Rate',     'Current utilization gauge',  '', '')}
						${this._chart_card('sad-ho-hostels',   'Per-Hostel Occupancy',   'Students per hostel block',  'Click to explore', '')}
						${this._chart_card('sad-ho-allstatus', 'Allocation Status',      'Active vs inactive allocations', '', '')}
						${this._chart_card('sad-ho-meal',      'Meal Plan Distribution', 'Student meal preferences',   '', '')}
					</div>

					<div class="sad-section-title">Complaints & Leaves</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-ho-complaint',  'Complaint Status',  'Resolution pipeline',      '', '')}
						${this._chart_card('sad-ho-comptype',   'Complaint Types',   'Category breakdown',       '', '')}
						${this._chart_card('sad-ho-leave',      'Leave Requests',    'Application status',       '', '')}
					</div>
				`);

				this._render_gauge('#sad-ho-gauge .sad-chart-body', d.occupancy_rate, `${d.occupied_beds} / ${d.total_beds} beds`);
				this._render_bar_horizontal('#sad-ho-hostels .sad-chart-body', d.hostel_occupancy, { module: 'hostel', dimension: 'hostel' });
				this._render_donut('#sad-ho-allstatus .sad-chart-body', d.allocation_status, 'hostel', 'allocation_status');
				this._render_donut('#sad-ho-meal .sad-chart-body', d.meal_distribution, 'hostel', 'meal');
				this._render_donut('#sad-ho-complaint .sad-chart-body', d.complaint_status, 'hostel', 'complaint_status');
				this._render_donut('#sad-ho-comptype .sad-chart-body', d.complaint_type, 'hostel', 'complaint_type');
				this._render_donut('#sad-ho-leave .sad-chart-body', d.leave_request_status, 'hostel', 'leave');
			},
		});
	}

	// ── Tab: Placement ────────────────────────────────────────────────────────

	_load_placement() {
		this._show_loading(4);

		frappe.call({
			method: `${PAGE_METHOD}.get_placement_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Opportunities', d.total_opportunities, '🏢', 'primary', 'total openings', { module:'placement', dimension:'opportunity_status', value:'all' })}
						${this._kpi('Applications', d.total_applications, '📋', 'info', 'student applications', { module:'placement', dimension:'status', value:'Applied' })}
						${this._kpi('Offers Issued', d.total_offers, '📄', 'warning', 'placement offers', { module:'placement', dimension:'status', value:'Pending' })}
						${this._kpi('Accepted Offers', d.accepted_offers, '✅', 'success', `${d.placement_rate}% acceptance rate`, { module:'placement', dimension:'status', value:'Accepted' })}
						${this._kpi('Placement Rate', d.placement_rate + '%', '📈', d.placement_rate >= 70 ? 'success' : 'warning', 'of applications → offers', { module:'placement', dimension:'status', value:'Accepted' })}
						${this._kpi('Avg. Compensation', fmt_currency(d.avg_compensation), '💰', 'purple', 'per accepted offer', { module:'placement', dimension:'status', value:'Accepted' })}
					</div>

					<div class="sad-section-title">Placement Pipeline</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-pl-funnel',   'Placement Funnel',         'Opportunities → Applications → Offers', '', '')}
						${this._chart_card('sad-pl-opptype',  'Opportunity Type',          'Placement vs Internship', '', '')}
						${this._chart_card('sad-pl-oppstatus','Opportunity Status',         'Pipeline stages', '', '')}
					</div>

					<div class="sad-section-title">Offers & Applications</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-pl-offstatus', 'Offer Status',     'Accepted vs Pending vs Rejected', '', '')}
						${this._chart_card('sad-pl-appstatus', 'Application Status','Shortlisted vs Rejected', '', '')}
						<div class="sad-chart-wide">
							${this._chart_card('sad-pl-companies', 'Top Companies by Offers', 'Hiring volume per company', 'Click to view students', '')}
						</div>
					</div>
				`);

				// Funnel: Opportunities → Applications → Offers → Accepted
				this._render_funnel('#sad-pl-funnel .sad-chart-body', [
					{ label: 'Opportunities', value: d.total_opportunities },
					{ label: 'Applications',  value: d.total_applications },
					{ label: 'Offers',        value: d.total_offers },
					{ label: 'Accepted',      value: d.accepted_offers },
				]);

				this._render_donut('#sad-pl-opptype .sad-chart-body', d.opportunity_type, 'placement', 'opp_type');
				this._render_donut('#sad-pl-oppstatus .sad-chart-body', d.opportunity_status, 'placement', 'opp_status');
				this._render_donut('#sad-pl-offstatus .sad-chart-body', d.status, 'placement', 'status');
				this._render_donut('#sad-pl-appstatus .sad-chart-body', d.application_funnel, 'placement', 'app_status');
				this._render_bar_horizontal('#sad-pl-companies .sad-chart-body', d.top_companies.map(c => ({
					label: c.label, value: c.offer_count,
				})), { module: 'placement', dimension: 'company' });
			},
		});
	}

	// ── Tab: Programme Management ─────────────────────────────────────────────

	_load_programme() {
		this._show_loading(5);

		frappe.call({
			method: `${PAGE_METHOD}.get_programme_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;

				const enroll_rate_color = d.enrollment_rate >= 80 ? 'success' : d.enrollment_rate >= 50 ? 'warning' : 'danger';

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Active Programs',      d.active_programs,      '🏫', 'primary',  `${d.total_programs} total`,               { module:'programme', dimension:'program_status', value:'Active' })}
						${this._kpi('Active Cohorts',       d.active_cohorts,       '🗂️', 'info',     `${d.total_cohorts} total cohorts`,         { module:'programme', dimension:'cohort_status',  value:'Active' })}
						${this._kpi('Total Enrollments',    d.total_enrollments,    '🎓', 'success',  `${d.active_enrollments} actively enrolled`, { module:'programme', dimension:'enrollment_status', value:'Enrolled' })}
						${this._kpi('Open Course Offerings',d.open_offerings,       '📖', 'warning',  `${d.total_offerings} total offerings`,     { module:'programme', dimension:'offering_status', value:'Open' })}
						${this._kpi('Enrollment Rate',      d.enrollment_rate + '%','📊', enroll_rate_color, 'enrolled vs dropped',              { module:'programme', dimension:'enrollment_status', value:'Enrolled' })}
					</div>

					<div class="sad-section-title">Program & Cohort Overview</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-pm-prog-status',  'Program Status',          'Active vs Inactive',           '', '')}
						${this._chart_card('sad-pm-cohort-status','Cohort Status',           'Planned / Active / Completed / Inactive', '', '')}
						${this._chart_card('sad-pm-level',        'Level of Study',          'UG / PG / Research breakdown', '', '')}
					</div>

					<div class="sad-section-title">Enrollment Analysis</div>
					<div class="sad-chart-grid">
						<div class="sad-chart-wide">
							${this._chart_card('sad-pm-prog-enroll', 'Program-wise Enrollment', 'Student count per program', 'Click bar to drill down', '')}
						</div>
					</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-pm-enroll-status', 'Enrollment Status',        'Enrolled / Dropped / Completed / Pending', '', '')}
						${this._chart_card('sad-pm-cohort-enroll', 'Top Cohorts by Enrollment','Active cohort headcount',   'Click bar to drill down', '')}
					</div>

					<div class="sad-section-title">Course Offering Analysis</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-pm-offering-status', 'Course Offering Status', 'Open vs Closed',             '', '')}
						${this._chart_card('sad-pm-offering-prog',   'Offerings by Program',   'Course offering distribution','Click bar to drill down', '')}
						${this._chart_card('sad-pm-course-status',   'Enrolled Course Status', 'Enrolled vs Dropped courses', '', '')}
					</div>
				`);

				this._render_donut('#sad-pm-prog-status .sad-chart-body',   d.program_status,      'programme', 'program_status');
				this._render_donut('#sad-pm-cohort-status .sad-chart-body', d.cohort_status,       'programme', 'cohort_status');
				this._render_donut('#sad-pm-level .sad-chart-body',         d.level_of_study,      'programme', 'level_of_study');
				this._render_bar_horizontal('#sad-pm-prog-enroll .sad-chart-body',   d.program_enrollment,  { module: 'programme', dimension: 'program_enrollment' });
				this._render_donut('#sad-pm-enroll-status .sad-chart-body', d.enrollment_status,   'programme', 'enrollment_status');
				this._render_bar_horizontal('#sad-pm-cohort-enroll .sad-chart-body', d.cohort_enrollment,   { module: 'programme', dimension: 'cohort_enrollment' });
				this._render_donut('#sad-pm-offering-status .sad-chart-body', d.offering_status,   'programme', 'offering_status');
				this._render_bar_horizontal('#sad-pm-offering-prog .sad-chart-body', d.offering_by_program, { module: 'programme', dimension: 'offering_program' });
				this._render_donut('#sad-pm-course-status .sad-chart-body', d.course_enroll_status,'programme', 'course_enroll_status');
			},
		});
	}

	// ── Tab: Admission ────────────────────────────────────────────────────────

	_load_admission() {
		this._show_loading(5);

		frappe.call({
			method: `${PAGE_METHOD}.get_admission_analytics`,
			args: this.filters,
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;

				const acceptance_color = d.acceptance_rate >= 60 ? 'success' : d.acceptance_rate >= 30 ? 'warning' : 'danger';

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Total Applicants',   d.total_applicants, '📋', 'primary',  'across all cycles',         { module:'admission', dimension:'app_status',  value:'all' })}
						${this._kpi('Active Cycles',      d.active_cycles,    '🔄', 'info',     'currently open',            { module:'admission', dimension:'cycle_status', value:'Active' })}
						${this._kpi('Offers Issued',      d.total_offers,     '📨', 'purple',   `${d.accepted_offers} accepted`, { module:'admission', dimension:'status', value:'Issued' })}
						${this._kpi('Acceptance Rate',    d.acceptance_rate + '%', '✅', acceptance_color, 'of offers accepted', { module:'admission', dimension:'status', value:'Accepted' })}
						${this._kpi('Merit Lists',        d.total_merit_lists,'📊', 'warning',  'generated / published',     { module:'admission', dimension:'merit_status', value:'all' })}
					</div>

					<div class="sad-section-title">Admission Pipeline</div>
					<div class="sad-chart-grid">
						<div class="sad-chart-wide">
							${this._chart_card('sad-adm-pipeline', 'Application Status Pipeline', 'End-to-end applicant journey', 'Stages ordered from Draft → Accepted', '')}
						</div>
					</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-adm-cycle',   'Admission Cycle Status',  'Draft / Active / Closed', '', '')}
						${this._chart_card('sad-adm-program', 'Program-wise Applications','Application count per program', 'Click bar to drill down', '')}
					</div>

					<div class="sad-section-title">Stage-wise Breakdown</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-adm-eligibility', 'Eligibility Status',     'Eligible / Ineligible / Pending', '', '')}
						${this._chart_card('sad-adm-test',        'Test Result Status',     'Qualified / Not Qualified / Pending', '', '')}
						${this._chart_card('sad-adm-interview',   'Interview Status',       'Scheduled / Completed / No Show', '', '')}
						${this._chart_card('sad-adm-appfee',      'Application Fee Status', 'Pending / Paid / Waived', '', '')}
					</div>

					<div class="sad-section-title">Outcomes</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-adm-offer',  'Offer Letter Status',  'Issued / Accepted / Rejected / Expired', '', '')}
						${this._chart_card('sad-adm-merit',  'Merit List Status',    'Draft / Generated / Published', '', '')}
					</div>
				`);

				// Pipeline funnel — ordered stages
				const pipeline_order = ['Draft','Submitted','Under Review','Shortlisted','Waitlisted','Offered','Accepted','Rejected','Withdrawn'];
				const pipeline_data = pipeline_order
					.map(s => (d.status_pipeline || []).find(x => x.label === s))
					.filter(Boolean);
				this._render_funnel('#sad-adm-pipeline .sad-chart-body', pipeline_data);

				this._render_donut('#sad-adm-cycle .sad-chart-body',       d.cycle_status,               'admission', 'cycle_status');
				this._render_bar_horizontal('#sad-adm-program .sad-chart-body', d.program_applications || [], { module: 'admission', dimension: 'app_program' });
				this._render_donut('#sad-adm-eligibility .sad-chart-body', d.eligibility_distribution,   'admission', 'eligibility_status');
				this._render_donut('#sad-adm-test .sad-chart-body',        d.test_result_distribution,   'admission', 'test_result_status');
				this._render_donut('#sad-adm-interview .sad-chart-body',   d.interview_distribution,     'admission', 'interview_status');
				this._render_donut('#sad-adm-appfee .sad-chart-body',      d.application_fee_status,     'admission', 'app_fee_status');
				this._render_donut('#sad-adm-offer .sad-chart-body',       d.offer_status_distribution,  'admission', 'status');
				this._render_donut('#sad-adm-merit .sad-chart-body',       d.merit_list_status,          'admission', 'merit_status');
			},
		});
	}

	// ── Chart renderers ───────────────────────────────────────────────────────

	_render_donut($sel, data, module, dimension) {
		const container = document.querySelector($sel);
		if (!container) return;
		if (!data || !data.length) { container.innerHTML = this._empty_html(); return; }

		const colors = data.map(d => status_color(d.label));
		try {
			const chart = new frappe.Chart(container, {
				data: labels_and_values(data),
				type: 'donut',
				height: 220,
				colors: colors,
			});

			container.addEventListener('data-select', (e) => {
				if (!e.detail) return;
				const idx = e.detail.index != null ? e.detail.index : null;
				const lbl = idx != null ? data[idx]?.label : null;
				if (lbl && module && dimension) {
					this._open_drilldown(module, dimension, lbl, data[idx]);
				}
			});
		} catch (err) {
			container.innerHTML = this._empty_html('Chart unavailable');
		}
	}

	_render_bar($sel, chartData, opts = {}) {
		const container = typeof $sel === 'string' ? document.querySelector($sel) : $sel;
		if (!container) return;
		try {
			const chart = new frappe.Chart(container, {
				data: chartData,
				type: 'bar',
				height: opts.height || 220,
				colors: opts.colors || PALETTE.primary,
				barOptions: { spaceRatio: 0.4 },
			});
		} catch (e) {
			container.innerHTML = this._empty_html();
		}
	}

	_render_bar_horizontal($sel, data, drilldown_opts = {}) {
		const container = document.querySelector($sel);
		if (!container) return;
		if (!data || !data.length) { container.innerHTML = this._empty_html(); return; }

		const max = Math.max(...data.map(x => x.value || 0));
		const html = data.map((d, i) => {
			const pct = max ? (d.value / max * 100) : 0;
			const color = PALETTE.mixed[i % PALETTE.mixed.length];
			return `
			<div class="sad-funnel-step" data-label="${d.label}" data-value="${d.value}">
				<div class="sad-funnel-name">${d.label}</div>
				<div class="sad-funnel-bar-wrap">
					<div class="sad-funnel-bar" style="width:${pct}%; background:${color}">
						<span class="sad-funnel-bar-label">${fmt_number(d.value)}</span>
					</div>
				</div>
				<div class="sad-funnel-meta">${fmt_number(d.value)}</div>
			</div>`;
		}).join('');

		container.innerHTML = `<div class="sad-funnel" style="padding:4px 0; max-height:280px; overflow-y:auto">${html}</div>`;

		if (drilldown_opts.module && drilldown_opts.dimension) {
			container.querySelectorAll('.sad-funnel-step').forEach((el) => {
				el.addEventListener('click', () => {
					const label = el.dataset.label;
					this._open_drilldown(drilldown_opts.module, drilldown_opts.dimension, label, { label, value: el.dataset.value });
				});
			});
		}
	}

	_render_funnel($sel, data, drilldown_opts = {}) {
		const container = document.querySelector($sel);
		if (!container) return;
		if (!data || !data.length) { container.innerHTML = this._empty_html(); return; }

		const max = Math.max(...data.map(x => x.value || 0));
		const colors = ['#1e3a8a', '#2563eb', '#0891b2', '#059669'];
		const clickable = drilldown_opts.module && drilldown_opts.dimension;
		const html = data.map((d, i) => {
			const pct = max ? Math.max((d.value / max * 100), 10) : 10;
			return `
			<div class="sad-funnel-step${clickable ? ' sad-drillable' : ''}" data-label="${d.label}" data-value="${d.value}" style="${clickable ? 'cursor:pointer' : ''}">
				<div class="sad-funnel-name">${d.label}</div>
				<div class="sad-funnel-bar-wrap">
					<div class="sad-funnel-bar" style="width:${pct}%; background:${colors[i % colors.length]}">
						<span class="sad-funnel-bar-label">${fmt_number(d.value)}</span>
					</div>
				</div>
				<div class="sad-funnel-meta">${fmt_number(d.value)}</div>
			</div>`;
		}).join('');
		container.innerHTML = `<div class="sad-funnel" style="padding:4px 0">${html}</div>`;

		if (clickable) {
			container.querySelectorAll('.sad-funnel-step.sad-drillable').forEach((el) => {
				el.addEventListener('click', () => {
					this._open_drilldown(drilldown_opts.module, drilldown_opts.dimension, el.dataset.label, {}, el.dataset.label);
				});
			});
		}
	}

	_render_gauge($sel, rate, subtitle = '') {
		const container = document.querySelector($sel);
		if (!container) return;

		const r = 54; const C = 2 * Math.PI * r;
		const filled = C * (Math.min(rate, 100) / 100);
		const color = rate >= 80 ? '#059669' : rate >= 60 ? '#d97706' : '#dc2626';

		container.innerHTML = `
		<div class="sad-gauge-wrap">
			<div class="sad-gauge-ring">
				<svg viewBox="0 0 120 120">
					<circle class="sad-gauge-bg" cx="60" cy="60" r="${r}" />
					<circle class="sad-gauge-fill"
						cx="60" cy="60" r="${r}"
						stroke="${color}"
						stroke-dasharray="${filled} ${C}"
						style="stroke-dasharray:${filled}px ${C}px"
					/>
				</svg>
				<div class="sad-gauge-text">
					<div class="sad-gauge-pct" style="color:${color}">${rate}%</div>
					<div class="sad-gauge-lbl">Utilized</div>
				</div>
			</div>
			${subtitle ? `<div style="font-size:12px;color:var(--sad-text3);text-align:center">${subtitle}</div>` : ''}
		</div>`;
	}

	// ── KPI card HTML ─────────────────────────────────────────────────────────

	_kpi(label, value, icon, variant, sub, dd = null) {
		const dd_attrs = dd
			? ` class="sad-kpi-card kpi-${variant} has-drilldown"
				data-dd-module="${dd.module}"
				data-dd-dim="${dd.dimension}"
				data-dd-val="${dd.value}"
				data-dd-title="${label}"`
			: ` class="sad-kpi-card kpi-${variant}"`;
		const arrow = dd
			? `<div class="sad-kpi-drill-arrow" style="color:var(--sad-${variant === 'primary' ? 'primary' : variant === 'success' ? 'success' : variant === 'danger' ? 'danger' : variant === 'warning' ? 'warning' : variant === 'info' ? 'info' : 'purple'})"><i class="fa fa-arrow-right"></i></div>`
			: '';
		const hint = dd
			? `<div class="sad-kpi-drill-hint"><i class="fa fa-search" style="font-size:9px"></i> Click to explore</div>`
			: '';
		return `
		<div${dd_attrs}>
			<div class="sad-kpi-accent"></div>
			<div class="sad-kpi-icon">${icon}</div>
			<div class="sad-kpi-label">${label}</div>
			<div class="sad-kpi-value">${value}</div>
			${sub ? `<div class="sad-kpi-sub">${sub}</div>` : ''}
			${hint}
			${arrow}
		</div>`;
	}

	_chart_card(id, title, subtitle, tip, badge) {
		return `
		<div class="sad-chart-card" id="${id}">
			<div class="sad-chart-header">
				<div class="sad-chart-title-wrap">
					<div class="sad-chart-title">${title}</div>
					${subtitle ? `<div class="sad-chart-subtitle">${subtitle}</div>` : ''}
				</div>
				${badge ? `<div class="sad-chart-badge">${badge}</div>` : ''}
			</div>
			<div class="sad-chart-body">
				<div class="sad-skeleton" style="height:180px"></div>
			</div>
			${tip ? `<div class="sad-chart-tip">💡 ${tip}</div>` : ''}
		</div>`;
	}

	_rate_card(id, title) {
		return `
		<div class="sad-chart-card" id="${id}">
			<div class="sad-chart-header">
				<div class="sad-chart-title-wrap">
					<div class="sad-chart-title">${title}</div>
					<div class="sad-chart-subtitle">Live performance snapshot</div>
				</div>
			</div>
			<div class="sad-chart-body"></div>
		</div>`;
	}

	_progress_bar(label, value, color) {
		const rate = Math.min(Math.max(value || 0, 0), 100);
		return `
		<div class="sad-progress-item">
			<div class="sad-progress-label">
				<span class="sad-progress-name">${label}</span>
				<span class="sad-progress-val">${rate_badge(rate)}</span>
			</div>
			<div class="sad-progress-track">
				<div class="sad-progress-fill" style="width:${rate}%; background:${color}"></div>
			</div>
		</div>`;
	}

	_empty_html(msg = 'No data available') {
		return `
		<div class="sad-empty">
			<div class="sad-empty-icon">📭</div>
			<div class="sad-empty-title">${msg}</div>
		</div>`;
	}

	_show_error() {
		$('#sad-tab-content').html(`
		<div class="sad-chart-card">
			<div class="sad-empty">
				<div class="sad-empty-icon">⚠️</div>
				<div class="sad-empty-title">Failed to load analytics</div>
				<div class="sad-empty-sub">Check console for details or try refreshing.</div>
			</div>
		</div>`);
	}

	// ── Drilldown panel ───────────────────────────────────────────────────────

	_get_list_route(module, dimension, value) {
		const v = (value && value !== 'all' && value !== 'All') ? value : null;
		const f = (field) => v ? { [field]: v } : {};

		const map = {
			// ── Students ────────────────────────────────────────────────
			'students:student_status':        { dt: 'Student Master',                filters: f('student_status') },
			'students:reg_status':            { dt: 'Student Master',                filters: f('student_status') },
			'students:gender':                { dt: 'Student Master',                filters: f('gender') },
			'students:cohort':                { dt: 'Student Master',                filters: {} },
			'students:programs_list':         { dt: 'Programme',                       filters: {} },
			'students:cohorts_list':          { dt: 'Batch',                        filters: {} },

			// ── Admission ────────────────────────────────────────────────
			'admission:app_status':           { dt: 'Admission Application',         filters: f('status') },
			'admission:app_program':          { dt: 'Admission Application',         filters: {} },
			'admission:eligibility_status':   { dt: 'Admission Application',         filters: f('eligibility_status') },
			'admission:test_result_status':   { dt: 'Admission Application',         filters: f('test_result') },
			'admission:interview_status':     { dt: 'Admission Application',         filters: f('interview_status') },
			'admission:app_fee_status':       { dt: 'Admission Application',         filters: f('application_fee_status') },
			'admission:status':         { dt: 'Offer Letter',                  filters: f('status') },
			'admission:cycle_status':         { dt: 'Admission Cycle',               filters: f('status') },
			'admission:merit_status':         { dt: 'Merit List',                    filters: f('status') },

			// ── Attendance ────────────────────────────────────────────────
			'attendance:status':              { dt: 'Student Attendance',            filters: f('status') },
			'attendance:session_type':        { dt: 'Student Attendance',            filters: f('session_type') },
			'attendance:source':              { dt: 'Student Attendance',            filters: f('source') },
			'attendance:condonation':         { dt: 'Student Attendance Condonation', filters: f('status') },
			'attendance:cond_faculty':        { dt: 'Student Attendance Condonation', filters: {} },
			'attendance:fa_mfa':              { dt: 'FA MFA Application',            filters: f('status') },
			'attendance:fa_mfa_type':         { dt: 'FA MFA Application',            filters: f('application_type') },

			// ── Examination ────────────────────────────────────────────────
			'examination:exam_status':        { dt: 'Exam Plan',                     filters: f('status') },
			'examination:exam_plans':         { dt: 'Exam Plan',                     filters: f('status') },
			'examination:enrollment_status':  { dt: 'Student Course Marks',          filters: f('enrollment_status') },
			'examination:marks_status':       { dt: 'Student Course Marks',          filters: f('status') },
			'examination:grade':              { dt: 'Student Course Marks',          filters: f('grade') },
			'examination:att_marks':          { dt: 'Student Course Marks',          filters: {} },
			'examination:fairness':           { dt: 'Student Course Marks',          filters: {} },
			'examination:mfa':                { dt: 'Student Course Marks',          filters: {} },
			'examination:reexam_payment':     { dt: 'Re Exam Registration',          filters: f('payment_status') },
			'examination:improvement_payment':{ dt: 'Improvement Exam Registration', filters: f('payment_status') },
			'examination:grade_appeal_status':{ dt: 'Grade Appeal',                  filters: f('status') },
			'examination:grade_appeal_type':  { dt: 'Grade Appeal',                  filters: f('appeal_type') },
			'examination:transcript_status':  { dt: 'Student Transcript',            filters: f('status') },
			'examination:transcript_type':    { dt: 'Student Transcript',            filters: f('transcript_type') },
			'examination:result_publish':     { dt: 'Student Result Publish',        filters: f('status') },
			'examination:barcode_list':       { dt: 'Exam Barcode',                  filters: {} },
			'examination:barcode_plan':       { dt: 'Exam Barcode',                  filters: f('exam_plan') },
			'examination:barcode_course':     { dt: 'Exam Barcode',                  filters: f('course') },

			// ── Programme ────────────────────────────────────────────────
			'programme:program_status':       { dt: 'Programme',                       filters: f('program_status') },
			'programme:level_of_study':       { dt: 'Programme',                       filters: f('level_of_study') },
			'programme:cohort_status':        { dt: 'Batch',                        filters: f('status') },
			'programme:enrollment_status':    { dt: 'Student Enrollment',            filters: f('enrollment_status') },
			'programme:course_enroll_status': { dt: 'Student Enrollment',            filters: f('enrollment_status') },
			'programme:program_enrollment':   { dt: 'Student Enrollment',            filters: {} },
			'programme:cohort_enrollment':    { dt: 'Student Enrollment',            filters: {} },
			'programme:offering_status':      { dt: 'Course Offering',               filters: f('status') },
			'programme:offering_program':     { dt: 'Course Offering',               filters: f('program') },

			// ── ID Card ────────────────────────────────────────────────
			'idcard:card_status':             { dt: 'ID Card Generation',            filters: f('card_status') },
			'idcard:card_type':               { dt: 'ID Card Generation',            filters: f('card_type') },
			'idcard:dept':                    { dt: 'ID Card Generation',            filters: f('department') },
			'idcard:program':                 { dt: 'ID Card Generation',            filters: {} },

			// ── Venue ────────────────────────────────────────────────
			'venue:booking_status':           { dt: 'Venue Booking',                 filters: f('status') },
			'venue:venue_type':               { dt: 'Venue Booking',                 filters: f('venue_type') },
			'venue:requester_type':           { dt: 'Venue Booking',                 filters: f('requester_type') },
			'venue:room':                     { dt: 'Venue Booking',                 filters: f('room') },

			// ── Promotion ────────────────────────────────────────────────
			'promotion:promotion_status':     { dt: 'Student Promotion',             filters: f('promotion_status') },
			'promotion:policy_status':        { dt: 'Promotion Policy',              filters: f('status') },
			'promotion:override':             { dt: 'Student Promotion',             filters: f('override') },
			'promotion:cgpa_result':          { dt: 'Student Promotion',             filters: {} },
			'promotion:backlog_result':       { dt: 'Student Promotion',             filters: {} },
			'promotion:attendance_result':    { dt: 'Student Promotion',             filters: {} },
			'promotion:shortage_result':      { dt: 'Student Promotion',             filters: {} },
			'promotion:cohort':               { dt: 'Student Promotion',             filters: f('cohort') },
		};

		return map[`${module}:${dimension}`] || null;
	}

	_open_drilldown(module, dimension, value, context = {}, title = null) {
		this._drilldown_state = { module, dimension, value, page: 1, page_size: 25 };
		$('#sad-dd-title').text(title || value || 'Detail View');
		$('#sad-dd-breadcrumb').text(`${module} › ${dimension} › ${value}`);
		$('#sad-dd-body').html('<div class="sad-empty"><div class="sad-empty-icon">⏳</div><div class="sad-empty-title">Loading...</div></div>');

		// Reset search on new drilldown
		$('#sad-dd-search').val('');
		$('#sad-dd-search-count').text('');
		$('#sad-dd-search-clear').hide();

		// View List button
		const listRoute = this._get_list_route(module, dimension, value);
		this._drilldown_list_route = listRoute;
		if (listRoute) {
			$('#sad-dd-viewlist').show();
		} else {
			$('#sad-dd-viewlist').hide();
		}

		$('#sad-dd-overlay, #sad-dd-panel').addClass('open');
		this._drilldown_open = true;

		this._load_drilldown_page(1);
	}

	_load_drilldown_page(page) {
		const { module, dimension, value, page_size } = this._drilldown_state;
		this._drilldown_state.page = page;

		frappe.call({
			method: `${PAGE_METHOD}.get_drilldown_data`,
			args: {
				module, dimension, value, page, page_size,
				...this.filters,
			},
			callback: (r) => {
				if (r.exc || !r.message) {
					$('#sad-dd-body').html(this._empty_html('No data found for this selection'));
					return;
				}
				const d = r.message;
				this._drilldown_state.total = d.total;
				this._render_drilldown_content(d);
			},
		});
	}

	_render_drilldown_content(d) {
		const { page, total, page_size } = this._drilldown_state;
		const total_pages = Math.ceil((total || 0) / page_size);

		const rows = d.rows || [];
		const cols = d.columns || [];

		if (!rows.length) {
			$('#sad-dd-body').html(this._empty_html('No records found'));
			return;
		}

		// Summary stats
		const stat_html = `
		<div class="sad-drilldown-stats">
			<div class="sad-drilldown-stat">
				<div class="dds-value">${fmt_number(total)}</div>
				<div class="dds-label">Total Records</div>
			</div>
			<div class="sad-drilldown-stat">
				<div class="dds-value">${page}</div>
				<div class="dds-label">Current Page</div>
			</div>
			<div class="sad-drilldown-stat">
				<div class="dds-value">${total_pages}</div>
				<div class="dds-label">Total Pages</div>
			</div>
		</div>`;

		// Determine row-navigation doctype + id field
		const { module, dimension } = this._drilldown_state;
		const listRoute = this._drilldown_list_route;
		const row_doctype = listRoute ? listRoute.dt : null;
		const special_id = { 'programs_list': 'program_id', 'cohorts_list': 'cohort_id' };
		const id_field = special_id[dimension] || 'name';

		// Table
		const col_labels = cols.map(c => `<th>${c.replace(/_/g,' ').replace(/\b\w/g, s => s.toUpperCase())}</th>`).join('');
		const row_html = rows.map(row => {
			const record_id = row[id_field];
			const is_link = row_doctype && record_id;
			const tr_attrs = is_link
				? `class="sad-row-link" data-dt="${frappe.utils.escape_html(row_doctype)}" data-id="${frappe.utils.escape_html(String(record_id))}"`
				: '';
			const cells = cols.map(c => {
				const val = row[c];
				if (val == null || val === '') return '<td>—</td>';
				if (typeof val === 'number' && c.includes('amount') || c.includes('fee')) return `<td>${fmt_currency(val)}</td>`;
				if (typeof val === 'number') return `<td>${fmt_number(val)}</td>`;
				return `<td>${frappe.utils.escape_html(String(val))}</td>`;
			}).join('');
			return `<tr ${tr_attrs}>${cells}</tr>`;
		}).join('');

		const table_html = `
		<div class="sad-table-wrap">
			<table class="sad-table">
				<thead><tr>${col_labels}</tr></thead>
				<tbody>${row_html}</tbody>
			</table>
		</div>`;

		// Pagination
		const prev_disabled = page <= 1 ? 'disabled' : '';
		const next_disabled = page >= total_pages ? 'disabled' : '';
		const size_options = [10, 25, 50, 100].map(n =>
			`<option value="${n}" ${n === page_size ? 'selected' : ''}>${n}</option>`
		).join('');
		const page_html = `
		<div class="sad-pagination">
			<span>Showing ${(page - 1) * page_size + 1}–${Math.min(page * page_size, total)} of ${total} records</span>
			<div class="sad-page-size-wrap">
				Rows per page:
				<select class="sad-page-size-select" id="sad-dd-page-size">${size_options}</select>
			</div>
			<div class="sad-page-btns">
				<button class="sad-page-btn" id="sad-dd-prev" ${prev_disabled}>← Prev</button>
				<button class="sad-page-btn" id="sad-dd-next" ${next_disabled}>Next →</button>
			</div>
		</div>`;

		$('#sad-dd-body').html(stat_html + table_html + page_html);

		// Pagination events
		$('#sad-dd-prev').on('click', () => this._load_drilldown_page(page - 1));
		$('#sad-dd-next').on('click', () => this._load_drilldown_page(page + 1));
		$('#sad-dd-page-size').on('change', (e) => {
			this._drilldown_state.page_size = parseInt(e.target.value);
			this._load_drilldown_page(1);
		});

		// Row → form navigation
		$('#sad-dd-body').on('click', 'tr.sad-row-link', function () {
			const dt = $(this).data('dt');
			const id = $(this).data('id');
			if (dt && id) frappe.set_route('Form', dt, id);
		});

		// Re-apply any active search after render
		const q = $('#sad-dd-search').val().toLowerCase().trim();
		if (q) {
			let visible = 0;
			const $rows = $('.sad-table tbody tr');
			$rows.each(function () {
				const match = $(this).text().toLowerCase().includes(q);
				$(this).toggle(match);
				if (match) visible++;
			});
			$('#sad-dd-search-count').text(`${visible} / ${$rows.length} shown`);
		}
	}

	// ── Tab: Ticketing ───────────────────────────────────────────────────────

	_load_ticketing() {
		this._show_loading(4);
		frappe.call({
			method: `${PAGE_METHOD}.get_ticketing_analytics`,
			args: {},
			callback: (r) => {
				if (r.exc || !r.message) { this._show_error(); return; }
				const d = r.message;

				$('#sad-tab-content').html(`
					<div class="sad-kpi-grid">
						${this._kpi('Total Tickets',      d.total_tickets,    '🎫', 'primary', 'all support tickets',                 { module:'ticketing', dimension:'ticket_status',   value:'all' })}
						${this._kpi('Open / In Progress', d.open_tickets,     '📬', 'warning', 'awaiting resolution',                 { module:'ticketing', dimension:'ticket_status',   value:'Open' })}
						${this._kpi('Resolved',           d.resolved_tickets, '✅', 'success', `${d.resolved_pct}% resolution rate`,  { module:'ticketing', dimension:'ticket_status',   value:'Resolved' })}
						${this._kpi('Closed',             d.closed_tickets,   '🔒', 'info',    'fully closed tickets',                { module:'ticketing', dimension:'ticket_status',   value:'Closed' })}
						${this._kpi('High / Urgent',      d.high_priority,    '🔴', 'danger',  'critical priority tickets',           { module:'ticketing', dimension:'ticket_priority', value:'High' })}
						${this._kpi('SLA Breached',        d.sla_breached,     '⚠️', 'danger',  `${d.sla_pct}% SLA compliance`,        { module:'ticketing', dimension:'ticket_status',   value:'all' })}
					</div>

					<div class="sad-section-title">Response & Resolution Performance</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-tk-response',   'Avg First Response Time', 'Hours to first reply', '', '')}
						${this._chart_card('sad-tk-resolution', 'Avg Resolution Time',     'Hours to resolve',     '', '')}
						${this._chart_card('sad-tk-sla',        'SLA Compliance',          'Met / Failed / Overdue', 'Click to explore', '')}
					</div>

					<div class="sad-section-title">Ticket Distribution</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-tk-status',   'Status Breakdown',  'Open / Replied / Resolved / Closed', 'Click to explore', '')}
						${this._chart_card('sad-tk-priority', 'Priority Levels',   'Urgent / High / Medium / Low',       'Click to explore', '')}
						${this._chart_card('sad-tk-type',     'Ticket Types',      'Category-wise distribution',         'Click to explore', '')}
					</div>

					<div class="sad-section-title">Team & Trend</div>
					<div class="sad-chart-grid">
						${this._chart_card('sad-tk-team', 'Tickets by Team', 'Agent group distribution', 'Click bar to drill down', '')}
						<div class="sad-chart-wide">
							${this._chart_card('sad-tk-trend', 'Monthly Ticket Trend', 'Last 6 months', '', '')}
						</div>
					</div>
				`);

				// Performance stat cards — render value directly into chart body
				const stat_body = (value, unit, color, sub) => `
					<div style="text-align:center;padding:28px 0 16px;">
						<div style="font-size:48px;font-weight:800;color:${color};line-height:1;">
							${value != null && value !== 0 ? value : '—'}
							<span style="font-size:16px;font-weight:500;color:var(--sad-text3);margin-left:4px;">${value != null && value !== 0 ? unit : ''}</span>
						</div>
						<div style="font-size:13px;color:var(--sad-text3);margin-top:8px;">${sub}</div>
					</div>`;
				$('#sad-tk-response .sad-chart-body').html(
					stat_body(d.avg_first_response_hrs, 'hrs', 'var(--sad-primary)', 'across all resolved tickets'));
				$('#sad-tk-resolution .sad-chart-body').html(
					stat_body(d.avg_resolution_hrs, 'hrs', 'var(--sad-success)', 'from open to resolved'));

				this._render_donut('#sad-tk-sla .sad-chart-body',      d.sla_dist,      'ticketing', 'ticket_status');
				this._render_donut('#sad-tk-status .sad-chart-body',   d.status_dist,   'ticketing', 'ticket_status');
				this._render_donut('#sad-tk-priority .sad-chart-body', d.priority_dist, 'ticketing', 'ticket_priority');
				this._render_donut('#sad-tk-type .sad-chart-body',     d.type_dist,     'ticketing', 'ticket_type');
				this._render_bar_horizontal('#sad-tk-team .sad-chart-body',  d.team_dist,     { module: 'ticketing', dimension: 'agent_group' });
				this._render_bar_horizontal('#sad-tk-trend .sad-chart-body', d.monthly_trend, {});
			},
		});
	}

	_close_drilldown() {
		$('#sad-dd-overlay, #sad-dd-panel').removeClass('open');
		this._drilldown_open = false;
	}

	_export_drilldown() {
		if (!this._drilldown_state) return;
		const { module, dimension, value } = this._drilldown_state;
		// Trigger CSV export by fetching all data
		frappe.call({
			method: `${PAGE_METHOD}.get_drilldown_data`,
			args: { module, dimension, value, page: 1, page_size: 10000, ...this.filters },
			callback: (r) => {
				if (r.exc || !r.message || !r.message.rows.length) {
					frappe.show_alert({ message: 'No data to export', indicator: 'orange' });
					return;
				}
				const { rows, columns } = r.message;
				const csv_rows = [
					columns.join(','),
					...rows.map(row => columns.map(c => `"${row[c] || ''}"`).join(',')),
				];
				const blob = new Blob([csv_rows.join('\n')], { type: 'text/csv' });
				const url  = URL.createObjectURL(blob);
				const a    = document.createElement('a');
				a.href = url;
				a.download = `slcm_${module}_${dimension}_${value}.csv`;
				a.click();
				URL.revokeObjectURL(url);
			},
		});
	}
}
