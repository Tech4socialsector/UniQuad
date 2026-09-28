# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, fmt_money, formatdate, getdate, today
from markupsafe import Markup

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import (
	DEFAULT_PAID_LINE,
	MULTI_YEAR,
	SINGLE_YEAR_RECEIPT,
	get_purpose_template,
)

ADMISSION_STAGE = "Admission Stage"
ORDINALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
DURATION_WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def _amt(amount):
	"""Format like the source templates: '3,18,200' (no currency symbol); '-' for nothing."""
	if not flt(amount):
		return "-"
	return fmt_money(flt(amount), precision=0, currency="INR").replace("₹", "").strip()


# Fee Component.component_type -> row label used on the certificate, and the
# order those rows appear in. Anything not listed here falls back to its own
# component_type text and is appended after these standard rows.
ROW_DEFS = [
	("Admission Fee", "Admission Fee - one time"),
	("Re-admission Fee", "Re-admission Fee - one time"),
	("Tuition and Facilities Fee", "Tuition and Facilities fee – per annum"),
	("Hostel Fee", "Housing fee – per annum"),
	("Housing and Mess Fee", "Housing fee – per annum"),
	("Mess Charges", "Mess Charges – per annum"),
	("Student Refundable Deposit", "Refundable Deposits – one time"),
]
ROW_LABELS = dict(ROW_DEFS)
ROW_ORDER = [key for key, _label in ROW_DEFS]
# Printed only for the student's first year of the programme ("-" in later years).
FIRST_YEAR_ONLY_TYPES = {"Admission Fee"}
# Charged once, so never repeated into a later year that has no fee data of its own.
ONE_TIME_TYPES = {"Admission Fee", "Re-admission Fee", "Student Refundable Deposit", "Application Fee"}


class FeeCertificateRequest(Document):
	def validate(self):
		template = get_purpose_template(self.purpose)
		if not template:
			frappe.throw(
				_("Purpose {0} is not configured in Fee Certificate Settings").format(frappe.bold(self.purpose))
			)
		if self.purpose_changed():
			self.include_bank_details = template.include_bank_details
		self.certificate_type = template.certificate_type
		self.certificate_mode = "Multi Year" if self.certificate_type == MULTI_YEAR else "Single Year"
		self.to_academic_year = None
		self._set_identity()

		if (
			not self.years
			or self.purpose_changed()
			or self.has_value_changed("from_academic_year")
			or self.has_value_changed("student")
			or self.has_value_changed("applicant")
			or self.has_value_changed("certificate_for")
		):
			self.set("years", [])
			for row in academic_year_rows(get_subject(self), self.from_academic_year, self.purpose):
				self.append("years", row)
		self._drop_duplicate_years()

	def _set_identity(self):
		"""Fill name / programme / numbers from the Student Master or the Applicant."""
		self.certificate_for = self.certificate_for or "Campus Student"
		if self.certificate_for == ADMISSION_STAGE:
			if not self.applicant:
				frappe.throw(_("Please select the Applicant"))
			self.student = None
			self.registration_id = None
			self.level_of_study = None
		else:
			if not self.student:
				frappe.throw(_("Please select the Student"))
			self.applicant = None
			self.application_number = None
			self.admit_card_number = None
		subject = get_subject(self)
		self.student_name = subject.first_name
		self.programme = subject.programme_of_study
		if self.certificate_for == ADMISSION_STAGE:
			self.application_number = subject.application_number
			self.admit_card_number = self.admit_card_number or subject.admit_card_number

	def _drop_duplicate_years(self):
		seen = set()
		for row in list(self.years):
			key = (row.academic_year, (row.year_label or "").strip())
			if key in seen:
				self.remove(row)
			seen.add(key)
		for idx, row in enumerate(self.years, 1):
			row.idx = idx

	def purpose_changed(self):
		return self.is_new() or self.has_value_changed("purpose")


