// Copyright (c) 2026, SLCM and contributors

frappe.pages["attendance-quick-view"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Attendance Quick View"),
		single_column: true,
	});

	$("<style>").prop("type", "text/css").html(`
		.aqv-filter-card {
			background: #fff;
			border: 1px solid var(--border-color);
			border-radius: 8px;
			padding: 20px 24px 16px;
			margin-bottom: 20px;
		}
		.aqv-filter-grid {
			display: grid;
			grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
			gap: 14px;
			align-items: end;
		}
		.aqv-field label {
			font-size: 12px;
			font-weight: 600;
			color: var(--text-muted);
			margin-bottom: 4px;
			display: block;
		}
		.aqv-field .form-control, .aqv-field select {
			height: 32px;
			font-size: 13px;
			padding: 4px 10px;
		}
		.aqv-field .link-field .awesomplete { width: 100%; }
		.aqv-field .link-field input { width: 100%; }
		.aqv-filter-actions { display: flex; gap: 8px; padding-top: 20px; }
		.aqv-summary-bar {
			display: flex;
			gap: 12px;
			flex-wrap: wrap;
			margin-bottom: 16px;
		}
		.aqv-kpi {
			background: #fff;
			border: 1px solid var(--border-color);
			border-radius: 8px;
			padding: 12px 20px;
			text-align: center;
			flex: 1 1 90px;
		}
		.aqv-kpi .val { font-size: 22px; font-weight: 700; line-height: 1.2; }
		.aqv-kpi .lbl { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
		.aqv-kpi.c-total .val   { color: var(--blue-500); }
		.aqv-kpi.c-present .val { color: var(--green-500); }
		.aqv-kpi.c-absent .val  { color: var(--red-500); }
		.aqv-kpi.c-late .val    { color: var(--orange-500); }
		.aqv-kpi.c-od .val      { color: var(--cyan-500); }
		.aqv-kpi.c-excused .val { color: var(--gray-600); }
		.aqv-table-wrap {
			background: #fff;
			border: 1px solid var(--border-color);
			border-radius: 8px;
			overflow: hidden;
		}
		.aqv-table {
			width: 100%;
			border-collapse: collapse;
			font-size: 13px;
		}
		.aqv-table thead th {
			padding: 10px 14px;
			font-weight: 600;
			color: var(--text-muted);
			font-size: 11px;
			text-transform: uppercase;
			letter-spacing: 0.4px;
			background: var(--fg-color);
			border-bottom: 1px solid var(--border-color);
			white-space: nowrap;
		}
		.aqv-table tbody tr { border-bottom: 1px solid var(--border-color); }
		.aqv-table tbody tr:hover { background: var(--fg-color); }
		.aqv-table tbody tr:last-child { border-bottom: none; }
		.aqv-table td { padding: 9px 14px; vertical-align: middle; }
		.aqv-badge {
			display: inline-block;
			padding: 2px 10px;
			border-radius: 12px;
			font-size: 11px;
			font-weight: 600;
		}
		.aqv-badge.Present  { background: #d1fae5; color: #065f46; }
		.aqv-badge.Absent   { background: #fee2e2; color: #991b1b; }
		.aqv-badge.Late     { background: #fef3c7; color: #92400e; }
		.aqv-badge.OD       { background: #dbeafe; color: #1e40af; }
		.aqv-badge.Excused  { background: #f3f4f6; color: #374151; }
		.aqv-empty { text-align: center; padding: 60px 20px; color: var(--text-muted); }
		.aqv-footer {
			padding: 9px 14px;
			font-size: 12px;
			color: var(--text-muted);
			border-top: 1px solid var(--border-color);
			background: var(--fg-color);
		}
		.aqv-row-num { color: var(--text-muted); font-size: 11px; }
		.aqv-link { color: var(--blue-500); cursor: pointer; }
		.aqv-link:hover { text-decoration: underline; }
	`).appendTo("head");

	// Load faculty context first, then build the page
	frappe.call({
		method: "slcm.slcm.page.attendance_quick_view.attendance_quick_view.get_faculty_context",
		callback: r => {
			new AttendanceQuickView(page, r.message || {});
		},
	});
};

