import frappe


# ==========================================================
# STUDENT MASTER - STATUS-BASED ACCESS CONTROL
# ==========================================================
#
# Each registration-workflow role sees only the students that
# are currently in *their* workflow stage.
#
# Admin-level roles (System Manager, slcm_Registrar, Accounts User)
# see every record without restriction.
#
# slcm_Faculty / slcm_Programme Chair see all *academically active*
# students (academic_status = 'Active').
#
# slcm_Student sees only their own record (matched by email).

# Map  role  →  tuple of registration_status values visible to that role
_WORKFLOW_ROLE_STATUS_MAP = {
    "slcm_REGO Officer":          ("Pending REGO",),
    "slcm_FINO Officer":          ("Pending FINO",),
    # Registration Officer handles two stages: intake + final approval
    "slcm_Registration Officer":  ("Pending Registration", "Final Verification REGO"),
    "slcm_Documentation Officer": ("Pending Print & Scan",),
    "slcm_Hostel Admin":          ("Pending Residences",),
    "slcm_Hostel Warden":         ("Pending Residences",),
    "slcm_IT Admin":              ("Pending IT", "Final Verification REGO"),
    # Registration User only needs to see students awaiting submission
    "slcm_Registration User":     ("Selected",),
}

# Roles that can see *all* Student Master records
_FULL_ACCESS_ROLES = {"System Manager", "slcm_Registrar", "Accounts User"}

# Roles that see only academically-active students (scoped to the Classes they teach)
_ACTIVE_STUDENTS_ROLES = {"slcm_Faculty", "slcm_Programme Chair"}


def _get_faculty_name(user):
    """Return the Faculty.name linked to this user account, or None."""
    name = frappe.db.get_value("Faculty", {"user_id": user}, "name")
    return str(name) if name is not None else None


def _get_faculty_classes(faculty_name):
    """Return list of Classes names this faculty teaches, derived from
    Classes.faculty, Course Schedule.instructor, and Time Table.instructor."""
    primary = frappe.get_all(
        "Classes",
        filters={"faculty": faculty_name},
        pluck="name",
    )
    via_schedule = frappe.get_all(
        "Course Schedule",
        filters={"instructor": faculty_name, "docstatus": ["<", 2]},
        pluck="class_name",
    )
    via_timetable = frappe.get_all(
        "Time Table",
        filters={"instructor": faculty_name, "docstatus": ["<", 2]},
        pluck="class_name",
    )
    return list({c for c in (primary + via_schedule + via_timetable) if c})


def _get_faculty_assigned_students(faculty_name):
    """
    Return a list of Student Master names on the roster (Class Enrolled
    Student, status Enrolled) of any Class this faculty teaches.
    """
    classes = _get_faculty_classes(faculty_name)

    if not classes:
        return []

    students = frappe.db.sql("""
        SELECT DISTINCT se.student
        FROM `tabClass Enrolled Student` ces
        JOIN `tabStudent Enrollment` se ON se.name = ces.student_enrollment
        WHERE ces.parenttype = 'Classes' AND ces.parent IN %(classes)s
        AND ces.status = 'Enrolled' AND se.status = 'Enrolled'
    """, {"classes": classes}, pluck=True)

    return list(set(students))


def _escape_list(values):
    """Return a comma-separated SQL-safe string from a list of values."""
    return ", ".join(frappe.db.escape(str(v)) for v in values)


