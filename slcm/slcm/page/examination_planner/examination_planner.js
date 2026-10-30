// Exam Plan page: one exam plan, five steps (see examination_planner.py)
frappe.pages['examination-planner'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Exam Plan'), single_column: true });
	$(wrapper).addClass('er-theme');
	if (!document.getElementById('er-theme-font')) {
		$('head').append(
			'<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">'
		);
	}
	frappe.require('/assets/slcm/css/exam_results_theme.css');
	wrapper.planner = new ExamPlanner(page, wrapper);
};

frappe.pages['examination-planner'].on_page_show = function (wrapper) {
	// The page is also linked from other sidebars; keep the Examinations one
	setTimeout(() => {
		if (frappe.app.sidebar && frappe.app.sidebar.sidebar_title !== 'Examinations') frappe.app.sidebar.setup('Examinations');
	}, 200);
	// Coming back (e.g. after entering marks on Course Results) shows the latest state
	const planner = wrapper.planner, plan = frappe.get_route()[1];
	if (!planner || !planner.o) return;
	if (plan && plan !== planner.plan) planner.open(plan);
	else planner.refresh();
};

const API = 'slcm.slcm.page.examination_planner.examination_planner.';
const esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));
const call = (method, args) => frappe.call({ method: API + method, args: args || {}, freeze: true }).then((r) => r.message);

const STEPS = [
	{ key: 'plan', label: __('Plan & courses'), hint: __('Map each course to its schemas') },
	{ key: 'timetable', label: __('Exam timetable'), hint: __('Dates, rooms, invigilators') },
	{ key: 'students', label: __('Students'), hint: __('From Classes, eligibility, barcodes') },
	{ key: 'marks', label: __('Marks'), hint: __('Access and entry progress') },
	{ key: 'results', label: __('Results'), hint: __('Submit, lock, GPA, publish') },
];

class ExamPlanner {
	constructor(page, wrapper) {
		this.page = page;
		this.step = 0;
		this.$root = $('<div class="xp-wrap"></div>').appendTo(page.main);
		this.add_styles();
		page.set_primary_action(__('New Exam Plan'), () => this.new_plan_dialog(), 'add');
		page.add_inner_button(__('Examination Settings'), () => frappe.set_route('Form', 'Examination Settings'));
		this.load_plans().then(() => {
			const plan = frappe.get_route()[1] || (this.plans[0] && this.plans[0].name);
			if (plan) this.open(plan);
			else this.render_empty();
		});
	}

	// ── plans ──────────────────────────────────────────────────────────
	load_plans() {
		return call('get_plans').then((r) => {
			this.plans = r.plans;
			this.terms = r.terms;
		});
	}

	render_empty() {
		this.$root.html(`<div class="xp-empty">
			<h3>${__('No exam plans yet')}</h3>
			<p>${__('Create one exam plan for the Academic Term. Its courses come from the Classes of that term.')}</p>
			<button class="btn btn-primary xp-new">${__('New Exam Plan')}</button></div>`);
		this.$root.find('.xp-new').on('click', () => this.new_plan_dialog());
	}

	new_plan_dialog() {
		const d = new frappe.ui.Dialog({
			title: __('New Exam Plan'),
			fields: [
				{ fieldname: 'term', label: __('Academic Term'), fieldtype: 'Link', options: 'Academic Term', reqd: 1,
				  onchange: () => { const t = d.get_value('term'); if (t && !d.get_value('exam_name')) d.set_value('exam_name', `${t} Examinations`); } },
				{ fieldname: 'exam_name', label: __('Exam Name'), fieldtype: 'Data', reqd: 1,
				  description: __('One plan covers every assessment of the term (internal and end term).') },
			],
			primary_action_label: __('Create'),
			primary_action: (v) => {
				call('create_plan', { term: v.term, exam_name: v.exam_name }).then((r) => {
					d.hide();
					this.load_plans().then(() => this.open(r.name));
				});
			},
		});
		d.show();
	}

	open(plan) {
		this.plan = plan;
		if (frappe.get_route()[1] !== plan) frappe.set_route('examination-planner', plan);
		return call('get_overview', { exam_plan: plan }).then((o) => {
			this.o = o;
			const first_open = STEPS.findIndex((s) => !o.steps[s.key]);
			if (this.step === null || this.step === undefined || !this.is_open(this.step)) this.step = Math.max(0, first_open === -1 ? 4 : first_open);
			this.render();
		});
	}

	refresh() { return this.open(this.plan); }

	is_open(i) {
		return i === 0 || STEPS.slice(0, i).every((s) => this.o.steps[s.key]);
	}

	// ── layout ─────────────────────────────────────────────────────────
	render() {
		const o = this.o, p = o.plan;
		const options = this.plans.map((x) => `<option value="${esc(x.name)}" ${x.name === p.name ? 'selected' : ''}>${esc(x.exam_name)} · ${esc(x.term || '')}</option>`).join('');
		const term = o.term ? `${frappe.datetime.str_to_user(o.term.term_start_date)} – ${frappe.datetime.str_to_user(o.term.term_end_date)}` : __('No term');
		const steps = STEPS.map((s, i) => {
			const done = o.steps[s.key], open = this.is_open(i);
			return `<button class="xp-step ${i === this.step ? 'on' : ''} ${open ? '' : 'locked'}" data-i="${i}">
				<span class="xp-step-n">${i + 1}</span><span class="xp-step-t"><b>${s.label}</b><small>${s.hint}</small></span>
				${done ? `<span class="xp-pill ok">${__('Done')}</span>` : open ? '' : `<span class="xp-pill warn">${__('Locked')}</span>`}</button>`;
		}).join('');
		this.$root.html(`
			<div class="xp-head">
				<select class="form-control xp-plan">${options}</select>
				<div class="xp-meta"><b>${esc(p.term || '')}</b> · ${term} · <a href="/desk/exam-plan/${encodeURIComponent(p.name)}">${__('Open Exam Plan form')}</a></div>
			</div>
			<div class="xp-steps">${steps}</div>
			<div class="xp-body"></div>`);
		this.$root.find('.xp-plan').on('change', (e) => { this.step = null; this.open($(e.target).val()); });
		this.$root.find('.xp-step').on('click', (e) => {
			const i = +$(e.currentTarget).data('i');
			if (!this.is_open(i)) { frappe.show_alert({ message: __('Finish the step before it first.'), indicator: 'orange' }); return; }
			this.step = i;
			this.render();
		});
		this.$body = this.$root.find('.xp-body');
		[this.render_plan, this.render_timetable, this.render_students, this.render_marks, this.render_results][this.step].call(this);
	}

