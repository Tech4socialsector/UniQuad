// Fee Certificates
//   /desk/fee-certificates → every generated certificate (campus students and applicants)
// Generate one, bulk generate for many campus students, preview / download / upload an
// edited copy per row, and download many at once as a ZIP.
// Opening with frappe.route_options = { generate_for: <student> } opens the Generate dialog for them.
// Helpers, icons, the multi-select and the styles come from /assets/slcm/js/sfm_common.js.

const FC_PAGE = "fee-certificates";
const FC_API = "slcm.slcm.page.fee_certificates.fee_certificates.";
const FC_PAGE_SIZES = [10, 25, 50, 100];
// Students sent per bulk-generate request, so the progress bar moves and no request runs long.
const FC_GENERATE_BATCH = 10;

frappe.pages[FC_PAGE].on_page_load = function (wrapper) {
	frappe.require("/assets/slcm/js/sfm_common.js", () => {
		wrapper.fee_certificates = new FeeCertificates(wrapper);
		wrapper.fee_certificates.show();
	});
};

frappe.pages[FC_PAGE].on_page_show = function (wrapper) {
	wrapper.fee_certificates && wrapper.fee_certificates.show();
};

const fc_empty_filters = () => ({ academic_year: [], programme: [], certificate_for: [], purpose: [], search: "" });

class FeeCertificates {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Fee Certificates"), single_column: true });
		let page_length = 25;
		try {
			page_length = cint(localStorage.getItem("fc_page_length")) || 25;
		} catch (e) {
			// storage blocked — fall back to the default
		}
		this.state = { start: 0, page_length: FC_PAGE_SIZES.includes(page_length) ? page_length : 25 };
		this.filters = fc_empty_filters();
		// Filter edits collect here and only reach this.filters (and the server) when Search is pressed.
		this.draft = fc_empty_filters();
		this.selected = new Set();
		this.certificate_rows = [];
		this.total = 0;
		this.req = 0;
		this.ms = {};

