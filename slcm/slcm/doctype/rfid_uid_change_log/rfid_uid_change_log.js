// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

// One log per student; rows are written only by slcm.slcm.utils.rfid_cards.log_uid_change.
frappe.ui.form.on("RFID UID Change Log", {
	refresh(frm) {
		frm.disable_save();
	},
});
