import frappe
import urllib.parse
from slcm.admission.utils.nlsat_portal import get_portal_login_url, get_portal_type_from_path
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response


def get_website_user_home_page(user):
    """Registered as the get_website_user_home_page hook.

    frappe.get_roles() special-cases Administrator to return EVERY Role in
    the system (see frappe/permissions.py), so Administrator always "holds"
    slcm_Faculty/slcm_Student/slcm_parent too. Without this override,
    get_home_page_via_hooks() would fall through to the role_home_page hook
    below and send Administrator to whichever portal role it happens to
    check first (e.g. /faculty-portal) instead of the desk. This hook is
    checked first, so returning "app" here for Administrator short-circuits
    that entirely; everyone else falls through to the normal role-based
    lookup unchanged.
    """
    if user == "Administrator":
        return "app"
    return None

class AuthRedirect(HTTPException):
    def __init__(self, location):
        super().__init__()
        self.location = location

    def get_response(self, environ=None):
        return Response(
            f'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">\n'
            f'<title>Redirecting...</title>\n'
            f'<h1>Redirecting...</h1>\n'
            f'<p>You should be redirected automatically to target URL: '
            f'<a href="{self.location}">{self.location}</a>. If not click the link.</p>',
            status=302,
            mimetype="text/html",
            headers={"Location": self.location}
        )

