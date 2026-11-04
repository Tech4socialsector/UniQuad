// Attendance Dashboard: count cards (see attendance_dashboard.py) for a chosen period.
// A card opens its list with the same filters.
frappe.pages['attendance-dashboard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Attendance Dashboard'), single_column: true });
	$(wrapper).addClass('er-theme');
	if (!document.getElementById('er-theme-font')) {
		$('head').append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	frappe.require('/assets/slcm/css/exam_results_theme.css');
	wrapper.dashboard = new AttendanceDashboard(page);
};

frappe.pages['attendance-dashboard'].on_page_show = function (wrapper) {
	if (wrapper.dashboard && wrapper.dashboard.data) wrapper.dashboard.load();
};

const ad_esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));
const ad_num = (v) => format_number(v || 0, null, 0);
const AD_PERIODS = [['today', __('Today')], ['7d', __('Last 7 days')], ['30d', __('Last 30 days')], ['term', __('This term')],
	['all', __('All time')], ['custom', __('Custom range…')]];
// a typed date counts only once it is complete and plausible (Chrome fires change mid-year, e.g. 0002-…)
const ad_valid_date = (v) => /^\d{4}-\d{2}-\d{2}$/.test(v || '') && +v.slice(0, 4) >= 2000 && +v.slice(0, 4) <= 2100;
const AD_API = 'slcm.slcm.page.attendance_dashboard.attendance_dashboard.';
const AD_STORE = 'attendance_dashboard_filters';
const AD_REMEMBERED = ['programme', 'academic_term', 'class_name'];

class AttendanceDashboard {
	constructor(page) {
		this.page = page;
		// programme / trimester / class are remembered per browser; the period always opens on All time
		this.f = { period: 'all', programme: '', academic_term: '', class_name: '', from_date: '', to_date: '' };
		try {
			const saved = JSON.parse(localStorage.getItem(AD_STORE) || '{}') || {};
			AD_REMEMBERED.forEach((k) => { if (typeof saved[k] === 'string') this.f[k] = saved[k]; });
		} catch (e) { /* storage blocked or corrupt */ }
		this.class_list = [];
		this.$root = $('<div class="xd"></div>').appendTo(page.main);
		this.$filters = $('<div class="xd-filters"></div>').appendTo(this.$root);
		this.$body = $('<div class="xd-body"></div>').appendTo(this.$root);
		page.set_primary_action(__('Mark attendance'), () => frappe.set_route('Form', 'Student Attendance Tool'), 'edit');
		page.add_inner_button(__('RFID Dashboard'), () => frappe.set_route('rfid-sql-agent-dashboard'));
		page.add_inner_button(__('Refresh'), () => this.load());
		this.add_styles();
		this.bind();
		frappe.xcall(AD_API + 'get_filter_options').then((o) => {
			this.options = o;
			return this.load_classes();
		}).then(() => {
			this.render_filters();
			this.load();
		});
	}

	bind() {
		this.$root.on('change', '.xd-f-period', (e) => {
			const period = e.target.value;
			if (period !== 'custom') return this.set({ period });
			// start the custom range from what is on screen, else the last 7 days
			const today = frappe.datetime.get_today();
			const d = this.data || {};
			this.set({
				period,
				from_date: ad_valid_date(this.f.from_date) ? this.f.from_date : d.from || frappe.datetime.add_days(today, -6),
				to_date: ad_valid_date(this.f.to_date) ? this.f.to_date : d.to || today,
			});
		});
		this.$root.on('change', '.xd-f-from, .xd-f-to', () => {
			clearTimeout(this._date_timer);
			this._date_timer = setTimeout(() => this.apply_dates(), 350);
		});
		this.$root.on('change', '.xd-f-programme', (e) => this.set({ programme: e.target.value, class_name: '' }, true));
		this.$root.on('change', '.xd-f-term', (e) => this.set({ academic_term: e.target.value, class_name: '' }, true));
		this.$root.on('change', '.xd-f-class', (e) => this.set({ class_name: e.target.value }));
		this.$root.on('click', '.xd-clear', () => this.set({ programme: '', academic_term: '', class_name: '' }, true));
		this.$root.on('click', '.xd-card', (e) => {
			const c = this.cards[+$(e.currentTarget).data('i')];
			if (c) this.drill(c);
		});
	}

