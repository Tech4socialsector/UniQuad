// Read-only record of one print action. The page renders its own summary and
// a paginated card list into `printed_images`; the standard fields and the
// Cards grid stay as the stored record but are hidden, so a run with hundreds
// of cards stays a short, fast page.
const IDPL_HIDDEN_FIELDS = [
	"bulk_print_id",
	"print_action_type",
	"print_layout",
	"print_type",
	"total_cards_in_bulk",
	"printed_on",
	"printed_by",
	"academic_year",
	"department",
	"program",
	"batch",
	"section_break_cards",
	"cards",
];
const IDPL_PAGE_SIZE = 25;

const IDPL_CSS = `
	:root { --idpl-maroon: #920c24; --idpl-maroon-soft: rgba(146,12,36,.07); --idpl-maroon-mid: rgba(146,12,36,.14); --idpl-maroon-solid: #920c24;
		--idpl-green: #15803d; --idpl-green-soft: rgba(34,197,94,.12); }
	[data-theme="dark"] { --idpl-maroon: #f08da0; --idpl-maroon-soft: rgba(214,74,102,.14); --idpl-maroon-mid: rgba(214,74,102,.26);
		--idpl-green: #4ade80; --idpl-green-soft: rgba(74,222,128,.14); }
	.idpl { --b: var(--border-color, #e2e6ea); --m: var(--text-muted, #6b7280); --s: var(--subtle-fg, #f4f5f7); --bg: var(--fg-color, #fff);
		--t: var(--text-color, #1f2937); --a: var(--idpl-maroon); --a-soft: var(--idpl-maroon-soft); color: var(--t); display: grid; gap: 16px; }
	.idpl * { box-sizing: border-box; }
	.idpl-panel { background: var(--bg); border: 1px solid var(--b); border-radius: 14px; overflow: hidden; }

	.idpl-head { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; padding: 20px 22px; border-left: 4px solid var(--idpl-maroon-solid); }
	.idpl-head-main { flex: 1 1 320px; min-width: 0; }
	.idpl-eyebrow { font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--a); }
	.idpl-head h3 { margin: 4px 0 6px; font-size: 21px; font-weight: 600; letter-spacing: -.01em; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
	.idpl-pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 11px; border-radius: 99px; font-size: 12px; font-weight: 600; background: var(--s); color: var(--t); }
	.idpl-summary { font-size: 13.5px; line-height: 1.5; }
	.idpl-summary .muted { color: var(--m); }
	.idpl-kpis { display: flex; border: 1px solid var(--b); border-radius: 12px; overflow: hidden; }
	.idpl-kpi { padding: 10px 18px; min-width: 100px; border-right: 1px solid var(--b); }
	.idpl-kpi:last-child { border-right: 0; }
	.idpl-kpi b { display: block; font-size: 20px; font-weight: 600; line-height: 1.2; font-variant-numeric: tabular-nums; }
	.idpl-kpi span { display: block; font-size: 11.5px; color: var(--m); white-space: nowrap; }
	.idpl-kpi.good b { color: var(--idpl-green); }
	.idpl-kpi.accent b { color: var(--a); }
	.idpl-kpi.zero b { color: var(--m); font-weight: 500; }
	.idpl-facts { display: flex; gap: 8px 22px; flex-wrap: wrap; padding: 12px 22px 16px 26px; border-top: 1px solid var(--b); font-size: 12.5px; color: var(--m); }
	.idpl-facts b { color: var(--t); font-weight: 500; }
	.idpl-facts a { color: var(--a); }

	.idpl-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 13px 16px; border-bottom: 1px solid var(--b); }
	.idpl-panel-title { font-weight: 600; font-size: 13.5px; display: flex; align-items: center; gap: 8px; }
	.idpl-panel-title svg { color: var(--a); }
	.idpl-sub { color: var(--m); font-size: 11.5px; }
	.idpl-tools { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 10px 16px; border-bottom: 1px solid var(--b); }
	.idpl-chip { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 11px; border-radius: 99px; border: 1px solid var(--b);
		background: var(--bg); color: var(--t); font-size: 12px; cursor: pointer; }
	.idpl-chip b { color: var(--m); font-weight: 600; }
	.idpl-chip.active { background: var(--idpl-maroon-solid); border-color: var(--idpl-maroon-solid); color: #fff; }
	.idpl-chip.active b { color: inherit; opacity: .8; }
	.idpl-spacer { flex: 1; }
	.idpl-search { height: 30px; width: 220px; max-width: 100%; border: 1px solid var(--b); border-radius: 8px; padding: 0 10px; background: var(--control-bg, var(--s)); color: var(--t); font-size: 12.5px; }
	.idpl-search:focus { outline: none; border-color: var(--a); box-shadow: 0 0 0 2px var(--a-soft); }
	.idpl-seg { display: inline-flex; background: var(--s); border-radius: 8px; padding: 2px; }
	.idpl-seg button { border: 0; background: transparent; color: var(--m); font-size: 12px; padding: 4px 10px; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; gap: 5px; }
	.idpl-seg button.active { background: var(--bg); color: var(--t); box-shadow: 0 1px 2px rgba(0,0,0,.12); }
	.idpl-btn { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 11px; border-radius: 8px; border: 1px solid var(--b); background: var(--bg);
		color: var(--t); font-size: 12.5px; cursor: pointer; }
	.idpl-btn:hover { border-color: var(--a); color: var(--a); }

	.idpl-table { width: 100%; border-collapse: collapse; font-size: 13px; }
	.idpl-table th { text-align: left; font-weight: 500; font-size: 11.5px; color: var(--m); padding: 9px 16px; background: var(--s); border-bottom: 1px solid var(--b); white-space: nowrap; }
	.idpl-table td { padding: 8px 16px; border-bottom: 1px solid var(--b); vertical-align: middle; }
	.idpl-table th.fit, .idpl-table td.fit { width: 1%; white-space: nowrap; }
	.idpl-table tbody tr { cursor: pointer; }
	.idpl-table tbody tr:hover td { background: var(--s); }
	.idpl-thumb { display: block; width: 68px; height: 43px; border-radius: 5px; object-fit: cover; background: var(--s); border: 1px solid var(--b); }
	.idpl-thumb.portrait { width: 30px; height: 47px; }
	.idpl-thumb.none { display: flex; align-items: center; justify-content: center; font-size: 10px; color: var(--m); }
	.idpl-name { font-weight: 500; white-space: nowrap; }
	.idpl-name a { color: var(--t); }
	.idpl-name a:hover { color: var(--a); }
	.idpl-type { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 99px; font-size: 11.5px; font-weight: 500; white-space: nowrap; }
	.idpl-type::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
	.idpl-type.original { background: var(--idpl-green-soft); color: var(--idpl-green); }
	.idpl-type.reprint { background: var(--a-soft); color: var(--a); }
	.idpl-reason { color: var(--m); font-size: 12px; }
	.idpl-card-link { color: var(--t); font-variant-numeric: tabular-nums; }
	.idpl-card-link:hover { color: var(--a); }

	.idpl-gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 14px; padding: 16px; }
	.idpl-tile { border: 1px solid var(--b); border-radius: 12px; padding: 10px; background: var(--bg); cursor: pointer; text-align: left; transition: border-color .15s, box-shadow .15s; }
	.idpl-tile:hover { border-color: var(--a); box-shadow: 0 6px 16px rgba(15,23,42,.08); }
	.idpl-tile img, .idpl-tile .idpl-noimg { display: block; width: 100%; aspect-ratio: 1.586; object-fit: contain; border-radius: 8px; background: var(--s); }
	.idpl-tile .idpl-noimg { display: flex; align-items: center; justify-content: center; font-size: 12px; color: var(--m); }
	.idpl-tile-meta { display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-top: 8px; }
	.idpl-tile-name { font-size: 12.5px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.idpl-more { padding: 12px 16px; text-align: center; border-top: 1px solid var(--b); font-size: 12px; color: var(--m); }
	.idpl-more .idpl-btn { margin-left: 8px; }
	.idpl-empty { padding: 36px 16px; text-align: center; color: var(--m); font-size: 13px; }

	@media (max-width: 760px) {
		.idpl-kpis { width: 100%; }
		.idpl-kpi { flex: 1; min-width: 0; }
		.idpl-search { width: 100%; }
		.idpl-col-prog { display: none; }
	}
`;

