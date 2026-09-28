# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, cint

from slcm.slcm.page.promotion_management.promotion_management import (
	_evaluate_student,
	_get_students_raw,
	_sync_student_master_batch,
)

BATCH_SIZE = 25
ALLOWED_ROLES = ("System Manager", "slcm_Academic Incharge")


def _resolve_target_batch(current_batch, target_academic_year, target_term=None):
	"""Resolve the Batch to promote into, honoring the target academic year
	the user picked on the Promotion Run (unlike the generic
	promotion_management._resolve_next_batch, which always auto-picks the
	chronologically-next Academic Year).

	target_term is intentionally NOT used to filter here: Batch.academic_term
	is fetched from Programme.academic_term, a single fixed Link the Programme
	carries — it is the same value on every Batch under that Programme
	regardless of term_year, not a per-batch "which term is this" marker.
	Matching against it would silently fail to find real target Batches
	whenever the Target Term differs from that Programme-wide constant.
	Programme + Section + (term_year + 1) + Academic Year is what actually
	identifies the next Batch."""
	batch = frappe.db.get_value(
		"Batch", current_batch, ["program", "section", "term_year"], as_dict=True
	)
	if not batch or not batch.section or batch.term_year is None:
		return None

	filters = {
		"program": batch.program,
		"section": batch.section,
		"term_year": cint(batch.term_year) + 1,
		"academic_year": target_academic_year,
	}

	return frappe.db.get_value("Batch", filters, "name")


def _move_enrollment(enrollment_name, student, next_batch):
	"""Complete the current enrollment and create the one in `next_batch`,
	atomically. Completing the old enrollment flips Student Master to
	"Graduated" until the new Enrolled one resets it to "Active", so a failed
	insert must roll back the whole move rather than strand the student."""
	save_point = "pr_move_" + frappe.generate_hash(length=10)
	frappe.db.savepoint(save_point)
	try:
		old_doc = frappe.get_doc("Student Enrollment", enrollment_name)
		old_doc.status = "Completed"
		old_doc.save(ignore_permissions=True)

		new_doc = _new_enrollment_for_batch(student, next_batch)
		new_doc.insert(ignore_permissions=True)

		# Keep Student Master pointing at the student's current Batch/term.
		_sync_student_master_batch(student, next_batch)
	except Exception:
		frappe.db.rollback(save_point=save_point)
		raise
	frappe.db.release_savepoint(save_point)
	return new_doc.name


def _new_enrollment_for_batch(student, batch):
	"""Build a new Student Enrollment for `batch`, with enrollment_date set to
	the Batch's own term start — not today's date — so a promoted student's
	record reflects when their new term actually begins rather than the day
	the promotion job happened to run."""
	doc = frappe.new_doc("Student Enrollment")
	doc.student = student
	doc.batch = batch
	doc.status = "Enrolled"
	doc.enrollment_date = frappe.db.get_value("Batch", batch, "start_date") or frappe.utils.today()
	return doc


class PromotionRun(Document):
	pass


def _check_permission():
	if not (set(ALLOWED_ROLES) & set(frappe.get_roles())):
		frappe.throw(
			frappe._("You are not permitted to run student promotions."),
			frappe.PermissionError,
		)


def _has_fee_due(student):
	return bool(
		frappe.db.exists(
			"Fee Demand",
			{"student": student, "status": ["in", ["Pending", "Partially Paid", "Overdue"]]},
		)
	)


def _reason_for_skip(evaluation, student):
	"""Map a failed evaluation to a structured reason_code + human detail."""
	checks = [
		("attendance_result", "Attendance Shortage", "attendance_percent"),
		("backlog_result", "Backlog", "backlog_count"),
		("cgpa_result", "CGPA Shortfall", "current_cgpa"),
		("shortage_course_result", "Attendance Shortage", "shortage_course_count"),
		("cf_result", "Backlog", "cf_fa_shortage_count"),
	]
	for result_key, reason_code, _val_key in checks:
		if evaluation.get(result_key) == "Fail":
			return reason_code, f"{result_key.replace('_', ' ').title()} did not meet policy criteria."
	return "Other", "Did not meet promotion policy criteria."


