"""API gate for website users (applicants, students, parents) — runs before every request.

Frappe lets any logged-in user call any whitelisted method, and applicants register themselves,
so admission staff actions were reachable from the internet. This gate closes that by default:

1. Website users may call admission / offer / fee server methods only if a portal page uses them
   (WEBSITE_ADMISSION_METHODS). Staff (System Users) are not affected.
2. Accounts whose only roles are Applicant / PACE Applicant also cannot use Frappe's generic
   document-write APIs (/api/resource writes, frappe.client.save, savedocs, run_doc_method, ...);
   every portal write goes through a dedicated endpoint that checks ownership.

Blocked calls are logged to the "admission_api_guard" log. Setting `admission_api_guard: "log"` in
site_config.json turns enforcement off (log only) without a deploy.
"""

import re

import frappe

from slcm.security.access import is_applicant_only

# Server methods under these prefixes are staff-only unless a portal page uses them.
STAFF_PREFIXES = (
	"slcm.admission.",
	"slcm.admission_cancel_api.",
	"slcm.api.service.offer_service.",
	"slcm.api.service.fee_service.",
	"slcm.api.service.application_fee_service.",
	"slcm.api.service.applicant_to_student.",
	"slcm.api.refund_dashboard.",
	"slcm.api.test_admission_emails.",
	"slcm.payment.",
	"slcm.www.",
	"slcm.slcm.api.",
	# Desk pages (term results, transcripts, re-exam, publish, ...). Only desk JS calls these;
	# students/parents must never reach them (they return every student's marks).
	"slcm.slcm.page.",
)

# Methods under STAFF_PREFIXES that the website pages (www/, web forms, templates) call.
WEBSITE_ADMISSION_METHODS = frozenset({
	"slcm.admission.api.profile.update_profile",
	"slcm.admission.api.profile.update_user_profile",
	"slcm.admission.api.profile.get_user_profile_data",
	"slcm.admission.api.seat.handle_seat_action",
	"slcm.admission.doctype.applicant.applicant.ensure_application_form_pdf_for_applicant",
	"slcm.admission.doctype.entrance_test_list.entrance_test_list.generate_and_store_admit_card",
	"slcm.admission.doctype.entrance_test_list.entrance_test_list.get_applicant_preferences",
	"slcm.admission.doctype.scholarship_application.scholarship_application.create_scholarship_application",
	"slcm.admission.doctype.scholarship_application.scholarship_application.get_applicant_details",
	"slcm.admission.doctype.scholarship_application.scholarship_application.get_eligible_scholarship_schemes",
	"slcm.admission.doctype.scholarship_application.scholarship_application.get_original_fee_amount",
	"slcm.admission.utils.web.download_admit_card",
	"slcm.admission.utils.web.download_application",
	"slcm.admission.utils.web.download_offer_letter",
	"slcm.admission.utils.web.download_receipt",
	"slcm.admission.utils.web.download_refund_receipt",
	"slcm.admission.utils.web.get_offer_list",
	"slcm.admission.utils.web.get_portal_notifications",
	"slcm.admission.utils.web.get_public_announcements",
	"slcm.admission.utils.web.get_stage_tracker_data",
	"slcm.admission.utils.web.mark_notifications_read",
	"slcm.admission.utils.web.mark_portal_announcement_read",
	"slcm.admission.web_form.applicant_form.applicant_form.check_eligibility",
	"slcm.admission.web_form.applicant_form.applicant_form.city_query",
	"slcm.admission.web_form.applicant_form.applicant_form.download_portal_application_fee_receipt",
	"slcm.admission.web_form.applicant_form.applicant_form.get_applicant_programs_already_applied",
	"slcm.admission.web_form.applicant_form.applicant_form.get_open_programmes",
	"slcm.admission.web_form.applicant_form.applicant_form.get_portal_shell_data",
	"slcm.admission.web_form.applicant_form.applicant_form.get_program_portal_derivatives",
	"slcm.admission.web_form.applicant_form.applicant_form.pop_multiprogram_profile_copy",
	"slcm.admission.web_form.applicant_form.applicant_form.portal_application_fee_receipt_ready",
	"slcm.admission.web_form.applicant_form.applicant_form.save_applicant_draft",
	"slcm.admission.web_form.applicant_form.applicant_form.state_belongs_to_country",
	"slcm.admission.web_form.applicant_form.applicant_form.state_query",
	"slcm.admission.web_form.applicant_form.applicant_form.submit_applicant",
	"slcm.admission.web_form.applicant_form.applicant_form.switch_applicant_program",
	"slcm.admission.web_form.applicant_form.applicant_form.validate_new_application_access",
	"slcm.admission_cancel_api.get_refund_policies",
	"slcm.admission_cancel_api.submit_admission_cancellation",
	"slcm.api.service.application_fee_service.get_application_fee_details",
	"slcm.api.service.fee_service.create_application_fee_razorpay_order",
	"slcm.api.service.fee_service.log_application_fee_payment_failure",
	"slcm.api.service.fee_service.log_payment_failure",
	"slcm.api.service.fee_service.verify_application_fee_payment",
	"slcm.api.service.offer_service.accept_offer",
	"slcm.api.service.offer_service.create_offer_razorpay_order",
	"slcm.api.service.offer_service.get_offer_details",
	"slcm.api.service.offer_service.reject_applicant_other_offer",
	"slcm.api.service.offer_service.reject_offer",
	"slcm.api.service.offer_service.verify_offer_payment",
	"slcm.www.application_form.index.check_portal_eligibility",
	"slcm.www.application_form.index.download_applicant_receipt",
	"slcm.www.application_form.index.get_application_fee_receipt",
	"slcm.www.application_form.index.get_cities_for_state",
	"slcm.www.application_form.index.get_states_for_country",
	"slcm.www.application_form.index.save_form",
	"slcm.www.nlsat.eligibility.entrance_test_seat_allocation.download_admit_card",
	"slcm.www.nlsat.eligibility.entrance_test_seat_allocation.save_provider",
	"slcm.www.nlsat.eligibility.interview_management.save_attendance_confirmation",
	"slcm.www.nlsat.eligibility.interview_management.save_feedback",
})

