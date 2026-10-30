frappe.ui.form.on("Interview Configuration", {
    onload: function (frm) {
        frm.set_query("admission_cycle", function () {
            return {
                filters: {
                    "status": "Active"
                }
            };
        });
        frm.set_query("program", function () {
            return {
                query: "slcm.admission.doctype.entrance_test_generation.entrance_test_generation.get_program_query",
                filters: {
                    "admission_cycle": frm.doc.admission_cycle,
                    "campus": frm.doc.campus
                }
            };
        });
    },

    before_save: function (frm) {
        let pattern = /^([1-9]\d*:[1-9]\d*|[1-9]\d*)$/;
        if (frm.doc.enter_domestic_ratio && !pattern.test(frm.doc.enter_domestic_ratio)) {
            frappe.throw(__("Domestic Ratio must be a positive integer (e.g. '3' for a 1:3 ratio) or in the format 'X:Y' (e.g. '1:3')."));
        }
        if (frm.doc.enter_international_ratio && !pattern.test(frm.doc.enter_international_ratio)) {
            frappe.throw(__("International Ratio must be a positive integer (e.g. '3' for a 1:3 ratio) or in the format 'X:Y' (e.g. '3:1')."));
        }
    },

    after_save: function (frm) {
        if (frm.doc.academic_year && frm.doc.campus && frm.doc.admission_cycle && frm.doc.program) {
            frm.call({
                method: "get_applicant_counts",
                doc: frm.doc,
                callback: (r) => {
                    if (r.message) {
                        let d = r.message;
                        let count_html = ``;
                        if (frm.doc.applicant_type === "Both") {
                            count_html = `
                                <div><b>Domestic Candidates:</b> ${d.domestic_eligible}</div>
                                <div style="margin-top: 4px;"><b>International Candidates:</b> ${d.international_eligible}</div>
                            `;
                        } else if (frm.doc.applicant_type === "Domestic Applicants") {
                            count_html = `<div><b>Domestic Candidates:</b> ${d.domestic_eligible}</div>`;
                        } else if (frm.doc.applicant_type === "International Applicants") {
                            count_html = `<div><b>International Candidates:</b> ${d.international_eligible}</div>`;
                        } else {
                            count_html = `<div><b>Total Eligible Candidates:</b> ${d.total_eligible}</div>`;
                        }

                        let msg = `
                            <div style="font-size: 14px; text-align: left; width: 100%;">
                                ${count_html}
                                <div style="margin-top: 8px; font-size: 13px; color: #64748b; border-top: 1px solid #e2e8f0; padding-top: 4px;">
                                    <b>Applicant Type:</b> ${frm.doc.applicant_type}
                                </div>
                            </div>
                        `;
                        
                        let $toast = $(`
                            <div style="position: fixed; top: 20px; left: 50%; transform: translateX(-50%); 
                                        z-index: 1040; background: #fff; color: #1f272e; padding: 12px 20px; 
                                        border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                                        border-left: 4px solid #007bff;
                                        display: flex; align-items: center; justify-content: space-between;
                                        min-width: 250px; font-weight: 500;">
                                <div style="flex-grow: 1;">${msg}</div>
                                <button style="background: transparent; border: none; font-size: 22px; color: #94a3b8; cursor: pointer; padding: 0; margin-left: 20px; line-height: 1; align-self: flex-start;" 
                                        onclick="$(this).parent().fadeOut(()=>$(this).parent().remove())">&times;</button>
                            </div>
                        `).hide().appendTo("body").fadeIn();

                        setTimeout(() => {
                            $toast.fadeOut(() => $toast.remove());
                        }, 7000);
                    }
                }
            });
        }
    },

    refresh: function (frm) {
        // Remove any previously added buttons (safety)
        frm.remove_custom_button("Fetch Applicant");
        frm.remove_custom_button("Generate Interview List");
        frm.remove_custom_button("View Interview List");

        const show_actions = (
            !frm.is_new() &&
            frm.doc.docstatus === 0 &&
            ["Draft", "In Progress", "Failed"].includes(frm.doc.status || "Draft") &&
            frm.doc.academic_year &&
            frm.doc.campus &&
            frm.doc.admission_cycle &&
            frm.doc.program
        );

        if (show_actions) {


            // ── "Generate Interview List" button ─────────────────────────────────
            frm.add_custom_button(__("Generate Interview List"), function () {
                let program_list = frm.doc.program || "";
                let program_row = program_list ? 
                    `<tr><td style="color: #adb5bd; font-weight: 500;">Programme</td><td style="font-weight: 700; text-align: right; color: #495057;">${program_list}</td></tr>` : '';

                frappe.confirm(
                    __(
                        `<div style="text-align: center; padding: 10px;">
                            <h4 style="font-weight: 800; color: #212529; margin-bottom: 10px;">Confirm Generation</h4>
                            <p style="color: #6c757d; font-size: 14px; line-height: 1.5;">Are you sure you want to generate the Interview list with the following configuration?</p>
                            
                            <div style="background: #fff; border: 1.5px solid #f1f3f5; border-radius: 12px; padding: 16px; margin: 24px 0; text-align: left;">
                                <table style="width: 100%; font-size: 13px; border-collapse: separate; border-spacing: 0 8px;">
                                    <tr><td style="color: #adb5bd; font-weight: 500;">Academic Year</td><td style="font-weight: 700; text-align: right; color: #495057;">{0}</td></tr>
                                    <tr><td style="color: #adb5bd; font-weight: 500;">Campus</td><td style="font-weight: 700; text-align: right; color: #495057;">{1}</td></tr>
                                    <tr><td style="color: #adb5bd; font-weight: 500;">Admission Cycle</td><td style="font-weight: 700; text-align: right; color: #495057;">{2}</td></tr>
                                    ${program_row}
                                </table>
                            </div>
                            <p style="font-size: 12px; color: #adb5bd; font-style: italic;">This process will only fetch eligible candidates.</p>
                        </div>`,
                        [
                            frm.doc.academic_year,
                            frm.doc.campus,
                            frm.doc.admission_cycle
                        ]
                    ),
                    () => {
                        // ── Yes → call server method ────────────────────────
                        frm.call({
                            method: "generate_interview_list",
                            doc: frm.doc,
                            freeze: true,
                            freeze_message: __("Generating Interview List… Please wait"),
                            callback: (r) => {
                                if (r.message) {
                                    frm.reload_doc();
                                }
                            }
                        });
                    },
                    () => {
                        // No → do nothing
                    }
                );

            })
        }

        // ── "View Interview List" button ──────────────────────────────────────
        // Visible when the list has already been generated
        if (["Completed"].includes(frm.doc.status)) {
            frm.add_custom_button(__("View Interview List"), function () {
                let filters = {
                    academic_year: frm.doc.academic_year,
                    campus: frm.doc.campus,
                    admission_cycle: frm.doc.admission_cycle
                };
                if (frm.doc.program) {
                    filters.program = frm.doc.program;
                }
                frappe.db.get_value("Interview List", filters, "name", (r) => {
                    if (r && r.name) {
                        frappe.set_route("Form", "Interview List", r.name);
                    } else {
                        frappe.msgprint(__("Associated Interview List not found."));
                    }
                });
            });
        }

        toggle_ratio_fields(frm);
        check_programme_settings(frm, false);
    },

    // Re-evaluate button visibility on field changes
    academic_year: function (frm) { frm.trigger("refresh"); },
    campus: function (frm) { frm.trigger("refresh"); },
    admission_cycle: function (frm) { frm.trigger("refresh"); },
    program: function (frm) { 
        frm.trigger("refresh");
        check_programme_settings(frm, true);
    },
    status: function (frm) { frm.trigger("refresh"); },

    applicant_type: function (frm) {
        if (frm.doc.applicant_type === "Domestic Applicants") {
            frm.set_value("enter_international_ratio", "");
        } else if (frm.doc.applicant_type === "International Applicants") {
            frm.set_value("enter_domestic_ratio", "");
        }
        check_programme_settings(frm, true);
    },

    fetch_exempted_applicant: function (frm) {
        toggle_ratio_fields(frm);
    }
});


