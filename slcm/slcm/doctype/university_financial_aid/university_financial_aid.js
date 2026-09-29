// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

const AID_COMPONENTS = [
	"tuition_facilities",
	"hostel_mess",
	"lunch_dinner_charges",
	"stipend",
	"laptop",
	"loan",
];

function calculate_total(frm) {
	const total = AID_COMPONENTS.reduce((sum, f) => sum + flt(frm.doc[f]), 0);
	frm.set_value("total_financial_aid", total);
}

frappe.ui.form.on("University Financial Aid", {
	...Object.fromEntries(AID_COMPONENTS.map((f) => [f, calculate_total])),
});
