"""Placeholder filling for user-written email text, without running Jinja on it.

Rendering user text with frappe.render_template lets it call frappe.db / frappe.get_doc inside
the template sandbox; here only {{ name }} / {{ doc.field }} placeholders are replaced, with
HTML-escaped values, and nothing else in the text is evaluated.
"""

import re

from frappe.utils import escape_html

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\}\}")
CONTENT_TOKEN = "@@SLCM_CUSTOM_CONTENT@@"


def fill_placeholders(text, args):
	def lookup(match):
		value = args
		for part in match.group(1).split("."):
			value = value.get(part) if hasattr(value, "get") else getattr(value, part, None)
			if value is None:
				return ""
		return escape_html(str(value))

	out = _PLACEHOLDER.sub(lookup, text or "")
	# Any remaining template syntax is shown as text, never evaluated.
	return out.replace("{%", "&#123;%").replace("{{", "&#123;&#123;").replace("{#", "&#123;#")


def render_custom_email(wrap, custom_content, args):
	"""wrap(content) builds the trusted HTML frame (which may itself use Jinja); the custom
	content is filled separately and dropped into the rendered frame."""
	import frappe

	frame = frappe.render_template(wrap(CONTENT_TOKEN), args)
	return frame.replace(CONTENT_TOKEN, fill_placeholders(custom_content, args))
