import frappe
import json
from frappe.utils import now, add_days, getdate, today, get_datetime
from slcm.admission.utils.institution import is_multi_campus_enabled

# Admission Cycle.application_form_type — DocType option is "Custom From"; accept "Custom Form" if relabelled.
_CUSTOM_PORTAL_FORM_TYPES = frozenset({"Custom From", "Custom Form"})


def parse_time_or_timedelta(val):
	if not val:
		return None
	from datetime import datetime, timedelta, time
	if isinstance(val, timedelta):
		total_seconds = int(val.total_seconds())
		hours = total_seconds // 3600
		minutes = (total_seconds % 3600) // 60
		seconds = total_seconds % 60
		return time(hours, minutes, seconds)
	if isinstance(val, time):
		return val
	if isinstance(val, str):
		val_str = val.strip()
		for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p"):
			try:
				return datetime.strptime(val_str, fmt).time()
			except ValueError:
				pass
	return None


def get_entrance_test_times(et_doc):
	"""
	Calculates entrance test start time and reporting time (45 minutes before start time).
	Returns (et_test_time, et_reporting_time) as formatted strings (e.g. '09:34 AM', '08:49 AM').
	"""
	if not et_doc:
		return "—", "—"

	from datetime import datetime, timedelta

	is_rescheduled = (getattr(et_doc, "is_rescheduled", 0) == 1 or getattr(et_doc, "entrance_test_status", None) == "Rescheduled")
	f_test = getattr(et_doc, "re_entrance_test_name", None) or getattr(et_doc, "re_entrance_test_list", None) if is_rescheduled else (getattr(et_doc, "entrance_test_name", None) or getattr(et_doc, "entrance_test_list", None))

	start_val = getattr(et_doc, "start_time", None)
	end_val = getattr(et_doc, "end_time", None)

	if not start_val and getattr(et_doc, "admission_cycle", None) and f_test:
		filters = {"parent": et_doc.admission_cycle, "entrance_test_name": f_test}
		if getattr(et_doc, "program_level", None):
			filters["programme_level"] = et_doc.program_level
		test_details = frappe.db.get_value("Entrance Test Details", filters, ["start_time", "end_time"], as_dict=True)
		if not test_details and getattr(et_doc, "program_level", None):
			test_details = frappe.db.get_value("Entrance Test Details", {"parent": et_doc.admission_cycle, "entrance_test_name": f_test}, ["start_time", "end_time"], as_dict=True)
		if test_details:
			start_val = test_details.start_time
			if not end_val:
				end_val = test_details.end_time

	start_t = parse_time_or_timedelta(start_val)
	if start_t:
		today_dt = datetime.combine(datetime.today(), start_t)
		test_time_str = today_dt.strftime("%I:%M %p")
		rep_dt = today_dt - timedelta(minutes=45)
		rep_time_str = rep_dt.strftime("%I:%M %p")
		return test_time_str, rep_time_str

	return "—", "—"



def admission_cycle_uses_applicant_web_form(cycle_name: str | None) -> bool:
	"""
	True → Frappe Web Form (/applicant-form/...).
	False when cycle uses the legacy /application_form portal page.
	"""
	if not cycle_name or not frappe.db.exists("Admission Cycle", cycle_name):
		return True
	if not frappe.db.has_column("Admission Cycle", "application_form_type"):
		return True
	ft = (frappe.db.get_value("Admission Cycle", cycle_name, "application_form_type") or "").strip()
	if ft in _CUSTOM_PORTAL_FORM_TYPES:
		return False
	return True


def build_custom_application_form_url(
	program,
	admission_cycle="",
	campus="",
	intake_type="",
	admission_year="",
	academic_year="",
	program_level="",
):
	"""Public URL for the portal application_form page with query-string prefills."""
	from urllib.parse import urlencode

	parts = {
		"program": program or "",
		"admission_cycle": admission_cycle or "",
		"campus": campus or "",
		"intake_type": intake_type or "",
		"admission_year": admission_year or "",
		"academic_year": academic_year or "",
		"program_level": program_level or "",
	}
	q = urlencode({k: v for k, v in parts.items() if v})
	return f"/application_form?{q}" if q else "/application_form"


def build_applicant_form_new_url(
	program,
	admission_cycle="",
	campus="",
	intake_type="",
	admission_year="",
	academic_year="",
	program_level="",
):
	"""New application entry URL: Web Form or custom portal page, based on Admission Cycle."""
	if admission_cycle and not admission_cycle_uses_applicant_web_form(admission_cycle):
		return build_custom_application_form_url(
			program,
			admission_cycle,
			campus=campus,
			intake_type=intake_type,
			admission_year=admission_year,
			academic_year=academic_year,
			program_level=program_level,
		)
	from urllib.parse import urlencode

	parts = {
		"program": program or "",
	}
	q = urlencode({k: v for k, v in parts.items() if v})
	route = frappe.db.get_value("Web Form", "applicant-form", "route") or "applicant-form"
	if not route.startswith("/"):
		route = "/" + route
	return f"{route}/new?{q}" if q else f"{route}/new"


def build_login_redirect_to_applicant_form_new(
	program,
	admission_cycle="",
	campus="",
	intake_type="",
	admission_year="",
	academic_year="",
	program_level="",
):
	from urllib.parse import quote

	path = build_applicant_form_new_url(
		program,
		admission_cycle,
		campus=campus,
		intake_type=intake_type,
		admission_year=admission_year,
		academic_year=academic_year,
		program_level=program_level,
	)
	return "/admission/login?redirect-to=" + quote(path, safe="/")