@frappe.whitelist()
def preview_academic_years(student=None, from_academic_year=None, purpose=None, applicant=None):
	"""Column rows for the Year-wise Breakdown table: one year for single-year
	purposes; for a multi-year one, every year of the programme from the student's
	first year. Pure computation, so the client can fill an unsaved form without
	clobbering edits."""
	frappe.has_permission("Fee Certificate Request", ptype="read", throw=True)
	if not (student or applicant):
		return []
	subject = get_subject(
		frappe._dict(
			certificate_for=ADMISSION_STAGE if applicant else "Campus Student", student=student, applicant=applicant
		)
	)
	return academic_year_rows(subject, from_academic_year, purpose)


def get_subject(request):
	"""The person the certificate is about, as one dict whatever their stage.
	Keys follow Student Master (first_name, registration_id, academic_year = batch
	start year, programme_of_study, master_programme, fee_structure) plus
	is_applicant / application_number / admit_card_number."""
	if (request.get("certificate_for") or "Campus Student") != ADMISSION_STAGE:
		student = frappe.get_doc("Student Master", request.get("student"))
		subject = frappe._dict(student.as_dict())
		subject.is_applicant = False
		return subject

	applicant = frappe.get_doc("Applicant", request.get("applicant"))
	admit_card = frappe.db.get_value(
		"Entrance Test Seat Allocation",
		{"applicant": applicant.name, "admit_card_number": ["is", "set"]},
		"admit_card_number",
		order_by="creation desc",
	)
	return frappe._dict(
		name=applicant.name,
		is_applicant=True,
		first_name=applicant.candidate_name or applicant.name,
		registration_id=applicant.applicant_id or applicant.name,
		application_number=applicant.applicant_id or applicant.name,
		admit_card_number=admit_card,
		academic_year=applicant.academic_year,
		programme_of_study=applicant.program,
		master_programme=frappe.db.get_value("Programme", applicant.program, "program_name") if applicant.program else None,
		nationality=applicant.nationality,
		fee_structure=None,
	)


def academic_year_rows(student_doc, from_academic_year, purpose=None):
	"""student_doc: a get_subject() dict (or a Student Master name)."""
	if not student_doc or not from_academic_year:
		return []
	if isinstance(student_doc, str):
		student_doc = get_subject(frappe._dict(student=student_doc))

	template = get_purpose_template(purpose)
	first_year = frappe.get_doc("Academic Year", from_academic_year)
	offset = _year_offset(student_doc, first_year)
	if not template or template.certificate_type != MULTI_YEAR:
		return [
			{
				"academic_year": first_year.name,
				"year_label": _short_ay_label(first_year),
				"programme_year": offset + 1 if offset is not None and offset >= 0 else 0,
			}
		]

	# Programme year 1 = the student's batch start year (or the chosen year when
	# the student has none / it is later than the chosen one).
	start = getdate(first_year.year_start_date).year - (offset if offset and offset > 0 else 0)
	existing = {
		getdate(ay.year_start_date).year: ay.name
		for ay in frappe.get_all("Academic Year", fields=["name", "year_start_date"])
		if ay.year_start_date
	}
	rows = []
	for i in range(_programme_duration(student_doc) or 1):
		year = start + i
		rows.append(
			{
				"academic_year": existing.get(year),
				"year_label": f"{year}-{str(year + 1)[-2:]}",
				"programme_year": i + 1,
			}
		)
	return rows


@frappe.whitelist()
def mark_generated(name):
	doc = frappe.get_doc("Fee Certificate Request", name)
	doc.check_permission("write")
	doc.db_set("status", "Generated")
	doc.db_set("generated_on", frappe.utils.now_datetime())


def _check_read_access(request):
	"""Desk users need read permission; a student may read their own requests
	(the student portal renders certificates for the logged-in student)."""
	if request.has_permission("read"):
		return
	user = frappe.session.user
	if user != "Guest":
		# Same lookup the student portal uses to find the logged-in student.
		linked = frappe.db.get_value(
			"Student Master", request.student, ["user", "email", "official_email_id"], as_dict=True
		)
		if linked and user in (linked.user, linked.email, linked.official_email_id):
			return
	raise frappe.PermissionError


def _short_ay_label(academic_year_doc):
	if not academic_year_doc.year_start_date:
		return academic_year_doc.academic_year_name or academic_year_doc.name
	year = getdate(academic_year_doc.year_start_date).year
	return f"{year}-{str(year + 1)[-2:]}"


