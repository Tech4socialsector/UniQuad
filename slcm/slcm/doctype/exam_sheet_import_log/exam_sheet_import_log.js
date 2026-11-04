// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

// One import of an Excel sheet into an Exam Plan (written by the Exam Planner page)
frappe.ui.form.on('Exam Sheet Import Log', {
	refresh(frm) {
		frm.disable_save();
		if ((frm.doc.issues || []).length) {
			frm.add_custom_button(__('Download problems'), () => window.open(
				`/api/method/slcm.slcm.page.examination_planner.examination_planner.download_log_issues?log=${encodeURIComponent(frm.doc.name)}`));
		}
		if (frm.doc.exam_plan) {
			frm.add_custom_button(__('Open Exam Planner'), () => frappe.set_route('examination-planner', frm.doc.exam_plan));
		}
	},
});
