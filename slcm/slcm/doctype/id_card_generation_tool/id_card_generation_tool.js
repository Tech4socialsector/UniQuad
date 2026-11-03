/* global slcm */
frappe.provide("slcm.id_card");

// The tool renders its own screen into `wizard_html`; the standard sections
// stay hidden and only hold the values sent to the server.
const IDCT_HIDDEN_SECTIONS = ["section_filters", "section_students", "section_template"];
const IDCT_PAGE_SIZE = 150;

const IDCT_CSS = `
	:root { --idct-maroon: #920c24; --idct-maroon-soft: rgba(146,12,36,.07); --idct-maroon-mid: rgba(146,12,36,.14); --idct-maroon-solid: #920c24; }
	[data-theme="dark"] { --idct-maroon: #f08da0; --idct-maroon-soft: rgba(214,74,102,.14); --idct-maroon-mid: rgba(214,74,102,.26); }
	.idct .btn-primary, .idct .btn-primary:hover, .idct .btn-primary:focus { background: var(--idct-maroon-solid); border-color: var(--idct-maroon-solid); color: #fff; }
	.idct .btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
	.idct input[type="checkbox"]:checked { background-color: var(--idct-maroon-solid); border-color: var(--idct-maroon-solid); }
	.idct input[type="checkbox"] { accent-color: var(--idct-maroon-solid); }
	.idct { --b: var(--border-color, #e2e6ea); --m: var(--text-muted, #6b7280); --s: var(--subtle-fg, #f4f5f7);
		--a: var(--idct-maroon); --a-soft: var(--idct-maroon-soft); --a-mid: var(--idct-maroon-mid); --bg: var(--fg-color, #fff); --t: var(--text-color, #1f2937); color: var(--t); }
	.idct * { box-sizing: border-box; }
	.idct-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }
	.idct-head h3 { margin: 0; font-size: 20px; font-weight: 600; letter-spacing: -.01em; }
	.idct-head p { margin: 4px 0 0; color: var(--m); font-size: 13px; }
	.idct-layout { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 20px; align-items: start; }
	.idct-panel { background: var(--bg); border: 1px solid var(--b); border-radius: 14px; }
	.idct-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--b); }
	.idct-panel-title { font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 8px; }
	.idct-num { width: 22px; height: 22px; border-radius: 50%; background: var(--s); color: var(--m); font-size: 11.5px; font-weight: 600;
		display: inline-flex; align-items: center; justify-content: center; }
	.idct-num.done { background: var(--green-500, #22c55e); color: #fff; }
	.idct-panel-body { padding: 14px 16px; }
	.idct-side { position: sticky; top: 72px; display: grid; gap: 16px; max-height: calc(100vh - 88px); overflow-y: auto; overscroll-behavior: contain;
		scrollbar-width: thin; padding-bottom: 4px; }
	.idct-filters { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)) auto; gap: 10px; align-items: end; }
	.idct .form-group { margin-bottom: 0; }
	.idct-filters .frappe-control { margin-bottom: 0; }
	.idct-filters [data-act='find'] { height: 28px; }
	.idct-filters .control-label, .idct-side .control-label { font-size: 11.5px; color: var(--m); margin-bottom: 4px; padding: 0; }
	.idct-side .frappe-control { margin-bottom: 10px; }
	.idct-side .help-box { display: none; }
	.idct-addrow { display: flex; align-items: center; gap: 10px; margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--b); }
	.idct-addrow .frappe-control { flex: 1; margin: 0; max-width: 360px; }
	.idct-addrow .control-label, .idct-addrow .clearfix { display: none; }
	.idct-addrow .idct-hint { color: var(--m); font-size: 12px; }
	.idct-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 12px 16px; border-bottom: 1px solid var(--b); }
	.idct-chip { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border-radius: 99px; border: 1px solid var(--b);
		background: var(--bg); color: var(--t); font-size: 12px; cursor: pointer; white-space: nowrap; }
	.idct-chip b { font-weight: 600; font-variant-numeric: tabular-nums; color: var(--m); }
	.idct-chip.active { background: var(--idct-maroon-solid); border-color: var(--idct-maroon-solid); color: #fff; }
	.idct-chip.active b { color: inherit; opacity: .75; }
	.idct-search { margin-left: auto; height: 30px; width: 220px; max-width: 100%; border: 1px solid var(--b); border-radius: 8px; padding: 0 10px;
		background: var(--control-bg, var(--s)); color: var(--t); font-size: 12.5px; }
	.idct-search:focus { outline: none; border-color: var(--a); }
	.idct-table { width: 100%; border-collapse: collapse; font-size: 13px; }
	.idct-table th { text-align: left; font-weight: 500; font-size: 11.5px; color: var(--m); padding: 8px 16px; border-bottom: 1px solid var(--b);
		background: var(--s); position: sticky; top: 0; z-index: 1; }
	.idct-table td { padding: 9px 16px; border-bottom: 1px solid var(--b); vertical-align: middle; }
	.idct-table tr:last-child td { border-bottom: 0; }
	.idct-table tbody tr { cursor: pointer; }
	.idct-table tbody tr:hover td { background: var(--s); }
	.idct-table tbody tr.is-preview td { background: var(--a-soft); }
	.idct-table tbody tr.is-preview td:first-child { box-shadow: inset 3px 0 0 var(--a); }
	.idct-person { display: flex; align-items: center; gap: 10px; min-width: 0; }
	.idct-avatar { width: 34px; height: 34px; border-radius: 9px; flex-shrink: 0; object-fit: cover; background: var(--s);
		display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; color: var(--m); }
	.idct-avatar.missing { border: 1.5px dashed var(--a); color: var(--a); }
	.idct-person-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.idct-person-id { color: var(--m); font-size: 11.5px; }
	.idct-status { display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px; border-radius: 99px; font-size: 11.5px; font-weight: 500; white-space: nowrap; }
	.idct-status::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
	.idct-status.new { background: var(--s); color: var(--t); }
	.idct-status.has { background: var(--s); color: var(--m); }
	.idct-status.done { background: rgba(34,197,94,.12); color: var(--green-700, #15803d); }
	.idct-status.fail { background: var(--a-mid); color: var(--a); }
	.idct-status.busy { background: var(--s); color: var(--m); }
	.idct-card-link { color: var(--t); font-variant-numeric: tabular-nums; }
	.idct-card-link:hover { color: var(--a); }
	.idct-icon-btn { width: 28px; height: 28px; border-radius: 7px; border: 0; background: transparent; color: var(--m); display: inline-flex;
		align-items: center; justify-content: center; cursor: pointer; }
	.idct-icon-btn:hover { background: var(--bg); color: var(--a); }
	.idct-icon-btn.dl:hover { color: var(--a); }
	.idct-check { width: 16px; height: 16px; margin: 0; cursor: pointer; vertical-align: middle; accent-color: var(--a); }
	.idct-table th.idct-col-check, .idct-table td.idct-col-check { width: 40px; padding-right: 0; }
	.idct-table tbody tr.is-selected td { background: var(--a-soft); }
	.idct-table tbody tr.is-selected:hover td { background: var(--a-mid); }
	.idct-status-cell { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
	.idct-selbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 10px 16px; background: var(--idct-maroon-solid); color: #fff;
		border-bottom: 1px solid var(--b); }
	.idct-selbar .idct-selbar-count { font-size: 13px; font-weight: 600; margin-right: 6px; }
	.idct-selbar .btn { display: inline-flex; align-items: center; gap: 6px; height: 28px; border-radius: 8px; font-size: 12px; border: 0;
		background: rgba(255,255,255,.14); color: #fff; }
	.idct-selbar .btn:hover:not(:disabled) { background: rgba(255,255,255,.22); }
	.idct-selbar .btn.primary { background: #fff; color: var(--idct-maroon-solid); }
	.idct-selbar .btn:disabled { opacity: .45; }
	.idct-selbar .idct-selbar-spacer { flex: 1; }
	.idct-selbar .idct-link { background: none; border: 0; color: inherit; opacity: .75; font-size: 12px; cursor: pointer; text-decoration: underline; }
	.idct-scope { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 10px; margin-bottom: 10px; border-radius: 9px;
		background: var(--a-soft); color: var(--a); font-size: 12.5px; font-weight: 500; }
	.idct-scope button { background: none; border: 0; color: inherit; font-size: 12px; text-decoration: underline; cursor: pointer; padding: 0; }
	.idct-empty { text-align: center; padding: 48px 24px; color: var(--m); font-size: 13px; }
	.idct-empty b { display: block; color: var(--t); font-size: 15px; margin-bottom: 6px; }
	.idct-empty-ico { width: 48px; height: 48px; border-radius: 14px; background: var(--s); color: var(--a); margin: 0 auto 12px; display: flex; align-items: center; justify-content: center; }
	.idct-more { padding: 12px 16px; text-align: center; border-top: 1px solid var(--b); }
	.idct-preview { border-radius: 12px; background: var(--s); padding: 16px; display: flex; align-items: center; justify-content: center; min-height: 190px; }
	.idct-preview img { display: block; max-width: 100%; max-height: 260px; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,.1), 0 10px 24px rgba(15,23,42,.16); }
	.idct-preview-meta { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 10px; font-size: 12px; color: var(--m); }
	.idct-seg { display: inline-flex; background: var(--s); border-radius: 8px; padding: 2px; }
	.idct-seg button { border: 0; background: transparent; color: var(--m); font-size: 12px; padding: 3px 10px; border-radius: 6px; cursor: pointer; }
	.idct-seg button.active { background: var(--bg); color: var(--t); box-shadow: 0 1px 2px rgba(0,0,0,.12); }
	.idct-seg button:disabled { opacity: .4; cursor: default; }
	.idct-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
	.idct-switch { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 8px 0; font-size: 13px; cursor: pointer; margin: 0; font-weight: 400; }
	.idct-switch small { display: block; color: var(--m); font-size: 11.5px; margin-top: 1px; }
	.idct-switch input { width: 16px; height: 16px; margin-top: 2px; flex-shrink: 0; cursor: pointer; }
	.idct-sides { display: flex; gap: 8px; margin-bottom: 4px; }
	.idct-sides label { flex: 1; display: flex; align-items: center; gap: 8px; border: 1px solid var(--b); border-radius: 9px; padding: 7px 10px; font-size: 12.5px; cursor: pointer; margin: 0; font-weight: 400; }
	.idct-sides label.on { border-color: var(--a); background: var(--a-soft); }
	.idct-summary { display: grid; gap: 6px; font-size: 12.5px; margin-bottom: 12px; }
	.idct-summary div { display: flex; justify-content: space-between; }
	.idct-summary span:last-child { font-weight: 600; font-variant-numeric: tabular-nums; }
	.idct-summary .warn { color: var(--a); }
	.idct-go { width: 100%; height: 42px; font-size: 14px; font-weight: 600; border-radius: 10px; }
	.idct-note { font-size: 12px; color: var(--m); margin-top: 8px; text-align: center; }
	.idct-progress { height: 8px; border-radius: 99px; background: var(--s); overflow: hidden; margin: 10px 0 2px; }
	.idct-progress > div { height: 100%; background: var(--a); border-radius: 99px; transition: width .35s ease; }
	.idct-banner { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 12px 16px; border-radius: 12px; margin-bottom: 16px; font-size: 13px;
		border: 1px solid var(--b); background: var(--bg); }
	.idct-banner.ok { border-color: rgba(34,197,94,.4); background: rgba(34,197,94,.07); }
	.idct-banner.bad { border-color: var(--a-mid); background: var(--a-soft); }
	.idct-banner .idct-banner-text { flex: 1; min-width: 220px; }
	.idct-banner small { display: block; color: var(--m); }
	.idct-export-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; padding: 14px 16px 0; }
	.idct-export-meta { display: flex; gap: 6px; flex-wrap: wrap; }
	.idct-pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 99px; font-size: 12px; background: var(--s); color: var(--m); }
	.idct-pill b { color: var(--t); font-variant-numeric: tabular-nums; }
	.idct-pill.ok b { color: var(--green-700, #15803d); }
	.idct-pill.warn b { color: var(--a); }
	.idct-export-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding: 14px 16px 16px; }
	.idct-action { display: flex; align-items: flex-start; gap: 12px; width: 100%; text-align: left; padding: 14px; border-radius: 12px; border: 1px solid var(--b);
		background: var(--bg); color: var(--t); cursor: pointer; transition: border-color .15s, box-shadow .15s, transform .15s; }
	.idct-action:hover:not(:disabled) { border-color: var(--a); box-shadow: 0 6px 18px rgba(15,23,42,.08); transform: translateY(-1px); }
	.idct-action:disabled { opacity: .5; cursor: default; }
	.idct-action-ico { width: 38px; height: 38px; border-radius: 10px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
	.idct-action-ico { background: var(--a-soft); color: var(--a); }
	.idct-action b { display: block; font-size: 13.5px; font-weight: 600; }
	.idct-action small { display: block; color: var(--m); font-size: 12px; margin-top: 2px; line-height: 1.4; }
	.idct-export-empty { display: flex; align-items: center; gap: 12px; padding: 14px 16px 16px; color: var(--m); font-size: 12.5px; }
	.idct-export .idct-scope { margin: 12px 16px 0; }
	@media (max-width: 900px) { .idct-export-grid { grid-template-columns: minmax(0, 1fr); } }
	.idct-skeleton { width: 100%; height: 170px; border-radius: 10px; background: linear-gradient(90deg, var(--s), var(--bg), var(--s)); background-size: 200% 100%;
		animation: idct-shimmer 1.2s infinite; }
	@keyframes idct-shimmer { to { background-position: -200% 0; } }
	@media (max-width: 1200px) { .idct-layout { grid-template-columns: minmax(0, 1fr); } .idct-side { position: static; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); } }
	@media (max-width: 760px) { .idct-filters { grid-template-columns: 1fr; } .idct-search { margin-left: 0; width: 100%; } .idct-col-card { display: none; } }
`;

