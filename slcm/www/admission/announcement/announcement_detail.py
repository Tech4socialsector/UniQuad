import frappe

login_required = False

def get_context(context):
    from slcm.admission.utils.portal import get_portal_config
    from slcm.admission.utils.web import _get_portal_announcement_read_ids

    context.portal_config = get_portal_config()

    name = frappe.form_dict.get("name") or ""
    if not name or not frappe.db.exists(
        "Portal Announcement",
        {"name": name, "is_active": 1, "status": "Published"},
    ):
        frappe.throw("Announcement not found or inactive", frappe.DoesNotExistError)

    ann = frappe.get_doc("Portal Announcement", name)
    context.announcement = ann
    context.no_cache = 1
    context.title = ann.title

    user = frappe.session.user or "Guest"
    context.portal_user_logged_in = user != "Guest"
    context.announcement_id = ann.name
    if context.portal_user_logged_in:
        context.announcement_marked_done = ann.name in _get_portal_announcement_read_ids(user)
    else:
        context.announcement_marked_done = False
