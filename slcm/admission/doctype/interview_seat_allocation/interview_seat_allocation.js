// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Interview Seat Allocation", {
    onload: function (frm) {
        frm.set_query("admission_cycle", function () {
            return {
                filters: {
                    "status": "Active"
                }
            };
        });
    },

    refresh(frm) {
        calculate_final_cumulative(frm, true);

        // Action buttons when interview_result_status is Pass
        const is_internal = !frappe.user_roles.includes("Applicant") || frappe.user_roles.includes("System Manager") || frappe.user_roles.includes("Administrator") || frappe.user_roles.includes("Interview Admin");
        if (frm.doc.interview_result_status === "Pass" && is_internal && frm.doc.is_international_applicant) {
            const hide_all_statuses = ["Selected", "Rejected", "Offer Issued"];
            
            if (!hide_all_statuses.includes(frm.doc.status)) {
                frm.add_custom_button(__("Select"), function () {
                    frappe.confirm(__("Are you sure you want to mark this applicant as Selected?"), () => {
                        frappe.db.set_value(frm.doc.doctype, frm.doc.name, "status", "Selected").then(() => frm.reload_doc());
                    });
                }).removeClass("btn-default").addClass("btn-success").css({"color": "white"});
                
                if (frm.doc.status !== "Waitlisted") {
                    frm.add_custom_button(__("Waitlist"), function () {
                        frappe.confirm(__("Are you sure you want to Waitlist this applicant?"), () => {
                            frappe.db.set_value(frm.doc.doctype, frm.doc.name, "status", "Waitlisted").then(() => frm.reload_doc());
                        });
                    }).removeClass("btn-default").addClass("btn-warning").css({"color": "white"});
                }
                
                frm.add_custom_button(__("Reject Application"), function () {
                    frappe.confirm(__("Are you sure you want to Reject this applicant?"), () => {
                        frappe.db.set_value(frm.doc.doctype, frm.doc.name, "status", "Rejected").then(() => frm.reload_doc());
                    });
                }).removeClass("btn-default").addClass("btn-danger").css({"color": "white"});
            }
        }

        // Generate Offer Letter Button for Selected status
        if (frm.doc.status === "Selected" && is_internal) {
            frm.add_custom_button(__("Generate Offer Letter"), function () {
                frappe.confirm(__("Are you sure you want to generate the Offer Letter for this applicant?"), function() {
                    frappe.call({
                        method: "slcm.api.service.offer_service.bulk_generate_offers",
                        args: {
                            applicants: [frm.doc.applicant]
                        },
                        freeze: true,
                        freeze_message: __("Generating Offer Letter..."),
                        callback: function (r) {
                            if (r.message && r.message.success && r.message.success.length > 0) {
                                frappe.msgprint({
                                    message: __("Offer Letter generated successfully."),
                                    indicator: "green"
                                });
                                frm.reload_doc();
                            } else if (r.message && r.message.errors && r.message.errors.length > 0) {
                                frappe.msgprint({
                                    title: __("Error generating Offer Letter"),
                                    message: r.message.errors[0].error,
                                    indicator: "red"
                                });
                            }
                        }
                    });
                });
            });
        }

        // Administrator can do everything — skip all restrictions
        if (frappe.user_roles.includes("Administrator")) {
            // Ensure all tabs/sections are visible and editable by default
            // But reschedule tab will be handled dynamically below
        }

        // show/hide reschedule tab depending on flag or status
        const is_rescheduled = frm.doc.is_rescheduled == 1 || frm.doc.interview_status === "Rescheduled";
        frm.set_df_property("tab_9_tab", "hidden", !is_rescheduled);
        frm.set_df_property("reschedule_section", "hidden", !is_rescheduled);

        // apply applicant restrictions
        if (frappe.user_roles.includes("Applicant")) {
            _apply_applicant_permissions(frm);
        }
    },

    // ── Applicant field change ───────────────────────────────────────────────
    applicant(frm) {
        if (!frm.doc.applicant) {
            frm.set_df_property("category", "hidden", 1);
            return;
        }

        // Fetch all needed Applicant information including categories
        frappe.call({
            method: "frappe.client.get",
            args: { doctype: "Applicant", name: frm.doc.applicant },
            callback: function (r) {
                if (!r.message) return;
                const app = r.message;

                // Populate standard fields
                frm.set_value("candidate_name", app.candidate_name);
                frm.set_value("program", app.program);
                frm.set_value("email", app.email);
                frm.set_value("gender", app.gender);
                frm.set_value("is_international_applicant", app.foriegn_national === "Yes" ? 1 : 0);

                // Source tracking fields (if present on the form)
                if (app.exempts_entrance_test !== undefined) {
                    frm.set_value("exempts_entrance_test", app.exempts_entrance_test);
                }
                if (app.exempts_interview !== undefined) {
                    frm.set_value("exempts_interview", app.exempts_interview);
                }

                // Show the category table and populate it from reservation fields
                frm.clear_table("category");
                if (app.whether_scstobc_ncl && app.whether_scstobc_ncl.toUpperCase() !== "General") {
                    frm.add_child("category", { category: app.whether_scstobc_ncl });
                } else {
                    frm.add_child("category", { category: "General" });
                }
                if (app.pwd === "Yes") {
                    frm.add_child("category", { category: "PWD" });
                }
                if (app.karnataka_category === "Yes") {
                    frm.add_child("category", { category: "Karnataka" });
                }
                frm.refresh_field("category");
                frm.set_df_property("category", "hidden", 0);
            }
        });
    },

    interview_score: function (frm) {
        if (frm.doc.interview_score > 30) {
            frappe.msgprint({
                title: __("Invalid Score"),
                indicator: "red",
                message: __("Interview Score cannot be more than 30. The field has been cleared.")
            });
            frm.set_value("interview_score", "");
            return;
        }
        calculate_final_cumulative(frm);
    },
 
    interview_status: function (frm) {
        calculate_final_cumulative(frm);
    }
});
 
