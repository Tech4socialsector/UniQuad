# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _
from frappe.utils import now_datetime

PUBLISH_RESULT_ROLES = {"System Manager", "Academics User"}


def _check_access():
	"""This page is restricted at the desk UI level, but the whitelisted RPCs
	are directly callable via /api/method/, so mutating actions must enforce
	the same role themselves."""
	if not PUBLISH_RESULT_ROLES & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def get_exam_plans(search=None):
	"""Return exam plans for the plan selector."""
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
	"""Return distinct programmes (with display names) for students in this exam plan."""
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
	"""Return distinct courses in this exam plan, optionally scoped to a programme."""
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
def get_publish_stats(exam_plan, course="", programme=""):
	"""Return publish summary stats, optionally filtered by programme and/or course."""
	if not exam_plan:
		return {}

	params = {"exam_plan": exam_plan}

	# ── Total students ────────────────────────────────────────────────────────
	total_join = ""
	total_cond = "scm.exam_plan = %(exam_plan)s"
	if programme:
		total_join = "INNER JOIN `tabStudent Master` sm ON sm.name = scm.student"
		total_cond += " AND sm.programme_of_study = %(programme)s"
		params["programme"] = programme
	if course:
		total_cond += " AND scm.course = %(course)s"
		params["course"] = course

	total_row = frappe.db.sql(
		f"SELECT COUNT(DISTINCT scm.student) AS cnt "
		f"FROM `tabStudent Course Marks` scm {total_join} WHERE {total_cond}",
		params, as_dict=True,
	)
	total = total_row[0]["cnt"] if total_row else 0

	# ── Published students ────────────────────────────────────────────────────
	pub_joins = []
	pub_cond  = "srp.exam_plan = %(exam_plan)s AND srp.is_published = 1"

	if course:
		pub_joins.append(
			"INNER JOIN `tabStudent Course Marks` scm "
			"ON scm.exam_plan = srp.exam_plan AND scm.student = srp.student"
		)
		pub_cond += " AND scm.course = %(course)s"
	if programme:
		pub_joins.append("INNER JOIN `tabStudent Master` sm ON sm.name = srp.student")
		pub_cond += " AND sm.programme_of_study = %(programme)s"

	pub_row = frappe.db.sql(
		f"SELECT COUNT(DISTINCT srp.student) AS cnt "
		f"FROM `tabStudent Result Publish` srp {' '.join(pub_joins)} WHERE {pub_cond}",
		params, as_dict=True,
	)
	published = pub_row[0]["cnt"] if pub_row else 0

	return {
		"total":         total,
		"published":     published,
		"not_published": total - published,
	}


@frappe.whitelist()
def get_publish_inst_filter_options(exam_plan):
	"""Return distinct programmes and batches for students in this exam plan."""
	if not exam_plan:
		return {"programmes": [], "batches": []}

	rows = frappe.db.sql(
		"""
		SELECT DISTINCT sm.programme_of_study AS programme, sm.batch AS batch_year
		FROM `tabStudent Course Marks` scm
		INNER JOIN `tabStudent Master` sm ON sm.name = scm.student
		WHERE scm.exam_plan = %(exam_plan)s
		""",
		{"exam_plan": exam_plan},
		as_dict=True,
	)
	programmes = sorted(set(r["programme"] for r in rows if r.get("programme")))
	batches    = sorted(set(str(r["batch_year"]) for r in rows if r.get("batch_year")), reverse=True)
	return {"programmes": programmes, "batches": batches}


def _build_publish_where(exam_plan, search="", status_filter="all",
                         inst_programmes="", inst_batches="", course="", programme=""):
	"""Shared WHERE-clause builder for the Publish Results student query —
	used both for the paginated table (get_publish_students) and for
	resolving the full filtered set for bulk email, so "currently filtered
	students" means exactly the same thing in both places."""
	f_programmes = json.loads(inst_programmes) if inst_programmes else []
	f_batches    = json.loads(inst_batches)    if inst_batches    else []

	params     = {"exam_plan": exam_plan}
	extra_cond = ""

	if programme:
		extra_cond += " AND sm.programme_of_study = %(programme)s"
		params["programme"] = programme

	if course:
		extra_cond += " AND scm.course = %(course)s"
		params["course"] = course

	if search:
		extra_cond += (
			" AND (sm.registration_id LIKE %(search)s"
			" OR sm.first_name LIKE %(search)s"
			" OR sm.last_name LIKE %(search)s)"
		)
		params["search"] = f"%{search}%"

	if status_filter == "published":
		extra_cond += " AND COALESCE(srp.is_published, 0) = 1"
	elif status_filter == "not_published":
		extra_cond += " AND COALESCE(srp.is_published, 0) = 0"

	if f_programmes:
		placeholders = ",".join([f"%(prog_{i})s" for i in range(len(f_programmes))])
		extra_cond += f" AND sm.programme_of_study IN ({placeholders})"
		for i, v in enumerate(f_programmes):
			params[f"prog_{i}"] = v
	if f_batches:
		placeholders = ",".join([f"%(batch_{i})s" for i in range(len(f_batches))])
		extra_cond += f" AND sm.batch IN ({placeholders})"
		for i, v in enumerate(f_batches):
			params[f"batch_{i}"] = v

	return params, extra_cond


