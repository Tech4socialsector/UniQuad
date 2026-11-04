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
const PD_REMEMBERED = ['programme', 'academic_year', 'academic_term'];

class ProgrammeDashboard {
	constructor(page) {
		this.page = page;
		// the filters are remembered per browser
		this.f = { programme: '', academic_year: '', academic_term: '' };
		try {
			const saved = JSON.parse(localStorage.getItem(PD_STORE) || '{}') || {};
			PD_REMEMBERED.forEach((k) => { if (typeof saved[k] === 'string') this.f[k] = saved[k]; });
		} catch (e) { /* storage blocked or corrupt */ }
		this.$root = $('<div class="xd"></div>').appendTo(page.main);
		this.$filters = $('<div class="xd-filters"></div>').appendTo(this.$root);
		this.$body = $('<div class="xd-body"></div>').appendTo(this.$root);
		page.set_primary_action(__('Time Table'), () => frappe.set_route('List', 'Time Table', 'Calendar'), 'calendar');
		if (frappe.user.has_role(['System Manager', 'Academics User', 'AAD', 'AAD Staff'])) {
			page.add_inner_button(__('Promotion Management'), () => frappe.set_route('promotion-management'));
		}
		page.add_inner_button(__('Refresh'), () => this.load());
		this.add_styles();
		this.bind();
		frappe.xcall(PD_API + 'get_filter_options').then((o) => {
			this.options = o || {};
			// drop remembered values that no longer exist (or the user can no longer see)
			const has = (list, v) => (list || []).some((x) => (x.name || x) === v);
			if (this.f.programme && !has(o.programmes, this.f.programme)) this.f.programme = '';
			if (this.f.academic_year && !has(o.years, this.f.academic_year)) this.f.academic_year = '';
			if (this.f.academic_term && !this.terms().some((t) => t.name === this.f.academic_term)) this.f.academic_term = '';
			this.render_filters();
			this.load();
		});
	}

	// trimesters of the chosen year, or all of them
	terms() {
		const y = this.f.academic_year;
		return this.terms_all().filter((t) => !y || t.academic_year === y);
	}

	terms_all() {
		return (this.options || {}).terms || [];
	}

	bind() {
		this.$root.on('change', '.xd-f-programme', (e) => this.set({ programme: e.target.value }));
		this.$root.on('change', '.xd-f-year', (e) => {
			const academic_year = e.target.value;
			const t = this.terms_all().find((x) => x.name === this.f.academic_term);
			this.set({ academic_year, academic_term: t && (!academic_year || t.academic_year === academic_year) ? t.name : '' });
		});
		this.$root.on('change', '.xd-f-term', (e) => {
			const t = this.terms_all().find((x) => x.name === e.target.value);
			this.set(t ? { academic_term: t.name, academic_year: t.academic_year || this.f.academic_year } : { academic_term: '' });
		});
		this.$root.on('click', '.xd-clear', () => this.set({ programme: '', academic_year: '', academic_term: '' }));
		this.$root.on('click', '.xd-card', (e) => {
			const c = this.cards[+$(e.currentTarget).data('i')];
			if (c) this.drill(c);
		});
	}

	set(changes) {
		Object.assign(this.f, changes);
		try {
			localStorage.setItem(PD_STORE, JSON.stringify(Object.fromEntries(PD_REMEMBERED.map((k) => [k, this.f[k]]))));
		} catch (e) { /* storage blocked */ }
		this.render_filters();
		this.load();
	}

	render_filters() {
		const o = this.options || {};
		const f = this.f;
		const opt = (v, l, cur) => `<option value="${pd_esc(v)}" ${v === cur ? 'selected' : ''}>${pd_esc(l)}</option>`;
		const any = f.programme || f.academic_year || f.academic_term;
		this.$filters.html(`
			<select class="xd-input xd-f-year" aria-label="${__('Academic year')}">
				${opt('', __('All academic years'), f.academic_year)}
				${(o.years || []).map((y) => opt(y.name, y.is_current_year ? `${y.name} (${__('current')})` : y.name, f.academic_year)).join('')}
			</select>
			<select class="xd-input xd-f-programme" aria-label="${__('Programme')}">
				${opt('', __('All programmes'), f.programme)}${(o.programmes || []).map((p) => opt(p, p, f.programme)).join('')}
			</select>
			<select class="xd-input xd-f-term" aria-label="${__('Trimester')}">
				${opt('', __('All trimesters ({0})', [this.terms().length]), f.academic_term)}
				${this.terms().map((t) => opt(t.name, t.name === o.current_term ? `${t.name} (${__('current')})` : t.name, f.academic_term)).join('')}
			</select>
			${any ? `<button class="xd-clear">${__('Clear filters')}</button>` : ''}`);
	}