def intercept_login():
    try:
        path = frappe.local.request.path
    except Exception:
        path = (getattr(frappe.local, "path_info", "") or "").strip("/")
        if path:
            path = "/" + path

    if not path:
        return

    normalized_path = path.strip("/").lower()

    # Dynamically capture current URL including query params for redirect
    full_path = path
    try:
        if hasattr(frappe.local, "request") and frappe.local.request.query_string:
            query_string = frappe.local.request.query_string.decode('utf-8')
            if query_string:
                full_path += "?" + query_string

            encoded_url = urllib.parse.quote(full_path, safe='')

            if "pace" in path:
                raise AuthRedirect(f"/pace/login?redirect-to={encoded_url}")
                full_path = f"{path}?{query_string}"
    except Exception:
        pass

    # IMPORTANT: Prevent redirect loops if the current path is already a login path
    if "paceadmissions/login" in full_path.lower() or "admission/login" in full_path.lower():
        return

    encoded_url = urllib.parse.quote(full_path, safe='')

    # 0. Guard /paceadmissions route based on Applicant Portal Config
    if (normalized_path == "paceadmissions" or 
        normalized_path.startswith("paceadmissions/") or 
        normalized_path.startswith("pace-application-form")):
        
        # Don't block the login or forgot_password pages themselves
        if not (normalized_path.startswith("paceadmissions/login") or 
                normalized_path.startswith("paceadmissions/forgot_password")):
            
            enable_pace_site = frappe.db.get_single_value("Applicant Portal Config", "enable_pace_site")
            if not int(enable_pace_site or 0):
                # ONLY redirect guests to login. Logged-in users should be allowed to proceed
                # (or they will be stopped by standard permission checks if they don't have roles).
                if frappe.session.user == "Guest":
                    raise AuthRedirect(f"/paceadmissions/login?redirect-to={encoded_url}#register")

    # 1. Intercept Guest hitting protected Web Forms directly BEFORE Frappe drops the query params
    if frappe.session.user == "Guest":
        applicant_route = (frappe.get_cached_value("Web Form", "applicant-form", "route") or "nlsatadmissions/application-form").strip("/")
        pace_route = (frappe.get_cached_value("Web Form", "pace-application-form", "route") or "paceadmissions/application-form").strip("/")

        if (normalized_path.startswith(pace_route) or normalized_path.startswith("pace-application-form")):
            raise AuthRedirect(f"/paceadmissions/login?redirect-to={encoded_url}#register")
        elif (normalized_path.startswith(applicant_route) or normalized_path.startswith("applicant-form")):
            portal_type = "International" if frappe.form_dict.get("foriegn_national") == "Yes" else None
            raise AuthRedirect(f"{get_portal_login_url(portal_type)}?redirect-to={encoded_url}#register")

        if path.startswith("/student-portal") or path.startswith("/faculty-portal"):
            encoded_url = urllib.parse.quote(path, safe='')
            raise AuthRedirect(f"/portal-login?tab=faculty-student&redirect-to={encoded_url}")

        if path.startswith("/parent-portal"):
            encoded_url = urllib.parse.quote(path, safe='')
            raise AuthRedirect(f"/portal-login?tab=parent&redirect-to={encoded_url}")

    elif frappe.session.user != "Guest":
        applicant_route = (frappe.get_cached_value("Web Form", "applicant-form", "route") or "nlsatadmissions/application-form").strip("/")
        pace_route = (frappe.get_cached_value("Web Form", "pace-application-form", "route") or "paceadmissions/application-form").strip("/")
        
        is_application_form = False
        base_route = ""
        if normalized_path in (pace_route, f"{pace_route}/new", "pace-application-form", "pace-application-form/new"):
            is_application_form = True
            base_route = pace_route
        elif normalized_path in (applicant_route, f"{applicant_route}/new", "applicant-form", "applicant-form/new"):
            is_application_form = True
            base_route = applicant_route

        if is_application_form:
            active_cycle = frappe.db.get_value("Admission Cycle", {"status": "Active"}, ["name", "allow_multiple_applications"], as_dict=True)
            if active_cycle:
                requested_program = frappe.form_dict.get("program") or ""
                allow_multiple = int(active_cycle.allow_multiple_applications or 0)
                
                filters = {
                    "email": frappe.session.user,
                    "admission_cycle": active_cycle.name
                }
                
                if allow_multiple:
                    if requested_program:
                        filters["program"] = requested_program
                        existing_app = frappe.db.exists("Applicant", filters)
                        if existing_app:
                            raise AuthRedirect(f"/{base_route}/{existing_app}")
                else:
                    # If multiple applications are not allowed, ANY application in this cycle counts
                    # If requested_program is present, try to match it first just in case
                    if requested_program:
                        exact_match_filters = filters.copy()
                        exact_match_filters["program"] = requested_program
                        existing_app = frappe.db.exists("Applicant", exact_match_filters)
                        if existing_app:
                            raise AuthRedirect(f"/{base_route}/{existing_app}")
                    
                    # Otherwise get the most recent application
                    existing_app = frappe.db.get_value("Applicant", filters, "name", order_by="creation desc")
                    if existing_app:
                        raise AuthRedirect(f"/{base_route}/{existing_app}")

    # 2. Intercept the standard Frappe /login fallback. /login is left as
    # Frappe's own stock login page (username/password) — that's what
    # Administrator/System Users hit when accessing /app while logged out,
    # and it must keep working untouched. We only redirect AWAY from /login
    # when there's a clear signal this is a Student/Faculty/Parent visit
    # (via the logged_out_from cookie or a matching redirect-to), sending
    # those to the unified /portal-login page instead. Admission/PACE
    # Applicant logins remain separate (different audience, out of scope).
    # Anything else (desk, or no signal at all) falls through and renders
    # the default Frappe /login page as-is.
    if path == "/login":
        if frappe.session.user != "Guest":
            return

        # Check if we have a logged_out_from cookie
        logged_out_from = ""
        if hasattr(frappe.local, "request") and frappe.local.request:
            logged_out_from = frappe.local.request.cookies.get("logged_out_from") or ""

        # We must clear the cookie so it doesn't affect subsequent logins/actions
        if hasattr(frappe.local, "cookie_manager") and frappe.local.cookie_manager:
            frappe.local.cookie_manager.delete_cookie("logged_out_from")

        if logged_out_from:
            logged_out_from = urllib.parse.unquote(logged_out_from)

        if logged_out_from == "desk":
            # Show the standard/default Frappe login page (return without redirecting)
            return
        elif logged_out_from == "pace" or logged_out_from == "paceadmissions":
            raise AuthRedirect("/paceadmissions/login")
        elif logged_out_from == "admission":
            raise AuthRedirect(get_portal_login_url())
        elif logged_out_from == "student" or logged_out_from == "faculty":
            raise AuthRedirect("/portal-login?tab=faculty-student")
        elif logged_out_from == "parent":
            raise AuthRedirect("/portal-login?tab=parent")

        # Normal fallback if no logout cookie is found
        redirect_to = frappe.form_dict.get("redirect-to") or frappe.form_dict.get("redirect_to") or ""

        if "/paceadmissions/application-form" in redirect_to or "/pace/" in redirect_to or "/paceadmissions" in redirect_to:
            raise AuthRedirect(f"/paceadmissions/login?redirect-to={urllib.parse.quote(redirect_to, safe='')}")
        elif any(r in redirect_to for r in ("/applicant-form", "/admission/", "/nlsatadmissions", "/nlsat-international")):
            portal_type = get_portal_type_from_path(urllib.parse.urlparse(redirect_to).path)
            raise AuthRedirect(f"{get_portal_login_url(portal_type)}?redirect-to={urllib.parse.quote(redirect_to, safe='')}")
        elif "/student-portal" in redirect_to or "/faculty-portal" in redirect_to:
            raise AuthRedirect(f"/portal-login?tab=faculty-student&redirect-to={urllib.parse.quote(redirect_to, safe='')}")
        elif "/parent-portal" in redirect_to:
            raise AuthRedirect(f"/portal-login?tab=parent&redirect-to={urllib.parse.quote(redirect_to, safe='')}")

        # No portal signal at all (e.g. redirect-to=/app, or a bare /login
        # hit) — this is desk/admin territory, so show the default Frappe
        # login page instead of guessing.
        return

