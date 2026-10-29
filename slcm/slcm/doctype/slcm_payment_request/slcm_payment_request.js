// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on("SLCM Payment Request", {
	refresh(frm) {
        if (frm.doc.status !== "Paid" && frm.doc.status !== "Cancelled" && frm.doc.payment_gateway === "Razorpay") {
            frm.add_custom_button(__("Reconcile with Razorpay"), function() {
                frappe.call({
                    method: "slcm.api.service.fee_service.reconcile_single_payment",
                    args: {
                        payment_request_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (r.message) {
                            frappe.show_alert({
                                message: r.message.message || __("Reconciliation triggered."),
                                indicator: r.message.status === "success" ? "green" : r.message.status === "info" ? "blue" : "red"
                            });
                            frm.reload_doc();
                        }
                    }
                });
            });
        }

        if (!frm.is_new() && frm.doc.gateway_status === "captured" && frm.doc.settlement_status != "processed") {
            frm.add_custom_button(__("Sync Settlement"), function() {
                frappe.call({
                    method: "slcm.api.sync_settlements.sync_single_payment_settlement",
                    args: {
                        pr_name: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __("Checking Razorpay settlement..."),
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint(r.message.message || __("Settlement synchronized."));
                            frm.reload_doc();
                        }
                    }
                });
            }).addClass("btn-primary");
        }
	},
});
