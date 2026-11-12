import datetime
import frappe
import json
import hmac
import hashlib
from frappe import _
from frappe.utils import now_datetime, flt


# ─────────────────────────────────────────────────────────────────────────────
#  Razorpay webhook
# ─────────────────────────────────────────────────────────────────────────────

def _verify_razorpay_signature(raw_data):
    """Fail closed: reject the webhook if it can't be verified against the
    configured secret, rather than trusting an unauthenticated payload."""
    settings = frappe.get_single("Razorpay Settings")
    webhook_secret = settings.get_password("webhook_secret")

    if not webhook_secret:
        frappe.log_error(
            title="Razorpay Webhook (Re Exam/Fee Invoice): secret not configured",
            message="Rejected an incoming webhook because Razorpay Settings.webhook_secret is not set."
        )
        frappe.throw(_("Webhook is not configured"), frappe.PermissionError)

    signature = frappe.get_request_header("X-Razorpay-Signature")
    if not signature:
        frappe.throw(_("Missing Razorpay Signature Header"), frappe.PermissionError)

    secret_bytes = webhook_secret.encode("utf-8") if isinstance(webhook_secret, str) else webhook_secret
    expected_signature = hmac.new(secret_bytes, raw_data, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        frappe.throw(_("Invalid Webhook Signature"), frappe.PermissionError)


@frappe.whitelist(allow_guest=True)
def razorpay_webhook():
    raw_data = frappe.request.get_data()
    _verify_razorpay_signature(raw_data)

    payload = json.loads(raw_data)
    event   = payload.get("event")

    dispatch = {
        "payment.captured":   _handle_payment_captured,
        "payment.failed":     _handle_payment_failed,
        # "created" only means a refund was requested: mark Refunded once Razorpay has processed it,
        # and put a failed refund back to paid
        "refund.processed":   _handle_refund,
        "refund.failed":      _handle_refund_failed,
        "settlement.processed": _handle_settlement,
    }
    handler = dispatch.get(event)
    if handler:
        try:
            handler(payload)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"razorpay_webhook: {event}")

    return "OK"


# ── helpers ───────────────────────────────────────────────────────────────────

def _re_exam_log_exists(razorpay_payment_id):
    return frappe.db.get_value(
        "Re Exam Payment Log",
        {"razorpay_payment_id": razorpay_payment_id},
        "name",
    )


def _upsert_re_exam_log(registration_name, payment, extra=None):
    """Create or update a Re Exam Payment Log for *payment* entity dict."""
    pay_id = payment.get("id")
    notes  = payment.get("notes") or {}

    existing = _re_exam_log_exists(pay_id) if pay_id else None

    fee_paise    = int(payment.get("fee") or 0)
    tax_paise    = int(payment.get("tax") or 0)
    amount_paise = int(payment.get("amount") or 0)

    data = {
        "razorpay_payment_id":  pay_id,
        "razorpay_order_id":    payment.get("order_id"),
        "payment_status":       _rzp_status_to_log(payment.get("status")),
        "amount":               flt(payment.get("amount", 0)) / 100,
        "payment_method":       payment.get("method"),
        "transaction_date":     now_datetime(),
        "transaction_id":       (payment.get("acquirer_data") or {}).get("rrn")
                                or (payment.get("acquirer_data") or {}).get("upi_transaction_id"),
        "account_number_or_upi_id": payment.get("vpa") or payment.get("bank"),
        "failure_reason":       payment.get("error_description") or payment.get("error_reason"),
        "gateway_fees":         fee_paise / 100,
        "gateway_tax":          tax_paise / 100,
        "net_settled":          max((amount_paise - fee_paise - tax_paise) / 100, 0),
        "settlement_amount":    amount_paise / 100,
        "gateway_response":     json.dumps(payment, indent=2),
    }
    if extra:
        data.update(extra)

    if existing:
        frappe.db.set_value("Re Exam Payment Log", existing, data, update_modified=True)
    else:
        doc = frappe.get_doc({
            "doctype":               "Re Exam Payment Log",
            "re_exam_registration":  registration_name,
            **data,
        })
        doc.insert(ignore_permissions=True)

    frappe.db.commit()


def _rzp_status_to_log(rzp_status):
    """Map a raw Razorpay payment status string to our log's Select options."""
    mapping = {
        "created":    "Payment Initiated",
        "authorized": "Authorized",
        "captured":   "Captured",
        "failed":     "Failed",
        "refunded":   "Refunded",
    }
    return mapping.get(rzp_status, "Payment Initiated")


def _rzp_status_to_registration(rzp_status):
    """Map a raw Razorpay payment status to Re Exam Registration payment_status."""
    mapping = {
        "captured":   "Paid",
        "failed":     "Failed",
        "refunded":   "Refunded",
        "authorized": "Authorized",
    }
    return mapping.get(rzp_status)


