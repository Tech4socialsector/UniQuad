"""Which roles may open each Uniquad portal.

Set on Roles & Permissions (uniquad-roles-permissions) > Portals and kept in the
global default below; until a portal is changed there it allows DEFAULT_ROLES.
`guard` runs in before_request after auth_routing.intercept_login, which has
already sent guests to the portal login, so it only sees signed-in users.
The portals' own checks (a Faculty / Student Master record) still apply.
"""

import json

import frappe
from frappe import _

PORTALS = (
	{"key": "student", "label": "Student Portal", "route": "/student-portal", "default_roles": ["slcm_Student", "Student"]},
	{"key": "faculty", "label": "Faculty Portal", "route": "/faculty-portal", "default_roles": ["slcm_Faculty"]},
	{"key": "parent", "label": "Parent Portal", "route": "/parent-portal", "default_roles": ["slcm_parent"]},
)
SETTINGS_KEY = "uniquad_portal_roles"


def _saved():
	try:
		return json.loads(frappe.db.get_global(SETTINGS_KEY) or "{}")
	except ValueError:
		return {}


def get_portal_roles():
	"""{portal key: [roles]}"""
	saved = _saved()
	return {p["key"]: saved.get(p["key"], p["default_roles"]) for p in PORTALS}


def set_portal_roles(key, roles):
	saved = _saved()
	saved[key] = sorted(set(roles))
	frappe.db.set_global(SETTINGS_KEY, json.dumps(saved))


def guard():
	user = frappe.session.user
	if user in ("Guest", "Administrator"):
		return
	try:
		path = frappe.local.request.path
	except Exception:
		return
	portal = next(
		(p for p in PORTALS if path == p["route"] or path.startswith(p["route"] + "/")),
		None,
	)
	if not portal:
		return
	allowed = set(get_portal_roles()[portal["key"]])
	if not allowed & set(frappe.get_roles(user)):
		frappe.throw(
			_("Your account does not have access to the {0}. Please contact the Registrar's office.").format(_(portal["label"])),
			frappe.PermissionError,
			title=_("Not Permitted"),
		)
