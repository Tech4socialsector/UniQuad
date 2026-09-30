"""
Student Portal – Secure Fee Payment API
========================================
All endpoints validate that the logged-in user owns the requested
Fee Invoice before any payment action is performed.

Security model
--------------
* Guest access → HTTP 403 on every endpoint.
* Invoice ownership: the invoice's `student` field must match the student
  record linked to `frappe.session.user`.
* Amount is always sourced from the server-side `outstanding_amount`; the
  client cannot influence the charge amount.
* CSRF: handled automatically by Frappe's @frappe.whitelist() decorator
  (requires X-Frappe-CSRF-Token header on non-GET calls).
* Razorpay signature verification is delegated to the payments app's
  `order_payment_success` handler, which performs HMAC-SHA256 validation.
"""

import hashlib
import hmac as _hmac
import json as _json

import frappe
from frappe import _
from frappe.utils import flt, today, getdate, add_days

# ── Internal helpers ───────────────────────────────────────────────────────

def _require_student():
    """Return the Student Master name for the current session user.
    Raises AuthenticationError if the user is a guest or has no student record.
    """
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to continue."), frappe.AuthenticationError)

    user = frappe.session.user
    for field in ("user", "email", "official_email_id"):
        name = frappe.db.get_value("Student Master", {field: user}, "name")
        if name:
            return name

    frappe.throw(_("No student record found for your account."), frappe.PermissionError)


def _get_owned_invoice(invoice_name, student_name):
    """Fetch a Fee Invoice that belongs to *student_name*.
    Raises PermissionError if the invoice does not exist or is owned by
    a different student (prevents IDOR).
    """
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
    """Return the configured Razorpay gateway controller or throw a clear error."""
    try:
        from payments.utils import get_payment_gateway_controller
        return get_payment_gateway_controller("Razorpay")
    except Exception:
        frappe.throw(
            _("Payment gateway is not configured. Please contact the Bursar's Office."),
            frappe.ValidationError,
        )


def _build_order_payload(controller, inv, student_name):
    """Create a Razorpay order for *inv* and return the full response dict."""
    sm = frappe.db.get_value(
        "Student Master",
        student_name,
        ["first_name", "last_name", "email", "official_email_id", "phone"],
        as_dict=True,
    ) or {}
    payer_name  = " ".join(filter(None, [sm.get("first_name"), sm.get("last_name")])) or inv.student_name
    payer_email = sm.get("official_email_id") or sm.get("email") or frappe.session.user
    payer_phone = sm.get("phone") or ""

    outstanding = flt(inv.outstanding_amount)

    try:
        order = controller.create_order(
            amount=outstanding,
            currency="INR",
            title=_("Fee Payment – {0}").format(inv.name),
            description=_("Fee payment for {0}").format(payer_name),
            reference_doctype="Fee Invoice",
            reference_docname=inv.name,
            payer_email=payer_email,
            payer_name=payer_name,
            receipt=inv.name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "student_payment._build_order_payload")
        frappe.throw(
            _("Could not create payment order. Please try again or contact support."),
            frappe.ValidationError,
        )

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
        "outstanding":         outstanding,
    }


def _ensure_fee_component():
    """Return the name of a generic 'Program Fee' Fee Component.
    Creates one if it does not already exist.
    """
    existing = frappe.db.get_value(
        "Fee Component",
        {"component_name": "Program Fee"},
        "name",
    )
    if existing:
        return existing

    # Create a generic component so invoices have at least one line item
    comp = frappe.get_doc({
        "doctype":        "Fee Component",
        "component_name": "Program Fee",
        "component_type": "Tuition Fee",
        "demand_type":    "Academic",
        "amount":         0,
    })
    comp.insert(ignore_permissions=True)
    frappe.db.commit()
    return comp.name


def _create_invoice_from_sm(student_name):
    """Mint a Fee Invoice directly from Student Master fee fields.

    Called when the student has outstanding fees recorded on their SM record
    but no corresponding Fee Invoice has been raised by the admin yet.
    This creates a minimal, single-component invoice so the student can pay.

    Returns the Fee Invoice document.
    """
    sm = frappe.db.get_value(
        "Student Master",
        student_name,
        [
            "total_program_fee", "discount_amount", "scholarship_amount",
            "net_program_fee", "total_paid_amount",
            "programme", "academic_year",
            "first_name", "last_name",
        ],
        as_dict=True,
    ) or {}

    total_fee    = flt(sm.get("total_program_fee") or 0)
    # discount_amount is the calculated scholarship applied to the programme fee.
    # scholarship_amount is the raw admin-entered value (fallback).
    scholarship  = flt(sm.get("discount_amount") or 0) or flt(sm.get("scholarship_amount") or 0)
    already_paid = flt(sm.get("total_paid_amount") or 0)

    if total_fee <= 0:
        frappe.throw(_("No fee amount found on your student record."))

    net = flt(sm.get("net_program_fee") or 0) or max(total_fee - scholarship, 0)
    outstanding = max(net - already_paid, 0)

    if outstanding <= 0:
        frappe.throw(_("No outstanding amount to pay."))

    # Academic context
    enrollment = (
        frappe.db.get_value(
            "Student Enrollment",
            {"student": student_name, "status": "Enrolled"},
            ["name", "academic_year", "term_name", "program"],
            as_dict=True,
            order_by="creation desc",
        )
    )

    fee_component_name = _ensure_fee_component()

    # Build the invoice
    invoice = frappe.get_doc({
        "doctype":          "Fee Invoice",
        "student":          student_name,
        "program":          (enrollment and enrollment.program) or sm.get("programme") or "",
        "academic_year":    (enrollment and enrollment.academic_year) or sm.get("academic_year") or "",
        "academic_term":    (enrollment and enrollment.term_name) or "",
        "enrollment":       (enrollment and enrollment.name) or "",
        "invoice_date":     today(),
        "due_date":         add_days(today(), 30),
        "scholarship_amount": scholarship,
        "fee_components":   [{
            "fee_component":  fee_component_name,
            "component_name": "Program Fee",
            "amount":         total_fee,
            "is_taxable":     0,
            "tax_amount":     0,
            "total_amount":   total_fee,
        }],
    })
    invoice.insert(ignore_permissions=True)

    # Record already-paid amount as a payment entry so the outstanding is correct
    if already_paid > 0:
        # Create a Fee Payment to reflect offline/prior payments
        payment = frappe.get_doc({
            "doctype":        "Fee Payment",
            "fee_invoice":    invoice.name,
            "student":        student_name,
            "payment_date":   today(),
            "payment_mode":   "Bank Transfer",
            "amount":         already_paid,
            "remarks":        "Prior payment recorded from student master",
            "status":         "Draft",
        })
        payment.insert(ignore_permissions=True)
        # submit() triggers FeePayment.on_submit → update_fee_invoice(), which
        # already appends the payment row to invoice.payments and saves it.
        # Do NOT manually append again — that would double-count the payment.
        payment.submit()

    frappe.db.commit()
    invoice.reload()
    return invoice


# ── Public whitelisted endpoints ───────────────────────────────────────────

@frappe.whitelist()
def create_payment_order(invoice_name):
    """Create a Razorpay order for an existing Fee Invoice.

    Validates:
    * Caller is an authenticated student.
    * The invoice belongs to that student (IDOR guard).
    * The invoice has a positive outstanding balance.
    * The invoice is not already Paid or Cancelled.
    """
    student_name = _require_student()
    inv          = _get_owned_invoice(invoice_name, student_name)

    if inv.status in ("Paid", "Cancelled"):
        frappe.throw(_("This invoice is already {0}.").format(inv.status))

    if flt(inv.outstanding_amount) <= 0:
        frappe.throw(_("There is no outstanding amount on this invoice."))

    frappe.db.set_value(
        "Fee Invoice", invoice_name, "payment_status", "Payment Initiated", update_modified=False
    )
    prev_status = frappe.db.get_value("Student Master", inv.student, "fee_payment_status") or "Unpaid"
    frappe.db.set_value(
        "Student Master", inv.student, "fee_payment_status", "Payment Initiated",
        update_modified=False,
    )
    frappe.db.commit()

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    _append_payment_log(
        inv.student,
        "Payment Initiated",
        amount=flt(inv.outstanding_amount),
        invoice=invoice_name,
        payment_mode="Online Payment",
        from_status=prev_status,
        to_status="Payment Initiated",
        remarks="Razorpay order created",
    )

    controller = _get_razorpay_controller()
    return _build_order_payload(controller, inv, student_name)


@frappe.whitelist()
def ensure_invoice_and_create_order():
    """Ensure the student has a payable Fee Invoice, creating one from their
    Student Master fee data if necessary, then create and return a Razorpay order.

    Called by the PAY NOW button on the Student Master fee fallback card when
    no Fee Invoice exists yet.

    Returns the same dict as create_payment_order().
    """
    student_name = _require_student()

    # Look for an existing unpaid/partially-paid invoice
    existing = frappe.db.get_value(
        "Fee Invoice",
        {
            "student":         student_name,
            "status":          ["not in", ["Paid", "Cancelled"]],
            "outstanding_amount": [">", 0],
        },
        ["name", "student", "student_name", "outstanding_amount",
         "final_payable_amount", "paid_amount", "status"],
        as_dict=True,
        order_by="creation desc",
    )

    if existing:
        inv = existing
    else:
        # Mint a fresh invoice from SM fee fields
        inv_doc = _create_invoice_from_sm(student_name)
        inv = frappe._dict({
            "name":               inv_doc.name,
            "student":            inv_doc.student,
            "student_name":       inv_doc.student_name,
            "outstanding_amount": inv_doc.outstanding_amount,
            "final_payable_amount": inv_doc.final_payable_amount,
            "paid_amount":        inv_doc.paid_amount,
            "status":             inv_doc.status,
        })

    if flt(inv.outstanding_amount) <= 0:
        frappe.throw(_("No outstanding amount to pay."))

    # ── Apply pending scholarship if Finance hasn't updated the invoice yet ──
    # SM discount_amount is the authoritative scholarship figure.  If it is
    # larger than what is recorded on the invoice's scholarship_amount, the
    # difference is a concession already granted to the student but not yet
    # reflected on the invoice document.  We deduct it from the charge amount
    # so Razorpay collects the correct effective balance (e.g. ₹20,045 instead
    # of the raw invoice outstanding ₹21,100).
    sm_discount  = flt(frappe.db.get_value("Student Master", student_name, "discount_amount") or 0)
    inv_sch      = flt(frappe.db.get_value("Fee Invoice", inv.name, "scholarship_amount") or 0)
    pending_sch  = max(round(sm_discount - inv_sch, 2), 0)
    effective_outstanding = max(flt(inv.outstanding_amount) - pending_sch, 0)

    if effective_outstanding <= 0:
        frappe.throw(_("No outstanding amount to pay after applying scholarship."))

    # Override outstanding_amount on the in-memory dict so _build_order_payload
    # charges the effective amount.  The database record is NOT changed here —
    # Finance will update the invoice separately via the normal workflow.
    inv = frappe._dict(inv)
    inv.outstanding_amount = effective_outstanding

    # ── Mark "Payment Initiated" on both SM and Invoice ───────────────
    invoice_name_for_order = inv.name
    prev_status = frappe.db.get_value(
        "Student Master", student_name, "fee_payment_status"
    ) or "Unpaid"

    _IN_FLIGHT_ALREADY = {"Payment Initiated", "Authorized"}
    if prev_status not in _IN_FLIGHT_ALREADY:
        frappe.db.set_value(
            "Fee Invoice", invoice_name_for_order,
            "payment_status", "Payment Initiated",
            update_modified=False,
        )
        frappe.db.set_value(
            "Student Master", student_name,
            "fee_payment_status", "Payment Initiated",
            update_modified=False,
        )
        frappe.db.commit()

        from slcm.slcm.doctype.student_master.student_master import _append_payment_log
        _append_payment_log(
            student_name,
            "Payment Initiated",
            amount=effective_outstanding,
            invoice=invoice_name_for_order,
            payment_mode="Online Payment",
            from_status=prev_status,
            to_status="Payment Initiated",
            remarks=(
                f"Razorpay order created (ensure_invoice_and_create_order)"
                + (f" — pending scholarship ₹{pending_sch:,.2f} applied" if pending_sch > 0 else "")
            ),
        )

    controller = _get_razorpay_controller()
    return _build_order_payload(controller, inv, student_name)


