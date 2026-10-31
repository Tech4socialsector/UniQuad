import frappe
from frappe.model.document import Document

PLACEHOLDER_MAP = {
    "Application Submitted": "{{candidate_name}}, {{program}}, {{campus}}, {{applicant_id}}, {{submission_date}}",
    "Status Changed":        "{{candidate_name}}, {{program}}, {{campus}}, {{applicant_id}}, {{status}}, {{old_status}}",
    "Offer Sent":            "{{candidate_name}}, {{program}}, {{campus}}, {{applicant_id}}, {{offer_amount}}, {{deadline}}",
    "Document Rejected":     "{{candidate_name}}, {{program}}, {{document_name}}, {{rejection_reason}}",
    "Deadline Reminder":     "{{candidate_name}}, {{program}}, {{deadline}}, {{action_required}}",
    "Interview Scheduled":   "{{candidate_name}}, {{program}}, {{campus}}, {{interview_date}}, {{interview_time}}, {{location}}",
    "Payment Confirmed":     "{{candidate_name}}, {{program}}, {{campus}}, {{amount_paid}}, {{transaction_id}}, {{receipt_number}}"
}

class EmailTemplateConfig(Document):

    def validate(self):
        self._set_available_placeholders()
        self._validate_no_duplicate_active_trigger()

    def _set_available_placeholders(self):
        if self.trigger_event:
            self.available_placeholders = PLACEHOLDER_MAP.get(
                self.trigger_event,
                "{{candidate_name}}, {{program}}, {{applicant_id}}"
            )

    def _validate_no_duplicate_active_trigger(self):
        if self.is_active and self.trigger_event:
            existing = frappe.db.get_value(
                "Email Template Config",
                {
                    "trigger_event": self.trigger_event,
                    "is_active": 1,
                    "name": ("!=", self.name or "")
                },
                "name"
            )
            if existing:
                frappe.msgprint(
                    f"Warning: Template '{existing}' is also active for "
                    f"'{self.trigger_event}'. Only one active template per "
                    f"trigger event is recommended.",
                    indicator="orange",
                    alert=True
                )

    def render(self, context):
        """
        Renders subject and body with given context dict.
        Returns dict with rendered subject and body.
        """
        subject = self.subject or ""
        body = self.body or ""
        for key, value in context.items():
            subject = subject.replace("{{" + key + "}}", str(value or ""))
            body = body.replace("{{" + key + "}}", str(value or ""))
        return {"subject": subject, "body": body}

    @staticmethod
    def get_active_template(trigger_event):
        """
        Returns the active Email Template Config for a given trigger event.
        """
        name = frappe.db.get_value(
            "Email Template Config",
            {"trigger_event": trigger_event, "is_active": 1},
            "name"
        )
        if name:
            return frappe.get_doc("Email Template Config", name)
        return None

    @staticmethod
    def send(trigger_event, recipient_email, context):
        """
        Central email sending method.
        """
        template = EmailTemplateConfig.get_active_template(trigger_event)
        if not template:
            frappe.log_error(
                f"No active Email Template Config for trigger: {trigger_event}",
                "Email Template Missing"
            )
            return False
        rendered = template.render(context)
        frappe.sendmail(
            recipients=[recipient_email],
            sender=frappe.db.get_value("Email Account", template.get("email_account"), "email_id") if template.get("email_account") else None,
            subject=rendered["subject"],
            message=rendered["body"],
            now=True
        )
        return True

@frappe.whitelist()
def send_test_email(template_name, recipient):
    doc = frappe.get_doc("Email Template Config", template_name)
    # Use generic placeholders for test
    context = {
        "candidate_name": "Test Candidate",
        "program": "Test Program",
        "campus": "Main Campus",
        "applicant_id": "APP-TEST-001",
        "status": "Verified",
        "old_status": "Draft",
        "deadline": "2025-12-31",
        "offer_amount": "50,000",
        "document_name": "ID Card",
        "rejection_reason": "Blurry image",
        "action_required": "Please re-upload",
        "interview_date": "2025-06-01",
        "interview_time": "10:00 AM",
        "location": "Online (Zoom)",
        "amount_paid": "1,000",
        "transaction_id": "TXN12345",
        "receipt_number": "REC-001",
        "submission_date": "2025-01-01"
    }
    return doc.send(doc.trigger_event, recipient, context)