// Viewer dialog (rendered outside .idpl, so it uses the root tokens).
const IDPL_VIEW_CSS = `
	.idpl-view { display: grid; gap: 14px; }
	.idpl-view-sides { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; padding: 18px; border-radius: 12px; background: var(--subtle-fg, #f4f5f7); min-height: 240px; align-items: center; }
	.idpl-view-sides figure { margin: 0; text-align: center; }
	.idpl-view-sides img { display: block; max-width: 100%; max-height: 300px; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,.1), 0 10px 26px rgba(15,23,42,.16); }
	.idpl-view-sides figcaption { margin-top: 8px; font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted, #6b7280); }
	.idpl-view-sides .none { color: var(--text-muted, #6b7280); font-size: 13px; }
	.idpl-view-bar { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
	.idpl-view-who b { font-size: 14px; }
	.idpl-view-who div { font-size: 12px; color: var(--text-muted, #6b7280); margin-top: 2px; }
	.idpl-view-nav { display: flex; align-items: center; gap: 8px; }
	.idpl-view-nav span { font-size: 12px; color: var(--text-muted, #6b7280); font-variant-numeric: tabular-nums; min-width: 64px; text-align: center; }
	.idpl-view-nav button { height: 30px; min-width: 30px; border-radius: 8px; border: 1px solid var(--border-color, #e2e6ea); background: var(--fg-color, #fff); color: var(--text-color, #1f2937); cursor: pointer; }
	.idpl-view-nav button:disabled { opacity: .4; cursor: default; }
	.idpl-view-nav button:hover:not(:disabled) { border-color: var(--idpl-maroon); color: var(--idpl-maroon); }
	.idpl-view-links { display: flex; gap: 8px; flex-wrap: wrap; }
`;

