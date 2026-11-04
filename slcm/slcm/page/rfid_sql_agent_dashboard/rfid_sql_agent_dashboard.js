// Copyright (c) 2026, Nishanth and contributors
// RFID SQL Agent Dashboard — health of the SQL Server puller, today's swipes,
// terminals, setup gaps that stop swipes becoming attendance, and the live feed.

const AUTO_REFRESH_MS = 30000;
const AUTO_REFRESH_STORAGE_KEY = "rfid_sql_agent_dashboard_auto_refresh";

frappe.pages["rfid-sql-agent-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("RFID Dashboard"),
		single_column: true,
	});
	$(wrapper).addClass("er-theme");
	if (!document.getElementById("er-theme-font")) {
		$("head").append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	frappe.require("/assets/slcm/css/exam_results_theme.css");

	page.set_primary_action(__("Run Now"), () => run_now(wrapper), "refresh");
	page.add_menu_item(__("RFID Agent Settings"), () => frappe.set_route("Form", "RFID SQL Agent Settings"));
	page.add_menu_item(__("Attendance Dashboard"), () => frappe.set_route("attendance-dashboard"));
	page.add_menu_item(__("Error Log"), () => frappe.set_route("List", "Error Log", { method: ["like", "RFID SQL Agent%"] }));

	let stored = null;
	try { stored = localStorage.getItem(AUTO_REFRESH_STORAGE_KEY); } catch (e) { /* storage blocked */ }
	wrapper._auto_refresh_on = stored === null ? true : stored === "1";
	wrapper._auto_refresh_btn = page.add_inner_button(
		auto_refresh_label(wrapper._auto_refresh_on),
		() => toggle_auto_refresh(wrapper)
	);
	page.add_inner_button(__("Refresh"), () => load(wrapper));

	add_styles();
	$(build_html()).appendTo(page.main);
	$(wrapper).on("click", "[data-route]", (e) => {
		const r = $(e.currentTarget).data("route").split("/");
		frappe.set_route(...r);
	});
	$(wrapper).on("click", "[data-detail]", (e) => open_detail(wrapper, $(e.currentTarget).data("detail")));
	load(wrapper);
	if (wrapper._auto_refresh_on) start_auto_refresh(wrapper);
};

frappe.pages["rfid-sql-agent-dashboard"].on_page_show = function (wrapper) {
	if (wrapper._loaded) load(wrapper);
	if (wrapper._auto_refresh_on) start_auto_refresh(wrapper);
};

frappe.pages["rfid-sql-agent-dashboard"].on_page_hide = function (wrapper) {
	stop_auto_refresh(wrapper);
};

const rf_esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
const rf_num = (v) => format_number(v || 0, null, 0);

function auto_refresh_label(on) {
	return on ? __("Auto Refresh: On (30s)") : __("Auto Refresh: Off");
}

function start_auto_refresh(wrapper) {
	stop_auto_refresh(wrapper);
	wrapper._rfid_sql_agent_interval = setInterval(() => load(wrapper), AUTO_REFRESH_MS);
}

function stop_auto_refresh(wrapper) {
	if (wrapper._rfid_sql_agent_interval) {
		clearInterval(wrapper._rfid_sql_agent_interval);
		wrapper._rfid_sql_agent_interval = null;
	}
}

function toggle_auto_refresh(wrapper) {
	wrapper._auto_refresh_on = !wrapper._auto_refresh_on;
	try { localStorage.setItem(AUTO_REFRESH_STORAGE_KEY, wrapper._auto_refresh_on ? "1" : "0"); } catch (e) { /* storage blocked */ }
	if (wrapper._auto_refresh_btn) wrapper._auto_refresh_btn.text(auto_refresh_label(wrapper._auto_refresh_on));
	if (wrapper._auto_refresh_on) {
		load(wrapper);
		start_auto_refresh(wrapper);
	} else {
		stop_auto_refresh(wrapper);
	}
}

