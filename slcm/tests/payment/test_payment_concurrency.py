# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from unittest.mock import patch
from slcm.tests.payment.payment_test_base import PaymentTestBase
from slcm.api.service.fee_service import FeeService
from slcm.api.razorpay_webhook import handle_razorpay_webhook
import json
import concurrent.futures

class TestPaymentConcurrency(PaymentTestBase):
	def setUp(self):
		super().setUp()
		self._site = frappe.local.site
		# For concurrency tests, we commit the test data to DB so other thread connections can see them.
		self.app = self.create_applicant(amount=1000)
		self.pr = self.create_payment_request("Applicant", self.app.name, "order_af_conc", amount=1000)
		frappe.db.commit()

	def _connect_worker_site(self):
		frappe.init(site=self._site)
		frappe.connect()
		frappe.set_user("Administrator")

	def test_verify_webhook_race(self):
		"""TEST 2: Verify + Webhook Race"""
		self.mock_razorpay(payment_data={
			"id": "pay_af_conc",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_af_conc",
			"status": "captured"
		})
		self.mock_signature_verification()

		def run_verify():
			self._connect_worker_site()
			try:
				res = FeeService.verify_application_fee_payment(
					razorpay_payment_id="pay_af_conc",
					razorpay_order_id="order_af_conc",
					razorpay_signature="sig",
					applicant_name=self.app.name
				)
				frappe.db.commit()
				return ("verify", res)
			except Exception as e:
				frappe.db.rollback()
				return ("verify", e)
			finally:
				frappe.destroy()

		def run_webhook():
			self._connect_worker_site()
			try:
				payload = {
					"event": "payment.captured",
					"payload": {
						"payment": {
							"entity": {
								"id": "pay_af_conc",
								"amount": 100000,
								"currency": "INR",
								"order_id": "order_af_conc",
								"status": "captured"
							}
						}
					}
				}
				self.bind_webhook_request(payload)
				with patch("frappe.get_request_header", side_effect=self.sign_webhook_request):
					res = handle_razorpay_webhook()
				frappe.db.commit()
				return ("webhook", res)
			except Exception as e:
				frappe.db.rollback()
				return ("webhook", e)
			finally:
				frappe.destroy()

		# Run them simultaneously
		with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
			futures = [executor.submit(run_verify), executor.submit(run_webhook)]
			results = [f.result() for f in futures]

		# Verify results: no exceptions raised
		for name, res in results:
			if isinstance(res, Exception):
				self.fail(f"Concurrency thread '{name}' raised exception: {res}")

		# Assert database integrity
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": self.app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 1)

	def test_verify_scheduler_race(self):
		"""TEST 3: Verify + Scheduler Race"""
		# Modify Payment Request modified date to trigger cutoff
		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, self.pr.name))
		frappe.db.commit()

		self.mock_razorpay(
			payment_data={
				"id": "pay_af_conc",
				"amount": 100000,
				"currency": "INR",
				"order_id": "order_af_conc",
				"status": "captured"
			},
			payments_list=[{
				"id": "pay_af_conc",
				"amount": 100000,
				"currency": "INR",
				"order_id": "order_af_conc",
				"status": "captured"
			}]
		)
		self.mock_signature_verification()

		def run_verify():
			self._connect_worker_site()
			try:
				res = FeeService.verify_application_fee_payment(
					razorpay_payment_id="pay_af_conc",
					razorpay_order_id="order_af_conc",
					razorpay_signature="sig",
					applicant_name=self.app.name
				)
				frappe.db.commit()
				return ("verify", res)
			except Exception as e:
				frappe.db.rollback()
				return ("verify", e)
			finally:
				frappe.destroy()

		def run_scheduler():
			self._connect_worker_site()
			try:
				FeeService.reconcile_pending_payments()
				frappe.db.commit()
				return ("scheduler", "success")
			except Exception as e:
				frappe.db.rollback()
				return ("scheduler", e)
			finally:
				frappe.destroy()

		with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
			futures = [executor.submit(run_verify), executor.submit(run_scheduler)]
			results = [f.result() for f in futures]

		for name, res in results:
			if isinstance(res, Exception):
				self.fail(f"Concurrency thread '{name}' raised exception: {res}")

		# Assert database integrity
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": self.app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 1)

	def test_triple_race(self):
		"""TEST 4: Triple Concurrency Race (Verify + Webhook + Scheduler)"""
		from frappe.utils import add_to_date
		old_time = add_to_date(frappe.utils.now_datetime(), minutes=-20)
		frappe.db.sql("UPDATE `tabSLCM Payment Request` SET modified = %s WHERE name = %s", (old_time, self.pr.name))
		frappe.db.commit()

		self.mock_razorpay(
			payment_data={
				"id": "pay_af_conc",
				"amount": 100000,
				"currency": "INR",
				"order_id": "order_af_conc",
				"status": "captured"
			},
			payments_list=[{
				"id": "pay_af_conc",
				"amount": 100000,
				"currency": "INR",
				"order_id": "order_af_conc",
				"status": "captured"
			}]
		)
		self.mock_signature_verification()

		def run_verify():
			self._connect_worker_site()
			try:
				res = FeeService.verify_application_fee_payment(
					razorpay_payment_id="pay_af_conc",
					razorpay_order_id="order_af_conc",
					razorpay_signature="sig",
					applicant_name=self.app.name
				)
				frappe.db.commit()
				return ("verify", res)
			except Exception as e:
				frappe.db.rollback()
				return ("verify", e)
			finally:
				frappe.destroy()

		def run_webhook():
			self._connect_worker_site()
			try:
				payload = {
					"event": "payment.captured",
					"payload": {
						"payment": {
							"entity": {
								"id": "pay_af_conc",
								"amount": 100000,
								"currency": "INR",
								"order_id": "order_af_conc",
								"status": "captured"
							}
						}
					}
				}
				self.bind_webhook_request(payload)
				with patch("frappe.get_request_header", side_effect=self.sign_webhook_request):
					res = handle_razorpay_webhook()
				frappe.db.commit()
				return ("webhook", res)
			except Exception as e:
				frappe.db.rollback()
				return ("webhook", e)
			finally:
				frappe.destroy()

		def run_scheduler():
			self._connect_worker_site()
			try:
				FeeService.reconcile_pending_payments()
				frappe.db.commit()
				return ("scheduler", "success")
			except Exception as e:
				frappe.db.rollback()
				return ("scheduler", e)
			finally:
				frappe.destroy()

		with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
			futures = [
				executor.submit(run_verify),
				executor.submit(run_webhook),
				executor.submit(run_scheduler)
			]
			results = [f.result() for f in futures]

		for name, res in results:
			if isinstance(res, Exception):
				self.fail(f"Concurrency thread '{name}' raised exception: {res}")

		# Assert database integrity
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": self.app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 1)

	def test_20_parallel_verifications(self):
		"""20 Parallel Verifications simultaneously using ThreadPoolExecutor"""
		self.mock_razorpay(payment_data={
			"id": "pay_af_conc",
			"amount": 100000,
			"currency": "INR",
			"order_id": "order_af_conc",
			"status": "captured"
		})
		self.mock_signature_verification()

		def worker():
			self._connect_worker_site()
			try:
				res = FeeService.verify_application_fee_payment(
					razorpay_payment_id="pay_af_conc",
					razorpay_order_id="order_af_conc",
					razorpay_signature="sig",
					applicant_name=self.app.name
				)
				frappe.db.commit()
				return ("worker", res)
			except Exception as e:
				frappe.db.rollback()
				return ("worker", e)
			finally:
				frappe.destroy()

		# Run 20 threads simultaneously
		with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
			futures = [executor.submit(worker) for _ in range(20)]
			results = [f.result() for f in futures]

		# Verify no errors/exceptions occurred
		for name, res in results:
			if isinstance(res, Exception):
				self.fail(f"Parallel verification worker raised exception: {res}")

		# Verify exactly one receipt is generated
		receipts = frappe.get_all("Applicant Payment Receipt", filters={"applicant": self.app.name, "docstatus": ["<", 2]})
		self.assertEqual(len(receipts), 1)
