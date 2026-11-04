// Fees Dashboard: amount + count cards (see fee_dashboard.py) for an academic year,
// programme and batch. Dues and payment cards open a breakdown; others open their list.
frappe.pages['fee-dashboard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Fees Dashboard'), single_column: true });
	$(wrapper).addClass('er-theme');
	if (!document.getElementById('er-theme-font')) {
		$('head').append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	frappe.require('/assets/slcm/css/exam_results_theme.css');
	wrapper.dashboard = new FeeDashboard(page);
};

frappe.pages['fee-dashboard'].on_page_show = function (wrapper) {
	if (wrapper.dashboard && wrapper.dashboard.data) wrapper.dashboard.load();
};

const fd_esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));
const fd_num = (v) => format_number(v || 0, null, 0);
const fd_money = (v) => format_currency(v || 0, 'INR', 0);
// "1 dues" → "1 due": the count labels are plural nouns
const fd_count = (n, unit) => `${fd_num(n)} ${n === 1 ? String(unit || '').replace(/s$/, '') : unit || ''}`;
const FD_API = 'slcm.slcm.page.fee_dashboard.fee_dashboard.';
const FD_STORE = 'fee_dashboard_filters';

class FeeDashboard {
	constructor(page) {
		this.page = page;
		// academic year / programme / batch; remembered per browser
		this.f = { academic_year: null, programme: '', batch: '' };
		try { Object.assign(this.f, JSON.parse(localStorage.getItem(FD_STORE) || '{}')); } catch (e) { /* storage blocked */ }
		this.$root = $('<div class="xd"></div>').appendTo(page.main);
		this.$filters = $('<div class="xd-filters"></div>').appendTo(this.$root);
		this.$body = $('<div class="xd-body"></div>').appendTo(this.$root);
		page.set_primary_action(__('Student fees'), () => frappe.set_route('student-fee-management'), 'users');
		page.add_inner_button(__('Fee Reports'), () => frappe.set_route('fee-reports'));
		page.add_inner_button(__('Refresh'), () => this.load());
		this.add_styles();
		this.bind();
		frappe.xcall(FD_API + 'get_filter_options').then((o) => {
			this.options = o;
			// first visit: the current academic year ("" = all years, chosen on purpose)
			if (this.f.academic_year == null) this.f.academic_year = o.current_academic_year || '';
			this.render_filters();
			this.load();
		});
	}

	bind() {
		this.$root.on('change', '.xd-f-ay', (e) => this.set({ academic_year: e.target.value }));
		this.$root.on('change', '.xd-f-programme', (e) => this.set({ programme: e.target.value }));
		this.$root.on('change', '.xd-f-batch', (e) => this.set({ batch: e.target.value }));
		this.$root.on('click', '.xd-clear', () => this.set({ programme: '', batch: '' }));
		this.$root.on('click', '.xd-card', (e) => {
			const c = this.cards[+$(e.currentTarget).data('i')];
			if (!c) return;
			if (c.drill) this.drill(c);
			else frappe.set_route('List', c.doctype, c.filters || {});
		});
	}

	set(changes) {
		Object.assign(this.f, changes);
		try { localStorage.setItem(FD_STORE, JSON.stringify(this.f)); } catch (e) { /* storage blocked */ }
		this.render_filters();
		this.load();
	}

	render_filters() {
		const o = this.options || {};
		const f = this.f;
		const opt = (v, l, cur) => `<option value="${fd_esc(v)}" ${v === cur ? 'selected' : ''}>${fd_esc(l)}</option>`;
		this.$filters.html(`
			<select class="xd-input xd-f-ay" aria-label="${__('Academic Year')}">
				${opt('', __('All academic years'), f.academic_year)}
				${(o.academic_years || []).map((y) => opt(y, y === o.current_academic_year ? `${y} (${__('current')})` : y, f.academic_year)).join('')}
			</select>
			<select class="xd-input xd-f-programme" aria-label="${__('Programme')}">
				${opt('', __('All programmes'), f.programme)}${(o.programmes || []).map((p) => opt(p, p, f.programme)).join('')}
			</select>
			<select class="xd-input xd-f-batch" aria-label="${__('Batch')}">
				${opt('', __('All batches'), f.batch)}${(o.batches || []).map((b) => opt(b, b, f.batch)).join('')}
			</select>
			${f.programme || f.batch ? `<button class="xd-clear">${__('Clear filters')}</button>` : ''}`);
	}

