# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe


# ── Settings helper ────────────────────────────────────────────────────────────

def _get_settings():
	"""Return Examination Settings as a dict with safe defaults."""
	try:
		s = frappe.get_single("Examination Settings")
		return {
			"require_both_schemas":      int(s.require_both_schemas or 0),
			"allow_partial_mapping":     int(s.allow_partial_mapping if s.allow_partial_mapping is not None else 1),
			"default_evaluation_schema": s.default_evaluation_schema or "",
			"default_grade_schema":      s.default_grade_schema or "",
			"schema_lock_date":          str(s.schema_lock_date) if s.schema_lock_date else "",
			"lock_override_role":        s.lock_override_role or "",
			"require_change_reason":     int(s.require_change_reason or 0),
			"notify_on_schema_change":   int(s.notify_on_schema_change or 0),
			"notify_on_unmap":           int(s.notify_on_unmap or 0),
			"notification_recipients":   s.notification_recipients or "",
			"enable_change_log":         int(s.enable_change_log if s.enable_change_log is not None else 1),
			"log_retention_months":      int(s.log_retention_months or 12),
			"default_reexam_enrollment": s.default_reexam_enrollment or "Auto",
			"reexam_max_marks_cap":      float(s.reexam_max_marks_cap or 0),
			"courses_per_page":          int(s.courses_per_page or 500),
			"show_unmapped_courses":     int(s.show_unmapped_courses if s.show_unmapped_courses is not None else 1),
		}
	except Exception:
		return {
			"require_both_schemas": 0, "allow_partial_mapping": 1,
			"default_evaluation_schema": "", "default_grade_schema": "",
			"schema_lock_date": "", "lock_override_role": "",
			"require_change_reason": 0,
			"notify_on_schema_change": 0, "notify_on_unmap": 0,
			"notification_recipients": "",
			"enable_change_log": 1, "log_retention_months": 12,
			"default_reexam_enrollment": "Auto", "reexam_max_marks_cap": 0,
			"courses_per_page": 500, "show_unmapped_courses": 1,
		}


def _check_lock(settings):
	"""Throw if schemas are locked for current user."""
	lock_date = settings.get("schema_lock_date")
	if not lock_date:
		return
	today = frappe.utils.getdate(frappe.utils.today())
	if today >= frappe.utils.getdate(lock_date):
		override_role = settings.get("lock_override_role")
		if override_role and frappe.db.exists("Has Role", {
			"parent": frappe.session.user, "role": override_role
		}):
			return
		frappe.throw(
			f"Schemas are locked as of {lock_date}. No changes are allowed.",
			title="Schema Locked"
		)


def _sync_course_schedules(exam_plan, courses):
	"""Add courses to Exam Plan course_schedules if not already listed."""
	if not courses:
		return
	try:
		plan_doc = frappe.get_doc("Exam Plan", exam_plan)
		existing = {row.course for row in plan_doc.course_schedules}
		changed = False
		for course in courses:
			if course not in existing:
				plan_doc.append("course_schedules", {"course": course})
				existing.add(course)
				changed = True
		if changed:
			plan_doc.save(ignore_permissions=True)
	except Exception as e:
		# The schemas are already saved; say why the schedule rows were not added
		frappe.log_error(frappe.get_traceback(), f"Exam Plan {exam_plan}: course schedule sync failed")
		frappe.msgprint(
			f"Schemas were saved, but the courses could not be added to the exam schedule: {e}",
			title="Exam schedule not updated",
			indicator="orange",
		)


def _send_notification(settings, subject, message):
	"""Send email notification to configured recipients."""
	recipients_raw = settings.get("notification_recipients", "")
	recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
	if not recipients:
		return
	try:
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=message,
			now=True,
		)
	except Exception:
		pass  # Never block the main operation due to notification failure


# ── Public API ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_exam_settings():
	return _get_settings()


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
def create_exam_plan(exam_name, term):
	if frappe.db.exists("Exam Plan", exam_name):
		frappe.throw(f"Exam Plan '{exam_name}' already exists.")
	doc = frappe.new_doc("Exam Plan")
	doc.exam_name = exam_name
	doc.term = term
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"name": doc.name, "exam_name": doc.exam_name, "term": doc.term, "status": doc.status}


@frappe.whitelist()
def get_components(search=None):
	filters = {}
	if search:
		filters["component_name"] = ["like", f"%{search}%"]
	return frappe.get_all(
		"Exam Component",
		filters=filters,
		fields=["name", "component_name", "component_type", "is_active"],
		order_by="creation desc",
	)


