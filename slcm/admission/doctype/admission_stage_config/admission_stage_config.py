import frappe
from frappe.model.document import Document
from slcm.admission.utils.stage_engine import can_unlock_next_stage

class AdmissionStageConfig(Document):
    def validate(self):
        # Block changes if stage is locked (applicants exist or cycle is Active)
        # unless user is System Manager
        if not frappe.utils.cint(frappe.db.get_single_value("Admission Settings", "bypass_stage_lock")):
            cycle_status = frappe.db.get_value("Admission Cycle", self.admission_cycle, "status")
            if cycle_status == "Active" or self.is_stage_locked:
                if "System Manager" not in frappe.get_roles():
                    frappe.throw(
                        "Admission Stage Config cannot be modified after cycle is Active or if stage is locked. "
                        "Contact System Manager for changes.",
                        title="Stage Locked"
                    )

        self.validate_unique_sequence()
        self.validate_disable_with_applicants()

    def validate_unique_sequence(self):
        existing = frappe.db.exists("Admission Stage Config", {
            "admission_cycle": self.admission_cycle,
            "sequence": self.sequence,
            "name": ["!=", self.name]
        })
        if existing:
            frappe.throw(
                f"Sequence {self.sequence} already exists for this cycle.",
                title="Duplicate Sequence"
            )

    def validate_disable_with_applicants(self):
        if not self.is_enabled:
            applicants_in_stage = frappe.db.count("Applicant", {
                "admission_cycle": self.admission_cycle,
                "status": self.stage_name
            })
            if applicants_in_stage > 0:
                frappe.throw(
                    f"Cannot disable stage <b>{self.stage_name}</b>. "
                    f"{applicants_in_stage} applicant(s) are currently in this stage.",
                    title="Stage Has Applicants"
                )

    def on_update(self):
        # Logic to handle side effects of stage updates
        pass
