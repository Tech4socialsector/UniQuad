# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Exam Plan page: runs one exam plan end to end in five steps.

1. Plan & courses   Exam Plan + Course Schema Assignment (courses from the
                     Classes of the plan's Academic Term)
2. Exam timetable    Exam Plan › Course Schedules, one row per room as on the
                     classroom allocation sheet (checked by
                     slcm.slcm.utils.exam_timetable) + the Continuing Evaluation
                     Schedule (Exam Assessment Schedules); both download and
                     import as the office's Excel sheets (slcm.slcm.utils.exam_sheets)
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

# ── Lookups used by the Evaluation Schema form ────────────────────────────────

@frappe.whitelist()
def get_components():
	return frappe.get_all(
		"Exam Component",
		filters={"is_active": 1},
		fields=["name", "component_name", "component_type"],
		order_by="component_name asc",
	)


@frappe.whitelist()
def get_assessment_types():
	return frappe.get_all(
		"Exam Assessment Type",
		filters={"is_active": 1},
		fields=["name", "type_name", "assessment_type"],
		order_by="type_name asc",
	)


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
def get_plan_list():
	"""Every exam plan with its step state, for the Examination Management home table."""
	plans = get_plans()["plans"]
	for p in plans:
		p.steps = get_overview(p.name)["steps"]
		p.created = frappe.db.get_value("Exam Plan", p.name, "creation")
	return plans


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
	scheduled = [r for r in plan.course_schedules if r.exam_date and r.start_time and r.end_time and (r.venue or r.hall)]
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
		"timetable": bool(mapped) and set(mapped) <= {r.course for r in scheduled},
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
		"setup": {
			"components": frappe.db.count("Exam Component", {"is_active": 1}),
			"assessment_types": frappe.db.count("Exam Assessment Type", {"is_active": 1}),
		},
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
	from slcm.slcm.utils.exam_timetable import check_exam_schedule

	plan = frappe.get_doc("Exam Plan", exam_plan)
	mapped = _mapped(exam_plan)
	have = {r.course for r in plan.course_schedules}
	missing = [c for c in mapped if c not in have]   # mapped but not yet in the timetable
	names = dict(frappe.get_all("Course", filters={"name": ["in", list(set(mapped) | have) or [""]]}, fields=["name", "course_name"], as_list=True))
	rows = [{
		"course": r.course or "", "course_name": names.get(r.course, ""), "paper": r.paper or "",
		"programme_year": r.programme_year or "", "session": r.session or "",
		"exam_date": r.exam_date, "start_time": str(r.start_time or "")[:5], "end_time": str(r.end_time or "")[:5],
		"venue": r.venue or "", "hall": r.hall or "", "invigilator": r.invigilator or "",
		"invigilator_name": r.invigilator_name or "", "seat_capacity": r.seat_capacity or "",
		"id_from": r.id_from or "", "id_to": r.id_to or "",
	} for r in plan.course_schedules]
	for c in missing:
		rows.append({"course": c, "course_name": names.get(c, ""), "paper": "", "programme_year": "", "session": "",
		             "exam_date": "", "start_time": "", "end_time": "", "venue": "", "hall": "", "invigilator": "",
		             "invigilator_name": "", "seat_capacity": "", "id_from": "", "id_to": ""})
	for r, n in zip(rows, _row_counts(plan.term, rows)):
		r["students"] = n
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
		"published": cint(plan.timetable_published),
		"show_invigilator": cint(plan.timetable_show_invigilator),
		**_rooms_and_faculty(),
		"assessment_schedules": assessment,
		"programmes": programmes,
		"courses": [{"name": c, "course_name": names.get(c, c)} for c in mapped],
	}


