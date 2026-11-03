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
const IDCL_STATUS_COLOR = { Success: "green", Partial: "orange", Failed: "red" };
const IDCL_RESULT_CLASS = { New: "new", Regenerated: "regen", Skipped: "skip", Failed: "fail" };

const IDCL_CSS = `
	.idcl { --b: var(--border-color, #e2e6ea); --m: var(--text-muted, #6b7280); --s: var(--subtle-fg, #f4f5f7); --bg: var(--fg-color, #fff);
		--t: var(--text-color, #1f2937); --a: var(--primary, #2563eb); color: var(--t); display: grid; gap: 16px; }
	.idcl-panel { background: var(--bg); border: 1px solid var(--b); border-radius: 14px; }
	.idcl-hero { padding: 18px 20px; display: flex; gap: 16px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
	.idcl-hero h3 { margin: 0 0 6px; font-size: 19px; font-weight: 600; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
	.idcl-meta { display: flex; gap: 6px 16px; flex-wrap: wrap; color: var(--m); font-size: 12.5px; }
	.idcl-meta b { color: var(--t); font-weight: 500; }
	.idcl-stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border-top: 1px solid var(--b); }
	.idcl-stat { padding: 14px 20px; border-right: 1px solid var(--b); }
	.idcl-stat:last-child { border-right: 0; }
	.idcl-stat b { display: block; font-size: 24px; font-weight: 600; line-height: 1.2; font-variant-numeric: tabular-nums; }
	.idcl-stat span { font-size: 12px; color: var(--m); }
	.idcl-stat small { display: block; font-size: 11.5px; color: var(--m); margin-top: 2px; }
	.idcl-stat.good b { color: var(--green-600, #16a34a); }
	.idcl-stat.bad b { color: var(--red-600, #dc2626); }
	.idcl-stat.warn b { color: var(--orange-600, #ea580c); }
	.idcl-bar { display: flex; height: 8px; border-radius: 99px; overflow: hidden; background: var(--s); margin: 0 20px 16px; }
	.idcl-bar > div { height: 100%; }
	.idcl-legend { display: flex; gap: 14px; flex-wrap: wrap; padding: 0 20px 16px; font-size: 12px; color: var(--m); margin-top: -6px; }
	.idcl-legend i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 6px; }
	.idcl-c-new { background: #22c55e; } .idcl-c-regen { background: #3b82f6; } .idcl-c-skip { background: #cbd5e1; } .idcl-c-fail { background: #ef4444; }
	.idcl-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; padding: 13px 18px; border-bottom: 1px solid var(--b); }
	.idcl-panel-title { font-weight: 600; font-size: 14px; }
	.idcl-settings { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px 20px; padding: 16px 18px; }
	.idcl-setting span { display: block; font-size: 11.5px; color: var(--m); margin-bottom: 3px; }
	.idcl-setting div { font-size: 13px; font-weight: 500; overflow-wrap: anywhere; }
	.idcl-setting .muted { color: var(--m); font-weight: 400; }
	.idcl-chip { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border-radius: 99px; border: 1px solid var(--b);
		background: var(--bg); color: var(--t); font-size: 12px; cursor: pointer; }
	.idcl-chip b { color: var(--m); font-weight: 600; }
	.idcl-chip.active { background: var(--t); border-color: var(--t); color: var(--bg); }
	.idcl-chip.active b { color: inherit; opacity: .75; }
	.idcl-search { height: 30px; width: 220px; max-width: 100%; border: 1px solid var(--b); border-radius: 8px; padding: 0 10px; background: var(--control-bg, var(--s)); color: var(--t); font-size: 12.5px; }
	.idcl-search:focus { outline: none; border-color: var(--a); }
	.idcl-table { width: 100%; border-collapse: collapse; font-size: 13px; }
	.idcl-table th { text-align: left; font-weight: 500; font-size: 11.5px; color: var(--m); padding: 8px 18px; background: var(--s); border-bottom: 1px solid var(--b); position: sticky; top: 0; }
	.idcl-table td { padding: 9px 18px; border-bottom: 1px solid var(--b); vertical-align: top; }
	.idcl-table tr:last-child td { border-bottom: 0; }
	.idcl-table a { color: var(--t); }
	.idcl-table a:hover { color: var(--a); }
	.idcl-sub { color: var(--m); font-size: 11.5px; }
	.idcl-result { display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px; border-radius: 99px; font-size: 11.5px; font-weight: 500; white-space: nowrap; }
	.idcl-result::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
	.idcl-result.new { background: rgba(34,197,94,.12); color: var(--green-700, #15803d); }
	.idcl-result.regen { background: rgba(59,130,246,.12); color: var(--blue-600, #2563eb); }
	.idcl-result.skip { background: var(--s); color: var(--m); }
	.idcl-result.fail { background: rgba(220,38,38,.1); color: var(--red-600, #dc2626); }
	.idcl-msg { color: var(--m); font-size: 12px; max-width: 420px; }
	.idcl-msg.fail { color: var(--red-600, #dc2626); }
	.idcl-nophoto { font-size: 11px; color: var(--orange-600, #ea580c); }
	.idcl-empty { padding: 32px 18px; text-align: center; color: var(--m); font-size: 13px; }
	.idcl-remarks { padding: 14px 18px; font-size: 13px; color: var(--m); }
	@media (max-width: 900px) {
		.idcl-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
		.idcl-stat { border-bottom: 1px solid var(--b); }
		.idcl-settings { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	}
`;

