import re

import frappe
from frappe.utils import getdate, nowdate

no_cache = 1


def get_context(context):
	context.no_cache = 1

	if frappe.session.user == "Guest":
		context.is_guest = True
		return context

	context.is_guest = False
	context.active_page = "enrollment"

	student_name = _get_student_name()
	if not student_name:
		context.no_student = True
		_set_nav_defaults(context)
		return context

	context.no_student = False

	try:
		student = frappe.get_doc("Student Master", student_name)
		_set_student_nav(context, student)

		# ── All enrollments ───────────────────────────────────────
		enrollments = frappe.get_all(
			"Student Enrollment",
			filters={"student": student_name},
			fields=["name", "cohort", "program", "academic_year", "term_name", "status",
					"faculty_advisor", "enrollment_date", "term_start_date", "creation"],
			order_by="creation desc",
			ignore_permissions=True,
		)

		# Newest first: academic year, then term start / enrolment date, then creation
		def _sort_key(e):
			year = re.match(r"\s*(\d{4})", e.academic_year or "")
			when = e.term_start_date or e.enrollment_date or getdate(e.creation)
			return (int(year.group(1)) if year else 0, str(when), str(e.creation))
		enrollments.sort(key=_sort_key, reverse=True)

		# Mark active + upcoming (a Pending enrolment, or one whose term hasn't started)
		today = getdate(nowdate())
		context.active_enrollment = None
		for e in enrollments:
			e["is_active"] = e.status == "Enrolled"
			start = e.term_start_date or e.enrollment_date
			e["is_upcoming"] = e.status == "Pending" or bool(
				e.status == "Enrolled" and start and getdate(start) > today
			)
			if e["is_active"] and not context.active_enrollment:
				context.active_enrollment = e

		# Courses per enrolment for the history view (bulk-fetched)
		enr_names = [e.name for e in enrollments]
		hist_rows = frappe.get_all(
			"Student Enrollment Course",
			filters={"parent": ["in", enr_names], "parenttype": "Student Enrollment"},
			fields=["parent", "course", "course_offering", "course_type", "credits", "status", "grade", "idx"],
			order_by="idx asc",
			ignore_permissions=True,
		) if enr_names else []
		# Older rows may only link a Course Offering — resolve the course through it
		off_ids = list({r.course_offering for r in hist_rows if r.course_offering and not r.course})
		off_map = {
			o.name: o for o in frappe.get_all(
				"Course Offering",
				filters={"name": ["in", off_ids]},
				fields=["name", "course_name", "course_title", "credit_value"],
				ignore_permissions=True,
			)
		} if off_ids else {}
		for r in hist_rows:
			o = off_map.get(r.course_offering) if not r.course else None
			if o:
				r.course = o.course_title or None
				r.offering_name = o.course_name
				r.offering_credits = o.credit_value
		course_ids = list({r.course for r in hist_rows if r.course})
		course_map = {
			c.name: c for c in frappe.get_all(
				"Course",
				filters={"name": ["in", course_ids]},
				fields=["name", "course_name", "course_code", "credit_value"],
				ignore_permissions=True,
			)
		} if course_ids else {}

		by_enr = {}
		for r in hist_rows:
			if not (r.course or r.course_offering):
				continue  # blank child row — nothing to show
			c = course_map.get(r.course) or frappe._dict()
			by_enr.setdefault(r.parent, []).append({
				"course_code": c.get("course_code") or r.course or "",
				"course_name": r.get("offering_name") or c.get("course_name") or r.course or r.course_offering,
				"course_type": r.course_type or "Core",
				"credits": r.credits or r.get("offering_credits") or c.get("credit_value") or 0,
				"status": r.status or "Enrolled",
				"grade": r.grade or "",
			})
		for e in enrollments:
			e["courses"] = by_enr.get(e.name, [])
			e["total_credits"] = sum(c["credits"] for c in e["courses"] if c["status"] != "Dropped")

		# Faculty adviser is a Faculty link — show the person's name, not the record ID
		adv_ids = list({e.faculty_advisor for e in enrollments if e.faculty_advisor})
		adv_names = {
			str(f.name): " ".join(filter(None, [f.first_name, f.last_name])) or str(f.name)
			for f in frappe.get_all(
				"Faculty",
				filters={"name": ["in", adv_ids]},
				fields=["name", "first_name", "last_name"],
				ignore_permissions=True,
			)
		} if adv_ids else {}
		for e in enrollments:
			e["faculty_advisor_name"] = adv_names.get(str(e.faculty_advisor)) or e.faculty_advisor or ""

		context.enrollments = enrollments

		# ── Course offerings for active enrollment ────────────────
		active_courses = []
		dropped_courses = []
		if context.active_enrollment:
			enrollment_name = context.active_enrollment["name"]

			# Child rows from Student Enrollment Course child table
			prog_rows = frappe.get_all(
				"Student Enrollment Course",
				filters={"parent": enrollment_name},
				fields=["course_offering", "course", "course_type", "credits", "status", "grade"],
				ignore_permissions=True,
			)

			# Fetch Course Offering details in bulk
			co_names = [r.course_offering for r in prog_rows if r.course_offering]
			co_map = {}
			if co_names:
				for co in frappe.get_all(
					"Course Offering",
					filters={"name": ["in", co_names]},
					fields=["name", "course_name", "faculty", "credit_value", "term_name"],
					ignore_permissions=True,
				):
					co_map[co.name] = co

			# Faculty names: the offering's own faculty link, else its faculty table
			fac_ids = {co.faculty for co in co_map.values() if co.get("faculty")}
			table_rows = frappe.get_all(
				"Course Offering Faculty",
				filters={"parent": ["in", co_names], "parenttype": "Course Offering"},
				fields=["parent", "faculty", "faculty_name", "is_primary", "idx"],
				order_by="is_primary desc, idx asc",
				ignore_permissions=True,
			) if co_names else []
			fac_ids.update(r.faculty for r in table_rows if r.faculty)
			fac_names = {}
			if fac_ids:
				for f in frappe.get_all(
					"Faculty",
					filters={"name": ["in", list(fac_ids)]},
					fields=["name", "first_name", "last_name"],
					ignore_permissions=True,
				):
					# Faculty names are integers; link fields store them as strings
					fac_names[str(f.name)] = " ".join(filter(None, [f.first_name, f.last_name])) or str(f.name)
			table_by_co = {}
			for r in table_rows:
				label = r.faculty_name or fac_names.get(str(r.faculty)) or r.faculty
				if label and label not in table_by_co.setdefault(r.parent, []):
					table_by_co[r.parent].append(label)

			# Enrich with faculty + attendance
			for r in prog_rows:
				co = co_map.get(r.course_offering) or frappe._dict()

				faculty = []
				if co.get("faculty"):
					faculty.append(fac_names.get(str(co.faculty)) or co.faculty)
				for label in table_by_co.get(r.course_offering, []):
					if label not in faculty:
						faculty.append(label)

				att = frappe.db.get_value(
					"Attendance Summary",
					{"student": student_name, "course_offering": r.course_offering},
					["attendance_percentage", "eligible_for_exam"],
					as_dict=True,
				) if r.course_offering else None
				has_att = bool(att)

				entry = {
					"course": r.course,
					"course_code": (course_map.get(r.course) or {}).get("course_code") or r.course or "",
					"course_offering": r.course_offering or "",
					"course_name": co.get("course_name") or r.course or "—",
					"course_type": r.course_type or "Core",
					"course_status": r.status or "Enrolled",
					"credits": co.get("credit_value") or r.credits or 0,
					"faculty": ", ".join(faculty),
					"term": co.get("term_name") or context.active_enrollment.get("term_name") or "",
					# None = no attendance recorded yet (not the same as 0%)
					"attendance_pct": round(float(att.attendance_percentage or 0), 1) if has_att else None,
					"eligible": bool(att.eligible_for_exam) if has_att else None,
				}
				if r.status == "Dropped":
					dropped_courses.append(entry)
				else:
					active_courses.append(entry)

		active_courses.sort(key=lambda c: (c["course_type"] != "Core", c["course_name"]))
		context.active_courses = active_courses
		context.dropped_courses = dropped_courses
		context.total_credits = sum(c["credits"] for c in active_courses)

		# ── Credit summary ────────────────────────────────────────
		context.core_credits = sum(c["credits"] for c in active_courses if c["course_type"] == "Core")
		context.elective_credits = sum(c["credits"] for c in active_courses if c["course_type"] == "Elective")

	except Exception as e:
		frappe.log_error(f"Enrollment portal error: {e}", "Student Portal")
		context.portal_error = str(e)
		_set_nav_defaults(context)

	return context


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
