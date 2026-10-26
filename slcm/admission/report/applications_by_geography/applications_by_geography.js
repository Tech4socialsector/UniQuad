// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.query_reports["Applications by Geography"] = {
	"filters": [
		{
			"fieldname": "country",
			"label": __("Country"),
			"fieldtype": "Link",
			"options": "Country",
			"default": "India",
			"reqd": 0,
			"on_change": function(query_report) {
				const current_state = query_report.get_filter_value("state");
				if (current_state) {
					query_report.set_filter_value("state", "");
				}
				query_report.refresh();
			}
		},
		{
			"fieldname": "state",
			"label": __("State"),
			"fieldtype": "Link",
			"options": "State",
			"reqd": 0,
			"get_query": function() {
				const country = frappe.query_report ? frappe.query_report.get_filter_value("country") : null;
				if (country) {
					return {
						filters: {
							country: country
						}
					};
				}
				return {};
			}
		},
		{
			"fieldname": "academic_year",
			"label": __("Academic Year"),
			"fieldtype": "Link",
			"options": "Academic Year",
			"reqd": 0
		},
		{
			"fieldname": "admission_cycle",
			"label": __("Admission Cycle"),
			"fieldtype": "Link",
			"options": "Admission Cycle",
			"reqd": 0,
			"get_query": function() {
				const year = frappe.query_report ? frappe.query_report.get_filter_value("academic_year") : null;
				if (year) {
					return {
						filters: {
							admission_year: year
						}
					};
				}
				return {};
			}
		},
		{
			"fieldname": "program",
			"label": __("Programme"),
			"fieldtype": "Link",
			"options": "Programme",
			"reqd": 0
		}
	],
	after_refresh: function(report) {
		setup_chart_observer(report.$chart, report);
		fix_chart_layout_and_labels(report.$chart, report);
	}
};

function setup_chart_observer($wrapper, report) {
	if (!$wrapper || !$wrapper.length) return;
	const el = $wrapper[0];
	if (el._abg_chart_observer) {
		el._abg_chart_observer.disconnect();
	}

	let is_formatting = false;
	const observer = new MutationObserver(function() {
		if (is_formatting) return;
		const $unrotated = $wrapper.find(".x.axis text:not([data-rotated='1'])");
		if ($unrotated.length) {
			is_formatting = true;
			try {
				fix_chart_layout_and_labels($wrapper, report);
			} finally {
				is_formatting = false;
			}
		}
	});

	observer.observe(el, {
		childList: true,
		subtree: true
	});

	el._abg_chart_observer = observer;
}

function fix_chart_layout_and_labels($wrapper, report) {
	if (!$wrapper || !$wrapper.length) return;

	const do_format = () => {
		const $svg = $wrapper.find("svg");
		if (!$svg.length) return;

		// 1. Format X-Axis Labels (rotate -45° and ensure full names)
		let maxLabelDrop = 0;
		const $xAxis = $svg.find(".x.axis");
		if ($xAxis.length) {
			const $groups = $xAxis.children("g");
			let raw_labels = null;
			if (report && report.chart && report.chart.data && report.chart.data.labels) {
				raw_labels = report.chart.data.labels;
			} else if (report && report.chart_options && report.chart_options.data && report.chart_options.data.labels) {
				raw_labels = report.chart_options.data.labels;
			}

			$groups.each(function(i) {
				const $g = $(this);
				const $text = $g.find("text");
				if (!$text.length) return;

				if (raw_labels && raw_labels[i]) {
					$text.text(raw_labels[i]);
				}

				let origY = $text.data("orig-y");
				if (origY === undefined) {
					origY = parseFloat($text.attr("y")) || 0;
					$text.data("orig-y", origY);
				}

				$text.attr({
					"transform": `rotate(-45, 0, ${origY})`,
					"text-anchor": "end",
					"dx": "-6px",
					"dy": "4px",
					"data-rotated": "1"
				});

				const txt = $text.text() || "";
				const textDrop = Math.ceil(txt.length * 4.8);
				if (textDrop > maxLabelDrop) {
					maxLabelDrop = textDrop;
				}
			});
		}

		const labelExtraHeight = maxLabelDrop > 0 ? Math.max(45, maxLabelDrop + 10) : 0;

		// 2. Adjust Legend position and alignment
		let legendExtraHeight = 0;
		const $legend = $svg.find(".chart-legend");
		if ($legend.length) {
			const $items = $legend.children("g");
			if ($items.length) {
				let origLegendTransform = $legend.data("orig-transform");
				if (!origLegendTransform) {
					origLegendTransform = $legend.attr("transform") || "";
					$legend.data("orig-transform", origLegendTransform);
				}

				if (labelExtraHeight > 0 && origLegendTransform) {
					const match = origLegendTransform.match(/translate\(([^,]+),\s*([^)]+)\)/);
					if (match) {
						const lx = parseFloat(match[1]) || 0;
						const ly = parseFloat(match[2]) || 0;
						$legend.attr("transform", `translate(${lx}, ${ly + labelExtraHeight})`);
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

				legendExtraHeight = curY;
			}
		}

		// 3. Update total SVG height and container styles
		if (labelExtraHeight > 0 || legendExtraHeight > 0) {
			const baseHeight = parseFloat($svg.data("base-height") || $svg.attr("height") || 360);
			if (!$svg.data("base-height")) {
				$svg.data("base-height", baseHeight);
			}
			const targetHeight = baseHeight + labelExtraHeight + legendExtraHeight;
			$svg.attr("height", targetHeight);
			$svg.css("height", targetHeight + "px");
		}

		$svg.css("overflow", "visible");
		$wrapper.css("overflow", "visible");
		$wrapper.find(".chart-container").css("overflow", "visible");
	};

	do_format();
	requestAnimationFrame(do_format);
	setTimeout(do_format, 100);
	setTimeout(do_format, 400);
}

$(window).off("resize.abg_report_chart").on("resize.abg_report_chart", () => {
	const report = frappe.query_report;
	if (report && report.$chart && report.$chart.length) {
		fix_chart_layout_and_labels(report.$chart, report);
	}
});
