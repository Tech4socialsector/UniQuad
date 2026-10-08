// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Eligibility Result", {

    // ── Applicant ID field change ────────────────────────────────────────────
    applicant_id(frm) {
        if (!frm.doc.applicant_id) {
            frm.set_df_property("category", "hidden", 1);
            frm.clear_table("category");
            frm.refresh_field("category");
            return;
        }

        // Fetch full Applicant record (includes categories child table)
        frappe.call({
            method: "frappe.client.get",
            args: { doctype: "Applicant", name: frm.doc.applicant_id },
            callback: function (r) {
                if (!r.message) return;
                const app = r.message;

                // Auto-fill applicant details
                frm.set_value("candidate_name", app.candidate_name);
                frm.set_value("email", app.email);
                frm.set_value("gender", app.gender);
                frm.set_value("program", app.program);

                // Populate the category child table from Applicant's reservation fields
                frm.clear_table("category");
                
                if (app.whether_scstobc_ncl && app.whether_scstobc_ncl !== "General") {
                    frm.add_child("category", { category: app.whether_scstobc_ncl });
                }
                if (app.pwd === "Yes") {
                    frm.add_child("category", { category: "PWD" });
                }
                if (app.karnataka_category === "Yes") {
                    frm.add_child("category", { category: "Karnataka" });
                }
                }
                
                frm.refresh_field("category");
                frm.set_df_property("category", "hidden", 0);
            }
        });
    },

    refresh(frm) {
        // Ensure category table is visible when applicant is already set
        if (frm.doc.applicant_id) {
            frm.set_df_property("category", "hidden", 0);
        }
    }
});
