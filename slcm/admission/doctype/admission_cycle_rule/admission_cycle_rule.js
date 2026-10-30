frappe.ui.form.on("Admission Cycle Rule", {
    rule_type: function(frm) {
        const hints = {
            "submission_cutoff": "Enter a datetime value e.g. 2025-06-30 23:59:00",
            "modification_lock": "Enter 'after_submit' or a datetime",
            "evaluation_start_dependency": "Enter stage name that must complete first",
            "offer_validity_period": "Enter number of days e.g. 7"
        };
        if (frm.doc.rule_type && hints[frm.doc.rule_type]) {
            frappe.show_alert({message: hints[frm.doc.rule_type], indicator: "blue"}, 6);
        }
    }
});
