# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""Shared rules for entering marks and grades.

Used by the desk Course Results page (slcm.slcm.page.examination_result) and
the faculty portal Grades page (slcm.api.faculty_grades), so both enforce the
same lock, access, validation and arrear-badge rules.

Access Result Settings (one per exam plan + course, set on the desk Result
Settings page) is the faculty switchboard: view / edit access with deadlines,
the course LOCK, student masking, the grade-access flags and the exam types
faculty may see. The course LOCK and a student's own "Locked" marks status
apply to everyone; the rest applies to faculty only.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

# Student Course Marks.status
STATUS_DRAFT = "Draft"
STATUS_SUBMITTED = "Submitted"
STATUS_LOCKED = "Locked"
MARKS_STATUSES = (STATUS_DRAFT, STATUS_SUBMITTED, STATUS_LOCKED)

# Grades that are not in a grading schema but are written by the system
SPECIAL_GRADES = {"Ab", "AS"}

# Re-exam / improvement registrations count only once paid
PAID_STATUSES = ("Paid",)


# ---------------------------------------------------------------------------
# Access Result Settings
# ---------------------------------------------------------------------------

def get_access(exam_plan, course):
	"""Access Result Settings for exam plan + course as a dict, with the same
	defaults as a freshly created record (view/edit on, unlocked, grade
	features off) when none exists."""
	row = frappe.db.get_value(
		"Access Result Settings",
		{"exam_plan": exam_plan, "course": course},
		[
			"name", "view_access", "view_deadline", "edit_access", "edit_deadline", "status",
			"mask_student_info", "auto_generate_grade_access", "edit_grade_access",
			"generate_grade_report",
		],
		as_dict=True,
	) if exam_plan and course else None
	row = row or frappe._dict()

	def flag(field, default):
		# 0 must stay 0: the old `int(x or 1)` pattern turned "off" back on
		value = row.get(field)
		return default if value is None else cint(value)

	visible_exams = []
	if row.get("name"):
		visible_exams = frappe.get_all(
			"Result Exam Visibility",
			filters={"parent": row.name, "parenttype": "Access Result Settings"},
			pluck="exam_type",
			ignore_permissions=True,
		)

	return frappe._dict(
		exists=bool(row.get("name")),
		view_access=flag("view_access", 1),
		view_deadline=row.get("view_deadline"),
		edit_access=flag("edit_access", 1),
		edit_deadline=row.get("edit_deadline"),
		locked=(row.get("status") == "LOCKED"),
		mask_student_info=flag("mask_student_info", 0),
		auto_generate_grade_access=flag("auto_generate_grade_access", 0),
		edit_grade_access=flag("edit_grade_access", 0),
		generate_grade_report=flag("generate_grade_report", 0),
		visible_exams=[v for v in visible_exams if v],
	)


def _passed(deadline):
	return bool(deadline and now_datetime() > get_datetime(deadline))


def view_block_reason(access):
	"""Why faculty may not see results, or None."""
	if not access.view_access:
		return _("View access for this course has been turned off. Please contact your Programme Chair.")
	if _passed(access.view_deadline):
		return _("The view deadline for this course has passed. Please contact your Programme Chair.")
	return None


def edit_block_reason(access, for_faculty):
	"""Why marks can't be changed for this course right now, or None.
	The course lock applies to everyone; edit access and its deadline are
	faculty settings."""
	if access.locked:
		return _("Result entry is locked for this course.")
	if for_faculty:
		if not access.edit_access:
			return _("Edit access for this course has been turned off.")
		if _passed(access.edit_deadline):
			return _("The edit deadline for this course has passed.")
	return None


def assert_course_editable(exam_plan, course, for_faculty=False, access=None):
	reason = edit_block_reason(access or get_access(exam_plan, course), for_faculty)
	if reason:
		frappe.throw(reason, title=_("Not Editable"))


