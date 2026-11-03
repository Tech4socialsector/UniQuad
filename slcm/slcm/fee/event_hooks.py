import frappe
from frappe.utils import flt, today, add_days
from slcm.slcm.fee.fee_demand_utils import create_event_demand

DEMAND_DUE_DAYS = 30


def _get_component_by_type(component_type):
	"""Return the Fee Component name matching a given component_type."""
	return frappe.get_value("Fee Component", {"component_type": component_type}, "name")


def _cancel_demand_for_trigger(trigger_doctype, trigger_name):
	"""Cancel any active Fee Demand created by a specific trigger document."""
	demands = frappe.get_all(
		"Fee Demand",
		filters={
			"trigger_ref_doctype": trigger_doctype,
			"trigger_ref_name": trigger_name,
			"status": ["not in", ["Paid", "Cancelled"]],
		},
		fields=["name", "paid_amount"],
	)
	for d in demands:
		if flt(d.paid_amount) > 0:
			frappe.log_error(
				f"Cannot cancel demand {d.name} — partial payment exists.",
				"EventHooks: Cancel Demand"
			)
			continue
		demand_doc = frappe.get_doc("Fee Demand", d.name)
		demand_doc.status = "Cancelled"
		demand_doc.save(ignore_permissions=True)


def _get_student_data(student, fields=None):
	"""Fetch student fields safely, ignoring missing columns."""
	if fields is None:
		fields = ["academic_year", "programme"]
	return frappe.db.get_value("Student Master", student, fields, as_dict=True) or {}


# ─── 1. Hostel Room Allocated ────────────────────────────────────────────────

def on_hostel_allocation_insert(doc, method=None):
	"""Create Housing and Mess Fee demand when a hostel room is allocated."""
	component = _get_component_by_type("Housing and Mess Fee")
	if not component:
		frappe.log_error("Fee Component with type 'Housing and Mess Fee' not found.", "EventHooks")
		return

	amount = frappe.get_value(
		"Fee Structure",
		{"status": "Active", "demand_type": "Hostel"},
		"total_amount"
	) or 0

	if not amount:
		frappe.log_error(
			f"No active Hostel Fee Structure found for student {doc.student}",
			"EventHooks: Hostel Allocation"
		)
		return

	student_data = _get_student_data(doc.student)

	create_event_demand(
		student=doc.student,
		fee_component_name=component,
		amount=amount,
		demand_type="Hostel",
		due_days=DEMAND_DUE_DAYS,
		trigger_doctype="Hostel Allocation",
		trigger_name=doc.name,
		description="Housing and Mess Fee",
		academic_year=student_data.get("academic_year"),
		programme=student_data.get("programme"),
	)


def on_hostel_allocation_trash(doc, method=None):
	"""Cancel housing demand if hostel allocation is deleted."""
	_cancel_demand_for_trigger("Hostel Allocation", doc.name)


# ─── 2. Course Re-registration Submitted ────────────────────────────────────

def on_course_reregistration_submit(doc):
	"""Create Re-registration Tuition Fee demand (₹1,500 × courses)."""
	component = _get_component_by_type("Re-registration Tuition Fee")
	if not component:
		frappe.log_error("Fee Component 'Re-registration Tuition Fee' not found.", "EventHooks")
		return

	total = flt(doc.number_of_courses) * flt(doc.fee_per_course)

	student_data = _get_student_data(doc.student, ["programme"])

	create_event_demand(
		student=doc.student,
		fee_component_name=component,
		amount=total,
		demand_type="Academic",
		due_days=DEMAND_DUE_DAYS,
		trigger_doctype="Course Reregistration",
		trigger_name=doc.name,
		description=f"Re-registration Tuition Fee ({doc.number_of_courses} course(s) × ₹{doc.fee_per_course:,.0f})",
		academic_year=doc.academic_year,
		programme=student_data.get("programme"),
	)


def on_course_reregistration_cancel(doc):
	_cancel_demand_for_trigger("Course Reregistration", doc.name)


# ─── 3. Re Exam Registration Submitted (after_insert) ───────────────────────

def on_reexam_registration_insert(doc, method=None):
	"""Create Examination Fee demand when exam is registered."""
	if doc.status != "Registered":
		return

	component = _get_component_by_type("Examination Fee") or _get_component_by_type("Revaluation Fee")
	if not component:
		frappe.log_error("Fee Component 'Examination Fee' not found.", "EventHooks")
		return

	amount = flt(doc.re_exam_fee) or 500.0

	student_data = _get_student_data(doc.student)

	create_event_demand(
		student=doc.student,
		fee_component_name=component,
		amount=amount,
		demand_type=frappe.db.get_value("Fee Component", component, "demand_type") or "Academic",
		due_days=DEMAND_DUE_DAYS,
		trigger_doctype="Re Exam Registration",
		trigger_name=doc.name,
		description=f"Examination Fee — {doc.course or 'Re-exam'}",
		academic_year=student_data.get("academic_year"),
		programme=student_data.get("programme"),
	)


