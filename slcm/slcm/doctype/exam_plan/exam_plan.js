// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on('Exam Plan', {
	refresh(frm) {
		if (!frm.is_new()) {

			frm.add_custom_button(__('Sync Courses to Schedule'), () => {
				frappe.call({
					method: 'slcm.slcm.doctype.exam_plan.exam_plan_api.sync_course_schedule_from_assignments',
					args: { exam_plan: frm.doc.name },
					callback: r => {
						frappe.show_alert({
							message: `${r.message || 0} mapped course(s) synced to schedule.`,
							indicator: 'green'
						});
						frm.reload_doc();
					}
				});
			}, __('Actions'));

			let btn = frm.add_custom_button(
				'View Courses to Map Schema',
				() => {
					_csm_open(frm.doc.name, frm.doc.exam_name || frm.doc.name);
				}
			);

			// Get icon
			let icon_html = frappe.utils.icon('layers', 'sm');

			// Set icon + text
			btn.html(`
				<span style="display:flex; align-items:center; gap:6px;">
					<span class="custom-icon">${icon_html}</span>
					<span>View Courses to Map Schema</span>
				</span>
			`);

			// Dark button style
			btn.removeClass('btn-default').addClass('btn-dark');

			btn.css({
				'background-color': '#2c2c2c',
				'color': '#ffffff',
				'border-color': '#2c2c2c'
			});

			// 🔥 FORCE ICON COLOR TO WHITE
			btn.find('svg').css({
				'stroke': '#ffffff',
				'fill': '#ffffff'
			});
		}
	}
});

