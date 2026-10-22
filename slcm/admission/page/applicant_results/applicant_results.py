import frappe
from slcm.admission.utils.nlsat_portal import get_portal_login_url
from frappe.utils import now_datetime, flt


def get_context(context):
    context.no_cache = 1
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = get_portal_login_url() + "?redirect-to=/app/applicant-results"
        raise frappe.Redirect
    return context


@frappe.whitelist()
def get_my_results():
    """
    Returns merit score, seat allocation, and applicable scholarships
    for the currently logged-in applicant.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Please log in to view your results.")

    # 1. Find the applicant record linked to this user (matched by email)
    applicant = frappe.db.get_value(
        "Applicant",
        {"email": user},
        ["name", "candidate_name", "email", "admission_cycle",
         "campus", "program", "status", "whether_scstobc_ncl",
         "annual_house_hold_income"],
        as_dict=True
    )

    if not applicant:
        return {"error": "No applicant record found for this account."}

    result = {
        "applicant": applicant,
        "merit": None,
        "seat_allocation": None,
        "scholarships": []
    }

    # 2. Fetch Merit Score from Merit List
    try:
        merit_row = frappe.db.sql("""
            SELECT
                mla.total_score,
                mla.overall_rank,
                mla.program_rank,
                mla.hsc_percentage,
                mla.entrance_score,
                mla.interview_score,
                mla.ug_cgpa,
                mla.pg_cgpa,
                mla.status as merit_status,
                ml.program_level,
                ml.generated_on,
                ml.status as list_status
            FROM `tabMerit List Applicant` mla
            INNER JOIN `tabMerit List` ml ON ml.name = mla.parent
            WHERE mla.applicant_id = %(applicant_id)s
              AND ml.admission_cycle = %(cycle)s
              AND ml.status = 'Published'
            ORDER BY ml.generated_on DESC
            LIMIT 1
        """, {
            "applicant_id": applicant.name,
            "cycle": applicant.admission_cycle
        }, as_dict=True)

        if merit_row:
            result["merit"] = merit_row[0]
    except Exception as e:
        frappe.log_error(f"Merit score fetch error: {e}", "Applicant Results")

    # 3. Fetch Published Seat Allocation
    try:
        seat_alloc = frappe.db.sql("""
            SELECT
                sa.name,
                sa.campus,
                sa.admission_cycle,
                sa.status,
                sa.published_on,
                saa.program,
                saa.selection_status,
                saa.overall_rank
            FROM `tabSeat Allocation` sa
            INNER JOIN `tabSeat Selection Applicant` saa ON saa.parent = sa.name
            WHERE saa.applicant_id = %(applicant_id)s
              AND sa.admission_cycle = %(cycle)s
              AND sa.status = 'Published'
            ORDER BY sa.published_on DESC
            LIMIT 1
        """, {
            "applicant_id": applicant.name,
            "cycle": applicant.admission_cycle
        }, as_dict=True)

        if seat_alloc:
            result["seat_allocation"] = seat_alloc[0]
    except Exception as e:
        frappe.log_error(f"Seat allocation fetch error: {e}", "Applicant Results")

    # 4. Fetch Applicable Scholarships
    try:
        from slcm.admission.utils.scholarship_availability import get_available_scholarships_for_dashboard

        applicant_statuses = [applicant.status] if applicant.status else []
        scholarships = get_available_scholarships_for_dashboard(
            applicant_id=applicant.name,
            cycle=applicant.admission_cycle,
            campus=applicant.campus,
            program=applicant.program,
            applicant_statuses=applicant_statuses
        )
        # Enrich with scheme_type
        for s in scholarships:
            s["scheme_type"] = frappe.db.get_value(
                "Scholarship Scheme", s.name, "scheme_type"
            ) or ""
        result["scholarships"] = scholarships
    except Exception as e:
        frappe.log_error(f"Scholarship fetch error: {e}", "Applicant Results")

    # 5. My existing scholarship applications
    try:
        my_applications = frappe.get_all(
            "Scholarship Application",
            filters={"applicant_id": applicant.name},
            fields=["name", "scholarship_scheme", "status", "calculated_benefit", "creation"],
            order_by="creation desc"
        )
        result["my_scholarship_applications"] = my_applications
    except Exception as e:
        frappe.log_error(f"Scholarship applications fetch error: {e}", "Applicant Results")
        result["my_scholarship_applications"] = []

    return result


@frappe.whitelist()
def apply_for_scholarship(scheme, family_income=None, income_certificate=None, supporting_documents=None):
    """
    Creates a Scholarship Application directly from the applicant results page.
    Identifies the applicant from the logged-in user's email.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Please log in to apply for a scholarship.")

    # Get applicant record
    applicant = frappe.db.get_value(
        "Applicant",
        {"email": user},
        ["name", "admission_cycle", "campus", "program", "annual_house_hold_income"],
        as_dict=True
    )
    if not applicant:
        frappe.throw("No applicant record found for your account.")

    # Duplicate check
    existing = frappe.db.exists("Scholarship Application", {
        "scholarship_scheme": scheme,
        "applicant_id": applicant.name
    })
    if existing:
        frappe.throw(f"You have already applied for this scholarship scheme.")

    # Validate scheme-type requirements using direct SQL (bypasses role permissions)
    scheme_data = frappe.db.sql("""
        SELECT scheme_type, income_certificate_required
        FROM `tabScholarship Scheme`
        WHERE name = %s LIMIT 1
    """, scheme, as_dict=True)
    if not scheme_data:
        frappe.throw("Scholarship Scheme not found.")
    scheme_data = scheme_data[0]
    is_need = scheme_data.scheme_type == "Need" and scheme_data.get("income_certificate_required")

    if is_need and not family_income:
        frappe.throw("Family income is required for Need-based scholarships.")
    if is_need and not income_certificate:
        frappe.throw("Income certificate is required for Need-based scholarships.")

    # Auto-use applicant's household income if not explicitly provided
    resolved_income = frappe.utils.flt(family_income or 0) or frappe.utils.flt(applicant.annual_house_hold_income or 0)

    # Create the application
    doc = frappe.new_doc("Scholarship Application")
    doc.scholarship_scheme = scheme
    doc.applicant_id = applicant.name
    doc.applicant_name = applicant.name
    doc.admission_cycle = applicant.admission_cycle
    doc.campus = applicant.campus
    doc.program = applicant.program
    doc.status = "Submitted"
    doc.family_income = resolved_income
    doc.income_certificate = income_certificate or ""
    doc.supporting_documents = supporting_documents or ""

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"name": doc.name, "status": doc.status}
