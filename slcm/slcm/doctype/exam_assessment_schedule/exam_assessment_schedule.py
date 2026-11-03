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
		# Courses taught (as Classes) under this programme in this term
		taught = set(_term_courses(self.programme, self.term)) if self.programme and self.term else None
		seen = set()
		for row in self.assessments:
			if taught is not None and row.course and row.course not in taught:
				frappe.throw(
					_("Row {0}: Course {1} has no Class under Programme {2} / Term {3}.").format(
						row.idx, frappe.bold(row.course), self.programme, self.term
					)
				)

			key = (row.course, (row.assessment_label or "").strip().lower())
			if key in seen:
				frappe.throw(
					_("Row {0}: Assessment {1} is listed more than once for {2}.").format(
						row.idx, frappe.bold(row.assessment_label), frappe.bold(row.course_name or row.course)
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
	"""Programmes that have at least one Class in the selected term."""
	term = (filters or {}).get("term")
	conditions = ""
	params = {"txt": f"%{txt}%", "start": start, "page_len": page_len}
	if term:
		conditions = "AND p.name IN (SELECT cl.programme FROM `tabClasses` cl WHERE cl.academic_term = %(term)s)"
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


def _term_courses(programme, term):
	"""Distinct courses that have a Class under the programme in the term."""
	return frappe.get_all(
		"Classes",
		filters={"programme": programme, "academic_term": term},
		pluck="course",
		distinct=True,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def course_query(doctype, txt, searchfield, start, page_len, filters):
	"""Active courses that have a Class under the selected programme/term."""
	filters = filters or {}
	conditions = ["c.status = 'Active'", "(c.name LIKE %(txt)s OR c.course_name LIKE %(txt)s)"]
	params = {"txt": f"%{txt}%", "start": start, "page_len": page_len}
	cl_conditions = []
	if filters.get("programme"):
		cl_conditions.append("cl.programme = %(programme)s")
		params["programme"] = filters["programme"]
	if filters.get("term"):
		cl_conditions.append("cl.academic_term = %(term)s")
		params["term"] = filters["term"]
	if cl_conditions:
		conditions.append(
			"c.name IN (SELECT cl.course FROM `tabClasses` cl WHERE " + " AND ".join(cl_conditions) + ")"
		)

	return frappe.db.sql(
		f"""
		SELECT c.name, c.course_name
		FROM `tabCourse` c
		WHERE {" AND ".join(conditions)}
		ORDER BY c.course_name
		LIMIT %(start)s, %(page_len)s
		""",
		params,
	)


@frappe.whitelist()
def get_schema_assessments(programme, term, exam_plan=None):
	"""Build assessment rows for every active course taught (as Classes) under the
	programme/term, from the Evaluation Schema mapped to it (assessment configs +
	re-exam configs)."""
	courses = frappe.get_all(
		"Course",
		filters={"name": ["in", _term_courses(programme, term) or [""]], "status": "Active"},
		fields=["name", "course_name"],
		order_by="course_name asc",
	)

	rows = []
	missing_schema = []
	for co in courses:
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


def _get_mapped_schema(course, exam_plan=None):
	if exam_plan:
		schema = frappe.db.get_value(
			"Course Schema Assignment",
			{"course": course, "exam_plan": exam_plan},
			"evaluation_schema",
		)
		if schema:
			return schema
	return frappe.db.get_value(
		"Course Schema Assignment",
		{"course": course, "evaluation_schema": ["is", "set"]},
		"evaluation_schema",
		order_by="modified desc",
	)


def _row(co, cfg, label):
	return {
		"course": co.name,
		"course_name": co.course_name,
		"assessment_label": label,
		"component": cfg.component,
		"assessment_type": cfg.assessment_type,
	}
