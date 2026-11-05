// Programme Dashboard: count cards (see programme_dashboard.py), laid out like the Attendance Dashboard.
// A card opens a breakdown of its records; a number there opens the list with the same filters.
frappe.pages['programme-dashboard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Programme Dashboard'), single_column: true });
	$(wrapper).addClass('er-theme');
	if (!document.getElementById('er-theme-font')) {
		$('head').append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	frappe.require('/assets/slcm/css/exam_results_theme.css');
	wrapper.dashboard = new ProgrammeDashboard(page);
};

frappe.pages['programme-dashboard'].on_page_show = function (wrapper) {
	if (wrapper.dashboard && wrapper.dashboard.data) wrapper.dashboard.load();
};

const pd_esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));
const pd_num = (v) => format_number(v || 0, null, 0);
const PD_API = 'slcm.slcm.page.programme_dashboard.programme_dashboard.';
const PD_STORE = 'programme_dashboard_filters';
// the filters, in screen order; each holds a list of names, empty meaning all
const PD_FILTERS = [
	{ key: 'academic_year', label: __('Academic year'), all: __('All academic years'), plural: __('academic years') },
	{ key: 'programme', label: __('Programme'), all: __('All programmes'), plural: __('programmes') },
	{ key: 'academic_term', label: __('Trimester'), all: __('All trimesters'), plural: __('trimesters') },
];
const pd_empty = () => ({ programme: [], academic_year: [], academic_term: [] });
const pd_same = (a, b) => PD_FILTERS.every(({ key }) => [...a[key]].sort().join('\n') === [...b[key]].sort().join('\n'));

class ProgrammeDashboard {
	constructor(page) {
		this.page = page;
		// applied filters (remembered per browser) and the draft being edited; Apply copies draft → applied
		this.f = pd_empty();
		try {
			const saved = JSON.parse(localStorage.getItem(PD_STORE) || '{}') || {};
			PD_FILTERS.forEach(({ key }) => {
				const v = saved[key];
				if (typeof v === 'string' && v) this.f[key] = [v]; // saved by the single-select version
				else if (Array.isArray(v)) this.f[key] = v.filter((x) => typeof x === 'string' && x);
			});
		} catch (e) { /* storage blocked or corrupt */ }
		this.draft = JSON.parse(JSON.stringify(this.f));
		this.$root = $('<div class="xd"></div>').appendTo(page.main);
		this.$filters = $('<div class="xd-filters pd-filters"></div>').appendTo(this.$root);
		this.$body = $('<div class="xd-body"></div>').appendTo(this.$root);
		page.set_primary_action(__('Time Table'), () => frappe.set_route('List', 'Time Table', 'Calendar'), 'calendar');
		if (frappe.user.has_role(['System Manager', 'Academics User', 'AAD', 'AAD Staff'])) {
			page.add_inner_button(__('Promotion Management'), () => frappe.set_route('promotion-management'));
		}
		page.add_inner_button(__('Refresh'), () => this.load());
		this.add_styles();
		this.bind();
		this.init();
	}

	init() {
		this.$body.html(`<p class="pd-state">${__('Loading the dashboard…')}</p>`);
		frappe.xcall(PD_API + 'get_filter_options').then((o) => {
			this.options = o || {};
			// drop remembered values that no longer exist (or the user can no longer see)
			PD_FILTERS.forEach(({ key }) => {
				const ok = new Set(this.choices(key, this.f, true).map((c) => c.value));
				this.f[key] = this.f[key].filter((v) => ok.has(v));
			});
			this.f.academic_term = this.valid_terms(this.f);
			this.draft = JSON.parse(JSON.stringify(this.f));
			this.render_filters();
			this.load();
		}).catch(() => this.render_error());
	}

	render_error() {
		this.$root.removeClass('pd-busy');
		this.$body.html(`<div class="pd-state pd-error"><b>${__('The dashboard could not be loaded.')}</b>
			<span>${__('Check your connection, then try again.')}</span>
			<button class="btn btn-default btn-xs pd-retry">${__('Try again')}</button></div>`);
	}

	// options of one filter; trimesters follow the academic years in `state` unless `all`
	choices(key, state, all) {
		const o = this.options || {};
		if (key === 'academic_year') {
			return (o.years || []).map((y) => ({ value: y.name, label: y.is_current_year ? `${y.name} (${__('current')})` : y.name }));
		}
		if (key === 'programme') return (o.programmes || []).map((p) => ({ value: p, label: p }));
		const years = state.academic_year;
		return (o.terms || []).filter((t) => all || !years.length || years.includes(t.academic_year))
			.map((t) => ({ value: t.name, label: t.name === o.current_term ? `${t.name} (${__('current')})` : t.name }));
	}

