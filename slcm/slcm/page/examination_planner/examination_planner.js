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
			const sel = (list, val, cls) => `<select class="form-control input-sm ${cls}"><option value=""></option>${list.map((x) => `<option ${x === val ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`;
			const rows = m.courses.map((c) => {
				const ev = c.evaluation_schema || c.suggest_evaluation_schema || '', gs = c.grade_schema || c.suggest_grade_schema || '';
				const saved = c.source === 'saved';
				return `<tr data-course="${esc(c.course)}" data-saved-ev="${esc(c.evaluation_schema || '')}" data-saved-gs="${esc(c.grade_schema || '')}" class="${ev && gs ? '' : 'xp-flag'}">
					<td><input type="checkbox" class="xp-sel"></td>
					<td><b>${esc(c.course_code || c.course)}</b><br><small>${esc(c.course_name || '')}</small></td>
					<td>${esc(c.programme || '')}</td><td class="num">${c.enrolled_students || 0}</td>
					<td>${sel(evs, ev, 'xp-ev')}</td><td>${sel(gss, gs, 'xp-gs')}</td>
					<td>${saved ? `<span class="xp-pill ok">${__('Saved')}</span>` : c.source ? `<span class="xp-pill info">${esc(c.source)}</span>` : `<span class="xp-pill bad">${__('Not mapped')}</span>`}</td></tr>`;
			}).join('');
			$c.html(`
				<div class="xp-bar"><b>${this.o.counts.courses_mapped} / ${this.o.counts.courses_taught}</b> ${__('courses mapped')}
					<span class="xp-grow"></span>
					<button class="btn btn-default btn-sm xp-new-es">${__('New Evaluation Schema')}</button>
					<button class="btn btn-default btn-sm xp-new-gs">${__('New Grading Schema')}</button></div>
				<div class="xp-table"><table class="table table-sm"><thead><tr><th><input type="checkbox" class="xp-all"></th><th>${__('Course')}</th><th>${__('Programme')}</th><th>${__('Students')}</th>
					<th>${__('Evaluation Schema')}</th><th>${__('Grade Schema')}</th><th>${__('Filled from')}</th></tr></thead><tbody>${rows || `<tr><td colspan="7">${__('No Classes in this term yet. Create Classes first (Programme Management).')}</td></tr>`}</tbody></table></div>
				<div class="xp-bar xp-soft"><span>${__('Selected')}:</span>${sel(evs, '', 'xp-bulk-ev')}${sel(gss, '', 'xp-bulk-gs')}
					<button class="btn btn-default btn-sm xp-apply">${__('Apply to selected')}</button>
					<button class="btn btn-default btn-sm xp-unmap">${__('Unmap selected')}</button>
					<span class="xp-grow"></span><button class="btn btn-primary btn-sm xp-save">${__('Save mapping')}</button></div>`);
			$c.find('.xp-all').on('change', (e) => $c.find('.xp-sel').prop('checked', e.target.checked));
			$c.find('.xp-new-es').on('click', () => frappe.new_doc('Evaluation Schema'));
			$c.find('.xp-new-gs').on('click', () => frappe.new_doc('Grading Schema'));
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
				<div class="xp-bar"><span class="xp-grow"></span><button class="btn btn-default btn-sm xp-check">${__('Check')}</button>
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
			$cards.eq(0).find('.xp-check').on('click', () => call('check_timetable', { exam_plan: this.plan, rows: JSON.stringify(collect()) }).then(show));
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
			.xp-table select,.xp-table input.form-control{min-width:120px}
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
