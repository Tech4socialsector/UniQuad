import json
import frappe
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from frappe.model.document import Document
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime
from frappe.email.doctype.email_template.email_template import get_email_template

WEEKDAY_FIELDS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

STATUS_PENDING = "Pending Allotment"
STATUS_ALLOTTED = "Allotted"
STATUS_REJECTED = "Rejected"
STATUS_CANCELLED = "Cancelled"

BLOCKING_STATUSES = (STATUS_PENDING, STATUS_ALLOTTED)


class VenueBooking(Document):
	def before_insert(self):
		self._set_requester_info()
		self.created_by = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
		self.created_on = frappe.utils.now()

	def validate(self):
		self.validate_dates()
		self.validate_recurrence_settings()
		self.check_availability()
		self._protect_status_field()

	def _protect_status_field(self):
		"""Prevent non-admin users from changing the status field directly."""
		if self.is_new():
			# New docs always start as Pending Allotment — reset if someone tried to set it
			self.status = STATUS_PENDING
			return

		admin_roles = {"System Manager", "Administrator", "slcm_Registrar"}
		user_roles = set(frappe.get_roles(frappe.session.user))
		if admin_roles & user_roles:
			return  # Admins may change status freely

		# For non-admins, revert any status change back to the saved value
		saved_status = frappe.db.get_value("Venue Booking", self.name, "status")
		if saved_status and self.status != saved_status:
			frappe.throw(
				_("You are not allowed to change the booking status. Only Admin can approve, reject, or cancel bookings."),
				frappe.PermissionError
			)

	def after_insert(self):
		_notify_admin_new_booking(self)
		if self.is_recurring and not self.parent_booking:
			self.create_recurring_bookings()

	def validate_dates(self):
		if get_datetime(self.start_datetime) < now_datetime():
			frappe.throw(_("Start Date & Time cannot be in the past"))
			
		if get_datetime(self.start_datetime) >= get_datetime(self.end_datetime):
			frappe.throw(_("End Date & Time must be after Start Date & Time"))

	def validate_recurrence_settings(self):
		"""Validate the recurrence fields on the series' parent booking.
		Generated occurrences carry parent_booking and never re-recurse, so they
		skip this entirely."""
		if not self.is_recurring or self.parent_booking:
			return

		if not self.recurrence_frequency:
			frappe.throw(_("Please select a Repeat Frequency for the recurring booking."))

		if not self.recurrence_end_date:
			frappe.throw(_("Please specify a 'Repeat Until' date for the recurring booking."))

		if getdate(self.recurrence_end_date) < getdate(self.start_datetime):
			frappe.throw(_("'Repeat Until' date cannot be before the Start Date & Time."))

		if self.recurrence_frequency == "Weekly" and not any(self.get(f) for f in WEEKDAY_FIELDS):
			frappe.throw(_("Please select at least one day of the week to repeat on."))

	def check_availability(self):
		if not self.venue:
			return

		is_active = frappe.db.get_value("Venue Master", self.venue, "is_active")
		if not is_active:
			frappe.throw(_("Booking is not allowed for this Venue: {0} (Not Active)").format(self.venue))

		# Lock the venue row to prevent concurrent double-booking of the same venue.
		# The lock is held until the end of the transaction.
		frappe.db.sql("SELECT name FROM `tabVenue Master` WHERE name = %s FOR UPDATE", (self.venue,))

		overlap = frappe.db.sql("""
			SELECT name FROM `tabVenue Booking`
			WHERE venue = %s
			AND docstatus < 2
			AND name != %s
			AND status IN %s
			AND start_datetime < %s 
			AND end_datetime > %s
		""", (self.venue, self.name or "New Venue Booking", BLOCKING_STATUSES, self.end_datetime, self.start_datetime))

		if overlap:
			frappe.throw(_("Venue {0} is already booked during this period (Ref: {1})").format(
				self.venue, overlap[0][0]))


	def create_recurring_bookings(self):
		"""Generate the remaining occurrences of a recurring series. Each occurrence
		is its own independent Venue Booking (own Pending status, own approval),
		linked back to this one via parent_booking. Dates that conflict with an
		existing booking are skipped rather than aborting the whole series."""
		if frappe.db.exists("Venue Booking", {"parent_booking": self.name}):
			return  # already generated (defensive — after_insert only fires once)

		start = get_datetime(self.start_datetime)
		duration = get_datetime(self.end_datetime) - start
		range_end = getdate(self.recurrence_end_date)

		selected_weekdays = None
		if self.recurrence_frequency == "Daily":
			step = timedelta(days=1)
		elif self.recurrence_frequency == "Weekly":
			step = timedelta(days=1)  # walk day-by-day, keep only selected weekdays
			selected_weekdays = {i for i, f in enumerate(WEEKDAY_FIELDS) if self.get(f)}
		elif self.recurrence_frequency == "Monthly":
			step = relativedelta(months=1)
		else:
			return

		candidate_starts = []
		current = start + step
		while getdate(current) <= range_end:
			if selected_weekdays is None or current.weekday() in selected_weekdays:
				candidate_starts.append(current)
			current += step

		if not candidate_starts:
			return

		# Batch-fetch existing bookings for this venue across the whole range up
		# front, instead of one query per candidate date.
		# Lock the venue master row once for the entire series generation
		frappe.db.sql("SELECT name FROM `tabVenue Master` WHERE name = %s FOR UPDATE", (self.venue,))

		existing = frappe.get_all(
			"Venue Booking",
			filters={
				"venue": self.venue,
				"name": ["!=", self.name],
				"docstatus": ["<", 2],
				"status": ["in", BLOCKING_STATUSES],
				"start_datetime": ["<", max(c + duration for c in candidate_starts)],
				"end_datetime": [">", min(candidate_starts)],
			},
			fields=["name", "start_datetime", "end_datetime"],
		)
		existing = [
			(get_datetime(e.start_datetime), get_datetime(e.end_datetime)) for e in existing
		]

		created_count = 0
		conflict_count = 0
		for occ_start in candidate_starts:
			occ_end = occ_start + duration
			if any(occ_start < e_end and occ_end > e_start for e_start, e_end in existing):
				conflict_count += 1
				continue

			occurrence = frappe.copy_doc(self)
			occurrence.start_datetime = occ_start
			occurrence.end_datetime = occ_end
			occurrence.parent_booking = self.name
			occurrence.status = STATUS_PENDING
			occurrence.is_recurring = 0
			occurrence.recurrence_frequency = None
			occurrence.recurrence_end_date = None
			for f in WEEKDAY_FIELDS:
				occurrence.set(f, 0)
			occurrence.insert(ignore_permissions=True)

			existing.append((occ_start, occ_end))
			created_count += 1

		if created_count:
			message = _("Created {0} recurring booking(s) for this venue.").format(created_count)
			if conflict_count:
				message += " " + _("Skipped {0} date(s) due to venue conflicts.").format(conflict_count)
			frappe.msgprint(message, indicator="green" if not conflict_count else "orange", alert=True)
		elif conflict_count:
			frappe.msgprint(
				_("Could not create any recurring bookings — all {0} date(s) conflicted with existing bookings.").format(conflict_count),
				indicator="red", alert=True,
			)

	def _set_requester_info(self):
		"""Auto-fill requester_name and requester_type from the logged-in user."""
		user = frappe.session.user
		if not self.requester_name:
			full_name = frappe.db.get_value("User", user, "full_name") or user
			self.requester_name = full_name

		if not self.requester_type:
			roles = set(frappe.get_roles(user))
			if "slcm_Student" in roles:
				self.requester_type = "Student"
			elif "slcm_Faculty" in roles:
				self.requester_type = "Faculty"
			elif "slcm_Staff" in roles:
				self.requester_type = "Staff"
			else:
				self.requester_type = "Other"

		# Auto-link student record if requester is a student
		if not self.student and self.requester_type == "Student":
			student = _get_student_for_user(user)
			if student:
				self.student = student


