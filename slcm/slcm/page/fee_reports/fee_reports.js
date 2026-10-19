// Fee Reports
//   /desk/fee-reports/due-wise     → Due Wise Report (one row per due)
//   /desk/fee-reports/outstanding  → Student Wise Outstanding (one row per student, a column per Fee Component)
// Both follow the office's sheets and export to Excel. Filters apply only when Search is pressed.
// Helpers, icons, the multi-select and the styles come from /assets/slcm/js/sfm_common.js.

const FR_PAGE = "fee-reports";
const FR_API = "slcm.slcm.page.fee_reports.fee_reports.";
const FR_PAGE_SIZES = [10, 25, 50, 100];
const FR_REPORTS = {
	"due-wise": { key: "due_wise", icon: "file-text", label: __("Due Wise Report"), method: "get_due_wise_report" },
	outstanding: { key: "outstanding", icon: "clock", label: __("Student Wise Outstanding"), method: "get_outstanding_report" },
};
// Filters that only narrow individual dues, so they show on the Due Wise Report only.
const FR_DUE_ONLY = ["demand_type", "demand_from", "demand_to", "settlement_from", "settlement_to"];

frappe.pages[FR_PAGE].on_page_load = function (wrapper) {
	frappe.require("/assets/slcm/js/sfm_common.js", () => {
		wrapper.fee_reports = new FeeReports(wrapper);
		wrapper.fee_reports.route();
	});
};

frappe.pages[FR_PAGE].on_page_show = function (wrapper) {
	wrapper.fee_reports && wrapper.fee_reports.route();
};

const fr_empty_filters = () => ({
	academic_year: [],
	academic_term: [],
	programme: [],
	dues_status: [],
	demand_type: [],
	demand_from: "",
	demand_to: "",
	settlement_from: "",
	settlement_to: "",
	search: "",
});

class FeeReports {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Fee Reports"), single_column: true });
		let page_length = 25;
		try {
			page_length = cint(localStorage.getItem("fr_page_length")) || 25;
		} catch (e) {
			// storage blocked — fall back to the default
		}
		this.state = { start: 0, page_length: FR_PAGE_SIZES.includes(page_length) ? page_length : 25 };
		this.filters = fr_empty_filters();
		// Filter edits collect here and only reach this.filters (and the server) when Search is pressed.
		this.draft = fr_empty_filters();
		this.filter_options = null;
		this.req = 0;
		this.ms = {};

