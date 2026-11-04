/* global slcm */
frappe.provide("slcm.id_card");

// The summary replaces these sections; they stay as the stored record.
const IDCL_HIDDEN_SECTIONS = [
	"sec_break_run",
	"sec_break_settings",
	"sec_break_metrics",
	"sec_break_results",
	"sec_break_remarks",
];
const IDCL_RESULT_CLASS = { New: "new", Regenerated: "regen", Skipped: "skip", Failed: "fail" };

// NLSIU maroon (same tokens as the Generation Tool); green marks success only.
const IDCL_CSS = `
	:root { --idcl-maroon: #920c24; --idcl-maroon-soft: rgba(146,12,36,.07); --idcl-maroon-mid: rgba(146,12,36,.14); --idcl-maroon-solid: #920c24;
		--idcl-green: #15803d; --idcl-green-soft: rgba(34,197,94,.12); }
	[data-theme="dark"] { --idcl-maroon: #f08da0; --idcl-maroon-soft: rgba(214,74,102,.14); --idcl-maroon-mid: rgba(214,74,102,.26);
		--idcl-green: #4ade80; --idcl-green-soft: rgba(74,222,128,.14); }
	.idcl-page .page-actions .btn-primary, .idcl-page .page-actions .btn-primary:hover { background: var(--idcl-maroon-solid); border-color: var(--idcl-maroon-solid); color: #fff; }

	.idcl { --b: var(--border-color, #e2e6ea); --m: var(--text-muted, #6b7280); --s: var(--subtle-fg, #f4f5f7); --bg: var(--fg-color, #fff);
		--t: var(--text-color, #1f2937); --a: var(--idcl-maroon); --a-soft: var(--idcl-maroon-soft); --a-mid: var(--idcl-maroon-mid);
		--ok: var(--idcl-green); --ok-soft: var(--idcl-green-soft); color: var(--t); display: grid; gap: 16px; }
	.idcl * { box-sizing: border-box; }
	.idcl-panel { background: var(--bg); border: 1px solid var(--b); border-radius: 14px; overflow: hidden; }
	.idcl-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 13px 16px; border-bottom: 1px solid var(--b); }
	.idcl-panel-title { font-weight: 600; font-size: 13.5px; display: flex; align-items: center; gap: 8px; }
	.idcl-panel-title svg { color: var(--a); }
	.idcl-sub { color: var(--m); font-size: 11.5px; }

	/* Header */
	.idcl-head { display: flex; align-items: center; gap: 22px; padding: 20px 22px; flex-wrap: wrap; border-left: 4px solid var(--idcl-maroon-solid); }
	.idcl-ring { position: relative; width: 84px; height: 84px; flex-shrink: 0; }
	.idcl-ring svg { transform: rotate(-90deg); display: block; }
	.idcl-ring-label { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
	.idcl-ring-label b { font-size: 19px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }
	.idcl-ring-label span { font-size: 10px; color: var(--m); margin-top: 3px; text-transform: uppercase; letter-spacing: .06em; }
	.idcl-head-main { flex: 1 1 320px; min-width: 0; }
	.idcl-eyebrow { font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--a); }
	.idcl-head h3 { margin: 4px 0 6px; font-size: 21px; font-weight: 600; letter-spacing: -.01em; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
	.idcl-summary { font-size: 13.5px; color: var(--t); line-height: 1.5; }
	.idcl-summary .muted { color: var(--m); }
	.idcl-status { display: inline-flex; align-items: center; gap: 6px; padding: 3px 11px; border-radius: 99px; font-size: 12px; font-weight: 600; }
	.idcl-status::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
	.idcl-status.success { background: var(--ok-soft); color: var(--ok); }
	.idcl-status.partial { background: var(--a-soft); color: var(--a); }
	.idcl-status.failed { background: var(--idcl-maroon-solid); color: #fff; }
	.idcl-status.failed::before { background: #fff; }
	.idcl-kpis { display: flex; flex: 0 1 auto; border: 1px solid var(--b); border-radius: 12px; overflow: hidden; }
	.idcl-kpi { padding: 10px 18px; min-width: 104px; border-right: 1px solid var(--b); }
	.idcl-kpi:last-child { border-right: 0; }
	.idcl-kpi b { display: block; font-size: 20px; font-weight: 600; line-height: 1.2; font-variant-numeric: tabular-nums; }
	.idcl-kpi span { display: block; font-size: 11.5px; color: var(--m); white-space: nowrap; }
	.idcl-kpi.good b { color: var(--ok); }
	.idcl-kpi.bad b, .idcl-kpi.warn b { color: var(--a); }
	.idcl-kpi.zero b { color: var(--m); font-weight: 500; }
	.idcl-breakdown { display: flex; align-items: center; gap: 14px; padding: 0 22px 16px 26px; flex-wrap: wrap; }
	.idcl-bar { flex: 1 1 240px; display: flex; height: 6px; border-radius: 99px; overflow: hidden; background: var(--s); gap: 2px; }
	.idcl-bar > div { height: 100%; }
	.idcl-c-new { background: var(--ok); }
	.idcl-c-regen { background: var(--ok); opacity: .5; }
	.idcl-c-skip { background: var(--gray-400, #9ca3af); opacity: .55; }
	.idcl-c-fail { background: var(--idcl-maroon-solid); }
	.idcl-legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--m); }
	.idcl-legend span { display: inline-flex; align-items: center; gap: 6px; }
	.idcl-legend i { display: inline-block; width: 9px; height: 9px; border-radius: 3px; }
	.idcl-legend b { color: var(--t); font-weight: 600; }

	/* Body */
	.idcl-body { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 16px; align-items: start; }
	.idcl-side { display: grid; gap: 16px; }
	.idcl-dl { margin: 0; padding: 6px 16px 10px; }
	.idcl-dl > div { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 9px 0; border-bottom: 1px dashed var(--b); font-size: 13px; }
	.idcl-dl > div:last-child { border-bottom: 0; }
	.idcl-dl dt { color: var(--m); font-weight: 400; flex-shrink: 0; }
	.idcl-dl dd { margin: 0; text-align: right; font-weight: 500; display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 5px; overflow-wrap: anywhere; }
	.idcl-dl dd a { color: var(--a); }
	.idcl-dl .muted { color: var(--m); font-weight: 400; }
	.idcl-tag { display: inline-flex; align-items: center; padding: 1px 8px; border-radius: 6px; background: var(--s); font-size: 12px; font-weight: 500; }
	.idcl-tag.on { background: var(--a-soft); color: var(--a); }

	/* Results */
	.idcl-tools { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 10px 16px; border-bottom: 1px solid var(--b); }
	.idcl-chip { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 11px; border-radius: 99px; border: 1px solid var(--b);
		background: var(--bg); color: var(--t); font-size: 12px; cursor: pointer; }
	.idcl-chip b { color: var(--m); font-weight: 600; }
	.idcl-chip.active { background: var(--idcl-maroon-solid); border-color: var(--idcl-maroon-solid); color: #fff; }
	.idcl-chip.active b { color: inherit; opacity: .8; }
	.idcl-spacer { flex: 1; }
	.idcl-search { height: 30px; width: 210px; max-width: 100%; border: 1px solid var(--b); border-radius: 8px; padding: 0 10px; background: var(--control-bg, var(--s)); color: var(--t); font-size: 12.5px; }
	.idcl-search:focus { outline: none; border-color: var(--a); box-shadow: 0 0 0 2px var(--a-soft); }
	.idcl-btn { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 11px; border-radius: 8px; border: 1px solid var(--b); background: var(--bg);
		color: var(--t); font-size: 12.5px; cursor: pointer; }
	.idcl-btn:hover { border-color: var(--a); color: var(--a); }
	.idcl-table { width: 100%; border-collapse: collapse; font-size: 13px; }
	.idcl-table th { text-align: left; font-weight: 500; font-size: 11.5px; color: var(--m); padding: 9px 16px; background: var(--s); border-bottom: 1px solid var(--b); position: sticky; top: 0; z-index: 1; white-space: nowrap; }
	.idcl-table td { padding: 10px 16px; border-bottom: 1px solid var(--b); vertical-align: middle; }
	.idcl-table th.fit, .idcl-table td.fit { width: 1%; white-space: nowrap; }
	.idcl-table tr:last-child td { border-bottom: 0; }
	.idcl-table tbody tr:hover td { background: var(--s); }
	.idcl-table tr.is-fail td { background: var(--a-soft); }
	.idcl-table tr.is-fail td:first-child { box-shadow: inset 3px 0 0 var(--idcl-maroon-solid); }
	.idcl-person { display: flex; align-items: center; gap: 10px; min-width: 0; }
	.idcl-avatar { width: 32px; height: 32px; border-radius: 9px; background: var(--s); color: var(--m); font-size: 11.5px; font-weight: 600; flex-shrink: 0;
		display: inline-flex; align-items: center; justify-content: center; }
	.idcl-avatar.missing { border: 1.5px dashed var(--a); color: var(--a); }
	.idcl-person a { color: var(--t); font-weight: 500; }
	.idcl-person a, .idcl-person .idcl-sub { white-space: nowrap; }
	.idcl-table td:first-child { min-width: 220px; }
	.idcl-msg { min-width: 220px; }
	.idcl-person a:hover { color: var(--a); }
	.idcl-sub .nophoto { color: var(--a); }
	.idcl-result { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 99px; font-size: 11.5px; font-weight: 500; white-space: nowrap; }
	.idcl-result::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
	.idcl-result.new { background: var(--ok-soft); color: var(--ok); }
	.idcl-result.regen { background: transparent; color: var(--ok); box-shadow: inset 0 0 0 1px var(--ok-soft); }
	.idcl-result.skip { background: var(--s); color: var(--m); }
	.idcl-result.fail { background: var(--idcl-maroon-solid); color: #fff; }
	.idcl-card-link { color: var(--t); font-variant-numeric: tabular-nums; display: inline-flex; align-items: center; gap: 4px; }
	.idcl-card-link:hover { color: var(--a); }
	.idcl-msg { color: var(--m); font-size: 12px; }
	.idcl-msg.fail { color: var(--a); font-weight: 500; }
	.idcl-note { display: flex; align-items: center; gap: 8px; padding: 9px 16px; font-size: 12.5px; color: var(--a); background: var(--a-soft); border-bottom: 1px solid var(--b); }
	.idcl .idcl-rebuild, .idcl .idcl-rebuild:hover { background: var(--idcl-maroon-solid); border-color: var(--idcl-maroon-solid); color: #fff; }
	.idcl-empty { padding: 36px 16px; text-align: center; color: var(--m); font-size: 13px; }
	.idcl-empty b { display: block; color: var(--t); font-size: 14px; margin-bottom: 4px; }

	@media (max-width: 1200px) { .idcl-body { grid-template-columns: minmax(0, 1fr); } .idcl-side { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); } }
	@media (max-width: 760px) {
		.idcl-kpis { width: 100%; flex-wrap: wrap; }
		.idcl-kpi { flex: 1 1 45%; border-bottom: 1px solid var(--b); }
		.idcl-search { width: 100%; }
	}
`;

