import frappe
from slcm.slcm.doctype.student_portal_settings.student_portal_settings import (
    get_student_portal_settings,
)

no_cache = 1


def get_context(context):
    context.no_cache = 1

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest    = False
    context.active_page = "documents"

    try:
        _ps = get_student_portal_settings()
    except Exception:
        _ps = {}
    context.show_uploaded_documents = bool(_ps.get("show_uploaded_documents", 1))

    student_name = _get_student_name()
    if not student_name:
        context.no_student = True
        _set_nav_defaults(context)
        return context

    context.no_student = False

    try:
        student = frappe.get_doc("Student Master", student_name)
        _set_student_nav(context, student)

        # ── Transcripts ───────────────────────────────────────────
        transcript_fields = _existing_fields(
            "Student Transcript",
            [
                "name", "transcript_type", "status", "academic_year",
                "generation_date", "creation", "modified", "pdf_file", "template",
            ],
        )
        transcripts = frappe.get_all(
            "Student Transcript",
            filters={"student": student_name},
            fields=transcript_fields,
            order_by="creation desc",
            ignore_permissions=True,
        )

        interim_transcripts = [t for t in transcripts if t.transcript_type == "Interim"]
        final_transcripts   = [t for t in transcripts if t.transcript_type == "Final"]

        context.interim_transcripts = interim_transcripts
        context.final_transcripts   = final_transcripts
        context.has_interim = bool(interim_transcripts)
        context.has_final   = bool(final_transcripts)

        # ── Student ID card ───────────────────────────────────────
        context.id_card_photo = student.passport_size_photo or ""
        id_card_fields = _existing_fields(
            "ID Card Generation",
            [
                "name", "card_status", "issue_date", "expiry_date",
                "front_id_image", "back_id_image", "verification_url",
                "cancellation_reason", "modified",
            ],
        )
        context.id_cards = frappe.get_all(
            "ID Card Generation",
            filters={"student": student_name, "card_type": "Student"},
            fields=id_card_fields,
            order_by="modified desc",
            ignore_permissions=True,
        )
        context.active_id_card = context.id_cards[0] if context.id_cards else None

        # ── Bonafide / other certificates ─────────────────────────
        if frappe.db.exists("DocType", "Student Certificate"):
            cert_fields = _existing_fields(
                "Student Certificate",
                ["name", "certificate_type", "status", "creation", "valid_till", "pdf_file"],
            )
            cert_docs = frappe.get_all(
                "Student Certificate",
                filters={"student": student_name},
                fields=cert_fields,
                order_by="creation desc",
                ignore_permissions=True,
            )
        else:
            cert_docs = []
        context.certificates = cert_docs

        # ── Enrollment certificate / record ───────────────────────
        context.active_enrollment = frappe.db.get_value(
            "Student Enrollment",
            {"student": student_name, "status": "Enrolled"},
            ["name", "program", "academic_year", "term_name", "enrollment_date", "status"],
            as_dict=True,
        )
        if not context.active_enrollment:
            context.active_enrollment = frappe.db.get_value(
                "Student Enrollment",
                {"student": student_name},
                ["name", "program", "academic_year", "term_name", "enrollment_date", "status"],
                order_by="creation desc",
                as_dict=True,
            )

        # ── Student Master uploaded documents ─────────────────────
        _STUDENT_DOC_FIELDS = [
            ("aadhaar_card",                  "Aadhaar Card"),
            ("pan_card",                      "PAN Card"),
            ("passport",                      "Passport"),
            ("pwd_certificate",               "PWD Certificate"),
            ("std_x_marksheet",               "Class X Marksheet"),
            ("class_xii_marksheet",           "Class XII Marksheet"),
            ("ug_certificate",                "UG Degree Certificate"),
            ("ug_transcripts",                "UG Transcripts / Marksheets"),
            ("transfer_certificate",          "Transfer Certificate"),
            ("entrance_exam_score_marksheet", "Entrance Exam Scoresheet"),
            ("offer_letter",                  "Offer Letter"),
            ("phd_proposal",                  "PhD Proposal"),
            ("posh_anti_ragging_declaration", "PoSH & Anti-Ragging Declaration"),
            ("student_declaration",           "Student Declaration"),
            ("parent_declaration",            "Parent Declaration"),
        ]
        student_docs = []
        if context.show_uploaded_documents:
            meta_fields = {df.fieldname for df in frappe.get_meta("Student Master").fields}
            for fieldname, label in _STUDENT_DOC_FIELDS:
                if fieldname not in meta_fields:
                    continue
                url = getattr(student, fieldname, None)
                if url:
                    student_docs.append({"label": label, "url": url, "fieldname": fieldname})
        context.student_docs = student_docs

        # ── Aggregate counts ──────────────────────────────────────
        context.total_docs = (
            len(transcripts)
            + len(cert_docs)
            + len(context.id_cards)
            + len(student_docs)
            + (1 if context.active_enrollment else 0)
        )

    except Exception as exc:
        frappe.log_error(f"Documents page error: {exc}", "Student Portal Documents")
        context.portal_error = str(exc)
        _set_nav_defaults(context)

    return context


# ── Helpers ──────────────────────────────────────────────────────────────────

def _existing_fields(doctype, wanted):
    meta = frappe.get_meta(doctype)
    valid = {"name", "creation", "modified", "owner", "docstatus"}
    valid.update(df.fieldname for df in meta.fields if df.fieldname)
    return [field for field in wanted if field in valid]

def _get_student_name():
    user = frappe.session.user
    name = frappe.db.get_value("Student Master", {"user": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"email": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    return name


def _set_student_nav(context, student):
    full = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))
    context.student_name    = full or student.name
    context.student_id      = student.registration_id or student.name
    context.student_photo   = student.passport_size_photo or ""
    context.student_initial = context.student_name[0].upper() if context.student_name else "S"
    context.programme_name  = (
        frappe.db.get_value("SLCM Batch", student.programme, "cohort_name")
        or student.programme or ""
    )
    context.department = student.department or ""
    context.batch_year = student.batch_year or ""


def _set_nav_defaults(context):
    user     = frappe.session.user
    user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
    context.student_name    = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.student_id      = ""
    context.student_photo   = (user_doc.user_image if user_doc else "") or ""
    context.student_initial = context.student_name[0].upper() if context.student_name else "S"
    context.programme_name  = ""
    context.department      = ""
    context.batch_year      = ""