# ─────────────────────────────────────────────────────────────────────────────
#  Venue query helper
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_venue_query_old(doctype, txt, searchfield, start, page_len, filters):
	filters_dict = {}
	if hasattr(filters, 'get'):
		filters_dict = filters
	elif isinstance(filters, str):
		filters_dict = json.loads(filters)

	conditions = []
	values = []
	if filters_dict.get('venue_type'):
		conditions.append("room_type = %s")
		values.append(filters_dict['venue_type'])

	if txt:
		conditions.append("room_name LIKE %s")
		values.append("%" + txt + "%")

	where_clause = ""
	if conditions:
		where_clause = "WHERE " + " AND ".join(conditions)

	return frappe.db.sql("""
		SELECT name, room_name, seating_capacity
		FROM `tabRoom`
		{where_clause}
		LIMIT %s, %s
	""".format(where_clause=where_clause), tuple(values + [int(start), int(page_len)]))


# ─────────────────────────────────────────────────────────────────────────────
#  Admin actions (approve / reject / cancel / swap)
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_venue_query(doctype, txt, searchfield, start, page_len, filters):
	filters_dict = {}
	if hasattr(filters, 'get'):
		filters_dict = filters
	elif isinstance(filters, str):
		filters_dict = json.loads(filters)

	venue_type = filters_dict.get("venue_type")
	expected_attendees = filters_dict.get("expected_attendees")
	include_booked = filters_dict.get("include_booked") in [1, "1", True, "true"]
	sort_order = filters_dict.get("sort_order", "asc")
	exclude_booking = filters_dict.get("exclude_booking")

	start_datetime = filters_dict.get("start_datetime")
	end_datetime = filters_dict.get("end_datetime")

	if expected_attendees is not None:
		try:
			expected_attendees = int(expected_attendees)
			if expected_attendees <= 0:
				frappe.throw(_("Expected attendees must be greater than 0"))
		except ValueError:
			pass
	
	conditions = ["`tabVenue Master`.is_active = 1"]
	values = []

	if venue_type:
		conditions.append("`tabVenue Master`.venue_type = %s")
		values.append(venue_type)

	if expected_attendees and isinstance(expected_attendees, int):
		conditions.append("`tabVenue Master`.capacity >= %s")
		values.append(expected_attendees)

	if txt:
		conditions.append("`tabVenue Master`.name LIKE %s")
		values.append(f"%{txt}%")

	user_roles = frappe.get_roles(frappe.session.user)
	if "System Manager" not in user_roles and "Administrator" not in user_roles:
		if user_roles:
			format_strings = ','.join(['%s'] * len(user_roles))
			conditions.append(f"`tabVenue Master`.name IN (SELECT parent FROM `tabVenue Allowed Role` WHERE role IN ({format_strings}) AND parenttype='Venue Master')")
			values.extend(user_roles)
		else:
			conditions.append("1=0")

	where_clause = " AND ".join(conditions)
	order_dir = "DESC" if str(sort_order).lower() == "desc" else "ASC"

	query = f"""
		SELECT `tabVenue Master`.name AS value, `tabVenue Master`.venue_name_or_number AS description, `tabVenue Master`.capacity
		FROM `tabVenue Master`
		WHERE {where_clause}
		ORDER BY `tabVenue Master`.capacity {order_dir}, `tabVenue Master`.name {order_dir}
		LIMIT %s, %s
	"""
	
	values.extend([start, page_len])
	venues = frappe.db.sql(query, tuple(values), as_dict=True)

	# If datetimes are provided, check availability
	if start_datetime and end_datetime and venues:
		is_recurring = filters_dict.get("is_recurring") in [1, "1", True, "true"]
		candidate_dates = []
		
		s_dt = get_datetime(start_datetime)
		e_dt = get_datetime(end_datetime)
		duration = e_dt - s_dt
		
		if is_recurring:
			frequency = filters_dict.get("recurrence_frequency")
			range_end = filters_dict.get("recurrence_end_date")
			if frequency and range_end:
				range_end_date = getdate(range_end)
				if frequency == "Daily":
					step = timedelta(days=1)
					selected_weekdays = None
				elif frequency == "Weekly":
					step = timedelta(days=1)
					selected_weekdays = {i for i, f in enumerate(WEEKDAY_FIELDS) if filters_dict.get(f) in [1, "1", True, "true"]}
				elif frequency == "Monthly":
					step = relativedelta(months=1)
					selected_weekdays = None
				else:
					step = None

				if step:
					candidate_starts = []
					current = s_dt
					while getdate(current) <= range_end_date:
						if selected_weekdays is None or current.weekday() in selected_weekdays:
							candidate_starts.append(current)
						current += step
					candidate_dates = [(c, c + duration) for c in candidate_starts]
		
		if not candidate_dates:
			candidate_dates = [(s_dt, e_dt)]
			
		venue_names = [v.value for v in venues]
		min_start = min(c[0] for c in candidate_dates)
		max_end = max(c[1] for c in candidate_dates)
		
		overlap_cond = " AND name != %s" if exclude_booking else ""
		overlap_val = [exclude_booking] if exclude_booking else []
		
		format_strings = ','.join(['%s'] * len(venue_names))
		status_strings = ','.join(['%s'] * len(BLOCKING_STATUSES))
		
		overlap_query = f"""
			SELECT name, venue, status, start_datetime, end_datetime 
			FROM `tabVenue Booking`
			WHERE venue IN ({format_strings})
			AND docstatus < 2
			AND status IN ({status_strings})
			AND start_datetime < %s 
			AND end_datetime > %s
			{overlap_cond}
		"""
		
		q_values = venue_names + list(BLOCKING_STATUSES) + [max_end, min_start] + overlap_val
		
		existing_bookings = frappe.db.sql(overlap_query, tuple(q_values), as_dict=True)
		
		venue_bookings_map = {}
		for b in existing_bookings:
			venue_bookings_map.setdefault(b.venue, []).append(b)

		filtered_venues = []
		for v in venues:
			is_booked = False
			booked_booking_name = None
			booked_booking_status = None
			
			ex_bookings = venue_bookings_map.get(v.value, [])
			for eb in ex_bookings:
				eb_start = get_datetime(eb.start_datetime)
				eb_end = get_datetime(eb.end_datetime)
				
				# check overlap with any candidate date
				for c_start, c_end in candidate_dates:
					if eb_start < c_end and eb_end > c_start:
						is_booked = True
						booked_booking_name = eb.name
						booked_booking_status = eb.status
						break
				if is_booked:
					break
			
			v.is_booked = is_booked
			v.booked_booking_name = booked_booking_name
			v.booked_booking_status = booked_booking_status
			
			if not is_booked or include_booked:
				filtered_venues.append(v)
				
		return filtered_venues

	return venues


