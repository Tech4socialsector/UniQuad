
import frappe
from frappe import _
from frappe.model.document import Document


class ApplicationFee(Document):
    # Several Application Fees may exist for one Academic Year; each Admission Cycle
    # programme row picks the one it uses.

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