/* ── Styles ───────────────────────────────────────── */
function _csm_inject_styles() {
	if (document.getElementById('csm-styles')) return;
	const s = document.createElement('style');
	s.id = 'csm-styles';
	s.textContent = `
		.csm-overlay {
			position: fixed; top: 0; left: 0; right: 0; bottom: 0;
			background: #f1f5f9; z-index: 9999;
			overflow-y: auto; display: flex; flex-direction: column;
		}
		.csm-topbar {
			background: #fff;
			border-bottom: 1px solid #e2e8f0;
			padding: 0 24px;
			display: flex; align-items: center; gap: 16px;
			height: 52px;
			position: sticky; top: 0; z-index: 10;
			box-shadow: 0 1px 4px rgba(0,0,0,0.05);
		}
		.csm-back-btn {
			background: none; border: none; cursor: pointer;
			color: #6366f1; font-weight: 600; font-size: 13px;
			padding: 5px 10px; border-radius: 5px;
			display: flex; align-items: center; gap: 5px;
			transition: background 0.15s; white-space: nowrap;
			flex-shrink: 0;
		}
		.csm-back-btn:hover { background: #eef2ff; }
		.csm-breadcrumb {
			font-size: 12.5px; color: #94a3b8;
			display: flex; align-items: center; gap: 5px;
		}
		.csm-breadcrumb span { color: #64748b; }
		.csm-breadcrumb strong { color: #1e293b; }
		.csm-breadcrumb .csm-sep { color: #cbd5e1; }
		.csm-log-link {
			margin-left: auto; font-size: 12px; font-weight: 600;
			color: #6366f1; text-decoration: none; white-space: nowrap;
			padding: 4px 10px; border-radius: 5px;
			border: 1px solid #e0e7ff; background: #f5f3ff;
			transition: background 0.15s;
			flex-shrink: 0;
		}
		.csm-log-link:hover { background: #ede9fe; }
		.csm-main {
			flex: 1; padding: 24px;
			max-width: 1400px; width: 100%; margin: 0 auto;
		}
		.csm-toolbar {
			display: flex; justify-content: space-between; align-items: center;
			margin-bottom: 14px; gap: 12px;
		}
		.csm-search-wrap { flex: 1; max-width: 520px; position: relative; }
		.csm-search-wrap::before {
			content: '🔍'; position: absolute; left: 11px; top: 50%;
			transform: translateY(-50%); font-size: 13px; pointer-events: none;
		}
		.csm-search {
			width: 100%;
			border: 1px solid #d1d5db; border-radius: 6px;
			padding: 8px 14px 8px 34px; font-size: 13px;
			transition: border-color 0.15s, box-shadow 0.15s;
			box-sizing: border-box;
		}
		.csm-search:focus {
			outline: none; border-color: #6366f1;
			box-shadow: 0 0 0 2px rgba(99,102,241,0.12);
		}
		.csm-btn-group { display: flex; gap: 8px; }
		.csm-btn-map {
			padding: 8px 20px; font-size: 13px; font-weight: 600;
			background: #1e293b; color: #fff; border: none;
			border-radius: 6px; cursor: pointer; transition: background 0.15s;
		}
		.csm-btn-map:hover { background: #334155; }
		.csm-btn-unmap {
			padding: 8px 20px; font-size: 13px; font-weight: 600;
			background: #fff; color: #64748b;
			border: 1px solid #d1d5db; border-radius: 6px;
			cursor: pointer; transition: all 0.15s;
		}
		.csm-btn-unmap:hover { background: #fef2f2; color: #dc2626; border-color: #fca5a5; }
		.csm-count-bar {
			font-size: 12px; color: #64748b;
			margin-bottom: 10px; font-weight: 500;
		}
		.csm-card {
			background: #fff; border-radius: 8px;
			border: 1px solid #e2e8f0;
			box-shadow: 0 1px 4px rgba(0,0,0,0.04);
			overflow: hidden;
		}
		.csm-tbl-wrap { overflow-x: auto; }
		table.csm-tbl {
			width: 100%; border-collapse: collapse; font-size: 13px;
		}
		table.csm-tbl th {
			background: #f8fafc; padding: 11px 14px;
			font-size: 11px; font-weight: 700; color: #64748b;
			text-transform: uppercase; letter-spacing: 0.06em;
			border-bottom: 2px solid #e2e8f0; white-space: nowrap;
			text-align: left;
		}
		table.csm-tbl td {
			padding: 11px 14px; border-bottom: 1px solid #f1f5f9;
			vertical-align: middle; color: #374151;
		}
		table.csm-tbl tr:last-child td { border-bottom: none; }
		table.csm-tbl tbody tr:hover > td { background: #fafbff; }
		table.csm-tbl input[type=checkbox] {
			width: 15px; height: 15px; cursor: pointer; accent-color: #6366f1;
		}
		.csm-course-name { font-weight: 600; color: #1e293b; font-size: 13px; }
		.csm-course-code { font-size: 11px; color: #94a3b8; margin-top: 2px; }
		.csm-badge {
			display: inline-block; font-size: 11.5px;
			padding: 3px 10px; border-radius: 12px; font-weight: 500;
			max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
			vertical-align: middle;
		}
		.csm-badge-eval { background: #dbeafe; color: #1d4ed8; }
		.csm-badge-grade { background: #dcfce7; color: #15803d; }
		.csm-badge-sync-success { background: #16a34a; color: #fff; margin-top: 4px; display: inline-block; }
		.csm-badge-sync-partial { background: #f59e0b; color: #fff; margin-top: 4px; display: inline-block; }
		.csm-enrolled-count { font-weight: 600; color: #1e293b; }
		.csm-dash { color: #cbd5e1; }
		.csm-empty {
			text-align: center; padding: 48px 16px;
			color: #94a3b8; font-size: 13px;
		}
		.csm-loading { text-align: center; padding: 32px; color: #94a3b8; }
		/* ── Inline notification (compact pill inside overlay) ── */
		.csm-notify {
			display: none; padding: 6px 18px; border-radius: 20px;
			font-size: 12px; font-weight: 600; margin: 0 auto 12px;
			width: fit-content; max-width: 90%;
			box-shadow: 0 1px 4px rgba(0,0,0,0.10);
			animation: csmFadeIn 0.15s ease;
		}
		@keyframes csmFadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
		.csm-notify-warn  { background: #fef9c3; border: 1px solid #fde047; color: #854d0e; display: block; }
		.csm-notify-ok    { background: #dcfce7; border: 1px solid #86efac; color: #166534; display: block; }
		.csm-notify-error { background: #fee2e2; border: 1px solid #fca5a5; color: #991b1b; display: block; }

		/* ── Map panel: readonly / edit modes ── */
		.csm-map-readonly, .csm-map-edit { }
		.csm-current-schemas {
			background: #f8fafc; border: 1px solid #e2e8f0;
			border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;
		}
		.csm-current-row {
			display: flex; align-items: center; justify-content: space-between;
			padding: 7px 0; border-bottom: 1px solid #f1f5f9;
		}
		.csm-current-row:last-child { border-bottom: none; }
		.csm-current-lbl {
			font-size: 11px; font-weight: 700; color: #64748b;
			text-transform: uppercase; letter-spacing: 0.05em;
		}
		.csm-change-confirm {
			background: #fffbeb; border: 1px solid #fde68a;
			border-radius: 7px; padding: 11px 14px; margin-bottom: 14px;
			font-size: 12.5px; color: #92400e; line-height: 1.5;
		}
		.csm-change-confirm strong { display: block; margin-bottom: 2px; }

		/* ── Custom panel (replaces frappe.ui.Dialog) ── */
		.csm-panel-backdrop {
			position: fixed; top: 0; left: 0; right: 0; bottom: 0;
			background: rgba(15,23,42,0.45); z-index: 10000;
			display: flex; align-items: center; justify-content: center;
		}
		.csm-panel {
			background: #fff; border-radius: 10px;
			box-shadow: 0 12px 40px rgba(0,0,0,0.22);
			width: 500px; max-width: 96vw;
			padding: 28px 28px 20px;
			animation: csmSlideIn 0.16s ease;
		}
		@keyframes csmSlideIn {
			from { opacity: 0; transform: translateY(-12px) scale(0.98); }
			to   { opacity: 1; transform: translateY(0)    scale(1); }
		}
		.csm-panel-title {
			font-size: 15px; font-weight: 700; color: #1e293b;
			margin-bottom: 20px; display: flex; align-items: center; gap: 10px;
		}
		.csm-panel-title .csm-panel-count {
			font-size: 11px; font-weight: 600; color: #6366f1;
			background: #eef2ff; padding: 2px 9px; border-radius: 20px;
		}
		.csm-panel-section { margin-bottom: 20px; }
		.csm-panel-section-label {
			font-size: 11px; font-weight: 700; color: #64748b;
			text-transform: uppercase; letter-spacing: 0.06em;
			margin-bottom: 7px; display: flex; align-items: center; gap: 6px;
		}
		.csm-panel-section-label .csm-lbl-badge {
			width: 8px; height: 8px; border-radius: 50%; display: inline-block;
		}
		.csm-lbl-badge-eval { background: #3b82f6; }
		.csm-lbl-badge-grade { background: #22c55e; }
		.csm-panel-select {
			width: 100%; border: 1px solid #d1d5db; border-radius: 7px;
			padding: 9px 12px; font-size: 13px; color: #374151;
			background: #fff; cursor: pointer;
			appearance: auto; box-sizing: border-box;
			transition: border-color 0.15s, box-shadow 0.15s;
		}
		.csm-panel-select:focus {
			outline: none; border-color: #6366f1;
			box-shadow: 0 0 0 2px rgba(99,102,241,0.12);
		}
		.csm-panel-select:disabled { background: #f8fafc; color: #94a3b8; cursor: default; }
		.csm-panel-footer {
			display: flex; justify-content: flex-end; gap: 10px;
			margin-top: 22px; padding-top: 16px;
			border-top: 1px solid #f1f5f9;
		}
		.csm-panel-btn-cancel {
			padding: 8px 22px; font-size: 13px; font-weight: 600;
			background: #fff; color: #64748b;
			border: 1px solid #d1d5db; border-radius: 6px; cursor: pointer;
			transition: all 0.15s;
		}
		.csm-panel-btn-cancel:hover { background: #f8fafc; border-color: #94a3b8; }
		.csm-panel-btn-apply {
			padding: 8px 22px; font-size: 13px; font-weight: 600;
			background: #6366f1; color: #fff;
			border: none; border-radius: 6px; cursor: pointer;
			transition: background 0.15s;
		}
		.csm-panel-btn-apply:hover { background: #4f46e5; }
		.csm-panel-btn-danger {
			padding: 8px 22px; font-size: 13px; font-weight: 600;
			background: #dc2626; color: #fff;
			border: none; border-radius: 6px; cursor: pointer;
			transition: background 0.15s;
		}
		.csm-panel-btn-danger:hover { background: #b91c1c; }

		/* ── Sortable column headers ── */
		table.csm-tbl th.csm-sortable {
			cursor: pointer; user-select: none;
		}
		table.csm-tbl th.csm-sortable:hover { background: #eff6ff; }
		table.csm-tbl th.csm-sortable .csm-sort-icon {
			display: inline-block; margin-left: 4px;
			font-size: 10px; color: #cbd5e1;
		}
		table.csm-tbl th.csm-sort-asc .csm-sort-icon,
		table.csm-tbl th.csm-sort-desc .csm-sort-icon { color: #6366f1; }

		/* ── Lock banner ── */
		.csm-lock-banner {
			background: #fff7ed; border: 1px solid #fed7aa;
			border-radius: 7px; padding: 10px 16px;
			font-size: 12.5px; color: #9a3412; font-weight: 600;
			margin-bottom: 14px; display: flex; align-items: center; gap: 8px;
		}
		.csm-lock-banner .csm-lock-icon { font-size: 15px; }

		/* ── Change reason textarea ── */
		.csm-reason-wrap { margin-top: 14px; display: none; }
		.csm-reason-wrap.csm-reason-visible { display: block; }
		.csm-reason-lbl {
			font-size: 11px; font-weight: 700; color: #64748b;
			text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px;
			display: flex; align-items: center; gap: 5px;
		}
		.csm-reason-lbl .csm-req { color: #dc2626; }
		.csm-reason-input {
			width: 100%; border: 1px solid #d1d5db; border-radius: 7px;
			padding: 9px 12px; font-size: 13px; color: #374151;
			resize: vertical; min-height: 72px; box-sizing: border-box;
			font-family: inherit; transition: border-color 0.15s, box-shadow 0.15s;
		}
		.csm-reason-input:focus {
			outline: none; border-color: #6366f1;
			box-shadow: 0 0 0 2px rgba(99,102,241,0.12);
		}
		.csm-reason-input.csm-input-error { border-color: #dc2626; box-shadow: 0 0 0 2px rgba(220,38,38,0.1); }

		/* ── Unmapped toggle button ── */
		.csm-btn-toggle {
			padding: 8px 16px; font-size: 12.5px; font-weight: 600;
			background: #f8fafc; color: #64748b;
			border: 1px solid #d1d5db; border-radius: 6px;
			cursor: pointer; transition: all 0.15s; white-space: nowrap;
		}
		.csm-btn-toggle:hover { background: #f1f5f9; border-color: #94a3b8; }
		.csm-btn-toggle.csm-toggle-active { background: #eef2ff; color: #6366f1; border-color: #a5b4fc; }

		/* ── Unmap checkboxes ── */
		.csm-unmap-opts { margin-bottom: 4px; }
		.csm-unmap-item {
			display: flex; align-items: center; gap: 12px;
			padding: 13px 14px; border: 1px solid #e2e8f0;
			border-radius: 7px; margin-bottom: 10px;
			cursor: pointer; transition: background 0.12s, border-color 0.12s;
		}
		.csm-unmap-item:hover { background: #fef2f2; border-color: #fca5a5; }
		.csm-unmap-item input[type=checkbox] {
			width: 16px; height: 16px; accent-color: #dc2626; cursor: pointer; flex-shrink: 0;
		}
		.csm-unmap-item-text { flex: 1; }
		.csm-unmap-item-title { font-size: 13px; font-weight: 600; color: #374151; }
		.csm-unmap-item-sub { font-size: 11.5px; color: #94a3b8; margin-top: 2px; }
		.csm-panel-warn {
			background: #fef9c3; border: 1px solid #fde047;
			border-radius: 6px; padding: 10px 14px;
			font-size: 12px; color: #854d0e; margin-bottom: 16px;
		}
	`;
	document.head.appendChild(s);
}

