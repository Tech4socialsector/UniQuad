// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.listview_settings["Classes"] = {
	onload(listview) {
		if (frappe.model.can_get_report("Classes")) {
			listview.page.add_inner_button(__("Student Changes Report"), () =>
				frappe.set_route("query-report", "Class Student Changes"));
		}
		if (frappe.model.can_create("Time Table")) {
			const $btn = listview.page
				.add_inner_button(__("Bulk Time Table"), () =>
					new BulkTimeTableDialog(listview.get_checked_items(true)).show())
				.addClass("btt-dark-btn");
			if ($btn && $btn.length && !$btn.find(".btt-btn-icon").length) {
				$btn.prepend(`<svg class="btt-btn-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;vertical-align:-2px;"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>`);
			}
			add_bulk_tt_style();
		}
	},
	refresh(listview) {
		const $btn = listview.page?.inner_toolbar?.find('button[data-label*="Bulk"]');
		if ($btn && $btn.length) {
			$btn.addClass("btt-dark-btn");
			if (!$btn.find(".btt-btn-icon").length) {
				$btn.prepend(`<svg class="btt-btn-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;vertical-align:-2px;"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>`);
			}
		}
	},
};

/* --------------------------------------------------------------------
   Bulk Time Table: Modern scheduling tool to create recurring sessions
   for one or more Classes with faculty, venues, conflict checks, and preview.
-------------------------------------------------------------------- */
const BTT_METHOD = "slcm.slcm.doctype.time_table.bulk_schedule";
const BTT_DAYS = [
	{ key: "Monday", short: "Mon" },
	{ key: "Tuesday", short: "Tue" },
	{ key: "Wednesday", short: "Wed" },
	{ key: "Thursday", short: "Thu" },
	{ key: "Friday", short: "Fri" },
	{ key: "Saturday", short: "Sat" },
	{ key: "Sunday", short: "Sun" },
];
const BTT_OFF_DAYS = ["Sunday"]; // Institutional default weekly off
const BTT_DEFAULT_SLOT = { from_time: "09:00:00", to_time: "10:00:00", venue: "" };
const BTT_SKIP_OPTIONS = [
	{
		key: "skip_holidays",
		default: 1,
		label: __("Holidays & Weekly Offs"),
		help: __("Skip institutional holidays and Sundays (untick to schedule make-up sessions)"),
		icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 1 0 10 10H12V2z"></path><path d="M12 12 2.1 7.1"></path><path d="M12 12v9"></path></svg>`,
	},
	{
		key: "skip_exams",
		default: 1,
		label: __("Exam Periods"),
		help: __("Skip scheduled exam periods marked in the Institutional Calendar"),
		icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`,
	},
	{
		key: "skip_others",
		default: 0,
		label: __("Events & Other Days"),
		help: __("Skip orientation, university events, and special non-teaching days"),
		icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>`,
	},
];

class BulkTimeTableDialog {
	constructor(class_names) {
		this.classes = [];
		this.days = {};
		this.common_slots = [{ ...BTT_DEFAULT_SLOT }];
		this.venue_per_slot = 0;
		this.skip = Object.fromEntries(BTT_SKIP_OPTIONS.map((o) => [o.key, o.default]));
		this.view = "config"; // "config" | "review"
		this.plan = null;
		this.args = null;
		this.busy = false;

		this.make();
		this.add_classes(class_names || []);
		this.set_default_day();
	}

	show() {
		this.dialog.show();
	}

	make() {
		this.dialog = new frappe.ui.Dialog({
			title: __("Bulk Time Table"),
			size: "extra-large",
			fields: [
				// Header and Stepper
				{ fieldname: "top_header_html", fieldtype: "HTML" },

				// Configuration View Sections (100% full width, no column breaks)
				{ fieldtype: "Section Break", fieldname: "sb_config" },
				{ fieldname: "classes_html", fieldtype: "HTML" },
				{ fieldname: "schedule_html", fieldtype: "HTML" },
				{ fieldname: "slots_html", fieldtype: "HTML" },
				{ fieldname: "skip_html", fieldtype: "HTML" },

				// Review & Preview View Section
				{ fieldtype: "Section Break", fieldname: "sb_review" },
				{ fieldname: "preview_html", fieldtype: "HTML" },
			],
		});

		const $w = this.dialog.$wrapper.addClass("btt-dialog");

		// Header navigation click
		$w.on("click", ".btt-step-nav-btn", (e) => {
			const target = $(e.currentTarget).attr("data-view");
			if (target === "config") {
				this.set_view("config");
			} else if (target === "review" && this.plan) {
				this.set_view("review");
			}
		});

		// Classes events
		$w.on("click", ".btt-add-classes", () => this.pick_classes());
		$w.on("click", ".btt-remove-class", (e) => this.remove_class($(e.currentTarget).attr("data-class")));

		// Schedule & Slots events
		$w.on("click", ".btt-day-chip:not(.disabled)", (e) => this.toggle_day($(e.currentTarget).attr("data-day")));
		$w.on("change", ".btt-slot-time", (e) => this.on_slot_time_change(e.currentTarget));
		$w.on("click", ".btt-add-slot", (e) => this.add_slot($(e.currentTarget).attr("data-day") || null));
		$w.on("click", ".btt-remove-slot", (e) =>
			this.remove_slot($(e.currentTarget).attr("data-day") || null, cint($(e.currentTarget).attr("data-idx"))));
		$w.on("click", ".btt-copy-slots", (e) => this.copy_slots_to_all($(e.currentTarget).attr("data-day")));
		$w.on("change", ".btt-venue-toggle", (e) => {
			this.venue_per_slot = e.currentTarget.checked ? 1 : 0;
			this.render_slots();
		});

		// Skip options events
		$w.on("click", ".btt-skip-card", (e) => {
			if ($(e.target).is('input[type="checkbox"]')) return;
			const $cb = $(e.currentTarget).find('input[type="checkbox"]');
			$cb.prop("checked", !$cb.prop("checked")).trigger("change");
		});
		$w.on("change", ".btt-skip-input", (e) => {
			const key = $(e.currentTarget).attr("data-key");
			this.skip[key] = e.currentTarget.checked ? 1 : 0;
			this.render_skip();
			if (key === "skip_holidays") this.render_slots();
		});

		// Review filter events
		$w.on("click", ".btt-filter-pill", (e) => this.render_session_list($(e.currentTarget).attr("data-filter")));

		// Initialize UI
		this.render_top_header();
		this.render_classes();
		this.render_schedule();
		this.render_slots();
		this.render_skip();
		this.set_view("config");
	}

	/* ---------- Navigation & Mode ---------- */

