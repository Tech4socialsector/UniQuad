"""Fee Certificates page: generate one certificate or many (campus students, in batches),
list / preview / download them, upload an edited copy, and download many as one ZIP."""

import zipfile
from io import BytesIO

import frappe
from frappe import _
from frappe.utils import cint

from slcm.slcm.page.student_fee_management.student_fee_management import (
	_as_list,
	_check_access,
	get_filter_options as _student_filter_options,
)

# Largest selection one bulk download / bulk generate request accepts.
BULK_LIMIT = 1000
# Up to this many certificates are zipped in the request itself; more go to a background job.
SYNC_ZIP_LIMIT = 15


@frappe.whitelist()
def get_fee_certificate_options():
	_check_access()
	from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import get_purpose_options

	student_options = _student_filter_options()
	return {
		"purposes": get_purpose_options(),
		"academic_years": frappe.get_all("Academic Year", pluck="name", order_by="year_start_date desc"),
		# For the list filters and for picking students to bulk generate
		"student_years": student_options["academic_years"],
		"terms": student_options["terms"],
		"programmes": student_options["programmes"],
		"batches": frappe.db.sql_list(
			"""SELECT DISTINCT batch FROM `tabStudent Master` WHERE IFNULL(batch, '') != '' ORDER BY batch"""
		),
	}


@frappe.whitelist()
def generate_fee_certificate(
	certificate_for, purpose, academic_year, student=None, applicant=None, has_scholarship=1, admit_card_number=None
):
	"""Create (or reuse) the Fee Certificate Request and return its name for download."""
	_check_access()
	is_applicant = certificate_for == "Admission Stage"
	person_field = "applicant" if is_applicant else "student"
	person = applicant if is_applicant else student
	if not person:
		frappe.throw(_("Please select the Applicant") if is_applicant else _("Please select the Student"))

	name = frappe.db.get_value(
		"Fee Certificate Request",
		{
			person_field: person,
			"certificate_for": certificate_for,
			"purpose": purpose,
			"from_academic_year": academic_year,
			"status": ["!=", "Cancelled"],
		},
		"name",
	)
	doc = (
		frappe.get_doc("Fee Certificate Request", name)
		if name
		else frappe.new_doc("Fee Certificate Request").update(
			{
				"certificate_for": certificate_for,
				person_field: person,
				"purpose": purpose,
				"from_academic_year": academic_year,
				"remarks": _("Generated from Fee Certificates."),
			}
		)
	)
	doc.has_scholarship = cint(has_scholarship)
	if is_applicant and admit_card_number:
		doc.admit_card_number = admit_card_number
	doc.set("years", [])  # rebuilt from the latest fee data
	doc.flags.ignore_permissions = True
	doc.save()
	doc.db_set({"status": "Generated", "generated_on": frappe.utils.now_datetime()})
	return doc.name


@frappe.whitelist()
def download_fee_certificate(name, file_format="pdf"):
	"""file_format: pdf (the uploaded edited copy if any, else generated), generated, docx."""
	_check_access()
	from slcm.slcm.doctype.fee_certificate_request.fee_certificate_request import certificate_file

	filename, content, response_type = certificate_file(frappe.get_doc("Fee Certificate Request", name), file_format)
	frappe.local.response.update(filename=filename, filecontent=content, type=response_type)


@frappe.whitelist()
def set_edited_certificate(name, file_url=None):
	"""Attach (or, with no file_url, remove) the staff-edited certificate. A Word
	(.docx) upload is converted to PDF; the Word file is kept for later edits."""
	_check_access()
	doc = frappe.get_doc("Fee Certificate Request", name)
	word_url = None
	if file_url:
		lower = file_url.lower()
		if not lower.endswith((".pdf", ".docx")):
			frappe.throw(_("Please upload the certificate as a PDF or Word (.docx) file."))
		uploaded = frappe.db.get_value(
			"File",
			{"file_url": file_url, "attached_to_doctype": "Fee Certificate Request", "attached_to_name": name},
			"name",
		)
		if not uploaded:
			frappe.throw(_("The uploaded file is not attached to {0}.").format(name))
		# Tag the file with its field, so saving the request doesn't register it a second time.
		frappe.db.set_value(
			"File", uploaded, "attached_to_field", "edited_word_file" if lower.endswith(".docx") else "edited_certificate"
		)
		if lower.endswith(".docx"):
			from slcm.slcm.doctype.fee_certificate_request.fee_certificate_docx import docx_to_pdf

			try:
				pdf = docx_to_pdf(frappe.get_doc("File", uploaded).get_content())
			except Exception:
				frappe.log_error(title=f"Fee certificate Word to PDF failed: {name}")
				frappe.throw(_("The Word file could not be converted to PDF. Please save it as PDF in Word and upload the PDF."))
			pdf_file = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": f"{name} - edited.pdf",
					"content": pdf,
					"is_private": 1,
					"attached_to_doctype": "Fee Certificate Request",
					"attached_to_name": name,
					"attached_to_field": "edited_certificate",
				}
			).insert(ignore_permissions=True)
			word_url, file_url = file_url, pdf_file.file_url
	doc.edited_certificate = file_url or None
	doc.edited_word_file = word_url
	doc.flags.ignore_permissions = True
	doc.save()
	return {"edited_certificate": doc.edited_certificate, "edited_on": doc.edited_on, "converted": bool(word_url)}


