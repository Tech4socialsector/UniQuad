// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

const TRANSCRIPT_TYPE_DISPLAY_LABELS = {
	"Final Transcript": __("Provisional Transcript"),
};

function transcript_type_label(value) {
	return TRANSCRIPT_TYPE_DISPLAY_LABELS[value] || value;
}

frappe.ui.form.on("Transcript Request", {
	onload(frm) {
		const original_options = (frm.fields_dict.transcript_type.df.options || "").split("\n");
		frm.set_df_property(
			"transcript_type",
			"options",
			original_options.map((value) => ({ value, label: transcript_type_label(value) }))
		);
		frm.fields_dict.transcript_type.df.formatter = (value) => transcript_type_label(value);
	},
	refresh(frm) {
		if (frm.is_new()) return;

		const pending_states = ["Submitted", "Under Review", "Approved"];
		if (!pending_states.includes(frm.doc.status)) return;

		const payment_blocked = frm.doc.payment_required &&
			!["Not Required", "Paid"].includes(frm.doc.payment_status);

		frm.add_custom_button(__("Approve & Generate"), () => {
			if (payment_blocked) {
				frappe.msgprint({
					title: __("Payment Incomplete"),
					indicator: "red",
					message: __(
						"This request cannot be approved until payment is completed. Current payment status: {0}",
						[frm.doc.payment_status]
					),
				});
				return;
			}
			frappe.confirm(
				__("Generate the transcript for this request now?"),
				() => {
					frappe.call({
						method: "slcm.slcm.page.transcript_management_page.transcript_management_page.approve_request",
						args: { request_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Generating transcript..."),
						callback: (r) => {
							if (!r.message) return;
							if (r.message.success) {
								frappe.show_alert({
									message: __("Request status: {0}", [r.message.status]),
									indicator: "green",
								});
								frm.reload_doc();
							}
						},
						error: () => {
							frappe.show_alert({
								message: __("Approval failed. Please check the request and try again."),
								indicator: "red",
							}, 6);
						},
					});
				}
			);
		}).addClass("btn-primary");

		frm.add_custom_button(__("Reject"), () => {
			frappe.prompt(
				{
					fieldname: "rejection_reason",
					label: __("Rejection Reason"),
					fieldtype: "Small Text",
					reqd: 1,
				},
				(values) => {
					frappe.call({
						method: "slcm.slcm.page.transcript_management_page.transcript_management_page.reject_request",
						args: {
							request_name: frm.doc.name,
							rejection_reason: values.rejection_reason,
						},
						freeze: true,
						callback: (r) => {
							if (r.message && r.message.success) {
								frappe.show_alert({ message: __("Request rejected"), indicator: "orange" });
								frm.reload_doc();
							}
						},
						error: () => {
							frappe.show_alert({
								message: __("Rejection failed. Please check the request and try again."),
								indicator: "red",
							}, 6);
						},
					});
				},
				__("Reject Request")
			);
		});
	},
});