const IDCL_ICONS = {
	calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
	user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>',
	clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
	layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
	hash: '<path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/>',
	users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
	check: '<path d="M20 6 9 17l-5-5"/>',
	skip: '<path d="M5 12h14M13 6l6 6-6 6"/>',
	alert: '<path d="M12 3 2 21h20z"/><path d="M12 10v5M12 18h.01"/>',
	camera: '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
	sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
	list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
	download: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>',
	arrow: '<path d="M7 17 17 7M8 7h9v9"/>',
	info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
};
const idcl_icon = (name, size = 16) =>
	`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IDCL_ICONS[name]}</svg>`;

function idcl_duration(seconds) {
	if (seconds === null || seconds === undefined || seconds === "") return "";
	const s = Math.round(+seconds);
	if (s < 60) return __("{0}s", [s]);
	const m = Math.floor(s / 60);
	return s % 60 ? __("{0}m {1}s", [m, s % 60]) : __("{0}m", [m]);
}

function idcl_figures(doc) {
	const generated = doc.total_id_cards_generated || 0;
	// Older runs recorded only the generated count.
	const failed =
		doc.failed_count ||
		(doc.total_processed ? Math.max(doc.total_processed - generated, 0) : 0);
	const processed = doc.total_processed || generated + failed;
	return {
		results: doc.results || [],
		generated,
		failed,
		processed,
		new_cards: doc.new_cards || 0,
		regenerated: doc.regenerated_cards || 0,
		skipped: doc.skipped_count || 0,
		selected: doc.total_students_selected || 0,
		// Old runs never recorded photos; only trust the count once students are listed.
		no_photo: doc.missing_photo_count || 0,
		no_photo_known: !!(doc.results || []).length || !!doc.started_on,
		rate: processed ? Math.round((generated / processed) * 100) : null,
	};
}