@frappe.whitelist()
def get_fee_certificates(
	academic_year=None,
	programme=None,
	certificate_for=None,
	purpose=None,
	search=None,
	certificate_search=None,
	start=0,
	page_length=25,
	names_only=0,
):
	"""Generated fee certificates (campus students and applicants), newest first;
	Draft requests that were never downloaded are left out.
	names_only: every matching certificate name (for "download all matching")."""
	_check_access()
	conditions = ["fcr.status = 'Generated'"]
	values = {}
	for param, column, key in (
		(academic_year, "fcr.from_academic_year", "academic_year"),
		(programme, "fcr.programme", "programme"),
		(certificate_for, "fcr.certificate_for", "certificate_for"),
		(purpose, "fcr.purpose", "purpose"),
	):
		selected = _as_list(param)
		if selected:
			conditions.append(f"{column} IN %({key})s")
			values[key] = tuple(selected)
	if search and search.strip():
		conditions.append(
			"(fcr.name LIKE %(search)s OR fcr.student_name LIKE %(search)s OR fcr.student LIKE %(search)s "
			"OR fcr.applicant LIKE %(search)s OR fcr.registration_id LIKE %(search)s "
			"OR fcr.application_number LIKE %(search)s OR fcr.purpose LIKE %(search)s)"
		)
		values["search"] = f"%{search.strip()}%"
	# The tab's own box: student / applicant name, ID or application number.
	if certificate_search and certificate_search.strip():
		conditions.append(
			"(fcr.student_name LIKE %(cert_search)s OR fcr.student LIKE %(cert_search)s "
			"OR fcr.applicant LIKE %(cert_search)s OR fcr.registration_id LIKE %(cert_search)s "
			"OR fcr.application_number LIKE %(cert_search)s OR fcr.name LIKE %(cert_search)s)"
		)
		values["cert_search"] = f"%{certificate_search.strip()}%"
	where = " AND ".join(conditions)

	if cint(names_only):
		return frappe.db.sql_list(
			f"""SELECT fcr.name FROM `tabFee Certificate Request` fcr WHERE {where}
			ORDER BY COALESCE(fcr.generated_on, fcr.creation) DESC, fcr.name DESC LIMIT {BULK_LIMIT}""",
			values,
		)

	count = frappe.db.sql(f"SELECT COUNT(*) FROM `tabFee Certificate Request` fcr WHERE {where}", values)[0][0]
	values.update(start=cint(start), page_length=min(cint(page_length) or 25, 500))
	rows = frappe.db.sql(
		f"""SELECT fcr.name, fcr.certificate_for, fcr.student, fcr.applicant, fcr.student_name,
			COALESCE(NULLIF(fcr.registration_id, ''), NULLIF(fcr.application_number, ''), fcr.student, fcr.applicant) AS person_id,
			fcr.admit_card_number, fcr.programme, fcr.purpose, fcr.from_academic_year AS academic_year,
			fcr.status, fcr.generated_on, fcr.creation, fcr.owner, fcr.remarks,
			fcr.edited_certificate, fcr.edited_on, fcr.edited_by
		FROM `tabFee Certificate Request` fcr
		WHERE {where}
		ORDER BY COALESCE(fcr.generated_on, fcr.creation) DESC, fcr.name DESC
		LIMIT %(start)s, %(page_length)s""",
		values,
		as_dict=True,
	)
	for r in rows:
		r["source"] = "Student Portal" if "student portal" in (r.remarks or "").lower() else "Staff"
	return {"rows": rows, "count": count}


# ─────────────────────────────────────────────────────────────────────────────
# Bulk generation — campus students picked by programme / batch / year / term
# ─────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_bulk_students(programme=None, batch=None, academic_year=None, academic_term=None, search=None, active_only=1):
	"""Students matching the Bulk Generate filters (the dialog lists them to confirm)."""
	_check_access()
	conditions = ["1=1"]
	values = {}
	for param, column, key in (
		(programme, "programme_of_study", "programme"),
		(batch, "batch", "batch"),
		(academic_year, "academic_year", "academic_year"),
		(academic_term, "academic_term", "academic_term"),
	):
		selected = _as_list(param)
		if selected:
			conditions.append(f"{column} IN %({key})s")
			values[key] = tuple(selected)
	if cint(active_only):
		conditions.append("IFNULL(student_status, 'Active') = 'Active'")
	if search and search.strip():
		conditions.append("(name LIKE %(search)s OR first_name LIKE %(search)s OR registration_id LIKE %(search)s)")
		values["search"] = f"%{search.strip()}%"
	return frappe.db.sql(
		f"""SELECT name, first_name, registration_id, programme_of_study, batch, academic_year
		FROM `tabStudent Master` WHERE {" AND ".join(conditions)}
		ORDER BY first_name, name LIMIT {BULK_LIMIT + 1}""",
		values,
		as_dict=True,
	)


