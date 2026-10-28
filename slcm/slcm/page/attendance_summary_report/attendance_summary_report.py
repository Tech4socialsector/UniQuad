# Copyright (c) 2026, SLCM and contributors

import calendar
import json

import frappe
from frappe.utils import getdate
from slcm.permissions import (
	_FULL_ACCESS_ROLES,
	_get_faculty_course_offerings,
	_get_faculty_name,
)
from slcm.slcm.doctype.student_enrollment.student_enrollment import year_log_exists

def _is_unrestricted(roles):
	return bool(roles & _FULL_ACCESS_ROLES) or "slcm_Programme Chair" in roles


@frappe.whitelist()
def get_student_filter_options(txt=None):
	"""Options for the Student filter dropdown, labelled "Name (ID)" instead
	of just the bare Student Master name — Student Master's title_field
	(first_name) alone isn't enough to tell same-named students apart."""
	or_filters = {}
	if txt:
		like = f"%{txt}%"
		or_filters = {
			"name": ["like", like],
			"first_name": ["like", like],
			"last_name": ["like", like],
			"registration_id": ["like", like],
		}

	students = frappe.get_all(
		"Student Master",
		or_filters=or_filters,
		fields=["name", "first_name", "last_name", "registration_id"],
		order_by="first_name asc, last_name asc",
		limit=20,
	)
	return [{
		"value": s.name,
		"label": f"{' '.join(filter(None, [s.first_name, s.last_name])) or s.name} ({s.registration_id or s.name})",
	} for s in students]


def _eligibility_for(percentage, min_pct):
	return "Eligible" if percentage >= min_pct else "Not Eligible"


def _as_list(value):
	"""Normalize a filter param into a plain list. Filters arrive as either
	a single string (old-style single-select calls, e.g. from bench execute),
	an already-decoded list (frappe.call JSON-encodes JS arrays and the
	framework decodes them before the whitelisted function runs), or a
	JSON-array string in edge cases — handle all three the same way."""
	if not value:
		return []
	if isinstance(value, list):
		return [v for v in value if v]
	if isinstance(value, str):
		s = value.strip()
		if s.startswith("[") and s.endswith("]"):
			try:
				parsed = json.loads(s)
				if isinstance(parsed, list):
					return [v for v in parsed if v]
			except ValueError:
				pass
		return [value]
	return [value]


def _resolve_offerings_and_roster(academic_year=None, term=None, programme=None,
	course=None, batch=None, section=None, student=None):
	"""Shared first step for every view on this page: build the Course
	Offering filter from whichever params were passed, apply faculty
	role-scoping, then resolve the actual student roster (via Student
	Enrollment / Student Enrollment Course) for the matching offerings.

	Returns (offerings, roster) where `offerings` is a list of Course
	Offering dicts (name, course_title, section) and `roster` is a list of
	dicts (course_offering, student, section, first_name, last_name).
	Either may be empty — callers should bail out early in that case.
	"""
	user = frappe.session.user
	roles = set(frappe.get_roles(user))

	academic_years = _as_list(academic_year)
	terms = _as_list(term)
	programmes = _as_list(programme)
	courses = _as_list(course)
	batches = _as_list(batch)
	sections = _as_list(section)
	students = _as_list(student)

	co_filters = {}
	if academic_years:
		co_filters["academic_year"] = ["in", academic_years]
	if terms:
		co_filters["term_name"] = ["in", terms]
	if programmes:
		co_filters["program"] = ["in", programmes]
	if courses:
		co_filters["course_title"] = ["in", courses]
	batch_offerings = None
	if batches:
		# Offerings have no Batch: a Batch filter means offerings whose
		# programme / academic year / year no match an Enrolled Student
		# Enrollment of that batch.
		batch_offerings = [r[0] for r in frappe.db.sql(f"""
			SELECT DISTINCT co.name
			FROM `tabCourse Offering` co
			JOIN `tabStudent Enrollment` se
				ON se.program = co.program
				AND {year_log_exists("se", "co.academic_year", "co.year_no")}
			WHERE se.batch IN %(batches)s AND se.status = 'Enrolled'
		""", {"batches": batches})]
		if not batch_offerings:
			return [], []
		co_filters["name"] = ["in", batch_offerings]

	if user != "Administrator" and not _is_unrestricted(roles):
		if "slcm_Faculty" not in roles:
			frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
		faculty_name = _get_faculty_name(user)
		if not faculty_name:
			frappe.throw(frappe._("No Faculty record linked to your account."), frappe.PermissionError)
		visible = _get_faculty_course_offerings(faculty_name)
		if batch_offerings is not None:
			visible = [v for v in visible if v in set(batch_offerings)]
		if not visible:
			return [], []
		co_filters["name"] = ["in", visible]

	offerings = frappe.get_all(
		"Course Offering",
		filters=co_filters,
		fields=["name", "course_title"],
	)
	if not offerings:
		return [], []

	offering_names = [o.name for o in offerings]

	student_clause = ""
	if students:
		student_clause = "AND se.student IN %(students)s"
	# Sections (and batches) are recorded on the student's enrollment.
	if batches:
		student_clause += " AND se.batch IN %(batches)s"
	if sections:
		student_clause += " AND se.section IN %(sections)s"

	roster = frappe.db.sql(f"""
		SELECT sec.course_offering, se.student, se.section, s.first_name, s.last_name,
			s.registration_id, s.passport_size_photo
		FROM `tabStudent Enrollment` se
		JOIN `tabStudent Enrollment Course` sec ON sec.parent = se.name
		JOIN `tabStudent Master` s ON s.name = se.student
		WHERE sec.course_offering IN %(offerings)s
		AND sec.status = 'Enrolled' AND se.status = 'Enrolled'
		{student_clause}
	""", {"offerings": offering_names, "students": students, "batches": batches,
		"sections": sections}, as_dict=True)

	return offerings, roster