function idcl_ring(rate, all_ok) {
	const r = 35;
	const c = 2 * Math.PI * r;
	const pct = rate === null ? 0 : rate;
	const color = all_ok ? "var(--ok)" : "var(--idcl-maroon-solid)";
	return `<div class="idcl-ring" title="${__("Cards generated out of students processed")}">
		<svg width="84" height="84" viewBox="0 0 84 84">
			<circle cx="42" cy="42" r="${r}" fill="none" stroke="var(--s)" stroke-width="8"/>
			<circle cx="42" cy="42" r="${r}" fill="none" stroke="${color}" stroke-width="8" stroke-linecap="round"
				stroke-dasharray="${(c * pct) / 100} ${c}"/>
		</svg>
		<div class="idcl-ring-label"><b>${rate === null ? "—" : `${rate}%`}</b><span>${__(
		"success"
	)}</span></div>
	</div>`;
}

function idcl_export_csv(frm) {
	const rows = [["Student", "Student Name", "Result", "ID Card", "Has Photo", "Details"]];
	(frm.doc.results || []).forEach((r) =>
		rows.push([
			r.student,
			r.student_name || "",
			r.result || "",
			r.id_card || "",
			r.has_photo ? "Yes" : "No",
			r.message || "",
		])
	);
	const csv = rows
		.map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))
		.join("\r\n");
	// The BOM makes Excel open the file as UTF-8.
	const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
	const a = document.createElement("a");
	a.href = url;
	a.download = `${frm.doc.name}_results.csv`;
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** One plain sentence describing what the run did. */
function idcl_sentence(f) {
	if (!f.processed && !f.skipped) return __("Nothing was processed in this run.");
	const parts = [];
	if (f.new_cards) parts.push(__("{0} new", [f.new_cards]));
	if (f.regenerated) parts.push(__("{0} regenerated", [f.regenerated]));
	let text = __("<b>{0}</b> card(s) generated for {1} student(s)", [f.generated, f.processed]);
	if (parts.length) text += ` — ${parts.join(", ")}`;
	const extra = [];
	if (f.skipped) extra.push(__("{0} skipped", [f.skipped]));
	if (f.failed) extra.push(`<b style="color:var(--a)">${__("{0} failed", [f.failed])}</b>`);
	if (extra.length) text += `; ${extra.join(", ")}`;
	return text + ".";
}

