# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import re
import frappe
from frappe.model.document import Document


class PACEProgramme(Document):
	def before_save(self):
		self.set_title()
		self.generate_program_slug()
		self.generate_application_form_link()

	def autoname(self):
		self.set_title()
		if not self.title:
			frappe.throw(frappe._("Title cannot be empty. Please provide Programme Prefix and Programme Name."))
		self.name = self.title

	def set_title(self):
		prefix = (self.programme_prefix or "").strip()
		name = (self.programme_name or "").strip()
		self.title = f"{prefix} {name}".strip()

	def generate_application_form_link(self):
		if self.route:
			# Site-relative (see Programme.generate_application_form_link): an absolute
			# get_url() link breaks login when the portal is opened from another host.
			web_form_route = (
				frappe.db.get_value("Web Form", "PACE Application Form", "route") or "paceadmissions/application-form"
			).strip("/")
			self.application_form_link = f"/{web_form_route}/new?programme={self.route}"

	def generate_program_slug(self):
		if not self.programme_name:
			return

		base_slug = self._slugify(self.programme_name)

		# Check for clash with other PACE Programme records
		existing = frappe.db.get_value(
			"PACE Programme",
			{"route": base_slug, "name": ("!=", self.name)},
			"name"
		)

		if existing:
			# Append the system name (unique) to resolve clash
			self.route = base_slug + "-" + self._slugify(self.name)
		else:
			self.route = base_slug

	@staticmethod
	def _slugify(text):
		slug = text.lower()
		slug = slug.replace("&", "and")
		slug = re.sub(r"[()]", "", slug)
		slug = re.sub(r"[^a-z0-9\s-]", "", slug)
		slug = re.sub(r"[\s-]+", "-", slug)
		return slug.strip("-")


def migrate_existing_programmes():
	programmes = frappe.get_all("PACE Programme", fields=["name", "programme_prefix", "programme_name"])
	for p in programmes:
		prefix = (p.programme_prefix or "").strip()
		name = (p.programme_name or "").strip()
		new_title = f"{prefix} {name}".strip()
		if new_title:
			# Set the title field
			frappe.db.set_value("PACE Programme", p.name, "title", new_title)
			# Rename the document to match the title
			if p.name != new_title:
				print(f"Renaming '{p.name}' to '{new_title}'")
				frappe.rename_doc("PACE Programme", p.name, new_title, force=True)
	frappe.db.commit()
