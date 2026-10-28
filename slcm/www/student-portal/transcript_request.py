import frappe
from frappe.utils import today
from slcm.slcm.utils.exam_schedule import get_student_programme

no_cache = 1


def get_context(context):
    context.no_cache = 1

    # Set all template variables unconditionally first — Jinja renders even for
    # early-return paths (guest, no-student) so every variable must always exist.
    context.settings = _get_settings()
    context.requests = []
    context.has_published_results = False
    context.cgpa = 0.0
    context.pending_count = 0
    context.ready_count = 0
    context.is_guest = False
    context.no_student = False
    context.portal_error = ""

    if frappe.session.user == "Guest":
        context.is_guest = True
        _set_nav_defaults(context)
        return context

    context.active_page = "documents"

    student_name = _get_student_name()
    if not student_name:
        context.no_student = True
        _set_nav_defaults(context)
        return context

    try:
        student = frappe.get_doc("Student Master", student_name)
        _set_student_nav(context, student)

        # ── Transcript Requests ───────────────────────────────────────────────────
        requests = frappe.get_all(
            "Transcript Request",
            filters={"student": student_name},
            fields=[
                "name", "transcript_type", "num_copies", "status", "payment_status",
                "razorpay_payment_status", "fee_amount", "payment_required",
                "requested_on", "purpose", "delivery_mode", "urgency",
                "transcript_doc", "rejection_reason",
                "payment_date", "payment_reference", "reviewed_on",
            ],
            order_by="requested_on desc, creation desc",
            ignore_permissions=True,
        )
        context.requests = requests

        # ── Derived counters ──────────────────────────────────────────────────────
        pending_statuses = {"Draft", "Payment Pending", "Submitted", "Under Review", "Approved"}
        ready_statuses   = {"Generated", "Delivered"}
        context.pending_count = sum(1 for r in requests if r.status in pending_statuses)
        context.ready_count   = sum(1 for r in requests if r.status in ready_statuses)

        # ── Published results check ───────────────────────────────────────────────
        published_count = frappe.db.count(
            "Student Result Publish",
            {"student": student_name, "is_published": 1},
        )
        context.has_published_results = bool(published_count)

        # ── Latest CGPA ───────────────────────────────────────────────────────────
        context.cgpa = round(student.current_cgpa or 0.0, 2)

    except Exception as e:
        frappe.log_error(f"Transcript request portal error: {e}", "Student Portal")
        context.portal_error = str(e)
        _set_nav_defaults(context)

    return context


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_settings():
    """Return Transcript Fee Settings as a simple dict/object."""
    defaults = frappe._dict({
        "enable_payment": 0,
        "allow_interim": 1, "allow_final": 1, "allow_marksheet": 1,
        "allow_duplicate": 1, "allow_digital": 1,
        "interim_fee": 300, "final_fee": 1000, "marksheet_fee": 500,
        "duplicate_fee": 500, "digital_fee": 150,
        "urgent_fee": 0, "tax_percentage": 0, "currency": "INR",
        "free_requests_per_student": 0,
        "auto_approve_interim": 1, "auto_approve_final": 0,
        "restrict_final_to_graduates": 0,
        "notify_on_submission": None, "notify_on_payment": None,
        "notify_on_approval": None, "notify_on_rejection": None,
        "notify_on_ready": None,
        "max_processing_days": 5, "urgent_processing_days": 2,
    })
    try:
        if frappe.db.exists("DocType", "Transcript Fee Settings"):
            doc = frappe.get_doc("Transcript Fee Settings", "Transcript Fee Settings")
            for key in defaults:
                val = getattr(doc, key, None)
                if val is not None:
                    defaults[key] = val
    except Exception:
        pass
    return defaults


def _get_student_name():
    user = frappe.session.user
    for field in ("user", "email", "official_email_id"):
        name = frappe.db.get_value("Student Master", {field: user}, "name")
        if name:
            return name
    return None


def _set_student_nav(context, student):
    full_name = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))
    context.student_name    = full_name or student.name
    context.student_id      = student.registration_id or student.name
    context.student_photo   = student.passport_size_photo or ""
    context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
    context.programme_name  = get_student_programme(student.name)
    context.department      = student.department or ""
    context.batch_year      = student.batch or ""


def _set_nav_defaults(context):
    user = frappe.session.user
    user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
    context.student_name    = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.student_id      = ""
    context.student_photo   = (user_doc.user_image if user_doc else "") or ""
    context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
    context.programme_name  = ""
    context.department      = ""
    context.batch_year      = ""
    context.has_published_results = False
    context.cgpa            = 0.0
    context.pending_count   = 0
    context.ready_count     = 0
