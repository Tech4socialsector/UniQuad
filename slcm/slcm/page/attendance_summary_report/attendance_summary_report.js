// Copyright (c) 2026, SLCM and contributors

const ASR_ELIGIBILITY_META = {
	"Eligible": { color: "#16a34a", bg: "#dcfce7", dot: "🟢" },
	"Not Eligible": { color: "#dc2626", bg: "#fee2e2", dot: "🔴" },
};

frappe.pages["attendance-summary-report"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Attendance Summary Report"),
		single_column: true,
	});

	asr_inject_styles();
	// frappe.DataTable's JS is already part of the desk bundle, but its CSS
	// is only bundled with the report/web_form views — load it explicitly
	// since this is a plain desk Page.
	frappe.require("report.bundle.css").then(() => {
		new AttendanceSummaryReport(page);
	});
};

class AttendanceSummaryReport {
	constructor(page) {
		this.page = page;
		this.ctrls = {};
		this.tab = "summary"; // summary | weekly | monthly | daily
		this._export = null;  // { headers, rows } for the last successfully rendered view
		this._filters_ready = false; // guards auto-apply while default values are still being set
		this._build();
	}

	_build() {
		const $main = $(this.page.main).empty();
		$main.addClass("asr-page");

		this._build_filters($main);
		this._build_tabs($main);
		this._build_search($main);

		this.$summary = $(`<div class="asr-kpi-row"></div>`).appendTo($main);
		this.$table = $(`<div class="asr-card asr-table-card"></div>`).appendTo($main);

		// Close any open multiselect dropdown when clicking elsewhere on the page
		$(document).on("click.asr-msdd", () => $(".asr-msdd-panel").hide());

		this._render_intro();
	}

	_build_filters($main) {
		const $card = $(`<div class="asr-card asr-filter-card"></div>`).appendTo($main);

		$(`<div class="asr-card-title">${__("Filters")}</div>`).appendTo($card);

		const $grid = $(`<div class="asr-filter-grid"></div>`).appendTo($card);
		this.ctrls.academic_year = this._link($grid, "Academic Year", "Academic Year");
		this.ctrls.term = this._dropdown_multiselect($grid, "Academic Term", (txt) => {
			const q = (txt || "").toLowerCase();
			return (this._term_values || [])
				.filter(v => v.toLowerCase().includes(q))
				.map(v => ({ value: v, label: v }));
		});
		this.ctrls.programme = this._link($grid, "Programme", "Programme");
		this.ctrls.course = this._link($grid, "Course", "Course");
		this.ctrls.batch = this._link($grid, "Batch", "SLCM Batch");
		this.ctrls.section = this._link($grid, "Section", "Section");
		this.ctrls.student = this._dropdown_multiselect($grid, "Student", (txt) =>
			new Promise((resolve) => {
				frappe.call({
					method: "slcm.slcm.page.attendance_summary_report.attendance_summary_report.get_student_filter_options",
					args: { txt },
					callback: (r) => resolve(r.message || []),
				});
			})
		);

		this._load_terms();

		// Date range picker — only relevant/visible on the Daily tab
		this.$month_picker = $(`<div class="asr-field asr-month-picker" style="display:none">
			<label>${__("From Date")}</label>
			<div class="asr-date-from"></div>
		</div>`).appendTo($grid);
		this.$to_date_field = $(`<div class="asr-field asr-month-picker" style="display:none">
			<label>${__("To Date")}</label>
			<div class="asr-date-to"></div>
		</div>`).appendTo($grid);
		this.ctrls.from_date = this._date(this.$month_picker.find(".asr-date-from"));
		this.ctrls.to_date = this._date(this.$to_date_field.find(".asr-date-to"));

		const today = frappe.datetime.now_date();
		this.ctrls.from_date.set_value(frappe.datetime.month_start());
		this.ctrls.to_date.set_value(today);

		const $condonation = $(`<div class="asr-checkbox-row">
			<label>
				<input type="checkbox" class="asr-condonation-check" />
				${__("Include Condonation Report")}
			</label>
		</div>`).appendTo($card);
		this.ctrls.include_condonation = {
			get_value: () => $condonation.find(".asr-condonation-check").is(":checked"),
			set_value: (v) => $condonation.find(".asr-condonation-check").prop("checked", !!v),
		};
		$condonation.find(".asr-condonation-check").on("change", () => this._auto_load());

		const $act = $(`<div class="asr-filter-actions"></div>`).appendTo($card);
		$(`<button class="btn btn-default btn-sm">${__("Reset")}</button>`)
			.appendTo($act).on("click", () => this._clear());
		this.$export_btn = $(`<button class="btn btn-default btn-sm" disabled>${__("Export CSV")}</button>`)
			.appendTo($act).on("click", () => this._export_csv());

		this._filters_ready = true;
	}

	_auto_load() {
		if (this._filters_ready) this._load();
	}

	_build_tabs($main) {
		const $tabs = $(`<div class="asr-tabs"></div>`).appendTo($main);
		const tabs = [
			["summary", __("Summary")],
			["weekly", __("Weekly")],
			["monthly", __("Monthly")],
			["daily", __("Daily")],
		];
		this.$tabs = {};
		tabs.forEach(([key, label]) => {
			const $t = $(`<div class="asr-tab">${label}</div>`).appendTo($tabs);
			$t.on("click", () => this._switch_tab(key));
			this.$tabs[key] = $t;
		});
		this._mark_active_tab();
	}

	_switch_tab(key) {
		this.tab = key;
		this._mark_active_tab();
		this.$month_picker.toggle(key === "daily");
		this.$to_date_field.toggle(key === "daily");
		this._load();
	}

	_build_search($main) {
		const search_icon = `<svg class="asr-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`;
		const $wrap = $(`<div class="asr-search-row">
			<div class="asr-search-box">
				${search_icon}
				<input type="text" placeholder="${esc(__("Search by student name or ID..."))}" />
			</div>
		</div>`).appendTo($main);

		this._search_text = "";
		let debounce_timer = null;
		$wrap.find("input").on("input", (e) => {
			const value = e.target.value;
			clearTimeout(debounce_timer);
			debounce_timer = setTimeout(() => this._on_search_change(value), 150);
		});
	}

