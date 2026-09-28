from __future__ import unicode_literals
import frappe
from frappe import _, bold, throw
from frappe.utils import flt, getdate, add_months, nowdate, add_days, get_datetime, now_datetime
from datetime import datetime
import json
import logging

def update_payment_request_paid_on(doc, method):
    if doc.status == "Paid" and not doc.paid_on:
        doc.paid_on = frappe.utils.nowdate()


from slcm.api.service.application_fee_service import get_payment_receipt_template_for_policy
from slcm.api.service.razorpay_utils import (
    ADMISSION_REF_DOCTYPES,
    cancel_payment_request_for_retry,
    get_offer_payable_amount,
    get_razorpay_client,
    prepare_checkout_order,
    reconcile_payment_request_record,
)


def _default_payment_gateway():
	return (
		frappe.db.get_value("Payment Gateway", {"gateway": "Razorpay"}, "name")
		or frappe.db.get_value("Payment Gateway", {}, "name")
		or "Razorpay"
	)


class FeeService:
    """
    Fee and Payment Service Layer.
    Handles fee calculation, fee assignments, and payment gateway integration.
    """

    @staticmethod
    def _calculate_deadline(fee_structure_name):
        """Determines payment deadline based on Fee Structure."""
        if not fee_structure_name:
            return None
            
        valid_until = frappe.db.get_value("Fee Structure", fee_structure_name, "valid_until")
        return get_datetime(valid_until) if valid_until else None

    @staticmethod
    def _calculate_and_freeze_fees(fee_structure_name, is_foreign=False):
        """
        Financial Logic: Calculates fees and returns a structured dict.
        """
        if not fee_structure_name:
            return {}

        fs_doc = frappe.get_doc("Fee Structure", fee_structure_name)
        
        base_fee = 0
        tax_amount = 0
        breakdown = {}
        components = []
        total_payable = 0
        
        source_components = fs_doc.get("fee_components_for_foreign") if is_foreign else fs_doc.get("fee_components_for_indian")
        if not source_components:
            source_components = []

        for component in source_components:
            base_fee += component.amount
            tax_amount += component.tax_amount
            label = component.component_name or component.fee_component 
            breakdown[label] = component.total_amount
            
            components.append({
                "fee_component": component.fee_component,
                "component_name": component.component_name,
                "amount": component.amount,
                "is_taxable": component.is_taxable,
                "tax_rate": component.tax_rate,
                "tax_amount": component.tax_amount,
                "total_amount": component.total_amount
            })

        if fs_doc.is_confirmation_fee_applicable:
            total_payable = fs_doc.confirmation_fee_amount
        else:
            total_payable = fs_doc.get("total_amount_for_foreign") if is_foreign else fs_doc.get("total_amount_for_indian")
            if total_payable is None or total_payable == "":
                total_payable = fs_doc.total_amount_for_indian

        return {
            "base_fee": base_fee, 
            "scholarship_amount": 0,
            "tax_amount": tax_amount,
            "total_payable": total_payable,
            "breakdown": breakdown,
            "components": components,
            "payment_gateway": fs_doc.payment_gateway,
            "online_payment": fs_doc.online_payment,
            "is_confirmation_fee_applicable": fs_doc.is_confirmation_fee_applicable,
            "confirmation_fee_amount": fs_doc.confirmation_fee_amount
        }

    @staticmethod
    def create_fee_assignment_from_offer(offer):
        """
        Creates an Applicant Fee Assignment record from an accepted offer letter.
        - Copies only the actual fee component rows (no scholarship link row).
        - Fetches total approved scholarship from Scholarship Application
          and stores it in scholarship_amount field directly.
        """
        if frappe.db.exists("Applicant Fee Assignment", {"offer_letter": offer.name, "fee_type": ["in", ["Admission Fee", "Confirmation Fee"]], "status": ["!=", "Cancelled"], "docstatus": ["!=", 2]}):
            # Check if there is already an active assignment
            return

        foriegn_national = frappe.db.get_value("Applicant", offer.applicant, "foriegn_national")
        is_foreign = foriegn_national == "Yes"
        fee_data = FeeService._calculate_and_freeze_fees(offer.fee_structure, is_foreign=is_foreign)

        admission_cycle = offer.admission_cycle or frappe.db.get_value("Applicant", offer.applicant, "admission_cycle")

        # Fetch total approved scholarship and the linked application for this applicant + cycle
        scholarship_data = frappe.db.get_all("Scholarship Application",
            filters={
                "applicant_id": offer.applicant,
                "admission_cycle": admission_cycle,
                "status": "Approved"
            },
            fields=["name", "calculated_benefit"],
            order_by="creation desc"
        )
        
        total_scholarship = sum(flt(d.calculated_benefit) for d in scholarship_data)
        primary_scholarship = scholarship_data[0].name if scholarship_data else None

        assignment = frappe.new_doc("Applicant Fee Assignment")
        assignment.applicant = offer.applicant
        assignment.offer_letter = offer.name
        assignment.scholarship_application = primary_scholarship
        assignment.program = offer.program
        assignment.academic_year = offer.academic_year or frappe.db.get_value("Applicant", offer.applicant, "academic_year")
        assignment.admission_cycle = admission_cycle
        assignment.assignment_date = frappe.utils.today()
        
        fs_doc = frappe.get_doc("Fee Structure", offer.fee_structure)

        if fs_doc.is_confirmation_fee_applicable:
            assignment.fee_type = "Confirmation Fee"
            assignment.confirmation_fee = fs_doc.confirmation_fee_amount
        else:
            assignment.fee_type = "Admission Fee"
            # Copy fee rows
            for row in fee_data.get("components", []):
                if (row.get("fee_component") or "").lower() == "scholarship":
                    continue
                assignment.append("fee_components", {
                    "fee_component": row.get("fee_component"),
                    "component_name": row.get("component_name"),
                    "amount": row.get("amount"),
                    "is_taxable": row.get("is_taxable"),
                    "tax_rate": row.get("tax_rate"),
                    "tax_amount": row.get("tax_amount"),
                    "total_amount": row.get("total_amount")
                })

        # Store scholarship in the dedicated field (no Fee Component record needed)
        assignment.scholarship_amount = total_scholarship
        assignment.scholarship_applied = 1 if total_scholarship > 0 else 0

        assignment.insert(ignore_permissions=True)
        assignment.submit()

        return assignment.name

    @staticmethod
    def process_fee_payment(offer_name, payment_mode="Cash", reference_number=None, 
                           bank_name=None, cheque_number=None, cheque_date=None, 
                           upi_id=None, remarks=None):
        """
        Processes the fee payment for an accepted offer.
        """
        offer_doc = frappe.get_doc("Offer Letter", offer_name)
        
        # Security: Prevent duplicate payments
        if offer_doc.status in ["Payment Completed", "Full Fee Paid"]:
            throw(_("Payment has already been recorded for this offer ({0}).").format(offer_name))

        assignment_name = frappe.db.get_value("Applicant Fee Assignment", 
            {"offer_letter": offer_name, "status": "Assigned", "docstatus": ["!=", 2]}, "name", order_by="creation desc")
        
        if not assignment_name:
            if offer_doc.status not in ["Accepted", "Confirmation Fee Paid"]:
                throw(_("Offer must be 'Accepted' or 'Confirmation Fee Paid' before paying fees."))
            assignment_name = FeeService.create_fee_assignment_from_offer(offer_doc)
        
        if not assignment_name:
            throw(_("Fee Assignment not found for offer {0}").format(offer_name))

        assignment = frappe.get_doc("Applicant Fee Assignment", assignment_name)
        assignment.db_set("status", "Paid")
        
        from slcm.api.service.offer_service import OfferService
        
        is_confirmation = (assignment.fee_type == "Confirmation Fee")
        if is_confirmation:
            offer_to_save = frappe.get_doc("Offer Letter", offer_name)
            offer_to_save.status = "Confirmation Fee Paid"
            offer_to_save.save(ignore_permissions=True)
            OfferService.update_applicant_status(assignment.applicant, status="Confirmation Fee Paid")
            # Generate the next assignment for Full Fee
            next_assignment = frappe.new_doc("Applicant Fee Assignment")
            next_assignment.update(assignment.as_dict(
                no_default_fields=True, 
                no_child_table_fields=False
            ))
            next_assignment.fee_type = "Admission Fee"
            next_assignment.confirmation_fee = assignment.confirmation_fee or assignment.total_amount
            next_assignment.status = "Assigned"
            
            needs_accommodation = offer_doc.needs_accommodation == "Yes"
            next_assignment.accommodation_fee = 1 if needs_accommodation else 0
            
            # Copy fee rows
            next_assignment.fee_components = []
            fee_data = FeeService._calculate_and_freeze_fees(offer_doc.fee_structure, is_foreign=frappe.db.get_value("Applicant", assignment.applicant, "foriegn_national") == "Yes")
            for row in fee_data.get("components", []):
                if (row.get("fee_component") or "").lower() == "scholarship":
                    continue
                
                if not needs_accommodation:
                    is_acc = frappe.db.get_value("Fee Component", row.get("fee_component"), "is_accommodation_fee")
                    if is_acc:
                        continue
                        
                next_assignment.append("fee_components", {
                    "fee_component": row.get("fee_component"),
                    "component_name": row.get("component_name"),
                    "amount": row.get("amount"),
                    "is_taxable": row.get("is_taxable"),
                    "tax_rate": row.get("tax_rate"),
                    "tax_amount": row.get("tax_amount"),
                    "total_amount": row.get("total_amount")
                })
            next_assignment.insert(ignore_permissions=True)
            next_assignment.submit()
        else:
            offer_to_save = frappe.get_doc("Offer Letter", offer_name)
            offer_to_save.status = "Full Fee Paid"
            offer_to_save.save(ignore_permissions=True)
            OfferService.update_applicant_status(assignment.applicant, status="Full Fee Paid")


        # Generate Receipt
        return FeeService.generate_receipt(
            offer_doc, 
            reference_number or "N/A", 
            payment_mode,
            bank_name=bank_name,
            cheque_number=cheque_number,
            cheque_date=cheque_date,
            upi_id=upi_id,
            remarks=remarks
        )


    @staticmethod
    @frappe.whitelist()
    def create_offer_razorpay_order(offer_name):
        """
        Creates a Razorpay order directly and returns details for the frontend modal.
        """
        try:
            offer = frappe.get_doc("Offer Letter", offer_name)
            
            # Validation
            if not offer.payable_amount or flt(offer.payable_amount) <= 0:
                frappe.throw(_("Payable amount must be greater than zero."))
            
            if offer.status == "Payment Completed":
                frappe.throw(_("Payment has already been completed."))

            actual_payable = get_offer_payable_amount(offer)

            target_fee_type = "Confirmation Fee" if offer.status == "Accepted" else "Admission Fee"

            # Fetch the specific Applicant Fee Assignment for this stage
            afa = frappe.db.get_value(
                "Applicant Fee Assignment",
                {"offer_letter": offer.name, "fee_type": target_fee_type, "docstatus": ["!=", 2]},
                ["name", "status", "creation"],
                as_dict=True
            )
            if not afa:
                frappe.throw(_("No pending fee assignment found for this offer. Payment has already been completed or the applicant has been converted."))
            
            if afa.status in ("Paid", "Converted"):
                frappe.throw(_("Fee for this offer has already been paid or the applicant has been converted. You cannot pay again."))

            if actual_payable <= 0:
                FeeService.process_fee_payment(
                    offer.name,
                    payment_mode="Confirmation Fee Adjustment",
                    remarks="Fee fully covered by confirmation fee deduction."
                )
                return {
                    "zero_amount": True,
                    "status": "success",
                    "message": _("Fee fully covered by confirmation fee payment.")
                }


            # Block if a Payment Request for the CURRENT fee amount is already Paid (gateway truth)
            # We filter by creation >= afa.creation to ignore PRs from previous fee stages
            existing_paid_pr = frappe.db.get_value(
                "Payment Request",
                {
                    "reference_doctype": "Offer Letter", 
                    "reference_name": offer.name, 
                    "status": "Paid",
                    "amount": actual_payable,
                    "creation": (">=", afa.creation)
                },
                "name",
                order_by="creation desc"
            )
            if existing_paid_pr:
                frappe.throw(_("Payment has already been completed for this offer. You cannot pay again."))
            
            if offer.status in ["Rejected", "Expired", "Withdrawn"]:
                frappe.throw(_("Cannot initiate payment. The offer is currently {0}.").format(offer.status))
            
            if offer.status in ["Draft", "Issued"]:
                frappe.throw(_("Please accept the offer before proceeding to fee payment."))

            # Real-time Deadline Validation
            now_date = frappe.utils.nowdate()
            if offer.status == "Accepted":
                if offer.confirmation_fee_deadline and frappe.utils.getdate(offer.confirmation_fee_deadline) < frappe.utils.getdate(now_date):
                    frappe.throw(_("Payment blocked: The Confirmation Fee deadline ({0}) has passed.").format(offer.confirmation_fee_deadline))
            elif offer.status == "Confirmation Fee Paid":
                if offer.payment_deadline and frappe.utils.getdate(offer.payment_deadline) < frappe.utils.getdate(now_date):
                    frappe.throw(_("Payment blocked: The Full Fee deadline ({0}) has passed.").format(offer.payment_deadline))

            # 2. Get Dynamic Gateway from Fee Structure
            gateway = frappe.db.get_value("Fee Structure", offer.fee_structure, "payment_gateway")
            if not gateway:
                # Fallback to system default if not set on Fee Structure
                gateway = _default_payment_gateway()

            from payments.utils import get_payment_gateway_controller
            controller = get_payment_gateway_controller(gateway)

            payment_details = {
                "amount": actual_payable,
                "title": _("Admission Fee"),
                "description": _("Admission Fee for {0}").format(offer.program),
                "reference_doctype": "Offer Letter",
                "reference_docname": offer.name,
                "payer_email": frappe.db.get_value("Applicant", offer.applicant, "email"),
                "payer_name": frappe.db.get_value("Applicant", offer.applicant, "candidate_name"),
                "currency": frappe.defaults.get_global_default("currency") or "INR",
                "receipt": (offer.name[:40]) if offer.name else None
            }

            pr_name = frappe.db.get_value(
                "Payment Request",
                {
                    "reference_doctype": "Offer Letter",
                    "reference_name": offer.name,
                    "docstatus": ["!=", 2],
                    "creation": (">=", afa.creation)
                },
                "name",
                order_by="creation desc"
            )
            pr = frappe.get_doc("Payment Request", pr_name) if pr_name else None
            if pr:
                pr_status = (pr.status or "").strip()
                if pr_status == "Paid":
                    frappe.throw(_("Payment has already been completed."))
                if pr_status == "Failed" or flt(pr.amount) != actual_payable:
                    cancel_payment_request_for_retry(pr)
                    pr = None

            rzp_client = get_razorpay_client()
            if pr:
                order = prepare_checkout_order(
                    rzp_client, controller, payment_details, pr, actual_payable
                )
            else:
                order = controller.create_order(**payment_details)
                if not order or not order.get("id"):
                    frappe.throw(_("Order creation failed. Please check gateway logs."))

            order_id = order.get("id") or order.get("order_id")
            FeeService._update_payment_request(
                offer, gateway, order_id, "Requested", response_data=order
            )

            return {
                "order_id": order_id,
                "key_id": controller.api_key,
                "amount": order.get("amount"),
                "currency": order.get("currency"),
                "gateway": gateway
            }
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Offer Payment Order Creation Failed")
            raise

    @staticmethod
    def complete_offer_payment(offer_doc, razorpay_payment_id, razorpay_order_id, gateway, response_data=None):
        """Idempotently records payment for the offer letter fee."""

        # Determine which fee was just paid by finding the pending assignment
        assignment_name = frappe.db.get_value("Applicant Fee Assignment", 
            {"offer_letter": offer_doc.name, "status": "Assigned", "docstatus": ["!=", 2]}, 
            "name", order_by="creation desc")
            
        is_confirmation = False
        if assignment_name:
            frappe.db.set_value("Applicant Fee Assignment", assignment_name, {
                "status": "Paid",
                "payment_date": frappe.utils.today(),
                "transaction_id": razorpay_payment_id
            })
            fee_type = frappe.db.get_value("Applicant Fee Assignment", assignment_name, "fee_type")
            is_confirmation = (fee_type == "Confirmation Fee")

        from slcm.api.service.offer_service import OfferService
        if is_confirmation:
            offer_doc.status = "Confirmation Fee Paid"
            offer_doc.confirmation_fee_paid_on = frappe.utils.today()
            offer_doc.save(ignore_permissions=True)
            OfferService.update_applicant_status(offer_doc.applicant, status="Confirmation Fee Paid")
            
            # Generate the next assignment for Full Fee
            next_assignment = frappe.new_doc("Applicant Fee Assignment")
            old_assignment = frappe.get_doc("Applicant Fee Assignment", assignment_name)
            next_assignment.update(old_assignment.as_dict(
                no_default_fields=True, 
                no_child_table_fields=False
            ))
            next_assignment.fee_type = "Admission Fee"
            next_assignment.confirmation_fee = old_assignment.confirmation_fee or old_assignment.total_amount
            next_assignment.status = "Assigned"
            
            needs_accommodation = offer_doc.needs_accommodation == "Yes"
            next_assignment.accommodation_fee = 1 if needs_accommodation else 0
            
            # Copy fee rows
            next_assignment.fee_components = []
            fee_data = FeeService._calculate_and_freeze_fees(offer_doc.fee_structure, is_foreign=frappe.db.get_value("Applicant", offer_doc.applicant, "foriegn_national") == "Yes")
            for row in fee_data.get("components", []):
                if (row.get("fee_component") or "").lower() == "scholarship":
                    continue
                    
                if not needs_accommodation:
                    is_acc = frappe.db.get_value("Fee Component", row.get("fee_component"), "is_accommodation_fee")
                    if is_acc:
                        continue
                        
                next_assignment.append("fee_components", {
                    "fee_component": row.get("fee_component"),
                    "component_name": row.get("component_name"),
                    "amount": row.get("amount"),
                    "is_taxable": row.get("is_taxable"),
                    "tax_rate": row.get("tax_rate"),
                    "tax_amount": row.get("tax_amount"),
                    "total_amount": row.get("total_amount")
                })
            next_assignment.insert(ignore_permissions=True)
            next_assignment.submit()
        else:
            offer_doc.status = "Full Fee Paid"
            offer_doc.full_fee_paid_on = frappe.utils.today()
            offer_doc.save(ignore_permissions=True)
            OfferService.update_applicant_status(offer_doc.applicant, status="Full Fee Paid")
            
        # 2. Update Payment Request
        FeeService._update_payment_request(
            offer_doc, gateway, razorpay_order_id, "Paid", razorpay_payment_id,
            response_data=response_data or {"payment_id": razorpay_payment_id, "order_id": razorpay_order_id}
        )
        
        # 4. Generate Receipt (with safety)
        try:
            FeeService.generate_receipt(offer_doc, razorpay_payment_id, "Online")
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Receipt Generation Failed during complete_offer_payment")

        try:
            offer_doc.add_comment("Comment", f"Payment verified. Razorpay Payment ID: {razorpay_payment_id}")
        except Exception:
            pass

    @staticmethod
    @frappe.whitelist()
    def verify_offer_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, offer_name):
        """
        Verifies the Razorpay signature and updates the offer status.
        """
        try:
            # Step 1: SELECT FOR UPDATE lock
            frappe.db.sql(
                "SELECT name FROM `tabOffer Letter` WHERE name = %s FOR UPDATE",
                offer_name,
            )

            # Step 2: reload()
            offer = frappe.get_doc("Offer Letter", offer_name)
            offer.reload()

            # Step 3: already paid check
            if offer.status == "Payment Completed":
                return {"status": "success"}

            gateway = frappe.db.get_value("Fee Structure", offer.fee_structure, "payment_gateway")
            if not gateway:
                gateway = _default_payment_gateway()

            # Validate Payment Request ownership
            pr_name = frappe.db.get_value(
                "Payment Request",
                {
                    "reference_doctype": "Offer Letter",
                    "reference_name": offer.name,
                    "docstatus": 1,
                    "transaction_id": razorpay_order_id,
                },
                "name",
            )
            if not pr_name:
                pr_name = frappe.db.get_value(
                    "Payment Request",
                    {
                        "reference_doctype": "Offer Letter",
                        "reference_name": offer.name,
                        "docstatus": 1,
                        "razorpay_order_id": razorpay_order_id,
                    },
                    "name",
                )
            if not pr_name:
                pr_name = frappe.db.get_value(
                    "Payment Request",
                    {
                        "reference_doctype": "Offer Letter",
                        "reference_name": offer.name,
                        "docstatus": 1,
                    },
                    "name",
                    order_by="creation desc",
                )
            if not pr_name:
                frappe.throw(_("No Payment Request found for this offer."))

            # Acquire lock on the Payment Request row to prevent deadlock / race condition with webhook
            frappe.db.sql(
                "SELECT name FROM `tabPayment Request` WHERE name = %s FOR UPDATE",
                pr_name,
            )

            # Reload fresh state AFTER acquiring lock
            pr = frappe.get_doc("Payment Request", pr_name, check_permission=False)
            if pr.status == "Paid":
                return {"status": "success"}

            duplicate_paid = frappe.db.exists(
                "Payment Request",
                {
                    "status": "Paid",
                    "transaction_id": razorpay_payment_id,
                    "name": ["!=", pr_name],
                },
            )
            if duplicate_paid:
                frappe.throw(_("This Razorpay payment has already been recorded."))

            pr = frappe.get_doc("Payment Request", pr_name)
            expected_order_id = pr.transaction_id or pr.razorpay_order_id
            if expected_order_id != razorpay_order_id:
                frappe.throw(_("Payment Request mismatch"))

            from payments.utils import get_payment_gateway_controller
            controller = get_payment_gateway_controller(gateway)
            
            # Step 4: verify signature
            body = razorpay_order_id + "|" + razorpay_payment_id
            api_secret = controller.get_password("api_secret")
            controller.verify_signature(body, razorpay_signature, api_secret)

            # Step 5: fetch payment from Razorpay
            import razorpay
            rzp_settings = frappe.get_single("Razorpay Settings")
            rzp_client = razorpay.Client(
                auth=(rzp_settings.api_key, rzp_settings.get_password("api_secret"))
            )
            payment = rzp_client.payment.fetch(razorpay_payment_id)

            # Step 6: validate amount/order/currency/status
            expected_amount = int(flt(pr.get("grand_total") or pr.amount) * 100)
            actual_amount = payment.get("amount")
            fee = payment.get("fee") or 0
            if actual_amount < expected_amount:
                frappe.log_error(
                    title="Offer Payment Amount Mismatch",
                    message=(
                        f"Offer: {offer.name}\n"
                        f"Expected: {expected_amount}\n"
                        f"Actual: {actual_amount}\n"
                        f"Fee: {fee}\n"
                        f"Payment ID: {razorpay_payment_id}"
                    )
                )
                frappe.throw(_("Payment amount validation failed"))

            if payment.get("order_id") != razorpay_order_id:
                frappe.throw(_("Order validation failed"))

            currency = "INR"
            if payment.get("currency") != currency:
                frappe.throw(_("Currency validation failed"))

            if payment.get("status") == "failed":
                error_reason = (
                    payment.get("error_description")
                    or payment.get("error_code")
                    or _("Payment failed at the gateway.")
                )
                frappe.throw(_("Payment Failed: {0}").format(error_reason))

            if payment.get("status") == "authorized":
                try:
                    payment = rzp_client.payment.capture(razorpay_payment_id, expected_amount, {"currency": payment.get("currency") or "INR"})
                except Exception as e:
                    frappe.log_error(frappe.get_traceback(), f"Razorpay Capture API Call Failed for Payment ID {razorpay_payment_id}")
                    frappe.throw(_("Failed to capture authorized payment at the gateway. Please retry or contact support."))

            payment_status = payment.get("status")
            if payment_status == "failed":
                frappe.throw(_("Your payment could not be completed. If money was deducted, it will be automatically refunded by the bank."))
            elif payment_status == "refunded":
                frappe.throw(_("Payment has been refunded"))
            elif payment_status != "captured":
                frappe.throw(_("Your payment is being verified. Please wait a few moments and refresh the page."))

            # Step 7: mark paid
            FeeService.complete_offer_payment(
                offer,
                razorpay_payment_id,
                razorpay_order_id,
                gateway,
                response_data=payment
            )
            
            frappe.db.commit()
            return {"status": "success"}

        except frappe.ValidationError as e:
            frappe.db.rollback()
            return {"status": "failed", "message": str(e)}
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "Offer Payment Verification Failed")
            return {"status": "failed", "message": _("An unexpected error occurred during payment verification. Please contact support.")}

    @staticmethod
    def _resolve_payment_receipt_print_format(applicant_name, campus=None, fee_type=None, offer_letter=None):
        """
        Print Format name from Programme Reservation Policy (same rules as portal download_receipt).
        """
        if fee_type in ["Confirmation Fee", "Admission Fee"] and offer_letter:
            try:
                offer = frappe.get_doc("Offer Letter", offer_letter)
                if offer.fee_structure:
                    tpl = frappe.db.get_value("Fee Structure", offer.fee_structure, "receipt_print_format")
                    if tpl:
                        return tpl
            except Exception:
                pass

        if not applicant_name:
            return None
        try:
            app = frappe.get_doc("Applicant", applicant_name)
        except Exception:
            return None
        if not app.admission_cycle or not app.program:
            return None
        campus = campus or app.campus
        policy_name = None
        if campus:
            policy_name = frappe.db.get_value(
                "Admission Cycle Program",
                {
                    "parent": app.admission_cycle,
                    "program": app.program,
                    "campus": campus,
                    "is_active": 1,
                },
                "reservation_policy",
            )
        if not policy_name:
            policy_name = frappe.db.get_value(
                "Admission Cycle Program",
                {
                    "parent": app.admission_cycle,
                    "program": app.program,
                    "is_active": 1,
                },
                "reservation_policy",
            )
        if not policy_name:
            return None
        return frappe.db.get_value("Programme Reservation Policy", policy_name, "payment_receipt_template")

    @staticmethod
    def generate_receipt(offer_doc, transaction_id, payment_mode, 
                        bank_name=None, cheque_number=None, cheque_date=None, 
                        upi_id=None, remarks=None):
        """
        Generates a Payment Receipt based on the current Offer and Fee Snapshot.
        """
        try:
            import json
            existing = frappe.db.exists(
                "Applicant Payment Receipt",
                {
                    "transaction_id": transaction_id,
                }
            )
            if existing:
                return existing

            # 1. Fetch the most recently paid assignment for this offer
            assignment_name = frappe.db.get_value(
                "Applicant Fee Assignment",
                {"offer_letter": offer_doc.name, "status": "Paid", "docstatus": ["<", 2]},
                "name",
                order_by="modified desc"
            )
            
            if not assignment_name:
                frappe.log_error("No Paid assignment found for receipt generation.", "Receipt Generation")
                return None
                
            afa = frappe.get_doc("Applicant Fee Assignment", assignment_name)

            # 2. Create Receipt
            receipt = frappe.new_doc("Applicant Payment Receipt")
            receipt.applicant = offer_doc.applicant
            receipt.offer_letter = offer_doc.name
            receipt.program = offer_doc.program
            receipt.fee_type = afa.fee_type
            receipt.assignment = afa.name

            receipt.academic_year = offer_doc.academic_year
            receipt.campus = offer_doc.campus
            receipt.payment_date = frappe.utils.today()
            receipt.transaction_id = transaction_id
            receipt.payment_mode = payment_mode
            receipt.total_amount = afa.total_amount
            receipt.currency = frappe.defaults.get_global_default("currency") or "INR"

            # Manual Details
            receipt.bank_name = bank_name
            receipt.cheque_number = cheque_number
            receipt.cheque_date = cheque_date
            receipt.upi_id = upi_id
            receipt.remarks = remarks
            
            # Link to existing Payment Request if possible
            pr = frappe.db.get_value("Payment Request", {"transaction_id": transaction_id}, "name")
            if pr:
                receipt.payment_reference = pr

            # 3. Copy Components
            from frappe.utils import flt as _flt
            
            # If scholarship is applied on the Applicant Fee Assignment
            receipt.scholarship_applied = afa.scholarship_applied
            receipt.scholarship_amount = _flt(afa.scholarship_amount)

            if afa.fee_type == "Confirmation Fee":
                receipt.confirmation_fee = afa.confirmation_fee or afa.total_amount
            else:
                for comp in afa.get("fee_components", []):
                    receipt.append("fee_components", {
                        "fee_component": comp.fee_component,
                        "component_name": comp.component_name,
                        "amount": comp.amount,
                        "is_taxable": comp.is_taxable,
                        "tax_rate": comp.tax_rate,
                        "tax_amount": comp.tax_amount,
                        "total_amount": comp.total_amount
                    })

            # Ensure header amounts reflect the breakdown
            receipt.net_amount = _flt(afa.final_payable_amount) if afa.final_payable_amount else receipt.total_amount - receipt.scholarship_amount

            tpl = FeeService._resolve_payment_receipt_print_format(
                offer_doc.applicant, getattr(offer_doc, "campus", None), afa.fee_type, offer_doc.name
            )
            if tpl:
                receipt.payment_receipt_template = tpl

            receipt.insert(ignore_permissions=True)
            
            return receipt.name
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Receipt Generation Failed")
            return None

    @staticmethod

    @frappe.whitelist()
    def log_payment_failure(offer_name, order_id, error_data):
        """
        Logs a payment failure reported by the frontend.
        """
        try:
            offer = frappe.get_doc("Offer Letter", offer_name)
            gateway = frappe.db.get_value("Fee Structure", offer.fee_structure, "payment_gateway")
            
            if isinstance(error_data, str):
                try:
                    error_data = json.loads(error_data)
                except:
                    pass
            
            error_message = ""
            if isinstance(error_data, dict):
                error_message = error_data.get("description") or error_data.get("message") or str(error_data)
            else:
                error_message = str(error_data)

            FeeService._update_payment_request(
                offer, 
                gateway, 
                order_id, 
                "Failed", 
                failure_reason=error_message,
                response_data=error_data
            )
            

            
            return {"status": "success"}
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Log Payment Failure Failed")
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _update_payment_request(offer, gateway, transaction_id, status, payment_id=None, failure_reason=None, response_data=None):
        """
        Creates or updates a Payment Request doc to store gateway response.
        We find by order_id (transaction_id) to allow multiple attempts per offer.
        """
        # Try to find an existing payment request for this offer first
        target_fee_type = "Confirmation Fee" if offer.status == "Accepted" else "Admission Fee"
        afa = frappe.db.get_value(
            "Applicant Fee Assignment",
            {"offer_letter": offer.name, "fee_type": target_fee_type, "docstatus": ["!=", 2]},
            ["creation"],
            as_dict=True
        )
        
        filters = {
            "reference_doctype": "Offer Letter", 
            "reference_name": offer.name,
            "status": ["not in", ["Paid", "Cancelled"]],
            "docstatus": ["!=", 2]
        }
        if afa:
            filters["creation"] = (">=", afa.creation)
            
        pr_name = frappe.db.get_value("Payment Request", filters, "name", order_by="creation desc")
        
        if not pr_name and transaction_id:
             # Fallback to finding by transaction id if specifically provided
             pr_name = frappe.db.get_value("Payment Request", 
                {"transaction_id": transaction_id}, "name")

        if pr_name:
            pr = frappe.get_doc("Payment Request", pr_name)
            
            # Removed amount overwrite to prevent corrupting paid PRs
            
            # Update gateway if it's a manual override and it exists
            if gateway:
                if frappe.db.exists("Payment Gateway", gateway):
                    pr.db_set("payment_gateway", gateway)
                else:
                    frappe.log_error(
                        f"Payment Gateway '{gateway}' not found or configured. PR: {pr.name if pr.name else 'NEW'}, Reference: {offer.name}",
                        "FeeService: Gateway Not Found"
                    )
        else:
            pr = frappe.new_doc("Payment Request")
            pr.reference_doctype = "Offer Letter"
            pr.reference_name = offer.name
            
            # Get actual amount (checking for scholarship and fee type safely)
            from slcm.api.service.razorpay_utils import get_offer_payable_amount
            pr.amount = get_offer_payable_amount(offer)
            
            pr.currency = frappe.defaults.get_global_default("currency") or "INR"
            pr.email_to = frappe.db.get_value("Applicant", offer.applicant, "email")
            if gateway:
                if frappe.db.exists("Payment Gateway", gateway):
                    pr.payment_gateway = gateway
                else:
                    frappe.log_error(
                        f"Payment Gateway '{gateway}' not found or configured. PR: {pr.name if pr.name else 'NEW'}, Reference: {offer.name}",
                        "FeeService: Gateway Not Found"
                    )
            pr.transaction_id = transaction_id

        # Gateway fields: razorpay_order_id and gateway_status for webhook and audit
        if transaction_id and status == "Requested":
            try:
                pr.razorpay_order_id = transaction_id
                pr.gateway_status = "created"
            except AttributeError:
                pass

        if pr.name and pr.docstatus > 0:
            # If doc is already submitted, we use db_set/set_value for direct DB update
            frappe.logger().debug(f"Updating submitted Payment Request {pr.name} to status {status}")
            frappe.flags.payment_request_status_from_backend = True

            update_data = {"status": status}
            if status == "Paid":
                update_data["failure_message"] = None
                update_data["gateway_status"] = "captured"
                update_data["paid_on"] = frappe.utils.nowdate()
            elif failure_reason:
                update_data["failure_message"] = failure_reason

            if payment_id:
                update_data["transaction_id"] = payment_id
                if status == "Paid":
                    update_data["razorpay_payment_id"] = payment_id
            if transaction_id and status == "Requested":
                update_data["razorpay_order_id"] = transaction_id
                update_data["gateway_status"] = "created"

            if response_data:
                update_data["gateway_response"] = json.dumps(response_data, indent=4)

            if gateway:
                if frappe.db.exists("Payment Gateway", gateway):
                    update_data["payment_gateway"] = gateway
                else:
                    frappe.log_error(
                        f"Payment Gateway '{gateway}' not found or configured. PR: {pr.name if pr.name else 'NEW'}, Reference: {offer.name}",
                        "FeeService: Gateway Not Found"
                    )

            frappe.db.set_value("Payment Request", pr.name, update_data, update_modified=True)
            frappe.db.commit()
            if hasattr(frappe.flags, "payment_request_status_from_backend"):
                del frappe.flags.payment_request_status_from_backend
        else:
            # Draft or New
            pr.status = status
            if payment_id:
                pr.transaction_id = payment_id
            if transaction_id and status == "Requested":
                pr.razorpay_order_id = transaction_id
                pr.gateway_status = "created"

            if response_data:
                pr.gateway_response = json.dumps(response_data, indent=4)

            if status == "Paid":
                pr.failure_message = None
                pr.gateway_status = "captured"

            if failure_reason:
                pr.failure_message = failure_reason

            frappe.flags.payment_request_status_from_backend = True
            if pr.name:
                pr.save(ignore_permissions=True)
            else:
                pr.insert(ignore_permissions=True)

            if status in ["Paid", "Requested"]:
                pr.submit()
            if hasattr(frappe.flags, "payment_request_status_from_backend"):
                del frappe.flags.payment_request_status_from_backend





    @staticmethod
    @frappe.whitelist()
    def create_confirmation_fee_refund(offer_name, refund_percentage):
        """
        Creates a Refund Request for the Confirmation Fee payment on an Offer Letter.

        Design decisions:
        - Full Fee AFA is NOT affected — this is a standalone monetary refund of the
          confirmation fee payment only.
        - Duplicate prevention: if an active (non-Rejected / non-Failed) Confirmation Fee
          Refund Request already exists for this offer, the call raises a user-visible error.
        - The refund percentage is supplied by the caller (0–100).  100% => Full, else Partial.

        Returns the name of the created Refund Request.
        """
        offer = frappe.get_doc("Offer Letter", offer_name)

        # Check Fee Structure refund settings
        if offer.fee_structure:
            fs_data = frappe.db.get_value("Fee Structure", offer.fee_structure, ["is_confirmation_fee_refundable", "confirmation_fee_refund_percentage"], as_dict=True)
            if fs_data:
                if not fs_data.get("is_confirmation_fee_refundable", False):
                    frappe.throw(_("Confirmation Fee is configured as non-refundable in the Fee Structure."))
                fs_pct = flt(fs_data.get("confirmation_fee_refund_percentage"))
                if fs_pct > 0 and (not refund_percentage or refund_percentage == 100):
                    refund_percentage = fs_pct

        refund_percentage = flt(refund_percentage)
        if refund_percentage <= 0 or refund_percentage > 100:
            frappe.throw(_("Refund percentage must be between 1 and 100."))

        # ── 1. Validate offer is in a fee-paid state ──────────────────────────────
        if offer.status not in ("Confirmation Fee Paid", "Full Fee Paid"):

            frappe.throw(
                _("Confirmation Fee refund can only be initiated when the offer status is "
                  "'Confirmation Fee Paid' or 'Full Fee Paid'. Current status: {0}.").format(offer.status)
            )

        # ── 2. Duplicate-prevention: block if an active Confirmation Fee RR exists ─
        existing_rr = frappe.db.sql("""
            SELECT rr.name
            FROM `tabRefund Request` rr
            JOIN `tabApplicant Fee Assignment` afa
              ON afa.name = rr.applicant_fee_assignment
            WHERE rr.applicant = %(applicant)s
              AND afa.offer_letter = %(offer)s
              AND afa.fee_type = 'Confirmation Fee'
              AND rr.status NOT IN ('Rejected', 'Failed')
            LIMIT 1
        """, {"applicant": offer.applicant, "offer": offer.name}, as_dict=True)

        if existing_rr:
            frappe.throw(
                _("A Confirmation Fee Refund Request ({0}) already exists for this offer "
                  "and is currently active. Please resolve it before raising a new one.").format(
                    existing_rr[0].name)
            )

        # ── 3. Find the Confirmation Fee AFA ─────────────────────────────────────
        conf_afa = frappe.db.get_value(
            "Applicant Fee Assignment",
            {
                "offer_letter": offer.name,
                "fee_type": "Confirmation Fee",
                "status": "Paid",
                "docstatus": ["!=", 2],
            },
            ["name", "confirmation_fee", "total_amount", "final_payable_amount", "creation"],
            as_dict=True,
            order_by="creation desc",
        )
        if not conf_afa:
            frappe.throw(
                _("No paid Confirmation Fee assignment found for offer {0}.").format(offer.name)
            )

        # ── 4. Resolve Payment Receipt & Razorpay Payment ID ────────────────────
        receipt_data = frappe.db.get_all(
            "Applicant Payment Receipt",
            filters={"offer_letter": offer.name, "fee_type": "Confirmation Fee"},
            fields=["name"],
            order_by="creation desc"
        )
        receipt_name = receipt_data[0].name if receipt_data else None

        # Fallback: any receipt linked to this offer (older data may not have fee_type set)
        if not receipt_name:
            receipt_data = frappe.db.get_all(
                "Applicant Payment Receipt",
                filters={"offer_letter": offer.name},
                fields=["name"],
                order_by="creation asc"
            )
            receipt_name = receipt_data[0].name if receipt_data else None

        razorpay_payment_id = None
        amount_paid = flt(conf_afa.final_payable_amount or conf_afa.confirmation_fee or conf_afa.total_amount)

        if receipt_name:
            receipt = frappe.get_doc("Applicant Payment Receipt", receipt_name)
            razorpay_payment_id = receipt.transaction_id
            # Prefer net_amount (post-scholarship) if set, else total_amount
            if flt(receipt.get("net_amount")) > 0:
                amount_paid = flt(receipt.net_amount)
            elif flt(receipt.total_amount) > 0:
                amount_paid = flt(receipt.total_amount)

        # Final fallback: resolve Razorpay payment ID from the Payment Request
        if not razorpay_payment_id:
            pr_name = frappe.db.get_value(
                "Payment Request",
                {
                    "reference_doctype": "Offer Letter",
                    "reference_name": offer.name,
                    "status": "Paid",
                    "docstatus": ["!=", 2],
                    "creation": [">=", conf_afa.creation],
                },
                "name",
                order_by="creation asc",
            )
            if pr_name:
                pr = frappe.get_doc("Payment Request", pr_name)
                razorpay_payment_id = pr.transaction_id or getattr(pr, "razorpay_payment_id", None)
                if not amount_paid:
                    amount_paid = flt(pr.amount)

        if not amount_paid:
            frappe.throw(
                _("Could not determine the Confirmation Fee amount paid for offer {0}.").format(offer.name)
            )

        # ── 5. Compute refund amount & type ──────────────────────────────────────
        refund_amount = round(amount_paid * refund_percentage / 100.0, 2)
        refund_type = "Full" if refund_percentage == 100 else "Partial"

        # ── 6. Create the Refund Request ─────────────────────────────────────────
        refund = frappe.new_doc("Refund Request")
        refund.applicant = offer.applicant
        refund.applicant_fee_assignment = conf_afa.name
        refund.status = "Under Review"
        refund.refund_reason = _("Confirmation Fee Refund for Offer {0}").format(offer.name)
        refund.refund_type = refund_type
        refund.amount_paid = amount_paid
        refund.refund_amount = refund_amount

        if receipt_name:
            refund.applicant_payment_receipt = receipt_name
        if razorpay_payment_id:
            refund.razorpay_payment_id = razorpay_payment_id

        refund.insert(ignore_permissions=True)

        frappe.db.commit()
        return refund.name

    @staticmethod
    def cancel_linked_fee_assignment(offer_name, reason=None):
        """
        Policy: If an offer is terminated (Rejected, Expired, Withdrawn), 
        any unpaid fee assignment must be cancelled to prevent 'ghost' revenue.
        """
        # Find any non-terminal Fee Assignment
        afa_list = frappe.get_all("Applicant Fee Assignment", 
            filters={
                "offer_letter": offer_name,
                "status": ["not in", ["Cancelled", "Paid", "Converted"]]
            }, fields=["name", "docstatus"])
        
        for entry in afa_list:
            try:
                doc = frappe.get_doc("Applicant Fee Assignment", entry.name)
                
                if reason == "Withdrawn":
                    doc.db_set("status", "Withdrawn")
                else:
                    # If assigned (submitted), we must use cancel()
                    if doc.docstatus == 1:
                        # The on_cancel method in AFA handles validation (preventing cancel if paid)
                        doc.cancel()
                    else:
                        # Draft or other
                        doc.db_set("status", "Cancelled")
                
                frappe.logger().info(f"Auto-cancelled linked Fee Assignment {entry.name} for Offer {offer_name}")
            except Exception as e:
                # We don't want to block the offer status change, but we log the failure
                frappe.log_error(f"Failed to auto-cancel AFA {entry.name}: {str(e)}", "Fee Service")

    @staticmethod
    def _update_payment_request_for_applicant(applicant_doc, gateway, transaction_id, status,
            payment_id=None, failure_reason=None, response_data=None):
        """Creates or updates Payment Request for Applicant (application fee).

        Keeps ``razorpay_order_id`` + ``gateway_status`` in sync (same as offer-letter flow)
        so webhooks can resolve the doc and the desk form shows ``captured`` after pay.
        """
        pr_name = frappe.db.get_value("Payment Request", {
            "reference_doctype": "Applicant",
            "reference_name": applicant_doc.name,
            "status": ["!=", "Cancelled"],
            "docstatus": ["!=", 2]
        }, "name", order_by="creation desc")

        if not pr_name and transaction_id:
            pr_name = frappe.db.get_value("Payment Request", {"transaction_id": transaction_id}, "name")
        if not pr_name and transaction_id:
            pr_name = frappe.db.get_value("Payment Request", {"razorpay_order_id": transaction_id}, "name")

        amount = flt(applicant_doc.application_fee_amount)
        email_to = applicant_doc.email

        if pr_name:
            pr = frappe.get_doc("Payment Request", pr_name)
            if gateway:
                if frappe.db.exists("Payment Gateway", gateway):
                    pr.db_set("payment_gateway", gateway)
                else:
                    frappe.log_error(
                        f"Payment Gateway '{gateway}' not found or configured. PR: {pr.name if pr.name else 'NEW'}, Reference: {applicant_doc.name}",
                        "FeeService: Gateway Not Found"
                    )
        else:
            pr = frappe.new_doc("Payment Request")
            pr.reference_doctype = "Applicant"
            pr.reference_name = applicant_doc.name
            pr.amount = amount
            pr.grand_total = amount
            pr.currency = frappe.defaults.get_global_default("currency") or "INR"
            pr.email_to = email_to
            if gateway:
                if frappe.db.exists("Payment Gateway", gateway):
                    pr.payment_gateway = gateway
                else:
                    frappe.log_error(
                        f"Payment Gateway '{gateway}' not found or configured. PR: {pr.name if pr.name else 'NEW'}, Reference: {applicant_doc.name}",
                        "FeeService: Gateway Not Found"
                    )
            pr.transaction_id = transaction_id
            pr.flags.ignore_validate = True
            pr.insert(ignore_permissions=True)

        if pr.docstatus > 0:
            frappe.flags.payment_request_status_from_backend = True
            update_data = {"status": status}
            if status == "Requested" and transaction_id:
                update_data["razorpay_order_id"] = transaction_id
                update_data["gateway_status"] = "created"
                update_data["transaction_id"] = transaction_id
            if status == "Paid":
                update_data["failure_message"] = None
                update_data["gateway_status"] = "captured"
                update_data["paid_on"] = now_datetime()
                if transaction_id:
                    prev_oid = frappe.db.get_value("Payment Request", pr.name, "razorpay_order_id")
                    if not prev_oid or str(transaction_id).startswith("order_"):
                        update_data["razorpay_order_id"] = transaction_id
                if payment_id:
                    update_data["transaction_id"] = payment_id
                    update_data["razorpay_payment_id"] = payment_id
            elif failure_reason:
                update_data["failure_message"] = failure_reason
                update_data["gateway_status"] = "failed"
            if response_data:
                update_data["gateway_response"] = json.dumps(response_data, indent=4)
            if gateway:
                if frappe.db.exists("Payment Gateway", gateway):
                    update_data["payment_gateway"] = gateway
                else:
                    frappe.log_error(
                        f"Payment Gateway '{gateway}' not found or configured. PR: {pr.name if pr.name else 'NEW'}, Reference: {applicant_doc.name}",
                        "FeeService: Gateway Not Found"
                    )
            frappe.db.set_value("Payment Request", pr.name, update_data, update_modified=True)
            frappe.db.commit()
            if frappe.flags.get("payment_request_status_from_backend"):
                del frappe.flags.payment_request_status_from_backend
        else:
            frappe.flags.payment_request_status_from_backend = True
            try:
                pr.status = status
                if status == "Requested" and transaction_id:
                    pr.razorpay_order_id = transaction_id
                    pr.gateway_status = "created"
                    pr.transaction_id = transaction_id
                if payment_id:
                    pr.transaction_id = payment_id
                    pr.razorpay_payment_id = payment_id
                if response_data:
                    pr.gateway_response = json.dumps(response_data, indent=4)
                if status == "Paid":
                    pr.failure_message = None
                    pr.gateway_status = "captured"
                    pr.paid_on = now_datetime()
                    if transaction_id:
                        if not getattr(pr, "razorpay_order_id", None) or str(transaction_id).startswith(
                            "order_"
                        ):
                            pr.razorpay_order_id = transaction_id
                    if payment_id:
                        pr.razorpay_payment_id = payment_id
                if failure_reason:
                    pr.failure_message = failure_reason
                    pr.gateway_status = "failed"
                pr.save(ignore_permissions=True)
                if status in ["Paid", "Requested"]:
                    pr.submit()
            finally:
                if frappe.flags.get("payment_request_status_from_backend"):
                    del frappe.flags.payment_request_status_from_backend

    @staticmethod
    @frappe.whitelist()
    def create_application_fee_razorpay_order(applicant_name):
        """Creates Razorpay order for application fee payment."""
        try:
            from slcm.api.service.application_fee_service import sync_application_fee_assignment_for_applicant
            applicant = frappe.get_doc("Applicant", applicant_name)
            if applicant.application_fee_status == "Paid":
                frappe.throw(_("Application fee has already been paid."))
            if applicant.application_fee_status == "Waived":
                frappe.throw(_("Application fee has been waived."))

            fee_amount = flt(applicant.application_fee_amount)
            if fee_amount <= 0:
                from slcm.api.service.application_fee_service import get_application_fee_for_category, _get_applicant_category
                category = _get_applicant_category(applicant_name)
                fee_amount = get_application_fee_for_category(applicant.program, applicant.admission_cycle, category)
                if fee_amount > 0:
                    frappe.db.set_value("Applicant", applicant_name, "application_fee_amount", fee_amount)
                    applicant.application_fee_amount = fee_amount
            
            if fee_amount <= 0:
                frappe.throw(_("Application fee amount is zero. No payment required."))

            actual_payable = fee_amount

            from slcm.api.service.application_fee_service import get_payment_gateway_for_application_fee
            gateway = (
                get_payment_gateway_for_application_fee(applicant.program, applicant.admission_cycle)
                or _default_payment_gateway()
            )
            try:
                from payments.utils import get_payment_gateway_controller
                controller = get_payment_gateway_controller(gateway)
            except ImportError as e:
                frappe.log_error(frappe.get_traceback(), "Application Fee Order Creation Failed")
                frappe.throw(_("Payment gateway is not available. Please install the Payments app and configure a Payment Gateway (e.g. Razorpay)."))
            if not controller:
                frappe.throw(_("Payment Gateway '{0}' not found or not configured. Please set up Razorpay (or your gateway) in Payment Gateway doctype.").format(gateway))

            payment_details = {
                "amount": actual_payable,
                "title": _("Application Fee"),
                "description": _("Application Fee for {0}").format(applicant.program or ""),
                "reference_doctype": "Applicant",
                "reference_docname": applicant_name,
                "payer_email": applicant.email or "",
                "payer_name": applicant.candidate_name,
                "currency": frappe.defaults.get_global_default("currency") or "INR",
                "receipt": (applicant_name[:40]) if applicant_name else None
            }

            pr_name = frappe.db.get_value(
                "Payment Request",
                {
                    "reference_doctype": "Applicant",
                    "reference_name": applicant_name,
                    "docstatus": ["!=", 2],
                },
                "name",
            )
            pr = frappe.get_doc("Payment Request", pr_name) if pr_name else None
            if pr:
                pr_status = (pr.status or "").strip()
                if pr_status == "Paid":
                    if applicant.application_fee_status != "Paid":
                        frappe.db.set_value("Applicant", applicant_name, "application_fee_status", "Paid")
                        sync_application_fee_assignment_for_applicant(applicant_name)
                        frappe.db.commit()
                    return {"already_paid": True}
                if pr_status == "Failed" or flt(pr.amount) != actual_payable:
                    cancel_payment_request_for_retry(pr)
                    pr = None

            rzp_client = get_razorpay_client()
            if pr:
                order = prepare_checkout_order(
                    rzp_client, controller, payment_details, pr, actual_payable
                )
            else:
                try:
                    order = controller.create_order(**payment_details)
                except Exception as order_err:
                    frappe.log_error(frappe.get_traceback(), "Application Fee Order Creation Failed")
                    err_msg = str(order_err) if order_err else _("Unknown error")
                    frappe.throw(_("Payment gateway could not create order: {0}").format(err_msg))
                if not order or not order.get("id"):
                    frappe.throw(_("Order creation failed. Please check gateway logs."))

            order_id = order.get("id") or order.get("order_id")
            FeeService._update_payment_request_for_applicant(
                applicant, gateway, order_id, "Requested", response_data=order
            )
            frappe.db.set_value("Applicant", applicant_name, "application_fee_status", "Requested")
            frappe.db.commit()
            sync_application_fee_assignment_for_applicant(applicant_name)
            frappe.db.commit()

            return {
                "order_id": order_id,
                "key_id": controller.api_key,
                "amount": order.get("amount"),
                "currency": order.get("currency"),
                "gateway": gateway
            }
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Application Fee Order Creation Failed")
            raise

    @staticmethod
    def complete_application_fee_payment(applicant_doc, razorpay_payment_id, razorpay_order_id, gateway, response_data=None):
        """Idempotently records payment for applicant's application fee and links/syncs everything."""
        frappe.db.sql(
            "SELECT name FROM `tabApplicant` WHERE name = %s FOR UPDATE",
            applicant_doc.name,
        )
        if frappe.db.get_value("Applicant", applicant_doc.name, "application_fee_status") == "Paid":
            FeeService._generate_application_fee_receipt(applicant_doc, razorpay_payment_id, "Online")
            return

        FeeService._update_payment_request_for_applicant(
            applicant_doc, gateway, razorpay_order_id, "Paid",
            payment_id=razorpay_payment_id,
            response_data=response_data or {"payment_id": razorpay_payment_id, "order_id": razorpay_order_id}
        )

        frappe.db.set_value("Applicant", applicant_doc.name, "application_fee_status", "Paid")
        FeeService._generate_application_fee_receipt(applicant_doc, razorpay_payment_id, "Online")

        from slcm.api.service.application_fee_service import sync_application_fee_assignment_for_applicant
        assignment_name = sync_application_fee_assignment_for_applicant(applicant_doc.name)
        if assignment_name:
            frappe.db.set_value("Applicant Fee Assignment", assignment_name, "transaction_id", razorpay_payment_id)

        applicant_doc.reload()
        if applicant_doc.status == "Submitted":
            from slcm.admission.web_form.applicant_form.applicant_form import submit_applicant
            submit_applicant(applicant_doc.name, "Completed")

        frappe.db.commit()

        frappe.db.commit()

    @staticmethod
    @frappe.whitelist()
    def verify_application_fee_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, applicant_name):
        """Verifies Razorpay payment for application fee and marks as paid."""
        try:
            # Step 1: SELECT FOR UPDATE lock
            frappe.db.sql(
                "SELECT name FROM `tabApplicant` WHERE name = %s FOR UPDATE",
                applicant_name,
            )

            # Step 2: reload()
            applicant = frappe.get_doc("Applicant", applicant_name)
            applicant.reload()

            # Step 3: already paid check
            if applicant.application_fee_status == "Paid":
                return {"status": "success"}

            # Use gateway from Payment Request (created with order), else from Programme Reservation Policy, else default
            pr_gateway = frappe.db.get_value(
                "Payment Request",
                {"reference_doctype": "Applicant", "reference_name": applicant_name, "transaction_id": razorpay_order_id},
                "payment_gateway"
            )
            if not pr_gateway:
                from slcm.api.service.application_fee_service import get_payment_gateway_for_application_fee
                pr_gateway = get_payment_gateway_for_application_fee(applicant.program, applicant.admission_cycle)
            gateway = pr_gateway or _default_payment_gateway()
            
            # Validate Payment Request ownership
            pr_name = frappe.db.get_value(
                "Payment Request",
                {
                    "reference_doctype": "Applicant",
                    "reference_name": applicant.name,
                    "docstatus": 1,
                    "transaction_id": razorpay_order_id,
                },
                "name",
            )
            if not pr_name:
                pr_name = frappe.db.get_value(
                    "Payment Request",
                    {
                        "reference_doctype": "Applicant",
                        "reference_name": applicant.name,
                        "docstatus": 1,
                        "razorpay_order_id": razorpay_order_id,
                    },
                    "name",
                )
            if not pr_name:
                pr_name = frappe.db.get_value(
                    "Payment Request",
                    {
                        "reference_doctype": "Applicant",
                        "reference_name": applicant.name,
                        "docstatus": 1,
                    },
                    "name",
                    order_by="creation desc",
                )
            if not pr_name:
                frappe.throw(_("No Payment Request found for this applicant."))

            # Acquire row-level lock on Payment Request to prevent deadlock / race condition with webhook
            frappe.db.sql(
                "SELECT name FROM `tabPayment Request` WHERE name = %s FOR UPDATE",
                pr_name,
            )

            # Reload fresh state AFTER acquiring lock
            pr = frappe.get_doc("Payment Request", pr_name, check_permission=False)
            if pr.status == "Paid":
                return {"status": "success"}

            duplicate_paid = frappe.db.exists(
                "Payment Request",
                {
                    "status": "Paid",
                    "transaction_id": razorpay_payment_id,
                    "name": ["!=", pr_name],
                },
            )
            if duplicate_paid:
                frappe.throw(_("This Razorpay payment has already been recorded."))

            pr = frappe.get_doc("Payment Request", pr_name)
            expected_order_id = pr.transaction_id or pr.razorpay_order_id
            if expected_order_id != razorpay_order_id:
                frappe.throw(_("Payment Request mismatch"))

            from payments.utils import get_payment_gateway_controller
            controller = get_payment_gateway_controller(gateway)

            # Step 4: verify signature
            body = razorpay_order_id + "|" + razorpay_payment_id
            api_secret = controller.get_password("api_secret")
            controller.verify_signature(body, razorpay_signature, api_secret)

            # Step 5: fetch payment from Razorpay
            import razorpay
            rzp_settings = frappe.get_single("Razorpay Settings")
            rzp_client = razorpay.Client(
                auth=(rzp_settings.api_key, rzp_settings.get_password("api_secret"))
            )
            payment = rzp_client.payment.fetch(razorpay_payment_id)

            # Step 6: validate amount/order/currency/status
            expected_amount = int(flt(pr.get("grand_total") or pr.amount) * 100)
            actual_amount = payment.get("amount")
            
            if actual_amount < expected_amount:
                frappe.log_error(
                    title="Applicant Payment Amount Mismatch",
                    message=(
                        f"Applicant: {applicant.name}\n"
                        f"Expected: {expected_amount}\n"
                        f"Actual: {actual_amount}\n"
                        f"Payment ID: {razorpay_payment_id}"
                    )
                )
                frappe.throw(_("Payment amount validation failed"))

            if payment.get("order_id") != razorpay_order_id:
                frappe.throw(_("Order validation failed"))

            # Validate currency
            currency = getattr(applicant, "currency", None) or frappe.defaults.get_global_default("currency") or "INR"
            if payment.get("currency") != currency:
                frappe.throw(_("Currency validation failed"))

            if payment.get("status") == "failed":
                error_reason = (
                    payment.get("error_description")
                    or payment.get("error_code")
                    or _("Payment failed at the gateway.")
                )
                frappe.throw(_("Payment Failed: {0}").format(error_reason))

            if payment.get("status") == "authorized":
                try:
                    payment = rzp_client.payment.capture(razorpay_payment_id, expected_amount, {"currency": payment.get("currency") or "INR"})
                except Exception as e:
                    frappe.log_error(frappe.get_traceback(), f"Razorpay Capture API Call Failed for Payment ID {razorpay_payment_id}")
                    frappe.throw(_("Failed to capture authorized payment at the gateway. Please retry or contact support."))

            if payment.get("status") != "captured":
                frappe.throw(_("Payment is not captured"))

            # Step 7: mark paid
            FeeService.complete_application_fee_payment(
                applicant,
                razorpay_payment_id,
                razorpay_order_id,
                gateway,
                response_data=payment
            )

            return {"status": "success"}
        except frappe.ValidationError as e:
            frappe.db.rollback()
            return {"status": "failed", "message": str(e)}
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "Application Fee Verification Failed")
            return {"status": "failed", "message": _("An unexpected error occurred during payment verification. Please contact support.")}

    @staticmethod
    def _generate_application_fee_receipt(applicant_doc, transaction_id, payment_mode,
            bank_name=None, cheque_number=None, cheque_date=None, upi_id=None, remarks=None):
        """Generates Applicant Payment Receipt for application fee."""
        try:
            if transaction_id:
                existing = frappe.db.exists(
                    "Applicant Payment Receipt",
                    {
                        "applicant": applicant_doc.name,
                        "transaction_id": transaction_id,
                        "docstatus": ["<", 2],
                    },
                    "name",
                )
                if existing:
                    return existing

            existing = frappe.db.sql(
                """
                SELECT name FROM `tabApplicant Payment Receipt`
                WHERE applicant = %s AND IFNULL(offer_letter, '') = ''
                ORDER BY creation DESC LIMIT 1
                """,
                applicant_doc.name,
            )
            if existing:
                return existing[0][0]

            from slcm.api.service.application_fee_service import get_application_fee_for_category, _get_applicant_category
            category = _get_applicant_category(applicant_doc.name)
            is_foreign = getattr(applicant_doc, "foriegn_national", "") == "Yes"
            fee_amount = flt(
                get_application_fee_for_category(applicant_doc.program, applicant_doc.admission_cycle, category, is_foreign=is_foreign)
            )
            if fee_amount <= 0:
                fee_amount = flt(applicant_doc.application_fee_amount or 0)

            receipt = frappe.new_doc("Applicant Payment Receipt")
            receipt.applicant = applicant_doc.name
            receipt.program = applicant_doc.program
            receipt.academic_year = getattr(applicant_doc, "academic_year", None) or None
            tpl = get_payment_receipt_template_for_policy(
                applicant_doc.program, applicant_doc.admission_cycle
            )
            if tpl:
                receipt.payment_receipt_template = tpl
            receipt.payment_date = frappe.utils.today()
            receipt.transaction_id = transaction_id
            receipt.payment_mode = payment_mode
            receipt.total_amount = flt(fee_amount)
            receipt.currency = frappe.defaults.get_global_default("currency") or "INR"
            receipt.bank_name = bank_name
            receipt.cheque_number = cheque_number
            receipt.cheque_date = cheque_date
            receipt.upi_id = upi_id
            receipt.remarks = remarks

            pr = frappe.db.get_value("Payment Request", {"transaction_id": transaction_id}, "name")
            if not pr:
                pr = frappe.db.get_value(
                    "Payment Request",
                    {
                        "reference_doctype": "Applicant",
                        "reference_name": applicant_doc.name,
                        "status": "Paid",
                    },
                    "name",
                    order_by="modified desc",
                )
            if pr:
                if frappe.db.get_value("Payment Request", pr, "docstatus") != 2:
                    receipt.payment_reference = pr
                
            receipt.append("fee_components", {
                "fee_component": "Application Fee",
                "component_name": "Application Fee",
                "amount": fee_amount,
                "is_taxable": 0,
                "tax_rate": 0,
                "tax_amount": 0,
                "total_amount": fee_amount
            })

            receipt.insert(ignore_permissions=True)
            return receipt.name
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Application Fee Receipt Generation Failed")
            return None

    @staticmethod
    def sync_application_fee_after_gateway_capture(pr_name):
        """
        Razorpay webhook marks Payment Request Paid before client verify runs.
        For application fee (reference Applicant), set applicant paid and create receipt. Idempotent.
        """
        if not pr_name:
            return
        pr = frappe.get_doc("Payment Request", pr_name)
        if pr.reference_doctype != "Applicant" or not pr.reference_name:
            return
        if (pr.status or "").strip() != "Paid":
            return
        applicant_name = pr.reference_name
        dup = frappe.db.sql(
            """
            SELECT name FROM `tabApplicant Payment Receipt`
            WHERE applicant = %s AND IFNULL(offer_letter, '') = ''
            LIMIT 1
            """,
            applicant_name,
        )
        if dup:
            return
        applicant = frappe.get_doc("Applicant", applicant_name)
        if (applicant.application_fee_status or "").strip() != "Paid":
            frappe.db.set_value("Applicant", applicant_name, "application_fee_status", "Paid")
        pay_ref = (getattr(pr, "razorpay_payment_id", None) or pr.transaction_id or "").strip() or pr.name
        FeeService._generate_application_fee_receipt(applicant, pay_ref, "Online")
        from slcm.api.service.application_fee_service import sync_application_fee_assignment_for_applicant
        sync_application_fee_assignment_for_applicant(applicant_name)

    @staticmethod
    @frappe.whitelist()
    def process_application_fee_payment(applicant_name, payment_mode="Cash", reference_number=None,
            bank_name=None, cheque_number=None, cheque_date=None, upi_id=None, remarks=None):
        """Records offline/manual application fee payment."""
        applicant = frappe.get_doc("Applicant", applicant_name)
        if applicant.application_fee_status == "Paid":
            frappe.throw(_("Application fee has already been paid."))

        gateway = "Manual Payment"
        FeeService._update_payment_request_for_applicant(
            applicant, gateway, reference_number or "N/A", "Paid", payment_id=reference_number
        )
        frappe.db.set_value("Applicant", applicant_name, "application_fee_status", "Paid")
        frappe.db.commit()

        out = FeeService._generate_application_fee_receipt(
            applicant, reference_number or "N/A", payment_mode,
            bank_name=bank_name, cheque_number=cheque_number, cheque_date=cheque_date,
            upi_id=upi_id, remarks=remarks
        )
        from slcm.api.service.application_fee_service import sync_application_fee_assignment_for_applicant
        sync_application_fee_assignment_for_applicant(applicant_name)
        frappe.db.commit()
        return out

    @staticmethod
    @frappe.whitelist()
    def log_application_fee_payment_failure(applicant_name, order_id, error_data):
        """Logs application fee payment failure."""
        try:
            applicant = frappe.get_doc("Applicant", applicant_name)
            gateway = _default_payment_gateway()
            if isinstance(error_data, str):
                try:
                    error_data = json.loads(error_data)
                except Exception:
                    pass
            err_msg = ""
            is_gateway_failure = True
            if isinstance(error_data, dict):
                err_msg = error_data.get("description") or error_data.get("message") or str(error_data)
                # Differentiate manual dismiss from actual failure
                if not (error_data.get("code") or error_data.get("reason") or error_data.get("step")):
                    is_gateway_failure = False
            else:
                err_msg = str(error_data)
                
            pr_status = "Requested"
            
            FeeService._update_payment_request_for_applicant(
                applicant, gateway, order_id, pr_status, failure_reason=err_msg, response_data=error_data
            )
            if applicant.application_fee_status != "Paid":
                frappe.db.set_value(
                    "Applicant", applicant_name, "application_fee_status", "Pending", update_modified=True
                )
                frappe.db.commit()
            return {"status": "success"}
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Log Application Fee Failure Failed")
            return {"status": "error", "message": str(e)}

    @staticmethod
    def reconcile_pending_payments():
        """
        Scheduled job to reconcile stale pending payment requests against Razorpay.
        Captures authorized payments and completes captured payments (incl. late auth).
        """
        from frappe.utils import add_to_date, now_datetime

        cutoff = add_to_date(now_datetime(), minutes=-15)
        failed_cutoff = add_to_date(now_datetime(), days=-3)
        fields = [
            "name", "reference_doctype", "reference_name", "transaction_id",
            "razorpay_order_id", "payment_gateway", "amount", "currency",
        ]

        pending_requests = frappe.get_all(
            "Payment Request",
            filters={
                "status": ["in", ["Requested", "Initiated", "Payment Initiated"]],
                "modified": ["<", cutoff],
                "docstatus": 1,
                "reference_doctype": ["in", list(ADMISSION_REF_DOCTYPES)],
            },
            fields=fields,
        )
        failed_requests = frappe.get_all(
            "Payment Request",
            filters={
                "status": "Failed",
                "modified": [">", failed_cutoff],
                "docstatus": 1,
                "reference_doctype": ["in", list(ADMISSION_REF_DOCTYPES)],
            },
            fields=fields,
        )

        by_name = {row.name: row for row in pending_requests + failed_requests}
        if not by_name:
            return

        try:
            rzp_client = get_razorpay_client()
        except Exception:
            frappe.logger().error("Reconciliation Scheduler: Razorpay credentials not configured.")
            return

        for pr_data in by_name.values():
            savepoint = f"reconcile_{pr_data.name}".replace("-", "_")
            try:
                frappe.db.savepoint(savepoint)
                result = reconcile_payment_request_record(pr_data, rzp_client)
                print(f"Result for {pr_data.name} is {result}")
                if result == "captured":
                    frappe.logger().info(
                        f"Reconciliation Scheduler: completed PR={pr_data.name}"
                    )
            except Exception:
                frappe.db.rollback(save_point=savepoint)
                import traceback; print(f"Exception in reconcile_pending_payments for {pr_data.name}:\n", traceback.format_exc())
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Reconciliation Scheduler Failed for PR={pr_data.name}",
                )

    @staticmethod
    def reconcile_single_payment(payment_request_name):
        pr_data = frappe.get_doc("Payment Request", payment_request_name)
        if pr_data.payment_gateway and pr_data.payment_gateway != "Razorpay":
            return {"status": "error", "message": _("Only Razorpay payments can be reconciled manually.")}

        order_id = pr_data.razorpay_order_id or pr_data.transaction_id
        if not order_id or not str(order_id).startswith("order_"):
            return {"status": "error", "message": _("Invalid or missing order ID.")}

        try:
            rzp_client = get_razorpay_client()
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

        try:
            result = reconcile_payment_request_record(pr_data, rzp_client)
        except Exception as exc:
            return {"status": "error", "message": f"Razorpay API Error: {str(exc)}"}

        if result == "captured":
            payment_id = frappe.db.get_value(
                "Payment Request", payment_request_name, "razorpay_payment_id"
            ) or frappe.db.get_value(
                "Payment Request", payment_request_name, "transaction_id"
            )
            return {
                "status": "success",
                "message": _("Payment successfully reconciled as Paid. Razorpay Payment ID: {0}").format(
                    payment_id or ""
                ),
            }
        if result == "failed":
            failure_message = frappe.db.get_value(
                "Payment Request", payment_request_name, "failure_message"
            )
            return {
                "status": "error",
                "message": _("Payment was failed at Razorpay. Marked as Failed. Error: {0}").format(
                    failure_message or ""
                ),
            }
        if result == "pending":
            return {"status": "info", "message": _("Payment is still pending at Razorpay.")}
        return {"status": "info", "message": _("No payment attempts found at Razorpay for this order.")}


