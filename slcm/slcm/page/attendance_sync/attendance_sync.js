// Copyright (c) 2026, Nishanth and contributors
// Attendance Sync — reconciliation queue for RFID taps that could not be
// auto-matched to a Student Attendance record (missing device/room mapping,
// faculty never activated RFID, unregistered card, etc.)

const AUTO_REFRESH_MS = 30000;
const AUTO_REFRESH_STORAGE_KEY = "attendance_sync_auto_refresh";

const STATUS_LABELS = {
	"Early Tap - Awaiting Activation": "Awaiting RFID Activation",
	"Unmatched - No Session": "No Session Found",
	"Unmatched - No Device Mapping": "Device/Venue Not Mapped",
	"Unmatched - Unknown Card": "No Active Lesson",
	"Pending": "Pending",
	"Matched": "Matched",
	"Manually Synced": "Manually Synced",
};

// Text tones for status/reason — .as-badge.tone-* classes
const STATUS_COLORS = {
	"Early Tap - Awaiting Activation": "amber",
	"Unmatched - No Session": "orange",
	"Unmatched - No Device Mapping": "red",
	"Unmatched - Unknown Card": "maroon",
	"Pending": "grey",
	"Matched": "green",
	"Manually Synced": "blue",
};

// sync_method — how a log was resolved into Student Attendance (Status column/filter)
const SYNC_METHOD_COLORS = {
	"Biometric": "green",
	"Class Attendance": "blue",
	"Bulk Sync": "purple",
};

// KPI tiles — clicking one filters the table by that match_status
const STAT_TILES = [
	{ id: "as-total", label: "Needs Review", status: "" },
	{ id: "as-awaiting-activation", label: "Awaiting Activation", status: "Early Tap - Awaiting Activation" },
	{ id: "as-no-session", label: "No Session Found", status: "Unmatched - No Session" },
	{ id: "as-no-device", label: "Device Not Mapped", status: "Unmatched - No Device Mapping" },
	{ id: "as-unknown", label: "No Active Lesson", status: "Unmatched - Unknown Card" },
];

// Status/reason shown as plain coloured text (no pill)
function badge(text, tone) {
	return `<span class="as-badge tone-${tone || "grey"}">${frappe.utils.escape_html(text)}</span>`;
}

const DASH = '<span class="as-dash">—</span>';

frappe.pages["attendance-sync"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Attendance Sync",
		single_column: true,
	});

	page.set_primary_action("Refresh", () => load(wrapper), "fa fa-refresh");
	page.add_inner_button("Bulk Sync", () => open_bulk_sync_dialog(wrapper));

	page.add_field({
		fieldtype: "Select",
		fieldname: "sync_status_filter",
		label: "Status",
		options: ["", "Biometric", "Class Attendance", "Bulk Sync"].join("\n"),
		change() {
			load(wrapper);
		},
	});

	page.add_field({
		fieldtype: "Select",
		fieldname: "status_filter",
		label: "Reason",
		options: [
			"",
			"Early Tap - Awaiting Activation",
			"Unmatched - No Session",
			"Unmatched - No Device Mapping",
			"Unmatched - Unknown Card",
		].join("\n"),
		change() {
			load(wrapper);
		},
	});

	page.add_field({
		fieldtype: "Datetime",
		fieldname: "swipe_from_filter",
		label: "Swipe Time From",
		change() {
			load(wrapper);
		},
	});

	page.add_field({
		fieldtype: "Datetime",
		fieldname: "swipe_to_filter",
		label: "Swipe Time To",
		change() {
			load(wrapper);
		},
	});

	page.add_field({
		fieldtype: "Link",
		fieldname: "programme_filter",
		label: "Programme",
		options: "Programme",
		change() {
			page.fields_dict.academic_year_filter.set_value("");
			page.fields_dict.academic_term_filter.set_value("");
			page.fields_dict.batch_filter.set_value("");
			page.fields_dict.section_filter.set_value("");
			load(wrapper);
		},
	});

	page.add_field({
		fieldtype: "Link",
		fieldname: "academic_year_filter",
		label: "Academic Year",
		options: "Academic Year",
		get_query() {
			return {
				query: "slcm.slcm.doctype.attendance_log.process_attendance_logs.academic_year_link_query",
				filters: { programme: page.fields_dict.programme_filter.get_value() },
			};
		},
		change() {
			page.fields_dict.academic_term_filter.set_value("");
			page.fields_dict.batch_filter.set_value("");
			page.fields_dict.section_filter.set_value("");
			load(wrapper);
		},
	});

	page.add_field({
		fieldtype: "Link",
		fieldname: "academic_term_filter",
		label: "Academic Term",
		options: "Academic Term",
		get_query() {
			return {
				query: "slcm.slcm.doctype.attendance_log.process_attendance_logs.academic_term_link_query",
				filters: {
					programme: page.fields_dict.programme_filter.get_value(),
					academic_year: page.fields_dict.academic_year_filter.get_value(),
				},
			};
		},
		change() {
			load(wrapper);
		},
	});

	page.add_field({
		fieldtype: "Link",
		fieldname: "batch_filter",
		label: "Batch",
		options: "SLCM Batch",
		get_query() {
			const filters = {};
			const programme = page.fields_dict.programme_filter.get_value();
			const academic_year = page.fields_dict.academic_year_filter.get_value();
			if (programme) filters.program = programme;
			if (academic_year) filters.academic_year = academic_year;
			return { filters };
		},
		change() {
			page.fields_dict.section_filter.set_value("");
			load(wrapper);
		},
	});

	page.add_field({
		fieldtype: "Link",
		fieldname: "section_filter",
		label: "Section",
		options: "Section",
		// Sections are global (not tied to a batch): no batch filter.
		change() {
			load(wrapper);
		},
	});

	const stored = localStorage.getItem(AUTO_REFRESH_STORAGE_KEY);
	wrapper._auto_refresh_on = stored === null ? true : stored === "1";

	wrapper._auto_refresh_btn = page.add_inner_button(
		auto_refresh_label(wrapper._auto_refresh_on),
		() => toggle_auto_refresh(wrapper)
	);

	wrapper._auto_refresh_btn.toggleClass("as-live", wrapper._auto_refresh_on);
	$(wrapper).addClass("as-wrapper");

	$(build_html()).appendTo($(wrapper).find(".page-content, .layout-main-section").first());
	$(wrapper).find(".as-stats").on("click", ".as-stat", function () {
		const status = $(this).data("status") || "";
		const field = page.fields_dict.status_filter;
		field.set_value(field.get_value() === status ? "" : status);
	});
	wrapper._page = page;
	load(wrapper);

	if (wrapper._auto_refresh_on) {
		start_auto_refresh(wrapper);
	}
};

