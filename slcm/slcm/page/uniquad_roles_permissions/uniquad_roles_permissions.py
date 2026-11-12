# Copyright (c) 2026, NLSIU and contributors
# For license information, please see license.txt

"""Uniquad Roles & Permissions (same model as Pathways > Settings > Roles & Permissions).

For each Uniquad role choose:
* Document Types: what it may do on every Uniquad DocType (modules SLCM,
  Admission, PACE), stored as standard Custom DocPerm rows, exactly what
  Desk's Role Permission Manager writes, so both screens always agree;
* Pages & Reports: stored as Custom Role, Frappe's own override of a
  standard Page's / Report's roles (what "Role Permission for Page and
  Report" writes), so the shipped files stay untouched;
* Desktop Icons: the icon's own roles table (saving it in developer mode
  also writes the app's desktop_icon/*.json, as Desk does);
* Portals: which roles may open the student / faculty / parent portals
  (slcm.utils.portal_access);
and who holds each role. System Manager only.

Which roles are "Uniquad roles": every role named on any of the above, every
slcm_* role, plus roles added here with New Role (kept in the global default
below until they are granted something).

Pages, reports and icons with no roles are open to everyone (Frappe's rule).
Taking one role off such an item restricts it to all the other Uniquad roles
(plus System Manager), so it never silently closes for everyone.
"""

import json

import frappe
from frappe import _
from frappe.permissions import reset_perms, setup_custom_perms
from frappe.utils import cint, validate_email_address

from slcm.utils.portal_access import PORTALS, get_portal_roles, set_portal_roles

MANAGER_ROLE = "System Manager"
MODULES = ("SLCM", "Admission", "PACE")
PTYPES = ("read", "write", "create", "delete", "submit", "cancel", "amend")
SUBMIT_PTYPES = ("submit", "cancel", "amend")
# Turning a permission on turns on what it needs; turning one off turns off
# what depends on it (mirrors Frappe's own validation rules).
REQUIRES = {
	"write": ("read",),
	"create": ("read",),
	"delete": ("read",),
	"submit": ("write",),
	"cancel": ("submit",),
	"amend": ("cancel",),
}
PROTECTED_ROLES = {"Administrator", "Guest", "All", "Desk User", MANAGER_ROLE}
# Portal roles: students, parents and applicants only ever reach their own
# records through the portals, and those pages rely on these exact grants.
PORTAL_ROLES = {"slcm_Student", "slcm_parent", "Student", "Applicant", "PACE Applicant"}
EXTRA_ROLES_KEY = "uniquad_access_extra_roles"
UNIQUAD_APP = "slcm"


def _only_manager():
	frappe.only_for(MANAGER_ROLE)


def _canon():
	"""{lower-case name: Role name}. Role names compare case-insensitively in
	MariaDB, and some permission rows spell them differently (slcm_faculty)."""
	return {name.lower(): name for name in frappe.get_all("Role", pluck="name")}


def _canonical(roles, canon=None):
	canon = canon or _canon()
	return [canon.get((r or "").lower(), r) for r in roles if r]


# ------------------------------------------------------------- doctypes


def _uniquad_doctypes():
	return frappe.get_all(
		"DocType",
		filters={"module": ["in", MODULES], "istable": 0},
		fields=["name", "module", "is_submittable", "issingle"],
		order_by="name asc",
	)


def _assert_doctype(doctype):
	if not frappe.db.exists("DocType", {"name": doctype, "module": ["in", MODULES], "istable": 0}):
		frappe.throw(_("{0} is not a Uniquad document type.").format(doctype))