		sfm_load_font();
		sfm_inject_styles();
		$(wrapper).addClass("sfm-page");
		this.$root = $(`<div class="sfm"></div>`).appendTo(this.page.main);
		this.render_shell();
	}

	route() {
		const slug = frappe.get_route()[1];
		if (!FR_REPORTS[slug]) {
			frappe.set_route(FR_PAGE, "due-wise");
			return;
		}
		this.report_slug = slug;
		this.report = FR_REPORTS[slug];
		this.page.set_title(this.report.label);
		this.$root.find(".sfm-view-tabs .sfm-tab").each((_, t) => {
			const active = $(t).data("report") === slug;
			$(t).toggleClass("active", active).attr({ "aria-selected": active, tabindex: active ? 0 : -1 });
		});
		this.$root.find("[data-due-only]").prop("hidden", slug !== "due-wise");
		this.$root.find(".sfm-report-title").text(this.report.label);
		this.reload();
	}

	render_shell() {
		const date_range = (key, label) => `
			<div class="sfm-field sfr-range-field" data-due-only>
				<label id="fr-${key}-label">${label}</label>
				<div class="sfr-range" role="group" aria-labelledby="fr-${key}-label">
					<input type="date" class="sfm-control" data-f="${key}_from" aria-label="${sfm_esc(__("{0} from", [label]))}" title="${__("From")}">
					<span class="sfm-muted" aria-hidden="true">${__("to")}</span>
					<input type="date" class="sfm-control" data-f="${key}_to" aria-label="${sfm_esc(__("{0} to", [label]))}" title="${__("To")}">
				</div>
			</div>`;

		this.$root.html(`
			<div class="sfm-shell">
				<header class="sfm-head">
					<div>
						<h1 class="sfm-title">${__("Fee Reports")}</h1>
						<p class="sfm-subtitle">${__("Due wise and student wise outstanding fee reports, exportable to Excel")}</p>
					</div>
					<div class="sfm-actions">
						<a class="sfm-btn sfm-btn-secondary" href="/desk/student-fee-management" data-act="fee-management">
							${sfm_icon("arrow-left", 15)}<span>${__("Student Fee Management")}</span>
						</a>
						<button type="button" class="sfm-btn sfm-btn-secondary" data-act="refresh">
							${sfm_icon("refresh", 15)}<span>${__("Refresh")}</span>
						</button>
					</div>
				</header>

				<div class="sfm-tabs sfm-view-tabs" role="tablist" aria-label="${__("Reports")}">
					${Object.entries(FR_REPORTS)
						.map(
							([slug, r]) =>
								`<a role="tab" class="sfm-tab" href="/desk/${FR_PAGE}/${slug}" data-report="${slug}">${sfm_icon(r.icon, 16)}<span>${r.label}</span></a>`
						)
						.join("")}
				</div>

				<section class="sfm-panel sfm-filter-panel" aria-labelledby="fr-filter-title">
					<div class="sfm-panel-head">
						<h2 id="fr-filter-title" class="sfm-panel-title">${sfm_icon("filter", 15)}${__("Filter & Search")}</h2>
						<button type="button" class="sfm-btn sfm-btn-ghost sfm-btn-sm" data-act="clear">
							${sfm_icon("x", 14)}<span>${__("Clear filters")}</span>
						</button>
					</div>
					<div class="sfm-filter-grid sfr-filter-grid">
						<div class="sfm-field" data-ms-key="academic_year"></div>
						<div class="sfm-field" data-ms-key="academic_term"></div>
						<div class="sfm-field" data-ms-key="programme"></div>
						<div class="sfm-field" data-ms-key="dues_status"></div>
						<div class="sfm-field" data-ms-key="demand_type" data-due-only></div>
						${date_range("demand", __("Demand Creation Date"))}
						${date_range("settlement", __("Settlement Date"))}
						<div class="sfm-field">
							<label for="fr-f-search">${__("Search")}</label>
							<div class="sfm-search-wrap">
								${sfm_icon("search", 15, "sfm-search-icon")}
								<input id="fr-f-search" type="search" class="sfm-control" data-f="search"
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

				<section class="sfm-panel sfm-report-panel">
					<div class="sfm-table-toolbar">
						<div>
							<h2 class="sfm-panel-title sfm-report-title"></h2>
							<div class="sfm-muted sfm-report-caption" aria-live="polite"></div>
						</div>
						<div class="sfm-report-tools">
							<div class="sfm-page-size">
								<label for="fr-report-size">${__("Rows per page")}</label>
								<div class="sfm-select-wrap">
									<select id="fr-report-size" class="sfm-control sfm-control-sm">
										${FR_PAGE_SIZES.map((n) => `<option value="${n}">${n}</option>`).join("")}
									</select>
									${sfm_icon("chevron-down", 14, "sfm-select-caret")}
								</div>
							</div>
							<button type="button" class="sfm-btn sfm-btn-primary sfm-btn-sm" data-act="export">
								${sfm_icon("download", 14)}<span>${__("Export Excel")}</span>
							</button>
						</div>
					</div>
					<div class="sfm-table-scroll">
						<table class="sfm-table sfm-report-table"><thead></thead><tbody></tbody><tfoot></tfoot></table>
					</div>
					<footer class="sfm-pager" data-pager="report"></footer>
				</section>
			</div>
		`);
		this.$root.find("#fr-report-size").val(this.state.page_length);
		this.build_filters();
		this.bind_events();

		frappe.call({ method: FR_API + "get_filter_options" }).then((r) => {
			this.filter_options = r.message;
			this.render_filter_options();
		});
	}

	// ── Filters ──────────────────────────────────────────────────────────
	build_filters() {
		const make = (key, label, all_label, searchable = false) =>
			new SfmMultiSelect(this.$root.find(`[data-ms-key="${key}"]`), {
				key: `fr-${key}`,
				label,
				all_label,
				searchable,
				on_change: (value) => {
					this.draft[key] = value;
					if (key === "academic_year") this.render_filter_options();
					this.update_dirty();
				},
			});
		this.ms = {
			academic_year: make("academic_year", __("Academic Year"), __("All Years")),
			academic_term: make("academic_term", __("Term"), __("All Terms")),
			programme: make("programme", __("Programme"), __("All Programmes"), true),
			dues_status: make("dues_status", __("Dues Status"), __("All Students")),
			demand_type: make("demand_type", __("Demand Type"), __("All Types")),
		};
		this.ms.dues_status.set_options(SFM_DUES_STATUS_OPTIONS, []);

		$(document)
			.off("mousedown.fr-ms")
			.on("mousedown.fr-ms", (e) => {
				if (!$(e.target).closest(".sfm-ms").length) Object.values(this.ms).forEach((m) => m.close());
			});
	}

	render_filter_options() {
		const o = this.filter_options;
		const d = this.draft;
		if (!o) return;

		this.ms.academic_year.set_options(o.academic_years.map((y) => ({ value: y, label: y })), d.academic_year);
		d.academic_year = this.ms.academic_year.value();

		// Terms follow the chosen years; a term name can repeat across years, so dedupe.
		const terms = [
			...new Set(
				o.terms.filter((t) => !d.academic_year.length || d.academic_year.includes(t.academic_year)).map((t) => t.academic_term)
			),
		];
		this.ms.academic_term.set_options(terms.map((t) => ({ value: t, label: t })), d.academic_term);
		d.academic_term = this.ms.academic_term.value();

		this.ms.programme.set_options(
			o.programmes.map((p) => ({
				value: p.name,
				label: p.program_name && p.program_name !== p.name ? `${p.name} — ${p.program_name}` : p.name,
			})),
			d.programme
		);
		d.programme = this.ms.programme.value();
		this.ms.dues_status.set_options(SFM_DUES_STATUS_OPTIONS, d.dues_status);
		this.ms.demand_type.set_options(
			(o.demand_types || []).map((t) => ({ value: t, label: __(t) })),
			d.demand_type
		);
		d.demand_type = this.ms.demand_type.value();
	}

	// The filters the current report actually uses (due-only ones are ignored on Outstanding).
	active_filters() {
		const f = { ...this.filters };
		if (this.report_slug !== "due-wise") FR_DUE_ONLY.forEach((k) => (f[k] = fr_empty_filters()[k]));
		return f;
	}

	apply_filters() {
		Object.values(this.ms).forEach((m) => m.close());
		const d = this.draft;
		for (const [key, label] of [
			["demand", __("Demand Creation Date")],
			["settlement", __("Settlement Date")],
		]) {
			if (d[`${key}_from`] && d[`${key}_to`] && d[`${key}_from`] > d[`${key}_to`]) {
				frappe.msgprint({ message: __("{0}: the From date must be on or before the To date.", [label]), indicator: "orange" });
				return;
			}
		}
		this.filters = JSON.parse(JSON.stringify({ ...d, search: (d.search || "").trim() }));
		this.update_dirty();
		this.reload();
	}

	clear_filters() {
		this.filters = fr_empty_filters();
		this.draft = fr_empty_filters();
		Object.values(this.ms).forEach((m) => m.set_options(m.options, []));
		this.$root.find("input[data-f]").val("");
		this.render_filter_options();
		this.update_dirty();
		this.reload();
	}

	// Flag the Search button while the filters on screen differ from the ones the table shows.
	update_dirty() {
		const norm = (f) => JSON.stringify({ ...f, search: (f.search || "").trim() });
		const dirty = norm(this.draft) !== norm(this.filters);
		this.$root
			.find(".sfm-search-btn")
			.toggleClass("is-dirty", dirty)
			.attr("title", dirty ? __("Filters changed — click Search to apply") : __("Search"));
	}

	bind_events() {
		const $r = this.$root;
		$r.on("input change", "input[data-f]", (e) => {
			this.draft[$(e.currentTarget).data("f")] = $(e.currentTarget).val();
			this.update_dirty();
		});
		$r.on("keydown", "input[data-f]", (e) => {
			if (e.key === "Enter") {
				e.preventDefault();
				this.apply_filters();
			}
		});
		$r.on("click", '[data-act="apply"]', () => this.apply_filters());
		$r.on("click", '[data-act="clear"]', () => this.clear_filters());
		$r.on("click", '[data-act="refresh"]', () => this.load());
		$r.on("click", '[data-act="export"]', () => this.export());
		$r.on("click", ".sfm-view-tabs .sfm-tab, [data-act='fee-management']", (e) => {
			if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
			e.preventDefault();
			const slug = $(e.currentTarget).data("report");
			slug ? frappe.set_route(FR_PAGE, slug) : frappe.set_route("student-fee-management");
		});
		// Arrow keys move between the report tabs (WAI-ARIA tabs pattern)
		$r.on("keydown", ".sfm-view-tabs .sfm-tab", (e) => {
			if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
			e.preventDefault();
			$r.find(".sfm-view-tabs .sfm-tab").not(e.currentTarget).trigger("focus").trigger("click");
		});
		$r.on("click", ".sfm-report-student", (e) => {
			if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
			e.preventDefault();
			frappe.set_route("student-fee-management", $(e.currentTarget).data("student"));
		});
		$r.on("change", "#fr-report-size", (e) => {
			this.state.page_length = cint($(e.currentTarget).val()) || 25;
			try {
				localStorage.setItem("fr_page_length", this.state.page_length);
			} catch (err) {
				// storage blocked — the choice just won't be remembered
			}
			this.reload();
		});
		$r.on("click", '.sfm-pager[data-pager="report"] [data-page]', (e) => {
			const s = this.state;
			s.start = Math.max(0, (cint($(e.currentTarget).data("page")) - 1) * s.page_length);
			this.load();
		});
	}

	// ── Loading ──────────────────────────────────────────────────────────
	reload() {
		this.state.start = 0;
		this.load();
	}

	async load() {
		if (!this.report) return;
		const report = this.report;
		const req = ++this.req;
		const $panel = this.$root.find(".sfm-report-panel");
		$panel.find(".sfm-report-caption").text(__("Loading…"));
		$panel.find(".sfm-report-table tbody").html(
			`<tr><td colspan="40"><div class="sfm-empty-state">${sfm_icon("loader", 22, "sfm-spin")}</div></td></tr>`
		);
		$panel.find(".sfm-report-table tfoot").empty();

		let result;
		try {
			const r = await frappe.call({
				method: FR_API + report.method,
				args: { ...this.active_filters(), start: this.state.start, page_length: this.state.page_length },
			});
			result = r.message;
		} catch (e) {
			result = null;
		}
		if (req !== this.req || report !== this.report) return;

		if (!result) {
			$panel.find(".sfm-report-caption").text("");
			$panel.find(".sfm-report-table thead").empty();
			$panel.find(".sfm-report-table tbody").html(
				`<tr><td><div class="sfm-empty-state"><span class="sfm-empty-icon">${sfm_icon("alert", 22)}</span><div class="sfm-empty-title">${__("Couldn't load the report")}</div></div></td></tr>`
			);
			$panel.find('.sfm-pager[data-pager="report"]').empty();
			return;
		}
		if (report.key === "due_wise") this.render_due_wise(result);
		else this.render_outstanding(result);
	}

	student_link(d, label) {
		return `<a href="/desk/student-fee-management/${encodeURIComponent(d.student)}" class="sfm-report-student" data-student="${sfm_esc(d.student)}">${sfm_esc(label || d.student)}</a>`;
	}

	pager_opts(wording = {}) {
		return {
			state: this.state,
			$pager: this.$root.find('.sfm-pager[data-pager="report"]'),
			$caption: this.$root.find(".sfm-report-caption"),
			...wording,
		};
	}

	render_due_wise({ columns, rows, totals }) {
		const $t = this.$root.find(".sfm-report-table");
		const cell = (key, is_amount, d) => {
			const v = d[key];
			if (is_amount) return `<td class="num">${sfm_money(v)}</td>`;
			if (key === "student_name") return `<td>${this.student_link(d, v)}</td>`;
			if (key === "voucher_number") return `<td><a href="${frappe.utils.get_form_link("Fee Demand", v)}">${sfm_esc(v)}</a></td>`;
			if (key === "due_status") return `<td>${sfm_badge(v)}</td>`;
			if (key.endsWith("_date")) return `<td>${sfm_date(v)}</td>`;
			return `<td class="${key === "remarks" || key === "email" ? "sfm-wrap" : ""}">${sfm_esc(v || "—")}</td>`;
		};
		$t.find("thead").html(
			`<tr>${columns.map(([_k, label, a]) => `<th scope="col" class="${a ? "num" : ""}">${sfm_esc(label)}</th>`).join("")}</tr>`
		);
		$t.find("tbody").html(
			rows.length
				? rows.map((d) => `<tr>${columns.map(([k, _l, a]) => cell(k, a, d)).join("")}</tr>`).join("")
				: `<tr><td colspan="${columns.length}"><div class="sfm-empty-state"><span class="sfm-empty-icon">${sfm_icon("search-x", 22)}</span><div class="sfm-empty-title">${__("No dues found")}</div></div></td></tr>`
		);
		const first_amount = columns.findIndex((c) => c[2]);
		$t.find("tfoot").html(
			rows.length
				? `<tr class="sfm-report-total"><td colspan="${first_amount}">${__("Total (all matching dues)")}</td>${columns
						.slice(first_amount)
						.map(([k, _l, a]) => (a ? `<td class="num">${sfm_money(totals[k])}</td>` : "<td></td>"))
						.join("")}</tr>`
				: ""
		);
		sfm_render_pager(
			cint(totals.row_count),
			rows.length,
			this.pager_opts({
				one: __("1 due matches the current filters"),
				many: __("{0} dues match the current filters"),
				showing_one: __("Showing 1 of 1 due"),
				showing_many: __("Showing {0} to {1} of {2} dues"),
			})
		);
	}

	render_outstanding({ components, rows, count, totals }) {
		const $t = this.$root.find(".sfm-report-table");
		const amount = (v) => (flt(v) ? sfm_money(v) : '<span class="sfm-sub">0</span>');
		$t.find("thead").html(`<tr>
			<th scope="col" class="num">${__("Sl. No.")}</th>
			<th scope="col">${__("Student ID")}</th>
			<th scope="col">${__("Student Name")}</th>
			<th scope="col">${__("Student Email ID")}</th>
			<th scope="col">${__("Academic Status")}</th>
			${components.map((c) => `<th scope="col" class="num">${sfm_esc(c)}</th>`).join("")}
			<th scope="col" class="num">${__("Total Outstanding Fee")}</th>
		</tr>`);
		$t.find("tbody").html(
			rows.length
				? rows
						.map(
							(d, i) => `<tr>
					<td class="num">${this.state.start + i + 1}</td>
					<td>${sfm_esc(d.student_id)}</td>
					<td>${this.student_link(d, d.student_name)}</td>
					<td class="sfm-wrap">${sfm_esc(d.email || "—")}</td>
					<td>${sfm_esc(d.academic_status || "—")}</td>
					${components.map((c) => `<td class="num">${amount(d.amounts[c])}</td>`).join("")}
					<td class="num sfm-amount-strong">${sfm_money(d.total)}</td>
				</tr>`
						)
						.join("")
				: `<tr><td colspan="${components.length + 6}"><div class="sfm-empty-state"><span class="sfm-empty-icon">${sfm_icon("search-x", 22)}</span><div class="sfm-empty-title">${__("No students found")}</div></div></td></tr>`
		);
		$t.find("tfoot").html(
			rows.length
				? `<tr class="sfm-report-total"><td colspan="5">${__("Total (all matching students)")}</td>${components
						.map((c) => `<td class="num">${sfm_money(totals[c])}</td>`)
						.join("")}<td class="num">${sfm_money(totals.total)}</td></tr>`
				: ""
		);
		sfm_render_pager(cint(count), rows.length, this.pager_opts());
	}

	export() {
		const params = new URLSearchParams({ report: this.report.key });
		Object.entries(this.active_filters()).forEach(([k, v]) => {
			if (Array.isArray(v) ? v.length : v) params.append(k, Array.isArray(v) ? JSON.stringify(v) : v);
		});
		window.open(`/api/method/${FR_API}export_report?${params.toString()}`);
	}
}
