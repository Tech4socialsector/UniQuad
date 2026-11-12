# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Demo data for the Uniquad Overall Dashboard — every card gets a number.

	bench --site slcm.local execute slcm.uniquad_demo_data.create
	bench --site slcm.local execute slcm.uniquad_demo_data.delete

Dev / demo sites only. Records are written with db_insert (no controllers, no
emails, no ERPNext postings). Every record is tagged so ``delete`` removes
exactly what ``create`` added: transaction records are named ``DEMO-…`` and
masters ``… (Demo)`` / ``DEMO-…``. Dates are spread across the current year,
with some on today and the next few days so the "today / next 7 days" cards
fill too — re-run ``create`` (it deletes first) on the morning of a demo.
"""

import random

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

TAG = "DEMO-"
SUFFIX = " (Demo)"
SEED = 2026

FIRST = ["Aarav", "Ananya", "Vihaan", "Diya", "Kabir", "Isha", "Arjun", "Meera", "Rohan", "Sara", "Aditya", "Kavya", "Nikhil",
	"Priya", "Rahul", "Sneha", "Varun", "Tara", "Siddharth", "Nisha", "Karan", "Riya", "Dev", "Pooja", "Yash", "Zoya", "Manav",
	"Ira", "Neel", "Anika"]
LAST = ["Sharma", "Iyer", "Reddy", "Nair", "Menon", "Gupta", "Rao", "Das", "Pillai", "Kumar", "Shetty", "Joshi", "Bose", "Khan",
	"Mehta", "Patel", "Singh", "Verma", "Kulkarni", "Chatterjee"]
STATES = ["Karnataka", "Kerala", "Tamil Nadu", "Maharashtra", "Delhi", "Telangana", "West Bengal", "Uttar Pradesh", "Rajasthan", "Gujarat"]

# Every DocType create() writes to (delete() clears them in this order).
DOCTYPES = [
	"Admission Audit Log", "Offer Letter", "Interview Seat Allocation", "Applicant Payment Receipt", "Applicant",
	"Student Promotion", "Promotion Run", "Promotion Policy", "Student Transcript", "Transcript Request", "Grade Appeal",
	"Student Result Publish", "Student Course Marks", "FLE Payment Log", "Foundations for a Legal Education",
	"SLCM Payment Request", "PACE Receipt", "PACE Applicant Fee Assignment", "PACE Document Verification",
	"PACE Enquiry", "PACE Application", "Venue Booking", "Fee Concession", "Fee Refund", "Fee Payment", "Fee Demand",
	"ID Card Generation", "Time Table", "Student Attendance Condonation", "Attendance Summary", "Student Attendance",
	"Attendance Session", "Student Enrollment", "Student Master", "Faculty", "SLCM Batch", "Course", "Programme",
	"PACE Programme", "Admission Cycle", "Hostel", "Condonation Reason",
]


def _rng():
	return random.Random(SEED)


def _ins(doctype, name, **fields):
	"""Insert without controllers. Unknown fields are dropped so the script
	survives DocType changes."""
	meta = frappe.get_meta(doctype)
	data = {k: v for k, v in fields.items() if meta.has_field(k) or k in ("docstatus", "creation", "modified")}
	doc = frappe.get_doc({"doctype": doctype, "name": name, **data})
	doc.flags.name_set = True
	doc.db_insert()
	if fields.get("creation"):
		frappe.db.set_value(doctype, name, {"creation": fields["creation"], "modified": fields.get("modified") or fields["creation"]},
			update_modified=False)
	return doc


def _day(rng, start="2026-01-02", end=None):
	"""A random date this year up to today."""
	end = getdate(end or nowdate())
	start = getdate(start)
	return add_days(start, rng.randint(0, max((end - start).days, 0)))


def _ts(d, rng):
	return f"{d} {rng.randint(9, 17):02d}:{rng.choice(['00', '15', '30', '45'])}:00"


def _person(rng):
	return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def _first(doctype, default=None, **filters):
	return frappe.db.get_value(doctype, filters, "name") or default


# ── create ───────────────────────────────────────────────────────────────────
def create():
	if not frappe.conf.get("developer_mode") and not frappe.flags.in_test:
		frappe.throw("Demo data is only for development / demo sites (developer_mode is off).")
	delete(quiet=True)
	rng = _rng()
	ctx = _masters(rng)
	apps = _admission(rng, ctx)
	students = _students(rng, ctx, apps)
	_programme_mgmt(rng, ctx, students)
	_attendance(rng, ctx, students)
	_id_cards(rng, ctx, students)
	_fees(rng, ctx, students)
	_venue(rng, ctx)
	_pace(rng, ctx)
	_fle(rng)
	_exams(rng, ctx, students)
	_transcripts(rng, ctx, students)
	_promotion(rng, ctx, students)
	frappe.db.commit()
	frappe.clear_cache()
	print("Demo data created. Remove it with: bench --site <site> execute slcm.uniquad_demo_data.delete")


def _masters(rng):
	ay = _first("Academic Year", "AY 2026 -2027", name=["like", "%2026%2027%"]) or "AY 2026 -2027"
	term = _first("Academic Term", None, academic_year=ay) or _first("Academic Term")
	progs = ["BALLB"] if frappe.db.exists("Programme", "BALLB") else []
	for code, title, level in [("LLM", "LLM — Master of Laws", "Postgraduate"), ("MPP", "Master of Public Policy", "Postgraduate")]:
		_ins("Programme", f"{TAG}{code}", program_name=title, program_code=code, level_of_study=level, program_duration=2, program_status="Active")
		progs.append(f"{TAG}{code}")
	_ins("Programme", f"{TAG}PHD", program_name="PhD in Law", program_code="PHD", level_of_study="Research Course", program_status="Inactive")

	_ins("Admission Cycle", f"{TAG}AC-2026", cycle_name="Regular Admission 2026", cycle_code="RA26", status="Active",
		academic_year=ay, application_start_date="2026-01-05", application_end_date=add_days(nowdate(), 30))

	pace_progs = []
	for p in ["Master of Business Laws", "PG Diploma in Cyber Law & Cyber Forensics", "PG Diploma in Medical Law & Ethics",
			"PG Diploma in Arbitration Law"]:
		name = p + SUFFIX
		_ins("PACE Programme", name, programme_name=p, program_name=p)
		pace_progs.append(name)
	_ins("Hostel", "Hostel A" + SUFFIX, hostel_name="Hostel A")
	_ins("Condonation Reason", "Medical" + SUFFIX, reason="Medical")

	for i, (code, status) in enumerate([("C101", "Inactive"), ("C102", "Active"), ("C103", "Active")]):
		_ins("Course", f"{TAG}{code}", course_code=code, course_name=["Legal History", "Constitutional Law I", "Law of Contracts"][i],
			course_type="Core", credit_value=4, status=status)
	_ins("SLCM Batch", f"{TAG}2027", batch_name="2027", batch_code="B27", academic_year=ay, status="Planned")
	# Faculty is autoincrement-named: the demo tag goes on faculty_id instead.
	for i, status in enumerate(["Active", "Active", "Inactive"]):
		doc = frappe.get_doc({"doctype": "Faculty", "faculty_id": f"{TAG}F{900 + i}", "first_name": rng.choice(FIRST),
			"last_name": rng.choice(LAST), "status": status, "email": f"demo.faculty{i}@example.org", "auto_create_user": 0})
		doc.db_insert()

	courses = frappe.get_all("Course", filters={"status": "Active"}, pluck="name") or ["Criminal Law-CL001"]
	return frappe._dict(ay=ay, term=term, progs=progs, pace_progs=pace_progs, courses=courses,
		classes=frappe.get_all("Classes", pluck="name") or [None], batch=_first("SLCM Batch", "2026", name="2026"),
		sections=frappe.get_all("Section", pluck="name") or ["A"], faculty=_first("Faculty"), cycle=f"{TAG}AC-2026",
		exam_plans=frappe.get_all("Exam Plan", pluck="name"), venue=_first("Venue Master"), policy=_first("Promotion Policy"))


# Applicant statuses, each several times, so every admission card fills.
APPLICANT_MIX = [
	("Draft", 6), ("Submitted", 5), ("Submitted and Paid", 4), ("Entrance Test Scheduled", 4), ("Entrance Test Completed", 4),
	("Entrance Test Rejected", 3), ("Interview Scheduled", 5), ("Interview Completed", 4), ("Interview Exempted", 2),
	("Interview Rejected", 3), ("Merit Selected", 4), ("Merit Waitlisted", 3), ("Merit Rejected", 3), ("Seat Selected", 3),
	("Seat Waitlisted", 2), ("Offer Issued", 4), ("Offer Accepted", 3), ("Offer Declined", 2), ("Offer Expired", 2),
	("Confirmation Fee Paid", 3), ("Full Fee Paid", 3), ("Enrolled", 8), ("Withdrawn", 2), ("Rejected", 2),
]


def _admission(rng, ctx):
	apps = []
	i = 0
	for status, n in APPLICANT_MIX:
		for _ in range(n):
			i += 1
			created = _day(rng, end=add_days(nowdate(), -3))
			name = f"{TAG}APP-{i:03d}"
			who = _person(rng)
			_ins("Applicant", name, candidate_name=who, status=status, program=rng.choice(ctx.progs), admission_cycle=ctx.cycle,
				academic_year=ctx.ay, gender=rng.choice(["Male", "Female", "Female", "Other"]),
				whether_scstobc_ncl=rng.choice(["General", "General", "OBC-NCL", "SC", "ST", "EWS"]),
				source_of_information=rng.choice(["NLSIU Website", "Instagram", "Youtube", "Newspaper Advertisement", "NLSIU Students, Faculty or Alumni"]),
				state=rng.choice(STATES), email=f"demo.applicant{i}@example.org", mobile_number=f"98{rng.randint(10000000, 99999999)}",
				application_fee_status="Pending" if status in ("Draft", "Submitted") else rng.choice(["Paid", "Paid", "Waived", "Requested"]),
				creation=_ts(created, rng), modified=_ts(add_days(created, rng.randint(1, 40)) if status != "Draft" else created, rng))
			apps.append(frappe._dict(name=name, who=who, status=status, created=created))
			if status not in ("Draft", "Submitted"):
				_ins("Applicant Payment Receipt", f"{TAG}APR-{i:03d}", applicant=name, fee_type="Application Fee", payment_mode="Online",
					payment_date=add_days(created, 1), academic_year=ctx.ay)
			if status.startswith("Interview") or status in ("Merit Selected", "Merit Waitlisted"):
				# Scheduled interviews land today and over the next week, so both time cards fill.
				when = add_days(nowdate(), [0, 0, 1, 3, 6][i % 5]) if status == "Interview Scheduled" else add_days(created, 20)
				_ins(ISA_DT, f"{TAG}ISA-{i:03d}", applicant=name, candidate_name=who, program=None, admission_cycle=ctx.cycle,
					academic_year=ctx.ay, interview_date=when, interview_time=f"{rng.randint(9, 16):02d}:30:00",
					interview_slot_status="Confirmed", staff_name=f"Prof. {rng.choice(LAST)}",
					interview_attendance_confirmation="Confirm Attendance")
			if RANK_OFFER.get(status):
				_ins("Offer Letter", f"{TAG}OL-{i:03d}", applicant=name, admission_cycle=ctx.cycle, academic_year=ctx.ay,
					status=RANK_OFFER[status], issued_on=_ts(add_days(created, 25), rng),
					accepted_on=_ts(add_days(created, 28), rng) if RANK_OFFER[status] not in ("Issued", "Rejected", "Expired") else None,
					confirmation_fee_paid_on=add_days(created, 30) if status in ("Confirmation Fee Paid", "Full Fee Paid", "Enrolled") else None,
					full_fee_paid_on=add_days(created, 35) if status in ("Full Fee Paid", "Enrolled") else None,
					offer_acceptance_deadline=add_days(created, 40))
	# Programme on interview slots follows the applicant.
	frappe.db.sql(f"""update `tab{ISA_DT}` isa join `tabApplicant` a on a.name = isa.applicant
		set isa.program = a.program where isa.name like 'DEMO-%%'""")
	for j, a in enumerate([x for x in apps if x.status not in ("Draft",)][:12]):
		_ins("Admission Audit Log", f"{TAG}LOG-{j:03d}", applicant=a.name, action="Status changed", field_changed="status",
			old_value="Submitted", new_value=a.status, performed_by="Administrator", remarks="Updated by admissions office",
			performed_on=_ts(add_days(a.created, 10), rng), reference_doctype="Applicant", reference_name=a.name)
	return apps


ISA_DT = "Interview Seat Allocation"
RANK_OFFER = {"Offer Issued": "Issued", "Offer Accepted": "Accepted", "Offer Declined": "Rejected", "Offer Expired": "Expired",
	"Confirmation Fee Paid": "Confirmation Fee Paid", "Full Fee Paid": "Full Fee Paid", "Enrolled": "Full Fee Paid"}
REG_MIX = [("Selected", 3), ("Pending REGO", 3), ("Pending FINO", 2), ("Pending Registration", 2), ("Pending Print & Scan", 2),
	("Pending Residences", 2), ("Pending IT", 2), ("Final Verification REGO", 2), ("Completed", 14), ("Re-Open", 1)]


def _students(rng, ctx, apps):
	enrolled = [a for a in apps if a.status == "Enrolled"]
	students = []
	i = 0
	for reg, n in REG_MIX:
		for _ in range(n):
			i += 1
			name = f"{TAG}STU-{i:03d}"
			app = enrolled.pop() if enrolled and reg == "Completed" else None
			done = reg == "Completed"
			left = i % 11 == 0
			_ins("Student Master", name, first_name=app.who if app else _person(rng), application_number=app.name if app else None,
				programme_of_study=rng.choice(ctx.progs), academic_year=ctx.ay, batch=ctx.batch, section=rng.choice(ctx.sections),
				gender=rng.choice(["Male", "Female"]), quota=rng.choice(["General", "General", "OBC", "SC", "EWS"]),
				registration_status=reg, student_status="Inactive" if left else "Active", academic_status="Active",
				email=f"demo.student{i}@example.org", phone=f"97{rng.randint(10000000, 99999999)}",
				date_of_registration=_day(rng) if done else None,
				id_card_issued="Yes" if done and rng.random() < .7 else "No",
				laptop_issued="Yes" if done and rng.random() < .6 else "No", laptop_issue_date=_day(rng) if done else None,
				bank_details_submitted=1 if done and rng.random() < .5 else 0,
				needs_accommodation="Yes" if rng.random() < .7 else "No",
				hostel=("Hostel A" + SUFFIX) if done and rng.random() < .6 else None, hostel_room=None,
				allocation_date=_day(rng) if done else None,
				fee_payment_status="Paid" if done and rng.random() < .6 else rng.choice(["Unpaid", "Partially Paid"]),
				aadhaar_verified=1 if done else rng.choice([0, 1]), offer_letter_verified=1 if done else 0,
				student_declaration_verified=1 if done else 0, creation=_ts(_day(rng, end=add_days(nowdate(), -2)), rng))
			students.append(name)
	return students


def _programme_mgmt(rng, ctx, students):
	for k, s in enumerate(students):
		_ins("Student Enrollment", f"{TAG}ENR-{k:03d}", student=s, program=frappe.db.get_value("Student Master", s, "programme_of_study"),
			batch=ctx.batch, section=rng.choice(ctx.sections), status="Pending" if k % 7 == 0 else "Enrolled",
			enrollment_date=_day(rng), faculty_advisor=ctx.faculty)


def _attendance(rng, ctx, students):
	for k in range(30):
		d = _day(rng, end=add_days(nowdate(), -1))
		status = "Cancelled" if k % 13 == 0 else "Postponed" if k % 17 == 0 else "Conducted"
		marked = 0 if k % 6 == 0 and status == "Conducted" else 1 if status == "Conducted" else 0
		if marked == 0 and status == "Conducted":
			status = "Scheduled"
		present = rng.randint(30, 45) if marked else 0
		_ins("Attendance Session", f"{TAG}SES-{k:03d}", based_on="Class", class_name=rng.choice(ctx.classes), course=rng.choice(ctx.courses),
			section=rng.choice(ctx.sections), session_date=d, session_type="Lecture", session_status=status, instructor=ctx.faculty,
			attendance_marked=marked, total_students=48 if marked else 0, present_count=present, absent_count=48 - present if marked else 0,
			attendance_percentage=round(present * 100 / 48, 1) if marked else 0)
	for k in range(60):
		s = rng.choice(students)
		_ins("Student Attendance", f"{TAG}ATT-{k:03d}", student=s, student_name=frappe.db.get_value("Student Master", s, "first_name"),
			program=frappe.db.get_value("Student Master", s, "programme_of_study"), course=rng.choice(ctx.courses), academic_year=ctx.ay,
			attendance_date=_day(rng), status=rng.choice(["Present"] * 6 + ["Absent", "Absent", "Late", "OD"]), source=rng.choice(["RFID", "Manual"]))
	for k, s in enumerate(students[:24]):
		pct = rng.choice([92, 88, 81, 79, 76, 68, 61])
		_ins("Attendance Summary", f"{TAG}SUM-{k:03d}", student=s, student_name=frappe.db.get_value("Student Master", s, "first_name"),
			programme=frappe.db.get_value("Student Master", s, "programme_of_study"), academic_year=ctx.ay, academic_term=ctx.term,
			course=rng.choice(ctx.courses), section=rng.choice(ctx.sections), total_classes=40, attended_classes=round(pct * .4),
			attendance_percentage=pct, minimum_required_percentage=75, eligible_for_exam=1 if pct >= 75 else 0)
	for k, st in enumerate(["Pending", "Pending", "May Be Approved", "Approved", "Approved", "Rejected"]):
		s = rng.choice(students)
		_ins("Student Attendance Condonation", f"{TAG}CON-{k:03d}", student=s, student_name=frappe.db.get_value("Student Master", s, "first_name"),
			programme=frappe.db.get_value("Student Master", s, "programme_of_study"), academic_year=ctx.ay, course=rng.choice(ctx.courses),
			condonation_reason="Medical" + SUFFIX, number_of_sessions=rng.randint(2, 6), submitted_date=_day(rng), final_status=st,
			docstatus=1 if st in ("Approved", "Rejected") else 0)
	for k in range(14):
		d = add_days(nowdate(), k // 2)
		_ins("Time Table", f"{TAG}TT-{k:03d}", based_on="Class", class_name=rng.choice(ctx.classes), academic_year=ctx.ay,
			programme=rng.choice(ctx.progs), course=rng.choice(ctx.courses), section=rng.choice(ctx.sections), schedule_date=d,
			instructor=ctx.faculty, instructor_name="Demo Faculty", venue=ctx.venue, session_status="Scheduled")


def _id_cards(rng, ctx, students):
	for k, s in enumerate(students[:20]):
		st = ["Generated", "Printed", "Printed", "Draft", "Error", "Cancelled", "Expired"][k % 7]
		_ins("ID Card Generation", f"{TAG}IDC-{k:03d}", card_type="Student", student=s,
			student_name=frappe.db.get_value("Student Master", s, "first_name"), programme=frappe.db.get_value("Student Master", s, "programme_of_study"),
			batch=ctx.batch, academic_year=ctx.ay, card_status=st, issue_date=_day(rng) if st in ("Generated", "Printed") else None,
			expiry_date="2031-06-30", print_count=1 if st == "Printed" else 0)


def _fees(rng, ctx, students):
	comps = ["Program Fee", "Examination Fee", "Registration Fee", "Annual Fee"]
	for k, s in enumerate(students):
		net = rng.choice([25000, 50000, 125000, 175000])
		kind = k % 4
		paid = net if kind == 0 else net // 2 if kind == 1 else 0
		due = add_days(nowdate(), -rng.randint(5, 60)) if kind == 2 else add_days(nowdate(), rng.randint(5, 60))
		_ins("Fee Demand", f"{TAG}FD-{k:03d}", student=s, student_name=frappe.db.get_value("Student Master", s, "first_name"),
			program=frappe.db.get_value("Student Master", s, "programme_of_study"), academic_year=ctx.ay, fee_component=rng.choice(comps),
			original_amount=net, net_payable=net, paid_amount=paid, outstanding_amount=net - paid, demand_date=_day(rng), due_date=due,
			status="Paid" if paid == net else "Partially Paid" if paid else "Overdue" if kind == 2 else "Pending")
		if paid:
			_ins("Fee Payment", f"{TAG}FP-{k:03d}", student=s, student_name=frappe.db.get_value("Student Master", s, "first_name"),
				program=frappe.db.get_value("Student Master", s, "programme_of_study"), academic_year=ctx.ay, fee_component=rng.choice(comps),
				fee_demand=f"{TAG}FD-{k:03d}", paid_amount=paid, amount=paid, payment_mode=rng.choice(["Online Payment", "Bank Transfer"]),
				payment_date=_day(rng), reference_number=f"TXN{rng.randint(100000, 999999)}", status="Submitted", docstatus=1)
	for k in range(4):
		s = rng.choice(students)
		_ins("Fee Refund", f"{TAG}RF-{k:03d}", student=s, student_name=frappe.db.get_value("Student Master", s, "first_name"),
			refund_type=rng.choice(["Overpayment", "Withdrawal"]), refund_amount=rng.choice([5000, 12500, 25000]), refund_mode="NEFT",
			refund_date=_day(rng), status="Approved", docstatus=1)
		_ins("Fee Concession", f"{TAG}FC-{k:03d}", student=s, registration_id=s, academic_year=ctx.ay,
			concession_type="University Financial Aid", waiver_value=rng.choice([20000, 40000, 60000]), concession_date=_day(rng),
			status="Approved", docstatus=1)


def _venue(rng, ctx):
	mix = ["Pending Allotment"] * 4 + ["Allotted"] * 8 + ["Rejected", "Cancelled"]
	for k, st in enumerate(mix):
		start = getdate(_day(rng, end=add_days(nowdate(), 20))) if st != "Pending Allotment" else add_days(nowdate(), rng.randint(1, 15))
		_ins("Venue Booking", f"{TAG}VB-{k:03d}", event_name=rng.choice(["Moot court practice", "Guest lecture", "Seminar", "Club meeting", "Workshop"]),
			venue=ctx.venue, building="Main Academic Block", start_datetime=_ts(start, rng), end_datetime=f"{start} 18:00:00",
			status=st, requester_type=rng.choice(["Student", "Faculty", "Staff"]), requester_name=_person(rng),
			swap_status="Pending" if k in (5, 6) else None, swap_requested=1 if k in (5, 6) else 0)


PACE_MIX = [("Draft", 10), ("Submitted", 8), ("Under Verification", 4), ("Verified", 8), ("Returned for Correction", 3),
	("Fee Paid", 4), ("Enrolled", 14), ("Withdrawn", 2), ("Rejected", 1)]


def _pace(rng, ctx):
	k = 0
	apps = []
	for st, n in PACE_MIX:
		for _ in range(n):
			k += 1
			name = f"{TAG}PACE-{k:03d}"
			who = _person(rng)
			sub = _day(rng, end=add_days(nowdate(), -2))
			_ins("PACE Application", name, applicant_name=who, first_name=who.split()[0], last_name=who.split()[1],
				email_address=f"demo.pace{k}@example.org", programme=rng.choice(ctx.pace_progs), academic_year=ctx.ay, status=st,
				submission_date=sub if st != "Draft" else None, gender=rng.choice(["Male", "Female"]), creation=_ts(sub, rng))
			apps.append(frappe._dict(name=name, who=who, status=st, sub=sub))
			if st not in ("Draft",):
				dv = {"Submitted": "Pending", "Under Verification": "Pending", "Returned for Correction": "Returned for Correction"}.get(st, "Verified")
				_ins("PACE Document Verification", f"{TAG}PDV-{k:03d}", application=name, applicant_name=who, academic_year=ctx.ay,
					status=dv, due_date=add_days(sub, 7))
	for k, st in enumerate(["New"] * 5 + ["Contacted"] * 6 + ["Closed"] * 2):
		_ins("PACE Enquiry", f"{TAG}PENQ-{k:03d}", full_name=_person(rng), email=f"demo.enquiry{k}@example.org", phone=f"96{rng.randint(10000000, 99999999)}",
			programme_of_interest=rng.choice(ctx.pace_progs), submitted_on=_ts(_day(rng), rng), status=st)

	# Fees: application fee for everyone who submitted, course fee for verified / enrolled.
	f = 0
	for a in apps:
		if a.status == "Draft":
			continue
		for fee_type, amount in [("Application Fee", 2000), ("Course Fee", 55000)]:
			if fee_type == "Course Fee" and a.status not in ("Verified", "Fee Paid", "Enrolled"):
				continue
			f += 1
			paid = a.status in ("Fee Paid", "Enrolled") or (fee_type == "Application Fee" and rng.random() < .8)
			assign = f"{TAG}PFA-{f:03d}"
			when = add_days(a.sub, 2 if fee_type == "Application Fee" else 12)
			_ins("PACE Applicant Fee Assignment", assign, applicant=a.name, applicant_name=a.who, fee_type=fee_type, academic_year=ctx.ay,
				nationality_type="Indian", total_amount=amount, final_payable_amount=amount, assignment_date=when,
				status=("Enrolled" if a.status == "Enrolled" and fee_type == "Course Fee" else "Paid") if paid else "Assigned",
				payment_date=add_days(when, 1) if paid else None)
			pr = f"{TAG}SPR-{f:03d}"
			status = "Paid" if paid else rng.choice(["Requested", "Requested", "Failed"])
			settled = paid and rng.random() < .85
			_ins("SLCM Payment Request", pr, reference_doctype="PACE Applicant Fee Assignment", reference_name=assign, email_to=f"demo.pace@example.org",
				amount=amount, status=status, gateway_status={"Paid": "captured", "Failed": "failed"}.get(status, "created"),
				payment_method=rng.choice(["upi", "card", "netbanking"]) if paid else None, paid_on=add_days(when, 1) if paid else None,
				settlement_status="processed" if settled else None, gateway_fees=round(amount * .0043, 2) if settled else 0,
				net_settled=round(amount * .9957, 2) if settled else 0, docstatus=1, creation=_ts(when, rng))
			if paid:
				_ins("PACE Receipt", f"{TAG}PRC-{f:03d}", pace_application=a.name, applicant_name=a.who, fee_type=fee_type, fee_assignment=assign,
					payment_request=pr, academic_year=ctx.ay, amount=amount, payment_date=_ts(add_days(when, 1), rng),
					transaction_id=f"pay_{rng.randint(10**9, 10**10)}")


def _fle(rng):
	mix = [("Authorized", "Enrolled", 1)] * 18 + [("Authorized", "Enrolled", 0)] * 2 + [("Authorized", "Certificate Issued", 1)] * 3 \
		+ [("Payment Initiated", "In Progress", 0)] * 4 + [("Cancelled", "In Progress", 0)] * 3 + [("Payment Failed", "In Progress", 0)] * 2
	for k, (ps, es, lms) in enumerate(mix):
		ts = _ts(_day(rng), rng)
		who = _person(rng)
		reg = f"{TAG}FLE-{k:03d}"
		_ins("Foundations for a Legal Education", reg, candidate_name=who, candidate_email_id=f"demo.fle{k}@example.org",
			email_address=f"demo.fle{k}@example.org", last_class_attended=rng.choice(["12th", "UG", "10th"]), timestamp=ts,
			enrollment_status=es, payment_status=ps, lms_account_created=lms, paid_amount=12500 if ps == "Authorized" else 0)
		if ps == "Authorized":
			settled = k % 9 != 0
			_ins("FLE Payment Log", f"{TAG}FLP-{k:03d}", reference_no=reg, full_name=who, email=f"demo.fle{k}@example.org",
				payment_status="Authorized", paid_amount=12500, transaction_date=ts, transaction_id=f"pay_{rng.randint(10**9, 10**10)}",
				settlement_status="processed" if settled else None, net_settled=12450 if settled else 0, gateway_fees=50 if settled else 0)
	_ins("FLE Payment Log", f"{TAG}FLP-FAIL", full_name=_person(rng), email="demo.fle.failed@example.org", payment_status="Failed",
		paid_amount=12500, transaction_date=_ts(_day(rng), rng))


def _exams(rng, ctx, students):
	plan = ctx.exam_plans[0] if ctx.exam_plans else None
	for k, s in enumerate(students[:20]):
		total = rng.randint(45, 92)
		_ins("Student Course Marks", f"{TAG}SCM-{k:03d}", exam_plan=plan, course=rng.choice(ctx.courses), academic_term=ctx.term, student=s,
			student_id=s, total_marks=total, grade="A" if total > 80 else "B" if total > 65 else "C", status="Draft" if k % 5 == 0 else "Submitted")
	for k, s in enumerate(students[:14]):
		pub = k % 4 != 0
		_ins("Student Result Publish", f"{TAG}SRP-{k:03d}", exam_plan=plan, student=s, term_gpa=round(rng.uniform(5.5, 9.5), 2),
			cumulative_gpa=round(rng.uniform(5.5, 9.5), 2), is_published=1 if pub else 0, published_on=_ts(_day(rng), rng) if pub else None)
	for k, st in enumerate(["Submitted", "Submitted", "Under Review", "Resolved", "Resolved", "Rejected"]):
		_ins("Grade Appeal", f"{TAG}GA-{k:03d}", student=rng.choice(students), exam_plan=plan, course=rng.choice(ctx.courses),
			academic_term=ctx.term, appeal_type=rng.choice(["Re-evaluation", "Marks Correction"]), status=st, submitted_on=_ts(_day(rng), rng),
			current_grade="C", revised_grade="B" if st == "Resolved" else None)


def _transcripts(rng, ctx, students):
	mix = ["Payment Pending", "Submitted", "Submitted", "Under Review", "Under Review", "Approved", "Generated", "Generated",
		"Delivered", "Delivered", "Rejected", "Cancelled"]
	for k, st in enumerate(mix):
		s = rng.choice(students)
		pay = "Pending" if st == "Payment Pending" else "Paid"
		_ins("Transcript Request", f"{TAG}TR-{k:03d}", student=s, student_name=frappe.db.get_value("Student Master", s, "first_name"),
			programme=frappe.db.get_value("Student Master", s, "programme_of_study"), transcript_type=rng.choice(["Interim Transcript", "Final Transcript",
				"Consolidated Marksheet"]), num_copies=rng.choice([1, 2]), status=st, delivery_mode="Soft Copy (PDF)",
			urgency="Urgent" if k in (1, 3) else "Normal", requested_on=_day(rng), payment_required=1, fee_amount=500, payment_status=pay)
		if st in ("Generated", "Delivered"):
			_ins("Student Transcript", f"{TAG}ST-{k:03d}", student=s, student_name=frappe.db.get_value("Student Master", s, "first_name"),
				transcript_type="Interim", status="Generated", generation_date=_day(rng), transcript_request=f"{TAG}TR-{k:03d}")
	_ins("Student Transcript", f"{TAG}ST-REV", student=students[0], transcript_type="Interim", status="Revoked", generation_date=_day(rng))


def _promotion(rng, ctx, students):
	_ins("Promotion Policy", f"{TAG}PP-DRAFT", title="Year 2 → 3 (draft)", program=ctx.progs[0], academic_year=ctx.ay, status="Draft",
		from_year=2, to_year=3, min_cgpa=5.0, min_attendance_percent=75)
	mix = ["Promoted"] * 12 + ["Override - Promoted", "Not Promoted", "Not Promoted", "Conditional", "Conditional", "Override - Not Promoted"]
	for k, (s, ps) in enumerate(zip(students, mix)):
		published = k % 3 != 0
		promoted = ps in ("Promoted", "Override - Promoted")
		_ins("Student Promotion", f"{TAG}SP-{k:03d}", promotion_policy=ctx.policy, student=s,
			student_name=frappe.db.get_value("Student Master", s, "first_name"), current_year="1", target_year="2", promotion_status=ps,
			current_cgpa=round(rng.uniform(4.5, 9.2), 2), backlog_count=0 if promoted else rng.randint(1, 3),
			attendance_percent=rng.choice([71, 78, 84, 90]), stage="Published" if published else "Draft",
			enrollment_status=("Enrolled" if k % 4 else "Pending") if promoted else "Not Applicable",
			processed_on=_ts(_day(rng), rng), published_on=_ts(_day(rng), rng) if published else None)
	for k, st in enumerate(["Completed", "Completed", "Completed with Errors"]):
		_ins("Promotion Run", f"{TAG}PR-{k:03d}", program=ctx.progs[0], source_academic_year=ctx.ay, batch=ctx.batch, status=st,
			total_students=48, promoted_count=44 if st == "Completed" else 39, skipped_count=4 if st == "Completed" else 9,
			run_on=_ts(_day(rng), rng), run_by="Administrator")


# ── delete ───────────────────────────────────────────────────────────────────
def delete(quiet=False):
	"""Remove every demo record (names DEMO-… or … (Demo)); nothing else is touched."""
	total = 0
	for dt in DOCTYPES:
		if not frappe.db.table_exists(dt):
			continue
		where = "faculty_id like %s and %s = %s" if dt == "Faculty" else "name like %s or name like %s"
		args = (TAG + "%", 1, 1) if dt == "Faculty" else (TAG + "%", "%" + SUFFIX)
		n = frappe.db.sql(f"select count(*) from `tab{dt}` where {where}", args)[0][0]
		if n:
			frappe.db.sql(f"delete from `tab{dt}` where {where}", args)
			total += n
	frappe.db.commit()
	frappe.clear_cache()
	if not quiet:
		print(f"Deleted {total} demo records.")