def build_existing_applicant_portal_url(
	applicant_name: str,
	admission_cycle: str | None = None,
	*,
	edit: bool = True,
) -> str:
	"""Open an existing Applicant from my-applications or view_application."""
	if not (applicant_name or "").strip():
		return "/my-applications"
	name = applicant_name.strip()
	cycle = (admission_cycle or "").strip()
	if cycle and not admission_cycle_uses_applicant_web_form(cycle):
		from urllib.parse import urlencode

		return f"/application_form?{urlencode({'applicant': name})}"
	
	route = frappe.db.get_value("Web Form", "applicant-form", "route") or "applicant-form"
	if not route.startswith("/"):
		route = "/" + route
		
	if edit:
		return f"{route}/{name}/edit"
	return f"{route}/{name}"


# ── TYPOGRAPHY HELPER ────────────────────────────────────────────

_FONT_GOOGLE_MAP = {
    "Merriweather": "family=Merriweather:ital,wght@0,300;0,400;0,700;1,300;1,400;1,700",
    "Inter":        "family=Inter:wght@300;400;700",
    "Roboto":       "family=Roboto:ital,wght@0,300;0,400;0,700;1,300;1,400;1,700",
    "Poppins":      "family=Poppins:ital,wght@0,300;0,400;0,700;1,300;1,400;1,700",
}

_FONT_FALLBACK_MAP = {
    "Merriweather":  "serif",
    "Inter":         "'Helvetica Neue', Arial, sans-serif",
    "Roboto":        "Arial, sans-serif",
    "Poppins":       "'Helvetica Neue', sans-serif",
    "System Default": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
}


PT_TO_PX = 1.3333

def pt_to_px(pt_string):
    try:
        pt_val = float(pt_string.replace("pt", "").strip())
        return f"{round(pt_val * PT_TO_PX, 2)}px"
    except Exception:
        return pt_string