@frappe.whitelist()
def save_component(component_name, component_type, name=None):
	if name and frappe.db.exists("Exam Component", name):
		doc = frappe.get_doc("Exam Component", name)
		doc.component_name = component_name
		doc.component_type = component_type
		doc.save(ignore_permissions=True)
	else:
		if frappe.db.exists("Exam Component", component_name):
			frappe.throw(f"Component '{component_name}' already exists.")
		doc = frappe.new_doc("Exam Component")
		doc.component_name = component_name
		doc.component_type = component_type
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {
		"name": doc.name,
		"component_name": doc.component_name,
		"component_type": doc.component_type,
		"is_active": doc.is_active,
	}


@frappe.whitelist()
def get_assessment_types(search=None):
	filters = {}
	if search:
		filters["type_name"] = ["like", f"%{search}%"]
	return frappe.get_all(
		"Exam Assessment Type",
		filters=filters,
		fields=["name", "type_name", "assessment_type", "is_active"],
		order_by="creation desc",
	)


@frappe.whitelist()
def save_assessment_type(type_name, assessment_type, name=None):
	if name and frappe.db.exists("Exam Assessment Type", name):
		doc = frappe.get_doc("Exam Assessment Type", name)
		doc.type_name = type_name
		doc.assessment_type = assessment_type
		doc.save(ignore_permissions=True)
	else:
		if frappe.db.exists("Exam Assessment Type", type_name):
			frappe.throw(f"Assessment Type '{type_name}' already exists.")
		doc = frappe.new_doc("Exam Assessment Type")
		doc.type_name = type_name
		doc.assessment_type = assessment_type
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {
		"name": doc.name,
		"type_name": doc.type_name,
		"assessment_type": doc.assessment_type,
		"is_active": doc.is_active,
	}


@frappe.whitelist()
def get_schemas(search=None):
	filters = {}
	if search:
		filters["schema_name"] = ["like", f"%{search}%"]
	schemas = frappe.get_all(
		"Evaluation Schema",
		filters=filters,
		fields=["name", "schema_name", "description", "total_marks", "passing_marks"],
		order_by="creation desc",
	)
	for schema in schemas:
		schema["assigned_courses"] = frappe.db.count(
			"Course Schema Assignment", {"evaluation_schema": schema["name"]}
		) if frappe.db.table_exists("tabCourse Schema Assignment") else 0
	return schemas


@frappe.whitelist()
def get_schema_detail(name):
	if not frappe.db.exists("Evaluation Schema", name):
		frappe.throw(f"Schema '{name}' not found.")
	doc = frappe.get_doc("Evaluation Schema", name)
	components = []
	for c in doc.schema_components:
		comp_type = frappe.db.get_value("Exam Component", c.component, "component_type") or "Custom"
		components.append({
			"name": c.name,
			"component": c.component,
			"component_type": comp_type,
			"label": c.label,
			"effective_max_marks": c.effective_max_marks,
			"weightage": c.weightage,
			"passing_marks": c.passing_marks,
			"consider_for_pass_fail": c.consider_for_pass_fail,
		})
	assessment_configs = []
	for a in doc.assessment_configs:
		at_type = frappe.db.get_value("Exam Assessment Type", a.assessment_type, "assessment_type") or "Assessment"
		assessment_configs.append({
			"name": a.name,
			"component": a.component,
			"assessment_type": a.assessment_type,
			"assessment_type_category": at_type,
			"label": a.label,
			"effective_marks": a.effective_marks,
			"maximum_marks": a.maximum_marks,
			"minimum_marks": a.minimum_marks,
			"passing_marks": a.passing_marks,
			"consider_for_pass_fail": a.consider_for_pass_fail,
			"weightage": a.weightage,
			"enrollment": a.enrollment,
		})
	reexam_configs = []
	for r in doc.reexam_configs:
		reexam_configs.append({
			"name": r.name,
			"component": r.component,
			"re_exam_type_category": r.re_exam_type_category,
			"assessment_type": r.assessment_type,
			"label": r.label,
			"maximum_marks": r.maximum_marks,
			"minimum_marks": r.minimum_marks,
			"passing_marks": r.passing_marks,
			"enrollment": r.enrollment,
			"substitute_for": r.substitute_for,
			"substitute_weightage": r.substitute_weightage,
			"effective_marks": r.effective_marks,
		})
	return {
		"name": doc.name,
		"schema_name": doc.schema_name,
		"description": doc.description,
		"total_marks": doc.total_marks,
		"passing_marks": doc.passing_marks,
		"reexam_result": doc.reexam_result,
		"schema_components": components,
		"assessment_configs": assessment_configs,
		"reexam_configs": reexam_configs,
	}


