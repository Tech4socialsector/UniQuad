# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# ── Defaults ─────────────────────────────────────────────────────────
_DEFAULTS = {
    # Branding
    "portal_title":          "National Law School of India University",
    "portal_subtitle":       "",
    "show_logo":             1,
    "nav_brand_text":        "",
    "portal_favicon":        "",
    # Typography
    "font_family":           "Merriweather",
    "font_size":             "Normal",
    # Theme — NLSIU palette (mirrors Parent Portal Settings › Theme Colors)
    "primary_color":         "#920c24",   # NLSIU maroon — active menu, buttons
    "secondary_color":       "#c9a84c",   # NLSIU gold accent
    "background_color":      "#f0f2f5",   # Light grey — same as Parent & Faculty portals
    "card_background":       "#ffffff",
    "nav_bg_color":          "#ffffff",
    "nav_text_color":        "#920c24",
    "sidebar_bg_color":      "#ffffff",
    "sidebar_text_color":    "#920c24",
    # Status colors
    "success_color":         "#16a34a",
    "warning_color":         "#920c24",
    "danger_color":          "#dc2626",
    "info_color":            "#920c24",
    # Grading
    "grade_excellent_color": "#16a34a",
    "grade_excellent_label": "A+ / A / S",
    "grade_good_color":      "#920c24",
    "grade_good_label":      "B+ / B",
    "grade_average_color":   "#920c24",
    "grade_average_label":   "C+ / C",
    "grade_color": "#000000",
            "grade_fail_color":      "#dc2626",
    "grade_fail_label":      "D / F",
    # Attendance thresholds
    "att_good_threshold":    75,
    "att_warn_threshold":    60,
    "att_label_good":        "Good",
    "att_label_warn":        "Low",
    "att_label_danger":      "Critical",
    # Layout
    "sidebar_position":      "Left",
    "sidebar_width":         "Normal",
    "nav_height":            "Normal",
    "corner_style":          "Normal",
    "layout_density":        "Normal",
    "show_student_id_sidebar": 1,
    # Features
    "show_announcements_ticker": 1,
    "show_cgpa":             1,
    "show_today_classes":    1,
    "show_fee_summary":      1,
    "show_quick_actions":    1,
    "show_course_insights":  1,
    "show_enrollment_info":  1,
    # Navigation menus — Main Menu section
    "select_all_menus":       1,
    "menu_dashboard":         1,
    "menu_courses":           1,
    "menu_attendance":        1,
    "menu_timetable":         1,
    "menu_exam_schedule":     1,
    "menu_fees":              1,
    "menu_results":           1,
    "menu_announcements":     1,
    "menu_enrollment":        1,
    "menu_venue_booking":     1,
    # Navigation menus — My Info section
    "menu_profile":           1,
    "menu_documents":         1,
    "menu_grade_appeal":      1,
    "menu_transcript_request":1,
    "menu_placement":         1,
    "menu_helpdesk":          1,
    # Portal navigation
    "enable_re_exam_menu":    1,
    "enable_counter_payment_re_exam": 1,
    "enable_counter_payment_fees":    1,
    # Documents page
    "show_uploaded_documents": 1,
    # Fee reminders
    "enable_fee_reminders":      1,
    "reminder_sender_name":      "Finance & Accounts Office",
    "reminder_from_email":       "",
    "enable_7day_reminder":      1,
    "reminder_7day_template":    "Student Fee Reminder - 7 Days Before Due",
    "enable_1day_reminder":      1,
    "reminder_1day_template":    "Student Fee Reminder - 1 Day Before Due",
    "enable_overdue_notice":     1,
    "overdue_notice_offset":     3,
    "overdue_notice_template":   "Student Fee Overdue Notice",
    # Advanced
    "custom_css":            "",
}

# ── Font mappings ─────────────────────────────────────────────────────
_FONT_CSS = {
    "Merriweather":   "'Merriweather', Georgia, serif",
    "Poppins":        "'Poppins', system-ui, -apple-system, sans-serif",
    "Inter":          "'Inter', system-ui, -apple-system, sans-serif",
    "Roboto":         "'Roboto', system-ui, -apple-system, sans-serif",
    "System Default": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
}

# Only fonts NOT already in the base template's default Google Fonts link
_FONT_GOOGLE_URL = {
    "Roboto":         "https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap",
}

