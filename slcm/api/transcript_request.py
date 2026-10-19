"""
Transcript Request API
======================
Portal-facing endpoints for the student Transcript Request workflow.

Payment status model
--------------------
Two separate fields track payment state:

  payment_status          – business/UX status shown to students and admins
  razorpay_payment_status – raw Razorpay gateway status, never modified by
                             business logic (only updated by gateway events)

Transitions
-----------
  Student clicks Pay            → razorpay: "created"    | payment: "Payment Initiated"
  Razorpay order created (API)  → razorpay: "created"    | payment: "Payment Initiated"
  Student dismisses checkout    → razorpay: "cancelled"  | payment: "Payment Cancelled"
  Gateway auth pending          → razorpay: "authorized" | payment: "Authorized"
  Signature verified + capture  → razorpay: "captured"   | payment: "Paid"
  Signature verification fails  → razorpay: "failed"     | payment: "Payment Failed"
  Refund processed              → razorpay: "refunded"   | payment: "Refunded"

Workflow
--------
1. Student opens portal → get_fee_preview() shows cost
2. Student submits form → create_request() creates Transcript Request doc
3. Student clicks Pay  → initiate_payment() sets "Payment Initiated", creates
                          Payment Request + Razorpay order, returns checkout data
4. Student dismisses   → cancel_payment_attempt() sets "Payment Cancelled"
5. Razorpay success    → confirm_payment() verifies HMAC signature:
                          • sets razorpay: "captured", payment: "Paid"
                          • fires auto-approval / transcript generation
6. Razorpay failure    → record_payment_failure() sets "Payment Failed"
7. Admin approves via desk → approve_request() in management page py
8. Student downloads from portal

Security
--------
* All endpoints require a valid Student session (guest → 403).
* Students can only access their own Transcript Request records (IDOR guard).
* Payment amounts are always sourced server-side; client cannot influence the charge.
"""

import json as _json

import frappe
from frappe import _
from frappe.utils import today, now_datetime


# ── Razorpay gateway status → business payment_status map ─────────────────────
# Mirrors GATEWAY_TO_SYSTEM_STATUS in slcm/payment.py
_RZ_TO_PAYMENT = {
    "created":    "Payment Initiated",
    "authorized": "Authorized",
    "captured":   "Paid",
    "failed":     "Payment Failed",
    "refunded":   "Refunded",
    "cancelled":  "Payment Cancelled",
}


# ── Internal helpers ───────────────────────────────────────────────────────────

def _require_student():
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to continue."), frappe.AuthenticationError)
    user = frappe.session.user
    for field in ("user", "email", "official_email_id"):
        name = frappe.db.get_value("Student Master", {field: user}, "name")
        if name:
            return name
    frappe.throw(_("No student record found for your account."), frappe.PermissionError)


def _get_settings():
    if frappe.db.exists("DocType", "Transcript Fee Settings"):
        return frappe.get_doc("Transcript Fee Settings", "Transcript Fee Settings")
    return frappe._dict({
        "enable_payment": 0,
        "allow_interim": 1, "allow_final": 1, "allow_marksheet": 1,
        "allow_duplicate": 1, "allow_digital": 1,
        "interim_fee": 300, "final_fee": 1000, "marksheet_fee": 500,
        "duplicate_fee": 500, "digital_fee": 150,
        "urgent_fee": 0, "tax_percentage": 0, "free_requests_per_student": 0,
        "auto_approve_interim": 1, "auto_approve_final": 0,
        "notify_on_submission": None, "notify_on_payment": None,
        "notify_on_approval": None, "notify_on_rejection": None,
        "notify_on_ready": None,
        "assignment_rules": [],
    })


def _fee_for_type(settings, transcript_type):
    return {
        "Interim Transcript":     settings.interim_fee or 0,
        "Final Transcript":       settings.final_fee or 0,
        "Consolidated Marksheet": settings.marksheet_fee or 0,
        "Duplicate Transcript":   settings.duplicate_fee or 0,
        "Digital Transcript":     settings.digital_fee or 0,
    }.get(transcript_type, settings.interim_fee or 0)


def _owned_request(request_name, student_name):
    doc = frappe.db.get_value(
        "Transcript Request",
        {"name": request_name, "student": student_name},
        [
            "name", "student", "status",
            "payment_status", "razorpay_payment_status",
            "fee_amount", "payment_required", "transcript_type", "num_copies",
            "razorpay_order_id", "transcript_doc",
        ],
        as_dict=True,
    )
    if not doc:
        frappe.throw(_("Request not found or you do not have permission."), frappe.PermissionError)
    return doc