frappe.pages["attendance-sync"].on_page_hide = function (wrapper) {
	stop_auto_refresh(wrapper);
};

function auto_refresh_label(on) {
	return on ? "Auto Refresh: On (30s)" : "Auto Refresh: Off";
}

function start_auto_refresh(wrapper) {
	stop_auto_refresh(wrapper);
	wrapper._sync_interval = setInterval(() => load(wrapper), AUTO_REFRESH_MS);
}

function stop_auto_refresh(wrapper) {
	if (wrapper._sync_interval) {
		clearInterval(wrapper._sync_interval);
		wrapper._sync_interval = null;
	}
}

function toggle_auto_refresh(wrapper) {
	wrapper._auto_refresh_on = !wrapper._auto_refresh_on;
	localStorage.setItem(AUTO_REFRESH_STORAGE_KEY, wrapper._auto_refresh_on ? "1" : "0");

	if (wrapper._auto_refresh_btn) {
		wrapper._auto_refresh_btn
			.text(auto_refresh_label(wrapper._auto_refresh_on))
			.toggleClass("as-live", wrapper._auto_refresh_on);
	}

	if (wrapper._auto_refresh_on) {
		load(wrapper);
		start_auto_refresh(wrapper);
	} else {
		stop_auto_refresh(wrapper);
	}
}

function build_html() {
	const tiles = STAT_TILES.map(
		(t) =>
			`<div class="as-stat" data-status="${t.status}" title="${t.status ? "Filter by this reason" : "Clear reason filter"}">` +
			`<div><div class="as-stat-value" id="${t.id}">-</div>` +
			`<div class="as-stat-label"${t.id === "as-total" ? ' id="as-total-label"' : ""}>${t.label}</div></div>` +
			`</div>`
	).join("");

	return `
		<div class="attendance-sync-page">
			<div class="as-stats">${tiles}</div>
			<div class="as-toolbar">
				<span id="as-shown-count"></span>
				<span class="as-updated" id="as-updated"></span>
			</div>
			<div id="as-table"></div>
		</div>
		<style>${STYLES}</style>
	`;
}

