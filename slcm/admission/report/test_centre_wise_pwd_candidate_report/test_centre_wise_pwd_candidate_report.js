// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.query_reports["Test Center-wise Candidate Detail Report"] = {
	filters: [
		{
			fieldname: "entrance_test_provider",
			label: __("Entrance Test Provider / Test Centre"),
			fieldtype: "Link",
			options: "Entrance Test Provider"
		},
		{
			fieldname: "city",
			label: __("Test City"),
			fieldtype: "Link",
			options: "City"
		},
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
			fieldname: "allocation_date",
			label: __("Entrance Test Date"),
			fieldtype: "Date"
		},
		{
			fieldname: "entrance_test_status",
			label: __("Attendance / Status"),
			fieldtype: "Select",
			options: "\nAttended\nAbsent\nScheduled\nRescheduled\nNot Scheduled"
		},
		{
			fieldname: "is_pwd_only",
			label: __("Is PWD Only"),
			fieldtype: "Check",
			default: 0
		},
		{
			fieldname: "scribe_required_only",
			label: __("Scribe Required Only"),
			fieldtype: "Check",
			default: 0
		}
	],
	onload: function(report) {
		// Hook chart rendering to rotate X-axis labels at -45° and prevent glitch / revert
		if (!report._chart_layout_hooked) {
			report._chart_layout_hooked = true;

			const orig_get_chart_options = report.get_chart_options;
			report.get_chart_options = function(data) {
				let options = orig_get_chart_options ? orig_get_chart_options.apply(this, arguments) : (data ? data.chart : null);
				if (options) {
					options.axisOptions = options.axisOptions || {};
					options.axisOptions.seriesLabelSpaceRatio = 5;
					options.axisOptions.xAxisMode = "span";
					options.height = 360;
				}
				return options;
			};

			const orig_render_chart = report.render_chart;
			report.render_chart = function(options) {
				if (options) {
					options.axisOptions = options.axisOptions || {};
					options.axisOptions.seriesLabelSpaceRatio = 5;
					options.axisOptions.xAxisMode = "span";
					options.height = 360;
				}
				if (orig_render_chart) {
					orig_render_chart.apply(this, arguments);
				}

				if (report.chart) {
					const orig_chart_draw = report.chart.draw;
					report.chart.draw = function() {
						const ret = orig_chart_draw.apply(this, arguments);
						fix_tcwcdr_chart_labels(report.$chart, report);
						return ret;
					};

					const orig_chart_render = report.chart.render;
					report.chart.render = function() {
						const ret = orig_chart_render.apply(this, arguments);
						fix_tcwcdr_chart_labels(report.$chart, report);
						return ret;
					};
				}

				setup_chart_observer(report.$chart, report);
				fix_tcwcdr_chart_labels(report.$chart, report);
			};
		}

		// Scoping for Entrance Test Provider role
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

		// Add custom Download button at the top
		const $dl_btn = report.page.add_inner_button(__("Download Excel"), function() {
			open_download_modal(report);
		});
		$dl_btn.addClass("btn-primary");
	},
	after_refresh: function(report) {
		setup_chart_observer(report.$chart, report);
		fix_tcwcdr_chart_labels(report.$chart, report);
	}
};

function setup_chart_observer($wrapper, report) {
	if (!$wrapper || !$wrapper.length) return;
	const el = $wrapper[0];
	if (el._tcwcdr_observer) {
		el._tcwcdr_observer.disconnect();
	}

	let is_formatting = false;
	const observer = new MutationObserver(function() {
		if (is_formatting) return;
		const $unrotated = $wrapper.find(".x.axis text:not([data-rotated='1'])");
		if ($unrotated.length) {
			is_formatting = true;
			try {
				fix_tcwcdr_chart_labels($wrapper, report);
			} finally {
				is_formatting = false;
			}
		}
	});

	observer.observe(el, {
		childList: true,
		subtree: true
	});

	el._tcwcdr_observer = observer;
}

