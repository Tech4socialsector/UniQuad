# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

@frappe.whitelist()
def create_pace_razorpay_order(assignment_name):
    """
    Creates/Gets a Razorpay order for a PACE Applicant Fee Assignment.
    Used by both Desk (Pay Now button) and Portal.
    """
    if not assignment_name or not frappe.db.exists("PACE Applicant Fee Assignment", assignment_name):
        frappe.throw(_("Fee Assignment {0} not found.").format(assignment_name))

    assignment = frappe.get_doc("PACE Applicant Fee Assignment", assignment_name)
    if assignment.status == "Paid":
        frappe.throw(_("This fee assignment has already been paid."))
    if assignment.status == "Draft":
        frappe.throw(_("Payment cannot be processed because this assignment is in Draft status."))

    # Block payment if the fee structure dates are invalid
    if assignment.fee_structure:
        fee_struct_details = frappe.db.get_value(
            "PACE Fee Structure",
            assignment.fee_structure,
            ["valid_from", "valid_to"],
            as_dict=True
        )
        if fee_struct_details:
            today_str = str(frappe.utils.today())
            if fee_struct_details.valid_from and str(fee_struct_details.valid_from) > today_str:
                frappe.throw(_("The payment period has not started yet. You can pay starting from {0}.").format(frappe.utils.format_date(fee_struct_details.valid_from)))
            if fee_struct_details.valid_to and str(fee_struct_details.valid_to) < today_str:
                frappe.throw(_("The payment period has ended. It closed on {0}.").format(frappe.utils.format_date(fee_struct_details.valid_to)))

    amount = flt(assignment.final_payable_amount)
    if amount <= 0:
        frappe.throw(_("Final payable amount must be greater than zero."))
    if assignment.status == "Paid":
        return {"already_paid": True, "message": _("This fee has already been paid.")}

    # 1. Get/Create Payment Request
    pr_name = frappe.db.get_value("SLCM Payment Request", {
        "reference_doctype": "PACE Applicant Fee Assignment",
        "reference_name": assignment_name,
        "docstatus": ["!=", 2]
    })

    if pr_name:
        pr = frappe.get_doc("SLCM Payment Request", pr_name)
        if pr.status == "Paid":
            return {
                "already_paid": True,
                "message": _("This fee has already been paid.")
            }
        # Cancel and recreate if amount changed or PR is Failed (gateway rejected the payment).
        # "Requested" PRs are reused — their order is still alive (within Razorpay's 15-min window).
        if pr.status == "Failed" or flt(pr.amount) != amount:
            try:
                from slcm.api.service.razorpay_utils import cancel_payment_request_for_retry
                cancel_payment_request_for_retry(pr)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "PACE Desk: cancel old Payment Request")
            pr = None
    else:
        pr = None

    # Resolve gateway from PACE Fee Structure (for Course Fee) or PACE Admission (for Application Fee)
    gateway = None
    if assignment.fee_type == "Course Fee" and assignment.fee_structure:
        gateway = frappe.db.get_value("PACE Fee Structure", assignment.fee_structure, "payment_gateway")
    elif assignment.fee_type == "Application Fee" and assignment.academic_year:
        gateway = frappe.db.get_value("PACE Admission", {"academic_year": assignment.academic_year, "status": "Active"}, "payment_gateway")
        if not gateway:
            gateway = frappe.db.get_value("PACE Admission", {"academic_year": assignment.academic_year}, "payment_gateway", order_by="creation desc")

    if not gateway:
        gateway = frappe.db.get_value("Payment Gateway", {}, "name") or "Razorpay"

    if not pr:
        pr = frappe.new_doc("SLCM Payment Request")
        pr.payment_gateway = gateway
        pr.currency = assignment.currency or "INR"
        pr.amount = amount
        pr.email_to = frappe.db.get_value("PACE Application", assignment.applicant, "email_address")
        pr.reference_doctype = "PACE Applicant Fee Assignment"
        pr.reference_name = assignment.name
        pr.flags.ignore_permissions = True
        pr.insert(ignore_permissions=True)
        pr.submit()

    # 2. Get/Create Razorpay Order
    try:
        from payments.utils import get_payment_gateway_controller
    except ImportError:
        from frappe.integrations.utils import get_payment_gateway_controller

    controller = get_payment_gateway_controller(gateway)

    from slcm.api.service.razorpay_utils import get_razorpay_client, prepare_checkout_order

    subject_label = _("Course Fee for {0}") if assignment.fee_type == "Course Fee" else _("Application Fee for {0}")
    subject = subject_label.format(assignment.program)
    payment_details = {
        "amount": amount,
        "currency": pr.currency,
        "receipt": (pr.name or "PACE")[:40],
        "description": (subject or "")[:255],
    }
    rzp_client = get_razorpay_client()
    order = prepare_checkout_order(rzp_client, controller, payment_details, pr, amount)
    order_id = (order or {}).get("id") or (order or {}).get("order_id") or ""
    if order_id:
        pr.db_set({"transaction_id": order_id, "razorpay_order_id": order_id})

    settings = frappe.get_single("Razorpay Settings")
    
    return {
        "order_id": order_id,
        "amount": int(amount * 100),
        "currency": pr.currency,
        "key_id": settings.get_password("api_key") if settings.api_key else settings.api_key,
        "payer_email": pr.email_to
    }