	_mark_active_tab() {
		Object.entries(this.$tabs).forEach(([key, $t]) => $t.toggleClass("active", key === this.tab));
	}

	/* ---------- filter helpers ---------- */

	_link($parent, label, doctype) {
		return this._dropdown_multiselect($parent, label, (txt) => frappe.db.get_link_options(doctype, txt));
	}

	/**
	 * A button that opens a searchable checkbox-list panel — the same
	 * pattern as the "All Asset Classes" style multiselect dropdowns used
	 * elsewhere. `fetch_options(txt)` returns (or resolves to) an array of
	 * {value, label} — used for both Link-backed fields (via
	 * frappe.db.get_link_options) and static in-memory lists (Academic Term).
	 */
	_dropdown_multiselect($parent, label, fetch_options) {
		const $wrap = $(`<div class="asr-field"><label>${__(label)}</label></div>`).appendTo($parent);
		const $control = $(`<div class="asr-msdd"></div>`).appendTo($wrap);
		const $btn = $(`<button type="button" class="asr-msdd-btn">${esc(__("All {0}", [__(label)]))}</button>`).appendTo($control);
		const $panel = $(`<div class="asr-msdd-panel">
			<div class="asr-msdd-search"><input type="text" placeholder="${esc(__("Search"))}" /></div>
			<div class="asr-msdd-options"></div>
		</div>`).appendTo($control).hide();

		const selected = new Set();
		const option_cache = new Map(); // value -> label
		let loaded = false;

		const update_btn = () => {
			if (!selected.size) {
				$btn.text(__("All {0}", [__(label)]));
			} else if (selected.size === 1) {
				const v = [...selected][0];
				$btn.text(option_cache.get(v) || v);
			} else {
				$btn.text(__("{0} selected", [selected.size]));
			}
		};

		const render_options = (txt) => {
			const $opts = $panel.find(".asr-msdd-options").empty();
			const q = (txt || "").toLowerCase();
			const seen = new Set();
			const rows = [];
			// Pinned: already-checked values stay visible even if they don't
			// match the current search text, so users can see/uncheck them.
			selected.forEach(v => {
				rows.push({ value: v, label: option_cache.get(v) || v });
				seen.add(v);
			});
			option_cache.forEach((lbl, v) => {
				if (seen.has(v)) return;
				if (q && !String(lbl).toLowerCase().includes(q) && !String(v).toLowerCase().includes(q)) return;
				rows.push({ value: v, label: lbl });
			});
			if (!rows.length) {
				$opts.append(`<div class="asr-msdd-empty">${esc(__("No matches"))}</div>`);
				return;
			}
			rows.forEach(({ value, label: lbl }) => {
				const $row = $(`<label class="asr-msdd-option">
					<input type="checkbox" ${selected.has(value) ? "checked" : ""}>
					<span>${esc(lbl)}</span>
				</label>`).appendTo($opts);
				$row.find("input").on("change", (e) => {
					if (e.target.checked) selected.add(value);
					else selected.delete(value);
					update_btn();
					this._auto_load();
				});
			});
		};

		const load_and_render = (txt) => {
			Promise.resolve(fetch_options(txt)).then(items => {
				(items || []).forEach(item => {
					const value = item && item.value !== undefined ? item.value : item;
					const lbl = (item && item.label) || value;
					option_cache.set(value, lbl);
				});
				loaded = true;
				render_options(txt);
			});
		};

		$btn.on("click", (e) => {
			e.stopPropagation();
			const opening = $panel.is(":hidden");
			$(".asr-msdd-panel").not($panel).hide();
			if (opening) {
				$panel.show();
				$panel.find("input[type=text]").val("").focus();
				load_and_render("");
			} else {
				$panel.hide();
			}
		});
		$panel.on("click", (e) => e.stopPropagation());
		$panel.find("input[type=text]").on("input", (e) => load_and_render(e.target.value));

		return {
			get_value: () => [...selected],
			set_value: (values) => {
				selected.clear();
				(values || []).forEach(v => selected.add(v));
				update_btn();
				if (loaded) render_options($panel.find("input[type=text]").val());
			},
		};
	}

	_date($parent) {
		const ctrl = frappe.ui.form.make_control({
			parent: $parent[0],
			df: { fieldtype: "Date", fieldname: "date", label: "", onchange: () => this._auto_load() },
			render_input: true,
		});
		ctrl.refresh();
		return ctrl;
	}

	_load_terms() {
		// Term is a plain Data field on Course Offering, not a Link doctype,
		// so populate the multiselect from the distinct values actually in use.
		frappe.db.get_list("Course Offering", {
			fields: ["term_name"],
			filters: { term_name: ["is", "set"] },
			group_by: "term_name",
			limit: 0,
		}).then(rows => {
			this._term_values = [...new Set(rows.map(r => r.term_name).filter(Boolean))].sort();
		});
	}

	_vals() {
		return {
			academic_year: this.ctrls.academic_year.get_value(),
			term: this.ctrls.term.get_value(),
			programme: this.ctrls.programme.get_value(),
			course: this.ctrls.course.get_value(),
			batch: this.ctrls.batch.get_value(),
			section: this.ctrls.section.get_value(),
			student: this.ctrls.student.get_value(),
		};
	}

	_clear() {
		this._filters_ready = false; // resetting shouldn't auto-trigger a load per field
		["academic_year", "term", "programme", "course", "batch", "section", "student"].forEach(key => {
			this.ctrls[key].set_value([]);
		});
		this.ctrls.from_date.set_value(frappe.datetime.month_start());
		this.ctrls.to_date.set_value(frappe.datetime.now_date());
		this.ctrls.include_condonation.set_value(false);
		this._filters_ready = true;
		this._search_text = "";
		this._last_response = undefined;
		this._last_daily_filters = null;
		$(".asr-search-box input").val("");
		this.$summary.empty();
		this._export = null;
		this.$export_btn.prop("disabled", true);
		this._render_intro();
	}

	/* ---------- data ---------- */