# ─── 4. Revaluation Request Submitted ───────────────────────────────────────

def on_revaluation_request_submit(doc):
	"""Create Revaluation Fee demand."""
	component = _get_component_by_type("Revaluation Fee")
	if not component:
		frappe.log_error("Fee Component 'Revaluation Fee' not found.", "EventHooks")
		return

	total = flt(doc.number_of_papers) * flt(doc.fee_per_paper)

	student_data = _get_student_data(doc.student, ["programme"])

	create_event_demand(
		student=doc.student,
		fee_component_name=component,
		amount=total,
		demand_type=frappe.db.get_value("Fee Component", component, "demand_type") or "Academic",
		due_days=DEMAND_DUE_DAYS,
		trigger_doctype="Revaluation Request",
		trigger_name=doc.name,
		description=f"Revaluation Fee ({doc.number_of_papers} paper(s) × ₹{doc.fee_per_paper:,.0f})",
		academic_year=doc.academic_year,
		programme=student_data.get("programme"),
	)


def on_revaluation_request_cancel(doc):
	_cancel_demand_for_trigger("Revaluation Request", doc.name)


# ─── 5. Deferral Order Issued ────────────────────────────────────────────────

def on_deferral_order_submit(doc):
	"""Create Gap Year Fee demand."""
	component = _get_component_by_type("Gap Year Fee")
	if not component:
		frappe.log_error("Fee Component 'Gap Year Fee' not found.", "EventHooks")
		return

	student_data = _get_student_data(doc.student, ["programme"])

	create_event_demand(
		student=doc.student,
		fee_component_name=component,
		amount=flt(doc.gap_year_fee),
		demand_type="Academic",
		due_days=DEMAND_DUE_DAYS,
		trigger_doctype="Deferral Order",
		trigger_name=doc.name,
		description="Gap Year Fee",
		academic_year=doc.academic_year,
		programme=student_data.get("programme"),
	)


def on_deferral_order_cancel(doc):
	_cancel_demand_for_trigger("Deferral Order", doc.name)


# ─── 6. Hostel Fine Issued ───────────────────────────────────────────────────

def on_hostel_fine_insert(doc, method=None):
	"""Create Fine — Hostel demand when a hostel fine is raised."""
	component = _get_component_by_type("Fine - Hostel")
	if not component:
		frappe.log_error("Fee Component 'Fine - Hostel' not found.", "EventHooks")
		return

	student_data = _get_student_data(doc.student)

	create_event_demand(
		student=doc.student,
		fee_component_name=component,
		amount=flt(doc.amount),
		demand_type="Fine",
		due_days=15,
		trigger_doctype="Hostel Fine",
		trigger_name=doc.name,
		description=f"Hostel Fine — {doc.reason or 'Hostel violation'}",
		academic_year=student_data.get("academic_year"),
		programme=student_data.get("programme"),
	)


# ─── 7. Discipline Order Issued ──────────────────────────────────────────────

def on_discipline_order_submit(doc):
	"""Create Fine — Disciplinary demand when a discipline order is issued."""
	component = _get_component_by_type("Fine - Disciplinary")
	if not component:
		frappe.log_error("Fee Component 'Fine - Disciplinary' not found.", "EventHooks")
		return

	student_data = _get_student_data(doc.student, ["programme"])

	create_event_demand(
		student=doc.student,
		fee_component_name=component,
		amount=flt(doc.fine_amount),
		demand_type="Fine",
		due_days=15,
		trigger_doctype="Discipline Order",
		trigger_name=doc.name,
		description=f"Disciplinary Fine — {doc.reason or 'Discipline violation'}",
		academic_year=doc.academic_year,
		programme=student_data.get("programme"),
	)


def on_discipline_order_cancel(doc):
	_cancel_demand_for_trigger("Discipline Order", doc.name)


# ─── 8. Convocation Registration Submitted ──────────────────────────────────

def on_convocation_registration_submit(doc, method=None):
	"""Fee demand is created inside the DocType controller on_submit; nothing extra needed here."""
	pass


def on_convocation_registration_cancel(doc, method=None):
	"""Fee demand is cancelled inside the DocType controller on_cancel; nothing extra needed here."""
	pass