def enforce_student_google_login(login_manager=None):
    """Runs on every successful login (on_session_creation hook).

    Only acts on logins that came in through Google OAuth — normal
    username/password logins are left untouched. For Google logins it:
      1. Steps aside (does nothing) if this email matches a Faculty record, or
         a Parent (Student Parent child table) record — enforce_faculty_google_login
         / enforce_parent_google_login handle those cases instead. Without this
         check, every faculty/parent Google login would get rejected here first,
         since all three portals share the same generic Frappe OAuth callback and
         this hook has no way to know which login page the user started at.
      2. Rejects the session if Google login is disabled in settings.
      3. Rejects if the account's email domain isn't the allowed domain
         (e.g. only @nls.ac.in accounts, once NLSIU confirms their domain).
      4. Rejects if no Student Master record has this email as its
         `official_email_id`. NLSIU issues this institutional Gmail AFTER
         admission, separately from the personal email a student applied
         with (Student Master.user still holds that original application
         email at this point) — so matching must key off official_email_id,
         not `user`.
      5. On first successful Google login for a student, re-points
         Student Master.user to the official email (this Google-created
         User account) so all later permission checks / portal data use
         the real login identity. The original application-email User
         record is left untouched.
      6. Grants the slcm_Student role (if missing) and lets the session
         through, so downstream pages see a properly-permissioned student
         account instead of a bare, unlinked Google User.

    Rejection = log the Google-created session out immediately and bounce
    back to the student login page with a human-readable ?error= message.
    """
    from slcm.slcm.utils.parent_portal import get_parent_wards

    user = getattr(login_manager, "user", None) or frappe.session.user
    if not user or user == "Guest" or user == "Administrator":
        return

    request_path = getattr(frappe.local.request, "path", "") or ""
    is_google_oauth = "frappe.integrations.oauth2_logins.login_via_google" in request_path
    if not is_google_oauth:
        return

    if frappe.db.exists("Faculty", {"user_id": user}) or frappe.db.exists("Faculty", {"email": user}):
        return

    if get_parent_wards(user):
        return

    settings = frappe.get_single("Student Portal Settings")
    if not settings.get("enable_google_login"):
        _reject_google_login(
            login_manager, "Google login is not enabled for the student portal.", "/portal-login?tab=faculty-student"
        )
        return

    allowed_domain = (settings.get("google_login_allowed_domain") or "").strip().lower()
    email_domain = user.split("@")[-1].lower() if "@" in user else ""

    if allowed_domain and email_domain != allowed_domain:
        _reject_google_login(
            login_manager,
            f"Only @{allowed_domain} accounts can log in to the student portal.",
            "/portal-login?tab=faculty-student"
        )
        return

    student = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    if not student:
        _reject_google_login(
            login_manager,
            "No student record found for this email. Please contact administration.",
            "/portal-login?tab=faculty-student"
        )
        return

    # Point the Student Master at this Google-created User so future
    # logins/permissions/portal data resolve against the real login email.
    if frappe.db.get_value("Student Master", student, "user") != user:
        frappe.db.set_value("Student Master", student, "user", user)

    if not frappe.db.exists("Has Role", {"parent": user, "role": "slcm_Student"}):
        user_doc = frappe.get_doc("User", user)
        user_doc.append("roles", {"role": "slcm_Student"})
        user_doc.save(ignore_permissions=True)