	_load() {
		const f = this._vals();
		this._render_skeleton();
		this._export = null;
		this.$export_btn.prop("disabled", true);
		this._last_daily_filters = null;

		if (this.tab === "summary") {
			const include_condonation = this.ctrls.include_condonation.get_value();
			frappe.call({
				method: "slcm.slcm.page.attendance_summary_report.attendance_summary_report.get_data",
				args: Object.assign({}, f, { include_condonation }),
				callback: r => {
					this._last_response = r.message || [];
					this._render_summary(this._search_filter_rows(this._last_response), include_condonation);
				},
				error: () => this._render_error(),
			});
		} else if (this.tab === "weekly") {
			frappe.call({
				method: "slcm.slcm.page.attendance_summary_report.attendance_summary_report.get_weekly_matrix",
				args: f,
				callback: r => {
					this._last_response = r.message || { weeks: [], rows: [] };
					this._render_weekly(this._search_filter_matrix(this._last_response));
				},
				error: () => this._render_error(),
			});
		} else if (this.tab === "monthly") {
			frappe.call({
				method: "slcm.slcm.page.attendance_summary_report.attendance_summary_report.get_monthly_matrix",
				args: f,
				callback: r => {
					this._last_response = r.message || { months: [], rows: [] };
					this._render_monthly(this._search_filter_matrix(this._last_response));
				},
				error: () => this._render_error(),
			});
		} else {
			const from_date = this.ctrls.from_date.get_value();
			const to_date = this.ctrls.to_date.get_value();
			this._last_daily_filters = f;
			frappe.call({
				method: "slcm.slcm.page.attendance_summary_report.attendance_summary_report.get_daily_matrix",
				args: Object.assign({}, f, { from_date, to_date }),
				callback: r => {
					this._last_response = r.message || { days: [], rows: [] };
					this._render_daily(this._search_filter_matrix(this._last_response));
				},
				error: () => this._render_error(),
			});
		}
	}

	/* ---------- global search (client-side, filters the last-loaded rows) ---------- */

	_matches_search(row) {
		if (!this._search_text) return true;
		const q = this._search_text.toLowerCase();
		return String(row.student_name || "").toLowerCase().includes(q)
			|| String(row.student_id || "").toLowerCase().includes(q);
	}

	// Summary tab: rows is a flat array.
	_search_filter_rows(rows) {
		return (rows || []).filter(r => this._matches_search(r));
	}

	// Weekly/Monthly/Daily tabs: { weeks|months|days, rows }, rows keeps its shape.
	_search_filter_matrix(payload) {
		if (!payload || !payload.rows) return payload;
		return Object.assign({}, payload, { rows: payload.rows.filter(r => this._matches_search(r)) });
	}

	_on_search_change(text) {
		this._search_text = text;
		if (this._last_response === undefined) return;
		if (this.tab === "summary") {
			const include_condonation = this.ctrls.include_condonation.get_value();
			this._render_summary(this._search_filter_rows(this._last_response), include_condonation);
		} else if (this.tab === "weekly") {
			this._render_weekly(this._search_filter_matrix(this._last_response));
		} else if (this.tab === "monthly") {
			this._render_monthly(this._search_filter_matrix(this._last_response));
		} else {
			this._render_daily(this._search_filter_matrix(this._last_response));
		}
	}

	/* ---------- render: KPI summary (Summary tab only) ---------- */

	_render_kpis(data) {
		const total = data.length;
		const avg = total ? data.reduce((sum, r) => sum + (r.attendance_percentage || 0), 0) / total : 0;
		const eligible = data.filter(r => r.eligibility === "Eligible").length;
		const not_eligible = total - eligible;

		const kpis = [
			{ icon: "users", accent: "blue", value: total, label: __("Students") },
			{ icon: "percentage", accent: "green", value: `${avg.toFixed(1)}%`, label: __("Average Attendance") },
			{ icon: "star", accent: "amber", value: eligible, label: __("Eligible") },
			{ icon: "warning", accent: "red", value: not_eligible, label: __("Not Eligible") },
		];

		this.$summary.html(kpis.map(k => `
			<div class="asr-kpi-card asr-accent-${k.accent}">
				<div class="asr-kpi-icon">${asr_icon(k.icon)}</div>
				<div class="asr-kpi-body">
					<div class="asr-kpi-value">${k.value}</div>
					<div class="asr-kpi-label">${k.label}</div>
				</div>
			</div>
		`).join(""));
	}

	/* ---------- render: shared DataTable wrapper ---------- */

	_render_table(columns, data, footer_text) {
		this.$table.html(`<div class="asr-datatable-wrap"></div><div class="asr-footer"></div>`);
		this.$table.find(".asr-footer").text(footer_text);
		columns.forEach((c, i) => {
			if (c.editable === undefined) c.editable = false;
			// "fixed" layout keeps every column at a readable minimum width and
			// lets the wrapper scroll horizontally instead of squeezing headers
			// into truncated garbage once condonation columns are added in.
			if (c.width === undefined) c.width = 140;
			// Keep the identifying column (Student ID / Student Name, always
			// first) visible while scrolling right through weeks/months/days —
			// otherwise a wide matrix makes it impossible to tell which row is
			// which once you've scrolled past the first couple of columns.
			if (i === 0 && c.sticky === undefined) c.sticky = true;
		});
		this._datatable = new frappe.DataTable(this.$table.find(".asr-datatable-wrap").get(0), {
			columns,
			data,
			layout: "fixed",
			serialNoColumn: true,
			checkboxColumn: false,
			cellHeight: 42,
			noDataMessage: __("No Data"),
			inlineFilters: false,
		});
	}

	/* ---------- render: Summary tab ---------- */