	load() {
		const f = this.f;
		return frappe.call({
			method: FD_API + 'get_dashboard',
			args: { academic_year: f.academic_year, programme: f.programme, batch: f.batch },
		}).then((r) => {
			this.data = r.message || {};
			this.render();
		});
	}

	render() {
		const d = this.data;
		this.cards = [];
		this.$body.html((d.groups || []).map((g) => `<section class="xd-group">
			<h4>${fd_esc(g.title)}${g.note ? ` <small>${fd_esc(g.note)}</small>` : ''}</h4>
			<div class="xd-cards">${g.cards.map((c) => {
				const i = this.cards.push(c) - 1;
				const money = c.amount != null;
				const zero = money ? !c.amount : !c.count;
				return `<button class="xd-card ${zero ? 'zero' : ''}" data-i="${i}"
					title="${c.drill ? __('See {0} by programme, component…', [fd_esc(c.label)]) : __('Open the list')}">
					<span class="xd-label">${fd_esc(c.label)}</span>
					<b class="xd-value">${fd_esc(money ? fd_money(c.amount) : fd_num(c.count))}</b>
					<small>${money ? `${fd_esc(fd_count(c.count, c.count_label))}${c.hint ? ' · ' : ''}` : ''}${fd_esc(c.hint || '')}</small></button>`;
			}).join('')}</div></section>`).join(''));
	}

	// a card's records grouped by programme / batch / component / mode, with their amounts
	drill(card, group_by) {
		frappe.xcall(FD_API + 'get_breakdown', { doctype: card.doctype, filters: card.filters || {}, group_by }).then((r) => {
			if (this.dialog) this.dialog.hide();
			const d = this.dialog = new frappe.ui.Dialog({
				title: card.label,
				size: 'extra-large',
				fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
				primary_action_label: __('Open full list'),
				primary_action: () => { d.hide(); frappe.set_route('List', card.doctype, card.filters || {}); },
			});
			const label = (r.groups.find((g) => g.field === r.group_by) || {}).label;
			const total = (k) => r.rows.reduce((s, x) => s + (k ? x.sums[k] : x.count), 0);
			const $body = $(d.fields_dict.body.wrapper).addClass('xd xd-dd');
			$body.html(`<div class="xd-dd-bar">
					<div class="xd-period" role="group" aria-label="${__('Group by')}">
						${r.groups.map((g) => `<button class="${g.field === r.group_by ? 'on' : ''}" data-g="${g.field}" aria-pressed="${g.field === r.group_by}">${fd_esc(g.label)}</button>`).join('')}
					</div>
					<span class="xd-muted">${__('click a row to open those records')}</span>
				</div>
				<div class="xd-ct">${r.rows.length ? `<table class="xd-table">
					<thead><tr><th>${fd_esc(label)}</th><th class="num">${__('Records')}</th>
						${r.sums.map((s) => `<th class="num">${fd_esc(s.label)}</th>`).join('')}</tr></thead>
					<tbody>${r.rows.map((x, i) => `<tr>
						<td><button class="xd-cell-link" data-row="${i}">${fd_esc(x.value || __('Not set'))}</button></td>
						<td class="num">${fd_num(x.count)}</td>
						${r.sums.map((s) => `<td class="num">${fd_money(x.sums[s.field])}</td>`).join('')}</tr>`).join('')}
					</tbody>
					<tfoot><tr><th>${__('Total')}</th><th class="num">${fd_num(total())}</th>
						${r.sums.map((s) => `<th class="num">${fd_money(total(s.field))}</th>`).join('')}</tr></tfoot>
				</table>` : `<p class="xd-empty">${__('No records.')}</p>`}</div>`);
			$body.on('click', '[data-g]', (e) => this.drill(card, e.currentTarget.dataset.g));
			$body.on('click', '[data-row]', (e) => {
				const x = r.rows[+e.currentTarget.dataset.row];
				const f = Object.assign({}, card.filters || {});
				f[r.group_by] = x.value == null || x.value === '' ? ['is', 'not set'] : x.value;
				d.hide();
				frappe.set_route('List', card.doctype, f);
			});
			d.show();
		});
	}

