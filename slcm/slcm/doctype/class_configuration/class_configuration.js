// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on('Class Configuration', {
    refresh: function (frm) {
        // Set filters for links
        set_link_filters(frm);
    },

    add_students_by_filter: function (frm) {
        add_students_by_filter(frm);
    },

    bulk_upload_students: function (frm) {
        bulk_upload_students(frm);
    },

    clear_all_students: function (frm) {
        clear_all_students(frm);
    },

    class_configuration_type: function (frm) {
        // Clear whichever of section/group no longer applies
        if (frm.doc.class_configuration_type === 'Section') {
            frm.set_value('group', '');
        } else if (frm.doc.class_configuration_type === 'Group') {
            frm.set_value('section', '');
        } else {
            frm.set_value('section', '');
            frm.set_value('group', '');
        }
    },

    programme: function (frm) {
        set_link_filters(frm);
    },

    batch: function (frm) {
        set_link_filters(frm);
        if (frm.doc.batch) {
            frappe.db.get_value('SLCM Batch', frm.doc.batch, ['program', 'academic_term'], (r) => {
                if (r) {
                    frm.set_value('programme', r.program || '');
                    frm.set_value('term', r.academic_term || '');
                    if (!r.academic_term) {
                        frappe.show_alert({
                            message: __('Selected Batch has no Academic Term set'),
                            indicator: 'orange'
                        });
                    }
                }
            });
        }
    },

    section: function (frm) {
        set_link_filters(frm);
        if (frm.doc.class_configuration_type === 'Section' && frm.doc.section) {
            fetch_students_for_section(frm);
        }
    },

    term: function (frm) {
        if (frm.doc.term) {
            // Fetch term details
            frappe.db.get_value('Term Configuration', frm.doc.term,
                ['academic_year', 'system'], (r) => {
                    if (r) {
                        frm.set_df_property('term', 'description',
                            `Academic Year: ${r.academic_year}, System: ${r.system}`);
                    }
                });
        }
    },

    course: function (frm) {
        if (frm.doc.course && !frm.doc.class_name) {
            // Auto-generate class name suggestion
            generate_class_name(frm);
        }
    },

    type: function (frm) {
        if (!frm.doc.class_name) {
            generate_class_name(frm);
        }
    }
});

frappe.ui.form.on('Class Student', {
    student: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.student) {
            // Fetch student details
            frappe.db.get_value('Student Master', row.student,
                ['first_name', 'registration_id', 'email'], (r) => {
                    if (r) {
                        let student_name = r.first_name || "";
                        frappe.model.set_value(cdt, cdn, 'student_name', student_name);
                        frappe.model.set_value(cdt, cdn, 'registration_id', r.registration_id);
                        frappe.model.set_value(cdt, cdn, 'email', r.email);
                    }
                });

            // Fetch the student's actual enrolled section for this batch
            // (Student Master has no section of its own - Student Enrollment is)
            if (frm.doc.batch) {
                frappe.db.get_value('Student Enrollment', { student: row.student, batch: frm.doc.batch },
                    'section', (r) => {
                        if (r && r.section) {
                            // Show the human-readable Section Name, not the Section docname
                            frappe.db.get_value('Section', r.section, 'section_name', (s) => {
                                frappe.model.set_value(cdt, cdn, 'section', (s && s.section_name) || r.section);
                            });
                        }
                    });
            }
        }
    }
});

function set_link_filters(frm) {
    // Only show students actually enrolled (via Student Enrollment) in this
    // class's programme/batch/section - Student Master has no batch/section
    // field of its own, so this goes through a custom server-side query.
    if (frm.doc.batch) {
        frm.set_query('student', 'students', function () {
            return {
                query: 'slcm.slcm.doctype.class_configuration.class_configuration.student_query',
                filters: {
                    programme_of_study: frm.doc.programme,
                    batch: frm.doc.batch,
                    section: frm.doc.section,
                },
            };
        });
    }
}

function generate_class_name(frm) {
    let parts = [];
    if (frm.doc.course) {
        parts.push(frm.doc.course);
    }
    if (frm.doc.type) {
        parts.push(frm.doc.type);
    }
    if (frm.doc.batch) {
        parts.push(frm.doc.batch);
    }
    if (frm.doc.section) {
        parts.push(frm.doc.section);
    }

    if (parts.length > 0) {
        frm.set_value('class_name', parts.join(' - '));
    }
}

function add_matched_students(frm, students) {
    let added = 0;
    students.forEach(function (student) {
        let exists = frm.doc.students.find(row => row.student === student.name);
        if (!exists) {
            let row = frm.add_child('students');
            row.student = student.name;
            row.student_name = [student.first_name, student.middle_name, student.last_name].filter(Boolean).join(" ");
            row.registration_id = student.registration_id;
            row.email = student.email;
            row.section = student.section || '';
            added++;
        }
    });
    frm.refresh_field('students');
    return added;
}

