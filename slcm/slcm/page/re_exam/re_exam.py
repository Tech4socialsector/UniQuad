# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _

RE_EXAM_ROLES = {"System Manager", "Academics User"}


def _check_access():
	"""Admin-only actions (settings, eligibility overrides, marking paid) —
	this page is restricted at the desk UI level, but the whitelisted RPCs
	are directly callable via /api/method/, so they must enforce the same
	role themselves."""
	if not RE_EXAM_ROLES & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _get_course_offering(exam_plan, course):
	"""Resolve the Course Offering for a course under this exam plan via its
	Course Schema Assignment. Throws if none exists yet.

	If the assignment points at a Course Offering that has since been deleted
	(offerings get regenerated when batches/terms are re-created), fall back to
	the course's live offering for the exam plan's term and repair the
	assignment, instead of failing every save with a LinkValidationError."""
	csa = frappe.db.get_value(
		"Course Schema Assignment",
		{"exam_plan": exam_plan, "course": course},
		["name", "course_offering"],
		as_dict=True,
	)
	course_offering = csa and csa.course_offering
	if course_offering and frappe.db.exists("Course Offering", course_offering):
		return course_offering

	term = frappe.db.get_value("Exam Plan", exam_plan, "term")
	candidates = frappe.get_all(
		"Course Offering",
		filters={"course_title": course, **({"term_name": term} if term else {})},
		pluck="name",
		order_by="modified desc",
	)
	if len(candidates) == 1:
		if csa:
			frappe.db.set_value("Course Schema Assignment", csa.name, "course_offering", candidates[0])
		return candidates[0]

	if course_offering:
		frappe.throw(
			_("Course Offering '{0}' linked to course '{1}' in exam plan '{2}' no longer exists. "
			  "Update its Course Schema Assignment to the current Course Offering.").format(
				course_offering, course, exam_plan)
		)
	frappe.throw(
		_("No Course Offering found for course '{0}' in exam plan '{1}'. "
		  "Map a Course Schema Assignment for it first.").format(course, exam_plan)
	)


@frappe.whitelist()
def get_exam_plans(search=None):
	filters = {}
	if search:
		filters["exam_name"] = ["like", f"%{search}%"]
	return frappe.get_all(
		"Exam Plan",
		filters=filters,
		fields=["name", "exam_name", "term", "status"],
		order_by="creation desc",
	)


