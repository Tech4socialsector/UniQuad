# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe

# Roles permitted to access the analytics dashboard
_DASHBOARD_ROLES = {
	"System Manager",
	"slcm_Registrar",
	"slcm_Programme Chair",
	"slcm_REGO Officer",
	"slcm_FINO Officer",
	"slcm_Registration Officer",
	"slcm_Hostel Admin",
	"slcm_Placement Officer",
}


def _require_dashboard_access():
	"""Raise PermissionError if the caller lacks a dashboard role."""
	if frappe.session.user == "Administrator":
		return
	user_roles = set(frappe.get_roles(frappe.session.user))
	if not user_roles.intersection(_DASHBOARD_ROLES):
		frappe.throw(
			"You do not have permission to access the SLCM Analytics Dashboard.",
			frappe.PermissionError,
		)


# ── Filter helpers ────────────────────────────────────────────────────────────

def _as_list(val):
	"""Normalise a filter value: always return a list, or None if empty."""
	if val is None:
		return None
	if isinstance(val, list):
		cleaned = [v for v in val if v]
		return cleaned if cleaned else None
	if isinstance(val, str) and val:
		return [val]
	return None


def _build_filters(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Return (where_clause, params) tuples for common filter sets.

	Each argument accepts either a single string value or a list of values
	(from multiselect filters) — both are handled uniformly via IN clauses.
	"""
	conditions = []
	params = {}

	ay_list = _as_list(academic_year)
	if ay_list:
		if len(ay_list) == 1:
			conditions.append("sm.academic_year = %(academic_year)s")
			params["academic_year"] = ay_list[0]
		else:
			conditions.append("sm.academic_year IN %(academic_year)s")
			params["academic_year"] = tuple(ay_list)

	ss_list = _as_list(student_status)
	if ss_list:
		if len(ss_list) == 1:
			conditions.append("sm.student_status = %(student_status)s")
			params["student_status"] = ss_list[0]
		else:
			conditions.append("sm.student_status IN %(student_status)s")
			params["student_status"] = tuple(ss_list)

	cohort_list = _as_list(cohort)
	program_list = _as_list(program)

	if cohort_list:
		if len(cohort_list) == 1:
			conditions.append("sm.programme = %(cohort)s")
			params["cohort"] = cohort_list[0]
		else:
			conditions.append("sm.programme IN %(cohort)s")
			params["cohort"] = tuple(cohort_list)
	elif program_list:
		prog_filter = program_list[0] if len(program_list) == 1 else program_list
		if len(program_list) == 1:
			cohorts = frappe.db.get_all("Batch", filters={"program": prog_filter}, pluck="name")
		else:
			cohorts = frappe.db.get_all("Batch", filters=[["program", "in", program_list]], pluck="name")
		if cohorts:
			conditions.append("sm.programme IN %(cohorts)s")
			params["cohorts"] = tuple(cohorts)
		else:
			conditions.append("1=0")

	return " AND ".join(conditions), params


# ── Public API ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_filter_options():
	"""Return cascading filter options for the dashboard."""
	_require_dashboard_access()
	academic_years = frappe.db.get_all(
		"Academic Year",
		fields=["name", "academic_year_name"],
		order_by="year_start_date desc",
	)

	programs = frappe.db.get_all(
		"Programme",
		filters={"program_status": "Active"},
		fields=["name", "program_name", "program_shortcode"],
		order_by="program_name asc",
	)

	cohorts = frappe.db.get_all(
		"Batch",
		fields=["name", "cohort_name", "program", "academic_year", "section", "status"],
		order_by="academic_year desc, cohort_name asc",
	)

	terms = frappe.db.get_all(
		"Academic Term",
		fields=["name", "term_name", "academic_year"],
		order_by="term_start_date desc",
	)

	student_statuses = [
		{"value": "Active",    "label": "Active"},
		{"value": "Inactive",  "label": "Inactive"},
		{"value": "Graduated", "label": "Graduated"},
		{"value": "Dropped",   "label": "Dropped"},
		{"value": "Dormant",   "label": "Dormant"},
	]

	return {
		"academic_years": academic_years,
		"programs": programs,
		"cohorts": cohorts,
		"terms": terms,
		"student_statuses": student_statuses,
	}


@frappe.whitelist()
def get_overview_stats(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Executive KPI cards across all modules."""
	_require_dashboard_access()
	where, params = _build_filters(academic_year, term, program, cohort, student_status)
	sm_where = f"WHERE {where}" if where else ""

	# ── Student totals ────────────────────────────────────────────────────────
	student_totals = frappe.db.sql(
		f"""
		SELECT
			COUNT(*) AS total_students,
			SUM(CASE WHEN student_status = 'Active' THEN 1 ELSE 0 END) AS active_students,
			SUM(CASE WHEN student_status = 'Graduated' THEN 1 ELSE 0 END) AS graduated,
			SUM(CASE WHEN student_status = 'Dropped' THEN 1 ELSE 0 END) AS dropped
		FROM `tabStudent Master` sm
		{sm_where}
		""",
		params,
		as_dict=True,
	)[0]

	# ── Attendance rate (last 30 days) ────────────────────────────────────────
	att_filters = {"attendance_date": [">=", frappe.utils.add_days(frappe.utils.today(), -30)]}
	if academic_year:
		att_filters["academic_year"] = academic_year
	if program:
		att_filters["program"] = program

	att_stats = frappe.db.sql(
		"""
		SELECT
			SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_count,
			SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS absent_count,
			COUNT(*) AS total_count
		FROM `tabStudent Attendance`
		WHERE attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
		""",
		as_dict=True,
	)[0]

	total_att = att_stats.total_count or 0
	att_rate = round((att_stats.present_count or 0) / total_att * 100, 1) if total_att else 0

	# ── Fee collection ────────────────────────────────────────────────────────
	fee_where_parts = []
	fee_params = {}
	if academic_year:
		fee_where_parts.append("academic_year = %(ay)s")
		fee_params["ay"] = academic_year
	if program:
		fee_where_parts.append("program = %(prog)s")
		fee_params["prog"] = program
	fee_where = ("WHERE " + " AND ".join(fee_where_parts)) if fee_where_parts else ""

	fee_stats = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(total_amount), 0) AS total_billed,
			COALESCE(SUM(paid_amount), 0) AS total_collected,
			COALESCE(SUM(outstanding_amount), 0) AS total_outstanding,
			COUNT(*) AS invoice_count
		FROM `tabFee Invoice`
		{fee_where}
		""",
		fee_params,
		as_dict=True,
	)[0]

	fee_rate = (
		round(fee_stats.total_collected / fee_stats.total_billed * 100, 1)
		if fee_stats.total_billed
		else 0
	)

	# ── Active exams ──────────────────────────────────────────────────────────
	active_exams = frappe.db.count("Exam Plan", filters={"status": "Active"})

	# ── Hostel occupancy ──────────────────────────────────────────────────────
	hostel_allocated = frappe.db.count("Hostel Allocation", filters={"is_active": 1})
	total_beds = frappe.db.count("Hostel Bed")

	# ── Placement offers ──────────────────────────────────────────────────────
	total_offers = frappe.db.count("Placement Offer")
	accepted_offers = frappe.db.count("Placement Offer", filters={"offer_status": "Accepted"})

	return {
		"total_students": student_totals.total_students or 0,
		"active_students": student_totals.active_students or 0,
		"graduated_students": student_totals.graduated or 0,
		"dropped_students": student_totals.dropped or 0,
		"attendance_rate": att_rate,
		"total_attendance_records": total_att,
		"fee_collection_rate": fee_rate,
		"total_billed": fee_stats.total_billed or 0,
		"total_collected": fee_stats.total_collected or 0,
		"total_outstanding": fee_stats.total_outstanding or 0,
		"active_exams": active_exams,
		"hostel_allocated": hostel_allocated,
		"total_beds": total_beds,
		"hostel_occupancy_rate": round(hostel_allocated / total_beds * 100, 1) if total_beds else 0,
		"total_placement_offers": total_offers,
		"accepted_placement_offers": accepted_offers,
		"placement_acceptance_rate": round(accepted_offers / total_offers * 100, 1) if total_offers else 0,
	}


@frappe.whitelist()
def get_student_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Student enrollment, status distribution, demographics."""
	_require_dashboard_access()
	where, params = _build_filters(academic_year, term, program, cohort, student_status)
	sm_where = f"WHERE {where}" if where else ""
	sm_and = f"AND {where}" if where else ""

	# Status distribution
	status_dist = frappe.db.sql(
		f"""
		SELECT student_status AS label, COUNT(*) AS value
		FROM `tabStudent Master` sm
		{sm_where}
		GROUP BY student_status
		ORDER BY value DESC
		""",
		params,
		as_dict=True,
	)

	# Gender distribution
	gender_dist = frappe.db.sql(
		f"""
		SELECT COALESCE(gender, 'Not Specified') AS label, COUNT(*) AS value
		FROM `tabStudent Master` sm
		{sm_where}
		GROUP BY gender
		ORDER BY value DESC
		""",
		params,
		as_dict=True,
	)

	# Quota distribution
	quota_dist = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(quota, ''), 'Not Set') AS label, COUNT(*) AS value
		FROM `tabStudent Master` sm
		{sm_where}
		GROUP BY quota
		ORDER BY value DESC
		""",
		params,
		as_dict=True,
	)

	# Program-wise enrollment (through Cohort)
	program_dist = frappe.db.sql(
		f"""
		SELECT
			COALESCE(p.program_name, c.program, 'Unknown') AS label,
			COUNT(sm.name) AS value
		FROM `tabStudent Master` sm
		LEFT JOIN `tabBatch` c ON c.name = sm.programme
		LEFT JOIN `tabProgramme` p ON p.name = c.program
		{sm_where}
		GROUP BY c.program
		ORDER BY value DESC
		LIMIT 12
		""",
		params,
		as_dict=True,
	)

	# Registration status distribution
	reg_status_dist = frappe.db.sql(
		f"""
		SELECT
			COALESCE(registration_status, 'Not Started') AS label,
			COUNT(*) AS value
		FROM `tabStudent Master` sm
		{sm_where}
		GROUP BY registration_status
		ORDER BY value DESC
		""",
		params,
		as_dict=True,
	)

	# Admission type breakdown
	admission_type_dist = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(admission_type, ''), 'Not Set') AS label,
			COUNT(*) AS value
		FROM `tabStudent Master` sm
		{sm_where}
		GROUP BY admission_type
		ORDER BY value DESC
		""",
		params,
		as_dict=True,
	)

	# Scholarship breakdown
	scholarship_dist = frappe.db.sql(
		f"""
		SELECT
			CASE WHEN applying_scholarship = 'Yes' THEN 'Scholarship' ELSE 'No Scholarship' END AS label,
			COUNT(*) AS value
		FROM `tabStudent Master` sm
		{sm_where}
		GROUP BY applying_scholarship
		""",
		params,
		as_dict=True,
	)

	# Cohort-wise count (top 10)
	cohort_dist = frappe.db.sql(
		f"""
		SELECT
			COALESCE(c.cohort_name, sm.programme, 'Unknown') AS label,
			COUNT(sm.name) AS value
		FROM `tabStudent Master` sm
		LEFT JOIN `tabBatch` c ON c.name = sm.programme
		{sm_where}
		GROUP BY sm.programme
		ORDER BY value DESC
		LIMIT 10
		""",
		params,
		as_dict=True,
	)

	return {
		"status_distribution": status_dist,
		"gender_distribution": gender_dist,
		"quota_distribution": quota_dist,
		"program_distribution": program_dist,
		"registration_status": reg_status_dist,
		"admission_type": admission_type_dist,
		"scholarship_distribution": scholarship_dist,
		"cohort_distribution": cohort_dist,
	}