@frappe.whitelist()
def confirm_fee_payment(invoice_name, integration_request,
                        razorpay_payment_id, razorpay_order_id, razorpay_signature):
    """
    Called from the browser after Razorpay's success handler fires.

    Security updates:
    - Added SELECT FOR UPDATE locks to prevent race conditions.
    - Added anti-replay check for razorpay_payment_id.
    - Added local signature verification.
    """
    student_name = _require_student()
    
    # Lock the invoice row
    frappe.db.sql("SELECT name FROM `tabFee Invoice` WHERE name = %s FOR UPDATE", invoice_name)
    inv = _get_owned_invoice(invoice_name, student_name)

    if inv.status == "Paid" or flt(inv.outstanding_amount) <= 0:
        return {
            "status":                "already_paid",
            "invoice_status":        inv.status,
            "paid_amount":           flt(inv.paid_amount),
            "outstanding_amount":    0.0,
            "formatted_paid":        "₹{:,.0f}".format(flt(inv.paid_amount)),
            "formatted_outstanding": "₹0",
        }

    # ── Verify Razorpay HMAC-SHA256 signature locally ─────────────────
    try:
        controller = frappe.get_doc("Razorpay Settings")
        secret     = controller.get_password(fieldname="api_secret", raise_exception=False) or ""
        if not secret:
            frappe.throw(_("Payment gateway is not configured."), frappe.ValidationError)

        message  = (razorpay_order_id + "|" + razorpay_payment_id).encode("utf-8")
        expected = _hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

        if not _hmac.compare_digest(expected, razorpay_signature):
            frappe.throw(_("Payment signature verification failed."), frappe.PermissionError)
    except (frappe.PermissionError, frappe.ValidationError):
        raise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "confirm_fee_payment: signature check")
        frappe.throw(_("Could not verify payment. Please contact the Bursar's Office."))

    # Anti-replay check
    duplicate_payment = frappe.db.exists("Fee Payment", {"reference_number": razorpay_payment_id, "docstatus": 1})
    if duplicate_payment:
        frappe.throw(_("This payment has already been recorded."))

    # ── Update Integration Request ────────────────────────────────────
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
        frappe.log_error(frappe.get_traceback(), "confirm_fee_payment: IR update (non-fatal)")

    # ── Idempotently create Fee Payment ──────────────────────────────
    existing_fp = frappe.db.get_value(
        "Fee Payment",
        {"fee_invoice": invoice_name, "docstatus": 1},
        "name",
        order_by="creation desc",
    )

    if not existing_fp:
        inv_doc = frappe.get_doc("Fee Invoice", invoice_name)
        ir_amount = None
        try:
            ir_data = frappe.db.get_value("Integration Request", integration_request, "data")
            if ir_data:
                ir_json = _json.loads(ir_data)
                if ir_json.get("amount"):
                    ir_amount = round(flt(ir_json["amount"]) / 100, 2)
        except Exception:
            pass

        outstanding = ir_amount if ir_amount and ir_amount > 0 else flt(inv_doc.outstanding_amount)

        if outstanding > 0:
            fp = frappe.get_doc({
                "doctype":          "Fee Payment",
                "fee_invoice":      invoice_name,
                "student":          student_name,
                "amount":           outstanding,
                "payment_date":     today(),
                "payment_mode":     "Online Payment",
                "reference_number": razorpay_payment_id,
            })
            fp.insert(ignore_permissions=True)
            fp.submit()
            frappe.db.commit()

    # ── Mark gateway payment_status as Captured ───────────────────────
    frappe.db.set_value("Fee Invoice", invoice_name, "payment_status", "Captured", update_modified=False)
    frappe.db.commit()

    # ── Payment Log: Captured ─────────────────────────────────────────
    inv_after = frappe.get_doc("Fee Invoice", invoice_name)
    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    _append_payment_log(
        student_name,
        "Captured",
        amount=flt(inv_after.paid_amount),
        invoice=invoice_name,
        payment_mode="Online Payment",
        razorpay_payment_id=razorpay_payment_id,
        razorpay_order_id=razorpay_order_id,
        webhook_status="Not Applicable",
        from_status="Payment Initiated",
        to_status=inv_after.status,
        remarks=f"Payment captured — Razorpay order {razorpay_order_id}",
    )

    return {
        "status":                "success",
        "invoice_status":        inv_after.status,
        "paid_amount":           flt(inv_after.paid_amount),
        "outstanding_amount":    max(flt(inv_after.outstanding_amount), 0),
        "formatted_paid":        "₹{:,.0f}".format(flt(inv_after.paid_amount)),
        "formatted_outstanding": "₹{:,.0f}".format(max(flt(inv_after.outstanding_amount), 0)),
    }


# ── Fee Demand payment endpoints ──────────────────────────────────────────


@frappe.whitelist()
def create_demand_payment_order(fee_demand_name):
    """Create a Razorpay order for a Fee Demand outstanding amount.

    Validates:
    * Caller is an authenticated student.
    * The demand belongs to that student (IDOR guard).
    * The demand is in a payable state (Pending, Overdue, or Partially Paid).
    * Outstanding amount is > 0.
    """
    student_name = _require_student()

    demand = frappe.db.get_value(
        "Fee Demand",
        {"name": fee_demand_name, "student": student_name},
        ["name", "student", "fee_component", "description", "status",
         "outstanding_amount", "net_payable", "demand_type"],
        as_dict=True,
    )
    if not demand:
        frappe.throw(
            _("Fee Demand not found or you do not have permission to access it."),
            frappe.PermissionError,
        )

    if demand.status in ("Paid", "Waived", "Cancelled"):
        frappe.throw(_("This demand is already {0}.").format(demand.status))

    outstanding = flt(demand.outstanding_amount)
    if outstanding <= 0:
        frappe.throw(_("There is no outstanding amount on this demand."))

    sm = frappe.db.get_value(
        "Student Master",
        student_name,
        ["first_name", "last_name", "email", "official_email_id", "phone"],
        as_dict=True,
    ) or {}
    payer_name  = " ".join(filter(None, [sm.get("first_name"), sm.get("last_name")])) or student_name
    payer_email = sm.get("official_email_id") or sm.get("email") or frappe.session.user
    payer_phone = sm.get("phone") or ""

    component   = demand.fee_component or demand.description or "Fee"
    controller  = _get_razorpay_controller()

    try:
        order = controller.create_order(
            amount=outstanding,
            currency="INR",
            title=_("Fee Payment – {0}").format(component),
            description=_("Fee demand payment for {0}").format(payer_name),
            reference_doctype="Fee Demand",
            reference_docname=fee_demand_name,
            payer_email=payer_email,
            payer_name=payer_name,
            receipt=fee_demand_name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "create_demand_payment_order")
        frappe.throw(
            _("Could not create payment order. Please try again or contact support."),
            frappe.ValidationError,
        )

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    _append_payment_log(
        student_name,
        "Payment Initiated",
        amount=outstanding,
        fee_demand=fee_demand_name,
        payment_mode="Online Payment",
        paid_by_role="Student",
        paid_by_name=payer_name,
        from_status=demand.status,
        to_status="Payment Initiated",
        remarks=f"Razorpay order created for Fee Demand {fee_demand_name} — {component}",
    )

    return {
        "order_id":            order.get("id"),
        "integration_request": order.get("integration_request"),
        "amount":              order.get("amount"),
        "currency":            order.get("currency", "INR"),
        "key_id":              controller.api_key,
        "payer_name":          payer_name,
        "payer_email":         payer_email,
        "payer_phone":         payer_phone,
        "fee_demand_name":     fee_demand_name,
        "component":           component,
        "outstanding":         outstanding,
    }


@frappe.whitelist()
def cancel_demand_payment(fee_demand_name, integration_request=None):
    """Called from the browser ondismiss handler when the student closes the
    Razorpay modal without completing payment for a Fee Demand.
    Logs a 'Payment Cancelled' entry in the audit trail.
    """
    student_name = _require_student()

    demand = frappe.db.get_value(
        "Fee Demand",
        {"name": fee_demand_name, "student": student_name},
        ["status", "fee_component", "description", "outstanding_amount"],
        as_dict=True,
    )
    if not demand:
        return {"status": "noop"}

    if integration_request:
        try:
            frappe.db.set_value(
                "Integration Request", integration_request, "status", "Cancelled",
                update_modified=False,
            )
        except Exception:
            pass

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    _append_payment_log(
        student_name,
        "Payment Cancelled",
        amount=flt(demand.outstanding_amount),
        fee_demand=fee_demand_name,
        payment_mode="Online Payment",
        paid_by_role="Student",
        from_status="Payment Initiated",
        to_status=demand.status,
        remarks="Student dismissed Razorpay modal without completing payment",
    )
    frappe.db.commit()
    return {"status": "cancelled"}


# ── Re-exam fees inside the fee page's single "Pay All" order ─────────────────
# The student fee page pays unpaid Fee Demands and unpaid re-exam fees together in one
# Razorpay order. Re-exam registrations are passed alongside the demands; on confirmation
# each one is marked Paid with its own Re Exam Payment Log, as the re-exam flow does.

def _parse_name_list(value):
    import json as _j
    if not value:
        return []
    try:
        names = _j.loads(value) if isinstance(value, str) else list(value)
    except Exception:
        frappe.throw(_("Invalid list."), frappe.ValidationError)
    return [n for n in names if n]


def _payable_re_exams(registration_names, student_name):
    """The student's re-exam registrations that can be paid now (IDOR guard included)."""
    regs = []
    for n in registration_names:
        reg = _get_owned_registration(n, student_name)
        if reg.status != "Registered":
            frappe.throw(_("Re-exam registration {0} is {1}.").format(n, reg.status), frappe.ValidationError)
        if reg.payment_status in ("Paid", "Captured"):
            frappe.throw(_("Re-exam fee {0} is already paid.").format(n), frappe.ValidationError)
        if reg.payment_status == "Refunded":
            frappe.throw(_("Re-exam registration {0} was refunded. Please contact the administration.").format(n))
        if flt(reg.re_exam_fee) <= 0:
            frappe.throw(_("Re-exam registration {0} has no fee.").format(n), frappe.ValidationError)
        regs.append(reg)
    return regs


def _mark_re_exams_paid(registration_names, student_name, razorpay_payment_id, razorpay_order_id):
    """Mark each re-exam registration paid by this combined payment (idempotent)."""
    paid = []
    for n in registration_names:
        reg = frappe.db.get_value(
            "Re Exam Registration", {"name": n, "student": student_name},
            ["name", "re_exam_fee", "payment_status"], as_dict=True,
        )
        if not reg or reg.payment_status in ("Paid", "Captured"):
            continue
        if not frappe.db.exists("Re Exam Payment Log", {"re_exam_registration": n, "razorpay_payment_id": razorpay_payment_id}):
            try:
                frappe.get_doc({
                    "doctype":              "Re Exam Payment Log",
                    "re_exam_registration": n,
                    "razorpay_payment_id":  razorpay_payment_id,
                    "razorpay_order_id":    razorpay_order_id,
                    "payment_status":       "Paid",
                    "amount":               flt(reg.re_exam_fee),
                    "settlement_amount":    flt(reg.re_exam_fee),
                    "transaction_date":     frappe.utils.now_datetime(),
                    "gateway_response":     _json.dumps({
                        "razorpay_payment_id": razorpay_payment_id,
                        "razorpay_order_id":   razorpay_order_id,
                        "source":              "fee_page_pay_all",
                    }, indent=2),
                }).insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Pay All: re-exam payment log (non-fatal)")
        frappe.db.set_value(
            "Re Exam Registration", n,
            {"payment_status": "Paid", "payment_reference": razorpay_payment_id},
            update_modified=True,
        )
        paid.append({"name": n, "amount": flt(reg.re_exam_fee)})
    return paid


def _reset_re_exams(registration_names, student_name, status):
    """Put re-exams that were in this order back to Pending (cancelled) or Payment Failed."""
    for n in registration_names:
        current = frappe.db.get_value("Re Exam Registration", {"name": n, "student": student_name}, "payment_status")
        if current == "Payment Initiated":
            frappe.db.set_value("Re Exam Registration", n, "payment_status", status, update_modified=False)


