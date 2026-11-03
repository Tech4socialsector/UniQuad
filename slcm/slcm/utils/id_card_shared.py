"""Shared logic for the ID Card Generation and Student ID Card controllers.

Both doctypes model the same lost/reissue/print/QR/canvas-rendering
lifecycle for a physical ID card, differing only in which "person" doctypes
they support and which link field on ID Card Print Log they populate. This
module holds the one copy of that shared logic so a fix here applies to
both controllers instead of needing to be duplicated by hand.
"""

import io
import json

import frappe
from frappe import _
from frappe.utils import add_years, cint, get_url, now, today
from frappe.utils.file_manager import save_file

from slcm.slcm.utils import id_card_render
from slcm.slcm.utils.exam_schedule import get_student_programme

# Valid card_status transitions. Terminal states map to empty list.
# Where each person type keeps its photo: (doctype, link field on the card, photo field).
PERSON_PHOTO_FIELDS = {
	"Student": ("Student Master", "student", "passport_size_photo"),
	"Faculty": ("Faculty", "faculty", "photo"),
	"Driver": ("SLCM Driver", "driver", "photo"),
}

VALID_STATUS_TRANSITIONS = {
	"Draft": ["Generated", "Cancelled"],
	"Generated": ["Printed", "Cancelled", "Expired"],
	"Printed": ["Cancelled", "Expired"],
	"Error": ["Draft", "Generated", "Cancelled"],
	"Expired": [],
	"Cancelled": [],
}


def hex_to_rgb(hex_color):
	hex_color = hex_color.lstrip("#")
	return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