@frappe.whitelist()
def get_attendance_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Attendance rates, trends, and pattern analytics."""
	_require_dashboard_access()
	att_where_parts = []
	att_params = {}

	if academic_year:
		att_where_parts.append("academic_year = %(academic_year)s")
		att_params["academic_year"] = academic_year
	if program:
		att_where_parts.append("program = %(program)s")
		att_params["program"] = program
	if term:
		att_where_parts.append("academic_term = %(term)s")
		att_params["term"] = term

	att_where = ("WHERE " + " AND ".join(att_where_parts)) if att_where_parts else ""
	att_and = ("AND " + " AND ".join(att_where_parts)) if att_where_parts else ""

	# Overall status distribution
	status_dist = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabStudent Attendance`
		{att_where}
		GROUP BY status
		ORDER BY value DESC
		""",
		att_params,
		as_dict=True,
	)

	# Monthly trend (last 12 months)
	monthly_trend = frappe.db.sql(
		f"""
		SELECT
			DATE_FORMAT(attendance_date, '%%Y-%%m') AS month,
			DATE_FORMAT(attendance_date, '%%b %%Y') AS month_label,
			SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present,
			SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS absent,
			SUM(CASE WHEN status = 'OD' THEN 1 ELSE 0 END) AS od,
			COUNT(*) AS total
		FROM `tabStudent Attendance`
		WHERE attendance_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
			AND attendance_date IS NOT NULL
			{att_and}
		GROUP BY DATE_FORMAT(attendance_date, '%%Y-%%m')
		ORDER BY month ASC
		""",
		att_params,
		as_dict=True,
	)

	# Program-wise attendance rate
	program_attendance = frappe.db.sql(
		f"""
		SELECT
			COALESCE(p.program_name, sa.program, 'Unknown') AS label,
			ROUND(
				SUM(CASE WHEN sa.status = 'Present' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0),
				1
			) AS attendance_rate,
			COUNT(*) AS total_records
		FROM `tabStudent Attendance` sa
		LEFT JOIN `tabProgramme` p ON p.name = sa.program
		WHERE sa.program IS NOT NULL AND sa.program != ''
			{att_and}
		GROUP BY sa.program
		HAVING total_records > 10
		ORDER BY attendance_rate DESC
		LIMIT 10
		""",
		att_params,
		as_dict=True,
	)

	# Condonation pipeline — field is `final_status` on this doctype
	cond_stats = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(final_status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabStudent Attendance Condonation`
		GROUP BY final_status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# FA/MFA applications
	fa_mfa_stats = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabFA MFA Application`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Session type breakdown (Lecture / Office Hour / Tutorial)
	session_type_dist = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(session_type, ''), 'Not Set') AS label,
			COUNT(*) AS value
		FROM `tabStudent Attendance`
		{att_where}
		GROUP BY session_type
		ORDER BY value DESC
		""",
		att_params,
		as_dict=True,
	)

	# Attendance source breakdown (Manual / RFID / QR / Auto)
	source_dist = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(source, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabStudent Attendance`
		{att_where}
		GROUP BY source
		ORDER BY value DESC
		""",
		att_params,
		as_dict=True,
	)

	# Condonation faculty recommendation
	condonation_faculty_rec = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(faculty_recommendation, ''), 'Pending') AS label,
			COUNT(*) AS value
		FROM `tabStudent Attendance Condonation`
		GROUP BY faculty_recommendation
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# FA/MFA application type breakdown (FA vs MFA + reason)
	fa_mfa_type_dist = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(application_type, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabFA MFA Application`
		GROUP BY application_type
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Daily attendance for last 30 days
	daily_trend = frappe.db.sql(
		f"""
		SELECT
			attendance_date AS date,
			SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present,
			COUNT(*) AS total
		FROM `tabStudent Attendance`
		WHERE attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
			AND attendance_date IS NOT NULL
			{att_and}
		GROUP BY attendance_date
		ORDER BY attendance_date ASC
		""",
		att_params,
		as_dict=True,
	)

	return {
		"status_distribution":    status_dist,
		"monthly_trend":          monthly_trend,
		"program_attendance":     program_attendance,
		"session_type_dist":      session_type_dist,
		"source_dist":            source_dist,
		"condonation_stats":      cond_stats,
		"condonation_faculty_rec": condonation_faculty_rec,
		"fa_mfa_stats":           fa_mfa_stats,
		"fa_mfa_type_dist":       fa_mfa_type_dist,
		"daily_trend":            daily_trend,
	}


@frappe.whitelist()
def get_examination_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Exam enrollment, grade distribution, pass/fail analytics."""
	_require_dashboard_access()
	# Exam plan filters
	ep_where_parts = []
	ep_params = {}
	if term:
		ep_where_parts.append("term = %(term)s")
		ep_params["term"] = term

	ep_where = ("WHERE " + " AND ".join(ep_where_parts)) if ep_where_parts else ""

	# Exam plans summary
	exam_plans = frappe.db.sql(
		f"""
		SELECT
			ep.exam_name AS label,
			ep.status,
			COUNT(scm.name) AS enrolled_students
		FROM `tabExam Plan` ep
		LEFT JOIN `tabStudent Course Marks` scm ON scm.exam_plan = ep.name
		{ep_where}
		GROUP BY ep.name
		ORDER BY ep.creation DESC
		LIMIT 15
		""",
		ep_params,
		as_dict=True,
	)

	# Grade distribution
	grade_dist = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(grade, ''), 'Not Graded') AS label,
			COUNT(*) AS value
		FROM `tabStudent Course Marks`
		WHERE status = 'Submitted'
		GROUP BY grade
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Pass/Fail/Detained distribution
	enrollment_status = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(enrollment_status, ''), 'Enrolled') AS label,
			COUNT(*) AS value
		FROM `tabStudent Course Marks`
		WHERE status = 'Submitted'
		GROUP BY enrollment_status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Exam plan status breakdown
	exam_status = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabExam Plan`
		{ep_where}
		GROUP BY status
		""",
		ep_params,
		as_dict=True,
	)

	# Re-exam statistics
	reexam_stats = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabRe Exam Registration`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Improvement exam stats
	improvement_stats = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabImprovement Exam Registration`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Course-wise submission status
	course_status = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Draft') AS label,
			COUNT(*) AS value
		FROM `tabStudent Course Marks`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Fairness status (Fair / Unfair / Malpractice)
	fairness_dist = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(fairness_status, ''), 'Not Set') AS label,
			COUNT(*) AS value
		FROM `tabStudent Course Marks`
		WHERE status = 'Submitted'
		GROUP BY fairness_status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Attendance status in marks (Present / Absent / Detained)
	att_in_marks = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(attendance_status, ''), 'Not Set') AS label,
			COUNT(*) AS value
		FROM `tabStudent Course Marks`
		GROUP BY attendance_status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# MFA flag distribution
	mfa_dist = frappe.db.sql(
		"""
		SELECT
			CASE WHEN mfa = 'Yes' THEN 'MFA Granted' ELSE 'No MFA' END AS label,
			COUNT(*) AS value
		FROM `tabStudent Course Marks`
		WHERE status = 'Submitted'
		GROUP BY mfa
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Re-exam payment status
	reexam_payment = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(payment_status, ''), 'Pending') AS label,
			COUNT(*) AS value
		FROM `tabRe Exam Registration`
		GROUP BY payment_status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Improvement exam payment status
	improvement_payment = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(payment_status, ''), 'Pending') AS label,
			COUNT(*) AS value
		FROM `tabImprovement Exam Registration`
		GROUP BY payment_status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Grade Appeals — appeal type and status
	grade_appeal_type = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(appeal_type, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabGrade Appeal`
		GROUP BY appeal_type
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	grade_appeal_status = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabGrade Appeal`
		GROUP BY status
		ORDER BY FIELD(status, 'Submitted', 'Under Review', 'Resolved', 'Rejected') ASC
		""",
		as_dict=True,
	)

	# Transcript — type and status
	transcript_type_dist = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(transcript_type, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabStudent Transcript`
		GROUP BY transcript_type
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	transcript_status_dist = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabStudent Transcript`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Result Publishing — published vs unpublished + average GPA
	result_publish_stats = frappe.db.sql(
		"""
		SELECT
			SUM(CASE WHEN is_published = 1 THEN 1 ELSE 0 END) AS published,
			SUM(CASE WHEN is_published = 0 THEN 1 ELSE 0 END) AS unpublished,
			COUNT(*) AS total,
			ROUND(AVG(CASE WHEN is_published = 1 AND term_gpa > 0 THEN term_gpa END), 2) AS avg_term_gpa,
			ROUND(AVG(CASE WHEN is_published = 1 AND cumulative_gpa > 0 THEN cumulative_gpa END), 2) AS avg_cgpa
		FROM `tabStudent Result Publish`
		""",
		as_dict=True,
	)[0]

	# Exam Barcodes
	barcode_by_plan = frappe.db.sql(
		"""
		SELECT ep.exam_name AS label, COUNT(eb.name) AS value
		FROM `tabExam Barcode` eb
		LEFT JOIN `tabExam Plan` ep ON ep.name = eb.exam_plan
		GROUP BY eb.exam_plan
		ORDER BY value DESC
		LIMIT 15
		""",
		as_dict=True,
	)

	barcode_by_course = frappe.db.sql(
		"""
		SELECT COALESCE(c.course_name, eb.course, 'Unknown') AS label, COUNT(*) AS value
		FROM `tabExam Barcode` eb
		LEFT JOIN `tabCourse` c ON c.name = eb.course
		GROUP BY eb.course
		ORDER BY value DESC
		LIMIT 12
		""",
		as_dict=True,
	)

	total_barcodes    = frappe.db.count("Exam Barcode")
	barcode_exam_plans = frappe.db.sql(
		"SELECT COUNT(DISTINCT exam_plan) FROM `tabExam Barcode`"
	)[0][0]

	# Summary counts
	total_grade_appeals = frappe.db.count("Grade Appeal")
	total_transcripts   = frappe.db.count("Student Transcript")
	generated_transcripts = frappe.db.count("Student Transcript", filters={"status": "Generated"})

	return {
		"exam_plans":           exam_plans,
		"grade_distribution":   grade_dist,
		"enrollment_status":    enrollment_status,
		"exam_status":          exam_status,
		"reexam_stats":         reexam_stats,
		"improvement_stats":    improvement_stats,
		"course_marks_status":  course_status,
		"fairness_dist":        fairness_dist,
		"att_in_marks":         att_in_marks,
		"mfa_dist":             mfa_dist,
		"reexam_payment":       reexam_payment,
		"improvement_payment":  improvement_payment,
		"grade_appeal_type":    grade_appeal_type,
		"grade_appeal_status":  grade_appeal_status,
		"transcript_type_dist": transcript_type_dist,
		"transcript_status_dist": transcript_status_dist,
		"result_publish_stats": result_publish_stats,
		"total_grade_appeals":  total_grade_appeals,
		"total_transcripts":    total_transcripts,
		"generated_transcripts": generated_transcripts,
		"barcode_by_plan":      barcode_by_plan,
		"barcode_by_course":    barcode_by_course,
		"total_barcodes":       total_barcodes or 0,
		"barcode_exam_plans":   barcode_exam_plans or 0,
	}


@frappe.whitelist()
def get_fees_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Fee collection, payment status, outstanding analysis."""
	_require_dashboard_access()
	fi_where_parts = []
	fi_params = {}

	if academic_year:
		fi_where_parts.append("academic_year = %(academic_year)s")
		fi_params["academic_year"] = academic_year
	if program:
		fi_where_parts.append("program = %(program)s")
		fi_params["program"] = program

	fi_where = ("WHERE " + " AND ".join(fi_where_parts)) if fi_where_parts else ""
	fi_and = ("AND " + " AND ".join(fi_where_parts)) if fi_where_parts else ""

	# Invoice status distribution — uses `status` field (Unpaid/Partially Paid/Paid/Overdue/Cancelled)
	# NOTE: `payment_status` on Fee Invoice is the Razorpay gateway field, not the invoice status
	payment_status = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value,
			COALESCE(SUM(total_amount), 0) AS amount
		FROM `tabFee Invoice`
		{fi_where}
		GROUP BY status
		ORDER BY value DESC
		""",
		fi_params,
		as_dict=True,
	)

	# Collection summary
	collection_summary = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(total_amount), 0) AS total_billed,
			COALESCE(SUM(paid_amount), 0) AS total_collected,
			COALESCE(SUM(outstanding_amount), 0) AS total_outstanding,
			COUNT(*) AS total_invoices,
			COUNT(DISTINCT student) AS students_billed
		FROM `tabFee Invoice`
		{fi_where}
		""",
		fi_params,
		as_dict=True,
	)[0]

	# Program-wise fee collection
	program_fees = frappe.db.sql(
		f"""
		SELECT
			COALESCE(p.program_name, fi.program, 'Unknown') AS label,
			COALESCE(SUM(fi.total_amount), 0) AS total_billed,
			COALESCE(SUM(fi.paid_amount), 0) AS collected,
			COALESCE(SUM(fi.outstanding_amount), 0) AS outstanding
		FROM `tabFee Invoice` fi
		LEFT JOIN `tabProgramme` p ON p.name = fi.program
		WHERE fi.program IS NOT NULL AND fi.program != ''
			{fi_and}
		GROUP BY fi.program
		ORDER BY total_billed DESC
		LIMIT 10
		""",
		fi_params,
		as_dict=True,
	)

	# Monthly collection trend
	monthly_collection = frappe.db.sql(
		f"""
		SELECT
			DATE_FORMAT(invoice_date, '%%Y-%%m') AS month,
			DATE_FORMAT(invoice_date, '%%b %%Y') AS month_label,
			COALESCE(SUM(total_amount), 0) AS billed,
			COALESCE(SUM(paid_amount), 0) AS collected
		FROM `tabFee Invoice`
		WHERE invoice_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
			AND invoice_date IS NOT NULL
			{fi_and}
		GROUP BY DATE_FORMAT(invoice_date, '%%Y-%%m')
		ORDER BY month ASC
		""",
		fi_params,
		as_dict=True,
	)

	# Fee payment status from Student Master
	sm_fee_status = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(fee_payment_status, ''), 'Not Set') AS label,
			COUNT(*) AS value
		FROM `tabStudent Master`
		GROUP BY fee_payment_status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	return {
		"payment_status_distribution": payment_status,
		"collection_summary": collection_summary,
		"program_fees": program_fees,
		"monthly_collection": monthly_collection,
		"student_fee_payment_status": sm_fee_status,
	}


