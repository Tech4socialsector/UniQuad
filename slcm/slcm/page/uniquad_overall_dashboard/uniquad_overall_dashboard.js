// Uniquad Overall Dashboard — /desk/uniquad-overall-dashboard
//
// Every Uniquad module in one place — Admission, Student Registration,
// Programme Management, Attendance, ID Card, Fees, Venue Booking, PACE, FLE,
// Examinations, Transcripts and Promotion — laid out like the Pathways Overall Dashboard: filters →
// headline funnel → a board of single / paired cards (one section per module)
// → Timeline tab (one person, start to end) → Admission Funnel tab.
// Uniquad look: #920C24 + Merriweather.
//
// Every card and number opens a centred drilldown (per-programme cards, then
// a server-paged, sortable, searchable table with "Export all (CSV)").
// Clicking a person opens their timeline. All numbers come from
// permission-scoped server calls; every value rendered into HTML goes
// through esc().

const UOD_API = 'slcm.slcm.page.uniquad_overall_dashboard.uniquad_overall_dashboard.';
const UOD_STORE_KEY = 'uod-filters-v1';
const UOD_LIST_FILTERS = ['programmes', 'academic_years', 'admission_cycles', 'genders', 'categories', 'stages'];

// Tone = what a colour means (same everywhere on the page).
const UOD_TONES = {
	good: '#1d6b3a', bad: '#a4161a', action: '#8a5a00', info: '#2b4f7e', neutral: '#6B6560', time: '#920c24'
};
const UOD_STAGE_COLORS = {
	'Applying': '#8A8580', 'In process': '#2b4f7e', 'Waitlisted': '#8a5a00',
	'Offer / Admitted': '#1d6b3a', 'Not admitted': '#a4161a'
};
// Categorical slots for programmes (assigned in name order, always shown with the name).
const UOD_PALETTE = ['#920c24', '#2b4f7e', '#0f6b63', '#8a5a00', '#6d3b8c', '#3d4a5c', '#b0476b', '#4f7a28', '#c2541a', '#5b6b7a'];
const UOD_KIND_COLORS = {
	application: '#920c24', status: '#6B7A8A', payment: '#2F7D4F', test: '#4F46E5', interview: '#0891B2',
	merit: '#0D9488', seat: '#16A34A', offer: '#7C3AED', log: '#8A96A3', student: '#2F7D4F', idcard: '#A16207', onboarding: '#0D9488',
	fees: '#1d6b3a', attendance: '#2b4f7e', exams: '#920c24', transcript: '#6d3b8c', promotion: '#0f6b63'
};
const UOD_DAY_RANGES = [['0-7', '0–7 days'], ['8-15', '8–15 days'], ['16-30', '16–30 days'], ['31-60', '31–60 days'],
	['61-90', '61–90 days'], ['91-', '90+ days'], ['31-', 'Over 30 days']];