def student_master_query_conditions(user):
    """
    Called by Frappe for every Student Master list/search query.

    Returns a raw SQL WHERE fragment (without the WHERE keyword) or "" for
    unrestricted access.  Returning "1=0" denies access completely.
    """
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))

    # --- Full access ---
    if roles & _FULL_ACCESS_ROLES:
        return ""

    # --- Faculty: only students of the Classes they teach ---
    if "slcm_Faculty" in roles:
        faculty_name = _get_faculty_name(user)
        if not faculty_name:
            # Faculty record not linked to this user — deny all
            return "1=0"

        students = _get_faculty_assigned_students(faculty_name)
        if not students:
            # Faculty has no groups assigned yet — show no students
            return "1=0"

        safe_list = ", ".join(frappe.db.escape(s) for s in students)
        return (
            f"`tabStudent Master`.name IN ({safe_list})"
            f" AND `tabStudent Master`.academic_status = 'Active'"
        )

    # --- Programme Chair: all academically active students ---
    if "slcm_Programme Chair" in roles:
        return "`tabStudent Master`.academic_status = 'Active'"

    # --- Registration workflow roles: stage-specific view ---
    for role, statuses in _WORKFLOW_ROLE_STATUS_MAP.items():
        if role in roles:
            status_list = ", ".join(f"'{s}'" for s in statuses)
            return f"`tabStudent Master`.registration_status IN ({status_list})"

    # --- Student: own record only (matched by email) ---
    if "slcm_Student" in roles:
        safe_user = user.replace("'", "\\'")
        return f"`tabStudent Master`.email = '{safe_user}'"

    # Deny by default – unknown roles should not see Student Master
    return "1=0"


# ==========================================================
# ATTENDANCE SESSION – FACULTY SEES ONLY THEIR OWN SESSIONS
# ==========================================================

def attendance_session_query_conditions(user):
    """
    Faculty: sessions where they are the instructor OR the session's
    class is one they teach.
    Programme Chair / AAD / Admin: unrestricted.
    """
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))

    if roles & _FULL_ACCESS_ROLES or roles & {"slcm_Programme Chair", "AAD"}:
        return ""

    if "slcm_Faculty" in roles:
        faculty_name = _get_faculty_name(user)
        if not faculty_name:
            return "1=0"

        classes = _get_faculty_classes(faculty_name)
        safe_fac = frappe.db.escape(faculty_name)

        if not classes:
            # No classes yet — only show sessions where they are the direct instructor
            return f"`tabAttendance Session`.instructor = {safe_fac}"

        safe_classes = _escape_list(classes)
        return (
            f"(`tabAttendance Session`.class_name IN ({safe_classes})"
            f" OR `tabAttendance Session`.instructor = {safe_fac})"
        )

    return "1=0"


# ==========================================================
# STUDENT ATTENDANCE – FACULTY SEES ONLY THEIR GROUPS
# ==========================================================

def student_attendance_query_conditions(user):
    """
    Faculty: records for students in their assigned student list.
    Programme Chair / Admin: unrestricted.
    """
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))

    if roles & _FULL_ACCESS_ROLES or "slcm_Programme Chair" in roles:
        return ""

    if "slcm_Faculty" in roles:
        faculty_name = _get_faculty_name(user)
        if not faculty_name:
            return "1=0"

        students = _get_faculty_assigned_students(faculty_name)
        if not students:
            return "1=0"

        safe_students = _escape_list(students)
        return f"`tabStudent Attendance`.student IN ({safe_students})"

    if "slcm_Student" in roles:
        safe_user = frappe.db.escape(user)
        return (
            f"`tabStudent Attendance`.student IN ("
            f"SELECT name FROM `tabStudent Master` WHERE email = {safe_user})"
        )

    return "1=0"


# ==========================================================
# ATTENDANCE LOG – FACULTY SEES LOGS FOR THEIR STUDENTS
# ==========================================================

def attendance_log_query_conditions(user):
    """
    Faculty: logs where the linked student is in their assigned student list.
    Programme Chair / Admin: unrestricted.
    """
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))

    if roles & _FULL_ACCESS_ROLES or "slcm_Programme Chair" in roles:
        return ""

    if "slcm_Faculty" in roles:
        faculty_name = _get_faculty_name(user)
        if not faculty_name:
            return "1=0"

        students = _get_faculty_assigned_students(faculty_name)
        if not students:
            return "1=0"

        safe_students = _escape_list(students)
        return f"`tabAttendance Log`.student IN ({safe_students})"

    return "1=0"


# ==========================================================
# ATTENDANCE SUMMARY – FACULTY SEES THEIR GROUPS' SUMMARIES
# ==========================================================