# ── Nav height mappings ───────────────────────────────────────────────
_NAV_HEIGHT = {
    "Compact": "50px",
    "Normal":  "60px",
    "Tall":    "72px",
}


class StudentPortalSettings(Document):
    def validate(self):
        self._validate_colors()
        self._validate_contrast()
        self._validate_thresholds()

    def on_update(self):
        frappe.clear_document_cache(self.doctype, self.name)

    def _validate_contrast(self):
        """Text identical to its background would make the navbar/sidebar unreadable."""
        for bg, fg, where in (
            ("nav_bg_color", "nav_text_color", "Navbar"),
            ("sidebar_bg_color", "sidebar_text_color", "Sidebar"),
        ):
            b = (self.get(bg) or _DEFAULTS[bg]).strip().lower()
            f = (self.get(fg) or _DEFAULTS[fg]).strip().lower()
            if _is_valid_hex(b) and _is_valid_hex(f) and _expand_hex(b) == _expand_hex(f):
                frappe.throw(f"{where} text colour is the same as the {where.lower()} background — the text would be invisible.")

    def _validate_colors(self):
        color_fields = [
            "primary_color", "secondary_color", "background_color", "card_background",
            "nav_bg_color", "nav_text_color", "sidebar_bg_color", "sidebar_text_color",
            "success_color", "warning_color", "danger_color", "info_color",
            "grade_color", "grade_fail_color",
        ]
        for field in color_fields:
            val = (self.get(field) or "").strip()
            if val and not _is_valid_hex(val):
                label = self.meta.get_field(field).label
                frappe.throw(f"<b>{label}</b> must be a valid hex color (e.g. #1a3c6e or #fff)")

    def _validate_thresholds(self):
        good = float(self.att_good_threshold or 75)
        warn = float(self.att_warn_threshold or 60)
        if good < 0 or good > 100:
            frappe.throw("Good Attendance Threshold must be between 0 and 100")
        if warn < 0 or warn > 100:
            frappe.throw("Warning Attendance Threshold must be between 0 and 100")
        if warn >= good:
            frappe.throw("Warning Attendance Threshold must be lower than the Good Attendance Threshold")


# ── Private helpers ───────────────────────────────────────────────────

def _is_valid_hex(color):
    import re
    return bool(re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", color.strip()))


def _expand_hex(color):
    h = color.strip().lstrip("#").lower()
    return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)