const STYLES = `
	@font-face { font-family: "Merriweather"; src: url("/assets/slcm/fonts/Merriweather-Regular.ttf") format("truetype"); font-weight: 400; font-style: normal; font-display: swap; }
	@font-face { font-family: "Merriweather"; src: url("/assets/slcm/fonts/Merriweather-Bold.ttf") format("truetype"); font-weight: 600 900; font-style: normal; font-display: swap; }
	@font-face { font-family: "Merriweather"; src: url("/assets/slcm/fonts/Merriweather-Italic.ttf") format("truetype"); font-weight: 400; font-style: italic; font-display: swap; }
	.as-wrapper, .as-wrapper .form-control, .as-wrapper .btn,
	.as-dialog, .as-dialog .form-control, .as-dialog .btn, .as-dialog .modal-title {
		font-family: "Merriweather", Georgia, serif;
	}
	.as-wrapper .as-mono, .as-dialog .as-mono { font-family: var(--font-family-monospace, monospace); }
	:root {
		--as-maroon: #920c24;
		--as-maroon-hover: #7a0a1e;
		--as-maroon-text: #920c24;
		--as-maroon-soft: rgba(146,12,36,0.06);
		--as-maroon-mid: rgba(146,12,36,0.14);
	}
	[data-theme="dark"] {
		--as-maroon: #a8203a;
		--as-maroon-hover: #bd2c48;
		--as-maroon-text: #f08da0;
		--as-maroon-soft: rgba(214,74,102,0.12);
		--as-maroon-mid: rgba(214,74,102,0.28);
	}

	/* Page chrome */
	.as-wrapper .page-head .btn-primary,
	.as-dialog .btn-primary { background: var(--as-maroon); border-color: var(--as-maroon); color: #fff; }
	.as-wrapper .page-head .btn-primary:hover,
	.as-dialog .btn-primary:hover { background: var(--as-maroon-hover); border-color: var(--as-maroon-hover); }
	.as-wrapper .page-head .btn-default:hover { color: var(--as-maroon-text); background: var(--as-maroon-soft); }
	.as-wrapper .page-title .title-text { color: var(--as-maroon-text); font-weight: 700; }
	.as-live::before { content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%;
		background: #22a06b; margin-right: 6px; vertical-align: middle; animation: as-pulse 2s infinite; }
	@keyframes as-pulse { 0% { box-shadow: 0 0 0 0 rgba(34,160,107,.55); } 70% { box-shadow: 0 0 0 6px rgba(34,160,107,0); } 100% { box-shadow: 0 0 0 0 rgba(34,160,107,0); } }

	.as-wrapper .page-form { background: var(--card-bg); border: 1px solid var(--border-color);
		border-radius: 10px; padding: 12px 8px 4px; margin: 0 0 16px; }
	.as-wrapper .page-form .form-control:focus { box-shadow: 0 0 0 2px var(--as-maroon-mid); }

	/* KPI tiles */
	.as-stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
	@media (max-width: 991px) { .as-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
	.as-stat { display: flex; align-items: center; gap: 12px; padding: 14px 16px; background: var(--card-bg);
		border: 1px solid var(--border-color); border-radius: 10px; cursor: pointer; transition: all .15s ease; }
	.as-stat:hover { background: var(--subtle-fg, var(--control-bg)); }
	.as-stat.active { background: var(--as-maroon-soft); }
	.as-stat.active .as-stat-value, .as-stat.active .as-stat-label { color: var(--as-maroon-text); }
	.as-stat-value { font-size: 1.5rem; font-weight: 700; line-height: 1.1; color: var(--heading-color, var(--text-color)); font-variant-numeric: tabular-nums; }
	.as-stat-value.is-zero { color: var(--text-muted); }
	.as-stat-label { font-size: .72rem; letter-spacing: .04em; color: var(--text-muted); text-transform: uppercase; font-weight: 600; margin-top: 2px; }

	.as-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 0 2px 8px; font-size: .85rem; color: var(--text-muted); }
	.as-toolbar #as-shown-count b { color: var(--as-maroon-text); }
	.as-updated { font-size: .78rem; }

	/* Table */
	.as-table-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }
	.as-table-scroll { overflow: auto; max-height: calc(100vh - 330px); min-height: 200px; }
	.as-table { width: 100%; margin: 0; border-collapse: separate; border-spacing: 0; font-size: .82rem; }
	.as-table thead th { position: sticky; top: 0; z-index: 1; background: var(--as-maroon); color: #fff; font-weight: 600;
		font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; padding: 10px 12px; white-space: nowrap; border: 0; }
	.as-table tbody td { padding: 9px 12px; border-top: 1px solid var(--border-color); vertical-align: middle; color: var(--text-color); }
	.as-table tbody tr { cursor: pointer; transition: background .1s; }
	.as-table tbody tr:nth-child(even) td { background: var(--subtle-fg, rgba(0,0,0,.015)); }
	.as-table tbody tr:hover td { background: var(--as-maroon-soft); }
	.as-table .as-primary { font-weight: 600; color: var(--text-color); }
	.as-table .as-sub { font-size: .74rem; color: var(--text-muted); margin-top: 1px; }
	.as-table .as-unknown { color: var(--text-muted); font-style: italic; white-space: nowrap; }
	.as-table .as-mono { font-family: var(--font-family-monospace, monospace); font-size: .78rem; background: var(--control-bg);
		padding: 2px 6px; border-radius: 4px; white-space: nowrap; }
	.as-table .as-nowrap { white-space: nowrap; }
	.as-table td.as-actions { white-space: nowrap; text-align: right; }
	.as-table .as-actions .btn { padding: 3px 10px; font-size: .75rem; border-radius: 6px; }
	.as-table .as-actions .btn + .btn { margin-left: 4px; }
	.as-table .as-actions .as-sync-btn { background: var(--as-maroon); border-color: var(--as-maroon); color: #fff; }
	.as-table .as-actions .as-sync-btn:hover { background: var(--as-maroon-hover); }
	.as-dash { color: var(--gray-400, #c0c6cc); }
	.as-empty { padding: 56px 20px; text-align: center; color: var(--text-muted); }
	.as-empty i { font-size: 34px; color: #22a06b; }

	.as-badge { white-space: nowrap; font-weight: 600; font-size: .8rem; }
	.as-badge.tone-grey { color: var(--text-muted); }
	.as-badge.tone-amber { color: #b45309; }
	.as-badge.tone-orange { color: #c2410c; }
	.as-badge.tone-red, .as-badge.tone-maroon { color: var(--as-maroon-text); }
	.as-badge.tone-green { color: #15803d; }
	.as-badge.tone-blue { color: #1d4ed8; }
	.as-badge.tone-purple { color: #6d28d9; }
	[data-theme="dark"] .as-badge.tone-amber { color: #fbbf24; }
	[data-theme="dark"] .as-badge.tone-orange { color: #fb923c; }
	[data-theme="dark"] .as-badge.tone-green { color: #4ade80; }
	[data-theme="dark"] .as-badge.tone-blue { color: #60a5fa; }
	[data-theme="dark"] .as-badge.tone-purple { color: #c4b5fd; }

	/* Dialogs */
	.as-dialog .modal-content { border-radius: 12px; overflow: hidden; border: 0; }
	.as-dialog .modal-header { padding: 14px 20px; }
	.as-dialog .modal-title { color: var(--as-maroon-text); font-weight: 700; }
	.as-dialog .modal-footer { background: var(--subtle-fg, var(--control-bg)); }
	.as-dialog .form-section .section-head { color: var(--as-maroon-text); font-size: .78rem; text-transform: uppercase;
		letter-spacing: .05em; font-weight: 700; }
	.as-dialog .form-control:focus { box-shadow: 0 0 0 2px var(--as-maroon-mid); }

	.as-callout { display: flex; gap: 12px; padding: 12px 14px; border-radius: 10px; background: var(--as-maroon-soft); margin-bottom: 4px; }
	.as-callout > i { color: var(--as-maroon-text); font-size: 18px; margin-top: 2px; }
	.as-callout-title { font-weight: 600; color: var(--text-color); margin-bottom: 4px; }
	.as-callout ul { margin: 0; padding-left: 16px; font-size: .8rem; color: var(--text-muted); }
	.as-callout li { margin: 2px 0; }
	.as-callout li.skip { list-style: none; margin-left: -16px; margin-top: 6px; }

	.as-presets { display: flex; flex-wrap: wrap; gap: 6px; }
	.as-chip { border: 1px solid var(--border-color); background: var(--card-bg); color: var(--text-color); border-radius: 999px;
		padding: 3px 12px; font-size: .78rem; cursor: pointer; transition: all .12s; }
	.as-chip:hover { border-color: var(--as-maroon); color: var(--as-maroon-text); }
	.as-chip.active { background: var(--as-maroon); border-color: var(--as-maroon); color: #fff; }
	.as-scope { padding: 10px 12px; border-radius: 8px; background: var(--control-bg); font-size: .8rem; color: var(--text-muted); }
	.as-scope b { color: var(--text-color); }

	.as-hero { display: flex; align-items: center; gap: 14px; padding: 4px 0 14px; border-bottom: 1px solid var(--border-color); margin-bottom: 14px; }
	.as-avatar { width: 46px; height: 46px; flex: none; border-radius: 50%; background: var(--as-maroon); color: #fff;
		display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 700; }
	.as-hero-name { font-size: 1rem; font-weight: 700; color: var(--text-color); }
	.as-hero-sub { font-size: .8rem; color: var(--text-muted); }
	.as-hero .as-badge { margin-left: auto; }
	.as-section-title { font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; font-weight: 700;
		color: var(--as-maroon-text); margin: 4px 0 8px; }
	.as-kv { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 16px; margin-bottom: 16px; }
	.as-kv-item { padding: 8px 10px; border-radius: 8px; background: var(--control-bg); }
	.as-kv-item.wide { grid-column: 1 / -1; }
	.as-kv-label { font-size: .7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .03em; }
	.as-kv-value { font-weight: 600; color: var(--text-color); margin-top: 2px; word-break: break-word; }

	.as-timeline { position: relative; padding-left: 20px; }
	.as-timeline::before { content: ""; position: absolute; left: 6px; top: 4px; bottom: 4px; width: 2px; background: var(--border-color); }
	.as-tl-item { position: relative; padding-bottom: 12px; }
	.as-tl-item::before { content: ""; position: absolute; left: -18px; top: 4px; width: 10px; height: 10px; border-radius: 50%;
		background: var(--card-bg); border: 2px solid var(--as-maroon); }
	.as-tl-item:last-child::before { background: var(--as-maroon); }
	.as-tl-status { font-weight: 600; color: var(--text-color); font-size: .85rem; }
	.as-tl-ts { font-size: .75rem; color: var(--text-muted); }

	.as-result-tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }
	.as-result-tile { padding: 14px; border-radius: 10px; text-align: center; background: var(--control-bg); }
	.as-result-tile .v { font-size: 1.6rem; font-weight: 700; font-variant-numeric: tabular-nums; }
	.as-result-tile .l { font-size: .72rem; text-transform: uppercase; color: var(--text-muted); font-weight: 600; letter-spacing: .04em; }
	.as-result-tile.ok .v { color: #15803d; }
	.as-result-tile.skip .v { color: var(--as-maroon-text); }
	.as-mini-table { width: 100%; font-size: .8rem; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; border-collapse: separate; border-spacing: 0; }
	.as-mini-table th { background: var(--as-maroon-soft); color: var(--as-maroon-text); padding: 7px 10px; font-weight: 600; position: sticky; top: 0; }
	.as-mini-table td { padding: 7px 10px; border-top: 1px solid var(--border-color); }
	.as-scroll-box { max-height: 280px; overflow: auto; border-radius: 8px; }
`;

