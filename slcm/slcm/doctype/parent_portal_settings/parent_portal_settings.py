# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# ── Defaults ─────────────────────────────────────────────────────────
_DEFAULTS = {
    # Branding
    "portal_title":          "Parent Portal",
    "portal_subtitle":       "",
    "show_logo":             1,
    "nav_brand_text":        "",
    "portal_logo":           "",
    "portal_favicon":        "",
    # Typography
    "font_family":           "Inter",
    "font_size":             "Normal",
    # Theme
    "primary_color":         "#920c24",
    "secondary_color":       "#c9a84c",
    "background_color":      "#f0f2f5",
    "card_background":       "#ffffff",
    "nav_text_color":        "#ffffff",
    "sidebar_bg_color":      "#ffffff",
    "sidebar_text_color":    "#475569",
    # Status colors
    "success_color":         "#008000",
    "warning_color":         "#d97706",
    "danger_color":          "#920c24",
    "info_color":            "#0369a1",
    # Grading
    "grade_excellent_color": "#16a34a",
    "grade_excellent_label": "A+ / A / S",
    "grade_good_color":      "#0369a1",
    "grade_good_label":      "B+ / B",
    "grade_average_color":   "#d97706",
    "grade_average_label":   "C+ / C",
    "grade_color":           "#000000",
    "grade_fail_color":      "#dc2626",
    "grade_fail_label":      "D / F",
    # Attendance thresholds
    "att_good_threshold":    75,
    "att_warn_threshold":    60,
    "att_label_good":        "Good",
    "att_label_warn":        "Low",
    "att_label_danger":      "Critical",
    # Layout
    "sidebar_width":         "Normal",
    "nav_height":            "Normal",
    "corner_style":          "Normal",
    "layout_density":        "Normal",
    # Features
    "show_fee_summary":          1,
    "show_attendance_overview":  1,
    "show_latest_result":        1,
    # Menu Visibility
    "show_menu_dashboard":       1,
    "show_menu_attendance":      1,
    "show_menu_results":         1,
    "show_menu_fees":            1,
    # Advanced
    "custom_css":            "",
}

# ── Font mappings ─────────────────────────────────────────────────────
_FONT_CSS = {
    "Inter":          "'Inter', system-ui, -apple-system, sans-serif",
    "Poppins":        "'Poppins', system-ui, -apple-system, sans-serif",
    "Roboto":         "'Roboto', system-ui, -apple-system, sans-serif",
    "Merriweather":   "'Merriweather', Georgia, 'Times New Roman', serif",
    "System Default": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
}

_FONT_GOOGLE_URL = {
    "Poppins":      "https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800&display=swap",
    "Roboto":       "https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap",
    "Merriweather": "https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700;900&display=swap",
}

# ── Nav height mappings ───────────────────────────────────────────────
_NAV_HEIGHT = {
    "Compact": "50px",
    "Normal":  "62px",
    "Tall":    "74px",
}

# ── Sidebar width mappings ────────────────────────────────────────────
_SIDEBAR_WIDTH = {
    "Narrow": "200px",
    "Normal": "256px",
    "Wide":   "300px",
}

# ── Corner radius mappings ────────────────────────────────────────────
_CORNER_RADIUS = {
    "Sharp":  "6px",
    "Normal": "16px",
    "Pill":   "24px",
}


class ParentPortalSettings(Document):
    def validate(self):
        self._validate_colors()
        self._validate_thresholds()

    def _validate_colors(self):
        color_fields = [
            "primary_color", "secondary_color", "background_color", "card_background",
            "nav_text_color", "sidebar_bg_color", "sidebar_text_color",
            "success_color", "warning_color", "danger_color", "info_color",
            "grade_excellent_color", "grade_good_color", "grade_average_color",
            "grade_color", "grade_fail_color",
        ]
        for field in color_fields:
            val = (self.get(field) or "").strip()
            if val and not _is_valid_hex(val):
                label = self.meta.get_field(field).label
                frappe.throw(f"<b>{label}</b> must be a valid hex color (e.g. #e11d48 or #fff)")

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