@frappe.whitelist()
def create_offer_razorpay_order(offer_name):
    return FeeService.create_offer_razorpay_order(offer_name)

@frappe.whitelist()
def verify_offer_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, offer_name):
    return FeeService.verify_offer_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, offer_name)

@frappe.whitelist()
def process_fee_payment(offer_name, payment_mode="Cash", reference_number=None, 
                       bank_name=None, cheque_number=None, cheque_date=None, 
                       upi_id=None, remarks=None):
    return FeeService.process_fee_payment(
        offer_name, payment_mode, reference_number, 
        bank_name, cheque_number, cheque_date, upi_id, remarks
    )
@frappe.whitelist()
def log_payment_failure(offer_name, order_id, error_data):
    return FeeService.log_payment_failure(offer_name, order_id, error_data)

@frappe.whitelist()
def create_application_fee_razorpay_order(applicant_name):
    return FeeService.create_application_fee_razorpay_order(applicant_name)

@frappe.whitelist()
def verify_application_fee_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, applicant_name):
    return FeeService.verify_application_fee_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, applicant_name)

@frappe.whitelist()
def process_application_fee_payment(applicant_name, payment_mode="Cash", reference_number=None,
        bank_name=None, cheque_number=None, cheque_date=None, upi_id=None, remarks=None):
    return FeeService.process_application_fee_payment(
        applicant_name, payment_mode, reference_number,
        bank_name, cheque_number, cheque_date, upi_id, remarks
    )

@frappe.whitelist()
def log_application_fee_payment_failure(applicant_name, order_id, error_data):
    return FeeService.log_application_fee_payment_failure(applicant_name, order_id, error_data)

@frappe.whitelist()
def reconcile_pending_payments():
    return FeeService.reconcile_pending_payments()

@frappe.whitelist()
def reconcile_single_payment(payment_request_name):
    return FeeService.reconcile_single_payment(payment_request_name)