function calculate_final_cumulative(frm, skip_dirty = false) {
    // Only auto-calculate the numeric score fields.
    // Result Status (interview_result_status) and Offered Admission (offered_admission)
    // are purely manual — never auto-set or overwritten by the system.
    const et_marks = flt(frm.doc.et_total_marks_secured_in_part_a_b || 0);
    const et_max = flt(frm.doc.et_total_marks || 0);
    const interview_max = 30.0;

    let score = flt(frm.doc.interview_score || 0);
    let max_marks = et_max + interview_max;
    let cumulative = 0;
    let percentage = 0;

    if (frm.doc.interview_status === "Attended") {
        cumulative = et_marks + score;
        percentage = max_marks > 0 ? (cumulative / max_marks * 100.0) : 0;
    }
    // Absent or Scheduled/blank → cumulative and percentage stay 0

    const skip_dirty_arg = skip_dirty ? true : false;

    if (frm.doc.final_cumulative_score !== cumulative) {
        frm.set_value("final_cumulative_score", cumulative, null, skip_dirty_arg);
    }
    if (frm.doc.final_percentage !== percentage) {
        frm.set_value("final_percentage", percentage, null, skip_dirty_arg);
    }
    // NOTE: offered_admission and interview_result_status are NOT touched here.
    //       Admin/user sets these fields manually at their discretion.
}


function _apply_applicant_permissions(frm) {
    // Reference section read-only
    const ref_fields = [
        "interview_list", "academic_year", "admission_cycle",
        "campus", "program_level"
    ];
    ref_fields.forEach(f => frm.set_df_property(f, "read_only", 1));

    // Applicant info read-only (including the category table)
    const info_fields = [
        "applicant", "candidate_name", "program",
        "email", "gender", "is_international_applicant"
    ];
    info_fields.forEach(f => frm.set_df_property(f, "read_only", 1));

    // Make the category child table read-only for applicants
    frm.set_df_property("category", "read_only", 1);

    // Slot section read-only except interview_staff_member until assigned
    const slot_readonly = [
        "staff_name", "staff_email", "staff_contact",
        "interview_date", "interview_time", "interview_slot_status",
        "slot_assigned_by"
    ];
    slot_readonly.forEach(f => frm.set_df_property(f, "read_only", 1));

    // Allow staff selection until slot status changes
    const assigned_statuses = ["Slot Assigned", "Confirmed", "Cancelled", "Rescheduled"];
    const is_assigned = assigned_statuses.includes(frm.doc.interview_slot_status);
    frm.set_df_property("interview_staff_member", "read_only", is_assigned ? 1 : 0);

    // Reschedule tab hidden for applicants until flagged
    const resched = frm.doc.is_rescheduled == 1 || frm.doc.interview_status === "Rescheduled";
    frm.set_df_property("tab_9_tab", "hidden", !resched);
    frm.set_df_property("reschedule_section", "hidden", !resched);

    if (resched) {
        // make all re_ fields read-only
        const re_fields = [
            "re_interview_staff_member", "re_staff_name", "re_staff_email",
            "re_staff_contact", "re_interview_date", "re_interview_time",
            "re_interview_slot_status", "re_slot_assigned_by", "reschedule_reason"
        ];
        re_fields.forEach(f => frm.set_df_property(f, "read_only", 1));
    }

    // Feedback field logic
    const results_ready = frm.doc.result_published == 1;
    
    // Show feedback only when results are published
    frm.set_df_property("feedback", "hidden", !results_ready);
    
    if (results_ready) {
        // Mandatory if empty, Read-only if already submitted (has value)
        const has_feedback = !!(frm.doc.feedback && frm.doc.feedback.trim());
        frm.set_df_property("feedback", "reqd", !has_feedback);
        frm.set_df_property("feedback", "read_only", has_feedback);
    }

    // Result section read-only for applicants
    const result_fields = [
        "interview_status", "attendance_marked_on", "interview_score",
        "interview_result_status", "rank", "result_published"
    ];
    result_fields.forEach(f => frm.set_df_property(f, "read_only", 1));
}
