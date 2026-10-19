const FD_EVENT_DEMAND_DOCTYPES = [
	"Hostel Fine",
	"Discipline Order",
	"Deferral Order",
	"Convocation Registration",
	"Re Exam Registration",
	"Revaluation Request",
	"Course Reregistration",
];

frappe.ui.form.on("Fee Demand", {
	setup(frm) {
		// Student ID: search by ID, name, Registration Id, Application Number or email
		frm.set_query("student", () => ({ query: "slcm.slcm.doctype.fee_concession.fee_concession.student_query" }));
	},

	refresh(frm) {
		frm.trigger("set_status_indicator");
		frm.trigger("render_action_buttons");
		frm.trigger("render_create_buttons");
	},

	set_status_indicator(frm) {
		const colors = {
			"Pending": "orange",
			"Partially Paid": "blue",
			"Paid": "green",
			"Overdue": "red",
			"Waived": "purple",
			"Moved to Excess": "cyan",
			"Cancelled": "grey",
		};
		if (frm.doc.status === "Cancelled" && flt(frm.doc.moved_to_excess_amount) > 0) {
			frm.page.set_indicator(__("Cancelled & Moved to Excess"), "grey");
		} else if (frm.doc.status) {
			frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "grey");
		}
	},

	render_action_buttons(frm) {
		if (frm.is_new()) return;

		const cancelable = !["Paid", "Cancelled"].includes(frm.doc.status);
		const editable = !["Paid", "Waived", "Cancelled"].includes(frm.doc.status);

		if (cancelable && frappe.user.has_role(["System Manager", "Campus Admin"])) {
			frm.add_custom_button(__("Cancel Demand"), () => {
				frappe.confirm(
					__("Are you sure you want to cancel this fee demand? This action cannot be undone."),
					() => {
						frm.call("cancel_demand").then(() => frm.reload_doc());
					}
				);
			}, __("Actions"));
		}

		// ── Mark Dues Cleared (single) ──────────────────────────────────────
		const clearable = !["Paid", "Cancelled", "Waived"].includes(frm.doc.status)
			&& flt(frm.doc.outstanding_amount) > 0;
		if (clearable && frappe.user.has_role(["System Manager", "Campus Admin"])) {
			frm.add_custom_button(__("Mark Dues Cleared"), () => {
				_fd_open_mark_cleared_dialog([frm.doc.name], () => frm.reload_doc());
			}, __("Actions"));
		}

		// ── Download Receipt button (only when paid) ───────────────────────
		if (["Paid", "Partially Paid"].includes(frm.doc.status)) {
			const rcpt_btn = frm.add_custom_button(__("⬇ Download Receipt"), () => {
				frappe.show_alert({ message: __("Preparing receipt…"), indicator: "blue" });
				frappe.call({
					method: "slcm.slcm.doctype.student_master.student_master.get_fee_demand_receipt",
					args:   { fee_demand_name: frm.doc.name },
					callback(r) {
						const info = r.message;
						if (!info || !info.receipt) {
							frappe.msgprint({
								title:     __("Receipt Not Found"),
								message:   __("No receipt has been generated for this demand yet."),
								indicator: "orange",
							});
							return;
						}
						const csrf = frappe.csrf_token || "";
						const url  = `/api/method/slcm.api.student_portal.download_fee_demand_receipt_admin`
						           + `?receipt_name=${encodeURIComponent(info.receipt)}`
						           + `&fee_demand_name=${encodeURIComponent(info.fee_demand)}`
						           + (csrf ? `&X-Frappe-CSRF-Token=${encodeURIComponent(csrf)}` : "");
						window.open(url, "_blank");
					},
					error() {
						frappe.show_alert({ message: __("Failed to fetch receipt."), indicator: "red" });
					},
				});
			});
			rcpt_btn.css({
				"background-color": "#7c3aed",
				"color":            "#fff",
				"border-color":     "#7c3aed",
				"font-weight":      "600",
			});
		}

		// Show outstanding amount prominently
		if (frm.doc.outstanding_amount > 0) {
			frm.dashboard.add_comment(
				__("Outstanding: <strong>₹{0}</strong> | Due Date: <strong>{1}</strong>",
					[
						format_currency(frm.doc.outstanding_amount, "INR"),
						frappe.datetime.str_to_user(frm.doc.due_date)
					]
				),
				frm.doc.status === "Overdue" ? "red" : "blue",
				true
			);
		}
	},

	student(frm) {
		if (frm.doc.student) {
			frappe.db.get_value(
				"Student Master",
				frm.doc.student,
				["academic_year"],
				(r) => {
					if (r && r.academic_year && !frm.doc.academic_year) {
						frm.set_value("academic_year", r.academic_year);
					}
				}
			);
		}
		frm.trigger("render_create_buttons");
	},

	render_create_buttons(frm) {
		if (!frm.doc.student) return;

		// ── Fee Concession / Waiver — needs a saved Fee Demand to link against ──
		const editable = !["Paid", "Waived", "Cancelled"].includes(frm.doc.status);
		if (!frm.is_new() && editable) {
			frm.add_custom_button(__("Fee Concession / Waiver"), () => {
				frappe.new_doc("Fee Concession", {
					student: frm.doc.student,
					fee_demand: frm.doc.name,
				});
			}, __("Create"));
		}

		// ── Event-Triggered Demand sources — just need the student ──────────────
		FD_EVENT_DEMAND_DOCTYPES.forEach((dt) => {
			frm.add_custom_button(__(dt), () => {
				frappe.new_doc(dt, { student: frm.doc.student });
			}, __("Create Event Demand"));
		});
	},

	fee_component(frm) {
		if (frm.doc.fee_component && !frm.doc.description) {
			frm.set_value("description", frm.doc.fee_component);
		}
		// Demand Type comes from the Fee Component (fetch_from fee_component.demand_type)
	},

	original_amount(frm) {

		frm.trigger("recalculate_amounts");
	},

	waiver_amount(frm) {
		if (flt(frm.doc.waiver_amount) > flt(frm.doc.original_amount)) {
			frappe.msgprint({
				message: __("Waiver Amount cannot exceed Original Amount."),
				indicator: "red",
			});
			frm.set_value("waiver_amount", frm.doc.original_amount);
			return;
		}
		frm.trigger("recalculate_amounts");

		// Warn if editing a demand with existing payments
		if (flt(frm.doc.paid_amount) > 0) {
			frappe.show_alert({
				message: __("This demand already has payments recorded. "
					+ "Changing the waiver will update the outstanding amount."),
				indicator: "orange",
			});
		}
	},

	penalty_amount(frm) {
		frm.trigger("recalculate_amounts");
	},

	recalculate_amounts(frm) {
		const original = flt(frm.doc.original_amount);
		const waiver   = flt(frm.doc.waiver_amount);
		const penalty  = flt(frm.doc.penalty_amount);
		const paid     = flt(frm.doc.paid_amount);
		const credit   = flt(frm.doc.credit_adjusted);

		const net_payable = original - waiver + penalty;
		const outstanding = Math.max(0, net_payable - paid - credit);

		frm.set_value("net_payable", net_payable);
		frm.set_value("outstanding_amount", outstanding);
	},
});

