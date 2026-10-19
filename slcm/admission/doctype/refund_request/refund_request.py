import frappe
import json
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, flt

from slcm.admission.utils.withdrawal_sync import sync_student_records_for_withdrawn_application

class RefundRequest(Document):
	def on_update(self):
		if self.admission_cancellation:
			self.sync_cancellation_status()

	def sync_cancellation_status(self):
		# Map Refund Request status to Admission Cancellation status
		status_map = {
			"Approved": "Approved",
			"Processing": "Approved",
			"Processed": "Completed"
		}
		
		new_status = status_map.get(self.status)
		if new_status:
			frappe.db.set_value("Admission Cancellation", self.admission_cancellation, "status", new_status)
		
		if self.status == "Processed":
			self.sync_linked_docs()

	def sync_linked_docs(self):
		"""
		Update linked Offer Letter, Student Master, Applicant, and Seat Allocation statuses.
		Releases the seat for reallocation.
		"""
		if not self.admission_cancellation:
			return

		# Ensure "Withdrawn" status exists in Applicant Status
		if not frappe.db.exists("Applicant Status", "Withdrawn"):
			frappe.get_doc({
				"doctype": "Applicant Status",
				"status": "Withdrawn"
			}).insert(ignore_permissions=True)

		# Fetch Admission Cancellation details
		cancellation = frappe.get_doc("Admission Cancellation", self.admission_cancellation)
		
		# 1. Update Offer Letter Status to Withdrawn
		if cancellation.offer:
			frappe.db.set_value("Offer Letter", cancellation.offer, "status", "Withdrawn")
			
		# 2. Student Master (Current Status = Withdrawn) + Student Enrollment = Dropped (if linked)
		sync_student_records_for_withdrawn_application(
			self.applicant,
			status_remark=_("Admission withdrawn and refund processed: {0}").format(self.name),
		)

		# 3. Update Applicant Status to Withdrawn
		frappe.db.set_value("Applicant", self.applicant, "status", "Withdrawn")

		# 4. Release Seat in Seat Allocation
		# We need to find the specific row in the Seat Allocation child table
		seat_row = frappe.db.get_value("Seat Selection Applicant", {
			"applicant_id": self.applicant,
			"selection_status": ["in", ["Selected", "Offer Issued", "Offer Accepted", "Confirmation Fee Paid", "Full Fee Paid", "Accepted"]]
		}, "name")

		if seat_row:
			# Update the status to Withdrawn
			frappe.db.set_value("Seat Selection Applicant", seat_row, "selection_status", "Withdrawn")
			
			# Find the parent Seat Allocation document to trigger waitlist promotion
			parent_allocation = frappe.db.get_value("Seat Selection Applicant", seat_row, "parent")
			if parent_allocation:
				allocation_doc = frappe.get_doc("Seat Allocation", parent_allocation)
				# Triggering save will fire the waitlist promotion logic defined in SeatAllocation.before_save/on_update
				# We set a flag to ensure the promotion logic knows this was a rejection/withdrawal
				allocation_doc.save(ignore_permissions=True)
				frappe.logger().info(f"Seat released for Applicant {self.applicant} in Allocation {parent_allocation}")

	def validate(self):
		self.validate_afa_fee_type()
		self.fetch_payment_details()
		self.apply_refund_policy()
		self.handle_refund_type()
		self.validate_refund_amount()
		self.set_approval_details()
		# NOTE: process_gateway_refund() is intentionally NOT called here.
		# Gateway refunds are only triggered via the 'Process Refund' button
		# (slcm.admission_cancel_api.process_refund) which sets a Processing lock
		# before calling Razorpay, preventing duplicate API calls.


	def validate_afa_fee_type(self):
		"""Ensure only Admission Fee or Confirmation Fee type AFA can be linked to a Refund Request."""
		if self.applicant_fee_assignment:
			fee_type = frappe.db.get_value(
				"Applicant Fee Assignment", self.applicant_fee_assignment, "fee_type"
			)
			if fee_type not in ("Admission Fee", "Confirmation Fee"):
				frappe.throw(
					_("Only 'Admission Fee' or 'Confirmation Fee' Applicant Fee Assignments can be linked to a Refund Request. "
					  "The selected assignment is of type '{0}'.").format(fee_type or "Unknown")
				)

	def fetch_payment_details(self):
		"""Resolve payment details from Applicant Fee Assignment → Applicant Payment Receipt."""
		if self.applicant_fee_assignment and not self.razorpay_payment_id:
			afa = frappe.db.get_value(
				"Applicant Fee Assignment",
				self.applicant_fee_assignment,
				["offer_letter", "fee_type"],
				as_dict=True
			)
			if afa and afa.offer_letter:
				# For Confirmation Fee, find the receipt with fee_type = Confirmation Fee
				# For Admission Fee, find the most recent receipt for the offer
				receipt_filters = {
					"offer_letter": afa.offer_letter,
					"docstatus": ["<", 2]
				}
				if afa.fee_type == "Confirmation Fee":
					receipt_filters["fee_type"] = "Confirmation Fee"
				receipt_name = frappe.db.get_value(
					"Applicant Payment Receipt",
					receipt_filters,
					"name",
					order_by="creation desc"
				)
				if receipt_name:
					self.applicant_payment_receipt = receipt_name

		if self.applicant_payment_receipt and not self.razorpay_payment_id:
			receipt = frappe.get_doc("Applicant Payment Receipt", self.applicant_payment_receipt)
			# Use net_amount (post-scholarship) as the actual amount paid
			self.amount_paid = flt(receipt.net_amount) if flt(receipt.get('net_amount')) > 0 else flt(receipt.total_amount)
			self.razorpay_payment_id = receipt.transaction_id

	def apply_refund_policy(self):
		if self.refund_type == "Full" and not self.applicant_fee_assignment and not self.applicant_payment_receipt:
			self.refund_amount = self.amount_paid
			return
		
		if self.refund_type == "No Refund":
			self.refund_amount = 0
			return

		# Check if this request is specifically for Confirmation Fee
		is_conf_fee = False
		if self.applicant_fee_assignment:
			afa_fee_type = frappe.db.get_value("Applicant Fee Assignment", self.applicant_fee_assignment, "fee_type")
			if afa_fee_type == "Confirmation Fee":
				is_conf_fee = True
		if not is_conf_fee and self.applicant_payment_receipt:
			apr_fee_type = frappe.db.get_value("Applicant Payment Receipt", self.applicant_payment_receipt, "fee_type")
			if apr_fee_type and "Confirmation" in apr_fee_type:
				is_conf_fee = True

		amount_paid = flt(self.amount_paid)
		from slcm.admission.utils.refund import get_applicant_refund_policies
		res = get_applicant_refund_policies(self.applicant)

		if is_conf_fee:
			is_conf_refundable = res.get("is_confirmation_fee_refundable", False)
			conf_pct = flt(res.get("confirmation_fee_refund_percentage") or 0.0) if is_conf_refundable else 0.0
			self.refund_amount = round(amount_paid * (conf_pct / 100.0), 2)
			if conf_pct == 100:
				self.refund_type = "Full"
			elif conf_pct == 0:
				self.refund_type = "No Refund"
			else:
				self.refund_type = "Partial"
			return

		# Course Fee Refund Policy calculation
		policies = res.get("policies", [])
		days = res.get("days_since_payment", 0)

		if not self.refund_policy:
			if not policies:
				self.refund_type = "No Refund"
				self.refund_amount = 0
				return

			sorted_policies = sorted(policies, key=lambda p: p.get("days_from_payment", 0))
			for p in sorted_policies:
				if days <= p.get("days_from_payment"):
					self.refund_policy = p.get("policy_name")
					break
			if not self.refund_policy and sorted_policies:
				self.refund_type = "No Refund"
				self.refund_amount = 0
				return

		if self.refund_policy:
			percentage = 0
			for p in policies:
				if p.get("policy_name") == self.refund_policy:
					percentage = flt(p.get("refund_percentage"))
					break
			
			if not percentage:
				percentage = flt(frappe.db.get_value("Refund Policy", self.refund_policy, "refund_percentage"))

			self.refund_amount = round(amount_paid * (percentage / 100.0), 2)


	def handle_refund_type(self):
		if self.refund_type == "Full" and not flt(self.refund_amount):
			self.refund_amount = self.amount_paid
		elif self.refund_type == "No Refund":
			self.refund_amount = 0


	def validate_refund_amount(self):
		if flt(self.refund_amount) > flt(self.amount_paid):
			frappe.throw(_("Refund Amount cannot be greater than Amount Paid ({0})").format(self.amount_paid))

		ref_field = None
		ref_value = None
		if self.applicant_payment_receipt:
			ref_field = "applicant_payment_receipt"
			ref_value = self.applicant_payment_receipt
			frappe.db.sql("SELECT name FROM `tabApplicant Payment Receipt` WHERE name = %s FOR UPDATE", ref_value)
		elif self.applicant_fee_assignment:
			ref_field = "applicant_fee_assignment"
			ref_value = self.applicant_fee_assignment
			frappe.db.sql("SELECT name FROM `tabApplicant Fee Assignment` WHERE name = %s FOR UPDATE", ref_value)

		if ref_field and ref_value:
			already_refunded = frappe.db.sql(f"""
				SELECT SUM(refund_amount) FROM `tabRefund Request`
				WHERE {ref_field} = %s AND name != %s AND status NOT IN ('Rejected', 'Failed')
				""", (ref_value, self.name))[0][0] or 0
			
			if flt(already_refunded) + flt(self.refund_amount) > flt(self.amount_paid):
				frappe.throw(_(
					"Total refund amount ({0}) would exceed the original amount paid ({1}). "
					"Already refunded/pending: {2}."
				).format(
					flt(already_refunded) + flt(self.refund_amount),
					self.amount_paid,
					already_refunded
				))

		# Allow 0 for No Refund type; otherwise enforce positive amount
		if self.refund_type != "No Refund" and flt(self.refund_amount) <= 0:
			frappe.throw(_("Refund Amount must be greater than 0"))

	def set_approval_details(self):
		if self.status == "Approved":
			if not self.approved_by:
				self.approved_by = frappe.session.user
				self.approval_date = now_datetime()
		elif self.status not in ["Processed", "Failed"]:
			self.approved_by = None
			self.approval_date = None

	def process_gateway_refund(self):
		if self.status == "Processed" and not self.razorpay_refund_id:
			if self.razorpay_payment_id and str(self.razorpay_payment_id).startswith("pay_"):
				from slcm.api.service.razorpay_utils import get_razorpay_client
				try:
					client = get_razorpay_client()
					amount_in_paise = int(flt(self.refund_amount) * 100)
					
					refund_response = client.refund.create({
						"payment_id": self.razorpay_payment_id,
						"amount": amount_in_paise,
						"notes": {
							"refund_request": self.name
						}
					}, {
						"X-Refund-Idempotency": self.name
					})
					
					if refund_response and refund_response.get("id"):
						self.razorpay_refund_id = refund_response.get("id")
						self.refund_date = now_datetime()
						self.create_refund_transaction(
							status="Processed",
							response=refund_response
						)
					else:
						frappe.throw(_("Failed to process refund at the gateway. Empty response received."))
				except Exception as e:
					frappe.log_error(frappe.get_traceback(), _("Razorpay Refund Processing Error"))
					self.create_refund_transaction(
						status="Failed",
						failure_reason=str(e)
					)
					frappe.throw(_("Gateway Refund Failed: {0}").format(str(e)))
			else:
				# Log processed cash/manual refund transaction
				self.create_refund_transaction(status="Processed")

	def create_refund_transaction(self, status, response=None, failure_reason=None):
		if not frappe.db.exists("Refund Transaction", {"refund_request": self.name, "status": status}):
			txn = frappe.get_doc({
				"doctype": "Refund Transaction",
				"refund_request": self.name,
				"applicant_fee_assignment": self.get("applicant_fee_assignment"),
				"razorpay_payment_id": self.razorpay_payment_id,
				"razorpay_refund_id": self.razorpay_refund_id or (response.get("id") if response else None),
				"refund_amount": flt(self.refund_amount),
				"status": status,
				"processed_at": now_datetime(),
				"gateway_response": json.dumps(response) if response else None,
				"failure_reason": failure_reason
			})
			txn.insert(ignore_permissions=True)

	def on_trash(self):
		"""
		Breaks the circular link with Admission Cancellation to allow deletion.
		"""
		if self.admission_cancellation:
			# Unset the link in the parent cancellation record
			frappe.db.set_value("Admission Cancellation", self.admission_cancellation, "refund_request", None)
			frappe.db.commit()

