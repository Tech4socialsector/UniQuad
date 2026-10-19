import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class FeeConcession(Document):

	def validate(self):
		self._resolve_student()
		self._sync_dues_details()
		self._calculate_waiver_amount()
		self._validate_waiver_amount()

	def on_submit(self):
		self._apply_waiver()
		self.db_set("status", "Approved")
		self.db_set("approved_by", frappe.session.user)
		self.db_set("approved_on", today())
		if not self.concession_date:
			self.db_set("concession_date", today())

	def _resolve_student(self):
		"""Student comes from the voucher; the Registration Id / Application Number and email
		(as in the bulk-upload sheet) are filled in, or checked against it when supplied."""
		reg = (self.registration_id or "").strip()
		email = (self.student_email or "").strip().lower()

		if self.fee_demand:
			if not frappe.db.exists("Fee Demand", self.fee_demand):
				frappe.throw(_("Voucher Number {0} was not found. It must be an existing Fee Demand ID.").format(self.fee_demand))
			voucher_student = frappe.db.get_value("Fee Demand", self.fee_demand, "student")
			if self.student and voucher_student and self.student != voucher_student:
				frappe.throw(
					_("Voucher {0} belongs to student {1}, not the selected Student ID {2}.").format(
						self.fee_demand, voucher_student, self.student
					)
				)
			self.student = voucher_student or self.student
		elif not self.student and reg:
			self.student = frappe.db.get_value("Student Master", {"registration_id": reg}, "name") or frappe.db.get_value(
				"Student Master", {"application_number": reg}, "name"
			)
		if not self.student:
			frappe.throw(_("Could not identify the student. Enter a Voucher Number or a valid Student Registration Id / Application Number."))

		sm = frappe.db.get_value(
			"Student Master",
			self.student,
			["registration_id", "application_number", "official_email_id", "email", "personal_email"],
			as_dict=True,
		) or frappe._dict()

		if reg and reg not in (sm.registration_id, sm.application_number):
			frappe.throw(
				_("Student Registration Id / Application Number {0} does not match the student on voucher {1}.").format(reg, self.fee_demand)
			)
		emails = {(e or "").strip().lower() for e in (sm.official_email_id, sm.email, sm.personal_email)} - {""}
		if email and email not in emails:
			frappe.throw(_("Student Email Id {0} does not match the student on voucher {1}.").format(self.student_email, self.fee_demand))

		self.registration_id = reg or sm.registration_id or sm.application_number
		self.student_email = self.student_email or sm.official_email_id or sm.email

	def _sync_dues_details(self):
		"""Dues columns always reflect the voucher (the same figures as the bulk-upload sheet)."""
		if not self.fee_demand:
			return
		d = frappe.db.get_value(
			"Fee Demand",
			self.fee_demand,
			["fee_component", "demand_date", "academic_year", "due_date", "remarks", "original_amount",
			 "penalty_amount", "net_payable", "paid_amount", "outstanding_amount"],
			as_dict=True,
		)
		if not d:
			return
		self.update({
			"fee_component": d.fee_component,
			"demand_date": d.demand_date,
			"academic_year": d.academic_year,
			"due_date": d.due_date,
			"remarks": d.remarks,
			"original_amount": d.original_amount,
			"penalty_amount": d.penalty_amount,
			"total_payable": d.net_payable,
			"paid_amount": d.paid_amount,
			"pending_amount": d.outstanding_amount,
		})

	def on_cancel(self):
		self._reverse_waiver()
		self.db_set("status", "Reversed")

	def _calculate_waiver_amount(self):
		# Waiver Value is the amount itself; waiver_amount mirrors it for Fee Demand / reports / portals.
		self.waiver_amount = flt(self.waiver_value)

	def _validate_waiver_amount(self):
		original = flt(self.original_amount)
		waiver = flt(self.waiver_amount)

		if waiver <= 0:
			frappe.throw("Waiver Amount must be greater than zero.")

		if waiver > original:
			frappe.throw(
				f"Waiver Amount (₹{waiver:,.2f}) cannot exceed Original Amount (₹{original:,.2f})."
			)

		# Block if another active concession already covers this demand
		existing = frappe.db.exists(
			"Fee Concession",
			{
				"fee_demand": self.fee_demand,
				"status": "Approved",
				"name": ["!=", self.name],
			}
		)
		if existing:
			frappe.throw(
				f"Fee Demand {self.fee_demand} already has an approved concession ({existing}). "
				"Cancel it before applying a new one."
			)

	def _apply_waiver(self):
		demand = frappe.get_doc("Fee Demand", self.fee_demand)

		if demand.status in ("Paid", "Cancelled"):
			frappe.throw(
				f"Cannot apply waiver — Fee Demand {self.fee_demand} is already {demand.status}."
			)

		paid = flt(demand.paid_amount)
		original = flt(demand.original_amount)
		new_waiver = flt(self.waiver_amount)

		if new_waiver > (original - paid):
			frappe.throw(
				f"Waiver (₹{new_waiver:,.2f}) exceeds the unpaid balance "
				f"(₹{original - paid:,.2f}) on demand {self.fee_demand}."
			)

		demand.waiver_amount = new_waiver
		demand.net_payable = original - new_waiver
		demand.outstanding_amount = max(0, demand.net_payable - paid - flt(demand.credit_adjusted))

		if demand.outstanding_amount == 0 and paid == 0 and new_waiver == original:
			demand.status = "Waived"
		elif demand.outstanding_amount == 0:
			demand.status = "Paid"

		demand.save(ignore_permissions=True)

	def _reverse_waiver(self):
		demand = frappe.get_doc("Fee Demand", self.fee_demand)

		paid = flt(demand.paid_amount)
		original = flt(demand.original_amount)

		demand.waiver_amount = 0
		demand.net_payable = original
		demand.outstanding_amount = max(0, original - paid - flt(demand.credit_adjusted))

		if demand.outstanding_amount > 0:
			demand.status = "Pending"

		demand.save(ignore_permissions=True)