/* ── Fee Demand — Payment Logs Dialog ────────────────────────────────────────
   Self-contained: all render helpers are local (_fd_ prefix) so this file has
   no dependency on student_master.js globals.
────────────────────────────────────────────────────────────────────────────── */
function _show_demand_payment_logs_dialog(frm) {
	const demand_label = frm.doc.description || frm.doc.fee_component || frm.doc.name;

	const dialog = new frappe.ui.Dialog({
		title:  __("Payment Logs — {0}", [demand_label]),
		size:   "extra-large",
		fields: [
			{ fieldtype: "HTML", fieldname: "analytics_html" },
			{ fieldtype: "HTML", fieldname: "logs_html" },
		],
	});
	dialog.$wrapper.find(".modal-dialog").css({ "max-width": "960px" });
	dialog.show();

	dialog.fields_dict.analytics_html.$wrapper.html(
		`<div style="text-align:center;padding:40px 0;color:#6b7280;">
			<div style="font-size:24px;margin-bottom:8px;">⏳</div>
			<div>Loading payment history…</div></div>`
	);

	frappe.call({
		method: "slcm.slcm.doctype.student_master.student_master.get_fee_demand_payment_logs",
		args:   { fee_demand_name: frm.doc.name },
		callback(r) {
			const data      = r.message || {};
			const logs      = data.logs      || [];
			const analytics = data.analytics || {};

			dialog.fields_dict.analytics_html.$wrapper.html(_fd_render_analytics(analytics));

			const $wrap = dialog.fields_dict.logs_html.$wrapper;
			$wrap.html(_fd_render_timeline(logs));

			function _apply() {
				const q      = ($wrap.find("#plog-search").val() || "").toLowerCase().trim();
				const status = $wrap.find("#plog-filter-status").val() || "";
				let visible  = 0;
				$wrap.find(".plog-item").each(function () {
					const text = (this.getAttribute("data-search-text") || "").toLowerCase();
					const evt  = this.getAttribute("data-event") || "";
					const show = (!q || text.indexOf(q) !== -1) && (!status || evt === status);
					$(this).toggleClass("hidden", !show);
					if (show) visible++;
				});
				$wrap.find("#plog-no-results").toggle(visible === 0 && logs.length > 0);
			}

			$wrap.on("input",  "#plog-search",        _apply);
			$wrap.on("change", "#plog-filter-status", _apply);

			$wrap.on("click", ".plog-toggle-json", function () {
				const $block = $wrap.find("#" + $(this).data("target"));
				const isOpen = $block.is(":visible");
				$block.toggle(!isOpen);
				$(this).text(isOpen ? "▶ Show Gateway Response" : "▼ Hide Gateway Response");
			});

			$wrap.on("click", "#plog-download-csv", function () {
				_fd_download_csv(logs, demand_label);
			});

			$wrap.on("click", ".plog-download-demand-receipt", function () {
				const btn      = $(this);
				const dem_name = btn.data("demand");
				if (!dem_name) return;
				const orig = btn.html();
				btn.prop("disabled", true).text("…");
				frappe.call({
					method: "slcm.slcm.doctype.student_master.student_master.get_fee_demand_receipt",
					args:   { fee_demand_name: dem_name },
					callback(r2) {
						const info = r2.message;
						if (!info || !info.receipt) {
							frappe.msgprint({ title: __("Receipt Not Found"),
								message: __("No receipt has been generated for this demand yet."),
								indicator: "orange" });
							btn.html(orig).prop("disabled", false);
							return;
						}
						const csrf = frappe.csrf_token || "";
						const url  = `/api/method/slcm.api.student_portal.download_fee_demand_receipt_admin`
						           + `?receipt_name=${encodeURIComponent(info.receipt)}`
						           + `&fee_demand_name=${encodeURIComponent(info.fee_demand)}`
						           + (csrf ? `&X-Frappe-CSRF-Token=${encodeURIComponent(csrf)}` : "");
						window.open(url, "_blank");
						frappe.show_alert({ message: `Downloading receipt for ${dem_name}…`, indicator: "blue" });
						setTimeout(() => {
							btn.html("✔ Done").css("background", "#16a34a");
							setTimeout(() => { btn.html(orig).css("background", "#7c3aed").prop("disabled", false); }, 2500);
						}, 600);
					},
					error() {
						frappe.show_alert({ message: __("Failed to find receipt."), indicator: "red" });
						btn.html(orig).prop("disabled", false);
					},
				});
			});

			_apply();
		},
		error() {
			dialog.fields_dict.analytics_html.$wrapper.html(
				`<div style="color:#dc2626;padding:12px;">Failed to load payment logs.</div>`
			);
		},
	});
}

