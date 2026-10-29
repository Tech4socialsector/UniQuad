"""Integration tests for the SLCM -> ERPNext bridge.

sync_document() commits (it runs as a background job), so these tests cannot rely on rollback: every record
is tagged and removed in tearDown, and the Company's SLCM settings are restored after each test.
Needs a configured company (bench execute slcm.erpnext_bridge.demo.setup) and the Redis cache running.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from slcm.erpnext_bridge import config as conf
from slcm.erpnext_bridge import install, sync
from slcm.erpnext_bridge.company import validate_company

TAG = "[ERP-BRIDGE-TEST]"
PAY_ID = "pay_ERPTEST0001"
TEST_COMPONENT = "ERP Bridge Test Component"
TEST_GST_COMPONENT = "ERP Bridge Test GST Component"
# Admission / PACE / FLE / stipend / refund test records, found for cleanup by TAG in this field.
OTHER_SOURCES = (
	("Applicant Payment Receipt", "remarks"),
	("PACE Receipt", "applicant_name"),
	("FLE Payment Log", "full_name"),
	("Refund Transaction", "failure_reason"),
	("Stipend Payment", "remarks"),
)
SAVED_FIELDS = (*conf.COMPANY_FIELDS, "default_cash_account", "default_bank_account")


class TestSLCMERPNextBridge(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.flags.mute_emails = True
		cls.company = conf.get_posting_company()
		if not cls.company:
			raise cls.skipTest(cls, "Run slcm.erpnext_bridge.demo.setup first (needs a company with posting enabled)")
		cls.student = frappe.get_all(
			"Student Master", filters={"programme_of_study": ("is", "set")}, pluck="name", limit=1
		)[0]
		from_date = frappe.db.get_value("Company", cls.company, "slcm_posting_from_date")
		cls.date = str(max(getdate(from_date), getdate("2026-09-01")))
		cls.tuition = cls._component_with_own_ledger()
		if not cls.tuition:
			raise cls.skipTest(cls, "No Fee Component has its own income ledger; run Create SLCM Fee Ledgers first")

	@classmethod
	def _component_with_own_ledger(cls):
		"""A non-taxable, non-deposit Fee Component whose Ledger has a matching income Account on this site,
		preferring tuition. Keeps the tests independent of any one site's component names."""
		cfg = conf.get_config()
		components = frappe.get_all(
			"Fee Component",
			filters={"is_taxable": 0, "name": ("!=", TEST_COMPONENT)},
			fields=["name", "component_type"],
			order_by="name",
		)
		components.sort(key=lambda c: "tuition" not in c.name.lower())
		for c in components:
			if "deposit" in c.name.lower() or "deposit" in (c.component_type or "").lower():
				continue
			account, used_default = conf.component_account(cfg, c.name)
			if not used_default and frappe.get_cached_value("Account", account, "root_type") == "Income":
				return c.name
		return None

	def setUp(self):
		self.deleted_sources = []  # names of test sources deleted inside a test, so their entries are cleaned up
		self.saved = frappe.db.get_value("Company", self.company, list(SAVED_FIELDS), as_dict=True)
		self.cfg = conf.get_config()

	def tearDown(self):
		try:
			self._remove_test_records()
		finally:
			frappe.db.rollback()
			frappe.db.set_value("Company", self.company, dict(self.saved))
			frappe.clear_document_cache("Company", self.company)
			frappe.db.commit()

	def _remove_test_records(self):
		like = ("like", f"%{TAG}%")
		requests = frappe.get_all("SLCM Payment Request", filters={"razorpay_payment_id": PAY_ID}, pluck="name")
		names = list(requests)
		notes = frappe.get_all("Student Credit Note", filters={"remarks": like}, pluck="name")
		names += notes
		names += frappe.get_all("Credit Adjustment Row", filters={"parent": ("in", notes or ["-"])}, pluck="name")
		for dt, field in OTHER_SOURCES:
			names += frappe.get_all(dt, filters={field: like}, pluck="name")
		names += self.deleted_sources
		for name in frappe.get_all("Stipend Payment", filters={"remarks": like, "docstatus": 1}, pluck="name"):
			frappe.get_doc("Stipend Payment", name).cancel()
		sources = (("Fee Refund", "reason"), ("Fee Concession", "reason"), ("Fee Payment", "remarks"))
		for dt, field in sources:
			for name, docstatus in frappe.get_all(dt, filters={field: like}, fields=["name", "docstatus"], as_list=True):
				names.append(name)
				if docstatus == 1:
					frappe.get_doc(dt, name).cancel()
		frappe.db.commit()
		# Wait for any background sync of these documents (doc_events) to finish before deleting their entries:
		# take the same per-document lock sync_document uses.
		locks = [sync._lock_name(dt, name) for name in names for dt in sync.SOURCES]
		for lock in locks:
			frappe.db.sql("select get_lock(%s, 60)", lock)
		try:
			self._delete_test_records(names, requests, sources, like)
		finally:
			for lock in locks:
				frappe.db.sql("select release_lock(%s)", lock)

	def _delete_test_records(self, names, requests, sources, like):
		frappe.db.commit()  # fresh snapshot after waiting on the locks
		for name in frappe.get_all("Journal Entry", filters={"slcm_reference_name": ("in", names or ["-"])}, pluck="name"):
			# A background worker may be cancelling the same entry (doc_events); always work on a fresh copy.
			je = frappe.get_doc("Journal Entry", name)
			if je.docstatus == 1:
				je.cancel()
			frappe.delete_doc("Journal Entry", name, force=True, ignore_permissions=True)
		for name in requests:
			frappe.delete_doc("SLCM Payment Request", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Student Credit Note", filters={"remarks": like}, pluck="name"):
			# Submitted and possibly used, so it cannot be cancelled or deleted through the controller.
			frappe.db.delete("Credit Adjustment Row", {"parent": name, "parenttype": "Student Credit Note"})
			frappe.db.delete("Student Credit Note", {"name": name})
		for dt, field in OTHER_SOURCES:
			for name in frappe.get_all(dt, filters={field: like}, pluck="name"):
				frappe.delete_doc(dt, name, force=True, ignore_permissions=True)
		for dt, field in sources:
			for name in frappe.get_all(dt, filters={field: like}, pluck="name"):
				receipt = frappe.db.get_value(dt, name, "receipt") if dt == "Fee Payment" else None
				frappe.delete_doc(dt, name, force=True, ignore_permissions=True)
				if receipt and frappe.db.exists("Fee Receipt", receipt):
					frappe.delete_doc("Fee Receipt", receipt, force=True, ignore_permissions=True)
		for name in frappe.get_all("Fee Demand", filters={"remarks": like}, pluck="name"):
			frappe.delete_doc("Fee Demand", name, force=True, ignore_permissions=True)
		for component in (TEST_COMPONENT, TEST_GST_COMPONENT):
			if frappe.db.exists("Fee Component", component):
				frappe.delete_doc("Fee Component", component, force=True, ignore_permissions=True)
		for name in names:
			for dt in sync.SOURCES:
				frappe.db.delete("Error Log", {"method": sync.ERROR_TITLE.format(dt, name)})
		frappe.db.commit()

	# ── helpers ──

	def demand(self, component=None, amount=10000):
		component = component or self.tuition
		return (
			frappe.get_doc(
				{
					"doctype": "Fee Demand",
					"student": self.student,
					"fee_component": component,
					"original_amount": amount,
					"demand_date": self.date,
					"due_date": add_days(self.date, 30),
					"remarks": TAG,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def pay(self, demand, amount, mode="Bank Transfer", ref=None, bank=None):
		doc = frappe.get_doc(
			{
				"doctype": "Fee Payment",
				"student": self.student,
				"amount": amount,
				"payment_date": self.date,
				"payment_mode": mode,
				"reference_number": ref,
				"university_bank_account": bank,
				"status": "Draft",
				"remarks": TAG,
				"payment_demands": [{"fee_demand": demand, "amount_allocated": amount}] if demand else [],
			}
		).insert(ignore_permissions=True)
		doc.submit()
		frappe.db.commit()
		return doc

	def set_company(self, **values):
		frappe.db.set_value("Company", self.company, values)
		frappe.clear_document_cache("Company", self.company)
		frappe.db.commit()

	def je_rows(self, je):
		return {r.account: r for r in frappe.get_all("Journal Entry Account", {"parent": je}, ["account", "debit", "credit"])}

	# ── posting ──

	def test_receipt_posts_once_and_cancel_reverses(self):
		fp = self.pay(self.demand(), 4000)
		self.assertEqual(sync.sync_document("Fee Payment", fp.name), "Posted")
		self.assertEqual(sync.sync_document("Fee Payment", fp.name), "Posted")  # idempotent
		self.assertEqual(frappe.db.count("Journal Entry", {"slcm_reference_name": fp.name, "docstatus": 1}), 1)
		je = frappe.get_doc("Journal Entry", sync.live_journal_entry("Fee Payment", fp.name))
		self.assertEqual(je.total_debit, 4000)
		self.assertEqual(je.slcm_student, self.student)
		self.assertEqual(self.je_rows(je.name)[conf.component_account(self.cfg, self.tuition)[0]].credit, 4000)

		fp.reload()
		fp.cancel()  # must not be blocked by the posted Journal Entry
		frappe.db.commit()
		self.assertEqual(sync.sync_document("Fee Payment", fp.name), "Cancelled")
		self.assertEqual(frappe.db.get_value("Journal Entry", je.name, "docstatus"), 2)

	def test_university_bank_is_matched_by_account_number(self):
		bank = frappe.db.get_value(
			"Bank Account",
			{"company": self.company, "is_company_account": 1, "bank_account_no": ("is", "set")},
			["bank_account_no", "account"],
			as_dict=True,
		)
		options = frappe.get_meta("Fee Payment").get_field("university_bank_account").options.split("\n")
		label = next((o for o in options if bank and bank.bank_account_no in o), None)
		if not label:
			self.skipTest("no company Bank Account matching an SLCM university bank")
		fp = self.pay(self.demand(), 1500, bank=label)
		sync.sync_document("Fee Payment", fp.name)
		self.assertEqual(self.je_rows(sync.live_journal_entry("Fee Payment", fp.name))[bank.account].debit, 1500)

	def test_component_without_matching_ledger_uses_default_income(self):
		frappe.get_doc(
			{
				"doctype": "Fee Component",
				"component_name": TEST_COMPONENT,
				"component_type": "Other",
				"demand_type": "Non Academic",
			}
		).insert(ignore_permissions=True)
		fp = self.pay(self.demand(TEST_COMPONENT, 700), 700)
		sync.sync_document("Fee Payment", fp.name)
		rows = self.je_rows(sync.live_journal_entry("Fee Payment", fp.name))
		self.assertEqual(rows[self.saved.slcm_default_fee_income_account].credit, 700)

		from slcm.erpnext_bridge.report.slcm_erpnext_reconciliation import slcm_erpnext_reconciliation as rec

		row = next(r for r in rec.execute({"student": self.student})[1] if r["reference_name"] == fp.name)
		self.assertIn("default fee income ledger", row["remark"])

	def test_refund_posts_and_cancel_reverses(self):
		demand = self.demand(amount=6000)
		self.pay(demand, 6000)
		refund = frappe.get_doc(
			{
				"doctype": "Fee Refund",
				"student": self.student,
				"refund_source": "Fee Demand",
				"fee_demand": demand,
				"refund_type": "Overpayment",
				"refund_amount": 1000,
				"refund_date": self.date,
				"refund_mode": "NEFT",
				"reason": TAG,
			}
		).insert(ignore_permissions=True)
		refund.submit()
		frappe.db.commit()
		self.assertEqual(sync.sync_document("Fee Refund", refund.name), "Posted")
		je = sync.live_journal_entry("Fee Refund", refund.name)
		self.assertEqual(self.je_rows(je)[self.saved.slcm_fee_refund_account].debit, 1000)

		refund.reload()
		refund.cancel()
		frappe.db.commit()
		self.assertEqual(sync.sync_document("Fee Refund", refund.name), "Cancelled")
		self.assertEqual(frappe.db.get_value("Journal Entry", je, "docstatus"), 2)

	def test_settlement_waits_for_receipt_then_posts(self):
		demand = self.demand(amount=10000)
		pr = frappe.get_doc(
			{
				"doctype": "SLCM Payment Request",
				"reference_doctype": "Fee Demand",
				"reference_name": demand,
				"amount": 10000,
				"currency": "INR",
				"razorpay_payment_id": PAY_ID,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"SLCM Payment Request",
			pr.name,
			{
				"settlement_status": "Settled",
				"settlement_date": f"{self.date} 09:00:00",
				"settlement_amount": 10000,
				"gateway_fees": 200,
				"gateway_tax": 36,
				"net_settled": 9764,
			},
		)
		frappe.db.commit()
		self.assertIsNone(sync.sync_document("SLCM Payment Request", pr.name))  # no receipt yet

		fp = self.pay(demand, 10000, mode="Online Payment", ref=PAY_ID)
		sync.sync_document("Fee Payment", fp.name)
		self.assertEqual(sync.sync_document("SLCM Payment Request", pr.name), "Posted")
		rows = self.je_rows(sync.live_journal_entry("SLCM Payment Request", pr.name))
		self.assertEqual(rows[conf.gateway_clearing_account(self.cfg)].credit, 10000)
		self.assertEqual(rows[self.saved.default_bank_account].debit, 9764)
		self.assertEqual(rows[self.saved.slcm_gateway_charges_account].debit, 200)

	def test_documents_before_start_date_are_not_posted(self):
		self.set_company(slcm_posting_from_date=add_days(self.date, 1))
		fp = self.pay(self.demand(), 1000)
		self.assertIsNone(sync.sync_document("Fee Payment", fp.name))
		self.assertIsNone(sync.live_journal_entry("Fee Payment", fp.name))

	def test_concession_posts_nothing(self):
		demand = self.demand(amount=8000)
		concession = frappe.get_doc(
			{
				"doctype": "Fee Concession",
				"student": self.student,
				"fee_demand": demand,
				"concession_type": "University Financial Aid",
				"waiver_value": 2000,
				"concession_date": self.date,
				"reason": TAG,
			}
		).insert(ignore_permissions=True)
		concession.submit()
		frappe.db.commit()
		self.assertIsNone(sync.sync_document("Fee Concession", concession.name))
		self.assertFalse(frappe.db.exists("Journal Entry", {"slcm_reference_name": concession.name}))

	# ── GST setting ──

	def gst_component(self):
		if not frappe.db.exists("Fee Component", TEST_GST_COMPONENT):
			frappe.get_doc(
				{
					"doctype": "Fee Component",
					"component_name": TEST_GST_COMPONENT,
					"component_type": "Other",
					"demand_type": "Non Academic",
					"is_taxable": 1,
					"tax_rate": 18,
				}
			).insert(ignore_permissions=True)
		return TEST_GST_COMPONENT

	def test_gst_is_carved_out_when_students_pay_gst(self):
		self.set_company(slcm_fees_include_gst=1)
		fp = self.pay(self.demand(self.gst_component(), 1180), 1180)
		sync.sync_document("Fee Payment", fp.name)
		rows = self.je_rows(sync.live_journal_entry("Fee Payment", fp.name))
		self.assertEqual(rows[self.saved.slcm_output_gst_account].credit, 180)
		self.assertEqual(rows[self.saved.slcm_default_fee_income_account].credit, 1000)

	def test_no_gst_when_students_do_not_pay_gst(self):
		self.set_company(slcm_fees_include_gst=0)
		fp = self.pay(self.demand(self.gst_component(), 1180), 1180)
		sync.sync_document("Fee Payment", fp.name)
		rows = self.je_rows(sync.live_journal_entry("Fee Payment", fp.name))
		self.assertNotIn(self.saved.slcm_output_gst_account, rows)
		self.assertEqual(rows[self.saved.slcm_default_fee_income_account].credit, 1180)

	# ── student excess ──

	def test_excess_moved_adjusted_and_refunded_through_unallocated(self):
		"""Paid fees moved to excess, part applied to another due, the rest refunded: the held money goes in and
		out of Unallocated Fee Receipts (a liability) and nets to zero; income follows the due it ends up on."""
		from slcm.slcm.page.student_fee_management import student_fee_management as sfm

		held = self.saved.slcm_unallocated_fee_account
		income = conf.component_account(self.cfg, self.tuition)[0]
		first = self.demand(amount=10000)
		self.pay(first, 10000)

		note = sfm.move_to_excess(self.student, first, 4000, "Overpayment", remarks=TAG)["credit_note"]
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("Student Credit Note", note, "source_fee_demand"), first)
		self.assertEqual(sync.sync_document("Student Credit Note", note), "Posted")
		rows = self.je_rows(sync.live_journal_entry("Student Credit Note", note))
		self.assertEqual((rows[income].debit, rows[held].credit), (4000, 4000))

		second = self.demand(amount=3000)
		sfm.apply_excess_credit(self.student, second, 3000, remarks=TAG)
		frappe.db.commit()
		row = frappe.db.get_value("Credit Adjustment Row", {"parent": note, "fee_demand": second}, "name")
		self.assertEqual(sync.sync_document("Credit Adjustment Row", row), "Posted")
		rows = self.je_rows(sync.live_journal_entry("Credit Adjustment Row", row))
		self.assertEqual((rows[held].debit, rows[income].credit), (3000, 3000))

		refund = sfm.refund_from_excess(self.student, 1000, "Cash", remarks=TAG)["fee_refund"]
		frappe.db.commit()
		self.assertEqual(sync.sync_document("Fee Refund", refund), "Posted")
		rows = self.je_rows(sync.live_journal_entry("Fee Refund", refund))
		self.assertEqual(rows[held].debit, 1000)
		self.assertNotIn(self.saved.slcm_fee_refund_account, rows)  # not an expense: the money was held

		# The refund's own audit row on the credit note (no due) posts nothing.
		refund_row = frappe.db.get_value("Credit Adjustment Row", {"parent": note, "fee_demand": ("is", "not set")}, "name")
		self.assertIsNone(sync.sync_document("Credit Adjustment Row", refund_row))

		jes = [sync.live_journal_entry(dt, dn) for dt, dn in (("Student Credit Note", note), ("Credit Adjustment Row", row), ("Fee Refund", refund))]
		balance = frappe.db.sql(
			"select sum(debit) - sum(credit) from `tabGL Entry` where account = %s and voucher_no in %s and is_cancelled = 0",
			(held, tuple(jes)),
		)[0][0]
		self.assertEqual(balance, 0)

	def test_credit_note_without_cash_posts_nothing(self):
		note = frappe.get_doc(
			{
				"doctype": "Student Credit Note",
				"student": self.student,
				"credit_type": "Scholarship Credit",
				"credit_amount": 2500,
				"remarks": f"Scholarship credit {TAG}",
			}
		).insert(ignore_permissions=True)
		note.submit()
		frappe.db.commit()
		self.assertIsNone(sync.sync_document("Student Credit Note", note.name))
		self.assertIsNone(sync.live_journal_entry("Student Credit Note", note.name))

	def test_sweeper_posts_missed_excess_entries(self):
		from slcm.slcm.page.student_fee_management import student_fee_management as sfm

		first = self.demand(amount=5000)
		self.pay(first, 5000)
		with patch.object(sync, "enqueue_sync"):  # as if the queue missed the events
			note = sfm.move_to_excess(self.student, first, 2000, "Overpayment", remarks=TAG)["credit_note"]
			sfm.apply_excess_credit(self.student, self.demand(amount=1500), 1500, remarks=TAG)
		frappe.db.commit()
		sync.sync_pending()
		row = frappe.db.get_value("Credit Adjustment Row", {"parent": note, "fee_demand": ("is", "set")}, "name")
		self.assertTrue(sync.live_journal_entry("Student Credit Note", note))
		self.assertTrue(sync.live_journal_entry("Credit Adjustment Row", row))

	def test_excess_received_by_hand_needs_how_it_came_in(self):
		note = frappe.get_doc(
			{
				"doctype": "Student Credit Note",
				"student": self.student,
				"credit_type": "Overpayment",
				"credit_amount": 5000,
				"remarks": f"Duplicate NEFT {TAG}",
			}
		)
		self.assertRaises(frappe.ValidationError, note.insert, ignore_permissions=True)

	def test_excess_received_by_hand_posts_to_bank_and_is_refundable(self):
		from slcm.slcm.page.student_fee_management import student_fee_management as sfm

		bank = frappe.db.get_value(
			"Bank Account", {"company": self.company, "is_company_account": 1, "bank_account_no": ("is", "set")},
			["bank_account_no", "account"], as_dict=True,
		)
		options = frappe.get_meta("Student Credit Note").get_field("received_bank_account").options.split("\n")
		label = next((o for o in options if bank and bank.bank_account_no in o), None)
		if not label:
			self.skipTest("no company Bank Account matching an SLCM university bank")
		note = frappe.get_doc(
			{
				"doctype": "Student Credit Note",
				"student": self.student,
				"credit_type": "Overpayment",
				"credit_amount": 5000,
				"received_via": "Bank Transfer",
				"received_bank_account": label,
				"received_date": self.date,
				"received_reference": "UTR-ERPTEST-1",
				"remarks": f"Duplicate NEFT {TAG}",
			}
		).insert(ignore_permissions=True)
		note.submit()
		frappe.db.commit()
		self.assertEqual(sync.sync_document("Student Credit Note", note.name), "Posted")
		je = frappe.get_doc("Journal Entry", sync.live_journal_entry("Student Credit Note", note.name))
		rows = self.je_rows(je.name)
		self.assertEqual((rows[bank.account].debit, rows[self.saved.slcm_unallocated_fee_account].credit), (5000, 5000))
		self.assertEqual(str(je.posting_date), self.date)

		refund = sfm.refund_from_excess(self.student, 5000, "Cash", remarks=TAG)["fee_refund"]
		frappe.db.commit()
		sync.sync_document("Fee Refund", refund)
		rows = self.je_rows(sync.live_journal_entry("Fee Refund", refund))
		self.assertEqual(rows[self.saved.slcm_unallocated_fee_account].debit, 5000)

	def test_money_received_completed_after_submit_posts(self):
		note = frappe.get_doc(
			{
				"doctype": "Student Credit Note",
				"student": self.student,
				"credit_type": "Other",
				"credit_amount": 800,
				"remarks": f"Completed later {TAG}",
			}
		).insert(ignore_permissions=True)
		note.submit()
		frappe.db.commit()
		self.assertIsNone(sync.sync_document("Student Credit Note", note.name))  # nothing says money came in

		note.reload()
		note.received_via = "Cash"
		note.received_date = self.date
		note.save(ignore_permissions=True)  # allowed after submit
		frappe.db.commit()
		self.assertEqual(sync.sync_document("Student Credit Note", note.name), "Posted")
		rows = self.je_rows(sync.live_journal_entry("Student Credit Note", note.name))
		self.assertEqual(rows[self.saved.default_cash_account].debit, 800)

	# ── admission, PACE, FLE, stipends, admission refunds ──

	def insert_raw(self, values):
		"""Insert a record the way its own flow would, without the PDF and link checks those flows do."""
		doc = frappe.get_doc(values)
		doc.flags.ignore_mandatory = True
		with (
			patch("slcm.admission.doctype.applicant_payment_receipt.applicant_payment_receipt.ApplicantPaymentReceipt.generate_and_attach_pdf"),
			patch("slcm.pace.doctype.pace_receipt.pace_receipt.PACEReceipt.generate_receipt_pdf"),
		):
			doc.insert(ignore_permissions=True, ignore_links=True)
		frappe.db.commit()
		return doc

	def applicant_receipt(self, mode="Bank Transfer", payment_request=None, net=9000):
		return self.insert_raw(
			{
				"doctype": "Applicant Payment Receipt",
				"applicant": "ERP-TEST-APPLICANT",
				"fee_type": "Admission Fee",
				"payment_date": self.date,
				"payment_mode": mode,
				"payment_reference": payment_request,
				"transaction_id": "UTR-ERPTEST-APR",
				"total_amount": 10000,
				"scholarship_amount": 10000 - net,
				"net_amount": net,
				"remarks": TAG,
				"fee_components": [
					{"fee_component": self.tuition, "component_name": self.tuition, "amount": 7000},
					{"fee_component": TEST_COMPONENT, "component_name": TEST_COMPONENT, "amount": 3000},
				],
			}
		)

	def test_admission_receipt_posts_per_component_net_of_scholarship(self):
		frappe.get_doc(
			{"doctype": "Fee Component", "component_name": TEST_COMPONENT, "component_type": "Other", "demand_type": "Non Academic"}
		).insert(ignore_permissions=True)
		apr = self.applicant_receipt(net=9000)
		self.assertEqual(sync.sync_document("Applicant Payment Receipt", apr.name), "Posted")
		rows = self.je_rows(sync.live_journal_entry("Applicant Payment Receipt", apr.name))
		self.assertEqual(rows[conf.receipt_cash_account(self.cfg, "Bank Transfer")].debit, 9000)
		self.assertEqual(rows[conf.component_account(self.cfg, self.tuition)[0]].credit, 6300)
		self.assertEqual(rows[self.saved.slcm_default_fee_income_account].credit, 2700)

		frappe.delete_doc("Applicant Payment Receipt", apr.name, force=True, ignore_permissions=True)
		frappe.db.commit()
		self.deleted_sources.append(apr.name)
		self.assertEqual(sync.sync_document("Applicant Payment Receipt", apr.name), "Cancelled")

	def test_admission_online_payment_settles_through_its_payment_request(self):
		demand = self.demand(amount=9000)
		pr = frappe.get_doc(
			{
				"doctype": "SLCM Payment Request",
				"reference_doctype": "Fee Demand",
				"reference_name": demand,
				"amount": 9000,
				"currency": "INR",
				"razorpay_payment_id": PAY_ID,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"SLCM Payment Request",
			pr.name,
			{"settlement_status": "Settled", "settlement_date": f"{self.date} 09:00:00", "settlement_amount": 9000,
			 "gateway_fees": 180, "gateway_tax": 32.4, "net_settled": 8787.6},
		)
		frappe.db.commit()
		apr = self.applicant_receipt(mode="Online", payment_request=pr.name)
		status = sync.sync_document("Applicant Payment Receipt", apr.name)
		self.assertEqual(status, "Posted", sync.last_error("Applicant Payment Receipt", apr.name))
		clearing = conf.gateway_clearing_account(self.cfg)
		self.assertEqual(self.je_rows(sync.live_journal_entry("Applicant Payment Receipt", apr.name))[clearing].debit, 9000)
		self.assertEqual(sync.sync_document("SLCM Payment Request", pr.name), "Posted")
		rows = self.je_rows(sync.live_journal_entry("SLCM Payment Request", pr.name))
		self.assertEqual(rows[clearing].credit, 9000)
		self.assertEqual(rows[self.saved.default_bank_account].debit, 8787.6)

	def test_pace_receipt_posts_and_foreign_currency_is_flagged(self):
		inr = self.insert_raw(
			{"doctype": "PACE Receipt", "pace_application": "ERP-TEST-PACE", "fee_type": "Course Fee", "amount": 15000,
			 "currency": "INR", "transaction_id": "pay_ERPTEST_PACE", "payment_date": self.date, "applicant_name": TAG}
		)
		self.assertEqual(sync.sync_document("PACE Receipt", inr.name), "Posted")
		income = conf.account_named(self.cfg, "PACE Course Fee") or self.saved.slcm_default_fee_income_account
		rows = self.je_rows(sync.live_journal_entry("PACE Receipt", inr.name))
		self.assertEqual((rows[conf.gateway_clearing_account(self.cfg)].debit, rows[income].credit), (15000, 15000))

		usd = self.insert_raw(
			{"doctype": "PACE Receipt", "pace_application": "ERP-TEST-PACE", "fee_type": "Course Fee", "amount": 200,
			 "currency": "USD", "transaction_id": "pay_ERPTEST_PACE2", "payment_date": self.date, "applicant_name": TAG}
		)
		self.assertEqual(sync.sync_document("PACE Receipt", usd.name), "Failed")
		self.assertIn("USD", sync.last_error("PACE Receipt", usd.name))

	def test_fle_payment_posts_once_and_settles(self):
		fle = frappe.get_all("Foundations for a Legal Education", pluck="name", limit=1)
		reference = fle[0] if fle else "ERP-TEST-FLE"

		def log(status):
			return self.insert_raw(
				{"doctype": "FLE Payment Log", "reference_no": reference, "full_name": TAG, "payment_status": status,
				 "paid_amount": 4000, "transaction_id": "pay_ERPTEST_FLE", "transaction_date": f"{self.date} 10:00:00"}
			)

		first, second = log("Authorized"), log("Captured")  # two callbacks for one payment
		self.assertEqual(sync.sync_document("FLE Payment Log", first.name), "Posted")
		self.assertIsNone(sync.sync_document("FLE Payment Log", second.name))

		# Razorpay's settlement webhook may write onto either log of the payment.
		frappe.db.set_value(
			"FLE Payment Log", second.name,
			{"settlement_status": "processed", "settlement_date": self.date, "gateway_fees": 80, "gateway_tax": 14.4, "net_settled": 3905.6},
		)
		frappe.db.commit()
		self.assertEqual(sync.sync_document("FLE Settlement", second.name), "Posted")
		rows = self.je_rows(sync.live_journal_entry("FLE Settlement", second.name))
		self.assertEqual(rows[conf.gateway_clearing_account(self.cfg)].credit, 4000)

	def test_stipend_posts_and_cancel_reverses(self):
		stipend_type = next(
			o for o in frappe.get_meta("Stipend Payment").get_field("stipend_type").options.split("\n") if o
		)
		sp = frappe.get_doc(
			{"doctype": "Stipend Payment", "student": self.student, "stipend_type": stipend_type,
			 "payment_date": self.date, "payment_mode": "Bank Transfer", "amount": 3500, "remarks": TAG}
		).insert(ignore_permissions=True)
		sp.submit()
		frappe.db.commit()
		self.assertEqual(sync.sync_document("Stipend Payment", sp.name), "Posted")
		rows = self.je_rows(sync.live_journal_entry("Stipend Payment", sp.name))
		self.assertEqual(rows[self.saved.slcm_stipend_account].debit, 3500)
		self.assertEqual(rows[conf.payment_out_account(self.cfg, "Bank Transfer")].credit, 3500)
		sp.reload()
		sp.cancel()
		frappe.db.commit()
		self.assertEqual(sync.sync_document("Stipend Payment", sp.name), "Cancelled")

	def test_admission_refund_posts_only_when_processed(self):
		rt = self.insert_raw(
			{"doctype": "Refund Transaction", "razorpay_payment_id": "pay_ERPTEST_RT", "status": "Initiated",
			 "refund_amount": 2500, "processed_at": f"{self.date} 12:00:00", "failure_reason": TAG}
		)
		self.assertIsNone(sync.sync_document("Refund Transaction", rt.name))
		frappe.db.set_value("Refund Transaction", rt.name, "status", "Processed")
		frappe.db.commit()
		self.assertEqual(sync.sync_document("Refund Transaction", rt.name), "Posted")
		rows = self.je_rows(sync.live_journal_entry("Refund Transaction", rt.name))
		self.assertEqual(rows[self.saved.slcm_fee_refund_account].debit, 2500)
		self.assertEqual(rows[conf.gateway_clearing_account(self.cfg)].credit, 2500)

	def test_reconciliation_report_lists_every_source(self):
		from slcm.erpnext_bridge.report.slcm_erpnext_reconciliation import slcm_erpnext_reconciliation as rec

		self.pay(self.demand(), 1000)
		sync.sync_pending()
		_columns, data, *_ = rec.execute({})
		self.assertTrue(data)
		self.assertFalse([r for r in data if r["exception"] and TAG in str(r)])

	def test_unallocated_account_must_be_a_liability(self):
		doc = frappe.get_doc("Company", self.company)
		doc.slcm_unallocated_fee_account = self.saved.slcm_default_fee_income_account
		self.assertRaises(frappe.ValidationError, validate_company, doc)

	# ── isolation ──

	def test_erpnext_failure_never_blocks_fee_payment(self):
		self.set_company(slcm_unallocated_fee_account=None)  # misconfiguration on the ERPNext side
		fp = self.pay(None, 1500)  # advance, needs the unallocated ledger
		self.assertEqual(fp.docstatus, 1)  # SLCM flow completed normally
		self.assertEqual(frappe.db.get_value("Fee Payment", fp.name, "status"), "Submitted")

		self.assertEqual(sync.sync_document("Fee Payment", fp.name), "Failed")
		self.assertIn("Unallocated", sync.last_error("Fee Payment", fp.name))
		sync.sync_document("Fee Payment", fp.name)
		self.assertEqual(frappe.db.count("Error Log", {"method": sync.ERROR_TITLE.format("Fee Payment", fp.name)}), 1)

		self.set_company(slcm_unallocated_fee_account=self.saved.slcm_unallocated_fee_account)
		sync.sync_pending()
		self.assertTrue(sync.live_journal_entry("Fee Payment", fp.name))

	def test_disabled_bridge_does_nothing(self):
		self.set_company(slcm_enable_fee_posting=0)
		fp = self.pay(self.demand(), 1000)
		self.assertFalse(sync.is_enabled())
		self.assertIsNone(sync.sync_document("Fee Payment", fp.name))
		self.assertIsNone(sync.sync_pending())
		self.assertIsNone(sync.live_journal_entry("Fee Payment", fp.name))

	def test_hook_is_silent_when_queue_is_unavailable(self):
		fp = self.pay(self.demand(), 1000)
		original = frappe.enqueue

		def broken(*args, **kwargs):
			raise ConnectionError("redis down")

		frappe.enqueue = broken
		try:
			sync.enqueue_sync(fp)
			frappe.db.commit()  # runs after-commit callbacks; must not raise
		finally:
			frappe.enqueue = original

	def test_no_erpnext_everything_is_inert(self):
		fp = self.pay(self.demand(), 1000)
		# Patch the bridge's single guard where it is used (patching frappe.get_installed_apps itself would break
		# ERPNext's own hooks that are still loaded in this process).
		with (
			patch("slcm.erpnext_bridge.config.erpnext_installed", return_value=False),
			patch("slcm.erpnext_bridge.install.erpnext_installed", return_value=False),
			patch.object(install, "setup_erpnext_side") as setup,
		):
			self.assertFalse(sync.is_enabled())
			queued = len(frappe.db.after_commit._functions)
			sync.enqueue_sync(fp)
			self.assertEqual(len(frappe.db.after_commit._functions), queued)  # nothing queued
			self.assertIsNone(sync.sync_document("Fee Payment", fp.name))
			self.assertIsNone(sync.sync_pending())
			install.after_migrate()
			install.after_app_install("slcm")
			setup.assert_not_called()
		self.assertIsNone(sync.live_journal_entry("Fee Payment", fp.name))

	def test_erpnext_installed_guard(self):
		from slcm.erpnext_bridge import erpnext_installed

		self.assertTrue(erpnext_installed())
		with patch("frappe.get_installed_apps", return_value=["frappe", "slcm"]):
			self.assertFalse(erpnext_installed())
		with patch("frappe.get_installed_apps", side_effect=Exception("no db")):
			self.assertFalse(erpnext_installed())

	def test_journal_entry_reference_fields_are_not_links(self):
		meta = frappe.get_meta("Journal Entry")
		for fieldname in ("slcm_reference_doctype", "slcm_reference_name", "slcm_student", "slcm_programme"):
			self.assertEqual(meta.get_field(fieldname).fieldtype, "Data", fieldname)

	def test_journal_entry_cancelled_in_erpnext_is_not_auto_reposted(self):
		fp = self.pay(self.demand(), 2000)
		sync.sync_document("Fee Payment", fp.name)
		first = sync.live_journal_entry("Fee Payment", fp.name)
		frappe.get_doc("Journal Entry", first).cancel()
		frappe.db.commit()
		self.assertEqual(sync.sync_document("Fee Payment", fp.name), "Cancelled in ERPNext")
		sync.sync_pending()
		self.assertIsNone(sync.live_journal_entry("Fee Payment", fp.name))
		self.assertEqual(sync.sync_document("Fee Payment", fp.name, repost=True), "Posted")
		self.assertNotEqual(sync.live_journal_entry("Fee Payment", fp.name), first)

	# ── company settings ──

	def test_company_rejects_party_foreign_accounts_and_second_company(self):
		receivable = frappe.db.get_value(
			"Account", {"company": self.company, "account_type": "Receivable", "is_group": 0}, "name"
		)
		foreign = frappe.db.get_value("Account", {"company": ("!=", self.company), "is_group": 0}, "name")
		for account in filter(None, (receivable, foreign)):
			doc = frappe.get_doc("Company", self.company)
			doc.slcm_fee_refund_account = account
			self.assertRaises(frappe.ValidationError, validate_company, doc)

		other = frappe.db.get_value("Company", {"name": ("!=", self.company)}, "name")
		if other:
			doc = frappe.get_doc("Company", other)
			doc.slcm_enable_fee_posting = 1
			doc.slcm_posting_from_date = self.date
			self.assertRaises(frappe.ValidationError, validate_company, doc)

	def test_fee_ledger_setup_is_idempotent(self):
		from slcm.erpnext_bridge.setup_accounts import setup_fee_accounting

		def counts():
			return (
				frappe.db.count("Account", {"company": self.company}),
				frappe.db.count("Mode of Payment Account", {"company": self.company}),
				frappe.db.count("Bank Account", {"company": self.company}),
			)

		before = counts()
		setup_fee_accounting(self.company)
		setup_fee_accounting(self.company)
		self.assertEqual(counts(), before)
		self.assertEqual(frappe.db.get_value("Company", self.company, list(SAVED_FIELDS), as_dict=True), self.saved)
