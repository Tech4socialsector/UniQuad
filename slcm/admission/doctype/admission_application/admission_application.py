import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AdmissionApplication(Document):

    def before_insert(self):
        """Set defaults on creation"""
        if not self.application_date:
            self.application_date = frappe.utils.today()

    def validate(self):
        """Validate before save"""
        self._validate_single_application()
        self._validate_cycle_active()

    def _validate_single_application(self):
        """Prevent duplicate applications for same program+cycle"""
        if self.is_new():
            existing = frappe.db.get_value(
                "Admission Application",
                {
                    "applicant": self.applicant,
                    "program": self.program,
                    "admission_cycle": self.admission_cycle,
                    "docstatus": ["!=", 2],  # not cancelled
                },
                "name"
            )
            if existing:
                frappe.throw(
                    f"An application already exists for this program and cycle: {existing}",
                    title="Duplicate Application"
                )

    def _validate_cycle_active(self):
        """Warn if cycle is not active"""
        if self.admission_cycle:
            status = frappe.db.get_value(
                "Admission Cycle", self.admission_cycle, "status"
            )
            if status not in ("Active", "Draft"):
                frappe.msgprint(
                    f"Admission Cycle '{self.admission_cycle}' is '{status}'. "
                    "Applications may not be accepted.",
                    alert=True
                )

    def on_submit(self):
        """Actions on submission"""
        self.submitted_on = now_datetime()
        self.status = "Submitted"
        self.db_set("submitted_on", self.submitted_on)
        self.db_set("status", "Submitted")

        # Increment application_count count on Admission Cycle Program
        self._increment_received_count()

        # Create notification for applicant
        self._notify_applicant("Application Submitted",
            f"Your application {self.name} for {self.program_name or self.program} "
            f"has been successfully submitted.")

    def on_cancel(self):
        """Actions on cancel"""
        self.status = "Withdrawn"
        self.db_set("status", "Withdrawn")
        self._decrement_received_count()

    def _increment_received_count(self):
        try:
            cp = frappe.db.get_value(
                "Admission Cycle Program",
                {"parent": self.admission_cycle, "program": self.program},
                ["name", "application_count"],
                as_dict=True
            )
            if cp:
                new_count = int(cp.application_count or 0) + 1
                frappe.db.set_value(
                    "Admission Cycle Program", cp.name,
                    "application_count", new_count
                )
                frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"increment application_count failed: {e}",
                           "Admission Application")

    def _decrement_received_count(self):
        try:
            cp = frappe.db.get_value(
                "Admission Cycle Program",
                {"parent": self.admission_cycle, "program": self.program},
                ["name", "application_count"],
                as_dict=True
            )
            if cp:
                new_count = max(0, int(cp.application_count or 0) - 1)
                frappe.db.set_value(
                    "Admission Cycle Program", cp.name,
                    "application_count", new_count
                )
                frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"decrement application_count failed: {e}",
                           "Admission Application")

    def _notify_applicant(self, title, message):
        try:
            # Find applicant record for this application's applicant field
            if self.applicant:
                notif = frappe.new_doc("Applicant Notification")
                notif.applicant     = self.applicant
                notif.notification_type = title
                notif.message       = message
                notif.is_read       = 0
                notif.created_on    = now_datetime()
                notif.insert(ignore_permissions=True)
                frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"notify applicant failed: {e}",
                           "Admission Application")
