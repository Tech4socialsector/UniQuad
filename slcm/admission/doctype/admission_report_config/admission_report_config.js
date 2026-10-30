frappe.ui.form.on("Admission Report Config", {
    refresh: function(frm) {
        const status_colors = {
            "Pending": "gray",
            "Generating": "blue",
            "Completed": "green",
            "Failed": "red"
        };
        const color = status_colors[frm.doc.status] || "gray";
        frm.dashboard.set_headline(
            `<span style="color: ${color}; font-weight: bold;">
            Report Status: ${frm.doc.status}
            </span>`
        );
        if (!frm.is_new()) {
            frm.add_custom_button("Generate Report", function() {
                frappe.confirm(
                    "Generate this report now?",
                    function() {
                        frappe.call({
                            method: "generate_report",
                            doc: frm.doc,
                            callback: function(r) {
                                if (r.message) {
                                    frappe.msgprint({
                                        title: "Report Generated",
                                        indicator: "green",
                                        message: `Report completed with ${r.message.length} records.`
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, "Actions");

            frm.add_custom_button("Export as PDF", function() {
                const url = frappe.urllib.get_full_url(
                    `/api/method/frappe.utils.print_format.download_pdf` +
                    `?doctype=Admission Report Config&name=${frm.doc.name}&format=Standard`
                );
                window.open(url);
            }, "Actions");

            frm.add_custom_button("Export Audit Log", function() {
                frappe.set_route("List", "Admission Audit Log");
            }, "Actions");
        }
    }
});