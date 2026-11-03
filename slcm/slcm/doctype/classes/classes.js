// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Classes", {
	setup(frm) {
		// Only terms of the selected Academic Year can be picked.
		frm.set_query("academic_term", () => ({
			filters: { academic_year: frm.doc.academic_year },
		}));
		frm.set_query("course", () => ({ filters: { status: "Active" } }));
		// A Group class may take students from any programme.
		frm.set_query("student_enrollment", "enrolled_students", () => ({
			filters:
				frm.doc.class_type === "Group"
					? { status: "Enrolled" }
					: { program: frm.doc.programme, status: "Enrolled" },
		}));
	},

	refresh(frm) {
		if (frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Add / Remove Students"), () => add_remove_students(frm));
		}
		// Dialogs in public/js/class_time_table.js
		if (!frm.is_new() && !frm.is_dirty()) {
			if (frappe.model.can_create("Time Table")) {
				frm.add_custom_button(__("Create Time Table"), () => slcm.class_time_table.open_create(frm), __("Time Table"));
			}
			if (frappe.model.can_read("Time Table")) {
				frm.add_custom_button(__("View Time Table"), () => slcm.class_time_table.open_view(frm), __("Time Table"));
			}
		}
		render_schedule_log(frm);
		render_student_log(frm);
	},

	class_type(frm) {
		frm.refresh();
	},

	academic_year(frm) {
		frm.set_value("academic_term", null);
	},
});

// Student Log tab: students added after the class was created (Late Add on
// their row), and every student added, removed or changed in status since
// (Class Student Log, written by the server on save).
const SL_BADGE = { Added: "green", Removed: "red", "Status Changed": "orange" };

function render_student_log(frm) {
	const $w = frm.get_field("student_log_html").$wrapper;
	frm.dashboard.clear_headline();
	if (frm.is_new()) {
		$w.empty();
		return;
	}
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const when = (v) => (v ? esc(frappe.datetime.str_to_user(v)) : "");
	const who = (u) => esc(u ? frappe.user.full_name(u) : "");
	const late = (frm.doc.enrolled_students || []).filter((r) => r.added_after_creation);
	const log = [...(frm.doc.student_log || [])].sort((a, b) => (b.changed_on || "").localeCompare(a.changed_on || "") || b.idx - a.idx);
	const report = `<button class="btn btn-xs btn-default sl-report">${__("Class Student Changes report")}</button>`;

	if (late.length) {
		frm.dashboard.set_headline(
			__("{0} student(s) were added after this class was created.", [late.length])
				+ ` <a class="sl-open">${__("See the Student Log tab")}</a>`,
			"orange"
		);
		frm.$wrapper.find(".sl-open").on("click", () => frm.scroll_to_field("student_log_html"));
	}

	$w.html(`
		<h5 style="margin:16px 0 8px">${__("Added after the class was created")} (${late.length})</h5>
		${late.length ? `<div style="border:1px solid var(--border-color);border-radius:8px;overflow:auto">
			<table class="table table-sm" style="margin:0;font-size:13px">
				<thead><tr><th>${__("Student ID")}</th><th>${__("Student Name")}</th><th>${__("Status")}</th>
					<th>${__("Added On")}</th><th>${__("Added By")}</th></tr></thead>
				<tbody>${late.map((r) => `<tr><td>${esc(r.student_enrollment)}</td><td>${esc(r.student_name)}</td>
					<td>${esc(r.status)}</td><td style="white-space:nowrap">${when(r.added_on)}</td><td>${who(r.added_by)}</td></tr>`).join("")}</tbody>
			</table></div>`
			: `<div class="text-muted">${__("Every student in the class was there when it was created.")}</div>`}

		<div style="display:flex;gap:10px;align-items:center;margin:24px 0 8px;flex-wrap:wrap">
			<h5 style="margin:0">${__("Change log")}</h5>
			<select class="form-control sl-action" style="max-width:180px">
				<option value="">${__("All Actions")}</option>
				${Object.keys(SL_BADGE).map((a) => `<option value="${esc(a)}">${__(a)}</option>`).join("")}
			</select>
			<span class="text-muted sl-count" style="font-size:12.5px"></span>
			<span style="flex:1"></span><span style="font-size:12.5px">${report}</span>
		</div>
		<div style="max-height:480px;overflow:auto;border:1px solid var(--border-color);border-radius:8px">
			<table class="table table-sm" style="margin:0;font-size:13px">
				<thead style="position:sticky;top:0;background:var(--subtle-fg, var(--control-bg))"><tr>
					<th>${__("Changed On")}</th><th>${__("Action")}</th><th>${__("Student ID")}</th><th>${__("Student Name")}</th>
					<th>${__("From")}</th><th>${__("To")}</th><th>${__("Changed By")}</th>
				</tr></thead>
				<tbody class="sl-body"></tbody>
			</table>
		</div>`);
	const render = (action) => {
		const list = log.filter((r) => !action || r.action === action);
		$w.find(".sl-count").text(__("{0} entries", [list.length]));
		$w.find(".sl-body").html(list.map((r) => `<tr>
			<td style="white-space:nowrap">${when(r.changed_on)}</td>
			<td><span class="indicator-pill ${SL_BADGE[r.action] || "gray"}">${__(r.action)}</span></td>
			<td>${esc(r.student_enrollment)}</td><td>${esc(r.student_name)}</td>
			<td>${esc(r.from_status)}</td><td>${esc(r.to_status)}</td><td style="white-space:nowrap">${who(r.changed_by)}</td>
		</tr>`).join("") || `<tr><td colspan="7" class="text-muted">${__("No students added, removed or changed since the class was created.")}</td></tr>`);
	};
	$w.find(".sl-action").on("change", (e) => render(e.target.value));
	$w.find(".sl-report").on("click", () => frappe.set_route("query-report", "Class Student Changes", { class_name: frm.doc.name }));
	render("");
}