def _programme_duration(student):
	"""Programme length in years, from Programme Master's "Programme duration
	(in years)" (free text: "5" or "Five"), falling back to Programme.program_duration."""
	master, programme_years = student.master_programme, 0
	if student.programme_of_study:
		name, programme_years = frappe.db.get_value(
			"Programme", student.programme_of_study, ["program_name", "program_duration"]
		) or (None, 0)
		master = master or name
	if master:
		text = (frappe.db.get_value("Programme Master", master, "programme_duration_in_years") or "").strip().lower()
		if text.split() and text.split()[0] in DURATION_WORDS:
			return DURATION_WORDS.index(text.split()[0]) + 1
		if cint(text.split()[0] if text.split() else 0):
			return cint(text.split()[0])
	return cint(programme_years)


def _year_offset(student, academic_year_doc):
	if not student or not student.academic_year:
		return None
	try:
		batch_start = frappe.get_doc("Academic Year", student.academic_year)
	except frappe.DoesNotExistError:
		return None
	return academic_year_doc.year_start_date.year - batch_start.year_start_date.year


def _ordinal_year_for(student, academic_year_doc):
	"""Roman-numeral ordinal (I/II/III...) of the student's year of study."""
	diff = _year_offset(student, academic_year_doc)
	if diff is None:
		return ""
	if 0 <= diff < len(ORDINALS):
		return ORDINALS[diff]
	return str(diff + 1)


def _duration_words(years):
	if not years:
		return ""
	word = DURATION_WORDS[years - 1] if years <= len(DURATION_WORDS) else str(years)
	return f"{word} year" if years == 1 else f"{word} years"


def _component_totals(student, academic_year):
	"""{component_type: {original, waiver, paid, outstanding}} for one year —
	from the student's Fee Demands, falling back to their assigned Fee Structure
	(if it is for this year) when no demands have been raised yet, e.g. an applicant."""
	if student.get("is_applicant"):
		return _applicant_component_totals(student, academic_year)
	totals = {}
	if academic_year:
		demands = frappe.get_all(
			"Fee Demand",
			filters={"student": student.name, "academic_year": academic_year, "status": ["!=", "Cancelled"]},
			fields=["fee_component", "original_amount", "waiver_amount", "paid_amount", "outstanding_amount"],
		)
		types = _component_types([d.fee_component for d in demands])
		for d in demands:
			row = totals.setdefault(
				types.get(d.fee_component) or d.fee_component,
				{"original": 0, "waiver": 0, "paid": 0, "outstanding": 0},
			)
			row["original"] += flt(d.original_amount)
			row["waiver"] += flt(d.waiver_amount)
			row["paid"] += flt(d.paid_amount)
			row["outstanding"] += flt(d.outstanding_amount)

	if (
		not totals
		and academic_year
		and student.fee_structure
		and frappe.db.get_value("Fee Structure", student.fee_structure, "academic_year") == academic_year
	):
		components = frappe.get_all(
			"Fee Component Child",
			filters={
				"parent": student.fee_structure,
				"parenttype": "Fee Structure",
				"parentfield": "fee_components_for_indian",
			},
			fields=["fee_component", "amount"],
		)
		types = _component_types([c.fee_component for c in components])
		for c in components:
			row = totals.setdefault(
				types.get(c.fee_component) or c.fee_component,
				{"original": 0, "waiver": 0, "paid": 0, "outstanding": 0},
			)
			row["original"] += flt(c.amount)
			row["outstanding"] += flt(c.amount)
	return totals