@frappe.whitelist()
def get_target_term_courses(student_list, target_academic_year, target_term=None):
	"""Read-only preview of the Course Offerings the selected students would
	actually be attached to on promotion — i.e. the exact same
	{cohort: <target Batch>, status: Active} rows that
	Student Enrollment.fetch_program_and_courses() attaches when the new
	enrollment is created. Purely informational: a Batch with no matching
	Course Offerings yet never blocks promotion."""
	_check_permission()

	if isinstance(student_list, str):
		import json
		student_list = json.loads(student_list) if student_list else None

	if not student_list or not target_academic_year:
		return {"courses": [], "target_batches": []}

	current_batches = list({
		b for b in (
			frappe.db.get_value("Student Enrollment", name, "batch") for name in student_list
		) if b
	})

	target_batches = sorted({
		b for b in (
			_resolve_target_batch(cb, target_academic_year, target_term) for cb in current_batches
		) if b
	})

	if not target_batches:
		return {"courses": [], "target_batches": []}

	offerings = frappe.get_all(
		"Course Offering",
		filters={"cohort": ["in", target_batches], "status": "Active"},
		fields=["name", "course_title", "course_name", "credit_value", "cohort"],
		order_by="cohort asc, course_name asc",
	)
	courses = [
		{
			"course": o.course_title,
			"course_name": o.course_name,
			"credits": o.credit_value,
			"batch": o.cohort,
		}
		for o in offerings
	]
	return {"courses": courses, "target_batches": target_batches}


@frappe.whitelist()
def create_and_queue(student_list, target_academic_year, target_term):
	"""Create a Promotion Run in Queued state and enqueue the background job,
	restricted to exactly the Student Enrollment names the user checked in the
	list view. Programme / Source Academic Year / Batch / Section are derived
	from that selection rather than re-asked in the dialog.

	Runs started from Student Enrollment are term-to-term moves and always
	auto-promote every selected student — no Promotion Policy is applied.
	Policy-checked promotion is year-to-year only (Promotion Management page)."""
	_check_permission()

	if isinstance(student_list, str):
		import json
		student_list = json.loads(student_list) if student_list else None

	if not student_list:
		frappe.throw(frappe._("Select at least one Student Enrollment to promote."))
	if not target_academic_year or not target_term:
		frappe.throw(frappe._("Target Academic Year and Target Term are required."))

	enrollments = frappe.db.get_all(
		"Student Enrollment",
		filters={"name": ["in", student_list]},
		fields=["name", "student", "student_name", "batch", "program", "academic_year", "section"],
	)
	if not enrollments:
		frappe.throw(frappe._("None of the selected records could be found."))

	programs = {e.program for e in enrollments if e.program}
	if len(programs) > 1:
		frappe.throw(frappe._(
			"Selected students belong to multiple Programmes ({0}). Please filter your "
			"selection to one Programme at a time before promoting."
		).format(", ".join(sorted(programs))))

	program = programs.pop() if programs else None
	source_academic_years = {e.academic_year for e in enrollments if e.academic_year}
	source_academic_year = source_academic_years.pop() if len(source_academic_years) == 1 else None
	sections = {e.section for e in enrollments if e.section}
	section = sections.pop() if len(sections) == 1 else None

	doc = frappe.new_doc("Promotion Run")
	doc.program = program
	doc.source_academic_year = source_academic_year
	doc.target_academic_year = target_academic_year
	doc.target_term = target_term
	doc.section = section
	doc.promotion_policy = None
	doc.status = "Queued"
	doc.run_by = frappe.session.user
	doc.run_on = now_datetime()
	doc.total_students = len(enrollments)
	doc.selected_enrollments = frappe.as_json([e.name for e in enrollments])
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	frappe.enqueue(
		method="slcm.slcm.doctype.promotion_run.promotion_run.process_promotion_run",
		queue="short",
		timeout=1200,
		promotion_run_name=doc.name,
	)

	return doc.name


