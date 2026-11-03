// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Application Fee", {
	refresh(frm) {
        frm.set_query("payment_receipt_template", () => {
            return {
                filters : {
                    "doc_type" : "Applicant Payment Receipt"
                }
            }
        })
         frm.set_query("admission_category", "application_fee_by_category", function (doc, cdt, cdn) {
            return {
                filters: {
                    "reservation_type": ["in", ["Vertical", "Horizontal"]],
                    "is_active" : 1
                }
            };
        });
	},
});