def attendance_summary_query_conditions(user):
    """
    Faculty: summaries for the Classes they teach.
    Programme Chair / Admin: unrestricted.
    Student: own summary only.
    """
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))

    if roles & _FULL_ACCESS_ROLES or "slcm_Programme Chair" in roles:
        return ""

    if "slcm_Faculty" in roles:
        faculty_name = _get_faculty_name(user)
        if not faculty_name:
            return "1=0"

        classes = _get_faculty_classes(faculty_name)
        if not classes:
            return "1=0"

        safe_classes = _escape_list(classes)
        return f"`tabAttendance Summary`.class_name IN ({safe_classes})"

    if "slcm_Student" in roles:
        safe_user = frappe.db.escape(user)
        return (
            f"`tabAttendance Summary`.student IN ("
            f"SELECT name FROM `tabStudent Master` WHERE email = {safe_user})"
        )

    return "1=0"


# ==========================================================
# STUDENT ATTENDANCE CONDONATION – FACULTY SEES THEIR STUDENTS
# ==========================================================

def attendance_condonation_query_conditions(user):
    """
    Faculty: condonations for students in their assigned groups.
    Programme Chair / Admin: unrestricted.
    Student: own condonations only.
    """
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))

    if roles & _FULL_ACCESS_ROLES or "slcm_Programme Chair" in roles:
        return ""

    conditions = []

    if "slcm_Faculty" in roles:
        faculty_name = _get_faculty_name(user)
        if faculty_name:
            students = _get_faculty_assigned_students(faculty_name)
            if students:
                safe_students = _escape_list(students)
                conditions.append(f"`tabStudent Attendance Condonation`.student IN ({safe_students})")

    if "slcm_Student" in roles:
        safe_user = frappe.db.escape(user)
        conditions.append(
            f"`tabStudent Attendance Condonation`.student IN ("
            f"SELECT name FROM `tabStudent Master` WHERE email = {safe_user})"
        )
        
    if "AAD" in roles:
        conditions.append(f"`tabStudent Attendance Condonation`.aad_approver = {frappe.db.escape(user)}")
        
    if "Programme Chair" in roles:
        conditions.append(f"`tabStudent Attendance Condonation`.programme_chair_approver = {frappe.db.escape(user)}")

    if not conditions:
        return "1=0"

    return "(" + " OR ".join(conditions) + ")"


# ==========================================================
# FA MFA APPLICATION – FACULTY SEES THEIR STUDENTS' APPLICATIONS
# ==========================================================

def fa_mfa_application_query_conditions(user):
    """
    Faculty: applications for students in their assigned groups.
    Programme Chair / Admin: unrestricted.
    Student: own applications only.
    """
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))

    if roles & _FULL_ACCESS_ROLES or "slcm_Programme Chair" in roles:
        return ""

    if "slcm_Faculty" in roles:
        faculty_name = _get_faculty_name(user)
        if not faculty_name:
            return "1=0"

        students = _get_faculty_assigned_students(faculty_name)
        if not students:
            return "1=0"

        safe_students = _escape_list(students)
        return f"`tabFA MFA Application`.student IN ({safe_students})"

    if "slcm_Student" in roles:
        safe_user = frappe.db.escape(user)
        return (
            f"`tabFA MFA Application`.student IN ("
            f"SELECT name FROM `tabStudent Master` WHERE email = {safe_user})"
        )

    return "1=0"


# ==========================================================
# TIME TABLE – FACULTY SEES ONLY THEIR ASSIGNED GROUPS
# ==========================================================

def class_schedule_query_conditions(user):
    """
    Faculty: schedules for the Classes they teach OR where they are the
    direct instructor.
    Programme Chair / AAD / Admin: unrestricted (AAD reopens locked
    attendance from the Time Table entry).
    """
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))

    if roles & _FULL_ACCESS_ROLES or roles & {"slcm_Programme Chair", "AAD"}:
        return ""

    if "slcm_Faculty" in roles:
        faculty_name = _get_faculty_name(user)
        if not faculty_name:
            return "1=0"

        classes = _get_faculty_classes(faculty_name)
        safe_fac = frappe.db.escape(faculty_name)

        if not classes:
            return f"`tabTime Table`.instructor = {safe_fac}"

        safe_classes = _escape_list(classes)
        return (
            f"(`tabTime Table`.class_name IN ({safe_classes})"
            f" OR `tabTime Table`.instructor = {safe_fac})"
        )

    return "1=0"