	card(title, sub, saves) {
		return `<div class="xp-card"><div class="xp-card-head"><div><h4>${title}</h4>${sub ? `<p>${sub}</p>` : ''}</div>
			${saves ? `<span class="xp-saves">${__('Saves to')} <b>${saves}</b></span>` : ''}</div><div class="xp-card-body"></div></div>`;
	}

	// ── 1. Plan & courses ──────────────────────────────────────────────
	render_plan() {
		call('get_mapping', { exam_plan: this.plan }).then((m) => {
			this.$body.html(this.card(__('Course → schema mapping'),
				__('Courses taught in the plan\'s term (from Classes). Unmapped courses are pre-filled from the course\'s last plan or the Examination Settings defaults; check them and save.'),
				'Course Schema Assignment'));
			const $c = this.$body.find('.xp-card-body');
			const evs = m.evaluation_schemas.map((e) => e.name), gss = m.grade_schemas.map((g) => g.name);
			const NEW = '__new__';
			const sel = (list, val, cls, doctype) => `<select class="form-control input-sm xp-select ${cls}" data-doctype="${doctype}">
				<option value="">${list.length ? __('Select…') : __('None yet')}</option>
				${list.map((x) => `<option ${x === val ? 'selected' : ''}>${esc(x)}</option>`).join('')}
				<option value="${NEW}">+ ${__('Create new {0}…', [__(doctype)])}</option></select>`;
			const missing = [!evs.length && 'Evaluation Schema', !gss.length && 'Grading Schema'].filter(Boolean);
			const su = m.setup || {};
			const setup_todo = !su.components || !su.assessment_types || missing.length;
			const todo = m.courses.filter((c) => !(c.evaluation_schema && c.grade_schema)).length;
			const rows = m.courses.map((c) => {
				const ev = c.evaluation_schema || c.suggest_evaluation_schema || '', gs = c.grade_schema || c.suggest_grade_schema || '';
				const saved = c.source === 'saved';
				return `<tr data-course="${esc(c.course)}" data-saved-ev="${esc(c.evaluation_schema || '')}" data-saved-gs="${esc(c.grade_schema || '')}" class="${ev && gs ? '' : 'xp-flag'}">
					<td><input type="checkbox" class="xp-sel"></td>
					<td><b>${esc(c.course_code || c.course)}</b><br><small>${esc(c.course_name || '')}</small></td>
					<td>${esc(c.programme || '')}</td><td class="num">${c.enrolled_students || 0}</td>
					<td>${sel(evs, ev, 'xp-ev', 'Evaluation Schema')}</td><td>${sel(gss, gs, 'xp-gs', 'Grading Schema')}</td>
					<td>${saved ? `<span class="xp-pill ok">${__('Saved')}</span>` : c.source ? `<span class="xp-pill info">${esc(c.source)}</span>` : `<span class="xp-pill bad">${__('Not mapped')}</span>`}</td></tr>`;
			}).join('');
			const item = (n, done, title, hint, btn, cls, blocked) => `<li class="${done ? 'done' : ''}"><span class="xp-dot">${done ? '✓' : n}</span>
				<div><b>${title}</b><p>${hint}</p></div><div class="xp-actions">${done ? `<span class="xp-pill ok">${done}</span>`
					: `<button class="btn btn-sm btn-primary ${cls}" ${blocked ? `disabled title="${esc(blocked)}"` : ''}>${btn}</button>`}</div></li>`;
			const guide = setup_todo
				? `<div class="xp-guide warn"><b>${__('First, the one-time setup (in this order)')}</b>
					<span>${__('Every exam plan reuses these. Once they exist this checklist goes away.')}</span></div>
					<ol class="xp-check">
					${item(1, su.components && __('{0} created', [su.components]), __('Exam Components'), __('The parts of a course, e.g. Internal, End Term, Re-Exam.'), __('Add components'), 'xp-add-comp')}
					${item(2, su.assessment_types && __('{0} created', [su.assessment_types]), __('Assessment Types'), __('What is marked, e.g. Quiz, Project, End Term Paper.'), __('Add assessment types'), 'xp-add-atype')}
					${item(3, evs.length && __('{0} created', [evs.length]), __('Evaluation Schema'), __('How a course is marked: its components and assessments.'), __('Create Evaluation Schema'), 'xp-new-es',
						!(su.components && su.assessment_types) && __('Add components and assessment types first'))}
					${item(4, gss.length && __('{0} created', [gss.length]), __('Grading Schema'), __('How marks become grades and grade points.'), __('Create Grading Schema'), 'xp-new-gs')}
					</ol>`
				: todo
					? `<div class="xp-guide"><b>${__('Next')}</b><span>${__('Pick an Evaluation Schema and a Grade Schema for {0} course(s), then click Save mapping.', [todo])}</span></div>`
					: `<div class="xp-guide ok"><b>${__('Done')}</b><span>${__('Every course is mapped. Go on to step 2, Exam timetable.')}</span></div>`;
			$c.html(guide + `
				<div class="xp-bar"><b>${this.o.counts.courses_mapped} / ${this.o.counts.courses_taught}</b> ${__('courses mapped')}
					<span class="xp-grow"></span>
					${missing.length ? '' : `<button class="btn btn-default btn-sm xp-new-es">${__('New Evaluation Schema')}</button>
					<button class="btn btn-default btn-sm xp-new-gs">${__('New Grading Schema')}</button>`}</div>
				<div class="xp-table"><table class="table table-sm"><thead><tr><th><input type="checkbox" class="xp-all"></th><th>${__('Course')}</th><th>${__('Programme')}</th><th>${__('Students')}</th>
					<th>${__('Evaluation Schema')}</th><th>${__('Grade Schema')}</th><th>${__('Filled from')}</th></tr></thead><tbody>${rows || `<tr><td colspan="7">${__('No Classes in this term yet. Create Classes first (Programme Management).')}</td></tr>`}</tbody></table></div>
				<div class="xp-bar xp-soft xp-bulk" style="display:none"><b class="xp-nsel"></b>${sel(evs, '', 'xp-bulk-ev', 'Evaluation Schema')}${sel(gss, '', 'xp-bulk-gs', 'Grading Schema')}
					<button class="btn btn-default btn-sm xp-apply">${__('Apply to selected')}</button>
					<button class="btn btn-default btn-sm xp-unmap">${__('Unmap selected')}</button></div>
				<div class="xp-bar"><span class="xp-grow"></span><button class="btn btn-primary xp-save" ${m.courses.length ? '' : 'disabled'}>${__('Save mapping')}</button></div>`);
			const sync_bulk = () => {
				const n = $c.find('.xp-sel:checked').length;
				$c.find('.xp-bulk').toggle(n > 0);
				$c.find('.xp-nsel').text(__('{0} selected', [n]));
			};
			$c.find('.xp-all').on('change', (e) => { $c.find('.xp-sel').prop('checked', e.target.checked); sync_bulk(); });
			$c.on('change', '.xp-sel', sync_bulk);
			$c.find('.xp-new-es').on('click', () => this.schema_dialog('Evaluation Schema'));
			$c.find('.xp-add-comp').on('click', () => this.masters_dialog('Exam Component'));
			$c.find('.xp-add-atype').on('click', () => this.masters_dialog('Exam Assessment Type'));
			$c.find('.xp-new-gs').on('click', () => this.schema_dialog('Grading Schema'));
			// A schema just made in the panel goes to every course still without one
			Object.entries(this.prefill || {}).forEach(([doctype, name]) => {
				$c.find(`tbody .xp-select[data-doctype="${doctype}"]`).filter((_, el) => !el.value).val(name).trigger('change');
			});
			this.prefill = {};
			// "+ Create new…" in a dropdown opens the form; coming back refreshes the lists
			$c.on('change', '.xp-select', (e) => {
				if (e.target.value !== NEW) {
					$(e.target).closest('tr').toggleClass('xp-flag', !($(e.target).closest('tr').find('.xp-ev').val() && $(e.target).closest('tr').find('.xp-gs').val()));
					return;
				}
				e.target.value = '';
				this.schema_dialog($(e.target).data('doctype'));
			});
			$c.find('.xp-apply').on('click', () => {
				const ev = $c.find('.xp-bulk-ev').val(), gs = $c.find('.xp-bulk-gs').val();
				$c.find('tbody tr').each((_, tr) => {
					if (!$(tr).find('.xp-sel').prop('checked')) return;
					if (ev) $(tr).find('.xp-ev').val(ev);
					if (gs) $(tr).find('.xp-gs').val(gs);
				});
			});
			$c.find('.xp-unmap').on('click', () => {
				const courses = $c.find('tbody tr').filter((_, tr) => $(tr).find('.xp-sel').prop('checked') && $(tr).data('saved-ev')).map((_, tr) => $(tr).data('course')).get();
				if (!courses.length) { frappe.msgprint(__('Select saved courses to unmap.')); return; }
				frappe.confirm(__('Remove the schemas of {0} course(s) from this plan?', [courses.length]),
					() => call('unmap', { exam_plan: this.plan, courses: JSON.stringify(courses) }).then(() => this.refresh()));
			});
			$c.find('.xp-save').on('click', () => {
				const assignments = [], changed = [];
				$c.find('tbody tr[data-course]').each((_, tr) => {
					const $tr = $(tr), ev = $tr.find('.xp-ev').val(), gs = $tr.find('.xp-gs').val();
					if (!ev && !gs) return;
					if ($tr.data('saved-ev') && ($tr.data('saved-ev') !== ev || $tr.data('saved-gs') !== gs)) changed.push($tr.data('course'));
					assignments.push({ course: $tr.data('course'), evaluation_schema: ev, grade_schema: gs });
				});
				if (!assignments.length) { frappe.msgprint(__('Pick schemas first.')); return; }
				const save = (reason) => call('save_mapping', { exam_plan: this.plan, assignments: JSON.stringify(assignments), reason: reason || '' })
					.then(() => { frappe.show_alert({ message: __('Mapping saved'), indicator: 'green' }); this.refresh(); });
				if (changed.length && this.o.settings.require_change_reason) {
					frappe.prompt({ fieldname: 'reason', fieldtype: 'Small Text', label: __('Reason for changing {0}', [changed.join(', ')]), reqd: 1 },
						(v) => save(v.reason), __('Change reason'));
				} else save();
			});
		});
	}

