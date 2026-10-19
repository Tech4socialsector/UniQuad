#SLCM
import frappe
import json
from frappe import _
from frappe.utils import flt, now, now_datetime

try:
	import razorpay
except ImportError:
	razorpay = None

@frappe.whitelist()
def get_refund_policies(applicant=None, program=None, campus=None, offer=None, payment_request=None):
	"""
	Fetches refund policies mapped to the applicant's Fee Structure.
	If is_refund_available is unchecked or table is empty, returns empty list.
	"""
	from slcm.admission.utils.refund import get_applicant_refund_policies

	if not applicant:
		user_email = frappe.session.user
		applicant = frappe.db.get_value("Applicant", {"email": user_email}, "name")

	if not applicant:
		return {"policies": [], "days_since_payment": 0}

	res = get_applicant_refund_policies(applicant)
	
	policies = res.get("policies") or []
	
	# Resolve payment_request automatically if not provided
	if not payment_request:
		offer_name = offer or frappe.db.get_value(
			"Offer Letter",
			{"applicant": applicant, "status": ["not in", ["Rejected", "Withdrawn"]]},
			"name",
			order_by="creation desc"
		)
		if offer_name:
			payment_request = frappe.db.get_value(
				"Applicant Payment Receipt",
				{"offer_letter": offer_name, "docstatus": ["<", 2]},
				"name",
				order_by="creation desc"
			)

	conf_fee_paid = 0.0
	course_fee_paid = 0.0

	offer_name = offer or frappe.db.get_value(
		"Offer Letter",
		{"applicant": applicant, "status": ["not in", ["Rejected", "Withdrawn"]]},
		"name",
		order_by="creation desc"
	)

	# 1. Fetch from Applicant Payment Receipt (by offer_letter or applicant)
	receipt_filters = {"docstatus": ["<", 2]}
	if offer_name:
		receipt_filters["offer_letter"] = offer_name
	else:
		receipt_filters["applicant"] = applicant

	receipts = frappe.get_all(
		"Applicant Payment Receipt",
		filters=receipt_filters,
		fields=["name", "total_amount", "net_amount", "fee_type", "currency"]
	)

	if not receipts and offer_name:
		receipts = frappe.get_all(
			"Applicant Payment Receipt",
			filters={"applicant": applicant, "docstatus": ["<", 2]},
			fields=["name", "total_amount", "net_amount", "fee_type", "currency"]
		)

	for r in receipts:
		amt = flt(r.net_amount) if flt(r.get("net_amount")) > 0 else flt(r.total_amount)
		ft = r.fee_type or ""
		if "Confirmation" in ft:
			conf_fee_paid += amt
		else:
			course_fee_paid += amt

	# 2. Check Applicant Fee Assignment (if paid)
	if offer_name:
		afas = frappe.get_all(
			"Applicant Fee Assignment",
			filters={"offer_letter": offer_name, "status": "Paid", "docstatus": ["!=", 2]},
			fields=["fee_type", "final_payable_amount", "total_amount", "confirmation_fee"]
		)
		for afa in afas:
			amt = flt(afa.final_payable_amount or afa.total_amount or afa.confirmation_fee)
			ft = afa.fee_type or ""
			if "Confirmation" in ft and conf_fee_paid == 0:
				conf_fee_paid += amt
			elif "Admission" in ft and course_fee_paid == 0:
				course_fee_paid += amt

	# 3. Check Student Master & Fee Payment (if converted to student)
	student_name = frappe.db.get_value("Student Master", {"application_number": applicant}, "name")
	if student_name:
		fee_payments = frappe.get_all(
			"Fee Payment",
			filters={"student": student_name, "status": "Submitted"},
			pluck="amount"
		)
		for fp in fee_payments:
			course_fee_paid += flt(fp)



	amount_paid = conf_fee_paid + course_fee_paid
	currency = "INR"

	is_conf_ref = bool(res.get("is_confirmation_fee_refundable", False))
	conf_pct = flt(res.get("confirmation_fee_refund_percentage") or 0.0) if is_conf_ref else 0.0
	conf_fee_ref_amt = round(conf_fee_paid * (conf_pct / 100.0), 2)

	for p in policies:
		desc = frappe.db.get_value("Refund Policy", p.get("policy_name"), "description")
		p["description"] = desc or ""
		course_ref_amt = flt(course_fee_paid) * (flt(p.get("refund_percentage", 0)) / 100.0)
		p["amount"] = round(conf_fee_ref_amt + course_ref_amt, 2)
		p["currency"] = currency

	return {
		"policies": policies,
		"days_since_payment": res.get("days_since_payment") or 0,
		"conf_fee_paid": conf_fee_paid,
		"course_fee_paid": course_fee_paid,
		"amount_paid": amount_paid,
		"currency": currency,
		"is_confirmation_fee_refundable": is_conf_ref,
		"confirmation_fee_refund_percentage": conf_pct
	}