@frappe.whitelist()
def verify_pace_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, assignment_name):
    """
    Verifies Razorpay payment and updates assignment status.
    Called as callback from Desk/Portal JS.
    """
    from slcm.pace.web_form.pace_application_form.pace_application_form import verify_pace_payment_signature
    
    # We leverage the existing verification logic in pace_application_form.py
    return verify_pace_payment_signature(
        razorpay_payment_id=razorpay_payment_id,
        razorpay_order_id=razorpay_order_id,
        razorpay_signature=razorpay_signature,
        assignment_name=assignment_name
    )


def _update_pace_payment_request(
    assignment,
    gateway,
    transaction_id,
    status,
    payment_id=None,
    response_data=None,
    failure_reason=None,
):
    """
    Internal helper to update the linked Payment Request.
    """
    import json

    pr_name = frappe.db.get_value(
        "SLCM Payment Request",
        {
            "reference_doctype": "PACE Applicant Fee Assignment",
            "reference_name": assignment.name,
            "docstatus": ["!=", 2],
        },
        "name",
        order_by="creation desc",
    )

    if not pr_name:
        return

    if frappe.db.get_value("SLCM Payment Request", pr_name, "status") == "Paid":
        return

    update_data = {"status": status}

    if status == "Paid":
        update_data["failure_message"] = None
        update_data["gateway_status"] = "captured"
        update_data["paid_on"] = frappe.utils.now_datetime()
        if payment_id:
            update_data["transaction_id"] = payment_id
            update_data["razorpay_payment_id"] = payment_id
    else:
        if failure_reason:
            update_data["failure_message"] = failure_reason
            update_data["gateway_status"] = "failed"
        if transaction_id:
            update_data["transaction_id"] = transaction_id
            update_data["razorpay_order_id"] = transaction_id

    if gateway and frappe.db.exists("Payment Gateway", gateway):
        update_data["payment_gateway"] = gateway

    if response_data is not None:
        if isinstance(response_data, str):
            update_data["gateway_response"] = response_data
        else:
            update_data["gateway_response"] = json.dumps(response_data, indent=4)

    frappe.flags.payment_request_status_from_backend = True
    try:
        frappe.db.set_value("SLCM Payment Request", pr_name, update_data, update_modified=True)
    finally:
        if hasattr(frappe.flags, "payment_request_status_from_backend"):
            del frappe.flags.payment_request_status_from_backend


def _get_active_pace_admission_name(academic_year=None):
    """
    Internal helper to get the name of the currently active PACE Admission record.
    """
    filters = {"status": "Active"}
    if academic_year:
        filters["academic_year"] = academic_year
    return frappe.db.get_value("PACE Admission", filters, "name")


def sync_pace_payment_after_gateway_capture(pr_name):
    """
    Razorpay webhook marks Payment Request Paid before client verify runs.
    For PACE (reference PACE Applicant Fee Assignment), set assignment paid,
    create receipt, update application status, and ensure document verification.
    """
    from frappe.utils import now_datetime
    
    if not pr_name or not frappe.db.exists("SLCM Payment Request", pr_name):
        return
    pr = frappe.get_doc("SLCM Payment Request", pr_name)
    if pr.reference_doctype != "PACE Applicant Fee Assignment" or not pr.reference_name:
        return
    if (pr.status or "").strip() != "Paid":
        return

    assignment_name = pr.reference_name
    assignment = frappe.get_doc("PACE Applicant Fee Assignment", assignment_name, check_permission=False)

    if assignment.status != "Paid":
        try:
            assignment.status = "Paid"
            assignment.transaction_id = pr.razorpay_payment_id or pr.transaction_id
            assignment.payment_date = pr.paid_on or now_datetime()
            
            pr_amt = None
            if pr.gateway_response:
                import json
                try:
                    resp_dict = json.loads(pr.gateway_response)
                    if "amount" in resp_dict:
                        raw_amount = float(resp_dict["amount"])
                        fee = float(resp_dict.get("fee") or 0)
                        pr_amt = (raw_amount - fee) / 100.0
                except Exception:
                    pass
            
            if not pr_amt:
                pr_amt = pr.get("amount") or 0.0

            if pr_amt and float(pr_amt) > 0:
                assignment.razorpay_paid_amount = pr_amt
            else:
                frappe.log_error(f"Payment Request {pr.name} has zero/missing amount.", "PACE Webhook Sync Warning")
                
            assignment.flags.ignore_permissions = True
            assignment.save(ignore_permissions=True)
        except Exception as e:
            error_log = frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Failed to update PACE Fee Assignment {assignment.name} from Webhook"
            )
            frappe.db.set_value("PACE Applicant Fee Assignment", assignment.name, "error_log", error_log.name)

        # Load linked PACE Application and update status
        if assignment.applicant:
            app = frappe.get_doc("PACE Application", assignment.applicant, check_permission=False)
            if assignment.fee_type == "Course Fee":
                # Standard transitions are "Submitted" -> "Completed" -> "Fee Paid" -> "Enrolled"
                app.status = "Fee Paid"
            else:
                app.status = "Completed"
            app.flags.ignore_permissions = True
            app.save(ignore_permissions=True)

            # Trigger document verification if application is Completed
            if app.status == "Completed":
                try:
                    from slcm.pace.doctype.pace_document_verification.get_document_api import (
                        ensure_document_verification_for_completed_application,
                    )
                    ensure_document_verification_for_completed_application(app)
                except Exception:
                    frappe.log_error(
                        message=frappe.get_traceback(),
                        title=f"Webhook Sync: Post Submission Doc Verification Failed for {app.name}"
                    )