	// Add several Exam Components / Assessment Types at once, on this page
	masters_dialog(doctype) {
		const comp = doctype === 'Exam Component';
		const [name_f, type_f] = comp ? ['component_name', 'component_type'] : ['type_name', 'assessment_type'];
		const types = comp ? ['Custom', 'Re Exam', 'Makeup'] : ['Default Assessment', 'Assessment', 'ReExam/Makeup Assessment'];
		const data = comp
			? [['Internal', 'Custom'], ['End Term', 'Custom'], ['Re-Exam', 'Re Exam']]
			: [['Quiz', 'Assessment'], ['Project', 'Assessment'], ['End Term Paper', 'Default Assessment'], ['Re-Exam Paper', 'ReExam/Makeup Assessment']];
		const d = new frappe.ui.Dialog({
			title: comp ? __('Add Exam Components') : __('Add Assessment Types'), size: 'large',
			fields: [
				{ fieldtype: 'HTML', options: `<p class="text-muted">${comp
					? __('Custom = a regular part of the course. Re Exam / Makeup = a paper written later that can replace a part. Example rows are filled in; change or delete them.')
					: __('Assessment = internal work. Default Assessment = the main paper. ReExam/Makeup Assessment = the re-exam paper. Example rows are filled in; change or delete them.')}</p>` },
				{ fieldname: 'rows', fieldtype: 'Table', in_place_edit: 1, data: data.map(([n, t]) => ({ [name_f]: n, [type_f]: t })), fields: [
					{ fieldname: name_f, label: __('Name'), fieldtype: 'Data', reqd: 1, in_list_view: 1, columns: 6 },
					{ fieldname: type_f, label: __('Type'), fieldtype: 'Select', options: types.join('\n'), reqd: 1, in_list_view: 1, columns: 4 },
				] },
			],
			primary_action_label: __('Add'),
			primary_action: (v) => {
				const docs = (v.rows || []).filter((r) => r[name_f]).map((r) => ({ doctype, [name_f]: r[name_f], [type_f]: r[type_f], is_active: 1 }));
				if (!docs.length) { frappe.msgprint(__('Add at least one row.')); return; }
				frappe.call({ method: 'frappe.client.insert_many', args: { docs }, freeze: true }).then(() => {
					d.hide();
					frappe.show_alert({ message: __('{0} added', [docs.length]), indicator: 'green' });
					this.refresh();
				});
			},
		});
		d.show();
	}

