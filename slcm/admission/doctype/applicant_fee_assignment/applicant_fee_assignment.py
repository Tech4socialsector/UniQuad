# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.model.document import Document
from frappe.utils import flt, add_days, nowdate


class ApplicantFeeAssignment(Document):
	def validate(self):
		self.validate_reference()
		self.set_metadata()
		self.set_notification_receiver()
		self.apply_scholarship()
		self.calculate_totals()
		self.validate_status_change()

	def validate_reference(self):
		"""Require either offer_letter (Admission/Confirmation Fee) or applicant for Application Fee."""
		if self.offer_letter:
			if not self.fee_type or self.fee_type not in ["Admission Fee", "Confirmation Fee", "Course Fee"]:
				self.fee_type = "Course Fee"
				
			existing = frappe.db.get_value("Applicant Fee Assignment", {
				"offer_letter": self.offer_letter,
				"fee_type": self.fee_type,
				"name": ["!=", self.name],
				"status": ["!=", "Cancelled"],
				"docstatus": ["<", 2]
			})
			if existing:
				frappe.throw(frappe._("An active Applicant Fee Assignment ({0}) already exists for the Offer Letter {1}.").format(existing, self.offer_letter))
		else:
			self.fee_type = "Application Fee"
			if self.applicant:
				meta = frappe.db.get_value("Applicant", self.applicant,
					["program", "admission_cycle", "academic_year"], as_dict=True)
				if meta:
					self.program = meta.program
					self.admission_cycle = meta.admission_cycle
					if meta.academic_year:
						self.academic_year = meta.academic_year

	def set_metadata(self):
		if self.applicant:
			if not self.admission_cycle or not self.academic_year:
				metadata = frappe.db.get_value("Applicant", self.applicant,
					["admission_cycle", "academic_year"], as_dict=True)
				if metadata:
					if not self.admission_cycle:
						self.admission_cycle = metadata.admission_cycle
					if not self.academic_year:
						self.academic_year = metadata.academic_year

	def set_notification_receiver(self):
		if self.applicant:
			applicant_email = frappe.db.get_value("Applicant", self.applicant, "email")
			if applicant_email:
				user_name = frappe.db.get_value("User", {"email": applicant_email}, "name")
				if user_name:
					self.notification_receiver = user_name

	def apply_scholarship(self):
		"""
		Fetches the total approved scholarship amount for this applicant + cycle
		and stores it directly in the scholarship_amount field.
		No Fee Component link row is added — scholarship is tracked as a separate field.
		Admission Fee assignments DO apply scholarship; scholarship applies only to Admission Fee.
		"""
		if self.fee_type not in ["Admission Fee", "Course Fee"] or not self.applicant or not self.admission_cycle:
			return

		scholarship_data = frappe.db.get_all("Scholarship Application",
			filters={
				"applicant_id": self.applicant,
				"admission_cycle": self.admission_cycle,
				"status": "Approved"
			},
			fields=["name", "calculated_benefit"],
			order_by="creation desc"
		)

		total_benefit = sum(flt(d.calculated_benefit) for d in scholarship_data)
		self.scholarship_amount = total_benefit
		self.scholarship_applied = 1 if total_benefit > 0 else 0

		if scholarship_data and not self.scholarship_application:
			self.scholarship_application = scholarship_data[0].name

	def calculate_totals(self):
		"""
		Sum fee component rows (Admission Fee and Application Fee both use the child table).
		Scholarship is deducted only for Application Fee assignments.
		Mirrors ``application_fee`` from the grid total for Application Fee type.
		"""
		if self.fee_type == "Confirmation Fee":
			base_total = flt(self.confirmation_fee)
			self.total_amount = base_total
			self.final_payable_amount = max(0, base_total - flt(self.scholarship_amount))
			return

		base_total = 0
		for row in self.fee_components:
			if row.is_taxable:
				row.tax_amount = flt(row.amount) * flt(row.tax_rate) / 100
			else:
				row.tax_amount = 0
			row.total_amount = flt(row.amount) + flt(row.tax_amount)
			base_total += row.total_amount

		self.total_amount = base_total
		if self.fee_type == "Application Fee":
			self.application_fee = base_total

		self.final_payable_amount = max(0, base_total - flt(self.scholarship_amount) - flt(self.confirmation_fee))

	def validate_status_change(self):
		if self.status == "Converted":
			if not frappe.flags.in_test and not frappe.flags.in_import:
				frappe.throw(frappe._("Status cannot be set to 'Converted' manually. Please use the 'Convert to Student' action."))

	def before_submit(self):
		if not self.fee_components and self.fee_type != "Confirmation Fee":
			frappe.throw(frappe._("At least one Fee Component row is required."))

		for row in self.fee_components:
			if flt(row.amount) < 0:
				frappe.throw(
					frappe._("Amount for {0} cannot be negative.").format(
						row.component_name or row.fee_component
					)
				)
			if self.fee_type in ["Admission Fee", "Confirmation Fee", "Course Fee"] and flt(row.amount) <= 0:
				frappe.throw(
					frappe._("Amount for {0} must be positive.").format(
						row.component_name or row.fee_component
					)
				)

		self.status = "Assigned"

	def before_save(self):
		if self.status == "Paid" and not self.payment_date:
			self.payment_date = frappe.utils.today()

	def on_cancel(self):
		self.status = "Cancelled"

	def on_update(self):
		if self.status == "Paid" and self.offer_letter:
			today = frappe.utils.today()
			if self.fee_type == "Confirmation Fee":
				if not frappe.db.get_value("Offer Letter", self.offer_letter, "confirmation_fee_paid_on"):
					frappe.db.set_value("Offer Letter", self.offer_letter, "confirmation_fee_paid_on", today)
			elif self.fee_type in ["Admission Fee", "Course Fee"]:
				if not frappe.db.get_value("Offer Letter", self.offer_letter, "full_fee_paid_on"):
					frappe.db.set_value("Offer Letter", self.offer_letter, "full_fee_paid_on", today)
			
			self.generate_payment_receipt()

	def generate_payment_receipt(self):
		if frappe.db.exists("Applicant Payment Receipt", {"assignment": self.name, "fee_type": self.fee_type, "docstatus": ["!=", 2]}):
			return
		
		# Get print format from Offer Letter's Fee Structure
		receipt_print_format = None
		if self.offer_letter:
			fee_structure = frappe.db.get_value("Offer Letter", self.offer_letter, "fee_structure")
			if fee_structure:
				receipt_print_format = frappe.db.get_value("Fee Structure", fee_structure, "receipt_print_format")
		
		receipt = frappe.new_doc("Applicant Payment Receipt")
		receipt.applicant = self.applicant
		receipt.applicant_name = self.applicant_name
		receipt.program = self.program
		receipt.academic_year = self.academic_year
		receipt.offer_letter = self.offer_letter
		receipt.fee_type = self.fee_type
		receipt.assignment = self.name
		receipt.payment_date = self.get("payment_date") or frappe.utils.today()
		receipt.total_amount = self.total_amount
		receipt.scholarship_amount = self.scholarship_amount
		receipt.scholarship_applied = self.scholarship_applied
		receipt.confirmation_fee = self.confirmation_fee
		receipt.net_amount = self.final_payable_amount
		receipt.payment_mode = "Online"
		if receipt_print_format:
			receipt.payment_receipt_template = receipt_print_format

		for row in self.fee_components:
			receipt.append("fee_components", {
				"fee_component": row.fee_component,
				"component_name": row.component_name,
				"amount": row.amount
			})
			
		receipt.insert(ignore_permissions=True)
		receipt.submit()


