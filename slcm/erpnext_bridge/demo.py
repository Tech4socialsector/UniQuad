"""Dummy data for testing the SLCM -> ERPNext bridge on a test site. Never run on production.

	bench --site <site> execute slcm.erpnext_bridge.demo.setup --kwargs '{"company": "TFSS"}'
	bench --site <site> execute slcm.erpnext_bridge.demo.create
	bench --site <site> execute slcm.erpnext_bridge.demo.cleanup

Every record is created through the normal SLCM controllers (Fee Demand -> Fee Payment -> Fee Refund ...),
tagged with DEMO_TAG so cleanup() can find and reverse it. Outgoing email is muted while it runs.
"""

import frappe
from frappe.utils import add_days, getdate

DEMO_TAG = "[ERP-BRIDGE-DEMO]"
GST_COMPONENT = "ERP Demo - Certificate Fee (GST)"
PAY_PREFIX = "pay_ERPDEMO"


def _guard():
	if not frappe.conf.get("developer_mode") and not frappe.conf.get("allow_tests"):
		frappe.throw("slcm.erpnext_bridge.demo is only for developer/test sites.")


def setup(company="TFSS"):
	"""Create the demo GST component and the company's fee ledgers, then enable posting on the Company."""
	_guard()
	_ensure_gst_component()
	from slcm.erpnext_bridge.company import validate_company
	from slcm.erpnext_bridge.setup_accounts import setup_fee_accounting

	setup_fee_accounting(company)
	doc = frappe.get_doc("Company", company)
	doc.slcm_enable_fee_posting = 1
	validate_company(doc)  # same checks as saving the Company form
	frappe.db.set_value("Company", company, {"slcm_enable_fee_posting": 1, "slcm_submit_journal_entries": 1})
	frappe.db.commit()
	print(f"{company} ready: posting SLCM fees dated on/after {doc.slcm_posting_from_date}")


def create():
	_guard()
	if frappe.db.exists("Fee Demand", {"remarks": ("like", f"%{DEMO_TAG}%")}):
		print("Demo data already exists - run cleanup() first.")
		return
	frappe.flags.mute_emails = True
	_ensure_gst_component()

	students = frappe.get_all(
		"Student Master",
		filters={"programme_of_study": ("is", "set")},
		pluck="name",
		order_by="name",
		limit=3,
	)
	if len(students) < 3:
		frappe.throw("Need at least 3 Student Master records with a Programme of Study.")
	s1, s2, s3 = students
	banks = [o for o in (frappe.get_meta("Fee Payment").get_field("university_bank_account").options or "").split("\n") if o]

	# ── demands (receivables in SLCM; nothing posts to ERPNext for these) ──
	d = {}
	for student in students:
		d[student, "tuition"] = _demand(student, "Tuition Fee", 60000, "2026-07-01")
		d[student, "hostel"] = _demand(student, "Hostel Fee", 20000, "2026-07-01")
		d[student, "deposit"] = _demand(student, "Caution Deposit", 5000, "2026-07-01")
	d[s1, "cert"] = _demand(s1, GST_COMPONENT, 1180, "2026-08-01")

	# ── receipts ──
	_pay(s1, "Bank Transfer", "2026-07-15", [(d[s1, "tuition"], 60000), (d[s1, "hostel"], 20000)], bank=banks[0] if banks else None, ref="NEFT-DEMO-1001")
	_pay(s1, "Cash", "2026-08-05", [(d[s1, "cert"], 1180)])
	_pay(s1, "Cheque", "2026-08-05", [(d[s1, "deposit"], 5000)], bank=banks[1] if len(banks) > 1 else None, ref="CHQ-778812")

	_pay(s2, "Online Payment", "2026-07-20", [(d[s2, "tuition"], 50000)], ref=f"{PAY_PREFIX}0001")
	_pay(s2, "Online Payment", "2026-08-10", [(d[s2, "deposit"], 5000)], ref=f"{PAY_PREFIX}0002")
	_pay(s2, "Online Payment", "2026-09-15", [(d[s2, "hostel"], 20000)], ref=f"{PAY_PREFIX}0003")

	_pay(s3, "Cheque", "2026-09-01", [(d[s3, "tuition"], 30000)], bank=banks[1] if len(banks) > 1 else None, ref="CHQ-551020")
	_pay(s3, "Bank Transfer", "2026-09-05", [], amount=2500, ref="NEFT-DEMO-ADV")  # advance, not allocated to any demand
	wrong = _pay(s3, "Bank Transfer", "2026-09-20", [(d[s3, "hostel"], 10000)], bank=banks[0] if banks else None, ref="NEFT-DEMO-WRONG")
	wrong.reload()
	wrong.cancel()  # entered by mistake -> its Journal Entry must be cancelled too

	# ── refunds ──
	_refund(s1, d[s1, "hostel"], 5000, "Overpayment", "NEFT", "2026-09-10")
	_refund(s1, d[s1, "deposit"], 5000, "Deposit Refund", "NEFT", "2026-10-05")

	# ── concession (SLCM only: reduces a receivable, no cash -> no ERPNext entry on cash basis) ──
	_concession(s3, d[s3, "tuition"], 10000)

	# ── Razorpay settlements (written the way the webhook does: db updates on the Payment Request) ──
	_settled_request(d[s2, "tuition"], 50000, f"{PAY_PREFIX}0001", "2026-07-22", fees=1000, tax=180, utr="UTRDEMO0722")
	_settled_request(d[s2, "hostel"], 20000, f"{PAY_PREFIX}0003", "2026-09-17", fees=400, tax=72, utr="UTRDEMO0917")
	_settled_request(d[s2, "deposit"], 5000, f"{PAY_PREFIX}0002", None)  # not settled yet -> stays in clearing
	frappe.db.commit()

	from slcm.erpnext_bridge.sync import sync_pending

	print(f"Demo data created. Synced {sync_pending()} documents to ERPNext.")


