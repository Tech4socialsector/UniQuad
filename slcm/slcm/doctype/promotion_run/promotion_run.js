frappe.ui.form.on("Promotion Run", {
	refresh(frm) {
		inject_promotion_run_css();
		if (frm.is_new()) return;

		frm.disable_save();
		hide_native_sections(frm);
		render_hero(frm);
		render_flow_guide(frm);
		render_log_table(frm);
		add_toolbar_actions(frm);

		if (frm.doc.status === "Queued" || frm.doc.status === "In Progress") {
			watch_run(frm);
		}
	},
});

/*****************************************************
 * LAYOUT: hide native form UI, we render our own
 *****************************************************/
function hide_native_sections(frm) {
	[
		"section_criteria", "section_target", "section_status",
		"section_meta", "error_log", "section_log",
	].forEach((f) => frm.toggle_display(f, false));
}

/*****************************************************
 * CSS
 *****************************************************/
function inject_promotion_run_css() {
	if (document.getElementById("promotion-run-css")) return;
	const style = document.createElement("style");
	style.id = "promotion-run-css";
	style.innerHTML = `
		.pr-hero {
			background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
			border-radius: 10px;
			padding: 22px 26px;
			margin: 4px 0 20px 0;
			color: #ffffff;
		}
		.pr-hero-top {
			display: flex;
			align-items: center;
			justify-content: space-between;
			flex-wrap: wrap;
			gap: 12px;
			margin-bottom: 18px;
		}
		.pr-hero-title {
			font-size: 13px;
			text-transform: uppercase;
			letter-spacing: 0.06em;
			color: #94a3b8;
			margin-bottom: 4px;
		}
		.pr-hero-criteria {
			font-size: 15px;
			font-weight: 600;
		}
		.pr-hero-criteria .arrow {
			color: #64748b;
			margin: 0 8px;
		}
		.pr-status-pill {
			display: inline-flex;
			align-items: center;
			gap: 6px;
			padding: 5px 14px;
			border-radius: 20px;
			font-size: 12px;
			font-weight: 700;
			text-transform: uppercase;
			letter-spacing: 0.04em;
		}
		.pr-status-pill .dot {
			width: 7px; height: 7px; border-radius: 50%;
			background: currentColor;
		}
		.pr-status-pill.queued, .pr-status-pill.in-progress {
			background: rgba(251, 191, 36, 0.18); color: #fbbf24;
		}
		.pr-status-pill.completed {
			background: rgba(74, 222, 128, 0.18); color: #4ade80;
		}
		.pr-status-pill.completed-with-errors {
			background: rgba(251, 146, 60, 0.18); color: #fb923c;
		}
		.pr-status-pill.error {
			background: rgba(248, 113, 113, 0.18); color: #f87171;
		}
		.pr-stats {
			display: grid;
			grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
			gap: 14px;
		}
		.pr-stat {
			background: rgba(255,255,255,0.06);
			border: 1px solid rgba(255,255,255,0.08);
			border-radius: 8px;
			padding: 12px 14px;
		}
		.pr-stat-value {
			font-size: 24px;
			font-weight: 700;
			line-height: 1.1;
		}
		.pr-stat-label {
			font-size: 11px;
			color: #94a3b8;
			text-transform: uppercase;
			letter-spacing: 0.05em;
			margin-top: 4px;
		}
		.pr-stat.promoted .pr-stat-value { color: #4ade80; }
		.pr-stat.skipped .pr-stat-value { color: #fb923c; }
		.pr-stat.resolved .pr-stat-value { color: #38bdf8; }

		.pr-reason-breakdown {
			margin-top: 16px;
			display: flex;
			flex-wrap: wrap;
			gap: 8px;
		}
		.pr-reason-chip {
			background: rgba(255,255,255,0.08);
			border: 1px solid rgba(255,255,255,0.1);
			border-radius: 20px;
			padding: 4px 12px;
			font-size: 12px;
			color: #e2e8f0;
		}
		.pr-reason-chip b { color: #ffffff; }

		.pr-flow-guide {
			background: #f8fafc;
			border: 1px solid #e2e8f0;
			border-radius: 8px;
			padding: 14px 18px;
			margin-bottom: 20px;
			font-size: 12.5px;
			color: #475569;
			line-height: 1.6;
		}
		.pr-flow-guide-title {
			font-weight: 700;
			font-size: 11px;
			text-transform: uppercase;
			letter-spacing: 0.05em;
			color: #64748b;
			margin-bottom: 8px;
		}
		.pr-flow-steps {
			display: flex;
			flex-wrap: wrap;
			gap: 6px;
			align-items: center;
		}
		.pr-flow-step {
			display: inline-flex;
			align-items: center;
			gap: 6px;
			background: #ffffff;
			border: 1px solid #e2e8f0;
			border-radius: 20px;
			padding: 4px 12px;
			font-size: 12px;
			color: #334155;
			font-weight: 500;
		}
		.pr-flow-step .num {
			width: 16px; height: 16px;
			border-radius: 50%;
			background: #1e293b;
			color: #fff;
			font-size: 10px;
			display: flex; align-items: center; justify-content: center;
			font-weight: 700;
		}
		.pr-flow-arrow { color: #cbd5e1; font-size: 13px; }

		.pr-toolbar {
			display: flex;
			align-items: center;
			justify-content: space-between;
			flex-wrap: wrap;
			gap: 10px;
			margin-bottom: 12px;
		}
		.pr-toolbar-title {
			font-size: 13px;
			font-weight: 700;
			color: #1e293b;
		}
		.pr-toolbar-hint {
			font-size: 11.5px;
			color: #94a3b8;
		}

		.pr-table-wrap {
			border: 1px solid #e2e8f0;
			border-radius: 8px;
			overflow: hidden;
		}
		.pr-table {
			width: 100%;
			border-collapse: collapse;
			font-size: 13px;
		}
		.pr-table thead th {
			background: #f8fafc;
			text-align: left;
			font-size: 11px;
			font-weight: 700;
			text-transform: uppercase;
			letter-spacing: 0.04em;
			color: #64748b;
			padding: 10px 12px;
			border-bottom: 1px solid #e2e8f0;
			white-space: nowrap;
		}
		.pr-table tbody tr {
			border-bottom: 1px solid #f1f5f9;
		}
		.pr-table tbody tr:last-child { border-bottom: none; }
		.pr-table tbody tr:hover { background: #f8fafc; }
		.pr-table tbody tr.resolved-row { background: #f8fafc; }
		.pr-table td {
			padding: 10px 12px;
			vertical-align: middle;
		}
		.pr-row-check { width: 30px; }
		.pr-student-name { font-weight: 600; color: #1e293b; }
		.pr-student-id { font-size: 11px; color: #94a3b8; }
		.pr-badge {
			display: inline-flex;
			align-items: center;
			gap: 5px;
			font-size: 11px;
			font-weight: 700;
			padding: 3px 10px;
			border-radius: 20px;
			white-space: nowrap;
		}
		.pr-badge.promoted { background: #dcfce7; color: #166534; }
		.pr-badge.skipped { background: #fee2e2; color: #b91c1c; }
		.pr-badge.failed { background: #fee2e2; color: #b91c1c; }
		.pr-badge.resolved { background: #e0f2fe; color: #075985; }
		.pr-reason-text {
			font-size: 11.5px;
			color: #64748b;
			max-width: 220px;
			white-space: normal;
		}
		.pr-row-actions {
			display: flex;
			gap: 6px;
			white-space: nowrap;
		}
		.pr-row-actions button {
			border: none;
			border-radius: 5px;
			font-size: 11px;
			font-weight: 600;
			padding: 5px 10px;
			cursor: pointer;
		}
		.pr-btn-promote { background: #16a34a; color: #fff; }
		.pr-btn-promote:hover { background: #15803d; }
		.pr-btn-exempt { background: #e2e8f0; color: #334155; }
		.pr-btn-exempt:hover { background: #cbd5e1; }
		.pr-resolved-note {
			font-size: 11px;
			color: #075985;
		}

		.pr-empty {
			padding: 40px;
			text-align: center;
			color: #94a3b8;
			font-size: 13px;
		}

		.pr-toolbar-btn {
			font-weight: 600 !important;
		}
	`;
	document.head.appendChild(style);
}