function build_html() {
	return `<div class="rf">
		<div class="rf-health" data-slot="health"></div>
		<div data-slot="setup"></div>
		<div class="rf-kpis" data-slot="kpis"></div>
		<div class="rf-two">
			<button class="rf-drill" data-detail="terminals">
				<span class="rf-drill-text"><h4>${__("Terminals today")}</h4><small class="rf-muted" data-slot="term-summary"></small></span>
				<span class="rf-drill-go">${__("View details")} →</span>
			</button>
			<button class="rf-drill" data-detail="outcomes">
				<span class="rf-drill-text"><h4>${__("What happened to today's swipes")}</h4><small class="rf-muted" data-slot="out-summary"></small></span>
				<span class="rf-drill-go">${__("View details")} →</span>
			</button>
		</div>
		<section class="rf-panel">
			<div class="rf-panel-head"><h4>${__("Live feed")}</h4><span class="rf-muted" data-slot="feed-count"></span></div>
			<div id="cp-datatable"></div>
		</section>
	</div>`;
}

// why a swipe did not become attendance, in plain words
const OUTCOME_TEXT = {
	"Matched": __("Marked present in a class"),
	"Manually Synced": __("Synced by hand"),
	"Pending": __("Waiting for the next matching run"),
	"Early Tap - Awaiting Activation": __("Swiped before the faculty opened RFID for the class"),
	"Unmatched - Unknown Card": __("Card number is not linked to any student"),
	"Unmatched - No Device Mapping": __("Terminal is not registered or not mapped to a room"),
	"Unmatched - No Session": __("No class in that room at that time"),
};

const DT_COLUMNS = [
	{ name: __("Card / Emp Code"), id: "emp_code", width: 150, editable: false, focusable: false },
	{ name: __("Student"), id: "student", width: 180, editable: false, focusable: false },
	{ name: __("Punch Time"), id: "punch_time", width: 170, editable: false, focusable: false },
	{ name: __("Terminal"), id: "terminal_id", width: 90, editable: false, focusable: false },
	{ name: __("Location"), id: "terminal_alias", width: 160, editable: false, focusable: false },
	{ name: __("Status"), id: "sync_status", width: 110, editable: false, focusable: false },
];

function rows_to_datatable_data(recent) {
	return (recent || []).map((row) => [
		row.emp_code || "",
		row.student ? row.student_name || row.student : __("Not linked"),
		frappe.datetime.str_to_user(row.punch_time) || "",
		row.terminal_id || "",
		row.terminal_alias || "",
		row.sync_status || "",
	]);
}

function format_interval(seconds) {
	seconds = seconds || 300;
	if (seconds % 60 === 0) {
		const mins = seconds / 60;
		return mins === 1 ? __("1 minute") : __("{0} minutes", [mins]);
	}
	return __("{0} seconds", [seconds]);
}

// "3 min ago", measured against the server clock so browser time zones don't matter
function ago(dt, now) {
	if (!dt) return __("never");
	const s = Math.max(0, moment(now).diff(moment(dt), "seconds"));
	if (s < 60) return __("{0} s ago", [s]);
	if (s < 3600) return __("{0} min ago", [Math.floor(s / 60)]);
	if (s < 86400) return __("{0} h ago", [Math.floor(s / 3600)]);
	return __("{0} days ago", [Math.floor(s / 86400)]);
}

function load(wrapper) {
	return frappe.call({
		method: "slcm.slcm.rfid_sql_agent.poller.get_dashboard_summary",
	}).then((r) => {
		if (!r.message) return;
		wrapper._loaded = true;
		render(wrapper, r.message);
	});
}

function slot(wrapper, name) {
	return $(wrapper).find(`[data-slot="${name}"]`);
}

