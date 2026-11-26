# Copyright (c) 2026, SLCM and contributors
# License: MIT

import frappe
from frappe.model.document import Document


class ApplicantPortalConfig(Document):
    def validate(self):
        from slcm.admission.utils.auth_emails import validate_portal_templates

        validate_portal_templates(self)