def _update_re_exam_registration(registration_name, payment_status, payment_reference=None):
    values = {"payment_status": payment_status}
    if payment_reference:
        values["payment_reference"] = payment_reference
    frappe.db.set_value("Re Exam Registration", registration_name, values, update_modified=True)
    frappe.db.commit()


# ── event handlers ────────────────────────────────────────────────────────────

def _handle_payment_captured(payload):
    payment    = payload.get("payload", {}).get("payment", {}).get("entity", {})
    notes      = payment.get("notes") or {}
    ref_type   = notes.get("reference_doctype", "Foundations for a Legal Education")
    ref_name   = notes.get("reference_name")

    if ref_type == "Re Exam Registration" and ref_name:
        # Only create log if confirm_re_exam_payment hasn't already done it
        if not _re_exam_log_exists(payment.get("id")):
            _upsert_re_exam_log(ref_name, payment)
        _update_re_exam_registration(ref_name, "Paid", payment.get("id"))
        return

    # ── Fee Invoice path ──────────────────────────────────────────────────
    if ref_type == "Fee Invoice" and ref_name:
        frappe.db.set_value(
            "Fee Invoice", ref_name, "payment_status", "Captured", update_modified=False
        )
        frappe.db.commit()

    # ── Original FLE / generic path ──────────────────────────────────────
    doc = frappe.get_doc({
        "doctype":             "Razorpay Payment Log",
        "reference_doctype":   ref_type,
        "reference_name":      ref_name,
        "razorpay_order_id":   payment.get("order_id"),
        "razorpay_payment_id": payment.get("id"),
        "razorpay_signature":  frappe.request.headers.get("X-Razorpay-Signature"),
        "transaction_id":      (payment.get("acquirer_data") or {}).get("rrn"),
        "upi_id":              payment.get("vpa"),
        "payment_method":      payment.get("method"),
        "payment_status":      payment.get("status"),
        "amount":              flt(payment.get("amount", 0)) / 100,
        "currency":            payment.get("currency"),
        "payment_datetime":    now_datetime(),
        "raw_response":        json.dumps(payment, indent=4),
    })
    doc.insert(ignore_permissions=True)

    if ref_name:
        try:
            main_doc = frappe.get_doc(ref_type, ref_name)
            if hasattr(main_doc, "payment_status"):
                main_doc.payment_status = "Paid"
            main_doc.save(ignore_permissions=True)
        except frappe.DoesNotExistError:
            pass


def _handle_payment_failed(payload):
    payment  = payload.get("payload", {}).get("payment", {}).get("entity", {})
    notes    = payment.get("notes") or {}
    ref_type = notes.get("reference_doctype")
    ref_name = notes.get("reference_name")

    if ref_type == "Re Exam Registration" and ref_name:
        _upsert_re_exam_log(ref_name, payment)
        _update_re_exam_registration(ref_name, "Failed")
        return

    if ref_type == "Fee Invoice" and ref_name:
        frappe.db.set_value(
            "Fee Invoice", ref_name, "payment_status", "Payment Failed", update_modified=False
        )
        frappe.db.commit()


