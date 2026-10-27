// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Attendance Condonation", {
	refresh(frm) {
		fix_private_file_link(frm, "proof_document");

		if (frm.doc.final_status === "Pending" && frappe.session.user === frm.doc.aad_approver) {
			frm.add_custom_button("May Be Approve", () => {
				frappe.prompt(
					[{ fieldname: "remarks", fieldtype: "Small Text", label: "Remarks" }],
					(values) => {
						frm.call({
							method: "aad_decision",
							doc: frm.doc,
							args: { action: "approve", remarks: values.remarks, rejected_reason: null },
							callback: () => frm.reload_doc()
						});
					},
					"Approve Condonation",
					"Submit"
				);
			}, "AAD Decision");

			frm.add_custom_button("Reject", () => {
				frappe.prompt(
					[{ fieldname: "rejected_reason", fieldtype: "Small Text", label: "Rejected Reason", reqd: 1 }],
					(values) => {
						frm.call({
							method: "aad_decision",
							doc: frm.doc,
							args: { action: "reject", remarks: null, rejected_reason: values.rejected_reason },
							callback: () => frm.reload_doc()
						});
					},
					"Reject Condonation",
					"Submit"
				);
			}, "AAD Decision");
		}

		if (frm.doc.final_status === "May Be Approved" && frappe.session.user === frm.doc.programme_chair_approver) {
			frm.add_custom_button("Approve", () => {
				frappe.prompt(
					[{ fieldname: "remarks", fieldtype: "Small Text", label: "Remarks" }],
					(values) => {
						frm.call({
							method: "programme_chair_decision",
							doc: frm.doc,
							args: { action: "approve", remarks: values.remarks, rejected_reason: null },
							callback: () => frm.reload_doc()
						});
					},
					"Approve Condonation",
					"Submit"
				);
			}, "Programme Chair Decision");

			frm.add_custom_button("Reject", () => {
				frappe.prompt(
					[{ fieldname: "rejected_reason", fieldtype: "Small Text", label: "Rejected Reason", reqd: 1 }],
					(values) => {
						frm.call({
							method: "programme_chair_decision",
							doc: frm.doc,
							args: { action: "reject", remarks: null, rejected_reason: values.rejected_reason },
							callback: () => frm.reload_doc()
						});
					},
					"Reject Condonation",
					"Submit"
				);
			}, "Programme Chair Decision");
		}
	},
	proof_document(frm) {
		fix_private_file_link(frm, "proof_document");
	},
	student(frm) {
		if (frm.doc.student) {
			// Student Master.master_programme was removed: it was the student's
			// Programme's program_name, so read that instead.
			frappe.db.get_value("Student Master", frm.doc.student, "programme_of_study", (r) => {
				if (r && r.programme_of_study) {
					frappe.db.get_value("Programme", r.programme_of_study, "program_name", (p) => {
						if (p && p.program_name) {
							frm.set_value("programme", p.program_name);
						}
					});
				}
			});
		} else {
			frm.set_value("programme", null);
		}
	}
});

function fix_private_file_link(frm, fieldname) {
	const file_url = frm.doc[fieldname];
	if (!file_url || !file_url.startsWith("/private/")) return;

	const download_url = `/api/method/frappe.utils.file_manager.download_file?file_url=${encodeURIComponent(file_url)}`;
	frm.fields_dict[fieldname].$wrapper.find("a").attr("href", download_url);
}