def process_promotion_run(promotion_run_name):
	doc = frappe.get_doc("Promotion Run", promotion_run_name)

	if doc.status == "Queued":
		doc.db_set("status", "In Progress")
		frappe.db.commit()

	try:
		if not doc.selected_enrollments:
			frappe.throw(frappe._("This Promotion Run has no selected students recorded."))

		import json
		selected = json.loads(doc.selected_enrollments)
		enrollments = frappe.db.get_all(
			"Student Enrollment",
			filters={"name": ["in", selected]},
			fields=["name", "student", "student_name", "batch"],
		)

		doc.db_set("total_students", len(enrollments))
		frappe.db.commit()

		policy_dict = {}
		if doc.promotion_policy:
			policy_dict = frappe.get_doc("Promotion Policy", doc.promotion_policy).as_dict()

		# from_year for the eligibility query: pulled per-student from their own Batch,
		# since a single run can now span students across different Batches.
		student_eval_map = {}
		if enrollments and policy_dict:
			batch_names = list({e.batch for e in enrollments if e.batch})
			from_years = {
				b.name: cint(b.term_year)
				for b in frappe.db.get_all("Batch", filters={"name": ["in", batch_names]}, fields=["name", "term_year"])
			} if batch_names else {}
			for from_year in set(from_years.values()):
				if from_year is None:
					continue
				for row in _get_students_raw(doc.program, doc.source_academic_year, from_year):
					student_eval_map[row["student"]] = row

		already_done = {row.student for row in doc.log}
		pending = [e for e in enrollments if e.student not in already_done]
		batch = pending[:BATCH_SIZE]

		for enrollment in batch:
			_process_one_student(doc, enrollment, policy_dict, student_eval_map)
			frappe.db.set_value(
				"Promotion Run", doc.name, "last_heartbeat", now_datetime(), update_modified=False
			)
			frappe.db.commit()

		doc.reload()
		processed = len(doc.log)

		if processed < len(enrollments):
			frappe.enqueue(
				method="slcm.slcm.doctype.promotion_run.promotion_run.process_promotion_run",
				queue="short",
				timeout=1200,
				promotion_run_name=doc.name,
			)
		else:
			_finalize(doc)

	except Exception:
		frappe.log_error(
			title=f"Promotion Run {promotion_run_name} failed",
			message=frappe.get_traceback(),
		)
		doc.db_set("status", "Error")
		doc.db_set("error_log", frappe.get_traceback())
		frappe.db.commit()
		frappe.publish_realtime(
			"promotion_run_complete",
			{"promotion_run": promotion_run_name, "status": "Error"},
			user=doc.run_by,
		)


def _process_one_student(doc, enrollment, policy_dict, student_eval_map):
	student = enrollment.student

	if policy_dict:
		row = student_eval_map.get(student)
		if not row:
			_append_log(doc, enrollment, "Skipped", "Other", "Student not found in eligibility dataset for this term.")
			return

		evaluation = _evaluate_student(row, policy_dict)
		status = evaluation.get("promotion_status", "Promoted")

		if status != "Promoted":
			reason_code, detail = _reason_for_skip(evaluation, student)
			_append_log(doc, enrollment, "Skipped", reason_code, detail)
			return

	if policy_dict.get("block_on_fee_due") and _has_fee_due(student):
		_append_log(doc, enrollment, "Skipped", "Fee Due", "Student has outstanding Fee Demand(s).")
		return

	next_batch = _resolve_target_batch(enrollment.batch, doc.target_academic_year, doc.target_term)
	if not next_batch:
		_append_log(
			doc, enrollment, "Skipped", "No Target Batch",
			f"No target Batch found for {doc.target_academic_year}. Create the Batch first.",
		)
		return

	existing = frappe.db.exists(
		"Student Enrollment", {"student": student, "batch": next_batch, "docstatus": ["<", 2]}
	)
	if existing:
		_append_log(doc, enrollment, "Skipped", "Already Promoted", "Enrollment already exists for the target term.", to_enrollment=existing)
		return

	try:
		new_name = _move_enrollment(enrollment.name, student, next_batch)
		_append_log(doc, enrollment, "Promoted", None, None, to_enrollment=new_name)
	except Exception:
		frappe.log_error(
			title=f"Promotion Run {doc.name}: promote failed for {student}",
			message=frappe.get_traceback(),
		)
		_append_log(doc, enrollment, "Failed", "Other", frappe.get_traceback()[:1000])


