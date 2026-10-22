import os
import base64
import mimetypes

import frappe
from slcm.admission.utils.nlsat_portal import get_portal_base, get_portal_login_url
from frappe import _
from frappe.utils import random_string
from frappe.core.doctype.user.user import sign_up


def _photo_as_data_uri(photo_url):
    """Read a Frappe file (public or private) from disk and return a base64 data URI.
    This avoids wkhtmltopdf having to make HTTP requests (which often fail on localhost).
    """
    if not photo_url:
        return None
    try:
        if photo_url.startswith("/private/files/"):
            rel = photo_url[len("/private/files/"):]
            file_path = os.path.abspath(frappe.get_site_path("private", "files", rel))
        elif photo_url.startswith("/files/"):
            rel = photo_url[len("/files/"):]
            file_path = os.path.abspath(frappe.get_site_path("public", "files", rel))
        else:
            return None
        if not os.path.exists(file_path):
            return None
        with open(file_path, "rb") as f:
            data = f.read()
        mime_type = mimetypes.guess_type(file_path)[0] or "image/jpeg"
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:{mime_type};base64,{b64}"
    except Exception:
        return None


def get_reset_password_link(user_doc, send_email=False):
    if hasattr(user_doc, "_reset_password"):
        return user_doc._reset_password(send_email=send_email)
    elif hasattr(user_doc, "reset_password"):
        import inspect
        sig = inspect.signature(user_doc.reset_password)
        if "send_email" in sig.parameters:
            return user_doc.reset_password(send_email=send_email)
        else:
            return user_doc.reset_password()
    else:
        from frappe.utils import get_url, now_datetime
        try:
            from frappe.core.doctype.user.user import sha256_hash
        except ImportError:
            from frappe.utils import sha256_hash
        key = frappe.generate_hash()
        hashed_key = sha256_hash(key)
        user_doc.db_set("reset_password_key", hashed_key)
        user_doc.db_set("last_reset_password_key_generated_on", now_datetime())
        url = "/update-password?key=" + key
        link = get_url(url, allow_header_override=False)
        if send_email:
            user_doc.password_reset_mail(link)
        return link


def send_welcome_or_custom_signup_email(user_doc, correct_link, template="new_user"):
    institution = frappe.get_single("Institution Settings")
    enable_custom = getattr(institution, "enable_signup_email", 0)
    has_custom_template = frappe.db.exists("Email Template", "Applicant Registration Email")
    
    if enable_custom or has_custom_template:
        full_name = user_doc.full_name or user_doc.first_name or user_doc.email
        
        # Context for rendering
        context = {
            "institution_name": getattr(institution, "institution_name", "") or "National Law School of India University",
            "logo": getattr(institution, "logo", ""),
            "full_name": full_name,
            "candidate_name": full_name,
            "applicant_name": full_name,
            "first_name": user_doc.first_name or full_name,
            "set_password_link": correct_link,
            "login_url": getattr(institution, "login_url", "") or frappe.utils.get_url(get_portal_login_url()),
            "support_email": getattr(institution, "support_email", ""),
            "link_expiry_hours": getattr(institution, "link_expiry_hours", 24) or 24,
            "doc": user_doc,
        }

        # Check if standard Email Template 'Applicant Registration Email' exists
        subject = None
        message = None
        sender = None

        if frappe.db.exists("Email Template", "Applicant Registration Email"):
            try:
                tmpl = frappe.get_doc("Email Template", "Applicant Registration Email")
                tmpl.flags.ignore_permissions = True
                subject = tmpl.get_formatted_subject(context)
                message = tmpl.get_formatted_response(context)
                if tmpl.email_account:
                    sender = frappe.db.get_value("Email Account", tmpl.email_account, "email_id") or tmpl.email_account
            except Exception as e:
                frappe.log_error(title="SLCM Email Template Render Error", message=frappe.get_traceback())

        if not message:
            # Fallback to Institution Settings fields
            subject_template = getattr(institution, "signup_email_subject", "")
            if not subject_template:
                subject_template = "Welcome to {{ institution_name }}"
                
            try:
                subject = frappe.render_template(subject_template, context)
            except Exception:
                subject = "Welcome to " + (getattr(institution, "institution_name", "") or "National Law School of India University")

            message_template = getattr(institution, "signup_email_template", "")
            if message_template:
                try:
                    message = frappe.render_template(message_template, context)
                except Exception as e:
                    frappe.log_error(title="SLCM Custom Signup Email Render Error", message=frappe.get_traceback())

        if message:
            frappe.sendmail(
                recipients=[user_doc.email],
                sender=sender,
                subject=subject,
                message=message,
                now=True
            )
            user_doc.flags.email_sent = 1
            return True
                
    # Fallback to standard welcome email
    site_name = (
        frappe.db.get_default("site_name")
        or (frappe.get_conf().get("site_name") if frappe.get_conf() else None)
        or "Admissions Portal"
    )
    subject = f"Welcome to {site_name} — Set your password"
    welcome_email_template = frappe.db.get_system_setting("welcome_email_template")
    user_doc.send_login_mail(
        subject,
        template,
        dict(
            link=correct_link,
            site_url=frappe.utils.get_url(),
            doc=user_doc,
            candidate_name=user_doc.full_name or user_doc.first_name,
            full_name=user_doc.full_name or user_doc.first_name,
            first_name=user_doc.first_name,
            set_password_link=correct_link,
            reset_password_link=correct_link,
        ),
        custom_template=welcome_email_template,
    )
    return False