def _student_offerings_map(roster):
	"""student -> set of course_offering names they're actually enrolled in,
	from the roster — used to scope monthly/daily totals to only the
	offerings a given student belongs to (not every offering the filters
	matched)."""
	out = {}
	for r in roster:
		out.setdefault(r.student, set()).add(r.course_offering)
	return out


def _condonation_status(row):
	"""Derive the two approver statuses from Student Attendance Condonation's
	single `final_status` field + timestamps (there's no separate per-approver
	status field on the doctype — see student_attendance_condonation.py's
	aad_decision()/programme_chair_decision() for the underlying state machine:
	Pending -> (AAD) -> May Be Approved -> (Programme Chair) -> Approved, with
	either level able to short-circuit to Rejected)."""
	if row.aad_rejected_reason:
		aad_status = "Rejected"
	elif row.aad_approve_or_rejected_timestamp:
		aad_status = "Approved"
	else:
		aad_status = "Pending"

	if row.programme_chair_approve_or_rejected_timestamp:
		pc_status = "Approved" if row.final_status == "Approved" else "Rejected"
	elif row.final_status == "May Be Approved":
		pc_status = "Pending"
	else:
		pc_status = "—"

	return aad_status, pc_status


def _condonation_by_student_offering(offering_names, students):
	"""Latest (by creation) non-cancelled condonation request per
	(course_offering, student) — used as the single row shown when the
	"Include Condonation Report" filter is checked."""
	records = frappe.db.sql("""
		SELECT student, course_offering, number_of_hours, condonation_reason,
			proof_document, final_status, aad_rejected_reason,
			aad_approve_or_rejected_timestamp, programme_chair_approve_or_rejected_timestamp,
			creation
		FROM `tabStudent Attendance Condonation`
		WHERE course_offering IN %(offerings)s AND student IN %(students)s AND docstatus < 2
		ORDER BY creation ASC
	""", {"offerings": offering_names, "students": students}, as_dict=True)

	out = {}
	for r in records:
		# ORDER BY creation ASC + plain overwrite keeps the latest record per key
		out[(r.course_offering, r.student)] = r
	return out