const UOD_ICONS = {
	users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
	file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/>',
	mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/>',
	calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
	clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
	award: '<circle cx="12" cy="8" r="6"/><path d="M15.48 12.89 17 22l-5-3-5 3 1.52-9.11"/>',
	xcircle: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>',
	check: '<path d="M20 6 9 17l-5-5"/>',
	clipboard: '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
	pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>',
	coins: '<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/>',
	send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
	handshake: '<path d="m11 17 2 2a1 1 0 1 0 3-3"/><path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4"/><path d="m21 3 1 11h-2"/><path d="M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3"/><path d="M3 4h8"/>',
	filesign: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="m9 15 2 2 4-4"/>',
	door: '<path d="M13 4h3a2 2 0 0 1 2 2v14"/><path d="M2 20h3"/><path d="M13 20h9"/><path d="M10 12v.01"/><path d="M13 4.56v16.88a.5.5 0 0 1-.6.49l-6.4-1.28A1 1 0 0 1 5 19.67V5.78a2 2 0 0 1 1.6-1.96l5.2-1.04a1 1 0 0 1 1.2.98z"/>',
	idcard: '<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="8" cy="12" r="2"/><path d="M14 10h4M14 14h4"/>',
	alert: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>'
};
const uod_icon = (k) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${UOD_ICONS[k] || ''}</svg>`;

frappe.pages['uniquad-overall-dashboard'].on_page_load = function (wrapper) {
	if (!document.getElementById('uod-font')) {
		$('head').append('<link id="uod-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Uniquad Overall Dashboard'),
		single_column: true
	});
	wrapper.uod = new UniquadOverallDashboard(page, wrapper);
};

class UniquadOverallDashboard {
	constructor(page, wrapper) {
		this.page = page;
		this.$root = $(wrapper).find('.page-content');
		this.meta = null;
		this.data = null;
		this.funnel = null;
		this.filters = null;
		this.ms = {};
		this.tab = 'dash';
		this.tl = { people: 'app', sort: 'creation', stage: '', status: '', pipeline: '', days: '' };
		this.render_shell();
		frappe.xcall(UOD_API + 'get_meta').then((meta) => {
			this.meta = meta;
			UOD_LIST_FILTERS.forEach(k => this.ms[k].set_options(meta.options[k] || []));
			const saved = this.read_saved() || {};
			UOD_LIST_FILTERS.forEach(k => this.ms[k].set_value(saved[k] || []));
			const [from_date, to_date] = this.preset_range('year');
			this.$root.find('#uod-from').val(from_date);
			this.$root.find('#uod-to').val(to_date);
			this.load(this.current_filters());
		});
	}

	// ── helpers ────────────────────────────────────────────────────────────
	esc(v) { return frappe.utils.escape_html(v === null || v === undefined ? '' : String(v)); }
	n(v) { return v === null || v === undefined ? '—' : Number(v).toLocaleString('en-IN'); }
	pct(a, b) { return b ? Math.round((a / b) * 1000) / 10 : 0; }
	pct_txt(a, b) {
		if (!b) return '0%';
		const p = (a / b) * 100;
		return a && p < 0.1 ? '<0.1%' : `${Math.round(p * 10) / 10}%`;
	}
	fmt_date(d) { return d ? frappe.datetime.str_to_user(String(d).slice(0, 10)) : ''; }
	fmt_dt(d) { return d ? frappe.datetime.str_to_user(String(d)).replace(/(\d{1,2}:\d{2}):\d{2}(\.\d+)?$/, '$1') : ''; }
	prog_name(p) { return (this.data && this.data.programme_names[p]) || p || __('Not set'); }
	prog_color(p) {
		const names = Object.keys((this.data && this.data.programme_names) || {}).sort();
		const i = names.indexOf(p);
		return i < 0 ? '#64748B' : UOD_PALETTE[i % UOD_PALETTE.length];
	}
	prog_pill(p) { return `<span class="uod-pill" style="--c:${this.prog_color(p)}">${this.esc(this.prog_name(p))}</span>`; }
	stage_pill(s) { return s ? `<span class="uod-pill" style="--c:${UOD_STAGE_COLORS[s] || '#64748B'}">${this.esc(s)}</span>` : ''; }
	slug(dt) { return String(dt || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
	desk_link(dt, name) { return `/desk/${this.slug(dt)}/${encodeURIComponent(name)}`; }

	read_saved() {
		try { return JSON.parse(localStorage.getItem(UOD_STORE_KEY) || 'null'); } catch (e) { return null; }
	}
	// Dates are deliberately not remembered: the page always opens on "This year".
	save_filters(f) {
		try {
			const keep = {};
			UOD_LIST_FILTERS.forEach(k => { keep[k] = f[k] || []; });
			localStorage.setItem(UOD_STORE_KEY, JSON.stringify(keep));
		} catch (e) { /* private mode etc. */ }
	}

	// ── layout ─────────────────────────────────────────────────────────────
	render_shell() {
		const ms = (k, label, ph) => `<div class="uod-f"><label>${label}</label><div class="uod-ms" id="uod-ms-${k}" data-placeholder="${ph}"></div></div>`;
		const panel = (id, title, sub, tools = '', body = `<div class="uod-panel-body" id="${id}"></div>`) => `
			<div class="uod-panel">
				<div class="uod-panel-head"><div><div class="uod-panel-title">${title}</div><div class="uod-panel-sub">${sub}</div></div>${tools}</div>
				${body}
			</div>`;
		this.$root.html(`
			<style>${UOD_CSS}</style>
			<div class="uod-root">
				<div class="uod-tabs" role="tablist">
					<button class="uod-tab is-on" data-tab="dash" role="tab">${__('Dashboard')}</button>
					<button class="uod-tab" data-tab="timeline" role="tab">${__('Timeline')}</button>
					<button class="uod-tab" data-tab="funnel" role="tab">${__('Admission Funnel')}</button>
				</div>
				<div class="uod-filters">
					<div class="uod-topbar">
						<div class="uod-presets">
							${[['month', __('This month')], ['last30', __('Last 30 days')], ['last90', __('Last 90 days')],
								['year', __('This year')], ['all', __('All time')]]
								.map(([k, l]) => `<button class="uod-preset" data-p="${k}">${l}</button>`).join('')}
						</div>
						<div class="uod-topbar-right">
							<span class="uod-muted" title="${__('Ignores every filter')}">${__('All-time applications')}: <b id="uod-alltime">—</b></span>
							<span class="uod-muted" id="uod-sub"></span>
							<button class="btn btn-default btn-xs" id="uod-guide">ⓘ ${__('Card guide')}</button>
							<button class="btn btn-default btn-xs" id="uod-refresh">⟳ ${__('Refresh')}</button>
						</div>
					</div>
					<div class="uod-filter-row">
						<div class="uod-f"><label>${__('Created from')}</label><input type="date" id="uod-from"></div>
						<div class="uod-f"><label>${__('To')}</label><input type="date" id="uod-to"></div>
						${ms('programmes', __('Programme'), __('All programmes'))}
						${ms('academic_years', __('Academic year'), __('All years'))}
						${ms('admission_cycles', __('Admission cycle'), __('All cycles'))}
						${ms('genders', __('Gender'), __('All genders'))}
						${ms('categories', __('Category'), __('All categories'))}
						${ms('stages', __('Stage'), __('All stages'))}
						<div class="uod-f uod-f-btns">
							<button class="btn btn-primary btn-sm" id="uod-apply">${__('Apply')}</button>
							<button class="btn btn-default btn-sm" id="uod-reset">${__('Reset')}</button>
						</div>
					</div>
				</div>

				<div class="uod-pane" data-pane="dash">
					<div class="uod-jump" id="uod-jump"></div>
					<div id="uod-overview"></div>
					<div class="uod-section-title uod-headline-title"><span>${__('Regular admission funnel')}</span></div>
					<div class="uod-cards" id="uod-cards"></div>
					<div class="uod-board" id="uod-board"></div>
				</div>

				<div class="uod-pane" data-pane="timeline" hidden>
					<div class="uod-panel">
						<div class="uod-panel-head"><div>
							<div class="uod-panel-title">${__('Student journey timeline')}</div>
							<div class="uod-panel-sub">${__('Everyone matching the filters above · search, then click a name to open their timeline, start to end')}</div>
						</div></div>
						<div class="uod-tl-tools" id="uod-tl-tools"></div>
						<div id="uod-tl-list"></div>
					</div>
				</div>

				<div class="uod-pane" data-pane="funnel" hidden>
					${panel('uod-funbars', __('Admission funnel'), __('How many applicants reach each step · bar length = share of all applications · click a step for its list'))}
					${panel('uod-fununits', __('Funnel by programme'), __('The same steps for each programme · % = share of the step before · click a number for its list'), '',
						'<div class="uod-table-scroll" id="uod-fununits"></div>')}
					${panel('uod-pipe', __('Pipeline & offers'), __('How long applicants have been in the process, and where offers stand · click any number or bar for its list'))}
					${panel('uod-prog', __('Programme summary'), __('Applications → admitted → registered, per programme · every number opens its list'),
						`<div class="uod-panel-tools"><button class="btn btn-default btn-xs" id="uod-export-prog">${__('Export CSV')}</button></div>`,
						'<div class="uod-table-scroll" id="uod-prog"></div>')}
					${panel('uod-profile', __('Who is applying'), __('Category, gender, source and state of the applications in scope · click a bar or slice for its list'))}
					${panel('uod-iv', __('Interviews'), __('Every interview slot — past, upcoming and cancelled · filtered by interview date'), this.range_tools())}
					${panel('uod-apps', __('All applications'), __('Every application in scope, newest first · page, sort, search and export all of them'))}
					${panel('uod-regs', __('Student registrations'), __('Every student record in scope and where it is in the registration chain'))}
					<div id="uod-log-wrap" style="display:none">
						${panel('uod-log', __('Admission change log'), __('Every admission audit entry (what changed, from → to, who, when, why) in the selected dates'))}
					</div>
					<div class="uod-grid-2">
						${panel('uod-stages', __('Where applicants are'), __('Current stage of every application in scope · click a bar for the list'))}
						${panel('uod-trend', __('Applications per week'), __('Week starting Monday · hover for numbers · click a bar for that week'))}
					</div>
				</div>
				<div class="uod-tip" id="uod-tip"></div>
			</div>
		`);

		const $c = this.$root;
		UOD_LIST_FILTERS.forEach(k => { this.ms[k] = this.make_multiselect($c.find(`#uod-ms-${k}`)); });
		$c.find('#uod-apply').on('click', () => { this.load(this.current_filters()); });
		$c.find('#uod-refresh').on('click', () => { this.load(this.filters || this.current_filters(), true); });
		$c.find('#uod-reset').on('click', () => {
			Object.values(this.ms).forEach(m => m.clear());
			const [f, t] = this.preset_range('year');
			$c.find('#uod-from').val(f);
			$c.find('#uod-to').val(t);
			this.load(this.current_filters());
		});
		// A preset is one click = the user is done choosing → apply at once.
		$c.find('.uod-preset:not(.uod-rpreset)').on('click', (e) => {
			const [f, t] = this.preset_range($(e.currentTarget).data('p'));
			$c.find('#uod-from').val(f || '');
			$c.find('#uod-to').val(t || '');
			this.load(this.current_filters());
		});
		$c.find('#uod-guide').on('click', () => { this.open_guide(); });
		$c.find('.uod-tab').on('click', (e) => { this.show_tab(String($(e.currentTarget).data('tab'))); });
		$(document).on('click.uod', (e) => {
			if (!$(e.target).closest('.uod-ms').length) $('.uod-ms.open').removeClass('open');
		});
		this.bind_tip($c);
	}

	preset_range(p) {
		const today = frappe.datetime.get_today();
		const d = frappe.datetime;
		if (p === 'month') return [d.month_start(), today];
		if (p === 'last30') return [d.add_days(today, -29), today];
		if (p === 'last90') return [d.add_days(today, -89), today];
		if (p === 'year') return [today.slice(0, 4) + '-01-01', today];
		return ['', ''];
	}
	current_filters() {
		const f = { from_date: this.$root.find('#uod-from').val() || null, to_date: this.$root.find('#uod-to').val() || null };
		UOD_LIST_FILTERS.forEach(k => { f[k] = this.ms[k].get_value(); });
		return f;
	}
	mark_preset() {
		const f = this.filters || {};
		let on = null;
		['month', 'last30', 'last90', 'year', 'all'].forEach(p => {
			const [a, b] = this.preset_range(p);
			if ((a || null) === (f.from_date || null) && (b || null) === (f.to_date || null)) on = p;
		});
		this.$root.find('.uod-preset:not(.uod-rpreset)').each((_i, el) => { $(el).toggleClass('is-on', $(el).data('p') === on); });
	}

	// Searchable multi-select with chips (no Frappe control: these filter
	// values come from three different DocTypes).
	make_multiselect($el) {
		const ph = $el.data('placeholder');
		let options = [];
		let value = [];
		$el.html(`<div class="uod-ms-box"></div>
			<div class="uod-ms-panel">
				<div class="uod-ms-search"><input type="text" placeholder="${__('Search')}"></div>
				<div class="uod-ms-actions"><a data-a="all">${__('Select all')}</a><a data-a="none">${__('Clear')}</a></div>
				<div class="uod-ms-list"></div>
			</div>`);
		const $box = $el.find('.uod-ms-box');
		const $list = $el.find('.uod-ms-list');
		const $q = $el.find('.uod-ms-search input');
		const label_of = (v) => (options.find(o => o.value === v) || { label: v }).label;
		const draw_box = () => {
			if (!value.length) { $box.html(`<span class="uod-ms-ph">${this.esc(ph)}</span>`); return; }
			const chips = value.slice(0, 2).map(v => `<span class="uod-ms-chip"><span class="txt">${this.esc(label_of(v))}</span><span class="x" data-v="${this.esc(v)}">×</span></span>`).join('');
			$box.html(chips + (value.length > 2 ? `<span class="uod-ms-more">+${value.length - 2}</span>` : ''));
		};
		const draw_list = () => {
			const q = ($q.val() || '').toLowerCase();
			const shown = options.filter(o => !q || String(o.label).toLowerCase().includes(q) || String(o.value).toLowerCase().includes(q));
			$list.html(shown.length ? shown.map(o => `<label class="uod-ms-opt"><input type="checkbox" value="${this.esc(o.value)}" ${value.includes(o.value) ? 'checked' : ''}> ${this.esc(o.label)}</label>`).join('')
				: `<div class="uod-ms-empty">${__('No matches')}</div>`);
		};
		$box.on('click', (e) => {
			const $x = $(e.target).closest('.x');
			if ($x.length) {
				value = value.filter(v => v !== String($x.data('v')));
				draw_box(); draw_list();
				e.stopPropagation();
				return;
			}
			$('.uod-ms.open').not($el).removeClass('open');
			$el.toggleClass('open');
			if ($el.hasClass('open')) { draw_list(); $q.trigger('focus'); }
		});
		$q.on('input', () => { draw_list(); });
		$list.on('change', 'input', (e) => {
			const v = e.target.value;
			value = e.target.checked ? value.concat([v]) : value.filter(x => x !== v);
			draw_box();
		});
		$el.find('.uod-ms-actions a').on('click', (e) => {
			const a = $(e.currentTarget).data('a');
			value = a === 'all' ? options.map(o => o.value) : [];
			draw_box(); draw_list();
		});
		draw_box();
		return {
			set_options: (o) => { options = o || []; value = value.filter(v => options.some(x => x.value === v)); draw_box(); },
			set_value: (v) => { value = (v || []).filter(x => options.some(o => o.value === x)); draw_box(); },
			get_value: () => value.slice(),
			clear: () => { value = []; draw_box(); }
		};
	}

	// ── data ───────────────────────────────────────────────────────────────
	load(filters, refresh = false) {
		this.filters = filters;
		this.save_filters(filters);
		this.mark_preset();
		this.funnel = null;
		const $r = this.$root.find('.uod-root').addClass('uod-loading');
		frappe.xcall(UOD_API + 'get_dashboard_data', { filters, refresh: refresh ? 1 : 0 }).then((data) => {
			this.data = data;
			$r.removeClass('uod-loading');
			this.$root.find('#uod-alltime').text(this.n(data.alltime));
			this.$root.find('#uod-sub').text(`${__('Updated')} ${data.updated}`);
			this.render_cards();
			this.render_board();
			if (this.tab === 'timeline') this.render_timeline_tab();
			if (this.tab === 'funnel') this.render_funnel_tab(refresh);
		}).catch(() => { $r.removeClass('uod-loading'); });
	}

	show_tab(tab) {
		this.tab = tab;
		this.$root.find('.uod-tab').each((_i, el) => { $(el).toggleClass('is-on', $(el).data('tab') === tab); });
		this.$root.find('.uod-pane').each((_i, el) => { el.hidden = $(el).data('pane') !== tab; });
		if (!this.data) return;
		if (tab === 'timeline') this.render_timeline_tab();
		if (tab === 'funnel') this.render_funnel_tab();
	}

	// ── dashboard tab ──────────────────────────────────────────────────────
	card_data(key) { return (this.data.cards || {})[key]; }
	card_count(key) { const d = this.card_data(key); return d ? d.total : null; }
	// null = the user cannot read that DocType: the card shows "—" and is not clickable.
	allowed(key) { return this.card_data(key) !== null && this.card_data(key) !== undefined; }
	base_of(card) {
		if (!card.pct) return null;
		const t = (this.data.totals || {})[card.kind];
		return t === undefined ? null : t;
	}
	money(v) { return format_currency(v || 0, frappe.boot.sysdefaults.currency || 'INR', 0); }
	unused(c) { const d = this.card_data(c.key); return !!(d && d.unused); }
	sub_of(c) {
		const d = this.card_data(c.key);
		if (d && d.unused) return __('not recorded in Uniquad yet');
		if (c.sum && d && d.amount !== null && d.amount !== undefined) return this.money(d.amount);
		if (c.sub) return c.sub;
		if (!c.pct) return '';
		return c.kind === 'stu' ? __('of student records') : __('of total applications');
	}
	info_html(text) {
		return text ? `<span class="uod-info" data-tip="${this.esc(text)}" tabindex="0" aria-label="${this.esc(text)}">i</span>` : '';
	}
	share_html(v, base) {
		return base === null ? '' : `<span class="uod-share">${this.pct_txt(v, base)}</span>`;
	}
	dot(card) {
		return ['good', 'bad'].includes(card.tone) ? `<span class="uod-dot" style="--c:${UOD_TONES[card.tone]}"></span>` : '';
	}

	render_cards() {
		const cards = this.meta.headline;
		const html = cards.map((c) => {
			const v = this.card_count(c.key);
			const aside = c.key === 'not_admitted' ? ' is-aside' : '';
			return `<div class="uod-kpi${this.allowed(c.key) ? ' is-click' : ''}${aside}" ${this.allowed(c.key) ? `data-card="${c.key}" tabindex="0" role="button"` : ''}>
				<div class="uod-kpi-top"><span class="uod-kpi-label">${this.dot(c)}${this.esc(c.label)}</span>${this.info_html(c.guide)}</div>
				<div class="uod-kpi-value" style="${c.tone === 'action' || c.tone === 'time' ? `color:${UOD_TONES[c.tone]}` : ''}">${this.n(v)}${v === null ? '' : this.share_html(v, this.data.app_total)}</div>
				<div class="uod-kpi-sub">${this.esc(c.sub)}</div>
			</div>`;
		}).join('');
		const $c = this.$root.find('#uod-cards').html(`<div class="uod-headline is-funnel">${html}</div>`);
		this.bind_click($c.find('[data-card]'), (el) => this.drill_card($(el).data('card')));
	}

	render_board() {
		const seen = new Set();
		const section_html = (sec) => {
			// A section whose every card the user cannot read is left out.
			const tiles = sec.tiles.filter(t => t.cards.some(c => this.allowed(c.key)));
			if (!tiles.length) return '';
			const anchor = seen.has(sec.key) ? '' : `id="uod-sec-${sec.key}"`;
			seen.add(sec.key);
			const is_stu = sec.key === 'registration';
			const note = is_stu ? `<span class="uod-section-note">${this.n(this.data.stu_total)} ${__('student records in scope')}</span>` : '';
			return `<div class="uod-section" ${anchor}><div class="uod-section-title"><span>${this.esc(sec.title)}</span>${note}</div>
				<div class="uod-tiles">${tiles.map(t => this.tile_html(t)).join('')}</div></div>`;
		};
		// "At a glance" sits above the admission funnel; every other section below it.
		const $o = this.$root.find('#uod-overview').html(this.meta.board.filter(sec => sec.key === 'overview').map(section_html).join(''));
		$o.find('.uod-section').first().css('margin-top', 0);
		this.bind_click($o.find('[data-card]'), (el) => this.drill_card($(el).data('card')));
		const html = this.meta.board.filter(sec => sec.key !== 'overview').map(section_html).join('');
		const $b = this.$root.find('#uod-board').html(html);
		this.bind_click($b.find('[data-card]'), (el) => this.drill_card($(el).data('card')));
		const chips = this.meta.modules.filter(m => seen.has(m.key))
			.map(m => `<button class="uod-jump-chip" data-sec="${m.key}">${this.esc(m.label)}</button>`).join('');
		const $j = this.$root.find('#uod-jump').html(chips ? `<span class="uod-jump-label">${__('Jump to')}</span>${chips}` : '');
		$j.find('.uod-jump-chip').on('click', (e) => {
			const el = this.$root.find(`#uod-sec-${$(e.currentTarget).data('sec')}`)[0];
			if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
		});
	}

	tile_html(t) {
		const guide = t.cards.map(c => `${c.label}: ${c.guide || ''}`).join('\n');
		const click = (c) => this.allowed(c.key) ? `is-click" data-card="${c.key}" tabindex="0" role="button` : 'is-denied" title="' + __('You do not have access to these records');
		const share = (c, v) => v === null || this.unused(c) ? '' : this.share_html(v, this.base_of(c));
		const value = (c, v) => this.unused(c) ? '—' : this.n(v);
		if (t.cards.length === 1) {
			const c = t.cards[0];
			const v = this.card_count(c.key);
			const color = ['action', 'time'].includes(c.tone) && v ? `color:${UOD_TONES[c.tone]}` : '';
			return `<div class="uod-tile uod-tile-1 ${click(c)}">
				<div class="uod-tile-head"><span class="uod-tile-title">${this.esc(t.title)}</span>${this.info_html(guide)}</div>
				<div class="uod-kpi-value" style="${color}">${value(c, v)}${share(c, v)}</div>
				<div class="uod-kpi-sub">${this.esc(this.sub_of(c))}</div>
			</div>`;
		}
		const halves = t.cards.map(c => {
			const v = this.card_count(c.key);
			const live = v && !this.unused(c);
			const color = c.tone === 'action' && live ? `color:${UOD_TONES.action}` : '';
			const flag = c.tone === 'action' && live ? `<span class="uod-flag">${__('Action')}</span>` : '';
			const sub = this.sub_of(c);
			return `<div class="uod-half ${click(c)}">
				<div class="uod-half-label"><span class="uod-dot" style="--c:${UOD_TONES[c.tone] || UOD_TONES.neutral}"></span>${this.esc(c.label)}${flag}</div>
				<div class="uod-kpi-value" style="${color}">${value(c, v)}${share(c, v)}</div>
				${sub ? `<div class="uod-kpi-sub">${this.esc(sub)}</div>` : ''}
			</div>`;
		}).join('');
		return `<div class="uod-tile uod-tile-2">
			<div class="uod-tile-head"><span class="uod-tile-title">${this.esc(t.title)}</span>${this.info_html(guide)}</div>
			<div class="uod-halves">${halves}</div>
		</div>`;
	}

	bind_click($els, open) {
		$els.on('click', (e) => {
			if ($(e.target).closest('.uod-info').length) return;
			e.stopPropagation();
			open(e.currentTarget);
		});
		$els.on('keydown', (e) => {
			if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(e.currentTarget); }
		});
	}

	find_card(key) {
		for (const c of this.meta.headline) if (c.key === key) return c;
		for (const s of this.meta.board) for (const t of s.tiles) for (const c of t.cards) if (c.key === key) return c;
		return null;
	}
	drill_card(key) {
		const c = this.find_card(key);
		if (!c) return;
		const src = this.meta.sources[c.kind] || {};
		const honours = (src.honours || []).length ? ` ${__('Filters applied')}: ${src.honours.join(', ')}.` : ` ${__('The filters above do not apply to these records.')}`;
		this.drill(c.label, c.kind, { card: key }, (c.guide || '') + honours);
	}

	// ── drilldown popup ────────────────────────────────────────────────────
	drill(title, kind, extra = {}, note = '') {
		const d = new frappe.ui.Dialog({ title, size: 'extra-large' });
		d.$wrapper.find('.modal-dialog').addClass('uod-modal');
		d.$body.html(`<style>${UOD_CSS}</style><div class="uod-root uod-in-modal">
			${note ? `<div class="uod-muted uod-dd-note">${this.esc(note)}</div>` : ''}
			<div class="uod-dd-units"></div><div class="uod-dd-table"></div></div>`);
		this.bind_tip(d.$body);
		const state = { programme: '__all__' };
		const draw_units = (units) => {
			const total = Object.values(units || {}).reduce((a, b) => a + b, 0);
			const keys = Object.keys(units || {}).sort((a, b) => units[b] - units[a]);
			if (keys.length < 2) { d.$body.find('.uod-dd-units').empty(); return; }
			const card = (k, label, v) => `<button class="uod-dd-unit ${state.programme === k ? 'is-on' : ''}" data-p="${this.esc(k)}">
				<span class="uod-dd-unit-name">${label}</span>
				<span class="uod-dd-unit-v"><b>${this.n(v)}</b><small>${this.pct_txt(v, total)}</small></span></button>`;
			d.$body.find('.uod-dd-units').html(card('__all__', __('All programmes'), total)
				+ keys.map(k => card(k, this.esc(this.prog_name(k)), units[k])).join(''));
		};
		const run = (first) => {
			this.server_table(d.$body.find('.uod-dd-table'), kind, Object.assign({}, extra, { programme: state.programme, with_units: first ? 1 : 0 }), {
				export_name: title,
				on_data: (r) => { if (r.units) draw_units(r.units); }
			});
		};
		d.$body.on('click', '.uod-dd-unit', (e) => {
			state.programme = String($(e.currentTarget).data('p'));
			d.$body.find('.uod-dd-unit').removeClass('is-on');
			$(e.currentTarget).addClass('is-on');
			run(false);
		});
		run(true);
		d.show();
	}

	// Server-paged table: search, sort, page size, pager, export all.
	server_table($el, kind, extra = {}, opts = {}) {
		const st = { search: '', sort: opts.sort || null, order: 'desc', page: 1, page_size: opts.page_size || 50 };
		// The same container is re-used on every filter change: drop old handlers first.
		$el.off();
		$el.html(`<div class="uod-tt">
			<div class="uod-tt-tools">
				<div class="uod-search"><input type="search" placeholder="${__('Search name, ID, email…')}"></div>
				<span class="uod-muted uod-tt-count"></span>
				<button class="btn btn-default btn-xs uod-tt-export">⬇ ${__('Export all (CSV)')}</button>
			</div>
			<div class="uod-table-scroll uod-tt-body"></div>
			<div class="uod-tt-pager"></div>
		</div>`);
		const $body = $el.find('.uod-tt-body');
		const args = () => ({ kind, filters: this.filters, extra, search: st.search, sort: st.sort, order: st.order, page: st.page, page_size: st.page_size });
		const fetch = () => {
			$body.addClass('uod-st-loading');
			frappe.xcall(UOD_API + 'get_table', args()).then((r) => {
				$body.removeClass('uod-st-loading');
				st.sort = r.sort; st.order = r.order;
				if (opts.on_data) opts.on_data(r);
				const from = r.total ? (r.page - 1) * r.page_size + 1 : 0;
				const to = Math.min(r.page * r.page_size, r.total);
				$el.find('.uod-tt-count').text(`${__('Rows')} ${this.n(from)}–${this.n(to)} ${__('of')} ${this.n(r.total)}`);
				$body.html(this.table_html(kind, r));
				const pages = Math.max(1, Math.ceil(r.total / r.page_size));
				$el.find('.uod-tt-pager').html(`
					<label class="uod-muted">${__('Rows per page')} <select class="uod-ps">${[25, 50, 100, 250].map(n => `<option ${n === r.page_size ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
					<div class="uod-pages">
						<button class="uod-pg" data-g="1" ${r.page <= 1 ? 'disabled' : ''}>«</button>
						<button class="uod-pg" data-g="${r.page - 1}" ${r.page <= 1 ? 'disabled' : ''}>‹</button>
						<span class="uod-muted">${__('Page')} <b>${this.n(r.page)}</b> ${__('of')} ${this.n(pages)}</span>
						<button class="uod-pg" data-g="${r.page + 1}" ${r.page >= pages ? 'disabled' : ''}>›</button>
						<button class="uod-pg" data-g="${pages}" ${r.page >= pages ? 'disabled' : ''}>»</button>
					</div>`);
			}).catch(() => { $body.removeClass('uod-st-loading'); });
		};
		let timer = null;
		$el.find('.uod-search input').on('input', (e) => {
			clearTimeout(timer);
			timer = setTimeout(() => { st.search = e.target.value; st.page = 1; fetch(); }, 300);
		});
		$el.on('click', 'th[data-sort]', (e) => {
			const f = String($(e.currentTarget).data('sort'));
			st.order = st.sort === f && st.order === 'desc' ? 'asc' : 'desc';
			st.sort = f; st.page = 1;
			fetch();
		});
		$el.on('click', '.uod-pg', (e) => { st.page = Number($(e.currentTarget).data('g')) || 1; fetch(); });
		$el.on('change', '.uod-ps', (e) => { st.page_size = Number(e.target.value) || 50; st.page = 1; fetch(); });
		$el.find('.uod-tt-export').on('click', () => {
			const q = $.param({ kind, filters: JSON.stringify(this.filters), extra: JSON.stringify(extra), search: st.search,
				sort: st.sort || '', order: st.order, name: opts.export_name || kind });
			window.open(`/api/method/${UOD_API}export_table?${q}`);
		});
		$el.on('click', '.uod-person', (e) => {
			if (e.ctrlKey || e.metaKey || e.button === 1) return;
			// Stop here too: Frappe's router follows any desk href that reaches the document.
			e.preventDefault();
			e.stopPropagation();
			const $a = $(e.currentTarget);
			this.open_timeline(String($a.data('k')), String($a.data('id')));
		});
		fetch();
	}

	table_html(kind, r) {
		if (!r.rows.length) return `<div class="uod-empty">${__('Nothing here for these filters.')}</div>`;
		const pkind = kind === 'stu' ? 'stu' : 'app';
		const id_field = { app: 'name', stu: 'name' }[kind];
		const person_link = (k, id, text) => `<a class="uod-idlink uod-person" data-k="${k}" data-id="${this.esc(id)}" href="${this.desk_link(k === 'stu' ? 'Student Master' : 'Applicant', id)}">${this.esc(text || id)}</a>`;
		const head = r.columns.map(c => {
			const arrow = r.sort === c.field ? (r.order === 'asc' ? ' ▲' : ' ▼') : (c.sortable ? ' ↕' : '');
			return `<th ${c.sortable ? `data-sort="${c.field}"` : ''} class="${c.sortable ? 'is-sort' : ''}">${this.esc(c.label)}<span class="uod-arrow">${arrow}</span></th>`;
		}).join('');
		const cell = (row, c) => {
			const v = row[c.field];
			switch (c.type) {
				case 'id': return v ? `<a class="uod-idlink" target="_blank" href="${this.desk_link(r.doctype, v)}">${this.esc(v)} ↗</a>` : '';
				case 'applicant': return v ? person_link('app', v) : '';
				case 'student': return v ? person_link('stu', v) : '';
				case 'person': return id_field && row[id_field] ? `<a class="uod-cand uod-person" data-k="${pkind}" data-id="${this.esc(row[id_field])}" href="#">${this.esc(v || row[id_field])}</a>` : this.esc(v);
				case 'currency': return `<span class="uod-num-cell">${this.esc(this.money(v))}</span>`;
				case 'pct': return v === null || v === undefined ? '' : `<span class="uod-num-cell">${Math.round(Number(v) * 10) / 10}%</span>`;
				case 'check': return Number(v) ? `<span class="uod-pill" style="--c:${UOD_TONES.good}">${__('Yes')}</span>` : `<span class="uod-pill" style="--c:${UOD_TONES.neutral}">${__('No')}</span>`;
				case 'programme': return v ? this.prog_pill(v) : '';
				case 'stage': return this.stage_pill(v);
				case 'date': return this.esc(this.fmt_date(v));
				case 'datetime': return this.esc(this.fmt_dt(v));
				case 'days': return `<span class="uod-days ${v > 30 ? 'is-long' : ''}">${this.n(v)} ${__('days')}</span>`;
				default: return `<span class="uod-trunc" title="${this.esc(v)}">${this.esc(v)}</span>`;
			}
		};
		const body = r.rows.map(row => `<tr>${r.columns.map(c => `<td>${cell(row, c)}</td>`).join('')}</tr>`).join('');
		return `<table class="uod-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
	}

	// ── timeline tab ───────────────────────────────────────────────────────
	render_timeline_tab() {
		const t = this.tl;
		const sel = (key, label, opts, wide = false) => `<label class="uod-tl-tool ${wide ? 'uod-tl-tool-wide' : ''}"><span>${label}</span>
			<select data-k="${key}">${opts.map(([v, l]) => `<option value="${this.esc(v)}" ${String(t[key]) === String(v) ? 'selected' : ''}>${this.esc(l)}</option>`).join('')}</select></label>`;
		const statuses = [['', __('All statuses')]].concat(Object.keys(
			(this.data.status_prog || []).reduce((a, r) => { a[r.status] = 1; return a; }, {})).sort().map(s => [s, s]));
		const tools = t.people === 'app'
			? [sel('people', __('People'), [['app', __('Applicants')], ['stu', __('Students')]]),
				sel('stage', __('Stage'), [['', __('All stages')]].concat(this.meta.stages.map(s => [s.name, s.name]))),
				sel('status', __('Status'), statuses, true),
				sel('pipeline', __('Pipeline'), [['', __('Everyone')], ['open', __('Still in process')], ['ended', __('Ended (enrolled / not admitted)')]]),
				sel('days', __('Days in pipeline'), [['', __('Any')]].concat(UOD_DAY_RANGES))]
			: [sel('people', __('People'), [['app', __('Applicants')], ['stu', __('Students')]])];
		const $tools = this.$root.find('#uod-tl-tools').html(tools.join(''));
		$tools.find('select').on('change', (e) => {
			const k = $(e.currentTarget).data('k');
			t[k] = e.target.value;
			if (k === 'people') { t.stage = ''; t.status = ''; t.pipeline = ''; t.days = ''; }
			this.render_timeline_tab();
		});
		const extra = t.people === 'app' ? { stage: t.stage, status: t.status, pipeline: t.pipeline, days: t.days } : {};
		this.server_table(this.$root.find('#uod-tl-list'), t.people, extra, { export_name: 'timeline' });
	}

	open_timeline(kind, name) {
		const d = new frappe.ui.Dialog({ title: __('Timeline'), size: 'extra-large' });
		d.$wrapper.find('.modal-dialog').addClass('uod-modal-tl');
		d.$body.html(`<style>${UOD_CSS}</style><div class="uod-root uod-in-modal"><div class="uod-empty">${__('Loading…')}</div></div>`);
		d.show();
		frappe.xcall(UOD_API + 'get_timeline', { kind, name }).then((t) => {
			d.$body.find('.uod-root').html(this.timeline_html(t));
			d.$body.on('click', '.uod-tlf', (e) => {
				const k = String($(e.currentTarget).data('k'));
				d.$body.find('.uod-tlf').removeClass('is-on');
				$(e.currentTarget).addClass('is-on');
				d.$body.find('.uod-tli').each((_i, el) => { $(el).toggleClass('is-hidden', k !== 'all' && $(el).data('kind') !== k); });
				d.$body.find('.uod-tlg').each((_i, el) => { $(el).toggleClass('is-hidden', !$(el).find('.uod-tli:not(.is-hidden)').length); });
			});
		}).catch(() => { d.hide(); });
	}

	timeline_html(t) {
		const h = t.head || {};
		const c = UOD_STAGE_COLORS[h.stage] || '#920c24';
		const initial = String(h.name || '?').trim().charAt(0).toUpperCase();
		const ids = [h.applicant ? `<a class="uod-idlink" target="_blank" href="${this.desk_link('Applicant', h.applicant)}">${this.esc(h.applicant)} ↗</a>` : '',
			h.student ? `<a class="uod-idlink" target="_blank" href="${this.desk_link('Student Master', h.student)}">${this.esc(h.student)} ↗</a>` : ''].join(' ');
		const stats = [
			[__('Applied on'), h.applied_on ? this.fmt_date(h.applied_on) : '—', '#920c24'],
			[__('Days in process'), h.days !== undefined ? `${this.n(h.days)} ${__('days')}` : '—', '#A16207'],
			[__('Admission status'), h.status || '—', c],
			[__('Registration'), h.registration_status || '—', h.registration_status === 'Completed' ? '#2F7D4F' : '#6B7A8A']
		].map(([l, v, col]) => `<div style="--c:${col}"><span>${l}</span><b>${this.esc(v)}</b></div>`).join('');
		const journey = (t.journey || []).map(s => `<div class="uod-step ${s.done ? 'is-done' : ''} ${s.bad ? 'is-bad' : ''}">
			<span class="uod-step-dot">${s.bad ? '✕' : s.done ? '✓' : ''}</span><span class="uod-step-l">${this.esc(s.label)}</span></div>`).join('');

		const kinds = {};
		(t.events || []).forEach(e => { kinds[e.kind] = (kinds[e.kind] || 0) + 1; });
		const filt = `<div class="uod-tlp-filter"><button class="uod-tlf is-on" data-k="all">${__('Everything')}<span>${(t.events || []).length}</span></button>
			${Object.keys(kinds).map(k => `<button class="uod-tlf" data-k="${k}" style="--k:${UOD_KIND_COLORS[k] || '#6B7A8A'}"><span class="uod-dot" style="--c:${UOD_KIND_COLORS[k] || '#6B7A8A'}"></span>${this.esc(frappe.utils.to_title_case(k))}<span>${kinds[k]}</span></button>`).join('')}</div>`;

		const groups = {};
		(t.events || []).forEach(e => { (groups[e.when.slice(0, 10)] = groups[e.when.slice(0, 10)] || []).push(e); });
		const today = frappe.datetime.get_today();
		let today_drawn = false;
		const body = Object.keys(groups).sort().map(day => {
			let marker = '';
			if (!today_drawn && day > today) { marker = `<div class="uod-tl-today"><span>${__('Today')}</span></div>`; today_drawn = true; }
			const dt = frappe.datetime.str_to_obj(day);
			const items = groups[day].map(e => {
				const k = UOD_TONES[e.tone] || UOD_KIND_COLORS[e.kind] || '#6B7A8A';
				const time = e.when.length > 10 && e.when.slice(11, 16) !== '00:00' ? e.when.slice(11, 16) : '';
				const flow = e.flow ? `<div class="uod-tli-flow">${e.flow.map(x => `<span class="uod-pill" style="--c:${k}">${this.esc(x)}</span>`).join('<span class="uod-tli-arrow">→</span>')}</div>` : '';
				return `<div class="uod-tli ${day > today ? 'is-future' : ''}" data-kind="${this.esc(e.kind)}" style="--k:${k}">
					<div class="uod-tli-time">${time}</div>
					<div class="uod-tli-card">
						<div class="uod-tli-top"><span class="uod-tli-kind">${this.esc(e.kind)}</span><span class="uod-tli-title">${this.esc(e.title)}</span>
							${e.doctype && e.name ? `<a class="uod-tli-doc" target="_blank" href="${this.desk_link(e.doctype, e.name)}">${this.esc(e.name)} ↗</a>` : ''}</div>
						${flow}${e.meta ? `<div class="uod-tli-meta">${this.esc(e.meta)}</div>` : ''}
					</div></div>`;
			}).join('');
			return `${marker}<div class="uod-tlg"><div class="uod-tlg-date"><b>${dt.getDate()} ${dt.toLocaleString('en', { month: 'short' })}</b><span>${dt.getFullYear()}</span></div>
				<div class="uod-tlg-items">${items}</div></div>`;
		}).join('');

		return `<div class="uod-tlp-head">
				<div class="uod-tlp-who"><div class="uod-tlp-avatar" style="--c:${c}">${this.esc(initial)}</div>
					<div><div class="uod-tlp-name">${this.esc(h.name || '—')} ${ids}</div>
					<div class="uod-tlp-pills">${h.programme ? this.prog_pill(h.programme) : ''}${this.stage_pill(h.stage)}
						${h.cycle ? `<span class="uod-muted">${this.esc(h.cycle)}</span>` : ''}${h.email ? `<span class="uod-muted">${this.esc(h.email)}</span>` : ''}</div></div>
				</div>
			</div>
			<div class="uod-tlp-stats">${stats}</div>
			<div class="uod-journey">${journey}</div>
			${filt}
			<div class="uod-tlp-scroll">${body || `<div class="uod-empty">${__('No dated events recorded yet.')}</div>`}</div>`;
	}

	// ── funnel tab ─────────────────────────────────────────────────────────
	step_counts(program = null) {
		const out = {};
		this.meta.steps.forEach(s => {
			// No status list = every status (Total applications).
			const set = s.statuses ? new Set(s.statuses) : null;
			out[s.key] = (this.data.status_prog || []).filter(r => (!set || set.has(r.status)) && (program === null || r.program === program))
				.reduce((a, r) => a + r.n, 0);
		});
		return out;
	}
	programmes_in_scope() {
		const set = {};
		(this.data.status_prog || []).forEach(r => { set[r.program] = (set[r.program] || 0) + r.n; });
		Object.keys(this.data.stu_by || {}).forEach(p => { if (!(p in set)) set[p] = 0; });
		return Object.keys(set).sort((a, b) => set[b] - set[a]);
	}

	render_funnel_tab(refresh = false) {
		this.render_funbars();
		this.render_fununits();
		this.render_prog();
		this.render_stages();
		this.server_table(this.$root.find('#uod-apps'), 'app', {}, { export_name: 'applications' });
		this.server_table(this.$root.find('#uod-regs'), 'stu', {}, { export_name: 'registrations' });
		this.render_iv('all');
		this.server_table(this.$root.find('#uod-log'), 'audit', {}, {
			export_name: 'admission-log',
			on_data: (r) => { this.$root.find('#uod-log-wrap').toggle(r.total > 0); }
		});
		const $p = this.$root.find('#uod-pipe, #uod-profile, #uod-trend').addClass('uod-st-loading');
		frappe.xcall(UOD_API + 'get_funnel_data', { filters: this.filters, refresh: refresh ? 1 : 0 }).then((f) => {
			this.funnel = f;
			$p.removeClass('uod-st-loading');
			this.render_pipeline();
			this.render_profile();
			this.render_trend();
		}).catch(() => { $p.removeClass('uod-st-loading'); });
	}

	render_funbars() {
		const counts = this.step_counts();
		const total = counts.total || 0;
		let prev = null;
		const rows = this.meta.steps.map(s => {
			const v = counts[s.key];
			const of_prev = prev === null ? '' : `${this.pct_txt(v, prev)} ${__('of previous')}`;
			const lost = prev === null ? '' : `−${this.n(Math.max(prev - v, 0))} ${__('did not reach')}`;
			prev = v;
			return `<div class="uod-fun-row is-click" data-step="${s.key}" tabindex="0" role="button">
				<span class="uod-fun-label">${this.esc(s.label)}</span>
				<span class="uod-fun-track"><span class="uod-fun-bar" style="width:${total ? Math.max((v / total) * 100, v ? 0.6 : 0) : 0}%"></span></span>
				<b class="uod-fun-val">${this.n(v)}</b>
				<span class="uod-fun-pct">${of_prev}</span>
				<span class="uod-fun-pct uod-muted">${this.pct_txt(v, total)} ${__('of all')}</span>
				<span class="uod-fun-lost">${lost}</span>
			</div>`;
		}).join('');
		const $f = this.$root.find('#uod-funbars').html(`<div class="uod-fun">${rows}</div>`);
		this.bind_click($f.find('[data-step]'), (el) => {
			const s = this.meta.steps.find(x => x.key === $(el).data('step'));
			this.drill(s.label, 'app', { step: s.key });
		});
	}

	render_fununits() {
		const steps = this.meta.steps;
		const progs = this.programmes_in_scope();
		const head = `<tr><th>${__('Programme')}</th>${steps.map(s => `<th>${this.esc(s.label)}</th>`).join('')}</tr>`;
		const body = progs.map(p => {
			const c = this.step_counts(p);
			let prev = null;
			return `<tr><td>${this.prog_pill(p)}</td>${steps.map(s => {
				const v = c[s.key];
				const pct = prev === null ? '' : `<small class="uod-muted"> ${this.pct_txt(v, prev)}</small>`;
				prev = v;
				return `<td>${v ? `<a class="uod-num" data-step="${s.key}" data-p="${this.esc(p)}">${this.n(v)}</a>` : '<span class="uod-muted">0</span>'}${pct}</td>`;
			}).join('')}</tr>`;
		}).join('');
		const $t = this.$root.find('#uod-fununits').html(progs.length
			? `<table class="uod-table uod-fun-table"><thead>${head}</thead><tbody>${body}</tbody></table>`
			: `<div class="uod-empty">${__('No applications for these filters.')}</div>`);
		$t.find('.uod-num').on('click', (e) => {
			const $a = $(e.currentTarget);
			const s = steps.find(x => x.key === $a.data('step'));
			this.drill(`${s.label} · ${this.prog_name(String($a.data('p')))}`, 'app', { step: s.key, programme: String($a.data('p')) });
		});
	}

	render_prog() {
		const progs = this.programmes_in_scope();
		const stage_of = {};
		this.meta.stages.forEach(s => s.statuses.forEach(st => { stage_of[st] = s.name; }));
		const reg_done = ((this.data.cards || {}).reg_done || { by: {} }).by;
		const cols = [['apps', __('Applications')]].concat(this.meta.stages.map(s => [s.name, s.name]))
			.concat([['students', __('Student records')], ['registered', __('Registration completed')], ['conv', __('Conversion')]]);
		this.prog_rows = progs.map(p => {
			const row = { programme: this.prog_name(p), key: p, apps: 0, students: (this.data.stu_by || {})[p] || 0, registered: reg_done[p] || 0 };
			this.meta.stages.forEach(s => { row[s.name] = 0; });
			(this.data.status_prog || []).filter(r => r.program === p).forEach(r => {
				row.apps += r.n;
				row[stage_of[r.status] || 'Applying'] += r.n;
			});
			row.conv = this.pct(row['Offer / Admitted'], row.apps);
			return row;
		});
		const head = `<tr><th>${__('Programme')}</th>${cols.map(c => `<th>${this.esc(c[1])}</th>`).join('')}</tr>`;
		const body = this.prog_rows.map(r => `<tr><td>${this.prog_pill(r.key)}</td>${cols.map(([k]) => {
			if (k === 'conv') return `<td><b>${r.conv}%</b></td>`;
			const v = r[k];
			const color = k === 'Not admitted' && v ? `style="color:${UOD_TONES.bad}"` : '';
			return `<td>${v ? `<a class="uod-num" data-k="${this.esc(k)}" data-p="${this.esc(r.key)}" ${color}>${this.n(v)}</a>` : '<span class="uod-muted">0</span>'}</td>`;
		}).join('')}</tr>`).join('');
		const $t = this.$root.find('#uod-prog').html(this.prog_rows.length
			? `<table class="uod-table uod-fun-table"><thead>${head}</thead><tbody>${body}</tbody></table>`
			: `<div class="uod-empty">${__('Nothing for these filters.')}</div>`);
		$t.find('.uod-num').on('click', (e) => {
			const $a = $(e.currentTarget);
			const k = String($a.data('k'));
			const p = String($a.data('p'));
			const title = `${cols.find(c => c[0] === k)[1]} · ${this.prog_name(p)}`;
			if (k === 'apps') this.drill(title, 'app', { programme: p });
			else if (k === 'students') this.drill(title, 'stu', { programme: p });
			else if (k === 'registered') this.drill(title, 'stu', { card: 'reg_done', programme: p });
			else this.drill(title, 'app', { stage: k, programme: p });
		});
		this.$root.find('#uod-export-prog').off('click').on('click', () => {
			this.export_csv('programme-summary', [{ key: 'programme', label: __('Programme') }].concat(cols.map(([k, l]) => ({ key: k, label: l }))), this.prog_rows);
		});
	}

	render_stages() {
		const by = {};
		const stage_of = {};
		this.meta.stages.forEach(s => s.statuses.forEach(st => { stage_of[st] = s.name; }));
		(this.data.status_prog || []).forEach(r => { const s = stage_of[r.status] || 'Applying'; by[s] = (by[s] || 0) + r.n; });
		const total = this.data.app_total;
		const max = Math.max(1, ...Object.values(by));
		const rows = this.meta.stages.map(s => {
			const v = by[s.name] || 0;
			return `<div class="uod-bar-row is-click" data-stage="${this.esc(s.name)}" tabindex="0" role="button">
				<span class="uod-bar-label"><span class="uod-dot" style="--c:${UOD_STAGE_COLORS[s.name]}"></span>${this.esc(s.name)}</span>
				<span class="uod-bar-track"><span class="uod-bar-fill" style="width:${(v / max) * 100}%;background:${UOD_STAGE_COLORS[s.name]}"></span></span>
				<span class="uod-bar-val"><b>${this.n(v)}</b> <small class="uod-muted">${this.pct_txt(v, total)}</small></span></div>`;
		}).join('');
		const $s = this.$root.find('#uod-stages').html(rows);
		this.bind_click($s.find('[data-stage]'), (el) => {
			const s = String($(el).data('stage'));
			this.drill(s, 'app', { stage: s });
		});
	}

	range_tools() {
		return `<div class="uod-panel-tools uod-range">${[['all', __('All')], ['today', __('Today')], ['next7', __('Next 7 days')], ['last7', __('Last 7 days')], ['month', __('This month')]]
			.map(([k, l]) => `<button class="uod-preset uod-rpreset ${k === 'all' ? 'is-on' : ''}" data-r="${k}">${l}</button>`).join('')}</div>`;
	}
	render_iv(range) {
		const today = frappe.datetime.get_today();
		const r = { all: {}, today: { from: today, to: today }, next7: { from: today, to: frappe.datetime.add_days(today, 7) },
			last7: { from: frappe.datetime.add_days(today, -7), to: today }, month: { from: frappe.datetime.month_start(), to: frappe.datetime.month_end() } }[range];
		const $tools = this.$root.find('#uod-iv').closest('.uod-panel').find('.uod-rpreset');
		$tools.each((_i, el) => { $(el).toggleClass('is-on', $(el).data('r') === range); });
		$tools.off('click').on('click', (e) => { this.render_iv(String($(e.currentTarget).data('r'))); });
		this.server_table(this.$root.find('#uod-iv'), 'isa', r, { export_name: 'interviews' });
	}

	render_pipeline() {
		const p = this.funnel.pipeline;
		const o = this.funnel.offers;
		const kpi = (label, v, sub, c, extra) => `<div class="uod-tl-kpi ${extra ? 'is-click' : ''}" style="--c:${c}" ${extra ? `data-x='${this.esc(JSON.stringify(extra))}' tabindex="0" role="button"` : ''}>
			<div class="uod-tl-kpi-top"><span>${label}</span></div><b>${v}</b><small>${sub}</small></div>`;
		const kpis = [
			kpi(__('Average days in pipeline'), `${p.avg_days} ${__('days')}`, `${p.avg_open} ${__('days for those still in it')}`, '#920c24'),
			kpi(__('Still in pipeline'), this.n(p.open), `${this.pct_txt(p.open, p.open + p.ended)} ${__('of these applicants')}`, '#2b4f7e', { pipeline: 'open' }),
			kpi(__('Waiting over 30 days'), this.n(p.over30), __('still in process, 30+ days'), '#B7651B', { pipeline: 'open', days: '31-' }),
			kpi(__('Ended'), this.n(p.ended), __('enrolled or not admitted'), '#6B7A8A', { pipeline: 'ended' })
		].join('');
		const cats = p.buckets.map(b => `${b.label} ${__('days')}`);
		const days_chart = this.svg_bars(cats, [
			{ key: 'open', label: __('Still in pipeline'), color: 'var(--pipe-open)' },
			{ key: 'ended', label: __('Ended'), color: 'var(--pipe-ended)' }
		], p.buckets, { stacked: true, click: (i) => ({ days: UOD_DAY_RANGES[i][0] }) });
		const max_stage = Math.max(1, ...p.by_stage.map(s => s.avg));
		const stage_bars = p.by_stage.map(s => `<div class="uod-bar-row is-click" data-stage="${this.esc(s.stage)}" tabindex="0" role="button">
			<span class="uod-bar-label"><span class="uod-dot" style="--c:${UOD_STAGE_COLORS[s.stage]}"></span>${this.esc(s.stage)}</span>
			<span class="uod-bar-track"><span class="uod-bar-fill" style="width:${(s.avg / max_stage) * 100}%;background:${UOD_STAGE_COLORS[s.stage]}"></span></span>
			<span class="uod-bar-val"><b>${s.avg} ${__('days')}</b> <small class="uod-muted">${__('avg')} · ${this.n(s.n)} ${__('applicants')}</small></span></div>`).join('');

		const progs = Object.keys(o.by_programme).sort();
		const statuses = ['Issued', 'Accepted', 'Confirmation Fee Paid', 'Full Fee Paid', 'Rejected', 'Expired', 'Withdrawn'];
		const st_colors = { 'Issued': '#8a5a00', 'Accepted': '#2b4f7e', 'Confirmation Fee Paid': '#0D9488', 'Full Fee Paid': '#2F7D4F',
			'Rejected': '#B83232', 'Expired': '#8A96A3', 'Withdrawn': '#6B7A8A' };
		const used = statuses.filter(s => progs.some(pg => o.by_programme[pg][s]));
		const per_prog = this.svg_bars(progs.map(pg => this.prog_name(pg)), [{ key: 'n', label: __('Offers'), color: '#920c24' }],
			progs.map(pg => ({ n: Object.values(o.by_programme[pg]).reduce((a, b) => a + b, 0) })), {});
		const by_status = this.svg_bars(progs.map(pg => this.prog_name(pg)), used.map(s => ({ key: s, label: s, color: st_colors[s] })),
			progs.map(pg => o.by_programme[pg]), {});
		const g_keys = Array.from(new Set([].concat(...Object.values(o.gender || {}).map(x => Object.keys(x))))).sort();
		const g_colors = ['#7C3AED', '#0891B2', '#B7791F', '#8A96A3'];
		const gprogs = Object.keys(o.gender || {}).sort();
		const gender = this.svg_bars(gprogs.map(pg => this.prog_name(pg)), g_keys.map((g, i) => ({ key: g, label: g || __('Not set'), color: g_colors[i % g_colors.length] })),
			gprogs.map(pg => o.gender[pg]), {});
		const mprogs = Object.keys(o.median_days || {}).sort();
		const med = this.svg_dots(mprogs.map(pg => this.prog_name(pg)), mprogs.map(pg => o.median_days[pg]));
		const chart = (title, sub, body, legend = '') => `<div class="uod-tl-chart"><div class="uod-tl-chart-head"><div>
			<div class="uod-tl-chart-title">${title}</div><div class="uod-panel-sub">${sub}</div></div>${legend}</div>${body}</div>`;
		const legend = (items) => `<div class="uod-legend">${items.map(([l, c]) => `<span><i style="background:${c}"></i>${this.esc(l)}</span>`).join('')}</div>`;

		const $p = this.$root.find('#uod-pipe').html(`
			<div class="uod-tl-kpis">${kpis}</div>
			<div class="uod-grid-2">
				${chart(__('Days in pipeline'), __('How long applicants have been in the process · click a column for its list'), days_chart,
					legend([[__('Still in pipeline'), 'var(--pipe-open)'], [__('Ended'), 'var(--pipe-ended)']]))}
				${chart(__('Average days by current stage'), __('Where the time goes · click a stage for its list'), `<div class="uod-bars">${stage_bars}</div>`)}
			</div>
			<div class="uod-offers-head"><div class="uod-tl-chart-title">${__('Offer update')}</div>
				<div class="uod-panel-sub">${this.n(o.total)} ${__('offer letters issued to applicants within the filters above')}</div></div>
			<div class="uod-grid-2">
				${chart(__('Number of offers'), __('Per programme'), per_prog)}
				${chart(__('Offer status'), __('Where each offer stands now'), by_status, legend(used.map(s => [s, st_colors[s]])))}
				${chart(__('Gender'), __('Of the applicants who reached the offer step'), gender, legend(g_keys.map((g, i) => [g || __('Not set'), g_colors[i % g_colors.length]])))}
				${chart(__('Median days to offer'), __('From application to offer letter, per programme'), med)}
			</div>`);
		this.bind_click($p.find('.uod-tl-kpi.is-click'), (el) => {
			const x = JSON.parse($(el).attr('data-x'));
			this.drill($(el).find('span').first().text(), 'app', x);
		});
		this.bind_click($p.find('[data-stage]'), (el) => { const s = String($(el).data('stage')); this.drill(s, 'app', { stage: s }); });
		this.bind_svg_clicks($p, 'app', __('Days in pipeline'));
	}

	render_profile() {
		const f = this.funnel;
		const donut_chart = (title, field, data) => {
			const items = Object.keys(data).sort((a, b) => data[b] - data[a]).map((k, i) => ({ key: k, label: k || __('Not given'), value: data[k], color: UOD_PALETTE[i % UOD_PALETTE.length] }));
			return `<div class="uod-tl-chart"><div class="uod-tl-chart-title">${title}</div>${this.svg_donut(items, field)}</div>`;
		};
		const st = Object.keys(f.state).sort((a, b) => f.state[b] - f.state[a]).slice(0, 12);
		const max = Math.max(1, ...st.map(k => f.state[k]));
		const states = st.map(k => `<div class="uod-bar-row is-click" data-field="state" data-value="${this.esc(k)}" tabindex="0" role="button">
			<span class="uod-bar-label">${this.esc(k || __('Not given'))}</span>
			<span class="uod-bar-track"><span class="uod-bar-fill" style="width:${(f.state[k] / max) * 100}%"></span></span>
			<span class="uod-bar-val"><b>${this.n(f.state[k])}</b></span></div>`).join('');
		const $p = this.$root.find('#uod-profile').html(`<div class="uod-grid-2">
			${donut_chart(__('Category'), 'whether_scstobc_ncl', f.category)}
			${donut_chart(__('Gender'), 'gender', f.gender)}
			${donut_chart(__('Source of information'), 'source_of_information', f.source)}
			<div class="uod-tl-chart"><div class="uod-tl-chart-title">${__('State')} <small class="uod-muted">${__('top 12')}</small></div><div class="uod-bars">${states || `<div class="uod-empty">${__('No data')}</div>`}</div></div>
		</div>`);
		this.bind_click($p.find('[data-field]'), (el) => {
			const $e = $(el);
			this.drill(`${$e.closest('.uod-tl-chart').find('.uod-tl-chart-title').first().text()}: ${$e.data('value') || __('Not given')}`, 'app',
				{ field: String($e.data('field')), value: String($e.data('value') || '') });
		});
	}

	render_trend() {
		const w = this.funnel.weeks || [];
		const cats = w.map(x => frappe.datetime.str_to_user(x.week).slice(0, 5));
		const $t = this.$root.find('#uod-trend').html(w.length
			? this.svg_bars(cats, [{ key: 'n', label: __('Applications'), color: '#920c24' }], w, { click: (i) => ({ week: w[i].week }), compact: true })
			: `<div class="uod-empty">${__('No applications for these filters.')}</div>`);
		this.bind_svg_clicks($t, 'app', __('Applications in week'));
	}

	bind_svg_clicks($scope, kind, title) {
		$scope.find('[data-x]').filter('g, rect').on('click', (e) => {
			const x = JSON.parse($(e.currentTarget).attr('data-x'));
			this.drill(`${title} · ${$(e.currentTarget).attr('data-cat')}`, kind, x);
		});
	}

	// ── SVG charts (no chart library: crisp in both themes, never redraws on resize) ──
	svg_bars(cats, series, rows, opts = {}) {
		if (!cats.length) return `<div class="uod-empty">${__('No data')}</div>`;
		const W = 560, H = opts.compact ? 200 : 230, L = 36, B = 34, T = 18;
		const totals = rows.map(r => series.reduce((a, s) => a + (r[s.key] || 0), 0));
		const max = Math.max(1, ...(opts.stacked ? totals : rows.map(r => Math.max(0, ...series.map(s => r[s.key] || 0)))));
		const nice = Math.pow(10, Math.floor(Math.log10(max)));
		const top = Math.ceil(max / nice) * nice || 1;
		const step = (W - L - 8) / cats.length;
		const bw = Math.min(46, step * 0.7);
		const y = (v) => T + (H - T - B) * (1 - v / top);
		let g = '';
		[0, 0.5, 1].forEach(f => {
			const v = Math.round(top * f);
			g += `<line x1="${L}" x2="${W}" y1="${y(v)}" y2="${y(v)}" class="uod-grid"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" class="uod-axis">${this.n(v)}</text>`;
		});
		cats.forEach((c, i) => {
			const x0 = L + i * step + (step - bw) / 2;
			const x_attr = opts.click ? `data-x='${this.esc(JSON.stringify(opts.click(i)))}' data-cat="${this.esc(c)}" class="uod-bar-g is-click"` : 'class="uod-bar-g"';
			let bars = '';
			if (opts.stacked) {
				let acc = 0;
				series.forEach(s => {
					const v = rows[i][s.key] || 0;
					if (!v) return;
					bars += `<rect x="${x0}" y="${y(acc + v)}" width="${bw}" height="${y(acc) - y(acc + v)}" fill="${s.color}" rx="2" data-tip="${this.esc(`${c} · ${s.label}: ${this.n(v)}`)}"/>`;
					acc += v;
				});
				bars += `<text x="${x0 + bw / 2}" y="${y(totals[i]) - 5}" text-anchor="middle" class="uod-axis-v">${totals[i] ? this.n(totals[i]) : ''}</text>`;
			} else {
				const sw = bw / series.length;
				series.forEach((s, j) => {
					const v = rows[i][s.key] || 0;
					bars += `<rect x="${x0 + j * sw}" y="${y(v)}" width="${Math.max(sw - 2, 2)}" height="${Math.max(y(0) - y(v), 0)}" fill="${s.color}" rx="2" data-tip="${this.esc(`${c} · ${s.label}: ${this.n(v)}`)}"/>`;
					if (v && series.length <= 2 && !opts.compact) bars += `<text x="${x0 + j * sw + (sw - 2) / 2}" y="${y(v) - 5}" text-anchor="middle" class="uod-axis-v">${this.n(v)}</text>`;
				});
			}
			const label = cats.length > 14 && i % Math.ceil(cats.length / 14) ? '' : c;
			g += `<g ${x_attr}><rect x="${L + i * step}" y="${T}" width="${step}" height="${H - T - B}" fill="transparent"/>${bars}
				<text x="${x0 + bw / 2}" y="${H - B + 16}" text-anchor="middle" class="uod-axis">${this.esc(String(label).slice(0, 16))}</text></g>`;
		});
		return `<svg class="uod-svg" viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
	}

	svg_dots(cats, vals) {
		if (!cats.length) return `<div class="uod-empty">${__('No offers with an issue date yet.')}</div>`;
		const W = 560, H = 200, L = 36, B = 34, T = 18;
		const top = Math.max(1, ...vals) * 1.15;
		const step = (W - L - 8) / cats.length;
		const y = (v) => T + (H - T - B) * (1 - v / top);
		let g = `<line x1="${L}" x2="${W}" y1="${y(0)}" y2="${y(0)}" class="uod-grid"/>`;
		cats.forEach((c, i) => {
			const x = L + i * step + step / 2;
			g += `<line x1="${x}" x2="${x}" y1="${y(0)}" y2="${y(vals[i])}" stroke="#920c24" stroke-dasharray="2 3"/>
				<circle cx="${x}" cy="${y(vals[i])}" r="5" fill="#920c24" data-tip="${this.esc(`${c}: ${vals[i]} ${__('days')}`)}"/>
				<text x="${x}" y="${y(vals[i]) - 10}" text-anchor="middle" class="uod-axis-v">${vals[i]}</text>
				<text x="${x}" y="${H - B + 16}" text-anchor="middle" class="uod-axis">${this.esc(String(c).slice(0, 16))}</text>`;
		});
		return `<svg class="uod-svg" viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
	}

	svg_donut(items, field) {
		const total = items.reduce((a, b) => a + b.value, 0);
		if (!total) return `<div class="uod-empty">${__('No data')}</div>`;
		const R = 70, r = 44, C = 85;
		let a0 = -Math.PI / 2;
		const arc = (a1) => {
			const p = (rad, a) => `${C + rad * Math.cos(a)} ${C + rad * Math.sin(a)}`;
			const large = a1 - a0 > Math.PI ? 1 : 0;
			const d = `M ${p(R, a0)} A ${R} ${R} 0 ${large} 1 ${p(R, a1)} L ${p(r, a1)} A ${r} ${r} 0 ${large} 0 ${p(r, a0)} Z`;
			a0 = a1;
			return d;
		};
		const slices = items.map(it => {
			const a1 = a0 + (it.value / total) * Math.PI * 2 - (items.length === 1 ? 0.0001 : 0);
			return `<path class="uod-slice is-click" d="${arc(a1)}" fill="${it.color}" data-field="${field}" data-value="${this.esc(it.key)}"
				data-tip="${this.esc(`${it.label}: ${this.n(it.value)} (${this.pct_txt(it.value, total)})`)}"/>`;
		}).join('');
		const legend = items.slice(0, 8).map(it => `<div class="is-click" data-field="${field}" data-value="${this.esc(it.key)}"><i style="background:${it.color}"></i>
			<span class="lbl">${this.esc(it.label)}</span><b>${this.n(it.value)}</b><span class="uod-muted">${this.pct_txt(it.value, total)}</span></div>`).join('');
		return `<div class="uod-donut"><svg class="uod-donut-svg" viewBox="0 0 170 170">${slices}
			<text x="${C}" y="${C + 7}" text-anchor="middle" class="uod-donut-total">${this.n(total)}</text></svg>
			<div class="uod-donut-legend">${legend}</div></div>`;
	}

	bind_tip($scope) {
		const $tip = () => this.$root.find('#uod-tip');
		$scope.on('mousemove', '[data-tip]', (e) => {
			const t = $(e.currentTarget).attr('data-tip');
			$tip().text(t).css({ left: e.clientX + 14, top: e.clientY + 14 }).addClass('is-on');
		});
		$scope.on('mouseleave', '[data-tip]', () => { $tip().removeClass('is-on'); });
	}

	export_csv(name, columns, rows) {
		const q = (v) => `"${String(v === null || v === undefined ? '' : v).replace(/"/g, '""')}"`;
		const csv = [columns.map(c => q(c.label)).join(',')].concat(rows.map(r => columns.map(c => q(r[c.key])).join(','))).join('\n');
		const a = document.createElement('a');
		a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
		a.download = `${name}-${frappe.datetime.get_today()}.csv`;
		a.click();
		setTimeout(() => { URL.revokeObjectURL(a.href); }, 1000);
	}

	// ── card guide ─────────────────────────────────────────────────────────
	open_guide() {
		const d = new frappe.ui.Dialog({ title: __('Card guide — what each number means'), size: 'extra-large' });
		const row = (c) => `<tr><th>${this.esc(c.label)}</th><td>${this.esc(c.guide || '')}</td></tr>`;
		const sections = [`<div class="uod-guide-sec">${__('Headline')}</div><table class="uod-guide">${this.meta.headline.map(row).join('')}</table>`]
			.concat(this.meta.board.map(s => {
				const kinds = Array.from(new Set([].concat(...s.tiles.map(t => t.cards.map(c => c.kind)))));
				const notes = kinds.map(k => {
					const src = this.meta.sources[k] || {};
					return `${this.esc(src.label || k)}: ${(src.honours || []).length ? this.esc(src.honours.join(', ')) : __('no filters (always everything you can see)')}`;
				}).join(' · ');
				return `<div class="uod-guide-sec">${this.esc(s.title)}</div><div class="uod-muted uod-guide-note">${__('Filters that apply')} — ${notes}</div>
				<table class="uod-guide">${s.tiles.map(t => t.cards.map(row).join('')).join('')}</table>`;
			}));
		d.$body.html(`<style>${UOD_CSS}</style><div class="uod-root uod-in-modal">
			<p class="uod-muted">${__('Every card counts records that are in that state <b>right now</b>, for the filters you applied, and only records you are allowed to see. Each module responds to the filters that exist on its records — listed under each section below. Cards marked "any date" are backlogs and ignore the date range. Click any number to open the list behind it; click a person for their timeline.')}</p>
			${sections.join('')}</div>`);
		d.show();
	}
}

const UOD_CSS = `
.uod-root { --page:#f0f2f5; --bg:#ffffff; --bg-soft:#f8fafc; --border:#e2e8f0; --border-soft:#edf0f4; --text:#1f1a17;
	--text-2:#3b342f; --muted:#57504a; --head:#7a0a1e; --link:#920c24; --hover:#fbf1f3; --grid:#e8e4e0;
	--brand:#920c24; --brand-tint:#fbf1f3; --shadow:0 1px 2px rgba(31,26,23,.05), 0 2px 8px rgba(31,26,23,.04);
	--pipe-open:#920c24; --pipe-ended:#e7b3bd; --font:"Merriweather", Georgia, "Times New Roman", serif;
	color:var(--text); padding:18px 22px 48px; background:var(--page); min-height:100%; transition:opacity .15s; font-family:var(--font); }
:root[data-theme="dark"] .uod-root { --page:#151312; --bg:#1f1c1a; --bg-soft:#252220; --border:#35302d; --border-soft:#2c2826;
	--text:#f2eeea; --text-2:#d4cdc7; --muted:#a79f98; --head:#4d232b; --link:#f07a8e; --hover:#2a2220; --grid:#35302d;
	--brand:#f07a8e; --brand-tint:#3a1c22; --shadow:none; --pipe-open:#f07a8e; --pipe-ended:#5a2a33; }
.uod-root button, .uod-root input, .uod-root select, .uod-root table { font-family:var(--font); }
.modal-dialog.uod-modal .modal-title, .modal-dialog.uod-modal-tl .modal-title { font-family:"Merriweather", Georgia, serif; }
.uod-root.uod-in-modal { padding:0; background:transparent; min-height:0; }
.uod-root.uod-loading { opacity:.6; }
.uod-muted { color:var(--muted); font-size:12px; }
.uod-tabs { display:flex; gap:2px; margin-bottom:12px; border-bottom:1px solid var(--border); }
.uod-tab { background:none; border:0; border-bottom:2px solid transparent; margin-bottom:-1px; padding:7px 16px; font-size:13px; font-weight:600; color:var(--muted); cursor:pointer; }
.uod-tab:hover { color:var(--text); }
.uod-tab.is-on { color:var(--brand); border-bottom-color:var(--brand); }
.uod-pane[hidden] { display:none !important; }
.uod-filters { background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:12px 16px 14px; margin-bottom:16px; box-shadow:var(--shadow); }
.uod-topbar { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap; }
.uod-topbar-right { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.uod-topbar-right b { color:var(--text); }
.uod-presets { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; }
.uod-preset { border:1px solid var(--border); background:var(--bg-soft); color:var(--text-2); border-radius:20px; padding:3px 12px; font-size:12px; font-weight:600; cursor:pointer; }
.uod-preset:hover { border-color:var(--brand); color:var(--brand); }
.uod-preset.is-on { background:var(--brand); border-color:var(--brand); color:#fff; }
:root[data-theme="dark"] .uod-preset.is-on, :root[data-theme="dark"] #uod-apply { color:#1f1a17; }
.uod-filter-row { display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; }
.uod-f { display:flex; flex-direction:column; gap:3px; }
.uod-f label { font-size:10.5px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin:0; }
.uod-f input[type=date] { height:32px; border:1px solid var(--border); border-radius:8px; padding:0 8px; font-size:12.5px; background:var(--bg); color:var(--text); }
.uod-f-btns { flex-direction:row; gap:6px; margin-left:auto; align-self:flex-end; }
#uod-apply { background:var(--brand); border-color:var(--brand); color:#fff; }
.uod-ms { position:relative; }
/* Wide screens: one row, the multi-selects share the free width. Narrower: wrap. */
@media (min-width:1251px) { .uod-filter-row { flex-wrap:nowrap; } .uod-f:has(.uod-ms) { flex:1 1 0; min-width:0; } }
@media (max-width:1250px) { .uod-ms { width:160px; } }
@media (max-width:700px) { .uod-f:has(.uod-ms), .uod-f:has(input[type=date]) { flex:1 1 calc(50% - 10px); min-width:0; } .uod-ms, .uod-f input[type=date] { width:100%; }
	.uod-jump { position:static; } }
.uod-ms-box { display:flex; flex-wrap:wrap; align-items:center; overflow:hidden; gap:4px; padding:3px 8px; border:1px solid var(--border); border-radius:8px; background:var(--bg); cursor:pointer; min-height:32px; }
.uod-ms.open .uod-ms-box { border-color:var(--brand); box-shadow:0 0 0 3px color-mix(in srgb, var(--brand) 18%, transparent); }
.uod-ms-ph { font-size:12.5px; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; }
.uod-ms-chip { display:inline-flex; align-items:center; gap:4px; background:color-mix(in srgb, var(--brand) 12%, transparent); color:var(--text-2); border-radius:6px; padding:1px 5px 1px 7px; font-size:11px; font-weight:600; max-width:120px; }
.uod-ms-chip .txt { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uod-ms-chip .x { cursor:pointer; opacity:.7; }
.uod-ms-more { font-size:11px; color:var(--muted); font-weight:600; }
.uod-ms-panel { display:none; position:absolute; top:calc(100% + 4px); left:0; z-index:60; background:var(--bg); border:1px solid var(--border); border-radius:10px;
	box-shadow:0 10px 24px -8px rgba(16,24,40,.25); width:max(100%,270px); max-width:min(360px,90vw); max-height:300px; overflow-y:auto; }
.uod-ms.open .uod-ms-panel { display:block; }
.uod-ms-search { position:sticky; top:0; background:var(--bg); padding:6px; border-bottom:1px solid var(--border-soft); }
.uod-ms-search input { width:100%; padding:5px 8px; border:1px solid var(--border); border-radius:6px; font-size:12px; background:var(--bg); color:var(--text); }
.uod-ms-actions { display:flex; justify-content:space-between; padding:5px 8px; border-bottom:1px solid var(--border-soft); font-size:11px; }
.uod-ms-actions a { color:var(--link); cursor:pointer; font-weight:600; }
.uod-ms-opt { display:flex; gap:8px; padding:6px 10px; font-size:12px; cursor:pointer; margin:0; font-weight:400; color:var(--text); }
.uod-ms-opt:hover { background:var(--hover); }
.uod-ms-empty, .uod-empty { padding:14px; font-size:12px; color:var(--muted); text-align:center; }
/* cards */
.uod-cards { margin-bottom:18px; }
.uod-headline { display:grid; grid-template-columns:repeat(6, minmax(0,1fr)); gap:12px; }
.uod-headline.is-funnel { column-gap:18px; }
.uod-headline.is-funnel .uod-kpi:not(:last-child)::after { content:'›'; position:absolute; right:-14px; top:30px; width:10px; text-align:center; font-size:20px; line-height:1; color:var(--muted); pointer-events:none; }
.uod-headline.is-funnel .uod-kpi:has(+ .is-aside)::after { display:none; }
.uod-kpi, .uod-tile { position:relative; background:var(--bg); border:1px solid var(--border); border-radius:8px; box-shadow:var(--shadow); min-width:0; }
.uod-kpi { padding:14px 16px 12px; display:flex; flex-direction:column; gap:6px; }
.uod-kpi.is-click, .uod-half.is-click, .uod-tile-1.is-click { cursor:pointer; }
.uod-kpi.is-click:hover, .uod-tile-1.is-click:hover { border-color:color-mix(in srgb, var(--brand) 45%, var(--border)); }
.uod-kpi:focus-visible, .uod-half:focus-visible, .uod-tile-1:focus-visible { outline:none; box-shadow:0 0 0 2px var(--brand); }
.uod-kpi-top, .uod-tile-head { display:flex; align-items:center; justify-content:space-between; gap:8px; min-width:0; }
.uod-kpi-label, .uod-tile-title { font-size:13.5px; font-weight:650; color:var(--text); display:flex; align-items:center; min-width:0; line-height:1.3; }
.uod-kpi-value { font-size:28px; font-weight:700; letter-spacing:-.02em; line-height:1.15; color:var(--text); font-variant-numeric:tabular-nums; display:flex; align-items:center; }
.uod-share { font-size:11.5px; font-weight:600; color:var(--text-2); background:var(--bg-soft); border:1px solid var(--border); border-radius:20px; padding:1px 8px; margin-left:10px; letter-spacing:0; }
.uod-kpi-sub { font-size:12px; color:var(--muted); }
.uod-dot { display:inline-block; flex:none; width:8px; height:8px; border-radius:50%; background:var(--c); margin-right:7px; }
.uod-info { flex:none; display:inline-grid; place-items:center; width:16px; height:16px; border-radius:50%; border:1px solid var(--border); color:var(--muted); font-size:10px; font-style:italic; font-family:Georgia, serif; cursor:help; }
.uod-section { margin-top:22px; }
.uod-section-title { display:flex; align-items:center; gap:10px; font-size:11px; font-weight:700; color:var(--text-2); text-transform:uppercase; letter-spacing:.06em; margin:0 2px 10px; }
.uod-section-title::after { content:''; flex:1; border-top:1px solid var(--border); }
.uod-section-note { text-transform:none; letter-spacing:0; font-weight:500; color:var(--muted); order:2; }
.uod-tiles { display:grid; grid-template-columns:repeat(6, minmax(0,1fr)); gap:12px; }
.uod-tile { padding:14px 16px 12px; display:flex; flex-direction:column; gap:6px; }
.uod-tile-2 { grid-column:span 2; }
.uod-halves { display:grid; grid-template-columns:1fr 1fr; gap:0; }
.uod-half { padding:2px 10px 2px 0; border-radius:6px; display:flex; flex-direction:column; gap:4px; min-width:0; }
.uod-half + .uod-half { border-left:1px solid var(--border-soft); padding-left:18px; }
.uod-half.is-click:hover .uod-kpi-value { color:var(--link) !important; }
/* Block (not flex) so a long label wraps as text and keeps its dot on the first line. */
.uod-half-label { font-size:12.5px; font-weight:600; color:var(--text); display:block; line-height:1.35; }
.uod-half-label .uod-dot { vertical-align:1px; }
.uod-half-label .uod-flag { display:inline-block; vertical-align:1px; }
.uod-flag { margin-left:6px; font-size:9.5px; font-weight:700; color:#B7651B; border:1px solid #B7651B; border-radius:3px; padding:0 4px; text-transform:uppercase; letter-spacing:.04em; }
@media (max-width:1250px) { .uod-headline, .uod-tiles { grid-template-columns:repeat(3, minmax(0,1fr)); } .uod-headline.is-funnel .uod-kpi::after { display:none; } }
@media (max-width:700px) { .uod-headline, .uod-tiles { grid-template-columns:repeat(2, minmax(0,1fr)); } .uod-tile-2 { grid-column:span 2; } .uod-root { padding:12px 16px 40px; } }
/* panels & tables */
.uod-panel { background:var(--bg); border:1px solid var(--border); border-radius:10px; box-shadow:var(--shadow); margin-bottom:16px; min-width:0; }
.uod-panel-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; padding:12px 14px; border-bottom:1px solid var(--border-soft); }
.uod-panel-title { font-size:14px; font-weight:700; color:var(--text); }
.uod-panel-sub { font-size:11.5px; color:var(--muted); margin-top:2px; }
.uod-panel-body { padding:14px; transition:opacity .15s; }
.uod-panel-tools { display:flex; gap:6px; flex-wrap:wrap; }
.uod-st-loading { opacity:.55; }
.uod-grid-2 { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:12px; }
.uod-grid-2 > .uod-panel { margin-bottom:16px; }
@media (max-width:900px) { .uod-grid-2 { grid-template-columns:minmax(0,1fr); } }
.uod-table-scroll { overflow-x:auto; position:relative; }
.uod-table { width:100%; border-collapse:collapse; font-size:12.5px; }
.uod-table th { background:var(--head); color:#fff; font-weight:600; text-align:left; padding:8px 10px; white-space:nowrap; position:sticky; top:0; }
.uod-table th.is-sort { cursor:pointer; }
.uod-arrow { opacity:.7; font-size:10px; }
.uod-table td { padding:8px 10px; border-bottom:1px solid var(--border-soft); color:var(--text); vertical-align:middle; white-space:nowrap; }
.uod-table tbody tr:hover td { background:var(--hover); }
.uod-trunc { display:inline-block; max-width:240px; overflow:hidden; text-overflow:ellipsis; vertical-align:bottom; }
.uod-idlink, .uod-cand, .uod-num { color:var(--link); font-weight:600; cursor:pointer; text-decoration:underline; text-decoration-color:color-mix(in srgb, var(--link) 35%, transparent); text-underline-offset:3px; }
.uod-pill { display:inline-block; font-size:11px; font-weight:600; color:color-mix(in srgb, var(--c) 80%, #000); background:color-mix(in srgb, var(--c) 12%, transparent);
	border:1px solid color-mix(in srgb, var(--c) 35%, transparent); border-radius:20px; padding:1px 8px; white-space:nowrap; }
:root[data-theme="dark"] .uod-pill { color:color-mix(in srgb, var(--c) 60%, #fff); }
.uod-days { font-weight:600; font-variant-numeric:tabular-nums; }
.uod-days.is-long { color:#B7651B; }
.uod-tt-tools { display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 14px; }
.uod-search { flex:0 1 380px; }
.uod-search input { width:100%; height:34px; border:1px solid var(--border); border-radius:8px; padding:0 10px; font-size:12.5px; background:var(--bg); color:var(--text); }
.uod-tt-export { margin-left:auto; }
.uod-tt-pager { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 14px; }
.uod-tt-pager select { margin-left:6px; height:28px; border:1px solid var(--border); border-radius:6px; background:var(--bg); color:var(--text); }
.uod-pages { display:flex; align-items:center; gap:4px; }
.uod-pg { border:1px solid var(--border); background:var(--bg); color:var(--text); border-radius:6px; min-width:28px; height:28px; cursor:pointer; }
.uod-pg:disabled { opacity:.4; cursor:default; }
/* funnel */
.uod-fun { display:flex; flex-direction:column; gap:2px; }
.uod-fun-row { display:grid; grid-template-columns:170px minmax(0,1fr) 80px 120px 90px 150px; align-items:center; gap:12px; padding:6px; border-radius:6px; font-size:12.5px; }
.uod-fun-row.is-click { cursor:pointer; }
.uod-fun-row.is-click:hover { background:var(--hover); }
.uod-fun-label { font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.uod-fun-track, .uod-bar-track { height:18px; background:var(--border-soft); border-radius:0 4px 4px 0; overflow:hidden; display:block; }
.uod-fun-bar, .uod-bar-fill { display:block; height:100%; background:var(--brand); border-radius:0 4px 4px 0; }
.uod-fun-val { text-align:right; font-variant-numeric:tabular-nums; }
.uod-fun-pct, .uod-fun-lost { white-space:nowrap; font-variant-numeric:tabular-nums; }
.uod-fun-lost { font-size:11.5px; color:var(--muted); }
@media (max-width:900px) { .uod-fun-row { grid-template-columns:110px minmax(0,1fr) 64px; } .uod-fun-pct, .uod-fun-lost { grid-column:2 / -1; } }
.uod-fun-table td { white-space:nowrap; }
.uod-bars { display:flex; flex-direction:column; gap:4px; }
.uod-bar-row { display:grid; grid-template-columns:150px minmax(0,1fr) 170px; align-items:center; gap:10px; padding:5px 6px; border-radius:6px; font-size:12.5px; }
.uod-bar-row.is-click { cursor:pointer; }
.uod-bar-row.is-click:hover { background:var(--hover); }
.uod-bar-label { display:flex; align-items:center; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.uod-bar-val { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
@media (max-width:600px) { .uod-bar-row { grid-template-columns:100px minmax(0,1fr); } .uod-bar-val { grid-column:1 / -1; text-align:left; } }
.uod-tl-kpis { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; margin-bottom:12px; }
.uod-tl-kpi { border:1px solid var(--border); border-top:3px solid var(--c); border-radius:8px; padding:10px 12px; background:var(--bg); display:flex; flex-direction:column; gap:2px; min-width:0; }
.uod-tl-kpi.is-click { cursor:pointer; }
.uod-tl-kpi.is-click:hover { background:var(--hover); }
.uod-tl-kpi-top span { font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
.uod-tl-kpi b { font-size:22px; color:var(--text); font-variant-numeric:tabular-nums; }
.uod-tl-kpi small { font-size:11.5px; color:var(--muted); }
@media (max-width:900px) { .uod-tl-kpis { grid-template-columns:repeat(2, minmax(0,1fr)); } }
.uod-tl-chart { border:1px solid var(--border); border-radius:8px; padding:12px 14px; background:var(--bg); min-width:0; }
.uod-tl-chart-head { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap; margin-bottom:8px; }
.uod-tl-chart-title { font-size:13.5px; font-weight:700; color:var(--text); margin-bottom:6px; }
.uod-offers-head { margin:16px 2px 10px; }
.uod-legend { display:flex; gap:12px; flex-wrap:wrap; font-size:11.5px; color:var(--text-2); }
.uod-legend span { display:inline-flex; align-items:center; gap:5px; white-space:nowrap; }
.uod-legend i { display:inline-block; width:10px; height:10px; border-radius:2px; }
.uod-svg { display:block; width:100%; height:auto; }
.uod-svg .uod-grid { stroke:var(--grid); }
.uod-svg .uod-axis { fill:var(--muted); font-size:11px; }
.uod-svg .uod-axis-v { fill:var(--text-2); font-size:11px; font-weight:600; }
.uod-svg .is-click { cursor:pointer; }
.uod-svg .is-click:hover > rect:first-child { fill:var(--hover); }
.uod-donut { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
.uod-donut-svg { width:170px; height:170px; flex:none; }
.uod-slice { cursor:pointer; }
.uod-slice:hover { opacity:.85; }
.uod-donut-total { font-size:20px; font-weight:700; fill:var(--text); }
.uod-donut-legend { flex:1; min-width:150px; display:flex; flex-direction:column; gap:6px; font-size:12px; color:var(--text-2); }
.uod-donut-legend > div { display:grid; grid-template-columns:10px minmax(0,1fr) auto 42px; align-items:center; gap:8px; cursor:pointer; border-radius:4px; }
.uod-donut-legend > div:hover { background:var(--hover); }
.uod-donut-legend i { width:10px; height:10px; border-radius:2px; }
.uod-donut-legend .lbl { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uod-donut-legend b { color:var(--text); font-variant-numeric:tabular-nums; }
.uod-donut-legend .uod-muted { text-align:right; }
.uod-tip { position:fixed; z-index:1100; pointer-events:none; background:#1A2B3C; color:#fff; font-size:12px; padding:5px 9px; border-radius:6px; opacity:0; transition:opacity .1s; max-width:320px; white-space:pre-line; }
.uod-tip.is-on { opacity:1; }
/* drilldown & timeline popups */
.modal-dialog.uod-modal, .modal-dialog.uod-modal-tl { max-width:min(1240px, 94vw); width:94vw; }
.uod-dd-note { margin-bottom:10px; }
.uod-dd-units { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:8px; margin-bottom:12px; }
.uod-dd-units:empty { display:none; }
.uod-dd-unit { display:flex; flex-direction:column; align-items:flex-start; gap:2px; text-align:left; cursor:pointer; border:1px solid var(--border); border-radius:8px; background:var(--bg); padding:8px 12px; color:var(--text); }
.uod-dd-unit:hover { border-color:var(--brand); }
.uod-dd-unit.is-on { border-color:var(--brand); box-shadow:inset 0 0 0 1px var(--brand); background:color-mix(in srgb, var(--brand) 7%, var(--bg)); }
.uod-dd-unit-name { font-size:12px; font-weight:600; color:var(--text-2); }
.uod-dd-unit-v { display:flex; align-items:baseline; gap:6px; }
.uod-dd-unit-v b { font-size:18px; font-variant-numeric:tabular-nums; }
.uod-dd-unit-v small { font-size:11.5px; color:var(--muted); }
.uod-in-modal .uod-tt { border:1px solid var(--border); border-radius:10px; }
.uod-tl-tools { display:flex; align-items:flex-end; gap:10px; flex-wrap:wrap; padding:10px 14px; border-bottom:1px solid var(--border-soft); background:var(--bg-soft); }
.uod-tl-tool { display:flex; flex-direction:column; gap:3px; margin:0; }
.uod-tl-tool span { font-size:10.5px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
.uod-tl-tool select { height:32px; min-width:170px; max-width:260px; border:1px solid var(--border); border-radius:8px; padding:0 8px; font-size:12.5px; background:var(--bg); color:var(--text); }
.uod-tl-tool-wide select { min-width:240px; }
@media (max-width:600px) { .uod-tl-tool, .uod-tl-tool select { width:100%; max-width:none; } }
.uod-tlp-head { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
.uod-tlp-who { display:flex; align-items:center; gap:12px; min-width:0; }
.uod-tlp-avatar { flex:none; width:42px; height:42px; border-radius:50%; display:grid; place-items:center; font-size:17px; font-weight:700;
	color:color-mix(in srgb, var(--c) 85%, #000); background:color-mix(in srgb, var(--c) 14%, var(--bg)); border:1px solid color-mix(in srgb, var(--c) 35%, transparent); }
.uod-tlp-name { font-size:16px; font-weight:700; color:var(--text); display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
.uod-tlp-name .uod-idlink { font-size:12.5px; }
.uod-tlp-pills { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-top:4px; }
.uod-tlp-stats { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; }
.uod-tlp-stats > div { border:1px solid var(--border); border-top:3px solid var(--c); border-radius:8px; padding:9px 12px; background:color-mix(in srgb, var(--c) 4%, var(--bg)); display:flex; flex-direction:column; gap:2px; }
.uod-tlp-stats span { font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
.uod-tlp-stats b { font-size:15px; color:var(--text); }
.uod-journey { display:flex; gap:0; margin:16px 0 6px; overflow-x:auto; padding-bottom:4px; }
.uod-step { flex:1; min-width:78px; display:flex; flex-direction:column; align-items:center; gap:4px; position:relative; font-size:11px; color:var(--muted); text-align:center; }
.uod-step::before { content:''; position:absolute; top:11px; left:-50%; width:100%; border-top:2px solid var(--border); z-index:0; }
.uod-step:first-child::before { display:none; }
.uod-step.is-done::before { border-color:#2F7D4F; }
.uod-step-dot { position:relative; z-index:1; width:24px; height:24px; border-radius:50%; display:grid; place-items:center; font-size:12px; font-weight:700;
	background:var(--bg); border:2px solid var(--border); color:#fff; }
.uod-step.is-done .uod-step-dot { background:#2F7D4F; border-color:#2F7D4F; }
.uod-step.is-done { color:var(--text); font-weight:600; }
.uod-step.is-bad .uod-step-dot { background:#B83232; border-color:#B83232; }
.uod-step.is-bad { color:#B83232; font-weight:600; }
.uod-tlp-filter { display:flex; gap:6px; flex-wrap:wrap; padding:10px 0; border-top:1px solid var(--border-soft); margin-top:8px; }
.uod-tlf { display:inline-flex; align-items:center; border:1px solid var(--border); background:var(--bg); color:var(--text-2); border-radius:20px; padding:3px 11px; font-size:12px; font-weight:600; cursor:pointer; }
.uod-tlf .uod-dot { width:7px; height:7px; margin-right:6px; }
.uod-tlf > span:last-child { margin-left:5px; color:var(--muted); font-weight:500; }
.uod-tlf.is-on { background:color-mix(in srgb, var(--k, var(--brand)) 12%, var(--bg)); border-color:var(--k, var(--brand)); color:var(--text); }
.uod-tlp-scroll { max-height:58vh; overflow:auto; overscroll-behavior:contain; border:1px solid var(--border); border-radius:10px; background:var(--bg-soft); padding:16px 18px 6px; }
.uod-tlg { display:grid; grid-template-columns:86px minmax(0,1fr); gap:14px; }
.uod-tlg.is-hidden, .uod-tli.is-hidden { display:none; }
.uod-tlg-date { text-align:right; padding-top:9px; display:flex; flex-direction:column; line-height:1.25; }
.uod-tlg-date b { font-size:13.5px; color:var(--text); }
.uod-tlg-date span { font-size:11px; color:var(--muted); }
.uod-tlg-items { border-left:2px solid var(--border); padding:0 0 10px 18px; display:flex; flex-direction:column; gap:6px; }
.uod-tli { position:relative; display:grid; grid-template-columns:40px minmax(0,1fr); gap:8px; align-items:start; }
.uod-tli::before { content:''; position:absolute; left:-25px; top:10px; width:12px; height:12px; border-radius:50%; background:var(--k); border:2px solid var(--bg-soft); box-shadow:0 0 0 1px var(--k); }
.uod-tli.is-future::before { background:var(--bg-soft); border:2px dashed var(--k); box-shadow:none; }
.uod-tli-time { font-size:11.5px; color:var(--muted); padding-top:8px; font-variant-numeric:tabular-nums; }
.uod-tli-card { background:var(--bg); border:1px solid var(--border-soft); border-left:3px solid var(--k); border-radius:8px; padding:7px 12px; min-width:0; }
.uod-tli-top { display:flex; align-items:center; gap:4px 8px; flex-wrap:wrap; }
.uod-tli-kind { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:color-mix(in srgb, var(--k) 85%, #000); background:color-mix(in srgb, var(--k) 11%, transparent); border-radius:4px; padding:1px 6px; }
:root[data-theme="dark"] .uod-tli-kind { color:color-mix(in srgb, var(--k) 65%, #fff); }
.uod-tli-title { font-size:13px; font-weight:650; color:var(--text); }
.uod-tli-doc { margin-left:auto; font-size:11.5px; color:var(--link); white-space:nowrap; }
.uod-tli-flow { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-top:5px; }
.uod-tli-arrow { color:var(--muted); }
.uod-tli-meta { font-size:12px; color:var(--text-2); margin-top:3px; overflow-wrap:anywhere; }
.uod-tl-today { position:relative; margin:8px 0 12px; text-align:center; }
.uod-tl-today::before { content:''; position:absolute; left:0; right:0; top:50%; border-top:1px dashed #A16207; }
.uod-tl-today span { position:relative; background:var(--bg-soft); padding:0 10px; font-size:11px; font-weight:700; color:#A16207; text-transform:uppercase; letter-spacing:.05em; }
@media (max-width:600px) { .uod-tlp-stats { grid-template-columns:repeat(2, minmax(0,1fr)); } .uod-tlg { grid-template-columns:minmax(0,1fr); gap:4px; }
	.uod-tlg-date { text-align:left; flex-direction:row; gap:6px; padding-top:0; } .uod-tli { grid-template-columns:minmax(0,1fr); } .uod-tli-time:empty { display:none; } }
.uod-headline-title { margin:22px 2px 10px; }
/* module jump bar */
/* Pinned while the board scrolls (the v16 desk scrolls .main-section, which is the sticky container). */
.uod-jump { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin:-4px -6px 14px; padding:8px 6px; position:sticky; top:0; z-index:20;
	background:color-mix(in srgb, var(--page) 92%, transparent); backdrop-filter:blur(6px); }
.uod-jump:empty { display:none; }
.uod-jump-label { font-size:10.5px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin-right:4px; }
.uod-jump-chip { border:1px solid var(--border); background:var(--bg); color:var(--text-2); border-radius:20px; padding:3px 12px; font-size:12px; font-weight:600; cursor:pointer; }
.uod-jump-chip:hover { border-color:var(--brand); color:var(--brand); background:var(--brand-tint); }
.uod-section { scroll-margin-top:56px; }
.uod-is-denied, .uod-tile-1.is-denied, .uod-half.is-denied { opacity:.55; cursor:not-allowed; }
.uod-num-cell { font-variant-numeric:tabular-nums; }
.uod-guide-note { margin:-2px 0 6px; }
/* guide */
.uod-guide-sec { font-size:11px; font-weight:700; color:var(--text-2); text-transform:uppercase; letter-spacing:.06em; margin:18px 0 6px; padding-bottom:6px; border-bottom:1px solid var(--border); }
.uod-guide { width:100%; border-collapse:collapse; font-size:12.5px; }
.uod-guide th { width:230px; text-align:left; vertical-align:top; padding:8px 12px 8px 0; color:var(--text); font-weight:650; border-bottom:1px solid var(--border-soft); }
.uod-guide td { padding:8px 0; color:var(--text-2); border-bottom:1px solid var(--border-soft); }
`;