function render(wrapper, d) {
	const s = d.stats || {};
	const polled_s = d.last_polled_at ? moment(d.server_now).diff(moment(d.last_polled_at), "seconds") : null;
	const stale = d.enabled && (polled_s === null || polled_s > d.poll_interval_seconds * 3 + 120);
	const state = !d.enabled ? ["off", __("Stopped")]
		: stale ? ["bad", __("Not polling")]
		: d.last_error && moment(d.server_now).diff(moment(d.last_error.creation), "seconds") < d.poll_interval_seconds * 3 + 120
			? ["warn", __("Connection problems")] : ["ok", __("Running")];

	slot(wrapper, "health").html(`
		<span class="rf-pill ${state[0]}"><i></i>${state[1]}</span>
		<div class="rf-health-text">
			${d.enabled
				? __("Pulling from <b>{0}</b> every {1}. Last poll {2}, last swipe {3}.",
					[rf_esc(d.source), format_interval(d.poll_interval_seconds), ago(d.last_polled_at, d.server_now), ago(s.last_punch, d.server_now)])
				: __("The agent is off. Turn on <b>Enable RFID SQL Agent</b> in RFID Agent Settings to start pulling swipes.")}
			${d.remote_push ? `<br>${__("Also forwarding each swipe to <b>{0}</b>", [rf_esc(d.remote_site_url)])}${s.remote_pending
				? ` · <span class="rf-warn-text">${__("{0} not forwarded yet", [rf_num(s.remote_pending)])}</span>` : ""}` : ""}
			${d.errors_24h ? `<br><button class="rf-link" data-route="List/Error Log">${__("{0} connection error(s) in the last 24 h", [d.errors_24h])}</button>
				<span class="rf-muted">· ${__("latest {0}", [ago(d.last_error.creation, d.server_now)])}</span>` : ""}
		</div>
		<span class="rf-muted rf-refreshed">${__("Refreshed {0}", [new Date().toLocaleTimeString()])}</span>`);

	const st = d.setup || {};
	const gaps = [];
	if (!st.students_with_card) gaps.push([__("No active student has an RFID card number yet ({0} of {1})", [st.students_with_card, st.active_students]), "rfid-mapping", __("Link cards")]);
	if (!st.devices) gaps.push([__("No terminal is registered as an RFID Device"), "List/RFID Device", __("Add devices")]);
	if (!st.mappings) gaps.push([__("No RFID Device is mapped to a room"), "List/RFID Device Room Mapping", __("Map rooms")]);
	slot(wrapper, "setup").html(gaps.length ? `<div class="rf-alert">
		<b>${__("Swipes are arriving, but they can't become attendance yet")}</b>
		<ul>${gaps.map((g) => `<li><span>${g[0]}</span><button class="rf-btn" data-route="${g[1]}">${g[2]}</button></li>`).join("")}</ul>
	</div>` : "");

	const pct = s.today ? Math.round((100 * (s.today_matched || 0)) / s.today) : 0;
	const kpis = [
		[__("Swipes today"), rf_num(s.today), __("{0} different cards", [rf_num(s.today_cards)]), "List/RFID SQL Punch Log"],
		[__("Linked to a student"), rf_num(s.today_matched), s.today ? __("{0}% of today", [pct]) : "", "List/RFID SQL Punch Log"],
		[__("Not linked"), rf_num((s.today || 0) - (s.today_matched || 0)), __("today, card unknown"), "attendance-sync"],
		[__("Terminals active"), rf_num((d.terminals || []).length), __("swiped today"), "List/RFID Device"],
		[__("All swipes"), rf_num(s.total_punches), __("{0} not linked", [rf_num(s.unmatched)]), "List/RFID SQL Punch Log"],
		[__("Last Log ID"), rf_esc(d.last_log_id || 0), __("source row reached"), "Form/RFID SQL Agent Settings"],
	];
	slot(wrapper, "kpis").html(kpis.map((k) => `<button class="rf-kpi" data-route="${k[3]}">
		<span>${k[0]}</span><b>${k[1]}</b><small>${k[2]}</small></button>`).join(""));

	const terms = d.terminals || [];
	const ready = terms.filter((t) => t.registered && t.mapped).length;
	slot(wrapper, "term-summary").text(terms.length
		? __("{0} terminals · {1} ready · {2} need setup", [terms.length, ready, terms.length - ready])
		: __("No swipes today."));
	wrapper._terminals_html = (terms.length ? `<table class="rf-table">
		<thead><tr><th>${__("Terminal")}</th><th>${__("Location")}</th><th class="num">${__("Swipes")}</th><th>${__("Last swipe")}</th><th>${__("Setup")}</th></tr></thead>
		<tbody>${terms.map((t) => `<tr>
			<td>${rf_esc(t.terminal_id)}</td><td>${rf_esc(t.terminal_alias)}</td><td class="num">${rf_num(t.swipes)}</td>
			<td>${rf_esc(ago(t.last_punch, d.server_now))}</td>
			<td>${!t.registered ? `<span class="rf-chip bad">${__("Not registered")}</span>`
				: !t.mapped ? `<span class="rf-chip warn">${__("No room")}</span>` : `<span class="rf-chip ok">${__("Ready")}</span>`}</td>
		</tr>`).join("")}</tbody></table>` : `<p class="rf-empty">${__("No swipes today.")}</p>`);

	const outs = d.outcomes || [];
	const total = outs.reduce((a, o) => a + o.n, 0);
	const marked = outs.filter((o) => ["Matched", "Manually Synced"].includes(o.status)).reduce((a, o) => a + o.n, 0);
	slot(wrapper, "out-summary").text(total
		? __("{0} swipes · {1} became attendance · {2} did not", [rf_num(total), rf_num(marked), rf_num(total - marked)])
		: __("No swipes today."));
	wrapper._outcomes_html = (outs.length ? outs.map((o) => `<div class="rf-out">
		<div class="rf-out-top"><b>${rf_esc(OUTCOME_TEXT[o.status] || o.status)}</b><span>${rf_num(o.n)}</span></div>
		<div class="rf-bar"><i class="${["Matched", "Manually Synced"].includes(o.status) ? "ok" : ""}" style="width:${Math.max(2, (100 * o.n) / total)}%"></i></div>
		<small class="rf-muted">${rf_esc(o.status)}</small>
	</div>`).join("") : `<p class="rf-empty">${__("No swipes today.")}</p>`);

	const data = rows_to_datatable_data(d.recent);
	slot(wrapper, "feed-count").text(data.length ? __("Latest {0} swipes · filter with the boxes under each heading", [data.length]) : "");
	if (!wrapper._rfid_dt) {
		wrapper._rfid_dt = new frappe.DataTable(wrapper.querySelector("#cp-datatable"), {
			columns: DT_COLUMNS,
			data,
			layout: "fluid",
			serialNoColumn: true,
			inlineFilters: true,
			clusterize: true,
			noDataMessage: __("No swipes yet."),
		});
	} else {
		wrapper._rfid_dt.refresh(data, DT_COLUMNS);
	}
}