def get_typography_style_block(
    font_family="Merriweather",
    font_size_heading="25.33px",
    font_size_subheading="21.33px",
    font_size_body="14px",
    font_size_form_title="20px",
    font_size_toast="16px",
    primary_color="#920C24",
    secondary_color="#FFFFFF",
    button_border_radius="4px",
    navbar_color="#2B2E4A",
    footer_color="#fafafa",
    footer_text_color="#000000"
):
    ff = (font_family or "Merriweather").strip()
    if ff not in _FONT_FALLBACK_MAP:
        ff = "Merriweather"

    fallback = _FONT_FALLBACK_MAP[ff]

    # Resolve navbar and footer colors with backward compatibility fallbacks
    nav_c = navbar_color or "#2B2E4A"
    foot_c = footer_color or "#fafafa"
    foot_t = footer_text_color or "#000000"

    # Google Fonts link (skipped for System Default)
    link_tag = ""
    if ff != "System Default":
        gf_param = _FONT_GOOGLE_MAP.get(ff, _FONT_GOOGLE_MAP["Merriweather"])
        link_tag = (
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'<link href="https://fonts.googleapis.com/css2?{gf_param}&display=swap" rel="stylesheet">'
        )
        font_stack = f"'{ff}', {fallback}"
    else:
        font_stack = fallback

    style_block = f"""<style>
:root {{
  /* Typography */
  --font-family: {font_stack};
  --font-size-heading: {font_size_heading};
  --font-size-subheading: {font_size_subheading};
  --font-size-body: {font_size_body};
  --font-size-form-title: {font_size_form_title};
  --font-size-toast: {font_size_toast};

  /* Brand colours */
  --colour-primary: {primary_color};
  --colour-white: {secondary_color};
  --colour-dark-blue: {nav_c};
  --colour-beige: {foot_c};
  --colour-navbar: {nav_c};
  --colour-footer: {foot_c};
  --colour-footer-text: {foot_t};

  /* Semantic aliases */
  --colour-nav-bg: var(--colour-navbar);
  --colour-nav-text: var(--colour-white);
  --colour-hero-bg: var(--colour-primary);
  --colour-hero-text: var(--colour-white);
  --colour-footer-bg: var(--colour-footer);
  --colour-footer-text: var(--colour-footer-text);
  --colour-card-bg: var(--colour-white);
  --colour-card-hover-bg: var(--colour-beige);
  --colour-page-bg: var(--colour-white);
  --colour-section-alt-bg: var(--colour-beige);
  --colour-btn-primary-bg: var(--colour-primary);
  --colour-btn-primary-text: var(--colour-white);
  --colour-btn-primary-hover: var(--colour-navbar);
  --colour-btn-primary-hover-text: var(--colour-white);
  --colour-form-bg: var(--colour-beige);
  --colour-border: var(--colour-navbar);
  --colour-focus: var(--colour-primary);
  --colour-divider: var(--colour-beige);

  /* Components */
  --button-border-radius: {button_border_radius};
}}

/* Base */
body {{
  font-family: var(--font-family) !important;
  font-size: var(--font-size-body) !important;
  font-weight: 300 !important;
  line-height: 1.6 !important;
}}

/* Headings */
h1, .main-title, .page-title {{
  font-family: var(--font-family) !important;
  font-size: var(--font-size-heading) !important;
  font-weight: 400 !important;
  line-height: 1.2 !important;
}}

h2 {{
  font-family: var(--font-family) !important;
  font-size: var(--font-size-subheading) !important;
  font-weight: 400 !important;
  line-height: 1.2 !important;
}}

h3, h4, .department-name, .section-heading, .sub-title {{
  font-family: var(--font-family) !important;
  font-size: var(--font-size-subheading) !important;
  font-weight: 400 !important;
  line-height: 1.2 !important;
}}

/* Form titles */
h5, h6, .form-title, .modal-title, .card-title,
.accordion-header, .section-title {{
  font-family: var(--font-family) !important;
  font-size: var(--font-size-form-title) !important;
  font-weight: 400 !important;
  line-height: 1.2 !important;
}}

/* Body elements */
label, .form-label, input, textarea, select,
p, li, td, th, .card-text, .list-group-item,
.description, .help-text, .text-muted {{
  font-family: var(--font-family) !important;
  font-size: var(--font-size-body) !important;
  font-weight: 300 !important;
  line-height: 1.6 !important;
}}

strong, b {{
  font-weight: 600 !important;
}}

/* Toast and alerts */
.toast, .toast-body, .alert, .alert-heading,
.notification-text, .status-message {{
  font-family: var(--font-family) !important;
  font-size: var(--font-size-toast) !important;
  font-weight: 700;
  text-align: center;
}}

/* Buttons and navigation — font-family only, never font-size */
button, .btn, nav a, .nav-link, .navbar-brand {{
  font-family: var(--font-family) !important;
}}

button, .btn {{
  border-radius: var(--button-border-radius) !important;
}}

/* Component overrides */
.programme-card, .programme-title, .programme-info,
.tab-content, .tab-pane, .modal, .modal-body,
.table, .badge, .accordion-body, .offcanvas,
.offcanvas-body, .popover, .tooltip,
.dropdown-menu, .dropdown-item {{
  font-family: var(--font-family) !important;
}}

/* Nuclear override — catches everything else, excluding icons */
html body *:not(.material-symbols-outlined):not(.material-icons):not(.fa):not(.fas):not(.far):not(.fab):not(.sp-ms):not(.ms-icon):not([class*="fa-"]):not([style*="font-family: 'Material Symbols Outlined'"]):not([style*="font-family:'Material Symbols Outlined'"]) {{
  font-family: var(--font-family) !important;
}}

/* Explicitly protect icon families */
.material-symbols-outlined, .sp-ms, .ms-icon {{
  font-family: 'Material Symbols Outlined' !important;
}}
.material-icons {{
  font-family: 'Material Icons' !important;
}}
.fa, .fas, .far, .fab {{
  font-family: 'Font Awesome 6 Free', 'Font Awesome 6 Brands', 'Font Awesome 5 Free', 'Font Awesome 5 Brands', sans-serif !important;
}}
</style>"""

    # JavaScript MutationObserver block (emit immediately after </style>)
    observer_script = """<script>
(function () {
  function applyFont() {
    var ff = getComputedStyle(document.documentElement)
      .getPropertyValue('--font-family').trim();
    if (!ff) return;
    var skip = ['script','style','svg','path','defs','symbol','meta','link'];
    function isIcon(el) {
      if (!el) return false;
      var classes = el.className;
      if (typeof classes === 'string') {
        if (classes.indexOf('material-symbols-outlined') !== -1 ||
            classes.indexOf('material-icons') !== -1 ||
            classes.indexOf('fa') !== -1 ||
            classes.indexOf('sp-ms') !== -1 ||
            classes.indexOf('ms-icon') !== -1) {
          return true;
        }
      }
      var style = el.getAttribute('style');
      if (style && (style.indexOf('Material Symbols Outlined') !== -1 || style.indexOf('Material Icons') !== -1)) {
        return true;
      }
      return false;
    }
    function setFont(root) {
      var els = root.querySelectorAll('*');
      for (var i = 0; i < els.length; i++) {
        if (skip.indexOf(els[i].tagName.toLowerCase()) === -1 && !isIcon(els[i])) {
          els[i].style.setProperty('font-family', ff, 'important');
        }
      }
    }
    setFont(document.body);
    var obs = new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        m.addedNodes.forEach(function (n) {
          if (n.nodeType === 1) {
            if (skip.indexOf(n.tagName.toLowerCase()) === -1 && !isIcon(n)) {
              n.style && n.style.setProperty('font-family', ff, 'important');
            }
            setFont(n);
          }
        });
      });
    });
    obs.observe(document.documentElement, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyFont);
  } else {
    applyFont();
  }
})();
</script>"""

    icon_links = (
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200">\n'
        '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.6.0/css/all.min.css" integrity="sha512-Kc323vGBEqzTmouAECnVceyQqyqdsSiqLQISBL29aUW4U/M7pSPA/gEUZQqv1cwx4OnYxTxve5UMg5GT6L4JJg==" crossorigin="anonymous" referrerpolicy="no-referrer">'
    )

    return (icon_links + "\n" + link_tag + "\n" + style_block + "\n" + observer_script).strip()