def _sheet_row(r, names):
	"""A timetable line for the page (exam or re-exam)."""
	return {
		"course": r.course or "", "course_name": names.get(r.course, ""), "paper": r.paper or "",
		"programme_year": r.programme_year or "", "session": r.session or "",
		"exam_date": r.exam_date or "", "start_time": str(r.start_time or "")[:5], "end_time": str(r.end_time or "")[:5],
		"venue": r.venue or "", "hall": r.hall or "", "invigilator": r.invigilator or "",
		"invigilator_name": r.invigilator_name or "", "seat_capacity": r.seat_capacity or "",
		"id_from": r.id_from or "", "id_to": r.id_to or "",
	}


def _row_counts(term, rows, reexam_plan=None):
	"""Students sitting each timetable row: a course split over rooms counts
	the Student IDs in each row's ID Nos. range. For a re-exam (reexam_plan),
	the students registered for it."""
	from slcm.slcm.utils.exam_timetable import course_student_ids, reexam_student_ids, split_by_id_range

	counts = [0] * len(rows)
	if not term and not reexam_plan:
		return counts
	by_course = {}
	for i, r in enumerate(rows):
		if r.get("course"):
			by_course.setdefault(r["course"], []).append(i)
	for course, idxs in by_course.items():
		ids = reexam_student_ids(reexam_plan, course) if reexam_plan else course_student_ids(course, term)
		for i, got in zip(idxs, split_by_id_range([rows[i] for i in idxs], ids)):
			counts[i] = len(got)
	return counts


def _rooms_and_faculty():
	return {
		"venues": frappe.get_all("Venue Master", filters={"is_active": 1}, fields=["name", "capacity"], order_by="name"),
		"faculty": [
			{"name": f.name, "label": " ".join(filter(None, [f.first_name, f.last_name])) or f.name}
			for f in frappe.get_all("Faculty", filters={"status": ["!=", "Inactive"]}, fields=["name", "first_name", "last_name"],
			                        order_by="first_name", limit=1000)
		],
	}


@frappe.whitelist()
def set_timetable_published(exam_plan, published, reexam=0, show_invigilator=0):
	"""Show (or hide) the exam or re-exam timetable on the student portal, with or
	without the invigilator names."""
	_check_access()
	field, invig = (
		("reexam_timetable_published", "reexam_show_invigilator") if cint(reexam)
		else ("timetable_published", "timetable_show_invigilator")
	)
	frappe.db.set_value("Exam Plan", exam_plan, {
		field: 1 if cint(published) else 0,
		invig: 1 if cint(published) and cint(show_invigilator) else 0,
	})
	frappe.db.commit()
	return cint(published)


# ── 5. Re-exam timetable ───────────────────────────────────────────────────────

@frappe.whitelist()
def get_reexam_timetable(exam_plan):
	"""Re-exam and improvement sittings, laid out like the exam timetable (a line
	per room). Courses with failed students, a re-exam / improvement window,
	registrations or a saved line; the ones without a date need one."""
	_check_access()
	from slcm.slcm.utils.exam_timetable import check_exam_schedule

	plan = frappe.get_doc("Exam Plan", exam_plan)
	failed_grades = set(frappe.get_all("Grading Schema Component", filters={"failed": 1}, pluck="grade", distinct=True))
	failed = {}
	for m in frappe.get_all("Student Course Marks", filters={"exam_plan": exam_plan},
	                        fields=["course", "grade", "updated_grade"]):
		if (m.updated_grade or m.grade) in failed_grades:
			failed[m.course] = failed.get(m.course, 0) + 1
	# re-exam and improvement students sit to the same timetable
	registered = {}
	for doctype in ("Re Exam Registration", "Improvement Exam Registration"):
		for r in frappe.get_all(doctype, filters={"exam_plan": exam_plan, "status": "Registered"}, fields=["course"]):
			registered[r.course] = registered.get(r.course, 0) + 1
	windows = set(frappe.get_all("Re Exam Course Setting", filters={"exam_plan": exam_plan}, pluck="course"))
	windows |= set(frappe.get_all("Improvement Exam Course Setting", filters={"exam_plan": exam_plan}, pluck="course"))
	have = {r.course for r in plan.reexam_schedules}
	courses = sorted((set(failed) | set(registered) | windows) - have)
	names = dict(frappe.get_all("Course", filters={"name": ["in", list(have | set(courses) | set(failed) | set(registered)) or [""]]},
	                            fields=["name", "course_name"], as_list=True))
	rows = [_sheet_row(r, names) for r in plan.reexam_schedules] + [_sheet_row(frappe._dict(course=c), names) for c in courses]
	for r, n in zip(rows, _row_counts(plan.term, rows, exam_plan)):
		r["students"] = n
		r["failed"] = failed.get(r["course"], 0)
	return {
		"rows": rows,
		"check": check_exam_schedule(plan, reexam=True),
		"published": cint(plan.reexam_timetable_published),
		"show_invigilator": cint(plan.reexam_show_invigilator),
		**_rooms_and_faculty(),
		"courses": [{"name": c, "course_name": names.get(c, c)} for c in sorted(c for c in have | set(courses) if c)],
		"programmes": [],
	}