function idcl_duration(seconds) {
	if (seconds === null || seconds === undefined || seconds === "") return "";
	const s = Math.round(+seconds);
	if (s < 60) return __("{0}s", [s]);
	const m = Math.floor(s / 60);
	return s % 60 ? __("{0}m {1}s", [m, s % 60]) : __("{0}m", [m]);
}

function idcl_render(frm) {
	if (!document.getElementById("idcl-css"))
		$(`<style id="idcl-css">${IDCL_CSS}</style>`).appendTo("head");
	const doc = frm.doc;
	const esc = frappe.utils.escape_html;
	const results = doc.results || [];
	const state = (frm.__idcl = frm.__idcl || { filter: "all", query: "" });

	const generated = doc.total_id_cards_generated || 0;
	const new_cards = doc.new_cards || 0;
	const regenerated = doc.regenerated_cards || 0;
	const skipped = doc.skipped_count || 0;
	// Older runs recorded only the generated count.
	const failed =
		doc.failed_count ||
		(doc.total_processed ? Math.max(doc.total_processed - generated, 0) : 0);
	const selected = doc.total_students_selected || 0;
	const has_detail = results.length > 0;

	const user = doc.generated_by ? frappe.user.full_name(doc.generated_by) : "";
	const when = doc.generated_on ? frappe.datetime.str_to_user(doc.generated_on) : "";
	const link = (doctype, name) =>
		name
			? `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${esc(
					name
			  )}</a>`
			: "";

	const bar_total = Math.max(new_cards + regenerated + skipped + failed, 1);
	const bar =
		has_detail || doc.new_cards !== undefined
			? [
					["new", new_cards],
					["regen", regenerated],
					["skip", skipped],
					["fail", failed],
			  ]
					.filter(([, n]) => n)
					.map(
						([k, n]) =>
							`<div class="idcl-c-${k}" style="width:${
								(n / bar_total) * 100
							}%" title="${n}"></div>`
					)
					.join("")
			: "";

	const stat = (value, label, sub = "", cls = "") =>
		`<div class="idcl-stat ${cls}"><b>${value}</b><span>${label}</span>${
			sub ? `<small>${sub}</small>` : ""
		}</div>`;

	const setting = (label, value, muted) =>
		`<div class="idcl-setting"><span>${label}</span><div class="${
			muted ? "muted" : ""
		}">${value}</div></div>`;

	let results_html;
	if (!has_detail) {
		results_html = `<div class="idcl-empty">${__(
			"Per-student results were not recorded for this run. Runs from now on include them."
		)}</div>`;
	} else {
		const counts = { all: results.length, New: 0, Regenerated: 0, Skipped: 0, Failed: 0 };
		results.forEach((r) => (counts[r.result] = (counts[r.result] || 0) + 1));
		const chip = (key, label) =>
			counts[key] || key === "all"
				? `<button class="idcl-chip ${
						state.filter === key ? "active" : ""
				  }" data-filter="${key}">${label} <b>${counts[key]}</b></button>`
				: "";
		const q = state.query.toLowerCase();
		const rows = results.filter(
			(r) =>
				(state.filter === "all" || r.result === state.filter) &&
				(!q ||
					`${r.student} ${r.student_name || ""} ${r.id_card || ""}`
						.toLowerCase()
						.includes(q))
		);
		results_html = `
			<div class="idcl-panel-head">
				<div style="display:flex;gap:6px;flex-wrap:wrap">${chip("all", __("All"))}${chip(
			"New",
			__("New")
		)}${chip("Regenerated", __("Regenerated"))}${chip("Skipped", __("Skipped"))}${chip(
			"Failed",
			__("Failed")
		)}</div>
				<input class="idcl-search" type="search" placeholder="${__(
					"Search student or card"
				)}" value="${esc(state.query)}">
			</div>
			${
				rows.length
					? `<div style="max-height:560px;overflow:auto"><table class="idcl-table">
				<thead><tr><th>${__("Student")}</th><th>${__("Result")}</th><th>${__("ID card")}</th><th>${__(
							"Details"
					  )}</th></tr></thead>
				<tbody>${rows
					.map(
						(r) => `<tr>
						<td>${link("Student Master", r.student)}<div class="idcl-sub">${esc(r.student_name || "")}${
							r.has_photo
								? ""
								: ` · <span class="idcl-nophoto">${__("no photo")}</span>`
						}</div></td>
						<td><span class="idcl-result ${IDCL_RESULT_CLASS[r.result] || "skip"}">${__(
							r.result || ""
						)}</span></td>
						<td>${r.id_card ? link("ID Card Generation", r.id_card) : `<span class="idcl-sub">—</span>`}</td>
						<td><div class="idcl-msg ${r.result === "Failed" ? "fail" : ""}">${esc(r.message || "")}</div></td>
					</tr>`
					)
					.join("")}</tbody></table></div>`
					: `<div class="idcl-empty">${__("No results match this filter.")}</div>`
			}`;
	}

	const $w = frm.fields_dict.summary_html.$wrapper;
	$w.closest(".section-body").css("max-width", "none");
	$w.html(`
		<div class="idcl">
			<section class="idcl-panel">
				<div class="idcl-hero">
					<div>
						<h3>${__("ID card run")} ${esc(doc.name)}
							<span class="indicator-pill ${IDCL_STATUS_COLOR[doc.generation_status] || "gray"}">${__(
		doc.generation_status || "—"
	)}</span>
						</h3>
						<div class="idcl-meta">
							${when ? `<span>${__("Finished")} <b>${esc(when)}</b></span>` : ""}
							${user ? `<span>${__("by")} <b>${esc(user)}</b></span>` : ""}
							${
								doc.duration_seconds
									? `<span>${__("took")} <b>${idcl_duration(
											doc.duration_seconds
									  )}</b></span>`
									: ""
							}
							${doc.generation_mode ? `<span>${__("{0} run", [__(doc.generation_mode)])}</span>` : ""}
							${
								doc.generation_tool_run_id
									? `<span>${__("Run ID")} <b>${esc(
											doc.generation_tool_run_id
									  )}</b></span>`
									: ""
							}
						</div>
					</div>
				</div>
				<div class="idcl-stats">
					${stat(
						selected,
						__("Students in list"),
						doc.total_processed !== undefined && doc.total_processed !== null
							? __("{0} processed", [doc.total_processed || 0])
							: ""
					)}
					${stat(
						generated,
						__("Cards generated"),
						new_cards || regenerated
							? __("{0} new · {1} regenerated", [new_cards, regenerated])
							: "",
						generated ? "good" : ""
					)}
					${stat(skipped, __("Skipped"), skipped ? __("Already had a card") : "")}
					${stat(failed, __("Failed"), failed ? __("See results below") : "", failed ? "bad" : "")}
					${stat(
						doc.missing_photo_count || 0,
						__("Without a photo"),
						doc.missing_photo_count ? __("Default avatar printed") : "",
						doc.missing_photo_count ? "warn" : ""
					)}
				</div>
				${
					bar
						? `<div class="idcl-bar">${bar}</div>
				<div class="idcl-legend"><span><i class="idcl-c-new"></i>${__(
					"New"
				)}</span><span><i class="idcl-c-regen"></i>${__("Regenerated")}</span>
					<span><i class="idcl-c-skip"></i>${__("Skipped")}</span><span><i class="idcl-c-fail"></i>${__(
								"Failed"
						  )}</span></div>`
						: ""
				}
			</section>
			<section class="idcl-panel">
				<div class="idcl-panel-head"><div class="idcl-panel-title">${__("Settings used")}</div></div>
				<div class="idcl-settings">
					${setting(
						__("Template"),
						doc.template_used ? link("ID Card Template", doc.template_used) : "—",
						!doc.template_used
					)}
					${setting(
						__("Academic Year"),
						doc.academic_year ? esc(doc.academic_year) : __("Any"),
						!doc.academic_year
					)}
					${setting(__("Programme"), doc.program ? esc(doc.program) : __("Any"), !doc.program)}
					${setting(__("Batch"), doc.batch ? esc(doc.batch) : __("Any"), !doc.batch)}
					${setting(__("Section"), doc.section ? esc(doc.section) : __("Any"), !doc.section)}
					${setting(
						__("Issue date"),
						doc.issue_date
							? frappe.datetime.str_to_user(doc.issue_date)
							: __("Not recorded"),
						!doc.issue_date
					)}
					${setting(
						__("Valid till"),
						doc.expiry_date
							? frappe.datetime.str_to_user(doc.expiry_date)
							: __("Programme end date"),
						!doc.expiry_date
					)}
					${setting(__("Sides"), doc.sides ? esc(doc.sides) : __("Not recorded"), !doc.sides)}
					${setting(__("Regenerate existing"), doc.regenerate_existing ? __("Yes") : __("No"))}
				</div>
			</section>
			<section class="idcl-panel">
				<div class="idcl-panel-head" style="${
					has_detail ? "border-bottom:0;padding-bottom:0" : ""
				}"><div class="idcl-panel-title">${__("Results by student")}</div></div>
				<div class="idcl-results">${results_html}</div>
			</section>
			${
				doc.remarks
					? `<section class="idcl-panel"><div class="idcl-remarks">${esc(
							doc.remarks
					  )}</div></section>`
					: ""
			}
		</div>`);

	$w.off(".idcl");
	$w.on("click.idcl", "[data-filter]", (e) => {
		state.filter = $(e.currentTarget).data("filter");
		idcl_render(frm);
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
		const cards = results.map((r) => r.id_card).filter(Boolean);
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
