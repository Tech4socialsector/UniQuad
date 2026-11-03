import io
import os
import zipfile

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now, now_datetime, strip_html
from frappe.utils.file_manager import save_file

from slcm.slcm.utils.id_card_render import get_file_path

RUN_CACHE_KEY = "slcm:id_card_generation_tool:run"
PROGRESS_EVENT = "id_card_tool_progress"

# A4 at 300 DPI; a CR80 card is 1011 x 638 px at the same resolution.
A4_PX = (2480, 3508)
CARD_PX = (1011, 638)
SHEET_MARGIN = 120
CARD_GAP = 60


def get_active_card(student):
	return frappe.db.get_value(
		"ID Card Generation",
		{"student": student, "card_status": ["not in", ["Cancelled", "Expired"]]},
		"name",
		order_by="creation desc",
	)


@frappe.whitelist()
def get_student_row(student):
	"""Row values for adding one student to the list by hand."""
	frappe.has_permission("Student Master", "read", doc=student, throw=True)
	values = frappe.db.get_value(
		"Student Master", student, ["name", "first_name", "passport_size_photo", "section"], as_dict=True
	)
	if not values:
		frappe.throw(_("Student {0} not found.").format(student))
	existing_card = get_active_card(student)
	return {
		"student": values.name,
		"student_name": (values.first_name or "").strip(),
		"section": values.section,
		"has_photo": 1 if values.passport_size_photo else 0,
		"current_id_card": existing_card,
		"status": "Already Exists" if existing_card else "Pending",
	}


@frappe.whitelist()
def get_student_rows(students):
	"""Rows for several students at once (used to retry a log's failures)."""
	students = frappe.parse_json(students) if isinstance(students, str) else students
	return [
		get_student_row(s) for s in dict.fromkeys(students or []) if frappe.db.exists("Student Master", s)
	]


