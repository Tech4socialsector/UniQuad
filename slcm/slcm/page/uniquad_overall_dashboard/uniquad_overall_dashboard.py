# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Uniquad Overall Dashboard — every Uniquad module on one page.

Laid out like the Pathways Overall Dashboard: filters → headline funnel → a
board of single / paired cards, one section per module (Admission, Student
Registration, Programme Management, Attendance, ID Card, Fees, Venue Booking,
PACE, FLE, Examinations, Transcripts, Promotion) → a per-person Timeline tab → an Admission Funnel tab.

Security: every number and row comes from ``frappe.get_list`` (DocPerm, User
Permissions and permission_query_conditions all apply). Sources, cards,
columns and sort keys live in server-side registries; the client only sends
keys.
"""

import csv
import hashlib
import io
import json
from collections import defaultdict
from statistics import median

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, get_datetime, getdate, now_datetime, nowdate

APP = "Applicant"
STU = "Student Master"
ISA = "Interview Seat Allocation"
OFFER = "Offer Letter"
AUDIT = "Admission Audit Log"

CACHE_SECONDS = 90
MAX_PAGE = 500
EXPORT_CHUNK = 5000
NONE = "__none__"

# ── Applicant status vocabulary ──────────────────────────────────────────────
# Rank = how far through admission a status is. "Reached a step" means rank
# >= that step, even if the applicant was turned down later (like Pathways).
RANK = {
	"Draft": 0,
	"Submitted": 1, "Submitted and Paid": 1,
	"Entrance Test Allocated": 2, "Entrance Test Scheduled": 2, "Entrance Test Completed": 2,
	"Entrance Test Rejected": 2, "Entrance Test Exempted": 2, "Entrance Test Excempted": 2,
	"Exempted Entrance Test And Interview": 2,
	"Interview Scheduled": 3, "Interview Sheduled": 3, "Interview Completed": 3,
	"Interview Rejected": 3, "Interview Exempted": 3, "Interview Excempted": 3,
	"Merit Published": 4, "Merit Selected": 4, "Merit Waitlisted": 4, "Merit Rejected": 4,
	"Selected": 4, "Waitlisted": 4,
	"Seat Selected": 5, "Seat Waitlisted": 5, "Seat Rejected": 5,
	"Offer Issued": 6, "Offer Accepted": 6, "Offer Declined": 6, "Offer Expired": 6, "Accepted": 6,
	"Confirmation Fee Paid": 7, "Fee Paid": 7, "Full Fee Paid": 7,
	"Enrolled": 8,
	# Rank unknown: these only ever count in "All rejected".
	"Rejected": 1, "Withdrawn": None,
}

G = {
	"draft": ["Draft"],
	"submitted": ["Submitted", "Submitted and Paid"],
	"test_scheduled": ["Entrance Test Allocated", "Entrance Test Scheduled"],
	"test_done": ["Entrance Test Completed", "Entrance Test Exempted", "Entrance Test Excempted",
		"Exempted Entrance Test And Interview"],
	"test_rejected": ["Entrance Test Rejected"],
	"iv_scheduled": ["Interview Scheduled", "Interview Sheduled"],
	"iv_done": ["Interview Completed"],
	"iv_exempted": ["Interview Exempted", "Interview Excempted"],
	"iv_rejected": ["Interview Rejected"],
	"merit_selected": ["Merit Selected", "Merit Published", "Selected"],
	"merit_waitlisted": ["Merit Waitlisted", "Waitlisted"],
	"merit_rejected": ["Merit Rejected"],
	"seat_selected": ["Seat Selected"],
	"seat_waitlisted": ["Seat Waitlisted"],
	"seat_rejected": ["Seat Rejected"],
	"offer_issued": ["Offer Issued"],
	"offer_accepted": ["Offer Accepted", "Accepted"],
	"offer_declined": ["Offer Declined"],
	"offer_expired": ["Offer Expired"],
	"conf_fee": ["Confirmation Fee Paid"],
	"full_fee": ["Full Fee Paid", "Fee Paid"],
	"enrolled": ["Enrolled"],
	"withdrawn": ["Withdrawn"],
	"rejected": ["Rejected"],
}
NOT_ADMITTED = (G["rejected"] + G["withdrawn"] + G["test_rejected"] + G["iv_rejected"]
	+ G["merit_rejected"] + G["seat_rejected"] + G["offer_declined"] + G["offer_expired"])


def reached(rank):
	"""Statuses at or past ``rank``."""
	return sorted(s for s, r in RANK.items() if r is not None and r >= rank)


# Funnel steps (rank-based, "reached or went further"). None = every status.
STEPS = [
	("total", _("Total applications"), None),
	("submitted", _("Submitted"), sorted(set(reached(1)) - set(G["withdrawn"]))),
	("test", _("Entrance test stage"), reached(2)),
	("interview", _("Interview stage"), reached(3)),
	("merit", _("Merit selected"), sorted(set(G["merit_selected"]) | set(reached(5)))),
	("offer", _("Offer issued"), reached(6)),
	("accepted", _("Offer accepted"), sorted(set(G["offer_accepted"]) | set(reached(7)))),
	("fee", _("Fee paid"), reached(7)),
	("enrolled", _("Enrolled"), G["enrolled"]),
]
STEP_STATUSES = {k: s for k, _l, s in STEPS}

# Stage = where an applicant stands now (the pill used in tables).
STAGES = [
	("Applying", G["draft"] + G["submitted"]),
	("In process", G["test_scheduled"] + G["test_done"] + G["iv_scheduled"] + G["iv_done"]
		+ G["iv_exempted"] + G["merit_selected"] + G["seat_selected"] + G["offer_issued"]),
	("Waitlisted", G["merit_waitlisted"] + G["seat_waitlisted"]),
	("Offer / Admitted", G["offer_accepted"] + G["conf_fee"] + G["full_fee"] + G["enrolled"]),
	("Not admitted", NOT_ADMITTED),
]
STAGE_OF = {s: name for name, sts in STAGES for s in sts}
ENDED = set(G["enrolled"]) | set(NOT_ADMITTED)

REG_STATES = ["Draft", "Selected", "Pending REGO", "Pending FINO", "Pending Registration",
	"Pending Print & Scan", "Pending Residences", "Pending IT", "Final Verification REGO",
	"Completed", "Re-Open"]
LEFT_STATUSES = ["Inactive", "Dropped", "Dormant", "Withdrawn"]
PENDING_CONDONATION = ["Pending", "May Be Approved"]
OPEN_DEMAND = ["Pending", "Partially Paid", "Overdue"]
TRANSCRIPT_OPEN = ["Payment Pending", "Submitted", "Under Review", "Approved"]
PROMOTED = ["Promoted", "Override - Promoted"]
# Razorpay success states. Live FLE records a successful payment as "Authorized".
FLE_PAID = ["Authorized", "Captured"]
SETTLED = ["processed", "Settled"]
PACE_PAY_REF = "PACE Applicant Fee Assignment"
NOT_PROMOTED = ["Not Promoted", "Override - Not Promoted"]


# ── Filters ──────────────────────────────────────────────────────────────────
LIST_FILTERS = ["programmes", "academic_years", "admission_cycles", "genders", "categories", "stages"]


def _ctx(filters):
	f = frappe.parse_json(filters) if filters else {}
	f = f or {}
	ctx = frappe._dict(from_date=f.get("from_date") or None, to_date=f.get("to_date") or None)
	for k in LIST_FILTERS:
		v = f.get(k) or []
		if isinstance(v, str):
			v = [v]
		ctx[k] = [str(x) for x in v if x not in (None, "")]
	return ctx


def _date_range(ctx, field, is_date=False):
	out = []
	if ctx.from_date:
		out.append([field, ">=", ctx.from_date if is_date else f"{ctx.from_date} 00:00:00"])
	if ctx.to_date:
		out.append([field, "<=", ctx.to_date if is_date else f"{ctx.to_date} 23:59:59"])
	return out


def _in(field, values):
	return [field, "in", list(values) or [NONE]]


def _students_of(ctx):
	"""Students matching the programme / gender / category filters, or None when
	none of those is set. Used only to scope student-keyed records, never returned."""
	if not (ctx.programmes or ctx.genders or ctx.categories):
		return None
	cache = getattr(frappe.local, "uod_students_of", None)
	if cache is None:
		cache = frappe.local.uod_students_of = {}
	sig = json.dumps([ctx.programmes, ctx.genders, ctx.categories])
	if sig not in cache:
		f = []
		if ctx.programmes:
			f.append(["programme_of_study", "in", ctx.programmes])
		if ctx.genders:
			f.append(["gender", "in", ctx.genders])
		if ctx.categories:
			f.append(["quota", "in", ctx.categories])
		cache[sig] = frappe.get_all(STU, filters=f, pluck="name")
	return cache[sig]


def _classes_of(ctx):
	if not (ctx.programmes or ctx.academic_years):
		return None
	f = []
	if ctx.programmes:
		f.append(["programme", "in", ctx.programmes])
	if ctx.academic_years:
		f.append(["academic_year", "in", ctx.academic_years])
	return frappe.get_all("Classes", filters=f, pluck="name")


# ── Sources: one per DocType the board reads ────────────────────────────────
# prog: Programme field, "name" (the Programme itself), "@student" (scope via
#   the student's programme), "@class" (scope via Classes.programme) or None.
# year / date / gender / category / cycle: fields the filters map onto.
# columns: (field, label, type) — type drives rendering on the client.
def _src(doctype, label, columns, search, sort, prog=None, year=None, date=None,
		gender=None, category=None, cycle=None, base=None, person=None):
	return {"doctype": doctype, "label": label, "columns": columns, "search": search, "sort": sort,
		"prog": prog, "year": year, "date": date, "gender": gender,
		"category": category, "cycle": cycle, "base": base or [], "person": person}


C_STUDENT = [("student", _("Student ID"), "student"), ("student_name", _("Student"), "text")]

SOURCES = {
	"app": _src(APP, _("Applicants"),
		[("name", _("Applicant ID"), "applicant"), ("candidate_name", _("Applicant"), "person"), ("program", _("Programme"), "programme"),
			("admission_cycle", _("Admission cycle"), "text"), ("status", _("Status"), "text"), ("stage", _("Stage"), "stage"),
			("application_fee_status", _("App. fee"), "text"), ("email", _("Email"), "text"), ("mobile_number", _("Mobile"), "text"),
			("creation", _("Applied on"), "date"), ("days", _("In pipeline"), "days")],
		["name", "candidate_name", "email", "mobile_number"], "creation",
		prog="program", year="academic_year", date="creation", gender="gender",
		category="whether_scstobc_ncl", cycle="admission_cycle", person="app"),
	"stu": _src(STU, _("Students"),
		[("name", _("Student ID"), "student"), ("first_name", _("Student"), "person"), ("programme_of_study", _("Programme"), "programme"),
			("batch", _("Batch"), "text"), ("section", _("Section"), "text"), ("registration_status", _("Registration"), "text"),
			("student_status", _("Student status"), "text"), ("application_number", _("Application"), "text"),
			("email", _("Email"), "text"), ("phone", _("Phone"), "text"), ("creation", _("Created on"), "date")],
		["name", "first_name", "email", "phone", "application_number"], "creation",
		prog="programme_of_study", year="academic_year", date="creation", gender="gender",
		category="quota", person="stu"),
	"isa": _src(ISA, _("Interview slots"),
		[("applicant", _("Applicant ID"), "applicant"), ("candidate_name", _("Applicant"), "text"), ("program", _("Programme"), "programme"),
			("interview_date", _("Date"), "date"), ("interview_time", _("Time"), "text"), ("interview_slot_status", _("Slot"), "text"),
			("staff_name", _("Interviewer"), "text"), ("interview_attendance_confirmation", _("Attendance"), "text"),
			("admission_cycle", _("Admission cycle"), "text")],
		["applicant", "candidate_name", "email", "staff_name"], "interview_date",
		prog="program", year="academic_year", cycle="admission_cycle"),
	"audit": _src(AUDIT, _("Admission log"),
		[("performed_on", _("Changed on"), "datetime"), ("applicant", _("Applicant ID"), "applicant"), ("program", _("Programme"), "programme"),
			("action", _("Action"), "text"), ("field_changed", _("Field"), "text"), ("old_value", _("From"), "text"),
			("new_value", _("To"), "text"), ("performed_by", _("Changed by"), "text"), ("remarks", _("Reason"), "text")],
		["applicant", "action", "remarks", "performed_by"], "performed_on",
		prog="program", date="performed_on", base=[["applicant", "is", "set"]]),
	"enr": _src("Student Enrollment", _("Enrolments"),
		[("name", _("Enrolment"), "id"), ("student", _("Student ID"), "student"), ("program", _("Programme"), "programme"),
			("batch", _("Batch"), "text"), ("section", _("Section"), "text"), ("faculty_advisor", _("Advisor"), "text"),
			("status", _("Status"), "text"), ("enrollment_date", _("Enrolled on"), "date")],
		["name", "student"], "enrollment_date", prog="program", date="enrollment_date"),
	"prog": _src("Programme", _("Programmes"),
		[("name", _("Programme"), "id"), ("program_name", _("Name"), "text"), ("program_code", _("Code"), "text"),
			("level_of_study", _("Level"), "text"), ("program_duration", _("Years"), "text"), ("program_status", _("Status"), "text")],
		["name", "program_name", "program_code"], "program_name", prog="name"),
	"course": _src("Course", _("Courses"),
		[("name", _("Course"), "id"), ("course_name", _("Name"), "text"), ("course_code", _("Code"), "text"),
			("course_type", _("Type"), "text"), ("credit_value", _("Credits"), "text"), ("status", _("Status"), "text")],
		["name", "course_name", "course_code"], "course_name"),
	"cls": _src("Classes", _("Classes"),
		[("name", _("Class"), "id"), ("course_name", _("Course"), "text"), ("programme", _("Programme"), "programme"),
			("academic_year", _("Academic year"), "text"), ("academic_term", _("Term"), "text"), ("section", _("Section"), "text"),
			("faculty_name", _("Faculty"), "text"), ("total_students", _("Students"), "text")],
		["name", "course_name", "faculty_name"], "course_name", prog="programme", year="academic_year"),
	"batch": _src("SLCM Batch", _("Batches"),
		[("name", _("Batch"), "id"), ("batch_name", _("Name"), "text"), ("batch_code", _("Code"), "text"),
			("academic_year", _("Academic year"), "text"), ("total_enrolled_count", _("Enrolled"), "text"), ("status", _("Status"), "text")],
		["name", "batch_name", "batch_code"], "name", year="academic_year"),
	"fac": _src("Faculty", _("Faculty"),
		[("name", _("Faculty"), "id"), ("first_name", _("First name"), "text"), ("last_name", _("Last name"), "text"),
			("designation", _("Designation"), "text"), ("email", _("Email"), "text"), ("status", _("Status"), "text")],
		["name", "first_name", "last_name", "email"], "first_name"),
	"ses": _src("Attendance Session", _("Attendance sessions"),
		[("name", _("Session"), "id"), ("session_date", _("Date"), "date"), ("course", _("Course"), "text"), ("class_name", _("Class"), "text"),
			("section", _("Section"), "text"), ("instructor", _("Instructor"), "text"), ("session_status", _("Status"), "text"),
			("attendance_marked", _("Marked"), "check"), ("present_count", _("Present"), "text"), ("absent_count", _("Absent"), "text"),
			("attendance_percentage", _("Attendance"), "pct")],
		["name", "course", "class_name", "instructor"], "session_date", prog="@class", date="session_date"),
	"att": _src("Student Attendance", _("Attendance records"),
		C_STUDENT + [("program", _("Programme"), "programme"), ("course", _("Course"), "text"), ("attendance_date", _("Date"), "date"),
			("status", _("Status"), "text"), ("source", _("Source"), "text"), ("attendance_session", _("Session"), "text")],
		["student", "student_name", "course"], "attendance_date", prog="program", year="academic_year", date="attendance_date"),
	"summ": _src("Attendance Summary", _("Attendance summary"),
		C_STUDENT + [("programme", _("Programme"), "programme"), ("course", _("Course"), "text"), ("section", _("Section"), "text"),
			("attended_classes", _("Attended"), "text"), ("total_classes", _("Classes"), "text"),
			("attendance_percentage", _("Attendance"), "pct"), ("minimum_required_percentage", _("Required"), "pct"),
			("eligible_for_exam", _("Eligible"), "check")],
		["student", "student_name", "course"], "attendance_percentage", prog="programme", year="academic_year"),
	"cond": _src("Student Attendance Condonation", _("Condonation requests"),
		[("name", _("Request"), "id")] + C_STUDENT + [("programme", _("Programme"), "programme"), ("course", _("Course"), "text"),
			("condonation_reason", _("Reason"), "text"), ("number_of_sessions", _("Sessions"), "text"),
			("submitted_date", _("Submitted"), "date"), ("final_status", _("Status"), "text")],
		["name", "student", "student_name", "course"], "submitted_date", prog="programme", year="academic_year",
		date="submitted_date", base=[["docstatus", "<", 2]]),
	"tt": _src("Time Table", _("Timetable"),
		[("name", _("Class slot"), "id"), ("schedule_date", _("Date"), "date"), ("course", _("Course"), "text"),
			("programme", _("Programme"), "programme"), ("section", _("Section"), "text"), ("instructor_name", _("Instructor"), "text"),
			("venue", _("Venue"), "text"), ("session_status", _("Status"), "text")],
		["name", "course", "instructor_name", "venue"], "schedule_date", prog="programme", year="academic_year", date="schedule_date"),
	"exam": _src("Exam Plan", _("Exam plans"),
		[("name", _("Exam plan"), "id"), ("exam_name", _("Exam"), "text"), ("term", _("Term"), "text"), ("status", _("Status"), "text"),
			("timetable_published", _("Timetable published"), "check")],
		["name", "exam_name"], "modified"),
	"marks": _src("Student Course Marks", _("Course marks"),
		[("student", _("Student ID"), "student"), ("student_id", _("Registration no."), "text"), ("course", _("Course"), "text"),
			("exam_plan", _("Exam plan"), "text"), ("total_marks", _("Marks"), "text"), ("grade", _("Grade"), "text"),
			("status", _("Status"), "text")],
		["student", "student_id", "course", "exam_plan"], "modified", prog="@student"),
	"res": _src("Student Result Publish", _("Results"),
		[("student", _("Student ID"), "student"), ("exam_plan", _("Exam plan"), "text"), ("term_gpa", _("Term GPA"), "text"),
			("cumulative_gpa", _("CGPA"), "text"), ("is_published", _("Published"), "check"), ("published_on", _("Published on"), "datetime")],
		["student", "exam_plan"], "modified", prog="@student"),
	"appeal": _src("Grade Appeal", _("Grade appeals"),
		[("name", _("Appeal"), "id"), ("student", _("Student ID"), "student"), ("course", _("Course"), "text"),
			("exam_plan", _("Exam plan"), "text"), ("appeal_type", _("Type"), "text"), ("current_grade", _("Grade"), "text"),
			("revised_grade", _("Revised"), "text"), ("submitted_on", _("Submitted"), "datetime"), ("status", _("Status"), "text")],
		["name", "student", "course"], "submitted_on", prog="@student", date="submitted_on"),
	"dem": _src("Fee Demand", _("Fee demands"),
		[("name", _("Demand"), "id")] + C_STUDENT + [("program", _("Programme"), "programme"), ("fee_component", _("Component"), "text"),
			("net_payable", _("Payable"), "currency"), ("paid_amount", _("Paid"), "currency"),
			("outstanding_amount", _("Outstanding"), "currency"), ("due_date", _("Due"), "date"), ("status", _("Status"), "text")],
		["name", "student", "student_name", "fee_component"], "due_date", prog="program", year="academic_year",
		base=[["status", "!=", "Cancelled"]]),
	"pay": _src("Fee Payment", _("Fee payments"),
		[("name", _("Payment"), "id")] + C_STUDENT + [("program", _("Programme"), "programme"), ("fee_component", _("Component"), "text"),
			("paid_amount", _("Amount"), "currency"), ("payment_mode", _("Mode"), "text"), ("payment_date", _("Paid on"), "date"),
			("reference_number", _("Reference"), "text")],
		["name", "student", "student_name", "reference_number"], "payment_date", prog="program", year="academic_year",
		date="payment_date", base=[["docstatus", "=", 1]]),
	"ref": _src("Fee Refund", _("Fee refunds"),
		[("name", _("Refund"), "id")] + C_STUDENT + [("refund_type", _("Type"), "text"), ("refund_amount", _("Amount"), "currency"),
			("refund_mode", _("Mode"), "text"), ("refund_date", _("Refunded on"), "date"), ("status", _("Status"), "text")],
		["name", "student", "student_name"], "refund_date", prog="@student", date="refund_date", base=[["docstatus", "=", 1]]),
	"con": _src("Fee Concession", _("Fee concessions"),
		[("name", _("Concession"), "id"), ("student", _("Student ID"), "student"), ("registration_id", _("Registration no."), "text"),
			("concession_type", _("Type"), "text"), ("waiver_value", _("Waiver"), "currency"), ("concession_date", _("Date"), "date"),
			("status", _("Status"), "text")],
		["name", "student", "registration_id"], "concession_date", prog="@student", year="academic_year",
		date="concession_date", base=[["docstatus", "=", 1]]),
	"idc": _src("ID Card Generation", _("ID cards"),
		[("name", _("Card"), "id")] + C_STUDENT + [("programme", _("Programme"), "programme"), ("batch", _("Batch"), "text"),
			("card_status", _("Status"), "text"), ("issue_date", _("Issued"), "date"), ("expiry_date", _("Expires"), "date"),
			("print_count", _("Prints"), "text")],
		["name", "student", "student_name"], "modified", prog="programme", year="academic_year",
		base=[["card_type", "=", "Student"]]),
	"ven": _src("Venue Booking", _("Venue bookings"),
		[("name", _("Booking"), "id"), ("event_name", _("Event"), "text"), ("venue", _("Venue"), "text"), ("building", _("Building"), "text"),
			("start_datetime", _("Starts"), "datetime"), ("end_datetime", _("Ends"), "datetime"), ("requester_type", _("Requested by"), "text"),
			("requester_name", _("Requester"), "text"), ("status", _("Status"), "text")],
		["name", "event_name", "venue", "requester_name"], "start_datetime", date="start_datetime"),
	"pace": _src("PACE Application", _("PACE applications"),
		[("name", _("Application"), "id"), ("applicant_name", _("Applicant"), "text"), ("programme", _("PACE programme"), "text"),
			("academic_year", _("Academic year"), "text"), ("email_address", _("Email"), "text"),
			("submission_date", _("Submitted"), "date"), ("status", _("Status"), "text")],
		["name", "applicant_name", "email_address"], "modified", year="academic_year", date="submission_date"),
	"penq": _src("PACE Enquiry", _("PACE enquiries"),
		[("name", _("Enquiry"), "id"), ("full_name", _("Name"), "text"), ("email", _("Email"), "text"), ("phone", _("Phone"), "text"),
			("programme_of_interest", _("Programme"), "text"), ("submitted_on", _("Submitted"), "datetime"), ("status", _("Status"), "text")],
		["name", "full_name", "email"], "submitted_on", date="submitted_on"),
	"pdv": _src("PACE Document Verification", _("PACE document checks"),
		[("name", _("Verification"), "id"), ("application", _("Application"), "text"), ("applicant_name", _("Applicant"), "text"),
			("programme", _("PACE programme"), "text"), ("assigned_verifier", _("Verifier"), "text"),
			("due_date", _("Due"), "date"), ("status", _("Status"), "text")],
		["name", "applicant_name", "application"], "due_date", year="academic_year"),
	"treq": _src("Transcript Request", _("Transcript requests"),
		[("name", _("Request"), "id")] + C_STUDENT + [("programme", _("Programme"), "programme"), ("transcript_type", _("Type"), "text"),
			("num_copies", _("Copies"), "text"), ("delivery_mode", _("Delivery"), "text"), ("urgency", _("Urgency"), "text"),
			("requested_on", _("Requested"), "date"), ("payment_status", _("Payment"), "text"), ("status", _("Status"), "text")],
		["name", "student", "student_name"], "requested_on", prog="programme", date="requested_on"),
	"trans": _src("Student Transcript", _("Transcripts issued"),
		[("name", _("Transcript"), "id")] + C_STUDENT + [("transcript_type", _("Type"), "text"), ("generation_date", _("Generated"), "date"),
			("generated_by", _("By"), "text"), ("transcript_request", _("Request"), "text"), ("status", _("Status"), "text")],
		["name", "student", "student_name"], "generation_date", prog="@student", date="generation_date"),
	"sprom": _src("Student Promotion", _("Promotion decisions"),
		C_STUDENT + [("current_year", _("Year"), "text"), ("target_year", _("To year"), "text"), ("promotion_status", _("Decision"), "text"),
			("current_cgpa", _("CGPA"), "text"), ("backlog_count", _("Backlogs"), "text"), ("attendance_percent", _("Attendance"), "pct"),
			("stage", _("Stage"), "text"), ("enrollment_status", _("Next-year enrolment"), "text"), ("published_on", _("Published"), "datetime")],
		["student", "student_name"], "modified", prog="@student", date="processed_on"),
	"prun": _src("Promotion Run", _("Promotion runs"),
		[("name", _("Run"), "id"), ("program", _("Programme"), "programme"), ("source_academic_year", _("From year"), "text"),
			("target_academic_year", _("To year"), "text"), ("batch", _("Batch"), "text"), ("total_students", _("Students"), "text"),
			("promoted_count", _("Promoted"), "text"), ("skipped_count", _("Skipped"), "text"), ("run_on", _("Run on"), "datetime"),
			("status", _("Status"), "text")],
		["name", "program", "batch"], "run_on", prog="program", year="source_academic_year", date="run_on"),
	"ppol": _src("Promotion Policy", _("Promotion policies"),
		[("name", _("Policy"), "id"), ("title", _("Title"), "text"), ("program", _("Programme"), "programme"),
			("academic_year", _("Academic year"), "text"), ("from_year", _("From year"), "text"), ("to_year", _("To year"), "text"),
			("min_cgpa", _("Min CGPA"), "text"), ("min_attendance_percent", _("Min attendance"), "pct"), ("status", _("Status"), "text")],
		["name", "title", "program"], "modified", prog="program", year="academic_year"),
	"pfa": _src("PACE Applicant Fee Assignment", _("PACE fee assignments"),
		[("name", _("Assignment"), "id"), ("applicant", _("Application"), "text"), ("applicant_name", _("Applicant"), "text"),
			("program", _("PACE programme"), "text"), ("fee_type", _("Fee"), "text"), ("nationality_type", _("Nationality"), "text"),
			("final_payable_amount", _("Payable"), "currency"), ("assignment_date", _("Assigned on"), "date"),
			("payment_date", _("Paid on"), "date"), ("status", _("Status"), "text")],
		["name", "applicant", "applicant_name", "transaction_id"], "assignment_date", year="academic_year", date="assignment_date"),
	"prc": _src("PACE Receipt", _("PACE receipts"),
		[("name", _("Receipt"), "id"), ("pace_application", _("Application"), "text"), ("applicant_name", _("Applicant"), "text"),
			("program", _("PACE programme"), "text"), ("fee_type", _("Fee"), "text"), ("amount", _("Amount"), "currency"),
			("payment_date", _("Paid on"), "date"), ("transaction_id", _("Transaction"), "text")],
		["name", "pace_application", "applicant_name", "transaction_id"], "payment_date", year="academic_year", date="payment_date"),
	"spr": _src("SLCM Payment Request", _("PACE online payments"),
		[("name", _("Payment request"), "id"), ("reference_name", _("Fee assignment"), "text"), ("email_to", _("Payer"), "text"),
			("amount", _("Amount"), "currency"), ("status", _("Status"), "text"), ("gateway_status", _("Gateway"), "text"),
			("payment_method", _("Method"), "text"), ("paid_on", _("Paid on"), "date"), ("settlement_status", _("Settlement"), "text"),
			("net_settled", _("Net settled"), "currency"), ("gateway_fees", _("Gateway fees"), "currency"), ("creation", _("Created"), "datetime")],
		["name", "reference_name", "email_to", "transaction_id", "razorpay_payment_id"], "creation",
		date="creation", base=[["reference_doctype", "=", PACE_PAY_REF], ["docstatus", "<", 2]]),
	"flp": _src("FLE Payment Log", _("FLE payments"),
		[("name", _("Payment"), "id"), ("reference_no", _("Registration"), "text"), ("full_name", _("Candidate"), "text"),
			("email", _("Email"), "text"), ("payment_status", _("Status"), "text"), ("paid_amount", _("Amount"), "currency"),
			("transaction_date", _("Paid on"), "datetime"), ("settlement_status", _("Settlement"), "text"),
			("net_settled", _("Net settled"), "currency"), ("transaction_id", _("Transaction"), "text")],
		["name", "reference_no", "full_name", "email", "transaction_id"], "transaction_date", date="transaction_date"),
	"fle": _src("Foundations for a Legal Education", _("FLE registrations"),
		[("name", _("Registration"), "id"), ("candidate_name", _("Candidate"), "text"), ("candidate_email_id", _("Email"), "text"),
			("last_class_attended", _("Last class"), "text"), ("timestamp", _("Registered"), "datetime"),
			("enrollment_status", _("Enrolment"), "text"), ("payment_status", _("Payment"), "text"), ("paid_amount", _("Paid"), "currency")],
		["name", "candidate_name", "candidate_email_id"], "timestamp", date="timestamp"),
}


def _is_date_field(doctype, field):
	"""True for a Date field; Datetime fields (and creation) need the time on the bounds."""
	df = frappe.get_meta(doctype).get_field(field)
	return bool(df and df.fieldtype == "Date")


def src_filters(kind, ctx, with_dates=True):
	s = SOURCES[kind]
	out = list(s["base"])
	if with_dates and s["date"]:
		out += _date_range(ctx, s["date"], _is_date_field(s["doctype"], s["date"]))
	if ctx.programmes:
		if s["prog"] == "@student":
			out.append(_in("student", _students_of(ctx)))
		elif s["prog"] == "@class":
			out.append(_in("class_name", _classes_of(ctx)))
		elif s["prog"]:
			out.append([s["prog"], "in", ctx.programmes])
	if ctx.academic_years:
		if s["year"]:
			out.append([s["year"], "in", ctx.academic_years])
		elif s["prog"] == "@class":
			out.append(_in("class_name", _classes_of(ctx)))
	if ctx.admission_cycles and s["cycle"]:
		out.append([s["cycle"], "in", ctx.admission_cycles])
	if ctx.genders:
		if s["gender"]:
			out.append([s["gender"], "in", ctx.genders])
		elif s["prog"] == "@student":
			out.append(_in("student", _students_of(ctx)))
	if ctx.categories:
		if s["category"]:
			out.append([s["category"], "in", ctx.categories])
		elif s["prog"] == "@student":
			out.append(_in("student", _students_of(ctx)))
	if ctx.stages and kind == "app":
		sts = [st for name, group in STAGES if name in ctx.stages for st in group]
		out.append(_in("status", sts))
	return out


def honours(kind):
	"""Which filters a source responds to (shown in the Card guide)."""
	s = SOURCES[kind]
	out = []
	if s["date"]:
		out.append(_("dates"))
	if s["prog"]:
		out.append(_("programme"))
	if s["year"] or s["prog"] == "@class":
		out.append(_("academic year"))
	if s["cycle"]:
		out.append(_("admission cycle"))
	if s["gender"] or s["prog"] == "@student":
		out.append(_("gender"))
	if s["category"] or s["prog"] == "@student":
		out.append(_("category"))
	if kind == "app":
		out.append(_("stage"))
	return out


def f_app(ctx, with_dates=True):
	return src_filters("app", ctx, with_dates)


def f_stu(ctx, with_dates=True):
	return src_filters("stu", ctx, with_dates)


# ── Card registry ────────────────────────────────────────────────────────────
# kind: a SOURCES key. statuses: Applicant statuses (counted from one grouped
# query). filters(ctx) / or_filters(ctx): extra conditions. dates: False =
# "right now" backlog card that ignores the date range. sum: currency field
# totalled alongside the count.
# unused_if: key of the "positive" card of a pair. When that card is 0 the field
# is not being filled in at all, so this card would claim 100% — it is shown as
# "not recorded yet" instead.
def _card(key, label, tone, kind="app", statuses=None, filters=None, or_filters=None, sub=None, guide=None,
		pct=True, dates=True, sum=None, unused_if=None):
	return {"key": key, "label": label, "tone": tone, "kind": kind, "statuses": statuses, "filters": filters,
		"or_filters": or_filters, "sub": sub, "guide": guide, "pct": pct, "dates": dates, "sum": sum, "unused_if": unused_if}


CARDS = {}
HEADLINE = []
BOARD = []


def _register(card):
	CARDS[card["key"]] = card
	return card


def _f(*conds):
	return lambda c, conds=conds: [list(x) for x in conds]


def _pace_statuses(kind):
	rows = frappe.get_all("PACE Application Status", fields=["name", "status_type", "stage_type"])
	enrolled = {r.name for r in rows if (r.stage_type or "").startswith("Enrol")}
	closed = {r.name for r in rows if r.status_type == "Closed"} - enrolled
	if kind == "enrolled":
		return sorted(enrolled)
	if kind == "closed":
		return sorted(closed)
	return sorted({r.name for r in rows} - enrolled - closed)


def _build_registry():
	def h(key, label, tone, statuses, sub, guide):
		HEADLINE.append(_register(_card(key, label, tone, statuses=statuses, sub=sub, guide=guide)))

	h("total", _("Total applications"), "neutral", None, _("in the selected period"),
		_("Every application whose created date is in the selected range, after all the filters above."))
	h("submitted", _("Submitted"), "neutral", STEP_STATUSES["submitted"], _("of total applications"),
		_("Submitted the application — includes everyone who went on to a test, interview, merit list, offer or enrolment, even if turned down later."))
	h("merit", _("Merit selected"), "neutral", STEP_STATUSES["merit"], _("of total applications"),
		_("Selected in a merit list, or went further (seat, offer, fees, enrolled) — even if the seat or offer was later declined."))
	h("accepted", _("Offer accepted"), "good", STEP_STATUSES["accepted"], _("of total applications"),
		_("Accepted the offer, or has already paid the confirmation / full fee or enrolled."))
	h("enrolled", _("Enrolled"), "good", STEP_STATUSES["enrolled"], _("of total applications"),
		_("Applicant status is Enrolled."))
	h("not_admitted", _("All rejected"), "bad", NOT_ADMITTED, _("of total applications"),
		_("Turned down or dropped out at any step: Rejected, Withdrawn, Entrance Test Rejected, Interview Rejected, Merit Rejected, Seat Rejected, Offer Declined, Offer Expired."))

	def section(key, title, tiles):
		BOARD.append({"key": key, "title": title, "tiles": tiles})

	def tile(title, icon, cards):
		return {"title": title, "icon": icon, "cards": [_register(c) for c in cards]}

	def app(key, label, tone, statuses, guide, sub=None):
		return _card(key, label, tone, statuses=statuses, guide=guide, sub=sub)

	# ── At a glance (one figure per programme family, above the admission funnel) ──
	section("overview", _("At a glance"), [
		tile(_("Students"), "users", [_card("ov_students", _("Active students"), "good", kind="stu", pct=False, dates=False,
			filters=_f(["student_status", "=", "Active"]), sub=_("Student Master, status Active"), guide=_("All active students in scope (any date)."))]),
		tile(_("Regular admission"), "file", [_card("ov_apps", _("Applications"), "neutral", pct=False, sub=_("Applicant records in the dates"),
			guide=_("Regular admission applications (Applicant) created in the selected dates."))]),
		tile(_("PACE"), "award", [
			_card("ov_pace_apps", _("Applications"), "info", kind="pace", pct=False, filters=_f(["status", "!=", "Draft"]),
				guide=_("PACE applications submitted (not Draft) in the selected dates.")),
			_card("ov_pace_enr", _("Enrolled"), "good", kind="pace", pct=False, filters=lambda c: [_in("status", _pace_statuses("enrolled"))],
				guide=_("PACE applications at an enrolment stage."))]),
		tile(_("FLE"), "users", [
			_card("ov_fle", _("Registrations"), "info", kind="fle", pct=False, guide=_("FLE registrations in the selected dates.")),
			_card("ov_fle_paid", _("Paid"), "good", kind="fle", pct=False, filters=_f(["payment_status", "in", FLE_PAID]),
				guide=_("FLE registrations whose payment is Authorized or Captured."))]),
		tile(_("Money received"), "coins", [
			_card("ov_pace_money", _("PACE"), "good", kind="spr", pct=False, filters=_f(["status", "=", "Paid"]), sum="amount",
				guide=_("PACE online payments (SLCM Payment Request) with status Paid, created in the selected dates.")),
			_card("ov_fle_money", _("FLE"), "good", kind="flp", pct=False, filters=_f(["payment_status", "in", FLE_PAID]), sum="paid_amount",
				guide=_("FLE payments (FLE Payment Log) Authorized or Captured, in the selected dates."))]),
	])

	# ── Admission ──
	section("admission", _("Admission · application & test"), [
		tile(_("Draft applications"), "pen", [app("draft", _("Draft"), "action", G["draft"], _("Started but not submitted (status Draft)."), _("not yet submitted"))]),
		tile(_("Application review"), "file", [app("awaiting_review", _("Awaiting review"), "info", G["submitted"],
			_("Status Submitted or Submitted and Paid — waiting for the test / interview / merit step."), _("submitted, no next step yet"))]),
		tile(_("Application fee"), "coins", [
			_card("appfee_paid", _("Fee paid"), "good", filters=_f(["status", "!=", "Draft"], ["application_fee_status", "in", ["Paid", "Waived"]]),
				guide=_("Submitted applications whose application fee is Paid or Waived.")),
			_card("appfee_pending", _("Fee pending"), "action", filters=_f(["status", "!=", "Draft"], ["application_fee_status", "in", ["Pending", "Requested"]]),
				guide=_("Submitted applications whose application fee is Pending or Requested."))]),
		tile(_("Entrance test"), "pen", [
			app("test_scheduled", _("Test scheduled"), "info", G["test_scheduled"], _("Status Entrance Test Allocated or Entrance Test Scheduled.")),
			app("test_done", _("Test done"), "good", G["test_done"], _("Status Entrance Test Completed, or exempted from the entrance test."))]),
	])
	section("admission", _("Admission · interviews & merit"), [
		tile(_("Interview"), "mic", [
			app("iv_scheduled", _("Interview scheduled"), "info", G["iv_scheduled"], _("Status Interview Scheduled.")),
			app("iv_done", _("Interview completed"), "good", G["iv_done"], _("Status Interview Completed."))]),
		tile(_("Interview outcome"), "check", [
			app("iv_exempted", _("Exempted"), "info", G["iv_exempted"], _("Status Interview Exempted.")),
			app("iv_rejected", _("Rejected"), "bad", G["iv_rejected"], _("Status Interview Rejected."))]),
		tile(_("Interviews today"), "clock", [
			_card("iv_today", _("Interviews today"), "time", kind="isa", dates=False, pct=False, sub=_("scheduled for today"),
				filters=lambda c: [["interview_date", "=", nowdate()], ["interview_slot_status", "!=", "Cancelled"]],
				guide=_("Interview slots (Interview Seat Allocation) dated today and not cancelled."))]),
		tile(_("Next 7 days"), "calendar", [
			_card("iv_next7", _("Next 7 days"), "neutral", kind="isa", dates=False, pct=False, sub=_("interviews coming up"),
				filters=lambda c: [["interview_date", ">", nowdate()], ["interview_date", "<=", add_days(nowdate(), 7)],
					["interview_slot_status", "!=", "Cancelled"]],
				guide=_("Interview slots in the next 7 days, not cancelled."))]),
		tile(_("Merit list"), "award", [
			app("merit_selected", _("Merit selected"), "good", G["merit_selected"], _("Status Merit Selected, Merit Published or Selected — on a merit list, seat not yet allocated.")),
			app("merit_waitlisted", _("Waitlisted"), "action", G["merit_waitlisted"], _("Status Merit Waitlisted or Waitlisted."))]),
		tile(_("Merit rejected"), "xcircle", [app("merit_rejected", _("Merit rejected"), "bad", G["merit_rejected"] + G["test_rejected"],
			_("Status Merit Rejected or Entrance Test Rejected."))]),
	])
	section("admission", _("Admission · seat, offer & fees"), [
		tile(_("Seat allocation"), "handshake", [
			app("seat_selected", _("Seat selected"), "good", G["seat_selected"], _("Status Seat Selected — seat allocated, offer not yet issued.")),
			app("seat_waitlisted", _("Seat waitlisted"), "action", G["seat_waitlisted"] + G["seat_rejected"], _("Status Seat Waitlisted or Seat Rejected."))]),
		tile(_("Offer letter"), "send", [
			app("offer_issued", _("Offer issued"), "info", G["offer_issued"], _("Status Offer Issued — the applicant has not replied yet."), _("awaiting reply")),
			app("offer_expired", _("Offer expired"), "bad", G["offer_expired"], _("Status Offer Expired."))]),
		tile(_("Offer response"), "handshake", [
			app("offer_accepted", _("Offer accepted"), "good", G["offer_accepted"], _("Status Offer Accepted or Accepted (no fee paid yet)."), _("fee not yet paid")),
			app("offer_declined", _("Offer declined"), "bad", G["offer_declined"], _("Status Offer Declined."))]),
		tile(_("Admission fees"), "coins", [
			app("conf_fee", _("Confirmation fee paid"), "good", G["conf_fee"], _("Status Confirmation Fee Paid.")),
			app("full_fee", _("Full fee paid"), "good", G["full_fee"], _("Status Full Fee Paid or Fee Paid."))]),
		tile(_("Enrolled"), "door", [app("enrolled_now", _("Enrolled"), "good", G["enrolled"], _("Status Enrolled."))]),
		tile(_("Withdrawn"), "xcircle", [app("withdrawn", _("Withdrawn"), "bad", G["withdrawn"] + G["rejected"], _("Status Withdrawn or Rejected."))]),
	])

	# ── Student Registration ──
	def stu(key, label, tone, conds, guide, **kw):
		return _card(key, label, tone, kind="stu", filters=_f(*conds), guide=guide, **kw)

	def reg(key, label, tone, states, guide):
		return stu(key, label, tone, [["registration_status", "in", states]], guide)

	section("registration", _("Student registration"), [
		tile(_("Student status"), "users", [
			stu("stu_active", _("Active"), "good", [["student_status", "=", "Active"]], _("Student status Active.")),
			stu("stu_left", _("Left / inactive"), "bad", [["student_status", "in", LEFT_STATUSES]], _("Student status Inactive, Dropped, Dormant or Withdrawn."))]),
		tile(_("Selected"), "users", [reg("reg_selected", _("Awaiting student"), "action", ["Selected", "Draft"],
			_("Student records at Draft or Selected — the student has not submitted the registration form yet."))]),
		tile(_("REGO & FINO"), "clipboard", [
			reg("reg_rego", _("Pending REGO"), "info", ["Pending REGO"], _("Registration status Pending REGO (REGO Officer).")),
			reg("reg_fino", _("Pending FINO"), "info", ["Pending FINO"], _("Registration status Pending FINO (FINO Officer)."))]),
		tile(_("Registration desk"), "filesign", [
			reg("reg_desk", _("Pending registration"), "info", ["Pending Registration"], _("Registration status Pending Registration.")),
			reg("reg_print", _("Pending print & scan"), "info", ["Pending Print & Scan"], _("Registration status Pending Print & Scan."))]),
		tile(_("Residences & IT"), "door", [
			reg("reg_res", _("Pending residences"), "info", ["Pending Residences"], _("Registration status Pending Residences.")),
			reg("reg_it", _("Pending IT"), "info", ["Pending IT"], _("Registration status Pending IT."))]),
		tile(_("Final verification"), "check", [
			reg("reg_final", _("Final verification"), "action", ["Final Verification REGO"], _("Registration status Final Verification REGO.")),
			reg("reg_done", _("Completed"), "good", ["Completed"], _("Registration status Completed."))]),
		tile(_("Re-opened"), "alert", [reg("reg_reopen", _("Re-opened"), "bad", ["Re-Open"], _("Registration status Re-Open — sent back for correction."))]),
	])
	section("registration", _("Onboarding"), [
		tile(_("Laptop"), "idcard", [
			stu("laptop_yes", _("Laptop issued"), "good", [["laptop_issued", "=", "Yes"]], _("Student Master: Laptop Issued = Yes.")),
			stu("laptop_no", _("Not issued"), "action", [["laptop_issued", "!=", "Yes"]], _("Student Master: Laptop Issued is No or empty."), unused_if="laptop_yes")]),
		tile(_("Bank details"), "coins", [
			stu("bank_yes", _("Submitted"), "good", [["bank_details_submitted", "=", 1]], _("The student has submitted bank details on the portal.")),
			stu("bank_no", _("Pending"), "action", [["bank_details_submitted", "=", 0]], _("Bank details not submitted yet."), unused_if="bank_yes")]),
		tile(_("Residence"), "door", [
			stu("hostel_yes", _("Room allocated"), "good", [["hostel", "is", "set"]], _("A hostel is set on the student record.")),
			stu("hostel_wait", _("Waiting for a room"), "action", [["needs_accommodation", "=", "Yes"], ["hostel", "is", "not set"]],
				_("Needs accommodation = Yes, but no hostel set yet."))]),
		tile(_("Documents verified"), "filesign", [
			stu("docs_yes", _("Verified"), "good", [["aadhaar_verified", "=", 1], ["offer_letter_verified", "=", 1], ["student_declaration_verified", "=", 1]],
				_("Aadhaar, offer letter and student declaration are all marked verified.")),
			_card("docs_no", _("Pending"), "action", kind="stu", guide=_("At least one of Aadhaar, offer letter or student declaration is not verified yet."),
				or_filters=lambda c: [["aadhaar_verified", "=", 0], ["offer_letter_verified", "=", 0], ["student_declaration_verified", "=", 0]],
				unused_if="docs_yes")]),
	])

	# ── Programme Management ──
	def card(key, label, tone, kind, conds, guide, **kw):
		return _card(key, label, tone, kind=kind, filters=_f(*conds), guide=guide, pct=kw.pop("pct", False), **kw)

	section("programme", _("Programme management"), [
		tile(_("Programmes"), "award", [
			card("prog_active", _("Active"), "good", "prog", [["program_status", "=", "Active"]], _("Programme status Active."), dates=False),
			card("prog_inactive", _("Inactive"), "neutral", "prog", [["program_status", "!=", "Active"]], _("Programme status Inactive or empty."), dates=False)]),
		tile(_("Courses"), "file", [
			card("course_active", _("Active"), "good", "course", [["status", "=", "Active"]], _("Course status Active."), dates=False),
			card("course_inactive", _("Inactive"), "neutral", "course", [["status", "!=", "Active"]], _("Course status Inactive or empty."), dates=False)]),
		tile(_("Classes"), "users", [card("classes", _("Classes"), "info", "cls", [], _("Course offerings (Classes) for the programme / academic year filters."),
			dates=False, sub=_("course offerings"))]),
		tile(_("Batches"), "calendar", [
			card("batch_active", _("Active"), "good", "batch", [["status", "=", "Active"]], _("SLCM Batch status Active."), dates=False),
			card("batch_planned", _("Planned"), "info", "batch", [["status", "=", "Planned"]], _("SLCM Batch status Planned."), dates=False)]),
		tile(_("Faculty"), "users", [
			card("fac_active", _("Active"), "good", "fac", [["status", "=", "Active"]], _("Faculty status Active."), dates=False),
			card("fac_inactive", _("Inactive"), "neutral", "fac", [["status", "=", "Inactive"]], _("Faculty status Inactive."), dates=False)]),
		tile(_("Enrolments"), "check", [
			card("enr_enrolled", _("Enrolled"), "good", "enr", [["status", "=", "Enrolled"]], _("Student Enrollment status Enrolled, enrolment date in range.")),
			card("enr_pending", _("Pending"), "action", "enr", [["status", "=", "Pending"]], _("Student Enrollment status Pending, enrolment date in range."))]),
	])

	# ── Attendance ──
	section("attendance", _("Attendance"), [
		tile(_("Sessions"), "calendar", [
			card("ses_done", _("Conducted"), "good", "ses", [["session_status", "=", "Conducted"]], _("Attendance sessions conducted in the selected dates.")),
			card("ses_unmarked", _("Attendance not entered"), "action", "ses",
				[["session_date", "<=", nowdate()], ["session_status", "!=", "Cancelled"], ["attendance_marked", "=", 0]],
				_("Past sessions in the selected dates, not cancelled, where attendance has not been marked."))]),
		tile(_("Cancelled / postponed"), "xcircle", [card("ses_cancelled", _("Cancelled / postponed"), "bad", "ses",
			[["session_status", "in", ["Cancelled", "Postponed"]]], _("Sessions cancelled or postponed in the selected dates."))]),
		tile(_("Attendance marked"), "check", [
			card("att_present", _("Present"), "good", "att", [["status", "in", ["Present", "Late", "OD"]]], _("Student attendance rows Present, Late or OD in the selected dates.")),
			card("att_absent", _("Absent"), "bad", "att", [["status", "=", "Absent"]], _("Student attendance rows Absent in the selected dates."))]),
		tile(_("Exam eligibility"), "award", [
			card("summ_ok", _("Eligible"), "good", "summ", [["eligible_for_exam", "=", 1]], _("Attendance Summary rows eligible for the exam."), dates=False),
			card("summ_low", _("Below threshold"), "action", "summ", [["eligible_for_exam", "=", 0]],
				_("Attendance Summary rows not eligible for the exam (attendance below the required %)."), dates=False)]),
		tile(_("Condonation"), "clipboard", [
			card("cond_pending", _("Awaiting decision"), "action", "cond", [["final_status", "in", PENDING_CONDONATION]],
				_("Condonation requests Pending or May Be Approved (any date)."), dates=False),
			card("cond_approved", _("Approved"), "good", "cond", [["final_status", "=", "Approved"]], _("Condonation requests approved, submitted in the selected dates."))]),
		tile(_("Classes"), "clock", [
			card("tt_today", _("Today"), "time", "tt", [["schedule_date", "=", nowdate()], ["session_status", "!=", "Cancelled"]],
				_("Timetable slots today, not cancelled."), dates=False),
			card("tt_next7", _("Next 7 days"), "neutral", "tt", [["schedule_date", ">", nowdate()], ["schedule_date", "<=", add_days(nowdate(), 7)],
				["session_status", "!=", "Cancelled"]], _("Timetable slots in the next 7 days, not cancelled."), dates=False)]),
	])

	# ── ID Card ──
	section("idcard", _("ID card"), [
		tile(_("Student ID cards"), "idcard", [
			card("idc_ready", _("Generated / printed"), "good", "idc", [["card_status", "in", ["Generated", "Printed"]]], _("Student ID cards Generated or Printed."), dates=False),
			card("idc_draft", _("Draft"), "action", "idc", [["card_status", "=", "Draft"]], _("Student ID cards still in Draft."), dates=False)]),
		tile(_("Card problems"), "alert", [
			card("idc_error", _("Error"), "bad", "idc", [["card_status", "=", "Error"]], _("Student ID cards whose generation failed."), dates=False),
			card("idc_dead", _("Cancelled / expired"), "neutral", "idc", [["card_status", "in", ["Cancelled", "Expired"]]], _("Student ID cards Cancelled or Expired."), dates=False)]),
		tile(_("Students"), "users", [
			stu("id_yes", _("ID card issued"), "good", [["id_card_issued", "=", "Yes"]], _("Student Master: ID Card Issued = Yes.")),
			stu("id_no", _("Not issued"), "action", [["id_card_issued", "!=", "Yes"]], _("Student Master: ID Card Issued is No or empty."), unused_if="id_yes")]),
	])

	# ── Fees ──
	section("fees", _("Fees"), [
		tile(_("Fee demands"), "coins", [
			card("dem_paid", _("Paid"), "good", "dem", [["status", "=", "Paid"]], _("Fee demands fully paid."), dates=False, sum="net_payable"),
			card("dem_due", _("Outstanding"), "action", "dem", [["outstanding_amount", ">", 0]], _("Fee demands with an outstanding balance."),
				dates=False, sum="outstanding_amount")]),
		tile(_("Overdue"), "alert", [card("dem_overdue", _("Overdue"), "bad", "dem",
			[["status", "in", OPEN_DEMAND], ["due_date", "<", nowdate()], ["outstanding_amount", ">", 0]],
			_("Open fee demands past their due date with money still outstanding."), dates=False, sum="outstanding_amount")]),
		tile(_("Payments received"), "send", [card("pay_in", _("Payments received"), "good", "pay", [],
			_("Submitted fee payments with a payment date in the selected range."), sum="paid_amount")]),
		tile(_("Refunds & concessions"), "handshake", [
			card("ref_ok", _("Refunds"), "info", "ref", [["status", "=", "Approved"]], _("Approved fee refunds in the selected dates."), sum="refund_amount"),
			card("con_ok", _("Concessions"), "info", "con", [["status", "=", "Approved"]], _("Approved fee concessions in the selected dates."), sum="waiver_value")]),
		tile(_("Student fee status"), "users", [
			stu("fee_paid", _("Fees paid"), "good", [["fee_payment_status", "=", "Paid"]], _("Student Master: Fee Payment Status = Paid.")),
			stu("fee_due", _("Not fully paid"), "action", [["fee_payment_status", "!=", "Paid"]], _("Student Master: Fee Payment Status is anything other than Paid."),
				unused_if="fee_paid")]),
	])

	# ── Venue Booking ──
	section("venue", _("Venue booking"), [
		tile(_("Requests"), "calendar", [
			card("ven_pending", _("Pending allotment"), "action", "ven", [["status", "=", "Pending Allotment"]], _("Venue requests waiting for allotment (any date)."), dates=False),
			card("ven_allotted", _("Allotted"), "good", "ven", [["status", "=", "Allotted"]], _("Allotted bookings starting in the selected dates."))]),
		tile(_("Rejected / cancelled"), "xcircle", [card("ven_rejected", _("Rejected / cancelled"), "bad", "ven",
			[["status", "in", ["Rejected", "Cancelled"]]], _("Bookings rejected or cancelled, starting in the selected dates."))]),
		tile(_("Swap requests"), "handshake", [card("ven_swap", _("Swap requests pending"), "action", "ven",
			[["swap_status", "=", "Pending"]], _("Bookings with a venue swap request waiting for a decision."), dates=False)]),
	])

	# ── PACE ──
	section("pace", _("PACE"), [
		tile(_("Enquiries"), "mic", [
			card("penq_new", _("New"), "action", "penq", [["status", "=", "New"]], _("PACE enquiries not yet contacted (any date)."), dates=False),
			card("penq_contacted", _("Contacted"), "good", "penq", [["status", "=", "Contacted"]], _("PACE enquiries contacted, submitted in the selected dates."))]),
		tile(_("Applications"), "file", [
			_card("pace_progress", _("In progress"), "info", kind="pace", pct=False,
				filters=lambda c: [_in("status", [x for x in _pace_statuses("progress") if x != "Draft"])],
				guide=_("PACE applications submitted and still moving (not Draft, closed or enrolled).")),
			_card("pace_enrolled", _("Enrolled"), "good", kind="pace", pct=False, filters=lambda c: [_in("status", _pace_statuses("enrolled"))],
				guide=_("PACE applications at an enrolment stage."))]),
		tile(_("Drafts & withdrawals"), "pen", [
			card("pace_draft", _("Draft"), "action", "pace", [["status", "=", "Draft"]], _("PACE applications started but not submitted.")),
			_card("pace_closed", _("Withdrawn / rejected"), "bad", kind="pace", pct=False, filters=lambda c: [_in("status", _pace_statuses("closed"))],
				guide=_("PACE applications Withdrawn or Rejected."))]),
		tile(_("Document checks"), "filesign", [
			card("pdv_verified", _("Verified"), "good", "pdv", [["status", "=", "Verified"]], _("PACE document verifications completed."), dates=False),
			card("pdv_returned", _("Returned for correction"), "bad", "pdv", [["status", "=", "Returned for Correction"]],
				_("PACE document verifications sent back to the applicant."), dates=False)]),
		tile(_("Documents pending"), "clock", [card("pdv_pending", _("Pending"), "action", "pdv", [["status", "=", "Pending"]],
			_("PACE document verifications waiting for a verifier."), dates=False)]),
	])
	section("pace", _("PACE · fees"), [
		tile(_("Application fee"), "coins", [
			card("pfa_app_paid", _("Paid"), "good", "pfa", [["fee_type", "=", "Application Fee"], ["status", "in", ["Paid", "Enrolled"]]],
				_("PACE application-fee assignments Paid, assigned in the selected dates."), sum="final_payable_amount"),
			card("pfa_app_due", _("Pending"), "action", "pfa", [["fee_type", "=", "Application Fee"], ["status", "in", ["Assigned", "Partially Paid"]]],
				_("PACE application-fee assignments not yet paid (Assigned or Partially Paid)."), sum="final_payable_amount")]),
		tile(_("Course fee"), "coins", [
			card("pfa_course_paid", _("Paid"), "good", "pfa", [["fee_type", "=", "Course Fee"], ["status", "in", ["Paid", "Enrolled"]]],
				_("PACE course-fee assignments Paid (or Enrolled), assigned in the selected dates."), sum="final_payable_amount"),
			card("pfa_course_due", _("Pending"), "action", "pfa", [["fee_type", "=", "Course Fee"], ["status", "in", ["Assigned", "Partially Paid"]]],
				_("PACE course-fee assignments not yet paid (Assigned or Partially Paid)."), sum="final_payable_amount")]),
		tile(_("Online payments"), "send", [
			card("spr_paid", _("Paid"), "good", "spr", [["status", "=", "Paid"]], _("Razorpay payment requests for PACE fees with status Paid."), sum="amount"),
			card("spr_failed", _("Failed"), "bad", "spr", [["status", "=", "Failed"]], _("Razorpay payment requests for PACE fees that failed."), sum="amount")]),
		tile(_("Payment links not paid"), "alert", [card("spr_requested", _("Sent, not yet paid"), "action", "spr", [["status", "=", "Requested"]],
			_("Payment requests sent to PACE applicants and not paid yet."), sum="amount")]),
		tile(_("Settlement"), "handshake", [
			card("spr_settled", _("Net settled"), "good", "spr", [["status", "=", "Paid"], ["settlement_status", "in", SETTLED]],
				_("Paid PACE payments the gateway has settled to the bank; the figure is the net amount settled."), sum="net_settled"),
			card("spr_fees", _("Gateway charges"), "neutral", "spr", [["status", "=", "Paid"], ["settlement_status", "in", SETTLED]],
				_("Gateway fees deducted on those settled PACE payments."), sum="gateway_fees")]),
		tile(_("Receipts issued"), "file", [card("prc_all", _("Receipts"), "info", "prc", [],
			_("PACE receipts generated, payment date in the selected range."), sum="amount")]),
	])

	# ── FLE ──
	section("fle", _("FLE · Foundations for a Legal Education"), [
		tile(_("Registrations"), "users", [card("fle_all", _("Registrations"), "info", "fle", [], _("FLE registrations in the selected dates."))]),
		tile(_("Enrolment"), "check", [
			card("fle_enrolled", _("Enrolled"), "good", "fle", [["enrollment_status", "in", ["Enrolled", "Completed", "Certificate Issued"]]],
				_("FLE candidates Enrolled, Completed or Certificate Issued.")),
			card("fle_inprogress", _("In progress"), "info", "fle", [["enrollment_status", "=", "In Progress"]],
				_("FLE registrations still In Progress (not yet enrolled)."))]),
		tile(_("Payment"), "coins", [
			card("fle_paid", _("Paid"), "good", "fle", [["payment_status", "in", FLE_PAID]], _("FLE registrations whose payment is Authorized or Captured.")),
			card("fle_unpaid", _("Not paid"), "action", "fle", [["payment_status", "not in", FLE_PAID]],
				_("FLE registrations whose payment is initiated, failed, cancelled or missing."))]),
		tile(_("LMS access"), "alert", [card("fle_no_lms", _("Paid, no LMS account"), "action", "fle",
			[["payment_status", "in", FLE_PAID], ["lms_account_created", "=", 0]], _("Paid FLE candidates who do not have an LMS account yet."))]),
		tile(_("Certificates"), "award", [card("fle_cert", _("Certificate issued"), "good", "fle", [["enrollment_status", "=", "Certificate Issued"]],
			_("FLE candidates whose certificate has been issued."))]),
	])
	section("fle", _("FLE · fees"), [
		tile(_("Amount collected"), "coins", [
			card("flp_paid", _("Collected"), "good", "flp", [["payment_status", "in", FLE_PAID]],
				_("FLE payments (FLE Payment Log) Authorized or Captured, in the selected dates."), sum="paid_amount"),
			card("flp_failed", _("Failed / refunded"), "bad", "flp", [["payment_status", "not in", FLE_PAID]],
				_("FLE payment log entries that failed, were refunded or are still pending."), sum="paid_amount")]),
		tile(_("Settlement"), "handshake", [
			card("flp_settled", _("Net settled"), "good", "flp", [["payment_status", "in", FLE_PAID], ["settlement_status", "in", SETTLED]],
				_("Paid FLE payments settled to the bank; the figure is the net amount settled."), sum="net_settled"),
			card("flp_unsettled", _("Not settled yet"), "action", "flp", [["payment_status", "in", FLE_PAID], ["settlement_status", "not in", SETTLED]],
				_("Paid FLE payments the gateway has not settled yet."), sum="paid_amount")]),
	])

	# ── Examinations ──
	section("exams", _("Examinations"), [
		tile(_("Exam plans"), "calendar", [
			card("exam_active", _("Active"), "good", "exam", [["status", "=", "Active"]], _("Exam plans with status Active."), dates=False),
			card("exam_tt", _("Timetable published"), "info", "exam", [["timetable_published", "=", 1]], _("Exam plans whose timetable is published."), dates=False)]),
		tile(_("Course marks"), "pen", [
			card("marks_done", _("Submitted / locked"), "good", "marks", [["status", "in", ["Submitted", "Locked"]]], _("Course marks Submitted or Locked."), dates=False),
			card("marks_draft", _("Still in draft"), "action", "marks", [["status", "=", "Draft"]], _("Course marks still in Draft."), dates=False)]),
		tile(_("Results"), "award", [
			card("res_pub", _("Published"), "good", "res", [["is_published", "=", 1]], _("Student results published."), dates=False),
			card("res_unpub", _("Not published"), "action", "res", [["is_published", "=", 0]], _("Student results computed but not published."), dates=False)]),
		tile(_("Grade appeals"), "alert", [
			card("appeal_open", _("Open"), "action", "appeal", [["status", "in", ["Submitted", "Under Review"]]], _("Grade appeals Submitted or Under Review (any date)."), dates=False),
			card("appeal_done", _("Resolved"), "good", "appeal", [["status", "in", ["Resolved", "Rejected"]]], _("Grade appeals resolved or rejected, submitted in the selected dates."))]),
	])

	# ── Transcripts ──
	section("transcripts", _("Transcripts"), [
		tile(_("Requests to process"), "file", [
			card("treq_open", _("In process"), "action", "treq", [["status", "in", TRANSCRIPT_OPEN]],
				_("Transcript requests Payment Pending, Submitted, Under Review or Approved — not yet generated (any date)."), dates=False),
			card("treq_review", _("Under review"), "info", "treq", [["status", "=", "Under Review"]], _("Transcript requests Under Review (any date)."), dates=False)]),
		tile(_("Completed requests"), "check", [
			card("treq_done", _("Generated / delivered"), "good", "treq", [["status", "in", ["Generated", "Delivered"]]],
				_("Transcript requests Generated or Delivered, requested in the selected dates.")),
			card("treq_rejected", _("Rejected / cancelled"), "bad", "treq", [["status", "in", ["Rejected", "Cancelled"]]],
				_("Transcript requests Rejected or Cancelled, requested in the selected dates."))]),
		tile(_("Transcript fee"), "coins", [
			card("treq_paid", _("Paid"), "good", "treq", [["payment_status", "=", "Paid"]], _("Transcript requests whose fee is Paid, requested in the selected dates."), sum="fee_amount"),
			card("treq_unpaid", _("Payment pending"), "action", "treq", [["payment_status", "in", ["Pending", "Payment Initiated", "Payment Failed"]]],
				_("Transcript requests whose fee is Pending, Initiated or Failed (any date)."), dates=False, sum="fee_amount")]),
		tile(_("Urgent requests"), "alert", [card("treq_urgent", _("Urgent, still open"), "action", "treq",
			[["urgency", "=", "Urgent"], ["status", "in", TRANSCRIPT_OPEN]], _("Open transcript requests marked Urgent (any date)."), dates=False)]),
		tile(_("Transcripts issued"), "award", [
			card("trans_gen", _("Generated"), "good", "trans", [["status", "=", "Generated"]], _("Student transcripts generated in the selected dates.")),
			card("trans_rev", _("Revoked"), "bad", "trans", [["status", "=", "Revoked"]], _("Student transcripts revoked."), dates=False)]),
	])

	# ── Promotion ──
	section("promotion", _("Promotion"), [
		tile(_("Promotion decisions"), "award", [
			card("prom_yes", _("Promoted"), "good", "sprom", [["promotion_status", "in", PROMOTED]],
				_("Student promotions Promoted (including overrides), processed in the selected dates.")),
			card("prom_no", _("Not promoted"), "bad", "sprom", [["promotion_status", "in", NOT_PROMOTED]],
				_("Student promotions Not Promoted (including overrides), processed in the selected dates."))]),
		tile(_("Conditional"), "alert", [card("prom_cond", _("Conditional — review"), "action", "sprom", [["promotion_status", "=", "Conditional"]],
			_("Student promotions marked Conditional — waiting for a review decision (any date)."), dates=False)]),
		tile(_("Publishing"), "send", [
			card("prom_draft", _("Draft"), "action", "sprom", [["stage", "=", "Draft"]], _("Promotion decisions still in Draft — not published to students (any date)."), dates=False),
			card("prom_pub", _("Published"), "good", "sprom", [["stage", "=", "Published"]], _("Promotion decisions published, processed in the selected dates."))]),
		tile(_("Next-year enrolment"), "check", [
			card("prom_enr", _("Enrolled"), "good", "sprom", [["enrollment_status", "=", "Enrolled"]], _("Promoted students already enrolled into the next year.")),
			card("prom_enr_fail", _("Pending / failed"), "action", "sprom", [["promotion_status", "in", PROMOTED], ["enrollment_status", "in", ["Pending", "Failed"]]],
				_("Promoted students whose next-year enrolment is Pending or Failed (any date)."), dates=False)]),
		tile(_("Promotion runs"), "calendar", [
			card("prun_done", _("Completed"), "good", "prun", [["status", "=", "Completed"]], _("Promotion runs completed in the selected dates.")),
			card("prun_err", _("With errors"), "bad", "prun", [["status", "in", ["Completed with Errors", "Error"]]], _("Promotion runs that ended with errors (any date)."), dates=False)]),
		tile(_("Policies"), "filesign", [
			card("ppol_active", _("Active"), "good", "ppol", [["status", "=", "Active"]], _("Promotion policies with status Active."), dates=False),
			card("ppol_draft", _("Draft"), "info", "ppol", [["status", "=", "Draft"]], _("Promotion policies still in Draft."), dates=False)]),
	])


_build_registry()

MODULES = [
	("admission", _("Admission")), ("registration", _("Student registration")), ("programme", _("Programme management")),
	("attendance", _("Attendance")), ("idcard", _("ID card")), ("fees", _("Fees")), ("venue", _("Venue booking")),
	("pace", _("PACE")), ("fle", _("FLE")), ("exams", _("Examinations")), ("transcripts", _("Transcripts")),
	("promotion", _("Promotion")),
]


# ── Query helpers ────────────────────────────────────────────────────────────
def _count(doctype, filters, or_filters=None):
	rows = frappe.get_list(doctype, filters=filters, or_filters=or_filters, fields=[{"COUNT": "*", "as": "n"}], order_by=None)
	return cint(rows[0].n) if rows else 0


def _group(doctype, filters, field, or_filters=None, sum_field=None):
	fields = [field, {"COUNT": "*", "as": "n"}] + ([{"SUM": sum_field, "as": "s"}] if sum_field else [])
	rows = frappe.get_list(doctype, filters=filters, or_filters=or_filters, fields=fields, group_by=field, order_by=None)
	by = {(r.get(field) or ""): cint(r.n) for r in rows}
	amount = sum(flt(r.get("s")) for r in rows) if sum_field else None
	return by, amount


def _card_filters(card, ctx):
	filters = src_filters(card["kind"], ctx, with_dates=card["dates"])
	if card["statuses"] is not None:
		filters.append(["status", "in", card["statuses"]])
	if card["filters"]:
		filters += card["filters"](ctx)
	or_filters = card["or_filters"](ctx) if card["or_filters"] else None
	return SOURCES[card["kind"]]["doctype"], filters, or_filters


def _group_field(kind):
	p = SOURCES[kind]["prog"]
	return p if p and not p.startswith("@") else None


def _cache_key(name, payload):
	h = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
	return f"uod:{name}:{frappe.session.user}:{h}"


def _cached(name, payload, fn, refresh=False):
	key = _cache_key(name, payload)
	if not refresh:
		hit = frappe.cache.get_value(key)
		if hit is not None:
			return hit
	val = fn()
	frappe.cache.set_value(key, val, expires_in_sec=CACHE_SECONDS)
	return val


def _can_read(doctype):
	return frappe.has_permission(doctype, "read")


# ── Main payload ─────────────────────────────────────────────────────────────
@frappe.whitelist()
def get_dashboard_data(filters=None, refresh=0):
	ctx = _ctx(filters)
	return _cached("dash", ctx, lambda: _dashboard(ctx), refresh=cint(refresh))


def _dashboard(ctx):
	status_prog = []
	if _can_read(APP):
		rows = frappe.get_list(APP, filters=f_app(ctx), fields=["status", "program", {"COUNT": "*", "as": "n"}],
			group_by="status, program", order_by=None)
		status_prog = [{"status": r.status or "", "program": r.program or "", "n": cint(r.n)} for r in rows]

	cards, totals, denied = {}, {}, set()
	for key, card in CARDS.items():
		kind = card["kind"]
		if not _can_read(SOURCES[kind]["doctype"]):
			denied.add(kind)
			cards[key] = None
			continue
		if kind == "app" and not card["filters"] and not card["or_filters"]:
			wanted = set(card["statuses"]) if card["statuses"] is not None else None
			by = defaultdict(int)
			for r in status_prog:
				if wanted is None or r["status"] in wanted:
					by[r["program"]] += r["n"]
			cards[key] = {"total": sum(by.values()), "by": dict(by)}
			continue
		doctype, filters, or_filters = _card_filters(card, ctx)
		field = _group_field(kind)
		if field:
			by, amount = _group(doctype, filters, field, or_filters, card["sum"])
		else:
			by = {"": _count(doctype, filters, or_filters)}
			amount = None
			if card["sum"]:
				rows = frappe.get_list(doctype, filters=filters, or_filters=or_filters, fields=[{"SUM": card["sum"], "as": "s"}], order_by=None)
				amount = flt(rows[0].s) if rows else 0
		cards[key] = {"total": sum(by.values()), "by": by, "amount": amount}

	for key, card in CARDS.items():
		ref = cards.get(card["unused_if"]) if card["unused_if"] else None
		if cards.get(key) and ref is not None and ref["total"] == 0:
			cards[key]["unused"] = True

	# Base for "% of …" on each module's cards: everything in scope for that source.
	for kind in {c["kind"] for c in CARDS.values() if c["pct"]} - denied:
		totals[kind] = _count(SOURCES[kind]["doctype"], src_filters(kind, ctx))

	return {
		"cards": cards,
		"totals": totals,
		"status_prog": status_prog,
		"app_total": sum(r["n"] for r in status_prog),
		"stu_total": totals.get("stu", 0),
		"stu_by": _group(STU, f_stu(ctx), "programme_of_study")[0] if "stu" not in denied else {},
		"alltime": _count(APP, []) if _can_read(APP) else 0,
		"programme_names": _programme_names(),
		"updated": now_datetime().strftime("%H:%M"),
	}


def _programme_names():
	return {p.name: (p.program_name or p.name) for p in frappe.get_all("Programme", fields=["name", "program_name"])}


@frappe.whitelist()
def get_meta():
	"""Board layout, guide text, funnel steps and filter options."""
	def strip(c):
		return {k: c[k] for k in ("key", "label", "tone", "kind", "sub", "guide", "pct", "sum")}

	return {
		"headline": [strip(c) for c in HEADLINE],
		"board": [{"key": s["key"], "title": s["title"], "tiles": [{"title": t["title"], "icon": t["icon"],
			"cards": [strip(c) for c in t["cards"]]} for t in s["tiles"]]} for s in BOARD],
		"modules": [{"key": k, "label": l} for k, l in MODULES],
		"sources": {k: {"label": s["label"], "honours": honours(k)} for k, s in SOURCES.items()},
		"steps": [{"key": k, "label": l, "statuses": s} for k, l, s in STEPS],
		"stages": [{"name": n, "statuses": s} for n, s in STAGES],
		"options": _filter_options(),
	}


def _filter_options():
	app_meta = frappe.get_meta(APP)

	def sel(meta, field):
		df = meta.get_field(field)
		return [o for o in (df.options or "").split("\n") if o] if df else []

	genders = sorted(set(sel(app_meta, "gender")) | set(frappe.get_all("Genders", pluck="name")))
	categories = sel(app_meta, "whether_scstobc_ncl")
	for q in sel(frappe.get_meta(STU), "quota"):
		if q not in categories:
			categories.append(q)
	def rows(doctype, **kw):
		# A user who cannot read the master just gets no choices for that filter.
		return frappe.get_list(doctype, limit_page_length=0, **kw) if _can_read(doctype) else []

	return {
		"programmes": [{"value": p.name, "label": p.program_name or p.name}
			for p in rows("Programme", fields=["name", "program_name"], order_by="program_name asc")],
		"academic_years": [{"value": y, "label": y} for y in rows("Academic Year", pluck="name", order_by="name desc")],
		"admission_cycles": [{"value": c.name, "label": c.cycle_name or c.name}
			for c in rows("Admission Cycle", fields=["name", "cycle_name"], order_by="creation desc")],
		"genders": [{"value": g, "label": g} for g in genders],
		"categories": [{"value": c, "label": c} for c in categories],
		"stages": [{"value": n, "label": n} for n, _s in STAGES],
	}


# ── Funnel tab ───────────────────────────────────────────────────────────────
DAY_BUCKETS = [(0, 7, "0–7"), (8, 15, "8–15"), (16, 30, "16–30"), (31, 60, "31–60"), (61, 90, "61–90"), (91, None, "90+")]


@frappe.whitelist()
def get_funnel_data(filters=None, refresh=0):
	ctx = _ctx(filters)
	return _cached("funnel", ctx, lambda: _funnel(ctx), refresh=cint(refresh))


def _days_in(r, today):
	end = getdate(r.modified) if r.status in ENDED else today
	return max(date_diff(end, getdate(r.creation)), 0)


def _funnel(ctx):
	today = getdate(nowdate())
	apps = frappe.get_list(APP, filters=f_app(ctx), fields=["name", "status", "program", "creation", "modified"],
		order_by=None, limit_page_length=0)

	open_days, ended_days, over30 = [], [], 0
	buckets = {b[2]: {"label": b[2], "open": 0, "ended": 0} for b in DAY_BUCKETS}
	by_stage = defaultdict(list)
	weeks = defaultdict(int)
	created = {}
	for r in apps:
		d = _days_in(r, today)
		created[r.name] = getdate(r.creation)
		ended = r.status in ENDED
		(ended_days if ended else open_days).append(d)
		if not ended and d > 30:
			over30 += 1
		for lo, hi, label in DAY_BUCKETS:
			if d >= lo and (hi is None or d <= hi):
				buckets[label]["ended" if ended else "open"] += 1
				break
		by_stage[STAGE_OF.get(r.status, "Applying")].append(d)
		c = getdate(r.creation)
		weeks[str(add_days(c, -c.weekday()))] += 1

	all_days = open_days + ended_days
	pipeline = {
		"avg_days": round(sum(all_days) / len(all_days), 1) if all_days else 0,
		"avg_open": round(sum(open_days) / len(open_days), 1) if open_days else 0,
		"open": len(open_days), "over30": over30, "ended": len(ended_days),
		"buckets": list(buckets.values()),
		"by_stage": [{"stage": n, "avg": round(sum(by_stage[n]) / len(by_stage[n]), 1) if by_stage[n] else 0,
			"n": len(by_stage[n])} for n, _s in STAGES],
	}

	# Offers for applicants in scope (filtered by the same programme / year /
	# cycle, then intersected with the in-scope applicants in Python).
	of = []
	if ctx.programmes:
		of.append(["program", "in", ctx.programmes])
	if ctx.academic_years:
		of.append(["academic_year", "in", ctx.academic_years])
	if ctx.admission_cycles:
		of.append(["admission_cycle", "in", ctx.admission_cycles])
	offers = [o for o in frappe.get_list(OFFER, filters=of + [["status", "!=", "Draft"]],
		fields=["name", "applicant", "program", "status", "issued_on"], order_by=None, limit_page_length=0)
		if o.applicant in created] if _can_read(OFFER) else []
	offer_status = defaultdict(lambda: defaultdict(int))
	days_to_offer = defaultdict(list)
	for o in offers:
		offer_status[o.program or ""][o.status or ""] += 1
		if o.issued_on:
			days_to_offer[o.program or ""].append(max(date_diff(getdate(o.issued_on), created[o.applicant]), 0))

	app_f = f_app(ctx)
	offered = app_f + [["status", "in", reached(6)]]
	return {
		"pipeline": pipeline,
		"weeks": [{"week": w, "n": n} for w, n in sorted(weeks.items())],
		"offers": {
			"total": len(offers),
			"by_programme": {p: dict(s) for p, s in offer_status.items()},
			"median_days": {p: median(v) for p, v in days_to_offer.items() if v},
			"gender": _group_by2(APP, offered, "program", "gender"),
		},
		"category": _group(APP, app_f, "whether_scstobc_ncl")[0],
		"gender": _group(APP, app_f, "gender")[0],
		"source": _group(APP, app_f, "source_of_information")[0],
		"state": _group(APP, app_f, "state")[0],
	}


def _group_by2(doctype, filters, a, b):
	rows = frappe.get_list(doctype, filters=filters, fields=[a, b, {"COUNT": "*", "as": "n"}], group_by=f"{a}, {b}", order_by=None)
	out = defaultdict(dict)
	for r in rows:
		out[r.get(a) or ""][r.get(b) or ""] = cint(r.n)
	return out


# ── Tables (drilldowns, timeline list, funnel tables) ───────────────────────
COMPUTED = {"app": {"stage", "days"}}


def _table_filters(kind, ctx, x):
	"""Base filters for a table + the extras the client may send (whitelisted)."""
	or_filters = None
	card = CARDS.get(x.get("card")) if x.get("card") else None
	if card:
		if card["kind"] != kind:
			frappe.throw(_("Card and table do not match."))
		_dt, filters, or_filters = _card_filters(card, ctx)
	else:
		filters = src_filters(kind, ctx)
	if kind == "app" and not card:
		if STEP_STATUSES.get(x.get("step")):
			filters.append(["status", "in", STEP_STATUSES[x["step"]]])
		if x.get("stage"):
			filters.append(_in("status", dict(STAGES).get(x["stage"]) or []))
		if x.get("status") and x["status"] in RANK:
			filters.append(["status", "=", x["status"]])
		if x.get("pipeline") == "open":
			filters.append(["status", "not in", sorted(ENDED)])
		elif x.get("pipeline") == "ended":
			filters.append(["status", "in", sorted(ENDED)])
		if x.get("days"):
			lo, _sep, hi = str(x["days"]).partition("-")
			if lo:
				filters.append(["creation", "<=", f"{add_days(nowdate(), -cint(lo))} 23:59:59"])
			if hi:
				filters.append(["creation", ">=", f"{add_days(nowdate(), -cint(hi))} 00:00:00"])
		if x.get("week"):
			w = getdate(x["week"])
			filters += [["creation", ">=", f"{w} 00:00:00"], ["creation", "<=", f"{add_days(w, 6)} 23:59:59"]]
		if x.get("field") in ("whether_scstobc_ncl", "gender", "source_of_information", "state"):
			v = x.get("value")
			filters.append([x["field"], "=", v] if v else [x["field"], "is", "not set"])
	elif kind == "stu" and not card and x.get("reg_status") in REG_STATES:
		filters.append(["registration_status", "=", x["reg_status"]])
	elif kind == "isa" and not card:
		if x.get("from"):
			filters.append(["interview_date", ">=", x["from"]])
		if x.get("to"):
			filters.append(["interview_date", "<=", x["to"]])

	prog_field = _group_field(kind)
	if prog_field and x.get("programme") is not None and x.get("programme") != "__all__":
		p = x.get("programme")
		filters = filters + ([[prog_field, "=", p]] if p else [[prog_field, "is", "not set"]])
	return filters, or_filters, prog_field


def _search_or(spec, q):
	q = (q or "").strip()
	if not q:
		return None
	return [[f, "like", f"%{q}%"] for f in spec["search"]]


def _merge_or(spec, filters, or_filters, search_or):
	"""A card's OR group and a search OR group can't both be or_filters: resolve
	the card's group to names first so the search keeps its own OR group."""
	if or_filters and search_or:
		names = frappe.get_list(spec["doctype"], filters=filters, or_filters=or_filters, pluck="name", limit_page_length=0)
		return filters + [_in("name", names)], search_or
	return filters, or_filters or search_or