	set_view(view) {
		this.view = view;
		const is_config = view === "config";

		$(this.dialog.fields_dict.sb_config.wrapper).toggle(is_config);
		$(this.dialog.fields_dict.sb_review.wrapper).toggle(!is_config);

		this.render_top_header();
		this.dialog.$wrapper.find(".modal-body").scrollTop(0);

		if (is_config) {
			this.set_actions(
				__("Preview Schedule") + ` <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-left:6px;vertical-align:-1px;"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>`,
				() => this.preview(),
				__("Cancel"),
				() => this.dialog.hide()
			);
		} else {
			const { summary } = this.plan || {};
			const can_create = summary && summary.create && summary.create <= summary.max_sessions;
			const primary_label = can_create
				? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><polyline points="20 6 9 17 4 12"></polyline></svg>` + __("Create {0} Sessions", [summary.create])
				: __("Nothing to Create");

			this.set_actions(
				primary_label,
				() => this.create(),
				`<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>` + __("Back to Setup"),
				() => this.set_view("config")
			);
			this.toggle_primary(Boolean(can_create));
		}
		this.update_footer_summary();
	}

	set_actions(primary_label, primary, secondary_label, secondary) {
		this.dialog.footer.removeClass("hide");
		this.dialog.get_primary_btn().removeClass("hide disabled").prop("disabled", false)
			.html(primary_label).off("click").on("click", primary);
		this.dialog.get_secondary_btn().removeClass("hide").html(secondary_label).off("click").on("click", secondary);
	}

	toggle_primary(enabled) {
		this.dialog.get_primary_btn().prop("disabled", !enabled).toggleClass("disabled", !enabled);
	}

	render_top_header() {
		const is_config = this.view === "config";
		const class_count = this.classes.length;

		const html = `
			<div class="btt-header-panel">
				<div class="btt-header-info">
					<div class="btt-header-icon-box">
						<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
							<line x1="16" y1="2" x2="16" y2="6"></line>
							<line x1="8" y1="2" x2="8" y2="6"></line>
							<line x1="3" y1="10" x2="21" y2="10"></line>
						</svg>
					</div>
					<div>
						<div class="btt-header-title-row">
							<h3 class="btt-title">${__("Bulk Time Table")}</h3>
							<span class="btt-badge ${class_count ? "has-items" : ""}">${class_count} ${class_count === 1 ? __("Class") : __("Classes")}</span>
						</div>
						<p class="btt-subtitle">${__("Configure recurring schedules, faculty, and venues across multiple classes with automated conflict checking.")}</p>
					</div>
				</div>
				<div class="btt-stepper-pills">
					<button type="button" class="btt-step-pill btt-step-nav-btn ${is_config ? "active" : "done"}" data-view="config">
						<span class="btt-step-num">${is_config ? "1" : "✓"}</span>
						<span class="btt-step-text">${__("1. Schedule Setup")}</span>
					</button>
					<div class="btt-step-divider ${!is_config ? "active" : ""}"></div>
					<button type="button" class="btt-step-pill btt-step-nav-btn ${!is_config ? "active" : ""}" data-view="review" ${!this.plan ? "disabled" : ""}>
						<span class="btt-step-num">2</span>
						<span class="btt-step-text">${__("2. Review & Create")}</span>
					</button>
				</div>
			</div>
		`;
		this.dialog.fields_dict.top_header_html.$wrapper.html(html);
	}

	render_schedule() {
		const $area = this.dialog.fields_dict.schedule_html.$wrapper;
		$area.html(`
			<div class="btt-card btt-dates-card">
				<div class="btt-card-head">
					<div class="btt-card-head-left">
						<div class="btt-card-icon-pill">
							<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
						</div>
						<div>
							<div class="btt-card-title">${__("Date & Recurrence")}</div>
							<div class="btt-card-desc">${__("Specify the first session date and repeating frequency.")}</div>
						</div>
					</div>
				</div>
				<div class="btt-card-body">
					<div class="btt-dates-grid">
						<div class="btt-field-col" data-field="start_date">
							<label class="btt-field-label">${__("Start Date")} <span class="text-danger">*</span></label>
							<div class="btt-field-input" id="btt-ctrl-start-date"></div>
						</div>
						<div class="btt-field-col" data-field="repeat">
							<label class="btt-field-label">${__("Repeat Frequency")}</label>
							<div class="btt-field-input" id="btt-ctrl-repeat"></div>
						</div>
						<div class="btt-field-col" data-field="repeats_till">
							<label class="btt-field-label">${__("Repeats Till")} <span class="text-danger">*</span></label>
							<div class="btt-field-input" id="btt-ctrl-repeats-till"></div>
							<div class="btt-field-help">${__("Defaulted to Academic Term end")}</div>
						</div>
					</div>
				</div>
			</div>
		`);

		const me = this;
		this.start_date_ctrl = btt_date_control(
			$area.find("#btt-ctrl-start-date"),
			"start_date",
			__("Select Start Date"),
			frappe.datetime.get_today(),
			() => {
				me.set_default_day();
				me.update_footer_summary();
			},
			true
		);

		this.repeat_ctrl = btt_select_control(
			$area.find("#btt-ctrl-repeat"),
			"repeat",
			["Weekly", "Daily", "Monthly", "Never"].map((v) => ({ label: __(v), value: v })),
			"Weekly",
			(v) => {
				const is_never = v === "Never";
				$area.find('[data-field="repeats_till"]').toggle(!is_never);
				me.render_slots();
				me.update_footer_summary();
			}
		);

		this.repeats_till_ctrl = btt_date_control(
			$area.find("#btt-ctrl-repeats-till"),
			"repeats_till",
			__("Select End Date"),
			"",
			() => {
				me.update_footer_summary();
			},
			true
		);
	}

	get_start_date() {
		return this.start_date_ctrl?.get_value() || "";
	}
	get_repeat() {
		return this.repeat_ctrl?.get_value() || "Weekly";
	}
	get_repeats_till() {
		return this.repeats_till_ctrl?.get_value() || "";
	}
	set_repeats_till(val) {
		if (this.repeats_till_ctrl) {
			this.repeats_till_ctrl.set_value(val);
		}
	}

	update_footer_summary() {
		let $summary = this.dialog.$wrapper.find(".btt-footer-summary");
		if (!$summary.length) {
			$summary = $(`<div class="btt-footer-summary"></div>`);
			this.dialog.footer.prepend($summary);
		}

		if (this.view === "review") {
			const { summary } = this.plan || {};
			if (summary) {
				$summary.html(`
					<span class="btt-summary-chip btt-chip-success">
						<b>${summary.create}</b> ${__("sessions to create")}
					</span>
					${summary.warnings ? `<span class="btt-summary-chip btt-chip-warning"><b>${summary.warnings}</b> ${__("with warnings")}</span>` : ""}
					${summary.skipped ? `<span class="btt-summary-chip btt-chip-muted"><b>${summary.skipped}</b> ${__("skipped")}</span>` : ""}
				`);
			}
			return;
		}

		const count = this.classes.length;
		const repeat = this.get_repeat();
		const start = this.get_start_date();
		const till = this.get_repeats_till();

		const days = this.selected_days();
		let total_slots = 0;
		if (repeat === "Weekly") {
			days.forEach((d) => (total_slots += (this.days[d]?.slots || []).length));
		} else {
			total_slots = this.common_slots.length;
		}

		const parts = [];
		parts.push(`<b>${count}</b> ${count === 1 ? __("Class") : __("Classes")}`);
		if (repeat === "Weekly") {
			parts.push(`<b>${days.length}</b> ${days.length === 1 ? __("day") : __("days")}/wk (${total_slots} slots)`);
		} else if (repeat !== "Never") {
			parts.push(`<b>${repeat}</b> (${total_slots} slots)`);
		} else {
			parts.push(__("One-time"));
		}

		if (start) {
			const start_fmt = frappe.datetime.str_to_user(start);
			if (repeat !== "Never" && till) {
				parts.push(`${start_fmt} → ${frappe.datetime.str_to_user(till)}`);
			} else {
				parts.push(start_fmt);
			}
		}

		$summary.html(`<span class="btt-summary-text">${parts.join(" · ")}</span>`);
	}

	/* ---------- Step 1: Classes ---------- */

	class_names() {
		return this.classes.map((c) => c.class_name);
	}

	pick_classes() {
		new BttClassPicker({
			added: this.class_names(),
			default_term: this.classes.find((c) => c.academic_term)?.academic_term || "",
			on_add: (names) => this.add_classes(names),
		}).show();
	}

	add_classes(names) {
		const existing = new Set(this.class_names());
		names = names.filter((n) => n && !existing.has(n));
		if (!names.length) {
			this.render_classes();
			this.update_footer_summary();
			return;
		}

		frappe.db
			.get_list("Classes", {
				filters: { name: ["in", names] },
				fields: ["name", "course_name", "course", "section", "group_name", "faculty", "faculty_name", "academic_term"],
				limit: names.length,
			})
			.then((rows) => {
				const have = new Set(this.class_names());
				rows.forEach((c) => {
					if (have.has(c.name)) return;
					const instructor = c.faculty ? String(c.faculty) : "";
					if (instructor && c.faculty_name) frappe.utils.add_link_title("Faculty", instructor, c.faculty_name);
					this.classes.push({
						class_name: c.name,
						course_name: c.course_name || c.course,
						group: c.section || c.group_name || "",
						academic_term: c.academic_term,
						instructor,
						venue: "",
					});
				});
				this.render_top_header();
				this.render_classes();
				this.render_slots();
				this.default_repeats_till();
				this.update_footer_summary();
			});
	}

	remove_class(name) {
		this.classes = this.classes.filter((c) => c.class_name !== name);
		if (this.classes.length !== 1) this.venue_per_slot = 0;
		this.render_top_header();
		this.render_classes();
		this.render_slots();
		this.update_footer_summary();
	}

	default_repeats_till() {
		// Latest term end among the selected classes, used only if it isn't
		// before the Start Date (an old term would give an impossible range)
		const terms = [...new Set(this.classes.map((c) => c.academic_term).filter(Boolean))];
		if (!terms.length || this.get_repeats_till()) return;
		frappe.db
			.get_list("Academic Term", { filters: { name: ["in", terms] }, fields: ["term_end_date"], limit: terms.length })
			.then((rows) => {
				const end = rows.map((r) => r.term_end_date).filter(Boolean).sort().pop();
				const start = this.get_start_date();
				if (!end || this.get_repeats_till() || (start && end < start)) return;
				this.set_repeats_till(end);
				this.update_footer_summary();
			});
	}

	render_classes() {
		const esc = frappe.utils.escape_html;
		const $area = this.dialog.fields_dict.classes_html.$wrapper;
		const count = this.classes.length;

		let bodyHtml = "";
		if (!count) {
			bodyHtml = `
				<div class="btt-empty-state">
					<div class="btt-empty-icon-wrap">
						<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
							<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
							<circle cx="9" cy="7" r="4"></circle>
							<path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
							<path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
						</svg>
					</div>
					<div class="btt-empty-title">${__("No classes selected yet")}</div>
					<div class="btt-empty-desc">${__("Add classes to schedule their recurring timetable sessions. Ticking classes in the list before opening this tool adds them automatically.")}</div>
					<button type="button" class="btn btn-sm btt-primary-btn btt-add-classes mt-3">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
						${__("Add Classes")}
					</button>
				</div>
			`;
		} else {
			const rows = this.classes
				.map(
					(c) => `
					<div class="btt-table-row btt-class-row" data-class="${esc(c.class_name)}">
						<div class="btt-col-class">
							<div class="btt-class-course-title">${esc(c.course_name || __("Untitled Course"))}</div>
							<div class="btt-class-meta-row">
								<span class="btt-code-pill">${esc(c.class_name)}</span>
								${c.group ? `<span class="btt-section-badge">${__("Sec")} ${esc(c.group)}</span>` : ""}
							</div>
						</div>
						<div class="btt-col-faculty" data-field="instructor"></div>
						<div class="btt-col-venue" data-field="venue"></div>
						<div class="btt-col-action">
							<button type="button" class="btt-icon-btn btt-remove-class" data-class="${esc(c.class_name)}" title="${__("Remove class")}">
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
							</button>
						</div>
					</div>
				`
				)
				.join("");

			bodyHtml = `
				<div class="btt-table-wrap">
					<div class="btt-table-head btt-class-head">
						<div class="btt-col-class">${__("Class & Course")}</div>
						<div class="btt-col-faculty">${__("Faculty")}</div>
						<div class="btt-col-venue">${__("Default Venue")}</div>
						<div class="btt-col-action"></div>
					</div>
					<div class="btt-table-rows">${rows}</div>
				</div>
			`;
		}

		$area.html(`
			<div class="btt-card btt-classes-card">
				<div class="btt-card-head">
					<div class="btt-card-head-left">
						<div class="btt-card-icon-pill">
							<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
						</div>
						<div>
							<div class="btt-card-title">${__("Selected Classes")} ${count ? `<span class="btt-count-chip">${count}</span>` : ""}</div>
							<div class="btt-card-desc">${__("Each class can have its own dedicated faculty and venue.")}</div>
						</div>
					</div>
					<div class="btt-card-head-right">
						<button type="button" class="btn btn-xs btt-outline-btn btt-add-classes">
							<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
							${__("Add Classes")}
						</button>
					</div>
				</div>
				<div class="btt-card-body">${bodyHtml}</div>
				${count ? `<div class="btt-card-foot-tip"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg> ${__("Tip: You can change the instructor or venue per class directly here before creating the schedule.")}</div>` : ""}
			</div>
		`);

		// Bind link controls
		this.classes.forEach((c) => {
			const $row = $area.find(`.btt-class-row[data-class="${CSS.escape(c.class_name)}"]`);
			btt_link_control(
				$row.find('[data-field="instructor"]'),
				"Faculty",
				__("Select Faculty..."),
				c.instructor,
				(v) => (c.instructor = v)
			);
			btt_link_control(
				$row.find('[data-field="venue"]'),
				"Venue Master",
				__("Select Venue..."),
				c.venue,
				(v) => (c.venue = v),
				{ is_active: 1 }
			);
		});
	}

	/* ---------- Step 2: Time Slots ---------- */

	is_weekly() {
		return this.get_repeat() === "Weekly";
	}

	off_days() {
		return this.skip.skip_holidays ? BTT_OFF_DAYS : [];
	}

	selected_days() {
		const off = this.off_days();
		return BTT_DAYS.filter((d) => !off.includes(d.key) && this.days[d.key]?.selected).map((d) => d.key);
	}

	slots_for(day) {
		return day ? this.get_day(day).slots : this.common_slots;
	}

	set_default_day() {
		if (!this.dialog) return;
		const start = this.get_start_date();
		if (start && !Object.values(this.days).some((d) => d.selected)) {
			const day = moment(start).format("dddd");
			if (!this.off_days().includes(day)) {
				this.get_day(day).selected = true;
			}
		}
		this.render_slots();
		this.update_footer_summary();
	}

	get_day(day) {
		if (!this.days[day]) {
			const template = this.selected_days().map((d) => this.days[d].slots)[0] || [BTT_DEFAULT_SLOT];
			this.days[day] = { selected: false, slots: template.map((s) => ({ ...s })) };
		}
		return this.days[day];
	}

	toggle_day(day) {
		const d = this.get_day(day);
		d.selected = !d.selected;
		this.render_slots();
		this.update_footer_summary();
	}

	add_slot(day) {
		const slots = this.slots_for(day);
		const last = slots[slots.length - 1];
		let slot = { ...BTT_DEFAULT_SLOT };
		if (last && last.from_time && last.to_time) {
			const length = moment(last.to_time, "HH:mm:ss").diff(moment(last.from_time, "HH:mm:ss"), "minutes");
			const from = moment(last.to_time, "HH:mm:ss");
			const to = from.clone().add(length, "minutes");
			if (length > 0 && to.isSame(from, "day")) {
				slot = { from_time: from.format("HH:mm:ss"), to_time: to.format("HH:mm:ss"), venue: last.venue || "" };
			}
		}
		slots.push(slot);
		this.render_slots();
		this.update_footer_summary();
	}

	remove_slot(day, idx) {
		const slots = this.slots_for(day);
		if (slots.length <= 1) return;
		slots.splice(idx, 1);
		this.render_slots();
		this.update_footer_summary();
	}

	copy_slots_to_all(source) {
		const slots = this.get_day(source).slots;
		this.selected_days().forEach((day) => {
			if (day !== source) this.days[day].slots = slots.map((s) => ({ ...s }));
		});
		this.render_slots();
		this.update_footer_summary();
		frappe.show_alert({
			message: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><polyline points="20 6 9 17 4 12"></polyline></svg> ${__("Copied {0}'s slots to all active days", [__(source)])}`,
			indicator: "green",
		});
	}

	on_slot_time_change(input) {
		const $input = $(input);
		const slot = this.slots_for($input.attr("data-day") || null)[cint($input.attr("data-idx"))];
		if (slot) {
			slot[$input.attr("data-field")] = input.value ? `${input.value}:00` : "";
			const $row = $input.closest(".btt-slot-item");
			const from = $row.find('[data-field="from_time"]').val();
			const to = $row.find('[data-field="to_time"]').val();
			const dur = btt_calc_duration(from ? `${from}:00` : "", to ? `${to}:00` : "");
			$row.find(".btt-duration-badge").text(dur || "–");
			this.update_footer_summary();
		}
	}

	slot_list_html(day) {
		const slots = this.slots_for(day);
		const key = day || "";
		return slots
			.map((s, idx) => {
				const dur = btt_calc_duration(s.from_time, s.to_time);
				return `
					<div class="btt-slot-item">
						<div class="btt-slot-time-group">
							<div class="btt-time-input-wrap">
								<svg class="btt-time-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
								<input type="time" class="btt-time-input btt-slot-time" data-day="${key}" data-idx="${idx}" data-field="from_time"
									value="${(s.from_time || "").slice(0, 5)}" aria-label="${__("Start Time")}">
							</div>
							<span class="btt-slot-arrow">→</span>
							<div class="btt-time-input-wrap">
								<svg class="btt-time-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
								<input type="time" class="btt-time-input btt-slot-time" data-day="${key}" data-idx="${idx}" data-field="to_time"
									value="${(s.to_time || "").slice(0, 5)}" aria-label="${__("End Time")}">
							</div>
							<span class="btt-duration-badge">${dur || "–"}</span>
						</div>
						${this.venue_per_slot ? `<div class="btt-slot-venue-wrap" data-day="${key}" data-idx="${idx}"></div>` : ""}
						<button type="button" class="btt-icon-btn btt-remove-slot" data-day="${key}" data-idx="${idx}"
							title="${__("Remove slot")}" ${slots.length <= 1 ? "disabled" : ""}>
							<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
						</button>
					</div>
				`;
			})
			.join("");
	}

	day_block_html(day, label) {
		const can_copy = day && this.selected_days().length > 1;
		return `
			<div class="btt-day-card">
				<div class="btt-day-card-head">
					<div class="btt-day-title-pill">
						<span class="btt-day-dot"></span>
						<span class="btt-day-title">${label}</span>
					</div>
					<div class="btt-day-card-actions">
						<button type="button" class="btn btn-xs btt-link-btn btt-add-slot" data-day="${day || ""}">
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
							${__("Add Slot")}
						</button>
						${
							can_copy
								? `<button type="button" class="btn btn-xs btt-link-btn btt-copy-slots" data-day="${day}">
									<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
									${__("Copy to all active days")}
								</button>`
								: ""
						}
					</div>
				</div>
				<div class="btt-day-slots-list">${this.slot_list_html(day)}</div>
			</div>
		`;
	}

	render_slots() {
		if (!this.dialog) return;
		const $area = this.dialog.fields_dict.slots_html.$wrapper;
		const single_class = this.classes.length === 1;
		if (!single_class) this.venue_per_slot = 0;

		const venue_toggle = single_class
			? `
				<label class="btt-toggle-switch-wrap">
					<input type="checkbox" class="btt-toggle-input btt-venue-toggle" ${this.venue_per_slot ? "checked" : ""}>
					<span class="btt-toggle-track"></span>
					<span class="btt-toggle-label">${__("Different venue per slot")}</span>
				</label>
			`
			: "";

		let body = "";
		if (this.is_weekly()) {
			const off = this.off_days();
			const chips = BTT_DAYS.map((d) => {
				const disabled = off.includes(d.key);
				const active = !disabled && this.days[d.key]?.selected;
				return `
					<button type="button" class="btt-day-chip ${active ? "active" : ""} ${disabled ? "disabled" : ""}"
						data-day="${d.key}" title="${disabled ? __("Weekly off - untick 'Holidays & Weekly Offs' below to enable") : __(d.key)}">
						<span class="btt-chip-dot"></span>
						<span class="btt-chip-text">${__(d.short)}</span>
					</button>
				`;
			}).join("");

			const days = this.selected_days();
			body = `
				<div class="btt-day-chips-bar">
					<div class="btt-day-chips-label">${__("Select weekdays:")}</div>
					<div class="btt-day-chips-group">${chips}</div>
				</div>
				<div class="btt-days-container">
					${
						days.map((day) => this.day_block_html(day, __(day))).join("") ||
						`<div class="btt-empty-day-state">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
							<span>${__("Select one or more weekdays above to set class times.")}</span>
						</div>`
					}
				</div>
			`;
		} else {
			body = `
				<div class="btt-days-container">
					${this.day_block_html(null, __("Recurring Session Time"))}
				</div>
			`;
		}

		$area.html(`
			<div class="btt-card btt-slots-card">
				<div class="btt-card-head">
					<div class="btt-card-head-left">
						<div class="btt-card-icon-pill">
							<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
						</div>
						<div>
							<div class="btt-card-title">${__("Time Slots & Schedule")}</div>
							<div class="btt-card-desc">${__("Define one or more session intervals per day (e.g. morning & afternoon).")}</div>
						</div>
					</div>
					<div class="btt-card-head-right">${venue_toggle}</div>
				</div>
				<div class="btt-card-body">${body}</div>
			</div>
		`);

		if (this.venue_per_slot) {
			$area.find(".btt-slot-venue-wrap").each((_, el) => {
				const slot = this.slots_for($(el).attr("data-day") || null)[cint($(el).attr("data-idx"))];
				btt_link_control($(el), "Venue Master", __("Venue..."), slot.venue, (v) => (slot.venue = v), { is_active: 1 });
			});
		}
	}

	/* ---------- Step 3: Skip & Exclusions ---------- */

	render_skip() {
		const options = BTT_SKIP_OPTIONS.map(
			(o) => `
			<div class="btt-skip-card ${this.skip[o.key] ? "checked" : ""}" data-key="${o.key}">
				<div class="btt-skip-icon-wrap">${o.icon}</div>
				<div class="btt-skip-body">
					<div class="btt-skip-title-row">
						<span class="btt-skip-title">${o.label}</span>
						<label class="btt-toggle-switch-wrap small">
							<input type="checkbox" class="btt-toggle-input btt-skip-input" data-key="${o.key}" ${this.skip[o.key] ? "checked" : ""}>
							<span class="btt-toggle-track"></span>
						</label>
					</div>
					<div class="btt-skip-help">${o.help}</div>
				</div>
			</div>
		`
		).join("");

		this.dialog.fields_dict.skip_html.$wrapper.html(`
			<div class="btt-card btt-skip-card-container">
				<div class="btt-card-head">
					<div class="btt-card-head-left">
						<div class="btt-card-icon-pill">
							<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
						</div>
						<div>
							<div class="btt-card-title">${__("Calendar Exclusions")}</div>
							<div class="btt-card-desc">${__("Automatically skip non-teaching dates, holidays, and institutional exam schedules.")}</div>
						</div>
					</div>
				</div>
				<div class="btt-card-body">
					<div class="btt-skip-grid">${options}</div>
				</div>
			</div>
		`);
	}

	/* ---------- Step 4: Review & Preview ---------- */

	get_args() {
		const classes = this.classes.map((c) => ({
			class_name: c.class_name,
			instructor: c.instructor || "",
			venue: c.venue || "",
		}));
		if (!classes.length) {
			frappe.msgprint(__("Please select at least one Class."));
			return null;
		}

		const venue_per_day = this.venue_per_slot && classes.length === 1 ? 1 : 0;
		const missing_venue = classes.filter((c) => !c.venue).map((c) => c.class_name);
		if (!venue_per_day && missing_venue.length) {
			frappe.msgprint(__("Please select the default Venue for: {0}", [missing_venue.join(", ")]));
			return null;
		}

		const start_date = this.get_start_date();
		if (!start_date) {
			frappe.msgprint(__("Please select the Start Date."));
			return null;
		}

		const repeat = this.get_repeat();
		let repeats_till = this.get_repeats_till();
		if (repeat !== "Never") {
			if (!repeats_till) {
				frappe.msgprint(__("Please select the Repeats Till date."));
				return null;
			}
			if (repeats_till < start_date) {
				frappe.msgprint(__("Repeats Till cannot be before the Start Date."));
				return null;
			}
		} else {
			repeats_till = null;
		}

		let slots = [];
		if (repeat === "Weekly") {
			this.selected_days().forEach((day) => this.days[day].slots.forEach((s) => slots.push({ day, ...s })));
			if (!slots.length) {
				frappe.msgprint(__("Please select at least one weekday."));
				return null;
			}
		} else {
			slots = this.common_slots.map((s) => ({ ...s, day: null }));
		}

		if (slots.some((s) => !s.from_time || !s.to_time)) {
			frappe.msgprint(__("Please provide valid start and end times for all slots."));
			return null;
		}

		return {
			classes,
			start_date,
			repeat,
			repeats_till,
			slots,
			venue_per_day,
			...this.skip,
		};
	}

	preview() {
		if (this.busy) return;
		const args = this.get_args();
		if (!args) return;
		this.busy = true;

		frappe.call({
			method: `${BTT_METHOD}.preview_bulk_schedule`,
			args: { args },
			freeze: true,
			freeze_message: `<svg class="btt-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:8px;vertical-align:-3px;"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a10 10 0 0 1 10 10"></path></svg>` + __("Checking calendar holidays and conflicts..."),
			always: () => (this.busy = false),
			callback: (r) => {
				if (!r.message) return;
				this.args = args;
				this.plan = r.message;
				this.render_preview();
				this.set_view("review");
			},
		});
	}

	render_preview() {
		const { summary, classes } = this.plan;
		const esc = frappe.utils.escape_html;
		const too_many = summary.create > summary.max_sessions;

		const by_day = {};
		summary.slots.forEach((s) => {
			const time = `${btt_time(s.from_time)} – ${btt_time(s.to_time)}${s.venue ? ` · ${esc(s.venue)}` : ""}`;
			(by_day[s.day || ""] = by_day[s.day || ""] || []).push(time);
		});
		const slot_chips = Object.entries(by_day)
			.map(([day, times]) => `<span class="btt-meta-pill">${day ? `<b>${__(day).slice(0, 3)}</b> ` : ""}${times.join(", ")}</span>`)
			.join("");

		const range =
			summary.repeat === "Never"
				? frappe.datetime.str_to_user(summary.start_date)
				: `${frappe.datetime.str_to_user(summary.start_date)} → ${frappe.datetime.str_to_user(summary.end_date)}`;

		const class_rows = classes
			.map(
				(c) => `
				<tr>
					<td>
						<div class="btt-class-course-title">${esc(c.course || "")}</div>
						<div class="btt-class-meta-row">
							<span class="btt-code-pill">${esc(c.class_name)}</span>
							${c.group ? `<span class="btt-section-badge">${esc(c.group)}</span>` : ""}
						</div>
					</td>
					<td>${esc(c.faculty_name || "–")}</td>
					<td>${esc(c.venue || "–")}</td>
					<td class="text-right"><span class="btt-stat-badge success">${c.create}</span></td>
					<td class="text-right">${c.warnings ? `<span class="btt-stat-badge warning">${c.warnings}</span>` : "–"}</td>
					<td class="text-right">${c.skipped ? `<span class="btt-stat-badge muted">${c.skipped}</span>` : "–"}</td>
				</tr>
			`
			)
			.join("");

		this.dialog.fields_dict.preview_html.$wrapper.html(`
			<div class="btt-review-overview-card">
				<div class="btt-overview-head">
					<div>
						<div class="btt-overview-title">${__(summary.repeat === "Never" ? "One-Time Schedule" : `${summary.repeat} Recurrence`)}</div>
						<div class="btt-overview-range">${range}</div>
					</div>
					<div class="btt-overview-slots">${slot_chips}</div>
				</div>

				<div class="btt-stats-grid">
					<div class="btt-stat-card primary">
						<div class="btt-stat-num">${summary.create}</div>
						<div class="btt-stat-label">${__("Sessions to Create")}</div>
					</div>
					<div class="btt-stat-card">
						<div class="btt-stat-num">${summary.classes}</div>
						<div class="btt-stat-label">${__("Target Classes")}</div>
					</div>
					<div class="btt-stat-card ${summary.warnings ? "warning" : ""}">
						<div class="btt-stat-num">${summary.warnings}</div>
						<div class="btt-stat-label">${__("With Warnings")}</div>
					</div>
					<div class="btt-stat-card">
						<div class="btt-stat-num">${summary.skipped}</div>
						<div class="btt-stat-label">${__("Skipped Dates")}</div>
					</div>
				</div>

				${
					too_many
						? `<div class="btt-alert danger">
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
							<span>${__("This run would generate {0} sessions; system limit is {1}. Please shorten the date range or schedule fewer classes.", [summary.create, summary.max_sessions])}</span>
						</div>`
						: ""
				}

				${
					summary.warnings
						? `<div class="btt-alert warning">
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
							<span>${__("Some sessions have warnings (e.g. faculty teaching another class simultaneously, or dates falling on holidays). These sessions will still be created, but flagged.")}</span>
						</div>`
						: ""
				}
			</div>

			<div class="btt-card mt-3">
				<div class="btt-card-head">
					<div class="btt-card-head-left">
						<div class="btt-card-title">${__("Class Breakdown")}</div>
					</div>
				</div>
				<div class="btt-card-body" style="padding:0;">
					<table class="btt-data-table">
						<thead>
							<tr>
								<th>${__("Class & Course")}</th>
								<th>${__("Faculty")}</th>
								<th>${__("Venue")}</th>
								<th class="text-right">${__("To Create")}</th>
								<th class="text-right">${__("Warnings")}</th>
								<th class="text-right">${__("Skipped")}</th>
							</tr>
						</thead>
						<tbody>${class_rows}</tbody>
					</table>
				</div>
			</div>

			<div class="btt-card mt-3">
				<div class="btt-card-head">
					<div class="btt-card-head-left">
						<div class="btt-card-title">${__("Generated Session Calendar")}</div>
						<div class="btt-card-desc">${__("Inspect individual dates, slots, and conflict reasons.")}</div>
					</div>
					<div class="btt-card-head-right">
						<div class="btt-filter-tabs">
							<button type="button" class="btt-filter-pill" data-filter="all">${__("All")} <span>${this.plan.sessions.length}</span></button>
							<button type="button" class="btt-filter-pill" data-filter="create">${__("To Create")} <span>${summary.create}</span></button>
							<button type="button" class="btt-filter-pill" data-filter="warning">${__("Warnings")} <span>${summary.warnings}</span></button>
							<button type="button" class="btt-filter-pill" data-filter="skipped">${__("Skipped")} <span>${summary.skipped}</span></button>
						</div>
					</div>
				</div>
				<div class="btt-card-body btt-session-explorer-body" style="padding:0;">
					<div class="btt-session-table-scroll"></div>
				</div>
			</div>
		`);

		this.render_session_list(summary.skipped ? "skipped" : "create");
	}

	render_session_list(filter) {
		const esc = frappe.utils.escape_html;
		const match = {
			all: () => true,
			create: (s) => s.status !== "skipped",
			warning: (s) => s.status === "warning",
			skipped: (s) => s.status === "skipped",
		}[filter] || (() => true);

		this.dialog.$wrapper.find(".btt-filter-pill").removeClass("active");
		this.dialog.$wrapper.find(`.btt-filter-pill[data-filter="${filter}"]`).addClass("active");

		const labels = {
			ok: `<span class="btt-status-tag success"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg> ${__("Create")}</span>`,
			warning: `<span class="btt-status-tag warning"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg> ${__("Warning")}</span>`,
			skipped: `<span class="btt-status-tag muted"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> ${__("Skip")}</span>`,
		};

		const rows = this.plan.sessions.filter(match);
		const $container = this.dialog.$wrapper.find(".btt-session-table-scroll");

		if (!rows.length) {
			$container.html(`<div class="btt-empty-day-state py-4">${__("No sessions matching this filter.")}</div>`);
			return;
		}

		$container.html(`
			<table class="btt-data-table">
				<thead>
					<tr>
						<th>${__("Date & Day")}</th>
						<th>${__("Time Interval")}</th>
						<th>${__("Class")}</th>
						<th>${__("Venue")}</th>
						<th>${__("Status")}</th>
						<th>${__("Note / Reason")}</th>
					</tr>
				</thead>
				<tbody>
					${rows
						.map(
							(s) => `
						<tr>
							<td class="text-nowrap">
								<div style="font-weight:600;">${frappe.datetime.str_to_user(s.date)}</div>
								<div class="text-muted small">${__(s.weekday)}</div>
							</td>
							<td class="text-nowrap font-monospace small">${btt_time(s.from_time)} – ${btt_time(s.to_time)}</td>
							<td>
								<div class="btt-class-course-title">${esc(s.course || "")}</div>
								<div class="btt-class-meta-row"><span class="btt-code-pill">${esc(s.class_name)}</span></div>
							</td>
							<td>${esc(s.venue || "–")}</td>
							<td>${labels[s.status]}</td>
							<td class="btt-note-cell">${esc(s.reason || "–")}</td>
						</tr>
					`
						)
						.join("")}
				</tbody>
			</table>
		`);
	}

	create() {
		const { summary } = this.plan || {};
		if (this.busy || !summary || !summary.create || summary.create > summary.max_sessions) return;
		this.busy = true;
		this.toggle_primary(false);
		bind_bulk_tt_progress();

		frappe.call({
			method: `${BTT_METHOD}.create_bulk_schedule`,
			args: { args: this.args },
			freeze: true,
			freeze_message: `<svg class="btt-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:8px;vertical-align:-3px;"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a10 10 0 0 1 10 10"></path></svg>` + __("Generating Time Table sessions..."),
			always: () => (this.busy = false),
			error: () => this.toggle_primary(true),
			callback: (r) => {
				if (!r.message) return;
				const res = r.message;
				this.dialog.hide();

				let message = `<div style="font-size:14px;margin-bottom:8px;">${__("Successfully created <b>{0}</b> session(s) for <b>{1}</b> class(es).", [res.created, res.classes.length])}</div>`;
				if (res.skipped) {
					message += `<div class="text-muted small mb-1">• ${__("{0} date(s) skipped due to holidays or exam periods.", [res.skipped])}</div>`;
				}
				if (res.warnings) {
					message += `<div class="text-warning small">• ${__("{0} session(s) created with faculty conflict warnings.", [res.warnings])}</div>`;
				}

				frappe.msgprint({
					title: __("Time Table Generated"),
					message,
					indicator: res.warnings ? "orange" : "green",
					primary_action: {
						label: __("Open in Time Table List"),
						action: () => {
							frappe.hide_msgprint();
							frappe.route_options = { class_name: ["in", res.classes] };
							frappe.set_route("List", "Time Table");
						},
					},
				});
			},
		});
	}
}