@frappe.whitelist()
def get_programmes_for_exam_plan(exam_plan):
	if not exam_plan:
		return []
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT sm.programme_of_study AS programme
		FROM `tabStudent Course Marks` scm
		INNER JOIN `tabStudent Master` sm ON sm.name = scm.student
		WHERE scm.exam_plan = %(exam_plan)s
		  AND sm.programme_of_study IS NOT NULL AND sm.programme_of_study != ''
		ORDER BY sm.programme_of_study
		""",
		{"exam_plan": exam_plan},
		as_dict=True,
	)
	return rows


@frappe.whitelist()
def get_courses_for_exam_plan(exam_plan, programme=""):
	if not exam_plan:
		return []
	extra_join = ""
	extra_cond = ""
	params = {"exam_plan": exam_plan}
	if programme:
		extra_join = "INNER JOIN `tabStudent Master` sm ON sm.name = scm.student"
		extra_cond = " AND sm.programme_of_study = %(programme)s"
		params["programme"] = programme
	rows = frappe.db.sql(
		f"""
		SELECT DISTINCT scm.course, c.course_name
		FROM `tabStudent Course Marks` scm
		LEFT JOIN `tabCourse` c ON c.name = scm.course
		{extra_join}
		WHERE scm.exam_plan = %(exam_plan)s{extra_cond}
		ORDER BY c.course_name, scm.course
		""",
		params,
		as_dict=True,
	)
	return rows


@frappe.whitelist()
def get_re_exam_setting(exam_plan, course):
	if not exam_plan or not course:
		return {}
	row = frappe.db.get_value(
		"Re Exam Course Setting",
		{"exam_plan": exam_plan, "course": course},
		["name", "re_exam_fee", "deadline_from", "deadline_to"],
		as_dict=True,
	)
	return row or {}


@frappe.whitelist()
def save_re_exam_setting(exam_plan, course, re_exam_fee=None, deadline_from=None, deadline_to=None):
	_check_access()
	if not exam_plan or not course:
		frappe.throw("Exam Plan and Course are required.")

	existing_name = frappe.db.get_value(
		"Re Exam Course Setting",
		{"exam_plan": exam_plan, "course": course},
		"name",
	)

	if existing_name:
		doc = frappe.get_doc("Re Exam Course Setting", existing_name)
	else:
		doc = frappe.new_doc("Re Exam Course Setting")
		doc.exam_plan = exam_plan
		doc.course    = course
	# Re-resolve every save so a setting saved against a since-deleted offering self-heals
	doc.course_offering = _get_course_offering(exam_plan, course)

	doc.re_exam_fee   = re_exam_fee   or None
	doc.deadline_from = deadline_from or None
	doc.deadline_to   = deadline_to   or None
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"name": doc.name}


@frappe.whitelist()
def get_failed_students(exam_plan, course, search="", page=1, page_length=20):
	if not exam_plan or not course:
		return {"students": [], "total": 0}

	page        = int(page)
	page_length = int(page_length)
	offset      = (page - 1) * page_length
	params      = {"exam_plan": exam_plan, "course": course}

	# Resolve grade schema via Course Schema Assignment
	assignment = frappe.db.sql(
		"""
		SELECT csa.grade_schema
		FROM `tabCourse Schema Assignment` csa
		WHERE csa.course = %(course)s AND csa.exam_plan = %(exam_plan)s
		LIMIT 1
		""",
		{"course": course, "exam_plan": exam_plan},
		as_dict=True,
	)
	grade_schema = assignment[0]["grade_schema"] if assignment else None

	if not grade_schema:
		# Fallback: pick grade_schema from any assignment for this course
		row = frappe.db.get_value(
			"Course Schema Assignment",
			{"course": course},
			"grade_schema",
		)
		grade_schema = row or None

	failed_grades = []
	all_grades_fallback = False
	if grade_schema:
		rows = frappe.db.sql(
			"SELECT grade FROM `tabGrading Schema Component` WHERE parent = %s AND failed = 1",
			grade_schema,
			as_list=True,
		)
		failed_grades = [r[0] for r in rows if r[0]]

	if not failed_grades:
		# No grades are explicitly marked as failed in the schema.
		# Fall back: show all students who have a grade recorded (non-null, non-empty).
		all_grades_fallback = True

	# Build grade filter condition
	if all_grades_fallback:
		# No failed=1 grades defined — show all students with any grade recorded
		grade_cond = "AND scm.grade IS NOT NULL AND scm.grade != ''"
	else:
		placeholders = ",".join([f"%(fg_{i})s" for i in range(len(failed_grades))])
		for i, v in enumerate(failed_grades):
			params[f"fg_{i}"] = v
		grade_cond = f"AND scm.grade IN ({placeholders})"

	extra_cond = ""
	if search:
		extra_cond += (
			" AND (sm.registration_id LIKE %(search)s"
			" OR sm.first_name LIKE %(search)s"
			" OR sm.last_name LIKE %(search)s)"
		)
		params["search"] = f"%{search}%"

	params["lim"] = page_length
	params["off"] = offset

	students = frappe.db.sql(
		f"""
		SELECT
			sm.name                                                              AS student,
			sm.registration_id,
			TRIM(CONCAT_WS(' ', sm.first_name,
				COALESCE(NULLIF(sm.middle_name,''), NULL),
				sm.last_name))                                                   AS student_name,
			sm.programme_of_study                                                AS programme,
			sm.batch_year,
			sm.passport_size_photo                                               AS image,
			sm.email,
			scm.grade,
			scm.total_marks,
			scm.status
		FROM `tabStudent Course Marks` scm
		INNER JOIN `tabStudent Master` sm ON sm.name = scm.student
		WHERE scm.exam_plan = %(exam_plan)s
		  AND scm.course = %(course)s
		  {grade_cond}
		{extra_cond}
		ORDER BY sm.registration_id ASC
		LIMIT %(lim)s OFFSET %(off)s
		""",
		params,
		as_dict=True,
	)

	count_params = {k: v for k, v in params.items() if k not in ("lim", "off")}
	count_row = frappe.db.sql(
		f"""
		SELECT COUNT(*) AS cnt
		FROM `tabStudent Course Marks` scm
		INNER JOIN `tabStudent Master` sm ON sm.name = scm.student
		WHERE scm.exam_plan = %(exam_plan)s
		  AND scm.course = %(course)s
		  {grade_cond}
		{extra_cond}
		""",
		count_params,
		as_dict=True,
	)
	total = count_row[0]["cnt"] if count_row else 0

	# Merge override (is_allowed, override_reason) into each student row; default = True
	override_rows = frappe.db.sql(
		"SELECT student, is_allowed, override_reason FROM `tabRe Exam Student Override` WHERE exam_plan = %(exam_plan)s AND course = %(course)s",
		{"exam_plan": exam_plan, "course": course},
		as_dict=True,
	)
	overrides = {
		r["student"]: {"is_allowed": bool(r["is_allowed"]), "reason": r.get("override_reason") or ""}
		for r in override_rows
	}
	for s in students:
		ov = overrides.get(s["student"])
		s["is_allowed"]      = ov["is_allowed"] if ov is not None else True
		s["override_reason"] = ov["reason"]     if ov is not None else ""

	return {
		"students":            students,
		"total":               total,
		"all_grades_fallback": all_grades_fallback,
	}


@frappe.whitelist()
def get_re_exam_stats(exam_plan, course):
	if not exam_plan or not course:
		return {}

	total_row = frappe.db.sql(
		"""
		SELECT COUNT(*) AS cnt
		FROM `tabStudent Course Marks` scm
		WHERE scm.exam_plan = %(exam_plan)s AND scm.course = %(course)s
		""",
		{"exam_plan": exam_plan, "course": course},
		as_dict=True,
	)
	total = total_row[0]["cnt"] if total_row else 0

	assignment = frappe.db.sql(
		"""
		SELECT csa.grade_schema
		FROM `tabCourse Schema Assignment` csa
		WHERE csa.course = %(course)s AND csa.exam_plan = %(exam_plan)s
		LIMIT 1
		""",
		{"course": course, "exam_plan": exam_plan},
		as_dict=True,
	)
	grade_schema = assignment[0]["grade_schema"] if assignment else None

	failed_grades = []
	if grade_schema:
		rows = frappe.db.sql(
			"SELECT grade FROM `tabGrading Schema Component` WHERE parent = %s AND failed = 1",
			grade_schema,
			as_list=True,
		)
		failed_grades = [r[0] for r in rows if r[0]]

	failed_count = 0
	if failed_grades:
		placeholders = ",".join([f"%(fg_{i})s" for i in range(len(failed_grades))])
		p = {"exam_plan": exam_plan, "course": course}
		for i, v in enumerate(failed_grades):
			p[f"fg_{i}"] = v
		count_row = frappe.db.sql(
			f"""
			SELECT COUNT(*) AS cnt
			FROM `tabStudent Course Marks` scm
			WHERE scm.exam_plan = %(exam_plan)s
			  AND scm.course = %(course)s
			  AND scm.grade IN ({placeholders})
			""",
			p,
			as_dict=True,
		)
		failed_count = count_row[0]["cnt"] if count_row else 0
	else:
		# Fallback: count students with any grade recorded
		count_row = frappe.db.sql(
			"""
			SELECT COUNT(*) AS cnt
			FROM `tabStudent Course Marks` scm
			WHERE scm.exam_plan = %(exam_plan)s
			  AND scm.course = %(course)s
			  AND scm.grade IS NOT NULL AND scm.grade != ''
			""",
			{"exam_plan": exam_plan, "course": course},
			as_dict=True,
		)
		failed_count = count_row[0]["cnt"] if count_row else 0

	registered_row = frappe.db.sql(
		"""
		SELECT COUNT(*) AS cnt
		FROM `tabRe Exam Registration`
		WHERE exam_plan = %(exam_plan)s AND course = %(course)s
		  AND status != 'Cancelled'
		""",
		{"exam_plan": exam_plan, "course": course},
		as_dict=True,
	)
	registered_count = registered_row[0]["cnt"] if registered_row else 0

	return {
		"total":      total,
		"failed":     failed_count,
		"passed":     total - failed_count,
		"registered": registered_count,
	}


@frappe.whitelist()
def get_student_overrides(exam_plan, course):
	"""Return a dict of {student: is_allowed} for the given exam_plan+course."""
	if not exam_plan or not course:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT student, is_allowed
		FROM `tabRe Exam Student Override`
		WHERE exam_plan = %(exam_plan)s AND course = %(course)s
		""",
		{"exam_plan": exam_plan, "course": course},
		as_dict=True,
	)
	return {r["student"]: bool(r["is_allowed"]) for r in rows}


