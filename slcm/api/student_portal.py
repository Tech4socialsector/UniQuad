# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, cint, today, nowdate, getdate
from slcm.api.student_payment import _require_parent_for_student


def _get_student():
    """Return the Student Master name for the currently logged-in user."""
    user = frappe.session.user
    name = frappe.db.get_value("Student Master", {"user": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"email": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    return name


# ─────────────────────────────────────────────────────────────────────────────
#  Lookup helpers
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_condonation_reasons():
    """Return a list of available Condonation Reason names."""
    try:
        reasons = frappe.get_all(
            "Condonation Reason",
            fields=["name"],
            order_by="name asc",
            ignore_permissions=True
        )
        return [r.name for r in reasons]
    except Exception as e:
        frappe.log_error(f"get_condonation_reasons error: {e}", "Student Portal API")
        return []


# ─────────────────────────────────────────────────────────────────────────────
#  FA / MFA Application
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def submit_fa_mfa_application(
    course,
    examination_date,
    application_type,
    reason,
    description=None,
    proof_document=None,
    event_from_date=None,
    event_to_date=None,
):
    """
    Create and save a new FA/MFA Application on behalf of the logged-in student.
    Called via AJAX from the student portal attendance page.
    """
    if frappe.session.user == "Guest":
        frappe.throw("Please log in to submit an application.", frappe.PermissionError)

    student = _get_student()
    if not student:
        frappe.throw(
            "No student record found for your account. "
            "Please contact the Registrar's Office."
        )

    # Validate required fields
    for label, val in [
        ("Course", course),
        ("Examination Date", examination_date),
        ("Application Type", application_type),
        ("Reason", reason),
        ("Proof Document", proof_document),
    ]:
        if not val:
            frappe.throw(f"{label} is required.")

    # Prevent duplicate
    existing = frappe.db.exists(
        "FA MFA Application",
        {
            "student": student,
            "course": course,
            "examination_date": examination_date,
            "docstatus": ["<", 2],
        },
    )
    if existing:
        frappe.throw(
            f"An application for this course and examination date already exists "
            f"(ID: {existing}). Please check your existing applications."
        )

    doc = frappe.new_doc("FA MFA Application")
    doc.student = student
    doc.course = course
    doc.examination_date = examination_date
    doc.application_type = application_type
    doc.reason = reason
    doc.description = description or ""
    doc.proof_document = proof_document
    doc.status = "Pending"

    if reason == "University Representation":
        if event_from_date:
            doc.event_from_date = event_from_date
        if event_to_date:
            doc.event_to_date = event_to_date

    try:
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"FA MFA Application insert error: {e}", "Student Portal API")
        frappe.throw(str(e))

    return {
        "name": doc.name,
        "status": "success",
        "message": f"Application submitted successfully. Application ID: {doc.name}",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Condonation Application
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def submit_condonation_application(
    course_offering,
    number_of_sessions,
    number_of_hours,
    condonation_reason,
    absence_from_date=None,
    absence_to_date=None,
    proof_document=None,
):
    """
    Create and save a new Student Attendance Condonation on behalf of the
    logged-in student. Called via AJAX from the student portal attendance page.
    """
    if frappe.session.user == "Guest":
        frappe.throw("Please log in to submit an application.", frappe.PermissionError)

    student = _get_student()
    if not student:
        frappe.throw(
            "No student record found for your account. "
            "Please contact the Registrar's Office."
        )

    # Validate required fields
    for label, val in [
        ("Course", course_offering),
        ("Number of Sessions", number_of_sessions),
        ("Number of Hours", number_of_hours),
        ("Reason", condonation_reason),
    ]:
        if not val:
            frappe.throw(f"{label} is required.")

    # Check global setting
    settings = frappe.get_single("Attendance Settings")
    if not settings.allow_condonation:
        frappe.throw("Condonation Applications are currently disabled by the administration.")

    # Prevent duplicate pending application for same course
    existing = frappe.db.exists(
        "Student Attendance Condonation",
        {
            "student": student,
            "course_offering": course_offering,
            "final_status": "Pending",
            "docstatus": ["<", 2],
        },
    )
    if existing:
        frappe.throw(
            f"A pending condonation application for this course already exists "
            f"(ID: {existing})."
        )

    # Attendance percentage is intentionally NOT checked here — students may
    # apply for condonation anytime. The minimum-percentage floor is only
    # enforced at final (Programme Chair) approval, closer to end-of-trimester
    # attendance figures. See StudentAttendanceCondonation.programme_chair_decision.

    doc = frappe.new_doc("Student Attendance Condonation")
    doc.student = student
    doc.course_offering = course_offering
    doc.number_of_sessions = cint(number_of_sessions)
    doc.number_of_hours = flt(number_of_hours)
    doc.condonation_reason = condonation_reason
    if absence_from_date:
        doc.absence_from_date = absence_from_date
    if absence_to_date:
        doc.absence_to_date = absence_to_date
    if proof_document:
        doc.proof_document = proof_document
    doc.final_status = "Pending"

    try:
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Condonation insert error: {e}", "Student Portal API")
        frappe.throw(str(e))

    return {
        "name": doc.name,
        "status": "success",
        "message": f"Condonation application submitted successfully. Application ID: {doc.name}",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Support Ticket
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def create_support_ticket(category, subject, description, attachment=None):
    """
    Create a support ticket (Communication record) on behalf of the logged-in student.
    Sends an email notification to the system admin.
    """
    if frappe.session.user == "Guest":
        frappe.throw("Please log in to raise a support ticket.", frappe.PermissionError)

    for label, val in [("Category", category), ("Subject", subject), ("Description", description)]:
        if not val or not str(val).strip():
            frappe.throw(f"{label} is required.")

    student = _get_student()
    student_name_display = frappe.session.user
    student_id = ""
    if student:
        s = frappe.db.get_value(
            "Student Master",
            student,
            ["first_name", "last_name", "registration_id"],
            as_dict=True,
        )
        if s:
            student_name_display = " ".join(filter(None, [s.first_name, s.last_name])) or student
            student_id = s.registration_id or student

    full_subject = f"[{category}] {str(subject).strip()}"
    full_content = (
        f"<p><strong>Category:</strong> {category}</p>"
        f"<p><strong>Student:</strong> {student_name_display}"
        + (f" ({student_id})" if student_id else "") +
        f"</p>"
        f"<p><strong>Email:</strong> {frappe.session.user}</p>"
        f"<hr>"
        f"<p>{str(description).strip().replace(chr(10), '<br>')}</p>"
        + (f"<p><strong>Attachment:</strong> <a href='{attachment}'>{attachment}</a></p>" if attachment else "")
    )

    # Create Communication record for tracking
    comm = frappe.new_doc("Communication")
    comm.communication_type = "Communication"
    comm.communication_medium = "Email"
    comm.subject = full_subject
    comm.content = full_content
    comm.sent_or_received = "Received"
    comm.status = "Open"
    comm.sender = frappe.session.user
    comm.sender_full_name = student_name_display
    if student:
        comm.reference_doctype = "Student Master"
        comm.reference_name = student
    comm.communication_date = frappe.utils.now()

    try:
        comm.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Support ticket Communication insert error: {e}", "Student Portal API")
        frappe.throw("Failed to create support ticket. Please try again.")

    # Email notification to admin
    try:
        admin_email = frappe.db.get_single_value("System Settings", "support_email") or ""
        if not admin_email:
            # Fallback to first outgoing email account
            acc = frappe.db.get_value(
                "Email Account",
                {"enable_outgoing": 1},
                "email_id",
            )
            admin_email = acc or ""

        if admin_email:
            frappe.sendmail(
                recipients=[admin_email],
                subject=f"[Student Portal] {full_subject}",
                message=full_content,
                now=False,
            )
    except Exception as e:
        # Email failure should not block the user
        frappe.log_error(f"Support ticket email error: {e}", "Student Portal API")

    return {
        "name": comm.name,
        "status": "success",
        "message": f"Support ticket raised successfully! Ticket ID: {comm.name}",
    }


@frappe.whitelist()
def get_my_support_tickets():
    """Return support tickets (Communications) raised by the logged-in student."""
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)

    student = _get_student()
    filters = [["sender", "=", frappe.session.user]]
    if student:
        filters = [
            ["reference_doctype", "=", "Student Master"],
            ["reference_name", "=", student],
        ]

    try:
        tickets = frappe.get_all(
            "Communication",
            filters=filters,
            fields=["name", "subject", "content", "status", "communication_date", "creation"],
            order_by="creation desc",
            limit=20,
            ignore_permissions=True,
        )
        return tickets
    except Exception as e:
        frappe.log_error(f"get_my_support_tickets error: {e}", "Student Portal API")
        return []


# ─────────────────────────────────────────────────────────────────────────────
#  Office Hours Registration
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def register_office_hours_attendance(session_name):
    """
    Register the logged-in student's attendance for a scheduled Office Hours Session.
    Creates a Student Attendance record with based_on = Office Hours.
    """
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)

    student = _get_student()
    if not student:
        frappe.throw("No student record found for your account.")

    try:
        session = frappe.get_doc("Office Hours Session", session_name, ignore_permissions=True)
    except frappe.DoesNotExistError:
        frappe.throw("Office Hours Session not found.")

    if session.session_status != "Scheduled":
        frappe.throw("This session is no longer available for registration.")

    # Prevent duplicate registration
    existing = frappe.db.exists(
        "Student Attendance",
        {
            "student": student,
            "attendance_date": session.session_date,
            "based_on": "Office Hours",
            "course_offer": session.course_offering,
        },
    )
    if existing:
        frappe.throw("You have already registered attendance for this office hours session.")

    office_hours_group = frappe.db.get_value(
        "Office Hours Group", {"office_hours_session": session.name}
    )

    doc = frappe.new_doc("Student Attendance")
    doc.based_on = "Office Hours"
    doc.office_hours_group = office_hours_group
    doc.student = student
    doc.course_offer = session.course_offering
    doc.attendance_date = session.session_date
    doc.date = session.session_date
    doc.status = "Present"
    doc.in_time = frappe.utils.get_datetime(f"{session.session_date} {session.start_time}")
    doc.out_time = frappe.utils.get_datetime(f"{session.session_date} {session.end_time}")
    doc.session_type = "Office Hour"
    doc.source = "Manual"

    try:
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Office Hours registration error: {e}", "Student Portal API")
        frappe.throw(str(e))

    return {
        "name": doc.name,
        "status": "success",
        "message": "You have been successfully registered for the office hours session.",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Secure Document Downloads
# ─────────────────────────────────────────────────────────────────────────────

# Maps doc_type keys the student can request to (Frappe doctype, print format name)
_ALLOWED_DOWNLOADS = {
    "application_form": {
        "doctype": "Applicant",
        "format":  "Applicant Application Form",
        "filename": "Application_Form",
        "source":   "application_number",   # SM field that holds the doc name
    },
    "registration_slip": {
        "doctype": "Student Master",
        "format":  "Student Registration Slip",
        "filename": "Registration_Slip",
        "source":   "self",                 # use the student's own SM name
    },
}


@frappe.whitelist()
def download_student_document(doc_type):
    """Generate and stream a PDF for the requesting student's own document.

    Security:
    * Caller must be authenticated and have a Student Master record.
    * Only document types listed in _ALLOWED_DOWNLOADS are permitted.
    * For Applicant documents, the Applicant name is read from the student's
      own `application_number` field — the student cannot request another
      applicant's form.

    Usage (called via a direct browser link):
        /api/method/slcm.api.student_portal.download_student_document
            ?doc_type=application_form
    """
    from frappe.utils.pdf import get_pdf

    # ── Auth guard ────────────────────────────────────────────
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in to download documents."),
                     frappe.AuthenticationError)

    student_name = _get_student()
    if not student_name:
        frappe.throw(frappe._("No student record found for your account."),
                     frappe.PermissionError)

    # ── Allowed-list check ────────────────────────────────────
    config = _ALLOWED_DOWNLOADS.get(doc_type)
    if not config:
        frappe.throw(
            frappe._("Invalid document type '{0}'.").format(doc_type),
            frappe.ValidationError,
        )

    # ── Resolve the document name ─────────────────────────────
    if config["source"] == "self":
        doc_name = student_name
    else:
        # e.g. application_number from Student Master
        doc_name = frappe.db.get_value(
            "Student Master", student_name, config["source"]
        )
        if not doc_name:
            frappe.throw(
                frappe._("No {0} record found on your student profile.").format(
                    config["doctype"]
                ),
                frappe.ValidationError,
            )

    # ── Verify the document exists before attempting PDF generation ──
    # Prevents a cryptic 500 error if the record was deleted or never created.
    if not frappe.db.exists(config["doctype"], doc_name):
        frappe.throw(
            frappe._(
                "Your {0} record could not be found. "
                "Please contact the Registrar's Office."
            ).format(config["doctype"]),
            frappe.DoesNotExistError,
        )

    # ── Generate PDF (escalate to Administrator so the print
    #    format can read the document regardless of role perms) ─
    pdf_bytes = _generate_pdf(config["doctype"], doc_name, config["format"])

    # ── Stream response ───────────────────────────────────────
    safe_name = doc_name.replace("/", "-").replace(" ", "_")
    frappe.local.response.filename    = f"{config['filename']}_{safe_name}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type        = "pdf"


@frappe.whitelist()
def download_fee_invoice(invoice_name):
    """Stream a PDF of the student's own Fee Invoice.

    Security:
    * Caller must be authenticated and have a Student Master record.
    * Invoice ownership validated before any PDF is generated (IDOR guard).
    """
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)

    student_name = _get_student()
    if not student_name:
        frappe.throw(frappe._("No student record found for your account."),
                     frappe.PermissionError)

    # Ownership check — the invoice must belong to this student
    owner = frappe.db.get_value("Fee Invoice", invoice_name, "student")
    if not owner or owner != student_name:
        frappe.throw(frappe._("Invoice not found or access denied."),
                     frappe.PermissionError)

    # Resolve print format: prefer the one configured on the student's Fee Structure
    print_format = _resolve_invoice_print_format(student_name)

    pdf_bytes = _generate_pdf("Fee Invoice", invoice_name, print_format)

    safe = invoice_name.replace("/", "-").replace(" ", "_")
    frappe.local.response.filename    = f"Fee_Invoice_{safe}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type        = "pdf"