@frappe.whitelist()
def approve_booking(booking_name, admin_remarks=None):
	_require_admin()
	booking = frappe.get_doc("Venue Booking", booking_name)
	if booking.status != STATUS_PENDING:
		frappe.throw(_("Only bookings Pending Allotment can be allotted."))
	frappe.db.set_value("Venue Booking", booking_name, {
		"status": STATUS_ALLOTTED,
		"admin_remarks": admin_remarks or "",
		**_reply_meta()
	})
	frappe.db.commit()
	_notify_requester(booking_name, STATUS_ALLOTTED, admin_remarks)
	return {"status": STATUS_ALLOTTED}


@frappe.whitelist()
def reject_booking(booking_name, admin_remarks=None):
	_require_admin()
	booking = frappe.get_doc("Venue Booking", booking_name)
	if booking.status != STATUS_PENDING:
		frappe.throw(_("Only bookings Pending Allotment can be rejected."))
	frappe.db.set_value("Venue Booking", booking_name, {
		"status": STATUS_REJECTED,
		"admin_remarks": admin_remarks or "",
		**_reply_meta()
	})
	frappe.db.commit()
	_notify_requester(booking_name, STATUS_REJECTED, admin_remarks)
	return {"status": STATUS_REJECTED}


@frappe.whitelist()
def cancel_booking(booking_name, admin_remarks=None):
	_require_admin()
	booking = frappe.get_doc("Venue Booking", booking_name)
	if booking.status == "Cancelled":
		frappe.throw(_("Booking is already cancelled."))
	frappe.db.set_value("Venue Booking", booking_name, {
		"status": "Cancelled",
		"admin_remarks": admin_remarks or "",
		**_reply_meta()
	})
	frappe.db.commit()
	_notify_requester(booking_name, "Cancelled", admin_remarks)
	return {"status": "Cancelled"}


