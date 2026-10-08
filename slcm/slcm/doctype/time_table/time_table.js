// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on('Time Table', {
    refresh: function (frm) {
        // Auto-generate title if not set
        if (!frm.doc.title && frm.doc.course) {
            frm.trigger('generate_title');
        }

        if (!frm.is_new()) {
            frm.add_custom_button(__('Mark Attendance'), function () {
                frappe.route_options = {
                    'based_on': frm.doc.based_on || 'Time Table',
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
        }
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

    course_offering: function (frm) {
        if (frm.doc.course_offering) {
            frappe.db.get_value("Course Offering", frm.doc.course_offering, ["course_title", "program", "faculty", "term_name"], (r) => {
                if (r) {
                    frm.set_value("course", r.course_title);
                    frm.set_value("programme", r.program);
                    if (r.faculty) frm.set_value("instructor", r.faculty);
                    if (r.term_name) frm.set_value("term", r.term_name);
                }
            });
        }
    },

    course_schedule: function (frm) {
        if (frm.doc.course_schedule) {
            frappe.db.get_value("Course Schedule", frm.doc.course_schedule, ["schedule_date", "from_time", "to_time", "room", "course_offering", "instructor"], (r) => {
                if (r) {
                    frm.set_value("schedule_date", r.schedule_date);
                    frm.set_value("from_time", r.from_time);
                    frm.set_value("to_time", r.to_time);
                    frm.set_value("venue", r.room);
                    if (r.course_offering) frm.set_value("course_offering", r.course_offering);
                    if (r.instructor) frm.set_value("instructor", r.instructor);
                }
            });
        }
    },

    office_hours_group: function (frm) {
        if (frm.doc.office_hours_group) {
            frappe.db.get_value("Office Hours Group", frm.doc.office_hours_group, ["date", "from_time", "to_time", "course_offering", "instructor"], (r) => {
                if (r) {
                    frm.set_value("schedule_date", r.date);
                    frm.set_value("from_time", r.from_time);
                    frm.set_value("to_time", r.to_time);
                    if (r.course_offering) frm.set_value("course_offering", r.course_offering);
                    if (r.instructor) frm.set_value("instructor", r.instructor);
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
