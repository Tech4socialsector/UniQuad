(() => {
	frappe.listview_settings["Fee Component"] = {
		onload(listview) {
			listview.page.add_inner_button(__("Change Payment Gateway"), () =>
				change_payment_gateway(listview),
			);

			listview.page.add_inner_button(__("Fetch Default Components"), () => {
				frappe.confirm(
					__(
						"This will create any missing standard Fee Components and update the ledger and demand type of existing ones. Continue?",
					),
					() => {
						frappe.dom.freeze(__("Creating default Fee Components…"));
						frappe.call({
							method: "slcm.slcm.doctype.fee_component.fee_component.create_default_fee_components",
							callback(r) {
								frappe.dom.unfreeze();
								const res = r.message || {};
								const created = res.created || [];
								const updated = res.updated || [];
								const skipped = res.skipped || [];
								frappe.msgprint({
									title: __("Default Fee Components"),
									message: __("Created: {0}<br>Updated: {1}<br>Already up to date: {2}", [
										created.length ? created.join(", ") : __("None"),
										updated.length ? updated.join(", ") : __("None"),
										skipped.length ? skipped.join(", ") : __("None"),
									]),
								});
								listview.refresh();
							},
							error() {
								frappe.dom.unfreeze();
							},
						});
					},
				);
			});
		},
	};

	const FEE_COMPONENT_METHOD = "slcm.slcm.doctype.fee_component.fee_component";

	function change_payment_gateway(listview) {
		const checked = listview.get_checked_items(true);
		frappe.call({
			method: `${FEE_COMPONENT_METHOD}.get_gateway_status`,
			freeze: true,
			callback(r) {
				const data = r.message || {};
				open_gateway_dialog(listview, checked, data.ready || {}, data.components || []);
			},
		});
	}

	function open_gateway_dialog(listview, checked, gateway_ready, components) {
		const esc = (v) => frappe.utils.escape_html(v || "");
		const gateway_of = Object.fromEntries(components.map((c) => [c.name, c.payment_gateway]));
		// Ticked rows that still exist (another user may have deleted one meanwhile)
		const selected = checked.filter((n) => n in gateway_of);
		const options = frappe.meta
			.get_docfield("Fee Component", "payment_gateway")
			.options.split("\n")
			.filter(Boolean);

		const APPLY = {
			selected: __("Selected Fee Components ({0})", [selected.length]),
			all: __("All Fee Components ({0})", [components.length]),
			choose: __("Choose Fee Components"),
		};
		const apply_options = [...(selected.length ? [APPLY.selected] : []), APPLY.all, APPLY.choose];

		let dialog = null; // assigned below; field onchange can fire while the dialog is being built

		const target_names = () => {
			if (!dialog) return [];
			const apply_to = dialog.get_value("apply_to");
			if (apply_to === APPLY.selected) return selected;
			if (apply_to === APPLY.all) return components.map((c) => c.name);
			return (dialog.get_value("components") || []).filter((n) => n in gateway_of);
		};

		const refresh_preview = () => {
			if (!dialog) return;
			const gw = dialog.get_value("payment_gateway");
			const names = target_names();
			let html = "";
			if (gw && gateway_ready[gw] === false) {
				html += `<div class="alert alert-warning small">${__(
					"{0} is not set up or not enabled yet. Students will not be able to pay these components online until it is.",
					[esc(gw)],
				)}</div>`;
			}
			if (gw && names.length) {
				const changing = names.filter((n) => gateway_of[n] !== gw).length;
				html += `<div class="text-muted small">${__(
					"{0} Fee Component(s) will change to {1}; {2} already on {1}.",
					[changing, esc(gw), names.length - changing],
				)}</div>`;
			}
			dialog.set_df_property("preview", "options", html);
		};

		dialog = new frappe.ui.Dialog({
			title: __("Change Payment Gateway"),
			fields: [
				{
					fieldname: "apply_to",
					fieldtype: "Select",
					label: __("Apply To"),
					options: apply_options.join("\n"),
					default: apply_options[0],
					reqd: 1,
					onchange: refresh_preview,
				},
				{
					fieldname: "components",
					fieldtype: "MultiSelectList",
					label: __("Fee Components"),
					depends_on: `eval:doc.apply_to === ${JSON.stringify(APPLY.choose)}`,
					get_data(txt) {
						const q = (txt || "").toLowerCase();
						return components
							.filter((c) => !q || c.name.toLowerCase().includes(q))
							.map((c) => ({
								value: c.name,
								label: esc(c.name),
								description: __("Current: {0}", [esc(c.payment_gateway)]),
							}));
					},
					onchange: refresh_preview,
				},
				{
					fieldname: "payment_gateway",
					fieldtype: "Select",
					label: __("New Payment Gateway"),
					options: ["", ...options].join("\n"),
					reqd: 1,
					onchange: refresh_preview,
				},
				{ fieldname: "preview", fieldtype: "HTML" },
			],
			primary_action_label: __("Update"),
			primary_action(values) {
				const gw = values.payment_gateway;
				const names = target_names();
				if (!names.length) {
					frappe.msgprint(__("Choose at least one Fee Component."));
					return;
				}
				const changing = names.filter((n) => gateway_of[n] !== gw).length;
				if (!changing) {
					frappe.msgprint(__("All chosen Fee Components are already on {0}.", [esc(gw)]));
					return;
				}
				const apply_to_all = values.apply_to === APPLY.all;
				frappe.confirm(
					__(
						"Change the Payment Gateway of {0} Fee Component(s) to <b>{1}</b>?<br><br>Online payments for their Fee Demands and Fee Invoices in the Student and Parent Portals will go through {1} from now on.",
						[apply_to_all ? __("all {0}", [components.length]) : changing, esc(gw)],
					),
					() => {
						dialog.hide();
						run_gateway_update(listview, apply_to_all ? null : names, gw);
					},
				);
			},
		});
		dialog.show();
		refresh_preview();
	}

	function run_gateway_update(listview, names, gateway) {
		frappe.call({
			method: `${FEE_COMPONENT_METHOD}.bulk_update_payment_gateway`,
			type: "POST",
			// names = null → every Fee Component, resolved on the server
			args: names ? { names, payment_gateway: gateway } : { apply_to_all: 1, payment_gateway: gateway },
			freeze: true,
			freeze_message: __("Updating Payment Gateway…"),
			callback(r) {
				const res = r.message || {};
				const updated = res.updated || [];
				const unchanged = res.unchanged || [];
				const failed = res.failed || [];
				const esc = (n) => frappe.utils.escape_html(n);

				let message = __("Updated to {0}: {1}", [esc(gateway), updated.length]);
				if (unchanged.length) {
					message += "<br>" + __("Already on {0}: {1}", [esc(gateway), unchanged.length]);
				}
				if (failed.length) {
					message +=
						"<br><br><b>" +
						__("Failed ({0}):", [failed.length]) +
						"</b><br>" +
						failed.map((f) => `${esc(f.name)} — ${esc(f.error)}`).join("<br>");
				}

				frappe.msgprint({
					title: __("Payment Gateway Updated"),
					message,
					indicator: failed.length ? "orange" : "green",
				});
				listview.clear_checked_items();
				listview.refresh();
			},
		});
	}
})();