@frappe.whitelist()
def download_fee_receipt(receipt_name):
    """Stream a PDF of a Fee Receipt for the logged-in student.

    Security:
    * Caller must be authenticated with a Student Master record.
    * Receipt ownership validated before any PDF is generated (IDOR guard).
    """
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)

    student_name = _get_student()
    if not student_name:
        frappe.throw(frappe._("No student record found for your account."),
                     frappe.PermissionError)

    receipt_row = frappe.db.get_value(
        "Fee Receipt", receipt_name, ["student", "fee_payment"], as_dict=True)
    if not receipt_row or receipt_row.student != student_name:
        frappe.throw(frappe._("Receipt not found or access denied."),
                     frappe.PermissionError)

    # Fee Receipt doctype has no dedicated print format — render the linked
    # Fee Payment document using the student-facing payment receipt format.
    fp_name = receipt_row.fee_payment
    if not fp_name:
        # Fallback: some receipts may have been created without the fee_payment
        # link set — find it by querying the reverse side.
        fp_name = frappe.db.get_value("Fee Payment", {"receipt": receipt_name}, "name")

    safe = receipt_name.replace("/", "-").replace(" ", "_")

    if fp_name:
        # Verify the Fee Payment also belongs to this student (belt-and-suspenders)
        fp_student = frappe.db.get_value("Fee Payment", fp_name, "student")
        if fp_student and fp_student != student_name:
            frappe.throw(frappe._("Receipt not found or access denied."),
                         frappe.PermissionError)
        pdf_bytes = _generate_pdf("Fee Payment", fp_name,
                                  "Fee Payment Receipt - Student Copy")
    else:
        # Orphan receipt: no Fee Payment document linked.
        # Generate a simple receipt PDF directly from Fee Receipt fields.
        pdf_bytes = _generate_orphan_receipt_pdf(receipt_name)

    frappe.local.response.filename    = f"Fee_Receipt_{safe}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type        = "pdf"


@frappe.whitelist()
def parent_download_fee_invoice(invoice_name, student_name):
    """Stream a PDF of a Fee Invoice for a parent viewing their ward's record.

    Security:
    * Caller must be a logged-in parent linked to student_name.
    * Invoice must belong to student_name (IDOR guard).
    """
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)

    _require_parent_for_student(student_name)

    owner = frappe.db.get_value("Fee Invoice", invoice_name, "student")
    if not owner or owner != student_name:
        frappe.throw(frappe._("Invoice not found or access denied."),
                     frappe.PermissionError)

    print_format = _resolve_invoice_print_format(student_name)
    pdf_bytes = _generate_pdf("Fee Invoice", invoice_name, print_format)

    safe = invoice_name.replace("/", "-").replace(" ", "_")
    frappe.local.response.filename    = f"Fee_Invoice_{safe}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type        = "pdf"


@frappe.whitelist()
def parent_download_fee_receipt(receipt_name, student_name):
    """Stream a PDF of a Fee Receipt for a parent viewing their ward's record.

    Security:
    * Caller must be a logged-in parent linked to student_name.
    * Receipt must belong to student_name (IDOR guard).
    """
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)

    _require_parent_for_student(student_name)

    receipt_row = frappe.db.get_value(
        "Fee Receipt", receipt_name, ["student", "fee_payment"], as_dict=True)
    if not receipt_row or receipt_row.student != student_name:
        frappe.throw(frappe._("Receipt not found or access denied."),
                     frappe.PermissionError)

    fp_name = receipt_row.fee_payment
    if not fp_name:
        fp_name = frappe.db.get_value("Fee Payment", {"receipt": receipt_name}, "name")

    safe = receipt_name.replace("/", "-").replace(" ", "_")

    if fp_name:
        fp_student = frappe.db.get_value("Fee Payment", fp_name, "student")
        if fp_student and fp_student != student_name:
            frappe.throw(frappe._("Receipt not found or access denied."),
                         frappe.PermissionError)
        pdf_bytes = _generate_pdf("Fee Payment", fp_name,
                                  "Fee Payment Receipt - Student Copy")
    else:
        pdf_bytes = _generate_orphan_receipt_pdf(receipt_name)

    frappe.local.response.filename    = f"Fee_Receipt_{safe}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type        = "pdf"


@frappe.whitelist()
def download_re_exam_receipt(registration_name):
    """Stream a PDF receipt for the student's own Re Exam Registration.

    Security:
    * Caller must be authenticated with a Student Master record.
    * Registration ownership validated (IDOR guard).
    * Only Paid registrations produce a receipt.
    """
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)

    student_name = _get_student()
    if not student_name:
        frappe.throw(frappe._("No student record found for your account."), frappe.PermissionError)

    reg = frappe.db.get_value(
        "Re Exam Registration",
        {"name": registration_name, "student": student_name},
        ["name", "status", "payment_status"],
        as_dict=True,
    )
    if not reg:
        frappe.throw(frappe._("Registration not found or access denied."), frappe.PermissionError)

    if reg.payment_status not in ("Paid", "Captured"):
        frappe.throw(
            frappe._("Receipt is only available after payment is confirmed."),
            frappe.ValidationError,
        )

    # Resolve print format from Student Portal Settings
    try:
        pf_setting = frappe.db.get_single_value(
            "Student Portal Settings", "re_exam_receipt_print_format"
        )
        if pf_setting and frappe.db.exists("Print Format", pf_setting):
            print_format = pf_setting
        else:
            print_format = "Re Exam Receipt"
    except Exception:
        print_format = "Re Exam Receipt"

    pdf_bytes = _generate_pdf("Re Exam Registration", registration_name, print_format)

    safe = registration_name.replace("/", "-").replace(" ", "_")
    frappe.local.response.filename    = f"ReExam_Receipt_{safe}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type        = "pdf"


