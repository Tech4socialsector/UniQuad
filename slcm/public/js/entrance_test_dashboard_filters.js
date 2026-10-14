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
				setup_dashboard_city_drilldown(dashboard);
			} else {
				const $container = $('.dashboard-graph');
				if ($container.length && !$('.entrance-test-filter-bar').length) {
					render_entrance_test_filters({ container: $container });
				}
			}
		}
	}, 300);

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

		let default_academic_year = null;
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Academic Year",
				filters: { status: "Active" },
				fields: ["name", "year_start_date", "year_end_date"],
				order_by: "year_start_date desc",
				limit_page_length: 5
			},
			callback: function(r) {
				if (r.message && r.message.length) {
					const today = frappe.datetime.get_today();
					let active = r.message.find(y => y.year_start_date && y.year_end_date && y.year_start_date <= today && y.year_end_date >= today);
					if (!active) active = r.message[0];
					default_academic_year = active.name;

					if (controls.academic_year && !frappe._entrance_test_dashboard_filters.academic_year) {
						controls.academic_year.set_value(default_academic_year);
						frappe._entrance_test_dashboard_filters.academic_year = default_academic_year;
						refresh_entrance_test_widgets(dashboard);
					}
				}
			}
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

			if (default_academic_year && controls.academic_year) {
				controls.academic_year.set_value(default_academic_year);
				frappe._entrance_test_dashboard_filters.academic_year = default_academic_year;
			}

			refresh_entrance_test_widgets(dashboard);
		});

		$(`<button class="btn btn-secondary btn-sm" style="height: 36px; margin-left: 8px;">
			<i class="fa fa-wheelchair mr-1"></i> ${__('PWD Candidate Report')}
		</button>`).appendTo(dashboard.$filter_bar).on('click', () => {
			const route_filters = Object.assign({}, frappe._entrance_test_dashboard_filters || {});
			route_filters.is_pwd_only = 1;
			frappe.set_route('query-report', 'Test Center-wise Candidate Detail Report', route_filters);
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
						w.fetch_and_update_chart().then(() => {
							setup_dashboard_city_drilldown(dashboard);
							align_dashboard_chart_legends(dashboard);
						});
					});
				} else if (w.refresh) {
					w.refresh();
					setTimeout(() => {
						setup_dashboard_city_drilldown(dashboard);
						align_dashboard_chart_legends(dashboard);
					}, 500);
				}
			});
		}
	}

	function setup_dashboard_city_drilldown(dashboard) {
		let d = dashboard || frappe.dashboard;
		if (!d || !d.chart_group || !d.chart_group.widgets_list) return;

		align_dashboard_chart_legends(d);

		const cityWidget = d.chart_group.widgets_list.find(w => {
			const name = (w.chart_doc && w.chart_doc.name) || w.chart_name || w.name;
			return name === "Allocated Students by City";
		});

		if (!cityWidget || !cityWidget.chart_wrapper || !cityWidget.chart_wrapper.length) return;
		if (cityWidget._drilldown_bound) return;
		cityWidget._drilldown_bound = true;

		const $wrapper = $(cityWidget.chart_wrapper);
		$wrapper.css('cursor', 'pointer');

		function handle_city_select(city) {
			if (!city || cityWidget._is_drilled_down) return;
			drilldown_dashboard_widget(cityWidget, city);
		}

		$wrapper.off('data-select.city_drill');
		$wrapper.on('data-select.city_drill', function(e) {
			const city = e.label || (e.originalEvent && e.originalEvent.label);
			if (city) handle_city_select(city);
		});

		$wrapper.off('click.city_bar');
		$wrapper.on('click.city_bar', '.data-point, rect.bar, path.bar, g.dataset-units rect', function() {
			if (cityWidget._is_drilled_down) return;
			const ptIdx = $(this).attr('data-point-index');
			if (ptIdx !== undefined && cityWidget.dashboard_chart && cityWidget.dashboard_chart.data && cityWidget.dashboard_chart.data.labels) {
				const city = cityWidget.dashboard_chart.data.labels[parseInt(ptIdx)];
				if (city) handle_city_select(city);
			}
		});
	}

	function drilldown_dashboard_widget(widget, city) {
		if (!widget.report_result || !widget.report_result.result) return;

		const cityRow = widget.report_result.result.find(r => r.city === city);
		if (!cityRow) return;

		const prog_cols = (widget.report_result.columns || []).filter(c => c.fieldname && c.fieldname.startsWith('prog_'));
		const prog_items = [];
		prog_cols.forEach(col => {
			const val = cityRow[col.fieldname] || 0;
			if (val > 0) {
				prog_items.push({ label: col.label, value: val });
			}
		});

		if (!prog_items.length) {
			frappe.show_alert({ message: __('No allocated candidates in {0}', [city]), indicator: 'orange' });
			return;
		}

		widget._is_drilled_down = true;
		widget._drilled_city = city;

		const total = cityRow.allocated_count || prog_items.reduce((a, b) => a + b.value, 0);

		if (!widget._orig_title) {
			widget._orig_title = widget.title_field.text();
		}

		widget.title_field.html(`<b>${frappe.utils.escape_html(city)}</b> <span class="text-muted" style="font-size: 13px; font-weight: normal;">— ${__('Programme Breakdown')} (${total.toLocaleString('en-IN')})</span>`);

		widget.action_area.find('.btn-reset-drill').remove();
		const $backBtn = $(`
			<button class="btn btn-xs btn-primary btn-reset-drill mr-2" style="font-weight: 500;">
				<i class="fa fa-arrow-left mr-1"></i> ${__('All Cities')}
			</button>
		`).prependTo(widget.action_area);

		$backBtn.on('click', function(e) {
			e.stopPropagation();
			widget._is_drilled_down = false;
			widget._drilled_city = null;
			$backBtn.remove();
			widget.title_field.text(widget._orig_title || __('Allocated Students by City'));
			widget.chart_wrapper.empty();
			delete widget.dashboard_chart;
			widget.render();
			widget._drilldown_bound = false;
			setTimeout(() => {
				setup_dashboard_city_drilldown(widget.dashboard || frappe.dashboard);
				align_dashboard_chart_legends(widget.dashboard || frappe.dashboard);
			}, 300);
		});

		const palette = [
			'#2490EF', '#48C774', '#FF9F43', '#EA5455', '#7367F0',
			'#1E9FF2', '#10AC84', '#EE5253', '#F368E0', '#00D2D3'
		];

		widget.chart_wrapper.empty();
		delete widget.dashboard_chart;
		widget.dashboard_chart = new frappe.Chart(widget.chart_wrapper[0], {
			data: {
				labels: prog_items.map(p => p.label),
				datasets: [{ name: city, values: prog_items.map(p => p.value) }]
			},
			type: 'donut',
			height: widget.height || 280,
			colors: palette.slice(0, Math.max(1, prog_items.length)),
			maxSlices: 8,
			tooltipOptions: {
				formatTooltipY: d => `${d.toLocaleString('en-IN')} (${((d / total) * 100).toFixed(1)}%)`
			}
		});
	}

	function align_dashboard_chart_legends(dashboard) {
		let d = dashboard || frappe.dashboard;
		if (!d || !d.chart_group || !d.chart_group.widgets_list) return;

		d.chart_group.widgets_list.forEach(w => {
			if (w.chart_wrapper && w.chart_wrapper.length) {
				align_chart_legend($(w.chart_wrapper), w);
			}
		});
	}

	function align_chart_legend($wrapper, widget) {
		if (!$wrapper || !$wrapper.length) return;

		const do_align = () => {
			const $svg = $wrapper.find('svg');
			if (!$svg.length) return;

			// 1. Check if this is "Allocated Students by City" or a bar chart with many X labels
			let maxLabelDrop = 0;
			const $xAxis = $svg.find('.x.axis');
			const isDrilledDown = widget && widget._is_drilled_down;
			const chartName = widget && ((widget.chart_doc && widget.chart_doc.name) || widget.chart_name || widget.name);
			const shouldRotateLabels = $xAxis.length && !isDrilledDown && (chartName === 'Allocated Students by City' || $xAxis.children('g').length > 6);

			if (shouldRotateLabels) {
				const $groups = $xAxis.children('g');
				let raw_labels = null;
				if (widget && widget.dashboard_chart && widget.dashboard_chart.data && widget.dashboard_chart.data.labels) {
					raw_labels = widget.dashboard_chart.data.labels;
				} else if (widget && widget.report_result && widget.report_result.result) {
					raw_labels = widget.report_result.result
						.filter(r => r.city !== 'International Applicant')
						.map(r => r.city);
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
						origY = parseFloat($text.attr('y')) || 0;
						$text.data('orig-y', origY);
					}

					$text.attr({
						'transform': `rotate(-45, 0, ${origY})`,
						'text-anchor': 'end',
						'dx': '-6px',
						'dy': '4px'
					});

					const txt = $text.text() || '';
					const textDrop = Math.ceil(txt.length * 4.8);
					if (textDrop > maxLabelDrop) {
						maxLabelDrop = textDrop;
					}
				});
			}

			const labelExtraHeight = maxLabelDrop > 0 ? Math.max(45, maxLabelDrop + 10) : 0;

			// 2. Adjust Legend
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

					let curX = 0;
					let curY = 0;
					const rowHeight = 26;
					const svgWidth = $svg.width() || $wrapper.width() || 600;
					const maxRowWidth = Math.max(280, svgWidth - 50);

					$items.each(function() {
						const $item = $(this);
						let itemWidth = 140;
						try {
							const bbox = this.getBBox();
							if (bbox && bbox.width > 0) {
								itemWidth = Math.ceil(bbox.width) + 26;
							}
						} catch (e) {
							const txt = $item.find('text').text();
							itemWidth = Math.max(120, (txt ? txt.length * 8 : 100) + 26);
						}

						if (curX + itemWidth > maxRowWidth && curX > 0) {
							curX = 0;
							curY += rowHeight;
						}

						$item.attr('transform', `translate(${curX}, ${curY})`);
						curX += itemWidth;
					});

					legendExtraHeight = curY;
				}
			}

			if (labelExtraHeight > 0 || legendExtraHeight > 0) {
				const baseHeight = parseFloat($svg.data('base-height') || $svg.attr('height') || 300);
				if (!$svg.data('base-height')) {
					$svg.data('base-height', baseHeight);
				}
				const targetHeight = baseHeight + labelExtraHeight + legendExtraHeight;
				$svg.attr('height', targetHeight);
				$svg.css('height', targetHeight + 'px');
			}

			$svg.css('overflow', 'visible');
			$wrapper.css('overflow', 'visible');
			$wrapper.find('.chart-container').css('overflow', 'visible');
		};

		// Run immediately to eliminate glitch
		do_align();
		requestAnimationFrame(do_align);
		setTimeout(do_align, 100);
		setTimeout(do_align, 400);
	}

	$(window).off('resize.entrance_test_legend').on('resize.entrance_test_legend', () => {
		align_dashboard_chart_legends();
	});
})();