@frappe.whitelist()
def save_schema(data):
	import json
	if isinstance(data, str):
		data = json.loads(data)

	name = data.get("name")
	schema_name = data.get("schema_name")

	if name and frappe.db.exists("Evaluation Schema", name):
		doc = frappe.get_doc("Evaluation Schema", name)
	else:
		if frappe.db.exists("Evaluation Schema", schema_name):
			frappe.throw(f"Schema '{schema_name}' already exists.")
		doc = frappe.new_doc("Evaluation Schema")
		doc.schema_name = schema_name

	doc.description = data.get("description", "")
	doc.total_marks = data.get("total_marks", 100)
	doc.passing_marks = data.get("passing_marks", 0)

	doc.set("schema_components", [])
	for c in data.get("schema_components", []):
		doc.append("schema_components", {
			"component": c.get("component"),
			"label": c.get("label", ""),
			"effective_max_marks": c.get("effective_max_marks", 0),
			"weightage": c.get("weightage", 100),
			"passing_marks": c.get("passing_marks", 0),
			"consider_for_pass_fail": c.get("consider_for_pass_fail", 0),
		})

	doc.set("assessment_configs", [])
	for a in data.get("assessment_configs", []):
		doc.append("assessment_configs", {
			"component": a.get("component"),
			"assessment_type": a.get("assessment_type"),
			"label": a.get("label", ""),
			"effective_marks": a.get("effective_marks", 0),
			"maximum_marks": a.get("maximum_marks", 0),
			"minimum_marks": a.get("minimum_marks", 0),
			"passing_marks": a.get("passing_marks", 0),
			"consider_for_pass_fail": a.get("consider_for_pass_fail", 0),
			"weightage": a.get("weightage", 100),
			"enrollment": a.get("enrollment", "Auto"),
		})

	doc.set("reexam_configs", [])
	for r in data.get("reexam_configs", []):
		doc.append("reexam_configs", {
			"component": r.get("component"),
			"re_exam_type_category": r.get("re_exam_type_category", "Assessment"),
			"assessment_type": r.get("assessment_type"),
			"label": r.get("label", ""),
			"maximum_marks": r.get("maximum_marks", 0),
			"minimum_marks": r.get("minimum_marks", 0),
			"passing_marks": r.get("passing_marks", 0),
			"enrollment": r.get("enrollment", "Manual"),
			"substitute_for": r.get("substitute_for"),
			"substitute_weightage": r.get("substitute_weightage", 100),
			"effective_marks": r.get("effective_marks", 0),
		})
	if data.get("reexam_result"):
		doc.reexam_result = data["reexam_result"]

	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"name": doc.name, "schema_name": doc.schema_name}


@frappe.whitelist()
def get_terms():
	return frappe.get_all(
		"Academic Term",
		fields=["name", "term_name"],
		order_by="creation desc",
	)


