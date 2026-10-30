# Copyright (c) 2026, TFSS and contributors
# Application fee payment service - integrates with Payment Request and Applicant Fee Assignment

import frappe
from frappe import _
from frappe.utils import cint, flt


def get_application_fee_doc(admission_cycle):
	"""
	Resolves the Application Fee document for an admission cycle:
	1. Direct link on Admission Cycle.application_fee
	2. Fall back to Application Fee matching the cycle's academic_year
	"""
	if not admission_cycle:
		return None

	app_fee_name = frappe.db.get_value("Admission Cycle", admission_cycle, "application_fee")
	if not app_fee_name:
		academic_year = frappe.db.get_value("Admission Cycle", admission_cycle, "academic_year")
		if academic_year:
			app_fee_name = frappe.db.get_value("Application Fee", {"academic_year": academic_year})

	if app_fee_name:
		try:
			return frappe.get_doc("Application Fee", app_fee_name)
		except Exception:
			return None
	return None


def get_application_fee_for_category(
	program=None,
	admission_cycle=None,
	category=None,
	is_foreign=False,
	applicant=None,
	gender=None,
	pwd=None,
):
	"""
	Returns application fee amount from Application Fee linked to admission cycle.

	Priority:
	1. International candidate (only foriegn_national == "Yes"):
	   returns international_application_fee.
	2. Domestic candidate:
	   a. Women: if gender == "Female" and 'Women' is configured in Application Fee
	   b. PWD: if pwd == "Yes" and 'PWD' is configured in Application Fee
	   c. Vertical Category: if category (SC, ST, OBC-NCL, EWS) is configured
	   d. Fallback to General / Unreserved
	   e. 0 if no match
	"""
	if isinstance(applicant, str):
		try:
			applicant = frappe.get_doc("Applicant", applicant)
		except Exception:
			applicant = None

	if applicant:
		if not admission_cycle:
			admission_cycle = applicant.admission_cycle
		if not program:
			program = applicant.program
		is_foreign = (getattr(applicant, "foriegn_national", "") or "").strip() == "Yes"
		if gender is None:
			gender = getattr(applicant, "gender", None)
		if pwd is None:
			pwd = getattr(applicant, "pwd", None)
		if not category:
			category = getattr(applicant, "whether_scstobc_ncl", None)

	if not admission_cycle:
		return 0

	app_fee = get_application_fee_doc(admission_cycle)
	if not app_fee:
		return 0

	# 1. International
	if is_foreign:
		return flt(getattr(app_fee, "international_application_fee", 0), 2)

	# 2. Domestic
	fee_map = {}
	for row in getattr(app_fee, "application_fee_by_category", []):
		cname = (getattr(row, "admission_category", "") or "").strip().lower()
		if cname:
			fee_map[cname] = flt(row.application_fee, 2)

	# a. Women
	if (gender or "").strip().lower() == "female":
		if "women" in fee_map:
			return fee_map["women"]

	# b. PWD
	if (pwd or "").strip().lower() == "yes":
		if "pwd" in fee_map:
			return fee_map["pwd"]

	# c. Vertical Category
	if category:
		cat_key = category.strip().lower()
		if cat_key in fee_map:
			return fee_map[cat_key]

	# d. General
	for gen_key in ("general", "gen", "unreserved"):
		if gen_key in fee_map:
			return fee_map[gen_key]

	return 0


def get_payment_gateway_for_application_fee(program=None, admission_cycle=None):
	"""
	Returns Payment Gateway from Application Fee document for the admission cycle.
	"""
	cycle = admission_cycle or program
	if cycle and not frappe.db.exists("Admission Cycle", cycle) and admission_cycle:
		cycle = admission_cycle
	if not cycle:
		return None

	app_fee = get_application_fee_doc(cycle)
	if app_fee and getattr(app_fee, "payment_gateway", None):
		return app_fee.payment_gateway
	return None


def get_payment_receipt_template_for_policy(program=None, admission_cycle=None):
	"""
	Returns Payment Receipt Template (Print Format) from Application Fee document.
	"""
	cycle = admission_cycle or program
	if cycle and not frappe.db.exists("Admission Cycle", cycle) and admission_cycle:
		cycle = admission_cycle
	if not cycle:
		return None

	app_fee = get_application_fee_doc(cycle)
	if app_fee and getattr(app_fee, "payment_receipt_template", None):
		return app_fee.payment_receipt_template
	return None