	_render_summary(data, include_condonation) {
		if (!data.length) {
			this.$summary.empty();
			this._render_empty(__("No attendance records found"), __("Try adjusting or clearing the filters above."));
			return;
		}

		this._render_kpis(data);

		const columns = [
			{
				id: "student_id", name: __("Student ID"), width: 140,
				format: (v, row, col, d) => `<span class="asr-link" onclick="frappe.set_route('Form','Student Master','${esc(d.student)}')">${esc(d.student_id)}</span>`,
			},
			{
				id: "student_name", name: __("Student Name"),
				format: (v, row, col, d) => `<div class="asr-name-cell">${asr_avatar_html(d.student_image)}<div>${esc(d.student_name)}</div></div>`,
			},
			{ id: "course", name: __("Course") },
			{ id: "section", name: __("Section"), format: (v, row, col, d) => esc(d.section || "—") },
			{ id: "total_scheduled_hours", name: __("Scheduled Hrs"), align: "right" },
			{ id: "total_conducted_hours", name: __("Conducted Hrs"), align: "right" },
			{ id: "total_attended_hours", name: __("Attended Hrs"), align: "right" },
			{
				id: "attendance_percentage", name: __("Attendance %"), width: 170,
				format: (v, row, col, d) => {
					const meta = ASR_ELIGIBILITY_META[d.eligibility] || ASR_ELIGIBILITY_META["Not Eligible"];
					const pct = Math.max(0, Math.min(100, d.attendance_percentage || 0));
					return `<div class="asr-progress-wrap">
						<div class="asr-progress-track"><div class="asr-progress-fill" style="width:${pct}%;background:${meta.color}"></div></div>
						<span class="asr-progress-label">${d.attendance_percentage}%</span>
					</div>`;
				},
			},
			{
				id: "eligibility", name: __("Eligibility"),
				format: (v, row, col, d) => {
					const meta = ASR_ELIGIBILITY_META[d.eligibility] || ASR_ELIGIBILITY_META["Not Eligible"];
					return `<span class="asr-badge" style="color:${meta.color};background:${meta.bg}">${meta.dot} ${__(d.eligibility)}</span>`;
				},
			},
		];

		if (include_condonation) {
			columns.push(
				{ id: "condonation_applied", name: __("Condonation Applied"), width: 160, format: (v, row, col, d) => esc(d.condonation_applied || "No") },
				{ id: "condonation_hours", name: __("Condonation Hrs"), width: 140, align: "right", format: (v, row, col, d) => d.condonation_hours ?? "—" },
				{ id: "percentage_before_condonation", name: __("Attendance % (Before Condonation)"), width: 220, align: "right", format: (v, row, col, d) => (d.percentage_before_condonation ?? "—") + "%" },
				{ id: "percentage_after_condonation", name: __("Attendance % (After Condonation)"), width: 220, align: "right", format: (v, row, col, d) => (d.percentage_after_condonation ?? "—") + "%" },
				{ id: "condonation_reason", name: __("Reason"), width: 160, format: (v, row, col, d) => esc(d.condonation_reason || "—") },
				{
					id: "condonation_proof", name: __("Proof"), width: 100,
					format: (v, row, col, d) => d.condonation_proof ? `<a href="${esc(d.condonation_proof)}" target="_blank">${__("View")}</a>` : "—",
				},
				{ id: "condonation_aad_status", name: __("Approver 1 (AAD)"), width: 170, format: (v, row, col, d) => d.condonation_aad_status ? esc(d.condonation_aad_status) : "—" },
				{ id: "condonation_pc_status", name: __("Approver 2 (Programme Chair)"), width: 220, format: (v, row, col, d) => d.condonation_pc_status ? esc(d.condonation_pc_status) : "—" },
			);
		}

		this._render_table(columns, data, __("Showing {0} student record(s)", [data.length]));

		const headers = ["Student ID", "Student Name", "Course", "Section", "Scheduled Hrs", "Conducted Hrs", "Attended Hrs", "Attendance %", "Eligibility"];
		const export_rows = data.map(r => [r.student_id, r.student_name, r.course, r.section, r.total_scheduled_hours, r.total_conducted_hours, r.total_attended_hours, r.attendance_percentage, r.eligibility]);
		if (include_condonation) {
			headers.push(
				"Condonation Applied", "Condonation Hrs",
				"Attendance % (Before Condonation)", "Attendance % (After Condonation)",
				"Reason", "Proof", "Approver 1 (AAD)", "Approver 2 (Programme Chair)"
			);
			data.forEach((r, i) => export_rows[i].push(
				r.condonation_applied || "No", r.condonation_hours ?? "",
				r.percentage_before_condonation ?? "", r.percentage_after_condonation ?? "",
				r.condonation_reason || "", r.condonation_proof || "",
				r.condonation_aad_status || "", r.condonation_pc_status || ""
			));
		}
		this._export = { headers, rows: export_rows, filename: "attendance_summary" };
		this.$export_btn.prop("disabled", false);
	}

	/* ---------- render: Weekly tab (classic spreadsheet look) ---------- */

	_render_weekly({ weeks, rows, min_pct }) {
		this.$summary.empty();

		if (!rows.length || !weeks.length) {
			this._render_empty(__("No attendance records found"), __("Try adjusting the filters, or check that sessions have been conducted for this period."));
			return;
		}
		min_pct = min_pct || 0;

		this._render_legend(min_pct);

		const flat_rows = rows.map(r => {
			const flat = { student: r.student, student_id: r.student_id, student_name: r.student_name, student_image: r.student_image };
			weeks.forEach(w => { flat[w.key] = r.weeks[w.key]; });
			return flat;
		});

		const columns = [
			{
				id: "student_name", name: __("Student Name"),
				format: (v, row, col, d) => {
					const values = weeks.map(w => d[w.key]).filter(Boolean).map(c => c.percentage);
					const row_low = values.length && (values.reduce((a, b) => a + b, 0) / values.length) < min_pct;
					return `<div class="asr-name-cell">${asr_avatar_html(d.student_image)}<div class="${row_low ? "asr-pivot-name-low" : ""}">${esc(d.student_name)}<div class="asr-pivot-subid">${esc(d.student_id)}</div></div></div>`;
				},
			},
			...weeks.map(w => ({
				id: w.key, name: esc(w.label), align: "center",
				format: (v, row, col, d) => {
					const cell = d[w.key];
					if (!cell) return `<div class="asr-cell-muted">—</div>`;
					const low = cell.percentage < min_pct;
					const title = __("{0} of {1} hrs attended", [cell.attended_hours, cell.conducted_hours]);
					return `<div class="asr-pivot-cell ${low ? "asr-pivot-low" : "asr-pivot-ok"}" title="${esc(title)}">${cell.percentage}%</div>`;
				},
			})),
		];

		this._render_table(columns, flat_rows, __("Showing {0} student(s) across {1} week(s)", [rows.length, weeks.length]));

		this._export = {
			headers: ["Student Name", "Student ID", ...weeks.map(w => w.label)],
			rows: rows.map(r => [r.student_name, r.student_id, ...weeks.map(w => {
				const c = r.weeks[w.key];
				return c ? `${c.percentage}% (${c.attended_hours}/${c.conducted_hours} hrs)` : "";
			})]),
			filename: "attendance_weekly",
		};
		this.$export_btn.prop("disabled", false);
	}