def _perm_rows(doctypes, canon=None):
	"""{doctype: {role: {ptype: 0/1}}} of the level-0 rows in force: Custom
	DocPerm if the DocType has any, else the standard DocPerm."""
	if not doctypes:
		return {}, set()
	canon = canon or _canon()
	fields = ", ".join(f"`{p}`" for p in PTYPES)
	customised = set(
		frappe.db.sql_list("select distinct parent from `tabCustom DocPerm` where parent in %(d)s", {"d": doctypes})
	)
	rows = frappe.db.sql(
		f"""select parent, role, {fields} from `tabCustom DocPerm`
			where parent in %(c)s and permlevel = 0
		union all
		select parent, role, {fields} from `tabDocPerm`
			where parenttype = 'DocType' and parent in %(d)s and parent not in %(c)s and permlevel = 0""",
		{"d": doctypes, "c": list(customised) or [""]},
		as_dict=True,
	)
	out = {}
	for row in rows:
		role = canon.get(row.role.lower(), row.role)
		entry = out.setdefault(row.parent, {}).setdefault(role, {p: 0 for p in PTYPES})
		for p in PTYPES:
			entry[p] = entry[p] or cint(row[p])
	return out, customised


# ---------------------------------------------------- pages and reports


def _has_roles(parenttype, names, canon):
	out = {}
	if not names:
		return out
	for row in frappe.get_all(
		"Has Role", filters={"parenttype": parenttype, "parent": ["in", names]}, fields=["parent", "role"]
	):
		out.setdefault(row.parent, [])
		role = canon.get(row.role.lower(), row.role)
		if role not in out[row.parent]:
			out[row.parent].append(role)
	return out


def _pages(canon):
	"""Uniquad Pages and Reports with the roles in force for each."""
	pages = frappe.get_all("Page", filters={"module": ["in", MODULES]}, fields=["name", "title", "module"])
	reports = frappe.get_all(
		"Report",
		filters={"module": ["in", MODULES], "disabled": 0},
		fields=["name", "ref_doctype", "report_type", "module"],
	)
	custom = frappe.get_all(
		"Custom Role",
		filters=[["page", "in", [p.name for p in pages] or [""]]],
		fields=["name", "page"],
	) + frappe.get_all(
		"Custom Role",
		filters=[["report", "in", [r.name for r in reports] or [""]]],
		fields=["name", "report"],
	)
	custom_of = {("Page", c.page) if c.get("page") else ("Report", c.report): c.name for c in custom}
	custom_roles = _has_roles("Custom Role", [c.name for c in custom], canon)
	std_roles = {
		"Page": _has_roles("Page", [p.name for p in pages], canon),
		"Report": _has_roles("Report", [r.name for r in reports], canon),
	}

	out = []
	for kind, rows in (("Page", pages), ("Report", reports)):
		for row in rows:
			custom_name = custom_of.get((kind, row.name))
			roles = custom_roles.get(custom_name, []) if custom_name else std_roles[kind].get(row.name, [])
			out.append(
				{
					"kind": kind,
					"name": row.name,
					"title": (row.get("title") or row.name) if kind == "Page" else row.name,
					"module": row.module,
					"detail": row.get("ref_doctype") or "",
					"report_type": row.get("report_type") or "",
					"roles": roles,
					"customised": bool(custom_name),
				}
			)
	out.sort(key=lambda p: (p["kind"] != "Page", p["title"].lower()))
	return out


def _assert_page(kind, name):
	if kind not in ("Page", "Report") or not frappe.db.exists(kind, {"name": name, "module": ["in", MODULES]}):
		frappe.throw(_("{0} is not a Uniquad page or report.").format(name))


# ------------------------------------------------------------ desktop icons


def _icons(canon):
	"""Uniquad desktop icons, each app folder followed by the icons inside it."""
	# What everyone's desk loads: standard icons and Administrator's own
	# (frappe.desk.doctype.desktop_icon.desktop_icon.get_desktop_icons).
	rows = frappe.get_all(
		"Desktop Icon",
		or_filters={"standard": 1, "owner": "Administrator"},
		fields=["name", "label", "icon_type", "app", "parent_icon", "link_type", "link_to", "hidden", "idx"],
		order_by="idx asc",
	)
	folders = {r.name for r in rows if r.app == UNIQUAD_APP and not r.parent_icon}
	mine = [r for r in rows if r.app == UNIQUAD_APP or r.parent_icon in folders]
	roles = _has_roles("Desktop Icon", [r.name for r in mine], canon)
	tops = [r for r in mine if not r.parent_icon or r.parent_icon not in folders]
	ordered = []
	for top in tops:
		ordered.append(top)
		ordered.extend(r for r in mine if r.parent_icon == top.name)
	return [
		{
			"name": r.name,
			"label": r.label,
			"icon_type": r.icon_type,
			"parent": r.parent_icon if r.parent_icon in folders else None,
			"sidebar": r.link_to if r.link_type == "Workspace Sidebar" else None,
			"hidden": cint(r.hidden),
			"external": r.app != UNIQUAD_APP,
			"roles": roles.get(r.name, []),
		}
		for r in ordered
	]