def get_or_create_application_fee_component():
	"""Ensure Fee Component 'Application Fee' exists for Applicant Fee Component child rows."""
	if frappe.db.exists("Fee Component", "Application Fee"):
		return "Application Fee"
	comp = frappe.new_doc("Fee Component")
	comp.component_name = "Application Fee"
	comp.component_type = "Other"
	comp.demand_type = "Non Academic"
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
	is_foreign = (applicant.foriegn_national or "").strip() == "Yes"
	fee_amount = flt(
		get_application_fee_for_category(
			program=applicant.program,
			admission_cycle=applicant.admission_cycle,
			category=applicant.whether_scstobc_ncl,
			is_foreign=is_foreign,
			applicant=applicant,
		),
		2,
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
	Get reservation category for fee calculation & assignment.
	Order of preference:
	1. International (if foriegn_national == "Yes")
	2. Women (if gender == "Female" and configured in Application Fee)
	3. PWD (if pwd == "Yes" and configured in Application Fee)
	4. Specific reserved vertical categories (SC/ST/OBC-NCL/EWS)
	5. General / Unreserved
	"""
	if not applicant_name or not frappe.db.exists("Applicant", applicant_name):
		return None

	app_data = frappe.db.get_value(
		"Applicant",
		applicant_name,
		["admission_cycle", "foriegn_national", "gender", "pwd", "whether_scstobc_ncl"],
		as_dict=True,
	)
	if not app_data:
		return None

	if (app_data.foriegn_national or "").strip() == "Yes":
		return "International"

	app_fee = get_application_fee_doc(app_data.admission_cycle)
	configured_categories = set()
	if app_fee:
		for row in getattr(app_fee, "application_fee_by_category", []):
			if row.admission_category:
				configured_categories.add(row.admission_category.strip().lower())

	# 1. Women
	if (app_data.gender or "").strip().lower() == "female" and "women" in configured_categories:
		return "Women"

	# 2. PWD
	if (app_data.pwd or "").strip().lower() == "yes" and "pwd" in configured_categories:
		return "PWD"

	# 3. Vertical category from whether_scstobc_ncl
	vert = (app_data.whether_scstobc_ncl or "").strip()
	if vert and vert.lower() in configured_categories:
		return vert

	# 4. Vertical category from Applicant Category child table
	rows = frappe.get_all(
		"Applicant Category",
		filters={"parent": applicant_name, "parenttype": "Applicant"},
		fields=["category"],
		order_by="idx asc",
	)
	if rows:
		for row in rows:
			name = (row.category or "").strip()
			if name and name.lower() not in ("general", "gen", "unreserved"):
				return name

	if vert and vert.upper() in {"SC", "ST", "OBC-NCL", "EWS"}:
		return vert

	if rows:
		return (rows[0].category or "").strip() or "General"

	return vert or "General"


@frappe.whitelist()
def get_application_fee_details(applicant_name):
	"""
	Returns application fee amount, currency, and status for the given Applicant.
	Used by the portal UI to show fee and enable/disable pay button.
	"""
	applicant = frappe.get_doc("Applicant", applicant_name)
	category = _get_applicant_category(applicant_name)
	is_foreign = (applicant.foriegn_national or "").strip() == "Yes"

	fee_amount = get_application_fee_for_category(
		program=applicant.program,
		admission_cycle=applicant.admission_cycle,
		category=applicant.whether_scstobc_ncl,
		is_foreign=is_foreign,
		applicant=applicant,
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

	app_fee = get_application_fee_doc(applicant.admission_cycle)
	currency = getattr(app_fee, "currency", None) or "INR"

	return {
		"applicant_name": applicant_name,
		"fee_amount": fee_amount,
		"currency": currency,
		"application_fee_status": status,
		"reservation_category": category,
		"program": applicant.program,
		"can_submit": status in ("Paid", "Waived"),
		"online_payment_enabled": True,
		"payment_gateway": payment_gateway,
	}