@frappe.whitelist()
def process_refund(name):
	frappe.has_permission("Refund Request", "write", throw=True)
	refund = frappe.get_doc("Refund Request", name)
	
	if refund.status == "Processed":
		frappe.throw(_("Refund Request has already been processed."))

	if refund.status != "Approved":
		frappe.throw(_("Refund Request must be Approved before processing."))

	if refund.refund_type == "No Refund":
		# No payment needed, just close the cycle
		refund.db_set("status", "Processed")
		refund.db_set("refund_date", now_datetime())
		refund.db_set("failure_message", "")
		
		# Create a 0-amount transaction for audit trail
		rt = frappe.new_doc("Refund Transaction")
		rt.refund_request = refund.name
		rt.applicant_fee_assignment = refund.get("applicant_fee_assignment")
		rt.razorpay_payment_id = refund.razorpay_payment_id
		rt.razorpay_refund_id = "INTERNAL_NO_REFUND"
		rt.refund_amount = 0
		rt.status = "Processed"
		rt.processed_at = now_datetime()
		rt.gateway_response = json.dumps({"note": "Refund skipped: Processed as 'No Refund' in system."})
		rt.insert(ignore_permissions=True)
		
		# Sync statuses (closes the Admission Cancellation)
		refund.sync_cancellation_status()
		
		return {"status": "Success", "message": _("Refund Request (No Refund) has been closed successfully.")}

	if not refund.razorpay_payment_id:
		frappe.throw(_("Cannot process refund: No Razorpay Payment ID found on this request."))

	if refund.razorpay_refund_id:
		# If ID exists but status is not Processed, try to sync it
		return update_razorpay_refund_status(name)
	
	# Set status to Processing immediately to prevent concurrent calls
	refund.db_set("status", "Processing")
	frappe.db.commit()
	
	if not razorpay:
		refund.db_set("status", "Failed")
		frappe.throw(_("Razorpay library is not installed."))
		
	# Razorpay Integration
	settings = frappe.get_single("Razorpay Settings")
	if not settings.api_key or not settings.api_secret:
		refund.db_set("status", "Failed")
		frappe.throw(_("Razorpay API Key or Secret not configured."))
		
	client = razorpay.Client(auth=(settings.api_key, settings.get_password("api_secret")))
	
	try:
		# Pre-check: verify available balance on Razorpay payment before attempting refund
		try:
			rzp_payment = client.payment.fetch(refund.razorpay_payment_id)
			rzp_amount = int(rzp_payment.get("amount", 0))
			amount_to_refund_paise = int(flt(refund.refund_amount) * 100)
			
			# Only block if Razorpay returned a valid non-zero amount AND it is truly insufficient.
			# If rzp_amount == 0, Razorpay may be in test mode or the payment is not accessible via the
			# current credentials — skip this pre-check and let the actual refund API call handle it.
			if rzp_amount > 0:
				amount_refunded_paise = int(rzp_payment.get("amount_refunded", 0))
				available_paise = rzp_amount - amount_refunded_paise
				
				if available_paise < amount_to_refund_paise:
					error_msg = _("Insufficient balance in Razorpay payment. Available: {0}, Requested: {1}").format(
						available_paise / 100.0, refund.refund_amount
					)
					refund.db_set("status", "Failed")
					refund.db_set("failure_message", error_msg)
					return {"status": "Error", "message": error_msg}
		except Exception as e:
			# If fetch fails, proceed and let the refund call itself surface any errors.
			frappe.log_error(f"Razorpay Fetch Error before refund: {str(e)}", "Refund Process")

		# Initiate refund via Razorpay API
		refund_data = {
			"amount": int(refund.refund_amount * 100), # Amount in paise
			"speed": "normal",
			"notes": {
				"refund_request": refund.name,
				"applicant": refund.applicant
			}
		}
		
		rzp_refund = client.payment.refund(refund.razorpay_payment_id, refund_data)
		
		if rzp_refund.get("id"):
			refund.db_set("razorpay_refund_id", rzp_refund.get("id"))
			refund.db_set("status", "Processed")
			refund.db_set("refund_date", now_datetime())
			refund.db_set("failure_message", "")
			
			# Create Refund Transaction
			rt = frappe.new_doc("Refund Transaction")
			rt.refund_request = refund.name
			rt.applicant_fee_assignment = refund.get("applicant_fee_assignment")
			rt.razorpay_payment_id = refund.razorpay_payment_id
			rt.razorpay_refund_id = rzp_refund.get("id")
			rt.refund_amount = refund.refund_amount
			rt.status = "Processed"
			rt.processed_at = now_datetime()
			
			# Add human-readable date for gateway response
			if rzp_refund.get("created_at"):
				from frappe.utils import format_datetime, get_datetime
				rzp_refund["processed_date"] = format_datetime(get_datetime(rzp_refund.get("created_at")))
				
			rt.gateway_response = json.dumps(rzp_refund, indent=4)
			rt.insert(ignore_permissions=True)
			
			# Trigger sync
			refund.sync_cancellation_status()

			# Notify applicant
			try:
				from slcm.admission.notification_service import notify_refund_processed
				notify_refund_processed(refund.name)
			except Exception as e:
				frappe.log_error(f"Refund Notification Failed: {str(e)}", "Refund Process")
			
			return {"status": "Success", "message": _("Refund processed successfully.")}
		else:
			refund.db_set("status", "Failed")
			error_msg = _("Refund failed at Razorpay: empty response received.")
			refund.db_set("failure_message", error_msg)
			return {"status": "Error", "message": error_msg}
			
	except Exception as e:
		refund.db_set("status", "Failed")
		error_detail = str(e)
		refund.db_set("failure_message", error_detail)
		frappe.log_error(frappe.get_traceback(), _("Razorpay Refund Error"))
		return {"status": "Error", "message": _("Razorpay Error: {0}").format(error_detail)}

