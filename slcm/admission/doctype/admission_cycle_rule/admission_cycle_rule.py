import frappe
from frappe.model.document import Document

class AdmissionCycleRule(Document):

    def validate(self):
        if not self.rule_value:
            frappe.throw("Rule Value is required.")
        if self.rule_type == "offer_validity_period":
            try:
                days = int(self.rule_value)
                if days <= 0:
                    frappe.throw("Offer validity period must be a positive number of days.")
            except ValueError:
                frappe.throw("For offer_validity_period, rule value must be a number (days).")

    def get_rule_value(self):
        return self.rule_value

    @staticmethod
    def get_cycle_rule(cycle_name, rule_type):
        name = frappe.db.get_value(
            "Admission Cycle Rule",
            {"admission_cycle": cycle_name, "rule_type": rule_type},
            "name"
        )
        if name:
            return frappe.get_doc("Admission Cycle Rule", name)
        return None