/*****************************************************
 * HERO SUMMARY
 *****************************************************/
const STATUS_LABEL = {
	"Queued": "Queued",
	"In Progress": "In Progress",
	"Completed": "Completed",
	"Completed with Errors": "Completed with Errors",
	"Error": "Error",
};

function status_class(status) {
	return (status || "").toLowerCase().replace(/\s+/g, "-");
}

function render_hero(frm) {
	const d = frm.doc;
	const resolved_count = (d.log || []).filter((r) => r.resolved).length;

	const by_reason = {};
	(d.log || []).forEach((r) => {
		if (r.result !== "Promoted" && !r.resolved) {
			const key = r.reason_code || "Other";
			by_reason[key] = (by_reason[key] || 0) + 1;
		}
	});
	const reason_html = Object.keys(by_reason).length
		? Object.entries(by_reason)
			.map(([k, v]) => `<span class="pr-reason-chip"><b>${v}</b> ${frappe.utils.escape_html(k)}</span>`)
			.join("")
		: "";

	const criteria = [
		d.program,
		d.source_academic_year,
		d.batch ? ` / ${d.batch}` : "",
	].filter(Boolean).join(" ");
	const target = [d.target_academic_year, d.target_term].filter(Boolean).join(" ");

	const html = `
		<div class="pr-hero">
			<div class="pr-hero-top">
				<div>
					<div class="pr-hero-title">${__("Promotion Run")} · ${frappe.utils.escape_html(d.name)}</div>
					<div class="pr-hero-criteria">
						${frappe.utils.escape_html(criteria || "—")}
						<span class="arrow">&#8594;</span>
						${frappe.utils.escape_html(target || "—")}
					</div>
				</div>
				<span class="pr-status-pill ${status_class(d.status)}">
					<span class="dot"></span>${frappe.utils.escape_html(STATUS_LABEL[d.status] || d.status || "")}
				</span>
			</div>
			<div class="pr-stats">
				<div class="pr-stat">
					<div class="pr-stat-value">${d.total_students || 0}</div>
					<div class="pr-stat-label">${__("Total Students")}</div>
				</div>
				<div class="pr-stat promoted">
					<div class="pr-stat-value">${d.promoted_count || 0}</div>
					<div class="pr-stat-label">${__("Promoted")}</div>
				</div>
				<div class="pr-stat skipped">
					<div class="pr-stat-value">${d.skipped_count || 0}</div>
					<div class="pr-stat-label">${__("Skipped")}</div>
				</div>
				<div class="pr-stat resolved">
					<div class="pr-stat-value">${resolved_count}</div>
					<div class="pr-stat-label">${__("Manually Resolved")}</div>
				</div>
			</div>
			${reason_html ? `<div class="pr-reason-breakdown">${reason_html}</div>` : ""}
		</div>
	`;

	if (frm.pr_hero_wrapper) frm.pr_hero_wrapper.remove();
	frm.pr_hero_wrapper = $(html).prependTo(frm.layout.wrapper);
}