# ── Import unified conversion helpers ────────────────────────────────────────
# The field mapping, scholarship sync, and student creation logic now live in
# slcm/api/service/applicant_to_student.py to avoid duplication between
# the AFA doctype and the Applicant doctype (which also has a bulk-convert path).
from slcm.api.service.applicant_to_student import (
	_get_academic_year_from_cycle,
	_sync_finance_to_student,
	_sync_scholarship_to_student,
	convert_applicant_to_student,
)


def _map_applicant_to_student(student, applicant, program, admission_cycle, offer_letter_name=None):
	"""
	Forwarding stub — real implementation is in slcm.api.service.applicant_to_student.
	Kept for backward-compat with any direct callers within this module.
	"""
	from slcm.api.service.applicant_to_student import _map_applicant_to_student as _real_map
	return _real_map(student, applicant, program, admission_cycle, offer_letter_name)


@frappe.whitelist()
def create_invoice(docname):
	doc = frappe.get_doc("Applicant Fee Assignment", docname)

	if doc.fee_type not in ["Admission Fee", "Course Fee"]:
		frappe.throw(frappe._("Conversion to Student is only allowed for the Course / Admission Fee."))

	if doc.status == "Converted":
		frappe.throw(frappe._("This assignment has already been converted to a student."))

	if doc.status not in ("Paid", "Partially Paid"):
		frappe.throw(frappe._(
			"Conversion is only allowed when status is 'Paid' or 'Partially Paid'. "
			"Current status is '{0}'."
		).format(doc.status or "unknown"))

	applicant = frappe.get_doc("Applicant", doc.applicant)

	# ── 1. Create Student Master via unified API (deduplication + role update included) ──
	result = convert_applicant_to_student(
		applicant_name=doc.applicant,
		program=doc.program,
		admission_cycle=doc.admission_cycle,
		offer_letter_name=doc.offer_letter,
	)
	student_name = result["student_name"]

	if result.get("created"):
		frappe.logger().info(
			f"[create_invoice] Student Master created: {student_name} "
			f"for Applicant: {applicant.name} | AFA: {docname}"
		)
	else:
		frappe.logger().info(
			f"[create_invoice] Re-using existing Student Master: {student_name} "
			f"for Applicant: {applicant.name} | AFA: {docname}"
		)

	# ── 2. Sync Finance tab of Student Master (Scholarship Details + Fee Details) ──
	# Fetching additional details from the linked Scholarship Application if present.

	scholarship_type = None
	scholarship_percentage = 0
	scholarship_approval_date = None

	if doc.get("scholarship_application"):
		sa_data = frappe.db.get_value("Scholarship Application", doc.scholarship_application,
			["scholarship_scheme", "approval_date"], as_dict=True)
		if sa_data:
			scholarship_approval_date = sa_data.approval_date
			if sa_data.scholarship_scheme:
				scheme_data = frappe.db.get_value("Scholarship Scheme", sa_data.scholarship_scheme,
					["scheme_type", "coverage_type", "coverage_value"], as_dict=True)
				if scheme_data:
					scholarship_type = scheme_data.scheme_type
					if scheme_data.coverage_type == "Percentage":
						scholarship_percentage = scheme_data.coverage_value

	offer_fee_structure = None
	if doc.get("offer_letter"):
		offer_fee_structure = frappe.db.get_value("Offer Letter", doc.offer_letter, "fee_structure")

	try:
		_sync_finance_to_student(
			student_name=student_name,
			scholarship_amount=flt(doc.scholarship_amount),
			scholarship_type=scholarship_type,
			scholarship_percentage=flt(scholarship_percentage),
			scholarship_approval_date=scholarship_approval_date,
			# AFA.remarks maps to fee_waiver_remarks when a scholarship/waiver is applied
			fee_waiver_remarks=doc.get("remarks") or None,
			total_amount=flt(doc.total_amount),
			final_payable_amount=flt(doc.get("final_payable_amount") or 0),
			fee_payment_status=doc.status,
			fee_structure=offer_fee_structure,
		)
	except Exception as sync_err:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Student Finance Sync Failed | Student: {student_name}"
		)

	# ── 3. Update Fee Assignment ──────────────────────────────────────────────
	doc.db_set("status", "Converted")

	# ── 4. Set Applicant status to Enrolled ───────────────────────────────────
	try:
		_enrolled_status = "Enrolled"
		if frappe.db.exists("Applicant Status", _enrolled_status):
			frappe.db.set_value(
				"Applicant", doc.applicant,
				"status", _enrolled_status,
				update_modified=True
			)
			frappe.db.commit()
	except Exception as status_err:
		# Non-fatal: student is already created; just log
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Applicant Status Update Failed | Applicant: {doc.applicant} | AFA: {docname}"
		)

	# NOTE: User role swap (Applicant → Student) is handled inside
	# convert_applicant_to_student() called in step 1 above.

	# ── 5. Create Fee Invoice for Confirmation Fee ───────────────────────────
	if doc.fee_type == "Confirmation Fee":
		try:
			from slcm.api.service.fee_service import FeeService
			fs_doc = frappe.get_doc("Fee Structure", offer_fee_structure)
			is_foreign = frappe.db.get_value("Applicant", doc.applicant, "foriegn_national") == "Yes"
			fee_data = FeeService._calculate_and_freeze_fees(offer_fee_structure, is_foreign=is_foreign)
			
			fi = frappe.new_doc("Fee Invoice")
			fi.student = student_name
			fi.program = doc.program
			fi.academic_year = doc.academic_year
			from slcm.slcm.doctype.academic_term.academic_term import get_current_term
			fi.academic_term = get_current_term()
			fi.applicant_fee_assignment = doc.name
			fi.invoice_date = frappe.utils.today()
			fi.due_date = frappe.utils.add_days(frappe.utils.today(), 15)
			fi.needs_accommodation = frappe.db.get_value("Applicant", doc.applicant, "needs_accommodation")
			
			deducted_amount = 0
			if fs_doc.is_confirmation_fee_applicable and fs_doc.deduct_confirmation_fee:
				deducted_amount = fs_doc.confirmation_fee_amount
				
			total_from_components = 0
			for row in fee_data.get("components", []):
				if (row.get("fee_component") or "").lower() == "scholarship":
					continue
				fi.append("fee_components", {
					"fee_component": row.get("fee_component"),
					"component_name": row.get("component_name"),
					"amount": row.get("amount"),
					"is_taxable": row.get("is_taxable"),
					"tax_rate": row.get("tax_rate"),
					"tax_amount": row.get("tax_amount"),
					"total_amount": row.get("total_amount")
				})
				total_from_components += flt(row.get("total_amount") or row.get("amount"))
			
			if deducted_amount > 0:
				if not frappe.db.exists("Fee Component", "Confirmation Fee Deduction"):
					frappe.get_doc({
						"doctype": "Fee Component",
						"fee_component": "Confirmation Fee Deduction",
						"component_name": "Confirmation Fee Deduction"
					}).insert(ignore_permissions=True)
				
				fi.append("fee_components", {
					"fee_component": "Confirmation Fee Deduction",
					"component_name": "Confirmation Fee Deduction",
					"amount": -deducted_amount,
					"is_taxable": 0,
					"tax_amount": 0,
					"total_amount": -deducted_amount
				})
			
			fi.scholarship_amount = flt(doc.scholarship_amount)
			fi.insert(ignore_permissions=True)
			
		except Exception as invoice_err:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Fee Invoice Creation Failed | Student: {student_name}"
			)

	return student_name