@frappe.whitelist()
def get_data(academic_year=None, term=None, programme=None, course=None, batch=None,
	section=None, student=None, include_condonation=None):
	"""Read-only, batched attendance summary — recomputed fresh from
	Time Table (scheduled), Attendance Session (conducted), and
	Student Attendance ⋈ Attendance Session (attended). Does not read or
	write the Attendance Summary DocType at all.

	Attended hours are deliberately summed from the *session's* duration
	(not Student Attendance.hours_counted, which can hold a stale/default
	value independent of the session it's linked to) — this guarantees
	attended hours can never exceed conducted hours for the same offering,
	since both are drawn from the same pool of conducted session durations.
	"""
	offerings, roster = _resolve_offerings_and_roster(
		academic_year, term, programme, course, batch, section, student
	)
	if not offerings or not roster:
		return []

	offering_names = [o.name for o in offerings]
	course_title_by_offering = {o.name: o.course_title for o in offerings}
	offering_section_by_offering = {o.name: o.section for o in offerings}
	students = list({r.student for r in roster})

	# Scheduled hours — planned Time Table hours per offering
	scheduled = frappe.db.sql("""
		SELECT course_offering, SUM(COALESCE(duration_hours, 0)) as hours
		FROM `tabTime Table`
		WHERE course_offering IN %(offerings)s AND docstatus < 2
		GROUP BY course_offering
	""", {"offerings": offering_names}, as_dict=True)
	scheduled_by_offering = {r.course_offering: r.hours or 0 for r in scheduled}

	# Conducted hours — actually-held Lecture/Tutorial sessions per offering.
	# This is the denominator used for attendance_percentage.
	conducted = frappe.db.sql("""
		SELECT course_offering, SUM(COALESCE(duration_hours, 0)) as hours
		FROM `tabAttendance Session`
		WHERE course_offering IN %(offerings)s
		AND session_status = 'Conducted'
		AND session_type IN ('Lecture', 'Tutorial')
		GROUP BY course_offering
	""", {"offerings": offering_names}, as_dict=True)
	conducted_by_offering = {r.course_offering: r.hours or 0 for r in conducted}

	# Attended hours — sum the CONDUCTED SESSION's own duration (not the
	# attendance record's hours_counted) for every session the student was
	# marked Present/Late/Excused in. This is the fix for the
	# "attended hours exceeds conducted hours" bug: both numbers now come
	# from the exact same `Attendance Session.duration_hours` pool.
	attended = frappe.db.sql("""
		SELECT ats.course_offering as course_offering, sa.student,
			SUM(ats.duration_hours) as hours
		FROM `tabStudent Attendance` sa
		JOIN `tabAttendance Session` ats ON ats.name = sa.attendance_session
		WHERE ats.course_offering IN %(offerings)s AND sa.student IN %(students)s
		AND sa.status IN ('Present', 'Late', 'Excused')
		AND ats.session_status = 'Conducted'
		AND ats.session_type IN ('Lecture', 'Tutorial')
		AND sa.docstatus < 2
		GROUP BY ats.course_offering, sa.student
	""", {"offerings": offering_names, "students": students}, as_dict=True)
	attended_map = {(r.course_offering, r.student): r.hours or 0 for r in attended}

	min_pct = frappe.db.get_single_value("Attendance Settings", "minimum_attendance_percentage") or 0

	condonation_by_key = {}
	if include_condonation:
		condonation_by_key = _condonation_by_student_offering(offering_names, students)

	rows = []
	for r in roster:
		key = (r.course_offering, r.student)
		conducted_hours = conducted_by_offering.get(r.course_offering, 0)
		attended_hours = attended_map.get(key, 0)
		percentage = (attended_hours / conducted_hours * 100) if conducted_hours else 0
		section_value = r.section or offering_section_by_offering.get(r.course_offering)

		row = {
			"student": r.student,
			"student_id": r.registration_id or r.student,
			"student_name": " ".join(filter(None, [r.first_name, r.last_name])) or r.student,
			"student_image": r.passport_size_photo,
			"course_offering": r.course_offering,
			"course": course_title_by_offering.get(r.course_offering),
			"section": section_value,
			"total_scheduled_hours": round(scheduled_by_offering.get(r.course_offering, 0), 2),
			"total_conducted_hours": round(conducted_hours, 2),
			"total_attended_hours": round(attended_hours, 2),
			"attendance_percentage": round(percentage, 2),
			"eligibility": _eligibility_for(percentage, min_pct),
		}

		if include_condonation:
			condonation = condonation_by_key.get(key)
			if condonation:
				aad_status, pc_status = _condonation_status(condonation)
				condoned_hours = condonation.number_of_hours or 0
				# Condoned hours only count towards attendance once BOTH approvers
				# have signed off — while it's Pending/May Be Approved/Rejected,
				# the "after condonation" percentage stays identical to "before".
				effective_hours = condoned_hours if condonation.final_status == "Approved" else 0
				after_percentage = (
					(attended_hours + effective_hours) / conducted_hours * 100
				) if conducted_hours else 0

				row.update({
					"condonation_applied": "Yes",
					"condonation_hours": round(condoned_hours, 2),
					"condonation_reason": condonation.condonation_reason,
					"condonation_proof": condonation.proof_document,
					"condonation_aad_status": aad_status,
					"condonation_pc_status": pc_status,
					"percentage_before_condonation": round(percentage, 2),
					"percentage_after_condonation": round(after_percentage, 2),
				})
			else:
				row.update({
					"condonation_applied": "No",
					"condonation_hours": None,
					"condonation_reason": None,
					"condonation_proof": None,
					"condonation_aad_status": None,
					"condonation_pc_status": None,
					"percentage_before_condonation": round(percentage, 2),
					"percentage_after_condonation": round(percentage, 2),
				})

		rows.append(row)

	rows.sort(key=lambda r: (r["course"] or "", r["student_name"] or ""))
	return rows


