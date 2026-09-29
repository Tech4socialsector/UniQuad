// Student Fee Management
//   /desk/student-fee-management            → student list (year / term / programme filters)
//   /desk/student-fee-management/<student>  → that student's dues, payments and excess

const SFM_PAGE = "student-fee-management";
const SFM_API = "slcm.slcm.page.student_fee_management.student_fee_management.";
const SFM_PAGE_SIZES = [10, 25, 50, 100];

frappe.pages[SFM_PAGE].on_page_load = function (wrapper) {
	wrapper.sfm = new StudentFeeManagement(wrapper);
};

// Fires on first load and every time the user navigates back here (e.g. after saving a
// Fee Demand / Refund form), so the current view always reloads fresh numbers.
frappe.pages[SFM_PAGE].on_page_show = function (wrapper) {
	wrapper.sfm && wrapper.sfm.route();
};

const sfm_esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
// Indian grouping, symbol attached: ₹1,00,000.00
const sfm_money = (v) => "₹" + format_number(flt(v), "#,##,###.##", 2);
const sfm_int = (v) => format_number(cint(v), "#,##,###.##", 0);
const sfm_date = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 10)) : "—");

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

class StudentFeeManagement {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Student Fee Management"),
			single_column: true,
		});
		let page_length = 25;
		try {
			page_length = cint(localStorage.getItem("sfm_page_length")) || 25;
		} catch (e) {
			// storage blocked — fall back to the default
		}
		this.list_state = {
			academic_year: [],
			academic_term: [],
			programme: [],
			dues_status: [],
			search: "",
			start: 0,
			page_length: SFM_PAGE_SIZES.includes(page_length) ? page_length : 25,
			sort_by: "outstanding_amount",
			sort_order: "desc",
		};
		this.filter_options = null;
		this.last_totals = null;
		this.list_rows = [];
		this.list_req = 0;
		this.detail = null;
		this.dues_filter = "All";
		this.detail_tab = "dues";
		this.sch_subtab = "scholarship";
		this.selected = new Set();
		this.hidden_cols = new Set();
		try {
			this.hidden_cols = new Set(JSON.parse(localStorage.getItem("sfm_hidden_due_cols") || "[]"));
		} catch (e) {
			// storage blocked or bad value — show every column
		}
		this.ms = {};
		// Filter edits collect here and only reach list_state (and the server) when Search is pressed.
		this.draft = this.applied_filters();

		sfm_load_font();
		this.inject_styles();
		$(wrapper).addClass("sfm-page");
		this.$root = $(`<div class="sfm"></div>`).appendTo(this.page.main);
	}

	route() {
		const student = decodeURIComponent(frappe.get_route()[1] || "");
		if (student) {
			if (!this.detail || this.detail.profile.name !== student) {
				this.dues_filter = "All";
				this.dues_component = "";
				this.detail_tab = "dues";
			}
			this.show_student(student);
		} else {
			this.show_list();
		}
	}

	// ─────────────────────────────────────────────────────────────────────
	// Student list
	// ─────────────────────────────────────────────────────────────────────
	show_list() {
		this.close_col_menu();
		this.page.set_title(__("Student Fee Management"));
		this.page.clear_primary_action();
		this.page.clear_secondary_action();

		this.$root.off().html(`
			<div class="sfm-shell">
				<header class="sfm-head">
					<div>
						<h1 class="sfm-title">${__("Student Fee Management")}</h1>
						<p class="sfm-subtitle">${__("Track student fee payments, pending dues and receipts")}</p>
					</div>
					<div class="sfm-actions">
						<button type="button" class="sfm-btn sfm-btn-secondary" data-act="bulk-upload">
							${sfm_icon("upload", 15)}<span>${__("Bulk Upload")}</span>
						</button>
						<button type="button" class="sfm-btn sfm-btn-secondary" data-act="refresh">
							${sfm_icon("refresh", 15)}<span>${__("Refresh")}</span>
						</button>
					</div>
				</header>

				<section class="sfm-panel sfm-filter-panel" aria-labelledby="sfm-filter-title">
					<div class="sfm-panel-head">
						<h2 id="sfm-filter-title" class="sfm-panel-title">${sfm_icon("filter", 15)}${__("Filter & Search")}</h2>
						<button type="button" class="sfm-btn sfm-btn-ghost sfm-btn-sm" data-act="clear">
							${sfm_icon("x", 14)}<span>${__("Clear filters")}</span>
						</button>
					</div>
					<div class="sfm-filter-grid">
						<div class="sfm-field" data-ms-key="academic_year"></div>
						<div class="sfm-field" data-ms-key="academic_term"></div>
						<div class="sfm-field sfm-field-wide" data-ms-key="programme"></div>
						<div class="sfm-field" data-ms-key="dues_status"></div>
						<div class="sfm-field sfm-field-wide">
							<label for="sfm-f-search">${__("Search")}</label>
							<div class="sfm-search-wrap">
								${sfm_icon("search", 15, "sfm-search-icon")}
								<input id="sfm-f-search" type="search" class="sfm-control" data-f="search"
									placeholder="${__("Name, ID, registration no. or email")}" autocomplete="off">
							</div>
						</div>
						<div class="sfm-field sfm-search-action">
							<button type="button" class="sfm-btn sfm-btn-primary sfm-search-btn" data-act="apply">
								${sfm_icon("search", 15)}<span>${__("Search")}</span>
							</button>
						</div>
					</div>
				</section>

				<section class="sfm-kpi-grid" aria-label="${__("Summary")}"></section>

				<section class="sfm-panel sfm-table-panel" aria-labelledby="sfm-table-title">
					<div class="sfm-table-toolbar">
						<div>
							<h2 id="sfm-table-title" class="sfm-panel-title">${__("Students")}</h2>
							<div class="sfm-muted sfm-table-caption" aria-live="polite"></div>
						</div>
						<div class="sfm-page-size">
							<label for="sfm-page-size">${__("Rows per page")}</label>
							<div class="sfm-select-wrap">
								<select id="sfm-page-size" class="sfm-control sfm-control-sm">
									${SFM_PAGE_SIZES.map((n) => `<option value="${n}">${n}</option>`).join("")}
								</select>
								${sfm_icon("chevron-down", 14, "sfm-select-caret")}
							</div>
						</div>
					</div>
					<div class="sfm-table-scroll">
						<table class="sfm-table sfm-student-table">
							<thead><tr>
								${[
									["student", __("Student")],
									["programme", __("Programme")],
									["year_term", __("Year / Term")],
									["batch", __("Batch")],
									["demand_count", __("Demands"), "num"],
									["total_payable", __("Total Payable"), "num"],
									["paid_amount", __("Paid"), "num"],
									["outstanding_amount", __("Pending"), "num"],
									["excess_amount", __("Excess"), "num"],
									["status", __("Status")],
								]
									.map(
										([key, label, cls = ""]) =>
											`<th scope="col" class="${cls}" data-sort-col="${key}"><button type="button" class="sfm-sort" data-sort="${key}">${label}<span class="sfm-sort-icon"></span></button></th>`
									)
									.join("")}
								<th scope="col" class="center">${__("Receipt")}</th>
							</tr></thead>
							<tbody></tbody>
						</table>
					</div>
					<footer class="sfm-pager"></footer>
				</section>
			</div>
		`);

		this.draft = this.applied_filters(); // unapplied edits from an earlier visit are discarded
		this.build_filters();
		this.bind_list_events();
		this.render_sort_indicators();
		this.$root.find("#sfm-page-size").val(this.list_state.page_length);
		this.load_students();

		if (this.filter_options) {
			this.render_filter_options();
		} else {
			frappe.call({ method: SFM_API + "get_filter_options" }).then((r) => {
				this.filter_options = r.message;
				this.render_filter_options();
			});
		}
	}

	build_filters() {
		const s = this.draft;
		const make = (key, label, all_label, searchable = false) =>
			new SfmMultiSelect(this.$root.find(`[data-ms-key="${key}"]`), {
				key,
				label,
				all_label,
				searchable,
				on_change: (value) => {
					s[key] = value;
					if (key === "academic_year") this.render_filter_options();
					this.update_dirty();
				},
			});
		this.ms = {
			academic_year: make("academic_year", __("Academic Year"), __("All Years")),
			academic_term: make("academic_term", __("Term"), __("All Terms")),
			programme: make("programme", __("Programme"), __("All Programmes"), true),
			dues_status: make("dues_status", __("Dues Status"), __("All Students")),
		};
		this.ms.dues_status.set_options(SFM_DUES_STATUS_OPTIONS, s.dues_status);
		this.ms.academic_year.set_options([], s.academic_year);
		this.ms.academic_term.set_options([], s.academic_term);
		this.ms.programme.set_options([], s.programme);

		// Close any open filter dropdown on an outside click.
		$(document)
			.off("mousedown.sfm-ms")
			.on("mousedown.sfm-ms", (e) => {
				if (!$(e.target).closest(".sfm-ms").length) Object.values(this.ms).forEach((m) => m.close());
			});
	}

	render_filter_options() {
		const o = this.filter_options;
		const s = this.draft;
		if (!o || !this.ms.academic_year) return;

		this.ms.academic_year.set_options(o.academic_years.map((y) => ({ value: y, label: y })), s.academic_year);
		s.academic_year = this.ms.academic_year.value();

		// Terms follow the chosen years; a term name can repeat across years, so dedupe.
		const terms = [
			...new Set(
				o.terms
					.filter((t) => !s.academic_year.length || s.academic_year.includes(t.academic_year))
					.map((t) => t.academic_term)
			),
		];
		this.ms.academic_term.set_options(terms.map((t) => ({ value: t, label: t })), s.academic_term);
		s.academic_term = this.ms.academic_term.value();

		this.ms.programme.set_options(
			o.programmes.map((p) => ({
				value: p.name,
				label: p.program_name && p.program_name !== p.name ? `${p.name} — ${p.program_name}` : p.name,
			})),
			s.programme
		);
		s.programme = this.ms.programme.value();
		this.ms.dues_status.set_options(SFM_DUES_STATUS_OPTIONS, s.dues_status);
		this.$root.find('[data-f="search"]').val(s.search);
	}

	applied_filters() {
		const s = this.list_state;
		return {
			academic_year: [...s.academic_year],
			academic_term: [...s.academic_term],
			programme: [...s.programme],
			dues_status: [...s.dues_status],
			search: s.search,
		};
	}

	// Push the draft filters to list_state and reload from page 1.
	apply_filters() {
		Object.values(this.ms).forEach((m) => m.close());
		const d = this.draft;
		Object.assign(this.list_state, {
			academic_year: [...d.academic_year],
			academic_term: [...d.academic_term],
			programme: [...d.programme],
			dues_status: [...d.dues_status],
			search: (d.search || "").trim(),
			start: 0,
		});
		this.update_dirty();
		this.load_students();
	}

	// Flag the Search button while the filters on screen differ from the ones the table shows.
	update_dirty() {
		const norm = (f) => JSON.stringify({ ...f, search: (f.search || "").trim() });
		const dirty = norm(this.draft) !== norm(this.applied_filters());
		this.$root
			.find(".sfm-search-btn")
			.toggleClass("is-dirty", dirty)
			.attr("title", dirty ? __("Filters changed — click Search to apply") : __("Search"));
	}

	has_active_filters() {
		const s = this.list_state;
		return !!(s.academic_year.length || s.academic_term.length || s.programme.length || s.dues_status.length || s.search);
	}

	clear_filters() {
		Object.assign(this.list_state, {
			academic_year: [],
			academic_term: [],
			programme: [],
			dues_status: [],
			search: "",
			start: 0,
		});
		this.draft = this.applied_filters();
		Object.values(this.ms).forEach((m) => m.set_options(m.options, []));
		this.render_filter_options();
		this.update_dirty();
		this.load_students();
	}

	bind_list_events() {
		const s = this.list_state;
		const $r = this.$root;

		$r.on("input", '[data-f="search"]', (e) => {
			this.draft.search = $(e.currentTarget).val();
			this.update_dirty();
		});
		$r.on("keydown", '[data-f="search"]', (e) => {
			if (e.key === "Enter") {
				e.preventDefault();
				this.apply_filters();
			}
		});
		$r.on("click", '[data-act="apply"]', () => this.apply_filters());
		$r.on("click", '[data-act="clear"]', () => this.clear_filters());
		$r.on("click", '[data-act="refresh"]', () => this.load_students());
		$r.on("click", '[data-act="bulk-upload"]', () => this.bulk_upload_dialog());
		$r.on("click", '[data-act="retry"]', () => this.load_students());

		$r.on("change", "#sfm-page-size", (e) => {
			s.page_length = cint($(e.currentTarget).val()) || 25;
			s.start = 0;
			try {
				localStorage.setItem("sfm_page_length", s.page_length);
			} catch (err) {
				// storage blocked — the choice just won't be remembered
			}
			this.load_students();
		});

		$r.on("click", ".sfm-sort", (e) => {
			const key = $(e.currentTarget).data("sort");
			if (s.sort_by === key) {
				s.sort_order = s.sort_order === "asc" ? "desc" : "asc";
			} else {
				const text_cols = ["student", "programme", "year_term", "batch"];
				s.sort_by = key;
				s.sort_order = text_cols.includes(key) ? "asc" : "desc";
			}
			s.start = 0;
			this.render_sort_indicators();
			this.load_students();
		});

		$r.on("click", ".sfm-pager [data-page]", (e) => {
			const page = cint($(e.currentTarget).data("page"));
			s.start = Math.max(0, (page - 1) * s.page_length);
			this.load_students();
		});

		// Whole row opens the student; the name is a real link for keyboard / middle-click users.
		$r.on("click", ".sfm-student-row", (e) => {
			if ($(e.target).closest("a, button, .sfm-receipt-cell").length) return;
			frappe.set_route(SFM_PAGE, $(e.currentTarget).data("student"));
		});
		$r.on("click", ".sfm-student-link", (e) => {
			if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
			e.preventDefault();
			frappe.set_route(SFM_PAGE, $(e.currentTarget).closest("tr").data("student"));
		});

		$r.on("click", ".sfm-receipt-btn", (e) => {
			e.stopPropagation();
			const $btn = $(e.currentTarget);
			const row = this.list_rows.find((x) => x.student === $btn.closest("tr").data("student"));
			if (!row || !row.receipt_count) return;
			if (row.receipt_count === 1) this.download_receipt(row.latest_receipt, $btn);
			else this.receipts_dialog(row);
		});
	}

	// ── Bulk upload (Fee Demand / Fee Payment / Fee Concession) ──────────
	// Download the office's sheet (pre-filled where it applies), then import it through Data Import.
	async bulk_upload_dialog() {
		const types = [
			{
				doctype: "Fee Demand",
				icon: "file-text",
				title: __("Fee Demands"),
				text: __("Create new dues. The sheet is blank; Voucher No. is assigned by the system. A Students sheet lists every Student ID."),
				submit: 0,
			},
			{
				doctype: "Fee Payment",
				icon: "card",
				title: __("Fee Payments"),
				text: __("Record payments against open dues. The sheet comes pre-filled with the dues; fill only the yellow payment columns."),
				submit: 1,
			},
			{
				doctype: "Fee Concession",
				icon: "award",
				title: __("Fee Concessions"),
				text: __("Apply scholarships / waivers to open dues. Pre-filled with the dues; fill only the yellow concession columns."),
				submit: 1,
			},
		].filter((t) => frappe.model.can_create(t.doctype));
		if (!types.length) return frappe.msgprint(__("You don't have permission to create fee demands, payments or concessions."));

		const dialog = new frappe.ui.Dialog({ title: __("Bulk Upload"), size: "large" });
		dialog.$wrapper.addClass("sfm-dialog");
		$(dialog.body).html(`
			<p class="sfm-muted sfm-bu-intro">${__("1. Download the template  ·  2. Fill the highlighted columns  ·  3. Import it. Headers match the fields, so no column mapping is needed.")}</p>
			<div class="sfm-bu-grid">
				${types
					.map(
						(t) => `<div class="sfm-bu-card">
							<div class="sfm-bu-head"><span class="sfm-kpi-icon">${sfm_icon(t.icon, 18)}</span><div class="sfm-bu-title">${t.title}</div></div>
							<p class="sfm-muted">${t.text}</p>
							<div class="sfm-bu-actions">
								<button type="button" class="sfm-btn sfm-btn-secondary sfm-btn-sm" data-bu-download="${t.doctype}">${sfm_icon("download", 14)}<span>${__("Download Template")}</span></button>
								<button type="button" class="sfm-btn sfm-btn-primary sfm-btn-sm" data-bu-import="${t.doctype}" data-submit="${t.submit}">${sfm_icon("upload", 14)}<span>${__("Import")}</span></button>
							</div>
						</div>`
					)
					.join("")}
			</div>
		`);
		$(dialog.body).on("click", "[data-bu-download]", async (e) => {
			const doctype = $(e.currentTarget).data("bu-download");
			if (!window.slcm_download_bulk_template) await frappe.require("/assets/slcm/js/bulk_upload_template.js");
			window.slcm_download_bulk_template(doctype);
		});
		$(dialog.body).on("click", "[data-bu-import]", (e) => {
			const doctype = $(e.currentTarget).data("bu-import");
			dialog.hide();
			// Data Import, ready for the filled sheet; payments / concessions are submitted after import
			frappe.new_doc("Data Import", {
				reference_doctype: doctype,
				import_type: "Insert New Records",
				submit_after_import: cint($(e.currentTarget).data("submit")),
			});
		});
		dialog.show();
	}

	render_sort_indicators() {
		const s = this.list_state;
		this.$root.find("th[data-sort-col]").each((_, th) => {
			const key = $(th).data("sort-col");
			const active = key === s.sort_by;
			$(th)
				.toggleClass("is-sorted", active)
				.attr("aria-sort", active ? (s.sort_order === "asc" ? "ascending" : "descending") : "none")
				.find(".sfm-sort-icon")
				.html(sfm_icon(active ? `sort-${s.sort_order}` : "sort-none", 13));
		});
	}

	render_kpis(totals) {
		const loading = !totals;
		const t = totals || {};
		const cards = [
			["users", __("Students"), sfm_int(t.student_count), "neutral"],
			["rupee", __("Total Payable"), sfm_money(t.total_payable), "primary"],
			["check", __("Collected"), sfm_money(t.paid_amount), "success"],
			["clock", __("Pending Dues"), sfm_money(t.outstanding_amount), "warning"],
			["alert", __("Overdue"), sfm_money(t.overdue_amount), "danger"],
			["wallet", __("Excess Amount"), sfm_money(t.excess_amount), "neutral"],
		];
		this.$root.find(".sfm-kpi-grid").html(
			cards
				.map(
					([icon, label, value, tone]) => `
				<div class="sfm-kpi sfm-kpi-${tone}">
					<span class="sfm-kpi-icon">${sfm_icon(icon, 18)}</span>
					<div class="sfm-kpi-body">
						<div class="sfm-kpi-label">${label}</div>
						<div class="sfm-kpi-value">${loading ? '<span class="sfm-skel sfm-skel-value"></span>' : value}</div>
					</div>
				</div>`
				)
				.join("")
		);
	}

	render_skeleton_rows() {
		const n = Math.min(this.list_state.page_length, 8);
		const cell = (w, cls = "") => `<td class="${cls}"><span class="sfm-skel" style="width:${w}"></span></td>`;
		this.$root.find(".sfm-student-table tbody").html(
			Array.from({ length: n })
				.map(
					() => `<tr class="sfm-skel-row" aria-hidden="true">
					<td><span class="sfm-skel" style="width:70%"></span><span class="sfm-skel sfm-skel-sm" style="width:45%"></span><span class="sfm-skel sfm-skel-sm" style="width:60%"></span></td>
					${cell("80%")}${cell("70%")}${cell("60%")}${cell("40%", "num")}${cell("75%", "num")}${cell("75%", "num")}${cell("75%", "num")}${cell("65%", "num")}${cell("80%")}${cell("32px", "center")}
				</tr>`
				)
				.join("")
		);
	}

	async load_students() {
		const s = this.list_state;
		const req = ++this.list_req;

		this.render_kpis(this.last_totals);
		this.$root.find(".sfm-kpi-grid").toggleClass("is-refreshing", !!this.last_totals);
		this.render_skeleton_rows();
		this.$root.find(".sfm-table-panel").attr("aria-busy", "true");
		this.$root.find(".sfm-table-caption").text(__("Loading students…"));
		this.$root.find('[data-act="refresh"]').prop("disabled", true).find(".sfm-icon").addClass("sfm-spin");

		let result;
		try {
			const r = await frappe.call({ method: SFM_API + "get_students", args: s });
			result = r.message;
		} catch (e) {
			result = null;
		}
		if (req !== this.list_req) return; // a newer filter change already superseded this request

		this.$root.find(".sfm-table-panel").attr("aria-busy", "false");
		this.$root.find(".sfm-kpi-grid").removeClass("is-refreshing");
		this.$root.find('[data-act="refresh"]').prop("disabled", false).find(".sfm-icon").removeClass("sfm-spin");

		if (!result) {
			this.$root.find(".sfm-table-caption").text("");
			this.$root.find(".sfm-student-table tbody").html(`
				<tr><td colspan="11">
					<div class="sfm-empty-state">
						<span class="sfm-empty-icon">${sfm_icon("alert", 22)}</span>
						<div class="sfm-empty-title">${__("Couldn't load students")}</div>
						<div class="sfm-muted">${__("Check your connection and try again.")}</div>
						<button type="button" class="sfm-btn sfm-btn-primary" data-act="retry">${sfm_icon("refresh", 15)}<span>${__("Retry")}</span></button>
					</div>
				</td></tr>`);
			this.$root.find(".sfm-pager").empty();
			return;
		}

		const { rows, totals } = result;
		this.list_rows = rows;
		this.last_totals = totals;
		this.render_kpis(totals);
		this.render_student_rows(rows);
		this.render_pager(cint(totals.student_count), rows.length);
	}

	render_student_rows(rows) {
		const $tbody = this.$root.find(".sfm-student-table tbody");
		if (!rows.length) {
			const filtered = this.has_active_filters();
			$tbody.html(`
				<tr><td colspan="11">
					<div class="sfm-empty-state">
						<span class="sfm-empty-icon">${sfm_icon("search-x", 22)}</span>
						<div class="sfm-empty-title">${__("No students found")}</div>
						<div class="sfm-muted">${
							filtered ? __("Try changing your filters or search criteria.") : __("No student records exist yet.")
						}</div>
						${
							filtered
								? `<button type="button" class="sfm-btn sfm-btn-primary" data-act="clear">${sfm_icon("x", 14)}<span>${__("Clear Filters")}</span></button>`
								: ""
						}
					</div>
				</td></tr>`);
			return;
		}

		$tbody.html(
			rows
				.map((d) => {
					let status;
					if (!cint(d.demand_count)) status = sfm_badge("No Demands", __("No Demands"));
					else if (flt(d.overdue_amount) > 0) status = sfm_badge("Overdue", __("Overdue"));
					else if (flt(d.outstanding_amount) > 0) status = sfm_badge("Pending", __("Pending"));
					else status = sfm_badge("Cleared", __("Cleared"));

					const name = d.student_name || d.student;
					const email = d.official_email_id || d.email;
					const count = cint(d.receipt_count);
					const receipt = count
						? `<button type="button" class="sfm-icon-btn sfm-receipt-btn"
								aria-label="${sfm_esc(__("Download receipt for {0}", [name]))}"
								title="${sfm_esc(count > 1 ? __("Download receipt ({0} available)", [count]) : __("Download Receipt"))}">
								${sfm_icon("download", 16)}${count > 1 ? `<span class="sfm-count">${count}</span>` : ""}
							</button>`
						: `<span class="sfm-disabled-wrap" title="${__("Receipt not available")}">
								<button type="button" class="sfm-icon-btn" disabled aria-label="${sfm_esc(__("Receipt not available for {0}", [name]))}">
									${sfm_icon("download", 16)}
								</button>
							</span>`;

					return `<tr class="sfm-student-row" data-student="${sfm_esc(d.student)}">
						<td>
							<a class="sfm-student-link" href="/desk/${SFM_PAGE}/${encodeURIComponent(d.student)}">${sfm_esc(name)}</a>
							<div class="sfm-sub">${sfm_esc(d.registration_id || d.student)}</div>
							${email ? `<div class="sfm-sub sfm-ellipsis" title="${sfm_esc(email)}">${sfm_esc(email)}</div>` : ""}
						</td>
						<td class="sfm-wrap">${sfm_esc(d.programme_of_study || "—")}</td>
						<td>${sfm_esc(d.academic_year || "—")}${d.academic_term ? `<div class="sfm-sub">${sfm_esc(d.academic_term)}</div>` : ""}</td>
						<td class="sfm-wrap sfm-batch">${sfm_esc(d.batch || "—")}</td>
						<td class="num">${cint(d.demand_count)}</td>
						<td class="num">${sfm_money(d.total_payable)}</td>
						<td class="num">${sfm_money(d.paid_amount)}</td>
						<td class="num sfm-amount-strong">${sfm_money(d.outstanding_amount)}</td>
						<td class="num">${flt(d.excess_amount) ? sfm_money(d.excess_amount) : '<span class="sfm-sub">—</span>'}</td>
						<td>${status}</td>
						<td class="center sfm-receipt-cell">${receipt}</td>
					</tr>`;
				})
				.join("")
		);
	}

	render_pager(total, shown) {
		const s = this.list_state;
		const pages = Math.max(1, Math.ceil(total / s.page_length));
		const current = Math.floor(s.start / s.page_length) + 1;
		const from = total ? s.start + 1 : 0;
		const to = Math.min(s.start + shown, total);
		
		this.$root
			.find(".sfm-table-caption")
			.text(total ? (total === 1 ? __("1 student matches the current filters") : __("{0} students match the current filters", [sfm_int(total)])) : "");

		if (!total) {
			this.$root.find(".sfm-pager").empty();
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

		this.$root.find(".sfm-pager").html(`
			<div class="sfm-muted">${(total === 1 ? __("Showing 1 of 1 student") : __("Showing {0} to {1} of {2} students", [sfm_int(from), sfm_int(to), sfm_int(total)]))}</div>
			<nav class="sfm-pages" aria-label="${__("Pagination")}">
				${nav(1, sfm_icon("chevrons-left", 15), __("First page"), current === 1)}
				${nav(current - 1, sfm_icon("chevron-left", 15) + `<span class="sfm-page-label">${__("Previous")}</span>`, __("Previous page"), current === 1)}
				${page_btns}
				${nav(current + 1, `<span class="sfm-page-label">${__("Next")}</span>` + sfm_icon("chevron-right", 15), __("Next page"), current === pages)}
				${nav(pages, sfm_icon("chevrons-right", 15), __("Last page"), current === pages)}
			</nav>
		`);
	}

	// ── Receipts ─────────────────────────────────────────────────────────
	// Downloads an existing Fee Receipt rendered with its standard print format.
	async download_receipt(receipt, $btn) {
		const swap_icon = (name, cls) => $btn && $btn.find(".sfm-icon").first().replaceWith(sfm_icon(name, $btn.hasClass("sfm-icon-btn-sm") ? 14 : 16, cls));
		if ($btn) $btn.prop("disabled", true).addClass("is-busy");
		swap_icon("loader", "sfm-spin");
		try {
			const res = await fetch(`/api/method/${SFM_API}download_receipt?receipt=${encodeURIComponent(receipt)}`, {
				credentials: "same-origin",
				headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
			});
			const type = res.headers.get("content-type") || "";
			if (!res.ok || !type.includes("pdf")) {
				let msg = __("Receipt {0} could not be generated.", [receipt]);
				try {
					msg = sfm_server_message(await res.json()) || msg;
				} catch (e) {
					// non-JSON error body — keep the generic message
				}
				frappe.msgprint({ title: __("Receipt not available"), message: sfm_esc(msg), indicator: "red" });
				return;
			}
			const url = URL.createObjectURL(await res.blob());
			const a = document.createElement("a");
			a.href = url;
			a.download = `${receipt.replace(/[\s/]/g, "-")}.pdf`;
			document.body.appendChild(a);
			a.click();
			a.remove();
			setTimeout(() => URL.revokeObjectURL(url), 2000);
		} catch (e) {
			frappe.msgprint({ title: __("Receipt not available"), message: __("Network error while downloading {0}.", [receipt]), indicator: "red" });
		} finally {
			if ($btn) $btn.prop("disabled", false).removeClass("is-busy");
			swap_icon("download", "");
		}
	}

	async receipts_dialog(row) {
		const r = await frappe.call({ method: SFM_API + "get_student_receipts", args: { student: row.student } });
		this.receipt_picker(__("Receipts — {0}", [row.student_name || row.student]), r.message || []);
	}

	// Lists several receipts with a download button each. `rc.demands` (what the receipt paid for) is optional.
	receipt_picker(title, receipts) {
		const show_towards = receipts.some((rc) => rc.demands);
		const dialog = new frappe.ui.Dialog({ title, size: "large" });
		dialog.$wrapper.addClass("sfm-dialog");
		$(dialog.body).html(
			receipts.length
				? `<div class="sfm-table-scroll"><table class="sfm-table">
					<thead><tr>
						<th scope="col">${__("Receipt No.")}</th><th scope="col">${__("Date")}</th>
						${show_towards ? `<th scope="col">${__("Paid Towards")}</th>` : ""}<th scope="col">${__("Mode")}</th>
						<th scope="col" class="num">${__("Amount")}</th><th scope="col" class="center">${__("Download")}</th>
					</tr></thead>
					<tbody>${receipts
						.map(
							(rc) => `<tr>
						<td class="sfm-strong">${sfm_esc(rc.name)}</td>
						<td>${sfm_date(rc.receipt_date)}</td>
						${show_towards ? `<td class="sfm-wrap">${(rc.demands || []).map(sfm_esc).join("<br>") || "—"}</td>` : ""}
						<td>${sfm_esc(rc.payment_mode || "—")}${rc.reference_number ? `<div class="sfm-sub">${sfm_esc(rc.reference_number)}</div>` : ""}</td>
						<td class="num sfm-amount-strong">${sfm_money(rc.amount)}</td>
						<td class="center"><button type="button" class="sfm-icon-btn" data-receipt="${sfm_esc(rc.name)}"
							aria-label="${sfm_esc(__("Download receipt {0}", [rc.name]))}" title="${__("Download Receipt")}">${sfm_icon("download", 16)}</button></td>
					</tr>`
						)
						.join("")}</tbody>
				</table></div>`
				: `<div class="sfm-empty-state"><div class="sfm-empty-title">${__("Receipt not available")}</div></div>`
		);
		$(dialog.body).on("click", "[data-receipt]", (e) => this.download_receipt($(e.currentTarget).data("receipt"), $(e.currentTarget)));
		dialog.show();
	}

	// ─────────────────────────────────────────────────────────────────────
	// Student detail
	// ─────────────────────────────────────────────────────────────────────
	async show_student(student) {
		this.page.set_title(__("Student Due Details"));
		this.page.clear_primary_action();
		this.page.clear_secondary_action();
		if (!this.detail || this.detail.profile.name !== student) {
			this.$root.off().html(`<div class="sfm-shell"><div class="sfm-panel sfm-empty-state">${sfm_icon("loader", 22, "sfm-spin")}<div class="sfm-muted">${__("Loading…")}</div></div></div>`);
		}

		const r = await frappe.call({ method: SFM_API + "get_student_dues", args: { student } });
		this.detail = r.message;
		// Drop selections for demands that are gone or no longer selectable.
		const names = new Set(this.detail.demands.map((d) => d.name));
		this.selected = new Set([...this.selected].filter((n) => names.has(n)));
		this.render_student();
	}

	render_student() {
		$(document).off("mousedown.sfm-ms");
		this.close_col_menu();
		const { profile: p, summary: s } = this.detail;
		const initial = sfm_esc((p.first_name || p.name).trim().charAt(0).toUpperCase());
		const avatar = p.passport_size_photo ? `<img src="${sfm_esc(p.passport_size_photo)}" alt="">` : initial;
		const meta = (label, value) =>
			`<div class="sfm-meta"><div class="sfm-meta-label">${label}</div><div class="sfm-meta-value">${sfm_esc(value || "—")}</div></div>`;

		this.$root.off().html(`
			<div class="sfm-shell">
				<a class="sfm-btn sfm-btn-secondary sfm-btn-sm sfm-back" href="/desk/${SFM_PAGE}" role="button">${sfm_icon("arrow-left", 14)}<span>${__("All Students")}</span></a>
				<header class="sfm-head">
					<div>
						<h1 class="sfm-title">${__("Student Due Details")}</h1>
						<p class="sfm-subtitle">${__("Dues, payments and excess for {0}", [sfm_esc(p.first_name || p.name)])}</p>
					</div>
					<button type="button" class="sfm-btn sfm-btn-secondary" data-act="refresh-student">
						${sfm_icon("refresh", 15)}<span>${__("Refresh")}</span>
					</button>
				</header>
				<div class="sfm-panel sfm-profile">
					<div class="sfm-avatar">${avatar}</div>
					<div class="sfm-identity">
						<div class="sfm-name">${sfm_esc(p.first_name || p.name)}</div>
						<div class="sfm-sub">${sfm_esc(p.registration_id || p.name)}</div>
						<div class="sfm-pills">
							${p.student_status ? `<span class="sfm-pill sfm-pill-muted">${sfm_esc(p.student_status)}</span>` : ""}
						</div>
						<div class="sfm-sub">${sfm_esc(p.official_email_id || p.email || "")}</div>
					</div>
					<div class="sfm-metas">
						${meta(__("Programme"), p.program_name || p.programme_of_study)}
						${meta(__("Year / Term"), [p.academic_year, p.academic_term].filter(Boolean).join(" · "))}
					</div>
					<div class="sfm-tiles">
						<div class="sfm-tile sfm-kpi-warning"><span class="sfm-kpi-icon">${sfm_icon("rupee", 16)}</span><div><div class="sfm-kpi-label">${__("Pending Dues")}</div><div class="sfm-tile-value">${sfm_money(s.pending_amount)}</div></div></div>
						<div class="sfm-tile sfm-kpi-neutral"><span class="sfm-kpi-icon">${sfm_icon("wallet", 16)}</span><div><div class="sfm-kpi-label">${__("Excess Amount")}</div><div class="sfm-tile-value">${sfm_money(s.excess_amount)}</div></div></div>
					</div>
				</div>
				<div class="sfm-tabs" role="tablist" aria-label="${__("Student sections")}">
					${[
						["dues", "file-text", __("Manage Dues"), this.detail.demands.length],
						["payments", "card", __("Payments"), this.detail.payments.length],
						["excess", "wallet", __("Excess Breakdown"), this.detail.credit_notes.length],
						["scholarship", "award", __("Scholarship / Stipend"), this.detail.concessions.length + this.detail.stipends.length],
					]
						.map(
							([key, icon, label, n]) =>
								`<button type="button" role="tab" class="sfm-tab" id="sfm-tab-${key}" data-tab="${key}" aria-controls="sfm-tab-body">${sfm_icon(icon, 16)}<span>${label}</span><span class="sfm-tab-count">${n}</span></button>`
						)
						.join("")}
				</div>
				<div class="sfm-tab-body" id="sfm-tab-body" role="tabpanel"></div>
			</div>
		`);

		this.$root.find(".sfm-back").on("click", (e) => {
			e.preventDefault();
			frappe.set_route(SFM_PAGE);
		});
		this.$root.find('[data-act="refresh-student"]').on("click", () => this.show_student(p.name));
		this.$root.find(".sfm-tab").on("click", (e) => {
			this.detail_tab = $(e.currentTarget).data("tab");
			this.render_tab();
		});
		// Arrow keys move between tabs (WAI-ARIA tabs pattern)
		this.$root.find(".sfm-tabs").on("keydown", ".sfm-tab", (e) => {
			if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
			e.preventDefault();
			const $tabs = this.$root.find(".sfm-tab");
			const i = $tabs.index(e.currentTarget);
			const next = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: $tabs.length - 1 }[e.key];
			$tabs.eq((next + $tabs.length) % $tabs.length).trigger("focus").trigger("click");
		});
		this.render_tab();
	}

	render_tab() {
		this.$root.find(".sfm-tab").each((_, t) => {
			const active = $(t).data("tab") === this.detail_tab;
			$(t).toggleClass("active", active).attr({ "aria-selected": active, tabindex: active ? 0 : -1 });
		});
		this.$root.find(".sfm-tab-body").attr("aria-labelledby", `sfm-tab-${this.detail_tab}`);
		this.close_col_menu();
		const $body = this.$root.find(".sfm-tab-body").off();
		if (this.detail_tab === "payments") this.render_payments($body);
		else if (this.detail_tab === "excess") this.render_excess($body);
		else if (this.detail_tab === "scholarship") this.render_scholarship($body);
		else this.render_dues($body);
	}

	// ── Manage Dues ──────────────────────────────────────────────────────
	render_dues($body) {
		const all_cols = this.due_columns();
		const cols = all_cols.filter((c) => !this.hidden_cols.has(c.key));
		const n_hidden = all_cols.length - cols.length;
		const components = [...new Set(this.detail.demands.map((d) => d.fee_component).filter(Boolean))].sort();
		if (this.dues_component && !components.includes(this.dues_component)) this.dues_component = "";
		const demands = this.dues_component
			? this.detail.demands.filter((d) => d.fee_component === this.dues_component)
			: this.detail.demands;
		const filters = ["All", "Pending", "Overdue", "Partially Paid", "Paid", "Waived", "Moved to Excess", "Cancelled", "Cancelled & Moved to Excess"];
		const count = (f) => (f === "All" ? demands.length : demands.filter((d) => sfm_demand_status(d) === f).length);
		const shown = this.dues_filter === "All" ? demands : demands.filter((d) => sfm_demand_status(d) === this.dues_filter);
		// Actions only ever apply to dues the user can see.
		const visible = new Set(shown.map((d) => d.name));
		this.selected = new Set([...this.selected].filter((n) => visible.has(n)));

		$body.html(`
			<div class="sfm-section-head">
				<h2 class="sfm-section-title sfm-sr-only">${__("Manage Dues")}</h2>
				<div class="sfm-actions">
					<button type="button" class="sfm-btn sfm-btn-secondary" data-act="refund">${sfm_icon("undo", 15)}<span>${__("Issue Refund")}</span></button>
					<button type="button" class="sfm-btn sfm-btn-primary" data-act="create">${sfm_icon("plus", 15)}<span>${__("Create a due")}</span></button>
				</div>
			</div>
			<div class="sfm-panel sfm-table-panel">
				<div class="sfm-table-toolbar">
					<div class="sfm-chips" role="group" aria-label="${__("Filter dues by status")}">
						${filters
							.filter((f) => f === "All" || count(f))
							.map(
								(f) =>
									`<button type="button" class="sfm-chip ${f === this.dues_filter ? "active" : ""}" data-filter="${f}" aria-pressed="${f === this.dues_filter}">${__(f)} <span>${count(f)}</span></button>`
							)
							.join("")}
						${
							components.length > 1
								? `<div class="sfm-select-wrap sfm-fc-filter">
									<select class="sfm-control sfm-control-sm ${this.dues_component ? "has-value" : ""}" data-dues-component aria-label="${__("Filter by Fee Component")}">
										<option value="">${__("All Fee Components")}</option>
										${components.map((c) => `<option value="${sfm_esc(c)}" ${c === this.dues_component ? "selected" : ""}>${sfm_esc(c)}</option>`).join("")}
									</select>
									${sfm_icon("chevron-down", 14, "sfm-select-caret")}
								</div>`
								: ""
						}
					</div>
					<div class="sfm-actions">
						<span class="sfm-muted sfm-sel-count" aria-live="polite"></span>
						<button type="button" class="sfm-btn sfm-btn-secondary sfm-cols-btn ${n_hidden ? "has-hidden" : ""}" data-cols-menu
							aria-haspopup="dialog" aria-expanded="false" title="${__("Show or hide columns")}">
							${sfm_icon("columns", 15)}<span>${__("Columns")}</span>${n_hidden ? `<span class="sfm-cols-badge">${__("{0} hidden", [n_hidden])}</span>` : ""}
						</button>
						<button type="button" class="sfm-btn sfm-btn-secondary" data-act="multi-pay">${__("Multiple Due Payment")}</button>
						<div class="dropdown">
							<button type="button" class="sfm-btn sfm-btn-primary dropdown-toggle" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">${__("Actions")}</button>
							<ul class="dropdown-menu dropdown-menu-right">
								<li><a class="dropdown-item" href="#" data-act="pay">${__("Record Payment")}</a></li>
								<li><a class="dropdown-item" href="#" data-act="excess">${__("Adjust from Excess")}</a></li>
								<li><a class="dropdown-item" href="#" data-act="move-excess">${__("Move to Excess")}</a></li>
								<li><a class="dropdown-item" href="#" data-act="waiver">${__("Apply Waiver / Concession")}</a></li>
								<li><a class="dropdown-item" href="#" data-act="refund-demand">${__("Issue Refund for Due")}</a></li>
								<li><a class="dropdown-item" href="#" data-act="open">${__("Open Voucher")}</a></li>
								<li class="dropdown-divider"></li>
								<li><a class="dropdown-item text-danger" href="#" data-act="cancel">${__("Cancel Due")}</a></li>
							</ul>
						</div>
					</div>
				</div>
				<div class="sfm-table-scroll">
					<table class="sfm-table sfm-dues-table">
						<thead><tr>
							<th scope="col" class="sfm-check"><input type="checkbox" class="sfm-check-all" aria-label="${__("Select all dues")}"></th>
							${cols.map((c) => `<th scope="col" class="${c.cls || ""}">${c.label}${c.sub ? `<div class="sfm-th-sub">${c.sub}</div>` : ""}</th>`).join("")}
						</tr></thead>
						<tbody>
							${
								shown.length
									? shown
											.map(
												(d) => `<tr class="${this.selected.has(d.name) ? "selected" : ""}" data-name="${sfm_esc(d.name)}">
								<td class="sfm-check"><input type="checkbox" class="sfm-row-check" aria-label="${sfm_esc(__("Select {0}", [d.name]))}" ${this.selected.has(d.name) ? "checked" : ""}></td>
								${cols.map((c) => c.cell(d)).join("")}
							</tr>`
											)
											.join("")
									: `<tr><td colspan="${cols.length + 1}"><div class="sfm-empty-state"><div class="sfm-empty-title">${__("No dues in this view")}</div></div></td></tr>`
							}
						</tbody>
					</table>
				</div>
			</div>
		`);

		const sync = () => {
			const n = this.selected.size;
			$body.find(".sfm-sel-count").text(n ? __("{0} selected", [n]) : "");
			const boxes = $body.find(".sfm-row-check");
			const checked = boxes.filter(":checked").length;
			$body
				.find(".sfm-check-all")
				.prop("checked", boxes.length && checked === boxes.length)
				.prop("indeterminate", checked > 0 && checked < boxes.length);
		};
		sync();

		$body.on("click", ".sfm-chip", (e) => {
			this.dues_filter = $(e.currentTarget).data("filter");
			this.render_tab();
		});
		$body.on("change", "[data-dues-component]", (e) => {
			this.dues_component = $(e.currentTarget).val();
			this.render_tab();
		});
		$body.on("change", ".sfm-row-check", (e) => {
			const $tr = $(e.currentTarget).closest("tr");
			const name = $tr.data("name");
			e.currentTarget.checked ? this.selected.add(name) : this.selected.delete(name);
			$tr.toggleClass("selected", e.currentTarget.checked);
			sync();
		});
		$body.on("change", ".sfm-check-all", (e) => {
			$body.find(".sfm-row-check").prop("checked", e.currentTarget.checked).trigger("change");
		});
		$body.on("click", ".sfm-dues-table tbody tr[data-name] td:not(.sfm-check):not(.sfm-receipt-cell)", (e) => {
			if ($(e.target).closest("a, button").length) return;
			$(e.currentTarget).closest("tr").find(".sfm-row-check").trigger("click");
		});
		$body.on("click", "[data-act]", (e) => {
			e.preventDefault();
			this.dues_action($(e.currentTarget).data("act"));
		});
		$body.on("click", "[data-cols-menu]", (e) => {
			e.stopPropagation();
			this.open_col_menu(e.currentTarget);
		});
		$body.on("click", ".sfm-demand-receipt", (e) => {
			e.stopPropagation();
			const $btn = $(e.currentTarget);
			const d = this.detail.demands.find((x) => x.name === $btn.closest("tr").data("name"));
			if (!d || !d.receipts.length) return;
			if (d.receipts.length === 1) this.download_receipt(d.receipts[0].name, $btn);
			else this.receipt_picker(__("Receipts for {0}", [d.name]), d.receipts);
		});
	}

	// Every column of the dues table; any of them can be hidden from the Columns menu.
	due_columns() {
		return [
			{
				key: "fee_component",
				label: __("Fee Component"),
				cell: (d) =>
					`<td class="sfm-wrap-cell sfm-fc-cell"><div class="sfm-strong">${sfm_esc(d.fee_component || "—")}</div><div class="sfm-sub">${sfm_esc(d.demand_type || "")}${d.academic_year ? " · " + sfm_esc(d.academic_year) : ""}</div></td>`,
			},
			{
				key: "voucher",
				label: __("Voucher No."),
				cell: (d) => `<td><a class="sfm-link" href="${frappe.utils.get_form_link("Fee Demand", d.name)}">${sfm_esc(d.name)}</a></td>`,
			},
			{ key: "status", label: __("Due Status"), cell: (d) => `<td class="sfm-wrap-cell sfm-status-cell">${sfm_badge(sfm_demand_status(d))}</td>` },
			{ key: "due_date", label: __("Due Date"), cell: (d) => `<td>${sfm_date(d.due_date)}</td>` },
			{ key: "created", label: __("Date of Creation"), cell: (d) => `<td>${sfm_date(d.demand_date || d.creation)}</td>` },
			{ key: "amount", label: __("Amount"), cls: "num", cell: (d) => `<td class="num">${sfm_money(d.original_amount)}</td>` },
			{ key: "penalty", label: __("Penalty"), cls: "num", cell: (d) => `<td class="num">${sfm_money(d.penalty_amount)}</td>` },
			{ key: "waiver", label: __("Scholarship"), sub: __("Waiver"), cls: "num", cell: (d) => `<td class="num">${sfm_money(d.waiver_amount)}</td>` },
			{ key: "payable", label: __("Total Payable"), cls: "num", cell: (d) => `<td class="num">${sfm_money(d.net_payable)}</td>` },
			{
				key: "paid",
				label: __("Paid Amount"),
				cls: "num",
				cell: (d) => `<td class="num">${sfm_money(flt(d.paid_amount) + flt(d.credit_adjusted))}</td>`,
			},
			{
				key: "pending",
				label: __("Pending Amount"),
				cls: "num",
				cell: (d) => `<td class="num sfm-amount-strong">${sfm_money(d.outstanding_amount)}</td>`,
			},
			{
				key: "remark",
				label: __("Remark"),
				cell: (d) =>
					`<td class="sfm-wrap-cell sfm-remark-cell" title="${sfm_esc(d.remarks || d.description || "")}"><span class="sfm-clamp">${sfm_esc(d.remarks || d.description || "—")}</span></td>`,
			},
			{
				key: "receipt",
				label: __("Receipt"),
				cls: "center sfm-receipt-th",
				cell: (d) => `<td class="center sfm-receipt-cell">${this.demand_receipt_button(d)}</td>`,
			},
		];
	}

	save_hidden_cols() {
		try {
			localStorage.setItem("sfm_hidden_due_cols", JSON.stringify([...this.hidden_cols]));
		} catch (e) {
			// storage blocked — the choice just won't be remembered next visit
		}
	}

	close_col_menu() {
		if (!this.$col_pop) return;
		if (this.col_pop_cleanup) this.col_pop_cleanup();
		this.col_pop_cleanup = null;
		this.$col_pop.remove();
		this.$col_pop = null;
		$(document).off(".sfm-colpop");
		$(window).off(".sfm-colpop");
		this.$root.find('[data-cols-menu][aria-expanded="true"]').attr("aria-expanded", "false");
	}

	// Show / hide columns. Changes apply straight away and stay open, so several can be toggled in a row.
	open_col_menu(btn, focus_key = null) {
		if (this.$col_pop && !focus_key) return this.close_col_menu();
		this.close_col_menu();
		const all_cols = this.due_columns();

		const $pop = $(`<div class="sfm-dialog sfm-col-pop" role="dialog" aria-label="${__("Show or hide columns")}">
			<div class="sfm-col-pop-title">${__("Show columns")}</div>
			<div class="sfm-ms-actions">
				<button type="button" data-cm="all">${__("Show all")}</button>
				<button type="button" data-cm="clear" title="${__("Hide every column except Fee Component, then tick the ones you need")}">${__("Clear")}</button>
			</div>
			<div class="sfm-ms-list">
				${all_cols
					.map(
						(c) => `<label class="sfm-ms-option">
							<input type="checkbox" value="${c.key}" ${this.hidden_cols.has(c.key) ? "" : "checked"}>
							<span>${c.label}${c.sub ? ` <span class="sfm-th-sub sfm-inline">(${c.sub})</span>` : ""}</span>
						</label>`
					)
					.join("")}
			</div>
			<div class="sfm-muted sfm-col-pop-note">${__("Your choice is remembered on this browser.")}</div>
		</div>`).appendTo("body");
		this.$col_pop = $pop;
		$(btn).attr("aria-expanded", "true");

		const place = () => {
			if (!btn.isConnected) return this.close_col_menu();
			const r = btn.getBoundingClientRect();
			const w = $pop.outerWidth();
			const top = Math.min(r.bottom + 6, window.innerHeight - $pop.outerHeight() - 8);
			$pop.css({ top: Math.max(8, top), left: Math.max(8, Math.min(r.right - w, window.innerWidth - w - 8)) });
		};
		place();

		// Re-render the table, then reopen the menu on the new Columns button.
		const apply = (key) => {
			this.save_hidden_cols();
			this.render_tab();
			const new_btn = this.$root.find("[data-cols-menu]")[0];
			if (new_btn) this.open_col_menu(new_btn, key || "__none__");
		};
		$pop.on("change", "input", (e) => {
			const key = e.currentTarget.value;
			if (e.currentTarget.checked) this.hidden_cols.delete(key);
			else if (this.hidden_cols.size >= all_cols.length - 1) {
				e.currentTarget.checked = true;
				return frappe.show_alert({ message: __("At least one column must stay visible."), indicator: "orange" });
			} else this.hidden_cols.add(key);
			apply(key);
		});
		$pop.on("click", '[data-cm="all"]', () => {
			this.hidden_cols.clear();
			apply();
		});
		// The table always keeps one column, so Clear leaves Fee Component (it identifies each row).
		$pop.on("click", '[data-cm="clear"]', () => {
			this.hidden_cols = new Set(all_cols.map((c) => c.key).filter((k) => k !== "fee_component"));
			apply();
		});
		$pop.on("keydown", (e) => {
			if (e.key === "Escape") {
				this.close_col_menu();
				const b = this.$root.find("[data-cols-menu]")[0];
				if (b) b.focus();
			}
		});
		setTimeout(() => {
			$(document).on("mousedown.sfm-colpop", (e) => {
				if (!$(e.target).closest(".sfm-col-pop, [data-cols-menu]").length) this.close_col_menu();
			});
			$(window).on("resize.sfm-colpop", () => this.close_col_menu());
			window.addEventListener("scroll", place, true);
			this.col_pop_cleanup = () => window.removeEventListener("scroll", place, true);
		});
		const target = focus_key && focus_key !== "__none__" ? $pop.find(`input[value="${focus_key}"]`)[0] : $pop.find("input")[0];
		if (target) target.focus();
	}

	demand_receipt_button(d) {
		const n = (d.receipts || []).length;
		if (!n) {
			return `<span class="sfm-disabled-wrap" title="${__("Receipt not available")}">
				<button type="button" class="sfm-icon-btn" disabled aria-label="${sfm_esc(__("Receipt not available for {0}", [d.name]))}">${sfm_icon("download", 16)}</button>
			</span>`;
		}
		return `<button type="button" class="sfm-icon-btn sfm-demand-receipt"
			aria-label="${sfm_esc(__("Download receipt for {0}", [d.name]))}"
			title="${sfm_esc(n > 1 ? __("Download receipt ({0} available)", [n]) : __("Download Receipt"))}">
			${sfm_icon("download", 16)}${n > 1 ? `<span class="sfm-count">${n}</span>` : ""}
		</button>`;
	}

	selected_demands() {
		return this.detail.demands.filter((d) => this.selected.has(d.name));
	}

	single_selected() {
		const sel = this.selected_demands();
		if (sel.length !== 1) {
			frappe.show_alert({ message: __("Select exactly one due for this action."), indicator: "orange" });
			return null;
		}
		return sel[0];
	}

	dues_action(act) {
		const p = this.detail.profile;
		const sel = this.selected_demands();
		let d;

		switch (act) {
			case "create":
				frappe.new_doc("Fee Demand", {
					student: p.name,
					program: p.programme_of_study,
					programme: p.batch,
					academic_year: p.academic_year,
					demand_date: frappe.datetime.get_today(),
				});
				break;

			case "refund":
				frappe.new_doc("Fee Refund", { student: p.name, refund_date: frappe.datetime.get_today() });
				break;

			case "multi-pay": {
				const payable = (sel.length ? sel : this.detail.demands).filter(SFM_PAYABLE);
				if (!payable.length) {
					frappe.msgprint(__("There are no dues with a pending amount to pay."));
					return;
				}
				this.payment_dialog(payable);
				break;
			}

			case "pay": {
				if (!sel.length) return frappe.show_alert({ message: __("Select at least one due."), indicator: "orange" });
				const payable = sel.filter(SFM_PAYABLE);
				if (!payable.length) return frappe.msgprint(__("None of the selected dues has a pending amount."));
				this.payment_dialog(payable);
				break;
			}

			case "excess":
				if (!(d = this.single_selected())) return;
				this.excess_dialog(d);
				break;

			case "waiver":
				if (!(d = this.single_selected())) return;
				if (!SFM_PAYABLE(d)) return frappe.msgprint(__("A waiver can only be applied to a due with a pending amount."));
				frappe.new_doc("Fee Concession", { student: p.name, fee_demand: d.name });
				break;

			case "refund-demand":
				if (!(d = this.single_selected())) return;
				if (!(flt(d.paid_amount) > 0)) return frappe.msgprint(__("Nothing has been paid against {0} yet.", [d.name]));
				frappe.new_doc("Fee Refund", { student: p.name, fee_demand: d.name, refund_date: frappe.datetime.get_today() });
				break;

			case "open":
				if (!(d = this.single_selected())) return;
				frappe.set_route("Form", "Fee Demand", d.name);
				break;

			case "move-excess":
				if (!(d = this.single_selected())) return;
				this.move_to_excess_dialog(d);
				break;

			case "cancel":
				if (!(d = this.single_selected())) return;
				this.cancel_dialog(d);
				break;
		}
	}

	async payment_dialog(demands) {
		const student = this.detail.profile.name;
		await frappe.model.with_doctype("Fee Payment");
		const bank_accounts = ((frappe.meta.get_docfield("Fee Payment", "university_bank_account") || {}).options || "").split("\n");
		const dialog = new frappe.ui.Dialog({
			title: __("Record Payment"),
			size: "large",
			fields: [
				{ fieldtype: "HTML", fieldname: "alloc" },
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Select",
					fieldname: "payment_mode",
					label: __("Payment Mode"),
					reqd: 1,
					options: ["Cash", "Bank Transfer", "Cheque", "Credit Card", "Debit Card", "Online Payment", "Other"],
					default: "Bank Transfer",
				},
				{ fieldtype: "Date", fieldname: "payment_date", label: __("Payment Date"), reqd: 1, default: frappe.datetime.get_today() },
				{ fieldtype: "Date", fieldname: "settlement_date", label: __("Settlement Date") },
				{ fieldtype: "Select", fieldname: "university_bank_account", label: __("University bank account"), options: bank_accounts },
				{ fieldtype: "Data", fieldname: "bank_name", label: __("Bank Name") },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Data", fieldname: "reference_number", label: __("Reference / UTR No.") },
				{ fieldtype: "Date", fieldname: "transaction_date", label: __("Transaction Date") },
				{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
			],
			primary_action_label: __("Record Payment"),
			primary_action: (values) => {
				if (!(values.remarks || "").trim()) return frappe.msgprint(__("Remarks are mandatory."));
				const allocations = [];
				let invalid = null;
				$alloc.find("input.sfm-alloc").each((_, el) => {
					const amount = flt(el.value);
					const max = flt($(el).data("max"));
					if (amount < 0 || amount > max) invalid = $(el).data("name");
					if (amount > 0) allocations.push({ fee_demand: $(el).data("name"), amount });
				});
				if (invalid) return frappe.msgprint(__("Amount for {0} must be between 0 and its pending amount.", [invalid]));
				if (!allocations.length) return frappe.msgprint(__("Enter an amount for at least one due."));

				const total = allocations.reduce((a, r) => a + r.amount, 0);
				frappe.confirm(__("Record a {0} payment of <b>{1}</b> against {2} due(s)?", [values.payment_mode, sfm_money(total), allocations.length]), async () => {
					const r = await frappe.call({
						method: SFM_API + "record_payment",
						args: { student, allocations, ...values },
						freeze: true,
						freeze_message: __("Recording payment…"),
					});
					dialog.hide();
					const { payment, receipt } = r.message;
					frappe.show_alert(
						{
							message: receipt ? __("Payment {0} recorded · Receipt {1}", [payment, receipt]) : __("Payment {0} recorded", [payment]),
							indicator: "green",
						},
						7
					);
					this.selected.clear();
					this.show_student(student);
				});
			},
		});
		dialog.$wrapper.addClass("sfm-dialog");

		const $alloc = dialog.fields_dict.alloc.$wrapper;
		$alloc.html(`
			<table class="sfm-table sfm-alloc-table">
				<thead><tr>
					<th scope="col">${__("Voucher No.")}</th><th scope="col">${__("Fee Component")}</th>
					<th scope="col" class="num">${__("Pending")}</th><th scope="col" class="num">${__("Paying Now")}</th>
				</tr></thead>
				<tbody>
					${demands
						.map(
							(d) => `<tr>
						<td>${sfm_esc(d.name)}</td>
						<td>${sfm_esc(d.fee_component || "")}</td>
						<td class="num">${sfm_money(d.outstanding_amount)}</td>
						<td class="num"><input type="number" class="form-control input-sm sfm-alloc" min="0" step="0.01"
							aria-label="${sfm_esc(__("Amount paying now for {0}", [d.name]))}"
							data-name="${sfm_esc(d.name)}" data-max="${flt(d.outstanding_amount)}" value="${flt(d.outstanding_amount)}"></td>
					</tr>`
						)
						.join("")}
				</tbody>
				<tfoot><tr><td colspan="3" class="num sfm-strong">${__("Total")}</td><td class="num sfm-amount-strong sfm-alloc-total"></td></tr></tfoot>
			</table>
		`);
		const update_total = () => {
			let total = 0;
			$alloc.find("input.sfm-alloc").each((_, el) => (total += flt(el.value)));
			$alloc.find(".sfm-alloc-total").text(sfm_money(total));
		};
		$alloc.on("input", "input.sfm-alloc", update_total);
		update_total();
		dialog.show();
	}

	excess_dialog(d) {
		const excess = flt(this.detail.summary.excess_amount);
		if (excess <= 0) return frappe.msgprint(__("This student has no excess amount to adjust."));
		if (!SFM_PAYABLE(d)) return frappe.msgprint(__("{0} has no pending amount.", [d.name]));

		const max = Math.min(excess, flt(d.outstanding_amount));
		const dialog = new frappe.ui.Dialog({
			title: __("Adjust from Excess"),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "info",
					options: `<p class="sfm-muted">${__("Due {0}: pending {1}. Available excess: {2}.", [sfm_esc(d.name), sfm_money(d.outstanding_amount), sfm_money(excess)])}</p>`,
				},
				{ fieldtype: "Currency", fieldname: "amount", label: __("Amount to Adjust"), reqd: 1, default: max, options: "INR" },
				{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
			],
			primary_action_label: __("Adjust"),
			primary_action: async ({ amount, remarks }) => {
				if (flt(amount) <= 0 || flt(amount) > max) return frappe.msgprint(__("Amount must be between 0 and {0}.", [sfm_money(max)]));
				if (!(remarks || "").trim()) return frappe.msgprint(__("Remarks are mandatory."));
				await frappe.call({
					method: SFM_API + "apply_excess_credit",
					args: { student: this.detail.profile.name, fee_demand: d.name, amount, remarks },
					freeze: true,
				});
				dialog.hide();
				frappe.show_alert({ message: __("Adjusted {0} against {1}", [sfm_money(amount), d.name]), indicator: "green" });
				this.show_student(this.detail.profile.name);
			},
		});
		dialog.$wrapper.addClass("sfm-dialog");
		dialog.show();
	}

	cancel_dialog(d) {
		if (flt(d.paid_amount) > 0) {
			return frappe.msgprint(__("{0} has payments against it. Move the paid amount to excess or refund it before cancelling.", [d.name]));
		}
		const dialog = new frappe.ui.Dialog({
			title: __("Cancel Due {0}", [d.name]),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "info",
					options: `<p class="sfm-muted">${__("{0} · {1}. This cannot be undone.", [sfm_esc(d.fee_component || d.name), sfm_money(d.net_payable)])}</p>`,
				},
				{ fieldtype: "Small Text", fieldname: "remarks", label: __("Reason / Remarks"), reqd: 1 },
			],
			primary_action_label: __("Cancel Due"),
			primary_action: async ({ remarks }) => {
				if (!(remarks || "").trim()) return frappe.msgprint(__("Remarks are mandatory."));
				await frappe.call({ method: SFM_API + "cancel_demand", args: { fee_demand: d.name, remarks }, freeze: true });
				dialog.hide();
				frappe.show_alert({ message: __("Due {0} cancelled", [d.name]), indicator: "green" });
				this.selected.delete(d.name);
				this.show_student(this.detail.profile.name);
			},
		});
		dialog.$wrapper.addClass("sfm-dialog");
		dialog.get_primary_btn().removeClass("btn-primary").addClass("btn-danger");
		dialog.show();
	}

	// Paid money on a due → student's excess (a new Student Credit Note).
	move_to_excess_dialog(d) {
		const paid = flt(d.paid_amount);
		if (d.status === "Cancelled") return frappe.msgprint(__("{0} is cancelled.", [d.name]));
		if (paid <= 0) return frappe.msgprint(__("Nothing has been paid against {0}, so there is nothing to move to excess.", [d.name]));

		const dialog = new frappe.ui.Dialog({
			title: __("Move to Excess"),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "info",
					options: `<div class="sfm-move-summary">
						<div><span class="sfm-muted">${__("Due")}</span><b>${sfm_esc(d.name)}</b></div>
						<div><span class="sfm-muted">${__("Fee Component")}</span><b>${sfm_esc(d.fee_component || "—")}</b></div>
						<div><span class="sfm-muted">${__("Paid Amount")}</span><b>${sfm_money(paid)}</b></div>
						<div><span class="sfm-muted">${__("Pending Amount")}</span><b>${sfm_money(d.outstanding_amount)}</b></div>
					</div>
					<p class="sfm-muted">${__("The amount is taken off this due's paid amount and added to the student's excess. The due's pending amount goes up by the same amount unless you cancel it.")}</p>`,
				},
				{ fieldtype: "Currency", fieldname: "amount", label: __("Amount to Move"), reqd: 1, default: paid, options: "INR" },
				{
					fieldtype: "Select",
					fieldname: "credit_type",
					label: __("Excess Type"),
					reqd: 1,
					options: ["Overpayment", "Advance Deposit", "Scholarship Credit", "Other"],
					default: "Overpayment",
				},
				{ fieldtype: "Column Break" },
				{ fieldtype: "Link", fieldname: "academic_year", label: __("Academic Year"), options: "Academic Year", default: d.academic_year || this.detail.profile.academic_year },
				{
					fieldtype: "Check",
					fieldname: "cancel_due",
					label: __("Cancel this due after moving"),
					description: __("Only when the full paid amount is moved."),
				},
				{ fieldtype: "Section Break" },
				{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
			],
			primary_action_label: __("Move to Excess"),
			primary_action: (v) => {
				const amount = flt(v.amount);
				if (amount <= 0 || amount > paid) return frappe.msgprint(__("Amount must be between 0 and {0}.", [sfm_money(paid)]));
				if (v.cancel_due && amount < paid) return frappe.msgprint(__("To cancel the due, move the full paid amount ({0}).", [sfm_money(paid)]));
				if (!(v.remarks || "").trim()) return frappe.msgprint(__("Remarks are mandatory."));
				frappe.confirm(
					__("Move <b>{0}</b> from {1} to the student's excess?", [sfm_money(amount), sfm_esc(d.name)]) +
						(v.cancel_due ? "<br>" + __("The due will then be cancelled.") : ""),
					async () => {
						const r = await frappe.call({
							method: SFM_API + "move_to_excess",
							args: { student: this.detail.profile.name, fee_demand: d.name, ...v, cancel_due: v.cancel_due ? 1 : 0 },
							freeze: true,
							freeze_message: __("Moving to excess…"),
						});
						dialog.hide();
						frappe.show_alert({ message: __("{0} moved to excess · {1}", [sfm_money(amount), r.message.credit_note]), indicator: "green" }, 7);
						this.selected.delete(d.name);
						this.show_student(this.detail.profile.name);
					}
				);
			},
		});
		dialog.$wrapper.addClass("sfm-dialog");
		dialog.show();
	}

	// ── Payments ─────────────────────────────────────────────────────────
	render_payments($body) {
		const payments = this.detail.payments;
		const s = this.detail.summary;
		$body.html(`
			<div class="sfm-section-head"><h2 class="sfm-section-title sfm-sr-only">${__("Payments")}</h2>
				<div class="sfm-muted">${__("Total paid against dues")}: <b class="sfm-amount-strong">${sfm_money(s.paid_amount)}</b></div>
			</div>
			<div class="sfm-panel sfm-table-panel"><div class="sfm-table-scroll">
				<table class="sfm-table">
					<thead><tr>
						<th scope="col">${__("Payment No.")}</th><th scope="col">${__("Date")}</th><th scope="col">${__("Mode")}</th>
						<th scope="col">${__("Reference")}</th><th scope="col">${__("Bank Account")}</th><th scope="col">${__("Allocated To")}</th>
						<th scope="col" class="num">${__("Amount")}</th><th scope="col">${__("Receipt")}</th><th scope="col">${__("Status")}</th>
					</tr></thead>
					<tbody>
						${
							payments.length
								? payments
										.map(
											(p) => `<tr>
							<td><a class="sfm-link" href="${frappe.utils.get_form_link("Fee Payment", p.name)}">${sfm_esc(p.name)}</a></td>
							<td>${sfm_date(p.payment_date)}</td>
							<td>${sfm_esc(p.payment_mode || "—")}</td>
							<td>${sfm_esc(p.reference_number || "—")}</td>
							<td class="sfm-wrap">${sfm_esc(p.university_bank_account || "—")}</td>
							<td>${(p.allocations || []).map((a) => `<div>${sfm_esc(a.fee_demand)} <span class="sfm-sub">· ${sfm_money(a.amount_allocated)}</span></div>`).join("") || "—"}</td>
							<td class="num sfm-amount-strong">${sfm_money(p.amount)}</td>
							<td>${
								p.receipt
									? `<div class="sfm-receipt-inline">
										<a class="sfm-link" href="${frappe.utils.get_form_link("Fee Receipt", p.receipt)}">${sfm_esc(p.receipt)}</a>
										<button type="button" class="sfm-icon-btn sfm-icon-btn-sm" data-receipt="${sfm_esc(p.receipt)}"
											aria-label="${sfm_esc(__("Download receipt {0}", [p.receipt]))}" title="${__("Download Receipt")}">${sfm_icon("download", 14)}</button>
									</div>`
									: '<span class="sfm-sub">—</span>'
							}</td>
							<td>${sfm_badge(p.status || ["Draft", "Submitted", "Cancelled"][p.docstatus])}</td>
						</tr>`
										)
										.join("")
								: `<tr><td colspan="9"><div class="sfm-empty-state"><div class="sfm-empty-title">${__("No payments recorded for this student")}</div></div></td></tr>`
						}
					</tbody>
				</table>
			</div></div>
		`);
		$body.on("click", "[data-receipt]", (e) => this.download_receipt($(e.currentTarget).data("receipt"), $(e.currentTarget)));
	}

	// ── Excess Breakdown ─────────────────────────────────────────────────
	render_excess($body) {
		const { credit_notes, refunds } = this.detail;
		const total = credit_notes.reduce((a, c) => a + flt(c.credit_amount), 0);
		const used = credit_notes.reduce((a, c) => a + flt(c.used_credit), 0);
		const kpi = (icon, label, value, tone) =>
			`<div class="sfm-kpi sfm-kpi-${tone}"><span class="sfm-kpi-icon">${sfm_icon(icon, 18)}</span><div class="sfm-kpi-body"><div class="sfm-kpi-label">${label}</div><div class="sfm-kpi-value">${value}</div></div></div>`;

		$body.html(`
			<div class="sfm-section-head"><h2 class="sfm-section-title sfm-sr-only">${__("Excess Breakdown")}</h2>
				<button type="button" class="sfm-btn sfm-btn-secondary" data-act="new-credit">${sfm_icon("plus", 15)}<span>${__("Add Excess / Credit")}</span></button>
			</div>
			<div class="sfm-kpi-grid sfm-kpi-grid-4">
				${kpi("wallet", __("Total Excess Received"), sfm_money(total), "primary")}
				${kpi("check", __("Adjusted Against Dues"), sfm_money(used), "neutral")}
				${kpi("rupee", __("Available Excess"), sfm_money(this.detail.summary.excess_amount), "success")}
				${kpi("undo", __("Refunded"), sfm_money(this.detail.summary.refunded_amount), "neutral")}
			</div>
			<div class="sfm-panel sfm-table-panel"><div class="sfm-table-scroll">
				<table class="sfm-table">
					<thead><tr>
						<th scope="col">${__("Credit Note")}</th><th scope="col">${__("Type")}</th><th scope="col">${__("Academic Year")}</th>
						<th scope="col" class="num">${__("Credit")}</th><th scope="col" class="num">${__("Used")}</th><th scope="col" class="num">${__("Available")}</th>
						<th scope="col">${__("Adjusted Against")}</th><th scope="col">${__("Status")}</th>
					</tr></thead>
					<tbody>
						${
							credit_notes.length
								? credit_notes
										.map(
											(c) => `<tr>
							<td><a class="sfm-link" href="${frappe.utils.get_form_link("Student Credit Note", c.name)}">${sfm_esc(c.name)}</a></td>
							<td>${sfm_esc(c.credit_type || "—")}</td>
							<td>${sfm_esc(c.academic_year || "—")}</td>
							<td class="num">${sfm_money(c.credit_amount)}</td>
							<td class="num">${sfm_money(c.used_credit)}</td>
							<td class="num sfm-amount-strong">${sfm_money(c.available_credit)}</td>
							<td>${(c.adjustments || []).map((a) => `<div>${sfm_esc(a.fee_demand)} <span class="sfm-sub">· ${sfm_money(a.amount_adjusted)} · ${sfm_date(a.adjusted_on)}</span></div>`).join("") || "—"}</td>
							<td>${sfm_badge(c.status)}</td>
						</tr>`
										)
										.join("")
								: `<tr><td colspan="8"><div class="sfm-empty-state"><div class="sfm-empty-title">${__("No excess / credit notes for this student")}</div></div></td></tr>`
						}
					</tbody>
				</table>
			</div></div>

			<div class="sfm-section-head"><h2 class="sfm-section-title">${__("Refunds")}</h2></div>
			<div class="sfm-panel sfm-table-panel"><div class="sfm-table-scroll">
				<table class="sfm-table">
					<thead><tr>
						<th scope="col">${__("Refund No.")}</th><th scope="col">${__("Due")}</th><th scope="col">${__("Type")}</th><th scope="col">${__("Date")}</th>
						<th scope="col">${__("Mode")}</th><th scope="col">${__("UTR")}</th><th scope="col" class="num">${__("Amount")}</th><th scope="col">${__("Status")}</th>
					</tr></thead>
					<tbody>
						${
							refunds.length
								? refunds
										.map(
											(r) => `<tr>
							<td><a class="sfm-link" href="${frappe.utils.get_form_link("Fee Refund", r.name)}">${sfm_esc(r.name)}</a></td>
							<td>${sfm_esc(r.fee_demand || "—")}<div class="sfm-sub">${sfm_esc(r.fee_component || "")}</div></td>
							<td>${sfm_esc(r.refund_type || "—")}</td>
							<td>${sfm_date(r.refund_date)}</td>
							<td>${sfm_esc(r.refund_mode || "—")}</td>
							<td>${sfm_esc(r.utr_number || "—")}</td>
							<td class="num sfm-amount-strong">${sfm_money(r.refund_amount)}</td>
							<td>${sfm_badge(r.status)}</td>
						</tr>`
										)
										.join("")
								: `<tr><td colspan="8"><div class="sfm-empty-state"><div class="sfm-empty-title">${__("No refunds for this student")}</div></div></td></tr>`
						}
					</tbody>
				</table>
			</div></div>
		`);
		$body.find('[data-act="new-credit"]').on("click", () =>
			frappe.new_doc("Student Credit Note", {
				student: this.detail.profile.name,
				academic_year: this.detail.profile.academic_year,
			})
		);
	}

	// ── Scholarship / Stipend ────────────────────────────────────────────
	render_scholarship($body) {
		const { profile: p, concessions, stipends, summary: s } = this.detail;
		const sub = this.sch_subtab === "stipend" ? "stipend" : "scholarship";
		const kpi = (icon, label, value, tone) =>
			`<div class="sfm-kpi sfm-kpi-${tone}"><span class="sfm-kpi-icon">${sfm_icon(icon, 18)}</span><div class="sfm-kpi-body"><div class="sfm-kpi-label">${label}</div><div class="sfm-kpi-value">${value}</div></div></div>`;
		const detail = (label, value) =>
			`<div class="sfm-meta"><div class="sfm-meta-label">${label}</div><div class="sfm-meta-value">${sfm_esc(value || "—")}</div></div>`;

		const subtabs = `
			<div class="sfm-subtabs" role="tablist" aria-label="${__("Scholarship or stipend")}">
				${[
					["scholarship", "award", __("Scholarship"), concessions.length],
					["stipend", "wallet", __("Stipend"), stipends.length],
				]
					.map(
						([key, icon, label, n]) =>
							`<button type="button" role="tab" class="sfm-subtab ${key === sub ? "active" : ""}" data-subtab="${key}"
								aria-selected="${key === sub}" tabindex="${key === sub ? 0 : -1}">${sfm_icon(icon, 15)}<span>${label}</span><span class="sfm-tab-count">${n}</span></button>`
					)
					.join("")}
			</div>`;

		let head_actions = "";
		let content = "";
		if (sub === "scholarship") {
			const on_record =
				flt(p.scholarship_amount) > 0
					? sfm_money(p.scholarship_amount)
					: flt(p.scholarship_percentage) > 0
					? `${flt(p.scholarship_percentage)}%`
					: "—";
			if (frappe.model.can_create("Fee Concession")) {
				head_actions = `<button type="button" class="sfm-btn sfm-btn-primary" data-act="new-scholarship">${sfm_icon("plus", 15)}<span>${__("Apply Scholarship")}</span></button>`;
			}
			content = `
				<div class="sfm-kpi-grid sfm-kpi-grid-3">
					${kpi("award", __("Scholarship on Record"), on_record, "primary")}
					${kpi("check", __("Scholarship / Waiver Applied"), sfm_money(s.scholarship_amount), "success")}
					${kpi("file-text", __("Concessions"), sfm_int(concessions.length), "neutral")}
				</div>

				<div class="sfm-panel sfm-scholar-card">
					<div class="sfm-panel-title">${sfm_icon("award", 15)}${__("Scholarship Details")}</div>
					<div class="sfm-metas">
						${detail(__("Applying for Scholarship"), p.applying_scholarship)}
						${detail(__("Scholarship Type"), p.scholarship_type)}
						${detail(__("Amount"), flt(p.scholarship_amount) ? sfm_money(p.scholarship_amount) : "")}
						${detail(__("Percentage"), flt(p.scholarship_percentage) ? `${flt(p.scholarship_percentage)}%` : "")}
						${detail(__("Approval Date"), p.scholarship_approval_date ? sfm_date(p.scholarship_approval_date) : "")}
						${detail(__("Remarks"), p.fee_waiver_remarks)}
					</div>
				</div>

				<div class="sfm-section-head"><h3 class="sfm-section-title">${__("Scholarships & Waivers Applied")}</h3></div>
				<div class="sfm-panel sfm-table-panel"><div class="sfm-table-scroll">
					<table class="sfm-table">
						<thead><tr>
							<th scope="col">${__("Concession No.")}</th><th scope="col">${__("Type")}</th>
							<th scope="col">${__("Due")}</th>
							<th scope="col" class="num">${__("Scholarship")}<div class="sfm-th-sub">${__("Waiver")}</div></th>
							<th scope="col">${__("Status")}</th><th scope="col">${__("Reason")}</th>
						</tr></thead>
						<tbody>
							${
								concessions.length
									? concessions
											.map(
												(c) => `<tr>
								<td><a class="sfm-link" href="${frappe.utils.get_form_link("Fee Concession", c.name)}">${sfm_esc(c.name)}</a></td>
								<td>${sfm_esc(c.concession_type || "—")}</td>
								<td>${sfm_esc(c.fee_demand || "—")}<div class="sfm-sub">${sfm_esc(c.fee_component || "")}</div></td>
								<td class="num sfm-amount-strong">${sfm_money(c.waiver_amount)}</td>
								<td>${sfm_badge(c.status || ["Draft", "Approved", "Cancelled"][c.docstatus])}</td>
								<td class="sfm-remark" title="${sfm_esc(c.reason || "")}">${sfm_esc(c.reason || "—")}</td>
							</tr>`
											)
											.join("")
									: `<tr><td colspan="6"><div class="sfm-empty-state"><div class="sfm-empty-title">${__("No scholarships or waivers for this student")}</div></div></td></tr>`
							}
						</tbody>
					</table>
				</div></div>`;
		} else {
			const paid = stipends.filter((x) => x.docstatus === 1);
			const last = paid[0];
			if (frappe.model.can_create("Stipend Payment")) {
				head_actions = `<button type="button" class="sfm-btn sfm-btn-primary" data-act="new-stipend">${sfm_icon("plus", 15)}<span>${__("Record Stipend Payment")}</span></button>`;
			}
			content = `
				<div class="sfm-kpi-grid sfm-kpi-grid-3">
					${kpi("wallet", __("Stipend Paid"), sfm_money(s.stipend_paid), "primary")}
					${kpi("card", __("Stipend Payments"), sfm_int(paid.length), "neutral")}
					${kpi("clock", __("Last Payment"), last ? `${sfm_money(last.amount)} <span class="sfm-kpi-note">${sfm_date(last.payment_date)}</span>` : "—", "neutral")}
				</div>

				<div class="sfm-section-head"><h3 class="sfm-section-title">${__("Stipend Payments")}</h3></div>
				<div class="sfm-panel sfm-table-panel"><div class="sfm-table-scroll">
					<table class="sfm-table">
						<thead><tr>
							<th scope="col">${__("Stipend No.")}</th><th scope="col">${__("Date")}</th><th scope="col">${__("Type")}</th>
							<th scope="col">${__("Year / Term")}</th><th scope="col">${__("Mode")}</th><th scope="col">${__("Reference")}</th>
							<th scope="col" class="num">${__("Amount")}</th><th scope="col">${__("Status")}</th><th scope="col">${__("Remarks")}</th>
						</tr></thead>
						<tbody>
							${
								stipends.length
									? stipends
											.map(
												(x) => `<tr>
								<td><a class="sfm-link" href="${frappe.utils.get_form_link("Stipend Payment", x.name)}">${sfm_esc(x.name)}</a></td>
								<td>${sfm_date(x.payment_date)}</td>
								<td>${sfm_esc(x.stipend_type || "—")}</td>
								<td>${sfm_esc(x.academic_year || "—")}${x.academic_term ? `<div class="sfm-sub">${sfm_esc(x.academic_term)}</div>` : ""}</td>
								<td>${sfm_esc(x.payment_mode || "—")}</td>
								<td>${sfm_esc(x.reference_number || "—")}</td>
								<td class="num sfm-amount-strong">${sfm_money(x.amount)}</td>
								<td>${sfm_badge(x.status || ["Draft", "Submitted", "Cancelled"][x.docstatus])}</td>
								<td class="sfm-remark" title="${sfm_esc(x.remarks || "")}">${sfm_esc(x.remarks || "—")}</td>
							</tr>`
											)
											.join("")
									: `<tr><td colspan="9"><div class="sfm-empty-state"><div class="sfm-empty-title">${__("No stipend payments for this student")}</div></div></td></tr>`
							}
						</tbody>
					</table>
				</div></div>`;
		}

		$body.html(`
			<h2 class="sfm-section-title sfm-sr-only">${__("Scholarship / Stipend")}</h2>
			<div class="sfm-subtab-bar">
				${subtabs}
				<div class="sfm-actions">${head_actions}</div>
			</div>
			<div role="tabpanel">${content}</div>
		`);

		$body.on("click", ".sfm-subtab", (e) => {
			this.sch_subtab = $(e.currentTarget).data("subtab");
			this.render_tab();
			this.$root.find(`.sfm-subtab[data-subtab="${this.sch_subtab}"]`).trigger("focus");
		});
		$body.on("keydown", ".sfm-subtab", (e) => {
			if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
			e.preventDefault();
			$body.find(".sfm-subtab").not(e.currentTarget).trigger("click");
		});
		$body.find('[data-act="new-scholarship"]').on("click", () =>
			frappe.new_doc("Fee Concession", { student: p.name })
		);
		$body.find('[data-act="new-stipend"]').on("click", () => this.stipend_dialog());
	}

	async stipend_dialog() {
		const p = this.detail.profile;
		await frappe.model.with_doctype("Stipend Payment");
		const opt = (field, fallback) =>
			((frappe.meta.get_docfield("Stipend Payment", field) || {}).options || fallback).split("\n").filter(Boolean);
		const dialog = new frappe.ui.Dialog({
			title: __("Record Stipend Payment — {0}", [p.first_name || p.name]),
			fields: [
				{ fieldtype: "Select", fieldname: "stipend_type", label: __("Stipend Type"), reqd: 1, options: opt("stipend_type", "University Financial"), default: opt("stipend_type", "University Financial")[0] },
				{ fieldtype: "Currency", fieldname: "amount", label: __("Amount"), reqd: 1, options: "INR" },
				{ fieldtype: "Date", fieldname: "payment_date", label: __("Payment Date"), reqd: 1, default: frappe.datetime.get_today() },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Select", fieldname: "payment_mode", label: __("Payment Mode"), reqd: 1, options: opt("payment_mode", "Bank Transfer"), default: "Bank Transfer" },
				{ fieldtype: "Data", fieldname: "reference_number", label: __("Reference / UTR No.") },
				{ fieldtype: "Link", fieldname: "academic_year", label: __("Academic Year"), options: "Academic Year", default: p.academic_year },
				{ fieldtype: "Link", fieldname: "academic_term", label: __("Academic Term"), options: "Academic Term" },
				{ fieldtype: "Section Break" },
				{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks"), reqd: 1 },
			],
			primary_action_label: __("Record Stipend Payment"),
			primary_action: (v) => {
				if (flt(v.amount) <= 0) return frappe.msgprint(__("Amount must be greater than zero."));
				if (!(v.remarks || "").trim()) return frappe.msgprint(__("Remarks are mandatory."));
				frappe.confirm(__("Record a stipend payment of <b>{0}</b> to {1}?", [sfm_money(v.amount), sfm_esc(p.first_name || p.name)]), async () => {
					const r = await frappe.call({
						method: SFM_API + "record_stipend",
						args: { student: p.name, ...v },
						freeze: true,
						freeze_message: __("Recording stipend…"),
					});
					dialog.hide();
					frappe.show_alert({ message: __("Stipend payment {0} recorded", [r.message.stipend_payment]), indicator: "green" }, 7);
					this.show_student(p.name);
				});
			},
		});
		dialog.$wrapper.addClass("sfm-dialog");
		dialog.show();
	}

	// ─────────────────────────────────────────────────────────────────────
	inject_styles() {
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
			.sfm-filter-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
			.sfm-search-btn { width: 100%; }
			.sfm-metas { border-right: none; padding-right: 0; }
		}
		@container sfm (max-width: 899px) {
			.sfm-kpi-grid.sfm-kpi-grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
		}
		@container sfm (max-width: 699px) {
			.sfm-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
			.sfm-kpi-grid.sfm-kpi-grid-3 { grid-template-columns: minmax(0, 1fr); }
			.sfm-filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
			.sfm-page-label { display: none; }
		}
		@container sfm (max-width: 459px) {
			.sfm-kpi-grid, .sfm-kpi-grid.sfm-kpi-grid-4, .sfm-kpi-grid.sfm-kpi-grid-3 { grid-template-columns: minmax(0, 1fr); }
			.sfm-filter-grid { grid-template-columns: minmax(0, 1fr); padding: 16px; }
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
}