class AttendanceQuickView {
	constructor(page, ctx) {
		this.page = page;
		this.ctx  = ctx || {};   // faculty context from server
		this.ctrls = {};
		this._build();
	}

	_build() {
		const $main = $(this.page.main).empty();
		const ctx   = this.ctx;

		// ---- Filter card ----
		const $card = $(`<div class="aqv-filter-card"></div>`).appendTo($main);
		const $grid = $(`<div class="aqv-filter-grid"></div>`).appendTo($card);

		// Build Programme link with optional in_filter restriction for faculty
		const progFilter = (ctx.restricted && ctx.programmes && ctx.programmes.length)
			? {"name": ["in", ctx.programmes]}
			: null;
		this.ctrls.programme = this._link($grid, "Programme", "Programme", progFilter);

		// Class — restricted to faculty's visible classes
		const classFilter = (ctx.restricted && ctx.classes && ctx.classes.length)
			? {"name": ["in", ctx.classes]}
			: null;
		this.ctrls.class_name = this._link($grid, "Class", "Classes", classFilter);

		this.ctrls.from_date = this._date($grid, "From Date");
		this.ctrls.to_date   = this._date($grid, "To Date");
		this.ctrls.period    = this._link($grid, "Period", "Attendance Period");

		// Section — restricted to faculty's visible sections
		const secFilter = (ctx.restricted && ctx.sections && ctx.sections.length)
			? {"name": ["in", ctx.sections]}
			: null;
		this.ctrls.section = this._link($grid, "Section", "Section", secFilter);

		this.ctrls.status = this._select($grid, "Status",
			["", "Present", "Absent", "Late", "OD", "Excused"]);

		// Actions cell
		const $act = $(`<div class="aqv-filter-actions"></div>`).appendTo($grid);
		$(`<button class="btn btn-primary btn-sm">${__("Search")}</button>`)
			.appendTo($act).on("click", () => this._load());
		$(`<button class="btn btn-default btn-sm">${__("Clear")}</button>`)
			.appendTo($act).on("click", () => this._clear());

		// ---- Summary bar (hidden until search) ----
		this.$summary = $(`<div class="aqv-summary-bar" style="display:none"></div>`).appendTo($main);

		// ---- Table area ----
		this.$table  = $(`<div class="aqv-table-wrap"></div>`).appendTo($main);
		this._empty("Use the filters above and click <b>Search</b> to view attendance records.");
	}

	/* ---------- filter helpers ---------- */

	_link($parent, label, doctype, filters) {
		const $wrap = $(`<div class="aqv-field"><label>${__(label)}</label></div>`).appendTo($parent);
		const df = { fieldtype: "Link", options: doctype, fieldname: frappe.scrub(label), label: "" };
		if (filters) df.filters = filters;
		const ctrl = frappe.ui.form.make_control({
			parent: $wrap[0],
			df,
			render_input: true,
		});
		ctrl.refresh();
		return ctrl;
	}

	_date($parent, label) {
		const $wrap = $(`<div class="aqv-field"><label>${__(label)}</label></div>`).appendTo($parent);
		const ctrl = frappe.ui.form.make_control({
			parent: $wrap[0],
			df: { fieldtype: "Date", fieldname: frappe.scrub(label), label: "" },
			render_input: true,
		});
		ctrl.refresh();
		return ctrl;
	}

	_select($parent, label, options) {
		const $wrap = $(`<div class="aqv-field"><label>${__(label)}</label></div>`).appendTo($parent);
		const $sel = $(`<select class="form-control"></select>`).appendTo($wrap);
		options.forEach(o => $sel.append(`<option value="${o}">${o ? __(o) : __("All")}</option>`));
		// duck-type to match ctrl API
		return { get_value: () => $sel.val(), set_value: (v) => $sel.val(v) };
	}

	_vals() {
		return {
			programme:       this.ctrls.programme.get_value(),
			class_name:      this.ctrls.class_name.get_value(),
			from_date:       this.ctrls.from_date.get_value(),
			to_date:         this.ctrls.to_date.get_value(),
			period:          this.ctrls.period.get_value(),
			section:         this.ctrls.section.get_value(),
			status:          this.ctrls.status.get_value(),
		};
	}