@frappe.whitelist()
def get_courses_for_plan(exam_plan, search=""):
	"""Return the courses taught in the given exam plan's term (one row per
	course, across all its Classes/sections) with their schema assignments.

	`name` of each row is the Course; `programme` lists the programmes of the
	Classes teaching it in the term.
	"""
	settings = _get_settings()
	page_length = settings.get("courses_per_page") or 500

	term_name = frappe.db.get_value("Exam Plan", exam_plan, "term")
	if not term_name:
		return []

	params = {"term_name": term_name, "limit": page_length}
	search_cond = ""
	if search:
		search_cond = " AND (c.course_name LIKE %(s)s OR c.course_code LIKE %(s)s)"
		params["s"] = f"%{search}%"

	rows = frappe.db.sql(
		f"""
		SELECT
			cl.course        AS name,
			cl.course        AS course,
			GROUP_CONCAT(DISTINCT cl.programme ORDER BY cl.programme SEPARATOR ', ') AS programme,
			c.course_name    AS course_name,
			c.course_code    AS course_code,
			c.credit_value   AS credit_value
		FROM `tabClasses` cl
		LEFT JOIN `tabCourse` c ON c.name = cl.course
		WHERE cl.academic_term = %(term_name)s
		{search_cond}
		GROUP BY cl.course, c.course_name, c.course_code, c.credit_value
		ORDER BY c.course_name ASC
		LIMIT %(limit)s
		""",
		params,
		as_dict=True,
	)

	# Fetch existing assignments, keyed by course (one mapping per course per plan)
	asgn_map = {}
	try:
		assignments = frappe.db.sql(
			"""
			SELECT name, course, evaluation_schema, grade_schema
			FROM `tabCourse Schema Assignment`
			WHERE exam_plan = %(exam_plan)s
			""",
			{"exam_plan": exam_plan},
			as_dict=True,
		)
		asgn_map = {a["course"]: a for a in assignments}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_courses_for_plan: assignment fetch failed")

	# Enrolled student counts per course = Enrolled students of its Classes in the term
	enrolled_map = {}
	try:
		enrollment_counts = frappe.db.sql(
			"""
			SELECT cl.course AS course, COUNT(DISTINCT ces.student_enrollment) AS enrolled_count
			FROM `tabClasses` cl
			JOIN `tabClass Enrolled Student` ces
				ON ces.parent = cl.name AND ces.parenttype = 'Classes'
			WHERE cl.academic_term = %(term_name)s
			  AND ces.status = 'Enrolled'
			GROUP BY cl.course
			""",
			{"term_name": term_name},
			as_dict=True,
		)
		enrolled_map = {row["course"]: row["enrolled_count"] for row in enrollment_counts}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_courses_for_plan: enrollment count fetch failed")

	for o in rows:
		asgn = asgn_map.get(o["name"], {})
		o["evaluation_schema"] = asgn.get("evaluation_schema") or ""
		o["grade_schema"] = asgn.get("grade_schema") or ""
		o["assignment_name"] = asgn.get("name", "")
		o["enrolled_students"] = enrolled_map.get(o["name"], 0)
		if asgn.get("evaluation_schema"):
			o["max_marks"] = (
				frappe.db.get_value("Evaluation Schema", asgn["evaluation_schema"], "total_marks") or ""
			)
		else:
			o["max_marks"] = ""

	return rows


@frappe.whitelist()
def save_course_schema(exam_plan, assignments, reason=None):
	"""Create or update Course Schema Assignment records."""
	import json

	settings = _get_settings()

	# ── Lock check ──────────────────────────────────────────────────────────
	_check_lock(settings)

	# ── Require change reason ───────────────────────────────────────────────
	if settings.get("require_change_reason") and not reason:
		frappe.throw(
			"A change reason is required. Please enter a justification for the schema change.",
			title="Change Reason Required"
		)

	_SKIP = "__SKIP__"
	if isinstance(assignments, str):
		assignments = json.loads(assignments)

	changed_courses = []
	mapped_courses = []
	academic_term = frappe.db.get_value("Exam Plan", exam_plan, "term")

	for asgn in assignments:
		course = asgn.get("course")
		if not course:
			continue

		eval_schema  = asgn.get("evaluation_schema", _SKIP)
		grade_schema = asgn.get("grade_schema",      _SKIP)

		rows = frappe.db.sql(
			"SELECT name FROM `tabCourse Schema Assignment` WHERE exam_plan=%s AND course=%s LIMIT 1",
			(exam_plan, course),
		)
		existing = rows[0][0] if rows else None

		if existing:
			update = {}
			if eval_schema  != _SKIP: update["evaluation_schema"] = eval_schema  or None
			if grade_schema != _SKIP: update["grade_schema"]      = grade_schema or None

			if update:
				cur_row = frappe.db.sql(
					"SELECT evaluation_schema, grade_schema FROM `tabCourse Schema Assignment` WHERE name=%s",
					(existing,), as_dict=True
				)
				cur = cur_row[0] if cur_row else frappe._dict()
				old_ev = cur.get("evaluation_schema")
				old_gr = cur.get("grade_schema")
				new_ev = update.get("evaluation_schema", old_ev)
				new_gr = update.get("grade_schema", old_gr)

				# ── Require both schemas check ──────────────────────────────
				if settings.get("require_both_schemas") and (not new_ev or not new_gr):
					frappe.throw(
						f"Both Evaluation Schema and Grade Schema are required for course '{course}'.",
						title="Both Schemas Required"
					)

				if not new_ev and not new_gr:
					frappe.delete_doc("Course Schema Assignment", existing, ignore_permissions=True)
				else:
					mapped_courses.append(course)
					frappe.db.sql(
						"""UPDATE `tabCourse Schema Assignment`
						   SET evaluation_schema=%s, grade_schema=%s, modified=NOW(), modified_by=%s
						   WHERE name=%s""",
						(new_ev, new_gr, frappe.session.user, existing)
					)
					if (old_ev != new_ev or old_gr != new_gr) and settings.get("enable_change_log"):
						try:
							log = frappe.new_doc("Schema Change Log")
							log.exam_plan = exam_plan
							log.course = course
							log.old_evaluation_schema = old_ev or ""
							log.new_evaluation_schema = new_ev or ""
							log.old_grade_schema = old_gr or ""
							log.new_grade_schema = new_gr or ""
							log.changed_by = frappe.session.user
							log.changed_on = frappe.utils.now()
							log.reason = reason or ""
							log.insert(ignore_permissions=True)
							changed_courses.append(course)
						except Exception:
							pass
		else:
			ev = eval_schema  if eval_schema  != _SKIP else None
			gr = grade_schema if grade_schema != _SKIP else None

			# ── Require both schemas check (new record) ─────────────────────
			if settings.get("require_both_schemas") and not (ev and gr):
				frappe.throw(
					f"Both Evaluation Schema and Grade Schema are required for course '{course}'.",
					title="Both Schemas Required"
				)

			if ev or gr:
				doc = frappe.new_doc("Course Schema Assignment")
				doc.exam_plan         = exam_plan
				doc.course            = course
				doc.academic_term     = academic_term
				doc.evaluation_schema = ev
				doc.grade_schema      = gr
				doc.insert(ignore_permissions=True)
				changed_courses.append(course)
				mapped_courses.append(course)

	_sync_course_schedules(exam_plan, mapped_courses)
	frappe.db.commit()

	# ── Notification ────────────────────────────────────────────────────────
	if changed_courses and settings.get("notify_on_schema_change"):
		course_list = ", ".join(changed_courses)
		_send_notification(
			settings,
			subject=f"Schema Mapped: {exam_plan}",
			message=(
				f"Schema was mapped/updated for the following course(s) in "
				f"<b>{exam_plan}</b>:<br><br>{course_list}"
				+ (f"<br><br><b>Reason:</b> {reason}" if reason else "")
				+ f"<br><br><b>Changed by:</b> {frappe.session.user}"
			),
		)

	return True


