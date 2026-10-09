let etl_allocation_progress_dialog = null;
if (typeof window.etl_allocation_done === 'undefined') {
    window.etl_allocation_done = false;
}
if (typeof window.etl_allocation_parent_dialog === 'undefined') {
    window.etl_allocation_parent_dialog = null;
}

if (!window.show_etl_allocation_success_toast) {
    window.show_etl_allocation_success_toast = function (count, unallocated) {
        if (!document.getElementById("etg-toast-style")) {
            const style = document.createElement("style");
            style.id = "etg-toast-style";
            style.innerHTML = `
                @keyframes etgSlideDown {
                    from { opacity: 0; transform: translateX(-50%) translateY(-30px); }
                    to   { opacity: 1; transform: translateX(-50%) translateY(0); }
                }
                @keyframes etgSlideUp {
                    from { opacity: 1; transform: translateX(-50%) translateY(0); }
                    to   { opacity: 0; transform: translateX(-50%) translateY(-30px); }
                }
            `;
            document.head.appendChild(style);
        }

        const existingToast = document.getElementById("etl-success-toast");
        if (existingToast) existingToast.remove();

        unallocated = unallocated || [];
        const border_color = unallocated.length > 0 ? "#eab308" : "#2da44e";
        const icon_bg = unallocated.length > 0 ? "#fef9c3" : "#eafbee";
        const icon_text = unallocated.length > 0 ? "⚠️" : "✅";
        const header_color = unallocated.length > 0 ? "#854d0e" : "#1a7f37";

        let unallocated_html = "";
        if (unallocated.length > 0) {
            unallocated_html = `
                <div style="margin-top:10px; padding-top:8px; border-top:1px solid #fef08a; font-size:12px; color:#713f12;">
                    <div style="font-weight:700; margin-bottom:4px;">
                        The following applicant(s) could not be allocated:
                    </div>
                    <ul style="margin:0 0 0 16px; padding:0; list-style-type:disc;">
                        ${unallocated.map(u => `<li style="margin-bottom:3px;"><b>${u.name}</b> (${u.applicant_id}): ${u.reason}</li>`).join("")}
                    </ul>
                </div>
            `;
        }

        const toast = document.createElement("div");
        toast.id = "etl-success-toast";
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            left: 50%;
            z-index: 999999;
            background: #ffffff;
            border: 1.5px solid ${border_color};
            border-left: 5px solid ${border_color};
            border-radius: 10px;
            padding: 14px 20px;
            min-width: 400px;
            max-width: 600px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.10);
            display: flex;
            align-items: flex-start;
            gap: 12px;
            font-family: inherit;
            animation: etgSlideDown 0.35s cubic-bezier(.4,0,.2,1) forwards;
        `;
        toast.innerHTML = `
            <div style="flex-shrink:0; width:36px; height:36px; background:${icon_bg};
                        border-radius:50%; display:flex; align-items:center;
                        justify-content:center; font-size:18px;">${icon_text}</div>
            <div style="flex:1;">
                <div style="font-weight:700; font-size:14px; color:${header_color}; margin-bottom:3px;">
                    Allocation Process Summary
                </div>
                <div style="font-size:13px; color:#333;">
                    Successfully allocated seats for <b>${count}</b> applicant(s).
                </div>
                ${unallocated_html}
            </div>
            <span id="etl-success-toast-close"
                  style="cursor:pointer; color:#aaa; font-size:18px; line-height:1;
                         padding:0 4px; align-self:flex-start; flex-shrink:0;"
                  title="Dismiss">✕</span>
        `;
        document.body.appendChild(toast);

        const dismissSuccessToast = () => {
            toast.style.animation = "etgSlideUp 0.35s cubic-bezier(.4,0,.2,1) forwards";
            setTimeout(() => toast.remove(), 350);
        };
        document.getElementById("etl-success-toast-close").addEventListener("click", dismissSuccessToast);
        setTimeout(dismissSuccessToast, unallocated.length > 0 ? 12000 : 6000);
    };
}

frappe.listview_settings['Entrance Test Seat Allocation'] = {
    onload: function (listview) {
        // Add to the 'Actions' menu that appears when records are selected
        listview.page.add_actions_menu_item(__('Bulk Records Download'), function () {
            const selected_items = listview.get_checked_items();

            if (selected_items.length === 0) {
                frappe.msgprint(__('Please select at least one record to download.'));
                return;
            }

            const names = selected_items.map(item => item.name);
            const total = names.length;

            // Build a custom progress dialog
            let progress_dialog = new frappe.ui.Dialog({
                title: __('Bulk Records Download'),
                fields: [{
                    fieldtype: 'HTML',
                    fieldname: 'progress_html',
                    options: `
                        <div style="padding: 10px 0;">
                            <div style="margin-bottom: 10px; font-size: 13px; color: #4a5568;">
                                <span id="bulk-dl-description">${__('Preparing download for {0} record(s)...', [total])}</span>
                            </div>
                            <div style="background: #e2e8f0; border-radius: 8px; height: 18px; overflow: hidden; margin-bottom: 8px;">
                                <div id="bulk-dl-bar" style="background: linear-gradient(90deg, #3182ce, #63b3ed); height: 100%; width: 0%; border-radius: 8px; transition: width 0.4s ease;"></div>
                            </div>
                            <div style="display: flex; justify-content: space-between; font-size: 12px; color: #718096;">
                                <span id="bulk-dl-counter">0 of ${total}</span>
                                <span id="bulk-dl-pct">0%</span>
                            </div>
                        </div>
                    `
                }]
            });
            progress_dialog.get_close_btn().hide();
            progress_dialog.show();
            progress_dialog.set_primary_action(__('Cancel'), () => {
                // Best-effort: just close the dialog; ZIP will still complete server-side
                progress_dialog.hide();
            });

            // Listen for realtime progress from backend
            frappe.realtime.on('progress', function (data) {
                if (data.title !== 'Bulk Download') return;
                const pct = Math.min(Math.round(data.percent || 0), 100);
                const desc = data.description || '';
                document.getElementById('bulk-dl-bar').style.width = pct + '%';
                document.getElementById('bulk-dl-pct').textContent = pct + '%';
                document.getElementById('bulk-dl-description').textContent = desc;
                // Extract "X of Y" from description if present
                const match = desc.match(/(\d+) of (\d+)/);
                if (match) document.getElementById('bulk-dl-counter').textContent = `${match[1]} of ${match[2]}`;
                else document.getElementById('bulk-dl-counter').textContent = `${pct}% complete`;
            });

            frappe.call({
                method: 'slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.bulk_download_all_records',
                args: { names: names },
                callback: function (r) {
                    frappe.realtime.off('progress');
                    progress_dialog.hide();
                    if (r.message) {
                        const file_url = r.message;
                        const link = document.createElement('a');
                        link.href = file_url;
                        link.download = file_url.split('/').pop();
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);

                        frappe.show_alert({
                            message: __('ZIP download started successfully.'),
                            indicator: 'green'
                        });
                    }
                },
                error: function () {
                    frappe.realtime.off('progress');
                    progress_dialog.hide();
                }
            });
        });
    },
    refresh: function (listview) {
        frappe.realtime.on("entrance_test_seat_allocation_progress", function (data) {
            let pct = data.progress;
            let current = data.current;
            let total = data.total;
            let name = data.applicant_name;

            if (etl_allocation_progress_dialog && etl_allocation_progress_dialog.display) {
                etl_allocation_progress_dialog.$wrapper.find("#etg-progress-bar").css("width", `${pct}%`);
                etl_allocation_progress_dialog.$wrapper.find("#etg-progress-percent").text(`${pct}%`);
                etl_allocation_progress_dialog.$wrapper.find("#etg-current-applicant").text(`Processing: ${name}`);
                etl_allocation_progress_dialog.$wrapper.find("#etg-counter-text").text(`Processing ${current} of ${total}`);
            }

            if (pct >= 100 || current >= total) {
                setTimeout(() => {
                    if (!window.etl_allocation_done) {
                        window.etl_allocation_done = true;
                        if (etl_allocation_progress_dialog) {
                            etl_allocation_progress_dialog.hide();
                        }
                        if (window.etl_allocation_parent_dialog) {
                            window.etl_allocation_parent_dialog.hide();
                        }
                        listview.refresh();
                        window.show_etl_allocation_success_toast(data.allocated_count || 0, []);
                    }
                }, 1500);
            }
        });

        // Hide buttons only for users with the "Applicant" role
        // and who are NOT Administrators/System Managers (to ensure admins always have access)
        const is_applicant = frappe.user_roles.includes("Applicant");
        const is_admin = frappe.user_roles.includes("Administrator") || frappe.user_roles.includes("System Manager");

        if (!is_applicant || is_admin) {
            // 1. Download Attendance Sheet (placed on the left)
            listview.page.add_inner_button(__("Download Attendance Sheet"), function () {
                open_download_attendance_sheet_dialog(listview);
            });

            // 2. Update Entrance Test Rank
            listview.page.add_inner_button(__("Update Entrance Test Rank"), function () {
                open_update_rank_dialog(listview);
            }, __("Actions"));

            // 3. Generate Result Card
            listview.page.add_inner_button(__("Generate Result Card"), function () {
                open_generate_result_card_dialog(listview);
            }, __("Actions"));

            // 4. Publish Result
            listview.page.add_inner_button(__("Publish Result"), function () {
                open_publish_result_dialog(listview);
            }, __("Actions"));

            // 5. Reject and Allocate Centre
            listview.page.add_inner_button(__("Reject and Allocate Centre"), function () {
                open_reject_and_allocate_dialog(listview);
            }, __("Actions"));

            // 6. Export Marks Template
            listview.page.add_inner_button(__("Export Marks Template"), function () {
                open_export_marks_dialog_for_list(listview);
            }, __("Actions"));

            // 7. Reschedule
            listview.page.add_inner_button(__("Reschedule"), function () {
                open_reschedule_dialog(listview);
            }, __("Actions"));

            // 8. Centre List Download
            listview.page.add_inner_button(__("Centre List Download"), function () {
                open_centre_list_download_dialog(listview);
            }, __("Actions"));
        }
    }
};

/**
 * Helper to extract filter values from route_options, listview filter_area, or URL query string
 */
function get_listview_filter_val(listview, fieldname) {
    if (frappe.route_options && frappe.route_options[fieldname]) {
        return frappe.route_options[fieldname];
    }
    if (listview && listview.filter_area && typeof listview.filter_area.get_filters === "function") {
        try {
            const filters = listview.filter_area.get_filters();
            for (let f of filters) {
                if (Array.isArray(f) && f[1] === fieldname) {
                    return f[3];
                } else if (f && f.fieldname === fieldname) {
                    return f.value;
                }
            }
        } catch (e) { }
    }
    try {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has(fieldname)) {
            return urlParams.get(fieldname);
        }
    } catch (e) { }
    return "";
}

/**
 * Custom Update Rank Dialog for List View
 */
function open_update_rank_dialog(listview) {
    const default_ay = get_listview_filter_val(listview, "academic_year");
    const default_ac = get_listview_filter_val(listview, "admission_cycle");
    const default_pl = get_listview_filter_val(listview, "program_level");

    let d = new frappe.ui.Dialog({
        title: __("Update Entrance Test Rank"),
        size: "large",
        fields: [
            { fieldtype: "Section Break", label: __("Filters") },
            {
                label: __("Academic Year"),
                fieldname: "academic_year",
                fieldtype: "Link",
                options: "Academic Year",
                default: default_ay,
                reqd: 1,
                change() { update_dialog_applicant_count(d); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Admission Cycle"),
                fieldname: "admission_cycle",
                fieldtype: "Link",
                options: "Admission Cycle",
                default: default_ac,
                reqd: 1,
                change() { update_dialog_applicant_count(d); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Programme Level"),
                fieldname: "program_level",
                fieldtype: "Select",
                options: "Undergraduate\nPostgraduate\nResearch Course",
                default: default_pl,
                reqd: 1,
                change() {
                    d.set_value("program", "");
                    update_dialog_applicant_count(d);
                }
            },
            { fieldtype: "Section Break" },
            {
                label: __("Applicant Type"),
                fieldname: "applicant_type",
                fieldtype: "Select",
                options: "Domestic Applicants\nInternational Applicants\nBoth",
                default: "Domestic Applicants",
                reqd: 1,
                change() { update_dialog_applicant_count(d); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Programme"),
                fieldname: "program",
                fieldtype: "Link",
                options: "Programme",
                depends_on: "eval:doc.program_level",
                change() { update_dialog_applicant_count(d); }
            },
            { fieldtype: "Section Break" },
            {
                fieldname: "total_applicants_html",
                fieldtype: "HTML"
            }
        ],
        primary_action_label: __("Generate"),
        primary_action(values) {
            d.hide();
            frappe.show_progress(__("Update Ranking"), 0, 100, __("Calculating scores and ranks..."));
            frappe.call({
                method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.update_ranks_by_category",
                args: values,
                callback: function (r) {
                    frappe.show_progress(__("Update Ranking"), 100, 100, __("Completed"));
                    setTimeout(() => frappe.hide_progress(), 3000);
                    if (!r.exc) {
                        frappe.msgprint({
                            message: __("Rank updated successfully for {0} applicants.", [r.message]),
                            indicator: 'green',
                            alert: true
                        });
                        listview.refresh();
                    }
                },
                error: function () {
                    frappe.hide_progress();
                }
            });
        }
    });

    d.listview = listview;

    d.set_query("admission_cycle", function () {
        return { filters: { "status": "Active" } };
    });
    d.set_query("program", function () {
        return {
            query: "slcm.admission.doctype.entrance_test_generation.entrance_test_generation.get_program_query",
            filters: {
                "program_level": d.get_value("program_level"),
                "admission_cycle": d.get_value("admission_cycle")
            }
        };
    });

    d.show();

    if (default_ay || default_ac || default_pl) {
        d.set_values({
            academic_year: default_ay,
            admission_cycle: default_ac,
            program_level: default_pl,
            applicant_type: "Domestic Applicants"
        });
    }

    ["academic_year", "admission_cycle", "program_level", "applicant_type", "program"].forEach(fn => {
        if (d.fields_dict[fn] && d.fields_dict[fn].$input) {
            d.fields_dict[fn].$input.on("change blur input", () => update_dialog_applicant_count(d));
        }
    });

    update_dialog_applicant_count(d);
}

/**
 * Custom Publish Result Dialog for List View
 */
function open_publish_result_dialog(listview) {
    const default_ay = get_listview_filter_val(listview, "academic_year");
    const default_ac = get_listview_filter_val(listview, "admission_cycle");
    const default_pl = get_listview_filter_val(listview, "program_level");

    let pd = new frappe.ui.Dialog({
        title: __("Publish Entrance Test Result"),
        size: "extra-large",
        fields: [
            { fieldtype: "Section Break", label: __("Filters") },
            {
                label: __("Academic Year"),
                fieldname: "academic_year",
                fieldtype: "Link",
                options: "Academic Year",
                default: default_ay,
                reqd: 1,
                change() {
                    update_dialog_applicant_count(pd);
                    update_unpublished_applicants_table(pd, false);
                }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Admission Cycle"),
                fieldname: "admission_cycle",
                fieldtype: "Link",
                options: "Admission Cycle",
                default: default_ac,
                reqd: 1,
                change() {
                    update_dialog_applicant_count(pd);
                    update_unpublished_applicants_table(pd, false);
                }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Programme Level"),
                fieldname: "program_level",
                fieldtype: "Select",
                options: "Undergraduate\nPostgraduate\nResearch Course",
                default: default_pl,
                change() {
                    pd.set_value("program", "");
                    update_dialog_applicant_count(pd);
                    update_unpublished_applicants_table(pd, false);
                }
            },
            { fieldtype: "Section Break" },
            {
                label: __("Applicant Type"),
                fieldname: "applicant_type",
                fieldtype: "Select",
                options: "Domestic Applicants\nInternational Applicants\nBoth",
                default: "Domestic Applicants",
                reqd: 1,
                change() {
                    update_dialog_applicant_count(pd);
                    update_unpublished_applicants_table(pd, false);
                }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Programme"),
                fieldname: "program",
                fieldtype: "Link",
                options: "Programme",
                depends_on: "eval:doc.program_level",
                change() {
                    update_dialog_applicant_count(pd);
                    update_unpublished_applicants_table(pd, false);
                }
            },
            { fieldtype: "Section Break" },
            {
                fieldname: "total_applicants_html",
                fieldtype: "HTML"
            },
            { fieldtype: "Section Break", label: __("Unpublished Applicants Preview") },
            {
                fieldname: "unpublished_applicants_html",
                fieldtype: "HTML"
            },
            { fieldtype: "Section Break", label: __("Email Settings") },
            {
                label: __("Send Email"),
                fieldname: "send_email",
                fieldtype: "Check",
                default: 0,
                onchange: function () {
                    let is_send = pd.get_value("send_email");
                    let format = pd.get_value("email_format");

                    if (pd.fields_dict.email_format) {
                        pd.fields_dict.email_format.$wrapper.toggle(!!is_send);
                    }

                    if (pd.fields_dict.custom_email_content) {
                        let show_editor = !!(is_send && format === "Custom");
                        pd.fields_dict.custom_email_content.$wrapper.toggle(show_editor);
                        if (show_editor) {
                            setTimeout(() => pd.fields_dict.custom_email_content.refresh(), 50);
                        }
                    }
                }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Email Format"),
                fieldname: "email_format",
                fieldtype: "Select",
                options: "Default\nCustom",
                default: "Default",
                onchange: function () {
                    let is_send = pd.get_value("send_email");
                    let format = pd.get_value("email_format");

                    if (pd.fields_dict.custom_email_content) {
                        let show_editor = !!(is_send && format === "Custom");
                        pd.fields_dict.custom_email_content.$wrapper.toggle(show_editor);
                        if (show_editor) {
                            setTimeout(() => pd.fields_dict.custom_email_content.refresh(), 50);
                        }
                    }
                }
            },
            { fieldtype: "Section Break" },
            {
                label: __("Custom Email Content"),
                fieldname: "custom_email_content",
                fieldtype: "Text Editor"
            }
        ],
        primary_action_label: __("Publish"),
        primary_action(values) {
            frappe.confirm(
                __("This will mark all matching Entrance Test Seat Allocation records as <b>Result Published</b> and send result emails to all applicants. Do you want to continue?"),
                function () {
                    pd.hide();
                    frappe.show_progress(__("Publishing Results"), 0, 100, __("Updating records and queueing emails..."));
                    frappe.call({
                        method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.publish_results",
                        args: {
                            academic_year: values.academic_year,
                            admission_cycle: values.admission_cycle,
                            program_level: values.program_level,
                            applicant_type: values.applicant_type,
                            program: values.program,
                            send_email: values.send_email,
                            email_format: values.email_format,
                            custom_email_content: values.custom_email_content,
                            selected_names: pd.unpublished_state.selected_names.length > 0 ? JSON.stringify(pd.unpublished_state.selected_names) : null
                        },
                        callback: function (r) {
                            frappe.show_progress(__("Publishing Results"), 100, 100, __("Completed"));
                            setTimeout(() => frappe.hide_progress(), 3000);
                            if (!r.exc && r.message) {
                                frappe.msgprint({
                                    title: __("Results Published"),
                                    message: __(
                                        "<b>{0}</b> records published. <b>{1}</b> notification emails queued.",
                                        [r.message.published, r.message.notified]
                                    ),
                                    indicator: "green"
                                });
                                listview.refresh();
                            }
                        },
                        error: function () {
                            frappe.hide_progress();
                        }
                    });
                }
            );
        }
    });

    pd.listview = listview;

    pd.set_query("admission_cycle", function () {
        return { filters: { "status": "Active" } };
    });
    pd.set_query("program", function () {
        return {
            query: "slcm.admission.doctype.entrance_test_generation.entrance_test_generation.get_program_query",
            filters: {
                "program_level": pd.get_value("program_level"),
                "admission_cycle": pd.get_value("admission_cycle")
            }
        };
    });

    pd.unpublished_state = {
        page: 1,
        limit: 10,
        selected_names: []
    };

    pd.show();

    // Initial Hide of Email Fields
    if (pd.fields_dict.email_format) pd.fields_dict.email_format.$wrapper.hide();
    if (pd.fields_dict.custom_email_content) pd.fields_dict.custom_email_content.$wrapper.hide();

    if (default_ay || default_ac || default_pl) {
        pd.set_values({
            academic_year: default_ay,
            admission_cycle: default_ac,
            program_level: default_pl,
            applicant_type: "Domestic Applicants"
        });
    }

    ["academic_year", "admission_cycle", "program_level", "applicant_type", "program"].forEach(fn => {
        if (pd.fields_dict[fn] && pd.fields_dict[fn].$input) {
            pd.fields_dict[fn].$input.on("change blur input", () => {
                update_dialog_applicant_count(pd);
                update_unpublished_applicants_table(pd, false);
            });
        }
    });

    update_dialog_applicant_count(pd);
    update_unpublished_applicants_table(pd, false);
}

/**
 * Custom Generate Result Card Dialog for List View
 */
function open_generate_result_card_dialog(listview) {
    const default_ay = get_listview_filter_val(listview, "academic_year");
    const default_ac = get_listview_filter_val(listview, "admission_cycle");
    const default_pl = get_listview_filter_val(listview, "program_level");

    let gd = new frappe.ui.Dialog({
        title: __("Generate Result Card"),
        size: "large",
        fields: [
            { fieldtype: "Section Break", label: __("Filters") },
            {
                label: __("Academic Year"),
                fieldname: "academic_year",
                fieldtype: "Link",
                options: "Academic Year",
                default: default_ay,
                reqd: 1,
                change() { update_dialog_applicant_count(gd); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Admission Cycle"),
                fieldname: "admission_cycle",
                fieldtype: "Link",
                options: "Admission Cycle",
                default: default_ac,
                reqd: 1,
                change() { update_dialog_applicant_count(gd); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Programme Level"),
                fieldname: "program_level",
                fieldtype: "Select",
                options: "\nUndergraduate\nPostgraduate\nResearch Course",
                default: default_pl,
                reqd: 0,
                change() {
                    gd.set_value("program", "");
                    update_dialog_applicant_count(gd);
                }
            },
            { fieldtype: "Section Break" },
            {
                label: __("Applicant Type"),
                fieldname: "applicant_type",
                fieldtype: "Select",
                options: "Domestic Applicants\nInternational Applicants\nBoth",
                default: "Domestic Applicants",
                reqd: 1,
                change() { update_dialog_applicant_count(gd); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Programme"),
                fieldname: "program",
                fieldtype: "Link",
                options: "Programme",
                depends_on: "eval:doc.program_level",
                change() { update_dialog_applicant_count(gd); }
            },
            { fieldtype: "Section Break" },
            {
                fieldname: "total_applicants_html",
                fieldtype: "HTML"
            }
        ],
        primary_action_label: __("Generate"),
        primary_action(values) {
            frappe.confirm(
                __("This will generate Result Cards for all matching Attended applicants. Do you want to continue?"),
                function () {
                    gd.hide();
                    frappe.show_progress(__("Generating Result Cards"), 0, 100, __("Starting generation..."));
                    frappe.call({
                        method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.bulk_generate_result_cards",
                        args: {
                            academic_year: values.academic_year,
                            admission_cycle: values.admission_cycle,
                            program_level: values.program_level,
                            applicant_type: values.applicant_type,
                            program: values.program
                        },
                        callback: function (r) {
                            frappe.show_progress(__("Generating Result Cards"), 100, 100, __("Completed"));
                            setTimeout(() => frappe.hide_progress(), 3000);
                            if (!r.exc && r.message) {
                                frappe.msgprint({
                                    title: __("Generation Complete"),
                                    message: __(
                                        "<b>{0}</b> Result Cards generated successfully.",
                                        [r.message.generated]
                                    ),
                                    indicator: "green"
                                });
                                listview.refresh();
                            }
                        },
                        error: function () {
                            frappe.hide_progress();
                        }
                    });
                }
            );
        }
    });

    gd.listview = listview;

    gd.set_query("admission_cycle", function () {
        return { filters: { "status": "Active" } };
    });
    gd.set_query("program", function () {
        let pl = gd.get_value("program_level");
        if (pl) {
            return {
                query: "slcm.admission.doctype.entrance_test_generation.entrance_test_generation.get_program_query",
                filters: {
                    "program_level": pl,
                    "admission_cycle": gd.get_value("admission_cycle")
                }
            };
        }
        return {};
    });

    gd.show();

    if (default_ay || default_ac || default_pl) {
        gd.set_values({
            academic_year: default_ay,
            admission_cycle: default_ac,
            program_level: default_pl,
            applicant_type: "Domestic Applicants"
        });
    }

    ["academic_year", "admission_cycle", "program_level", "applicant_type", "program"].forEach(fn => {
        if (gd.fields_dict[fn] && gd.fields_dict[fn].$input) {
            gd.fields_dict[fn].$input.on("change blur input", () => update_dialog_applicant_count(gd));
        }
    });

    setTimeout(() => update_dialog_applicant_count(gd), 500);
}

/**
 * Helper to update the Total Applicants HTML tile in dialogs
 */
function update_dialog_applicant_count(d) {
    const html_field = d.get_field("total_applicants_html");
    if (!html_field) return;

    let ay = d.get_value("academic_year") || "";
    let ac = d.get_value("admission_cycle") || "";
    let pl = d.get_value("program_level") || "";
    let at = d.get_value("applicant_type") || "Domestic Applicants";
    let prog = d.get_value("program") || "";

    frappe.call({
        method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.get_applicant_count",
        args: {
            academic_year: ay,
            admission_cycle: ac,
            program_level: pl,
            applicant_type: at,
            program: prog
        },
        callback: function (r) {
            if (r && r.message) {
                const total = r.message.total !== undefined ? r.message.total : 0;
                const attended = r.message.attended !== undefined ? r.message.attended : 0;
                const absent = r.message.absent !== undefined ? r.message.absent : 0;
                html_field.$wrapper.html(`
                    <div style="background-color: #ebf8ff; border: 1px solid #bee3f8; border-radius: 8px; padding: 12px 16px; margin: 12px 0; display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #2b6cb0; font-weight: 600;">Total Applicants</div>
                            <div style="font-size: 22px; font-weight: 700; color: #2c5282; margin-top: 2px;">${total}</div>
                        </div>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <div style="background: #ffffff; padding: 6px 12px; border-radius: 6px; border: 1px solid #cbd5e0; font-size: 12px; font-weight: 600; color: #4a5568;">
                                Attended: <span style="color: #2b6cb0;">${attended}</span>
                            </div>
                            <div style="background: #ffffff; padding: 6px 12px; border-radius: 6px; border: 1px solid #cbd5e0; font-size: 12px; font-weight: 600; color: #4a5568;">
                                Absent: <span style="color: #e53e3e;">${absent}</span>
                            </div>
                            ${r.message.unpublished !== undefined ? `
                            <div style="background: #ffffff; padding: 6px 12px; border-radius: 6px; border: 1px solid #cbd5e0; font-size: 12px; font-weight: 600; color: #4a5568;">
                                Unpublished: <span style="color: #d97706;">${r.message.unpublished}</span>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                `);
            }
        }
    });
}