function fmt_dt(value) {
	return value ? frappe.datetime.str_to_user(value) || value : "";
}

// "07-23-2026 12:36:08" → time on top, date underneath
function stacked_dt(value) {
	const s = fmt_dt(value);
	if (!s) return DASH;
	const [date, time] = s.split(" ");
	return time
		? `<div class="as-primary as-nowrap">${time}</div><div class="as-sub as-nowrap">${date}</div>`
		: `<span class="as-nowrap">${s}</span>`;
}

function esc_or_dash(value) {
	return value ? frappe.utils.escape_html(value) : DASH;
}

function load(wrapper) {
	const fields = wrapper._page.fields_dict;
	frappe.call({
		method: "slcm.slcm.doctype.attendance_log.process_attendance_logs.get_unmatched_logs",
		args: {
			match_status: fields.status_filter.get_value() || null,
			status_filter: fields.sync_status_filter.get_value() || null,
			from_date: fields.swipe_from_filter.get_value() || null,
			to_date: fields.swipe_to_filter.get_value() || null,
			programme: fields.programme_filter.get_value() || null,
			academic_year: fields.academic_year_filter.get_value() || null,
			academic_term: fields.academic_term_filter.get_value() || null,
			batch: fields.batch_filter.get_value() || null,
			section: fields.section_filter.get_value() || null,
		},
		callback(r) {
			if (!r.message) return;
			render(wrapper, r.message);
		},
	});
}