@frappe.whitelist()
def create_bulk_demand_payment_order(fee_demand_names, re_exam_registrations=None):
    """Create a single Razorpay order that covers multiple Fee Demands at once.

    ``fee_demand_names`` is a JSON-encoded list of Fee Demand names; ``re_exam_registrations``
    an optional JSON list of the student's unpaid Re Exam Registrations paid in the same order.

    Security:
    * Every demand / registration must belong to the calling student (IDOR guard).
    * Only Pending / Overdue demands with outstanding > 0 are accepted.
    * Total amount is computed server-side; the client cannot influence it.
    """
    import json as _j
    student_name = _require_student()

    try:
        names = _j.loads(fee_demand_names) if isinstance(fee_demand_names, str) else list(fee_demand_names or [])
    except Exception:
        frappe.throw(_("Invalid demand list."), frappe.ValidationError)
    rex_names = _parse_name_list(re_exam_registrations)

    if not names and not rex_names:
        frappe.throw(_("No fee demands provided."), frappe.ValidationError)
    if len(names) > 50:
        frappe.throw(_("Too many demands in a single payment (max 50)."), frappe.ValidationError)

    demands = []
    total = 0.0
    for n in names:
        d = frappe.db.get_value(
            "Fee Demand",
            {"name": n, "student": student_name},
            ["name", "fee_component", "description", "status", "outstanding_amount", "net_payable"],
            as_dict=True,
        )
        if not d:
            frappe.throw(_("Demand {0} not found or access denied.").format(n), frappe.PermissionError)
        if d.status in ("Paid", "Waived", "Cancelled"):
            frappe.throw(_("Demand {0} is already {1}.").format(n, d.status), frappe.ValidationError)
        out = flt(d.outstanding_amount)
        if out <= 0:
            frappe.throw(_("Demand {0} has no outstanding amount.").format(n), frappe.ValidationError)
        total += out
        demands.append(d)

    re_exams = _payable_re_exams(rex_names, student_name)
    total += sum(flt(r.re_exam_fee) for r in re_exams)

    if total <= 0:
        frappe.throw(_("Total outstanding amount is zero."), frappe.ValidationError)

    sm = frappe.db.get_value(
        "Student Master", student_name,
        ["first_name", "last_name", "email", "official_email_id", "phone"],
        as_dict=True,
    ) or {}
    payer_name  = " ".join(filter(None, [sm.get("first_name"), sm.get("last_name")])) or student_name
    payer_email = sm.get("official_email_id") or sm.get("email") or frappe.session.user
    payer_phone = sm.get("phone") or ""

    labels = [d.fee_component or d.description or "Fee" for d in demands] + [
        _("Re-exam: {0}").format(frappe.db.get_value("Course", r.course, "course_name") or r.course) for r in re_exams
    ]
    item_count = len(labels)
    components = ", ".join(labels[:3])
    if item_count > 3:
        components += f" +{item_count - 3} more"

    controller = _get_razorpay_controller()
    # Razorpay receipt field: the first demand, else the first re-exam registration
    ref_doctype, receipt_ref = ("Fee Demand", demands[0].name) if demands else ("Re Exam Registration", re_exams[0].name)

    try:
        order = controller.create_order(
            amount=total,
            currency="INR",
            title=_("Fee Payment – {0} item(s)").format(item_count),
            description=_("Fee payment for {0}").format(payer_name),
            reference_doctype=ref_doctype,
            reference_docname=receipt_ref,
            payer_email=payer_email,
            payer_name=payer_name,
            receipt=receipt_ref,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "create_bulk_demand_payment_order")
        frappe.throw(
            _("Could not create payment order. Please try again or contact support."),
            frappe.ValidationError,
        )

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    for d in demands:
        _append_payment_log(
            student_name,
            "Payment Initiated",
            amount=flt(d.outstanding_amount),
            fee_demand=d.name,
            payment_mode="Online Payment",
            paid_by_role="Student",
            paid_by_name=payer_name,
            remarks=f"Bulk Razorpay order for {len(demands)} demands: {', '.join(x.name for x in demands)}",
        )
    for r in re_exams:
        frappe.db.set_value("Re Exam Registration", r.name, "payment_status", "Payment Initiated", update_modified=False)
    if re_exams:
        frappe.db.commit()

    return {
        "order_id":            order.get("id"),
        "integration_request": order.get("integration_request"),
        "amount":              order.get("amount"),
        "currency":            order.get("currency", "INR"),
        "key_id":              controller.api_key,
        "payer_name":          payer_name,
        "payer_email":         payer_email,
        "payer_phone":         payer_phone,
        "total":               total,
        "components":          components,
        "demand_names":        [d.name for d in demands],
        "re_exam_registrations": [r.name for r in re_exams],
    }


@frappe.whitelist()
def confirm_bulk_demand_payment(fee_demand_names, integration_request,
                                razorpay_payment_id, razorpay_order_id, razorpay_signature,
                                re_exam_registrations=None):
    """Verify HMAC signature and record a single Fee Payment covering all demands; re-exam
    registrations paid in the same order are marked Paid with their own payment log.

    ``fee_demand_names`` / ``re_exam_registrations`` are JSON-encoded lists.
    """
    import json as _j
    student_name = _require_student()

    try:
        names = _j.loads(fee_demand_names) if isinstance(fee_demand_names, str) else list(fee_demand_names or [])
    except Exception:
        frappe.throw(_("Invalid demand list."), frappe.ValidationError)
    rex_names = _parse_name_list(re_exam_registrations)

    # ── Signature verification ────────────────────────────────────────
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
        frappe.log_error(frappe.get_traceback(), "confirm_bulk_demand_payment: sig check")
        frappe.throw(_("Could not verify payment. Please contact the Bursar's Office."))

    # ── Update Integration Request (best-effort) ──────────────────────
    try:
        from payments.payment_gateways.doctype.razorpay_settings.razorpay_settings import order_payment_success
        order_payment_success(
            integration_request,
            _json.dumps({
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_order_id":   razorpay_order_id,
                "razorpay_signature":  razorpay_signature,
            }),
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "confirm_bulk_demand_payment: IR update (non-fatal)")

    # ── Re-exam fees in this order (idempotent on its own) ────────────
    re_exams_paid = _mark_re_exams_paid(rex_names, student_name, razorpay_payment_id, razorpay_order_id)
    if re_exams_paid:
        frappe.db.commit()
    re_exam_total = sum(r["amount"] for r in re_exams_paid)

    # ── Idempotency check ─────────────────────────────────────────────
    existing_fp = frappe.db.get_value(
        "Fee Payment",
        {"reference_number": razorpay_payment_id, "student": student_name, "docstatus": 1},
        "name",
    )
    if existing_fp:
        return {"status": "already_paid"}

    # ── Build payment_demands rows, verify ownership, compute total ───
    demand_rows = []
    total = 0.0
    for n in names:
        d = frappe.db.get_value(
            "Fee Demand",
            {"name": n, "student": student_name},
            ["name", "fee_component", "description", "status", "outstanding_amount"],
            as_dict=True,
        )
        if not d:
            continue  # demand may have been paid concurrently — skip
        if d.status in ("Paid", "Waived", "Cancelled"):
            continue
        out = flt(d.outstanding_amount)
        if out <= 0:
            continue
        demand_rows.append({
            "fee_demand":         n,
            "demand_description": d.fee_component or d.description or "",
            "outstanding_amount": out,
            "amount_allocated":   out,
        })
        total += out

    if not demand_rows:
        if re_exams_paid:
            return {
                "status":          "success",
                "demands_paid":    len(re_exams_paid),
                "total_paid":      re_exam_total,
                "formatted_total": "₹{:,.0f}".format(re_exam_total),
            }
        return {"status": "already_paid"}

    # ── Create single Fee Payment covering all demands ────────────────
    fp = frappe.get_doc({
        "doctype":          "Fee Payment",
        "student":          student_name,
        "payment_date":     today(),
        "payment_mode":     "Online Payment",
        "amount":           total,
        "reference_number": razorpay_payment_id,
        "remarks":          f"Bulk payment — Razorpay order {razorpay_order_id} — {len(demand_rows)} demands",
        "payment_demands":  demand_rows,
    })
    fp.insert(ignore_permissions=True)
    fp.submit()
    frappe.db.commit()

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    for row in demand_rows:
        _append_payment_log(
            student_name,
            "Captured",
            amount=flt(row["amount_allocated"]),
            fee_demand=row["fee_demand"],
            payment_mode="Online Payment",
            paid_by_role="Student",
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            webhook_status="Not Applicable",
            remarks=f"Bulk payment captured — {len(demand_rows)} demands — Razorpay {razorpay_order_id}",
        )

    return {
        "status":        "success",
        "demands_paid":  len(demand_rows) + len(re_exams_paid),
        "total_paid":    total + re_exam_total,
        "formatted_total": "₹{:,.0f}".format(total + re_exam_total),
    }


@frappe.whitelist()
def cancel_bulk_demand_payment(fee_demand_names, integration_request=None, re_exam_registrations=None):
    """Log a 'Payment Cancelled' entry when the student closes the Razorpay modal.

    The JS _failedAlready flag ensures this is only called for true user cancels —
    not for bank/gateway declines (those go through mark_demand_payment_failed).
    """
    import json as _j
    student_name = _require_student()
    try:
        names = _j.loads(fee_demand_names) if isinstance(fee_demand_names, str) else list(fee_demand_names or [])
    except Exception:
        return {"status": "noop"}
    try:
        _reset_re_exams(_parse_name_list(re_exam_registrations), student_name, "Pending")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "cancel_bulk_demand_payment: re-exam reset (non-fatal)")

    if integration_request:
        try:
            frappe.db.set_value(
                "Integration Request", integration_request, "status", "Cancelled",
                update_modified=False,
            )
        except Exception:
            pass

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    for dem_name in names:
        _append_payment_log(
            student_name,
            "Payment Cancelled",
            fee_demand=dem_name,
            payment_mode="Online Payment",
            paid_by_role="Student",
            remarks=f"Student dismissed bulk-payment modal for {len(names)} demands: {', '.join(names[:5])}",
        )
    frappe.db.commit()
    return {"status": "cancelled"}


@frappe.whitelist()
def confirm_demand_payment(fee_demand_name, integration_request,
                           razorpay_payment_id, razorpay_order_id, razorpay_signature):
    """Verify Razorpay HMAC-SHA256 signature and record payment against the Fee Demand.

    * Ownership check (IDOR guard).
    * Local HMAC-SHA256 signature verification — no external call.
    * Creates a submitted Fee Payment with the demand in payment_demands.
    * Idempotent: if a Fee Payment already exists for this demand+payment_id, returns success.
    """
    student_name = _require_student()

    demand = frappe.db.get_value(
        "Fee Demand",
        {"name": fee_demand_name, "student": student_name},
        ["name", "student", "fee_component", "description",
         "status", "outstanding_amount", "net_payable"],
        as_dict=True,
    )
    if not demand:
        frappe.throw(
            _("Fee Demand not found or you do not have permission to access it."),
            frappe.PermissionError,
        )

    if demand.status == "Paid" and flt(demand.outstanding_amount) <= 0:
        return {"status": "already_paid", "demand_status": "Paid"}

    # ── Verify Razorpay HMAC-SHA256 signature locally ─────────────────
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
        frappe.log_error(frappe.get_traceback(), "confirm_demand_payment: signature check")
        frappe.throw(_("Could not verify payment. Please contact the Bursar's Office."))

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
        frappe.log_error(frappe.get_traceback(), "confirm_demand_payment: IR update (non-fatal)")

    # ── Idempotently create Fee Payment ───────────────────────────────
    existing_fp = frappe.db.get_value(
        "Fee Payment",
        {"reference_number": razorpay_payment_id, "student": student_name, "docstatus": 1},
        "name",
    )

    if not existing_fp:
        outstanding = flt(demand.outstanding_amount)
        if outstanding > 0:
            fp = frappe.get_doc({
                "doctype":          "Fee Payment",
                "student":          student_name,
                "payment_date":     today(),
                "payment_mode":     "Online Payment",
                "amount":           outstanding,
                "reference_number": razorpay_payment_id,
                "remarks":          f"Razorpay order {razorpay_order_id}",
                "payment_demands":  [{
                    "fee_demand":        fee_demand_name,
                    "demand_description": demand.fee_component or demand.description or "",
                    "outstanding_amount": outstanding,
                    "amount_allocated":   outstanding,
                }],
            })
            fp.insert(ignore_permissions=True)
            fp.submit()
            frappe.db.commit()

    # ── Return refreshed demand state ─────────────────────────────────
    updated = frappe.db.get_value(
        "Fee Demand",
        fee_demand_name,
        ["status", "paid_amount", "outstanding_amount"],
        as_dict=True,
    ) or {}

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    _append_payment_log(
        student_name,
        "Captured",
        amount=flt(updated.get("paid_amount") or 0),
        fee_demand=fee_demand_name,
        payment_mode="Online Payment",
        razorpay_payment_id=razorpay_payment_id,
        razorpay_order_id=razorpay_order_id,
        webhook_status="Not Applicable",
        from_status="Payment Initiated",
        to_status=updated.get("status", ""),
        remarks=f"Payment captured for Fee Demand {fee_demand_name} — Razorpay order {razorpay_order_id}",
    )

    return {
        "status":             "success",
        "demand_status":      updated.get("status", ""),
        "paid_amount":        flt(updated.get("paid_amount") or 0),
        "outstanding_amount": max(flt(updated.get("outstanding_amount") or 0), 0),
        "formatted_paid":     "₹{:,.0f}".format(flt(updated.get("paid_amount") or 0)),
        "formatted_outstanding": "₹{:,.0f}".format(max(flt(updated.get("outstanding_amount") or 0), 0)),
    }


# ── Re-Exam payment endpoints ──────────────────────────────────────────────