	set(changes, reload_classes, keep_filters) {
		Object.assign(this.f, changes);
		try {
			localStorage.setItem(AD_STORE, JSON.stringify(Object.fromEntries(AD_REMEMBERED.map((k) => [k, this.f[k]]))));
		} catch (e) { /* storage blocked */ }
		(reload_classes ? this.load_classes() : Promise.resolve()).then(() => {
			if (!keep_filters) this.render_filters();
			this.load();
		});
	}

	// From/To typed or picked: keep the order valid, then reload without redrawing the inputs
	apply_dates() {
		const $from = this.$filters.find('.xd-f-from');
		const $to = this.$filters.find('.xd-f-to');
		let from = $from.val();
		let to = $to.val();
		if (!ad_valid_date(from) || !ad_valid_date(to)) return;
		if (from > to) {
			if (from !== this.f.from_date) to = from; else from = to;
			$from.val(from);
			$to.val(to);
		}
		$to.attr('min', from);
		$from.attr('max', to);
		if (from === this.f.from_date && to === this.f.to_date) return;
		this.set({ from_date: from, to_date: to }, false, true);
	}

	load_classes() {
		return frappe.xcall(AD_API + 'get_classes', { programme: this.f.programme, academic_term: this.f.academic_term })
			.then((rows) => {
				this.class_list = rows || [];
				if (this.f.class_name && !this.class_list.some((c) => c.name === this.f.class_name)) this.f.class_name = '';
			});
	}

	class_label(c) {
		return [c.course_name || c.name, c.section ? __('Section {0}', [c.section]) : ''].filter(Boolean).join(' · ');
	}

	render_filters() {
		const o = this.options || {};
		const f = this.f;
		const opt = (v, l, cur) => `<option value="${ad_esc(v)}" ${v === cur ? 'selected' : ''}>${ad_esc(l)}</option>`;
		const any = f.programme || f.academic_term || f.class_name;
		this.$filters.html(`
			<select class="xd-input xd-f-period" aria-label="${__('Period')}">
				${AD_PERIODS.map(([k, l]) => opt(k, l, f.period)).join('')}
			</select>
			${f.period === 'custom' ? `<span class="xd-range-inputs">
				<input type="date" class="xd-input xd-f-from" value="${ad_esc(f.from_date)}" max="${ad_esc(f.to_date)}"
					min="2000-01-01" aria-label="${__('From date')}">
				<span class="xd-muted">${__('to')}</span>
				<input type="date" class="xd-input xd-f-to" value="${ad_esc(f.to_date)}" min="${ad_esc(f.from_date)}"
					max="2100-12-31" aria-label="${__('To date')}">
			</span>` : ''}
			<select class="xd-input xd-f-programme" aria-label="${__('Programme')}">
				${opt('', __('All programmes'), f.programme)}${(o.programmes || []).map((p) => opt(p, p, f.programme)).join('')}
			</select>
			<select class="xd-input xd-f-term" aria-label="${__('Trimester')}">
				${opt('', __('All trimesters'), f.academic_term)}
				${(o.terms || []).map((t) => opt(t.name, t.name === o.current_term ? `${t.name} (${__('current')})` : t.name, f.academic_term)).join('')}
			</select>
			<select class="xd-input xd-f-class" aria-label="${__('Class')}">
				${opt('', __('All classes ({0})', [this.class_list.length]), f.class_name)}
				${this.class_list.map((c) => opt(c.name, `${this.class_label(c)}${f.programme ? '' : ` — ${c.programme || ''}`}`, f.class_name)).join('')}
			</select>
			${any ? `<button class="xd-clear">${__('Clear filters')}</button>` : ''}`);
	}

	load() {
		const f = this.f;
		const custom = f.period === 'custom';
		if (custom && !(ad_valid_date(f.from_date) && ad_valid_date(f.to_date))) return Promise.resolve();
		// only the latest request may render (filters can change while one is in flight)
		const req = (this._req = (this._req || 0) + 1);
		return frappe.call({
			method: AD_API + 'get_dashboard',
			args: {
				period: f.period, programme: f.programme, academic_term: f.academic_term, class_name: f.class_name,
				from_date: custom ? f.from_date : null, to_date: custom ? f.to_date : null,
			},
		}).then((r) => {
			if (req !== this._req) return;
			this.data = r.message || {};
			this.render();
		});
	}

