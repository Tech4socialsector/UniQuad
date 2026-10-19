/**
 * Global Filter Injection for PACE Dashboard
 * This script provides a robust global filter bar for the standard PACE dashboard.
 */

(function() {
	console.log("SLCM: PACE Dashboard Filters script initialized");

	// 1. Monkey-patch get_all_filters to inject/override filters for PACE widgets
	const original_get_all_filters = frappe.dashboard_utils.get_all_filters;
	frappe.dashboard_utils.get_all_filters = function(doc) {
		let filters = original_get_all_filters.apply(this, arguments);
		
		const route = frappe.get_route();
		if (route && route[0] === 'dashboard-view' && route[1] === 'PACE' && frappe._pace_dashboard_filters) {
			const global = frappe._pace_dashboard_filters;
			const target_doctype = doc.document_type || (doc.report_name ? 'PACE Application' : null);
			
			if (target_doctype) {
				const is_report = !!doc.report_name;
				
				if (!is_report && Array.isArray(filters)) {
					// Handle Standard DocType Filters (Arrays)
					apply_array_filters(filters, target_doctype, global, doc);
				} else {
					// Handle Report/Object Filters (Objects)
					if (Array.isArray(filters)) filters = {};
					apply_object_filters(filters, target_doctype, global, doc.report_name);
				}
			}
		}
		return filters;
	};

	function apply_array_filters(filters, doctype, global, doc) {
		const card_name = (doc && (doc.name || doc.label)) || '';

		let date_field = 'creation';
		let year_field = 'academic_year';
		let prog_field = 'programme';
		let verifier_field = null;

		if (doctype === 'PACE Receipt') {
			prog_field = 'program';
			date_field = 'payment_date';
		} else if (doctype === 'PACE Applicant Fee Assignment') {
			prog_field = 'program';
			date_field = 'assignment_date';
		} else if (doctype === 'PACE Document Verification') {
			verifier_field = 'assigned_verifier';
			if (card_name.includes('Verified') || card_name.includes('Completed') || card_name === 'Verified') {
				date_field = 'verified_on';
			} else {
				date_field = 'modified';
			}
		} else if (doctype === 'PACE Application') {
			if (card_name === 'Applications Verified') {
				date_field = 'modified';
			} else if (card_name === 'Students Enrolled') {
				date_field = 'modified';
			} else if (card_name === 'Applications Rejected') {
				date_field = 'modified';
			} else {
				date_field = 'creation';
			}
		}

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

		if (global.academic_year) upsert(year_field, '=', global.academic_year);
		if (global.programme) upsert(prog_field, '=', global.programme);
		if (global.assigned_verifier) upsert(verifier_field, '=', global.assigned_verifier);
		if (global.from_date || global.to_date) {
			let start = global.from_date || '1900-01-01';
			let end = global.to_date || '2099-12-31';
			if (date_field === 'creation' || date_field === 'modified' || date_field === 'verified_on' || date_field === 'payment_date') {
				if (start.length === 10) start = start + ' 00:00:00';
				if (end.length === 10) end = end + ' 23:59:59';
			}
			upsert(date_field, 'between', [start, end]);
		}
	}

	function apply_object_filters(filters, doctype, global, report_name) {
		const prog_key = (doctype === 'PACE Receipt' || report_name) ? 'program' : 'programme';

		if (global.academic_year) {
			filters.academic_year = global.academic_year;
		} else {
			delete filters.academic_year;
		}

		if (global.programme) {
			filters[prog_key] = global.programme;
		} else {
			delete filters.program;
			delete filters.programme;
		}

		if (global.from_date) {
			filters.from_date = global.from_date;
		} else {
			delete filters.from_date;
		}

		if (global.to_date) {
			filters.to_date = global.to_date;
		} else {
			delete filters.to_date;
		}

		if (global.assigned_verifier) {
			filters.assigned_verifier = global.assigned_verifier;
		} else {
			delete filters.assigned_verifier;
		}
	}

	// 2. Dashboard Integration Logic
	let filter_check_interval = setInterval(() => {
		const route = frappe.get_route();
		if (route && route[0] === 'dashboard-view' && route[1] === 'PACE') {
			// Skip for Document Verifiers who should use their own dashboard
			if (frappe.user_roles.includes("Document Verifier") && 
				!frappe.user_roles.includes("System Manager") && 
				!frappe.user_roles.includes("Admission Admin") &&
				!frappe.user_roles.includes("PACE Admission Manager")) {
				return;
			}
			let dashboard = frappe.dashboard;
			if (!dashboard && cur_page && cur_page.page.dashboard) {
				dashboard = cur_page.page.dashboard;
			}

			if (dashboard && (dashboard.dashboard_name === 'PACE' || dashboard.name === 'PACE')) {
				if (!dashboard.$filter_bar) {
					render_pace_filters(dashboard);
				}
			} else {
				const $container = $('.dashboard-graph');
				if ($container.length && !$('.pace-filter-bar').length) {
					render_pace_filters({ container: $container });
				}
			}
		}
	}, 200);

	function render_pace_filters(dashboard) {
		if ($('.pace-filter-bar').length) return;

		if (!frappe._document_verifiers_list) {
			frappe.call({
				method: 'slcm.pace.api.get_verifiers',
				callback: function(r) {
					frappe._document_verifiers_list = (r.message || []).map(x => Array.isArray(x) ? x[0] : x.name || x);
				}
			});
		}

		const $target = dashboard.container || $('.dashboard-graph');
		if (!$target || !$target.length) return;

		dashboard.$filter_bar = $(`
			<div class="pace-filter-bar shadow-sm px-3 py-3 mb-4" style="background: #fff; border-radius: 8px; border: 1px solid #e2e8f0; display: flex; flex-wrap: wrap; gap: 15px; align-items: flex-end; width: 100%; z-index: 101;">
			</div>
		`).prependTo($target);

		function inject_pace_sections() {
			if ($('.pace-my-docs-section').length === 0) {
				const $cards = $('.widget-title');
				$cards.each(function() {
					if ($(this).text().trim() === 'Assigned Documents') {
						const $cardWidget = $(this).closest('.widget');
						$cardWidget.before(`
							<div class="pace-my-docs-section mt-4 mb-2" style="grid-column: 1 / -1; width: 100%;">
								<h5 style="font-weight: 700; font-size:20px; color: #1a3c6e; margin: 0; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0;">
									My Documents Status
								</h5>
							</div>
						`);
					}
				});
			}

			if ($('.pace-fee-summary-section').length === 0) {
				const $cards = $('.widget-title');
				$cards.each(function() {
					if ($(this).text().trim() === 'Application Fees Collected') {
						const $cardWidget = $(this).closest('.widget');
						$cardWidget.before(`
							<div class="pace-fee-summary-section mt-4 mb-2" style="grid-column: 1 / -1; width: 100%;">
								<h5 style="font-weight: 700; font-size:20px; color: #1a3c6e; margin: 0; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0;">
									Fee Collection Summary
								</h5>
							</div>
						`);
					}
				});
			}
		}

		// Initial injection
		inject_pace_sections();

		// Mutation observer for instant injection when DOM changes
		const observer = new MutationObserver(() => {
			observer.disconnect();
			inject_pace_sections();
			observer.observe($target[0], { childList: true, subtree: true });
		});
		observer.observe($target[0], { childList: true, subtree: true });

		// Fast fallback check just in case
		setInterval(inject_pace_sections, 100);

		frappe._pace_dashboard_filters = {};

		const config = [
			{ label: __('Academic Year'), fieldname: 'academic_year', fieldtype: 'Link', options: 'Academic Year' },
			{ label: __('Programme'), fieldname: 'programme', fieldtype: 'Link', options: 'PACE Programme' },
			{ label: __('From Date'), fieldname: 'from_date', fieldtype: 'Date' },
			{ label: __('To Date'), fieldname: 'to_date', fieldtype: 'Date' },
			{ 
				label: __('Document Verifier'), fieldname: 'assigned_verifier', fieldtype: 'Link', options: 'User',
				get_query: () => {
					return {
						filters: {
							name: ['in', frappe._document_verifiers_list || []]
						}
					};
				}
			}
		];

		config.forEach(f => {
			const $wrapper = $(`<div style="min-width: 180px;"></div>`).appendTo(dashboard.$filter_bar);
			const ctrl = frappe.ui.form.make_control({
				df: {
					...f,
					onchange: () => {
						frappe._pace_dashboard_filters[f.fieldname] = ctrl.get_value();
						refresh_pace_widgets(dashboard);
					}
				},
				parent: $wrapper,
				render_input: true
			});
		});

		$(`<button class="btn btn-default btn-sm ml-auto" style="height: 36px;">
			<i class="fa fa-refresh mr-1"></i> ${__('Reset')}
		</button>`).appendTo(dashboard.$filter_bar).on('click', () => {
			dashboard.$filter_bar.find('.form-control').val('').trigger('change');
			frappe._pace_dashboard_filters = {};
			refresh_pace_widgets(dashboard);
		});
	}

	function refresh_pace_widgets(dashboard) {
		let d = dashboard || frappe.dashboard;
		if (!d) return;
		const global = frappe._pace_dashboard_filters;

		// Refresh Cards
		if (d.number_card_group) {
			d.number_card_group.widgets_list.forEach(w => {
				// Inject filters directly if possible
				if (w.render_card) w.render_card();
			});
		}

		// Refresh Charts
		if (d.chart_group) {
			d.chart_group.widgets_list.forEach(w => {
				const chart_doc = w.chart_doc || w.chart;
				if (!chart_doc) return;

				// Brute-force override filters for Reports just before refresh
				if (chart_doc.report_name) {
					if (!w.filters || Array.isArray(w.filters)) w.filters = {};
					apply_object_filters(w.filters, chart_doc.document_type, global, chart_doc.report_name);
				}

				if (w.set_chart_filters && w.fetch_and_update_chart) {
					w.set_chart_filters().then(() => {
						// Ensure our overrides stay after set_chart_filters
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