# ── Bulk Convert to Student ───────────────────────────────────────────────────

@frappe.whitelist()
def bulk_convert_to_student(assignments):
	"""
	Convert multiple Applicant Fee Assignments to Student.
	Uses background job if batch > 250.
	"""
	if isinstance(assignments, str):
		assignments = json.loads(assignments)
	if not assignments:
		return {"message": frappe._("No assignments provided")}

	eligible = []
	skipped = []
	for name in assignments:
		if not name:
			continue
		afa = frappe.db.get_value(
			"Applicant Fee Assignment",
			name,
			["fee_type", "status", "docstatus", "name"],
			as_dict=True,
		)
		if not afa:
			skipped.append({"assignment": name, "reason": frappe._("Not found")})
			continue
		if afa.fee_type not in ["Admission Fee", "Confirmation Fee", "Course Fee"] or afa.docstatus != 1:
			skipped.append(
				{
					"assignment": name,
					"reason": frappe._("Must be submitted Course/Admission/Confirmation Fee assignment."),
				}
			)
			continue
		if afa.status not in ("Paid", "Partially Paid"):
			skipped.append(
				{
					"assignment": name,
					"reason": frappe._(
						"Status must be 'Paid' or 'Partially Paid' (current: {0})."
					).format(afa.status or "—"),
				}
			)
			continue
		eligible.append(name)

	if not eligible:
		return {
			"message": frappe._(
				"No eligible assignments to convert. Only submitted Admission Fee rows with status "
				"'Paid' or 'Partially Paid' can be converted."
			),
			"skipped": skipped,
		}

	# Background queue for large batches (isolated commits + notification)
	if len(eligible) > 250:
		frappe.enqueue(
			method="slcm.admission.doctype.applicant_fee_assignment.applicant_fee_assignment.background_bulk_convert_worker",
			queue="long",
			assignments=eligible,
			user=frappe.session.user,
			timeout=5400,
			now=frappe.flags.in_test,
		)
		return {
			"queued": True,
			"message": frappe._(
				"Large batch detected ({0} assignments). Processing started safely in the background. "
				"You will receive a notification when finished."
			).format(len(eligible)),
			"skipped": skipped,
		}

	out = _process_bulk_convert_batch(eligible)
	if skipped:
		out["skipped"] = skipped
	return out