def _reply_meta():
	"""replied_by/replied_on stamp for whichever admin action (Allot/Reject/Cancel)
	is changing the booking's status."""
	return {
		"replied_by": frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user,
		"replied_on": frappe.utils.now(),
	}


@frappe.whitelist()
def approve_venue_swap(booking_name, admin_remarks=None):
    """Admin approves a student's swap request — moves the booking to the requested venue."""
    _require_admin()

    booking = frappe.get_doc("Venue Booking", booking_name, ignore_permissions=True)

    if not booking.swap_requested or booking.swap_status != "Pending":
        frappe.throw(_("No pending swap request found for this booking."))

    new_venue = booking.swap_requested_venue
    if not new_venue:
        frappe.throw(_("Swap request has no target venue specified."))

    # Conflict check: can the booking move to the new venue?
    try:
        check_conflict(booking, new_venue)
    except Exception as e:
        frappe.throw(_("Cannot approve swap — {0}").format(str(e)))

    old_venue = booking.venue
    decided_by = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

    frappe.db.set_value("Venue Booking", booking_name, {
        "swap_status":         "Approved",
        "swap_admin_remarks":  admin_remarks or "",
        "venue":               new_venue,
        "swap_requested":      0
    }, update_modified=False)

    frappe.db.sql("""
        UPDATE `tabVenue Swap Log`
        SET swap_status    = 'Approved',
            decided_on     = %(now)s,
            decided_by     = %(by)s,
            admin_remarks  = %(remarks)s,
            modified       = %(now)s
        WHERE parent = %(parent)s
          AND swap_status = 'Pending'
        ORDER BY idx DESC
        LIMIT 1
    """, {"parent": booking_name, "now": frappe.utils.now(),
          "by": decided_by, "remarks": admin_remarks or ""})
    frappe.db.commit()

    _notify_requester_swap(booking_name, "Approved", old_venue, new_venue, admin_remarks)
    return {"status": "swap_approved", "new_venue": new_venue}


