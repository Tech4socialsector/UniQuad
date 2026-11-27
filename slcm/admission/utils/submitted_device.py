"""The device an applicant used to submit their application (Applicant.submitted_device).

Read from the browser's User-Agent text when the applicant moves their own application out of
Draft. iPads since iPadOS 13 send a Mac User-Agent, so they are counted as Desktop.
"""

import frappe
from frappe.utils import cstr

MOBILE = "Mobile"
TABLET = "Tablet"
DESKTOP = "Desktop"
DEVICES = (MOBILE, TABLET, DESKTOP)
USER_AGENT_MAX_LENGTH = 500


def record_submitted_device(applicant):
	"""Set the device fields when the applicant's own request takes the application out of Draft.

	Staff edits, the payment webhook (Guest) and scheduled jobs are not the applicant's browser,
	so they leave the fields alone.
	"""
	before = applicant.get_doc_before_save()
	if not before or (before.status or "").strip() != "Draft" or (applicant.status or "").strip() == "Draft":
		return
	if not _is_applicant_request(applicant):
		return
	user_agent = cstr(frappe.request.headers.get("User-Agent"))[:USER_AGENT_MAX_LENGTH]
	applicant.submitted_device = device_from_user_agent(user_agent)
	applicant.submitted_user_agent = user_agent or None


def device_from_user_agent(user_agent):
	"""Mobile, Tablet or Desktop for a User-Agent text; None when there is none."""
	ua = cstr(user_agent).lower()
	if not ua:
		return None
	if "ipad" in ua or "tablet" in ua or ("android" in ua and "mobile" not in ua):
		return TABLET
	if "mobi" in ua or "iphone" in ua or "android" in ua:
		return MOBILE
	return DESKTOP


def _is_applicant_request(applicant):
	if not getattr(frappe.local, "request", None):
		return False
	user = frappe.session.user
	if not user or user == "Guest":
		return False
	return user in {applicant.owner, applicant.get("email"), applicant.get("user_id")}
