import frappe
from frappe.model.document import Document

class AdmissionAuditLog(Document):
    def on_trash(self):
        frappe.throw(
            "Admission Audit Logs cannot be deleted. They are legally required records.",
            title="Deletion Not Allowed"
        )