	// selected trimesters that still belong to the selected years
	valid_terms(state) {
		const ok = new Set(this.choices('academic_term', state).map((c) => c.value));
		return state.academic_term.filter((t) => ok.has(t));
	}

	summary(key, values) {
		const def = PD_FILTERS.find((x) => x.key === key);
		if (!values.length) return def.all;
		if (values.length === 1) return values[0];
		return `${values.length} ${def.plural}`;
	}

	bind() {
		const $f = this.$filters;
		$f.on('click', '.pd-ms-btn', (e) => {
			const key = $(e.currentTarget).closest('.pd-ms').data('key');
			this.toggle(this.open_key === key ? null : key);
		});
		$f.on('change', '.pd-ms-opt input', (e) => {
			const key = $(e.currentTarget).closest('.pd-ms').data('key');
			const v = e.currentTarget.value;
			const cur = this.draft[key];
			this.draft[key] = e.currentTarget.checked ? cur.concat(cur.includes(v) ? [] : [v]) : cur.filter((x) => x !== v);
			this.changed(key);
		});
		$f.on('input', '.pd-ms-q', (e) => {
			const q = e.target.value.trim().toLowerCase();
			$(e.target).closest('.pd-ms').find('.pd-ms-opt').each((i, el) => {
				el.hidden = !!q && !el.textContent.toLowerCase().includes(q);
			});
			this.no_match($(e.target).closest('.pd-ms'));
		});
		// select all / clear act on the options the search shows
		$f.on('click', '.pd-ms-all, .pd-ms-none', (e) => {
			const $ms = $(e.currentTarget).closest('.pd-ms');
			const key = $ms.data('key');
			const on = e.currentTarget.classList.contains('pd-ms-all');
			const shown = $ms.find('.pd-ms-opt:not([hidden]) input').map((i, el) => { el.checked = on; return el.value; }).get();
			const cur = this.draft[key];
			this.draft[key] = on ? cur.concat(shown.filter((v) => !cur.includes(v))) : cur.filter((v) => !shown.includes(v));
			this.changed(key);
		});
		$f.on('keydown', '.pd-ms', (e) => {
			if (e.key !== 'Escape' || !this.open_key) return;
			e.stopPropagation();
			const key = this.open_key;
			this.toggle(null);
			$f.find(`.pd-ms[data-key="${key}"] .pd-ms-btn`).trigger('focus');
		});
		$f.on('click', '.pd-apply', () => this.apply());
		$f.on('click', '.pd-reset', () => {
			this.draft = pd_empty();
			this.apply();
		});
		// a click anywhere else closes the open list
		$(document).on('mousedown.pd-ms', (e) => {
			if (this.open_key && !$(e.target).closest('.pd-ms').length) this.toggle(null);
		});
		this.$root.on('click', '.pd-retry', () => (this.options ? this.load() : this.init()));
		this.$root.on('click', '.xd-card', (e) => {
			const c = this.cards[+$(e.currentTarget).data('i')];
			if (c) this.drill(c);
		});
	}

	toggle(key) {
		this.open_key = key;
		this.$filters.find('.pd-ms').each((i, el) => {
			const open = el.dataset.key === key;
			const $ms = $(el);
			$ms.find('.pd-ms-btn').attr('aria-expanded', open ? 'true' : 'false');
			if (open) $ms.find('.pd-ms-pop').html(this.pop_html(key));
			$ms.find('.pd-ms-pop').prop('hidden', !open);
			if (open) $ms.find('.pd-ms-q').trigger('focus');
		});
	}

	// a draft value changed: years narrow the trimesters, then the buttons and Apply follow
	changed(key) {
		if (key === 'academic_year') this.draft.academic_term = this.valid_terms(this.draft);
		this.update_bar();
	}

	no_match($ms) {
		const any = $ms.find('.pd-ms-opt:not([hidden])').length;
		$ms.find('.pd-ms-empty').prop('hidden', !!any);
	}