@frappe.whitelist()
def reject_venue_swap(booking_name, admin_remarks=None):
    """Admin rejects a student's swap request — booking stays in the current venue."""
    _require_admin()

    booking = frappe.get_doc("Venue Booking", booking_name, ignore_permissions=True)

    if not booking.swap_requested or booking.swap_status != "Pending":
        frappe.throw(_("No pending swap request found for this booking."))

    decided_by = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

    frappe.db.set_value("Venue Booking", booking_name, {
        "swap_requested":     0,
        "swap_status":        "Rejected",
        "swap_admin_remarks": admin_remarks or "",
    }, update_modified=False)

    frappe.db.sql("""
        UPDATE `tabVenue Swap Log`
        SET swap_status    = 'Rejected',
            decided_on     = %(now)s,
            decided_by     = %(by)s,
            admin_remarks  = %(remarks)s,
            modified       = %(now)s
        WHERE parent = %(parent)s
          AND swap_status = 'Pending'
        ORDER BY idx DESC
        LIMIT 1
    """, {"parent": booking_name, "now": frappe.utils.now(),
          "by": decided_by, "remarks": admin_remarks or ""})
    frappe.db.commit()

    _notify_requester_swap(booking_name, "Rejected", 
                           booking.venue, booking.swap_requested_venue, admin_remarks)

    return {"status": "swap_rejected"}


