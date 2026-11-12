"""
Parent Portal – Secure Fee Payment API
========================================
Parents pay on behalf of their ward. Every endpoint validates:
  1. Caller is an authenticated, non-Guest user.
  2. The student_name supplied is actually linked to the caller (parent-ward check).
  3. The Fee Invoice belongs to that student (IDOR guard).
  4. Amount always comes from server-side outstanding_amount.

Payment recording is identical to the student portal: a Fee Payment is
inserted and submitted, which updates Fee Invoice (status, paid_amount,
outstanding_amount) and therefore reflects immediately in:
  • Student portal  (reads the same Fee Invoice)
  • Frappe desk     (Fee Invoice + Fee Payment doctypes)
"""

import hashlib
import hmac as _hmac
import json as _json

import frappe
from slcm.api.razorpay_reconcile import attach_intent, cap_fee_payment, lock_intent, verify_order
from frappe import _
from frappe.utils import flt, today


# ── Internal helpers ───────────────────────────────────────────────────────

def _require_parent_for_student(student_name):
    """Validate the caller is a non-guest parent of *student_name*.

    Returns student_name if valid, otherwise raises PermissionError.
    """
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to continue."), frappe.AuthenticationError)

    user = frappe.session.user

    # Verify the student is linked to this parent via tabStudent Parent child table
    linked = frappe.db.sql(
        """
        SELECT sm.name
        FROM `tabStudent Master` sm
        INNER JOIN `tabStudent Parent` sp
               ON sp.parent = sm.name AND sp.parenttype = 'Student Master'
        WHERE sp.email = %s AND sm.name = %s
        LIMIT 1
        """,
        (user, student_name),
        as_dict=True,
    )

    if not linked:
        frappe.throw(
            _("You do not have permission to make payments for this student."),
            frappe.PermissionError,
        )

    return student_name


def _get_owned_invoice(invoice_name, student_name):
    """Fetch a Fee Invoice belonging to *student_name* (IDOR guard)."""
    inv = frappe.db.get_value(
        "Fee Invoice",
        {"name": invoice_name, "student": student_name},
        [
            "name", "student", "student_name",
            "outstanding_amount", "final_payable_amount",
            "paid_amount", "status",
        ],
        as_dict=True,
    )
    if not inv:
        frappe.throw(
            _("Invoice not found or you do not have permission to access it."),
            frappe.PermissionError,
        )
    return inv


def _get_razorpay_controller():
    try:
        from payments.utils import get_payment_gateway_controller
        return get_payment_gateway_controller("Razorpay")
    except Exception:
        frappe.throw(
            _("Payment gateway is not configured. Please contact the Bursar's Office."),
            frappe.ValidationError,
        )


def _build_order_payload(controller, inv, student_name, parent_user):
    """Create a Razorpay order and return the full payload dict.

    Uses the parent's name/email for Razorpay prefill (they're the one paying),
    but records the student as the fee owner.
    """
    sm = frappe.db.get_value(
        "Student Master",
        student_name,
        ["first_name", "last_name", "phone"],
        as_dict=True,
    ) or {}
    student_full_name = " ".join(
        filter(None, [sm.get("first_name"), sm.get("last_name")])
    ) or inv.student_name

    # Payer is the parent — use their Frappe User record
    parent_doc = frappe.db.get_value(
        "User", parent_user, ["full_name", "email"], as_dict=True
    ) or {}
    payer_name  = parent_doc.get("full_name") or parent_user
    payer_email = parent_doc.get("email") or parent_user
    payer_phone = sm.get("phone") or ""

    outstanding = flt(inv.outstanding_amount)

    try:
        order = controller.create_order(
            amount=outstanding,
            currency="INR",
            title=_("Fee Payment – {0}").format(inv.name),
            description=_("Fee payment for {0} (paid by parent)").format(student_full_name),
            reference_doctype="Fee Invoice",
            reference_docname=inv.name,
            payer_email=payer_email,
            payer_name=payer_name,
            receipt=inv.name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "parent_payment._build_order_payload")
        frappe.throw(
            _("Could not create payment order. Please try again or contact support."),
            frappe.ValidationError,
        )

    # lets the scheduler record this payment if the browser never confirms it
    attach_intent(order, "invoice", student_name, outstanding, paid_by_role="Parent", invoice_name=inv.name)

    return {
        "order_id":            order.get("id"),
        "integration_request": order.get("integration_request"),
        "amount":              order.get("amount"),
        "currency":            order.get("currency", "INR"),
        "key_id":              controller.api_key,
        "payer_name":          payer_name,
        "payer_email":         payer_email,
        "payer_phone":         payer_phone,
        "invoice_name":        inv.name,
        "student_name":        student_name,
        "outstanding":         outstanding,
    }