/* ── Open overlay ─────────────────────────────────── */
function _csm_open(exam_plan, exam_name) {
	_csm_inject_styles();
	$('#csm-overlay').remove();

	const $ov = $(`
		<div class="csm-overlay" id="csm-overlay">
			<div class="csm-topbar">
				<button class="csm-back-btn">&#8592; Back</button>
				<div class="csm-breadcrumb">
					<span>Examination Management</span>
					<span class="csm-sep">/</span>
					<span>Exam Plan</span>
					<span class="csm-sep">/</span>
					<strong>${_esc(exam_name)}</strong>
					<span class="csm-sep">/</span>
					<span>Course Schema</span>
				</div>
				<a class="csm-log-link" href="/app/schema-change-log" target="_blank">&#128203; View Change Log</a>
			</div>
			<div class="csm-main">
				<div class="csm-toolbar">
					<div class="csm-search-wrap">
						<input type="text" class="csm-search" placeholder="Search by Course Name or Course Code..."/>
					</div>
					<div class="csm-btn-group">
						<button class="csm-btn-toggle csm-do-toggle" title="Toggle unmapped courses visibility">Show All</button>
						<button class="csm-btn-map csm-do-map">Map Schema</button>
						<button class="csm-btn-unmap csm-do-unmap">Unmap Schema</button>
					</div>
				</div>
				<div class="csm-notify" id="csm-notify"></div>
			<div class="csm-count-bar">Loading courses…</div>
				<div class="csm-card">
					<div class="csm-tbl-wrap">
						<table class="csm-tbl">
							<thead>
								<tr>
									<th style="width:40px;"><input type="checkbox" class="csm-chk-all"/></th>
									<th class="csm-sortable" data-sort="course_name">Course Name <span class="csm-sort-icon">⇅</span></th>
									<th class="csm-sortable" data-sort="credit_value">Credits <span class="csm-sort-icon">⇅</span></th>
									<th class="csm-sortable" data-sort="programme">Programme <span class="csm-sort-icon">⇅</span></th>
									<th>Enrolled Students</th>
									<th class="csm-sortable" data-sort="evaluation_schema">Evaluation Schema <span class="csm-sort-icon">⇅</span></th>
									<th class="csm-sortable" data-sort="max_marks">Max Marks <span class="csm-sort-icon">⇅</span></th>
									<th class="csm-sortable" data-sort="grade_schema">Grade Schema <span class="csm-sort-icon">⇅</span></th>
								</tr>
							</thead>
							<tbody class="csm-tbody">
								<tr><td colspan="8" class="csm-loading">Loading…</td></tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>
		</div>
	`);

	$('body').append($ov);

	// Back button
	$ov.find('.csm-back-btn').on('click', () => $ov.remove());

	// Select all
	$ov.find('.csm-chk-all').on('change', function () {
		$ov.find('.csm-chk-row').prop('checked', $(this).is(':checked'));
	});

	// Search with debounce
	let _timer = null;
	$ov.find('.csm-search').on('input', function () {
		clearTimeout(_timer);
		_timer = setTimeout(() => _csm_load(exam_plan, $(this).val().trim(), $ov), 400);
	});

	// Sortable column headers
	$ov.find('th.csm-sortable').on('click', function () {
		const col = $(this).data('sort');
		const curCol = $ov.data('_sortCol');
		const curDir = $ov.data('_sortDir') || 'asc';
		const newDir = (col === curCol && curDir === 'asc') ? 'desc' : 'asc';
		$ov.data('_sortCol', col).data('_sortDir', newDir);
		// Update icons on all sortable headers
		$ov.find('th.csm-sortable').removeClass('csm-sort-asc csm-sort-desc')
			.find('.csm-sort-icon').text('⇅');
		$(this).addClass('csm-sort-' + newDir)
			.find('.csm-sort-icon').text(newDir === 'asc' ? '↑' : '↓');
		_csm_sort_render($ov);
	});

	// Map Schema
	$ov.find('.csm-do-map').on('click', () => {
		const sel = _csm_selected($ov);
		if (!sel.length) { _csm_notify($ov, 'Please select a course first.', 'warn'); return; }
		_csm_show_map_panel(exam_plan, sel, $ov);
	});

	// Unmap Schema
	$ov.find('.csm-do-unmap').on('click', () => {
		const sel = _csm_selected($ov);
		if (!sel.length) { _csm_notify($ov, 'Please select a course first.', 'warn'); return; }
		_csm_show_unmap_panel(exam_plan, sel, $ov);
	});

	// Toggle unmapped courses
	$ov.find('.csm-do-toggle').on('click', function () {
		const cur = !!$ov.data('_showUnmapped');
		const next = !cur;
		$ov.data('_showUnmapped', next);
		$(this).text(next ? 'Unmapped Only' : 'Show All')
			.toggleClass('csm-toggle-active', !next);
		_csm_sort_render($ov);
	});

	// Fetch settings, then load courses
	frappe.call({
		method: 'slcm.slcm.doctype.exam_plan.exam_plan_api.get_exam_settings',
		callback: r => {
			const settings = r.message || {};
			$ov.data('_settings', settings);

			// Apply show_unmapped_courses default
			const showUnmapped = settings.show_unmapped_courses !== undefined
				? !!settings.show_unmapped_courses : true;
			$ov.data('_showUnmapped', showUnmapped);
			const $toggleBtn = $ov.find('.csm-do-toggle');
			$toggleBtn.text(showUnmapped ? 'Unmapped Only' : 'Show All')
				.toggleClass('csm-toggle-active', !showUnmapped);

			// Apply lock date
			const lockDate = settings.schema_lock_date;
			if (lockDate && frappe.datetime.get_today() >= lockDate) {
				$ov.find('.csm-notify').before(
					`<div class="csm-lock-banner"><span class="csm-lock-icon">🔒</span>` +
					`Schema changes are locked as of ${lockDate}. Contact your administrator to make changes.</div>`
				);
				$ov.find('.csm-do-map, .csm-do-unmap').prop('disabled', true)
					.css({ opacity: 0.45, cursor: 'not-allowed' });
			}

			_csm_load(exam_plan, '', $ov);
		},
		error: () => {
			// Settings unavailable — proceed normally
			$ov.data('_showUnmapped', true);
			$ov.find('.csm-do-toggle').text('Unmapped Only');
			_csm_load(exam_plan, '', $ov);
		}
	});
}