def _notify_requester_swap(booking_name, decision, old_room, new_room, admin_remarks=None):
    """Email the requester when their swap request is approved or rejected."""
    try:
        doc = frappe.db.get_value(
            "Venue Booking", booking_name,
            ["owner", "event_name", "requester_name", "start_datetime", "end_datetime"],
            as_dict=True,
        )
        if not doc:
            return

        requester_email = frappe.db.get_value("User", doc.owner, "email")
        if not requester_email:
            return

        new_room_name = frappe.db.get_value("Venue Master", new_room, "venue_name_or_number") or new_room or "—"
        color = "#166534" if decision == "Approved" else "#991b1b"
        bg    = "#f0fdf4" if decision == "Approved" else "#fef2f2"
        body_detail = (
            f"Your venue has been moved from <strong>{old_room}</strong> to <strong>{new_room_name}</strong>."
            if decision == "Approved"
            else f"Your request to move to <strong>{new_room_name}</strong> was not approved. Your booking remains in <strong>{old_room}</strong>."
        )

        args = {
            "booking_name": booking_name,
            "event_name": doc.event_name,
            "requester_name": doc.requester_name or "there",
            "start_datetime": doc.start_datetime,
            "end_datetime": doc.end_datetime,
            "decision": decision,
            "decision_lower": decision.lower(),
            "color": color,
            "bg": bg,
            "admin_remarks": admin_remarks or "",
            "body_detail": body_detail,
        }
        rendered = get_email_template("Venue Booking - Swap Request Decision (Requester)", args)
        frappe.sendmail(
            recipients=[requester_email],
            subject=rendered.get("subject"),
            message=rendered.get("message"),
            now=False,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Venue Swap — Requester Notification Error")


@frappe.whitelist()
def swap_venues(booking_a, booking_b):
	"""Swap the venues of two bookings."""
	_require_admin()
	doc_a = frappe.get_doc("Venue Booking", booking_a)
	doc_b = frappe.get_doc("Venue Booking", booking_b)

	venue_a = doc_a.venue
	venue_b = doc_b.venue

	if venue_a == venue_b:
		frappe.throw(_("Both bookings are already for the same venue."))

	# Conflict check excluding each other
	try:
		check_conflict(doc_a, venue_b, exclude_booking=doc_b.name)
		check_conflict(doc_b, venue_a, exclude_booking=doc_a.name)

		frappe.db.set_value("Venue Booking", doc_a.name, "venue", venue_b)
		frappe.db.set_value("Venue Booking", doc_b.name, "venue", venue_a)

		doc_a.add_comment("Comment", _("Venue swapped with {0}").format(doc_b.name))
		doc_b.add_comment("Comment", _("Venue swapped with {0}").format(doc_a.name))

		frappe.msgprint(_("Venues swapped successfully: {0} ↔ {1}").format(venue_a, venue_b))

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Venue Swap Error")
		frappe.throw(_("Could not swap venues: {0}").format(str(e)))


def check_conflict(booking_doc, new_venue, exclude_booking=None):
	existing = frappe.db.sql("""
		SELECT name FROM `tabVenue Booking`
		WHERE venue = %s
		AND docstatus < 2
		AND name != %s
		AND name != %s
		AND status IN %s
		AND start_datetime < %s 
		AND end_datetime > %s
	""", (new_venue, booking_doc.name, exclude_booking or "", BLOCKING_STATUSES,
		booking_doc.end_datetime, booking_doc.start_datetime))

	if existing:
		frappe.throw(_("Booking {0} conflicts with existing booking {1} in {2}").format(
			booking_doc.name, existing[0][0], new_venue))


# ─────────────────────────────────────────────────────────────────────────────
#  Calendar availability (used by desk calendar view or external queries)
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_venue_bookings(venue=None, from_date=None, to_date=None):
	"""Return bookings for calendar display. Optionally filter by venue and date range."""
	filters = [["status", "not in", ["Cancelled", "Rejected"]], ["docstatus", "<", 2]]
	if venue:
		filters.append(["venue", "=", venue])
	if from_date:
		filters.append(["start_datetime", ">=", from_date])
	if to_date:
		filters.append(["end_datetime", "<=", to_date])

	return frappe.get_all(
		"Venue Booking",
		filters=filters,
		fields=[
			"name", "event_name", "venue", "venue_type",
			"start_datetime", "end_datetime", "status",
			"requester_name", "requester_type"
		],
		order_by="start_datetime asc",
		ignore_permissions=True,
	)


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _require_admin():
	allowed_roles = {"System Manager", "Administrator", "slcm_Registrar"}
	user_roles = set(frappe.get_roles(frappe.session.user))
	if not (allowed_roles & user_roles):
		frappe.throw(_("You do not have permission to perform this action."), frappe.PermissionError)


def _get_student_for_user(user):
	name = frappe.db.get_value("Student Master", {"user": user}, "name")
	if not name:
		name = frappe.db.get_value("Student Master", {"email": user}, "name")
	if not name:
		name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
	return name


def _notify_admin_new_booking(doc):
	"""Email the admin/registrar when a new booking is submitted."""
	try:
		admin_roles = ["slcm_Registrar", "System Manager"]
		admin_emails = []
		for role in admin_roles:
			users = frappe.get_all(
				"Has Role",
				filters={"role": role, "parenttype": "User"},
				fields=["parent"],
				ignore_permissions=True,
			)
			for u in users:
				email = frappe.db.get_value("User", u.parent, "email")
				if email and email not in admin_emails:
					admin_emails.append(email)

		if not admin_emails:
			return

		# requester_name now stores the display name directly
		requester_display = doc.requester_name or "—"

		# Build direct approval link to the Venue Booking desk form
		site_url = frappe.utils.get_url()
		booking_url = f"{site_url}/app/venue-booking/{doc.name}"

		args = {
			"booking_name": doc.name,
			"booking_url": booking_url,
			"event_name": doc.event_name,
			"requester_display": requester_display,
			"requester_type": doc.requester_type,
			"programme": getattr(doc, "programme", None) or "",
			"batch": getattr(doc, "batch", None) or "",
			"academic_year": getattr(doc, "academic_year", None) or "",
			"venue": doc.venue,
			"venue_type": doc.venue_type,
			"start_datetime": doc.start_datetime,
			"end_datetime": doc.end_datetime,
			"expected_attendees": doc.expected_attendees,
			"reason": doc.reason,
		}
		rendered = get_email_template("Venue Booking - New Request (Admin)", args)
		frappe.sendmail(
			recipients=admin_emails,
			subject=rendered.get("subject"),
			message=rendered.get("message"),
			now=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Venue Booking — Admin Notification Error")


def _notify_requester(booking_name, new_status, admin_remarks=None):
	"""Email the booking owner when their request is approved, rejected, or cancelled."""
	try:
		doc = frappe.db.get_value(
			"Venue Booking", booking_name,
			["owner", "event_name", "venue", "venue_type", "start_datetime", "end_datetime", "requester_name"],
			as_dict=True,
		)
		if not doc:
			return

		requester_email = frappe.db.get_value("User", doc.owner, "email")
		if not requester_email:
			return

		status_colors = {
			STATUS_ALLOTTED: "#166534",
			STATUS_REJECTED: "#991b1b",
			STATUS_CANCELLED: "#374151",
		}
		status_bg = {
			STATUS_ALLOTTED: "#f0fdf4",
			STATUS_REJECTED: "#fef2f2",
			STATUS_CANCELLED: "#f3f4f6",
		}
		color = status_colors.get(new_status, "#374151")
		bg    = status_bg.get(new_status, "#f3f4f6")
		footer_note = (
			"Your booking is confirmed. Please ensure the venue is kept clean after use."
			if new_status == STATUS_ALLOTTED
			else "If you have any questions, please contact the administration."
		)

		args = {
			"booking_name": booking_name,
			"event_name": doc.event_name,
			"requester_name": doc.requester_name or "there",
			"venue": doc.venue,
			"venue_type": doc.venue_type,
			"start_datetime": doc.start_datetime,
			"end_datetime": doc.end_datetime,
			"new_status": new_status,
			"new_status_lower": new_status.lower(),
			"color": color,
			"bg": bg,
			"admin_remarks": admin_remarks or "",
			"footer_note": footer_note,
		}
		rendered = get_email_template("Venue Booking - Status Update (Requester)", args)
		frappe.sendmail(
			recipients=[requester_email],
			subject=rendered.get("subject"),
			message=rendered.get("message"),
			now=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Venue Booking — Requester Notification Error")

	@frappe.whitelist()
	def override_booking(self, target_booking_name, reason):
		if "AAD" not in frappe.get_roles(frappe.session.user):
			frappe.throw(_("Only AAD members can override bookings."))

		if not target_booking_name:
			frappe.throw(_("Target booking to override is required."))

		target = frappe.get_doc("Venue Booking", target_booking_name)
		if target.status not in BLOCKING_STATUSES:
			frappe.throw(_("Target booking is not active, so it cannot be overridden."))

		if target.venue != self.venue:
			frappe.throw(_("Target booking venue does not match this booking venue."))

		# Check 24 hour notice
		now = frappe.utils.now_datetime()
		s_dt = get_datetime(target.start_datetime)
		if (s_dt - now).total_seconds() < 24 * 3600:
			frappe.throw(_("Cannot override booking. Must provide at least 24 hours notice before the event."))

		# Perform override
		target.db_set("status", "Cancelled")
		target.db_set("admin_remarks", f"Overridden by AAD ({frappe.session.user}). Reason: {reason}")
		
		# Set on self
		self.db_set("overridden_booking", target.name)
		self.db_set("overridden_by", frappe.session.user)
		self.db_set("override_reason", reason)
		self.db_set("override_notice_sent_on", frappe.utils.now_datetime())

		# Notify target owner
		owner_email = frappe.db.get_value("User", target.owner, "email")
		if owner_email:
			frappe.sendmail(
				recipients=[owner_email],
				subject=f"Notice: Venue Booking {target.name} Overridden",
				message=f"""
				<p>Dear {target.requester_name or 'User'},</p>
				<p>Your booking <strong>{target.name}</strong> for event <strong>{target.event_name}</strong> has been cancelled and the venue overridden by the Academic Affairs Department (AAD).</p>
				<p><strong>Reason provided:</strong> {reason}</p>
				"""
			)
		frappe.msgprint(_("Booking {0} has been overridden and cancelled.").format(target.name), alert=True)
