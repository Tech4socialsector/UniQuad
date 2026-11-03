# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Re-exam and improvement students of an Exam Plan in one list (Exam Planner step 5).

* Re-exam: students whose result in the plan is a fail (or absent), and anyone
  registered for the plan's re-exam.
* Improvement: students registered for the plan's improvement exam (they passed).

One registration window per course serves both: it is written to the course's
Re Exam Course Setting and Improvement Exam Course Setting. Fees are not set
there: they come with the enrolment (Fee column of the upload, or the Enrol
dialog) and raise a Fee Demand.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from slcm.slcm.utils.result_access import PAID_STATUSES, grade_marker, grade_markers, is_improved

TYPES = {"Re-exam": "Re Exam Registration", "Improvement": "Improvement Exam Registration"}
FEE_FIELD = {"Re Exam Registration": "re_exam_fee", "Improvement Exam Registration": "improvement_fee"}


def _failed_grades(exam_plan):
	"""{course: failed grades of its Grading Schema in the plan}."""
	out = {}
	for c in frappe.get_all("Course Schema Assignment", filters={"exam_plan": exam_plan}, fields=["course", "grade_schema"]):
		out[c.course] = set(frappe.get_all("Grading Schema Component", filters={"parent": c.grade_schema, "failed": 1}, pluck="grade")) if c.grade_schema else set()
	return out


def _demands(doctype, names):
	return {d.trigger_ref_name: d for d in frappe.get_all(
		"Fee Demand", filters={"trigger_ref_doctype": doctype, "trigger_ref_name": ["in", names or [""]], "status": ["!=", "Cancelled"]},
		fields=["name", "trigger_ref_name", "status", "original_amount"])}


def students(exam_plan):
	"""Every re-exam and improvement student of the plan, one row per student and
	course and type, with the registration, fee, payment and demand."""
	failed = _failed_grades(exam_plan)
	marks = {(m.student, m.course): m for m in frappe.get_all(
		"Student Course Marks", filters={"exam_plan": exam_plan},
		fields=["student", "course", "grade", "updated_grade", "total_marks", "updated_final_marks", "mfa", "improvement_applied"])}
	regs = {}
	for kind, doctype in TYPES.items():
		for r in frappe.get_all(doctype, filters={"exam_plan": exam_plan, "status": ["!=", "Cancelled"]},
		                        fields=["name", "student", "course", FEE_FIELD[doctype] + " as fee", "payment_status"]):
			regs[(kind, r.student, r.course)] = r
	blocked = {(o.student, o.course) for o in frappe.get_all(
		"Re Exam Student Override", filters={"exam_plan": exam_plan, "is_allowed": 0}, fields=["student", "course"])}

	keys = set()
	for (student, course), m in marks.items():
		grade = m.updated_grade or m.grade
		if grade and (grade == "Ab" or grade in failed.get(course, set())):
			keys.add(("Re-exam", student, course))
	keys |= set(regs)

	students = {s.name: s for s in frappe.get_all("Student Master", filters={"name": ["in", [k[1] for k in keys] or [""]]},
	                                             fields=["name", "first_name", "last_name", "registration_id", "programme_of_study"])}
	courses = dict(frappe.get_all("Course", filters={"name": ["in", [k[2] for k in keys] or [""]]}, fields=["name", "course_name"], as_list=True))
	demands = {}
	for kind, doctype in TYPES.items():
		demands[kind] = _demands(doctype, [r.name for k, r in regs.items() if k[0] == kind])
	markers = {}
	for course in {k[2] for k in keys}:
		markers[course] = grade_markers(course, exam_plan, [k[1] for k in keys if k[2] == course])

	rows = []
	for kind, student, course in sorted(keys, key=lambda k: (k[2], (students.get(k[1]) or {}).get("registration_id") or k[1], k[0])):
		m = marks.get((student, course)) or frappe._dict()
		reg = regs.get((kind, student, course))
		demand = demands[kind].get(reg.name) if reg else None
		st = students.get(student) or frappe._dict()
		mark = grade_marker(m.mfa, "" if m.mfa == "Yes" else markers[course].get(student, ""), is_improved(m))
		rows.append({
			"type": kind, "student": student, "course": course, "course_name": courses.get(course, course),
			"student_name": " ".join(filter(None, [st.first_name, st.last_name])) or student,
			"registration_id": st.registration_id or "", "programme": st.programme_of_study or "",
			"grade": m.updated_grade or m.grade or "", "mark": mark,
			"final_marks": m.updated_final_marks if m.updated_final_marks is not None else m.total_marks,
			"registration": reg.name if reg else "", "fee": flt(reg.fee) if reg else 0,
			"payment_status": (reg.payment_status or "") if reg else "",
			"paid": bool(reg and (reg.payment_status in PAID_STATUSES or (demand and demand.status == "Paid"))),
			"demand": demand.name if demand else "", "demand_status": demand.status if demand else "",
			"allowed": (student, course) not in blocked if kind == "Re-exam" else True,
		})
	return rows


