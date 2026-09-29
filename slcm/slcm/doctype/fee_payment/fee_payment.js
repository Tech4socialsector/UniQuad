frappe.ui.form.on("Fee Payment", {
	setup(frm) {
		// Student ID: search by ID, name, Registration Id, Application Number or email
		frm.set_query("student", () => ({ query: "slcm.slcm.doctype.fee_concession.fee_concession.student_query" }));
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.student) {
			frm.add_custom_button(__("Load Pending Demands"), () => {
				frm.trigger("load_pending_demands");
			}).addClass("btn-primary");
		}

		if (frm.doc.student) {
			frm.add_custom_button(__("View Fee Demands"), () => {
				frm.trigger("show_fee_demands");
			}, __("View"));
		}

		if (frm.doc.docstatus === 1 && frm.doc.receipt) {
			frm.add_custom_button(__("View Receipt"), () => {
				frappe.set_route("Form", "Fee Receipt", frm.doc.receipt);
			}).addClass("btn-primary");

			frm.add_custom_button(__("Print Admin Copy"), () => {
				const url = frappe.urllib.get_full_url(
					`/printview?doctype=Fee Payment&name=${frm.doc.name}&format=Fee Payment Receipt - Admin Copy`
				);
				window.open(url, "_blank");
			}, __("Print Receipt"));

			frm.add_custom_button(__("Print Student Copy"), () => {
				const url = frappe.urllib.get_full_url(
					`/printview?doctype=Fee Payment&name=${frm.doc.name}&format=Fee Payment Receipt - Student Copy`
				);
				window.open(url, "_blank");
			}, __("Print Receipt"));
		}

		// Show total allocated vs payment amount summary
		if (frm.doc.payment_demands && frm.doc.payment_demands.length) {
			frm.trigger("update_allocation_summary");
		}
	},

	student(frm) {
		frm.refresh();
		if (!frm.doc.student || frm.doc.fee_demand) return;
		frm.trigger("load_pending_demands");
	},

	// Voucher Number (one due): its student + dues columns; the Fee Demands Covered row is built on save
	async fee_demand(frm) {
		if (!frm.doc.fee_demand) return;
		const d = (await frappe.db.get_value("Fee Demand", frm.doc.fee_demand, ["student", "outstanding_amount"])).message || {};
		if (frm.doc.student !== d.student) {
			frm.doc.student = d.student; // set silently: don't auto-load every pending due into the table
			frm.refresh_field("student");
		}
		frm.clear_table("payment_demands");
		frm.refresh_field("payment_demands");
		if (!flt(frm.doc.amount)) frm.set_value("amount", flt(d.outstanding_amount));
		frm.refresh();
	},

	load_pending_demands(frm) {
		if (!frm.doc.student) return;

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Fee Demand",
				filters: [
					["student", "=", frm.doc.student],
					["status", "in", ["Pending", "Partially Paid", "Overdue", "Moved to Excess"]],
				],
				fields: ["name", "description", "fee_component", "outstanding_amount", "due_date", "status"],
				order_by: "due_date asc",
				limit: 50,
			},
			callback(r) {
				if (!r.message || !r.message.length) {
					frappe.show_alert({
						message: __("No pending dues found for this student."),
						indicator: "orange",
					});
					return;
				}

				// Build a dialog to select demands
				const fields = r.message.map((d) => ({
					fieldtype: "Check",
					fieldname: d.name,
					label: `${d.description || d.fee_component} — ₹${format_number(d.outstanding_amount)} (Due: ${frappe.datetime.str_to_user(d.due_date)}) [${d.status}]`,
					default: 0,
				}));

				const dialog = new frappe.ui.Dialog({
					title: __("Select Fee Demands to Pay"),
					fields: fields,
					primary_action_label: __("Add to Payment"),
					primary_action(values) {
						const selected = r.message.filter((d) => values[d.name]);
						if (!selected.length) {
							frappe.msgprint(__("Please select at least one demand."));
							return;
						}

						// Clear existing demands table
						frm.clear_table("payment_demands");

						let total = 0;
						selected.forEach((d) => {
							const row = frm.add_child("payment_demands");
							row.fee_demand = d.name;
							row.demand_description = d.description || d.fee_component;
							row.outstanding_amount = d.outstanding_amount;
							row.amount_allocated = d.outstanding_amount;
							total += d.outstanding_amount;
						});

						frm.set_value("amount", total);
						frm.refresh_field("payment_demands");
						frm.refresh_field("amount");
						frm.trigger("update_allocation_summary");
						dialog.hide();
					},
				});
				dialog.show();
			},
		});
	},

	show_fee_demands(frm) {
		if (!frm.doc.student) return;

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Fee Demand",
				filters: [["student", "=", frm.doc.student]],
				fields: [
					"name", "description", "fee_component", "demand_type",
					"academic_year", "due_date", "status",
					"original_amount", "paid_amount", "outstanding_amount",
				],
				order_by: "due_date asc",
				limit: 100,
			},
			callback(r) {
				if (!r.message || !r.message.length) {
					frappe.msgprint({
						title: __("Fee Demands"),
						message: __("No fee demands found for {0}.", [frm.doc.student_name || frm.doc.student]),
						indicator: "orange",
					});
					return;
				}

				const rows = r.message.map((d) => {
					const status_color = {
						"Pending": "#f59e0b",
						"Partially Paid": "#3b82f6",
						"Paid": "#10b981",
						"Overdue": "#ef4444",
						"Waived": "#8b5cf6",
						"Cancelled": "#6b7280",
					}[d.status] || "#6b7280";

					return `<tr>
						<td><a href="/desk#Form/Fee Demand/${d.name}" target="_blank">${d.name}</a></td>
						<td>${d.description || d.fee_component || "-"}</td>
						<td>${d.demand_type || "-"}</td>
						<td>${d.academic_year || "-"}</td>
						<td>${frappe.datetime.str_to_user(d.due_date) || "-"}</td>
						<td style="text-align:right">₹${format_number(d.original_amount)}</td>
						<td style="text-align:right">₹${format_number(d.paid_amount)}</td>
						<td style="text-align:right; font-weight:bold">₹${format_number(d.outstanding_amount)}</td>
						<td><span style="color:${status_color}; font-weight:600">${d.status}</span></td>
					</tr>`;
				}).join("");

				const total_outstanding = r.message.reduce((s, d) => s + (d.outstanding_amount || 0), 0);
				const total_paid = r.message.reduce((s, d) => s + (d.paid_amount || 0), 0);
				const total_original = r.message.reduce((s, d) => s + (d.original_amount || 0), 0);

				const html = `
					<div style="margin-bottom:12px; font-weight:600; font-size:14px">
						${frm.doc.student_name || frm.doc.student}
					</div>
					<div style="overflow-x:auto">
					<table class="table table-bordered table-condensed" style="font-size:12px; width:100%">
						<thead style="background:#f5f5f5">
							<tr>
								<th>Demand ID</th>
								<th>Description</th>
								<th>Type</th>
								<th>Academic Year</th>
								<th>Due Date</th>
								<th style="text-align:right">Original</th>
								<th style="text-align:right">Paid</th>
								<th style="text-align:right">Outstanding</th>
								<th>Status</th>
							</tr>
						</thead>
						<tbody>${rows}</tbody>
						<tfoot style="background:#f9f9f9; font-weight:bold">
							<tr>
								<td colspan="5">Total (${r.message.length} demands)</td>
								<td style="text-align:right">₹${format_number(total_original)}</td>
								<td style="text-align:right">₹${format_number(total_paid)}</td>
								<td style="text-align:right">₹${format_number(total_outstanding)}</td>
								<td></td>
							</tr>
						</tfoot>
					</table>
					</div>`;

				const dialog = new frappe.ui.Dialog({
					title: __("Fee Demands — {0}", [frm.doc.student_name || frm.doc.student]),
					fields: [{ fieldtype: "HTML", fieldname: "demands_html" }],
					size: "extra-large",
					primary_action_label: __("Open Fee Demand List"),
					primary_action() {
						frappe.set_route("List", "Fee Demand", { student: frm.doc.student });
						dialog.hide();
					},
					secondary_action_label: __("Close"),
					secondary_action() { dialog.hide(); },
				});
				dialog.show();
				dialog.fields_dict.demands_html.$wrapper.html(html);
			},
		});
	},

	amount(frm) {
		frm.trigger("update_allocation_summary");
	},

	update_allocation_summary(frm) {
		if (!frm.doc.payment_demands || !frm.doc.payment_demands.length) return;

		const total_allocated = frm.doc.payment_demands.reduce(
			(sum, row) => sum + (flt(row.amount_allocated) || 0), 0
		);
		const payment_amount = flt(frm.doc.amount) || 0;
		const diff = Math.round((payment_amount - total_allocated) * 100) / 100;

		if (diff !== 0) {
			frappe.show_alert({
				message: __("Payment ₹{0} — Allocated ₹{1} — Difference ₹{2}",
					[format_number(payment_amount), format_number(total_allocated), format_number(Math.abs(diff))]),
				indicator: "orange",
			});
		}
	},
});

// Child table — recalculate summary when row changes
frappe.ui.form.on("Fee Payment Demand Row", {
	amount_allocated(frm) {
		frm.trigger("update_allocation_summary");
	},
	fee_payment_demand_row_remove(frm) {
		frm.trigger("update_allocation_summary");
	},
});