# ── Public whitelisted endpoints ───────────────────────────────────────────

@frappe.whitelist()
def create_payment_order(invoice_name, student_name):
    """Create a Razorpay order for a parent paying a student's Fee Invoice.

    Validates:
    * Caller is authenticated and is a parent of student_name.
    * Invoice belongs to student_name.
    * Invoice has positive outstanding and is not Paid/Cancelled.
    """
    _require_parent_for_student(student_name)
    inv = _get_owned_invoice(invoice_name, student_name)

    if inv.status in ("Paid", "Cancelled"):
        frappe.throw(_("This invoice is already {0}.").format(inv.status))

    if flt(inv.outstanding_amount) <= 0:
        frappe.throw(_("There is no outstanding amount on this invoice."))

    # Razorpay-only legacy endpoint; the Parent Portal uses student_payment.parent_create_payment_order,
    # which also handles Easebuzz.
    from slcm.slcm.fee import payment_gateway as gw
    if gw.for_invoice(invoice_name) != gw.RAZORPAY:
        from slcm.api.student_payment import parent_create_payment_order
        return parent_create_payment_order(invoice_name, student_name)

    from slcm.slcm.fee.checkout_guard import ensure_no_other_checkout
    ensure_no_other_checkout(student_name, invoice=invoice_name, paid_by_role="Parent")

    frappe.db.set_value(
        "Fee Invoice", invoice_name, "payment_status", "Payment Initiated",
        update_modified=False,
    )
    frappe.db.commit()

    controller = _get_razorpay_controller()
    return _build_order_payload(controller, inv, student_name, frappe.session.user)


@frappe.whitelist()
def confirm_fee_payment(invoice_name, student_name, integration_request,
                        razorpay_payment_id, razorpay_order_id, razorpay_signature):
    """Verify Razorpay HMAC-SHA256 signature and record the fee payment.

    Idempotent — safe to call more than once (only creates one Fee Payment).
    Payment recording updates Fee Invoice, which propagates to student portal
    and Frappe desk automatically.
    """
    _require_parent_for_student(student_name)
    inv = _get_owned_invoice(invoice_name, student_name)

    if inv.status == "Paid" or flt(inv.outstanding_amount) <= 0:
        from slcm.api.student_payment import _already_paid
        return {
            **_already_paid(razorpay_payment_id),
            "invoice_status":        inv.status,
            "paid_amount":           flt(inv.paid_amount),
            "outstanding_amount":    0.0,
            "formatted_paid":        "₹{:,.0f}".format(flt(inv.paid_amount)),
            "formatted_outstanding": "₹0",
        }

    # ── Verify Razorpay HMAC-SHA256 signature ─────────────────────────
    try:
        rzp_settings = frappe.get_doc("Razorpay Settings")
        secret = rzp_settings.get_password(fieldname="api_secret", raise_exception=False) or ""
        if not secret:
            frappe.throw(_("Payment gateway is not configured."), frappe.ValidationError)

        message  = (razorpay_order_id + "|" + razorpay_payment_id).encode("utf-8")
        expected = _hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

        if not _hmac.compare_digest(expected, razorpay_signature):
            frappe.throw(_("Payment signature verification failed."), frappe.PermissionError)
    except (frappe.PermissionError, frappe.ValidationError):
        raise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "parent_payment.confirm_fee_payment: sig check")
        frappe.throw(_("Could not verify payment. Please contact the Bursar's Office."))

    # the order must be this student's order for exactly this invoice (not just any valid payment)
    intent = verify_order(integration_request, razorpay_order_id, razorpay_payment_id, student_name, "invoice", invoice_name=invoice_name)

    # ── Update Integration Request (best-effort) ───────────────────────
    try:
        from payments.payment_gateways.doctype.razorpay_settings.razorpay_settings import (
            order_payment_success,
        )
        order_payment_success(
            integration_request,
            _json.dumps({
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_order_id":   razorpay_order_id,
                "razorpay_signature":  razorpay_signature,
            }),
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "parent_payment.confirm_fee_payment: IR update (non-fatal)",
        )

    # serialise with the payment reconciler (slcm/api/razorpay_reconcile.py)
    lock_intent(integration_request)
    # ── Idempotently create Fee Payment ───────────────────────────────
    existing_fp = frappe.db.get_value(
        "Fee Payment",
        {"fee_invoice": invoice_name, "docstatus": 1},
        "name",
        order_by="creation desc",
    )

    if not existing_fp:
        inv_doc     = frappe.get_doc("Fee Invoice", invoice_name)
        outstanding = flt(inv_doc.outstanding_amount)
        if outstanding > 0:
            fp = frappe.get_doc({
                "doctype":          "Fee Payment",
                "fee_invoice":      invoice_name,
                "student":          student_name,
                "amount":           outstanding,
                "payment_date":     today(),
                "payment_mode":     "Online Payment",
                "reference_number": razorpay_payment_id,
                "payment_gateway":  "Razorpay",
                "remarks":          "Paid by parent via Parent Portal",
            })
            # never record more than this order actually charged
            if cap_fee_payment(fp, intent.amount):
                fp.insert(ignore_permissions=True)
                fp.submit()
            frappe.db.commit()

    frappe.db.set_value(
        "Fee Invoice", invoice_name, "payment_status", "Captured",
        update_modified=False,
    )
    frappe.db.commit()

    # ── Return refreshed invoice state ────────────────────────────────
    inv_doc = frappe.get_doc("Fee Invoice", invoice_name)
    return {
        "status":                "success",
        "invoice_status":        inv_doc.status,
        "paid_amount":           flt(inv_doc.paid_amount),
        "outstanding_amount":    max(flt(inv_doc.outstanding_amount), 0),
        "formatted_paid":        "₹{:,.0f}".format(flt(inv_doc.paid_amount)),
        "formatted_outstanding": "₹{:,.0f}".format(max(flt(inv_doc.outstanding_amount), 0)),
    }


