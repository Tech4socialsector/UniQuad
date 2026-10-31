frappe.pages['admission-setup-wizard'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Admission Setup Wizard',
        single_column: true
    });

    const $body = $(wrapper).find('.layout-main-section');

    const steps = [
        { id: 'institution', title: 'Institution Profile', description: 'Enter your institution name, code, and compliance settings.' },
        { id: 'campus',      title: 'Campus Mode',         description: 'Choose single campus or multi-campus mode.' },
        { id: 'portal',      title: 'Portal Configuration', description: 'Set your portal title, colors, and branding.' },
        { id: 'complete',    title: 'Review and Activate',  description: 'Review your setup and go live.' }
    ];

    let currentStep = 0;
    const data = {};

    async function init() {
        // Load initial data
        const inst = await frappe.db.get_doc('Institution Settings', 'Institution Settings');
        const portal = await frappe.db.get_doc('Applicant Portal Config', 'Applicant Portal Config');
        
        Object.assign(data, {
            institution_name: inst.institution_name,
            institution_code: inst.institution_code,
            compliance_mode: inst.compliance_mode,
            support_email: inst.support_email,
            multi_campus: inst.enable_multi_campus === 1,
            max_campus_preferences: inst.max_campus_preferences || 3,
            portal_title: portal.portal_title,
            portal_subtitle: portal.portal_subtitle,
            primary_color: portal.primary_color || '#1a237e',
            hero_image: portal.hero_image,
            footer_text: portal.footer_text
        });
        
        render();
    }

    function render() {
        const step = steps[currentStep];
        const progressPct = Math.round((currentStep / (steps.length - 1)) * 100);

        const stepNav = steps.map((s, i) => `
            <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;
                border-radius:var(--border-radius);margin-bottom:4px;
                background:${i === currentStep ? 'var(--bg-blue)' : 'transparent'};
                cursor:${i < currentStep ? 'pointer' : 'default'}"
                ${i < currentStep ? `class="wizard-step-nav" data-step="${i}"` : ''}>
                <div style="width:24px;height:24px;border-radius:50%;
                    background:${i < currentStep ? 'var(--green)' : i === currentStep ? 'var(--primary)' : 'var(--border-color)'};
                    color:#fff;display:flex;align-items:center;justify-content:center;
                    font-size:11px;font-weight:700;flex-shrink:0">
                    ${i < currentStep ? '&#10003;' : i + 1}
                </div>
                <div style="font-size:13px;font-weight:${i === currentStep ? '600' : '400'};
                    color:${i === currentStep ? 'var(--text-color)' : 'var(--text-muted)'}">
                    ${s.title}
                </div>
            </div>`).join('');

        $body.html(`
            <div style="max-width:900px;margin:0 auto;padding:20px;display:flex;gap:24px;flex-wrap:wrap;">
                <!-- Sidebar -->
                <div style="width:220px;flex-shrink:0;">
                    <div class="frappe-card" style="padding:16px;">
                        <div style="font-size:12px;font-weight:600;color:var(--text-muted);
                            text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px;">
                            Steps
                        </div>
                        ${stepNav}
                    </div>
                </div>
                <!-- Main content -->
                <div style="flex:1;min-width:300px;">
                    <div class="frappe-card" style="padding:28px;">
                        <div style="margin-bottom:8px;">
                            <span class="indicator-pill blue" style="font-size:11px">
                                Step ${currentStep + 1} of ${steps.length}
                            </span>
                        </div>
                        <h4 style="margin:8px 0 6px">${step.title}</h4>
                        <p class="text-muted" style="font-size:13px;margin-bottom:20px">${step.description}</p>
                        <div style="height:3px;background:var(--border-color);border-radius:3px;margin-bottom:24px;">
                            <div style="height:3px;width:${progressPct}%;background:var(--primary);
                                border-radius:3px;transition:width 0.3s;"></div>
                        </div>
                        <div id="step-body">${renderStepBody(step.id)}</div>
                        <div style="display:flex;justify-content:space-between;margin-top:24px;padding-top:16px;
                            border-top:1px solid var(--border-color);">
                            ${currentStep > 0
                                ? '<button class="btn btn-default" id="btn-prev">Previous</button>'
                                : '<div></div>'}
                            ${currentStep < steps.length - 1
                                ? '<button class="btn btn-primary" id="btn-next">Save and Continue</button>'
                                : '<button class="btn btn-success" id="btn-finish">Complete Setup</button>'}
                        </div>
                    </div>
                </div>
            </div>
        `);

    // Events
    $body.find('#btn-next').on('click', async () => { if (await collectStep()) { currentStep++; render(); } });
    $body.find('#btn-prev').on('click', () => { currentStep--; render(); });
    $body.find('#btn-finish').on('click', finishSetup);
    $body.find('.wizard-step-nav').on('click', async function() {
        const targetStep = parseInt($(this).data('step'));
        if (targetStep > currentStep) {
            if (await collectStep()) {
                currentStep = targetStep;
                render();
            }
        } else {
            currentStep = targetStep;
            render();
        }
    });
}

    function renderStepBody(stepId) {
        if (stepId === 'institution') {
            return `
                <div class="form-group">
                    <label class="control-label">Institution Name <span class="text-danger">*</span></label>
                    <input type="text" class="form-control" id="inst-name"
                        value="${data.institution_name || ''}" placeholder="e.g. National Law School of India University">
                </div>
                <div class="form-group">
                    <label class="control-label">Institution Code <span class="text-danger">*</span></label>
                    <input type="text" class="form-control" id="inst-code"
                        value="${data.institution_code || ''}" placeholder="e.g. NLSIU">
                </div>
                <div class="form-group">
                    <label class="control-label">Compliance Mode</label>
                    <select class="form-control" id="compliance-mode">
                        <option value="India" ${data.compliance_mode === 'India' ? 'selected' : ''}>India (RTI / NAAC / UGC)</option>
                        <option value="International" ${data.compliance_mode === 'International' ? 'selected' : ''}>International (GDPR)</option>
                        <option value="Both" ${data.compliance_mode === 'Both' ? 'selected' : ''}>Both</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="control-label">Support Email</label>
                    <input type="email" class="form-control" id="support-email"
                        value="${data.support_email || ''}" placeholder="admissions@yourinstitution.edu">
                </div>`;
        }

        if (stepId === 'campus') {
            return `
                <div class="form-group">
                    <label class="control-label">Campus Mode</label>
                    <div style="margin-top:8px;display:flex;flex-direction:column;gap:10px;">
                        <label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer;
                            padding:14px;border:1px solid var(--border-color);border-radius:var(--border-radius);
                            ${!data.multi_campus ? 'border-color:var(--primary);background:var(--bg-blue);' : ''}">
                            <input type="radio" name="campus-mode" value="0"
                                ${!data.multi_campus ? 'checked' : ''} style="margin-top:3px;flex-shrink:0">
                            <div>
                                <div style="font-weight:600">Single Campus</div>
                                <div class="text-muted" style="font-size:12px;margin-top:2px">
                                    All admissions managed at one location. Campus fields are hidden throughout.
                                </div>
                            </div>
                        </label>
                        <label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer;
                            padding:14px;border:1px solid var(--border-color);border-radius:var(--border-radius);
                            ${data.multi_campus ? 'border-color:var(--primary);background:var(--bg-blue);' : ''}">
                            <input type="radio" name="campus-mode" value="1"
                                ${data.multi_campus ? 'checked' : ''} style="margin-top:3px;flex-shrink:0">
                            <div>
                                <div style="font-weight:600">Multi Campus</div>
                                <div class="text-muted" style="font-size:12px;margin-top:2px">
                                    Applicants select campus preferences. Seat matrices and merit lists are campus-specific.
                                </div>
                            </div>
                        </label>
                    </div>
                </div>
                <div class="form-group" id="max-prefs-group" style="${data.multi_campus ? '' : 'display:none'}">
                    <label class="control-label">Max Campus Preferences per Applicant</label>
                    <input type="number" class="form-control" id="max-prefs"
                        value="${data.max_campus_preferences || 3}" min="1" max="10" style="width:120px">
                </div>`;
        }

        if (stepId === 'portal') {
            return `
                <div class="form-group">
                    <label class="control-label">Portal Title <span class="text-danger">*</span></label>
                    <input type="text" class="form-control" id="portal-title"
                        value="${data.portal_title || ''}" placeholder="e.g. NLSIU Admissions Portal">
                </div>
                <div class="form-group">
                    <label class="control-label">Portal Subtitle</label>
                    <input type="text" class="form-control" id="portal-subtitle"
                        value="${data.portal_subtitle || ''}" placeholder="e.g. Applications open for 2026-27">
                </div>
                <div class="row">
                    <div class="col-sm-6">
                        <div class="form-group">
                            <label class="control-label">Primary Color</label>
                            <input type="color" class="form-control" id="portal-color"
                                value="${data.primary_color || '#1a237e'}" style="height:42px;padding:4px;">
                        </div>
                    </div>
                    <div class="col-sm-6">
                        <div class="form-group">
                            <label class="control-label">Hero / Banner Image</label>
                            <input type="text" class="form-control" id="portal-hero"
                                value="${data.hero_image || ''}" placeholder="Paste image URL or upload via Portal Config">
                        </div>
                    </div>
                </div>
                <div class="form-group">
                    <label class="control-label">Footer Text</label>
                    <input type="text" class="form-control" id="portal-footer"
                        value="${data.footer_text || ''}" placeholder="e.g. 2026 NLSIU. All rights reserved.">
                </div>`;
        }

        if (stepId === 'complete') {
            const items = [
                { label: 'Programs & Courses', doctype: 'Programme', description: 'Add programs offered by your institution' },
                { label: 'Exam Types', doctype: 'Exam Type Config', description: 'Configure CLAT, NLSAT, or custom exams' },
                { label: 'Document Requirements', doctype: 'Document Requirement Config', description: 'Define required documents per program' },
                { label: 'Fee Structure', doctype: 'Fee Structure Config', description: 'Set application and acceptance fees' },
                { label: 'Email Templates', doctype: 'Email Template Config', description: 'Customize notification emails' },
                { label: 'Application Forms', doctype: 'Application Form Config', description: 'Build application forms per program' }
            ];

            const summaryHtml = `
                <div class="alert alert-success" style="font-size:13px">
                    Your institution profile, campus mode, and portal configuration have been saved.
                    You can now complete the remaining configuration from the Admission workspace.
                </div>
                <h6 style="margin-bottom:12px">Configure these next:</h6>
                ${items.map(item => `
                    <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;
                        border:1px solid var(--border-color);border-radius:var(--border-radius);
                        margin-bottom:8px;background:var(--card-bg);">
                        <div style="flex:1">
                            <div style="font-weight:600;font-size:13px">${item.label}</div>
                            <div class="text-muted" style="font-size:12px">${item.description}</div>
                        </div>
                        <a href="/app/${item.doctype.toLowerCase().replace(/ /g,'-')}"
                            class="btn btn-default btn-xs" target="_blank">Open</a>
                    </div>`).join('')}
                <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border-color);">
                    <button class="btn btn-default btn-sm" id="preview-portal-btn">Preview Portal</button>
                </div>`;

            setTimeout(() => {
                $body.find('#preview-portal-btn').on('click', () => window.open('/applicant-portal', '_blank'));
            }, 100);

            return summaryHtml;
        }

        return '';
    }

    async function collectStep() {
        const stepId = steps[currentStep].id;
        if (stepId === 'institution') {
            const name = $('#inst-name').val().trim();
            const code = $('#inst-code').val().trim();
            if (!name) { frappe.show_alert({ message: 'Institution Name is required.', indicator: 'red' }, 4); return false; }
            if (!code) { frappe.show_alert({ message: 'Institution Code is required.', indicator: 'red' }, 4); return false; }
            data.institution_name = name;
            data.institution_code = code;
            data.compliance_mode = $('#compliance-mode').val();
            data.support_email = $('#support-email').val();
            // Save to Institution Settings
            await frappe.call({ method: 'frappe.client.set_value', args: {
                doctype: 'Institution Settings', name: 'Institution Settings',
                fieldname: { institution_name: name, institution_code: code,
                    compliance_mode: data.compliance_mode, support_email: data.support_email }
            }});
        }
        if (stepId === 'campus') {
            data.multi_campus = $('input[name="campus-mode"]:checked').val() === '1';
            data.max_campus_preferences = parseInt($('#max-prefs').val()) || 3;
            await frappe.call({ method: 'frappe.client.set_value', args: {
                doctype: 'Institution Settings', name: 'Institution Settings',
                fieldname: { enable_multi_campus: data.multi_campus ? 1 : 0,
                    max_campus_preferences: data.max_campus_preferences }
            }});
        }
        if (stepId === 'portal') {
            const title = $('#portal-title').val().trim();
            if (!title) { frappe.show_alert({ message: 'Portal Title is required.', indicator: 'red' }, 4); return false; }
            data.portal_title = title;
            data.portal_subtitle = $('#portal-subtitle').val();
            data.primary_color = $('#portal-color').val();
            data.hero_image = $('#portal-hero').val();
            data.footer_text = $('#portal-footer').val();
            await frappe.call({ method: 'frappe.client.set_value', args: {
                doctype: 'Applicant Portal Config', name: 'Applicant Portal Config',
                fieldname: { portal_title: data.portal_title, portal_subtitle: data.portal_subtitle,
                    primary_color: data.primary_color, hero_image: data.hero_image,
                    footer_text: data.footer_text }
            }});
        }
        return true;
    }

    async function finishSetup() {
        await frappe.call({ method: 'frappe.client.set_value', args: {
            doctype: 'Institution Settings', name: 'Institution Settings',
            fieldname: { onboarding_complete: 1 }
        }});
        frappe.show_alert({ message: 'Setup complete. Welcome!', indicator: 'green' }, 5);
        setTimeout(() => frappe.set_route('admission'), 1500);
    }

    // Bind campus mode radio change
    $(document).on('change', 'input[name="campus-mode"]', function() {
        const multi = $(this).val() === '1';
        $('#max-prefs-group').toggle(multi);
        $('input[name="campus-mode"]').closest('label').css({
            'border-color': 'var(--border-color)', 'background': ''
        });
        $(this).closest('label').css({
            'border-color': 'var(--primary)', 'background': 'var(--bg-blue)'
        });
    });

    init();
};