@frappe.whitelist()
def get_monthly_matrix(academic_year=None, term=None, programme=None, course=None, batch=None,
	section=None, student=None):
	"""Students × calendar-month matrix. Each cell is that student's
	attendance % for that month, using the same attended/conducted hours
	definition as get_data(), just grouped by month instead of totalled."""
	offerings, roster = _resolve_offerings_and_roster(
		academic_year, term, programme, course, batch, section, student
	)
	if not offerings or not roster:
		return {"months": [], "rows": []}

	offering_names = [o.name for o in offerings]
	students = list({r.student for r in roster})
	student_offerings = _student_offerings_map(roster)
	student_name_by_id = {
		r.student: " ".join(filter(None, [r.first_name, r.last_name])) or r.student
		for r in roster
	}
	student_id_by_id = {r.student: r.registration_id or r.student for r in roster}
	student_image_by_id = {r.student: r.passport_size_photo for r in roster}

	conducted = frappe.db.sql("""
		SELECT course_offering, DATE_FORMAT(session_date, '%%Y-%%m') as ym,
			SUM(COALESCE(duration_hours, 0)) as hours
		FROM `tabAttendance Session`
		WHERE course_offering IN %(offerings)s
		AND session_status = 'Conducted'
		AND session_type IN ('Lecture', 'Tutorial')
		GROUP BY course_offering, ym
	""", {"offerings": offering_names}, as_dict=True)
	conducted_by_offering_month = {}
	all_months = set()
	for r in conducted:
		conducted_by_offering_month[(r.course_offering, r.ym)] = r.hours or 0
		all_months.add(r.ym)

	attended = frappe.db.sql("""
		SELECT ats.course_offering as course_offering, sa.student,
			DATE_FORMAT(ats.session_date, '%%Y-%%m') as ym,
			SUM(ats.duration_hours) as hours
		FROM `tabStudent Attendance` sa
		JOIN `tabAttendance Session` ats ON ats.name = sa.attendance_session
		WHERE ats.course_offering IN %(offerings)s AND sa.student IN %(students)s
		AND sa.status IN ('Present', 'Late', 'Excused')
		AND ats.session_status = 'Conducted'
		AND ats.session_type IN ('Lecture', 'Tutorial')
		AND sa.docstatus < 2
		GROUP BY ats.course_offering, sa.student, ym
	""", {"offerings": offering_names, "students": students}, as_dict=True)
	attended_by_offering_student_month = {(r.course_offering, r.student, r.ym): r.hours or 0 for r in attended}

	months = sorted(all_months)

	min_pct = frappe.db.get_single_value("Attendance Settings", "minimum_attendance_percentage") or 0

	rows = []
	for student in students:
		own_offerings = student_offerings.get(student, set())
		month_data = {}
		for ym in months:
			conducted_hours = sum(
				conducted_by_offering_month.get((off, ym), 0) for off in own_offerings
			)
			attended_hours = sum(
				attended_by_offering_student_month.get((off, student, ym), 0) for off in own_offerings
			)
			pct = round((attended_hours / conducted_hours * 100), 2) if conducted_hours else None
			# Hours are included alongside the percentage so the UI can show
			# "9/9 hrs" context on hover instead of a bare, unexplained number.
			month_data[ym] = None if pct is None else {
				"percentage": pct,
				"conducted_hours": round(conducted_hours, 2),
				"attended_hours": round(attended_hours, 2),
			}

		rows.append({
			"student": student,
			"student_id": student_id_by_id.get(student, student),
			"student_name": student_name_by_id.get(student, student),
			"student_image": student_image_by_id.get(student),
			"months": month_data,
		})

	rows.sort(key=lambda r: r["student_name"] or "")

	month_labels = [{"key": ym, "label": _format_month_label(ym)} for ym in months]
	return {"months": month_labels, "rows": rows, "min_pct": min_pct}