function fix_tcwcdr_chart_labels($wrapper, report) {
	if (!$wrapper || !$wrapper.length) return;

	const do_format = () => {
		const $svg = $wrapper.find("svg");
		if (!$svg.length) return;

		// 1. Rotate X-Axis labels -45° and restore full names
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

				// Restore full label text
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

		// 2. Adjust Legend position
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

		// 3. Expand SVG height to fit rotated labels + legend
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
	[50, 100, 200, 350, 500, 700, 850, 1000, 1200, 1500, 2000, 2500].forEach(delay => {
		setTimeout(do_format, delay);
	});
}

$(window).off("resize.tcwcdr_chart").on("resize.tcwcdr_chart", () => {
	const report = frappe.query_report;
	if (report && report.report_name === "Test Center-wise Candidate Detail Report" && report.$chart && report.$chart.length) {
		setup_chart_observer(report.$chart, report);
		fix_tcwcdr_chart_labels(report.$chart, report);
	}
});

function open_download_modal(report) {
	const filters = report.get_values() || {};
	const center_text = filters.entrance_test_provider || __("All Test Centres");
	const pwd_text = filters.is_pwd_only ? __("PWD Candidates Only") : __("All Applicants");
	const prog_text = filters.program || filters.program_level || __("All Programmes");

	const d = new frappe.ui.Dialog({
		title: __("Download Candidate Detail Report"),
		fields: [
			{
				fieldname: "summary_html",
				fieldtype: "HTML",
				options: `
					<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px 16px; margin-bottom: 16px; font-size: 13px;">
						<div style="font-weight: 600; color: #1e293b; margin-bottom: 8px;">${__("Active Filter Summary")}</div>
						<div style="display: grid; grid-template-columns: 140px 1fr; gap: 6px; color: #475569;">
							<div><b>${__("Test Centre")}:</b></div><div>${frappe.utils.escape_html(center_text)}</div>
							<div><b>${__("Programme")}:</b></div><div>${frappe.utils.escape_html(prog_text)}</div>
							<div><b>${__("Candidate Scope")}:</b></div><div>${frappe.utils.escape_html(pwd_text)}</div>
						</div>
					</div>
				`
			},
			{
				fieldname: "download_type",
				label: __("Select Download Option"),
				fieldtype: "Select",
				options: [
					{ label: __("Download Overall (Single Excel file for all candidates)"), value: "overall" },
					{ label: __("Download Center-wise (ZIP containing individual Excel file per center)"), value: "center_wise" }
				],
				default: "overall",
				reqd: 1
			}
		],
		primary_action_label: `<span style="display:inline-flex; align-items:center; gap:6px;">
			<i class="fa fa-download"></i> ${__("Download")}
		</span>`,
		primary_action: function(values) {
			d.hide();
			trigger_download(report, values.download_type);
		}
	});

	d.show();
}

function trigger_download(report, download_type) {
	const filters = report.get_values() || {};
	const is_zip = download_type === "center_wise";
	const action_label = is_zip ? __("Center-wise ZIP") : __("Overall Excel");

	frappe.show_progress(__("Preparing Download"), 30, 100, __("Generating {0}...", [action_label]));

	frappe.call({
		method: "slcm.admission.report.test_center_wise_candidate_detail_report.test_center_wise_candidate_detail_report.download_candidate_detail_excel",
		args: {
			filters: JSON.stringify(filters),
			download_type: download_type
		},
		callback: function(r) {
			frappe.show_progress(__("Preparing Download"), 100, 100, __("Done"));
			setTimeout(() => frappe.hide_progress(), 600);

			if (r.message && r.message.file_url) {
				const { file_url, filename, total_centres, total_records } = r.message;
				const a = document.createElement("a");
				a.href = file_url;
				a.download = filename;
				document.body.appendChild(a);
				a.click();
				document.body.removeChild(a);

				if (is_zip) {
					frappe.show_alert({
						message: __("✅ Downloaded ZIP folder with <b>{0}</b> center file(s) for <b>{1}</b> candidate(s).", [
							total_centres || 0,
							total_records || 0
						]),
						indicator: "green"
					}, 7);
				} else {
					frappe.show_alert({
						message: __("✅ Downloaded Overall Excel for <b>{0}</b> candidate(s).", [
							total_records || 0
						]),
						indicator: "green"
					}, 7);
				}
			}
		},
		error: function() {
			frappe.hide_progress();
		}
	});
}
