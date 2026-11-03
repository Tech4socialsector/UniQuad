import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class RevaluationRequest(Document):
	"""Retired: revaluation is a Grade Appeal of type Re-evaluation, which
	raises the Revaluation Fee itself. Kept so old records still open."""

	def validate(self):
		if self.is_new():
			frappe.throw(_("Revaluation Request is replaced by Grade Appeal. Create a Grade Appeal with Appeal Type Re-evaluation."))
		self.total_fee = flt(self.number_of_papers) * flt(self.fee_per_paper)

	def on_submit(self):
		from slcm.slcm.fee.event_hooks import on_revaluation_request_submit
		on_revaluation_request_submit(self)

	def on_cancel(self):
		from slcm.slcm.fee.event_hooks import on_revaluation_request_cancel
		on_revaluation_request_cancel(self)
