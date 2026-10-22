import frappe
from slcm.admission.utils.nlsat_portal import get_portal_login_url

def user_before_insert(doc, method):
    """
    Triggered on User before_insert.
    If custom signup email is enabled, disable Frappe's default welcome mail.
    """
    if doc.user_type != "Website User":
        return

    # Assign the current active admission cycle to the user for accurate applicant reminders
    try:
        from slcm.admission.applicant_reminder_emails import _get_active_cycle
        active_cycle_name = _get_active_cycle()[0]
        if active_cycle_name:
            doc.registered_admission_cycle = active_cycle_name
    except Exception:
        pass

    institution = frappe.get_single("Institution Settings")
    enable_custom = getattr(institution, "enable_signup_email", 0)
    
    frappe.log_error(f"User: {doc.email}, enable_signup_email: {enable_custom}, send_welcome_email: {doc.send_welcome_email}", "Signup Email Hook: before_insert")

    if enable_custom:
        # If the creator intended to send a welcome email, we intercept it
        if doc.send_welcome_email:
            # Disable default welcome mail to prevent double sending
            doc.send_welcome_email = 0
            # Set a flag to signal our after_insert hook to send the custom one
            doc.flags.send_custom_signup_email = 1
            frappe.log_error(f"Suppressed default email for {doc.email}. Set flag: send_custom_signup_email", "Signup Email Hook: before_insert")

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


def send_signup_email(doc, method):
    """
    Triggered on User after_insert.
    Sends a custom signup email to self-registered applicants if flagged.
    """
    try:
        if not doc.flags.get("send_custom_signup_email"):
            # Check if it was bypassed but should have been triggered
            if doc.user_type == "Website User":
                institution = frappe.get_single("Institution Settings")
                if getattr(institution, "enable_signup_email", 0):
                    frappe.log_error(f"Flag 'send_custom_signup_email' not found for {doc.email}. Method: {method}", "Signup Email Hook: after_insert bypassed")
            return

        frappe.log_error(f"Processing custom signup email for {doc.email}", "Signup Email Hook: after_insert start")

        # Fetch "Institution Settings"
        institution = frappe.get_single("Institution Settings")
        
        # Double check if still enabled (though flag should be enough)
        if not getattr(institution, "enable_signup_email", 0):
            frappe.log_error("Custom email disabled in Institution Settings during processing", "Signup Email Error")
            return

        full_name = doc.full_name or doc.first_name or doc.email

        # Generate secure password setup link
        set_password_link = get_reset_password_link(doc)

        # Context for rendering
        context = {
            "institution_name": getattr(institution, "institution_name", "") or "National Law School of India University",
            "logo": getattr(institution, "logo", ""),
            "full_name": full_name,
            "candidate_name": full_name,
            "applicant_name": full_name,
            "first_name": doc.first_name or full_name,
            "set_password_link": set_password_link,
            "login_url": getattr(institution, "login_url", "") or frappe.utils.get_url(get_portal_login_url()),
            "support_email": getattr(institution, "support_email", ""),
            "link_expiry_hours": getattr(institution, "link_expiry_hours", 24) or 24,
            "doc": doc,
        }

        subject = None
        message = None
        sender = None

        # Check if standard Email Template 'Applicant Registration Email' exists
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
            if not message_template:
                frappe.log_error("No Signup Email Template configured in Institution Settings", "Signup Email Error")
                return
                
            message = frappe.render_template(message_template, context)

        # Send Email
        frappe.sendmail(
            recipients=[doc.email],
            sender=sender,
            subject=subject,
            message=message,
            now=True
        )
        # Core sign_up() treats success as user.flags.email_sent; we suppress the default welcome mail
        # in before_insert, so mark the flag here so the API returns (1, ...) instead of (2, ...).
        doc.flags.email_sent = 1
        frappe.log_error(f"Successfully triggered sendmail for {doc.email}", "Signup Email Hook: after_insert success")

    except Exception:
        frappe.log_error(title="SLCM Signup Email Error", message=frappe.get_traceback())

def on_login_hook(login_manager):
    """
    Triggered on successful user authentication.
    Ensures System Users (like Administrator) are routed directly to /desk,
    overriding any Role-level home_page defaults (e.g. from the Applicant role).
    """
    try:
        user = frappe.session.user
        if user and user != "Guest":
            user_type = frappe.db.get_value("User", user, "user_type")
            if user_type == "System User":
                frappe.local.response["home_page"] = "/desk"
    except Exception:
        pass
