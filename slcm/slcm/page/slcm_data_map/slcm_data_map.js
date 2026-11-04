// SLCM Data Entry Map: the modules in the order their data is entered, built from
// each module's sidebar (see slcm_data_map.py). Click a record type to open its list.
frappe.pages['slcm-data-map'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('SLCM Data Entry Map'), single_column: true });
	$(wrapper).addClass('dm-theme');
	if (!document.getElementById('er-theme-font')) {
		$('head').append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	dm_styles();
	wrapper.data_map = new DataMap(page);
};

frappe.pages['slcm-data-map'].on_page_show = function (wrapper) {
	if (wrapper.data_map && wrapper.data_map.data) wrapper.data_map.load();
};

const dm_esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));
const dm_num = (v) => format_number(v || 0, null, 0);
const DM_LIMIT = 8;

class DataMap {
	constructor(page) {
		this.page = page;
		this.q = '';
		this.expanded = new Set();   // module keys showing every record type
		this.$root = $(`<div class="dm">
			<header class="dm-head">
				<h1>${__('Data Entry Map')}</h1>
				<p>${__('Enter data module by module, from top to bottom. Each module lists what it needs first. Click any record type to open its list; the number is how many records exist.')}</p>
			</header>
			<section class="dm-quick" data-slot="quick"></section>
			<div class="dm-bar">
				<input type="search" class="dm-input" placeholder="${__('Find a record type')}" aria-label="${__('Find a record type')}">
				<span class="dm-muted" data-slot="info"></span>
			</div>
			<div class="dm-grid" data-slot="modules"></div>
		</div>`).appendTo(page.main);
		page.set_primary_action(__('Print'), () => window.print(), 'printer');
		page.add_inner_button(__('Refresh'), () => this.load());
		this.$root.on('input', '.dm-input', (e) => { this.q = e.target.value.trim().toLowerCase(); this.render_modules(); });
		this.$root.on('click', '[data-dt]', (e) => {
			const b = e.currentTarget;
			if (b.dataset.single) frappe.set_route('Form', b.dataset.dt);
			else frappe.set_route('List', b.dataset.dt);
		});
		this.$root.on('click', '[data-more]', (e) => {
			const k = e.currentTarget.dataset.more;
			this.expanded.has(k) ? this.expanded.delete(k) : this.expanded.add(k);
			this.render_modules();
		});
		this.$root.on('click', '[data-ws]', (e) => frappe.set_route(frappe.router.slug(e.currentTarget.dataset.ws)));
		this.load();
	}

	load() {
		return frappe.xcall('slcm.slcm.page.slcm_data_map.slcm_data_map.get_map').then((d) => {
			this.data = d;
			this.render_quick();
			this.render_modules();
		});
	}

	render_quick() {
		const q = this.data.quickstart || [];
		const next = q.findIndex((x) => !x.count);
		this.$root.find('[data-slot="quick"]').html(`
			<div class="dm-quick-head">
				<span class="dm-tag">${__('Quick start')}</span>
				<h2>${__('The shortest path to a published result')}</h2>
			</div>
			<ol class="dm-path">${q.map((x, i) => `<li>
				<button class="dm-step ${x.count ? 'done' : i === next ? 'next' : ''}" data-dt="${dm_esc(x.doctype)}">
					<span class="dm-step-n">${x.count ? '✓' : i + 1}</span>${dm_esc(x.label)}<em>${dm_num(x.count)}</em>
				</button></li>`).join('')}</ol>
			${next === -1 ? `<p class="dm-quick-note">${__('Every step has data.')}</p>`
				: `<p class="dm-quick-note">${__('Next: add {0}.', [`<b>${dm_esc(q[next].label)}</b>`])}</p>`}`);
	}

