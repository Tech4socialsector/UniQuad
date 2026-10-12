# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""Attendance lock.

Faculty can change a session's attendance only until `attendance_lock_hours`
(Attendance Settings, default 24) after the session ends. After that the
session is locked: Student Attendance saves, the faculty-portal save, the
Student Attendance Tool and RFID activation are all refused.

AAD can reopen a locked session from its Time Table entry; it stays open
until AAD locks it again by hand. Every reopen / re-lock is written to
Attendance Reopen Log (who, when, reason, notice) and the faculty is notified.

System Manager / Administrator are never locked out, and the RFID pipeline
sets `doc.flags.ignore_attendance_lock` because late biometric taps are
reconciled by the system, not edited by faculty.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, format_datetime, get_datetime, getdate, now_datetime, to_timedelta

DEFAULT_LOCK_HOURS = 24
LOCK_EXEMPT_ROLES = {"System Manager"}
REOPEN_ROLES = {"AAD", "System Manager"}

# Attendance Session fields needed to work out its lock state
SESSION_LOCK_FIELDS = [
	"name",
	"session_date",
	"session_start_time",
	"session_end_time",
	"attendance_reopened",
	"reopened_by",
	"reopened_on",
	"reopen_reason",
]

# Changing any of these on a locked session counts as an attendance edit
# (they decide the hours each student is credited with).
SESSION_GUARDED_FIELDS = (
	"session_date",
	"session_start_time",
	"session_end_time",
	"duration_hours",
	"session_status",
)

DATETIME_FORMAT = "dd MMM yyyy, hh:mm a"


def get_lock_hours():
	hours = cint(frappe.db.get_single_value("Attendance Settings", "attendance_lock_hours"))
	return hours if hours > 0 else DEFAULT_LOCK_HOURS


def get_session_end(session_date, end_time=None, start_time=None):
	"""When the session finished: its date + end time (start time if the end
	time is missing, end of that day if both are)."""
	if not session_date:
		return None
	day_start = get_datetime(getdate(session_date))
	time = end_time or start_time
	if time:
		return day_start + to_timedelta(time)
	return day_start + timedelta(days=1)


def compute_lock_state(session, now=None, lock_hours=None):
	"""Lock state of an Attendance Session (doc or dict with SESSION_LOCK_FIELDS).

	locked     - faculty may not change attendance right now
	past_lock  - the lock time has passed (locked unless reopened)
	reopened   - AAD has reopened it and not locked it again
	"""
	lock_hours = lock_hours or get_lock_hours()
	end = get_session_end(
		session.get("session_date"), session.get("session_end_time"), session.get("session_start_time")
	)
	lock_at = end + timedelta(hours=lock_hours) if end else None
	past_lock = bool(lock_at and (now or now_datetime()) >= lock_at)
	reopened = bool(cint(session.get("attendance_reopened")))
	return frappe._dict(
		lock_at=lock_at,
		lock_hours=lock_hours,
		past_lock=past_lock,
		reopened=reopened,
		locked=past_lock and not reopened,
		reopened_by=session.get("reopened_by"),
		reopened_on=session.get("reopened_on"),
		reopen_reason=session.get("reopen_reason"),
	)


def get_session_lock_state(session_name):
	row = frappe.db.get_value("Attendance Session", session_name, SESSION_LOCK_FIELDS, as_dict=True)
	if not row:
		return frappe._dict(locked=False, past_lock=False, reopened=False, lock_at=None)
	return compute_lock_state(row)


