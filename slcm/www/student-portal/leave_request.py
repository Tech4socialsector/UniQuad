import frappe
from frappe.utils import today, date_diff

no_cache = 1


def get_context(context):
	context.no_cache = 1

	if frappe.session.user == "Guest":
		context.is_guest = True
		return context

	context.is_guest = False
	context.active_page = "leave_request"

	student_name = _get_student_name()
	if not student_name:
		context.no_student = True
		_set_nav_defaults(context)
		context.leave_requests = []
		return context

	context.no_student = False

	try:
		student = frappe.get_doc("Student Master", student_name)
		_set_student_nav(context, student)

		leave_requests = frappe.get_all(
			"Student Leave Applications",
			filters={"student": student_name},
			fields=[
				"name", "from_date", "to_date", "total_leave_days",
				"reason", "status", "submitted_on",
				"admin_remarks", "reviewed_on",
			],
			order_by="creation desc",
			limit=50,
			ignore_permissions=True,
		)

		context.leave_requests  = leave_requests
		context.total_count     = len(leave_requests)
		context.pending_count   = sum(1 for r in leave_requests if r.status == "Pending")
		context.approved_count  = sum(1 for r in leave_requests if r.status == "Approved")
		context.rejected_count  = sum(1 for r in leave_requests if r.status == "Rejected")

	except Exception as e:
		frappe.log_error(f"Leave Request portal error: {e}", "Student Portal")
		context.portal_error = str(e)
		_set_nav_defaults(context)
		context.leave_requests = []

	return context


@frappe.whitelist()
def submit_leave_request(from_date, to_date, reason):
	student_name = _get_student_name()
	if not student_name:
		frappe.throw("Student record not found")

	if not from_date or not to_date:
		frappe.throw("Please select valid dates.")

	days = date_diff(to_date, from_date) + 1
	if days <= 0:
		frappe.throw("To Date must be on or after From Date.")

	student = frappe.get_doc("Student Master", student_name)
	full_name = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))

	doc = frappe.get_doc({
		"doctype": "Student Leave Applications",
		"student": student_name,
		"student_name": full_name or student_name,
		"from_date": from_date,
		"to_date": to_date,
		"total_leave_days": days,
		"reason": reason,
		"status": "Pending",
		"submitted_on": today(),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"name": doc.name, "days": days}


def _get_student_name():
	user = frappe.session.user
	name = frappe.db.get_value("Student Master", {"user": user}, "name")
	if not name:
		name = frappe.db.get_value("Student Master", {"email": user}, "name")
	if not name:
		name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
	if name:
		# Auto-link the user field so future lookups hit the faster index
		try:
			current_user = frappe.db.get_value("Student Master", name, "user")
			if not current_user:
				frappe.db.set_value("Student Master", name, "user", user, update_modified=False)
		except Exception:
			pass
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