# ── registration window (one for re-exam and improvement) ──────────────────────

def plan_courses(exam_plan):
	return frappe.get_all("Course Schema Assignment", filters={"exam_plan": exam_plan}, pluck="course", order_by="course")


def get_window(exam_plan, course):
	re = frappe.db.get_value("Re Exam Course Setting", {"exam_plan": exam_plan, "course": course},
	                         ["deadline_from", "deadline_to", "payment_gateway"], as_dict=True) or {}
	imp = frappe.db.get_value("Improvement Exam Course Setting", {"exam_plan": exam_plan, "course": course},
	                          ["deadline_from", "deadline_to", "payment_gateway", "registration_limit"], as_dict=True) or {}
	return {
		"deadline_from": re.get("deadline_from") or imp.get("deadline_from"),
		"deadline_to": re.get("deadline_to") or imp.get("deadline_to"),
		"payment_gateway": re.get("payment_gateway") or imp.get("payment_gateway") or "Razorpay",
		"registration_limit": imp.get("registration_limit"),
	}


def save_window(exam_plan, courses, deadline_from=None, deadline_to=None, payment_gateway=None, registration_limit=None):
	"""Write the window to both settings of every course (fees are left as they are)."""
	term = frappe.db.get_value("Exam Plan", exam_plan, "term")
	for course in courses:
		for doctype in ("Re Exam Course Setting", "Improvement Exam Course Setting"):
			name = frappe.db.get_value(doctype, {"exam_plan": exam_plan, "course": course}, "name")
			doc = frappe.get_doc(doctype, name) if name else frappe.get_doc({
				"doctype": doctype, "exam_plan": exam_plan, "course": course, "academic_term": term})
			doc.deadline_from = deadline_from or None
			doc.deadline_to = deadline_to or None
			if payment_gateway:
				doc.payment_gateway = payment_gateway
			if doctype == "Improvement Exam Course Setting":
				doc.registration_limit = cint(registration_limit) or None
			doc.save(ignore_permissions=True)
	frappe.db.commit()
	return len(courses)


# ── enrolment (upload sheet or Enrol dialog) ───────────────────────────────────

def _course_of(text, index):
	from slcm.slcm.utils.exam_sheets import _norm

	return index.get(_norm(text)) if text else None


