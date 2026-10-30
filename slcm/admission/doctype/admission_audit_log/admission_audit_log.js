frappe.ui.form.on("Admission Audit Log", {
    refresh: function(frm) {
        frm.disable_save();
        frm.dashboard.set_headline(
            `<span style="color: gray; font-weight: bold;">
            🔒 Read-Only - Legal Audit Record
            </span>`
        );
        
    }
});