def cleanup():
	"""Reverse and delete everything create() made (SLCM docs and their Journal Entries)."""
	_guard()
	frappe.flags.mute_emails = True
	like = ("like", f"%{DEMO_TAG}%")
	from slcm.erpnext_bridge.sync import sync_document

	requests = frappe.get_all("SLCM Payment Request", filters={"razorpay_payment_id": ("like", f"{PAY_PREFIX}%")}, pluck="name")
	for name in requests:
		frappe.db.set_value("SLCM Payment Request", name, "settlement_status", "Pending")
		frappe.db.commit()
		sync_document("SLCM Payment Request", name)
	for dt in ("Fee Refund", "Fee Concession", "Fee Payment"):
		for name in frappe.get_all(dt, filters={"reason" if dt != "Fee Payment" else "remarks": like, "docstatus": 1}, pluck="name"):
			frappe.get_doc(dt, name).cancel()
			frappe.db.commit()
			if dt in ("Fee Refund", "Fee Payment"):
				sync_document(dt, name)

	for je in frappe.get_all(
		"Journal Entry",
		filters={"slcm_reference_name": ("in", _demo_names(requests))},
		fields=["name", "docstatus"],
	):
		if je.docstatus == 1:
			print(f"Skipping {je.name}: still submitted")
			continue
		frappe.delete_doc("Journal Entry", je.name, ignore_permissions=True, force=True)

	for name in requests:
		frappe.delete_doc("SLCM Payment Request", name, ignore_permissions=True, force=True)
	for dt, field in (("Fee Refund", "reason"), ("Fee Concession", "reason"), ("Fee Payment", "remarks")):
		for name in frappe.get_all(dt, filters={field: like}, pluck="name"):
			receipt = frappe.db.get_value(dt, name, "receipt") if dt == "Fee Payment" else None
			frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
			if receipt and frappe.db.exists("Fee Receipt", receipt):
				frappe.delete_doc("Fee Receipt", receipt, ignore_permissions=True, force=True)
	for name in frappe.get_all("Fee Demand", filters={"remarks": like}, pluck="name"):
		frappe.delete_doc("Fee Demand", name, ignore_permissions=True, force=True)
	frappe.db.commit()
	print("Demo data removed.")


