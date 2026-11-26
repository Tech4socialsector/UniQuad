"""Registration (set-password) and password-reset emails.

Exactly one email per event. The Email Template is chosen by where the account
belongs:

    NLSAT Domestic      Applicant Portal Config > NLSAT Admission tab
    NLSAT International Applicant Portal Config > International Admission tab
    PACE                Applicant Portal Config > PACE Admission tab
    desk / everyone else System Settings > Welcome / Reset Password Email Template

An empty, deleted or broken portal template falls back to the System Settings one,
and that to Frappe's own email. The link expires after System Settings > Reset
Password Link Expiry Duration.

Users added from the desk with "Send Welcome Email" ticked, and the desk's own
password reset, are sent by Frappe itself with the System Settings templates.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, get_url

from slcm.admission.utils.nlsat_portal import DOMESTIC, INTERNATIONAL, get_applicant_portal_type

PACE = "PACE"
REGISTER = "register"
RESET = "reset"

CONFIG_DOCTYPE = "Applicant Portal Config"
PORTAL_TEMPLATE_FIELDS = {
	DOMESTIC: {REGISTER: "nlsat_register_email_template", RESET: "nlsat_reset_password_template"},
	INTERNATIONAL: {REGISTER: "intl_register_email_template", RESET: "intl_reset_password_template"},
	PACE: {REGISTER: "pace_register_email_template", RESET: "pace_reset_password_template"},
}
SYSTEM_TEMPLATE_FIELDS = {REGISTER: "welcome_email_template", RESET: "reset_password_template"}
# Frappe's own emails (frappe/templates/emails), used when no Email Template applies
FRAPPE_TEMPLATES = {REGISTER: "new_user", RESET: "password_reset"}
FRAPPE_WRAPPER = "templates/emails/auth_email.html"

# A template must use one of these, or the candidate cannot set a password
LINK_VARIABLE = re.compile(r"{{[^}]*\b(link|set_password_link|reset_password_link)\b[^}]*}}")


def send_auth_email(
	user_doc,
	kind: str,
	link: str,
	portal: str | None = None,
	login_url: str | None = None,
	subject: str | None = None,
	default_template: str | None = None,
	system_fallback: bool = True,
) -> str | None:
	"""Send the one registration / password-reset email for `user_doc`.

	link: the set-password / reset link, already on the right domain.
	default_template: email file used when no Email Template applies (Frappe's
	new_user / password_reset by default).
	system_fallback: False skips the System Settings template (FLE has its own email).
	Returns the Email Template name used, or None for the email file."""
	email = AuthEmail(user_doc, kind, link, portal, login_url, subject, default_template, system_fallback)
	return email.send()


def validate_portal_templates(doc) -> None:
	"""Applicant Portal Config validate: each register / reset template set must render
	and contain the set-password link, or candidates could not get into their account."""
	for fields in PORTAL_TEMPLATE_FIELDS.values():
		for field in fields.values():
			if doc.get(field):
				_check_template(_(doc.meta.get_label(field)), doc.get(field))


def get_user_portal(user: str) -> str | None:
	"""The portal whose emails `user` gets: DOMESTIC / INTERNATIONAL / PACE, or None (desk).

	Only website users are portal users. An NLSAT applicant whose portal is not known
	yet is Domestic; an account with both roles is NLSAT (as at sign-in)."""
	if not user or frappe.db.get_value("User", user, "user_type") != "Website User":
		return None
	roles = set(frappe.get_roles(user))
	if "Applicant" in roles:
		return get_applicant_portal_type(user) or DOMESTIC
	if "PACE Applicant" in roles:
		return PACE
	return None


def get_email_templates(kind: str, portal: str | None = None, system_fallback: bool = True) -> list[str]:
	"""Names of the Email Templates to try for `kind` on `portal`, most specific first."""
	names = []
	field = PORTAL_TEMPLATE_FIELDS.get(portal or "", {}).get(kind)
	if field and frappe.get_meta(CONFIG_DOCTYPE).has_field(field):
		names.append(frappe.db.get_single_value(CONFIG_DOCTYPE, field))
	if system_fallback:
		names.append(frappe.db.get_system_setting(SYSTEM_TEMPLATE_FIELDS[kind]))
	return [n for n in dict.fromkeys(names) if n and frappe.db.exists("Email Template", n)]


def get_email_args(user_doc, link: str, portal: str | None, login_url: str | None, subject: str) -> dict:
	"""Variables available to the templates: Frappe's own plus slcm's."""
	from frappe.email.email_body import get_brand_name
	from frappe.utils.user import get_user_fullname

	institution = frappe.db.get_values_from_single(
		["institution_name", "logo", "support_email"], None, "Institution Settings", as_dict=True
	)[0]
	full_name = user_doc.full_name or user_doc.first_name or user_doc.last_name or user_doc.email
	expiry_seconds = cint(frappe.get_system_settings("reset_password_link_expiry_duration"))
	created_by = get_user_fullname(frappe.session.user)

	return {
		# Frappe's own variables (User.send_login_mail / welcome / reset)
		"first_name": user_doc.first_name or user_doc.last_name or "user",
		"user": user_doc.name,
		"title": subject,
		"login_url": login_url or get_url(),
		"created_by": "Administrator" if created_by == "Guest" else created_by,
		"link": link,
		"site_url": get_url(),
		"app_name": get_brand_name() or "Frappe",
		"expiry_minutes": (expiry_seconds // 60) or None,
		# slcm template variables
		"full_name": full_name,
		"candidate_name": full_name,
		"applicant_name": full_name,
		"email": user_doc.email or user_doc.name,
		"set_password_link": link,
		"reset_password_link": link,
		"institution_name": institution.institution_name or "National Law School of India University",
		"logo": institution.logo or "",
		"support_email": institution.support_email or "",
		# "20 minutes" / "24 hours"; empty when links don't expire
		"link_expiry": _describe_expiry(expiry_seconds),
		"link_expiry_hours": round(expiry_seconds / 3600, 1) if expiry_seconds else "",
		"portal": portal or "",
		"doc": user_doc,
	}


class AuthEmail:
	"""One registration / password-reset email: picks the template, then sends."""

	def __init__(self, user_doc, kind, link, portal, login_url, subject, default_template, system_fallback):
		self.user_doc = user_doc
		self.kind = kind
		self.portal = portal
		self.default_template = default_template
		self.system_fallback = system_fallback
		self.subject = subject or (_("Password Reset") if kind == RESET else _registration_subject())
		self.args = get_email_args(user_doc, link, portal, login_url, self.subject)
		self.sender = _session_sender()
		self.template_name = None
		self.content = None

	def send(self) -> str | None:
		if not self.user_doc.enabled:
			return None
		self.pick_template()
		frappe.sendmail(
			recipients=self.user_doc.email,
			sender=self.sender,
			subject=self.subject,
			template=None if self.template_name else (self.default_template or FRAPPE_TEMPLATES[self.kind]),
			content=self.content,
			args=self.args,
			# Email Templates are complete designed emails; Frappe frames only its own files.
			with_container=not self.template_name,
			wrapper=None if (self.template_name or self.default_template) else FRAPPE_WRAPPER,
			now=True,
			retry=3,
			redact_message_after_send=True,
		)
		self.user_doc.flags.email_sent = 1
		return self.template_name

	def pick_template(self) -> None:
		"""Use the first template that renders; a broken one is logged and skipped."""
		for name in get_email_templates(self.kind, self.portal, self.system_fallback):
			sender = _template_sender(name) or self.sender
			email = _render(name, self.args, sender)
			if email:
				self.template_name, self.sender, self.content = name, sender, email.get("message")
				self.subject = email.get("subject") or self.subject
				return


def _check_template(label: str, name: str) -> None:
	"""Throw unless Email Template `name` has the set-password link and renders."""
	template = frappe.get_doc("Email Template", name)
	source = (template.response_html if template.use_html else template.response) or ""
	if not LINK_VARIABLE.search(source):
		frappe.throw(
			_("{0}: Email Template {1} has no {2}. Candidates could not set their password.").format(
				label, frappe.bold(name), "<code>{{ link }}</code>"
			),
			title=_("Set-password link missing from email"),
		)
	sample = frappe._dict(first_name="Candidate", full_name="Candidate", email="candidate@example.com")
	args = get_email_args(sample, get_url("/update-password?key=sample"), None, None, "")
	try:
		template.get_formatted_email(args)
	except Exception as e:
		error = frappe.utils.escape_html(str(e))
		frappe.throw(
			_("{0}: Email Template {1} could not be rendered: {2}").format(label, frappe.bold(name), error),
			title=_("Email Template error"),
		)


def _render(template_name: str, args: dict, sender: str | None) -> dict | None:
	"""Subject and message of the template, or None (logged) when it does not render."""
	try:
		return frappe.get_doc("Email Template", template_name).get_formatted_email(args, sender=sender)
	except Exception:
		frappe.log_error(
			title=f"Email Template '{template_name}' could not be rendered",
			message=frappe.get_traceback(),
		)
		return None


def _session_sender() -> str | None:
	"""The signed-in user's address, as Frappe's own login emails use; None for guests."""
	from frappe.core.doctype.user.user import STANDARD_USERS

	user = frappe.session.user
	return (user not in STANDARD_USERS and frappe.utils.get_formatted_email(user)) or None


def _template_sender(template_name: str) -> str | None:
	"""The Email Account set on the template (custom field Email Template.email_account), else None."""
	if not frappe.get_meta("Email Template").has_field("email_account"):
		return None
	account = frappe.db.get_value("Email Template", template_name, "email_account")
	if not account:
		return None
	return frappe.db.get_value("Email Account", account, "email_id") or account


def _registration_subject() -> str:
	"""Frappe's welcome email subject: the welcome_email hook, else Welcome to <site>."""
	method = frappe.get_hooks("welcome_email")
	if method:
		subject = frappe.get_attr(method[-1])()
		if subject:
			return subject
	site_name = frappe.db.get_default("site_name") or frappe.get_conf().get("site_name")
	return _("Welcome to {0}").format(site_name) if site_name else _("Complete Registration")


def _describe_expiry(seconds: int) -> str:
	if not seconds:
		return ""
	if seconds % 3600 == 0:
		hours = seconds // 3600
		return _("{0} hour").format(hours) if hours == 1 else _("{0} hours").format(hours)
	minutes = max(seconds // 60, 1)
	return _("{0} minute").format(minutes) if minutes == 1 else _("{0} minutes").format(minutes)
