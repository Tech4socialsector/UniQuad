import html
import re

import frappe
from frappe.utils import add_days, getdate, nowdate

no_cache = 1

PREVIEW_CHARS = 240   # characters of plain text shown before "Read more"
NEW_DAYS = 3          # published within this many days → "New"
ARCHIVE_DAYS = 180    # expired announcements kept in the "Past" list (~ one semester)
ARCHIVE_LIMIT = 100   # most past items rendered (paged in the browser)
PAST_PAGE_SIZE = 5    # past items shown before "Show more"
ACTIVE_FETCH = 200    # rows fetched before audience filtering
PAST_FETCH = 400


def get_context(context):
	context.no_cache = 1

	if frappe.session.user == "Guest":
		context.is_guest = True
		return context

	context.is_guest = False
	context.active_page = "announcements"

	student_name = _get_student_name()
	if not student_name:
		context.no_student = True
		_set_nav_defaults(context)
		return context

	context.no_student = False

	try:
		student = frappe.get_doc("Student Master", student_name)
		_set_student_nav(context, student)

		today = getdate(nowdate())
		archive_from = add_days(today, -ARCHIVE_DAYS)

		fields = [
			"name", "title", "content", "announcement_type", "priority",
			"publish_date", "expiry_date", "target_audience",
		]
		base = [["is_active", "=", 1], ["publish_date", "<=", today]]

		# Two separate queries so a long archive can never crowd out active notices
		active_rows = frappe.get_all(
			"Student Announcement",
			filters=base,
			or_filters=[["expiry_date", "is", "not set"], ["expiry_date", ">=", today]],
			fields=fields,
			order_by="publish_date desc, creation desc",
			limit=ACTIVE_FETCH,
			ignore_permissions=True,
		)
		past_rows = frappe.get_all(
			"Student Announcement",
			filters=base + [["expiry_date", "<", today], ["expiry_date", ">=", archive_from]],
			fields=fields,
			order_by="expiry_date desc, creation desc",
			limit=PAST_FETCH,
			ignore_permissions=True,
		)

		visible = [r for r in active_rows + past_rows if _is_for_student(r, student, student_name)]

		priority_icon = {"Urgent": "warning", "Important": "priority_high", "Normal": "campaign"}
		type_icon = {
			"Academic": "school", "Administrative": "admin_panel_settings",
			"Hostel": "hotel", "Placement": "work", "General": "campaign",
		}

		active, past = [], []
		for a in visible:
			a["priority"] = a.priority or "Normal"
			a["announcement_type"] = a.announcement_type or "General"
			a["priority_icon"] = priority_icon.get(a.priority, "campaign")
			a["type_icon"] = type_icon.get(a.announcement_type, "campaign")

			text = _plain_text(a.content)
			a["preview"] = text[:PREVIEW_CHARS].rstrip() + ("…" if len(text) > PREVIEW_CHARS else "")
			a["has_more"] = len(text) > PREVIEW_CHARS
			a["search_text"] = f"{a.title or ''} {text}".lower()

			published = getdate(a.publish_date)
			a["days_ago"] = (today - published).days
			a["is_new"] = a["days_ago"] <= NEW_DAYS

			expiry = getdate(a.expiry_date) if a.expiry_date else None
			a["days_left"] = (expiry - today).days if expiry else None

			if expiry and expiry < today:
				if expiry >= archive_from:
					past.append(a)
			else:
				active.append(a)

		# Urgent → Important → Normal, newest first within each
		rank = {"Urgent": 0, "Important": 1, "Normal": 2}
		active.sort(key=lambda a: (rank.get(a.priority, 3), a["days_ago"]))
		past.sort(key=lambda a: (getdate(a.expiry_date), getdate(a.publish_date)), reverse=True)
		past = past[:ARCHIVE_LIMIT]
		for a in past:
			a["month_label"] = getdate(a.expiry_date).strftime("%B %Y")

		context.announcements = active
		context.past_announcements = past
		context.past_page_size = PAST_PAGE_SIZE
		context.archive_days = ARCHIVE_DAYS
		context.total_count = len(active)
		context.urgent_count = sum(1 for a in active if a.priority == "Urgent")
		context.important_count = sum(1 for a in active if a.priority == "Important")
		context.expiring_count = sum(1 for a in active if a["days_left"] is not None and a["days_left"] <= 7)
		context.categories = sorted({a.announcement_type for a in active})

	except Exception as e:
		frappe.log_error(f"Announcements portal error: {e}", "Student Portal")
		context.portal_error = str(e)
		_set_nav_defaults(context)

	return context


def _plain_text(content):
	"""Editor HTML → one line of text; tags become spaces so paragraphs don't run together."""
	text = re.sub(r"<[^>]+>", " ", content or "")
	return " ".join(html.unescape(text).split())


def _is_for_student(r, student, student_name):
	"""Same audience rules as the notification bell (slcm.api.student_portal)."""
	audience = r.target_audience or "All Students"
	if audience == "All Students":
		return True
	if audience == "Specific Programme(s)":
		targets = frappe.get_all(
			"Announcement Programme Target", filters={"parent": r.name},
			pluck="programme", ignore_permissions=True,
		)
		return student.programme in targets
	if audience == "Specific Batch Year(s)":
		targets = frappe.get_all(
			"Announcement Batch Target", filters={"parent": r.name},
			pluck="batch_year", ignore_permissions=True,
		)
		s_batch = str(student.batch_year or "")
		s_acyr = str(student.academic_year or "")
		return any(str(t) == s_batch or (s_acyr and str(t) == s_acyr) for t in targets)
	if audience == "Specific Student(s)":
		targets = frappe.get_all(
			"Announcement Student Target", filters={"parent": r.name},
			pluck="student", ignore_permissions=True,
		)
		return student_name in targets
	return False


def _get_student_name():
	user = frappe.session.user
	name = frappe.db.get_value("Student Master", {"user": user}, "name")
	if not name:
		name = frappe.db.get_value("Student Master", {"email": user}, "name")
	if not name:
		name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
	return name


def _set_student_nav(context, student):
	full_name = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))
	context.student_name = full_name or student.name
	context.student_id = student.registration_id or student.name
	context.student_photo = student.passport_size_photo or ""
	context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
	context.programme_name = frappe.db.get_value("Batch", student.programme, "cohort_name") or student.programme or ""
	context.department = student.department or ""
	context.batch_year = student.batch_year or ""
	context.academic_year = student.academic_year or ""


def _set_nav_defaults(context):
	user = frappe.session.user
	user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
	context.student_name = (user_doc.full_name if user_doc else "") or user.split("@")[0]
	context.student_id = ""
	context.student_photo = (user_doc.user_image if user_doc else "") or ""
	context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
	context.programme_name = ""
	context.department = ""
	context.batch_year = ""