def _fetch_razorpay_payment_details(payment_id):
    """Fetch full payment details from Razorpay GET /v1/payments/{id}.
    Returns a dict with parsed fields; returns {} on any error (best-effort).
    Works on both Frappe Cloud and local — only needs api_key/api_secret.
    """
    try:
        import requests as _requests
        import datetime as _dt

        settings   = frappe.get_doc("Razorpay Settings")
        api_key    = settings.api_key or ""
        api_secret = settings.get_password(fieldname="api_secret", raise_exception=False) or ""
        if not api_key or not api_secret:
            return {}

        resp = _requests.get(
            f"https://api.razorpay.com/v1/payments/{payment_id}",
            auth=(api_key, api_secret),
            timeout=10,
        )
        if resp.status_code != 200:
            frappe.log_error(
                f"Razorpay GET /v1/payments/{payment_id} → HTTP {resp.status_code}: {resp.text[:500]}",
                "_fetch_razorpay_payment_details",
            )
            return {}

        data     = resp.json()
        method   = data.get("method") or ""
        acquirer = data.get("acquirer_data") or {}

        # Transaction reference varies by method
        transaction_id = (
            acquirer.get("rrn")                    # UPI / card RRN
            or acquirer.get("upi_transaction_id")  # UPI Tx ID
            or acquirer.get("bank_transaction_id") # Netbanking
            or acquirer.get("transaction_id")
            or ""
        )

        # Account / VPA varies by method
        account = (
            data.get("vpa")                                     # UPI VPA
            or (data.get("card") or {}).get("number", "")      # Masked card number
            or data.get("bank")                                 # Netbanking bank
            or data.get("wallet")                               # Wallet name
            or ""
        )

        # Timestamp (epoch → datetime)
        transaction_date = None
        created_at = data.get("created_at")
        if created_at:
            try:
                transaction_date = _dt.datetime.utcfromtimestamp(int(created_at))
            except Exception:
                pass

        fee_paise    = int(data.get("fee") or 0)
        tax_paise    = int(data.get("tax") or 0)
        amount_paise = int(data.get("amount") or 0)

        # Settlement date — available on settled payments
        settlement_date = None
        settled_at = data.get("settled_at")
        if settled_at:
            try:
                settlement_date = _dt.date.fromtimestamp(int(settled_at)).isoformat()
            except Exception:
                pass

        return {
            "payment_method":           method,
            "transaction_id":           transaction_id,
            "account_number_or_upi_id": account,
            "transaction_date":         transaction_date,
            "failure_reason":           data.get("error_description") or "",
            "gateway_fees":             fee_paise / 100,
            "gateway_tax":              tax_paise / 100,
            "net_settled":              max((amount_paise - fee_paise - tax_paise) / 100, 0),
            "settlement_date":          settlement_date,
            "raw_data":                 data,
        }
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_fetch_razorpay_payment_details")
        return {}


def _get_owned_registration(registration_name, student_name):
    """Fetch a Re Exam Registration that belongs to *student_name* (IDOR guard)."""
    reg = frappe.db.get_value(
        "Re Exam Registration",
        {"name": registration_name, "student": student_name},
        ["name", "student", "exam_plan", "course", "re_exam_fee", "status", "payment_status"],
        as_dict=True,
    )
    if not reg:
        frappe.throw(
            _("Registration not found or you do not have permission to access it."),
            frappe.PermissionError,
        )
    return reg


def _build_re_exam_order_payload(controller, reg, student_name):
    """Create a Razorpay order for a Re Exam Registration and return the payload dict."""
    sm = frappe.db.get_value(
        "Student Master",
        student_name,
        ["first_name", "last_name", "email", "official_email_id", "phone"],
        as_dict=True,
    ) or {}
    payer_name  = " ".join(filter(None, [sm.get("first_name"), sm.get("last_name")])) or student_name
    payer_email = sm.get("official_email_id") or sm.get("email") or frappe.session.user
    payer_phone = sm.get("phone") or ""

    course_name = frappe.db.get_value("Course", reg.course, "course_name") or reg.course
    fee_amount  = flt(reg.re_exam_fee)

    try:
        order = controller.create_order(
            amount=fee_amount,
            currency="INR",
            title=_("Re-Exam Fee – {0}").format(course_name),
            description=_("Re-examination fee for {0}").format(payer_name),
            reference_doctype="Re Exam Registration",
            reference_docname=reg.name,
            payer_email=payer_email,
            payer_name=payer_name,
            receipt=reg.name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "student_payment._build_re_exam_order_payload")
        frappe.throw(
            _("Could not create payment order. Please try again or contact support."),
            frappe.ValidationError,
        )

    return {
        "order_id":            order.get("id"),
        "integration_request": order.get("integration_request"),
        "amount":              order.get("amount"),
        "currency":            order.get("currency", "INR"),
        "key_id":              controller.api_key,
        "payer_name":          payer_name,
        "payer_email":         payer_email,
        "payer_phone":         payer_phone,
        "registration_name":   reg.name,
        "course_name":         course_name,
    }


@frappe.whitelist()
def create_re_exam_payment_order(exam_plan, course):
    """Create (or retrieve) a Re Exam Registration and return a Razorpay order payload.

    Validates:
    * Caller is an authenticated student with no block override.
    * Re-exam setting exists and deadline has not passed.
    * Fee is > 0 (free registrations use initiate_re_exam_registration instead).
    * Registration is not already Paid.
    """
    student_name = _require_student()

    setting = frappe.db.get_value(
        "Re Exam Course Setting",
        {"exam_plan": exam_plan, "course": course},
        ["name", "re_exam_fee", "deadline_from", "deadline_to"],
        as_dict=True,
    )
    if not setting:
        frappe.throw(_("Re-exam registration is not open for this course yet."))

    if setting.get("deadline_to") and str(setting["deadline_to"]) < today():
        frappe.throw(_("The registration deadline for this course has passed."))

    fee_amount = flt(setting.get("re_exam_fee") or 0)
    if fee_amount <= 0:
        frappe.throw(_("This course has no re-exam fee. Use free registration instead."))

    # Block override check
    override = frappe.db.get_value(
        "Re Exam Student Override",
        {"exam_plan": exam_plan, "course": course, "student": student_name},
        "is_allowed",
    )
    if override is not None and not override:
        frappe.throw(_("You are not allowed to register for this re-examination. Please contact the faculty."))

    # Find or create registration
    existing = frappe.db.get_value(
        "Re Exam Registration",
        {"student": student_name, "exam_plan": exam_plan, "course": course},
        ["name", "status", "payment_status", "re_exam_fee"],
        as_dict=True,
    )

    if existing and existing.payment_status in ("Paid", "Captured"):
        frappe.throw(_("You have already paid for this re-examination."))

    if existing and existing.payment_status == "Refunded":
        frappe.throw(_("This registration was refunded. Please contact the administration."))

    if existing and existing.status == "Cancelled":
        frappe.throw(_("This registration has been cancelled. Please contact the administration."))

    if existing:
        reg_name = existing.name
    else:
        course_offering = frappe.db.get_value(
            "Course Schema Assignment", {"exam_plan": exam_plan, "course": course}, "course_offering"
        )
        if not course_offering:
            frappe.throw(_("No Course Offering found for this course/exam plan. Contact administration."))
        doc = frappe.new_doc("Re Exam Registration")
        doc.student         = student_name
        doc.exam_plan       = exam_plan
        doc.course          = course
        doc.course_offering = course_offering
        doc.re_exam_fee     = fee_amount
        doc.status          = "Registered"
        doc.payment_status  = "Pending"
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        reg_name = doc.name

    # Mark that the student has opened the payment modal
    frappe.db.set_value(
        "Re Exam Registration", reg_name, "payment_status", "Payment Initiated", update_modified=False
    )
    frappe.db.commit()

    reg = frappe.db.get_value(
        "Re Exam Registration",
        reg_name,
        ["name", "student", "exam_plan", "course", "re_exam_fee", "status", "payment_status"],
        as_dict=True,
    )

    controller = _get_razorpay_controller()
    return _build_re_exam_order_payload(controller, reg, student_name)


@frappe.whitelist()
def confirm_re_exam_payment(registration_name, integration_request,
                             razorpay_payment_id, razorpay_order_id, razorpay_signature):
    """Verify Razorpay HMAC-SHA256 signature and mark Re Exam Registration as Paid.

    Follows the same security model as confirm_fee_payment:
    * Ownership check (IDOR guard).
    * Local HMAC-SHA256 signature verification — no external call.
    * Idempotent: safe to call more than once.
    """
    student_name = _require_student()
    reg = _get_owned_registration(registration_name, student_name)

    if reg.payment_status in ("Paid", "Captured"):
        return {"status": "already_paid", "registration_status": "Paid"}

    # Verify signature locally
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
        frappe.log_error(frappe.get_traceback(), "confirm_re_exam_payment: signature check")
        frappe.throw(_("Could not verify payment. Please contact the administration."))

    # Update Integration Request (best-effort)
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
        frappe.log_error(frappe.get_traceback(), "confirm_re_exam_payment: IR update (non-fatal)")

    # Fetch full payment details from Razorpay (best-effort, non-blocking)
    rzp_details = _fetch_razorpay_payment_details(razorpay_payment_id)

    # Create Re Exam Payment Log (idempotent — webhook may have beaten us to it)
    existing_log = frappe.db.get_value(
        "Re Exam Payment Log",
        {"razorpay_payment_id": razorpay_payment_id},
        "name",
    )
    log_name = existing_log
    if not existing_log:
        try:
            reg_for_log = frappe.db.get_value(
                "Re Exam Registration",
                registration_name,
                ["re_exam_fee", "exam_plan", "course"],
                as_dict=True,
            ) or {}
            log_doc = frappe.get_doc({
                "doctype":                    "Re Exam Payment Log",
                "re_exam_registration":       registration_name,
                "razorpay_payment_id":        razorpay_payment_id,
                "razorpay_order_id":          razorpay_order_id,
                "payment_status":             "Paid",
                "amount":                     flt(reg_for_log.get("re_exam_fee") or 0),
                "payment_method":             rzp_details.get("payment_method") or "",
                "transaction_date":           rzp_details.get("transaction_date") or frappe.utils.now_datetime(),
                "transaction_id":             rzp_details.get("transaction_id") or "",
                "account_number_or_upi_id":   rzp_details.get("account_number_or_upi_id") or "",
                "failure_reason":             rzp_details.get("failure_reason") or "",
                "gateway_fees":               flt(rzp_details.get("gateway_fees") or 0),
                "gateway_tax":                flt(rzp_details.get("gateway_tax") or 0),
                "net_settled":                flt(rzp_details.get("net_settled") or 0),
                "settlement_amount":          flt(reg_for_log.get("re_exam_fee") or 0),
                "settlement_date":            rzp_details.get("settlement_date") or None,
                "gateway_response":           _json.dumps(
                    rzp_details.get("raw_data") or {
                        "razorpay_payment_id": razorpay_payment_id,
                        "razorpay_order_id":   razorpay_order_id,
                        "source":              "browser_confirmation",
                    }, indent=2
                ),
            })
            log_doc.insert(ignore_permissions=True)
            log_name = log_doc.name
        except Exception:
            frappe.log_error(frappe.get_traceback(), "confirm_re_exam_payment: log creation (non-fatal)")
    elif rzp_details:
        # Log already existed — patch any missing detail fields
        try:
            patch = {}
            for field, key in [
                ("payment_method",           "payment_method"),
                ("transaction_id",           "transaction_id"),
                ("account_number_or_upi_id", "account_number_or_upi_id"),
                ("transaction_date",         "transaction_date"),
                ("gateway_fees",             "gateway_fees"),
                ("gateway_tax",              "gateway_tax"),
                ("net_settled",              "net_settled"),
                ("settlement_amount",        "settlement_amount"),
                ("settlement_date",          "settlement_date"),
            ]:
                val = rzp_details.get(key)
                if val and not frappe.db.get_value("Re Exam Payment Log", existing_log, field):
                    patch[field] = val
            if patch:
                frappe.db.set_value("Re Exam Payment Log", existing_log, patch, update_modified=False)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "confirm_re_exam_payment: log patch (non-fatal)")

    # Mark registration as Paid
    frappe.db.set_value(
        "Re Exam Registration",
        registration_name,
        {
            "payment_status":    "Paid",
            "payment_reference": razorpay_payment_id,
        },
        update_modified=True,
    )
    frappe.db.commit()

    return {"status": "success", "registration_status": "Paid", "registration_name": registration_name}


@frappe.whitelist()
def cancel_re_exam_payment(registration_name):
    """Set payment_status to 'Payment Cancelled' when the student closes the Razorpay modal.

    Called when the student dismisses the Razorpay modal without completing payment.
    Only operates on registrations owned by the current student and only when the
    payment_status is exactly 'Payment Initiated' — captured/refunded records are never touched.
    """
    student_name = _require_student()
    reg = _get_owned_registration(registration_name, student_name)

    if reg.payment_status == "Payment Initiated":
        frappe.db.set_value(
            "Re Exam Registration",
            registration_name,
            "payment_status",
            "Payment Cancelled",
            update_modified=False,
        )
        frappe.db.commit()

    return {"status": "ok", "payment_status": "Payment Cancelled" if reg.payment_status == "Payment Initiated" else reg.payment_status}


# ─────────────────────────────────────────────────────────────────────────────
#  Improvement Exam Payment (mirrors Re-Exam pattern above)
# ─────────────────────────────────────────────────────────────────────────────

def _get_owned_improvement_registration(registration_name, student_name):
    """Fetch an Improvement Exam Registration that belongs to *student_name* (IDOR guard)."""
    reg = frappe.db.get_value(
        "Improvement Exam Registration",
        {"name": registration_name, "student": student_name},
        ["name", "student", "exam_plan", "course", "improvement_fee", "status", "payment_status"],
        as_dict=True,
    )
    if not reg:
        frappe.throw(
            _("Registration not found or you do not have permission to access it."),
            frappe.PermissionError,
        )
    return reg