@frappe.whitelist()
def bulk_apply_concession(demand_names, concession_type, waiver_value,
	reason, **kwargs):
	"""
	Create and submit one Fee Concession per selected Fee Demand, using the
	same waiver rule for all of them. Used by the Fee Demand list view's
	"Apply Fee Concession / Waiver" bulk action.
	"""
	if isinstance(demand_names, str):
		demand_names = frappe.parse_json(demand_names)
	if not demand_names:
		frappe.throw(_("Please select at least one Fee Demand."))

	demands = frappe.get_all(
		"Fee Demand",
		filters={"name": ["in", demand_names]},
		fields=["name", "student", "status", "outstanding_amount"],
	)

	created = []
	skipped = []

	for d in demands:
		if d.status in ("Paid", "Cancelled", "Waived") or flt(d.outstanding_amount) <= 0:
			skipped.append({"name": d.name, "reason": _("No outstanding amount / already settled")})
			continue

		if frappe.db.exists("Fee Concession", {"fee_demand": d.name, "status": "Approved"}):
			skipped.append({"name": d.name, "reason": _("Already has an approved concession")})
			continue

		try:
			doc = frappe.get_doc({
				"doctype": "Fee Concession",
				"student": d.student,
				"fee_demand": d.name,
				"concession_type": concession_type,
				"waiver_value": flt(waiver_value),
				"reason": reason,
			})
			doc.insert(ignore_permissions=True)
			doc.submit()
			created.append(doc.name)
		except Exception:
			frappe.log_error(title="Bulk Fee Concession Failed", message=frappe.get_traceback())
			skipped.append({"name": d.name, "reason": _("Could not be processed — see error log")})

	return {"created": created, "skipped": skipped}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def student_query(doctype, txt, searchfield, start, page_len, filters):
	"""Student ID picker: search by ID, name, Registration Id, Application Number or email."""
	txt = f"%{txt}%"
	return frappe.db.sql(
		"""SELECT name, first_name, IFNULL(registration_id, application_number)
		FROM `tabStudent Master`
		WHERE name LIKE %(txt)s OR first_name LIKE %(txt)s OR registration_id LIKE %(txt)s
			OR application_number LIKE %(txt)s OR official_email_id LIKE %(txt)s OR email LIKE %(txt)s
		ORDER BY
			CASE WHEN registration_id LIKE %(txt)s OR name LIKE %(txt)s THEN 0 ELSE 1 END, first_name
		LIMIT %(start)s, %(page_len)s""",
		{"txt": txt, "start": start, "page_len": page_len},
	)


# ── Bulk-upload template (shared implementation in slcm.slcm.fee.bulk_upload) ──
@frappe.whitelist()
def get_template_filter_options():
	from slcm.slcm.fee.bulk_upload import get_filter_options

	return get_filter_options("Fee Concession")


@frappe.whitelist()
def download_bulk_upload_template(academic_year=None, programme=None, fee_component=None, student=None, file_type="Excel"):
	from slcm.slcm.fee.bulk_upload import download_template

	return download_template("Fee Concession", academic_year, programme, fee_component, file_type)


@frappe.whitelist()
def data_import_download_template(doctype, export_fields=None, export_records=None, export_filters=None, file_type="CSV"):
	from slcm.slcm.fee.bulk_upload import data_import_download_template as override

	return override(doctype, export_fields, export_records, export_filters, file_type)
