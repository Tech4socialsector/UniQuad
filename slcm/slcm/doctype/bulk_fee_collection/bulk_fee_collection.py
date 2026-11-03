import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class BulkFeeCollection(Document):

	def validate(self):
		if not self.students:
			return
		for row in self.students:
			if flt(row.amount_to_collect) <= 0:
				frappe.throw(
					f"Row {row.idx} ({row.student}): Amount to Collect must be greater than zero."
				)

	@frappe.whitelist()
	def fetch_students(self):
		"""Fetch all students with pending dues matching the filters."""
		# Step 1: get all pending demands for the academic year
		demand_filters = {"status": ["in", ["Pending", "Partially Paid", "Overdue"]]}
		if self.academic_year:
			demand_filters["academic_year"] = self.academic_year

		demands = frappe.get_all(
			"Fee Demand",
			filters=demand_filters,
			fields=["student", "outstanding_amount"],
		)

		if not demands:
			self.students = []
			self.total_students = 0
			return 0

		# Step 2: aggregate outstanding per student
		student_totals = {}
		for d in demands:
			student_totals.setdefault(d.student, 0)
			student_totals[d.student] += flt(d.outstanding_amount)

		# Step 3: optionally narrow by batch_year / programme from student master
		# (Student Master has no batch_year field, so a Batch Year selection can't narrow here.)
		student_filters = {"student_status": "Active", "name": ["in", list(student_totals.keys())]}
		if self.programme:
			student_filters["programme_of_study"] = ["like", f"%{self.programme}%"]

		students = frappe.get_all(
			"Student Master",
			filters=student_filters,
			fields=["name", "programme_of_study"],
		)

		# Step 4: build child table rows
		self.students = []
		for s in students:
			outstanding = student_totals.get(s.name, 0)
			if outstanding <= 0:
				continue
			self.append("students", {
				"student": s.name,
				"total_outstanding": outstanding,
				"amount_to_collect": outstanding,
				"status": "Pending",
			})

		self.total_students = len(self.students)
		return len(self.students)

	@frappe.whitelist()
	def process_bulk_payment(self):
		"""Create one Fee Payment + Receipt per student row. Runs synchronously."""
		if not self.students:
			frappe.throw("No students to process. Please fetch students first.")

		self.db_set("status", "Processing", update_modified=False)
		frappe.db.commit()

		processed = skipped = failed = 0
		total_collected = 0.0

		for row in self.students:
			if row.status == "Processed":
				skipped += 1
				continue
			if flt(row.amount_to_collect) <= 0:
				frappe.db.set_value(
					"Bulk Fee Collection Student", row.name,
					{"status": "Skipped", "remarks": "Amount to collect is zero"},
				)
				skipped += 1
				continue

			try:
				# Get pending demands for this student
				demands = frappe.get_all(
					"Fee Demand",
					filters={
						"student": row.student,
						"academic_year": self.academic_year,
						"status": ["in", ["Pending", "Partially Paid", "Overdue"]],
					},
					fields=["name", "description", "fee_component", "outstanding_amount"],
					order_by="due_date asc",
				)

				if not demands:
					frappe.db.set_value(
						"Bulk Fee Collection Student", row.name,
						{"status": "Skipped", "remarks": "No pending demands found"},
					)
					skipped += 1
					continue

				# Build demand allocation — allocate up to amount_to_collect
				remaining = flt(row.amount_to_collect)
				demand_rows = []
				for d in demands:
					if remaining <= 0:
						break
					alloc = min(flt(d.outstanding_amount), remaining)
					if alloc > 0:
						demand_rows.append({
							"fee_demand": d.name,
							"demand_description": d.description or d.fee_component,
							"outstanding_amount": d.outstanding_amount,
							"amount_allocated": alloc,
						})
						remaining -= alloc

				student_doc = frappe.db.get_value(
					"Student Master", row.student,
					["first_name", "programme_of_study", "academic_year"],
					as_dict=True,
				) or {}

				payment = frappe.get_doc({
					"doctype": "Fee Payment",
					"student": row.student,
					"payment_date": self.payment_date or today(),
					"payment_mode": self.payment_mode,
					"bank_account": self.bank_account,
					"reference_number": self.reference_number,
					"amount": flt(row.amount_to_collect),
					"status": "Draft",
					"payment_demands": demand_rows,
				})
				payment.insert(ignore_permissions=True)
				payment.submit()

				frappe.db.set_value(
					"Bulk Fee Collection Student", row.name,
					{
						"status": "Processed",
						"fee_payment": payment.name,
						"remarks": f"Receipt: {payment.receipt}" if payment.receipt else payment.name,
					},
				)
				processed += 1
				total_collected += flt(row.amount_to_collect)

			except Exception as e:
				frappe.db.set_value(
					"Bulk Fee Collection Student", row.name,
					{"status": "Failed", "remarks": str(e)[:200]},
				)
				failed += 1
				frappe.log_error(frappe.get_traceback(), f"BulkFeeCollection: failed for {row.student}")

		final_status = "Completed" if failed == 0 else "Completed with Errors"
		self.db_set("status", final_status, update_modified=False)
		self.db_set("processed_count", processed, update_modified=False)
		self.db_set("failed_count", failed, update_modified=False)
		self.db_set("skipped_count", skipped, update_modified=False)
		self.db_set("total_amount_collected", total_collected, update_modified=False)
		frappe.db.commit()

		return {
			"processed": processed,
			"failed": failed,
			"skipped": skipped,
			"total_collected": total_collected,
			"status": final_status,
		}