	render() {
		const d = this.data;
		this.cards = [];
		const range = d.from ? (d.from === d.to ? frappe.datetime.str_to_user(d.from)
			: `${frappe.datetime.str_to_user(d.from)} – ${frappe.datetime.str_to_user(d.to)}`) : '';
		this.$body.html(`
			<p class="xd-muted xd-range"><b>${ad_esc(d.label)}</b>${range ? ` · ${ad_esc(range)}` : ''}</p>
			${(d.groups || []).map((g) => `<section class="xd-group">
				<h4>${ad_esc(g.title)}${g.note ? ` <small>${ad_esc(g.note)}</small>` : ''}</h4>
				<div class="xd-cards">${g.cards.map((c) => {
					const i = this.cards.push(c) - 1;
					return `<button class="xd-card ${c.value ? '' : 'zero'}" data-i="${i}" title="${__('See {0} by class', [ad_esc(c.label)])}">
						<span class="xd-label">${ad_esc(c.label)}</span>
						<b class="xd-value">${ad_esc(ad_num(c.value))}</b>
						<small>${ad_esc(c.hint || '')}</small></button>`;
				}).join('')}</div></section>`).join('')}`);
	}

	// a card opens a breakdown of its records by class (or terminal, course...); rows open the list
	drill(card) {
		frappe.xcall(AD_API + 'get_drilldown', { doctype: card.doctype, filters: card.filters || {} }).then((r) => {
			const d = new frappe.ui.Dialog({
				title: `${card.label} · ${ad_num(r.total)}`,
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
				if (sp != null && r.split !== 'eligible_for_exam') f[r.split] = sp === __('Not set') ? ['is', 'not set'] : sp;
				if (sp != null && r.split === 'eligible_for_exam') f.eligible_for_exam = sp === __('Eligible') ? 1 : 0;
				d.hide();
				frappe.set_route('List', card.doctype, f);
			};
			const draw = (q) => {
				const rows = r.rows.filter((x) => !q || `${x.value || ''} ${x.course_name || ''} ${x.section || ''} ${x.programme || ''} ${x.academic_term || ''}`
					.toLowerCase().includes(q));
				const name = (x) => (by_class ? [x.course_name || x.value, x.section ? __('Section {0}', [x.section]) : ''].filter(Boolean).join(' · ')
					: x.value || __('Not set'));
				$body.find('.xd-dd-wrap').html(rows.length ? `<table class="xd-table">
					<thead><tr><th>${ad_esc(r.group_label)}</th>${by_class ? `<th>${__('Programme · Trimester')}</th>` : ''}
						${splits.map((sp) => `<th class="num">${ad_esc(sp)}</th>`).join('')}<th class="num">${__('Total')}</th></tr></thead>
					<tbody>${rows.map((x) => {
						const i = r.rows.indexOf(x);
						return `<tr>
						<td><button class="xd-cell-link" data-row="${i}">${ad_esc(name(x))}</button>${by_class ? `<small class="xd-sub">${ad_esc(x.value)}</small>` : ''}</td>
						${by_class ? `<td>${ad_esc(x.programme || '—')}<small class="xd-sub">${ad_esc(x.academic_term || '')}</small></td>` : ''}
						${splits.map((sp, j) => `<td class="num">${x.split[sp] ? `<button class="xd-num-link" data-row="${i}" data-sp="${j}">${ad_num(x.split[sp])}</button>`
							: '<span class="xd-muted">0</span>'}</td>`).join('')}
						<td class="num"><button class="xd-num-link" data-row="${i}"><b>${ad_num(x.total)}</b></button></td></tr>`;
					}).join('')}</tbody></table>` : `<p class="xd-empty">${r.rows.length ? __('Nothing matches the search.') : __('No records.')}</p>`);
			};
			const $body = $(d.fields_dict.body.wrapper).addClass('xd xd-dd');
			$body.html(`<div class="xd-dd-bar">
					<span class="xd-muted">${__('{0} records in {1} {2}', [ad_num(r.total), r.rows.length, ad_esc(r.rows.length === 1 ? r.group_label.toLowerCase() : r.group_plural)])}
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
		// card styles match the Examination Dashboard (.xd-*); added here in case it hasn't loaded
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
