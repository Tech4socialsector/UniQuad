frappe.listview_settings["Fee Demand"] = {
	add_fields: ["status", "moved_to_excess_amount"],
	get_indicator(doc) {
		const colors = {
			Pending: "orange",
			"Partially Paid": "blue",
			Paid: "green",
			Overdue: "red",
			Waived: "purple",
			"Moved to Excess": "cyan",
			Cancelled: "gray",
		};
		if (doc.status === "Cancelled" && flt(doc.moved_to_excess_amount) > 0) {
			return [__("Cancelled & Moved to Excess"), "gray", "status,=,Cancelled"];
		}
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
	onload(listview) {
		if (!frappe.user.has_role(["System Manager", "Campus Admin"])) return;

		listview.page.add_inner_button(__("Mark Dues Cleared"), () => {
			const selected = listview.get_checked_items();
			if (!selected.length) {
				frappe.msgprint(__("Please select at least one Fee Demand record."));
				return;
			}

			const clearable = selected.filter(
				(d) => !["Paid", "Cancelled", "Waived"].includes(d.status) && flt(d.outstanding_amount) > 0
			);
			if (!clearable.length) {
				frappe.msgprint(__("None of the selected demands have an outstanding amount to clear."));
				return;
			}

			frappe.confirm(
				__("Mark {0} of {1} selected demand(s) as cleared? This records a Fee Payment for the outstanding amount of each.",
					[clearable.length, selected.length]),
				() => {
					_fd_list_open_mark_cleared_dialog(clearable.map((d) => d.name), () => listview.refresh());
				}
			);
		});

		listview.page.add_inner_button(__("Apply Fee Concession / Waiver"), () => {
			const selected = listview.get_checked_items();
			if (!selected.length) {
				frappe.msgprint(__("Please select at least one Fee Demand record."));
				return;
			}

			const eligible = selected.filter(
				(d) => !["Paid", "Cancelled", "Waived"].includes(d.status) && flt(d.outstanding_amount) > 0
			);
			if (!eligible.length) {
				frappe.msgprint(__("None of the selected demands are eligible for a concession."));
				return;
			}

			_fd_list_open_bulk_concession_dialog(eligible.map((d) => d.name), () => listview.refresh());
		});
	},
};

/* ── Apply Fee Concession / Waiver (bulk) ────────────────────────────────── */
async function _fd_list_open_bulk_concession_dialog(demand_names, on_done) {
	if (!demand_names || !demand_names.length) return;

	// Concession types come from the Fee Concession doctype, so edits there show up here.
	await frappe.model.with_doctype("Fee Concession");
	const type_options = ((frappe.meta.get_docfield("Fee Concession", "concession_type") || {}).options || "").split("\n");

	const dialog = new frappe.ui.Dialog({
		title: __("Apply Fee Concession / Waiver — {0} Demand(s)", [demand_names.length]),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "info_html",
				options: `<div style="margin-bottom:10px;color:#6b7280;font-size:13px;">
					${__("This creates and submits a separate Fee Concession for each selected demand, "
						+ "using the same rule below. Demands that are already settled or already have "
						+ "an approved concession will be skipped.")}
				</div>`,
			},
			{
				fieldtype: "Select",
				fieldname: "concession_type",
				label: __("Concession Type"),
				options: type_options,
				reqd: 1,
			},
			{
				fieldtype: "Column Break",
			},
			{
				fieldtype: "Currency",
				fieldname: "waiver_value",
				label: __("Waiver Value"),
				options: "INR",
				description: __("Amount (₹) waived on each selected demand"),
				reqd: 1,
			},
			{
				fieldtype: "Section Break",
			},
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Reason"),
				reqd: 1,
			},
		],
		primary_action_label: __("Apply"),
		primary_action(values) {
			dialog.set_primary_action(__("Processing…"), () => {});
			frappe.call({
				method: "slcm.slcm.doctype.fee_concession.fee_concession.bulk_apply_concession",
				args: {
					demand_names: demand_names,
					concession_type: values.concession_type,
					waiver_value: values.waiver_value,
					reason: values.reason,
				},
				callback(r) {
					dialog.hide();
					const res = r.message || {};
					const created = res.created || [];
					const skipped = res.skipped || [];
					let msg = __("{0} Fee Concession(s) created and applied.", [created.length]);
					if (skipped.length) {
						msg += " " + __("{0} demand(s) were skipped.", [skipped.length]);
					}
					frappe.show_alert({ message: msg, indicator: created.length ? "green" : "orange" });
					if (skipped.length) {
						const rows = skipped.map((s) => `<li>${s.name}: ${s.reason}</li>`).join("");
						frappe.msgprint({
							title: __("Some demands were skipped"),
							message: `<ul>${rows}</ul>`,
							indicator: "orange",
						});
					}
					if (on_done) on_done(res);
				},
				error() {
					dialog.set_primary_action(__("Apply"), () => dialog.primary_action(dialog.get_values()));
				},
			});
		},
	});
	dialog.show();
}

/* ── Mark Dues Cleared dialog — self-contained copy for the list view ──────
   (fee_demand.js, which defines the form-side version, is not loaded here) */
function _fd_list_open_mark_cleared_dialog(demand_names, on_done) {
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