/* --------------------------------------------------------------------
   Helpers
-------------------------------------------------------------------- */
function btt_link_control($parent, doctype, placeholder, value, on_change, filters) {
	const control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Link",
			options: doctype,
			fieldname: frappe.scrub(doctype),
			placeholder,
			get_query: filters ? () => ({ filters }) : null,
			onchange: () => on_change(control.get_value() || ""),
		},
		parent: $parent,
		render_input: true,
		only_input: true,
	});
	control.set_value(value || "");
	return control;
}

function btt_date_control($parent, fieldname, placeholder, value, on_change, reqd) {
	const control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Date",
			fieldname,
			placeholder,
			reqd: reqd ? 1 : 0,
			onchange: () => on_change && on_change(control.get_value() || ""),
		},
		parent: $parent,
		render_input: true,
		only_input: true,
	});
	if (value) control.set_value(value);
	return control;
}

function btt_select_control($parent, fieldname, options, value, on_change) {
	const control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Select",
			fieldname,
			options,
			onchange: () => on_change && on_change(control.get_value() || ""),
		},
		parent: $parent,
		render_input: true,
		only_input: true,
	});
	if (value) control.set_value(value);
	return control;
}

function btt_time(t) {
	return t ? moment(t, "HH:mm:ss").format("hh:mm A") : "-";
}

