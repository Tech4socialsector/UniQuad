# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Which exam plans (and which of their courses) a student may see.

The student's courses come from the same source as the student portal Courses
page — Student Enrollment → Student Enrollment Course. A student with no
enrollment record has no courses.

An exam plan is shown for a course only when the student is enrolled in that
course *in the plan's term* (Exam Plan.term == Student Enrollment Course.academic_term), so
an old marks row or a plan of another term never brings a course in. Shared by
the student portal and the parent portal (a parent sees their ward's view).
"""

import frappe


def get_student_programme(student):
	"""Programme of a student: the latest Enrolled Student Enrollment's
	programme, else Student Master.programme_of_study ("" when neither)."""
	if not student:
		return ""
	return (
		frappe.db.get_value(
			"Student Enrollment",
			{"student": student, "status": "Enrolled", "docstatus": ["<", 2]},
			"program",
			order_by="creation desc",
		)
		or frappe.db.get_value("Student Master", student, "programme_of_study")
		or ""
	)


def get_enrolled_courses(student):
	"""[{class_name, course, term}] of the student's enrolled courses in any term
	(Upcoming, Ongoing, Completed, Carry Forward). The exam plan's term decides
	which of them an exam schedule shows, so a schedule is visible before the
	term starts and stays visible after it ends."""
	has_enrollment = frappe.db.exists("Student Enrollment", {"student": student, "docstatus": ["<", 2]})
	if has_enrollment:
		return frappe.db.sql(
			"""
			SELECT DISTINCT sec.class_name,
			       COALESCE(NULLIF(sec.course, ''), cl.course) AS course,
			       COALESCE(NULLIF(sec.academic_term, ''), cl.academic_term) AS term
			FROM `tabStudent Enrollment Course` sec
			JOIN `tabStudent Enrollment` se
			  ON se.name = sec.parent AND sec.parenttype = 'Student Enrollment'
			LEFT JOIN `tabClasses` cl ON cl.name = sec.class_name
			WHERE se.student = %(student)s
			  AND se.docstatus < 2
			  AND se.status != 'Dropped'
			  AND IFNULL(sec.status, '') NOT IN ('Withdrawn', 'Dropped')
			""",
			{"student": student},
			as_dict=True,
		)

	# No enrollment record: no programme + year of study to derive courses from
	return []


def get_visible_exam_plans(student):
	"""{exam_plan: set(course)} — the exam plans the student may see, each
	limited to the courses they are enrolled in for that plan's term.

	A plan is a candidate when it is Active or the student already has marks
	in it; a course belongs to a plan through its Exam Course Schedule, its
	Course Schema Assignment, or the student's own marks row."""
	enrolled = get_enrolled_courses(student)
	if not enrolled:
		return {}

	by_term, all_courses = {}, set()
	for e in enrolled:
		if not e.course:
			continue
		all_courses.add(e.course)
		by_term.setdefault(e.term or "", set()).add(e.course)
	termless = by_term.get("", set())   # course row with no term: any plan

	marks = frappe.get_all(
		"Student Course Marks",
		filters={"student": student},
		fields=["exam_plan", "course"],
		ignore_permissions=True,
	)
	plan_names = set(frappe.get_all("Exam Plan", filters={"status": "Active"}, pluck="name", ignore_permissions=True))
	plan_names |= {m.exam_plan for m in marks if m.exam_plan}
	if not plan_names:
		return {}

	plans = frappe.get_all(
		"Exam Plan",
		filters={"name": ["in", list(plan_names)]},
		fields=["name", "term"],
		ignore_permissions=True,
	)

	# Courses each plan covers (schedule rows, schema assignments, own marks)
	plan_courses = {p.name: set() for p in plans}
	params = {"plans": tuple(plan_courses), "courses": tuple(all_courses)}
	for r in frappe.db.sql(
		"""
		SELECT parent AS plan, course FROM `tabExam Course Schedule`
		WHERE parenttype = 'Exam Plan' AND parent IN %(plans)s AND course IN %(courses)s
		UNION
		SELECT exam_plan AS plan, course FROM `tabCourse Schema Assignment`
		WHERE exam_plan IN %(plans)s AND course IN %(courses)s
		""",
		params,
		as_dict=True,
	):
		plan_courses[r.plan].add(r.course)
	for m in marks:
		if m.exam_plan in plan_courses:
			plan_courses[m.exam_plan].add(m.course)

	visible = {}
	for p in plans:
		allowed = (by_term.get(p.term, set()) | termless) if p.term else all_courses
		# A marks row in the plan (e.g. an arrear attempt of an earlier term's course) also counts
		allowed = allowed | {m.course for m in marks if m.exam_plan == p.name}
		courses = plan_courses[p.name] & allowed
		if courses:
			visible[p.name] = courses
	return visible
