# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
import hashlib
import json
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import now_datetime, flt, get_datetime


class ScholarshipApplication(Document):
	def autoname(self):
		if not self.admission_cycle:
			frappe.throw(frappe._("Admission Cycle is mandatory for naming"))

		# Naming Series: SA-{CYCLE}-.#####
		self.name = make_autoname(f"SA-{self.admission_cycle}-.#####")

	def validate(self):
		if not self.status:
			self.status = "Submitted"

		if self.admission_cycle:
			enable_scholarship = frappe.db.get_value("Admission Cycle", self.admission_cycle, "enable_scholarship")
			if not enable_scholarship:
				frappe.throw(frappe._("Scholarships are not enabled for this admission cycle."))

		# Auto-populate Reviewed By and Approval Date when approved
		if self.status == "Approved":
			if not self.reviewed_by:
				self.reviewed_by = frappe.session.user
			if not self.approval_date:
				self.approval_date = now_datetime()

		if self.approval_date and get_datetime(self.approval_date) > get_datetime(now_datetime()):
			frappe.throw(frappe._("Approval Date cannot be in the future."))

		self.set_applicant_metadata()
		self.set_academic_year()
		self.prevent_duplicate()
		self.validate_scheme_mapping()
		self.validate_requirements()
		self.validate_stage()
		self.set_original_fee()
		self.calculate_benefit()
		self.validate_rejection_reason()
		self.validate_conflicts()
		self.validate_payment_status()

	def set_applicant_metadata(self):
		if not self.applicant_id:
			return

		if not self.applicant_name:
			self.applicant_name = frappe.db.get_value("Applicant", self.applicant_id, "candidate_name")

	def set_academic_year(self):
		if self.admission_cycle and not self.academic_year:
			admission_year = frappe.db.get_value("Admission Cycle", self.admission_cycle, "admission_year")
			if admission_year:
				# Academic Year usually matches Admission Year name in this system
				if frappe.db.exists("Academic Year", admission_year):
					self.academic_year = admission_year
				else:
					# Fallback to Admission Settings
					self.academic_year = frappe.db.get_single_value("Admission Settings", "current_academic_year")

	def set_original_fee(self):
		if not self.applicant_id or not self.program:
			return

		from slcm.api.service.offer_service import OfferService
		from slcm.api.service.fee_service import FeeService

		# Resolve admission year
		campus = self.campus or frappe.db.get_value("Applicant", self.applicant_id, "campus")
		cycle = self.admission_cycle or frappe.db.get_value("Applicant", self.applicant_id, "admission_cycle")

		try:
			admission_year = OfferService.resolve_admission_year(self.applicant_id, campus, cycle)
			if not admission_year:
				return

			# Get active config
			config = OfferService.get_config(admission_year, cycle, campus)

			fee_structure_name = None
			for row in config.fee_structure:
				fs_program = frappe.db.get_value("Fee Structure", row.fee_structure, "program")
				if fs_program == self.program:
					fee_structure_name = row.fee_structure
					break

			if fee_structure_name:
				nationality = frappe.db.get_value("Applicant", self.applicant_id, "nationality")
				is_foreign = nationality != "Indian"
				fee_data = FeeService._calculate_and_freeze_fees(fee_structure_name, is_foreign=is_foreign)
				self.original_fee_amount = flt(fee_data.get("total_payable") or 0)
		except Exception:
			# If resolution fails, we don't block save, but fee might be 0
			pass

	def prevent_duplicate(self):
		existing = frappe.db.exists(
			"Scholarship Application",
			{
				"applicant_id": self.applicant_id,
				"scholarship_scheme": self.scholarship_scheme,
				"status": ["not in", ["Rejected", "Revoked"]],
				"name": ["!=", self.name]
			}
		)

		if existing:
			frappe.throw(frappe._("You have already applied for this scholarship."))

	def validate_scheme_mapping(self):
		scheme = frappe.get_doc("Scholarship Scheme", self.scholarship_scheme)

		# Validate cycle/campus match
		if scheme.admission_cycle != self.admission_cycle or scheme.campus != self.campus:
			frappe.throw(frappe._("Scholarship is not applicable for selected admission cycle or campus."))

		from slcm.admission.doctype.seat_allocation.seat_allocation import get_applicant_categories
		applicant_categories = get_applicant_categories(self.applicant_id)

		# Check program match
		program_match = not scheme.program or scheme.program == self.program

		# Check category match
		category_match = not scheme.category or scheme.category in applicant_categories

		if not (program_match and category_match):
			frappe.throw(frappe._("Scholarship not applicable for selected program/category."))

		# Check target applicant match (Domestic / International)
		foriegn_national = frappe.db.get_value("Applicant", self.applicant_id, "foriegn_national")
		applicant_type = "International" if foriegn_national == "Yes" else "Domestic"
		target_for = scheme.get("scholarship_for") or "Domestic"
		if target_for != applicant_type:
			frappe.throw(frappe._("This scholarship scheme is only available for {0} applicants.").format(target_for))

	def validate_requirements(self):
		# Always mandatory as per user request
		if self.family_income is None or self.family_income == "":
			frappe.throw(frappe._("Family Income is mandatory for this scholarship"))
		if not self.income_certificate:
			frappe.throw(frappe._("Income Certificate is mandatory for this scholarship"))

		scheme = frappe.get_doc("Scholarship Scheme", self.scholarship_scheme)

		# 1. Income Validation
		if scheme.scheme_type == "Need" and scheme.income_certificate_required:
			if scheme.max_income and flt(self.family_income) > flt(scheme.max_income):
				frappe.throw(frappe._("Family Income {0} exceeds the maximum allowed {1} for this scholarship")
					.format(self.family_income, scheme.max_income))
			if scheme.min_income and flt(self.family_income) < flt(scheme.min_income):
				frappe.throw(frappe._("Family Income {0} is below the minimum required {1} for this scholarship")
					.format(self.family_income, scheme.min_income))

		# 2. Merit Validation
		if scheme.scheme_type == "Merit" and scheme.min_merit_score:
			# Try to fetch total score from Merit List Applicant
			merit_score = frappe.db.get_value(
				"Merit List Applicant",
				{
					"applicant_id": self.applicant_id,
					"parentfield": "merit_applicants"
				},
				"total_score"
			)

			if merit_score is None:
				# Fallback to Entrance Test Seat Allocation entrance test score
				merit_score = frappe.db.get_value(
					"Entrance Test Seat Allocation",
					{"applicant": self.applicant_id, "admission_cycle": self.admission_cycle},
					"total_marks_secured_in_part_a_b"
				)

			if merit_score is not None:
				if flt(merit_score) < flt(scheme.min_merit_score):
					frappe.throw(frappe._("Your merit score ({0}) is below the required minimum ({1}) for this scholarship")
						.format(merit_score, scheme.min_merit_score))
			else:
				# No merit score found at all
				frappe.msgprint(
					frappe._("Warning: No merit score found for this applicant. Manual verification required for Merit Scholarship."),
					indicator="orange"
				)

	def validate_stage(self):
		# Skip availability checks if rejecting or revoking
		if self.status in ["Rejected", "Revoked"]:
			return

		# Skip if already approved and just being updated, to avoid blocking saves on archived schemes
		if not self.is_new():
			old_doc = self.get_doc_before_save()
			if old_doc and old_doc.status == "Approved" and self.status == "Approved":
				return

		from slcm.admission.utils.scholarship_availability import check_scholarship_availability

		# Get applicant status
		applicant_status = frappe.db.get_value("Applicant", self.applicant_id, "status")

		check_scholarship_availability(
			self.scholarship_scheme,
			applicant_status,
			self.applicant_id
		)

	def calculate_benefit(self):
		from slcm.admission.utils.scholarship_coverage_engine import calculate_scholarship_amount

		self.calculated_benefit = calculate_scholarship_amount(self)
		self.final_fee_amount = flt(self.original_fee_amount or 0) - flt(self.calculated_benefit or 0)

	def validate_rejection_reason(self):
		if self.status == "Rejected" and not self.rejection_reason:
			frappe.throw(frappe._("Rejection reason is mandatory"))

	def validate_conflicts(self):
		# Check Max Schemes Per Applicant limit from Admission Cycle
		limit = frappe.db.get_value("Admission Cycle", self.admission_cycle, "max_schemes_per_applicant")
		if limit and limit > 0:
			approved_count = frappe.db.count("Scholarship Application", {
				"applicant_id": self.applicant_id,
				"status": "Approved",
				"name": ["!=", self.name],
				"admission_cycle": self.admission_cycle # Limit per cycle
			})

			if approved_count >= limit:
				frappe.throw(frappe._("Limit Reached: This admission cycle allows a maximum of {0} approved scholarships per applicant. Applicant already has {1}.").format(limit, approved_count))

	def validate_payment_status(self):
		"""
		Prevents application if the admission fee has already been paid.
		Scholarships must be applied for and approved BEFORE fee payment.
		"""
		if not self.applicant_id:
			return

		# Check for Paid or Converted Admission Fee Assignments
		# Application Fee payment should not block scholarship applications.
		paid_afa = frappe.db.exists("Applicant Fee Assignment", {
			"applicant": self.applicant_id,
			"admission_cycle": self.admission_cycle,
			"fee_type": "Admission Fee",
			"status": ["in", ["Paid", "Converted"]],
			"docstatus": ["!=", 2]
		})

		if paid_afa:
			frappe.throw(
				frappe._("Scholarship applications are not permitted once the admission fee has been paid. "
						 "Scholarships must be granted before the final fee payment is processed."),
				title=frappe._("Payment Already Completed")
			)

	def create_audit_log(self):
		"""
		Records status changes and application creation in the Scholarship Audit Log.
		"""
		old_doc = self.get_doc_before_save()

		is_new = not old_doc
		if not is_new and old_doc.status == self.status:
			# Only log if status has changed
			return

		# Mapping status to action_type allowed in Scholarship Audit Log
		action_map = {
			"Submitted": "Apply",
			"Approved": "Approve",
			"Rejected": "Reject",
			"Revoked": "Revoke",
			"Cancelled": "Revoke"
		}

		# If new, use Apply action
		if is_new:
			action_type = "Apply"
			previous_state = {}
		else:
			action_type = action_map.get(self.status, "Modify")
			previous_state = old_doc.as_dict()

		# Determine triggered_by based on user role/session
		triggered_by = "Admin"
		if frappe.session.user == self.owner:
			triggered_by = "Applicant"
		elif frappe.session.user == "Administrator":
			triggered_by = "System"

		# Create hash for tamper detection
		record_string = json.dumps({
			"application": self.name,
			"old_status": old_doc.status if old_doc else None,
			"new_status": self.status,
			"user": frappe.session.user,
			"time": str(now_datetime())
		}, sort_keys=True)
		record_hash = hashlib.sha256(record_string.encode()).hexdigest()

		try:
			frappe.get_doc({
				"doctype": "Scholarship Audit Log",
				"scholarship_application": self.name,
				"scholarship_scheme": self.scholarship_scheme,
				"admission_cycle": self.admission_cycle,
				"campus": self.campus,
				"program": self.program,
				"action_type": action_type,
				"previous_state": json.dumps(previous_state, indent=4, default=str),
				"new_state": json.dumps(self.as_dict(), indent=4, default=str),
				"performed_by": frappe.session.user,
				"triggered_by": triggered_by,
				"action_timestamp": now_datetime(),
				"reason": self.rejection_reason or f"Status changed to {self.status}",
				"ip_address": frappe.local.request_ip if hasattr(frappe.local, "request_ip") else None,
				"record_hash": record_hash
			}).insert(ignore_permissions=True)
		except Exception as e:
			# Log to Error Log but don't stop the main Scholarship save
			frappe.log_error(title="Scholarship Audit Log Error", message=frappe.get_traceback())

	def on_update(self):
		"""Called when a doc is saved."""
		self.create_audit_log()

		old_doc = self.get_doc_before_save()
		old_status = old_doc.status if old_doc else None

		if old_status != "Approved" and self.status == "Approved":
			self.apply_financial_effects()
			self.sync_fee_assignment()
			from slcm.admission.notification_service import notify_scholarship_status
			notify_scholarship_status(self.name)

		elif old_status != "Rejected" and self.status == "Rejected":
			from slcm.admission.notification_service import notify_scholarship_status
			notify_scholarship_status(self.name)

		elif old_status == "Approved" and self.status != "Approved":
			self.reverse_financial_effects()
			self.sync_fee_assignment(reverse=True)

		elif self.status == "Approved" and old_status == "Approved":
			benefit_diff = flt(self.calculated_benefit) - flt(old_doc.calculated_benefit)
			if benefit_diff != 0:
				from slcm.admission.utils.scholarship_availability import update_scheme_usage
				update_scheme_usage(self.scholarship_scheme, benefit_diff, mapping_name=None, update_count=False)
			self.sync_fee_assignment()

	def on_submit(self):
		"""Called when doc is submitted (docstatus 0 → 1)."""
		self.create_audit_log()
		if self.status == "Approved":
			self.apply_financial_effects()
			self.sync_fee_assignment()
			from slcm.admission.notification_service import notify_scholarship_status
			notify_scholarship_status(self.name)
		elif self.status == "Rejected":
			from slcm.admission.notification_service import notify_scholarship_status
			notify_scholarship_status(self.name)

	def on_cancel(self):
		"""Called when submitted doc is cancelled (docstatus 1 → 2)."""
		self.create_audit_log()
		if self.status == "Approved":
			self.reverse_financial_effects()
			self.sync_fee_assignment(reverse=True)

	def on_update_after_submit(self):
		"""
		Called when a SUBMITTED doc (docstatus=1) is updated
		via direct save (e.g. status field changed by admin on submitted doc).
		"""
		self.create_audit_log()

		old_doc = self.get_doc_before_save()
		old_status = old_doc.status if old_doc else None

		# Case 1: Status changed TO Approved
		if old_status != "Approved" and self.status == "Approved":
			self.apply_financial_effects()
			self.sync_fee_assignment()
			from slcm.admission.notification_service import notify_scholarship_status
			notify_scholarship_status(self.name)

		# Case 1b: Status changed TO Rejected
		elif old_status != "Rejected" and self.status == "Rejected":
			from slcm.admission.notification_service import notify_scholarship_status
			notify_scholarship_status(self.name)

		# Case 2: Status changed FROM Approved
		elif old_status == "Approved" and self.status != "Approved":
			self.reverse_financial_effects()
			self.sync_fee_assignment(reverse=True)

		# Case 3: Still Approved, but benefit may have changed
		elif self.status == "Approved" and old_status == "Approved":
			if old_doc:
				benefit_diff = flt(self.calculated_benefit) - flt(old_doc.calculated_benefit)
				if benefit_diff != 0:
					from slcm.admission.utils.scholarship_availability import update_scheme_usage
					update_scheme_usage(self.scholarship_scheme, benefit_diff, mapping_name=None, update_count=False)
			self.sync_fee_assignment()


	def on_trash(self):
		"""Reverse financial effects if an Approved application is deleted."""
		if self.status == "Approved":
			self.reverse_financial_effects()
			self.sync_fee_assignment(reverse=True)

	def sync_fee_assignment(self, reverse=False):
		"""
		Updates the linked Applicant Fee Assignment with scholarship benefit.
		Calculates the TOTAL approved scholarship amount for this applicant in this cycle
		to ensure multiple scholarships are handled correctly (cumulative).
		"""
		if not self.applicant_id or not self.admission_cycle:
			return

		# Query matching AFA specifically for Admission Fee
		afa_data = frappe.db.get_value("Applicant Fee Assignment", {
			"applicant": self.applicant_id,
			"admission_cycle": self.admission_cycle,
			"fee_type": "Admission Fee",
			"docstatus": ["!=", 2]
		}, ["name", "total_amount"], as_dict=True)

		if not afa_data:
			# If no Admission Fee assignment exists yet, we don't sync
			return

		afa_name = afa_data.name
		total_amount = flt(afa_data.total_amount)

		# Calculate cumulative scholarship amount from ALL OTHER approved applications
		# for this specific applicant in this cycle.
		other_scholarships = frappe.db.sql("""
			SELECT SUM(calculated_benefit)
			FROM `tabScholarship Application`
			WHERE applicant_id = %s
			AND admission_cycle = %s
			AND status = 'Approved'
			AND name != %s
		""", (self.applicant_id, self.admission_cycle, self.name))[0][0] or 0

		# Add current application benefit if it is currently Approved
		current_benefit = 0
		if not reverse and self.status == "Approved":
			current_benefit = flt(self.calculated_benefit)

		total_scholarship = flt(other_scholarships) + current_benefit

		# Cap scholarship so it never exceeds the gross fee
		total_scholarship = min(flt(total_scholarship), total_amount)

		scholarship_applied = 1 if total_scholarship > 0 else 0
		final_payable_amount = max(0, total_amount - flt(total_scholarship))

		# Apply changes directly to DB to ensure persistence
		frappe.db.set_value("Applicant Fee Assignment", afa_name, {
			"scholarship_amount": total_scholarship,
			"scholarship_applied": scholarship_applied,
			"final_payable_amount": final_payable_amount
		}, update_modified=True)

		frappe.db.commit()

		# Also update any existing Payment Request amount to match the new final payable amount
		pr_list = frappe.get_all("SLCM Payment Request", filters={
			"reference_doctype": "Offer Letter",
			"reference_name": self.get("offer_letter") or frappe.db.get_value("Applicant Fee Assignment", afa_name, "offer_letter"),
			"status": ["not in", ["Paid", "Cancelled"]]
		}, fields=["name"])

		for pr in pr_list:
			frappe.db.set_value("SLCM Payment Request", pr.name, "amount", final_payable_amount, update_modified=True)

		msg = frappe._("Fee Assignment {0} synced. Total Scholarship: {1}, Final Payable: {2}")\
			.format(afa_name, total_scholarship, final_payable_amount)
		frappe.msgprint(msg, indicator="green")

	def apply_financial_effects(self):
		from slcm.admission.utils.scholarship_availability import update_scheme_usage
		update_scheme_usage(self.scholarship_scheme, self.calculated_benefit)

	def reverse_financial_effects(self):
		from slcm.admission.utils.scholarship_availability import update_scheme_usage
		benefit = self.calculated_benefit
		try:
			old_doc = self.get_doc_before_save()
			if old_doc:
				benefit = old_doc.calculated_benefit
		except Exception:
			pass
		update_scheme_usage(self.scholarship_scheme, benefit, reverse=True)


