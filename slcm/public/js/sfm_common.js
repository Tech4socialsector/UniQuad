// Shared by the Student Fee Management and Fee Reports desk pages: formatting helpers,
// icons, the multi-select filter and the page styles. Loaded once through frappe.require,
// so its top-level names are declared a single time however many of the pages are opened.

const sfm_esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
// Indian grouping, symbol attached: ₹1,00,000.00
const sfm_money = (v) => "₹" + format_number(flt(v), "#,##,###.##", 2);
const sfm_int = (v) => format_number(cint(v), "#,##,###.##", 0);
const sfm_date = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 10)) : "—");
// 29-09-2026, 09:02 AM
const sfm_datetime = (v) => (v ? moment(frappe.datetime.str_to_obj(String(v))).format("DD-MM-YYYY, hh:mm A") : "—");

// Lucide icon set (inlined so every icon on the page comes from one consistent family).
const SFM_ICON_PATHS = {
	refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
	search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
	"search-x": '<path d="m13.5 8.5-5 5"/><path d="m8.5 8.5 5 5"/><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
	filter: '<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>',
	download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
	users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
	rupee: '<path d="M6 3h12"/><path d="M6 8h12"/><path d="m6 13 8.5 8"/><path d="M6 13h3"/><path d="M9 13c6.667 0 6.667-10 0-10"/>',
	check: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
	clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
	alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
	wallet: '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
	x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
	"chevron-left": '<path d="m15 18-6-6 6-6"/>',
	"chevron-right": '<path d="m9 18 6-6-6-6"/>',
	"chevrons-left": '<path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/>',
	"chevrons-right": '<path d="m6 17 5-5-5-5"/><path d="m13 17 5-5-5-5"/>',
	"chevron-down": '<path d="m6 9 6 6 6-6"/>',
	"sort-none": '<path d="m21 16-4 4-4-4"/><path d="M17 20V4"/><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/>',
	"sort-asc": '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
	"sort-desc": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
	"arrow-left": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
	plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
	undo: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
	"file-text": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
	card: '<rect width="20" height="14" x="2" y="5" rx="2"/><path d="M2 10h20"/>',
	loader: '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
	upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
	columns: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="M15 3v18"/>',
	eye: '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
	award: '<circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/>',
};
const sfm_icon = (name, size = 16, cls = "") =>
	`<svg class="sfm-icon ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${SFM_ICON_PATHS[name] || ""}</svg>`;

const SFM_STATUS_CLASS = {
	Pending: "pending",
	Overdue: "overdue",
	"Partially Paid": "partial",
	Paid: "paid",
	Cleared: "paid",
	Waived: "waived",
	Cancelled: "muted",
	"No Demands": "muted",
	Submitted: "paid",
	Draft: "pending",
	Approved: "paid",
	Reversed: "muted",
	Active: "paid",
	Exhausted: "muted",
	"Moved to Excess": "excess",
	"Cancelled & Moved to Excess": "excess-cancelled",
};

// A cancelled due whose paid money went to excess is stored as Cancelled + moved_to_excess_amount.
const sfm_demand_status = (d) =>
	d.status === "Cancelled" && flt(d.moved_to_excess_amount) > 0 ? "Cancelled & Moved to Excess" : d.status;
const sfm_badge = (status, label) =>
	`<span class="sfm-badge sfm-badge-${SFM_STATUS_CLASS[status] || "muted"}">${sfm_esc(label || status || "—")}</span>`;

const SFM_PAYABLE = (d) => !["Paid", "Cancelled", "Waived"].includes(d.status) && flt(d.outstanding_amount) > 0;

// Pull the human-readable message out of a Frappe error response.
function sfm_server_message(json) {
	try {
		const msgs = JSON.parse(json._server_messages || "[]").map((m) => JSON.parse(m).message);
		return $("<div>").html(msgs.join("<br>")).text() || json.exception || "";
	} catch (e) {
		return json && json.exception;
	}
}

function sfm_load_font() {
	if (document.getElementById("sfm-font")) return;
	$("head").append(
		'<link rel="preconnect" href="https://fonts.googleapis.com">' +
			'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' +
			'<link id="sfm-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">'
	);
}

const SFM_DUES_STATUS_OPTIONS = [
	{ value: "pending", label: __("Has Pending Dues") },
	{ value: "overdue", label: __("Has Overdue Dues") },
	{ value: "cleared", label: __("All Dues Cleared") },
	{ value: "excess", label: __("Has Excess Amount") },
	{ value: "no_demands", label: __("No Demands") },
];

// Checkbox dropdown with "Select all" / "Clear". An empty selection means "no filter".
class SfmMultiSelect {
	constructor($field, { key, label, all_label, searchable = false, on_change }) {
		this.all_label = all_label;
		this.on_change = on_change;
		this.options = [];
		this.selected = new Set();
		this.$field = $field;
		const id = `sfm-f-${key}`;
		$field.addClass("sfm-ms").html(`
			<label id="${id}-label" for="${id}">${label}</label>
			<button type="button" id="${id}" class="sfm-control sfm-ms-trigger" aria-haspopup="true" aria-expanded="false" aria-controls="${id}-panel">
				<span class="sfm-ms-text"></span>
				${sfm_icon("chevron-down", 14, "sfm-ms-caret")}
			</button>
			<div class="sfm-ms-panel" id="${id}-panel" role="group" aria-labelledby="${id}-label" hidden>
				${
					searchable
						? `<div class="sfm-ms-search">${sfm_icon("search", 14)}<input type="search" class="sfm-ms-filter" placeholder="${__("Search…")}" aria-label="${sfm_esc(__("Search {0}", [label]))}" autocomplete="off"></div>`
						: ""
				}
				<div class="sfm-ms-actions">
					<button type="button" data-ms="all">${__("Select all")}</button>
					<button type="button" data-ms="clear">${__("Clear")}</button>
				</div>
				<div class="sfm-ms-list"></div>
			</div>`);
		this.$trigger = $field.find(".sfm-ms-trigger");
		this.$panel = $field.find(".sfm-ms-panel");
		this.$list = $field.find(".sfm-ms-list");
		this.$trigger.on("click", () => (this.is_open() ? this.close() : this.open()));
		$field.on("keydown", (e) => {
			if (e.key === "Escape" && this.is_open()) {
				e.stopPropagation();
				this.close();
				this.$trigger.trigger("focus");
			}
		});
		this.$list.on("change", "input", (e) => {
			e.currentTarget.checked ? this.selected.add(e.currentTarget.value) : this.selected.delete(e.currentTarget.value);
			this.changed();
		});
		// "Select all" respects the search box: it adds only the options currently shown.
		this.$panel.on("click", '[data-ms="all"]', () => {
			this.visible_options().forEach((o) => this.selected.add(o.value));
			this.render_list();
			this.changed();
		});
		this.$panel.on("click", '[data-ms="clear"]', () => {
			this.selected.clear();
			this.render_list();
			this.changed();
		});
		this.$panel.on("input", ".sfm-ms-filter", () => this.render_list());
		this.render_list();
		this.render_trigger();
	}

