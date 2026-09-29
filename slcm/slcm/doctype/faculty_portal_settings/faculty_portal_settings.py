# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# ── Defaults ──────────────────────────────────────────────────────────
_DEFAULTS = {
    # Branding
    "portal_title":          "Faculty Portal",
    "portal_subtitle":       "",
    "show_logo":             1,
    "nav_brand_text":        "",
    "portal_favicon":        "",
    # Typography
    "font_family":           "Poppins",
    "font_size":             "Normal",
    # Theme
    "primary_color":         "#920c24",
    "secondary_color":       "#c9a84c",
    "background_color":      "#f0f2f5",
    "card_background":       "#ffffff",
    "sidebar_theme":         "Light",
    "nav_text_color":        "#ffffff",
    "sidebar_active_text_color": "#ffffff",
    "sidebar_menu_text_color":         "#475569",
    "sidebar_menu_hover_bg_color":     "#f0f4f8",
    "sidebar_menu_hover_text_color":   "#0f172a",
    # Status colors
    "success_color":         "#920c24",
    "warning_color":         "#920c24",
    "danger_color":          "#dc2626",
    "info_color":            "#0369a1",
    # Grading
    "grade_excellent_color": "#16a34a",
    "grade_excellent_label": "A+ / A / S",
    "grade_good_color":      "#0369a1",
    "grade_good_label":      "B+ / B",
    "grade_average_color":   "#d97706",
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
    "sidebar_position":         "Left",
    "sidebar_width":            "Normal",
    "nav_height":               "Normal",
    "corner_style":             "Normal",
    "layout_density":           "Normal",
    "show_faculty_id_sidebar":  1,
    "show_department_sidebar":  1,
    # Dashboard features
    "show_announcements_ticker":        1,
    "show_today_schedule":              1,
    "show_pending_evaluations":         1,
    "show_class_statistics":            1,
    "show_quick_actions":               1,
    "show_workload_summary":            1,
    "show_leave_status":                1,
    "show_student_performance_overview":1,
    "show_upcoming_exams":              1,
    # Attendance module
    "enable_attendance_marking":         1,
    "enable_bulk_attendance":            1,
    "show_student_photos_attendance":    1,
    "auto_close_session_minutes":        120,
    "enable_proxy_attendance_alert":     1,
    "allow_attendance_edit_window_days": 2,
    # Marks & Grading
    "enable_marks_entry":               1,
    "enable_internal_marks":            1,
    "show_class_grade_statistics":      1,
    "allow_marks_edit_after_submission": 0,
    "marks_edit_approval_required":     1,
    "enable_grade_remarks":             1,
    # Assignments
    "enable_assignment_module":             1,
    "allow_late_submission_marking":        1,
    "assignment_submission_notification":   1,
    "show_plagiarism_indicator":            0,
    # Student interaction
    "enable_office_hours":              1,
    "show_student_contact_info":        1,
    "enable_student_query_system":      1,
    "office_hours_advance_booking_days":7,
    "max_office_hour_bookings":         10,
    # Leave & Workload
    "enable_leave_request":         1,
    "show_workload_indicator":      1,
    "workload_calculation_method":  "Credit Hours",
    "max_weekly_teaching_hours":    20,
    # Self-service permissions
    "allow_theme_override":         1,
    "allow_density_override":       1,
    "allow_notification_settings":  1,
    "allow_dashboard_customization":1,
    "allow_font_size_override":     1,
    "allow_language_preference":    0,
    # Advanced
    "custom_css": "",
}

# ── Font mappings ─────────────────────────────────────────────────────
_FONT_CSS = {
    "Poppins":        "'Poppins', system-ui, -apple-system, sans-serif",
    "Inter":          "'Inter', system-ui, -apple-system, sans-serif",
    "Roboto":         "'Roboto', system-ui, -apple-system, sans-serif",
    "Merriweather":   "'Merriweather', Georgia, serif",
    "System Default": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
}

_FONT_GOOGLE_URL = {
    "Inter":        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap",
    "Roboto":       "https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap",
    "Merriweather": "https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700;900&display=swap",
}

_NAV_HEIGHT = {
    "Compact": "50px",
    "Normal":  "60px",
    "Tall":    "72px",
}

