frappe.views.calendar["Time Table"] = {
    field_map: {
        start: "start",
        end: "end",
        id: "name",
        title: "title",
        allDay: "allDay",
        color: "color",
        // get_events() already returns naive local wall-clock times
        // ("schedule_date from_time"), not UTC - skip Frappe's default
        // system-tz -> user-tz re-projection or the tile renders at the
        // wrong time whenever the viewer's personal timezone differs from
        // System Settings (e.g. class entered as 9:00 AM shows as 2:30 PM).
        convertToUserTz: "convertToUserTz",
    },
    get_events_method: "slcm.slcm.doctype.time_table.time_table.get_events",
    update_event_method: "slcm.slcm.doctype.time_table.time_table.update_event",
    options: {
        editable: true,
        eventClick: function (info) {
            // Institutional Calendar markers (holidays, exams, etc.) aren't
            // Time Table records - clicking them shouldn't navigate anywhere.
            if (info.event.extendedProps && info.event.extendedProps.institutional_calendar) {
                return;
            }
            show_time_table_event_details(info.event);
        },
        select: function (startDate, endDate, jsEvent, view) {
            // Prevent single day click in month view
            if (view.name === "month" && endDate - startDate === 86400000) {
                return;
            }

            // Create new Time Table document
            var new_doc = frappe.model.get_new_doc("Time Table");

            // Extract date and time from startDate
            var start_moment = moment(startDate);
            new_doc.schedule_date = start_moment.format("YYYY-MM-DD");
            new_doc.from_time = start_moment.format("HH:mm:ss");

            // Extract end time from endDate
            if (endDate) {
                var end_moment = moment(endDate);
                new_doc.to_time = end_moment.format("HH:mm:ss");
            }

            // Navigate to the new form
            frappe.set_route("Form", "Time Table", new_doc.name);
        }
    },
};

function show_time_table_event_details(event) {
    const props = event.extendedProps || {};

    const format_time = (t) => (t ? moment(t, "HH:mm:ss").format("hh:mm A") : "-");

    const rows = [
        ["Based On", props.based_on],
        ["Time", `${format_time(props.from_time)} - ${format_time(props.to_time)}`],
        ["Duration", props.duration_hours ? `${props.duration_hours} hr` : "-"],
        ["Course", props.course],
        ["Class", props.class_name],
        ["Faculty", props.instructor],
        ["Venue", props.venue],
    ];

    if (props.based_on === "Office Hours" && props.office_hours_group) {
        rows.push(["Office Hours Group", props.office_hours_group]);
    }

    const html = rows
        .filter(([, value]) => value)
        .map(
            ([label, value]) =>
                `<div style="display:flex;padding:6px 0;border-bottom:1px solid var(--border-color);">
                    <div style="width:150px;color:var(--text-muted);font-weight:600;">${__(label)}</div>
                    <div>${frappe.utils.escape_html(String(value))}</div>
                </div>`
        )
        .join("");

    const dialog = new frappe.ui.Dialog({
        title: event.title,
        fields: [{ fieldtype: "HTML", options: html }],
        primary_action_label: __("Open"),
        primary_action: function () {
            dialog.hide();
            if (frappe.model.can_read("Time Table")) {
                frappe.set_route("Form", "Time Table", event.id);
            }
        },
    });

    // "Apply to Future" only makes sense on the full form, where the venue /
    // time change and its conflict check are visible together with the doc -
    // keep this popover a quick-view and point users to the form for it.
    dialog.set_secondary_action_label(__("Open & Edit Future Occurrences"));
    dialog.set_secondary_action(function () {
        dialog.hide();
        if (frappe.model.can_write("Time Table")) {
            frappe.set_route("Form", "Time Table", event.id);
        }
    });

    dialog.show();
}