const IDCT_ICONS = {
	users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
	x: '<path d="M18 6 6 18M6 6l12 12"/>',
	file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
	archive:
		'<rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8M10 12h4"/>',
	check: '<path d="M20 6 9 17l-5-5"/>',
	download: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>',
	trash: '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>',
	printer:
		'<path d="M6 9V2h12v7"/><rect x="6" y="14" width="12" height="8" rx="1"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>',
	spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
};
const idct_icon = (name, size = 16) =>
	`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${IDCT_ICONS[name]}</svg>`;

function idct_status(row) {
	const s = row.status || "Pending";
	if (s === "Already Exists") return { key: "has", label: __("Has card") };
	if (s === "Generated") return { key: "done", label: __("Generated") };
	if (s.startsWith("Error"))
		return { key: "fail", label: __("Failed"), detail: s.replace(/^Error:\s*/, "") };
	return { key: "new", label: __("New card") };
}

function idct_counts(frm, only) {
	const rows = (frm.doc.student_list || []).filter((r) => !only || only.has(r.student));
	const c = { total: rows.length, new: 0, has: 0, done: 0, fail: 0, no_photo: 0, with_card: 0 };
	rows.forEach((r) => {
		c[idct_status(r).key]++;
		if (!r.has_photo) c.no_photo++;
		if (r.current_id_card) c.with_card++;
	});
	// Mirrors IDCardGenerationTool._rows_to_process on the server.
	c.to_process = frm.doc.regenerate_existing ? c.total : c.new + c.fail;
	c.skipped = frm.doc.regenerate_existing ? 0 : c.has + c.done;
	return c;
}

class IDCardBulkConsole {
	constructor(frm) {
		this.frm = frm;
		this.filter = "all";
		this.query = "";
		this.limit = IDCT_PAGE_SIZE;
		this.preview_side = "front";
		this.preview_student = null;
		this.preview = null;
		this.photos = {};
		this.controls = {};
		this.selected = new Set();
		this.card_states = {};
	}

	get running() {
		return !!this.frm.__idc_run;
	}

	/** The selected students, or null when nothing is selected (= whole list). */
	get scope() {
		this.prune_selection();
		return this.selected.size ? this.selected : null;
	}

	prune_selection() {
		const present = new Set((this.frm.doc.student_list || []).map((r) => r.student));
		[...this.selected].forEach((s) => present.has(s) || this.selected.delete(s));
	}

	clear_selection() {
		this.selected.clear();
		this.refresh();
	}