def _fetch(kind, filters, or_filters, order_by, start, length):
	spec = SOURCES[kind]
	computed = COMPUTED.get(kind, set())
	fields = ["name"] + [c[0] for c in spec["columns"] if c[0] not in computed and c[0] != "name"]
	if kind == "app":
		fields.append("modified")
	rows = frappe.get_list(spec["doctype"], filters=filters, or_filters=or_filters, fields=fields,
		order_by=order_by, limit_start=start, limit_page_length=length)
	if kind == "app":
		today = getdate(nowdate())
		for r in rows:
			r["stage"] = STAGE_OF.get(r.status, "Applying")
			r["days"] = _days_in(r, today)
			r.pop("modified", None)
	return rows


def _resolve(kind, filters, extra, search, sort, order):
	if kind not in SOURCES:
		frappe.throw(_("Unknown table."))
	spec = SOURCES[kind]
	if not _can_read(spec["doctype"]):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	ctx = _ctx(filters)
	x = frappe.parse_json(extra) if extra else {}
	x = x or {}
	f, or_f, prog_field = _table_filters(kind, ctx, x)
	f, or_f = _merge_or(spec, f, or_f, _search_or(spec, search))
	computed = COMPUTED.get(kind, set())
	sortable = {c[0] for c in spec["columns"] if c[0] not in computed}
	sort = sort if sort in sortable else spec["sort"]
	order = "asc" if order == "asc" else "desc"
	return spec, ctx, x, f, or_f, prog_field, sortable, sort, order