def resolve_sizes(doc):
    preset = doc.font_size_preset or "Normal"
    preset_map = {
        "Small":  {"heading": "17pt", "subheading": "14pt", "body": "9pt",
                   "form_title": "13pt", "toast": "10pt"},
        "Normal": {"heading": "19pt", "subheading": "16pt", "body": "10.5pt",
                   "form_title": "15pt", "toast": "12pt"},
        "Large":  {"heading": "21pt", "subheading": "17pt", "body": "11.5pt",
                   "form_title": "16pt", "toast": "13pt"},
    }
    if preset == "Custom":
        raw = {
            "font_size_heading":    doc.font_size_heading    or "19pt",
            "font_size_subheading": doc.font_size_subheading or "16pt",
            "font_size_body":       doc.font_size_body        or "10.5pt",
            "font_size_form_title": doc.font_size_form_title  or "15pt",
            "font_size_toast":      doc.font_size_toast        or "12pt",
        }
    else:
        p = preset_map.get(preset, preset_map["Normal"])
        raw = {
            "font_size_heading":    p["heading"],
            "font_size_subheading": p["subheading"],
            "font_size_body":       p["body"],
            "font_size_form_title": p["form_title"],
            "font_size_toast":      p["toast"],
        }
    res = {k: pt_to_px(v) for k, v in raw.items()}
    res["font_size_preset"] = preset
    return res


# ── CONFIG ────────────────────────────────────────────────────────
@frappe.whitelist(allow_guest=True)
def api_get_portal_config():
    """Alias for get_portal_config to match JS expectations."""
    return get_portal_config()

@frappe.whitelist(allow_guest=True)
def api_get_announcements(limit=10):
    """Alias for get_active_announcements to match JS expectations."""
    return get_active_announcements(limit=limit)

@frappe.whitelist(allow_guest=True)
def api_get_programs():
    """Alias for get_active_programs to match JS expectations."""
    return get_active_programs()

@frappe.whitelist()
def api_get_my_application():
    """Returns the current user's application for the active cycle."""
    user = frappe.session.user
    if user == "Guest":
        return None
    
    active_cycle = frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")
    if not active_cycle:
        return None
        
    apps = frappe.get_all(
        "Applicant",
        filters={"owner": user, "admission_cycle": active_cycle},
        fields=["name", "candidate_name", "program", "campus", "admission_open_for", "admission_cycle", "status", "application_fee_status", "application_fee_amount", "creation"],
        limit=1
    )
    return apps[0] if apps else None

@frappe.whitelist(allow_guest=True)
def get_portal_config():
    """
    Returns Applicant Portal Config singleton.
    Falls back to safe defaults if not configured yet.
    """
    try:
        config = frappe.get_single("Applicant Portal Config")
        sizes = resolve_sizes(config)
        return {
            "portal_title": config.portal_title or "Admissions",
            "portal_subtitle": config.portal_subtitle or "",
            "hero_image": config.hero_image or "",
            # Colours
            "primary_color":         config.get("primary_color") or "#920C24",
            "secondary_color":       config.get("secondary_color") or "#FFFFFF",
            "navbar_color":          config.get("navbar_color") or "#2B2E4A",
            "footer_color":          config.get("footer_color") or "#fafafa",
            "footer_text_color":     config.get("footer_text_color") or "#000000",
            "button_border_radius":  config.get("button_border_radius") or "4px",
            "show_hero_section":     int(config.show_hero_section) if config.show_hero_section is not None else 0,
            "slideshow_images": [
                {"image": s.image, "caption": s.caption or "", "idx": s.idx or 0}
                for s in sorted(config.slideshow_images or [], key=lambda x: x.idx or 0)
            ],
            "show_announcement": config.show_announcement,
            "header_announcement": config.header_announcement or "",
            "show_admission_page": int(config.show_admission_page) if config.show_admission_page is not None else 0,
            "portal_active": config.portal_active if config.portal_active is not None else 1,
            "maintenance_message": config.maintenance_message or "",
            "program_card_layout": config.program_card_layout or "Grid",
            "show_intake_count": config.show_intake_count,
            "show_eligibility_hint": config.show_eligibility_hint,
            "login_required_for_application": config.login_required_for_application
                if config.login_required_for_application is not None else 1,
            "show_stage_progress": config.show_stage_progress
                if config.show_stage_progress is not None else 1,
            "progress_style": config.progress_style or "Steps",
            "allow_pdf_download": config.allow_pdf_download,
            "contact_email": config.contact_email or "",
            "contact_phone": config.contact_phone or "",
            "footer_text": config.footer_text or "",
            "submission_message": config.submission_message or "",
            "enable_portal_notifications": config.enable_portal_notifications
                if config.enable_portal_notifications is not None else 1,
            "portal_tagline": config.get("portal_tagline") or config.get("portal_subtitle") or "",
            "pace_tagline": config.get("pace_tagline") or config.get("pace_login_page_tagline_subtitle") or config.get("portal_subtitle") or "",
            "institution_since": config.get("institution_since") or "",
            "hero_cta_label": config.get("hero_cta_label") or "Explore Programs",
            "hero_cta2_label": config.get("hero_cta2_label") or "Virtual Tour",
            "footer_address": config.get("footer_address") or "",
            "footer_phone": config.get("footer_phone") or "",
            "footer_email": config.get("footer_email") or config.get("contact_email") or "",
            "powerd_by": config.get("powerd_by") or "boscosoft",
            "support_email": config.get("support_email") or "",
            "pace_support_email": config.get("pace_support_email") or "",
            "admission_website_url": config.get("admission_website_url") or "",
            "pace_website_url": config.get("pace_website_url") or "",
            "social_links": [
                {
                    "platform": row.platform,
                    "url": row.url,
                    "is_active": row.is_active
                } for row in (config.social_links or [])
            ],
            "font_family": config.get("font_family") or "Merriweather",
            "font_size_preset": sizes["font_size_preset"],
            "font_size_heading": sizes["font_size_heading"],
            "font_size_subheading": sizes["font_size_subheading"],
            "font_size_body": sizes["font_size_body"],
            "font_size_form_title": sizes["font_size_form_title"],
            "font_size_toast": sizes["font_size_toast"],
        }
    except Exception:
        # DocType not yet configured — return safe defaults
        return {
            "portal_title": "Admissions",
            "portal_subtitle": "",
            "hero_image": "",
            # Colours
            "primary_color":         "#920C24",
            "secondary_color":       "#FFFFFF",
            "navbar_color":          "#2B2E4A",
            "footer_color":          "#fafafa",
            "footer_text_color":     "#000000",
            "button_border_radius":  "4px",
            "show_hero_section":     0,
            "slideshow_images": [],
            "show_announcement": 0,
            "header_announcement": "",
            "show_admission_page": 0,
            "portal_active": 1,
            "maintenance_message": "",
            "program_card_layout": "Grid",
            "show_intake_count": 0,
            "show_eligibility_hint": 0,
            "login_required_for_application": 1,
            "show_stage_progress": 1,
            "progress_style": "Steps",
            "allow_pdf_download": 1,
            "contact_email": "",
            "contact_phone": "",
            "footer_text": "",
            "submission_message": "",
            "enable_portal_notifications": 1,
            "portal_tagline": "",
            "institution_since": "",
            "hero_cta_label": "Explore Programs",
            "hero_cta2_label": "Virtual Tour",
            "footer_address": "",
            "footer_phone": "",
            "footer_email": "",
            "powerd_by": "boscosoft",
            "support_email": "",
            "pace_support_email": "",
            "admission_website_url": "",
            "pace_website_url": "",
            "social_links": [],
            "font_family": "Merriweather",
            "font_size_preset": "Normal",
            "font_size_heading": "25.33px",
            "font_size_subheading": "21.33px",
            "font_size_body": "14px",
            "font_size_form_title": "20px",
            "font_size_toast": "16px",
        }


