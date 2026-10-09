# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import get_datetime


def get_active_google_calendar_account():
	"""Return the name of the Google Calendar account to push Time Table entries to.

	SLCM syncs every Time Table entry into a single shared Google Calendar
	account (the first enabled one with push turned on) rather than mapping
	per-instructor calendars.
	"""
	return frappe.db.get_value(
		"Google Calendar", {"enable": 1, "push_to_google_calendar": 1}, "name"
	)


def _ensure_google_calendar_ready():
	"""Throw a user-readable error if Google Calendar sync can't work yet,
	instead of letting every class fail later with a raw traceback."""
	account = get_active_google_calendar_account()
	if not account:
		frappe.throw(
			"Google Calendar sync is not configured yet. Contact the administrator.",
			title="Calendar Sync Unavailable",
		)

	settings = frappe.get_cached_doc("Google Settings")
	if not settings.enable or not settings.client_id:
		frappe.throw(
			"Google API is not enabled in Google Settings. Contact the administrator.",
			title="Calendar Sync Unavailable",
		)

	# refresh_token is a Password field: the stored value is masked but non-empty
	# once Google access has been granted.
	if not frappe.db.get_value("Google Calendar", account, "refresh_token"):
		frappe.throw(
			f"The Google Calendar account <b>{account}</b> has not been authorized yet. "
			"An administrator must open it and click <b>Allow Google Calendar Access</b>.",
			title="Calendar Sync Unavailable",
		)

	return account


def build_event_fields(doc):
	subject = doc.title or doc.course or "Class"
	if doc.venue:
		subject = f"{subject} ({doc.venue})"

	return {
		"subject": subject,
		"starts_on": get_datetime(f"{doc.schedule_date} {doc.from_time}"),
		"ends_on": get_datetime(f"{doc.schedule_date} {doc.to_time}"),
	}


def sync_time_table_to_google_calendar(doc, method=None, raise_error=False):
	"""Create/update a linked Event so this Time Table entry pushes to Google
	Calendar via Frappe's existing Event -> Google Calendar sync hooks."""
	if not (doc.schedule_date and doc.from_time and doc.to_time):
		return

	# Document.insert() runs after_insert and then on_update. The after_insert
	# hook has just pushed this event, so the on_update one would only push it
	# to Google a second time (and doubles the time a recurring series takes).
	if method == "on_update" and doc.flags.in_insert:
		return

	account = get_active_google_calendar_account()
	if not account:
		return

	stats = frappe.flags.tt_bulk_stats
	prev_mute = frappe.flags.mute_messages
	# Frappe's Event -> Google push msgprints "Event Synced with Google
	# Calendar." on every push; report it once below instead.
	frappe.flags.mute_messages = True

	# If the Google push in Event.after_insert fails, the Event row is already
	# written — roll back to here so we don't leave orphan Events behind.
	frappe.db.savepoint("tt_gcal_sync")
	try:
		event_fields = build_event_fields(doc)

		if doc.linked_google_event and frappe.db.exists("Event", doc.linked_google_event):
			event = frappe.get_doc("Event", doc.linked_google_event)
			event.update(event_fields)
			event.save(ignore_permissions=True)
		else:
			event = frappe.get_doc(
				{
					"doctype": "Event",
					"event_type": "Private",
					"sync_with_google_calendar": 1,
					"google_calendar": account,
					"description": f"Synced from Time Table: {doc.name}",
					**event_fields,
				}
			)
			event.insert(ignore_permissions=True)
			frappe.db.set_value(
				"Time Table", doc.name, "linked_google_event", event.name, update_modified=False
			)
			doc.linked_google_event = event.name
	except Exception:
		frappe.db.rollback(save_point="tt_gcal_sync")
		frappe.log_error(
			message=frappe.get_traceback(), title="Time Table Google Calendar Sync Failed"
		)
		if stats is not None:
			stats.gcal_failed += 1
		if raise_error:
			raise
		return
	finally:
		frappe.flags.mute_messages = prev_mute

	if stats is not None:
		stats.gcal_synced += 1
	elif not prev_mute and not frappe.flags.tt_summary_shown:
		frappe.msgprint("Synced with Google Calendar.", indicator="green", alert=True)


def _get_student_for_session_user():
	user = frappe.session.user
	name = (
		frappe.db.get_value("Student Master", {"user": user}, "name")
		or frappe.db.get_value("Student Master", {"email": user}, "name")
		or frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
	)
	if not name:
		frappe.throw("No student record found for your account.")
	return frappe.get_doc("Student Master", name)


def _get_or_create_contact_for_email(email, full_name=None):
	existing = frappe.db.get_value("Contact Email", {"email_id": email}, "parent")
	if existing:
		return existing

	contact = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": full_name or email.split("@")[0],
			"email_ids": [{"email_id": email, "is_primary": 1}],
		}
	)
	contact.insert(ignore_permissions=True)
	return contact.name


def _get_enrolled_course_offerings(student_name):
	rows = frappe.get_all(
		"Attendance Summary",
		filters={"student": student_name},
		fields=["course_offering"],
		ignore_permissions=True,
	)
	return {r.course_offering for r in rows if r.course_offering}


