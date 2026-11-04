import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import now_datetime


class FeeNotification(Document):

	def validate(self):
		self._validate_dates()
		self._validate_duplicate_components()

	def _validate_dates(self):
		if self.issued_date and self.effective_from:
			if self.effective_from < self.issued_date:
				frappe.throw(_("Effective From cannot be earlier than Issued Date."))

	def _validate_duplicate_components(self):
		seen = set()
		for row in self.components:
			key = (
				row.fee_component, row.program or "", row.batch or "", row.year_no or "",
				row.program_level or "All", row.student_category or "All",
			)
			if key in seen:
				frappe.throw(
					_("Row {0}: Duplicate entry for Fee Component <b>{1}</b> with the same Programme, "
					  "Batch, Year No, Program Level and Student Category. Each combination must be unique.").format(
						row.idx, row.fee_component
					)
				)
			seen.add(key)

	@frappe.whitelist()
	def publish(self):
		"""Publish the notification — makes it ready for demand generation."""
		self.check_permission("write")
		if self.status == "Published":
			frappe.throw(_("This Fee Notification is already published."))

		if not self.components:
			frappe.throw(_("Please add at least one fee component before publishing."))

		self.status = "Published"
		self.save()
		frappe.msgprint(
			_("Fee Notification <b>{0}</b> published successfully. "
			  "You can now generate fee demands.").format(self.name),
			alert=True,
			indicator="green",
		)

	@frappe.whitelist()
	def generate_demands(self):
		"""Enqueue the annual demand generation as a background job."""
		self.check_permission("write")
		if self.status != "Published":
			frappe.throw(_("Please publish this Fee Notification before generating demands."))

		frappe.enqueue(
			"slcm.slcm.fee.fee_demand_utils.generate_annual_demands",
			fee_notification_name=self.name,
			queue="long",
			timeout=3600,
			job_id=f"generate_demands_{self.name}",
		)

		frappe.msgprint(
			_("Demand generation has been queued as a background job. "
			  "You will be notified once it completes."),
			alert=True,
			indicator="blue",
		)

	def update_generation_log(self, log_name):
		"""Called by the generator after completion to update the log link."""
		self.db_set("last_generated_on", now_datetime())
		self.db_set("last_generated_by", frappe.session.user)
		self.db_set("generation_log", log_name)
