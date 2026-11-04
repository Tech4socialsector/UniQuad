
console.debug('Interview Seat Allocation list view script loaded');

frappe.listview_settings['Interview Seat Allocation'] = {
    refresh: function (listview) {
        // log roles so we can debug why buttons may be hidden
        const is_applicant = frappe.user_roles.includes("Applicant");
        const is_admin = frappe.user_roles.includes("Administrator") || frappe.user_roles.includes("System Manager");
        console.debug('Interview Seat Allocation refresh – roles:', frappe.user_roles,
            'is_applicant=', is_applicant, 'is_admin=', is_admin);

        // show buttons for anyone who is not a pure applicant or when the user is an admin
        if (!is_applicant || is_admin) {
            if (!listview.page.wrapper.find('.btn-publish-seat-allocations').length) {
                const button = listview.page.add_inner_button(__('Publish Seat Allocations'), () => {
                    open_publish_seat_allocations_dialog(listview);
                }, __('Actions'));
                button.addClass('btn-publish-seat-allocations');
            }

            // Bulk Publish Results button
            if (!listview.page.wrapper.find('.btn-bulk-publish').length) {
                const pbbtn = listview.page.add_inner_button(__('Bulk Publish Results'), function () {
                    try {
                        open_bulk_publish_dialog(listview);
                    } catch (e) {
                        console.error('Bulk Publish dialog error', e);
                        frappe.msgprint({ title: __('Error'), message: __('Unable to open Bulk Publish dialog.'), indicator: 'red' });
                    }
                }, __("Actions"));
                pbbtn.addClass('btn-bulk-publish');
            }

            // Generate Offer Letters button (only once)
            if (!listview.page.wrapper.find('.btn-generate-offers').length) {
                const obtn = listview.page.add_inner_button(__('Generate Offer Letters'), function () {
                    try {
                        open_generate_offer_dialog(listview);
                    } catch (e) {
                        console.error('Generate Offer dialog error', e);
                        frappe.msgprint({ title: __('Error'), message: __('Unable to open Generate Offer dialog.'), indicator: 'red' });
                    }
                }, __("Actions"));
                obtn.addClass('btn-generate-offers');
            }

            // Reschedule button (also only once)
            if (!listview.page.wrapper.find('.btn-reschedule').length) {
                const rbtn = listview.page.add_inner_button(__('Reschedule'), function () {
                    try {
                        open_reschedule_dialog(listview);
                    } catch (e) {
                        console.error('Reschedule dialog error', e);
                        frappe.msgprint({ title: __('Error'), message: __('Unable to open Reschedule dialog. See browser console for details.'), indicator: 'red' });
                    }
                }, __("Actions"));
                rbtn.addClass('btn-reschedule');
            }
        }
    }
};


