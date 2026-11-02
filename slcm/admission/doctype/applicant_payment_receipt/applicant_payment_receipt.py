import io
import json
import zipfile

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, now_datetime
from frappe.utils.file_manager import save_file


class ApplicantPaymentReceipt(Document):
	def validate(self):
		self.set_notification_receiver()


	def after_insert(self):
		"""Automated generation and attachment of PDF on creation."""
		self.generate_and_attach_pdf()

	def generate_and_attach_pdf(self):
		"""Generates the receipt PDF and attaches it to the record."""
		try:
			# Use the template specified in the record, or fallback to default
			print_format = self.payment_receipt_template or "Applicant Payment Receipt"
			
			pdf_content = frappe.get_print(
				self.doctype,
				self.name,
				print_format,
				as_pdf=True,
			)

			formatted_date = formatdate(self.payment_date, "dd-mm-yyyy")
			filename = f"{self.applicant or self.name} - fee receipt ( {formatted_date} ).pdf"
			
			# Save to file manager
			from frappe.utils.file_manager import save_file
			saved_file = save_file(
				filename,
				pdf_content,
				self.doctype,
				self.name,
				is_private=1
			)
			
			self.db_set("receipt_pdf", saved_file.file_url)
			return saved_file.file_url
		except Exception as e:
			frappe.log_error(f"PDF Generation Failed for {self.name}: {str(e)}", "Receipt PDF Error")
			return None

	def set_notification_receiver(self):
		if self.applicant:
			applicant_email = frappe.db.get_value("Applicant", self.applicant, "email")
			if applicant_email:
				user_name = frappe.db.get_value("User", {"email": applicant_email}, "name")
				if user_name:
					self.notification_receiver = user_name


@frappe.whitelist()
def get_bulk_receipts_zip(filters):
	if isinstance(filters, str):
		filters = json.loads(filters)

	query_filters = {}
	if filters.get("program"):
		query_filters["program"] = filters["program"]
	if filters.get("academic_year"):
		query_filters["academic_year"] = filters["academic_year"]
	if filters.get("payment_mode"):
		query_filters["payment_mode"] = filters["payment_mode"]

	if filters.get("from_date") and filters.get("to_date"):
		query_filters["payment_date"] = ["between", [filters["from_date"], filters["to_date"]]]
	elif filters.get("from_date"):
		query_filters["payment_date"] = [">=", filters["from_date"]]
	elif filters.get("to_date"):
		query_filters["payment_date"] = ["<=", filters["to_date"]]

	output_format = filters.get("output_format", "ZIP Archive")

	receipts = frappe.get_all(
		"Applicant Payment Receipt",
		filters=query_filters,
		fields=["name", "applicant", "payment_date", "receipt_pdf", "payment_receipt_template"],
	)

	if not receipts:
		frappe.throw(_("No receipts found for the selected filters."))

	if len(receipts) > 10:
		frappe.enqueue(
			method="slcm.admission.doctype.applicant_payment_receipt.applicant_payment_receipt.bulk_receipts_zip_worker",
			queue="long",
			receipts=receipts,
			user=frappe.session.user,
			output_format=output_format
		)
		return {
			"status": "enqueued",
			"message": _("Preparing {0} for {1} fee receipts in the background. You will receive a notification when it's ready.").format(output_format, len(receipts))
		}

	file_url, summary, errors = process_bulk_receipts_zip(receipts, user=frappe.session.user, output_format=output_format)
	return file_url

# Background job only (frappe.enqueue); not whitelisted — it switches to the given user.
def bulk_receipts_zip_worker(receipts, user, output_format="ZIP Archive"):
	frappe.set_user(user)
	try:
		file_url, summary, errors = process_bulk_receipts_zip(receipts, user=user, output_format=output_format)
		
		error_details = ""
		if errors:
			error_details = "<br><br><b>Errors:</b><ul>" + "".join([f"<li>{e}</li>" for e in errors[:10]]) + "</ul>"
			if len(errors) > 10:
				error_details += _("<p>...and {0} more errors.</p>").format(len(errors) - 10)

		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
		enqueue_create_notification(
			[user],
			{
				"subject": _("Bulk Receipt Download Ready"),
				"email_content": _("{0}. <a href='{1}' target='_blank'><b>Click here to download</b></a>. {2}").format(summary, file_url, error_details),
				"type": "Alert",
				"document_type": "Applicant Payment Receipt"
			}
		)

		# AUTO-DOWNLOAD TRIGGER
		frappe.publish_realtime("bulk_download_complete", {
			"file_url": file_url,
			"doctype": "Applicant Payment Receipt"
		}, user=user)

	except Exception as e:
		frappe.log_error(f"Bulk Receipt Download Worker Failed: {e!s}", "Bulk Download Error")

