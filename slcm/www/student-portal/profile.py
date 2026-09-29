import frappe
from slcm.api.student_portal import BANK_DETAIL_FIELDS

no_cache = 1

def _mask_account(acct):
    acct = str(acct or "")
    return ("•••• " + acct[-4:]) if len(acct) > 4 else acct

def _mask_ifsc(ifsc):
    ifsc = str(ifsc or "")
    return ("••••" + ifsc[-4:]) if len(ifsc) > 4 else ifsc

def get_context(context):
    context.no_cache = 1

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "profile"

    student_name = _get_student_name()
    if not student_name:
        context.no_student = True
        _set_nav_defaults(context)
        return context

    context.no_student = False
    context.portal_error = None
    context.profile = {}
    context.id_card = None
    context.parents = []
    context.ug_degrees = []
    context.bank_prefill = {}
    context.can_download_application = False
    context.can_download_registration = False

    try:
        student = frappe.get_doc("Student Master", student_name)
        _set_student_nav(context, student)

        full_name = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))

        context.profile = {
            "full_name":        full_name or student.name,
            "first_name":       student.first_name or "",
            "middle_name":      student.middle_name or "",
            "last_name":        student.last_name or "",
            "dob":              frappe.utils.formatdate(student.dob, "dd MMMM yyyy") if student.dob else "",
            "gender":           student.gender or "",
            "nationality":      student.nationality or "",
            "marital_status":   student.marital_status or "",
            "quota":            student.quota or "",
            "photo":            student.passport_size_photo or "",

            "email":            student.email or "",
            "official_email":   student.official_email_id or "",
            "personal_email":   student.personal_email or "",
            "phone":            student.phone or "",
            "present_address":  student.present_address or "",
            "permanent_address":student.permanent_address or "",
            "city":             student.city or "",
            "pincode":          student.pincode or "",
            "country":          student.country or "",

            "registration_id":  student.registration_id or "",
            "application_number": student.application_number or "",
            "programme":        student.master_programme or "N/A",
            "department":       student.department or "AAD",
            "batch_year":       student.batch or "N/A",
            "academic_year":    student.academic_year or "",
            "current_term":     student.academic_term or "N/A",
            "current_year":     student.current_year or "",
            "current_cgpa":     round(student.current_cgpa or 0.0, 2),
            "student_status":   student.student_status or "",
            "academic_status":  student.academic_status or "",
            "specialisation":   student.get("specialisation") or "",
            "programme_system": student.get("programme_system") or "",
            "admission_type":   student.get("admission_type") or "",

            "is_hosteller":     bool(student.is_hosteller),
            "hostel_name":      student.get("hostel_name") or "",
            "hostel_room":      student.hostel_room or "",
            "hostel_bed":       student.hostel_bed or "",
            "meal_plan":        student.get("meal_plan") or "",

            "savings_account_number": _mask_account(student.savings_account_number),
            "savings_account_holder_name": student.savings_account_holder_name or "",
            "savings_bank_name":   student.savings_bank_name or "",
            "savings_branch_name": student.savings_branch_name or "",
            "savings_ifsc_code":   _mask_ifsc(student.savings_ifsc_code),
            "availed_education_loan": student.availed_education_loan or "",
            "education_loan_scheme":  student.education_loan_scheme or "",
            "other_loan_scheme":      student.other_loan_scheme or "",
            "loan_account_number":    _mask_account(student.loan_account_number),
            "loan_account_holder_name": student.loan_account_holder_name or "",
            "loan_bank_name":      student.loan_bank_name or "",
            "loan_branch_name":    student.loan_branch_name or "",
            "loan_ifsc_code":      _mask_ifsc(student.loan_ifsc_code),
            "savings_passbook":    student.get("savings_passbook") or "",
            "loan_passbook":       student.get("loan_passbook") or "",
            "bank_details_submitted": bool(student.bank_details_submitted),
            "bank_details_submitted_on": frappe.utils.format_datetime(student.bank_details_submitted_on, "dd MMM yyyy, hh:mm a") if student.bank_details_submitted_on else "",
        }

        # Unmasked values pre-fill the one-time form; only exposed while it is still editable
        context.bank_prefill = {} if student.bank_details_submitted else {
            f: student.get(f) or "" for f in BANK_DETAIL_FIELDS
        }

        try:
            id_card = frappe.get_all(
                "ID Card Generation",
                filters={"student": student_name, "card_status": ["in", ["Generated", "Printed"]], "card_type": "Student"},
                fields=["name", "expiry_date", "card_status", "front_id_image"],
                order_by="creation desc",
                limit=1,
                ignore_permissions=True
            )
            context.id_card = id_card[0] if id_card else None
        except Exception:
            context.id_card = None

        try:
            parents_raw = frappe.get_all(
                "Student Parent",
                filters={"parent": student_name},
                fields=["relation", "first_name", "middle_name", "last_name",
                        "phone", "email", "occupation", "annual_income"],
                ignore_permissions=True
            )
            parents = []
            for p in parents_raw:
                full = " ".join(filter(None, [p.get("first_name"), p.get("middle_name"), p.get("last_name")]))
                parents.append({
                    "parent_name": full or "—",
                    "first_name": p.get("first_name") or "",
                    "middle_name": p.get("middle_name") or "",
                    "last_name": p.get("last_name") or "",
                    "relation": p.get("relation") or "",
                    "contact_number": p.get("phone") or "",
                    "email_id": p.get("email") or "",
                    "occupation": p.get("occupation") or "",
                })
            context.parents = parents
        except Exception:
            context.parents = []

        context.can_download_application = bool(
            student.application_number
            and frappe.db.exists("Applicant", student.application_number)
        )
        context.can_download_registration = True

        try:
            ug = frappe.get_all(
                "UG Degree Detail",
                filters={"parent": student_name},
                fields=["ug_program", "college", "year_of_completion", "ug_cgpa"],
                ignore_permissions=True
            )
            context.ug_degrees = [
                {
                    "degree": d.get("ug_program") or "",
                    "institution": d.get("college") or "",
                    "year_of_passing": d.get("year_of_completion") or "",
                    "percentage": d.get("ug_cgpa") or "",
                }
                for d in ug
            ]
        except Exception:
            context.ug_degrees = []

        # Fetch important links from Student Portal Settings
        try:
            settings = frappe.get_single("Student Portal Settings")
            context.important_links = {
                "academic_calendar": settings.get("academic_calendar") or "#",
                "student_handbook": settings.get("student_handbook") or "#",
                "examination_guidelines": settings.get("examination_guidelines") or "#"
            }
        except Exception:
            context.important_links = {
                "academic_calendar": "#",
                "student_handbook": "#",
                "examination_guidelines": "#"
            }

    except Exception as e:
        frappe.log_error(f"Student Portal Profile error: {e}", "Student Portal")
        context.portal_error = str(e)
        _set_nav_defaults(context)

    return context


def _get_student_name():
    user = frappe.session.user
    name = frappe.db.get_value("Student Master", {"user": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"email": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    return name


def _set_student_nav(context, student):
    full_name = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))
    context.student_name = full_name or student.name
    context.student_id = student.registration_id or student.name
    context.student_photo = student.passport_size_photo or ""
    context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
    context.programme_name = student.master_programme or "N/A"
    context.department = student.department or "AAD"
    context.batch_year = student.batch or "N/A"


def _set_nav_defaults(context):
    user = frappe.session.user
    user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
    context.student_name = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.student_id = ""
    context.student_photo = (user_doc.user_image if user_doc else "") or ""
    context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
    context.programme_name = ""
    context.department = ""
    context.batch_year = ""


@frappe.whitelist()
def add_guardian(first_name, last_name, relation, phone, email, occupation):
    student_name = _get_student_name()
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
