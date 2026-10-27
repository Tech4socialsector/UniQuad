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


def _sync_course_schedules(exam_plan, course_offerings):
	"""Add course offerings to Exam Plan course_schedules if not already listed."""
	if not course_offerings:
		return
	try:
		plan_doc = frappe.get_doc("Exam Plan", exam_plan)
		existing = {row.course_offering for row in plan_doc.course_schedules}
		changed = False
		for offering in course_offerings:
			if offering not in existing:
				plan_doc.append("course_schedules", {"course_offering": offering})
				existing.add(offering)
				changed = True
		if changed:
			plan_doc.save(ignore_permissions=True)
	except Exception:
		pass


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
	"""Return course offerings (one row per course+programme) with their schema
	assignments for the given exam plan's term.

	A course can have multiple offerings in the same term (one per programme) -
	each offering is its own row here so different programmes can carry their
	own schema mapping even when they share the same underlying Course.
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

	offerings = frappe.db.sql(
		f"""
		SELECT
			co.name          AS name,
			co.course_title  AS course,
			co.program       AS programme,
			c.course_name    AS course_name,
			c.course_code    AS course_code,
			c.credit_value   AS credit_value
		FROM `tabCourse Offering` co
		LEFT JOIN `tabCourse` c ON c.name = co.course_title
		WHERE co.term_name = %(term_name)s
		{search_cond}
		ORDER BY c.course_name ASC, co.program ASC
		LIMIT %(limit)s
		""",
		params,
		as_dict=True,
	)

	# Fetch existing assignments, keyed by course_offering (the correct grain -
	# two offerings of the same course, for different programmes, must be able
	# to carry independent schema mappings).
	asgn_map = {}
	try:
		assignments = frappe.db.sql(
			"""
			SELECT name, course_offering, evaluation_schema, grade_schema
			FROM `tabCourse Schema Assignment`
			WHERE exam_plan = %(exam_plan)s
			""",
			{"exam_plan": exam_plan},
			as_dict=True,
		)
		asgn_map = {a["course_offering"]: a for a in assignments}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_courses_for_plan: assignment fetch failed")

	# Fetch enrolled student counts per course offering
	enrolled_map = {}
	try:
		enrollment_counts = frappe.db.sql(
			"""
			SELECT co.name AS course_offering, COUNT(DISTINCT se.name) AS enrolled_count
			FROM `tabStudent Enrollment` se
			JOIN `tabStudent Enrollment Course` sec ON sec.parent = se.name
			JOIN `tabCourse Offering` co ON co.name = sec.course_offering
			WHERE co.term_name = %(term_name)s
			  AND sec.status = 'Enrolled'
			GROUP BY co.name
			""",
			{"term_name": term_name},
			as_dict=True,
		)
		enrolled_map = {row["course_offering"]: row["enrolled_count"] for row in enrollment_counts}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_courses_for_plan: enrollment count fetch failed")

	for o in offerings:
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

	return offerings


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
	mapped_offerings = []

	for asgn in assignments:
		course_offering = asgn.get("course_offering")
		course = asgn.get("course")
		if not course_offering:
			continue
		if not course:
			course = frappe.db.get_value("Course Offering", course_offering, "course_title")

		eval_schema  = asgn.get("evaluation_schema", _SKIP)
		grade_schema = asgn.get("grade_schema",      _SKIP)

		rows = frappe.db.sql(
			"SELECT name FROM `tabCourse Schema Assignment` WHERE exam_plan=%s AND course_offering=%s LIMIT 1",
			(exam_plan, course_offering),
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
					mapped_offerings.append(course_offering)
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
				doc.course_offering    = course_offering
				doc.evaluation_schema = ev
				doc.grade_schema      = gr
				doc.insert(ignore_permissions=True)
				changed_courses.append(course)
				mapped_offerings.append(course_offering)

	_sync_course_schedules(exam_plan, mapped_offerings)
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
def unmap_course_schema(exam_plan, course_offerings):
	"""Delete Course Schema Assignment records for the given course offerings."""
	import json

	settings = _get_settings()
	_check_lock(settings)

	if isinstance(course_offerings, str):
		course_offerings = json.loads(course_offerings)

	courses = []
	for course_offering in course_offerings:
		rows = frappe.db.sql(
			"SELECT name, course FROM `tabCourse Schema Assignment` WHERE exam_plan=%s AND course_offering=%s",
			(exam_plan, course_offering),
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
		"SELECT DISTINCT course_offering FROM `tabCourse Schema Assignment` WHERE exam_plan=%s",
		(exam_plan,),
		as_dict=True,
	)
	offerings = [row["course_offering"] for row in assignments if row.get("course_offering")]
	_sync_course_schedules(exam_plan, offerings)
	frappe.db.commit()
	return len(offerings)


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
