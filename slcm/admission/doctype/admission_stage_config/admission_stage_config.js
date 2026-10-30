frappe.ui.form.on("Admission Stage Config", {
    refresh: function(frm) {
        if (frm.doc.is_stage_locked) {
            frm.dashboard.set_headline(
                `<span style="color: red; font-weight: bold;">
                🔒 Stage Locked - Live Applicants Present
                </span>`
            );
            frm.disable_save();
        }
        if (!frm.doc.is_enabled) {
            frm.dashboard.set_headline(
                `<span style="color: gray;">
                ○ Stage Disabled
                </span>`
            );
        }
    },
    is_enabled: function(frm) {
        if (!frm.doc.is_enabled) {
            frappe.confirm(
                "Are you sure you want to disable this stage? " +
                "This will affect the admission flow.",
                function() {},
                function() {
                    frm.set_value("is_enabled", 1);
                }
            );
        }
    }
});