def assert_student_editable(scm_name, for_faculty=False):
	"""A student's marks status: Locked blocks everyone, Submitted blocks
	faculty (the admin reviews it, or sets it back to Draft)."""
	if not scm_name:
		return
	status = frappe.db.get_value("Student Course Marks", scm_name, "status") or STATUS_DRAFT
	if status == STATUS_LOCKED:
		frappe.throw(_("This student's marks are locked."), title=_("Not Editable"))
	if for_faculty and status == STATUS_SUBMITTED:
		frappe.throw(
			_("This student's marks have been submitted. Set them back to Draft to edit."),
			title=_("Not Editable"),
		)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def get_max_marks(evaluation_schema):
	"""{(component, assessment_type): maximum_marks} for regular and re-exam
	components of an evaluation schema."""
	if not evaluation_schema:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT component, assessment_type, maximum_marks FROM `tabSchema Assessment Config` WHERE parent = %(s)s
		UNION ALL
		SELECT component, assessment_type, maximum_marks FROM `tabSchema Reexam Config` WHERE parent = %(s)s
		""",
		{"s": evaluation_schema},
		as_dict=True,
	)
	return {((r.component or ""), (r.assessment_type or "")): flt(r.maximum_marks) for r in rows}


def parse_marks(value, max_marks=None, label=None):
	"""Blank -> None (an empty mark, not 0). Otherwise a number between 0 and
	max_marks, or a ValidationError naming the field."""
	if value is None or (isinstance(value, str) and value.strip() in ("", "null", "--")):
		return None
	what = label or _("Marks")
	try:
		number = float(value)
	except (TypeError, ValueError):
		frappe.throw(_("{0}: '{1}' is not a number.").format(what, value))
	if number < 0:
		frappe.throw(_("{0} cannot be negative.").format(what))
	if max_marks and number > flt(max_marks):
		frappe.throw(_("{0} cannot be more than {1}.").format(what, flt(max_marks)))
	return round(number, 2)


def get_valid_grades(grade_schema):
	"""Grades allowed for a grading schema (regular and re-exam composition)."""
	if not grade_schema:
		return set()
	rows = frappe.db.sql(
		"SELECT grade FROM `tabGrading Schema Component` WHERE parent = %s",
		grade_schema,
		as_list=True,
	)
	grades = {r[0] for r in rows if r[0]}
	try:
		schema = frappe.get_cached_doc("Grading Schema", grade_schema)
		grades |= {r.grade for r in (schema.get("reexam_grades") or []) if r.grade}
	except frappe.DoesNotExistError:
		pass
	return grades


def validate_grade(value, grade_schema):
	"""Blank is allowed (clears the grade); anything else must be a grade of
	the schema (or Ab / AS)."""
	value = (value or "").strip()
	if not value or value in SPECIAL_GRADES:
		return value
	valid = get_valid_grades(grade_schema)
	if valid and value not in valid:
		frappe.throw(
			_("'{0}' is not a grade in the grading schema. Allowed: {1}").format(
				value, ", ".join(sorted(valid))
			)
		)
	return value


# ---------------------------------------------------------------------------
# Arrear / improvement badges
# ---------------------------------------------------------------------------

def get_reexam_attempts(course, students):
	"""{student: number of paid re-exam registrations for the course}."""
	students = [s for s in (students or []) if s]
	if not course or not students:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT student, COUNT(*) AS cnt
		FROM `tabRe Exam Registration`
		WHERE course = %(course)s AND student IN %(students)s
		  AND status = 'Registered' AND payment_status IN %(paid)s
		GROUP BY student
		""",
		{"course": course, "students": tuple(students), "paid": PAID_STATUSES},
		as_dict=True,
	)
	return {r.student: cint(r.cnt) for r in rows}


def arrear_badge(attempts):
	"""One R per re-exam written: R, RR, RRR, ..."""
	return "R" * cint(attempts)


def is_improved(row):
	"""The final result was raised by a re-exam or an improvement exam."""
	if cint(row.get("improvement_applied")):
		return True
	updated = row.get("updated_final_marks")
	original = row.get("total_marks")
	return updated is not None and original is not None and flt(updated) > flt(original)
