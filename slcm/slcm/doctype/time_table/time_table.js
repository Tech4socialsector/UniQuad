// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

// Renders "Scheduling... NN%" with a spinner into Frappe's freeze overlay
// (the #freeze backdrop shown while the save request runs). The server pushes
// `time_table_bulk_progress` after every occurrence it creates/updates.
function render_bulk_progress(data) {
    const $msg = $('#freeze .freeze-message');
    if (!$msg.length) return;

    const percent = Math.min(100, Math.max(0, cint(data.percent)));
    const counts = data.total
        ? `<div class="text-muted small mt-1">${__('{0} of {1} occurrence(s)', [cint(data.done), cint(data.total)])}</div>`
        : '';

    $msg.html(`
        <div class="d-flex align-items-center justify-content-center">
            <span class="spinner-border spinner-border-sm text-primary mr-2" role="status"></span>
            <span class="lead mb-0">${__(data.label || 'Scheduling')}... ${percent}%</span>
        </div>
        <div class="progress mt-2" style="height: 6px; min-width: 240px;">
            <div class="progress-bar" style="width: ${percent}%"></div>
        </div>
        ${counts}
    `);
}

if (!frappe.flags.time_table_progress_bound) {
    frappe.flags.time_table_progress_bound = true;
    frappe.realtime.on('time_table_bulk_progress', render_bulk_progress);
}

// The freeze overlay is created by the save request that starts right after
// before_save, so wait briefly for it before showing the initial 0%.
function show_initial_progress(label) {
    let tries = 0;
    const timer = setInterval(() => {
        if ($('#freeze .freeze-message').length) {
            clearInterval(timer);
            // A server update may already have rendered a real percentage.
            if (!$('#freeze .progress').length) {
                render_bulk_progress({ label: label, percent: 0 });
            }
        } else if (++tries > 40) {
            clearInterval(timer);
        }
    }, 50);
}