def get_portal_website_branding():
    """
    Safe site title + banner for portal Jinja (Website Settings schema varies by Frappe version;
    field "title" no longer exists — use app_name / title_prefix).
    """
    title = ""
    banner = ""
    try:
        if not frappe.db.exists("DocType", "Website Settings"):
            return {"title": title, "banner_image": banner}
        meta = frappe.get_meta("Website Settings")
        for fn in ("app_name", "title_prefix"):
            if meta.has_field(fn):
                v = frappe.db.get_single_value("Website Settings", fn)
                if v and str(v).strip():
                    title = str(v).strip()
                    break
        if meta.has_field("banner_image"):
            banner = frappe.db.get_single_value("Website Settings", "banner_image") or ""
    except Exception:
        pass
    return {"title": title, "banner_image": banner}


def update_website_context(context):
    """
    Globally provides portal_config and sp_settings to all website templates.
    """
    context.portal_config = get_portal_config()
    try:
        from slcm.slcm.doctype.student_portal_settings.student_portal_settings import (
            get_student_portal_settings,
        )
        context.sp_settings = get_student_portal_settings()
    except Exception:
        context.sp_settings = {}
        
    try:
        context.portal_config = get_portal_config()

        # PACE Admission toggle (used by admission_base navbar)
        # Keep it safe: never break public pages if PACE config isn't installed yet.
        try:
            pc = frappe.get_single("Applicant Portal Config")
            context.pace_enabled = int(pc.enable_pace_admission or 0) if pc else 0
            
            # Provide current path safely for templates
            context.current_path = (getattr(frappe.local, "request", None) and getattr(frappe.local.request, "path", "")) or context.get("path") or ""
        except Exception:
            context.pace_enabled = 0
            context.current_path = context.get("path") or ""
        
        # Issue 2: Fetch active programs for the footer -> Replaced by Dynamic Footer Context
        try:
            pc_doc = frappe.get_doc("Applicant Portal Config", "Applicant Portal Config", ignore_permissions=True)
            
            def format_footer(rows):
                cols = []
                curr = None
                for r in rows:
                    if r.get("is_parent"):
                        curr = {"title": r.get("label"), "links": []}
                        cols.append(curr)
                    else:
                        if curr is None:
                            curr = {"title": "", "links": []}
                            cols.append(curr)
                        curr["links"].append({"label": r.get("label"), "route": r.get("route")})
                return cols

            context.admission_footer = format_footer(pc_doc.get("admission_footer") or [])
            context.pace_footer = format_footer(pc_doc.get("pace_footer") or [])
            context.footer_text = pc_doc.get("footer_text") or ""
        except Exception:
            context.admission_footer = []
            context.pace_footer = []
            context.footer_text = ""

        # Institution logo from Institution Settings (used in footer & login brand block)
        try:
            context.institution_logo = frappe.db.get_single_value("Institution Settings", "logo") or ""
        except Exception:
            context.institution_logo = ""

        # Hide standard signup link on default Frappe login page since applicants register via /admission/login
        if context.get("pathname") == "login" or (isinstance(context.get("template"), str) and context.get("template").endswith("login.html")):
            context.disable_signup = True
        
    except Exception as e:
        frappe.log_error(
            title="update_website_context failed",
            message=frappe.get_traceback(),
        )
        context.portal_config = {
            "portal_title": "Admissions",
            "portal_active": 1,
            "primary_color": "#1a3c6e",
            "secondary_color": "#c8a14b",
            "social_links": [],
        }
        context.admission_footer = []
        context.pace_footer = []
        context.pace_enabled = 0

