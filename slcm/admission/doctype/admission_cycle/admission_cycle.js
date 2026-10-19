function slcm_build_admission_cycle_conflict_message(overlaps) {
    if (!overlaps || !overlaps.length) {
        return "";
    }
    const intro = __("The selected date range overlaps with an existing admission cycle:");
    const bullets = overlaps.map((row) => {
        const safeLabel = frappe.utils.escape_html(row.cycle_name || row.name || "");
        const linkHtml = frappe.utils.get_form_link(
            "Admission Cycle",
            row.name,
            true,
            safeLabel
        );
        const sd = frappe.utils.escape_html(
            row.start_label ||
            (row.cycle_start_date
                ? frappe.datetime.str_to_user(row.cycle_start_date, false, true)
                : "—")
        );
        const ed = frappe.utils.escape_html(
            row.end_label ||
            (row.cycle_end_date
                ? frappe.datetime.str_to_user(row.cycle_end_date, false, true)
                : "—")
        );
        return `• ${linkHtml}: ${sd} ${__("to")} ${ed}`;
    });
    const footer = __("Please adjust the dates to avoid overlapping periods.");
    return `${intro}<br><br>${bullets.join("<br>")}<br><br>${footer}`;
}

function slcm_check_admission_cycle_date_overlap(frm) {
    if (!frm.doc.cycle_start_date || !frm.doc.cycle_end_date) {
        return;
    }
    if (!["Draft", "Active"].includes(frm.doc.status)) {
        return;
    }
    frappe.call({
        method: "slcm.admission.doctype.admission_cycle.admission_cycle.check_admission_cycle_date_overlap",
        args: {
            name: frm.doc.name,
            cycle_start_date: frm.doc.cycle_start_date,
            cycle_end_date: frm.doc.cycle_end_date,
            status: ["Draft", "Active"]
        },
        callback(r) {
            const m = r && r.message;
            if (!m || m.valid) {
                return;
            }
            let body;
            if (m.overlaps && m.overlaps.length) {
                body = slcm_build_admission_cycle_conflict_message(m.overlaps);
            } else {
                body =
                    (m.message && String(m.message).replace(/\n/g, "<br>")) ||
                    __("These dates overlap with another Active admission cycle.");
            }
            frappe.msgprint({
                title: __("Admission Cycle Dates Conflict"),
                message: body,
                indicator: "red",
            });
        },
    });
}

const slcm_debounced_cycle_overlap = frappe.utils.debounce(slcm_check_admission_cycle_date_overlap, 350);

let slcm_multi_campus_enabled = false;

function slcm_apply_program_campus_field_rules(frm) {
    const grid = frm.fields_dict.programs && frm.fields_dict.programs.grid;
    if (!grid) return;
    grid.update_docfield_property("campus", "hidden", 0);
    grid.update_docfield_property("campus", "reqd", 1);
    frm.refresh_field("programs");
}

function slcm_apply_application_date_bounds(frm) {
    const cycleStart = frm.doc.cycle_start_date ? new Date(frm.doc.cycle_start_date) : null;
    const cycleEnd = frm.doc.cycle_end_date ? new Date(frm.doc.cycle_end_date) : null;

    if (frm.fields_dict.application_start_date && frm.fields_dict.application_start_date.datepicker) {
        frm.fields_dict.application_start_date.datepicker.update({
            minDate: cycleStart || null,
            maxDate: cycleEnd || null,
        });
    }

    if (frm.fields_dict.application_end_date && frm.fields_dict.application_end_date.datepicker) {
        const minForAppEnd = frm.doc.application_start_date
            ? new Date(frm.doc.application_start_date)
            : (cycleStart || null);
        frm.fields_dict.application_end_date.datepicker.update({
            minDate: minForAppEnd,
            maxDate: cycleEnd || null,
        });
    }
}