function render(wrapper, logs) {
	const $w = $(wrapper);
	const sync_status = wrapper._page.fields_dict.sync_status_filter.get_value();
	const reason = wrapper._page.fields_dict.status_filter.get_value() || "";

	const counts = {
		"Early Tap - Awaiting Activation": 0,
		"Unmatched - No Session": 0,
		"Unmatched - No Device Mapping": 0,
		"Unmatched - Unknown Card": 0,
	};
	logs.forEach((l) => {
		if (counts[l.match_status] !== undefined) counts[l.match_status] += 1;
	});

	const set_stat = (id, n) => $w.find(`#${id}`).text(n).toggleClass("is-zero", !n);
	set_stat("as-total", logs.length);
	$w.find("#as-total-label").text(sync_status ? `${sync_status} Synced` : "Needs Review");
	set_stat("as-awaiting-activation", counts["Early Tap - Awaiting Activation"]);
	set_stat("as-no-session", counts["Unmatched - No Session"]);
	set_stat("as-no-device", counts["Unmatched - No Device Mapping"]);
	set_stat("as-unknown", counts["Unmatched - Unknown Card"]);
	$w.find(".as-stat").each(function () {
		$(this).toggleClass("active", ($(this).data("status") || "") === reason);
	});

	$w.find("#as-shown-count").html(
		logs.length ? `Showing <b>${logs.length}</b> ${sync_status ? sync_status + " synced" : "unresolved"} tap(s)` : ""
	);
	$w.find("#as-updated").html(
		`<i class="fa fa-refresh"></i> Updated ${frappe.datetime.now_time().slice(0, 5)}`
	);

	wrapper._logs = logs;
	build_table(wrapper, logs);
}

function build_table(wrapper, logs) {
	const $container = $(wrapper).find("#as-table");
	$container.empty();

	if (!logs.length) {
		$container.html(
			'<div class="as-table-card"><div class="as-empty">' +
				'<i class="fa fa-check-circle"></i>' +
				"<p style='margin:10px 0 0;font-weight:600;'>All clear</p>" +
				"<p style='margin:2px 0 0;font-size:.85rem;'>No taps match the current filters.</p></div></div>"
		);
		return;
	}

	const $table = $(
		'<table class="as-table">' +
			"<thead><tr>" +
			"<th>Student</th><th>Card / RFID UID</th><th>Punch Time</th>" +
			"<th>Device / Reader</th><th>Class / Course</th><th>Lesson Time</th>" +
			"<th>RFID Activated By</th><th>Activation Time</th>" +
			"<th>Programme / Batch / Section</th>" +
			"<th>Status</th>" +
			"<th>Reason</th><th style='text-align:right;'>Action</th>" +
			"</tr></thead><tbody></tbody></table>"
	);
	const $tbody = $table.find("tbody");

	logs.forEach((log) => {
		const lesson_candidates = log.candidate_sessions || [];
		const first_session = lesson_candidates[0];

		const student_html = log.student
			? `<div class="as-primary">${frappe.utils.escape_html(log.student_name || log.student)}</div>` +
			  `<div class="as-sub">${frappe.utils.escape_html(log.student)}</div>`
			: '<span class="as-unknown"><i class="fa fa-question-circle-o"></i> Unknown Card</span>';

		const device_html = log.terminal_alias
			? `<div class="as-primary as-nowrap">${frappe.utils.escape_html(log.terminal_alias)}</div>` +
			  `<div class="as-sub">Device ${frappe.utils.escape_html(log.device_id || "-")}</div>`
			: esc_or_dash(log.device_id);

		const class_html = first_session
			? `<div class="as-primary">${esc_or_dash(first_session.class_name)}</div>` +
			  (first_session.course_code ? `<div class="as-sub">${frappe.utils.escape_html(first_session.course_code)}</div>` : "")
			: log.resolved_rooms && log.resolved_rooms.length
			? `<div>Room ${frappe.utils.escape_html(log.resolved_rooms.join(", "))}</div><div class="as-sub">No session that day</div>`
			: DASH;

		const lesson_time = first_session
			? `<span class="as-nowrap">${fmt_dt(first_session.session_start_time)} – ${first_session.session_end_time || ""}</span>`
			: DASH;

		const activated_by = first_session ? esc_or_dash(first_session.rfid_activated_by) : DASH;
		const activation_time = first_session && first_session.rfid_activation_time
			? stacked_dt(first_session.rfid_activation_time)
			: DASH;

		const enrollment_html = log.programme
			? `<div class="as-primary">${frappe.utils.escape_html(log.programme)}</div>` +
			  `<div class="as-sub">${frappe.utils.escape_html([log.batch, log.section].filter(Boolean).join(" · "))}</div>`
			: DASH;

		const sync_status_html = log.processed && log.sync_method
			? badge(log.sync_method, SYNC_METHOD_COLORS[log.sync_method]) +
			  (log.synced_by
					? `<div class="as-sub">by ${frappe.utils.escape_html(log.synced_by)}` +
					  (log.synced_on ? ` on ${fmt_dt(log.synced_on)}` : "") + "</div>"
					: "")
			: badge("Needs Review", "grey");

		const $row = $("<tr></tr>");
		$row.on("click", () => open_log_detail_dialog(log));
		$row.append(`<td>${student_html}</td>`);
		$row.append(`<td>${log.rfid_uid ? `<span class="as-mono">${frappe.utils.escape_html(log.rfid_uid)}</span>` : DASH}</td>`);
		$row.append(`<td>${stacked_dt(log.swipe_time)}</td>`);
		$row.append(`<td>${device_html}</td>`);
		$row.append(`<td>${class_html}</td>`);
		$row.append(`<td>${lesson_time}</td>`);
		$row.append(`<td>${activated_by}</td>`);
		$row.append(`<td>${activation_time}</td>`);
		$row.append(`<td>${enrollment_html}</td>`);
		$row.append(`<td>${sync_status_html}</td>`);
		$row.append(`<td>${badge(STATUS_LABELS[log.match_status] || log.match_status, STATUS_COLORS[log.match_status])}</td>`);

		const $actionTd = $('<td class="as-actions"></td>').on("click", (e) => e.stopPropagation());
		const $viewBtn = $('<button class="btn btn-xs btn-default"><i class="fa fa-eye"></i> View</button>');
		$viewBtn.on("click", () => open_log_detail_dialog(log));
		$actionTd.append($viewBtn);
		if (!log.processed) {
			const $syncBtn = $('<button class="btn btn-xs as-sync-btn"><i class="fa fa-link"></i> Sync</button>');
			$syncBtn.on("click", () => open_sync_dialog(wrapper, log));
			$actionTd.append($syncBtn);
		}
		$row.append($actionTd);

		$tbody.append($row);
	});

	$("<div class='as-table-card'><div class='as-table-scroll'></div></div>")
		.find(".as-table-scroll").append($table).end()
		.appendTo($container);
}