/**
 * Custom Export Marks Template Dialog for List View
 */
function open_export_marks_dialog_for_list(listview) {
    let d = new frappe.ui.Dialog({
        title: __('Export Entrance Test Marks Template'),
        fields: [
            {
                label: __('Academic Year'),
                fieldname: 'academic_year',
                fieldtype: 'Link',
                options: 'Academic Year'
            },
            {
                label: __('Admission Cycle'),
                fieldname: 'admission_cycle',
                fieldtype: 'Link',
                options: 'Admission Cycle'
            },
            {
                label: __('Campus'),
                fieldname: 'campus',
                fieldtype: 'Link',
                options: 'Campus'
            },
            {
                label: __('Programme Level'),
                fieldname: 'program_level',
                fieldtype: 'Select',
                options: '\nUndergraduate\nPostgraduate\nResearch Course'
            },
            {
                label: __('Programme'),
                fieldname: 'program',
                fieldtype: 'Link',
                options: 'Programme'
            },
            {
                label: __('Entrance Test'),
                fieldname: 'entrance_test',
                fieldtype: 'Link',
                options: 'Entrance Test'
            },
            {
                label: __('Shortlisted Only (Stage 2 - Part B)'),
                fieldname: 'shortlisted_only',
                fieldtype: 'Check',
                default: 0,
                description: __('Check this for Stage 2 (Part B marks entry) to export shortlisted applicants only with Part A marks pre-filled.')
            },
            {
                label: __('File Format'),
                fieldname: 'file_format',
                fieldtype: 'Select',
                options: 'xlsx\ncsv',
                default: 'xlsx',
                reqd: 1
            }
        ],
        primary_action_label: __('Export Template'),
        primary_action(values) {
            d.hide();
            frappe.show_alert({ message: __('Generating Marks Template...'), indicator: 'blue' });

            frappe.call({
                method: 'slcm.admission.utils.entrance_test_marks_manager.export_entrance_test_marks_template',
                args: values,
                freeze: true,
                freeze_message: __('Building Export File...'),
                callback: function (r) {
                    if (r.message && r.message.file_url) {
                        const link = document.createElement('a');
                        link.href = r.message.file_url;
                        link.download = r.message.filename || 'Marks_Template.xlsx';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);

                        frappe.show_alert({
                            message: __('Template downloaded successfully.'),
                            indicator: 'green'
                        });
                    }
                }
            });
        }
    });

    d.set_query("admission_cycle", function () {
        return { filters: { "status": "Active" } };
    });

    d.show();
}

// ──────────────────────────────────────────────────────────────────────────────
//  open_reschedule_dialog
//  Pre-fetches all active providers FIRST (same pattern as entrance_test_list.js),
//  then builds and shows the dialog with providers already embedded.
// ──────────────────────────────────────────────────────────────────────────────

// ──────────────────────────────────────────────────────────────────────────────
//  open_download_attendance_sheet_dialog
//  Shows a filter dialog then triggers an Attendance Sheet PDF download matching LLB.pdf.
// ──────────────────────────────────────────────────────────────────────────────
// ──────────────────────────────────────────────────────────────────────────────
//  MultiSelect Data Fetchers & Handlers
// ──────────────────────────────────────────────────────────────────────────────
function _patch_multiselect_status(field) {
    if (!field) return;
    const ctrl = field.control || field;
    if (!ctrl || typeof ctrl.set_status !== "function") return;

    if (ctrl._patched_comma_status) return;
    ctrl._patched_comma_status = true;

    ctrl.update_status = function () {
        let text;
        if (!this.values || this.values.length === 0) {
            text = this.get_placeholder_text();
        } else {
            let labels = this.values.map(val => {
                let opt = (this._options || []).find(o => o && o.value === val) ||
                          (this._selected_values || []).find(o => o && o.value === val);
                return opt ? (opt.label || opt.value) : val;
            });
            text = frappe.utils.escape_html(labels.join(", "));
        }
        this.set_status(text);
    };
}

function _get_city_options(dialog, txt) {
    const ay = dialog.get_value("academic_year") || "";
    const ac = dialog.get_value("admission_cycle") || "";
    if (!ay || !ac) return Promise.resolve([]);

    return frappe.call({
        method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.get_cities_for_filter",
        args: { academic_year: ay, admission_cycle: ac }
    }).then(r => {
        let cities = (r.message && r.message.cities) ? r.message.cities : [];
        if (txt) {
            const q = txt.toLowerCase();
            cities = cities.filter(c => c.toLowerCase().includes(q));
        }
        return cities.map(c => ({ value: c, label: c, description: "" }));
    });
}

function _get_centre_options(dialog, txt) {
    const ay = dialog.get_value("academic_year") || "";
    const ac = dialog.get_value("admission_cycle") || "";
    const pl = dialog.get_value("program_level") || "";
    const at = dialog.get_value("applicant_type") || "Domestic Applicants";
    const prog = dialog.get_value("program") || "";

    let city_raw = dialog.get_value("entrance_test_city");
    let cities = Array.isArray(city_raw) ? city_raw : (city_raw ? [city_raw] : []);
    cities = cities.filter(c => c && c !== "(All Cities)");

    if (!ay || !ac) return Promise.resolve([]);

    return frappe.call({
        method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.get_centre_list_preview",
        args: {
            academic_year: ay,
            admission_cycle: ac,
            program_level: pl,
            applicant_type: at,
            program: prog,
            center_name: "",
            entrance_test_city: cities
        }
    }).then(r => {
        let centres = (r.message && r.message.centres) ? r.message.centres : [];
        let items = centres.map(c => ({
            value: c.name,
            label: c.name,
            description: __("{0} candidates", [c.count])
        }));
        if (txt) {
            const q = txt.toLowerCase();
            items = items.filter(i => i.label.toLowerCase().includes(q) || (i.value && i.value.toLowerCase().includes(q)));
        }
        return items;
    });
}