/*****************************************************
 * FLOW GUIDE — explains the process to the user
 *****************************************************/
function render_flow_guide(frm) {
	// Runs started from Student Enrollment carry no policy: term-to-term
	// promotion is automatic. Older runs may still reference a policy.
	const has_policy = !!frm.doc.promotion_policy;
	const html = `
		<div class="pr-flow-guide">
			<div class="pr-flow-guide-title">${__("How this works")}</div>
			<div class="pr-flow-steps">
				<span class="pr-flow-step"><span class="num">1</span>${has_policy
					? __("System evaluates every enrolled student against the policy")
					: __("Term-to-term promotion — no policy check is applied")}</span>
				<span class="pr-flow-arrow">&#8594;</span>
				<span class="pr-flow-step"><span class="num">2</span>${has_policy
					? __("Eligible students are promoted automatically")
					: __("Every selected student is moved to the next term's Batch")}</span>
				<span class="pr-flow-arrow">&#8594;</span>
				<span class="pr-flow-step"><span class="num">3</span>${has_policy
					? __("Ineligible students are listed below as Skipped, with a reason")
					: __("Students who couldn't be moved (e.g. no target Batch) are listed as Skipped")}</span>
				<span class="pr-flow-arrow">&#8594;</span>
				<span class="pr-flow-step"><span class="num">4</span>${__("You decide: Promote Anyway, Mark as Exempt, or fix data and Retry")}</span>
			</div>
		</div>
	`;
	if (frm.pr_flow_wrapper) frm.pr_flow_wrapper.remove();
	frm.pr_flow_wrapper = $(html).insertAfter(frm.pr_hero_wrapper);
}

/*****************************************************
 * TOOLBAR ACTIONS (top of form + above table)
 *****************************************************/