	mount() {
		if (!document.getElementById("idct-css"))
			$(`<style id="idct-css">${IDCT_CSS}</style>`).appendTo("head");
		const $w = this.frm.fields_dict.wizard_html.$wrapper;
		$w.closest(".section-body").css("max-width", "none");
		$w.html(`
			<div class="idct">
				<div class="idct-head">
					<div>
						<h3>${__("Generate ID Cards")}</h3>
						<p>${__("Pick the students, choose a template, and generate print-ready cards in one go.")}</p>
					</div>
				</div>
				<div class="idct-banner-slot"></div>
				<div class="idct-layout">
					<div style="display:grid;gap:16px;min-width:0">
						<section class="idct-panel">
							<div class="idct-panel-head"><div class="idct-panel-title"><span class="idct-num" data-step="1">1</span>${__(
								"Who needs cards?"
							)}</div></div>
							<div class="idct-panel-body">
								<div class="idct-filters">
									<div data-control="academic_year"></div>
									<div data-control="program"></div>
									<div data-control="batch"></div>
									<div data-control="section"></div>
									<button class="btn btn-primary btn-sm" data-act="find">${__("Find students")}</button>
								</div>
								<div class="idct-addrow">
									<div data-control="add_student"></div>
									<span class="idct-hint">${__("or add one student by name")}</span>
								</div>
							</div>
						</section>
						<section class="idct-panel idct-export"></section>
						<section class="idct-panel">
							<div class="idct-toolbar"></div>
							<div class="idct-list"></div>
						</section>
					</div>
					<aside class="idct-side">
						<section class="idct-panel">
							<div class="idct-panel-head">
								<div class="idct-panel-title"><span class="idct-num" data-step="2">2</span>${__(
									"Card design"
								)}</div>
								<a class="idct-edit-template small" target="_blank" style="display:none">${__("Edit template")}</a>
							</div>
							<div class="idct-panel-body">
								<div data-control="id_card_template"></div>
								<div class="idct-preview"></div>
								<div class="idct-preview-meta">
									<span class="idct-preview-caption"></span>
									<div class="idct-seg">
										<button data-side="front">${__("Front")}</button>
										<button data-side="back">${__("Back")}</button>
									</div>
								</div>
							</div>
						</section>
						<section class="idct-panel">
							<div class="idct-panel-head"><div class="idct-panel-title"><span class="idct-num" data-step="3">3</span>${__(
								"Generate"
							)}</div></div>
							<div class="idct-panel-body">
								<div class="idct-grid2">
									<div data-control="issue_date"></div>
									<div data-control="expiry_date"></div>
								</div>
								<div class="idct-sides">
									<label data-flag-label="generate_front"><input type="checkbox" data-flag="generate_front"> ${__(
										"Front"
									)}</label>
									<label data-flag-label="generate_back"><input type="checkbox" data-flag="generate_back"> ${__(
										"Back"
									)}</label>
								</div>
								<label class="idct-switch">
									<div>${__("Regenerate existing cards")}<small>${__(
			"Re-render cards students already have, e.g. after a design change."
		)}</small></div>
									<input type="checkbox" data-flag="regenerate_existing">
								</label>
								<div class="idct-run"></div>
							</div>
						</section>
					</aside>
				</div>
			</div>`);
		this.$root = $w.find(".idct");
		this.make_controls();
		this.bind();
	}

	is_mounted() {
		return !!(this.$root && document.documentElement.contains(this.$root[0]));
	}

	make_controls() {
		const frm = this.frm;
		const make = (key, df) => {
			const control = frappe.ui.form.make_control({
				df: {
					fieldname: `idct_${key}`,
					...df,
					onchange: () => {
						const value = control.get_value() || null;
						if (df.on_value) return df.on_value(value, control);
						if ((frm.doc[key] || null) !== value) frm.set_value(key, value);
					},
				},
				parent: this.$root.find(`[data-control='${key}']`)[0],
				render_input: true,
			});
			control.refresh();
			this.controls[key] = control;
			return control;
		};
		make("academic_year", {
			fieldtype: "Link",
			options: "Academic Year",
			label: __("Academic Year"),
			placeholder: __("Any year"),
		});
		make("program", {
			fieldtype: "Link",
			options: "Programme",
			label: __("Programme"),
			placeholder: __("Any programme"),
		});
		make("batch", {
			fieldtype: "Link",
			options: "SLCM Batch",
			label: __("Batch"),
			placeholder: __("Any batch"),
		});
		make("section", {
			fieldtype: "Link",
			options: "Section",
			label: __("Section"),
			placeholder: __("Any section"),
		});
		make("add_student", {
			fieldtype: "Link",
			options: "Student Master",
			placeholder: __("Add a student…"),
			get_query: () => ({ filters: { student_status: "Active" } }),
			on_value: (value, control) => {
				if (!value) return;
				control.set_value("");
				this.add_student(value);
			},
		});
		make("id_card_template", {
			fieldtype: "Link",
			options: "ID Card Template",
			label: __("Template"),
			placeholder: __("Choose a template"),
			get_query: () => ({ filters: { card_type: "Student" } }),
		});
		make("issue_date", { fieldtype: "Date", label: __("Issue date") });
		make("expiry_date", {
			fieldtype: "Date",
			label: __("Valid till"),
			placeholder: __("Programme end"),
		});
	}

	sync_controls() {
		[
			"academic_year",
			"program",
			"batch",
			"section",
			"id_card_template",
			"issue_date",
			"expiry_date",
		].forEach((key) => {
			const control = this.controls[key];
			if (control && (control.get_value() || null) !== (this.frm.doc[key] || null)) {
				control.set_value(this.frm.doc[key] || "");
			}
		});
		this.$root.find("[data-flag]").each((_, el) => {
			el.checked = !!this.frm.doc[el.dataset.flag];
			$(el).closest("[data-flag-label]").toggleClass("on", el.checked);
		});
	}

	bind() {
		const $r = this.$root;
		$r.on("click", "[data-act='find']", () => this.find_students());
		$r.on("change", "[data-flag]", (e) => {
			this.frm.set_value(e.target.dataset.flag, e.target.checked ? 1 : 0);
			$(e.target).closest("[data-flag-label]").toggleClass("on", e.target.checked);
		});
		$r.on("click", "[data-filter]", (e) => {
			this.filter = $(e.currentTarget).data("filter");
			this.limit = IDCT_PAGE_SIZE;
			this.render_list();
		});
		$r.on(
			"input",
			".idct-search",
			frappe.utils.debounce((e) => {
				this.query = e.target.value.trim().toLowerCase();
				this.limit = IDCT_PAGE_SIZE;
				this.render_list(true);
			}, 150)
		);
		$r.on("click", "[data-act='more']", () => {
			this.limit += IDCT_PAGE_SIZE;
			this.render_list(true);
		});
		$r.on("click", "[data-act='clear']", () => {
			frappe.confirm(__("Remove all students from the list?"), () => {
				this.frm.doc.student_list = [];
				this.frm.dirty();
				this.selected.clear();
				this.preview_student = null;
				this.refresh();
				this.load_preview();
			});
		});
		$r.on("click", "[data-remove]", (e) => {
			e.stopPropagation();
			const name = $(e.currentTarget).data("remove");
			this.frm.doc.student_list = (this.frm.doc.student_list || []).filter(
				(r) => r.name !== name
			);
			this.frm.doc.student_list.forEach((r, i) => (r.idx = i + 1));
			this.frm.dirty();
			this.refresh();
			this.load_preview();
		});
		$r.on("click", "a[data-card], .idct-col-check", (e) => e.stopPropagation());
		$r.on("change", "[data-select]", (e) => {
			const student = String($(e.currentTarget).data("select"));
			if (e.currentTarget.checked) this.selected.add(student);
			else this.selected.delete(student);
			this.refresh_selection();
		});
		$r.on("change", "[data-select-all]", (e) => {
			const on = e.currentTarget.checked;
			this.visible_rows().forEach((r) =>
				on ? this.selected.add(r.student) : this.selected.delete(r.student)
			);
			this.refresh_selection();
		});
		$r.on("click", "[data-download-card]", (e) => {
			e.stopPropagation();
			const $b = $(e.currentTarget);
			idct_download_dialog(
				String($b.data("download-card")),
				String($b.data("student")),
				String($b.data("name"))
			);
		});
		$r.on("click", "[data-sel]", (e) => {
			const act = $(e.currentTarget).data("sel");
			const scope = this.scope;
			if (act === "clear") return this.clear_selection();
			if (act === "generate") return idct_generate(this.frm, scope);
			if (act === "sheet") return idct_print_sheet(this.frm, scope);
			if (act === "zip") return idct_zip(this.frm, scope);
			if (act === "printed") return idct_mark_printed(this.frm, scope);
			if (act === "remove") {
				frappe.confirm(
					__("Remove {0} selected student(s) from the list?", [this.selected.size]),
					() => {
						this.frm.doc.student_list = (this.frm.doc.student_list || []).filter(
							(r) => !this.selected.has(r.student)
						);
						this.frm.doc.student_list.forEach((r, i) => (r.idx = i + 1));
						this.selected.clear();
						this.frm.dirty();
						this.refresh();
						this.load_preview();
					}
				);
			}
		});
		$r.on("click", "tr[data-student]", (e) => {
			this.preview_student = String($(e.currentTarget).data("student"));
			this.render_list(true);
			this.load_preview();
		});
		$r.on("click", "[data-side]", (e) => {
			this.preview_side = $(e.currentTarget).data("side");
			this.render_preview();
		});
		$r.on("click", "[data-act='generate']", () => idct_generate(this.frm, this.scope));
		$r.on("click", "[data-out]", (e) => {
			const out = $(e.currentTarget).data("out");
			if (out === "sheet") idct_print_sheet(this.frm, this.scope);
			if (out === "zip") idct_zip(this.frm, this.scope);
			if (out === "printed") idct_mark_printed(this.frm, this.scope);
		});
	}