function idcl_render(frm) {
	if (!document.getElementById("idcl-css"))
		$(`<style id="idcl-css">${IDCL_CSS}</style>`).appendTo("head");
	const doc = frm.doc;
	const esc = frappe.utils.escape_html;
	const f = idcl_figures(doc);
	const state = (frm.__idcl =
		frm.__idcl && frm.__idcl.name === doc.name
			? frm.__idcl
			: { name: doc.name, filter: "all", query: "" });
	const link = (doctype, name) =>
		name
			? `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${esc(
					name
			  )}</a>`
			: "";
	const muted = (text) => `<span class="muted">${text}</span>`;

	// ---- Header ----------------------------------------------------------
	const status = doc.generation_status || "";
	const status_cls =
		{ Success: "success", Partial: "partial", Failed: "failed" }[status] || "partial";
	const kpi = (value, label, cls) =>
		value === null
			? `<div class="idcl-kpi zero" title="${__(
					"Not recorded for this run"
			  )}"><b>—</b><span>${label}</span></div>`
			: `<div class="idcl-kpi ${
					value ? cls : "zero"
			  }"><b>${value}</b><span>${label}</span></div>`;
	const parts = [
		["new", f.new_cards, __("New")],
		["regen", f.regenerated, __("Regenerated")],
		["skip", f.skipped, __("Skipped")],
		["fail", f.failed, __("Failed")],
	].filter((p) => p[1]);
	const parts_total = parts.reduce((n, p) => n + p[1], 0);
	const breakdown = parts_total
		? `<div class="idcl-breakdown">
			<div class="idcl-bar">${parts
				.map(
					(p) =>
						`<div class="idcl-c-${p[0]}" style="width:${
							(p[1] / parts_total) * 100
						}%" title="${p[2]}: ${p[1]}"></div>`
				)
				.join("")}</div>
			<div class="idcl-legend">${parts
				.map((p) => `<span><i class="idcl-c-${p[0]}"></i>${p[2]} <b>${p[1]}</b></span>`)
				.join("")}</div>
		</div>`
		: "";
	const when = doc.generated_on ? frappe.datetime.str_to_user(doc.generated_on) : "";
	const user = doc.generated_by ? frappe.user.full_name(doc.generated_by) : "";

	// ---- Side: run details & settings --------------------------------------
	const row = (label, value) => `<div><dt>${label}</dt><dd>${value}</dd></div>`;
	const run_rows = [
		doc.started_on && row(__("Started"), esc(frappe.datetime.str_to_user(doc.started_on))),
		when && row(__("Finished"), esc(when)),
		doc.duration_seconds && row(__("Duration"), idcl_duration(doc.duration_seconds)),
		user && row(__("Run by"), esc(user)),
		doc.generation_mode && row(__("Mode"), esc(__("{0} run", [__(doc.generation_mode)]))),
		doc.generation_tool_run_id &&
			row(__("Run ID"), `<span class="idcl-tag">${esc(doc.generation_tool_run_id)}</span>`),
	]
		.filter(Boolean)
		.join("");
	const filters = [
		[__("Year"), doc.academic_year],
		[__("Programme"), doc.program],
		[__("Batch"), doc.batch],
		[__("Section"), doc.section],
	].filter((x) => x[1]);
	const settings_rows = [
		row(
			__("Template"),
			doc.template_used
				? link("ID Card Template", doc.template_used)
				: muted(__("Not recorded"))
		),
		row(
			__("Students"),
			filters.length
				? filters
						.map(
							([k, v]) => `<span class="idcl-tag" title="${esc(k)}">${esc(v)}</span>`
						)
						.join("")
				: muted(__("Whole list"))
		),
		row(
			__("Issue date"),
			doc.issue_date
				? esc(frappe.datetime.str_to_user(doc.issue_date))
				: muted(__("Not recorded"))
		),
		row(
			__("Valid till"),
			doc.expiry_date
				? esc(frappe.datetime.str_to_user(doc.expiry_date))
				: muted(__("Programme end date"))
		),
		row(
			__("Sides"),
			doc.sides
				? doc.sides
						.split("+")
						.map((s) => `<span class="idcl-tag">${esc(s.trim())}</span>`)
						.join("")
				: muted(__("Not recorded"))
		),
		row(
			__("Regenerate existing"),
			// Runs before start times were kept didn't record this setting either.
			!doc.started_on && !doc.regenerate_existing
				? muted(__("Not recorded"))
				: `<span class="idcl-tag ${doc.regenerate_existing ? "on" : ""}">${
						doc.regenerate_existing ? __("Yes") : __("No")
				  }</span>`
		),
	].join("");

	// ---- Results --------------------------------------------------------
	let results_html;
	const can_rebuild = !!(frm.perm[0] && frm.perm[0].write);
	if (!f.results.length) {
		if (!f.generated && !f.failed) {
			results_html = `<div class="idcl-empty"><b>${__("No cards in this run")}</b>${__(
				"No ID cards were generated, so there are no students to list."
			)}</div>`;
		} else if (doc.results_reconstructed) {
			results_html = `<div class="idcl-empty"><b>${__(
				"These cards no longer exist"
			)}</b>${__(
				"This run was recorded before students were listed, and the {0} card(s) it produced have since been deleted, so the students can't be found.",
				[f.generated]
			)}</div>`;
		} else {
			results_html = `<div class="idcl-empty"><b>${__("Students not listed yet")}</b>${__(
				"This run was recorded before students were listed with each run. They can be found from the cards it produced."
			)}${
				can_rebuild
					? `<div style="margin-top:14px"><button class="btn btn-primary btn-sm idcl-rebuild" data-act="rebuild">${__(
							"Find students from card records"
					  )}</button></div>`
					: ""
			}</div>`;
		}
	} else {
		const counts = { all: f.results.length };
		f.results.forEach((r) => (counts[r.result] = (counts[r.result] || 0) + 1));
		const chip = (key, label) =>
			key === "all" || counts[key]
				? `<button class="idcl-chip ${
						state.filter === key ? "active" : ""
				  }" data-filter="${key}">${label} <b>${counts[key]}</b></button>`
				: "";
		const q = state.query.toLowerCase();
		const rows = f.results.filter(
			(r) =>
				(state.filter === "all" || r.result === state.filter) &&
				(!q ||
					`${r.student} ${r.student_name || ""} ${r.id_card || ""}`
						.toLowerCase()
						.includes(q))
		);
		const show_details = f.results.some((r) => r.message);
		const initials = (name) =>
			(name || "")
				.split(/\s+/)
				.map((w) => w[0])
				.slice(0, 2)
				.join("")
				.toUpperCase();
		const body = rows
			.map(
				(r) => `<tr class="${r.result === "Failed" ? "is-fail" : ""}">
				<td><div class="idcl-person"><span class="idcl-avatar ${r.has_photo ? "" : "missing"}" title="${
					r.has_photo ? "" : __("No photo: the default avatar was printed")
				}">${esc(
					initials(r.student_name || r.student)
				)}</span><div style="min-width:0">${link(
					"Student Master",
					r.student
				)}<div class="idcl-sub">${esc(r.student_name || "")}${
					r.has_photo ? "" : ` · <span class="nophoto">${__("no photo")}</span>`
				}</div></div></div></td>
				<td class="fit"><span class="idcl-result ${IDCL_RESULT_CLASS[r.result] || "skip"}">${__(
					r.result || ""
				)}</span></td>
				<td class="fit">${
					r.id_card
						? `<a class="idcl-card-link" href="/app/id-card-generation/${encodeURIComponent(
								r.id_card
						  )}">${esc(r.id_card)} ${idcl_icon("arrow", 12)}</a>`
						: `<span class="idcl-sub">—</span>`
				}</td>
				${
					show_details
						? `<td><div class="idcl-msg ${r.result === "Failed" ? "fail" : ""}">${esc(
								r.message || ""
						  )}</div></td>`
						: ""
				}
			</tr>`
			)
			.join("");
		const rebuilt_note = doc.results_reconstructed
			? `<div class="idcl-note">${idcl_icon("info", 14)}<span>${
					f.results.length < f.generated
						? __(
								"Rebuilt from card records: found {0} of {1} card(s). The rest have since been deleted.",
								[f.results.length, f.generated]
						  )
						: __(
								"Rebuilt from card records, because this run was recorded before students were listed."
						  )
			  }</span></div>`
			: "";
		results_html = `${rebuilt_note}
			<div class="idcl-tools">
				${chip("all", __("All"))}${chip("New", __("New"))}${chip("Regenerated", __("Regenerated"))}${chip(
			"Skipped",
			__("Skipped")
		)}${chip("Failed", __("Failed"))}
				<span class="idcl-spacer"></span>
				<input class="idcl-search" type="search" placeholder="${__(
					"Search student or card"
				)}" value="${esc(state.query)}">
				<button class="idcl-btn" data-act="csv" title="${__("Download these results as CSV")}">${idcl_icon(
			"download",
			14
		)} ${__("CSV")}</button>
			</div>
			${
				rows.length
					? `<div style="max-height:640px;overflow:auto"><table class="idcl-table">
				<thead><tr><th>${__("Student")}</th><th class="fit">${__("Result")}</th><th class="fit">${__(
							"ID card"
					  )}</th>${show_details ? `<th>${__("Details")}</th>` : ""}</tr></thead>
				<tbody>${body}</tbody></table></div>`
					: `<div class="idcl-empty">${__("No results match this filter.")}</div>`
			}`;
	}

	const $w = frm.fields_dict.summary_html.$wrapper;
	$w.closest(".section-body").css("max-width", "none");
	$w.html(`
		<div class="idcl">
			<section class="idcl-panel">
				<div class="idcl-head">
					${idcl_ring(f.rate, !f.failed && f.generated > 0)}
					<div class="idcl-head-main">
						<div class="idcl-eyebrow">${__("ID card generation run")}</div>
						<h3>${esc(doc.name)} <span class="idcl-status ${status_cls}">${__(status || "—")}</span></h3>
						<div class="idcl-summary">${idcl_sentence(f)} ${
		when
			? `<span class="muted">${__("Finished {0}", [
					frappe.datetime.comment_when(doc.generated_on),
			  ])}.</span>`
			: ""
	}</div>
					</div>
					<div class="idcl-kpis">
						${kpi(f.generated, __("Generated"), "good")}
						${kpi(f.skipped, __("Skipped"), "")}
						${kpi(f.failed, __("Failed"), "bad")}
						${kpi(f.no_photo_known ? f.no_photo : null, __("Without photo"), "warn")}
					</div>
				</div>
				${breakdown}
			</section>
			<div class="idcl-body">
				<section class="idcl-panel">
					<div class="idcl-panel-head"><div class="idcl-panel-title">${idcl_icon("list", 15)}${__(
		"Results by student"
	)}</div>
						<span class="idcl-sub">${__("{0} of {1} students processed", [
							f.processed,
							f.selected || f.processed,
						])}</span></div>
					${results_html}
				</section>
				<aside class="idcl-side">
					${
						run_rows
							? `<section class="idcl-panel"><div class="idcl-panel-head"><div class="idcl-panel-title">${idcl_icon(
									"clock",
									15
							  )}${__(
									"Run details"
							  )}</div></div><dl class="idcl-dl">${run_rows}</dl></section>`
							: ""
					}
					<section class="idcl-panel"><div class="idcl-panel-head"><div class="idcl-panel-title">${idcl_icon(
						"sliders",
						15
					)}${__(
		"Settings used"
	)}</div></div><dl class="idcl-dl">${settings_rows}</dl></section>
				</aside>
			</div>
		</div>`);

	$w.off(".idcl");
	$w.on("click.idcl", "[data-filter]", (e) => {
		state.filter = $(e.currentTarget).data("filter");
		idcl_render(frm);
	});
	$w.on("click.idcl", "[data-act='csv']", () => idcl_export_csv(frm));
	$w.on("click.idcl", "[data-act='rebuild']", () => {
		frm.call({
			doc: frm.doc,
			method: "rebuild_results",
			freeze: true,
			freeze_message: __("Looking up the cards from this run…"),
		}).then((r) => {
			if (r.exc || !r.message) return;
			frm.reload_doc();
			const { found, expected } = r.message;
			frappe.show_alert({
				message: found
					? __("Found {0} of {1} card(s) from this run.", [found, expected])
					: __("The cards from this run no longer exist."),
				indicator: found ? "green" : "orange",
			});
		});
	});
	$w.on(
		"input.idcl",
		".idcl-search",
		frappe.utils.debounce((e) => {
			state.query = e.target.value.trim();
			const pos = e.target.selectionStart;
			idcl_render(frm);
			const input = $w.find(".idcl-search")[0];
			if (input) {
				input.focus();
				input.setSelectionRange(pos, pos);
			}
		}, 200)
	);
}

frappe.ui.form.on("ID Card Generation Tool Log", {
	refresh(frm) {
		frm.disable_save();
		frm.toggle_display(IDCL_HIDDEN_SECTIONS, false);
		frm.page.wrapper.addClass("idcl-page");
		// The status is shown in the summary, in the NLSIU colours.
		frm.page.clear_indicator();
		frm.page.wrapper.find(".layout-side-section").hide();
		idcl_render(frm);

		const results = frm.doc.results || [];
		const failed = results.filter((r) => r.result === "Failed").map((r) => r.student);
		if (failed.length) {
			frm.page.set_primary_action(__("Retry {0} failed", [failed.length]), () => {
				slcm.id_card.pending_tool_students = {
					students: failed,
					template: frm.doc.template_used,
				};
				frappe.set_route("Form", "ID Card Generation Tool");
			});
		}
		const cards = [...new Set(results.map((r) => r.id_card).filter(Boolean))];
		if (cards.length) {
			frm.add_custom_button(__("View {0} card(s)", [cards.length]), () => {
				frappe.route_options = { name: ["in", cards] };
				frappe.set_route("List", "ID Card Generation");
			});
		}
		frm.add_custom_button(__("Open Generation Tool"), () =>
			frappe.set_route("Form", "ID Card Generation Tool")
		);
	},
});
