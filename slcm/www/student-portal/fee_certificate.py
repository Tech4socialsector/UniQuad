import frappe

from slcm.api.fee_certificate import default_academic_year, get_student_name, outstanding_fee, student_academic_years
from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import get_purpose_options

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.fc_purposes = []
	context.fc_academic_years = []
	context.fc_default_academic_year = ""
	context.fc_outstanding = 0

	if frappe.session.user == "Guest":
		context.is_guest = True
		return context

	context.is_guest = False
	context.active_page = "fee_certificate"

	student_name = get_student_name()
	if not student_name:
		context.no_student = True
		_set_nav_defaults(context)
		return context

	context.no_student = False

	try:
		student = frappe.get_doc("Student Master", student_name)
		_set_student_nav(context, student)

		context.fc_purposes = get_purpose_options()
		context.fc_outstanding = outstanding_fee(student_name)
		context.fc_academic_years = student_academic_years(student)
		context.fc_default_academic_year = default_academic_year(context.fc_academic_years)
	except Exception as e:
		frappe.log_error(f"Fee Certificate portal error: {e}", "Student Portal")
		context.portal_error = str(e)
		_set_nav_defaults(context)

	return context


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
