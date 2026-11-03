// Examination Dashboard: count cards of what has been created (see exam_dashboard.py),
// for all exam plans or one. A card opens its list with the same filters.
frappe.pages['exam-dashboard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Examination Dashboard'), single_column: true });
	$(wrapper).addClass('er-theme');
	if (!document.getElementById('er-theme-font')) {
		$('head').append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	frappe.require('/assets/slcm/css/exam_results_theme.css');
	wrapper.dashboard = new ExamDashboard(page);
};

frappe.pages['exam-dashboard'].on_page_show = function (wrapper) {
	if (wrapper.dashboard && wrapper.dashboard.data) wrapper.dashboard.load();
};

const xd_esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));
// child tables of Exam Plan have no list of their own; their cards open the planner
const XD_CHILD = ['Exam Course Schedule', 'Exam Reexam Schedule'];

class ExamDashboard {
	constructor(page) {
		this.page = page;
		this.plan = '';   // '' = all exam plans
		this.$root = $('<div class="xd"></div>').appendTo(page.main);
		page.set_primary_action(__('Open Exam Planner'), () => frappe.set_route('examination-planner', this.plan || undefined), 'external-link');
		page.add_inner_button(__('Refresh'), () => this.load());
		this.add_styles();
		this.$root.on('change', '.xd-plan', (e) => { this.plan = $(e.target).val(); this.load(); });
		this.$root.on('click', '.xd-card', (e) => this.open(this.cards[+$(e.currentTarget).data('i')]));
		this.load();
	}

	load() {
		return frappe.call({
			method: 'slcm.slcm.page.exam_dashboard.exam_dashboard.get_dashboard',
			args: { exam_plan: this.plan || '' },
		}).then((r) => {
			this.data = r.message || {};
			this.render();
		});
	}

	open(card) {
		if (!card) return;
		if (XD_CHILD.includes(card.doctype)) {
			if (card.step !== null && card.step !== undefined) frappe.flags.exam_planner_open = { step: card.step };
			frappe.set_route('examination-planner', this.plan || undefined);
			return;
		}
		frappe.set_route('List', card.doctype, card.filters || {});
	}

	render() {
		const d = this.data;
		this.cards = [];
		const plan = (d.plans || []).find((p) => p.name === d.exam_plan);
		this.$root.html(`
			<div class="xd-head">
				<label class="xd-muted" for="xd-plan">${__('Showing')}</label>
				<select id="xd-plan" class="form-control xd-plan">
					<option value="">${__('All exam plans')}</option>
					${(d.plans || []).map((p) => `<option value="${xd_esc(p.name)}" ${p.name === d.exam_plan ? 'selected' : ''}>${xd_esc(p.exam_name || p.name)}</option>`).join('')}
				</select>
				<span class="xd-muted">${plan ? xd_esc(plan.term || '') : __('{0} exam plan(s)', [(d.plans || []).length])}</span>
			</div>
			${(d.groups || []).map((g) => `<section class="xd-group">
				<h4>${xd_esc(g.title)}${g.note ? ` <small>${xd_esc(g.note)}</small>` : ''}</h4>
				<div class="xd-cards">${g.cards.map((c) => {
					const i = this.cards.push(c) - 1;
					return `<button class="xd-card ${c.value ? '' : 'zero'}" data-i="${i}" title="${__('Open {0}', [xd_esc(c.label)])}">
						<span class="xd-label">${xd_esc(c.label)}</span>
						<b class="xd-value">${xd_esc(c.value)}</b>
						<small>${xd_esc(c.hint || '')}</small></button>`;
				}).join('')}</div></section>`).join('')}`);
	}

	add_styles() {
		if (document.getElementById('xd-styles')) return;
		$('head').append(`<style id="xd-styles">
			.xd{display:flex;flex-direction:column;gap:18px;padding:6px 0 40px;font-family:var(--er-font,Georgia,serif);font-size:13px}
			.xd-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.xd-plan{max-width:360px;font-family:inherit}
			.xd-muted{color:var(--text-muted);font-size:12px;margin:0}
			.xd-group h4{font-size:14px;font-weight:700;margin:0 0 8px}.xd-group h4 small{font-weight:400;color:var(--text-muted);font-size:12px;margin-left:6px}
			.xd-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
			.xd-card{display:flex;flex-direction:column;align-items:flex-start;gap:4px;text-align:left;font:inherit;color:var(--text-color);
				background:var(--card-bg);border:1px solid var(--border-color);border-left:3px solid var(--er-brand,#920C24);border-radius:10px;padding:12px 14px;cursor:pointer}
			.xd-card:hover{border-color:var(--er-brand,#920C24);box-shadow:0 2px 10px rgba(146,12,36,.08)}
			.xd-card.zero{border-left-color:var(--border-color)}.xd-card.zero .xd-value{color:var(--text-muted)}
			.xd-label{font-size:12px;color:var(--text-muted)}
			.xd-value{font-size:26px;line-height:1.15;font-weight:700;font-variant-numeric:tabular-nums}
			.xd-card small{font-size:11.5px;color:var(--text-muted);min-height:16px}
			@media (max-width:600px){.xd-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.xd-value{font-size:22px}}
		</style>`);
	}
}