def _assert_icon(name):
	icon = frappe.db.get_value("Desktop Icon", name, ["app", "parent_icon"], as_dict=True)
	parent_app = icon and icon.parent_icon and frappe.db.get_value("Desktop Icon", icon.parent_icon, "app")
	if not icon or UNIQUAD_APP not in (icon.app, parent_app):
		frappe.throw(_("{0} is not a Uniquad desktop icon.").format(name))


def _clear_access_caches():
	"""Pages/reports per user ("has_role:Page"), desktop icons and boot info."""
	frappe.cache.delete_keys("user:*:has_role:")
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")


def _toggle_roles(current, role, value):
	"""New role list for an item after ticking / unticking `role`. An item
	with no roles is open to everyone: unticking restricts it to every other
	Uniquad role, and System Manager always keeps a restricted item."""
	current = list(current)
	if value:
		if not current or role in current:
			return current
		return current + [role]
	if not current:
		current = sorted(_uniquad_roles())
	roles = [r for r in current if r != role]
	if MANAGER_ROLE not in roles:
		roles.append(MANAGER_ROLE)
	return roles


# ------------------------------------------------------------------ roles


def _extra_roles():
	try:
		return set(json.loads(frappe.db.get_global(EXTRA_ROLES_KEY) or "[]"))
	except ValueError:
		return set()


def _set_extra_roles(roles):
	frappe.db.set_global(EXTRA_ROLES_KEY, json.dumps(sorted(roles)))


def _role_usage(canon=None):
	"""{role: number of document types, pages/reports, icons and portals it
	is named on}, plus the lists themselves for the matrix."""
	canon = canon or _canon()
	doctypes = _uniquad_doctypes()
	perms, customised = _perm_rows([d.name for d in doctypes], canon)
	pages = _pages(canon)
	icons = _icons(canon)
	portal_roles = {k: _canonical(v, canon) for k, v in get_portal_roles().items()}
	usage = {}
	for by_role in perms.values():
		for role, p in by_role.items():
			if any(p.values()):
				usage[role] = usage.get(role, 0) + 1
	for item in pages + icons:
		for role in item["roles"]:
			usage[role] = usage.get(role, 0) + 1
	for roles in portal_roles.values():
		for role in roles:
			usage[role] = usage.get(role, 0) + 1
	return usage, doctypes, perms, customised, pages, icons, portal_roles


def _uniquad_roles(usage=None):
	canon = _canon()
	if usage is None:
		usage = _role_usage(canon)[0]
	roles = set(usage)
	roles |= {name for name in canon.values() if name.startswith("slcm_")}
	roles |= set(_canonical(_extra_roles(), canon))
	return {r for r in roles if r.lower() in canon} - PROTECTED_ROLES


def _assert_role(role):
	if role not in _uniquad_roles():
		frappe.throw(_("{0} is not a Uniquad role.").format(role))


def _assert_editable_role(role):
	_assert_role(role)
	if role in PORTAL_ROLES:
		frappe.throw(_("{0} is a portal role; its permissions are fixed because the portals rely on them.").format(role))


def _user_counts(roles):
	if not roles:
		return {}
	rows = frappe.db.sql(
		"""select hr.role, count(distinct hr.parent)
		from `tabHas Role` hr join `tabUser` u on u.name = hr.parent
		where hr.parenttype = 'User' and u.enabled = 1
			and u.name not in ('Administrator', 'Guest') and hr.role in %(roles)s
		group by hr.role""",
		{"roles": list(roles)},
	)
	return dict(rows)