def _append_log(doc, enrollment, result, reason_code, reason_detail, to_enrollment=None):
	frappe.get_doc(
		{
			"doctype": "Promotion Run Log",
			"parent": doc.name,
			"parenttype": "Promotion Run",
			"parentfield": "log",
			"student": enrollment.student,
			"student_name": enrollment.student_name,
			"from_enrollment": enrollment.name,
			"to_enrollment": to_enrollment,
			"result": result,
			"reason_code": reason_code,
			"reason_detail": reason_detail,
		}
	).db_insert()
	frappe.db.commit()


def _finalize(doc):
	doc.reload()
	promoted = len([r for r in doc.log if r.result == "Promoted"])
	skipped = len([r for r in doc.log if r.result in ("Skipped", "Failed")])
	final_status = "Completed" if skipped == 0 else "Completed with Errors"

	doc.db_set("promoted_count", promoted)
	doc.db_set("skipped_count", skipped)
	doc.db_set("status", final_status)
	frappe.db.commit()

	frappe.publish_realtime(
		"promotion_run_complete",
		{
			"promotion_run": doc.name,
			"status": final_status,
			"promoted": promoted,
			"skipped": skipped,
			"total": doc.total_students,
		},
		user=doc.run_by,
	)


@frappe.whitelist()
def promote_anyway(promotion_run_name, log_row_name, reason=None):
	"""Manual override: create the target enrollment for one skipped student,
	bypassing the policy check."""
	_check_permission()
	run = frappe.get_doc("Promotion Run", promotion_run_name)
	frappe.has_permission("Promotion Run", "write", doc=run, throw=True)

	row = next((r for r in run.log if r.name == log_row_name), None)
	if not row:
		frappe.throw(frappe._("Log entry not found."))
	if row.result == "Promoted":
		frappe.throw(frappe._("This student was already promoted."))

	enrollment = frappe.db.get_value(
		"Student Enrollment", row.from_enrollment, ["name", "student", "batch"], as_dict=True
	)
	if not enrollment:
		frappe.throw(frappe._("Original enrollment not found."))

	next_batch = _resolve_target_batch(enrollment.batch, run.target_academic_year, run.target_term)
	if not next_batch:
		frappe.throw(frappe._("No target Batch exists yet for this student's next term."))

	existing = frappe.db.exists(
		"Student Enrollment", {"student": enrollment.student, "batch": next_batch, "docstatus": ["<", 2]}
	)
	if existing:
		new_name = existing
	else:
		new_name = _move_enrollment(enrollment.name, enrollment.student, next_batch)

	row.to_enrollment = new_name
	row.result = "Promoted"
	row.resolved = 1
	row.resolution_action = "Manually Promoted"
	row.resolved_by = frappe.session.user
	row.resolved_on = now_datetime()
	row.reason_detail = (row.reason_detail or "") + f"\n[Manual override by {frappe.session.user}] {reason or ''}".strip()
	row.db_update()

	_recount(run.name)
	frappe.db.commit()
	return {"ok": True, "to_enrollment": new_name}


@frappe.whitelist()
def mark_as_exempt(promotion_run_name, log_row_name, reason=None):
	_check_permission()
	run = frappe.get_doc("Promotion Run", promotion_run_name)
	frappe.has_permission("Promotion Run", "write", doc=run, throw=True)

	row = next((r for r in run.log if r.name == log_row_name), None)
	if not row:
		frappe.throw(frappe._("Log entry not found."))

	row.resolved = 1
	row.resolution_action = "Marked Exempt"
	row.resolved_by = frappe.session.user
	row.resolved_on = now_datetime()
	row.reason_detail = (row.reason_detail or "") + f"\n[Marked exempt by {frappe.session.user}] {reason or ''}".strip()
	row.db_update()

	frappe.db.commit()
	return {"ok": True}


@frappe.whitelist()
def bulk_resolve(promotion_run_name, log_row_names, action, reason=None):
	"""action: 'promote' or 'exempt'"""
	_check_permission()
	if isinstance(log_row_names, str):
		import json
		log_row_names = json.loads(log_row_names)

	results = {"succeeded": [], "failed": []}
	for row_name in log_row_names:
		try:
			if action == "promote":
				promote_anyway(promotion_run_name, row_name, reason)
			elif action == "exempt":
				mark_as_exempt(promotion_run_name, row_name, reason)
			else:
				frappe.throw(frappe._("Unknown action."))
			results["succeeded"].append(row_name)
		except Exception as e:
			results["failed"].append({"row": row_name, "error": str(e)})
	return results