def _handle_refund_failed(payload):
    """A refund Razorpay could not complete: the money stays with the university, so undo a Refunded mark
    made for this refund (re-exam payment log + registration, Fee Invoice)."""
    refund  = payload.get("payload", {}).get("refund", {}).get("entity", {})
    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
    try:
        from slcm.slcm.fee.payment_ledger import remove_gateway_refund
        remove_gateway_refund(refund.get("payment_id") or payment.get("id"), refund.get("id"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "razorpay_webhook: remove failed refund")
    notes    = (payment.get("notes") or {}) if payment else {}
    ref_type = notes.get("reference_doctype")
    ref_name = notes.get("reference_name")

    if ref_type == "Fee Invoice" and ref_name:
        if frappe.db.get_value("Fee Invoice", ref_name, "payment_status") == "Refunded":
            frappe.db.set_value("Fee Invoice", ref_name, "payment_status", "Captured", update_modified=False)
            frappe.db.commit()
        return

    refund_id = refund.get("id")
    log_name = frappe.db.get_value(
        "Re Exam Payment Log", {"refund_id": refund_id, "payment_status": "Refunded"}, "name"
    ) if refund_id else None
    if log_name:
        frappe.db.set_value("Re Exam Payment Log", log_name, "payment_status", "Paid", update_modified=True)
        if ref_type == "Re Exam Registration" and ref_name:
            _update_re_exam_registration(ref_name, "Paid")
        frappe.db.commit()


def _handle_refund(payload):
    """Handle refund.processed events."""
    refund  = payload.get("payload", {}).get("refund", {}).get("entity", {})
    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})

    # record it on the student payment's SLCM Payment Request (ERPNext: Gateway Refund)
    try:
        from slcm.slcm.fee.payment_ledger import record_gateway_refund
        created = refund.get("created_at")
        record_gateway_refund(
            refund.get("payment_id") or payment.get("id"), refund.get("id"), flt(refund.get("amount", 0)) / 100,
            refunded_on=datetime.datetime.utcfromtimestamp(int(created)).date() if created else None,
            source="Razorpay refund webhook",
        )
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "razorpay_webhook: record refund on payment request")

    # Resolve reference from payment notes (Razorpay includes the payment entity in refund events)
    notes    = (payment.get("notes") or {}) if payment else {}
    ref_type = notes.get("reference_doctype")
    ref_name = notes.get("reference_name")

    if ref_type == "Fee Invoice" and ref_name:
        frappe.db.set_value(
            "Fee Invoice", ref_name, "payment_status", "Refunded", update_modified=False
        )
        frappe.db.commit()
        return

    if ref_type != "Re Exam Registration" or not ref_name:
        return

    pay_id  = refund.get("payment_id") or payment.get("id")
    log_name = frappe.db.get_value(
        "Re Exam Payment Log",
        {"razorpay_payment_id": pay_id},
        "name",
    ) if pay_id else None

    refund_data = {
        "payment_status": "Refunded",
        "refund_id":      refund.get("id"),
        "refund_amount":  flt(refund.get("amount", 0)) / 100,
        "gateway_response": json.dumps({
            "refund": refund,
            "original_payment": payment,
        }, indent=2),
    }

    if log_name:
        frappe.db.set_value("Re Exam Payment Log", log_name, refund_data, update_modified=True)
    else:
        # No prior log — create one now
        _upsert_re_exam_log(ref_name, payment or {}, extra=refund_data)

    _update_re_exam_registration(ref_name, "Refunded")


def _handle_settlement(payload):
    """Update settlement fields on Re Exam Payment Logs matching this settlement.

    Razorpay's settlement.processed webhook covers a batch of payments.
    We store settlement metadata here; individual gateway_fees/tax are captured
    during payment.captured via _upsert_re_exam_log.
    """
    import datetime as _dt

    settlement = payload.get("payload", {}).get("settlement", {}).get("entity", {})
    settle_id  = settlement.get("id")
    if not settle_id:
        return

    settle_utr    = settlement.get("utr") or ""
    settle_status = settlement.get("status") or ""
    settle_date   = None
    settled_at    = settlement.get("settled_at")
    if settled_at:
        try:
            settle_date = _dt.date.fromtimestamp(int(settled_at)).isoformat()
        except Exception:
            pass

    # Razorpay does not include individual payment IDs in the settlement webhook.
    # We update all Paid/Captured logs that have no settlement_id yet (best-effort).
    # Fine-grained reconciliation requires the Razorpay settlement recon API.
    logs = frappe.db.get_all(
        "Re Exam Payment Log",
        filters={"payment_status": ["in", ["Paid", "Captured"]], "settlement_id": ["in", ["", None]]},
        pluck="name",
        limit=500,
    )
    if logs:
        update_data = {"settlement_id": settle_id, "settlement_status": settle_status}
        if settle_utr:
            update_data["settlement_utr"] = settle_utr
        if settle_date:
            update_data["settlement_date"] = settle_date
        for log_name in logs:
            frappe.db.set_value("Re Exam Payment Log", log_name, update_data, update_modified=False)
        frappe.db.commit()


# ─────────────────────────────────────────────────────────────────────────────
#  FLE sign-up
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def fle_sign_up(email: str, mobile_no: str) -> tuple[int, str]:
    if not email or not mobile_no:
        frappe.throw("Email and Mobile Number are required")

    user = frappe.db.get("User", {"email": email})
    if user:
        if user.enabled:
            return 0, "Already Registered"
        else:
            return 0, "Registered but disabled"

    from frappe.utils import random_string, escape_html

    first_name = email.split('@')[0]

    user_doc = frappe.get_doc({
        "doctype":         "User",
        "email":           email,
        "first_name":      escape_html(first_name),
        "mobile_no":       escape_html(mobile_no),
        "enabled":         1,
        "new_password":    random_string(10),
        "user_type":       "Website User",
        "send_welcome_email": 1,
    })
    user_doc.flags.ignore_permissions = True
    user_doc.flags.ignore_password_policy = True
    user_doc.insert()

    # default_role = frappe.get_single_value("Portal Settings", "default_role")
    # if default_role:
    #     user_doc.add_roles(default_role)

    if user_doc.flags.email_sent:
        return 1, "Please check your email to verify your account and set a password"
    else:
        return 1, "Registration successful. Please check your email for verification"