	// Replace the option list; selections that no longer exist are dropped.
	set_options(options, selected = [...this.selected]) {
		this.options = options;
		this.selected = new Set(selected.filter((v) => options.some((o) => o.value === v)));
		this.render_list();
		this.render_trigger();
	}

	value() {
		return this.options.filter((o) => this.selected.has(o.value)).map((o) => o.value);
	}

	visible_options() {
		const q = (this.$panel.find(".sfm-ms-filter").val() || "").trim().toLowerCase();
		return q ? this.options.filter((o) => o.label.toLowerCase().includes(q)) : this.options;
	}

	render_list() {
		const shown = this.visible_options();
		this.$list.html(
			shown.length
				? shown
						.map(
							(o) => `<label class="sfm-ms-option">
								<input type="checkbox" value="${sfm_esc(o.value)}" ${this.selected.has(o.value) ? "checked" : ""}>
								<span>${sfm_esc(o.label)}</span>
							</label>`
						)
						.join("")
				: `<div class="sfm-ms-empty">${this.options.length ? __("No matches") : __("No options available")}</div>`
		);
	}

	render_trigger() {
		const n = this.selected.size;
		let text = this.all_label;
		if (n === 1) text = (this.options.find((o) => this.selected.has(o.value)) || {}).label || this.all_label;
		else if (n > 1 && n === this.options.length) text = __("All selected ({0})", [n]);
		else if (n > 1) text = __("{0} selected", [n]);
		this.$trigger.toggleClass("has-value", n > 0).find(".sfm-ms-text").text(text);
		this.$trigger.attr("title", n > 1 ? this.value().map((v) => (this.options.find((o) => o.value === v) || {}).label).join(", ") : text);
	}

	changed() {
		this.render_trigger();
		this.on_change(this.value());
	}

	is_open() {
		return !this.$panel.prop("hidden");
	}

	open() {
		this.$field.closest(".sfm-filter-grid").find(".sfm-ms").not(this.$field).each((_, el) => {
			$(el).find(".sfm-ms-panel").prop("hidden", true);
			$(el).find(".sfm-ms-trigger").attr("aria-expanded", "false");
		});
		this.$panel.prop("hidden", false);
		this.$trigger.attr("aria-expanded", "true");
		const $search = this.$panel.find(".sfm-ms-filter");
		($search.length ? $search : this.$list.find("input").first()).trigger("focus");
	}

	close() {
		this.$panel.prop("hidden", true);
		this.$trigger.attr("aria-expanded", "false");
	}
}

// Caption ("N students match…") and numbered pager for a paginated table.
// opts: state ({start, page_length}), $pager, $caption, and optional wording (one/many/showing_one/showing_many).
function sfm_render_pager(total, shown, opts) {
	const s = opts.state;
	const $pager = opts.$pager;
	const $caption = opts.$caption;
	const one = opts.one || __("1 student matches the current filters");
	const many = opts.many || __("{0} students match the current filters");
	const showing_one = opts.showing_one || __("Showing 1 of 1 student");
	const showing_many = opts.showing_many || __("Showing {0} to {1} of {2} students");
	const pages = Math.max(1, Math.ceil(total / s.page_length));
	const current = Math.floor(s.start / s.page_length) + 1;
	const from = total ? s.start + 1 : 0;
	const to = Math.min(s.start + shown, total);

	$caption.text(total ? (total === 1 ? one : many.replace("{0}", sfm_int(total))) : "");

	if (!total) {
		$pager.empty();
		return;
	}

	// 1 … 4 5 [6] 7 8 … 20
	const nums = new Set([1, pages, current - 1, current, current + 1]);
	if (current <= 3) [2, 3, 4].forEach((n) => nums.add(n));
	if (current >= pages - 2) [pages - 1, pages - 2, pages - 3].forEach((n) => nums.add(n));
	const list = [...nums].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);

	let prev = 0;
	const page_btns = list
		.map((n) => {
			const gap = n - prev > 1 ? '<span class="sfm-page-gap" aria-hidden="true">…</span>' : "";
			prev = n;
			return (
				gap +
				`<button type="button" class="sfm-page-btn ${n === current ? "is-active" : ""}" data-page="${n}"
					aria-label="${__("Page {0}", [n])}" ${n === current ? 'aria-current="page"' : ""}>${n}</button>`
			);
		})
		.join("");
	const nav = (page, icon, label, disabled) =>
		`<button type="button" class="sfm-page-btn sfm-page-nav" data-page="${page}" aria-label="${label}" title="${label}" ${disabled ? "disabled" : ""}>${icon}</button>`;

	$pager.html(`
		<div class="sfm-muted">${total === 1 ? showing_one : showing_many.replace("{0}", sfm_int(from)).replace("{1}", sfm_int(to)).replace("{2}", sfm_int(total))}</div>
		<nav class="sfm-pages" aria-label="${__("Pagination")}">
			${nav(1, sfm_icon("chevrons-left", 15), __("First page"), current === 1)}
			${nav(current - 1, sfm_icon("chevron-left", 15) + `<span class="sfm-page-label">${__("Previous")}</span>`, __("Previous page"), current === 1)}
			${page_btns}
			${nav(current + 1, `<span class="sfm-page-label">${__("Next")}</span>` + sfm_icon("chevron-right", 15), __("Next page"), current === pages)}
			${nav(pages, sfm_icon("chevrons-right", 15), __("Last page"), current === pages)}
		</nav>
	`);
}

