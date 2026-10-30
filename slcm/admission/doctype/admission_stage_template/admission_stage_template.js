frappe.ui.form.on("Admission Stage Template", {
    refresh: function(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button("Preview Stage Flow", function() {
                const stages = frm.doc.stages || [];
                const sorted = stages
                    .filter(s => s.is_enabled)
                    .sort((a, b) => a.sequence - b.sequence);
                let html = "<ol style='font-size:14px;'>";
                sorted.forEach(s => {
                    const lock = s.requires_approval_to_unlock
                        ? " <span style='color:red'>🔒</span>" : "";
                    const notify = s.notify_applicant_on_entry
                        ? " <span style='color:green'>📧</span>" : "";
                    html += `<li><b>${s.stage_name}</b> [${s.stage_type}]${lock}${notify}</li>`;
                });
                html += "</ol>";
                html += "<small>🔒 = Requires approval to unlock | 📧 = Notifies applicant</small>";
                frappe.msgprint({title: "Stage Flow Preview", message: html});
            });
            frm.add_custom_button("Apply to Cycle", function() {
                frappe.prompt([
                    {label: "Admission Cycle", fieldname: "admission_cycle", fieldtype: "Link", options: "Admission Cycle", reqd: 1}
                ], function(values) {
                    frappe.call({
                        method: "slcm.admission.utils.stage_engine.apply_template_to_cycle",
                        args: {template_name: frm.doc.name, cycle_name: values.admission_cycle},
                        callback: function(r) {
                            frappe.show_alert({message: "Template applied to cycle.", indicator: "green"});
                        }
                    });
                }, "Apply Stage Template to Cycle", "Apply");
            }, "Actions");
        }
    }
});

frappe.ui.form.on("Stage Definition", {
    sequence: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const sequences = (frm.doc.stages || []).map(s => s.sequence);
        const duplicates = sequences.filter(s => s === row.sequence).length;
        if (duplicates > 1) {
            frappe.show_alert({message: "Duplicate sequence number. Please use unique values.", indicator: "red"});
        }
    }
});
