# Copyright (c) 2026, TFSS and contributors
# Application fee payment service - integrates with Payment Request and Applicant Fee Assignment

import frappe
from frappe import _
from frappe.utils import cint, flt


def get_application_fee_for_category(program, admission_cycle, category, is_foreign=False):
	"""
	Returns the application fee amount from Programme Reservation Policy
	based on program, admission_cycle, and category (Admission Category name).

	Look up Programme Reservation Policy for the given program+cycle,
	then find the Programme Reservation Category row where category_name matches.
	Returns application_fee or 0 if not found.
	"""
	if not program or not admission_cycle:
		return 0

	acp = frappe.db.get_value(
		"Admission Cycle Program",
		{"parent": admission_cycle, "program": program},
		["reservation_applicable", "application_fee_indian", "application_fee_foreign"],
		as_dict=True
	)
	if acp and not acp.reservation_applicable:
		return flt(acp.application_fee_foreign if is_foreign else acp.application_fee_indian, 2)

	policy_data = frappe.db.get_value(
		"Programme Reservation Policy",
		{"program": program, "admission_cycle": admission_cycle, "status": "Active"},
		["name", "application_fee_for_foreign"],
		as_dict=True
	)
	if not policy_data:
		policy_data = frappe.db.get_value(
			"Programme Reservation Policy",
			{"program": program, "admission_cycle": admission_cycle},
			["name", "application_fee_for_foreign"],
			as_dict=True
		)
	if not policy_data:
		return 0

	policy = policy_data.name

	rows = frappe.get_all(
		"Programme Reservation Category",
		filters={"parent": policy, "parenttype": "Programme Reservation Policy"},
		fields=["category_name", "application_fee_for_indian"]
	)

	def _get_fee(row):
		if is_foreign:
			return flt(policy_data.application_fee_for_foreign, 2)
		return flt(row.application_fee_for_indian, 2)

	category_str = (category or "").strip()
	for row in rows:
		if row.category_name == category_str or (row.category_name and row.category_name.strip() == category_str):
			return _get_fee(row)

	for row in rows:
		if (row.category_name or "").lower() in ("general", "gen", "unreserved", ""):
			return _get_fee(row)

	return 0


def get_payment_gateway_for_application_fee(program, admission_cycle):
	"""
	Returns the Payment Gateway from Programme Reservation Policy for the given program and admission_cycle.
	Uses the same policy lookup as get_application_fee_for_category (Active first, then any).
	"""
	if not program or not admission_cycle:
		return None

	acp = frappe.db.get_value(
		"Admission Cycle Program",
		{"parent": admission_cycle, "program": program},
		["reservation_applicable", "payment_gateway"],
		as_dict=True
	)
	if acp and not acp.reservation_applicable:
		return acp.payment_gateway

	gateway = frappe.db.get_value(
		"Programme Reservation Policy",
		{"program": program, "admission_cycle": admission_cycle, "status": "Active"},
		"payment_gateway"
	)
	if not gateway:
		gateway = frappe.db.get_value(
			"Programme Reservation Policy",
			{"program": program, "admission_cycle": admission_cycle},
			"payment_gateway"
		)
	return gateway


def get_payment_receipt_template_for_policy(program, admission_cycle):
	"""
	Return Print Format name from Programme Reservation Policy (same lookup as fee / gateway).
	"""
	if not program or not admission_cycle:
		return None

	acp = frappe.db.get_value(
		"Admission Cycle Program",
		{"parent": admission_cycle, "program": program},
		["reservation_applicable", "payment_receipt_template"],
		as_dict=True
	)
	if acp and not acp.reservation_applicable:
		return acp.payment_receipt_template

	template = frappe.db.get_value(
		"Programme Reservation Policy",
		{"program": program, "admission_cycle": admission_cycle, "status": "Active"},
		"payment_receipt_template",
	)
	if not template:
		template = frappe.db.get_value(
			"Programme Reservation Policy",
			{"program": program, "admission_cycle": admission_cycle},
			"payment_receipt_template",
		)
	return template


def get_or_create_application_fee_component():
	"""Ensure Fee Component 'Application Fee' exists for Applicant Fee Component child rows."""
	if frappe.db.exists("Fee Component", "Application Fee"):
		return "Application Fee"
	comp = frappe.new_doc("Fee Component")
	comp.component_name = "Application Fee"
	comp.component_type = "Other"
	comp.amount = 0
	comp.insert(ignore_permissions=True)
	return comp.name