@frappe.whitelist()
def get_publish_students(exam_plan, search="", page=1, page_length=20,
                         status_filter="all", sort_by="registration_id", sort_order="asc",
                         inst_programmes="", inst_batches="", course="", programme=""):
	"""Return paginated students with their publish status for the given exam plan."""
	if not exam_plan:
		return {"students": [], "total": 0}

	page        = int(page)
	page_length = int(page_length)
	offset      = (page - 1) * page_length
	sort_dir    = "DESC" if sort_order == "desc" else "ASC"

	sort_col_map = {
		"registration_id": "sm.registration_id",
		"name":            "CONCAT_WS(' ', sm.first_name, sm.last_name)",
		"programme":       "sm.programme_of_study",
	}
	sort_col = sort_col_map.get(sort_by, "sm.registration_id")

	params, extra_cond = _build_publish_where(
		exam_plan, search, status_filter, inst_programmes, inst_batches, course, programme
	)

	students = frappe.db.sql(
		f"""
		SELECT
			sm.name                                                              AS student,
			sm.registration_id,
			TRIM(CONCAT_WS(' ', sm.first_name,
				COALESCE(NULLIF(sm.middle_name,''), NULL),
				sm.last_name))                                                   AS student_name,
			sm.programme_of_study                                                AS programme,
			sm.passport_size_photo                                               AS image,
			sm.email,
			COALESCE(srp.is_published, 0)                                        AS is_published,
			srp.published_by,
			srp.published_on,
			srp.unpublished_by,
			srp.unpublished_on
		FROM `tabStudent Course Marks` scm
		INNER JOIN `tabStudent Master` sm ON sm.name = scm.student
		LEFT JOIN `tabStudent Result Publish` srp
			ON srp.exam_plan = %(exam_plan)s AND srp.student = sm.name
		WHERE scm.exam_plan = %(exam_plan)s
		{extra_cond}
		GROUP BY scm.student
		ORDER BY {sort_col} {sort_dir}
		LIMIT %(lim)s OFFSET %(off)s
		""",
		{**params, "lim": page_length, "off": offset},
		as_dict=True,
	)

	# Resolve user full names
	for s in students:
		s["published_by_name"]   = frappe.db.get_value("User", s["published_by"],   "full_name") if s.get("published_by")   else None
		s["unpublished_by_name"] = frappe.db.get_value("User", s["unpublished_by"], "full_name") if s.get("unpublished_by") else None

	total_row = frappe.db.sql(
		f"""
		SELECT COUNT(DISTINCT scm.student) AS cnt
		FROM `tabStudent Course Marks` scm
		INNER JOIN `tabStudent Master` sm ON sm.name = scm.student
		LEFT JOIN `tabStudent Result Publish` srp
			ON srp.exam_plan = %(exam_plan)s AND srp.student = sm.name
		WHERE scm.exam_plan = %(exam_plan)s
		{extra_cond}
		""",
		params,
		as_dict=True,
	)
	total = total_row[0]["cnt"] if total_row else 0

	return {"students": students, "total": total}


@frappe.whitelist()
def toggle_publish(exam_plan, student, publish):
	"""Toggle publish status for a single student."""
	_check_access()
	if not exam_plan or not student:
		return False

	publish = int(publish)
	user    = frappe.session.user
	now     = now_datetime()

	existing = frappe.db.get_value(
		"Student Result Publish",
		{"exam_plan": exam_plan, "student": student},
		"name",
	)

	if existing:
		updates = {"is_published": publish}
		if publish:
			updates["published_by"]   = user
			updates["published_on"]   = now
		else:
			updates["unpublished_by"] = user
			updates["unpublished_on"] = now
		frappe.db.set_value("Student Result Publish", existing, updates)
	else:
		doc = frappe.get_doc({
			"doctype":        "Student Result Publish",
			"exam_plan":      exam_plan,
			"student":        student,
			"is_published":   publish,
			"published_by":   user if publish else None,
			"published_on":   now  if publish else None,
			"unpublished_by": None if publish else user,
			"unpublished_on": None if publish else now,
		})
		doc.insert(ignore_permissions=True)

	frappe.db.commit()

	full_name = frappe.db.get_value("User", user, "full_name") or user
	if publish:
		return {"published_by_name": full_name, "published_on": str(now),
		        "unpublished_by_name": None,    "unpublished_on": None}
	else:
		return {"published_by_name": None, "published_on": None,
		        "unpublished_by_name": full_name, "unpublished_on": str(now)}