const IDPL_ICONS = {
	printer:
		'<path d="M6 9V2h12v7"/><rect x="6" y="14" width="12" height="8" rx="1"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>',
	list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
	grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
	download: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>',
};
const idpl_icon = (name, size = 15) =>
	`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IDPL_ICONS[name]}</svg>`;

const idpl_card_name = (c) => c.id_card_generation || c.student_id_card || "";
const idpl_card_route = (c) =>
	c.id_card_generation
		? `/app/id-card-generation/${encodeURIComponent(c.id_card_generation)}`
		: c.student_id_card
		? `/app/student-id-card/${encodeURIComponent(c.student_id_card)}`
		: "";

function idpl_visible(frm, state) {
	const q = state.query.toLowerCase();
	return (frm.doc.cards || []).filter(
		(c) =>
			(state.filter === "all" || c.print_type === state.filter) &&
			(!q ||
				`${c.student || ""} ${c.student_name || ""} ${idpl_card_name(c)} ${
					c.program || ""
				} ${c.batch || ""}`
					.toLowerCase()
					.includes(q))
	);
}

function idpl_render(frm) {
	if (!document.getElementById("idpl-css")) {
		$(`<style id="idpl-css">${IDPL_CSS}${IDPL_VIEW_CSS}</style>`).appendTo("head");
	}
	const doc = frm.doc;
	const esc = frappe.utils.escape_html;
	const cards = doc.cards || [];
	const state = (frm.__idpl =
		frm.__idpl && frm.__idpl.name === doc.name
			? frm.__idpl
			: { name: doc.name, filter: "all", query: "", view: "list", limit: IDPL_PAGE_SIZE });

	const originals = cards.filter((c) => c.print_type === "Original").length;
	const reprints = cards.filter((c) => c.print_type === "Reprint").length;
	const total = doc.total_cards_in_bulk || cards.length;
	const when = doc.printed_on ? frappe.datetime.str_to_user(doc.printed_on) : "";
	const user = doc.printed_by ? frappe.user.full_name(doc.printed_by) : "";
	const kpi = (value, label, cls) =>
		`<div class="idpl-kpi ${value ? cls : "zero"}"><b>${value}</b><span>${label}</span></div>`;
	const fact = (label, value) => (value ? `<span>${label} <b>${value}</b></span>` : "");
	const link = (doctype, name) =>
		name
			? `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${esc(
					name
			  )}</a>`
			: "";

	let summary = __("<b>{0}</b> card(s) printed", [total]);
	if (originals && reprints)
		summary += ` — ${__("{0} first print(s), {1} reprint(s)", [originals, reprints])}`;
	else if (reprints) summary += ` — ${__("all reprints")}`;
	else if (originals) summary += ` — ${__("all first prints")}`;
	summary += ".";
	if (when)
		summary += ` <span class="muted">${__("Printed {0}", [
			frappe.datetime.comment_when(doc.printed_on),
		])}.</span>`;

	// ---- Cards: list or gallery, one page at a time -------------------------
	const counts = { all: cards.length, Original: originals, Reprint: reprints };
	const chip = (key, label) =>
		key === "all" || counts[key]
			? `<button class="idpl-chip ${
					state.filter === key ? "active" : ""
			  }" data-filter="${key}">${label} <b>${counts[key]}</b></button>`
			: "";
	const rows = idpl_visible(frm, state);
	const shown = rows.slice(0, state.limit);
	const type_chip = (c) =>
		c.print_type
			? `<span class="idpl-type ${c.print_type === "Reprint" ? "reprint" : "original"}">${__(
					c.print_type
			  )}</span>`
			: "";

	let body;
	if (!cards.length) {
		body = `<div class="idpl-empty">${__("No cards were recorded for this print.")}</div>`;
	} else if (!rows.length) {
		body = `<div class="idpl-empty">${__("No cards match this filter.")}</div>`;
	} else if (state.view === "gallery") {
		body = `<div class="idpl-gallery">${shown
			.map(
				(c) => `<button class="idpl-tile" data-view="${esc(c.name)}" title="${__(
					"Open front and back"
				)}">
				${
					c.front_image
						? `<img src="${esc(
								frappe.utils.get_file_link(c.front_image)
						  )}" alt="" loading="lazy">`
						: `<div class="idpl-noimg">${__("No image")}</div>`
				}
				<div class="idpl-tile-meta"><span class="idpl-tile-name">${esc(
					c.student_name || c.student || ""
				)}</span>${type_chip(c)}</div>
				<div class="idpl-sub">${esc(c.student || "")} · ${esc(idpl_card_name(c))}</div>
			</button>`
			)
			.join("")}</div>`;
	} else {
		const any_reason = rows.some((c) => c.reprint_reason);
		body = `<div style="overflow-x:auto"><table class="idpl-table">
			<thead><tr><th class="fit">${__("Card")}</th><th>${__("Student")}</th><th class="fit">${__(
			"ID card"
		)}</th>
				<th class="fit">${__("Print")}</th><th class="idpl-col-prog">${__("Programme")}</th>${
			any_reason ? `<th>${__("Reason")}</th>` : ""
		}</tr></thead>
			<tbody>${shown
				.map(
					(c) => `<tr data-view="${esc(c.name)}" title="${__("Open front and back")}">
					<td class="fit">${
						c.front_image
							? `<img class="idpl-thumb" src="${esc(
									frappe.utils.get_file_link(c.front_image)
							  )}" alt="" loading="lazy">`
							: `<span class="idpl-thumb none">—</span>`
					}</td>
					<td><div class="idpl-name">${link("Student Master", c.student) || esc(c.student_name || "")}</div>
						<div class="idpl-sub">${esc(c.student_name || "")}${c.batch ? ` · ${esc(c.batch)}` : ""}</div></td>
					<td class="fit">${
						idpl_card_route(c)
							? `<a class="idpl-card-link" data-card href="${idpl_card_route(
									c
							  )}">${esc(idpl_card_name(c))}</a>`
							: "—"
					}</td>
					<td class="fit">${type_chip(c)}</td>
					<td class="idpl-col-prog"><span class="idpl-sub" style="font-size:12.5px">${esc(
						c.program || ""
					)}</span></td>
					${any_reason ? `<td><span class="idpl-reason">${esc(c.reprint_reason || "")}</span></td>` : ""}
				</tr>`
				)
				.join("")}</tbody></table></div>`;
	}
	const more =
		rows.length > state.limit
			? `<div class="idpl-more">${__("Showing {0} of {1}", [shown.length, rows.length])}
				<button class="idpl-btn" data-act="more">${__("Show {0} more", [
					Math.min(IDPL_PAGE_SIZE, rows.length - state.limit),
				])}</button>
				<button class="idpl-btn" data-act="all">${__("Show all")}</button></div>`
			: rows.length > IDPL_PAGE_SIZE
			? `<div class="idpl-more">${__("Showing all {0}", [rows.length])}</div>`
			: "";

	const $w = frm.fields_dict.printed_images.$wrapper;
	$w.closest(".section-body").css("max-width", "none");
	$w.html(`
		<div class="idpl">
			<section class="idpl-panel">
				<div class="idpl-head">
					<div class="idpl-head-main">
						<div class="idpl-eyebrow">${__("ID card print")}</div>
						<h3>${esc(doc.name)} ${
		doc.print_action_type
			? `<span class="idpl-pill">${esc(__("{0} print", [__(doc.print_action_type)]))}</span>`
			: ""
	}</h3>
						<div class="idpl-summary">${summary}</div>
					</div>
					<div class="idpl-kpis">
						${kpi(total, __("Cards printed"), "accent")}
						${kpi(originals, __("First prints"), "good")}
						${kpi(reprints, __("Reprints"), "accent")}
					</div>
				</div>
				<div class="idpl-facts">
					${fact(__("Printed on"), esc(when))}
					${fact(__("By"), esc(user))}
					${fact(__("Layout"), esc(__(doc.print_layout || "")))}
					${fact(__("Run ID"), esc(doc.bulk_print_id || ""))}
					${fact(__("Academic Year"), esc(doc.academic_year || ""))}
					${fact(__("Programme"), esc(doc.program || ""))}
					${fact(__("Batch"), link("SLCM Batch", doc.batch))}
					${fact(__("Department"), esc(doc.department || ""))}
				</div>
			</section>
			<section class="idpl-panel">
				<div class="idpl-panel-head"><div class="idpl-panel-title">${idpl_icon("printer")}${__(
		"Cards in this print"
	)}</div>
					<span class="idpl-sub">${__(
						"Click a card to see the front and back that were printed"
					)}</span></div>
				${
					cards.length
						? `<div class="idpl-tools">
					${chip("all", __("All"))}${chip("Original", __("First prints"))}${chip("Reprint", __("Reprints"))}
					<span class="idpl-spacer"></span>
					<input class="idpl-search" type="search" placeholder="${__(
						"Search student, card or batch"
					)}" value="${esc(state.query)}">
					<div class="idpl-seg">
						<button data-mode="list" class="${state.view === "list" ? "active" : ""}" title="${__(
								"List"
						  )}">${idpl_icon("list", 14)} ${__("List")}</button>
						<button data-mode="gallery" class="${state.view === "gallery" ? "active" : ""}" title="${__(
								"Gallery"
						  )}">${idpl_icon("grid", 14)} ${__("Gallery")}</button>
					</div>
					<button class="idpl-btn" data-act="csv" title="${__("Download the card list as CSV")}">${idpl_icon(
								"download",
								14
						  )} ${__("CSV")}</button>
				</div>`
						: ""
				}
				${body}
				${more}
			</section>
		</div>`);
}

