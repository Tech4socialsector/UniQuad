"""Student-portal endpoints for Fee Certificates (Services & Requests → Fee Certificate)."""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, getdate, now_datetime, today

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import get_purpose_options


@frappe.whitelist()
def generate_certificate(purpose, academic_year):
	"""Create (or reuse) the student's Fee Certificate Request for this purpose
	and academic year, and return its name for download_certificate."""
	student_name = get_student_name()
	if not student_name:
		frappe.throw(_("Student record not found"))

	student = frappe.get_doc("Student Master", student_name)
	if academic_year not in [ay.name for ay in student_academic_years(student)]:
		frappe.throw(_("Please select a valid Academic Year."))

	option = next((p for p in get_purpose_options() if p["purpose"] == purpose), None)
	if not option:
		frappe.throw(_("Please select a valid purpose."))
	_check_fully_paid(student_name, option)

	name = frappe.db.get_value(
		"Fee Certificate Request",
		{
			"student": student_name,
			"purpose": purpose,
			"from_academic_year": academic_year,
			"status": ["!=", "Cancelled"],
		},
		"name",
	)
	if name:
		doc = frappe.get_doc("Fee Certificate Request", name)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Fee Certificate Request",
				"student": student_name,
				"purpose": purpose,
				"from_academic_year": academic_year,
				# Only affects students who actually have a waiver on their demands.
				"has_scholarship": 1,
				"remarks": _("Downloaded by the student from the student portal."),
			}
		)
		doc.insert(ignore_permissions=True)

	doc.db_set({"status": "Generated", "generated_on": now_datetime()})
	frappe.db.commit()
	return doc.name


@frappe.whitelist()
def download_certificate(name):
	"""Stream the certificate PDF — only for the logged-in student's own request."""
	student_name = get_student_name()
	request = frappe.get_doc("Fee Certificate Request", name)
	if not student_name or request.student != student_name or request.status == "Cancelled":
		raise frappe.PermissionError
	option = next((p for p in get_purpose_options() if p["purpose"] == request.purpose), None)
	if option:
		_check_fully_paid(student_name, option)

	from slcm.slcm.doctype.fee_certificate_request.fee_certificate_request import certificate_file

	# The staff-edited PDF when one was uploaded, else the generated certificate.
	filename, content, response_type = certificate_file(request, "pdf")
	frappe.local.response.update(filename=filename, filecontent=content, type=response_type)


def outstanding_fee(student_name):
	"""Total still to be paid across the student's (non-cancelled) Fee Demands."""
	amounts = frappe.get_all(
		"Fee Demand",
		filters={"student": student_name, "status": ["!=", "Cancelled"]},
		pluck="outstanding_amount",
	)
	return sum(flt(a) for a in amounts)


def _check_fully_paid(student_name, option):
	if not option.get("require_full_payment"):
		return
	outstanding = outstanding_fee(student_name)
	if outstanding > 0:
		frappe.throw(
			_("{0} can be downloaded only after your fees are fully paid. Outstanding amount: {1}").format(
				option["purpose"], fmt_money(outstanding, currency="INR")
			),
			title=_("Fees Pending"),
		)


def student_academic_years(student):
	"""Academic Years from the student's batch start onward, newest first."""
	filters = {}
	if student.academic_year and frappe.db.exists("Academic Year", student.academic_year):
		start = frappe.db.get_value("Academic Year", student.academic_year, "year_start_date")
		if start:
			filters["year_start_date"] = [">=", start]
	return frappe.get_all(
		"Academic Year",
		filters=filters,
		fields=["name", "academic_year_name", "year_start_date", "year_end_date"],
		order_by="year_start_date desc",
	)


def default_academic_year(years):
	now = getdate(today())
	for ay in years:
		if ay.year_start_date and ay.year_end_date and getdate(ay.year_start_date) <= now <= getdate(ay.year_end_date):
			return ay.name
	return years[0].name if years else ""


def get_student_name():
	user = frappe.session.user
	for field in ("user", "email", "official_email_id"):
		name = frappe.db.get_value("Student Master", {field: user}, "name")
		if name:
			return name
	return None