@frappe.whitelist()
def get_weekly_matrix(academic_year=None, term=None, programme=None, course=None, batch=None,
	section=None, student=None):
	"""Students × week matrix. Each cell is that student's attendance % for
	that week, using the same attended/conducted hours definition as
	get_data(), just grouped by week instead of totalled.

	Weeks run Monday-Sunday (Sunday is the institution's mandatory weekly
	off — see Institutional Calendar's DEFAULT_WEEKLY_OFF_DAYS — so a week
	is labeled/anchored by its Monday rather than MySQL's default
	Sunday-starts-the-week convention, which would otherwise split the
	teaching week across two columns)."""
	offerings, roster = _resolve_offerings_and_roster(
		academic_year, term, programme, course, batch, section, student
	)
	if not offerings or not roster:
		return {"weeks": [], "rows": []}

	offering_names = [o.name for o in offerings]
	students = list({r.student for r in roster})
	student_offerings = _student_offerings_map(roster)
	student_name_by_id = {
		r.student: " ".join(filter(None, [r.first_name, r.last_name])) or r.student
		for r in roster
	}
	student_id_by_id = {r.student: r.registration_id or r.student for r in roster}
	student_image_by_id = {r.student: r.passport_size_photo for r in roster}

	# WEEKDAY() is 0=Monday..6=Sunday, so subtracting it from the date always
	# lands on that date's Monday regardless of MySQL's default week-start.
	conducted = frappe.db.sql("""
		SELECT course_offering,
			DATE_SUB(session_date, INTERVAL WEEKDAY(session_date) DAY) as week_start,
			SUM(COALESCE(duration_hours, 0)) as hours
		FROM `tabAttendance Session`
		WHERE course_offering IN %(offerings)s
		AND session_status = 'Conducted'
		AND session_type IN ('Lecture', 'Tutorial')
		GROUP BY course_offering, week_start
	""", {"offerings": offering_names}, as_dict=True)
	conducted_by_offering_week = {}
	all_weeks = set()
	for r in conducted:
		wk = str(r.week_start)
		conducted_by_offering_week[(r.course_offering, wk)] = r.hours or 0
		all_weeks.add(wk)

	attended = frappe.db.sql("""
		SELECT ats.course_offering as course_offering, sa.student,
			DATE_SUB(ats.session_date, INTERVAL WEEKDAY(ats.session_date) DAY) as week_start,
			SUM(ats.duration_hours) as hours
		FROM `tabStudent Attendance` sa
		JOIN `tabAttendance Session` ats ON ats.name = sa.attendance_session
		WHERE ats.course_offering IN %(offerings)s AND sa.student IN %(students)s
		AND sa.status IN ('Present', 'Late', 'Excused')
		AND ats.session_status = 'Conducted'
		AND ats.session_type IN ('Lecture', 'Tutorial')
		AND sa.docstatus < 2
		GROUP BY ats.course_offering, sa.student, week_start
	""", {"offerings": offering_names, "students": students}, as_dict=True)
	attended_by_offering_student_week = {
		(r.course_offering, r.student, str(r.week_start)): r.hours or 0 for r in attended
	}

	weeks = sorted(all_weeks)

	min_pct = frappe.db.get_single_value("Attendance Settings", "minimum_attendance_percentage") or 0

	rows = []
	for student in students:
		own_offerings = student_offerings.get(student, set())
		week_data = {}
		for wk in weeks:
			conducted_hours = sum(
				conducted_by_offering_week.get((off, wk), 0) for off in own_offerings
			)
			attended_hours = sum(
				attended_by_offering_student_week.get((off, student, wk), 0) for off in own_offerings
			)
			pct = round((attended_hours / conducted_hours * 100), 2) if conducted_hours else None
			week_data[wk] = None if pct is None else {
				"percentage": pct,
				"conducted_hours": round(conducted_hours, 2),
				"attended_hours": round(attended_hours, 2),
			}

		rows.append({
			"student": student,
			"student_id": student_id_by_id.get(student, student),
			"student_name": student_name_by_id.get(student, student),
			"student_image": student_image_by_id.get(student),
			"weeks": week_data,
		})

	rows.sort(key=lambda r: r["student_name"] or "")

	week_labels = [{"key": wk, "label": _format_week_label(wk)} for wk in weeks]
	return {"weeks": week_labels, "rows": rows, "min_pct": min_pct}


