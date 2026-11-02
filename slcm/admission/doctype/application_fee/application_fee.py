
import frappe
from frappe import _
from frappe.model.document import Document


class ApplicationFee(Document):

    def before_save(self):

        filters = {
            "academic_year": self.academic_year,
            "name": ["!=", self.name],
        }

        if frappe.db.exists("Application Fee", filters):
            frappe.throw(
                _("An  application fee already exists for this academic year.")
            )

    def validate(self):
        selected_categories = []

        for row in self.application_fee_by_category:
            if not row.admission_category:
                continue

            if row.admission_category in selected_categories:
                frappe.throw(
                    _("Admission Category {0} is selected more than once.").format(
                        row.admission_category
                    )
                )

            selected_categories.append(row.admission_category)