@frappe.whitelist(allow_guest=True)
def api_get_hero_slides():
    """
    Returns all slides for the hero banner carousel.
    hero_image is always slide 1.
    slideshow_images child table provides slides 2, 3, 4...
    Returns empty list if neither is set — JS shows text-only hero.
    """
    try:
        config = frappe.get_single("Applicant Portal Config")
        slides = []

        # Slide 1: hero_image (always first if set)
        hero_image = config.get("hero_image")
        if hero_image:
            slides.append({
                "url": hero_image,
                "caption": config.get("portal_title") or "",
                "link_url": ""
            })

        # Slides 2+: slideshow_images child table
        for row in config.get("slideshow_images") or []:
            if row.get("image"):
                slides.append({
                    "url": row.image,
                    "caption": row.get("caption") or "",
                    "link_url": row.get("link_url") or ""
                })

        return slides

    except Exception as e:
        frappe.log_error(f"api_get_hero_slides error: {e}", "Portal API")
        return []

# ── PROGRAMS ──────────────────────────────────────────────────────

@frappe.whitelist()
def api_get_all_program_statuses(cycle):
    """Returns mapping of program name to its current application status."""
    if not cycle or frappe.session.user == "Guest":
        return {}
    
    apps = frappe.get_all(
        "Applicant",
        filters={"owner": frappe.session.user, "admission_cycle": cycle},
        fields=["program", "status"]
    )
    
    return {a.program: a.status for a in apps}

@frappe.whitelist(allow_guest=True)
def get_active_programs():
    """
    Returns programs listed in the currently active Admission Cycle.
    """
    try:
        active_cycle = frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")
        if not active_cycle:
            return []

        multi_campus = is_multi_campus_enabled()

        programs = frappe.get_all(
            "Admission Cycle Program",
            filters={"parent": active_cycle, "is_active": 1},
            fields=[
                "program", "program_name", "seats", "eligibility_hint",
                "brochure_url", "program_image", "desciption",
                "program_media", "reservation_policy", "max_applications",
                "application_count", "program_level", "intake_type", "campus", "admission_open_for",
            ],
            order_by="program_name asc"
        )

        # We now rely on the "application_count" field in the child table, 
        # which is updated in real-time by Applicant DocType hooks.

        import re as _re
        for p in programs:
            p["admission_cycle"] = active_cycle
            p["multi_campus_enabled"] = 1 if multi_campus else 0
            p["campus_label"] = (p.get("campus") or "").strip()
            if multi_campus and p.get("campus"):
                try:
                    campus_title = (
                        frappe.db.get_value("Campus", p.get("campus"), "campus_name")
                        or p.get("campus")
                    )
                    p["campus_label"] = campus_title
                except Exception:
                    p["campus_label"] = p.get("campus")
            # Fetch slug, abbreviation, and other details from Program
            prog_info = frappe.db.get_value("Programme", p.program,
                ["program_slug", "program_code", "program_duration", "program_image", "program_description", "brochure_file", "level_of_study", "application_form_link"],
                as_dict=True
            )
            if prog_info:
                prog_info = frappe._dict(prog_info)
                p["program_slug"] = prog_info.program_slug or _re.sub(r'[^a-z0-9]+', '-', (p.program or "").lower()).strip('-')
                p["program_abbreviation"] = prog_info.program_code
                p["duration"] = f"{prog_info.program_duration} Years" if prog_info.program_duration else ""
                p["program_image"] = prog_info.program_image or p.get("program_image")
                p["program_description"] = prog_info.program_description
                p["brochure_file"] = prog_info.brochure_file
                p["program_level"] = prog_info.level_of_study or p.get("program_level")
                p["application_form_link"] = prog_info.application_form_link
            else:
                p["program_slug"] = _re.sub(r'[^a-z0-9]+', '-', (p.program or "").lower()).strip('-')
                p["program_abbreviation"] = ""
                p["duration"] = ""
                p["program_description"] = ""
                p["brochure_file"] = ""
                p["application_form_link"] = ""

            p["description"] = p.get("desciption") or ""
            
            raw = p.get("desciption") or ""
            if raw:
                # 20 words plain text for cards
                plain = _re.sub(r'<[^>]+>', '', raw).strip()
                words = plain.split()
                p["desc_short"]    = ' '.join(words[:20])
                p["desc_full"]     = raw
                p["desc_has_more"] = len(words) > 20
            else:
                p["desc_short"]    = p.get("eligibility_hint") or ""
                p["desc_full"]     = ""
                p["desc_has_more"] = False

            # Fill badge
            max_apps = int(p.get("max_applications") or 0)
            received = int(p.get("application_count") or 0)

            # If max_applications is 0, assume there is no limitation for intake.
            if max_apps > 0:
                total = max_apps
                pct = min(100, round((received / total) * 100)) if total else 0
                p["fill_pct"] = pct
                p["seats_limit"] = total
                p["seats_remaining"] = max(0, total - received)

                p["seats_full"] = received >= total
                p["seats_almost_full"] = (not p["seats_full"]) and pct >= 90

                if p["seats_full"]:
                    p["fill_badge"] = "Seats Full"
                    p["fill_class"] = "fill-danger"
                elif p["seats_almost_full"]:
                    p["fill_badge"] = "Seat Almost Filled"
                    p["fill_class"] = "fill-warning"
                elif pct >= 70:
                    p["fill_badge"] = f"{pct}% filled"
                    p["fill_class"] = "fill-warning"
                elif pct >= 40:
                    p["fill_badge"] = f"{pct}% filled"
                    p["fill_class"] = "fill-info"
                else:
                    p["fill_badge"] = "Seats available"
                    p["fill_class"] = "fill-success"
            else:
                p["fill_pct"] = 0
                p["seats_limit"] = 0
                p["seats_remaining"] = None
                p["seats_full"] = False
                p["seats_almost_full"] = False
                p["fill_badge"] = "Open Intake"
                p["fill_class"] = "fill-success"

        return programs
    except Exception as e:
        frappe.log_error(f"get_active_programs failed: {e}", "Portal")
        return []

