"""
Default Helpdesk ticket views for AAD / AAD Staff agents.

AAD users chosen to work tickets (helpdesk agents) get two views
pinned in their Helpdesk agent sidebar: "Student Tickets" (assigned to them)
and "My Raised Tickets". HD View has no role targeting — a public view shows
to every agent — so each user gets their own pinned copy; helpdesk resolves
@me to the viewing user. The views are removed again when the user loses the
AAD role or stops being an agent.
"""

import json

import frappe

from slcm.permissions import AAD_ROLES

AGENT_ROUTE = "TicketsAgent"
AAD_TICKET_VIEWS = {
    "Student Tickets": {"_assign": ["LIKE", "%@me%"]},
    "My Raised Tickets": {"raised_by": "@me"},
}


def sync_user_ticket_views(doc, method=None):
    """Hook: User on_update — roles may have changed."""
    sync_ticket_views(doc.name)


def sync_agent_ticket_views(doc, method=None):
    """Hook: HD Agent after_insert / on_update / after_delete."""
    sync_ticket_views(doc.user or doc.name)


def sync_all_ticket_views():
    users = frappe.get_all(
        "Has Role", filters={"parenttype": "User", "role": ["in", list(AAD_ROLES)]}, pluck="parent", distinct=True
    )
    for user in users:
        sync_ticket_views(user)


def sync_ticket_views(user):
    if not user or not frappe.db.exists("DocType", "HD View"):
        return

    existing = {
        v.label: v.name
        for v in frappe.get_all(
            "HD View",
            filters={
                "user": user,
                "dt": "HD Ticket",
                "route_name": AGENT_ROUTE,
                "is_customer_portal": 0,
                "pinned": 1,
                "label": ["in", list(AAD_TICKET_VIEWS)],
            },
            fields=["name", "label"],
        )
    }

    # Same test helpdesk uses to open the agent UI (Agent / Agent Manager role
    # or an HD Agent record), so the views exist exactly when it's shown
    from helpdesk.utils import is_agent

    qualifies = bool(AAD_ROLES & set(frappe.get_roles(user))) and is_agent(user)
    if not qualifies:
        for name in existing.values():
            frappe.delete_doc("HD View", name, ignore_permissions=True)
        return

    for label, filters in AAD_TICKET_VIEWS.items():
        if label in existing:
            continue
        frappe.get_doc(
            {
                "doctype": "HD View",
                "label": label,
                "user": user,
                "dt": "HD Ticket",
                "type": "list",
                "route_name": AGENT_ROUTE,
                "is_customer_portal": 0,
                "pinned": 1,
                "filters": json.dumps(filters),
                "order_by": "modified desc",
                "columns": "[]",
                "rows": "[]",
            }
        ).insert(ignore_permissions=True)