def _application_fee_component_row(fee_component_name, amount):
	amt = flt(amount, 2)
	return {
		"fee_component": fee_component_name,
		"component_name": "Application Fee",
		"amount": amt,
		"is_taxable": 0,
		"tax_rate": 0,
		"tax_amount": 0,
		"total_amount": amt,
	}


def _scholarship_benefit_for_applicant(applicant_name, admission_cycle):
	"""Approved scholarship total for applicant + cycle (same rule as AFA.apply_scholarship)."""
	if not applicant_name or not admission_cycle:
		return 0
	total_benefit = frappe.db.sql(
		"""
		SELECT SUM(calculated_benefit)
		FROM `tabScholarship Application`
		WHERE applicant_id = %s
		AND admission_cycle = %s
		AND status = 'Approved'
		""",
		(applicant_name, admission_cycle),
	)[0][0]
	return flt(total_benefit or 0)


def _write_afa_application_fee_grid(doc, fee_component_name, fee_amount, sch, applicant):
	"""Replace fee_components with one Application Fee line; set scholarship; recalc via validate."""
	doc.fee_components = []
	doc.append(
		"fee_components",
		_application_fee_component_row(fee_component_name, fee_amount),
	)
	doc.scholarship_amount = sch
	doc.scholarship_applied = 1 if sch > 0 else 0
	doc.program = applicant.program
	doc.admission_cycle = applicant.admission_cycle
	doc.academic_year = applicant.academic_year


def sync_application_fee_assignment_for_applicant(applicant_name):
	"""
	Create or update Applicant Fee Assignment for Application Fee.

	- Amount is stored in ``fee_components`` (same fields as Applicant Payment Receipt row:
	  fee_component, component_name, amount, is_taxable, tax_rate, tax_amount, total_amount).
	- ``application_fee`` is kept in sync with the grid total (see calculate_totals).
	- Uses ``doc.save()`` so the desk form stays clean (no orphan ``Not Saved`` state from db_set-only).
	- ``status`` is ``Assigned`` until Applicant application fee is ``Paid``; then ``Paid``.
	"""
	applicant_name = (applicant_name or "").strip()
	if not applicant_name or not frappe.db.exists("Applicant", applicant_name):
		return None

	applicant = frappe.get_doc("Applicant", applicant_name)
	if not applicant.program or not applicant.admission_cycle:
		return None

	category = _get_applicant_category(applicant_name)
	is_foreign = applicant.foriegn_national == "Yes"
	fee_amount = flt(
		get_application_fee_for_category(applicant.program, applicant.admission_cycle, category, is_foreign=is_foreign), 2
	)

	if fee_amount > 0 and flt(applicant.application_fee_amount or 0) != fee_amount:
		frappe.db.set_value("Applicant", applicant_name, "application_fee_amount", fee_amount)

	fee_status = (applicant.application_fee_status or "").strip()
	if fee_amount <= 0 and fee_status != "Paid":
		return None

	target_status = "Paid" if fee_status == "Paid" else "Assigned"

	sch = _scholarship_benefit_for_applicant(applicant_name, applicant.admission_cycle)

	fee_component_name = get_or_create_application_fee_component()

	existing = frappe.db.get_value(
		"Applicant Fee Assignment",
		{"applicant": applicant_name, "fee_type": "Application Fee", "status": ["!=", "Cancelled"]},
		"name",
	)

	def _finalize_status(afa_name):
		if target_status == "Paid":
			frappe.db.set_value(
				"Applicant Fee Assignment", afa_name, "status", "Paid", update_modified=True
			)

	if existing:
		doc = frappe.get_doc("Applicant Fee Assignment", existing)
		if doc.docstatus == 2:
			return doc.name
		doc.flags.ignore_permissions = True
		_write_afa_application_fee_grid(doc, fee_component_name, fee_amount, sch, applicant)
		# AFA is often submitted; programme/cycle must follow Applicant (e.g. portal switch).
		if cint(doc.docstatus) == 1:
			doc.flags.ignore_validate_update_after_submit = True
		doc.save()
		if doc.docstatus == 0:
			doc.reload()
			doc.submit()
		_finalize_status(doc.name)
		return doc.name

	assignment = frappe.new_doc("Applicant Fee Assignment")
	assignment.applicant = applicant_name
	assignment.fee_type = "Application Fee"
	assignment.offer_letter = None
	assignment.program = applicant.program
	assignment.admission_cycle = applicant.admission_cycle
	assignment.academic_year = applicant.academic_year
	assignment.assignment_date = frappe.utils.today()
	assignment.flags.ignore_permissions = True
	_write_afa_application_fee_grid(assignment, fee_component_name, fee_amount, sch, applicant)
	assignment.insert()
	assignment.submit()
	_finalize_status(assignment.name)
	return assignment.name