frappe.ui.form.on("Admission Cycle", {

    refresh: function (frm) {
        frappe.db.get_single_value("Institution Settings", "enable_multi_campus")
            .then((val) => {
                slcm_multi_campus_enabled = parseInt(val || 0, 10) === 1;
                slcm_apply_program_campus_field_rules(frm);
            });

        // frm.set_query("academic_year", function () {
        //     return {
        //         filters: {
        //             status: "Active"
        //         }
        //     };
        // });
        frm.set_query("admission_year", function () {
            return {
                filters: {
                    is_active: 1
                }
            };
        });
        frm.set_query("application_form_template", function () {
            return {
                filters: {
                    doc_type: "Applicant"
                }
            };
        });


        const today = new Date(frappe.datetime.get_today());

        if (frm.fields_dict.cycle_start_date && frm.fields_dict.cycle_start_date.datepicker) {
            frm.fields_dict.cycle_start_date.datepicker.update({
                minDate: today,
            });
        }

        if (frm.fields_dict.cycle_end_date && frm.fields_dict.cycle_end_date.datepicker) {
            let until_min = frm.doc.cycle_start_date ? new Date(frm.doc.cycle_start_date) : today;
            frm.fields_dict.cycle_end_date.datepicker.update({
                minDate: until_min,
            });
        }
        slcm_apply_application_date_bounds(frm);

        // Status indicator
        const colors = { "Draft": "gray", "Active": "green", "Closed": "red" };
        frm.dashboard.set_headline_alert(
            __(frm.doc.status),
            colors[frm.doc.status] || "gray"
        );

        // Override the Frappe breadcrumb/header status pill (which defaults to
        // docstatus-derived labels like "Cancelled") with the custom status field.
        frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "gray");


        // Intro messages
        if (frm.doc.status === "Active") {
            frm.set_intro(__("This admission cycle is currently <b>Active</b>. It is visible on the applicant portal."));
        } else if (frm.doc.status === "Closed") {
            frm.set_intro(__("This admission cycle is <b>Closed</b>. No more applications are being accepted."), "red");
        } else {
            frm.set_intro(__("This cycle is currently in <b>Draft</b>. It will not be visible on the portal until it is activated."), "blue");
        }

        // Program count warning
        if (!frm.is_new()) {
            const active_programs = (frm.doc.programs || [])
                .filter(p => p.is_active).length;
            if (frm.doc.status === "Active" && active_programs === 0) {
                frm.dashboard.set_headline_alert(
                    __("No programs added. Portal will show empty."),
                    "orange"
                );
            } else if (active_programs > 0) {
                frm.dashboard.set_headline_alert(
                    __("{0} program(s) visible on portal", [active_programs]),
                    "green"
                );
            }
        }

        // Set queries for Admission Cycle Stage child table
        const stage_status_fields = ["activate_status", "completed_status", "closed_status"];
        stage_status_fields.forEach(field => {
            frm.set_query(field, "stages", function (doc, cdt, cdn) {
                let row = locals[cdt][cdn];
                if (!row.stage_type) {
                    return {};
                }
                return {
                    filters: {
                        "stage_type": row.stage_type
                    }
                };
            });
        });

        frm.set_query("programme", "entrance_test_details", function (doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            let filters = { "entrance_test": 1 };
            if (row.programme_level) {
                filters["level_of_study"] = row.programme_level;
            }
            return {
                filters: filters
            };
        });

        // Quick actions
        if (!frm.is_new()) {
            if (frm.doc.status === "Draft") {
                frm.add_custom_button(__("Activate"), function () {
                    slcm_run_activation_checks(frm, () => {
                        frappe.confirm(slcm_build_activate_confirm_msg(frm), () => {
                            frappe.call({
                                method: "slcm.admission.doctype.admission_cycle.admission_cycle.activate_cycle",
                                args: { name: frm.doc.name },
                                callback: function (r) {
                                    if (r.message && r.message.success) {
                                        frappe.show_alert({
                                            message: r.message.message,
                                            indicator: "green"
                                        });
                                    } else if (r.message && !r.message.success) {
                                        frappe.msgprint({
                                            title: __("Cannot Activate"),
                                            message: r.message.message,
                                            indicator: "red"
                                        });
                                    }
                                    frm.reload_doc();
                                }
                            });
                        });
                    });
                }, __("Actions"));
            }

            if (frm.doc.status === "Active") {
                frm.add_custom_button(__("Close Cycle"), function () {

                    const today = frappe.datetime.get_today();
                    const cycle_end = frm.doc.cycle_end_date;

                    const build_close_confirm_msg = () => {
                        let msg = "";

                        if (cycle_end && today < cycle_end) {
                            const days_remaining = frappe.datetime.get_diff(cycle_end, today);
                            msg += __("⚠️ This cycle is scheduled to end on <b>{0}</b>, which is <b>{1} day(s)</b> from today. Closing it early will stop all applications immediately.<br><br>",
                                [cycle_end, days_remaining]);
                        } else if (cycle_end && today > cycle_end) {
                            const days_past = frappe.datetime.get_diff(today, cycle_end);
                            msg += __("ℹ️ This cycle's end date <b>{0}</b> passed <b>{1} day(s)</b> ago.<br><br>",
                                [cycle_end, days_past]);
                        }

                        msg += __("Closing the cycle will set the document status to <b>Closed</b> and no more applications will be accepted. Do you want to continue?");

                        return msg;
                    };

                    frappe.confirm(build_close_confirm_msg(), function () {
                        frappe.call({
                            method: "slcm.admission.doctype.admission_cycle.admission_cycle.close_cycle",
                            args: {
                                name: frm.doc.name
                            },
                            callback: function (r) {
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: r.message.message,
                                        indicator: "green"
                                    });
                                } else if (r.message && !r.message.success) {
                                    frappe.msgprint({
                                        title: __("Error"),
                                        message: r.message.message,
                                        indicator: "red"
                                    });
                                }
                                frm.reload_doc();
                            }
                        });
                    });
                }, __("Actions"));
            }

            if (frm.doc.status === "Closed") {
                frm.set_read_only();
                frm.add_custom_button(__("Reopen Cycle"), function () {
                    frappe.confirm(__("Are you sure you want to reopen this admission cycle?"), function () {
                        frappe.call({
                            method: "slcm.admission.doctype.admission_cycle.admission_cycle.reopen_cycle",
                            args: {
                                name: frm.doc.name
                            },
                            callback: function (r) {
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: r.message.message,
                                        indicator: "green"
                                    });
                                    frm.reload_doc();
                                } else if (r.message) {
                                    frappe.msgprint({
                                        message: r.message.message,
                                        title: __("Cannot Reopen"),
                                        indicator: "red"
                                    });
                                }
                            }
                        });
                    });
                }, __("Actions"));
            }
        }
    },

    status: function (frm) {
        if (frm.doc.status === "Active") {
            // Check for other Active cycles
            frappe.db.get_value("Admission Cycle", {
                status: "Active",
                name: ["!=", frm.doc.name]
            }, "cycle_name", (r) => {
                if (r && r.cycle_name) {
                    frappe.msgprint({
                        message: __("Cycle <b>{0}</b> is already Active. Close it before activating this one.", [r.cycle_name]),
                        title: __("Active Cycle Conflict"),
                        indicator: "red"
                    });
                    frm.set_value("status", "Draft");
                    return;
                }
                slcm_check_admission_cycle_date_overlap(frm);
                frappe.show_alert({
                    message: __("Cycle activated. Programs will appear on the portal."),
                    indicator: "green"
                }, 5);
            });
        }
    },
    cycle_start_date: function (frm) {
        if (frm.doc.cycle_start_date && frm.fields_dict.cycle_end_date && frm.fields_dict.cycle_end_date.datepicker) {
            frm.fields_dict.cycle_end_date.datepicker.update({
                minDate: new Date(frm.doc.cycle_start_date),
            });
        }
        slcm_apply_application_date_bounds(frm);
        if (frm.doc.application_start_date && frm.doc.application_start_date < frm.doc.cycle_start_date) {
            frm.set_value("application_start_date", frm.doc.cycle_start_date);
        }
        slcm_debounced_cycle_overlap(frm);
    },

    cycle_end_date: function (frm) {
        slcm_apply_application_date_bounds(frm);
        if (frm.doc.application_end_date && frm.doc.application_end_date > frm.doc.cycle_end_date) {
            frm.set_value("application_end_date", frm.doc.cycle_end_date);
        }
        slcm_debounced_cycle_overlap(frm);
    },
    application_start_date: function (frm) {
        slcm_apply_application_date_bounds(frm);
        if (frm.doc.cycle_start_date && frm.doc.application_start_date && frm.doc.application_start_date < frm.doc.cycle_start_date) {
            frappe.msgprint(__("Application Start Date cannot be before Cycle Start Date."));
            frm.set_value("application_start_date", frm.doc.cycle_start_date);
            return;
        }
        if (frm.doc.cycle_end_date && frm.doc.application_start_date && frm.doc.application_start_date > frm.doc.cycle_end_date) {
            frappe.msgprint(__("Application Start Date cannot be after Cycle End Date."));
            frm.set_value("application_start_date", "");
            return;
        }
        if (frm.doc.application_end_date && frm.doc.application_start_date && frm.doc.application_start_date > frm.doc.application_end_date) {
            frm.set_value("application_end_date", frm.doc.application_start_date);
        }
    },
    application_end_date: function (frm) {
        slcm_apply_application_date_bounds(frm);
        if (frm.doc.cycle_end_date && frm.doc.application_end_date && frm.doc.application_end_date > frm.doc.cycle_end_date) {
            frappe.msgprint(__("Application End Date cannot be after Cycle End Date."));
            frm.set_value("application_end_date", frm.doc.cycle_end_date);
            return;
        }
        if (frm.doc.cycle_start_date && frm.doc.application_end_date && frm.doc.application_end_date < frm.doc.cycle_start_date) {
            frappe.msgprint(__("Application End Date cannot be before Cycle Start Date."));
            frm.set_value("application_end_date", "");
            return;
        }
        if (frm.doc.application_start_date && frm.doc.application_end_date && frm.doc.application_end_date < frm.doc.application_start_date) {
            frappe.msgprint(__("Application End Date cannot be before Application Start Date."));
            frm.set_value("application_end_date", frm.doc.application_start_date);
        }
    },

    before_submit: function (frm) {
        if (!frm.flags) frm.flags = {};
        if (!frm.flags.ignore_submit_check && frm.doc.status !== "Active") {
            frappe.validated = false;
            slcm_run_activation_checks(frm, () => {
                frappe.confirm(slcm_build_activate_confirm_msg(frm), () => {
                    frm.set_value("status", "Active");
                    if (!frm.flags) frm.flags = {};
                    frm.flags.ignore_submit_check = true;
                    frm.save("Submit");
                });
            });
        }
    },
});

