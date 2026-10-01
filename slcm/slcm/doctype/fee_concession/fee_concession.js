frappe.ui.form.on("Fee Concession", {
	refresh(frm) {
		frm.trigger("set_status_indicator");
		frm.trigger("set_fee_demand_filter");
	},

	set_status_indicator(frm) {
		const colors = {
			"Draft": "orange",
			"Approved": "green",
			"Rejected": "red",
			"Reversed": "grey",
		};
		if (frm.doc.status) {
			frm.page.set_indicator(frm.doc.status, colors[frm.doc.status] || "grey");
		}
	},

	setup(frm) {
		// Student ID: search by ID, name, Registration Id, Application Number or email
		frm.set_query("student", () => ({
			query: "slcm.slcm.doctype.fee_concession.fee_concession.student_query",
		}));
	},

	set_fee_demand_filter(frm) {
		frm.set_query("fee_demand", () => {
			const filters = {
				status: ["not in", ["Paid", "Cancelled", "Waived"]],
			};
			if (frm.doc.student) {
				filters.student = frm.doc.student;
			}
			return { filters };
		});
	},

	// Student ID picked first → fill Registration Id / email, and limit the Voucher list to their dues
	async student(frm) {
		frm.trigger("set_fee_demand_filter");
		if (!frm.doc.student) {
			frm.set_value({ registration_id: "", student_email: "" });
			return;
		}
		const sm = (await frappe.db.get_value("Student Master", frm.doc.student, ["registration_id", "application_number", "official_email_id", "email"])).message || {};
		frm.set_value({
			registration_id: sm.registration_id || sm.application_number || "",
			student_email: sm.official_email_id || sm.email || "",
		});
		if (frm.doc.fee_demand) {
			const v = (await frappe.db.get_value("Fee Demand", frm.doc.fee_demand, "student")).message || {};
			if (v.student !== frm.doc.student) frm.set_value("fee_demand", "");
		}
	},

	// Voucher → its student; the dues columns come from the voucher via fetch_from
	async fee_demand(frm) {
		if (!frm.doc.fee_demand) return;
		const r = await frappe.db.get_value("Fee Demand", frm.doc.fee_demand, "student");
		const student = r.message && r.message.student;
		if (student && frm.doc.student !== student) {
			await frm.set_value("student", student);
			const sm = (await frappe.db.get_value("Student Master", student, ["registration_id", "application_number", "official_email_id", "email"])).message || {};
			frm.set_value("registration_id", sm.registration_id || sm.application_number || "");
			frm.set_value("student_email", sm.official_email_id || sm.email || "");
		}
	},

	waiver_value(frm) {
		frm.trigger("calculate_waiver");
	},

	original_amount(frm) {
		frm.trigger("calculate_waiver");
	},

	calculate_waiver(frm) {
		const original = flt(frm.doc.original_amount);
		const value = flt(frm.doc.waiver_value);

		if (!original || !value) return;

		const waiver = value;

		if (waiver > original) {
			frappe.show_alert({
				message: __("Waiver Amount cannot exceed Original Amount ₹{0}", [format_currency(original, "INR")]),
				indicator: "red",
			});
			return;
		}

		frm.set_value("waiver_amount", waiver);

		// Show live preview
		frappe.show_alert({
			message: __("Waiver: ₹{0} | Outstanding after waiver: ₹{1}", [
				format_currency(waiver, "INR"),
				format_currency(Math.max(0, original - waiver - flt(frm.doc.paid_amount)), "INR"),
			]),
			indicator: "blue",
		});
	},
});