/* ── Extract a readable message from a failed frappe.call ─── */
function _csm_error_message(r) {
	try {
		// If r is a jqXHR object, the actual response JSON is in r.responseJSON
		if (r && r.responseJSON) {
			r = r.responseJSON;
		}
		
		if (r && r._server_messages) {
			const msgs = JSON.parse(r._server_messages);
			if (msgs && msgs.length) {
				const last = JSON.parse(msgs[msgs.length - 1]);
				return {
					title: last.title || 'Error',
					message: last.message || last.title || 'An error occurred.'
				};
			}
		}
		if (r && r.exception) {
			const idx = r.exception.indexOf(': ');
			return { title: 'Error', message: idx !== -1 ? r.exception.slice(idx + 2) : r.exception };
		}
	} catch (e) {
		// fall through to default
	}
	return { title: 'Error', message: 'Something went wrong. Please check the browser console for details.' };
}

/* ── Inline notification (inside overlay) ─────────── */
function _csm_notify($ov, msg, type) {
	// type: 'warn' | 'ok' | 'error'
	const $n = $ov.find('#csm-notify');
	clearTimeout($n.data('_t'));
	// Remove any inline style set by previous jQuery .hide() calls
	$n.removeAttr('style')
		.removeClass('csm-notify-warn csm-notify-ok csm-notify-error')
		.addClass('csm-notify-' + (type || 'warn'))
		.text(msg);
	const t = setTimeout(() => {
		// Remove class (not .hide) so CSS display:none takes effect cleanly
		$n.removeClass('csm-notify-warn csm-notify-ok csm-notify-error');
	}, 3000);
	$n.data('_t', t);
}