function _kv(label, value, wide) {
	return `<div class="as-kv-item${wide ? " wide" : ""}">` +
		`<div class="as-kv-label">${frappe.utils.escape_html(label)}</div>` +
		`<div class="as-kv-value">${value}</div></div>`;
}

function make_dialog(opts) {
	const d = new frappe.ui.Dialog(opts);
	d.$wrapper.addClass("as-dialog");
	return d;
}

function open_log_detail_dialog(log) {
	const first_session = (log.candidate_sessions || [])[0];
	const tone = STATUS_COLORS[log.match_status];
	const label = STATUS_LABELS[log.match_status] || log.match_status;
	const name = log.student ? log.student_name || log.student : "Unregistered Card";
	const initials = log.student
		? name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("")
		: "?";

	let body = "";
	body += `<div class="as-hero">` +
		`<div class="as-avatar">${frappe.utils.escape_html(initials)}</div>` +
		`<div><div class="as-hero-name">${frappe.utils.escape_html(name)}</div>` +
		`<div class="as-hero-sub">${frappe.utils.escape_html(
			[log.student, log.student_email].filter(Boolean).join(" · ") || "Card " + (log.rfid_uid || "-")
		)}</div></div>` +
		badge(label, tone) +
		`</div>`;

	body += `<div class="as-section-title">Punch</div><div class="as-kv">`;
	body += _kv("Punch Id", frappe.utils.escape_html(log.name));
	body += _kv("Punch Timestamp", fmt_dt(log.swipe_time) || "-");
	body += _kv("Card / RFID UID", log.rfid_uid ? `<span class="as-mono">${frappe.utils.escape_html(log.rfid_uid)}</span>` : "-");
	body += _kv("Device / Reader", frappe.utils.escape_html(log.device_id || "-") +
		(log.terminal_alias ? " / " + frappe.utils.escape_html(log.terminal_alias) : ""));
	body += `</div>`;

	const class_name_display = first_session
		? frappe.utils.escape_html(first_session.class_name || "-") +
		  (first_session.course_code ? ` [${frappe.utils.escape_html(first_session.course_code)}]` : "")
		: "-";

	body += `<div class="as-section-title">Lesson</div><div class="as-kv">`;
	body += _kv("Class Name [Course Code]", class_name_display, true);
	body += _kv("Lesson Id", first_session ? frappe.utils.escape_html(first_session.name) : "-");
	body += _kv("System Activated", first_session && first_session.rfid_activation_time
		? badge("Yes", "green") : badge("No", "grey"));
	body += _kv("Lesson Start", first_session ? fmt_dt(first_session.session_start_time) || "-" : "-");
	body += _kv("Lesson End", first_session ? fmt_dt(first_session.session_end_time) || "-" : "-");
	body += _kv("Activation Time", first_session && first_session.rfid_activation_time
		? fmt_dt(first_session.rfid_activation_time) : "-");
	body += _kv("RFID Activated By", first_session && first_session.rfid_activated_by
		? frappe.utils.escape_html(first_session.rfid_activated_by) : "-");
	if (!first_session && log.resolved_rooms && log.resolved_rooms.length) {
		body += _kv("Resolved Room(s)", frappe.utils.escape_html(log.resolved_rooms.join(", ")) +
			' <span class="as-hero-sub">— no Attendance Session found for this date</span>', true);
	}
	body += `</div>`;

	const history = [{ ts: log.creation, status: "Log received" }];
	if (log.synced_on) {
		history.push({ ts: log.synced_on, status: `Manually synced by ${log.synced_by || "-"}` });
	} else if (log.processed) {
		history.push({ ts: log.modified, status: "Matched to Student Attendance" });
	} else {
		history.push({ ts: log.modified, status: label });
	}

	body += `<div class="as-section-title">Processing History</div><div class="as-timeline">`;
	history.forEach((h) => {
		body += `<div class="as-tl-item"><div class="as-tl-status">${frappe.utils.escape_html(h.status)}</div>` +
			`<div class="as-tl-ts">${fmt_dt(h.ts) || "-"}</div></div>`;
	});
	body += `</div>`;

	const d = make_dialog({
		title: `Log Details — ${log.name}`,
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "detail_html", options: body }],
	});
	d.show();
}

