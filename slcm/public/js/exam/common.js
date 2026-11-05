// Shared helpers for the examination screens in this folder.
frappe.provide('slcm.exam_ui');

// Default picture for a student without a photo, or whose photo file is missing
slcm.exam_ui.USER_ICON =
	'<svg class="slcm-user-icon" viewBox="0 0 24 24" width="62%" height="62%" fill="none" stroke="currentColor"' +
	' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
	'<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/></svg>';

// <img> that falls back to the user icon, or the icon alone when there is no photo
slcm.exam_ui.avatar = function (url, attrs) {
	if (!url) return slcm.exam_ui.USER_ICON;
	return '<img src="' + frappe.utils.escape_html(url) + '" alt="" ' + (attrs || '') +
		' onerror="this.outerHTML = slcm.exam_ui.USER_ICON">';
};

// Consolidated Report: one Excel of results across plans / programmes / terms.
// Opened from the Examination workspace, the Exam Planner and the result pages.
slcm.exam_ui.consolidated_report = function (exam_plan) {
		var d = new frappe.ui.Dialog({
			title: 'Download Consolidated Report',
			fields: [
				{ label: 'Exam Plan',     fieldname: 'exam_plan',     fieldtype: 'Link',   options: 'Exam Plan',     default: exam_plan || '',
					onchange() { d.set_value('course', ''); } },
				{ fieldtype: 'Column Break' },
				{ label: 'Academic Year', fieldname: 'academic_year', fieldtype: 'Link',   options: 'Academic Year' },
				{ fieldtype: 'Section Break' },
				{ label: 'Programme',     fieldname: 'programme',     fieldtype: 'Link',   options: 'Programme',
					onchange() { d.set_value('trimester', ''); d.set_value('course', ''); } },
				{ fieldtype: 'Column Break' },
				{ label: 'Trimester',     fieldname: 'trimester',     fieldtype: 'Link',   options: 'Academic Term',
					get_query() {
						return {
							query: 'slcm.slcm.page.examination_result.examination_result.trimester_link_query',
							filters: { programme: d.get_value('programme') },
						};
					},
					onchange() { d.set_value('course', ''); } },
				{ fieldtype: 'Section Break' },
				{ label: 'Batch',         fieldname: 'batch',         fieldtype: 'Link', options: 'SLCM Batch' },
				{ fieldtype: 'Section Break' },
				{ label: 'Report Type',   fieldname: 'report_type',   fieldtype: 'Select', options: 'Bulk\nCourse Based', default: 'Bulk' },
				{ fieldtype: 'Column Break' },
				{ label: 'Course',        fieldname: 'course',        fieldtype: 'Link',   options: 'Course', depends_on: 'eval:doc.report_type=="Course Based"',
					get_query() {
						return {
							query: 'slcm.slcm.page.examination_result.examination_result.course_link_query',
							filters: { exam_plan: d.get_value('exam_plan'), programme: d.get_value('programme'), trimester: d.get_value('trimester') },
						};
					} }
			],
			primary_action_label: 'Download Excel',
			primary_action: function(v) {
				var args = {};
				if (v.exam_plan)     args.exam_plan     = v.exam_plan;
				if (v.academic_year) args.academic_year = v.academic_year;
				if (v.programme)     args.programme     = v.programme;
				if (v.trimester)     args.trimester      = v.trimester;
				if (v.batch)         args.batch          = v.batch;
				if (v.report_type === 'Course Based') {
					if (!v.course) {
						frappe.msgprint({ message: __('Pick the Course, or set Report Type to Bulk for all courses.'), indicator: 'orange' });
						return;
					}
					args.course = v.course;
				}
				if (!Object.keys(args).length) {
					frappe.msgprint({ message: __('Please select at least one filter.'), indicator: 'orange' });
					return;
				}
				var url = '/api/method/slcm.slcm.page.term_result.term_result.download_consolidated_report?' + $.param(args);
				frappe.show_alert({ message: __('Preparing report…'), indicator: 'blue' });
				d.hide();

				fetch(url, {
					credentials: 'same-origin',
					headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token || '' }
				})
				.then(function(res) {
					if (!res.ok) {
						return res.json().catch(function () { return {}; }).then(function (errBody) {
							var msg = 'Server error: ' + res.status;
							try {
								if (errBody && errBody._server_messages) {
									var arr = JSON.parse(errBody._server_messages);
									if (arr && arr.length) {
										var first = JSON.parse(arr[0]);
										msg = first.message || msg;
									}
								} else if (errBody && errBody.exception) {
									msg = errBody.exception.split(': ').pop();
								}
							} catch (e) { /* fall back to generic message */ }
							throw new Error(msg);
						});
					}
					return res.blob();
				})
				.then(function(blob) {
					var a = document.createElement('a');
					a.href = URL.createObjectURL(blob);
					a.download = 'Consolidated_Report.xlsx';
					document.body.appendChild(a);
					a.click();
					a.remove();
					URL.revokeObjectURL(a.href);
					frappe.show_alert({ message: __('Report downloaded successfully.'), indicator: 'green' });
				})
				.catch(function(err) {
					frappe.msgprint({ title: __('Download Failed'), message: err.message || __('Could not download the report. Please try again.'), indicator: 'red' });
				});
			}
		});
		d.show();
};
