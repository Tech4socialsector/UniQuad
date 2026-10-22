/**
 * Global Filter Injection for Admission Dashboard
 * This script provides a robust global filter bar for the standard Admission dashboard.
 */

(function() {
	console.log("SLCM: Admission Dashboard Filters script initialized");

	// 1. Monkey-patch get_all_filters to inject/override filters for Admission widgets
	if (!frappe.dashboard_utils._slcm_admission_patched) {
		const original_get_all_filters = frappe.dashboard_utils.get_all_filters;
		frappe.dashboard_utils.get_all_filters = function(doc) {
			let filters = original_get_all_filters.apply(this, arguments);
			
			const route = frappe.get_route();
			if (route && route[0] === 'dashboard-view' && route[1] === 'Admission' && frappe._admission_dashboard_filters) {
				const global = frappe._admission_dashboard_filters;
				const target_doctype = doc.document_type || (doc.report_name ? 'Applicant' : null);
				
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
		frappe.dashboard_utils._slcm_admission_patched = true;
	}

	function apply_array_filters(filters, doctype, global) {
		const maps = {
			'Applicant': { year: 'academic_year', cycle: 'admission_cycle', campus: 'campus', prog: 'program' },
			'Refund Request': { year: 'applicant.academic_year', cycle: 'applicant.admission_cycle', campus: 'applicant.campus', prog: 'applicant.program' }
		};

		const map = maps[doctype];
		if (!map) return;

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

		if (global.academic_year) upsert(map.year, '=', global.academic_year); else remove(map.year);
		if (global.admission_cycle) upsert(map.cycle, '=', global.admission_cycle); else remove(map.cycle);
		if (global.campus) upsert(map.campus, '=', global.campus); else remove(map.campus);
		if (global.program) upsert(map.prog, '=', global.program); else remove(map.prog);
	}

	function apply_object_filters(filters, doctype, global, report_name) {
		if (global.academic_year) {
			if (report_name === 'Primary Program Choice' || report_name === 'Application Trends') {
				filters.admission_year = global.academic_year;
			} else {
				filters.academic_year = global.academic_year;
			}
		} else {
			delete filters.admission_year;
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
	}

	// 2. Dashboard Integration Logic
	function is_admission_dashboard() {
		const route = frappe.get_route ? frappe.get_route() : [];
		const path = (window.location && window.location.pathname) || '';
		const hash = (window.location && window.location.hash) || '';
		const dashboard = frappe.dashboard || (cur_page && cur_page.page && cur_page.page.dashboard);

		return (route && route[0] === 'dashboard-view' && (route[1] === 'Admission' || route[1] === 'admission'))
			|| path.includes('dashboard-view/Admission')
			|| hash.includes('dashboard-view/Admission')
			|| (dashboard && (dashboard.dashboard_name === 'Admission' || dashboard.name === 'Admission'));
	}

	// Inject custom styles for rotated charts
	if (!$('#slcm-rotated-chart-styles').length) {
		$('head').append(`
			<style id="slcm-rotated-chart-styles">
				.slcm-rotated-chart-widget,
				.slcm-rotated-chart-widget .widget-body,
				.slcm-rotated-chart-widget .chart-wrapper,
				.slcm-rotated-chart-widget .chart-container,
				.slcm-rotated-chart-widget .frappe-chart,
				.slcm-rotated-chart-widget svg {
					overflow: visible !important;
				}
				.slcm-rotated-chart-widget {
					padding-bottom: 25px !important;
				}
			</style>
		`);
	}

	let filter_check_interval = setInterval(() => {
		if (is_admission_dashboard()) {
			let dashboard = frappe.dashboard;
			if (!dashboard && cur_page && cur_page.page && cur_page.page.dashboard) {
				dashboard = cur_page.page.dashboard;
			}

			if (dashboard && (dashboard.dashboard_name === 'Admission' || dashboard.name === 'Admission')) {
				if (!dashboard.$filter_bar) {
					render_admission_filters(dashboard);
				}
				format_admission_chart_labels(dashboard);
			} else {
				const $container = $('.dashboard-graph');
				if ($container.length && !$('.admission-filter-bar').length) {
					render_admission_filters({ container: $container });
				}
				format_admission_chart_labels(dashboard);
			}
		}
	}, 200);

	function render_admission_filters(dashboard) {
		if ($('.admission-filter-bar').length) return;

		const $target = dashboard.container || $('.dashboard-graph');
		if (!$target || !$target.length) return;

		dashboard.$filter_bar = $(`
			<div class="admission-filter-bar shadow-sm px-3 py-3 mb-4" style="background: #fff; border-radius: 8px; border: 1px solid #e2e8f0; display: flex; flex-wrap: wrap; gap: 15px; align-items: flex-end; width: 100%; z-index: 101;">
			</div>
		`).prependTo($target);

		function move_fee_payment_to_middle() {
			const $container = $('.dashboard-graph');
			if (!$container.length) return;

			const $chart = $('.widget-title').filter(function() {
				return $(this).text().trim() === 'Applicant Fee Payment';
			}).closest('.widget');

			if (!$chart.length) return;

			const $refundSection = $('.admission-refunds-section');
			const $approvedRefundCard = $('.widget-title').filter(function() {
				return $(this).text().trim() === 'Approved Refund Requests';
			}).closest('.widget');

			const $reference = $refundSection.length ? $refundSection : $approvedRefundCard;

			if ($reference.length) {
				if ($('.admission-fee-details-section').length === 0) {
					$reference.before(`
						<div class="admission-fee-details-section mt-4 mb-2" style="grid-column: 1 / -1; width: 100%;">
							<h5 style="font-weight: 700; font-size:20px; color: #1a3c6e; margin: 0; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0;">
								Fee Details
							</h5>
						</div>
					`);
				}

				const $feeSection = $('.admission-fee-details-section');
				if ($feeSection.length && $chart.prev().get(0) !== $feeSection.get(0)) {
					$feeSection.after($chart);
					
					// Trigger resize to force the chart SVG to redraw to full width when relocated
					setTimeout(() => {
						window.dispatchEvent(new Event('resize'));
					}, 200);
				}

				// Always ensure the chart spans the full width of the grid container and doesn't get squished
				$chart.attr('style', function(i, s) {
					let base = s || '';
					if (!base.includes('grid-column')) {
						base += ' ; grid-column: 1 / -1 !important; width: 100% !important; margin-bottom: 20px !important;';
					}
					return base;
				});
			}
		}

		function inject_admission_sections() {
			move_fee_payment_to_middle();

			if ($('.admission-applications-section').length === 0) {
				const $cards = $('.widget-title');
				$cards.each(function() {
					if ($(this).text().trim() === 'Total Applicants') {
						const $cardWidget = $(this).closest('.widget');
						$cardWidget.before(`
							<div class="admission-applications-section mt-4 mb-2" style="grid-column: 1 / -1; width: 100%;">
								<h5 style="font-weight: 700; font-size:20px; color: #1a3c6e; margin: 0; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0;">
									Applications & Offers
								</h5>
							</div>
						`);
					}
				});
			}

			if ($('.admission-refunds-section').length === 0) {
				const $cards = $('.widget-title');
				$cards.each(function() {
					if ($(this).text().trim() === 'Approved Refund Requests') {
						const $cardWidget = $(this).closest('.widget');
						$cardWidget.before(`
							<div class="admission-refunds-section mt-4 mb-2" style="grid-column: 1 / -1; width: 100%;">
								<h5 style="font-weight: 700; font-size:20px; color: #1a3c6e; margin: 0; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0;">
									Refund Details
								</h5>
							</div>
						`);
					}
				});
			}
		}

		// Initial injection
		inject_admission_sections();

		// Mutation observer for instant injection when DOM changes
		const observer = new MutationObserver(() => {
			observer.disconnect();
			inject_admission_sections();
			observer.observe($target[0], { childList: true, subtree: true });
		});
		observer.observe($target[0], { childList: true, subtree: true });

		// Fast fallback check just in case
		setInterval(inject_admission_sections, 100);

		frappe._admission_dashboard_filters = {};

		const config = [
			{ label: __('Academic Year'), fieldname: 'academic_year', fieldtype: 'Link', options: 'Academic Year' },
			{ label: __('Admission Cycle'), fieldname: 'admission_cycle', fieldtype: 'Link', options: 'Admission Cycle' },
			{ label: __('Campus'), fieldname: 'campus', fieldtype: 'Link', options: 'Campus' },
			{ label: __('Programme'), fieldname: 'program', fieldtype: 'Link', options: 'Programme' }
		];

		const controls = {};

		config.forEach(f => {
			const $wrapper = $(`<div style="min-width: 180px;"></div>`).appendTo(dashboard.$filter_bar);
			const ctrl = frappe.ui.form.make_control({
				df: {
					...f,
					onchange: () => {
						frappe._admission_dashboard_filters[f.fieldname] = ctrl.get_value();
						refresh_admission_widgets(dashboard);
					}
				},
				parent: $wrapper,
				render_input: true
			});
			controls[f.fieldname] = ctrl;
		});

		// Related Filter Logic: Admission Cycle depends on Academic Year
		if (controls.admission_cycle && controls.academic_year) {
			controls.admission_cycle.get_query = function() {
				return {
					filters: { 'admission_year': controls.academic_year.get_value() || "" }
				};
			};
		}

		$(`<button class="btn btn-default btn-sm ml-auto" style="height: 36px;">
			<i class="fa fa-refresh mr-1"></i> ${__('Reset')}
		</button>`).appendTo(dashboard.$filter_bar).on('click', () => {
			dashboard.$filter_bar.find('.form-control').val('').trigger('change');
			frappe._admission_dashboard_filters = {};
			refresh_admission_widgets(dashboard);
		});
	}

	function refresh_admission_widgets(dashboard) {
		let d = dashboard || frappe.dashboard;
		if (!d) return;
		const global = frappe._admission_dashboard_filters;

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
						w.fetch_and_update_chart().then(() => {
							format_admission_chart_labels(d);
						});
					});
				} else if (w.refresh) {
					w.refresh();
					setTimeout(() => format_admission_chart_labels(d), 200);
				}
			});
		}
	}

	// 3. Slanted X-Axis Labels (-45°) for Target Reports on Admission Dashboard
	const ROTATE_TARGET_CHARTS = [
		'Primary Program Choice',
		'Applications by Geography',
		'Admission Marketing Source Analysis',
		'Allocated Students by Centre'
	];

	function is_target_chart(name) {
		if (!name) return false;
		const cleanName = name.trim().toLowerCase();
		return ROTATE_TARGET_CHARTS.some(target => {
			const cleanTarget = target.toLowerCase();
			return cleanName === cleanTarget || cleanName.includes(cleanTarget);
		});
	}

	function get_widget_name(w) {
		if (!w) return '';
		const chart_doc = w.chart_doc || w.chart || {};
		return chart_doc.chart_name || chart_doc.report_name || chart_doc.name || w.chart_name || w.name || (w.title_field ? w.title_field.text().trim() : '') || '';
	}

	function setup_widget_observer(widget, chartName) {
		if (!widget || !widget.chart_wrapper || !widget.chart_wrapper.length) return;
		const el = widget.chart_wrapper[0];
		if (el._slcm_chart_observer) return;

		let is_formatting = false;
		const observer = new MutationObserver(function() {
			if (is_formatting) return;
			const $unrotated = $(el).find(".x.axis text:not([data-rotated='1'])");
			if ($unrotated.length) {
				is_formatting = true;
				try {
					format_widget_x_axis($(widget.chart_wrapper), widget, chartName);
				} finally {
					is_formatting = false;
				}
			}
		});

		observer.observe(el, {
			childList: true,
			subtree: true,
			attributes: false
		});

		el._slcm_chart_observer = observer;
	}

	// Monkey-patch ChartWidget.render if available to catch target charts instantly upon creation
	if (frappe.widget && frappe.widget.widget_factory && frappe.widget.widget_factory.chart && !frappe.widget.widget_factory.chart._slcm_admission_render_patched) {
		const orig_chart_render = frappe.widget.widget_factory.chart.prototype.render;
		frappe.widget.widget_factory.chart.prototype.render = async function() {
			const res = await orig_chart_render.apply(this, arguments);
			try {
				if (is_admission_dashboard()) {
					const name = get_widget_name(this);
					if (is_target_chart(name) && this.chart_wrapper && this.chart_wrapper.length) {
						setup_widget_observer(this, name);
						format_widget_x_axis($(this.chart_wrapper), this, name);
					}
				}
			} catch (e) {
				console.error("Error in Admission ChartWidget render hook:", e);
			}
			return res;
		};
		frappe.widget.widget_factory.chart._slcm_admission_render_patched = true;
	}

	function format_admission_chart_labels(dashboard) {
		let d = dashboard || frappe.dashboard;
		if (!d && cur_page && cur_page.page && cur_page.page.dashboard) {
			d = cur_page.page.dashboard;
		}
		if (!d || !d.chart_group || !d.chart_group.widgets_list) return;

		d.chart_group.widgets_list.forEach(w => {
			const name = get_widget_name(w);
			if (is_target_chart(name) && w.chart_wrapper && w.chart_wrapper.length) {
				setup_widget_observer(w, name);
				format_widget_x_axis($(w.chart_wrapper), w, name);
			}
		});
	}

	function format_widget_x_axis($wrapper, widget, chartName) {
		if (!$wrapper || !$wrapper.length) return;

		const do_align = () => {
			const $svg = $wrapper.find('svg');
			if (!$svg.length) return;

			if (widget && widget.widget) {
				widget.widget.addClass('slcm-rotated-chart-widget');
			}

			// Ensure overflow is visible so labels and tooltips aren't clipped
			$svg.css('overflow', 'visible');
			$wrapper.css('overflow', 'visible');
			$wrapper.closest('.widget').css('overflow', 'visible');
			$wrapper.closest('.widget-body').css('overflow', 'visible');
			$wrapper.find('.chart-container').css('overflow', 'visible');
			$wrapper.find('.frappe-chart').css('overflow', 'visible');

			let maxLabelDrop = 0;
			const $xAxis = $svg.find('.x.axis');
			if ($xAxis.length) {
				const $groups = $xAxis.children('g');
				let raw_labels = null;
				if (widget && widget.data && widget.data.labels && widget.data.labels.length) {
					raw_labels = widget.data.labels;
				} else if (widget && widget.dashboard_chart && widget.dashboard_chart.data && widget.dashboard_chart.data.labels && widget.dashboard_chart.data.labels.length) {
					raw_labels = widget.dashboard_chart.data.labels;
				} else if (widget && widget.report_result && widget.report_result.chart && widget.report_result.chart.data && widget.report_result.chart.data.labels) {
					raw_labels = widget.report_result.chart.data.labels;
				} else if (widget && widget.report_result && widget.report_result.result) {
					if (chartName.includes('Applications by Geography')) {
						raw_labels = widget.report_result.result.map(r => (r.city && r.city !== 'Unknown' ? r.city : (r.state || r.country)));
					} else if (chartName.includes('Allocated Students by Centre')) {
						raw_labels = widget.report_result.result.map(r => r.center_name || r.entrance_test_provider);
					} else if (chartName.includes('Primary Program Choice')) {
						raw_labels = widget.report_result.result.map(r => r.program);
					} else if (chartName.includes('Admission Marketing Source Analysis')) {
						raw_labels = widget.report_result.result.map(r => r.source_of_information);
					}
				}

				$groups.each(function(i) {
					const $g = $(this);
					const $text = $g.find('text');
					if (!$text.length) return;

					if (raw_labels && raw_labels[i]) {
						$text.text(raw_labels[i]);
					}

					let origY = $text.data('orig-y');
					if (origY === undefined) {
						origY = parseFloat($text.attr('y')) || 16.5;
						$text.data('orig-y', origY);
					}

					$text.attr({
						'transform': `rotate(-45, 0, ${origY})`,
						'text-anchor': 'end',
						'dx': '-6px',
						'dy': '4px',
						'data-rotated': '1'
					});

					const txt = $text.text() || '';
					const textDrop = Math.ceil(txt.length * 5.2);
					if (textDrop > maxLabelDrop) {
						maxLabelDrop = textDrop;
					}
				});
			}

			const labelExtraHeight = maxLabelDrop > 0 ? Math.max(55, maxLabelDrop + 20) : 0;

			let legendExtraHeight = 0;
			const $legend = $svg.find('.chart-legend');
			if ($legend.length) {
				const $items = $legend.children('g');
				if ($items.length) {
					let origLegendTransform = $legend.data('orig-transform');
					if (!origLegendTransform) {
						origLegendTransform = $legend.attr('transform') || '';
						$legend.data('orig-transform', origLegendTransform);
					}

					if (labelExtraHeight > 0 && origLegendTransform) {
						const match = origLegendTransform.match(/translate\(([^,]+),\s*([^)]+)\)/);
						if (match) {
							const lx = parseFloat(match[1]) || 0;
							const ly = parseFloat(match[2]) || 0;
							$legend.attr('transform', `translate(${lx}, ${ly + labelExtraHeight})`);
						}
					}
				}
			}

			if (labelExtraHeight > 0 || legendExtraHeight > 0) {
				let baseHeight = parseFloat($svg.data('base-height'));
				if (!baseHeight) {
					baseHeight = parseFloat($svg.attr('height')) || 240;
					$svg.data('base-height', baseHeight);
				}
				const targetHeight = baseHeight + labelExtraHeight + legendExtraHeight;
				$svg.attr('height', targetHeight);
				$svg.css('height', targetHeight + 'px');
				$wrapper.css('min-height', targetHeight + 'px');
			}
		};

		do_align();
		requestAnimationFrame(do_align);
		setTimeout(do_align, 50);
		setTimeout(do_align, 150);
		setTimeout(do_align, 400);
	}

	$(window).off('resize.admission_dashboard_target_charts').on('resize.admission_dashboard_target_charts', () => {
		if (is_admission_dashboard()) {
			format_admission_chart_labels();
		}
	});
})();