function toggle_ratio_fields(frm) {
    let show_domestic = !frm.doc.fetch_exempted_applicant && (frm.doc.applicant_type === "Domestic Applicants" || frm.doc.applicant_type === "Both");
    let show_international = !frm.doc.fetch_exempted_applicant && (frm.doc.applicant_type === "International Applicants" || frm.doc.applicant_type === "Both");
    let show_exempted = !!frm.doc.fetch_exempted_applicant;

    if (frm.doc.__show_dom_ratio !== undefined) {
        show_domestic = show_domestic && frm.doc.__show_dom_ratio;
    }
    if (frm.doc.__show_int_ratio !== undefined) {
        show_international = show_international && frm.doc.__show_int_ratio;
    }

    frm.toggle_display("enter_domestic_ratio", show_domestic);
    frm.toggle_display("enter_international_ratio", show_international);
    frm.toggle_display("part_b_score", show_exempted);

    if (!show_domestic && frm.doc.enter_domestic_ratio) {
        frm.set_value("enter_domestic_ratio", "");
    }
    if (!show_international && frm.doc.enter_international_ratio) {
        frm.set_value("enter_international_ratio", "");
    }
}

function check_programme_settings(frm, show_toast = true) {
    if (!frm.doc.program) {
        frm.doc.__show_dom_ratio = true;
        frm.doc.__show_int_ratio = true;
        toggle_ratio_fields(frm);
        return;
    }

    let program_names = [frm.doc.program];

    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Programme",
            filters: { "name": ["in", program_names] },
            fields: ["name", "entrance_test", "intereview", "international_entrance_test", "international_interview"]
        },
        callback: function (r) {
            if (r.message) {
                let show_dom_ratio = false;
                let show_int_ratio = false;
                let missing_msgs = [];

                r.message.forEach(prog => {
                    // Check for Toast messages if applicant type allows
                    if (frm.doc.applicant_type === "Both") {
                        if (prog.intereview == 0 && prog.international_interview == 1) {
                            missing_msgs.push(`Please Note: For Programme <b>${prog.name}</b>, Domestic applicants do not have an interview stage. We will allocate the interview for International applicants only.`);
                        } else if (prog.intereview == 1 && prog.international_interview == 0) {
                            missing_msgs.push(`Please Note: For Programme <b>${prog.name}</b>, International applicants do not have an interview stage. We will allocate the interview for Domestic applicants only.`);
                        }
                    } else if (frm.doc.applicant_type === "Domestic Applicants") {
                        if (prog.intereview == 0) {
                            missing_msgs.push(`Please Note: For Programme <b>${prog.name}</b>, Domestic applicants do not have an interview stage.`);
                            frm.set_value("program", "");
                            return;
                        }
                    } else if (frm.doc.applicant_type === "International Applicants") {
                        if (prog.international_interview == 0) {
                            missing_msgs.push(`Please Note: For Programme <b>${prog.name}</b>, International applicants do not have an interview stage.`);
                            frm.set_value("program", "");
                            return;
                        }
                    }

                    // Check for ratios
                    if (prog.entrance_test == 1 && prog.intereview == 1) {
                        show_dom_ratio = true;
                    }
                    if (prog.international_entrance_test == 1 && prog.international_interview == 1) {
                        show_int_ratio = true;
                    }
                });

                if (show_toast && missing_msgs.length > 0) {
                    frappe.msgprint({
                        title: __('Notice'),
                        indicator: 'orange',
                        message: missing_msgs.join("<br><br>")
                    });
                }

                frm.doc.__show_dom_ratio = show_dom_ratio;
                frm.doc.__show_int_ratio = show_int_ratio;
                
                toggle_ratio_fields(frm);
            }
        }
    });
}
