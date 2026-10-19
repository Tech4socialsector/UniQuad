import frappe


# field: (value to set, stored values that may be replaced)
_THEME = {
    "primary_color":      ("#920c24", ("#2b2e4a", "#e11d48", "")),
    "secondary_color":    ("#c9a84c", ("#920c24", "#c8a14b", "#2b2e4a", "")),
    "sidebar_bg_color":   ("#ffffff", ("#2b2e4a", "")),
    "sidebar_text_color": ("#475569", ("#e8e9f0", "#374151", "")),
    "background_color":   ("#f0f2f5", ("#f3f6f5", "")),
    "success_color":      ("#008000", ("#16a34a", "")),
    "danger_color":       ("#920c24", ("#dc2626", "")),
}


def execute():
    """
    Give the Parent Portal the same look as the Faculty Portal: NLSIU maroon
    primary, gold accent, light sidebar with slate menu text and
    #008000 for success (green) text, NLSIU maroon for alerts/errors. Only values that
    are still at an old default are replaced, so admin customisations survive.
    """
    if not frappe.db.exists("Parent Portal Settings", "Parent Portal Settings"):
        return

    doc = frappe.get_single("Parent Portal Settings")

    changed = False
    for field, (value, replaceable) in _THEME.items():
        if (doc.get(field) or "").strip().lower() in replaceable:
            doc.set(field, value)
            changed = True

    if changed:
        doc.save(ignore_permissions=True)
        frappe.db.commit()