def _menus():
	"""{doctype: [sidebar names]} from the Uniquad workspace sidebars. Desk
	shows a sidebar link only to users who can read its DocType."""
	rows = frappe.db.sql(
		"""select i.link_to, s.name from `tabWorkspace Sidebar Item` i
		join `tabWorkspace Sidebar` s on s.name = i.parent
		where i.parenttype = 'Workspace Sidebar' and i.link_type = 'DocType'
			and s.module in %(m)s and ifnull(i.link_to, '') != ''""",
		{"m": MODULES},
	)
	out = {}
	for doctype, sidebar in rows:
		if sidebar not in out.setdefault(doctype, []):
			out[doctype].append(sidebar)
	return out


@frappe.whitelist()
def get_access_matrix():
	_only_manager()
	canon = _canon()
	usage, doctypes, perms, customised, pages, icons, portal_roles = _role_usage(canon)
	roles = sorted(_uniquad_roles(usage), key=str.lower)
	counts = _user_counts(roles)
	role_meta = {
		r.name: r for r in frappe.get_all("Role", filters={"name": ["in", roles or [""]]}, fields=["name", "desk_access", "disabled"])
	}
	menus = _menus()
	scoped = set(frappe.get_hooks("permission_query_conditions") or {}) | set(frappe.get_hooks("has_permission") or {})

	matrix = {role: {} for role in roles}
	for dt, by_role in perms.items():
		for role, p in by_role.items():
			if role in matrix and any(p.values()):
				matrix[role][dt] = p

	return {
		"roles": [
			{
				"role": role,
				"users": counts.get(role, 0),
				"editable": role not in PORTAL_ROLES,
				"desk_access": cint(role_meta.get(role, {}).get("desk_access")),
				"disabled": cint(role_meta.get(role, {}).get("disabled")),
				"grants": usage.get(role, 0),
			}
			for role in roles
		],
		"doctypes": [
			{
				"name": dt.name,
				"module": dt.module,
				"is_submittable": cint(dt.is_submittable),
				"is_single": cint(dt.issingle),
				"menus": menus.get(dt.name, []),
				"customised": dt.name in customised,
				"row_scoped": dt.name in scoped,
			}
			for dt in doctypes
		],
		"pages": pages,
		"icons": icons,
		"portals": [
			{
				"key": p["key"],
				"label": p["label"],
				"route": p["route"],
				"roles": portal_roles[p["key"]],
				"customised": sorted(portal_roles[p["key"]]) != sorted(p["default_roles"]),
			}
			for p in PORTALS
		],
		"modules": list(MODULES),
		"ptypes": list(PTYPES),
		"matrix": matrix,
	}


def _resolve(current, ptype, value, allowed):
	"""Apply one toggle plus its dependencies to a {ptype: 0/1} dict."""
	perms = {p: cint(current.get(p)) for p in PTYPES}
	stack = [ptype]
	if value:
		while stack:
			p = stack.pop()
			if p in allowed:
				perms[p] = 1
				stack.extend(REQUIRES.get(p, ()))
	else:
		while stack:
			p = stack.pop()
			perms[p] = 0
			stack.extend(child for child, needs in REQUIRES.items() if p in needs and perms[child])
	for p in PTYPES:
		if p not in allowed:
			perms[p] = 0
	return perms


