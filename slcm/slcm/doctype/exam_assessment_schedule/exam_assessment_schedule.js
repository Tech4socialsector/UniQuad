// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

const EAS_PATH = 'slcm.slcm.doctype.exam_assessment_schedule.exam_assessment_schedule';

frappe.ui.form.on('Exam Assessment Schedule', {
	setup(frm) {
		frm.set_query('term', () => ({
			filters: frm.doc.academic_year ? { academic_year: frm.doc.academic_year } : {}
		}));

		frm.set_query('programme', () => ({
			query: `${EAS_PATH}.programme_query`,
			filters: { term: frm.doc.term }
		}));

		frm.set_query('exam_plan', () => ({
			filters: frm.doc.term ? { term: frm.doc.term } : {}
		}));

		frm.set_query('course', 'assessments', () => ({
			query: `${EAS_PATH}.course_query`,
			filters: { programme: frm.doc.programme, term: frm.doc.term }
		}));

		frm.set_query('component', 'assessments', () => ({ filters: { is_active: 1 } }));
		frm.set_query('assessment_type', 'assessments', () => ({ filters: { is_active: 1 } }));
	},

	refresh(frm) {
		frm.add_custom_button(__('Fetch Assessments from Schema'), () => eas_fetch_assessments(frm));
	},

	academic_year(frm) {
		frm.set_value('term', '');
	},

	term(frm) {
		frm.set_value('programme', '');
		frm.set_value('exam_plan', '');
		if (!frm.doc.term) return;

		// Pre-select the term's Exam Plan when there is only one
		frappe.db.get_list('Exam Plan', { filters: { term: frm.doc.term, status: 'Active' }, limit: 2 }).then(plans => {
			if (plans.length === 1) frm.set_value('exam_plan', plans[0].name);
		});
	}
});

function eas_fetch_assessments(frm) {
	if (!frm.doc.programme || !frm.doc.term) {
		frappe.msgprint(__('Select Term and Programme first.'));
		return;
	}

	frappe.call({
		method: `${EAS_PATH}.get_schema_assessments`,
		args: { programme: frm.doc.programme, term: frm.doc.term, exam_plan: frm.doc.exam_plan },
		freeze: true,
		freeze_message: __('Fetching assessments…'),
		callback: r => {
			const { rows = [], missing_schema = [] } = r.message || {};

			// Skip rows already in the table, so dates entered earlier are kept
			const existing = new Set(
				(frm.doc.assessments || []).map(d => `${d.course}::${(d.assessment_label || '').trim().toLowerCase()}`)
			);
			let added = 0;
			rows.forEach(row => {
				const key = `${row.course}::${(row.assessment_label || '').trim().toLowerCase()}`;
				if (existing.has(key)) return;
				frm.add_child('assessments', row);
				existing.add(key);
				added++;
			});
			frm.refresh_field('assessments');

			let msg = __('{0} assessment row(s) added.', [added]);
			if (missing_schema.length) {
				msg += '<br><br>' + __('No Evaluation Schema mapped for:') + '<br>• ' +
					missing_schema.map(frappe.utils.escape_html).join('<br>• ');
			}
			frappe.msgprint({ title: __('Fetch Assessments'), message: msg, indicator: added ? 'green' : 'orange' });
		}
	});
}