const BULK_PRESETS = [
	{ key: "today", label: "Today", range: (t) => [t, t] },
	{ key: "yesterday", label: "Yesterday", range: (t) => [frappe.datetime.add_days(t, -1), frappe.datetime.add_days(t, -1)] },
	{ key: "7d", label: "Last 7 days", range: (t) => [frappe.datetime.add_days(t, -7), t] },
	{ key: "month", label: "This month", range: (t) => [frappe.datetime.month_start(), t] },
];

function open_bulk_sync_dialog(wrapper) {
	const today = frappe.datetime.get_today();
	let d = null;

	d = make_dialog({
		title: "Bulk Sync Attendance Logs",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "bulk_sync_note",
				options:
					'<div class="as-callout"><i class="fa fa-magic"></i><div>' +
					'<div class="as-callout-title">Auto-sync unresolved taps that are safe to match</div>' +
					"<ul>" +
					"<li>The student is known (card is registered)</li>" +
					"<li>The reader/device maps to exactly one room</li>" +
					"<li>The tap falls within the class's RFID window — the first N minutes after " +
					"session start (Attendance Settings), whether or not faculty pressed Activate RFID</li>" +
					'<li class="skip"><i class="fa fa-info-circle"></i> Ambiguous, unregistered, or after-class ' +
					"taps are skipped for individual review.</li>" +
					"</ul></div></div>",
			},
			{ fieldtype: "Section Break", label: "Date Range" },
			{
				fieldtype: "HTML",
				fieldname: "presets",
				options:
					'<div class="as-presets">' +
					BULK_PRESETS.map((p) => `<button type="button" class="as-chip" data-key="${p.key}">${p.label}</button>`).join("") +
					"</div>",
			},
			{ fieldtype: "Section Break", hide_border: 1 },
			{
				fieldtype: "Date",
				fieldname: "from_date",
				label: "From Date",
				reqd: 1,
				default: frappe.datetime.add_days(today, -7),
				onchange: () => update_scope(),
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Date",
				fieldname: "to_date",
				label: "To Date",
				reqd: 1,
				default: today,
				onchange: () => update_scope(),
			},
			{ fieldtype: "Section Break", label: "Narrow Down (Optional)", collapsible: 0 },
			{
				fieldtype: "Time",
				fieldname: "from_time",
				label: "From Time",
				onchange: () => update_scope(),
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Time",
				fieldname: "to_time",
				label: "To Time",
				onchange: () => update_scope(),
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Link",
				fieldname: "venue",
				label: "Venue",
				options: "Room",
				onchange: () => update_scope(),
			},
			{ fieldtype: "Section Break", hide_border: 1 },
			{ fieldtype: "HTML", fieldname: "scope" },
		],
		primary_action_label: __("Run Bulk Sync"),
		primary_action(values) {
			if (values.to_date < values.from_date) {
				frappe.msgprint(__("To Date cannot be before From Date."));
				return;
			}
			frappe.call({
				method: "slcm.slcm.doctype.attendance_log.process_attendance_logs.bulk_sync_attendance_logs",
				args: {
					from_date: values.from_date,
					to_date: values.to_date,
					from_time: values.from_time || null,
					to_time: values.to_time || null,
					venue: values.venue || null,
				},
				freeze: true,
				freeze_message: __("Running Bulk Sync..."),
				callback(r) {
					if (!r.message) return;
					d.hide();
					show_bulk_sync_result(wrapper, r.message);
					load(wrapper);
				},
			});
		},
	});

	function update_scope() {
		if (!d) return;
		const v = d.get_values(true) || {};
		const $chips = d.fields_dict.presets.$wrapper.find(".as-chip");
		$chips.removeClass("active");
		BULK_PRESETS.forEach((p) => {
			const [from, to] = p.range(today);
			if (v.from_date === from && v.to_date === to) $chips.filter(`[data-key="${p.key}"]`).addClass("active");
		});

		if (!v.from_date || !v.to_date) {
			d.fields_dict.scope.$wrapper.html("");
			return;
		}
		const dates = v.from_date === v.to_date
			? `<b>${frappe.datetime.str_to_user(v.from_date)}</b>`
			: `<b>${frappe.datetime.str_to_user(v.from_date)}</b> to <b>${frappe.datetime.str_to_user(v.to_date)}</b>`;
		const times = v.from_time || v.to_time
			? `between <b>${(v.from_time || "00:00").slice(0, 5)}</b> and <b>${(v.to_time || "23:59").slice(0, 5)}</b>`
			: "<b>all day</b>";
		const venue = v.venue ? `at <b>${frappe.utils.escape_html(v.venue)}</b>` : "across <b>all venues</b>";
		const warn = v.to_date < v.from_date
			? ' <span style="color:var(--as-maroon-text);font-weight:600;">— To Date is before From Date</span>'
			: "";
		d.fields_dict.scope.$wrapper.html(
			`<div class="as-scope"><i class="fa fa-filter"></i> Will scan unresolved taps on ${dates}, ${times}, ${venue}.${warn}</div>`
		);
	}

	d.fields_dict.presets.$wrapper.on("click", ".as-chip", function () {
		const preset = BULK_PRESETS.find((p) => p.key === $(this).data("key"));
		const [from, to] = preset.range(today);
		d.set_values({ from_date: from, to_date: to }).then(update_scope);
	});

	d.show();
	update_scope();
}