def _set_status(request_name, updates):
    """
    Write status/payment_status fields via a raw db.set_value (as this whole
    module does throughout — Transcript Request rows change fast during
    checkout and don't need a full Document.save() round-trip), then sync
    the change to a linked Helpdesk ticket if one exists.

    Document.on_update() is NOT called by db.set_value, so every status
    mutation in this file must go through here rather than calling
    frappe.db.set_value directly — otherwise a ticket-linked request would
    silently stop reflecting status in the Helpdesk queue.
    """
    frappe.db.set_value("Transcript Request", request_name, updates)
    _sync_helpdesk_ticket(request_name)


def _sync_helpdesk_ticket(request_name):
    helpdesk_ticket = frappe.db.get_value("Transcript Request", request_name, "helpdesk_ticket")
    if not helpdesk_ticket:
        return
    try:
        from helpdesk.api.nls_student import sync_transcript_status_to_ticket
        doc = frappe.get_doc("Transcript Request", request_name)
        sync_transcript_status_to_ticket(doc)
    except ImportError:
        pass
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Transcript Request → HD Ticket sync failed")


def _set_payment_fields(request_name, razorpay_status, gateway_response=None, extra=None):
    """
    Update both payment status fields atomically from a Razorpay gateway status.
    extra – dict of additional fields to set in the same call.
    """
    business_status = _RZ_TO_PAYMENT.get(razorpay_status, "Payment Initiated")
    updates = {
        "razorpay_payment_status": razorpay_status,
        "payment_status":          business_status,
    }
    if gateway_response is not None:
        updates["gateway_response"] = (
            _json.dumps(gateway_response, indent=2)
            if isinstance(gateway_response, dict) else gateway_response
        )
    if extra:
        updates.update(extra)
    _set_status(request_name, updates)


def _get_student_email(student_name):
    fields = frappe.db.get_value(
        "Student Master", student_name,
        ["email", "personal_email", "official_email_id"],
        as_dict=True,
    )
    if not fields:
        return None
    return fields.official_email_id or fields.email or fields.personal_email


def _get_student_full_name(student_name):
    row = frappe.db.get_value("Student Master", student_name, ["first_name", "last_name"], as_dict=True)
    if not row:
        return student_name
    return f"{row.first_name or ''} {row.last_name or ''}".strip()


def _send_email(student_name, subject, message):
    """Send a plain-text/HTML email (fallback when no Email Template configured)."""
    try:
        to_email = _get_student_email(student_name)
        if not to_email:
            return
        frappe.sendmail(recipients=[to_email], subject=subject, message=message)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Transcript email send error")


def _send_template_email(student_name, template_name, context=None):
    """
    Send using a Frappe Email Template.
    template_name – the name of the Email Template doc (from settings).
    context       – dict of variables for Jinja rendering in the template.
    Returns True if sent, False if template_name is blank/None (skip).
    """
    if not template_name:
        return False
    try:
        to_email = _get_student_email(student_name)
        if not to_email:
            return False
        template = frappe.get_doc("Email Template", template_name)
        ctx = context or {}
        subject = frappe.render_template(template.subject, ctx)
        raw = (template.response_html if template.use_html and template.response_html else template.response) or ""
        message = frappe.render_template(raw, ctx)
        frappe.sendmail(recipients=[to_email], subject=subject, message=message)
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Transcript template email send error")
        return False


# ── Public API ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_fee_preview(transcript_type, num_copies=1, urgency="Normal"):
    """Return fee breakdown for the given transcript type and copy count."""
    _require_student()
    settings = _get_settings()
    num_copies = max(int(num_copies or 1), 1)
    base_fee = _fee_for_type(settings, transcript_type) * num_copies
    urgent_surcharge = float(settings.urgent_fee or 0) if urgency == "Urgent" else 0
    subtotal = base_fee + urgent_surcharge
    tax_amount = round(subtotal * float(settings.tax_percentage or 0) / 100, 2)
    return {
        "payment_required": bool(settings.enable_payment),
        "base_fee": base_fee,
        "urgent_surcharge": urgent_surcharge,
        "tax_amount": tax_amount,
        "total": subtotal + tax_amount,
        "currency": settings.currency or "INR",
        "transcript_type": transcript_type,
        "num_copies": num_copies,
    }