	_clear() {
		Object.values(this.ctrls).forEach(c => c.set_value(""));
		this.$summary.hide();
		this._empty("Use the filters above and click <b>Search</b> to view attendance records.");
	}

	/* ---------- data ---------- */

	_load() {
		const f = this._vals();
		if (!f.from_date && !f.to_date && !f.programme && !f.class_name && !f.period) {
			frappe.msgprint(__("Please select at least one filter before searching."));
			return;
		}
		this.$table.html(`<div class="aqv-empty">${frappe.utils.icon("loading", "lg")} Loading...</div>`);
		this.$summary.hide();

		frappe.call({
			method: "slcm.slcm.page.attendance_quick_view.attendance_quick_view.get_attendance_data",
			args: f,
			callback: r => {
				if (r.message) this._render(r.message);
			},
		});
	}

	/* ---------- render ---------- */

	_render({ data, summary }) {
		// summary bar
		const s = summary;
		this.$summary.html(`
			<div class="aqv-kpi c-total">  <div class="val">${s.total}</div>   <div class="lbl">${__("Total")}</div></div>
			<div class="aqv-kpi c-present"><div class="val">${s.present}</div>  <div class="lbl">${__("Present")}</div></div>
			<div class="aqv-kpi c-absent"> <div class="val">${s.absent}</div>   <div class="lbl">${__("Absent")}</div></div>
			<div class="aqv-kpi c-late">   <div class="val">${s.late}</div>     <div class="lbl">${__("Late")}</div></div>
			<div class="aqv-kpi c-od">     <div class="val">${s.od}</div>       <div class="lbl">${__("OD")}</div></div>
			<div class="aqv-kpi c-excused"><div class="val">${s.excused}</div>  <div class="lbl">${__("Excused")}</div></div>
		`).show();

		if (!data || !data.length) {
			this._empty("No attendance records found for the selected filters.");
			return;
		}

		const rows = data.map((r, i) => `
			<tr>
				<td class="aqv-row-num">${i + 1}</td>
				<td>
					<span class="aqv-link" onclick="frappe.set_route('Form','Student Master','${esc(r.student)}')">${esc(r.student_name || r.student)}</span>
					<div style="font-size:11px;color:var(--text-muted)">${esc(r.student)}</div>
				</td>
				<td>${esc(r.program || "—")}</td>
				<td>${esc(r.course || r.class_name || "—")}</td>
				<td>${r.attendance_date ? frappe.datetime.str_to_user(r.attendance_date) : "—"}</td>
				<td>${esc(r.period || "—")}</td>
				<td>${esc(r.session_type || "—")}</td>
				<td><span class="aqv-badge ${r.status}">${__(r.status)}</span></td>
				<td>
					<span class="aqv-link" title="${__("Open record")}"
						onclick="frappe.set_route('Form','Student Attendance','${esc(r.name)}')">
						${frappe.utils.icon("external-link", "xs")}
					</span>
				</td>
			</tr>
		`).join("");

		const cap = data.length === 500
			? ` &nbsp;·&nbsp; ${__("Results capped at 500 — narrow your filters to see more.")}`
			: "";

		this.$table.html(`
			<table class="aqv-table">
				<thead><tr>
					<th>#</th>
					<th>${__("Student")}</th>
					<th>${__("Programme")}</th>
					<th>${__("Course")}</th>
					<th>${__("Date")}</th>
					<th>${__("Period")}</th>
					<th>${__("Session Type")}</th>
					<th>${__("Status")}</th>
					<th></th>
				</tr></thead>
				<tbody>${rows}</tbody>
			</table>
			<div class="aqv-footer">${__("Showing {0} records", [data.length])}${cap}</div>
		`);
	}

	_empty(msg) {
		this.$table.html(`<div class="aqv-empty">
			<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom:12px;opacity:.35">
				<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
			</svg>
			<div>${msg}</div>
		</div>`);
	}
}

function esc(s) {
	return frappe.utils.escape_html(String(s || ""));
}