def _hex_to_rgba(hex_color, alpha):
    """#RRGGBB  →  rgba(r, g, b, alpha)"""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _darken_hex(hex_color, factor=0.82):
    """Return a darkened hex color."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#{:02x}{:02x}{:02x}".format(
        max(0, int(r * factor)),
        max(0, int(g * factor)),
        max(0, int(b * factor)),
    )


# ── Public API ────────────────────────────────────────────────────────

_CHECK_FIELDS = frozenset({
    "show_logo", "show_student_id_sidebar",
    "show_announcements_ticker", "show_cgpa", "show_today_classes",
    "show_fee_summary", "show_quick_actions",
    "show_course_insights", "show_enrollment_info",
    "show_uploaded_documents", "enable_re_exam_menu",
    "enable_counter_payment_re_exam", "enable_counter_payment_fees",
    # Navigation menu toggles
    "select_all_menus",
    "menu_dashboard", "menu_courses", "menu_attendance", "menu_timetable",
    "menu_exam_schedule", "menu_fees", "menu_results", "menu_announcements",
    "menu_enrollment", "menu_venue_booking",
    "menu_profile", "menu_documents", "menu_grade_appeal",
    "menu_transcript_request", "menu_placement", "menu_helpdesk",
    # Fee reminder toggles
    "enable_fee_reminders", "enable_7day_reminder",
    "enable_1day_reminder", "enable_overdue_notice",
    "enable_improvement_exam_menu", "enable_counter_payment_improvement",
})


def get_student_portal_settings():
    """
    Returns a fully-resolved settings dict suitable for Jinja template use.
    All CSS-derived values (rgba, darkened shades, body classes) are pre-computed.
    Falls back to safe defaults when the doctype is missing or not yet configured.
    """
    try:
        doc = frappe.get_single("Student Portal Settings")
        # tabSingles only contains rows for fields that were explicitly saved.
        # Frappe's _fix_numeric_types converts unset Check fields to 0 on the doc
        # object, making them indistinguishable from an explicit "disabled" save.
        # We query tabSingles directly so we can fall back to _DEFAULTS for fields
        # that were never saved (instead of treating the Frappe-injected 0 as intent).
        saved = frappe.db.get_singles_dict("Student Portal Settings")
        # Fields without a coded default (logo, attachments, print formats …)
        raw = {f.fieldname: doc.get(f.fieldname) for f in doc.meta.fields
               if f.fieldtype not in ("Section Break", "Column Break", "Tab Break", "HTML")}
        for k, default_val in _DEFAULTS.items():
            v = getattr(doc, k, None)
            if k in _CHECK_FIELDS:
                # Use saved value only when the row exists in tabSingles;
                # otherwise keep our default (important for newly-added fields).
                raw[k] = int(saved[k]) if k in saved else default_val
            else:
                raw[k] = v if v not in (None, "") else default_val
        # Sites saved before the Navbar/Sidebar split only have `sidebar_theme`
        legacy = (raw.get("sidebar_theme") or "").strip()
        if _is_valid_hex(legacy):
            for k in ("nav_bg_color", "sidebar_bg_color"):
                if not saved.get(k):
                    raw[k] = legacy
    except Exception:
        raw = dict(_DEFAULTS)

    # Never hand the template an invalid colour (e.g. a stray "Dark")
    for k in ("primary_color", "secondary_color", "background_color", "card_background",
              "nav_bg_color", "nav_text_color", "sidebar_bg_color", "sidebar_text_color",
              "success_color", "warning_color", "danger_color", "info_color",
              "grade_color", "grade_fail_color", "grade_excellent_color",
              "grade_good_color", "grade_average_color"):
        if not _is_valid_hex(str(raw.get(k) or "")):
            raw[k] = _DEFAULTS[k]

    # ── Derived primary palette ───────────────────────────────────
    primary = raw["primary_color"]
    raw["primary_dark"]  = _darken_hex(primary, 0.82)
    raw["primary_light"] = _hex_to_rgba(primary, 0.1)
    raw["primary_mid"]   = _hex_to_rgba(primary, 0.2)

    # ── Derived status bg variants ────────────────────────────────
    for col, alpha in (("success", 0.15), ("warning", 0.15), ("danger", 0.15), ("info", 0.12)):
        raw[f"{col}_bg"] = _hex_to_rgba(raw[f"{col}_color"], alpha)

    # ── Derived grade bg variants ─────────────────────────────────
    for band in ("excellent", "good", "average", "fail"):
        raw[f"grade_{band}_bg"] = _hex_to_rgba(raw[f"grade_{band}_color"], 0.15)

    # ── Nav text color as rgba (for 80% opacity hover) ────────────
    raw["nav_text_rgba_80"] = _hex_to_rgba(raw["nav_text_color"], 0.8)

    # ── Font family CSS value + optional Google Fonts URL ─────────
    raw["font_family_css"] = _FONT_CSS.get(raw["font_family"], _FONT_CSS["Merriweather"])
    raw["font_google_url"] = _FONT_GOOGLE_URL.get(raw["font_family"], "")

    # ── Nav height CSS value ──────────────────────────────────────
    raw["nav_height_css"] = _NAV_HEIGHT.get(raw["nav_height"], "60px")

    # ── Attendance thresholds as floats ───────────────────────────
    raw["att_good_threshold"] = float(raw["att_good_threshold"] or 75)
    raw["att_warn_threshold"] = float(raw["att_warn_threshold"] or 60)

    # ── Body CSS classes ──────────────────────────────────────────
    body_classes = []

    if raw["font_size"] == "Small":
        body_classes.append("sp-font-sm")
    elif raw["font_size"] == "Large":
        body_classes.append("sp-font-lg")

    if raw["layout_density"] == "Compact":
        body_classes.append("sp-compact")

    if raw["corner_style"] == "Sharp":
        body_classes.append("sp-corners-sharp")
    elif raw["corner_style"] == "Pill":
        body_classes.append("sp-corners-pill")

    if raw["sidebar_width"] == "Narrow":
        body_classes.append("sp-sidebar-narrow")
    elif raw["sidebar_width"] == "Wide":
        body_classes.append("sp-sidebar-wide")

    if raw["sidebar_position"] == "Right":
        body_classes.append("sp-right-sidebar")

    if raw["nav_height"] == "Compact":
        body_classes.append("sp-nav-compact")
    elif raw["nav_height"] == "Tall":
        body_classes.append("sp-nav-tall")

    raw["body_classes"] = " ".join(body_classes)

    return raw