@frappe.whitelist()
def download_improvement_exam_receipt(registration_name):
    """Stream a PDF receipt for the student's own Improvement Exam Registration."""
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)

    student_name = _get_student()
    if not student_name:
        frappe.throw(frappe._("No student record found for your account."), frappe.PermissionError)

    reg = frappe.db.get_value(
        "Improvement Exam Registration",
        {"name": registration_name, "student": student_name},
        ["name", "status", "payment_status"],
        as_dict=True,
    )
    if not reg:
        frappe.throw(frappe._("Registration not found or access denied."), frappe.PermissionError)

    if reg.payment_status not in ("Paid", "Captured"):
        frappe.throw(
            frappe._("Receipt is only available after payment is confirmed."),
            frappe.ValidationError,
        )

    try:
        pf_setting = frappe.db.get_single_value(
            "Student Portal Settings", "improvement_exam_receipt_print_format"
        )
        if pf_setting and frappe.db.exists("Print Format", pf_setting):
            print_format = pf_setting
        else:
            print_format = "Improvement Exam Receipt"
    except Exception:
        print_format = "Improvement Exam Receipt"

    pdf_bytes = _generate_pdf("Improvement Exam Registration", registration_name, print_format)

    safe = registration_name.replace("/", "-").replace(" ", "_")
    frappe.local.response.filename    = f"ImprovementExam_Receipt_{safe}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type        = "pdf"


@frappe.whitelist()
def download_fee_invoice_admin(invoice_name):
    """Stream a PDF of any Fee Invoice for admin / REGO office users.

    Security:
    * Caller must be authenticated (not Guest).
    * Caller must have at least one of the allowed admin roles.
      (System Manager, REGO Officer, FINO Officer, Registration Officer,
       Registration User, Documentation Officer, IT Admin, or Accounts Manager)
    * No student-ownership check — admins can download any student's invoice.
    """
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)

    ADMIN_ROLES = {
        "System Manager", "Administrator",
        "slcm_REGO Officer", "slcm_FINO Officer",
        "slcm_Registration Officer", "slcm_Registration User",
        "slcm_Documentation Officer", "slcm_IT Admin",
        "Accounts Manager", "Accounts User",
    }
    user_roles = set(frappe.get_roles(frappe.session.user))
    if not user_roles.intersection(ADMIN_ROLES):
        frappe.throw(
            frappe._("You do not have permission to download fee invoices."),
            frappe.PermissionError,
        )

    if not frappe.db.exists("Fee Invoice", invoice_name):
        frappe.throw(frappe._("Invoice not found."), frappe.DoesNotExistError)

    # Resolve print format via the invoice's linked student
    student_name = frappe.db.get_value("Fee Invoice", invoice_name, "student")
    print_format  = _resolve_invoice_print_format(student_name) if student_name else "Fee Invoice Receipt"

    pdf_bytes = _generate_pdf("Fee Invoice", invoice_name, print_format)

    safe = invoice_name.replace("/", "-").replace(" ", "_")
    frappe.local.response.filename    = f"Fee_Invoice_{safe}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type        = "pdf"


@frappe.whitelist()
def download_fee_demand_receipt_admin(receipt_name, fee_demand_name=None):
    """Stream a per-demand PDF receipt for admin users.

    When fee_demand_name is supplied the PDF shows only that demand's row,
    even if the underlying Fee Receipt covers multiple demands paid together.

    Security:
    * Caller must be authenticated (not Guest).
    * Caller must have at least one of the allowed admin roles.
    * No student-ownership check — admins can download any student's receipt.
    """
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)

    ADMIN_ROLES = {
        "System Manager", "Administrator",
        "slcm_REGO Officer", "slcm_FINO Officer",
        "slcm_Registration Officer", "slcm_Registration User",
        "slcm_Documentation Officer", "slcm_IT Admin",
        "Accounts Manager", "Accounts User",
    }
    user_roles = set(frappe.get_roles(frappe.session.user))
    if not user_roles.intersection(ADMIN_ROLES):
        frappe.throw(
            frappe._("You do not have permission to download fee receipts."),
            frappe.PermissionError,
        )

    if not frappe.db.exists("Fee Receipt", receipt_name):
        frappe.throw(frappe._("Receipt not found."), frappe.DoesNotExistError)

    pdf_bytes = _generate_demand_receipt_pdf(receipt_name, fee_demand_name)

    safe_dem = (fee_demand_name or receipt_name).replace("/", "-").replace(" ", "_")
    frappe.local.response.filename    = f"Fee_Demand_Receipt_{safe_dem}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type        = "pdf"


def _generate_demand_receipt_pdf(receipt_name, fee_demand_name=None):
    """Generate a PDF for a single Fee Demand row from a (possibly shared) Fee Receipt.

    Loads the receipt, filters demands_paid to the requested demand, adjusts the
    amount total, then renders the print format — without modifying the database.
    """
    from frappe.utils.pdf import get_pdf
    import copy as _copy

    sess          = frappe.local.session
    orig_user     = sess.user
    orig_sid      = getattr(sess, "sid",  None)
    orig_data     = _copy.deepcopy(getattr(sess, "data", frappe._dict()))

    try:
        frappe.set_user("Administrator")
        receipt = frappe.get_doc("Fee Receipt", receipt_name)

        if fee_demand_name:
            # Filter demands_paid to the specific demand row
            filtered = [r for r in receipt.demands_paid if r.get("fee_demand") == fee_demand_name]
            if filtered:
                receipt.demands_paid = filtered
                receipt.amount = sum(r.amount for r in filtered)

        html = frappe.get_print(
            doctype="Fee Receipt",
            name=receipt_name,
            print_format="Fee Receipt",
            as_pdf=False,
            no_letterhead=0,
            doc=receipt,
        )
        return get_pdf(html)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_generate_demand_receipt_pdf")
        frappe.throw(
            frappe._("Could not generate the receipt. Please try again or contact support."),
            frappe.ValidationError,
        )
    finally:
        frappe.set_user(orig_user)
        if orig_sid:
            sess.sid  = orig_sid
        sess.data = orig_data


def _resolve_invoice_print_format(student_name):
    """Return the receipt_print_format from the student's active Fee Structure, or the default."""
    default_fmt = "Fee Invoice Receipt"
    try:
        fs_name = frappe.db.get_value("Student Master", student_name, "fee_structure")
        if not fs_name:
            # Fallback: find active Student fee structure via programme
            programme = frappe.db.get_value("Student Master", student_name, "programme")
            if programme:
                program = frappe.db.get_value("Batch", programme, "program")
                if not program and frappe.db.exists("Programme", programme):
                    program = programme
                if program:
                    fs_name = frappe.db.get_value(
                        "Fee Structure",
                        {"program": program, "status": "Active", "applicable": "Student"},
                        "name",
                        order_by="valid_from desc, creation desc",
                    )
        if fs_name:
            pf = frappe.db.get_value("Fee Structure", fs_name, "receipt_print_format")
            if pf and frappe.db.exists("Print Format", pf):
                return pf
    except Exception:
        pass
    return default_fmt


@frappe.whitelist()
def download_student_record_pdf(doctype, name):
    """Stream a PDF for portal documents owned by the logged-in student."""
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)

    student_name = _get_student()
    if not student_name:
        frappe.throw(frappe._("No student record found for your account."),
                     frappe.PermissionError)

    allowed = {
        "Student Transcript":  {"student_field": "student", "filename": "Transcript"},
        "ID Card Generation":  {"student_field": "student", "filename": "ID_Card"},
        "Student Enrollment":  {"student_field": "student", "filename": "Enrollment"},
    }
    config = allowed.get(doctype)
    if not config:
        frappe.throw(frappe._("Document type not allowed."), frappe.PermissionError)

    owner = frappe.db.get_value(doctype, name, config["student_field"])
    if not owner or owner != student_name:
        frappe.throw(frappe._("Document not found or access denied."),
                     frappe.PermissionError)

    if doctype == "ID Card Generation":
        pdf_bytes = _generate_id_card_pdf(name)
    else:
        pdf_bytes = _generate_pdf(doctype, name, None)

    safe = name.replace("/", "-").replace(" ", "_")
    frappe.local.response.filename = f"{config['filename']}_{safe}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type = "pdf"


# Allowed Student Master fields that a student may download
_STUDENT_MASTER_DOWNLOADABLE_FIELDS = {
    "aadhaar_card",
    "pan_card",
    "passport",
    "pwd_certificate",
    "std_x_marksheet",
    "class_xii_marksheet",
    "ug_certificate",
    "ug_transcripts",
    "transfer_certificate",
    "entrance_exam_score_marksheet",
    "offer_letter",
    "phd_proposal",
    "posh_anti_ragging_declaration",
    "student_declaration",
    "parent_declaration",
}