def _build_improvement_exam_order_payload(controller, reg, student_name):
    """Create a Razorpay order for an Improvement Exam Registration and return the payload dict."""
    sm = frappe.db.get_value(
        "Student Master",
        student_name,
        ["first_name", "last_name", "email", "official_email_id", "phone"],
        as_dict=True,
    ) or {}
    payer_name  = " ".join(filter(None, [sm.get("first_name"), sm.get("last_name")])) or student_name
    payer_email = sm.get("official_email_id") or sm.get("email") or frappe.session.user
    payer_phone = sm.get("phone") or ""

    course_name = frappe.db.get_value("Course", reg.course, "course_name") or reg.course
    fee_amount  = flt(reg.improvement_fee)

    try:
        order = controller.create_order(
            amount=fee_amount,
            currency="INR",
            title=_("Improvement Exam Fee – {0}").format(course_name),
            description=_("Improvement examination fee for {0}").format(payer_name),
            reference_doctype="Improvement Exam Registration",
            reference_docname=reg.name,
            payer_email=payer_email,
            payer_name=payer_name,
            receipt=reg.name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "student_payment._build_improvement_exam_order_payload")
        frappe.throw(
            _("Could not create payment order. Please try again or contact support."),
            frappe.ValidationError,
        )

    return {
        "order_id":            order.get("id"),
        "integration_request": order.get("integration_request"),
        "amount":              order.get("amount"),
        "currency":            order.get("currency", "INR"),
        "key_id":              controller.api_key,
        "payer_name":          payer_name,
        "payer_email":         payer_email,
        "payer_phone":         payer_phone,
        "registration_name":   reg.name,
        "course_name":         course_name,
    }


@frappe.whitelist()
def create_improvement_exam_payment_order(exam_plan, course):
    """Create (or retrieve) an Improvement Exam Registration and return a Razorpay order payload."""
    student_name = _require_student()

    from slcm.api.student_portal import check_improvement_cgpa_eligibility
    check_improvement_cgpa_eligibility(student_name, exam_plan)

    setting = frappe.db.get_value(
        "Improvement Exam Course Setting",
        {"exam_plan": exam_plan, "course": course},
        ["name", "improvement_fee", "deadline_from", "deadline_to", "registration_limit"],
        as_dict=True,
    )
    if not setting:
        frappe.throw(_("Improvement exam registration is not open for this course yet."))

    if setting.get("deadline_to") and str(setting["deadline_to"]) < today():
        frappe.throw(_("The registration deadline for this course has passed."))

    fee_amount = flt(setting.get("improvement_fee") or 0)
    if fee_amount <= 0:
        frappe.throw(_("This course has no improvement exam fee. Use free registration instead."))

    # Find or create registration
    existing = frappe.db.get_value(
        "Improvement Exam Registration",
        {"student": student_name, "exam_plan": exam_plan, "course": course, "status": ["!=", "Cancelled"]},
        ["name", "status", "payment_status", "improvement_fee"],
        as_dict=True,
    )

    if existing and existing.payment_status in ("Paid", "Captured"):
        frappe.throw(_("You have already paid for this improvement examination."))

    if existing and existing.payment_status == "Refunded":
        frappe.throw(_("This registration was refunded. Please contact the administration."))

    if existing:
        reg_name = existing.name
    else:
        # Check registration limit
        if setting.get("registration_limit"):
            count_row = frappe.db.sql(
                "SELECT COUNT(*) FROM `tabImprovement Exam Registration` WHERE exam_plan=%s AND course=%s AND status!='Cancelled'",
                (exam_plan, course),
            )
            current_count = int(count_row[0][0]) if count_row else 0
            if current_count >= int(setting["registration_limit"]):
                frappe.throw(_("Registration limit has been reached for this improvement exam."))

        course_offering = frappe.db.get_value(
            "Course Schema Assignment", {"exam_plan": exam_plan, "course": course}, "course_offering"
        )
        if not course_offering:
            frappe.throw(_("No Course Offering found for this course/exam plan. Contact administration."))
        doc = frappe.new_doc("Improvement Exam Registration")
        doc.student          = student_name
        doc.exam_plan        = exam_plan
        doc.course           = course
        doc.course_offering  = course_offering
        doc.improvement_fee  = fee_amount
        doc.status           = "Registered"
        doc.payment_status   = "Pending"
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        reg_name = doc.name

    # Mark that the student has opened the payment modal
    frappe.db.set_value(
        "Improvement Exam Registration", reg_name, "payment_status", "Payment Initiated", update_modified=False
    )
    frappe.db.commit()

    reg = frappe.db.get_value(
        "Improvement Exam Registration",
        reg_name,
        ["name", "student", "exam_plan", "course", "improvement_fee", "status", "payment_status"],
        as_dict=True,
    )

    controller = _get_razorpay_controller()
    return _build_improvement_exam_order_payload(controller, reg, student_name)


@frappe.whitelist()
def confirm_improvement_exam_payment(registration_name, integration_request,
                                      razorpay_payment_id, razorpay_order_id, razorpay_signature):
    """Verify Razorpay HMAC-SHA256 signature and mark Improvement Exam Registration as Paid."""
    student_name = _require_student()
    reg = _get_owned_improvement_registration(registration_name, student_name)

    if reg.payment_status in ("Paid", "Captured"):
        return {"status": "already_paid", "registration_status": "Paid"}

    # Verify signature locally
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
        frappe.log_error(frappe.get_traceback(), "confirm_improvement_exam_payment: signature check")
        frappe.throw(_("Could not verify payment. Please contact the administration."))

    # Update Integration Request (best-effort)
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
        frappe.log_error(frappe.get_traceback(), "confirm_improvement_exam_payment: IR update (non-fatal)")

    # Fetch full payment details from Razorpay (best-effort, non-blocking)
    rzp_details = _fetch_razorpay_payment_details(razorpay_payment_id)

    # Create Improvement Exam Payment Log (idempotent)
    existing_log = frappe.db.get_value(
        "Improvement Exam Payment Log",
        {"razorpay_payment_id": razorpay_payment_id},
        "name",
    )
    if not existing_log:
        try:
            reg_for_log = frappe.db.get_value(
                "Improvement Exam Registration",
                registration_name,
                ["improvement_fee", "exam_plan", "course"],
                as_dict=True,
            ) or {}
            log_doc = frappe.get_doc({
                "doctype":                          "Improvement Exam Payment Log",
                "improvement_exam_registration":    registration_name,
                "razorpay_payment_id":              razorpay_payment_id,
                "razorpay_order_id":                razorpay_order_id,
                "payment_status":                   "Paid",
                "amount":                           flt(reg_for_log.get("improvement_fee") or 0),
                "payment_method":                   rzp_details.get("payment_method") or "",
                "transaction_date":                 rzp_details.get("transaction_date") or frappe.utils.now_datetime(),
                "transaction_id":                   rzp_details.get("transaction_id") or "",
                "account_number_or_upi_id":         rzp_details.get("account_number_or_upi_id") or "",
                "failure_reason":                   rzp_details.get("failure_reason") or "",
                "gateway_fees":                     flt(rzp_details.get("gateway_fees") or 0),
                "gateway_tax":                      flt(rzp_details.get("gateway_tax") or 0),
                "net_settled":                      flt(rzp_details.get("net_settled") or 0),
                "settlement_amount":                flt(reg_for_log.get("improvement_fee") or 0),
                "settlement_date":                  rzp_details.get("settlement_date") or None,
                "gateway_response":                 _json.dumps(
                    rzp_details.get("raw_data") or {
                        "razorpay_payment_id": razorpay_payment_id,
                        "razorpay_order_id":   razorpay_order_id,
                        "source":              "browser_confirmation",
                    }, indent=2
                ),
            })
            log_doc.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "confirm_improvement_exam_payment: log creation (non-fatal)")
    elif rzp_details:
        try:
            patch = {}
            for field, key in [
                ("payment_method",           "payment_method"),
                ("transaction_id",           "transaction_id"),
                ("account_number_or_upi_id", "account_number_or_upi_id"),
                ("transaction_date",         "transaction_date"),
                ("gateway_fees",             "gateway_fees"),
                ("gateway_tax",              "gateway_tax"),
                ("net_settled",              "net_settled"),
                ("settlement_amount",        "settlement_amount"),
                ("settlement_date",          "settlement_date"),
            ]:
                val = rzp_details.get(key)
                if val and not frappe.db.get_value("Improvement Exam Payment Log", existing_log, field):
                    patch[field] = val
            if patch:
                frappe.db.set_value("Improvement Exam Payment Log", existing_log, patch, update_modified=False)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "confirm_improvement_exam_payment: log patch (non-fatal)")

    # Mark registration as Paid
    frappe.db.set_value(
        "Improvement Exam Registration",
        registration_name,
        {
            "payment_status":    "Paid",
            "payment_reference": razorpay_payment_id,
        },
        update_modified=True,
    )
    frappe.db.commit()

    return {"status": "success", "registration_status": "Paid", "registration_name": registration_name}


@frappe.whitelist()
def cancel_improvement_exam_payment(registration_name):
    """Set payment_status to 'Payment Cancelled' when the student closes the Razorpay modal."""
    student_name = _require_student()
    reg = _get_owned_improvement_registration(registration_name, student_name)

    if reg.payment_status == "Payment Initiated":
        frappe.db.set_value(
            "Improvement Exam Registration",
            registration_name,
            "payment_status",
            "Payment Cancelled",
            update_modified=False,
        )
        frappe.db.commit()

    return {"status": "ok", "payment_status": "Payment Cancelled" if reg.payment_status == "Payment Initiated" else reg.payment_status}


# Razorpay payment status → (Integration Request status, Fee Invoice payment_status)
_RZP_STATUS_MAP = {
    "created":    ("Pending",     "Payment Initiated"),
    "authorized": ("Authorized",  "Authorized"),
    "captured":   ("Completed",   "Captured"),
    "failed":     ("Failed",      "Payment Failed"),
    "refunded":   ("Completed",   "Refunded"),
}

# Razorpay status → Student Master fee_payment_status
# NOTE: "authorized" means the bank approved the debit but Razorpay has not yet
# settled/captured the funds.  We keep it as "Authorized" (not "Paid") because a
# small number of authorized payments are later reversed.  The SM will be set to
# "Paid" / "Partially Paid" by fee_payment._sync_student_master once the Fee
# Payment Entry is submitted (i.e. after the "captured" webhook or confirm call).
_SM_STATUS_MAP = {
    "created":    "Payment Initiated",
    "authorized": "Authorized",          # ← was incorrectly "Paid" before this fix
    "captured":   None,                  # handled by fee_payment._sync_student_master
    "failed":     "Payment Failed",
    "refunded":   "Refunded",
}


def _derive_resting_sm_status(student_name, invoice_name):
    """Return the correct *resting* fee_payment_status for a student whose
    current status is an in-flight gateway state (Payment Initiated / Authorized)
    that should be rolled back.

    Logic mirrors fees.py:
      - outstanding ≤ 0         → Paid
      - 0 < paid < net_payable  → Partially Paid
      - paid == 0               → Unpaid
    """
    sm = frappe.db.get_value(
        "Student Master", student_name,
        ["net_program_fee", "total_paid_amount", "total_program_fee",
         "discount_amount", "scholarship_amount"],
        as_dict=True,
    ) or {}
    total     = flt(sm.get("total_program_fee") or 0)
    net       = flt(sm.get("net_program_fee") or 0) or max(
        total - (flt(sm.get("discount_amount") or 0) or flt(sm.get("scholarship_amount") or 0)), 0
    )
    paid_raw  = flt(sm.get("total_paid_amount") or 0)
    paid      = min(paid_raw, net) if net > 0 else paid_raw
    outstanding = max(net - paid, 0)

    if net > 0:
        if outstanding <= 0:
            return "Paid"
        elif paid > 0:
            return "Partially Paid"
    return "Unpaid"


@frappe.whitelist()
def cancel_fee_payment(invoice_name, integration_request=None):
    """Revert Student Master and Fee Invoice to the correct resting state when the
    student closes the Razorpay modal without completing payment.

    This is called from the browser's ``ondismiss`` callback so that "Payment
    Initiated" / "Authorized" states on the Student Master are never left dangling
    after a modal dismissal.

    Security:
    * Caller must be an authenticated student who owns the invoice (IDOR guard).
    * Only operates when the current SM status is an in-flight gateway state.
      Confirmed payments (Paid, Partially Paid, Refunded) are never touched.
    * Idempotent — safe to call multiple times.
    """
    student_name = _require_student()
    inv          = _get_owned_invoice(invoice_name, student_name)

    # Never touch a settled or refunded invoice
    if inv.status in ("Paid", "Cancelled"):
        return {"status": "noop", "reason": "invoice_terminal"}

    # Determine what the Student Master status should return to
    resting_status = _derive_resting_sm_status(student_name, invoice_name)

    current_sm_status = frappe.db.get_value(
        "Student Master", student_name, "fee_payment_status"
    ) or "Unpaid"

    # Only revert in-flight gateway states — never overwrite Paid/Partially Paid
    _IN_FLIGHT = {"Payment Initiated", "Authorized"}
    sm_changed = False
    if current_sm_status in _IN_FLIGHT:
        frappe.db.set_value(
            "Student Master", student_name,
            "fee_payment_status", resting_status,
            update_modified=False,
        )
        sm_changed = True

    # Revert the Fee Invoice payment_status to match
    current_inv_status = frappe.db.get_value(
        "Fee Invoice", invoice_name, "payment_status"
    ) or ""
    inv_changed = False
    if current_inv_status in _IN_FLIGHT:
        # Map resting_status → invoice payment_status equivalent
        inv_resting = {
            "Paid":           "Captured",
            "Partially Paid": "Captured",
            "Unpaid":         "Pending",
        }.get(resting_status, "Pending")
        frappe.db.set_value(
            "Fee Invoice", invoice_name, "payment_status", inv_resting,
            update_modified=False,
        )
        inv_changed = True

    # Revert Integration Request to Pending so it isn't shown as an active attempt
    if integration_request:
        try:
            ir_current = frappe.db.get_value(
                "Integration Request", integration_request, "status"
            ) or ""
            # Never downgrade a Completed IR (that would hide a real payment)
            if ir_current not in ("Completed", "Authorized"):
                frappe.db.set_value(
                    "Integration Request", integration_request,
                    "status", "Cancelled",
                    update_modified=False,
                )
        except Exception:
            pass

    if sm_changed or inv_changed:
        frappe.db.commit()

    # Append audit log entry
    if sm_changed:
        from slcm.slcm.doctype.student_master.student_master import _append_payment_log
        _append_payment_log(
            student_name,
            "Payment Cancelled",
            invoice=invoice_name,
            payment_mode="Online Payment",
            from_status=current_sm_status,
            to_status=resting_status,
            remarks="Student dismissed Razorpay modal without completing payment",
        )

    frappe.logger("student_payment").info(
        f"cancel_fee_payment: student={student_name} invoice={invoice_name} "
        f"sm_status {current_sm_status!r} → {resting_status!r} (changed={sm_changed})"
    )

    return {
        "status":         "ok",
        "sm_status":      resting_status,
        "sm_changed":     sm_changed,
        "inv_changed":    inv_changed,
    }