function open_publish_seat_allocations_dialog(listview) {
    const dialog = new frappe.ui.Dialog({
        title: __('Publish Interview Seat Allocations'),
        size: 'extra-large',
        fields: [
            { fieldtype: 'HTML', fieldname: 'allocations_html' },
            { fieldtype: 'Section Break', label: __('Email Settings') },
            { label: __('Send Email Notification'), fieldname: 'send_email', fieldtype: 'Check', default: 1 },
            { fieldtype: 'Column Break' },
            { label: __('Email Format'), fieldname: 'email_format', fieldtype: 'Select', options: 'Default\nCustom', default: 'Default' },
            { fieldtype: 'Section Break' },
            { label: __('Custom Email Content'), fieldname: 'custom_email_content', fieldtype: 'Text Editor', depends_on: 'eval:doc.email_format=="Custom"' },
        ],
        primary_action_label: __('Publish Allocations'),
        primary_action(values) {
            const records = dialog.$wrapper.find('input[name="publish_allocation"]:checked').map(function () { return this.value; }).get();
            if (!records.length) {
                frappe.msgprint(__('Select at least one applicant.'));
                return;
            }
            frappe.call({
                method: 'slcm.admission.doctype.interview_seat_allocation.interview_seat_allocation.publish_seat_allocations',
                args: { records, send_email: values.send_email, email_format: values.email_format, custom_email_content: values.custom_email_content },
                freeze: true,
                freeze_message: __('Publishing seat allocations…'),
                callback: (r) => {
                    dialog.hide();
                    frappe.show_alert({ message: __('Published {0} allocation(s).', [r.message.published]), indicator: 'green' });
                    listview.refresh();
                },
            });
        },
    });
    frappe.call({
        method: 'slcm.admission.doctype.interview_seat_allocation.interview_seat_allocation.get_unpublished_seat_allocations',
        callback: (r) => {
            const rows = r.message || [];
            const content = rows.length ? `<table class="table table-bordered"><thead><tr><th></th><th>${__('Applicant')}</th><th>${__('Name')}</th><th>${__('Programme')}</th><th>${__('Date')}</th></tr></thead><tbody>${rows.map(row => `<tr><td><input type="checkbox" name="publish_allocation" value="${frappe.utils.escape_html(row.name)}"></td><td>${frappe.utils.escape_html(row.applicant || '')}</td><td>${frappe.utils.escape_html(row.candidate_name || '')}</td><td>${frappe.utils.escape_html(row.program || '')}</td><td>${frappe.datetime.str_to_user(row.interview_date || '')}</td></tr>`).join('')}</tbody></table>` : `<p class="text-muted">${__('No unpublished scheduled seat allocations found.')}</p>`;
            dialog.fields_dict.allocations_html.$wrapper.html(content);
        },
    });
    dialog.show();
}