function btt_calc_duration(from_t, to_t) {
	if (!from_t || !to_t) return "";
	const m_from = moment(from_t, "HH:mm:ss");
	const m_to = moment(to_t, "HH:mm:ss");
	const diff = m_to.diff(m_from, "minutes");
	if (diff <= 0) return "";
	const h = Math.floor(diff / 60);
	const m = diff % 60;
	if (h && m) return `${h}h ${m}m`;
	if (h) return `${h}h`;
	return `${m}m`;
}

/* --------------------------------------------------------------------
   Class picker: search + Term / Programme / Section filters, checkbox
   rows, "select all shown", paging. Classes already in the schedule are
   listed as "Added" and can't be picked twice. The selection survives
   filter changes, so classes can be collected across terms/programmes.
-------------------------------------------------------------------- */
const BTT_PICKER_PAGE = 20;
const BTT_PICKER_FILTERS = [
	{ fieldname: "academic_term", doctype: "Academic Term", placeholder: __("All terms") },
	{ fieldname: "programme", doctype: "Programme", placeholder: __("All programmes") },
	{ fieldname: "section", doctype: "Section", placeholder: __("All sections") },
];

class BttClassPicker {
	constructor({ added, default_term, on_add }) {
		this.added = new Set(added || []);
		this.on_add = on_add;
		this.selected = new Map(); // name -> row, kept across searches
		this.rows = [];
		this.query = "";
		this.filters = { academic_term: default_term || "", programme: "", section: "" };
		this.limit = BTT_PICKER_PAGE;
		this.request_no = 0;
		this.make();
	}

	show() {
		this.dialog.show();
		this.load();
		setTimeout(() => this.$area.find(".btt-picker-q").trigger("focus"), 300);
	}

	make() {
		this.dialog = new frappe.ui.Dialog({
			title: __("Add Classes"),
			size: "large",
			fields: [{ fieldname: "picker_html", fieldtype: "HTML" }],
		});
		this.dialog.$wrapper.addClass("btt-dialog btt-picker");
		this.$area = this.dialog.fields_dict.picker_html.$wrapper;

		this.$area.html(`
			<div class="btt-picker-head">
				<div class="btt-header-info">
					<div class="btt-header-icon-box">
						<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path></svg>
					</div>
					<div>
						<h3 class="btt-title">${__("Add Classes")}</h3>
						<p class="btt-subtitle">${__("Search and tick the classes to schedule together.")}</p>
					</div>
				</div>
				<button type="button" class="btt-icon-btn btt-picker-close" title="${__("Close")}">
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
				</button>
			</div>
			<div class="btt-picker-filters">
				<div class="btt-picker-search">
					<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
					<input type="search" class="form-control btt-picker-q" placeholder="${__("Search course or class ID...")}" autocomplete="off">
				</div>
				${BTT_PICKER_FILTERS.map((f) => `<div class="btt-picker-filter" data-filter="${f.fieldname}"></div>`).join("")}
			</div>
			<div class="btt-picker-toolbar">
				<label class="btt-picker-all-label">
					<input type="checkbox" class="btt-picker-all">
					<span>${__("Select all shown")}</span>
				</label>
				<span class="btt-picker-status"></span>
				<button type="button" class="btt-link-btn btt-picker-reset">${__("Clear filters")}</button>
			</div>
			<div class="btt-picker-list"></div>
			<div class="btt-picker-more"></div>
		`);

		this.make_filter_controls();

		const reload_debounced = frappe.utils.debounce(() => this.reload(), 300);
		this.$area.on("input", ".btt-picker-q", (e) => {
			this.query = (e.currentTarget.value || "").trim();
			reload_debounced();
		});
		this.$area.on("keydown", ".btt-picker-q", (e) => e.key === "Enter" && e.preventDefault());
		this.$area.on("change", ".btt-pick-cb", (e) => this.toggle_row($(e.currentTarget).attr("data-name"), e.currentTarget.checked));
		this.$area.on("change", ".btt-picker-all", (e) => this.toggle_all(e.currentTarget.checked));
		this.$area.on("click", ".btt-picker-more-btn", () => {
			this.limit += BTT_PICKER_PAGE;
			this.load();
		});
		this.$area.on("click", ".btt-picker-reset", () => this.reset_filters());
		this.$area.on("click", ".btt-picker-close", () => this.dialog.hide());

		// Footer: live selection count + actions (bound directly, no form validation needed)
		this.dialog.footer.removeClass("hide");
		this.$selected = $(`<div class="btt-footer-summary btt-picker-selected"></div>`).prependTo(this.dialog.footer);
		this.dialog.get_secondary_btn().removeClass("hide").html(__("Cancel")).off("click").on("click", () => this.dialog.hide());
		this.dialog.get_primary_btn().removeClass("hide").off("click").on("click", () => this.submit());
		this.update_footer();
	}