@frappe.whitelist(allow_guest=True)
def register_fle_user(email, mobile_number=None):
    if not email:
        frappe.throw(_("Email is mandatory"))

    if frappe.db.exists("User", email):
        frappe.throw(_("User with this email already exists."))
        
    user_dict = {
        "doctype": "User",
        "email": email,
        "first_name": email.split('@')[0],
        "enabled": 1,
        "new_password": random_string(10),
        "user_type": "Website User",
        "send_welcome_email": 0,
        "redirect_url": "/fle/login.html",
    }
    if mobile_number:
        user_dict["mobile_no"] = mobile_number

    user = frappe.get_doc(user_dict)
    
    user.flags.ignore_permissions = True
    user.flags.ignore_password_policy = True
    user.insert()

    # Clear internal __new_password to prevent subsequent save (like add_roles) from sending Security Alert email
    if hasattr(user, "_User__new_password"):
        user._User__new_password = None
    if hasattr(user, "__new_password"):
        user.__new_password = None

    # Track that this user is a new signup to suppress Security Alert email during first password setup
    frappe.cache().hset("newly_signup_user", user.name, 1)

    # Generate the password reset link silently (without emailing)
    frappe_link = get_reset_password_link(user, send_email=False)

    # Disable expiration for "Complete Registration" link by setting generation date 10 years in the future
    from frappe.utils import add_days, now_datetime
    user.db_set("last_reset_password_key_generated_on", add_days(now_datetime(), 3650))
    
    # Extract the path + query (e.g., /update-password?key=XYZ)
    import urllib.parse
    parsed = urllib.parse.urlparse(frappe_link)
    
    # Rebuild the link using frappe.utils.get_url which picks up the request host/port correctly,
    # but point it to our custom page.
    from frappe.utils import get_url
    correct_link = get_url(f"/fle/update_password.html?{parsed.query}")
    
    # Prepare and send the welcome email
    send_welcome_or_custom_signup_email(user, correct_link, template="fle_new_user")

    # default_role = frappe.get_single_value("Portal Settings", "default_role")
    # if default_role:
    #     user.add_roles(default_role)

    # Reliable fallback cache assignment
    frappe.cache().hset("redirect_after_login", user.name, "/fle/login.html")
    
    return {"status": "success", "message": "Check your email to set your password and activate your account!"}

# (duplicate custom_sign_up removed)

@frappe.whitelist(allow_guest=True, methods=["POST"])
def update_password_fle(new_password, key, confirm_password=None):
    # Call the core update_password function
    from frappe.core.doctype.user.user import update_password, User
    from frappe.utils import sha256_hash

    target_user = frappe.db.get_value("User", {"reset_password_key": sha256_hash(key)}, "name")
    is_new_signup = frappe.cache().hget("newly_signup_user", target_user) if target_user else False

    original_set_new_password = None
    if is_new_signup and hasattr(User, "set_new_password"):
        original_set_new_password = User.set_new_password
        def custom_set_new_password(self, new_password=None):
            if new_password and not self.flags.in_insert:
                from frappe.core.doctype.user.user import _update_password
                _update_password(user=self.name, pwd=new_password, logout_all_sessions=self.logout_all_sessions)
        User.set_new_password = custom_set_new_password
        frappe.cache().hdel("newly_signup_user", target_user)

    try:
        # This will log the user in and return a redirect URL (usually /me or /desk)
        core_redirect = update_password(new_password=new_password, key=key)
    finally:
        if original_set_new_password:
            User.set_new_password = original_set_new_password

    # We want to force redirect to the FLE form
    user = frappe.session.user
    if user == "Guest":
        # If somehow not logged in, just go to login
        return "/fle/login.html"

    user_doc = frappe.get_doc("User", user)
    email = user_doc.email or ""
    mobile = user_doc.mobile_no or ""

    # Store prefill data server-side so the URL stays clean (email only)
    frappe.cache().hset("fle_prefill", user, {"email": email})

    # If the user has a paid FLE application, send them to the enrolled dashboard
    paid_doc = frappe.db.get_value(
        "Foundations for a Legal Education",
        {"email_address": email, "payment_status": ["in", ["Authorized", "Paid", "Captured"]]},
        "name",
    )
    if paid_doc:
        return "/fle/enrolled"

    # If the user has an unpaid/incomplete document, redirect to continue it
    existing_doc = frappe.db.get_value(
        "Foundations for a Legal Education",
        {"email_address": email, "payment_status": ["not in", ["Authorized", "Paid", "Captured"]]},
        "name",
    )
    if existing_doc:
        return f"/foundations-for-a-legal-education/{existing_doc}"
    return "/foundations-for-a-legal-education/new"

@frappe.whitelist(allow_guest=True, methods=["POST"])
def reset_password_fle(user: str):
    """FLE forgot-password: same response shape as reset_password for consistent UI handling."""
    try:
        user_doc = frappe.get_doc("User", user)
        if user_doc.name == "Administrator":
            return {
                "status": "not_allowed",
                "message": _("Password reset is not allowed for this account."),
            }
        if not user_doc.enabled:
            return {"status": "disabled", "message": _("This account has been disabled.")}

        user_doc.validate_reset_password()
        
        # Generate just the key without sending email yet
        frappe_link = get_reset_password_link(user_doc, send_email=False)
        
        import urllib.parse
        parsed = urllib.parse.urlparse(frappe_link)
        
        from frappe.utils import get_url
        correct_link = get_url(f"/fle/update_password.html?{parsed.query}")
        
        try:
            logo_path = os.path.abspath(frappe.get_site_path("public", "files", "nlsiu-logo.jpg"))
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode("utf-8")
            logo_src = f"data:image/jpeg;base64,{logo_b64}"
        except Exception:
            logo_src = ""

        base_url = get_url()

        user_doc.send_login_mail(
            _("Password Reset"),
            "fle_password_reset",
            {"link": correct_link, "site_url": base_url, "logo_src": logo_src},
            now=True,
        )

        return {
            "status": "ok",
            "message": _(
                "We have sent a password reset link to {0}. Check your inbox and spam folder."
            ).format(user_doc.email or user_doc.full_name or _("user")),
        }
    except frappe.DoesNotExistError:
        frappe.local.response["http_status_code"] = 404
        frappe.clear_messages()
        return {
            "status": "not_found",
            "message": _("No account found for this email address."),
        }

@frappe.whitelist(allow_guest=True)
def login_fle_user(usr, pwd):
    from frappe.auth import LoginManager

    # Check if the user exists before attempting authentication
    if not frappe.db.exists("User", usr):
        frappe.clear_messages()
        frappe.local.response["message"] = (
            "No account found for this email. "
            "Please register to create an account."
        )
        return

    try:
        login_manager = LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
    except frappe.exceptions.AuthenticationError:
        frappe.clear_messages()
        frappe.local.response["message"] = "Incorrect password"
        return

    frappe.local.response["message"] = "Logged In"

    user_type = frappe.db.get_value("User", frappe.session.user, "user_type")
    if user_type == "System User":
        frappe.local.response["home_page"] = "/desk"
        return

    # Get the user to fetch email and mobile
    user_doc = frappe.get_doc("User", usr)
    email = user_doc.email or ""
    mobile = user_doc.mobile_no or ""

    # Store prefill data server-side so the URL stays clean (email only)
    frappe.cache().hset("fle_prefill", frappe.session.user, {"email": email})

    # If the user has a paid FLE application, send them to the enrolled dashboard
    paid_doc = frappe.db.get_value(
        "Foundations for a Legal Education",
        {"email_address": email, "payment_status": ["in", ["Authorized", "Paid", "Captured"]]},
        "name",
    )
    if paid_doc:
        frappe.local.response["home_page"] = "/fle/enrolled"
        return

    # If the user has an unpaid/incomplete document, redirect them to continue it
    existing_doc = frappe.db.get_value(
        "Foundations for a Legal Education",
        {"email_address": email, "payment_status": ["not in", ["Authorized", "Paid", "Captured"]]},
        "name",
    )
    if existing_doc:
        frappe.local.response["home_page"] = f"/foundations-for-a-legal-education/{existing_doc}"
    else:
        frappe.local.response["home_page"] = "/foundations-for-a-legal-education/new"