@frappe.whitelist()
def download_student_master_document(fieldname):
    """Stream a file attached to the logged-in student's Student Master record."""
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)

    if fieldname not in _STUDENT_MASTER_DOWNLOADABLE_FIELDS:
        frappe.throw(frappe._("Document type not allowed."), frappe.PermissionError)

    student_name = _get_student()
    if not student_name:
        frappe.throw(frappe._("No student record found for your account."), frappe.PermissionError)

    file_url = frappe.db.get_value("Student Master", student_name, fieldname)
    if not file_url:
        frappe.throw(frappe._("Document not found."), frappe.DoesNotExistError)

    # Resolve the actual file doc to get the real path / content
    file_doc = frappe.db.get_value(
        "File",
        {"file_url": file_url, "attached_to_doctype": "Student Master", "attached_to_name": student_name},
        ["name", "file_url", "file_name", "is_private"],
        as_dict=True,
    )
    if not file_doc:
        # Fallback: try matching only by URL (covers public files not linked strictly)
        file_doc = frappe.db.get_value(
            "File",
            {"file_url": file_url},
            ["name", "file_url", "file_name", "is_private"],
            as_dict=True,
        )

    if not file_doc:
        # If no File doc, serve as redirect to the stored URL directly
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = file_url
        return

    # Stream the file via Frappe's file manager
    from frappe.utils.file_manager import get_file
    fname, content = get_file(file_doc.name)
    frappe.local.response.filename = fname
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"


@frappe.whitelist()
def get_portal_notifications():
	"""Return notification data for the bell icon and announcement ticker in the student portal."""
	if frappe.session.user == "Guest":
		return {"notifications": [], "count": 0, "urgent_count": 0}

	student_name = _get_student()
	if not student_name:
		return {"notifications": [], "count": 0, "urgent_count": 0}

	notifications = []

	try:
		student = frappe.get_doc("Student Master", student_name, ignore_permissions=True)
		today_str = nowdate()
		today_date = getdate(today_str)

		# ── 1. Student Announcements ───────────────────────────────
		priority_order = {"Urgent": 0, "Important": 1, "Normal": 2}
		priority_icon = {"Urgent": "warning", "Important": "priority_high", "Normal": "campaign"}

		all_records = frappe.get_all(
			"Student Announcement",
			filters=[["is_active", "=", 1], ["publish_date", "<=", today_str]],
			fields=["name", "title", "announcement_type", "priority", "publish_date", "expiry_date", "target_audience"],
			order_by="priority desc, publish_date desc",
			limit=30,
			ignore_permissions=True,
		)

		for r in all_records:
			if r.expiry_date and getdate(r.expiry_date) < today_date:
				continue

			if r.target_audience != "All Students":
				if r.target_audience == "Specific Programme(s)":
					targets = frappe.get_all(
						"Announcement Programme Target",
						filters={"parent": r.name},
						fields=["programme"],
						ignore_permissions=True,
					)
					if not any(t.programme == student.programme for t in targets):
						continue
				elif r.target_audience == "Specific Batch Year(s)":
					targets = frappe.get_all(
						"Announcement Batch Target",
						filters={"parent": r.name},
						fields=["batch_year"],
						ignore_permissions=True,
					)
					s_batch = str(student.batch_year or "")
					s_acyr  = str(student.academic_year or "")
					if not any(
						str(t.batch_year) == s_batch or (s_acyr and str(t.batch_year) == s_acyr)
						for t in targets
					):
						continue
				elif r.target_audience == "Specific Student(s)":
					targets = frappe.get_all(
						"Announcement Student Target",
						filters={"parent": r.name},
						fields=["student"],
						ignore_permissions=True,
					)
					if not any(t.student == student_name for t in targets):
						continue

			pub_date = ""
			if r.publish_date:
				try:
					pub_date = getdate(r.publish_date).strftime("%d %b %Y")
				except Exception:
					pub_date = str(r.publish_date)

			notifications.append({
				"type": "announcement",
				"category": r.announcement_type or "General",
				"priority": r.priority or "Normal",
				"title": r.title or "",
				"subtitle": pub_date,
				"icon": priority_icon.get(r.priority, "campaign"),
				"link": "/student-portal/announcements",
				"sort_key": priority_order.get(r.priority, 2),
			})

		# ── 2. Upcoming Exam Schedule ──────────────────────────────
		try:
			att_summaries = frappe.get_all(
				"Attendance Summary",
				filters={"student": student_name},
				fields=["course_offering", "course"],
				ignore_permissions=True,
			)
			enrolled_courses = list({s.course for s in att_summaries if s.course})

			if enrolled_courses:
				exam_schedules = frappe.get_all(
					"Exam Course Schedule",
					filters=[
						["course", "in", enrolled_courses],
						["exam_date", ">=", today_str],
					],
					fields=["course", "exam_date", "start_time", "venue"],
					order_by="exam_date asc",
					limit=5,
					ignore_permissions=True,
				)
				for es in exam_schedules:
					date_str = ""
					try:
						date_str = getdate(es.exam_date).strftime("%d %b %Y")
					except Exception:
						date_str = str(es.exam_date or "")
					notifications.append({
						"type": "exam_schedule",
						"category": "Exam Schedule",
						"priority": "Important",
						"title": f"Exam: {es.course}",
						"subtitle": f"{date_str}" + (f" | {es.venue}" if es.venue else ""),
						"icon": "event_note",
						"link": "/student-portal/exam-schedule",
						"sort_key": 1,
					})
		except Exception:
			pass

		# ── 3. Published Results ───────────────────────────────────
		try:
			published_results = frappe.get_all(
				"Student Result Publish",
				filters={"student": student_name, "is_published": 1},
				fields=["exam_plan", "term_gpa", "published_on"],
				order_by="published_on desc",
				limit=3,
				ignore_permissions=True,
			)
			for res in published_results:
				pub_on = ""
				try:
					if res.published_on:
						pub_on = getdate(res.published_on).strftime("%d %b %Y")
				except Exception:
					pass
				notifications.append({
					"type": "result",
					"category": "Exam Result",
					"priority": "Important",
					"title": f"Results Published: {res.exam_plan or 'Exam'}",
					"subtitle": (f"GPA: {res.term_gpa:.2f}" if res.term_gpa else "") + (f" | {pub_on}" if pub_on else ""),
					"icon": "assignment_turned_in",
					"link": "/student-portal/results",
					"sort_key": 1,
				})
		except Exception:
			pass

		# ── 4. FA / MFA Application Status ────────────────────────
		try:
			fa_apps = frappe.get_all(
				"FA MFA Application",
				filters={"student": student_name, "status": ["in", ["Approved", "Rejected"]]},
				fields=["name", "status", "application_type", "course"],
				order_by="modified desc",
				limit=5,
				ignore_permissions=True,
			)
			for app in fa_apps:
				notifications.append({
					"type": "fa_mfa",
					"category": "FA / MFA",
					"priority": "Important",
					"title": f"{app.application_type or 'Application'} {app.status}",
					"subtitle": app.course or "",
					"icon": "check_circle" if app.status == "Approved" else "cancel",
					"link": "/student-portal/attendance",
					"sort_key": 1,
				})
		except Exception:
			pass

		# ── 5. Condonation Status ──────────────────────────────────
		try:
			cond_apps = frappe.get_all(
				"Student Attendance Condonation",
				filters={"student": student_name, "final_status": ["in", ["Approved", "Rejected"]]},
				fields=["name", "final_status", "course_offering"],
				order_by="modified desc",
				limit=5,
				ignore_permissions=True,
			)
			for app in cond_apps:
				notifications.append({
					"type": "condonation",
					"category": "Condonation",
					"priority": "Important",
					"title": f"Condonation {app.final_status}",
					"subtitle": app.course_offering or "",
					"icon": "check_circle" if app.final_status == "Approved" else "cancel",
					"link": "/student-portal/attendance",
					"sort_key": 1,
				})
		except Exception:
			pass

		# ── 6. Leave Application Status ───────────────────────────────
		try:
			leave_apps = frappe.get_all(
				"Student Leave Applications",
				filters={"student": student_name, "status": ["in", ["Approved", "Rejected"]]},
				fields=["name", "status", "from_date", "to_date", "total_leave_days"],
				order_by="modified desc",
				limit=5,
				ignore_permissions=True,
			)
			for app in leave_apps:
				from_str = ""
				try:
					if app.from_date:
						from_str = getdate(app.from_date).strftime("%d %b")
				except Exception:
					pass
				notifications.append({
					"type": "leave",
					"category": "Leave Request",
					"priority": "Important",
					"title": f"Leave {app.status}: {app.name}",
					"subtitle": from_str + (f" · {int(app.total_leave_days or 0)} day(s)" if app.total_leave_days else ""),
					"icon": "check_circle" if app.status == "Approved" else "cancel",
					"link": "/student-portal/leave-request",
					"sort_key": 1,
				})
		except Exception:
			pass

		# ── 7. Upcoming Office Hours ───────────────────────────────
		try:
			att_sums = frappe.get_all(
				"Attendance Summary",
				filters={"student": student_name},
				fields=["course_offering"],
				ignore_permissions=True,
			)
			enrolled_co = list({s.course_offering for s in att_sums if s.course_offering})

			if enrolled_co:
				oh_sessions = frappe.get_all(
					"Office Hours Session",
					filters=[
						["session_date", ">=", today_str],
						["session_status", "=", "Scheduled"],
						["course_offering", "in", enrolled_co],
					],
					fields=["name", "session_date", "start_time", "course_offering"],
					order_by="session_date asc",
					limit=3,
					ignore_permissions=True,
				)
				for sess in oh_sessions:
					date_str = ""
					try:
						date_str = getdate(sess.session_date).strftime("%d %b %Y")
					except Exception:
						date_str = str(sess.session_date or "")
					notifications.append({
						"type": "office_hours",
						"category": "Office Hours",
						"priority": "Normal",
						"title": "Office Hours Available",
						"subtitle": f"{sess.course_offering} — {date_str}",
						"icon": "school",
						"link": "/student-portal/attendance",
						"sort_key": 2,
					})
		except Exception:
			pass

	except Exception as e:
		frappe.log_error(f"get_portal_notifications error: {e}", "Student Portal API")

	notifications.sort(key=lambda x: x.get("sort_key", 2))

	count = len(notifications)
	urgent_count = sum(1 for n in notifications if n.get("priority") == "Urgent")

	return {
		"notifications": notifications[:20],
		"count": count,
		"urgent_count": urgent_count,
	}


