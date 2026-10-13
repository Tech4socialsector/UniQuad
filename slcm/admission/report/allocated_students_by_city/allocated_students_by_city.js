// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.query_reports["Allocated Students by City"] = {
	filters: [
		{
			fieldname: "academic_year",
			label: __("Academic Year"),
			fieldtype: "Link",
			options: "Academic Year"
		},
		{
			fieldname: "admission_cycle",
			label: __("Admission Cycle"),
			fieldtype: "Link",
			options: "Admission Cycle"
		},
		{
			fieldname: "program_level",
			label: __("Programme Level"),
			fieldtype: "Select",
			options: "\nUndergraduate\nPostgraduate\nResearch Course"
		},
		{
			fieldname: "program",
			label: __("Programme"),
			fieldtype: "Link",
			options: "Programme"
		},
		{
			fieldname: "entrance_test_list",
			label: __("Entrance Test List"),
			fieldtype: "Link",
			options: "Entrance Test List"
		},
		{
			fieldname: "entrance_test_provider",
			label: __("Entrance Test Provider"),
			fieldtype: "Link",
			options: "Entrance Test Provider"
		},
		{
			fieldname: "allocation_date",
			label: __("Entrance Test Date"),
			fieldtype: "Date"
		}
	],
	onload: function(report) {
		if (frappe.user_roles.includes("Entrance Test Provider") &&
			!frappe.user_roles.includes("System Manager") &&
			!frappe.user_roles.includes("Entrance Test Admin")) {
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Entrance Test Provider",
					filters: { user: frappe.session.user },
					fieldname: "name"
				},
				callback: function(r) {
					if (r.message && r.message.name) {
						report.set_filter_value("entrance_test_provider", r.message.name);
						const field = report.get_filter("entrance_test_provider");
						if (field) {
							field.df.read_only = 1;
							field.refresh();
						}
					}
				}
			});
		}

		if (!report.get_filter_value("academic_year")) {
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
					if (r.message && r.message.length && !report.get_filter_value("academic_year")) {
						const today = frappe.datetime.get_today();
						let active = r.message.find(y => y.year_start_date && y.year_end_date && y.year_start_date <= today && y.year_end_date >= today);
						if (!active) active = r.message[0];
						report.set_filter_value("academic_year", active.name);
					}
				}
			});
		}
	},

	get_chart_data: function(columns, result) {
		if (!result || !result.length) return null;

		// Exclude international applicant row from chart
		const rows = result.filter(r => r.city !== "International Applicant");
		if (!rows.length) return null;

		// Extract programme columns (prefixed with prog_)
		const prog_cols = (columns || []).filter(c => c.fieldname && c.fieldname.startsWith("prog_"));

		// Keep only programmes that have at least one count > 0 in the displayed rows
		const active_prog_cols = prog_cols.filter(c => rows.some(r => (r[c.fieldname] || 0) > 0));

		const labels = rows.map(r => r.city);
		let datasets = [];

		if (active_prog_cols.length > 0) {
			datasets = active_prog_cols.map(c => ({
				name: c.label,
				values: rows.map(r => r[c.fieldname] || 0)
			}));
		} else {
			datasets = [
				{
					name: __("Allocated Count"),
					values: rows.map(r => r.allocated_count || 0)
				}
			];
		}

		const palette = [
			"#2490EF",
			"#48C774",
			"#FF9F43",
			"#EA5455",
			"#7367F0",
			"#1E9FF2",
			"#10AC84",
			"#EE5253",
			"#F368E0",
			"#00D2D3",
			"#6C5CE7",
			"#FFA502"
		];

		return {
			data: {
				labels: labels,
				datasets: datasets
			},
			type: "bar",
			barOptions: {
				stacked: true,
				spaceRatio: 0.3
			},
			height: 340,
			colors: palette.slice(0, Math.max(1, datasets.length)),
			axisOptions: {
				xAxisMode: "span"
			},
			tooltipOptions: {
				formatTooltipY: d => d.toLocaleString("en-IN")
			}
		};
	},

	after_refresh: function(report) {
		setup_report_drilldown(report);
		fix_chart_legend_alignment(report.$chart);
	}
};

function fix_chart_legend_alignment($wrapper) {
	if (!$wrapper || !$wrapper.length) return;

	const do_align = () => {
		const $svg = $wrapper.find("svg");
		if (!$svg.length) return;
		const $legend = $svg.find(".chart-legend");
		if (!$legend.length) return;

		const $items = $legend.children("g");
		if (!$items.length) return;

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
				const txt = $item.find("text").text();
				itemWidth = Math.max(120, (txt ? txt.length * 8 : 100) + 26);
			}

			if (curX + itemWidth > maxRowWidth && curX > 0) {
				curX = 0;
				curY += rowHeight;
			}

			$item.attr("transform", `translate(${curX}, ${curY})`);
			curX += itemWidth;
		});

		if (curY > 0) {
			const baseHeight = parseFloat($svg.data("base-height") || $svg.attr("height") || 340);
			if (!$svg.data("base-height")) {
				$svg.data("base-height", baseHeight);
			}
			const targetHeight = baseHeight + curY;
			$svg.attr("height", targetHeight);
			$svg.css("height", targetHeight + "px");
			$svg.css("overflow", "visible");
		}
	};

	setTimeout(do_align, 60);
	setTimeout(do_align, 200);
	setTimeout(do_align, 500);
}