/* ── Mark Dues Cleared — shared dialog (used by form + list view) ──────────── */
function _fd_open_mark_cleared_dialog(demand_names, on_done) {
	if (!demand_names || !demand_names.length) return;

	const dialog = new frappe.ui.Dialog({
		title: __("Mark Dues Cleared — {0} Demand(s)", [demand_names.length]),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "info_html",
				options: `<div style="margin-bottom:10px;color:#6b7280;font-size:13px;">
					${__("This records a Fee Payment for the outstanding amount of the selected "
						+ "demand(s) and submits it, so status, receipts and payment history stay "
						+ "consistent with the normal payment flow.")}
				</div>`,
			},
			{
				fieldtype: "Select",
				fieldname: "payment_mode",
				label: __("Payment Mode"),
				options: ["Cash", "Bank Transfer", "Cheque", "Credit Card", "Debit Card", "Online Payment", "Other"],
				default: "Cash",
				reqd: 1,
			},
			{
				fieldtype: "Small Text",
				fieldname: "remarks",
				label: __("Remarks"),
				default: __("Dues marked cleared administratively."),
			},
		],
		primary_action_label: __("Mark Cleared"),
		primary_action(values) {
			dialog.set_primary_action(__("Processing…"), () => {});
			frappe.call({
				method: "slcm.slcm.doctype.fee_demand.fee_demand.mark_dues_cleared",
				args: {
					demand_names: demand_names,
					payment_mode: values.payment_mode,
					remarks: values.remarks,
				},
				callback(r) {
					dialog.hide();
					const res = r.message || {};
					const cleared = res.cleared_demands || [];
					const skipped = res.skipped_demands || [];
					let msg = __("{0} demand(s) marked cleared via {1} payment(s).",
						[cleared.length, (res.created_payments || []).length]);
					if (skipped.length) {
						msg += " " + __("{0} demand(s) were skipped (already settled).", [skipped.length]);
					}
					frappe.show_alert({ message: msg, indicator: "green" });
					if (on_done) on_done(res);
				},
				error() {
					dialog.set_primary_action(__("Mark Cleared"), () => dialog.primary_action(dialog.get_values()));
				},
			});
		},
	});
	dialog.show();
}

