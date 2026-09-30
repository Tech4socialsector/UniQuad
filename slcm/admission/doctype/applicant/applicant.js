function slcm_applicant_setup_country_state_city_queries(frm) {
    frm.set_query("state", () => {
        if (frm.doc.country) {
            return { filters: { country: frm.doc.country } };
        }
        return { filters: { name: "!__noop__" } };
    });
}

frappe.ui.form.on("Applicant", {

    if_cgpa_maximum_cgpa_class_xii: function(frm) {
        if (frm.doc.if_cgpa_maximum_cgpa_class_xii && frm.doc.if_cgpa_maximum_cgpa_class_xii > 10) {
            frappe.msgprint({
                title: __('Invalid CGPA'),
                message: __('Class XII CGPA cannot be greater than 10.'),
                indicator: 'red'
            });
            frm.set_value('if_cgpa_maximum_cgpa_class_xii', '');
        }
    },


    // ── REFRESH ──────────────────────────────
    refresh: function (frm) {
        // Auto-refresh when status is updated from Entrance Test Seat Allocation
        if (!window._applicant_status_realtime_subscribed) {
            window._applicant_status_realtime_subscribed = true;
            frappe.realtime.on("applicant_status_updated", function (data) {
                const frm = cur_frm;
                if (frm && frm.doctype === "Applicant" && frm.doc && frm.doc.name === data.docname) {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Application status was updated to {0}", [data.status || ""]),
                        indicator: "blue",
                    }, 4);
                }
            });
        }
         // Override after attach widget renders
         if (frm.fields_dict['candidate_photo']) {
             frm.fields_dict['candidate_photo'].df.options = 'My Device'; // won't work alone
            
             // Hook into the upload dialog
             frm.fields_dict['candidate_photo'].$input?.on('click', function() {
             setTimeout(() => {
                 // Remove Link option
                 $('.upload-area .from-link').hide();
                 // Remove Camera option  
                 $('.upload-area .from-camera').hide();
             }, 100);
         });
         }

        if (frm.doc.status === "Draft" || frm.doc.__islocal) {
            frm.add_custom_button(__("Save as Draft"), function () {
                frm.set_value("status", "Draft");
                
                frappe.call({
                    method: "frappe.desk.form.save.savedocs",
                    args: {
                        doc: JSON.stringify(frm.doc),
                        action: "Save"
                    },
                    freeze: true,
                    freeze_message: __("Saving Draft..."),
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.show_alert({message: __("Saved as Draft"), indicator: "green"});
                            frm.reload_doc();
                        }
                    }
                });
            });
        }

        if (!frm.doc.__islocal && (frm.doc.status === 'Fee Paid' || frm.doc.status === 'Enrolled')) {
            frm.add_custom_button(__("Refund Request"), function () {
                frappe.set_route("List", "Refund Request", {
                    applicant: frm.doc.name
                });
            },);
        }

        // Custom buttons for submitted docs
        // if (frm.doc.status && frm.doc.status !== "Draft") {
        //     frm.add_custom_button(__("View Campus Status"), function () {
        //         frappe.set_route("List", "Applicant Campus Preference", {
        //             applicant: frm.doc.name
        //         });
        //     });
        //     frm.add_custom_button(__("View Documents"), function () {
        //         frappe.set_route("List", "Applicant Document", {
        //             applicant: frm.doc.name
        //         });
        //     });
        // }

        // Record Application Fee Payment (offline)
        const feeStatus = (frm.doc.application_fee_status || "").trim();
        if (!frm.doc.__islocal && frm.doc.status === "Draft" &&
            (feeStatus === "Pending" || feeStatus === "Requested") &&
            frm.doc.program && frm.doc.admission_cycle) {
            frm.add_custom_button(__("Record Application Fee Payment"), function () {
                const d = new frappe.ui.Dialog({
                    title: __("Record Application Fee Payment"),
                    fields: [
                        { label: __("Payment Mode"), fieldname: "payment_mode", fieldtype: "Select",
                            options: "Cash\nCheque\nUPI\nQR Code\nBank Transfer\nDemand Draft", default: "Cash", reqd: 1 },
                        { label: __("Reference No / UTR / Cheque No"), fieldname: "reference_number", fieldtype: "Data", reqd: 1 },
                        { label: __("Bank Name"), fieldname: "bank_name", fieldtype: "Data" },
                        { label: __("Cheque Number"), fieldname: "cheque_number", fieldtype: "Data" },
                        { label: __("Cheque Date"), fieldname: "cheque_date", fieldtype: "Date" },
                        { label: __("UPI ID"), fieldname: "upi_id", fieldtype: "Data" },
                        { label: __("Remarks"), fieldname: "remarks", fieldtype: "Small Text" }
                    ],
                    primary_action_label: __("Record Payment"),
                    primary_action(values) {
                        frappe.call({
                            method: "slcm.api.service.fee_service.process_application_fee_payment",
                            args: {
                                applicant_name: frm.doc.name,
                                payment_mode: values.payment_mode,
                                reference_number: values.reference_number,
                                bank_name: values.bank_name,
                                cheque_number: values.cheque_number,
                                cheque_date: values.cheque_date,
                                upi_id: values.upi_id,
                                remarks: values.remarks
                            },
                            callback(r) {
                                if (!r.exc) {
                                    d.hide();
                                    frm.reload_doc();
                                    frappe.show_alert({ message: __("Payment recorded. Receipt: {0}", [r.message || ""]), indicator: "green" });
                                }
                            }
                        });
                    }
                });
                d.show();
            }, __("Actions"));
        }

        if (frm.doc.application_fee_status === "Pending" || frm.doc.application_fee_status === "Requested") {
            frm.add_custom_button(__("Waive Application Fee"), function () {
                frappe.confirm(
                    __("Mark application fee as Waived for this applicant?"),
                    function () {
                        frappe.call({
                            method: "slcm.admission.doctype.applicant.applicant.waive_fee",
                            args: { name: frm.doc.name },
                            callback: function (r) {
                                frm.reload_doc();
                                frappe.show_alert({ message: __("Fee marked as Waived"), indicator: "green" }, 5);
                            }
                        });
                    }
                );
            }, __("Portal"));
        }

        if (!frm.doc.__islocal) {
            frm.add_custom_button(__("View as Candidate"), function() {
                window.open(`/my-applications?app=${encodeURIComponent(frm.doc.name)}`, '_blank');
            });
        }

        // Guardian fields required only when flag is set
        frm.toggle_reqd("guardian_name", frm.doc.guardian_required);
        frm.toggle_reqd("guardian_mobile", frm.doc.guardian_required);
        // Percentage required when National test is selected
        frm.toggle_reqd("percentage", !!frm.doc.national_test_name);

        // ── Convert to Student (single record) ───────────────────────────────────
        // Visible only when the applicant has status "Confirmation Fee Paid" or "Full Fee Paid".
        // Calls the unified API (slcm.api.service.applicant_to_student.convert_applicant_to_student).
        // For the full AFA flow (Fee Invoice + Enrollment), use the "Convert to Student" button
        // on the Applicant Fee Assignment form instead.
        if (!frm.doc.__islocal && frm.doc.status === 'Full Fee Paid') {
            const student_btn = frm.add_custom_button(__('Convert to Student'), function () {
                // Resolve AFA for program and admission_cycle
                frappe.db.get_list('Applicant Fee Assignment', {
                    filters: {
                        applicant: frm.doc.name,
                        fee_type: 'Admission Fee',
                        docstatus: 1,
                        status: ['in', ['Paid', 'Partially Paid']]
                    },
                    fields: ['name', 'program', 'admission_cycle', 'offer_letter'],
                    order_by: 'modified desc',
                    limit: 1
                }).then(function (rows) {
                    if (!rows || !rows.length) {
                        frappe.msgprint({
                            title: __('No Eligible Fee Assignment'),
                            indicator: 'red',
                            message: __(
                                'No submitted Admission or Confirmation Fee assignment with status Paid or Partially Paid was found. ' +
                                'Please use the "Convert to Student" button on the Applicant Fee Assignment form.'
                            )
                        });
                        return;
                    }
                    const afa = rows[0];
                    frappe.confirm(
                        __('Convert applicant {0} to a Student Master? This will also update the user role.', [frm.doc.candidate_name || frm.doc.name]),
                        function () {
                            frappe.call({
                                method: 'slcm.api.service.applicant_to_student.convert_applicant_to_student',
                                args: {
                                    applicant_name:    frm.doc.name,
                                    program:           afa.program,
                                    admission_cycle:   afa.admission_cycle,
                                    offer_letter_name: afa.offer_letter || null
                                },
                                freeze: true,
                                freeze_message: __('Creating Student Master...'),
                                callback: function (r) {
                                    if (r.message) {
                                        const res = r.message;
                                        if (res.created) {
                                            frappe.show_alert({
                                                message: __('Student Master {0} created successfully.', [res.student_name]),
                                                indicator: 'green'
                                            }, 6);
                                            frm.reload_doc();
                                        } else {
                                            let d = new frappe.ui.Dialog({
                                                title: __('Student Already Exists'),
                                                fields: [
                                                    {
                                                        fieldname: 'msg',
                                                        fieldtype: 'HTML',
                                                        options: `<div style="padding: 10px; font-size: 13px;">
                                                            ${__('Student Master <b>{0}</b> already exists for this applicant.', [res.student_name])}
                                                            <br><br>
                                                            ${__('Would you like to mark this Applicant as Enrolled?')}
                                                        </div>`
                                                    }
                                                ],
                                                primary_action_label: __('Mark as Enrolled'),
                                                primary_action: function() {
                                                    d.get_primary_btn().prop('disabled', true);
                                                    frappe.call({
                                                        method: 'frappe.client.set_value',
                                                        args: {
                                                            doctype: 'Applicant',
                                                            name: frm.doc.name,
                                                            fieldname: 'status',
                                                            value: 'Enrolled'
                                                        },
                                                        callback: function(r) {
                                                            if (!r.exc) {
                                                                frappe.show_alert({message: __('Applicant marked as Enrolled.'), indicator: 'green'});
                                                                d.hide();
                                                                frm.reload_doc();
                                                            } else {
                                                                d.get_primary_btn().prop('disabled', false);
                                                            }
                                                        }
                                                    });
                                                }
                                            });
                                            d.show();
                                        }
                                    }
                                }
                            });
                        }
                    );
                });
            });
            student_btn.css({
                "background-color": "#1a3c6e",
                "color":            "#fff",
                "border-color":     "#1a3c6e",
                "font-weight":      "600",
            });
        }

        slcm_applicant_setup_country_state_city_queries(frm);
    },

    country: function (frm) {
        frm.set_value("state", "");
        frm.set_value("city", "");
    },

    state: function (frm) {
        frm.set_value("city", "");
    },

    nationality: function (frm) {
        if (frm.doc.nationality && frm.doc.nationality !== "Indian") {
            frm.set_value("foriegn_national", "Yes");
        } else if (frm.doc.nationality === "Indian" && frm.doc.foriegn_national === "Yes") {
            frm.set_value("foriegn_national", "No");
        }
    },

    foriegn_national: function (frm) {
        if (frm.doc.foriegn_national === "Yes" && frm.doc.nationality === "Indian") {
            frm.set_value("nationality", "");
        } else if (frm.doc.foriegn_national === "No" && frm.doc.nationality && frm.doc.nationality !== "Indian") {
            frm.set_value("nationality", "Indian");
        }
    },

    validate: function (frm) {
        if (frm.doc.status === "Draft") {
            frm.ignore_mandatory = true;
            return; // Skip all custom validations for draft
        } else {
            frm.ignore_mandatory = false;
        }

        let errors = [];

        // HSC Percentage
        if (frm.doc.hsc_percentage !== undefined && frm.doc.hsc_percentage !== null && frm.doc.hsc_percentage !== "") {
            if (frm.doc.hsc_percentage < 35) {
                errors.push(__("HSC percentage should be above 35%"));
            } else if (frm.doc.hsc_percentage > 100) {
                errors.push(__("HSC percentage cannot be more than 100%"));
            }
        }

        // UG CGPA (child table)
        if (frm.doc.ug_degree_details && frm.doc.ug_degree_details.length) {
            frm.doc.ug_degree_details.forEach(row => {
                if (row.ug_cgpa !== undefined && row.ug_cgpa !== null && row.ug_cgpa !== "") {
                    let is_cgpa = !!row.if_ug_cgpa;
                    let max_val = is_cgpa ? row.if_ug_cgpa : 100;
                    
                    if (row.ug_cgpa < (is_cgpa ? 4 : 35) || row.ug_cgpa > max_val) {
                        if (is_cgpa) {
                            errors.push(__("UG CGPA for degree \"{0}\" should be between 4 and {1}",
                                [row.ug_program || __("(unnamed)"), max_val]));
                        } else {
                            errors.push(__("UG Percentage for degree \"{0}\" should be between 35 and 100",
                                [row.ug_program || __("(unnamed)")]));
                        }
                    }
                }
            });
        }

        // PG CGPA (child table)
        if (frm.doc.pg_degree_details && frm.doc.pg_degree_details.length) {
            frm.doc.pg_degree_details.forEach(row => {
                if (row.pg_cgpa !== undefined && row.pg_cgpa !== null && row.pg_cgpa !== "") {
                    let is_cgpa = !!row.if_pg_cgpa;
                    let max_val = is_cgpa ? row.if_pg_cgpa : 100;
                    
                    if (row.pg_cgpa < (is_cgpa ? 4 : 35) || row.pg_cgpa > max_val) {
                        if (is_cgpa) {
                            errors.push(__("PG CGPA for degree \"{0}\" should be between 4 and {1}",
                                [row.pg_program || __("(unnamed)"), max_val]));
                        } else {
                            errors.push(__("PG Percentage for degree \"{0}\" should be between 35 and 100",
                                [row.pg_program || __("(unnamed)")]));
                        }
                    }
                }
            });
        }

        // When National test is selected, percentage is required
        if (frm.doc.national_test_name && (frm.doc.percentage === undefined || frm.doc.percentage === null || frm.doc.percentage === "")) {
            errors.push(__("Score or percentage is required when National test is selected."));
        }

        // Declaration must be accepted when submitting
        const has_declaration = frm.doc.declaration_undertaking || (
            frm.doc.authorisation_information &&
            frm.doc.agreement_to_communications &&
            frm.doc.agreement_withdrawal_conditions
        );
        if (frm.doc.status === "Submitted" && !has_declaration) {
            errors.push(__("You must accept the Declaration & Undertaking before submitting."));
        }

        // Campus preference duplicates
        const prefs = [frm.doc.first_preference, frm.doc.second_preference, frm.doc.third_preference]
            .filter(Boolean);
        if (new Set(prefs).size !== prefs.length) {
            errors.push(__("Campus preferences must all be unique. Please remove duplicate selections."));
        }

        if (frm.doc.nationality && frm.doc.foriegn_national) {
            if (frm.doc.nationality !== "Indian" && frm.doc.foriegn_national !== "Yes") {
                errors.push(__("If Nationality is not Indian, then 'Foreign National' must be Yes."));
            }
            if (frm.doc.foriegn_national === "Yes" && frm.doc.nationality === "Indian") {
                errors.push(__("If 'Foreign National' is Yes, Nationality cannot be Indian."));
            }
        }

        if (errors.length) {
            frappe.msgprint({
                title: __("Validation Error"),
                indicator: "red",
                message: errors.join("<br>")
            });
            frappe.validated = false;
        }
    },

    before_save: function (frm) {
        frm._previous_status = frm.doc ? frm.doc.status : null;
    },

    after_save: function (frm) {
        if (frm.doc.status === "Submitted" && frm._previous_status === "Draft") {
            frappe.show_alert({
                message: __("Application Submitted email sent to the applicant successfully."),
                indicator: "green"
            }, 5);
        }
    },

    // ── APPLICATION TYPE ──────────────────────
    application_type: function (frm) {
        const messages = {
            "External Test": __("CLAT workflow: Your CLAT rank will be imported from the Consortium."),
            "Internal Test": __("NLSAT workflow: You must appear for the NLSAT exam."),
            "PACE": __("PACE workflow: Admission is based on academic merit only.")
        };
        if (frm.doc.application_type && messages[frm.doc.application_type]) {
            frappe.show_alert({ message: messages[frm.doc.application_type], indicator: "blue" }, 6);
        }
    },

    // ── GUARDIAN REQUIRED ────────────────────
    guardian_required: function (frm) {
        frm.toggle_reqd("guardian_name", frm.doc.guardian_required);
        frm.toggle_reqd("guardian_mobile", frm.doc.guardian_required);
    },

    national_test_name: function (frm) {
        frm.toggle_reqd("percentage", !!frm.doc.national_test_name);
    },



    // ── HSC PERCENTAGE ───────────────────────
    hsc_percentage: function (frm) {
        const val = frm.doc.hsc_percentage;
        if (val === null || val === undefined || val === "") return;

        if (val < 35) {
            frappe.show_alert({ message: __("HSC percentage must be at least 35%."), indicator: "orange" });
            frm.set_value("hsc_percentage", null);
        } else if (val > 100) {
            frappe.show_alert({ message: __("HSC percentage cannot exceed 100%."), indicator: "orange" });
            frm.set_value("hsc_percentage", null);
        }
    },

    // ── CAMPUS PREFERENCES ───────────────────
    first_preference: function (frm) {
        if (frm.doc.first_preference &&
            frm.doc.first_preference === frm.doc.second_preference) {
            frappe.msgprint({
                title: __("Duplicate Preference"),
                indicator: "red",
                message: __("First and Second preference cannot be the same campus.")
            });
            frm.set_value("second_preference", "");
        }
    },

    second_preference: function (frm) {
        if (frm.doc.second_preference &&
            frm.doc.second_preference === frm.doc.first_preference) {
            frappe.msgprint({
                title: __("Duplicate Preference"),
                indicator: "red",
                message: __("Second preference cannot be the same as First preference.")
            });
            frm.set_value("second_preference", "");
            return;
        }
        if (frm.doc.second_preference &&
            frm.doc.second_preference === frm.doc.third_preference) {
            frappe.msgprint({
                title: __("Duplicate Preference"),
                indicator: "red",
                message: __("Second and Third preference cannot be the same campus.")
            });
            frm.set_value("third_preference", "");
        }
    },

    third_preference: function (frm) {
        if (frm.doc.third_preference && (
            frm.doc.third_preference === frm.doc.first_preference ||
            frm.doc.third_preference === frm.doc.second_preference
        )) {
            frappe.msgprint({
                title: __("Duplicate Preference"),
                indicator: "red",
                message: __("Third preference must differ from First and Second preference.")
            });
            frm.set_value("third_preference", "");
        }
    }
});

// ─────────────────────────────────────────────
//  UG Degree Detail — Child Table
// ─────────────────────────────────────────────
frappe.ui.form.on("UG Degree Detail", {
    ug_cgpa: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.ug_cgpa === null || row.ug_cgpa === undefined || row.ug_cgpa === "") return;

        if (row.ug_cgpa < 4 || row.ug_cgpa > 10) {
            frappe.show_alert({ message: __("UG CGPA must be between 4 and 10."), indicator: "orange" });
            frappe.model.set_value(cdt, cdn, "ug_cgpa", null);
        }
    }
});

// ─────────────────────────────────────────────
//  PG Degree Details — Child Table
// ─────────────────────────────────────────────
frappe.ui.form.on("PG Degree Details", {
    pg_cgpa: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.pg_cgpa === null || row.pg_cgpa === undefined || row.pg_cgpa === "") return;

        if (row.pg_cgpa < 4 || row.pg_cgpa > 10) {
            frappe.show_alert({ message: __("PG CGPA must be between 4 and 10."), indicator: "orange" });
            frappe.model.set_value(cdt, cdn, "pg_cgpa", null);
        }
    }
});