	refresh() {
		if (!this.is_mounted()) return;
		this.sync_controls();
		this.render_steps();
		this.render_banner();
		this.render_list();
		this.render_run();
		this.render_outputs();
		this.render_preview();
		this.load_photos();
		this.load_card_states();
	}

	render_steps() {
		const c = idct_counts(this.frm);
		const done = {
			1: c.total > 0,
			2: !!this.frm.doc.id_card_template,
			3: c.with_card > 0 && c.to_process === 0,
			4: false,
		};
		this.$root.find("[data-step]").each((_, el) => {
			const n = +el.dataset.step;
			$(el)
				.toggleClass("done", done[n])
				.html(done[n] ? idct_icon("check", 12) : n);
		});
		this.$root.find("[data-act='find'], [data-flag]").prop("disabled", this.running);
	}

	render_banner() {
		const run = this.frm.__idc_run;
		const last = this.frm.__idc_last;
		let html = "";
		if (run) {
			const pct = run.total ? Math.round((run.done / run.total) * 100) : 0;
			html = `<div class="idct-banner"><div class="idct-banner-text">
				<b>${__("Generating ID cards… {0} of {1}", [run.done, run.total])}</b>
				<small>${
					run.student_name
						? __("Last: {0}", [frappe.utils.escape_html(run.student_name)])
						: __("Starting the renderer…")
				}${run.failed ? " · " + __("{0} failed", [run.failed]) : ""} · ${__(
				"You can leave this page; it keeps running."
			)}</small>
				<div class="idct-progress"><div style="width:${pct}%"></div></div></div></div>`;
		} else if (last) {
			html = `<div class="idct-banner ${
				last.failed ? "bad" : "ok"
			}"><div class="idct-banner-text">
				<b>${
					last.failed
						? __("{0} generated, {1} failed", [last.generated, last.failed])
						: __("{0} ID card(s) generated", [last.generated])
				}</b>
				<small>${
					last.failed
						? __("Use the Failed filter below to see why.")
						: __("Print them from Print & export.")
				}</small></div>
				${
					last.log
						? `<a class="btn btn-default btn-sm" href="/app/id-card-generation-tool-log/${encodeURIComponent(
								last.log
						  )}">${__("View report")}</a>`
						: ""
				}
				<button class="btn btn-default btn-sm" data-dismiss-banner>${__("Dismiss")}</button></div>`;
		}
		const $slot = this.$root.find(".idct-banner-slot").html(html);
		$slot.find("[data-dismiss-banner]").on("click", () => {
			this.frm.__idc_last = null;
			this.render_banner();
		});
	}

	render_list(rows_only) {
		const rows = this.frm.doc.student_list || [];
		const c = idct_counts(this.frm);
		const esc = frappe.utils.escape_html;

		if (!rows_only) {
			const chip = (key, label, n) =>
				`<button class="idct-chip ${
					this.filter === key ? "active" : ""
				}" data-filter="${key}">${label} <b>${n}</b></button>`;
			this.$root
				.find(".idct-toolbar")
				.html(
					rows.length
						? [
								chip("all", __("All"), c.total),
								chip("new", __("New card"), c.new),
								chip("has", __("Has card"), c.has),
								chip("done", __("Generated"), c.done),
								c.fail ? chip("fail", __("Failed"), c.fail) : "",
								c.no_photo ? chip("no_photo", __("No photo"), c.no_photo) : "",
								`<input class="idct-search" type="search" placeholder="${__(
									"Search name or ID"
								)}" value="${esc(this.query)}">`,
								this.running
									? ""
									: `<button class="btn btn-default btn-xs" data-act="clear">${__(
											"Clear list"
									  )}</button>`,
						  ].join("")
						: `<div class="idct-panel-title"><span class="idct-num">${idct_icon(
								"users",
								12
						  )}</span>${__("Students")}</div>`
				);
		}

		const $list = this.$root.find(".idct-list");
		if (!rows.length) {
			$list.html(`<div class="idct-empty"><div class="idct-empty-ico">${idct_icon(
				"users",
				22
			)}</div>
				<b>${__("No students yet")}</b>${__(
				"Choose a year, programme, batch or section above and click Find students."
			)}</div>`);
			return;
		}

		const matches = this.visible_rows();
		const preview_student = this.current_preview_student();
		const run = this.frm.__idc_run;
		const all_on = matches.length > 0 && matches.every((r) => this.selected.has(r.student));
		const some_on = matches.some((r) => this.selected.has(r.student));

		const body = matches
			.slice(0, this.limit)
			.map((r) => {
				const st = idct_status(r);
				const photo = this.photos[r.student];
				const on = this.selected.has(r.student);
				const initials = (r.student_name || r.student)
					.split(/\s+/)
					.map((w) => w[0])
					.slice(0, 2)
					.join("")
					.toUpperCase();
				const avatar = photo
					? `<img class="idct-avatar" src="${esc(photo)}" alt="" loading="lazy">`
					: `<span class="idct-avatar ${r.has_photo ? "" : "missing"}" title="${
							r.has_photo ? "" : __("No photo: the default avatar will be printed")
					  }">${esc(initials)}</span>`;
				const queued = run && st.key === "new";
				const downloadable = r.current_id_card && (st.key === "done" || st.key === "has");
				return `<tr data-student="${esc(r.student)}" class="${
					r.student === preview_student ? "is-preview" : ""
				} ${on ? "is-selected" : ""}" title="${__(
					"Click to preview this student's card"
				)}">
					<td class="idct-col-check"><input type="checkbox" class="idct-check" data-select="${esc(
						r.student
					)}" ${on ? "checked" : ""} aria-label="${__("Select")}"></td>
					<td><div class="idct-person">${avatar}<div style="min-width:0"><div class="idct-person-name">${esc(
					r.student_name || r.student
				)}</div>
						<div class="idct-person-id">${esc(r.student)}${
					r.section ? ` · ${__("Section {0}", [esc(r.section)])}` : ""
				}</div></div></div></td>
					<td class="idct-col-card">${
						r.current_id_card
							? `<a class="idct-card-link" data-card href="/app/id-card-generation/${encodeURIComponent(
									r.current_id_card
							  )}" target="_blank">${esc(r.current_id_card)}</a>`
							: `<span class="text-muted">—</span>`
					}</td>
					<td><div class="idct-status-cell"><span class="idct-status ${queued ? "busy" : st.key}">${
					queued ? __("Queued") : st.label
				}</span>${
					downloadable
						? `<button class="idct-icon-btn dl" data-download-card="${esc(
								r.current_id_card
						  )}" data-student="${esc(r.student)}" data-name="${esc(
								r.student_name || r.student
						  )}" title="${__("Download card")}">${idct_icon("download", 15)}</button>`
						: ""
				}</div>
						${
							st.detail
								? `<div class="small text-muted" style="max-width:320px;white-space:normal;margin-top:3px">${esc(
										st.detail
								  )}</div>`
								: ""
						}</td>
					<td style="width:44px;text-align:right">${
						this.running
							? ""
							: `<button class="idct-icon-btn" data-remove="${esc(
									r.name
							  )}" title="${__("Remove from list")}">${idct_icon("x", 15)}</button>`
					}</td>
				</tr>`;
			})
			.join("");

		$list.html(
			matches.length
				? `<div class="idct-selbar-slot"></div>
					<div style="max-height:620px;overflow:auto"><table class="idct-table"><thead><tr>
					<th class="idct-col-check"><input type="checkbox" class="idct-check" data-select-all ${
						all_on ? "checked" : ""
					} title="${__("Select all shown")}" aria-label="${__(
						"Select all shown"
				  )}"></th>
					<th>${__("Student")}</th><th class="idct-col-card">${__("ID card")}</th><th>${__(
						"Status"
				  )}</th><th></th></tr></thead><tbody>${body}</tbody></table></div>
					${
						matches.length > this.limit
							? `<div class="idct-more"><button class="btn btn-default btn-xs" data-act="more">${__(
									"Show more ({0} left)",
									[matches.length - this.limit]
							  )}</button></div>`
							: ""
					}`
				: `<div class="idct-empty">${__("No students match this filter.")}</div>`
		);
		const head = $list.find("[data-select-all]")[0];
		if (head) head.indeterminate = some_on && !all_on;
		this.render_selbar();
	}

	visible_rows() {
		return (this.frm.doc.student_list || []).filter((r) => {
			if (this.filter === "no_photo") {
				if (r.has_photo) return false;
			} else if (this.filter !== "all" && idct_status(r).key !== this.filter) {
				return false;
			}
			return (
				!this.query ||
				`${r.student} ${r.student_name || ""} ${r.section || ""}`
					.toLowerCase()
					.includes(this.query)
			);
		});
	}

	/** Re-render the parts that depend on the selection, keeping scroll position. */
	refresh_selection() {
		const $scroll = this.$root.find(".idct-list > div[style*='overflow']");
		const top = $scroll.scrollTop();
		this.render_list(true);
		this.$root.find(".idct-list > div[style*='overflow']").scrollTop(top);
		this.render_run();
		this.render_outputs();
	}

	render_selbar() {
		const $slot = this.$root.find(".idct-selbar-slot");
		const scope = this.scope;
		if (!scope) {
			$slot.empty();
			return;
		}
		const c = idct_counts(this.frm, scope);
		const busy = this.running ? "disabled" : "";
		$slot.html(`<div class="idct-selbar">
			<span class="idct-selbar-count">${__("{0} selected", [scope.size])}</span>
			<button class="btn primary" data-sel="generate" ${
				busy || !c.to_process || !this.frm.doc.id_card_template ? "disabled" : ""
			}
				title="${
					c.to_process
						? ""
						: __(
								"Everyone selected already has a card. Turn on Regenerate to re-render them."
						  )
				}">
				${idct_icon("spark", 14)} ${
			c.to_process ? __("Generate {0}", [c.to_process]) : __("Generate")
		}</button>
			<button class="btn" data-sel="sheet" ${busy || !c.with_card ? "disabled" : ""}>${idct_icon(
			"printer",
			14
		)} ${__("Print sheet")}</button>
			<button class="btn" data-sel="zip" ${busy || !c.with_card ? "disabled" : ""}>${idct_icon(
			"download",
			14
		)} ${__("Download")}</button>
			<button class="btn" data-sel="printed" ${busy || !c.with_card ? "disabled" : ""}>${idct_icon(
			"check",
			14
		)} ${__("Mark printed")}</button>
			<button class="btn" data-sel="remove" ${busy}>${idct_icon("trash", 14)} ${__("Remove")}</button>
			<span class="idct-selbar-spacer"></span>
			<button class="idct-link" data-sel="clear">${__("Clear selection")}</button>
		</div>`);
	}

	render_run() {
		const scope = this.scope;
		const c = idct_counts(this.frm, scope);
		const doc = this.frm.doc;
		const run = this.frm.__idc_run;
		let reason = "";
		if (!c.total) reason = scope ? __("Select students first.") : __("Add students first.");
		else if (!doc.id_card_template) reason = __("Choose a template first.");
		else if (!doc.issue_date) reason = __("Set the issue date.");
		else if (!doc.generate_front && !doc.generate_back)
			reason = __("Select the front, the back, or both.");
		else if (!c.to_process)
			reason = scope
				? __("Everyone selected already has a card. Turn on Regenerate to re-render them.")
				: __("Everyone already has a card. Turn on Regenerate to re-render them.");

		const line = (label, value, cls = "") =>
			`<div class="${cls}"><span>${label}</span><span>${value}</span></div>`;
		this.$root.find(".idct-run").html(`
			${idct_scope_note(scope)}
			<div class="idct-summary" style="margin-top:12px">
				${line(doc.regenerate_existing ? __("Cards to render") : __("New cards"), c.to_process)}
				${c.skipped ? line(__("Skipped (already have a card)"), c.skipped) : ""}
				${c.no_photo ? line(__("Without a photo"), c.no_photo, "warn") : ""}
			</div>
			<button class="btn btn-primary idct-go" data-act="generate" ${run || reason ? "disabled" : ""}>
				${
					run
						? __("Generating… {0}/{1}", [run.done, run.total])
						: c.to_process
						? scope
							? __("Generate {0} selected", [c.to_process])
							: __("Generate {0} card(s)", [c.to_process])
						: __("Generate cards")
				}
			</button>
			<div class="idct-note">${
				run
					? __("Running in the background.")
					: reason || __("Runs in the background; you can keep working.")
			}</div>`);
	}

	/** Printable cards in scope. Cancelled/expired cards are left out, as on the server. */
	output_counts(scope) {
		const out = { ready: 0, printed: 0, unprinted: 0, void: 0, known: 0 };
		[...new Set(this.scoped_cards(scope))].forEach((n) => {
			const st = this.card_states[n];
			if (st) out.known++;
			if (st === "Cancelled" || st === "Expired") {
				out.void++;
				return;
			}
			out.ready++;
			if (st === "Printed") out.printed++;
			if (st === "Generated") out.unprinted++;
		});
		return out;
	}

	render_outputs() {
		const scope = this.scope;
		const o = this.output_counts(scope);
		const c = { with_card: o.ready };
		const known = { length: o.known };
		const printed = o.printed;
		const unprinted = o.unprinted;
		const busy = this.running;
		const $panel = this.$root.find(".idct-export");
		const head = `<div class="idct-export-head">
				<div class="idct-panel-title"><span class="idct-num ${
					printed && !unprinted ? "done" : ""
				}" data-step="4">${printed && !unprinted ? idct_icon("check", 12) : 4}</span>${__(
			"Print & export"
		)}</div>
				${
					c.with_card
						? `<div class="idct-export-meta">
					<span class="idct-pill"><b>${c.with_card}</b> ${__("card(s) ready")}</span>
					${known.length ? `<span class="idct-pill ok"><b>${printed}</b> ${__("printed")}</span>` : ""}
					${
						unprinted
							? `<span class="idct-pill warn"><b>${unprinted}</b> ${__(
									"not printed yet"
							  )}</span>`
							: ""
					}
					${
						o.void
							? `<span class="idct-pill" title="${__(
									"Cancelled and expired cards are left out of print sheets and downloads."
							  )}"><b>${o.void}</b> ${__("cancelled / expired")}</span>`
							: ""
					}
				</div>`
						: ""
				}
			</div>`;

		if (!c.with_card) {
			$panel.html(`${head}${idct_scope_note(scope)}
				<div class="idct-export-empty">${idct_icon("printer", 18)}<span>${
				o.void
					? __(
							"These cards are cancelled or expired, so there is nothing to print. Generate new cards first."
					  )
					: scope
					? __("None of the selected students has a card yet. Generate them first.")
					: __("Print sheets and image downloads appear here once cards are generated.")
			}</span></div>`);
			return;
		}
		const off = busy ? "disabled" : "";
		const layout_hint = this.preview && this.preview.orientation === "vertical" ? 3 : 4;
		$panel.html(`${head}${idct_scope_note(scope)}
			<div class="idct-export-grid">
				<button class="idct-action" data-out="sheet" ${off}>
					<span class="idct-action-ico blue">${idct_icon("printer", 18)}</span>
					<span><b>${__("Print sheet")}</b><small>${__(
			"A4 PDF at 300 DPI with crop marks · about {0} card(s) per page",
			[layout_hint]
		)}</small></span>
				</button>
				<button class="idct-action" data-out="zip" ${off}>
					<span class="idct-action-ico violet">${idct_icon("archive", 18)}</span>
					<span><b>${__("Download images")}</b><small>${__("ZIP of front and back PNGs for {0} card(s)", [
			c.with_card,
		])}</small></span>
				</button>
				<button class="idct-action" data-out="printed" ${
					off || (known.length && !unprinted ? "disabled" : "")
				}>
					<span class="idct-action-ico green">${idct_icon("check", 18)}</span>
					<span><b>${__("Mark as printed")}</b><small>${
			known.length && !unprinted
				? __("All of these cards are already marked printed")
				: __("After the cards come off the printer")
		}</small></span>
				</button>
			</div>`);
	}

	scoped_cards(scope) {
		return (this.frm.doc.student_list || [])
			.filter((r) => r.current_id_card && (!scope || scope.has(r.student)))
			.map((r) => r.current_id_card);
	}

	/** Current status of each listed card, so Print & export can show what's printed. */
	load_card_states(force) {
		if (force) this.card_states = {};
		const missing = [...new Set(this.scoped_cards(null))].filter(
			(n) => !(n in this.card_states)
		);
		if (!missing.length) return;
		missing.forEach((n) => (this.card_states[n] = null));
		frappe.db
			.get_list("ID Card Generation", {
				filters: { name: ["in", missing] },
				fields: ["name", "card_status"],
				limit: missing.length,
			})
			.then((list) => {
				list.forEach((c) => (this.card_states[c.name] = c.card_status));
				this.render_outputs();
			});
	}

	load_photos() {
		const missing = (this.frm.doc.student_list || [])
			.filter((r) => r.has_photo && !(r.student in this.photos))
			.map((r) => r.student);
		if (!missing.length) return;
		missing.forEach((s) => (this.photos[s] = null));
		frappe.db
			.get_list("Student Master", {
				filters: { name: ["in", missing] },
				fields: ["name", "passport_size_photo"],
				limit: missing.length,
			})
			.then((list) => {
				list.forEach((s) => (this.photos[s.name] = s.passport_size_photo || null));
				this.render_list(true);
			});
	}

	current_preview_student() {
		const rows = this.frm.doc.student_list || [];
		if (rows.some((r) => r.student === this.preview_student)) return this.preview_student;
		return rows.length ? rows[0].student : null;
	}

	load_preview() {
		const frm = this.frm;
		const template = frm.doc.id_card_template;
		this.$root
			.find(".idct-edit-template")
			.toggle(!!template)
			.attr(
				"href",
				template ? `/app/id-card-template/${encodeURIComponent(template)}` : "#"
			);
		if (!template) {
			this.preview = null;
			this.render_preview();
			return;
		}
		const student = this.current_preview_student();
		const key = `${template}|${student || ""}`;
		if (this.preview && this.preview.key === key && !this.preview.error) {
			this.render_preview();
			return;
		}
		const id = (this._preview_id = (this._preview_id || 0) + 1);
		this.preview = { key, loading: true };
		this.render_preview();
		frm.call({ doc: frm.doc, method: "render_preview", args: { student } })
			.then((r) => {
				if (id !== this._preview_id) return;
				this.preview = { key, ...(r.message || {}) };
				this.render_preview();
			})
			.catch(() => {
				if (id !== this._preview_id) return;
				this.preview = { key, error: true };
				this.render_preview();
			});
	}

	render_preview() {
		const p = this.preview;
		const $box = this.$root.find(".idct-preview");
		const $cap = this.$root.find(".idct-preview-caption");
		const $front = this.$root.find(".idct-seg button[data-side='front']");
		const $back = this.$root.find(".idct-seg button[data-side='back']");
		const ready = p && !p.loading && !p.error && p.front;
		$front.prop("disabled", !ready);
		$back.prop("disabled", !(ready && p.back));
		const side = ready && p[this.preview_side] ? this.preview_side : "front";
		$front.toggleClass("active", side === "front");
		$back.toggleClass("active", side === "back");

		if (!this.frm.doc.id_card_template) {
			$box.html(
				`<div class="text-muted small">${__("Choose a template to see the card.")}</div>`
			);
			$cap.text("");
		} else if (!p || p.loading) {
			$box.html('<div class="idct-skeleton"></div>');
			$cap.text(__("Rendering…"));
		} else if (!ready) {
			$box.html(
				`<div class="text-muted small">${__(
					"Preview unavailable. Check the template design."
				)}</div>`
			);
			$cap.text("");
		} else {
			$box.html(`<img src="${p[side]}" alt="${side}">`);
			$cap.text(p.sample ? __("Sample data") : __("Preview: {0}", [p.person || ""]));
		}
	}

	find_students() {
		const frm = this.frm;
		if (!(frm.doc.academic_year || frm.doc.program || frm.doc.batch || frm.doc.section)) {
			frappe.show_alert({
				message: __("Pick a year, programme, batch or section first."),
				indicator: "orange",
			});
			return;
		}
		const go = () =>
			idct_saving_call(frm, {
				doc: frm.doc,
				method: "get_students",
				freeze: true,
				freeze_message: __("Finding students…"),
			}).then((r) => {
				this.filter = "all";
				this.query = "";
				this.selected.clear();
				this.preview_student = null;
				frm.__idc_last = null;
				this.refresh();
				this.load_preview();
				const n = r.message || 0;
				frappe.show_alert({
					message: n
						? __("{0} student(s) found.", [n])
						: __("No active students match these filters."),
					indicator: n ? "green" : "orange",
				});
			});
		if ((frm.doc.student_list || []).length) {
			frappe.confirm(
				__("Replace the current list with the students matching these filters?"),
				go
			);
		} else {
			go();
		}
	}

	async load_students(students, template) {
		const frm = this.frm;
		const rows = await frappe.xcall(
			"slcm.slcm.doctype.id_card_generation_tool.id_card_generation_tool.get_student_rows",
			{ students }
		);
		frm.doc.student_list = [];
		rows.forEach((row) => frm.add_child("student_list", row));
		if (template) frm.set_value("id_card_template", template);
		frm.dirty();
		this.filter = "all";
		this.query = "";
		this.selected.clear();
		this.preview_student = null;
		frm.__idc_last = null;
		this.refresh();
		this.load_preview();
		frappe.show_alert({
			message: __("{0} student(s) loaded to retry.", [rows.length]),
			indicator: "blue",
		});
	}

	async add_student(student) {
		const frm = this.frm;
		if ((frm.doc.student_list || []).some((r) => r.student === student)) {
			frappe.show_alert({
				message: __("{0} is already in the list.", [student]),
				indicator: "blue",
			});
			return;
		}
		const row = await frappe.xcall(
			"slcm.slcm.doctype.id_card_generation_tool.id_card_generation_tool.get_student_row",
			{
				student,
			}
		);
		frm.add_child("student_list", row);
		frm.dirty();
		this.refresh();
		this.load_preview();
		frappe.show_alert({
			message: __("Added {0}.", [frappe.utils.escape_html(row.student_name || student)]),
			indicator: "green",
		});
	}
}