def _applicant_component_totals(applicant, academic_year):
	"""Same shape as _component_totals for an admission-stage applicant: their
	Applicant Fee Assignment(s) for the year, else the programme's Fee Structure;
	paid amounts from their submitted Applicant Payment Receipts."""
	totals = {}
	if not academic_year:
		return totals

	def row(fee_component, types):
		return totals.setdefault(
			types.get(fee_component) or fee_component, {"original": 0, "waiver": 0, "paid": 0, "outstanding": 0}
		)

	assignments = frappe.get_all(
		"Applicant Fee Assignment",
		filters={
			"applicant": applicant.name,
			"academic_year": academic_year,
			"docstatus": ["<", 2],
			"status": ["not in", ["Cancelled", "Withdrawn"]],
		},
		fields=["name", "scholarship_amount"],
	)
	components = []
	if assignments:
		components = frappe.get_all(
			"Applicant Fee Component Child",
			filters={"parenttype": "Applicant Fee Assignment", "parent": ["in", [a.name for a in assignments]]},
			fields=["fee_component", "amount"],
		)
	waiver = sum(flt(a.scholarship_amount) for a in assignments) if components else 0
	if not components and applicant.programme_of_study:
		structures = frappe.get_all(
			"Fee Structure",
			filters={"program": applicant.programme_of_study, "academic_year": academic_year, "status": "Active"},
			fields=["name", "applicable"],
			order_by="creation desc",
		)
		structure = next((f for f in structures if f.applicable == "Applicant"), structures[0] if structures else None)
		if structure:
			field = "fee_components_for_indian" if (applicant.nationality or "Indian") == "Indian" else "fee_components_for_foreign"
			components = frappe.get_all(
				"Fee Component Child",
				filters={"parenttype": "Fee Structure", "parent": structure.name, "parentfield": field},
				fields=["fee_component", "amount"],
			)

	receipts = frappe.get_all(
		"Applicant Payment Receipt",
		filters={"applicant": applicant.name, "academic_year": academic_year, "docstatus": 1},
		pluck="name",
	)
	paid = []
	if receipts:
		paid = frappe.get_all(
			"Applicant Receipt Component",
			filters={"parenttype": "Applicant Payment Receipt", "parent": ["in", receipts]},
			fields=["fee_component", "amount"],
		)

	types = _component_types([c.fee_component for c in components + paid])
	for c in components:
		row(c.fee_component, types)["original"] += flt(c.amount)
	for c in paid:
		row(c.fee_component, types)["paid"] += flt(c.amount)
	if totals and waiver:
		next(iter(totals.values()))["waiver"] += waiver
	for r in totals.values():
		r["outstanding"] = max(r["original"] - r["waiver"] - r["paid"], 0)
	return totals


def _component_types(fee_components):
	if not fee_components:
		return {}
	return frappe._dict(
		frappe.get_all(
			"Fee Component",
			filters={"name": ["in", list(set(fee_components))]},
			fields=["name", "component_type"],
			as_list=1,
		)
	)


def _ordered_types(types):
	types = list(dict.fromkeys(types))
	ordered = [t for t in ROW_ORDER if t in types]
	return ordered + [t for t in types if t not in ordered]


def _year_amounts(totals, certificate_type, has_scholarship):
	"""{component_type: amount} as printed for one year, plus the scholarship deduction."""
	if certificate_type == SINGLE_YEAR_RECEIPT:
		return {t: a["paid"] for t, a in totals.items() if a["paid"]}, 0
	amounts = {t: a["original"] for t, a in totals.items()}
	waiver = sum(a["waiver"] for a in totals.values()) if has_scholarship else 0
	return amounts, waiver


def _long_ay_label(academic_year_doc):
	if not academic_year_doc.year_start_date:
		return academic_year_doc.academic_year_name or academic_year_doc.name
	year = getdate(academic_year_doc.year_start_date).year
	return f"{year}-{year + 1}"