def plan_enrolment(exam_plan, rows, default_course=None):
	"""What enrolling rows {registration_id | student, course, type, fee} would do:
	enrol (and raise a demand when there is a fee) or skip, with the reason."""
	from slcm.slcm.fee.event_hooks import reexam_fee_component
	from slcm.slcm.utils.exam_sheets import _norm
	from slcm.slcm.utils.reexam_attempts import course_attempts

	courses = plan_courses(exam_plan)
	index = {}
	for c in frappe.get_all("Course", filters={"name": ["in", courses or [""]]}, fields=["name", "course_name", "course_code"]):
		for k in (c.name, c.course_name, c.course_code):
			if k:
				index[_norm(k)] = c.name
	component = reexam_fee_component()
	out = []
	for i, r in enumerate(rows, 2):   # sheet row 1 is the header
		kind = "Improvement" if _norm(r.get("type")).startswith("improv") else "Re-exam"
		fee = flt(str(r.get("fee") or "").replace(",", "").replace("₹", ""))
		course = _course_of(r.get("course"), index) or (r.get("course") if r.get("course") in courses else None) or default_course
		line = {"sheet_row": i, "registration_id": (r.get("registration_id") or "").strip(), "student_name": r.get("student_name") or "",
		        "type": kind, "course": course or (r.get("course") or ""), "fee": fee, "action": "skip", "note": ""}
		student = r.get("student") or (frappe.db.get_value("Student Master", {"registration_id": line["registration_id"]}, "name") if line["registration_id"] else None)
		if not student:
			line["note"] = _("No student with this Registration ID")
		elif not course:
			line["note"] = _("Course not in this exam plan")
		elif frappe.db.exists(TYPES[kind], {"student": student, "exam_plan": exam_plan, "course": course, "status": ["!=", "Cancelled"]}):
			line["note"] = _("Already enrolled")
		else:
			st = frappe.db.get_value("Student Master", student, ["first_name", "last_name", "registration_id"], as_dict=True)
			line.update(student=student, registration_id=st.registration_id or line["registration_id"],
			            student_name=" ".join(filter(None, [st.first_name, st.last_name])) or line["student_name"])
			attempts = course_attempts(student, course)
			last = attempts[-1] if attempts else None
			passed = bool(last and last.result_grade and not last.failed)
			here = any(a.exam_plan == exam_plan for a in attempts)
			limit = cint(frappe.db.get_value("Improvement Exam Course Setting", {"exam_plan": exam_plan, "course": course}, "registration_limit"))
			if kind == "Re-exam" and passed:
				line["note"] = _("Already passed ({0}): use Improvement").format(last.result_grade)
			elif kind == "Improvement" and not passed:
				line["note"] = _("Has not passed this course: use Re-exam")
			elif kind == "Improvement" and not here:
				line["note"] = _("No result for this course in this exam plan")
			elif kind == "Improvement" and limit and frappe.db.count(TYPES[kind], {"exam_plan": exam_plan, "course": course, "status": "Registered"}) >= limit:
				line["note"] = _("Improvement seats full ({0})").format(limit)
			elif fee > 0 and not component:
				line["note"] = _("No Fee Component of type Examination Fee for the demand")
			else:
				line.update(action="enrol", demand=fee > 0, carry=bool(kind == "Re-exam" and last and not here))
				if kind == "Re-exam" and not last:
					line["note"] = _("No marks for this course yet: add the student in Course Results to enter re-exam marks")
				elif line["carry"]:
					line["note"] = _("Marks brought over from {0}").format(last.exam_plan)
		out.append(line)
	return out, component


def enrol(exam_plan, rows, default_course=None):
	"""Enrol the rows that pass plan_enrolment: a Re Exam / Improvement Exam
	Registration each; a fee raises a Fee Demand, no fee means nothing to pay."""
	from slcm.slcm.fee.event_hooks import _get_student_data, reexam_fee_component
	from slcm.slcm.fee.fee_demand_utils import create_event_demand
	from slcm.slcm.utils.reexam_attempts import carry_forward

	lines, _component = plan_enrolment(exam_plan, rows, default_course)
	term = frappe.db.get_value("Exam Plan", exam_plan, "term")
	enrolled, demands, errors = 0, [], []
	for x in lines:
		if x["action"] != "enrol":
			continue
		doctype = TYPES[x["type"]]
		try:
			if x.get("carry"):
				carry_forward(x["student"], x["course"], exam_plan)
			reg = frappe.get_doc({
				"doctype": doctype, "student": x["student"], "exam_plan": exam_plan, "course": x["course"],
				"academic_term": term, FEE_FIELD[doctype]: x["fee"], "status": "Registered",
				# nothing to pay without a fee; with one, the Fee Demand is paid (and marks this Paid)
				"payment_status": "Pending" if x["fee"] > 0 else "Paid",
				"remarks": _("Enrolled by the examination office") + ("" if x["fee"] > 0 else _("; no fee")),
			}).insert(ignore_permissions=True)
			enrolled += 1
			demand = frappe.db.get_value("Fee Demand", {"trigger_ref_doctype": doctype, "trigger_ref_name": reg.name}, "name")
			if not demand and x["fee"] > 0:   # Re Exam Registration raises its own (hook); improvement here
				student_data = _get_student_data(x["student"])
				component = reexam_fee_component()
				demand = create_event_demand(
					student=x["student"], fee_component_name=component, amount=x["fee"],
					demand_type=frappe.db.get_value("Fee Component", component, "demand_type") or "Academic",
					trigger_doctype=doctype, trigger_name=reg.name,
					description=f"Improvement Exam Fee — {x['course']}",
					academic_year=student_data.get("academic_year"), programme=student_data.get("programme"),
				)
			if demand:
				demands.append(demand)
		except Exception as e:
			frappe.clear_messages()
			errors.append(f"{x['registration_id']} · {x['course']}: {e}")
	frappe.db.commit()
	return {"enrolled": enrolled, "demands": demands, "errors": errors}


def mark_paid(kind, registration, reference=""):
	doc = frappe.get_doc(TYPES[kind], registration)
	doc.payment_status = "Paid"
	if reference:
		doc.payment_reference = reference
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return True
