// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("Office Hours Group", {
    setup(frm) {
        frm.set_query("program", () => {
            return {
                filters: {
                    program_status: "Active"
                }
            };
        });

        frm.set_query("course", () => {
            return {
                filters: {
                    status: "Active"
                }
            };
        });



        // Sections are global (not tied to a batch): no batch filter.
        frm.set_query("section", () => {
            return { filters: {} };
        });
    },

    get_students(frm) {
        if (!frm.doc.program) {
            frappe.msgprint(__("Please select Program first."));
            return;
        }

        frappe.call({
            method: "slcm.slcm.doctype.office_hours_group.office_hours_group.get_students",
            args: {
                program: frm.doc.program,
                course: frm.doc.course,
                academic_year: frm.doc.academic_year,
                academic_term: frm.doc.academic_term,
                batch: frm.doc.batch,
                section: frm.doc.section
            },
            freeze: true,
            freeze_message: __("Fetching Students..."),
            callback: function (r) {
                if (r.message) {
                    frm.clear_table("students");

                    r.message.forEach(s => {
                        let row = frm.add_child("students");
                        row.student = s.student;
                        row.student_name = s.student_name;
                        row.group_roll_number = s.group_roll_number;
                        row.active = s.active;
                    });

                    frm.refresh_field("students");

                    if (r.message.length === 0) {
                        frappe.msgprint(__("No students found matching these criteria."));
                    } else {
                        frappe.show_alert({
                            message: __("Added {0} students", [r.message.length]),
                            indicator: "green"
                        });
                    }
                }
            }
        });
    }
});