@frappe.whitelist()
def mark_payment_failed(invoice_name, integration_request=None,
                        payment_id=None, error_code=None, error_description=None):
    """Directly mark a fee payment as failed on Student Master, Fee Invoice, and
    Integration Request.

    Called by the browser ``payment.failed`` Razorpay callback.  Unlike
    ``sync_payment_status``, this endpoint does NOT make an outbound HTTP call to
    Razorpay's API — it trusts the event that Razorpay already delivered to the
    browser, which is authoritative for the failed case.  This makes it reliable
    in all environments (local dev, test mode, firewalled servers).

    Security:
    * Caller must own the invoice (IDOR guard).
    * Never overwrites a confirmed Paid / Partially Paid status.
    * Idempotent — safe to call more than once.
    """
    student_name = _require_student()
    inv          = _get_owned_invoice(invoice_name, student_name)

    # Never touch a terminal-success record
    _TERMINAL_OK = {"Paid", "Partially Paid"}
    current_sm = frappe.db.get_value(
        "Student Master", student_name, "fee_payment_status"
    ) or "Unpaid"

    if current_sm in _TERMINAL_OK:
        return {"status": "noop", "reason": "already_paid", "sm_status": current_sm}

    pid = (payment_id or "").strip()

    # ── Update Integration Request ──────────────────────────────────
    if integration_request:
        try:
            ir_current = frappe.db.get_value(
                "Integration Request", integration_request, "status"
            ) or ""
            if ir_current != "Completed":
                upd = {"status": "Failed"}
                if pid:
                    upd["payment_id"] = pid
                frappe.db.set_value(
                    "Integration Request", integration_request, upd,
                    update_modified=False,
                )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "mark_payment_failed: IR update")

    # ── Update Fee Invoice payment_status ───────────────────────────
    frappe.db.set_value(
        "Fee Invoice", invoice_name, "payment_status", "Payment Failed",
        update_modified=False,
    )

    # ── Update Student Master fee_payment_status ────────────────────
    frappe.db.set_value(
        "Student Master", student_name, "fee_payment_status", "Payment Failed",
        update_modified=False,
    )

    frappe.db.commit()

    # ── Audit log ───────────────────────────────────────────────────
    try:
        from slcm.slcm.doctype.student_master.student_master import _append_payment_log
        _append_payment_log(
            student_name,
            "Payment Failed",
            invoice=invoice_name,
            payment_mode="Online Payment",
            razorpay_payment_id=pid,
            from_status=current_sm,
            to_status="Payment Failed",
            error_message=f"Code: {error_code or 'N/A'} — {(error_description or '')[:200]}",
            failure_reason=(error_description or error_code or "")[:500],
            remarks=f"Razorpay payment.failed event — code: {error_code or 'N/A'}",
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "mark_payment_failed: payment log")

    frappe.logger("student_payment").info(
        f"mark_payment_failed: student={student_name} invoice={invoice_name} "
        f"pid={pid} prev_sm={current_sm!r}"
    )

    # Best-effort: also kick off async Razorpay API sync to enrich the IR record
    # (non-blocking — failure here doesn't affect the response)
    if pid:
        try:
            details = _fetch_razorpay_payment_details(pid)
            if details:
                rzp_raw = details.get("raw_data") or {}
                # Only use the API result if Razorpay confirms it really is failed
                if rzp_raw.get("status") == "failed":
                    failure_reason = (
                        rzp_raw.get("error_description")
                        or rzp_raw.get("description")
                        or ""
                    )
                    if integration_request and failure_reason:
                        try:
                            frappe.db.set_value(
                                "Integration Request", integration_request,
                                "error", failure_reason[:500],
                                update_modified=False,
                            )
                            frappe.db.commit()
                        except Exception:
                            pass
        except Exception:
            pass

    return {
        "status":    "ok",
        "sm_status": "Payment Failed",
        "prev_sm":   current_sm,
    }


@frappe.whitelist()
def sync_payment_status(invoice_name, integration_request=None, payment_id=None):
    """Fetch the actual payment status from Razorpay and update local records.

    Called from the browser after any Razorpay event (payment.failed, etc.).
    We call Razorpay's GET /v1/payments/{payment_id} from the server — never trusting
    the browser — and update both the Integration Request and Fee Invoice to match
    what Razorpay says.

    payment_id: Razorpay payment ID (from r.error.metadata.payment_id on failure,
                or from the order payload on success).  When absent, the IR's own
                payment_id field is tried.  If still absent, the SM is reverted to
                its correct resting status (user dismissed modal — no payment attempted).
    """
    student_name = _require_student()
    _get_owned_invoice(invoice_name, student_name)   # IDOR guard

    # Resolve payment_id — prefer caller-supplied, fall back to what's stored on the IR
    pid = payment_id or ""
    if not pid and integration_request:
        pid = frappe.db.get_value("Integration Request", integration_request, "payment_id") or ""

    if not pid:
        # No payment was attempted (user closed modal before entering card details).
        # Revert any in-flight "Payment Initiated" state on the SM so the portal
        # doesn't freeze in a pending state forever.
        _revert_sm_if_in_flight(invoice_name, student_name, integration_request)
        return {"status": "no_payment", "rzp_status": None}

    # Call Razorpay API from our server to get the authoritative status
    details = _fetch_razorpay_payment_details(pid)
    if not details:
        frappe.log_error(
            f"sync_payment_status: could not fetch Razorpay details for payment {pid}",
            "sync_payment_status",
        )
        # Best-effort revert to avoid leaving SM in "Payment Initiated" indefinitely
        _revert_sm_if_in_flight(invoice_name, student_name, integration_request)
        return {"status": "fetch_failed", "payment_id": pid}

    rzp_status = (details.get("raw_data") or {}).get("status") or ""

    # If Razorpay returned details but the status is missing or unrecognised
    # AND we were called with a payment_id from r.error (i.e. the caller knows
    # the payment failed), default to "failed" so the SM is never left stuck at
    # "Payment Initiated".  This also covers test-mode race conditions where
    # Razorpay's GET /v1/payments/{id} briefly returns status="" before settling.
    if not rzp_status and payment_id:
        rzp_status = "failed"

    ir_status, inv_status = _RZP_STATUS_MAP.get(rzp_status, (None, None))
    sm_status = _SM_STATUS_MAP.get(rzp_status)

    if integration_request and ir_status:
        current = frappe.db.get_value("Integration Request", integration_request, "status") or ""
        # Never downgrade a record that Razorpay already confirmed as Completed
        if current != "Completed":
            frappe.db.set_value(
                "Integration Request",
                integration_request,
                {"status": ir_status, "payment_id": pid},
                update_modified=False,
            )

    if inv_status:
        frappe.db.set_value(
            "Fee Invoice", invoice_name, "payment_status", inv_status, update_modified=False
        )

    student_for_log = None
    prev_sm = "Unpaid"
    if sm_status:
        student_for_log = frappe.db.get_value("Fee Invoice", invoice_name, "student")
        if student_for_log:
            prev_sm = frappe.db.get_value("Student Master", student_for_log, "fee_payment_status") or "Unpaid"
            # Guard: never overwrite a confirmed-successful terminal status with a
            # failure/cancellation status.  Only skip the write when BOTH conditions
            # are true: current is a successful terminal AND incoming is a failure.
            # Use AND (not OR) so that non-terminal states (e.g. "Payment Initiated")
            # are always updated regardless of what the new status is.
            _TERMINAL_OK     = {"Paid", "Partially Paid", "Refunded"}
            _FAILURE_STATUSES = {"Payment Failed", "Payment Cancelled", "Authorized"}
            _should_skip = (prev_sm in _TERMINAL_OK and sm_status in _FAILURE_STATUSES)
            if not _should_skip:
                frappe.db.set_value(
                    "Student Master", student_for_log, "fee_payment_status", sm_status,
                    update_modified=False,
                )

    if integration_request or inv_status or sm_status:
        frappe.db.commit()

    # ── Payment Log: one entry per non-trivial Razorpay status ───────
    if student_for_log and sm_status:
        _EVENT_MAP = {
            "created":    "Payment Initiated",
            "authorized": "Authorized",
            "failed":     "Payment Failed",
            "refunded":   "Refunded",
        }
        log_event = _EVENT_MAP.get(rzp_status)
        if log_event:
            from slcm.slcm.doctype.student_master.student_master import _append_payment_log
            _append_payment_log(
                student_for_log,
                log_event,
                invoice=invoice_name,
                payment_mode="Online Payment",
                razorpay_payment_id=pid,
                from_status=prev_sm,
                to_status=sm_status,
                remarks=f"Razorpay status: {rzp_status}",
            )

    return {
        "status":     "ok",
        "rzp_status": rzp_status,
        "ir_status":  ir_status,
        "inv_status": inv_status,
        "payment_id": pid,
    }


def _revert_sm_if_in_flight(invoice_name, student_name, integration_request=None):
    """Internal helper: revert SM and invoice payment_status from in-flight gateway
    states (Payment Initiated / Authorized) back to the correct resting state.

    Called when sync_payment_status determines no payment_id exists (user dismissed
    the modal without submitting a payment instrument).
    """
    _IN_FLIGHT = {"Payment Initiated", "Authorized"}
    current = frappe.db.get_value(
        "Student Master", student_name, "fee_payment_status"
    ) or "Unpaid"

    if current not in _IN_FLIGHT:
        return  # already at a resting state — nothing to do

    resting = _derive_resting_sm_status(student_name, invoice_name)
    frappe.db.set_value(
        "Student Master", student_name, "fee_payment_status", resting,
        update_modified=False,
    )

    # Revert invoice payment_status too
    inv_current = frappe.db.get_value("Fee Invoice", invoice_name, "payment_status") or ""
    if inv_current in _IN_FLIGHT:
        frappe.db.set_value(
            "Fee Invoice", invoice_name, "payment_status", "Pending",
            update_modified=False,
        )

    if integration_request:
        try:
            ir_st = frappe.db.get_value("Integration Request", integration_request, "status") or ""
            if ir_st not in ("Completed", "Authorized"):
                frappe.db.set_value(
                    "Integration Request", integration_request, "status", "Cancelled",
                    update_modified=False,
                )
        except Exception:
            pass

    frappe.db.commit()

    try:
        from slcm.slcm.doctype.student_master.student_master import _append_payment_log
        _append_payment_log(
            student_name,
            "Payment Cancelled",
            invoice=invoice_name,
            payment_mode="Online Payment",
            from_status=current,
            to_status=resting,
            remarks="No payment attempt found — modal dismissed before payment instrument submitted",
        )
    except Exception:
        pass

    frappe.logger("student_payment").info(
        f"_revert_sm_if_in_flight: student={student_name} invoice={invoice_name} "
        f"{current!r} → {resting!r}"
    )


@frappe.whitelist()
def register_re_exam_for_cash(exam_plan, course):
    """Create a Re Exam Registration for cash payment at the admin counter.

    The registration is created with payment_status='Pending'.
    Admin will mark it as Paid via the Re Exam admin page after receiving cash.
    """
    student_name = _require_student()

    setting = frappe.db.get_value(
        "Re Exam Course Setting",
        {"exam_plan": exam_plan, "course": course},
        ["name", "re_exam_fee", "deadline_from", "deadline_to"],
        as_dict=True,
    )
    if not setting:
        frappe.throw(_("Re-exam registration is not open for this course yet."))

    if setting.get("deadline_to") and str(setting["deadline_to"]) < today():
        frappe.throw(_("The registration deadline for this course has passed."))

    override = frappe.db.get_value(
        "Re Exam Student Override",
        {"exam_plan": exam_plan, "course": course, "student": student_name},
        "is_allowed",
    )
    if override is not None and not override:
        frappe.throw(_("You are not allowed to register for this re-examination."))

    # Return existing registration if it already exists and is not cancelled
    existing = frappe.db.get_value(
        "Re Exam Registration",
        {
            "student":    student_name,
            "exam_plan":  exam_plan,
            "course":     course,
            "status":     ["!=", "Cancelled"],
        },
        ["name", "payment_status"],
        as_dict=True,
    )
    if existing:
        if existing.payment_status in ("Paid", "Captured"):
            frappe.throw(_("You have already paid for this re-examination."))
        return {"status": "already_registered", "registration_name": existing.name}

    fee_amount = flt(setting.get("re_exam_fee") or 0)
    course_offering = frappe.db.get_value(
        "Course Schema Assignment", {"exam_plan": exam_plan, "course": course}, "course_offering"
    )
    if not course_offering:
        frappe.throw(_("No Course Offering found for this course/exam plan. Contact administration."))
    doc = frappe.new_doc("Re Exam Registration")
    doc.student        = student_name
    doc.exam_plan      = exam_plan
    doc.course         = course
    doc.course_offering = course_offering
    doc.re_exam_fee    = fee_amount
    doc.status         = "Registered"
    doc.payment_status = "Pending"
    doc.remarks        = "Cash payment — awaiting admin confirmation at counter."
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "ok", "registration_name": doc.name}