@frappe.whitelist()
def create_scholarship_application(scheme, family_income, income_certificate_data=None, income_certificate_name=None, supporting_documents_data=None, supporting_documents_name=None):
	"""
	Creates a new Scholarship Application from the portal dashboard with support for base64 files.
	"""
	user = frappe.session.user
	frappe.log_error(f"Applying for scheme {scheme} by user {user}", "Scholarship Application Debug")

	if user == "Guest" or not user:
		frappe.throw(frappe._("You must be logged in to apply for a scholarship."))

	# Get applicant record
	applicant = frappe.db.get_value("Applicant", {"email": user},
		["name", "candidate_name", "program", "campus", "admission_cycle"], as_dict=1)

	if not applicant:
		# Fallback 1: check Entrance Test Seat Allocation if Applicant email doesn't match
		applicant_id = frappe.db.get_value("Entrance Test Seat Allocation", {"email": user}, "applicant")
		if applicant_id:
			applicant = frappe.db.get_value("Applicant", applicant_id,
				["name", "candidate_name", "program", "campus", "admission_cycle"], as_dict=1)

	if not applicant:
		# Fallback 2: search by owner (User ID)
		applicant = frappe.db.get_value("Applicant", {"owner": user},
			["name", "candidate_name", "program", "campus", "admission_cycle"], as_dict=1)

	if not applicant:
		frappe.log_error(f"No applicant found for user {user}", "Scholarship Application Debug")
		frappe.throw(frappe._("No applicant record found for your account."))

	frappe.log_error(f"Found applicant {applicant.name}", "Scholarship Application Debug")

	# Server side validation
	enable_scholarship = frappe.db.get_value("Admission Cycle", applicant.admission_cycle, "enable_scholarship")
	if not enable_scholarship:
		frappe.throw(frappe._("Scholarship applications are not currently enabled for this admission cycle."))

	if not family_income:
		frappe.throw(frappe._("Annual Family Income is mandatory."))
	
	if not income_certificate_data or not income_certificate_name:
		frappe.throw(frappe._("Income Certificate is mandatory."))

	# Handle file uploads
	income_cert_url = None
	if income_certificate_data and income_certificate_name:
		try:
			import base64
			import os

			# Validate extension
			allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
			ext = os.path.splitext(income_certificate_name.lower())[1]
			if ext not in allowed_extensions:
				frappe.throw(frappe._("Income Certificate must be a PDF, JPG, or PNG file."))

			if "," in income_certificate_data:
				income_certificate_data = income_certificate_data.split(",")[1]

			file_content = base64.b64decode(income_certificate_data)

			# Validate size (Max 5MB)
			if len(file_content) > 5 * 1024 * 1024:
				frappe.throw(frappe._("Income Certificate file size must not exceed 5MB."))

			_file = frappe.get_doc({
				"doctype": "File",
				"file_name": income_certificate_name,
				"content": file_content,
				"is_private": 1
			})
			_file.insert(ignore_permissions=True)
			income_cert_url = _file.file_url
		except Exception as e:
			frappe.log_error(f"File upload error (Income): {e}", "Scholarship Application Debug")
			frappe.throw(frappe._("Failed to upload Income Certificate: {0}").format(str(e)))

	supporting_docs_url = None
	if supporting_documents_data and supporting_documents_name:
		try:
			import base64
			import os

			# Validate extension
			allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
			ext = os.path.splitext(supporting_documents_name.lower())[1]
			if ext not in allowed_extensions:
				frappe.throw(frappe._("Supporting Documents must be a PDF, JPG, or PNG file."))

			if "," in supporting_documents_data:
				supporting_documents_data = supporting_documents_data.split(",")[1]

			file_content = base64.b64decode(supporting_documents_data)

			# Validate size (Max 5MB)
			if len(file_content) > 5 * 1024 * 1024:
				frappe.throw(frappe._("Supporting Documents file size must not exceed 5MB."))

			_file = frappe.get_doc({
				"doctype": "File",
				"file_name": supporting_documents_name,
				"content": file_content,
				"is_private": 1
			})
			_file.insert(ignore_permissions=True)
			supporting_docs_url = _file.file_url
		except Exception as e:
			frappe.log_error(f"File upload error (Supporting): {e}", "Scholarship Application Debug")
			frappe.throw(frappe._("Failed to upload Supporting Documents: {0}").format(str(e)))

	# Create the application
	try:
		app = frappe.get_doc({
			"doctype": "Scholarship Application",
			"applicant_id": applicant.name,
			"applicant_name": applicant.candidate_name,
			"admission_cycle": applicant.admission_cycle,
			"campus": applicant.campus,
			"program": applicant.program,
			"scholarship_scheme": scheme,
			"family_income": flt(family_income),
			"income_certificate": income_cert_url,
			"supporting_documents": supporting_docs_url,
			"status": "Submitted",
			"workflow_state": "Submitted"
		})

		# Insert with ignore permissions to allow creation from portal
		app.insert(ignore_permissions=True)

		# Update file references
		if income_cert_url:
			frappe.db.set_value("File", {"file_url": income_cert_url}, {
				"attached_to_doctype": "Scholarship Application",
				"attached_to_name": app.name
			}, update_modified=False)
		if supporting_docs_url:
			frappe.db.set_value("File", {"file_url": supporting_docs_url}, {
				"attached_to_doctype": "Scholarship Application",
				"attached_to_name": app.name
			}, update_modified=False)

		frappe.db.commit()
		return app.name
	except Exception as e:
		frappe.log_error(f"Insert error: {e}", "Scholarship Application Debug")
		frappe.throw(str(e))

