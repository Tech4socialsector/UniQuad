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

	def setUp(self):
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
		for dt, field in sources:
			for name in frappe.get_all(dt, filters={field: like}, pluck="name"):
				receipt = frappe.db.get_value(dt, name, "receipt") if dt == "Fee Payment" else None
				frappe.delete_doc(dt, name, force=True, ignore_permissions=True)
				if receipt and frappe.db.exists("Fee Receipt", receipt):
					frappe.delete_doc("Fee Receipt", receipt, force=True, ignore_permissions=True)
		for name in frappe.get_all("Fee Demand", filters={"remarks": like}, pluck="name"):
			frappe.delete_doc("Fee Demand", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Fee Component", TEST_COMPONENT):
			frappe.delete_doc("Fee Component", TEST_COMPONENT, force=True, ignore_permissions=True)
		for name in names:
			for dt in ("Fee Payment", "Fee Refund", "SLCM Payment Request"):
				frappe.db.delete("Error Log", {"method": sync.ERROR_TITLE.format(dt, name)})
		frappe.db.commit()

	# ── helpers ──

	def demand(self, component="Tuition Fee", amount=10000):
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
		self.assertEqual(self.je_rows(je.name)[conf.component_account(self.cfg, "Tuition Fee")[0]].credit, 4000)

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
