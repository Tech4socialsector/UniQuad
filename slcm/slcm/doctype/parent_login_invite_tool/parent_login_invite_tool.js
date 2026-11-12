// Parent Login Invite Tool
// Flow: 1. choose students (filters or Student Master list selection)
//       2. Get Students → review the overview + table
//       3. Send Invites (only Pending rows; one email per parent)

const PLIT_STATUS = {
	Pending: { color: "orange", hint: __("Will receive an invite") },
	Invited: { color: "green", hint: __("Invite sent") },
	"Already Exists": { color: "blue", hint: __("Has an account — skipped") },
	"No Email": { color: "grey", hint: __("No email on record") },
	"Invalid Email": { color: "red", hint: __("Fix the email on the Student Master") },
	Failed: { color: "red", hint: __("Sending failed — see Remarks") },
};
const PLIT_FILTERS = ["academic_year", "programme", "batch", "student_status", "selected_students", "resend_unactivated"];

frappe.ui.form.on("Parent Login Invite Tool", {
	setup(frm) {
		frm.set_query("batch", () => ({
			filters: frm.doc.academic_year ? { academic_year: frm.doc.academic_year } : {},
		}));
	},

	onload(frm) {
		const grid = frm.fields_dict.student_list.grid;
		grid.get_docfield("invite_status").formatter = (value) => plit_pill(value);
	},

	refresh(frm) {
		frm._plit_stale = false;
		plit_setup_actions(frm);
		plit_render_summary(frm);
		frm.set_intro(
			frm.doc.student_list?.length
				? ""
				: __("Choose students with the filters below (or pick them on the Student Master list → Action → Parent Login Invite), then click <b>Get Students</b>."),
			"blue"
		);
	},

	academic_year(frm) {
		if (frm.doc.batch) frm.set_value("batch", "");
		plit_mark_stale(frm);
	},
	programme: plit_mark_stale,
	batch: plit_mark_stale,
	student_status: plit_mark_stale,
	resend_unactivated: plit_mark_stale,
	selected_students: plit_mark_stale,
});

function plit_counts(frm) {
	const c = { total: 0 };
	(frm.doc.student_list || []).forEach((r) => {
		c.total++;
		c[r.invite_status] = (c[r.invite_status] || 0) + 1;
	});
	return c;
}

function plit_pending_parents(frm) {
	const emails = new Set();
	(frm.doc.student_list || []).forEach((r) => {
		if (r.invite_status === "Pending" && r.parent_email) emails.add(r.parent_email.toLowerCase());
	});
	return emails.size;
}

function plit_setup_actions(frm) {
	frm.clear_custom_buttons();
	if (frm.doc.selected_students) {
		frm.add_custom_button(__("Clear Selection"), () => frm.set_value("selected_students", ""));
	}
	frm.add_custom_button(__("Get Students"), () => plit_get_students(frm));
	if ((frm.doc.student_list || []).some((r) => r.email_queue)) {
		frm.add_custom_button(__("Check Delivery"), () => plit_check_delivery(frm));
	}

	const parents = plit_pending_parents(frm);
	if (parents && !frm._plit_stale && !frm.is_dirty()) {
		frm.page.set_primary_action(__("Send Invites ({0})", [parents]), () => plit_send(frm), "mail");
	} else {
		// fall back to the standard Save button
		frm.toolbar.set_primary_action();
	}
}

function plit_has_filters(frm) {
	return ["academic_year", "programme", "batch", "student_status", "selected_students"].some((f) => frm.doc[f]);
}

function plit_get_students(frm) {
	if (!plit_has_filters(frm)) {
		frappe.msgprint({
			title: __("Choose Students"),
			message: __("Set at least one filter (Academic Year, Programme, Batch or Student Status) first."),
			indicator: "orange",
		});
		return;
	}
	const run = () =>
		frm
			.call({ doc: frm.doc, method: "get_students", freeze: true, freeze_message: __("Fetching students and parents…") })
			.then((r) => {
				const c = r.message || {};
				frm._plit_stale = false;
				frappe.show_alert({
					message: __("{0} row(s) loaded — {1} pending invite(s).", [c.total || 0, c.Pending || 0]),
					indicator: c.Pending ? "green" : "blue",
				});
				return frm.reload_doc();
			});

	if (frm.is_new() || frm.is_dirty()) frm.save().then(run);
	else run();
}