frappe.ui.form.on("Admission Cycle Program", {
    campus: function (frm, cdt, cdn) {
        if (!slcm_multi_campus_enabled) return;
        const row = locals[cdt][cdn];
        const program = row.program;
        const campus = row.campus;
        if (!program || !campus) return;

        const duplicate = (frm.doc.programs || []).find(
            d => d.name !== row.name && d.program === program && d.campus === campus
        );
        if (duplicate) {
            frappe.msgprint({
                title: __("Duplicate Entry"),
                indicator: "red",
                message: __("Program <b>{0}</b> with campus <b>{1}</b> already exists at row {2}.", [row.program_name || row.program, campus, duplicate.idx])
            });
            frappe.model.set_value(cdt, cdn, "campus", "");
        }
    },

    add_reservation_policy: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.campus) {
            frappe.msgprint(__("Please select Campus before adding Reservation Policy."));
            return;
        }

        if (frm.is_new() || frm.is_dirty()) {
            frm.save().then(() => {
                open_reservation_policy(frm, row);
            });
        } else {
            open_reservation_policy(frm, row);
        }
    },

    add_program_media: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.program_media) {
            open_program_media(frm, row);
        } else {
            frappe.msgprint(__("Program media already exists"));
        }


    }
});

frappe.ui.form.on("Admission Cycle Stage", {
    stage_type: function (frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "activate_status", null);
        frappe.model.set_value(cdt, cdn, "completed_status", null);
        frappe.model.set_value(cdt, cdn, "closed_status", null);
    },
    stage_name: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (row.stage_name) {
            let duplicate = (frm.doc.stages || []).find(
                d => d.name !== row.name && d.stage_name === row.stage_name
            );

            if (duplicate) {
                frappe.msgprint({
                    title: __("Duplicate Entry"),
                    indicator: "red",
                    message: __("Stage <b>{0}</b> is already added at row {1}.", [row.stage_name, duplicate.idx])
                });

                frappe.model.set_value(cdt, cdn, "stage_name", null);
            }
        }
    }
});
frappe.ui.form.on("Entrance Test Details", {
    programme_level: function (frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "programme", null);
    }
});