def _generate_id_card_pdf(card_name):
    """Build a landscape PDF with front + back ID card images, base64-embedded for Frappe Cloud."""
    import base64
    import mimetypes
    from frappe.utils.pdf import get_pdf
    from frappe.utils.file_manager import get_file
    from frappe.utils import get_url, nowdate, escape_html, formatdate

    card = frappe.db.get_value(
        "ID Card Generation",
        card_name,
        [
            "front_id_image", "back_id_image", "student_name",
            "card_status", "issue_date", "expiry_date", "academic_year",
            "cancellation_reason",
        ],
        as_dict=True,
    )
    if not card:
        frappe.throw(frappe._("ID Card record not found."))

    if card.card_status in ("Cancelled", "Expired"):
        frappe.throw(
            frappe._(f"This ID card is {card.card_status.lower()} and cannot be downloaded."),
            frappe.PermissionError,
        )

    def _embed_image(file_url):
        """Return (data-URI, is_ok). Falls back to absolute URL on failure."""
        if not file_url:
            return None
        try:
            file_doc_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
            if file_doc_name:
                fname, content = get_file(file_doc_name)
                mime = mimetypes.guess_type(fname)[0] or "image/png"
                b64 = base64.b64encode(content).decode()
                return f"data:{mime};base64,{b64}"
        except Exception:
            pass
        return get_url(file_url)

    front_src = _embed_image(card.front_id_image)
    back_src  = _embed_image(card.back_id_image)

    if not front_src and not back_src:
        frappe.throw(
            frappe._("ID card images have not been generated yet."),
            frappe.ValidationError,
        )

    def _card_col(src, label):
        if not src:
            return ""
        return (
            f'<td class="card-col">'
            f'  <div class="card-label">{label}</div>'
            f'  <div class="card-img-wrap">'
            f'    <img src="{src}" alt="{label}">'
            f'  </div>'
            f'</td>'
        )

    issue_str  = formatdate(card.issue_date,  "dd MMM yyyy") if card.issue_date  else "—"
    expiry_str = formatdate(card.expiry_date, "dd MMM yyyy") if card.expiry_date else "—"
    name_safe  = escape_html(card.student_name or card_name)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{ size: A4 landscape; margin: 18mm 16mm; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: 'Helvetica Neue', Arial, sans-serif;
  background: #fff;
  color: #222;
  font-size: 12px;
}}