@frappe.whitelist()
def get_hostel_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Hostel occupancy, room allocation, and complaint analytics."""
	_require_dashboard_access()
	# Room summary
	room_summary = frappe.db.sql(
		"""
		SELECT
			COUNT(*) AS total_rooms,
			SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS occupied_rooms
		FROM `tabHostel Allocation`
		""",
		as_dict=True,
	)[0]

	total_beds = frappe.db.count("Hostel Bed")
	occupied_beds = frappe.db.count("Hostel Allocation", filters={"is_active": 1})

	# Per-hostel occupancy
	hostel_occupancy = frappe.db.sql(
		"""
		SELECT
			COALESCE(h.hostel_name, ha.hostel, 'Unknown') AS label,
			COUNT(ha.name) AS value
		FROM `tabHostel Allocation` ha
		LEFT JOIN `tabHostel` h ON h.name = ha.hostel
		WHERE ha.is_active = 1
		GROUP BY ha.hostel
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Allocation status
	allocation_status = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabHostel Allocation`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Complaint analytics
	complaint_status = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabHostel Complaint`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Complaint types
	complaint_type = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(complaint_type, ''), 'Other') AS label,
			COUNT(*) AS value
		FROM `tabHostel Complaint`
		GROUP BY complaint_type
		ORDER BY value DESC
		LIMIT 8
		""",
		as_dict=True,
	)

	# Meal plan distribution
	meal_dist = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(meal_plan, ''), 'Not Set') AS label,
			COUNT(*) AS value
		FROM `tabStudent Master`
		WHERE is_hosteller = 1
		GROUP BY meal_plan
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Leave request status
	leave_status = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabHostel Leave Request`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	return {
		"total_beds": total_beds,
		"occupied_beds": occupied_beds,
		"available_beds": max(0, total_beds - occupied_beds),
		"occupancy_rate": round(occupied_beds / total_beds * 100, 1) if total_beds else 0,
		"hostel_occupancy": hostel_occupancy,
		"allocation_status": allocation_status,
		"complaint_status": complaint_status,
		"complaint_type": complaint_type,
		"meal_distribution": meal_dist,
		"leave_request_status": leave_status,
	}


@frappe.whitelist()
def get_placement_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Placement opportunity pipeline, applications, and offers."""
	_require_dashboard_access()
	# Opportunity summary
	opportunity_status = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabPlacement Opportunity`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Opportunity type breakdown
	opportunity_type = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(opportunity_type, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabPlacement Opportunity`
		GROUP BY opportunity_type
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Application funnel
	status = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value
		FROM `tabPlacement Application`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Offer status
	status = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(status, ''), 'Unknown') AS label,
			COUNT(*) AS value,
			COALESCE(SUM(compensation), 0) AS total_compensation
		FROM `tabPlacement Offer`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Top companies by offers
	top_companies = frappe.db.sql(
		"""
		SELECT
			COALESCE(c.company_name, po.company, 'Unknown') AS label,
			COUNT(pof.name) AS offer_count,
			COALESCE(SUM(pof.compensation), 0) AS total_compensation
		FROM `tabPlacement Offer` pof
		LEFT JOIN `tabPlacement Opportunity` po ON po.name = pof.opportunity
		LEFT JOIN `tabCompany` c ON c.name = po.company
		GROUP BY po.company
		ORDER BY offer_count DESC
		LIMIT 10
		""",
		as_dict=True,
	)

	# Summary stats
	total_opportunities = frappe.db.count("Placement Opportunity")
	total_applications = frappe.db.count("Placement Application")
	total_offers = frappe.db.count("Placement Offer")
	accepted_offers = frappe.db.count("Placement Offer", filters={"offer_status": "Accepted"})

	avg_compensation = frappe.db.sql(
		"""
		SELECT COALESCE(AVG(compensation), 0) AS avg_comp
		FROM `tabPlacement Offer`
		WHERE offer_status = 'Accepted' AND compensation > 0
		""",
		as_dict=True,
	)[0].get("avg_comp", 0)

	return {
		"opportunity_status": opportunity_status,
		"opportunity_type": opportunity_type,
		"application_funnel": status,
		"status": status,
		"top_companies": top_companies,
		"total_opportunities": total_opportunities,
		"total_applications": total_applications,
		"total_offers": total_offers,
		"accepted_offers": accepted_offers,
		"avg_compensation": round(avg_compensation, 0),
		"placement_rate": round(accepted_offers / total_applications * 100, 1) if total_applications else 0,
	}


@frappe.whitelist()
def get_programme_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Programme structure, cohort health, enrollment, and course offering analytics."""
	_require_dashboard_access()

	ay_filter   = {"academic_year": academic_year} if academic_year else {}
	prog_filter = {"program": program} if program else {}
	coh_filter  = {"cohort": cohort} if cohort else {}

	# ── Programs ─────────────────────────────────────────────────────────────
	program_status = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(program_status, ''), 'Not Set') AS label, COUNT(*) AS value
		FROM `tabProgramme`
		GROUP BY program_status ORDER BY value DESC
		""",
		as_dict=True,
	)

	level_of_study = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(level_of_study, ''), 'Not Set') AS label, COUNT(*) AS value
		FROM `tabProgramme`
		GROUP BY level_of_study ORDER BY value DESC
		""",
		as_dict=True,
	)

	dept_distribution = frappe.db.sql(
		"""
		SELECT COALESCE(d.department_name, p.department, 'No Department') AS label,
			   COUNT(p.name) AS value
		FROM `tabProgramme` p
		LEFT JOIN `tabDepartment` d ON d.name = p.department
		GROUP BY p.department ORDER BY value DESC LIMIT 12
		""",
		as_dict=True,
	)

	# ── Cohorts ───────────────────────────────────────────────────────────────
	cohort_filters = {}
	if academic_year:
		cohort_filters["academic_year"] = academic_year
	if program:
		cohort_filters["program"] = program

	cohort_status = frappe.db.get_all(
		"Batch", filters=cohort_filters,
		fields=["status"],
	)
	from collections import Counter
	cohort_status_counts = Counter(r.status or "Not Set" for r in cohort_status)
	cohort_status_dist = [{"label": k, "value": v} for k, v in cohort_status_counts.most_common()]

	# ── Student Enrollment ────────────────────────────────────────────────────
	se_where_parts = []
	se_params = {}
	if academic_year:
		se_where_parts.append("se.academic_year = %(academic_year)s")
		se_params["academic_year"] = academic_year
	if program:
		se_where_parts.append("se.program = %(program)s")
		se_params["program"] = program
	if cohort:
		se_where_parts.append("se.batch = %(cohort)s")
		se_params["cohort"] = cohort

	se_where = ("WHERE " + " AND ".join(se_where_parts)) if se_where_parts else ""

	enrollment_status = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(se.status, ''), 'Unknown') AS label, COUNT(*) AS value
		FROM `tabStudent Enrollment` se
		{se_where}
		GROUP BY se.status ORDER BY value DESC
		""",
		se_params,
		as_dict=True,
	)

	program_enrollment = frappe.db.sql(
		f"""
		SELECT COALESCE(p.program_name, se.program, 'Unknown') AS label, COUNT(*) AS value
		FROM `tabStudent Enrollment` se
		LEFT JOIN `tabProgramme` p ON p.name = se.program
		{se_where}
		GROUP BY se.program ORDER BY value DESC LIMIT 12
		""",
		se_params,
		as_dict=True,
	)

	cohort_enrollment = frappe.db.sql(
		f"""
		SELECT COALESCE(c.batch_name, se.batch, 'Unknown') AS label, COUNT(*) AS value
		FROM `tabStudent Enrollment` se
		LEFT JOIN `tabBatch` c ON c.name = se.batch
		{se_where}
		GROUP BY se.batch ORDER BY value DESC LIMIT 10
		""",
		se_params,
		as_dict=True,
	)

	# ── Course Offerings ──────────────────────────────────────────────────────
	co_where_parts = []
	co_params = {}
	if academic_year:
		co_where_parts.append("co.academic_year = %(academic_year)s")
		co_params["academic_year"] = academic_year
	if program:
		co_where_parts.append("co.program = %(program)s")
		co_params["program"] = program
	if cohort:
		co_where_parts.append("co.cohort = %(cohort)s")
		co_params["cohort"] = cohort

	co_where = ("WHERE " + " AND ".join(co_where_parts)) if co_where_parts else ""

	offering_status = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(co.status, ''), 'Unknown') AS label, COUNT(*) AS value
		FROM `tabCourse Offering` co
		{co_where}
		GROUP BY co.status ORDER BY value DESC
		""",
		co_params,
		as_dict=True,
	)

	offering_by_program = frappe.db.sql(
		f"""
		SELECT COALESCE(p.program_name, co.program, 'Unknown') AS label, COUNT(*) AS value
		FROM `tabCourse Offering` co
		LEFT JOIN `tabProgramme` p ON p.name = co.program
		{co_where}
		GROUP BY co.program ORDER BY value DESC LIMIT 12
		""",
		co_params,
		as_dict=True,
	)

	# ── Student Enrollment Course (child rows) ────────────────────────────────
	course_enroll_status = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(sec.status, ''), 'Unknown') AS label, COUNT(*) AS value
		FROM `tabStudent Enrollment Course` sec
		GROUP BY sec.status ORDER BY value DESC
		""",
		as_dict=True,
	)

	# ── Summary counts ────────────────────────────────────────────────────────
	total_programs    = frappe.db.count("Programme")
	active_programs   = frappe.db.count("Programme", filters={"program_status": "Active"})
	total_cohorts     = frappe.db.count("Batch", filters=cohort_filters)
	active_cohorts    = frappe.db.count("Batch", filters={**cohort_filters, "status": "Active"})
	total_enrollments = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabStudent Enrollment` se {se_where}", se_params
	)[0][0]
	active_enrollments = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabStudent Enrollment` se {se_where}"
		+ (" AND " if se_where else " WHERE ") + "se.status = 'Enrolled'",
		se_params,
	)[0][0]
	total_offerings = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabCourse Offering` co {co_where}", co_params
	)[0][0]
	open_offerings = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabCourse Offering` co {co_where}"
		+ (" AND " if co_where else " WHERE ") + "co.status = 'Active'",
		co_params,
	)[0][0]

	dropped = next((x["value"] for x in enrollment_status if x["label"] == "Dropped"), 0)
	enrolled = next((x["value"] for x in enrollment_status if x["label"] == "Enrolled"), 0)
	enrollment_rate = round(enrolled / (enrolled + dropped) * 100, 1) if (enrolled + dropped) else 0

	return {
		"total_programs":      total_programs,
		"active_programs":     active_programs,
		"total_cohorts":       total_cohorts,
		"active_cohorts":      active_cohorts,
		"total_enrollments":   total_enrollments or 0,
		"active_enrollments":  active_enrollments or 0,
		"total_offerings":     total_offerings or 0,
		"open_offerings":      open_offerings or 0,
		"enrollment_rate":     enrollment_rate,
		"program_status":      program_status,
		"level_of_study":      level_of_study,
		"dept_distribution":   dept_distribution,
		"cohort_status":       cohort_status_dist,
		"enrollment_status":   enrollment_status,
		"program_enrollment":  program_enrollment,
		"cohort_enrollment":   cohort_enrollment,
		"offering_status":     offering_status,
		"offering_by_program": offering_by_program,
		"course_enroll_status": course_enroll_status,
	}


