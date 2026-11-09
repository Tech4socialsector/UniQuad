frappe.pages['applicant_dashboard'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Applicant Dashboard'),
        single_column: true
    });

    new ApplicantDashboard(wrapper);
}

class ApplicantDashboard {
    constructor(wrapper) {
        this.wrapper = $(wrapper);
        this.page = wrapper.page;
        this.init();
    }

    init() {
        this.fetch_data();
    }

    fetch_data() {
        let me = this;
        frappe.call({
            method: 'slcm.admission.page.applicant_dashboard.applicant_dashboard.get_dashboard_data',
            callback: function (r) {
                if (r.message && !r.message.error) {
                    if (r.message.no_application) {
                        me.render_no_application();
                    } else {
                        me.render(r.message);
                    }
                } else {
                    me.render_error(r.message ? r.message.error : "Unknown Error");
                }
            }
        });
    }

    render(data) {
        let me = this;
        const { applicant, campus_status, pending_actions, documents, deadlines, completion } = data;

        let html = `
            <div class="dashboard-container p-4">
                <!-- Header Card -->
                <div class="card mb-4 border-0 shadow-sm text-white" style="background: linear-gradient(135deg, #1f4e79 0%, #2e6a9e 100%);">
                    <div class="card-body p-4">
                        <div class="row align-items-center">
                            <div class="col-md-8">
                                <h2 class="mb-1 fw-bold text-white">${applicant.candidate_name}</h2>
                                <p class="mb-2 opacity-75">Application ID: ${applicant.name || 'N/A'}</p>
                                <div class="d-flex align-items-center mt-3">
                                    <span class="badge rounded-pill bg-white text-primary px-3 py-2 me-3 fw-bold">
                                        ${applicant.status}
                                    </span>
                                    <span class="text-white-50">${applicant.program} | ${applicant.application_type}</span>
                                </div>
                            </div>
                            <div class="col-md-4 text-md-end mt-3 mt-md-0">
                                <div class="completion-info">
                                    <p class="mb-2 small fw-bold text-uppercase">Profile Completion</p>
                                    <div class="progress mb-1" style="height: 8px; background: rgba(255,255,255,0.2);">
                                        <div class="progress-bar bg-success" style="width: ${completion}%"></div>
                                    </div>
                                    <span class="h4 fw-bold text-white">${completion}%</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="row">
                    <!-- Left Column -->
                    <div class="col-md-6">
                        <!-- Pending Actions -->
                        <div class="card mb-4 border-0 shadow-sm">
                            <div class="card-header bg-white border-0 pt-4 px-4 pb-0">
                                <h5 class="fw-bold"><i class="fa fa-bolt me-2 text-warning"></i> ${__('Pending Actions')}</h5>
                            </div>
                            <div class="card-body p-4">
                                ${pending_actions.length > 0 ? pending_actions.map(action => `
                                    <div class="action-item d-flex align-items-center p-3 mb-3 rounded border-start border-4 ${this.get_action_bg(action.type)}">
                                        <div class="icon-box me-3 h4 mb-0">
                                            <i class="${action.icon}"></i>
                                        </div>
                                        <div class="flex-grow-1">
                                            <h6 class="mb-1 fw-bold text-dark">${action.action}</h6>
                                            <p class="mb-0 small text-muted">${action.description}</p>
                                        </div>
                                        <a href="${action.url}" class="btn btn-sm btn-primary ms-2">${__('Go')}</a>
                                    </div>
                                `).join('') : `
                                    <div class="text-center py-4">
                                        <i class="fa fa-check-circle text-success display-4 mb-2"></i>
                                        <p class="text-muted">${__('All caught up! No pending actions.')}</p>
                                    </div>
                                `}
                            </div>
                        </div>

                        <!-- Document Checklist -->
                        <div class="card mb-4 border-0 shadow-sm">
                            <div class="card-header bg-white border-0 pt-4 px-4 pb-0">
                                <h5 class="fw-bold"><i class="fa fa-file-text me-2 text-primary"></i> ${__('Document Checklist')}</h5>
                            </div>
                            <div class="card-body p-4">
                                <div class="list-group list-group-flush">
                                    ${documents.map(doc => `
                                        <div class="list-group-item px-0 py-3 d-flex justify-content-between align-items-center border-bottom">
                                            <div>
                                                <h6 class="mb-0 fw-bold text-dark">${__(doc.document_type)}</h6>
                                            </div>
                                            <div>
                                                ${doc.verified ?
                `<span class="text-success small fw-bold"><i class="fa fa-check-circle me-1"></i> ${__('Verified')}</span>` :
                (doc.uploaded ?
                    `<span class="text-warning small fw-bold"><i class="fa fa-clock-o me-1"></i> ${__('Pending Verification')}</span>` :
                    `<span class="text-danger small fw-bold"><i class="fa fa-times-circle me-1"></i> ${__('Missing')}</span>`
                )
            }
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                                <div class="mt-4 text-center">
                                    <button class="btn btn-outline-primary btn-sm px-4" onclick="frappe.set_route('List', 'Applicant Document', {applicant: '${applicant.name}'})">
                                        ${__('Manage Documents')}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Right Column -->
                    <div class="col-md-6">
                        <!-- Campus Status -->
                        <div class="card mb-4 border-0 shadow-sm">
                            <div class="card-header bg-white border-0 pt-4 px-4 pb-0">
                                <h5 class="fw-bold"><i class="fa fa-university me-2 text-info"></i> ${__('Campus Status')}</h5>
                            </div>
                            <div class="card-body p-4">
                                ${campus_status.length > 0 ? campus_status.map(cs => `
                                    <div class="status-card p-3 mb-3 border rounded shadow-xs">
                                        <div class="d-flex justify-content-between align-items-start mb-2">
                                            <div>
                                                <h6 class="mb-0 fw-bold text-primary">${cs.campus}</h6>
                                                <span class="small text-muted">${__('Preference')} ${cs.preference_order} | ${cs.program}</span>
                                            </div>
                                            <span class="badge ${this.get_status_badge_class(cs.status)} px-3 py-2">
                                                ${cs.status}
                                            </span>
                                        </div>
                                        ${cs.acceptance_deadline ? `
                                            <div class="mt-2 text-danger small fw-bold">
                                                <i class="fa fa-exclamation-triangle me-1"></i> ${__('Accept before')}: ${frappe.datetime.str_to_user(cs.acceptance_deadline)}
                                            </div>
                                        ` : ''}
                                    </div>
                                `).join('') : `
                                    <p class="text-muted text-center py-4">${__('No campus preferences found.')}</p>
                                `}
                            </div>
                        </div>

                        <!-- Upcoming Deadlines -->
                        <div class="card mb-4 border-0 shadow-sm">
                            <div class="card-header bg-white border-0 pt-4 px-4 pb-0">
                                <h5 class="fw-bold"><i class="fa fa-calendar me-2 text-danger"></i> ${__('Deadlines & Rounds')}</h5>
                            </div>
                            <div class="card-body p-4">
                                ${deadlines.length > 0 ? deadlines.map(d => `
                                    <div class="deadline-item p-3 mb-3 rounded border-start border-4 ${d.status === 'Active' ? 'border-success bg-light-success' : 'bg-light'}">
                                        <div class="d-flex justify-content-between align-items-center">
                                            <div>
                                                <h6 class="mb-1 fw-bold text-dark">${d.round_name}</h6>
                                                <p class="mb-0 small text-muted">${d.round_type}</p>
                                            </div>
                                            <div class="text-end">
                                                <p class="mb-0 fw-bold text-dark">${frappe.datetime.str_to_user(d.application_end)}</p>
                                                <span class="small ${d.status === 'Active' ? 'text-success fw-bold' : 'text-primary'}">${d.status}</span>
                                            </div>
                                        </div>
                                    </div>
                                `).join('') : `
                                    <p class="text-muted text-center py-4">${__('No active deadlines at this time.')}</p>
                                `}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.wrapper.html(html);
    }

