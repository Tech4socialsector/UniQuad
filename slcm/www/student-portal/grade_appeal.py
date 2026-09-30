import frappe
from frappe.utils import cint, today

# NOTE: Frappe maps grade-appeal.html → grade_appeal.py (hyphens become
# underscores), so this file must keep the underscore name to be loaded.

no_cache = 1

APPEAL_TYPES = [
	{"value": "Re-evaluation", "icon": "fact_check", "hint": "Ask for your answer script to be evaluated again"},
	{"value": "Marks Correction", "icon": "calculate", "hint": "Marks were totalled or entered incorrectly"},
	{"value": "Grade Change", "icon": "swap_vert", "hint": "The grade doesn't match the marks awarded"},
]
ACTIVE_STATUSES = ("Submitted", "Under Review")
MIN_REASON_CHARS = 20


def get_context(context):
	context.no_cache = 1

	if frappe.session.user == "Guest":
		context.is_guest = True
		return context

	context.is_guest = False
	context.active_page = "grade_appeal"
	context.appeal_types = APPEAL_TYPES
	context.min_reason_chars = MIN_REASON_CHARS
	context.appeals = []
	context.eligible_results = []

	student_name = _get_student_name()
	if not student_name:
		context.no_student = True
		_set_nav_defaults(context)
		return context

	context.no_student = False

	try:
		student = frappe.get_doc("Student Master", student_name)
		_set_student_nav(context, student)

		course_meta = {}  # course id → {course_name, course_code}

		def _course(cid):
			if cid not in course_meta:
				row = frappe.db.get_value("Course", cid, ["course_name", "course_code"], as_dict=True) or frappe._dict()
				course_meta[cid] = frappe._dict(
					course_name=row.course_name or cid or "—",
					course_code=row.course_code or cid or "",
				)
			return course_meta[cid]

		exam_names = {}

		def _exam(plan):
			if plan not in exam_names:
				exam_names[plan] = frappe.db.get_value("Exam Plan", plan, "exam_name") or plan
			return exam_names[plan]

		# ── Existing appeals ──────────────────────────────────────
		appeals = frappe.get_all(
			"Grade Appeal",
			filters={"student": student_name},
			fields=[
				"name", "exam_plan", "course", "appeal_type", "status",
				"current_grade", "current_marks", "reason", "supporting_remarks",
				"resolution", "submitted_on", "resolved_on", "creation",
			],
			order_by="creation desc",
			limit=50,
			ignore_permissions=True,
		)
		active_types = {}  # "exam_plan|course" → [appeal types still open]
		for a in appeals:
			c = _course(a.course)
			a["course_name"] = c.course_name
			a["course_code"] = c.course_code
			a["exam_name"] = _exam(a.exam_plan)
			a["is_active"] = a.status in ACTIVE_STATUSES
			if a["is_active"]:
				active_types.setdefault(f"{a.exam_plan}|{a.course}", []).append(a.appeal_type)

		context.appeals = appeals
		context.active_appeals = sum(1 for a in appeals if a["is_active"])
		context.resolved_appeals = sum(1 for a in appeals if a.status == "Resolved")
		context.rejected_appeals = sum(1 for a in appeals if a.status == "Rejected")

		# ── Results eligible for appeal ───────────────────────────
		# Same gate as the Results page: the student's result is published.
		published_plans = frappe.get_all(
			"Student Result Publish",
			filters={"student": student_name, "is_published": 1},
			fields=["exam_plan", "published_on"],
			ignore_permissions=True,
		)
		show_total = {p.exam_plan: _shows_total(p.exam_plan) for p in published_plans}

		eligible = []
		if published_plans:
			marks = frappe.get_all(
				"Student Course Marks",
				filters={"student": student_name, "exam_plan": ["in", list(show_total)]},
				fields=["exam_plan", "course", "grade", "moderated_grade", "updated_grade",
						"total_marks", "updated_final_marks", "attendance_status"],
				ignore_permissions=True,
			)
			for m in marks:
				grade = m.updated_grade or m.moderated_grade or m.grade or ""
				if not grade or m.attendance_status == "Absent":
					continue  # nothing published to appeal against
				c = _course(m.course)
				key = f"{m.exam_plan}|{m.course}"
				total = m.updated_final_marks or m.total_marks
				eligible.append({
					"key": key,
					"exam_plan": m.exam_plan,
					"exam_name": _exam(m.exam_plan),
					"course": m.course,
					"course_name": c.course_name,
					"course_code": c.course_code,
					"grade": grade,
					"marks": round(float(total), 2) if (total is not None and show_total.get(m.exam_plan)) else None,
					"active_types": active_types.get(key, []),
				})
			eligible.sort(key=lambda r: (r["exam_name"], r["course_name"]))
			for r in eligible:
				r["all_blocked"] = len(r["active_types"]) >= len(APPEAL_TYPES)

		context.eligible_results = eligible
		context.open_for_appeal = sum(1 for r in eligible if not r["all_blocked"])

	except Exception as e:
		frappe.log_error(f"Grade Appeal portal error: {e}", "Student Portal")
		context.portal_error = str(e)
		_set_nav_defaults(context)
		context.setdefault("active_appeals", 0)
		context.setdefault("resolved_appeals", 0)
		context.setdefault("rejected_appeals", 0)
		context.setdefault("open_for_appeal", 0)

	return context


