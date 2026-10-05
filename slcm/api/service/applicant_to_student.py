# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt
#
# Unified Applicant → Student Master conversion API.
#
# This module is the single source of truth for:
#   - Field mapping from Applicant → Student Master
#   - Student Master creation / deduplication guard
#   - User role swap (Applicant role → Student role)
#   - Scholarship sync from AFA → Student Master
#
# Entry points:
#   convert_applicant_to_student()  — @frappe.whitelist, called by AFA create_invoice()
#                                     and the "Convert to Student" button on the Applicant form.

import frappe
from frappe.utils import flt, nowdate


# ── Academic Year Helper ──────────────────────────────────────────────────────

def _get_academic_year_from_cycle(admission_cycle):
    """
    Derive academic year name from the Admission Cycle's linked Admission Year.
    Falls back to None if not resolvable.
    """
    if not admission_cycle:
        return None
    try:
        year_link = frappe.db.get_value("Admission Cycle", admission_cycle, "admission_year")
        if year_link:
            academic_year_name = frappe.db.get_value("Admission Year", year_link, "year_name")
            return academic_year_name or year_link
    except Exception:
        pass
    return None


# ── Field Mapping: Applicant → Student Master ─────────────────────────────────

def _map_applicant_to_student(student, applicant, program, admission_cycle, offer_letter_name=None):
    """
    Central mapping function: Applicant fields → Student Master fields.
    All field assignments and error-safe lookups are handled here.

    Mapped fields (Applicant → Student Master):
        name                        → application_number
        candidate_name              → first_name  (full name; no split)
        date_of_birth               → dob
        email                       → email, personal_email
        mobile_number               → phone  (falls back to alternate_contact)
        alternate_contact           → alternate_phone
        nationality                 → nationality
        religion                    → religion
        gender                      → gender  (Link — existence-checked)
        correspondence_address      → present_address, permanent_address
        city                        → city
        state                       → state
        pincode                     → pincode
        country                     → country  (Link value stored as Data)
        pwd (Yes/No)                → pwd (Check 0/1)
        ews / whether_scstobc_ncl   → quota
        academic_year               → academic_year  (falls back via admission_cycle)
        intake_type                 → intake
        intake_type                 → admission_type  (Internal Test→Regular, External Test→PACE)
        program (AFA)               → programme_of_study
        program (AFA) department    → department
        class_x_school              → class_x_school
        class_x_percentage          → class_x_percentage
        class_x_year_of_completion  → class_x_completion_year
        class_x_board               → class_x_board
        class_x_cgpa                → class_x_max_cgpa
        class_xii_school            → class_xii_school
        hsc_percentage              → class_xii_percentage
        class_xii_year_of_completion→ class_xii_completion_year
        class_xii_board             → class_xii_board
        class_xii_cgpa              → class_xii_max_cgpa
        class_xii_name_of_examination→ class_xii_exam_name
        candidate_photo             → passport_size_photo
        id_proof                    → aadhaar_card
        class_x_marksheet           → std_x_marksheet
        class_xii_marksheet         → class_xii_marksheet
        pwd_certificate             → pwd_certificate
        national_test_certificate   → entrance_exam_score_marksheet
        ug_degree_completion        → ug_degree_completed
        ug_degree_details (table)   → ug_degree_details (table)
        pg_degree_details (table)   → pg_degree_details (table)
        phd_proposal                → phd_proposal
        phd_program_type            → phd_programme
        proposed_phd_topic          → proposed_phd_topic
        father_*/mother_*/guardian_*→ parents (child table)
        Offer Letter PDF            → offer_letter
        (hardcoded)                 → student_status = "Active"
        (hardcoded)                 → account_status = "Active"
        (hardcoded)                 → date_of_registration = today
    """

    # ── Registration / Naming ─────────────────────────────────────────────────
    # name (registration_id) will be set via naming series — do not force-set.
    # application_number tracks back to the Applicant record.
    student.application_number = applicant.name

    # ── Programme ─────────────────────────────────────────────────────────────
    student.programme_of_study = program

    # ── Department & Level of Study (derived from programme/program) ────────────────────────────
    if program:
        program_data = frappe.db.get_value("Programme", program, ["department", "level_of_study"], as_dict=True)
        if program_data:
            if program_data.get("department"):
                student.department = program_data.department
            if program_data.get("level_of_study"):
                student.level_of_study = program_data.level_of_study

    # ── Academic Year ──────────────────────────────────────────────────────────
    # Priority: 1. Applicant's academic_year, 2. Derived from Admission Cycle
    student.academic_year = applicant.get("academic_year")
    if not student.academic_year:
        derived_year = _get_academic_year_from_cycle(admission_cycle)
        if derived_year:
            student.academic_year = derived_year

    # ── Batch Assignment ───────────────────────────────────────────────────────
    if program and student.academic_year:
        batch_data = frappe.db.get_value(
            "Batch",
            {
                "program": program,
                "academic_year": student.academic_year,
                "status": "Active"
            },
            ["name", "academic_term"],
            as_dict=True
        )
        if batch_data:
            student.programme = batch_data.name
            if batch_data.academic_term:
                student.academic_term = batch_data.academic_term

    # ── Name: full candidate_name in first_name only (no split) ──────────────
    full_name = (applicant.get("candidate_name") or "").strip()
    student.first_name = full_name if full_name else (applicant.name or "Applicant")
    student.middle_name = None
    student.last_name = None

    # ── Personal Details ───────────────────────────────────────────────────────
    student.dob            = applicant.date_of_birth or nowdate()
    student.email          = applicant.email or ""
    student.personal_email = applicant.email or ""
    student.phone          = applicant.mobile_number or applicant.get("alternate_contact") or ""
    student.alternate_phone = applicant.get("alternate_contact") if (
        applicant.get("alternate_contact") and applicant.mobile_number
    ) else None
    student.nationality    = applicant.get("nationality") or None
    student.religion       = applicant.get("religion") or None

    # ── Gender (Link to Genders / Gender DocType) ──────────────────────────────
    raw_gender = applicant.get("gender")
    if raw_gender:
        if frappe.db.exists("Genders", raw_gender):
            student.gender = raw_gender
        elif frappe.db.exists("Gender", raw_gender):
            student.gender = raw_gender

    # ── Address ────────────────────────────────────────────────────────────────
    student.present_address   = applicant.get("correspondence_address") or None
    student.permanent_address = applicant.get("correspondence_address") or None
    student.city              = applicant.get("city") or None
    student.district          = applicant.get("city") or None
    student.state             = applicant.get("state") or None
    student.pincode           = applicant.get("pincode") or None
    student.passport_available = "No"

    # country: Applicant stores as Link → Student stores as Data (store the link value/name)
    raw_country = applicant.get("country")
    if raw_country:
        student.country = str(raw_country)

    # ── PwD ───────────────────────────────────────────────────────────────────
    # Applicant stores "Yes"/"No" Select; Student Master uses Check (0/1)
    pwd_val = applicant.get("pwd")
    student.pwd = 1 if str(pwd_val).strip().lower() in ("yes", "1") else 0

    # ── Admission Type / Intake ────────────────────────────────────────────────
    # admission_type is always "Regular" — all applicants apply for Regular programmes.
    # PACE applicants use a separate PACE application form and are handled independently.
    student.admission_type = "Regular"

    # intake: store the raw intake_type label from the Applicant (Internal Test /
    # External Test / Direct Merit) so it is visible on the Student record.
    raw_intake = (applicant.get("intake_type") or "").strip()
    if raw_intake:
        student.intake = raw_intake

    # Map quota based on reservation fields
    is_international = str(applicant.get("foriegn_national")).strip().lower() in ("yes", "1")
    
    if is_international:
        student.quota = "NA"
    else:
        sc_st_obc = (applicant.get("whether_scstobc_ncl") or "").strip()
        if sc_st_obc == "OBC-NCL":
            student.quota = "OBC"
        elif sc_st_obc and sc_st_obc != "NA":
            student.quota = sc_st_obc
        else:
            student.quota = "General"

    # ── Fetch Dynamic Data from Entrance Test / Merit ──────────────────────────
    sa_data = frappe.db.get_value(
        "Entrance Test Seat Allocation",
        {"applicant": applicant.name, "program": program},
        ["admit_card_number", "entrance_test_status", "total_marks_secured_in_part_a_b"],
        as_dict=True
    )
    if sa_data:
        student.admit_card_number = sa_data.admit_card_number
        if sa_data.entrance_test_status == "Attended":
            student.exam_attended = "Attended"
        else:
            student.exam_attended = "Not Attended"
        student.total_marks_obtained = sa_data.total_marks_secured_in_part_a_b
        
    ma_data = frappe.db.get_value(
        "Merit List Applicant",
        {"applicant_id": applicant.name},
        ["overall_rank", "category_rank", "shortlist_category", "vertical_category", "horizontal_categories", "percentile_score"],
        as_dict=True
    )
    if ma_data:
        student.final_rank = ma_data.overall_rank
        student.final_category_rank = ma_data.category_rank
        student.final_percentile = ma_data.percentile_score
        student.final_rank_category = ma_data.shortlist_category
        student.rank_category = ma_data.shortlist_category
        student.final_vertical = ma_data.vertical_category
        student.final_horizontal = ma_data.horizontal_categories

    # ── Map Direct Applicant Fields ───────────────────────────────────────────
    student.annual_income = applicant.get("annual_house_hold_income")
    student.needs_accommodation = applicant.get("needs_accommodation")
    student.id_proof_govt_issued_photo_id = applicant.get("id_proof")
    student.caste_certificate = applicant.get("caste_certificate")
    student.whether_ews = "Yes" if applicant.get("whether_scstobc_ncl") == "EWS" else "No"
    if applicant.get("whether_scstobc_ncl") == "EWS":
        student.ews_certificate = applicant.get("caste_certificate")
    student.pwd_required_test = applicant.get("pwd_required_test")
    student.scribe_allotment = applicant.get("scribe_allotment")
    student.karnataka_category = applicant.get("karnataka_category")
    student.ka_study_7yrs = applicant.get("ka_study_7yrs")
    student.ka_study_7yrs_certificate = applicant.get("ka_study_7yrs_certificate")
    student.ka_defence_child = applicant.get("ka_defence_child")
    student.ka_defence_child_certificate = applicant.get("ka_defence_child_certificate")
    student.ka_govt_child = applicant.get("ka_govt_child")
    student.ka_govt_child_certificate = applicant.get("ka_govt_child_certificate")
    student.ka_ais_child = applicant.get("ka_ais_child")
    student.ka_ais_child_certificate = applicant.get("ka_ais_child_certificate")
    student.ka_capf_child = applicant.get("ka_capf_child")
    student.ka_capf_child_certificate = applicant.get("ka_capf_child_certificate")
    student.curriculum_vitae = applicant.get("cv")
    student.do_you_have_any_post_degree_work_experince = applicant.get("post_degree_work_experience")
    student.how_many_years_of_work_experince_do_you_have = applicant.get("years_of_work_experience")

    # Set registration date
    student.date_of_registration = nowdate()

    # ── Class X ───────────────────────────────────────────────────────────────
    student.class_x_school          = applicant.get("class_x_school") or None
    student.class_x_percentage      = applicant.get("class_x_percentage") or None
    student.class_x_completion_year = applicant.get("class_x_year_of_completion") or None
    student.class_x_board           = applicant.get("class_x_board") or None
    student.class_x_max_cgpa        = applicant.get("class_x_cgpa") or None

    # ── Class XII ─────────────────────────────────────────────────────────────
    student.class_xii_school          = applicant.get("class_xii_school") or None
    student.class_xii_percentage      = applicant.get("hsc_percentage") or None
    student.class_xii_completion_year = applicant.get("class_xii_year_of_completion") or None
    student.class_xii_board           = applicant.get("class_xii_board") or None
    student.class_xii_max_cgpa        = applicant.get("class_xii_cgpa") or None
    student.class_xii_exam_name       = applicant.get("class_xii_name_of_examination") or None

    # ── Documents (Attachments) ───────────────────────────────────────────────
    student.passport_size_photo           = applicant.get("candidate_photo") or None
    student.std_x_marksheet               = applicant.get("class_x_marksheet") or None
    student.class_xii_marksheet           = applicant.get("class_xii_marksheet") or None
    student.pwd_certificate               = applicant.get("pwd_certificate") or None
    student.entrance_exam_score_marksheet = applicant.get("national_test_certificate") or None
    student.passport                      = applicant.get("copy_of_passport") or None

    #User
    student.user = applicant.get("email") or None

    if offer_letter_name:
        offer_pdf = frappe.db.get_value("Offer Letter", offer_letter_name, "offer_letter_pdf")
        if offer_pdf:
            student.offer_letter = offer_pdf

    # ── UG Degree (child table: ug_degree_details) ────────────────────────────
    student.ug_degree_completed = applicant.get("ug_degree_completion") or None
    if applicant.get("ug_degree_details"):
        for row in applicant.ug_degree_details:
            student.append("ug_degree_details", {
                "ug_program":         row.get("ug_program") or None,
                "college":            row.get("college") or None,
                "year_of_completion": row.get("year_of_completion") or None,
                "ug_cgpa":            row.get("ug_cgpa") or None,
                "ug_max_cgpa":        row.get("ug_max_cgpa") or None,
                "degree_certificate": row.get("degree_certificate") or None,
                "marksheets":         row.get("marksheets") or None,
            })

    # ── PG Degree (child table: pg_degree_details) ────────────────────────────
    if applicant.get("pg_degree_details"):
        for row in applicant.pg_degree_details:
            student.append("pg_degree_details", {
                "pg_program":         row.get("pg_program") or None,
                "collegeuniversity":  row.get("collegeuniversity") or None,
                "year_of_completion": row.get("year_of_completion") or None,
                "pg_cgpa":            row.get("pg_cgpa") or None,
                "pg_max_cgpa":        row.get("pg_max_cgpa") or None,
                "pg_degree_certificatebonafide_certificate_to_be_uploaded":
                    row.get("pg_degree_certificatebonafide_certificate_to_be_uploaded") or None,
                "transcriptsmarksheets_to_be_uploaded":
                    row.get("transcriptsmarksheets_to_be_uploaded") or None,
            })

    # ── PhD ───────────────────────────────────────────────────────────────────
    student.phd_proposal      = applicant.get("phd_proposal") or None
    student.phd_programme     = applicant.get("phd_program_type") or None
    student.proposed_phd_topic = applicant.get("proposed_phd_topic") or None

    # ── Parents (child table) ─────────────────────────────────────────────────
    parent_rows = [
        {
            "relation":        "Father",
            "name_field":      applicant.get("father_name"),
            "email_field":     applicant.get("father_email"),
            "mobile_field":    applicant.get("father_mobile"),
            "occupation_field":applicant.get("father_occupation"),
        },
        {
            "relation":        "Mother",
            "name_field":      applicant.get("mother_name"),
            "email_field":     applicant.get("mother_email"),
            "mobile_field":    applicant.get("mother_mobile"),
            "occupation_field":applicant.get("mother_occupation"),
        },
    ]

    guardian_required = str(applicant.get("guardian_required") or "").strip().lower()
    if guardian_required in ("yes", "1"):
        parent_rows.append({
            "relation":        "Guardian",
            "name_field":      applicant.get("guardian_name"),
            "email_field":     applicant.get("guardian_email"),
            "mobile_field":    applicant.get("guardian_mobile"),
            "occupation_field":None,
        })

    for p in parent_rows:
        if p["name_field"]:   # only add row if at least a name exists
            student.append("parents", {
                "relation":   p["relation"],
                "first_name": p["name_field"],
                "email":      p["email_field"] or None,
                "phone":      p["mobile_field"] or None,
                "occupation": p["occupation_field"] or None,
            })

    # ── Account Status (set at enrollment) ────────────────────────────────────
    student.student_status = "Active"
    student.account_status = "Active"
    student.registration_status = "Active"

    return student