	/* ---------- render: Monthly tab (classic spreadsheet look) ---------- */

	_render_monthly({ months, rows, min_pct }) {
		this.$summary.empty();

		if (!rows.length || !months.length) {
			this._render_empty(__("No attendance records found"), __("Try adjusting the filters, or check that sessions have been conducted for this period."));
			return;
		}
		min_pct = min_pct || 0;

		this._render_legend(min_pct);

		const flat_rows = rows.map(r => {
			const flat = { student: r.student, student_id: r.student_id, student_name: r.student_name, student_image: r.student_image };
			months.forEach(m => { flat[m.key] = r.months[m.key]; });
			return flat;
		});

		const columns = [
			{
				id: "student_name", name: __("Student Name"),
				format: (v, row, col, d) => {
					const values = months.map(m => d[m.key]).filter(Boolean).map(c => c.percentage);
					const row_low = values.length && (values.reduce((a, b) => a + b, 0) / values.length) < min_pct;
					return `<div class="asr-name-cell">${asr_avatar_html(d.student_image)}<div class="${row_low ? "asr-pivot-name-low" : ""}">${esc(d.student_name)}<div class="asr-pivot-subid">${esc(d.student_id)}</div></div></div>`;
				},
			},
			...months.map(m => ({
				id: m.key, name: esc(m.label), align: "center",
				format: (v, row, col, d) => {
					const cell = d[m.key];
					if (!cell) return `<div class="asr-cell-muted">—</div>`;
					const low = cell.percentage < min_pct;
					const title = __("{0} of {1} hrs attended", [cell.attended_hours, cell.conducted_hours]);
					return `<div class="asr-pivot-cell ${low ? "asr-pivot-low" : "asr-pivot-ok"}" title="${esc(title)}">${cell.percentage}%</div>`;
				},
			})),
		];

		this._render_table(columns, flat_rows, __("Showing {0} student(s) across {1} month(s)", [rows.length, months.length]));

		this._export = {
			headers: ["Student Name", "Student ID", ...months.map(m => m.label)],
			rows: rows.map(r => [r.student_name, r.student_id, ...months.map(m => {
				const c = r.months[m.key];
				return c ? `${c.percentage}% (${c.attended_hours}/${c.conducted_hours} hrs)` : "";
			})]),
			filename: "attendance_monthly",
		};
		this.$export_btn.prop("disabled", false);
	}

	_render_legend(min_pct) {
		$(`<div class="asr-legend">
			<span class="asr-legend-item"><span class="asr-legend-dot asr-legend-ok"></span>${__("≥ {0}% (meets minimum)", [min_pct])}</span>
			<span class="asr-legend-item"><span class="asr-legend-dot asr-legend-low"></span>${__("< {0}% (below minimum)", [min_pct])}</span>
			<span class="asr-legend-item">${__("Hover a cell for the hours behind it")}</span>
		</div>`).appendTo(this.$summary);
	}

	/* ---------- render: Daily tab (classic spreadsheet look) ---------- */

	_render_daily({ days, rows }) {
		this.$summary.empty();

		if (!rows.length || !days.length) {
			this._render_empty(__("No attendance records found"), __("Try adjusting the filters or the selected date range."));
			return;
		}

		const flat_rows = rows.map(r => {
			const flat = { student: r.student, student_id: r.student_id, student_name: r.student_name, student_image: r.student_image };
			days.forEach(d => { flat[d.key] = r.days[d.key] || null; });
			return flat;
		});

		const columns = [
			{
				id: "student_name", name: __("Student Name"),
				format: (v, row, col, d) => `<div class="asr-name-cell">${asr_avatar_html(d.student_image)}<div>${esc(d.student_name)}<div class="asr-pivot-subid">${esc(d.student_id)}</div></div></div>`,
			},
			...days.map(d => ({
				id: d.key, name: esc(d.label), align: "center",
				format: (v, row, col, data) => {
					const cell = data[d.key];
					if (!cell) return `<div class="asr-cell-muted">—</div>`;
					const ratio = cell.scheduled_hours ? cell.attended_hours / cell.scheduled_hours : 0;
					const cls = ratio >= 1 ? "asr-day-full" : ratio === 0 ? "asr-day-none" : "asr-day-partial";
					return `<div class="asr-day-cell asr-day-cell-clickable ${cls}" data-student="${esc(data.student)}" data-date="${esc(d.key)}">${cell.attended_hours}/${cell.scheduled_hours} hrs</div>`;
				},
			})),
		];

		this._render_table(columns, flat_rows, __("Showing {0} student(s) across {1} day(s)", [rows.length, days.length]));

		// Delegated binding: frappe.DataTable re-renders cells on horizontal/
		// vertical scroll (virtual rendering), which would silently drop any
		// handler bound directly to the initial `.find(...)` elements.
		this.$table.off("click.asr-daily-drilldown").on(
			"click.asr-daily-drilldown",
			".asr-day-cell-clickable",
			(e) => {
				const $cell = $(e.currentTarget);
				this._open_daily_drilldown($cell.data("student"), $cell.data("date"));
			}
		);

		this._export = {
			headers: ["Student Name", "Student ID", ...days.map(d => d.label)],
			rows: rows.map(r => [r.student_name, r.student_id, ...days.map(d => {
				const cell = r.days[d.key];
				return cell ? `${cell.attended_hours}/${cell.scheduled_hours} hrs` : "";
			})]),
			filename: "attendance_daily",
		};
		this.$export_btn.prop("disabled", false);
	}

	/* ---------- Daily tab: cell drill-down ---------- */