def enforce_faculty_google_login(login_manager=None):
    """Runs on every successful login (on_session_creation hook).

    Faculty counterpart of enforce_student_google_login — see that function's
    docstring for why both hooks fire on every Google login regardless of
    which portal's login page initiated the OAuth flow.

    For Google logins on a Faculty account it:
      1. Steps aside if this email doesn't match any Faculty record — the
         account is not faculty, so enforce_student_google_login (or a
         rejection there) is authoritative instead.
      2. Rejects if Google login is disabled in Faculty Portal Settings.
      3. Rejects if the account's email domain isn't the allowed domain.
      4. Grants the slcm_Faculty role (if missing) and lets the session
         through.
    """
    user = getattr(login_manager, "user", None) or frappe.session.user
    if not user or user == "Guest" or user == "Administrator":
        return

    request_path = getattr(frappe.local.request, "path", "") or ""
    is_google_oauth = "frappe.integrations.oauth2_logins.login_via_google" in request_path
    if not is_google_oauth:
        return

    faculty = (
        frappe.db.get_value("Faculty", {"user_id": user}, "name")
        or frappe.db.get_value("Faculty", {"official_email_id": user}, "name")
        or frappe.db.get_value("Faculty", {"email": user}, "name")
    )
    if not faculty:
        return

    settings = frappe.get_single("Faculty Portal Settings")
    if not settings.get("enable_google_login"):
        _reject_google_login(
            login_manager, "Google login is not enabled for the faculty portal.", "/portal-login?tab=faculty-student"
        )
        return

    allowed_domain = (settings.get("google_login_allowed_domain") or "").strip().lower()
    email_domain = user.split("@")[-1].lower() if "@" in user else ""

    if allowed_domain and email_domain != allowed_domain:
        _reject_google_login(
            login_manager,
            f"Only @{allowed_domain} accounts can log in to the faculty portal.",
            "/portal-login?tab=faculty-student"
        )
        return

    if frappe.db.get_value("Faculty", faculty, "user_id") != user:
        frappe.db.set_value("Faculty", faculty, "user_id", user)

    if not frappe.db.exists("Has Role", {"parent": user, "role": "slcm_Faculty"}):
        user_doc = frappe.get_doc("User", user)
        user_doc.append("roles", {"role": "slcm_Faculty"})
        user_doc.save(ignore_permissions=True)


