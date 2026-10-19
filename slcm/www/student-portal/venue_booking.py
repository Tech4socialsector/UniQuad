import frappe
from frappe.utils import now_datetime

no_cache = 1

VENUE_TYPES = [
    "Classroom", "Moot Court", "Open Spaces", "Meeting Room",
    "Mess", "Quad", "Conference Hall", "Project", "Guest House", "Staff Quarters"
]


def get_context(context):
    context.no_cache = 1

    if frappe.session.user == "Guest":
        context.is_guest = True
        return context

    context.is_guest = False
    context.active_page = "venue_booking"

    student_name = _get_student_name()
    if not student_name:
        context.no_student = True
        _set_nav_defaults(context)
        context.venue_bookings = []
        context.all_swap_logs  = []
        context.venue_types = VENUE_TYPES
        return context

    context.no_student = False

    try:
        student = frappe.get_doc("Student Master", student_name)
        _set_student_nav(context, student)

        user = frappe.session.user

        # Comprehensive lookup via direct SQL + JOIN so bookings are found
        # regardless of whether they were submitted via the portal or created
        # by an admin on the student's behalf.
        #
        # A booking "belongs" to this portal user if ANY of the following is true:
        #  1. vb.student  = the student record found for this portal user
        #  2. vb.owner    = this portal user (student submitted it themselves)
        #  3. Linked Student Master has user         = this portal user's email
        #  4. Linked Student Master has email        = this portal user's email
        #  5. Linked Student Master has official_email_id = this portal user's email
        venue_bookings = frappe.db.sql("""
            SELECT DISTINCT
                vb.name, vb.event_name, vb.venue_type, vb.venue AS room, vb.capacity,
                vb.start_datetime, vb.end_datetime, vb.status,
                vb.reason, vb.attachment, vb.admin_remarks,
                vb.expected_attendees, vb.creation,
                vb.swap_requested, vb.swap_requested_venue AS swap_requested_room,
                vb.swap_request_reason, vb.swap_status, vb.swap_admin_remarks
            FROM `tabVenue Booking` vb
            LEFT JOIN `tabStudent Master` sm ON sm.name = vb.student
            WHERE vb.docstatus IN (0, 1)
              AND (
                    vb.student = %(student)s
                 OR vb.owner   = %(user)s
                 OR sm.user              = %(user)s
                 OR sm.email             = %(user)s
                 OR sm.official_email_id = %(user)s
              )
            ORDER BY vb.creation DESC
            LIMIT 100
        """, {"student": student_name, "user": user}, as_dict=True)

        # Fetch swap logs for all bookings in one query
        booking_names = [b.name for b in venue_bookings]
        swap_logs = {}
        if booking_names:
            placeholders = ", ".join(["%s"] * len(booking_names))
            log_rows = frappe.db.sql("""
                SELECT parent, from_room, to_room, swap_status,
                       requested_on, requested_by, decided_on, decided_by,
                       swap_reason, admin_remarks
                FROM `tabVenue Swap Log`
                WHERE parent IN ({ph})
                ORDER BY parent, idx ASC
            """.format(ph=placeholders), tuple(booking_names), as_dict=True)
            for row in log_rows:
                swap_logs.setdefault(row.parent, []).append(row)

        for b in venue_bookings:
            b.swap_history = swap_logs.get(b.name, [])

        # Build a flat sorted list of all swap log entries for the dedicated section
        all_swap_logs = []
        for b in venue_bookings:
            for lg in b.swap_history:
                all_swap_logs.append({
                    "booking":   b.name,
                    "event":     b.event_name or "",
                    "from_room": lg.from_room or "",
                    "to_room":   lg.to_room or "",
                    "swap_status":   lg.swap_status or "",
                    "requested_by":  lg.requested_by or "",
                    "requested_on":  lg.requested_on,
                    "decided_by":    lg.decided_by or "",
                    "decided_on":    lg.decided_on,
                    "swap_reason":   lg.swap_reason or "",
                    "admin_remarks": lg.admin_remarks or "",
                })
        # Sort newest first
        all_swap_logs.sort(key=lambda x: x["requested_on"] or "", reverse=True)
        context.all_swap_logs = all_swap_logs

        context.venue_bookings = venue_bookings
        context.total_count     = len(venue_bookings)
        context.pending_count   = sum(1 for b in venue_bookings if b.status == "Pending Allotment")
        context.approved_count  = sum(1 for b in venue_bookings if b.status == "Allotted")
        context.rejected_count  = sum(1 for b in venue_bookings if b.status == "Rejected")
        context.cancelled_count = sum(1 for b in venue_bookings if b.status == "Cancelled")
        context.venue_types     = VENUE_TYPES

    except Exception as e:
        frappe.log_error(f"Venue Booking portal error: {e}", "Student Portal")
        context.portal_error = str(e)
        _set_nav_defaults(context)
        context.venue_bookings = []
        context.all_swap_logs  = []
        context.venue_types    = VENUE_TYPES

    return context



def _get_student_name():
    user = frappe.session.user
    name = frappe.db.get_value("Student Master", {"user": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"email": user}, "name")
    if not name:
        name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
    if name:
        try:
            current_user = frappe.db.get_value("Student Master", name, "user")
            if not current_user:
                frappe.db.set_value("Student Master", name, "user", user, update_modified=False)
        except Exception:
            pass
    return name


def _set_student_nav(context, student):
    full_name = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))
    context.student_name   = full_name or student.name
    context.student_id     = student.registration_id or student.name
    context.student_photo  = student.passport_size_photo or ""
    context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
    context.programme_name = frappe.db.get_value("Batch", student.programme, "cohort_name") or student.programme or ""
    context.department     = student.department or ""
    context.batch_year     = student.batch_year or ""


def _set_nav_defaults(context):
    user     = frappe.session.user
    user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
    context.student_name   = (user_doc.full_name if user_doc else "") or user.split("@")[0]
    context.student_id     = ""
    context.student_photo  = (user_doc.user_image if user_doc else "") or ""
    context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
    context.programme_name = ""
    context.department     = ""
    context.batch_year     = ""
