"""Helpdesk for AAD / AAD Staff, and the SLCM Technical Team for their tickets.

- Helpdesk's desktop icon is created from the helpdesk app (not a slcm JSON
  file), so its roles are set here: AAD / AAD Staff alongside its existing ones.
- HD Ticket read / write / create for AAD / AAD Staff (Custom DocPerm), and
  the student portal's Custom DocPerms on the other portal DocTypes (Ticket
  Template, Priority, Comment, Activity, Notification).
- Existing AAD users get HD Customer (new ones get it from the User validate
  hook, slcm.api.user_events.grant_helpdesk_customer_role).
- Create the SLCM Technical Team (HD Team creates its own round-robin
  Assignment Rule) with the technical team as active HD Agents. Technical Issue
  tickets raised by AAD users are routed to it by
  slcm.api.helpdesk_assignment.route_aad_technical_issue. Only created once —
  membership is managed from the HD Team form afterwards.
"""

import frappe
from frappe.permissions import rights, setup_custom_perms

from slcm.api.helpdesk_assignment import AAD_TECHNICAL_TEAM
from slcm.permissions import AAD_ROLES

HELPDESK_ICON_ROLES = ("System Manager", "Agent", "slcm_Faculty", *sorted(AAD_ROLES))
PORTAL_TEMPLATE_ROLE = "slcm_Student"
PORTAL_DOCTYPES = (
	"HD Ticket Template",
	"HD Ticket Priority",
	"HD Ticket Comment",
	"HD Ticket Activity",
	"HD Notification",
)
TECHNICAL_TEAM_MEMBERS = (
	"nishanth.a@azimpremjifoundation.org",
	"jenifar.a@azimpremjifoundation.org",
)


def execute():
	if not frappe.db.exists("DocType", "HD Team"):
		return

	if frappe.db.exists("Desktop Icon", "Helpdesk"):
		icon = frappe.get_doc("Desktop Icon", "Helpdesk")
		have = {r.role for r in icon.roles}
		missing = [r for r in HELPDESK_ICON_ROLES if r not in have and frappe.db.exists("Role", r)]
		if missing:
			for role in missing:
				icon.append("roles", {"role": role})
			icon.save(ignore_permissions=True)

	# HD Ticket runs on Custom DocPerms (no HD Customer row), so give the AAD
	# roles their own; helpdesk's permission_query still limits non-agents to
	# the tickets they raised
	setup_custom_perms("HD Ticket")
	for role in sorted(AAD_ROLES):
		if not frappe.db.exists("Custom DocPerm", {"parent": "HD Ticket", "role": role, "permlevel": 0, "if_owner": 0}):
			frappe.get_doc(
				{
					"doctype": "Custom DocPerm",
					"parent": "HD Ticket",
					"parenttype": "DocType",
					"parentfield": "permissions",
					"role": role,
					"permlevel": 0,
					"read": 1,
					"write": 1,
					"create": 1,
					"print": 1,
					"email": 1,
					# Custom DocPerm defaults export to 1
					"export": 0,
				}
			).insert(ignore_permissions=True)
	frappe.clear_cache(doctype="HD Ticket")

	# The customer portal also reads Ticket Template / Priority and writes
	# comments / activity; where those run on Custom DocPerms, HD Customer's
	# standard rows don't apply. Mirror what the student portal (slcm_Student)
	# is given there, owner restrictions included.
	meta = frappe.get_meta("Custom DocPerm")
	fields = ["permlevel", "if_owner", *(r for r in rights if meta.has_field(r))]
	for dt in PORTAL_DOCTYPES:
		student_rows = frappe.get_all(
			"Custom DocPerm", filters={"parent": dt, "role": PORTAL_TEMPLATE_ROLE}, fields=fields
		)
		if not student_rows:
			continue
		frappe.db.delete("Custom DocPerm", {"parent": dt, "role": ["in", list(AAD_ROLES)]})
		for role in sorted(AAD_ROLES):
			for row in student_rows:
				frappe.get_doc(
					{"doctype": "Custom DocPerm", "parent": dt, "parenttype": "DocType", "parentfield": "permissions", "role": role, **row}
				).insert(ignore_permissions=True)
		frappe.clear_cache(doctype=dt)

	aad_users = frappe.get_all(
		"Has Role", filters={"parenttype": "User", "role": ["in", list(AAD_ROLES)]}, pluck="parent", distinct=True
	)
	for user in aad_users:
		if "HD Customer" not in frappe.get_roles(user):
			frappe.get_doc("User", user).save(ignore_permissions=True)

	members = [u for u in TECHNICAL_TEAM_MEMBERS if frappe.db.get_value("User", u, "enabled")]
	for user in members:
		if frappe.db.exists("HD Agent", user):
			frappe.db.set_value("HD Agent", user, "is_active", 1)
		else:
			frappe.get_doc(
				{
					"doctype": "HD Agent",
					"user": user,
					"agent_name": frappe.db.get_value("User", user, "full_name") or user,
					"is_active": 1,
				}
			).insert(ignore_permissions=True)

	if not frappe.db.exists("HD Team", AAD_TECHNICAL_TEAM):
		frappe.get_doc(
			{
				"doctype": "HD Team",
				"team_name": AAD_TECHNICAL_TEAM,
				"users": [{"user": u} for u in members],
			}
		).insert(ignore_permissions=True)

	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")
