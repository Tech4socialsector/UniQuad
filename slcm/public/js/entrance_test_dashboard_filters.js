/**
 * Global Filter Injection for Entrance Test Dashboard
 * This script provides a robust global filter bar for the Entrance Test dashboard.
 */

(function() {
	console.log("SLCM: Entrance Test Dashboard Filters script initialized");

	// 1. Monkey-patch get_all_filters to inject/override filters for Entrance Test widgets
	if (!frappe.dashboard_utils._slcm_entrance_test_patched) {
		const original_get_all_filters = frappe.dashboard_utils.get_all_filters;
		frappe.dashboard_utils.get_all_filters = function(doc) {
			let filters = original_get_all_filters.apply(this, arguments);
			
			const route = frappe.get_route();
			if (route && route[0] === 'dashboard-view' && (route[1] === 'Entrance Test Dashboard' || route[1] === 'Entrance Test') && frappe._entrance_test_dashboard_filters) {
				const global = frappe._entrance_test_dashboard_filters;
				const target_doctype = doc.document_type || (doc.report_name ? 'Entrance Test Seat Allocation' : null);
				
				if (target_doctype) {
					if (Array.isArray(filters)) {
						// Handle Standard DocType Filters (Arrays)
						apply_array_filters(filters, target_doctype, global);
					} else {
						// Handle Report/Object Filters (Objects)
						if (!filters) filters = {};
						apply_object_filters(filters, target_doctype, global, doc.report_name);
					}
				}
			}
			return filters;
		};
		frappe.dashboard_utils._slcm_entrance_test_patched = true;
	}

	function apply_array_filters(filters, doctype, global) {
		const upsert = (fieldname, op, value) => {
			if (!fieldname) return;
			let found = false;
			for (let i = 0; i < filters.length; i++) {
				if (Array.isArray(filters[i]) && filters[i][1] === fieldname) {
					filters[i] = [doctype, fieldname, op, value];
					found = true;
					break;
				}
			}
			if (!found) filters.push([doctype, fieldname, op, value]);
		};

		const remove = (fieldname) => {
			if (!fieldname) return;
			for (let i = filters.length - 1; i >= 0; i--) {
				if (Array.isArray(filters[i]) && filters[i][1] === fieldname) {
					filters.splice(i, 1);
				}
			}
		};

		if (global.academic_year) upsert('academic_year', '=', global.academic_year); else remove('academic_year');
		if (global.admission_cycle) upsert('admission_cycle', '=', global.admission_cycle); else remove('admission_cycle');
		if (global.campus) upsert('campus', '=', global.campus); else remove('campus');
		if (global.program) upsert('program', '=', global.program); else remove('program');

		if (global.is_international_applicant) {
			upsert('is_international_applicant', '=', 1);
			remove('entrance_test_provider');
		} else {
			remove('is_international_applicant');
			if (global.entrance_test_provider) {
				upsert('entrance_test_provider', '=', global.entrance_test_provider);
			} else {
				remove('entrance_test_provider');
			}
		}
	}

	function apply_object_filters(filters, doctype, global, report_name) {
		if (global.academic_year) {
			filters.academic_year = global.academic_year;
		} else {
			delete filters.academic_year;
		}

		if (global.admission_cycle) {
			filters.admission_cycle = global.admission_cycle;
		} else {
			delete filters.admission_cycle;
		}

		if (global.campus) {
			filters.campus = global.campus;
		} else {
			delete filters.campus;
		}

		if (global.program) {
			filters.program = global.program;
		} else {
			delete filters.program;
		}

		if (global.is_international_applicant) {
			filters.is_international_applicant = 1;
			delete filters.entrance_test_provider;
		} else {
			delete filters.is_international_applicant;
			if (global.entrance_test_provider) {
				filters.entrance_test_provider = global.entrance_test_provider;
			} else {
				delete filters.entrance_test_provider;
			}
		}
	}

	// 2. Dashboard Integration Logic
	let filter_check_interval = setInterval(() => {
		const route = frappe.get_route();
		if (route && route[0] === 'dashboard-view' && (route[1] === 'Entrance Test Dashboard' || route[1] === 'Entrance Test')) {
			let dashboard = frappe.dashboard;
			if (!dashboard && cur_page && cur_page.page.dashboard) {
				dashboard = cur_page.page.dashboard;
			}

			if (dashboard && (dashboard.dashboard_name === 'Entrance Test Dashboard' || dashboard.name === 'Entrance Test Dashboard' || dashboard.name === 'Entrance Test')) {
				if (!dashboard.$filter_bar) {
					render_entrance_test_filters(dashboard);
				}
			} else {
				const $container = $('.dashboard-graph');
				if ($container.length && !$('.entrance-test-filter-bar').length) {
					render_entrance_test_filters({ container: $container });
				}
			}
		}
	}, 200);

	function render_entrance_test_filters(dashboard) {
		if ($('.entrance-test-filter-bar').length) return;

		const $target = dashboard.container || $('.dashboard-graph');
		if (!$target || !$target.length) return;

		dashboard.$filter_bar = $(`
			<div class="entrance-test-filter-bar shadow-sm px-3 py-3 mb-4" style="background: #fff; border-radius: 8px; border: 1px solid #e2e8f0; display: flex; flex-wrap: wrap; gap: 15px; align-items: flex-end; width: 100%; z-index: 101;">
			</div>
		`).prependTo($target);

		frappe._entrance_test_dashboard_filters = {};

		const config = [
			{ label: __('Academic Year'), fieldname: 'academic_year', fieldtype: 'Link', options: 'Academic Year' },
			{ label: __('Admission Cycle'), fieldname: 'admission_cycle', fieldtype: 'Link', options: 'Admission Cycle' },
			{ label: __('Campus'), fieldname: 'campus', fieldtype: 'Link', options: 'Campus' },
			{ label: __('Programme'), fieldname: 'program', fieldtype: 'Link', options: 'Programme' },
			{ label: __('Center Name'), fieldname: 'entrance_test_provider', fieldtype: 'Link', options: 'Entrance Test Provider' },
			{ label: __('Show International Applicant'), fieldname: 'is_international_applicant', fieldtype: 'Check' }
		];

		const controls = {};

		config.forEach(f => {
			const isCheck = f.fieldtype === 'Check';
			const $wrapper = $(`<div style="${isCheck ? 'min-width: 200px; display: flex; align-items: center; padding-bottom: 8px;' : 'min-width: 170px;'}"></div>`).appendTo(dashboard.$filter_bar);
			const ctrl = frappe.ui.form.make_control({
				df: {
					...f,
					onchange: () => {
						const val = ctrl.get_value();
						if (f.fieldname === 'is_international_applicant') {
							const is_checked = !!val;
							frappe._entrance_test_dashboard_filters.is_international_applicant = is_checked ? 1 : 0;
							
							if (controls.entrance_test_provider) {
								if (is_checked) {
									controls.entrance_test_provider.set_value('');
									frappe._entrance_test_dashboard_filters.entrance_test_provider = '';
									controls.entrance_test_provider.df.read_only = 1;
								} else {
									// Only un-lock if not restricted by provider role
									if (!is_provider_role_restricted()) {
										controls.entrance_test_provider.df.read_only = 0;
									}
								}
								controls.entrance_test_provider.refresh();
							}
						} else {
							frappe._entrance_test_dashboard_filters[f.fieldname] = val;
						}
						refresh_entrance_test_widgets(dashboard);
					}
				},
				parent: $wrapper,
				render_input: true
			});
			controls[f.fieldname] = ctrl;
		});

		// Check if user is restricted to Entrance Test Provider role
		function is_provider_role_restricted() {
			return frappe.user_roles.includes("Entrance Test Provider") &&
				!frappe.user_roles.includes("System Manager") &&
				!frappe.user_roles.includes("Entrance Test Admin");
		}

		if (is_provider_role_restricted() && controls.entrance_test_provider) {
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Entrance Test Provider",
					filters: { user: frappe.session.user },
					fieldname: "name"
				},
				callback: function(r) {
					if (r.message && r.message.name) {
						controls.entrance_test_provider.set_value(r.message.name);
						frappe._entrance_test_dashboard_filters.entrance_test_provider = r.message.name;
						controls.entrance_test_provider.df.read_only = 1;
						controls.entrance_test_provider.refresh();
					}
				}
			});
		}

		$(`<button class="btn btn-default btn-sm ml-auto" style="height: 36px;">
			<i class="fa fa-refresh mr-1"></i> ${__('Reset')}
		</button>`).appendTo(dashboard.$filter_bar).on('click', () => {
			dashboard.$filter_bar.find('.form-control').val('').trigger('change');
			dashboard.$filter_bar.find('input[type="checkbox"]').prop('checked', false).trigger('change');
			
			frappe._entrance_test_dashboard_filters = {};

			if (controls.entrance_test_provider && !is_provider_role_restricted()) {
				controls.entrance_test_provider.df.read_only = 0;
				controls.entrance_test_provider.refresh();
			}

			refresh_entrance_test_widgets(dashboard);
		});

		$(`<button class="btn btn-secondary btn-sm" style="height: 36px; margin-left: 8px;">
			<i class="fa fa-wheelchair mr-1"></i> ${__('PWD Candidate Report')}
		</button>`).appendTo(dashboard.$filter_bar).on('click', () => {
			const route_filters = Object.assign({}, frappe._entrance_test_dashboard_filters || {});
			route_filters.pwd_only = 1;
			frappe.set_route('query-report', 'Test Center-wise PWD Candidate Report', route_filters);
		});
	}

	function refresh_entrance_test_widgets(dashboard) {
		let d = dashboard || frappe.dashboard;
		if (!d) return;
		const global = frappe._entrance_test_dashboard_filters;

		// Refresh Cards
		if (d.number_card_group) {
			d.number_card_group.widgets_list.forEach(w => {
				if (w.render_card) w.render_card();
			});
		}

		// Refresh Charts
		if (d.chart_group) {
			d.chart_group.widgets_list.forEach(w => {
				const chart_doc = w.chart_doc || w.chart;
				if (!chart_doc) return;

				if (chart_doc.report_name) {
					if (!w.filters || Array.isArray(w.filters)) w.filters = {};
					apply_object_filters(w.filters, chart_doc.document_type, global, chart_doc.report_name);
				}

				if (w.set_chart_filters && w.fetch_and_update_chart) {
					w.set_chart_filters().then(() => {
						if (chart_doc.report_name) {
							apply_object_filters(w.filters, chart_doc.document_type, global, chart_doc.report_name);
						}
						w.fetch_and_update_chart();
					});
				} else if (w.refresh) {
					w.refresh();
				}
			});
		}
	}
})();