/** "Applies to N selected" banner shown in the side panels. */
function idct_scope_note(scope) {
	return scope
		? `<div class="idct-scope"><span>${__("Applies to {0} selected student(s)", [
				scope.size,
		  ])}</span><button data-sel="clear">${__("Use whole list")}</button></div>`
		: "";
}

/**
 * Call a tool method that saves the tool on the server. Frappe would otherwise
 * treat the realtime update from our own save as someone else's edit and show
 * "This form has been modified after you have loaded it".
 */
function idct_saving_call(frm, opts) {
	frappe.ui.form.is_saving = true;
	// frm.call returns a jQuery jqXHR: it has .always(), not .finally().
	const request = frm.call(opts);
	request.always(() => {
		frappe.ui.form.is_saving = false;
	});
	return request;
}

const idct_students_arg = (scope) => (scope ? JSON.stringify([...scope]) : null);

function idct_generate(frm, scope) {
	if (frm.__idc_run) return;
	const c = idct_counts(frm, scope);
	if (!frm.doc.id_card_template || !c.to_process) return;
	const lines = [
		__(
			scope
				? "Generate <b>{0}</b> card(s) for the selected students with the <b>{1}</b> template?"
				: "Generate <b>{0}</b> card(s) with the <b>{1}</b> template?",
			[c.to_process, frappe.utils.escape_html(frm.doc.id_card_template)]
		),
	];
	if (c.no_photo)
		lines.push(
			__("{0} student(s) have no photo; the default avatar will be printed.", [c.no_photo])
		);
	if (c.skipped)
		lines.push(__("{0} student(s) who already have a card will be skipped.", [c.skipped]));
	frappe.confirm(lines.join("<br><br>"), () => {
		idct_saving_call(frm, {
			doc: frm.doc,
			method: "generate_cards",
			args: { students: idct_students_arg(scope) },
		}).then((r) => {
			if (!r.message) return;
			frm.__idc_last = null;
			frm.__idc_run = { total: r.message.queued, done: 0 };
			if (frm.idct) frm.idct.refresh();
		});
	});
}