@frappe.whitelist()
def retry_unresolved(promotion_run_name):
	"""Re-evaluate only the still-unresolved Skipped/Failed rows of a run,
	e.g. after underlying data (attendance, fee payment) has been corrected."""
	_check_permission()
	run = frappe.get_doc("Promotion Run", promotion_run_name)
	frappe.has_permission("Promotion Run", "write", doc=run, throw=True)

	unresolved = [r for r in run.log if r.result in ("Skipped", "Failed") and not r.resolved]
	if not unresolved:
		return {"retried": 0, "promoted": 0}

	policy_dict = {}
	if run.promotion_policy:
		policy_dict = frappe.get_doc("Promotion Policy", run.promotion_policy).as_dict()

	student_eval_map = {}
	if policy_dict:
		unresolved_batches = list({
			b for b in (
				frappe.db.get_value("Student Enrollment", r.from_enrollment, "batch") for r in unresolved
			) if b
		})
		from_years = {
			b.name: cint(b.term_year)
			for b in frappe.db.get_all("Batch", filters={"name": ["in", unresolved_batches]}, fields=["name", "term_year"])
		} if unresolved_batches else {}
		for from_year in set(from_years.values()):
			if from_year is None:
				continue
			for row in _get_students_raw(run.program, run.source_academic_year, from_year):
				student_eval_map[row["student"]] = row

	promoted_now = 0
	for row in unresolved:
		enrollment = frappe.db.get_value(
			"Student Enrollment", row.from_enrollment, ["name", "student", "student_name", "batch"], as_dict=True
		)
		if not enrollment:
			continue

		eval_row = student_eval_map.get(enrollment.student)
		evaluation = _evaluate_student(eval_row, policy_dict) if (eval_row and policy_dict) else {"promotion_status": "Promoted"}
		status = evaluation.get("promotion_status", "Promoted")

		fee_blocked = policy_dict.get("block_on_fee_due") and _has_fee_due(enrollment.student)
		if status == "Promoted" and not fee_blocked:
			next_batch = _resolve_target_batch(enrollment.batch, run.target_academic_year, run.target_term)
			if next_batch and not frappe.db.exists(
				"Student Enrollment", {"student": enrollment.student, "batch": next_batch, "docstatus": ["<", 2]}
			):
				try:
					new_name = _move_enrollment(enrollment.name, enrollment.student, next_batch)
				except Exception:
					frappe.log_error(
						title=f"Promotion Run {run.name}: retry failed for {enrollment.student}",
						message=frappe.get_traceback(),
					)
					continue

				row.to_enrollment = new_name
				row.result = "Promoted"
				row.reason_code = None
				row.reason_detail = f"Promoted on retry by {frappe.session.user}."
				row.resolved = 1
				row.resolution_action = "Manually Promoted"
				row.resolved_by = frappe.session.user
				row.resolved_on = now_datetime()
				row.db_update()
				promoted_now += 1

	_recount(run.name)
	frappe.db.commit()
	return {"retried": len(unresolved), "promoted": promoted_now}


def _recount(promotion_run_name):
	log_rows = frappe.db.get_all(
		"Promotion Run Log", filters={"parent": promotion_run_name}, fields=["result"]
	)
	promoted = len([r for r in log_rows if r.result == "Promoted"])
	skipped = len([r for r in log_rows if r.result in ("Skipped", "Failed")])
	final_status = "Completed" if skipped == 0 else "Completed with Errors"
	frappe.db.set_value("Promotion Run", promotion_run_name, {
		"promoted_count": promoted,
		"skipped_count": skipped,
		"status": final_status,
	})


@frappe.whitelist()
def is_job_active(promotion_run_name):
	last_beat = frappe.db.get_value("Promotion Run", promotion_run_name, "last_heartbeat")
	if not last_beat:
		return False
	return (now_datetime() - last_beat).total_seconds() < 90
