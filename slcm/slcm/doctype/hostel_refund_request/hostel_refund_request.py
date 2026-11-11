# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class HostelRefundRequest(Document):
	def validate(self):
		# Processed = the money was paid out; the ERPNext bridge books it on this date from this mode.
		if self.status == "Processed":
			if not self.refund_mode:
				frappe.throw(_("Set the Refund Mode before marking the request Processed."))
			self.processed_on = self.processed_on or today()