@frappe.whitelist()
def get_calculated_benefit(doc):
	if isinstance(doc, str):
		doc = frappe._dict(json.loads(doc))

	from slcm.admission.utils.scholarship_coverage_engine import calculate_scholarship_amount

	benefit = calculate_scholarship_amount(doc)
	final_fee = flt(doc.original_fee_amount or 0) - flt(benefit or 0)

	return {
		"benefit": benefit,
		"final_fee": final_fee
	}

@frappe.whitelist()
def sync_fee_assignment_manually(docname):
	"""
	Whitelisted method to manually trigger fee assignment sync from Client Script.
	"""
	doc = frappe.get_doc("Scholarship Application", docname)
	_validate_applicant_ownership_or_staff(doc.applicant_id)
	if doc.status == "Approved":
		doc.sync_fee_assignment()
	else:
		frappe.throw(frappe._("Fee assignment can only be synced for Approved applications."))

@frappe.whitelist()
def get_original_fee_amount(applicant_id, program, campus=None, cycle=None):
	"""
	Whitelisted method for JS access to fetch original fee amount.
	"""
	if not applicant_id or not program:
		return 0

	_validate_applicant_ownership_or_staff(applicant_id)

	from slcm.api.service.offer_service import OfferService
	from slcm.api.service.fee_service import FeeService

	# Resolve missing fields from Applicant
	if not campus or not cycle:
		details = frappe.db.get_value("Applicant", applicant_id, ["campus", "admission_cycle"], as_dict=1)
		if details:
			campus = campus or details.campus
			cycle = cycle or details.admission_cycle

	if not campus or not cycle:
		return 0

	try:
		admission_year = OfferService.resolve_admission_year(applicant_id, campus, cycle)
		if not admission_year:
			return 0

		config = OfferService.get_config(admission_year, cycle, campus)

		fee_structure_name = None
		for row in config.fee_structure:
			fs_program = frappe.db.get_value("Fee Structure", row.fee_structure, "program")
			if fs_program == program:
				fee_structure_name = row.fee_structure
				break

		if fee_structure_name:
			nationality = frappe.db.get_value("Applicant", applicant_id, "nationality")
			is_foreign = nationality != "Indian"
			fee_data = FeeService._calculate_and_freeze_fees(fee_structure_name, is_foreign=is_foreign)
			return flt(fee_data.get("total_payable") or 0)
	except Exception:
		pass

	return 0


