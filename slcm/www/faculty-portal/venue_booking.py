import frappe
from slcm.utils.faculty_portal import get_faculty_name, set_faculty_nav, set_nav_defaults, set_portal_settings

no_cache = 1


def get_context(context):
    context.no_cache = 1
    set_portal_settings(context)
    _set_defaults(context)

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "venue_booking"

    faculty_name = get_faculty_name()
    if not faculty_name:
        context.not_a_faculty = True
        set_nav_defaults(context)
        _set_defaults(context)
        return context

    context.not_a_faculty = False

    try:
        faculty = frappe.get_doc("Faculty", faculty_name)
        set_faculty_nav(context, faculty)

        # ── My bookings ─────────────────────────────────────────────
        my_bookings = frappe.get_all(
            "Venue Booking",
            filters={"owner": frappe.session.user, "requester_type": "Faculty"},
            fields=["name", "event_name", "venue_type", "venue as room",
                    "start_datetime", "end_datetime", "status",
                    "expected_attendees", "reason", "admin_remarks"],
            order_by="start_datetime desc",
            limit=40,
            ignore_permissions=True,
        )

        for b in my_bookings:
            b["start_fmt"] = frappe.utils.format_datetime(b.start_datetime, "dd MMM yyyy, hh:mm a") if b.start_datetime else "—"
            b["end_fmt"]   = frappe.utils.format_datetime(b.end_datetime, "hh:mm a") if b.end_datetime else "—"
            status = b.status or "Pending Allotment"
            b["status_class"] = {
                "Pending Allotment": "fp-badge-outline",
                "Allotted": "fp-badge-success",
                "Rejected": "fp-badge-dark",
                "Cancelled": "fp-badge-neutral",
            }.get(status, "fp-badge-neutral")

        context.my_bookings = my_bookings

        # ── Stats ────────────────────────────────────────────────────
        context.total_bookings = len(my_bookings)
        context.pending_bookings = sum(1 for b in my_bookings if (b.status or "Pending Allotment") == "Pending Allotment")
        context.approved_bookings = sum(1 for b in my_bookings if b.status == "Allotted")
        context.rejected_bookings = sum(1 for b in my_bookings if b.status == "Rejected")

        # ── Available rooms ──────────────────────────────────────────
        try:
            rooms = frappe.get_all(
                "Venue Master",
                filters={"is_active": 1},
                fields=["name", "venue_name_or_number", "venue_code", "capacity", "venue_type"],
                order_by="venue_name_or_number asc",
                ignore_permissions=True,
            )
            rooms = [
                {
                    "name": r.name or "",
                    "room_name": r.venue_name_or_number or r.name or "",
                    "room_number": r.venue_code or "",
                    "seating_capacity": r.capacity or 0,
                    "room_type": r.venue_type or "",
                }
                for r in rooms
            ]
        except Exception as re:
            frappe.log_error(f"Venue Booking rooms load error: {re}", "Faculty Portal")
            rooms = []
        context.available_rooms = rooms

    except Exception as e:
        frappe.log_error(f"Faculty Portal Venue Booking error: {e}", "Faculty Portal")
        context.portal_error = str(e)
        set_nav_defaults(context)
        _set_defaults(context)

    return context


def _set_defaults(context):
    context.is_guest = False
    context.not_a_faculty = False
    context.my_bookings = []
    context.total_bookings = 0
    context.pending_bookings = 0
    context.approved_bookings = 0
    context.rejected_bookings = 0
    context.available_rooms = []