@frappe.whitelist(methods=["POST"])
def set_role_permission(doctype, role, ptype, value):
	"""Toggle one permission for a role on a DocType (with dependencies)."""
	_only_manager()
	_assert_doctype(doctype)
	_assert_editable_role(role)
	if ptype not in PTYPES:
		frappe.throw(_("Unknown permission type {0}.").format(ptype))

	meta = frappe.get_meta(doctype)
	allowed = set(PTYPES)
	if not meta.is_submittable:
		allowed -= set(SUBMIT_PTYPES)
	if meta.issingle:
		allowed -= {"create", "delete"}
	if ptype not in allowed:
		frappe.throw(_("{0} does not support the {1} permission.").format(doctype, _(ptype.title())))

	setup_custom_perms(doctype)
	# A role may have several level-0 rows (e.g. an extra "if owner" row);
	# this screen edits the plain one.
	name = frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}, "name")
	current = frappe.db.get_value("Custom DocPerm", name, list(PTYPES), as_dict=True) if name else {}
	perms = _resolve(current or {}, ptype, cint(value), allowed)

	if not any(perms.values()):
		if name:
			frappe.delete_doc("Custom DocPerm", name, ignore_permissions=True)
	else:
		row = (
			frappe.get_doc("Custom DocPerm", name)
			if name
			else frappe.get_doc(
				{
					"doctype": "Custom DocPerm",
					"parent": doctype,
					"parenttype": "DocType",
					"parentfield": "permissions",
					"role": role,
					"permlevel": 0,
					"if_owner": 0,
				}
			)
		)
		row.update(perms)
		if perms["read"] and not name:
			# Sensible companions for a brand-new grant.
			row.update({"print": 1, "report": 1, "export": 1})
		row.save(ignore_permissions=True)

	frappe.clear_cache(doctype=doctype)
	# The effective row may still grant more (another level-0 row); report what is in force.
	effective, _c = _perm_rows([doctype])
	return {"doctype": doctype, "role": role, "perms": effective.get(doctype, {}).get(role) or perms}


@frappe.whitelist(methods=["POST"])
def reset_doctype_permissions(doctype):
	"""Drop customisations and go back to the permissions shipped with the app."""
	_only_manager()
	_assert_doctype(doctype)
	reset_perms(doctype)
	frappe.clear_cache(doctype=doctype)
	return True


@frappe.whitelist(methods=["POST"])
def set_page_role(kind, name, role, value):
	"""Tick / untick a role on a Page or Report (via its Custom Role)."""
	_only_manager()
	_assert_page(kind, name)
	_assert_editable_role(role)
	field = kind.lower()
	custom_name = frappe.db.get_value("Custom Role", {field: name}, "name")
	if custom_name:
		custom = frappe.get_doc("Custom Role", custom_name)
		current = [r.role for r in custom.roles]
	else:
		current = frappe.get_all("Has Role", filters={"parenttype": kind, "parent": name}, pluck="role")
		custom = frappe.get_doc({"doctype": "Custom Role", field: name})
	roles = _toggle_roles(_canonical(current), role, cint(value))
	custom.set("roles", [{"role": r} for r in roles])
	custom.save(ignore_permissions=True)
	_clear_access_caches()
	return {"roles": roles}


@frappe.whitelist(methods=["POST"])
def reset_page_roles(kind, name):
	"""Back to the roles shipped with the Page / Report."""
	_only_manager()
	_assert_page(kind, name)
	for custom_name in frappe.get_all("Custom Role", filters={kind.lower(): name}, pluck="name"):
		frappe.delete_doc("Custom Role", custom_name, ignore_permissions=True)
	_clear_access_caches()
	return True


@frappe.whitelist(methods=["POST"])
def set_icon_role(icon, role, value):
	"""Tick / untick a role on a Uniquad desktop icon."""
	_only_manager()
	_assert_icon(icon)
	_assert_editable_role(role)
	doc = frappe.get_doc("Desktop Icon", icon)
	roles = _toggle_roles(_canonical([r.role for r in doc.roles]), role, cint(value))
	doc.set("roles", [{"role": r} for r in roles])
	doc.save(ignore_permissions=True)
	_clear_access_caches()
	return {"roles": roles}