@frappe.whitelist()
def create_request(transcript_type, num_copies=1, purpose="",
                   delivery_mode="Soft Copy (PDF)", urgency="Normal"):
    """Create a new Transcript Request for the logged-in student."""
    return _create_request(
        transcript_type, num_copies=num_copies, purpose=purpose,
        delivery_mode=delivery_mode, urgency=urgency,
    )


def _create_request(transcript_type, num_copies=1, purpose="",
                    delivery_mode="Soft Copy (PDF)", urgency="Normal",
                    helpdesk_ticket=None):
    """
    Shared implementation behind create_request(). helpdesk_ticket links the
    resulting doc back to the HD Ticket it was raised from (Helpdesk
    "Transcript Request" ticket type), so status updates can sync back.
    """
    student_name = _require_student()

    valid_types = ["Interim Transcript", "Final Transcript", "Consolidated Marksheet",
                   "Duplicate Transcript", "Digital Transcript"]
    if transcript_type not in valid_types:
        frappe.throw(_("Invalid transcript type."))

    # Check if this type is enabled in settings
    settings = _get_settings()
    _allow_map = {
        "Interim Transcript":     getattr(settings, "allow_interim",    1),
        "Final Transcript":       getattr(settings, "allow_final",      1),
        "Consolidated Marksheet": getattr(settings, "allow_marksheet",  1),
        "Duplicate Transcript":   getattr(settings, "allow_duplicate",  1),
        "Digital Transcript":     getattr(settings, "allow_digital",    1),
    }
    if not _allow_map.get(transcript_type, 1):
        frappe.throw(_("{0} requests are currently not accepted. Please contact the Academic Office.").format(transcript_type))

    if transcript_type in ("Final Transcript", "Consolidated Marksheet"):
        if getattr(settings, "restrict_final_to_graduates", 0):
            acad_status = frappe.db.get_value("Student Master", student_name, "academic_status")
            if acad_status not in ("Graduated", "Programme Completed", "Completed"):
                frappe.throw(_(
                    "Final Transcript and Consolidated Marksheet are only issued after programme "
                    "completion. Your current academic status is '{0}'. "
                    "Please request an Interim Transcript instead, or contact the Academic Office."
                ).format(acad_status or "Unknown"))

    existing = frappe.db.get_value(
        "Transcript Request",
        {
            "student": student_name,
            "transcript_type": transcript_type,
            "status": ["in", ["Draft", "Payment Pending", "Submitted", "Under Review", "Approved"]],
        },
        "name",
    )
    if existing:
        frappe.throw(_(
            "You already have an open request ({0}) for {1}. "
            "Please wait for it to be processed before submitting a new one."
        ).format(existing, transcript_type))

    doc = frappe.get_doc({
        "doctype": "Transcript Request",
        "student": student_name,
        "transcript_type": transcript_type,
        "num_copies": max(int(num_copies or 1), 1),
        "purpose": (purpose or "").strip(),
        "delivery_mode": delivery_mode or "Soft Copy (PDF)",
        "urgency": urgency or "Normal",
        "requested_on": today(),
        "helpdesk_ticket": helpdesk_ticket or None,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    # settings already loaded above; use it for email
    ctx = {
        "student": student_name,
        "student_name": _get_student_full_name(student_name),
        "request_name": doc.name,
        "transcript_type": transcript_type, "status": doc.status,
        "fee_amount": doc.fee_amount or 0, "payment_required": doc.payment_required,
    }
    sent = _send_template_email(student_name, settings.notify_on_submission, ctx)
    if sent:
        frappe.db.set_value("Transcript Request", doc.name, "confirmation_email_sent", 1)

    return {
        "name": doc.name,
        "status": doc.status,
        "payment_required": bool(doc.payment_required),
        "fee_amount": doc.fee_amount or 0,
        "transcript_type": transcript_type,
        "num_copies": doc.num_copies,
    }


@frappe.whitelist()
def initiate_payment(request_name):
    """
    Called when the student clicks the Pay button.

    Creates a Razorpay order directly — no intermediate Payment Request doc needed.
    All payment data is stored on the Transcript Request itself.
    """
    student_name = _require_student()
    req = _owned_request(request_name, student_name)

    if not req.payment_required:
        frappe.throw(_("This request does not require payment."))
    if req.payment_status == "Paid":
        frappe.throw(_("Payment has already been completed for this request."))
    if req.status == "Cancelled":
        frappe.throw(_("This request has been cancelled."))

    # Mark "Payment Initiated" immediately so the portal shows the right state
    _set_payment_fields(request_name, "created")
    frappe.db.commit()

    # Get student email for Razorpay prefill
    student_fields = frappe.db.get_value(
        "Student Master", student_name,
        ["email", "official_email_id", "personal_email"],
        as_dict=True,
    )
    email_to = (
        (student_fields.official_email_id or student_fields.email or student_fields.personal_email)
        if student_fields else frappe.session.user
    )

    # Create Razorpay order directly — no Payment Request intermediary
    try:
        from payments.utils import get_payment_gateway_controller
        controller = get_payment_gateway_controller("Razorpay")

        # create_order() expects amount in RUPEES — it multiplies by 100 internally
        fee_rupees = float(req.fee_amount)
        order = controller.create_order(
            amount=fee_rupees,
            currency="INR",
            receipt=request_name,   # use Transcript Request name as receipt
        )
        razorpay_order_id = order.get("id")

        frappe.db.set_value("Transcript Request", request_name, {
            "razorpay_order_id": razorpay_order_id,
            "gateway_response":  _json.dumps(order, indent=2),
            "payment_failure_reason": "",
        })
        frappe.db.commit()

        rz_settings = frappe.get_doc("Razorpay Settings")
        return {
            "razorpay_order_id": razorpay_order_id,
            "razorpay_key":      rz_settings.api_key,
            "amount":            int(fee_rupees * 100),   # paise for Razorpay JS
            "currency":          "INR",
            "description":       f"Transcript Fee – {req.transcript_type}",
            "prefill":           {"email": email_to},
        }
    except Exception:
        # Roll back so the student can retry
        _set_payment_fields(
            request_name, "failed",
            extra={"payment_status": "Pending", "razorpay_payment_status": ""},
        )
        frappe.db.commit()
        frappe.log_error(frappe.get_traceback(), "Transcript payment order error")
        frappe.throw(_("Could not create payment order. Please try again or contact support."))


@frappe.whitelist()
def cancel_payment_attempt(request_name):
    """
    Called when the student dismisses the Razorpay checkout modal without paying.
    Sets razorpay_payment_status = "cancelled", payment_status = "Payment Cancelled".
    The request status stays "Payment Pending" so the student can try again.
    """
    student_name = _require_student()
    req = _owned_request(request_name, student_name)

    # Only act if currently in an initiated state (guard against double-call)
    if req.payment_status not in ("Payment Initiated", "Pending", "Payment Cancelled"):
        return {"success": True, "payment_status": req.payment_status}

    _set_payment_fields(request_name, "cancelled")
    frappe.db.commit()
    return {"success": True, "payment_status": "Payment Cancelled"}


@frappe.whitelist()
def confirm_payment(request_name, razorpay_payment_id,
                    razorpay_order_id, razorpay_signature):
    """
    Called after Razorpay checkout succeeds on the client side.

    1. Verifies HMAC-SHA256 signature (prevents spoofed callbacks).
    2. Sets razorpay_payment_status = "captured", payment_status = "Paid".
    3. Fires auto-approval / transcript generation if configured.
    """
    student_name = _require_student()
    req = _owned_request(request_name, student_name)

    if req.payment_status == "Paid":
        return {"success": True, "already_paid": True, "status": req.status}

    # ── Signature verification ─────────────────────────────────────────────────
    # Razorpay HMAC-SHA256: body = "order_id|payment_id", key = api_secret
    try:
        from payments.utils import get_payment_gateway_controller
        controller = get_payment_gateway_controller("Razorpay")
        api_secret = controller.get_password(fieldname="api_secret", raise_exception=False)
        body = f"{razorpay_order_id}|{razorpay_payment_id}"
        controller.verify_signature(body, razorpay_signature, api_secret)
    except Exception:
        _set_payment_fields(
            request_name, "failed",
            gateway_response={"payment_id": razorpay_payment_id, "error": "signature_mismatch"},
        )
        frappe.db.commit()
        frappe.throw(_(
            "Payment verification failed. Please contact support with your payment ID: {0}"
        ).format(razorpay_payment_id))

    # ── Mark Paid (captured) ───────────────────────────────────────────────────
    _set_payment_fields(
        request_name, "captured",
        gateway_response={"payment_id": razorpay_payment_id, "order_id": razorpay_order_id},
        extra={
            "payment_date":      now_datetime(),
            "payment_reference": razorpay_payment_id,
            "status":            "Submitted",
            "payment_failure_reason": "",
        },
    )
    frappe.db.commit()

    settings = _get_settings()
    _send_template_email(student_name, settings.notify_on_payment, {
        "student": student_name,
        "student_name": _get_student_full_name(student_name),
        "request_name": request_name,
        "transcript_type": req.transcript_type, "fee_amount": req.fee_amount or 0,
        "payment_id": razorpay_payment_id,
    })

    # ── Auto-approval ─────────────────────────────────────────────────────────
    new_status  = "Submitted"
    tr_doc_name = None
    auto_approve = (
        (req.transcript_type == "Interim Transcript" and settings.auto_approve_interim)
        or (req.transcript_type in (
                "Final Transcript", "Consolidated Marksheet",
                "Duplicate Transcript", "Digital Transcript",
            ) and settings.auto_approve_final)
    )
    if auto_approve:
        tr_doc_name = _do_generate_transcript(request_name, student_name, req.transcript_type)
        if tr_doc_name:
            new_status = "Generated"

    _set_status(request_name, {"status": new_status})
    frappe.db.commit()

    return {
        "success":       True,
        "status":        new_status,
        "payment_status": "Paid",
        "transcript_doc": tr_doc_name,
    }


@frappe.whitelist()
def record_payment_failure(request_name, error_description="", error_code="",
                            error_reason="", error_source="", error_step=""):
    """
    Called when Razorpay fires an explicit failure event on the client side
    (razorpay.on('payment.failed', ...)).
    Sets razorpay_payment_status = "failed", payment_status = "Payment Failed",
    and stores a human-readable reason in payment_failure_reason so admins can
    see why the payment failed without digging into the raw gateway JSON.
    Request status stays "Payment Pending" so the student can retry.
    """
    student_name = _require_student()
    req = _owned_request(request_name, student_name)

    if req.payment_status == "Paid":
        return {"success": True}  # already paid, ignore

    reason = error_description or "Payment failed at gateway"

    # Keep request status as "Payment Pending" – student can retry
    _set_payment_fields(
        request_name, "failed",
        gateway_response={
            "error_description": reason,
            "error_code":        error_code or "",
            "error_reason":      error_reason or "",
            "error_source":      error_source or "",
            "error_step":        error_step or "",
        },
        extra={
            "status": "Payment Pending",
            "payment_failure_reason": reason,
        },
    )
    frappe.db.commit()
    return {"success": True, "payment_status": "Payment Failed"}


@frappe.whitelist()
def get_my_requests():
    """Return all Transcript Requests for the logged-in student."""
    student_name = _require_student()
    requests = frappe.get_all(
        "Transcript Request",
        filters={"student": student_name},
        fields=[
            "name", "transcript_type", "num_copies", "status",
            "payment_status", "razorpay_payment_status",
            "fee_amount", "payment_required", "requested_on", "purpose",
            "delivery_mode", "urgency", "transcript_doc", "rejection_reason",
            "payment_date", "payment_reference", "reviewed_on",
        ],
        order_by="requested_on desc, creation desc",
        ignore_permissions=True,
    )
    for r in requests:
        r["download_url"] = ""
        if r.get("transcript_doc") and r.get("status") in ("Generated", "Delivered"):
            r["download_url"] = (
                f"/api/method/slcm.api.transcript_request.download_my_transcript"
                f"?request_name={frappe.utils.quote(r['name'])}"
            )
    return requests


@frappe.whitelist()
def get_unlinked_paid_request():
    """
    Returns the student's most recent Transcript Request left over from an
    interrupted Helpdesk pay-first attempt, if any — confirm_payment()
    succeeded (payment_status "Paid", status advanced to "Submitted") but
    the browser closed/reloaded/lost connection before the ticket-creation
    step that normally runs right after did.

    helpdesk_ticket is only ever set once a ticket actually claims the
    request (see create_transcript_request_on_ticket /
    _link_prepaid_transcript_request on the Helpdesk side), so "still
    unlinked" is what marks this as interrupted rather than completed.

    status is restricted to exactly "Submitted" — the one status
    confirm_payment() can leave an unlinked, Paid request in without
    auto-approval having already generated something. This deliberately
    excludes Generated/Delivered/Under Review/Approved/Rejected/Cancelled:
    those mean either auto-approval already produced a transcript for it,
    or an admin has since acted on it — a same-session interruption can't
    reach those states, so a request sitting there is an old, already
    fulfilled/handled record from a different flow (the student portal page
    predates helpdesk_ticket entirely) that must never be silently
    resurrected into an unrelated new ticket.

    Used by the Helpdesk New Ticket form to resume instead of re-charging:
    if this returns a request, the payment panel shows it as already paid
    and skips straight to letting the student fill in Subject/Description.
    """
    student_name = _require_student()
    row = frappe.db.get_value(
        "Transcript Request",
        {
            "student": student_name,
            "helpdesk_ticket": ["is", "not set"],
            "status": "Submitted",
            "payment_status": "Paid",
        },
        ["name", "transcript_type", "num_copies", "purpose", "delivery_mode",
         "fee_amount", "payment_required", "payment_reference"],
        as_dict=True,
        order_by="creation desc",
    )
    return row


@frappe.whitelist()
def cancel_request(request_name):
    """Allow student to cancel a Draft or Payment Pending request."""
    student_name = _require_student()
    req = _owned_request(request_name, student_name)
    if req.status not in ("Draft", "Payment Pending"):
        frappe.throw(_("Only Draft or Payment Pending requests can be cancelled."))
    _set_status(request_name, {"status": "Cancelled"})
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist()
def download_my_transcript(request_name):
    """
    Stream the Student Transcript PDF for the logged-in student.
    - Final Transcript → Compact format (two-column condensed layout)
    - All other types  → Standard year-based format

    Security: verifies the request belongs to the student and is in
    Generated/Delivered state before rendering the PDF.
    """
    student_name = _require_student()
    req = _owned_request(request_name, student_name)

    if req.status not in ("Generated", "Delivered"):
        frappe.throw(_("Transcript is not yet ready for download."))
    if not req.transcript_doc:
        frappe.throw(_("No transcript document found. Please contact the Academic Office."))
    if not frappe.db.exists("Student Transcript", req.transcript_doc):
        frappe.throw(_("Transcript document not found. Please contact the Academic Office."))

    from frappe.utils.pdf import get_pdf

    # Final Transcript → Compact two-column format
    if req.transcript_type == "Final Transcript":
        from slcm.slcm.page.transcript_management_page.transcript_management_page import (
            _get_compact_template_html,
        )
        from slcm.slcm.doctype.student_transcript.student_transcript import (
            get_compact_transcript_context,
        )
        ctx = get_compact_transcript_context(student_name)
        tr_doc = frappe.get_doc("Student Transcript", req.transcript_doc)
        html = frappe.render_template(
            _get_compact_template_html(),
            {
                "doc": tr_doc,
                "ctx": ctx,
                "get_compact_transcript_context": get_compact_transcript_context,
            },
        )
        student_info = ctx.get("student") or {}
        file_label = student_info.get("registration_id") or student_name
        filename = f"Final-Transcript-{file_label}.pdf"

    else:
        # All other types → standard year-based format
        from frappe.www.printview import get_rendered_template, get_print_format_doc
        tr_doc = frappe.get_doc("Student Transcript", req.transcript_doc)
        pf_doc = get_print_format_doc("Student Transcript", frappe.get_meta("Student Transcript"))
        try:
            frappe.flags.ignore_print_permissions = True
            html = get_rendered_template(doc=tr_doc, print_format=pf_doc, no_letterhead=True)
        finally:
            frappe.flags.ignore_print_permissions = False
        filename = f"Transcript-{req.transcript_doc}.pdf"

    pdf_content = get_pdf(html)
    frappe.local.response.filename    = filename
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type        = "pdf"


# ── Internal generation helper ─────────────────────────────────────────────────

def _do_generate_transcript(request_name, student_name, transcript_type):
    """Create a Student Transcript doc linked to this request. Returns doc name or None."""
    type_map = {
        "Interim Transcript":     "Interim",
        "Final Transcript":       "Final",
        "Consolidated Marksheet": "Consolidated Marksheet",
        "Duplicate Transcript":   "Duplicate",
        "Digital Transcript":     "Digital",
    }
    st_type = type_map.get(transcript_type, "Interim")
    try:
        existing = frappe.db.get_value(
            "Student Transcript",
            {"student": student_name, "transcript_request": request_name},
            "name",
        )
        if existing:
            frappe.db.set_value("Student Transcript", existing, {
                "status":          "Generated",
                "generation_date": today(),
                "generated_by":    frappe.session.user,
            })
            return existing

        doc = frappe.new_doc("Student Transcript")
        doc.student            = student_name
        doc.transcript_type    = st_type
        doc.status             = "Generated"
        doc.generation_date    = today()
        doc.generated_by       = frappe.session.user
        doc.transcript_request = request_name
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        frappe.log_error(frappe.get_traceback(),
                         f"Transcript generation error for {request_name}")
        return None