@frappe.whitelist()
def submit_appeal(exam_plan, course, appeal_type, reason, supporting_remarks=""):
	student_name = _get_student_name()
	if not student_name:
		frappe.throw("Student record not found.")

	if appeal_type not in {t["value"] for t in APPEAL_TYPES}:
		frappe.throw("Please choose a valid appeal type.")

	reason = (reason or "").strip()
	if len(reason) < MIN_REASON_CHARS:
		frappe.throw(f"Please describe your reason in at least {MIN_REASON_CHARS} characters.")

	if not frappe.db.exists(
		"Student Result Publish",
		{"student": student_name, "exam_plan": exam_plan, "is_published": 1},
	):
		frappe.throw("You can only appeal results that have been published.")

	marks = frappe.db.get_value(
		"Student Course Marks",
		{"student": student_name, "exam_plan": exam_plan, "course": course},
		["grade", "moderated_grade", "updated_grade", "total_marks", "updated_final_marks", "course_offering"],
		as_dict=True,
	)
	if not marks:
		frappe.throw("No published marks were found for this course.")

	course_offering = _resolve_course_offering(student_name, course, marks.course_offering)
	if not course_offering:
		frappe.throw("This course isn't linked to a course offering yet. Please contact the Examination Office.")

	doc = frappe.get_doc({
		"doctype": "Grade Appeal",
		"student": student_name,
		"exam_plan": exam_plan,
		"course": course,
		"course_offering": course_offering,
		"appeal_type": appeal_type,
		"reason": reason,
		"supporting_remarks": (supporting_remarks or "").strip(),
		"current_grade": marks.updated_grade or marks.moderated_grade or marks.grade or "",
		"current_marks": marks.updated_final_marks or marks.total_marks or 0,
		"status": "Submitted",
		"submitted_on": today(),
	})
	doc.insert(ignore_permissions=True)  # Grade Appeal.validate() rejects active duplicates
	frappe.db.commit()
	return {"name": doc.name, "status": doc.status}


def _resolve_course_offering(student_name, course, from_marks=None):
	"""Marks record → student's enrolment → any offering of the course."""
	if from_marks:
		return from_marks
	enrollments = frappe.get_all("Student Enrollment", filters={"student": student_name}, pluck="name")
	if enrollments:
		co = frappe.get_all(
			"Student Enrollment Course",
			filters={"parent": ["in", enrollments], "parenttype": "Student Enrollment",
					 "course": course, "course_offering": ["is", "set"]},
			pluck="course_offering",
			order_by="creation desc",
			limit=1,
			ignore_permissions=True,
		)
		if co:
			return co[0]
	co = frappe.get_all(
		"Course Offering", filters={"course_title": course}, pluck="name",
		order_by="creation desc", limit=1, ignore_permissions=True,
	)
	return co[0] if co else None


def _shows_total(exam_plan):
	try:
		return bool(cint(frappe.db.get_value("Publish Result Setting", exam_plan, "show_total_marks")))
	except Exception:
		return False


def _get_student_name():
	user = frappe.session.user
	name = frappe.db.get_value("Student Master", {"user": user}, "name")
	if not name:
		name = frappe.db.get_value("Student Master", {"email": user}, "name")
	if not name:
		name = frappe.db.get_value("Student Master", {"official_email_id": user}, "name")
	return name


def _set_student_nav(context, student):
	full_name = " ".join(filter(None, [student.first_name, student.middle_name, student.last_name]))
	context.student_name = full_name or student.name
	context.student_id = student.registration_id or student.name
	context.student_photo = student.passport_size_photo or ""
	context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
	context.programme_name = frappe.db.get_value("Batch", student.programme, "cohort_name") or student.programme or ""
	context.department = student.department or ""
	context.batch_year = student.batch_year or ""


def _set_nav_defaults(context):
	user = frappe.session.user
	user_doc = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True)
	context.student_name = (user_doc.full_name if user_doc else "") or user.split("@")[0]
	context.student_id = ""
	context.student_photo = (user_doc.user_image if user_doc else "") or ""
	context.student_initial = (context.student_name[0]).upper() if context.student_name else "S"
	context.programme_name = ""
	context.department = ""
	context.batch_year = ""