function _on_city_change(dialog, is_excel) {
    const ay = dialog.get_value("academic_year") || "";
    const ac = dialog.get_value("admission_cycle") || "";
    const pl = dialog.get_value("program_level") || "";
    const at = dialog.get_value("applicant_type") || "Domestic Applicants";
    const prog = dialog.get_value("program") || "";

    let city_raw = dialog.get_value("entrance_test_city");
    let cities = Array.isArray(city_raw) ? city_raw : (city_raw ? [city_raw] : []);
    cities = cities.filter(c => c && c !== "(All Cities)");

    if (ay && ac) {
        frappe.call({
            method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.get_centre_list_preview",
            args: {
                academic_year: ay,
                admission_cycle: ac,
                program_level: pl,
                applicant_type: at,
                program: prog,
                center_name: "",
                entrance_test_city: cities
            },
            callback(r) {
                const valid_centres = (r.message && r.message.centres) ? r.message.centres.map(c => c.name) : [];
                let current_cn = dialog.get_value("center_name");
                let sel = Array.isArray(current_cn) ? current_cn : (current_cn ? [current_cn] : []);
                sel = sel.filter(c => valid_centres.includes(c));
                dialog.set_value("center_name", sel);

                if (is_excel) {
                    _update_centre_preview(dialog);
                } else {
                    _update_attendance_preview(dialog);
                }
            }
        });
    } else {
        if (is_excel) {
            _update_centre_preview(dialog);
        } else {
            _update_attendance_preview(dialog);
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────────
//  open_download_attendance_sheet_dialog
//  Shows a filter dialog then triggers Attendance Sheet PDF / ZIP download.
// ──────────────────────────────────────────────────────────────────────────────
function open_download_attendance_sheet_dialog(listview) {
    const default_ay = get_listview_filter_val(listview, "academic_year");
    const default_ac = get_listview_filter_val(listview, "admission_cycle");
    const default_pl = get_listview_filter_val(listview, "program_level");
    const default_prog = get_listview_filter_val(listview, "program");
    const default_cn = get_listview_filter_val(listview, "center_name");

    let ad = new frappe.ui.Dialog({
        title: __("Download Attendance Sheet"),
        size: "extra-large",
        fields: [
            // ── Row 1: Academic Year | Admission Cycle | Programme Level | Programme ──
            { fieldtype: "Section Break", label: __("Filters") },
            {
                label: __("Academic Year"),
                fieldname: "academic_year",
                fieldtype: "Link",
                options: "Academic Year",
                default: default_ay,
                reqd: 1,
                change() { _refresh_city_select(ad); _refresh_centre_select(ad); _update_attendance_preview(ad); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Admission Cycle"),
                fieldname: "admission_cycle",
                fieldtype: "Link",
                options: "Admission Cycle",
                default: default_ac,
                reqd: 1,
                change() { _refresh_city_select(ad); _refresh_centre_select(ad); _update_attendance_preview(ad); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Programme Level"),
                fieldname: "program_level",
                fieldtype: "Select",
                options: "\nUndergraduate\nPostgraduate\nResearch Course",
                default: default_pl,
                description: __("Leave blank for all Programme levels"),
                change() {
                    ad.set_value("program", "");
                    _refresh_centre_select(ad);
                    _update_attendance_preview(ad);
                }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Programme"),
                fieldname: "program",
                fieldtype: "Link",
                options: "Programme",
                default: default_prog,
                depends_on: "eval:doc.program_level",
                change() {
                    _refresh_city_select(ad);
                    _refresh_centre_select(ad);
                    _update_attendance_preview(ad);
                }
            },
            // ── Row 2: Applicant Type | Entrance Test City | Centre Name | Download Format ─────
            { fieldtype: "Section Break" },
            {
                label: __("Applicant Type"),
                fieldname: "applicant_type",
                fieldtype: "Select",
                options: "Domestic Applicants\nInternational Applicants\nBoth",
                default: "Domestic Applicants",
                reqd: 1,
                change() { _refresh_city_select(ad); _refresh_centre_select(ad); _update_attendance_preview(ad); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Entrance Test City"),
                fieldname: "entrance_test_city",
                fieldtype: "MultiSelectList",
                placeholder: __("(All Cities)"),
                description: __("Select one or more cities (leave empty for all)"),
                get_data(txt) { return _get_city_options(ad, txt); },
                change() { _on_city_change(ad, false); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Centre Name"),
                fieldname: "center_name",
                fieldtype: "MultiSelectList",
                placeholder: __("(All Centres)"),
                description: __("Select one or more centres (leave empty for all)"),
                get_data(txt) { return _get_centre_options(ad, txt); },
                change() { _update_attendance_preview(ad); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Download Format"),
                fieldname: "download_mode",
                fieldtype: "Select",
                options: "Separate PDFs per Centre (ZIP Archive)\nSingle Combined PDF File",
                default: "Separate PDFs per Centre (ZIP Archive)",
                description: __("Separate PDFs per centre in a ZIP archive prevents >10MB size limit errors."),
                change() { _update_attendance_preview(ad); }
            },
            // ── Preview section ────────────────────────────────────────────────
            { fieldtype: "Section Break", label: __("Preview") },
            {
                fieldname: "attendance_preview_html",
                fieldtype: "HTML",
                options: `<div id="att-preview" style="min-height:50px; display:flex; align-items:center; justify-content:center; color:#718096; font-size:13px;">
                    Fill the filters above to preview the data.
                </div>`
            }
        ],
        primary_action_label: `<span style="display:flex;align-items:center;gap:6px;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Download Attendance Sheet
        </span>`,
        primary_action(values) {
            if (!values.academic_year || !values.admission_cycle) {
                frappe.msgprint(__("Academic Year and Admission Cycle are required."));
                return;
            }

            let city_raw = ad.get_value("entrance_test_city");
            let cities = Array.isArray(city_raw) ? city_raw : (city_raw ? [city_raw] : []);
            cities = cities.filter(c => c && c !== "(All Cities)");

            let cn_raw = ad.get_value("center_name");
            let centres = Array.isArray(cn_raw) ? cn_raw : (cn_raw ? [cn_raw] : []);
            centres = centres.filter(c => c && c !== "(All Centres)");

            const mode_val = values.download_mode || "Separate PDFs per Centre (ZIP Archive)";

            ad.disable_primary_action();
            ad.get_primary_btn().text(__("Generating..."));

            if (!document.getElementById("att-progress-style")) {
                const st = document.createElement("style");
                st.id = "att-progress-style";
                st.textContent = `
                    @keyframes attPulse {
                        0%, 100% { transform: scale(0.8); opacity: 0.5; }
                        50% { transform: scale(1.2); opacity: 1; }
                    }
                `;
                document.head.appendChild(st);
            }

            const preview_el = ad.$wrapper.find("#att-preview")[0];
            if (preview_el) {
                preview_el.innerHTML = `
                    <div style="width:100%; padding:14px 18px; background:#f8fafc; border:1.5px solid #cbd5e1; border-radius:10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; font-size:13px; font-weight:600; color:#1e293b;">
                            <span id="att-pdf-status" style="display:flex; align-items:center; gap:8px;">
                                <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:#2563eb; animation: attPulse 1.2s infinite ease-in-out;"></span>
                                ${__("Generating Attendance Sheets...")}
                            </span>
                            <span id="att-pdf-pct" style="color:#2563eb; font-weight:700; font-size:14px;">0%</span>
                        </div>
                        <div style="background:#e2e8f0; border-radius:8px; height:16px; overflow:hidden; position:relative; margin-bottom:6px;">
                            <div id="att-pdf-bar" style="background: linear-gradient(90deg, #3b82f6, #1d4ed8); height:100%; width:0%; border-radius:8px; transition: width 0.3s ease;"></div>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:12px; color:#64748b;">
                            <span id="att-pdf-counter">${__("Initializing layout...")}</span>
                            <span id="att-pdf-sub">${__("Please wait while file is created...")}</span>
                        </div>
                    </div>`;
            }

            let target_pct = 5;
            let current_pct = 0;
            let current_desc = __("Initializing layout...");
            let current_counter = __("Preparing candidate records...");
            let is_completed = false;

            const pdf_rendering_messages = [
                __("Generating document structure..."),
                __("Formatting candidate pages and photo embeds..."),
                __("Applying print layout and page breaks..."),
                __("Compiling pages for download..."),
                __("Optimizing document stream..."),
                __("Finalizing file creation..."),
                __("Preparing download file...")
            ];
            let msg_idx = 0;

            const updateAttProgressUI = function (pct, status, counter) {
                const bar_el = ad.$wrapper.find("#att-pdf-bar")[0];
                const pct_el = ad.$wrapper.find("#att-pdf-pct")[0];
                const status_el = ad.$wrapper.find("#att-pdf-status")[0];
                const counter_el = ad.$wrapper.find("#att-pdf-counter")[0];

                const rounded_pct = Math.min(Math.round(pct), 100);
                if (bar_el) bar_el.style.width = rounded_pct + "%";
                if (pct_el) pct_el.textContent = rounded_pct + "%";
                if (status_el && status) {
                    status_el.innerHTML = `
                        <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:#2563eb; animation: attPulse 1.2s infinite ease-in-out;"></span>
                        ${status}
                    `;
                }
                if (counter_el && counter) counter_el.textContent = counter;
            };

            const progress_ticker = setInterval(() => {
                if (is_completed) return;

                if (current_pct < target_pct) {
                    current_pct += Math.max(0.4, (target_pct - current_pct) * 0.15);
                } else if (current_pct >= 75 && current_pct < 99) {
                    current_pct += 0.12;
                    if (current_pct > 99) current_pct = 99;
                }

                updateAttProgressUI(current_pct, current_desc, current_counter);
            }, 150);

            const msg_timer = setInterval(() => {
                if (is_completed) return;
                if (current_pct >= 70) {
                    current_desc = pdf_rendering_messages[msg_idx % pdf_rendering_messages.length];
                    msg_idx++;
                }
            }, 2000);

            frappe.realtime.on("attendance_sheet_progress", function (data) {
                if (is_completed) return;
                const backend_pct = data.progress || 0;
                if (backend_pct > target_pct) {
                    target_pct = backend_pct;
                }
                if (data.description && backend_pct < 75) {
                    current_desc = data.description;
                }
                if (data.total) {
                    current_counter = __("{0} of {1} candidates processed", [data.current || 0, data.total]);
                }
            });

            ad.onhide = function () {
                if (!is_completed) {
                    frappe.show_alert({
                        message: __("File generation is running in background. Your download will start automatically once ready."),
                        indicator: "blue"
                    }, 6);
                }
            };

            frappe.call({
                method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.download_attendance_sheet_pdf",
                args: {
                    academic_year: values.academic_year,
                    admission_cycle: values.admission_cycle,
                    program_level: values.program_level || "",
                    program: values.program || "",
                    applicant_type: values.applicant_type || "Domestic Applicants",
                    entrance_test_city: cities,
                    center_name: centres,
                    download_mode: mode_val
                },
                callback(r) {
                    is_completed = true;
                    clearInterval(progress_ticker);
                    clearInterval(msg_timer);
                    frappe.realtime.off("attendance_sheet_progress");

                    const is_zip = r.message && r.message.is_zip;
                    const success_msg = is_zip
                        ? __("✅ Attendance Sheet ZIP archive generated!")
                        : __("✅ Attendance Sheet PDF generated!");

                    updateAttProgressUI(100, success_msg, __("Starting download..."));

                    setTimeout(() => {
                        ad.enable_primary_action();
                        ad.get_primary_btn().html(ad.primary_action_label);

                        if (r.message && r.message.file_url) {
                            const { file_url, filename, total_candidates, total_pages, total_centres } = r.message;

                            const a = document.createElement("a");
                            a.href = file_url;
                            a.download = filename;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);

                            ad.hide();

                            const alert_msg = is_zip
                                ? __(
                                    `✅ Downloaded Attendance Sheets ZIP (<b>${total_centres}</b> centre PDFs) for <b>${total_candidates}</b> candidate(s).`
                                )
                                : __(
                                    `✅ Downloaded Attendance Sheet (<b>${total_pages}</b> pages) for <b>${total_candidates}</b> candidate(s).`
                                );

                            frappe.show_alert({
                                message: alert_msg,
                                indicator: "green"
                            }, 7);
                        }
                    }, 400);
                },
                error() {
                    is_completed = true;
                    clearInterval(progress_ticker);
                    clearInterval(msg_timer);
                    frappe.realtime.off("attendance_sheet_progress");
                    ad.enable_primary_action();
                    ad.get_primary_btn().html(ad.primary_action_label);
                    _update_attendance_preview(ad);
                }
            });
        }
    });

    ad.set_query("admission_cycle", () => ({ filters: { status: "Active" } }));
    ad.set_query("program", () => ({
        query: "slcm.admission.doctype.entrance_test_generation.entrance_test_generation.get_program_query",
        filters: {
            program_level: ad.get_value("program_level"),
            admission_cycle: ad.get_value("admission_cycle")
        }
    }));

    ad.show();

    if (default_ay || default_ac || default_pl || default_prog) {
        ad.set_values({
            academic_year: default_ay,
            admission_cycle: default_ac,
            program_level: default_pl,
            program: default_prog,
            applicant_type: "Domestic Applicants"
        });
    }

    if (default_cn) {
        ad.set_value("center_name", [default_cn]);
    }

    setTimeout(() => {
        _refresh_city_select(ad);
        _refresh_centre_select(ad);
        _update_attendance_preview(ad);
    }, 300);

    ["academic_year", "admission_cycle"].forEach(fn => {
        const f = ad.fields_dict[fn];
        if (f && f.$input) {
            f.$input.on("change blur", () => {
                _refresh_centre_select(ad);
                _update_attendance_preview(ad);
            });
        }
    });

    const prog_f = ad.fields_dict["program"];
    if (prog_f && prog_f.$input) {
        prog_f.$input.on("change blur", () => {
            _refresh_centre_select(ad);
            _update_attendance_preview(ad);
        });
    }
}

function _update_attendance_preview(ad) {
    const ay = ad.get_value("academic_year") || "";
    const ac = ad.get_value("admission_cycle") || "";
    const pl = ad.get_value("program_level") || "";
    const at = ad.get_value("applicant_type") || "Domestic Applicants";
    const prog = ad.get_value("program") || "";
    const download_mode = ad.get_value("download_mode") || "Separate PDFs per Centre (ZIP Archive)";

    let city_raw = ad.get_value("entrance_test_city");
    let cities = Array.isArray(city_raw) ? city_raw : (city_raw ? [city_raw] : []);
    cities = cities.filter(c => c && c !== "(All Cities)");

    let cn_raw = ad.get_value("center_name");
    let centres = Array.isArray(cn_raw) ? cn_raw : (cn_raw ? [cn_raw] : []);
    centres = centres.filter(c => c && c !== "(All Centres)");

    const preview_el = ad.$wrapper.find("#att-preview")[0];
    if (!preview_el) return;

    if (!ay || !ac) {
        preview_el.innerHTML = `<div style="min-height:50px; display:flex; align-items:center; justify-content:center; color:#718096; font-size:13px;">
            Select Academic Year and Admission Cycle to preview attendance sheet.
        </div>`;
        return;
    }

    frappe.call({
        method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.get_attendance_sheet_preview_count",
        args: {
            academic_year: ay,
            admission_cycle: ac,
            program_level: pl,
            program: prog,
            applicant_type: at,
            entrance_test_city: cities,
            center_name: centres
        },
        callback(r) {
            const count = (r.message && r.message.count != null) ? r.message.count : 0;
            const total_centres = (r.message && r.message.total_centres != null) ? r.message.total_centres : 0;
            const pages = Math.ceil(count / 10);

            let format_text = "Single PDF File";
            if (total_centres > 1 && download_mode !== "Single Combined PDF File") {
                format_text = `ZIP Archive (${total_centres} Centre PDF files)`;
            } else if (download_mode === "Single Combined PDF File") {
                format_text = `Single Combined PDF (${count} Candidates, ${pages} Pages)`;
            } else {
                format_text = `Single PDF File (${count} Candidates, ${pages} Pages)`;
            }

            preview_el.innerHTML = `
                <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:12px 18px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px;">
                    <div>
                        <span style="font-size:14px; font-weight:600; color:#166534;">Total Candidates: <b>${count}</b></span>
                        <span style="font-size:12px; color:#15803d; margin-left:12px;">(${pages} page${pages === 1 ? '' : 's'} &bull; 10 candidates/page &bull; <b>${total_centres}</b> centre${total_centres === 1 ? '' : 's'})</span>
                    </div>
                    <div style="font-size:12px; color:#374151;">
                        Format: <b>${format_text}</b>
                    </div>
                </div>
            `;
        }
    });
}

// ──────────────────────────────────────────────────────────────────────────────
//  open_centre_list_download_dialog
//  Shows a filter dialog then triggers a per-centre Excel download (ZIP).
// ──────────────────────────────────────────────────────────────────────────────
function open_centre_list_download_dialog(listview) {
    const default_ay = get_listview_filter_val(listview, "academic_year");
    const default_ac = get_listview_filter_val(listview, "admission_cycle");
    const default_pl = get_listview_filter_val(listview, "program_level");
    const default_cn = get_listview_filter_val(listview, "center_name");

    let cd = new frappe.ui.Dialog({
        title: __("Centre List Download"),
        size: "extra-large",
        fields: [
            // ── Row 1: Academic Year | Admission Cycle | Programme Level ──────
            { fieldtype: "Section Break", label: __("Filters") },
            {
                label: __("Academic Year"),
                fieldname: "academic_year",
                fieldtype: "Link",
                options: "Academic Year",
                default: default_ay,
                reqd: 1,
                change() { _refresh_city_select(cd); _refresh_centre_select(cd); _update_centre_preview(cd); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Admission Cycle"),
                fieldname: "admission_cycle",
                fieldtype: "Link",
                options: "Admission Cycle",
                default: default_ac,
                reqd: 1,
                change() { _refresh_city_select(cd); _refresh_centre_select(cd); _update_centre_preview(cd); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Programme Level"),
                fieldname: "program_level",
                fieldtype: "Select",
                options: "\nUndergraduate\nPostgraduate\nResearch Course",
                default: default_pl,
                description: __("Leave blank for all Programme level"),
                change() {
                    cd.set_value("program", "");
                    _refresh_centre_select(cd);
                    _update_centre_preview(cd);
                }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Programme"),
                fieldname: "program",
                fieldtype: "Link",
                options: "Programme",
                depends_on: "eval:doc.program_level",
                change() {
                    _refresh_city_select(cd);
                    _refresh_centre_select(cd);
                    _update_centre_preview(cd);
                }
            },
            // ── Row 2: Applicant Type | Entrance Test City | Centre Name ─────
            { fieldtype: "Section Break" },
            {
                label: __("Applicant Type"),
                fieldname: "applicant_type",
                fieldtype: "Select",
                options: "Domestic Applicants\nInternational Applicants\nBoth",
                default: "Domestic Applicants",
                reqd: 1,
                change() { _refresh_city_select(cd); _refresh_centre_select(cd); _update_centre_preview(cd); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Entrance Test City"),
                fieldname: "entrance_test_city",
                fieldtype: "MultiSelectList",
                placeholder: __("(All Cities)"),
                description: __("Select one or more cities (leave empty for all)"),
                get_data(txt) { return _get_city_options(cd, txt); },
                change() { _on_city_change(cd, true); }
            },
            { fieldtype: "Column Break" },
            {
                label: __("Centre Name"),
                fieldname: "center_name",
                fieldtype: "MultiSelectList",
                placeholder: __("(All Centres)"),
                description: __("Select one or more centres (leave empty for all)"),
                get_data(txt) { return _get_centre_options(cd, txt); },
                change() { _update_centre_preview(cd); }
            },
            // ── Preview section ────────────────────────────────────────────────
            { fieldtype: "Section Break", label: __("Preview") },
            {
                fieldname: "centre_preview_html",
                fieldtype: "HTML",
                options: `<div id="cldd-preview" style="min-height:70px; display:flex; align-items:center; justify-content:center; color:#718096; font-size:13px;">
                    Fill the filters above to preview the data.
                </div>`
            }
        ],
        primary_action_label: `<span style="display:flex;align-items:center;gap:6px;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Download Excel ZIP
        </span>`,
        primary_action(values) {
            if (!values.academic_year || !values.admission_cycle) {
                frappe.msgprint(__("Academic Year and Admission Cycle are required."));
                return;
            }

            let city_raw = cd.get_value("entrance_test_city");
            let cities = Array.isArray(city_raw) ? city_raw : (city_raw ? [city_raw] : []);
            cities = cities.filter(c => c && c !== "(All Cities)");

            let cn_raw = cd.get_value("center_name");
            let centres = Array.isArray(cn_raw) ? cn_raw : (cn_raw ? [cn_raw] : []);
            centres = centres.filter(c => c && c !== "(All Centres)");

            cd.disable_primary_action();
            cd.get_primary_btn().text(__("Generating..."));

            if (!document.getElementById("att-progress-style")) {
                const st = document.createElement("style");
                st.id = "att-progress-style";
                st.textContent = `
                    @keyframes attPulse {
                        0%, 100% { transform: scale(0.8); opacity: 0.5; }
                        50% { transform: scale(1.2); opacity: 1; }
                    }
                `;
                document.head.appendChild(st);
            }

            const preview_el = cd.$wrapper.find("#cldd-preview")[0];
            if (preview_el) {
                preview_el.innerHTML = `
                    <div style="width:100%; padding:14px 18px; background:#f8fafc; border:1.5px solid #cbd5e1; border-radius:10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; font-size:13px; font-weight:600; color:#1e293b;">
                            <span id="cldd-excel-status" style="display:flex; align-items:center; gap:8px;">
                                <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:#2563eb; animation: attPulse 1.2s infinite ease-in-out;"></span>
                                ${__("Building Excel sheets per centre...")}
                            </span>
                            <span id="cldd-excel-pct" style="color:#2563eb; font-weight:700; font-size:14px;">0%</span>
                        </div>
                        <div style="background:#e2e8f0; border-radius:8px; height:16px; overflow:hidden; position:relative; margin-bottom:6px;">
                            <div id="cldd-excel-bar" style="background: linear-gradient(90deg, #3b82f6, #1d4ed8); height:100%; width:0%; border-radius:8px; transition: width 0.3s ease;"></div>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:12px; color:#64748b;">
                            <span id="cldd-excel-counter">${__("Processing records...")}</span>
                            <span id="cldd-excel-sub">${__("Please wait while ZIP is created...")}</span>
                        </div>
                    </div>`;
            }

            const updateClddProgress = function (pct, status, counter) {
                const bar_el = cd.$wrapper.find("#cldd-excel-bar")[0];
                const pct_el = cd.$wrapper.find("#cldd-excel-pct")[0];
                const status_el = cd.$wrapper.find("#cldd-excel-status")[0];
                const counter_el = cd.$wrapper.find("#cldd-excel-counter")[0];

                const rounded_pct = Math.min(Math.round(pct), 100);
                if (bar_el) bar_el.style.width = rounded_pct + "%";
                if (pct_el) pct_el.textContent = rounded_pct + "%";
                if (status_el && status) {
                    status_el.innerHTML = `
                        <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:#2563eb; animation: attPulse 1.2s infinite ease-in-out;"></span>
                        ${status}
                    `;
                }
                if (counter_el && counter) counter_el.textContent = counter;
            };

            let sim_pct = 5;
            const sim_timer = setInterval(() => {
                if (sim_pct < 85) {
                    sim_pct += Math.floor(Math.random() * 7) + 4;
                    if (sim_pct > 85) sim_pct = 85;
                    updateClddProgress(sim_pct, __("Formatting Excel workbooks per centre..."), __("Packing files into ZIP..."));
                }
            }, 350);

            frappe.call({
                method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.download_centre_list_excel",
                args: {
                    academic_year: values.academic_year,
                    admission_cycle: values.admission_cycle,
                    program_level: values.program_level || "",
                    program: values.program || "",
                    applicant_type: values.applicant_type || "Domestic Applicants",
                    entrance_test_city: cities,
                    center_name: centres
                },
                callback(r) {
                    clearInterval(sim_timer);
                    updateClddProgress(100, __("Excel ZIP generated!"), __("Starting download..."));

                    setTimeout(() => {
                        cd.enable_primary_action();
                        cd.get_primary_btn().html(cd.primary_action_label);

                        if (r.message && r.message.file_url) {
                            const { file_url, filename, total_centres, total_applicants } = r.message;

                            const a = document.createElement("a");
                            a.href = file_url;
                            a.download = filename;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);

                            cd.hide();

                            frappe.show_alert({
                                message: __(
                                    `✅ Downloaded <b>${total_centres}</b> centre sheet(s) for <b>${total_applicants}</b> applicant(s).`
                                ),
                                indicator: "green"
                            }, 7);
                        }
                    }, 400);
                },
                error() {
                    clearInterval(sim_timer);
                    cd.enable_primary_action();
                    cd.get_primary_btn().html(cd.primary_action_label);
                    _update_centre_preview(cd);
                }
            });
        }
    });

    cd.set_query("admission_cycle", () => ({ filters: { status: "Active" } }));
    cd.set_query("program", () => ({
        query: "slcm.admission.doctype.entrance_test_generation.entrance_test_generation.get_program_query",
        filters: {
            program_level: cd.get_value("program_level"),
            admission_cycle: cd.get_value("admission_cycle")
        }
    }));

    cd.show();

    const pre_fill = () => {
        if (default_ay || default_ac || default_pl) {
            cd.set_values({
                academic_year: default_ay,
                admission_cycle: default_ac,
                program_level: default_pl,
                applicant_type: "Domestic Applicants"
            });
        }
        if (default_cn) {
            cd.set_value("center_name", [default_cn]);
        }
        setTimeout(() => {
            _refresh_city_select(cd);
            _refresh_centre_select(cd);
            _update_centre_preview(cd);
        }, 300);
    };
    pre_fill();

    ["academic_year", "admission_cycle"].forEach(fn => {
        const f = cd.fields_dict[fn];
        if (f && f.$input) {
            f.$input.on("change blur", () => {
                _refresh_centre_select(cd);
                _update_centre_preview(cd);
            });
        }
    });

    const prog_f = cd.fields_dict["program"];
    if (prog_f && prog_f.$input) {
        prog_f.$input.on("change blur", () => {
            _refresh_centre_select(cd);
            _update_centre_preview(cd);
        });
    }
}

/**
 * Refresh the Entrance Test City select options for MultiSelectList controls.
 */
function _refresh_city_select(dialog) {
    const f = dialog.fields_dict["entrance_test_city"];
    if (f) {
        _patch_multiselect_status(f);
        if (f.set_options) f.set_options();
    }
}

/**
 * Refresh the Centre Name select options for MultiSelectList controls.
 */
function _refresh_centre_select(dialog) {
    const f = dialog.fields_dict["center_name"];
    if (f) {
        _patch_multiselect_status(f);
        if (f.set_options) f.set_options();
    }
}

/**
 * Fetch and render a preview tile: total applicants + list of centres in the selection.
 */
function _update_centre_preview(cd) {
    const ay = cd.get_value("academic_year") || "";
    const ac = cd.get_value("admission_cycle") || "";
    const pl = cd.get_value("program_level") || "";
    const at = cd.get_value("applicant_type") || "Domestic Applicants";
    const prog = cd.get_value("program") || "";

    let city_raw = cd.get_value("entrance_test_city");
    let cities = Array.isArray(city_raw) ? city_raw : (city_raw ? [city_raw] : []);
    cities = cities.filter(c => c && c !== "(All Cities)");

    let cn_raw = cd.get_value("center_name");
    let centres = Array.isArray(cn_raw) ? cn_raw : (cn_raw ? [cn_raw] : []);
    centres = centres.filter(c => c && c !== "(All Centres)");

    const preview_el = cd.$wrapper.find("#cldd-preview")[0];
    if (!preview_el) return;

    if (!ay || !ac) {
        preview_el.innerHTML = `<div style="color:#718096;font-size:13px;padding:12px 0;text-align:center;">Fill <b>Academic Year</b> and <b>Admission Cycle</b> to preview data.</div>`;
        return;
    }

    preview_el.innerHTML = `<div style="color:#718096;font-size:13px;padding:12px 0;text-align:center;">
        <span style="display:inline-flex;align-items:center;gap:6px;">
            <span class="cldd-spinner" style="width:14px;height:14px;border:2px solid #BFDBFE;border-top-color:#1E40AF;border-radius:50%;animation:clddSpin 0.7s linear infinite;display:inline-block;"></span>
            Loading preview...
        </span>
    </div>`;
    if (!document.getElementById("cldd-spin-style")) {
        const st = document.createElement("style");
        st.id = "cldd-spin-style";
        st.textContent = "@keyframes clddSpin { to { transform: rotate(360deg); } }";
        document.head.appendChild(st);
    }

    frappe.call({
        method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.get_centre_list_preview",
        args: {
            academic_year: ay,
            admission_cycle: ac,
            program_level: pl,
            applicant_type: at,
            program: prog,
            center_name: centres,
            entrance_test_city: cities
        },
        callback(r) {
            if (!r.message) {
                preview_el.innerHTML = `<div style="color:#e53e3e;font-size:13px;padding:10px 0;text-align:center;">No data found for the selected filters.</div>`;
                return;
            }
            const { total_applicants, centres: centres_list } = r.message;

            let pills_html = "";
            if (centres_list && centres_list.length > 0) {
                pills_html = centres_list.map(c => `
                    <span style="display:inline-flex; align-items:center; background:#e0f2fe; color:#0369a1; border-radius:12px; padding:3px 10px; font-size:12px; font-weight:500; margin:3px;">
                        ${c.name} <span style="margin-left:4px; background:#0284c7; color:#fff; border-radius:8px; padding:1px 6px; font-size:11px;">${c.count}</span>
                    </span>
                `).join("");
            }

            preview_el.innerHTML = `
                <div style="background:#f8fafc; border:1px solid #cbd5e1; border-radius:8px; padding:12px 16px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:8px; font-size:13px; font-weight:600;">
                        <span>Total Applicants: <b>${total_applicants}</b></span>
                        <span style="color:#475569;">Selected Centres: <b>${centres_list ? centres_list.length : 0}</b></span>
                    </div>
                    <div style="max-height:90px; overflow-y:auto; display:flex; flex-wrap:wrap; gap:4px; margin-top:6px;">
                        ${pills_html || '<span style="color:#94a3b8; font-size:12px;">No centres found.</span>'}
                    </div>
                </div>
            `;
        }
    });
}

function _render_centre_preview_error(el) {
    if (el) el.innerHTML = `<div style="color:#e53e3e;font-size:13px;padding:10px 0;text-align:center;">Failed to load preview. Please check filters.</div>`;
}

function open_reschedule_dialog(listview) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Entrance Test Provider',
            filters: {
                active: 1,
                available_capacity: [">", 0]
            },
            fields: ['name', 'center_name', 'center_address', 'campus', 'provider_type'],
            limit_page_length: 200
        },
        callback: function (r) {
            const all_providers = r.message || [];
            if (!all_providers.length) {
                frappe.msgprint({
                    title: __('No Available Providers'),
                    message: __('No active Entrance Test Providers with available seats found in the system.'),
                    indicator: 'orange'
                });
                return;
            }
            _show_reschedule_dialog(listview, all_providers);
        }
    });
}

// Build provider checkboxes HTML (3-column grid style with search)
function _build_provider_html(providers) {
    if (!providers.length) {
        return '<p class="text-muted" style="padding:10px 0;">No providers match the selected campus.</p>';
    }
    const items = providers.map(p => `
        <label class="provider-card"
               data-center-name="${(p.center_name || p.name).toLowerCase()}"
               data-center-address="${(p.center_address || '').toLowerCase()}"
               style="display:flex; align-items:flex-start; gap:10px; padding:10px 12px;
                      border:1.5px solid #cbd5e1; border-radius:8px; cursor:pointer;
                      background:#ffffff; transition: all 0.15s ease; margin:0; box-shadow:0 1px 2px rgba(0,0,0,0.04);
                      position:relative; min-height:64px; box-sizing:border-box;">
            <input type="checkbox" class="provider-checkbox"
                   data-name="${p.name}"
                   data-campus="${p.campus || ''}"
                   style="width:16px; height:16px; cursor:pointer; margin-top:2px; flex-shrink:0;">
            <span style="line-height:1.4; flex:1; overflow:hidden;">
                <span style="display:block; font-weight:700; font-size:13px; color:#1e293b; text-overflow:ellipsis; overflow:hidden; white-space:nowrap;" title="${p.center_name || p.name}">
                    ${p.center_name || p.name}
                </span>
                ${p.center_address
            ? `<span style="display:block; font-size:11px; color:#64748b; margin-top:2px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;" title="${p.center_address}">
                           📍 ${p.center_address}
                       </span>`
            : `<span style="display:block; font-size:11px; color:#94a3b8; margin-top:2px; font-style:italic;">No address provided</span>`
        }
            </span>
        </label>
    `).join('');

    return `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <div id="provider-sel-count" style="font-size:12px; color:#6c757d; font-weight:500;">
                0 provider(s) selected
            </div>
            <div style="position:relative; width:220px;">
                <input type="text" id="reschedule-center-search" placeholder="${__("🔍 Search centre...")}" 
                       style="width:100%; padding:5px 10px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px; outline:none; background:#ffffff;">
            </div>
        </div>
        <div id="provider-list" style="display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:10px; max-height:200px; overflow-y:auto; padding:6px; border:1px solid #e2e8f0; border-radius:8px; background:#f8fafc;">
            ${items}
        </div>
    `;
}

function _show_reschedule_dialog(listview, all_providers) {
    let applicants = [];
    const selected_applicant_names = new Set();
    let applicant_current_page = 1;
    const applicant_page_size = 10;
    let applicant_filters = {
        applicant_id: "",
        candidate_name: "",
        programme: "",
        pwd_only: false
    };

    function get_filtered_applicants() {
        return applicants.filter(a => {
            const id_match = !applicant_filters.applicant_id || (a.applicant || "").toLowerCase().includes(applicant_filters.applicant_id);
            const name_match = !applicant_filters.candidate_name || (a.candidate_name || "").toLowerCase().includes(applicant_filters.candidate_name);
            const prog_match = !applicant_filters.programme || (a.program || "").toLowerCase().includes(applicant_filters.programme);
            let pwd_match = true;
            if (applicant_filters.pwd_only) {
                pwd_match = (a.pwd == 1 || (a.pwd || "").toString().toLowerCase() === "yes");
            }
            return id_match && name_match && prog_match && pwd_match;
        });
    }

    function render_applicant_page() {
        const filtered = get_filtered_applicants();
        const total_pages = Math.ceil(filtered.length / applicant_page_size) || 1;
        if (applicant_current_page > total_pages) applicant_current_page = total_pages;
        if (applicant_current_page < 1) applicant_current_page = 1;

        const start = (applicant_current_page - 1) * applicant_page_size;
        const page_applicants = filtered.slice(start, start + applicant_page_size);

        if (!page_applicants.length) {
            d.$wrapper.find("#reschedule-applicant-table-body").html(`
                <tr>
                    <td colspan="5" style="text-align:center; padding:25px; color:#94a3b8; font-size:13px;">
                        No applicants match the filter criteria.
                    </td>
                </tr>
            `);
        } else {
            const rows_html = page_applicants.map((row, p_idx) => {
                const global_idx = start + p_idx + 1;
                const is_checked = selected_applicant_names.has(row.name);
                return `
                    <tr data-name="${row.name}">
                        <td style="text-align:center; width:40px; vertical-align:middle;">
                            <input type="checkbox" class="applicant-checkbox" 
                                   data-name="${row.name}" ${is_checked ? 'checked' : ''}>
                        </td>
                        <td style="text-align:center; width:60px; color:#64748b; font-size:12px; vertical-align:middle;">${global_idx}</td>
                        <td style="vertical-align:middle;">${row.applicant || "-"}</td>
                        <td style="vertical-align:middle;">
                            <b>${row.candidate_name || "Unknown"}</b>
                            ${(row.pwd == 1 || (row.pwd || "").toString().toLowerCase() === "yes") ? `<span style="font-size:10px; background:#fef3c7; color:#92400e; padding:1px 5px; border-radius:4px; margin-left:4px; border:1px solid #fde68a; font-weight:700;">♿ PWD</span>` : ''}
                        </td>
                        <td style="vertical-align:middle;">${row.program || "-"}</td>
                    </tr>
                `;
            }).join("");

            d.$wrapper.find("#reschedule-applicant-table-body").html(rows_html);
        }

        d.$wrapper.find("#applicant-page-info").text(`Page ${applicant_current_page} of ${total_pages}`);
        d.$wrapper.find("#applicant-prev-btn").prop("disabled", applicant_current_page <= 1);
        d.$wrapper.find("#applicant-next-btn").prop("disabled", applicant_current_page >= total_pages);

        update_applicant_counts(filtered.length);
    }

    function update_applicant_counts(filtered_length) {
        const sel_count = selected_applicant_names.size;
        const total_count = applicants.length;
        if (filtered_length !== undefined && filtered_length !== total_count) {
            d.$wrapper.find("#sel-count").text(`${sel_count} of ${total_count} selected (Filtered: ${filtered_length})`);
        } else {
            d.$wrapper.find("#sel-count").text(`${sel_count} of ${total_count} selected`);
        }
        const all_selected = total_count > 0 && sel_count === total_count;
        d.$wrapper.find("#select-all-chk").prop("checked", all_selected);
    }

    let d = new frappe.ui.Dialog({
        title: __('Reschedule Entrance Test'),
        size: 'extra-large',
        fields: [
            // ── Filters (horizontal 4-column) ─────────────────────────────────
            { fieldtype: 'Section Break', label: __('Filters') },
            {
                label: __('Programme Level'),
                fieldname: 'program_level',
                fieldtype: 'Select',
                options: 'Undergraduate\nPostgraduate\nResearch Course',
                on_change: () => fetch_absent_applicants()
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Academic Year'),
                fieldname: 'academic_year',
                fieldtype: 'Link',
                options: 'Academic Year',
                on_change: () => fetch_absent_applicants()
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Campus'),
                fieldname: 'campus',
                fieldtype: 'Link',
                options: 'Campus',
                on_change: () => {
                    fetch_absent_applicants();
                    _filter_providers_by_campus(d, all_providers);
                }
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Admission Cycle'),
                fieldname: 'admission_cycle',
                fieldtype: 'Link',
                options: 'Admission Cycle',
                on_change: () => fetch_absent_applicants()
            },

            // ── Providers (pre-built HTML) ─────────────────────────────────────
            {
                fieldtype: 'Section Break',
                label: __('Select Entrance Test Providers (Preferences)')
            },
            {
                fieldtype: 'HTML',
                fieldname: 'providers_html',
                options: _build_provider_html(all_providers)
            },

            // ── Settings ──────────────────────────────────────────────────────
            { fieldtype: 'Section Break', label: __('Reschedule Settings') },
            {
                label: __('New Allocation Date'),
                fieldname: 'allocation_date',
                fieldtype: 'Datetime',
                reqd: 1,
                description: __('Must be today or a future date/time')
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Auto-select (Enter Number)'),
                fieldname: 'auto_select_count',
                fieldtype: 'Int',
                description: __('Auto-select first N absent applicants')
            },
            {
                label: __("Entrance Test Name"),
                fieldname: "re_entrance_test_name",
                fieldtype: "Link",
                options: "Entrance Test",
                reqd: 1
            },
            { fieldtype: 'Section Break' },
            {
                label: __('Reason for Reschedule'),
                fieldname: 'reschedule_reason',
                fieldtype: 'Small Text',
                reqd: 1,
                description: __('This reason will be included in the email sent to applicants')
            },

            // ── Applicants table ───────────────────────────────────────────────
            { fieldtype: 'Section Break', label: __('Select Absent Applicants') },
            {
                fieldtype: 'HTML',
                fieldname: 'applicants_html'
            }
        ],
        primary_action_label: __('Reschedule'),
        primary_action(values) {
            const selected_applicants = Array.from(selected_applicant_names);
            const selected_providers = [];
            d.$wrapper.find('.provider-checkbox:checked').each(function () {
                selected_providers.push($(this).data('name'));
            });

            if (!selected_applicants.length) {
                frappe.msgprint(__('Please select at least one applicant.'));
                return;
            }
            if (!selected_providers.length) {
                frappe.msgprint(__('Please select at least one provider.'));
                return;
            }

            frappe.call({
                method: 'slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.reschedule_applicants',
                args: {
                    applicants: selected_applicants,
                    providers: selected_providers,
                    allocation_date: values.allocation_date,
                    reschedule_reason: values.reschedule_reason,
                    re_entrance_test_name: values.re_entrance_test_name
                },
                freeze: true,
                freeze_message: __('Rescheduling Applicants...'),
                callback: function (r) {
                    if (!r.exc) {
                        d.hide();
                        listview.refresh();
                        frappe.show_alert({
                            message: __('Successfully rescheduled {0} applicants.', [selected_applicants.length]),
                            indicator: 'green'
                        });
                    }
                }
            });
        }
    });

    d.show();

    d.set_query("admission_cycle", function () {
        return {
            filters: {
                "status": "Active"
            }
        };
    });

    // Set query for re_entrance_test_name with correct filtering
    d.set_query("re_entrance_test_name", () => {
        const campus = d.get_value("campus");
        const academic_year = d.get_value("academic_year");
        const admission_cycle = d.get_value("admission_cycle");
        return {
            filters: [
                ["Entrance Test", "campus", "=", campus],
                ["Entrance Test", "academic_year", "=", academic_year],
                ["Entrance Test", "admission_cycle", "=", admission_cycle],
                ["Entrance Test", "is_active", "=", 1]
            ]
        };
    });

    // ── Center search filtering ───────────────────────────────────────────────
    d.$wrapper.on("input keyup search", "#reschedule-center-search", function () {
        const q = $(this).val().toLowerCase().trim();
        d.$wrapper.find(".provider-card").each(function () {
            const name = $(this).attr("data-center-name") || "";
            const addr = $(this).attr("data-center-address") || "";
            if (!q || name.includes(q) || addr.includes(q)) {
                $(this).css("display", "flex");
            } else {
                $(this).css("display", "none");
            }
        });
    });

    // ── Provider checkbox count & card highlight ──────────────────────────────
    d.$wrapper.on('change', '.provider-checkbox', function () {
        const n = d.$wrapper.find('.provider-checkbox:checked').length;
        d.$wrapper.find('#provider-sel-count').text(`${n} provider(s) selected`);

        d.$wrapper.find(".provider-card").each(function () {
            const $chk = $(this).find(".provider-checkbox");
            if ($chk.is(":checked")) {
                $(this).css({
                    "border-color": "#2da44e",
                    "background-color": "#f0fdf4",
                    "box-shadow": "0 2px 6px rgba(45,164,78,0.15)"
                });
            } else {
                $(this).css({
                    "border-color": "#cbd5e1",
                    "background-color": "#ffffff",
                    "box-shadow": "0 1px 2px rgba(0,0,0,0.04)"
                });
            }
        });
    });

    // ── Min-date restriction: block past dates on New Allocation Date ──────────
    setTimeout(() => {
        const $input = d.fields_dict.allocation_date.$input;
        // Frappe wraps the datetime input — try to get flatpickr instance
        const fp = $input[0]._flatpickr;
        if (fp) {
            fp.set('minDate', new Date());
        } else {
            // Fallback: set min attribute on the raw input
            const now = frappe.datetime.get_datetime_as_string(new Date());
            $input.attr('min', now);
        }
    }, 400);

    // Also validate on change in case the user types a date manually
    d.fields_dict.allocation_date.$input.on('change blur', function () {
        const val = d.get_value('allocation_date');
        if (val && frappe.datetime.str_to_obj(val) < new Date()) {
            frappe.show_alert({ message: __('New Allocation Date must be today or in the future.'), indicator: 'red' });
            d.set_value('allocation_date', null);
        }
    });

    // ── Auto-select logic ──────────────────────────────────────────────────────
    d.fields_dict.auto_select_count.$input.on('input', function () {
        const val = parseInt($(this).val()) || 0;
        selected_applicant_names.clear();
        for (let i = 0; i < Math.min(val, applicants.length); i++) {
            selected_applicant_names.add(applicants[i].name);
        }
        applicant_current_page = 1;
        render_applicant_page();
    });

    // ── Applicant Filtering & Pagination Events ────────────────────────────────
    d.$wrapper.on("input", "#filter-applicant-id", function () {
        applicant_filters.applicant_id = $(this).val().toLowerCase().trim();
        applicant_current_page = 1;
        render_applicant_page();
    });
    d.$wrapper.on("input", "#filter-candidate-name", function () {
        applicant_filters.candidate_name = $(this).val().toLowerCase().trim();
        applicant_current_page = 1;
        render_applicant_page();
    });
    d.$wrapper.on("input", "#filter-programme", function () {
        applicant_filters.programme = $(this).val().toLowerCase().trim();
        applicant_current_page = 1;
        render_applicant_page();
    });
    d.$wrapper.on("change", "#pwd-applicant-filter-chk", function () {
        applicant_filters.pwd_only = this.checked;
        applicant_current_page = 1;
        render_applicant_page();
    });
    d.$wrapper.on("click", "#applicant-clear-all-btn", function () {
        selected_applicant_names.clear();
        render_applicant_page();
    });
    d.$wrapper.on("click", "#applicant-prev-btn", function () {
        if (applicant_current_page > 1) {
            applicant_current_page--;
            render_applicant_page();
        }
    });
    d.$wrapper.on("click", "#applicant-next-btn", function () {
        const filtered = get_filtered_applicants();
        const total_pages = Math.ceil(filtered.length / applicant_page_size) || 1;
        if (applicant_current_page < total_pages) {
            applicant_current_page++;
            render_applicant_page();
        }
    });
    d.$wrapper.on("change", ".applicant-checkbox", function () {
        const name = $(this).data("name");
        if (this.checked) {
            selected_applicant_names.add(name);
        } else {
            selected_applicant_names.delete(name);
        }
        update_applicant_counts(get_filtered_applicants().length);
    });
    d.$wrapper.on("change", "#select-all-chk", function () {
        const filtered = get_filtered_applicants();
        if (this.checked) {
            filtered.forEach(a => selected_applicant_names.add(a.name));
        } else {
            filtered.forEach(a => selected_applicant_names.delete(a.name));
        }
        render_applicant_page();
    });

    // ── Initial applicant fetch ────────────────────────────────────────────────
    function fetch_absent_applicants() {
        const filters = {
            entrance_test_status: 'Absent',
            is_rescheduled: 0
        };

        if (d.get_value('program_level')) filters.program_level = d.get_value('program_level');
        if (d.get_value('academic_year')) filters.academic_year = d.get_value('academic_year');
        if (d.get_value('campus')) filters.campus = d.get_value('campus');
        if (d.get_value('admission_cycle')) filters.admission_cycle = d.get_value('admission_cycle');

        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Entrance Test Seat Allocation',
                filters: filters,
                fields: ['name', 'candidate_name', 'applicant', 'program', 'pwd'],
                limit_page_length: 0
            },
            callback: function (r) {
                applicants = r.message || [];
                selected_applicant_names.clear();
                applicant_current_page = 1;

                let html = `
                    <div style="margin-bottom:10px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                        <div style="display:flex; gap:12px; align-items:center;">
                            <label style="font-weight:600; cursor:pointer; margin:0; display:flex; align-items:center; font-size:13px;">
                                <input type="checkbox" id="select-all-chk" style="width:15px; height:15px; cursor:pointer; margin-right:6px;">
                                Select All
                            </label>
                            <label style="font-weight:600; cursor:pointer; margin:0; display:flex; align-items:center; font-size:13px; margin-left:12px;" title="Filter PWD Applicants">
                                <input type="checkbox" id="pwd-applicant-filter-chk" style="width:15px; height:15px; cursor:pointer; margin-right:6px;" ${applicant_filters.pwd_only ? 'checked' : ''}>
                                ♿ PWD
                            </label>
                            <button type="button" id="applicant-clear-all-btn" class="btn btn-xs btn-default" style="font-size:11px; padding:2px 8px; border-radius:4px;">
                                Clear All
                            </button>
                            <span id="sel-count" style="color:#6c757d; font-size:12px; font-weight:500;">
                                0 of ${applicants.length} selected
                            </span>
                        </div>
                        <div id="applicant-pagination" style="display:flex; align-items:center; gap:8px; font-size:12px;">
                            <button type="button" id="applicant-prev-btn" class="btn btn-xs btn-default" style="padding:2px 8px; font-size:11px;">
                                &laquo; Prev
                            </button>
                            <span id="applicant-page-info" style="font-weight:600; color:#475569;">Page 1 of 1</span>
                            <button type="button" id="applicant-next-btn" class="btn btn-xs btn-default" style="padding:2px 8px; font-size:11px;">
                                Next &raquo;
                            </button>
                        </div>
                    </div>
                    <div style="border:1px solid #d1d8dd; border-radius:8px; overflow:hidden; background:#ffffff;">
                        <table class="table table-bordered table-hover" style="margin:0; font-size:13px; width:100%;">
                            <thead style="background:#f8fafc;">
                                <tr>
                                    <th style="width:40px; text-align:center; vertical-align:middle; padding:8px 4px;"></th>
                                    <th style="width:60px; text-align:center; color:#3b82f6; vertical-align:middle; padding:8px 4px; font-weight:600;">No.</th>
                                    <th style="width:25%; color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Applicant ID</th>
                                    <th style="width:35%; color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Candidate Name</th>
                                    <th style="color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Programme</th>
                                </tr>
                                <tr style="background:#f1f5f9;">
                                    <th style="padding:4px 6px; text-align:center;"></th>
                                    <th style="padding:4px 6px; text-align:center;"></th>
                                    <th style="padding:4px 6px;">
                                        <input type="text" id="filter-applicant-id" placeholder="${__("Filter ID...")}" value="${applicant_filters.applicant_id}"
                                               style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; font-weight:normal; outline:none; background:#ffffff; box-shadow:inset 0 1px 2px rgba(0,0,0,0.03);">
                                    </th>
                                    <th style="padding:4px 6px;">
                                        <input type="text" id="filter-candidate-name" placeholder="${__("Filter Name...")}" value="${applicant_filters.candidate_name}"
                                               style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; font-weight:normal; outline:none; background:#ffffff; box-shadow:inset 0 1px 2px rgba(0,0,0,0.03);">
                                    </th>
                                    <th style="padding:4px 6px;">
                                        <input type="text" id="filter-programme" placeholder="${__("Filter Programme...")}" value="${applicant_filters.programme}"
                                               style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; font-weight:normal; outline:none; background:#ffffff; box-shadow:inset 0 1px 2px rgba(0,0,0,0.03);">
                                    </th>
                                </tr>
                            </thead>
                            <tbody id="reschedule-applicant-table-body"></tbody>
                        </table>
                    </div>`;

                d.get_field('applicants_html').$wrapper.html(html);
                render_applicant_page();
            }
        });
    }

    fetch_absent_applicants();
}

// Re-render provider list filtered by campus (no extra API call needed)
function _filter_providers_by_campus(d, all_providers) {
    const campus = d.get_value('campus');
    const filtered = campus ? all_providers.filter(p => p.campus === campus) : all_providers;
    d.get_field('providers_html').$wrapper.html(_build_provider_html(filtered));
    d.$wrapper.off('change.prov').on('change.prov', '.provider-checkbox', function () {
        const n = d.$wrapper.find('.provider-checkbox:checked').length;
        d.$wrapper.find('#provider-sel-count').text(`${n} provider(s) selected`);
    });
}

// ──────────────────────────────────────────────────────────────────────────────
//  Reject and Allocate Centre Dialog
// ──────────────────────────────────────────────────────────────────────────────
function open_reject_and_allocate_dialog(listview) {
    frappe.call({
        method: "slcm.admission.doctype.entrance_test_list.entrance_test_list.get_providers_with_capacity",
        args: {
            city: "",
            campus: "",
            programme: ""
        },
        callback: function (r) {
            const all_providers = r.message || [];
            if (!all_providers.length) {
                frappe.msgprint({ title: __('No Available Providers'), message: __('No active Entrance Test Providers found.'), indicator: 'orange' });
                return;
            }
            _show_reject_and_allocate_dialog(listview, all_providers);
        }
    });
}

function _show_reject_and_allocate_dialog(listview, initial_providers) {
    let all_providers = initial_providers;
    let applicants = [];
    const selected_applicant_names = new Set();
    const selected_provider_names = new Set();

    let search_center_query = "";
    let center_pwd_only = false;
    let center_current_page = 1;
    const center_page_size = 9;

    let applicant_current_page = 1;
    const applicant_page_size = 10;
    let applicant_filters = { applicant_id: "", candidate_name: "", programme_level: "", programme: "", entrance_test_city: "", old_centre: "", pwd_only: false };

    function get_filtered_providers() {
        let list = all_providers;
        const selected_city = d ? d.get_value("entrance_test_city") : "";
        if (selected_city) {
            list = list.filter(p => p.city === selected_city);
        }
        if (center_pwd_only) {
            list = list.filter(p => p.pwd_accessible == 1 || p.pwd_accessible === "1");
        }
        if (!search_center_query) return list;
        const q = search_center_query.toLowerCase().trim();
        return list.filter(p => {
            const name = (p.center_name || p.name).toLowerCase();
            const addr = (p.center_address || "").toLowerCase();
            return name.includes(q) || addr.includes(q);
        });
    }

    function fetch_and_render_providers() {
        const city_name = d ? d.get_value("entrance_test_city") : "";
        const prog_name = d ? d.get_value("check_available_seats_by_programme") : "";

        frappe.call({
            method: "slcm.admission.doctype.entrance_test_list.entrance_test_list.get_providers_with_capacity",
            args: {
                city: city_name || "",
                campus: "",
                programme: prog_name || ""
            },
            callback: function (r) {
                all_providers = r.message || [];
                selected_provider_names.clear();
                center_current_page = 1;
                render_center_page();
                update_allocation_type_ui();
            }
        });
    }

    function render_center_page() {
        if (!d || !d.$wrapper) return;
        const filtered = get_filtered_providers();
        const total_pages = Math.ceil(filtered.length / center_page_size) || 1;
        if (center_current_page > total_pages) center_current_page = total_pages;
        if (center_current_page < 1) center_current_page = 1;

        const start = (center_current_page - 1) * center_page_size;
        const page_providers = filtered.slice(start, start + center_page_size);

        const $wrapper = d.$wrapper;

        if (!page_providers.length) {
            $wrapper.find("#provider-list").html(`
                <div style="grid-column: 1 / -1; padding:20px; text-align:center; color:#94a3b8; font-size:13px;">
                    No centres match your criteria.
                </div>
            `);
        } else {
            const html = page_providers.map(p => {
                const is_checked = selected_provider_names.has(p.name);
                const border_col = is_checked ? "#2da44e" : "#cbd5e1";
                const bg_col = is_checked ? "#f0fdf4" : "#ffffff";
                const box_shadow = is_checked ? "0 2px 6px rgba(45,164,78,0.15)" : "0 1px 2px rgba(0,0,0,0.04)";

                return `
                    <label class="provider-card" data-name="${p.name}"
                           style="display:flex; align-items:flex-start; gap:10px; padding:10px 12px;
                                  border:1.5px solid ${border_col}; border-radius:8px; cursor:pointer;
                                  background:${bg_col}; transition: all 0.15s ease; margin:0; box-shadow:${box_shadow};
                                  position:relative; min-height:64px; box-sizing:border-box;">
                        <input type="checkbox" class="provider-checkbox"
                               data-name="${p.name}"
                               ${is_checked ? 'checked' : ''}
                               style="width:16px; height:16px; cursor:pointer; margin-top:2px; flex-shrink:0;">
                        <span style="line-height:1.4; flex:1; overflow:hidden;">
                            <span style="display:block; font-weight:700; font-size:13px; color:#1e293b; text-overflow:ellipsis; overflow:hidden; white-space:nowrap;" title="${p.center_name || p.name}">
                                ${p.center_name || p.name}
                                ${(p.pwd_accessible == 1 || p.pwd_accessible === "1") ? `<span style="font-size:10px; background:#dbeafe; color:#1e40af; padding:1px 5px; border-radius:4px; margin-left:4px; font-weight:600;">♿ PWD</span>` : ''}
                            </span>
                            <div style="margin-top: 4px; margin-bottom: 2px;">
                                <span style="font-size:10px; background:${(p.available_capacity || 0) > 0 ? '#dcfce7' : '#fee2e2'}; color:${(p.available_capacity || 0) > 0 ? '#166534' : '#991b1b'}; padding:2px 6px; border-radius:4px; font-weight:600; display:inline-block;">Available Seats: ${p.available_capacity || 0}</span>
                            </div>
                            ${p.center_address
                        ? `<span style="display:block; font-size:11px; color:#64748b; margin-top:2px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;" title="${p.center_address}">
                                       ${p.center_address}
                                   </span>`
                        : `<span style="display:block; font-size:11px; color:#94a3b8; margin-top:2px; font-style:italic;">No address provided</span>`
                    }
                        </span>
                    </label>
                `;
            }).join("");
            $wrapper.find("#provider-list").html(html);
        }

        $wrapper.find("#center-page-info").text(`Page ${center_current_page} of ${total_pages}`);
        $wrapper.find("#center-prev-btn").prop("disabled", center_current_page <= 1);
        $wrapper.find("#center-next-btn").prop("disabled", center_current_page >= total_pages);

        update_center_counts();
    }

    function update_center_counts() {
        if (!d || !d.$wrapper) return;
        const sel_count = selected_provider_names.size;
        const total_count = all_providers.length;
        const filtered_count = get_filtered_providers().length;
        if (center_pwd_only || search_center_query || d.get_value("entrance_test_city")) {
            d.$wrapper.find("#provider-sel-count").text(`Centres: ${filtered_count} of ${total_count} | ${sel_count} selected`);
        } else {
            d.$wrapper.find("#provider-sel-count").text(`Total Centres: ${total_count} | ${sel_count} selected`);
        }
        const all_selected = filtered_count > 0 && sel_count === filtered_count;
        d.$wrapper.find("#center-select-all-chk").prop("checked", all_selected);
    }

    function get_filtered_applicants() {
        return applicants.filter(a => {
            const id_match = !applicant_filters.applicant_id || (a.applicant || "").toLowerCase().includes(applicant_filters.applicant_id);
            const name_match = !applicant_filters.candidate_name || (a.candidate_name || "").toLowerCase().includes(applicant_filters.candidate_name);
            const level_match = !applicant_filters.programme_level || (a.program_level || "").toLowerCase() === applicant_filters.programme_level;
            const prog_match = !applicant_filters.programme || (a.program || "").toLowerCase() === applicant_filters.programme;
            const city_match = !applicant_filters.entrance_test_city || (a.entrance_test_city || "").toLowerCase().includes(applicant_filters.entrance_test_city);
            const centre_match = !applicant_filters.old_centre || (a.center_name || "").toLowerCase().includes(applicant_filters.old_centre);
            let pwd_match = true;
            if (applicant_filters.pwd_only) {
                pwd_match = (a.pwd == 1 || (a.pwd || "").toString().toLowerCase() === "yes");
            }
            return id_match && name_match && level_match && prog_match && city_match && centre_match && pwd_match;
        });
    }

    function render_applicant_page() {
        if (!d || !d.$wrapper) return;
        const filtered = get_filtered_applicants();
        const total_pages = Math.ceil(filtered.length / applicant_page_size) || 1;
        if (applicant_current_page > total_pages) applicant_current_page = total_pages;
        if (applicant_current_page < 1) applicant_current_page = 1;

        const start = (applicant_current_page - 1) * applicant_page_size;
        const page_applicants = filtered.slice(start, start + applicant_page_size);

        if (!page_applicants.length) {
            d.$wrapper.find("#rej-applicant-table-body").html(`<tr><td colspan="6" style="text-align:center; padding:25px; color:#94a3b8; font-size:13px;">No applicants match the filter criteria.</td></tr>`);
        } else {
            const rows_html = page_applicants.map((row, p_idx) => {
                const global_idx = start + p_idx + 1;
                const is_checked = selected_applicant_names.has(row.name);
                return `
                    <tr data-name="${row.name}">
                        <td style="text-align:center; width:40px; vertical-align:middle;">
                            <input type="checkbox" class="applicant-checkbox" data-name="${row.name}" ${is_checked ? 'checked' : ''}>
                        </td>
                        <td style="text-align:center; width:60px; color:#64748b; font-size:12px; vertical-align:middle;">${global_idx}</td>
                        <td style="vertical-align:middle;">${row.applicant || "-"}</td>
                        <td style="vertical-align:middle;">
                            <b>${row.candidate_name || "Unknown"}</b>
                            ${(row.pwd == 1 || (row.pwd || "").toString().toLowerCase() === "yes") ? `<span style="font-size:10px; background:#fef3c7; color:#92400e; padding:1px 5px; border-radius:4px; margin-left:4px; border:1px solid #fde68a; font-weight:700;">♿ PWD</span>` : ''}
                        </td>
                        <td style="vertical-align:middle;">${row.program_level || "-"}</td>
                        <td style="vertical-align:middle;">${row.program || "-"}</td>
                        <td style="vertical-align:middle;">${row.entrance_test_city || "-"}</td>
                        <td style="vertical-align:middle;">${row.center_name || "-"}</td>
                    </tr>
                `;
            }).join("");
            d.$wrapper.find("#rej-applicant-table-body").html(rows_html);
        }
        d.$wrapper.find("#applicant-page-info").text(`Page ${applicant_current_page} of ${total_pages}`);
        d.$wrapper.find("#applicant-prev-btn").prop("disabled", applicant_current_page <= 1);
        d.$wrapper.find("#applicant-next-btn").prop("disabled", applicant_current_page >= total_pages);
        update_applicant_counts(filtered.length);
    }

    function update_applicant_counts(filtered_length) {
        if (!d || !d.$wrapper) return;
        const sel_count = selected_applicant_names.size;
        const total_count = applicants.length;
        if (filtered_length !== undefined && filtered_length !== total_count) {
            d.$wrapper.find("#sel-count").text(`${sel_count} of ${total_count} selected (Filtered: ${filtered_length})`);
        } else {
            d.$wrapper.find("#sel-count").text(`${sel_count} of ${total_count} selected`);
        }
        const all_selected = total_count > 0 && sel_count === total_count;
        d.$wrapper.find("#select-all-chk").prop("checked", all_selected);
    }

    function update_allocation_type_ui() {
        if (!d || !d.$wrapper) return;
        const alloc_type = d.get_value("allocation_type");
        if (alloc_type === "Allocate Directly") {
            if (selected_provider_names.size > 1) {
                const first = Array.from(selected_provider_names)[0];
                selected_provider_names.clear();
                selected_provider_names.add(first);
            }
            d.$wrapper.find("#center-select-all-chk").prop("disabled", true).prop("checked", false);
            d.$wrapper.find("#center-select-all-chk").closest("label").css("opacity", "0.4").css("pointer-events", "none");
            d.$wrapper.find("#center-pwd-filter-chk").prop("disabled", false);
            d.$wrapper.find("#center-search-input").prop("disabled", false);
            d.$wrapper.find(".provider-checkbox").prop("disabled", false);
        } else {
            d.$wrapper.find("#center-select-all-chk").prop("disabled", false);
            d.$wrapper.find("#center-select-all-chk").closest("label").css("opacity", "1.0").css("pointer-events", "auto");
        }
        render_center_page();
    }

    let d = new frappe.ui.Dialog({
        title: __('Reject and Allocate Centre'),
        size: 'extra-large',
        fields: [
            { fieldtype: 'Section Break', label: __('Filters & Allocation Settings') },
            {
                label: __('Allocation Status'),
                fieldname: 'filter_allocation_status',
                fieldtype: 'Select',
                options: '\nNot Allocated\nPreferences Assigned\nAllocated\nReallocated\nCancelled\nRejected',
                onchange: () => fetch_applicants()
            },
            {
                label: __("Allocate Type"),
                fieldname: "allocation_type",
                fieldtype: "Select",
                options: ["Allocate Directly", "Allow Applicant Selection"],
                default: "Allocate Directly",
                reqd: 1,
                onchange: function () {
                    update_allocation_type_ui();
                }
            },
            {
                label: __("Send Email"),
                fieldname: "send_email",
                fieldtype: "Check",
                default: 1
            },
            { fieldtype: 'Column Break' },
            {
                label: __("Entrance Test City"),
                fieldname: "entrance_test_city",
                fieldtype: "Link",
                options: "Entrance Test City",
                onchange: function () {
                    fetch_and_render_providers();
                }
            },
            {
                label: __("Check Available Seats By Programme"),
                fieldname: "check_available_seats_by_programme",
                fieldtype: "Link",
                options: "Programme",
                onchange: function () {
                    fetch_and_render_providers();
                }
            },
            { fieldtype: "Section Break" },
            {
                fieldtype: "HTML",
                fieldname: "provider_section_label",
                options: `
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;">
                        <div style="font-weight:600; font-size:13px; color:#333;">
                            ${__("Select Entrance Test Centres")}
                            <span style="font-weight:400; font-size:11px; color:#888; margin-left:8px;">
                                — Select one or more centres as preferences for applicants
                            </span>
                        </div>
                        <div style="position:relative; width:240px;">
                            <input type="text" id="center-search-input" placeholder="${__("🔍 Search Centre")}" 
                                   style="width:100%; padding:6px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px; outline:none; background:#ffffff; transition:border 0.15s;">
                        </div>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; background:#f1f5f9; padding:6px 12px; border-radius:6px; font-size:12px;">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <label style="margin:0; font-weight:600; cursor:pointer; display:flex; align-items:center; color:#334155;">
                                <input type="checkbox" id="center-select-all-chk" style="width:15px; height:15px; cursor:pointer; margin-right:6px;">
                                Select All Centres
                            </label>
                            <label style="margin:0; font-weight:600; cursor:pointer; display:flex; align-items:center; color:#334155; margin-left:12px;" title="Filter PWD Accessible Centres">
                                <input type="checkbox" id="center-pwd-filter-chk" style="width:15px; height:15px; cursor:pointer; margin-right:6px;">
                                ♿ PWD
                            </label>
                            <button type="button" id="center-clear-all-btn" class="btn btn-xs btn-default" style="font-size:11px; padding:2px 8px; border-radius:4px;">
                                Clear All
                            </button>
                        </div>
                        <div id="provider-sel-count" style="color:#475569; font-weight:600; font-size:12px;">
                            Total Centres: ${all_providers.length} | 0 selected
                        </div>
                    </div>
                `
            },
            {
                fieldtype: "HTML",
                fieldname: "provider_checkboxes",
                options: `
                    <div id="provider-list" style="display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:10px; min-height:150px; padding:6px; border:1px solid #e2e8f0; border-radius:8px; background:#f8fafc;">
                    </div>
                    <div style="display:flex; justify-content:flex-end; align-items:center; margin-top:8px;">
                        <div id="center-pagination" style="display:flex; align-items:center; gap:8px; font-size:12px;">
                            <button type="button" id="center-prev-btn" class="btn btn-xs btn-default" style="padding:2px 8px; font-size:11px;">
                                &laquo; Prev
                            </button>
                            <span id="center-page-info" style="font-weight:600; color:#475569;">Page 1 of 1</span>
                            <button type="button" id="center-next-btn" class="btn btn-xs btn-default" style="padding:2px 8px; font-size:11px;">
                                Next &raquo;
                            </button>
                        </div>
                    </div>
                `
            },
            { fieldtype: 'Section Break', label: __('Select Applicants') },
            {
                label: __("Auto-select (Enter Number)"),
                fieldname: "auto_select_count",
                fieldtype: "Int",
                description: __("Enter count to automatically select first N unallocated applicants")
            },
            { fieldtype: "Section Break" },
            { fieldtype: 'HTML', fieldname: 'applicants_html' }
        ],
        primary_action_label: __('Reject and Allocate'),
        primary_action(values) {
            const filtered_applicant_names = new Set(get_filtered_applicants().map(a => a.name));
            const selected_applicants = Array.from(selected_applicant_names).filter(name => filtered_applicant_names.has(name));
            const selected_providers_array = Array.from(selected_provider_names);

            if (!selected_applicants.length) {
                frappe.msgprint(__('Please select at least one applicant from the current filter.'));
                return;
            }
            if (values.allocation_type === "Allocate Directly" && !selected_providers_array.length) {
                frappe.msgprint(__('Please select at least one provider (test centre).'));
                return;
            }

            if (values.allocation_type === "Allocate Directly" && selected_providers_array.length > 1) {
                frappe.msgprint(__("For 'Allocate Directly', please select only one Entrance Test Centre."));
                return;
            }

            if (values.allocation_type === "Allocate Directly" && selected_providers_array.length) {
                const selected_provider = all_providers.find(p => p.name === selected_providers_array[0]);
                if (selected_provider) {
                    const same_centre_applicants = applicants.filter(a =>
                        selected_applicant_names.has(a.name) && a.center_name === selected_provider.center_name
                    );
                    if (same_centre_applicants.length > 0) {
                        frappe.show_alert({
                            message: __('Cannot allocate to the same centre again for some applicants (e.g., {0}).', [same_centre_applicants[0].candidate_name]),
                            indicator: 'orange'
                        });
                        return;
                    }
                }
            }

            frappe.call({
                method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.check_reallocation_seat_availability",
                args: {
                    selected_applicants: selected_applicants,
                    providers: selected_providers_array,
                    allocation_type: values.allocation_type
                },
                freeze: true,
                freeze_message: __("Analyzing Allocation Scenario..."),
                callback: function (r) {
                    if (!r.exc && r.message) {
                        const send_email = values.send_email ? 1 : 0;
                        _show_reallocation_confirmation(d, listview, r.message, selected_providers_array, selected_applicants, values.allocation_type, send_email);
                    }
                }
            });
        }
    });

    d.show();

    // Initial render for providers
    render_center_page();

    // Provider events
    d.$wrapper.on("input", "#center-search-input", function () {
        search_center_query = $(this).val();
        center_current_page = 1;
        render_center_page();
    });

    d.$wrapper.on("change", "#center-pwd-filter-chk", function () {
        center_pwd_only = this.checked;
        center_current_page = 1;
        render_center_page();
    });

    d.$wrapper.on("click", "#center-clear-all-btn", function () {
        selected_provider_names.clear();
        render_center_page();
    });

    d.$wrapper.on("click", "#center-prev-btn", function () {
        if (center_current_page > 1) {
            center_current_page--;
            render_center_page();
        }
    });

    d.$wrapper.on("click", "#center-next-btn", function () {
        const filtered = get_filtered_providers();
        const total_pages = Math.ceil(filtered.length / center_page_size) || 1;
        if (center_current_page < total_pages) {
            center_current_page++;
            render_center_page();
        }
    });

    d.$wrapper.on("change", ".provider-checkbox", function () {
        const name = $(this).data("name");
        const alloc_type = d.get_value("allocation_type");

        if (alloc_type === "Allocate Directly") {
            if (this.checked) {
                selected_provider_names.clear();
                selected_provider_names.add(name);
            } else {
                selected_provider_names.delete(name);
            }
        } else {
            if (this.checked) {
                selected_provider_names.add(name);
            } else {
                selected_provider_names.delete(name);
            }
        }
        render_center_page(); // re-render to update selected styling
    });

    d.$wrapper.on("change", "#center-select-all-chk", function () {
        const filtered = get_filtered_providers();
        if (this.checked) {
            filtered.forEach(p => selected_provider_names.add(p.name));
        } else {
            filtered.forEach(p => selected_provider_names.delete(p.name));
        }
        render_center_page();
    });


    // Applicant Events
    d.$wrapper.on("input", "#filter-applicant-id", function () { applicant_filters.applicant_id = $(this).val().toLowerCase().trim(); applicant_current_page = 1; render_applicant_page(); });
    d.$wrapper.on("input", "#filter-candidate-name", function () { applicant_filters.candidate_name = $(this).val().toLowerCase().trim(); applicant_current_page = 1; render_applicant_page(); });
    d.$wrapper.on("input change", "#filter-programme-level", function () { applicant_filters.programme_level = $(this).val().toLowerCase().trim(); applicant_current_page = 1; render_applicant_page(); });
    d.$wrapper.on("input change", "#filter-programme", function () { applicant_filters.programme = $(this).val().toLowerCase().trim(); applicant_current_page = 1; render_applicant_page(); });
    d.$wrapper.on("input", "#filter-entrance-test-city", function () { applicant_filters.entrance_test_city = $(this).val().toLowerCase().trim(); applicant_current_page = 1; render_applicant_page(); });
    d.$wrapper.on("input", "#filter-old-centre", function () { applicant_filters.old_centre = $(this).val().toLowerCase().trim(); applicant_current_page = 1; render_applicant_page(); });
    d.$wrapper.on("change", "#pwd-applicant-filter-chk", function () { applicant_filters.pwd_only = this.checked; applicant_current_page = 1; render_applicant_page(); });
    d.$wrapper.on("click", "#applicant-clear-all-btn", function () { selected_applicant_names.clear(); render_applicant_page(); });
    d.$wrapper.on("click", "#applicant-prev-btn", function () { if (applicant_current_page > 1) { applicant_current_page--; render_applicant_page(); } });
    d.$wrapper.on("click", "#applicant-next-btn", function () { const filtered = get_filtered_applicants(); const total_pages = Math.ceil(filtered.length / applicant_page_size) || 1; if (applicant_current_page < total_pages) { applicant_current_page++; render_applicant_page(); } });
    d.$wrapper.on("change", ".applicant-checkbox", function () { const name = $(this).data("name"); if (this.checked) selected_applicant_names.add(name); else selected_applicant_names.delete(name); update_applicant_counts(get_filtered_applicants().length); });
    d.$wrapper.on("change", "#select-all-chk", function () { const filtered = get_filtered_applicants(); if (this.checked) filtered.forEach(a => selected_applicant_names.add(a.name)); else filtered.forEach(a => selected_applicant_names.delete(a.name)); render_applicant_page(); });

    // Handle auto select count
    d.fields_dict.auto_select_count.df.onchange = function () {
        const count = d.get_value("auto_select_count") || 0;
        const filtered = get_filtered_applicants();
        selected_applicant_names.clear();
        for (let i = 0; i < Math.min(count, filtered.length); i++) {
            selected_applicant_names.add(filtered[i].name);
        }
        render_applicant_page();
    };

    function fetch_applicants() {
        const filters = {};
        if (d.get_value('filter_allocation_status')) filters.allocation_status = d.get_value('filter_allocation_status');
        if (d.get_value('filter_entrance_test_status')) filters.entrance_test_status = d.get_value('filter_entrance_test_status');

        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Entrance Test Seat Allocation',
                filters: filters,
                fields: ['name', 'candidate_name', 'applicant', 'program_level', 'program', 'pwd', 'center_name', 'entrance_test_list.entrance_test_city'],
                limit_page_length: 0
            },
            callback: function (r) {
                applicants = r.message || [];
                selected_applicant_names.clear();
                applicant_current_page = 1;

                const unique_programme_levels = [...new Set(applicants.map(a => a.program_level).filter(Boolean))].sort();
                const unique_programmes = [...new Set(applicants.map(a => a.program).filter(Boolean))].sort();

                const prog_level_options = `<option value="">${__("All Levels")}</option>` +
                    unique_programme_levels.map(l => `<option value="${l}" ${applicant_filters.programme_level === l.toLowerCase().trim() ? 'selected' : ''}>${l}</option>`).join("");

                const prog_options = `<option value="">${__("All Programmes")}</option>` +
                    unique_programmes.map(p => `<option value="${p}" ${applicant_filters.programme === p.toLowerCase().trim() ? 'selected' : ''}>${p}</option>`).join("");

                let html = `
                    <div style="margin-bottom:10px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                        <div style="display:flex; gap:12px; align-items:center;">
                            <label style="font-weight:600; cursor:pointer; margin:0; display:flex; align-items:center; font-size:13px;">
                                <input type="checkbox" id="select-all-chk" style="width:15px; height:15px; cursor:pointer; margin-right:6px;">
                                Select All Applicants
                            </label>
                            <label style="font-weight:600; cursor:pointer; margin:0; display:flex; align-items:center; font-size:13px; margin-left:12px;">
                                <input type="checkbox" id="pwd-applicant-filter-chk" style="width:15px; height:15px; cursor:pointer; margin-right:6px;" ${applicant_filters.pwd_only ? 'checked' : ''}>
                                ♿ PWD
                            </label>
                            <button type="button" id="applicant-clear-all-btn" class="btn btn-xs btn-default" style="font-size:11px; padding:2px 8px; border-radius:4px;">Clear All</button>
                            <span id="sel-count" style="color:#6c757d; font-size:12px; font-weight:500;">0 of ${applicants.length} selected</span>
                        </div>
                        <div id="applicant-pagination" style="display:flex; align-items:center; gap:8px; font-size:12px;">
                            <button type="button" id="applicant-prev-btn" class="btn btn-xs btn-default" style="padding:2px 8px; font-size:11px;">&laquo; Prev</button>
                            <span id="applicant-page-info" style="font-weight:600; color:#475569;">Page 1 of 1</span>
                            <button type="button" id="applicant-next-btn" class="btn btn-xs btn-default" style="padding:2px 8px; font-size:11px;">Next &raquo;</button>
                        </div>
                    </div>
                    <div style="border:1px solid #d1d8dd; border-radius:8px; overflow:hidden; background:#ffffff;">
                        <table class="table table-bordered table-hover" style="margin:0; font-size:13px; width:100%;">
                            <thead style="background:#f8fafc;">
                                <tr>
                                    <th style="width:40px; text-align:center; vertical-align:middle; padding:8px 4px;"></th>
                                    <th style="width:60px; text-align:center; color:#3b82f6; vertical-align:middle; padding:8px 4px; font-weight:600;">No.</th>
                                    <th style="width:20%; color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Applicant ID</th>
                                    <th style="width:25%; color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Candidate Name</th>
                                    <th style="color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Programme Level</th>
                                    <th style="color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Programme</th>
                                    <th style="color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Entrance Test City</th>
                                    <th style="color:#3b82f6; vertical-align:middle; padding:8px 10px; font-weight:600;">Old Centre Name</th>
                                </tr>
                                <tr style="background:#f1f5f9;">
                                    <th style="padding:4px 6px; text-align:center;"></th>
                                    <th style="padding:4px 6px; text-align:center;"></th>
                                    <th style="padding:4px 6px;">
                                        <input type="text" id="filter-applicant-id" placeholder="${__("Filter ID...")}" value="${applicant_filters.applicant_id}"
                                               style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; outline:none; background:#ffffff;">
                                    </th>
                                    <th style="padding:4px 6px;">
                                        <input type="text" id="filter-candidate-name" placeholder="${__("Filter Name...")}" value="${applicant_filters.candidate_name}"
                                               style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; outline:none; background:#ffffff;">
                                    </th>
                                    <th style="padding:4px 6px;">
                                        <select id="filter-programme-level" style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; outline:none; background:#ffffff;">
                                            ${prog_level_options}
                                        </select>
                                    </th>
                                    <th style="padding:4px 6px;">
                                        <select id="filter-programme" style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; outline:none; background:#ffffff;">
                                            ${prog_options}
                                        </select>
                                    </th>
                                    <th style="padding:4px 6px;">
                                        <input type="text" id="filter-entrance-test-city" placeholder="${__("Filter City...")}" value="${applicant_filters.entrance_test_city || ''}"
                                               style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; outline:none; background:#ffffff;">
                                    </th>
                                    <th style="padding:4px 6px;">
                                        <input type="text" id="filter-old-centre" placeholder="${__("Filter Old Centre...")}" value="${applicant_filters.old_centre || ''}"
                                               style="width:100%; border:1px solid #cbd5e1; border-radius:14px; padding:3px 10px; font-size:11px; outline:none; background:#ffffff;">
                                    </th>
                                </tr>
                            </thead>
                            <tbody id="rej-applicant-table-body"></tbody>
                        </table>
                    </div>`;

                d.get_field('applicants_html').$wrapper.html(html);
                render_applicant_page();
            }
        });
    }

    fetch_applicants();
}