	reset_filters() {
		this.query = "";
		this.$area.find(".btt-picker-q").val("");
		BTT_PICKER_FILTERS.forEach((f) => (this.filters[f.fieldname] = ""));
		this.make_filter_controls(); // rebuilt so their inputs are emptied too
		this.reload();
	}

	make_filter_controls() {
		BTT_PICKER_FILTERS.forEach((f) => {
			const show_full_name = (value) => value && f.doctype === "Academic Term" && frappe.utils.add_link_title(f.doctype, value, value);
			show_full_name(this.filters[f.fieldname]);
			const control = btt_link_control(
				this.$area.find(`[data-filter="${f.fieldname}"]`).empty(),
				f.doctype,
				f.placeholder,
				this.filters[f.fieldname],
				(value) => {
					if ((this.filters[f.fieldname] || "") === (value || "")) return; // set_value echoes back
					this.filters[f.fieldname] = value || "";
					if (show_full_name(value)) control?.set_formatted_input(value);
					this.reload();
				}
			);
		});
	}

	reload() {
		this.limit = BTT_PICKER_PAGE;
		this.load();
	}

	load() {
		const request_no = ++this.request_no; // only the latest search may render
		const filters = {};
		BTT_PICKER_FILTERS.forEach((f) => {
			if (this.filters[f.fieldname]) filters[f.fieldname] = this.filters[f.fieldname];
		});
		const like = `%${this.query}%`;
		this.$area.find(".btt-picker-status").text(__("Loading..."));

		const args = {
			doctype: "Classes",
			fields: ["name", "course_name", "course", "section", "group_name", "programme", "academic_term", "faculty_name"],
			filters,
			order_by: "modified desc",
			limit_page_length: this.limit + 1, // one extra tells whether there is more
		};
		// Only send or_filters when searching - an explicit null makes the server return nothing
		if (this.query) args.or_filters = [["name", "like", like], ["course_name", "like", like], ["course", "like", like]];

		frappe.call({
			method: "frappe.client.get_list",
			args,
			callback: (r) => {
				if (request_no !== this.request_no) return;
				const rows = r.message || [];
				this.has_more = rows.length > this.limit;
				this.rows = rows.slice(0, this.limit);
				this.render_list();
			},
			error: () => {
				if (request_no === this.request_no) this.$area.find(".btt-picker-status").text("");
			},
		});
	}

	render_list() {
		const esc = frappe.utils.escape_html;
		const $list = this.$area.find(".btt-picker-list");

		if (!this.rows.length) {
			$list.html(`<div class="btt-picker-empty">
				<div class="btt-empty-title">${__("No classes found")}</div>
				<div class="btt-empty-desc">${__("Try a different search or clear the filters.")}</div>
			</div>`);
		} else {
			$list.html(
				this.rows
					.map((c) => {
						const added = this.added.has(c.name);
						const checked = added || this.selected.has(c.name);
						const group = c.section || c.group_name || "";
						return `<label class="btt-pick-row ${added ? "is-added" : ""} ${checked && !added ? "is-checked" : ""}">
							<input type="checkbox" class="btt-pick-cb" data-name="${esc(c.name)}" ${checked ? "checked" : ""} ${added ? "disabled" : ""}>
							<div class="btt-pick-main">
								<div class="btt-pick-title">${esc(c.course_name || c.course || c.name)}</div>
								<div class="btt-pick-meta">
									<span class="btt-code-pill">${esc(c.name)}</span>
									${group ? `<span class="btt-section-badge">${c.section ? __("Sec") + " " : ""}${esc(group)}</span>` : ""}
									${c.programme ? `<span class="btt-pick-programme" title="${esc(c.programme)}">${esc(c.programme)}</span>` : ""}
								</div>
							</div>
							<div class="btt-pick-side">
								<div class="btt-pick-term">${esc(c.academic_term || "")}</div>
								<div class="btt-pick-faculty">${c.faculty_name ? esc(c.faculty_name) : `<span class="text-muted">${__("No faculty")}</span>`}</div>
							</div>
							${added ? `<span class="btt-pick-added">${__("Added")}</span>` : ""}
						</label>`;
					})
					.join("")
			);
		}

		this.$area.find(".btt-picker-more").html(
			this.has_more ? `<button type="button" class="btn btn-xs btt-outline-btn btt-picker-more-btn">${__("Load more")}</button>` : ""
		);
		this.$area.find(".btt-picker-status").text(
			this.rows.length ? __("{0} shown", [this.rows.length + (this.has_more ? "+" : "")]) : ""
		);
		this.sync_select_all();
	}

	selectable_rows() {
		return this.rows.filter((c) => !this.added.has(c.name));
	}

	toggle_row(name, checked) {
		const row = this.rows.find((c) => c.name === name);
		if (!row || this.added.has(name)) return;
		if (checked) this.selected.set(name, row);
		else this.selected.delete(name);
		this.$area.find(`.btt-pick-cb[data-name="${CSS.escape(name)}"]`).closest(".btt-pick-row").toggleClass("is-checked", checked);
		this.sync_select_all();
		this.update_footer();
	}

	toggle_all(checked) {
		this.selectable_rows().forEach((c) => (checked ? this.selected.set(c.name, c) : this.selected.delete(c.name)));
		this.render_list();
		this.update_footer();
	}

	sync_select_all() {
		const rows = this.selectable_rows();
		const picked = rows.filter((c) => this.selected.has(c.name)).length;
		const $all = this.$area.find(".btt-picker-all");
		$all.prop("disabled", !rows.length);
		$all.prop("checked", rows.length > 0 && picked === rows.length);
		$all.prop("indeterminate", picked > 0 && picked < rows.length);
	}

	update_footer() {
		const n = this.selected.size;
		this.$selected.html(
			n
				? `<span class="btt-summary-chip btt-chip-success"><b>${n}</b> ${n === 1 ? __("class selected") : __("classes selected")}</span>`
				: `<span class="btt-summary-text">${__("No classes selected")}</span>`
		);
		this.dialog.get_primary_btn()
			.html(n ? __("Add {0} {1}", [n, n === 1 ? __("Class") : __("Classes")]) : __("Add Classes"))
			.prop("disabled", !n)
			.toggleClass("disabled", !n);
	}

	submit() {
		if (!this.selected.size) return;
		this.on_add(Array.from(this.selected.keys()));
		this.dialog.hide();
	}
}

function bind_bulk_tt_progress() {
	if (frappe.flags.bulk_tt_progress_bound) return;
	frappe.flags.bulk_tt_progress_bound = true;
	frappe.realtime.on("time_table_bulk_progress", (data) => {
		const $msg = $("#freeze .freeze-message");
		if (!$msg.length || !data.total) return;
		const percent = Math.min(100, Math.max(0, cint(data.percent)));
		$msg.html(`
			<div class="lead mb-2" style="font-size:16px;font-weight:600;">${frappe.utils.escape_html(data.label || __("Creating Time Table"))}... ${percent}%</div>
			<div class="progress" style="height:8px;border-radius:4px;min-width:280px;background:rgba(255,255,255,0.2);">
				<div class="progress-bar" style="width:${percent}%;background:#10b981;border-radius:4px;transition:width 0.2s;"></div>
			</div>
			<div class="text-muted small mt-2">${__("{0} of {1} sessions created", [cint(data.done), cint(data.total)])}</div>
		`);
	});
}