	pop_html(key) {
		const sel = new Set(this.draft[key]);
		const list = this.choices(key, this.draft);
		const def = PD_FILTERS.find((x) => x.key === key);
		return `<input type="search" class="xd-input pd-ms-q" placeholder="${__('Search')}" aria-label="${__('Search {0}', [def.plural])}">
			<div class="pd-ms-actions"><button type="button" class="pd-ms-all">${__('Select all')}</button>
				<button type="button" class="pd-ms-none">${__('Clear')}</button></div>
			<div class="pd-ms-list" role="group" aria-label="${pd_esc(def.label)}">
				${list.map((c) => `<label class="pd-ms-opt"><input type="checkbox" value="${pd_esc(c.value)}" ${sel.has(c.value) ? 'checked' : ''}>
					<span>${pd_esc(c.label)}</span></label>`).join('')}
				<p class="pd-ms-empty" ${list.length ? 'hidden' : ''}>${list.length ? __('Nothing matches the search.') : __('No options.')}</p>
			</div>`;
	}

	render_filters() {
		this.open_key = null;
		this.$filters.html(`${PD_FILTERS.map((x) => `<div class="pd-ms" data-key="${x.key}">
				<span class="pd-ms-label">${pd_esc(x.label)}</span>
				<button type="button" class="xd-input pd-ms-btn" aria-haspopup="true" aria-expanded="false">
					<span class="pd-ms-text"></span><span class="pd-ms-caret" aria-hidden="true">▾</span></button>
				<div class="pd-ms-pop" hidden></div>
			</div>`).join('')}
			<span class="pd-actions">
				<button type="button" class="pd-btn pd-btn-primary pd-apply">${__('Apply')}</button>
				<button type="button" class="pd-btn pd-reset">${__('Reset')}</button>
				<span class="pd-pending xd-muted" hidden>${__('Changes not applied yet')}</span>
			</span>`);
		this.update_bar();
	}

	update_bar() {
		PD_FILTERS.forEach(({ key }) => {
			const $ms = this.$filters.find(`.pd-ms[data-key="${key}"]`);
			$ms.find('.pd-ms-text').text(this.summary(key, this.draft[key]));
			$ms.toggleClass('active', !!this.draft[key].length);
		});
		const dirty = !pd_same(this.draft, this.f);
		const any = PD_FILTERS.some(({ key }) => this.f[key].length || this.draft[key].length);
		this.$filters.find('.pd-apply').prop('disabled', !dirty);
		this.$filters.find('.pd-reset').prop('disabled', !any);
		this.$filters.find('.pd-pending').prop('hidden', !dirty);
	}

	apply() {
		// every option ticked is the same as no filter (trimesters: every one of the chosen years')
		const f = pd_empty();
		PD_FILTERS.forEach(({ key }) => {
			const v = this.draft[key];
			f[key] = v.length && v.length === this.choices(key, this.draft).length ? [] : [...v];
		});
		this.f = f;
		this.draft = JSON.parse(JSON.stringify(f));
		try {
			localStorage.setItem(PD_STORE, JSON.stringify(this.f));
		} catch (e) { /* storage blocked */ }
		this.render_filters();
		this.load();
	}

	load() {
		const f = this.f;
		// only the latest request may render (filters can change while one is in flight)
		const req = (this._req = (this._req || 0) + 1);
		this.$root.addClass('pd-busy');
		return frappe.call({
			method: PD_API + 'get_dashboard',
			args: {
				programme: JSON.stringify(f.programme),
				academic_year: JSON.stringify(f.academic_year),
				academic_term: JSON.stringify(f.academic_term),
			},
			error: () => { if (req === this._req) this.render_error(); },
		}).then((r) => {
			if (req !== this._req) return;
			this.$root.removeClass('pd-busy');
			this.data = (r && r.message) || {};
			this.render();
		});
	}

	// the applied filters, shown above the cards
	scope_html() {
		const parts = PD_FILTERS.filter(({ key }) => this.f[key].length).map(({ key, label }) => {
			const v = this.f[key];
			const names = v.slice(0, 3).join(', ') + (v.length > 3 ? ` ${__('+{0} more', [v.length - 3])}` : '');
			return `<span class="pd-chip" title="${pd_esc(v.join(', '))}"><b>${pd_esc(label)}:</b> ${pd_esc(names)}</span>`;
		});
		return parts.length ? parts.join('') : `<b>${__('Everything')}</b> <span>${__('no filters applied')}</span>`;
	}