@frappe.whitelist()
def process_bulk_refunds(names):
	frappe.has_permission("Refund Request", "write", throw=True)
	if isinstance(names, str):
		names = json.loads(names)
	
	results = []
	for name in names:
		try:
			res = process_refund(name)
			results.append({
				"name": name,
				"status": res.get("status"),
				"message": res.get("message")
			})
		except Exception as e:
			results.append({
				"name": name,
				"status": "Error",
				"message": str(e)
			})
	
	return results

@frappe.whitelist()
def update_razorpay_refund_status(name):
	"""
	Fetches the latest status of a refund from Razorpay API 
	and updates the Refund Request accordingly.
	"""
	refund = frappe.get_doc("Refund Request", name)
	
	if not refund.razorpay_refund_id:
		frappe.throw(_("No Razorpay Refund ID found to check status."))

	if not razorpay:
		frappe.throw(_("Razorpay library is not installed."))
		
	from slcm.api.service.razorpay_utils import get_razorpay_client
	client = get_razorpay_client()
	
	try:
		# Fetch status from Razorpay
		rzp_refund = client.refund.fetch(refund.razorpay_refund_id)
		rzp_status = rzp_refund.get("status") # e.g., 'processed', 'pending', 'failed'
		
		if rzp_status == "processed":
			# If it was previously Processing or Failed, mark as Processed
			if refund.status != "Processed":
				refund.db_set("status", "Processed")
				if not refund.refund_date:
					refund.db_set("refund_date", now_datetime())
				refund.db_set("failure_message", "")
				refund.sync_cancellation_status()
				return {"status": "Success", "message": _("Refund is officially PROCESSED at Razorpay.")}
			else:
				# Even if already processed, provide a more reassuring confirmation message
				from frappe.utils import format_datetime
				date_str = format_datetime(refund.refund_date) if refund.refund_date else "recently"
				return {
					"status": "Success", 
					"message": _("Verified: Razorpay confirms this refund was successfully processed on {0}. (Refund ID: {1})").format(date_str, refund.razorpay_refund_id)
				}
				
		elif rzp_status == "failed":
			error_code = rzp_refund.get("error_code", "Unknown")
			error_desc = rzp_refund.get("error_description", "No description provided")
			
			refund.db_set("status", "Failed")
			refund.db_set("failure_message", f"Razorpay Failure: {error_code} - {error_desc}")
			return {"status": "Error", "message": _("Refund has FAILED at Razorpay: {0}").format(error_desc)}
			
		else:
			# Status like 'pending'
			return {"status": "Info", "message": _("Refund status at Razorpay is: {0}").format(rzp_status.upper())}
			
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Razorpay Refund Status Check Error"))
		return {"status": "Error", "message": str(e)}

