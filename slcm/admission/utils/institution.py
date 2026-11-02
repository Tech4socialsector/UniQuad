import frappe

def get_institution_settings():
    """Returns Institution Settings singleton. Cached for 5 minutes."""
    cached = frappe.cache().get_value("institution_settings")
    if cached:
        return cached
    try:
        settings = frappe.get_single("Institution Settings")
        frappe.cache().set_value("institution_settings", settings, expires_in_sec=300)
        return settings
    except Exception:
        return frappe._dict({
            "enable_multi_campus": 0,
            "compliance_mode": "India",
            "max_campus_preferences": 3,
            "payment_gateway": "Offline Only",
            "onboarding_complete": 0
        })

def is_multi_campus_enabled():
    """Returns True if multi-campus mode is ON."""
    settings = get_institution_settings()
    return bool(settings.get("enable_multi_campus"))

def get_compliance_mode():
    """Returns compliance mode: India / International / Both."""
    settings = get_institution_settings()
    return settings.get("compliance_mode") or "India"

def get_max_campus_preferences():
    """Returns max campus preferences allowed per applicant."""
    settings = get_institution_settings()
    return int(settings.get("max_campus_preferences") or 3)

def get_payment_gateway():
    """Returns configured payment gateway name."""
    settings = get_institution_settings()
    return settings.get("payment_gateway") or "Offline Only"

def is_onboarding_complete():
    """Returns True if institution has completed Setup Wizard."""
    settings = get_institution_settings()
    return bool(settings.get("onboarding_complete"))

def validate_institution_setup():
    """Raises error if onboarding not complete."""
    if not is_onboarding_complete():
        frappe.throw(
            "Institution onboarding is not complete. "
            "Please run the Setup Wizard from Institution Settings.",
            title="Setup Required"
        )