	render_modules() {
		const q = this.q;
		let shown = 0;
		const html = (this.data.modules || []).map((m) => {
			const sections = m.sections.map((s) => ({
				label: s.label,
				docs: s.docs.filter((d) => !q || `${d.label} ${d.doctype} ${m.title}`.toLowerCase().includes(q)),
			})).filter((s) => s.docs.length);
			if (!sections.length) return '';
			const count = sections.reduce((a, s) => a + s.docs.length, 0);
			shown += count;
			// long modules show their first DM_LIMIT record types until expanded
			const open = q || count <= DM_LIMIT || this.expanded.has(m.key);
			let left = open ? Infinity : DM_LIMIT;
			const visible = sections.map((s) => {
				const docs = s.docs.slice(0, Math.max(0, left));
				left -= docs.length;
				return { label: s.label, docs };
			}).filter((s) => s.docs.length);
			return `<article class="dm-card">
				<div class="dm-card-head">
					<span class="dm-num">${m.num}</span>
					<div class="dm-card-title"><h3>${dm_esc(m.title)}</h3>
						<small>${m.needs ? `${__('Needs')}: ${dm_esc(m.needs)}` : __('No dependencies — start here')}</small></div>
					<span class="dm-total" title="${__('Records in this module')}">${dm_num(m.total)}</span>
				</div>
				<p class="dm-about">${dm_esc(m.about)}</p>
				${visible.map((s) => `<div class="dm-sec">
					<h4>${dm_esc(s.label)}</h4>
					${s.docs.map((d) => `<button class="dm-doc" data-dt="${dm_esc(d.doctype)}" ${d.single ? 'data-single="1"' : ''}>
						<span>${dm_esc(d.label)}</span>
						${d.single ? `<em class="dm-pill set">${__('Settings')}</em>`
							: `<em class="dm-pill ${d.count ? '' : 'zero'}">${dm_num(d.count)}</em>`}
					</button>`).join('')}
				</div>`).join('')}
				${count > DM_LIMIT && !q ? `<button class="dm-more" data-more="${dm_esc(m.key)}">${open
					? __('Show fewer') : __('Show all {0}', [count])}</button>` : ''}
				${m.workspace ? `<button class="dm-open" data-ws="${dm_esc(m.workspace)}">${__('Open {0}', [dm_esc(m.title)])} →</button>` : ''}
			</article>`;
		}).join('');
		this.$root.find('[data-slot="modules"]').html(html || `<p class="dm-muted">${__('No record type matches.')}</p>`);
		const n = (this.data.modules || []).length;
		this.$root.find('[data-slot="info"]').text(q ? __('{0} record types match', [shown]) : __('{0} modules', [n]));
	}
}

