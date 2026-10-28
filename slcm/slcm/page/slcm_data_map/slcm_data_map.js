frappe.pages['slcm-data-map'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'SLCM Data Entry Map',
		single_column: true,
	});

	const page = wrapper.page;

	// ── Default stage definitions ─────────────────────────────────────────────
	const DEFAULT_STAGES = [
		{
			num: 1, emoji: '🔧', title: 'Master Lookups',
			note: 'No dependencies — start here', color: '#6366f1',
			docs: [
				{ name: 'Gender',             dt: 'Gender' },
				{ name: 'Student Category',   dt: 'Student Category' },
				{ name: 'Skill',              dt: 'Skill' },
				{ name: 'Designation',        dt: 'SLCM Designation' },
				{ name: 'Condonation Reason', dt: 'Condonation Reason' },
				{ name: 'Department',         dt: 'SLCM Department' },
				{ name: 'Faculty',            dt: 'Faculty' },
				{ name: 'Room',               dt: 'Room' },
			],
		},
		{
			num: 2, emoji: '📅', title: 'Academic Calendar',
			note: 'Needs: Department', color: '#0ea5e9',
			docs: [
				{ name: 'Academic Year',    dt: 'Academic Year' },
				{ name: 'Academic Term',    dt: 'Academic Term' },
				{ name: 'Academic Holiday', dt: 'Academic Holiday' },
			],
		},
		{
			num: 3, emoji: '🏫', title: 'Programme Structure',
			note: 'Needs: Stage 1 + 2', color: '#10b981',
			docs: [
				{ name: 'Course Master',       dt: 'Course Master' },
				{ name: 'Course',              dt: 'Course' },
				{ name: 'Programme',             dt: 'Programme' },
				{ name: 'Curriculum',          dt: 'Curriculum' },
				{ name: 'Batch',              dt: 'Batch' },
				{ name: 'Classes',             dt: 'Classes' },
				{ name: 'Class Configuration', dt: 'Class Configuration' },
				{ name: 'Time Table',      dt: 'Time Table' },
			],
		},
		{
			num: 4, emoji: '📊', title: 'Assessment Config',
			note: 'Needs: Stage 3', color: '#f59e0b',
			docs: [
				{ name: 'Grading Schema',          dt: 'Grading Schema' },
				{ name: 'Evaluation Schema',       dt: 'Evaluation Schema' },
				{ name: 'Exam Assessment Type',    dt: 'Exam Assessment Type' },
				{ name: 'Exam Component',          dt: 'Exam Component' },
				{ name: 'CGPA Percentage Scale',   dt: 'CGPA Percentage Scale' },
				{ name: 'Course Schema Assignment',dt: 'Course Schema Assignment' },
				{ name: 'Access Result Settings',  dt: 'Access Result Settings' },
				{ name: 'Publish Result Setting',  dt: 'Publish Result Setting' },
			],
		},
		{
			num: 5, emoji: '🎓', title: 'Students',
			note: 'Needs: Stage 1–3', color: '#8b5cf6',
			docs: [
				{ name: 'Student Master',        dt: 'Student Master' },
				{ name: 'Student Parent',        dt: 'Student Parent' },
			],
		},
		{
			num: 6, emoji: '📋', title: 'Enrollment',
			note: 'Needs: Stage 5', color: '#06b6d4',
			docs: [
				{ name: 'Program Enrollment',        dt: 'Program Enrollment' },
				{ name: 'Student Enrollment',        dt: 'Student Enrollment' },
				{ name: 'Student Enrollment Course', dt: 'Student Enrollment Course' },
			],
		},
		{
			num: 7, emoji: '✅', title: 'Attendance',
			note: 'Needs: Stage 6', color: '#14b8a6',
			docs: [
				{ name: 'Attendance Session',             dt: 'Attendance Session' },
				{ name: 'Attendance Session Student',     dt: 'Attendance Session Student' },
				{ name: 'Student Attendance',             dt: 'Student Attendance' },
				{ name: 'FA MFA Application',             dt: 'FA MFA Application' },
				{ name: 'Student Attendance Condonation', dt: 'Student Attendance Condonation' },
			],
		},
		{
			num: 8, emoji: '📝', title: 'Examination & Marks',
			note: 'Needs: Stage 6 + 7', color: '#ef4444',
			docs: [
				{ name: 'Exam Plan',                    dt: 'Exam Plan' },
				{ name: 'Student Course Marks',         dt: 'Student Course Marks' },
				{ name: 'Student Marks Entry',          dt: 'Student Marks Entry' },
				{ name: 'Re Exam Registration',         dt: 'Re Exam Registration' },
				{ name: 'Improvement Exam Registration',dt: 'Improvement Exam Registration' },
				{ name: 'Grade Appeal',                 dt: 'Grade Appeal' },
				{ name: 'Exam Barcode',                 dt: 'Exam Barcode' },
				{ name: 'Student Result Publish',       dt: 'Student Result Publish' },
				{ name: 'Student Transcript',           dt: 'Student Transcript' },
			],
		},
		{
			num: 9, emoji: '💰', title: 'Fees',
			note: 'Needs: Stage 5–6', color: '#f97316',
			docs: [
				{ name: 'Fee Structure', dt: 'Fee Structure' },
				{ name: 'Fee Invoice',   dt: 'Fee Invoice' },
				{ name: 'Fee Payment',   dt: 'Fee Payment' },
			],
		},
		{
			num: 10, emoji: '📥', title: 'Admission',
			note: 'Parallel to Stage 5 — independent', color: '#ec4899',
			docs: [
				{ name: 'Admission Cycle',       dt: 'Admission Cycle' },
				{ name: 'Applicant',             dt: 'Applicant' },
				{ name: 'Admission Application', dt: 'Admission Application' },
				{ name: 'Offer Letter',          dt: 'Offer Letter' },
				{ name: 'Merit List',            dt: 'Merit List' },
			],
		},
		{
			num: 11, emoji: '🪪', title: 'ID Cards',
			note: 'Needs: Stage 5', color: '#6366f1',
			docs: [
				{ name: 'ID Card Template',   dt: 'ID Card Template' },
				{ name: 'ID Card Generation', dt: 'ID Card Generation' },
			],
		},
		{
			num: 12, emoji: '🏛️', title: 'Venue Booking',
			note: 'Needs: Room (Stage 1)', color: '#0ea5e9',
			docs: [
				{ name: 'Venue Booking', dt: 'Venue Booking' },
			],
		},
		{
			num: 13, emoji: '🏆', title: 'Promotion',
			note: 'Needs: Stage 6 + Exam results', color: '#10b981',
			docs: [
				{ name: 'Promotion Policy',  dt: 'Promotion Policy' },
				{ name: 'Student Promotion', dt: 'Student Promotion' },
			],
		},
		{
			num: 14, emoji: '🏠', title: 'Hostel',
			note: 'Needs: Stage 5', color: '#8b5cf6',
			docs: [
				{ name: 'Hostel',            dt: 'Hostel' },
				{ name: 'Hostel Block',      dt: 'Hostel Block' },
				{ name: 'Hostel Floor',      dt: 'Hostel Floor' },
				{ name: 'Hostel Room',       dt: 'Hostel Room' },
				{ name: 'Hostel Bed',        dt: 'Hostel Bed' },
				{ name: 'Hostel Allocation', dt: 'Hostel Allocation' },
			],
		},
		{
			num: 15, emoji: '💼', title: 'Placement',
			note: 'Needs: Stage 5', color: '#f59e0b',
			docs: [
				{ name: 'Placement Opportunity', dt: 'Placement Opportunity' },
				{ name: 'Placement Application', dt: 'Placement Application' },
				{ name: 'Placement Offer',       dt: 'Placement Offer' },
			],
		},
	];

	const QUICKSTART = [
		'Department', 'Academic Year', 'Academic Term',
		'Programme', 'Course', 'Batch', 'Classes',
		'Student Master', 'Student Enrollment', 'Student Enrollment Course',
		'Exam Plan', 'Student Course Marks', 'Student Result Publish',
	];

	// ── State ─────────────────────────────────────────────────────────────────
	let STAGES = load_stages();
	let edit_mode = false;
	let last_counts = null;
	let drag_src_idx = null;

	function load_stages() {
		try {
			const saved = localStorage.getItem('sdm_custom_stages');
			if (saved) {
				// Batch / Department / Designation were renamed to avoid clashing with ERPNext.
				const renamed = { 'Batch': 'SLCM Batch', 'Department': 'SLCM Department', 'Designation': 'SLCM Designation' };
				const stages = JSON.parse(saved);
				stages.forEach((s) => (s.docs || []).forEach((d) => { d.dt = renamed[d.dt] || d.dt; }));
				return stages;
			}
		} catch (e) { /* ignore */ }
		return JSON.parse(JSON.stringify(DEFAULT_STAGES));
	}

	function persist_stages() {
		localStorage.setItem('sdm_custom_stages', JSON.stringify(STAGES));
	}

	// ── Toolbar buttons ───────────────────────────────────────────────────────
	const $btn_edit   = $(page.add_inner_button('✏️ Edit', enter_edit_mode));
	const $btn_save   = $(page.add_inner_button('✓ Save', save_edit)).closest('button, .btn, li');
	const $btn_cancel = $(page.add_inner_button('✕ Cancel', cancel_edit)).closest('button, .btn, li');
	const $btn_reset  = $(page.add_inner_button('↺ Reset', reset_to_default)).closest('button, .btn, li');

	$btn_save.hide();
	$btn_cancel.hide();
	$btn_reset.hide();

	page.add_inner_button('🖨 Print', do_print);

	function enter_edit_mode() {
		edit_mode = true;
		$btn_edit.closest('button, .btn, li').hide();
		$btn_save.show();
		$btn_cancel.show();
		$btn_reset.show();
		render_all(last_counts);
	}

	function save_edit() {
		persist_stages();
		edit_mode = false;
		$btn_edit.closest('button, .btn, li').show();
		$btn_save.hide();
		$btn_cancel.hide();
		$btn_reset.hide();
		render_all(last_counts);
		frappe.show_alert({ message: 'Layout saved.', indicator: 'green' });
	}

	function cancel_edit() {
		STAGES = load_stages();
		edit_mode = false;
		$btn_edit.closest('button, .btn, li').show();
		$btn_save.hide();
		$btn_cancel.hide();
		$btn_reset.hide();
		render_all(last_counts);
	}

	function reset_to_default() {
		frappe.confirm('Reset to default layout? All customizations will be lost.', () => {
			localStorage.removeItem('sdm_custom_stages');
			STAGES = JSON.parse(JSON.stringify(DEFAULT_STAGES));
			edit_mode = false;
			$btn_edit.closest('button, .btn, li').show();
			$btn_save.hide();
			$btn_cancel.hide();
			$btn_reset.hide();
			render_all(last_counts);
			frappe.show_alert({ message: 'Reset to default.', indicator: 'blue' });
		});
	}

	// ── Stage editor dialog ───────────────────────────────────────────────────
	function open_stage_editor(stage_idx) {
		const stage = STAGES[stage_idx];
		const docs_text = stage.docs.map(d =>
			d.name !== d.dt ? `${d.name} | ${d.dt}` : d.dt
		).join('\n');

		const d = new frappe.ui.Dialog({
			title: `Edit Stage: ${stage.title}`,
			fields: [
				{
					label: 'Title', fieldname: 'title', fieldtype: 'Data',
					reqd: 1, default: stage.title,
				},
				{ fieldtype: 'Column Break' },
				{
					label: 'Emoji', fieldname: 'emoji', fieldtype: 'Data',
					default: stage.emoji, description: 'e.g. 🔧 📅 🎓 💼',
				},
				{ fieldtype: 'Section Break' },
				{
					label: 'Color', fieldname: 'color', fieldtype: 'Color',
					default: stage.color,
				},
				{ fieldtype: 'Column Break' },
				{
					label: 'Dependency Note', fieldname: 'note', fieldtype: 'Data',
					default: stage.note, description: 'e.g. Needs: Stage 1 + 2',
				},
				{ fieldtype: 'Section Break', label: 'Doctypes in this stage' },
				{
					label: 'Doctypes (one per line)',
					fieldname: 'docs_text',
					fieldtype: 'Small Text',
					default: docs_text,
					description: 'Format: "Display Name | DocType" — or just "DocType Name" if they match.',
				},
			],
			primary_action_label: 'Apply',
			primary_action(values) {
				const docs = (values.docs_text || '').split('\n')
					.map(l => l.trim()).filter(Boolean)
					.map(l => {
						if (l.includes('|')) {
							const [name, dt] = l.split('|').map(s => s.trim());
							return { name, dt };
						}
						return { name: l, dt: l };
					});
				STAGES[stage_idx] = {
					...stage,
					title: values.title,
					emoji: values.emoji || stage.emoji,
					color: values.color || stage.color,
					note: values.note || '',
					docs,
				};
				d.hide();
				render_all(last_counts);
			},
		});
		d.show();
	}

	function open_add_stage_dialog() {
		const d = new frappe.ui.Dialog({
			title: 'Add New Stage',
			fields: [
				{ label: 'Title', fieldname: 'title', fieldtype: 'Data', reqd: 1 },
				{ fieldtype: 'Column Break' },
				{ label: 'Emoji', fieldname: 'emoji', fieldtype: 'Data', default: '📄', description: 'e.g. 🔧 📅 🎓' },
				{ fieldtype: 'Section Break' },
				{ label: 'Color', fieldname: 'color', fieldtype: 'Color', default: '#6366f1' },
				{ fieldtype: 'Column Break' },
				{ label: 'Dependency Note', fieldname: 'note', fieldtype: 'Data', description: 'e.g. Needs: Stage 1 + 2' },
				{ fieldtype: 'Section Break', label: 'Doctypes' },
				{
					label: 'Doctypes (one per line)',
					fieldname: 'docs_text', fieldtype: 'Small Text',
					description: 'Format: "Display Name | DocType" or just "DocType Name"',
				},
			],
			primary_action_label: 'Add Stage',
			primary_action(values) {
				const docs = (values.docs_text || '').split('\n')
					.map(l => l.trim()).filter(Boolean)
					.map(l => {
						if (l.includes('|')) {
							const [name, dt] = l.split('|').map(s => s.trim());
							return { name, dt };
						}
						return { name: l, dt: l };
					});
				STAGES.push({
					num: STAGES.length + 1,
					title: values.title,
					emoji: values.emoji || '📄',
					color: values.color || '#6366f1',
					note: values.note || '',
					docs,
				});
				d.hide();
				render_all(last_counts);
			},
		});
		d.show();
	}

	// ── Styles ────────────────────────────────────────────────────────────────
	if (!document.getElementById('sdm-styles')) {
		const style = document.createElement('style');
		style.id = 'sdm-styles';
		style.textContent = `
		.sdm-wrap { max-width: 1200px; margin: 0 auto; padding: 24px 20px 60px; font-family: var(--font-stack); }
		.sdm-header { text-align: center; margin-bottom: 32px; }
		.sdm-header h1 { font-size: 26px; font-weight: 800; color: var(--text-color); margin: 0 0 6px; }
		.sdm-header p { color: var(--text-muted); font-size: 13px; margin: 0; }

		/* Edit mode banner */
		.sdm-edit-banner {
			background: #fef3c7; border: 1.5px dashed #f59e0b; border-radius: 10px;
			padding: 10px 18px; margin-bottom: 20px; display: flex; align-items: center;
			gap: 10px; font-size: 13px; font-weight: 600; color: #92400e;
		}

		/* Quick start banner */
		.sdm-quickstart { background: linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%); border-radius: 14px; padding: 20px 24px; margin-bottom: 36px; color: #fff; }
		.sdm-quickstart h3 { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; margin: 0 0 12px; color: #facc15; }
		.sdm-qs-flow { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
		.sdm-qs-item { background: rgba(255,255,255,.18); border-radius: 8px; padding: 6px 14px; font-size: 12.5px; font-weight: 600; cursor: pointer; transition: background .15s; white-space: nowrap; color: #fff; text-decoration: none; }
		.sdm-qs-item:hover { background: rgba(255,255,255,.32); color: #fff; }
		.sdm-qs-arrow { font-size: 16px; opacity: .6; }

		/* Stage grid */
		.sdm-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }

		/* Stage card */
		.sdm-card { border-radius: 14px; border: 1.5px solid var(--border-color); background: var(--card-bg); overflow: hidden; box-shadow: 0 1px 6px rgba(0,0,0,.06); transition: box-shadow .2s, transform .2s; position: relative; }
		.sdm-card:not(.sdm-edit-active):hover { box-shadow: 0 6px 24px rgba(0,0,0,.1); transform: translateY(-2px); }

		/* Edit mode card */
		.sdm-card.sdm-edit-active { border: 1.5px dashed #f59e0b; cursor: default; }
		.sdm-card.sdm-drag-over { border: 2px solid #2563eb !important; background: var(--fg-hover-color, #f0f4ff) !important; }
		.sdm-card.sdm-dragging { opacity: .4; }

		/* Drag handle */
		.sdm-drag-handle {
			display: flex; align-items: center; justify-content: center;
			width: 28px; color: #94a3b8; font-size: 16px; cursor: grab; flex-shrink: 0;
			user-select: none; padding: 2px 4px;
		}
		.sdm-drag-handle:hover { color: #475569; }
		.sdm-drag-handle:active { cursor: grabbing; }

		/* Edit controls on card */
		.sdm-card-edit-btns { display: flex; gap: 4px; margin-left: auto; }
		.sdm-card-edit-btn {
			width: 26px; height: 26px; border-radius: 6px; border: none;
			background: transparent; cursor: pointer; font-size: 13px;
			display: flex; align-items: center; justify-content: center;
			transition: background .15s;
		}
		.sdm-card-edit-btn:hover { background: var(--fg-hover-color, #f0f4ff); }
		.sdm-card-edit-btn.del:hover { background: #fee2e2; color: #dc2626; }

		/* Card header / body */
		.sdm-card-header { padding: 14px 18px 12px; display: flex; align-items: center; gap: 10px; }
		.sdm-stage-badge { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; color: #fff; flex-shrink: 0; }
		.sdm-card-title { font-size: 13.5px; font-weight: 700; color: var(--text-color); flex: 1; }
		.sdm-card-emoji { font-size: 18px; }
		.sdm-dep-note { font-size: 10px; color: var(--text-muted); font-style: italic; padding: 0 18px 8px; }
		.sdm-divider { height: 1px; background: var(--border-color); margin: 0 18px; }
		.sdm-doc-list { padding: 10px 18px 14px; display: flex; flex-direction: column; gap: 5px; }
		.sdm-doc-item { display: flex; align-items: center; gap: 8px; padding: 5px 10px; border-radius: 7px; cursor: pointer; transition: background .15s; text-decoration: none; }
		.sdm-doc-item:hover { background: var(--fg-hover-color, #f0f4ff); }
		.sdm-doc-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
		.sdm-doc-name { font-size: 12.5px; color: var(--text-color); font-weight: 500; flex: 1; }
		.sdm-doc-item:hover .sdm-doc-name { color: var(--primary); }
		.sdm-doc-arrow { font-size: 11px; color: var(--text-muted); opacity: 0; transition: opacity .15s; }
		.sdm-doc-item:hover .sdm-doc-arrow { opacity: 1; }
		.sdm-doc-count { font-size: 10px; background: var(--bg-blue,#e8f0fe); color: var(--primary); border-radius: 10px; padding: 1px 7px; font-weight: 700; min-width: 22px; text-align: center; }
		.sdm-doc-count.has-data { background: #dcfce7; color: #15803d; }
		.sdm-doc-count.no-data { background: #f1f5f9; color: #94a3b8; }

		/* Add stage button */
		.sdm-add-stage {
			border-radius: 14px; border: 2px dashed #cbd5e1; background: transparent;
			display: flex; flex-direction: column; align-items: center; justify-content: center;
			gap: 8px; padding: 30px; cursor: pointer; color: #64748b;
			font-size: 13px; font-weight: 600; transition: border-color .2s, color .2s, background .2s;
			min-height: 120px;
		}
		.sdm-add-stage:hover { border-color: #2563eb; color: #2563eb; background: #f0f4ff; }
		.sdm-add-stage .sdm-add-icon { font-size: 28px; }

		/* Print */
		@media print {
			.navbar,.page-head,.layout-side-section,.sidebar-toggle-btn,[class*="sidebar"],.page-toolbar,.page-actions,.inner-toolbar,.col-md-2 { display: none !important; }
			html,body { margin: 0 !important; padding: 0 !important; background: #fff !important; }
			.layout-main,.layout-main-section,.page-content,.container,.row,[class*="col-"] { width: 100% !important; max-width: 100% !important; padding: 0 !important; margin: 0 !important; float: none !important; }
			.sdm-wrap { padding: 10px !important; max-width: 100% !important; }
			.sdm-quickstart { background: #1e3a5f !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
			.sdm-grid { grid-template-columns: repeat(3,1fr) !important; gap: 10px !important; }
			.sdm-card { break-inside: avoid; box-shadow: none !important; border: 1px solid #ccc !important; }
			.sdm-card:hover { transform: none !important; }
			.sdm-stage-badge,.sdm-doc-dot,.sdm-qs-item { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
			.sdm-doc-arrow,.sdm-drag-handle,.sdm-card-edit-btns,.sdm-edit-banner,.sdm-add-stage { display: none !important; }
		}
		`;
		document.head.appendChild(style);
	}

	// ── Render helpers ────────────────────────────────────────────────────────
	function dt_url(dt) {
		return `/app/${frappe.router.slug(dt)}`;
	}

	function render_doc(doc, color, counts) {
		const cnt = (counts && counts[doc.dt] !== undefined) ? counts[doc.dt] : '…';
		const cls = cnt === '…' ? '' : (cnt > 0 ? 'has-data' : 'no-data');
		return `
		<a class="sdm-doc-item" href="${dt_url(doc.dt)}" target="_blank">
			<span class="sdm-doc-dot" style="background:${color}"></span>
			<span class="sdm-doc-name">${doc.name}</span>
			<span class="sdm-doc-count ${cls}">${cnt}</span>
			<span class="sdm-doc-arrow">↗</span>
		</a>`;
	}

	function render_card(stage, idx, counts) {
		const docs_html = stage.docs.map(d => render_doc(d, stage.color, counts)).join('');
		const total = counts ? stage.docs.reduce((s, d) => s + (counts[d.dt] || 0), 0) : null;
		const total_badge = total !== null
			? `<span class="sdm-doc-count ${total > 0 ? 'has-data' : 'no-data'}" style="margin-left:auto;margin-right:4px">${total}</span>`
			: '';

		if (edit_mode) {
			return `
			<div class="sdm-card sdm-edit-active" data-stage-idx="${idx}">
				<div class="sdm-card-header">
					<span class="sdm-drag-handle" title="Drag to reorder">⠿</span>
					<div class="sdm-stage-badge" style="background:${stage.color}">${stage.num}</div>
					<div class="sdm-card-title">${stage.title}</div>
					${total_badge}
					<span class="sdm-card-emoji">${stage.emoji}</span>
					<div class="sdm-card-edit-btns">
						<button class="sdm-card-edit-btn edit" data-idx="${idx}" title="Edit stage">✏️</button>
						<button class="sdm-card-edit-btn del" data-idx="${idx}" title="Delete stage">✕</button>
					</div>
				</div>
				${stage.note ? `<div class="sdm-dep-note">↳ ${stage.note}</div>` : ''}
				<div class="sdm-divider"></div>
				<div class="sdm-doc-list">${docs_html}</div>
			</div>`;
		}

		return `
		<div class="sdm-card">
			<div class="sdm-card-header">
				<div class="sdm-stage-badge" style="background:${stage.color}">${stage.num}</div>
				<div class="sdm-card-title">${stage.title}</div>
				${total_badge}
				<span class="sdm-card-emoji">${stage.emoji}</span>
			</div>
			${stage.note ? `<div class="sdm-dep-note">↳ ${stage.note}</div>` : ''}
			<div class="sdm-divider"></div>
			<div class="sdm-doc-list">${docs_html}</div>
		</div>`;
	}

	function render_all(counts) {
		last_counts = counts;

		const qs_html = QUICKSTART.map((dt, i) => {
			const cnt = counts ? counts[dt] : null;
			const badge = cnt !== null
				? ` <span style="background:rgba(255,255,255,.25);border-radius:8px;padding:1px 6px;font-size:10px;margin-left:4px">${cnt}</span>`
				: '';
			const arrow = i < QUICKSTART.length - 1 ? `<span class="sdm-qs-arrow">→</span>` : '';
			return `<a class="sdm-qs-item" href="${dt_url(dt)}" target="_blank">${dt}${badge}</a>${arrow}`;
		}).join('');

		const cards_html = STAGES.map((s, idx) => render_card(s, idx, counts)).join('');

		const add_btn = edit_mode
			? `<button class="sdm-add-stage" id="sdm-add-stage-btn"><span class="sdm-add-icon">＋</span>Add Stage</button>`
			: '';

		const edit_banner = edit_mode
			? `<div class="sdm-edit-banner">✏️ Edit Mode — drag cards to reorder, click ✏️ to edit a stage, ✕ to remove. Click <strong>✓ Save</strong> when done.</div>`
			: '';

		$(wrapper).find('.page-content').html(`
			<div class="sdm-wrap">
				<div class="sdm-header">
					<h1>📌 SLCM Data Entry Map</h1>
					<p>Follow the stages in order — each stage depends on the ones before it. Click any doctype to open its list.</p>
				</div>
				${edit_banner}
				<div class="sdm-quickstart">
					<h3>⚡ Minimum Viable Path — Quick Start</h3>
					<div class="sdm-qs-flow">${qs_html}</div>
				</div>
				<div class="sdm-grid" id="sdm-stage-grid">
					${cards_html}
					${add_btn}
				</div>
			</div>
		`);

		if (edit_mode) {
			setup_edit_handlers();
			setup_drag_drop();
		}
	}

	// ── Edit mode event handlers ──────────────────────────────────────────────
	function setup_edit_handlers() {
		// Edit button on each card
		$(wrapper).find('.sdm-card-edit-btn.edit').on('click', function (e) {
			e.stopPropagation();
			open_stage_editor(parseInt($(this).data('idx')));
		});

		// Delete button on each card
		$(wrapper).find('.sdm-card-edit-btn.del').on('click', function (e) {
			e.stopPropagation();
			const idx = parseInt($(this).data('idx'));
			frappe.confirm(`Remove stage "${STAGES[idx].title}"?`, () => {
				STAGES.splice(idx, 1);
				STAGES.forEach((s, i) => s.num = i + 1);
				render_all(last_counts);
			});
		});

		// Add stage button
		$('#sdm-add-stage-btn').on('click', open_add_stage_dialog);
	}

	// ── Drag and drop (stage reordering) ──────────────────────────────────────
	function setup_drag_drop() {
		const cards = wrapper.querySelectorAll('.sdm-card.sdm-edit-active');

		cards.forEach((card) => {
			const handle = card.querySelector('.sdm-drag-handle');
			if (!handle) return;

			// Only allow drag when mousedown starts on the handle
			card.draggable = false;
			handle.addEventListener('mousedown', () => { card.draggable = true; });
			document.addEventListener('mouseup', () => { card.draggable = false; }, { once: false });

			card.addEventListener('dragstart', (e) => {
				if (!card.draggable) { e.preventDefault(); return; }
				drag_src_idx = parseInt(card.dataset.stageIdx);
				e.dataTransfer.effectAllowed = 'move';
				e.dataTransfer.setData('text/plain', drag_src_idx);
				setTimeout(() => card.classList.add('sdm-dragging'), 0);
			});

			card.addEventListener('dragend', () => {
				card.draggable = false;
				card.classList.remove('sdm-dragging');
				wrapper.querySelectorAll('.sdm-card').forEach(c => c.classList.remove('sdm-drag-over'));
			});

			card.addEventListener('dragover', (e) => {
				e.preventDefault();
				e.dataTransfer.dropEffect = 'move';
				const target_idx = parseInt(card.dataset.stageIdx);
				if (drag_src_idx !== null && drag_src_idx !== target_idx) {
					wrapper.querySelectorAll('.sdm-card').forEach(c => c.classList.remove('sdm-drag-over'));
					card.classList.add('sdm-drag-over');
				}
			});

			card.addEventListener('dragleave', (e) => {
				if (!card.contains(e.relatedTarget)) {
					card.classList.remove('sdm-drag-over');
				}
			});

			card.addEventListener('drop', (e) => {
				e.preventDefault();
				card.classList.remove('sdm-drag-over');
				const target_idx = parseInt(card.dataset.stageIdx);
				if (drag_src_idx !== null && drag_src_idx !== target_idx) {
					const [moved] = STAGES.splice(drag_src_idx, 1);
					STAGES.splice(target_idx, 0, moved);
					STAGES.forEach((s, i) => s.num = i + 1);
					drag_src_idx = null;
					render_all(last_counts);
				}
			});
		});
	}

	// ── Print ─────────────────────────────────────────────────────────────────
	function do_print() {
		const content = document.querySelector('.sdm-wrap');
		if (!content) return;

		// Strip edit controls from the clone
		const clone = content.cloneNode(true);
		clone.querySelectorAll('.sdm-card-edit-btns, .sdm-drag-handle, .sdm-edit-banner, .sdm-add-stage').forEach(el => el.remove());
		clone.querySelectorAll('.sdm-card.sdm-edit-active').forEach(el => {
			el.classList.remove('sdm-edit-active');
		});

		const win = window.open('', '_blank', 'width=1200,height=800');
		win.document.write(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>SLCM Data Entry Map</title><style>
*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#fff;color:#1a202c;padding:20px}
.sdm-wrap{max-width:100%}.sdm-header{text-align:center;margin-bottom:24px}.sdm-header h1{font-size:22px;font-weight:800;margin-bottom:4px}.sdm-header p{font-size:11px;color:#666}
.sdm-quickstart{background:#1e3a5f;border-radius:10px;padding:14px 18px;margin-bottom:24px;color:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.sdm-quickstart h3{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;margin-bottom:10px;color:#facc15}
.sdm-qs-flow{display:flex;align-items:center;flex-wrap:wrap;gap:5px}.sdm-qs-item{background:rgba(255,255,255,.2);border-radius:6px;padding:4px 10px;font-size:11px;font-weight:600;-webkit-print-color-adjust:exact;print-color-adjust:exact;color:#fff;text-decoration:none}
.sdm-qs-arrow{font-size:13px;opacity:.6}
.sdm-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.sdm-card{border-radius:10px;border:1px solid #dde;overflow:hidden;break-inside:avoid}
.sdm-card-header{padding:10px 14px 8px;display:flex;align-items:center;gap:8px}
.sdm-stage-badge{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:#fff;flex-shrink:0;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.sdm-card-title{font-size:12px;font-weight:700;flex:1}.sdm-card-emoji{font-size:15px}
.sdm-dep-note{font-size:9px;color:#888;font-style:italic;padding:0 14px 6px}
.sdm-divider{height:1px;background:#eee;margin:0 14px}
.sdm-doc-list{padding:8px 14px 10px;display:flex;flex-direction:column;gap:3px}
.sdm-doc-item{display:flex;align-items:center;gap:6px;padding:3px 0;text-decoration:none;color:inherit}
.sdm-doc-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.sdm-doc-name{font-size:11px;font-weight:500}.sdm-doc-arrow{display:none}
.sdm-doc-count{font-size:10px;border-radius:8px;padding:1px 6px;font-weight:700}
.sdm-doc-count.has-data{background:#dcfce7;color:#15803d;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.sdm-doc-count.no-data{background:#f1f5f9;color:#94a3b8}
@media print{body{padding:10px}.sdm-grid{grid-template-columns:repeat(3,1fr)}.sdm-card{break-inside:avoid}}
</style></head><body>${clone.outerHTML}</body></html>`);
		win.document.close();
		win.focus();
		setTimeout(() => { win.print(); win.close(); }, 500);
	}

	// ── Initial render ────────────────────────────────────────────────────────
	render_all(null);

	frappe.call({
		method: 'slcm.slcm.page.slcm_data_map.slcm_data_map.get_doctype_counts',
		callback(r) {
			if (r.message) render_all(r.message);
		},
	});
};