function open_reservation_policy(frm, row) {
    let vertical_rows = [];
    let horizontal_rows = [];
    let compartmental_rows = [];
    let existing_policy_name = null;

    function sync_tables() {
        // Vertical
        dialog.$wrapper.find(".vertical-table tbody tr").each(function (idx) {
            const comp_cat_text = $(this).find(".comp-category-btn").text().trim();
            vertical_rows[idx] = {
                reservation_quota: $(this).find(".category").val(),
                category_name: $(this).find(".category-name-btn").text().trim(),
                compartmentalized_category: (comp_cat_text === __("Pick") || comp_cat_text === "None") ? "" : comp_cat_text,
                priority: parseInt($(this).find(".priority").val()) || (idx + 1),
                percentage: parseFloat($(this).find(".percentage").val()) || 0,
                seats: parseInt($(this).find(".allocated_seats").val()) || 0,
                compartmentalized_waitlist_seats: parseInt($(this).find(".comp_waitlist").val()) || 0,
                application_fee: parseFloat($(this).find(".application_fee").val()) || 0,
                min_percentile: parseFloat($(this).find(".min_percentile").val()) || 0
            };
        });
        // Horizontal
        dialog.$wrapper.find(".horizontal-table tbody tr").each(function (idx) {
            horizontal_rows[idx] = {
                category_name: $(this).find(".category-name-btn").text().trim(),
                percentage: parseFloat($(this).find(".percentage").val()) || 0,
                seats: parseInt($(this).find(".seats").val()) || 0
            };
        });
        // Compartmental
        dialog.$wrapper.find(".compartmental-table tbody tr").each(function (idx) {
            compartmental_rows[idx] = {
                category_name: $(this).find(".category-name-btn").text().trim(),
                percentage: parseFloat($(this).find(".percentage").val()) || 0,
                seats: parseInt($(this).find(".seats").val()) || 0
            };
        });
    }

    function calculate_seats(table_class, idx) {
        const total = dialog.get_value("total_seats") || 0;
        const $row = dialog.$wrapper.find(`.${table_class} tbody tr`).eq(idx);
        const percentage = parseFloat($row.find(".percentage").val()) || 0;
        const seats = Math.floor((total * percentage) / 100);
        $row.find(".allocated_seats, .seats").val(seats);
    }

    function open_category_picker(table_class, idx) {
        let res_type = "Vertical";
        if (table_class === "horizontal-table") res_type = "Horizontal";
        if (table_class === "compartmental-table") res_type = "Compartmentalised Horizontal";

        const p = frappe.prompt([{
            fieldtype: "Link", fieldname: "val", label: __("Category Name"),
            options: "Admission Category", reqd: 1,
            get_query: () => {
                return {
                    filters: { "reservation_type": res_type, "is_active": 1 }
                };
            }
        }], function (values) {
            dialog.$wrapper.find(`.${table_class} tbody tr`).eq(idx).find(".category-name-btn").text(values.val);
            sync_tables();
        }, __("Select Category"));
    }

    function open_comp_category_picker(idx) {
        const p = frappe.prompt([{
            fieldtype: "Link", fieldname: "val", label: __("Compartmentalised Category"),
            options: "Admission Category",
            get_query: () => {
                return {
                    filters: { "reservation_type": "Compartmentalised Horizontal", "is_active": 1 }
                };
            }
        }], function (values) {
            dialog.$wrapper.find(`.vertical-table tbody tr`).eq(idx).find(".comp-category-btn").text(values.val || "None");
            sync_tables();
        }, __("Select Compartmentalised Category"));
    }

    function render_vertical() {
        const rows = (vertical_rows.length ? vertical_rows : [{}]).map((r, idx) => `
            <tr>
                <td style="width: 10%;"><select class="form-control category" style="height: 32px;"><option value="General" ${r.reservation_quota === "General" ? "selected" : ""}>General</option><option value="Government" ${r.reservation_quota === "Government" ? "selected" : ""}>Government</option><option value="Management" ${r.reservation_quota === "Management" ? "selected" : ""}>Management</option></select></td>
                <td style="width: 15%;"><button class="btn btn-default btn-sm category-name-btn" style="width:100%; height: 32px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${r.category_name || __("Pick")}</button></td>
                <td style="width: 15%;"><button class="btn btn-default btn-sm comp-category-btn" style="width:100%; height: 32px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${r.compartmentalized_category || "None"}</button></td>
                <td style="width: 8%;"><input type="number" class="form-control priority" style="height: 32px;" value="${r.priority || (idx + 1)}"></td>
                <td style="width: 8%;"><input type="number" class="form-control percentage" style="height: 32px;" value="${r.percentage || ""}"></td>
                <td style="width: 8%;"><input type="number" class="form-control allocated_seats" style="height: 32px;" value="${r.seats || ""}" readonly></td>
                <td style="width: 10%;"><input type="number" class="form-control comp_waitlist" style="height: 32px;" value="${r.compartmentalized_waitlist_seats || ""}"></td>
                <td style="width: 12%;"><input type="number" class="form-control application_fee" style="height: 32px;" value="${r.application_fee || r.application_fee_for_indian || ""}"></td>
                <td style="width: 10%;"><input type="number" class="form-control min_percentile" style="height: 32px;" value="${r.min_percentile || ""}"></td>
                <td style="width: 4%; text-align: center;"><button class="btn btn-danger btn-xs remove-row" style="margin-top: 5px;"><i class="fa fa-times"></i></button></td>
            </tr>`).join("");
        dialog.fields_dict.vertical_html.$wrapper.html(`
            <div style="margin-bottom: 15px;">
                <table class="table table-bordered vertical-table" style="table-layout: fixed; width: 100%;">
                    <thead>
                        <tr style="background-color: #f8f9fa;">
                            <th style="width: 10%; font-size: 11px;">Quota</th>
                            <th style="width: 15%; font-size: 11px;">Category</th>
                            <th style="width: 15%; font-size: 11px;">Compartmentalised</th>
                            <th style="width: 8%; font-size: 11px;">Priority</th>
                            <th style="width: 8%; font-size: 11px;">Percentage</th>
                            <th style="width: 8%; font-size: 11px;">Seats</th>
                            <th style="width: 10%; font-size: 11px;">Comp Waitlist</th>
                            <th style="width: 12%; font-size: 11px;">Application Fee</th>
                            <th style="width: 10%; font-size: 11px;">Min Percentile Cutoff</th>
                            <th style="width: 4%;"></th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                <button class="btn btn-xs btn-primary add-vertical" style="margin-top: -10px;"><i class="fa fa-plus"></i> ${__("Add Row")}</button>
            </div>`);
    }

    function render_sub_table(table_class, rows_data, field_dict) {
        const rows = (rows_data.length ? rows_data : [{}]).map((r, idx) => `
            <tr>
                <td style="width: 40%;"><button class="btn btn-default btn-sm category-name-btn" style="width:100%; height: 32px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${r.category_name || __("Pick")}</button></td>
                <td style="width: 30%;"><input type="number" class="form-control percentage" style="height: 32px;" value="${r.percentage || ""}"></td>
                <td style="width: 25%;"><input type="number" class="form-control seats" style="height: 32px;" value="${r.seats || ""}" readonly></td>
                <td style="width: 5%; text-align: center;"><button class="btn btn-danger btn-xs remove-row" style="margin-top: 5px;"><i class="fa fa-times"></i></button></td>
            </tr>`).join("");
        field_dict.$wrapper.html(`
            <div style="margin-bottom: 15px;">
                <table class="table table-bordered ${table_class}" style="table-layout: fixed; width: 100%;">
                    <thead>
                        <tr style="background-color: #f8f9fa;">
                            <th style="width: 40%; font-size: 12px;">Category Name</th>
                            <th style="width: 30%; font-size: 12px;">Percentage (%)</th>
                            <th style="width: 25%; font-size: 12px;">Seats</th>
                            <th style="width: 5%;"></th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                <button class="btn btn-xs btn-primary add-row" data-table="${table_class}" style="margin-top: -10px;"><i class="fa fa-plus"></i> ${__("Add Row")}</button>
            </div>`);
    }

    const dialog = new frappe.ui.Dialog({
        title: __("Reservation Policy"), size: "large",
        fields: [
            { fieldtype: "Link", fieldname: "admission_cycle", label: __("Cycle"), options: "Admission Cycle", read_only: 1, default: frm.doc.name },
            { fieldtype: "Column Break" },
            { fieldtype: "Link", fieldname: "program", label: __("Programme"), options: "Programme", read_only: 1, default: row.program },
            { fieldtype: "Column Break" },
            { fieldtype: "Link", fieldname: "campus", label: __("Campus"), options: "Campus", read_only: 1, default: row.campus },
            { fieldtype: "Column Break" },
            { fieldtype: "Int", fieldname: "total_seats", label: __("Total Seats"), read_only: 1, default: row.seats },
            { fieldtype: "Section Break" },
            { fieldtype: "Link", fieldname: "payment_gateway", label: __("Payment Gateway"), options: "Payment Gateway", reqd: 1 },
            { fieldtype: "Column Break" },
            { fieldtype: "Link", fieldname: "payment_receipt_template", label: __("Payment Receipt Template"), options: "Print Format", reqd: 1 },
            { fieldtype: "Column Break" },
            { fieldtype: "Select", fieldname: "status", label: __("Status"), options: ["Draft", "Active", "Locked"], default: "Active", reqd: 1 },
            { fieldtype: "Section Break" },
            { fieldtype: "Attach", fieldname: "policy_document", label: __("Policy Document") },
            { fieldtype: "Section Break", label: __("Main Categories (Vertical)") },
            { fieldtype: "HTML", fieldname: "vertical_html" },
            { fieldtype: "Section Break", label: __("Horizontal Reservations") },
            { fieldtype: "HTML", fieldname: "horizontal_html" },
            { fieldtype: "Section Break", label: __("Compartmentalised Reservations") },
            { fieldtype: "HTML", fieldname: "compartmental_html" }
        ],
        primary_action_label: __("Save Reservation Policy"),
        primary_action: () => {
            sync_tables();
            frappe.call({
                method: "slcm.admission.doctype.admission_cycle_program.admission_cycle_program.save_categories",
                args: {
                    admission_cycle: dialog.get_value("admission_cycle"),
                    program: dialog.get_value("program"),
                    campus: dialog.get_value("campus"),
                    total_seats: dialog.get_value("total_seats"),
                    status: dialog.get_value("status"),
                    payment_gateway: dialog.get_value("payment_gateway"),
                    payment_receipt_template: dialog.get_value("payment_receipt_template"),
                    policy_document: dialog.get_value("policy_document"),
                    reservation_rows: JSON.stringify(vertical_rows),
                    horizontal_rows: JSON.stringify(horizontal_rows),
                    compartmental_rows: JSON.stringify(compartmental_rows),
                    existing_policy: existing_policy_name
                },
                callback: (r) => {
                    if (r.message) {
                        frappe.model.set_value(row.doctype, row.name, "reservation_policy", r.message.policy_name);
                        frm.refresh_field("programs");
                        dialog.hide();
                    }
                }
            });
        }
    });

    dialog.$wrapper.on("click", ".add-vertical", () => { sync_tables(); vertical_rows.push({}); render_vertical(); });
    dialog.$wrapper.on("click", ".add-row", (e) => {
        const tbl = $(e.currentTarget).data("table");
        sync_tables();
        if (tbl === "horizontal-table") horizontal_rows.push({});
        else compartmental_rows.push({});
        render_sub_table(tbl, tbl === "horizontal-table" ? horizontal_rows : compartmental_rows, tbl === "horizontal-table" ? dialog.fields_dict.horizontal_html : dialog.fields_dict.compartmental_html);
    });
    dialog.$wrapper.on("click", ".remove-row", (e) => { $(e.currentTarget).closest("tr").remove(); sync_tables(); });
    dialog.$wrapper.on("click", ".category-name-btn", (e) => {
        const $tr = $(e.currentTarget).closest("tr");
        const idx = $tr.index();
        // Specifically look for classes ending in -table to avoid matching the generic 'table' class
        const tbl = $tr.closest("table").attr("class").split(" ").find(c => c.endsWith("-table"));
        open_category_picker(tbl, idx);
    });
    dialog.$wrapper.on("click", ".comp-category-btn", (e) => {
        const $tr = $(e.currentTarget).closest("tr");
        const idx = $tr.index();
        open_comp_category_picker(idx);
    });
    dialog.$wrapper.on("input", ".percentage", (e) => {
        const $tr = $(e.currentTarget).closest("tr");
        const idx = $tr.index();
        // Specifically look for classes ending in -table
        const tbl = $tr.closest("table").attr("class").split(" ").find(c => c.endsWith("-table"));
        calculate_seats(tbl, idx);
    });

    dialog.show();
    dialog.$wrapper.find('.modal-dialog').css("max-width", "85%");

    frappe.call({
        method: "frappe.client.get_value",
        args: {
            doctype: "Programme Reservation Policy",
            filters: { admission_cycle: frm.doc.name, program: row.program, campus: row.campus },
            fieldname: "name"
        },
        callback: (r) => {
            if (r.message && r.message.name) {
                frappe.call({
                    method: "frappe.client.get",
                    args: {
                        doctype: "Programme Reservation Policy",
                        name: r.message.name
                    },
                    callback: (res) => {
                        if (res.message) {
                            const d = res.message;
                            existing_policy_name = d.name;
                            dialog.set_value("payment_gateway", d.payment_gateway);
                            dialog.set_value("payment_receipt_template", d.payment_receipt_template);
                            dialog.set_value("policy_document", d.policy_document);
                            vertical_rows = d.categories || [];
                            horizontal_rows = d.horizontal_reservations || [];
                            compartmental_rows = d.compartmental_reservations || [];
                            render_vertical();
                            render_sub_table("horizontal-table", horizontal_rows, dialog.fields_dict.horizontal_html);
                            render_sub_table("compartmental-table", compartmental_rows, dialog.fields_dict.compartmental_html);
                        }
                    }
                });
            } else {
                render_vertical();
                render_sub_table("horizontal-table", horizontal_rows, dialog.fields_dict.horizontal_html);
                render_sub_table("compartmental-table", compartmental_rows, dialog.fields_dict.compartmental_html);
            }
        }
    });
}