/* ── Load & render ────────────────────────────────── */
function _csm_load(exam_plan, search, $ov) {
	$ov.find('.csm-tbody').html('<tr><td colspan="8" class="csm-loading">Loading…</td></tr>');
	frappe.call({
		method: 'slcm.slcm.doctype.exam_plan.exam_plan_api.get_courses_for_plan',
		args: { exam_plan, search },
		callback: r => {
			const courses = r.message || [];
			$ov.data('_courses', courses);
			$ov.find('.csm-chk-all').prop('checked', false);
			_csm_sort_render($ov);
		},
		error: r => {
			const { title, message } = _csm_error_message(r);
			$ov.find('.csm-tbody').html(`<tr><td colspan="8" class="csm-empty">Failed to load courses: ${_esc(message)}</td></tr>`);
			frappe.msgprint({ title, message, indicator: 'red' });
		}
	});
}

function _csm_sort_render($ov) {
	let courses = ($ov.data('_courses') || []).slice();
	// Filter: when showUnmapped is false, show only unmapped (no both schemas)
	if (!$ov.data('_showUnmapped')) {
		courses = courses.filter(c => !c.evaluation_schema || !c.grade_schema);
	}
	$ov.find('.csm-count-bar').text(`${courses.length} course(s)`);
	const col = $ov.data('_sortCol');
	const dir = $ov.data('_sortDir') || 'asc';
	if (col) {
		courses.sort((a, b) => {
			let av = a[col] != null ? a[col] : '';
			let bv = b[col] != null ? b[col] : '';
			const an = parseFloat(av), bn = parseFloat(bv);
			if (!isNaN(an) && !isNaN(bn) && av !== '' && bv !== '') {
				av = an; bv = bn;
			} else {
				av = String(av).toLowerCase();
				bv = String(bv).toLowerCase();
			}
			if (av < bv) return dir === 'asc' ? -1 : 1;
			if (av > bv) return dir === 'asc' ? 1 : -1;
			return 0;
		});
	}
	_csm_render(courses, $ov);
}

function _csm_render(courses, $ov) {
	const $tbody = $ov.find('.csm-tbody');
	if (!courses.length) {
		$tbody.html('<tr><td colspan="8" class="csm-empty">No courses found.</td></tr>');
		return;
	}
	$tbody.empty();
	courses.forEach(c => {
		const ev = c.evaluation_schema
			? `<span class="csm-badge csm-badge-eval" title="${_esc(c.evaluation_schema)}">${_esc(c.evaluation_schema)}</span>`
			: '<span class="csm-dash">--</span>';
		const gr = c.grade_schema
			? `<span class="csm-badge csm-badge-grade" title="${_esc(c.grade_schema)}">${_esc(c.grade_schema)}</span>`
			: '<span class="csm-dash">--</span>';

		// Mapping status badge
		let syncBadge = '';
		if (c.evaluation_schema && c.grade_schema) {
			syncBadge = '<span class="csm-badge csm-badge-sync-success">Sync : Success</span>';
		} else if (c.evaluation_schema || c.grade_schema) {
			syncBadge = '<span class="csm-badge csm-badge-sync-partial">Partially Mapped</span>';
		}

		const enrolledCount = (c.enrolled_students != null && c.enrolled_students !== 0)
			? `<span class="csm-enrolled-count">${c.enrolled_students}</span>`
			: '<span class="csm-dash">--</span>';

		$tbody.append(`
			<tr data-course="${_esc(c.name)}"
			    data-course-name="${_esc(c.course_name || c.course)}"
			    data-eval="${_esc(c.evaluation_schema || '')}"
			    data-grade="${_esc(c.grade_schema || '')}">
				<td><input type="checkbox" class="csm-chk-row" data-course="${_esc(c.name)}"/></td>
				<td>
					<div class="csm-course-name">${_esc(c.course_name || c.course)}</div>
					${c.course_code ? `<div class="csm-course-code">${_esc(c.course_code)}</div>` : ''}
					${syncBadge}
				</td>
				<td>${c.credit_value != null ? c.credit_value : '<span class="csm-dash">--</span>'}</td>
				<td>${c.programme ? _esc(c.programme) : '<span class="csm-dash">--</span>'}</td>
				<td>${enrolledCount}</td>
				<td>${ev}</td>
				<td>${c.max_marks !== '' && c.max_marks != null ? c.max_marks : '<span class="csm-dash">--</span>'}</td>
				<td>${gr}</td>
			</tr>
		`);
	});
}