/* ── Header ── */
.hdr {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 3px solid #1a3c6e;
  margin-bottom: 18px;
}}
.hdr-left {{ }}
.hdr-title {{
  font-size: 20px;
  font-weight: 800;
  color: #1a3c6e;
  letter-spacing: -0.3px;
}}
.hdr-sub {{
  font-size: 12px;
  color: #666;
  margin-top: 2px;
}}
.hdr-meta {{
  text-align: right;
  font-size: 11px;
  color: #888;
  line-height: 1.8;
}}
.hdr-meta strong {{ color: #333; }}

/* ── Info strip ── */
.info-strip {{
  display: flex;
  gap: 32px;
  background: #f4f7fb;
  border: 1px solid #dce5f0;
  border-radius: 8px;
  padding: 10px 18px;
  margin-bottom: 22px;
}}
.info-item {{ }}
.info-label {{
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: #999;
  font-weight: 700;
}}
.info-val {{
  font-size: 13px;
  font-weight: 700;
  color: #1a3c6e;
  margin-top: 1px;
}}

/* ── Cards ── */
.cards-table {{
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}}
.card-col {{
  width: 50%;
  vertical-align: top;
  padding: 0 12px;
}}
.card-col:first-child {{ padding-left: 0; border-right: 1px dashed #ddd; }}
.card-col:last-child  {{ padding-right: 0; }}
.card-label {{
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: .12em;
  color: #888;
  margin-bottom: 10px;
  text-align: center;
}}
.card-img-wrap {{
  text-align: center;
  background: #f8fafc;
  border-radius: 12px;
  padding: 12px;
  border: 1px solid #e8eef5;
}}
.card-img-wrap img {{
  max-width: 100%;
  max-height: 200px;
  border-radius: 10px;
  box-shadow: 0 3px 14px rgba(0,0,0,.14);
  display: inline-block;
}}

/* ── Footer ── */
.footer {{
  margin-top: 22px;
  padding-top: 8px;
  border-top: 1px solid #e5e5e5;
  display: flex;
  justify-content: space-between;
  font-size: 9px;
  color: #bbb;
}}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-left">
    <div class="hdr-title">Student ID Card</div>
    <div class="hdr-sub">{name_safe}</div>
  </div>
  <div class="hdr-meta">
    <div><strong>Card ID</strong> {escape_html(card_name)}</div>
    <div><strong>Status</strong> {escape_html(card.card_status or 'Generated')}</div>
  </div>
</div>

<div class="info-strip">
  <div class="info-item">
    <div class="info-label">Card Holder</div>
    <div class="info-val">{name_safe}</div>
  </div>
  <div class="info-item">
    <div class="info-label">Issue Date</div>
    <div class="info-val">{issue_str}</div>
  </div>
  <div class="info-item">
    <div class="info-label">Valid Until</div>
    <div class="info-val">{expiry_str}</div>
  </div>
  {f'<div class="info-item"><div class="info-label">Academic Year</div><div class="info-val">{escape_html(card.academic_year)}</div></div>' if card.academic_year else ''}
</div>

<table class="cards-table">
  <tr>
    {_card_col(front_src, "Front")}
    {_card_col(back_src,  "Back")}
  </tr>
</table>

<div class="footer">
  <span>Downloaded from Student Portal &mdash; {nowdate()}</span>
  <span>Card ID: {escape_html(card_name)}</span>
</div>

</body>
</html>"""

    return get_pdf(html, {"orientation": "Landscape"})


def _generate_orphan_receipt_pdf(receipt_name):
    """Generate a receipt PDF from Fee Receipt fields for receipts with no Fee Payment link."""
    from frappe.utils.pdf import get_pdf
    from frappe.utils import formatdate, fmt_money

    r = frappe.db.get_value(
        "Fee Receipt", receipt_name,
        ["student", "student_name", "registration_id", "programme",
         "academic_year", "receipt_date", "amount", "payment_mode",
         "reference_number", "bank_name", "transaction_date", "received_by"],
        as_dict=True,
    ) or {}

    def _esc(v):
        return frappe.utils.escape_html(str(v or "—"))

    amount_fmt = "₹ {:,.2f}".format(frappe.utils.flt(r.get("amount") or 0))
    date_fmt   = formatdate(r.get("receipt_date"), "dd MMM yyyy") if r.get("receipt_date") else "—"
    txn_date   = formatdate(r.get("transaction_date"), "dd MMM yyyy") if r.get("transaction_date") else "—"

    # Resolve institution name
    try:
        inst_name = frappe.db.get_single_value("System Settings", "site_name") or "Institution"
    except Exception:
        inst_name = "Institution"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 13px; color: #1e293b; margin: 0; padding: 32px; }}
  .hdr {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #0f2a5c; padding-bottom: 16px; margin-bottom: 24px; }}
  .hdr-title {{ font-size: 22px; font-weight: 700; color: #0f2a5c; }}
  .hdr-sub {{ font-size: 12px; color: #64748b; margin-top: 2px; }}
  .receipt-no {{ text-align: right; }}
  .receipt-no .label {{ font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }}
  .receipt-no .val {{ font-size: 16px; font-weight: 700; color: #0f2a5c; }}
  .section {{ margin-bottom: 20px; }}
  .section-title {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; margin-bottom: 10px; }}
  .row {{ display: flex; margin-bottom: 6px; }}
  .row .lbl {{ width: 180px; color: #64748b; flex-shrink: 0; }}
  .row .val {{ font-weight: 600; color: #1e293b; }}
  .amount-box {{ background: #f0fdf4; border: 1.5px solid #86efac; border-radius: 8px; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; margin: 20px 0; }}
  .amount-label {{ font-size: 13px; font-weight: 700; color: #166534; text-transform: uppercase; letter-spacing: 0.06em; }}
  .amount-val {{ font-size: 22px; font-weight: 800; color: #14532d; }}
  .footer {{ margin-top: 40px; border-top: 1px solid #e2e8f0; padding-top: 12px; font-size: 11px; color: #94a3b8; display: flex; justify-content: space-between; }}
</style>
</head>
<body>
<div class="hdr">
  <div>
    <div class="hdr-title">{_esc(inst_name)}</div>
    <div class="hdr-sub">Fee Payment Receipt</div>
  </div>
  <div class="receipt-no">
    <div class="label">Receipt No.</div>
    <div class="val">{_esc(receipt_name)}</div>
  </div>
</div>

<div class="section">
  <div class="section-title">Student Details</div>
  <div class="row"><span class="lbl">Student Name</span><span class="val">{_esc(r.get("student_name"))}</span></div>
  <div class="row"><span class="lbl">Student ID</span><span class="val">{_esc(r.get("registration_id"))}</span></div>
  <div class="row"><span class="lbl">Programme</span><span class="val">{_esc(r.get("programme"))}</span></div>
  <div class="row"><span class="lbl">Academic Year</span><span class="val">{_esc(r.get("academic_year"))}</span></div>
</div>

<div class="amount-box">
  <span class="amount-label">Amount Paid</span>
  <span class="amount-val">{_esc(amount_fmt)}</span>
</div>

<div class="section">
  <div class="section-title">Payment Details</div>
  <div class="row"><span class="lbl">Receipt Date</span><span class="val">{_esc(date_fmt)}</span></div>
  <div class="row"><span class="lbl">Payment Mode</span><span class="val">{_esc(r.get("payment_mode"))}</span></div>
  {f'<div class="row"><span class="lbl">Reference / TXN No.</span><span class="val">{_esc(r.get("reference_number"))}</span></div>' if r.get("reference_number") else ""}
  {f'<div class="row"><span class="lbl">Transaction Date</span><span class="val">{_esc(txn_date)}</span></div>' if r.get("transaction_date") else ""}
  {f'<div class="row"><span class="lbl">Bank</span><span class="val">{_esc(r.get("bank_name"))}</span></div>' if r.get("bank_name") else ""}
</div>

<div class="footer">
  <span>This is a computer-generated receipt and does not require a physical signature.</span>
  <span>Generated: {formatdate(frappe.utils.today(), "dd MMM yyyy")}</span>
</div>
</body>
</html>"""

    return get_pdf(html)


def _generate_pdf(doctype, name, print_format):
    """Generate a PDF by temporarily running as Administrator.

    frappe.set_user() corrupts three session fields that must all be restored:
      - session.sid  → overwritten with username string (breaks cookie lookup)
      - session.data → cleared to empty _dict() (loses all session payload)
      - session.user → restored by set_user(original_user), but data/sid are not
    We snapshot all three before escalating and restore them in the finally block.
    """
    from frappe.utils.pdf import get_pdf
    import copy as _copy

    sess            = frappe.local.session
    original_user   = sess.user
    original_sid    = getattr(sess, "sid",  None)
    original_data   = _copy.deepcopy(getattr(sess, "data", frappe._dict()))

    try:
        frappe.set_user("Administrator")
        html = frappe.get_print(
            doctype=doctype,
            name=name,
            print_format=print_format,
            as_pdf=False,
            no_letterhead=0,
        )
        return get_pdf(html)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_generate_pdf")
        frappe.throw(
            frappe._("Could not generate the document. Please try again or contact support."),
            frappe.ValidationError,
        )
    finally:
        # set_user(original_user) restores .user but clears .sid and .data again.
        frappe.set_user(original_user)
        if original_sid:
            sess.sid  = original_sid
        sess.data = original_data
 

@frappe.whitelist()
def initiate_re_exam_registration(exam_plan, course):
    """Create or retrieve a Re Exam Registration record for the logged-in student."""
    if frappe.session.user == "Guest":
        frappe.throw("Not allowed.", frappe.AuthenticationError)

    user = frappe.session.user
    student_name = (
        frappe.db.get_value("Student Master", {"user": user}, "name")
        or frappe.db.get_value("Student Master", {"email": user}, "name")
        or frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    )
    if not student_name:
        frappe.throw("No student record found for this account.")

    setting = frappe.db.get_value(
        "Re Exam Course Setting",
        {"exam_plan": exam_plan, "course": course},
        ["name", "re_exam_fee", "deadline_from", "deadline_to"],
        as_dict=True,
    )
    if not setting:
        frappe.throw("Re-exam registration is not open for this course yet.")

    today = frappe.utils.today()
    if setting.get("deadline_to") and str(setting["deadline_to"]) < today:
        frappe.throw("The registration deadline for this course has passed.")

    existing = frappe.db.get_value(
        "Re Exam Registration",
        {"student": student_name, "exam_plan": exam_plan, "course": course},
        "name",
    )
    if existing:
        return {"name": existing, "message": "You are already registered for this re-examination."}

    course_offering = frappe.db.get_value(
        "Course Schema Assignment", {"exam_plan": exam_plan, "course": course}, "course_offering"
    )
    if not course_offering:
        frappe.throw("No Course Offering found for this course/exam plan. Contact administration.")

    doc = frappe.new_doc("Re Exam Registration")
    doc.student    = student_name
    doc.exam_plan  = exam_plan
    doc.course     = course
    doc.course_offering = course_offering
    doc.re_exam_fee = setting.get("re_exam_fee") or 0
    doc.status         = "Registered"
    doc.payment_status = "Pending"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    fee_msg = f"Fee of ₹{doc.re_exam_fee:,.0f} is payable at the fees counter." if doc.re_exam_fee else ""
    return {"name": doc.name, "message": fee_msg}


def check_improvement_cgpa_eligibility(student_name, exam_plan):
    """Throw unless the student's published Cumulative GPA for this exam plan
    is below Examination Settings.max_cgpa_for_improvement. Enforced
    server-side here (not just hidden in the UI) since this is the actual
    gate on who may register/pay for an Improvement Exam."""
    cgpa = frappe.db.get_value(
        "Student Result Publish",
        {"student": student_name, "exam_plan": exam_plan, "is_published": 1},
        "cumulative_gpa",
    )
    if not cgpa:
        frappe.throw("Your result for this exam plan must be published before you can apply for Improvement Exam.")

    max_cgpa = flt(frappe.db.get_single_value("Examination Settings", "max_cgpa_for_improvement") or 3.0)
    if flt(cgpa) >= max_cgpa:
        frappe.throw(
            f"Improvement Exam is only open to students with a CGPA below {max_cgpa:g}. "
            f"Your current CGPA is {flt(cgpa):g}."
        )


@frappe.whitelist()
def initiate_improvement_exam_registration(exam_plan, course):
    """Create or retrieve an Improvement Exam Registration for free/counter-payment flow."""
    if frappe.session.user == "Guest":
        frappe.throw("Not allowed.", frappe.AuthenticationError)

    user = frappe.session.user
    student_name = (
        frappe.db.get_value("Student Master", {"user": user}, "name")
        or frappe.db.get_value("Student Master", {"email": user}, "name")
        or frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    )
    if not student_name:
        frappe.throw("No student record found for this account.")

    check_improvement_cgpa_eligibility(student_name, exam_plan)

    setting = frappe.db.get_value(
        "Improvement Exam Course Setting",
        {"exam_plan": exam_plan, "course": course},
        ["name", "improvement_fee", "deadline_from", "deadline_to", "registration_limit"],
        as_dict=True,
    )
    if not setting:
        frappe.throw("Improvement exam registration is not open for this course yet.")

    today = frappe.utils.today()
    if setting.get("deadline_to") and str(setting["deadline_to"]) < today:
        frappe.throw("The registration deadline for this course has passed.")

    existing = frappe.db.get_value(
        "Improvement Exam Registration",
        {"student": student_name, "exam_plan": exam_plan, "course": course, "status": ["!=", "Cancelled"]},
        "name",
    )
    if existing:
        return {"name": existing, "message": "You are already registered for this improvement examination."}

    if setting.get("registration_limit"):
        count_row = frappe.db.sql(
            "SELECT COUNT(*) FROM `tabImprovement Exam Registration` WHERE exam_plan=%s AND course=%s AND status!='Cancelled'",
            (exam_plan, course),
        )
        current_count = int(count_row[0][0]) if count_row else 0
        if current_count >= int(setting["registration_limit"]):
            frappe.throw("Registration limit has been reached for this improvement exam.")

    course_offering = frappe.db.get_value(
        "Course Schema Assignment", {"exam_plan": exam_plan, "course": course}, "course_offering"
    )
    if not course_offering:
        frappe.throw("No Course Offering found for this course/exam plan. Contact administration.")

    doc = frappe.new_doc("Improvement Exam Registration")
    doc.student         = student_name
    doc.exam_plan       = exam_plan
    doc.course          = course
    doc.course_offering = course_offering
    doc.improvement_fee = setting.get("improvement_fee") or 0
    doc.status          = "Registered"
    doc.payment_status  = "Pending"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    fee_msg = f"Fee of ₹{doc.improvement_fee:,.0f} is payable at the fees counter." if doc.improvement_fee else ""
    return {"name": doc.name, "message": fee_msg}


# ─────────────────────────────────────────────────────────────────────────────
#  Venue Booking (Student Portal)
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def check_room_availability(room, start_datetime, end_datetime):
    """Return conflicting Pending/Approved bookings for the venue in the given time window."""
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)
    if not room or not start_datetime or not end_datetime:
        return {"conflicts": []}
    conflicts = frappe.db.sql("""
        SELECT name, event_name, start_datetime, end_datetime, status
        FROM `tabVenue Booking`
        WHERE venue = %(venue)s
          AND docstatus IN (0, 1)
          AND status IN ('Pending', 'Approved')
          AND start_datetime < %(end)s
          AND end_datetime   > %(start)s
        ORDER BY start_datetime ASC
        LIMIT 5
    """, {"venue": room, "start": start_datetime, "end": end_datetime}, as_dict=True)
    return {"conflicts": conflicts}


@frappe.whitelist()
def get_rooms_for_type(venue_type):
    """Return available venues for the given venue type."""
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)
    if not venue_type:
        return []
    venues = frappe.get_all(
        "Venue Master",
        filters={"venue_type": venue_type, "is_active": 1},
        fields=["name", "venue_name_or_number as room_name", "capacity as seating_capacity", "building as block", "floor"],
        order_by="venue_name_or_number asc",
        ignore_permissions=True,
    )
    return venues


@frappe.whitelist()
def submit_venue_booking(
    event_name=None, venue_type=None, room=None, start_datetime=None, end_datetime=None,
    reason=None, expected_attendees=None, attachment=None
):
    """Create a Venue Booking on behalf of the logged-in student."""
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)

    student_name = _get_student()
    if not student_name:
        frappe.throw("No student record found for your account.")

    if not event_name or not venue_type or not room or not start_datetime or not end_datetime:
        frappe.throw("Please fill all required fields.")

    user = frappe.session.user
    full_name = frappe.db.get_value("User", user, "full_name") or user

    doc = frappe.get_doc({
        "doctype":            "Venue Booking",
        "event_name":         event_name,
        "venue_type":         venue_type,
        "venue":              room,
        "start_datetime":     start_datetime,
        "end_datetime":       end_datetime,
        "reason":             reason or "",
        "status":             "Pending Allotment",
        "student":            student_name,
        "requester_type":     "Student",
        "requester_name":     full_name,
        "expected_attendees": cint(expected_attendees) if expected_attendees else None,
        "attachment":         attachment or None,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name}


@frappe.whitelist()
def request_venue_swap(booking_name, requested_room, reason=None):
    """Student/Faculty raises a swap request to move their booking to a different venue."""
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)

    student_name = _get_student()
    if not student_name:
        frappe.throw("No student record found for your account.")

    booking = frappe.get_doc("Venue Booking", booking_name, ignore_permissions=True)

    if booking.student != student_name and booking.owner != frappe.session.user:
        frappe.throw("You can only request a swap for your own bookings.", frappe.PermissionError)

    if booking.status not in ("Pending Allotment", "Allotted"):
        frappe.throw("Swap requests can only be raised for bookings Pending Allotment or Allotted.")

    if booking.swap_requested:
        frappe.throw("A swap request is already pending for this booking.")

    if not requested_room:
        frappe.throw("Please select a venue to swap to.")

    if requested_room == booking.venue:
        frappe.throw("The requested venue is the same as the current venue.")

    requester_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

    frappe.db.set_value("Venue Booking", booking_name, {
        "swap_requested":       1,
        "swap_requested_venue": requested_room,
        "swap_request_reason":  reason or "",
        "swap_status":          "Pending",
        "swap_admin_remarks":   "",
    }, update_modified=False)

    _insert_swap_log(
        booking_name  = booking_name,
        from_room     = booking.venue,
        to_room       = requested_room,
        swap_status   = "Pending",
        requested_by  = requester_name,
        requested_on  = frappe.utils.now(),
        swap_reason   = reason or "",
        decided_by    = "",
        decided_on    = None,
        admin_remarks = "",
    )
    frappe.db.commit()

    _notify_admin_swap_request(booking_name, requested_room, reason)
    return {"status": "requested"}


@frappe.whitelist()
def cancel_venue_swap_request(booking_name):
    """Student withdraws their pending swap request."""
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)

    student_name = _get_student()
    if not student_name:
        frappe.throw("No student record found for your account.")

    booking = frappe.get_doc("Venue Booking", booking_name, ignore_permissions=True)

    if booking.student != student_name and booking.owner != frappe.session.user:
        frappe.throw("You can only cancel your own swap requests.", frappe.PermissionError)

    if not booking.swap_requested or booking.swap_status != "Pending":
        frappe.throw("No pending swap request found for this booking.")

    frappe.db.set_value("Venue Booking", booking_name, {
        "swap_requested":       0,
        "swap_requested_venue": "",
        "swap_request_reason":  "",
        "swap_status":          "",
        "swap_admin_remarks":   "",
    }, update_modified=False)

    # Mark the latest Pending log entry as Withdrawn
    frappe.db.sql("""
        UPDATE `tabVenue Swap Log`
        SET swap_status = 'Withdrawn',
            decided_on  = %(now)s,
            decided_by  = %(by)s,
            modified    = %(now)s
        WHERE parent = %(parent)s
          AND swap_status = 'Pending'
        ORDER BY idx DESC
        LIMIT 1
    """, {"parent": booking_name, "now": frappe.utils.now(),
          "by": frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user})
    frappe.db.commit()
    return {"status": "cancelled"}


