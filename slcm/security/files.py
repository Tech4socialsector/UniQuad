"""Applicant uploads (ID proof, marksheets, certificates, photos) are always private files.

The portal asks for private uploads, but that flag comes from the browser; this makes it a
server rule. Registered in hooks.py as a File before_insert event.
"""

import frappe

from slcm.security.access import is_applicant_only

# Records that hold applicant documents.
APPLICANT_DOCTYPES = ("Applicant", "Applicant Document", "Scholarship Application", "Admission Cancellation",
                      "Refund Request")


def make_applicant_upload_private(doc, method=None):
	if doc.is_folder or doc.is_remote_file:
		return
	if is_applicant_only() or doc.attached_to_doctype in APPLICANT_DOCTYPES:
		doc.is_private = 1