# ── Finance Tab Sync (Scholarship Details + Fee Details) ─────────────────────

def _sync_finance_to_student(
    student_name,
    scholarship_amount=0,
    scholarship_type=None,
    scholarship_percentage=0,
    scholarship_approval_date=None,
    fee_waiver_remarks=None,
    number_of_instalments=0,
    total_amount=0,
    final_payable_amount=0,
    fee_payment_status=None,
    fee_structure=None,
):
    """
    Populate the Finance tab of Student Master from AFA / conversion data.

    Scholarship Details section:
        applying_scholarship     — "Yes" / "No"
        scholarship_type         — Merit / Need-Based / Sports / Cultural / Other
        scholarship_amount       — raw scholarship currency amount
        scholarship_percentage   — if the scholarship is expressed as a percentage
        scholarship_approval_date— Date the scholarship was approved
        discount_amount          — same as scholarship_amount (readonly display field)
        fee_waiver_remarks       — free-text reason for fee waiver
        number_of_instalments    — payment split count

    Fee Details section:
        fee_structure            — Link to Fee Structure (written if currently blank)
        total_program_fee        — AFA total_amount (written if currently zero)
        net_program_fee          — total_program_fee minus discount_amount
        outstanding_balance      — net_program_fee minus total_paid_amount
        fee_payment_status       — mapped from AFA status vocabulary

    Rules:
      - Scholarship fields (discount_amount and friends) are written only when
        discount_amount is currently zero (admin manual entry wins).
      - total_program_fee is only written if currently zero / blank.
      - Never raises — invoice creation must not be blocked by this.

    Source mapping (AFA → Student Master):
        AFA.scholarship_amount        → scholarship_amount, discount_amount
        AFA.remarks                   → fee_waiver_remarks (optional, pass explicitly)
        (no AFA source)               → scholarship_type, scholarship_percentage,
                                        scholarship_approval_date, number_of_instalments
                                        (these are admin-entry fields on Student Master;
                                        pass them explicitly if your caller has the data)
    """
    try:
        sm = frappe.db.get_value(
            "Student Master",
            student_name,
            [
                "total_program_fee", "total_paid_amount",
                "discount_amount", "fee_structure",
            ],
            as_dict=True,
        ) or {}

        update_fields = {}

        # ── Scholarship Details ───────────────────────────────────────────────
        scholarship_amount = flt(scholarship_amount)
        admin_discount_set = flt(sm.get("discount_amount") or 0) > 0

        if not admin_discount_set and scholarship_amount > 0:
            # Admin has not manually set a discount — write all scholarship values.
            update_fields["applying_scholarship"] = "Yes"
            update_fields["scholarship_amount"]   = scholarship_amount
            update_fields["discount_amount"]       = scholarship_amount
        elif scholarship_amount <= 0:
            update_fields["applying_scholarship"] = "No"

        # These scholarship detail fields are written regardless of the
        # admin_discount_set guard — they are informational, not computed.
        if scholarship_type:
            update_fields["scholarship_type"] = scholarship_type

        if flt(scholarship_percentage) > 0:
            update_fields["scholarship_percentage"] = flt(scholarship_percentage)

        if scholarship_approval_date:
            update_fields["scholarship_approval_date"] = scholarship_approval_date

        if fee_waiver_remarks:
            update_fields["fee_waiver_remarks"] = fee_waiver_remarks

        if int(number_of_instalments or 0) > 0:
            update_fields["number_of_instalments"] = int(number_of_instalments)

        # ── Fee Details ───────────────────────────────────────────────────────
        total_amount   = flt(total_amount)
        existing_total = flt(sm.get("total_program_fee") or 0)
        paid           = flt(sm.get("total_paid_amount") or 0)
        disc           = flt(
            update_fields.get("discount_amount")
            or sm.get("discount_amount")
            or 0
        )

        # Write fee_structure link
        if fee_structure:
            update_fields["fee_structure"] = fee_structure

        # Write total_program_fee only if currently blank
        if total_amount > 0 and existing_total <= 0:
            update_fields["total_program_fee"] = total_amount

        # Recalculate derived fee fields
        effective_total = total_amount if total_amount > 0 else existing_total
        net_fee = max(effective_total - disc, 0)
        update_fields["net_program_fee"]     = net_fee

        # Fee payment status — map AFA vocabulary → Student Master options
        mapped_status = None
        if fee_payment_status:
            afa_to_student_status = {
                "Paid":           "Paid",
                "Partially Paid": "Partially Paid",
                "Assigned":       "Unpaid",
                "Converted":      "Paid",
            }
            mapped_status = afa_to_student_status.get(fee_payment_status)
            if mapped_status:
                update_fields["fee_payment_status"] = mapped_status

        # If fully paid, override the paid and outstanding values
        if mapped_status == "Paid":
            update_fields["total_paid_amount"] = net_fee
            update_fields["outstanding_balance"] = 0
        else:
            update_fields["outstanding_balance"] = max(net_fee - paid, 0)

        if update_fields:
            frappe.db.set_value(
                "Student Master",
                student_name,
                update_fields,
                update_modified=False,
            )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Finance tab sync failed for Student Master: {student_name}",
        )