@frappe.whitelist()
def get_carry_forward(exam_plan):
	"""Students still failing a course from an earlier Exam Plan (they write the
	re-exam again until they pass), for this plan's next attempt."""
	_check_access()
	from slcm.slcm.utils.reexam_attempts import students_to_carry

	rows = students_to_carry(exam_plan)
	names = {s.name: s for s in frappe.get_all("Student Master", filters={"name": ["in", [r[0] for r in rows] or [""]]},
	                                           fields=["name", "first_name", "last_name", "registration_id"])}
	courses = dict(frappe.get_all("Course", filters={"name": ["in", [r[1] for r in rows] or [""]]}, fields=["name", "course_name"], as_list=True))
	return [{
		"student": st, "student_name": " ".join(filter(None, [names[st].first_name, names[st].last_name])) if st in names else st,
		"registration_id": names[st].registration_id if st in names else "", "course": c, "course_name": courses.get(c, c), "from_plan": src,
	} for st, c, src in rows]


@frappe.whitelist()
def carry_forward_all(exam_plan, pairs=None):
	"""Bring the students (all, or the given [[student, course], ...]) into this
	plan's re-exam with their regular marks."""
	_check_access()
	from slcm.slcm.utils.reexam_attempts import carry_forward, students_to_carry

	todo = [tuple(x) for x in _load(pairs, [])] or [(st, c) for st, c, _src in students_to_carry(exam_plan)]
	done, errors = 0, []
	for st, c in todo:
		try:
			if carry_forward(st, c, exam_plan)[1] == "created":
				done += 1
		except frappe.ValidationError as e:
			frappe.clear_messages()
			errors.append(f"{st} · {c}: {e}")
	frappe.db.commit()
	return {"added": done, "errors": errors}


# ── Re-exam & improvement students (one list) ─────────────────────────────────

@frappe.whitelist()
def get_after_students(exam_plan):
	_check_access()
	from slcm.slcm.utils import after_results as ar

	courses = ar.plan_courses(exam_plan)
	names = dict(frappe.get_all("Course", filters={"name": ["in", courses or [""]]}, fields=["name", "course_name"], as_list=True))
	return {"rows": ar.students(exam_plan), "courses": [{"name": c, "course_name": names.get(c, c)} for c in courses]}


@frappe.whitelist()
def get_window(exam_plan, course):
	_check_access()
	from slcm.slcm.utils.after_results import get_window as window

	return window(exam_plan, course)


@frappe.whitelist()
def save_window(exam_plan, courses, deadline_from=None, deadline_to=None, payment_gateway=None, registration_limit=None):
	"""One registration window for the re-exam and the improvement exam of the courses."""
	_check_access()
	from slcm.slcm.utils.after_results import save_window as save

	return save(exam_plan, _load(courses, []), deadline_from, deadline_to, payment_gateway, registration_limit)


