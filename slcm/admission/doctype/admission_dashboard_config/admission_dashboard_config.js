frappe.ui.form.on("Admission Dashboard Config", {
    refresh: function(frm) {
        frm.add_custom_button("Refresh Stats", function() {
            frappe.call({
                method: "refresh_stats",
                doc: frm.doc,
                callback: function(r) {
                    if (r.message) {
                        frm.reload_doc();
                        frappe.show_alert({
                            message: "Dashboard stats refreshed",
                            indicator: "green"
                        }, 3);
                    }
                }
            });
        }, "Actions");

        if (frm.doc.admission_cycle) {
            frm.add_custom_button("View All Applicants", function() {
                frappe.set_route("List", "Applicant", {
                    admission_cycle: frm.doc.admission_cycle
                });
            });
            frm.add_custom_button("View Seat Matrices", function() {
                frappe.set_route("List", "Campus Seat Matrix", {
                    admission_cycle: frm.doc.admission_cycle
                });
            });
            frm.add_custom_button("View Merit Lists", function() {
                frappe.set_route("List", "Merit List", {
                    admission_cycle: frm.doc.admission_cycle
                });
            });
            frm.add_custom_button("Generate Report", function() {
                frappe.set_route("List", "Admission Report Config");
            });
        }

        if (frm.doc.total_applications) {
            const accepted_pct = frm.doc.total_applications > 0
                ? Math.round(
                    (frm.doc.accepted / frm.doc.total_applications) * 100
                  )
                : 0;
            frm.dashboard.add_comment(
                `Acceptance Rate: ${accepted_pct}% | ` +
                `Docs Pending: ${frm.doc.documents_pending}`,
                frm.doc.documents_pending > 0 ? "orange" : "green"
            );
        }

        if (frm.doc.last_refreshed) {
            frm.dashboard.set_headline(
                `<span style="color: gray; font-size: 12px;">
                Last refreshed: ${frm.doc.last_refreshed}
                </span>`
            );
        }
    }
});