function add_toolbar_actions(frm) {
	frm.page.clear_custom_buttons();

	frm.add_custom_button(__("Retry Unresolved"), () => {
		const unresolved = (frm.doc.log || []).filter((r) => r.result !== "Promoted" && !r.resolved).length;
		if (!unresolved) {
			frappe.msgprint(__("There are no unresolved skipped students to retry."));
			return;
		}
		frappe.confirm(
			__("Re-evaluate all {0} unresolved Skipped/Failed student(s) against current data?", [unresolved]),
			() => {
				frappe.call({
					method: "slcm.slcm.doctype.promotion_run.promotion_run.retry_unresolved",
					args: { promotion_run_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Retrying..."),
					callback: (r) => {
						if (!r.message) return;
						frappe.show_alert({
							message: __("Retried {0}, promoted {1}", [r.message.retried, r.message.promoted]),
							indicator: "green",
						});
						frm.reload_doc();
					},
				});
			}
		);
	}).addClass("pr-toolbar-btn");
}

/*****************************************************
 * CUSTOM LOG TABLE (replaces the native child grid)
 *****************************************************/
function render_log_table(frm) {
	const rows = frm.doc.log || [];

	const table_html = rows.length ? build_table_html(rows) : `<div class="pr-empty">${__("No students processed yet.")}</div>`;

	const html = `
		<div class="pr-log-section">
			<div class="pr-toolbar">
				<div>
					<div class="pr-toolbar-title">${__("Per-Student Log")} (${rows.length})</div>
					<div class="pr-toolbar-hint">${__("Select Skipped rows to promote or exempt in bulk")}</div>
				</div>
				<div>
					<button class="btn btn-sm pr-select-all-btn" style="margin-right:6px;">${__("Select All Skipped")}</button>
					<button class="btn btn-sm btn-success pr-bulk-promote-btn">${__("Promote Selected")}</button>
					<button class="btn btn-sm pr-bulk-exempt-btn" style="margin-left:6px;">${__("Mark Selected Exempt")}</button>
				</div>
			</div>
			<div class="pr-table-wrap">${table_html}</div>
		</div>
	`;

	if (frm.pr_log_wrapper) frm.pr_log_wrapper.remove();
	frm.pr_log_wrapper = $(html).insertAfter(frm.pr_flow_wrapper);

	wire_log_table_events(frm);
}

function build_table_html(rows) {
	const body = rows
		.map((r) => {
			const is_promoted = r.result === "Promoted";
			const can_select = !is_promoted;
			const badge_class = r.resolved ? "resolved" : status_class_for_result(r.result);
			const badge_label = r.resolved ? `${__("Resolved")} · ${r.resolution_action || ""}` : r.result;

			const reason_html = r.reason_code || r.reason_detail
				? `<div class="pr-reason-text"><b>${frappe.utils.escape_html(r.reason_code || "")}</b>${
					r.reason_detail ? ` — ${frappe.utils.escape_html((r.reason_detail || "").split("\n")[0])}` : ""
				  }</div>`
				: "";

			let action_html = "";
			if (is_promoted) {
				action_html = `<span class="pr-resolved-note">${__("Enrolled in")} ${frappe.utils.escape_html(r.to_enrollment || "")}</span>`;
			} else if (r.resolved) {
				action_html = `<span class="pr-resolved-note">${__("by")} ${frappe.utils.escape_html(r.resolved_by || "")}</span>`;
			} else {
				action_html = `
					<div class="pr-row-actions">
						<button class="pr-btn-promote" data-action="promote" data-row="${r.name}">${__("Promote Anyway")}</button>
						<button class="pr-btn-exempt" data-action="exempt" data-row="${r.name}">${__("Mark Exempt")}</button>
					</div>
				`;
			}

			return `
				<tr data-row-name="${r.name}" class="${r.resolved ? "resolved-row" : ""}">
					<td class="pr-row-check">
						${can_select ? `<input type="checkbox" class="pr-row-checkbox" data-row="${r.name}">` : ""}
					</td>
					<td>
						<div class="pr-student-name">${frappe.utils.escape_html(r.student_name || r.student)}</div>
						<div class="pr-student-id">${frappe.utils.escape_html(r.student)}</div>
					</td>
					<td><span class="pr-badge ${badge_class}">${frappe.utils.escape_html(badge_label)}</span></td>
					<td>${reason_html}</td>
					<td>${action_html}</td>
				</tr>
			`;
		})
		.join("");

	return `
		<table class="pr-table">
			<thead>
				<tr>
					<th></th>
					<th>${__("Student")}</th>
					<th>${__("Result")}</th>
					<th>${__("Reason")}</th>
					<th>${__("Action")}</th>
				</tr>
			</thead>
			<tbody>${body}</tbody>
		</table>
	`;
}

function status_class_for_result(result) {
	if (result === "Promoted") return "promoted";
	if (result === "Failed") return "failed";
	return "skipped";
}

function wire_log_table_events(frm) {
	const $wrap = frm.pr_log_wrapper;

	$wrap.find(".pr-btn-promote").on("click", function () {
		const row_name = $(this).data("row");
		const row = (frm.doc.log || []).find((r) => r.name === row_name);
		frappe.confirm(
			__("Promote {0}, overriding the policy check?", [row ? row.student_name : row_name]),
			() => {
				frappe.call({
					method: "slcm.slcm.doctype.promotion_run.promotion_run.promote_anyway",
					args: { promotion_run_name: frm.doc.name, log_row_name: row_name },
					freeze: true,
					callback: (r) => {
						if (!r.message) return;
						frappe.show_alert({ message: __("Promoted"), indicator: "green" });
						frm.reload_doc();
					},
				});
			}
		);
	});

	$wrap.find(".pr-btn-exempt").on("click", function () {
		const row_name = $(this).data("row");
		frappe.prompt(
			{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text" },
			(values) => {
				frappe.call({
					method: "slcm.slcm.doctype.promotion_run.promotion_run.mark_as_exempt",
					args: { promotion_run_name: frm.doc.name, log_row_name: row_name, reason: values.reason },
					freeze: true,
					callback: (r) => {
						if (!r.message) return;
						frappe.show_alert({ message: __("Marked exempt"), indicator: "blue" });
						frm.reload_doc();
					},
				});
			},
			__("Mark as Exempt")
		);
	});

	$wrap.find(".pr-select-all-btn").on("click", () => {
		$wrap.find(".pr-row-checkbox").prop("checked", true);
	});

	$wrap.find(".pr-bulk-promote-btn").on("click", () => {
		const selected = $wrap.find(".pr-row-checkbox:checked").map(function () {
			return $(this).data("row");
		}).get();
		if (!selected.length) {
			frappe.msgprint(__("Select one or more Skipped rows first."));
			return;
		}
		frappe.confirm(__("Promote {0} selected student(s), overriding policy checks?", [selected.length]), () => {
			frappe.call({
				method: "slcm.slcm.doctype.promotion_run.promotion_run.bulk_resolve",
				args: { promotion_run_name: frm.doc.name, log_row_names: selected, action: "promote" },
				freeze: true,
				callback: (r) => {
					if (!r.message) return;
					frappe.show_alert({
						message: __("{0} promoted, {1} failed", [r.message.succeeded.length, r.message.failed.length]),
						indicator: r.message.failed.length ? "orange" : "green",
					});
					frm.reload_doc();
				},
			});
		});
	});

	$wrap.find(".pr-bulk-exempt-btn").on("click", () => {
		const selected = $wrap.find(".pr-row-checkbox:checked").map(function () {
			return $(this).data("row");
		}).get();
		if (!selected.length) {
			frappe.msgprint(__("Select one or more Skipped rows first."));
			return;
		}
		frappe.prompt(
			{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text" },
			(values) => {
				frappe.call({
					method: "slcm.slcm.doctype.promotion_run.promotion_run.bulk_resolve",
					args: { promotion_run_name: frm.doc.name, log_row_names: selected, action: "exempt", reason: values.reason },
					freeze: true,
					callback: (r) => {
						if (!r.message) return;
						frappe.show_alert({ message: __("{0} marked exempt", [r.message.succeeded.length]), indicator: "green" });
						frm.reload_doc();
					},
				});
			},
			__("Mark as Exempt")
		);
	});
}

/*****************************************************
 * REALTIME
 *****************************************************/
function watch_run(frm) {
	frappe.realtime.on("promotion_run_complete", (data) => {
		if (data.promotion_run !== frm.doc.name) return;
		frappe.show_alert({
			message: __("Promotion Run {0} finished: {1}", [frm.doc.name, data.status]),
			indicator: data.status === "Error" ? "red" : "green",
		}, 8);
		frappe.realtime.off("promotion_run_complete");
		frm.reload_doc();
	});
}