function open_program_media(frm, row) {
    let table_rows = [];
    let existing_media_name = null;

    function sync_table_rows() {
        dialog.$wrapper.find("tbody tr").each(function () {
            const idx = parseInt($(this).find(".media_type").data("idx"));
            if (isNaN(idx)) return;
            table_rows[idx] = {
                media_type: $(this).find(".media_type").val(),
                file_url: table_rows[idx] ? table_rows[idx].file_url : "",
                sequence: parseInt($(this).find(".sequence").val()) || 0,
                caption: $(this).find(".caption").val()
            };
        });
    }

    function open_file_picker(idx) {
        frappe.prompt(
            [
                {
                    fieldtype: "Attach",
                    fieldname: "file_url",
                    label: __("Upload File"),
                    reqd: 1,
                    default: table_rows[idx] ? table_rows[idx].file_url : ""
                }
            ],
            function (values) {
                if (values.file_url) {
                    table_rows[idx].file_url = values.file_url;
                    dialog.$wrapper
                        .find(`.file-btn[data-idx="${idx}"]`)
                        .text(values.file_url.split("/").pop());
                }
            },
            __("Upload File"),
            __("Attach")
        );
    }

    function render_table() {
        const rows_html = table_rows.map((r, idx) => `
        <tr>
            <td>
                <select class="form-control media_type" data-idx="${idx}">
                    <option value="">Select</option>
                    <option value="Image" ${r.media_type === "Image" ? "selected" : ""}>Image</option>
                    <option value="Video" ${r.media_type === "Video" ? "selected" : ""}>Video</option>
                </select>
            </td>
            <td>
                <button class="btn btn-default btn-sm file-btn" data-idx="${idx}"
                    style="width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                    ${r.file_url ? frappe.utils.escape_html(r.file_url.split("/").pop()) : __("Upload File")}
                </button>
            </td>
            <td>
                <input type="number" class="form-control sequence" data-idx="${idx}"
                    value="${r.sequence || ""}">
            </td>
            <td>
                <input type="text" class="form-control caption" data-idx="${idx}"
                    value="${frappe.utils.escape_html(r.caption || "")}">
            </td>
            <td style="text-align:center; vertical-align:middle;">
                <button class="btn btn-danger btn-xs remove-row" data-idx="${idx}">Remove</button>
            </td>
        </tr>
        `).join("");

        dialog.fields_dict.media_table.$wrapper.html(`
            <div style="overflow-x:auto; margin-bottom:10px;">
                <table class="table table-bordered" style="table-layout:fixed; width:100%;">
                    <thead>
                        <tr>
                            <th style="width:20%;">Media Type</th>
                            <th style="width:20%;">File</th>
                            <th style="width:15%;">Sequence</th>
                            <th style="width:25%;">Caption</th>
                            <th style="width:20%; text-align:center;">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows_html}
                    </tbody>
                </table>
            </div>
            <button class="btn btn-primary btn-sm" id="add-media-row-btn">+ Add Row</button>
        `);
    }

    function validate_and_save() {
        sync_table_rows();

        if (!table_rows.length) {
            frappe.msgprint(__("Please add at least one media item."));
            return;
        }

        for (let i = 0; i < table_rows.length; i++) {
            const r = table_rows[i];
            const rowNum = i + 1;

            if (!r.media_type) {
                frappe.msgprint(__(`Row ${rowNum}: Media Type is mandatory.`));
                return;
            }

            if (!r.file_url || r.file_url.trim() === "") {
                frappe.msgprint(__(`Row ${rowNum}: File is mandatory.`));
                return;
            }
        }

        // If existing record, confirm before updating
        if (existing_media_name) {
            frappe.confirm(
                __(`A Program Media record (<strong>${existing_media_name}</strong>) already exists for this program. Do you want to update it?`),
                () => do_save(),
                () => { /* user cancelled — do nothing */ }
            );
        } else {
            do_save();
        }
    }

    function do_save() {
        frappe.call({
            method: "slcm.admission.doctype.admission_cycle_program.admission_cycle_program.save_program_media",
            args: {
                program: dialog.get_value("program"),
                active: dialog.get_value("active"),
                brochure_pdf: dialog.get_value("brochure_pdf"),
                media_rows: table_rows,
                parent_doctype: row.doctype,
                parent_name: row.name,
                existing_media: existing_media_name || null  // backend uses this to update vs insert
            },
            freeze: true,
            freeze_message: __("Saving Program Media..."),
            callback(r) {
                if (!r.exc && r.message) {
                    frappe.model.set_value(
                        row.doctype,
                        row.name,
                        "program_media",
                        r.message
                    );
                    frm.refresh_field("programs");
                    frappe.show_alert({
                        message: existing_media_name
                            ? __("Program Media Updated: ") + r.message
                            : __("Program Media Saved: ") + r.message,
                        indicator: "green"
                    });
                    dialog.hide();
                }
            }
        });
    }

    function link_existing_media() {
        if (!existing_media_name) return;

        frappe.confirm(
            __(`Do you want to link the existing Program Media (<strong>${existing_media_name}</strong>) without making any changes?`),
            () => {
                frappe.model.set_value(
                    row.doctype,
                    row.name,
                    "program_media",
                    existing_media_name
                );
                frm.refresh_field("programs");
                frappe.show_alert({
                    message: __("Linked existing Program Media: ") + existing_media_name,
                    indicator: "blue"
                });
                dialog.hide();
            }
        );
    }

    function update_dialog_buttons() {
        if (existing_media_name) {
            dialog.set_primary_action(__("Update Program Media"), validate_and_save);

            if (!dialog.$wrapper.find(".btn-link-existing-media").length) {
                dialog.add_custom_action(__("Link Existing"), link_existing_media, "btn-link-existing-media");
            }
        } else {
            dialog.set_primary_action(__("Save Program Media"), validate_and_save);
        }
    }

    const dialog = new frappe.ui.Dialog({
        title: __("Program Media"),
        size: "large",
        fields: [
            {
                fieldtype: "Link",
                fieldname: "program",
                label: __("Programme"),
                options: "Programme",
                read_only: 1,
                default: row.program
            },
            { fieldtype: "Column Break" },
            {
                fieldtype: "Check",
                fieldname: "active",
                label: __("Active"),
                default: 1
            },
            { fieldtype: "Column Break" },
            {
                fieldtype: "Attach",
                fieldname: "brochure_pdf",
                label: __("Brochure PDF"),
                default: ""
            },
            { fieldtype: "Section Break" },
            {
                fieldtype: "HTML",
                fieldname: "media_table"
            }
        ],
        primary_action_label: __("Save Program Media"),
        primary_action: validate_and_save
    });

    dialog.show();
    render_table();

    // On dialog open — check if Program Media already exists for this program
    frappe.call({
        method: "frappe.client.get_value",
        args: {
            doctype: "Program Media",
            filters: { name: row.program },
            fieldname: ["name", "is_active", "brochure_pdf"]
        },
        callback(res) {
            if (res.message && res.message.name) {
                frappe.call({
                    method: "frappe.client.get",
                    args: {
                        doctype: "Program Media",
                        name: res.message.name
                    },
                    callback(r) {
                        if (r.message) {
                            const doc = r.message;

                            // Store existing record name
                            existing_media_name = doc.name;

                            dialog.set_value("active", doc.is_active);
                            dialog.set_value("brochure_pdf", doc.brochure_pdf || "");

                            table_rows = (doc.media_gallery || []).map(item => ({
                                media_type: item.media_type || "",
                                file_url: item.file || "",
                                sequence: item.sequence || 0,
                                caption: item.caption || ""
                            }));

                            render_table();

                            // Swap buttons to Update + Link Existing
                            update_dialog_buttons();

                            frappe.show_alert({
                                message: __("Loaded existing Program Media for: ") + row.program,
                                indicator: "blue"
                            });
                        }
                    }
                });
            }
            // No existing record — stays as new entry mode
        }
    });

    // Open file picker on button click
    dialog.$wrapper.on("click", ".file-btn", function () {
        sync_table_rows();
        const idx = parseInt($(this).data("idx"));
        open_file_picker(idx);
    });

    // Add row
    dialog.$wrapper.on("click", "#add-media-row-btn", function () {
        sync_table_rows();
        table_rows.push({
            media_type: "",
            file_url: "",
            sequence: "",
            caption: ""
        });
        render_table();
    });

    // Remove row
    dialog.$wrapper.on("click", ".remove-row", function () {
        sync_table_rows();
        const idx = parseInt($(this).data("idx"));
        table_rows.splice(idx, 1);
        render_table();
    });
}
function slcm_run_activation_checks(frm, callback) {
    // 1. Check for any other Active cycle first (Global rule)
    frappe.db.get_value("Admission Cycle", {
        status: "Active",
        name: ["!=", frm.doc.name]
    }, "cycle_name", (r) => {
        if (r && r.cycle_name) {
            frappe.msgprint({
                message: __("Cycle <b>{0}</b> is already Active. Close it before activating this one.", [r.cycle_name]),
                title: __("Active Cycle Conflict"),
                indicator: "red",
                primary_action: {
                    label: __("Go to {0}", [r.cycle_name]),
                    action: () => {
                        frappe.set_route("Form", "Admission Cycle", r.cycle_name);
                    }
                }
            });
            return;
        }

        // 2. Check for existing active cycle date overlaps (Secondary rule)
        frappe.call({
            method: "slcm.admission.doctype.admission_cycle.admission_cycle.check_admission_cycle_date_overlap",
            args: {
                name: frm.doc.name,
                cycle_start_date: frm.doc.cycle_start_date,
                cycle_end_date: frm.doc.cycle_end_date,
                status: "Active"
            },
            callback: (r) => {
                const m = r && r.message;
                if (m && !m.valid) {
                    let body = m.overlaps && m.overlaps.length
                        ? slcm_build_admission_cycle_conflict_message(m.overlaps)
                        : (m.message || __("These dates overlap with another Active admission cycle."));

                    frappe.msgprint({
                        message: body,
                        title: __("Active Cycle Conflict"),
                        indicator: "red"
                    });
                    return;
                }
                if (callback) callback();
            }
        });
    });
}

function slcm_build_activate_confirm_msg(frm) {
    const today = frappe.datetime.get_today();
    const cycle_start = frm.doc.cycle_start_date;
    const cycle_end = frm.doc.cycle_end_date;

    let msg = "";

    if (cycle_start && today < cycle_start) {
        const days_to_start = frappe.datetime.get_diff(cycle_start, today);
        msg += __("⚠️ The cycle is scheduled to start on <b>{0}</b> ({1} day(s) from today). Activating early may allow premature applications.<br><br>",
            [cycle_start, days_to_start]);
    }

    if (cycle_end && today > cycle_end) {
        const days_past_end = frappe.datetime.get_diff(today, cycle_end);
        msg += __("⚠️ The cycle end date <b>{0}</b> has already passed ({1} day(s) ago). Activating a past-dated cycle is not recommended.<br><br>",
            [cycle_end, days_past_end]);
    }

    if (frm.doc.docstatus === 0) {
        msg += __("Submitting will also set this cycle as <b>Active</b> and make it visible on the portal. Do you want to continue?");
    } else {
        msg += __("Do you want to activate this cycle?");
    }

    return msg;
}
