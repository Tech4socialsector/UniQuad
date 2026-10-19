frappe.ui.form.on("Student Enrollment", {
	refresh(frm) {
		// Lightweight only - just keep the Section link filtered to this
		// batch. The auto-fill of enrolled_courses must NOT re-run here,
		// otherwise simply opening an existing enrollment would wipe out
		// any manually edited rows (grades, status, faculty overrides).
		frm.set_query("section", function () {
			return { filters: { batch: frm.doc.batch } };
		});

		// Only students who have completed the registration workflow
		// should be selectable for enrollment.
		frm.set_query("student", function () {
			return { filters: { registration_status: "Completed" } };
		});

		render_academic_timeline(frm);
	},

	batch(frm) {
		// Fires on real user-driven changes only (not on load), which is
		// exactly when we want to refill enrolled_courses for the new batch.
		frm.set_query("section", function () {
			return { filters: { batch: frm.doc.batch } };
		});

		// 1️⃣ Clear table if batch removed
		if (!frm.doc.batch) {
			frm.set_value("section", "");
			frm.clear_table("enrolled_courses");
			frm.refresh_field("enrolled_courses");
			return;
		}

		// 2️⃣ Clear existing rows before refilling
		frm.clear_table("enrolled_courses");

		const batch = frm.doc.batch;

		// 3️⃣ Fetch all Open Course Offerings for this batch directly
		// (Course Offering's own link field is still named "cohort")
		frappe.db.get_list("Course Offering", {
			filters: [["cohort", "=", batch], ["status", "=", "Active"]],
			fields: ["name", "course_title"],
		}).then((offerings) => {
			if (!offerings.length) {
				frm.refresh_field("enrolled_courses");
				return;
			}

			frappe.db.get_list("Course", {
				filters: [["name", "in", offerings.map(o => o.course_title)]],
				fields: ["name", "course_type"],
			}).then((courses) => {
				const course_type_map = {};
				courses.forEach(c => { course_type_map[c.name] = c.course_type; });

				offerings.forEach((offering) => {
					const row = frm.add_child("enrolled_courses");
					frappe.model.set_value(row.doctype, row.name, "course_offering", offering.name);
					frappe.model.set_value(row.doctype, row.name, "course", offering.course_title);
					frappe.model.set_value(row.doctype, row.name, "course_type", course_type_map[offering.course_title] || "");
					frappe.model.set_value(row.doctype, row.name, "status", "Enrolled");
				});

				frm.refresh_field("enrolled_courses");
			});
		});
	},
});

/*****************************************************
 * ACADEMIC TIMELINE
 * Replaces the old "Other Terms" dropdown (a plain list
 * of text-only buttons buried in the toolbar) with an
 * always-visible strip of term cards at the top of the
 * form, so a student's full enrollment history is
 * scannable at a glance instead of hidden in a menu.
 *****************************************************/
const TIMELINE_STATUS_COLOR = {
	Enrolled: { fg: "#1e7e34", bg: "#e6f4ea" },
	Completed: { fg: "#0d6efd", bg: "#e7f1ff" },
	Dropped: { fg: "#b02a37", bg: "#fdecea" },
	Pending: { fg: "#92400e", bg: "#fef3c7" },
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
		method: "slcm.slcm.doctype.student_enrollment.student_enrollment.get_other_terms",
		args: { student: frm.doc.student, exclude: null },
		callback(r) {
			const terms = r.message || [];
			if (terms.length <= 1) {
				// Nothing to navigate between - don't show a timeline of one.
				$wrapper.empty();
				return;
			}
			$wrapper.html(build_academic_timeline_html(terms, frm.doc.name));
			$wrapper.find(".timeline-term[data-name]").on("click", function () {
				const name = $(this).attr("data-name");
				if (name && name !== frm.doc.name) {
					frappe.set_route("Form", "Student Enrollment", name);
				}
			});
		},
	});
}

function build_academic_timeline_html(terms, current_name) {
	const cards = terms
		.map((term) => {
			const is_current = term.name === current_name;
			const color = TIMELINE_STATUS_COLOR[term.status] || { fg: "#475569", bg: "#f1f5f9" };
			return `
				<div class="timeline-term ${is_current ? "is-current" : ""}" data-name="${frappe.utils.escape_html(term.name)}"
					style="--term-fg:${color.fg}; --term-bg:${color.bg};">
					<div class="timeline-term-top">
						<span class="timeline-term-year">${frappe.utils.escape_html(term.academic_year || "—")}</span>
						${is_current ? `<span class="timeline-current-tag">${__("Viewing")}</span>` : ""}
					</div>
					<div class="timeline-term-name">${frappe.utils.escape_html(term.term_name || "—")}</div>
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