	_open_daily_drilldown(student, date) {
		const row = ((this._last_response && this._last_response.rows) || []).find(r => r.student === student);
		const student_label = row ? `${row.student_name} (${row.student_id})` : student;

		const dialog = new frappe.ui.Dialog({
			title: __("{0} — {1}", [student_label, frappe.datetime.str_to_user(date)]),
			size: "large",
			fields: [{ fieldname: "detail_html", fieldtype: "HTML" }],
		});
		dialog.fields_dict.detail_html.$wrapper.html(`<div class="asr-drilldown-loading">${__("Loading...")}</div>`);
		dialog.show();

		const args = Object.assign({}, this._last_daily_filters || {}, { student, date });
		frappe.call({
			method: "slcm.slcm.page.attendance_summary_report.attendance_summary_report.get_daily_drilldown",
			args,
			callback: (r) => this._render_drilldown_dialog(dialog, r.message || []),
			error: () => {
				dialog.fields_dict.detail_html.$wrapper.html(
					`<div class="asr-drilldown-error">${esc(__("Could not load session details."))}</div>`
				);
			},
		});
	}

	_render_drilldown_dialog(dialog, sessions) {
		if (!sessions.length) {
			dialog.fields_dict.detail_html.$wrapper.html(
				`<div class="asr-drilldown-empty">${esc(__("No sessions found for this day."))}</div>`
			);
			return;
		}

		const status_meta = {
			"Present": { color: "#16a34a", bg: "#dcfce7" },
			"Late": { color: "#d97706", bg: "#fef3c7" },
			"Excused": { color: "#0284c7", bg: "#e0f2fe" },
			"Absent": { color: "#dc2626", bg: "#fee2e2" },
			"Not Marked": { color: "#64748b", bg: "#f1f5f9" },
		};

		const attended_statuses = new Set(["Present", "Late", "Excused"]);
		let total_hours = 0;
		let attended_hours = 0;

		const rows_html = sessions.map(s => {
			const meta = status_meta[s.status] || status_meta["Not Marked"];
			const time = (s.from_time && s.to_time) ? `${s.from_time.slice(0, 5)} - ${s.to_time.slice(0, 5)}` : "—";
			const hours = flt(s.duration_hours);
			total_hours += hours;
			if (attended_statuses.has(s.status)) attended_hours += hours;

			return `<tr>
				<td>${esc(s.course)}</td>
				<td>${esc(time)}</td>
				<td>${esc(s.instructor || "—")}</td>
				<td>${esc(s.room || "—")}</td>
				<td>${hours ? hours.toFixed(2) : "—"}</td>
				<td><span class="asr-badge" style="color:${meta.color};background:${meta.bg}">${esc(s.status)}</span></td>
				<td>
					<a href="#" class="asr-drilldown-link" data-session="${esc(s.session)}">${esc(__("View"))}</a>
				</td>
			</tr>`;
		}).join("");

		dialog.fields_dict.detail_html.$wrapper.html(`
			<div class="asr-drilldown-table-wrap">
				<table class="asr-drilldown-table">
					<thead>
						<tr>
							<th>${__("Course")}</th>
							<th>${__("Time")}</th>
							<th>${__("Instructor")}</th>
							<th>${__("Room")}</th>
							<th>${__("Hours")}</th>
							<th>${__("Status")}</th>
							<th></th>
						</tr>
					</thead>
					<tbody>${rows_html}</tbody>
					<tfoot>
						<tr class="asr-drilldown-total-row">
							<td colspan="4">${__("Total")}</td>
							<td>${attended_hours.toFixed(2)} / ${total_hours.toFixed(2)}</td>
							<td colspan="2"></td>
						</tr>
					</tfoot>
				</table>
			</div>
		`);

		dialog.fields_dict.detail_html.$wrapper.find(".asr-drilldown-link").on("click", (e) => {
			e.preventDefault();
			frappe.set_route("Form", "Attendance Session", $(e.currentTarget).data("session"));
		});
	}

	/* ---------- render: shared states ---------- */

	_render_intro() {
		this._render_empty(
			__("Use the filters above to get started"),
			__("Select at least one filter and click Apply Filters to view the attendance summary.")
		);
	}

	_render_empty(title, subtitle) {
		this.$table.html(`
			<div class="asr-empty">
				${asr_icon("empty")}
				<div class="asr-empty-title">${title}</div>
				<div class="asr-empty-subtitle">${subtitle}</div>
			</div>
		`);
	}

	_render_error() {
		this.$summary.empty();
		this._render_empty(__("Something went wrong"), __("Could not load the attendance data. Please try again."));
	}

	_render_skeleton() {
		const bar = `<div class="asr-skeleton-bar"></div>`;
		if (this.tab === "summary") {
			this.$summary.html(
				Array.from({ length: 4 }, () => `
					<div class="asr-kpi-card asr-skeleton-card">
						<div class="asr-skeleton-circle"></div>
						<div class="asr-kpi-body">${bar}${bar}</div>
					</div>
				`).join("")
			);
		} else {
			this.$summary.empty();
		}
		this.$table.html(`
			<div class="asr-table-wrap asr-skeleton-table">
				${Array.from({ length: 6 }, () => `<div class="asr-skeleton-row">${bar}</div>`).join("")}
			</div>
		`);
	}

	/* ---------- CSV export ---------- */

	_export_csv() {
		if (!this._export) return;
		const { headers, rows, filename } = this._export;
		const csv_escape = (v) => {
			const s = v === null || v === undefined ? "" : String(v);
			return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
		};
		const lines = [headers, ...rows].map(row => row.map(csv_escape).join(","));
		const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `${filename}_${frappe.datetime.now_date()}.csv`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}
}

/* ---------- shared helpers ---------- */

function esc(s) {
	return frappe.utils.escape_html(String(s || ""));
}

function asr_avatar_html(image_url) {
	const src = image_url || "/assets/frappe/images/default-avatar.png";
	return `<img class="asr-avatar" src="${esc(src)}" onerror="this.onerror=null;this.src='/assets/frappe/images/default-avatar.png';">`;
}

function asr_icon(name) {
	const icons = {
		users: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,
		percentage: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>`,
		warning: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12" y2="17"/></svg>`,
		star: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
		empty: `<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="asr-empty-icon"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`,
	};
	return icons[name] || "";
}

