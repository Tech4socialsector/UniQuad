"""Applicant uploads (ID proof, marksheets, certificates, photos) are always private files.

The portal asks for private uploads, but that flag comes from the browser; this makes it a
server rule:

- File before_insert (hooks.py): a file attached to an applicant record, or uploaded by an
  applicant, is stored under /private/files.
- Applicant before_validate (hooks.py): any attach field still pointing at a public /files/ URL
  (desk "attach from library", copied values, API writes) is switched to a private copy.
"""

import os

import frappe

from slcm.security.access import is_applicant_only

# Records that hold applicant documents.
APPLICANT_DOCTYPES = ("Applicant", "Applicant Document", "Scholarship Application", "Admission Cancellation",
                      "Refund Request")

_ATTACH_TYPES = ("Attach", "Attach Image")


def _public_path(file_url):
	return frappe.get_site_path("public", "files", file_url.split("/")[-1])


def make_applicant_upload_private(doc, method=None):
	"""File before_insert. Runs after File.before_insert has already written the content, so a
	public upload is rewritten as a private file rather than just flagged (flagging alone leaves
	the content in /files/ and fails File URL validation)."""
	if doc.is_folder or doc.is_remote_file:
		return
	if not (is_applicant_only() or doc.attached_to_doctype in APPLICANT_DOCTYPES):
		return

	url = doc.file_url or ""
	if not url or url.startswith("/private/files/"):
		doc.is_private = 1
		return
	if not url.startswith("/files/"):
		return

	public_path = _public_path(url)
	content = getattr(doc, "_content", None)
	if not content:
		if not os.path.exists(public_path):
			frappe.throw(frappe._("Cannot find file {0} on disk").format(url))
		with open(public_path, "rb") as fh:
			content = fh.read()

	# Remove the public copy only if this upload just created it; a public file that another
	# File record already points to (duplicate content, attach-from-library) is left alone.
	shared = frappe.db.exists("File", {"file_url": url})
	if doc.flags.new_file and not shared and os.path.exists(public_path):
		os.remove(public_path)

	doc.is_private = 1
	doc.file_url = None
	doc.flags.new_file = True  # save_file must not try to read "original content" from file_url
	doc.save_file(content=content)


def _private_copy(file_url, applicant, fieldname):
	# No is_private here: Frappe rejects is_private=1 with a /files/ URL before hooks run.
	# make_applicant_upload_private (File before_insert) writes the private copy.
	f = frappe.get_doc({
		"doctype": "File",
		"file_url": file_url,
		"attached_to_doctype": "Applicant",
		"attached_to_name": applicant,
		"attached_to_field": fieldname,
	})
	f.flags.ignore_permissions = True
	f.insert()
	return f.file_url


def make_applicant_attachments_private(doc, method=None):
	"""Applicant before_validate: point every attach field (parent and child rows) at a private
	file. Runs on every save, including portal drafts saved with ignore_validate."""
	if not doc.name:
		return
	rows = [doc]
	for df in doc.meta.get_table_fields():
		rows.extend(doc.get(df.fieldname) or [])
	for row in rows:
		for df in row.meta.fields:
			if df.fieldtype not in _ATTACH_TYPES:
				continue
			url = row.get(df.fieldname)
			if not url or not url.startswith("/files/"):
				continue
			if not os.path.exists(_public_path(url)):
				continue  # nothing to copy; leave as is rather than fail the save
			try:
				row.set(df.fieldname, _private_copy(url, doc.name, df.fieldname))
			except Exception:
				frappe.log_error(
					title=f"Applicant {doc.name}: could not make {df.fieldname} private",
					message=frappe.get_traceback(),
				)