	render() {
		const d = this.data;
		this.cards = [];
		this.$body.html(`
			<p class="xd-muted xd-range pd-scope">${this.scope_html()}</p>
			${(d.groups || []).map((g) => `<section class="xd-group">
				<h4>${pd_esc(g.title)}${g.note ? ` <small>${pd_esc(g.note)}</small>` : ''}</h4>
				<div class="xd-cards">${g.cards.map((c) => {
					const i = this.cards.push(c) - 1;
					return `<button class="xd-card ${c.value ? '' : 'zero'}" data-i="${i}" title="${__('See the breakdown of {0}', [pd_esc(c.label)])}">
						<span class="xd-label">${pd_esc(c.label)}</span>
						<b class="xd-value">${pd_esc(pd_num(c.value))}</b>
						<small>${pd_esc(c.hint || '')}</small></button>`;
				}).join('')}</div></section>`).join('')}`);
	}

	// a card opens its breakdown in a dialog; everything after that stays in the dialog (see PdDrill)
	drill(card) {
		new PdDrill(card);
	}

	add_styles() {
		// this page's own additions: loading/error states and the drill-down's records step
		if (!document.getElementById('pd-styles')) {
			$('head').append(`<style id="pd-styles">
				.xd.pd-busy .xd-body,.pd-dd-main.pd-busy{opacity:.55;pointer-events:none;transition:opacity .15s}
				.pd-state{color:var(--text-muted);margin:0;padding:24px 14px}
				.pd-error{display:flex;flex-direction:column;align-items:flex-start;gap:8px}.pd-error b{color:var(--text-color)}
				.pd-dd .pd-tools{display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap}
				.pd-dd .pd-dd-top>span:first-child{display:inline-flex;align-items:center;gap:10px;flex-wrap:wrap}
				.pd-dd-foot{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
				.pd-dd-foot:empty{display:none}
				.pd-dd .pd-size{height:26px;font-size:12px}
				.pd-sort{font:inherit;color:inherit;border:0;background:none;padding:0;cursor:pointer;white-space:nowrap;text-align:inherit}
				.pd-sort:hover,.pd-sort.on{color:var(--text-color)}
				.pd-arrow{display:inline-block;width:12px;margin-left:3px;font-size:9px}
				.pd-rec-link{font-weight:700;color:var(--text-color)!important;white-space:nowrap}
				.pd-rec-link:hover{color:var(--er-brand,#920C24)!important;text-decoration:underline}
				.xd-filters.pd-filters{align-items:flex-end;gap:10px}
				.pd-ms{position:relative;display:flex;flex-direction:column;gap:3px}
				.pd-ms-label{font-size:11px;font-weight:700;color:var(--text-muted)}
				.pd-ms-btn{display:flex;align-items:center;justify-content:space-between;gap:10px;width:230px;max-width:100%;text-align:left;cursor:pointer}
				.pd-ms-text{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
				.pd-ms-caret{font-size:10px;color:var(--text-muted)}
				.pd-ms.active .pd-ms-btn{border-color:var(--er-brand,#920C24);font-weight:700}
				.pd-ms-pop{position:absolute;top:calc(100% + 4px);left:0;z-index:30;width:320px;max-width:calc(100vw - 32px);padding:8px;
					background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.12)}
				.pd-ms-pop .pd-ms-q{width:100%;max-width:none}
				.pd-ms-actions{display:flex;justify-content:space-between;padding:6px 2px}
				.pd-ms-actions button{font:inherit;font-size:12px;font-weight:700;border:0;background:none;padding:2px;color:var(--er-brand,#920C24);cursor:pointer}
				.pd-ms-list{max-height:260px;overflow:auto;display:flex;flex-direction:column}
				.pd-ms-opt{display:flex;align-items:center;gap:8px;margin:0;padding:6px 6px;border-radius:6px;font-weight:400;cursor:pointer}
				.pd-ms-opt:hover{background:var(--subtle-fg,var(--gray-50,#fafafa))}
				.pd-ms-opt input{margin:0;accent-color:var(--er-brand,#920C24)}
				.pd-ms-opt[hidden]{display:none}
				.pd-ms-empty{margin:0;padding:8px 6px;color:var(--text-muted);font-size:12px}
				.pd-actions{display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap;min-height:32px}
				.pd-btn{height:32px;padding:0 16px;font-family:inherit;font-size:12.5px;font-weight:700;line-height:30px;border-radius:8px;
					border:1px solid var(--border-color);background:var(--card-bg);color:var(--text-color);cursor:pointer;transition:background .15s,border-color .15s}
				.pd-btn:hover:not(:disabled){border-color:var(--er-brand,#920C24);color:var(--er-brand,#920C24)}
				.pd-btn-primary{background:var(--er-brand,#920C24);border-color:var(--er-brand,#920C24);color:#fff}
				.pd-btn-primary:hover:not(:disabled){background:var(--er-brand-dark,#6f0919);border-color:var(--er-brand-dark,#6f0919);color:#fff}
				.pd-btn:disabled{background:var(--control-bg,#f3f3f3);border-color:var(--border-color);color:var(--text-muted);cursor:not-allowed;opacity:1}
				.pd-btn:focus-visible{outline:2px solid var(--er-brand,#920C24);outline-offset:2px}
				.pd-pending{color:var(--er-brand,#920C24);font-weight:700}
				.pd-scope{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
				.pd-chip{display:inline-block;max-width:100%;padding:2px 8px;border:1px solid var(--border-color);border-radius:99px;
					background:var(--card-bg);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
				.pd-chip b{color:var(--text-color)}
				@media (max-width:600px){.pd-ms,.pd-ms-btn{width:100%}.pd-ms-pop{width:100%}}
				.pd-ms-btn:focus-visible,.pd-sort:focus-visible,.xd-card:focus-visible,.xd-cell-link:focus-visible,.xd-num-link:focus-visible,.pd-rec-link:focus-visible{
					outline:2px solid var(--er-brand,#920C24);outline-offset:2px}
			</style>`);
		}
		if (document.getElementById('ad-styles')) return;
		// same block (and id) as the Attendance Dashboard, so whichever page opens first adds it once
		$('head').append(`<style id="ad-styles">
			.xd{display:flex;flex-direction:column;gap:18px;padding:6px 16px 40px;font-family:var(--er-font,Georgia,serif);font-size:13px}
			.xd-filters{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
			.xd-body{display:flex;flex-direction:column;gap:18px}.xd-range{margin-top:-6px}
			.xd-input{font-family:inherit;font-size:12.5px;height:32px;border:1px solid var(--border-color);border-radius:8px;background:var(--control-bg,#fff);color:var(--text-color);padding:0 10px;max-width:280px}
			.xd-input:focus{outline:none;border-color:var(--er-brand,#920C24)}
			.xd-range-inputs{display:inline-flex;align-items:center;gap:6px}.xd-range-inputs .xd-input{width:150px}
			.xd-clear{font:inherit;font-size:12px;font-weight:700;border:0;background:none;color:var(--er-brand,#920C24);cursor:pointer}
			.xd-dd{padding:0;gap:10px}.xd-dd-bar{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
			.xd-ct{background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;overflow:auto;max-height:60vh;position:relative}
			.xd-table{width:100%;border-collapse:collapse;font-size:12.5px}
			.xd-table th{position:sticky;top:0;background:var(--card-bg);text-align:left;font-weight:700;color:var(--text-muted);font-size:11.5px;padding:8px 10px;border-bottom:1px solid var(--border-color);white-space:nowrap}
			.xd-table td{padding:8px 10px;border-bottom:1px solid var(--border-color);vertical-align:top}
			.xd-table tr:last-child td{border-bottom:0}
			.xd-table .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
			.xd-sub{display:block;color:var(--text-muted);font-size:11px}
			.xd-cell-link,.xd-num-link{font:inherit;border:0;background:none;padding:0;color:var(--text-color);font-weight:700;cursor:pointer;text-align:left}
			.xd-cell-link:hover,.xd-num-link:hover{color:var(--er-brand,#920C24);text-decoration:underline}
			.xd-num-link.bad{color:var(--er-brand,#920C24)}
			.xd-empty{color:var(--text-muted);margin:0;padding:14px}
			.xd-muted{color:var(--text-muted);font-size:12px;margin:0}
			.xd-group h4{font-size:14px;font-weight:700;margin:0 0 8px}.xd-group h4 small{font-weight:400;color:var(--text-muted);font-size:12px;margin-left:6px}
			.xd-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}
			.xd-card{display:flex;flex-direction:column;align-items:flex-start;gap:4px;text-align:left;font:inherit;color:var(--text-color);
				background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:12px 14px;cursor:pointer}
			.xd-card:hover{background:var(--subtle-fg,var(--gray-50,#fafafa))}
			.xd-card.zero .xd-value{color:var(--text-muted)}
			.xd-label{font-size:12px;color:var(--text-muted)}
			.xd-value{font-size:26px;line-height:1.15;font-weight:700;font-variant-numeric:tabular-nums}
			.xd-card small{font-size:11.5px;color:var(--text-muted);min-height:16px}
			@media (max-width:600px){.xd-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.xd-value{font-size:22px}.xd-range-inputs{flex-wrap:wrap}}
		</style>`);
	}
}