@frappe.whitelist()
def get_swap_log(booking_name):
    """Return swap request history for a given booking."""
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)
    rows = frappe.db.sql("""
        SELECT from_room, to_room, swap_status, requested_on, requested_by,
               decided_on, decided_by, swap_reason, admin_remarks
        FROM `tabVenue Swap Log`
        WHERE parent = %(parent)s
        ORDER BY idx ASC
    """, {"parent": booking_name}, as_dict=True)
    return rows


def _insert_swap_log(booking_name, from_room, to_room, swap_status,
                     requested_by, requested_on, swap_reason="",
                     decided_by="", decided_on=None, admin_remarks=""):
    """Insert a row into tabVenue Swap Log for the given booking."""
    next_idx_row = frappe.db.sql(
        "SELECT COALESCE(MAX(idx),0)+1 FROM `tabVenue Swap Log` WHERE parent=%s",
        booking_name
    )
    next_idx = next_idx_row[0][0] if next_idx_row else 1
    now = frappe.utils.now()
    frappe.db.sql("""
        INSERT INTO `tabVenue Swap Log`
            (name, parent, parenttype, parentfield, idx,
             from_room, to_room, swap_status, requested_on, requested_by,
             decided_on, decided_by, swap_reason, admin_remarks,
             creation, modified, modified_by, owner, docstatus)
        VALUES
            (%(name)s, %(parent)s, 'Venue Booking', 'swap_log', %(idx)s,
             %(from_room)s, %(to_room)s, %(swap_status)s, %(requested_on)s, %(requested_by)s,
             %(decided_on)s, %(decided_by)s, %(swap_reason)s, %(admin_remarks)s,
             %(now)s, %(now)s, %(user)s, %(user)s, 0)
    """, {
        "name":         frappe.generate_hash(length=10),
        "parent":       booking_name,
        "idx":          next_idx,
        "from_room":    from_room or "",
        "to_room":      to_room or "",
        "swap_status":  swap_status,
        "requested_on": requested_on or now,
        "requested_by": requested_by or "",
        "decided_on":   decided_on,
        "decided_by":   decided_by or "",
        "swap_reason":  swap_reason or "",
        "admin_remarks":admin_remarks or "",
        "now":          now,
        "user":         frappe.session.user,
    })


@frappe.whitelist()
def backfill_swap_log(booking_name):
    """Backfill a log entry for a booking that has a swap_requested flag but no log row yet.
    Safe to call multiple times — skips if a log row already exists."""
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)

    bk = frappe.db.get_value(
        "Venue Booking", booking_name,
        ["swap_requested", "swap_status", "swap_requested_venue",
         "swap_request_reason", "venue", "owner", "requester_name"],
        as_dict=True
    )
    if not bk or not bk.swap_requested:
        return {"skipped": "no active swap request"}

    existing = frappe.db.sql(
        "SELECT name FROM `tabVenue Swap Log` WHERE parent=%s LIMIT 1", booking_name
    )
    if existing:
        return {"skipped": "log already exists"}

    requester_name = (
        frappe.db.get_value("User", bk.owner, "full_name") or bk.requester_name or bk.owner
    )
    _insert_swap_log(
        booking_name  = booking_name,
        from_room     = bk.venue,
        to_room       = bk.swap_requested_venue or "",
        swap_status   = bk.swap_status or "Pending",
        requested_by  = requester_name,
        requested_on  = frappe.utils.now(),
        swap_reason   = bk.swap_request_reason or "",
    )
    frappe.db.commit()
    return {"backfilled": True}


def _notify_admin_swap_request(booking_name, requested_room, reason):
    """Email admins when a swap request is raised, including info about the conflicting booking."""
    try:
        booking = frappe.db.get_value(
            "Venue Booking", booking_name,
            ["event_name", "venue", "venue_type", "start_datetime", "end_datetime",
             "requester_name", "requester_type"],
            as_dict=True,
        )
        if not booking:
            return

        req_room_name = frappe.db.get_value("Venue Master", requested_room, "venue_name_or_number") or requested_room

        # Find who currently has the requested venue booked in this time window
        conflict_rows = frappe.db.sql("""
            SELECT name, event_name, requester_name, start_datetime, end_datetime, status
            FROM `tabVenue Booking`
            WHERE venue = %(venue)s
              AND docstatus IN (0, 1)
              AND status IN ('Pending', 'Approved')
              AND start_datetime < %(end)s
              AND end_datetime   > %(start)s
            LIMIT 3
        """, {"venue": requested_room,
              "start": booking.start_datetime,
              "end":   booking.end_datetime}, as_dict=True)

        conflict_html = ""
        if conflict_rows:
            rows = "".join(
                f'<tr><td style="padding:4px 12px;">{r.name}</td>'
                f'<td style="padding:4px 12px;">{r.event_name}</td>'
                f'<td style="padding:4px 12px;">{r.requester_name}</td>'
                f'<td style="padding:4px 12px;">{r.status}</td>'
                f'<td style="padding:4px 12px;">{r.start_datetime} → {r.end_datetime}</td></tr>'
                for r in conflict_rows
            )
            conflict_html = f"""
<p style="margin-top:16px;"><strong>⚠ The requested room already has conflicting bookings — please contact those in-charges:</strong></p>
<table style="border-collapse:collapse;font-size:13px;width:100%;margin-top:8px;">
  <thead style="background:#fef3c7;">
    <tr>
      <th style="padding:6px 12px;text-align:left;">Ref</th>
      <th style="padding:6px 12px;text-align:left;">Event</th>
      <th style="padding:6px 12px;text-align:left;">Booked By</th>
      <th style="padding:6px 12px;text-align:left;">Status</th>
      <th style="padding:6px 12px;text-align:left;">Time</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>"""

        admin_roles = ["slcm_Registrar", "System Manager"]
        admin_emails = []
        for role in admin_roles:
            users = frappe.get_all("Has Role",
                filters={"role": role, "parenttype": "User"},
                fields=["parent"], ignore_permissions=True)
            for u in users:
                email = frappe.db.get_value("User", u.parent, "email")
                if email and email not in admin_emails:
                    admin_emails.append(email)

        if not admin_emails:
            return

        subject = f"[Venue Booking] Swap Request: {booking.event_name} → {req_room_name}"
        message = f"""
<p>A venue swap request has been submitted and requires your review.</p>
<table style="border-collapse:collapse;width:100%;font-size:14px;">
  <tr><td style="padding:6px 12px;font-weight:600;color:#555;width:180px;">Booking Ref</td><td style="padding:6px 12px;">{booking_name}</td></tr>
  <tr style="background:#f7f7f7;"><td style="padding:6px 12px;font-weight:600;color:#555;">Requested By</td><td style="padding:6px 12px;">{booking.requester_name} ({booking.requester_type})</td></tr>
  <tr><td style="padding:6px 12px;font-weight:600;color:#555;">Event / Purpose</td><td style="padding:6px 12px;">{booking.event_name}</td></tr>
  <tr style="background:#f7f7f7;"><td style="padding:6px 12px;font-weight:600;color:#555;">Current Room</td><td style="padding:6px 12px;">{booking.venue}</td></tr>
  <tr><td style="padding:6px 12px;font-weight:600;color:#555;">Requested Room</td><td style="padding:6px 12px;font-weight:700;color:#1d4ed8;">{req_room_name} ({requested_room})</td></tr>
  <tr style="background:#f7f7f7;"><td style="padding:6px 12px;font-weight:600;color:#555;">Time Slot</td><td style="padding:6px 12px;">{booking.start_datetime} → {booking.end_datetime}</td></tr>
  {f'<tr><td style="padding:6px 12px;font-weight:600;color:#555;">Swap Reason</td><td style="padding:6px 12px;">{reason}</td></tr>' if reason else ""}
</table>
{conflict_html}
<p style="margin-top:16px;">Please log in to <strong>approve or reject</strong> this swap request from the Venue Booking record.</p>
"""
        frappe.sendmail(recipients=admin_emails, subject=subject, message=message, now=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Venue Swap Request — Admin Notification Error")


@frappe.whitelist()
def update_venue_booking_attachment(booking_name, attachment):
    """Update the attachment on a student's own Pending venue booking."""
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)

    student_name = _get_student()
    if not student_name:
        frappe.throw("No student record found for your account.")

    booking = frappe.get_doc("Venue Booking", booking_name, ignore_permissions=True)

    if booking.student != student_name and booking.owner != frappe.session.user:
        frappe.throw("You can only update your own bookings.", frappe.PermissionError)

    if booking.status != "Pending Allotment":
        frappe.throw("Attachments can only be updated on bookings Pending Allotment.")

    frappe.db.set_value("Venue Booking", booking_name, "attachment", attachment, update_modified=False)
    frappe.db.commit()
    return {"status": "updated"}