def is_lock_exempt(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(LOCK_EXEMPT_ROLES & set(frappe.get_roles(user)))


def locked_message(state):
	return _(
		"Attendance for this session was locked on {0}, {1} hours after the session ended. "
		"Contact AAD to reopen it."
	).format(format_datetime(state.lock_at, DATETIME_FORMAT), state.lock_hours)


def assert_session_editable(session, user=None):
	"""Throw unless the current user may change attendance for `session`
	(an Attendance Session name, doc or dict)."""
	if is_lock_exempt(user):
		return
	state = get_session_lock_state(session) if isinstance(session, str) else compute_lock_state(session)
	if state.locked:
		frappe.throw(locked_message(state), title=_("Attendance Locked"))


def assert_date_editable(attendance_date, user=None):
	"""Lock for legacy Student Attendance records with no Attendance Session:
	counted from the end of the attendance date."""
	if is_lock_exempt(user) or not attendance_date:
		return
	state = compute_lock_state(frappe._dict(session_date=attendance_date))
	if state.locked:
		frappe.throw(locked_message(state), title=_("Attendance Locked"))


def get_lock_info_for_portal(session_name):
	"""Lock details shown in the faculty portal's attendance modal."""
	state = get_session_lock_state(session_name)
	info = {
		"locked": bool(state.locked),
		"reopened": bool(state.reopened),
		"lock_at": format_datetime(state.lock_at, DATETIME_FORMAT) if state.lock_at else None,
		"lock_hours": state.get("lock_hours"),
		"reopened_by": None,
		"reopened_on": None,
		"reopen_reason": None,
		"notice": None,
	}
	if state.reopened:
		info["reopened_by"] = _user_full_name(state.reopened_by)
		info["reopened_on"] = format_datetime(state.reopened_on, DATETIME_FORMAT) if state.reopened_on else None
		info["reopen_reason"] = state.reopen_reason
		info["notice"] = frappe.db.get_value(
			"Attendance Reopen Log",
			{"attendance_session": session_name, "action": "Reopened"},
			"notice",
			order_by="action_on desc",
		)
	return info


# ---------------------------------------------------------------------------
# AAD actions (Time Table form buttons)
# ---------------------------------------------------------------------------


def can_manage_lock(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or bool(REOPEN_ROLES & set(frappe.get_roles(user)))


def _assert_can_manage_lock():
	if not can_manage_lock():
		frappe.throw(_("Only AAD can reopen or lock attendance."), frappe.PermissionError)


def _session_for_time_table(time_table):
	return frappe.db.get_value(
		"Attendance Session", {"class_schedule": time_table}, "name", order_by="creation asc"
	)


def _user_full_name(user):
	if not user:
		return None
	return frappe.db.get_value("User", user, "full_name") or user


@frappe.whitelist()
def get_time_table_lock_status(time_table):
	"""Attendance lock state of the session behind a Time Table entry, for
	the Time Table form's headline and AAD buttons."""
	frappe.has_permission("Time Table", "read", time_table, throw=True)

	session_name = _session_for_time_table(time_table)
	if not session_name:
		return {"session": None, "can_manage": can_manage_lock()}

	session = frappe.db.get_value(
		"Attendance Session",
		session_name,
		SESSION_LOCK_FIELDS + ["attendance_marked", "session_status"],
		as_dict=True,
	)
	state = compute_lock_state(session)
	history = frappe.get_all(
		"Attendance Reopen Log",
		filters={"attendance_session": session_name},
		fields=["action", "action_by", "action_on", "reason", "notice"],
		order_by="action_on desc",
		limit=5,
		ignore_permissions=True,
	)
	for row in history:
		row.action_by = _user_full_name(row.action_by)
		row.action_on = format_datetime(row.action_on, DATETIME_FORMAT)

	return {
		"session": session_name,
		"session_status": session.session_status,
		"attendance_marked": cint(session.attendance_marked),
		"locked": state.locked,
		"past_lock": state.past_lock,
		"reopened": state.reopened,
		"lock_at": format_datetime(state.lock_at, DATETIME_FORMAT) if state.lock_at else None,
		"lock_hours": state.lock_hours,
		"reopened_by": _user_full_name(state.reopened_by),
		"reopened_on": format_datetime(state.reopened_on, DATETIME_FORMAT) if state.reopened_on else None,
		"reopen_reason": state.reopen_reason,
		"history": history,
		"can_manage": can_manage_lock(),
	}


@frappe.whitelist()
def reopen_attendance(session, reason, notice=None, notify_faculty=1):
	"""AAD: let faculty change a locked session's attendance again, until
	AAD locks it by hand."""
	_assert_can_manage_lock()
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("A reason is required to reopen attendance."))

	doc = frappe.get_doc("Attendance Session", session)
	state = compute_lock_state(doc)
	if state.reopened:
		frappe.throw(_("Attendance for this session is already reopened."))
	if not state.past_lock:
		frappe.throw(
			_("Attendance is not locked yet. Faculty can still change it until {0}.").format(
				format_datetime(state.lock_at, DATETIME_FORMAT)
			)
		)

	now = now_datetime()
	frappe.db.set_value(
		"Attendance Session",
		doc.name,
		{
			"attendance_reopened": 1,
			"reopened_by": frappe.session.user,
			"reopened_on": now,
			"reopen_reason": reason,
		},
	)
	log = _write_log(doc, "Reopened", reason, notice, now, cint(notify_faculty))
	return {"log": log}


@frappe.whitelist()
def lock_attendance(session, reason=None, notice=None, notify_faculty=1):
	"""AAD: close a reopened session again."""
	_assert_can_manage_lock()

	doc = frappe.get_doc("Attendance Session", session)
	if not cint(doc.attendance_reopened):
		frappe.throw(_("Attendance for this session is not reopened."))

	now = now_datetime()
	frappe.db.set_value(
		"Attendance Session",
		doc.name,
		{
			"attendance_reopened": 0,
			"reopened_by": None,
			"reopened_on": None,
			"reopen_reason": None,
		},
	)
	log = _write_log(doc, "Locked", (reason or "").strip(), notice, now, cint(notify_faculty))
	return {"log": log}


def _session_faculty(doc):
	if doc.instructor:
		return doc.instructor
	if doc.course_offering:
		return frappe.db.get_value("Course Offering", doc.course_offering, "faculty")
	return None


def _write_log(doc, action, reason, notice, when, notify):
	faculty = _session_faculty(doc)
	notice = (notice or "").strip()
	log = frappe.get_doc(
		{
			"doctype": "Attendance Reopen Log",
			"action": action,
			"attendance_session": doc.name,
			"time_table": doc.class_schedule,
			"course_offering": doc.course_offering,
			"session_date": doc.session_date,
			"faculty": faculty,
			"action_by": frappe.session.user,
			"action_on": when,
			"reason": reason,
			"notice": notice,
			"faculty_notified": 0,
		}
	)
	log.insert(ignore_permissions=True)

	if notify and faculty and _notify_faculty(doc, faculty, action, reason, notice):
		frappe.db.set_value("Attendance Reopen Log", log.name, "faculty_notified", 1, update_modified=False)
	return log.name


def _notify_faculty(doc, faculty, action, reason, notice):
	"""Bell notification (and email, per the user's notification settings)."""
	user = frappe.db.get_value("Faculty", faculty, "user_id")
	if not user:
		return False

	course = frappe.db.get_value("Course Offering", doc.course_offering, "course_name") if doc.course_offering else None
	when = frappe.utils.formatdate(doc.session_date, "dd MMM yyyy")
	what = course or doc.course_offering or doc.name
	if action == "Reopened":
		subject = _("Attendance reopened: {0} on {1}").format(what, when)
		body = _("AAD has reopened attendance for this session. You can update it from the Faculty Portal until AAD locks it again.")
	else:
		subject = _("Attendance locked: {0} on {1}").format(what, when)
		body = _("AAD has locked attendance for this session again.")

	parts = [f"<p>{frappe.utils.escape_html(body)}</p>"]
	if reason:
		parts.append(f"<p><b>{_('Reason')}:</b> {frappe.utils.escape_html(reason)}</p>")
	if notice:
		parts.append(f"<p><b>{_('Notice')}:</b> {frappe.utils.escape_html(notice)}</p>")

	try:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": "Attendance Session",
				"document_name": doc.name,
				"subject": subject,
				"email_content": "".join(parts),
				"from_user": frappe.session.user,
			}
		).insert(ignore_permissions=True)
		return True
	except Exception:
		frappe.log_error(title="Attendance Reopen Notification Error")
		return False