function idpl_bind(frm) {
	const $w = frm.fields_dict.printed_images.$wrapper;
	$w.off(".idpl");
	const state = () => frm.__idpl;
	$w.on("click.idpl", "[data-filter]", (e) => {
		Object.assign(state(), {
			filter: $(e.currentTarget).data("filter"),
			limit: IDPL_PAGE_SIZE,
		});
		idpl_render(frm);
	});
	$w.on("click.idpl", "[data-mode]", (e) => {
		state().view = $(e.currentTarget).data("mode");
		idpl_render(frm);
	});
	$w.on("click.idpl", "[data-act='more']", () => {
		state().limit += IDPL_PAGE_SIZE;
		idpl_render(frm);
	});
	$w.on("click.idpl", "[data-act='all']", () => {
		state().limit = Number.MAX_SAFE_INTEGER;
		idpl_render(frm);
	});
	$w.on("click.idpl", "[data-act='csv']", () => idpl_export_csv(frm));
	$w.on("click.idpl", "a[data-card], .idpl-name a", (e) => e.stopPropagation());
	$w.on("click.idpl", "[data-view]", (e) => {
		const rows = idpl_visible(frm, state());
		const index = rows.findIndex((c) => c.name === String($(e.currentTarget).data("view")));
		if (index >= 0) idpl_viewer(rows, index);
	});
	$w.on(
		"input.idpl",
		".idpl-search",
		frappe.utils.debounce((e) => {
			Object.assign(state(), { query: e.target.value.trim(), limit: IDPL_PAGE_SIZE });
			const pos = e.target.selectionStart;
			idpl_render(frm);
			const input = $w.find(".idpl-search")[0];
			if (input) {
				input.focus();
				input.setSelectionRange(pos, pos);
			}
		}, 200)
	);
}

