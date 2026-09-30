import frappe
from frappe.utils import getdate, nowdate

from slcm.api.fee_certificate import get_student_name
from slcm.api.student_portal import get_portal_notifications

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.notifications = []
	context.categories = []
	context.groups = []

	if frappe.session.user == "Guest":
		context.is_guest = True
		return context

	context.is_guest = False
	context.active_page = "notifications"

	student_name = get_student_name()
	if not student_name:
		context.no_student = True
		_set_nav_defaults(context)
		return context

	context.no_student = False

	try:
		student = frappe.get_doc("Student Master", student_name)
		_set_student_nav(context, student)

		# Same feed as the bell icon, so the page and the dropdown always agree.
		notifications = get_portal_notifications().get("notifications") or []
		context.notifications = notifications
		context.groups = _group_by_date(notifications)
		categories = []
		for n in notifications:
			if n.get("category") and n["category"] not in categories:
				categories.append(n["category"])
		context.categories = [
			{"name": c, "count": sum(1 for n in notifications if n.get("category") == c)} for c in categories
		]
	except Exception as e:
		frappe.log_error(f"Notifications portal error: {e}", "Student Portal")
		context.portal_error = str(e)
		_set_nav_defaults(context)

	return context


_GROUP_ORDER = ("Upcoming", "Today", "This week", "Earlier")


def _group_by_date(notifications):
	"""Split the feed into Upcoming / Today / This week / Earlier, each with a relative label."""
	today = getdate(nowdate())
	buckets = {g: [] for g in _GROUP_ORDER}
	for n in notifications:
		try:
			d = getdate(n.get("date")) if n.get("date") else None
		except Exception:
			d = None
		delta = (d - today).days if d else None
		if delta is None:
			group, when = "Earlier", ""
		elif delta > 0:
			group = "Upcoming"
			when = "Tomorrow" if delta == 1 else f"In {delta} days"
		elif delta == 0:
			group, when = "Today", "Today"
		elif delta >= -6:
			group = "This week"
			when = "Yesterday" if delta == -1 else f"{-delta} days ago"
		else:
			group = "Earlier"
			when = d.strftime("%d %b %Y")
		n["when"] = when
		n["_delta"] = delta if delta is not None else -99999
		# The date already shows on the right — don't repeat it in the subtitle
		date_txt = d.strftime("%d %b %Y") if d else ""
		parts = [p for p in (n.get("subtitle") or "").split(" · ") if p and p != date_txt]
		n["page_subtitle"] = " · ".join(parts)
		buckets[group].append(n)

	# Upcoming: soonest first; everything else: newest first
	buckets["Upcoming"].sort(key=lambda n: n["_delta"])
	for g in ("Today", "This week", "Earlier"):
		buckets[g].sort(key=lambda n: n["_delta"], reverse=True)
	return [{"label": g, "entries": buckets[g]} for g in _GROUP_ORDER if buckets[g]]


def _set_student_nav(context, student):
	full_name = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))
	context.student_name = full_name or student.name
	context.student_id = student.registration_id or student.name
	context.student_photo = student.passport_size_photo or ""
	context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
	context.programme_name = frappe.db.get_value("Batch", student.programme, "cohort_name") or student.programme or ""
	context.department = student.department or ""
	context.batch_year = student.batch_year or ""


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