MAX_DAILY_RANGE = 62  # ~2 months, keeps the register table a reasonable width


@frappe.whitelist()
def get_daily_matrix(academic_year=None, term=None, programme=None, course=None, batch=None,
	section=None, student=None, from_date=None, to_date=None):
	"""Students × day matrix for a custom date range, showing EVERY day in
	that range (like a manual attendance register) — not just days that had
	a class. Days with no conducted session for a student's own offering are
	left blank; days with one show "attended/scheduled" hours for that day
	(a student can have more than one class the same day, so hours are
	summed across all of that day's sessions for their own offering)."""
	if not from_date or not to_date:
		frappe.throw(frappe._("From Date and To Date are required"))

	start_date = getdate(from_date)
	end_date = getdate(to_date)
	if end_date < start_date:
		frappe.throw(frappe._("To Date cannot be before From Date"))
	if (end_date - start_date).days + 1 > MAX_DAILY_RANGE:
		frappe.throw(frappe._("Please select a range of {0} days or fewer").format(MAX_DAILY_RANGE))

	all_days = []
	d = start_date
	while d <= end_date:
		all_days.append(str(d))
		d = frappe.utils.add_days(d, 1)

	offerings, roster = _resolve_offerings_and_roster(
		academic_year, term, programme, course, batch, section, student
	)
	if not offerings or not roster:
		return {"days": [], "rows": []}

	offering_names = [o.name for o in offerings]
	students = list({r.student for r in roster})
	student_offerings = _student_offerings_map(roster)
	student_name_by_id = {
		r.student: " ".join(filter(None, [r.first_name, r.last_name])) or r.student
		for r in roster
	}
	student_id_by_id = {r.student: r.registration_id or r.student for r in roster}
	student_image_by_id = {r.student: r.passport_size_photo for r in roster}

	sessions = frappe.db.sql("""
		SELECT name, course_offering, session_date, COALESCE(duration_hours, 0) as duration_hours
		FROM `tabAttendance Session`
		WHERE course_offering IN %(offerings)s
		AND session_status = 'Conducted'
		AND session_type IN ('Lecture', 'Tutorial')
		AND session_date BETWEEN %(start)s AND %(end)s
	""", {"offerings": offering_names, "start": start_date, "end": end_date}, as_dict=True)

	# (course_offering, date) -> set of session names held that day
	sessions_by_offering_date = {}
	session_hours_by_name = {}
	for s in sessions:
		d = str(getdate(s.session_date))
		sessions_by_offering_date.setdefault((s.course_offering, d), set()).add(s.name)
		session_hours_by_name[s.name] = s.duration_hours

	present_sessions_by_student = {}
	if sessions:
		session_names = [s.name for s in sessions]
		attendance = frappe.db.sql("""
			SELECT sa.student, sa.attendance_session, sa.status
			FROM `tabStudent Attendance` sa
			WHERE sa.attendance_session IN %(sessions)s AND sa.student IN %(students)s
			AND sa.docstatus < 2
		""", {"sessions": session_names, "students": students}, as_dict=True)
		for a in attendance:
			if a.status in ("Present", "Late", "Excused"):
				present_sessions_by_student.setdefault(a.student, set()).add(a.attendance_session)

	rows = []
	for student in students:
		own_offerings = student_offerings.get(student, set())
		present_set = present_sessions_by_student.get(student, set())
		day_cells = {}
		# Every day in the selected range becomes a column (like a manual
		# attendance register) — days with no class for this student's own
		# offering are simply left out of day_cells and render as blank.
		for d in all_days:
			session_set = set()
			for off in own_offerings:
				session_set |= sessions_by_offering_date.get((off, d), set())
			if not session_set:
				continue
			scheduled_hours = sum(session_hours_by_name.get(s, 0) for s in session_set)
			attended_hours = sum(session_hours_by_name.get(s, 0) for s in session_set & present_set)
			day_cells[d] = {
				"attended_hours": round(attended_hours, 2),
				"scheduled_hours": round(scheduled_hours, 2),
			}

		rows.append({
			"student": student,
			"student_id": student_id_by_id.get(student, student),
			"student_name": student_name_by_id.get(student, student),
			"student_image": student_image_by_id.get(student),
			"days": day_cells,
		})

	rows.sort(key=lambda r: r["student_name"] or "")

	day_labels = [{"key": d, "label": _format_day_label(d)} for d in all_days]
	return {"days": day_labels, "rows": rows}