@frappe.whitelist()
def get_invoice_summary(invoice_name):
    """Return a lightweight summary of a student's own invoice.
    Used to refresh the fee card after a payment without a full page reload.
    """
    student_name = _require_student()
    inv          = _get_owned_invoice(invoice_name, student_name)

    return {
        "outstanding_amount":    flt(inv.outstanding_amount),
        "paid_amount":           flt(inv.paid_amount),
        "final_payable_amount":  flt(inv.final_payable_amount),
        "status":                inv.status,
        "formatted_outstanding": "₹{:,.0f}".format(flt(inv.outstanding_amount)),
        "formatted_paid":        "₹{:,.0f}".format(flt(inv.paid_amount)),
    }


@frappe.whitelist()
def mark_demand_payment_failed(fee_demand_names, integration_request=None,
                               payment_id=None, error_code=None, error_description=None,
                               re_exam_registrations=None):
    """Record a 'Payment Failed' audit log entry for one or more Fee Demands.

    Called from the browser ``payment.failed`` Razorpay callback for student
    bulk-demand payments.  Mirrors mark_payment_failed for invoices.

    * Updates the Integration Request to Failed (best-effort).
    * Writes a Payment Failed log row for every demand in the list.
    * Never overwrites a Paid / Waived demand status.
    * Idempotent — safe to call more than once.
    """
    import json as _j
    student_name = _require_student()

    try:
        names = _j.loads(fee_demand_names) if isinstance(fee_demand_names, str) else list(fee_demand_names)
    except Exception:
        names = [fee_demand_names] if fee_demand_names else []

    try:
        rex_names = _parse_name_list(re_exam_registrations)
        _reset_re_exams(rex_names, student_name, "Payment Failed")
    except Exception:
        rex_names = []
        frappe.log_error(frappe.get_traceback(), "mark_demand_payment_failed: re-exam status (non-fatal)")

    if not names:
        if rex_names:
            frappe.db.commit()
        return {"status": "logged" if rex_names else "noop", "demands": names}

    pid      = (payment_id or "").strip()
    err_code = (error_code or "N/A")
    err_desc = (error_description or "")[:200]

    if integration_request:
        try:
            ir_status = frappe.db.get_value("Integration Request", integration_request, "status") or ""
            if ir_status != "Completed":
                upd = {"status": "Failed"}
                if pid:
                    upd["payment_id"] = pid
                frappe.db.set_value("Integration Request", integration_request, upd,
                                    update_modified=False)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "mark_demand_payment_failed: IR update")

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    for n in names:
        d = frappe.db.get_value(
            "Fee Demand",
            {"name": n, "student": student_name},
            ["name", "fee_component", "description", "status", "outstanding_amount"],
            as_dict=True,
        )
        if not d or d.status in ("Paid", "Waived"):
            continue
        _append_payment_log(
            student_name,
            "Payment Failed",
            fee_demand=n,
            payment_mode="Online Payment",
            paid_by_role="Student",
            razorpay_payment_id=pid,
            from_status=d.status,
            to_status="Payment Failed",
            error_message=f"Code: {err_code} — {err_desc}",
            remarks=f"Razorpay payment.failed event for demand {n}",
        )

    frappe.db.commit()
    return {"status": "logged", "demands": names}


@frappe.whitelist()
def parent_cancel_bulk_demand_payment(fee_demand_names, student_name, integration_request=None):
    """Log a 'Payment Cancelled' entry when a parent dismisses the Razorpay modal.

    The JS _failedAlready flag ensures this is only called for true user cancels —
    not for bank/gateway declines (those go through parent_mark_demand_payment_failed).
    """
    import json as _j
    _require_parent_for_student(student_name)

    try:
        names = _j.loads(fee_demand_names) if isinstance(fee_demand_names, str) else list(fee_demand_names)
    except Exception:
        return {"status": "noop"}

    if integration_request:
        try:
            frappe.db.set_value(
                "Integration Request", integration_request, "status", "Cancelled",
                update_modified=False,
            )
        except Exception:
            pass

    _parent_full_name = (
        frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    )

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    for dem_name in names:
        _append_payment_log(
            student_name,
            "Payment Cancelled",
            fee_demand=dem_name,
            payment_mode="Online Payment",
            paid_by_role="Parent",
            paid_by_name=_parent_full_name,
            remarks=f"Parent dismissed bulk-payment modal for {len(names)} demand(s): {', '.join(names[:5])}",
        )
    frappe.db.commit()
    return {"status": "cancelled"}


@frappe.whitelist()
def parent_mark_demand_payment_failed(fee_demand_names, student_name,
                                      integration_request=None,
                                      payment_id=None, error_code=None, error_description=None):
    """Record a 'Payment Failed' audit log for one or more Fee Demands — parent flow.

    * Validates caller is a parent of student_name.
    * Updates Integration Request to Failed (best-effort).
    * Writes Payment Failed log rows with paid_by_role='Parent'.
    * Never overwrites a Paid / Waived demand.
    * Idempotent.
    """
    import json as _j
    _require_parent_for_student(student_name)

    try:
        names = _j.loads(fee_demand_names) if isinstance(fee_demand_names, str) else list(fee_demand_names)
    except Exception:
        names = [fee_demand_names] if fee_demand_names else []

    if not names:
        return {"status": "noop"}

    pid      = (payment_id or "").strip()
    err_code = (error_code or "N/A")
    err_desc = (error_description or "")[:200]

    if integration_request:
        try:
            ir_status = frappe.db.get_value("Integration Request", integration_request, "status") or ""
            if ir_status != "Completed":
                upd = {"status": "Failed"}
                if pid:
                    upd["payment_id"] = pid
                frappe.db.set_value("Integration Request", integration_request, upd,
                                    update_modified=False)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "parent_mark_demand_payment_failed: IR update")

    _parent_full_name = (
        frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    )

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    for n in names:
        d = frappe.db.get_value(
            "Fee Demand",
            {"name": n, "student": student_name},
            ["name", "fee_component", "description", "status", "outstanding_amount"],
            as_dict=True,
        )
        if not d or d.status in ("Paid", "Waived"):
            continue
        _append_payment_log(
            student_name,
            "Payment Failed",
            fee_demand=n,
            payment_mode="Online Payment",
            paid_by_role="Parent",
            paid_by_name=_parent_full_name,
            razorpay_payment_id=pid,
            from_status=d.status,
            to_status="Payment Failed",
            error_message=f"Code: {err_code} — {err_desc}",
            remarks=f"Parent payment.failed event for demand {n} — payer: {_parent_full_name}",
        )

    frappe.db.commit()
    return {"status": "logged", "demands": names}


# ── Parent Portal payment endpoints ───────────────────────────────────────
# These mirror the student endpoints above but validate that the logged-in
# user is a parent/guardian of the target student instead of the student
# themselves. They live in this module (not a separate file) so they share
# the module's whitelist registration and are always available.


def _require_parent_for_student(student_name):
    """Validate caller is a logged-in parent of *student_name*.
    Returns student_name on success, raises PermissionError otherwise.
    """
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to continue."), frappe.AuthenticationError)

    user = frappe.session.user
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


@frappe.whitelist()
def parent_create_payment_order(invoice_name, student_name):
    """Create a Razorpay order for a parent paying a student's Fee Invoice.

    Security:
    * Caller must be a non-guest parent linked to student_name.
    * Invoice must belong to student_name (IDOR guard).
    * Amount sourced from server-side outstanding_amount only.
    """
    _require_parent_for_student(student_name)
    inv = _get_owned_invoice(invoice_name, student_name)

    if inv.status in ("Paid", "Cancelled"):
        frappe.throw(_("This invoice is already {0}.").format(inv.status))
    if flt(inv.outstanding_amount) <= 0:
        frappe.throw(_("There is no outstanding amount on this invoice."))

    frappe.db.set_value(
        "Fee Invoice", invoice_name, "payment_status", "Payment Initiated",
        update_modified=False,
    )
    frappe.db.commit()

    controller = _get_razorpay_controller()

    sm = frappe.db.get_value(
        "Student Master", student_name,
        ["first_name", "last_name", "phone"], as_dict=True,
    ) or {}
    student_full = " ".join(filter(None, [sm.get("first_name"), sm.get("last_name")])) or inv.student_name

    parent_doc = frappe.db.get_value(
        "User", frappe.session.user, ["full_name", "email"], as_dict=True
    ) or {}
    payer_name  = parent_doc.get("full_name") or frappe.session.user
    payer_email = parent_doc.get("email") or frappe.session.user
    payer_phone = sm.get("phone") or ""

    outstanding = flt(inv.outstanding_amount)
    try:
        order = controller.create_order(
            amount=outstanding,
            currency="INR",
            title=_("Fee Payment – {0}").format(inv.name),
            description=_("Fee payment for {0} (by parent)").format(student_full),
            reference_doctype="Fee Invoice",
            reference_docname=inv.name,
            payer_email=payer_email,
            payer_name=payer_name,
            receipt=inv.name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "parent_create_payment_order")
        frappe.throw(
            _("Could not create payment order. Please try again or contact support."),
            frappe.ValidationError,
        )

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


@frappe.whitelist()
def parent_confirm_fee_payment(invoice_name, student_name, integration_request,
                               razorpay_payment_id, razorpay_order_id, razorpay_signature):
    """Verify Razorpay signature and record fee payment made by a parent.

    Idempotent — safe to call more than once.
    Creates a Fee Payment that updates Fee Invoice (status, paid_amount,
    outstanding_amount), which is immediately visible in student portal and
    Frappe desk.
    """
    _require_parent_for_student(student_name)
    inv = _get_owned_invoice(invoice_name, student_name)

    if inv.status == "Paid" or flt(inv.outstanding_amount) <= 0:
        return {
            "status":                "already_paid",
            "invoice_status":        inv.status,
            "paid_amount":           flt(inv.paid_amount),
            "outstanding_amount":    0.0,
            "formatted_paid":        "₹{:,.0f}".format(flt(inv.paid_amount)),
            "formatted_outstanding": "₹0",
        }

    # Verify Razorpay HMAC-SHA256 signature locally
    try:
        rzp = frappe.get_doc("Razorpay Settings")
        secret = rzp.get_password(fieldname="api_secret", raise_exception=False) or ""
        if not secret:
            frappe.throw(_("Payment gateway is not configured."), frappe.ValidationError)

        import hashlib as _hashlib
        import hmac as _hmac_mod
        message  = (razorpay_order_id + "|" + razorpay_payment_id).encode("utf-8")
        expected = _hmac_mod.new(secret.encode("utf-8"), message, _hashlib.sha256).hexdigest()
        if not _hmac_mod.compare_digest(expected, razorpay_signature):
            frappe.throw(_("Payment signature verification failed."), frappe.PermissionError)
    except (frappe.PermissionError, frappe.ValidationError):
        raise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "parent_confirm_fee_payment: sig check")
        frappe.throw(_("Could not verify payment. Please contact the Bursar's Office."))

    # Update Integration Request (best-effort)
    try:
        import json as _json
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
            "parent_confirm_fee_payment: IR update (non-fatal)",
        )

    # Idempotently create Fee Payment
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
                "remarks":          "Paid by parent via Parent Portal",
            })
            fp.insert(ignore_permissions=True)
            fp.submit()
            frappe.db.commit()

    frappe.db.set_value(
        "Fee Invoice", invoice_name, "payment_status", "Captured",
        update_modified=False,
    )
    frappe.db.commit()

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
def parent_sync_payment_status(invoice_name, student_name,
                               integration_request=None, payment_id=None):
    """Sync payment status from Razorpay after a failure or modal dismissal."""
    _require_parent_for_student(student_name)
    _get_owned_invoice(invoice_name, student_name)  # IDOR guard

    pid = payment_id or ""
    if not pid and integration_request:
        pid = frappe.db.get_value("Integration Request", integration_request, "payment_id") or ""

    if not pid:
        return {"status": "no_payment", "rzp_status": None}

    details = _fetch_razorpay_payment_details(pid)
    if not details:
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
def parent_get_invoice_summary(invoice_name, student_name):
    """Lightweight invoice summary for refreshing a parent-portal fee card."""
    _require_parent_for_student(student_name)
    inv = _get_owned_invoice(invoice_name, student_name)

    return {
        "outstanding_amount":    max(flt(inv.outstanding_amount), 0),
        "paid_amount":           flt(inv.paid_amount),
        "final_payable_amount":  flt(inv.final_payable_amount),
        "status":                inv.status,
        "formatted_outstanding": "₹{:,.0f}".format(max(flt(inv.outstanding_amount), 0)),
        "formatted_paid":        "₹{:,.0f}".format(flt(inv.paid_amount)),
    }