@frappe.whitelist()
def get_default_settings():
    """Factory defaults for the settings form's "Reset to Defaults" action."""
    frappe.only_for(("System Manager",))
    return dict(_DEFAULTS)


def get_parent_portal_settings():
    """
    Returns a fully-resolved settings dict suitable for Jinja template use.
    All CSS-derived values (rgba, darkened shades, body classes) are pre-computed.
    Falls back to safe defaults when the doctype is missing or not yet configured.
    """
    _check_fields = (
        "show_logo", "show_fee_summary", "show_attendance_overview", "show_latest_result",
        "show_menu_dashboard", "show_menu_attendance", "show_menu_results", "show_menu_fees",
    )

    try:
        doc = frappe.get_single("Parent Portal Settings")
        raw = {}
        for k, default_val in _DEFAULTS.items():
            v = getattr(doc, k, None)
            if k in _check_fields:
                raw[k] = int(v) if v is not None else default_val
            else:
                raw[k] = v if v not in (None, "") else default_val
    except Exception:
        raw = dict(_DEFAULTS)

    # A stored colour that isn't valid hex (e.g. saved before validation
    # existed) must not break every portal page — use the default instead.
    for k, default_val in _DEFAULTS.items():
        if k.endswith("_color") and not _is_valid_hex(str(raw.get(k) or "")):
            raw[k] = default_val

    # ── Derived primary palette ───────────────────────────────────
    primary = raw["primary_color"]
    raw["primary_dark"]  = _darken_hex(primary, 0.82)
    raw["primary_light"] = _hex_to_rgba(primary, 0.08)
    raw["primary_mid"]   = _hex_to_rgba(primary, 0.18)

    # ── Derived status bg variants ────────────────────────────────
    for col, alpha in (("success", 0.15), ("warning", 0.15), ("danger", 0.15), ("info", 0.12)):
        raw[f"{col}_bg"] = _hex_to_rgba(raw[f"{col}_color"], alpha)

    # ── Derived grade bg variants ─────────────────────────────────
    for band in ("excellent", "good", "average", "fail"):
        raw[f"grade_{band}_bg"] = _hex_to_rgba(raw[f"grade_{band}_color"], 0.15)

    # ── Font family CSS value + optional Google Fonts URL ─────────
    raw["font_family_css"] = _FONT_CSS.get(raw["font_family"], _FONT_CSS["Inter"])
    raw["font_google_url"] = _FONT_GOOGLE_URL.get(raw["font_family"], "")

    # ── Nav + sidebar CSS values ──────────────────────────────────
    raw["nav_height_css"]    = _NAV_HEIGHT.get(raw["nav_height"], "62px")
    raw["sidebar_width_css"] = _SIDEBAR_WIDTH.get(raw["sidebar_width"], "256px")
    raw["corner_radius_css"] = _CORNER_RADIUS.get(raw["corner_style"], "16px")

    # ── Attendance thresholds as floats ───────────────────────────
    raw["att_good_threshold"] = float(raw["att_good_threshold"] or 75)
    raw["att_warn_threshold"] = float(raw["att_warn_threshold"] or 60)

    # ── Body CSS classes ──────────────────────────────────────────
    body_classes = []

    if raw["font_size"] == "Small":
        body_classes.append("pp-font-sm")
    elif raw["font_size"] == "Large":
        body_classes.append("pp-font-lg")

    if raw["layout_density"] == "Compact":
        body_classes.append("pp-compact")

    if raw["corner_style"] == "Sharp":
        body_classes.append("pp-corners-sharp")
    elif raw["corner_style"] == "Pill":
        body_classes.append("pp-corners-pill")

    if raw["sidebar_width"] == "Narrow":
        body_classes.append("pp-sidebar-narrow")
    elif raw["sidebar_width"] == "Wide":
        body_classes.append("pp-sidebar-wide")

    if raw["nav_height"] == "Compact":
        body_classes.append("pp-nav-compact")
    elif raw["nav_height"] == "Tall":
        body_classes.append("pp-nav-tall")

    raw["body_classes"] = " ".join(body_classes)

    return raw