		sfm_load_font();
		sfm_inject_styles();
		$(wrapper).addClass("sfm-page");
		this.$root = $(`<div class="sfm"></div>`).appendTo(this.page.main);
		this.render_shell();
		this.bind_realtime();
	}

	async options() {
		if (!this.fc_options) {
			const r = await frappe.call({ method: FC_API + "get_fee_certificate_options" });
			this.fc_options = r.message || { purposes: [], academic_years: [], programmes: [], batches: [], terms: [], student_years: [] };
		}
		return this.fc_options;
	}

	show() {
		this.load();
		const ro = frappe.route_options;
		if (ro && ro.generate_for) {
			frappe.route_options = null;
			this.fee_certificate_dialog({ student: ro.generate_for, academic_year: ro.academic_year });
		}
	}

	render_shell() {
		this.$root.html(`
			<div class="sfm-shell">
				<button type="button" class="sfm-btn sfm-btn-secondary sfm-btn-sm sfm-back-btn" data-act="back">
					${sfm_icon("arrow-left", 14)}<span>${__("Back")}</span>
				</button>
				<header class="sfm-head">
					<div>
						<h1 class="sfm-title">${__("Fee Certificates")}</h1>
						<p class="sfm-subtitle">${__("Generate fee certificates one at a time or in bulk, and download them together as a ZIP")}</p>
					</div>
					<div class="sfm-actions">
						<button type="button" class="sfm-btn sfm-btn-secondary" data-act="refresh">
							${sfm_icon("refresh", 15)}<span>${__("Refresh")}</span>
						</button>
						<button type="button" class="sfm-btn sfm-btn-secondary" data-act="bulk-generate">
							${sfm_icon("users", 15)}<span>${__("Bulk Generate")}</span>
						</button>
						<button type="button" class="sfm-btn sfm-btn-primary" data-act="generate">
							${sfm_icon("plus", 15)}<span>${__("Generate Certificate")}</span>
						</button>
					</div>
				</header>

				<section class="sfm-panel sfm-filter-panel" aria-labelledby="fc-filter-title">
					<div class="sfm-panel-head">
						<h2 id="fc-filter-title" class="sfm-panel-title">${sfm_icon("filter", 15)}${__("Filter & Search")}</h2>
						<button type="button" class="sfm-btn sfm-btn-ghost sfm-btn-sm" data-act="clear">
							${sfm_icon("x", 14)}<span>${__("Clear filters")}</span>
						</button>
					</div>
					<div class="sfm-filter-grid sfr-filter-grid">
						<div class="sfm-field" data-ms-key="academic_year"></div>
						<div class="sfm-field" data-ms-key="programme"></div>
						<div class="sfm-field" data-ms-key="certificate_for"></div>
						<div class="sfm-field" data-ms-key="purpose"></div>
						<div class="sfm-field sfc-search-field">
							<label for="fc-f-search">${__("Search")}</label>
							<div class="sfm-search-wrap">
								${sfm_icon("search", 15, "sfm-search-icon")}
								<input id="fc-f-search" type="search" class="sfm-control" data-f="search"
									placeholder="${__("Certificate no., student / applicant name, ID…")}" autocomplete="off">
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
							<h2 class="sfm-panel-title">${__("Generated Certificates")}</h2>
							<div class="sfm-muted sfm-report-caption" aria-live="polite"></div>
						</div>
						<div class="sfm-report-tools">
							<span class="sfm-muted sfc-selected" aria-live="polite"></span>
							<button type="button" class="sfm-btn sfm-btn-ghost sfm-btn-sm" data-act="clear-selection" hidden>
								${sfm_icon("x", 14)}<span>${__("Clear selection")}</span>
							</button>
							<div class="sfm-page-size">
								<label for="fc-page-size">${__("Rows per page")}</label>
								<div class="sfm-select-wrap">
									<select id="fc-page-size" class="sfm-control sfm-control-sm">
										${FC_PAGE_SIZES.map((n) => `<option value="${n}">${n}</option>`).join("")}
									</select>
									${sfm_icon("chevron-down", 14, "sfm-select-caret")}
								</div>
							</div>
							<button type="button" class="sfm-btn sfm-btn-primary sfm-btn-sm" data-act="bulk-download">
								${sfm_icon("download", 14)}<span class="sfc-bulk-label">${__("Download All (ZIP)")}</span>
							</button>
						</div>
					</div>
					<div class="sfm-table-scroll">
						<table class="sfm-table sfm-report-table sfc-table"><thead></thead><tbody></tbody></table>
					</div>
					<footer class="sfm-pager" data-pager="report"></footer>
				</section>
			</div>
		`);
		this.$root.find("#fc-page-size").val(this.state.page_length);
		this.build_filters();
		this.bind_events();
		this.options().then(() => this.render_filter_options());
	}

	// ── Filters ──────────────────────────────────────────────────────────
	build_filters() {
		const make = (key, label, all_label, searchable = false) =>
			new SfmMultiSelect(this.$root.find(`[data-ms-key="${key}"]`), {
				key: `fc-${key}`,
				label,
				all_label,
				searchable,
				on_change: (value) => {
					this.draft[key] = value;
					this.update_dirty();
				},
			});
		this.ms = {
			academic_year: make("academic_year", __("Academic Year"), __("All Years")),
			programme: make("programme", __("Programme"), __("All Programmes"), true),
			certificate_for: make("certificate_for", __("Certificate For"), __("Students & Applicants")),
			purpose: make("purpose", __("Purpose"), __("All Purposes"), true),
		};
		this.ms.certificate_for.set_options(
			[
				{ value: "Campus Student", label: __("Campus Student") },
				{ value: "Admission Stage", label: __("Applicant (Admission Stage)") },
			],
			[]
		);
		$(document)
			.off("mousedown.fc-ms")
			.on("mousedown.fc-ms", (e) => {
				if (!$(e.target).closest(".sfm-ms").length) Object.values(this.ms).forEach((m) => m.close());
			});
	}

	render_filter_options() {
		const o = this.fc_options;
		const d = this.draft;
		this.ms.academic_year.set_options(o.academic_years.map((y) => ({ value: y, label: y })), d.academic_year);
		this.ms.programme.set_options(
			o.programmes.map((p) => ({
				value: p.name,
				label: p.program_name && p.program_name !== p.name ? `${p.name} — ${p.program_name}` : p.name,
			})),
			d.programme
		);
		this.ms.purpose.set_options(o.purposes.map((p) => ({ value: p.purpose, label: p.purpose })), d.purpose);
	}

	apply_filters() {
		Object.values(this.ms).forEach((m) => m.close());
		this.filters = JSON.parse(JSON.stringify({ ...this.draft, search: (this.draft.search || "").trim() }));
		this.update_dirty();
		this.reload();
	}

	clear_filters() {
		this.filters = fc_empty_filters();
		this.draft = fc_empty_filters();
		Object.values(this.ms).forEach((m) => m.set_options(m.options, []));
		this.$root.find("input[data-f]").val("");
		this.update_dirty();
		this.reload();
	}

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
		$r.on("input", "input[data-f]", (e) => {
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
		$r.on("click", '[data-act="refresh"]', () => {
			this.fc_options = null;
			this.options().then(() => this.render_filter_options());
			this.load();
		});
		$r.on("click", '[data-act="back"]', () => {
			// Back to wherever the user came from; straight links land on Student Fee Management.
			if (frappe.route_history.length > 1) window.history.back();
			else frappe.set_route("student-fee-management");
		});
		$r.on("click", '[data-act="generate"]', () => this.fee_certificate_dialog());
		$r.on("click", '[data-act="bulk-generate"]', () => this.bulk_generate_dialog());
		$r.on("click", '[data-act="bulk-download"]', () => this.bulk_download_dialog());
		$r.on("click", '[data-act="clear-selection"]', () => {
			this.selected.clear();
			this.render_selection();
		});

		$r.on("click", "[data-certificate]", (e) => {
			const row = this.certificate_rows.find((c) => c.name === $(e.currentTarget).data("certificate"));
			if (row) this.certificate_download_dialog(row);
		});
		$r.on("click", "[data-certificate-preview]", (e) => {
			// PDFs are served inline, so this opens the browser's viewer; the edited copy wins when uploaded.
			const params = new URLSearchParams({ name: $(e.currentTarget).data("certificate-preview"), file_format: "pdf" });
			window.open(`/api/method/${FC_API}download_fee_certificate?${params.toString()}`, "_blank");
		});
		$r.on("click", "[data-certificate-upload]", (e) => {
			const row = this.certificate_rows.find((c) => c.name === $(e.currentTarget).data("certificate-upload"));
			if (row) this.certificate_upload(row);
		});
		$r.on("click", ".sfm-report-student", (e) => {
			if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
			e.preventDefault();
			frappe.set_route("student-fee-management", $(e.currentTarget).data("student"));
		});

		// Selection survives paging and filtering until cleared.
		$r.on("change", ".sfc-row-check", (e) => {
			const name = $(e.currentTarget).val();
			e.currentTarget.checked ? this.selected.add(name) : this.selected.delete(name);
			this.render_selection();
		});
		$r.on("change", ".sfc-page-check", (e) => {
			this.certificate_rows.forEach((c) => (e.currentTarget.checked ? this.selected.add(c.name) : this.selected.delete(c.name)));
			this.render_selection();
		});

		$r.on("change", "#fc-page-size", (e) => {
			this.state.page_length = cint($(e.currentTarget).val()) || 25;
			try {
				localStorage.setItem("fc_page_length", this.state.page_length);
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

	// ── List ─────────────────────────────────────────────────────────────
	reload() {
		this.state.start = 0;
		this.load();
	}

	async load() {
		const req = ++this.req;
		const $panel = this.$root.find(".sfm-report-panel");
		$panel.find(".sfm-report-caption").text(__("Loading…"));
		$panel.find(".sfc-table tbody").html(
			`<tr><td colspan="11"><div class="sfm-empty-state">${sfm_icon("loader", 22, "sfm-spin")}</div></td></tr>`
		);
		let result;
		try {
			const r = await frappe.call({
				method: FC_API + "get_fee_certificates",
				args: { ...this.filters, start: this.state.start, page_length: this.state.page_length },
			});
			result = r.message;
		} catch (e) {
			result = null;
		}
		if (req !== this.req) return;
		if (!result) {
			$panel.find(".sfm-report-caption").text("");
			$panel.find(".sfc-table thead").empty();
			$panel.find(".sfc-table tbody").html(
				`<tr><td><div class="sfm-empty-state"><span class="sfm-empty-icon">${sfm_icon("alert", 22)}</span><div class="sfm-empty-title">${__("Couldn't load certificates")}</div></div></td></tr>`
			);
			$panel.find('.sfm-pager[data-pager="report"]').empty();
			return;
		}
		this.render_certificates(result);
	}

	render_certificates({ rows, count }) {
		this.certificate_rows = rows;
		this.total = cint(count);
		const $t = this.$root.find(".sfc-table");
		$t.find("thead").html(`<tr>
			<th scope="col" class="sfm-check"><input type="checkbox" class="sfc-page-check" aria-label="${__("Select all on this page")}"></th>
			<th scope="col">${__("Certificate No.")}</th>
			<th scope="col">${__("Name")}</th>
			<th scope="col">${__("Certificate For")}</th>
			<th scope="col">${__("Purpose")}</th>
			<th scope="col">${__("Academic Year")}</th>
			<th scope="col">${__("Generated On")}</th>
			<th scope="col">${__("Generated By")}</th>
			<th scope="col" class="center">${__("Preview")}</th>
			<th scope="col" class="center">${__("Download")}</th>
			<th scope="col" class="center">${__("Upload Edited")}</th>
		</tr>`);
		$t.find("tbody").html(
			rows.length
				? rows
						.map((d) => {
							const name = d.student
								? `<a href="/desk/student-fee-management/${encodeURIComponent(d.student)}" class="sfm-report-student" data-student="${sfm_esc(d.student)}">${sfm_esc(d.student_name || d.student)}</a>`
								: `<a href="${frappe.utils.get_form_link("Applicant", d.applicant)}">${sfm_esc(d.student_name || d.applicant)}</a>`;
							const ids = [d.person_id, d.admit_card_number ? __("Admit card {0}", [d.admit_card_number]) : ""]
								.filter(Boolean)
								.map(sfm_esc)
								.join(" · ");
							const is_applicant = d.certificate_for === "Admission Stage";
							return `<tr>
								<td class="sfm-check"><input type="checkbox" class="sfc-row-check" value="${sfm_esc(d.name)}"
									${this.selected.has(d.name) ? "checked" : ""} aria-label="${sfm_esc(__("Select {0}", [d.name]))}"></td>
								<td><a class="sfm-strong" href="${frappe.utils.get_form_link("Fee Certificate Request", d.name)}">${sfm_esc(d.name)}</a></td>
								<td>${name}<div class="sfm-sub">${ids}</div></td>
								<td>${sfm_badge(is_applicant ? "Pending" : "Active", is_applicant ? __("Applicant") : __("Campus Student"))}</td>
								<td class="sfm-wrap">${sfm_esc(d.purpose)}</td>
								<td>${sfm_esc(d.academic_year || "—")}</td>
								<td class="sfm-nowrap">${sfm_datetime(d.generated_on || d.creation)}</td>
								<td>${sfm_esc(d.source === "Student Portal" ? __("Student (portal)") : d.owner)}</td>
								<td class="center"><button type="button" class="sfm-icon-btn" data-certificate-preview="${sfm_esc(d.name)}"
									aria-label="${sfm_esc(__("Preview certificate {0}", [d.name]))}"
									title="${sfm_esc(d.edited_certificate ? __("Preview (edited PDF)") : __("Preview"))}">${sfm_icon("eye", 16)}</button></td>
								<td class="center"><button type="button" class="sfm-icon-btn" data-certificate="${sfm_esc(d.name)}"
									aria-label="${sfm_esc(__("Download certificate {0}", [d.name]))}" title="${__("Download Certificate")}">${sfm_icon("download", 16)}</button></td>
								<td class="center">
									<button type="button" class="sfm-icon-btn" data-certificate-upload="${sfm_esc(d.name)}"
										aria-label="${sfm_esc(__("Upload edited PDF for {0}", [d.name]))}"
										title="${sfm_esc(d.edited_certificate ? __("Edited certificate uploaded {0} — click to replace or remove", [sfm_datetime(d.edited_on)]) : __("Upload edited certificate (Word or PDF — saved as PDF)"))}">${sfm_icon("upload", 16)}</button>
									${d.edited_certificate ? `<div class="sfm-sub">${sfm_badge("Paid", __("Edited"))}</div>` : ""}
								</td>
							</tr>`;
						})
						.join("")
				: `<tr><td colspan="11"><div class="sfm-empty-state"><span class="sfm-empty-icon">${sfm_icon("search-x", 22)}</span><div class="sfm-empty-title">${__("No certificates found")}</div><div class="sfm-muted">${__("Use Generate Certificate or Bulk Generate above to create some.")}</div></div></td></tr>`
		);
		sfm_render_pager(this.total, rows.length, {
			state: this.state,
			$pager: this.$root.find('.sfm-pager[data-pager="report"]'),
			$caption: this.$root.find(".sfm-report-caption"),
			one: __("1 certificate matches the current filters"),
			many: __("{0} certificates match the current filters"),
			showing_one: __("Showing 1 of 1 certificate"),
			showing_many: __("Showing {0} to {1} of {2} certificates"),
		});
		this.render_selection();
	}

	render_selection() {
		const n = this.selected.size;
		this.$root.find(".sfc-selected").text(n ? __("{0} selected", [sfm_int(n)]) : "");
		this.$root.find('[data-act="clear-selection"]').prop("hidden", !n);
		this.$root.find(".sfc-bulk-label").text(n ? __("Download Selected (ZIP)") : __("Download All (ZIP)"));
		const on_page = this.certificate_rows.filter((c) => this.selected.has(c.name)).length;
		this.$root
			.find(".sfc-page-check")
			.prop("checked", on_page > 0 && on_page === this.certificate_rows.length)
			.prop("indeterminate", on_page > 0 && on_page < this.certificate_rows.length);
	}

	// ── Bulk download ────────────────────────────────────────────────────
	// Selected certificates, or every certificate matching the filters when none are selected.
	bulk_download_dialog(names = null) {
		const chosen = names || [...this.selected];
		const count = chosen.length || this.total;
		if (!count) return frappe.msgprint(__("There are no certificates to download."));
		const dialog = new frappe.ui.Dialog({
			title: __("Download Certificates"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p>${
						chosen.length
							? __("{0} selected certificate(s) will be downloaded as one ZIP file.", [sfm_int(chosen.length)])
							: __("All {0} certificate(s) matching the current filters will be downloaded as one ZIP file.", [sfm_int(count)])
					}</p><p class="sfm-muted">${__("PDF gives the edited copy wherever one was uploaded.")}</p>`,
				},
				{
					fieldtype: "Select",
					fieldname: "file_format",
					label: __("Download As"),
					options: [
						{ value: "pdf", label: __("PDF") },
						{ value: "docx", label: __("Word (.docx)") },
					],
					default: "pdf",
					reqd: 1,
				},
			],
			primary_action_label: __("Download ZIP"),
			primary_action: async ({ file_format }) => {
				dialog.hide();
				let list = chosen;
				if (!list.length) {
					const r = await frappe.call({ method: FC_API + "get_fee_certificates", args: { ...this.filters, names_only: 1 } });
					list = r.message || [];
				}
				this.bulk_download(list, file_format);
			},
		});
		dialog.$wrapper.addClass("sfm-dialog");
		dialog.show();
	}

	async bulk_download(names, file_format) {
		if (!names.length) return frappe.msgprint(__("There are no certificates to download."));
		frappe.dom.freeze(__("Preparing {0} certificate(s)…", [sfm_int(names.length)]));
		try {
			const res = await fetch(`/api/method/${FC_API}bulk_download_fee_certificates`, {
				method: "POST",
				credentials: "same-origin",
				headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, "Content-Type": "application/x-www-form-urlencoded" },
				body: new URLSearchParams({ names: JSON.stringify(names), file_format }),
			});
			const type = res.headers.get("content-type") || "";
			if (res.ok && !type.includes("json")) {
				const disposition = res.headers.get("content-disposition") || "";
				const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
				this.save_blob(await res.blob(), match ? decodeURIComponent(match[1]) : "Fee Certificates.zip");
				return;
			}
			const json = await res.json();
			if (!res.ok) {
				frappe.msgprint({ title: __("Download failed"), message: sfm_esc(sfm_server_message(json) || __("Could not prepare the ZIP.")), indicator: "red" });
				return;
			}
			// Large selection: built in the background; realtime tells us when it's ready.
			this.zip_progress(json.message.count);
		} catch (e) {
			frappe.msgprint({ title: __("Download failed"), message: __("Network error while preparing the ZIP."), indicator: "red" });
		} finally {
			frappe.dom.unfreeze();
		}
	}

	save_blob(blob, filename) {
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = filename;
		document.body.appendChild(a);
		a.click();
		a.remove();
		setTimeout(() => URL.revokeObjectURL(url), 2000);
	}

	zip_progress(total) {
		this.zip_total = total;
		frappe.show_progress(__("Preparing ZIP"), 0, total, __("Building {0} certificates in the background…", [sfm_int(total)]));
	}

	bind_realtime() {
		frappe.realtime.off("fee_certificate_zip");
		frappe.realtime.on("fee_certificate_zip", (data) => {
			if (data.progress != null) {
				frappe.show_progress(__("Preparing ZIP"), data.progress, data.total, __("{0} of {1} certificates ready", [data.progress, data.total]));
				return;
			}
			frappe.hide_progress();
			if (data.failed) {
				frappe.msgprint({ title: __("Download failed"), message: __("The ZIP could not be built. See the Error Log."), indicator: "red" });
				return;
			}
			const a = document.createElement("a");
			a.href = data.file_url;
			a.download = "";
			document.body.appendChild(a);
			a.click();
			a.remove();
			frappe.msgprint({
				title: __("ZIP ready"),
				indicator: data.errors && data.errors.length ? "orange" : "green",
				message:
					__("{0} certificate(s) downloaded.", [sfm_int(data.count)]) +
					` <a href="${sfm_esc(data.file_url)}" download>${__("Download again")}</a>` +
					(data.errors && data.errors.length
						? `<br><br>${__("Skipped:")}<br>${data.errors.map((e) => `${sfm_esc(e.certificate)}: ${sfm_esc(e.error)}`).join("<br>")}`
						: ""),
			});
		});
	}

	// ── Bulk generate (campus students) ──────────────────────────────────
	async bulk_generate_dialog() {
		const o = await this.options();
		if (!o.purposes.length) {
			frappe.msgprint(__("No certificate purposes are enabled. Set them up in Fee Certificate Settings."));
			return;
		}
		let students = [];
		const picked = new Set();
		const list_opts = (values) => (txt) =>
			values
				.filter((v) => !txt || String(v.label || v).toLowerCase().includes(txt.toLowerCase()))
				.map((v) => (typeof v === "string" ? { value: v, description: "" } : v));

		const dialog = new frappe.ui.Dialog({
			title: __("Bulk Generate Fee Certificates"),
			size: "large",
			fields: [
				{ fieldtype: "Section Break", label: __("Certificate") },
				{ fieldname: "purpose", fieldtype: "Select", label: __("Purpose"), options: ["", ...o.purposes.map((p) => p.purpose)], reqd: 1 },
				{ fieldtype: "Column Break" },
				{ fieldname: "academic_year", fieldtype: "Select", label: __("Academic Year"), options: o.academic_years, default: o.academic_years[0], reqd: 1 },
				{ fieldtype: "Column Break" },
				{
					fieldname: "has_scholarship",
					fieldtype: "Check",
					label: __("Deduct University Scholarship"),
					default: 1,
					description: __("Shows the scholarship / waiver on the student's dues as a deduction."),
				},
				{ fieldtype: "Section Break", label: __("Students"), description: __("Pick the students by programme, batch, year or term, then Find Students. Campus students only; applicants are generated one at a time.") },
				{
					fieldname: "programme",
					fieldtype: "MultiSelectList",
					label: __("Programme"),
					get_data: list_opts(o.programmes.map((p) => ({ value: p.name, description: p.program_name || "" }))),
				},
				{ fieldname: "batch", fieldtype: "MultiSelectList", label: __("Batch"), get_data: list_opts(o.batches) },
				{ fieldtype: "Column Break" },
				{ fieldname: "student_year", fieldtype: "MultiSelectList", label: __("Student's Academic Year"), get_data: list_opts(o.student_years) },
				{
					fieldname: "academic_term",
					fieldtype: "MultiSelectList",
					label: __("Term"),
					get_data: list_opts([...new Set(o.terms.map((t) => t.academic_term))]),
				},
				{ fieldtype: "Column Break" },
				{ fieldname: "search", fieldtype: "Data", label: __("Name / ID contains") },
				{ fieldname: "active_only", fieldtype: "Check", label: __("Active students only"), default: 1 },
				{ fieldname: "find", fieldtype: "Button", label: __("Find Students"), click: () => find() },
				{ fieldtype: "Section Break" },
				{ fieldname: "students_html", fieldtype: "HTML" },
			],
			primary_action_label: __("Generate"),
			primary_action: (v) => {
				const chosen = students.filter((s) => picked.has(s.name)).map((s) => s.name);
				if (!chosen.length) return frappe.msgprint(__("Find and select at least one student."));
				frappe.confirm(__("Generate <b>{0}</b> certificate(s) for <b>{1}</b> ({2})?", [sfm_int(chosen.length), sfm_esc(v.purpose), sfm_esc(v.academic_year)]), () => {
					dialog.hide();
					this.run_bulk_generate(chosen, v);
				});
			},
		});

		const $list = dialog.fields_dict.students_html.$wrapper;
		const render = () => {
			const n = picked.size;
			dialog.set_primary_action(n ? __("Generate {0} Certificate(s)", [sfm_int(n)]) : __("Generate"));
			if (!students.length) {
				$list.html(`<div class="sfm-muted sfc-pick-empty">${__("No students listed yet — set the filters and click Find Students.")}</div>`);
				return;
			}
			$list.html(`
				<div class="sfc-pick-head">
					<label class="sfc-pick-all"><input type="checkbox" class="sfc-pick-toggle" ${n === students.length ? "checked" : ""}>
						<span>${__("{0} of {1} students selected", [sfm_int(n), sfm_int(students.length)])}</span></label>
				</div>
				<div class="sfc-pick-list">
					${students
						.map(
							(s) => `<label class="sfc-pick-row"><input type="checkbox" value="${sfm_esc(s.name)}" ${picked.has(s.name) ? "checked" : ""}>
								<span><b>${sfm_esc(s.first_name || s.name)}</b> <span class="sfm-muted">${sfm_esc(s.registration_id || s.name)}</span></span>
								<span class="sfm-muted">${sfm_esc([s.programme_of_study, s.batch, s.academic_year].filter(Boolean).join(" · "))}</span></label>`
						)
						.join("")}
				</div>`);
			$list.find(".sfc-pick-toggle").prop("indeterminate", n > 0 && n < students.length);
		};
		$list.on("change", ".sfc-pick-row input", (e) => {
			e.currentTarget.checked ? picked.add(e.currentTarget.value) : picked.delete(e.currentTarget.value);
			render();
		});
		$list.on("change", ".sfc-pick-toggle", (e) => {
			students.forEach((s) => (e.currentTarget.checked ? picked.add(s.name) : picked.delete(s.name)));
			render();
		});
		const find = async () => {
			const v = dialog.get_values(true);
			$list.html(`<div class="sfm-empty-state">${sfm_icon("loader", 22, "sfm-spin")}</div>`);
			const r = await frappe.call({
				method: FC_API + "get_bulk_students",
				args: {
					programme: v.programme || [],
					batch: v.batch || [],
					academic_year: v.student_year || [],
					academic_term: v.academic_term || [],
					search: v.search || "",
					active_only: v.active_only ? 1 : 0,
				},
			});
			students = r.message || [];
			if (students.length > 1000) {
				students = students.slice(0, 1000);
				frappe.show_alert({ message: __("Showing the first 1,000 students — narrow the filters to generate the rest."), indicator: "orange" });
			}
			picked.clear();
			students.forEach((s) => picked.add(s.name));
			render();
		};
		dialog.$wrapper.addClass("sfm-dialog");
		render();
		dialog.show();
	}

	async run_bulk_generate(students, v) {
		const done = [];
		const failed = [];
		const total = students.length;
		frappe.show_progress(__("Generating certificates"), 0, total, __("Starting…"));
		try {
			for (let i = 0; i < total; i += FC_GENERATE_BATCH) {
				const r = await frappe.call({
					method: FC_API + "bulk_generate_fee_certificates",
					args: {
						students: students.slice(i, i + FC_GENERATE_BATCH),
						purpose: v.purpose,
						academic_year: v.academic_year,
						has_scholarship: v.has_scholarship ? 1 : 0,
					},
				});
				(r.message || []).forEach((x) => (x.certificate ? done.push(x) : failed.push(x)));
				const n = Math.min(i + FC_GENERATE_BATCH, total);
				frappe.show_progress(__("Generating certificates"), n, total, __("{0} of {1} done", [n, total]));
			}
		} catch (e) {
			failed.push({ student: __("Remaining students"), error: __("Stopped by a server error") });
		} finally {
			frappe.hide_progress();
		}
		this.selected = new Set(done.map((x) => x.certificate));
		this.reload();

		const dialog = new frappe.ui.Dialog({
			title: __("Bulk Generation Finished"),
			fields: [
				{
					fieldtype: "HTML",
					options:
						`<p>${__("{0} certificate(s) generated.", [`<b>${sfm_int(done.length)}</b>`])}` +
						(done.length ? ` ${__("They are selected in the list, ready to download.")}` : "") +
						`</p>` +
						(failed.length
							? `<p class="text-danger">${__("{0} failed:", [sfm_int(failed.length)])}</p><div class="sfc-pick-list">${failed
									.map((x) => `<div class="sfc-pick-row"><b>${sfm_esc(x.student)}</b><span class="sfm-muted">${sfm_esc(x.error)}</span></div>`)
									.join("")}</div>`
							: ""),
				},
			],
			primary_action_label: done.length ? __("Download All as ZIP") : __("Close"),
			primary_action: () => {
				dialog.hide();
				if (done.length) this.bulk_download_dialog(done.map((x) => x.certificate));
			},
		});
		dialog.$wrapper.addClass("sfm-dialog");
		dialog.show();
	}

	// ── Single certificate: generate, download, upload edited ────────────
	// Campus students (Student Master) or admission-stage applicants, who only have an
	// application number and admit card number. Generates the request, then downloads it.
	async fee_certificate_dialog(defaults = {}) {
		if (!this.fc_options) {
			const r = await frappe.call({ method: FC_API + "get_fee_certificate_options" });
			this.fc_options = r.message || { purposes: [], academic_years: [] };
		}
		const { purposes, academic_years } = this.fc_options;
		if (!purposes.length) {
			frappe.msgprint(__("No certificate purposes are enabled. Set them up in Fee Certificate Settings."));
			return;
		}
		const dialog = new frappe.ui.Dialog({
			title: __("Generate Fee Certificate"),
			fields: [
				{
					fieldname: "certificate_for",
					fieldtype: "Select",
					label: __("Certificate For"),
					options: [
						{ value: "Campus Student", label: __("Campus Student (ongoing)") },
						{ value: "Admission Stage", label: __("Admission Stage (applicant)") },
					],
					default: "Campus Student",
					reqd: 1,
					description: __("Admission stage: applicants with only an application number and admit card number."),
				},
				{
					fieldname: "student",
					fieldtype: "Link",
					options: "Student Master",
					label: __("Student"),
					default: defaults.student,
					depends_on: 'eval:doc.certificate_for=="Campus Student"',
					mandatory_depends_on: 'eval:doc.certificate_for=="Campus Student"',
				},
				{
					fieldname: "applicant",
					fieldtype: "Link",
					options: "Applicant",
					label: __("Applicant"),
					depends_on: 'eval:doc.certificate_for=="Admission Stage"',
					mandatory_depends_on: 'eval:doc.certificate_for=="Admission Stage"',
					onchange: () => {
						const applicant = dialog.get_value("applicant");
						if (!applicant) return;
						frappe.db.get_value("Applicant", applicant, "academic_year").then((r) => {
							const ay = r.message && r.message.academic_year;
							if (ay) dialog.set_value("academic_year", ay);
						});
					},
				},
				{
					fieldname: "admit_card_number",
					fieldtype: "Data",
					label: __("Admit Card Number"),
					depends_on: 'eval:doc.certificate_for=="Admission Stage"',
					description: __("Leave blank to use the one from the applicant's entrance test allocation."),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "purpose",
					fieldtype: "Select",
					label: __("Purpose"),
					options: ["", ...purposes.map((p) => p.purpose)],
					reqd: 1,
					description: __("The heading and wording of the certificate follow the purpose."),
				},
				{
					fieldname: "academic_year",
					fieldtype: "Select",
					label: __("Academic Year"),
					options: academic_years,
					default: defaults.academic_year && academic_years.includes(defaults.academic_year) ? defaults.academic_year : academic_years[0],
					reqd: 1,
				},
				{
					fieldname: "file_format",
					fieldtype: "Select",
					label: __("Download As"),
					options: [
						{ value: "pdf", label: __("PDF") },
						{ value: "docx", label: __("Word (.docx) — to edit") },
					],
					default: "pdf",
					reqd: 1,
					description: __("Edit the Word file, then upload it from the list below; it is saved as PDF."),
				},
				{
					fieldname: "has_scholarship",
					fieldtype: "Check",
					label: __("Deduct University Scholarship"),
					default: 1,
					description: __("Shows the scholarship / waiver on the student's dues as a deduction."),
				},
			],
			primary_action_label: __("Generate & Download"),
			primary_action: async (values) => {
				dialog.get_primary_btn().prop("disabled", true);
				try {
					const { file_format, ...args } = values;
					const r = await frappe.call({
						method: FC_API + "generate_fee_certificate",
						args,
						freeze: true,
						freeze_message: __("Generating certificate…"),
					});
					if (r.message) {
						this.download_certificate_file(r.message, file_format === "docx" ? "docx" : "generated");
						dialog.hide();
						this.load();
						frappe.show_alert({
							message: __("Certificate {0} generated", [
								`<a href="${frappe.utils.get_form_link("Fee Certificate Request", r.message)}">${sfm_esc(r.message)}</a>`,
							]),
							indicator: "green",
						});
					}
				} finally {
					dialog.get_primary_btn().prop("disabled", false);
				}
			},
		});
		dialog.$wrapper.addClass("sfm-dialog");
		dialog.show();
	}

	// Saves the file (a PDF would otherwise just open in the browser's viewer).
	download_certificate_file(name, file_format = "pdf") {
		const params = new URLSearchParams({ name, file_format });
		const a = document.createElement("a");
		a.href = `/api/method/${FC_API}download_fee_certificate?${params.toString()}`;
		a.download = "";
		document.body.appendChild(a);
		a.click();
		a.remove();
	}

	// Pick PDF / Word; when an edited PDF was uploaded it is the default.
	certificate_download_dialog(row) {
		const options = [
			...(row.edited_certificate ? [{ value: "pdf", label: __("Edited PDF (uploaded {0})", [sfm_date(row.edited_on)]) }] : []),
			{ value: "generated", label: row.edited_certificate ? __("Generated PDF (without edits)") : __("PDF") },
			{ value: "docx", label: __("Word (.docx) — to edit") },
		];
		const dialog = new frappe.ui.Dialog({
			title: __("Download {0}", [row.name]),
			fields: [
				{ fieldname: "file_format", fieldtype: "Select", label: __("Download As"), options, default: options[0].value, reqd: 1 },
			],
			primary_action_label: __("Download"),
			primary_action: ({ file_format }) => {
				dialog.hide();
				this.download_certificate_file(row.name, file_format);
			},
		});
		dialog.$wrapper.addClass("sfm-dialog");
		dialog.show();
	}

	// Staff edit the Word version, save it as PDF and attach it here; it then replaces
	// the generated certificate on every download (desk and student portal).
	certificate_upload(row) {
		const save = (file_url) =>
			frappe
				.call({
					method: FC_API + "set_edited_certificate",
					args: { name: row.name, file_url },
					freeze: true,
					freeze_message: __("Saving certificate as PDF…"),
				})
				.then((r) => {
					frappe.show_alert({
						message: !file_url
							? __("Edited certificate removed from {0}", [row.name])
							: r.message && r.message.converted
							? __("Word file converted and saved as PDF for {0}", [row.name])
							: __("Edited PDF attached to {0}", [row.name]),
						indicator: "green",
					});
					this.load();
				});
		const upload = () =>
			new frappe.ui.FileUploader({
				doctype: "Fee Certificate Request",
				docname: row.name,
				folder: "Home/Attachments",
				make_attachments_public: 0,
				restrictions: { allowed_file_types: [".pdf", ".docx"], max_number_of_files: 1 },
				on_success: (file) => {
					const url = (file.file_url || "").toLowerCase();
					if (!url.endsWith(".pdf") && !url.endsWith(".docx")) {
						frappe.msgprint(__("Please upload the certificate as a PDF or Word (.docx) file."));
						return;
					}
					save(file.file_url);
				},
			});
		if (!row.edited_certificate) return upload();
		const dialog = new frappe.ui.Dialog({
			title: __("Edited PDF — {0}", [row.name]),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p class="sfm-muted">${__("An edited PDF was uploaded on {0}. Downloads give this file instead of the generated certificate.", [sfm_date(row.edited_on)])}</p>`,
				},
			],
			primary_action_label: __("Replace PDF"),
			primary_action: () => {
				dialog.hide();
				upload();
			},
			secondary_action_label: __("Remove Edited PDF"),
			secondary_action: () => {
				dialog.hide();
				frappe.confirm(__("Remove the edited PDF? Downloads will go back to the generated certificate."), () => save(null));
			},
		});
		dialog.$wrapper.addClass("sfm-dialog");
		dialog.show();
	}
}
