frappe.listview_settings['Student Course Marks'] = {
    onload: function (listview) {
        listview.page.add_inner_button(__('Bulk Import Marks'), function () {
            open_marks_import_dialog();
        });
    }
};

function open_marks_import_dialog() {
    let current_step = 1;
    let import_log = null;
    let missing_student_count = 0;
    let missing_course_count = 0;
    let missing_off_count = 0;
    let preview_page = 1;
    let is_importing = false;

    // Step 1 values
    let selected_file_url = null;
    let selected_exam_plan = null;
    let selected_eval_schema = null;
    let selected_exam_component = null;
    let selected_assessment_type = null;
    let selected_re_exam_component = null;
    let selected_re_exam_assessment_type = null;

    let d = new frappe.ui.Dialog({
        title: __('Bulk Import Student Marks'),
        size: 'extra-large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'stepper_html',
                options: `
                    <style>
                        .import-stepper { display: flex; justify-content: space-between; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #d1d8dd; padding-left: 50px; padding-right: 50px; }
                        .step-item { display: flex; align-items: center; cursor: pointer; color: #8D99A6; transition: all 0.2s; }
                        .step-item.active { color: #1F272E; font-weight: bold; }
                        .step-item.completed { color: #28a745; }
                        .step-item.failed { color: #dc3545; }
                        .step-item.disabled { cursor: not-allowed; opacity: 0.6; }
                        .step-circle { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 8px; background: #F3F3F3; font-size: 12px; }
                        .step-item.active .step-circle { background: #1F272E; color: white; }
                        .step-item.completed .step-circle { background: #28a745; color: white; }
                        .step-item.failed .step-circle { background: #dc3545; color: white; }
                    </style>
                    <div class="import-stepper" id="dialog-stepper">
                        <div class="step-item active" data-step="1"><div class="step-circle">1</div> Upload</div>
                        <div class="step-item disabled" data-step="2"><div class="step-circle">2</div> Preview</div>
                        <div class="step-item disabled" data-step="3"><div class="step-circle">3</div> Validate</div>
                        <div class="step-item disabled" data-step="4"><div class="step-circle">4</div> Import</div>
                    </div>
                `
            },
            {
                fieldtype: 'HTML',
                fieldname: 'step_container',
                options: `<div id="step-render-area"></div>`
            }
        ],
        primary_action_label: __('Next'),
        primary_action: function () {
            handle_next();
        },
        secondary_action_label: __('Previous'),
        secondary_action: function () {
            if (current_step === 4 && !is_importing) {
                d.hide();
                if (window.cur_list) cur_list.refresh();
            } else if (current_step > 1 && !is_importing) {
                render_step(current_step - 1);
            } else if (current_step === 1) {
                d.hide();
            }
        }
    });

    let original_close = d.hide;
    d.hide = function() {
        if ([1, 2, 3].includes(current_step) && import_log) {
            frappe.confirm('This will discard your uploaded data and validation results. Continue?', function() {
                frappe.call({
                    method: "slcm.slcm.doctype.student_course_marks.marks_bulk_import.discard_import_draft",
                    args: { import_log: import_log },
                    callback: function(r) {
                        import_log = null;
                        original_close.call(d);
                    }
                });
            }, function() {
                // Cancel
            });
        } else if (current_step === 4 && is_importing) {
            // Block close
            return;
        } else {
            original_close.call(d);
        }
    };
    d.get_close_btn().off('click').on('click', function() {
        d.hide();
    });

    let step_1_controls = {};

    function update_stepper(step) {
        let stepper = d.wrapper.find('#dialog-stepper');
        for (let i = 1; i <= 4; i++) {
            let el = stepper.find(`[data-step="${i}"]`);
            el.removeClass('active completed failed disabled');

            if (i < step) {
                el.addClass('completed');
                el.find('.step-circle').html('&#10003;'); // checkmark
            } else if (i === step) {
                el.addClass('active');
                el.find('.step-circle').html(i);
            } else {
                el.addClass('disabled');
                el.find('.step-circle').html(i);
            }
        }
    }

    function bind_stepper_clicks() {
        d.wrapper.find('.step-item').on('click', function () {
            if (is_importing) return;
            let target_step = parseInt($(this).attr('data-step'));
            if (target_step < current_step) {
                render_step(target_step);
            }
        });
    }

    function render_step(step) {
        current_step = step;
        update_stepper(step);
        let container = $(d.fields_dict.step_container.wrapper).find('#step-render-area');
        container.empty();

        if (step === 1) {
            d.set_primary_action(__('Next'));
            d.get_primary_btn().prop('disabled', false);
            d.get_secondary_btn().hide();
            d.get_close_btn().show();

            let wrapper = $(`
                <div>
                    <h4>Step 1: Upload File & Select Schema</h4>
                    <p class="text-muted">The file must have exactly matching columns.</p>
                    <p><button id="download-template" class="btn btn-primary btn-sm">Download Sample Template</button></p>
                    <div id="step1-fields"></div>
                    <div id="parsing-loader" style="display: none; margin-top: 24px;" class="text-center">
                        <i class="fa fa-spinner fa-spin fa-3x" style="color:#5e64ff;"></i>
                        <p class="mt-2 text-muted" style="font-size:14px; margin-top:12px;" id="parsing-status-text">Parsing file... please wait.</p>
                        <p style="font-size:20px; font-weight:700; color:#1F272E; margin:6px 0;" id="parsing-count-text"></p>
                        <div style="max-width:320px; margin:10px auto;">
                            <div class="progress" style="height:8px; border-radius:4px;">
                                <div id="parsing-progress-bar" class="progress-bar" style="width:0%; background:#5e64ff; transition:width 0.4s;"></div>
                            </div>
                        </div>
                    </div>
                </div>
            `);
            container.append(wrapper);

            wrapper.find('#download-template').on('click', function (e) {
                e.preventDefault();
                window.open(frappe.urllib.get_full_url('/api/method/slcm.slcm.doctype.student_course_marks.marks_bulk_import.download_sample_template'));
            });

            let fields_wrapper = wrapper.find('#step1-fields');

            let row1 = $('<div class="row"></div>').appendTo(fields_wrapper);
            let col1 = $('<div class="col-sm-4"></div>').appendTo(row1);
            let col2 = $('<div class="col-sm-4"></div>').appendTo(row1);
            let col3 = $('<div class="col-sm-4"></div>').appendTo(row1);

            step_1_controls.import_file = frappe.ui.form.make_control({
                df: { fieldtype: 'Attach', fieldname: 'import_file', label: 'Import File', reqd: 1 },
                parent: col1,
                render_input: true
            });
            if (selected_file_url) step_1_controls.import_file.set_input(selected_file_url);

            step_1_controls.exam_plan = frappe.ui.form.make_control({
                df: { fieldtype: 'Link', fieldname: 'exam_plan', label: 'Exam Plan', options: 'Exam Plan', reqd: 1 },
                parent: col2,
                render_input: true
            });
            if (selected_exam_plan) step_1_controls.exam_plan.set_input(selected_exam_plan);

            step_1_controls.eval_schema = frappe.ui.form.make_control({
                df: { fieldtype: 'Link', fieldname: 'evaluation_schema', label: 'Evaluation Schema', options: 'Evaluation Schema', reqd: 1 },
                parent: col3,
                render_input: true
            });
            if (selected_eval_schema) step_1_controls.eval_schema.set_input(selected_eval_schema);

            let exam_wrapper = $('<div class="exam-section" style="margin-top: 15px; border-top: 1px solid #d1d8dd; padding-top: 15px;"><h5>Exam</h5></div>').appendTo(fields_wrapper);
            let row2 = $('<div class="row"></div>').appendTo(exam_wrapper);
            let col4 = $('<div class="col-sm-6"></div>').appendTo(row2);
            let col5 = $('<div class="col-sm-6"></div>').appendTo(row2);

            step_1_controls.exam_component = frappe.ui.form.make_control({
                parent: col4,
                df: { fieldname: 'exam_component', fieldtype: 'Link', options: 'Exam Component', label: 'Exam Component', reqd: 1 },
                render_input: true
            });
            if (selected_exam_component) step_1_controls.exam_component.set_input(selected_exam_component);

            step_1_controls.assessment_type = frappe.ui.form.make_control({
                parent: col5,
                df: { fieldname: 'assessment_type', fieldtype: 'Link', options: 'Exam Assessment Type', label: 'Assessment Type', reqd: 1 },
                render_input: true
            });
            if (selected_assessment_type) step_1_controls.assessment_type.set_input(selected_assessment_type);

            let re_exam_wrapper = $('<div class="re-exam-section" style="margin-top: 15px; border-top: 1px solid #d1d8dd; padding-top: 15px;"><h5>Re Exam</h5></div>').appendTo(fields_wrapper);
            let row3 = $('<div class="row"></div>').appendTo(re_exam_wrapper);
            let col6 = $('<div class="col-sm-6"></div>').appendTo(row3);
            let col7 = $('<div class="col-sm-6"></div>').appendTo(row3);

            step_1_controls.re_exam_component = frappe.ui.form.make_control({
                parent: col6,
                df: { fieldname: 're_exam_component', fieldtype: 'Link', options: 'Exam Component', label: 'Exam Component', reqd: 1 },
                render_input: true
            });
            step_1_controls.re_exam_component.get_query = function () { return { filters: { component_type: 'Re Exam' } }; };
            if (selected_re_exam_component) step_1_controls.re_exam_component.set_input(selected_re_exam_component);

            step_1_controls.re_exam_assessment_type = frappe.ui.form.make_control({
                parent: col7,
                df: { fieldname: 're_exam_assessment_type', fieldtype: 'Link', options: 'Exam Assessment Type', label: 'Assessment Type', reqd: 1 },
                render_input: true
            });
            step_1_controls.re_exam_assessment_type.get_query = function () { return { filters: { assessment_type: 'ReExam/Makeup Assessment' } }; };
            if (selected_re_exam_assessment_type) step_1_controls.re_exam_assessment_type.set_input(selected_re_exam_assessment_type);

        } else if (step === 2) {
            d.set_primary_action(__('Validate'));
            d.get_secondary_btn().hide();
            d.get_close_btn().show();

            let wrapper = $(`
                <div>
                    <h4>Step 2: Preview &amp; Mapping</h4>
                    <div id="step2-stat-cards" style="display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap;">
                        <div style="flex:1; min-width:110px; background:#f0f4ff; border:1px solid #c7d2fe; border-radius:8px; padding:12px 16px;">
                            <div style="font-size:10px; color:#6366f1; font-weight:700; text-transform:uppercase; letter-spacing:.5px;">Total Rows</div>
                            <div id="s2-total" style="font-size:28px; font-weight:800; color:#1F272E; margin-top:4px;">—</div>
                        </div>
                        <div style="flex:2; min-width:150px; background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:12px 16px;">
                            <div style="font-size:10px; color:#16a34a; font-weight:700; text-transform:uppercase; letter-spacing:.5px;">Exam Plan</div>
                            <div id="s2-plan" style="font-size:13px; font-weight:600; color:#1F272E; margin-top:4px; word-break:break-word;">—</div>
                        </div>
                        <div style="flex:2; min-width:150px; background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:12px 16px;">
                            <div style="font-size:10px; color:#d97706; font-weight:700; text-transform:uppercase; letter-spacing:.5px;">Evaluation Schema</div>
                            <div id="s2-schema" style="font-size:13px; font-weight:600; color:#1F272E; margin-top:4px; word-break:break-word;">—</div>
                        </div>
                    </div>
                    <div style="margin-bottom:12px; display:flex; align-items:center; gap:10px;">
                        <button id="view-full-sheet" class="btn btn-default btn-sm">View Full Sheet</button>
                        <span class="text-muted" style="font-size:11px;">Reg ID → Student | Course Code+Batch+Term → Class | Improvement rules auto-applied</span>
                    </div>
                    <h5 style="margin-bottom:8px;">Parsed Rows Preview</h5>
                    <div id="preview-table-wrapper" style="max-height: 250px; overflow: auto; border: 1px solid #d1d8dd; margin-bottom: 10px;">
                        <span class="text-muted">Loading preview...</span>
                    </div>
                    <div>
                        <button id="preview-prev" class="btn btn-default btn-sm" disabled>Prev</button>
                        <span id="preview-page-info" style="margin: 0 10px;">Page 1</span>
                        <button id="preview-next" class="btn btn-default btn-sm" disabled>Next</button>
                    </div>
                </div>
            `);
            container.append(wrapper);
            // Populate stat cards
            wrapper.find('#s2-plan').text(selected_exam_plan || '—');
            wrapper.find('#s2-schema').text(selected_eval_schema || '—');
            if (import_log) {
                frappe.db.get_value('Marks Import Log', import_log, 'total_rows', function(v) {
                    if (v && v.total_rows != null) wrapper.find('#s2-total').text(v.total_rows.toLocaleString());
                });
            }

            wrapper.find('#view-full-sheet').on('click', function (e) {
                e.preventDefault();
                window.open('/app/marks-import-log-detail?import_log=' + import_log);
            });

            wrapper.find('#preview-prev').on('click', function (e) {
                e.preventDefault();
                if (preview_page > 1) load_preview_page(preview_page - 1);
            });
            wrapper.find('#preview-next').on('click', function (e) {
                e.preventDefault();
                load_preview_page(preview_page + 1);
            });

            load_preview_page(1);

        } else if (step === 3) {
            d.set_primary_action(__('Start Import'));
            d.get_secondary_btn().show().text(__('Previous'));
            d.get_close_btn().show();

            let wrapper = $(`
                <div>
                    <h4>Step 3: Validation Summary</h4>
                    <div id="validation-spinner" class="text-center" style="margin-top: 28px; padding-bottom: 20px;">
                        <i class="fa fa-spinner fa-spin fa-3x" style="color:#5e64ff;"></i>
                        <p class="mt-2 text-muted" style="font-size:14px; margin-top:12px;" id="validation-status-text">Validating rows... please wait</p>
                        <p style="font-size:22px; font-weight:700; color:#1F272E; margin:6px 0;" id="validation-count-text"></p>
                        <div style="max-width:340px; margin:10px auto;">
                            <div class="progress" style="height:8px; border-radius:4px;">
                                <div id="validation-progress-bar" class="progress-bar" style="width:0%; background:#5e64ff; transition:width 0.4s;"></div>
                            </div>
                        </div>
                    </div>
                    <div id="validation-content" style="display: none;">
                        <div id="validation-summary"></div>
                        <div style="margin-top: 15px;" id="csv-download-buttons">
                            <button id="dl-missing-courses" class="btn btn-danger btn-sm" style="display:none;">Missing Courses</button>
                            <button id="dl-missing-classes" class="btn btn-warning btn-sm" style="display:none;">Missing Classes</button>
                            <button id="dl-missing-students" class="btn btn-danger btn-sm" style="display:none;">Missing Students</button>
                        </div>
                        <div id="missing-classes" style="display: none; margin-top: 15px;">
                            <h5><span class="text-danger">Blocked</span>: Missing Classes</h5>
                            <div id="missing-classes-table" style="max-height: 150px; overflow: auto; border: 1px solid #d1d8dd;"></div>
                        </div>
                        <div id="validation-errors" style="display: none; margin-top: 15px;">
                            <h5>Error Details</h5>
                            <div style="margin-bottom: 10px;">
                                <select id="error-status-filter" class="form-control input-sm" style="width: 200px; display: inline-block;">
                                    <option value="">All Errors</option>
                                    <option value="Failed">Failed</option>
                                    <option value="Missing Student">Missing Student</option>
                                    <option value="Missing Course">Missing Course</option>
                                    <option value="Missing Class">Missing Class</option>
                                    <option value="Duplicate (Skip)">Duplicate (Skip)</option>
                                </select>
                            </div>
                            <div id="errors-table-wrapper" style="max-height: 250px; overflow: auto; border: 1px solid #d1d8dd; margin-bottom: 10px;"></div>
                            <div>
                                <button id="errors-prev" class="btn btn-default btn-sm" disabled>Prev</button>
                                <span id="errors-page-info" style="margin: 0 10px;">Page 1</span>
                                <button id="errors-next" class="btn btn-default btn-sm" disabled>Next</button>
                            </div>
                        </div>
                        <div style="margin-top: 20px;" id="proceed-checkbox-wrapper"></div>
                    </div>
                </div>
            `);
            container.append(wrapper);
            d.get_primary_btn().prop('disabled', true);
            
            // Set up real-time event listeners BEFORE triggering validation
            frappe.realtime.off("marks_validation_progress");
            frappe.realtime.on("marks_validation_progress", function(data) {
                if (data.import_log === import_log) {
                    let pct = data.percent != null ? data.percent : (data.total > 0 ? Math.round((data.progress / data.total) * 100) : 0);
                    wrapper.find('#validation-status-text').text('Validating rows... please wait');
                    wrapper.find('#validation-count-text').text(`${data.progress} / ${data.total} (${pct}%)`);
                    wrapper.find('#validation-progress-bar').css('width', pct + '%');
                }
            });
            
            frappe.realtime.off("marks_validation_complete");
            frappe.realtime.on("marks_validation_complete", function(data) {
                if (data.import_log === import_log) {
                    is_validating = false;
                    wrapper.find('#validation-spinner').hide();
                    if (data.error) {
                        wrapper.find('#validation-content').html(`<div class="alert alert-danger"><b>Validation Job Failed:</b><br/>${data.error}</div>`).show();
                    } else {
                        wrapper.find('#validation-content').show();
                        render_validation_results(data, wrapper);
                    }
                }
            });
            
            let is_validating = true;
            let check_val_interval = setInterval(function() {
                if (!is_validating) {
                    clearInterval(check_val_interval);
                    return;
                }
                frappe.db.get_value('Marks Import Log', import_log, ['status', 'success_count', 'failed_count', 'skipped_count', 'missing_offerings_count'], function(v) {
                    if (v && v.status === 'Failed') {
                        clearInterval(check_val_interval);
                        if (is_validating) {
                            is_validating = false;
                            wrapper.find('#validation-spinner').hide();
                            wrapper.find('#validation-content').html(`<div class="alert alert-danger"><b>Validation Job Failed.</b> Please check the system Error Log for traceback details.</div>`).show();
                        }
                    } else if (v && v.status === 'Validated') {
                        clearInterval(check_val_interval);
                        if (is_validating) {
                            is_validating = false;
                            wrapper.find('#validation-spinner').hide();
                            wrapper.find('#validation-content').show();
                            // If fallback hit, trigger the render with the saved counts
                            frappe.call({
                                method: 'slcm.slcm.doctype.student_course_marks.marks_bulk_import.get_errors_page',
                                args: { import_log: import_log, page: 1, page_size: 20, status_filter: 'Missing Class' },
                                callback: function(r2) {
                                    let missing_groups_list = [];
                                    if (r2.message && r2.message.rows) {
                                        // group them (we can just fetch the detailed summary from backend instead)
                                    }
                                    
                                    // A simpler approach is to refresh the validation summary
                                    // We will just do a basic render or the socket event might have caught it anyway
                            frappe.call({
                                method: 'slcm.slcm.doctype.student_course_marks.marks_bulk_import.get_validation_summary',
                                args: { import_log: import_log },
                                callback: function(r3) {
                                    if (r3.message) {
                                        render_validation_results(r3.message, wrapper);
                                    }
                                }
                            });
                                }
                            });
                        }
                    }
                });
            }, 3000);
            
            let retry_mode = is_importing ? "revalidate" : "";
            is_importing = false;
            
            frappe.call({
                method: "slcm.slcm.doctype.student_course_marks.marks_bulk_import.start_validation",
                args: { import_log: import_log, retry_mode: retry_mode },
                callback: function (r) {
                    if (r && r.exc) {
                        is_validating = false;
                        clearInterval(check_val_interval);
                        wrapper.find('#validation-spinner').hide();
                        wrapper.find('#validation-content').html('<div class="alert alert-danger"><b>Validation Error:</b><br/>The server rejected this request. Please check the Error Log.</div>').show();
                    }
                    // Otherwise just wait for realtime events
                },
                error: function() {
                    is_validating = false;
                    clearInterval(check_val_interval);
                    wrapper.find('#validation-spinner').hide();
                    wrapper.find('#validation-content').html('<div class="alert alert-danger"><b>Network Error:</b> Could not start validation. Please try again.</div>').show();
                }
            });

        } else if (step === 4) {
            d.get_primary_btn().hide();
            d.get_secondary_btn().show().text(__('Close'));

            let wrapper = $(`
                <div>
                    <h4>Step 4: Live Progress</h4>
                    <div id="import-step4-status" class="text-center" style="margin-top:20px; margin-bottom:8px;">
                        <i class="fa fa-spinner fa-spin" style="color:#5e64ff;"></i>
                        <span style="color:#8D99A6; font-size:13px; margin-left:8px;">Importing records... please wait</span>
                    </div>
                    <div class="progress" style="height: 26px; margin-top: 8px; border-radius:6px;">
                        <div id="import-progress-bar" class="progress-bar progress-bar-success" role="progressbar" style="width: 0%; font-size:13px; font-weight:600; line-height:26px;">0 / 0 (0%)</div>
                    </div>
                    <div id="import-result-summary" style="margin-top: 20px; display: none;">
                        <h5 id="import-final-title">Import Completed</h5>
                        <p id="import-final-message"></p>
                        <button id="view-log-btn" class="btn btn-default btn-sm">View Log</button>
                        <button id="retry-failed-btn" class="btn btn-primary btn-sm" style="display:none;">Retry Failed Rows</button>
                        
                        <div id="step4-errors-section" style="display: none; margin-top: 20px;">
                            <h5>Error Details</h5>
                            <div id="step4-errors-table-wrapper" style="max-height: 250px; overflow: auto; border: 1px solid #d1d8dd; margin-bottom: 10px;"></div>
                            <div>
                                <button id="step4-errors-prev" class="btn btn-default btn-sm" disabled>Prev</button>
                                <span id="step4-errors-page-info" style="margin: 0 10px;">Page 1</span>
                                <button id="step4-errors-next" class="btn btn-default btn-sm" disabled>Next</button>
                            </div>
                        </div>
                    </div>
                </div>
            `);
            container.append(wrapper);

            if (is_importing) {
                d.get_secondary_btn().prop('disabled', true);
                d.get_close_btn().hide();
            } else {
                d.get_secondary_btn().prop('disabled', false);
                d.get_close_btn().show();
            }
        }
        update_dialog_footer();
    }

    function update_dialog_footer() {
        // Frappe 13+ standard Dialogs use a custom-actions div floated left
        let custom_actions = d.footer.find('.custom-actions');
        custom_actions.empty(); // clear existing buttons if any
        
        if (current_step === 2 || current_step === 3) {
            let restart_btn = $('<button class="btn btn-danger btn-sm" style="float: left; margin-right: 10px;">Restart</button>');
            restart_btn.on('click', function(e) {
                e.preventDefault();
                frappe.confirm('This will permanently delete your uploaded file and all drafted validation results. Continue?', function() {
                    frappe.call({
                        method: "slcm.slcm.doctype.student_course_marks.marks_bulk_import.discard_import_draft",
                        args: { import_log: import_log },
                        callback: function(r) {
                            if (!r.exc) {
                                // Successfully discarded, reset state
                                import_log = null;
                                selected_file_url = null;
                                is_importing = false;
                                render_step(1);
                            }
                        }
                    });
                });
            });
            custom_actions.append(restart_btn);
        }
    }

    function handle_next() {
        if (current_step === 1) {
            let file = step_1_controls.import_file.get_value();
            let plan = step_1_controls.exam_plan.get_value();
            let eval_sch = step_1_controls.eval_schema.get_value();
            let exam_comp = step_1_controls.exam_component.get_value();
            let asst_type = step_1_controls.assessment_type.get_value();
            let re_exam_comp = step_1_controls.re_exam_component.get_value();
            let re_exam_asst_type = step_1_controls.re_exam_assessment_type.get_value();

            if (!file || !plan || !eval_sch || !exam_comp || !asst_type) {
                frappe.msgprint("Please provide the file, exam plan, evaluation schema, exam component, and assessment type.");
                return;
            }

            d.get_primary_btn().prop('disabled', true);
            let proceed = () => {
                selected_file_url = file;
                selected_exam_plan = plan;
                selected_eval_schema = eval_sch;
                selected_exam_component = exam_comp;
                selected_assessment_type = asst_type;
                selected_re_exam_component = re_exam_comp;
                selected_re_exam_assessment_type = re_exam_asst_type;
                
                let container = $(d.fields_dict.step_container.wrapper).find('#step-render-area');
                container.find('#step1-fields').hide();
                container.find('#parsing-loader').show();
                
                frappe.realtime.off("marks_parsing_progress");
                frappe.realtime.on("marks_parsing_progress", function(data) {
                    container.find('#parsing-status-text').text('Parsing file... please wait');
                    container.find('#parsing-count-text').text(`${data.progress} / ${data.total} rows (${data.percent || 0}%)`);
                    container.find('#parsing-progress-bar').css('width', (data.percent || 0) + '%');
                });

                frappe.realtime.off("marks_parsing_complete");
                frappe.realtime.on("marks_parsing_complete", function(data) {
                    if (window.check_parse_interval) {
                        clearInterval(window.check_parse_interval);
                        window.check_parse_interval = null;
                    }
                    frappe.realtime.off("marks_parsing_progress");
                    frappe.realtime.off("marks_parsing_complete");
                    d.get_primary_btn().prop('disabled', false);
                    
                    if (data.error) {
                        container.find('#step1-fields').show();
                        container.find('#parsing-loader').hide();
                        frappe.msgprint({title: data.error_title || "Error", message: data.error, indicator: "red"});
                        return;
                    }
                    if (data.import_log) {
                        import_log = data.import_log;
                        render_step(2);
                    }
                });

                frappe.call({
                    method: "slcm.slcm.doctype.student_course_marks.marks_bulk_import.parse_import_file",
                    args: { file_url: file, exam_plan: plan, evaluation_schema: eval_sch, exam_component: exam_comp, assessment_type: asst_type, re_exam_component: re_exam_comp, re_exam_assessment_type: re_exam_asst_type },
                    callback: function (r) {
                        if (r && r.exc) {
                            d.get_primary_btn().prop('disabled', false);
                            frappe.realtime.off("marks_parsing_progress");
                            frappe.realtime.off("marks_parsing_complete");
                            container.find('#step1-fields').show();
                            container.find('#parsing-loader').hide();
                            return;
                        }
                        if (r.message && r.message.status === "parsing") {
                            import_log = r.message.import_log;
                            // Add polling fallback in case socket.io fails
                            if (!window.check_parse_interval) {
                                window.check_parse_interval = setInterval(function() {
                                    if (!import_log) return;
                                    frappe.db.get_value('Marks Import Log', import_log, ['status', 'total_rows'], function(v) {
                                        if (v && v.status === 'Staging') {
                                            clearInterval(window.check_parse_interval);
                                            window.check_parse_interval = null;
                                            frappe.realtime.off("marks_parsing_progress");
                                            frappe.realtime.off("marks_parsing_complete");
                                            d.get_primary_btn().prop('disabled', false);
                                            render_step(2);
                                        } else if (v && (v.status === 'Failed' || v.status === 'Completed with Errors')) {
                                            clearInterval(window.check_parse_interval);
                                            window.check_parse_interval = null;
                                            frappe.realtime.off("marks_parsing_progress");
                                            frappe.realtime.off("marks_parsing_complete");
                                            d.get_primary_btn().prop('disabled', false);
                                            container.find('#step1-fields').show();
                                            container.find('#parsing-loader').hide();
                                            frappe.msgprint({title: "Parse Failed", message: "Parsing job failed. Check Error Log.", indicator: "red"});
                                        } else if (v && v.status === 'Parsing') {
                                            // Fallback progress update
                                            let progress = v.total_rows || 0;
                                            if (progress > 0) {
                                                container.find('#parsing-count-text').text(progress + ' rows processed...');
                                            }
                                        }
                                    });
                                }, 3000);
                            }
                        } else if (r.message && r.message.import_log) {
                            d.get_primary_btn().prop('disabled', false);
                            frappe.realtime.off("marks_parsing_progress");
                            frappe.realtime.off("marks_parsing_complete");
                            import_log = r.message.import_log;
                            render_step(2);
                        } else {
                            d.get_primary_btn().prop('disabled', false);
                            frappe.realtime.off("marks_parsing_progress");
                            frappe.realtime.off("marks_parsing_complete");
                            container.find('#parsing-loader').hide();
                            container.find('#step1-fields').show();
                            frappe.msgprint({title: "Parse Failed", message: "Failed to start parsing job.", indicator: "red"});
                        }
                    },
                    error: function () {
                        d.get_primary_btn().prop('disabled', false);
                        frappe.realtime.off("marks_parsing_progress");
                        frappe.realtime.off("marks_parsing_complete");
                        container.find('#step1-fields').show();
                        container.find('#parsing-loader').hide();
                        frappe.msgprint({title: "Network Error", message: "Could not reach the server. Please check your connection and try again.", indicator: "red"});
                    }
                });
            };

            if (import_log && selected_file_url !== file) {
                // new file selected, delete old log
                frappe.call({
                    method: "slcm.slcm.doctype.student_course_marks.marks_bulk_import.delete_import_log",
                    args: { import_log: import_log },
                    callback: function () {
                        import_log = null;
                        proceed();
                    },
                    error: function () {
                        d.get_primary_btn().prop('disabled', false);
                    }
                });
            } else {
                proceed();
            }

        } else if (current_step === 2) {
            render_step(3);
        } else if (current_step === 3) {
            let container = $(d.fields_dict.step_container.wrapper).find('#step-render-area');
            let cb = container.find('#proceed_checkbox');
            if (cb.length > 0 && !cb.prop('checked') && !cb.prop('disabled')) {
                frappe.msgprint("You must check the confirmation box to proceed.");
                return;
            }

            d.get_primary_btn().prop('disabled', true);
            is_importing = true;
            render_step(4);

            function handle_progress_update(data) {
                if (data.import_log === import_log) {
                    let pct = data.percent != null ? Math.round(data.percent) : (data.total > 0 ? Math.round((data.progress / data.total) * 100) : 100);
                    let step_container = $(d.fields_dict.step_container.wrapper).find('#step-render-area');
                    let pbar = step_container.find('#import-progress-bar');
                    pbar.css('width', pct + '%').text(`${data.progress || 0} / ${data.total || 0}  (${pct}%)`);

                    if (data.progress >= data.total) {
                        is_importing = false;
                        d.get_secondary_btn().prop('disabled', false).text(__('Close'));
                        d.get_close_btn().show();
                        step_container.find('#import-step4-status').hide();

                        step_container.find('#import-result-summary').show();
                        step_container.find('#view-log-btn').off('click').on('click', function () {
                            window.open('/app/marks-import-log/' + import_log);
                        });

                        // Check status for retry button
                        frappe.db.get_value('Marks Import Log', import_log, 'status', function (v) {
                            if (v && (v.status === 'Completed with Errors' || v.status === 'Failed')) {
                                d.wrapper.find('.step-item[data-step="4"]').removeClass('active').addClass('failed').find('.step-circle').html('X');
                                step_container.find('#import-final-title').html('<span class="text-danger">Completed with Errors</span>');
                                step_container.find('#import-final-message').text('The import finished, but some rows failed to process.');

                                let rbtn = step_container.find('#retry-failed-btn');
                                rbtn.show().off('click').on('click', function () {
                                    d.get_secondary_btn().prop('disabled', true);
                                    frappe.call({
                                        method: "slcm.slcm.doctype.student_course_marks.marks_bulk_import.retry_failed_rows",
                                        args: { import_log: import_log },
                                        callback: function (r2) {
                                            d.get_secondary_btn().prop('disabled', false);
                                            if (!r2.exc) {
                                                is_importing = true;
                                                render_step(4);
                                            }
                                        }
                                    });
                                });

                                // Load error table
                                step_container.find('#step4-errors-section').show();
                                bind_error_pagination(step_container, '#step4-errors-prev', '#step4-errors-next', '#step4-errors-page-info', '#step4-errors-table-wrapper', 'Failed');

                            } else {
                                d.wrapper.find('.step-item[data-step="4"]').removeClass('active').addClass('completed').find('.step-circle').html('&#10003;');
                                step_container.find('#import-final-title').html('<span class="text-success">Import Completed Successfully</span>');
                                step_container.find('#import-final-message').text('All rows were imported without errors.');
                            }
                        });
                    }
                }
            }

            frappe.realtime.off("marks_import_progress");
            frappe.realtime.on("marks_import_progress", handle_progress_update);

            // Fallback polling for very fast imports that might miss the socket event
            let check_interval = setInterval(function() {
                if (!is_importing) {
                    clearInterval(check_interval);
                    return;
                }
                frappe.db.get_value('Marks Import Log', import_log, ['status', 'total_rows'], function(v) {
                    if (v && ['Completed', 'Completed with Errors', 'Failed'].includes(v.status)) {
                        clearInterval(check_interval);
                        if (is_importing) {
                            handle_progress_update({
                                import_log: import_log,
                                progress: v.total_rows || 100,
                                total: v.total_rows || 100
                            });
                        }
                    }
                });
            }, 3000);

            frappe.call({
                method: "slcm.slcm.doctype.student_course_marks.marks_bulk_import.start_bulk_import",
                args: { import_log: import_log, skip_blocked: 1 },
                callback: function (r) {
                    if (r && r.exc) {
                        is_importing = false;
                        clearInterval(check_interval);
                        d.get_secondary_btn().prop('disabled', false).text(__('Close'));
                        d.get_close_btn().show();
                        let sc = $(d.fields_dict.step_container.wrapper).find('#step-render-area');
                        sc.find('#import-step4-status').hide();
                        sc.find('#import-result-summary').show();
                        sc.find('#import-final-title').html('<span class="text-danger">Import Failed to Start</span>');
                        sc.find('#import-final-message').text('An error occurred before import could begin. Please check the Frappe Error Log.');
                    }
                },
                error: function() {
                    is_importing = false;
                    clearInterval(check_interval);
                    d.get_secondary_btn().prop('disabled', false).text(__('Close'));
                    d.get_close_btn().show();
                    frappe.msgprint({title: "Network Error", message: "Could not start import. Please check your connection.", indicator: "red"});
                }
            });
        }
    }

    function load_preview_page(page) {
        frappe.call({
            method: "slcm.slcm.doctype.student_course_marks.marks_bulk_import.get_preview_page",
            args: { import_log: import_log, page: page, page_size: 50 },
            callback: function (r) {
                if (r.message) {
                    preview_page = r.message.page;
                    let container = $(d.fields_dict.step_container.wrapper).find('#step-render-area');
                    container.find('#preview-page-info').text('Page ' + preview_page);

                    let has_more = (preview_page * r.message.page_size) < r.message.total;
                    container.find('#preview-next').prop('disabled', !has_more);
                    container.find('#preview-prev').prop('disabled', preview_page <= 1);

                    render_preview_table(r.message.rows, container);
                }
            }
        });
    }

    function load_errors_page(page, filter, container, info_el, wrapper_el, prev_btn, next_btn) {
        frappe.call({
            method: "slcm.slcm.doctype.student_course_marks.marks_bulk_import.get_errors_page",
            args: { import_log: import_log, page: page, page_size: 20, status_filter: filter },
            callback: function (r) {
                if (r.message) {
                    container.find(info_el).text('Page ' + r.message.page);
                    let has_more = (r.message.page * r.message.page_size) < r.message.total;
                    container.find(next_btn).prop('disabled', !has_more).data('page', r.message.page + 1);
                    container.find(prev_btn).prop('disabled', r.message.page <= 1).data('page', r.message.page - 1);

                    if (r.message.rows.length === 0) {
                        container.find(wrapper_el).html('<div style="padding:10px;" class="text-muted">No errors found.</div>');
                    } else {
                        let html = '<table class="table table-bordered table-condensed" style="font-size: 11px;"><thead><tr><th style="width:20%;">Detail ID</th><th style="width:20%;">Status</th><th>Error Message</th></tr></thead><tbody>';
                        r.message.rows.forEach(row => {
                            html += `<tr>
                                <td><a href="/app/marks-import-log-detail/${row.name}" target="_blank">${row.name}</a></td>
                                <td>${row.status}</td>
                                <td class="text-danger">${row.error_reason || ''}</td>
                            </tr>`;
                        });
                        html += '</tbody></table>';
                        container.find(wrapper_el).html(html);
                    }
                }
            }
        });
    }

    function bind_error_pagination(container, prev_btn, next_btn, info_el, wrapper_el, default_filter) {
        let filter_val = default_filter || '';

        container.find(prev_btn).off('click').on('click', function (e) {
            e.preventDefault();
            load_errors_page($(this).data('page'), filter_val, container, info_el, wrapper_el, prev_btn, next_btn);
        });

        container.find(next_btn).off('click').on('click', function (e) {
            e.preventDefault();
            load_errors_page($(this).data('page'), filter_val, container, info_el, wrapper_el, prev_btn, next_btn);
        });

        if (container.find('#error-status-filter').length > 0) {
            container.find('#error-status-filter').off('change').on('change', function () {
                filter_val = $(this).val();
                load_errors_page(1, filter_val, container, info_el, wrapper_el, prev_btn, next_btn);
            });
        }

        load_errors_page(1, filter_val, container, info_el, wrapper_el, prev_btn, next_btn);
    }

    function render_preview_table(rows, container) {
        if (!rows || rows.length === 0) return;
        let html = '<table class="table table-bordered table-condensed" style="font-size: 11px;"><thead><tr>';
        let keys = Object.keys(rows[0].raw_data || {});
        html += '<th>Row #</th>';
        keys.forEach(k => { html += `<th>${k}</th>`; });
        html += '</tr></thead><tbody>';
        rows.forEach(r => {
            html += '<tr>';
            html += `<td>${r.row_number}</td>`;
            let raw = r.raw_data || {};
            keys.forEach(k => { html += `<td>${raw[k] !== undefined && raw[k] !== null ? raw[k] : ''}</td>`; });
            html += '</tr>';
        });
        html += '</tbody></table>';
        container.find('#preview-table-wrapper').html(html);
    }

    function render_validation_results(res, wrapper) {
        let cardS = 'flex:1; min-width:100px; border-radius:8px; padding:10px 12px; text-align:center;';
        let summary = `
            <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
                <div style="${cardS} background:#f0fdf4; border:1px solid #bbf7d0;">
                    <div style="font-size:9px; color:#16a34a; font-weight:700; text-transform:uppercase; letter-spacing:.5px;">Valid</div>
                    <div style="font-size:24px; font-weight:800; color:#16a34a;">${res.valid_count || 0}</div>
                </div>
                <div style="${cardS} background:#fffbeb; border:1px solid #fde68a;">
                    <div style="font-size:9px; color:#d97706; font-weight:700; text-transform:uppercase; letter-spacing:.5px;">Duplicates</div>
                    <div style="font-size:24px; font-weight:800; color:#d97706;">${res.skip_count || 0}</div>
                </div>
                <div style="${cardS} background:#fef2f2; border:1px solid #fecaca;">
                    <div style="font-size:9px; color:#dc2626; font-weight:700; text-transform:uppercase; letter-spacing:.5px;">Errors</div>
                    <div style="font-size:24px; font-weight:800; color:#dc2626;">${res.error_count || 0}</div>
                </div>
                <div style="${cardS} background:#fef2f2; border:1px solid #fecaca;">
                    <div style="font-size:9px; color:#dc2626; font-weight:700; text-transform:uppercase; letter-spacing:.5px;">Miss. Students</div>
                    <div style="font-size:24px; font-weight:800; color:#dc2626;">${res.missing_student_count || 0}</div>
                </div>
                <div style="${cardS} background:#fef2f2; border:1px solid #fecaca;">
                    <div style="font-size:9px; color:#dc2626; font-weight:700; text-transform:uppercase; letter-spacing:.5px;">Miss. Courses</div>
                    <div style="font-size:24px; font-weight:800; color:#dc2626;">${res.missing_course_count || 0}</div>
                </div>
                <div style="${cardS} background:#fff7ed; border:1px solid #fed7aa;">
                    <div style="font-size:9px; color:#ea580c; font-weight:700; text-transform:uppercase; letter-spacing:.5px;">Miss. Classes</div>
                    <div style="font-size:24px; font-weight:800; color:#ea580c;">${res.missing_class_count || 0}</div>
                </div>
            </div>`;
        wrapper.find('#validation-summary').html(summary);

        if (res.missing_course_count > 0) {
            wrapper.find('#dl-missing-courses').show().on('click', () => window.open(frappe.urllib.get_full_url('/api/method/slcm.slcm.doctype.student_course_marks.marks_bulk_import.download_missing_courses_template?import_log=' + import_log)));
        }
        if (res.missing_class_count > 0) {
            wrapper.find('#dl-missing-classes').show().on('click', () => window.open(frappe.urllib.get_full_url('/api/method/slcm.slcm.doctype.student_course_marks.marks_bulk_import.download_missing_classes_template?import_log=' + import_log)));
        }
        if (res.missing_student_count > 0) {
            wrapper.find('#dl-missing-students').show().on('click', () => window.open(frappe.urllib.get_full_url('/api/method/slcm.slcm.doctype.student_course_marks.marks_bulk_import.download_missing_students?import_log=' + import_log)));
        }

        if (res.missing_class_groups && res.missing_class_groups.length > 0) {
            let mhtml = '<table class="table table-bordered table-condensed" style="font-size: 11px;"><thead><tr><th>Course Code</th><th>Batch</th><th>Term Name</th><th>Affected Rows</th></tr></thead><tbody>';
            res.missing_class_groups.forEach(g => {
                mhtml += `<tr><td>${g.course_code}</td><td>${g.batch}</td><td>${g.term_name}</td><td>${g.affected_row_count}</td></tr>`;
            });
            mhtml += '</tbody></table>';
            wrapper.find('#missing-classes-table').html(mhtml);
            wrapper.find('#missing-classes').show();
        }

        if (res.error_count > 0 || res.missing_student_count > 0 || res.missing_course_count > 0 || res.missing_class_count > 0 || res.skip_count > 0) {
            wrapper.find('#validation-errors').show();
            bind_error_pagination(wrapper, '#errors-prev', '#errors-next', '#errors-page-info', '#errors-table-wrapper', '');
        }

        let issues = res.error_count + res.missing_student_count + res.missing_course_count + res.missing_class_count + res.skip_count;

        let cb_html = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <label><input type="checkbox" id="proceed_checkbox" ${issues === 0 ? 'checked disabled' : ''}> 
                    Import ${res.valid_count} valid rows now, skip ${issues} rows with issues
                </label>
                <button class="btn btn-default btn-sm" id="revalidate-btn">Re-validate</button>
            </div>
        `;
        wrapper.find('#proceed-checkbox-wrapper').html(cb_html);
        
        wrapper.find('#revalidate-btn').on('click', function() {
            is_importing = true; // flag to trigger revalidate
            d.get_primary_btn().prop('disabled', true);
            render_step(3);
        });

        if (issues > 0) {
            d.get_primary_btn().prop('disabled', true);
            wrapper.find('#proceed_checkbox').on('change', function () {
                d.get_primary_btn().prop('disabled', !$(this).prop('checked'));
            });
        } else {
            d.get_primary_btn().prop('disabled', false);
        }
    }

    d.show();
    render_step(1);
    bind_stepper_clicks();
}
