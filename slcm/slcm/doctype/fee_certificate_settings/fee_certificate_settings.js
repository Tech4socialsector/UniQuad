frappe.ui.form.on("Fee Certificate Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Restore Default Purposes"), () => {
			frappe.confirm(
				__("This resets the heading and text of the three standard purposes to their original wording (custom purposes are kept). Continue?"),
				() => {
					frappe.call({
						method: "slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings.restore_default_purposes",
						freeze: true,
						callback: () => frm.reload_doc(),
					});
				}
			);
		});
	},
});
