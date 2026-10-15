# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime


class ExamAssessmentSchedule(Document):
	def validate(self):
		self.validate_term()
		self.validate_exam_plan()
		self.validate_duplicate_schedule()
		self.validate_rows()

	def validate_term(self):
		term_year = frappe.db.get_value("Academic Term", self.term, "academic_year")
		if term_year and term_year != self.academic_year:
			frappe.throw(
				_("Term {0} belongs to Academic Year {1}, not {2}.").format(
					frappe.bold(self.term), frappe.bold(term_year), frappe.bold(self.academic_year)
				)
			)

	def validate_exam_plan(self):
		if not self.exam_plan:
			return
		plan_term = frappe.db.get_value("Exam Plan", self.exam_plan, "term")
		if plan_term and plan_term != self.term:
			frappe.throw(
				_("Exam Plan {0} is for term {1}, not {2}.").format(
					frappe.bold(self.exam_plan), frappe.bold(plan_term), frappe.bold(self.term)
				)
			)

	def validate_duplicate_schedule(self):
		if self.status != "Active":
			return
		existing = frappe.db.get_value(
			"Exam Assessment Schedule",
			{
				"term": self.term,
				"programme": self.programme,
				"status": "Active",
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw(
				_("An active Assessment Schedule {0} already exists for {1} in {2}.").format(
					frappe.bold(existing), frappe.bold(self.programme), frappe.bold(self.term)
				)
			)

	def validate_rows(self):
		offerings = {
			o.name: o
			for o in frappe.get_all(
				"Course Offering",
				filters={"name": ["in", list({r.course_offering for r in self.assessments if r.course_offering})]},
				fields=["name", "program", "term_name"],
			)
		}
		seen = set()
		for row in self.assessments:
			co = offerings.get(row.course_offering)
			if co and (co.program != self.programme or co.term_name != self.term):
				frappe.throw(
					_("Row {0}: Course Offering {1} does not belong to Programme {2} / Term {3}.").format(
						row.idx, frappe.bold(row.course_offering), self.programme, self.term
					)
				)

			key = (row.course_offering, (row.assessment_label or "").strip().lower())
			if key in seen:
				frappe.throw(
					_("Row {0}: Assessment {1} is listed more than once for {2}.").format(
						row.idx, frappe.bold(row.assessment_label), frappe.bold(row.course_name or row.course_offering)
					)
				)
			seen.add(key)

			start = get_datetime(row.assessment_date) if row.assessment_date else None
			first = get_datetime(row.first_submission_deadline) if row.first_submission_deadline else None
			second = get_datetime(row.second_submission_deadline) if row.second_submission_deadline else None

			if second and not first:
				frappe.throw(
					_("Row {0}: Set the First Submission Deadline before the Second Submission Deadline.").format(row.idx)
				)
			if start and first and first < start:
				frappe.throw(
					_("Row {0}: First Submission Deadline cannot be before the Assessment Date.").format(row.idx)
				)
			if first and second and second <= first:
				frappe.throw(
					_("Row {0}: Second Submission Deadline must be after the First Submission Deadline.").format(row.idx)
				)

			marks_by = get_datetime(row.marks_entry_deadline) if row.marks_entry_deadline else None
			closes = second or first or start
			if marks_by and closes and marks_by <= closes:
				frappe.throw(
					_("Row {0}: Marks Entry Deadline must be after the last submission deadline.").format(row.idx)
				)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def programme_query(doctype, txt, searchfield, start, page_len, filters):
	"""Programmes that have at least one Course Offering in the selected term."""
	term = (filters or {}).get("term")
	conditions = ""
	params = {"txt": f"%{txt}%", "start": start, "page_len": page_len}
	if term:
		conditions = "AND p.name IN (SELECT co.program FROM `tabCourse Offering` co WHERE co.term_name = %(term)s)"
		params["term"] = term

	return frappe.db.sql(
		f"""
		SELECT p.name, p.program_name
		FROM `tabProgramme` p
		WHERE (p.name LIKE %(txt)s OR p.program_name LIKE %(txt)s)
		{conditions}
		ORDER BY p.name
		LIMIT %(start)s, %(page_len)s
		""",
		params,
	)


@frappe.whitelist()
def get_schema_assessments(programme, term, exam_plan=None):
	"""Build assessment rows for every active Course Offering of the programme/term,
	from the Evaluation Schema mapped to it (assessment configs + re-exam configs)."""
	offerings = frappe.get_all(
		"Course Offering",
		filters={"program": programme, "term_name": term, "status": "Active"},
		fields=["name", "course_title", "course_name"],
		order_by="course_name asc",
	)

	rows = []
	missing_schema = []
	for co in offerings:
		schema = _get_mapped_schema(co.name, exam_plan)
		if not schema:
			missing_schema.append(co.course_name or co.name)
			continue

		configs = frappe.get_all(
			"Schema Assessment Config",
			filters={"parent": schema, "parenttype": "Evaluation Schema"},
			fields=["label", "component", "assessment_type"],
			order_by="idx asc",
		)
		reexams = frappe.get_all(
			"Schema Reexam Config",
			filters={"parent": schema, "parenttype": "Evaluation Schema"},
			fields=["label", "component", "assessment_type"],
			order_by="idx asc",
		)

		for cfg in configs:
			rows.append(_row(co, cfg, cfg.label or cfg.assessment_type or cfg.component))
		for cfg in reexams:
			rows.append(_row(co, cfg, cfg.label or "Re-Exam"))

	return {"rows": rows, "missing_schema": missing_schema}


def _get_mapped_schema(course_offering, exam_plan=None):
	if exam_plan:
		schema = frappe.db.get_value(
			"Course Schema Assignment",
			{"course_offering": course_offering, "exam_plan": exam_plan},
			"evaluation_schema",
		)
		if schema:
			return schema
	return frappe.db.get_value(
		"Course Schema Assignment",
		{"course_offering": course_offering, "evaluation_schema": ["is", "set"]},
		"evaluation_schema",
		order_by="modified desc",
	)


def _row(co, cfg, label):
	return {
		"course_offering": co.name,
		"course": co.course_title,
		"course_name": co.course_name,
		"assessment_label": label,
		"component": cfg.component,
		"assessment_type": cfg.assessment_type,
	}