# ── Check fields that need special saved-value handling ───────────────
_CHECK_FIELDS = frozenset({
    "show_logo", "show_faculty_id_sidebar", "show_department_sidebar",
    "show_announcements_ticker", "show_today_schedule", "show_pending_evaluations",
    "show_class_statistics", "show_quick_actions", "show_workload_summary",
    "show_leave_status", "show_student_performance_overview", "show_upcoming_exams",
    "enable_attendance_marking", "enable_bulk_attendance", "show_student_photos_attendance",
    "enable_proxy_attendance_alert",
    "enable_marks_entry", "enable_internal_marks", "show_class_grade_statistics",
    "allow_marks_edit_after_submission", "marks_edit_approval_required", "enable_grade_remarks",
    "enable_assignment_module", "allow_late_submission_marking",
    "assignment_submission_notification", "show_plagiarism_indicator",
    "enable_office_hours", "show_student_contact_info", "enable_student_query_system",
    "enable_leave_request", "show_workload_indicator",
    "allow_theme_override", "allow_density_override", "allow_notification_settings",
    "allow_dashboard_customization", "allow_font_size_override", "allow_language_preference",
})


class FacultyPortalSettings(Document):
    def validate(self):
        self._validate_colors()
        self._validate_thresholds()
        self._validate_integers()
        self._ensure_public_attachments()

    def _ensure_public_attachments(self):
        # portal_logo / portal_favicon are rendered on every faculty-portal page
        # (including for guests before login), so they must not be private —
        # the Attach Image widget defaults to private unless the uploader
        # remembers to tick "Public", so force it here instead of relying on that.
        for fieldname in ("portal_logo", "portal_favicon"):
            file_url = self.get(fieldname)
            if not file_url or not file_url.startswith("/private/files/"):
                continue
            file_doc = frappe.db.get_value(
                "File", {"file_url": file_url}, ["name", "is_private"], as_dict=True
            )
            if not file_doc or not file_doc.is_private:
                continue
            file = frappe.get_doc("File", file_doc.name)
            file.is_private = 0
            file.save(ignore_permissions=True)
            self.set(fieldname, file.file_url)

    def _validate_colors(self):
        color_fields = [
            "primary_color", "secondary_color", "background_color", "card_background",
            "nav_text_color", "sidebar_active_text_color",
            "sidebar_menu_text_color", "sidebar_menu_hover_bg_color", "sidebar_menu_hover_text_color",
            "success_color", "warning_color", "danger_color", "info_color",
            "grade_color", "grade_fail_color",
        ]
        for field in color_fields:
            val = (self.get(field) or "").strip()
            if val and not _is_valid_hex(val):
                label = self.meta.get_field(field).label
                frappe.throw(f"<b>{label}</b> must be a valid hex color (e.g. #1e3a5f or #fff)")

    def _validate_thresholds(self):
        good = float(self.att_good_threshold or 75)
        warn = float(self.att_warn_threshold or 60)
        if not (0 <= good <= 100):
            frappe.throw("Good Attendance Threshold must be between 0 and 100")
        if not (0 <= warn <= 100):
            frappe.throw("Warning Attendance Threshold must be between 0 and 100")
        if warn >= good:
            frappe.throw("Warning Attendance Threshold must be lower than the Good Attendance Threshold")

    def _validate_integers(self):
        int_fields = {
            "auto_close_session_minutes":       (0, 480),
            "allow_attendance_edit_window_days":(0, 30),
            "office_hours_advance_booking_days":(1, 90),
            "max_office_hour_bookings":         (1, 100),
            "max_weekly_teaching_hours":        (1, 80),
        }
        for field, (mn, mx) in int_fields.items():
            val = self.get(field)
            if val is not None and not (mn <= int(val) <= mx):
                label = self.meta.get_field(field).label
                frappe.throw(f"<b>{label}</b> must be between {mn} and {mx}")


# ── Private helpers ───────────────────────────────────────────────────