function setup_report_drilldown(report) {
	if (!report || !report.$chart || !report.$chart.length) return;

	const $chartWrapper = report.$chart;
	$chartWrapper.find('.report-drilldown-toolbar').remove();

	// Style chart cursor
	$chartWrapper.find('.frappe-chart').css('cursor', 'pointer');

	// Add helper hint banner if in overview mode
	if (!report._is_drilled_down) {
		$(`
			<div class="report-drilldown-toolbar text-muted small" style="margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
				<span><i class="fa fa-info-circle text-info mr-1"></i> ${__('Click any city bar to drill down into its programme-wise distribution')}</span>
			</div>
		`).insertBefore($chartWrapper.find('.frappe-chart'));
	}

	function handle_city_select(city) {
		if (!city || report._is_drilled_down) return;
		drilldown_into_city(report, city);
	}

	// Listen for Frappe Charts native data-select event
	$chartWrapper.off('data-select.city_drill');
	$chartWrapper.on('data-select.city_drill', function(e) {
		const city = e.label || (e.originalEvent && e.originalEvent.label);
		if (city) handle_city_select(city);
	});

	// Also listen on SVG bar clicks as a reliable fallback
	$chartWrapper.off('click.city_bar_click');
	$chartWrapper.on('click.city_bar_click', '.data-point, rect.bar, path.bar, g.dataset-units rect', function() {
		if (report._is_drilled_down) return;
		const ptIdx = $(this).attr('data-point-index');
		if (ptIdx !== undefined && report.chart && report.chart.data && report.chart.data.labels) {
			const city = report.chart.data.labels[parseInt(ptIdx)];
			if (city) handle_city_select(city);
		}
	});
}

function drilldown_into_city(report, city) {
	if (!report.data || !report.columns) return;

	const cityRow = report.data.find(r => r.city === city);
	if (!cityRow) return;

	// Extract active programmes for this city
	const prog_cols = report.columns.filter(c => c.fieldname && c.fieldname.startsWith('prog_'));
	const prog_items = [];
	prog_cols.forEach(col => {
		const val = cityRow[col.fieldname] || 0;
		if (val > 0) {
			prog_items.push({
				label: col.label,
				value: val
			});
		}
	});

	if (!prog_items.length) {
		frappe.show_alert({
			message: __('No allocated candidates found for {0}', [city]),
			indicator: 'orange'
		});
		return;
	}

	report._is_drilled_down = true;
	report._drilled_city = city;

	const $chartWrapper = report.$chart;
	$chartWrapper.find('.report-drilldown-toolbar').remove();

	const total = cityRow.allocated_count || prog_items.reduce((acc, p) => acc + p.value, 0);

	const $toolbar = $(`
		<div class="report-drilldown-toolbar" style="margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; background: var(--bg-light-gray, #f8f9fa); padding: 8px 14px; border-radius: 6px; border: 1px solid var(--border-color, #d1d8dd);">
			<div>
				<span class="font-weight-bold" style="font-size: 15px; color: var(--text-color, #111827);">${frappe.utils.escape_html(city)}</span>
				<span class="text-muted ml-2">— ${__('Programme Breakdown')} (<b>${total.toLocaleString('en-IN')}</b> ${__('Applicants')})</span>
			</div>
			<button class="btn btn-xs btn-primary btn-back-to-cities" style="font-weight: 500;">
				<i class="fa fa-arrow-left mr-1"></i> ${__('Back to All Cities')}
			</button>
		</div>
	`).insertBefore($chartWrapper.find('.frappe-chart'));

	$toolbar.find('.btn-back-to-cities').on('click', function() {
		report._is_drilled_down = false;
		report._drilled_city = null;
		$toolbar.remove();
		const original_options = report.get_chart_options(report.raw_data);
		if (original_options) {
			report.render_chart(original_options);
			setup_report_drilldown(report);
		}
	});

	const palette = [
		'#2490EF', '#48C774', '#FF9F43', '#EA5455', '#7367F0',
		'#1E9FF2', '#10AC84', '#EE5253', '#F368E0', '#00D2D3'
	];

	// Render Donut chart for the selected city
	const donut_options = {
		data: {
			labels: prog_items.map(p => p.label),
			datasets: [
				{
					name: city,
					values: prog_items.map(p => p.value)
				}
			]
		},
		type: 'donut',
		height: 320,
		colors: palette.slice(0, Math.max(1, prog_items.length)),
		maxSlices: 10,
		tooltipOptions: {
			formatTooltipY: d => `${d.toLocaleString('en-IN')} (${((d / total) * 100).toFixed(1)}%)`
		}
	};

	report.render_chart(donut_options);
}