const PD_PAGE_SIZES = [25, 50, 100];
const PD_EXPORT_LIMIT = 20000;

// Drill-down dialog. Step 1: the card's records grouped (by programme, class...) and split by status.
// Step 2: a number there lists those records, paged and sortable, without leaving the dialog.
// Both steps export to CSV; "Open in list view" opens the list with whatever is on screen.
class PdDrill {
	constructor(card) {
		this.card = card;
		this.req = 0;
		this.view = 'groups';
		this.gsort = { key: 'total', dir: 'desc' };
		this.q = '';
		this.d = new frappe.ui.Dialog({
			title: pd_esc(card.label),
			size: 'extra-large',
			fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
			primary_action_label: __('Open in list view'),
			primary_action: () => {
				this.d.hide();
				frappe.set_route('List', this.card.doctype, this.filters());
			},
		});
		this.$b = $(this.d.fields_dict.body.wrapper).addClass('xd xd-dd pd-dd');
		this.$b.html('<div class="xd-dd-bar pd-dd-top"></div><div class="xd-ct pd-dd-main"></div><div class="pd-dd-foot"></div>');
		this.bind();
		this.d.show();
		this.load_groups();
	}

	filters() {
		return this.view === 'records' ? this.rec.filters : this.card.filters || {};
	}