def _is_valid_hex(color):
    import re
    return bool(re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", color.strip()))


def _hex_to_rgba(hex_color, alpha):
    """#RRGGBB → rgba(r, g, b, alpha)"""
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

def get_faculty_portal_settings():
    """
    Returns a fully-resolved settings dict suitable for Jinja template use.
    All CSS-derived values (rgba, darkened shades, body classes) are pre-computed.
    Falls back to safe defaults when the doctype is missing or not yet configured.
    Merges active Faculty Portal User Preferences for the current session user.
    """
    try:
        doc = frappe.get_single("Faculty Portal Settings")
        saved = frappe.db.get_singles_dict("Faculty Portal Settings")
        raw = {}
        for k, default_val in _DEFAULTS.items():
            v = getattr(doc, k, None)
            if k in _CHECK_FIELDS:
                sv = saved.get(k)
                raw[k] = int(sv) if sv is not None else default_val
            else:
                raw[k] = v if v not in (None, "") else default_val
    except Exception:
        raw = dict(_DEFAULTS)

    # ── Merge per-faculty user preferences (self-service overrides) ───
    _apply_user_preferences(raw)

    # ── Derived primary palette ────────────────────────────────────
    primary = raw["primary_color"]
    raw["primary_dark"]  = _darken_hex(primary, 0.82)
    raw["primary_light"] = _hex_to_rgba(primary, 0.1)
    raw["primary_mid"]   = _hex_to_rgba(primary, 0.2)

    # ── Derived status bg variants ─────────────────────────────────
    for col, alpha in (("success", 0.15), ("warning", 0.15), ("danger", 0.15), ("info", 0.12)):
        raw[f"{col}_bg"] = _hex_to_rgba(raw[f"{col}_color"], alpha)

    # ── Derived grade bg variants ──────────────────────────────────
    for band in ("excellent", "good", "average", "fail"):
        raw[f"grade_{band}_bg"] = _hex_to_rgba(raw[f"grade_{band}_color"], 0.15)

    # ── Nav text color as rgba (for hover states) ──────────────────
    raw["nav_text_rgba_80"] = _hex_to_rgba(raw["nav_text_color"], 0.8)

    # ── Font family CSS value + optional Google Fonts URL ──────────
    raw["font_family_css"] = _FONT_CSS.get(raw["font_family"], _FONT_CSS["Poppins"])
    raw["font_google_url"] = _FONT_GOOGLE_URL.get(raw["font_family"], "")

    # ── Nav height CSS value ───────────────────────────────────────
    raw["nav_height_css"] = _NAV_HEIGHT.get(raw["nav_height"], "60px")

    # ── Attendance thresholds as floats ────────────────────────────
    raw["att_good_threshold"] = float(raw["att_good_threshold"] or 75)
    raw["att_warn_threshold"] = float(raw["att_warn_threshold"] or 60)

    # ── Body CSS classes ───────────────────────────────────────────
    body_classes = []

    if raw["font_size"] == "Small":
        body_classes.append("fp-font-sm")
    elif raw["font_size"] == "Large":
        body_classes.append("fp-font-lg")

    if raw["layout_density"] == "Compact":
        body_classes.append("fp-compact")

    if raw["corner_style"] == "Sharp":
        body_classes.append("fp-corners-sharp")
    elif raw["corner_style"] == "Pill":
        body_classes.append("fp-corners-pill")

    if raw["sidebar_width"] == "Narrow":
        body_classes.append("fp-sidebar-narrow")
    elif raw["sidebar_width"] == "Wide":
        body_classes.append("fp-sidebar-wide")

    if raw["sidebar_position"] == "Right":
        body_classes.append("fp-right-sidebar")

    if raw["sidebar_theme"] == "Dark":
        body_classes.append("fp-sidebar-dark")

    if raw["nav_height"] == "Compact":
        body_classes.append("fp-nav-compact")
    elif raw["nav_height"] == "Tall":
        body_classes.append("fp-nav-tall")

    raw["body_classes"] = " ".join(body_classes)

    return raw


def _apply_user_preferences(raw):
    """Overlay per-user preferences onto the global settings where the admin allows it."""
    user = frappe.session.user
    if not user or user in ("Administrator", "Guest"):
        return

    try:
        prefs = frappe.get_doc("Faculty Portal User Preferences", user)
    except frappe.DoesNotExistError:
        return
    except Exception:
        return

    if raw.get("allow_theme_override") and prefs.primary_color_override:
        if _is_valid_hex(prefs.primary_color_override):
            raw["primary_color"] = prefs.primary_color_override

    if raw.get("allow_font_size_override") and prefs.font_size_pref:
        raw["font_size"] = prefs.font_size_pref

    if raw.get("allow_density_override") and prefs.layout_density_pref:
        raw["layout_density"] = prefs.layout_density_pref

    if raw.get("allow_dashboard_customization"):
        for field in (
            "show_today_schedule", "show_pending_evaluations", "show_class_statistics",
            "show_workload_summary", "show_leave_status",
        ):
            hide_field = "hide_" + field[5:]  # strip "show_" → "hide_"
            if getattr(prefs, hide_field, None):
                raw[field] = 0