@frappe.whitelist()
def preview_enrolment(exam_plan, rows, course=None):
	_check_access()
	from slcm.slcm.utils.after_results import plan_enrolment

	lines, component = plan_enrolment(exam_plan, _load(rows, []), course)
	return {"lines": lines, "fee_component": component,
	        "enrol": sum(1 for x in lines if x["action"] == "enrol"),
	        "demands": sum(1 for x in lines if x.get("demand")),
	        "demand_total": sum(x["fee"] for x in lines if x.get("demand"))}


@frappe.whitelist()
def enrol_students(exam_plan, rows, course=None):
	_check_access()
	from slcm.slcm.utils.after_results import enrol

	return enrol(exam_plan, _load(rows, []), course)


@frappe.whitelist()
def mark_registration_paid(kind, registration, reference=""):
	_check_access()
	from slcm.slcm.utils.after_results import mark_paid

	return mark_paid(kind, registration, reference)


@frappe.whitelist()
def set_reexam_allowed(exam_plan, course, student, allowed, reason=""):
	_check_access()
	from slcm.slcm.page.re_exam.re_exam import set_student_re_exam_allowed

	return set_student_re_exam_allowed(exam_plan, course, student, allowed, reason)


@frappe.whitelist()
def check_reexam_timetable(exam_plan, rows):
	_check_access()
	from slcm.slcm.utils.exam_timetable import check_exam_schedule

	plan = frappe.get_doc("Exam Plan", exam_plan)
	rows = [_exam_row(r) for r in _load(rows, [])]
	plan.set("reexam_schedules", [r for r in rows if r.get("course") or r.get("paper")])
	for i, r in enumerate(plan.reexam_schedules, 1):
		r.idx = i
	out = check_exam_schedule(plan, reexam=True)
	# check rows are numbered among the kept ones; map them back to the rows sent
	kept = [i for i, r in enumerate(rows) if r.get("course") or r.get("paper")]
	for x in out["errors"] + out["warnings"]:
		x["row"] = kept[x["row"] - 1] + 1
	out["students"] = _row_counts(plan.term, rows, exam_plan)
	return out


@frappe.whitelist()
def save_reexam_timetable(exam_plan, rows):
	"""Replace the plan's re-exam lines (only lines with a date are kept);
	Exam Plan.validate applies the checks."""
	_check_access()
	plan = frappe.get_doc("Exam Plan", exam_plan)
	plan.set("reexam_schedules", [_exam_row(r) for r in _load(rows, []) if (r.get("course") or r.get("paper")) and r.get("exam_date")])
	plan.save()
	frappe.db.commit()
	return True


@frappe.whitelist()
def check_timetable(exam_plan, rows):
	_check_access()
	from slcm.slcm.utils.exam_timetable import preview_exam_schedule

	rows = [_exam_row(r) for r in _load(rows, [])]
	out = preview_exam_schedule(exam_plan, rows)
	out["students"] = _row_counts(frappe.db.get_value("Exam Plan", exam_plan, "term"), rows)
	return out


def _row(r):
	return {k: (r.get(k) or None) for k in ("course", "exam_date", "start_time", "end_time", "venue", "invigilator", "seat_capacity")}


# Exam rows also carry the classroom allocation sheet's columns
def _exam_row(r):
	return {**_row(r), **{k: (r.get(k) or None) for k in (
		"paper", "programme_year", "session", "hall", "invigilator_name", "id_from", "id_to")}}


@frappe.whitelist()
def save_timetable(exam_plan, rows):
	"""Replace the plan's course schedule rows; Exam Plan.validate applies every check."""
	_check_access()
	plan = frappe.get_doc("Exam Plan", exam_plan)
	plan.set("course_schedules", [_exam_row(r) for r in _load(rows, []) if r.get("course") or r.get("paper")])
	plan.save()
	frappe.db.commit()
	return True


