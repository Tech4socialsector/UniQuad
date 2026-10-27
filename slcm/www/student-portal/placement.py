import frappe
from frappe.utils import nowdatetime
from slcm.slcm.utils.exam_schedule import get_student_programme

no_cache = 1


def get_context(context):
	context.no_cache = 1

	if frappe.session.user == "Guest":
		context.is_guest = True
		return context

	context.is_guest = False
	context.active_page = "placement"

	student_name = _get_student_name()
	if not student_name:
		context.no_student = True
		_set_nav_defaults(context)
		context.opportunities = []
		context.my_applications = []
		return context

	context.no_student = False

	try:
		student = frappe.get_doc("Student Master", student_name)
		_set_student_nav(context, student)

		# ── Placement Profile ──────────────────────────────────────
		profile = None
		try:
			profile = frappe.get_doc("Student Placement Profile", student_name)
		except frappe.DoesNotExistError:
			pass
		context.placement_profile = profile

		# ── Open Opportunities ────────────────────────────────────
		now_str = nowdatetime()
		opportunities = frappe.get_all(
			"Placement Opportunity",
			filters={"status": "Open"},
			fields=[
				"name", "company", "opportunity_type", "compensation",
				"location", "application_start", "application_end",
				"eligibility_criteria", "status",
			],
			order_by="application_end asc",
			ignore_permissions=True,
		)

		# Enrich with company name and check if already applied
		applied_set = {
			a.opportunity for a in frappe.get_all(
				"Placement Application",
				filters={"student": student_name},
				fields=["opportunity"],
				ignore_permissions=True,
			)
		}

		for opp in opportunities:
			opp["company_name"] = (
				frappe.db.get_value("Company", opp.company, "company_name") or opp.company
			)
			opp["already_applied"] = opp.name in applied_set
			opp["is_closed"] = bool(
				opp.application_end and str(opp.application_end) < now_str
			)

		context.opportunities = opportunities
		context.open_count = sum(1 for o in opportunities if not o["is_closed"])

		# ── My Applications ───────────────────────────────────────
		my_apps = frappe.get_all(
			"Placement Application",
			filters={"student": student_name},
			fields=[
				"name", "opportunity", "applied_on",
				"status", "remarks",
			],
			order_by="applied_on desc",
			ignore_permissions=True,
		)
		for app in my_apps:
			opp_data = frappe.db.get_value(
				"Placement Opportunity", app.opportunity,
				["company", "opportunity_type"], as_dict=True,
			) or frappe._dict()
			app["company_name"] = (
				frappe.db.get_value("Company", opp_data.company, "company_name") or opp_data.company or app.opportunity
			)
			app["opportunity_type"] = opp_data.opportunity_type or ""

		context.my_applications = my_apps
		context.applications_count = len(my_apps)
		context.shortlisted_count = sum(1 for a in my_apps if a.status == "Shortlisted")

		# ── Placement Offer ───────────────────────────────────────
		offer = frappe.db.get_value(
			"Placement Offer",
			{"student": student_name},
			["name", "opportunity", "offered_role", "compensation", "offer_status", "decision_date"],
			as_dict=True,
		)
		context.placement_offer = offer

	except Exception as e:
		frappe.log_error(f"Placement portal error: {e}", "Student Portal")
		context.portal_error = str(e)
		_set_nav_defaults(context)
		context.opportunities = []
		context.my_applications = []

	return context


@frappe.whitelist()
def apply_for_opportunity(opportunity, resume_url=""):
	student_name = _get_student_name()
	if not student_name:
		frappe.throw("Student record not found")

	# Check not already applied
	existing = frappe.db.exists(
		"Placement Application", {"student": student_name, "opportunity": opportunity}
	)
	if existing:
		frappe.throw("You have already applied for this opportunity.")

	# Verify opportunity is still open
	opp = frappe.db.get_value(
		"Placement Opportunity", opportunity, ["status", "application_end"], as_dict=True
	)
	if not opp or opp.status != "Open":
		frappe.throw("This opportunity is no longer accepting applications.")

	doc = frappe.get_doc({
		"doctype": "Placement Application",
		"student": student_name,
		"opportunity": opportunity,
		"applied_on": nowdatetime(),
		"resume_used": resume_url or "",
		"status": "Applied",
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"name": doc.name, "status": "Applied"}


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
	context.programme_name = get_student_programme(student.name)
	context.department = student.department or ""
	context.batch_year = student.batch or ""


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
