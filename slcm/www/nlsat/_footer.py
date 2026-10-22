"""
Footer partial for the NLSAT portal layout (www/nlsat/admission_base.html).

_footer.html is included by the layout, not served as a page. Its data comes from
get_nlsat_footer_context(), exposed to Jinja through the `jinja.methods` hook.
"""

import frappe

# platform → (Font Awesome icon class, brand colour)
SOCIAL_ICONS = {
	"facebook": ("fa-brands fa-facebook", "#1877F2"),
	"instagram": ("fa-brands fa-instagram", "#E4405F"),
	"x": ("fa-brands fa-x-twitter", "#000000"),
	"linkedin": ("fa-brands fa-linkedin", "#0077b5"),
	"youtube": ("fa-brands fa-youtube", "#FF0000"),
	"whatsapp": ("fa-brands fa-whatsapp", "#25D366"),
	"telegram": ("fa-brands fa-telegram", "#229ED9"),
	"threads": ("fa-brands fa-threads", "#000000"),
	"pinterest": ("fa-brands fa-pinterest", "#E60023"),
	"tiktok": ("fa-brands fa-tiktok", "#000000"),
}


def get_context(context):
	# Partial only — /nlsat/_footer must not render as a page
	raise frappe.PageDoesNotExistError


def _val(obj, key):
	if not obj:
		return None
	return obj.get(key) if hasattr(obj, "get") else getattr(obj, key, None)


def _social_icon(platform):
	p = (platform or "").lower()
	if "twitter" in p:
		p = "x"
	return SOCIAL_ICONS.get(p, ("", "inherit"))


def get_nlsat_footer_context(portal_config=None, institution_logo="", admission_footer=None, pace_footer=None):
	"""Values the footer needs: logo, link columns for the user's portal, social links, bottom bar."""
	pc = portal_config or {}
	user = frappe.session.user if frappe.session else ""

	has_applicant = bool(frappe.db.get_value("Has Role", {"parent": user, "role": "Applicant"}, "role"))
	has_pace = bool(frappe.db.get_value("Has Role", {"parent": user, "role": "PACE Applicant"}, "role"))
	show_pace_only = has_pace and not has_applicant

	configured_links = _val(pc, "social_links") or []
	social_links = []
	for link in configured_links:
		if not _val(link, "is_active"):
			continue
		platform = _val(link, "platform") or ""
		icon, color = _social_icon(platform)
		if icon:
			social_links.append(frappe._dict(platform=platform, url=_val(link, "url"), icon=icon, color=color))

	return frappe._dict(
		logo=institution_logo or "",
		title=_val(pc, "portal_title") or "Admissions",
		powerd_by=_val(pc, "powerd_by") or "boscosoft",
		columns=(pace_footer if show_pace_only else admission_footer) or [],
		# the icon column keeps its width whenever links are configured, even if none are active
		show_social=bool(configured_links),
		social_links=social_links,
		year=frappe.utils.nowdate()[:4],
	)