@frappe.whitelist()
def bulk_publish(exam_plan, students, publish):
	"""Bulk publish or unpublish a list of students."""
	_check_access()
	if not exam_plan or not students:
		return 0

	if isinstance(students, str):
		students = json.loads(students)

	publish = int(publish)
	count   = 0
	for student in students:
		toggle_publish(exam_plan, student, publish)
		count += 1

	return count


@frappe.whitelist()
def send_bulk_publish_email(exam_plan, email_template, search="", status_filter="all",
                            inst_programmes="", inst_batches="", course="", programme=""):
	"""Enqueue a background job emailing every student currently matching the
	Publish Results filters (same filter semantics as get_publish_students,
	just without pagination) using the chosen Email Template."""
	_check_access()
	if not exam_plan:
		frappe.throw("Select an Exam Plan first.")
	if not email_template or not frappe.db.exists("Email Template", email_template):
		frappe.throw("Select a valid Email Template.")

	params, extra_cond = _build_publish_where(
		exam_plan, search, status_filter, inst_programmes, inst_batches, course, programme
	)

	students = frappe.db.sql(
		f"""
		SELECT
			sm.name                                                              AS student,
			sm.registration_id,
			TRIM(CONCAT_WS(' ', sm.first_name,
				COALESCE(NULLIF(sm.middle_name,''), NULL),
				sm.last_name))                                                   AS student_name,
			sm.programme_of_study                                                AS programme,
			sm.email
		FROM `tabStudent Course Marks` scm
		INNER JOIN `tabStudent Master` sm ON sm.name = scm.student
		LEFT JOIN `tabStudent Result Publish` srp
			ON srp.exam_plan = %(exam_plan)s AND srp.student = sm.name
		WHERE scm.exam_plan = %(exam_plan)s
		{extra_cond}
		GROUP BY scm.student
		""",
		params,
		as_dict=True,
	)

	recipients = [s for s in students if s.get("email")]
	skipped_no_email = len(students) - len(recipients)

	if not recipients:
		frappe.throw("None of the matching students have an email address on file.")

	exam_name = frappe.db.get_value("Exam Plan", exam_plan, "exam_name") or exam_plan

	frappe.enqueue(
		"slcm.slcm.page.publish_result.publish_result._bulk_send_publish_email_job",
		queue="long",
		timeout=1800,
		students=recipients,
		template_name=email_template,
		exam_plan=exam_plan,
		exam_name=exam_name,
	)

	msg = f"{len(recipients)} email(s) queued. Emails will be delivered shortly."
	if skipped_no_email:
		msg += f" ({skipped_no_email} student(s) skipped — no email on file.)"

	return {"queued": len(recipients), "skipped_no_email": skipped_no_email, "message": msg}


def _bulk_send_publish_email_job(students, template_name, exam_plan, exam_name):
	"""Background job: render the chosen Email Template per student and send.
	Runs outside the HTTP request — mirrors fee_reminder_tool's _bulk_send_job."""
	email_template = frappe.get_doc("Email Template", template_name)

	sent = skipped = 0
	for s in students:
		try:
			args = {
				"doc":             frappe.get_doc("Student Master", s["student"]),
				"student_name":    s.get("student_name"),
				"registration_id": s.get("registration_id"),
				"programme":       s.get("programme"),
				"exam_plan":       exam_plan,
				"exam_name":       exam_name,
			}
			subject = frappe.render_template(email_template.subject, args)
			if email_template.use_html:
				message = frappe.render_template(email_template.response_html, args)
			else:
				message = frappe.render_template(email_template.response, args)

			frappe.sendmail(
				recipients=[s["email"]],
				subject=subject,
				message=message,
				reference_doctype="Student Master",
				reference_name=s["student"],
			)
			sent += 1
		except Exception as e:
			frappe.logger().warning(f"[publish_result] Bulk email failed for {s.get('student')}: {e}")
			skipped += 1

	frappe.db.commit()
	frappe.logger().info(f"[publish_result] Bulk publish email done — sent: {sent}, skipped: {skipped}")