function show_bulk_sync_result(wrapper, result) {
	let body = "";
	body += `<div class="as-scope" style="margin-bottom:12px;"><i class="fa fa-calendar"></i> ` +
		`<b>${frappe.datetime.str_to_user(result.from_date)}</b> to <b>${frappe.datetime.str_to_user(result.to_date)}</b></div>`;
	body += '<div class="as-result-tiles">' +
		`<div class="as-result-tile"><div class="v">${result.total}</div><div class="l">Considered</div></div>` +
		`<div class="as-result-tile ok"><div class="v">${result.synced_count}</div><div class="l">Synced</div></div>` +
		`<div class="as-result-tile skip"><div class="v">${result.skipped_count}</div><div class="l">Skipped</div></div>` +
		"</div>";

	if (result.skipped && result.skipped.length) {
		body += `<div class="as-section-title">Skipped — Needs Individual Review</div>`;
		body += '<div class="as-scroll-box"><table class="as-mini-table">' +
			"<thead><tr><th>Log</th><th>Reason</th></tr></thead><tbody>";
		result.skipped.forEach((s) => {
			body += `<tr><td class="as-nowrap">${frappe.utils.escape_html(s.log)}</td><td>${frappe.utils.escape_html(s.reason)}</td></tr>`;
		});
		body += "</tbody></table></div>";
	}

	const d = make_dialog({
		title: "Bulk Sync Result",
		fields: [{ fieldtype: "HTML", fieldname: "result_html", options: body }],
	});
	d.show();
}

function open_sync_dialog(wrapper, log) {
	const candidate_sessions = log.candidate_sessions || [];

	const summary =
		'<div class="as-scope" style="margin-bottom:6px;">' +
		`<div><i class="fa fa-id-card-o"></i> <b>${frappe.utils.escape_html(
			log.student ? `${log.student_name || ""} (${log.student})` : "Unregistered card"
		)}</b></div>` +
		`<div style="margin-top:4px;">Tapped <b>${fmt_dt(log.swipe_time) || "-"}</b> on ` +
		`<b>${frappe.utils.escape_html(log.terminal_alias || log.device_id || "-")}</b> &nbsp;` +
		badge(STATUS_LABELS[log.match_status] || log.match_status, STATUS_COLORS[log.match_status]) +
		"</div></div>";

	const fields = [
		{ fieldtype: "HTML", fieldname: "summary", options: summary },
		{
			fieldtype: "Data",
			fieldname: "rfid_uid",
			label: "RFID UID",
			default: log.rfid_uid,
			read_only: 1,
		},
	];

	if (!log.student) {
		fields.push({
			fieldtype: "Link",
			fieldname: "student",
			label: "Student (identify the card owner)",
			options: "Student Master",
			reqd: 1,
		});
	}

	fields.push({
		fieldtype: "Link",
		fieldname: "session",
		label: "Attendance Session",
		options: "Attendance Session",
		reqd: 1,
		default: candidate_sessions.length ? candidate_sessions[0].name : "",
		description: candidate_sessions.length
			? `${candidate_sessions.length} candidate session(s) resolved from the device's room mapping for this date. Override if incorrect.`
			: "No session could be auto-resolved — pick the correct one manually.",
	});

	const d = make_dialog({
		title: `Sync Attendance Log — ${log.name}`,
		fields,
		primary_action_label: "Sync",
		primary_action(values) {
			frappe.call({
				method: "slcm.slcm.doctype.attendance_log.process_attendance_logs.sync_attendance_log",
				args: {
					log_name: log.name,
					session_name: values.session,
					student: values.student || null,
				},
				freeze: true,
				freeze_message: __("Syncing..."),
				callback(r) {
					if (!r.message) return;
					frappe.show_alert({ message: __("Attendance synced successfully"), indicator: "green" });
					d.hide();
					load(wrapper);
				},
			});
		},
	});

	d.show();
}
