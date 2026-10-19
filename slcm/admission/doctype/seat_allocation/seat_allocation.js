// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Seat Allocation", {

    setup(frm) {
        frm.set_query("merit_list", () => {
            let filters = {
                "docstatus": 1 // Only submitted merit lists
            };
            if (frm.doc.admission_cycle) filters.admission_cycle = frm.doc.admission_cycle;
            if (frm.doc.campus) filters.campus = frm.doc.campus;
            if (frm.doc.program_level) filters.program_level = frm.doc.program_level;
            if (frm.doc.program) filters.program = frm.doc.program;
            return { filters: filters };
        });
        frm.set_query("program", () => {
            let filters = {};
            if (frm.doc.program_level) {
                filters["level_of_study"] = frm.doc.program_level;
            }
            return { filters: filters };
        });
    },

    onload(frm) {
        frm.set_query("program", () => {
            let filters = {};
            if (frm.doc.program_level) {
                filters["level_of_study"] = frm.doc.program_level;
            }
            return { filters: filters };
        });
    },

    program_level(frm) {
        frm.set_query("program", () => {
            let filters = {};
            if (frm.doc.program_level) {
                filters["level_of_study"] = frm.doc.program_level;
            }
            return { filters: filters };
        });
        if (frm.doc.program && frm.doc.program_level) {
            frappe.db.get_value("Programme", frm.doc.program, "level_of_study", (r) => {
                if (r && r.level_of_study && r.level_of_study !== frm.doc.program_level) {
                    frm.set_value("program", "");
                }
            });
        }
    },

    merit_list(frm) {
        // Auto-fill Admission Cycle, Campus, Program Level from the selected Merit List
        if (frm.doc.merit_list) {
            frappe.db.get_value(
                "Merit List",
                frm.doc.merit_list,
                ["admission_cycle", "campus", "program_level", "program"]
            ).then(r => {
                if (r.message) {
                    frm.set_value("admission_cycle", r.message.admission_cycle);
                    frm.set_value("campus", r.message.campus);
                    frm.set_value("program_level", r.message.program_level);
                    frm.set_value("program", r.message.program);
                    frm.refresh_field("program");
                }
            });
        } else {
            frm.set_value("admission_cycle", null);
            frm.set_value("campus", null);
            frm.set_value("program_level", null);
        }
    },

    refresh(frm) {
        if (frm.doc.status === "In Progress") {
            start_allocation_progress_polling(frm);
        }

        // Auto-listen to progress if page is loaded/refreshed while Publishing
        if (frm.doc.status === "Publishing") {
            const total = (frm.doc.selection_applicant || []).length || 100;
            frappe.show_progress(__("Publishing Seat Allocation"), 0, total, __("Publication in progress..."));
            frappe.realtime.on("publish_seat_allocation_progress", function (data) {
                if (data.docname === frm.doc.name) {
                    frappe.show_progress(
                        __("Publishing Seat Allocation"),
                        data.current,
                        data.total,
                        data.message || __("Processing {0} of {1}", [data.current, data.total])
                    );
                    if (data.percent >= 100) {
                        frappe.realtime.off("publish_seat_allocation_progress");
                        frappe.hide_progress();
                        frm.reload_doc();
                    }
                }
            });
        }

        // Status indicator
        if (frm.doc.status === "Published") {
            frm.page.set_indicator(__("Published"), "green");
        } else if (frm.doc.status === "Publishing" || frm.doc.status === "In Progress") {
            frm.page.set_indicator(__("Publishing"), "orange");
        } else if (frm.doc.status === "Allocated") {
            frm.page.set_indicator(__("Allocated"), "blue");
        } else if (frm.doc.status === "Draft") {
            frm.page.set_indicator(__("Draft"), "grey");
        }

        // Prevent selecting past dates for published_on
        frm.set_df_property("published_on", "options", {
            minDate: new Date()
        });

        if (frm.doc.status === "Draft") {
            frm.add_custom_button(__("Get Merit List"), () => {
                if (!frm.doc.merit_list) {
                    frappe.msgprint({
                        title: __("Missing Merit List"),
                        message: __("Please select a Merit List before pulling data."),
                        indicator: "orange"
                    });
                    return;
                }

                frappe.confirm(
                    __("This will replace all existing rows in the Selection Applicant table. Continue?"),
                    () => {
                        frm.call({
                            method: "pull_from_merit_list",
                            args: { docname: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Pulling applicants from Merit List..."),
                            callback(r) {
                                if (!r.exc) {
                                    frm.reload_doc();
                                    frappe.show_alert({
                                        message: __("Applicants pulled successfully from Merit List."),
                                        indicator: "green"
                                    });
                                }
                            }
                        });
                    }
                );
            });
        }

        if (frm.doc.status === "Draft") {
            frm.add_custom_button(__("Allocate Seats"), () => {
                frappe.show_progress(__("Allocating Seats"), 0, 100, __("Starting seat allocation..."));
                start_allocation_progress_polling(frm);

                frm.call({
                    method: "allocate_seats",
                    args: { docname: frm.doc.name },
                    callback(r) {
                        if (frm._progress_interval) {
                            clearInterval(frm._progress_interval);
                            frm._progress_interval = null;
                        }
                        frappe.hide_progress();

                        if (!r.exc) {
                            frappe.show_alert({
                                message: __("Seats allocated successfully."),
                                indicator: "green"
                            });
                            frm.dirty(false);
                            frm.reload_doc();
                        }
                    },
                    error() {
                        if (frm._progress_interval) {
                            clearInterval(frm._progress_interval);
                            frm._progress_interval = null;
                        }
                        frappe.hide_progress();
                    }
                });
            }, __("Actions"));
        }

        if (frm.doc.status === "Allocated") {
            frm.add_custom_button(__("Publish Allocation"), () => {
                frappe.confirm(
                    __("Are you sure you want to publish this allocation? This action is irreversible."),
                    () => {
                        const total = (frm.doc.selection_applicant || []).length || 100;
                        frappe.show_progress(__("Publishing Seat Allocation"), 0, total, __("Starting publication..."));

                        frappe.realtime.on("publish_seat_allocation_progress", function (data) {
                            if (data.docname === frm.doc.name) {
                                frappe.show_progress(
                                    __("Publishing Seat Allocation"),
                                    data.current,
                                    data.total,
                                    data.message || __("Processing {0} of {1}", [data.current, data.total])
                                );
                            }
                        });

                        frm.call({
                            method: "publish_allocation",
                            args: { docname: frm.doc.name },
                            callback(r) {
                                frappe.realtime.off("publish_seat_allocation_progress");
                                frappe.hide_progress();
                                if (!r.exc) {
                                    frm.reload_doc();
                                }
                            },
                            error() {
                                frappe.realtime.off("publish_seat_allocation_progress");
                                frappe.hide_progress();
                            }
                        });
                    }
                );
            }, __("Actions"));
        }

        if (frm.doc.status === "Published") {
            frm.add_custom_button(__("Generate Offer Letters"), () => {
                const applicants = frm.doc.selection_applicant
                    .filter(row => row.selection_status === "Selected")
                    .map(row => ({
                        applicant_id: row.applicant_id,
                        program: row.program,
                        selection_status: row.selection_status,
                        name: row.name // childcare record name for internal reference
                    }));

                if (applicants.length === 0) {
                    frappe.msgprint(__("No applicants with 'Selected' status found to generate offers."));
                    return;
                }

                let d = new frappe.ui.Dialog({
                    title: __("Generate Offer Letters"),
                    size: "extra-large",
                    fields: [
                        {
                            label: __("Admission Cycle"),
                            fieldname: "dialog_admission_cycle",
                            fieldtype: "Link",
                            options: "Admission Cycle",
                            read_only: 1,
                            default: frm.doc.admission_cycle,
                            columns: 4
                        },
                        {
                            fieldtype: "Column Break",
                        },
                        {
                            label: __("Campus"),
                            fieldname: "dialog_campus",
                            fieldtype: "Link",
                            options: "Campus",
                            read_only: 1,
                            default: frm.doc.campus,
                            columns: 4
                        },
                        {
                            fieldtype: "Column Break",
                        },
                        {
                            label: __("Admission Year"),
                            fieldname: "dialog_admission_year",
                            fieldtype: "Link",
                            options: "Admission Year",
                            read_only: 1,
                            columns: 4
                        },
                        {
                            fieldtype: "Section Break",
                        },
                        {
                            fieldtype: "HTML",
                            fieldname: "selection_buttons",
                            options: `
                                <div style="margin-bottom: 12px; display: flex; gap: 8px;">
                                    <button type="button" class="btn btn-xs btn-default btn-select-all" style="font-weight: 600; padding: 4px 10px; border-radius: 4px; border: 1px solid #d1d5db; background: #fff; cursor: pointer;">
                                        Select All
                                    </button>
                                    <button type="button" class="btn btn-xs btn-default btn-unselect-all" style="font-weight: 600; padding: 4px 10px; border-radius: 4px; border: 1px solid #d1d5db; background: #fff; cursor: pointer;">
                                        Unselect All
                                    </button>
                                </div>
                            `
                        },
                        {
                            label: __("Selected Applicants"),
                            fieldname: "applicants_grid",
                            fieldtype: "Table",
                            cannot_add_rows: true,
                            cannot_delete_rows: true,
                            page_length: 20,
                            fields: [
                                {
                                    fieldname: "applicant_id",
                                    fieldtype: "Data",
                                    label: __("Applicant ID"),
                                    in_list_view: 1,
                                    read_only: 1
                                },
                                {
                                    fieldname: "program",
                                    fieldtype: "Link",
                                    options: "Programme",
                                    label: __("Programme"),
                                    in_list_view: 1,
                                    read_only: 1
                                },
                                {
                                    fieldname: "selection_status",
                                    fieldtype: "Select",
                                    label: __("Status"),
                                    in_list_view: 1,
                                    read_only: 1
                                }
                            ],
                            data: applicants
                        }
                    ],
                    primary_action_label: __("Generate Offers"),
                    primary_action(values) {
                        const selections = d.fields_dict.applicants_grid.grid.get_selected_children()
                            .map(row => ({
                                applicant: row.applicant_id,
                                campus: frm.doc.campus,
                                cycle: frm.doc.admission_cycle,
                                program: row.program,
                                admission_year: values.dialog_admission_year
                            }));

                        if (!values.dialog_admission_year) {
                            frappe.msgprint({
                                title: __("Missing Configuration"),
                                message: __("Admission Year is required to generate offer letters. Please ensure the Admission Cycle is correctly configured."),
                                indicator: "red"
                            });
                            return;
                        }

                        if (selections.length === 0) {
                            frappe.msgprint(__('Please select at least one applicant.'));
                            return;
                        }

                        d.hide();

                        if (selections.length > 500) {
                            frappe.dom.freeze(__("Submitting batch to background queue..."));
                            frappe.call({
                                method: "slcm.api.service.offer_service.bulk_generate_offers",
                                args: { applicants: selections },
                                callback: function (r) {
                                    frappe.dom.unfreeze();
                                    if (r.message && r.message.queued) {
                                        frappe.msgprint({
                                            title: __("Processing Started"),
                                            message: r.message.message,
                                            indicator: 'blue',
                                            primary_action: {
                                                label: __('View Offer Letters'),
                                                action: () => frappe.set_route('List', 'Offer Letter')
                                            }
                                        });
                                    }
                                }
                            });
                            return;
                        }

                        // SMALL BATCH PROCESSING
                        const total = selections.length;
                        frappe.show_progress(__("Generating Offer Letters"), 0, total, __("Preparing..."));

                        let processed = 0, success_count = 0, error_count = 0, summary_log = [];

                        const process_next = () => {
                            if (processed >= total) {
                                frappe.show_progress(__("Generating Offer Letters"), total, total, __("Completed."));
                                setTimeout(() => {
                                    frappe.hide_progress();

                                    let message = `
                                        <div style="padding: 10px;">
                                            <div style="display: flex; gap: 15px; margin-bottom: 20px;">
                                                <div style="flex: 1; padding: 12px; background: #f0fff4; border: 1px solid #c6f6d5; border-radius: 8px; text-align: center;">
                                                    <h3 style="margin: 0; color: #2f855a;">${success_count}</h3>
                                                    <div style="font-size: 11px; color: #38a169; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">${__('Successful')}</div>
                                                </div>
                                                <div style="flex: 1; padding: 12px; background: ${error_count > 0 ? '#fff5f5' : '#f7fafc'}; border: 1px solid ${error_count > 0 ? '#fed7d7' : '#edf2f7'}; border-radius: 8px; text-align: center;">
                                                    <h3 style="margin: 0; color: ${error_count > 0 ? '#c53030' : '#718096'};">${error_count}</h3>
                                                    <div style="font-size: 11px; color: ${error_count > 0 ? '#e53e3e' : '#a0aec0'}; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">${__('Failed')}</div>
                                                </div>
                                            </div>
                                    `;

                                    if (error_count > 0) {
                                        message += `
                                            <div style="margin-bottom: 8px; font-weight: 600; color: #4a5568;">${__('Generation Failures:')}</div>
                                            <div style="max-height: 250px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 6px;">
                                                <table class="table table-bordered table-condensed" style="margin:0; font-size: 12px; background: #fff;">
                                                    <thead style="background: #f8fafc;">
                                                        <tr>
                                                            <th style="width: 35%;">${__('Applicant')}</th>
                                                            <th>${__('Reason for Failure')}</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        ${summary_log.map(item => `
                                                            <tr>
                                                                <td style="font-weight: 600;">${item.applicant}</td>
                                                                <td style="color: #e53e3e; word-break: break-word;">${item.error}</td>
                                                            </tr>
                                                        `).join('')}
                                                    </tbody>
                                                </table>
                                            </div>
                                        `;
                                    }
                                    message += `</div>`;

                                    frappe.msgprint({
                                        title: __('Offer Generation Report'),
                                        message: message,
                                        wide: true,
                                        indicator: error_count === 0 ? 'green' : (success_count > 0 ? 'orange' : 'red'),
                                        primary_action: {
                                            label: __('View Offer Letters'),
                                            action: () => frappe.set_route('List', 'Offer Letter')
                                        }
                                    });
                                }, 1000);
                                return;
                            }

                            const payload = selections[processed];
                            frappe.show_progress(__("Generating Offer Letters"), processed + 1, total, __("Processing {0}", [payload.applicant]));

                            frappe.call({
                                method: "slcm.api.service.offer_service.bulk_generate_offers",
                                args: { applicants: [payload] },
                                callback: (r) => {
                                    if (r.message) {
                                        if (r.message.success?.length) success_count++;
                                        if (r.message.errors?.length) {
                                            error_count++;
                                            summary_log.push(r.message.errors[0]);
                                        }
                                    }
                                    processed++;
                                    process_next();
                                },
                                error: (err) => {
                                    frappe.hide_progress();
                                    // Stop loop on server error to prevent spamming modals
                                    return;
                                }
                            });
                        };
                        process_next();
                    }
                });

                d.show();

                // Fetch and set Admission Year from Admission Cycle
                if (frm.doc.admission_cycle) {
                    frappe.db.get_value("Admission Cycle", frm.doc.admission_cycle, "admission_year")
                        .then(r => {
                            if (r.message && r.message.admission_year) {
                                d.set_value("dialog_admission_year", r.message.admission_year);
                            }
                        });
                }

                // Select all by default and hide grid action buttons
                setTimeout(() => {
                    const grid = d.fields_dict.applicants_grid.grid;
                    if (grid) {
                        grid.wrapper.find('.grid-add-row').hide();
                        grid.wrapper.find('.grid-remove-rows').hide();
                        grid.data.forEach(row => row.__checked = 1);
                        grid.refresh();
                    }

                    // Bind selection buttons
                    d.$wrapper.find('.btn-select-all').on('click', (e) => {
                        e.preventDefault();
                        if (grid) {
                            grid.data.forEach(row => row.__checked = 1);
                            grid.refresh();
                        }
                    });

                    d.$wrapper.find('.btn-unselect-all').on('click', (e) => {
                        e.preventDefault();
                        if (grid) {
                            grid.data.forEach(row => row.__checked = 0);
                            grid.refresh();
                        }
                    });
                }, 300);
            });
        }

        if (frm.doc.status === "Allocated" || frm.doc.status === "Published") {
            frm.add_custom_button(__("Promote Waitlist"), () => {
                frm.call({
                    method: "get_waitlist_promotion_preview",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Calculating promotion preview..."),
                    callback: (r) => {
                        const data = r.message || {};
                        if (!data.promotions || data.promotions.length === 0) {
                            frappe.msgprint({
                                title: __("No Promotions Available"),
                                message: __("No vacancies found or no waitlisted candidates eligible for promotion."),
                                indicator: "orange"
                            });
                            return;
                        }

                        let d = new frappe.ui.Dialog({
                            title: __("Promote Waitlist Candidates"),
                            size: "large",
                            fields: [
                                {
                                    fieldtype: "HTML",
                                    fieldname: "preview_info",
                                    options: `
                                        <div style="padding: 10px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; margin-bottom: 15px;">
                                            <p style="margin: 0; color: #475569; font-size: 13px;">
                                                The following waitlisted candidates are eligible for promotion to seats that became available due to 
                                                <b>Expired</b>, <b>Declined</b>, or <b>Withdrawn</b> offers. Select one or more candidates to promote.
                                            </p>
                                        </div>
                                    `
                                },
                                {
                                    fieldtype: "HTML",
                                    fieldname: "promotions_html",
                                    options: `
                                        <div class="promotions-wrapper" style="border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; max-height: 550px; overflow-y: auto;">
                                            <table class="table table-bordered" style="margin: 0; background: #fff;">
                                                <thead style="background: #f8fafc; font-size: 12px; color: #475569; position: sticky; top: 0; z-index: 10;">
                                                    <tr>
                                                        <th style="width: 40px; text-align: center;"><input type="checkbox" id="check-all-promotions" checked></th>
                                                        <th style="width: 30%;">${__('Vacant Seat Released By')}</th>
                                                        <th style="width: 25%;">${__('Promote Category')}</th>
                                                        <th style="width: 45%;">${__('Promote Candidate')}</th>
                                                    </tr>
                                                </thead>
                                                <tbody id="promotions-body">
                                                    ${data.promotions.map((p, i) => {
                                        const options_html = (p.eligible_candidates || []).map(cand => {
                                            const selected = cand.applicant_id === p.applicant_id ? 'selected' : '';
                                            return `<option value="${cand.applicant_id}" ${selected} data-name="${cand.candidate_name}" data-score="${cand.total_score}" data-rank="${cand.overall_rank}">
                                                                ${cand.candidate_name} (${cand.applicant_id}) - Score: ${cand.total_score || 0}, Rank: ${cand.overall_rank || 0}
                                                            </option>`;
                                        }).join('');

                                        return `
                                                        <tr class="promotion-row" data-idx="${i}">
                                                            <td style="text-align: center; vertical-align: middle;">
                                                                <input type="checkbox" class="promotion-check" checked>
                                                            </td>
                                                    <td style="vertical-align: middle;">
                                                        <div style="color: #475569; font-size: 13px;">
                                                            ${p.vacant_candidate_name ?
                                                                `<div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                                                                    <span style="background: #fef2f2; color: #ef4444; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; text-transform: uppercase;">Replaces</span> 
                                                                    <span style="font-weight: 600; color: #1e293b;">${p.vacant_candidate_name}</span> 
                                                                    <span style="color: #475569; font-size: 12px; font-weight: 500;">(${p.vacant_applicant_id}) - Score: ${p.vacant_total_score || 0}, Rank: ${p.vacant_overall_rank || 0}</span> 
                                                                    <span style="color: #94a3b8; font-size: 11px;">(${p.vacant_selection_status})</span>
                                                                 </div>` :
                                                                (p.vacant_seat_info && p.vacant_seat_info.includes('(') ?
                                                                    `<div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                                                                        <span style="background: #fef2f2; color: #ef4444; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; text-transform: uppercase;">Replaces</span> 
                                                                        <span style="font-weight: 500;">${p.vacant_seat_info.substring(0, p.vacant_seat_info.lastIndexOf('(')).trim()}</span> 
                                                                        <span style="color: #94a3b8; font-size: 11px;">${p.vacant_seat_info.substring(p.vacant_seat_info.lastIndexOf('('))}</span>
                                                                     </div>` :
                                                                    `<span style="color: #10b981; font-weight: 500;">${p.vacant_seat_info || __('Available Seat')}</span>`
                                                                )
                                                            }
                                                        </div>
                                                    </td>
                                                            <td style="vertical-align: middle;">
                                                                <span style="background: #e0f2fe; color: #0284c7; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; white-space: nowrap;">
                                                                    ${p.allocated_category}
                                                                </span>
                                                            </td>
                                                            <td style="vertical-align: middle;">
                                                                <select class="form-control candidate-select" style="font-size: 13px; font-weight: 600; color: #1e293b; border-color: #cbd5e1; border-radius: 6px; padding: 6px 12px; width: 100%; max-width: 100%; height: 38px; background-color: #fff; cursor: pointer; box-shadow: inset 0 1px 2px rgba(0,0,0,0.05);">
                                                                    ${options_html}
                                                                </select>
                                                            </td>
                                                        </tr>
                                                        `;
                                    }).join('')}
                                                </tbody>
                                            </table>
                                        </div>
                                    `
                                }
                            ],
                            primary_action_label: __("Promote"),
                            primary_action(values) {
                                const selected = [];
                                $(d.wrapper).find('.promotion-row').each(function () {
                                    const row = $(this);
                                    const is_checked = row.find('.promotion-check').is(':checked');
                                    if (is_checked) {
                                        const idx = row.data('idx');
                                        const orig_promotion = data.promotions[idx];
                                        const select_el = row.find('.candidate-select');
                                        const applicant_id = select_el.val();
                                        const option_el = select_el.find('option:selected');

                                        selected.push({
                                            applicant_id: applicant_id,
                                            candidate_name: option_el.data('name'),
                                            program: orig_promotion.program,
                                            allocated_category: orig_promotion.allocated_category,
                                            overall_rank: option_el.data('rank'),
                                            total_score: option_el.data('score')
                                        });
                                    }
                                });

                                if (selected.length === 0) {
                                    frappe.msgprint(__('Please select at least one candidate to promote.'));
                                    return;
                                }

                                d.hide();
                                frappe.confirm(__("Are you sure you want to promote {0} candidates? This will generate offer letters immediately.", [selected.length]), () => {
                                    frm.call({
                                        method: "run_promotion",
                                        args: {
                                            docname: frm.doc.name,
                                            promoted_applicants: selected
                                        },
                                        freeze: true,
                                        freeze_message: __("Running waitlist promotion and generating offers..."),
                                        callback: (r) => {
                                            if (!r.exc) {
                                                frm.reload_doc();
                                                frappe.show_alert({
                                                    message: __("{0} candidates promoted successfully.", [selected.length]),
                                                    indicator: "green"
                                                });
                                            }
                                        }
                                    });
                                });
                            }
                        });

                        d.show();
                        d.$wrapper.find('.modal-dialog').css({
                            "max-width": "1300px",
                            "width": "1300px"
                        });

                        // Handle select all checkbox and dialog sizing
                        setTimeout(() => {
                            d.$wrapper.find('.modal-dialog').css({
                                "max-width": "1300px",
                                "width": "1300px"
                            });
                            $(d.wrapper).find('#check-all-promotions').on('change', function () {
                                const is_checked = $(this).is(':checked');
                                $(d.wrapper).find('.promotion-check').prop('checked', is_checked);
                            });

                            $(d.wrapper).find('.promotion-check').on('change', function () {
                                const total = $(d.wrapper).find('.promotion-check').length;
                                const checked = $(d.wrapper).find('.promotion-check:checked').length;
                                $(d.wrapper).find('#check-all-promotions').prop('checked', total === checked);
                            });
                        }, 100);
                    }
                });
            }, __("Actions"));
        }

        if (frm.doc.status === "Published") {
            frm.add_custom_button(__("Unpublish"), () => {
                frappe.confirm(
                    __("This will hide results from students. Continue?"),
                    () => {
                        frm.call({
                            method: "unpublish_allocation",
                            args: { docname: frm.doc.name },
                            callback(r) {
                                if (!r.exc) {
                                    frm.reload_doc();
                                    frappe.show_alert({
                                        message: __("Allocation unpublished."),
                                        indicator: "orange"
                                    });
                                }
                            }
                        });
                    }
                );
            }, __("Actions"));
        }

        if (!frm.is_new()) {
            frm.add_custom_button(__("Download Results PDF"), function () {
                let url = frappe.urllib.get_full_url(
                    "/api/method/slcm.admission.doctype.seat_allocation.seat_allocation.download_results_pdf?" +
                    "name=" + encodeURIComponent(frm.doc.name)
                );
                window.open(url, '_blank');
            }, __("Actions"));

            frm.add_custom_button(__("Download Allocation"), function () {
                let url = frappe.urllib.get_full_url(
                    "/api/method/slcm.admission.doctype.seat_allocation.seat_allocation.download_allocation?" +
                    "name=" + encodeURIComponent(frm.doc.name)
                );
                window.open(url, '_blank');
            }, __("Actions"));

            frm.add_custom_button(__("Download Summary"), function () {
                let url = frappe.urllib.get_full_url(
                    "/api/method/slcm.admission.doctype.seat_allocation.seat_allocation.download_summary?" +
                    "name=" + encodeURIComponent(frm.doc.name)
                );
                window.open(url, '_blank');
            }, __("Actions"));
        }
    }
});

function start_allocation_progress_polling(frm) {
    if (frm._progress_interval) {
        clearInterval(frm._progress_interval);
    }

    let progress_dialog = null;

    frm._progress_interval = setInterval(() => {
        frappe.call({
            method: "slcm.admission.doctype.seat_allocation.seat_allocation.get_allocation_progress",
            args: {
                docname: frm.doc.name
            },
            callback: (res) => {
                let data = res.message;
                if (data) {
                    let percent = Math.round(data.percent || 0);
                    let desc = data.description || __("Allocating seats based on merit and capacity...");
                    if (data.status === "In Progress") {
                        if (!progress_dialog) {
                            progress_dialog = frappe.show_progress(__("Allocating Seats"), percent, 100, desc);
                        } else {
                            frappe.show_progress(__("Allocating Seats"), percent, 100, desc);
                        }
                    } else if (data.status === "Completed" || data.status === "Failed" || data.status === "Allocated" || data.status === "Published") {
                        clearInterval(frm._progress_interval);
                        frm._progress_interval = null;
                        frm.dirty(false);
                        frm.reload_doc().then(() => {
                            frappe.hide_progress();
                        });
                    }
                }
            }
        });
    }, 500);
}
