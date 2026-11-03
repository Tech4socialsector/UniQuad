"""Bring users' saved Desktop Layouts in line with the Desktop Icons.

A layout keeps a copy of every icon as it was when the user last arranged the
desktop. Icons removed since (Exam Planner, Exam Result after the Examinations
merge) then show as "Icon is not correctly configured", icons added since
(Examinations) are missing, and fixed icons keep their old settings.
"""

import json

import frappe

FIELDS = ("label", "link_to", "link_type", "icon", "icon_type", "parent_icon", "bg_color", "hidden", "app", "standard")


def execute():
	if not frappe.db.table_exists("Desktop Layout"):
		return
	icons = {d.name: d for d in frappe.get_all("Desktop Icon", fields=["name", *FIELDS])}
	children = {}
	for d in icons.values():
		if d.parent_icon:
			children.setdefault(d.parent_icon, []).append(d.name)

	for name, layout in frappe.get_all("Desktop Layout", fields=["name", "layout"], as_list=True):
		try:
			entries = json.loads(layout or "[]")
		except ValueError:
			continue
		if not isinstance(entries, list):
			continue
		new = [_refresh(e, icons, children) for e in entries if isinstance(e, dict) and e.get("name") in icons]
		# The desktop builds folders from this flat list by parent_icon, so a
		# new icon of a folder already on the desktop must be listed too
		present = {e["name"] for e in new}
		new += [
			dict(name=n, idx=0, **{f: icons[n].get(f) for f in FIELDS})
			for parent in list(present) for n in children.get(parent, [])
			if n not in present and not icons[n].hidden
		]
		if new != entries:
			frappe.db.set_value("Desktop Layout", name, "layout", json.dumps(new), update_modified=False)


def _refresh(entry, icons, children):
	entry.update({f: icons[entry["name"]].get(f) for f in FIELDS})
	if "child_icons" in entry:
		kept = [_refresh(c, icons, children) for c in entry["child_icons"] or [] if c.get("name") in icons]
		have = {c["name"] for c in kept}
		kept += [dict(name=n, **{f: icons[n].get(f) for f in FIELDS}) for n in children.get(entry["name"], []) if n not in have]
		entry["child_icons"] = kept
	return entry