@frappe.whitelist()
def get_table(kind, filters=None, extra=None, search=None, sort=None, order="desc", page=1, page_size=50):
	spec, ctx, x, f, or_f, prog_field, sortable, sort, order = _resolve(kind, filters, extra, search, sort, order)
	page_size = max(1, min(cint(page_size) or 50, MAX_PAGE))
	page = max(1, cint(page) or 1)
	out = {
		"columns": [{"field": c[0], "label": c[1], "type": c[2], "sortable": c[0] in sortable} for c in spec["columns"]],
		"rows": _fetch(kind, f, or_f, f"{sort} {order}", (page - 1) * page_size, page_size),
		"total": _count(spec["doctype"], f, or_f), "page": page, "page_size": page_size, "sort": sort, "order": order,
		"doctype": spec["doctype"],
	}
	if x.get("with_units") and prog_field:
		f_all, or_all, _p = _table_filters(kind, ctx, dict(x, programme="__all__"))
		out["units"] = _group(spec["doctype"], f_all, prog_field, or_all)[0]
	return out


@frappe.whitelist()
def export_table(kind, filters=None, extra=None, search=None, sort=None, order="desc", name="uniquad"):
	"""Every matching row as CSV (no cap; fetched in chunks)."""
	spec, _ctx_, _x, f, or_f, _p, _s, sort, order = _resolve(kind, filters, extra, search, sort, order)
	buf = io.StringIO()
	w = csv.writer(buf)
	w.writerow([str(c[1]) for c in spec["columns"]])
	start = 0
	while True:
		chunk = _fetch(kind, f, or_f, f"{sort} {order}", start, EXPORT_CHUNK)
		for r in chunk:
			w.writerow(["" if r.get(c[0]) is None else r.get(c[0]) for c in spec["columns"]])
		if len(chunk) < EXPORT_CHUNK:
			break
		start += EXPORT_CHUNK
	safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(name))[:60] or "uniquad"
	frappe.response["type"] = "download"
	frappe.response["filename"] = f"{safe}-{nowdate()}.csv"
	frappe.response["filecontent"] = buf.getvalue()
	frappe.response["content_type"] = "text/csv"