@frappe.whitelist()
def create_refund_request(cancellation):
	if isinstance(cancellation, str):
		cancellation = frappe.get_doc("Admission Cancellation", cancellation)

	created_refunds = []

	receipt_name = cancellation.get("applicant_payment_receipt")
	if receipt_name:
		receipts = frappe.get_all(
			"Applicant Payment Receipt",
			filters={"name": receipt_name},
			fields=["name", "fee_type", "net_amount", "total_amount", "transaction_id", "offer_letter", "assignment"]
		)
	else:
		receipts = frappe.get_all(
			"Applicant Payment Receipt",
			filters={"applicant": cancellation.applicant, "docstatus": ["<", 2]},
			fields=["name", "fee_type", "net_amount", "total_amount", "transaction_id", "offer_letter", "assignment"],
			order_by="creation asc"
		)


	# Also fetch refund policies to know percentages
	from slcm.admission.utils.refund import get_applicant_refund_policies
	res_ref = get_applicant_refund_policies(cancellation.applicant)
	policies = res_ref.get("policies", [])
	days = res_ref.get("days_since_payment", 0)
	
	is_conf_refundable = res_ref.get("is_confirmation_fee_refundable", False)
	conf_fee_pct = flt(res_ref.get("confirmation_fee_refund_percentage") or 0.0) if is_conf_refundable else 0.0

	# Find active course policy percentage
	course_policy_pct = 0.0
	sorted_policies = sorted(policies, key=lambda p: p.get("days_from_payment", 0))
	for p in sorted_policies:
		if days <= p.get("days_from_payment", 0):
			course_policy_pct = flt(p.get("refund_percentage", 0))
			break
	if not course_policy_pct and sorted_policies:
		course_policy_pct = flt(sorted_policies[-1].get("refund_percentage", 0))

	# Process each receipt (Confirmation Fee vs Course/Admission Fee)
	for r in receipts:
		existing_rr = frappe.db.get_value(
			"Refund Request",
			{"applicant_payment_receipt": r.name, "status": ["not in", ["Rejected", "Failed"]]},
			"name"
		)
		if existing_rr:
			if not frappe.db.get_value("Refund Request", existing_rr, "admission_cancellation"):
				frappe.db.set_value("Refund Request", existing_rr, "admission_cancellation", cancellation.name)
			created_refunds.append(existing_rr)
			continue

		amt_paid = flt(r.net_amount) if flt(r.get("net_amount")) > 0 else flt(r.total_amount)

		if amt_paid <= 0:
			continue

		ft = r.fee_type or ""
		if not ft and r.get("assignment"):
			ft = frappe.db.get_value("Applicant Fee Assignment", r.assignment, "fee_type") or ""

		# Application / Form Fee is non-refundable on admission cancellation
		if "Application" in ft or "Form" in ft:
			continue

		is_conf = "Confirmation" in ft
		
		ref_pct = conf_fee_pct if is_conf else course_policy_pct
		ref_amt = round(amt_paid * (ref_pct / 100.0), 2)
		if ref_amt <= 0:
			continue

		# Resolve AFA for this receipt
		afa_name = r.get("assignment")
		if not afa_name:
			afa_type = "Confirmation Fee" if is_conf else "Admission Fee"
			afa_name = frappe.db.get_value("Applicant Fee Assignment", {
				"applicant": cancellation.applicant,
				"fee_type": afa_type,
				"status": "Paid",
				"docstatus": ["!=", 2]
			}, "name", order_by="creation desc")

		# Create individual Refund Request for this specific transaction ID
		refund = frappe.new_doc("Refund Request")
		refund.applicant = cancellation.applicant
		refund.admission_cancellation = cancellation.name
		refund.status = "Under Review"
		refund.refund_reason = cancellation.cancellation_reason
		if afa_name:
			refund.applicant_fee_assignment = afa_name
		refund.applicant_payment_receipt = r.name
		refund.razorpay_payment_id = r.transaction_id
		refund.amount_paid = amt_paid
		refund.refund_amount = ref_amt
		refund.refund_type = "Full" if ref_pct == 100 else ("No Refund" if ref_pct == 0 else "Partial")
		
		refund.insert(ignore_permissions=True)
		created_refunds.append(refund.name)

	# Fallback: If no receipts found, use direct cancellation razorpay_id
	if not created_refunds and (cancellation.get("razorpay_id") or cancellation.get("amount_paid")):
		amt_paid = flt(cancellation.amount_paid)
		if amt_paid > 0:
			refund = frappe.new_doc("Refund Request")
			refund.applicant = cancellation.applicant
			refund.admission_cancellation = cancellation.name
			refund.status = "Under Review"
			refund.refund_reason = cancellation.cancellation_reason
			refund.razorpay_payment_id = cancellation.razorpay_id
			refund.amount_paid = amt_paid
			refund.refund_amount = amt_paid
			refund.refund_type = "Full"
			refund.insert(ignore_permissions=True)
			created_refunds.append(refund.name)

	return created_refunds[0] if created_refunds else None


