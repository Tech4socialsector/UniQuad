import base64
import io
import os
import tempfile

import frappe
from frappe import _
from frappe.model.document import Document

from slcm.slcm.utils import id_card_render


class IDCardTemplate(Document):
	def validate(self):
		self.validate_fields()
		self.validate_canvas_data()

	def on_update(self):
		# Only one default template per card type.
		if self.is_default:
			frappe.db.sql(
				"""update `tabID Card Template` set is_default = 0
				where card_type = %s and name != %s and is_default = 1""",
				(self.card_type, self.name),
			)

	def validate_fields(self):
		if self.template_creation_mode != "Field Mapping":
			return

		student_meta = frappe.get_meta("Student Master")
		valid_fields = [f.fieldname for f in student_meta.fields]
		valid_fields.extend(["name", "owner", "creation", "modified", "docstatus"])

		special_fields = ["photo", "qrcode", "static_text"]

		for row in self.fields:
			if row.student_fieldname not in special_fields:
				if row.student_fieldname not in valid_fields:
					frappe.throw(
						f"Row {row.idx}: Field '{row.student_fieldname}' does not exist in Student Master."
					)

	def validate_canvas_data(self):
		if self.template_creation_mode != "Drag and Drop":
			return
		if not self.canvas_data:
			frappe.throw(_("Design the card in the designer before saving."), title=_("Empty Design"))
		try:
			data = id_card_render.parse_canvas_data(self.canvas_data)
		except ValueError:
			frappe.throw(_("The saved design is not valid. Pick a starter or reset the design."))

		if not id_card_render.visible_elements(data, "front"):
			frappe.throw(_("The front side of the card is empty."), title=_("Empty Design"))

		unknown = id_card_render.find_unknown_tokens(data)
		if unknown:
			frappe.msgprint(
				_("These placeholders don't match any data field and will print as typed: {0}").format(
					", ".join(frappe.bold(u) for u in unknown)
				),
				title=_("Unknown Fields"),
				indicator="orange",
			)

	@frappe.whitelist()
	def render_preview(self, person=None):
		"""Server-rendered front/back images, exactly as cards will print.

		Works on unsaved changes (the form sends its current state). Without
		a `person`, sample data is used."""
		frappe.has_permission("ID Card Template", "read", throw=True)
		return build_preview(self, person)

	@frappe.whitelist()
	def get_preview(self):
		"""Kept for older callers; returns the preview as HTML."""
		images = build_preview(self)
		return "".join(
			f'<div style="display:inline-block;margin:8px;text-align:center">'
			f'<div class="text-muted small">{side.title()}</div>'
			f'<img src="{images[side]}" style="max-width:420px;border-radius:12px"></div>'
			for side in ("front", "back")
			if images.get(side)
		)


def build_preview(template, person=None):
	card = frappe.new_doc("ID Card Generation")
	card.card_type = template.card_type or "Student"
	card.name = "PREVIEW"
	link = id_card_render.PERSON_LINKS.get(card.card_type)

	if person and link:
		frappe.has_permission(link[1], "read", doc=person, throw=True)
		card.set(link[0], person)
		card._populate_person_fields()
		card._auto_set_issue_date()
		card._auto_set_expiry_date()
		person_doc = card.get_person_doc()
		photo_src = None
	else:
		person = None
		person_doc = id_card_render.apply_sample_to_card(card, template)
		photo_src = id_card_render.SAMPLE_PHOTO

	qr_payload = card.generate_qr_code_string() if person else "SAMPLE ID CARD"
	with tempfile.TemporaryDirectory(prefix="idcard-qr-") as tmp:
		qr_path = os.path.join(tmp, "qr.png")
		with open(qr_path, "wb") as f:
			f.write(id_card_render.make_qr_png(qr_payload))
		images = card.render_card_images(
			template,
			person_doc,
			qr_src=id_card_render.to_src(qr_path),
			photo_src=photo_src,
		)

	result = {side: "data:image/png;base64," + base64.b64encode(png).decode() for side, png in images.items()}
	result["orientation"] = _orientation(images.get("front"))
	result["sample"] = not person
	result["person"] = card.student_name if person else None
	return result


def _orientation(png):
	if not png:
		return "horizontal"
	from PIL import Image

	width, height = Image.open(io.BytesIO(png)).size
	return "vertical" if height > width else "horizontal"