# Frappe's generic write APIs, closed to applicant-only accounts.
GENERIC_WRITE_METHODS = frozenset({
	"frappe.client.set_value",
	"frappe.client.save",
	"frappe.client.insert",
	"frappe.client.insert_many",
	"frappe.client.submit",
	"frappe.client.cancel",
	"frappe.client.delete",
	"frappe.client.bulk_update",
	"frappe.client.rename_doc",
	"frappe.desk.form.save.savedocs",
	"frappe.desk.form.save.cancel",
	"frappe.desk.reportview.delete_items",
	"frappe.desk.reportview.delete_bulk",
	"frappe.model.workflow.apply_workflow",
	"frappe.model.workflow.bulk_workflow_approval",
	"run_doc_method",
	"runserverobj",
	"frappe.handler.run_doc_method",
	"frappe.desk.form.utils.remove_attach",
	"frappe.model.rename_doc.update_document_title",
})

_METHOD_PATH = re.compile(r"^/api/(?:v1/|v2/)?method/(.+?)/?$")
_DOC_WRITE_PATH = re.compile(r"^/api/(?:v1/)?resource/|^/api/v2/document/")


def guard():
	request = getattr(frappe.local, "request", None)
	if not request:
		return
	user = frappe.session.user
	if not user or user == "Guest":
		return  # Frappe only lets guests call allow_guest methods
	if frappe.get_cached_value("User", user, "user_type") != "Website User":
		return  # desk users: DocPerm and per-method checks apply

	path = request.path or ""
	method = (frappe.form_dict.get("cmd") or "").strip()
	if not method:
		m = _METHOD_PATH.match(path)
		method = m.group(1) if m else ""

	reason = None
	if method.startswith(STAFF_PREFIXES) and method not in WEBSITE_ADMISSION_METHODS:
		reason = "staff-only admission method"
	elif path.startswith("/api/v2/mcp"):
		reason = "MCP endpoint"
	elif is_applicant_only(user):
		if method in GENERIC_WRITE_METHODS or "/" in method:
			reason = "generic document write"
		elif _DOC_WRITE_PATH.match(path) and request.method != "GET":
			reason = "document REST write"

	if not reason:
		return
	frappe.logger("admission_api_guard").warning(
		{"user": user, "method": method, "path": path, "http": request.method, "reason": reason}
	)
	if frappe.conf.get("admission_api_guard") == "log":
		return
	frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
