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
	},

	class_type(frm) {
		frm.refresh();
	},

	academic_year(frm) {
		frm.set_value("academic_term", null);
	},
});

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