@frappe.whitelist()
def bulk_generate_fee_certificates(students, purpose, academic_year, has_scholarship=1):
	"""Generate (or refresh) a campus-student certificate for each student. The page sends
	students in small batches so it can show progress; one student's error doesn't stop the rest."""
	_check_access()
	students = _as_list(students)
	if len(students) > BULK_LIMIT:
		frappe.throw(_("Select at most {0} students at a time.").format(BULK_LIMIT))
	results = []
	for student in students:
		try:
			frappe.db.savepoint("fee_certificate_bulk")
			name = generate_fee_certificate("Campus Student", purpose, academic_year, student=student, has_scholarship=has_scholarship)
			results.append({"student": student, "certificate": name})
		except Exception as e:
			frappe.db.rollback(save_point="fee_certificate_bulk")
			frappe.clear_messages()
			results.append({"student": student, "error": frappe.utils.strip_html(str(e)) or _("Could not generate")})
	return results


# ─────────────────────────────────────────────────────────────────────────────
# Bulk download — one ZIP of many certificates
# ─────────────────────────────────────────────────────────────────────────────


def _build_zip(names, file_format, on_progress=None):
	"""ZIP of the certificates (edited copy when uploaded, for PDF). Returns (bytes, errors)."""
	from slcm.slcm.doctype.fee_certificate_request.fee_certificate_request import certificate_file

	buf = BytesIO()
	errors = []
	used = set()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
		for i, name in enumerate(names, 1):
			try:
				request = frappe.get_doc("Fee Certificate Request", name)
				filename, content, _type = certificate_file(request, file_format)
				# "<certificate no> - <purpose> - <name> - <student ID>.pdf": the number first keeps
				# names unique and sorted; the ID tells apart students who share a name.
				stem, ext = filename.rsplit(".", 1)
				person_id = request.registration_id or request.application_number or request.student or request.applicant
				arcname = f"{name} - {stem}{f' - {person_id}' if person_id else ''}.{ext}".replace("/", "-")
				while arcname in used:
					arcname = f"_{arcname}"
				used.add(arcname)
				zf.writestr(arcname, content)
			except Exception as e:
				frappe.clear_messages()
				errors.append({"certificate": name, "error": frappe.utils.strip_html(str(e))})
			if on_progress:
				on_progress(i, len(names))
		if errors:
			zf.writestr(
				"_errors.txt", "\n".join(f"{e['certificate']}: {e['error']}" for e in errors)
			)
	return buf.getvalue(), errors


def _zip_filename(file_format):
	return f"Fee Certificates {frappe.utils.now_datetime().strftime('%Y-%m-%d %H%M')}{' (Word)' if file_format == 'docx' else ''}.zip"


@frappe.whitelist()
def bulk_download_fee_certificates(names, file_format="pdf"):
	"""Small selections come back as the ZIP itself; larger ones are built in the background
	and the page is told (realtime "fee_certificate_zip") where to fetch it."""
	_check_access()
	names = [n for n in _as_list(names) if frappe.db.exists("Fee Certificate Request", n)]
	if file_format not in ("pdf", "docx"):
		frappe.throw(_("Unknown format"))
	if not names:
		frappe.throw(_("Select at least one certificate."))
	if len(names) > BULK_LIMIT:
		frappe.throw(_("Download at most {0} certificates at a time.").format(BULK_LIMIT))

	if len(names) <= SYNC_ZIP_LIMIT:
		content, _errors = _build_zip(names, file_format)
		frappe.local.response.update(filename=_zip_filename(file_format), filecontent=content, type="download")
		return

	job = frappe.enqueue(
		_bulk_download_job,
		queue="long",
		timeout=3600,
		names=names,
		file_format=file_format,
		# PDFs load their styles from the site URL; a worker has no request, so pass the one the user is on.
		host=frappe.utils.get_url(),
	)
	return {"queued": True, "job_id": job.id if job else None, "count": len(names)}


def _bulk_download_job(names, file_format, host=None):
	user = frappe.session.user
	if host and not frappe.conf.get("host_name"):
		frappe.local.conf.host_name = host

	def progress(done, total):
		if done == total or done % 5 == 0:
			frappe.publish_realtime("fee_certificate_zip", {"progress": done, "total": total}, user=user)

	try:
		content, errors = _build_zip(names, file_format, progress)
		file_doc = frappe.get_doc(
			{"doctype": "File", "file_name": _zip_filename(file_format), "content": content, "is_private": 1}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.publish_realtime(
			"fee_certificate_zip",
			{"file_url": file_doc.file_url, "count": len(names) - len(errors), "errors": errors},
			user=user,
		)
	except Exception:
		frappe.log_error(title="Fee certificate bulk download failed")
		frappe.publish_realtime("fee_certificate_zip", {"failed": True}, user=user)