const IDCT_SHEET_CSS = `
	.idct-layouts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
	.idct-layout-opt { position: relative; border: 2px solid var(--border-color, #e2e6ea); border-radius: 12px; padding: 14px; cursor: pointer;
		background: var(--fg-color, #fff); text-align: left; transition: border-color .15s, background .15s; }
	.idct-layout-opt:hover { border-color: var(--gray-400, #9ca3af); }
	.idct-layout-opt.on { border-color: var(--idct-maroon); background: var(--idct-maroon-soft); }
	.idct-layout-opt svg { display: block; margin: 0 auto 12px; }
	.idct-layout-opt b { display: block; font-size: 13.5px; }
	.idct-layout-opt small { display: block; color: var(--text-muted, #6b7280); font-size: 12px; margin-top: 3px; line-height: 1.4; }
	.idct-layout-radio { position: absolute; top: 10px; right: 10px; width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--border-color, #cbd2d9); }
	.idct-layout-opt.on .idct-layout-radio { border: 5px solid var(--idct-maroon); }
	.idct-sheet-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 16px; padding: 12px 14px; border-radius: 10px;
		background: var(--subtle-fg, #f4f5f7); font-size: 13px; }
	.idct-sheet-row label { display: flex; align-items: center; gap: 8px; margin: 0; cursor: pointer; font-weight: 400; }
	.idct-sheet-row input { width: 16px; height: 16px; margin: 0; }
	.idct-sheet-row input:checked { background-color: var(--idct-maroon-solid); border-color: var(--idct-maroon-solid); }
	.idct-sheet-row input { accent-color: var(--idct-maroon-solid); }
	.idct-sheet-summary { font-variant-numeric: tabular-nums; color: var(--text-muted, #6b7280); }
	.idct-sheet-summary b { color: var(--text-color, #1f2937); }
	.idct-sheet-note { margin-top: 10px; font-size: 12px; color: var(--text-muted, #6b7280); }
	.idct-ready { text-align: center; padding: 8px 4px 4px; }
	.idct-ready-ico { width: 52px; height: 52px; border-radius: 50%; margin: 0 auto 12px; display: flex; align-items: center; justify-content: center;
		background: rgba(34,197,94,.12); color: var(--green-700, #15803d); }
	.idct-ready h4 { margin: 0 0 4px; font-size: 16px; font-weight: 600; }
	.idct-ready p { margin: 0; color: var(--text-muted, #6b7280); font-size: 13px; }
	.idct-ready-tips { margin: 16px 0 0; padding: 12px 14px; border-radius: 10px; background: var(--subtle-fg, #f4f5f7); text-align: left; font-size: 12.5px;
		color: var(--text-muted, #6b7280); list-style: none; display: grid; gap: 4px; }
`;

