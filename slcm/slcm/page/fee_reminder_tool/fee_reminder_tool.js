frappe.pages["fee-reminder-tool"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Fee Reminder Tool",
		single_column: true,
	});

	// ── State ────────────────────────────────────────────────────────────
	let all_demands = [];
	let selected_names = new Set();

	// ── Filter bar ───────────────────────────────────────────────────────
	const $filters = $(`
		<div class="frt-filters" style="
			background:#fff;border:1px solid #e5e7eb;border-radius:8px;
			padding:18px 20px;margin-bottom:16px;display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;">
		</div>
	`).appendTo(page.main);

	function _select(label, name, options_promise) {
		const $wrap = $(`<div style="display:flex;flex-direction:column;gap:4px;min-width:160px;">
			<label style="font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.04em;">${label}</label>
			<select name="${name}" style="border:1px solid #d1d5db;border-radius:6px;padding:7px 10px;font-size:13px;color:#111827;background:#f9fafb;">
				<option value="">— All —</option>
			</select>
		</div>`).appendTo($filters);
		const $sel = $wrap.find("select");
		options_promise.then(opts => {
			opts.forEach(o => $sel.append(`<option value="${o}">${o}</option>`));
		});
		return $sel;
	}

	frappe.call({ method: "slcm.slcm.page.fee_reminder_tool.fee_reminder_tool.get_filter_options" })
		.then(r => {
			const opts = r.message;
			window._frt_opts = opts;
		});

	// Reminder type (always shown first)
	const $type = $(`<div style="display:flex;flex-direction:column;gap:4px;min-width:180px;">
		<label style="font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.04em;">Reminder Type</label>
		<select name="reminder_type" style="border:1px solid #d1d5db;border-radius:6px;padding:7px 10px;font-size:13px;color:#111827;background:#f9fafb;">
			<option value="overdue">Overdue Notice</option>
			<option value="7day">7-Day Advance Reminder</option>
			<option value="1day">1-Day Final Reminder</option>
		</select>
	</div>`).appendTo($filters).find("select");

	const $program = _select("Programme", "program",
		Promise.resolve([]).then(() => window._frt_opts ? window._frt_opts.programs : []));
	const $year    = _select("Academic Year", "academic_year",
		Promise.resolve([]).then(() => window._frt_opts ? window._frt_opts.academic_years : []));
	const $dtype   = _select("Demand Type", "demand_type",
		Promise.resolve(["Academic","Non Academic"]));

	// Reload options after fetch
	frappe.call({ method: "slcm.slcm.page.fee_reminder_tool.fee_reminder_tool.get_filter_options" })
		.then(r => {
			const opts = r.message;
			$program.empty().append('<option value="">— All —</option>');
			opts.programs.forEach(o => $program.append(`<option value="${o}">${o}</option>`));
			$year.empty().append('<option value="">— All —</option>');
			opts.academic_years.forEach(o => $year.append(`<option value="${o}">${o}</option>`));
		});

	// Search button
	const $searchBtn = $(`<div style="display:flex;flex-direction:column;gap:4px;">
		<label style="font-size:11px;color:transparent;">.</label>
		<button class="btn btn-primary btn-sm" style="padding:7px 20px;font-size:13px;">
			<i class="fa fa-search" style="margin-right:6px;"></i>Search
		</button>
	</div>`).appendTo($filters).find("button");

	// ── Summary bar ──────────────────────────────────────────────────────
	const $summary = $(`
		<div class="frt-summary" style="
			display:none;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;
			padding:12px 18px;margin-bottom:12px;font-size:13px;color:#1e40af;
			display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
			<span class="frt-summary-text"></span>
			<div style="display:flex;gap:8px;">
				<button class="btn btn-xs frt-select-all" style="background:#dbeafe;color:#1e40af;border:none;border-radius:4px;padding:4px 12px;">
					Select All
				</button>
				<button class="btn btn-xs frt-deselect-all" style="background:#e5e7eb;color:#374151;border:none;border-radius:4px;padding:4px 12px;">
					Deselect All
				</button>
			</div>
		</div>
	`).appendTo(page.main);

	// ── Results table ────────────────────────────────────────────────────
	const $tableWrap = $(`
		<div class="frt-table-wrap" style="display:none;background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;margin-bottom:16px;">
			<table class="table table-bordered" style="margin:0;font-size:13px;">
				<thead style="background:#f9fafb;">
					<tr>
						<th style="width:36px;padding:10px 12px;">
							<input type="checkbox" id="frt-check-all">
						</th>
						<th style="padding:10px 12px;">Student</th>
						<th style="padding:10px 12px;">Program</th>
						<th style="padding:10px 12px;">Academic Year</th>
						<th style="padding:10px 12px;">Fee Head</th>
						<th style="padding:10px 12px;">Demand Type</th>
						<th style="padding:10px 12px;text-align:right;">Outstanding (₹)</th>
						<th style="padding:10px 12px;">Due Date</th>
						<th style="padding:10px 12px;">Status</th>
						<th style="padding:10px 12px;">Email</th>
					</tr>
				</thead>
				<tbody class="frt-tbody"></tbody>
			</table>
		</div>
	`).appendTo(page.main);

	// ── Send bar ─────────────────────────────────────────────────────────
	const $sendBar = $(`
		<div class="frt-send-bar" style="
			display:none;background:#fff;border:1px solid #e5e7eb;border-radius:8px;
			padding:14px 18px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;">
			<span class="frt-selected-count" style="font-size:13px;color:#374151;font-weight:600;"></span>
			<button class="btn btn-danger frt-send-btn" style="padding:8px 24px;font-size:13px;font-weight:600;">
				<i class="fa fa-paper-plane" style="margin-right:6px;"></i>Send Reminders
			</button>
		</div>
	`).appendTo(page.main);

	// ── Helpers ───────────────────────────────────────────────────────────
	function _status_badge(status) {
		const map = {
			"Overdue":      "background:#fee2e2;color:#dc2626",
			"Pending":      "background:#fef9c3;color:#854d0e",
			"Partially Paid":"background:#e0f2fe;color:#0369a1",
		};
		const style = map[status] || "background:#f3f4f6;color:#374151";
		return `<span style="${style};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;">${status}</span>`;
	}

	function _update_selected_count() {
		const n = selected_names.size;
		$sendBar.find(".frt-selected-count").text(`${n} student${n !== 1 ? "s" : ""} selected`);
		$sendBar.css("display", n > 0 ? "flex" : "none");
	}

	function _render_table(demands) {
		all_demands = demands;
		selected_names.clear();
		const $tbody = $tableWrap.find(".frt-tbody").empty();

		if (!demands.length) {
			$tbody.append(`<tr><td colspan="10" style="text-align:center;padding:24px;color:#6b7280;">
				No pending demands found for the selected filters.</td></tr>`);
			$tableWrap.show();
			$summary.hide();
			$sendBar.css("display", "none");
			return;
		}

		demands.forEach(d => {
			const noEmail = !d.student_email;
			const $row = $(`<tr data-name="${d.name}" style="${noEmail ? 'opacity:0.5;' : ''}">
				<td style="padding:10px 12px;text-align:center;">
					<input type="checkbox" class="frt-row-check" data-name="${d.name}" ${noEmail ? "disabled title='No email address'" : ""}>
				</td>
				<td style="padding:10px 12px;">
					<div style="font-weight:600;color:#111827;">${d.student_name || d.student}</div>
					<div style="font-size:11px;color:#6b7280;">${d.student}</div>
				</td>
				<td style="padding:10px 12px;color:#374151;">${d.program || "—"}</td>
				<td style="padding:10px 12px;color:#374151;">${d.academic_year || "—"}</td>
				<td style="padding:10px 12px;color:#374151;">${d.fee_component || "—"}</td>
				<td style="padding:10px 12px;color:#374151;">${d.demand_type || "—"}</td>
				<td style="padding:10px 12px;text-align:right;font-weight:600;color:#111827;">
					${frappe.format(d.outstanding_amount, {fieldtype:"Currency"})}</td>
				<td style="padding:10px 12px;color:#374151;">${d.due_date || "—"}</td>
				<td style="padding:10px 12px;">${_status_badge(d.status)}</td>
				<td style="padding:10px 12px;font-size:11px;color:#6b7280;">
					${d.student_email || '<span style="color:#dc2626;">No email</span>'}</td>
			</tr>`);
			$tbody.append($row);
		});

		const total   = demands.length;
		const no_mail = demands.filter(d => !d.student_email).length;
		$summary.find(".frt-summary-text").html(
			`Found <strong>${total}</strong> pending demand${total !== 1 ? "s" : ""}.
			${no_mail ? `<span style="color:#dc2626;margin-left:8px;">${no_mail} skipped — no email address.</span>` : ""}`
		);
		$summary.show();
		$tableWrap.show();
		_update_selected_count();
	}

	// ── Events ────────────────────────────────────────────────────────────
	$searchBtn.on("click", () => {
		const reminder_type = $type.val();
		const program       = $program.val();
		const academic_year = $year.val();
		const demand_type   = $dtype.val();

		$searchBtn.prop("disabled", true).html('<i class="fa fa-spinner fa-spin"></i> Searching...');

		frappe.call({
			method: "slcm.slcm.page.fee_reminder_tool.fee_reminder_tool.get_pending_demands",
			args: { program, academic_year, demand_type, reminder_type },
			callback(r) {
				$searchBtn.prop("disabled", false).html('<i class="fa fa-search" style="margin-right:6px;"></i>Search');
				_render_table(r.message || []);
			},
		});
	});

	// Row checkbox
	$tableWrap.on("change", ".frt-row-check", function () {
		const name = $(this).data("name");
		if (this.checked) selected_names.add(name);
		else selected_names.delete(name);
		_update_selected_count();

		// Sync header checkbox
		const total_checkable = $tableWrap.find(".frt-row-check:not(:disabled)").length;
		const total_checked   = $tableWrap.find(".frt-row-check:checked").length;
		$("#frt-check-all").prop("indeterminate", total_checked > 0 && total_checked < total_checkable);
		$("#frt-check-all").prop("checked", total_checked === total_checkable && total_checkable > 0);
	});

	// Header checkbox — select/deselect all enabled rows
	$("#frt-check-all").on("change", function () {
		$tableWrap.find(".frt-row-check:not(:disabled)").prop("checked", this.checked).trigger("change");
	});

	$summary.find(".frt-select-all").on("click", () => {
		$tableWrap.find(".frt-row-check:not(:disabled)").prop("checked", true).trigger("change");
	});
	$summary.find(".frt-deselect-all").on("click", () => {
		$tableWrap.find(".frt-row-check:not(:disabled)").prop("checked", false).trigger("change");
	});

	// Send button
	$sendBar.find(".frt-send-btn").on("click", () => {
		const names = [...selected_names];
		const reminder_type = $type.val();
		const label_map = { overdue: "Overdue Notice", "7day": "7-Day Reminder", "1day": "1-Day Reminder" };

		frappe.confirm(
			`Send <strong>${label_map[reminder_type]}</strong> to <strong>${names.length}</strong> student(s)?`,
			() => {
				$sendBar.find(".frt-send-btn").prop("disabled", true)
					.html('<i class="fa fa-spinner fa-spin"></i> Sending...');

				frappe.call({
					method: "slcm.slcm.page.fee_reminder_tool.fee_reminder_tool.send_manual_reminders",
					args: { demand_names: names, reminder_type },
					callback(r) {
						$sendBar.find(".frt-send-btn").prop("disabled", false)
							.html('<i class="fa fa-paper-plane" style="margin-right:6px;"></i>Send Reminders');

						const { queued, message } = r.message || {};
						frappe.msgprint({
							title: "Reminders Queued",
							message: message || `${queued} reminder(s) queued for delivery.`,
							indicator: "green",
						});

						// Refresh the table to reflect new flag state
						$searchBtn.trigger("click");
					},
				});
			}
		);
	});
};