@frappe.whitelist()
def get_admission_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Admission pipeline, applicant funnel, cycle, and offer analytics."""
	_require_dashboard_access()

	adm_where_parts = []
	adm_params = {}

	if program:
		adm_where_parts.append("aa.program = %(program)s")
		adm_params["program"] = program

	if academic_year:
		adm_where_parts.append(
			"aa.admission_cycle IN "
			"(SELECT name FROM `tabAdmission Cycle` WHERE academic_year = %(academic_year)s)"
		)
		adm_params["academic_year"] = academic_year

	adm_where = ("WHERE " + " AND ".join(adm_where_parts)) if adm_where_parts else ""

	# Application status pipeline (ordered)
	app_status_pipeline = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(status, ''), 'Unknown') AS label, COUNT(*) AS value
		FROM `tabAdmission Application` aa
		{adm_where}
		GROUP BY status
		ORDER BY FIELD(status,
			'Draft','Submitted','Under Review','Shortlisted','Waitlisted',
			'Offered','Accepted','Rejected','Withdrawn') ASC
		""",
		adm_params,
		as_dict=True,
	)

	# Eligibility status
	eligibility_dist = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(eligibility_status, ''), 'Pending') AS label, COUNT(*) AS value
		FROM `tabAdmission Application` aa
		{adm_where}
		GROUP BY eligibility_status
		ORDER BY value DESC
		""",
		adm_params,
		as_dict=True,
	)

	# Test result status
	test_result_dist = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(test_result_status, ''), 'Pending') AS label, COUNT(*) AS value
		FROM `tabAdmission Application` aa
		{adm_where}
		GROUP BY test_result_status
		ORDER BY value DESC
		""",
		adm_params,
		as_dict=True,
	)

	# Interview status
	interview_dist = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(interview_status, ''), 'Not Scheduled') AS label, COUNT(*) AS value
		FROM `tabAdmission Application` aa
		{adm_where}
		GROUP BY interview_status
		ORDER BY value DESC
		""",
		adm_params,
		as_dict=True,
	)

	# Offer letter status
	offer_status_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(status, ''), 'Draft') AS label, COUNT(*) AS value
		FROM `tabOffer Letter`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Merit list status
	merit_status_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(status, ''), 'Draft') AS label, COUNT(*) AS value
		FROM `tabMerit List`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Application fee status (on Applicant)
	app_fee_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(application_fee_status, ''), 'Pending') AS label, COUNT(*) AS value
		FROM `tabApplicant`
		GROUP BY application_fee_status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Admission cycle status
	cycle_status_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(status, ''), 'Draft') AS label, COUNT(*) AS value
		FROM `tabAdmission Cycle`
		GROUP BY status
		ORDER BY value DESC
		""",
		as_dict=True,
	)

	# Program-wise applications
	program_apps = frappe.db.sql(
		f"""
		SELECT COALESCE(p.program_name, aa.program, 'Unknown') AS label, COUNT(*) AS value
		FROM `tabAdmission Application` aa
		LEFT JOIN `tabProgramme` p ON p.name = aa.program
		{adm_where}
		GROUP BY aa.program
		ORDER BY value DESC
		LIMIT 12
		""",
		adm_params,
		as_dict=True,
	)

	total_applicants = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabAdmission Application` aa {adm_where}",
		adm_params,
	)[0][0]

	active_cycles   = frappe.db.count("Admission Cycle", filters={"status": "Active"})
	total_offers    = frappe.db.count("Offer Letter")
	accepted_offers = frappe.db.count("Offer Letter", filters={"status": "Accepted"})
	total_merit_lists = frappe.db.count("Merit List")

	return {
		"total_applicants":           total_applicants or 0,
		"active_cycles":              active_cycles,
		"total_offers":               total_offers,
		"accepted_offers":            accepted_offers,
		"acceptance_rate":            round(accepted_offers / total_offers * 100, 1) if total_offers else 0,
		"total_merit_lists":          total_merit_lists,
		"status_pipeline": app_status_pipeline,
		"eligibility_distribution":   eligibility_dist,
		"test_result_distribution":   test_result_dist,
		"interview_distribution":     interview_dist,
		"offer_status_distribution":  offer_status_dist,
		"merit_list_status":          merit_status_dist,
		"application_fee_status":     app_fee_dist,
		"cycle_status":               cycle_status_dist,
		"program_applications":       program_apps,
	}


@frappe.whitelist()
def get_idcard_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Student ID Card issuance, status, and type analytics."""
	_require_dashboard_access()

	status_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(card_status, ''), 'Draft') AS label, COUNT(*) AS value
		FROM `tabID Card Generation`
		GROUP BY card_status ORDER BY value DESC
		""",
		as_dict=True,
	)

	type_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(card_type, ''), 'Unknown') AS label, COUNT(*) AS value
		FROM `tabID Card Generation`
		GROUP BY card_type ORDER BY value DESC
		""",
		as_dict=True,
	)

	dept_dist = frappe.db.sql(
		"""
		SELECT COALESCE(d.department_name, ic.department, 'No Department') AS label,
			   COUNT(*) AS value
		FROM `tabID Card Generation` ic
		LEFT JOIN `tabDepartment` d ON d.name = ic.department
		WHERE ic.department IS NOT NULL AND ic.department != ''
		GROUP BY ic.department ORDER BY value DESC LIMIT 12
		""",
		as_dict=True,
	)

	program_dist = frappe.db.sql(
		"""
		SELECT COALESCE(c.cohort_name, ic.program, 'Unknown') AS label, COUNT(*) AS value
		FROM `tabID Card Generation` ic
		LEFT JOIN `tabBatch` c ON c.name = ic.program
		WHERE ic.program IS NOT NULL AND ic.program != ''
		GROUP BY ic.program ORDER BY value DESC LIMIT 12
		""",
		as_dict=True,
	)

	total_cards     = frappe.db.count("ID Card Generation")
	generated_cards = frappe.db.count("ID Card Generation", filters={"card_status": "Generated"})
	printed_cards   = frappe.db.count("ID Card Generation", filters={"card_status": "Printed"})
	active_cards    = generated_cards + printed_cards
	cancelled_cards = frappe.db.sql(
		"""SELECT COUNT(*) FROM `tabID Card Generation`
		   WHERE card_status IN ('Cancelled', 'Expired', 'Error')"""
	)[0][0]

	return {
		"total_cards":     total_cards,
		"generated_cards": generated_cards,
		"printed_cards":   printed_cards,
		"active_cards":    active_cards,
		"cancelled_cards": cancelled_cards or 0,
		"status_dist":     status_dist,
		"type_dist":       type_dist,
		"dept_dist":        dept_dist,
		"program_dist":     program_dist,
	}


@frappe.whitelist()
def get_venue_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Venue booking requests, status, and usage analytics."""
	_require_dashboard_access()

	status_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(status, ''), 'Pending Allotment') AS label, COUNT(*) AS value
		FROM `tabVenue Booking`
		GROUP BY status
		ORDER BY FIELD(status, 'Pending Allotment', 'Allotted', 'Rejected', 'Cancelled') ASC
		""",
		as_dict=True,
	)

	venue_type_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(venue_type, ''), 'Unknown') AS label, COUNT(*) AS value
		FROM `tabVenue Booking`
		GROUP BY venue_type ORDER BY value DESC
		""",
		as_dict=True,
	)

	requester_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(requester_type, ''), 'Unknown') AS label, COUNT(*) AS value
		FROM `tabVenue Booking`
		GROUP BY requester_type ORDER BY value DESC
		""",
		as_dict=True,
	)

	room_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(room, ''), 'Not Specified') AS label, COUNT(*) AS value
		FROM `tabVenue Booking`
		WHERE room IS NOT NULL AND room != ''
		GROUP BY room ORDER BY value DESC LIMIT 15
		""",
		as_dict=True,
	)

	total_bookings    = frappe.db.count("Venue Booking")
	pending_bookings  = frappe.db.count("Venue Booking", filters={"status": "Pending Allotment"})
	approved_bookings = frappe.db.count("Venue Booking", filters={"status": "Allotted"})
	rejected_bookings = frappe.db.sql(
		"""SELECT COUNT(*) FROM `tabVenue Booking`
		   WHERE status IN ('Rejected', 'Cancelled')"""
	)[0][0]

	return {
		"total_bookings":    total_bookings,
		"pending_bookings":  pending_bookings,
		"approved_bookings": approved_bookings,
		"rejected_bookings": rejected_bookings or 0,
		"status_dist":       status_dist,
		"venue_type_dist":   venue_type_dist,
		"requester_dist":    requester_dist,
		"room_dist":         room_dist,
	}


@frappe.whitelist()
def get_promotion_analytics(academic_year=None, term=None, program=None, cohort=None, student_status=None):
	"""Student promotion decisions, criteria checks, and policy analytics."""
	_require_dashboard_access()

	# Only published decisions count; Drafts are unreleased and Superseded
	# rows are history replaced by a later decision.
	sp_where_parts = ["IFNULL(sp.stage, 'Published') = 'Published'"]
	sp_params = {}
	if academic_year:
		sp_where_parts.append(
			"sp.promotion_policy IN "
			"(SELECT name FROM `tabPromotion Policy` WHERE academic_year = %(academic_year)s)"
		)
		sp_params["academic_year"] = academic_year
	if cohort:
		sp_where_parts.append("sp.programme = %(cohort)s")
		sp_params["cohort"] = cohort

	sp_where = ("WHERE " + " AND ".join(sp_where_parts)) if sp_where_parts else ""

	promotion_status = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(sp.promotion_status, ''), 'Unknown') AS label, COUNT(*) AS value
		FROM `tabStudent Promotion` sp
		{sp_where}
		GROUP BY sp.promotion_status
		ORDER BY FIELD(sp.promotion_status,
			'Promoted','Not Promoted','Conditional',
			'Override - Promoted','Override - Not Promoted') ASC
		""",
		sp_params,
		as_dict=True,
	)

	override_dist = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(sp.promotion_status, ''), 'Unknown') AS label, COUNT(*) AS value
		FROM `tabStudent Promotion` sp
		{sp_where} AND sp.manual_override = 1
		GROUP BY sp.promotion_status ORDER BY value DESC
		""",
		sp_params,
		as_dict=True,
	)

	cgpa_result = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(sp.cgpa_result, ''), 'Not Checked') AS label, COUNT(*) AS value
		FROM `tabStudent Promotion` sp {sp_where}
		GROUP BY sp.cgpa_result ORDER BY value DESC
		""",
		sp_params, as_dict=True,
	)

	backlog_result = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(sp.backlog_result, ''), 'Not Checked') AS label, COUNT(*) AS value
		FROM `tabStudent Promotion` sp {sp_where}
		GROUP BY sp.backlog_result ORDER BY value DESC
		""",
		sp_params, as_dict=True,
	)

	attendance_result = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(sp.attendance_result, ''), 'Not Checked') AS label, COUNT(*) AS value
		FROM `tabStudent Promotion` sp {sp_where}
		GROUP BY sp.attendance_result ORDER BY value DESC
		""",
		sp_params, as_dict=True,
	)

	shortage_result = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(sp.shortage_course_result, ''), 'Not Checked') AS label, COUNT(*) AS value
		FROM `tabStudent Promotion` sp {sp_where}
		GROUP BY sp.shortage_course_result ORDER BY value DESC
		""",
		sp_params, as_dict=True,
	)

	policy_status = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(status, ''), 'Draft') AS label, COUNT(*) AS value
		FROM `tabPromotion Policy`
		GROUP BY status ORDER BY value DESC
		""",
		as_dict=True,
	)

	cohort_dist = frappe.db.sql(
		f"""
		SELECT COALESCE(c.cohort_name, sp.programme, 'Unknown') AS label,
			   COUNT(*) AS value
		FROM `tabStudent Promotion` sp
		LEFT JOIN `tabBatch` c ON c.name = sp.programme
		{sp_where}
		GROUP BY sp.programme ORDER BY value DESC LIMIT 12
		""",
		sp_params,
		as_dict=True,
	)

	total_promotions  = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabStudent Promotion` sp {sp_where}", sp_params
	)[0][0]

	def _count(status_label):
		return next((x["value"] for x in promotion_status if x["label"] == status_label), 0)

	total_policies  = frappe.db.count("Promotion Policy")
	active_policies = frappe.db.count("Promotion Policy", filters={"status": "Active"})

	return {
		"total_promotions":   total_promotions or 0,
		"promoted_count":     _count("Promoted"),
		"not_promoted_count": _count("Not Promoted"),
		"conditional_count":  _count("Conditional"),
		"total_policies":     total_policies,
		"active_policies":    active_policies,
		"promotion_status":   promotion_status,
		"override_dist":      override_dist,
		"policy_status":      policy_status,
		"cgpa_result":        cgpa_result,
		"backlog_result":     backlog_result,
		"attendance_result":  attendance_result,
		"shortage_result":    shortage_result,
		"cohort_dist":        cohort_dist,
	}