# ── Timeline (one person, start to end) ─────────────────────────────────────
JOURNEY = [("Applied", 0), ("Submitted", 1), ("Entrance test", 2), ("Interview", 3), ("Merit", 4),
	("Seat", 5), ("Offer", 6), ("Fee paid", 7), ("Enrolled", 8)]
REJECTED_AT = {s: RANK.get(s) for s in NOT_ADMITTED if RANK.get(s) is not None}


def _in_scope(doctype, name):
	"""IDOR guard: the record must be visible through get_list, not just get_doc."""
	if not frappe.get_list(doctype, filters={"name": name}, pluck="name", limit_page_length=1):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _visible(doctype, filters, fields):
	return frappe.get_list(doctype, filters=filters, fields=fields, limit_page_length=0) if _can_read(doctype) else []


@frappe.whitelist()
def get_timeline(kind, name):
	if kind not in ("app", "stu"):
		frappe.throw(_("Unknown record type."))
	app_name, stu_name = (name, None) if kind == "app" else (None, name)
	if kind == "stu":
		_in_scope(STU, name)
		app_name = frappe.db.get_value(STU, name, "application_number")
		if app_name and not (_can_read(APP) and frappe.get_list(APP, filters={"name": app_name}, pluck="name", limit_page_length=1)):
			app_name = None
	else:
		_in_scope(APP, name)
		stu_name = (frappe.get_list(STU, filters={"application_number": name}, pluck="name", limit_page_length=1) or [None])[0] \
			if _can_read(STU) else None

	events = []
	head = {}

	def ev(when, kind_, title, meta="", tone="info", doctype=None, docname=None, flow=None):
		if when:
			events.append({"when": str(get_datetime(when)), "kind": kind_, "title": title, "meta": meta or "",
				"tone": tone, "doctype": doctype, "name": docname, "flow": flow})

	if app_name:
		a = frappe.get_doc(APP, app_name)
		head.update(applicant=a.name, name=a.candidate_name, programme=a.program, status=a.status,
			stage=STAGE_OF.get(a.status, "Applying"), cycle=a.admission_cycle, email=a.email, mobile=a.mobile_number,
			applied_on=str(getdate(a.creation)), days=_days_in(a, getdate(nowdate())))
		ev(a.creation, "application", _("Application started"), a.program, "info", APP, a.name)
		if a.status != "Draft":
			ev(a.modified, "status", _("Current status"), "", _tone_of(a.status), APP, a.name, flow=[a.status])

		for p in _visible("Applicant Payment Receipt", {"applicant": a.name}, ["name", "fee_type", "payment_date", "payment_mode", "creation"]):
			ev(p.payment_date or p.creation, "payment", _("{0} paid").format(p.fee_type or _("Fee")), p.payment_mode, "good", "Applicant Payment Receipt", p.name)
		for t in _visible("Entrance Test Seat Allocation", {"applicant": a.name},
				["name", "allocation_status", "allocation_date", "center_name", "start_time", "creation"]):
			ev(t.allocation_date or t.creation, "test", _("Entrance test centre {0}").format(t.allocation_status or ""),
				" · ".join(filter(None, [t.center_name, str(t.start_time or "")])), "info", "Entrance Test Seat Allocation", t.name)
		for i in _visible(ISA, {"applicant": a.name},
				["name", "interview_date", "interview_time", "interview_slot_status", "staff_name", "interview_attendance_confirmation", "creation"]):
			when = f"{i.interview_date} {i.interview_time or '00:00:00'}" if i.interview_date else i.creation
			ev(when, "interview", _("Interview {0}").format((i.interview_slot_status or "").lower()),
				" · ".join(filter(None, [i.staff_name, i.interview_attendance_confirmation])),
				"bad" if i.interview_slot_status == "Cancelled" else "info", ISA, i.name)
		# One applicant appears in several category tables of the same list.
		for m in frappe.db.sql("""select distinct ml.name, ml.published_on, ml.generated_on, ml.creation, mla.status, mla.total_score
				from `tabMerit List Applicant` mla join `tabMerit List` ml on ml.name = mla.parent
				where mla.applicant_id = %s and mla.parenttype = 'Merit List'""", a.name, as_dict=True):
			ev(m.published_on or m.generated_on or m.creation, "merit", _("Merit list: {0}").format(m.status or "—"),
				_("Total score {0}").format(m.total_score) if m.total_score is not None else "",
				_tone_of(m.status), "Merit List", m.name)
		for s in frappe.db.sql("""select distinct sa.name, sa.published_on, sa.creation, ssa.selection_status
				from `tabSeat Selection Applicant` ssa join `tabSeat Allocation` sa on sa.name = ssa.parent
				where ssa.applicant_id = %s""", a.name, as_dict=True):
			ev(s.published_on or s.creation, "seat", _("Seat allocation: {0}").format(s.selection_status or "—"), "",
				_tone_of(s.selection_status), "Seat Allocation", s.name)
		for o in _visible(OFFER, {"applicant": a.name},
				["name", "status", "issued_on", "accepted_on", "confirmation_fee_paid_on", "full_fee_paid_on", "offer_acceptance_deadline"]):
			ev(o.issued_on, "offer", _("Offer issued"), _("Reply by {0}").format(o.offer_acceptance_deadline) if o.offer_acceptance_deadline else "", "info", OFFER, o.name)
			ev(o.accepted_on, "offer", _("Offer accepted"), "", "good", OFFER, o.name)
			ev(o.confirmation_fee_paid_on, "payment", _("Confirmation fee paid"), "", "good", OFFER, o.name)
			ev(o.full_fee_paid_on, "payment", _("Full fee paid"), "", "good", OFFER, o.name)
			if o.status in ("Rejected", "Expired", "Withdrawn"):
				ev(o.issued_on, "offer", _("Offer {0}").format(o.status.lower()), "", "bad", OFFER, o.name)
		for g in _visible(AUDIT, {"applicant": a.name},
				["name", "action", "field_changed", "old_value", "new_value", "remarks", "performed_by", "performed_on", "timestamp", "creation"]):
			flow = [g.old_value or "—", g.new_value or "—"] if (g.old_value or g.new_value) else None
			ev(g.performed_on or g.timestamp or g.creation, "log", g.action or g.field_changed or _("Change"),
				" · ".join(filter(None, [g.remarks, g.performed_by])), "neutral", AUDIT, g.name, flow=flow)

	if stu_name:
		s = frappe.get_doc(STU, stu_name)
		head.setdefault("name", s.first_name)
		head.setdefault("programme", s.programme_of_study)
		head.update(student=s.name, registration_status=s.registration_status, student_status=s.student_status, batch=s.batch)
		ev(s.creation, "student", _("Student record created"), s.batch, "good", STU, s.name)
		if s.date_of_registration:
			ev(s.date_of_registration, "student", _("Registered"), "", "good", STU, s.name)
		if s.registration_status:
			ev(s.modified, "status", _("Registration status"), "", "good" if s.registration_status == "Completed" else "info", STU, s.name,
				flow=[s.registration_status])
		for e in _visible("Student Enrollment", {"student": s.name}, ["name", "program", "batch", "section", "status", "enrollment_date", "creation"]):
			ev(e.enrollment_date or e.creation, "student", _("Enrolment {0}").format((e.status or "").lower()),
				" · ".join(filter(None, [e.program, e.batch, e.section])), _tone_of(e.status), "Student Enrollment", e.name)
		for c in _visible("ID Card Generation", {"student": s.name}, ["name", "card_status", "issue_date", "creation"]):
			ev(c.issue_date or c.creation, "idcard", _("ID card {0}").format((c.card_status or "").lower()), "",
				"bad" if c.card_status == "Error" else "info", "ID Card Generation", c.name)
		for p in _visible("Fee Payment", {"student": s.name, "docstatus": 1}, ["name", "fee_component", "paid_amount", "payment_date", "payment_mode"]):
			ev(p.payment_date, "fees", _("Fee paid: {0}").format(p.fee_component or ""),
				" · ".join(filter(None, [frappe.format_value(p.paid_amount, {"fieldtype": "Currency"}), p.payment_mode])), "good", "Fee Payment", p.name)
		for d in _visible("Fee Demand", {"student": s.name, "status": ["in", OPEN_DEMAND], "due_date": ["is", "set"]},
				["name", "fee_component", "outstanding_amount", "due_date"]):
			ev(d.due_date, "fees", _("Fee due: {0}").format(d.fee_component or ""),
				_("Outstanding {0}").format(frappe.format_value(d.outstanding_amount, {"fieldtype": "Currency"})), "action", "Fee Demand", d.name)
		for c in _visible("Student Attendance Condonation", {"student": s.name, "docstatus": ["<", 2]},
				["name", "course", "final_status", "submitted_date", "number_of_sessions"]):
			ev(c.submitted_date, "attendance", _("Condonation request: {0}").format(c.final_status or ""),
				" · ".join(filter(None, [c.course, _("{0} sessions").format(c.number_of_sessions) if c.number_of_sessions else ""])),
				_tone_of(c.final_status), "Student Attendance Condonation", c.name)
		for r in _visible("Student Result Publish", {"student": s.name, "is_published": 1}, ["name", "exam_plan", "term_gpa", "cumulative_gpa", "published_on"]):
			ev(r.published_on, "exams", _("Result published: {0}").format(r.exam_plan or ""),
				_("Term GPA {0} · CGPA {1}").format(r.term_gpa or "—", r.cumulative_gpa or "—"), "good", "Student Result Publish", r.name)
		for g in _visible("Grade Appeal", {"student": s.name}, ["name", "course", "appeal_type", "status", "submitted_on"]):
			ev(g.submitted_on, "exams", _("Grade appeal ({0}): {1}").format(g.appeal_type or "", g.status or ""), g.course,
				_tone_of(g.status), "Grade Appeal", g.name)
		for t in _visible("Transcript Request", {"student": s.name}, ["name", "transcript_type", "status", "requested_on", "num_copies"]):
			ev(t.requested_on, "transcript", _("Transcript requested: {0}").format(t.transcript_type or ""),
				_("{0} · {1} copies").format(t.status or "", t.num_copies or 1), _tone_of(t.status), "Transcript Request", t.name)
		for t in _visible("Student Transcript", {"student": s.name}, ["name", "transcript_type", "status", "generation_date"]):
			ev(t.generation_date, "transcript", _("Transcript {0}: {1}").format((t.status or "").lower(), t.transcript_type or ""), "",
				"bad" if t.status == "Revoked" else "good", "Student Transcript", t.name)
		for pr in _visible("Student Promotion", {"student": s.name},
				["name", "promotion_status", "current_year", "target_year", "current_cgpa", "stage", "processed_on", "published_on", "creation"]):
			ev(pr.published_on or pr.processed_on or pr.creation, "promotion",
				_("Promotion: {0}").format(pr.promotion_status or "—"),
				" · ".join(filter(None, [_("Year {0} → {1}").format(pr.current_year or "?", pr.target_year or "?"),
					_("CGPA {0}").format(pr.current_cgpa) if pr.current_cgpa else "", pr.stage])),
				"good" if pr.promotion_status in PROMOTED else "bad" if pr.promotion_status in NOT_PROMOTED else "action", "Student Promotion", pr.name)
		if s.laptop_issue_date:
			ev(s.laptop_issue_date, "onboarding", _("Laptop issued"), "", "good", STU, s.name)
		if s.allocation_date and s.hostel:
			ev(s.allocation_date, "onboarding", _("Room allocated"), " · ".join(filter(None, [s.hostel, s.hostel_room])), "good", STU, s.name)
		if s.bank_details_submitted_on:
			ev(s.bank_details_submitted_on, "onboarding", _("Bank details submitted"), "", "good", STU, s.name)

	rank = RANK.get(head.get("status")) if head.get("status") else None
	bad_at = REJECTED_AT.get(head.get("status"))
	journey = []
	for label, r in JOURNEY:
		done = rank is not None and rank >= r and not (bad_at is not None and r > bad_at)
		# A student record without a visible application was admitted.
		journey.append({"label": _(label), "done": bool(done) or bool(stu_name and not app_name),
			"bad": bad_at is not None and r == bad_at})
	journey.append({"label": _("Registration"), "done": head.get("registration_status") == "Completed", "bad": False})

	events.sort(key=lambda e: e["when"])
	return {"head": head, "journey": journey, "events": events}


def _tone_of(status):
	s = (status or "").lower()
	if any(w in s for w in ("reject", "declin", "expire", "withdraw", "cancel", "drop")):
		return "bad"
	if "wait" in s or "pending" in s:
		return "action"
	if any(w in s for w in ("select", "accept", "paid", "enrol", "complet", "approv", "resolv", "generat", "deliver", "promot")):
		return "good"
	return "info"