	load() {
		const f = this.f;
		// only the latest request may render (filters can change while one is in flight)
		const req = (this._req = (this._req || 0) + 1);
		return frappe.call({
			method: PD_API + 'get_dashboard',
			args: { programme: f.programme, academic_year: f.academic_year, academic_term: f.academic_term },
		}).then((r) => {
			if (req !== this._req) return;
			this.data = r.message || {};
			this.render();
		});
	}

	render() {
		const d = this.data;
		const f = this.f;
		this.cards = [];
		const scope = [f.academic_year, f.programme, f.academic_term].filter(Boolean).join(' · ') || __('Everything');
		this.$body.html(`
			<p class="xd-muted xd-range"><b>${pd_esc(scope)}</b></p>
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

	// a card opens a breakdown of its records by programme (or class, year...); numbers open the list
	drill(card) {
		frappe.xcall(PD_API + 'get_drilldown', { doctype: card.doctype, filters: card.filters || {} }).then((r) => {
			const d = new frappe.ui.Dialog({
				title: `${card.label} · ${pd_num(r.total)}`,
				size: 'extra-large',
				fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
				primary_action_label: __('Open full list'),
				primary_action: () => { d.hide(); frappe.set_route('List', card.doctype, card.filters || {}); },
			});
			const by_class = r.group === 'class_name';
			const splits = r.split ? r.splits : [];
			const open = (row, sp) => {
				const f = Object.assign({}, card.filters || {});
				f[r.group] = row.value == null || row.value === '' ? ['is', 'not set'] : row.value;
				if (sp != null) f[r.split] = sp === __('Not set') ? ['is', 'not set'] : sp;
				d.hide();
				frappe.set_route('List', card.doctype, f);
			};
			const draw = (q) => {
				const rows = r.rows.filter((x) => !q || `${x.value || ''} ${x.course_name || ''} ${x.section || ''} ${x.programme || ''} ${x.academic_term || ''}`
					.toLowerCase().includes(q));
				const name = (x) => (by_class ? [x.course_name || x.value, x.section ? __('Section {0}', [x.section]) : ''].filter(Boolean).join(' · ')
					: x.value || __('Not set'));
				$body.find('.xd-dd-wrap').html(rows.length ? `<table class="xd-table">
					<thead><tr><th>${pd_esc(r.group_label)}</th>${by_class ? `<th>${__('Programme · Trimester')}</th>` : ''}
						${splits.map((sp) => `<th class="num">${pd_esc(sp)}</th>`).join('')}<th class="num">${__('Total')}</th></tr></thead>
					<tbody>${rows.map((x) => {
						const i = r.rows.indexOf(x);
						return `<tr>
						<td><button class="xd-cell-link" data-row="${i}">${pd_esc(name(x))}</button>${by_class ? `<small class="xd-sub">${pd_esc(x.value)}</small>` : ''}</td>
						${by_class ? `<td>${pd_esc(x.programme || '—')}<small class="xd-sub">${pd_esc(x.academic_term || '')}</small></td>` : ''}
						${splits.map((sp, j) => `<td class="num">${x.split[sp] ? `<button class="xd-num-link" data-row="${i}" data-sp="${j}">${pd_num(x.split[sp])}</button>`
							: '<span class="xd-muted">0</span>'}</td>`).join('')}
						<td class="num"><button class="xd-num-link" data-row="${i}"><b>${pd_num(x.total)}</b></button></td></tr>`;
					}).join('')}</tbody></table>` : `<p class="xd-empty">${r.rows.length ? __('Nothing matches the search.') : __('No records.')}</p>`);
			};
			const $body = $(d.fields_dict.body.wrapper).addClass('xd xd-dd');
			$body.html(`<div class="xd-dd-bar">
					<span class="xd-muted">${__('{0} records in {1} {2}', [pd_num(r.total), r.rows.length, pd_esc(r.rows.length === 1 ? r.group_label.toLowerCase() : r.group_plural)])}
						· ${__('click a number to open those records')}</span>
					${r.rows.length > 8 ? `<input type="search" class="xd-input xd-dd-q" placeholder="${__('Search')}" aria-label="${__('Search')}">` : ''}
				</div><div class="xd-ct xd-dd-wrap"></div>`);
			$body.on('input', '.xd-dd-q', (e) => draw(e.target.value.trim().toLowerCase()));
			$body.on('click', '[data-row]', (e) => {
				const el = e.currentTarget;
				open(r.rows[+el.dataset.row], el.dataset.sp === undefined ? null : splits[+el.dataset.sp]);
			});
			draw('');
			d.show();
		});
	}

	add_styles() {
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
