frappe.ui.form.on("Student Enrollment", {
	refresh(frm) {
		// The auto-fill of enrolled_courses must NOT re-run here, otherwise
		// simply opening an existing enrollment would wipe out any manually
		// edited rows (grades, status, faculty overrides).

		// Only students who have completed the registration workflow
		// should be selectable for enrollment.
		frm.set_query("student", function () {
			return { filters: { registration_status: "Completed" } };
		});

		// Terms in a log row belong to that row's academic year.
		frm.set_query("academic_term", "academic_log", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return { filters: row.academic_year ? { academic_year: row.academic_year } : {} };
		});

		render_academic_timeline(frm);

		const ongoing = (frm.doc.academic_log || []).find((r) => r.status === "Ongoing");
		if (!frm.is_new() && frm.doc.status === "Enrolled" && ongoing && frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Change Section"), () => open_change_section_dialog(frm, ongoing));
		}
	},
});

/*****************************************************
 * CHANGE SECTION
 * Section is read-only after creation: moves go through
 * here so they are logged on the Ongoing Academic Log
 * row (Upcoming rows follow the new section).
 *****************************************************/
function open_change_section_dialog(frm, ongoing) {
	const dialog = new frappe.ui.Dialog({
		title: __("Change Section"),
		fields: [
			{ fieldtype: "Link", fieldname: "academic_year", label: __("Academic Year"), options: "Academic Year",
				default: ongoing.academic_year, read_only: 1 },
			{ fieldtype: "Column Break" },
			{ fieldtype: "Link", fieldname: "academic_term", label: __("Academic Term"), options: "Academic Term",
				default: ongoing.academic_term, read_only: 1 },
			{ fieldtype: "Section Break" },
			{ fieldtype: "Link", fieldname: "from_section", label: __("From Section"), options: "Section",
				default: frm.doc.section, read_only: 1 },
			{ fieldtype: "Column Break" },
			{ fieldtype: "Link", fieldname: "to_section", label: __("To Section"), options: "Section", reqd: 1,
				get_query: () => ({ filters: frm.doc.section ? { name: ["!=", frm.doc.section] } : {} }) },
			{ fieldtype: "Section Break" },
			{ fieldtype: "Small Text", fieldname: "reason", label: __("Reason") },
			{ fieldtype: "HTML", options: `<div class="text-muted small">${__(
				"Applies from the current term: the Ongoing and Upcoming Academic Log rows move to the new section and the change is noted on the Ongoing row. Completed terms keep their section."
			)}</div>` },
		],
		primary_action_label: __("Change Section"),
		primary_action(values) {
			frappe.call({
				method: "slcm.slcm.doctype.student_enrollment.student_enrollment.change_section",
				args: { enrollment: frm.doc.name, to_section: values.to_section, reason: values.reason },
				freeze: true,
				freeze_message: __("Changing section..."),
				callback({ message }) {
					dialog.hide();
					frappe.show_alert({ message: (message && message.note) || __("Section changed"), indicator: "green" }, 6);
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

/*****************************************************
 * ACADEMIC TIMELINE
 * A strip of term cards at the top of the form, built
 * from the Academic Log, so the student's path through
 * the programme is scannable at a glance.
 *****************************************************/
const TIMELINE_STATUS_COLOR = {
	Ongoing: { fg: "#1e7e34", bg: "#e6f4ea" },
	Upcoming: { fg: "#92400e", bg: "#fef3c7" },
	Completed: { fg: "#0d6efd", bg: "#e7f1ff" },
	Redo: { fg: "#7c3aed", bg: "#f3e8ff" },
	Dropped: { fg: "#b02a37", bg: "#fdecea" },
};

function render_academic_timeline(frm) {
	const $wrapper = frm.get_field("academic_timeline_html").$wrapper;

	if (frm.is_new() || !frm.doc.student) {
		$wrapper.empty();
		return;
	}

	inject_academic_timeline_css();
	$wrapper.html(`<div class="academic-timeline academic-timeline-loading">${__("Loading academic timeline...")}</div>`);

	frappe.call({
		method: "slcm.slcm.doctype.student_enrollment.student_enrollment.get_academic_timeline",
		args: { enrollment: frm.doc.name },
		callback(r) {
			const terms = r.message || [];
			if (!terms.length) {
				$wrapper.empty();
				return;
			}
			$wrapper.html(build_academic_timeline_html(terms));
		},
	});
}

function build_academic_timeline_html(terms) {
	const cards = terms
		.map((term) => {
			const is_current = term.status === "Ongoing";
			const color = TIMELINE_STATUS_COLOR[term.status] || { fg: "#475569", bg: "#f1f5f9" };
			return `
				<div class="timeline-term ${is_current ? "is-current" : ""}"
					style="--term-fg:${color.fg}; --term-bg:${color.bg};">
					<div class="timeline-term-top">
						<span class="timeline-term-year">${frappe.utils.escape_html(term.academic_year || "—")}</span>
						${is_current ? `<span class="timeline-current-tag">${__("Current")}</span>` : ""}
					</div>
					<div class="timeline-term-name">${term.year_no ? __("Year {0}", [term.year_no]) : "—"}${
						term.term_name ? ` · ${frappe.utils.escape_html(term.term_name)}` : ""
					}</div>
					<span class="timeline-status-pill">${frappe.utils.escape_html(__(term.status))}</span>
				</div>
			`;
		})
		.join(`<div class="timeline-connector"></div>`);

	return `
		<div class="academic-timeline">
			<div class="academic-timeline-label">${__("Academic Timeline")}</div>
			<div class="academic-timeline-track">${cards}</div>
		</div>
	`;
}

function inject_academic_timeline_css() {
	if (document.getElementById("academic-timeline-css")) return;

	const style = document.createElement("style");
	style.id = "academic-timeline-css";
	style.innerHTML = `
		.academic-timeline-loading {
			font-size: 12.5px;
			color: #94a3b8;
			padding: 4px 0 12px;
		}
		.academic-timeline {
			margin: 4px 0 20px;
			padding-bottom: 16px;
			border-bottom: 1px solid #e2e8f0;
		}
		.academic-timeline-label {
			font-size: 11px;
			font-weight: 700;
			letter-spacing: 0.06em;
			text-transform: uppercase;
			color: #94a3b8;
			margin-bottom: 10px;
		}
		.academic-timeline-track {
			display: flex;
			align-items: stretch;
			overflow-x: auto;
			padding-bottom: 2px;
		}
		.timeline-connector {
			flex: 0 0 22px;
			align-self: center;
			height: 1px;
			background: #cbd5e1;
			margin-top: -12px;
		}
		.timeline-term {
			flex: 0 0 auto;
			min-width: 168px;
			border: 1px solid #e2e8f0;
			border-radius: 8px;
			padding: 10px 14px;
			cursor: pointer;
			background: #ffffff;
			transition: border-color 0.15s ease, box-shadow 0.15s ease;
		}
		.timeline-term:hover {
			border-color: var(--term-fg, #94a3b8);
			box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
		}
		.timeline-term.is-current {
			cursor: default;
			border-color: var(--term-fg, #1e293b);
			background: var(--term-bg, #f8fafc);
			box-shadow: 0 0 0 1px var(--term-fg, #1e293b);
		}
		.timeline-term-top {
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 8px;
			margin-bottom: 2px;
		}
		.timeline-term-year {
			font-size: 11.5px;
			font-weight: 600;
			color: #64748b;
		}
		.timeline-current-tag {
			font-size: 9.5px;
			font-weight: 700;
			letter-spacing: 0.04em;
			text-transform: uppercase;
			color: var(--term-fg, #1e293b);
		}
		.timeline-term-name {
			font-size: 13.5px;
			font-weight: 600;
			color: #1e293b;
			margin-bottom: 8px;
			white-space: nowrap;
		}
		.timeline-status-pill {
			display: inline-block;
			font-size: 10.5px;
			font-weight: 700;
			padding: 2px 9px;
			border-radius: 20px;
			color: var(--term-fg, #475569);
			background: var(--term-bg, #f1f5f9);
		}
	`;
	document.head.appendChild(style);
}
