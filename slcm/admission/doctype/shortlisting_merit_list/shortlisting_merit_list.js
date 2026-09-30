frappe.ui.form.on("Shortlisting Merit List", {
    refresh(frm) {
        if (!frm.is_new()) {
            if (frm.doc.status === "In Progress") {
                start_shortlist_progress_polling(frm);
            }

            frm.add_custom_button(__("Generate Final Admission Merit"), function () {
                frappe.confirm(__("Are you sure you want to generate the Final Merit List?<br><br><span class='text-muted' style='font-size: 13px;'>This action will evaluate all shortlisted candidates by combining Part A and Part B scores to generate the final admission rank list.</span>"), function () {
                    frm.call({
                        method: "clear_generation_progress",
                        args: { docname: frm.doc.name },
                        callback: function () {
                            frappe.show_progress(__("Generating Final Merit List"), 0, 100, __("Starting Final Merit List generation..."));
                            start_shortlist_progress_polling(frm);

                            frm.call({
                                method: "generate_final_merit_list",
                                args: { docname: frm.doc.name },
                                callback: function (r) {
                                    if (frm._progress_interval) {
                                        clearInterval(frm._progress_interval);
                                        frm._progress_interval = null;
                                    }

                                    frappe.hide_progress();
                                    if (r.message) {
                                        frappe.show_alert({
                                            message: __("Final Merit List generated successfully."),
                                            indicator: "green"
                                        });
                                    }
                                },
                                error: function () {
                                    if (frm._progress_interval) {
                                        clearInterval(frm._progress_interval);
                                        frm._progress_interval = null;
                                    }
                                    frappe.hide_progress();
                                }
                            });
                        }
                    });
                });
            }, __("Actions"));

            frm.add_custom_button(__("Download Merit List"), function () {
                let d = new frappe.ui.Dialog({
                    title: __('Download Shortlisting Merit List'),
                    fields: [
                        {
                            label: __('Download Type'),
                            fieldname: 'download_type',
                            fieldtype: 'Select',
                            options: [
                                { label: __('Overall Master List'), value: 'Overall' },
                                { label: __('Category Wise'), value: 'Category Wise' }
                            ],
                            default: 'Overall',
                            reqd: 1
                        },
                        {
                            label: __('Specific Category'),
                            fieldname: 'category',
                            fieldtype: 'Select',
                            options: [
                                { label: __('All Categories'), value: 'All' },
                                { label: __('General List'), value: 'General' },
                                { label: __('SC List'), value: 'SC' },
                                { label: __('ST List'), value: 'ST' },
                                { label: __('OBC List'), value: 'OBC' },
                                { label: __('EWS List'), value: 'EWS' },
                                { label: __('Karnataka Students'), value: 'Karnataka' },
                                { label: __('Women Merit List'), value: 'Women' },
                                { label: __('PWD Merit List'), value: 'PWD' }
                            ],
                            depends_on: "eval:doc.download_type == 'Category Wise'",
                            default: 'All'
                        }
                    ],
                    primary_action_label: __('Download'),
                    primary_action(values) {
                        let url = frappe.urllib.get_full_url(
                            "/api/method/slcm.admission.doctype.shortlisting_merit_list.shortlisting_merit_list.download_merit_list?" +
                            "name=" + encodeURIComponent(frm.doc.name) +
                            "&download_type=" + encodeURIComponent(values.download_type) +
                            "&category=" + encodeURIComponent(values.category || "")
                        );
                        window.open(url, '_blank');
                        d.hide();
                    }
                });
                d.show();
            }, __("Actions"));
        }
    },
    onload(frm) {
        frm.set_query("program", function () {
            let filters = {};
            if (frm.doc.program_level) {
                filters["level_of_study"] = frm.doc.program_level;
            }
            return { filters: filters };
        });
    },
    program_level(frm) {
        frm.set_query("program", function () {
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
    }
});

function start_shortlist_progress_polling(frm) {
    if (frm._progress_interval) {
        clearInterval(frm._progress_interval);
    }

    frm._progress_interval = setInterval(() => {
        frappe.call({
            method: "slcm.admission.doctype.shortlisting_merit_list.shortlisting_merit_list.get_generation_progress",
            args: {
                docname: frm.doc.name
            },
            callback: (res) => {
                let data = res.message;
                if (data) {
                    let percent = Math.round(data.percent || 0);
                    let desc = data.description || __("Processing applicants...");
                    if (data.status === "In Progress") {
                        frappe.show_progress(__("Generating Final Merit List"), percent, 100, desc);
                    } else if (data.status === "Completed") {
                        if (frm._progress_interval) {
                            clearInterval(frm._progress_interval);
                            frm._progress_interval = null;
                        }
                        frappe.hide_progress();
                    } else if (data.status === "Failed") {
                        if (frm._progress_interval) {
                            clearInterval(frm._progress_interval);
                            frm._progress_interval = null;
                        }
                        frappe.hide_progress();
                    }
                }
            }
        });
    }, 500);
}
