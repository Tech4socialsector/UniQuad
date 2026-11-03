"""Desktop icon visibility for the Academics desktop and the AAD roles.

Two gaps in Frappe's own Desktop Icon role check:

1. An icon with no roles is shown to anyone who can open something in its
   sidebar, so AAD / AAD Staff (who read Course, Time Table, ...) also get
   Faculty Management, Fees & Payments, Tools and the ERPNext workspaces. For
   AAD users (unless also System Manager) only icons granted to one of their
   roles are kept — filtered from the boot, which feeds both the desktop and
   the awesomebar.
2. A saved Desktop Layout replaces the boot icons, so the role check is
   bypassed for anyone who has ever arranged their desktop: users who lose
   access keep the icons, and users who gain access never get them. Layouts
   are brought in line whenever a User is saved, and once for everyone from a
   patch.
"""

import json

import frappe
from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache
from frappe.permissions import AUTOMATIC_ROLES

from slcm.permissions import AAD_ROLES

ROOT = "Academics"
FIELDS = ("label", "link_to", "link_type", "icon", "icon_type", "parent_icon", "bg_color", "hidden", "app", "standard")
UNRESTRICTED_ROLES = {"System Manager", "Administrator"}


def is_desktop_restricted(roles):
	return bool(set(roles) & AAD_ROLES) and not set(roles) & UNRESTRICTED_ROLES


def granted_icons(roles):
	"""Icons explicitly granted to one of `roles`, plus role-less icons inside
	a granted folder (they follow their parent)."""
	roles = set(roles) - set(AUTOMATIC_ROLES)
	icon_roles = {}
	for r in frappe.get_all("Has Role", filters={"parenttype": "Desktop Icon"}, fields=["parent", "role"]):
		icon_roles.setdefault(r.parent, set()).add(r.role)
	granted = {name for name, rs in icon_roles.items() if rs & roles}
	return granted | {
		d.name
		for d in frappe.get_all("Desktop Icon", filters={"parent_icon": ["in", list(granted) or [""]]}, fields=["name"])
		if not icon_roles.get(d.name)
	}


def filter_boot_icons(bootinfo):
	"""boot_session hook."""
	roles = frappe.get_roles()
	if not bootinfo.get("desktop_icons") or not is_desktop_restricted(roles):
		return
	allowed = granted_icons(roles)
	bootinfo.desktop_icons = [i for i in bootinfo.desktop_icons if i.get("name") in allowed]


def sync_user_layout(doc, method=None):
	"""User on_update — roles may have changed."""
	sync_layout(doc.name)


def sync_all_layouts():
	if not frappe.db.table_exists("Desktop Layout"):
		return
	for user in frappe.get_all("Desktop Layout", pluck="name"):
		sync_layout(user)


def sync_layout(user):
	if not frappe.db.table_exists("Desktop Layout") or not frappe.db.exists("Desktop Layout", user):
		return
	try:
		entries = json.loads(frappe.db.get_value("Desktop Layout", user, "layout") or "[]")
	except ValueError:
		return
	if not isinstance(entries, list):
		return

	icons = {
		d.name: d
		for d in frappe.get_all(
			"Desktop Icon",
			or_filters=[["name", "=", ROOT], ["parent_icon", "=", ROOT]],
			fields=["name", *FIELDS],
		)
	}
	if ROOT not in icons:
		return

	icon_roles = {}
	for r in frappe.get_all(
		"Has Role", filters={"parenttype": "Desktop Icon", "parent": ["in", list(icons)]}, fields=["parent", "role"]
	):
		icon_roles.setdefault(r.parent, set()).add(r.role)

	user_roles = set(frappe.get_roles(user))
	allowed = {
		name
		for name in icons
		if user == "Administrator" or not icon_roles.get(name) or icon_roles[name] & user_roles
	}
	if ROOT not in allowed:
		allowed = set()

	if is_desktop_restricted(user_roles):
		granted = granted_icons(user_roles)
		keep = lambda name: name in granted  # noqa: E731
	else:
		keep = lambda name: name not in icons or name in allowed  # noqa: E731

	new = [_strip(e, keep) for e in entries if isinstance(e, dict) and keep(e.get("name"))]
	present = _names(new)
	if ROOT in allowed:
		new += [
			dict(name=n, idx=0, **{f: icons[n].get(f) for f in FIELDS})
			for n in [ROOT, *sorted(allowed - {ROOT})]
			if n not in present and not icons[n].hidden
		]

	if new != entries:
		frappe.db.set_value("Desktop Layout", user, "layout", json.dumps(new), update_modified=False)
		clear_desktop_icons_cache(user)


def _strip(entry, keep):
	if isinstance(entry.get("child_icons"), list):
		entry["child_icons"] = [
			_strip(c, keep) for c in entry["child_icons"] if isinstance(c, dict) and keep(c.get("name"))
		]
	return entry


def _names(entries):
	names = set()
	for e in entries:
		names.add(e.get("name"))
		names |= _names(e.get("child_icons") or [])
	return names