class IDCardCommonMixin:
	"""Mixin providing the full card lifecycle. Host doctype must set
	`_print_log_linkfield` to the name of the ID Card Print Log field that
	links back to it (e.g. "id_card_generation" or "student_id_card")."""

	_print_log_linkfield = None

	# ------------------------------------------------------------------
	# Frappe lifecycle hooks
	# ------------------------------------------------------------------

	def validate(self):
		# Cache old DB values once to avoid multiple reads in before_save
		if not self.is_new():
			self._old_card_status = frappe.db.get_value(self.doctype, self.name, "card_status")
			self._old_qr_data = frappe.db.get_value(self.doctype, self.name, "qr_code_data")
		else:
			self._old_card_status = None
			self._old_qr_data = None

		self._validate_card_status_transition()

		if not self.expiry_date:
			frappe.throw(
				_(
					"Set the Expiry Date. It could not be worked out from the person's batch or academic year."
				),
				title=_("Expiry Date Missing"),
			)

		# Duplicate active-card check
		if self.card_status != "Cancelled":
			self._validate_no_duplicate_active_card()

	def before_insert(self):
		self._populate_person_fields()
		self._auto_set_issue_date()
		self._auto_set_expiry_date()

	def before_save(self):
		# Regenerate QR only when data actually changed or image is missing
		new_qr_data = self.generate_qr_code_string()
		self.qr_code_data = new_qr_data
		if (
			new_qr_data
			and not self.flags.qr_refreshed
			and (new_qr_data != getattr(self, "_old_qr_data", None) or not self.qr_code_image)
		):
			self.generate_and_save_qr_image()

		self.verification_url = self.generate_verification_url()

		old_status = getattr(self, "_old_card_status", None)

		# Log status change in events child table
		if old_status is not None and self.card_status != old_status:
			self.append(
				"events", {"timestamp": now(), "card_status": self.card_status, "user": frappe.session.user}
			)

		# Sync id_card_issued on Student Master when card is Cancelled
		if (
			old_status is not None
			and old_status != "Cancelled"
			and self.card_status == "Cancelled"
			and self.card_type == "Student"
			and self.student
		):
			self._sync_id_card_issued_on_cancel()

	# ------------------------------------------------------------------
	# Private helpers
	# ------------------------------------------------------------------

	def _validate_card_status_transition(self):
		"""Block invalid status jumps. System Manager bypasses."""
		if self.is_new():
			return
		old_status = getattr(self, "_old_card_status", None)
		if not old_status or old_status == self.card_status:
			return
		if "System Manager" in frappe.get_roles():
			return
		allowed = VALID_STATUS_TRANSITIONS.get(old_status, [])
		if self.card_status not in allowed:
			frappe.throw(
				_("Cannot change ID Card status from '{0}' to '{1}'. Allowed next states: {2}").format(
					old_status, self.card_status, ", ".join(allowed) or _("None")
				)
			)

	def _validate_no_duplicate_active_card(self):
		filters_map = {
			"Student": ("student", self.student),
			"Faculty": ("faculty", self.faculty),
			"Driver": ("driver", self.driver),
		}
		if self.card_type not in filters_map:
			return
		field, value = filters_map[self.card_type]
		if not value:
			return
		existing = frappe.db.exists(
			self.doctype,
			{field: value, "card_status": ["not in", ["Cancelled", "Expired"]], "name": ["!=", self.name]},
		)
		if existing:
			frappe.throw(
				_("Active ID Card {0} already exists for {1} {2}").format(existing, self.card_type, value)
			)

	def _populate_person_fields(self):
		"""Auto-fill card fields from the linked person document on first insert."""
		if self.card_type == "Student" and self.student:
			student = frappe.get_doc("Student Master", self.student)
			self.student_name = f"{student.first_name or ''} {student.get('last_name') or ''}".strip()
			self.email = student.email
			self.phone = student.phone
			if not self.photo:
				self.photo = student.passport_size_photo
			self.batch = student.batch
			self.programme = student.programme_of_study
			self.date_of_birth = self.date_of_birth or student.dob
			self.academic_year = self.academic_year or student.academic_year

		elif self.card_type == "Faculty" and self.faculty:
			faculty = frappe.get_doc("Faculty", self.faculty)
			self.student_name = f"{faculty.first_name} {faculty.last_name or ''}".strip()
			self.email = faculty.email
			self.phone = faculty.phone
			self.department = faculty.department
			self.designation = faculty.designation
			if not self.photo:
				self.photo = getattr(faculty, "photo", None)

		elif self.card_type == "Driver" and self.driver:
			driver = frappe.get_doc("SLCM Driver", self.driver)
			self.student_name = driver.driver_name
			self.phone = driver.phone
			if not self.photo:
				self.photo = getattr(driver, "photo", None)

		elif self.card_type == "Visitor":
			self.student_name = self.visitor_name
			self.designation = "Visitor"

		elif self.card_type == "Non-Faculty":
			self.student_name = self.non_faculty_name

	def _auto_set_issue_date(self):
		if not self.issue_date:
			self.issue_date = today()

	def _auto_set_expiry_date(self):
		"""Set expiry_date to the end of the student's programme when not provided:
		the end of the Batch's academic year plus the remaining programme years."""
		if self.expiry_date:
			return
		if self.card_type == "Student" and self.student:
			batch, student_year = frappe.db.get_value(
				"Student Master", self.student, ["batch", "academic_year"]
			) or (None, None)
			academic_year = frappe.db.get_value("SLCM Batch", batch, "academic_year") if batch else None
			academic_year = academic_year or student_year
			year_end = (
				frappe.db.get_value("Academic Year", academic_year, "year_end_date")
				if academic_year
				else None
			)
			if year_end:
				duration = cint(
					frappe.db.get_value("Programme", get_student_programme(self.student), "program_duration")
				)
				self.expiry_date = add_years(year_end, max(duration, 1) - 1)

	def _sync_id_card_issued_on_cancel(self):
		"""Reset id_card_issued on Student Master if no other active card remains."""
		other_active = frappe.db.exists(
			self.doctype,
			{
				"student": self.student,
				"card_status": ["not in", ["Cancelled", "Expired"]],
				"name": ["!=", self.name],
			},
		)
		if not other_active:
			frappe.db.set_value("Student Master", self.student, "id_card_issued", "No")

	# ------------------------------------------------------------------
	# Person document accessor
	# ------------------------------------------------------------------

	def get_person_doc(self):
		if self.card_type == "Student" and self.student:
			return frappe.get_doc("Student Master", self.student)
		elif self.card_type == "Faculty" and self.faculty:
			return frappe.get_doc("Faculty", self.faculty)
		elif self.card_type == "Driver" and self.driver:
			return frappe.get_doc("SLCM Driver", self.driver)
		elif self.card_type == "Visitor":
			return frappe._dict(
				{
					"first_name": self.visitor_name,
					"full_name": self.visitor_name,
					"company": self.visitor_company,
					"phone": self.phone,
					"designation": "Visitor",
				}
			)
		elif self.card_type == "Non-Faculty":
			return frappe._dict(
				{
					"first_name": self.non_faculty_name,
					"full_name": self.non_faculty_name,
					"designation": self.designation,
					"phone": self.phone,
					"email": self.email,
					"department": self.department,
					"company": self.visitor_company,
				}
			)
		return None

	# ------------------------------------------------------------------
	# QR code helpers
	# ------------------------------------------------------------------

	def get_qr_code_url(self):
		return self.qr_code_image or None

	def generate_and_save_qr_image(self):
		if not self.qr_code_data:
			return
		import qrcode

		qr = qrcode.QRCode(
			version=1,
			error_correction=qrcode.constants.ERROR_CORRECT_M,
			box_size=10,
			border=4,
		)
		qr.add_data(self.qr_code_data)
		qr.make(fit=True)
		img = qr.make_image(fill_color="black", back_color="white")

		fname = f"{self.name}-QR.png"
		buffer = io.BytesIO()
		img.save(buffer, format="PNG")
		saved_file = save_file(
			fname, buffer.getvalue(), self.doctype, self.name, is_private=1, df="qr_code_image"
		)
		self.qr_code_image = saved_file.file_url

	def generate_qr_code_string(self):
		"""Generate QR payload string for verification."""
		person = self.get_person_doc()
		if not person:
			return ""

		parts = []
		if self.card_type == "Student":
			parts = [
				person.first_name or "",
				person.academic_year or "",
				person.programme_of_study or "",
				person.batch or "",
				person.blood_group or "",
				person.email or "",
			]
		elif self.card_type == "Faculty":
			parts = [
				person.faculty_id or "",
				person.first_name or "",
				person.department or "",
				person.designation or "",
				person.email or "",
			]
		elif self.card_type == "Driver":
			parts = [
				person.driver_id or "",
				person.driver_name or "",
				person.license_number or "",
			]
		elif self.card_type == "Visitor":
			parts = [
				"VISITOR",
				self.visitor_name or "",
				self.visitor_company or "",
				str(self.issue_date) if self.issue_date else "",
			]
		elif self.card_type == "Non-Faculty":
			parts = [
				"STAFF",
				self.non_faculty_name or "",
				self.designation or "",
				self.department or "",
			]

		return " | ".join(filter(None, [str(p) for p in parts]))

	def generate_verification_url(self):
		base_url = get_url()
		return f"{base_url}/verify-student/{self.student}"

	# ------------------------------------------------------------------
	# Card generation
	# ------------------------------------------------------------------

	@frappe.whitelist()
	def generate_card(self, sides=None):
		"""Render the card images from the linked template.

		`sides` limits rendering to "front" and/or "back"; by default both
		sides the template defines are rendered."""
		if self.card_status in ("Cancelled", "Expired"):
			frappe.throw(_("Cannot generate a card that is {0}.").format(_(self.card_status)))

		if self.is_new():
			# Rendering happens right here, so skip the after_insert job.
			self.flags.skip_auto_generate = True
			self.save()

		if not self.id_card_template:
			frappe.throw(_("ID Card Template is required."))

		if isinstance(sides, str):
			sides = json.loads(sides) if sides.startswith("[") else [sides]
		sides = [s for s in (sides or ("front", "back")) if s in ("front", "back")]
		if not sides:
			frappe.throw(_("Select at least one side (front or back) to generate."))

		template = frappe.get_doc("ID Card Template", self.id_card_template)
		person = self.get_person_doc()

		self._refresh_qr()
		images = self.render_card_images(template, person, sides)
		if not images:
			frappe.throw(
				_("Template {0} has nothing to render on the selected side(s).").format(template.name)
			)

		for side, content in images.items():
			saved = save_file(
				f"{self.name}_{side.capitalize()}.png",
				content,
				self.doctype,
				self.name,
				is_private=1,
				df=f"{side}_id_image",
			)
			self.set(f"{side}_id_image", saved.file_url)

		# Regenerating a printed card keeps it Printed.
		if self.card_status in ("Draft", "Error"):
			self.card_status = "Generated"
		self.save()

		if self.card_type == "Student" and self.student:
			frappe.db.set_value("Student Master", self.student, "id_card_issued", "Yes")

	def _refresh_qr(self):
		"""Make sure the QR image matches the current card data before rendering."""
		new_qr_data = self.generate_qr_code_string()
		if new_qr_data and (new_qr_data != self.qr_code_data or not self.qr_code_image):
			self.qr_code_data = new_qr_data
			self.generate_and_save_qr_image()
		self.flags.qr_refreshed = True

	def render_card_images(self, template, person, sides=("front", "back"), qr_src=None, photo_src=None):
		"""Return {side: png_bytes} for the template, without saving anything."""
		mode = template.template_creation_mode
		images = {}

		if mode == "Drag and Drop":
			try:
				data = id_card_render.parse_canvas_data(template.canvas_data)
			except ValueError:
				data = None
			if not data or not id_card_render.visible_elements(data, "front"):
				frappe.throw(_("Template {0} has no design on the front side.").format(template.name))

			values = id_card_render.get_token_values(self, template, person)
			sources = self.get_image_sources(template, person, qr_src, photo_src)
			for side in sides:
				if side == "back" and not id_card_render.visible_elements(data, "back"):
					continue
				images[side] = id_card_render.render_canvas_side(data, side, values, sources)

		elif mode == "Jinja Template":
			for side in sides:
				html_src = template.front_html if side == "front" else template.back_html
				if html_src:
					images[side] = self._render_jinja_side(html_src, person, template, qr_src, photo_src)

		else:
			for side in sides:
				background = template.front_background if side == "front" else template.back_background
				if background:
					images[side] = self._render_field_mapping_side(
						background, template, person, side.capitalize()
					)

		return images

	def _person_photo(self, person):
		if self.photo:
			return self.photo
		if self.card_type == "Student":
			return id_card_render._get(person, "passport_size_photo")
		return id_card_render._get(person, "photo")

	def get_image_sources(self, template, person=None, qr_src=None, photo_src=None):
		"""<img src> values for the image fields a design can map."""
		to_src = id_card_render.to_src
		photo = photo_src or to_src(self._person_photo(person))
		if not photo:
			photo = to_src(self.get_file_path("/assets/frappe/images/default-avatar.png"))
		return {
			"photo": photo,
			"qr_code_image": qr_src or to_src(self.qr_code_image),
			"institute_logo": to_src(template.institute_logo),
			"authority_signature": to_src(template.authority_signature),
			"watermark_image": to_src(template.watermark_image),
		}

	@frappe.whitelist()
	def update_photo(self, file_url=None, update_person=0, regenerate=1):
		"""Set the card photo and optionally re-render the card.

		Without `file_url`, the photo saved on the person's record is used.
		With `update_person`, the new photo is also saved on that record so
		future cards pick it up."""
		self.check_permission("write")
		if self.card_status in ("Cancelled", "Expired"):
			frappe.throw(_("Cannot change the photo of a {0} card.").format(_(self.card_status)))

		target = PERSON_PHOTO_FIELDS.get(self.card_type)
		person = self.get(target[1]) if target else None

		if not file_url:
			if not person:
				frappe.throw(_("This card is not linked to a person record with a photo."))
			file_url = frappe.db.get_value(target[0], person, target[2])
			if not file_url:
				frappe.throw(_("{0} {1} has no photo yet.").format(_(target[0]), person))
			update_person = 0

		self.photo = file_url
		self.save()

		if cint(update_person) and person:
			frappe.has_permission(target[0], "write", doc=person, throw=True)
			# Direct update: only the photo changes, so the person's own
			# validations (registration workflow etc.) are not re-run.
			frappe.db.set_value(target[0], person, target[2], file_url)

		regenerated = False
		if cint(regenerate) and self.id_card_template:
			self.generate_card()
			regenerated = True
		return {"photo": self.photo, "regenerated": regenerated}

	# ------------------------------------------------------------------
	# Cancel and Reissue (Lost Card workflow)
	# ------------------------------------------------------------------

	@frappe.whitelist()
	def cancel_card(self, reason):
		"""Cancel this card with a mandatory reason."""
		if not reason:
			frappe.throw(_("Cancellation reason is mandatory."))
		if self.card_status == "Cancelled":
			frappe.throw(_("Card is already cancelled."))
		self.cancellation_reason = reason
		self.card_status = "Cancelled"
		self.save()

	@frappe.whitelist()
	def reissue_card(self, reason):
		"""Cancel the current card and create a replacement (Lost/Damaged card flow)."""
		if not reason:
			frappe.throw(_("Reason for reissue is mandatory."))
		if self.card_status == "Cancelled":
			frappe.throw(_("Cannot reissue an already cancelled card."))

		# Cancel the existing card first
		self.cancel_card(f"Reissue requested — {reason}")

		# Create new card for the same person
		new_card = frappe.copy_doc(self)
		new_card.card_status = "Draft"
		new_card.front_id_image = None
		new_card.back_id_image = None
		new_card.qr_code_image = None
		new_card.qr_code_data = None
		new_card.verification_url = None
		new_card.print_count = 0
		new_card.cancellation_reason = None
		new_card.remarks = f"Reissued from {self.name}. Reason: {reason}"
		new_card.set("events", [])
		new_card.insert()
		return new_card.name

	# ------------------------------------------------------------------
	# Print logging
	# ------------------------------------------------------------------

	@frappe.whitelist()
	def log_print(self, layout="Single", bulk_print_id=None, total_cards=1, mark_printed=0):
		"""Log a print action for this card; optionally move it to Printed."""
		if self.card_status not in ("Generated", "Printed"):
			frappe.throw(_("Only generated or printed cards can be printed."))

		current_count = self.print_count or 0
		self.db_set("print_count", current_count + 1)

		p_type = "Original" if (current_count + 1) <= 1 else "Reprint"

		if not bulk_print_id:
			bulk_print_id = frappe.utils.generate_hash(length=10)

		log = frappe.new_doc("ID Card Print Log")
		setattr(log, self._print_log_linkfield, self.name)
		log.student = self.student
		log.academic_year = self.academic_year
		log.department = self.department
		log.program = self.programme
		log.batch = self.batch
		log.print_type = p_type
		log.print_layout = layout
		log.bulk_print_id = bulk_print_id
		log.print_action_type = "Bulk" if layout == "Bulk" else "Single"
		log.total_cards_in_bulk = total_cards
		log.printed_by = frappe.session.user
		log.printed_on = frappe.utils.now()
		log.front_image = self.front_id_image
		log.back_image = self.back_id_image

		if p_type == "Reprint":
			log.reprint_reason = "Bulk Reprint" if layout == "Bulk" else "Manual Reprint"

		log.insert(ignore_permissions=True)

		if cint(mark_printed) and self.card_status == "Generated":
			self.reload()
			self.card_status = "Printed"
			self.save()
		return p_type

	# ------------------------------------------------------------------
	# Jinja / Field-mapping render modes
	# ------------------------------------------------------------------

	def _render_jinja_side(self, html_content, person, template, qr_src=None, photo_src=None):
		if hasattr(person, "as_dict") and callable(person.as_dict):
			context = person.as_dict()
		else:
			context = dict(person) if person else {}

		context.update(self.as_dict())
		context.update(template.as_dict())

		person_photo = self.get_file_path(self._person_photo(person)) or ""
		qr = qr_src or self.get_file_path(self.qr_code_image) or ""
		context.update(
			{
				"doc": self,
				"student": person,
				"person": person,
				"template": template,
				"institute_name": template.institute_name,
				"institute_address": template.institute_address,
				"institute_logo": self.get_file_path(template.institute_logo) or "",
				"logo_url": self.get_file_path(template.institute_logo) or "",
				"authority_signature": self.get_file_path(template.authority_signature) or "",
				"passport_size_photo": photo_src or person_photo,
				"photo": photo_src or person_photo,
				"qr_code_image": qr,
				"qr_code": qr,
				"institute_logo_url": get_url(template.institute_logo) if template.institute_logo else "",
			}
		)

		rendered_html = frappe.render_template(html_content, context)
		if "width: 638px" in rendered_html.replace("width:638px", "width: 638px"):
			width, height = 638, 1011
		else:
			width, height = 1011, 638
		return id_card_render.screenshot_html(rendered_html, width, height, 1)

	def _render_field_mapping_side(self, background, template, person, side):
		from PIL import Image

		path = self.get_file_path(background)
		if not path:
			frappe.throw(_("Background image for the {0} side was not found.").format(side))
		image = Image.open(path).convert("RGBA")
		self.process_side(image, template, person, side)
		buf = io.BytesIO()
		image.save(buf, format="PNG", dpi=(300, 300))
		return buf.getvalue()

	def process_side(self, image, template, student, side):
		from PIL import ImageDraw

		draw = ImageDraw.Draw(image)
		fields = [f for f in template.fields if f.side == side]
		for field in fields:
			self.draw_field(draw, image, field, student)

	def draw_field(self, draw, image, field, student):
		from PIL import ImageFont

		content = self.get_field_value(field.student_fieldname, student)
		if not content:
			return

		x, y = field.position_x, field.position_y
		font_size = field.font_size or 30
		font_color = hex_to_rgb(field.font_color or "#000000")

		try:
			font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
			if field.font_files:
				font_path = self.get_file_path(field.font_files)
			font = ImageFont.truetype(font_path, font_size)
		except Exception:
			font = ImageFont.load_default()

		if field.student_fieldname == "photo":
			self.paste_photo(image, content, x, y, field.width, field.width)
		elif field.student_fieldname == "qrcode":
			self.paste_qr(image, self.qr_code_data, x, y, field.width)
		else:
			if field.alignment == "Center":
				text_width = draw.textlength(str(content), font=font)
				x = x - (text_width / 2)
			elif field.alignment == "Right":
				text_width = draw.textlength(str(content), font=font)
				x = x - text_width
			draw.text((x, y), str(content), font=font, fill=font_color)

	def get_field_value(self, fieldname, student):
		if fieldname == "qrcode":
			return "qrcode"
		if fieldname == "photo":
			if hasattr(student, "passport_size_photo") and student.passport_size_photo:
				return student.passport_size_photo
			if hasattr(student, "photo") and student.photo:
				return student.photo
			return None
		if hasattr(student, fieldname):
			return getattr(student, fieldname)
		return None

	def paste_photo(self, base_image, photo_path, x, y, w, h):
		from PIL import Image

		if not photo_path:
			return
		try:
			full_path = self.get_file_path(photo_path)
			photo = Image.open(full_path).convert("RGBA")
			if w and h:
				photo = photo.resize((w, h), Image.Resampling.LANCZOS)
			elif w:
				ratio = w / photo.width
				h = int(photo.height * ratio)
				photo = photo.resize((w, h), Image.Resampling.LANCZOS)
			base_image.paste(photo, (x, y), photo)
		except Exception as e:
			frappe.log_error(f"Error pasting photo: {e}", "ID Card Photo Error")

	def paste_qr(self, base_image, data, x, y, size):
		import qrcode
		from PIL import Image

		qr = qrcode.QRCode(
			version=1,
			error_correction=qrcode.constants.ERROR_CORRECT_H,
			box_size=10,
			border=1,
		)
		qr.add_data(data)
		qr.make(fit=True)
		img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
		if size:
			img_qr = img_qr.resize((size, size), Image.Resampling.LANCZOS)
		base_image.paste(img_qr, (x, y), img_qr)

	def get_file_path(self, file_url):
		return id_card_render.get_file_path(file_url)