@frappe.whitelist()
def get_ticketing_analytics(**kwargs):
	"""Support ticketing metrics from the HD Ticket doctype."""
	_require_dashboard_access()

	if not frappe.db.table_exists("HD Ticket"):
		return {
			"total_tickets": 0, "open_tickets": 0, "resolved_tickets": 0,
			"closed_tickets": 0, "high_priority": 0, "sla_breached": 0,
			"avg_first_response_hrs": 0, "avg_resolution_hrs": 0,
			"resolved_pct": 0, "sla_pct": 0,
			"status_dist": [], "priority_dist": [], "type_dist": [],
			"team_dist": [], "sla_dist": [], "monthly_trend": [],
		}

	# ── Totals by status ─────────────────────────────────────────────────────
	status_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(status,''), 'Unknown') AS label, COUNT(*) AS value
		FROM `tabHD Ticket`
		GROUP BY status ORDER BY value DESC
		""",
		as_dict=True,
	)

	priority_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(priority,''), 'None') AS label, COUNT(*) AS value
		FROM `tabHD Ticket`
		GROUP BY priority ORDER BY FIELD(priority,'Urgent','High','Medium','Low') ASC
		""",
		as_dict=True,
	)

	type_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(ticket_type,''), 'Uncategorized') AS label, COUNT(*) AS value
		FROM `tabHD Ticket`
		GROUP BY ticket_type ORDER BY value DESC LIMIT 10
		""",
		as_dict=True,
	)

	team_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(agent_group,''), 'Unassigned') AS label, COUNT(*) AS value
		FROM `tabHD Ticket`
		GROUP BY agent_group ORDER BY value DESC LIMIT 10
		""",
		as_dict=True,
	)

	sla_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(agreement_status,''), 'None') AS label, COUNT(*) AS value
		FROM `tabHD Ticket`
		GROUP BY agreement_status ORDER BY value DESC
		""",
		as_dict=True,
	)

	# ── Monthly trend (last 6 months) ─────────────────────────────────────────
	monthly_trend = frappe.db.sql(
		"""
		SELECT DATE_FORMAT(opening_date, '%b %Y') AS label,
			   COUNT(*) AS value,
			   DATE_FORMAT(opening_date, '%Y-%m') AS sort_key
		FROM `tabHD Ticket`
		WHERE opening_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
		GROUP BY DATE_FORMAT(opening_date, '%Y-%m')
		ORDER BY sort_key ASC
		""",
		as_dict=True,
	)

	# ── KPI totals ────────────────────────────────────────────────────────────
	totals = frappe.db.sql(
		"""
		SELECT
			COUNT(*) AS total_tickets,
			SUM(CASE WHEN status IN ('Open','Replied') THEN 1 ELSE 0 END) AS open_tickets,
			SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) AS resolved_tickets,
			SUM(CASE WHEN status = 'Closed' THEN 1 ELSE 0 END) AS closed_tickets,
			SUM(CASE WHEN priority IN ('High','Urgent') THEN 1 ELSE 0 END) AS high_prio_count,
			SUM(CASE WHEN agreement_status = 'Failed' THEN 1 ELSE 0 END) AS sla_breached,
			ROUND(AVG(CASE WHEN first_response_time > 0 THEN first_response_time END) / 3600, 1)
				AS avg_first_response_hrs,
			ROUND(AVG(CASE WHEN resolution_time > 0 THEN resolution_time END) / 3600, 1)
				AS avg_resolution_hrs
		FROM `tabHD Ticket`
		""",
		as_dict=True,
	)[0]

	total = totals.total_tickets or 0
	resolved_pct = round((totals.resolved_tickets or 0) / total * 100, 1) if total else 0
	sla_met = next((x["value"] for x in sla_dist if x["label"] == "Met"), 0)
	sla_total = sum(x["value"] for x in sla_dist if x["label"] in ("Met", "Failed", "Overdue"))
	sla_pct = round(sla_met / sla_total * 100, 1) if sla_total else 0

	return {
		"total_tickets":          total,
		"open_tickets":           totals.open_tickets or 0,
		"resolved_tickets":       totals.resolved_tickets or 0,
		"closed_tickets":         totals.closed_tickets or 0,
		"high_priority":          totals.high_prio_count or 0,
		"sla_breached":           totals.sla_breached or 0,
		"avg_first_response_hrs": totals.avg_first_response_hrs or 0,
		"avg_resolution_hrs":     totals.avg_resolution_hrs or 0,
		"resolved_pct":           resolved_pct,
		"sla_pct":                sla_pct,
		"status_dist":            status_dist,
		"priority_dist":          priority_dist,
		"type_dist":              type_dist,
		"team_dist":              team_dist,
		"sla_dist":               sla_dist,
		"monthly_trend":          monthly_trend,
	}


@frappe.whitelist()
def get_rfid_analytics(**kwargs):
	"""RFID swipe analytics from Attendance Log and Student RFID Card."""
	_require_dashboard_access()

	if not frappe.db.table_exists("Attendance Log") or not frappe.db.table_exists("Student RFID Card"):
		return {
			"total_swipes": 0, "unique_cards": 0, "processed": 0, "unprocessed": 0,
			"active_devices": 0, "active_days": 0, "total_cards": 0, "active_cards": 0,
			"today_swipes": 0, "processing_pct": 0,
			"card_status": [], "location_dist": [], "terminal_dist": [],
			"processing_dist": [], "hourly_dist": [], "monthly_trend": [],
		}

	# ── KPI totals ────────────────────────────────────────────────────────────
	totals = frappe.db.sql(
		"""
		SELECT
			COUNT(*)                                              AS total_swipes,
			COUNT(DISTINCT rfid_uid)                              AS unique_cards,
			SUM(CASE WHEN processed = 1 THEN 1 ELSE 0 END)       AS processed,
			SUM(CASE WHEN processed = 0 THEN 1 ELSE 0 END)       AS unprocessed,
			COUNT(DISTINCT device_id)                             AS active_devices,
			COUNT(DISTINCT DATE(swipe_time))                      AS active_days
		FROM `tabAttendance Log`
		""",
		as_dict=True,
	)[0]

	# ── RFID card status ──────────────────────────────────────────────────────
	card_status = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(card_status,''), 'Unknown') AS label,
		       COUNT(*) AS value
		FROM `tabStudent RFID Card`
		GROUP BY card_status ORDER BY value DESC
		""",
		as_dict=True,
	)

	total_cards   = sum(r["value"] for r in card_status)
	active_cards  = next((r["value"] for r in card_status if r["label"] == "Active"), 0)

	# ── Swipes by location ────────────────────────────────────────────────────
	location_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(location,''), 'Unknown') AS label,
		       COUNT(*) AS value
		FROM `tabAttendance Log`
		GROUP BY location ORDER BY value DESC LIMIT 10
		""",
		as_dict=True,
	)

	# ── Top terminals ─────────────────────────────────────────────────────────
	terminal_dist = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(terminal_alias,''), 'Unknown') AS label,
		       COUNT(*) AS value
		FROM `tabAttendance Log`
		WHERE terminal_alias IS NOT NULL AND terminal_alias != ''
		GROUP BY terminal_alias ORDER BY value DESC LIMIT 10
		""",
		as_dict=True,
	)

	# ── Processing status ─────────────────────────────────────────────────────
	processing_dist = [
		{"label": "Processed",   "value": int(totals.processed or 0)},
		{"label": "Unprocessed", "value": int(totals.unprocessed or 0)},
	]

	# ── Hourly distribution ───────────────────────────────────────────────────
	hourly_dist = frappe.db.sql(
		"""
		SELECT CONCAT(LPAD(HOUR(swipe_time), 2, '0'), ':00') AS label,
		       COUNT(*) AS value
		FROM `tabAttendance Log`
		GROUP BY HOUR(swipe_time) ORDER BY HOUR(swipe_time)
		""",
		as_dict=True,
	)

	# ── Monthly trend (last 12 months) ────────────────────────────────────────
	monthly_trend = frappe.db.sql(
		"""
		SELECT DATE_FORMAT(swipe_time, '%b %Y') AS label,
		       COUNT(*) AS value,
		       DATE_FORMAT(swipe_time, '%Y-%m') AS sort_key
		FROM `tabAttendance Log`
		WHERE swipe_time >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
		GROUP BY DATE_FORMAT(swipe_time, '%Y-%m')
		ORDER BY sort_key ASC
		""",
		as_dict=True,
	)

	# ── Today's swipes ────────────────────────────────────────────────────────
	today_swipes = frappe.db.sql(
		"SELECT COUNT(*) AS cnt FROM `tabAttendance Log` WHERE DATE(swipe_time) = CURDATE()",
		as_dict=True,
	)[0].get("cnt", 0)

	processing_pct = round(
		(totals.processed or 0) / (totals.total_swipes or 1) * 100, 1
	)

	return {
		"total_swipes":     int(totals.total_swipes or 0),
		"unique_cards":     int(totals.unique_cards or 0),
		"processed":        int(totals.processed or 0),
		"unprocessed":      int(totals.unprocessed or 0),
		"active_devices":   int(totals.active_devices or 0),
		"active_days":      int(totals.active_days or 0),
		"total_cards":      total_cards,
		"active_cards":     active_cards,
		"today_swipes":     int(today_swipes or 0),
		"processing_pct":   processing_pct,
		"card_status":      card_status,
		"location_dist":    location_dist,
		"terminal_dist":    terminal_dist,
		"processing_dist":  processing_dist,
		"hourly_dist":      hourly_dist,
		"monthly_trend":    monthly_trend,
	}