// Schedule Log tab: who created, edited, cancelled, swapped or deleted the
// class's Time Table sessions, and when (Class Schedule Log).
const CSL_BADGE = { Created: "green", Edited: "blue", Cancelled: "red", Swapped: "orange", Deleted: "gray" };

function render_schedule_log(frm) {
	const $w = frm.get_field("schedule_log_html").$wrapper;
	if (frm.is_new()) {
		$w.empty();
		return;
	}
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	frappe.call({
		method: "slcm.slcm.doctype.class_schedule_log.class_schedule_log.get_class_schedule_log",
		args: { class_name: frm.doc.name },
	}).then(({ message: rows = [] }) => {
		if (!rows.length) {
			$w.html(`<div class="text-muted" style="padding:16px 0">${__("No Time Table changes logged for this class yet.")}</div>`);
			return;
		}
		const actions = [...new Set(rows.map((r) => r.action))];
		$w.html(`
			<div style="display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
				<select class="form-control csl-action" style="max-width:180px">
					<option value="">${__("All Actions")}</option>
					${actions.map((a) => `<option value="${esc(a)}">${__(a)}</option>`).join("")}
				</select>
				<span class="text-muted csl-count" style="font-size:12.5px"></span>
			</div>
			<div style="max-height:480px;overflow:auto;border:1px solid var(--border-color);border-radius:8px">
				<table class="table table-sm" style="margin:0;font-size:13px">
					<thead style="position:sticky;top:0;background:var(--subtle-fg, var(--control-bg))"><tr>
						<th>${__("Changed On")}</th><th>${__("Action")}</th><th>${__("Session Date")}</th>
						<th>${__("Details")}</th><th>${__("Changed By")}</th>
					</tr></thead>
					<tbody class="csl-body"></tbody>
				</table>
			</div>`);
		const render = (action) => {
			const list = rows.filter((r) => !action || r.action === action);
			$w.find(".csl-count").text(__("{0} entries", [list.length]));
			$w.find(".csl-body").html(list.map((r) => `<tr>
				<td style="white-space:nowrap">${esc(frappe.datetime.str_to_user(r.changed_on))}</td>
				<td><span class="indicator-pill ${CSL_BADGE[r.action] || "gray"}">${__(r.action)}</span></td>
				<td style="white-space:nowrap">${r.session_date ? esc(frappe.datetime.str_to_user(r.session_date)) : ""}
					${r.time_table ? `<div class="text-muted" style="font-size:11.5px">${esc(r.time_table)}</div>` : ""}</td>
				<td>${esc(r.details)}</td>
				<td style="white-space:nowrap">${esc(r.changed_by_name)}</td>
			</tr>`).join(""));
		};
		$w.find(".csl-action").on("change", (e) => render(e.target.value));
		render("");
	});
}

// The class's Enrolled students ticked, others found with any filters (any
// year); ticked ones not listed are added, unticked ones taken off. Rows with
// another status (Completed, Withdrawn ...) stay as history.
function add_remove_students(frm) {
	const enrolled = (frm.doc.enrolled_students || []).filter((r) => r.status === "Enrolled");
	slcm.class_students.pick({
		current: enrolled.map((r) => ({ student_enrollment: r.student_enrollment, student_name: r.student_name, section: r.section })),
		programme: frm.doc.class_type === "Group" ? "" : frm.doc.programme,
	}).then((picked) => {
		if (!picked) return;
		const keep = new Set(picked.map((r) => r.student_enrollment));
		const listed = new Set((frm.doc.enrolled_students || []).map((r) => r.student_enrollment));
		const removed = enrolled.filter((r) => !keep.has(r.student_enrollment));
		removed.forEach((r) => frappe.model.clear_doc(r.doctype, r.name));
		const added = picked.filter((r) => !listed.has(r.student_enrollment));
		added.forEach((r) => frm.add_child("enrolled_students", {
			student_enrollment: r.student_enrollment,
			student_name: r.student_name,
			section: r.section,
			status: "Enrolled",
		}));
		if (!added.length && !removed.length) return;
		frm.refresh_field("enrolled_students");
		frm.save().then(() => frappe.show_alert({
			message: __("{0} student(s) added, {1} removed.", [added.length, removed.length]),
			indicator: "green",
		}));
	});
}
