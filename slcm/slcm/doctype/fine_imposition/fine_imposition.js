frappe.ui.form.on("Fine Imposition", {
	refresh(frm) {
		if (frm.doc.status === "Draft" && !frm.is_new()) {
			frm.add_custom_button(__("Preview Outstanding Demands"), () => {
				if (!frm.doc.from_date || !frm.doc.to_date) {
					frappe.msgprint(__("Please set From Date and To Date first."));
					return;
				}
				frappe.show_alert({ message: __("Fetching outstanding demands..."), indicator: "blue" });
				frm.call("get_outstanding_preview").then((r) => {
					show_outstanding_preview(frm, r.message);
				});
			});
		}

		if (frm.doc.status === "Draft" && !frm.is_new() && !frm.is_dirty()) {
			frm.add_custom_button(__("Apply Fine"), () => {
				frappe.confirm(
					__("This will scan outstanding Fee Demands with a Due Date between "
						+ "<b>{0}</b> and <b>{1}</b> and add a Penalty Amount to each match. "
						+ "This action cannot be undone. Proceed?",
						[frm.doc.from_date, frm.doc.to_date]),
					() => {
						frappe.show_alert({ message: __("Applying fine..."), indicator: "blue" });
						frm.call("apply_fine").then((r) => {
							frm.reload_doc();
							if (r.message) {
								frappe.msgprint(
									__("Applied fine to {0} demand(s) totalling {1}.", [
										r.message.total_demands_affected,
										format_currency(r.message.total_fine_amount),
									])
								);
							}
						});
					}
				);
			}).addClass("btn-primary");
		}

		if (frm.doc.status === "Applied") {
			frm.set_intro(
				__("This Fine Imposition has already been applied on {0} and cannot be re-applied.",
					[frappe.datetime.str_to_user(frm.doc.applied_on)]),
				"green"
			);

			frm.add_custom_button(__("Reverse Fine"), () => {
				frappe.confirm(
					__("This will remove the Penalty Amount this record added to each Fee Demand "
						+ "(demands with amounts already paid beyond the pre-penalty total are left "
						+ "untouched and logged as errors). Continue?"),
					() => {
						frappe.show_alert({ message: __("Reversing fine..."), indicator: "blue" });
						frm.call("reverse_fine").then(() => {
							frm.reload_doc();
							frappe.show_alert({ message: __("Fine reversed."), indicator: "green" });
						});
					}
				);
			});
		}

		if (frm.doc.status === "Reversed") {
			frm.set_intro(
				__("This Fine Imposition was reversed on {0}.",
					[frappe.datetime.str_to_user(frm.doc.reversed_on)]),
				"grey"
			);
		}
	},
});

function show_outstanding_preview(frm, data) {
	if (!data || !data.total_demands) {
		frappe.msgprint(__("No outstanding Fee Demands matched the selection criteria."));
		return;
	}

	let rows_html = data.rows
		.map((row) => `
			<tr>
				<td>${frappe.utils.escape_html(row.student)}</td>
				<td>${frappe.utils.escape_html(row.fee_component || "")}</td>
				<td>${frappe.utils.escape_html(row.demand_type || "")}</td>
				<td>${frappe.datetime.str_to_user(row.due_date)}</td>
				<td class="text-right">${format_currency(row.outstanding_amount)}</td>
				<td class="text-right">${format_currency(row.estimated_fine_amount)}</td>
			</tr>
		`)
		.join("");

	let dialog = new frappe.ui.Dialog({
		title: __("Outstanding Demands Preview"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "preview_html",
				options: `
					<div class="text-muted margin-bottom">
						${__("{0} demand(s) matched &mdash; total outstanding {1}, estimated total penalty {2}. "
							+ "Applying will add the estimated penalty to each demand's Penalty Amount field.", [
							data.total_demands,
							format_currency(data.total_outstanding),
							format_currency(data.total_estimated_fine),
						])}
					</div>
					<div class="table-responsive">
						<table class="table table-bordered">
							<thead>
								<tr>
									<th>${__("Student")}</th>
									<th>${__("Fee Component")}</th>
									<th>${__("Demand Type")}</th>
									<th>${__("Due Date")}</th>
									<th class="text-right">${__("Outstanding Amount")}</th>
									<th class="text-right">${__("Estimated Penalty")}</th>
								</tr>
							</thead>
							<tbody>${rows_html}</tbody>
						</table>
					</div>
				`,
			},
		],
	});

	dialog.show();
}