@frappe.whitelist()
def unmap_course_schema(exam_plan, courses):
	"""Delete Course Schema Assignment records for the given courses."""
	import json

	settings = _get_settings()
	_check_lock(settings)

	if isinstance(courses, str):
		courses = json.loads(courses)

	selected = courses
	courses = []
	for course in selected:
		rows = frappe.db.sql(
			"SELECT name, course FROM `tabCourse Schema Assignment` WHERE exam_plan=%s AND course=%s",
			(exam_plan, course),
			as_dict=True,
		)
		for row in rows:
			courses.append(row["course"])
			frappe.delete_doc("Course Schema Assignment", row["name"], ignore_permissions=True)

	frappe.db.commit()

	# ── Notification ────────────────────────────────────────────────────────
	if settings.get("notify_on_unmap"):
		course_list = ", ".join(courses)
		_send_notification(
			settings,
			subject=f"Schema Unmapped: {exam_plan}",
			message=(
				f"Schema was unmapped for the following course(s) in "
				f"<b>{exam_plan}</b>:<br><br>{course_list}"
				f"<br><br><b>Unmapped by:</b> {frappe.session.user}"
			),
		)

	return True


@frappe.whitelist()
def sync_course_schedule_from_assignments(exam_plan):
	"""Backfill course_schedules from all existing Course Schema Assignments for this exam plan."""
	assignments = frappe.db.sql(
		"SELECT DISTINCT course FROM `tabCourse Schema Assignment` WHERE exam_plan=%s",
		(exam_plan,),
		as_dict=True,
	)
	courses = [row["course"] for row in assignments if row.get("course")]
	_sync_course_schedules(exam_plan, courses)
	frappe.db.commit()
	return len(courses)


@frappe.whitelist()
def purge_old_change_logs():
	"""Delete Schema Change Log entries older than the configured retention period."""
	settings = _get_settings()
	months = settings.get("log_retention_months") or 12
	cutoff = frappe.utils.add_months(frappe.utils.now_datetime(), -months)
	old_logs = frappe.db.sql(
		"SELECT name FROM `tabSchema Change Log` WHERE creation < %s",
		(cutoff,),
	)
	for (name,) in old_logs:
		frappe.delete_doc("Schema Change Log", name, ignore_permissions=True)
	frappe.db.commit()
	return len(old_logs)
