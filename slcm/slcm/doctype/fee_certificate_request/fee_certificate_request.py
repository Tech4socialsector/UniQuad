# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, fmt_money, formatdate, getdate, today
from markupsafe import Markup

from slcm.slcm.doctype.academic_year.academic_year import get_current_academic_year
from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import (
	DEFAULT_PAID_LINE,
	MULTI_YEAR,
	SINGLE_YEAR_DEMAND,
	SINGLE_YEAR_RECEIPT,
	get_purpose_template,
)
from slcm.slcm.fee.component_groups import (
	ADMISSION,
	HOUSING,
	MESS,
	READMISSION,
	REFUNDABLE,
	TUITION,
	component_group as _row_group,
)

ADMISSION_STAGE = "Admission Stage"
ORDINALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
DURATION_WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def _amt(amount):
	"""Format like the source templates: '3,18,200' (no currency symbol); '-' for nothing."""
	if not flt(amount):
		return "-"
	return fmt_money(flt(amount), precision=0, currency="INR").replace("₹", "").strip()


# Certificate rows are Fee Components in group order (slcm.slcm.fee.component_groups),
# then any other component in the order its demand was raised.
# Printed particulars for the per-annum groups; every other component prints as
# "<name> – one time".
PER_ANNUM_LABELS = {
	TUITION: "Tuition and Facilities fee – per annum",
	HOUSING: "Housing fee – per annum",
	MESS: "Mess Charges – per annum",
}
# Admission Fee prints for the student's first programme year only ("-" later).
# Charged once, so never repeated into a later year that has no fee data of its own:
ONE_TIME_GROUPS = {ADMISSION, READMISSION, REFUNDABLE}
ONE_TIME_TYPES = {"Application Fee"}


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
		if self.certificate_type == SINGLE_YEAR_RECEIPT and not self.from_academic_year:
			# A receipt is for the chosen Academic Year; the current one when none is chosen.
			self.from_academic_year = get_current_academic_year()
		self.to_academic_year = None
		self._set_identity()
		check_not_fully_paid(self)
		self._validate_edited_certificate()

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

	def _validate_edited_certificate(self):
		if self.edited_certificate and not self.edited_certificate.lower().endswith(".pdf"):
			frappe.throw(_("The edited certificate must be a PDF file."))
		if self.has_value_changed("edited_certificate"):
			if self.edited_certificate:
				self.edited_by, self.edited_on = frappe.session.user, frappe.utils.now_datetime()
			else:
				self.edited_by = self.edited_on = None
				self.edited_word_file = None

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
		registration_id=applicant.name,
		application_number=applicant.name,
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
	# At least up to the chosen year and the current Academic Year, so a student is never
	# cut off before the year they are in (e.g. a programme with no duration recorded).
	needed = getdate(first_year.year_start_date).year - start + 1
	current_ay = get_current_academic_year()
	current_start = frappe.db.get_value("Academic Year", current_ay, "year_start_date") if current_ay else None
	if current_start:
		needed = max(needed, getdate(current_start).year - start + 1)
	rows = []
	for i in range(max(_programme_duration(student_doc), needed, 1)):
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
	(the student portal renders certificates for the logged-in student). Callers
	that already checked access (page roles, portal ownership) set
	frappe.flags.ignore_print_permissions."""
	if frappe.flags.ignore_print_permissions or request.has_permission("read"):
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


def _years_in_text(text):
	"""Years from "5", "Five", "5 years" or a programme name such as "5-Year B.A., LL.B.
	(Hons.)", "1- Year LL.M." or "Bridge Course- Two Year"; 0 if none."""
	import re

	text = (text or "").strip().lower()
	if not text:
		return 0
	first = text.split()[0]
	if first in DURATION_WORDS:
		return DURATION_WORDS.index(first) + 1
	if cint(first):
		return cint(first)
	match = re.search(r"(\d+|" + "|".join(DURATION_WORDS) + r")\s*-?\s*years?\b", text)
	if not match:
		return 0
	value = match.group(1)
	return cint(value) if value.isdigit() else DURATION_WORDS.index(value) + 1