// ── Local render helpers (no dependency on student_master.js) ─────────────────

function _fd_render_analytics(a) {
	if (!a || !a.total_attempts) {
		return `<div style="padding:12px 0 4px;color:#6b7280;font-style:italic;font-size:13px;">
			No payment activity recorded yet.</div>`;
	}
	const last_ts = a.last_attempt ? frappe.datetime.str_to_user(a.last_attempt) : "—";
	const tiles = [
		{ label: "Total Attempts", value: a.total_attempts, color: "#1e40af", bg: "#dbeafe" },
		{ label: "Successful",     value: a.successful,     color: "#166534", bg: "#dcfce7" },
		{ label: "Failed",         value: a.failed,         color: "#991b1b", bg: "#fee2e2" },
		{ label: "Cancelled",      value: a.cancelled,      color: "#92400e", bg: "#fef3c7" },
		{ label: "Refunded",       value: a.refunded,       color: "#4b5563", bg: "#f3f4f6" },
	];
	const tiles_html = tiles.map(t => `
		<div style="background:${t.bg};border-radius:10px;padding:14px 18px;text-align:center;min-width:100px;flex:1;">
			<div style="font-size:22px;font-weight:800;color:${t.color};">${t.value}</div>
			<div style="font-size:11px;color:${t.color};font-weight:600;margin-top:2px;">${t.label}</div>
		</div>`).join("");
	return `
	<div style="padding:4px 0 8px;">
		<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
			<span style="font-size:14px;font-weight:700;color:#374151;">Payment Analytics</span>
			<span style="font-size:12px;color:#6b7280;">Last attempt: ${last_ts}</span>
		</div>
		<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;">${tiles_html}</div>
	</div>`;
}

const _FD_PLOG_STYLE = {
	"Payment Initiated":    { icon: "🚀", dot: "#3b82f6", badge_bg: "#dbeafe", badge_text: "#1e40af" },
	"Captured":             { icon: "💰", dot: "#16a34a", badge_bg: "#dcfce7", badge_text: "#166534" },
	"Payment Recorded":     { icon: "💰", dot: "#16a34a", badge_bg: "#dcfce7", badge_text: "#166534" },
	"Payment Failed":       { icon: "❌", dot: "#ef4444", badge_bg: "#fee2e2", badge_text: "#991b1b" },
	"Payment Cancelled":    { icon: "🚫", dot: "#f59e0b", badge_bg: "#fef3c7", badge_text: "#92400e" },
	"Refunded":             { icon: "↩️", dot: "#6366f1", badge_bg: "#ede9fe", badge_text: "#4c1d95" },
	"Pending Verification": { icon: "⏳", dot: "#a855f7", badge_bg: "#f3e8ff", badge_text: "#581c87" },
	"Webhook Received":     { icon: "🔔", dot: "#06b6d4", badge_bg: "#cffafe", badge_text: "#155e75" },
	"Manual Status Update": { icon: "✏️", dot: "#6b7280", badge_bg: "#f3f4f6", badge_text: "#374151" },
};