# ==========================================================
# APPLICANT – EMAIL-BASED RESTRICTION
# ==========================================================

def applicant_query_conditions(user):

    roles = frappe.get_roles(user)

    # Full access roles
    if "Administrator" in roles or "Entrance Test Admin" in roles:
        return ""

    # Applicant role restriction
    if "Applicant" in roles:
        return f"`tabApplicant`.email = '{user}'"

    return ""


# ==========================================================
# ENTRANCE TEST PROVIDER – SELF RECORD ONLY
# ==========================================================

def entrance_test_provider_query_conditions(user):

    if user == "Administrator":
        return ""

    roles = frappe.get_roles(user)

    if "Entrance Test Provider" in roles:

        provider_name = frappe.db.get_value(
            "Entrance Test Provider",
            {"user": user},
            "name"
        )

        if not provider_name:
            return "1=0"

        return f"`tabEntrance Test Provider`.name = '{provider_name}'"

    return ""


# ==========================================================
# ENTRANCE TEST SEAT ALLOCATION – STRICT PROVIDER FILTER
# ==========================================================

def seat_allocation_query_conditions(user):

    if user == "Administrator":
        return ""

    roles = frappe.get_roles(user)

    if "Entrance Test Admin" in roles:
        return ""

    if "Entrance Test Provider" in roles:

        provider_name = frappe.db.get_value(
            "Entrance Test Provider",
            {"user": user},
            "name"
        )

        if not provider_name:
            return "1=0"

        return f"`tabEntrance Test Seat Allocation`.entrance_test_provider = '{provider_name}'"

    if "Applicant" in roles:
        return f"`tabEntrance Test Seat Allocation`.email = '{user}'"

    return ""


# ==========================================================
# INTERVIEW STAFF MEMBER – SELF RECORD ONLY
# ==========================================================

def interview_staff_member_query_conditions(user):

    if user == "Administrator":
        return ""

    roles = frappe.get_roles(user)

    if "Interview Staff Member" in roles:

        staff_name = frappe.db.get_value(
            "Interview Staff Member",
            {"user": user},
            "name"
        )

        if not staff_name:
            return "1=0"

        return f"`tabInterview Staff Member`.name = '{staff_name}'"

    return ""


# ==========================================================
# INTERVIEW SEAT ALLOCATION – ROLE-BASED FILTER
# ==========================================================

def interview_seat_allocation_query_conditions(user):

    if user == "Administrator":
        return ""

    roles = frappe.get_roles(user)

    if "Applicant" in roles:
        return f"`tabInterview Seat Allocation`.email = '{user}'"

    if "Interview Staff Member" in roles:

        staff_name = frappe.db.get_value(
            "Interview Staff Member",
            {"user": user},
            "name"
        )

        if not staff_name:
            return "1=0"

        return f"`tabInterview Seat Allocation`.interview_staff_member = '{staff_name}'"

    return ""


# ==========================================================
# VENUE BOOKING – ROLE-BASED ACCESS CONTROL
# ==========================================================
#
# Admin roles (System Manager, Administrator, slcm_Registrar):
#   → See ALL bookings from every user.
#
# Faculty, Staff, Student, and any other role:
#   → See ONLY their own bookings (owner = current user).

def venue_booking_query_conditions(user):
    """
    Called by Frappe for every Venue Booking list/search query.
    Returns a raw SQL WHERE fragment (without the WHERE keyword)
    or "" for unrestricted access.
    """
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))

    # Admin roles see everything
    admin_roles = {"System Manager", "slcm_Registrar"}
    if admin_roles & roles:
        return ""

    # Everyone else (Faculty, Staff, Student, etc.) sees only their own bookings
    safe_user = frappe.db.escape(user)
    return f"`tabVenue Booking`.owner = {safe_user}"