@frappe.whitelist()
def get_fle_prefill_data():
    """Return cached prefill data for the current user and clear it (one-time use)."""
    user = frappe.session.user
    if user == "Guest":
        return {}
    data = frappe.cache().hget("fle_prefill", user) or {}
    if data:
        frappe.cache().hdel("fle_prefill", user)
    return data


@frappe.whitelist()
def download_fle_receipt(docname):
    if not docname:
        frappe.throw(_("Document name required"))

    if not frappe.db.exists("Foundations for a Legal Education", docname):
        frappe.throw(_("Document not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("Foundations for a Legal Education", docname)

    # Only allow owner or System Manager
    if frappe.session.user != doc.owner:
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            frappe.throw(_("Not permitted"), frappe.PermissionError)

    from frappe.utils.pdf import get_pdf
    from frappe.utils import flt, fmt_money

    def esc(v):
        return frappe.utils.escape_html(str(v or ""))

    logo_url = frappe.utils.get_url("/files/nlsiu-logo.jpg")
    photo_src = _photo_as_data_uri(doc.candidate_photo)
    if photo_src:
        photo_td = f'<td style="width: 100px; text-align: right; vertical-align: middle;"><img src="{photo_src}" style="width: 90px; height: 110px; border: 1px solid #E5E7EB;" /></td>'
    else:
        photo_td = '<td style="width: 100px;"></td>'

    amount_formatted = fmt_money(flt(doc.paid_amount), currency="INR") if doc.paid_amount else str(doc.paid_amount or "")

    html = f"""
        <html>
        <head>
            <meta charset="utf-8" />
            <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&display=swap" rel="stylesheet" />
            <style>
                body {{ font-family: "Merriweather", serif; font-size: 11px; color: #111827; }}
                .h1 {{ font-size: 12px; font-weight: 700; margin: 12px 0 12px 0; }}
                .sub {{ color: #4b5563; margin: 0 0 12px 0; }}
                table {{ width: 100%; border-collapse: collapse; }}
                td {{ padding: 10px 12px; border: 1px solid #E5E7EB; vertical-align: top; }}
                td.k {{ width: 35%; background: #F9FAFB; font-weight: 600; }}
                table.header-table {{ border: none; margin-bottom: 20px; border-bottom: 2px solid #a81119; padding-bottom: 10px; }}
                table.header-table td {{ border: none; padding: 0; vertical-align: middle; }}
                .header-title-container {{ text-align: center; color: #a81119; font-family: "Merriweather", serif; }}
                .university-name {{ font-size: 22px; font-weight: bold; margin: 0 0 6px 0; }}
                .red-ribbon {{ background-color: #8B0000; height: 6px; margin: 4px 0; width: 100%; }}
                .department-name {{ font-size: 14px; font-weight: bold; margin: 6px 0 0 0; }}
            </style>
        </head>
        <body>
            <table class="header-table">
                <tr>
                    <td style="width: 80px;"><img src="{esc(logo_url)}" style="width: 60px; height: auto;" /></td>
                    <td class="header-title-container">
                        <div class="university-name">NATIONAL LAW SCHOOL OF INDIA UNIVERSITY, BENGALURU</div>
                        <div class="red-ribbon"></div>
                        <div class="department-name">Foundations for a Legal Education Certificate Course (FLE)</div>
                    </td>
                    {photo_td}
                </tr>
            </table>
            <div class="h1">Payment receipt</div>
            <p class="sub">Reference: {esc(docname)}</p>
            <table>
                <tr><td class="k">Name</td><td>{esc(doc.candidate_name)}</td></tr>
                <tr><td class="k">Email</td><td>{esc(doc.email_address)}</td></tr>
                <tr><td class="k">Payment status</td><td>{esc(doc.payment_status)}</td></tr>
                <tr><td class="k">Amount</td><td>{esc(amount_formatted)}</td></tr>
                <tr><td class="k">Transaction ID</td><td>{esc(doc.payment_id)}</td></tr>
                <tr><td class="k">Reference</td><td>{esc(docname)}</td></tr>
                <tr><td class="k">Date</td><td>{esc(doc.modified)}</td></tr>
            </table>
             <p style="text-align: center; font-size: 11px; color: #374151; margin-top: 18px; letter-spacing: 2px;">
                *********
            </p>
        </body>
        </html>
    """

    pdf_content = get_pdf(html)
    frappe.local.response.filename = f"Receipt-{docname}.pdf"
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type = "download"


@frappe.whitelist()
def get_fle_receipt_pdf_base64(docname):
    """Returns the payment receipt PDF as base64 for inline viewing."""
    if not docname:
        frappe.throw(_("Document name required"))

    if not frappe.db.exists("Foundations for a Legal Education", docname):
        frappe.throw(_("Document not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("Foundations for a Legal Education", docname)

    if frappe.session.user != doc.owner:
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            frappe.throw(_("Not permitted"), frappe.PermissionError)

    from frappe.utils.pdf import get_pdf
    from frappe.utils import flt, fmt_money


    def esc(v):
        return frappe.utils.escape_html(str(v or ""))

    logo_url = frappe.utils.get_url("/files/nlsiu-logo.jpg")
    photo_src = _photo_as_data_uri(doc.candidate_photo)
    if photo_src:
        photo_td = f'<td style="width: 100px; text-align: right; vertical-align: middle;"><img src="{photo_src}" style="width: 90px; height: 110px; border: 1px solid #E5E7EB;" /></td>'
    else:
        photo_td = '<td style="width: 100px;"></td>'

    amount_formatted = fmt_money(flt(doc.paid_amount), currency="INR") if doc.paid_amount else str(doc.paid_amount or "")

    html = f"""
        <html>
        <head>
            <meta charset="utf-8" />
            <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&display=swap" rel="stylesheet" />
            <style>
                body {{ font-family: "Merriweather", serif; font-size: 11px; color: #111827; }}
                .h1 {{ font-size: 12px; font-weight: 700; margin: 12px 0 12px 0; }}
                .sub {{ color: #4b5563; margin: 0 0 12px 0; }}
                table {{ width: 100%; border-collapse: collapse; }}
                td {{ padding: 10px 12px; border: 1px solid #E5E7EB; vertical-align: top; }}
                td.k {{ width: 35%; background: #F9FAFB; font-weight: 600; }}
                table.header-table {{ border: none; margin-bottom: 20px; border-bottom: 2px solid #a81119; padding-bottom: 10px; }}
                table.header-table td {{ border: none; padding: 0; vertical-align: middle; }}
                .header-title-container {{ text-align: center; color: #a81119; font-family: "Merriweather", serif; }}
                .university-name {{ font-size: 22px; font-weight: bold; margin: 0 0 6px 0; }}
                .red-ribbon {{ background-color: #8B0000; height: 6px; margin: 4px 0; width: 100%; }}
                .department-name {{ font-size: 14px; font-weight: bold; margin: 6px 0 0 0; }}
            </style>
        </head>
        <body>
            <table class="header-table">
                <tr>
                    <td style="width: 80px;"><img src="{esc(logo_url)}" style="width: 60px; height: auto;" /></td>
                    <td class="header-title-container">
                        <div class="university-name">NATIONAL LAW SCHOOL OF INDIA UNIVERSITY, BENGALURU</div>
                        <div class="red-ribbon"></div>
                        <div class="department-name">Foundations for a Legal Education Certificate Course (FLE)</div>
                    </td>
                    {photo_td}
                </tr>
            </table>
            <div class="h1">Payment receipt</div>
            <p class="sub">Reference: {esc(docname)}</p>
            <table>
                <tr><td class="k">Name</td><td>{esc(doc.candidate_name)}</td></tr>
                <tr><td class="k">Email</td><td>{esc(doc.email_address)}</td></tr>
                <tr><td class="k">Payment status</td><td>{esc(doc.payment_status)}</td></tr>
                <tr><td class="k">Amount</td><td>{esc(amount_formatted)}</td></tr>
                <tr><td class="k">Transaction ID</td><td>{esc(doc.payment_id)}</td></tr>
                <tr><td class="k">Reference</td><td>{esc(docname)}</td></tr>
                <tr><td class="k">Date</td><td>{esc(doc.modified)}</td></tr>
            </table>
            <p style="text-align: center; font-size: 11px; color: #374151; margin-top: 18px; letter-spacing: 2px;">
                *********
            </p>
        </body>
        </html>
    """

    pdf_content = get_pdf(html)
    return {
        "pdf": base64.b64encode(pdf_content).decode("utf-8"),
        "filename": f"Receipt-{docname}.pdf"
    }


@frappe.whitelist()
def download_fle_application_pdf(docname):
    if not docname:
        frappe.throw(_("Document name required"))

    if not frappe.db.exists("Foundations for a Legal Education", docname):
        frappe.throw(_("Document not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("Foundations for a Legal Education", docname)

    # Only allow owner or System Manager
    if frappe.session.user != doc.owner:
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            frappe.throw(_("Not permitted"), frappe.PermissionError)

    from frappe.utils.pdf import get_pdf

    def esc(v):
        return frappe.utils.escape_html(str(v or ""))

    def row(label, value):
        return f'<tr><td class="k">{esc(label)}</td><td>{esc(value)}</td></tr>'

    def sec(title):
        return f'<tr><td colspan="2" class="sec-head">{esc(title)}</td></tr>'

    logo_url = frappe.utils.get_url("/files/nlsiu-logo.jpg")
    photo_src = _photo_as_data_uri(doc.candidate_photo)
    if photo_src:
        photo_td = f'<td style="width: 110px; text-align: right; vertical-align: middle;"><img src="{photo_src}" style="width: 100px; height: 125px; border: 1px solid #E5E7EB;" /></td>'
    else:
        photo_td = '<td style="width: 110px;"></td>'

    year_of_passing = doc.year_of_passing or ""
    if year_of_passing == "Prior to 2016" and doc.please_specify_the_year_of_passing:
        year_of_passing = f"Prior to 2016 ({doc.please_specify_the_year_of_passing})"

    occupation = doc.candidate_current_occupation or ""
    if occupation == "Other" and doc.if_other4:
        occupation = f"Other ({doc.if_other4})"

    state = doc.candidates_state or ""
    if state == "Other" and doc.if_other3:
        state = f"Other ({doc.if_other3})"

    board = doc.latest_board_attended or ""
    if board == "Other" and doc.if_others2:
        board = f"Other ({doc.if_others2})"

    exam = doc.last_class_attended or ""
    if exam == "Other" and doc.if_others1:
        exam = f"Other ({doc.if_others1})"

    where_heard = doc.where_did_you_hear or ""
    if where_heard == "Other" and doc.if_others_mention_here:
        where_heard = f"Other ({doc.if_others_mention_here})"

    html = f"""
        <html>
        <head>
            <meta charset="utf-8" />
            <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&display=swap" rel="stylesheet" />
            <style>
                body {{ font-family: "Merriweather", serif; font-size: 11px; color: #111827; }}
                table.header-table {{ border: none; margin-bottom: 16px; border-bottom: 2px solid #a81119; padding-bottom: 8px; width: 100%; border-collapse: collapse; }}
                table.header-table td {{ border: none; padding: 0; vertical-align: middle; }}
                .header-title-container {{ text-align: center; color: #a81119; }}
                .university-name {{ font-size: 22px; font-weight: bold; margin: 0; }}
                .department-name {{ font-size: 14px; font-weight: bold; margin: 4px 0 0 0; }}
                .app-ref {{ font-size: 12px; margin: 4px 0 0 0; color: #374151; }}
                table.main {{ width: 100%; border-collapse: collapse; margin-bottom: 0; }}
                table.main td {{ padding: 7px 10px; border: 1px solid #E5E7EB; vertical-align: top; }}
                table.main td.k {{ width: 38%; background: #F9FAFB; font-weight: 600; }}
                table.main td.sec-head {{ background: #a81119; color: #fff; font-weight: 700; font-size: 14px; padding: 5px 10px; }}
            </style>
        </head>
        <body>
            <table class="header-table">
                <tr>
                    <td style="width: 75px;"><img src="{esc(logo_url)}" style="width: 55px; height: auto;" /></td>
                    <td class="header-title-container">
                        <div class="university-name">NATIONAL LAW SCHOOL OF INDIA UNIVERSITY, BENGALURU</div>
                        <div class="red-ribbon"></div>
                        <div class="department-name">Foundations for a Legal Education Certificate Course (FLE)</div>
                    </td>
                    {photo_td}
                </tr>
            </table>
            <table class="main">
                {sec("Candidate details")}
                {row("Application number", doc.name)}
                {row("Submission date", doc.timestamp)}
                {row("Name on certificate", doc.candidate_name)}
                {row("Email address", doc.email_address)}
                {row("Current occupation", occupation)}
                {row("Gender", doc.candidate_gender)}
                {row("Date of birth", doc.candidate_dob)}
                {row("Nationality", doc.candidate_nationality)}
                {row("Country of residence", doc.country_of_residence)}
                {row("State", state)}
                {row("City", doc.city)}
                {row("Address", doc.address_line_1)}
                {row("Pincode", doc.pincode)}
                {row("Contact number", doc.candidate_contact_number)}
                {row("Where did you hear about FLE?", where_heard)}

                {sec("Educational background")}
                {row("Last examination attended", exam)}
                {row("Latest board", board)}
                {row("Year of passing", year_of_passing)}
                {row("Last institution attended", doc.last_institution_attended)}

                {sec("Parent / guardian details")}
                {row("Relationship with candidate", doc.relationship_with_candidate)}
                {row("Parent's name", doc.parent_name)}
                {row("Parent's contact number", doc.parent_contact_number)}
                {row("Parent's email address", doc.parent_email_address)}
                {row("Parent's occupation", doc.parent_occupation)}

                {sec("Payment details")}
                {row("Payment status", doc.payment_status)}
                {row("Amount paid", doc.paid_amount)}
                {row("Payment ID", doc.payment_id)}

                {sec("Application status")}
                {row("Enrollment status", doc.enrollment_status)}
                {row("Declaration consent", "Yes" if doc.declaration_consent else "No")}
            </table>
            <p style="text-align: center; font-size: 11px; color: #374151; margin-top: 18px; letter-spacing: 2px;">
                *********
            </p>
        </body>
        </html>
    """

    pdf_content = get_pdf(html)
    frappe.local.response.filename = f"FLE-Application-{docname}.pdf"
    frappe.local.response.filecontent = pdf_content
    frappe.local.response.type = "download"


@frappe.whitelist()
def get_fle_application_pdf_base64(docname):
    """Returns the application PDF as a base64 string for inline viewing."""
    if not docname:
        frappe.throw(_("Document name required"))

    if not frappe.db.exists("Foundations for a Legal Education", docname):
        frappe.throw(_("Document not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("Foundations for a Legal Education", docname)

    if frappe.session.user != doc.owner:
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            frappe.throw(_("Not permitted"), frappe.PermissionError)

    from frappe.utils.pdf import get_pdf


    def esc(v):
        return frappe.utils.escape_html(str(v or ""))

    def row(label, value):
        return f'<tr><td class="k">{esc(label)}</td><td>{esc(value)}</td></tr>'

    def sec(title):
        return f'<tr><td colspan="2" class="sec-head">{esc(title)}</td></tr>'

    logo_url = frappe.utils.get_url("/files/nlsiu-logo.jpg")
    photo_src = _photo_as_data_uri(doc.candidate_photo)
    if photo_src:
        photo_td = f'<td style="width: 110px; text-align: right; vertical-align: middle;"><img src="{photo_src}" style="width: 100px; height: 125px; border: 1px solid #E5E7EB;" /></td>'
    else:
        photo_td = '<td style="width: 110px;"></td>'

    year_of_passing = doc.year_of_passing or ""
    if year_of_passing == "Prior to 2016" and doc.please_specify_the_year_of_passing:
        year_of_passing = f"Prior to 2016 ({doc.please_specify_the_year_of_passing})"

    occupation = doc.candidate_current_occupation or ""
    if occupation == "Other" and doc.if_other4:
        occupation = f"Other ({doc.if_other4})"

    state = doc.candidates_state or ""
    if state == "Other" and doc.if_other3:
        state = f"Other ({doc.if_other3})"

    board = doc.latest_board_attended or ""
    if board == "Other" and doc.if_others2:
        board = f"Other ({doc.if_others2})"

    exam = doc.last_class_attended or ""
    if exam == "Other" and doc.if_others1:
        exam = f"Other ({doc.if_others1})"

    where_heard = doc.where_did_you_hear or ""
    if where_heard == "Other" and doc.if_others_mention_here:
        where_heard = f"Other ({doc.if_others_mention_here})"

    html = f"""
        <html>
        <head>
            <meta charset="utf-8" />
            <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&display=swap" rel="stylesheet" />
            <style>
                body {{ font-family: "Merriweather", serif; font-size: 11px; color: #111827; }}
                table.header-table {{ border: none; margin-bottom: 16px; border-bottom: 2px solid #a81119; padding-bottom: 8px; width: 100%; border-collapse: collapse; }}
                table.header-table td {{ border: none; padding: 0; vertical-align: middle; }}
                .header-title-container {{ text-align: center; color: #a81119; }}
                .university-name {{ font-size: 22px; font-weight: bold; margin: 0; }}
                .department-name {{ font-size: 14px; font-weight: bold; margin: 4px 0 0 0; }}
                .app-ref {{ font-size: 12px; margin: 4px 0 0 0; color: #374151; }}
                table.main {{ width: 100%; border-collapse: collapse; margin-bottom: 0; }}
                table.main td {{ padding: 7px 10px; border: 1px solid #E5E7EB; vertical-align: top; }}
                table.main td.k {{ width: 38%; background: #F9FAFB; font-weight: 600; }}
                table.main td.sec-head {{ background: #a81119; color: #fff; font-weight: 700; font-size: 14px; padding: 5px 10px; }}
            </style>
        </head>
        <body>
            <table class="header-table">
                <tr>
                    <td style="width: 75px;"><img src="{esc(logo_url)}" style="width: 55px; height: auto;" /></td>
                    <td class="header-title-container">
                        <div class="university-name">NATIONAL LAW SCHOOL OF INDIA UNIVERSITY, BENGALURU</div>
                        <div class="red-ribbon"></div>
                        <div class="department-name">Foundations for a Legal Education Certificate Course (FLE)</div>
                    </td>
                    {photo_td}
                </tr>
            </table>
            <table class="main">

                {sec("Candidate details")}
                {row("Application number", doc.name)}
                {row("Submission date", doc.timestamp)}
                {row("Name on certificate", doc.candidate_name)}
                {row("Email address", doc.email_address)}
                {row("Current occupation", occupation)}
                {row("Gender", doc.candidate_gender)}
                {row("Date of birth", doc.candidate_dob)}
                {row("Nationality", doc.candidate_nationality)}
                {row("Country of residence", doc.country_of_residence)}
                {row("State", state)}
                {row("City", doc.city)}
                {row("Address", doc.address_line_1)}
                {row("Pincode", doc.pincode)}
                {row("Contact number", doc.candidate_contact_number)}
                {row("Where did you hear about FLE?", where_heard)}

                {sec("Educational background")}
                {row("Last examination attended", exam)}
                {row("Latest board", board)}
                {row("Year of passing", year_of_passing)}
                {row("Last institution attended", doc.last_institution_attended)}

                {sec("Parent / guardian details")}
                {row("Relationship with candidate", doc.relationship_with_candidate)}
                {row("Parent's name", doc.parent_name)}
                {row("Parent's contact number", doc.parent_contact_number)}
                {row("Parent's email address", doc.parent_email_address)}
                {row("Parent's occupation", doc.parent_occupation)}

                {sec("Payment details")}
                {row("Payment status", doc.payment_status)}
                {row("Amount paid", doc.paid_amount)}
                {row("Payment ID", doc.payment_id)}

                {sec("Application status")}
                {row("Enrollment status", doc.enrollment_status)}
                {row("Declaration consent", "Yes" if doc.declaration_consent else "No")}
            </table>
            <p style="text-align: center; font-size: 11px; color: #374151; margin-top: 18px; letter-spacing: 2px;">
                *********
            </p>
        </body>
        </html>
    """

    pdf_content = get_pdf(html)
    return {
        "pdf": base64.b64encode(pdf_content).decode("utf-8"),
        "filename": f"FLE-Application-{docname}.pdf"
    }


@frappe.whitelist(allow_guest=True)
def get_payment_status(docname):
    if not docname:
        return {}
        
    if not frappe.db.exists("Foundations for a Legal Education", docname):
        return {}
        
    doc = frappe.get_doc("Foundations for a Legal Education", docname)

    # Allow only if the session user is the owner, or has System Manager role.
    # (Guest can never be the owner, so this also denies unauthenticated access.)
    if frappe.session.user != doc.owner:
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            return {}
            
    return {
        "payment_status": doc.payment_status,
        "docstatus": doc.docstatus
    }
@frappe.whitelist(allow_guest=True)
def custom_sign_up(email, full_name, mobile_no=None, redirect_to=None):
    """
    Custom sign-up that bypasses Frappe's core sign_up() to avoid the
    'Please ask your administrator to verify your sign-up' gate caused by
    the 'Allow Guests to Sign Up' Website Settings flag.
    User is created directly (same approach as register_pace_user) and
    assigned the Applicant role automatically.
    """
    email = (email or "").strip().lower()
    full_name = (full_name or "").strip()

    if not email:
        return [0, "Email is required."]

    # Duplicate checks before attempting insert
    if frappe.db.exists("User", email):
        return [0, "An account with this email already exists. Please log in or use 'Forgot Password'."]

    if mobile_no and frappe.db.exists("User", {"mobile_no": mobile_no}):
        return [0, "Mobile number is already registered to another account."]

    user_created = False
    try:
        from frappe.utils import random_string, get_url, add_days, now_datetime
        import urllib.parse

        user_dict = {
            "doctype": "User",
            "email": email,
            "first_name": full_name or email.split("@")[0],
            "enabled": 1,
            "new_password": random_string(10),
            "user_type": "Website User",
            "send_welcome_email": 0,
        }
        if mobile_no:
            user_dict["mobile_no"] = mobile_no

        user_doc = frappe.get_doc(user_dict)
        user_doc.flags.ignore_permissions = True
        user_doc.flags.ignore_password_policy = True
        user_doc.insert()
        user_created = True

        # Clear internal __new_password to prevent subsequent save (like add_roles) from sending Security Alert email
        if hasattr(user_doc, "_User__new_password"):
            user_doc._User__new_password = None
        if hasattr(user_doc, "__new_password"):
            user_doc.__new_password = None

        # Track that this user is a new signup to suppress Security Alert email during first password setup
        frappe.cache().hset("newly_signup_user", user_doc.name, 1)

        # Assign Applicant role
        user_doc.flags.ignore_permissions = True
        if "Applicant" not in [r.role for r in user_doc.roles]:
            user_doc.add_roles("Applicant")

        # Generate a password-reset link so they can set their password
        frappe_link = get_reset_password_link(user_doc, send_email=False)
        user_doc.db_set("last_reset_password_key_generated_on", add_days(now_datetime(), 30))

        parsed = urllib.parse.urlparse(frappe_link)
        base_redir = redirect_to or get_portal_base()
        correct_link = get_url(f"/update-password?{parsed.query}&redirect_to={urllib.parse.quote(base_redir)}")

        # Cache redirect for post-password-set
        frappe.cache().hset("redirect_after_login", user_doc.name, base_redir)

        # Send welcome email with set-password link
        send_welcome_or_custom_signup_email(user_doc, correct_link, template="new_user")

        frappe.db.commit()
        return [1, "Account created! Check your email to set your password and activate your account."]

    except frappe.exceptions.DuplicateEntryError:
        frappe.db.rollback()
        if user_created:
            try:
                frappe.delete_doc("User", email, force=1, ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                pass
        return [0, "An account with this email already exists. Please log in or use 'Forgot Password'."]
    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        if user_created:
            try:
                frappe.delete_doc("User", email, force=1, ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                pass
        frappe.log_error(frappe.get_traceback(), "custom_sign_up: ValidationError")
        return [0, f"Registration could not be completed: {e}"]
    except Exception as e:
        frappe.db.rollback()
        if user_created:
            try:
                frappe.delete_doc("User", email, force=1, ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                pass
        frappe.log_error(frappe.get_traceback(), "custom_sign_up: Unexpected error")
        err = str(e)
        if "Duplicate entry" in err:
            if "mobile_no" in err:
                return [0, "Mobile number is already registered to another account."]
            return [0, "An account with this email already exists. Please log in or use 'Forgot Password'."]
        # Never expose raw tracebacks or internal messages to the user
        return [0, "Registration failed due to an unexpected error. Please try again or contact support."]

 
@frappe.whitelist()
def get_districts(state):
    return frappe.get_all("District", filters={"state": state}, fields=["name"], order_by="name asc")
 
@frappe.whitelist()
def get_user_details():
    user = frappe.session.user
    if user == "Guest":
        return {}
    
    return frappe.db.get_value("User", user,
        ["name", "full_name", "email", "mobile_no", "user_image"], as_dict=True)
 
@frappe.whitelist()
def get_login_redirect():
    user = frappe.session.user
    if user == "Guest":
        return get_portal_login_url()
    
    user_type = frappe.db.get_value("User", user, "user_type") or "Website User"
    if user_type == "System User":
        return "/desk"
        
    roles = frappe.get_roles(user)
    if "PACE Applicant" in roles and "Applicant" not in roles:
        return "/pace/my-profile"
    else:
        return "/nlsat/my-profile"

from frappe.rate_limiter import rate_limit
from frappe.core.doctype.user.user import get_password_reset_limit

@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="user", limit=get_password_reset_limit, seconds=60 * 60)
def reset_password(user: str, redirect_to: str = None):
    """
    Send password reset email. Returns a dict {status, message} for portal JSON clients.
    """
    try:
        user_doc = frappe.get_doc("User", user)
        if user_doc.name == "Administrator":
            return {
                "status": "not_allowed",
                "message": _("Password reset is not allowed for this account."),
            }
        if not user_doc.enabled:
            return {"status": "disabled", "message": _("This account has been disabled.")}

        user_doc.validate_reset_password()
        
        # Generate the link without sending the email via Frappe core (which has a header list bug)
        link = get_reset_password_link(user_doc, send_email=False)
        
        # Determine redirect for portal users
        from frappe.utils import get_url
        from frappe.utils.user import get_user_fullname

        roles = frappe.get_roles(user_doc.name)
        if "Applicant" in roles and not redirect_to:
            redirect_to = "/admission"

        if redirect_to:
            import urllib.parse
            parsed = urllib.parse.urlparse(link)
            if "redirect_to" not in parsed.query:
                link = get_url(f"/update-password?{parsed.query}&redirect_to={urllib.parse.quote(redirect_to)}")
            frappe.cache().hset("redirect_after_login", user_doc.name, redirect_to)

        subject = _("Password Reset")
        created_by = get_user_fullname(frappe.session["user"]) if frappe.session.get("user") else "Administrator"
        if created_by == "Guest":
            created_by = "Administrator"

        institution = frappe.get_single("Institution Settings")
        institution_name = getattr(institution, "institution_name", "") or "National Law School of India University"
        full_name = user_doc.full_name or user_doc.first_name or user_doc.last_name or "Candidate"

        args = {
            "first_name": user_doc.first_name or user_doc.last_name or "Candidate",
            "full_name": full_name,
            "candidate_name": full_name,
            "applicant_name": full_name,
            "user": user_doc.name,
            "email": user_doc.email or user_doc.name,
            "title": subject,
            "login_url": getattr(institution, "login_url", "") or get_url("/admission/login"),
            "created_by": created_by,
            "link": link,
            "reset_password_link": link,
            "set_password_link": link,
            "institution_name": institution_name,
            "support_email": getattr(institution, "support_email", ""),
            "link_expiry_hours": getattr(institution, "link_expiry_hours", 24) or 24,
            "logo": getattr(institution, "logo", ""),
            "doc": user_doc,
        }
        
        reset_password_template = frappe.db.get_system_setting("reset_password_template") or "Reset Password Template"
        content = None
        template = "slcm_password_reset"
        sender = None
        
        if reset_password_template and frappe.db.exists("Email Template", reset_password_template):
            tmpl = frappe.get_doc("Email Template", reset_password_template)
            tmpl.flags.ignore_permissions = True
            subject = tmpl.get_formatted_subject(args) or subject
            content = tmpl.get_formatted_response(args)
            
            # Resolve sender from the template
            if tmpl.email_account:
                sender = frappe.db.get_value("Email Account", tmpl.email_account, "email_id") or tmpl.email_account

        frappe.sendmail(
            recipients=user_doc.email,
            sender=sender,
            subject=subject,
            template=template if not (reset_password_template and content) else None,
            content=content if (reset_password_template and content) else None,
            args=args,
            now=True
        )

        return {
            "status": "ok",
            "message": _(
                "A password reset link has been sent to {0}. Check your inbox and spam folder."
            ).format(user_doc.email or user_doc.full_name or _("your email")),
        }
    except frappe.DoesNotExistError:
        frappe.local.response["http_status_code"] = 404
        frappe.clear_messages()
        return {
            "status": "not_found",
            "message": _("No account found for this email address. Please check the spelling or register."),
        }

@frappe.whitelist(allow_guest=True)
def custom_update_password(new_password, logout_all_sessions=0, key=None, old_password=None, redirect_to=None):
    from frappe.core.doctype.user.user import update_password as core_update_password
    from frappe.core.doctype.user.user import User
    from frappe.utils import sha256_hash
    
    target_user = None
    if key:
        target_user = frappe.db.get_value("User", {"reset_password_key": sha256_hash(key)}, "name")
    elif old_password:
        target_user = frappe.session.user
        
    is_new_signup = False
    if target_user:
        is_new_signup = frappe.cache().hget("newly_signup_user", target_user)
        
    original_set_new_password = None
    if is_new_signup and hasattr(User, "set_new_password"):
        original_set_new_password = User.set_new_password
        def custom_set_new_password(self, new_password=None):
            if new_password and not self.flags.in_insert:
                from frappe.core.doctype.user.user import _update_password
                _update_password(user=self.name, pwd=new_password, logout_all_sessions=self.logout_all_sessions)
        User.set_new_password = custom_set_new_password
        frappe.cache().hdel("newly_signup_user", target_user)
        
    try:
        # Call the original Frappe core method with keyword arguments
        result = core_update_password(
            new_password=new_password, 
            logout_all_sessions=logout_all_sessions, 
            key=key, 
            old_password=old_password
        )
    finally:
        if original_set_new_password:
            # Restore the original method
            User.set_new_password = original_set_new_password
    
    # Now override the return URL based on our custom routing rules
    user = frappe.session.user
    if user and user != "Guest":
        user_type = frappe.db.get_value("User", user, "user_type")
        roles = frappe.get_roles(user)
        if user_type == "System User":
            return "/desk"
        
        # Try to resolve a redirect target
        target = redirect_to or frappe.form_dict.get("redirect_to")
        
        if not target:
            # Try parsing from Referer header
            try:
                import urllib.parse
                referer = frappe.request.headers.get("Referer")
                if referer:
                    parsed_referer = urllib.parse.urlparse(referer)
                    query_params = urllib.parse.parse_qs(parsed_referer.query)
                    redirect_to_val = query_params.get("redirect_to")
                    if redirect_to_val and redirect_to_val[0]:
                        target = redirect_to_val[0]
            except Exception:
                pass
                
        if not target:
            # Fallback to cache
            target = frappe.cache().hget("redirect_after_login", user)
            if target:
                frappe.cache().hdel("redirect_after_login", user)
                
        # Validate target redirect path to prevent open redirect vulnerabilities
        if target:
            from frappe.utils import get_url
            site_url = get_url()
            if (target.startswith("/") and not target.startswith("//")) or target.startswith(site_url):
                return target

        if "PACE Applicant" in roles and "Applicant" not in roles:
            return "/pace/my-profile"
        else:
            return "/nlsat/my-profile"
    
    return result

@frappe.whitelist(allow_guest=True)
def register_pace_user(email, full_name=None, mobile_number=None, redirect_to=None):
    email = (email or "").strip().lower()
    full_name = (full_name or "").strip()

    if not email:
        return {"status": "error", "message": "Email is required."}
    
    if frappe.db.exists("User", email):
        return {"status": "error", "message": "An account with this email already exists. Please log in or use 'Forgot Password'."}

    user_created = False
    try:
        from frappe.utils import random_string, get_url, add_days, now_datetime
        import urllib.parse
        
        user_dict = {
            "doctype": "User",
            "email": email,
            "first_name": full_name or email.split('@')[0],
            "enabled": 1,
            "new_password": random_string(10),
            "user_type": "Website User",
            "send_welcome_email": 0,
            "redirect_url": "/paceadmissions/login",
        }
        if mobile_number:
            user_dict["mobile_no"] = mobile_number

        user = frappe.get_doc(user_dict)
        user.flags.ignore_permissions = True
        user.flags.ignore_password_policy = True
        user.insert()
        user_created = True

        # Clear internal __new_password to prevent subsequent save (like add_roles) from sending Security Alert email
        if hasattr(user, "_User__new_password"):
            user._User__new_password = None
        if hasattr(user, "__new_password"):
            user.__new_password = None

        # Track that this user is a new signup to suppress Security Alert email during first password setup
        frappe.cache().hset("newly_signup_user", user.name, 1)

        # Generate the password reset link silently
        frappe_link = get_reset_password_link(user, send_email=False)
        
        from frappe.utils import add_days, now_datetime
        user.db_set("last_reset_password_key_generated_on", add_days(now_datetime(), 3650))
        
        import urllib.parse
        parsed = urllib.parse.urlparse(frappe_link)
        
        from frappe.utils import get_url
        correct_link = get_url(f"/update-password?{parsed.query}")
        if redirect_to:
            correct_link += f"&redirect_to={urllib.parse.quote(redirect_to)}"
        
        send_welcome_or_custom_signup_email(user, correct_link, template="new_user")

        # Assign "PACE Applicant" role
        user.flags.ignore_permissions = True
        user.add_roles("PACE Applicant")

        if redirect_to:
            frappe.cache().hset("redirect_after_login", user.name, redirect_to)
        else:
            frappe.cache().hset("redirect_after_login", user.name, "/pace/my-profile")
            
        frappe.db.commit()
        return {"status": "success", "message": "Check your email to set your password and activate your account!"}

    except Exception as e:
        frappe.db.rollback()
        if user_created:
            try:
                frappe.delete_doc("User", email, force=1, ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                pass
                
        frappe.log_error(frappe.get_traceback(), "register_pace_user: Unexpected error")
        err = str(e)
        if "Duplicate entry" in err:
            return {"status": "error", "message": "An account with this email already exists. Please log in or use 'Forgot Password'."}
        return {"status": "error", "message": "Registration failed due to an unexpected error. Please try again or contact support."}

@frappe.whitelist(allow_guest=True)
def login_pace_user(usr, pwd):
    from frappe.auth import LoginManager
    if not frappe.db.exists("User", usr):
        frappe.clear_messages()
        frappe.local.response["message"] = "No account found for this email. Please register to create an account."
        return

    try:
        login_manager = LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
    except frappe.exceptions.AuthenticationError:
        frappe.clear_messages()
        frappe.local.response["message"] = "Incorrect password"
        return

    frappe.local.response["message"] = "Logged In"
    user_type = frappe.db.get_value("User", frappe.session.user, "user_type")
    if user_type == "System User":
        frappe.local.response["home_page"] = "/desk"
    else:
        frappe.local.response["home_page"] = "/pace/my-profile"


@frappe.whitelist(allow_guest=True, methods=["POST"])
def reset_password_pace(user: str, redirect_to=None):
    """PACE forgot-password: points to /paceadmissions/update_password.html"""
    try:
        user_doc = frappe.get_doc("User", user)
        if user_doc.name == "Administrator":
            return {"status": "not_allowed", "message": _("Password reset is not allowed for this account.")}
        if not user_doc.enabled:
            return {"status": "disabled", "message": _("This account has been disabled.")}

        user_doc.validate_reset_password()
        frappe_link = get_reset_password_link(user_doc, send_email=False)
        
        import urllib.parse
        parsed = urllib.parse.urlparse(frappe_link)
        
        from frappe.utils import get_url
        correct_link = get_url(f"/update-password?{parsed.query}")
        if redirect_to:
            correct_link += f"&redirect_to={urllib.parse.quote(redirect_to)}"
        
        try:
            logo_path = os.path.abspath(frappe.get_site_path("public", "files", "nlsiu-logo.jpg"))
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode("utf-8")
            logo_src = f"data:image/jpeg;base64,{logo_b64}"
        except Exception:
            logo_src = ""

        base_url = get_url()

        user_doc.send_login_mail(
            _("Password Reset"),
            "pace_password_reset",
            {"link": correct_link, "site_url": base_url, "logo_src": logo_src},
            now=True,
        )

        return {
            "status": "ok",
            "message": _("We have sent a password reset link to {0}. Check your inbox and spam folder.").format(user_doc.email or user_doc.full_name or _("user")),
        }
    except frappe.DoesNotExistError:
        frappe.local.response["http_status_code"] = 404
        frappe.clear_messages()
        return {"status": "not_found", "message": _("No account found for this email address.")}

@frappe.whitelist(allow_guest=True, methods=["POST"])
def update_password_pace(new_password, key):
    """PACE set-password: redirects to PACE dashboard after success"""
    from frappe.core.doctype.user.user import update_password
    core_redirect = update_password(new_password=new_password, key=key)
    
    user = frappe.session.user
    if user == "Guest":
        return "/paceadmissions/login"

    # Default redirect for PACE
    return "/pace/my-profile"