function asr_inject_styles() {
	if (document.getElementById("asr-styles")) return;
	$(`<style id="asr-styles">
		.asr-page { background: #f8fafc; padding: 4px; }
		.asr-card {
			background: #fff;
			border: 1px solid #e5e9f0;
			border-radius: 12px;
			box-shadow: 0 1px 3px rgba(16, 24, 40, 0.05);
			padding: 24px 28px;
			margin-bottom: 28px;
		}
		.asr-card-title {
			font-size: 15px;
			font-weight: 700;
			color: #1e293b;
			margin-bottom: 18px;
		}
		.asr-filter-grid {
			display: flex;
			flex-wrap: wrap;
			gap: 20px 24px;
			align-items: flex-start;
		}
		.asr-field {
			flex: 1 1 calc(16.666% - 20px);
			min-width: 160px;
			display: flex;
			flex-direction: column;
		}
		@media (max-width: 1200px) {
			.asr-field { flex: 1 1 calc(33.333% - 16px); }
		}
		@media (max-width: 900px) {
			.asr-field { flex: 1 1 calc(50% - 12px); }
		}
		@media (max-width: 600px) {
			.asr-field { flex: 1 1 100%; }
		}
		.asr-field label {
			font-size: 12px;
			font-weight: 600;
			color: #64748b;
			margin-bottom: 6px;
			display: block;
		}
		.asr-field input.form-control,
		.asr-field select.form-control {
			height: 36px;
			font-size: 13px;
			border-radius: 8px;
			width: 100%;
		}
		/* Dropdown checkbox-list multiselect (Select2-style "All X" button) */
		.asr-msdd { position: relative; }
		.asr-msdd-btn {
			width: 100%;
			height: 36px;
			text-align: left;
			background: #fff;
			border: 1px solid #d7dce4;
			border-radius: 8px;
			font-size: 13px;
			color: #334155;
			padding: 0 30px 0 12px;
			position: relative;
			cursor: pointer;
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
			transition: border-color 0.15s;
		}
		.asr-msdd-btn:hover { border-color: #94a3b8; }
		.asr-msdd-btn:focus { outline: none; border-color: #0284c7; box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.12); }
		.asr-msdd-btn::after {
			content: "";
			position: absolute;
			right: 13px;
			top: 46%;
			width: 7px;
			height: 7px;
			border-right: 1.5px solid #94a3b8;
			border-bottom: 1.5px solid #94a3b8;
			transform: translateY(-60%) rotate(45deg);
		}
		.asr-msdd-panel {
			position: absolute;
			top: calc(100% + 4px);
			left: 0;
			z-index: 60;
			background: #fff;
			border: 1px solid #d7dce4;
			border-radius: 8px;
			box-shadow: 0 10px 24px rgba(16, 24, 40, 0.14);
			width: 240px;
			max-height: 280px;
			display: flex;
			flex-direction: column;
		}
		.asr-msdd-search { padding: 8px; border-bottom: 1px solid #f1f4f9; }
		.asr-msdd-search input {
			width: 100%;
			border: 1px solid #e2e8f0;
			border-radius: 6px;
			padding: 5px 8px;
			font-size: 12px;
			outline: none;
		}
		.asr-msdd-options { overflow-y: auto; padding: 4px; flex: 1; }
		.asr-msdd-option {
			display: flex;
			align-items: center;
			gap: 8px;
			padding: 7px 8px;
			font-size: 13px;
			color: #334155;
			border-radius: 6px;
			cursor: pointer;
			margin: 0;
		}
		.asr-msdd-option:hover { background: #f0f6ff; }
		.asr-msdd-option input[type="checkbox"] { width: 15px; height: 15px; cursor: pointer; flex-shrink: 0; }
		.asr-msdd-empty { padding: 14px; font-size: 12px; color: #94a3b8; text-align: center; }
		.asr-month-picker-inputs { display: flex; gap: 8px; }
		.asr-field-inline { flex: 1; }
		.asr-checkbox-row {
			margin-top: 18px;
			padding-top: 16px;
			border-top: 1px solid #f1f4f9;
		}
		.asr-checkbox-row label {
			display: flex;
			align-items: center;
			gap: 8px;
			font-size: 13px;
			font-weight: 600;
			color: #334155;
			cursor: pointer;
			margin: 0;
		}
		.asr-checkbox-row input[type="checkbox"] {
			width: 16px;
			height: 16px;
			cursor: pointer;
		}
		.asr-filter-actions {
			display: flex;
			gap: 10px;
			margin-top: 22px;
			padding-top: 18px;
			border-top: 1px solid #f1f4f9;
		}
		.asr-filter-actions .btn { border-radius: 8px; }

		.asr-tabs {
			display: flex;
			gap: 4px;
			margin-bottom: 20px;
			border-bottom: 1px solid #e5e9f0;
		}
		.asr-tab {
			padding: 10px 18px;
			font-size: 13px;
			font-weight: 600;
			color: #64748b;
			cursor: pointer;
			border-bottom: 2px solid transparent;
			margin-bottom: -1px;
		}
		.asr-tab:hover { color: #1e293b; }
		.asr-tab.active { color: #0284c7; border-bottom-color: #0284c7; }

		.asr-search-row { margin-bottom: 20px; }
		.asr-search-box {
			position: relative;
			max-width: 340px;
		}
		.asr-search-icon {
			position: absolute;
			left: 12px;
			top: 50%;
			transform: translateY(-50%);
			color: #94a3b8;
			pointer-events: none;
		}
		.asr-search-box input {
			width: 100%;
			height: 38px;
			border: 1px solid #d7dce4;
			border-radius: 8px;
			padding: 0 14px 0 36px;
			font-size: 13px;
			color: #334155;
			outline: none;
			transition: border-color 0.15s;
		}
		.asr-search-box input:focus { border-color: #0284c7; box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.12); }

		.asr-kpi-row {
			display: grid;
			grid-template-columns: repeat(4, 1fr);
			gap: 20px;
			margin-bottom: 28px;
		}
		@media (max-width: 900px) {
			.asr-kpi-row { grid-template-columns: repeat(2, 1fr); }
		}
		@media (max-width: 500px) {
			.asr-kpi-row { grid-template-columns: 1fr; }
		}
		.asr-legend {
			grid-column: 1 / -1;
			display: flex;
			flex-wrap: wrap;
			gap: 18px;
			font-size: 12px;
			color: #64748b;
			padding: 10px 4px 0;
		}
		.asr-legend-item { display: flex; align-items: center; gap: 6px; }
		.asr-legend-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
		.asr-legend-ok { background: #15803d; }
		.asr-legend-low { background: #dc2626; }
		.asr-kpi-card {
			background: #fff;
			border: 1px solid #e5e9f0;
			border-radius: 12px;
			box-shadow: 0 1px 3px rgba(16, 24, 40, 0.05);
			padding: 20px 22px;
			display: flex;
			align-items: center;
			gap: 16px;
			min-height: 88px;
			transition: box-shadow 0.15s, transform 0.15s;
		}
		.asr-kpi-card:hover {
			box-shadow: 0 6px 16px rgba(16, 24, 40, 0.1);
			transform: translateY(-2px);
		}
		.asr-kpi-icon {
			width: 44px;
			height: 44px;
			border-radius: 10px;
			display: flex;
			align-items: center;
			justify-content: center;
			flex-shrink: 0;
		}
		.asr-accent-blue .asr-kpi-icon  { background: #e0f2fe; color: #0284c7; }
		.asr-accent-green .asr-kpi-icon { background: #dcfce7; color: #16a34a; }
		.asr-accent-red .asr-kpi-icon   { background: #fee2e2; color: #dc2626; }
		.asr-accent-amber .asr-kpi-icon { background: #fef3c7; color: #d97706; }
		.asr-kpi-value { font-size: 24px; font-weight: 700; color: #1e293b; line-height: 1.2; }
		.asr-kpi-label { font-size: 12px; color: #64748b; margin-top: 2px; }

		.asr-table-card { padding: 0; overflow: hidden; }
		.asr-datatable-wrap { overflow-x: auto; }
		.asr-datatable-wrap .dt-scrollable { overflow: visible; }
		.asr-link { color: #0284c7; cursor: pointer; font-weight: 600; }
		.asr-link:hover { text-decoration: underline; }

		.asr-progress-wrap { display: flex; align-items: center; gap: 10px; min-width: 120px; }
		.asr-progress-track {
			flex: 1;
			height: 8px;
			border-radius: 4px;
			background: #eef1f6;
			overflow: hidden;
		}
		.asr-progress-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
		.asr-progress-label { font-size: 12px; font-weight: 700; color: #334155; width: 42px; text-align: right; }

		.asr-badge {
			display: inline-block;
			padding: 4px 12px;
			border-radius: 999px;
			font-size: 11px;
			font-weight: 700;
			white-space: nowrap;
		}

		.asr-footer {
			padding: 12px 20px;
			font-size: 12px;
			color: #64748b;
			border-top: 1px solid #e5e9f0;
			background: #f8fafc;
		}

		.asr-empty {
			text-align: center;
			padding: 70px 20px;
			color: #64748b;
		}
		.asr-empty-icon { opacity: 0.3; margin-bottom: 16px; }
		.asr-empty-title { font-size: 15px; font-weight: 700; color: #1e293b; margin-bottom: 6px; }
		.asr-empty-subtitle { font-size: 13px; color: #94a3b8; }

		.asr-skeleton-card { pointer-events: none; }
		.asr-skeleton-circle, .asr-skeleton-bar, .asr-skeleton-row {
			background: linear-gradient(90deg, #eef1f6 25%, #e2e8f0 37%, #eef1f6 63%);
			background-size: 400% 100%;
			animation: asr-shimmer 1.4s ease infinite;
			border-radius: 6px;
		}
		.asr-skeleton-circle { width: 44px; height: 44px; border-radius: 10px; flex-shrink: 0; }
		.asr-skeleton-bar { height: 12px; margin-bottom: 8px; width: 70%; }
		.asr-skeleton-bar:first-child { width: 45%; height: 18px; }
		.asr-skeleton-table { padding: 18px 20px; }
		.asr-skeleton-row { height: 20px; margin-bottom: 14px; width: 100%; }
		.asr-skeleton-row:last-child { margin-bottom: 0; }
		@keyframes asr-shimmer {
			0% { background-position: 100% 50%; }
			100% { background-position: 0 50%; }
		}

		/* Pivot tables (Monthly / Daily) — cell content inside frappe.DataTable */
		.asr-pivot-name-low { color: #dc2626; font-weight: 600; }
		.asr-pivot-subid { font-size: 11px; color: #94a3b8; font-weight: 400; }
		.asr-name-cell { display: flex; align-items: center; gap: 8px; }
		.asr-avatar {
			width: 28px; height: 28px; border-radius: 50%;
			object-fit: cover; flex-shrink: 0; border: 1px solid #e5e9f0;
			background: #f1f5f9;
		}
		.asr-pivot-cell { text-align: center; font-weight: 700; }
		.asr-pivot-cell.asr-pivot-ok { color: #15803d; }
		.asr-pivot-cell.asr-pivot-low { color: #dc2626; }
		.asr-cell-muted { text-align: center; color: #cbd5e1; }

		.asr-day-cell { text-align: center; font-weight: 700; border-radius: 6px; }
		.asr-day-full { color: #15803d; background: #f0fdf4; }
		.asr-day-partial { color: #b45309; background: #fffbeb; }
		.asr-day-none { color: #dc2626; background: #fef2f2; }
		.asr-day-cell-clickable { cursor: pointer; transition: box-shadow 0.15s; }
		.asr-day-cell-clickable:hover { box-shadow: inset 0 0 0 2px currentColor; }

		.asr-drilldown-loading, .asr-drilldown-empty, .asr-drilldown-error {
			padding: 30px 10px;
			text-align: center;
			color: #64748b;
			font-size: 13px;
		}
		.asr-drilldown-table-wrap { overflow-x: auto; }
		.asr-drilldown-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.asr-drilldown-table th {
			text-align: left;
			padding: 8px 12px;
			font-size: 11px;
			font-weight: 700;
			text-transform: uppercase;
			color: #64748b;
			border-bottom: 2px solid #e5e9f0;
			white-space: nowrap;
		}
		.asr-drilldown-table td {
			padding: 10px 12px;
			border-bottom: 1px solid #f1f4f9;
			color: #334155;
			white-space: nowrap;
		}
		.asr-drilldown-link { color: #0284c7; font-weight: 600; }
		.asr-drilldown-total-row td {
			font-weight: 700;
			color: #1e293b;
			border-bottom: none;
			border-top: 2px solid #e5e9f0;
		}
	</style>`).appendTo("head");
}