# ── helpers ─────────────────────────────────────────────────────────────────────


def _demo_names(requests):
	like = ("like", f"%{DEMO_TAG}%")
	names = list(requests)
	names += frappe.get_all("Fee Payment", filters={"remarks": like}, pluck="name")
	names += frappe.get_all("Fee Refund", filters={"reason": like}, pluck="name")
	return names or ["-"]


def _ensure_gst_component():
	if frappe.db.exists("Fee Component", GST_COMPONENT):
		return
	frappe.get_doc(
		{
			"doctype": "Fee Component",
			"component_name": GST_COMPONENT,
			"component_type": "Other",
			"demand_type": "Non Academic",
			"is_taxable": 1,
			"tax_rate": 18,
			"description": f"{DEMO_TAG} taxable component used to test GST posting",
		}
	).insert(ignore_permissions=True)


def _demand(student, component, amount, date):
	doc = frappe.get_doc(
		{
			"doctype": "Fee Demand",
			"student": student,
			"fee_component": component,
			"original_amount": amount,
			"demand_date": date,
			"due_date": add_days(getdate(date), 30),
			"academic_year": frappe.db.get_value("Academic Year", {}, "name", order_by="year_start_date desc"),
			"remarks": f"{DEMO_TAG} {component}",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _pay(student, mode, date, allocations, amount=None, bank=None, ref=None):
	doc = frappe.get_doc(
		{
			"doctype": "Fee Payment",
			"student": student,
			"amount": amount if amount is not None else sum(a for _, a in allocations),
			"payment_date": date,
			"settlement_date": date,
			"payment_mode": mode,
			"university_bank_account": bank,
			"reference_number": ref,
			"status": "Draft",
			"remarks": f"{DEMO_TAG} {mode}",
			"payment_demands": [{"fee_demand": dem, "amount_allocated": amt} for dem, amt in allocations],
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def _refund(student, demand, amount, refund_type, mode, date):
	doc = frappe.get_doc(
		{
			"doctype": "Fee Refund",
			"student": student,
			"refund_source": "Fee Demand",
			"fee_demand": demand,
			"fee_component": frappe.db.get_value("Fee Demand", demand, "fee_component"),
			"refund_type": refund_type,
			"refund_amount": amount,
			"refund_date": date,
			"refund_mode": mode,
			"utr_number": f"UTR-REF-{demand}",
			"reason": f"{DEMO_TAG} {refund_type}",
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()


def _concession(student, demand, amount):
	doc = frappe.get_doc(
		{
			"doctype": "Fee Concession",
			"student": student,
			"fee_demand": demand,
			"concession_type": "University Financial Aid",
			"waiver_value": amount,
			"concession_date": "2026-09-02",
			"reason": f"{DEMO_TAG} financial aid",
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()


def _settled_request(demand, amount, payment_id, settled_on, fees=0, tax=0, utr=None):
	doc = frappe.get_doc(
		{
			"doctype": "SLCM Payment Request",
			"reference_doctype": "Fee Demand",
			"reference_name": demand,
			"amount": amount,
			"currency": "INR",
			"razorpay_payment_id": payment_id,
		}
	)
	doc.insert(ignore_permissions=True)  # left as Draft: submitting would call the live payment gateway
	values = {"status": "Paid", "gateway_status": "captured", "settlement_status": "Pending"}
	if settled_on:
		values.update(
			settlement_status="Settled",
			settlement_date=f"{settled_on} 10:30:00",
			settlement_utr=utr,
			settlement_amount=amount,
			gateway_fees=fees,
			gateway_tax=tax,
			net_settled=amount - fees - tax,
		)
	frappe.db.set_value("SLCM Payment Request", doc.name, values)