def get_active_events(limit=4, target_audience=None):
    """Returns announcements of type Event, sorted by event_date."""
    try:
        meta = frappe.get_meta("Portal Announcement")
        fields_available = [f.fieldname for f in meta.fields]
        
        # Base fields we know exist
        fields = ["name", "title", "summary", "announcement_type", "creation"]
        
        # Optional fields
        optional = ["publish_date", "event_date", "event_venue", "featured_image", "created_by_role"]
        for f in optional:
            if f in fields_available:
                fields.append(f)

        filters = {
            "announcement_type": "Event",
            "is_active": 1,
            "status": "Published"
        }
        if target_audience:
            filters["target_audience"] = ["in", target_audience]

        return frappe.get_all(
            "Portal Announcement",
            filters=filters,
            fields=fields,
            order_by="event_date asc" if "event_date" in fields_available else "creation desc",
            limit=limit
        )
    except Exception as e:
        frappe.log_error(f"get_active_events failed: {e}", "Portal")
        return []

@frappe.whitelist(allow_guest=True)
def api_get_program_images(program, cycle):
    """Returns image gallery for a program in a cycle."""
    res = api_get_program_detail(program, cycle)
    return res.get("images") if res else []

@frappe.whitelist(allow_guest=True)
def api_get_program_detail(program, cycle):
    """Returns full detail for one program including media and categories."""
    try:
        # Get cycle program row
        cp = frappe.db.get_value(
            "Admission Cycle Program",
            {"parent": cycle, "program": program},
            ["program_name", "seats", "eligibility_hint", "brochure_url", "desciption", "program_media", "reservation_policy"],
            as_dict=True
        )
        if not cp: return None

        res = {
            "program": program,
            "program_name": cp.program_name or program,
            "program_abbreviation": frappe.db.get_value("Programme", program, "program_code") or "",
            "total_seats": cp.seats or 0,
            "eligibility_hint": cp.eligibility_hint or "",
            "brochure_url": cp.brochure_url or "",
            "description": cp.desciption or "",
            "images": [],
            "videos": [],
            "categories": []
        }

        # Media
        if cp.program_media:
            # brochure_pdf is in Program Media DocType
            brochure_pdf = frappe.db.get_value("Program Media", cp.program_media, "brochure_pdf")
            if brochure_pdf:
                res["brochure_url"] = brochure_pdf

            # media_gallery is the child table fieldname in Program Media
            media_list = frappe.get_all(
                "Media",
                filters={"parent": cp.program_media, "parentfield": "media_gallery"},
                fields=["media_type", "file", "caption", "sequence"],
                order_by="sequence asc"
            )
            for m in media_list:
                if m.media_type == "Image":
                    res["images"].append(m)
                else:
                    res["videos"].append({"video_url": m.file, "caption": m.caption})

        # Categories & Fees from Reservation Policy
        if cp.reservation_policy:
            cats = frappe.get_all(
                "Programme Reservation Category",
                filters={"parent": cp.reservation_policy},
                fields=["category_name", "total_seats", "application_fee"],
                order_by="total_seats desc"
            )
            res["categories"] = cats

        return res
    except Exception as e:
        frappe.log_error(f"api_get_program_detail failed: {e}", "Portal")
        return None


# ── STATS & ANNOUNCEMENTS ───────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def api_get_campus_options():
    """Returns list of active campuses."""
    return frappe.get_all("Company", filters={"is_group": 0}, fields=["name", "company_name"])

@frappe.whitelist()
def api_get_application_fee(program, cycle, category=None):
    """Returns the application fee for a program and category."""
    detail = api_get_program_detail(program, cycle)
    if not detail or not detail.get("categories"):
        return 0
    
    if category:
        for cat in detail["categories"]:
            if cat.category_name == category:
                return cat.application_fee or 0
    
    return detail["categories"][0].get("application_fee") or 0

@frappe.whitelist(allow_guest=True)
def api_get_portal_stats():
    """Returns live stats for the admission dashboard."""
    try:
        active_cycle = frappe.db.get_value(
            "Admission Cycle", {"status": "Active"},
            ["name"], as_dict=True
        )
        if not active_cycle: return {}

        active_cycle_name = active_cycle.get("name")
        total_programs = frappe.db.count("Admission Cycle Program", {"parent": active_cycle_name, "is_active": 1})
        
        # Sum seats from policy if available, else from program row
        total_seats = 0
        cycle_progs = frappe.get_all("Admission Cycle Program", filters={"parent": active_cycle_name, "is_active": 1}, fields=["seats", "reservation_policy"])
        for p in cycle_progs:
            if p.reservation_policy:
                total_seats += frappe.db.get_value("Programme Reservation Policy", p.reservation_policy, "total_seats") or 0
            else:
                total_seats += p.seats or 0

        return {
            "total_programs": total_programs,
            "total_seats": total_seats,
        }
    except Exception:
        return {}

