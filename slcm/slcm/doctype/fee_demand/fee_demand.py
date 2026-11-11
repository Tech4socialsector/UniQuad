import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt, today, now_datetime, getdate


# Fee Component types that count as "Academic" — used only as a fallback when a Fee Component has no
# Demand Type of its own (the Fee Component's Demand Type is the source of truth).
ACADEMIC_COMPONENT_TYPES = {
	"Admission Fee", "Re-admission Fee", "Tuition and Facilities Fee", "Tuition Fee",
	"Re-registration Tuition Fee", "Annual Fee (PhD)", "Continuation Fee (PhD)", "Course Work Fee (PhD)",
	"Registration Fee (PhD)", "Gap Year Fee",
}


def demand_type_for_component_type(component_type):
	return "Academic" if component_type in ACADEMIC_COMPONENT_TYPES else "Non Academic"


class FeeDemand(Document):

	def validate(self):
		self._fill_from_student()
		self._set_demand_type()
		self._calculate_amounts()
		self._validate_waiver()
		self._auto_set_description()

	def before_save(self):
		self._update_status()

	def _fill_from_student(self):
		"""Student Email ID (and Academic Year, Programme and Batch when blank) come from the student. A
		supplied email is checked only when the demand is created, so later email changes never block saving."""
		if not self.student:
			return
		sm = frappe.db.get_value(
			"Student Master", self.student,
			["official_email_id", "email", "personal_email", "academic_year", "batch", "programme_of_study"],
			as_dict=True,
		)
		if not sm:
			return
		# Programme / Batch: stamped once so dues can be filtered and fined by programme.
		# Stale links on the student are skipped rather than blocking the demand.
		if not self.programme and sm.batch and frappe.db.exists("SLCM Batch", sm.batch):
			self.programme = sm.batch
		if not self.program:
			from slcm.slcm.fee.fee_demand_utils import _enrolled_programs
			program = _enrolled_programs([self.student]).get(self.student) or sm.programme_of_study
			if program and frappe.db.exists("Programme", program):
				self.program = program
		given = (self.student_email or "").strip().lower()
		known = {(e or "").strip().lower() for e in (sm.official_email_id, sm.email, sm.personal_email)} - {""}
		if self.is_new() and given and known and given not in known:
			frappe.throw(_("Student Email ID {0} does not match student {1}.").format(self.student_email, self.student))
		self.student_email = sm.official_email_id or sm.email or self.student_email
		if not self.academic_year and sm.academic_year and frappe.db.exists("Academic Year", sm.academic_year):
			self.academic_year = sm.academic_year
		if self.is_new() and not self.academic_year:
			frappe.throw(_("Academic Year is required (the student has none to default from)."))

	def _set_demand_type(self):
		"""Demand Type always follows the Fee Component's Demand Type, whatever a caller passed in (event
		hooks, integrations and the bulk upload included), so every demand uses the current Academic /
		Non Academic types."""
		if not self.fee_component:
			return
		comp = frappe.db.get_value("Fee Component", self.fee_component, ["demand_type", "component_type"], as_dict=True) or {}
		options = [o for o in (self.meta.get_field("demand_type").options or "").split("\n") if o]
		if comp.get("demand_type"):
			self.demand_type = comp["demand_type"]
		elif self.demand_type not in options:
			self.demand_type = demand_type_for_component_type(comp.get("component_type"))

	def _calculate_amounts(self):
		self.original_amount = flt(self.original_amount)
		self.waiver_amount = flt(self.waiver_amount)
		self.penalty_amount = flt(self.penalty_amount)
		self.paid_amount = flt(self.paid_amount)
		self.credit_adjusted = flt(self.credit_adjusted)

		self.net_payable = self.original_amount - self.waiver_amount + self.penalty_amount
		self.outstanding_amount = self.net_payable - self.paid_amount - self.credit_adjusted

		# Prevent negative outstanding
		if self.outstanding_amount < 0:
			self.outstanding_amount = 0

	def _validate_waiver(self):
		if flt(self.waiver_amount) < 0:
			frappe.throw(_("Waiver Amount cannot be negative."))
		if flt(self.waiver_amount) > flt(self.original_amount):
			frappe.throw(
				_("Waiver Amount ({0}) cannot exceed Original Amount ({1}).").format(
					self.waiver_amount, self.original_amount
				)
			)

	def _auto_set_description(self):
		if not self.description and self.fee_component:
			self.description = self.fee_component

	def _update_status(self):
		# Full waiver → Waived
		if flt(self.waiver_amount) >= flt(self.original_amount) and flt(self.original_amount) > 0:
			self.status = "Waived"
			return

		# Already manually set to Cancelled or Waived — don't override
		if self.status in ("Cancelled", "Waived"):
			return

		# "Moved to Excess" is kept on ordinary saves; a new payment/reversal recalculates it.
		if self.status == "Moved to Excess" and not self.flags.payment_update:
			return

		outstanding = flt(self.outstanding_amount)
		paid = flt(self.paid_amount)

		if outstanding <= 0 and paid > 0:
			self.status = "Paid"
		# past due and not fully paid → Overdue, even when part-paid (same rule as the daily scheduler)
		elif self.due_date and getdate(self.due_date) < getdate(today()) and outstanding > 0:
			self.status = "Overdue"
		elif paid > 0 and outstanding > 0:
			self.status = "Partially Paid"
		else:
			if self.status not in ("Overdue",):
				self.status = "Pending"

	def update_payment_status(self, paid_delta, credit_delta=0):
		"""
		Called externally by Fee Payment on submit/cancel.
		paid_delta: positive on payment, negative on cancellation.
		credit_delta: positive when credit applied, negative when reversed.
		"""
		self.paid_amount = flt(self.paid_amount) + flt(paid_delta)
		self.credit_adjusted = flt(self.credit_adjusted) + flt(credit_delta)

		if self.paid_amount < 0:
			self.paid_amount = 0
		if self.credit_adjusted < 0:
			self.credit_adjusted = 0

		self.flags.payment_update = True
		self._calculate_amounts()
		self._update_status()
		self.save(ignore_permissions=True)
		self.flags.payment_update = False

		# a re-exam / improvement fee paid through its demand marks the registration paid
		if self.trigger_ref_doctype in ("Re Exam Registration", "Improvement Exam Registration") and self.trigger_ref_name:
			reg_status = "Paid" if self.status == "Paid" else None
			if reg_status or flt(paid_delta) < 0:
				frappe.db.set_value(self.trigger_ref_doctype, self.trigger_ref_name, "payment_status",
				                    reg_status or "Pending", update_modified=False)
		# a hostel fine is paid only through its demand (HostelFine.validate refuses a hand-set Paid)
		if self.trigger_ref_doctype == "Hostel Fine" and self.trigger_ref_name:
			if self.status == "Paid" or flt(paid_delta) < 0:
				frappe.db.set_value("Hostel Fine", self.trigger_ref_name, "status",
				                    "Paid" if self.status == "Paid" else "Unpaid", update_modified=False)

		self._log_payment_event(paid_delta)

	@frappe.whitelist()
	def cancel_demand(self):
		"""Cancel this demand — only allowed if unpaid."""
		self.check_permission("write")
		if self.status == "Paid":
			frappe.throw(_("Cannot cancel a fully paid Fee Demand."))
		if flt(self.paid_amount) > 0:
			frappe.throw(
				_("Cannot cancel a Fee Demand that has partial payments. "
				  "Please reverse the payment first.")
			)
		self.status = "Cancelled"
		self.save(ignore_permissions=True)
		return "Cancelled"

	def _log_payment_event(self, paid_delta):
		event = "Payment Recorded" if paid_delta > 0 else "Payment Reversed"
		try:
			sm = frappe.db.get_value("Student Master", {"student": self.student}, "name")
			row = frappe.get_doc({
				"doctype":      "Student Fee Payment Log",
				"parent":       sm or self.student,
				"parenttype":   "Student Master",
				"parentfield":  "fee_payment_log",
				"event_type":   event,
				"timestamp":    now_datetime(),
				"amount":       abs(paid_delta),
				"fee_demand":   self.name,
				"to_status":    self.status,
				"triggered_by": frappe.session.user,
				"remarks":      f"Fee Demand: {self.name}",
			})
			row.insert(ignore_permissions=True)
		except Exception:
			pass


