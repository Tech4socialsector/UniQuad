"""Move existing public applicant files (ID proof, marksheets, certificates) to private.

Applicant had make_attachments_public = 1, so documents attached to applications were served
from /files/ to anyone with the link. Each such file becomes private; the field that referenced
the old /files/ URL is pointed at the new /private/files/ URL. A file that can't be moved (missing
on disk, name clash) is logged and left as it is.
"""

import frappe

from slcm.security.files import APPLICANT_DOCTYPES


def execute():
	files = frappe.get_all(
		"File",
		filters={"is_private": 0, "is_folder": 0, "attached_to_doctype": ["in", APPLICANT_DOCTYPES]},
		fields=["name", "file_url", "attached_to_doctype", "attached_to_name", "attached_to_field"],
	)
	moved = failed = 0
	for row in files:
		if not (row.file_url or "").startswith("/files/"):
			continue
		try:
			f = frappe.get_doc("File", row.name)
			_rename_if_private_name_taken(f)
			f.is_private = 1
			f.flags.ignore_permissions = True
			f.save()
			if row.attached_to_field and frappe.db.exists(row.attached_to_doctype, row.attached_to_name):
				current = frappe.db.get_value(row.attached_to_doctype, row.attached_to_name, row.attached_to_field)
				if current == row.file_url:
					frappe.db.set_value(row.attached_to_doctype, row.attached_to_name, row.attached_to_field,
						f.file_url, update_modified=False)
			frappe.db.commit()
			moved += 1
		except Exception:
			frappe.db.rollback()
			failed += 1
			frappe.log_error(title=f"make_applicant_files_private: {row.name}", message=frappe.get_traceback())
	if files:
		print(f"Applicant files made private: {moved}, failed (see Error Log): {failed}")


def _rename_if_private_name_taken(f):
	"""Common names (photo.jpg, aadhaar.pdf) often already exist in private/files; Frappe refuses to
	move onto them, so the public file first gets a unique name."""
	import os

	file_name = f.file_url.split("/")[-1]
	if not os.path.exists(frappe.get_site_path("private", "files", file_name)):
		return
	stem, ext = os.path.splitext(file_name)
	new_name = f"{stem}-{frappe.generate_hash(length=6)}{ext}"
	os.rename(frappe.get_site_path("public", "files", file_name), frappe.get_site_path("public", "files", new_name))
	old_url = f.file_url
	f.file_url = f"/files/{new_name}"
	f.db_set("file_url", f.file_url, update_modified=False)
	if f.attached_to_field and frappe.db.get_value(f.attached_to_doctype, f.attached_to_name, f.attached_to_field) == old_url:
		frappe.db.set_value(f.attached_to_doctype, f.attached_to_name, f.attached_to_field, f.file_url, update_modified=False)