@frappe.whitelist()
def set_student_re_exam_allowed(exam_plan, course, student, is_allowed, override_reason=""):
	"""Upsert an override record for a single student."""
	_check_access()
	if not exam_plan or not course or not student:
		frappe.throw("exam_plan, course and student are required.")

	is_allowed = int(is_allowed)

	existing = frappe.db.get_value(
		"Re Exam Student Override",
		{"exam_plan": exam_plan, "course": course, "student": student},
		"name",
	)
	if existing:
		frappe.db.set_value("Re Exam Student Override", existing, {
			"is_allowed":      is_allowed,
			"override_reason": override_reason or "",
		})
	else:
		doc = frappe.new_doc("Re Exam Student Override")
		doc.exam_plan        = exam_plan
		doc.course           = course
		doc.course_offering  = _get_course_offering(exam_plan, course)
		doc.student          = student
		doc.is_allowed       = is_allowed
		doc.override_reason  = override_reason or ""
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True}


@frappe.whitelist()
def get_re_exam_registrations(exam_plan, course=""):
	"""Return active registrations for an exam_plan.
	Pass course to filter to one course; omit (or empty) to get all courses.
	"""
	if not exam_plan:
		return []
	params = {"exam_plan": exam_plan}
	course_cond = ""
	if course:
		course_cond = "AND r.course = %(course)s"
		params["course"] = course
	rows = frappe.db.sql(
		f"""
		SELECT
			r.name,
			r.student,
			r.course,
			COALESCE(c.course_name, r.course)  AS course_name,
			TRIM(CONCAT_WS(' ', sm.first_name,
				COALESCE(NULLIF(sm.middle_name,''), NULL),
				sm.last_name))                 AS student_name,
			sm.registration_id,
			sm.programme_of_study                                                AS programme,
			r.re_exam_fee,
			r.status,
			r.payment_status,
			r.payment_reference,
			r.remarks,
			r.creation
		FROM `tabRe Exam Registration` r
		INNER JOIN `tabStudent Master` sm ON sm.name = r.student
		LEFT  JOIN `tabCourse`         c  ON c.name  = r.course
		WHERE r.exam_plan = %(exam_plan)s
		  {course_cond}
		  AND r.status != 'Cancelled'
		ORDER BY r.creation DESC
		""",
		params,
		as_dict=True,
	)
	return rows


