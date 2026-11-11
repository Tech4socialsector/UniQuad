// SLCM Fee Accounting section on ERPNext's Company form (loaded only where ERPNext provides Company).

function show_fee_mapping(frm) {
	frappe
		.call({ method: "slcm.erpnext_bridge.company.fee_mapping", args: { company: frm.doc.name }, freeze: true })
		.then(({ message }) => {
			const esc = frappe.utils.escape_html;
			const unmapped = message.rows.filter((r) => !r.ok).length;
			const rows = message.rows
				.map(
					(r) => `<tr>
						<td>${esc(r.name)}</td>
						<td class="text-muted">${esc(r.source)}</td>
						<td>${r.account ? frappe.utils.get_form_link("Account", r.account, true, esc(r.account)) : "-"}</td>
						<td><span class="indicator-pill ${r.ok ? "green" : r.account ? "orange" : "red"}">${esc(r.status)}</span></td>
					</tr>`
				)
				.join("");
			const d = new frappe.ui.Dialog({
				title: __("SLCM Fee Mapping - {0}", [frm.doc.name]),
				size: "extra-large",
				fields: [{ fieldtype: "HTML", fieldname: "table" }],
				primary_action_label: __("Edit Mapping"),
				primary_action() {
					d.hide();
					map_fee_accounts(frm);
				},
			});
			d.fields_dict.table.$wrapper.html(`
				<p class="text-muted">${
					unmapped
						? __(
								"{0} SLCM fee name(s) have no account of their own. Click Edit Mapping to pick one, or name an Account exactly like the fee.",
								[unmapped]
						  )
						: __("Every SLCM fee name posts to its own account.")
				} ${__("Edit Mapping adds, changes or removes a mapping; a removed one posts to the Default Fee Income Account.")}</p>
				<table class="table table-bordered table-sm">
					<thead><tr><th>${__("SLCM Name")}</th><th>${__("Source")}</th><th>${__("Posts To")}</th><th>${__("Status")}</th></tr></thead>
					<tbody>${rows}</tbody>
				</table>`);
			d.show();
		});
}

function map_fee_accounts(frm) {
	frappe
		.call({ method: "slcm.erpnext_bridge.company.fee_mapping", args: { company: frm.doc.name }, freeze: true })
		.then(({ message }) => {
			const data = message.rows.map((r) => ({
				slcm_name: r.name,
				source: r.source,
				// prefill only real mappings; a fee on the default ledger starts blank
				account: r.ok ? r.account : "",
			}));
			const d = new frappe.ui.Dialog({
				title: __("Map SLCM Fees - {0}", [frm.doc.name]),
				size: "extra-large",
				fields: [
					{
						fieldtype: "HTML",
						options: `<p class="text-muted">${__(
							"Pick the account each SLCM fee posts to. Blank: it posts to the Default Fee Income Account ({0}). An account named exactly like the fee always takes it.",
							[frappe.utils.escape_html(message.default || __("not set - such fees wait"))]
						)}</p>`,
					},
					{
						fieldtype: "Table",
						fieldname: "rows",
						cannot_add_rows: true,
						cannot_delete_rows: true,
						in_place_edit: true,
						data,
						fields: [
							{ fieldtype: "Data", fieldname: "slcm_name", label: __("SLCM Name"), read_only: 1, in_list_view: 1, columns: 4 },
							{ fieldtype: "Data", fieldname: "source", label: __("Source"), read_only: 1, in_list_view: 1, columns: 2 },
							{
								fieldtype: "Link",
								fieldname: "account",
								label: __("Account"),
								options: "Account",
								in_list_view: 1,
								columns: 4,
								get_query: () => ({
									filters: {
										company: frm.doc.name,
										is_group: 0,
										disabled: 0,
										account_type: ["not in", ["Receivable", "Payable"]],
										root_type: ["in", ["Income", "Liability", "Equity"]],
									},
								}),
							},
						],
					},
				],
				primary_action_label: __("Save Mapping"),
				primary_action(values) {
					const mapping = {};
					(values.rows || []).forEach((r) => (mapping[r.slcm_name] = r.account || ""));
					frappe
						.call({
							method: "slcm.erpnext_bridge.company.save_fee_mapping",
							args: { company: frm.doc.name, mapping },
							freeze: true,
						})
						.then((r) => {
							d.hide();
							frappe.show_alert({ message: r.message, indicator: "green" });
							show_fee_mapping(frm);
						});
				},
			});
			d.show();
		});
}

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
		frm.add_custom_button(__("Map SLCM Fees"), () => map_fee_accounts(frm), group);
		frm.add_custom_button(__("Check Fee Mapping"), () => show_fee_mapping(frm), group);
		frm.add_custom_button(
			__("Fee Reconciliation"),
			() => frappe.set_route("query-report", "SLCM ERPNext Reconciliation"),
			group
		);
	},
});