@frappe.whitelist()
def parent_create_demand_payment_order(fee_demand_name, student_name):
    """Create a Razorpay order for a parent paying a single Fee Demand.

    Security:
    * Caller must be a non-guest parent linked to student_name.
    * Demand must belong to student_name (IDOR guard).
    * Amount sourced server-side only.
    """
    _require_parent_for_student(student_name)

    demand = frappe.db.get_value(
        "Fee Demand",
        {"name": fee_demand_name, "student": student_name},
        ["name", "student", "fee_component", "description", "status",
         "outstanding_amount", "net_payable", "demand_type"],
        as_dict=True,
    )
    if not demand:
        frappe.throw(
            _("Fee Demand not found or access denied."),
            frappe.PermissionError,
        )

    if demand.status in ("Paid", "Waived", "Cancelled"):
        frappe.throw(_("This demand is already {0}.").format(demand.status))

    outstanding = flt(demand.outstanding_amount)
    if outstanding <= 0:
        frappe.throw(_("There is no outstanding amount on this demand."))

    sm = frappe.db.get_value(
        "Student Master", student_name,
        ["first_name", "last_name", "phone"], as_dict=True,
    ) or {}
    student_full = " ".join(filter(None, [sm.get("first_name"), sm.get("last_name")])) or student_name

    parent_doc = frappe.db.get_value(
        "User", frappe.session.user, ["full_name", "email"], as_dict=True,
    ) or {}
    payer_name  = parent_doc.get("full_name") or frappe.session.user
    payer_email = parent_doc.get("email") or frappe.session.user
    payer_phone = sm.get("phone") or ""

    component  = demand.fee_component or demand.description or "Fee"
    controller = _get_razorpay_controller()

    try:
        order = controller.create_order(
            amount=outstanding,
            currency="INR",
            title=_("Fee Payment – {0}").format(component),
            description=_("Fee demand payment for {0} (by parent)").format(student_full),
            reference_doctype="Fee Demand",
            reference_docname=fee_demand_name,
            payer_email=payer_email,
            payer_name=payer_name,
            receipt=fee_demand_name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "parent_create_demand_payment_order")
        frappe.throw(
            _("Could not create payment order. Please try again or contact support."),
            frappe.ValidationError,
        )

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    _append_payment_log(
        student_name,
        "Payment Initiated",
        amount=outstanding,
        fee_demand=fee_demand_name,
        payment_mode="Online Payment",
        paid_by_role="Parent",
        paid_by_name=payer_name,
        from_status=demand.status,
        to_status="Payment Initiated",
        remarks=f"Razorpay order created for Fee Demand {fee_demand_name} by parent — {component}",
    )

    return {
        "order_id":            order.get("id"),
        "integration_request": order.get("integration_request"),
        "amount":              order.get("amount"),
        "currency":            order.get("currency", "INR"),
        "key_id":              controller.api_key,
        "payer_name":          payer_name,
        "payer_email":         payer_email,
        "payer_phone":         payer_phone,
        "fee_demand_name":     fee_demand_name,
        "component":           component,
        "outstanding":         outstanding,
    }


@frappe.whitelist()
def parent_confirm_demand_payment(fee_demand_name, student_name, integration_request,
                                  razorpay_payment_id, razorpay_order_id, razorpay_signature):
    """Verify Razorpay signature and record a parent's payment against a Fee Demand."""
    _require_parent_for_student(student_name)

    demand = frappe.db.get_value(
        "Fee Demand",
        {"name": fee_demand_name, "student": student_name},
        ["name", "fee_component", "description", "status", "outstanding_amount"],
        as_dict=True,
    )
    if not demand:
        frappe.throw(_("Fee Demand not found or access denied."), frappe.PermissionError)

    if demand.status == "Paid" and flt(demand.outstanding_amount) <= 0:
        return {"status": "already_paid"}

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
        frappe.log_error(frappe.get_traceback(), "parent_confirm_demand_payment: sig check")
        frappe.throw(_("Could not verify payment. Please contact the Bursar's Office."))

    try:
        from payments.payment_gateways.doctype.razorpay_settings.razorpay_settings import order_payment_success
        order_payment_success(
            integration_request,
            _json.dumps({
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_order_id":   razorpay_order_id,
                "razorpay_signature":  razorpay_signature,
            }),
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "parent_confirm_demand_payment: IR update (non-fatal)")

    existing_fp = frappe.db.get_value(
        "Fee Payment",
        {"reference_number": razorpay_payment_id, "student": student_name, "docstatus": 1},
        "name",
    )
    if existing_fp:
        return {"status": "already_paid"}

    outstanding = flt(demand.outstanding_amount)
    fp = frappe.get_doc({
        "doctype":         "Fee Payment",
        "student":         student_name,
        "payment_date":    today(),
        "payment_mode":    "Online Payment",
        "amount":          outstanding,
        "reference_number": razorpay_payment_id,
        "remarks":         f"Parent payment — Razorpay order {razorpay_order_id} — demand {fee_demand_name}",
        "payment_demands": [{
            "fee_demand":         fee_demand_name,
            "demand_description": demand.fee_component or demand.description or "",
            "outstanding_amount": outstanding,
            "amount_allocated":   outstanding,
        }],
    })
    fp.insert(ignore_permissions=True)
    fp.submit()
    frappe.db.commit()

    _parent_full_name = (
        frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    )

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    _append_payment_log(
        student_name,
        "Captured",
        amount=outstanding,
        fee_demand=fee_demand_name,
        payment_mode="Online Payment",
        paid_by_role="Parent",
        paid_by_name=_parent_full_name,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_order_id=razorpay_order_id,
        webhook_status="Not Applicable",
        remarks=f"Parent payment captured — demand {fee_demand_name} — Razorpay {razorpay_order_id}",
    )

    return {"status": "success", "total_paid": outstanding}


@frappe.whitelist()
def parent_create_bulk_demand_payment_order(fee_demand_names, student_name):
    """Create a single Razorpay order covering multiple Fee Demands for a parent.

    Security:
    * Caller must be a non-guest parent linked to student_name.
    * Every demand must belong to student_name (IDOR guard).
    * Total amount computed server-side only.
    """
    import json as _j
    _require_parent_for_student(student_name)

    try:
        names = _j.loads(fee_demand_names) if isinstance(fee_demand_names, str) else list(fee_demand_names)
    except Exception:
        frappe.throw(_("Invalid demand list."), frappe.ValidationError)

    if not names:
        frappe.throw(_("No fee demands provided."), frappe.ValidationError)
    if len(names) > 50:
        frappe.throw(_("Too many demands in a single payment (max 50)."), frappe.ValidationError)

    demands = []
    total = 0.0
    for n in names:
        d = frappe.db.get_value(
            "Fee Demand",
            {"name": n, "student": student_name},
            ["name", "fee_component", "description", "status", "outstanding_amount", "net_payable"],
            as_dict=True,
        )
        if not d:
            frappe.throw(_("Demand {0} not found or access denied.").format(n), frappe.PermissionError)
        if d.status in ("Paid", "Waived", "Cancelled"):
            frappe.throw(_("Demand {0} is already {1}.").format(n, d.status), frappe.ValidationError)
        out = flt(d.outstanding_amount)
        if out <= 0:
            frappe.throw(_("Demand {0} has no outstanding amount.").format(n), frappe.ValidationError)
        total += out
        demands.append(d)

    if total <= 0:
        frappe.throw(_("Total outstanding amount is zero."), frappe.ValidationError)

    sm = frappe.db.get_value(
        "Student Master", student_name,
        ["first_name", "last_name", "phone"], as_dict=True,
    ) or {}
    student_full = " ".join(filter(None, [sm.get("first_name"), sm.get("last_name")])) or student_name

    parent_doc = frappe.db.get_value(
        "User", frappe.session.user, ["full_name", "email"], as_dict=True,
    ) or {}
    payer_name  = parent_doc.get("full_name") or frappe.session.user
    payer_email = parent_doc.get("email") or frappe.session.user
    payer_phone = sm.get("phone") or ""

    components = ", ".join(d.fee_component or d.description or "Fee" for d in demands[:3])
    if len(demands) > 3:
        components += f" +{len(demands) - 3} more"

    controller  = _get_razorpay_controller()
    receipt_ref = demands[0].name

    try:
        order = controller.create_order(
            amount=total,
            currency="INR",
            title=_("Fee Payment – {0} item(s)").format(len(demands)),
            description=_("Fee payment for {0} (by parent)").format(student_full),
            reference_doctype="Fee Demand",
            reference_docname=receipt_ref,
            payer_email=payer_email,
            payer_name=payer_name,
            receipt=receipt_ref,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "parent_create_bulk_demand_payment_order")
        frappe.throw(
            _("Could not create payment order. Please try again or contact support."),
            frappe.ValidationError,
        )

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    for d in demands:
        _append_payment_log(
            student_name,
            "Payment Initiated",
            amount=flt(d.outstanding_amount),
            fee_demand=d.name,
            payment_mode="Online Payment",
            paid_by_role="Parent",
            paid_by_name=payer_name,
            remarks=f"Bulk parent payment order for {len(demands)} demands: {', '.join(x.name for x in demands)}",
        )

    return {
        "order_id":            order.get("id"),
        "integration_request": order.get("integration_request"),
        "amount":              order.get("amount"),
        "currency":            order.get("currency", "INR"),
        "key_id":              controller.api_key,
        "payer_name":          payer_name,
        "payer_email":         payer_email,
        "payer_phone":         payer_phone,
        "total":               total,
        "components":          components,
        "demand_names":        [d.name for d in demands],
    }


@frappe.whitelist()
def parent_confirm_bulk_demand_payment(fee_demand_names, student_name, integration_request,
                                       razorpay_payment_id, razorpay_order_id, razorpay_signature):
    """Verify HMAC signature and record a single Fee Payment covering all demands (parent)."""
    import json as _j
    _require_parent_for_student(student_name)

    try:
        names = _j.loads(fee_demand_names) if isinstance(fee_demand_names, str) else list(fee_demand_names)
    except Exception:
        frappe.throw(_("Invalid demand list."), frappe.ValidationError)

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
        frappe.log_error(frappe.get_traceback(), "parent_confirm_bulk_demand_payment: sig check")
        frappe.throw(_("Could not verify payment. Please contact the Bursar's Office."))

    try:
        from payments.payment_gateways.doctype.razorpay_settings.razorpay_settings import order_payment_success
        order_payment_success(
            integration_request,
            _json.dumps({
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_order_id":   razorpay_order_id,
                "razorpay_signature":  razorpay_signature,
            }),
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "parent_confirm_bulk_demand_payment: IR update (non-fatal)")

    existing_fp = frappe.db.get_value(
        "Fee Payment",
        {"reference_number": razorpay_payment_id, "student": student_name, "docstatus": 1},
        "name",
    )
    if existing_fp:
        return {"status": "already_paid"}

    demand_rows = []
    total = 0.0
    for n in names:
        d = frappe.db.get_value(
            "Fee Demand",
            {"name": n, "student": student_name},
            ["name", "fee_component", "description", "status", "outstanding_amount"],
            as_dict=True,
        )
        if not d or d.status in ("Paid", "Waived", "Cancelled"):
            continue
        out = flt(d.outstanding_amount)
        if out <= 0:
            continue
        demand_rows.append({
            "fee_demand":         n,
            "demand_description": d.fee_component or d.description or "",
            "outstanding_amount": out,
            "amount_allocated":   out,
        })
        total += out

    if not demand_rows:
        return {"status": "already_paid"}

    fp = frappe.get_doc({
        "doctype":          "Fee Payment",
        "student":          student_name,
        "payment_date":     today(),
        "payment_mode":     "Online Payment",
        "amount":           total,
        "reference_number": razorpay_payment_id,
        "remarks":          f"Parent bulk payment — Razorpay order {razorpay_order_id} — {len(demand_rows)} demands",
        "payment_demands":  demand_rows,
    })
    fp.insert(ignore_permissions=True)
    fp.submit()
    frappe.db.commit()

    _parent_full_name = (
        frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    )

    from slcm.slcm.doctype.student_master.student_master import _append_payment_log
    for row in demand_rows:
        _append_payment_log(
            student_name,
            "Captured",
            amount=flt(row["amount_allocated"]),
            fee_demand=row["fee_demand"],
            payment_mode="Online Payment",
            paid_by_role="Parent",
            paid_by_name=_parent_full_name,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            webhook_status="Not Applicable",
            remarks=f"Parent bulk payment captured — {len(demand_rows)} demands — Razorpay {razorpay_order_id}",
        )

    return {
        "status":           "success",
        "demands_paid":     len(demand_rows),
        "total_paid":       total,
        "formatted_total":  "₹{:,.0f}".format(total),
    }