@frappe.whitelist()
def desk_resync_application_fee_assignment(afa_name):
	"""Desk: rebuild Application Fee grid from Applicant + policy; then commit."""
	afa_name = (afa_name or "").strip()
	if not afa_name:
		frappe.throw(_("Applicant Fee Assignment is required."))
	doc = frappe.get_doc("Applicant Fee Assignment", afa_name)
	if doc.fee_type != "Application Fee":
		frappe.throw(_("Only Application Fee assignments can be synced here."))
	if not doc.applicant:
		frappe.throw(_("Applicant is not set."))
	doc.check_permission("write")
	sync_application_fee_assignment_for_applicant(doc.applicant)
	frappe.db.commit()
	return {"ok": 1, "name": doc.applicant}


def create_application_fee_assignment(applicant_name):
	"""Backward-compatible alias for payment/order flows."""
	return sync_application_fee_assignment_for_applicant(applicant_name)


def _get_applicant_category(applicant_name):
	"""
	Get reservation category for fee calculation.

	Order of preference:
	1. Applicant Category child rows – prefer specific reserved categories (SC/ST/OBC-NCL)
	   over generic ones like "General" / "Unreserved".
	2. If child rows are missing or only General, fall back to Applicant.whether_scstobc_ncl
	   when it is set to a reserved value.
	"""
	rows = frappe.get_all(
		"Applicant Category",
		filters={"parent": applicant_name, "parenttype": "Applicant"},
		fields=["category"],
		order_by="idx asc",
	)

	# 1) Prefer explicit categories from child table
	if rows:
		for row in rows:
			name = (row.category or "").strip()
			if name and name.lower() not in ("general", "gen", "unreserved"):
				return name

	# 2) Fallback to Applicant.whether_scstobc_ncl when it's a reserved code
	raw = frappe.db.get_value("Applicant", applicant_name, "whether_scstobc_ncl") or ""
	code = raw.strip()
	if code and code.upper() in {"SC", "ST", "OBC-NCL"}:
		return code

	# 3) Last resort: use first child row (usually General), or None
	if rows:
		return (rows[0].category or "").strip() or None
	return None


@frappe.whitelist()
def get_application_fee_details(applicant_name):
	"""
	Returns application fee amount and status for the given Applicant.
	Used by the portal UI to show fee and enable/disable pay button.
	"""
	applicant = frappe.get_doc("Applicant", applicant_name)
	category = _get_applicant_category(applicant_name)
	is_foreign = applicant.foriegn_national == "Yes"

	fee_amount = get_application_fee_for_category(
		applicant.program, applicant.admission_cycle, category, is_foreign=is_foreign
	)

	if fee_amount != flt(applicant.application_fee_amount):
		frappe.db.set_value("Applicant", applicant_name, "application_fee_amount", fee_amount)
		frappe.db.commit()

	status = applicant.application_fee_status or "Pending"

	try:
		sync_application_fee_assignment_for_applicant(applicant_name)
		frappe.db.commit()
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"get_application_fee_details — sync_application_fee_assignment_for_applicant",
		)

	payment_gateway = get_payment_gateway_for_application_fee(
		applicant.program, applicant.admission_cycle
	)

	return {
		"applicant_name": applicant_name,
		"fee_amount": fee_amount,
		"application_fee_status": status,
		"reservation_category": category,
		"program": applicant.program,
		"can_submit": status in ("Paid", "Waived"),
		"online_payment_enabled": True,
		"payment_gateway": payment_gateway
	}
