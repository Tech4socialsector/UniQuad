// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on("SLCM Payment Request", {
	refresh(frm) {
        if (frm.doc.status === "Failed" && frm.doc.failure_message) {
            frm.dashboard.set_headline_alert(
                `<b>${__("Payment failed")}:</b> ${frappe.utils.escape_html(frm.doc.failure_message)}`, "red"
            );
        }

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

        // Razorpay settlements only (Easebuzz requests carry gateway status "success")
        if (!frm.is_new() && frm.doc.payment_gateway !== "Easebuzz" && frm.doc.gateway_status === "captured" && frm.doc.settlement_status != "processed") {
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

        // Money no SLCM record holds (duplicate / unapplied): record the refund made in the gateway dashboard
        if (frm.doc.docstatus === 1 && frm.doc.status === "Paid" && frappe.user.has_role(["System Manager", "Accounts Manager"])) {
            frappe.call({
                method: "slcm.slcm.fee.payment_ledger.get_refundable",
                args: { request_name: frm.doc.name },
                callback: function(r) {
                    const refundable = flt(r.message);
                    if (refundable <= 0) return;
                    frm.dashboard.set_headline_alert(
                        __("₹{0} of this payment is not applied to any fee and needs a refund.", [format_number(refundable, null, 2)]), "orange"
                    );
                    frm.add_custom_button(__("Record Refund"), function() {
                        const d = new frappe.ui.Dialog({
                            title: __("Record Refund"),
                            fields: [
                                { fieldname: "amount", fieldtype: "Currency", label: __("Refunded Amount"), reqd: 1, default: refundable,
                                  description: __("At most ₹{0}", [format_number(refundable, null, 2)]) },
                                { fieldname: "refunded_on", fieldtype: "Date", label: __("Refunded On"), reqd: 1, default: frappe.datetime.get_today() },
                                { fieldname: "refund_reference", fieldtype: "Data", label: __("Refund Reference"), reqd: 1,
                                  description: __("Refund id / UTR from the gateway dashboard. SLCM does not send the refund; do it in the gateway first.") },
                            ],
                            primary_action_label: __("Record"),
                            primary_action(values) {
                                frappe.call({
                                    method: "slcm.slcm.fee.payment_ledger.record_refund",
                                    args: { request_name: frm.doc.name, ...values },
                                    freeze: true,
                                    callback: function() { d.hide(); frm.reload_doc(); },
                                });
                            },
                        });
                        d.show();
                    });
                }
            });
        }

        // Easebuzz payouts
        if (frm.doc.docstatus === 1 && frm.doc.payment_gateway === "Easebuzz" && frm.doc.status === "Paid" && frm.doc.settlement_status !== "Settled") {
            frm.add_custom_button(__("Sync Settlement"), function() {
                frappe.call({
                    method: "slcm.slcm.fee.easebuzz_settlement.sync_for_request",
                    args: {
                        pr_name: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __("Checking Easebuzz settlement..."),
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint(r.message.message);
                            frm.reload_doc();
                        }
                    }
                });
            }).addClass("btn-primary");
        }
	},
});
