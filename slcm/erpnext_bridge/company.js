// SLCM Fee Accounting section on ERPNext's Company form (loaded only where ERPNext provides Company).

frappe.ui.form.on("Company", {
	setup(frm) {
		[
			"slcm_default_fee_income_account",
			"slcm_unallocated_fee_account",
			"slcm_output_gst_account",
			"slcm_fee_refund_account",
			"slcm_gateway_charges_account",
			"slcm_gateway_gst_account",
		].forEach((fieldname) =>
			frm.set_query(fieldname, () => ({
				filters: {
					company: frm.doc.name,
					is_group: 0,
					disabled: 0,
					account_type: ["not in", ["Receivable", "Payable"]],
				},
			}))
		);
	},

	refresh(frm) {
		if (frm.is_new() || !frm.fields_dict.slcm_enable_fee_posting) return;
		const group = __("SLCM Fees");
		frm.add_custom_button(
			__("Create SLCM Fee Ledgers"),
			() =>
				frappe.confirm(
					__(
						"Create the SLCM fee ledgers, payment-mode accounts and university bank accounts for {0}? Existing ones are reused.",
						[frm.doc.name]
					),
					() =>
						frappe
							.call({
								method: "slcm.erpnext_bridge.company.create_fee_ledgers",
								args: { company: frm.doc.name },
								freeze: true,
							})
							.then((r) => {
								frappe.msgprint(r.message);
								frm.reload_doc();
							})
				),
			group
		);
		if (frm.doc.slcm_enable_fee_posting) {
			frm.add_custom_button(
				__("Post Pending Fees Now"),
				() =>
					frappe
						.call("slcm.erpnext_bridge.company.post_pending_now")
						.then((r) => frappe.show_alert({ message: r.message, indicator: "green" })),
				group
			);
		}
		frm.add_custom_button(
			__("Fee Reconciliation"),
			() => frappe.set_route("query-report", "SLCM ERPNext Reconciliation"),
			group
		);
	},
});
