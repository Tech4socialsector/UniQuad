// Improvement Exam now lives in the Exam Planner (step 5, After results); this route
// stays so sidebar links and bookmarks keep working.
frappe.pages['improvement-exam'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __('Improvement Exam'), single_column: true });
};

frappe.pages['improvement-exam'].on_page_show = function () {
	frappe.flags.exam_planner_open = { step: 4, after_tab: 'improvement' };   // route_options are cleared by the router here
	frappe.set_route('examination-planner');
};