/** Large front/back view with previous/next through the filtered cards. */
function idpl_viewer(rows, start) {
	const esc = frappe.utils.escape_html;
	let index = start;
	const d = new frappe.ui.Dialog({
		title: __("Printed card"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
	});
	const render = () => {
		const c = rows[index];
		const side = (url, label) =>
			url
				? `<figure><img src="${esc(
						frappe.utils.get_file_link(url)
				  )}" alt="${label}"><figcaption>${label}</figcaption></figure>`
				: "";
		const sides = side(c.front_image, __("Front")) + side(c.back_image, __("Back"));
		const route = idpl_card_route(c);
		d.set_title(__("Printed card · {0}", [c.student_name || c.student || idpl_card_name(c)]));
		d.fields_dict.body.$wrapper.html(`
			<div class="idpl-view">
				<div class="idpl-view-sides">${
					sides ||
					`<div class="none">${__("No card images were recorded for this card.")}</div>`
				}</div>
				<div class="idpl-view-bar">
					<div class="idpl-view-who"><b>${esc(c.student_name || "")}</b>
						<div>${[c.student, idpl_card_name(c), c.print_type && __(c.print_type), c.reprint_reason]
							.filter(Boolean)
							.map(esc)
							.join(" · ")}</div></div>
					<div class="idpl-view-links">
						${route ? `<a class="btn btn-default btn-sm" href="${route}">${__("Open card")}</a>` : ""}
						${
							c.front_image
								? `<a class="btn btn-default btn-sm" href="${esc(
										frappe.utils.get_file_link(c.front_image)
								  )}" download>${__("Front")} ↓</a>`
								: ""
						}
						${
							c.back_image
								? `<a class="btn btn-default btn-sm" href="${esc(
										frappe.utils.get_file_link(c.back_image)
								  )}" download>${__("Back")} ↓</a>`
								: ""
						}
					</div>
					<div class="idpl-view-nav">
						<button data-nav="-1" ${index === 0 ? "disabled" : ""} title="${__("Previous")} (←)">‹</button>
						<span>${__("{0} of {1}", [index + 1, rows.length])}</span>
						<button data-nav="1" ${index === rows.length - 1 ? "disabled" : ""} title="${__(
			"Next"
		)} (→)">›</button>
					</div>
				</div>
			</div>`);
	};
	const go = (step) => {
		const next = index + step;
		if (next < 0 || next >= rows.length) return;
		index = next;
		render();
	};
	d.fields_dict.body.$wrapper.on("click", "[data-nav]", (e) =>
		go(+$(e.currentTarget).data("nav"))
	);
	const onkey = (e) => {
		if ($(e.target).is("input, textarea, select")) return;
		if (e.key === "ArrowLeft") go(-1);
		if (e.key === "ArrowRight") go(1);
	};
	d.$wrapper.on("keydown", onkey);
	d.onhide = () => d.$wrapper.off("keydown", onkey);
	d.show();
	render();
}

function idpl_export_csv(frm) {
	const header = [
		"#",
		"Student",
		"Student Name",
		"ID Card",
		"Print Type",
		"Reason",
		"Programme",
		"Batch",
		"Academic Year",
	];
	const rows = (frm.doc.cards || []).map((c) => [
		c.idx,
		c.student || "",
		c.student_name || "",
		idpl_card_name(c),
		c.print_type || "",
		c.reprint_reason || "",
		c.program || "",
		c.batch || "",
		c.academic_year || "",
	]);
	const csv = [header, ...rows]
		.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))
		.join("\r\n");
	// The BOM makes Excel open the file as UTF-8.
	const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
	const a = document.createElement("a");
	a.href = url;
	a.download = `${frm.doc.name}_cards.csv`;
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

frappe.ui.form.on("ID Card Print Log", {
	refresh(frm) {
		frm.disable_save();
		frm.toggle_display(IDPL_HIDDEN_FIELDS, false);

		frm.page.wrapper.find(".layout-side-section").hide();
		idpl_render(frm);
		idpl_bind(frm);
		// The summary has its own heading; drop the section's "Printed Images" title.
		frm.fields_dict.printed_images.$wrapper
			.closest(".form-section")
			.find(".section-head")
			.hide();
	},
});
