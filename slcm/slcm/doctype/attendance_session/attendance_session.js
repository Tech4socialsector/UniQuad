// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Attendance Session", {

    refresh: function (frm) {
        // Bug 9: Color indicator for session_status
        if (frm.doc.session_status) {
            const color_map = {
                "Scheduled": "blue",
                "Conducted": "green",
                "Cancelled": "red",
                "Postponed": "orange"
            };
            frm.page.set_indicator(frm.doc.session_status, color_map[frm.doc.session_status] || "grey");
        }

        // Bug 8: Toggle field visibility based on based_on value
        toggle_fields_based_on(frm);

        // Bug 11: "Fetch Students" button when class_name or class_schedule is set and doc is saved
        if (!frm.is_new() && (frm.doc.class_name || frm.doc.class_schedule)) {
            frm.add_custom_button(__("Fetch Students"), function () {
                frappe.call({
                    method: "slcm.slcm.doctype.attendance_session.attendance_session.fetch_students_for_session",
                    args: { session_name: frm.doc.name },
                    freeze: true,
                    callback: function (r) {
                        if (r.message) {
                            frappe.show_alert({ message: __(r.message), indicator: "green" });
                            frm.reload_doc();
                        }
                    }
                });
            }, __("Actions"));
        }
    },

    based_on: function (frm) {
        // Bug 8: Re-toggle fields when based_on changes
        toggle_fields_based_on(frm);
    },

    session_start_time: function (frm) {
        frm.events.calculate_duration(frm);
    },

    session_end_time: function (frm) {
        frm.events.calculate_duration(frm);
    },

    calculate_duration: function (frm) {
        if (frm.doc.session_start_time && frm.doc.session_end_time) {
            // Parse time strings (format: HH:MM:SS)
            const start_parts = frm.doc.session_start_time.split(':');
            const end_parts = frm.doc.session_end_time.split(':');

            // Create Date objects for today with the specified times
            const start_date = new Date();
            start_date.setHours(parseInt(start_parts[0]), parseInt(start_parts[1]), parseInt(start_parts[2] || 0), 0);

            const end_date = new Date();
            end_date.setHours(parseInt(end_parts[0]), parseInt(end_parts[1]), parseInt(end_parts[2] || 0), 0);

            // Calculate difference in milliseconds and convert to hours
            const diff_ms = end_date - start_date;

            // Bug 10: Negative duration guard
            if (diff_ms <= 0) {
                frappe.msgprint(__("Session end time must be after start time."));
                frm.set_value("duration_hours", 0);
                return;
            }

            const duration_hours = diff_ms / (1000 * 60 * 60);

            // Set the duration field (rounded to 2 decimal places)
            frm.set_value('duration_hours', parseFloat(duration_hours.toFixed(2)));
        }
    },

});

// Bug 8: Helper to show/hide schedule fields based on based_on value
function toggle_fields_based_on(frm) {
    const based_on = frm.doc.based_on;

    // Class and Time Table sessions both come from a Time Table entry
    frm.toggle_display("class_schedule", based_on === "Class" || based_on === "Time Table");
}