@frappe.whitelist()
def get_applicant_details():
	"""Returns the applicant record for the current user based on session email."""
	user = frappe.session.user
	if user == "Guest" or not user:
		return None

	applicant = frappe.db.get_value("Applicant", {"email": user},
		["name", "candidate_name", "program", "campus", "admission_cycle"], as_dict=1)
	return applicant


@frappe.whitelist()
def get_eligible_scholarship_schemes(applicant_id, program, campus, admission_cycle):
	"""Returns a list of eligible scholarship schemes for the applicant."""
	if not all([applicant_id, program, campus, admission_cycle]):
		return []

	_validate_applicant_ownership_or_staff(applicant_id)

	schemes = frappe.get_all(
		"Scholarship Scheme",
		filters={
			"admission_cycle": admission_cycle,
			"campus": campus,
			"status": "Active"
		},
		fields=["name", "program", "category", "scholarship_for"]
	)

	applicant_categories = frappe.get_all("Applicant Category", filters={"parent": applicant_id}, fields=["category"])
	applicant_category_names = [c.category for c in applicant_categories]

	foriegn_national = frappe.db.get_value("Applicant", applicant_id, "foriegn_national")
	applicant_type = "International" if foriegn_national == "Yes" else "Domestic"

	eligible_schemes = []
	for s in schemes:
		# Check target applicant type match
		target_for = s.get("scholarship_for") or "Domestic"
		if target_for != applicant_type:
			continue

		# Check program match (scheme has specific program or is global)
		program_match = not s.program or s.program == program

		# Check category match (scheme has specific category or is global)
		category_match = not s.category or s.category in applicant_category_names

		if program_match and category_match:
			eligible_schemes.append(s.name)

	return list(set(eligible_schemes))


def _validate_applicant_ownership_or_staff(applicant_id):
	user = frappe.session.user
	if user == "Administrator" or getattr(frappe.flags, "in_test", False):
		return

	staff_roles = {
		"System Manager",
		"Admission Admin",
		"Academic Manager",
		"Scholarship Manager",
		"Academic User",
	}
	user_roles = set(frappe.get_roles(user))
	if staff_roles.intersection(user_roles):
		return

	applicant_data = frappe.db.get_value("Applicant", applicant_id, ["email", "owner"], as_dict=True)
	if not applicant_data:
		frappe.throw(frappe._("Applicant record not found."), frappe.PermissionError)

	if user not in (applicant_data.email, applicant_data.owner):
		frappe.throw(frappe._("Not authorized to access data for this applicant."), frappe.PermissionError)