class IDCardGenerationTool(Document):
	@frappe.whitelist()
	def reset_filters(self):
		self.academic_year = None
		self.program = None
		self.batch = None
		self.section = None
		self.id_card_template = None
		self.issue_date = frappe.utils.today()
		self.expiry_date = None
		self.generate_front = 1
		self.generate_back = 1
		self.regenerate_existing = 0
		self.set("student_list", [])
		self.flags.ignore_mandatory = True
		self.save()
		self.flags.ignore_mandatory = False

	@frappe.whitelist()
	def get_students(self):
		self._ensure_not_running()
		if not any([self.academic_year, self.program, self.batch, self.section]):
			frappe.throw(
				_(
					"Select at least one filter (Academic Year, Programme, Batch or Section) before fetching students."
				)
			)

		filters = {"student_status": "Active"}
		if self.academic_year:
			filters["academic_year"] = self.academic_year
		if self.program:
			filters["programme_of_study"] = self.program
		if self.batch:
			filters["batch"] = self.batch
		if self.section:
			filters["section"] = self.section

		students = frappe.get_all(
			"Student Master",
			filters=filters,
			fields=["name", "first_name", "passport_size_photo", "section"],
			order_by="first_name asc",
		)

		self.set("student_list", [])
		for student in students:
			existing_card = get_active_card(student.name)
			self.append(
				"student_list",
				{
					"student": student.name,
					"student_name": (student.first_name or "").strip(),
					"section": student.section,
					"has_photo": 1 if student.passport_size_photo else 0,
					"current_id_card": existing_card,
					"status": "Already Exists" if existing_card else "Pending",
				},
			)

		self.flags.ignore_mandatory = True
		self.save()
		return len(students)

	def _scoped_rows(self, students=None):
		"""Rows limited to the given students (all rows when none are given)."""
		students = _parse_students(students)
		if not students:
			return list(self.student_list)
		return [r for r in self.student_list if r.student in students]

	def _rows_to_process(self, students=None):
		"""Rows without an active card, plus every row when regenerating."""
		rows = self._scoped_rows(students)
		if cint(self.regenerate_existing):
			return rows
		return [r for r in rows if r.status not in ("Already Exists", "Generated")]

	def _ensure_not_running(self):
		if frappe.cache.get_value(RUN_CACHE_KEY):
			frappe.throw(_("ID cards are being generated right now. Wait for that run to finish."))

	@frappe.whitelist()
	def generate_cards(self, students=None):
		"""Queue generation for the list, or only for `students` when given."""
		students = _parse_students(students)
		self._ensure_not_running()
		if not self.id_card_template:
			frappe.throw(_("Select an ID Card Template."))
		if not (cint(self.generate_front) or cint(self.generate_back)):
			frappe.throw(_("Select the front side, the back side, or both."))
		if not self.student_list:
			frappe.throw(_("No students in the list. Use Get Students first."))

		rows = self._rows_to_process(students)
		if not rows:
			frappe.throw(
				_(
					"Every selected student already has an active ID card. "
					"Tick Regenerate Existing Cards to re-render them."
				)
			)

		self.save()
		frappe.cache.set_value(
			RUN_CACHE_KEY,
			{"user": frappe.session.user, "total": len(rows), "done": 0, "started": now()},
			expires_in_sec=3 * 3600,
		)
		frappe.enqueue(
			"slcm.slcm.doctype.id_card_generation_tool.id_card_generation_tool.run_bulk_generation",
			queue="long",
			timeout=4 * 3600,
			job_id="slcm-id-card-generation-tool",
			deduplicate=True,
			enqueue_after_commit=True,
			requested_by=frappe.session.user,
			students=students or None,
		)
		return {"queued": len(rows)}

	@frappe.whitelist()
	def get_run_status(self):
		return frappe.cache.get_value(RUN_CACHE_KEY)

	@frappe.whitelist()
	def render_preview(self, student=None):
		"""Front/back preview of the selected template for a student in the list
		(the first one by default)."""
		if not self.id_card_template:
			return None
		from slcm.slcm.doctype.id_card_template.id_card_template import build_preview

		template = frappe.get_doc("ID Card Template", self.id_card_template)
		listed = [r.student for r in self.student_list]
		if student not in listed:
			student = listed[0] if listed else None
		return build_preview(template, student)

	# ------------------------------------------------------------------
	# Output
	# ------------------------------------------------------------------

	def _generated_cards(self, students=None):
		names = [r.current_id_card for r in self._scoped_rows(students) if r.current_id_card]
		if not names:
			return []
		cards = frappe.get_all(
			"ID Card Generation",
			filters={"name": ["in", names], "card_status": ["in", ["Generated", "Printed"]]},
			fields=["name", "student", "student_name", "card_status", "front_id_image", "back_id_image"],
		)
		by_name = {c.name: c for c in cards}
		# Keep the order of the student list.
		return [by_name[n] for n in names if n in by_name and by_name[n].front_id_image]

	@frappe.whitelist()
	def download_zip(self, students=None):
		cards = self._generated_cards(students)
		if not cards:
			frappe.throw(_("No generated cards in this list yet."))

		zip_buffer = io.BytesIO()
		added = 0
		with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
			for card in cards:
				for side, url in (("Front", card.front_id_image), ("Back", card.back_id_image)):
					path = get_file_path(url)
					if path and os.path.exists(path):
						zip_file.write(path, arcname=f"{card.student}_{side}.png")
						added += 1
		if not added:
			frappe.throw(_("The card image files could not be found on the server."))

		saved = save_file(
			f"ID_Cards_{frappe.utils.nowdate()}.zip",
			zip_buffer.getvalue(),
			self.doctype,
			self.name,
			is_private=1,
		)
		return saved.file_url

	@frappe.whitelist()
	def generate_print_layout(self, layout="pairs", crop_marks=1, students=None):
		"""A4 print-ready PDF at 300 DPI.

		layout "pairs": each card's front and back side by side.
		layout "duplex": a page of fronts followed by a page of backs,
		mirrored so they line up when printed double-sided (long-edge flip)."""
		import tempfile

		from PIL import Image

		cards = self._generated_cards(students)
		if not cards:
			frappe.throw(_("No generated cards in this list yet."))

		# Only image headers are read here; pixels load page by page.
		groups = {}
		for card in cards:
			front = get_file_path(card.front_id_image)
			if not front or not os.path.exists(front):
				continue
			back = get_file_path(card.back_id_image) if card.back_id_image else None
			if back and not os.path.exists(back):
				back = None
			with Image.open(front) as img:
				size = CARD_PX if img.width >= img.height else (CARD_PX[1], CARD_PX[0])
			groups.setdefault(size, []).append((card, front, back))
		if not groups:
			frappe.throw(_("The card image files could not be found on the server."))

		page_count = 0
		with tempfile.TemporaryDirectory(prefix="idcard-sheet-") as tmp:
			pdf_path = os.path.join(tmp, "sheet.pdf")
			for size, items in groups.items():
				for page in _layout_pages(items, size, layout, cint(crop_marks)):
					page.save(pdf_path, "PDF", resolution=300, quality=95, append=page_count > 0)
					page.close()
					page_count += 1
			with open(pdf_path, "rb") as f:
				pdf_bytes = f.read()

		bulk_print_id = frappe.utils.generate_hash(length=10)
		printed = [item[0] for items in groups.values() for item in items]
		for card in printed:
			doc = frappe.get_doc("ID Card Generation", card.name)
			doc.log_print(layout="Bulk", bulk_print_id=bulk_print_id, total_cards=len(printed))

		def clean(s):
			return "".join(c for c in (s or "") if c.isalnum() or c in ("-", "_")).strip() or "All"

		filename = f"{clean(self.academic_year)}_{clean(self.program)}_{clean(self.batch)}_ID_Cards.pdf"
		saved = save_file(filename, pdf_bytes, self.doctype, self.name, is_private=1)
		return {"file_url": saved.file_url, "cards": len(printed), "pages": page_count}

	@frappe.whitelist()
	def mark_as_printed(self, students=None):
		names = [c.name for c in self._generated_cards(students) if c.card_status == "Generated"]
		for name in names:
			doc = frappe.get_doc("ID Card Generation", name)
			doc.card_status = "Printed"
			doc.save()
		return len(names)