@frappe.whitelist()
def reconcile_refund_status(name):
	"""
	Reconciles a refund request with Razorpay.
	If razorpay_refund_id is already set, it checks its status.
	If not set, it queries Razorpay for refunds on the associated payment_id
	and tries to find one matching this refund request name in notes.
	"""
	refund = frappe.get_doc("Refund Request", name)
	
	if not razorpay:
		frappe.throw(_("Razorpay library is not installed."))
		
	from slcm.api.service.razorpay_utils import get_razorpay_client
	client = get_razorpay_client()
	
	# Case 1: razorpay_refund_id is already known, query its status directly
	if refund.razorpay_refund_id:
		return update_razorpay_refund_status(name)
		
	# Case 2: razorpay_refund_id is not set, search by payment_id
	if not refund.razorpay_payment_id:
		frappe.throw(_("Cannot reconcile: No Razorpay Payment ID or Refund ID found on this request."))
		
	try:
		# Fetch all refunds for the payment
		res = client.refund.all({"payment_id": refund.razorpay_payment_id})
		items = res.get("items") or []
		
		matched_rzp_refund = None
		for item in items:
			# Check if notes contains the refund request name
			notes = item.get("notes") or {}
			if notes.get("refund_request") == refund.name:
				matched_rzp_refund = item
				break
			
		if matched_rzp_refund:
			rzp_refund_id = matched_rzp_refund.get("id")
			rzp_status = matched_rzp_refund.get("status")
			
			refund.db_set("razorpay_refund_id", rzp_refund_id)
			
			if rzp_status == "processed":
				refund.db_set("status", "Processed")
				if not refund.refund_date:
					refund.db_set("refund_date", now_datetime())
				refund.db_set("failure_message", "")
				
				# Create Refund Transaction if it doesn't exist
				if not frappe.db.exists("Refund Transaction", {"refund_request": refund.name, "status": "Processed"}):
					rt = frappe.new_doc("Refund Transaction")
					rt.refund_request = refund.name
					rt.applicant_fee_assignment = refund.get("applicant_fee_assignment")
					rt.razorpay_payment_id = refund.razorpay_payment_id
					rt.razorpay_refund_id = rzp_refund_id
					rt.refund_amount = refund.refund_amount
					rt.status = "Processed"
					rt.processed_at = now_datetime()
					
					if matched_rzp_refund.get("created_at"):
						from frappe.utils import format_datetime, get_datetime
						matched_rzp_refund["processed_date"] = format_datetime(get_datetime(matched_rzp_refund.get("created_at")))
					rt.gateway_response = json.dumps(matched_rzp_refund, indent=4)
					rt.insert(ignore_permissions=True)
					
				# Sync status
				refund.sync_cancellation_status()
				
				return {"status": "Success", "message": _("Refund reconciled successfully as PROCESSED. Razorpay Refund ID: {0}").format(rzp_refund_id)}
				
			elif rzp_status == "failed":
				error_code = matched_rzp_refund.get("error_code", "Unknown")
				error_desc = matched_rzp_refund.get("error_description", "No description provided")
				refund.db_set("status", "Failed")
				refund.db_set("failure_message", f"Razorpay Failure: {error_code} - {error_desc}")
				return {"status": "Error", "message": _("Refund was reconciled as FAILED at Razorpay: {0}").format(error_desc)}
			else:
				# Pending/other
				refund.db_set("status", "Processing")
				return {"status": "Info", "message": _("Refund was found on Razorpay with status: {0}").format(rzp_status.upper())}
		else:
			return {"status": "Info", "message": _("No matching refund attempt was found on Razorpay for this request.")}
			
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Razorpay Refund Reconciliation Error"))
		return {"status": "Error", "message": str(e)}