def _format_month_label(ym):
	year, month = ym.split("-")
	return f"{calendar.month_abbr[int(month)]} {year}"


@frappe.whitelist()
def get_daily_drilldown(student, date, academic_year=None, term=None, programme=None,
	course=None, batch=None, section=None):
	"""Per-session detail for one student on one day, used by the Daily tab's
	cell drill-down. Re-applies the same filters (and therefore the same
	faculty/role scoping) as get_daily_matrix so a faculty member can't pull
	up detail for a student/offering outside what they're permitted to see,
	then further restricts to just that one student's own enrolled
	offering(s) — never every offering the page-level filters matched."""
	if not student or not date:
		frappe.throw(frappe._("Student and Date are required"))

	target_date = getdate(date)

	offerings, roster = _resolve_offerings_and_roster(
		academic_year, term, programme, course, batch, section
	)
	if not offerings or not roster:
		return []

	student_offerings = _student_offerings_map(roster)
	own_offerings = student_offerings.get(student)
	if not own_offerings:
		# Either the student isn't in the roster this filter combination
		# resolves to, or isn't enrolled in any matching offering — either
		# way there is nothing this caller is entitled to see for them.
		return []

	course_title_by_offering = {o.name: o.course_title for o in offerings}

	sessions = frappe.db.sql("""
		SELECT ats.name, ats.course_offering, ats.session_start_time, ats.session_end_time,
			ats.instructor, ats.room, ats.duration_hours,
			sa.status, sa.remarks, sa.in_time, sa.out_time
		FROM `tabAttendance Session` ats
		LEFT JOIN `tabStudent Attendance` sa
			ON sa.attendance_session = ats.name AND sa.student = %(student)s AND sa.docstatus < 2
		WHERE ats.course_offering IN %(offerings)s
		AND ats.session_status = 'Conducted'
		AND ats.session_type IN ('Lecture', 'Tutorial')
		AND ats.session_date = %(date)s
		ORDER BY ats.session_start_time
	""", {
		"student": student,
		"offerings": list(own_offerings),
		"date": target_date,
	}, as_dict=True)

	instructor_names = {s.instructor for s in sessions if s.instructor}
	faculty_name_by_id = {}
	if instructor_names:
		faculty_name_by_id = {
			str(f.name): " ".join(filter(None, [f.first_name, f.last_name]))
			for f in frappe.get_all(
				"Faculty", filters={"name": ["in", list(instructor_names)]},
				fields=["name", "first_name", "last_name"],
			)
		}

	return [{
		"session": s.name,
		"course": course_title_by_offering.get(s.course_offering, s.course_offering),
		"from_time": str(s.session_start_time) if s.session_start_time else None,
		"to_time": str(s.session_end_time) if s.session_end_time else None,
		"instructor": faculty_name_by_id.get(s.instructor, s.instructor),
		"room": s.room,
		"duration_hours": s.duration_hours,
		"status": s.status or "Not Marked",
		"remarks": s.remarks,
	} for s in sessions]


def _format_day_label(date_str):
	d = getdate(date_str)
	return f"{d.day} {calendar.month_abbr[d.month]}"


def _format_week_label(week_start_str):
	"""e.g. '6 - 12 Jul' or '30 Jun - 6 Jul' when the week spans a month boundary."""
	start = getdate(week_start_str)
	end = frappe.utils.add_days(start, 6)
	if start.month == end.month:
		return f"{start.day} - {end.day} {calendar.month_abbr[start.month]}"
	return f"{start.day} {calendar.month_abbr[start.month]} - {end.day} {calendar.month_abbr[end.month]}"
