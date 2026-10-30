import frappe
from slcm.slcm.doctype.faculty_portal_settings.faculty_portal_settings import (
    get_faculty_portal_settings,
)


def get_faculty_name():
    """Faculty doc name for the current session user, as a string.

    Faculty is autoincrement-named, so the raw lookup returns an int; Link
    fields (Classes.faculty, Attendance Session.instructor, ...) hold the
    name as a string, and comparing the two would never match.
    """
    name = _find_faculty_name()
    return str(name) if name is not None else None


def _find_faculty_name():
    """
    Return the Faculty doc name for the current session user, as a string.

    Faculty is named by autoincrement, so the database hands back an int (1)
    while Link fields (Classes.faculty, ...) hold the text "1". Returning a
    string keeps ownership checks like `cls.faculty != faculty_name` correct.
    """
    name = _lookup_faculty_name()
    return str(name) if name is not None else None


def _lookup_faculty_name():
    """
    Return the Faculty doc name for the current session user.

    Tries six strategies in order:
      1. Faculty.user_id           == session user  (fastest, canonical)
      2. Faculty.official_email_id == session user  (institutional/Google login email)
      3. Faculty.email             == session user  (common setup path)
      4. Faculty.official_email_id == User.email     }
      5. Faculty.email             == User.email     } handle aliased logins
      6. Faculty.user_id           == User.email     }
      7. Admin/System Manager preview — returns first active Faculty record
         so administrators can preview the portal without a personal Faculty record.

    On first successful match via strategies 2-6, back-fills user_id so
    future lookups hit strategy 1.
    """
    user = frappe.session.user
    if not user or user == "Guest":
        return None

    # Strategy 1 — user_id direct match (fastest path)
    name = frappe.db.get_value("Faculty", {"user_id": user}, "name")
    if name:
        return name

    # Strategy 2 — official email direct match (institutional/Google login email)
    name = frappe.db.get_value("Faculty", {"official_email_id": user}, "name")
    if name:
        _backfill_user_id(name, user)
        return name

    # Strategy 3 — email field direct match
    name = frappe.db.get_value("Faculty", {"email": user}, "name")
    if name:
        _backfill_user_id(name, user)
        return name

    # Strategies 4-6 — look up the User doc's email (handles SSO / aliased logins)
    try:
        user_email = frappe.db.get_value("User", user, "email")
        if user_email and user_email != user:
            name = frappe.db.get_value("Faculty", {"official_email_id": user_email}, "name")
            if name:
                _backfill_user_id(name, user)
                return name
            name = frappe.db.get_value("Faculty", {"email": user_email}, "name")
            if name:
                _backfill_user_id(name, user)
                return name
            name = frappe.db.get_value("Faculty", {"user_id": user_email}, "name")
            if name:
                _backfill_user_id(name, user)
                return name
    except Exception:
        pass

    # Strategy 7 — admin/system-manager preview using any active Faculty record
    if _is_admin_user(user):
        name = frappe.db.get_value("Faculty", {"status": "Active"}, "name", order_by="name asc")
        if name:
            return name

    return None


def _is_admin_user(user):
    """Return True if the user holds the Administrator or System Manager role."""
    if user == "Administrator":
        return True
    try:
        roles = frappe.get_roles(user)
        return "System Manager" in roles or "Administrator" in roles
    except Exception:
        return False


def is_admin_preview(user=None):
    """
    Return True when the current user is viewing the portal in admin-preview mode
    (i.e. they are an admin/system manager with no personal Faculty record).
    """
    if user is None:
        user = frappe.session.user
    if not user or user == "Guest":
        return False
    if not _is_admin_user(user):
        return False
    # They have a real faculty record — not preview mode
    direct = (
        frappe.db.get_value("Faculty", {"user_id": user}, "name")
        or frappe.db.get_value("Faculty", {"email": user}, "name")
    )
    return not direct


def _backfill_user_id(faculty_name, user):
    """Write user_id onto the Faculty record so strategy 1 hits next time."""
    try:
        if not frappe.db.get_value("Faculty", faculty_name, "user_id"):
            frappe.db.set_value(
                "Faculty", faculty_name, "user_id", user, update_modified=False
            )
    except Exception:
        pass


def set_faculty_nav(context, faculty):
    full_name = " ".join(filter(None, [faculty.first_name, faculty.last_name]))
    context.faculty_name = full_name or faculty.name
    context.faculty_id = faculty.faculty_id or faculty.name
    context.faculty_photo = faculty.photo or ""
    context.faculty_initial = (context.faculty_name[0]).upper() if context.faculty_name else "F"
    context.faculty_email = faculty.email or frappe.session.user
    context.faculty_designation = faculty.designation or ""
    context.faculty_department = (
        frappe.db.get_value("SLCM Department", faculty.department, "department_name")
        if faculty.department
        else faculty.department or ""
    )


def set_portal_settings(context):
    """Load Faculty Portal Settings into context.fp_settings for template use."""
    try:
        context.fp_settings = get_faculty_portal_settings()
    except Exception:
        context.fp_settings = {}
    context.is_admin_preview = is_admin_preview()


def set_nav_defaults(context):
    user = frappe.session.user
    user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
    context.faculty_name = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.faculty_id = ""
    context.faculty_photo = (user_doc.user_image if user_doc else "") or ""
    context.faculty_initial = (context.faculty_name[0]).upper() if context.faculty_name else "F"
    context.faculty_email = user
    context.faculty_designation = ""
    context.faculty_department = ""


def fmt_time(t):
    if not t:
        return ""
    try:
        if hasattr(t, "seconds"):
            total = int(t.seconds)
            h, rem = divmod(total, 3600)
            m = rem // 60
        else:
            parts = str(t).split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
        suffix = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {suffix}"
    except Exception:
        return str(t)