@frappe.whitelist()
def mark_re_exam_paid(registration_name, payment_reference=""):
	"""Mark a Re Exam Registration as Paid."""
	_check_access()
	if not registration_name:
		frappe.throw("Registration name is required.")
	doc = frappe.get_doc("Re Exam Registration", registration_name)
	doc.payment_status = "Paid"
	if payment_reference:
		doc.payment_reference = payment_reference
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True}


@frappe.whitelist()
def bulk_save_re_exam_setting(exam_plan, re_exam_fee=None, deadline_from=None, deadline_to=None, courses=None):
	"""Apply the same fee + deadline to selected (or all) courses under an exam plan."""
	_check_access()
	import json as _json
	if not exam_plan:
		frappe.throw("Exam Plan is required.")

	if courses:
		# Caller passed a specific list of course names
		course_list = _json.loads(courses) if isinstance(courses, str) else list(courses)
	else:
		rows = frappe.db.sql(
			"SELECT DISTINCT course FROM `tabStudent Course Marks` WHERE exam_plan = %(exam_plan)s",
			{"exam_plan": exam_plan},
			as_list=True,
		)
		course_list = [r[0] for r in rows]

	updated = 0
	for course in course_list:
		if not course:
			continue
		existing_name = frappe.db.get_value(
			"Re Exam Course Setting",
			{"exam_plan": exam_plan, "course": course},
			"name",
		)
		if existing_name:
			doc = frappe.get_doc("Re Exam Course Setting", existing_name)
		else:
			doc = frappe.new_doc("Re Exam Course Setting")
			doc.exam_plan = exam_plan
			doc.course    = course
		doc.course_offering = _get_course_offering(exam_plan, course)
		doc.re_exam_fee   = re_exam_fee   or None
		doc.deadline_from = deadline_from or None
		doc.deadline_to   = deadline_to   or None
		doc.save(ignore_permissions=True)
		updated += 1
	frappe.db.commit()
	return {"updated": updated}
