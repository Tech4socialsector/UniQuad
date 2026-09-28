"""Student Portal Settings: use the Parent Portal colours.

NLSIU maroon primary, gold accent, slate sidebar menu text, #008000 for
success and maroon for alerts. Only values that are still at an old default
are replaced, so admin customisations survive.
"""

import frappe

DT = "Student Portal Settings"

# field: (value to set, stored values that may be replaced)
_THEME = {
	"primary_color":      ("#920c24", ("#2b2e4a", "")),
	"secondary_color":    ("#c9a84c", ("#920c24", "#85142b", "#ed0505", "#2b2e4a", "")),
	"sidebar_text_color": ("#475569", ("#920c24", "#2b2e4a", "")),
	"success_color":      ("#008000", ("#16a34a", "#15803d", "")),
	"danger_color":       ("#920c24", ("#dc2626", "")),
	# No orange anywhere — warnings and the average grade band use NLS maroon
	"warning_color":       ("#920c24", ("#d97706", "")),
	"grade_average_color": ("#920c24", ("#d97706", "")),
	"grade_fail_color":    ("#920c24", ("#dc2626", "#85142b", "")),
}


def execute():
	if not frappe.db.exists("DocType", DT):
		return
	saved = frappe.db.get_singles_dict(DT)

	changed = False
	for field, (value, replaceable) in _THEME.items():
		if (saved.get(field) or "").strip().lower() in replaceable:
			frappe.db.set_single_value(DT, field, value, update_modified=False)
			changed = True

	if changed:
		frappe.clear_document_cache(DT, DT)