function sfm_inject_styles() {
	if (document.getElementById("sfm-styles")) return;
	const css = `
	/* ── Tokens ── */
	.sfm, .sfm-dialog {
		--sfm-primary: #920C24;
		--sfm-primary-hover: #7A0A1E;
		--sfm-primary-text: #920C24;
		--sfm-primary-soft: rgba(146, 12, 36, .05);
		--sfm-primary-tint: rgba(146, 12, 36, .09);
		--sfm-bg: #F8F8F8;
		--sfm-card: #FFFFFF;
		--sfm-subtle: #FAFAFA;
		--sfm-border: #E5E5E5;
		--sfm-border-strong: #D4D4D4;
		--sfm-text: #222222;
		--sfm-muted: #6B7280;
		--sfm-success: #15803D; --sfm-success-bg: #F0FDF4; --sfm-success-bd: #BBF7D0;
		--sfm-warning: #C2410C; --sfm-warning-bg: #FFF7ED; --sfm-warning-bd: #FED7AA;
		--sfm-amber: #854D0E;   --sfm-amber-bg: #FEFCE8;   --sfm-amber-bd: #FDE68A;
		--sfm-danger: #B42318;  --sfm-danger-bg: #FEF3F2;  --sfm-danger-bd: #FECDCA;
		--sfm-violet: #6B21A8;  --sfm-violet-bg: #FAF5FF;  --sfm-violet-bd: #E9D5FF;
		--sfm-font: 'Merriweather', Georgia, 'Times New Roman', serif;
		--sfm-radius: 8px;
		--sfm-shadow: 0 1px 2px rgba(16, 24, 40, .04);
	}
	[data-theme="dark"] .sfm, [data-theme="dark"] .sfm-dialog {
		--sfm-primary-text: #F2899B;
		--sfm-primary-soft: rgba(242, 137, 155, .07);
		--sfm-primary-tint: rgba(242, 137, 155, .13);
		--sfm-bg: #141414; --sfm-card: #1C1C1C; --sfm-subtle: #232323;
		--sfm-border: #2E2E2E; --sfm-border-strong: #3A3A3A;
		--sfm-text: #EDEDED; --sfm-muted: #A1A1AA;
		--sfm-success: #4ADE80; --sfm-success-bg: rgba(74,222,128,.08); --sfm-success-bd: rgba(74,222,128,.3);
		--sfm-warning: #FB923C; --sfm-warning-bg: rgba(251,146,60,.08); --sfm-warning-bd: rgba(251,146,60,.3);
		--sfm-amber: #FACC15;   --sfm-amber-bg: rgba(250,204,21,.08);   --sfm-amber-bd: rgba(250,204,21,.3);
		--sfm-danger: #F87171;  --sfm-danger-bg: rgba(248,113,113,.08); --sfm-danger-bd: rgba(248,113,113,.3);
		--sfm-violet: #C084FC;  --sfm-violet-bg: rgba(192,132,252,.08); --sfm-violet-bd: rgba(192,132,252,.3);
	}

	/* ── Page frame: let the dashboard use the width, centred at 1600px ── */
	.sfm-page .page-head .container, .sfm-page .page-body.container { max-width: 1664px; }
	.sfm-page .page-body, .sfm-page .layout-main-section-wrapper, .sfm-page .layout-main-section { background: transparent; }
	.sfm-page .layout-main-section { border: none; box-shadow: none; }
	.sfm-page .navbar-breadcrumbs, .sfm-page .title-area .title-text { font-family: var(--sfm-font, 'Merriweather', Georgia, serif); font-size: 13px; font-weight: 400; }

	.sfm { font-family: var(--sfm-font); color: var(--sfm-text); font-size: 13px; line-height: 1.55; }
	.sfm button, .sfm input, .sfm select, .sfm-dialog, .sfm-dialog button, .sfm-dialog input, .sfm-dialog select, .sfm-dialog textarea { font-family: var(--sfm-font); }
	.sfm-shell { max-width: 1600px; margin: 0 auto; padding: 8px 16px 40px; display: flex; flex-direction: column; gap: 20px; container: sfm / inline-size; }
	.sfm-icon { flex: none; display: inline-block; vertical-align: middle; }
	.sfm-spin { animation: sfm-spin .8s linear infinite; }
	@keyframes sfm-spin { to { transform: rotate(360deg); } }

	/* ── Header ── */
	.sfm-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
	.sfm-title { font-family: var(--sfm-font); font-size: 24px; font-weight: 700; line-height: 1.3; margin: 0; color: var(--sfm-text); letter-spacing: -.01em; }
	.sfm-subtitle { margin: 4px 0 0; font-size: 13px; color: var(--sfm-muted); }
	.sfm-back { align-self: flex-start; margin-bottom: -4px; text-decoration: none !important; color: var(--sfm-primary-text) !important; }

	/* ── Buttons ── */
	.sfm-btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 36px; padding: 0 16px; border-radius: 6px; font-size: 13px; font-weight: 500; line-height: 1; border: 1px solid transparent; cursor: pointer; white-space: nowrap; transition: background-color .15s, border-color .15s, color .15s, box-shadow .15s; }
	.sfm-btn:focus-visible, .sfm-icon-btn:focus-visible, .sfm-page-btn:focus-visible, .sfm-sort:focus-visible, .sfm-chip:focus-visible, .sfm-tab:focus-visible, .sfm-student-link:focus-visible { outline: 2px solid var(--sfm-primary); outline-offset: 2px; }
	.sfm-btn:disabled { opacity: .6; cursor: default; }
	.sfm-btn-primary { background: var(--sfm-primary); border-color: var(--sfm-primary); color: #fff !important; }
	.sfm-btn-primary:hover:not(:disabled) { background: var(--sfm-primary-hover); border-color: var(--sfm-primary-hover); }
	.sfm-btn-secondary { background: var(--sfm-card); border-color: var(--sfm-primary); color: var(--sfm-primary-text); }
	.sfm-btn-secondary:hover:not(:disabled) { background: var(--sfm-primary-soft); }
	.sfm-btn-ghost { background: transparent; color: var(--sfm-primary-text); border-color: var(--sfm-border); }
	.sfm-btn-ghost:hover { background: var(--sfm-primary-soft); border-color: var(--sfm-primary); }
	.sfm-btn-sm { height: 30px; padding: 0 12px; font-size: 12px; gap: 6px; }
	.sfm-btn.dropdown-toggle::after { margin-left: 2px; }

	/* ── Panels ── */
	.sfm-panel { background: var(--sfm-card); border: 1px solid var(--sfm-border); border-radius: var(--sfm-radius); box-shadow: var(--sfm-shadow); }
	.sfm-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 20px; border-bottom: 1px solid var(--sfm-border); }
	.sfm-panel-title { display: flex; align-items: center; gap: 8px; margin: 0; font-family: var(--sfm-font); font-size: 15px; font-weight: 600; color: var(--sfm-text); }
	.sfm-panel-title .sfm-icon { color: var(--sfm-primary-text); }
	.sfm-muted { color: var(--sfm-muted); font-size: 12px; }
	.sfm-sub { color: var(--sfm-muted); font-size: 12px; line-height: 1.5; }
	.sfm-strong { font-weight: 600; }
	.sfm-link { color: var(--sfm-primary-text) !important; font-weight: 500; }
	.sfm-link:hover { text-decoration: underline; }

	/* ── Filters ── */
	.sfm-filter-grid { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr) minmax(0,1.6fr) minmax(0,1fr) minmax(0,1.6fr) auto; gap: 16px; padding: 16px 20px 20px; }
	.sfm-search-action { justify-content: flex-end; }
	.sfm-search-btn { height: 38px; position: relative; }
	.sfm-search-btn.is-dirty::after { content: ""; position: absolute; top: -4px; right: -4px; width: 10px; height: 10px; border-radius: 50%; background: #F59E0B; border: 2px solid var(--sfm-card); }
	.sfm-field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
	.sfm-field label, .sfm-page-size label { font-size: 12px; font-weight: 600; color: var(--sfm-text); margin: 0; }
	.sfm-control { width: 100%; height: 38px; border: 1px solid var(--sfm-border-strong); border-radius: 6px; padding: 0 12px; font-size: 13px; background: var(--sfm-card); color: var(--sfm-text); transition: border-color .15s, box-shadow .15s; }
	.sfm-control:hover { border-color: #A3A3A3; }
	.sfm-control:focus { outline: none; border-color: var(--sfm-primary); box-shadow: 0 0 0 3px var(--sfm-primary-tint); }
	.sfm-control-sm { height: 32px; width: auto; min-width: 72px; }
	.sfm-select-wrap, .sfm-search-wrap { position: relative; }
	.sfm-select-wrap select { appearance: none; -webkit-appearance: none; padding-right: 32px; text-overflow: ellipsis; }
	.sfm-select-caret { position: absolute; right: 11px; top: 50%; transform: translateY(-50%); color: var(--sfm-muted); pointer-events: none; }
	.sfm-search-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--sfm-muted); pointer-events: none; }
	.sfm-search-wrap input { padding-left: 36px; }

	/* ── Multi-select ── */
	.sfm-ms { position: relative; }
	.sfm-ms-trigger { display: flex; align-items: center; gap: 8px; text-align: left; cursor: pointer; }
	.sfm-ms-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.sfm-ms-trigger.has-value { border-color: var(--sfm-primary); background: var(--sfm-primary-soft); color: var(--sfm-primary-text); font-weight: 600; }
	.sfm-ms-caret { color: var(--sfm-muted); transition: transform .15s; }
	.sfm-ms-trigger[aria-expanded="true"] .sfm-ms-caret { transform: rotate(180deg); }
	.sfm-ms-trigger[aria-expanded="true"] { border-color: var(--sfm-primary); box-shadow: 0 0 0 3px var(--sfm-primary-tint); }
	.sfm-ms-panel { position: absolute; top: calc(100% + 4px); left: 0; width: 100%; min-width: 240px; z-index: 40; background: var(--sfm-card); border: 1px solid var(--sfm-border); border-radius: var(--sfm-radius); box-shadow: 0 10px 28px rgba(16, 24, 40, .14); padding: 8px; }
	.sfm-ms-panel[hidden] { display: none; }
	.sfm-ms-search { position: relative; margin-bottom: 8px; }
	.sfm-ms-search .sfm-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: var(--sfm-muted); pointer-events: none; }
	.sfm-ms-filter { width: 100%; height: 32px; border: 1px solid var(--sfm-border-strong); border-radius: 6px; padding: 0 10px 0 30px; font-size: 12px; background: var(--sfm-card); color: var(--sfm-text); }
	.sfm-ms-filter:focus { outline: none; border-color: var(--sfm-primary); box-shadow: 0 0 0 3px var(--sfm-primary-tint); }
	.sfm-ms-actions { display: flex; justify-content: space-between; gap: 8px; padding: 0 4px 8px; margin-bottom: 4px; border-bottom: 1px solid var(--sfm-border); }
	.sfm-ms-actions button { background: none; border: none; padding: 2px 4px; border-radius: 4px; font-size: 12px; font-weight: 600; color: var(--sfm-primary-text); cursor: pointer; }
	.sfm-ms-actions button:hover { background: var(--sfm-primary-soft); }
	.sfm-ms-actions button:focus-visible { outline: 2px solid var(--sfm-primary); outline-offset: 1px; }
	.sfm-ms-list { max-height: 240px; overflow-y: auto; }
	.sfm-field .sfm-ms-option { display: flex; align-items: flex-start; gap: 8px; padding: 8px; margin: 0; border-radius: 6px; font-size: 13px; font-weight: 400; color: var(--sfm-text); cursor: pointer; }
	.sfm-ms-option:hover { background: var(--sfm-primary-soft); }
	.sfm-ms-option input { accent-color: var(--sfm-primary); width: 15px; height: 15px; margin-top: 2px; flex: none; }
	.sfm-ms-empty { padding: 12px 8px; text-align: center; font-size: 12px; color: var(--sfm-muted); }

	/* ── KPI cards ── */
	.sfm-kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 16px; transition: opacity .15s; }
	.sfm-kpi-grid.is-refreshing { opacity: .6; }
	.sfm-kpi-grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 16px; }
	.sfm-kpi { display: flex; align-items: center; gap: 12px; min-height: 84px; padding: 16px; background: var(--sfm-card); border: 1px solid var(--sfm-border); border-radius: var(--sfm-radius); box-shadow: var(--sfm-shadow); transition: border-color .15s, box-shadow .15s; min-width: 0; }
	.sfm-kpi:hover { border-color: var(--sfm-border-strong); box-shadow: 0 4px 12px rgba(16, 24, 40, .06); }
	.sfm-kpi-icon { width: 40px; height: 40px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; flex: none; background: var(--sfm-subtle); color: var(--sfm-muted); border: 1px solid var(--sfm-border); }
	.sfm-kpi-body { min-width: 0; }
	.sfm-kpi-label { font-size: 12px; color: var(--sfm-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.sfm-kpi-value { font-size: 18px; font-weight: 700; line-height: 1.35; margin-top: 2px; color: var(--sfm-text); font-variant-numeric: tabular-nums lining-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.sfm-kpi-primary .sfm-kpi-icon { background: var(--sfm-primary-soft); color: var(--sfm-primary-text); border-color: var(--sfm-primary-tint); }
	.sfm-kpi-primary .sfm-kpi-value { color: var(--sfm-primary-text); }
	.sfm-kpi-success .sfm-kpi-icon { background: var(--sfm-success-bg); color: var(--sfm-success); border-color: var(--sfm-success-bd); }
	.sfm-kpi-success .sfm-kpi-value { color: var(--sfm-success); }
	.sfm-kpi-warning .sfm-kpi-icon { background: var(--sfm-warning-bg); color: var(--sfm-warning); border-color: var(--sfm-warning-bd); }
	.sfm-kpi-warning .sfm-kpi-value { color: var(--sfm-warning); }
	.sfm-kpi-danger .sfm-kpi-icon { background: var(--sfm-danger-bg); color: var(--sfm-danger); border-color: var(--sfm-danger-bd); }
	.sfm-kpi-danger .sfm-kpi-value { color: var(--sfm-danger); }

	/* ── Skeletons ── */
	.sfm-skel { display: block; height: 12px; border-radius: 4px; background: linear-gradient(90deg, var(--sfm-border) 25%, var(--sfm-subtle) 50%, var(--sfm-border) 75%); background-size: 200% 100%; animation: sfm-shimmer 1.2s ease-in-out infinite; }
	.sfm-skel + .sfm-skel { margin-top: 8px; }
	.sfm-skel-sm { height: 9px; }
	.sfm-skel-value { width: 110px; height: 18px; margin-top: 4px; }
	td.num .sfm-skel { margin-left: auto; }
	td.center .sfm-skel { margin: 0 auto; height: 28px; border-radius: 6px; }
	@keyframes sfm-shimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
	@media (prefers-reduced-motion: reduce) { .sfm-skel, .sfm-spin { animation: none; } }

	/* ── Table ── */
	.sfm-table-panel { overflow: visible; }
	.sfm-table-panel > .sfm-table-scroll:last-child { border-radius: 0 0 var(--sfm-radius) var(--sfm-radius); }
	.sfm-table-panel > .sfm-table-scroll:first-child { border-radius: var(--sfm-radius) var(--sfm-radius) 0 0; }
	.sfm-table-panel > .sfm-table-scroll:only-child { border-radius: var(--sfm-radius); }
	.sfm .dropdown-menu { z-index: 1050; }
	.sfm-table-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 20px; border-bottom: 1px solid var(--sfm-border); }
	.sfm-table-caption { margin-top: 2px; }
	.sfm-page-size { display: flex; align-items: center; gap: 8px; }
	.sfm-page-size label { font-weight: 400; color: var(--sfm-muted); }
	.sfm-table-scroll { overflow: auto; max-height: min(72vh, 920px); }
	.sfm-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; }
	.sfm-student-table { min-width: 1080px; }
	.sfm-student-table td:first-child { min-width: 200px; max-width: 250px; }
	.sfm-student-table td.sfm-wrap { min-width: 130px; }
	.sfm-student-table td.sfm-batch { min-width: 70px; }
	.sfm-student-table th, .sfm-student-table td { padding-left: 12px; padding-right: 12px; }
	.sfm-student-table .sfm-sort { gap: 4px; }
	/* Receipt column stays pinned to the right edge while the table scrolls sideways */
	.sfm-student-table th:last-child, .sfm-student-table td:last-child { position: sticky; right: 0; background: var(--sfm-card); box-shadow: -1px 0 0 var(--sfm-border); }
	.sfm-student-table thead th:last-child { z-index: 2; background: var(--sfm-subtle); }
	.sfm-dues-table th.sfm-receipt-th, .sfm-dues-table td.sfm-receipt-cell { position: sticky; right: 0; background: var(--sfm-card); box-shadow: -1px 0 0 var(--sfm-border); }
	.sfm-dues-table thead th.sfm-receipt-th { z-index: 2; background: var(--sfm-subtle); }
	.sfm-dues-table tbody tr[data-name]:hover td.sfm-receipt-cell { background: linear-gradient(var(--sfm-primary-soft), var(--sfm-primary-soft)), var(--sfm-card); }
	.sfm-dues-table tr.selected td.sfm-receipt-cell { background: linear-gradient(var(--sfm-primary-tint), var(--sfm-primary-tint)), var(--sfm-card); }
	.sfm-student-row:hover td:last-child { background: linear-gradient(var(--sfm-primary-soft), var(--sfm-primary-soft)), var(--sfm-card); }
	.sfm-table thead th { position: sticky; top: 0; z-index: 1; background: var(--sfm-subtle); color: var(--sfm-text); font-family: var(--sfm-font); font-weight: 600; font-size: 12px; padding: 12px 14px; text-align: left; white-space: nowrap; border-bottom: 2px solid var(--sfm-primary); }
	.sfm-table td { padding: 14px; border-bottom: 1px solid var(--sfm-border); vertical-align: top; color: var(--sfm-text); }
	.sfm-table tbody tr:last-child td { border-bottom: none; }
	.sfm-table .num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums lining-nums; }
	.sfm-table .center { text-align: center; }
	.sfm-table thead th.num .sfm-sort { flex-direction: row-reverse; }
	.sfm-sort { display: inline-flex; align-items: center; gap: 6px; background: none; border: none; padding: 0; font: inherit; color: inherit; cursor: pointer; border-radius: 4px; }
	.sfm-sort-icon { display: inline-flex; color: var(--sfm-muted); opacity: .55; }
	.sfm-sort:hover .sfm-sort-icon { opacity: 1; }
	th.is-sorted { color: var(--sfm-primary-text) !important; }
	th.is-sorted .sfm-sort-icon { color: var(--sfm-primary-text); opacity: 1; }
	.sfm-wrap { white-space: normal; overflow-wrap: break-word; }
	.sfm-ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.sfm-amount-strong { font-weight: 700; }
	.sfm-student-row { cursor: pointer; transition: background-color .12s; }
	.sfm-student-row:hover td, .sfm-dues-table tbody tr[data-name]:hover td { background: var(--sfm-primary-soft); }
	.sfm-student-link { font-weight: 700; font-size: 13.5px; color: var(--sfm-text) !important; text-decoration: none !important; }
	.sfm-student-row:hover .sfm-student-link { color: var(--sfm-primary-text) !important; }
	.sfm-dues-table tbody tr[data-name] { cursor: pointer; }
	.sfm-dues-table tr.selected td { background: var(--sfm-primary-tint); }
	.sfm-dues-table td { white-space: nowrap; }
	/* Text-heavy cells wrap (numbers/dates stay on one line) so more columns fit without side-scrolling */
	.sfm-dues-table td.sfm-wrap-cell { white-space: normal; }
	.sfm-dues-table td.sfm-fc-cell { min-width: 150px; max-width: 200px; }
	.sfm-dues-table td.sfm-status-cell { max-width: 150px; }
	.sfm-dues-table td.sfm-status-cell .sfm-badge { white-space: normal; height: auto; min-height: 22px; padding: 3px 10px; line-height: 1.35; text-align: center; }
	.sfm-dues-table td.sfm-remark-cell { min-width: 150px; max-width: 200px; }
	.sfm-clamp { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
	.sfm-check { width: 44px; text-align: center !important; }
	.sfm-check input { accent-color: var(--sfm-primary); width: 15px; height: 15px; }
	.sfm-remark { max-width: 240px; overflow: hidden; text-overflow: ellipsis; }

	/* ── Badges ── */
	.sfm-badge { display: inline-flex; align-items: center; height: 22px; padding: 0 10px; border-radius: 999px; border: 1px solid; font-size: 10.5px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; white-space: nowrap; }
	.sfm-badge-pending { color: var(--sfm-warning); background: var(--sfm-warning-bg); border-color: var(--sfm-warning-bd); }
	.sfm-badge-overdue { color: var(--sfm-danger);  background: var(--sfm-danger-bg);  border-color: var(--sfm-danger-bd); }
	.sfm-badge-partial { color: var(--sfm-amber);   background: var(--sfm-amber-bg);   border-color: var(--sfm-amber-bd); }
	.sfm-badge-paid    { color: var(--sfm-success); background: var(--sfm-success-bg); border-color: var(--sfm-success-bd); }
	.sfm-badge-waived  { color: var(--sfm-violet);  background: var(--sfm-violet-bg);  border-color: var(--sfm-violet-bd); }
	.sfm-badge-excess  { color: #0E7490; background: #ECFEFF; border-color: #A5F3FC; }
	.sfm-badge-excess-cancelled { color: var(--sfm-muted); background: var(--sfm-subtle); border-color: #A5F3FC; }
	[data-theme="dark"] .sfm .sfm-badge-excess { color: #67E8F9; background: rgba(103,232,249,.08); border-color: rgba(103,232,249,.3); }
	.sfm-badge-muted   { color: var(--sfm-muted);   background: var(--sfm-subtle);     border-color: var(--sfm-border); }

	/* ── Icon buttons (receipt) ── */
	.sfm-icon-btn { position: relative; display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 6px; border: 1px solid var(--sfm-border); background: var(--sfm-card); color: var(--sfm-primary-text); cursor: pointer; transition: background-color .15s, border-color .15s; }
	.sfm-icon-btn:hover:not(:disabled) { background: var(--sfm-primary-tint); border-color: var(--sfm-primary); }
	.sfm-icon-btn:disabled { color: var(--sfm-border-strong); background: var(--sfm-subtle); cursor: not-allowed; }
	.sfm-icon-btn.is-busy { cursor: progress; }
	.sfm-icon-btn-sm { width: 26px; height: 26px; }
	.sfm-disabled-wrap { display: inline-block; cursor: not-allowed; }
	.sfm-disabled-wrap .sfm-icon-btn { pointer-events: none; }
	.sfm-count { position: absolute; top: -6px; right: -6px; min-width: 16px; height: 16px; padding: 0 4px; border-radius: 8px; background: var(--sfm-primary); color: #fff; font-size: 10px; font-weight: 700; line-height: 16px; }
	.sfm-receipt-inline { display: inline-flex; align-items: center; gap: 8px; }

	/* ── Pagination ── */
	.sfm-pager { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 20px; border-top: 1px solid var(--sfm-border); }
	.sfm-pager:empty { display: none; }
	.sfm-pages { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
	.sfm-page-btn { display: inline-flex; align-items: center; justify-content: center; gap: 4px; min-width: 32px; height: 32px; padding: 0 8px; border-radius: 6px; border: 1px solid var(--sfm-border); background: var(--sfm-card); color: var(--sfm-text); font-size: 13px; cursor: pointer; transition: background-color .15s, border-color .15s, color .15s; }
	.sfm-page-btn:hover:not(:disabled):not(.is-active) { border-color: var(--sfm-primary); color: var(--sfm-primary-text); background: var(--sfm-primary-soft); }
	.sfm-page-btn.is-active { background: var(--sfm-primary); border-color: var(--sfm-primary); color: #fff; font-weight: 700; cursor: default; }
	.sfm-page-btn:disabled { opacity: .45; cursor: default; }
	.sfm-page-gap { color: var(--sfm-muted); padding: 0 4px; }

	/* ── Empty / error ── */
	.sfm-empty-state { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 48px 16px; text-align: center; }
	.sfm-empty-icon { width: 48px; height: 48px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; background: var(--sfm-primary-soft); color: var(--sfm-primary-text); margin-bottom: 4px; }
	.sfm-empty-title { font-size: 15px; font-weight: 600; color: var(--sfm-text); }
	.sfm-empty-state .sfm-btn { margin-top: 8px; }

	/* ── Student detail ── */
	.sfm-view-tabs { margin-bottom: -8px; }
	.sfm-report-tools { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
	/* Fee Reports page */
	/* Fee Certificates page */
	.sfm-back-btn { align-self: flex-start; margin-bottom: -8px; }
	.sfc-search-field { grid-column: span 2; }
	.sfc-table th.sfm-check, .sfc-table td.sfm-check { width: 36px; padding-right: 0; }
	.sfc-table input[type="checkbox"], .sfc-pick-list input[type="checkbox"], .sfc-pick-all input { width: 16px; height: 16px; accent-color: var(--sfm-primary); cursor: pointer; margin: 0; }
	.sfc-pick-empty { padding: 16px; text-align: center; border: 1px dashed var(--sfm-border-strong); border-radius: var(--sfm-radius); }
	.sfc-pick-head { padding: 8px 12px; border: 1px solid var(--sfm-border); border-bottom: none; border-radius: var(--sfm-radius) var(--sfm-radius) 0 0; background: var(--sfm-subtle); }
	.sfc-pick-all { display: flex; align-items: center; gap: 8px; margin: 0; font-weight: 600; font-size: 13px; cursor: pointer; }
	.sfc-pick-list { max-height: 320px; overflow: auto; border: 1px solid var(--sfm-border); border-radius: 0 0 var(--sfm-radius) var(--sfm-radius); }
	.sfc-pick-head + .sfc-pick-list { border-top: 1px solid var(--sfm-border); }
	.sfc-pick-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 8px 12px; margin: 0; font-size: 13px; font-weight: 400; border-bottom: 1px solid var(--sfm-border); cursor: pointer; }
	.sfc-pick-row:last-child { border-bottom: none; }
	.sfc-pick-row:hover { background: var(--sfm-primary-soft); }
	.sfm-field[hidden] { display: none; }
	a.sfm-btn, a.sfm-tab { text-decoration: none; }
	.sfm-filter-grid.sfr-filter-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
	.sfr-range { display: flex; align-items: center; gap: 8px; }
	.sfr-range .sfm-control { min-width: 0; flex: 1 1 0; padding: 0 8px; }
	.sfr-filter-grid .sfm-search-action { justify-content: flex-end; align-self: end; }
	.sfm-cert-search { min-width: 260px; }
	.sfm-nowrap { white-space: nowrap; }
	.sfm-report-table tfoot td { font-weight: 700; background: var(--sfm-subtle); border-top: 2px solid var(--sfm-primary); padding: 12px 14px; white-space: nowrap; }
	.sfm-report-table td { white-space: nowrap; }
	.sfm-report-table td.sfm-wrap { white-space: normal; min-width: 180px; }
	.sfm-tabs { display: flex; gap: 4px; box-shadow: inset 0 -1px 0 var(--sfm-border); overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; }
	.sfm-tab { display: inline-flex; align-items: center; gap: 8px; height: 44px; padding: 0 16px; background: none; border: none; border-bottom: 2px solid transparent; font-size: 13px; font-weight: 500; color: var(--sfm-muted); white-space: nowrap; cursor: pointer; transition: color .15s, border-color .15s, background-color .15s; border-radius: 6px 6px 0 0; }
	.sfm-tab:hover { color: var(--sfm-text); background: var(--sfm-primary-soft); }
	.sfm-tab.active { color: var(--sfm-primary-text); border-bottom-color: var(--sfm-primary); font-weight: 600; }
	.sfm-tab-count { min-width: 20px; height: 20px; padding: 0 6px; border-radius: 10px; background: var(--sfm-subtle); border: 1px solid var(--sfm-border); color: var(--sfm-muted); font-size: 11px; font-weight: 600; line-height: 18px; text-align: center; }
	.sfm-tab.active .sfm-tab-count { background: var(--sfm-primary); border-color: var(--sfm-primary); color: #fff; }
	.sfm-profile { display: flex; flex-wrap: wrap; gap: 20px; align-items: center; padding: 20px; }
	.sfm-avatar { width: 56px; height: 56px; border-radius: 50%; background: var(--sfm-primary-tint); color: var(--sfm-primary-text); display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 700; overflow: hidden; flex: none; }
	.sfm-avatar img { width: 100%; height: 100%; object-fit: cover; }
	.sfm-identity { min-width: 180px; display: flex; flex-direction: column; gap: 4px; }
	.sfm-name { font-size: 16px; font-weight: 700; }
	.sfm-pills { display: flex; gap: 6px; }
	.sfm-pill { font-size: 11px; font-weight: 600; padding: 1px 10px; border-radius: 999px; background: var(--sfm-primary-soft); color: var(--sfm-primary-text); border: 1px solid var(--sfm-primary-tint); }
	.sfm-pill-muted { background: var(--sfm-subtle); color: var(--sfm-muted); border-color: var(--sfm-border); }
	.sfm-metas { display: flex; flex-wrap: wrap; gap: 16px 24px; flex: 1; padding-right: 20px; border-right: 1px solid var(--sfm-border); min-width: 260px; }
	.sfm-meta { max-width: 320px; }
	.sfm-meta-value { overflow-wrap: break-word; }
	.sfm-sr-only { position: absolute !important; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
	.sfm-section-head:has(> .sfm-sr-only) { justify-content: flex-end; }
	.sfm-meta-label { font-size: 12px; font-weight: 600; }
	.sfm-meta-value { font-size: 12px; color: var(--sfm-muted); margin-top: 4px; }
	.sfm-tiles { display: flex; flex-wrap: wrap; gap: 12px; }
	.sfm-tile { display: flex; gap: 12px; align-items: center; border: 1px solid var(--sfm-border); border-radius: var(--sfm-radius); padding: 12px 16px; min-width: 180px; }
	.sfm-tile .sfm-kpi-icon { width: 34px; height: 34px; }
	.sfm-tile-value { font-size: 15px; font-weight: 700; font-variant-numeric: tabular-nums lining-nums; }
	.sfm-section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
	.sfm-section-title { margin: 0; font-family: var(--sfm-font); font-size: 17px; font-weight: 600; color: var(--sfm-text); }
	.sfm-tab-body .sfm-section-head { margin-bottom: 12px; }
	.sfm-tab-body .sfm-panel + .sfm-section-head { margin-top: 24px; }
	.sfm-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
	.sfm-chips { display: flex; gap: 6px; flex-wrap: wrap; }
	.sfm-chip { height: 30px; border: 1px solid var(--sfm-border); background: var(--sfm-card); color: var(--sfm-text); border-radius: 999px; padding: 0 12px; font-size: 12px; cursor: pointer; transition: background-color .15s, border-color .15s; }
	.sfm-chip:hover { border-color: var(--sfm-primary); }
	.sfm-chip span { color: var(--sfm-muted); margin-left: 2px; }
	.sfm-chip.active { border-color: var(--sfm-primary); color: var(--sfm-primary-text); background: var(--sfm-primary-tint); font-weight: 600; }
	.sfm-chip.active span { color: var(--sfm-primary-text); }
	.sfm .dropdown-menu { font-family: var(--sfm-font); font-size: 13px; }
	.sfm-dialog .modal-footer .btn-primary { background: var(--sfm-primary); border-color: var(--sfm-primary); color: #fff; font-family: var(--sfm-font); }
	.sfm-dialog .modal-footer .btn-primary:hover { background: var(--sfm-primary-hover); border-color: var(--sfm-primary-hover); }
	/* Columns menu */
	.sfm-col-pop { position: fixed; z-index: 1060; width: 260px; background: var(--sfm-card); color: var(--sfm-text); border: 1px solid var(--sfm-border); border-radius: var(--sfm-radius); box-shadow: 0 12px 32px rgba(16, 24, 40, .16); padding: 12px; font-family: var(--sfm-font); font-size: 13px; }
	.sfm-col-pop-title { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
	.sfm-col-pop .sfm-ms-option { display: flex; align-items: flex-start; gap: 8px; padding: 7px 8px; margin: 0; border-radius: 6px; font-size: 13px; font-weight: 400; cursor: pointer; }
	.sfm-col-pop .sfm-ms-option > span:nth-child(2) { flex: 1; overflow-wrap: anywhere; }
	.sfm-col-pop .sfm-ms-list { max-height: 232px; overflow-y: auto; overscroll-behavior: contain; }
	.sfm-col-pop-foot { display: flex; justify-content: space-between; gap: 8px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--sfm-border); }
	.sfm-col-pop-note { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--sfm-border); font-size: 11px; }
	.sfm-cols-btn.has-hidden { background: var(--sfm-primary-soft); }
	.sfm-cols-badge { margin-left: 2px; padding: 1px 6px; border-radius: 999px; background: var(--sfm-primary); color: #fff; font-size: 10.5px; font-weight: 700; }
	.sfm-th-sub { font-size: 10.5px; font-weight: 400; color: var(--sfm-muted); line-height: 1.2; margin-top: 1px; }
	.sfm-th-sub.sfm-inline { display: inline; margin: 0; }
	.sfm-subtab-bar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
	.sfm-subtabs { display: inline-flex; gap: 4px; padding: 4px; background: var(--sfm-subtle); border: 1px solid var(--sfm-border); border-radius: 10px; }
	.sfm-subtab { display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 14px; border: none; border-radius: 7px; background: none; color: var(--sfm-muted); font-size: 13px; font-weight: 500; cursor: pointer; transition: background-color .15s, color .15s; }
	.sfm-subtab:hover { color: var(--sfm-text); }
	.sfm-subtab.active { background: var(--sfm-card); color: var(--sfm-primary-text); font-weight: 600; box-shadow: 0 1px 3px rgba(16, 24, 40, .12); }
	.sfm-subtab.active .sfm-tab-count { background: var(--sfm-primary); border-color: var(--sfm-primary); color: #fff; }
	.sfm-subtab:focus-visible { outline: 2px solid var(--sfm-primary); outline-offset: 1px; }
	.sfm-kpi-grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-bottom: 16px; }
	.sfm-kpi-note { font-size: 11px; font-weight: 400; color: var(--sfm-muted); margin-left: 4px; }
	.sfm-scholar-card { padding: 16px 20px; margin-bottom: 20px; display: flex; flex-direction: column; gap: 12px; }
	.sfm-scholar-card .sfm-metas { border-right: none; padding-right: 0; }
	.sfm-bu-intro { margin-bottom: 14px; }
	.sfm-bu-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
	.sfm-bu-card { display: flex; flex-direction: column; gap: 10px; padding: 16px; border: 1px solid var(--sfm-border); border-radius: var(--sfm-radius); background: var(--sfm-card); }
	.sfm-bu-card p { margin: 0; flex: 1; }
	.sfm-bu-head { display: flex; align-items: center; gap: 10px; }
	.sfm-bu-head .sfm-kpi-icon { background: var(--sfm-primary-soft); color: var(--sfm-primary-text); border-color: var(--sfm-primary-tint); }
	.sfm-bu-title { font-weight: 700; font-size: 14px; }
	.sfm-bu-actions { display: flex; gap: 8px; flex-wrap: wrap; }
	.sfm-fc-filter { display: inline-block; }
	.sfm-fc-filter select { height: 30px; border-radius: 999px; font-size: 12px; min-width: 190px; max-width: 260px; }
	.sfm-fc-filter select.has-value { border-color: var(--sfm-primary); background: var(--sfm-primary-tint); color: var(--sfm-primary-text); font-weight: 600; }
	.sfm-move-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; padding: 12px; margin-bottom: 12px; border: 1px solid var(--sfm-border); border-radius: var(--sfm-radius); background: var(--sfm-subtle); }
	.sfm-move-summary div { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
	.sfm-alloc-table input { max-width: 150px; margin-left: auto; text-align: right; }
	.sfm-dialog .sfm-table-scroll { max-height: 60vh; }

	/* ── Responsive (container width = space beside the desk sidebar) ── */
	@container sfm (max-width: 1239px) {
		.sfm-kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
		.sfm-kpi-grid.sfm-kpi-grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
		.sfm-kpi-grid.sfm-kpi-grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
	}
	@container sfm (max-width: 1099px) {
		.sfm-filter-grid, .sfm-filter-grid.sfr-filter-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
		.sfm-search-btn { width: 100%; }
		.sfm-metas { border-right: none; padding-right: 0; }
	}
	@container sfm (max-width: 899px) {
		.sfm-kpi-grid.sfm-kpi-grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	}
	@container sfm (max-width: 699px) {
		.sfm-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
		.sfm-kpi-grid.sfm-kpi-grid-3 { grid-template-columns: minmax(0, 1fr); }
		.sfm-filter-grid, .sfm-filter-grid.sfr-filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
		.sfm-page-label { display: none; }
	}
	@container sfm (max-width: 459px) {
		.sfm-kpi-grid, .sfm-kpi-grid.sfm-kpi-grid-4, .sfm-kpi-grid.sfm-kpi-grid-3 { grid-template-columns: minmax(0, 1fr); }
		.sfm-filter-grid, .sfm-filter-grid.sfr-filter-grid { grid-template-columns: minmax(0, 1fr); padding: 16px; }
		.sfc-search-field { grid-column: auto; }
		.sfm-panel-head, .sfm-table-toolbar, .sfm-pager { padding: 12px 16px; }
		.sfm-pager { justify-content: center; }
		.sfm-title { font-size: 20px; }
		.sfm-head .sfm-btn { width: 100%; }
		.sfm-tiles, .sfm-tile { width: 100%; }
	}
	@media (max-width: 600px) {
		.sfm-shell { padding: 8px 16px 32px; gap: 16px; }
	}}`;
	$(`<style id="sfm-styles">${css}</style>`).appendTo("head");
}