function _csm_selected($ov) {
	const sel = [];
	$ov.find('.csm-chk-row:checked').each(function () { sel.push($(this).attr('data-course')); });
	return sel;
}

/* ── Map panel (readonly → confirm → edit flow) ──── */
function _csm_show_map_panel(exam_plan, selected, $ov) {
	const courseNames = selected.map(c => $ov.find(`tr[data-course="${c}"]`).data('course-name') || c);
	const courseLabel = courseNames.length === 1 ? courseNames[0] : `${courseNames.length} courses`;

	// Common current values across all selected rows
	const getCommon = attr => {
		const vals = selected.map(c => $ov.find(`tr[data-course="${c}"]`).attr(attr) || '');
		return vals.every(v => v === vals[0]) ? vals[0] : '';
	};
	const preEval = getCommon('data-eval');
	const preGrade = getCommon('data-grade');
	const alreadyMapped = !!(preEval && preGrade);

	// Build readonly summary HTML
	const roEval = preEval
		? `<span class="csm-badge csm-badge-eval">${_esc(preEval)}</span>`
		: '<span class="csm-dash">--</span>';
	const roGrade = preGrade
		? `<span class="csm-badge csm-badge-grade">${_esc(preGrade)}</span>`
		: '<span class="csm-dash">--</span>';

	const $bd = $(`
		<div class="csm-panel-backdrop">
			<div class="csm-panel">
				<div class="csm-panel-title">
					Map Schema
					<span class="csm-panel-count">${_esc(courseLabel)}</span>
				</div>

				<!-- Readonly view (shown when already mapped) -->
				<div class="csm-map-readonly" id="csm-map-readonly" style="${alreadyMapped ? '' : 'display:none'}">
					<div class="csm-current-schemas">
						<div class="csm-current-row">
							<span class="csm-current-lbl">Evaluation Schema</span>
							${roEval}
						</div>
						<div class="csm-current-row">
							<span class="csm-current-lbl">Grade Schema</span>
							${roGrade}
						</div>
					</div>
					<div class="csm-panel-footer" style="margin-top:0; padding-top:14px;">
						<button class="csm-panel-btn-cancel csm-pnl-cancel">Close</button>
						<button class="csm-panel-btn-apply csm-pnl-change">Change Schema</button>
					</div>
				</div>

				<!-- Confirm banner (shown after clicking Change) -->
				<div class="csm-map-confirm" id="csm-map-confirm" style="display:none">
					<div class="csm-change-confirm">
						<strong>Are you sure you want to change the schema?</strong>
						The previous values will be saved to the Schema Change Log before updating.
					</div>
				</div>

				<!-- Edit view -->
				<div class="csm-map-edit" id="csm-map-edit" style="${alreadyMapped ? 'display:none' : ''}">
					<div class="csm-panel-section">
						<div class="csm-panel-section-label">
							<span class="csm-lbl-badge csm-lbl-badge-eval"></span>
							Evaluation Schema
						</div>
						<select class="csm-panel-select" id="csm-eval-select" disabled>
							<option value="">Loading…</option>
						</select>
					</div>
					<div class="csm-panel-section">
						<div class="csm-panel-section-label">
							<span class="csm-lbl-badge csm-lbl-badge-grade"></span>
							Grade Schema
						</div>
						<select class="csm-panel-select" id="csm-grade-select" disabled>
							<option value="">Loading…</option>
						</select>
					</div>
					<!-- Change reason (shown when require_change_reason is on) -->
					<div class="csm-reason-wrap" id="csm-reason-wrap">
						<div class="csm-reason-lbl">Change Reason <span class="csm-req">*</span></div>
						<textarea class="csm-reason-input" id="csm-reason-input" placeholder="Enter a reason for this schema change…"></textarea>
					</div>
					<div class="csm-panel-footer">
						<button class="csm-panel-btn-cancel csm-pnl-back">${alreadyMapped ? 'Back' : 'Cancel'}</button>
						<button class="csm-panel-btn-apply csm-pnl-apply">Apply</button>
					</div>
				</div>
			</div>
		</div>
	`);

	$('body').append($bd);

	const settings = $ov.data('_settings') || {};
	let _evalAll = [], _gradeAll = [], _loaded = false;

	const _load_dropdowns = () => {
		if (_loaded) return;
		_loaded = true;
		frappe.call({
			method: 'slcm.slcm.doctype.exam_plan.exam_plan_api.get_schemas',
			args: {},
			callback: r => {
				_evalAll = (r.message || []).map(x => ({ name: x.name, label: x.schema_name || x.name }));
				_fill_select($bd.find('#csm-eval-select'), _evalAll, '-- Select Evaluation Schema --');
				const defEval = settings.default_evaluation_schema || '';
				$bd.find('#csm-eval-select').val(preEval || defEval || '');
			},
			error: r => {
				const { title, message } = _csm_error_message(r);
				$bd.find('#csm-eval-select').empty().append('<option value="">Failed to load</option>');
				frappe.msgprint({ title, message, indicator: 'red' });
			}
		});
		frappe.call({
			method: 'frappe.client.get_list',
			args: { doctype: 'Grading Schema', fields: ['name', 'schema_name'], limit: 200, order_by: 'name asc' },
			callback: r => {
				_gradeAll = (r.message || []).map(x => ({ name: x.name, label: x.schema_name || x.name }));
				_fill_select($bd.find('#csm-grade-select'), _gradeAll, '-- Select Grade Schema --');
				const defGrade = settings.default_grade_schema || '';
				$bd.find('#csm-grade-select').val(preGrade || defGrade || '');
			},
			error: r => {
				const { title, message } = _csm_error_message(r);
				$bd.find('#csm-grade-select').empty().append('<option value="">Failed to load</option>');
				frappe.msgprint({ title, message, indicator: 'red' });
			}
		});
	};

	// Populate a <select>
	function _fill_select($sel, items, placeholder) {
		$sel.empty().prop('disabled', false);
		$sel.append(`<option value="">${placeholder}</option>`);
		items.forEach(item => {
			$sel.append(`<option value="${_esc(item.name)}">${_esc(item.label || item.name)}</option>`);
		});
	}

	// Load dropdowns immediately if no current mapping
	if (!alreadyMapped) _load_dropdowns();

	// Close / back / change buttons
	$bd.on('click', function (e) { if (e.target === this) $bd.remove(); });
	$bd.find('.csm-pnl-cancel').on('click', () => $bd.remove());

	$bd.find('.csm-pnl-change').on('click', () => {
		$bd.find('#csm-map-readonly').hide();
		$bd.find('#csm-map-confirm').show();
		$bd.find('#csm-map-edit').show();
		$bd.find('.csm-pnl-back').show();
		if (settings.require_change_reason) {
			$bd.find('#csm-reason-wrap').addClass('csm-reason-visible');
		}
		_load_dropdowns();
	});

	$bd.find('.csm-pnl-back').on('click', () => {
		if (alreadyMapped) {
			$bd.find('#csm-map-readonly').show();
			$bd.find('#csm-map-confirm').hide();
			$bd.find('#csm-map-edit').hide();
			$bd.find('#csm-reason-wrap').removeClass('csm-reason-visible');
			$bd.find('#csm-reason-input').val('').removeClass('csm-input-error');
		} else {
			$bd.remove();
		}
	});

	// Apply
	$bd.find('.csm-pnl-apply').on('click', () => {
		const evalSel = $bd.find('#csm-eval-select').val() || null;
		const gradeSel = $bd.find('#csm-grade-select').val() || null;

		if (!evalSel && !gradeSel) {
			$bd.find('#csm-map-edit .csm-panel-section:first').prepend(
				'<div class="csm-change-confirm" style="background:#fee2e2;border-color:#fca5a5;color:#991b1b;margin-bottom:10px;">Please select at least one schema.</div>'
			);
			setTimeout(() => $bd.find('.csm-change-confirm[style*=fee2e2]').remove(), 3000);
			return;
		}

		// Validate: require_both_schemas
		if (settings.require_both_schemas && (!evalSel || !gradeSel)) {
			$bd.find('#csm-map-edit .csm-panel-section:first').prepend(
				'<div class="csm-change-confirm" style="background:#fee2e2;border-color:#fca5a5;color:#991b1b;margin-bottom:10px;">Both Evaluation Schema and Grade Schema are required.</div>'
			);
			setTimeout(() => $bd.find('.csm-change-confirm[style*=fee2e2]').remove(), 3000);
			return;
		}

		// Validate: require_change_reason (only when changing an existing mapping)
		const $reasonInput = $bd.find('#csm-reason-input');
		const reason = ($reasonInput.val() || '').trim() || null;
		if (settings.require_change_reason && alreadyMapped && !reason) {
			$reasonInput.addClass('csm-input-error').focus();
			setTimeout(() => $reasonInput.removeClass('csm-input-error'), 2500);
			return;
		}

		const assignments = selected.map(course => {
			const obj = { course };
			if (evalSel) obj.evaluation_schema = evalSel;
			if (gradeSel) obj.grade_schema = gradeSel;
			return obj;
		});

		const $btn = $bd.find('.csm-pnl-apply').prop('disabled', true).text('Saving…');
		
		const showError = r => {
			$btn.prop('disabled', false).text('Apply');
			const { title, message } = _csm_error_message(r);
			$bd.find('.csm-change-confirm').remove();
			$bd.find('.csm-panel-section:first').prepend(
				`<div class="csm-change-confirm" style="background:#fee2e2;border-color:#fca5a5;color:#991b1b;margin-bottom:10px;"><b>${_esc(title)}:</b> ${_esc(message)}</div>`
			);
		};

		frappe.call({
			method: 'slcm.slcm.doctype.exam_plan.exam_plan_api.save_course_schema',
			args: { exam_plan, assignments: JSON.stringify(assignments), reason: reason || '' },
			error: r => showError(r),
			callback: r => {
				if (r && r.exc) {
					return showError(r);
				}
				// Update DOM directly (fast path)
				selected.forEach(course => {
					const $row = $ov.find(`tr[data-course="${course}"]`);
					if (evalSel) {
						const lbl = (_evalAll.find(x => x.name === evalSel) || {}).label || evalSel;
						$row.find('td:nth-child(6)').html(`<span class="csm-badge csm-badge-eval" title="${_esc(evalSel)}">${_esc(lbl)}</span>`);
						$row.attr('data-eval', evalSel);
					}
					if (gradeSel) {
						const lbl = (_gradeAll.find(x => x.name === gradeSel) || {}).label || gradeSel;
						$row.find('td:nth-child(8)').html(`<span class="csm-badge csm-badge-grade" title="${_esc(gradeSel)}">${_esc(lbl)}</span>`);
						$row.attr('data-grade', gradeSel);
					}
				});
				$bd.remove();
				_csm_notify($ov, 'Schema mapped successfully.', 'ok');
				_csm_load(exam_plan, $ov.find('.csm-search').val().trim(), $ov);
			}
		});
	});
}

