"""Shared logic for the ID Card Generation and Student ID Card controllers.

Both doctypes model the same lost/reissue/print/QR/canvas-rendering
lifecycle for a physical ID card, differing only in which "person" doctypes
they support and which link field on ID Card Print Log they populate. This
module holds the one copy of that shared logic so a fix here applies to
both controllers instead of needing to be duplicated by hand.
"""

import io
import json
import os
import subprocess
import tempfile

import frappe
from frappe import _
from frappe.utils import add_years, cint, get_url, now, today
from frappe.utils.file_manager import save_file

from slcm.slcm.utils.exam_schedule import get_student_programme

# Valid card_status transitions. Terminal states map to empty list.
VALID_STATUS_TRANSITIONS = {
	"Draft": ["Generated", "Cancelled"],
	"Generated": ["Printed", "Cancelled", "Expired"],
	"Printed": ["Cancelled", "Expired"],
	"Error": ["Draft", "Cancelled"],
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
		if new_qr_data and (new_qr_data != getattr(self, "_old_qr_data", None) or not self.qr_code_image):
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
				_(
					"Cannot change ID Card status from '{0}' to '{1}'. "
					"Allowed next states: {2}"
				).format(old_status, self.card_status, ", ".join(allowed) or _("None"))
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
				_("Active ID Card {0} already exists for {1} {2}").format(
					existing, self.card_type, value
				)
			)

	def _populate_person_fields(self):
		"""Auto-fill card fields from the linked person document on first insert."""
		if self.card_type == "Student" and self.student:
			student = frappe.get_doc("Student Master", self.student)
			self.student_name = f"{student.first_name} {student.last_name or ''}".strip()
			self.email = student.email
			self.phone = student.phone
			if not self.photo:
				self.photo = student.passport_size_photo
			self.batch = student.batch
			self.programme = student.programme_of_study

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
			driver = frappe.get_doc("Driver", self.driver)
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
			batch = frappe.db.get_value("Student Master", self.student, "batch")
			academic_year = frappe.db.get_value("Batch", batch, "academic_year") if batch else None
			year_end = frappe.db.get_value("Academic Year", academic_year, "year_end_date") if academic_year else None
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
			frappe.db.set_value("Student Master", self.student, "id_card_issued", 0)

	# ------------------------------------------------------------------
	# Person document accessor
	# ------------------------------------------------------------------

	def get_person_doc(self):
		if self.card_type == "Student" and self.student:
			return frappe.get_doc("Student Master", self.student)
		elif self.card_type == "Faculty" and self.faculty:
			return frappe.get_doc("Faculty", self.faculty)
		elif self.card_type == "Driver" and self.driver:
			return frappe.get_doc("Driver", self.driver)
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
		saved_file = save_file(fname, buffer.getvalue(), self.doctype, self.name, is_private=1)
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
	def generate_card(self):
		if self.is_new():
			self.save()

		if not self.id_card_template:
			frappe.throw(_("ID Card Template is required."))

		template = frappe.get_doc("ID Card Template", self.id_card_template)
		person = self.get_person_doc()

		if template.template_creation_mode == "Drag and Drop":
			self.generate_card_from_canvas(template, person)
		elif template.template_creation_mode == "Jinja Template":
			self.generate_card_html(template, person)
		else:
			from PIL import Image

			front_bg_path = self.get_file_path(template.front_background)
			back_bg_path = self.get_file_path(template.back_background)

			if front_bg_path:
				front_img = Image.open(front_bg_path).convert("RGBA")
				self.process_side(front_img, template, person, "Front")
				self.save_image(front_img, f"{self.name}_Front.png", "front_id_image")

			if back_bg_path:
				back_img = Image.open(back_bg_path).convert("RGBA")
				self.process_side(back_img, template, person, "Back")
				self.save_image(back_img, f"{self.name}_Back.png", "back_id_image")

		self.card_status = "Generated"
		self.save()

		# Auto-mark id_card_issued on Student Master
		if self.card_type == "Student" and self.student:
			frappe.db.set_value("Student Master", self.student, "id_card_issued", 1)

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
	def log_print(self, layout="Single", bulk_print_id=None, total_cards=1):
		"""Log a print action for this card."""
		if self.card_status != "Generated":
			frappe.throw(_("Cannot log print for a card that is not in 'Generated' status."))

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
		return p_type

	# ------------------------------------------------------------------
	# Canvas / Jinja / Field-mapping generation modes
	# ------------------------------------------------------------------

	def generate_card_from_canvas(self, template, student):
		if not template.canvas_data:
			frappe.throw(_("No design data found in the selected Drag & Drop Template."))

		try:
			data = json.loads(template.canvas_data)
		except Exception:
			frappe.throw(_("Invalid Canvas Data in Template."))

		if data.get("orientation") == "horizontal":
			width, height = 1011, 638
			scale_factor = 3
		else:
			width, height = 638, 1011
			scale_factor = 3

		for side in ["front", "back"]:
			elements = data.get(side, [])
			bg_color = data.get("bg_color", {}).get(side, "#ffffff")

			html_content = f"""
			<html>
			<head>
				<style>
					body {{ margin: 0; padding: 0; background-color: {bg_color}; }}
					.container {{
						position: relative;
						width: {width}px;
						height: {height}px;
						overflow: hidden;
					}}
					.element {{ position: absolute; }}
				</style>
			</head>
			<body>
				<div class="container">
			"""

			for el in elements:
				x = float(el.get("x", 0)) * scale_factor
				y = float(el.get("y", 0)) * scale_factor
				w = float(el.get("width", 0)) * scale_factor
				h = float(el.get("height", 0)) * scale_factor
				style = el.get("style", {})

				css_style = f"left: {x}px; top: {y}px;"
				if "fontSize" in style:
					size_px = float(style["fontSize"].replace("px", "")) * scale_factor
					css_style += f" font-size: {size_px}px;"
				if "fontWeight" in style:
					css_style += f" font-weight: {style['fontWeight']};"
				if "color" in style:
					css_style += f" color: {style['color']};"
				if "opacity" in style:
					css_style += f" opacity: {style['opacity']};"
				if "fontFamily" in style:
					css_style += f" font-family: {style['fontFamily']}, sans-serif;"
				if "backgroundColor" in style:
					css_style += f" background-color: {style['backgroundColor']};"
				if "borderRadius" in style:
					css_style += f" border-radius: {style['borderRadius']};"
				if "clipPath" in style and style["clipPath"] != "none":
					css_style += f" clip-path: {style['clipPath']}; -webkit-clip-path: {style['clipPath']};"

				for border_side in ["Top", "Bottom", "Left", "Right"]:
					style_prop = f"border{border_side}Style"
					width_prop = f"border{border_side}Width"
					color_prop = f"border{border_side}Color"

					if style_prop in style:
						b_style = style[style_prop]
						b_width = style.get(width_prop, "0px")
						b_color = style.get(color_prop, "#000000")

						try:
							w_val = float(str(b_width).replace("px", "")) * scale_factor
							w_css = f"{w_val}px"
						except Exception:
							w_css = b_width

						css_side = border_side.lower()
						css_style += f" border-{css_side}-style: {b_style}; border-{css_side}-width: {w_css}; border-{css_side}-color: {b_color};"

				content = el.get("content", "")

				if el.get("type") == "text":
					html_content += (
						f'<div class="element" style="{css_style} white-space: nowrap;">{content}</div>'
					)
				elif el.get("type") == "image":
					if el.get("mapping"):
						mapping = el.get("mapping")
						if mapping == "photo":
							content = (
								self.get_file_path(self.photo) or "/assets/frappe/images/default-avatar.png"
							)
						elif mapping == "institute_logo":
							content = self.get_file_path(template.institute_logo) or ""
						elif mapping == "authority_signature":
							content = self.get_file_path(template.authority_signature) or ""
							if not content:
								frappe.log_error(
									f"Missing Authority Signature for Template: {template.name}",
									"ID Card Generation Warning",
								)
						elif mapping == "qr_code_image":
							content = self.get_file_path(self.qr_code_image) or ""
							if not content:
								frappe.log_error(
									f"Missing QR Code Image for Card: {self.name}",
									"ID Card Generation Warning",
								)

					html_content += f'<div class="element" style="{css_style} width: {w}px; height: {h}px; overflow: hidden;">'
					if content:
						html_content += f'<img src="{content}" style="width: 100%; height: 100%; object-fit: cover; display: block;">'
					html_content += "</div>"
				elif el.get("type") == "rect":
					html_content += (
						f'<div class="element" style="{css_style} width: {w}px; height: {h}px;"></div>'
					)

			html_content += """
				</div>
			</body>
			</html>
			"""

			field_map = {
				"[Student Name]": self.student_name,
				"[Faculty Name]": self.student_name,
				"[Driver Name]": self.student_name,
				"[Visitor Name]": self.student_name,
				"[Staff Name]": self.student_name,
				"[Student ID]": getattr(student, "registration_id", None) or self.name,
				"[Employee ID]": self.faculty,
				"[Driver ID]": self.driver,
				"[Blood Group]": getattr(student, "blood_group", ""),
				"[Phone]": self.phone,
				"[Email]": self.email,
				"[Batch]": self.batch,
				"[Programme]": self.programme,
				"[Academic Year]": self.academic_year,
				"[Date of Birth]": frappe.utils.format_date(self.date_of_birth) if self.date_of_birth else "",
				"[Expiry Date]": frappe.utils.format_date(self.expiry_date) if self.expiry_date else "",
				"[Department]": self.department,
				"[Institute Name]": template.institute_name,
				"[Institute Address]": template.institute_address,
				"[Address]": getattr(student, "state_of_domicile", ""),
				"[Designation]": self.designation,
				"[Company]": self.visitor_company,
				"[License No]": getattr(student, "license_number", ""),
				"[Purpose]": self.remarks,
			}

			for key, val in field_map.items():
				if val is None:
					val = ""
				html_content = html_content.replace(key, str(val))

			self.generate_image_from_raw_html(html_content, f"{side}_id_image", side.capitalize())

	def generate_image_from_raw_html(self, html_content, fieldname, side_label):
		with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
			f.write(html_content)
			html_path = f.name

		output_filename = f"{self.name}_{side_label}.png"
		output_path = os.path.join(tempfile.gettempdir(), output_filename)

		try:
			from frappe.utils.print_utils import find_or_download_chromium_executable

			chrome_path = find_or_download_chromium_executable()
			if not chrome_path:
				frappe.throw(_("Chromium executable not found. Cannot generate ID Card image."))

			window_width = "638" if "width: 638px;" in html_content else "1011"
			window_height = "1011" if window_width == "638" else "638"

			args = [
				chrome_path,
				"--headless",
				"--disable-gpu",
				"--no-sandbox",
				f"--window-size={window_width},{window_height}",
				"--hide-scrollbars",
				f"--screenshot={output_path}",
				f"file://{os.path.abspath(html_path)}",
			]

			result = subprocess.run(args, capture_output=True, text=True)
			if result.returncode != 0:
				frappe.throw(f"Chromium failed: {result.stderr}")

			with open(output_path, "rb") as f:
				img_content = f.read()

			saved_file = save_file(output_filename, img_content, self.doctype, self.name, is_private=1)
			self.db_set(fieldname, saved_file.file_url)

		except Exception as e:
			frappe.throw(f"Error generating from canvas: {e}")
		finally:
			if os.path.exists(html_path):
				os.remove(html_path)
			if os.path.exists(output_path):
				os.remove(output_path)

	def generate_card_html(self, template, student):
		if template.front_html:
			self.generate_image_from_html(template.front_html, student, template, "front_id_image", "Front")
		if template.back_html:
			self.generate_image_from_html(template.back_html, student, template, "back_id_image", "Back")

	def generate_image_from_html(self, html_content, person, template, fieldname, side):
		if hasattr(person, "as_dict") and callable(person.as_dict):
			context = person.as_dict()
		else:
			context = person.copy() if person else {}

		context.update(self.as_dict())
		context.update(template.as_dict())

		person_photo = ""
		if self.card_type == "Student":
			person_photo = getattr(person, "passport_size_photo", "")
		elif self.card_type in ["Faculty", "Driver"]:
			person_photo = getattr(person, "photo", "")

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
				"passport_size_photo": self.get_file_path(person_photo) or "",
				"photo": self.get_file_path(person_photo) or "",
				"qr_code_image": self.get_file_path(self.qr_code_image) or "",
				"qr_code": self.get_file_path(self.qr_code_image) or "",
				"institute_logo_url": get_url(template.institute_logo) if template.institute_logo else "",
			}
		)

		rendered_html = frappe.render_template(html_content, context)

		with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
			f.write(rendered_html)
			html_path = f.name

		output_filename = f"{self.name}_{side}.png"
		output_path = os.path.join(tempfile.gettempdir(), output_filename)

		try:
			from frappe.utils.print_utils import find_or_download_chromium_executable

			chrome_path = find_or_download_chromium_executable()
			if not chrome_path:
				frappe.throw(_("Chromium executable not found. Cannot generate ID Card image."))

			args = [
				chrome_path,
				"--headless",
				"--disable-gpu",
				"--no-sandbox",
				"--window-size=1011,638",
				"--hide-scrollbars",
				f"--screenshot={output_path}",
				f"file://{os.path.abspath(html_path)}",
			]

			result = subprocess.run(args, capture_output=True, text=True)
			if result.returncode != 0:
				frappe.throw(f"Chromium failed with code {result.returncode}: {result.stderr}")

			with open(output_path, "rb") as f:
				img_content = f.read()

			saved_file = save_file(output_filename, img_content, self.doctype, self.name, is_private=1)
			self.db_set(fieldname, saved_file.file_url)

		except Exception as e:
			frappe.throw(f"Error generating ID Card from HTML: {e}")
		finally:
			if os.path.exists(html_path):
				os.remove(html_path)
			if os.path.exists(output_path):
				os.remove(output_path)

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
		if not file_url:
			return None
		if file_url.startswith("http"):
			return file_url

		path = None
		if file_url.startswith("/assets/"):
			asset_path = file_url.replace("/assets/", "", 1)
			bench_path = frappe.utils.get_bench_path()
			full_path = os.path.join(bench_path, "sites", "assets", asset_path)
			if os.path.exists(full_path):
				path = full_path
			elif "default-avatar.png" in file_url:
				path = frappe.get_app_path("frappe", "public", "images", "default-avatar.png")
		elif file_url.startswith("/private/files/"):
			file_name = file_url.replace("/private/files/", "", 1)
			path = frappe.get_site_path("private", "files", file_name)
		elif file_url.startswith("/"):
			path = frappe.get_site_path("public", file_url.lstrip("/"))
		else:
			path = frappe.get_site_path("public", file_url)

		if path:
			return os.path.abspath(path)
		return None

	def save_image(self, image, filename, fieldname):
		img_io = io.BytesIO()
		image.save(img_io, format="PNG", dpi=(300, 300))
		saved_file = save_file(filename, img_io.getvalue(), self.doctype, self.name, is_private=1)
		self.db_set(fieldname, saved_file.file_url)