def _office_duration(name):
	"""Course length from the office's Education Loan fee-structure list: BA LLB Hons 5,
	LLB Hons 3, LLM 1, MPP 2, BA Hons 4 years; 0 when the name matches none (e.g. Ph.D)."""
	import re

	text = (name or "").lower()
	letters = re.sub(r"[^a-z]", "", text)
	if not letters or "phd" in letters:
		return 0
	if "llm" in letters:
		return 1
	if "publicpolicy" in letters or letters.startswith("mpp"):
		return 2
	if "ballb" in letters:
		return 5
	if "llb" in letters:
		return 3
	if re.search(r"\bb\.?\s*a\b.*hons", text):
		return 4
	return 0


def _programme_duration(student):
	"""Programme length in years. The office's Education Loan list (_office_duration:
	BA LLB 5, LLB 3, LLM 1, MPP 2, BA Hons 4) comes first, because the recorded durations
	disagree on live data (e.g. "5-Year LL.B. (Hons.)" is 3 on Programme but 5 on
	Programme Master). Then Programme.program_duration, Programme Master "Programme
	duration (in years)" ("5" or "Five"), and last the years in the name ("Two Year")."""
	master, programme_years, name = student.master_programme, 0, None
	if student.programme_of_study:
		name, programme_years = frappe.db.get_value(
			"Programme", student.programme_of_study, ["program_name", "program_duration"]
		) or (None, 0)
		master = master or name
	texts = (name, master, student.programme_of_study)
	for text in texts:
		years = _office_duration(text)
		if years:
			return years
	if cint(programme_years):
		return cint(programme_years)
	if master:
		years = _years_in_text(frappe.db.get_value("Programme Master", master, "programme_duration_in_years"))
		if years:
			return years
	for text in texts:
		years = _years_in_text(text)
		if years:
			return years
	return 0


def _programme_title(programme, duration):
	"""The programme as printed with its length: "5-Year LL.B. (Hons.)", "4-Year BA (Hons)"
	(any "N-Year" already in the name is replaced by the duration)."""
	import re

	name = re.sub(r"^\s*\d+\s*-?\s*years?\s*", "", programme or "", flags=re.I).strip()
	if not duration or not name or re.search(r"\byears?\b", name, re.I) or name.lower().startswith("master"):
		return programme or ""
	return f"{duration}-Year {name}"


def _year_offset(student, academic_year_doc):
	if not student or not student.academic_year:
		return None
	try:
		batch_start = frappe.get_doc("Academic Year", student.academic_year)
	except frappe.DoesNotExistError:
		return None
	return academic_year_doc.year_start_date.year - batch_start.year_start_date.year


def _ordinal_year_for(student, academic_year_doc):
	"""Roman-numeral ordinal (I/II/III...) of the student's year of study in
	academic_year_doc, counted from their joining year (Student Master academic_year):
	joined 2023-24 -> 2023-24 I, 2024-25 II, 2025-26 III, 2026-27 IV."""
	diff = _year_offset(student, academic_year_doc)
	if diff is None or diff < 0:
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
	"""{Fee Component name: {original, waiver, paid, outstanding}} for one year —
	from the student's Fee Demands, falling back to their assigned Fee Structure
	(if it is for this year) when no demands have been raised yet, e.g. an applicant."""
	if student.get("is_applicant"):
		return _applicant_component_totals(student, academic_year)
	totals = {}
	if academic_year:
		demands = frappe.get_all(
			"Fee Demand",
			filters={"student": student.name, "academic_year": academic_year, "status": ["!=", "Cancelled"]},
			fields=[
				"fee_component", "original_amount", "penalty_amount", "waiver_amount", "net_payable",
				"paid_amount", "outstanding_amount",
			],
			order_by="creation asc",
		)
		for d in demands:
			row = totals.setdefault(
				d.fee_component,
				{"original": 0, "penalty": 0, "waiver": 0, "net": 0, "paid": 0, "outstanding": 0},
			)
			row["original"] += flt(d.original_amount)
			row["penalty"] += flt(d.penalty_amount)
			row["waiver"] += flt(d.waiver_amount)
			row["net"] += flt(d.net_payable)
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
			order_by="idx asc",
		)
		for c in components:
			row = totals.setdefault(
				c.fee_component,
				{"original": 0, "penalty": 0, "waiver": 0, "net": 0, "paid": 0, "outstanding": 0},
			)
			row["original"] += flt(c.amount)
			row["net"] += flt(c.amount)
			row["outstanding"] += flt(c.amount)
	return totals