function fetch_students_for_section(frm) {
    frappe.call({
        method: 'slcm.slcm.doctype.class_configuration.class_configuration.get_students_by_filter',
        args: {
            programme: frm.doc.programme,
            batch: frm.doc.batch,
            section: frm.doc.section
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                let added = add_matched_students(frm, r.message);
                frappe.show_alert({
                    message: __(`${added} student(s) added from Section ${frm.doc.section}`),
                    indicator: 'green'
                });
            }
        }
    });
}

function add_students_by_filter(frm) {
    let d = new frappe.ui.Dialog({
        title: __('Add Students by Filter'),
        fields: [
            {
                fieldname: 'programme',
                fieldtype: 'Link',
                label: __('Programme'),
                options: 'Programme',
                default: frm.doc.programme
            },
            {
                fieldname: 'batch',
                fieldtype: 'Link',
                options: 'SLCM Batch',
                label: __('Batch'),
                default: frm.doc.batch
            },
            {
                fieldname: 'section',
                fieldtype: 'Link',
                options: 'Section',
                label: __('Section'),
                default: frm.doc.section
            }
        ],
        primary_action_label: __('Add Students'),
        primary_action: function (values) {
            frappe.call({
                method: 'slcm.slcm.doctype.class_configuration.class_configuration.get_students_by_filter',
                args: {
                    programme: values.programme,
                    batch: values.batch,
                    section: values.section
                },
                callback: function (r) {
                    if (r.message && r.message.length > 0) {
                        let added = add_matched_students(frm, r.message);
                        frappe.msgprint(__(`${added} students added successfully`));
                    } else {
                        frappe.msgprint(__('No students found with the given filters'));
                    }
                }
            });
            d.hide();
        }
    });
    d.show();
}

function download_sample_students_csv() {
    let csv_content = "Student ID,Student Name,Section\n"
        + "B20262027001,Jane Doe,B2627-A\n"
        + "B20262027002,John Smith,B2627-A\n";
    let blob = new Blob([csv_content], { type: 'text/csv' });
    let url = window.URL.createObjectURL(blob);
    let link = document.createElement('a');
    link.href = url;
    link.download = 'sample_students.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
}

function bulk_upload_students(frm) {
    let d = new frappe.ui.Dialog({
        title: __('Bulk Upload Students'),
        fields: [
            {
                fieldname: 'sample_html',
                fieldtype: 'HTML',
                options: `<a href="#" id="download-sample-students-csv" class="btn btn-secondary btn-sm">
                    ${frappe.utils.icon('download', 'sm')} ${__('Download Sample CSV')}
                </a>`
            },
            {
                fieldname: 'file',
                fieldtype: 'Attach',
                label: __('Student List (CSV)'),
                reqd: 1,
                description: __('CSV must have a "Student ID" column. "Student Name" and "Section" columns are optional and only for your reference - matching is always done by Student ID.')
            }
        ],
        primary_action_label: __('Upload'),
        primary_action: function (values) {
            frappe.call({
                method: 'slcm.slcm.doctype.class_configuration.class_configuration.bulk_add_students_from_file',
                args: {
                    file_url: values.file
                },
                freeze: true,
                freeze_message: __('Processing student list...'),
                callback: function (r) {
                    let result = r.message || {};
                    if (!result.success) {
                        frappe.msgprint({
                            title: __('Upload Failed'),
                            indicator: 'red',
                            message: result.error || __('Could not process the uploaded file')
                        });
                        return;
                    }

                    let added = add_matched_students(frm, result.matched || []);
                    let unmatched = result.unmatched_rows || [];

                    let message = __(`${added} student(s) added successfully.`);
                    if (unmatched.length > 0) {
                        message += `<br>${__('Not found (Student ID):')} ${unmatched.join(', ')}`;
                    }
                    frappe.msgprint({
                        title: __('Bulk Upload Complete'),
                        indicator: unmatched.length > 0 ? 'orange' : 'green',
                        message: message
                    });
                    d.hide();
                }
            });
        }
    });

    d.get_field('sample_html').$wrapper.find('#download-sample-students-csv').on('click', function (e) {
        e.preventDefault();
        download_sample_students_csv();
    });

    d.show();
}

function clear_all_students(frm) {
    frappe.confirm(
        __('Are you sure you want to clear all students?'),
        function () {
            frm.clear_table('students');
            frm.refresh_field('students');
            frappe.msgprint(__('All students cleared'));
        }
    );
}