	part(name, html) {
		this.$b.find(`.pd-dd-${name}`).html(html);
	}

	set_title(extra) {
		this.d.set_title(pd_esc(extra ? `${this.card.label} · ${extra}` : this.card.label));
	}

	failed(retry) {
		this._retry = retry;
		this.$b.find('.pd-dd-main').removeClass('pd-busy');
		this.part('main', `<div class="pd-state pd-error"><b>${__('This could not be loaded.')}</b>
			<button class="btn btn-default btn-xs pd-dd-retry">${__('Try again')}</button></div>`);
	}

	bind() {
		const $b = this.$b;
		$b.on('input', '.pd-dd-q', (e) => {
			this.q = e.target.value.trim().toLowerCase();
			this.draw_groups();
		});
		$b.on('click', '.pd-sort', (e) => {
			const key = e.currentTarget.dataset.key;
			if (this.view === 'groups') {
				const g = this.gsort;
				this.gsort = { key, dir: g.key === key && g.dir === 'desc' ? 'asc' : 'desc' };
				this.draw_groups();
			} else {
				const r = this.rec;
				r.sort_order = r.sort_by === key && r.sort_order === 'desc' ? 'asc' : 'desc';
				r.sort_by = key;
				r.start = 0;
				this.load_records();
			}
		});
		$b.on('click', '[data-row]', (e) => {
			const el = e.currentTarget;
			const splits = this.g.split ? this.g.splits : [];
			this.open_group(this.g.rows[+el.dataset.row], el.dataset.sp === undefined ? null : splits[+el.dataset.sp]);
		});
		$b.on('click', '.pd-back', () => this.render_groups());
		$b.on('click', '.pd-page', (e) => {
			this.rec.start = Math.max(+e.currentTarget.dataset.start || 0, 0);
			this.load_records();
		});
		$b.on('change', '.pd-size', (e) => {
			this.rec.page_length = +e.target.value;
			this.rec.start = 0;
			this.load_records();
		});
		$b.on('click', '.pd-export', () => this.export());
		$b.on('click', '.pd-dd-retry', () => this._retry && this._retry());
	}

	// a dialog can outlive several requests (paging, sorting); only the latest may render
	call(method, args) {
		const req = ++this.req;
		return frappe.xcall(PD_API + method, args).then((r) => {
			if (req !== this.req) return Promise.reject({ stale: true });
			return r;
		});
	}

	sort_head(key, label, cur, num) {
		const on = cur.key === key;
		const aria = on ? (cur.dir === 'asc' ? 'ascending' : 'descending') : 'none';
		return `<th class="${num ? 'num' : ''}" aria-sort="${aria}"><button class="pd-sort ${on ? 'on' : ''}" data-key="${pd_esc(key)}"
			title="${__('Sort')}">${pd_esc(label)}<span class="pd-arrow">${on ? (cur.dir === 'asc' ? '▲' : '▼') : ''}</span></button></th>`;
	}