// Mini page diagrams for the two sheet layouts.
const IDCT_SHEET_SVG = {
	pairs: `<svg width="64" height="88" viewBox="0 0 64 88"><rect x="1" y="1" width="62" height="86" rx="3" fill="none" stroke="currentColor" opacity=".35"/>
		${[0, 1, 2, 3]
			.map(
				(i) =>
					`<rect x="8" y="${
						8 + i * 19
					}" width="22" height="14" rx="2" fill="#920c24" opacity=".8"/><rect x="34" y="${
						8 + i * 19
					}" width="22" height="14" rx="2" fill="#94a3b8"/>`
			)
			.join("")}</svg>`,
	duplex: `<svg width="120" height="88" viewBox="0 0 120 88"><rect x="1" y="1" width="54" height="86" rx="3" fill="none" stroke="currentColor" opacity=".35"/>
		<rect x="65" y="1" width="54" height="86" rx="3" fill="none" stroke="currentColor" opacity=".35"/>
		${[0, 1, 2, 3]
			.map(
				(i) =>
					`<rect x="7" y="${
						8 + i * 19
					}" width="19" height="13" rx="2" fill="#920c24" opacity=".8"/><rect x="30" y="${
						8 + i * 19
					}" width="19" height="13" rx="2" fill="#920c24" opacity=".8"/><rect x="71" y="${
						8 + i * 19
					}" width="19" height="13" rx="2" fill="#94a3b8"/><rect x="94" y="${
						8 + i * 19
					}" width="19" height="13" rx="2" fill="#94a3b8"/>`
			)
			.join("")}</svg>`,
};

/** Rough page count, using the same grid as the server's _layout_pages. */
function idct_estimate_pages(cards, layout, portrait) {
	if (!cards) return 0;
	if (layout === "duplex") return Math.ceil(cards / (portrait ? 9 : 8)) * 2;
	return Math.ceil(cards / (portrait ? 3 : 4));
}

function idct_print_sheet(frm, scope) {
	if (!document.getElementById("idct-sheet-css"))
		$(`<style id="idct-sheet-css">${IDCT_SHEET_CSS}</style>`).appendTo("head");
	const c = {
		with_card: frm.idct
			? frm.idct.output_counts(scope).ready
			: idct_counts(frm, scope).with_card,
	};
	const portrait = !!(
		frm.idct &&
		frm.idct.preview &&
		frm.idct.preview.orientation === "vertical"
	);
	const state = { layout: "pairs", crop_marks: true };
	const d = new frappe.ui.Dialog({
		title: __("Create print sheet"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
		primary_action_label: __("Create PDF"),
		primary_action() {
			d.hide();
			frm.call({
				doc: frm.doc,
				method: "generate_print_layout",
				args: {
					layout: state.layout,
					crop_marks: state.crop_marks ? 1 : 0,
					students: idct_students_arg(scope),
				},
				freeze: true,
				freeze_message: __("Laying out {0} card(s)…", [c.with_card]),
			}).then((r) => {
				if (r.message) idct_sheet_ready(frm, scope, r.message);
			});
		},
	});
	const render = () => {
		const pages = idct_estimate_pages(c.with_card, state.layout, portrait);
		const opt = (key, title, sub) => `<div class="idct-layout-opt ${
			state.layout === key ? "on" : ""
		}" data-layout="${key}" role="radio"
			aria-checked="${state.layout === key}" tabindex="0"><span class="idct-layout-radio"></span>${
			IDCT_SHEET_SVG[key]
		}<b>${title}</b><small>${sub}</small></div>`;
		d.fields_dict.body.$wrapper.html(`
			<div class="idct-layouts">
				${opt(
					"pairs",
					__("Front and back side by side"),
					__(
						"For single-sided printers. Cut each card out and fold or laminate the pair."
					)
				)}
				${opt(
					"duplex",
					__("Double-sided (duplex)"),
					__(
						"A page of fronts, then a page of mirrored backs. Print double-sided, flip on the long edge."
					)
				)}
			</div>
			<div class="idct-sheet-row">
				<label><input type="checkbox" data-crop ${state.crop_marks ? "checked" : ""}> ${__(
			"Crop marks for cutting"
		)}</label>
				<span class="idct-sheet-summary">${__("<b>{0}</b> card(s) on about <b>{1}</b> A4 page(s)", [
					c.with_card,
					pages,
				])}</span>
			</div>
			<div class="idct-sheet-note">${
				scope
					? __("Only the selected students' cards are included.")
					: __("Every generated card in the list is included.")
			} ${__("Each card is recorded in the ID Card Print Log.")}</div>`);
	};
	const $b = d.fields_dict.body.$wrapper;
	$b.on("click keydown", "[data-layout]", (e) => {
		if (e.type === "keydown" && e.key !== " " && e.key !== "Enter") return;
		e.preventDefault();
		state.layout = $(e.currentTarget).data("layout");
		render();
	});
	$b.on("change", "[data-crop]", (e) => {
		state.crop_marks = e.target.checked;
		render();
	});
	d.show();
	render();
}

function idct_sheet_ready(frm, scope, result) {
	// Offer "mark as printed" only for cards that aren't marked yet.
	const unprinted = frm.idct ? frm.idct.output_counts(scope).unprinted : result.cards;
	const opts = {
		title: __("Print sheet ready"),
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
		primary_action_label: __("Open PDF"),
		primary_action() {
			window.open(result.file_url, "_blank");
		},
	};
	if (unprinted) {
		opts.secondary_action_label = __("Mark {0} as printed", [unprinted]);
		opts.secondary_action = () => {
			d.hide();
			idct_mark_printed(frm, scope);
		};
	}
	const d = new frappe.ui.Dialog(opts);
	d.fields_dict.body.$wrapper.html(`
		<div class="idct-ready">
			<div class="idct-ready-ico">${idct_icon("check", 24)}</div>
			<h4>${__("{0} card(s) on {1} page(s)", [result.cards, result.pages])}</h4>
			<p>${__("Open the PDF and print it on A4.")}</p>
			<ul class="idct-ready-tips">
				<li>• ${__("Print at <b>100% / Actual size</b>. “Fit to page” shrinks the cards.")}</li>
				<li>• ${__("Use card stock or a PVC card printer for the best result.")}</li>
				<li>• ${__("After printing, mark the cards as printed so they're tracked.")}</li>
			</ul>
		</div>`);
	d.show();
}

const IDCT_DL_CSS = `
	.idct-dl-tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
	.idct-dl-tile { position: relative; border: 2px solid var(--border-color, #e2e6ea); border-radius: 12px; padding: 12px; cursor: pointer;
		background: var(--subtle-fg, #f4f5f7); text-align: center; transition: border-color .15s, background .15s; }
	.idct-dl-tile:hover { border-color: var(--gray-400, #9ca3af); }
	.idct-dl-tile.on { border-color: var(--idct-maroon); background: var(--idct-maroon-soft); }
	.idct-dl-tile.off { opacity: .45; cursor: default; }
	.idct-dl-tile img { display: block; margin: 0 auto; max-width: 100%; max-height: 210px; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.1), 0 8px 20px rgba(15,23,42,.14); }
	.idct-dl-tile .idct-dl-none { height: 150px; display: flex; align-items: center; justify-content: center; color: var(--text-muted, #6b7280); font-size: 12.5px; }
	.idct-dl-tick { position: absolute; top: 8px; right: 8px; width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--border-color, #cbd2d9);
		background: var(--fg-color, #fff); color: #fff; display: flex; align-items: center; justify-content: center; }
	.idct-dl-tile.on .idct-dl-tick { background: var(--idct-maroon-solid); border-color: var(--idct-maroon-solid); }
	.idct-dl-label { margin-top: 10px; font-size: 12.5px; font-weight: 600; }
	.idct-dl-meta { margin-top: 12px; font-size: 12px; color: var(--text-muted, #6b7280); }
`;

/** Download a site file under a readable name. Private files come with the
 * server's stored name in Content-Disposition, which would override `download`. */
function idct_save_file(file_url, filename) {
	fetch(frappe.utils.get_file_link(file_url), { credentials: "same-origin" })
		.then((res) => {
			if (!res.ok) throw new Error(res.statusText);
			return res.blob();
		})
		.then((blob) => {
			const url = URL.createObjectURL(blob);
			const a = document.createElement("a");
			a.href = url;
			a.download = filename;
			document.body.appendChild(a);
			a.click();
			a.remove();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
		})
		.catch(() => frappe.msgprint(__("Could not download {0}.", [filename])));
}

async function idct_download_dialog(card, student, name) {
	if (!document.getElementById("idct-dl-css"))
		$(`<style id="idct-dl-css">${IDCT_DL_CSS}</style>`).appendTo("head");
	const r = await frappe.db.get_value("ID Card Generation", card, [
		"front_id_image",
		"back_id_image",
		"card_status",
	]);
	const info = r.message || {};
	const sides = [
		{ key: "front", label: __("Front"), url: info.front_id_image },
		{ key: "back", label: __("Back"), url: info.back_id_image },
	];
	const chosen = new Set(sides.filter((x) => x.url).map((x) => x.key));
	if (!chosen.size) {
		frappe.msgprint(__("This card has no images yet. Generate it first."));
		return;
	}
	const d = new frappe.ui.Dialog({
		title: __("Download ID card"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
		primary_action_label: __("Download"),
		primary_action() {
			const picked = sides.filter((x) => chosen.has(x.key) && x.url);
			d.hide();
			picked.forEach((x, i) => {
				// Stagger so the browser accepts several downloads from one click.
				setTimeout(() => idct_save_file(x.url, `${student}_${x.label}.png`), i * 400);
			});
		},
		secondary_action_label: __("Open card"),
		secondary_action() {
			window.open(`/app/id-card-generation/${encodeURIComponent(card)}`, "_blank");
		},
	});
	const esc = frappe.utils.escape_html;
	const render = () => {
		d.fields_dict.body.$wrapper.html(`
			<div class="idct-dl-tiles">${sides
				.map(
					(x) => `<div class="idct-dl-tile ${
						x.url ? (chosen.has(x.key) ? "on" : "") : "off"
					}" data-dl-side="${x.key}" role="checkbox"
						aria-checked="${chosen.has(x.key)}" tabindex="0">
						${
							x.url
								? `<span class="idct-dl-tick">${
										chosen.has(x.key) ? idct_icon("check", 12) : ""
								  }</span>`
								: ""
						}
						${
							x.url
								? `<img src="${esc(frappe.utils.get_file_link(x.url))}" alt="${
										x.label
								  }">`
								: `<div class="idct-dl-none">${__("No {0} side", [
										x.label.toLowerCase(),
								  ])}</div>`
						}
						<div class="idct-dl-label">${x.label}</div>
					</div>`
				)
				.join("")}</div>
			<div class="idct-dl-meta">${esc(name)} · ${esc(student)} · ${esc(card)} — ${__(
			"PNG, 300 DPI, CR80 size"
		)}</div>`);
		const n = chosen.size;
		d.get_primary_btn()
			.prop("disabled", !n)
			.text(
				n === 2
					? __("Download both")
					: n === 1
					? __("Download {0}", [sides.find((x) => chosen.has(x.key)).label])
					: __("Select a side")
			);
	};
	d.fields_dict.body.$wrapper.on("click keydown", "[data-dl-side]", (e) => {
		if (e.type === "keydown" && e.key !== " " && e.key !== "Enter") return;
		e.preventDefault();
		const key = $(e.currentTarget).data("dl-side");
		if (!sides.find((x) => x.key === key).url) return;
		if (chosen.has(key)) chosen.delete(key);
		else chosen.add(key);
		render();
	});
	d.show();
	render();
}

function idct_zip(frm, scope) {
	frm.call({
		doc: frm.doc,
		method: "download_zip",
		args: { students: idct_students_arg(scope) },
		freeze: true,
		freeze_message: __("Packing images…"),
	}).then((r) => {
		if (r.message) idct_save_file(r.message, `ID_Cards_${frappe.datetime.get_today()}.zip`);
	});
}

function idct_mark_printed(frm, scope) {
	frappe.confirm(
		scope
			? __(
					"Mark the selected students' generated cards as <b>Printed</b>? Do this after the cards are physically printed."
			  )
			: __(
					"Mark every generated card in this list as <b>Printed</b>? Do this after the cards are physically printed."
			  ),
		() => {
			frm.call({
				doc: frm.doc,
				method: "mark_as_printed",
				args: { students: idct_students_arg(scope) },
				freeze: true,
			}).then((r) => {
				frappe.show_alert({
					message: __("{0} card(s) marked as printed.", [r.message || 0]),
					indicator: "green",
				});
				if (frm.idct) frm.idct.load_card_states(true);
			});
		}
	);
}

frappe.ui.form.on("ID Card Generation Tool", {
	onload(frm) {
		frappe.realtime.off("id_card_tool_progress");
		frappe.realtime.on("id_card_tool_progress", (data) => {
			const f = window.cur_frm;
			if (!f || f.doctype !== "ID Card Generation Tool") return;
			if (data.finished) {
				f.__idc_run = null;
				f.__idc_last = { generated: data.generated, failed: data.failed, log: data.log };
				f.reload_doc();
				return;
			}
			f.__idc_run = data;
			const row = (f.doc.student_list || []).find((r) => r.student === data.student);
			if (row) row.status = data.status;
			if (f.idct) f.idct.refresh();
		});
	},

	refresh(frm) {
		frm.disable_save();
		frm.toggle_display(IDCT_HIDDEN_SECTIONS, false);
		frm.page.wrapper.find(".layout-side-section").hide();
		frm.page.clear_primary_action();
		frm.page.clear_menu();
		frm.page.add_menu_item(__("Reset everything"), () => {
			frappe.confirm(__("Clear the filters, template and student list?"), () =>
				frm.call("reset_filters").then(() => frm.reload_doc())
			);
		});
		frm.page.add_menu_item(__("Generation history"), () =>
			frappe.set_route("List", "ID Card Generation Tool Log")
		);

		if (slcm.id_card.pending_tool_template) {
			frm.set_value("id_card_template", slcm.id_card.pending_tool_template);
			slcm.id_card.pending_tool_template = null;
		} else if (!frm.doc.id_card_template) {
			frappe.db
				.get_value("ID Card Template", { card_type: "Student", is_default: 1 }, "name")
				.then((r) => {
					if (r.message && r.message.name && !frm.doc.id_card_template)
						frm.set_value("id_card_template", r.message.name);
				});
		}

		if (!frm.idct || frm.idct.frm !== frm || !frm.idct.is_mounted()) {
			frm.idct = new IDCardBulkConsole(frm);
			frm.idct.mount();
		}

		// Handed over from a Tool Log's "Retry failed students".
		const pending = slcm.id_card.pending_tool_students;
		if (pending && pending.students && pending.students.length) {
			slcm.id_card.pending_tool_students = null;
			frm.idct.load_students(pending.students, pending.template);
		}
		frm.idct.refresh();
		frm.idct.load_preview();
		frm.call("get_run_status").then((r) => {
			frm.__idc_run = r.message || null;
			frm.idct.refresh();
		});
	},

	id_card_template(frm) {
		if (!frm.idct) return;
		frm.idct.refresh();
		frm.idct.load_preview();
	},
	issue_date: (frm) => frm.idct && frm.idct.refresh(),
	expiry_date: (frm) => frm.idct && frm.idct.refresh(),
	generate_front: (frm) => frm.idct && frm.idct.refresh(),
	generate_back: (frm) => frm.idct && frm.idct.refresh(),
	regenerate_existing: (frm) => frm.idct && frm.idct.refresh(),
});
