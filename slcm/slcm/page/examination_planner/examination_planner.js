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
	planner.take_step_option();
	if (plan && plan !== planner.plan) planner.open(plan);
	else planner.refresh();
};

const API = 'slcm.slcm.page.examination_planner.examination_planner.';
const esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));
const call = (method, args) => frappe.call({ method: API + method, args: args || {}, freeze: true }).then((r) => r.message);

const STEPS = [
	{ key: 'plan', label: __('Plan & courses'), hint: __('Map each course to its schemas') },
	{ key: 'timetable', label: __('Exam timetable'), hint: __('Dates, rooms, invigilators') },
	{ key: 'courses', label: __('Students & marks'), hint: __('Students, eligibility, barcodes, marks') },
	{ key: 'results', label: __('Results & publish'), hint: __('Lock, term GPA, publish') },
	// opens with step 4 and is never "done": re-exams and appeals come and go
	{ key: 'after', label: __('After results'), hint: __('Re-exam timetable, re-exam, improvement'), always: true },
];
const LAST = STEPS.length - 1;
// Screens from the result pages, mounted inside steps 3 and 4 (see slcm/public/js/exam/)
const EXAM_UI = (mod) => new Promise((resolve) => frappe.require(['/assets/slcm/js/exam/common.js', `/assets/slcm/js/exam/${mod}.js`], () => resolve(slcm.exam_ui[mod])));

class ExamPlanner {
	constructor(page, wrapper) {
		this.page = page;
		this.step = null;   // open() lands on the first unfinished step
		this.take_step_option();
		this.$root = $('<div class="xp-wrap"></div>').appendTo(page.main);
		this.add_styles();
		page.set_primary_action(__('New Exam Plan'), () => this.new_plan_dialog(), 'add');
		page.add_inner_button(__('Examination Settings'), () => frappe.set_route('Form', 'Examination Settings'));
		this.load_plans().then(() => {
			// no plan in the URL (e.g. the Re Exam link): reopen the plan last worked on
			let last = null;
			try { last = localStorage.getItem('xp-last-plan'); } catch (e) { /* storage blocked */ }
			const known = (name) => name && this.plans.some((x) => x.name === name);
			const plan = frappe.get_route()[1] || (known(last) && last) || (this.plans[0] && this.plans[0].name);
			if (plan) this.open(plan);
			else this.render_empty();
		});
	}

	// Other pages open a given step with frappe.route_options = { step: <0-4> }
	// (frappe.flags.exam_planner_open is used by the redirecting Re Exam / Improvement routes)
	take_step_option() {
		const opt = frappe.flags.exam_planner_open || frappe.route_options;
		const want = opt && opt.step;
		if (want === undefined || want === null) return;
		this.step = Math.min(LAST, Math.max(0, +want || 0));
		if (opt.after_tab) this.after_tab = opt.after_tab;
		this.course = null;
		frappe.flags.exam_planner_open = null;
		frappe.route_options = null;
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
		try { localStorage.setItem('xp-last-plan', plan); } catch (e) { /* storage blocked */ }
		if (frappe.get_route()[1] !== plan) frappe.set_route('examination-planner', plan);
		return call('get_overview', { exam_plan: plan }).then((o) => {
			this.o = o;
			// step 3 covers the server's "students" and "marks" checks
			o.done = { plan: o.steps.plan, timetable: o.steps.timetable, courses: o.steps.students && o.steps.marks, results: o.steps.results };
			const first_open = STEPS.findIndex((s) => !s.always && !o.done[s.key]);
			if (this.step === null || this.step === undefined) this.step = Math.max(0, first_open === -1 ? LAST - 1 : first_open);
			this.render();
		});
	}

	refresh() { return this.open(this.plan); }


	// ── layout ─────────────────────────────────────────────────────────
	// Screens mounted from slcm/public/js/exam/ are torn down before the step re-renders
	unmount() {
		if (this.mounted) this.mounted.destroy();
		this.mounted = null;
	}

	mount(mod, el, opts) {
		this.unmount();
		const token = (this.mount_token = (this.mount_token || 0) + 1);
		return EXAM_UI(mod).then((fn) => {
			if (token !== this.mount_token || !document.body.contains(el)) return;   // step changed meanwhile
			this.mounted = fn(el, Object.assign({ embedded: true, exam_plan: this.plan }, opts));
		});
	}

	render() {
		this.unmount();
		const o = this.o, p = o.plan;
		const options = this.plans.map((x) => `<option value="${esc(x.name)}" ${x.name === p.name ? 'selected' : ''}>${esc(x.exam_name)} · ${esc(x.term || '')}</option>`).join('');
		const term = o.term ? `${frappe.datetime.str_to_user(o.term.term_start_date)} – ${frappe.datetime.str_to_user(o.term.term_end_date)}` : __('No term');
		const steps = STEPS.map((s, i) => {
			// every step can be opened at any time; Done only marks the finished ones
			const done = o.done[s.key];
			return `<button class="xp-step ${i === this.step ? 'on' : ''}" data-i="${i}">
				<span class="xp-step-n">${i + 1}</span><span class="xp-step-t"><b>${s.label}</b><small>${s.hint}</small></span>
				${done ? `<span class="xp-pill ok">${__('Done')}</span>` : ''}</button>`;
		}).join('');
		this.$root.html(`
			<div class="xp-head">
				<select class="form-control xp-plan">${options}</select>
				<div class="xp-meta"><b>${esc(p.term || '')}</b> · ${term} · <a href="/desk/exam-plan/${encodeURIComponent(p.name)}">${__('Open Exam Plan form')}</a></div>
			</div>
			<div class="xp-steps">${steps}</div>
			<div class="xp-body"></div>`);
		this.$root.find('.xp-plan').on('change', (e) => { this.step = null; this.course = null; this.open($(e.target).val()); });
		this.$root.find('.xp-step').on('click', (e) => {
			const i = +$(e.currentTarget).data('i');
			this.step = i;
			this.course = null;
			this.render();
		});
		this.$body = this.$root.find('.xp-body');
		[this.render_plan, this.render_timetable, this.render_courses, this.render_results, this.render_after][this.step].call(this);
	}

	card(title, sub, saves) {
		return `<div class="xp-card"><div class="xp-card-head"><div><h4>${title}</h4>${sub ? `<p>${sub}</p>` : ''}</div>
			${saves ? `<span class="xp-saves">${__('Saves to')} <b>${saves}</b></span>` : ''}</div><div class="xp-card-body"></div></div>`;
	}