	add_styles() {
		if (document.getElementById('fd-styles')) return;
		// card styles match the Examination / Attendance dashboards (.xd-*); added here in case they haven't loaded
		$('head').append(`<style id="fd-styles">
			.xd{display:flex;flex-direction:column;gap:18px;padding:6px 16px 40px;font-family:var(--er-font,Georgia,serif);font-size:13px}
			.xd-filters{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
			.xd-body{display:flex;flex-direction:column;gap:18px}
			.xd-input{font-family:inherit;font-size:12.5px;height:32px;border:1px solid var(--border-color);border-radius:8px;background:var(--control-bg,#fff);color:var(--text-color);padding:0 10px;max-width:280px}
			.xd-input:focus{outline:none;border-color:var(--er-brand,#920C24)}
			.xd-clear{font:inherit;font-size:12px;font-weight:700;border:0;background:none;color:var(--er-brand,#920C24);cursor:pointer}
			.xd-dd{padding:0;gap:10px}.xd-dd-bar{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
			.xd-ct{background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;overflow:auto;max-height:60vh;position:relative}
			.xd-table{width:100%;border-collapse:collapse;font-size:12.5px}
			.xd-table th{position:sticky;top:0;background:var(--card-bg);text-align:left;font-weight:700;color:var(--text-muted);font-size:11.5px;padding:8px 10px;border-bottom:1px solid var(--border-color);white-space:nowrap}
			.xd-table tfoot th{position:sticky;bottom:0;color:var(--text-color);border-top:1px solid var(--border-color);border-bottom:0}
			.xd-table td{padding:8px 10px;border-bottom:1px solid var(--border-color);vertical-align:top}
			.xd-table .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
			.xd-cell-link{font:inherit;border:0;background:none;padding:0;color:var(--text-color);font-weight:700;cursor:pointer;text-align:left}
			.xd-cell-link:hover{color:var(--er-brand,#920C24);text-decoration:underline}
			.xd-empty{color:var(--text-muted);margin:0;padding:14px}
			.xd-muted{color:var(--text-muted);font-size:12px;margin:0}
			.xd-period{display:inline-flex;flex-wrap:wrap;border:1px solid var(--border-color);border-radius:8px;overflow:hidden;background:var(--card-bg)}
			.xd-period button{font:inherit;font-size:12.5px;font-weight:700;border:0;border-right:1px solid var(--border-color);background:none;color:var(--text-color);padding:6px 12px;cursor:pointer}
			.xd-period button:last-child{border-right:0}
			.xd-period button:hover{color:var(--er-brand,#920C24)}
			.xd-period button.on{background:var(--er-brand,#920C24);color:#fff}
			.xd-group h4{font-size:14px;font-weight:700;margin:0 0 8px}.xd-group h4 small{font-weight:400;color:var(--text-muted);font-size:12px;margin-left:6px}
			.xd-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
			.xd-card{display:flex;flex-direction:column;align-items:flex-start;gap:4px;text-align:left;font:inherit;color:var(--text-color);
				background:var(--card-bg);border:1px solid var(--border-color);border-left:3px solid var(--er-brand,#920C24);border-radius:10px;padding:12px 14px;cursor:pointer}
			.xd-card:hover{border-color:var(--er-brand,#920C24);box-shadow:0 2px 10px rgba(146,12,36,.08)}
			.xd-card.zero{border-left-color:var(--border-color)}.xd-card.zero .xd-value{color:var(--text-muted)}
			.xd-label{font-size:12px;color:var(--text-muted)}
			.xd-value{font-size:24px;line-height:1.15;font-weight:700;font-variant-numeric:tabular-nums;word-break:break-word}
			.xd-card small{font-size:11.5px;color:var(--text-muted);min-height:16px}
			@media (max-width:600px){.xd-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.xd-value{font-size:19px}}
		</style>`);
	}
}