# ── Excel sheets: classroom allocation sheet + Continuing Evaluation Schedule ─

@frappe.whitelist()
def download_timetable(exam_plan, reexam=0):
	_check_access()
	from slcm.slcm.utils import exam_sheets

	what = "Re-exam timetable" if cint(reexam) else "Exam timetable"
	exam_sheets._send(exam_sheets.timetable_workbook(exam_plan, cint(reexam)),
	                  exam_sheets._safe_filename(f"{exam_plan} - {what}") + ".xlsx")


@frappe.whitelist()
def import_timetable(exam_plan, file_url, duration_hours=3, apply=0, reexam=0):
	"""Preview (apply=0) or replace (apply=1) the (re-)exam timetable from the sheet."""
	_check_access()
	from slcm.slcm.utils import exam_sheets

	return exam_sheets.import_timetable(exam_plan, exam_sheets.file_content(file_url), flt(duration_hours) or 3,
	                                    cint(apply), file_url, cint(reexam))


@frappe.whitelist()
def get_assessment_grid(exam_plan):
	_check_access()
	from slcm.slcm.utils.exam_sheets import assessment_grid

	return assessment_grid(exam_plan)


@frappe.whitelist()
def save_assessment_grid(exam_plan, lines):
	_check_access()
	from slcm.slcm.utils.exam_sheets import save_assessment_grid as save

	return save(exam_plan, _load(lines, []))


@frappe.whitelist()
def download_assessment_sheet(exam_plan, blank=0):
	_check_access()
	from slcm.slcm.utils import exam_sheets

	exam_sheets._send(exam_sheets.assessment_workbook(exam_plan, blank=cint(blank)),
	                  exam_sheets._safe_filename(f"{exam_plan} - Continuing Evaluation Schedule") + ".xlsx")


@frappe.whitelist()
def import_assessment_sheet(exam_plan, file_url, mapping=None, apply=0):
	"""Preview (apply=0) or save (apply=1) the Continuing Evaluation Schedule sheet;
	mapping {subject: course} settles subjects that aren't a course name."""
	_check_access()
	from slcm.slcm.utils import exam_sheets

	return exam_sheets.import_assessment_sheet(exam_plan, exam_sheets.file_content(file_url), _load(mapping, {}), cint(apply), file_url)


@frappe.whitelist()
def download_import_issues(exam_plan, file_url, sheet, duration_hours=3, mapping=None):
	"""The problems the import preview found, one line per sheet row, as Excel."""
	_check_access()
	from slcm.slcm.utils import exam_sheets

	content = exam_sheets.file_content(file_url)
	if sheet in ("timetable", "reexam"):
		issues = exam_sheets.timetable_issues(exam_plan, content, flt(duration_hours) or 3, sheet == "reexam")[2]
		title = _("Re-exam timetable import problems") if sheet == "reexam" else _("Exam timetable import problems")
	else:
		issues = exam_sheets.assessment_issues(exam_plan, content, _load(mapping, {}))[2]
		title = _("Continuing Evaluation Schedule import problems")
	exam_sheets._send(exam_sheets.issues_workbook(issues, f"{title}: {exam_plan}"),
	                  exam_sheets._safe_filename(f"{exam_plan} - import problems") + ".xlsx")


@frappe.whitelist()
def download_log_issues(log):
	_check_access()
	from slcm.slcm.utils import exam_sheets

	doc = frappe.get_doc("Exam Sheet Import Log", log)
	issues = [{"sheet_row": x.sheet_row, "level": x.level, "line": x.line, "message": x.message} for x in doc.issues]
	exam_sheets._send(exam_sheets.issues_workbook(issues, f"{doc.sheet} import problems: {doc.exam_plan} ({doc.name})"),
	                  exam_sheets._safe_filename(f"{doc.name} - import problems") + ".xlsx")


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

