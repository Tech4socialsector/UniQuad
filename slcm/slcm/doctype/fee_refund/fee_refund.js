frappe.ui.form.on("Fee Refund", {
	refresh(frm) {
		_show_available_excess(frm);
	},

	refund_source(frm) {
		if (frm.doc.refund_source === "Excess Amount") {
			frm.set_value("fee_demand", "");
			if (!frm.doc.refund_type) frm.set_value("refund_type", "Excess Refund");
		}
		_show_available_excess(frm);
	},

	student(frm) {
		frm.set_value("fee_demand", "");
		_show_available_excess(frm);
		if (frm.doc.student) {
			frm.set_query("fee_demand", () => ({
				filters: {
					student: frm.doc.student,
					status: ["in", ["Pending", "Partially Paid", "Overdue", "Paid"]],
				},
			}));
		}
	},

	fee_demand(frm) {
		if (!frm.doc.fee_demand) return;
		frappe.db.get_value("Fee Demand", frm.doc.fee_demand, [
			"fee_component", "original_amount", "paid_amount"
		], (r) => {
			if (!r) return;
			frm.set_value("fee_component", r.fee_component);
			frm.set_value("original_amount", r.original_amount);
			frm.set_value("paid_amount", r.paid_amount);

			if (r.paid_amount === 0) {
				frappe.msgprint({
					title: "No Payment Found",
					message: `This demand has ₹0 paid. A refund can only be issued for paid amounts.`,
					indicator: "orange",
				});
			}
		});
	},

	refund_amount(frm) {
		_show_refund_preview(frm);
	},

	refund_mode(frm) {
		const bank_fields = ["bank_name", "account_number", "ifsc_code", "utr_number"];
		const needs_bank = ["NEFT", "Cheque", "Online"].includes(frm.doc.refund_mode);
		bank_fields.forEach((f) => frm.toggle_reqd(f, needs_bank));
	},
});

function _show_refund_preview(frm) {
	const refund = flt(frm.doc.refund_amount);
	const paid = flt(frm.doc.paid_amount);
	if (!refund || !paid) return;

	const remaining_paid = paid - refund;
	if (remaining_paid < 0) {
		frappe.msgprint({
			title: "Invalid Refund Amount",
			message: `Refund (₹${format_currency(refund)}) exceeds amount paid (₹${format_currency(paid)}).`,
			indicator: "red",
		});
		return;
	}

	frm.dashboard.set_headline(
		`<b>Refund:</b> ₹${format_currency(refund)} &nbsp;|&nbsp; ` +
		`<b>Remaining Paid Balance:</b> ₹${format_currency(remaining_paid)}`
	);
}

function format_currency(val) {
	return frappe.format(val, { fieldtype: "Currency" });
}

// Excess refunds: show what the student can be refunded (unused active credit notes).
function _show_available_excess(frm) {
	if (frm.doc.docstatus !== 0 || frm.doc.refund_source !== "Excess Amount" || !frm.doc.student) return;
	frappe.db
		.get_list("Student Credit Note", {
			filters: { student: frm.doc.student, docstatus: 1, status: "Active" },
			fields: ["available_credit"],
			limit: 0,
		})
		.then((rows) => {
			const available = rows.reduce((sum, r) => sum + flt(r.available_credit), 0);
			frm.set_value("available_excess", available);
			if (!frm.doc.refund_amount && available) frm.set_value("refund_amount", available);
		});
}