def _process_bulk_convert_batch(assignments, progress_user=None):
	"""Process a list of AFA docnames; return { success: [], errors: [] }. Commits each success separately."""
	results = {"success": [], "errors": []}
	total = len(assignments)
	for idx, docname in enumerate(assignments):
		if progress_user:
			frappe.publish_realtime(
				"bulk_convert_to_student_progress",
				{
					"progress": idx + 1,
					"total": total,
					"message": frappe._("Converting {0} ({1} / {2})").format(docname, idx + 1, total),
				},
				user=progress_user,
			)
		try:
			invoice_name = create_invoice(docname)
			frappe.db.commit()
			results["success"].append({"assignment": docname, "invoice": invoice_name})
		except Exception as e:
			frappe.db.rollback()
			err_detail = str(e)
			results["errors"].append({"assignment": docname, "error": err_detail})
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Bulk Convert to Student Error | AFA: {docname}",
			)
	return results


def background_bulk_convert_worker(assignments, user):
	"""Background worker for bulk convert; notifies user when done."""
	frappe.set_user(user)
	results = _process_bulk_convert_batch(assignments, progress_user=user)
	success_count = len(results["success"])
	error_count = len(results["errors"])

	if error_count:
		summary_raw = frappe._("Converted {0} assignment(s); {1} failed.").format(success_count, error_count)
	else:
		summary_raw = frappe._("Successfully converted {0} assignment(s).").format(success_count)
	summary_msg = frappe.utils.escape_html(summary_raw)
	detail_lines = []
	for err in results["errors"][:25]:
		detail_lines.append(
			"<p><b>{0}</b>: {1}</p>".format(
				frappe.utils.escape_html(err.get("assignment") or ""),
				frappe.utils.escape_html(err.get("error") or ""),
			)
		)
	if len(results["errors"]) > 25:
		detail_lines.append(
			"<p><i>"
			+ frappe.utils.escape_html(
				frappe._("…and {0} more (see Error Log).").format(len(results["errors"]) - 25)
			)
			+ "</i></p>"
		)
	err_block = "".join(detail_lines)

	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	enqueue_create_notification(
		[user],
		{
			"subject": frappe._("Bulk Convert to Student — {0} ok, {1} errors").format(success_count, error_count),
			"email_content": (
				f"<h4>{summary_msg}</h4>"
				f"<p>{frappe.utils.escape_html(frappe._('Check Applicant Fee Assignment and Fee Invoice for details.'))}</p>"
				+ (f"<h5>{frappe.utils.escape_html(frappe._('Errors'))}</h5>{err_block}" if err_block else "")
			),
			"type": "Alert",
			"document_type": "Applicant Fee Assignment",
		},
	)
	frappe.publish_realtime(
		event="bulk_convert_to_student_done",
		message={"success": success_count, "errors": error_count},
		user=user,
	)
