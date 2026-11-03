// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

// Domains come from the site: rows are not typed in and not deleted (no Add
// Row, no Delete in the grid or the row editor). Untick Enabled instead.
function lock_domain_rows(frm) {
	frm.set_df_property("domains", "cannot_add_rows", 1);
	frm.set_df_property("domains", "cannot_delete_rows", 1);
	const grid = frm.fields_dict.domains && frm.fields_dict.domains.grid;
	if (grid) {
		grid.cannot_add_rows = true;
		grid.df.cannot_delete_rows = 1;
		grid.refresh();
	}
}

frappe.ui.form.on("Site Domain Settings", {
	onload(frm) {
		lock_domain_rows(frm);
	},

	refresh(frm) {
		lock_domain_rows(frm);
		frm.add_custom_button(__("Sync Domains"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save your changes before syncing."));
				return;
			}
			frappe.call({
				method: "slcm.slcm.doctype.site_domain_settings.site_domain_settings.sync_domains",
				type: "POST",
				args: { current_host: window.location.hostname },
				freeze: true,
				freeze_message: __("Syncing domains..."),
			}).then(({ message }) => {
				const added = (message && message.added) || [];
				frappe.show_alert({
					message: added.length
						? __("{0} domain(s) added: {1}", [added.length, added.join(", ")])
						: __("No new domains found."),
					indicator: added.length ? "green" : "blue",
				});
				frm.reload_doc();
			});
		});
	},
});