// -----------------------------------------------------------------------------
//  Interview rescheduling dialog
// -----------------------------------------------------------------------------
function open_reschedule_dialog(listview) {
    console.debug('Opening reschedule dialog');
    let d = new frappe.ui.Dialog({
        title: __('Reschedule Interview'),
        size: 'extra-large',
        fields: [
            { fieldtype: 'Section Break', label: __('Filters') },
            {
                label: __('Program Level'),
                fieldname: 'program_level',
                fieldtype: 'Select',
                options: 'Undergraduate\nPostgraduate\nResearch Course',
                on_change: () => fetch_absent_applicants(d)
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Academic Year'),
                fieldname: 'academic_year',
                fieldtype: 'Link',
                options: 'Academic Year',
                on_change: () => fetch_absent_applicants(d)
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Campus'),
                fieldname: 'campus',
                fieldtype: 'Link',
                options: 'Campus',
                on_change: () => fetch_absent_applicants(d)
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Admission Cycle'),
                fieldname: 'admission_cycle',
                fieldtype: 'Link',
                options: 'Admission Cycle',
                on_change: () => fetch_absent_applicants(d)
            },

            { fieldtype: 'Section Break', label: __('Reschedule Settings') },
            {
                label: __('New Interview Date'),
                fieldname: 'interview_date',
                fieldtype: 'Datetime',
                reqd: 1,
                description: __('Must be today or a future date/time')
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Interview Staff Member'),
                fieldname: 'interview_staff_member',
                fieldtype: 'Link',
                options: 'Interview Staff Member',
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

            { fieldtype: 'Section Break', label: __('Select Absent Applicants') },
            {
                fieldtype: 'HTML',
                fieldname: 'applicants_html'
            }
        ],
        primary_action_label: __('Reschedule'),
        primary_action(values) {
            const selected_applicants = [];
            d.$wrapper.find('.applicant-checkbox:checked').each(function () {
                selected_applicants.push($(this).data('name'));
            });

            if (!selected_applicants.length) {
                frappe.msgprint({ message: __('Please select at least one applicant.'), indicator: 'orange' });
                return;
            }

            frappe.call({
                method: 'slcm.admission.doctype.interview_seat_allocation.interview_seat_allocation.reschedule_applicants',
                args: {
                    applicants: selected_applicants,
                    interview_staff: values.interview_staff_member,
                    interview_date: values.interview_date,
                    interview_time: values.interview_date ? frappe.datetime.get_time(values.interview_date) : null,
                    reschedule_reason: values.reschedule_reason
                },
                freeze: true,
                freeze_message: __('Rescheduling Applicants...'),
                callback: function (r) {
                    if (r.message !== undefined) {
                        frappe.msgprint(__('{0} record(s) updated.', [r.message]));
                    }
                    d.hide();
                    listview.refresh();
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
    fetch_absent_applicants(d);
}

function fetch_absent_applicants(d) {
    const filters = { interview_status: 'Absent', is_rescheduled: 0 };

    if (d.get_value('program_level')) filters.program_level = d.get_value('program_level');
    if (d.get_value('academic_year')) filters.academic_year = d.get_value('academic_year');
    if (d.get_value('campus')) filters.campus = d.get_value('campus');
    if (d.get_value('admission_cycle')) filters.admission_cycle = d.get_value('admission_cycle');

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Interview Seat Allocation',
            filters: filters,
            fields: ['name', 'candidate_name', 'applicant', 'program'],
            limit_page_length: 50
        },
        callback: function (r) {
            const applicants = r.message || [];
            let html = `
                <div style="margin-bottom:10px; display:flex; gap:12px; align-items:center;">
                    <label style="font-weight:600; cursor:pointer; margin:0; display:flex; align-items:center;">
                        <input type="checkbox" id="select-all-applicants">
                        <span style="margin-left:8px;">Select All</span>
                    </label>
                    <span id="selected-count" style="color:#6c757d; font-size:12px;">0 of ${applicants.length} selected</span>
                </div>
                <div style="max-height:250px; overflow-y:auto; border:1px solid #d1d8dd; border-radius:4px;">
                    <table class="table table-bordered table-hover" style="margin:0; font-size:13px;">
                        <thead style="position:sticky; top:0; background:#f4f5f6; z-index:1;">
                            <tr>
                                <th style="width:40px;"></th>
                                <th>Candidate Name</th>
                                <th>Applicant ID</th>
                                <th>Program</th>
                            </tr>
                        </thead>
                        <tbody>`;

            if (applicants.length) {
                applicants.forEach(app => {
                    html += `
                        <tr>
                            <td><input type="checkbox" class="applicant-checkbox" data-name="${app.name}"></td>
                            <td>${app.candidate_name || ''}</td>
                            <td>${app.applicant || ''}</td>
                            <td>${app.program || ''}</td>
                        </tr>`;
                });
            } else {
                html += `<tr><td colspan="5" class="text-muted">No applicants found.</td></tr>`;
            }

            html += '</tbody></table></div>';
            d.get_field('applicants_html').$wrapper.html(html);

            // Select All
            d.$wrapper.find('#select-all-applicants').on('change', function () {
                d.$wrapper.find('.applicant-checkbox').prop('checked', $(this).is(':checked'));
                update_selected_count(d, applicants.length);
            });

            // Individual
            d.$wrapper.on('change', '.applicant-checkbox', function () {
                update_selected_count(d, applicants.length);
            });

            update_selected_count(d, applicants.length);
        }
    });
}

function update_selected_count(d, total) {
    const n = d.$wrapper.find('.applicant-checkbox:checked').length;
    const t = total !== undefined ? total : d.$wrapper.find('.applicant-checkbox').length;
    d.$wrapper.find('#selected-count').text(`${n} of ${t} selected`);
    d.$wrapper.find('#select-all-applicants').prop('checked', t > 0 && n === t);
}

// -----------------------------------------------------------------------------
//  Generate Offer Letters dialog
// -----------------------------------------------------------------------------
function open_generate_offer_dialog(listview) {
    let d = new frappe.ui.Dialog({
        title: __('Generate Offer Letters'),
        size: 'extra-large',
        fields: [
            { fieldtype: 'Section Break', label: __('Filters') },
            {
                label: __('Programme Level'),
                fieldname: 'program_level',
                fieldtype: 'Select',
                options: 'Undergraduate\nPostgraduate\nResearch Course',
                on_change: () => fetch_pass_applicants(d)
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Academic Year'),
                fieldname: 'academic_year',
                fieldtype: 'Link',
                options: 'Academic Year',
                on_change: () => fetch_pass_applicants(d)
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Campus'),
                fieldname: 'campus',
                fieldtype: 'Link',
                options: 'Campus',
                on_change: () => fetch_pass_applicants(d)
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Admission Cycle'),
                fieldname: 'admission_cycle',
                fieldtype: 'Link',
                options: 'Admission Cycle',
                on_change: () => fetch_pass_applicants(d)
            },

            { fieldtype: 'Section Break', label: __('Select Passed Applicants') },
            {
                fieldtype: 'HTML',
                fieldname: 'applicants_html'
            }
        ],
        primary_action_label: __('Generate Offer Letters'),
        primary_action(values) {
            const selected_applicants = [];
            d.$wrapper.find('.applicant-checkbox:checked').each(function () {
                selected_applicants.push($(this).data('applicant'));
            });

            if (!selected_applicants.length) {
                frappe.msgprint({ message: __('Please select at least one applicant.'), indicator: 'orange' });
                return;
            }

            frappe.call({
                method: 'slcm.api.service.offer_service.bulk_generate_offers',
                args: {
                    applicants: selected_applicants
                },
                freeze: true,
                freeze_message: __('Generating Offer Letters...'),
                callback: function (r) {
                    if (r.message) {
                        if (r.message.queued) {
                            frappe.msgprint({
                                message: r.message.message,
                                indicator: 'blue'
                            });
                        } else {
                            let s_count = r.message.success ? r.message.success.length : 0;
                            let e_count = r.message.errors ? r.message.errors.length : 0;
                            
                            let message = `
                                <div style="padding: 10px;">
                                    <div style="display: flex; gap: 15px; margin-bottom: 20px;">
                                        <div style="flex: 1; padding: 12px; background: #f0fff4; border: 1px solid #c6f6d5; border-radius: 8px; text-align: center;">
                                            <h3 style="margin: 0; color: #2f855a;">${s_count}</h3>
                                            <div style="font-size: 11px; color: #38a169; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">${__('Successful')}</div>
                                        </div>
                                        <div style="flex: 1; padding: 12px; background: ${e_count > 0 ? '#fff5f5' : '#f7fafc'}; border: 1px solid ${e_count > 0 ? '#fed7d7' : '#edf2f7'}; border-radius: 8px; text-align: center;">
                                            <h3 style="margin: 0; color: ${e_count > 0 ? '#c53030' : '#718096'};">${e_count}</h3>
                                            <div style="font-size: 11px; color: ${e_count > 0 ? '#e53e3e' : '#a0aec0'}; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">${__('Failed')}</div>
                                        </div>
                                    </div>
                            `;

                            if (e_count > 0) {
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
                                                ${r.message.errors.map(item => `
                                                    <tr>
                                                        <td style="font-weight: 600;">${item.applicant || item.name}</td>
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
                                indicator: e_count === 0 ? 'green' : (s_count > 0 ? 'orange' : 'red'),
                                primary_action: {
                                    label: __('View Offer Letters'),
                                    action: () => frappe.set_route('List', 'Offer Letter')
                                }
                            });
                        }
                    }
                    d.hide();
                    listview.refresh();
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
    fetch_pass_applicants(d);
}

function fetch_pass_applicants(d) {
    const filters = { status: 'Selected' };

    if (d.get_value('program_level')) filters.program_level = d.get_value('program_level');
    if (d.get_value('academic_year')) filters.academic_year = d.get_value('academic_year');
    if (d.get_value('campus')) filters.campus = d.get_value('campus');
    if (d.get_value('admission_cycle')) filters.admission_cycle = d.get_value('admission_cycle');

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Interview Seat Allocation',
            filters: filters,
            fields: ['name', 'candidate_name', 'applicant', 'program', 'interview_result_status'],
            limit_page_length: 100
        },
        callback: function (r) {
            const applicants = r.message || [];
            let html = `
                <div style="margin-bottom:10px; display:flex; gap:12px; align-items:center;">
                    <label style="font-weight:600; cursor:pointer; margin:0; display:flex; align-items:center;">
                        <input type="checkbox" id="select-all-offer-applicants">
                        <span style="margin-left:8px;">Select All</span>
                    </label>
                    <span id="selected-offer-count" style="color:#6c757d; font-size:12px;">0 of ${applicants.length} selected</span>
                </div>
                <div style="max-height:250px; overflow-y:auto; border:1px solid #d1d8dd; border-radius:4px;">
                    <table class="table table-bordered table-hover" style="margin:0; font-size:13px;">
                        <thead style="position:sticky; top:0; background:#f4f5f6; z-index:1;">
                            <tr>
                                <th style="width:40px;"></th>
                                <th>Candidate Name</th>
                                <th>Applicant ID</th>
                                <th>Programme</th>
                                <th>Result</th>
                            </tr>
                        </thead>
                        <tbody>`;

            if (applicants.length) {
                applicants.forEach(app => {
                    html += `
                        <tr>
                            <td><input type="checkbox" class="applicant-checkbox" data-applicant="${app.applicant}" data-name="${app.name}"></td>
                            <td>${app.candidate_name || ''}</td>
                            <td>${app.applicant || ''}</td>
                            <td>${app.program || ''}</td>
                            <td><span class="badge badge-success">${app.interview_result_status}</span></td>
                        </tr>`;
                });
            } else {
                html += `<tr><td colspan="5" class="text-muted">No eligible applicants found.</td></tr>`;
            }

            html += '</tbody></table></div>';
            d.get_field('applicants_html').$wrapper.html(html);

            // Select All
            d.$wrapper.find('#select-all-offer-applicants').on('change', function () {
                d.$wrapper.find('.applicant-checkbox').prop('checked', $(this).is(':checked'));
                update_offer_selected_count(d, applicants.length);
            });

            // Individual
            d.$wrapper.on('change', '.applicant-checkbox', function () {
                update_offer_selected_count(d, applicants.length);
            });

            update_offer_selected_count(d, applicants.length);
        }
    });
}

function update_offer_selected_count(d, total) {
    const n = d.$wrapper.find('.applicant-checkbox:checked').length;
    const t = total !== undefined ? total : d.$wrapper.find('.applicant-checkbox').length;
    d.$wrapper.find('#selected-offer-count').text(`${n} of ${t} selected`);
    d.$wrapper.find('#select-all-offer-applicants').prop('checked', t > 0 && n === t);
}

function get_listview_filter_val(listview, fieldname) {
    let filter = listview.filter_area.filter_list.filters.find(f => f[1] === fieldname);
    return filter ? filter[3] : "";
}

function open_bulk_publish_dialog(listview) {
    const default_pl = get_listview_filter_val(listview, "program_level");
    const default_ay = get_listview_filter_val(listview, "academic_year");
    const default_program = get_listview_filter_val(listview, "program");
    const default_ac = get_listview_filter_val(listview, "admission_cycle");

    let d = new frappe.ui.Dialog({
        title: __('Bulk Publish Results'),
        size: 'extra-large',
        fields: [
            { fieldtype: 'Section Break', label: __('Filters') },
            {
                label: __('Programme Level'),
                fieldname: 'program_level',
                fieldtype: 'Select',
                options: 'Undergraduate\nPostgraduate\nResearch Course',
                default: default_pl,
                change() { 
                    update_dialog_applicant_count(d);
                    update_unpublished_interviews_table(d, false);
                }
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Academic Year'),
                fieldname: 'academic_year',
                fieldtype: 'Link',
                options: 'Academic Year',
                default: default_ay,
                change() { 
                    update_dialog_applicant_count(d);
                    update_unpublished_interviews_table(d, false);
                }
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Programme'),
                fieldname: 'program',
                fieldtype: 'Link',
                options: 'Programme',
                default: default_program,
                change() { 
                    update_dialog_applicant_count(d);
                    update_unpublished_interviews_table(d, false);
                }
            },
            { fieldtype: 'Column Break' },
            {
                label: __('Admission Cycle'),
                fieldname: 'admission_cycle',
                fieldtype: 'Link',
                options: 'Admission Cycle',
                default: default_ac,
                change() { 
                    update_dialog_applicant_count(d);
                    update_unpublished_interviews_table(d, false);
                }
            },
            { fieldtype: 'Section Break' },
            {
                fieldname: 'total_applicants_html',
                fieldtype: 'HTML'
            },
            { fieldtype: 'Section Break', label: __('Select Unpublished Results') },
            {
                fieldtype: 'HTML',
                fieldname: 'unpublished_interviews_html'
            },
            { fieldtype: "Section Break", label: __("Email Settings") },
            {
                label: __("Send Email"),
                fieldname: "send_email",
                fieldtype: "Check",
                default: 0,
                onchange: function() {
                    let is_send = d.get_value("send_email");
                    let format = d.get_value("email_format");
                    
                    if (d.fields_dict.email_format) {
                        d.fields_dict.email_format.$wrapper.toggle(!!is_send);
                    }
                    
                    if (d.fields_dict.custom_email_content) {
                        let show_editor = !!(is_send && format === "Custom");
                        d.fields_dict.custom_email_content.$wrapper.toggle(show_editor);
                        if (show_editor) {
                            setTimeout(() => d.fields_dict.custom_email_content.refresh(), 50);
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
                onchange: function() {
                    let is_send = d.get_value("send_email");
                    let format = d.get_value("email_format");
                    
                    if (d.fields_dict.custom_email_content) {
                        let show_editor = !!(is_send && format === "Custom");
                        d.fields_dict.custom_email_content.$wrapper.toggle(show_editor);
                        if (show_editor) {
                            setTimeout(() => d.fields_dict.custom_email_content.refresh(), 50);
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
        primary_action_label: __('Publish Results'),
        primary_action(values) {
            if (!d.unpublished_state.selected_names.length) {
                frappe.msgprint({ message: __('Please select at least one record to publish.'), indicator: 'orange' });
                return;
            }

            frappe.call({
                method: 'slcm.admission.doctype.interview_seat_allocation.interview_seat_allocation.bulk_publish_results',
                args: {
                    records: JSON.stringify(d.unpublished_state.selected_names),
                    send_email: values.send_email,
                    email_format: values.email_format,
                    custom_email_content: values.custom_email_content
                },
                freeze: true,
                freeze_message: __('Publishing Results...'),
                callback: function (r) {
                    if (r.message && r.message.success) {
                        frappe.msgprint({
                            message: __("{0} result(s) successfully published.", [r.message.count]),
                            indicator: 'green'
                        });
                        d.hide();
                        listview.refresh();
                    }
                }
            });
        }
    });

    d.unpublished_state = {
        page: 1,
        limit: 10,
        selected_names: []
    };

    d.show();

    if (d.fields_dict.email_format) d.fields_dict.email_format.$wrapper.hide();
    if (d.fields_dict.custom_email_content) d.fields_dict.custom_email_content.$wrapper.hide();

    d.set_query("admission_cycle", function () {
        return { filters: { "status": "Active" } };
    });

    ["program_level", "academic_year", "program", "admission_cycle"].forEach(fn => {
        if (d.fields_dict[fn] && d.fields_dict[fn].$input) {
            d.fields_dict[fn].$input.on("change blur input", () => {
                update_dialog_applicant_count(d);
                update_unpublished_interviews_table(d, false);
            });
        }
    });

    update_dialog_applicant_count(d);
    update_unpublished_interviews_table(d, false);
}

function update_dialog_applicant_count(d) {
    const html_field = d.get_field("total_applicants_html");
    if (!html_field) return;

    let args = {
        academic_year: d.get_value("academic_year") || "",
        admission_cycle: d.get_value("admission_cycle") || "",
        program_level: d.get_value("program_level") || "",
        program: d.get_value("program") || ""
    };

    frappe.call({
        method: "slcm.admission.doctype.interview_seat_allocation.interview_seat_allocation.get_interview_applicant_count",
        args: args,
        callback: function (r) {
            if (r.message) {
                let html = `
                    <div style="background-color: #f0f8ff; border: 1px solid #cce5ff; padding: 15px 20px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                        <div style="display: flex; flex-direction: column;">
                            <span style="font-size: 11px; font-weight: 700; color: #0056b3; text-transform: uppercase; letter-spacing: 0.5px;">${__('Total Applicants')}</span>
                            <span style="font-size: 24px; font-weight: 700; color: #004085; line-height: 1.2;">${r.message.total || 0}</span>
                        </div>
                        <div style="display: flex; gap: 10px;">
                            <div style="background-color: #ffffff; border: 1px solid #b8daff; padding: 5px 10px; border-radius: 4px; font-size: 11px; color: #004085; font-weight: 600; display: flex; align-items: center; gap: 5px;">
                                <span style="display: inline-block; width: 6px; height: 6px; background-color: #28a745; border-radius: 50%;"></span>
                                ${__('Attend: ')} <span style="font-size: 13px;">${r.message.completed || 0}</span>
                            </div>
                            <div style="background-color: #ffffff; border: 1px solid #b8daff; padding: 5px 10px; border-radius: 4px; font-size: 11px; color: #004085; font-weight: 600; display: flex; align-items: center; gap: 5px;">
                                <span style="display: inline-block; width: 6px; height: 6px; background-color: #dc3545; border-radius: 50%;"></span>
                                ${__('Absent: ')} <span style="font-size: 13px;">${r.message.absent || 0}</span>
                            </div>
                        </div>
                    </div>
                `;
                html_field.$wrapper.html(html);
            }
        }
    });
}

function update_unpublished_interviews_table(d, is_page_change = false) {
    const html_field = d.get_field("unpublished_interviews_html");
    if (!html_field) return;

    if (!is_page_change) {
        d.unpublished_state.page = 1;
    }

    let args = {
        academic_year: d.get_value("academic_year") || "",
        admission_cycle: d.get_value("admission_cycle") || "",
        program_level: d.get_value("program_level") || "",
        program: d.get_value("program") || "",
        filter_applicant: d.unpublished_state.filter_applicant || "",
        filter_candidate_name: d.unpublished_state.filter_candidate_name || "",
        filter_program: d.unpublished_state.filter_program || "",
        filter_result: d.unpublished_state.filter_result || "",
        filter_selection_status: d.unpublished_state.filter_selection_status || "",
        limit_start: (d.unpublished_state.page - 1) * d.unpublished_state.limit,
        limit_page_length: d.unpublished_state.limit
    };

    html_field.$wrapper.html(`<div class="text-muted"><i class="fa fa-spinner fa-spin"></i> ${__('Loading applicants...')}</div>`);

    frappe.call({
        method: "slcm.admission.doctype.interview_seat_allocation.interview_seat_allocation.get_unpublished_interviews_for_dialog",
        args: args,
        callback: function (r) {
            if (r && r.message) {
                render_unpublished_interviews_table(d, html_field, r.message.records, r.message.total_count);
            }
        }
    });
}

function render_unpublished_interviews_table(d, html_field, records, total_count) {
    let state = d.unpublished_state;
    let total_pages = Math.ceil(total_count / state.limit) || 1;

    let html = `
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-size: 13px;">
            <div style="display: flex; align-items: center; gap: 15px;">
                <label style="margin: 0; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 6px;">
                    <input type="checkbox" class="unpub-select-all" ${records.length > 0 && html_field.$wrapper.find('.unpub-select-row:not(:checked)').length === 0 ? 'checked' : ''}> Select All Applicants
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
                        <th style="width: 40px; text-align: center; vertical-align: middle;"></th>
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
                            <input type="text" class="form-control input-xs unpub-filter" data-filter="filter_program" placeholder="Filter Programme..." value="${state.filter_program || ''}">
                        </th>
                        <th>
                            <div style="color: #2b6cb0; margin-bottom: 5px;">${__('Selection Status')}</div>
                            <select class="form-control input-xs unpub-filter" data-filter="filter_selection_status">
                                <option value=""></option>
                                <option value="Selected" ${state.filter_selection_status === 'Selected' ? 'selected' : ''}>Selected</option>
                                <option value="Waitlisted" ${state.filter_selection_status === 'Waitlisted' ? 'selected' : ''}>Waitlisted</option>
                                <option value="Rejected" ${state.filter_selection_status === 'Rejected' ? 'selected' : ''}>Rejected</option>
                                <option value="Offer Issued" ${state.filter_selection_status === 'Offer Issued' ? 'selected' : ''}>Offer Issued</option>
                            </select>
                        </th>
                        <th>
                            <div style="color: #2b6cb0; margin-bottom: 5px;">${__('Result')}</div>
                            <select class="form-control input-xs unpub-filter" data-filter="filter_result">
                                <option value=""></option>
                                <option value="Pass" ${state.filter_result === 'Pass' ? 'selected' : ''}>Pass</option>
                                <option value="Fail" ${state.filter_result === 'Fail' ? 'selected' : ''}>Fail</option>
                            </select>
                        </th>
                    </tr>
                </thead>
                <tbody>
    `;

    if (records.length === 0) {
        html += `<tr><td colspan="7" class="text-center text-muted" style="padding: 15px;">${__('No unpublished applicants found matching filters.')}</td></tr>`;
    } else {
        records.forEach((r, idx) => {
            let row_no = ((state.page - 1) * state.limit) + idx + 1;
            let checked = state.selected_names.includes(r.name) ? 'checked' : '';
            
            // Badge styling for Result
            let result_html = r.interview_result_status || '';
            if (result_html === 'Pass') {
                result_html = `<span class="badge badge-success">${result_html}</span>`;
            } else if (result_html === 'Fail') {
                result_html = `<span class="badge badge-danger">${result_html}</span>`;
            }

            html += `
                <tr>
                    <td style="text-align: center;">
                        <input type="checkbox" class="unpub-select-row" data-name="${r.name}" ${checked}>
                    </td>
                    <td style="text-align: center; color: #2b6cb0;">${row_no}</td>
                    <td>${r.applicant || ''}</td>
                    <td style="font-weight: 600;">${r.candidate_name || ''}</td>
                    <td>${r.program || ''}</td>
                    <td>${r.status || ''}</td>
                    <td>${result_html}</td>
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
    html_field.$wrapper.find('.unpub-filter').on('input change', function() {
        let filter_name = $(this).attr('data-filter');
        let val = $(this).val();
        state[filter_name] = val;
        
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            update_unpublished_interviews_table(d, false);
        }, 500);
    });

    html_field.$wrapper.find('.unpub-clear-all').on('click', function() {
        state.selected_names = [];
        html_field.$wrapper.find('.unpub-select-row').prop('checked', false);
        html_field.$wrapper.find('.unpub-select-all').prop('checked', false);
        html_field.$wrapper.find('.unpub-selected-count').text(0);
    });

    html_field.$wrapper.find('.unpub-select-all').on('change', function() {
        let is_checked = $(this).is(':checked');
        html_field.$wrapper.find('.unpub-select-row').each(function() {
            $(this).prop('checked', is_checked);
            let name = $(this).attr('data-name');
            if (is_checked && !state.selected_names.includes(name)) {
                state.selected_names.push(name);
            } else if (!is_checked) {
                state.selected_names = state.selected_names.filter(n => n !== name);
            }
        });
        html_field.$wrapper.find('.unpub-selected-count').text(state.selected_names.length);
    });

    html_field.$wrapper.find('.unpub-select-row').on('change', function() {
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

    html_field.$wrapper.find('.unpub-prev').on('click', function() {
        if (state.page > 1) {
            state.page--;
            update_unpublished_interviews_table(d, true);
        }
    });

    html_field.$wrapper.find('.unpub-next').on('click', function() {
        if (state.page < total_pages) {
            state.page++;
            update_unpublished_interviews_table(d, true);
        }
    });
}