@frappe.whitelist()
def cancel_venue_booking(booking_name):
    """Cancel the student's own Pending venue booking."""
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)

    student_name = _get_student()
    if not student_name:
        frappe.throw("No student record found for your account.")

    booking = frappe.get_doc("Venue Booking", booking_name, ignore_permissions=True)

    if booking.student != student_name:
        frappe.throw("You can only cancel your own bookings.", frappe.PermissionError)

    if booking.status != "Pending Allotment":
        frappe.throw("Only bookings Pending Allotment can be cancelled.")

    frappe.db.set_value("Venue Booking", booking_name, "status", "Cancelled")
    frappe.db.commit()
    return {"status": "Cancelled"}


@frappe.whitelist()
def bulk_update_venue_booking_status(booking_names, status, admin_remarks=""):
    """Bulk update venue booking status — admin only."""
    allowed_roles = {"System Manager", "Administrator", "slcm_Registrar"}
    if not allowed_roles.intersection(set(frappe.get_roles())):
        frappe.throw("Not permitted.", frappe.PermissionError)

    valid_statuses = {"Pending Allotment", "Allotted", "Rejected", "Cancelled"}
    if status not in valid_statuses:
        frappe.throw(f"Invalid status: {status}")

    if isinstance(booking_names, str):
        import json
        booking_names = json.loads(booking_names)

    replied_by = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    replied_on = frappe.utils.now()

    updated = 0
    for name in booking_names:
        try:
            values = {"status": status, "replied_by": replied_by, "replied_on": replied_on}
            if admin_remarks:
                values["admin_remarks"] = admin_remarks
            frappe.db.set_value("Venue Booking", name, values)
            updated += 1
        except Exception:
            pass

    frappe.db.commit()
    return {"updated": updated, "status": status}

@frappe.whitelist()
def add_guardian(first_name, last_name, relation, phone, email, occupation):
    student_name = _get_student()
    if not student_name:
        frappe.throw("Student not found")

    student = frappe.get_doc("Student Master", student_name)
    student.append("parents", {
        "first_name": first_name,
        "last_name": last_name,
        "relation": relation,
        "phone": phone,
        "email": email,
        "occupation": occupation
    })
    
    student.flags.ignore_permissions = True
    student.save()
    return {"status": "success"}


BANK_DETAIL_FIELDS = (
    "savings_account_number", "savings_account_holder_name", "savings_bank_name",
    "savings_branch_name", "savings_ifsc_code", "availed_education_loan",
    "education_loan_scheme", "other_loan_scheme", "loan_account_number",
    "loan_account_holder_name", "loan_bank_name", "loan_branch_name", "loan_ifsc_code",
)


@frappe.whitelist(methods=["POST"])
def submit_bank_details(**kwargs):
    """One-time submission of savings / education-loan bank details from the Student Portal.

    Once submitted the details are locked; the office can re-open them by unchecking
    "Bank Details Submitted by Student" on the Student Master.
    """
    student_name = _get_student()
    if not student_name:
        frappe.throw(_("Student not found"))

    student = frappe.get_doc("Student Master", student_name)
    if student.bank_details_submitted:
        frappe.throw(_("Bank details have already been submitted. Please contact the administration office to make changes."))

    values = {f: (str(kwargs.get(f) or "")).strip() for f in BANK_DETAIL_FIELDS}

    required = {
        "savings_account_number": _("Savings Bank Account Number"),
        "savings_account_holder_name": _("Name of the Account Holder"),
        "savings_bank_name": _("Name of the Bank"),
        "savings_branch_name": _("Name of the Branch"),
        "savings_ifsc_code": _("IFSC Code"),
        "availed_education_loan": _("Availed Education Loan?"),
    }
    if values["availed_education_loan"] not in ("Yes", "No"):
        values["availed_education_loan"] = ""
    if values["availed_education_loan"] == "Yes":
        required.update({
            "education_loan_scheme": _("Loan Scheme"),
            "loan_account_number": _("Loan Account Number"),
            "loan_account_holder_name": _("Loan Account Holder Name"),
            "loan_bank_name": _("Loan Bank Name"),
            "loan_branch_name": _("Loan Branch Name"),
            "loan_ifsc_code": _("Loan IFSC Code"),
        })
        if values["education_loan_scheme"] not in ("PM Vidyalaxmi", "Others"):
            values["education_loan_scheme"] = ""
        if values["education_loan_scheme"] == "Others":
            required["other_loan_scheme"] = _("Specify Other Scheme")

    missing = [label for f, label in required.items() if not values[f]]
    if missing:
        frappe.throw(_("Please fill: {0}").format(", ".join(missing)))

    # Bank fields are masked, and Frappe resets masked fields on save for users without
    # mask permission (students), so validate via the controller and write them directly.
    student.update(values)
    student.validate_bank_details(reveal_owner=False)
    updates = {f: student.get(f) or None for f in BANK_DETAIL_FIELDS}
    updates.update(bank_details_submitted=1, bank_details_submitted_on=frappe.utils.now_datetime())

    # Optional passbook uploads (loan passbook only when a loan was availed)
    passbooks = {"savings_passbook": kwargs.get("savings_passbook")}
    if values["availed_education_loan"] == "Yes":
        passbooks["loan_passbook"] = kwargs.get("loan_passbook")
    for field, file_url in passbooks.items():
        if file_url:
            updates[field] = _claim_passbook_file(student_name, field, file_url)

    frappe.db.set_value("Student Master", student_name, updates)
    student.add_comment("Info", _("Bank details submitted by the student from the Student Portal."))
    return {"status": "success"}


PASSBOOK_FIELDS = {"savings": "savings_passbook", "loan": "loan_passbook"}
PASSBOOK_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")


def _claim_passbook_file(student_name, fieldname, file_url):
    """Attach a passbook the student just uploaded (private, owned by them) to their Student Master."""
    file_url = (file_url or "").strip()
    f = frappe.db.get_value(
        "File",
        {"file_url": file_url, "owner": frappe.session.user},
        ["name", "is_private", "attached_to_name", "file_name"],
        as_dict=True,
    )
    if not f:
        frappe.throw(_("The passbook upload could not be found. Please upload the file again."))
    if not f.is_private:
        frappe.throw(_("Passbook files must be uploaded privately. Please upload the file again."))
    if f.attached_to_name and f.attached_to_name != student_name:
        frappe.throw(_("This file is already attached to another record. Please upload the file again."))
    if not (f.file_name or file_url).lower().endswith(PASSBOOK_EXTENSIONS):
        frappe.throw(_("Passbook must be a PDF, JPG or PNG file."))

    frappe.db.set_value("File", f.name, {
        "attached_to_doctype": "Student Master",
        "attached_to_name": student_name,
        "attached_to_field": fieldname,
    })
    return file_url


@frappe.whitelist(methods=["POST"])
def upload_bank_passbook(kind, file_url):
    """Add a missing savings / loan passbook after bank details were submitted (details stay locked).

    An existing passbook can only be replaced by the administration office.
    """
    student_name = _get_student()
    if not student_name:
        frappe.throw(_("Student not found"))

    fieldname = PASSBOOK_FIELDS.get(kind)
    if not fieldname:
        frappe.throw(_("Invalid passbook type."))

    student = frappe.db.get_value(
        "Student Master", student_name, ["availed_education_loan", fieldname], as_dict=True
    )
    if kind == "loan" and student.availed_education_loan != "Yes":
        frappe.throw(_("A loan passbook can only be added when an education loan was availed."))
    if student.get(fieldname):
        frappe.throw(_("A passbook is already on file. Please contact the administration office to replace it."))

    frappe.db.set_value("Student Master", student_name, fieldname, _claim_passbook_file(student_name, fieldname, file_url))
    frappe.get_doc("Student Master", student_name).add_comment(
        "Info", _("{0} passbook uploaded by the student from the Student Portal.").format(kind.title())
    )
    return {"status": "success"}