	// ---- step 1: breakdown
	load_groups() {
		this.view = 'groups';
		this.part('top', '');
		this.part('foot', '');
		this.part('main', `<p class="pd-state">${__('Loading…')}</p>`);
		this.call('get_drilldown', { doctype: this.card.doctype, filters: this.card.filters || {} }).then((r) => {
			this.g = r;
			this.render_groups();
		}).catch((e) => { if (!(e && e.stale)) this.failed(() => this.load_groups()); });
	}

	render_groups() {
		const r = this.g;
		this.view = 'groups';
		this.req++; // ignore a records page still loading
		this.set_title(pd_num(r.total));
		this.part('top', `<span class="xd-muted">${__('{0} records in {1} {2}', [pd_num(r.total), r.rows.length,
			pd_esc(r.rows.length === 1 ? r.group_label.toLowerCase() : r.group_plural)])} · ${__('click a number to see those records')}</span>
			<span class="pd-tools">
				${r.rows.length > 8 ? `<input type="search" class="xd-input pd-dd-q" value="${pd_esc(this.q)}" placeholder="${__('Search')}" aria-label="${__('Search')}">` : ''}
				<button class="btn btn-default btn-xs pd-export" ${r.rows.length ? '' : 'disabled'}>${__('Export CSV')}</button>
			</span>`);
		this.part('foot', '');
		this.$b.find('.pd-dd-main').removeClass('pd-busy');
		this.draw_groups();
	}

	group_name(x) {
		return this.g.group === 'class_name'
			? [x.course_name || x.value, x.section ? __('Section {0}', [x.section]) : ''].filter(Boolean).join(' · ')
			: x.value || __('Not set');
	}

	draw_groups() {
		const r = this.g;
		const by_class = r.group === 'class_name';
		const splits = r.split ? r.splits : [];
		const q = this.q;
		const { key, dir } = this.gsort;
		const val = (x) => (key === 'total' ? x.total : key === 'name' ? this.group_name(x).toLowerCase() : x.split[splits[+key.slice(1)]] || 0);
		const rows = r.rows
			.map((x, i) => ({ x, i }))
			.filter(({ x }) => !q || `${x.value || ''} ${x.course_name || ''} ${x.section || ''} ${x.programme || ''} ${x.academic_term || ''}`.toLowerCase().includes(q))
			.sort((a, b) => {
				const va = val(a.x);
				const vb = val(b.x);
				return (va < vb ? -1 : va > vb ? 1 : 0) * (dir === 'asc' ? 1 : -1);
			});
		this.part('main', rows.length ? `<table class="xd-table">
			<thead><tr>${this.sort_head('name', r.group_label, this.gsort)}${by_class ? `<th>${__('Programme · Trimester')}</th>` : ''}
				${splits.map((sp, j) => this.sort_head(`s${j}`, sp, this.gsort, true)).join('')}${this.sort_head('total', __('Total'), this.gsort, true)}</tr></thead>
			<tbody>${rows.map(({ x, i }) => `<tr>
				<td><button class="xd-cell-link" data-row="${i}">${pd_esc(this.group_name(x))}</button>${by_class ? `<small class="xd-sub">${pd_esc(x.value)}</small>` : ''}</td>
				${by_class ? `<td>${pd_esc(x.programme || '—')}<small class="xd-sub">${pd_esc(x.academic_term || '')}</small></td>` : ''}
				${splits.map((sp, j) => `<td class="num">${x.split[sp] ? `<button class="xd-num-link" data-row="${i}" data-sp="${j}">${pd_num(x.split[sp])}</button>`
					: '<span class="xd-muted">0</span>'}</td>`).join('')}
				<td class="num"><button class="xd-num-link" data-row="${i}"><b>${pd_num(x.total)}</b></button></td></tr>`).join('')}</tbody></table>`
			: `<p class="xd-empty">${r.rows.length ? __('Nothing matches the search.') : __('No records.')}</p>`);
	}

	// ---- step 2: the records behind one number
	open_group(row, sp) {
		const g = this.g;
		const f = Object.assign({}, this.card.filters || {});
		f[g.group] = row.value == null || row.value === '' ? ['is', 'not set'] : row.value;
		if (sp != null) f[g.split] = sp === __('Not set') ? ['is', 'not set'] : sp;
		this.rec = { filters: f, label: [this.group_name(row), sp].filter((v) => v != null).join(' · '),
			sort_by: null, sort_order: 'desc', start: 0, page_length: 50, data: null };
		this.load_records();
	}