    get_action_bg(type) {
        const map = {
            'warning': 'bg-light-warning border-warning',
            'success': 'bg-light-success border-success',
            'info': 'bg-light-info border-info',
            'primary': 'bg-light-primary border-primary'
        };
        return map[type] || 'bg-light border-secondary';
    }

    get_status_badge_class(status) {
        const map = {
            'Offered': 'badge-success bg-success-subtle text-success',
            'Accepted': 'badge-primary bg-primary-subtle text-primary',
            'Rejected': 'badge-danger bg-danger-subtle text-danger',
            'Shortlisted': 'badge-warning bg-warning-subtle text-warning',
            'Under Evaluation': 'badge-info bg-info-subtle text-info',
            'Waitlisted': 'badge-secondary bg-secondary-subtle text-secondary'
        };
        return map[status] || 'badge-light bg-light text-dark';
    }

    render_no_application() {
        this.wrapper.html(`
            <div class="text-center p-5">
                <i class="fa fa-folder-open-o display-1 text-light mb-4" style="font-size: 80px;"></i>
                <h3 class="fw-bold">${__('No Application Found')}</h3>
                <p class="text-muted lead">${__('It seems you haven\'t started your application process yet.')}</p>
                <div class="mt-4">
                    <button class="btn btn-primary px-5 py-3 fw-bold" onclick="frappe.new_doc('Applicant')">
                        ${__('Start New Application')}
                    </button>
                </div>
            </div>
        `);
    }

    render_error(error) {
        this.wrapper.html(`
            <div class="alert alert-danger m-5">
                <h4 class="alert-heading fw-bold">${__('Error')}</h4>
                <p>${error}</p>
                <hr>
                <button class="btn btn-outline-danger btn-sm" onclick="location.reload()">
                    <i class="fa fa-refresh me-1"></i> ${__('Retry')}
                </button>
            </div>
        `);
    }
}