@frappe.whitelist()
def mark_dues_cleared(demand_names, payment_mode="Cash", remarks=None):
	"""
	Administrative "dues cleared" action for one or more Fee Demands.

	Records a real Fee Payment for each affected student's outstanding
	demands (grouped by student, since Fee Payment is per-student) and
	submits it, so the demand's status/outstanding, receipt generation,
	and payment logs all flow through the existing, already-validated
	payment pipeline instead of hand-editing amounts/status here.
	"""
	if isinstance(demand_names, str):
		demand_names = frappe.parse_json(demand_names)
	if not demand_names:
		frappe.throw(_("Please select at least one Fee Demand."))

	demands = frappe.get_all(
		"Fee Demand",
		filters={"name": ["in", demand_names]},
		fields=["name", "student", "description", "fee_component", "outstanding_amount", "status"],
	)
	if not demands:
		frappe.throw(_("No valid Fee Demand records found."))

	clearable = [
		d for d in demands
		if d.status not in ("Paid", "Cancelled", "Waived") and flt(d.outstanding_amount) > 0
	]
	skipped = [d.name for d in demands if d not in clearable]
	if not clearable:
		frappe.throw(_("None of the selected demands have an outstanding amount to clear."))

	by_student = {}
	for d in clearable:
		by_student.setdefault(d.student, []).append(d)

	created = []
	for student, rows in by_student.items():
		payment = frappe.new_doc("Fee Payment")
		payment.student = student
		payment.payment_date = today()
		payment.payment_mode = payment_mode
		payment.amount = sum(flt(r.outstanding_amount) for r in rows)
		payment.remarks = remarks or _("Dues marked cleared administratively.")
		for r in rows:
			payment.append("payment_demands", {
				"fee_demand": r.name,
				"demand_description": r.description or r.fee_component,
				"outstanding_amount": r.outstanding_amount,
				"amount_allocated": r.outstanding_amount,
			})
		payment.insert(ignore_permissions=True)
		payment.submit()
		created.append(payment.name)

	return {
		"created_payments": created,
		"cleared_demands": [d.name for d in clearable],
		"skipped_demands": skipped,
	}
