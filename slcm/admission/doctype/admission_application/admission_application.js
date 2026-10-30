frappe.ui.form.on('Admission Application', {

    refresh(frm) {
        // Status badge color
        const colors = {
            'Draft':        'gray',
            'Submitted':    'blue',
            'Under Review': 'orange',
            'Shortlisted':  'yellow',
            'Offered':      'green',
            'Accepted':     'green',
            'Rejected':     'red',
            'Withdrawn':    'gray',
            'Waitlisted':   'orange',
        };
        if (frm.doc.status && colors[frm.doc.status]) {
            frm.set_indicator_formatter('status',
                () => colors[frm.doc.status]);
        }

        // Quick action buttons
        if (!frm.doc.__islocal && frm.doc.docstatus === 1) {
            frm.add_custom_button('Generate Offer Letter', () => {
                frappe.msgprint('Offer letter generation will be implemented in Module 9 (US-OF-118).');
            }, 'Actions');

            frm.add_custom_button('View Merit Score', () => {
                frappe.msgprint(`Merit Score: ${frm.doc.merit_score || 'Not calculated yet'}`);
            }, 'Actions');
        }
    },

    applicant(frm) {
        if (frm.doc.applicant) {
            frappe.db.get_value('Applicant', frm.doc.applicant,
                ['candidate_name', 'email', 'admission_cycle'],
                (r) => {
                    frm.set_value('applicant_name',  r.candidate_name || '');
                    frm.set_value('applicant_email', r.email || '');
                    if (r.admission_cycle && !frm.doc.admission_cycle) {
                        frm.set_value('admission_cycle', r.admission_cycle);
                    }
                }
            );
        }
    },

    program(frm) {
        if (frm.doc.program) {
            frappe.db.get_value('Programme', frm.doc.program,
                ['program_name'], (r) => {
                    frm.set_value('program_name', r.program_name || '');
                }
            );
        }
    },
});
