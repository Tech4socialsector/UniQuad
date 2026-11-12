# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from slcm.slcm.utils.rfid_cards import set_student_uid, sync_student_master


class StudentRFIDCard(Document):
	# History of a student's cards; the Active one is mirrored to Student Master.rfid_uid
	# (see slcm/slcm/utils/rfid_cards.py).

	def validate(self):
		self.rfid_uid = (self.rfid_uid or "").strip()
		if not self.rfid_uid:
			frappe.throw(_("RFID UID is required."))
		self.card_status = self.card_status or "Active"
		self.is_active = 1 if self.card_status == "Active" else 0
		self.issued_date = self.issued_date or today()

		if self.is_active:
			self.deactivated_date = None
			holder = frappe.db.get_value(
				"Student Master", {"rfid_uid": self.rfid_uid, "name": ["!=", self.student]}, "name"
			)
			if holder:
				frappe.throw(
					_("RFID UID <b>{0}</b> is already assigned to student <b>{1}</b>.").format(self.rfid_uid, holder)
				)
		else:
			self.deactivated_date = self.deactivated_date or today()

	def on_update(self):
		if not self.flags.skip_rfid_sync:
			sync_student_master(self)

	def on_trash(self):
		if self.card_status == "Active" and frappe.db.get_value("Student Master", self.student, "rfid_uid") == self.rfid_uid:
			set_student_uid(self.student, None, _("Student RFID Card deleted"))