@frappe.whitelist()
def sync_payment_status(invoice_name, student_name, integration_request=None, payment_id=None):
    """Sync payment status from Razorpay after a failure or dismissal."""
    _require_parent_for_student(student_name)
    _get_owned_invoice(invoice_name, student_name)  # IDOR guard

    pid = payment_id or ""
    if not pid and integration_request:
        pid = frappe.db.get_value("Integration Request", integration_request, "payment_id") or ""

    if not pid:
        return {"status": "no_payment", "rzp_status": None}

    # Import and reuse the status-fetch helper from student_payment
    try:
        from slcm.api.student_payment import _fetch_razorpay_payment_details, _RZP_STATUS_MAP
        details = _fetch_razorpay_payment_details(pid)
    except Exception:
        return {"status": "fetch_failed", "payment_id": pid}

    rzp_status = (details.get("raw_data") or {}).get("status") or ""
    ir_status, inv_status = _RZP_STATUS_MAP.get(rzp_status, (None, None))

    if integration_request and ir_status:
        current = frappe.db.get_value("Integration Request", integration_request, "status") or ""
        if current != "Completed":
            frappe.db.set_value(
                "Integration Request",
                integration_request,
                {"status": ir_status, "payment_id": pid},
                update_modified=False,
            )

    if inv_status:
        frappe.db.set_value(
            "Fee Invoice", invoice_name, "payment_status", inv_status,
            update_modified=False,
        )

    if integration_request or inv_status:
        frappe.db.commit()

    return {
        "status":     "ok",
        "rzp_status": rzp_status,
        "ir_status":  ir_status,
        "inv_status": inv_status,
        "payment_id": pid,
    }


@frappe.whitelist()
def get_invoice_summary(invoice_name, student_name):
    """Return a lightweight summary for refreshing a fee card without page reload."""
    _require_parent_for_student(student_name)
    inv = _get_owned_invoice(invoice_name, student_name)

    return {
        "outstanding_amount":    flt(inv.outstanding_amount),
        "paid_amount":           flt(inv.paid_amount),
        "final_payable_amount":  flt(inv.final_payable_amount),
        "status":                inv.status,
        "formatted_outstanding": "₹{:,.0f}".format(max(flt(inv.outstanding_amount), 0)),
        "formatted_paid":        "₹{:,.0f}".format(flt(inv.paid_amount)),
    }