@frappe.whitelist(allow_guest=True)
def api_get_announcement_detail(ann_name):
    """Returns full detail for one announcement."""
    if not ann_name or not frappe.db.exists("Portal Announcement", ann_name):
        return None
    doc = frappe.get_doc("Portal Announcement", ann_name)
    if not doc.is_active:
        return None
    return doc.as_dict()

@frappe.whitelist(allow_guest=True)
def api_increment_view_count(ann_name):
    """Increments the view count for an announcement."""
    if not ann_name: return
    frappe.db.sql("""
        UPDATE `tabPortal Announcement` 
        SET view_count = view_count + 1 
        WHERE name = %s
    """, ann_name)
    frappe.db.commit()

@frappe.whitelist()
def api_mark_notification_read(notification_id):
    """Alias for web.mark_notifications_read for single ID."""
    from slcm.admission.utils.web import mark_notifications_read
    return mark_notifications_read([notification_id])

@frappe.whitelist(allow_guest=True)
def get_active_announcements(limit=10, target_audience=None):
    """Returns active announcements for display on portal"""
    try:
        filters = {"is_active": 1, "status": "Published"}
        if target_audience:
            filters["target_audience"] = ["in", target_audience]
            
        anns = frappe.get_all("Portal Announcement",
            filters=filters,
            fields=["name", "title", "announcement_type", "summary",
                    "featured_image", "publish_date", "event_date",
                    "event_venue", "created_by_role", "owner"],
            order_by="publish_date desc",
            limit=limit
        )
        for a in anns:
            # Enrich with owner full name if created_by_role not set
            if not a.get("created_by_role") and a.get("owner"):
                a["created_by_role"] = frappe.db.get_value(
                    "User", a.owner, "full_name"
                ) or a.owner
        return anns
    except Exception as e:
        frappe.log_error(f"get_active_announcements failed: {e}", "Portal")
        return []


# ── UTILS ─────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def api_get_program_media(program_media=None):
    """Returns media items for a gallery, or all media if not specified."""
    if program_media:
        return frappe.get_all(
            "Media",
            filters={"parent": program_media},
            fields=["media_type", "file", "caption", "sequence"],
            order_by="sequence asc"
        )
    
    # Return all media across all programs for applicant_portal compat
    media_list = frappe.db.sql("""
        SELECT 
            m.parent as program_media,
            acp.program,
            m.media_type,
            m.file as image,
            m.file as video_url,
            m.caption,
            m.sequence,
            0 as is_featured
        FROM `tabMedia` m
        JOIN `tabAdmission Cycle Program` acp ON m.parent = acp.program_media
        WHERE acp.is_active = 1
        ORDER BY m.sequence ASC
    """, as_dict=True)
    
    # Also add brochure_pdfs from acp.brochure_url
    brochures = frappe.db.sql("""
        SELECT 
            acp.program,
            'Brochure' as media_type,
            acp.brochure_url as brochure_pdf,
            0 as sequence
        FROM `tabAdmission Cycle Program` acp
        WHERE acp.is_active = 1 AND acp.brochure_url IS NOT NULL AND acp.brochure_url != ''
    """, as_dict=True)
    
    return media_list + brochures

def lock_expired_drafts():
    """Scheduler task to lock drafts after cycle deadline."""
    # This logic needs to be updated to use Stages or Deadlines instead of cycle.application_end
    pass

@frappe.whitelist()
def api_get_stage_progress(applicant=None):
    """Stub for applicant_portal.js"""
    return []

@frappe.whitelist()
def api_get_campus_status(applicant=None):
    """Stub for applicant_portal.js"""
    return []

def is_application_editable(applicant):
    """
    Returns True if the application is currently editable by the applicant.
    This is determined by the 'is_editable' flag on the current stage
    of the Admission Cycle that matches the application's status.
    """
    if isinstance(applicant, str):
        applicant = frappe.get_doc("Applicant", applicant, ignore_permissions=True)
    
    # If no status, default to True (Draft-like)
    if not applicant.get("status"):
        return True
    
    # If no admission_cycle, we can't look up stages
    if not applicant.get("admission_cycle"):
        return True
    
    current_status = applicant.status
    
    # Draft is always editable by default, overriding stage settings
    if current_status == "Draft":
        return True
    
    # Fetch stages for this cycle
    stages = frappe.get_all(
        "Admission Cycle Stage",
        filters={
            "parent": applicant.admission_cycle,
            "is_enabled": 1
        },
        fields=["activate_status", "completed_status", "closed_status", "is_editable", "applicable_workflow"],
        order_by="sequence_no asc"
    )
    
    intake = applicant.get("intake_type") or "External Test"
    filtered_stages = [
        s for s in stages
        if s.applicable_workflow == "All" or s.applicable_workflow == intake
    ]
    
    # Look for the stage that matches current status
    for s in filtered_stages:
        if s.activate_status == current_status:
            return bool(s.is_editable)
        if s.completed_status == current_status:
            next_stage_match = any(st.activate_status == current_status for st in filtered_stages)
            if next_stage_match:
                continue
            return bool(s.is_editable)
        
    return False