def _applicant_component_totals(applicant, academic_year):
	"""Same shape as _component_totals for an admission-stage applicant: their
	Applicant Fee Assignment(s) for the year, else the programme's Fee Structure;
	paid amounts from their submitted Applicant Payment Receipts."""
	totals = {}
	if not academic_year:
		return totals

	def row(fee_component):
		return totals.setdefault(
			fee_component, {"original": 0, "penalty": 0, "waiver": 0, "net": 0, "paid": 0, "outstanding": 0}
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

	for c in components:
		row(c.fee_component)["original"] += flt(c.amount)
	for c in paid:
		row(c.fee_component)["paid"] += flt(c.amount)
	if totals and waiver:
		next(iter(totals.values()))["waiver"] += waiver
	for r in totals.values():
		r["net"] = r["original"] - r["waiver"]
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


def _ordered_components(components):
	"""Fee Component names by group (Admission, Re-admission, Tuition, Housing,
	Refundable Deposit), the rest after in their original order."""
	components = list(dict.fromkeys(components))
	types = _component_types(components)
	return sorted(components, key=lambda c: _row_group(c, types.get(c)))


def _balance(year):
	"""What is left to pay for one certificate year (column): what is still outstanding on
	the year's own demands, or, for a year with no demands yet, its fees less scholarship."""
	if year.get("has_demands"):
		return max(flt(year.get("outstanding")), 0)
	return max(sum(year["amounts"].values()) - year["waiver"] - flt(year["paid"]), 0)


def _year_amounts(totals, certificate_type, has_scholarship):
	"""{Fee Component: amount} as printed for one year, plus the scholarship deduction.

	Each amount is the demand's Total Fee Payable (Fee Demand original_amount, the
	"Total Fee Payable" column on Student Fee Management). With the request's
	scholarship box ticked, the waiver is returned for the "Less: University
	Scholarship" row (giving the Net Fee payable line)."""
	if certificate_type == SINGLE_YEAR_RECEIPT:
		return {t: a["original"] for t, a in totals.items() if a["original"]}, 0
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
	that has Fee Demands. fee is the year's Total Fee Payable, less the scholarship
	(waiver) when the request has one, matching the table."""
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


def pdf_true_scale():
	"""True when wkhtmltopdf is the patched-Qt build (Frappe Cloud, the official packages): it
	honours --disable-smart-shrinking and lays CSS out 1:1. The unpatched build (e.g. Ubuntu's
	apt package) shrinks CSS to about 0.75, which the certificate was designed at, so on the
	patched build the certificate is zoomed to 0.75 to get the same page."""
	patched = frappe.cache.get_value("slcm_wkhtmltopdf_patched_qt")
	if patched is None:
		import subprocess

		try:
			out = subprocess.check_output(["wkhtmltopdf", "--version"], timeout=10).decode().lower()
			patched = int("patched qt" in out)
		except Exception:
			patched = 0
		frappe.cache.set_value("slcm_wkhtmltopdf_patched_qt", patched)
	return bool(cint(patched))


@frappe.whitelist()
def get_fee_certificate_context(request_name):
	request = frappe.get_doc("Fee Certificate Request", request_name)
	_check_read_access(request)

	student = get_subject(request)
	settings = frappe.get_single("Fee Certificate Settings")
	template = get_purpose_template(request.purpose)
	certificate_type = request.certificate_type or (template and template.certificate_type)

	certificate_ay = request.from_academic_year or get_current_academic_year()
	computed_rows = [frappe._dict(row) for row in academic_year_rows(student, certificate_ay, request.purpose)]
	# Saved year rows, unless the programme now has more years than were saved (e.g. a
	# request made while the programme's duration was unknown).
	year_rows = request.years if len(request.years or []) >= len(computed_rows) else computed_rows

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
		# Scholarship per component, so a waiver stays with the fee it was given on.
		component_waivers = {c: flt(a["waiver"]) for c, a in totals.items() if flt(a["waiver"])}
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
				"start_year": getdate(ay.year_start_date).year if ay and ay.year_start_date else cint((row.year_label or "")[:4]),
				"amounts": amounts,
				"waiver": waiver,
				"component_waivers": component_waivers,
				"outstanding": sum(a["outstanding"] for a in totals.values()),
				"paid": sum(a["paid"] for a in totals.values()),
				"has_demands": bool(totals),
			}
		)

	component_types = _component_types([c for y in years for c in y["amounts"]])

	def group(component):
		return _row_group(component, component_types.get(component))

	def one_time(component):
		return group(component) in ONE_TIME_GROUPS or component_types.get(component) in ONE_TIME_TYPES

	if certificate_type == MULTI_YEAR:
		# Fee structure: every column shows the same per-annum fees (Tuition, Housing,
		# Mess) and scholarship, taken from the current Academic Year's demands (or the
		# latest year before it that has them). One-time and other fees show only in the
		# year they were charged. Amount paid / Balance payable stay each year's own.
		current_ay = get_current_academic_year()
		current_start = frappe.db.get_value("Academic Year", current_ay, "year_start_date") if current_ay else None
		current_start = getdate(current_start).year if current_start else None
		reference, reference_waivers = {}, {}
		for y in years:
			if current_start and y["start_year"] > current_start:
				break
			per_annum = {c: a for c, a in y["amounts"].items() if group(c) in PER_ANNUM_LABELS and a}
			if per_annum:
				# Replace by group, so a renamed component doesn't appear twice.
				groups = {group(c) for c in per_annum}
				reference = {c: a for c, a in reference.items() if group(c) not in groups}
				reference.update(per_annum)
				reference_waivers = {c: w for c, w in reference_waivers.items() if group(c) not in groups}
				reference_waivers.update({c: y["component_waivers"].get(c, 0) for c in per_annum})
		for y in years:
			y["amounts"] = {c: a for c, a in y["amounts"].items() if group(c) not in PER_ANNUM_LABELS}
			y["amounts"].update(reference)
			y["component_waivers"] = {
				**{c: w for c, w in y["component_waivers"].items() if group(c) not in PER_ANNUM_LABELS},
				**reference_waivers,
			}
	if certificate_type != SINGLE_YEAR_RECEIPT:
		# Admission Fee belongs to the first year only (programme_year 0 = unknown: keep as is).
		for y in years:
			if y["programme_year"] > 1:
				for t in [c for c in y["amounts"] if group(c) == ADMISSION]:
					y["amounts"].pop(t)
	if certificate_type == MULTI_YEAR and request.has_scholarship:
		# Each column's scholarship = the waivers on the fees it actually shows.
		for y in years:
			y["waiver"] = sum(flt(y["component_waivers"].get(c)) for c in y["amounts"])

	if certificate_type == MULTI_YEAR and years:
		# Show the remaining course only: from the current Academic Year to the final
		# programme year (the chosen year only when no Academic Year is marked current).
		chosen_start = frappe.db.get_value("Academic Year", certificate_ay, "year_start_date")
		from_year = current_start or (getdate(chosen_start).year if chosen_start else 0)
		first = next((i for i, y in enumerate(years) if y["start_year"] >= from_year), len(years) - 1)
		years, unique_rows = years[first:], unique_rows[first:]

	first_ay = frappe.get_doc("Academic Year", certificate_ay)
	current_ay_doc = (
		frappe.get_doc("Academic Year", get_current_academic_year()) if get_current_academic_year() else first_ay
	)
	table = _build_table(years)
	if (
		certificate_type == MULTI_YEAR
		and not student.is_applicant
		and template
		and cint(template.get("show_paid_rows"))
	):
		table["show_paid_rows"] = True
		table["paid_row_label"] = template.get("paid_row_label") or "Amount paid"
		table["outstanding_row_label"] = template.get("outstanding_row_label") or "Balance payable"
		table["paid_row"] = [_amt(y["paid"]) for y in years]
		# Balance: the year's fee less scholarship and payments; "Nil" once a charged year is paid.
		table["outstanding_row"] = [
			"Nil" if _balance(y) <= 0 and (y["has_demands"] or flt(y["paid"])) else _amt(_balance(y))
			for y in years
		]

	# First year from the certificate's year onward that still has fee to pay
	# (the "now required to pay the course fee for III year i.e. AY 2027-28" year).
	# (Multi-year columns already start at the current Academic Year.)
	cert_index = (
		0
		if certificate_type == MULTI_YEAR
		else next((i for i, r in enumerate(unique_rows) if r.academic_year == first_ay.name), 0)
	)
	due = next(
		(
			y
			for y in years[cert_index:]
			if _balance(y) > 0
		),
		years[cert_index] if years else None,
	)

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
		"programme_title": _programme_title(programme, _programme_duration(student)),
		"programme_duration": _duration_words(_programme_duration(student)),
		"academic_year": _short_ay_label(first_ay),
		# Year of study in the requested Academic Year, and now (the current Academic Year),
		# both counted from the student's joining year.
		"current_year": _ordinal_year_for(student, first_ay),
		"studying_year": _ordinal_year_for(student, current_ay_doc),
		"current_academic_year": _short_ay_label(current_ay_doc),
		"due_year": (
			(ORDINALS[due["programme_year"] - 1] if 0 < due["programme_year"] <= len(ORDINALS) else str(due["programme_year"]))
			if due and due["programme_year"]
			else _ordinal_year_for(student, first_ay)
		),
		"due_academic_year": (due["label"] if due else _short_ay_label(first_ay)),
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
		"bank_name": settings.get("bank_name") or "",
		"bank_account_type": settings.get("bank_account_type") or "",
		"bank_table": _bank_table(settings),
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
		# Picks the page-box heights that fit one A4 page for this server's wkhtmltopdf
		"true_scale": pdf_true_scale(),
		"certificate_type": certificate_type,
		"heading": (template and template.heading) or "FEE CERTIFICATE",
		"body_html": render(
			template
			and ((student.is_applicant and template.get("applicant_body_text")) or template.body_text)
		),
		"bank_details_html": render(template and template.bank_details_text) if request.include_bank_details else "",
		"bank_details_source": (template and template.bank_details_text) or "",
		"closing_html": render(template and template.closing_text),
		"total_label": (template and template.total_label) or "Total",
		"generation_date": formatdate(today(), "dd.mm.yyyy"),
		"font_face_css": _merriweather_font_face(),
		"header_image": _trimmed_image_b64(settings.letterhead_header_image),
		"footer_image": _trimmed_image_b64(settings.letterhead_footer_image),
		"signature_image": _trimmed_image_b64(settings.cfo_signature),
		"table": table,
	}


def _bank_table(settings):
	"""University bank account as a two-column label / value list (blank rows skipped)."""
	from frappe.utils import escape_html

	rows = [
		("Account Holder Name", settings.bank_account_name or settings.institute_name),
		("Account Number", settings.bank_account_no),
		("IFSC", settings.bank_ifsc_code),
		("Bank Name", settings.get("bank_name")),
		("Branch", settings.bank_branch),
		("Account Type", settings.get("bank_account_type")),
	]
	body = "".join(
		f'<tr><td style="padding:0 24px 0 0;border:none;white-space:nowrap;">{label}</td>'
		f'<td style="padding:0;border:none;">{escape_html(value)}</td></tr>'
		for label, value in rows
		if value
	)
	return Markup(f'<table class="bank-table" style="border-collapse:collapse;line-height:1.4;">{body}</table>') if body else ""


def _merriweather_font_face():
	"""@font-face rules embedding the app's Merriweather .ttf files as data URIs, so the
	PDF uses Merriweather whether or not the server has the font installed."""
	cache_key = "slcm_fee_certificate_merriweather_css_v2"
	css = frappe.cache.get_value(cache_key)
	if css:
		return Markup(css)
	import base64
	import os

	rules = []
	for file_name, weight, style in (
		("Merriweather-Regular.ttf", "normal", "normal"),
		("Merriweather-Bold.ttf", "bold", "normal"),
		("Merriweather-Italic.ttf", "normal", "italic"),
	):
		path = frappe.get_app_path("slcm", "public", "fonts", file_name)
		if not os.path.exists(path):
			continue
		with open(path, "rb") as f:
			data = base64.b64encode(f.read()).decode()
		# Two spaces after "src:" on purpose: Frappe's expand_relative_urls appends
		# " !important" to any ": url(...)" (one optional space), which would make
		# this src invalid and silently drop the font.
		rules.append(
			"@font-face { font-family: 'Merriweather'; font-weight: %s; font-style: %s; "
			"src:  url(data:font/truetype;charset=utf-8;base64,%s) format('truetype'); }" % (weight, style, data)
		)
	css = "\n".join(rules)
	frappe.cache.set_value(cache_key, css)
	return Markup(css)


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


def _particular_label(component, component_type):
	"""Tuition / Housing: "... – per annum"; anything else: "<component> – one time"."""
	return PER_ANNUM_LABELS.get(_row_group(component, component_type)) or f"{component} – one time"


def _build_table(years):
	"""One row per Fee Component in group order (_row_group), labelled by _particular_label, with each
	year's amount. Components that print the same label (two housing components) share a row."""
	components = _ordered_components([c for y in years for c in y["amounts"]])
	types = _component_types(components)
	merged = {}
	for c in components:
		label = _particular_label(c, types.get(c) or c)
		merged.setdefault(label, [0] * len(years))
		for i, y in enumerate(years):
			merged[label][i] += flt(y["amounts"].get(c))
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


def check_not_fully_paid(request):
	"""A Fee Demand Letter asks for fees still due, so it can't be generated for an
	Academic Year whose fees are already fully paid (there are demands and nothing is
	outstanding). Throws a "Fees Already Paid" message."""
	certificate_type = request.get("certificate_type") or (
		get_purpose_template(request.purpose) and get_purpose_template(request.purpose).certificate_type
	)
	if certificate_type != SINGLE_YEAR_DEMAND or not request.get("from_academic_year"):
		return
	if not (request.get("student") or request.get("applicant")):
		return
	totals = _component_totals(get_subject(request), request.from_academic_year)
	payable = sum(flt(t["original"]) for t in totals.values())
	outstanding = sum(flt(t["outstanding"]) for t in totals.values())
	if payable > 0 and outstanding <= 0:
		ay = frappe.get_doc("Academic Year", request.from_academic_year)
		frappe.throw(
			_(
				"{0} has already paid the fees for AY {1}, so a Fee Demand Letter can't be generated. "
				"Generate the Fee Receipt instead."
			).format(frappe.bold(request.get("student_name") or get_subject(request).first_name), _short_ay_label(ay)),
			title=_("Fees Already Paid"),
		)


def certificate_file(request, file_format="pdf"):
	"""(filename, content, response type) for a certificate download.

	file_format: "pdf" gives the uploaded edited PDF when one is attached, else the
	generated PDF; "generated" always gives the generated PDF; "docx" the Word version.
	Callers do their own permission check."""
	if not (file_format == "pdf" and request.edited_certificate):
		check_not_fully_paid(request)
	base = f"{(request.purpose or 'Fee Certificate').replace('/', '-')} - {(request.student_name or request.name).replace('/', '-')}"
	if file_format == "docx":
		from slcm.slcm.doctype.fee_certificate_request.fee_certificate_docx import build_certificate_docx

		frappe.flags.ignore_print_permissions = True
		try:
			ctx = get_fee_certificate_context(request.name)
		finally:
			frappe.flags.ignore_print_permissions = False
		return f"{base}.docx", build_certificate_docx(ctx), "binary"

	if file_format == "pdf" and request.edited_certificate:
		file_doc = frappe.get_doc("File", {"file_url": request.edited_certificate})
		return f"{base}.pdf", file_doc.get_content(), "pdf"

	frappe.flags.ignore_print_permissions = True
	try:
		pdf = frappe.get_print(
			"Fee Certificate Request", request.name, "Fee Certificate", doc=request, as_pdf=True, no_letterhead=1
		)
	finally:
		frappe.flags.ignore_print_permissions = False
	return f"{base}.pdf", pdf, "pdf"


@frappe.whitelist()
def download(name, file_format="pdf"):
	"""Desk download (form button): needs read permission on the request."""
	request = frappe.get_doc("Fee Certificate Request", name)
	request.check_permission("read")
	filename, content, response_type = certificate_file(request, file_format)
	frappe.local.response.update(filename=filename, filecontent=content, type=response_type)