function _fd_render_timeline(logs) {
	if (!logs || !logs.length) {
		return `<div style="text-align:center;padding:40px 0;color:#6b7280;">
			<div style="font-size:32px;margin-bottom:8px;">📭</div>
			<div style="font-size:15px;font-weight:600;">No payment logs found</div>
			<div style="font-size:12px;margin-top:4px;">Payment activity will appear here once initiated.</div>
		</div>`;
	}

	const toolbar = `
	<div style="display:flex;gap:10px;align-items:center;margin-bottom:14px;flex-wrap:wrap;">
		<input id="plog-search" type="text" placeholder="🔍 Search by event, payment ID…"
		       style="flex:1;min-width:220px;border:1px solid #d1d5db;border-radius:8px;
		              padding:7px 12px;font-size:13px;outline:none;"/>
		<select id="plog-filter-status"
		        style="border:1px solid #d1d5db;border-radius:8px;padding:7px 12px;
		               font-size:13px;outline:none;background:#fff;cursor:pointer;">
			<option value="">All Events</option>
			<option value="Payment Initiated">Payment Initiated</option>
			<option value="Captured">Captured / Paid</option>
			<option value="Payment Failed">Payment Failed</option>
			<option value="Payment Cancelled">Cancelled</option>
			<option value="Refunded">Refunded</option>
		</select>
		<button id="plog-download-csv"
		        style="background:#374151;color:#fff;border:none;border-radius:8px;
		               padding:7px 14px;font-size:13px;cursor:pointer;font-weight:600;white-space:nowrap;">
			⬇ Export CSV
		</button>
	</div>`;

	const items_html = logs.map((row, idx) => {
		const style      = _FD_PLOG_STYLE[row.event_type] || _FD_PLOG_STYLE["Manual Status Update"];
		const ts         = row.timestamp ? frappe.datetime.str_to_user(row.timestamp) : "—";
		const amount_str = row.amount
			? "₹" + parseFloat(row.amount).toLocaleString("en-IN", { minimumFractionDigits: 0 })
			: "";
		const badge_html = `<span style="display:inline-block;background:${style.badge_bg};
			color:${style.badge_text};padding:2px 10px;border-radius:20px;
			font-size:11px;font-weight:700;white-space:nowrap;">${row.event_type}</span>`;

		const is_captured = ["Captured", "Payment Recorded"].includes(row.event_type);
		const receipt_btn = is_captured
			? `<button class="plog-download-demand-receipt" data-demand="${row.fee_demand}"
				style="margin-top:8px;background:#7c3aed;color:#fff;border:none;border-radius:6px;
				       padding:4px 12px;font-size:11px;cursor:pointer;font-weight:600;margin-left:4px;">
				🧾 Download Receipt</button>`
			: "";

		// Payer badge
		let payer_html = "";
		if (row.paid_by_role || row.paid_by_name) {
			const role_colors = {
				"Parent":  { bg: "#fef3c7", text: "#92400e", icon: "👨‍👩‍👧" },
				"Student": { bg: "#dbeafe", text: "#1e40af", icon: "🎓" },
				"Staff":   { bg: "#d1fae5", text: "#065f46", icon: "🏫" },
				"System":  { bg: "#f3f4f6", text: "#374151", icon: "⚙️" },
			};
			const rc = role_colors[row.paid_by_role] || { bg: "#f3f4f6", text: "#374151", icon: "👤" };
			const role_label = row.paid_by_role ? `${rc.icon} ${row.paid_by_role}` : "👤 Unknown";
			const name_part  = row.paid_by_name  ? ` — ${frappe.utils.escape_html(row.paid_by_name)}` : "";
			payer_html = `<span style="display:inline-block;background:${rc.bg};color:${rc.text};
				padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;
				white-space:nowrap;margin-left:6px;">${role_label}${name_part}</span>`;
		}

		let chips = [];
		if (row.fee_demand)           chips.push(`<span class="plog-chip">📋 ${row.fee_demand}</span>`);
		if (row.razorpay_payment_id)  chips.push(`<span class="plog-chip">💳 ${row.razorpay_payment_id}</span>`);
		if (row.razorpay_order_id)    chips.push(`<span class="plog-chip">🗂 ${row.razorpay_order_id}</span>`);
		if (row.payment_mode)         chips.push(`<span class="plog-chip">🏦 ${row.payment_mode}</span>`);
		if (row.retry_count > 0)      chips.push(`<span class="plog-chip">🔁 Retry #${row.retry_count}</span>`);
		if (row.ip_address)           chips.push(`<span class="plog-chip">🌐 ${row.ip_address}</span>`);
		if (row.triggered_by)         chips.push(`<span class="plog-chip">👤 ${row.triggered_by}</span>`);

		let transition = "";
		if (row.from_status || row.to_status) {
			transition = `<div style="font-size:11px;margin-top:6px;color:#6b7280;">
				<span>${row.from_status || "—"}</span>
				<span style="margin:0 6px;color:#9ca3af;">→</span>
				<span style="font-weight:600;">${row.to_status || "—"}</span>
			</div>`;
		}

		const remarks_html = row.remarks
			? `<div style="font-size:12px;color:#6b7280;margin-top:5px;font-style:italic;">${row.remarks}</div>`
			: "";

		const json_id = `plog-json-${idx}`;
		let toggle_html = "", json_html = "";
		if (row.gateway_response) {
			let pretty = row.gateway_response;
			try { pretty = JSON.stringify(JSON.parse(row.gateway_response), null, 2); } catch(e) {}
			toggle_html = `<button class="plog-toggle-json" data-target="${json_id}"
				style="margin-top:8px;background:none;border:1px solid #d1d5db;border-radius:6px;
				       padding:3px 10px;font-size:11px;cursor:pointer;color:#374151;font-weight:500;">
				▶ Show Gateway Response</button>`;
			json_html = `<div id="${json_id}" style="display:none;margin-top:6px;">
				<pre style="background:#1e293b;color:#e2e8f0;padding:12px;border-radius:8px;
				            font-size:11px;overflow-x:auto;max-height:240px;white-space:pre-wrap;
				            word-break:break-all;">${frappe.utils.escape_html(pretty)}</pre>
			</div>`;
		}

		const line_display = idx === logs.length - 1 ? "none" : "block";
		const search_text  = [row.event_type, row.fee_demand, row.razorpay_payment_id,
		                       row.transaction_id, row.paid_by_role, row.paid_by_name, row.remarks]
		                     .filter(Boolean).join(" ").toLowerCase()
		                     .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

		return `
		<div class="plog-item" data-event="${row.event_type}" data-search-text="${search_text}"
		     style="display:flex;gap:0;margin-bottom:0;">
			<div style="display:flex;flex-direction:column;align-items:center;width:28px;flex-shrink:0;">
				<div style="width:14px;height:14px;border-radius:50%;background:#7c3aed;
				            margin-top:14px;flex-shrink:0;box-shadow:0 0 0 3px #7c3aed22;"></div>
				<div style="width:2px;flex:1;background:#e5e7eb;display:${line_display};min-height:20px;"></div>
			</div>
			<div style="flex:1;background:#faf5ff;border:1px solid #ddd6fe;border-radius:10px;
			            padding:12px 16px;margin:6px 0 6px 10px;box-shadow:0 1px 3px rgba(0,0,0,.06);">
				<div style="display:flex;justify-content:space-between;align-items:flex-start;
				            flex-wrap:wrap;gap:8px;">
					<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
						<span style="font-size:16px;">${style.icon}</span>
						${badge_html}
						${payer_html}
						${amount_str ? `<span style="font-weight:700;font-size:14px;color:#1f2937;">${amount_str}</span>` : ""}
					</div>
					<div style="display:flex;align-items:center;gap:6px;">
						${receipt_btn}
						<span style="font-size:11px;color:#9ca3af;white-space:nowrap;">${ts}</span>
					</div>
				</div>
				${transition}
				${chips.length ? `<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;">${chips.join("")}</div>` : ""}
				${remarks_html}
				${toggle_html}
				${json_html}
			</div>
		</div>`;
	}).join("");

	return `
	<style>
		.plog-chip { background:#f3f4f6;color:#374151;padding:2px 8px;border-radius:20px;
		             font-size:11px;font-weight:500;white-space:nowrap; }
		.plog-item.hidden { display:none !important; }
	</style>
	${toolbar}
	<div style="padding:4px 0;">${items_html}</div>
	<div id="plog-no-results" style="display:none;text-align:center;padding:30px 0;color:#6b7280;">
		No matching entries found.
	</div>`;
}

function _fd_download_csv(logs, label) {
	if (!logs || !logs.length) {
		frappe.show_alert({ message: __("No logs to export."), indicator: "orange" });
		return;
	}
	const cols = ["event_type", "timestamp", "amount", "fee_demand", "payment_mode",
	              "paid_by_role", "paid_by_name",
	              "razorpay_payment_id", "razorpay_order_id", "from_status", "to_status",
	              "ip_address", "remarks"];
	const esc    = v => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
	const header = cols.map(c => esc(c.replace(/_/g, " ").toUpperCase())).join(",");
	const body   = logs.map(r => cols.map(c => esc(r[c] ?? "")).join(",")).join("\n");
	const blob   = new Blob([header + "\n" + body], { type: "text/csv;charset=utf-8;" });
	const url    = URL.createObjectURL(blob);
	const a      = document.createElement("a");
	a.href = url;
	a.download = `payment_logs_${(label || "demand").replace(/\s+/g, "_")}.csv`;
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	URL.revokeObjectURL(url);
}