const DETAILS = {
	terminals: { title: __("Terminals today"), html: "_terminals_html", wide: true },
	outcomes: { title: __("What happened to today's swipes"), html: "_outcomes_html" },
};

// snapshot of the panel as of the last refresh
function open_detail(wrapper, key) {
	const cfg = DETAILS[key];
	const d = new frappe.ui.Dialog({
		title: cfg.title,
		size: cfg.wide ? "large" : null,
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
		...(key === "outcomes" ? {
			primary_action_label: __("Open Attendance Sync"),
			primary_action() { d.hide(); frappe.set_route("attendance-sync"); },
		} : {}),
	});
	d.$wrapper.addClass("er-theme");
	d.fields_dict.body.$wrapper.html(`<div class="rf rf-dialog"><div class="rf-scroll">${wrapper[cfg.html] || ""}</div></div>`);
	d.show();
}

function run_now(wrapper) {
	frappe.call({
		method: "slcm.slcm.rfid_sql_agent.poller.poll_now",
		freeze: true,
		freeze_message: __("Polling SQL Server..."),
		callback(r) {
			if (!r.message) return;
			frappe.show_alert({
				message: r.message.message,
				indicator: r.message.success ? "green" : "red",
			});
			load(wrapper);
		},
	});
}

function add_styles() {
	if (document.getElementById("rf-styles")) return;
	$("head").append(`<style id="rf-styles">
		.rf{display:flex;flex-direction:column;gap:16px;padding:6px 16px 40px;font-family:var(--er-font,Georgia,serif);font-size:13px;color:var(--text-color)}
		.rf button{font:inherit;cursor:pointer}
		.rf h4{font-size:14px;font-weight:700;margin:0}
		.rf-muted{color:var(--text-muted);font-size:12px}
		.rf-health{display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap;background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:14px 16px}
		.rf-health-text{flex:1 1 420px;line-height:1.7}
		.rf-refreshed{margin-left:auto}
		.rf-pill{display:inline-flex;align-items:center;gap:7px;font-weight:700;font-size:12px;border-radius:999px;padding:4px 12px;white-space:nowrap;background:var(--gray-100,#f3f3f3)}
		.rf-pill i{width:8px;height:8px;border-radius:50%;background:currentColor}
		.rf-pill.ok{color:#1F7A4D;background:#E7F4EC}.rf-pill.warn{color:#8A5A00;background:#FDF3DC}
		.rf-pill.bad,.rf-pill.off{color:#920C24;background:#FBEEF0}
		.rf-warn-text{color:#8A5A00;font-weight:700}
		.rf-link{border:0;background:none;padding:0;color:var(--er-brand,#920C24);font-weight:700}
		.rf-link:hover{text-decoration:underline}
		.rf-alert{border:1px solid #E8B4BE;background:#FBEEF0;border-radius:10px;padding:12px 16px}
		.rf-alert ul{margin:8px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px}
		.rf-alert li{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
		.rf-btn{border:1px solid var(--er-brand,#920C24);background:var(--card-bg);color:var(--er-brand,#920C24);border-radius:7px;padding:4px 12px;font-size:12px;font-weight:700}
		.rf-btn:hover{background:var(--er-brand,#920C24);color:#fff}
		.rf-kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px}
		.rf-kpi{display:flex;flex-direction:column;align-items:flex-start;gap:3px;text-align:left;color:var(--text-color);background:var(--card-bg);
			border:1px solid var(--border-color);border-radius:10px;padding:12px 14px}
		.rf-kpi:hover{background:var(--subtle-fg,var(--gray-50,#fafafa))}
		.rf-kpi span,.rf-kpi small{font-size:12px;color:var(--text-muted)}
		.rf-kpi b{font-size:24px;line-height:1.15;font-variant-numeric:tabular-nums}
		.rf-two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
		.rf-drill{display:flex;align-items:center;justify-content:space-between;gap:12px;text-align:left;color:var(--text-color);
			background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:14px 16px;min-width:0}
		.rf-drill:hover{background:var(--subtle-fg,var(--gray-50,#fafafa))}
		.rf-drill-text{display:flex;flex-direction:column;gap:4px;min-width:0}
		.rf-drill-go{color:var(--er-brand,#920C24);font-weight:700;font-size:12px;white-space:nowrap}
		.rf.rf-dialog{padding:0}
		.rf-dialog .rf-scroll{max-height:60vh}
		.rf-panel{background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:14px 16px;min-width:0}
		.rf-panel-head{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:10px;flex-wrap:wrap}
		.rf-scroll{max-height:340px;overflow:auto;position:relative}
		.rf-table{width:100%;border-collapse:collapse;font-size:12.5px}
		.rf-table th{position:sticky;top:0;background:var(--card-bg);text-align:left;font-weight:700;color:var(--text-muted);font-size:11.5px;padding:6px 8px;border-bottom:1px solid var(--border-color)}
		.rf-table td{padding:6px 8px;border-bottom:1px solid var(--border-color)}
		.rf-table .num{text-align:right;font-variant-numeric:tabular-nums}
		.rf-chip{display:inline-block;font-size:11px;font-weight:700;border-radius:999px;padding:1px 9px;white-space:nowrap}
		.rf-chip.ok{color:#1F7A4D;background:#E7F4EC}.rf-chip.warn{color:#8A5A00;background:#FDF3DC}.rf-chip.bad{color:#920C24;background:#FBEEF0}
		.rf-out{padding:6px 0 10px}
		.rf-out-top{display:flex;justify-content:space-between;gap:10px}
		.rf-out-top span{font-weight:700;font-variant-numeric:tabular-nums}
		.rf-bar{height:6px;border-radius:3px;background:var(--gray-100,#f0f0f0);margin:5px 0 2px;overflow:hidden}
		.rf-bar i{display:block;height:100%;background:var(--er-brand,#920C24)}.rf-bar i.ok{background:#1F7A4D}
		.rf-empty{color:var(--text-muted);margin:0}
		@media (max-width:900px){.rf-two{grid-template-columns:minmax(0,1fr)}.rf-refreshed{margin-left:0}}
		@media (max-width:600px){.rf-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.rf-kpi b{font-size:20px}}
	</style>`);
}