function add_bulk_tt_style() {
	if (document.getElementById("btt-modern-style")) return;
	$(`<style id="btt-modern-style">
		/* NLSIU maroon brand, shared by the dialog and the class picker */
		.btt-dialog {
			--btt-brand: #7a1030;
			--btt-brand-hover: #651028;
			--btt-brand-active: #4f0b1f;
			--btt-brand-tint: #fbf1f4;
			--btt-brand-tint-border: #efcdd8;
			--btt-brand-text: #7a1030;
			--btt-brand-shadow: rgba(122, 16, 48, 0.25);
		}
		[data-theme="dark"] .btt-dialog {
			--btt-brand: #9c1f45;
			--btt-brand-hover: #b32853;
			--btt-brand-active: #7a1030;
			--btt-brand-tint: rgba(236, 130, 160, 0.10);
			--btt-brand-tint-border: rgba(236, 130, 160, 0.30);
			--btt-brand-text: #f2a7bc;
			--btt-brand-shadow: rgba(0, 0, 0, 0.4);
		}

		/* ==========================================================================
		   CUSTOM BUTTON: DARK THEME FOR "BULK TIME TABLE"
		   ========================================================================== */
		.btn.btt-dark-btn,
		button[data-label="Bulk%20Time%20Table"],
		button[data-label="Bulk Time Table"] {
			background-color: #0f172a !important;
			background: #0f172a !important;
			color: #ffffff !important;
			border: 1px solid #1e293b !important;
			border-radius: 8px !important;
			font-weight: 500 !important;
			font-size: 13px !important;
			padding: 5px 14px !important;
			display: inline-flex !important;
			align-items: center !important;
			gap: 6px !important;
			box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.18), 0 1px 2px -1px rgba(0, 0, 0, 0.1) !important;
			transition: all 0.15s ease-in-out !important;
			cursor: pointer !important;
		}

		.btn.btt-dark-btn:hover,
		button[data-label="Bulk%20Time%20Table"]:hover,
		button[data-label="Bulk Time Table"]:hover {
			background-color: #1e293b !important;
			background: #1e293b !important;
			border-color: #334155 !important;
			color: #ffffff !important;
			box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.25), 0 2px 4px -2px rgba(0, 0, 0, 0.15) !important;
			transform: translateY(-1px);
		}

		.btn.btt-dark-btn:active,
		button[data-label="Bulk%20Time%20Table"]:active,
		button[data-label="Bulk Time Table"]:active {
			background-color: #020617 !important;
			background: #020617 !important;
			transform: translateY(0);
		}

		.btn.btt-dark-btn svg,
		button[data-label="Bulk%20Time%20Table"] svg,
		button[data-label="Bulk Time Table"] svg {
			stroke: #ffffff !important;
			color: #ffffff !important;
		}

		/* Dark theme system compatibility */
		[data-theme="dark"] .btn.btt-dark-btn,
		[data-theme="dark"] button[data-label="Bulk%20Time%20Table"],
		[data-theme="dark"] button[data-label="Bulk Time Table"] {
			background-color: #18181b !important;
			background: #18181b !important;
			border-color: #3f3f46 !important;
			color: #f4f4f5 !important;
			box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.4) !important;
		}
		[data-theme="dark"] .btn.btt-dark-btn:hover,
		[data-theme="dark"] button[data-label="Bulk%20Time%20Table"]:hover,
		[data-theme="dark"] button[data-label="Bulk Time Table"]:hover {
			background-color: #27272a !important;
			background: #27272a !important;
			border-color: #52525b !important;
		}

		/* ==========================================================================
		   MODERN DIALOG SHELL & FULL-WIDTH LAYOUT
		   ========================================================================== */
		.btt-dialog .modal-dialog {
			max-width: 1040px !important;
			width: 95% !important;
			margin: 20px auto !important;
		}
		.btt-dialog .modal-content {
			border-radius: 16px !important;
			border: 1px solid var(--border-color, #e2e8f0) !important;
			box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.22) !important;
			background: var(--modal-bg, #ffffff) !important;
			overflow: hidden;
		}
		.btt-dialog .modal-header {
			display: none !important; /* Replaced by custom btt-header-panel */
		}
		.btt-dialog .modal-body {
			padding: 22px 28px !important;
			max-height: calc(88vh - 120px) !important;
			overflow-y: auto !important;
		}
		.btt-dialog .modal-footer {
			padding: 14px 28px !important;
			border-top: 1px solid var(--border-color, #e2e8f0) !important;
			background: var(--subtle-fg, #fafafa) !important;
			display: flex !important;
			align-items: center !important;
			justify-content: space-between !important;
		}

		/* Force Frappe sections to full width and zero unwanted margins */
		.btt-dialog .form-section {
			border-top: none !important;
			padding: 0 !important;
			margin: 0 !important;
			width: 100% !important;
			display: block !important;
		}
		.btt-dialog .form-section .section-body {
			padding: 0 !important;
			margin: 0 !important;
			width: 100% !important;
			display: block !important;
		}
		.btt-dialog .form-section .form-column {
			width: 100% !important;
			max-width: 100% !important;
			flex: 1 1 100% !important;
			padding: 0 !important;
			margin: 0 !important;
		}

		/* ==========================================================================
		   CUSTOM HEADER & STEPPER
		   ========================================================================== */
		.btt-header-panel {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding-bottom: 20px;
			margin-bottom: 22px;
			border-bottom: 1px solid var(--border-color, #e2e8f0);
			gap: 16px;
			flex-wrap: wrap;
		}
		.btt-header-info {
			display: flex;
			align-items: center;
			gap: 14px;
		}
		.btt-header-icon-box {
			width: 44px;
			height: 44px;
			border-radius: 12px;
			background: linear-gradient(135deg, var(--btt-brand) 0%, var(--btt-brand-active) 100%);
			color: #ffffff;
			display: flex;
			align-items: center;
			justify-content: center;
			box-shadow: 0 4px 6px -1px var(--btt-brand-shadow);
			flex-shrink: 0;
		}
		.btt-header-title-row {
			display: flex;
			align-items: center;
			gap: 10px;
		}
		.btt-title {
			font-size: 18px;
			font-weight: 700;
			color: var(--text-color, #0f172a);
			margin: 0;
			letter-spacing: -0.01em;
		}
		.btt-subtitle {
			font-size: 13px;
			color: var(--text-muted, #64748b);
			margin: 2px 0 0;
		}
		.btt-badge {
			display: inline-flex;
			align-items: center;
			font-size: 11px;
			font-weight: 600;
			padding: 2px 9px;
			border-radius: 12px;
			background: var(--control-bg, #f1f5f9);
			color: var(--text-muted, #64748b);
			border: 1px solid var(--border-color, #e2e8f0);
		}
		.btt-badge.has-items {
			background: var(--btt-brand-tint);
			color: var(--btt-brand-text);
			border-color: var(--btt-brand-tint-border);
		}

		/* Stepper Pills */
		.btt-stepper-pills {
			display: inline-flex;
			align-items: center;
			gap: 8px;
			background: var(--control-bg, #f8fafc);
			padding: 4px;
			border-radius: 10px;
			border: 1px solid var(--border-color, #e2e8f0);
		}
		.btt-step-pill {
			border: none;
			background: transparent;
			padding: 6px 14px;
			border-radius: 7px;
			font-size: 12px;
			font-weight: 500;
			color: var(--text-muted, #64748b);
			display: inline-flex;
			align-items: center;
			gap: 7px;
			cursor: pointer;
			transition: all 0.15s;
		}
		.btt-step-pill:hover:not(:disabled) {
			color: var(--text-color, #0f172a);
		}
		.btt-step-pill:disabled {
			opacity: 0.45;
			cursor: not-allowed;
		}
		.btt-step-pill.active {
			background: var(--card-bg, #ffffff);
			color: var(--text-color, #0f172a);
			font-weight: 600;
			box-shadow: 0 1px 3px rgba(0,0,0,0.08);
		}
		.btt-step-num {
			width: 18px;
			height: 18px;
			border-radius: 50%;
			background: var(--border-color, #e2e8f0);
			display: inline-flex;
			align-items: center;
			justify-content: center;
			font-size: 10px;
			font-weight: 700;
			color: var(--text-muted, #64748b);
		}
		.btt-step-pill.active .btt-step-num {
			background: var(--btt-brand);
			color: #ffffff;
		}
		.btt-step-pill.done .btt-step-num {
			background: var(--btt-brand-tint);
			color: var(--btt-brand-text);
			box-shadow: inset 0 0 0 1px var(--btt-brand-tint-border);
		}
		.btt-step-divider {
			width: 16px;
			height: 1px;
			background: var(--border-color, #e2e8f0);
		}
		.btt-step-divider.active {
			background: var(--btt-brand);
		}

		/* ==========================================================================
		   CARD SYSTEM (100% Full Width Containers)
		   ========================================================================== */
		.btt-card {
			background: var(--card-bg, #ffffff);
			border: 1px solid var(--border-color, #e2e8f0);
			border-radius: 12px;
			margin-bottom: 18px;
			overflow: visible; /* Link dropdowns (Faculty / Venue) must not be clipped */
			position: relative;
			box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04);
			width: 100% !important;
			display: block !important;
		}
		.btt-card-head {
			padding: 13px 18px;
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 12px;
			border-bottom: 1px solid var(--border-color, #f1f5f9);
			background: var(--card-subtle-bg, #ffffff);
			border-radius: 12px 12px 0 0;
		}
		[data-theme="dark"] .btt-card-head {
			background: var(--card-bg);
			border-bottom-color: var(--border-color);
		}
		.btt-card-head-left {
			display: flex;
			align-items: center;
			gap: 10px;
		}
		.btt-card-icon-pill {
			width: 30px;
			height: 30px;
			border-radius: 8px;
			background: var(--control-bg, #f1f5f9);
			color: var(--text-color, #0f172a);
			display: flex;
			align-items: center;
			justify-content: center;
			flex-shrink: 0;
		}
		.btt-card-title {
			font-size: 13.5px;
			font-weight: 600;
			color: var(--text-color, #0f172a);
			display: flex;
			align-items: center;
			gap: 6px;
		}
		.btt-card-desc {
			font-size: 12px;
			color: var(--text-muted, #64748b);
			margin-top: 1px;
		}
		.btt-count-chip {
			display: inline-block;
			padding: 1px 7px;
			border-radius: 10px;
			font-size: 11px;
			font-weight: 600;
			background: #f1f5f9;
			color: #334155;
		}
		[data-theme="dark"] .btt-count-chip {
			background: #27272a;
			color: #e4e4e7;
		}
		.btt-card-body {
			padding: 18px 20px;
		}
		.btt-card-foot-tip {
			padding: 9px 18px;
			background: var(--control-bg, #f8fafc);
			border-top: 1px solid var(--border-color, #f1f5f9);
			font-size: 11.5px;
			color: var(--text-muted, #64748b);
			display: flex;
			align-items: center;
			gap: 6px;
			border-radius: 0 0 12px 12px;
		}
		[data-theme="dark"] .btt-card-foot-tip {
			background: rgba(255,255,255,0.02);
			border-top-color: var(--border-color);
		}

		/* ==========================================================================
		   CLASSES TABLE & EMPTY STATE
		   ========================================================================== */
		.btt-table-wrap {
			border: 1px solid var(--border-color, #e2e8f0);
			border-radius: 10px;
			overflow: visible;
			width: 100%;
		}
		.btt-table-head {
			display: grid;
			grid-template-columns: minmax(280px, 2.5fr) minmax(200px, 1.5fr) minmax(200px, 1.5fr) 40px;
			gap: 14px;
			padding: 10px 16px;
			background: var(--control-bg, #f8fafc);
			font-size: 11px;
			font-weight: 600;
			letter-spacing: 0.04em;
			text-transform: uppercase;
			color: var(--text-muted, #64748b);
			border-bottom: 1px solid var(--border-color, #e2e8f0);
			align-items: center;
			border-radius: 10px 10px 0 0;
		}
		/* The card / row holding an open dropdown sits above its neighbours */
		.btt-card:focus-within { z-index: 3; }
		.btt-table-row:focus-within { position: relative; z-index: 2; }
		.btt-dialog .awesomplete > [role="listbox"] {
			z-index: 1080 !important;
			max-height: 248px;
			overflow-y: auto;
			min-width: 100%;
			border-radius: 10px;
			border: 1px solid var(--border-color, #e2e8f0);
			box-shadow: 0 12px 28px -6px rgba(15, 23, 42, 0.22);
		}
		.btt-table-rows {
			display: flex;
			flex-direction: column;
		}
		.btt-table-row {
			display: grid;
			grid-template-columns: minmax(280px, 2.5fr) minmax(200px, 1.5fr) minmax(200px, 1.5fr) 40px;
			gap: 14px;
			align-items: center;
			padding: 10px 16px;
			border-top: 1px solid var(--border-color, #f1f5f9);
			transition: background 0.1s;
		}
		.btt-table-row:first-child {
			border-top: none;
		}
		.btt-table-row:hover {
			background: var(--control-bg, #fbfcfd);
		}
		[data-theme="dark"] .btt-table-row:hover {
			background: rgba(255,255,255,0.02);
		}
		.btt-class-course-title {
			font-size: 13.5px;
			font-weight: 600;
			color: var(--text-color, #0f172a);
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}
		.btt-class-meta-row {
			display: flex;
			align-items: center;
			gap: 6px;
			margin-top: 3px;
		}
		.btt-code-pill {
			font-family: SFMono-Regular, Menlo, Monaco, Consolas, monospace;
			font-size: 11px;
			background: var(--control-bg, #f1f5f9);
			color: var(--text-muted, #475569);
			padding: 1px 6px;
			border-radius: 4px;
			border: 1px solid var(--border-color, #e2e8f0);
		}
		.btt-section-badge {
			font-size: 10.5px;
			font-weight: 600;
			padding: 1px 7px;
			border-radius: 10px;
			background: var(--btt-brand-tint);
			color: var(--btt-brand-text);
		}
		.btt-col-faculty .form-group,
		.btt-col-venue .form-group,
		.btt-slot-venue-wrap .form-group {
			margin: 0 !important;
		}
		.btt-col-faculty input,
		.btt-col-venue input,
		.btt-slot-venue-wrap input {
			height: 34px !important;
			border-radius: 7px !important;
			font-size: 12.5px !important;
		}

		.btt-empty-state {
			text-align: center;
			padding: 36px 16px;
			border: 1.5px dashed var(--border-color, #e2e8f0);
			border-radius: 10px;
			background: var(--control-bg, #fafafa);
		}
		[data-theme="dark"] .btt-empty-state {
			background: rgba(255,255,255,0.01);
		}
		.btt-empty-icon-wrap {
			width: 52px;
			height: 52px;
			border-radius: 50%;
			background: var(--card-bg, #ffffff);
			border: 1px solid var(--border-color, #e2e8f0);
			display: inline-flex;
			align-items: center;
			justify-content: center;
			color: var(--text-muted, #64748b);
			margin-bottom: 12px;
			box-shadow: 0 1px 3px rgba(0,0,0,0.04);
		}
		.btt-empty-title {
			font-size: 14px;
			font-weight: 600;
			color: var(--text-color, #0f172a);
		}
		.btt-empty-desc {
			font-size: 12.5px;
			color: var(--text-muted, #64748b);
			max-width: 440px;
			margin: 4px auto 0;
			line-height: 1.45;
		}

		/* ==========================================================================
		   DATE & RECURRENCE 3-COLUMN GRID
		   ========================================================================== */
		.btt-dates-grid {
			display: grid;
			grid-template-columns: repeat(3, minmax(0, 1fr));
			gap: 20px;
			align-items: flex-start;
			width: 100%;
		}
		.btt-field-col {
			display: flex;
			flex-direction: column;
		}
		.btt-field-label {
			display: block;
			font-size: 12px;
			font-weight: 600;
			color: var(--text-color, #0f172a);
			margin-bottom: 6px;
		}
		.btt-field-input .form-group {
			margin: 0 !important;
		}
		.btt-field-input input,
		.btt-field-input select {
			height: 34px !important;
			border-radius: 7px !important;
			font-size: 12.5px !important;
			width: 100% !important;
		}
		.btt-field-help {
			font-size: 11.5px;
			color: var(--text-muted, #64748b);
			margin-top: 4px;
		}

		/* ==========================================================================
		   SLOTS & DAY SELECTOR
		   ========================================================================== */
		.btt-day-chips-bar {
			display: flex;
			align-items: center;
			gap: 14px;
			margin-bottom: 16px;
			flex-wrap: wrap;
		}
		.btt-day-chips-label {
			font-size: 12px;
			font-weight: 600;
			color: var(--text-muted, #64748b);
		}
		.btt-day-chips-group {
			display: inline-flex;
			background: var(--control-bg, #f1f5f9);
			border: 1px solid var(--border-color, #e2e8f0);
			border-radius: 9px;
			padding: 3px;
			gap: 3px;
			flex-wrap: wrap;
		}
		.btt-day-chip {
			border: none;
			background: transparent;
			padding: 6px 14px;
			border-radius: 6px;
			font-size: 12px;
			font-weight: 500;
			color: var(--text-muted, #475569);
			display: inline-flex;
			align-items: center;
			gap: 6px;
			cursor: pointer;
			transition: all 0.15s;
		}
		.btt-day-chip:hover:not(.disabled) {
			color: var(--text-color, #0f172a);
			background: rgba(255,255,255,0.7);
		}
		.btt-day-chip.active {
			background: var(--btt-brand);
			color: #ffffff;
			font-weight: 600;
			box-shadow: 0 1px 3px var(--btt-brand-shadow);
		}
		.btt-day-chip.disabled {
			opacity: 0.4;
			cursor: not-allowed;
			text-decoration: line-through;
		}
		.btt-chip-dot {
			width: 5px;
			height: 5px;
			border-radius: 50%;
			background: currentColor;
			opacity: 0.6;
		}

		.btt-days-container {
			display: flex;
			flex-direction: column;
			gap: 12px;
			width: 100%;
		}
		.btt-day-card {
			background: var(--card-bg, #ffffff);
			border: 1px solid var(--border-color, #e2e8f0);
			border-radius: 10px;
			padding: 13px 16px;
			width: 100%;
		}
		.btt-day-card-head {
			display: flex;
			align-items: center;
			justify-content: space-between;
			margin-bottom: 11px;
		}
		.btt-day-title-pill {
			display: inline-flex;
			align-items: center;
			gap: 7px;
			font-size: 13px;
			font-weight: 600;
			color: var(--text-color, #0f172a);
		}
		.btt-day-dot {
			width: 8px;
			height: 8px;
			border-radius: 50%;
			background: var(--btt-brand);
		}
		.btt-day-card-actions {
			display: flex;
			align-items: center;
			gap: 12px;
		}
		.btt-day-slots-list {
			display: flex;
			flex-direction: column;
			gap: 8px;
			width: 100%;
		}
		.btt-slot-item {
			display: flex;
			align-items: center;
			gap: 12px;
			flex-wrap: wrap;
		}
		.btt-slot-time-group {
			display: inline-flex;
			align-items: center;
			gap: 8px;
		}
		.btt-time-input-wrap {
			position: relative;
			display: inline-flex;
			align-items: center;
		}
		.btt-time-icon {
			position: absolute;
			left: 9px;
			color: var(--text-muted, #94a3b8);
			pointer-events: none;
		}
		.btt-time-input {
			height: 33px;
			width: 140px; /* fits "09:00 AM" next to both clock icons */
			padding: 4px 8px 4px 28px;
			border: 1px solid var(--border-color, #cbd5e1);
			border-radius: 7px;
			font-size: 12.5px;
			background: var(--control-bg, #ffffff);
			color: var(--text-color, #0f172a);
			transition: border-color 0.15s, box-shadow 0.15s;
		}
		.btt-time-input:focus {
			outline: none;
			border-color: var(--btt-brand);
			box-shadow: 0 0 0 2px var(--btt-brand-tint-border);
		}
		.btt-slot-arrow {
			color: var(--text-muted, #94a3b8);
			font-size: 13px;
			font-weight: 600;
		}
		.btt-duration-badge {
			display: inline-block;
			padding: 3px 8px;
			border-radius: 6px;
			font-size: 11px;
			font-weight: 600;
			background: var(--control-bg, #f1f5f9);
			color: var(--text-muted, #475569);
			border: 1px solid var(--border-color, #e2e8f0);
			min-width: 48px;
			text-align: center;
		}
		.btt-slot-venue-wrap {
			width: 220px;
		}
		.btt-empty-day-state {
			display: flex;
			align-items: center;
			justify-content: center;
			gap: 10px;
			padding: 24px;
			border: 1px dashed var(--border-color, #e2e8f0);
			border-radius: 9px;
			color: var(--text-muted, #64748b);
			font-size: 13px;
		}

		/* ==========================================================================
		   SWITCH / TOGGLES
		   ========================================================================== */
		.btt-toggle-switch-wrap {
			display: inline-flex;
			align-items: center;
			gap: 8px;
			margin: 0;
			cursor: pointer;
			user-select: none;
		}
		.btt-toggle-input {
			display: none;
		}
		.btt-toggle-track {
			position: relative;
			width: 32px;
			height: 18px;
			border-radius: 10px;
			background: var(--gray-400, #cbd5e1);
			transition: background 0.15s ease-in-out;
			display: inline-block;
			flex-shrink: 0;
		}
		.btt-toggle-track::after {
			content: "";
			position: absolute;
			top: 2px;
			left: 2px;
			width: 14px;
			height: 14px;
			border-radius: 50%;
			background: #ffffff;
			box-shadow: 0 1px 2px rgba(0,0,0,0.2);
			transition: transform 0.15s ease-in-out;
		}
		.btt-toggle-input:checked + .btt-toggle-track {
			background: var(--btt-brand);
		}
		.btt-toggle-input:checked + .btt-toggle-track::after {
			transform: translateX(14px);
		}
		.btt-toggle-label {
			font-size: 12.5px;
			font-weight: 500;
			color: var(--text-color, #0f172a);
		}

		/* ==========================================================================
		   EXCLUSIONS ("SKIP") 3-COLUMN GRID
		   ========================================================================== */
		.btt-skip-grid {
			display: grid;
			grid-template-columns: repeat(3, minmax(0, 1fr));
			gap: 16px;
			width: 100%;
		}
		.btt-skip-card {
			display: flex;
			gap: 12px;
			align-items: flex-start;
			padding: 14px 16px;
			border: 1px solid var(--border-color, #e2e8f0);
			border-radius: 10px;
			background: var(--card-bg, #ffffff);
			cursor: pointer;
			transition: all 0.15s;
		}
		.btt-skip-card:hover {
			border-color: #cbd5e1;
		}
		.btt-skip-card.checked {
			border-color: var(--btt-brand);
			background: var(--btt-brand-tint);
		}
		.btt-skip-icon-wrap {
			width: 32px;
			height: 32px;
			border-radius: 8px;
			background: var(--control-bg, #f1f5f9);
			color: var(--text-color, #0f172a);
			display: flex;
			align-items: center;
			justify-content: center;
			flex-shrink: 0;
			margin-top: 1px;
		}
		.btt-skip-body {
			flex: 1;
			min-width: 0;
		}
		.btt-skip-title-row {
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 8px;
		}
		.btt-skip-title {
			font-size: 13px;
			font-weight: 600;
			color: var(--text-color, #0f172a);
		}
		.btt-skip-help {
			font-size: 11.5px;
			color: var(--text-muted, #64748b);
			margin-top: 4px;
			line-height: 1.4;
		}

		/* ==========================================================================
		   REVIEW & PREVIEW VIEW
		   ========================================================================== */
		.btt-review-overview-card {
			background: var(--control-bg, #f8fafc);
			border: 1px solid var(--border-color, #e2e8f0);
			border-radius: 12px;
			padding: 18px 20px;
			margin-bottom: 16px;
			width: 100%;
		}
		.btt-overview-head {
			display: flex;
			align-items: flex-start;
			justify-content: space-between;
			gap: 16px;
			margin-bottom: 18px;
			flex-wrap: wrap;
		}
		.btt-overview-title {
			font-size: 16px;
			font-weight: 700;
			color: var(--text-color, #0f172a);
		}
		.btt-overview-range {
			font-size: 13px;
			color: var(--text-muted, #64748b);
			margin-top: 2px;
		}
		.btt-overview-slots {
			display: flex;
			gap: 6px;
			flex-wrap: wrap;
		}
		.btt-meta-pill {
			display: inline-block;
			padding: 3px 10px;
			border-radius: 6px;
			font-size: 12px;
			background: var(--card-bg, #ffffff);
			border: 1px solid var(--border-color, #e2e8f0);
			color: var(--text-color, #0f172a);
		}

		.btt-stats-grid {
			display: grid;
			grid-template-columns: repeat(4, minmax(0, 1fr));
			gap: 12px;
		}
		.btt-stat-card {
			background: var(--card-bg, #ffffff);
			border: 1px solid var(--border-color, #e2e8f0);
			border-radius: 10px;
			padding: 12px 16px;
			box-shadow: 0 1px 2px rgba(0,0,0,0.03);
		}
		.btt-stat-num {
			font-size: 26px;
			font-weight: 800;
			line-height: 1.1;
			color: var(--text-color, #0f172a);
		}
		.btt-stat-label {
			font-size: 12px;
			color: var(--text-muted, #64748b);
			margin-top: 4px;
		}
		.btt-stat-card.primary {
			background: linear-gradient(135deg, var(--btt-brand) 0%, var(--btt-brand-active) 100%);
			border-color: var(--btt-brand);
		}
		.btt-stat-card.primary .btt-stat-num {
			color: #ffffff;
		}
		.btt-stat-card.primary .btt-stat-label {
			color: rgba(255, 255, 255, 0.75);
		}
		.btt-stat-card.warning .btt-stat-num {
			color: #d97706;
		}

		.btt-alert {
			display: flex;
			align-items: center;
			gap: 10px;
			padding: 10px 14px;
			border-radius: 8px;
			font-size: 12.5px;
			margin-top: 14px;
			line-height: 1.4;
		}
		.btt-alert.warning {
			background: #fffbeb;
			color: #92400e;
			border: 1px solid #fde68a;
		}
		[data-theme="dark"] .btt-alert.warning {
			background: rgba(217, 119, 6, 0.15);
			color: #fbbf24;
			border-color: rgba(251, 191, 36, 0.3);
		}
		.btt-alert.danger {
			background: #fef2f2;
			color: #991b1b;
			border: 1px solid #fecaca;
		}
		[data-theme="dark"] .btt-alert.danger {
			background: rgba(239, 68, 68, 0.15);
			color: #f87171;
			border-color: rgba(248, 113, 113, 0.3);
		}

		/* Data table in Preview */
		.btt-data-table {
			width: 100%;
			font-size: 12.5px;
			border-collapse: collapse;
		}
		.btt-data-table th {
			font-size: 11px;
			font-weight: 600;
			letter-spacing: 0.04em;
			text-transform: uppercase;
			color: var(--text-muted, #64748b);
			padding: 9px 14px;
			background: var(--control-bg, #f8fafc);
			border-bottom: 1px solid var(--border-color, #e2e8f0);
			position: sticky;
			top: 0;
			z-index: 1;
		}
		.btt-data-table td {
			padding: 10px 14px;
			border-top: 1px solid var(--border-color, #f1f5f9);
			vertical-align: top;
		}
		.btt-data-table tbody tr:first-child td {
			border-top: none;
		}
		.btt-stat-badge {
			display: inline-block;
			padding: 2px 7px;
			border-radius: 6px;
			font-size: 11px;
			font-weight: 600;
		}
		.btt-stat-badge.success {
			background: #ecfdf5;
			color: #059669;
		}
		.btt-stat-badge.warning {
			background: #fffbeb;
			color: #d97706;
		}
		.btt-stat-badge.muted {
			background: #f1f5f9;
			color: #64748b;
		}
		[data-theme="dark"] .btt-stat-badge.success {
			background: rgba(16, 185, 129, 0.2);
			color: #34d399;
		}

		.btt-filter-tabs {
			display: inline-flex;
			background: var(--control-bg, #f1f5f9);
			border: 1px solid var(--border-color, #e2e8f0);
			border-radius: 7px;
			padding: 2px;
			gap: 2px;
		}
		.btt-filter-pill {
			border: none;
			background: transparent;
			padding: 3px 9px;
			font-size: 11.5px;
			border-radius: 5px;
			color: var(--text-muted, #64748b);
			cursor: pointer;
		}
		.btt-filter-pill span {
			opacity: 0.75;
			margin-left: 2px;
		}
		.btt-filter-pill.active {
			background: var(--card-bg, #ffffff);
			color: var(--text-color, #0f172a);
			font-weight: 600;
			box-shadow: 0 1px 2px rgba(0,0,0,0.06);
		}
		.btt-session-table-scroll {
			max-height: 320px;
			overflow-y: auto;
		}
		.btt-status-tag {
			display: inline-flex;
			align-items: center;
			gap: 4px;
			padding: 2px 8px;
			border-radius: 6px;
			font-size: 11px;
			font-weight: 600;
			white-space: nowrap;
		}
		.btt-status-tag.success {
			background: #ecfdf5;
			color: #059669;
		}
		.btt-status-tag.warning {
			background: #fffbeb;
			color: #d97706;
		}
		.btt-status-tag.muted {
			background: #f1f5f9;
			color: #64748b;
		}
		[data-theme="dark"] .btt-status-tag.success {
			background: rgba(16, 185, 129, 0.2);
			color: #34d399;
		}
		.btt-note-cell {
			font-size: 12px;
			color: var(--text-muted, #64748b);
			line-height: 1.4;
		}

		/* ==========================================================================
		   BUTTONS & FOOTER CONTROLS
		   ========================================================================== */
		.btt-primary-btn {
			background: var(--btt-brand) !important;
			color: #ffffff !important;
			border: 1px solid var(--btt-brand) !important;
			border-radius: 8px !important;
			font-weight: 500 !important;
			box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
		}
		.btt-primary-btn:hover:not(:disabled) {
			background: var(--btt-brand-hover) !important;
			border-color: var(--btt-brand-hover) !important;
		}
		.btt-outline-btn {
			background: var(--card-bg, #ffffff) !important;
			color: var(--text-color, #0f172a) !important;
			border: 1px solid var(--border-color, #cbd5e1) !important;
			border-radius: 7px !important;
			font-weight: 500 !important;
			font-size: 12px !important;
			padding: 4px 10px !important;
		}
		.btt-outline-btn:hover {
			background: var(--control-bg, #f8fafc) !important;
		}
		.btt-link-btn {
			background: transparent !important;
			border: none !important;
			color: var(--btt-brand-text) !important;
			font-size: 12px !important;
			font-weight: 500 !important;
			display: inline-flex !important;
			align-items: center !important;
			gap: 4px !important;
			padding: 2px 6px !important;
		}
		.btt-link-btn:hover {
			text-decoration: underline !important;
		}
		.btt-icon-btn {
			background: transparent;
			border: none;
			color: var(--text-muted, #94a3b8);
			padding: 5px;
			border-radius: 6px;
			display: inline-flex;
			align-items: center;
			justify-content: center;
			cursor: pointer;
			transition: all 0.15s;
		}
		.btt-icon-btn:hover:not(:disabled) {
			background: #fee2e2;
			color: #dc2626;
		}
		[data-theme="dark"] .btt-icon-btn:hover:not(:disabled) {
			background: rgba(220, 38, 38, 0.2);
			color: #f87171;
		}
		.btt-icon-btn:disabled {
			opacity: 0.3;
			cursor: not-allowed;
		}

		/* Modal footer summary */
		.btt-footer-summary {
			font-size: 12.5px;
			color: var(--text-muted, #64748b);
			display: flex;
			align-items: center;
			gap: 8px;
		}
		.btt-summary-chip {
			display: inline-block;
			padding: 2px 8px;
			border-radius: 6px;
			font-size: 11.5px;
		}
		.btt-summary-chip.btt-chip-success {
			background: #ecfdf5;
			color: #059669;
		}
		[data-theme="dark"] .btt-summary-chip.btt-chip-success {
			background: rgba(16, 185, 129, 0.14);
			color: #6ee7b7;
		}
		[data-theme="dark"] .btt-summary-chip.btt-chip-warning {
			background: rgba(217, 119, 6, 0.16);
			color: #fcd34d;
		}
		.btt-summary-chip.btt-chip-warning {
			background: #fffbeb;
			color: #d97706;
		}
		.btt-summary-chip.btt-chip-muted {
			background: #f1f5f9;
			color: #64748b;
		}

		/* Dialog Primary Button */
		.btt-dialog .btn-primary {
			background-color: var(--btt-brand) !important;
			background: var(--btt-brand) !important;
			border-color: var(--btt-brand) !important;
			color: #ffffff !important;
			border-radius: 8px !important;
			font-weight: 500 !important;
			padding: 6px 16px !important;
			box-shadow: 0 1px 2px rgba(0,0,0,0.12) !important;
			display: inline-flex !important;
			align-items: center !important;
		}
		.btt-dialog .btn-primary:hover:not(:disabled) {
			background-color: var(--btt-brand-hover) !important;
			background: var(--btt-brand-hover) !important;
			border-color: var(--btt-brand-hover) !important;
		}
		.btt-dialog .btn-primary:active:not(:disabled) {
			background-color: var(--btt-brand-active) !important;
			background: var(--btt-brand-active) !important;
		}

		/* ==========================================================================
		   CLASS PICKER
		   ========================================================================== */
		.btt-picker .modal-dialog { max-width: 880px !important; }
		.btt-picker .modal-body { padding: 20px 24px 12px !important; }
		.btt-picker-head {
			display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
			padding-bottom: 16px; margin-bottom: 16px; border-bottom: 1px solid var(--border-color, #e2e8f0);
		}
		.btt-picker-filters {
			display: grid; grid-template-columns: minmax(0, 1.6fr) repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px;
		}
		.btt-picker-filter .form-group { margin: 0 !important; }
		.btt-picker-filter input, .btt-picker-search input { height: 36px !important; border-radius: 8px !important; font-size: 13px !important; }
		.btt-picker-search { position: relative; }
		.btt-picker-search svg { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); color: var(--text-muted, #64748b); pointer-events: none; z-index: 2; }
		.btt-picker-search input { padding-left: 32px !important; }
		.btt-picker-search input:focus { border-color: var(--btt-brand) !important; box-shadow: 0 0 0 2px var(--btt-brand-tint-border) !important; }
		.btt-picker-toolbar {
			display: flex; align-items: center; gap: 12px; padding: 8px 2px; font-size: 12.5px; color: var(--text-muted, #64748b);
		}
		.btt-picker-all-label { display: inline-flex; align-items: center; gap: 8px; margin: 0; cursor: pointer; color: var(--text-color, #0f172a); font-weight: 500; }
		.btt-picker-status { margin-left: auto; }
		.btt-picker .btt-pick-cb, .btt-picker .btt-picker-all { width: 16px; height: 16px; margin: 0; accent-color: var(--btt-brand); cursor: pointer; }
		.btt-picker input[type="checkbox"]:checked { background-color: var(--btt-brand); border-color: var(--btt-brand); }
		.btt-picker-list {
			border: 1px solid var(--border-color, #e2e8f0); border-radius: 12px; max-height: 46vh; overflow-y: auto;
			background: var(--card-bg, #ffffff);
		}
		.btt-pick-row {
			display: grid; grid-template-columns: 18px minmax(0, 1fr) minmax(0, 220px) auto; gap: 14px; align-items: center;
			padding: 12px 16px; margin: 0; cursor: pointer; font-weight: normal;
			border-top: 1px solid var(--border-color, #f1f5f9); transition: background 0.1s;
		}
		.btt-pick-row:first-child { border-top: none; }
		.btt-pick-row:hover { background: var(--control-bg, #f8fafc); }
		.btt-pick-row.is-checked { background: var(--btt-brand-tint); box-shadow: inset 3px 0 0 var(--btt-brand); }
		.btt-pick-row.is-added { cursor: default; opacity: 0.65; }
		.btt-pick-row.is-added:hover { background: transparent; }
		.btt-pick-title { font-weight: 600; font-size: 13.5px; color: var(--text-color, #0f172a); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
		.btt-pick-meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; min-width: 0; flex-wrap: wrap; }
		.btt-pick-programme { font-size: 12px; color: var(--text-muted, #64748b); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 320px; }
		.btt-pick-side { text-align: right; min-width: 0; }
		.btt-pick-term { font-size: 12px; font-weight: 500; color: var(--text-color, #0f172a); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.btt-pick-faculty { font-size: 12px; color: var(--text-muted, #64748b); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.btt-pick-added {
			font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px;
			background: var(--control-bg, #f1f5f9); color: var(--text-muted, #64748b);
		}
		.btt-picker-empty { padding: 40px 16px; text-align: center; }
		.btt-picker-more { text-align: center; padding: 10px 0 2px; }
		.btt-picker-more:empty { display: none; }
		@media (max-width: 768px) {
			.btt-picker-filters { grid-template-columns: 1fr 1fr; }
			.btt-picker-search { grid-column: 1 / -1; }
			.btt-pick-row { grid-template-columns: 18px minmax(0, 1fr) auto; }
			.btt-pick-side { display: none; }
		}

		@keyframes btt-spin {
			from { transform: rotate(0deg); }
			to { transform: rotate(360deg); }
		}
		.btt-spin {
			animation: btt-spin 1s linear infinite;
		}

		/* Responsive */
		@media (max-width: 820px) {
			.btt-table-head { display: none; }
			.btt-table-row { grid-template-columns: 1fr 36px; }
			.btt-table-row .btt-col-faculty,
			.btt-table-row .btt-col-venue { grid-column: 1 / 2; }
			.btt-dates-grid, .btt-skip-grid, .btt-stats-grid { grid-template-columns: 1fr; }
			.btt-header-panel { flex-direction: column; align-items: flex-start; }
			.btt-stepper-pills { width: 100%; justify-content: space-between; }
		}
	</style>`).appendTo("head");
}