	// Create a schema in a panel on this page (no leaving the plan)
	schema_dialog(doctype) {
		const evaluation = doctype === 'Evaluation Schema';
		const num = (fieldname, label, extra) => Object.assign({ fieldname, label, fieldtype: 'Float', in_list_view: 1 }, extra || {});
		const fields = evaluation ? [
			{ fieldname: 'schema_name', label: __('Schema Name'), fieldtype: 'Data', reqd: 1, description: __('For example Theory 100 (40 internal + 60 end term)') },
			{ fieldtype: 'Column Break' },
			num('total_marks', __('Total Marks'), { default: 100, in_list_view: 0, description: __('Worked out from the component marks on save') }),
			{ fieldtype: 'Column Break' },
			num('passing_marks', __('Passing Marks'), { default: 40, in_list_view: 0 }),
			{ fieldtype: 'Section Break', label: __('Components'), description: __('The parts of the course, e.g. Internal 40 and End Term 60.') },
			{ fieldname: 'schema_components', fieldtype: 'Table', cannot_add_rows: 0, in_place_edit: 1, data: [], fields: [
				{ fieldname: 'component', label: __('Component'), fieldtype: 'Link', options: 'Exam Component', reqd: 1, in_list_view: 1, columns: 3 },
				num('effective_max_marks', __('Max Marks'), { columns: 2 }), num('weightage', __('Weightage'), { columns: 1 }),
				num('passing_marks', __('Passing Marks'), { columns: 2 }),
				{ fieldname: 'consider_for_pass_fail', label: __('Must pass'), fieldtype: 'Check', in_list_view: 1, columns: 1 },
			] },
			{ fieldtype: 'Section Break', label: __('Assessments'), description: __('What is marked inside each component, e.g. Quiz 20 and Project 20 under Internal.') },
			{ fieldname: 'assessment_configs', fieldtype: 'Table', in_place_edit: 1, data: [], fields: [
				{ fieldname: 'component', label: __('Component'), fieldtype: 'Link', options: 'Exam Component', reqd: 1, in_list_view: 1, columns: 2 },
				{ fieldname: 'assessment_type', label: __('Assessment Type'), fieldtype: 'Link', options: 'Exam Assessment Type', reqd: 1, in_list_view: 1, columns: 2 },
				{ fieldname: 'label', label: __('Label'), fieldtype: 'Data', in_list_view: 1, columns: 1 },
				num('maximum_marks', __('Max Marks'), { columns: 1 }), num('effective_marks', __('Effective'), { columns: 1 }),
				num('passing_marks', __('Pass'), { columns: 1 }),
				{ fieldname: 'consider_for_pass_fail', label: __('Must pass'), fieldtype: 'Check', in_list_view: 1, columns: 1 },
			] },
			{ fieldtype: 'HTML', options: `<p class="text-muted small">${__('Re-exam papers and calculation settings can be added later on the full Evaluation Schema form.')}</p>` },
		] : [
			{ fieldname: 'grading_schema_name', label: __('Schema Code'), fieldtype: 'Data', reqd: 1, description: __('For example G10-100') },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'schema_name', label: __('Name'), fieldtype: 'Data' },
			{ fieldtype: 'Column Break' },
			num('maximum_marks', __('Maximum Marks'), { default: 100, reqd: 1, in_list_view: 0 }),
			{ fieldname: 'grading_type', label: __('Grading Type'), fieldtype: 'Select', options: 'Absolute\nRelative-Manual\nRelative-Auto', default: 'Absolute' },
			{ fieldtype: 'Section Break', label: __('Grades'), description: __('An example 10-point scale is filled in; change it to your rules. Tick Failed on fail grades.') },
			{ fieldname: 'grades', fieldtype: 'Table', in_place_edit: 1, fields: [
				{ fieldname: 'grade', label: __('Grade'), fieldtype: 'Data', reqd: 1, in_list_view: 1, columns: 1 },
				{ fieldname: 'from_operator', label: __('From'), fieldtype: 'Select', options: '>=\n>', default: '>=', in_list_view: 1, columns: 1 },
				num('marks_from', __('Marks From'), { reqd: 1, columns: 2 }),
				{ fieldname: 'to_operator', label: __('To'), fieldtype: 'Select', options: '<=\n<', default: '<', in_list_view: 1, columns: 1 },
				num('marks_to', __('Marks To'), { reqd: 1, columns: 2 }),
				num('grade_point', __('Grade Point'), { reqd: 1, columns: 1 }),
				{ fieldname: 'failed', label: __('Failed'), fieldtype: 'Check', in_list_view: 1, columns: 1 },
			], data: [['O', 90, 100, 10], ['A+', 80, 90, 9], ['A', 70, 80, 8], ['B+', 60, 70, 7], ['B', 50, 60, 6], ['C', 40, 50, 5], ['F', 0, 40, 0]]
				.map(([grade, a, b, gp]) => ({ grade, from_operator: '>=', marks_from: a, to_operator: b === 100 ? '<=' : '<', marks_to: b, grade_point: gp, failed: grade === 'F' ? 1 : 0 })) },
		];
		const d = new frappe.ui.Dialog({
			title: __('New {0}', [__(doctype)]), size: 'extra-large', fields,
			secondary_action_label: __('Open full form instead'),
			secondary_action: () => { d.hide(); frappe.new_doc(doctype); },
			primary_action_label: __('Create'),
			primary_action: (v) => {
				const doc = Object.assign({ doctype }, v);
				const clean = (rows, keys) => (rows || []).filter((r) => keys.every((k) => r[k] !== undefined && r[k] !== null && r[k] !== ''))
					.map(({ name, idx, __islocal, __checked, ...r }) => r);
				if (evaluation) {
					doc.schema_components = clean(v.schema_components, ['component']);
					doc.assessment_configs = clean(v.assessment_configs, ['component', 'assessment_type']);
					if (!doc.schema_components.length) { frappe.msgprint(__('Add at least one component.')); return; }
				} else {
					doc.grades = clean(v.grades, ['grade']);
					if (!doc.grades.length) { frappe.msgprint(__('Add at least one grade.')); return; }
				}
				frappe.call({ method: 'frappe.client.insert', args: { doc }, freeze: true }).then((r) => {
					d.hide();
					frappe.show_alert({ message: __('{0} {1} created and picked for unmapped courses — check and Save mapping', [__(doctype), r.message.name]), indicator: 'green' });
					this.prefill = Object.assign(this.prefill || {}, { [doctype]: r.message.name });
					this.refresh();
				});
			},
		});
		d.show();
	}

	// ── 2. Exam timetable ──────────────────────────────────────────────
	render_timetable() {
		call('get_timetable', { exam_plan: this.plan }).then((t) => {
			this.tt = t;
			this.$body.html(this.card(__('Exam timetable'),
				__('Rooms are Venue Master rooms shared with the class Time Table. Checked: term dates, holidays, a class in the room, seats (papers may share a room), the same students in two exams, invigilator.'),
				'Exam Plan › Course Schedules') + this.card(__('Assessment schedules'),
				__('Internal assessment dates and marks-entry windows per programme; rows come from the mapped schemas. Faculty enter these marks on the portal.'),
				'Exam Assessment Schedule'));
			const $cards = this.$body.find('.xp-card-body');
			const venue_opts = (v) => `<option value=""></option>` + t.venues.map((x) => `<option value="${esc(x.name)}" ${x.name === v ? 'selected' : ''}>${esc(x.name)} (${x.capacity || 0})</option>`).join('');
			const fac_opts = (v) => `<option value=""></option>` + t.faculty.map((x) => `<option value="${esc(x.name)}" ${String(x.name) === String(v) ? 'selected' : ''}>${esc(x.label)}</option>`).join('');
			const rows = t.rows.map((r, i) => `<tr data-i="${i}" data-course="${esc(r.course)}">
				<td><b>${esc(r.course)}</b><br><small>${esc(r.course_name)}</small></td><td class="num">${r.students}</td>
				<td><input type="date" class="form-control input-sm xp-d" value="${esc(r.exam_date || '')}"></td>
				<td><input type="time" class="form-control input-sm xp-s" value="${esc(r.start_time)}"></td>
				<td><input type="time" class="form-control input-sm xp-e" value="${esc(r.end_time)}"></td>
				<td><select class="form-control input-sm xp-v">${venue_opts(r.venue)}</select></td>
				<td><input type="number" class="form-control input-sm xp-c" value="${esc(r.seat_capacity)}" placeholder="${__('room')}"></td>
				<td><select class="form-control input-sm xp-f">${fac_opts(r.invigilator)}</select></td>
				<td class="xp-msg"></td></tr>`).join('');
			$cards.eq(0).html(`
				<div class="xp-table"><table class="table table-sm"><thead><tr><th>${__('Course')}</th><th>${__('Students')}</th><th>${__('Date')}</th><th>${__('Start')}</th><th>${__('End')}</th>
					<th>${__('Venue (seats)')}</th><th>${__('Seats')}</th><th>${__('Invigilator')}</th><th>${__('Check')}</th></tr></thead><tbody>${rows || `<tr><td colspan="9">${__('Map courses first.')}</td></tr>`}</tbody></table></div>
				<div class="xp-issues"></div>
				<div class="xp-bar"><span class="xp-grow"></span><button class="btn btn-default btn-sm xp-run-check">${__('Check')}</button>
					<button class="btn btn-primary btn-sm xp-save-tt">${__('Save timetable')}</button></div>`);
			const collect = () => $cards.eq(0).find('tbody tr[data-course]').map((_, tr) => {
				const $tr = $(tr);
				return { course: $tr.data('course'), exam_date: $tr.find('.xp-d').val(), start_time: $tr.find('.xp-s').val(), end_time: $tr.find('.xp-e').val(),
					venue: $tr.find('.xp-v').val(), seat_capacity: $tr.find('.xp-c').val(), invigilator: $tr.find('.xp-f').val() };
			}).get();
			$cards.eq(0).find('.xp-v').on('change', (e) => {
				const v = t.venues.find((x) => x.name === $(e.target).val());
				$(e.target).closest('tr').find('.xp-c').val(v ? v.capacity : '');
			});
			const show = (res) => {
				$cards.eq(0).find('.xp-msg').html('');
				$cards.eq(0).find('tbody tr').removeClass('xp-flag');
				const items = [...res.errors.map((x) => ({ ...x, bad: 1 })), ...res.warnings];
				items.forEach((x) => {
					const $tr = $cards.eq(0).find(`tbody tr[data-i="${x.row - 1}"]`);
					if (x.bad) $tr.addClass('xp-flag');
					$tr.find('.xp-msg').append(`<div class="xp-pill ${x.bad ? 'bad' : 'warn'}">${esc(x.message)}</div>`);
				});
				$cards.eq(0).find('.xp-issues').html(res.errors.length
					? `<div class="xp-alert bad">${__('{0} problem(s) to fix before saving.', [res.errors.length])}</div>`
					: `<div class="xp-alert ok">${__('No clashes.')}${res.warnings.length ? ' ' + __('{0} warning(s).', [res.warnings.length]) : ''}</div>`);
			};
			if (t.rows.some((r) => r.exam_date)) show(t.check);
			$cards.eq(0).find('.xp-run-check').on('click', () => call('check_timetable', { exam_plan: this.plan, rows: JSON.stringify(collect()) }).then(show));
			$cards.eq(0).find('.xp-save-tt').on('click', () => call('save_timetable', { exam_plan: this.plan, rows: JSON.stringify(collect()) })
				.then(() => { frappe.show_alert({ message: __('Timetable saved'), indicator: 'green' }); this.refresh(); }));

			const made = new Set(t.assessment_schedules.map((a) => a.programme));
			$cards.eq(1).html(`
				<div class="xp-table"><table class="table table-sm"><thead><tr><th>${__('Schedule')}</th><th>${__('Programme')}</th><th>${__('Rows')}</th><th>${__('Status')}</th></tr></thead><tbody>
				${t.assessment_schedules.map((a) => `<tr><td><a href="/desk/exam-assessment-schedule/${encodeURIComponent(a.name)}">${esc(a.name)}</a></td><td>${esc(a.programme)}</td><td class="num">${a.rows}</td><td>${esc(a.status)}</td></tr>`).join('') || `<tr><td colspan="4">${__('None yet')}</td></tr>`}
				</tbody></table></div>
				<div class="xp-bar">${t.programmes.filter((p) => !made.has(p)).map((p) => `<button class="btn btn-default btn-sm xp-eas" data-p="${esc(p)}">${__('Create for {0}', [esc(p)])}</button>`).join('')}</div>`);
			$cards.eq(1).find('.xp-eas').on('click', (e) => call('create_assessment_schedule', { exam_plan: this.plan, programme: $(e.currentTarget).data('p') })
				.then((name) => frappe.set_route('Form', 'Exam Assessment Schedule', name)));
		});
	}

	// ── 3. Students ────────────────────────────────────────────────────
	render_students() {
		call('get_students', { exam_plan: this.plan }).then((rows) => {
			this.$body.html(this.card(__('Students'),
				__('Enrolled students of each course\'s Classes in this term. Detained = not eligible in Attendance Summary (attendance %, condonation and FA/MFA counted); classes without sessions yet are left alone.'),
				'Student Course Marks, Exam Barcode'));
			const $c = this.$body.find('.xp-card-body');
			$c.html(`
				<div class="xp-bar"><button class="btn btn-primary btn-sm xp-sync">${__('Sync students for all courses')}</button>
					<button class="btn btn-default btn-sm xp-elig">${__('Update eligibility from attendance')}</button>
					<span class="xp-grow"></span>${__('Copies')} <input type="number" class="form-control input-sm xp-copies" value="1" min="1" style="width:70px">
					<button class="btn btn-default btn-sm xp-bc">${__('Generate barcodes')}</button></div>
				<div class="xp-table"><table class="table table-sm"><thead><tr><th>${__('Course')}</th><th>${__('In Classes')}</th><th>${__('In plan')}</th><th>${__('Detained')}</th><th>${__('Added by hand')}</th><th>${__('Barcodes')}</th></tr></thead><tbody>
				${rows.map((r) => `<tr class="${r.synced < r.in_classes ? 'xp-flag' : ''}"><td><b>${esc(r.course)}</b></td><td class="num">${r.in_classes}</td><td class="num">${r.synced}</td>
					<td class="num">${r.detained ? `<span class="xp-pill bad">${r.detained}</span>` : 0}</td><td class="num">${r.manual}</td><td class="num">${r.barcodes}</td></tr>`).join('')}</tbody></table></div>
				<div class="xp-bar xp-soft">${__('Single students, arrear attempts, CSV of registration IDs and Class-wise adding stay on')}
					<a class="xp-link" data-route="examination-result">${__('Course Results')}</a> · <a class="xp-link" data-route="exam-barcode-sheet">${__('Exam Barcode Sheet')}</a> ${__('(attendance sheets)')}</div>`);
			$c.find('.xp-link').on('click', (e) => frappe.set_route($(e.currentTarget).data('route')));
			$c.find('.xp-sync').on('click', () => call('sync_all_students', { exam_plan: this.plan }).then((r) => {
				frappe.msgprint(__('{0} added, {1} already in the plan.', [r.added, r.skipped]) + (r.errors.length ? '<br><br>' + r.errors.map(esc).join('<br>') : ''));
				this.refresh();
			}));
			$c.find('.xp-elig').on('click', () => call('update_eligibility', { exam_plan: this.plan }).then((r) => {
				frappe.msgprint(__('{0} detained, {1} cleared, {2} without attendance yet.', [r.detained, r.cleared, r.no_attendance_yet]));
				this.refresh();
			}));
			$c.find('.xp-bc').on('click', () => call('generate_barcodes', { exam_plan: this.plan, copies: $c.find('.xp-copies').val() })
				.then((r) => { frappe.show_alert({ message: r.message || __('Barcodes generated'), indicator: 'green' }); this.refresh(); }));
		});
	}

	// ── 4. Marks ───────────────────────────────────────────────────────
	render_marks() {
		call('get_marks_progress', { exam_plan: this.plan }).then((rows) => {
			this.$body.html(this.card(__('Marks access for the whole plan'),
				__('Applied to every course. Each course\'s Class faculty become its evaluators. Fine-tune one course on Result Settings.'),
				'Access Result Settings') + this.card(__('Entry progress'),
				__('Marks are entered on Course Results (desk) or the faculty portal (Grades, Assessment Marks), including Excel import.'), ''));
			const $cards = this.$body.find('.xp-card-body');
			const fields = [
				{ fieldname: 'view_access', label: __('View Access'), fieldtype: 'Check', default: 1 },
				{ fieldname: 'view_deadline', label: __('View Access Deadline'), fieldtype: 'Datetime' },
				{ fieldname: 'col1', fieldtype: 'Column Break' },
				{ fieldname: 'edit_access', label: __('Edit Access'), fieldtype: 'Check', default: 1 },
				{ fieldname: 'edit_deadline', label: __('Edit Access Deadline'), fieldtype: 'Datetime' },
				{ fieldname: 'sec', fieldtype: 'Section Break', label: __('Grade / Schema Access') },
				{ fieldname: 'auto_generate_grade_access', label: __('Auto Generate Grade Access'), fieldtype: 'Check' },
				{ fieldname: 'edit_grade_access', label: __('Edit Grade Access (Manually / Bulk Upload)'), fieldtype: 'Check' },
				{ fieldname: 'relative_grading_access', label: __('Complete Relative Grading - Manual Schema Access'), fieldtype: 'Check' },
				{ fieldname: 'col2', fieldtype: 'Column Break' },
				{ fieldname: 'mask_student_info', label: __('Mask Student Information'), fieldtype: 'Check' },
				{ fieldname: 'generate_grade_report', label: __('Generate Grade Report'), fieldtype: 'Check' },
				{ fieldname: 'moderation_policy_access', label: __('Moderation Policy Access'), fieldtype: 'Check' },
			];
			const $form = $('<div></div>').appendTo($cards.eq(0));
			const fg = new frappe.ui.FieldGroup({ fields, body: $form[0] });
			fg.make();
			$cards.eq(0).append(`<div class="xp-bar"><span class="xp-grow"></span><a class="xp-link" data-route="result-settings">${__('Result Settings')}</a>
				<button class="btn btn-primary btn-sm xp-acc">${__('Apply to every course ({0})', [rows.length])}</button></div>`);
			$cards.eq(0).find('.xp-acc').on('click', () => {
				const v = fg.get_values(true);
				const settings = {};
				fields.filter((f) => f.fieldtype === 'Check' || f.fieldtype === 'Datetime').forEach((f) => { settings[f.fieldname] = f.fieldtype === 'Check' ? (v[f.fieldname] ? 1 : 0) : (v[f.fieldname] || null); });
				call('apply_access', { exam_plan: this.plan, settings: JSON.stringify(settings) })
					.then((n) => { frappe.show_alert({ message: __('Access saved for {0} courses', [n]), indicator: 'green' }); this.refresh(); });
			});
			$cards.eq(1).html(`<div class="xp-table"><table class="table table-sm"><thead><tr><th>${__('Course')}</th><th>${__('Evaluators')}</th><th>${__('Access')}</th>
				<th>${__('Marks entered')}</th><th></th><th>${__('Graded')}</th><th>${__('Submitted')}</th><th>${__('Locked')}</th></tr></thead><tbody>
				${rows.map((r) => {
					const pct = r.students ? Math.round((r.entered / r.students) * 100) : 0;
					return `<tr><td><b>${esc(r.course)}</b></td><td>${esc((r.evaluators || []).join(', ') || '—')}</td>
						<td>${r.access ? `<span class="xp-pill ${r.access.status === 'LOCKED' ? 'warn' : 'ok'}">${esc(r.access.status)}</span>${r.access.edit_deadline ? `<br><small>${__('edit till')} ${frappe.datetime.str_to_user(r.access.edit_deadline)}</small>` : ''}` : `<span class="xp-pill bad">${__('No access')}</span>`}</td>
						<td class="num">${r.entered} / ${r.students}</td><td><div class="xp-meter"><i style="width:${pct}%"></i></div></td>
						<td class="num">${r.graded}</td><td class="num">${r.submitted}</td><td class="num">${r.locked}</td></tr>`;
				}).join('')}</tbody></table></div>
				<div class="xp-bar"><span class="xp-grow"></span><a class="xp-link" data-route="examination-result">${__('Open Course Results')}</a></div>`);
			this.$body.find('.xp-link').on('click', (e) => frappe.set_route($(e.currentTarget).data('route')));
		});
	}

	// ── 5. Results ─────────────────────────────────────────────────────
	render_results() {
		call('get_results', { exam_plan: this.plan }).then((r) => {
			this.$body.html(this.card(__('Results'), __('Run these in order. Each button uses the same function as its own page.'), 'Student Course Marks, Student Result Publish'));
			const $c = this.$body.find('.xp-card-body');
			const total = r.marks.Draft + r.marks.Submitted + r.marks.Locked;
			const item = (n, done, title, desc, btn, cls, page) => `<li class="${done ? 'done' : ''}"><span class="xp-dot">${done ? '✓' : n}</span>
				<div><b>${title}</b><p>${desc}</p></div><div class="xp-actions">${btn ? `<button class="btn btn-sm ${done ? 'btn-default' : 'btn-primary'} ${cls}">${btn}</button>` : ''}
				${page ? `<a class="xp-link" data-route="${page[0]}">${page[1]}</a>` : ''}</div></li>`;
			$c.html(`
				<div class="xp-kpis"><div><b>${total}</b><span>${__('marks records')}</span></div><div><b>${r.marks.Draft}</b><span>${__('Draft')}</span></div>
					<div><b>${r.marks.Submitted}</b><span>${__('Submitted')}</span></div><div><b>${r.marks.Locked}</b><span>${__('Locked')}</span></div>
					<div><b>${r.fails}</b><span>${__('fail grades')}</span></div><div><b>${r.published} / ${r.results}</b><span>${__('published')}</span></div><div><b>${r.avg_gpa}</b><span>${__('average Term GPA')}</span></div></div>
				<ol class="xp-check">
					${item(1, total && !r.marks.Draft, __('Submit grades'), __('Every Draft marks record becomes Submitted; faculty can no longer edit them.'), __('Submit all'), 'xp-submit')}
					${item(2, total && r.marks.Locked === total, __('Lock'), __('Every marks record and every course\'s access becomes Locked. Later changes go through Grade Appeal.'), __('Lock all'), 'xp-lock')}
					${item(3, r.results > 0, __('Generate term results'), __('Term GPA, Term %, Cumulative GPA / % for every student.'), __('Generate'), 'xp-gen', ['term-result', __('Term Result')])}
					${item(4, !!r.publish_setting, __('Publish settings'), __('What students see: components, SGPA, e-grade sheet, hold for unpaid fees / feedback.'), '', '', ['result-settings', __('Result Settings')])}
					${item(5, r.results && r.published === r.results, __('Publish'), __('Results appear on the student and parent portals.'), __('Publish all'), 'xp-pub', ['publish-result', __('Publish Result')])}
					${item(6, r.re_exam_settings || r.improvement_settings, __('Re-exam and improvement'), __('Open the windows, fees and deadlines; mark payments; enter re-exam / improvement marks.'), '', '', ['re-exam', __('Re Exam')])}
				</ol>
				<div class="xp-bar xp-soft"><a class="xp-link" data-route="improvement-exam">${__('Improvement Exam')}</a> · <a href="/desk/grade-appeal">${__('Grade Appeals')}</a></div>`);
			$c.find('.xp-link').on('click', (e) => frappe.set_route($(e.currentTarget).data('route')));
			const run = (method, args, msg) => call(method, Object.assign({ exam_plan: this.plan }, args)).then((n) => { frappe.show_alert({ message: msg(n), indicator: 'green' }); this.refresh(); });
			$c.find('.xp-submit').on('click', () => run('set_status_all', { status: 'Submitted' }, (n) => __('{0} submitted', [n])));
			$c.find('.xp-lock').on('click', () => frappe.confirm(__('Lock every marks record and course of this plan?'), () => run('set_status_all', { status: 'Locked' }, (n) => __('{0} locked', [n]))));
			$c.find('.xp-gen').on('click', () => run('generate_results', {}, (n) => __('Results for {0} students', [n])));
			$c.find('.xp-pub').on('click', () => frappe.confirm(__('Publish results of every student in this plan?'), () => run('publish_all', { publish: 1 }, (n) => __('{0} published', [n]))));
		});
	}

	add_styles() {
		if (document.getElementById('xp-styles')) return;
		$('head').append(`<style id="xp-styles">
			.xp-wrap{display:flex;flex-direction:column;gap:16px;padding:8px 0 40px}
			.xp-head{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
			.xp-head .xp-plan{max-width:420px;font-weight:600}
			.xp-meta{color:var(--text-muted)}
			.xp-steps{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:8px;overflow-x:auto}
			.xp-step{display:flex;gap:10px;align-items:flex-start;text-align:left;border:1px solid var(--border-color);background:var(--card-bg);border-radius:8px;padding:10px 12px;cursor:pointer}
			.xp-step.on{border-color:var(--er-brand,#920C24);box-shadow:inset 0 -3px 0 var(--er-brand,#920C24)}
			.xp-step.locked{opacity:.55}
			.xp-step-n{font-family:var(--er-font);font-weight:900;color:var(--er-brand,#920C24);font-size:18px;line-height:1}
			.xp-step-t{display:flex;flex-direction:column;flex:1;min-width:0}.xp-step-t small{color:var(--text-muted);font-size:11px}
			.xp-card{border:1px solid var(--border-color);border-radius:10px;background:var(--card-bg);padding:16px;display:flex;flex-direction:column;gap:12px}
			.xp-card+.xp-card{margin-top:4px}
			.xp-card-head{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;align-items:flex-start}
			.xp-card-head h4{margin:0 0 4px;font-weight:700}.xp-card-head p{margin:0;color:var(--text-muted);max-width:90ch}
			.xp-saves{font-size:12px;color:var(--text-muted);border:1px dashed var(--border-color);border-radius:6px;padding:3px 8px}
			.xp-card-body{display:flex;flex-direction:column;gap:12px}
			.xp-table{overflow-x:auto;border:1px solid var(--border-color);border-radius:8px}
			.xp-table table{margin:0}.xp-table th{font-size:12px;color:var(--text-muted);white-space:nowrap;background:var(--subtle-fg)}
			.xp-table td{vertical-align:middle}.xp-table td:first-child{min-width:180px}.xp-table td.num{text-align:right;font-variant-numeric:tabular-nums}
			.xp-table select,.xp-table input.form-control{min-width:160px}
			.xp-wrap select.form-control,.xp-wrap input.form-control{background-color:var(--control-bg,#fff);border:1px solid var(--border-color,#d1d5db);border-radius:6px;height:32px;color:var(--text-color);font-family:inherit;font-size:13px}
			.xp-wrap select.form-control{appearance:none;-webkit-appearance:none;padding-right:28px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 8px center}
			.xp-wrap select.form-control:focus,.xp-wrap input.form-control:focus{border-color:var(--er-brand,#920C24);box-shadow:0 0 0 2px var(--er-brand-soft,#f6dde1)}
			.xp-wrap .btn-default{background:var(--control-bg,#fff);border:1px solid var(--border-color,#d1d5db);color:var(--text-color)}
			.xp-wrap .btn-default:hover{border-color:var(--er-brand,#920C24);color:var(--er-brand,#920C24)}
			.xp-wrap .btn-primary{background:var(--er-brand,#920C24);border-color:var(--er-brand,#920C24);color:#fff}
			.xp-wrap .btn[disabled]{opacity:.5}
			.xp-guide{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;border-left:4px solid var(--blue-500,#3b82f6);background:var(--bg-blue,#eff6ff);border-radius:6px;padding:10px 14px}
			.xp-guide.warn{border-color:var(--orange-500,#f59e0b);background:var(--bg-orange,#fff7ed)}
			.xp-guide.ok{border-color:var(--green-500,#22c55e);background:var(--bg-green,#f0fdf4)}
			.xp-guide-actions{display:flex;gap:8px;flex-basis:100%}
			.xp-wrap .btn[disabled]{cursor:not-allowed}
			.xp-table tr.xp-flag td{background:var(--bg-red,#fde6e8)}
			.xp-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.xp-bar select{max-width:220px}
			.xp-soft{background:var(--subtle-fg);border-radius:8px;padding:8px 10px}
			.xp-grow{flex:1}
			.xp-pill{display:inline-block;font-size:11px;font-weight:700;padding:2px 7px;border-radius:4px;margin:1px 0}
			.xp-pill.ok{background:var(--bg-green,#e5f4ea);color:var(--text-on-green,#1d6b3a)}
			.xp-pill.warn{background:var(--bg-yellow,#fdf1d2);color:var(--text-on-yellow,#8a5a00)}
			.xp-pill.bad{background:var(--bg-red,#fde6e8);color:var(--text-on-red,#b0182b)}
			.xp-pill.info{background:var(--bg-blue,#e6edf9);color:var(--text-on-blue,#2d4f8a)}
			.xp-msg{min-width:220px;white-space:normal}.xp-msg .xp-pill{display:block;font-weight:600}
			.xp-alert{border-radius:8px;padding:8px 12px}.xp-alert.bad{background:var(--bg-red,#fde6e8)}.xp-alert.ok{background:var(--bg-green,#e5f4ea)}
			.xp-meter{height:8px;border-radius:4px;background:var(--border-color);min-width:90px;overflow:hidden}.xp-meter i{display:block;height:100%;background:var(--er-brand,#920C24)}
			.xp-kpis{display:flex;flex-wrap:wrap;gap:24px}.xp-kpis b{display:block;font-size:20px;font-family:var(--er-font)}.xp-kpis span{font-size:12px;color:var(--text-muted)}
			.xp-check{list-style:none;margin:0;padding:0}
			.xp-check li{display:grid;grid-template-columns:32px minmax(0,1fr) auto;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--border-color)}
			.xp-check li:last-child{border-bottom:0}.xp-check p{margin:2px 0 0;color:var(--text-muted)}
			.xp-dot{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;border:2px solid var(--border-color);font-weight:700}
			.xp-check li.done .xp-dot{background:var(--green-500,#1d6b3a);border-color:var(--green-500,#1d6b3a);color:#fff}
			.xp-actions{display:flex;gap:10px;align-items:center}.xp-link{cursor:pointer}
			.xp-empty{text-align:center;padding:60px 16px}
			@media (max-width:860px){.xp-steps{grid-template-columns:repeat(5,minmax(140px,1fr))}}
		</style>`);
	}
}
