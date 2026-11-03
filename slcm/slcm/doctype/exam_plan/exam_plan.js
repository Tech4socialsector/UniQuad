// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

// Course mapping, timetable, students, marks and results are all done in the
// Exam Planner page; the form only links there so there is one place to do each.
frappe.ui.form.on('Exam Plan', {
	refresh(frm) {
		if (frm.is_new()) return;
		const open_step = (step) => {
			frappe.route_options = { step };
			frappe.set_route('examination-planner', frm.doc.name);
		};
		frm.add_custom_button(__('Map courses in Exam Planner'), () => open_step(0))
			.removeClass('btn-default').addClass('btn-primary');
		frm.add_custom_button(__('Exam timetable'), () => open_step(1), __('Exam Planner'));
		frm.add_custom_button(__('Students'), () => open_step(2), __('Exam Planner'));
		frm.add_custom_button(__('Marks'), () => open_step(3), __('Exam Planner'));
		frm.add_custom_button(__('Results'), () => open_step(4), __('Exam Planner'));
		frm.set_intro(__('Map courses and schemas, and run this exam, in the {0}.',
			[`<a href="/desk/examination-planner/${encodeURIComponent(frm.doc.name)}">${__('Exam Planner')}</a>`]), 'blue');
	}
});

frappe.ui.form.on('Exam Course Schedule', {
	// Seats follow the venue's capacity; lower them by hand if fewer are usable
	venue(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.venue) return;
		frappe.db.get_value('Venue Master', row.venue, 'capacity').then((r) => {
			frappe.model.set_value(cdt, cdn, 'seat_capacity', (r.message && r.message.capacity) || 0);
		});
	},
});
