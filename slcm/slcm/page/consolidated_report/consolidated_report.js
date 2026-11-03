// Consolidated Report: the sidebar's way to the Excel download. The form is the
// shared dialog (slcm.exam_ui.consolidated_report); it opens on arrival.
frappe.pages['consolidated-report'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Consolidated Report'), single_column: true });
	$(wrapper).addClass('er-theme');
	frappe.require('/assets/slcm/css/exam_results_theme.css');
	$(page.main).html(`
		<div style="max-width:640px;margin:24px auto;padding:20px 22px;border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg);font-family:var(--er-font, Georgia, serif);">
			<h4 style="margin:0 0 6px;font-weight:700;">${__('Consolidated Report')}</h4>
			<p style="margin:0 0 14px;color:var(--text-muted);">${__('One Excel file of student results. Filter by exam plan, academic year, programme, term or batch, for all courses or one course.')}</p>
			<button class="btn btn-primary btn-sm cr-open">${__('Choose filters and download')}</button>
		</div>`);
	const open = () => frappe.require('/assets/slcm/js/exam/common.js', () => {
		let plan = null;
		try { plan = localStorage.getItem('xp-last-plan'); } catch (e) { /* storage blocked */ }
		slcm.exam_ui.consolidated_report(plan);
	});
	$(page.main).find('.cr-open').on('click', open);
	wrapper.cr_open = open;
};

frappe.pages['consolidated-report'].on_page_show = function (wrapper) {
	if (wrapper.cr_open) wrapper.cr_open();
};
