# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import re
import frappe
from frappe.model.document import Document


class Programme(Document):

	def autoname(self):
		if not (self.program_code and self.academic_year and self.academic_term):
			frappe.throw(
				frappe._("Programme Code, Academic Year and Academic Term are required to name the Programme.")
			)

		self.name = "-".join([
			self.program_code.strip().upper(),
			self.academic_year.strip(),
			self._slugify(self.academic_term).upper(),
		])

	def before_save(self):
		self.generate_program_slug()
		self.generate_application_form_link()

	def generate_application_form_link(self):
		# Site-relative on purpose: an absolute get_url() link bakes in the host it was saved
		# from (127.0.0.1 / localhost / domain); opened from another host the session cookie
		# is missing and logged-in applicants get sent to the login page.
		web_form_route = (
			frappe.db.get_value("Web Form", "applicant-form", "route") or "admission/application-form"
		).strip("/")
		self.application_form_link = f"/{web_form_route}/new?program={self.program_slug}&foriegn_national=No&nationality=India"
		self.international_application_form_link = f"/{web_form_route}/new?program={self.program_slug}&foriegn_national=Yes"
	def generate_program_slug(self):
		if not self.program_name:
			return

		base_slug = self._slugify(self.program_name)

		# Check for clash with other Programme records
		existing = frappe.db.get_value(
			"Programme",
			{"program_slug": base_slug, "name": ("!=", self.name)},
			"name"
		)

		if existing:
			# Append the system name (unique) to resolve clash
			self.program_slug = base_slug + "-" + self._slugify(self.name)
		else:
			self.program_slug = base_slug

	@staticmethod
	def _slugify(text):
		slug = text.lower()
		slug = slug.replace("&", "and")
		slug = re.sub(r"[()]", "", slug)
		slug = re.sub(r"[^a-z0-9\s-]", "", slug)
		slug = re.sub(r"[\s-]+", "-", slug)
		return slug.strip("-")