def _earlier_years(student, before_academic_year, has_scholarship):
	"""[(label "2025-2026", fee, paid)] for each academic year the student has
	already studied before the certificate's first year (from their batch start)
	that has Fee Demands. fee is the year's overall total: original fee, less the
	scholarship (waiver) when the request has one."""
	if student.get("is_applicant"):
		return []
	if not (student.academic_year and frappe.db.exists("Academic Year", student.academic_year)):
		return []
	start = getdate(frappe.db.get_value("Academic Year", student.academic_year, "year_start_date"))
	years = frappe.get_all(
		"Academic Year",
		filters={"year_start_date": [">=", start]},
		fields=["name", "year_start_date"],
		order_by="year_start_date asc",
	)
	result = []
	for ay in years:
		if getdate(ay.year_start_date) >= getdate(before_academic_year.year_start_date):
			break
		demands = frappe.get_all(
			"Fee Demand",
			filters={"student": student.name, "academic_year": ay.name, "status": ["!=", "Cancelled"]},
			fields=["original_amount", "waiver_amount", "paid_amount"],
		)
		if demands:
			result.append(
				(
					_long_ay_label(ay),
					sum(flt(d.original_amount) - (flt(d.waiver_amount) if has_scholarship else 0) for d in demands),
					sum(flt(d.paid_amount) for d in demands),
				)
			)
	return result


@frappe.whitelist()
def get_fee_certificate_context(request_name):
	request = frappe.get_doc("Fee Certificate Request", request_name)
	_check_read_access(request)

	student = get_subject(request)
	settings = frappe.get_single("Fee Certificate Settings")
	template = get_purpose_template(request.purpose)
	certificate_type = request.certificate_type or (template and template.certificate_type)

	year_rows = request.years or [
		frappe._dict(row) for row in academic_year_rows(student, request.from_academic_year, request.purpose)
	]

	seen, unique_rows = set(), []
	for row in year_rows:
		key = (row.academic_year, (row.year_label or "").strip())
		if key not in seen:
			seen.add(key)
			unique_rows.append(row)

	years = []
	for row in unique_rows:
		totals = _component_totals(student, row.academic_year)
		amounts, waiver = _year_amounts(totals, certificate_type, request.has_scholarship)
		ay = frappe.get_doc("Academic Year", row.academic_year) if row.academic_year else None
		programme_year = cint(row.get("programme_year"))
		if not programme_year and ay:
			offset = _year_offset(student, ay)
			programme_year = offset + 1 if offset is not None and offset >= 0 else 0
		years.append(
			{
				"label": row.year_label or row.academic_year or "",
				"long_label": _long_ay_label(ay) if ay else (row.year_label or ""),
				"has_academic_year": bool(ay),
				"programme_year": programme_year,
				"amounts": amounts,
				"waiver": waiver,
				"paid": sum(a["paid"] for a in totals.values()),
			}
		)

	if certificate_type == MULTI_YEAR:
		# A year with no fee data of its own (a future year) repeats the per-annum
		# fees of the latest earlier year that has data; one-time fees aren't repeated.
		last = None
		for y in years:
			if y["amounts"]:
				last = y
			elif last:
				y["amounts"] = {t: a for t, a in last["amounts"].items() if t not in ONE_TIME_TYPES}
				y["waiver"] = last["waiver"]
	if certificate_type != SINGLE_YEAR_RECEIPT:
		# Admission Fee belongs to the first year only (programme_year 0 = unknown: keep as is).
		for y in years:
			if y["programme_year"] > 1:
				for t in FIRST_YEAR_ONLY_TYPES:
					y["amounts"].pop(t, None)

	table = _build_table(years)

	first_ay = frappe.get_doc("Academic Year", request.from_academic_year)
	programme = (
		frappe.db.get_value("Programme", student.programme_of_study, "program_name") or student.programme_of_study or ""
	)
	placeholders = {
		"student_name": student.first_name or "",
		"admit_card_number": request.admit_card_number or student.admit_card_number or "-",
		"application_number": request.application_number or student.application_number or "-",
		"registration_id": student.registration_id or student.name,
		"student_id": student.registration_id or student.name,
		"programme": programme,
		"programme_duration": _duration_words(_programme_duration(student)),
		"academic_year": _short_ay_label(first_ay),
		"current_year": _ordinal_year_for(student, first_ay),
		# The certificate year's total as on the table (after any scholarship), for "Rs. ___".
		"year_fee": _amt(
			next(
				(sum(y["amounts"].values()) - y["waiver"] for r, y in zip(unique_rows, years) if r.academic_year == first_ay.name),
				sum(years[0]["amounts"].values()) - years[0]["waiver"] if years else 0,
			)
		),
		"institute_name": settings.institute_name or "",
		"bank_account_name": settings.bank_account_name or settings.institute_name or "",
		"bank_account_no": settings.bank_account_no or "",
		"bank_ifsc_code": settings.bank_ifsc_code or "",
		"bank_branch": settings.bank_branch or "",
	}

	# One line per year: years already studied before the table's first column,
	# then every column that has an Academic Year record (adding an Academic Year
	# adds its line, with the same total as its column).
	first_column = next(
		(frappe.get_doc("Academic Year", r.academic_year) for r in unique_rows if r.academic_year), first_ay
	)
	year_lines = _earlier_years(student, first_column, request.has_scholarship) + [
		(y["long_label"], sum(y["amounts"].values()) - y["waiver"], y["paid"]) for y in years if y["has_academic_year"]
	]
	paid_line = (template and template.paid_line_text) or DEFAULT_PAID_LINE
	placeholders["paid_summary"] = Markup(
		"".join(
			"<p>{}</p>".format(
				frappe.render_template(
					paid_line,
					{
						"academic_year": label,
						"fee_amount": _amt(fee) if fee else "0",
						"paid_amount": _amt(paid) if paid else "0",
						"is_paid": flt(paid) > 0,
					},
				)
			)
			for label, fee, paid in year_lines
		)
	)

	def render(text):
		return frappe.render_template(text, placeholders) if text else ""

	return {
		"request": request.as_dict(),
		"settings": settings.as_dict(),
		"certificate_type": certificate_type,
		"heading": (template and template.heading) or "FEE CERTIFICATE",
		"body_html": render(
			template
			and ((student.is_applicant and template.get("applicant_body_text")) or template.body_text)
		),
		"bank_details_html": render(template and template.bank_details_text) if request.include_bank_details else "",
		"closing_html": render(template and template.closing_text),
		"total_label": (template and template.total_label) or "Total",
		"generation_date": formatdate(today(), "dd.mm.yyyy"),
		"header_image": _trimmed_image_b64(settings.letterhead_header_image),
		"footer_image": _trimmed_image_b64(settings.letterhead_footer_image),
		"signature_image": _trimmed_image_b64(settings.cfo_signature),
		"table": table,
	}