# Backward-compat alias — keeps existing callers that imported the old name working.
def _sync_scholarship_to_student(student_name, scholarship_amount):
    """Thin wrapper — delegates to _sync_finance_to_student."""
    _sync_finance_to_student(
        student_name=student_name,
        scholarship_amount=scholarship_amount,
    )

# ── User Role Swap ────────────────────────────────────────────────────────────

def _update_user_roles_for_student(applicant_email):
    """
    Add 'slcm_Student' role and remove 'Applicant' role/role_profile from the user.
    Non-fatal — logs errors silently.
    """
    if not applicant_email:
        return
    try:
        user_name = frappe.db.get_value("User", {"email": applicant_email}, "name")
        if not user_name:
            return
        user = frappe.get_doc("User", user_name)
        roles_updated = False

        existing_roles = [d.role for d in user.get("roles", [])]

        # Add slcm_Student role if not present
        if "slcm_Student" not in existing_roles:
            user.append("roles", {"role": "slcm_Student"})
            roles_updated = True

        if roles_updated:
            user.save(ignore_permissions=True)
            frappe.logger().info(
                f"[convert_applicant_to_student] User {user_name}: Added slcm_Student role"
            )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"User role update failed for email: {applicant_email}",
        )


# ── Whitelist API ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def convert_applicant_to_student(applicant_name, program, admission_cycle, offer_letter_name=None):
    """
    Single whitelist entry point for converting an Applicant to a Student Master.

    Responsibilities:
      1. Load the Applicant doc
      2. Deduplicate guard (by application_number and email)
      3. Create Student Master via _map_applicant_to_student
      4. Swap User roles: Applicant → Student
      5. Return {"student_name": <name>, "created": True/False}

    This function does NOT create Fee Invoice, Student Enrollment, or AFA records.
    Those remain in applicant_fee_assignment.create_invoice() which calls this function.

    Args:
        applicant_name  (str): Applicant doc name
        program         (str): Program doc name (from AFA or form)
        admission_cycle (str): Admission Cycle doc name
        offer_letter_name (str, optional): Offer Letter doc name for PDF attachment

    Returns:
        dict: {"student_name": str, "created": bool}
    """
    if not frappe.db.exists("Applicant", applicant_name):
        frappe.throw(frappe._("Applicant {0} not found.").format(applicant_name))

    applicant = frappe.get_doc("Applicant", applicant_name)
    
    # Acquire a row-level lock on the Applicant record to serialize concurrent conversion requests
    frappe.db.sql("SELECT name FROM `tabApplicant` WHERE name = %s FOR UPDATE", applicant_name)

    # ── 1. Check if Student Master already exists ──────────────────────────────
    existing_by_app_no = frappe.db.get_value(
        "Student Master", {"application_number": applicant_name}, "name"
    )
    if existing_by_app_no:
        frappe.logger().info(
            f"[convert_applicant_to_student] Student Master {existing_by_app_no} "
            f"already exists for Applicant {applicant_name}. Returning existing."
        )
        if applicant.status != "Enrolled":
            applicant.status = "Enrolled"
            applicant.save(ignore_permissions=True)
        return {"student_name": existing_by_app_no, "created": False}

    # ── 2. Guard: block if Active student with same email belongs to different applicant ──
    if applicant.email:
        existing_by_email = frappe.db.get_value(
            "Student Master",
            {"email": applicant.email, "student_status": "Active"},
            ["name", "application_number"],
            as_dict=True,
        )
        if existing_by_email and existing_by_email.application_number != applicant_name:
            frappe.throw(
                frappe._(
                    "An Active Student Master record ({0}) with email {1} already exists "
                    "and belongs to a different application ({2}). "
                    "Cannot create a duplicate student. "
                    "Please verify the applicant's email before converting."
                ).format(
                    existing_by_email.name,
                    applicant.email,
                    existing_by_email.application_number or frappe._("unknown"),
                ),
                title=frappe._("Duplicate Student Email"),
            )

    # ── 3. Create Student Master ───────────────────────────────────────────────
    try:
        student = frappe.new_doc("Student Master")
        student = _map_applicant_to_student(
            student, applicant, program, admission_cycle, offer_letter_name
        )
        student.insert(
            ignore_permissions=True,
            ignore_mandatory=True,
            ignore_links=True,
        )
        student_name = student.name

        frappe.logger().info(
            f"[convert_applicant_to_student] Student Master created: {student_name} "
            f"for Applicant: {applicant_name}"
        )

    except Exception as err:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Student Master Creation Failed | Applicant: {applicant_name}",
        )
        frappe.throw(
            frappe._(
                "Could not create Student record. Please check the Error Log for details. Error: {0}"
            ).format(str(err))
        )

    # Mark Applicant as Enrolled
    if applicant.status != "Enrolled":
        applicant.db_set("status", "Enrolled", update_modified=True)

    # ── 4. Swap User roles ─────────────────────────────────────────────────────
    _update_user_roles_for_student(applicant.email)

    # ── 5. Trigger Finance Sync if AFA exists ──────────────────────────────────
    # This ensures scholarship details and fee totals are pushed to the Finance tab
    # even if converted via the Applicant form button.
    try:
        afa_name = frappe.db.get_value("Applicant Fee Assignment", {
            "applicant": applicant_name,
            "program": program,
            "admission_cycle": admission_cycle,
            "fee_type": "Admission Fee",
            "docstatus": 1
        }, "name")

        if afa_name:
            from slcm.admission.doctype.applicant_fee_assignment.applicant_fee_assignment import create_invoice
            # We don't call create_invoice here because that would create a DUPLICATE invoice
            # if this was called FROM create_invoice.
            # Instead, we just sync the finance data if it hasn't been done.
            afa_doc = frappe.get_doc("Applicant Fee Assignment", afa_name)

            # Re-use the logic from AFA.py to fetch scholarship details
            scholarship_type = None
            scholarship_percentage = 0
            scholarship_approval_date = None

            if afa_doc.get("scholarship_application"):
                sa_data = frappe.db.get_value("Scholarship Application", afa_doc.scholarship_application,
                    ["scholarship_scheme", "approval_date"], as_dict=True)
                if sa_data:
                    scholarship_approval_date = sa_data.approval_date
                    if sa_data.scholarship_scheme:
                        scheme_data = frappe.db.get_value("Scholarship Scheme", sa_data.scholarship_scheme,
                            ["scheme_type", "coverage_type", "coverage_value"], as_dict=True)
                        if scheme_data:
                            scholarship_type = scheme_data.scheme_type
                            if scheme_data.coverage_type == "Percentage":
                                scholarship_percentage = scheme_data.coverage_value

            offer_fee_structure = None
            if afa_doc.get("offer_letter"):
                offer_fee_structure = frappe.db.get_value("Offer Letter", afa_doc.offer_letter, "fee_structure")

            _sync_finance_to_student(
                student_name=student_name,
                scholarship_amount=flt(afa_doc.scholarship_amount),
                scholarship_type=scholarship_type,
                scholarship_percentage=flt(scholarship_percentage),
                scholarship_approval_date=scholarship_approval_date,
                fee_waiver_remarks=afa_doc.get("remarks") or None,
                total_amount=flt(afa_doc.total_amount),
                final_payable_amount=flt(afa_doc.get("final_payable_amount") or 0),
                fee_payment_status=afa_doc.status,
                fee_structure=offer_fee_structure,
            )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Finance sync during conversion failed for {applicant_name}")

    # ── 6. Create Student Enrollment ───────────────────────────────────────────
    # If you want to disable automatic enrollment creation in the future, 
    # simply comment out the line below.
    create_student_enrollment(student_name)

    return {"student_name": student_name, "created": True}


def create_student_enrollment(student_name):
    """
    Creates the initial Student Enrollment record for a newly converted student.
    Uses the batch (programme) assigned during the applicant conversion.
    """
    try:
        student = frappe.get_doc("Student Master", student_name)
        
        # Enrollment requires a batch (stored in 'programme' field on Student Master)
        if not student.programme:
            frappe.logger().warning(f"Skipping Student Enrollment for {student_name}: No batch assigned.")
            return None
            
        # Check if enrollment already exists for this batch
        if frappe.db.exists("Student Enrollment", {"student": student_name, "batch": student.programme}):
            return None
            
        enrollment = frappe.new_doc("Student Enrollment")
        enrollment.student = student_name
        enrollment.enrollment_date = frappe.utils.today()
        enrollment.batch = student.programme
        
        # Fields like program, academic_year, and term_name are fetch_from batch
        enrollment.insert(ignore_permissions=True)
        frappe.logger().info(f"[create_student_enrollment] Created {enrollment.name} for Student {student_name}")
        
        return enrollment.name
        
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Student Enrollment Creation Failed | Student: {student_name}"
        )
        return None