@frappe.whitelist(methods=["POST"])
def set_portal_role(portal, role, value):
	"""Allow / stop a role opening a portal. Portal roles (students, parents,
	applicants) can be moved between portals here, unlike their other grants."""
	_only_manager()
	_assert_role(role)
	portal_def = next((p for p in PORTALS if p["key"] == portal), None)
	if not portal_def:
		frappe.throw(_("Unknown portal {0}.").format(portal))
	roles = _canonical(get_portal_roles()[portal])
	roles = [r for r in roles if r != role] + ([role] if cint(value) else [])
	if not roles:
		frappe.throw(_("At least one role must be able to open the {0}.").format(portal_def["label"]))
	set_portal_roles(portal, roles)
	return {"roles": sorted(roles)}


@frappe.whitelist(methods=["POST"])
def reset_portal_roles(portal):
	_only_manager()
	portal_def = next((p for p in PORTALS if p["key"] == portal), None)
	if not portal_def:
		frappe.throw(_("Unknown portal {0}.").format(portal))
	set_portal_roles(portal, portal_def["default_roles"])
	return True


@frappe.whitelist(methods=["POST"])
def create_role(role_name, desk_access=1):
	"""Create a role (or adopt an existing one) and list it here."""
	_only_manager()
	role_name = (role_name or "").strip()
	if not role_name:
		frappe.throw(_("Role name is required."))
	if role_name in PROTECTED_ROLES:
		frappe.throw(_("{0} cannot be managed from this screen.").format(role_name))
	existing = _canon().get(role_name.lower())
	if existing:
		role_name = existing
	else:
		frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": cint(desk_access)}).insert(
			ignore_permissions=True
		)
	_set_extra_roles(_extra_roles() | {role_name})
	return role_name


@frappe.whitelist(methods=["POST"])
def remove_role(role):
	"""Take a role off this screen. Only a role named nowhere in Uniquad can go
	(else it would keep working unseen); the Role itself stays."""
	_only_manager()
	_assert_role(role)
	if _role_usage()[0].get(role):
		frappe.throw(_("{0} still has access to parts of Uniquad. Turn it off everywhere first.").format(role))
	if role.startswith("slcm_"):
		frappe.throw(_("{0} is a built-in Uniquad role and cannot be removed.").format(role))
	_set_extra_roles(_extra_roles() - {role})
	return True


# ------------------------------------------------------------------ users


def _assert_user(user):
	if user in ("Administrator", "Guest") or not frappe.db.exists("User", user):
		frappe.throw(_("Choose a valid user."))


@frappe.whitelist()
def get_role_users(role):
	_only_manager()
	_assert_role(role)
	return frappe.get_all(
		"User",
		filters=[["Has Role", "role", "=", role], ["name", "not in", ["Administrator", "Guest"]]],
		fields=["name", "full_name", "user_type", "enabled", "last_active"],
		order_by="full_name asc",
		distinct=True,
	)


@frappe.whitelist(methods=["POST"])
def assign_role(user, role):
	_only_manager()
	_assert_role(role)
	_assert_user(user)
	frappe.get_doc("User", user).add_roles(role)
	return True


@frappe.whitelist(methods=["POST"])
def unassign_role(user, role):
	_only_manager()
	_assert_role(role)
	_assert_user(user)
	frappe.get_doc("User", user).remove_roles(role)
	return True


@frappe.whitelist(methods=["POST"])
def create_staff_user(email, first_name, last_name=None, roles=None):
	"""Create a staff (System) user, give them roles and email them Frappe's
	welcome mail with a set-password link."""
	_only_manager()
	email = (email or "").strip().lower()
	if not validate_email_address(email):
		frappe.throw(_("Enter a valid email address."))
	if frappe.db.exists("User", email):
		frappe.throw(_("A user with this email already exists; assign roles to them instead."))
	if isinstance(roles, str):
		roles = frappe.parse_json(roles)
	uniquad_roles = _uniquad_roles()
	roles = [r for r in (roles or []) if r in uniquad_roles and r not in PORTAL_ROLES]

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": (first_name or "").strip() or email,
			"last_name": (last_name or "").strip() or None,
			"user_type": "System User",
			"send_welcome_email": 1,
		}
	)
	user.insert(ignore_permissions=True)
	if roles:
		user.add_roles(*roles)
	return user.name
