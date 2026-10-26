frappe.ui.form.on("Applicant Reminder Email Configuration", {
    refresh(frm) {
        frm.add_custom_button(__("Send Reminders Now"), function () {
            _trigger_manual_reminders(frm, false);
        }, __("Actions"));
        frm.add_custom_button(__("Send Rejected Email"), function () {
            _trigger_manual_reminders(frm, true);
        }, __("Actions"));
    }
});

function _trigger_manual_reminders(frm, is_rejection_only = false) {
    // Collect which reminders are Active
    const reminder_fields = [
        "enable_not_started_reminder",
        "enable_draft_reminder",
        "enable_unpaid_fee_reminder",
        "enable_admission_fee_reminder",
        "enable_confirmation_fee_reminder"
    ];

    const active_reminders = reminder_fields.filter(f => frm.doc[f] === "Active");

    if (!active_reminders.length) {
        frappe.msgprint({
            title: __("No Active Reminders"),
            message: __("Please activate at least one reminder type before triggering."),
            indicator: "orange"
        });
        return;
    }

    frappe.confirm(
        is_rejection_only 
            ? __("This will immediately send rejection emails to all eligible applicants whose cycle has ended. Do you want to continue?")
            : __("This will immediately send reminder emails to all eligible applicants for the selected active reminder types. Do you want to continue?"),
        function () {
            frappe.call({
                method: "slcm.admission.doctype.applicant_reminder_email_configuration.applicant_reminder_email_configuration.trigger_manual_reminders",
                args: { reminders: active_reminders, is_rejection_only: is_rejection_only },
                freeze: true,
                freeze_message: __("Queuing task..."),
                callback(r) {
                    frappe.show_alert({
                        message: r.message.message || __("Reminder emails are being processed in the background."),
                        indicator: "green"
                    }, 5);
                },
                error() {
                    frappe.msgprint({
                        title: __("Error"),
                        message: __("An error occurred while queuing the reminders. Please check the Error Log for details."),
                        indicator: "red"
                    });
                }
            });
        }
    );
}
