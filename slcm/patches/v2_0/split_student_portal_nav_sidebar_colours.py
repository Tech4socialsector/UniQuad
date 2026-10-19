"""Student Portal Settings: split the single "Navbar & Sidebar" colour pair into
separate Navbar and Sidebar colours (as in Parent Portal Settings).

Copies the old `sidebar_theme` background into `nav_bg_color` / `sidebar_bg_color`
and the old `nav_text_color` into `sidebar_text_color`, keeping the portal's look.
Invalid values (e.g. "Light"/"Dark" written by old theme presets) fall back to the
NLSIU defaults.
"""

import re

import frappe

DT = "Student Portal Settings"
HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _hex(value, fallback):
	value = (value or "").strip()
	return value if HEX.match(value) else fallback


def execute():
	if not frappe.db.exists("DocType", DT):
		return
	saved = frappe.db.get_singles_dict(DT)

	legacy_bg = _hex(saved.get("sidebar_theme"), "#ffffff")
	text = _hex(saved.get("nav_text_color"), "#920c24")

	values = {
		"nav_bg_color": _hex(saved.get("nav_bg_color"), legacy_bg),
		"sidebar_bg_color": _hex(saved.get("sidebar_bg_color"), legacy_bg),
		"nav_text_color": text,
		"sidebar_text_color": _hex(saved.get("sidebar_text_color"), text),
	}
	for field, value in values.items():
		frappe.db.set_single_value(DT, field, value, update_modified=False)

	frappe.clear_document_cache(DT, DT)