def process_bulk_receipts_zip(receipts, user=None, output_format="ZIP Archive"):
	import tempfile
	import os
	from frappe.utils import formatdate
	
	total = len(receipts)
	success_count = 0
	failure_count = 0
	errors = []

	# Use a temporary file on disk for memory safety
	with tempfile.NamedTemporaryFile(delete=False, suffix=".zip" if output_format == "ZIP Archive" else ".pdf") as temp_out:
		temp_path = temp_out.name
		
		if output_format == "ZIP Archive":
			with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
				for i, receipt in enumerate(receipts):
					formatted_date = formatdate(receipt.payment_date, "dd-mm-yyyy")
					filename = f"{receipt.applicant} - fee receipt ( {formatted_date} ).pdf"
					
					try:
						content = _get_receipt_pdf_content(receipt)
						if content:
							zip_file.writestr(filename, content)
							success_count += 1
						else:
							failure_count += 1
							errors.append(f"Empty content for {receipt.name}")
					except Exception as e:
						failure_count += 1
						errors.append(f"Error zipping {receipt.name}: {str(e)}")
					
					_update_bulk_progress(i, total, success_count, failure_count, user, "bulk_receipt_download_progress")
		
		else:
			# PDF Merging logic
			from pypdf import PdfWriter
			merger = PdfWriter()
			
			for i, receipt in enumerate(receipts):
				try:
					content = _get_receipt_pdf_content(receipt)
					if content:
						# For merging, we need to load into memory one by one
						import io
						merger.append(io.BytesIO(content))
						success_count += 1
					else:
						failure_count += 1
						errors.append(f"Empty content for {receipt.name}")
				except Exception as e:
					failure_count += 1
					errors.append(f"Error merging {receipt.name}: {str(e)}")
				
				_update_bulk_progress(i, total, success_count, failure_count, user, "bulk_receipt_download_progress")
			
			with open(temp_path, "wb") as f:
				merger.write(f)
			merger.close()

	if success_count == 0:
		if os.path.exists(temp_path):
			os.remove(temp_path)
		frappe.throw(_("Failed to generate any receipts. Please check the error logs."))

	# Save the final file from disk to Frappe
	final_filename = f"Bulk_Receipts_{now_datetime().strftime('%Y%m%d_%H%M%S')}"
	final_filename += ".zip" if output_format == "ZIP Archive" else ".pdf"
	
	with open(temp_path, "rb") as f:
		saved_file = save_file(
			final_filename,
			f.read(), # This still reads into memory for save_file, but the *generation* was disk-safe.
			"Applicant Payment Receipt",
			"Bulk Download",
			is_private=1,
		)

	# Cleanup temp file
	if os.path.exists(temp_path):
		os.remove(temp_path)

	summary = _("Bulk Download Complete: {0} receipts successful").format(success_count)
	if failure_count > 0:
		summary += _(", {0} failed").format(failure_count)
	
	return saved_file.file_url, summary, errors

def _get_receipt_pdf_content(receipt):
	"""Internal helper to get PDF content for a receipt (cached or dynamic)."""
	pdf_content = None
	if receipt.get("receipt_pdf"):
		try:
			from frappe.utils.file_manager import get_file_path
			file_path = get_file_path(receipt.receipt_pdf)
			if file_path and os.path.exists(file_path):
				with open(file_path, "rb") as f:
					pdf_content = f.read()
		except Exception:
			pass
	
	if not pdf_content:
		print_format = receipt.get("payment_receipt_template") or "Applicant Payment Receipt"
		pdf_content = frappe.get_print(
			"Applicant Payment Receipt",
			receipt.name,
			print_format,
			as_pdf=True,
		)
	return pdf_content

def _update_bulk_progress(i, total, success, failure, user, event_name):
	"""Internal helper for adaptive progress updates."""
	update_step = 100 if total > 1000 else 10
	if (i + 1) % update_step == 0 or i == total - 1:
		frappe.publish_realtime(event_name, {
			"progress": [(i + 1) * 100 / total],
			"title": _("Preparing Bulk Download..."),
			"description": _("Processing {0} of {1} records ({2} successful, {3} failed)").format(
				i + 1, total, success, failure
			)
		}, user=user or frappe.session.user)