	// ── 1. Plan & courses ──────────────────────────────────────────────
	render_plan() {
		call('get_mapping', { exam_plan: this.plan }).then((m) => {
			this.$body.html(this.card(__('Map each course to its schemas'),
				__('Every course taught this term needs an Evaluation Schema (how it is marked) and a Grading Schema (how marks become grades).'),
				''));
			const $c = this.$body.find('.xp-card-body');
			const evs = m.evaluation_schemas.map((e) => e.name), gss = m.grade_schemas.map((g) => g.name);
			const NEW = '__new__';
			const sel = (list, val, cls, doctype) => `<select class="form-control input-sm xp-select ${cls}" data-doctype="${doctype}">
				<option value="">${list.length ? __('Select…') : __('None yet')}</option>
				${(val && !list.includes(val) ? [val, ...list] : list).map((x) => `<option ${x === val ? 'selected' : ''}>${esc(x)}</option>`).join('')}
				<option value="${NEW}">+ ${__('Create new {0}…', [__(doctype)])}</option></select>`;
			const missing = [!evs.length && 'Evaluation Schema', !gss.length && 'Grading Schema'].filter(Boolean);
			const su = m.setup || {};
			const setup_todo = !su.components || !su.assessment_types || missing.length;
			const by_course = {};
			m.courses.forEach((c) => { by_course[c.course] = c; });
			const mapped = m.courses.filter((c) => c.source === 'saved');
			const unmapped = m.courses.filter((c) => c.source !== 'saved');
			const why = (c) => (c.source || '').startsWith('last plan') ? __('Suggested from the last exam plan of this course')
				: c.source === 'settings default' ? __('Suggested from the defaults in Examination Settings') : '';
			const head = (c) => `<div class="xp-cr-name"><b>${esc(c.course_name || c.course)}</b>
				<small>${esc(c.course_code || c.course)} · ${esc(c.programme || '')} · ${__('{0} students', [c.enrolled_students || 0])}</small></div>`;

			const mapped_row = (c) => `<div class="xp-cr" data-course="${esc(c.course)}">
				${head(c)}
				<div class="xp-cr-view">
					<span><small>${__('Evaluation')}</small><button class="xp-schema-link" data-doctype="Evaluation Schema" data-name="${esc(c.evaluation_schema)}" title="${__('View schema')}">${esc(c.evaluation_schema)}</button></span>
					<span><small>${__('Grading')}</small><button class="xp-schema-link" data-doctype="Grading Schema" data-name="${esc(c.grade_schema)}" title="${__('View schema')}">${esc(c.grade_schema)}</button></span>
					<span class="xp-pill ok">✓ ${__('Mapped')}</span>
				</div>
				<div class="xp-cr-edit" style="display:none">${sel(evs, c.evaluation_schema, 'xp-ev', 'Evaluation Schema')}${sel(gss, c.grade_schema, 'xp-gs', 'Grading Schema')}</div>
				<div class="xp-cr-act">
					<button class="btn btn-default btn-sm xp-change">${__('Change')}</button>
					<button class="btn btn-default btn-sm xp-remove">${__('Remove')}</button>
					<button class="btn btn-primary btn-sm xp-save-one" style="display:none">${__('Save')}</button>
					<button class="btn btn-default btn-sm xp-cancel" style="display:none">${__('Cancel')}</button>
				</div></div>`;
			const unmapped_row = (c) => {
				const ev = c.suggest_evaluation_schema || '', gs = c.suggest_grade_schema || '';
				return `<div class="xp-cr todo" data-course="${esc(c.course)}">
					${head(c)}
					<div class="xp-cr-edit">${sel(evs, ev, 'xp-ev', 'Evaluation Schema')}${sel(gss, gs, 'xp-gs', 'Grading Schema')}
						<button class="xp-schema-link xp-peek" data-for="xp-ev">${__('View')}</button><button class="xp-schema-link xp-peek" data-for="xp-gs">${__('View')}</button>
						${why(c) ? `<small class="xp-why">${why(c)}</small>` : ''}</div>
					<div class="xp-cr-act"><button class="btn btn-primary btn-sm xp-save-one">${__('Map')}</button></div></div>`;
			};

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
					</ol>` : '';
			const total = m.courses.length;
			const progress = total ? `<div class="xp-map-progress"><b>${__('{0} of {1} courses mapped', [mapped.length, total])}</b>
				<div class="xp-bar-track"><i style="width:${Math.round(mapped.length * 100 / total)}%"></i></div></div>` : '';
			const suggested = unmapped.filter((c) => c.suggest_evaluation_schema && c.suggest_grade_schema).length;

			$c.html(guide + (total ? `
				<div class="xp-bar">${progress}<span class="xp-grow"></span>
					${missing.length ? '' : `<button class="btn btn-default btn-sm xp-new-es">+ ${__('Evaluation Schema')}</button>
					<button class="btn btn-default btn-sm xp-new-gs">+ ${__('Grading Schema')}</button>`}</div>
				${unmapped.length ? `<div class="xp-cr-group"><div class="xp-cr-title"><h5>${__('Not mapped yet')} <span class="xp-count">${unmapped.length}</span></h5>
					${suggested > 1 ? `<button class="btn btn-primary btn-sm xp-map-all">${__('Map all {0} as suggested', [suggested])}</button>` : ''}</div>
					${unmapped.map(unmapped_row).join('')}</div>` : ''}
				${mapped.length ? `<div class="xp-cr-group"><div class="xp-cr-title"><h5>${__('Mapped')} <span class="xp-count">${mapped.length}</span></h5></div>
					${mapped.map(mapped_row).join('')}</div>` : ''}
				${!unmapped.length ? `<div class="xp-next"><span>✓ ${__('Every course is mapped.')}</span>
					<button class="btn btn-primary xp-go-next">${__('Continue to step 2: Exam timetable')} →</button></div>` : ''}`
				: `<div class="xp-guide">${__('No Classes in this term yet. Create Classes first (Programme Management).')}</div>`));

			$c.find('.xp-new-es').on('click', () => this.schema_dialog('Evaluation Schema'));
			$c.find('.xp-new-gs').on('click', () => this.schema_dialog('Grading Schema'));
			$c.find('.xp-add-comp').on('click', () => this.masters_dialog('Exam Component'));
			$c.find('.xp-add-atype').on('click', () => this.masters_dialog('Exam Assessment Type'));
			$c.find('.xp-go-next').on('click', () => { this.step = 1; this.refresh(); });
			$c.on('click', '.xp-schema-link', (e) => {
				const $b = $(e.currentTarget);
				if (!$b.data('for')) { this.schema_view($b.data('doctype'), $b.data('name')); return; }
				const $sel = $b.closest('.xp-cr').find('.' + $b.data('for'));
				const name = $sel.val();
				if (!name || name === NEW) { frappe.show_alert({ message: __('Pick a schema first.'), indicator: 'orange' }); return; }
				this.schema_view($sel.data('doctype'), name);
			});
			// A schema just made in the panel goes to every course still without one
			Object.entries(this.prefill || {}).forEach(([doctype, name]) => {
				$c.find(`.xp-cr.todo .xp-select[data-doctype="${doctype}"]`).filter((_, el) => !el.value).val(name);
			});
			this.prefill = {};
			// "+ Create new…" in a dropdown opens the panel; the new schema comes back pre-selected
			$c.on('change', '.xp-select', (e) => {
				if (e.target.value !== NEW) return;
				e.target.value = '';
				this.schema_dialog($(e.target).data('doctype'));
			});

			const save = (rows, changed) => {
				const go = (reason) => call('save_mapping', { exam_plan: this.plan, assignments: JSON.stringify(rows), reason: reason || '' })
					.then(() => {
						frappe.show_alert({ message: rows.length === 1 ? __('{0} mapped', [by_course[rows[0].course].course_name || rows[0].course]) : __('{0} courses mapped', [rows.length]), indicator: 'green' });
						this.refresh();
					});
				if (changed && this.o.settings.require_change_reason) {
					frappe.prompt({ fieldname: 'reason', fieldtype: 'Small Text', label: __('Why are you changing the schemas?'), reqd: 1 },
						(v) => go(v.reason), __('Reason for change'), __('Save'));
				} else go();
			};
			const row_values = ($r) => ({ course: $r.data('course'), evaluation_schema: $r.find('.xp-ev').val(), grade_schema: $r.find('.xp-gs').val() });

			$c.find('.xp-save-one').on('click', (e) => {
				const $r = $(e.currentTarget).closest('.xp-cr'), v = row_values($r);
				if (!v.evaluation_schema || !v.grade_schema) {
					frappe.show_alert({ message: __('Pick both an Evaluation Schema and a Grading Schema.'), indicator: 'orange' });
					return;
				}
				const c = by_course[v.course];
				const changed = c.source === 'saved' && (c.evaluation_schema !== v.evaluation_schema || c.grade_schema !== v.grade_schema);
				if (c.source === 'saved' && !changed) { $r.find('.xp-cancel').trigger('click'); return; }
				save([v], changed);
			});
			$c.find('.xp-map-all').on('click', () => {
				const rows = $c.find('.xp-cr.todo').map((_, r) => row_values($(r))).get().filter((v) => v.evaluation_schema && v.grade_schema);
				frappe.confirm(__('Map {0} courses with the schemas shown?', [rows.length]), () => save(rows, false));
			});
			$c.find('.xp-change').on('click', (e) => {
				const $r = $(e.currentTarget).closest('.xp-cr');
				$r.addClass('editing').find('.xp-cr-view, .xp-change, .xp-remove').hide();
				$r.find('.xp-cr-edit, .xp-save-one, .xp-cancel').show();
			});
			$c.find('.xp-cancel').on('click', (e) => {
				const $r = $(e.currentTarget).closest('.xp-cr'), c = by_course[$r.data('course')];
				$r.find('.xp-ev').val(c.evaluation_schema);
				$r.find('.xp-gs').val(c.grade_schema);
				$r.removeClass('editing').find('.xp-cr-edit, .xp-save-one, .xp-cancel').hide();
				$r.find('.xp-cr-view, .xp-change, .xp-remove').show();
			});
			$c.find('.xp-remove').on('click', (e) => {
				const c = by_course[$(e.currentTarget).closest('.xp-cr').data('course')];
				const warn = this.o.counts.students ? `<br><br>${__('Marks already entered for this course are kept, but they will not be graded until the course is mapped again.')}` : '';
				frappe.confirm(`${__('Remove the schemas from <b>{0}</b>?', [esc(c.course_name || c.course)])}<br>${__('The course moves back to "Not mapped yet" and you can map it again at any time.')}${warn}`,
					() => call('unmap', { exam_plan: this.plan, courses: JSON.stringify([c.course]) }).then(() => {
						frappe.show_alert({ message: __('{0} removed', [c.course_name || c.course]), indicator: 'orange' });
						this.refresh();
					}));
			});
		});
	}

	// Read-only view of a schema, from the mapping step
	schema_view(doctype, name) {
		const grading = doctype === 'Grading Schema';
		const method = 'slcm.slcm.page.examination_result.examination_result.' + (grading ? 'get_grading_schema_details' : 'get_evaluation_schema_details');
		frappe.call({ method, args: { name } }).then((r) => {
			const x = r.message || {};
			const n = (v) => (v === null || v === undefined || v === '' ? '—' : esc(String(+v === +v ? +v : v)));
			const yes = (v) => (v ? `<span class="xp-pill bad">${__('Must pass')}</span>` : '');
			let body;
			if (grading) {
				body = `<div class="xp-sv-stats">
						<span><small>${__('Grading type')}</small><b>${esc(x.grading_type || '—')}</b></span>
						<span><small>${__('Out of')}</small><b>${n(x.maximum_marks)}</b></span>
						<span><small>${__('Grades')}</small><b>${(x.grades || []).length}</b></span></div>
					<table class="xp-sv-table"><thead><tr><th>${__('Grade')}</th><th>${__('Marks')}</th><th class="num">${__('Grade point')}</th><th></th></tr></thead><tbody>
					${(x.grades || []).map((g) => `<tr class="${g.failed ? 'fail' : ''}"><td><b>${esc(g.grade)}</b>${g.qualitative_meaning ? ` <small>${esc(g.qualitative_meaning)}</small>` : ''}</td>
						<td>${n(g.marks_from)} ${g.to_operator === '<' ? __('to under') : __('to')} ${n(g.marks_to)}</td>
						<td class="num">${n(g.grade_point)}</td><td>${g.failed ? `<span class="xp-pill bad">${__('Fail')}</span>` : ''}</td></tr>`).join('')}
					</tbody></table>`;
			} else {
				const comps = x.components || [], asmts = x.assessments || [];
				body = `<div class="xp-sv-stats">
						<span><small>${__('Total marks')}</small><b>${n(x.total_marks)}</b></span>
						<span><small>${__('Pass mark')}</small><b>${n(x.passing_marks)}</b></span>
						<span><small>${__('Components')}</small><b>${comps.length}</b></span></div>
					${comps.map((c) => {
						const rows = asmts.filter((a) => a.component === c.component);
						return `<div class="xp-sv-comp"><div class="xp-sv-comp-head"><b>${esc(c.component_name || c.component)}</b>
							<span>${__('{0} marks', [n(c.effective_max_marks)])}${c.passing_marks ? ' · ' + __('pass {0}', [n(c.passing_marks)]) : ''} ${yes(c.consider_for_pass_fail)}</span></div>
							${rows.length ? `<table class="xp-sv-table"><thead><tr><th>${__('Assessment')}</th><th class="num">${__('Marked out of')}</th><th class="num">${__('Counts as')}</th><th class="num">${__('Pass')}</th></tr></thead><tbody>
							${rows.map((a) => `<tr><td>${esc(a.label || a.type_name || a.assessment_type)} ${yes(a.consider_for_pass_fail)}</td><td class="num">${n(a.maximum_marks)}</td>
								<td class="num">${n(a.effective_marks)}</td><td class="num">${a.passing_marks ? n(a.passing_marks) : '—'}</td></tr>`).join('')}
							</tbody></table>` : `<p class="xp-muted">${__('No assessments')}</p>`}</div>`;
					}).join('')}
					<p class="xp-muted">${__('"Counts as" is what the assessment adds to the total; "Must pass" means a student fails the course if they fail that part.')}</p>`;
			}
			const d = new frappe.ui.Dialog({
				title: `${__(doctype)}: ${name}`,
				size: 'large',
				fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
				primary_action_label: __('Close'),
				primary_action: () => d.hide(),
				secondary_action_label: __('Open full {0}', [__(doctype)]),
				secondary_action: () => { d.hide(); frappe.set_route('Form', doctype, name); },
			});
			d.fields_dict.body.$wrapper.html(`<div class="xp-sv">${x.description ? `<p>${esc(x.description)}</p>` : ''}${body}</div>`);
			d.show();
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
	// Two tabs laid out like the office's Excel sheets: the classroom allocation
	// sheet and the Continuing Evaluation Schedule
	render_timetable() {
		call('get_timetable', { exam_plan: this.plan }).then((t) => {
			this.tt = t;
			this.tt_tab = this.tt_tab || 'timetable';
			this.$body.html(`<div class="xp-card">
				<div class="xp-rtabs">
					<button class="xp-rtab" data-tab="timetable">${__('Exam timetable')}</button>
					<button class="xp-rtab" data-tab="evaluation">${__('Continuing Evaluation Schedule')}</button>
				</div>
				<div class="xp-tab" data-tab="timetable"></div><div class="xp-tab" data-tab="evaluation"></div></div>`);
			const show = () => this.$body.find('.xp-rtab, .xp-tab').each((_, el) => {
				const on = $(el).data('tab') === this.tt_tab;
				$(el).toggleClass('on', on);
				if ($(el).hasClass('xp-tab')) $(el).toggle(on);
			});
			this.$body.find('.xp-rtab').on('click', (e) => { this.tt_tab = $(e.currentTarget).data('tab'); show(); });
			show();
			this.allocation_sheet(this.$body.find('.xp-tab[data-tab="timetable"]'), t);
			this.render_evaluation_schedule(this.$body.find('.xp-tab[data-tab="evaluation"]'), t);
		});
	}

	open_import_log(sheet) {
		frappe.set_route('List', 'Exam Sheet Import Log', { exam_plan: this.plan, sheet });
	}

	download(method, args) {
		const q = $.param({ exam_plan: this.plan, ...(args || {}) });
		window.open(`/api/method/${API}${method}?${q}`);
	}

	// Sheet import: Check sheet previews (problems listed, downloadable); the second click
	// imports the lines that pass and skips the rest. Every import goes to Exam Sheet Import Log.
	sheet_import_dialog(o) {
		let checked = null;
		const d = new frappe.ui.Dialog({
			title: o.title, size: 'large',
			fields: [
				{ fieldtype: 'HTML', options: `<p class="text-muted small">${o.help}</p>` },
				{ fieldname: 'file_url', fieldtype: 'Attach', label: __('Excel sheet (.xlsx)'), reqd: 1,
				  onchange: () => { checked = null; d.fields_dict.preview.$wrapper.html(''); d.set_primary_action(__('Check sheet'), run); d.get_primary_btn().removeClass('hide'); } },
				...(o.fields || []),
				{ fieldname: 'preview', fieldtype: 'HTML' },
			],
			secondary_action_label: __('Close'),
			secondary_action: () => d.hide(),
		});
		const args = () => ({ exam_plan: this.plan, ...d.get_values(), ...(o.args ? o.args(d) : {}) });
		const run = () => {
			if (!d.get_values()) return;
			const apply = checked ? 1 : 0;
			call(o.method, { ...args(), apply }).then((r) => {
				if (apply) {
					d.hide();
					const log = r.log ? ` <a href="/desk/exam-sheet-import-log/${encodeURIComponent(r.log)}">${__('Import log')}</a>` : '';
					frappe.show_alert({ message: (r.skipped ? __('{0} imported, {1} skipped.', [r.imported, r.skipped]) : __('{0} imported.', [r.imported])) + log,
						indicator: r.skipped ? 'orange' : 'green' }, 10);
					o.done(r);
					return;
				}
				checked = r;
				const $p = d.fields_dict.preview.$wrapper.html(o.preview(r));
				$p.find('.xp-dl-issues').on('click', () => this.download('download_import_issues', { ...args(), sheet: o.sheet }));
				const label = o.apply_label(r);
				if (label) d.set_primary_action(label, run);
				else d.get_primary_btn().addClass('hide');
			});
		};
		d.set_primary_action(__('Check sheet'), run);
		d.$wrapper.find('.modal-footer').prepend(`<a class="btn btn-link btn-sm xp-log-link" href="/desk/exam-sheet-import-log?exam_plan=${encodeURIComponent(this.plan)}" target="_blank">${__('Import log')}</a>`);
		d.show();
	}

	import_timetable_dialog() {
		const level = { error: 'bad', warning: 'warn', info: 'info' };
		this.sheet_import_dialog({
			title: __('Import exam timetable'), method: 'import_timetable', sheet: 'timetable',
			help: __('The classroom allocation sheet (same format as Download sheet). It replaces this plan\'s exam timetable. Papers, rooms and invigilators that are not Course / Venue Master / Faculty records are kept as written.'),
			fields: [{ fieldname: 'duration_hours', fieldtype: 'Float', label: __('Exam length (hours)'), default: 3,
			           description: __('Start times come from the session headers; end time = start + this.') }],
			apply_label: (r) => (!r.valid_lines ? null : r.error_lines
				? __('Import {0} valid line(s), skip {1}', [r.valid_lines, r.error_lines]) : __('Replace timetable')),
			preview: (r) => `<div class="xp-alert ${r.error_lines ? 'bad' : 'ok'}">${__('{0} line(s) over {1} day(s): {2} course(s), {3} paper(s) kept as text.', [r.lines, r.days, r.courses, r.text_only])}
				${r.error_lines ? ' ' + __('{0} line(s) have a problem and will be skipped; {1} line(s) are ready.', [r.error_lines, r.valid_lines]) : ' ' + __('All lines are ready.')}</div>
				${r.issues.length ? `<div class="xp-bar" style="margin-top:8px"><span class="xp-muted">${__('{0} note(s)', [r.issues.length])}</span><span class="xp-grow"></span>
					<button class="btn btn-default btn-xs xp-dl-issues">${__('Download problems')}</button></div>
				<div class="xp-table" style="max-height:300px;overflow:auto;margin-top:6px"><table class="table table-sm"><thead><tr><th>${__('Sheet rows')}</th><th></th><th>${__('Note')}</th></tr></thead><tbody>
				${r.issues.map((x) => `<tr><td>${esc(x.sheet_rows.length > 6 ? x.sheet_rows.slice(0, 6).join(', ') + ' … (' + x.sheet_rows.length + ')' : x.sheet_rows.join(', '))}</td><td><span class="xp-pill ${level[x.level]}">${esc(x.level)}</span></td><td>${esc(x.message)}</td></tr>`).join('')}</tbody></table></div>` : ''}`,
			done: () => this.refresh(),
		});
	}

	// Whether students can see the (re-)exam timetable, with the switch
	publish_bar($el, published, reexam) {
		const what = reexam ? __('re-exam timetable') : __('timetable');
		const $bar = $(`<div class="xp-pub-bar ${published ? 'on' : ''}">
			<span><b>${published ? '● ' + __('Published') : '○ ' + __('Not published')}</b>
			${published ? __('Students can see this {0} on the portal.', [what]) : __('Students cannot see this {0} yet. Publish it when the dates are final.', [what])}</span>
			<span class="xp-grow"></span>
			<button class="btn btn-sm ${published ? 'btn-default' : 'btn-primary'}">${published ? __('Hide from students') : __('Publish to students')}</button></div>`).appendTo($el);
		$bar.find('button').on('click', () => {
			const go = () => call('set_timetable_published', { exam_plan: this.plan, published: published ? 0 : 1, reexam: reexam ? 1 : 0 }).then(() => {
				frappe.show_alert({ message: published ? __('Hidden from students') : __('Published to students'), indicator: 'green' });
				this.render();
			});
			if (published) go();
			else frappe.confirm(__('Publish the {0}? Students will see the dates, times and rooms on the portal. Save your changes first.', [what]), go);
		});
	}

	// Timetable table (exam or re-exam): dates, rooms, seats, invigilators, with Check / Save
	tt_editor($el, t, o) {
		const venue_opts = (v) => `<option value=""></option>` + t.venues.map((x) => `<option value="${esc(x.name)}" ${x.name === v ? 'selected' : ''}>${esc(x.name)} (${x.capacity || 0})</option>`).join('');
		const can_add_inv = frappe.model.can_create('Faculty');
		const fac_opts = (v) => `<option value=""></option>` + t.faculty.map((x) => `<option value="${esc(x.name)}" ${String(x.name) === String(v) ? 'selected' : ''}>${esc(x.label)}</option>`).join('')
			+ (can_add_inv ? `<option value="__new_invigilator__">+ ${__('Add new invigilator…')}</option>` : '');
		const extra = o.failed ? `<th>${__('Failed')}</th>` : '';
		const rows = t.rows.map((r, i) => `<tr data-i="${i}" data-course="${esc(r.course)}">
			<td><b>${esc(r.course)}</b><br><small>${esc(r.course_name)}</small></td>${o.failed ? `<td class="num">${r.failed}</td>` : ''}<td class="num">${r.students}</td>
			<td><input type="date" class="form-control input-sm xp-d" value="${esc(r.exam_date || '')}"></td>
			<td><input type="time" class="form-control input-sm xp-s" value="${esc(r.start_time)}"></td>
			<td><input type="time" class="form-control input-sm xp-e" value="${esc(r.end_time)}"></td>
			<td><select class="form-control input-sm xp-v">${venue_opts(r.venue)}</select></td>
			<td><input type="number" class="form-control input-sm xp-c" value="${esc(r.seat_capacity)}" placeholder="${__('room')}"></td>
			<td><select class="form-control input-sm xp-f">${fac_opts(r.invigilator)}</select></td>
			<td class="xp-msg"></td></tr>`).join('');
		const cols = 9 + (o.failed ? 1 : 0);
		$el.html(`
			<div class="xp-table"><table class="table table-sm xp-tt"><thead><tr><th>${__('Course')}</th>${extra}<th>${o.students}</th><th>${__('Date')}</th><th>${__('Start')}</th><th>${__('End')}</th>
				<th>${__('Venue (seats)')}</th><th>${__('Seats')}</th><th>${__('Invigilator')}</th><th>${__('Check')}</th></tr></thead><tbody>${rows || `<tr><td colspan="${cols}">${o.empty}</td></tr>`}</tbody></table></div>
			<div class="xp-issues"></div>
			<div class="xp-bar">${can_add_inv ? `<button class="btn btn-default btn-sm xp-new-inv">+ ${__('Add invigilator')}</button>` : ''}
				<span class="xp-muted">${o.hint || __('Invigilators come from Faculty.')}</span>
				<span class="xp-grow"></span><button class="btn btn-default btn-sm xp-run-check">${__('Check')}</button>
				<button class="btn btn-primary btn-sm xp-save-tt" ${t.rows.length ? '' : 'disabled'}>${o.save_label || __('Save timetable')}</button></div>`);
		const collect = () => $el.find('tbody tr[data-course]').map((_, tr) => {
			const $tr = $(tr);
			return { course: $tr.data('course'), exam_date: $tr.find('.xp-d').val(), start_time: $tr.find('.xp-s').val(), end_time: $tr.find('.xp-e').val(),
				venue: $tr.find('.xp-v').val(), seat_capacity: $tr.find('.xp-c').val(), invigilator: $tr.find('.xp-f').val() };
		}).get();
		$el.find('.xp-v').on('change', (e) => {
			const v = t.venues.find((x) => x.name === $(e.target).val());
			$(e.target).closest('tr').find('.xp-c').val(v ? v.capacity : '');
		});
		const show = (res) => {
			$el.find('.xp-msg').html('');
			$el.find('tbody tr').removeClass('xp-flag');
			const items = [...res.errors.map((x) => ({ ...x, bad: 1 })), ...res.warnings];
			$el.find('tbody tr[data-course]').each((_, tr) => {
				if ($(tr).find('.xp-d').val()) $(tr).find('.xp-msg').html(`<span class="xp-pill ok">✓ ${__('OK')}</span>`);
			});
			items.forEach((x) => {
				const $tr = $el.find(`tbody tr[data-i="${x.row - 1}"]`);
				if ($tr.find('.xp-pill.ok').length) $tr.find('.xp-msg').html('');
				if (x.bad) $tr.addClass('xp-flag');
				$tr.find('.xp-msg').append(`<div class="xp-pill ${x.bad ? 'bad' : 'warn'}">${esc(x.message)}</div>`);
			});
			$el.find('.xp-issues').html(res.errors.length
				? `<div class="xp-alert bad">${__('{0} problem(s) to fix before saving.', [res.errors.length])}</div>`
				: `<div class="xp-alert ok">${__('No clashes.')}${res.warnings.length ? ' ' + __('{0} warning(s).', [res.warnings.length]) : ''}</div>`);
		};
		if (t.rows.some((r) => r.exam_date)) show(t.check);
		// A new invigilator is added to every row's list; the row it was picked from gets it selected
		const add_invigilator = ($select) => this.invigilator_dialog((f) => {
			t.faculty.push(f);
			$el.find('.xp-f').each((_, sel) => {
				$(sel).find('option[value="__new_invigilator__"]').before(`<option value="${esc(f.name)}">${esc(f.label)}</option>`);
			});
			if ($select) $select.val(f.name).data('prev', f.name);
		});
		$el.find('.xp-new-inv').on('click', () => add_invigilator());
		$el.find('.xp-f').each((_, sel) => { $(sel).data('prev', sel.value); });
		$el.find('.xp-f').on('change', (e) => {
			if (e.target.value !== '__new_invigilator__') { $(e.target).data('prev', e.target.value); return; }
			e.target.value = $(e.target).data('prev') || '';
			add_invigilator($(e.target));
		});
		$el.find('.xp-run-check').on('click', () => call(o.check, { exam_plan: this.plan, rows: JSON.stringify(collect()) }).then(show));
		$el.find('.xp-save-tt').on('click', () => call(o.save, { exam_plan: this.plan, rows: JSON.stringify(collect()) })
			.then(() => { frappe.show_alert({ message: o.saved, indicator: 'green' }); (o.after_save || (() => this.refresh()))(); }));
	}

	// Exam timetable as the classroom allocation sheet: a grey row per day, then
	// Sl. No. | Date | Venue | Year | Forenoon Session | ID Nos. From | To | Invigilator
	// | Date | the same for the Afternoon. Each line is one room (Exam Course Schedule row).
	allocation_sheet($el, t) {
		const SESS = ['Forenoon', 'Afternoon'];
		const DEF = { Forenoon: ['10:00', '13:00'], Afternoon: ['14:30', '17:30'] };
		const key = (v) => String(v || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
		let seq = 0;
		const lines = t.rows.map((r, i) => ({
			...r, _k: ++seq, _src: i,
			session: r.session || (r.exam_date ? (r.start_time && r.start_time >= '12:00' ? 'Afternoon' : 'Forenoon') : ''),
		}));
		const find = (k) => lines.find((l) => l._k === +k);
		// session times: the most used start / end of each session's lines
		const times = {};
		SESS.forEach((s) => {
			const own = lines.filter((l) => l.exam_date && l.session === s);
			const top = (fld) => {
				const c = {};
				own.forEach((l) => { if (l[fld]) c[l[fld]] = (c[l[fld]] || 0) + 1; });
				return Object.keys(c).sort((a, b) => c[b] - c[a])[0];
			};
			times[s] = [top('start_time') || DEF[s][0], top('end_time') || DEF[s][1]];
		});
		const course_name = {}, by_course = {}, by_venue = {};
		(t.courses || []).forEach((c) => { course_name[c.name] = c.course_name; });
		lines.forEach((l) => { if (l.course && l.course_name) course_name[l.course] = l.course_name; });
		Object.entries(course_name).forEach(([n, label]) => { by_course[label.toLowerCase()] = n; by_course[n.toLowerCase()] = n; });
		t.venues.forEach((v) => { by_venue[key(v.name)] = v; });
		const fac_label = (id) => (t.faculty.find((x) => String(x.name) === String(id)) || {}).label || id;
		const paper_of = (l) => l.paper || course_name[l.course] || l.course || '';
		const venue_of = (l) => l.venue || l.hall || '';
		const inv_of = (l) => (l.invigilator ? fac_label(l.invigilator) : l.invigilator_name || '');
		const uniq = (a) => [...new Set(a.filter(Boolean))].sort();
		const years = () => uniq([...lines.map((l) => l.programme_year), ...(t.programmes || [])]);
		const extra_days = new Set();
		const f = { day: '', session: '', venue: '', year: '', q: '' };
		let issues = {}, summary = null;

		$el.html(`
			<div class="xp-bar xp-tools">
				<button class="btn btn-default btn-sm xp-dl">${__('Download sheet')}</button>
				<button class="btn btn-default btn-sm xp-im">${__('Import sheet')}</button>
				<button class="btn btn-default btn-sm xp-log">${__('Import log')}</button>
				<button class="btn btn-default btn-sm xp-day-add">+ ${__('Exam day')}</button>
				<button class="btn btn-default btn-sm xp-clear-tt">${__('Clear timetable')}</button>
				${frappe.model.can_create('Faculty') ? `<button class="btn btn-default btn-sm xp-new-inv">+ ${__('Invigilator')}</button>` : ''}
				<span class="xp-grow"></span>
				<button class="btn btn-default btn-sm xp-run-check">${__('Check')}</button>
				<button class="btn btn-primary btn-sm xp-save-tt">${__('Save timetable')}</button>
			</div>
			<div class="xp-pub"></div>
			<div class="xp-bar xp-filters">
				<label>${__('Day')}<select class="form-control input-sm" data-f="day"></select></label>
				<label>${__('Session')}<select class="form-control input-sm" data-f="session"><option value="">${__('Both')}</option>${SESS.map((s) => `<option value="${s}">${__(s)}</option>`).join('')}</select></label>
				<label>${__('Venue')}<select class="form-control input-sm" data-f="venue"></select></label>
				<label>${__('Year')}<select class="form-control input-sm" data-f="year"></select></label>
				<label>${__('Course / paper')}<input class="form-control input-sm" data-f="q" placeholder="${__('Search')}"></label>
				<span class="xp-count-lines xp-muted"></span>
				<button class="btn btn-default btn-xs xp-clear-f">${__('Clear filters')}</button>
			</div>
			<div class="xp-unsched"></div>
			<div class="xp-sheet"></div>
			<div class="xp-issues"></div>`);
		this.publish_bar($el.find('.xp-pub'), t.published, false);

		// ── one styled dropdown for Venue / Year / Course / Invigilator cells ──
		$('.xp-pick').remove();
		const $pick = $('<div class="xp-pick"></div>').appendTo(document.body).hide();
		let pick_el = null, pick_items = [], pick_i = 0;
		const SOURCES = {
			venue: () => t.venues.map((v) => ({ value: v.name, hint: __('{0} seats', [v.capacity || 0]) })),
			programme_year: () => years().map((y) => ({ value: y })),
			paper: () => Object.entries(course_name).map(([n, label]) => ({ value: label, hint: n })),
			invigilator: () => t.faculty.map((x) => ({ value: x.label })),
		};
		const hide_pick = () => { $pick.hide(); pick_el = null; };
		const show_pick = (el, typed) => {
			const src = SOURCES[$(el).data('f')];
			if (!src) return hide_pick();
			const q = typed ? el.value.trim().toLowerCase() : '';
			pick_items = src().filter((x) => !q || `${x.value} ${x.hint || ''}`.toLowerCase().includes(q)).slice(0, 60);
			if (!pick_items.length) return hide_pick();
			pick_el = el;
			pick_i = Math.max(0, pick_items.findIndex((x) => x.value === el.value.trim()));
			const r = el.getBoundingClientRect();
			$pick.html(pick_items.map((x, i) => `<div class="xp-pick-i ${i === pick_i ? 'on' : ''}" data-i="${i}"><span>${esc(x.value)}</span>${x.hint ? `<small>${esc(x.hint)}</small>` : ''}</div>`).join(''))
				.css({ top: r.bottom + window.scrollY + 2, left: r.left + window.scrollX, minWidth: Math.max(r.width, 220) }).show();
		};
		const choose = (i) => {
			const el = pick_el, x = pick_items[i];
			if (!el || !x) return;
			el.value = x.value;
			hide_pick();
			$(el).trigger('change');
		};
		$pick.on('mousedown', '.xp-pick-i', (e) => { e.preventDefault(); choose(+$(e.currentTarget).data('i')); });
		$el.on('focus', '.xp-sheet .xp-in', (e) => show_pick(e.target, false));
		$el.on('input', '.xp-sheet .xp-in', (e) => show_pick(e.target, true));
		$el.on('blur', '.xp-sheet .xp-in', () => setTimeout(() => { if (!$(document.activeElement).is('.xp-in[data-f]')) hide_pick(); }, 120));
		$el.on('keydown', '.xp-sheet .xp-in', (e) => {
			const open = pick_el === e.target && $pick.is(':visible');
			if (open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
				e.preventDefault();
				pick_i = (pick_i + (e.key === 'ArrowDown' ? 1 : -1) + pick_items.length) % pick_items.length;
				$pick.find('.xp-pick-i').removeClass('on').eq(pick_i).addClass('on')[0].scrollIntoView({ block: 'nearest' });
			} else if (open && e.key === 'Enter') {
				e.preventDefault();
				choose(pick_i);
			} else if (e.key === 'Escape') {
				hide_pick();
			} else if (e.key === 'Enter' && ['venue', 'invigilator', 'programme_year'].includes($(e.target).data('f'))) {
				e.preventDefault();
				e.target.blur();
			}
		});

		const fill_filters = () => {
			const opt = (all, values, cur, label) => `<option value="">${all}</option>` + values.map((v) => `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(label ? label(v) : v)}</option>`).join('');
			$el.find('[data-f="day"]').html(opt(__('All days'), days(), f.day, (d) => moment(d).format('DD.MM.YYYY, ddd')));
			$el.find('[data-f="venue"]').html(opt(__('All venues'), uniq(lines.filter((l) => l.exam_date).map(venue_of)), f.venue));
			$el.find('[data-f="year"]').html(opt(__('All years'), uniq(lines.filter((l) => l.exam_date).map((l) => l.programme_year)), f.year));
		};
		const days = () => [...new Set([...lines.filter((l) => l.exam_date).map((l) => l.exam_date), ...extra_days])].sort();
		const match = (l) => (!f.venue || venue_of(l) === f.venue)
			&& (!f.year || l.programme_year === f.year)
			&& (!f.q || `${paper_of(l)} ${l.course || ''}`.toLowerCase().includes(f.q.toLowerCase()));
		const line_filter = () => f.venue || f.year || f.q;

		const cell_cls = (l) => ((issues[l._k] || []).some((x) => x.bad) ? 'xp-bad' : (issues[l._k] || []).length ? 'xp-warn' : '');
		const area = (l, fld, value, ph) => `<textarea class="xp-in" rows="1" data-k="${l._k}" data-f="${fld}" placeholder="${ph || ''}">${esc(value)}</textarea>`;
		const side = (l) => {
			const cls = cell_cls(l);
			const tag = l.course
				? `<span class="xp-ctag" title="${__('Linked course')}">${esc(course_name[l.course] || l.course)} · ${__('{0} students', [l.students || 0])}<button class="xp-unlink" data-k="${l._k}" title="${__('Unlink course')}">×</button></span>`
				: '';
			return `<td class="${cls} ${l.hall && !l.venue ? 'xp-txt' : ''}" title="${l.hall && !l.venue ? esc(__('Not a Venue Master room: not checked for clashes or seats')) : ''}">${area(l, 'venue', venue_of(l))}</td>
				<td class="${cls}">${area(l, 'programme_year', l.programme_year)}</td>
				<td class="${cls} xp-paper-c ${!l.course && paper_of(l) ? 'xp-txt' : ''}" title="${!l.course && paper_of(l) ? esc(__('Not a Course: kept as text. Pick a course from the list to link it.')) : ''}">
					${area(l, 'paper', paper_of(l), __('Course / paper'))}
					${tag ? `<div class="xp-sub">${tag}</div>` : ''}<span class="xp-ln-act"><button class="xp-dup" data-k="${l._k}" title="${__('Another room for this paper')}">+ ${__('Room')}</button><button class="xp-del" data-k="${l._k}" title="${__('Remove')}">×</button></span></td>
				<td class="${cls}">${area(l, 'id_from', l.id_from, __('All students'))}</td>
				<td class="${cls}">${area(l, 'id_to', l.id_to)}</td>
				<td class="${cls} ${l.invigilator_name && !l.invigilator ? 'xp-txt' : ''}">${area(l, 'invigilator', inv_of(l))}</td>`;
		};

		const draw = () => {
			hide_pick();
			fill_filters();
			const all_days = days();
			const sides = f.session ? [f.session] : SESS;
			const N = 2 + sides.length * 6 + (sides.length - 1);
			const head = sides.map((s, j) => `${j ? `<th>${__('Date')}</th>` : ''}<th>${__('Venue')}</th><th>${__('Year')}</th>
				<th class="xp-sess">${__(s + ' Session')}<span><input type="time" class="xp-st" data-s="${s}" data-j="0" value="${times[s][0]}"> – <input type="time" class="xp-st" data-s="${s}" data-j="1" value="${times[s][1]}"></span></th>
				<th>${__('ID Nos.')}<br>${__('From')}</th><th>${__('ID Nos.')}<br>${__('To')}</th><th>${__('Invigilator')}</th>`).join('');
			const cols = sides.map((s, j) => `${j ? '<col style="width:100px">' : ''}<col style="width:150px"><col style="width:150px"><col style="width:260px"><col style="width:105px"><col style="width:105px"><col style="width:150px">`).join('');
			let body = '', shown = 0, total = 0;
			all_days.forEach((d, n) => {
				const per = sides.map((s) => lines.filter((l) => l.exam_date === d && l.session === s));
				total += per.reduce((a, p) => a + p.length, 0);
				if (f.day && d !== f.day) return;
				const vis = per.map((p) => p.filter(match));
				if (line_filter() && !vis.some((p) => p.length)) return;
				shown += vis.reduce((a, p) => a + p.length, 0);
				const k = Math.max(1, ...vis.map((p) => p.length));
				const date_cell = `<td class="xp-dt" rowspan="${k}">${moment(d).format('DD.MM.YYYY')}<br>${moment(d).format('dddd')}</td>`;
				body += `<tr class="xp-day"><td colspan="${N}"><div class="xp-day-in"><b>${moment(d).format('dddd, Do MMMM YYYY')}</b>
					${sides.map((s) => `<button class="btn btn-default btn-xs xp-add" data-d="${d}" data-s="${s}">+ ${__('{0} line', [__(s)])}</button>`).join('')}
					<button class="btn btn-default btn-xs xp-day-del" data-d="${d}">${__('Remove day')}</button></div></td></tr>`;
				for (let i = 0; i < k; i++) {
					body += '<tr>' + (i ? '' : `<td class="xp-sl" rowspan="${k}">${n + 1}</td>${date_cell}`);
					vis.forEach((p, j) => {
						if (j && !i) body += date_cell;
						if (p[i]) body += side(p[i]);
						else if (i === p.length) body += `<td class="xp-blank" colspan="6" rowspan="${k - i}">${p.length ? '' : `<span class="xp-muted">${__('No {0} papers', [__(sides[j]).toLowerCase()])}</span>`}</td>`;
					});
					body += '</tr>';
				}
			});
			$el.find('.xp-sheet').html(`<table><colgroup><col style="width:50px"><col style="width:100px">${cols}</colgroup>
				<thead><tr><th class="xp-sl">${__('Sl. No.')}</th><th class="xp-dt">${__('Date')}</th>${head}</tr></thead>
				<tbody>${body || `<tr><td colspan="${N}" class="xp-none">${all_days.length ? __('Nothing matches the filters.') : __('No exam days yet. Add an exam day, or import the sheet.')}</td></tr>`}</tbody></table>`);
			const filtered = f.day || f.session || line_filter();
			$el.find('.xp-count-lines').text(filtered ? __('Showing {0} of {1} lines', [shown, total]) : __('{0} lines', [total]));
			$el.find('.xp-clear-f').toggle(!!filtered);

			const todo = lines.filter((l) => !l.exam_date && (l.course || l.paper));
			$el.find('.xp-unsched').html(todo.length ? `<div class="xp-soft"><span class="xp-muted">${__('Not in the timetable yet')}:</span>
				${todo.map((l) => `<button class="btn btn-default btn-xs xp-place" data-k="${l._k}">${esc(paper_of(l))} +</button>`).join(' ')}</div>` : '');

			const list = lines.flatMap((l) => (issues[l._k] || []).map((x) => ({ ...x, l })));
			$el.find('.xp-issues').html(summary === null ? '' : list.length
				? `<div class="xp-alert ${summary ? 'bad' : 'ok'}">${summary ? __('{0} problem(s) to fix before saving.', [summary]) : __('No clashes.')}
					<ul>${list.map((x) => `<li class="${x.bad ? 'bad' : ''}">${moment(x.l.exam_date).format('DD.MM.YYYY')} · ${__(x.l.session)} · ${esc(venue_of(x.l))} · <b>${esc(paper_of(x.l))}</b>: ${esc(x.message)}</li>`).join('')}</ul></div>`
				: `<div class="xp-alert ok">${__('No clashes.')}</div>`);
		};

		// rows in sheet order (date, Forenoon before Afternoon), with the session times
		const payload = () => {
			const order = [...lines].sort((a, b) => (a.exam_date ? 0 : 1) - (b.exam_date ? 0 : 1)
				|| String(a.exam_date || '').localeCompare(String(b.exam_date || ''))
				|| SESS.indexOf(a.session) - SESS.indexOf(b.session) || lines.indexOf(a) - lines.indexOf(b));
			return { order, rows: order.map((l) => ({
				course: l.course || '', paper: l.paper || '', programme_year: l.programme_year || '',
				exam_date: l.exam_date || '', session: l.exam_date ? l.session : '',
				start_time: l.exam_date ? times[l.session][0] : '', end_time: l.exam_date ? times[l.session][1] : '',
				venue: l.venue || '', hall: l.hall || '', seat_capacity: l.seat_capacity || '',
				invigilator: l.invigilator || '', invigilator_name: l.invigilator_name || '',
				id_from: l.id_from || '', id_to: l.id_to || '',
			})) };
		};
		const take_check = (res, line_of) => {
			issues = {};
			[...res.errors.map((x) => ({ ...x, bad: 1 })), ...res.warnings].forEach((x) => {
				const l = line_of(x.row - 1);
				if (l) (issues[l._k] = issues[l._k] || []).push(x);
			});
			summary = res.errors.length;
		};
		if (t.rows.some((r) => r.exam_date)) take_check(t.check, (i) => lines.find((l) => l._src === i));

		$el.on('change', '.xp-sheet .xp-in', (e) => {
			const l = find($(e.target).data('k')), fld = $(e.target).data('f'), v = e.target.value.trim();
			if (!l) return;
			if (fld === 'paper') {
				// a course's name links the course; other text keeps the current link
				const c = by_course[v.toLowerCase()];
				if (c) l.course = c;
				if (!v) l.course = '';
				l.paper = l.course && course_name[l.course] === v ? '' : v;
			} else if (fld === 'venue') {
				const m = by_venue[key(v)];
				Object.assign(l, { venue: m ? m.name : '', hall: m ? '' : v, seat_capacity: m ? m.capacity : '' });
			} else if (fld === 'invigilator') {
				const x = t.faculty.find((y) => y.label.toLowerCase() === v.toLowerCase() || String(y.name) === v);
				Object.assign(l, { invigilator: x ? x.name : '', invigilator_name: x ? '' : v });
			} else {
				l[fld] = v;
			}
			if (['paper', 'venue', 'invigilator'].includes(fld)) draw();
		});
		$el.on('click', '.xp-unlink', (e) => {
			const l = find($(e.currentTarget).data('k'));
			l.paper = paper_of(l);
			l.course = '';
			draw();
		});
		$el.on('change', '.xp-st', (e) => { times[$(e.target).data('s')][+$(e.target).data('j')] = e.target.value; });
		$el.on('change input', '.xp-filters [data-f]', (e) => {
			const fld = $(e.target).data('f');
			if (f[fld] === e.target.value) return;
			f[fld] = e.target.value;
			draw();
		});
		$el.find('.xp-clear-f').on('click', () => {
			Object.keys(f).forEach((x) => { f[x] = ''; });
			$el.find('.xp-filters [data-f]').val('');
			draw();
		});
		const new_line = (d, s, from) => ({ _k: ++seq, course: '', paper: '', programme_year: '', venue: '', hall: '', id_from: '', id_to: '',
			invigilator: '', invigilator_name: '', seat_capacity: '', students: 0, ...(from || {}), exam_date: d, session: s });
		$el.on('click', '.xp-add', (e) => {
			const l = new_line($(e.currentTarget).data('d'), $(e.currentTarget).data('s'));
			lines.push(l);
			Object.assign(f, { venue: '', year: '', q: '' });   // so the new line shows
			$el.find('.xp-filters input[data-f]').val('');
			draw();
			$el.find(`.xp-in[data-k="${l._k}"][data-f="venue"]`).trigger('focus');
		});
		$el.on('click', '.xp-dup', (e) => {
			const src = find($(e.currentTarget).data('k'));
			const l = new_line(src.exam_date, src.session, { course: src.course, paper: src.paper, programme_year: src.programme_year });
			lines.splice(lines.indexOf(src) + 1, 0, l);
			draw();
			$el.find(`.xp-in[data-k="${l._k}"][data-f="venue"]`).trigger('focus');
		});
		$el.on('click', '.xp-del', (e) => {
			const l = find($(e.currentTarget).data('k'));
			// a course's last line goes back to "Not in the timetable yet"
			if (l.course && !lines.some((x) => x !== l && x.course === l.course)) l.exam_date = '';
			else lines.splice(lines.indexOf(l), 1);
			delete issues[l._k];
			draw();
		});
		// Lines leave the timetable; a course keeps one undated line ("Not in the timetable yet")
		const unschedule = (gone) => {
			const left = lines.filter((l) => !gone.includes(l));
			gone.forEach((l) => {
				if (l.course && !left.some((x) => x.course === l.course)) {
					Object.assign(l, { exam_date: '', session: '' });
					left.push(l);
				}
				delete issues[l._k];
			});
			lines.splice(0, lines.length, ...lines.filter((l) => left.includes(l)));
		};
		$el.on('click', '.xp-day-del', (e) => {
			const d = $(e.currentTarget).data('d');
			const gone = lines.filter((l) => l.exam_date === d);
			const go = () => { unschedule(gone); extra_days.delete(d); draw(); };
			if (!gone.length) return go();
			frappe.confirm(__('Remove {0} and its {1} line(s)? Its courses go back to "Not in the timetable yet". Click Save timetable to keep the change.',
				[moment(d).format('DD.MM.YYYY'), gone.length]), go);
		});
		$el.find('.xp-clear-tt').on('click', () => frappe.confirm(
			__('Clear the whole exam timetable? Every line is removed and the courses go back to "Not in the timetable yet". Nothing is saved until you click Save timetable.'),
			() => { unschedule(lines.filter((l) => l.exam_date)); extra_days.clear(); summary = null; draw(); }));
		$el.on('click', '.xp-place', (e) => {
			const l = find($(e.currentTarget).data('k'));
			frappe.prompt([
				{ fieldname: 'exam_date', fieldtype: 'Date', label: __('Date'), reqd: 1, default: days()[0] },
				{ fieldname: 'session', fieldtype: 'Select', label: __('Session'), options: SESS.join('\n'), default: 'Forenoon' },
			], (v) => { Object.assign(l, v); draw(); }, __('Add {0} to the timetable', [paper_of(l)]), __('Add'));
		});
		$el.find('.xp-day-add').on('click', () => frappe.prompt(
			[{ fieldname: 'd', fieldtype: 'Date', label: __('Exam day'), reqd: 1 }],
			(v) => { extra_days.add(v.d); draw(); }, __('Add exam day'), __('Add')));
		$el.find('.xp-new-inv').on('click', () => this.invigilator_dialog((x) => { t.faculty.push(x); }));
		$el.find('.xp-dl').on('click', () => this.download('download_timetable'));
		$el.find('.xp-im').on('click', () => this.import_timetable_dialog());
		$el.find('.xp-log').on('click', () => this.open_import_log('Exam Timetable'));
		$el.find('.xp-sheet').on('scroll', hide_pick);
		$el.find('.xp-run-check').on('click', () => {
			const p = payload();
			call('check_timetable', { exam_plan: this.plan, rows: JSON.stringify(p.rows) }).then((res) => {
				p.order.forEach((l, i) => { l.students = res.students[i]; });
				take_check(res, (i) => p.order[i]);
				draw();
			});
		});
		$el.find('.xp-save-tt').on('click', () => call('save_timetable', { exam_plan: this.plan, rows: JSON.stringify(payload().rows) })
			.then(() => { frappe.show_alert({ message: __('Timetable saved'), indicator: 'green' }); this.refresh(); }));
		draw();
	}

	// Continuing Evaluation Schedule, as the sheet: Subject | Evaluation n/Assessment n, Marks, Date | SGD | remarks
	render_evaluation_schedule($el, t) {
		call('get_assessment_grid', { exam_plan: this.plan }).then((data) => {
			const lines = data.map((l) => ({ ...l, evaluations: l.evaluations.map((e) => ({ ...e })) }));
			let groups = Math.max(4, ...lines.map((l) => l.evaluations.length));
			const f = { q: '', programme: '' };
			const programmes = [...new Set(lines.flatMap((l) => l.programmes || []))].sort();
			$el.html(`
				<div class="xp-bar xp-tools">
					<button class="btn btn-default btn-sm xp-dl">${__('Download sheet')}</button>
					<button class="btn btn-default btn-sm xp-dl-blank">${__('Download blank sheet')}</button>
					<button class="btn btn-default btn-sm xp-im">${__('Import sheet')}</button>
					<button class="btn btn-default btn-sm xp-log">${__('Import log')}</button>
					<button class="btn btn-default btn-sm xp-ce-add">+ ${__('Evaluation column')}</button>
					<span class="xp-grow"></span>
					<button class="btn btn-primary btn-sm xp-ce-save" ${lines.length ? '' : 'disabled'}>${__('Save evaluation schedule')}</button>
				</div>
				<div class="xp-bar xp-filters">
					<input class="form-control input-sm" data-f="q" placeholder="${__('Search subject')}">
					<select class="form-control input-sm" data-f="programme"><option value="">${__('All programmes')}</option>${programmes.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`).join('')}</select>
					<span class="xp-muted">${t.assessment_schedules.length ? __('Saved in') + ': ' + t.assessment_schedules.map((a) => `<a href="/desk/exam-assessment-schedule/${encodeURIComponent(a.name)}">${esc(a.name)}</a> (${esc(a.programme)})`).join(', ') : ''}</span>
				</div>
				<div class="xp-sheet xp-ce-sheet"></div>`);
			const area = (i, n, fld, v) => `<textarea class="xp-in" rows="2" data-i="${i}" data-n="${n}" data-f="${fld}">${esc(v)}</textarea>`;
			const draw = () => {
				const heads = Array.from({ length: groups }, (_, n) => `<th>${__('Evaluation {0}/Assessment {0}', [n + 1])}</th><th>${__('Marks')}</th><th>${__('Date')}</th>`).join('');
				const cols = Array.from({ length: groups }, () => '<col style="width:230px"><col style="width:95px"><col style="width:140px">').join('');
				const shown = lines.map((l, i) => ({ l, i })).filter(({ l }) => (!f.q || l.course_name.toLowerCase().includes(f.q.toLowerCase()))
					&& (!f.programme || (l.programmes || []).includes(f.programme)));
				$el.find('.xp-ce-sheet').html(`<table><colgroup><col style="width:180px">${cols}<col style="width:300px"><col style="width:200px"></colgroup>
					<thead><tr><th>${__('Subject')}</th>${heads}<th>${__('SGD')}</th><th></th></tr></thead><tbody>
					${shown.map(({ l, i }) => `<tr><td class="xp-subj"><b>${esc(l.course_name)}</b><small>${l.suggested ? __('From the Evaluation Schema, not saved yet') : esc((l.programmes || []).join(', '))}</small></td>
						${Array.from({ length: groups }, (_, n) => { const e = l.evaluations[n] || {}; return `<td>${area(i, n, 'label', e.label)}</td><td>${area(i, n, 'marks', e.marks)}</td><td>${area(i, n, 'date', e.date)}</td>`; }).join('')}
						<td>${area(i, '', 'sgd', l.sgd)}</td><td>${area(i, '', 'remarks', l.remarks)}</td></tr>`).join('')
						|| `<tr><td colspan="${groups * 3 + 3}" class="xp-none">${lines.length ? __('Nothing matches the filters.') : __('Map courses first, or import the sheet.')}</td></tr>`}
					</tbody></table>`);
			};
			$el.on('input', '.xp-ce-sheet .xp-in', (e) => {
				const d = $(e.target).data(), l = lines[d.i];
				if (d.n === '') { l[d.f] = e.target.value; return; }
				l.evaluations[d.n] = l.evaluations[d.n] || { label: '', marks: '', date: '' };
				l.evaluations[d.n][d.f] = e.target.value;
			});
			$el.on('change input', '.xp-filters [data-f]', (e) => { f[$(e.target).data('f')] = e.target.value; draw(); });
			$el.find('.xp-ce-add').on('click', () => { groups += 1; draw(); });
			$el.find('.xp-dl').on('click', () => this.download('download_assessment_sheet'));
			$el.find('.xp-dl-blank').on('click', () => this.download('download_assessment_sheet', { blank: 1 }));
			$el.find('.xp-im').on('click', () => this.import_evaluation_dialog());
			$el.find('.xp-log').on('click', () => this.open_import_log('Continuing Evaluation Schedule'));
			$el.find('.xp-ce-save').on('click', () => {
				const out = lines.map((l) => ({ course: l.course, sgd: l.sgd, remarks: l.remarks,
					evaluations: Array.from(l.evaluations).filter((e) => e && (e.label || '').trim()) }));
				call('save_assessment_grid', { exam_plan: this.plan, lines: JSON.stringify(out) }).then((r) => {
					frappe.show_alert({ message: __('Evaluation schedule saved for {0} course(s)', [r.courses]), indicator: 'green' });
					if (r.warnings.length) frappe.msgprint({ title: __('Saved, please note'), message: r.warnings.map(esc).join('<br>'), indicator: 'orange' });
					this.render();
				});
			});
			draw();
		});
	}

	import_evaluation_dialog() {
		this.sheet_import_dialog({
			title: __('Import Continuing Evaluation Schedule'), method: 'import_assessment_sheet', sheet: 'evaluation',
			help: __('The evaluation schedule sheet (same format as Download sheet). Each Subject is matched to a Course by name or code; pick the course for any that are not. The sheet\'s courses replace their evaluations; other courses are not touched.'),
			args: (d) => {
				const mapping = {};
				d.$wrapper.find('.xp-map-subject').each((_, sel) => { if (sel.value) mapping[$(sel).data('subject')] = sel.value; });
				return { mapping: JSON.stringify(mapping) };
			},
			apply_label: (r) => (!r.lines ? null : r.unmatched.length
				? __('Import matched subjects, skip the rest') : __('Save evaluation schedule')),
			preview: (r) => `<div class="xp-alert ${r.unmatched.length ? 'bad' : 'ok'}">${__('{0} subject(s): {1} matched to a course.', [r.lines, r.matched])}
				${r.unmatched.length ? ' ' + __('Pick the course for the others below; left empty, they are skipped.') : ''}</div>
				${r.unmatched.length ? `<div class="xp-bar" style="margin-top:8px"><span class="xp-grow"></span><button class="btn btn-default btn-xs xp-dl-issues">${__('Download problems')}</button></div>
				<div class="xp-table" style="margin-top:6px"><table class="table table-sm"><thead><tr><th>${__('Sheet row')}</th><th>${__('Subject')}</th><th>${__('Course')}</th></tr></thead><tbody>
				${r.unmatched.map((x) => `<tr><td class="num">${x.sheet_row}</td><td>${esc(x.subject)}</td><td><select class="form-control input-sm xp-map-subject" data-subject="${esc(x.subject)}">
					<option value=""></option>${r.courses.map((c) => `<option value="${esc(c.name)}">${esc(c.course_name)} (${esc(c.name)})</option>`).join('')}</select></td></tr>`).join('')}
				</tbody></table></div>` : ''}`,
			done: (r) => {
				if (r.warnings.length) frappe.msgprint({ title: __('Imported, please note'), message: r.warnings.map(esc).join('<br>'), indicator: 'orange' });
				this.render();
			},
		});
	}

	// Re-exam sittings, above the Re Exam screen in step 5
	render_reexam_timetable($el) {
		call('get_reexam_timetable', { exam_plan: this.plan }).then((t) => {
			$el.html(`<div class="xp-card-head"><div><h4>${__('Re-exam timetable')}</h4>
				<p>${__('Date, time, room and invigilator for each re-exam. Same checks as the exam timetable (except term dates); seats and clashes count the students registered for the re-exam.')}</p></div></div>`);
			this.publish_bar($el, t.published, true);
			this.tt_editor($('<div></div>').appendTo($el), t, {
				check: 'check_reexam_timetable', save: 'save_reexam_timetable', saved: __('Re-exam timetable saved'),
				students: __('Registered'), failed: true, save_label: __('Save re-exam timetable'),
				hint: __('Only rows with a date are saved.'),
				empty: __('No course needs a re-exam yet: no failed students, re-exam windows or registrations.'),
				after_save: () => this.render_reexam_timetable($el),
			});
		});
	}

	// New Faculty record from the timetable, without leaving the page
	invigilator_dialog(done) {
		const d = new frappe.ui.Dialog({
			title: __('Add invigilator'),
			fields: [
				{ fieldtype: 'HTML', options: `<p class="text-muted small">${__('Invigilators are Faculty records. This adds the person to Faculty and to the invigilator list.')}</p>` },
				{ fieldname: 'first_name', label: __('First Name'), fieldtype: 'Data', reqd: 1 },
				{ fieldname: 'last_name', label: __('Last Name'), fieldtype: 'Data' },
				{ fieldname: 'faculty_id', label: __('Faculty ID'), fieldtype: 'Data', reqd: 1, description: __('Must be unique') },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'email', label: __('Email'), fieldtype: 'Data', options: 'Email', reqd: 1 },
				{ fieldname: 'phone', label: __('Phone'), fieldtype: 'Data', options: 'Phone' },
				{ fieldname: 'designation', label: __('Designation'), fieldtype: 'Link', options: 'SLCM Designation' },
				{ fieldtype: 'Section Break' },
				{ fieldname: 'photo', label: __('Photo'), fieldtype: 'Attach Image', reqd: 1 },
			],
			primary_action_label: __('Add invigilator'),
			primary_action: (v) => {
				frappe.db.insert({ doctype: 'Faculty', status: 'Active', ...v }).then((doc) => {
					d.hide();
					const label = [doc.first_name, doc.last_name].filter(Boolean).join(' ') || doc.name;
					frappe.show_alert({ message: __('{0} added. Pick them for a course, then Save timetable.', [label]), indicator: 'green' }, 6);
					done({ name: doc.name, label });
				});
			},
		});
		d.show();
	}

	// ── 3. Students & marks ────────────────────────────────────────────
	render_courses() {
		if (this.course) return this.render_course_view();
		Promise.all([call('get_students', { exam_plan: this.plan }), call('get_marks_progress', { exam_plan: this.plan })]).then(([students, marks]) => {
			const by = {};
			students.forEach((r) => { by[r.course] = Object.assign({ course: r.course }, r); });
			marks.forEach((r) => { by[r.course] = Object.assign(by[r.course] || { course: r.course, in_classes: 0, synced: 0, detained: 0, manual: 0, barcodes: 0 }, { mk: r }); });
			const rows = Object.values(by).sort((a, b) => a.course.localeCompare(b.course));
			this.course_list = rows.map((r) => r.course);
			const status = (r) => {
				const m = r.mk || {}, n = m.students || r.synced || 0;
				if (!n) return ['bad', __('No students')];
				if (m.locked >= n) return ['ok', __('Locked')];
				if ((m.submitted || 0) + (m.locked || 0) >= n) return ['ok', __('Submitted')];
				if (m.entered >= n) return ['info', __('Marks entered')];
				if (m.entered) return ['warn', __('In progress')];
				return ['', __('Not started')];
			};
			const t = rows.reduce((a, r) => {
				a.students += r.synced; a.classes += r.in_classes; a.detained += r.detained; a.barcodes += r.barcodes;
				a.entered += (r.mk && r.mk.entered) || 0; a.marks += (r.mk && r.mk.students) || 0; return a;
			}, { students: 0, classes: 0, detained: 0, barcodes: 0, entered: 0, marks: 0 });

			this.$body.html(this.card(__('Students & marks'),
				__('One row per course. Students come from Classes on their own: saving a Class adds its enrolled students here and removes students who left (if they have no marks yet). Open a course to enter or import marks, and lock it.'), ''));
			const $c = this.$body.find('.xp-card-body');
			$c.html(`
				<div class="xp-kpis">
					<div><b>${t.students}</b><span>${__('students in the plan')}${t.classes > t.students ? ` · ${__('{0} still to add', [t.classes - t.students])}` : ''}</span></div>
					<div><b>${t.detained}</b><span>${__('detained (attendance)')}</span></div>
					<div><b>${t.barcodes}</b><span>${__('barcodes')}</span></div>
					<div><b>${t.entered} / ${t.marks}</b><span>${__('marks entered')}</span></div>
				</div>
				<div class="xp-bar">
					<!-- Students added to Classes now reach the plan automatically (Classes save / course mapping)
					<button class="btn btn-primary btn-sm xp-sync">${__('Add students from Classes')}</button> -->
					<button class="btn btn-default btn-sm xp-elig">${__('Update eligibility')}</button>
					<button class="btn btn-default btn-sm xp-acc">${__('Marks entry access')}</button>
					<span class="xp-grow"></span>
					<button class="btn btn-default btn-sm xp-bc">${__('Generate barcodes…')}</button>
					<button class="btn btn-default btn-sm xp-bc-dl">${__('Download barcode sheet')}</button>
				</div>
				<div class="xp-table"><table class="table table-sm xp-ct"><thead><tr>
					<th>${__('Course')}</th><th class="num">${__('Students')}</th><th class="num">${__('Detained')}</th><th class="num">${__('Barcodes')}</th>
					<th>${__('Marks entered')}</th><th>${__('Evaluators')}</th><th>${__('Status')}</th><th></th></tr></thead><tbody>
				${rows.map((r) => {
					const m = r.mk || {}, n = m.students || 0, pct = n ? Math.round((m.entered || 0) * 100 / n) : 0, [cls, label] = status(r);
					const missing = r.in_classes - r.synced;
					return `<tr class="xp-crow" data-course="${esc(r.course)}">
						<td><b>${esc(r.course)}</b>${missing > 0 ? `<br><small class="xp-warn-text">${__('{0} not added yet', [missing])}</small>` : ''}</td>
						<td class="num">${r.synced}${r.in_classes && r.in_classes !== r.synced ? ` <small>/ ${r.in_classes}</small>` : ''}</td>
						<td class="num">${r.detained ? `<span class="xp-pill bad">${r.detained}</span>` : 0}</td>
						<td class="num">${r.barcodes}${r.synced && r.barcodes < r.synced ? ` <small>/ ${r.synced}</small>` : ''}</td>
						<td><div class="xp-mk"><div class="xp-meter"><i style="width:${pct}%"></i></div><small>${m.entered || 0} / ${n}</small></div></td>
						<td><small>${esc((m.evaluators || []).join(', ') || '—')}</small></td>
						<td><span class="xp-pill ${cls}">${label}</span></td>
						<td class="act"><button class="btn btn-default btn-sm xp-open">${__('Open')} ›</button></td></tr>`;
				}).join('') || `<tr><td colspan="8">${__('Map courses in step 1 first.')}</td></tr>`}
				</tbody></table></div>`);

			const open = (course) => { this.course = course; this.render_course_view(); };
			$c.find('.xp-crow').on('click', (e) => open($(e.currentTarget).data('course')));
			// Add students from Classes: now automatic, see Classes.add_students_to_exam_plans
			// $c.find('.xp-sync').on('click', () => call('sync_all_students', { exam_plan: this.plan }).then((r) => {
			// 	frappe.msgprint(__('{0} added, {1} already in the plan.', [r.added, r.skipped]) + (r.errors.length ? '<br><br>' + r.errors.map(esc).join('<br>') : ''));
			// 	this.refresh();
			// }));
			$c.find('.xp-elig').on('click', () => call('update_eligibility', { exam_plan: this.plan }).then((r) => {
				frappe.msgprint(__('{0} detained, {1} cleared, {2} without attendance yet.', [r.detained, r.cleared, r.no_attendance_yet]));
				this.refresh();
			}));
			$c.find('.xp-acc').on('click', () => this.access_screen(rows.length));
			$c.find('.xp-bc').on('click', () => {
				const missing = rows.reduce((a, r) => a + Math.max(0, r.synced - r.barcodes), 0);
				frappe.prompt({ fieldname: 'copies', fieldtype: 'Int', label: __('Copies of each barcode on the sheet'), default: 1, reqd: 1,
					description: missing ? __('{0} student(s) have no barcode yet and will get one. Existing barcodes never change.', [missing])
						: __('Every student already has a barcode. This only changes how many copies are printed.') },
				(v) => call('generate_barcodes', { exam_plan: this.plan, copies: v.copies }).then((r) => {
					frappe.show_alert({ message: missing ? (r.message || __('Barcodes generated')) : __('Copies updated'), indicator: 'green' });
					this.refresh();
				}), __('Generate barcodes'), __('Generate'));
			});
			$c.find('.xp-bc-dl').on('click', () => frappe.prompt({ fieldname: 'mode', fieldtype: 'Select', label: __('One sheet per'), reqd: 1, default: 'by_date',
				options: [{ value: 'by_date', label: __('Exam date') }, { value: 'by_course', label: __('Course') }] },
				(v) => this.download_barcodes(v.mode), __('Download barcode sheet'), __('Download')));
		});
	}

	download_barcodes(mode, course) {
		frappe.call({ method: 'slcm.slcm.page.exam_barcode_sheet.exam_barcode_sheet.export_attendance_excel', freeze: true,
			args: { exam_plan: this.plan, course: course || '', mode, selected_courses: mode === 'by_course' && !course ? JSON.stringify(this.course_list || []) : '' } })
			.then((r) => {
				if (!r.message) return;
				const a = document.createElement('a');
				a.href = 'data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,' + r.message.file_content;
				a.download = r.message.filename;
				document.body.appendChild(a); a.click(); a.remove();
			});
	}

	// One course of step 3: the Course Results screen, inside the planner
	render_course_view() {
		const list = this.course_list || [], i = list.indexOf(this.course);
		this.$body.html(`<div class="xp-card xp-course">
			<div class="xp-course-head">
				<button class="btn btn-default btn-sm xp-back">‹ ${__('All courses')}</button>
				<h4>${esc(this.course)}</h4>
				<span class="xp-grow"></span>
				<button class="btn btn-default btn-sm xp-bc-one">${__('Barcode sheet')}</button>
				${list.length > 1 ? `<button class="btn btn-default btn-sm xp-prev-course" ${i > 0 ? '' : 'disabled'}>‹ ${__('Previous')}</button>
				<span class="xp-muted">${__('{0} of {1}', [i + 1, list.length])}</span>
				<button class="btn btn-default btn-sm xp-next-course" ${i >= 0 && i < list.length - 1 ? '' : 'disabled'}>${__('Next')} ›</button>` : ''}
			</div>
			<div class="xp-mount"></div></div>`);
		const go = (course) => { this.course = course; this.render_course_view(); };
		this.$body.find('.xp-back').on('click', () => { this.course = null; this.refresh(); });
		this.$body.find('.xp-prev-course').on('click', () => go(list[i - 1]));
		this.$body.find('.xp-next-course').on('click', () => go(list[i + 1]));
		this.$body.find('.xp-bc-one').on('click', () => this.download_barcodes('by_course', this.course));
		this.mount('course_results', this.$body.find('.xp-mount')[0], { course: this.course });
	}

	// Marks entry access per course: who may view / edit marks (evaluators) and until when.
	// This is Result Settings' Access screen; the quick form below sets every course at once.
	access_screen(n) {
		const d = new frappe.ui.Dialog({ title: __('Marks entry access'), size: 'extra-large' });
		d.$wrapper.addClass('er-theme');
		$(d.body).html(`<div class="xp-bar" style="margin-bottom:10px"><span class="xp-muted">${__('Per course: who can view or edit marks, until when, and which evaluators. Use Configure on a row to pick evaluators.')}</span>
			<span class="xp-grow"></span><button class="btn btn-default btn-sm xp-acc-all">${__('Same settings for all courses…')}</button></div><div class="xp-acc-mount"></div>`);
		let screen = null;
		const load = () => {
			if (screen) screen.destroy();
			EXAM_UI('result_settings').then((fn) => {
				screen = fn($(d.body).find('.xp-acc-mount')[0], { embedded: true, exam_plan: this.plan, subtab: 'access_results', only_subtab: true });
			});
		};
		$(d.body).find('.xp-acc-all').on('click', () => this.access_dialog(n, load));
		d.onhide = () => { if (screen) screen.destroy(); this.refresh(); };
		d.show();
		load();
	}

	// Same marks entry access for every course of the plan
	access_dialog(n, after) {
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
		const d = new frappe.ui.Dialog({
			title: __('Marks entry access for all {0} courses', [n]),
			size: 'large',
			fields: [{ fieldtype: 'HTML', options: `<p class="text-muted small">${__("Faculty of each course's Classes become its evaluators. To change one course only, open it and use its access settings.")}</p>` }, ...fields],
			primary_action_label: __('Apply to every course'),
			primary_action: (v) => {
				const settings = {};
				fields.filter((f) => f.fieldtype === 'Check' || f.fieldtype === 'Datetime').forEach((f) => { settings[f.fieldname] = f.fieldtype === 'Check' ? (v[f.fieldname] ? 1 : 0) : (v[f.fieldname] || null); });
				call('apply_access', { exam_plan: this.plan, settings: JSON.stringify(settings) }).then((k) => {
					d.hide();
					frappe.show_alert({ message: __('Access saved for {0} courses', [k]), indicator: 'green' });
					if (after) after(); else this.refresh();
				});
			},
		});
		d.show();
	}

	// ── 4. Results & publish ───────────────────────────────────────────
	render_results() {
		call('get_results', { exam_plan: this.plan }).then((r) => {
			const total = r.marks.Draft + r.marks.Submitted + r.marks.Locked;
			const TABS = [
				['term', __('Term results'), 'term_results'],
				['publish', __('Publish'), 'publish_results'],
				['settings', __('What students see'), 'result_settings'],
			];
			this.results_tab = this.results_tab || 'term';
			this.$body.html(this.card(__('Results & publish'), __('Five steps, left to right. The tabs below show each student\'s term result, who is published, and what students see.'), '')
				+ `<div class="xp-card xp-rtabs-card"><div class="xp-rtabs">${TABS.map(([k, l]) => `<button class="xp-rtab ${k === this.results_tab ? 'on' : ''}" data-tab="${k}">${l}</button>`).join('')}</div>
				<div class="xp-mount"></div></div>`);
			const $c = this.$body.find('.xp-card-body').first();
			const FLOW = [
				{ done: total && !r.marks.Draft, title: __('Submit grades'), desc: __('Draft marks become Submitted; faculty can no longer edit them.'),
				  status: __('{0} of {1} submitted', [r.marks.Submitted + r.marks.Locked, total]), btn: __('Submit all'), cls: 'xp-submit' },
				{ done: total && r.marks.Locked === total, title: __('Lock'), desc: __('Marks are frozen. Later changes go through Grade Appeal.'),
				  status: __('{0} of {1} locked', [r.marks.Locked, total]), btn: __('Lock all'), cls: 'xp-lock' },
				// the Term results tab's own Generate menu does this (all or selected students)
				{ done: r.results > 0, title: __('Calculate results'), desc: __('Use Generate in the Term results tab below: term GPA, term % and cumulative GPA.'),
				  status: r.results ? __('Average term GPA {0}', [r.avg_gpa]) : __('Not calculated yet'), btn: __('Go to Generate'), cls: 'xp-to-term' },
				{ done: !!r.publish_setting, title: __('What students see'), desc: __('Components, SGPA, e-grade sheet; holds for unpaid fees.'),
				  status: r.publish_setting ? __('Settings saved') : __('Not set yet'), btn: __('Edit settings'), cls: 'xp-settings' },
				{ done: r.results && r.published === r.results, title: __('Publish'), desc: __('Results appear on the student and parent portals.'),
				  status: __('{0} of {1} published', [r.published, r.results]), btn: __('Publish all'), cls: 'xp-pub' },
			];
			const next = FLOW.findIndex((f) => !f.done);
			const stat = (v, l, warn) => `<div class="${warn ? 'warn' : ''}"><b>${v}</b><span>${l}</span></div>`;
			$c.html(`
				<div class="xp-r4-stats">
					${stat(total, __('marks records'))}${stat(r.marks.Draft, __('draft'))}${stat(r.marks.Submitted, __('submitted'))}${stat(r.marks.Locked, __('locked'))}
					${stat(r.fails, __('fail grades'), r.fails > 0)}${stat(`${r.published} / ${r.results}`, __('published'))}${stat(r.avg_gpa, __('average term GPA'))}
				</div>
				<ol class="xp-flow">
					${FLOW.map((f, i) => `<li class="${f.done ? 'done' : i === next ? 'next' : ''}">
						<div class="xp-flow-head"><span class="xp-dot">${f.done ? '✓' : i + 1}</span><b>${f.title}</b></div>
						<p>${f.desc}</p>
						<div class="xp-flow-foot"><small>${f.status}</small>
							<button class="btn btn-sm ${i === next ? 'btn-primary' : 'btn-default'} ${f.cls}">${f.btn}</button></div>
					</li>`).join('')}
				</ol>
				${next === -1 ? `<div class="xp-next"><span>✓ ${__('Results are published.')}</span>
					<button class="btn btn-default btn-sm xp-go-after">${__('Re-exams and improvement are in step 5')} →</button></div>` : ''}`);
			this.$body.find('.xp-card-head').first().append(`<button class="btn btn-default btn-sm xp-consolidated">${__('Consolidated report')}</button>`);
			this.$body.find('.xp-consolidated').on('click', () => EXAM_UI('term_results').then(() => slcm.exam_ui.consolidated_report(this.plan)));
			$c.find('.xp-go-after').on('click', () => { this.step = 4; this.render(); });
			const $mount = this.$body.find('.xp-rtabs-card .xp-mount');
			const show_tab = (k, scroll) => {
				this.results_tab = k;
				this.$body.find('.xp-rtab').removeClass('on').filter(`[data-tab="${k}"]`).addClass('on');
				$mount.empty();
				this.mount(TABS.find((x) => x[0] === k)[2], $mount[0], k === 'settings' ? { subtab: 'publish', only_subtab: true } : {});
				if (scroll) this.$body.find('.xp-rtabs-card')[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
			};
			this.$body.find('.xp-rtab').on('click', (e) => show_tab($(e.currentTarget).data('tab')));
			$c.find('.xp-settings').on('click', () => show_tab('settings', true));
			$c.find('.xp-to-term').on('click', () => show_tab('term', true));
			show_tab(this.results_tab);
			const run = (method, args, msg) => call(method, Object.assign({ exam_plan: this.plan }, args)).then((n) => { frappe.show_alert({ message: msg(n), indicator: 'green' }); this.refresh(); });
			$c.find('.xp-submit').on('click', () => run('set_status_all', { status: 'Submitted' }, (n) => __('{0} submitted', [n])));
			$c.find('.xp-lock').on('click', () => frappe.confirm(__('Lock every marks record and course of this plan?'), () => run('set_status_all', { status: 'Locked' }, (n) => __('{0} locked', [n]))));
			$c.find('.xp-pub').on('click', () => frappe.confirm(__('Publish results of every student in this plan?'), () => run('publish_all', { publish: 1 }, (n) => __('{0} published', [n]))));
		});
	}

	// ── 5. After results ───────────────────────────────────────────────
	render_after() {
		const TABS = [
			['reexam', __('Re-exam'), 're_exams'],
			['improvement', __('Improvement'), 'improvement_exams'],
		];
		this.after_tab = TABS.some((t) => t[0] === this.after_tab) ? this.after_tab : 'reexam';
		this.$body.html(this.card(__('After results'),
			__('For students who failed (re-exam) or want a better grade (improvement). Schedule the re-exams, open the windows and fees, then follow registrations and payments.'), '')
			+ `<div class="xp-card xp-rtabs-card"><div class="xp-rtabs">${TABS.map(([k, l]) => `<button class="xp-rtab ${k === this.after_tab ? 'on' : ''}" data-tab="${k}">${l}</button>`).join('')}</div>
			<div class="xp-mount"></div></div>`);
		this.$body.find('.xp-card-body').first().remove();
		const $mount = this.$body.find('.xp-rtabs-card .xp-mount');
		const show = (k) => {
			this.after_tab = k;
			this.$body.find('.xp-rtab').removeClass('on').filter(`[data-tab="${k}"]`).addClass('on');
			this.unmount();
			$mount.empty();
			const mod = TABS.find((t) => t[0] === k)[2];
			if (k === 'reexam') {
				$mount.html('<div class="xp-rx-tt"></div><div class="xp-rx-screen"></div>');
				this.render_reexam_timetable($mount.find('.xp-rx-tt'));
				this.mount(mod, $mount.find('.xp-rx-screen')[0], {});
			} else {
				this.mount(mod, $mount[0], {});
			}
		};
		this.$body.find('.xp-rtab').on('click', (e) => show($(e.currentTarget).data('tab')));
		show(this.after_tab);
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
			.xp-msg{min-width:220px;white-space:normal}
			.xp-muted{color:var(--text-muted);font-size:12px}
			.xp-pub-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 12px;margin-bottom:12px;border:1px solid var(--border-color);border-radius:10px;background:var(--subtle-fg,#f8fafc)}
			.xp-pub-bar b{margin-right:6px;color:var(--text-muted)}.xp-pub-bar.on{border-color:var(--bg-green,#cdebd8);background:var(--bg-green,#e5f4ea)}
			.xp-pub-bar.on b{color:var(--text-on-green,#1d6b3a)}
			.xp-rx-tt{border:1px solid var(--border-color);border-radius:10px;padding:14px;margin-bottom:16px}
			.xp-r4-stats{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));border:1px solid var(--border-color);border-radius:10px;margin-bottom:14px}
			.xp-r4-stats>div{padding:10px 12px;border-right:1px solid var(--border-color)}.xp-r4-stats>div:last-child{border-right:0}
			.xp-r4-stats b{display:block;font-family:var(--er-font);font-size:17px}.xp-r4-stats span{font-size:11.5px;color:var(--text-muted)}
			.xp-r4-stats .warn b{color:var(--er-brand,#920C24)}
			.xp-flow{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
			.xp-flow li{display:flex;flex-direction:column;gap:6px;border:1px solid var(--border-color);border-radius:10px;padding:12px;background:var(--card-bg)}
			.xp-flow li.next{border-color:var(--er-brand,#920C24);box-shadow:0 0 0 1px var(--er-brand,#920C24) inset}
			.xp-flow-head{display:flex;align-items:center;gap:8px}.xp-flow-head b{font-size:13.5px}.xp-flow .xp-dot{width:24px;height:24px;font-size:12px;flex:none}
			.xp-flow li p{margin:0;color:var(--text-muted);font-size:12px;flex:1}
			.xp-flow-foot{display:flex;flex-direction:column;align-items:flex-start;gap:6px}.xp-flow-foot small{color:var(--text-muted);font-size:11.5px}
			.xp-flow li.done .xp-dot{background:var(--green-500,#1d6b3a);border-color:var(--green-500,#1d6b3a);color:#fff}
			@media (max-width:1100px){.xp-flow{grid-template-columns:repeat(3,minmax(0,1fr))}.xp-r4-stats{grid-template-columns:repeat(4,minmax(0,1fr))}}
			@media (max-width:700px){.xp-flow{grid-template-columns:1fr}.xp-r4-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
			.xp-ct tbody tr.xp-crow{cursor:pointer}.xp-ct tbody tr.xp-crow:hover td{background:var(--er-brand-softest,#FBEEF0)}
			.xp-ct td.act{text-align:right;white-space:nowrap}.xp-ct td small{color:var(--text-muted)}.xp-warn-text{color:var(--text-on-yellow,#8a5a00)!important}
			.xp-mk{display:flex;align-items:center;gap:8px;min-width:150px}.xp-mk .xp-meter{flex:1}
			.xp-course-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding-bottom:12px;margin-bottom:12px;border-bottom:1px solid var(--border-color)}
			.xp-course-head h4{margin:0 0 0 6px;font-family:var(--er-font);font-size:16px;font-weight:700}
			.xp-rtabs{display:flex;gap:4px;border-bottom:1px solid var(--border-color);margin-bottom:14px;overflow-x:auto}
			.xp-rtab{background:none;border:0;border-bottom:3px solid transparent;padding:8px 14px;font-family:var(--er-font);font-weight:700;font-size:13px;color:var(--text-muted);white-space:nowrap}
			.xp-rtab.on{color:var(--er-brand,#920C24);border-bottom-color:var(--er-brand,#920C24)}.xp-rtab:hover{color:var(--er-brand,#920C24)}
			.xp-schema-link{background:none;border:0;padding:0;font:inherit;font-weight:700;font-size:13px;color:var(--er-brand,#920C24);text-decoration:underline dotted;text-underline-offset:3px;cursor:pointer;text-align:left}
			.xp-schema-link:hover{text-decoration-style:solid}.xp-peek{font-size:11.5px;justify-self:start}
			.xp-sv{font-family:var(--er-font,Georgia,serif);font-size:13px}
			.xp-sv-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:14px}
			.xp-sv-stats span{border:1px solid var(--border-color);border-radius:8px;padding:10px 12px;background:var(--er-brand-softest,#FBEEF0)}
			.xp-sv-stats small{display:block;color:var(--text-muted);font-size:11px}.xp-sv-stats b{font-size:18px;color:var(--er-brand,#920C24)}
			.xp-sv-comp{border:1px solid var(--border-color);border-radius:8px;margin-bottom:10px;overflow:hidden}
			.xp-sv-comp-head{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:9px 12px;background:var(--subtle-fg,#f7f7f8)}
			.xp-sv-comp-head span{color:var(--text-muted);font-size:12px}
			.xp-sv-table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
			.xp-sv-table th{font-size:11px;color:var(--text-muted);text-align:left;padding:7px 12px;border-bottom:1px solid var(--border-color);font-weight:700}
			.xp-sv-table td{padding:7px 12px;border-bottom:1px solid var(--border-color)}.xp-sv-table tr:last-child td{border-bottom:0}
			.xp-sv-table .num{text-align:right}.xp-sv-table tr.fail td{background:var(--bg-red,#fde6e8)}
			.xp-sv-table td small{color:var(--text-muted)}.xp-sv > .xp-sv-table{border:1px solid var(--border-color);border-radius:8px}
			.xp-map-progress{display:flex;flex-direction:column;gap:6px;min-width:240px}.xp-map-progress b{font-size:13px}
			.xp-bar-track{height:6px;border-radius:3px;background:var(--gray-200,#e6e9ec);overflow:hidden}.xp-bar-track i{display:block;height:100%;background:var(--er-brand,#920C24)}
			.xp-cr-group{margin-top:16px}.xp-cr-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
			.xp-cr-title h5{margin:0;font-family:var(--er-font);font-size:14px;font-weight:700}
			.xp-count{display:inline-block;min-width:22px;text-align:center;font-size:11px;padding:1px 7px;border-radius:999px;background:var(--er-brand-softest,#FBEEF0);color:var(--er-brand,#920C24);margin-left:4px}
			.xp-cr{display:grid;grid-template-columns:minmax(200px,1.1fr) minmax(0,2fr) auto;gap:16px;align-items:center;border:1px solid var(--border-color);border-radius:10px;padding:12px 14px;margin-bottom:8px;background:var(--card-bg)}
			.xp-cr.todo{border-left:3px solid var(--er-brand-light,#C4566A)}.xp-cr.editing{border-color:var(--er-brand-border,#E8B4BE);background:var(--er-brand-softest,#FBEEF0)}
			.xp-cr-name b{display:block;font-size:13.5px}.xp-cr-name small{color:var(--text-muted);font-size:11.5px}
			.xp-cr-view{display:flex;gap:22px;align-items:center;flex-wrap:wrap}.xp-cr-view span small{display:block;color:var(--text-muted);font-size:11px}
			.xp-cr-view span b{font-size:13px}.xp-cr-view .xp-pill{margin-left:auto}
			.xp-cr-edit{display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:center}.xp-cr-edit select{min-width:0!important}
			.xp-why{grid-column:1/-1;color:var(--text-muted);font-size:11.5px}
			.xp-cr-act{display:flex;gap:6px;justify-content:flex-end;white-space:nowrap}
			.xp-next{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-top:16px;padding:12px 14px;border-radius:10px;background:var(--bg-green,#e5f4ea)}
			.xp-next span{font-weight:700;color:var(--text-on-green,#1d6b3a)}
			@media (max-width:860px){.xp-cr{grid-template-columns:1fr}.xp-cr-act{justify-content:flex-start}.xp-cr-edit{grid-template-columns:1fr}}
			.xp-tt td:first-child{min-width:150px}.xp-table .xp-tt .xp-d{min-width:135px}.xp-table .xp-tt .xp-s,.xp-table .xp-tt .xp-e{min-width:110px}
			.xp-table .xp-tt .xp-v{min-width:160px}.xp-table .xp-tt input.xp-c{min-width:64px;width:72px}.xp-table .xp-tt .xp-f{min-width:140px}.xp-tt .xp-msg{min-width:90px}.xp-msg .xp-pill{display:block;font-weight:600}
			.xp-tab{display:none;flex-direction:column;gap:10px}.xp-tab.on{display:flex}.xp-card .xp-rtabs{margin-bottom:4px}
			.xp-tools,.xp-filters{gap:8px}
			.xp-filters{align-items:flex-end;padding:8px 10px;border:1px solid var(--border-color);border-radius:8px;background:var(--subtle-fg,#f8f8f8)}
			.xp-filters label{display:flex;flex-direction:column;gap:2px;margin:0;font-size:11px;font-weight:600;color:var(--text-muted)}
			.xp-filters .form-control{width:170px;min-width:0!important;font-weight:400}.xp-filters .xp-count-lines{align-self:center;margin-left:auto}
			.xp-tab .xp-pub-bar{margin-bottom:0;padding:6px 12px}
			.xp-sheet{overflow:auto;max-height:72vh;border:1px solid var(--gray-400,#bdbdbd);border-radius:6px;background:var(--card-bg,#fff)}
			.xp-sheet table{border-collapse:separate;border-spacing:0;table-layout:fixed;width:max-content;font-size:12.5px}
			.xp-sheet th,.xp-sheet td{border-right:1px solid var(--gray-400,#bdbdbd);border-bottom:1px solid var(--gray-400,#bdbdbd);padding:0;vertical-align:top;background:var(--card-bg,#fff)}
			.xp-sheet thead th{position:sticky;top:0;z-index:2;background:var(--gray-300,#d6d6d6);color:var(--text-color);font-weight:700;text-align:center;vertical-align:middle;padding:6px;line-height:1.25;white-space:normal}
			.xp-sheet th.xp-sl,.xp-sheet td.xp-sl{position:sticky;left:0;z-index:1}.xp-sheet thead th.xp-dt,.xp-sheet td.xp-dt:nth-child(2){position:sticky;left:50px;z-index:1}
			.xp-sheet thead th.xp-sl,.xp-sheet thead th.xp-dt{z-index:3}
			.xp-sheet th.xp-sess span{display:flex;justify-content:center;gap:2px;font-weight:400;font-size:11.5px;white-space:nowrap;margin-top:2px}
			.xp-sheet .xp-st{border:1px solid transparent;border-radius:4px;background:rgba(255,255,255,.5);font:inherit;width:100px;padding:0 2px}
			.xp-sheet tr.xp-day td{background:var(--gray-200,#e8e8e8);padding:0}
			.xp-day-in{position:sticky;left:0;display:flex;gap:8px;align-items:center;padding:6px 10px;width:max-content}
			.xp-day-in .btn{font-weight:400}
			.xp-sheet td.xp-sl,.xp-sheet td.xp-dt{text-align:center;font-weight:700;padding:8px 4px}
			.xp-sheet td.xp-blank{background:var(--subtle-fg,#f7f7f7);text-align:center;vertical-align:middle}
			.xp-sheet td.xp-none{padding:24px;text-align:center;color:var(--text-muted)}
			.xp-sheet .xp-in{display:block;width:100%;border:0;background:transparent;padding:7px 8px;font:inherit;color:var(--text-color);min-height:34px;field-sizing:content;resize:none;overflow:hidden;line-height:1.35}
			.xp-sheet .xp-in:focus{outline:2px solid var(--er-brand,#920C24);outline-offset:-2px;background:var(--control-bg,#fff)}
			.xp-sheet td.xp-bad,.xp-sheet td.xp-bad .xp-in{background:var(--bg-red,#fde6e8)}.xp-sheet td.xp-warn{background:var(--bg-yellow,#fdf1d2)}
			.xp-sheet td.xp-txt>.xp-in{text-decoration:underline dotted var(--orange-500,#f59e0b);text-underline-offset:3px}
			.xp-sub{display:flex;align-items:center;padding:0 8px 6px;font-size:11px}.xp-sheet td.xp-paper-c{position:relative}
			.xp-ctag{display:inline-flex;align-items:center;gap:4px;background:var(--er-brand-softest,#FBEEF0);color:var(--er-brand,#920C24);border-radius:10px;padding:0 4px 0 8px}
			.xp-ctag button{border:0;background:none;color:inherit;padding:0 2px;line-height:1;cursor:pointer}
			.xp-ln-act{visibility:hidden;display:flex;gap:4px;position:absolute;right:4px;bottom:4px}.xp-sheet tr:hover .xp-ln-act,.xp-paper-c:focus-within .xp-ln-act{visibility:visible}
			.xp-ln-act button{border:1px solid var(--border-color);background:var(--control-bg,#fff);border-radius:4px;font-size:11px;padding:0 6px;line-height:18px;color:var(--text-color)}
			.xp-ln-act .xp-del:hover{color:var(--red-600,#c0262d);border-color:currentColor}
			.xp-pick{position:absolute;z-index:1050;max-height:260px;overflow:auto;background:var(--card-bg,#fff);border:1px solid var(--border-color,#d1d5db);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.14);padding:4px;font-size:12.5px}
			.xp-pick-i{display:flex;justify-content:space-between;gap:12px;padding:6px 10px;border-radius:5px;cursor:pointer;white-space:nowrap}
			.xp-pick-i small{color:var(--text-muted)}.xp-pick-i.on,.xp-pick-i:hover{background:var(--er-brand-softest,#FBEEF0);color:var(--er-brand,#920C24)}
			.xp-ce-sheet td{vertical-align:top}.xp-ce-sheet td.xp-subj{padding:6px 8px}.xp-ce-sheet td.xp-subj small{display:block;color:var(--text-muted);font-size:11px}
			.xp-unsched .xp-soft{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
			.xp-issues ul{margin:6px 0 0;padding-left:18px}.xp-issues li.bad{color:var(--text-on-red,#b0182b)}
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