@frappe.whitelist()
def sync_student_calendar(email):
	"""Add the requesting student as a Google Calendar attendee on every
	upcoming class in their timetable, using whichever email (personal or
	official) they choose. No per-student Google OAuth is needed — invites
	are sent from the single already-authorized Google Calendar account,
	so this scales to any number of students."""
	student = _get_student_for_session_user()

	allowed_emails = {
		e for e in [student.email, student.official_email_id, student.personal_email] if e
	}
	if email not in allowed_emails:
		frappe.throw("You can only sync using your own registered email address.")

	_ensure_google_calendar_ready()

	full_name = " ".join(filter(None, [student.first_name, student.last_name]))
	contact_name = _get_or_create_contact_for_email(email, full_name)

	course_offerings = _get_enrolled_course_offerings(student.name)
	if not course_offerings:
		return {"synced": 0, "failed": 0, "message": "No enrolled courses found."}

	today = frappe.utils.getdate()
	schedule_names = frappe.get_all(
		"Time Table",
		filters=[
			["course_offering", "in", list(course_offerings)],
			["schedule_date", ">=", str(today)],
			["docstatus", "<", 2],
		],
		pluck="name",
		limit_page_length=0,
	)

	return _add_contact_to_time_tables(schedule_names, contact_name, "Student Calendar Sync Failed")


def _error_text(exc):
	return frappe.utils.strip_html(str(exc)).strip() or exc.__class__.__name__


def _add_contact_to_time_tables(schedule_names, contact_name, error_title):
	"""Returns {"synced", "failed", "error"} — `error` is the first failure
	reason, so the portal can show why classes could not be synced."""
	synced, failed, first_error = 0, 0, None
	for tt_name in schedule_names:
		try:
			tt = frappe.get_doc("Time Table", tt_name)

			if not tt.linked_google_event:
				sync_time_table_to_google_calendar(tt, raise_error=True)
				tt.reload()

			if not tt.linked_google_event:
				failed += 1
				continue

			event = frappe.get_doc("Event", tt.linked_google_event)
			already_added = any(
				p.reference_doctype == "Contact" and p.reference_docname == contact_name
				for p in event.event_participants
			)
			if not already_added:
				event.add_participant("Contact", contact_name)
				event.set_participants_email()
				event.save(ignore_permissions=True)
			synced += 1
		except Exception as e:
			failed += 1
			first_error = first_error or _error_text(e)
			frappe.log_error(message=frappe.get_traceback(), title=error_title)

	return {"synced": synced, "failed": failed, "error": first_error}


def _get_faculty_for_session_user():
	from slcm.utils.faculty_portal import get_faculty_name

	faculty_name = get_faculty_name()
	if not faculty_name:
		frappe.throw("No faculty record found for your account.")
	return frappe.get_doc("Faculty", faculty_name)


def _get_faculty_upcoming_schedule_names(faculty_name):
	"""Upcoming Time Table entries the faculty teaches — as instructor or via
	a Course Offering assigned to them."""
	course_offerings = frappe.get_all(
		"Course Offering", filters={"faculty": faculty_name}, pluck="name", ignore_permissions=True
	)

	today = str(frappe.utils.getdate())
	base_filters = [["schedule_date", ">=", today], ["docstatus", "<", 2]]
	schedule_names = set(
		frappe.get_all(
			"Time Table",
			filters=base_filters + [["instructor", "=", faculty_name]],
			pluck="name",
			limit_page_length=0,
			ignore_permissions=True,
		)
	)
	if course_offerings:
		schedule_names.update(
			frappe.get_all(
				"Time Table",
				filters=base_filters + [["course_offering", "in", course_offerings]],
				pluck="name",
				limit_page_length=0,
				ignore_permissions=True,
			)
		)
	return sorted(schedule_names)


@frappe.whitelist()
def get_faculty_sync_classes():
	"""List the upcoming classes `sync_faculty_calendar` would sync, so the
	portal can sync them in batches and show progress."""
	faculty = _get_faculty_for_session_user()
	_ensure_google_calendar_ready()
	return {"names": _get_faculty_upcoming_schedule_names(faculty.name)}


@frappe.whitelist()
def sync_faculty_calendar(email, schedule_names=None):
	"""Add the requesting faculty member as a Google Calendar attendee on every
	upcoming class they teach — Time Table entries where they are the
	instructor or that belong to a Course Offering assigned to them.

	`schedule_names` (JSON list) limits the run to that batch; names outside
	the faculty's own upcoming classes are ignored."""
	faculty = _get_faculty_for_session_user()

	allowed_emails = {e for e in [faculty.email, faculty.official_email_id] if e}
	if email not in allowed_emails:
		frappe.throw("You can only sync using your own registered email address.")

	_ensure_google_calendar_ready()

	full_name = " ".join(filter(None, [faculty.first_name, faculty.last_name]))
	contact_name = _get_or_create_contact_for_email(email, full_name)

	names = _get_faculty_upcoming_schedule_names(faculty.name)
	if schedule_names is not None:
		requested = set(frappe.parse_json(schedule_names) or [])
		names = [n for n in names if n in requested]

	if not names:
		return {"synced": 0, "failed": 0, "message": "No upcoming classes found."}

	return _add_contact_to_time_tables(names, contact_name, "Faculty Calendar Sync Failed")


def delete_linked_google_event(doc, method=None):
	"""Remove the linked Event (and its Google Calendar entry) when the Time
	Table entry is deleted."""
	if not doc.linked_google_event or not frappe.db.exists("Event", doc.linked_google_event):
		return

	try:
		frappe.delete_doc("Event", doc.linked_google_event, ignore_permissions=True, force=True)
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(), title="Time Table Google Calendar Event Deletion Failed"
		)
