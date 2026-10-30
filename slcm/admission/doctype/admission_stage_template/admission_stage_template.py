import frappe
from frappe.model.document import Document

class AdmissionStageTemplate(Document):

    def validate(self):
        if not self.stages:
            frappe.throw("At least one stage is required in the template.")
        sequences = [s.sequence for s in self.stages]
        if len(sequences) != len(set(sequences)):
            frappe.throw("Stage sequence numbers must be unique.")
        mandatory_types = ["Application", "Merit", "Enrollment"]
        enabled_types = [s.stage_type for s in self.stages if s.is_enabled]
        for mt in mandatory_types:
            mandatory_stages = [s for s in self.stages if s.stage_type == mt and s.is_mandatory]
            if mandatory_stages:
                if not any(s.stage_type == mt and s.is_enabled for s in self.stages):
                    frappe.throw(f"Stage type '{mt}' is mandatory and cannot be disabled.")
        if self.is_default:
            existing = frappe.db.get_value(
                "Admission Stage Template",
                {"applicable_exam_type": self.applicable_exam_type, "is_default": 1, "name": ("!=", self.name)},
                "name"
            )
            if existing:
                frappe.throw(
                    f"Template '{existing}' is already the default for this exam type. "
                    f"Only one default template allowed per exam type."
                )

    def get_ordered_stages(self):
        return sorted(self.stages, key=lambda s: s.sequence)

    def get_enabled_stages(self):
        return sorted([s for s in self.stages if s.is_enabled], key=lambda s: s.sequence)