function plit_send(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("You have unsaved changes. Click Get Students to refresh the list before sending."));
		return;
	}
	const parents = plit_pending_parents(frm);
	frappe.confirm(
		__("Create parent-portal accounts and email a set-password link to <b>{0}</b> parent(s)?<br><br><small class='text-muted'>Rows marked Already Exists, No Email or Invalid Email are skipped. Siblings sharing a parent get one combined email.</small>", [parents]),
		() =>
			frm
				.call({ doc: frm.doc, method: "send_invites", freeze: true, freeze_message: __("Sending invites…") })
				.then((r) => {
					const m = r.message || {};
					frappe.msgprint({
						title: m.failed_now ? __("Invites Sent with Errors") : __("Invites Sent"),
						indicator: m.failed_now ? "orange" : "green",
						message:
							__("<b>{0}</b> parent email(s) queued — one per parent.", [m.invited_now || 0]) +
							"<br><small class='text-muted'>" + __("Use <b>Check Delivery</b> in a minute to confirm each email left the mail server.") + "</small>" +
							(m.failed_now ? "<br>" + __("<b>{0}</b> failed — see the Remarks column and Error Log.", [m.failed_now]) : ""),
					});
					return frm.reload_doc();
				})
	);
}

function plit_check_delivery(frm) {
	frm.call({ doc: frm.doc, method: "check_delivery", freeze: true, freeze_message: __("Checking email queue…") })
		.then((r) => {
			const m = r.message || {};
			frappe.msgprint({
				title: __("Delivery Status"),
				indicator: m.Error ? "red" : m.Queued ? "orange" : "green",
				message: __("Sent: <b>{0}</b> · Waiting in queue: <b>{1}</b> · Failed: <b>{2}</b>", [m.Sent || 0, m.Queued || 0, m.Error || 0]) +
					(m.Error ? "<br>" + __("Failed rows show the mailer error in Remarks; fix the email/account and use Resend.") : ""),
			});
			return frm.reload_doc();
		});
}

function plit_mark_stale(frm) {
	if (!(frm.doc.student_list || []).length) return plit_setup_actions(frm);
	frm._plit_stale = true;
	plit_setup_actions(frm);
	plit_render_summary(frm);
}

function plit_pill(value) {
	if (!value) return "";
	const s = PLIT_STATUS[value] || { color: "grey" };
	return `<span class="indicator-pill ${s.color}" title="${frappe.utils.escape_html(s.hint || "")}">${__(value)}</span>`;
}

function plit_render_summary(frm) {
	const $w = frm.fields_dict.summary_html.$wrapper;
	const c = plit_counts(frm);

	if (!c.total) {
		$w.html(`<div class="text-muted small" style="padding:4px 0 8px">${__("No students loaded yet.")}</div>`);
		return;
	}

	const card = (label, value, color, hint) => `
		<div style="flex:1 1 130px;min-width:120px;border:1px solid var(--border-color);border-radius:var(--border-radius-md);
			padding:10px 14px;background:var(--card-bg)">
			<div class="small text-muted" style="display:flex;align-items:center;gap:6px">
				${color ? `<span class="indicator ${color}"></span>` : ""}${label}
			</div>
			<div style="font-size:20px;font-weight:600;margin-top:2px">${value}</div>
			${hint ? `<div class="small text-muted">${hint}</div>` : ""}
		</div>`;

	const students = new Set((frm.doc.student_list || []).map((r) => r.student)).size;
	let html = `<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:8px">`;
	html += card(__("Students"), students, "", __("{0} parent row(s)", [c.total]));
	Object.keys(PLIT_STATUS).forEach((st) => {
		if (c[st] || st === "Pending") html += card(__(st), c[st] || 0, PLIT_STATUS[st].color, PLIT_STATUS[st].hint);
	});
	html += `</div>`;

	if (frm._plit_stale) {
		html += `<div class="alert alert-warning small" style="margin:6px 0">${__("Filters changed — click <b>Get Students</b> to refresh the list before sending invites.")}</div>`;
	} else if (!c.Pending && !c.Failed) {
		html += `<div class="small text-muted">${__("Nothing left to send for this list.")}</div>`;
	}
	$w.html(html);
}