def enforce_parent_google_login(login_manager=None):
    """Runs on every successful login (on_session_creation hook).

    Parent counterpart of enforce_student_google_login / enforce_faculty_google_login
    — see enforce_student_google_login's docstring for why all three hooks fire
    on every Google login regardless of which portal's login page initiated
    the OAuth flow.

    Unlike Student/Faculty, parents have no standalone master doctype — a
    Google account is recognized as a parent purely by its email appearing on
    at least one Student Master's "Parents" child table (Student Parent.email).
    There is no per-parent link field to backfill (Student Parent has no
    "user" field), so this hook only needs to check and grant the role.

    For Google logins on a parent account it:
      1. Steps aside if this email matches no Student Parent row — the
         account is not a parent, so another hook (or a rejection there) is
         authoritative instead.
      2. Rejects if Google login is disabled in Parent Portal Settings.
      3. Rejects if the account's email domain isn't the allowed domain.
      4. Grants the slcm_parent role (if missing) and lets the session through.
    """
    from slcm.slcm.utils.parent_portal import get_parent_wards

    user = getattr(login_manager, "user", None) or frappe.session.user
    if not user or user == "Guest" or user == "Administrator":
        return

    request_path = getattr(frappe.local.request, "path", "") or ""
    is_google_oauth = "frappe.integrations.oauth2_logins.login_via_google" in request_path
    if not is_google_oauth:
        return

    if not get_parent_wards(user):
        return

    settings = frappe.get_single("Parent Portal Settings")
    if not settings.get("enable_google_login"):
        _reject_google_login(
            login_manager, "Google login is not enabled for the parent portal.", "/portal-login?tab=parent"
        )
        return

    allowed_domain = (settings.get("google_login_allowed_domain") or "").strip().lower()
    email_domain = user.split("@")[-1].lower() if "@" in user else ""

    if allowed_domain and email_domain != allowed_domain:
        _reject_google_login(
            login_manager,
            f"Only @{allowed_domain} accounts can log in to the parent portal.",
            "/portal-login?tab=parent"
        )
        return

    if not frappe.db.exists("Has Role", {"parent": user, "role": "slcm_parent"}):
        user_doc = frappe.get_doc("User", user)
        user_doc.append("roles", {"role": "slcm_parent"})
        user_doc.save(ignore_permissions=True)


def _reject_google_login(login_manager, message, redirect_page="/portal-login?tab=faculty-student"):
    """Tears down a just-created Google login session and bounces the
    browser back to the given login page with an error message.

    Must use AuthRedirect (a Werkzeug HTTPException), NOT frappe.Redirect —
    this runs deep inside Frappe's login internals (on_session_creation),
    which nothing catches frappe.Redirect from. AuthRedirect propagates as
    a normal HTTP 302 response regardless of which hook raises it.
    """
    user = getattr(login_manager, "user", None) or frappe.session.user
    frappe.local.login_manager.logout()
    frappe.set_user("Guest")
    frappe.db.commit()
    frappe.log_error(
        f"Rejected Google login for {user}: {message}",
        "Google login rejected"
    )
    raise AuthRedirect(f"{redirect_page}?error={urllib.parse.quote(message)}")


def handle_logout(login_manager=None):
    user = getattr(login_manager, "user", None) or frappe.session.user
    if not user or user == "Guest":
        return
        
    roles = frappe.get_roles(user)
    
    # Check referrer to see if they logged out from pace, admission or desk
    req = getattr(frappe.local, "request", None)
    referrer = req.headers.get("Referer", "") if req else ""
    
    target = None
    
    # 1. Referrer checks first for explicit paths
    if "/desk" in referrer or "/app" in referrer:
        target = "desk"
    elif "/paceadmissions" in referrer or "/pace" in referrer:
        target = "paceadmissions"
    elif "/admission" in referrer or "/nlsat" in referrer or "/applicant" in referrer:
        target = "admission"
    elif "/student-portal" in referrer or "/student/" in referrer:
        target = "student"
    elif "/faculty-portal" in referrer or "/faculty/" in referrer:
        target = "faculty"
    elif "/parent-portal" in referrer or "/parent/" in referrer:
        target = "parent"
    else:
        # 2. If referrer is ambiguous or other page, use roles:
        if "System Manager" in roles or "Desk User" in roles or user == "Administrator":
            target = "desk"
        elif "PACE Applicant" in roles:
            target = "paceadmissions"
        elif "Applicant" in roles:
            target = "admission"
        elif "slcm_student" in roles or "Student" in roles:
            target = "student"
        elif "slcm_faculty" in roles or "Faculty" in roles:
            target = "faculty"
        elif "slcm_parent" in roles or "Parent" in roles:
            target = "parent"
        else:
            target = "desk"
            
    if target and hasattr(frappe.local, "cookie_manager") and frappe.local.cookie_manager:
        frappe.local.cookie_manager.set_cookie("logged_out_from", target)