function dm_styles() {
	if (document.getElementById('dm-styles')) return;
	$('head').append(`<style id="dm-styles">
		.dm-theme .page-head .title-text, .dm, .dm button, .dm input { font-family: "Merriweather", Georgia, "Times New Roman", serif; }
		.dm { --dm-brand: #920C24; --dm-brand-dark: #6E091B; --dm-border: #E8B4BE; --dm-soft: #FBEEF0;
			color: var(--text-color); font-size: 13px; line-height: 1.55; padding: 8px 16px 48px; display: flex; flex-direction: column; gap: 18px; }
		.dm button { cursor: pointer; }
		.dm h1, .dm h2, .dm h3, .dm h4, .dm p { margin: 0; }
		.dm-muted { color: var(--text-muted); font-size: 12px; }
		.dm-head { padding-bottom: 14px; border-bottom: 1px solid var(--border-color); }
		.dm-head h1 { font-size: 22px; font-weight: 700; }
		.dm-head p { color: var(--text-muted); margin-top: 4px; max-width: 720px; }
		.dm-tag { font-size: 10.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #F5D9DE; }
		.dm-quick { background: var(--dm-brand); color: #fff; border-radius: 12px; padding: 16px 18px; }
		.dm-quick h2 { font-size: 16px; font-weight: 700; margin-top: 2px; color: #fff; }
		.dm-path { list-style: none; margin: 12px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
		.dm-path li { display: flex; align-items: center; }
		.dm-path li:not(:last-child)::after { content: "→"; margin-left: 8px; color: #E8B4BE; }
		.dm-step { display: inline-flex; align-items: center; gap: 7px; border: 1px solid rgba(255,255,255,.35); background: transparent; color: #fff;
			border-radius: 999px; padding: 4px 10px 4px 5px; font-size: 12px; font-weight: 700; }
		.dm-step:hover { background: rgba(255,255,255,.12); }
		.dm-step.done { background: #fff; color: var(--dm-brand); border-color: #fff; }
		.dm-step.next { border: 1.5px dashed #fff; }
		.dm-step-n { width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center; font-size: 11px;
			background: rgba(255,255,255,.18); }
		.dm-step.done .dm-step-n { background: var(--dm-soft); }
		.dm-step em { font-style: normal; font-weight: 400; font-size: 11px; opacity: .8; }
		.dm-quick-note { margin-top: 10px; font-size: 12px; color: #F5D9DE; }
		.dm-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
		.dm-input { height: 34px; width: 320px; max-width: 100%; border: 1px solid var(--border-color); border-radius: 8px; padding: 0 12px;
			background: var(--control-bg, #fff); color: var(--text-color); font-size: 12.5px; }
		.dm-input:focus { outline: none; border-color: var(--dm-brand); }
		.dm-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; align-items: start; }
		.dm-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; }
		.dm-card-head { display: flex; align-items: center; gap: 10px; }
		.dm-num { flex: none; width: 28px; height: 28px; border-radius: 50%; background: var(--dm-soft); color: var(--dm-brand);
			border: 1px solid var(--dm-border); display: grid; place-items: center; font-weight: 700; font-size: 12px; }
		.dm-card-title { flex: 1; min-width: 0; }
		.dm-card-title h3 { font-size: 14.5px; font-weight: 700; }
		.dm-card-title small { display: block; color: var(--text-muted); font-size: 11.5px; }
		.dm-total { font-weight: 700; font-size: 13px; color: var(--dm-brand); font-variant-numeric: tabular-nums; }
		.dm-about { color: var(--text-muted); font-size: 12px; }
		.dm-sec { border-top: 1px solid var(--border-color); padding-top: 6px; }
		.dm-sec h4 { font-size: 10.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--dm-brand); margin: 2px 0 2px; }
		.dm-doc { display: flex; justify-content: space-between; align-items: center; gap: 10px; width: 100%; text-align: left;
			border: 0; background: none; color: inherit; padding: 4px 6px; margin: 0 -6px; border-radius: 6px; font-size: 12.5px; width: calc(100% + 12px); }
		.dm-doc:hover { background: var(--dm-soft); }
		.dm-doc:hover span { color: var(--dm-brand); }
		.dm-pill { font-style: normal; font-size: 11px; font-weight: 700; border-radius: 999px; padding: 0 8px; min-width: 26px; text-align: center;
			background: var(--dm-soft); color: var(--dm-brand); font-variant-numeric: tabular-nums; }
		.dm-pill.zero { background: var(--gray-100, #f3f4f6); color: var(--text-muted); font-weight: 400; }
		.dm-pill.set { background: none; color: var(--text-muted); font-weight: 400; }
		.dm-more { align-self: flex-start; border: 1px solid var(--border-color); background: var(--card-bg); color: var(--text-color);
			border-radius: 999px; padding: 2px 12px; font-size: 11.5px; font-weight: 700; }
		.dm-more:hover { border-color: var(--dm-brand); color: var(--dm-brand); }
		.dm-open { align-self: flex-start; margin-top: 4px; border: 0; background: none; padding: 0; color: var(--dm-brand); font-weight: 700; font-size: 12px; }
		.dm-open:hover { text-decoration: underline; }
		@media (max-width: 1100px) { .dm-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
		@media (max-width: 680px) { .dm-grid { grid-template-columns: minmax(0, 1fr); } }
		@media print {
			.dm-bar, .dm-open, .dm-more { display: none; }
			.dm-quick { background: none; color: #000; border: 1px solid #999; }
			.dm-step, .dm-step.done { color: #000; border-color: #999; background: none; }
			.dm-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
			.dm-card { break-inside: avoid; }
		}
	</style>`);
}