	load_records() {
		const rec = this.rec;
		this.view = 'records';
		this.set_title(rec.label);
		const $main = this.$b.find('.pd-dd-main');
		if (rec.data) $main.addClass('pd-busy');
		else {
			this.part('top', `<span><button class="btn btn-default btn-xs pd-back">← ${__('Back')}</button></span>`);
			this.part('foot', '');
			this.part('main', `<p class="pd-state">${__('Loading…')}</p>`);
		}
		this.call('get_records', {
			doctype: this.card.doctype, filters: rec.filters, sort_by: rec.sort_by, sort_order: rec.sort_order,
			start: rec.start, page_length: rec.page_length,
		}).then((r) => {
			Object.assign(rec, { data: r, sort_by: r.sort_by, sort_order: r.sort_order, start: r.start });
			$main.removeClass('pd-busy');
			this.render_records();
		}).catch((e) => { if (!(e && e.stale)) this.failed(() => this.load_records()); });
	}

	fmt(v, type) {
		if (v == null || v === '') return '';
		if (type === 'Date' || type === 'Datetime') return frappe.datetime.str_to_user(v);
		if (type === 'Time') return moment(String(v), 'HH:mm:ss').format('HH:mm');
		if (type === 'Check') return v ? __('Yes') : __('No');
		if (['Int', 'Float', 'Currency', 'Percent'].includes(type)) return format_number(v, null, type === 'Int' ? 0 : 2);
		return String(v);
	}

	render_records() {
		const rec = this.rec;
		const r = rec.data;
		const sort = { key: rec.sort_by, dir: rec.sort_order };
		const first = r.total ? r.start + 1 : 0;
		const last = Math.min(r.start + r.rows.length, r.total);
		const num = (c) => ['Int', 'Float', 'Currency', 'Percent'].includes(c.fieldtype);
		this.part('top', `<span><button class="btn btn-default btn-xs pd-back">← ${__('Back')}</button>
				<span class="xd-muted">${__('{0} records', [pd_num(r.total)])} · ${__('open a record by its ID')}</span></span>
			<span class="pd-tools"><button class="btn btn-default btn-xs pd-export" ${r.total ? '' : 'disabled'}>${__('Export CSV')}</button></span>`);
		this.part('main', r.rows.length ? `<table class="xd-table">
			<thead><tr>${r.columns.map((c) => this.sort_head(c.fieldname, c.label, sort, num(c))).join('')}</tr></thead>
			<tbody>${r.rows.map((row) => `<tr>${r.columns.map((c, j) => (j === 0
				? `<td><a class="pd-rec-link" href="${pd_esc(frappe.utils.get_form_link(this.card.doctype, row.name))}" target="_blank"
					rel="noopener noreferrer" title="${__('Open in a new tab')}">${pd_esc(row.name)}</a></td>`
				: `<td class="${num(c) ? 'num' : ''}">${pd_esc(this.fmt(row[c.fieldname], c.fieldtype))}</td>`)).join('')}</tr>`).join('')}</tbody></table>`
			: `<p class="xd-empty">${__('No records.')}</p>`);
		this.part('foot', r.total ? `<span class="xd-muted">${__('Showing {0}–{1} of {2}', [pd_num(first), pd_num(last), pd_num(r.total)])}</span>
			<span class="pd-tools">
				<select class="xd-input pd-size" aria-label="${__('Rows per page')}">${PD_PAGE_SIZES.map((n) =>
					`<option value="${n}" ${n === r.page_length ? 'selected' : ''}>${__('{0} per page', [n])}</option>`).join('')}</select>
				<button class="btn btn-default btn-xs pd-page" data-start="${r.start - r.page_length}" ${r.start ? '' : 'disabled'}>${__('Previous')}</button>
				<button class="btn btn-default btn-xs pd-page" data-start="${r.start + r.page_length}" ${last < r.total ? '' : 'disabled'}>${__('Next')}</button>
			</span>` : '');
	}

	export() {
		const args = { doctype: this.card.doctype, filters: JSON.stringify(this.filters()) };
		if (this.view === 'records') {
			if (this.rec.data && this.rec.data.total > PD_EXPORT_LIMIT) {
				frappe.msgprint(__('More than {0} records. Narrow the filters first.', [pd_num(PD_EXPORT_LIMIT)]));
				return;
			}
			Object.assign(args, { view: 'records', sort_by: this.rec.sort_by || '', sort_order: this.rec.sort_order });
		} else {
			args.view = 'breakdown';
		}
		open_url_post('/api/method/' + PD_API + 'export_drilldown', args);
	}
}