function _show_reallocation_confirmation(parent_dialog, listview, result, selected_providers, selected_applicants, allocation_type, send_email) {
    const total = result.total_selected || 0;
    const total_avail = result.effective_total_available != null ? result.effective_total_available : (result.total_available_seats || 0);
    const breakdown = result.programme_breakdown || [];
    const centres = result.centre_details || [];
    const has_shortage = result.has_programme_shortage || false;
    const overall_sufficient = result.overall_sufficient || false;
    const total_pwd = result.total_pwd || 0;
    const has_pwd_centre = result.has_pwd_centre || false;
    const pwd_conflict = result.pwd_conflict || false;
    const pwd_applicants = result.pwd_applicants || [];
    const is_direct = allocation_type === "Allocate Directly";

    // Build the summary header
    const has_issues = !overall_sufficient || pwd_conflict;
    const overall_color = has_issues ? "#dc2626" : "#16a34a";
    const overall_bg = has_issues ? "#fef2f2" : "#f0fdf4";
    const overall_border = has_issues ? "#fecaca" : "#bbf7d0";
    const status_msg = !overall_sufficient ? 'Seat Shortage Detected' : pwd_conflict ? 'PWD Accessibility Conflict Detected' : 'Seats Available — Ready to Allocate';

    let pwd_summary = '';
    if (total_pwd > 0) {
        pwd_summary = `
                <div>
                    <span style="font-weight:600;">♿ PWD Applicants:</span>
                    <span style="font-weight:700; color:${pwd_conflict ? '#dc2626' : '#0f766e'}; font-size:14px; margin-left:4px;">${total_pwd}</span>
                    ${pwd_conflict ? '<span style="font-size:11px; background:#fee2e2; color:#991b1b; padding:2px 6px; border-radius:4px; margin-left:6px; font-weight:600;">No PWD Centre Selected!</span>' : ''}
                </div>`;
    }

    // For "Allocate Directly" show the actual centre name; for multi-centre show count
    let centre_info_html = '';
    let avail_label = '';
    if (is_direct && centres.length === 1) {
        const c = centres[0];
        const pwd_tag = c.pwd_accessible ? '<span style="font-size:9px; background:#dbeafe; color:#1e40af; padding:1px 5px; border-radius:3px; margin-left:4px; font-weight:600;">♿ PWD</span>' : '';
        centre_info_html = `
                <div>
                    <span style="font-weight:600;">Selected Centre:</span>
                    <span style="font-weight:700; color:#6d28d9; font-size:13px; margin-left:4px;">${c.center_name}</span>${pwd_tag}
                </div>`;
        avail_label = `Available Seats at ${c.center_name}:`;
    } else {
        centre_info_html = `
                <div>
                    <span style="font-weight:600;">Centres Selected:</span>
                    <span style="font-weight:700; color:#6d28d9; font-size:14px; margin-left:4px;">${centres.length}</span>
                </div>`;
        avail_label = `Total Available Seats (All Centres):`;
    }

    let summary_html = `
        <div style="background:${overall_bg}; border:1.5px solid ${overall_border}; border-radius:10px; padding:14px 18px; margin-bottom:16px;">
            <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                <span style="font-size:15px; font-weight:700; color:${overall_color};">
                    ${status_msg}
                </span>
                <span style="font-size:11px; background:#e0e7ff; color:#3730a3; padding:2px 8px; border-radius:4px; font-weight:600; margin-left:auto;">
                    ${is_direct ? 'Allocate Directly' : 'Allow Applicant Selection'}
                </span>
            </div>
            <div style="display:flex; gap:24px; flex-wrap:wrap; font-size:13px; color:#334155;">
                <div>
                    <span style="font-weight:600;">Total Applicants Selected:</span>
                    <span style="font-weight:700; color:#1e40af; font-size:14px; margin-left:4px;">${total}</span>
                </div>
                <div>
                    <span style="font-weight:600;">${avail_label}</span>
                    <span style="font-weight:700; color:${total_avail >= total ? '#16a34a' : '#dc2626'}; font-size:14px; margin-left:4px;">${total_avail}</span>
                </div>
                ${centre_info_html}
                ${pwd_summary}
            </div>
        </div>
    `;

    // Build programme-wise breakdown table
    let programme_rows = "";
    breakdown.forEach(prog => {
        const status_bg = prog.sufficient ? "#dcfce7" : "#fee2e2";
        const status_color = prog.sufficient ? "#166534" : "#991b1b";
        const status_text = prog.sufficient ? "Sufficient" : `Shortage: ${prog.shortage}`;

        // Build centre-wise availability cells
        let centre_cells = "";
        centres.forEach(cd => {
            const prog_cd = (prog.centre_details || []).find(c => c.center_name === cd.center_name);
            if (prog_cd) {
                const avail_color = prog_cd.available > 0 ? "#16a34a" : "#dc2626";
                centre_cells += `
                    <td class="centre-cell-click" data-center-id="${cd.provider}" style="text-align:center; padding:8px 10px; border-bottom:1px solid #e2e8f0; font-size:12px; vertical-align:middle; cursor:pointer;" title="Click to view centre details">
                        <span style="font-weight:700; color:${avail_color};">${prog_cd.available}</span>
                        <span style="color:#94a3b8; font-size:10px;"> / ${prog_cd.capacity}</span>
                    </td>
                `;
            } else {
                centre_cells += `
                    <td class="centre-cell-click" data-center-id="${cd.provider}" style="text-align:center; padding:8px 10px; border-bottom:1px solid #e2e8f0; font-size:12px; color:#94a3b8; vertical-align:middle; cursor:pointer;" title="Click to view centre details">
                        —
                    </td>
                `;
            }
        });

        programme_rows += `
            <tr>
                <td style="padding:8px 12px; font-weight:600; color:#1e293b; border-bottom:1px solid #e2e8f0; font-size:13px; vertical-align:middle; white-space:nowrap;">
                    ${prog.programme}
                    ${(prog.pwd_count || 0) > 0 ? `<span style="font-size:10px; background:#fef3c7; color:#92400e; padding:1px 5px; border-radius:4px; margin-left:4px; border:1px solid #fde68a; font-weight:700;">♿ ${prog.pwd_count} PWD</span>` : ''}
                </td>
                <td style="text-align:center; padding:8px 10px; font-weight:700; color:#1e40af; border-bottom:1px solid #e2e8f0; font-size:14px; vertical-align:middle;">
                    ${prog.applicant_count}
                </td>
                ${centre_cells}
                <td style="text-align:center; padding:8px 10px; font-weight:700; color:#0f766e; border-bottom:1px solid #e2e8f0; font-size:13px; vertical-align:middle;">
                    ${prog.total_available}
                </td>
                <td style="text-align:center; padding:6px 10px; border-bottom:1px solid #e2e8f0; vertical-align:middle;">
                    <span style="display:inline-block; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:700; background:${status_bg}; color:${status_color};">
                        ${status_text}
                    </span>
                </td>
            </tr>
        `;
    });

    // Centre column headers
    let centre_headers = "";
    centres.forEach(cd => {
        const pwd_badge = cd.pwd_accessible ? `<span style="font-size:9px; background:#dbeafe; color:#1e40af; padding:1px 4px; border-radius:3px; margin-left:3px;">♿</span>` : "";
        const name = cd.center_name.length > 18 ? cd.center_name.substring(0, 18) + "…" : cd.center_name;
        centre_headers += `
            <th class="centre-cell-click" data-center-id="${cd.provider}" style="text-align:center; padding:10px 8px; font-weight:600; color:#475569; font-size:11px; border-bottom:2px solid #cbd5e1; white-space:nowrap; vertical-align:middle; cursor:pointer;" title="Click to view ${cd.center_name} details">
                ${name}${pwd_badge}
                <div style="font-size:10px; color:#94a3b8; font-weight:400; margin-top:2px;">
                    Avail / Total
                </div>
            </th>
        `;
    });

    let table_html = `
        <div style="margin-bottom:12px;">
            <div style="font-weight:700; font-size:14px; color:#1e293b; margin-bottom:10px; display:flex; align-items:center; gap:6px;">
                Programme-wise Allocation Breakdown
            </div>
            <div style="border:1px solid #e2e8f0; border-radius:10px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.06);">
                <div style="overflow-x:auto;">
                    <table style="width:100%; border-collapse:collapse; font-size:13px; min-width:600px;">
                        <thead>
                            <tr style="background:linear-gradient(135deg, #f8fafc, #f1f5f9);">
                                <th style="text-align:left; padding:10px 12px; font-weight:700; color:#1e293b; font-size:12px; border-bottom:2px solid #cbd5e1; vertical-align:middle;">
                                    Programme
                                </th>
                                <th style="text-align:center; padding:10px 8px; font-weight:700; color:#1e40af; font-size:12px; border-bottom:2px solid #cbd5e1; white-space:nowrap; vertical-align:middle;">
                                    Applicants
                                </th>
                                ${centre_headers}
                                <th style="text-align:center; padding:10px 8px; font-weight:700; color:#0f766e; font-size:12px; border-bottom:2px solid #cbd5e1; white-space:nowrap; vertical-align:middle;">
                                    Total Avail
                                </th>
                                <th style="text-align:center; padding:10px 8px; font-weight:700; color:#475569; font-size:12px; border-bottom:2px solid #cbd5e1; vertical-align:middle;">
                                    Status
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            ${programme_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;

    let centre_summary_html = `
        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px 14px; margin-top:4px;">
            <div style="font-weight:600; font-size:12px; color:#475569; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center;">
                <span>Centre Summary</span>
                <span class="show-all-centres" style="display:none; color:#2563eb; cursor:pointer; font-size:11px; font-weight:700; text-decoration:underline;">Show All Centres</span>
            </div>
            <div style="display:flex; gap:10px; flex-wrap:wrap;">
    `;
    centres.forEach(cd => {
        const avail_pct = cd.total_capacity > 0 ? Math.round((cd.available_capacity / cd.total_capacity) * 100) : 0;
        const bar_color = avail_pct > 50 ? "#22c55e" : avail_pct > 20 ? "#eab308" : "#ef4444";

        let prog_details_html = '';
        if (cd.programme_capacities && Object.keys(cd.programme_capacities).length > 0) {
            prog_details_html = `<div style="margin-top:8px; border-top:1px dashed #e2e8f0; padding-top:6px;">`;
            for (const [prog_name, caps] of Object.entries(cd.programme_capacities)) {
                prog_details_html += `
                    <div style="display:flex; justify-content:space-between; font-size:10px; color:#475569; margin-bottom:3px;">
                        <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:75%;" title="${prog_name}">${prog_name}</span>
                        <span style="font-weight:600;"><span style="color:${caps.available > 0 ? '#16a34a' : '#dc2626'};">${caps.available}</span> <span style="color:#94a3b8; font-weight:400;">/ ${caps.capacity}</span></span>
                    </div>
                `;
            }
            prog_details_html += `</div>`;
        }

        centre_summary_html += `
            <div class="centre-summary-card" data-center-id="${cd.provider}" style="background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:8px 12px; min-width:180px; flex:1;">
                <div style="font-weight:600; font-size:12px; color:#1e293b; margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${cd.center_name}">
                    ${cd.center_name}
                    ${cd.pwd_accessible ? '<span style="font-size:9px; background:#dbeafe; color:#1e40af; padding:1px 4px; border-radius:3px; margin-left:3px;">♿ PWD</span>' : '<span style="font-size:9px; background:#fee2e2; color:#991b1b; padding:1px 4px; border-radius:3px; margin-left:3px;">No PWD</span>'}
                </div>
                <div style="display:flex; justify-content:space-between; font-size:11px; color:#64748b; margin-bottom:3px;">
                    <span>Overall Avail: <b style="color:${bar_color};">${cd.available_capacity}</b></span>
                    <span>Total: <b>${cd.total_capacity}</b></span>
                </div>
                <div style="height:5px; background:#e2e8f0; border-radius:3px; overflow:hidden;">
                    <div style="height:100%; width:${avail_pct}%; background:${bar_color}; border-radius:3px; transition:width 0.3s;"></div>
                </div>
                ${prog_details_html}
            </div>
        `;
    });
    centre_summary_html += `</div></div>`;

    // Warning notes
    let warning_html = "";
    if (has_shortage) {
        const shortage_msg = is_direct
            ? 'Some programmes have more applicants than available seats. These applicants <b>will not be allocated</b> and will appear in the unallocated list.'
            : 'Some programmes have more applicants than available seats. Applicants will still be assigned preferences, but they may not find available seats when they choose their preferred centre.';
        warning_html += `
            <div style="background:#fef3c7; border:1px solid #fde68a; border-radius:8px; padding:10px 14px; margin-top:10px; font-size:12px; color:#92400e;">
                <b>Seat Shortage:</b> ${shortage_msg}
            </div>
        `;
    }
    if (pwd_conflict) {
        let pwd_list_html = pwd_applicants.map(p => `<li><b>${p.name}</b> (${p.applicant_id}) — ${p.programme}</li>`).join('');
        warning_html += `
            <div style="background:#fee2e2; border:1px solid #fecaca; border-radius:8px; padding:10px 14px; margin-top:10px; font-size:12px; color:#991b1b;">
                <b>♿ PWD Conflict:</b> The following <b>${total_pwd}</b> PWD applicant(s) are selected but <b>none of the chosen centres</b> have PWD accessibility:
                <ul style="margin:6px 0 0 16px; padding:0; list-style-type:disc;">${pwd_list_html}</ul>
                ${is_direct ? '<div style="margin-top:6px; font-weight:700;">These applicants will NOT be allocated and will appear as unallocated.</div>' : '<div style="margin-top:6px; font-weight:700;">These applicants will still receive preferences but may face accessibility issues.</div>'}
            </div>
        `;
    } else if (total_pwd > 0 && has_pwd_centre) {
        warning_html += `
            <div style="background:#dcfce7; border:1px solid #bbf7d0; border-radius:8px; padding:10px 14px; margin-top:10px; font-size:12px; color:#166534;">
                <b>♿ PWD Status:</b> ${total_pwd} PWD applicant(s) found. PWD-accessible centre(s) are available among the selected centres.
            </div>
        `;
    }

    const dialog_title = is_direct ? __("Confirm Re-allocation — Allocate Directly") : __("Confirm Re-allocation — Allow Applicant Selection");
    const btn_label = is_direct ? __("Confirm & Re-allocate") : __("Allocate Centre");

    const confirm_dialog = new frappe.ui.Dialog({
        title: dialog_title,
        size: "extra-large",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "confirmation_content",
                options: `
                    <div style="font-family:inherit;">
                        ${summary_html}
                        ${table_html}
                        ${centre_summary_html}
                        ${warning_html}
                    </div>
                `
            }
        ],
        primary_action_label: btn_label,
        primary_action: function () {
            confirm_dialog.hide();

            const total_count = selected_applicants.length;
            window.etl_allocation_done = false;
            window.etl_allocation_parent_dialog = parent_dialog;

            if (!etl_allocation_progress_dialog) {
                etl_allocation_progress_dialog = new frappe.ui.Dialog({
                    title: __("Allocating Seats in Background..."),
                    fields: [
                        {
                            fieldtype: "HTML",
                            fieldname: "progress_html",
                            options: `
                                <div style="padding: 10px 5px; font-family: inherit;">
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                        <div id="etg-current-applicant" style="font-weight:600; font-size:13px; color:#1e293b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:75%;">
                                            Initializing seat allocation...
                                        </div>
                                        <div id="etg-progress-percent" style="font-weight:700; font-size:14px; color:#2563eb;">
                                            0%
                                        </div>
                                    </div>
                                    <div style="height:10px; background:#e2e8f0; border-radius:6px; overflow:hidden; margin-bottom:12px; position:relative;">
                                        <div id="etg-progress-bar" style="height:100%; width:0%; background:linear-gradient(90deg, #3b82f6, #10b981); border-radius:6px; transition: width 0.2s ease;"></div>
                                    </div>
                                    <div style="display:flex; justify-content:space-between; align-items:center; font-size:11.5px; color:#64748b;">
                                        <span id="etg-counter-text">Processing 0 of ${total_count}</span>
                                    </div>
                                </div>
                            `
                        }
                    ]
                });
                etl_allocation_progress_dialog.no_cancel();
            }

            etl_allocation_progress_dialog.$wrapper.find("#etg-progress-bar").css("width", `0%`);
            etl_allocation_progress_dialog.$wrapper.find("#etg-progress-percent").text(`0%`);
            etl_allocation_progress_dialog.$wrapper.find("#etg-current-applicant").html("Initializing seat allocation...");
            etl_allocation_progress_dialog.$wrapper.find("#etg-counter-text").text(`Processing 0 of ${total_count}`);

            etl_allocation_progress_dialog.show();

            frappe.call({
                method: 'slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.reject_and_allocate_applicants',
                args: {
                    applicants: selected_applicants,
                    providers: selected_providers,
                    allocation_type: allocation_type,
                    send_email: send_email
                },
                timeout: 18000000,
                callback: function (r) {
                    frappe.realtime.off("entrance_test_seat_allocation_progress");
                    if (window.etl_allocation_done) return;
                    window.etl_allocation_done = true;

                    if (etl_allocation_progress_dialog) {
                        etl_allocation_progress_dialog.hide();
                    }

                    if (!r.exc) {
                        let count = r.message || 0;
                        window.show_etl_allocation_success_toast(count, []);

                        if (parent_dialog) {
                            parent_dialog.hide();
                        }
                        listview.refresh();
                    }
                }
            });
        },
        secondary_action_label: __("Cancel"),
        secondary_action: function () {
            confirm_dialog.hide();
        }
    });

    confirm_dialog.$wrapper.find(".modal-dialog").css("max-width", "900px");
    confirm_dialog.show();

    setTimeout(() => {
        const $wrapper = confirm_dialog.$wrapper;

        $wrapper.find(".centre-cell-click").on("click", function () {
            const provider = $(this).attr("data-center-id");
            if (!provider) return;

            $wrapper.find(".centre-cell-click").css("background", "transparent");
            $(this).css("background", "#fef9c3").delay(500).queue(function (next) {
                $(this).css("background", "transparent");
                next();
            });

            $wrapper.find(".centre-summary-card").hide();
            $wrapper.find(`.centre-summary-card[data-center-id="${provider}"]`).show();

            $wrapper.find(".show-all-centres").show();
        });

        $wrapper.find(".show-all-centres").on("click", function () {
            $wrapper.find(".centre-summary-card").show();
            $(this).hide();
        });

        $wrapper.find(".centre-cell-click").hover(
            function () { $(this).css("background-color", "#f1f5f9"); },
            function () { $(this).css("background-color", "transparent"); }
        );
    }, 100);
}

/**
 * Fetch and render the unpublished applicants table for the Publish dialog
 */
function update_unpublished_applicants_table(pd, is_page_change = false) {
    const html_field = pd.get_field("unpublished_applicants_html");
    if (!html_field) return;

    if (!is_page_change) {
        pd.unpublished_state.page = 1;
        // Keep selected_names when filters change so user doesn't lose selections
    }

    let args = {
        academic_year: pd.get_value("academic_year") || "",
        admission_cycle: pd.get_value("admission_cycle") || "",
        program_level: pd.get_value("program_level") || "",
        applicant_type: pd.get_value("applicant_type") || "Domestic Applicants",
        program: pd.get_value("program") || "",
        filter_applicant: pd.unpublished_state.filter_applicant || "",
        filter_candidate_name: pd.unpublished_state.filter_candidate_name || "",
        filter_entrance_test_status: pd.unpublished_state.filter_entrance_test_status || "",
        filter_status: pd.unpublished_state.filter_status || "",
        filter_admission_status: pd.unpublished_state.filter_admission_status || "",
        filter_program: pd.unpublished_state.filter_program || "",
        limit_start: (pd.unpublished_state.page - 1) * pd.unpublished_state.limit,
        limit_page_length: pd.unpublished_state.limit
    };

    html_field.$wrapper.html(`<div class="text-muted"><i class="fa fa-spinner fa-spin"></i> ${__('Loading applicants...')}</div>`);

    frappe.call({
        method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.get_unpublished_applicants_for_dialog",
        args: args,
        callback: function (r) {
            if (r && r.message) {
                render_unpublished_applicants_table(pd, html_field, r.message.records, r.message.total_count, r.message.unique_programs);
            }
        }
    });
}

function render_unpublished_applicants_table(pd, html_field, records, total_count, unique_programs) {
    let state = pd.unpublished_state;
    let total_pages = Math.ceil(total_count / state.limit) || 1;
    let all_page_selected = records.length > 0 && records.every(r => state.selected_names.includes(r.name));

    let html = `
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-size: 13px;">
            <div style="display: flex; align-items: center; gap: 15px;">
                <label style="margin: 0; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 6px;">
                    <input type="checkbox" class="unpub-select-all" ${all_page_selected ? 'checked' : ''}> Select All Applicants
                </label>
                <button class="btn btn-xs btn-default unpub-clear-all">Clear All</button>
                <span class="text-muted"><span class="unpub-selected-count">${state.selected_names.length}</span> of ${total_count} selected</span>
            </div>
            <div>
                <button class="btn btn-xs btn-default unpub-prev" ${state.page <= 1 ? 'disabled' : ''}>« Prev</button>
                <span style="margin: 0 10px; font-weight: 500;">Page ${state.page} of ${total_pages}</span>
                <button class="btn btn-xs btn-default unpub-next" ${state.page >= total_pages ? 'disabled' : ''}>Next »</button>
            </div>
        </div>

        <div style="border: 1px solid #d1d8dd; border-radius: 4px; overflow: hidden; overflow-x: auto;">
            <table class="table table-bordered table-hover" style="margin-bottom: 0; font-size: 12px; white-space: nowrap;">
                <thead style="background-color: #f8f9fa;">
                    <tr>
                        <th style="width: 40px; text-align: center; vertical-align: middle;">
                            
                        </th>
                        <th style="width: 40px; text-align: center; vertical-align: middle;">No.</th>
                        <th>
                            <div style="color: #2b6cb0; margin-bottom: 5px;">${__('Applicant ID')}</div>
                            <input type="text" class="form-control input-xs unpub-filter" data-filter="filter_applicant" placeholder="Filter ID..." value="${state.filter_applicant || ''}">
                        </th>
                        <th>
                            <div style="color: #2b6cb0; margin-bottom: 5px;">${__('Candidate Name')}</div>
                            <input type="text" class="form-control input-xs unpub-filter" data-filter="filter_candidate_name" placeholder="Filter Name..." value="${state.filter_candidate_name || ''}">
                        </th>
                        <th>
                            <div style="color: #2b6cb0; margin-bottom: 5px;">${__('Programme')}</div>
                            <select class="form-control input-xs unpub-filter" data-filter="filter_program">
                                <option value=""></option>
                                ${unique_programs ? unique_programs.map(p => `<option value="${p}" ${state.filter_program === p ? 'selected' : ''}>${p}</option>`).join('') : ''}
                            </select>
                        </th>
                        <th>
                            <div style="color: #2b6cb0; margin-bottom: 5px;">${__('Entrance Test Status')}</div>
                            <select class="form-control input-xs unpub-filter" data-filter="filter_entrance_test_status">
                                <option value=""></option>
                                <option value="Scheduled" ${state.filter_entrance_test_status === 'Scheduled' ? 'selected' : ''}>Scheduled</option>
                                <option value="Attended" ${state.filter_entrance_test_status === 'Attended' ? 'selected' : ''}>Attended</option>
                                <option value="Absent" ${state.filter_entrance_test_status === 'Absent' ? 'selected' : ''}>Absent</option>
                                <option value="Rescheduled" ${state.filter_entrance_test_status === 'Rescheduled' ? 'selected' : ''}>Rescheduled</option>
                            </select>
                        </th>
                        <th>
                            <div style="color: #2b6cb0; margin-bottom: 5px;">${__('Status')}</div>
                            <select class="form-control input-xs unpub-filter" data-filter="filter_status">
                                <option value=""></option>
                                <option value="Pass" ${state.filter_status === 'Pass' ? 'selected' : ''}>Pass</option>
                                <option value="Fail" ${state.filter_status === 'Fail' ? 'selected' : ''}>Fail</option>
                            </select>
                        </th>
                        <th>
                            <div style="color: #2b6cb0; margin-bottom: 5px;">${__('Admission Status')}</div>
                            <select class="form-control input-xs unpub-filter" data-filter="filter_admission_status">
                                <option value=""></option>
                                <option value="Provisionally Offered Admission" ${state.filter_admission_status === 'Provisionally Offered Admission' ? 'selected' : ''}>Provisionally Offered Admission</option>
                                <option value="Waitlisted" ${state.filter_admission_status === 'Waitlisted' ? 'selected' : ''}>Waitlisted</option>
                            </select>
                        </th>
                    </tr>
                </thead>
                <tbody>
    `;

    if (records.length === 0) {
        html += `<tr><td colspan="8" class="text-center text-muted" style="padding: 15px;">${__('No unpublished applicants found matching filters.')}</td></tr>`;
    } else {
        records.forEach((r, idx) => {
            let row_no = ((state.page - 1) * state.limit) + idx + 1;
            let checked = state.selected_names.includes(r.name) ? 'checked' : '';
            html += `
                <tr>
                    <td style="text-align: center;">
                        <input type="checkbox" class="unpub-select-row" data-name="${r.name}" ${checked}>
                    </td>
                    <td style="text-align: center; color: #2b6cb0;">${row_no}</td>
                    <td>${r.applicant || ''}</td>
                    <td style="font-weight: 600;">${r.candidate_name || ''}</td>
                    <td>${r.program || ''}</td>
                    <td>${r.entrance_test_status || ''}</td>
                    <td>${r.result_status || ''}</td>
                    <td>${r.admission_status || ''}</td>
                </tr>
            `;
        });
    }

    html += `
                </tbody>
            </table>
        </div>
    `;

    html_field.$wrapper.html(html);

    // Event listeners
    let timeout = null;
    html_field.$wrapper.find('.unpub-filter').on('input change', function () {
        let filter_name = $(this).attr('data-filter');
        let val = $(this).val();
        state[filter_name] = val;

        clearTimeout(timeout);
        timeout = setTimeout(() => {
            update_unpublished_applicants_table(pd, false);
        }, 500);
    });

    html_field.$wrapper.find('.unpub-clear-all').on('click', function () {
        state.selected_names = [];
        html_field.$wrapper.find('.unpub-select-row').prop('checked', false);
        html_field.$wrapper.find('.unpub-select-all').prop('checked', false);
        html_field.$wrapper.find('.unpub-selected-count').text(0);
    });

    html_field.$wrapper.find('.unpub-select-all').on('change', function () {
        let is_checked = $(this).is(':checked');

        if (!is_checked) {
            state.selected_names = [];
            html_field.$wrapper.find('.unpub-select-row').prop('checked', false);
            html_field.$wrapper.find('.unpub-selected-count').text(0);
        } else {
            html_field.$wrapper.find('.unpub-select-row').prop('checked', true);
            let btn = $(this);
            btn.prop('disabled', true);

            frappe.call({
                method: "slcm.admission.doctype.entrance_test_seat_allocation.entrance_test_seat_allocation.get_unpublished_applicants_for_dialog",
                args: {
                    academic_year: pd.get_value("academic_year") || "",
                    admission_cycle: pd.get_value("admission_cycle") || "",
                    program_level: pd.get_value("program_level") || "",
                    applicant_type: pd.get_value("applicant_type") || "Domestic Applicants",
                    program: pd.get_value("program") || "",
                    filter_applicant: pd.unpublished_state.filter_applicant || "",
                    filter_candidate_name: pd.unpublished_state.filter_candidate_name || "",
                    filter_entrance_test_status: pd.unpublished_state.filter_entrance_test_status || "",
                    filter_status: pd.unpublished_state.filter_status || "",
                    filter_admission_status: pd.unpublished_state.filter_admission_status || "",
                    filter_program: pd.unpublished_state.filter_program || "",
                    fetch_all_names: 1
                },
                callback: function (r) {
                    btn.prop('disabled', false);
                    if (r && r.message) {
                        state.selected_names = r.message;
                        html_field.$wrapper.find('.unpub-selected-count').text(state.selected_names.length);
                    }
                }
            });
        }
    });

    html_field.$wrapper.find('.unpub-select-row').on('change', function () {
        let name = $(this).attr('data-name');
        if ($(this).is(':checked')) {
            if (!state.selected_names.includes(name)) state.selected_names.push(name);
        } else {
            state.selected_names = state.selected_names.filter(n => n !== name);
        }

        html_field.$wrapper.find('.unpub-selected-count').text(state.selected_names.length);

        let all_checked = html_field.$wrapper.find('.unpub-select-row:not(:checked)').length === 0;
        html_field.$wrapper.find('.unpub-select-all').prop('checked', all_checked && records.length > 0);
    });

    html_field.$wrapper.find('.unpub-prev').on('click', function () {
        if (state.page > 1) {
            state.page--;
            update_unpublished_applicants_table(pd, true);
        }
    });

    html_field.$wrapper.find('.unpub-next').on('click', function () {
        if (state.page < total_pages) {
            state.page++;
            update_unpublished_applicants_table(pd, true);
        }
    });
}