def _grid(card_size, unit_w):
	width = A4_PX[0] - 2 * SHEET_MARGIN
	height = A4_PX[1] - 2 * SHEET_MARGIN
	cols = max(1, (width + CARD_GAP) // (unit_w + CARD_GAP))
	rows = max(1, (height + CARD_GAP) // (card_size[1] + CARD_GAP))
	# Centre the grid on the page.
	left = (A4_PX[0] - (cols * unit_w + (cols - 1) * CARD_GAP)) // 2
	top = (A4_PX[1] - (rows * card_size[1] + (rows - 1) * CARD_GAP)) // 2
	return cols, rows, left, top


def _draw_crop_marks(draw, x, y, w, h):
	length, gap = 22, 6
	color = (150, 150, 150)
	for cx, dx in ((x, -1), (x + w, 1)):
		for cy, dy in ((y, -1), (y + h, 1)):
			draw.line([(cx + dx * gap, cy), (cx + dx * (gap + length), cy)], fill=color, width=2)
			draw.line([(cx, cy + dy * gap), (cx, cy + dy * (gap + length))], fill=color, width=2)


def _load_card(path, size):
	from PIL import Image

	with Image.open(path) as img:
		img = img.convert("RGB")
		return img.resize(size, Image.Resampling.LANCZOS) if img.size != size else img.copy()


def _layout_pages(items, card_size, layout, crop_marks):
	"""Yield A4 pages one at a time so large batches stay light on memory."""
	from PIL import Image, ImageDraw

	w, h = card_size

	if layout == "duplex":
		cols, rows, left, top = _grid(card_size, w)
		per_page = cols * rows
		for start in range(0, len(items), per_page):
			chunk = items[start : start + per_page]
			front_page = Image.new("RGB", A4_PX, "white")
			back_page = Image.new("RGB", A4_PX, "white")
			fd, bd = ImageDraw.Draw(front_page), ImageDraw.Draw(back_page)
			for idx, (_card, front, back) in enumerate(chunk):
				col, row = idx % cols, idx // cols
				y = top + row * (h + CARD_GAP)
				fx = left + col * (w + CARD_GAP)
				bx = left + (cols - 1 - col) * (w + CARD_GAP)
				front_page.paste(_load_card(front, card_size), (fx, y))
				if back:
					back_page.paste(_load_card(back, card_size), (bx, y))
				if crop_marks:
					_draw_crop_marks(fd, fx, y, w, h)
					_draw_crop_marks(bd, bx, y, w, h)
			yield front_page
			yield back_page
		return

	unit_w = 2 * w + CARD_GAP
	cols, rows, left, top = _grid(card_size, unit_w)
	per_page = cols * rows
	for start in range(0, len(items), per_page):
		page = Image.new("RGB", A4_PX, "white")
		draw = ImageDraw.Draw(page)
		for idx, (_card, front, back) in enumerate(items[start : start + per_page]):
			col, row = idx % cols, idx // cols
			x = left + col * (unit_w + CARD_GAP)
			y = top + row * (h + CARD_GAP)
			page.paste(_load_card(front, card_size), (x, y))
			if crop_marks:
				_draw_crop_marks(draw, x, y, w, h)
			if back:
				page.paste(_load_card(back, card_size), (x + w + CARD_GAP, y))
				if crop_marks:
					_draw_crop_marks(draw, x + w + CARD_GAP, y, w, h)
		yield page


def _parse_students(students):
	if isinstance(students, str):
		students = frappe.parse_json(students) if students.strip().startswith("[") else [students]
	return {s for s in (students or []) if s}


def run_bulk_generation(requested_by=None, students=None):
	"""Background job: generate cards for the rows in the tool, one by one,
	and record the run in an ID Card Generation Tool Log."""
	user = requested_by or frappe.session.user
	started_on = now_datetime()
	total = generated = failed = 0
	log_name = None

	def publish(done, row=None, finished=False):
		state = {"user": user, "total": total, "done": done, "generated": generated, "failed": failed}
		if not finished:
			frappe.cache.set_value(RUN_CACHE_KEY, state, expires_in_sec=3 * 3600)
		payload = dict(state, finished=finished, log=log_name)
		if row is not None:
			payload.update({"student": row.student, "student_name": row.student_name, "status": row.status})
		frappe.publish_realtime(PROGRESS_EVENT, payload, user=user)

	try:
		tool = frappe.get_doc("ID Card Generation Tool")
		scope = tool._scoped_rows(students)
		rows = tool._rows_to_process(students)
		total = len(rows)
		sides = [s for s, on in (("front", tool.generate_front), ("back", tool.generate_back)) if cint(on)]
		processing = {r.name for r in rows}
		results = {}
		new_cards = regenerated = skipped = 0

		for row in scope:
			if row.name not in processing:
				skipped += 1
				results[row.name] = {
					"result": "Skipped",
					"id_card": row.current_id_card,
					"message": _("Already had a card"),
				}

		for done, row in enumerate(rows, start=1):
			existing = get_active_card(row.student)
			if existing and not cint(tool.regenerate_existing):
				# Someone issued a card since the list was loaded.
				row.current_id_card = existing
				row.status = "Already Exists"
				skipped += 1
				results[row.name] = {
					"result": "Skipped",
					"id_card": existing,
					"message": _("Card issued while the run was queued"),
				}
				frappe.db.set_value(
					"ID Card Generation Item",
					row.name,
					{"current_id_card": existing, "status": row.status},
					update_modified=False,
				)
				frappe.db.commit()
				publish(done, row)
				continue
			try:
				if existing:
					doc = frappe.get_doc("ID Card Generation", existing)
					if tool.issue_date:
						doc.issue_date = tool.issue_date
					if tool.expiry_date:
						doc.expiry_date = tool.expiry_date
				else:
					doc = frappe.new_doc("ID Card Generation")
					doc.card_type = "Student"
					doc.student = row.student
					doc.issue_date = tool.issue_date
					doc.expiry_date = tool.expiry_date or None

				doc.id_card_template = tool.id_card_template
				doc.generate_card(sides=sides)
				frappe.db.commit()

				row.current_id_card = doc.name
				row.status = "Generated"
				generated += 1
				if existing:
					regenerated += 1
				else:
					new_cards += 1
				results[row.name] = {
					"result": "Regenerated" if existing else "New",
					"id_card": doc.name,
					"message": "",
				}
			except Exception as e:
				frappe.db.rollback()
				message = strip_html(str(e))
				row.current_id_card = existing
				row.status = f"Error: {message}"[:140]
				failed += 1
				results[row.name] = {"result": "Failed", "id_card": existing, "message": message[:1000]}
				frappe.log_error(
					title=f"ID Card Generation Error: {row.student}", message=frappe.get_traceback()
				)

			frappe.db.set_value(
				"ID Card Generation Item",
				row.name,
				{"current_id_card": row.current_id_card, "status": row.status},
				update_modified=False,
			)
			frappe.db.commit()
			publish(done, row)

		finished_on = now_datetime()
		log = frappe.get_doc(
			{
				"doctype": "ID Card Generation Tool Log",
				"generation_tool_run_id": frappe.generate_hash(length=10),
				"started_on": started_on,
				"generated_on": finished_on,
				"duration_seconds": round((finished_on - started_on).total_seconds(), 1),
				"generated_by": user,
				"academic_year": tool.academic_year,
				"program": tool.program,
				"batch": tool.batch,
				"section": tool.section,
				"template_used": tool.id_card_template,
				"issue_date": tool.issue_date,
				"expiry_date": tool.expiry_date,
				"sides": " + ".join(s.title() for s in sides),
				"regenerate_existing": cint(tool.regenerate_existing),
				"total_students_selected": len(scope),
				"total_processed": total,
				"total_id_cards_generated": generated,
				"new_cards": new_cards,
				"regenerated_cards": regenerated,
				"skipped_count": skipped,
				"failed_count": failed,
				"missing_photo_count": sum(1 for r in scope if not r.has_photo),
				"generation_mode": "Single" if total == 1 else "Bulk",
				"generation_status": "Success" if not failed else ("Failed" if not generated else "Partial"),
				"remarks": _(
					"Generated {0} of {1} cards ({2} new, {3} regenerated); {4} skipped, {5} failed."
				).format(generated, total, new_cards, regenerated, skipped, failed),
				"results": [
					{
						"student": row.student,
						"student_name": row.student_name,
						"has_photo": row.has_photo,
						**results[row.name],
					}
					for row in scope
					if row.name in results
				],
			}
		).insert(ignore_permissions=True)
		log_name = log.name
		frappe.db.commit()
	finally:
		frappe.cache.delete_value(RUN_CACHE_KEY)
		publish(total, finished=True)