def _trimmed_image_b64(file_url):
	"""Base64 PNG of an attached image with its blank (white/transparent) border
	cropped, so letterhead artwork lines up exactly with the page margins."""
	if not file_url:
		return ""
	import base64
	from io import BytesIO

	from PIL import Image, ImageOps

	from slcm.admission.utils.jinja import get_file_b64

	raw = get_file_b64(file_url)
	if not raw:
		return ""
	try:
		img = Image.open(BytesIO(base64.b64decode(raw))).convert("RGBA")
		flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
		flat.alpha_composite(img)
		mask = ImageOps.invert(flat.convert("L")).point(lambda v: 255 if v > 40 else 0)
		bbox = mask.getbbox()
		if bbox:
			img = img.crop(bbox)
		out = BytesIO()
		img.save(out, format="PNG")
		return base64.b64encode(out.getvalue()).decode()
	except Exception:
		return raw


def _build_table(years):
	types = _ordered_types([t for y in years for t in y["amounts"]])
	# Two component types can share a printed label (e.g. hostel variants) —
	# merge them so the table doesn't show the same particulars twice.
	merged = {}
	for t in types:
		label = ROW_LABELS.get(t, t)
		merged.setdefault(label, [0] * len(years))
		for i, y in enumerate(years):
			merged[label][i] += flt(y["amounts"].get(t))
	rows = [{"particulars": label, "amounts": [_amt(a) for a in amounts]} for label, amounts in merged.items()]

	totals = [sum(y["amounts"].values()) for y in years]
	show_scholarship = any(y["waiver"] for y in years)
	return {
		"year_labels": [y["label"] for y in years],
		"rows": rows,
		"total_row": [_amt(t) for t in totals],
		"show_scholarship_row": show_scholarship,
		"scholarship_row": [_amt(y["waiver"]) for y in years] if show_scholarship else [],
		"net_row": [_amt(t - y["waiver"]) for t, y in zip(totals, years)] if show_scholarship else [],
	}
