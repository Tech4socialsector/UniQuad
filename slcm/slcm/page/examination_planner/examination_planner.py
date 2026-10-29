# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Exam Plan page: runs one exam plan end to end in five steps.

1. Plan & courses   Exam Plan + Course Schema Assignment (courses from the
                     Classes of the plan's Academic Term)
2. Exam timetable    Exam Plan › Course Schedules (Venue Master rooms, checked by
                     slcm.slcm.utils.exam_timetable) + Exam Assessment Schedules
3. Students          Student Course Marks from Classes, attendance eligibility,
                     Exam Barcodes
4. Marks             Access Result Settings for every course, entry progress
5. Results           Submit, Lock, Term Result, Publish

It only orchestrates: every step calls the existing functions of Exam Plan,
Course Results, Barcode Sheet, Term Result and Publish Result.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

from slcm.slcm.doctype.exam_plan import exam_plan_api as plan_api
from slcm.slcm.page.examination_result import examination_result as results
from slcm.slcm.page.examination_result.examination_result import _check_access


def _load(value, default):
	if value in (None, ""):
		return default
	return json.loads(value) if isinstance(value, str) else value


def _mapped(exam_plan):
	return {
		r.course: r
		for r in frappe.get_all(
			"Course Schema Assignment",
			filters={"exam_plan": exam_plan},
			fields=["name", "course", "evaluation_schema", "grade_schema"],
		)
	}


# ── Plans ──────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_plans():
	_check_access()
	plans = frappe.get_all("Exam Plan", fields=["name", "exam_name", "term", "status"], order_by="creation desc")
	for p in plans:
		p.courses = frappe.db.count("Course Schema Assignment", {"exam_plan": p.name})
		p.students = frappe.db.count("Student Course Marks", {"exam_plan": p.name})
		p.published = frappe.db.count("Student Result Publish", {"exam_plan": p.name, "is_published": 1})
	return {
		"plans": plans,
		"terms": frappe.get_all(
			"Academic Term", fields=["name", "term_start_date", "term_end_date"], order_by="term_start_date desc"
		),
	}


@frappe.whitelist()
def create_plan(term, exam_name=None):
	_check_access()
	if not term:
		frappe.throw(_("Pick the Academic Term."))
	return plan_api.create_exam_plan(exam_name or f"{term} Examinations", term)


@frappe.whitelist()
def get_overview(exam_plan):
	"""Plan header and the state of each step (the page unlocks steps in order)."""
	_check_access()
	plan = frappe.get_doc("Exam Plan", exam_plan)
	term = frappe.db.get_value(
		"Academic Term", plan.term, ["term_start_date", "term_end_date"], as_dict=True
	) if plan.term else None
	taught = {c["course"] for c in plan_api.get_courses_for_plan(exam_plan)}
	mapped = _mapped(exam_plan)
	complete_map = {c for c, r in mapped.items() if r.evaluation_schema and r.grade_schema}
	scheduled = [r for r in plan.course_schedules if r.exam_date and r.start_time and r.end_time and r.venue]
	scm = frappe.get_all(
		"Student Course Marks", filters={"exam_plan": exam_plan},
		fields=["course", "status", "total_marks", "grade", "attendance_status"],
	)
	results_rows = frappe.get_all(
		"Student Result Publish", filters={"exam_plan": exam_plan}, fields=["is_published"]
	)
	courses_with_students = {r.course for r in scm}
	graded = [r for r in scm if r.grade or (r.attendance_status or "") in ("Detained", "Absent")]
	steps = {
		"plan": bool(taught) and taught <= complete_map,
		"timetable": bool(mapped) and len(scheduled) >= len(mapped),
		"students": bool(mapped) and set(mapped) <= courses_with_students,
		"marks": bool(scm) and len(graded) == len(scm),
		"results": bool(results_rows) and all(r.is_published for r in results_rows),
	}
	return {
		"plan": {"name": plan.name, "exam_name": plan.exam_name, "term": plan.term, "status": plan.status},
		"term": term,
		"steps": steps,
		"counts": {
			"courses_taught": len(taught), "courses_mapped": len(complete_map),
			"rows_scheduled": len(scheduled), "rows": len(plan.course_schedules),
			"students": len(scm), "graded": len(graded),
			"locked": sum(1 for r in scm if r.status == "Locked"),
			"results": len(results_rows), "published": sum(1 for r in results_rows if r.is_published),
		},
		"settings": {
			"allow_multiple_plans_per_term": cint(frappe.db.get_single_value("Examination Settings", "allow_multiple_plans_per_term")),
			"require_change_reason": cint(frappe.db.get_single_value("Examination Settings", "require_change_reason")),
		},
	}


# ── 1. Plan & courses ──────────────────────────────────────────────────────────

@frappe.whitelist()
def get_mapping(exam_plan):
	"""Courses of the term with their schemas. Unmapped courses get a suggestion:
	the course's schemas in its latest other plan, else the Examination
	Settings defaults."""
	_check_access()
	settings = frappe.get_cached_doc("Examination Settings")
	rows = plan_api.get_courses_for_plan(exam_plan)
	for r in rows:
		if r.get("assignment_name") and r.get("evaluation_schema") and r.get("grade_schema"):
			r["source"] = "saved"
			continue
		last = frappe.db.sql(
			"""
			SELECT csa.evaluation_schema, csa.grade_schema, csa.exam_plan
			FROM `tabCourse Schema Assignment` csa
			WHERE csa.course = %s AND csa.exam_plan != %s
			  AND IFNULL(csa.evaluation_schema, '') != '' AND IFNULL(csa.grade_schema, '') != ''
			ORDER BY csa.creation DESC LIMIT 1
			""",
			(r["course"], exam_plan),
			as_dict=True,
		)
		if last:
			r["suggest_evaluation_schema"] = r.get("evaluation_schema") or last[0].evaluation_schema
			r["suggest_grade_schema"] = r.get("grade_schema") or last[0].grade_schema
			r["source"] = f"last plan ({last[0].exam_plan})"
		elif settings.default_evaluation_schema or settings.default_grade_schema:
			r["suggest_evaluation_schema"] = r.get("evaluation_schema") or settings.default_evaluation_schema
			r["suggest_grade_schema"] = r.get("grade_schema") or settings.default_grade_schema
			r["source"] = "settings default"
		else:
			r["source"] = ""
	return {
		"courses": rows,
		"evaluation_schemas": frappe.get_all("Evaluation Schema", fields=["name", "total_marks"], order_by="name"),
		"grade_schemas": frappe.get_all("Grading Schema", fields=["name", "schema_name"], order_by="name"),
	}


@frappe.whitelist()
def save_mapping(exam_plan, assignments, reason=None):
	_check_access()
	return plan_api.save_course_schema(exam_plan, assignments, reason)


@frappe.whitelist()
def unmap(exam_plan, courses):
	_check_access()
	return plan_api.unmap_course_schema(exam_plan, courses)


# ── 2. Exam timetable ──────────────────────────────────────────────────────────

@frappe.whitelist()
def get_timetable(exam_plan):
	_check_access()
	from slcm.slcm.utils.exam_timetable import check_exam_schedule, course_students

	plan = frappe.get_doc("Exam Plan", exam_plan)
	mapped = _mapped(exam_plan)
	have = {r.course for r in plan.course_schedules}
	missing = [c for c in mapped if c not in have]   # mapped but not yet in the timetable
	names = dict(frappe.get_all("Course", filters={"name": ["in", list(set(mapped) | have) or [""]]}, fields=["name", "course_name"], as_list=True))
	rows = []
	for r in plan.course_schedules:
		rows.append({
			"course": r.course, "course_name": names.get(r.course, ""),
			"exam_date": r.exam_date, "start_time": str(r.start_time or "")[:5], "end_time": str(r.end_time or "")[:5],
			"venue": r.venue or "", "invigilator": r.invigilator or "", "seat_capacity": r.seat_capacity or "",
			"students": len(course_students(r.course, plan.term)) if plan.term else 0,
		})
	for c in missing:
		rows.append({"course": c, "course_name": names.get(c, ""), "exam_date": "", "start_time": "", "end_time": "",
		             "venue": "", "invigilator": "", "seat_capacity": "", "students": len(course_students(c, plan.term)) if plan.term else 0})
	assessment = frappe.get_all(
		"Exam Assessment Schedule", filters={"exam_plan": exam_plan},
		fields=["name", "programme", "status"], order_by="programme",
	)
	for a in assessment:
		a.rows = frappe.db.count("Exam Assessment Schedule Item", {"parent": a.name})
	programmes = frappe.db.sql_list(
		"SELECT DISTINCT programme FROM `tabClasses` WHERE academic_term = %s AND IFNULL(programme, '') != '' ORDER BY programme",
		plan.term,
	) if plan.term else []
	return {
		"rows": rows,
		"check": check_exam_schedule(plan),
		"venues": frappe.get_all("Venue Master", filters={"is_active": 1}, fields=["name", "capacity"], order_by="name"),
		"faculty": [
			{"name": f.name, "label": " ".join(filter(None, [f.first_name, f.last_name])) or f.name}
			for f in frappe.get_all("Faculty", filters={"status": ["!=", "Inactive"]}, fields=["name", "first_name", "last_name"],
			                        order_by="first_name", limit=1000)
		],
		"assessment_schedules": assessment,
		"programmes": programmes,
	}


@frappe.whitelist()
def check_timetable(exam_plan, rows):
	_check_access()
	from slcm.slcm.utils.exam_timetable import preview_exam_schedule

	return preview_exam_schedule(exam_plan, [_row(r) for r in _load(rows, [])])


def _row(r):
	return {k: (r.get(k) or None) for k in ("course", "exam_date", "start_time", "end_time", "venue", "invigilator", "seat_capacity")}


@frappe.whitelist()
def save_timetable(exam_plan, rows):
	"""Replace the plan's course schedule rows; Exam Plan.validate applies every check."""
	_check_access()
	plan = frappe.get_doc("Exam Plan", exam_plan)
	plan.set("course_schedules", [_row(r) for r in _load(rows, []) if r.get("course")])
	plan.save()
	frappe.db.commit()
	return True


@frappe.whitelist()
def create_assessment_schedule(exam_plan, programme):
	"""Exam Assessment Schedule for one programme, rows taken from the mapped
	schemas (get_schema_assessments). Dates are filled on the form."""
	_check_access()
	from slcm.slcm.doctype.exam_assessment_schedule.exam_assessment_schedule import get_schema_assessments

	term = frappe.db.get_value("Exam Plan", exam_plan, "term")
	existing = frappe.db.get_value("Exam Assessment Schedule", {"exam_plan": exam_plan, "programme": programme}, "name")
	if existing:
		return existing
	doc = frappe.new_doc("Exam Assessment Schedule")
	doc.update({
		"academic_year": frappe.db.get_value("Academic Term", term, "academic_year"),
		"term": term, "programme": programme, "exam_plan": exam_plan, "status": "Active",
	})
	for r in get_schema_assessments(programme, term, exam_plan)["rows"]:
		doc.append("assessments", r)
	doc.insert()
	frappe.db.commit()
	return doc.name


# ── 3. Students ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_students(exam_plan):
	_check_access()
	from slcm.slcm.utils.exam_timetable import course_students

	term = frappe.db.get_value("Exam Plan", exam_plan, "term")
	out = []
	for course in _mapped(exam_plan):
		marks = frappe.get_all("Student Course Marks", filters={"exam_plan": exam_plan, "course": course},
		                       fields=["attendance_status", "manually_added"])
		out.append({
			"course": course,
			"in_classes": len(course_students(course, term)) if term else 0,
			"synced": len(marks),
			"detained": sum(1 for m in marks if m.attendance_status == "Detained"),
			"manual": sum(1 for m in marks if m.manually_added),
			"barcodes": frappe.db.count("Exam Barcode", {"exam_plan": exam_plan, "course": course}),
		})
	return out


@frappe.whitelist()
def sync_all_students(exam_plan):
	"""Fetch from Enrollment for every mapped course, into this plan."""
	_check_access()
	added = skipped = 0
	errors = []
	for course in _mapped(exam_plan):
		try:
			r = results.sync_students_from_enrollment(course, exam_plan)
			added += r["added"]
			skipped += r["skipped"]
		except frappe.ValidationError as e:
			frappe.clear_messages()
			errors.append(f"{course}: {e}")
	return {"added": added, "skipped": skipped, "errors": errors}


@frappe.whitelist()
def update_eligibility(exam_plan):
	_check_access()
	return results.update_attendance_eligibility(exam_plan)


@frappe.whitelist()
def generate_barcodes(exam_plan, copies=1):
	_check_access()
	from slcm.slcm.page.exam_barcode_sheet.exam_barcode_sheet import generate_barcodes as _generate

	return _generate(exam_plan, json.dumps(list(_mapped(exam_plan))), cint(copies) or 1)


# ── 4. Marks ───────────────────────────────────────────────────────────────────

def _faculty_label(faculty):
	from slcm.slcm.utils.exam_timetable import _faculty_label as label

	return label(faculty) if frappe.db.exists("Faculty", faculty) else (faculty or "")


@frappe.whitelist()
def get_marks_progress(exam_plan):
	_check_access()
	out = []
	for course, csa in _mapped(exam_plan).items():
		keys = frappe.get_all("Schema Assessment Config", filters={"parent": csa.evaluation_schema, "parenttype": "Evaluation Schema"},
		                      fields=["component", "assessment_type"]) if csa.evaluation_schema else []
		marks = frappe.get_all("Student Course Marks", filters={"exam_plan": exam_plan, "course": course},
		                       fields=["name", "status", "grade", "attendance_status"])
		entered = 0
		if marks and keys:
			counts = dict(frappe.db.sql(
				"""SELECT parent, COUNT(DISTINCT CONCAT(component, '|', assessment_type))
				   FROM `tabStudent Marks Entry` WHERE parent IN %s GROUP BY parent""",
				(tuple(m.name for m in marks),),
			))
			entered = sum(1 for m in marks if counts.get(m.name, 0) >= len(keys) or m.attendance_status in ("Detained", "Absent"))
		access = frappe.db.get_value("Access Result Settings", {"exam_plan": exam_plan, "course": course},
		                             ["name", "status", "edit_access", "edit_deadline"], as_dict=True)
		out.append({
			"course": course, "students": len(marks), "entered": entered,
			"graded": sum(1 for m in marks if m.grade),
			"submitted": sum(1 for m in marks if m.status == "Submitted"),
			"locked": sum(1 for m in marks if m.status == "Locked"),
			"access": access,
			"evaluators": [
				_faculty_label(e) for e in frappe.get_all("Result Course Evaluator", filters={"parent": access.name}, pluck="evaluator_name")
			] if access else [],
		})
	return out


@frappe.whitelist()
def apply_access(exam_plan, settings):
	"""One access setting for every course of the plan; each course's Class
	faculty become its evaluators (Course Results' own functions)."""
	_check_access()
	courses = list(_mapped(exam_plan))
	if not courses:
		frappe.throw(_("Map the courses first."))
	results.save_access_settings(exam_plan, json.dumps(courses), json.dumps(_load(settings, {})))
	term = frappe.db.get_value("Exam Plan", exam_plan, "term")
	for course in courses:
		access = results._get_or_create_access(exam_plan, course)
		if access.evaluators:
			continue
		for faculty in frappe.get_all("Classes", filters={"course": course, "academic_term": term}, pluck="faculty", distinct=True):
			if faculty:
				access.append("evaluators", {"evaluator_type": "Class Faculty", "evaluator_doctype": "Faculty",
				                             "evaluator_name": faculty,
				                             "evaluator_email": frappe.db.get_value("Faculty", faculty, "email") or ""})
		access.save(ignore_permissions=True)
	frappe.db.commit()
	return len(courses)


# ── 5. Results ─────────────────────────────────────────────────────────────────

def _plan_students(exam_plan):
	return frappe.get_all("Student Course Marks", filters={"exam_plan": exam_plan}, pluck="student", distinct=True)


@frappe.whitelist()
def set_status_all(exam_plan, status):
	"""Submitted or Locked for every course (Locking also locks Access Result Settings)."""
	_check_access()
	if status not in ("Submitted", "Locked"):
		frappe.throw(_("Status must be Submitted or Locked."))
	count = 0
	for course in _mapped(exam_plan):
		if status == "Submitted":
			# Locked rows stay Locked
			students = frappe.get_all("Student Course Marks", filters={"exam_plan": exam_plan, "course": course, "status": "Draft"}, pluck="student")
			if students:
				count += results.set_marks_status(course, exam_plan, status, json.dumps(students), 0).get("updated", 0)
		else:
			count += results.set_marks_status(course, exam_plan, status, "[]", 1).get("updated", 0)
			access = results._get_or_create_access(exam_plan, course)
			if access.status != "LOCKED":
				access.status = "LOCKED"
				access.save(ignore_permissions=True)
	frappe.db.commit()
	return count


@frappe.whitelist()
def generate_results(exam_plan):
	"""Term GPA, Term %, Cumulative GPA / % for every student of the plan."""
	_check_access()
	from slcm.slcm.page.term_result.term_result import generate_term_results

	for action in ("term_gpa", "term_percentage", "cumulative_gpa"):
		generate_term_results(exam_plan, "[]", action, select_all=1)
	return frappe.db.count("Student Result Publish", {"exam_plan": exam_plan})


@frappe.whitelist()
def publish_all(exam_plan, publish=1):
	_check_access()
	from slcm.slcm.page.publish_result.publish_result import bulk_publish

	students = frappe.get_all("Student Result Publish", filters={"exam_plan": exam_plan}, pluck="student")
	return bulk_publish(exam_plan, json.dumps(students), cint(publish))


@frappe.whitelist()
def get_results(exam_plan):
	_check_access()
	scm = frappe.get_all("Student Course Marks", filters={"exam_plan": exam_plan}, fields=["status", "grade", "updated_grade"])
	srp = frappe.get_all("Student Result Publish", filters={"exam_plan": exam_plan},
	                     fields=["term_gpa", "cumulative_gpa", "is_published"])
	failed_grades = set(frappe.get_all("Grading Schema Component", filters={"failed": 1}, pluck="grade", distinct=True))
	return {
		"marks": {s: sum(1 for r in scm if r.status == s) for s in ("Draft", "Submitted", "Locked")},
		"fails": sum(1 for r in scm if (r.updated_grade or r.grade) in failed_grades),
		"results": len(srp),
		"published": sum(1 for r in srp if r.is_published),
		"avg_gpa": round(sum(flt(r.term_gpa) for r in srp) / len(srp), 2) if srp else 0,
		"publish_setting": frappe.db.exists("Publish Result Setting", exam_plan),
		"re_exam_settings": frappe.db.count("Re Exam Course Setting", {"exam_plan": exam_plan}),
		"improvement_settings": frappe.db.count("Improvement Exam Course Setting", {"exam_plan": exam_plan}),
	}
