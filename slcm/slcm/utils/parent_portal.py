import frappe
from slcm.slcm.doctype.parent_portal_settings.parent_portal_settings import get_parent_portal_settings


def get_parent_wards(email):
    """
    Return the list of Student Master names for which the given email
    appears as a parent/guardian (Student Parent child table row).
    Empty list if the email matches no one — i.e. this account is not a parent.
    """
    if not email:
        return []
    return frappe.db.sql_list(
        """
        SELECT sm.name
        FROM   `tabStudent Master` sm
        INNER JOIN `tabStudent Parent` sp
               ON sp.parent = sm.name AND sp.parenttype = 'Student Master'
        WHERE  sp.email = %s
        """,
        email,
    )


_WARD_FIELDS = """
    sm.name, sm.first_name, sm.last_name, sm.programme,
    sm.programme_of_study, sm.batch_year, sm.student_status,
    sm.passport_size_photo, sm.academic_year, sm.academic_term
"""

PREVIEW_ROLES = ("System Manager",)


def can_preview_portal(user=None):
    """Administrator / System Manager may preview the parent portal."""
    user = user or frappe.session.user
    if user == "Guest":
        return False
    return user == "Administrator" or bool(set(PREVIEW_ROLES) & set(frappe.get_roles(user)))


def _get_preview_rows(context):
    """Pick the student an admin previews the portal for.

    ?ward=<Student Master> chooses the student; otherwise the first student
    with a linked parent (falling back to any student). Returns [] when the
    site has no students yet.
    """
    requested = frappe.request.args.get("ward") if frappe.request else None
    row = None
    if requested:
        row = _fetch_ward_row("WHERE sm.name = %s", (requested,))
        if not row:
            context.preview_notice = f"Student {requested} was not found — showing another student instead."
    if not row:
        row = _fetch_ward_row(
            """WHERE EXISTS (SELECT 1 FROM `tabStudent Parent` sp
                             WHERE sp.parent = sm.name AND sp.parenttype = 'Student Master'
                               AND IFNULL(sp.email, '') != '')""",
            (),
        ) or _fetch_ward_row("", ())
    if not row:
        return []

    context.is_preview = True
    context.preview_students = frappe.db.sql(
        """
        SELECT sm.name, TRIM(CONCAT(IFNULL(sm.first_name, ''), ' ', IFNULL(sm.last_name, ''))) AS full_name
        FROM   `tabStudent Master` sm
        ORDER  BY (EXISTS (SELECT 1 FROM `tabStudent Parent` sp
                           WHERE sp.parent = sm.name AND sp.parenttype = 'Student Master'
                             AND IFNULL(sp.email, '') != '')) DESC,
                  sm.modified DESC
        LIMIT  500
        """,
        as_dict=True,
    )
    return [row]


def _fetch_ward_row(where, values):
    rows = frappe.db.sql(
        f"SELECT {_WARD_FIELDS} FROM `tabStudent Master` sm {where} ORDER BY sm.first_name LIMIT 1",
        values,
        as_dict=True,
    )
    return rows[0] if rows else None


def get_parent_context(context):
    """
    Shared setup for all parent portal pages.
    Resolves which student(s) the logged-in user is a parent of,
    sets nav variables, and returns the active Student Master doc.

    Returns the active Student Master doc, or None if not a parent.
    """
    context.no_cache = 1

    user = frappe.session.user
    if user == "Guest":
        context.is_guest = True
        context.not_a_parent = False
        try:
            context.pp_settings = get_parent_portal_settings()
        except Exception:
            context.pp_settings = {}
        return None

    context.is_guest = False

    # Find all students where this user's email is in the parents child table
    rows = frappe.db.sql(
        f"""
        SELECT {_WARD_FIELDS}
        FROM   `tabStudent Master` sm
        INNER JOIN `tabStudent Parent` sp
               ON sp.parent = sm.name AND sp.parenttype = 'Student Master'
        WHERE  sp.email = %s
        ORDER  BY sm.first_name
        """,
        user,
        as_dict=True,
    )

    # Admins who aren't parents get a read-only preview as one student's parent
    context.is_preview = False
    if not rows and can_preview_portal(user):
        rows = _get_preview_rows(context)

    if not rows:
        context.not_a_parent = True
        context.is_guest = False
        context.parent_display_name = ""
        context.parent_initial = "?"
        try:
            context.pp_settings = get_parent_portal_settings()
        except Exception:
            context.pp_settings = {}
        return None

    context.not_a_parent = False

    # Parent display name from Frappe User
    user_doc = frappe.db.get_value("User", user, ["first_name", "last_name", "full_name"], as_dict=True)
    if user_doc:
        context.parent_display_name = (
            user_doc.full_name
            or f"{user_doc.first_name or ''} {user_doc.last_name or ''}".strip()
            or user
        )
    else:
        context.parent_display_name = user
    context.parent_initial = (context.parent_display_name or "P")[0].upper()

    context.wards = rows

    # Active ward: from ?ward= query param, default to first
    active_ward = frappe.request.args.get("ward") if frappe.request else None
    ward_names = [r.name for r in rows]
    if active_ward not in ward_names:
        active_ward = ward_names[0]

    context.active_ward = active_ward

    student = next((r for r in rows if r.name == active_ward), rows[0])
    context.ward_name = f"{student.first_name} {student.last_name or ''}".strip()
    context.ward_initial = (student.first_name or "S")[0].upper()
    context.ward_photo = student.passport_size_photo or ""
    context.ward_status = student.student_status or ""

    # Programme display name
    context.ward_programme = ""
    if student.programme:
        prog_name = frappe.db.get_value("Batch", student.programme, "cohort_name")
        context.ward_programme = prog_name or student.programme
    elif student.programme_of_study:
        prog_name = frappe.db.get_value("Programme", student.programme_of_study, "program_name")
        context.ward_programme = prog_name or student.programme_of_study

    context.ward_batch = student.batch_year or ""
    context.ward_academic_year = student.academic_year or ""
    context.ward_term = student.academic_term or ""

    # Every portal link must carry the active ward, otherwise navigating
    # (e.g. back to the dashboard) silently falls back to the first ward.
    context.ward_qs = f"?ward={active_ward}"

    # Inject portal settings so all pages can access pp_settings in templates
    try:
        context.pp_settings = get_parent_portal_settings()
    except Exception:
        context.pp_settings = {}

    return frappe.get_doc("Student Master", active_ward, ignore_permissions=True)