frappe.ui.form.on('Time Table', {
    before_save: function (frm) {
        if (frm.is_new() && frm.doc.repeat_frequency && frm.doc.repeat_frequency !== 'Never') {
            show_initial_progress('Scheduling');
        }
    },

    setup: function (frm) {
        // Both fields link to Student Group - restrict each to its own group type.
        frm.set_query('office_hours_group', function () {
            return { filters: { group_based_on: 'Office Hours' } };
        });
        frm.set_query('week', 'class_participation_week_group', function () {
            return { filters: { group_based_on: 'Class-Participation' } };
        });
    },

    refresh: function (frm) {
        frm.set_df_property('course', 'read_only', frm.doc.class_name ? 1 : 0);

        // Auto-generate title if not set
        if (!frm.doc.title && frm.doc.course) {
            frm.trigger('generate_title');
        }

        if (!frm.is_new()) {
            frm.add_custom_button(__('Mark Attendance'), function () {
                // Attendance for this entry is taken against the Time Table
                // (its Class gives the roster); only Office Hours differ.
                frappe.route_options = {
                    'based_on': frm.doc.based_on === 'Office Hours' ? 'Office Hours' : 'Time Table',
                    'class_schedule': frm.doc.name,
                    'date': frm.doc.schedule_date
                };
                frappe.set_route('Form', 'Student Attendance Tool');
            });

            // Only meaningful for recurring series (this doc is either the
            // parent of a series or one of its generated children).
            if (frm.doc.parent_schedule || frm.doc.repeat_frequency !== 'Never') {
                frm.add_custom_button(__('Apply Changes to Future Occurrences'), function () {
                    frm.events.show_apply_future_dialog(frm);
                }, __('Actions'));
            }

            frm.events.render_attendance_lock(frm);
        }
    },

    // Attendance lock: a headline with the linked session's lock state, and
    // (for AAD) Reopen / Lock buttons. See slcm.slcm.utils.attendance_lock.
    render_attendance_lock: function (frm) {
        const name = frm.doc.name;
        frappe.call({
            method: 'slcm.slcm.utils.attendance_lock.get_time_table_lock_status',
            args: { time_table: name },
            callback: function (r) {
                const s = r.message;
                // Ignore a late response after navigating to another entry
                if (!s || !s.session || frm.doc.name !== name) return;

                if (s.reopened) {
                    frm.dashboard.set_headline_alert(
                        __('Attendance reopened by {0} on {1}. Reason: {2}', [
                            frappe.utils.escape_html(s.reopened_by || ''),
                            s.reopened_on || '',
                            frappe.utils.escape_html(s.reopen_reason || '')
                        ]),
                        'orange'
                    );
                } else if (s.locked) {
                    frm.dashboard.set_headline_alert(
                        __('Attendance locked since {0} ({1} hours after the session ended). Faculty can no longer change it.', [s.lock_at, s.lock_hours]),
                        'red'
                    );
                } else if (s.lock_at) {
                    frm.dashboard.set_headline_alert(
                        __('Faculty can change attendance until {0}.', [s.lock_at]),
                        'green'
                    );
                }

                if (!s.can_manage) return;
                const group = __('Attendance Lock');
                if (s.locked) {
                    frm.add_custom_button(__('Reopen Attendance'), function () {
                        frm.events.attendance_lock_dialog(frm, s, 'reopen');
                    }, group);
                } else if (s.reopened) {
                    frm.add_custom_button(__('Lock Attendance'), function () {
                        frm.events.attendance_lock_dialog(frm, s, 'lock');
                    }, group);
                }
                frm.add_custom_button(__('Reopen History'), function () {
                    frappe.set_route('List', 'Attendance Reopen Log', { attendance_session: s.session });
                }, group);
            }
        });
    },

    attendance_lock_dialog: function (frm, status, mode) {
        const reopen = mode === 'reopen';
        const d = new frappe.ui.Dialog({
            title: reopen ? __('Reopen Attendance') : __('Lock Attendance'),
            fields: [
                {
                    fieldtype: 'HTML',
                    options: '<p class="text-muted">' + (reopen
                        ? __('Faculty will be able to change attendance for session {0} again, until you lock it.', [status.session])
                        : __('Faculty will no longer be able to change attendance for session {0}.', [status.session])) + '</p>'
                },
                {
                    fieldname: 'reason',
                    fieldtype: 'Small Text',
                    label: __('Reason'),
                    reqd: reopen ? 1 : 0
                },
                {
                    fieldname: 'notice',
                    fieldtype: 'Small Text',
                    label: __('Notice to Faculty'),
                    description: __('Optional message included in the faculty notification.')
                },
                {
                    fieldname: 'notify_faculty',
                    fieldtype: 'Check',
                    label: __('Notify Faculty'),
                    default: 1
                }
            ],
            primary_action_label: reopen ? __('Reopen') : __('Lock'),
            primary_action: function (values) {
                frappe.call({
                    method: reopen
                        ? 'slcm.slcm.utils.attendance_lock.reopen_attendance'
                        : 'slcm.slcm.utils.attendance_lock.lock_attendance',
                    args: {
                        session: status.session,
                        reason: values.reason,
                        notice: values.notice,
                        notify_faculty: values.notify_faculty ? 1 : 0
                    },
                    freeze: true,
                    callback: function (r) {
                        if (r.exc) return;
                        d.hide();
                        frappe.show_alert({
                            message: reopen ? __('Attendance reopened') : __('Attendance locked'),
                            indicator: 'green'
                        }, 5);
                        frm.reload_doc();
                    }
                });
            }
        });
        d.show();
    },

    show_apply_future_dialog: function (frm) {
        if (frm.is_dirty()) {
            frappe.msgprint({
                title: __('Save First'),
                message: __('Please save this occurrence before applying changes to future occurrences.'),
                indicator: 'orange'
            });
            return;
        }

        frappe.call({
            method: 'slcm.slcm.doctype.time_table.time_table.get_future_occurrences',
            args: { time_table_name: frm.doc.name },
            freeze: true,
            callback: function (r) {
                const info = r.message || { count: 0, occurrences: [] };
                if (!info.count) {
                    frappe.msgprint(__('No current or future occurrences found in this series.'));
                    return;
                }

                const dialog = new frappe.ui.Dialog({
                    title: __('Apply to Future Occurrences'),
                                        fields: [
                        {
                            fieldtype: 'HTML',
                            options: `<p>${__('This will update')} <b>${info.count}</b> ${__('occurrence(s) — today and every future date in this series. Past dates are left untouched.')}</p>`
                        },
                        {
                            fieldtype: 'Section Break',
                            label: __('Faculty')
                        },
                        {
                            fieldname: 'instructor',
                            fieldtype: 'Link',
                            options: 'Faculty',
                            label: __('Faculty'),
                            default: frm.doc.instructor
                        },
                        {
                            fieldtype: 'Section Break',
                            label: __('Schedule')
                        },
                        {
                            fieldname: 'schedule_date',
                            fieldtype: 'Date',
                            label: __('Schedule Date'),
                            default: frm.doc.schedule_date
                        },
                        {
                            fieldname: 'venue',
                            fieldtype: 'Link',
                            options: 'Venue Master',
                            label: __('Venue'),
                            default: frm.doc.venue
                        },
                        {
                            fieldname: 'from_time',
                            fieldtype: 'Time',
                            label: __('From Time'),
                            default: frm.doc.from_time ? frm.doc.from_time.padStart(8, '0') : ''
                        },
                        {
                            fieldname: 'to_time',
                            fieldtype: 'Time',
                            label: __('To Time'),
                            default: frm.doc.to_time ? frm.doc.to_time.padStart(8, '0') : ''
                        },
                        {
                            fieldtype: 'Section Break',
                            label: __('Repeat Settings')
                        },
                        {
                            fieldname: 'repeat_frequency',
                            fieldtype: 'Select',
                            label: __('Repeat'),
                            options: 'Never\nDaily\nWeekly\nMonthly',
                            default: frm.doc.repeat_frequency
                        },
                        {
                            fieldname: 'repeats_till',
                            fieldtype: 'Date',
                            label: __('Repeats Till'),
                            depends_on: 'eval:doc.repeat_frequency && doc.repeat_frequency != "Never"',
                            default: frm.doc.repeats_till
                        },
                        {
                            fieldtype: 'Section Break',
                            label: __('Display Settings')
                        },
                        {
                            fieldname: 'title',
                            fieldtype: 'Data',
                            label: __('Title'),
                            default: frm.doc.title
                        },
                        {
                            fieldname: 'color',
                            fieldtype: 'Color',
                            label: __('Color'),
                            default: frm.doc.color
                        }
                    ],
                    primary_action_label: __('Apply'),
                    primary_action: function (values) {
                        const updates = {};
                        const check_fields = ['instructor', 'schedule_date', 'venue', 'from_time', 'to_time', 'repeat_frequency', 'repeats_till', 'title', 'color'];
                        check_fields.forEach(f => {
                            if (values[f] !== undefined && values[f] !== frm.doc[f]) {
                                updates[f] = values[f];
                            }
                        });

                        if (!Object.keys(updates).length) {
                            frappe.msgprint(__('No changes were made.'));
                            return;
                        }

                        frappe.call({
                            method: 'slcm.slcm.doctype.time_table.time_table.bulk_update_future_occurrences',
                            args: {
                                time_table_name: frm.doc.name,
                                updates: updates
                            },
                            freeze: true,
                            freeze_message: __('Checking for conflicts and updating...'),
                            callback: function (res) {
                                if (res.message) {
                                    dialog.hide();
                                    frappe.show_alert({
                                        message: __('Updated {0} occurrence(s)', [res.message.updated_count]),
                                        indicator: 'green'
                                    }, 5);
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                });

                dialog.show();
            }
        });
    },

    class_name: function (frm) {
        // Course, programme, section, faculty, academic year and term
        // come from the Class (fetch_from); the title names the class.
        frm.set_df_property('course', 'read_only', frm.doc.class_name ? 1 : 0);
        if (!frm.doc.class_name) return;
        frappe.db.get_value('Classes', frm.doc.class_name,
            ['course_name', 'section', 'group_name', 'faculty'], (r) => {
                if (!r) return;
                frm.set_value('title', [r.course_name, r.section || r.group_name].filter(Boolean).join(' - '));
                if (!frm.doc.instructor && r.faculty) frm.set_value('instructor', r.faculty);
            });
    },

    class_configuration: function (frm) {
        if (frm.doc.class_configuration) {
            // Fetch details from Class Configuration
            frappe.db.get_value('Class Configuration', frm.doc.class_configuration,
                ['course', 'faculty', 'programme', 'term'], (r) => {
                    if (r) {
                        frm.set_value('course', r.course);
                        frm.set_value('instructor', r.faculty);
                        frm.set_value('programme', r.programme);
                        frm.set_value('term', r.term);
                    }
                });
        }
    },

    course: function (frm) {
        frm.events.get_title(frm);
    },

    course_schedule: function (frm) {
        if (frm.doc.course_schedule) {
            frappe.db.get_value("Course Schedule", frm.doc.course_schedule, ["schedule_date", "from_time", "to_time", "room", "class_name", "instructor"], (r) => {
                if (r) {
                    frm.set_value("schedule_date", r.schedule_date);
                    frm.set_value("from_time", r.from_time);
                    frm.set_value("to_time", r.to_time);
                    frm.set_value("venue", r.room);
                    if (r.class_name) frm.set_value("class_name", r.class_name);
                    if (r.instructor) frm.set_value("instructor", r.instructor);
                }
            });
        }
    },

    office_hours_group: function (frm) {
        // Office Hours Group now links to Student Group, which carries no date,
        // time or faculty - only the class context. Setting class_name
        // fetches course, programme, faculty and term from the Class.
        if (frm.doc.office_hours_group) {
            frappe.db.get_value("Student Group", frm.doc.office_hours_group, ["class_name", "programme"], (r) => {
                if (r) {
                    if (r.class_name) frm.set_value("class_name", r.class_name);
                    if (r.programme && !frm.doc.programme) frm.set_value("programme", r.programme);
                }
            });
        }
    },

    class_schedule_color: function (frm) {
        // Map color name to hex color
        const colorMap = {
            'Blue': '#3498db',
            'Green': '#2ecc71',
            'Red': '#e74c3c',
            'Yellow': '#f39c12',
            'Orange': '#e67e22',
            'Purple': '#9b59b6',
            'Pink': '#e91e63',
            'Gray': '#95a5a6'
        };

        if (frm.doc.class_schedule_color && colorMap[frm.doc.class_schedule_color]) {
            frm.set_value('color', colorMap[frm.doc.class_schedule_color]);
        }
    },

    generate_title: function (frm) {
        if (frm.doc.course) {
            let title = frm.doc.course;
            if (frm.doc.venue) {
                title += ' - ' + frm.doc.venue;
            }
            frm.set_value('title', title);
        }
    },

    repeat_frequency: function (frm) {
        if (frm.doc.repeat_frequency === 'Never' || !frm.doc.repeat_frequency) {
            frm.set_value('repeats_till', null);
        }
    },

    validate: function (frm) {
        // Validate repeat settings
        if (frm.doc.repeat_frequency && frm.doc.repeat_frequency !== 'Never') {
            if (!frm.doc.repeats_till) {
                frappe.msgprint(__('Please specify "Repeats Till" date for recurring schedules'));
                frappe.validated = false;
            }
            if (frm.doc.repeats_till && frm.doc.repeats_till < frm.doc.schedule_date) {
                frappe.msgprint(__('Repeats Till date cannot be before Schedule Date'));
                frappe.validated = false;
            }
        }

        // Validate time
        if (frm.doc.from_time && frm.doc.to_time && frm.doc.from_time >= frm.doc.to_time) {
            frappe.msgprint(__('To Time must be after From Time'));
            frappe.validated = false;
        }
    },

    from_time: function (frm) {
        frm.events.calculate_duration(frm);
        frm.events.sync_to_attendance_session(frm);
    },

    to_time: function (frm) {
        frm.events.calculate_duration(frm);
        frm.events.sync_to_attendance_session(frm);
    },

    calculate_duration: function (frm) {
        if (frm.doc.from_time && frm.doc.to_time) {
            // Parse time strings (format: HH:MM:SS)
            const from_parts = frm.doc.from_time.split(':');
            const to_parts = frm.doc.to_time.split(':');

            // Create Date objects for today with the specified times
            const from_date = new Date();
            from_date.setHours(parseInt(from_parts[0]), parseInt(from_parts[1]), parseInt(from_parts[2] || 0), 0);

            const to_date = new Date();
            to_date.setHours(parseInt(to_parts[0]), parseInt(to_parts[1]), parseInt(to_parts[2] || 0), 0);

            // Calculate difference in milliseconds and convert to hours
            const diff_ms = to_date - from_date;
            const hours = Math.floor(diff_ms / (1000 * 60 * 60)); const minutes = Math.floor((diff_ms % (1000 * 60 * 60)) / (1000 * 60)); const duration_hours = hours + (minutes / 100);

            // Set the duration field (rounded to 2 decimal places)
            frm.set_value('duration_hours', parseFloat(duration_hours.toFixed(2)));
        }
    },

    sync_to_attendance_session: function (frm) {
        // Only sync if the document is saved (has a name)
        if (!frm.doc.name || frm.is_new()) {
            return;
        }

        // Only sync if we have valid times
        if (!frm.doc.from_time || !frm.doc.to_time) {
            return;
        }

        // Call server method to update Attendance Session in real-time
        frappe.call({
            method: 'slcm.slcm.doctype.time_table.time_table.update_attendance_session_realtime',
            args: {
                time_table_name: frm.doc.name,
                from_time: frm.doc.from_time,
                to_time: frm.doc.to_time,
                schedule_date: frm.doc.schedule_date,
                duration_hours: frm.doc.duration_hours
            },
            callback: function (r) {
                if (r.message && r.message.success) {
                    frappe.show_alert({
                        message: __('Attendance Session updated'),
                        indicator: 'green'
                    }, 3);
                }
            }
        });
    }
});