@frappe.whitelist()
def submit_admission_cancellation(**kwargs):

	"""
	Portal-safe method to submit admission cancellation.
	If separate payments exist (Confirmation Fee & Admission Fee), creates
	separate Admission Cancellation records for each fee payment.
	"""
	applicant = kwargs.get("applicant")
	
	if frappe.session.user != "Administrator":
		owner = frappe.db.get_value("Applicant", applicant, "owner")
		email = frappe.db.get_value("Applicant", applicant, "email")
		if owner != frappe.session.user and email != frappe.session.user:
			frappe.throw(_("Not permitted to cancel this admission."), frappe.PermissionError)

	offer = kwargs.get("offer")

	if offer in ("None", "", None):
		offer = frappe.db.get_value("Offer Letter", 
			{"applicant": applicant, "status": ["not in", ["Rejected", "Withdrawn", "Expired"]]}, 
			"name", order_by="creation desc")
	
	if not offer:
		frappe.throw(_("Could not find an active Offer Letter associated with your application."))

	# Check for existing active cancellation
	existing_cancellations = frappe.get_all("Admission Cancellation", {
		"applicant": applicant,
		"status": ["not in", ["Rejected"]]
	}, "name")
	
	if existing_cancellations:
		frappe.throw(_("A cancellation request has already been submitted."))

	# Find all active payment receipts for this applicant/offer
	receipts = frappe.get_all(
		"Applicant Payment Receipt",
		filters={"applicant": applicant, "docstatus": ["<", 2]},
		fields=["name", "fee_type", "total_amount", "net_amount", "transaction_id", "assignment"],
		order_by="creation asc"
	)
	

	from slcm.admission.utils.refund import get_applicant_refund_policies
	res_ref = get_applicant_refund_policies(applicant)
	is_conf_ref = bool(res_ref.get("is_confirmation_fee_refundable", False))

	# Filter receipts with paid amount > 0
	valid_receipts = []
	for r in receipts:
		amt = flt(r.net_amount) if flt(r.get("net_amount")) > 0 else flt(r.total_amount)
		if amt > 0:
			ft = r.fee_type or ""
			if not ft and r.get("assignment"):
				ft = frappe.db.get_value("Applicant Fee Assignment", r.assignment, "fee_type") or ""

			# Application/Form Fees are non-refundable during admission cancellation
			if "Application" in ft or "Form" in ft:
				continue

			if "Confirmation" in ft and not is_conf_ref:
				continue
			valid_receipts.append(r)


	created_cancellations = []

	if valid_receipts:
		# Create a separate Admission Cancellation record per fee payment receipt
		for r in valid_receipts:
			doc = frappe.new_doc("Admission Cancellation")
			doc.applicant = applicant
			doc.offer = offer
			doc.applicant_payment_receipt = r.name
			doc.campus = kwargs.get("campus")
			doc.program = kwargs.get("program")
			doc.cancellation_reason_type = kwargs.get("cancellation_reason_type")
			doc.cancellation_reason = kwargs.get("cancellation_reason")
			doc.additional_comments = kwargs.get("additional_comments")
			doc.cancellation_type = "Student"
			doc.status = "Initiated"
			doc.requested_by = frappe.session.user
			doc.requested_on = now_datetime()
			doc.amount_paid = flt(r.net_amount) if flt(r.get("net_amount")) > 0 else flt(r.total_amount)
			doc.razorpay_id = r.transaction_id
			doc.insert(ignore_permissions=True)
			created_cancellations.append(doc.name)
	else:
		# Fallback: create single cancellation record
		doc = frappe.new_doc("Admission Cancellation")
		doc.applicant = applicant
		doc.offer = offer
		doc.campus = kwargs.get("campus")
		doc.program = kwargs.get("program")
		doc.cancellation_reason_type = kwargs.get("cancellation_reason_type")
		doc.cancellation_reason = kwargs.get("cancellation_reason")
		doc.additional_comments = kwargs.get("additional_comments")
		doc.cancellation_type = "Student"
		doc.status = "Initiated"
		doc.requested_by = frappe.session.user
		doc.requested_on = now_datetime()
		doc.insert(ignore_permissions=True)
		created_cancellations.append(doc.name)

	frappe.db.commit()
	return {"status": "Success", "names": created_cancellations, "name": created_cancellations[0]}