/* ── Unmap panel ──────────────────────────────────── */
function _csm_show_unmap_panel(exam_plan, selected, $ov) {
	// Read what's actually mapped from DOM data attributes
	const courseNames = selected.map(c => $ov.find(`tr[data-course="${c}"]`).data('course-name') || c);
	const courseLabel = courseNames.length === 1
		? courseNames[0]
		: `${courseNames.length} courses`;

	// Read current mapped values for display
	const curEval = selected.length === 1
		? ($ov.find(`tr[data-course="${selected[0]}"]`).attr('data-eval') || '') : '';
	const curGrade = selected.length === 1
		? ($ov.find(`tr[data-course="${selected[0]}"]`).attr('data-grade') || '') : '';

	const hasEval = selected.some(c => !!$ov.find(`tr[data-course="${c}"]`).attr('data-eval'));
	const hasGrade = selected.some(c => !!$ov.find(`tr[data-course="${c}"]`).attr('data-grade'));

	if (!hasEval && !hasGrade) {
		_csm_notify($ov, 'No schemas are mapped to the selected course(s).', 'warn');
		return;
	}

	const evalChk = hasEval ? `
		<label class="csm-unmap-item">
			<input type="checkbox" id="csm-unmap-eval"/>
			<div class="csm-unmap-item-text">
				<div class="csm-unmap-item-title">Unmap Evaluation Schema</div>
				<div class="csm-unmap-item-sub">${_esc(curEval) || 'Currently mapped'}</div>
			</div>
		</label>` : '';

	const gradeChk = hasGrade ? `
		<label class="csm-unmap-item">
			<input type="checkbox" id="csm-unmap-grade"/>
			<div class="csm-unmap-item-text">
				<div class="csm-unmap-item-title">Unmap Grade Schema</div>
				<div class="csm-unmap-item-sub">${_esc(curGrade) || 'Currently mapped'}</div>
			</div>
		</label>` : '';

	const $bd = $(`
		<div class="csm-panel-backdrop">
			<div class="csm-panel">
				<div class="csm-panel-title">
					Unmap Schema
					<span class="csm-panel-count">${_esc(courseLabel)}</span>
				</div>

				<div class="csm-panel-warn">
					Select which schema(s) to remove. This action cannot be undone.
				</div>

				<div class="csm-unmap-opts">
					${evalChk}
					${gradeChk}
				</div>

				<div class="csm-panel-footer">
					<button class="csm-panel-btn-cancel csm-pnl-cancel">Cancel</button>
					<button class="csm-panel-btn-danger csm-pnl-confirm">Confirm Unmap</button>
				</div>
			</div>
		</div>
	`);

	$('body').append($bd);

	$bd.on('click', function (e) { if (e.target === this) $bd.remove(); });
	$bd.find('.csm-pnl-cancel').on('click', () => $bd.remove());

	$bd.find('.csm-pnl-confirm').on('click', () => {
		const doEval = $bd.find('#csm-unmap-eval').is(':checked');
		const doGrade = $bd.find('#csm-unmap-grade').is(':checked');
		if (!doEval && !doGrade) {
			frappe.show_alert({ message: __('Select at least one schema to unmap.'), indicator: 'orange' });
			return;
		}

		const $btn = $bd.find('.csm-pnl-confirm').prop('disabled', true).text('Removing…');

		const onError = r => {
			$btn.prop('disabled', false).text('Confirm Unmap');
			const { title, message } = _csm_error_message(r);
			$bd.find('.csm-change-confirm').remove();
			$bd.find('.csm-panel-warn').after(
				`<div class="csm-change-confirm" style="background:#fee2e2;border-color:#fca5a5;color:#991b1b;margin-bottom:10px;padding:8px;border-radius:4px;border:1px solid;"><b>${_esc(title)}:</b> ${_esc(message)}</div>`
			);
		};

		const done = r => {
			if (r && r.exc) {
				onError(r);
				return;
			}
			// Update DOM directly
			selected.forEach(course => {
				const $row = $ov.find(`tr[data-course="${course}"]`);
				if (doEval) {
					$row.find('td:nth-child(6)').html('<span class="csm-dash">--</span>');
					$row.find('td:nth-child(7)').html('<span class="csm-dash">--</span>');
					$row.attr('data-eval', '');
				}
				if (doGrade) {
					$row.find('td:nth-child(8)').html('<span class="csm-dash">--</span>');
					$row.attr('data-grade', '');
				}
			});
			$bd.remove();
			frappe.show_alert({ message: __('Schema unmapped successfully.'), indicator: 'green' });
			_csm_load(exam_plan, $ov.find('.csm-search').val().trim(), $ov);
		};

		if (doEval && doGrade) {
			// Full unmap — delete the record entirely
			frappe.call({
				method: 'slcm.slcm.doctype.exam_plan.exam_plan_api.unmap_course_schema',
				args: { exam_plan, courses: JSON.stringify(selected) },
				callback: done,
				error: onError
			});
		} else {
			// Partial unmap — null out only the checked field
			const assignments = selected.map(course => {
				const obj = { course };
				if (doEval) obj.evaluation_schema = null;
				if (doGrade) obj.grade_schema = null;
				return obj;
			});
			frappe.call({
				method: 'slcm.slcm.doctype.exam_plan.exam_plan_api.save_course_schema',
				args: { exam_plan, assignments: JSON.stringify(assignments) },
				callback: done,
				error: onError
			});
		}
	});
}

/* ── Utility ─────────────────────────────────────── */
function _esc(s) {
	if (!s) return '';
	return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