@frappe.whitelist()
def get_drilldown_data(module, dimension, value, academic_year=None, term=None, program=None,
					   cohort=None, student_status=None, page=1, page_size=25):
	"""Generic drilldown — returns a detailed record list for chart click-throughs."""
	_require_dashboard_access()
	page     = int(page)
	page_size = int(page_size)
	offset   = (page - 1) * page_size

	# ── Students ──────────────────────────────────────────────────────────────
	if module == "students":
		if dimension == "student_status":
			filters = {"student_status": value}
			if academic_year:
				filters["academic_year"] = academic_year
			rows = frappe.db.get_all(
				"Student Master", filters=filters,
				fields=["name", "registration_id", "first_name", "last_name", "programme",
						"academic_year", "gender", "student_status", "email", "phone"],
				limit_start=offset, limit_page_length=page_size, order_by="registration_id asc",
			)
			total = frappe.db.count("Student Master", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["registration_id", "first_name", "last_name", "programme",
								"academic_year", "gender", "student_status"]}

		elif dimension == "gender":
			filters = {"gender": value}
			if academic_year:
				filters["academic_year"] = academic_year
			rows = frappe.db.get_all(
				"Student Master", filters=filters,
				fields=["name", "registration_id", "first_name", "last_name", "programme",
						"gender", "student_status", "academic_year"],
				limit_start=offset, limit_page_length=page_size, order_by="registration_id asc",
			)
			total = frappe.db.count("Student Master", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["registration_id", "first_name", "last_name",
								"programme", "gender", "student_status"]}

		elif dimension == "program":
			rows = frappe.db.sql(
				"""
				SELECT sm.name, sm.registration_id, sm.first_name, sm.last_name,
					   p.program_name, sm.academic_year, sm.student_status
				FROM `tabStudent Master` sm
				LEFT JOIN `tabBatch` c ON c.name = sm.programme
				LEFT JOIN `tabProgramme` p ON p.name = c.program
				WHERE p.program_name = %(value)s OR c.program = %(value)s
				ORDER BY sm.registration_id ASC
				LIMIT %(limit)s OFFSET %(offset)s
				""",
				{"value": value, "limit": page_size, "offset": offset}, as_dict=True,
			)
			cnt = frappe.db.sql(
				"""
				SELECT COUNT(*) FROM `tabStudent Master` sm
				LEFT JOIN `tabBatch` c ON c.name = sm.programme
				LEFT JOIN `tabProgramme` p ON p.name = c.program
				WHERE p.program_name = %(value)s OR c.program = %(value)s
				""",
				{"value": value},
			)
			total = cnt[0][0] if cnt else 0
			return {"rows": rows, "total": total,
					"columns": ["registration_id", "first_name", "last_name",
								"program_name", "academic_year", "student_status"]}

		elif dimension == "programs_list":
			rows = frappe.db.sql(
				"""
				SELECT p.program_name AS label, p.name AS program_id,
					   COUNT(sm.name) AS total_students,
					   SUM(CASE WHEN sm.student_status='Active' THEN 1 ELSE 0 END) AS active,
					   SUM(CASE WHEN sm.student_status='Graduated' THEN 1 ELSE 0 END) AS graduated
				FROM `tabProgramme` p
				LEFT JOIN `tabBatch` c ON c.program = p.name
				LEFT JOIN `tabStudent Master` sm ON sm.programme = c.name
				GROUP BY p.name
				HAVING total_students > 0
				ORDER BY total_students DESC
				LIMIT %(limit)s OFFSET %(offset)s
				""",
				{"limit": page_size, "offset": offset}, as_dict=True,
			)
			total = frappe.db.sql("""
				SELECT COUNT(*) FROM (
					SELECT p.name
					FROM `tabProgramme` p
					LEFT JOIN `tabBatch` c ON c.program = p.name
					LEFT JOIN `tabStudent Master` sm ON sm.programme = c.name
					GROUP BY p.name
					HAVING COUNT(sm.name) > 0
				) sub
			""")[0][0]
			return {"rows": rows, "total": total,
					"columns": ["label", "total_students", "active", "graduated"]}

		elif dimension == "cohorts_list":
			rows = frappe.db.sql(
				"""
				SELECT c.cohort_name AS label, c.name AS cohort_id,
					   p.program_name, c.section, c.status,
					   COUNT(sm.name) AS total_students
				FROM `tabBatch` c
				LEFT JOIN `tabProgramme` p ON p.name = c.program
				LEFT JOIN `tabStudent Master` sm ON sm.programme = c.name
				GROUP BY c.name
				HAVING total_students > 0
				ORDER BY total_students DESC
				LIMIT %(limit)s OFFSET %(offset)s
				""",
				{"limit": page_size, "offset": offset}, as_dict=True,
			)
			total = frappe.db.sql("""
				SELECT COUNT(*) FROM (
					SELECT c.name
					FROM `tabBatch` c
					LEFT JOIN `tabStudent Master` sm ON sm.programme = c.name
					GROUP BY c.name
					HAVING COUNT(sm.name) > 0
				) sub
			""")[0][0]
			return {"rows": rows, "total": total,
					"columns": ["label", "program_name", "section", "status", "total_students"]}

		elif dimension == "cohort":
			cohort_id = frappe.db.get_value("Batch", {"cohort_name": value}, "name") or value
			rows = frappe.db.sql(
				"""
				SELECT sm.name, sm.registration_id, sm.first_name, sm.last_name,
					   c.cohort_name AS cohort, p.program_name,
					   sm.academic_year, sm.student_status, sm.gender
				FROM `tabStudent Master` sm
				LEFT JOIN `tabBatch` c ON c.name = sm.programme
				LEFT JOIN `tabProgramme` p ON p.name = c.program
				WHERE sm.programme = %(cohort_id)s OR c.cohort_name = %(value)s
				ORDER BY sm.registration_id ASC
				LIMIT %(limit)s OFFSET %(offset)s
				""",
				{"cohort_id": cohort_id, "value": value, "limit": page_size, "offset": offset},
				as_dict=True,
			)
			cnt = frappe.db.sql(
				"""
				SELECT COUNT(*) FROM `tabStudent Master` sm
				LEFT JOIN `tabBatch` c ON c.name = sm.programme
				WHERE sm.programme = %(cohort_id)s OR c.cohort_name = %(value)s
				""",
				{"cohort_id": cohort_id, "value": value},
			)
			total = cnt[0][0] if cnt else 0
			return {"rows": rows, "total": total,
					"columns": ["registration_id", "first_name", "last_name",
								"cohort", "program_name", "academic_year", "student_status"]}

		elif dimension == "reg_status":
			filters = {}
			if value and value not in ("all", "All"):
				filters["registration_status"] = value
			if academic_year:
				filters["academic_year"] = academic_year
			rows = frappe.db.get_all(
				"Student Master", filters=filters,
				fields=["name", "registration_id", "first_name", "last_name", "programme",
						"academic_year", "registration_status", "student_status", "email"],
				limit_start=offset, limit_page_length=page_size, order_by="registration_id asc",
			)
			total = frappe.db.count("Student Master", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["registration_id", "first_name", "last_name",
								"programme", "academic_year", "registration_status", "student_status"]}

	# ── Attendance ────────────────────────────────────────────────────────────
	elif module == "attendance":
		if dimension in ("status", "session_type", "source"):
			att_filters = {}
			field_map = {"status": "status", "session_type": "session_type", "source": "source"}
			if value and value not in ("all", "All"):
				att_filters[field_map[dimension]] = value
			if academic_year:
				att_filters["academic_year"] = academic_year
			if program:
				att_filters["program"] = program
			if term:
				att_filters["academic_term"] = term

			rows = frappe.db.get_all(
				"Student Attendance", filters=att_filters,
				fields=["name", "student", "student_name", "attendance_date", "status",
						"course", "program", "academic_term", "session_type", "source"],
				limit_start=offset, limit_page_length=page_size,
				order_by="attendance_date desc",
			)
			total = frappe.db.count("Student Attendance", filters=att_filters)
			return {"rows": rows, "total": total,
					"columns": ["student_name", "attendance_date", "status",
								"course", "program", "session_type", "source"]}

		elif dimension == "condonation":
			cond_filters = {}
			if value and value not in ("all", "All"):
				cond_filters["final_status"] = value
			rows = frappe.db.get_all(
				"Student Attendance Condonation", filters=cond_filters,
				fields=["name", "student", "student_name", "course_offering", "course",
						"academic_year", "faculty_recommendation", "final_status",
						"number_of_sessions", "condonation_reason"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("Student Attendance Condonation", filters=cond_filters)
			return {"rows": rows, "total": total,
					"columns": ["student_name", "course", "academic_year",
								"faculty_recommendation", "final_status", "number_of_sessions"]}

		elif dimension == "cond_faculty":
			cond_filters = {}
			if value and value not in ("all", "All"):
				cond_filters["faculty_recommendation"] = value
			rows = frappe.db.get_all(
				"Student Attendance Condonation", filters=cond_filters,
				fields=["name", "student", "student_name", "course", "academic_year",
						"faculty_recommendation", "final_status", "number_of_sessions"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("Student Attendance Condonation", filters=cond_filters)
			return {"rows": rows, "total": total,
					"columns": ["student_name", "course", "academic_year",
								"faculty_recommendation", "final_status", "number_of_sessions"]}

		elif dimension in ("fa_mfa", "fa_mfa_type"):
			famfa_filters = {}
			if dimension == "fa_mfa" and value and value not in ("all", "All"):
				famfa_filters["status"] = value
			elif dimension == "fa_mfa_type" and value and value not in ("all", "All"):
				famfa_filters["application_type"] = value
			rows = frappe.db.get_all(
				"FA MFA Application", filters=famfa_filters,
				fields=["name", "student", "student_name", "course", "application_type",
						"reason", "status", "examination_date"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("FA MFA Application", filters=famfa_filters)
			return {"rows": rows, "total": total,
					"columns": ["student_name", "course", "application_type",
								"reason", "status", "examination_date"]}

	# ── Examination ──────────────────────────────────────────────────────────
	elif module == "examination":
		if dimension == "grade":
			cond = "WHERE scm.grade = %(grade)s AND scm.status = 'Submitted'"
			params = {"grade": value, "limit": page_size, "offset": offset}
			rows = frappe.db.sql(
				f"""
				SELECT scm.name, scm.student, COALESCE(c.course_name, scm.course) AS course_name,
				       scm.grade, scm.total_marks, scm.enrollment_status,
				       COALESCE(ep.exam_name, scm.exam_plan) AS exam_plan
				FROM `tabStudent Course Marks` scm
				LEFT JOIN `tabCourse` c ON c.name = scm.course
				LEFT JOIN `tabExam Plan` ep ON ep.name = scm.exam_plan
				{cond}
				ORDER BY scm.student ASC
				LIMIT %(limit)s OFFSET %(offset)s
				""",
				params, as_dict=True,
			)
			total = frappe.db.sql(
				f"SELECT COUNT(*) FROM `tabStudent Course Marks` scm {cond}",
				params
			)[0][0]
			return {"rows": rows, "total": total,
					"columns": ["student", "course_name", "grade", "total_marks",
								"enrollment_status", "exam_plan"]}

		elif dimension == "marks_status":
			cond = ""
			params = {"limit": page_size, "offset": offset}
			if value and value != "all":
				cond = "WHERE scm.status = %(status)s"
				params["status"] = value
			rows = frappe.db.sql(
				f"""
				SELECT scm.name, scm.student, COALESCE(c.course_name, scm.course) AS course_name,
				       scm.grade, scm.total_marks, scm.status, scm.enrollment_status,
				       COALESCE(ep.exam_name, scm.exam_plan) AS exam_plan
				FROM `tabStudent Course Marks` scm
				LEFT JOIN `tabCourse` c ON c.name = scm.course
				LEFT JOIN `tabExam Plan` ep ON ep.name = scm.exam_plan
				{cond}
				ORDER BY scm.student ASC
				LIMIT %(limit)s OFFSET %(offset)s
				""",
				params, as_dict=True,
			)
			total = frappe.db.sql(
				f"SELECT COUNT(*) FROM `tabStudent Course Marks` scm {cond}",
				params
			)[0][0]
			return {"rows": rows, "total": total,
					"columns": ["student", "course_name", "grade", "total_marks",
								"status", "enrollment_status", "exam_plan"]}

		elif dimension == "exam_plans":
			ep_filters = {}
			if value and value != "all":
				ep_filters["status"] = value
			if term:
				ep_filters["term"] = term
			rows = frappe.db.get_all(
				"Exam Plan", filters=ep_filters,
				fields=["name", "exam_name", "term", "status"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			for r in rows:
				r["enrolled_students"] = frappe.db.count(
					"Student Course Marks", filters={"exam_plan": r["name"]}
				)
			total = frappe.db.count("Exam Plan", filters=ep_filters)
			return {"rows": rows, "total": total,
					"columns": ["exam_name", "term", "status", "enrolled_students"]}

		elif dimension == "fairness":
			filters = {"status": "Submitted"}
			if value and value not in ("all", "All"):
				filters["fairness_status"] = value
			rows = frappe.db.get_all(
				"Student Course Marks", filters=filters,
				fields=["name", "student", "course", "grade", "total_marks",
						"fairness_status", "enrollment_status", "exam_plan"],
				limit_start=offset, limit_page_length=page_size, order_by="student asc",
			)
			total = frappe.db.count("Student Course Marks", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "course", "grade", "total_marks",
								"fairness_status", "enrollment_status", "exam_plan"]}

		elif dimension == "att_marks":
			filters = {}
			if value and value not in ("all", "All"):
				filters["attendance_status"] = value
			rows = frappe.db.get_all(
				"Student Course Marks", filters=filters,
				fields=["name", "student", "course", "attendance_status", "grade",
						"total_marks", "enrollment_status", "exam_plan"],
				limit_start=offset, limit_page_length=page_size, order_by="student asc",
			)
			total = frappe.db.count("Student Course Marks", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "course", "attendance_status", "grade",
								"total_marks", "enrollment_status"]}

		elif dimension == "mfa":
			mfa_val = "Yes" if value == "MFA Granted" else ("No" if value == "No MFA" else None)
			filters = {"status": "Submitted"}
			if mfa_val:
				filters["mfa"] = mfa_val
			rows = frappe.db.get_all(
				"Student Course Marks", filters=filters,
				fields=["name", "student", "course", "mfa", "grade", "total_marks",
						"enrollment_status", "exam_plan"],
				limit_start=offset, limit_page_length=page_size, order_by="student asc",
			)
			total = frappe.db.count("Student Course Marks", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "course", "mfa", "grade",
								"total_marks", "enrollment_status"]}

		elif dimension in ("reexam", "reexam_payment"):
			filters = {}
			if dimension == "reexam" and value and value not in ("all", "All"):
				filters["status"] = value
			elif dimension == "reexam_payment" and value and value not in ("all", "All"):
				filters["payment_status"] = value
			rows = frappe.db.get_all(
				"Re Exam Registration", filters=filters,
				fields=["name", "student", "exam_plan", "course",
						"status", "payment_status"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("Re Exam Registration", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "exam_plan", "course",
								"status", "payment_status"]}

		elif dimension in ("improvement", "improvement_payment"):
			filters = {}
			if dimension == "improvement" and value and value not in ("all", "All"):
				filters["status"] = value
			elif dimension == "improvement_payment" and value and value not in ("all", "All"):
				filters["payment_status"] = value
			rows = frappe.db.get_all(
				"Improvement Exam Registration", filters=filters,
				fields=["name", "student", "exam_plan", "course",
						"status", "payment_status"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("Improvement Exam Registration", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "exam_plan", "course",
								"status", "payment_status"]}

		elif dimension in ("grade_appeal_status", "grade_appeal_type"):
			filters = {}
			if dimension == "grade_appeal_status" and value and value not in ("all", "All"):
				filters["status"] = value
			elif dimension == "grade_appeal_type" and value and value not in ("all", "All"):
				filters["appeal_type"] = value
			rows = frappe.db.get_all(
				"Grade Appeal", filters=filters,
				fields=["name", "student", "exam_plan", "course",
						"appeal_type", "status"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("Grade Appeal", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "exam_plan", "course",
								"appeal_type", "status"]}

		elif dimension in ("transcript_status", "transcript_type"):
			filters = {}
			if dimension == "transcript_status" and value and value not in ("all", "All"):
				filters["status"] = value
			elif dimension == "transcript_type" and value and value not in ("all", "All"):
				filters["transcript_type"] = value
			rows = frappe.db.get_all(
				"Student Transcript", filters=filters,
				fields=["name", "student", "student_name", "transcript_type",
						"status", "generation_date"],
				limit_start=offset, limit_page_length=page_size, order_by="generation_date desc",
			)
			total = frappe.db.count("Student Transcript", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student_name", "transcript_type",
								"status", "generation_date"]}

		elif dimension == "result_publish":
			rp_filters = {}
			if value == "published":
				rp_filters["is_published"] = 1
			elif value == "unpublished":
				rp_filters["is_published"] = 0
			rows = frappe.db.get_all(
				"Student Result Publish", filters=rp_filters,
				fields=["name", "student", "exam_plan", "is_published",
						"term_gpa", "cumulative_gpa", "published_on"],
				limit_start=offset, limit_page_length=page_size,
				order_by="published_on desc",
			)
			total = frappe.db.count("Student Result Publish", filters=rp_filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "exam_plan", "is_published",
								"term_gpa", "cumulative_gpa", "published_on"]}

		elif dimension == "exam_status":
			ep_filters = {}
			if value and value not in ("all", "All"):
				ep_filters["status"] = value
			rows = frappe.db.get_all(
				"Exam Plan", filters=ep_filters,
				fields=["name", "exam_name", "term", "status"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("Exam Plan", filters=ep_filters)
			return {"rows": rows, "total": total,
					"columns": ["exam_name", "term", "status"]}

		elif dimension == "enrollment_status":
			filters = {"status": "Submitted"}
			if value and value not in ("all", "All"):
				filters["enrollment_status"] = value
			rows = frappe.db.get_all(
				"Student Course Marks", filters=filters,
				fields=["name", "student", "course", "grade", "total_marks",
						"enrollment_status", "exam_plan"],
				limit_start=offset, limit_page_length=page_size, order_by="student asc",
			)
			total = frappe.db.count("Student Course Marks", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "course", "grade", "total_marks",
								"enrollment_status", "exam_plan"]}

	# ── Fees ──────────────────────────────────────────────────────────────────
	elif module == "fees":
		if dimension == "payment_status":
			fi_filters = {}
			if value and value not in ("all", "All"):
				fi_filters["status"] = value
			if academic_year:
				fi_filters["academic_year"] = academic_year
			if program:
				fi_filters["program"] = program
			rows = frappe.db.get_all(
				"Fee Invoice", filters=fi_filters,
				fields=["name", "student", "student_name", "program",
						"total_amount", "paid_amount", "outstanding_amount",
						"status", "invoice_date"],
				limit_start=offset, limit_page_length=page_size, order_by="invoice_date desc",
			)
			total = frappe.db.count("Fee Invoice", filters=fi_filters)
			return {"rows": rows, "total": total,
					"columns": ["name", "student_name", "program", "total_amount",
								"paid_amount", "outstanding_amount", "status"]}

		elif dimension == "students_billed":
			rows = frappe.db.sql(
				"""
				SELECT fi.student,
					   sm.registration_id,
					   CONCAT_WS(' ', sm.first_name, sm.last_name) AS student_name,
					   fi.program,
					   COALESCE(SUM(fi.total_amount),      0) AS total_billed,
					   COALESCE(SUM(fi.paid_amount),       0) AS total_paid,
					   COALESCE(SUM(fi.outstanding_amount),0) AS outstanding,
					   COUNT(fi.name) AS invoice_count
				FROM `tabFee Invoice` fi
				LEFT JOIN `tabStudent Master` sm ON sm.name = fi.student
				GROUP BY fi.student
				ORDER BY outstanding DESC
				LIMIT %(limit)s OFFSET %(offset)s
				""",
				{"limit": page_size, "offset": offset}, as_dict=True,
			)
			total = frappe.db.count("Fee Invoice")
			return {"rows": rows, "total": total,
					"columns": ["registration_id", "student_name", "program",
								"total_billed", "total_paid", "outstanding", "invoice_count"]}

	# ── Hostel ────────────────────────────────────────────────────────────────
	elif module == "hostel":
		if dimension in ("hostel", "active_allocations"):
			ha_filters = {"is_active": 1}
			if dimension == "hostel" and value and value != "all":
				ha_filters["hostel"] = value
			rows = frappe.db.get_all(
				"Hostel Allocation", filters=ha_filters,
				fields=["student", "hostel", "room", "bed", "from_date", "to_date", "status"],
				limit_start=offset, limit_page_length=page_size,
				order_by="hostel asc, room asc",
			)
			total = frappe.db.count("Hostel Allocation", filters=ha_filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "hostel", "room", "bed", "from_date", "status"]}

		elif dimension == "all_beds":
			rows = frappe.db.get_all(
				"Hostel Bed",
				fields=["name", "hostel", "room", "bed_number", "is_occupied"],
				limit_start=offset, limit_page_length=page_size,
				order_by="hostel asc, room asc",
			)
			total = frappe.db.count("Hostel Bed")
			return {"rows": rows, "total": total,
					"columns": ["name", "hostel", "room", "bed_number", "is_occupied"]}

		elif dimension == "available_beds":
			rows = frappe.db.sql(
				"""
				SELECT hb.name, hb.hostel, hb.room, hb.bed_number
				FROM `tabHostel Bed` hb
				WHERE NOT EXISTS (
					SELECT 1 FROM `tabHostel Allocation` ha
					WHERE ha.bed = hb.name AND ha.is_active = 1
				)
				ORDER BY hb.hostel ASC, hb.room ASC
				LIMIT %(limit)s OFFSET %(offset)s
				""",
				{"limit": page_size, "offset": offset}, as_dict=True,
			)
			total_cnt = frappe.db.sql(
				"""
				SELECT COUNT(*) FROM `tabHostel Bed` hb
				WHERE NOT EXISTS (
					SELECT 1 FROM `tabHostel Allocation` ha
					WHERE ha.bed = hb.name AND ha.is_active = 1
				)
				"""
			)
			total = total_cnt[0][0] if total_cnt else 0
			return {"rows": rows, "total": total,
					"columns": ["name", "hostel", "room", "bed_number"]}

	# ── Programme Management ─────────────────────────────────────────────────
	elif module == "programme":
		if dimension == "program_status":
			filters = {}
			if value and value not in ("all", "All"):
				filters["program_status"] = value
			rows = frappe.db.get_all(
				"Programme", filters=filters,
				fields=["name", "program_name", "program_shortcode", "department",
						"level_of_study", "program_status"],
				limit_start=offset, limit_page_length=page_size, order_by="program_name asc",
			)
			total = frappe.db.count("Programme", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["program_name", "program_shortcode", "department",
								"level_of_study", "program_status"]}

		elif dimension == "level_of_study":
			filters = {}
			if value and value not in ("all", "All"):
				filters["level_of_study"] = value
			rows = frappe.db.get_all(
				"Programme", filters=filters,
				fields=["name", "program_name", "department", "level_of_study", "program_status"],
				limit_start=offset, limit_page_length=page_size, order_by="program_name asc",
			)
			total = frappe.db.count("Programme", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["program_name", "department", "level_of_study", "program_status"]}

		elif dimension == "department":
			dept_id = frappe.db.get_value("Department", {"department_name": value}, "name") or value
			filters = {"department": dept_id}
			rows = frappe.db.get_all(
				"Programme", filters=filters,
				fields=["name", "program_name", "level_of_study", "program_status"],
				limit_start=offset, limit_page_length=page_size, order_by="program_name asc",
			)
			total = frappe.db.count("Programme", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["program_name", "level_of_study", "program_status"]}

		elif dimension == "cohort_status":
			filters = {}
			if value and value not in ("all", "All"):
				filters["status"] = value
			rows = frappe.db.get_all(
				"Batch", filters=filters,
				fields=["name", "cohort_name", "program", "section", "academic_year",
						"status", "seat_limit", "start_date", "end_date"],
				limit_start=offset, limit_page_length=page_size, order_by="start_date desc",
			)
			total = frappe.db.count("Batch", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["cohort_name", "program", "section", "academic_year",
								"status", "seat_limit"]}

		elif dimension == "enrollment_status":
			filters = {}
			if value and value not in ("all", "All"):
				filters["status"] = value
			if academic_year:
				filters["academic_year"] = academic_year
			if program:
				filters["program"] = program
			rows = frappe.db.get_all(
				"Student Enrollment", filters=filters,
				fields=["name", "student", "student_name", "batch as cohort", "program",
						"academic_year", "status", "enrollment_date"],
				limit_start=offset, limit_page_length=page_size, order_by="enrollment_date desc",
			)
			total = frappe.db.count("Student Enrollment", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student_name", "cohort", "program", "academic_year",
								"status", "enrollment_date"]}

		elif dimension == "program_enrollment":
			prog_id = frappe.db.get_value("Programme", {"program_name": value}, "name") or value
			filters = {"program": prog_id}
			if academic_year:
				filters["academic_year"] = academic_year
			rows = frappe.db.get_all(
				"Student Enrollment", filters=filters,
				fields=["name", "student", "student_name", "batch as cohort", "program",
						"academic_year", "status", "enrollment_date"],
				limit_start=offset, limit_page_length=page_size, order_by="enrollment_date desc",
			)
			total = frappe.db.count("Student Enrollment", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student_name", "cohort", "program", "academic_year",
								"status", "enrollment_date"]}

		elif dimension == "cohort_enrollment":
			cohort_id = frappe.db.get_value("Batch", {"cohort_name": value}, "name") or value
			filters = {"batch": cohort_id}
			rows = frappe.db.get_all(
				"Student Enrollment", filters=filters,
				fields=["name", "student", "student_name", "batch as cohort", "program",
						"academic_year", "status", "enrollment_date"],
				limit_start=offset, limit_page_length=page_size, order_by="enrollment_date desc",
			)
			total = frappe.db.count("Student Enrollment", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student_name", "cohort", "program", "academic_year",
								"status", "enrollment_date"]}

		elif dimension == "offering_status":
			filters = {}
			if value and value not in ("all", "All"):
				filters["status"] = value
			if academic_year:
				filters["academic_year"] = academic_year
			if program:
				filters["program"] = program
			rows = frappe.db.get_all(
				"Course Offering", filters=filters,
				fields=["name", "course_name", "program", "cohort", "faculty",
						"academic_year", "status"],
				limit_start=offset, limit_page_length=page_size, order_by="course_name asc",
			)
			total = frappe.db.count("Course Offering", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["course_name", "program", "cohort", "faculty",
								"academic_year", "status"]}

		elif dimension == "offering_program":
			prog_id = frappe.db.get_value("Programme", {"program_name": value}, "name") or value
			filters = {"program": prog_id}
			if academic_year:
				filters["academic_year"] = academic_year
			rows = frappe.db.get_all(
				"Course Offering", filters=filters,
				fields=["name", "course_name", "cohort", "faculty",
						"academic_year", "status"],
				limit_start=offset, limit_page_length=page_size, order_by="course_name asc",
			)
			total = frappe.db.count("Course Offering", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["course_name", "cohort", "faculty",
								"academic_year", "status"]}

		elif dimension == "course_enroll_status":
			filters = {}
			if value and value not in ("all", "All"):
				filters["status"] = value
			rows = frappe.db.get_all(
				"Student Enrollment Course", filters=filters,
				fields=["name", "course_offering", "course", "status", "parent"],
				limit_start=offset, limit_page_length=page_size, order_by="parent asc",
			)
			total = frappe.db.count("Student Enrollment Course", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["parent", "course", "course_offering", "status"]}

	# ── Placement ─────────────────────────────────────────────────────────────
	elif module == "placement":
		if dimension == "company":
			rows = frappe.db.sql(
				"""
				SELECT pof.student, pof.opportunity, pof.offered_role,
					   pof.compensation, pof.status,
					   COALESCE(c.company_name, po.company) AS company_name
				FROM `tabPlacement Offer` pof
				LEFT JOIN `tabPlacement Opportunity` po ON po.name = pof.opportunity
				LEFT JOIN `tabCompany` c ON c.name = po.company
				WHERE po.company = %(value)s OR c.company_name = %(value)s
				LIMIT %(limit)s OFFSET %(offset)s
				""",
				{"value": value, "limit": page_size, "offset": offset}, as_dict=True,
			)
			total = len(rows)
			return {"rows": rows, "total": total,
					"columns": ["student", "company_name", "offered_role",
								"compensation", "status"]}

		elif dimension == "status":
			filters = {}
			if value and value != "all":
				filters["status"] = value
			rows = frappe.db.get_all(
				"Placement Offer", filters=filters,
				fields=["student", "opportunity", "offered_role", "location",
						"compensation", "status", "decision_date"],
				limit_start=offset, limit_page_length=page_size, order_by="decision_date desc",
			)
			total = frappe.db.count("Placement Offer", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "opportunity", "offered_role",
								"location", "compensation", "status"]}

		elif dimension == "status":
			filters = {}
			if value and value != "all":
				filters["status"] = value
			rows = frappe.db.get_all(
				"Placement Application", filters=filters,
				fields=["student", "opportunity", "status", "applied_on", "remarks"],
				limit_start=offset, limit_page_length=page_size, order_by="applied_on desc",
			)
			total = frappe.db.count("Placement Application", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "opportunity", "status", "applied_on"]}

		elif dimension == "opportunity_status":
			opp_filters = {}
			if value and value != "all":
				opp_filters["status"] = value
			rows = frappe.db.get_all(
				"Placement Opportunity", filters=opp_filters,
				fields=["name", "company", "opportunity_type", "compensation",
						"location", "status", "application_start", "application_end"],
				limit_start=offset, limit_page_length=page_size, order_by="application_start desc",
			)
			# Enrich with applicant count
			for r in rows:
				r["applicants"] = frappe.db.count(
					"Placement Application", filters={"opportunity": r["name"]}
				)
			total = frappe.db.count("Placement Opportunity", filters=opp_filters)
			return {"rows": rows, "total": total,
					"columns": ["name", "company", "opportunity_type", "compensation",
								"location", "status", "applicants"]}

	# ── Admission ─────────────────────────────────────────────────────────────
	elif module == "admission":
		if dimension == "app_status":
			aa_filters = {}
			if value and value not in ("all", "All"):
				aa_filters["status"] = value
			if program:
				aa_filters["program"] = program
			rows = frappe.db.get_all(
				"Admission Application", filters=aa_filters,
				fields=["name", "applicant", "program", "status", "eligibility_status",
						"test_result_status", "interview_status", "admission_cycle"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("Admission Application", filters=aa_filters)
			return {"rows": rows, "total": total,
					"columns": ["name", "applicant", "program", "status",
								"eligibility_status", "test_result_status", "interview_status"]}

		elif dimension == "status":
			ol_filters = {}
			if value and value not in ("all", "All"):
				ol_filters["status"] = value
			rows = frappe.db.get_all(
				"Offer Letter", filters=ol_filters,
				fields=["name", "applicant", "program", "status", "creation"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("Offer Letter", filters=ol_filters)
			return {"rows": rows, "total": total,
					"columns": ["name", "applicant", "program", "status", "creation"]}

		elif dimension == "cycle_status":
			cy_filters = {}
			if value and value not in ("all", "All"):
				cy_filters["status"] = value
			rows = frappe.db.get_all(
				"Admission Cycle", filters=cy_filters,
				fields=["name", "cycle_name", "academic_year", "status",
						"cycle_start_date", "cycle_end_date"],
				limit_start=offset, limit_page_length=page_size,
				order_by="cycle_start_date desc",
			)
			total = frappe.db.count("Admission Cycle", filters=cy_filters)
			return {"rows": rows, "total": total,
					"columns": ["cycle_name", "academic_year", "status",
								"cycle_start_date", "cycle_end_date"]}

		elif dimension == "merit_status":
			ml_filters = {}
			if value and value not in ("all", "All"):
				ml_filters["status"] = value
			rows = frappe.db.get_all(
				"Merit List", filters=ml_filters,
				fields=["name", "admission_cycle", "campus", "program_level",
						"status", "generated_on"],
				limit_start=offset, limit_page_length=page_size, order_by="generated_on desc",
			)
			total = frappe.db.count("Merit List", filters=ml_filters)
			return {"rows": rows, "total": total,
					"columns": ["name", "admission_cycle", "campus",
								"program_level", "status", "generated_on"]}

		elif dimension == "app_program":
			aa_filters = {}
			if value and value not in ("all", "All"):
				# value may be program_name; resolve to program id
				prog_id = frappe.db.get_value("Programme", {"program_name": value}, "name") or value
				aa_filters["program"] = prog_id
			rows = frappe.db.get_all(
				"Admission Application", filters=aa_filters,
				fields=["name", "applicant", "program", "status", "admission_cycle"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("Admission Application", filters=aa_filters)
			return {"rows": rows, "total": total,
					"columns": ["name", "applicant", "program", "status", "admission_cycle"]}

		elif dimension in ("eligibility_status", "test_result_status",
							"interview_status", "app_fee_status"):
			field_map = {
				"eligibility_status":  "eligibility_status",
				"test_result_status":  "test_result_status",
				"interview_status":    "interview_status",
			}
			if dimension == "app_fee_status":
				appl_filters = {}
				if value and value not in ("all", "All"):
					appl_filters["application_fee_status"] = value
				rows = frappe.db.get_all(
					"Applicant", filters=appl_filters,
					fields=["name", "application_fee_status", "creation"],
					limit_start=offset, limit_page_length=page_size, order_by="creation desc",
				)
				total = frappe.db.count("Applicant", filters=appl_filters)
				return {"rows": rows, "total": total,
						"columns": ["name", "application_fee_status", "creation"]}
			else:
				aa_filters = {}
				field = field_map[dimension]
				if value and value not in ("all", "All"):
					aa_filters[field] = value
				rows = frappe.db.get_all(
					"Admission Application", filters=aa_filters,
					fields=["name", "applicant", "program", "status", field],
					limit_start=offset, limit_page_length=page_size, order_by="creation desc",
				)
				total = frappe.db.count("Admission Application", filters=aa_filters)
				return {"rows": rows, "total": total,
						"columns": ["name", "applicant", "program", "status", field]}

	# ── ID Card ───────────────────────────────────────────────────────────────
	elif module == "idcard":
		filters = {}
		if dimension == "card_status" and value and value not in ("all", "All"):
			filters["card_status"] = value
		elif dimension == "card_type" and value and value not in ("all", "All"):
			filters["card_type"] = value
		elif dimension == "dept":
			dept_id = frappe.db.get_value("Department", {"department_name": value}, "name") or value
			filters["department"] = dept_id
		elif dimension == "program":
			cohort_id = frappe.db.get_value("Batch", {"cohort_name": value}, "name") or value
			filters["program"] = cohort_id

		rows = frappe.db.get_all(
			"ID Card Generation", filters=filters,
			fields=["name", "student", "student_name", "card_type", "card_status",
					"department", "program", "issue_date", "expiry_date", "print_count"],
			limit_start=offset, limit_page_length=page_size, order_by="creation desc",
		)
		total = frappe.db.count("ID Card Generation", filters=filters)
		return {"rows": rows, "total": total,
				"columns": ["name", "student_name", "card_type", "card_status",
							"department", "issue_date", "expiry_date", "print_count"]}

	# ── Venue Booking ──────────────────────────────────────────────────────────
	elif module == "venue":
		filters = {}
		if dimension == "booking_status" and value and value not in ("all", "All"):
			filters["status"] = value
		elif dimension == "venue_type" and value and value not in ("all", "All"):
			filters["venue_type"] = value
		elif dimension == "requester_type" and value and value not in ("all", "All"):
			filters["requester_type"] = value
		elif dimension == "room" and value and value not in ("all", "All"):
			filters["room"] = value

		rows = frappe.db.get_all(
			"Venue Booking", filters=filters,
			fields=["name", "event_name", "venue_type", "room", "requester_type",
					"requester_name", "start_datetime", "end_datetime",
					"status", "expected_attendees"],
			limit_start=offset, limit_page_length=page_size, order_by="start_datetime desc",
		)
		total = frappe.db.count("Venue Booking", filters=filters)
		return {"rows": rows, "total": total,
				"columns": ["event_name", "venue_type", "room", "requester_type",
							"requester_name", "start_datetime", "status", "expected_attendees"]}

	# ── Promotion ──────────────────────────────────────────────────────────────
	elif module == "promotion":
		if dimension == "policy_status":
			filters = {}
			if value and value not in ("all", "All"):
				filters["status"] = value
			rows = frappe.db.get_all(
				"Promotion Policy", filters=filters,
				fields=["name", "title", "program", "academic_year", "status",
						"from_year", "to_year"],
				limit_start=offset, limit_page_length=page_size, order_by="creation desc",
			)
			total = frappe.db.count("Promotion Policy", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["title", "program", "academic_year", "status",
								"from_year", "to_year"]}

		else:
			filters = {}
			field_map = {
				"promotion_status": "promotion_status",
				"override":         "promotion_status",
				"cgpa_result":      "cgpa_result",
				"backlog_result":   "backlog_result",
				"attendance_result":"attendance_result",
				"shortage_result":  "shortage_course_result",
			}
			field = field_map.get(dimension, "promotion_status")
			if value and value not in ("all", "All"):
				filters[field] = value
			if dimension == "override":
				filters["manual_override"] = 1
			if cohort:
				filters["programme"] = cohort
			filters["stage"] = "Published"

			rows = frappe.db.get_all(
				"Student Promotion", filters=filters,
				fields=["name", "student", "student_name", "programme", "promotion_policy",
						"current_year", "target_year", "promotion_status",
						"current_cgpa", "backlog_count", "attendance_percent",
						"manual_override"],
				limit_start=offset, limit_page_length=page_size, order_by="processed_on desc",
			)
			total = frappe.db.count("Student Promotion", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student_name", "programme", "current_year", "target_year",
								"promotion_status", "current_cgpa", "backlog_count",
								"attendance_percent", "manual_override"]}

		if dimension == "cohort":
			cohort_id = frappe.db.get_value("Batch", {"cohort_name": value}, "name") or value
			rows = frappe.db.get_all(
				"Student Promotion", filters={"programme": cohort_id, "stage": "Published"},
				fields=["name", "student", "student_name", "programme", "promotion_policy",
						"current_year", "target_year", "promotion_status",
						"current_cgpa", "backlog_count"],
				limit_start=offset, limit_page_length=page_size, order_by="processed_on desc",
			)
			total = frappe.db.count("Student Promotion", filters={"programme": cohort_id, "stage": "Published"})
			return {"rows": rows, "total": total,
					"columns": ["student_name", "programme", "current_year", "target_year",
								"promotion_status", "current_cgpa", "backlog_count"]}

	# ── Exam Barcodes (under examination module) ───────────────────────────────
	elif module == "examination" and dimension in ("barcode_list", "barcode_plan", "barcode_course"):
		filters = {}
		if dimension == "barcode_plan" and value and value not in ("all", "All"):
			plan_id = frappe.db.get_value("Exam Plan", {"exam_name": value}, "name") or value
			filters["exam_plan"] = plan_id
		elif dimension == "barcode_course" and value and value not in ("all", "All"):
			course_id = frappe.db.get_value("Course", {"course_name": value}, "name") or value
			filters["course"] = course_id

		rows = frappe.db.get_all(
			"Exam Barcode", filters=filters,
			fields=["name", "student", "student_name", "registration_id",
					"exam_plan", "course", "exam_date", "section", "barcode", "generated_on"],
			limit_start=offset, limit_page_length=page_size, order_by="generated_on desc",
		)
		total = frappe.db.count("Exam Barcode", filters=filters)
		return {"rows": rows, "total": total,
				"columns": ["student_name", "registration_id", "exam_plan",
							"course", "exam_date", "section", "barcode"]}

	# ── Ticketing ─────────────────────────────────────────────────────────────
	elif module == "ticketing":
		# Build SQL directly so we can handle NULL/empty "Unassigned" labels
		conditions = []
		params = {}

		if dimension == "ticket_status" and value and value != "all":
			conditions.append("status = %(val)s")
			params["val"] = value
		elif dimension == "ticket_priority" and value and value != "all":
			conditions.append("priority = %(val)s")
			params["val"] = value
		elif dimension == "ticket_type" and value and value != "all":
			if value == "Uncategorized":
				conditions.append("(ticket_type IS NULL OR ticket_type = '')")
			else:
				conditions.append("ticket_type = %(val)s")
				params["val"] = value
		elif dimension == "agent_group" and value and value != "all":
			if value == "Unassigned":
				conditions.append("(agent_group IS NULL OR agent_group = '')")
			else:
				conditions.append("agent_group = %(val)s")
				params["val"] = value

		where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

		rows = frappe.db.sql(
			f"""
			SELECT name, subject, raised_by, status, priority,
				   ticket_type, agent_group, agreement_status, opening_date, resolution_date
			FROM `tabHD Ticket`
			{where}
			ORDER BY opening_date DESC
			LIMIT %(page_size)s OFFSET %(offset)s
			""",
			{**params, "page_size": page_size, "offset": offset},
			as_dict=True,
		)
		total = frappe.db.sql(
			f"SELECT COUNT(*) FROM `tabHD Ticket` {where}", params
		)[0][0]
		return {"rows": rows, "total": total,
				"columns": ["name", "subject", "raised_by", "status", "priority",
							"ticket_type", "agent_group", "agreement_status", "opening_date"]}

	# ── RFID ──────────────────────────────────────────────────────────────────
	if module == "rfid":
		att_log_cols = ["name", "student", "rfid_uid", "swipe_time",
						"location", "terminal_alias", "source", "processed"]

		if dimension == "location":
			# "Unknown" was a display alias for blank/null
			if value == "Unknown":
				filters = [["Attendance Log", "location", "in", ["", None]]]
			else:
				filters = {"location": value}
			rows = frappe.db.get_all(
				"Attendance Log", filters=filters, fields=att_log_cols,
				limit_start=offset, limit_page_length=page_size, order_by="swipe_time desc",
			)
			total = frappe.db.count("Attendance Log", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "rfid_uid", "swipe_time", "location", "terminal_alias", "processed"]}

		elif dimension == "terminal":
			if value == "Unknown":
				filters = [["Attendance Log", "terminal_alias", "in", ["", None]]]
			else:
				filters = {"terminal_alias": value}
			rows = frappe.db.get_all(
				"Attendance Log", filters=filters, fields=att_log_cols,
				limit_start=offset, limit_page_length=page_size, order_by="swipe_time desc",
			)
			total = frappe.db.count("Attendance Log", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "rfid_uid", "swipe_time", "location", "terminal_alias", "processed"]}

		elif dimension == "processing":
			is_processed = 1 if value == "Processed" else 0
			filters = {"processed": is_processed}
			rows = frappe.db.get_all(
				"Attendance Log", filters=filters, fields=att_log_cols,
				limit_start=offset, limit_page_length=page_size, order_by="swipe_time desc",
			)
			total = frappe.db.count("Attendance Log", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "rfid_uid", "swipe_time", "location", "terminal_alias", "processed"]}

		elif dimension == "card_status":
			filters = {"card_status": value}
			rows = frappe.db.get_all(
				"Student RFID Card", filters=filters,
				fields=["name", "student", "rfid_uid", "card_status", "issue_date", "expiry_date"],
				limit_start=offset, limit_page_length=page_size, order_by="issue_date desc",
			)
			total = frappe.db.count("Student RFID Card", filters=filters)
			return {"rows": rows, "total": total,
					"columns": ["student", "rfid_uid", "card_status", "issue_date", "expiry_date"]}

	return {"rows": [], "total": 0, "columns": [],
			"message": "No drilldown configured for this dimension."}
