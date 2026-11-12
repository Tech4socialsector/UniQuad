// Uniquad Roles & Permissions: same model as Pathways > Settings > Roles & Permissions.
// Roles on the left; for the chosen role, a Permissions grid over every Uniquad DocType
// (saved as Custom DocPerm on each click) and a Users tab. Rules live in the .py.
frappe.pages['uniquad-roles-permissions'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Roles & Permissions'), single_column: true });
	$(wrapper).addClass('er-theme');
	if (!document.getElementById('er-theme-font')) {
		$('head').append('<link id="er-theme-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	frappe.require('/assets/slcm/css/exam_results_theme.css');
	wrapper.access = new UniquadAccess(page);
};

const ua_esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));
const UA_API = 'slcm.slcm.page.uniquad_roles_permissions.uniquad_roles_permissions.';
const UA_PTYPE_LABEL = (p) => p.charAt(0).toUpperCase() + p.slice(1);
const UA_TABS = [
	{ key: 'permissions', label: 'Document Types' },
	{ key: 'pages', label: 'Pages & Reports' },
	{ key: 'icons', label: 'Desktop Icons' },
	{ key: 'portals', label: 'Portals' },
];

class UniquadAccess {
	constructor(page) {
		this.page = page;
		this.data = null;
		this.role = '';
		this.tab = 'permissions';
		this.q = { role: '', doctype: '', module: '', granted: false, item: '', item_type: '' };
		this.busy = new Set();
		this.$root = $('<div class="ua"></div>').appendTo(page.main);
		page.set_primary_action(__('New Role'), () => this.new_role(), 'add');
		page.add_inner_button(__('New Staff User'), () => this.new_user());
		page.add_inner_button(__('Role Permission Manager'), () => frappe.set_route('permission-manager'));
		this.add_styles();
		this.render_shell();
		this.bind();
		this.load();
	}

	call(method, args) {
		return frappe.xcall(UA_API + method, args);
	}

	async load() {
		try {
			this.data = await this.call('get_access_matrix');
		} catch (e) {
			this.$roles.html(`<div class="ua-muted">${__('Could not load roles and permissions.')}</div>`);
			return;
		}
		const roles = this.data.roles;
		if (!roles.find((r) => r.role === this.role) && roles.length) {
			this.role = (roles.find((r) => r.editable) || roles[0]).role;
		}
		this.render_modules();
		this.render_roles();
		this.render_role();
	}

	get selected() {
		return (this.data?.roles || []).find((r) => r.role === this.role) || null;
	}

	// ----------------------------------------------------------------- layout
	render_shell() {
		this.$root.html(`
			<p class="ua-intro">${__('Choose what each Uniquad role can see and do, and who holds each role.')}</p>
			<div class="ua-card">
				<aside class="ua-side">
					<input class="ua-input ua-role-q" placeholder="${__('Search roles...')}">
					<div class="ua-roles"><div class="ua-muted">${__('Loading...')}</div></div>
				</aside>
				<section class="ua-main"></section>
			</div>
			<p class="ua-foot">${frappe.utils.icon('check', 'sm')} ${__('Changes on this page are saved as you make them.')}</p>`);
		this.$roles = this.$root.find('.ua-roles');
		this.$main = this.$root.find('.ua-main');
	}

	render_roles() {
		const q = this.q.role.trim().toLowerCase();
		const rows = this.data.roles.filter((r) => !q || r.role.toLowerCase().includes(q));
		this.$roles.html(rows.map((r) => `
			<button class="ua-role ${r.role === this.role ? 'active' : ''}" data-role="${ua_esc(r.role)}" title="${ua_esc(r.role)}">
				<span class="ua-role-name">${ua_esc(r.role)}</span>
				<span class="ua-role-meta">
					${r.editable ? '' : frappe.utils.icon('lock', 'xs')}
					<span class="ua-count">${r.users}</span>
				</span>
			</button>`).join('') || `<div class="ua-muted">${__('No roles match.')}</div>`);
	}

	render_modules() {
		this.modules_html = [`<option value="">${__('All modules')}</option>`]
			.concat(this.data.modules.map((m) => `<option value="${ua_esc(m)}" ${m === this.q.module ? 'selected' : ''}>${ua_esc(m)}</option>`))
			.join('');
	}

	role_note(r) {
		if (!r.editable) return __('Portal role: its document permissions are fixed because the student, parent and applicant portals rely on them. Which portal it may open is set on the Portals tab.');
		if (r.disabled) return __('This role is disabled, so its permissions have no effect.');
		if (!r.desk_access) return __('No desk access: users with only this role work through the portals, which use these permissions.');
		return __('Users with this role see every record of the document types they can read, unless a Uniquad rule narrows it (marked Row rules).');
	}

	render_role() {
		const r = this.selected;
		if (!r) {
			this.$main.html(`<div class="ua-empty">${__('Choose a role.')}</div>`);
			return;
		}
		const removable = r.editable && !r.grants && !r.role.startsWith('slcm_');
		this.$main.html(`
			<div class="ua-head">
				<div class="ua-head-text">
					<div class="ua-title">${ua_esc(r.role)}</div>
					<div class="ua-sub">${this.role_note(r)}</div>
				</div>
				<div class="ua-head-actions">
					<div class="ua-tabs">
						${UA_TABS.map((t) => `<button class="ua-tab ${this.tab === t.key ? 'active' : ''}" data-tab="${t.key}">${__(t.label)}</button>`).join('')}
						<button class="ua-tab ${this.tab === 'users' ? 'active' : ''}" data-tab="users">${__('Users')} (${r.users})</button>
					</div>
					${removable ? `<button class="ua-link-danger ua-remove-role">${__('Remove')}</button>` : ''}
				</div>
			</div>
			<div class="ua-body"></div>`);
		this.$body = this.$main.find('.ua-body');
		if (this.tab === 'permissions') this.render_permissions();
		else if (this.tab === 'pages') this.render_items('pages');
		else if (this.tab === 'icons') this.render_items('icons');
		else if (this.tab === 'portals') this.render_items('portals');
		else this.render_users();
	}

	// ------------------------------------- pages & reports, desktop icons, portals
	// One grid shape for all three: a row per item with a single "allowed" tick.
	// An item with no roles is open to everyone (Frappe's rule) and shows ticked.
	render_items(kind) {
		const tools = kind === 'portals' ? '' : `
			<div class="ua-tools">
				<input class="ua-input ua-item-q" placeholder="${__(kind === 'pages' ? 'Search pages and reports...' : 'Search desktop icons...')}" value="${ua_esc(this.q.item)}">
				${kind === 'pages' ? `<select class="ua-input ua-item-type">
					${[['', 'Pages and reports'], ['Page', 'Pages'], ['Report', 'Reports']].map(([v, l]) => `<option value="${v}" ${v === this.q.item_type ? 'selected' : ''}>${__(l)}</option>`).join('')}
				</select><select class="ua-input ua-module">${this.modules_html}</select>` : ''}
				<label class="ua-check"><input type="checkbox" class="ua-granted" ${this.q.granted ? 'checked' : ''}> ${__('Only show granted')}</label>
			</div>`;
		const info = {
			pages: __('A ticked page or report opens for this role. One with no roles at all is open to everyone; unticking it restricts it to every other Uniquad role and System Manager. A report also needs Read on its document type. Changes are kept as a Custom Role, so the shipped page files stay untouched; Reset goes back to them.'),
			icons: __('A ticked icon shows on the desk home screen for this role. An icon inside a folder shows only when its folder shows too, and a sidebar icon also needs Read on at least one document type in its sidebar. An icon with no roles is open to everyone who can see its sidebar.'),
			portals: __('Users must hold one of the ticked roles to open a portal; they still need their own Faculty, Student Master or parent record inside it. Students, parents and applicants keep their fixed document permissions, but which portal they may enter is set here.'),
		}[kind];
		const head = {
			pages: [__('Page / Report'), __('Type')],
			icons: [__('Desktop Icon'), __('Shows')],
			portals: [__('Portal'), __('Roles allowed')],
		}[kind];
		this.$body.html(`${tools}
			<div class="ua-info">${info}</div>
			<div class="ua-table-wrap">
				<table class="ua-table">
					<thead><tr><th>${head[0]}</th><th>${head[1]}</th><th class="c">${__('Access')}</th><th></th></tr></thead>
					<tbody></tbody>
				</table>
			</div>`);
		this.item_kind = kind;
		this.render_item_rows();
	}

	item_key(kind, it) {
		return kind === 'pages' ? `${it.kind}::${it.name}` : (it.key || it.name);
	}

	item_open(it) {
		return !it.roles.length;
	}

	item_granted(it) {
		return this.item_open(it) || it.roles.includes(this.role);
	}

	render_item_rows() {
		const kind = this.item_kind;
		const r = this.selected;
		const q = (this.q.item || '').trim().toLowerCase();
		const locked = kind !== 'portals' && !r.editable;
		const rows = this.data[kind].filter((it) => {
			if (kind === 'pages' && this.q.item_type && it.kind !== this.q.item_type) return false;
			if (kind === 'pages' && this.q.module && it.module !== this.q.module) return false;
			if (q && !`${it.title || it.label} ${it.name} ${it.detail || ''} ${it.sidebar || ''}`.toLowerCase().includes(q)) return false;
			if (kind !== 'portals' && this.q.granted && !it.roles.includes(this.role)) return false;
			return true;
		});
		const html = rows.map((it) => {
			const key = this.item_key(kind, it);
			const busy = this.busy.has(key);
			let name, second, tags = [];
			if (kind === 'pages') {
				const href = it.kind === 'Page' ? `/desk/${encodeURIComponent(it.name)}` : `/desk/query-report/${encodeURIComponent(it.name)}`;
				name = `<a href="${href}" class="ua-dt-name">${ua_esc(it.title)}</a>`;
				second = ua_esc(it.kind === 'Report' ? `${it.report_type || ''} ${__('Report')}`.trim() : __('Page'));
				tags.push(ua_esc(it.module));
				if (it.detail) tags.push(`${__('On')}: ${ua_esc(it.detail)}`);
			} else if (kind === 'icons') {
				name = `<span class="ua-dt-name ${it.parent ? 'ua-indent' : ''}">${ua_esc(it.label)}</span>`;
				second = it.icon_type === 'App' ? __('Folder of icons') : it.sidebar ? `${__('Sidebar')}: ${ua_esc(it.sidebar)}` : ua_esc(it.icon_type);
				if (it.parent) tags.push(`${__('In')}: ${ua_esc(it.parent)}`);
				if (it.hidden) tags.push(__('Hidden'));
				if (it.external) tags.push(__('Other app'));
			} else {
				name = `<a href="${it.route}" target="_blank" class="ua-dt-name">${ua_esc(it.label)}</a>`;
				second = it.roles.map((x) => `<span class="ua-chip ${x === this.role ? 'me' : ''}">${ua_esc(x)}</span>`).join(' ');
				tags.push(ua_esc(it.route));
			}
			const extra = (this.item_open(it) && kind !== 'portals' ? [`<span class="ua-tag ua-tag-blue">${__('Open to everyone')}</span>`] : [])
				.concat(it.customised ? [`<span class="ua-tag ua-tag-amber">${__('Customised')}</span>`] : []);
			return `<tr>
				<td><div>${name}</div><div class="ua-tags ${kind === 'icons' && it.parent ? 'ua-indent' : ''}">${tags.map((t) => `<span class="ua-tag">${t}</span>`).join('')}${extra.join('')}</div></td>
				<td class="ua-second">${second}</td>
				<td class="c"><input type="checkbox" class="ua-item" data-key="${ua_esc(key)}"
					aria-label="${ua_esc((it.title || it.label) + ' ' + __('access'))}"
					${this.item_granted(it) ? 'checked' : ''} ${locked || busy ? 'disabled' : ''}></td>
				<td class="r">${it.customised && kind !== 'icons' ? `<button class="ua-btn-ghost ua-item-reset" data-key="${ua_esc(key)}" ${busy ? 'disabled' : ''}>${__('Reset')}</button>` : ''}</td>
			</tr>`;
		}).join('');
		this.$body.find('tbody').html(html || `<tr><td colspan="4" class="ua-muted c">${__('Nothing matches.')}</td></tr>`);
	}

	find_item(kind, key) {
		return this.data[kind].find((it) => this.item_key(kind, it) === key);
	}

	toggle_item(key, value, $box) {
		const kind = this.item_kind;
		const it = this.find_item(kind, key);
		if (!it) return;
		const run = () => this.save_item(kind, it, key, value);
		if (!value && this.item_open(it) && kind !== 'portals') {
			frappe.confirm(
				__('{0} is open to everyone. Unticking it for {1} restricts it to every other Uniquad role and System Manager. Continue?', [`<b>${ua_esc(it.title || it.label)}</b>`, `<b>${ua_esc(this.role)}</b>`]),
				run,
				() => $box.prop('checked', true)
			);
		} else {
			run();
		}
	}

	async save_item(kind, it, key, value) {
		const role = this.role;
		const v = value ? 1 : 0;
		this.busy.add(key);
		this.render_item_rows();
		try {
			const res = kind === 'pages'
				? await this.call('set_page_role', { kind: it.kind, name: it.name, role, value: v })
				: kind === 'icons'
					? await this.call('set_icon_role', { icon: it.name, role, value: v })
					: await this.call('set_portal_role', { portal: it.key, role, value: v });
			it.roles = res.roles;
			if (kind !== 'icons') it.customised = true;
		} catch (e) {
			await this.load();
		} finally {
			this.busy.delete(key);
			if (this.tab === kind) this.render_item_rows();
		}
	}

	reset_item(key) {
		const kind = this.item_kind;
		const it = this.find_item(kind, key);
		if (!it) return;
		const label = it.title || it.label;
		frappe.confirm(
			__('Reset {0} to the roles shipped with Uniquad? This affects every role, not just {1}.', [`<b>${ua_esc(label)}</b>`, `<b>${ua_esc(this.role)}</b>`]),
			async () => {
				if (kind === 'pages') await this.call('reset_page_roles', { kind: it.kind, name: it.name });
				else await this.call('reset_portal_roles', { portal: it.key });
				frappe.show_alert({ message: __('{0} reset to default.', [label]), indicator: 'green' });
				this.load();
			}
		);
	}

	// ------------------------------------------------------------ permissions
	render_permissions() {
		this.$body.html(`
			<div class="ua-tools">
				<input class="ua-input ua-dt-q" placeholder="${__('Search document types...')}" value="${ua_esc(this.q.doctype)}">
				<select class="ua-input ua-module">${this.modules_html}</select>
				<label class="ua-check"><input type="checkbox" class="ua-granted" ${this.q.granted ? 'checked' : ''}> ${__('Only show granted')}</label>
			</div>
			<div class="ua-info">
				<b>${__('Read')}</b> ${__('on a document type also shows its link in the workspace sidebar. Turning a permission on adds what it depends on (e.g. Amend → Cancel → Submit → Write → Read); turning one off removes what depends on it. Finer rules (if owner, higher levels, User Permissions) stay in the')}
				<a href="/desk/permission-manager">${__('Role Permission Manager')}</a>.
			</div>
			<div class="ua-table-wrap">
				<table class="ua-table">
					<thead><tr>
						<th>${__('Document Type')}</th>
						${this.data.ptypes.map((p) => `<th class="c">${__(UA_PTYPE_LABEL(p))}</th>`).join('')}
						<th></th>
					</tr></thead>
					<tbody></tbody>
				</table>
			</div>`);
		this.render_rows();
	}

	applies(dt, p) {
		if (['submit', 'cancel', 'amend'].includes(p)) return !!dt.is_submittable;
		if (['create', 'delete'].includes(p)) return !dt.is_single;
		return true;
	}

	granted(dt, p) {
		return !!this.data.matrix[this.role]?.[dt]?.[p];
	}

	render_rows() {
		const r = this.selected;
		const q = this.q.doctype.trim().toLowerCase();
		const ptypes = this.data.ptypes;
		const rows = this.data.doctypes.filter((dt) => {
			if (this.q.module && dt.module !== this.q.module) return false;
			if (q && !`${dt.name} ${dt.menus.join(' ')}`.toLowerCase().includes(q)) return false;
			if (this.q.granted && !ptypes.some((p) => this.granted(dt.name, p))) return false;
			return true;
		});
		const html = rows.map((dt) => {
			const busy = this.busy.has(dt.name);
			const cells = ptypes.map((p) => {
				if (!this.applies(dt, p)) return '<td class="c"><span class="ua-na">—</span></td>';
				return `<td class="c"><input type="checkbox" class="ua-perm" data-dt="${ua_esc(dt.name)}" data-p="${p}"
					aria-label="${ua_esc(UA_PTYPE_LABEL(p) + ' ' + dt.name)}"
					${this.granted(dt.name, p) ? 'checked' : ''} ${!r.editable || busy ? 'disabled' : ''}></td>`;
			}).join('');
			const tags = [`<span class="ua-tag">${ua_esc(dt.module)}</span>`]
				.concat(dt.menus.map((m) => `<span class="ua-tag">${__('Menu')}: ${ua_esc(m)}</span>`))
				.concat(dt.row_scoped ? [`<span class="ua-tag ua-tag-blue" title="${__('A Uniquad rule limits which records some roles see (e.g. a faculty member sees only their own courses).')}">${__('Row rules')}</span>`] : [])
				.concat(dt.customised ? [`<span class="ua-tag ua-tag-amber">${__('Customised')}</span>`] : [])
				.join('');
			return `<tr>
				<td><div class="ua-dt"><a href="/desk/${frappe.router.slug(dt.name)}" class="ua-dt-name">${ua_esc(dt.name)}</a></div><div class="ua-tags">${tags}</div></td>
				${cells}
				<td class="r">${dt.customised ? `<button class="ua-btn-ghost ua-reset" data-dt="${ua_esc(dt.name)}" ${busy ? 'disabled' : ''}>${__('Reset')}</button>` : ''}</td>
			</tr>`;
		}).join('');
		this.$body.find('tbody').html(html || `<tr><td colspan="${ptypes.length + 2}" class="ua-muted c">${__('No document types match.')}</td></tr>`);
	}

	async toggle(doctype, ptype, value) {
		const role = this.role;
		this.busy.add(doctype);
		this.render_rows();
		try {
			const res = await this.call('set_role_permission', { doctype, role, ptype, value: value ? 1 : 0 });
			const by_role = this.data.matrix[role] || (this.data.matrix[role] = {});
			if (Object.values(res.perms).some(Boolean)) by_role[doctype] = res.perms;
			else delete by_role[doctype];
			const dt = this.data.doctypes.find((d) => d.name === doctype);
			if (dt) dt.customised = true;
			const r = this.data.roles.find((x) => x.role === role);
			if (r) r.grants = Object.keys(by_role).length;
		} catch (e) {
			await this.load();
		} finally {
			this.busy.delete(doctype);
			if (this.role === role && this.tab === 'permissions') this.render_rows();
		}
	}

	reset(doctype) {
		frappe.confirm(
			__('Reset {0} to the permissions shipped with Uniquad? This affects every role, not just {1}.', [`<b>${ua_esc(doctype)}</b>`, `<b>${ua_esc(this.role)}</b>`]),
			async () => {
				await this.call('reset_doctype_permissions', { doctype });
				frappe.show_alert({ message: __('{0} reset to default.', [doctype]), indicator: 'green' });
				this.load();
			}
		);
	}

	// ------------------------------------------------------------------ users
	async render_users() {
		this.$body.html(`
			<div class="ua-add-user">
				<div class="ua-add-label">${__('Give this role to')}</div>
				<div class="ua-add-row"><div class="ua-user-field"></div><button class="btn btn-primary btn-sm ua-assign" disabled>${__('Add')}</button></div>
			</div>
			<div class="ua-users"><div class="ua-muted">${__('Loading...')}</div></div>`);
		this.user_field = frappe.ui.form.make_control({
			parent: this.$body.find('.ua-user-field'),
			df: {
				fieldtype: 'Link', options: 'User', fieldname: 'user', placeholder: __('Search users by name or email'),
				get_query: () => ({ filters: { enabled: 1, name: ['not in', ['Administrator', 'Guest']] } }),
				onchange: () => this.$body.find('.ua-assign').prop('disabled', !this.user_field.get_value()),
			},
			render_input: true,
		});
		this.load_users();
	}

	async load_users() {
		const role = this.role;
		let users;
		try {
			users = await this.call('get_role_users', { role });
		} catch (e) {
			users = [];
		}
		if (role !== this.role || this.tab !== 'users') return;
		const r = this.selected;
		if (r) {
			r.users = users.filter((u) => u.enabled).length;
			this.$main.find('.ua-tab[data-tab="users"]').text(`${__('Users')} (${r.users})`);
			this.render_roles();
		}
		this.$body.find('.ua-users').html(users.length ? `
			<div class="ua-table-wrap ua-table-plain"><table class="ua-table">
				<thead><tr><th>${__('Name')}</th><th>${__('Email')}</th><th>${__('Type')}</th><th></th></tr></thead>
				<tbody>${users.map((u) => `<tr>
					<td><b>${ua_esc(u.full_name || u.name)}</b>${u.enabled ? '' : ` <span class="ua-muted">(${__('disabled')})</span>`}</td>
					<td><a href="/desk/user/${encodeURIComponent(u.name)}">${ua_esc(u.name)}</a></td>
					<td>${u.user_type === 'System User' ? __('Staff') : __('Portal')}</td>
					<td class="r"><button class="ua-link-danger ua-unassign" data-user="${ua_esc(u.name)}">${__('Remove')}</button></td>
				</tr>`).join('')}</tbody>
			</table></div>` : `<div class="ua-empty">${__('Nobody has this role yet.')}</div>`);
	}

	async assign() {
		const user = this.user_field?.get_value();
		if (!user) return;
		await this.call('assign_role', { user, role: this.role });
		this.user_field.set_value('');
		this.load_users();
	}

	unassign(user) {
		frappe.confirm(__('Remove {0} from {1}?', [`<b>${ua_esc(user)}</b>`, `<b>${ua_esc(this.role)}</b>`]), async () => {
			await this.call('unassign_role', { user, role: this.role });
			this.load_users();
		});
	}

	// ---------------------------------------------------------------- dialogs
	new_role() {
		const d = new frappe.ui.Dialog({
			title: __('New Role'),
			fields: [
				{ fieldname: 'role_name', fieldtype: 'Data', label: __('Role name'), reqd: 1, placeholder: __('e.g. Hostel Accounts Officer') },
				{ fieldname: 'desk_access', fieldtype: 'Check', label: __('Desk access'), default: 1, description: __('Untick for a portal-only role.') },
				{ fieldtype: 'HTML', options: `<p class="text-muted small">${__('A new role starts with no permissions. Grant it access on the Permissions tab, then give it to users.')}</p>` },
			],
			primary_action_label: __('Create'),
			primary_action: async (v) => {
				const role = await this.call('create_role', v);
				d.hide();
				this.role = role;
				this.tab = 'permissions';
				this.q.role = '';
				this.$root.find('.ua-role-q').val('');
				this.load();
			},
		});
		d.show();
	}

	new_user() {
		const r = this.selected;
		const options = this.data.roles.filter((x) => x.editable).map((x) => ({ label: x.role, value: x.role, checked: r && r.editable && x.role === r.role }));
		const d = new frappe.ui.Dialog({
			title: __('New Staff User'),
			size: 'large',
			fields: [
				{ fieldname: 'email', fieldtype: 'Data', options: 'Email', label: __('Email'), reqd: 1 },
				{ fieldtype: 'Section Break' },
				{ fieldname: 'first_name', fieldtype: 'Data', label: __('First name'), reqd: 1 },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'last_name', fieldtype: 'Data', label: __('Last name') },
				{ fieldtype: 'Section Break' },
				{ fieldname: 'roles', fieldtype: 'MultiCheck', label: __('Roles'), columns: 3, options },
				{ fieldtype: 'HTML', options: `<p class="text-muted small">${__("They'll get an email with a link to set their password.")}</p>` },
			],
			primary_action_label: __('Create User'),
			primary_action: async (v) => {
				await this.call('create_staff_user', { ...v, roles: d.fields_dict.roles.get_checked_options() });
				d.hide();
				frappe.show_alert({ message: __('User created and invited.'), indicator: 'green' });
				this.load();
			},
		});
		d.show();
	}

	remove_role() {
		frappe.confirm(
			__('Remove {0} from this list? The role itself stays in the system and can be added back with New Role.', [`<b>${ua_esc(this.role)}</b>`]),
			async () => {
				await this.call('remove_role', { role: this.role });
				this.role = '';
				this.load();
			}
		);
	}

	render_current_rows() {
		if (this.tab === 'permissions') this.render_rows();
		else if (['pages', 'icons', 'portals'].includes(this.tab)) this.render_item_rows();
	}

	// ----------------------------------------------------------------- events
	bind() {
		const $r = this.$root;
		$r.on('click', '.ua-role', (e) => {
			this.role = $(e.currentTarget).data('role');
			this.render_roles();
			this.render_role();
		});
		$r.on('input', '.ua-role-q', (e) => {
			this.q.role = e.target.value;
			this.render_roles();
		});
		$r.on('click', '.ua-tab', (e) => {
			this.tab = $(e.currentTarget).data('tab');
			this.render_role();
		});
		$r.on('input', '.ua-dt-q', frappe.utils.debounce((e) => {
			this.q.doctype = e.target.value;
			this.render_rows();
		}, 150));
		$r.on('change', '.ua-module', (e) => {
			this.q.module = e.target.value;
			this.render_modules();
			this.render_current_rows();
		});
		$r.on('change', '.ua-granted', (e) => {
			this.q.granted = e.target.checked;
			this.render_current_rows();
		});
		$r.on('input', '.ua-item-q', frappe.utils.debounce((e) => {
			this.q.item = e.target.value;
			this.render_item_rows();
		}, 150));
		$r.on('change', '.ua-item-type', (e) => {
			this.q.item_type = e.target.value;
			this.render_item_rows();
		});
		$r.on('change', '.ua-item', (e) => {
			const $c = $(e.currentTarget);
			this.toggle_item(String($c.data('key')), e.target.checked, $c);
		});
		$r.on('click', '.ua-item-reset', (e) => {
			this.reset_item(String($(e.currentTarget).data('key')));
		});
		$r.on('change', '.ua-perm', (e) => {
			const $c = $(e.currentTarget);
			this.toggle($c.data('dt'), $c.data('p'), e.target.checked);
		});
		$r.on('click', '.ua-reset', (e) => {
			this.reset($(e.currentTarget).data('dt'));
		});
		$r.on('click', '.ua-assign', () => {
			this.assign();
		});
		$r.on('click', '.ua-unassign', (e) => {
			this.unassign($(e.currentTarget).data('user'));
		});
		$r.on('click', '.ua-remove-role', () => {
			this.remove_role();
		});
	}

	add_styles() {
		if (document.getElementById('ua-styles')) return;
		$('head').append(`<style id="ua-styles">
			#page-uniquad-roles-permissions .layout-main-section { padding: 0 16px; }
			.ua { font-family: var(--er-font); color: #1f2328; padding-bottom: 24px; }
			.ua-intro { color: #6b7280; margin: 4px 0 12px; font-size: 13px; }
			.ua-foot { color: #6b7280; margin: 14px 0 0; font-size: 12.5px; display: flex; align-items: center; justify-content: flex-start; gap: 6px; }
			.ua-foot svg { margin: 0; flex-shrink: 0; }
			.ua-card { display: flex; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; height: calc(100vh - 230px); min-height: 480px; overflow: hidden; }
			.ua-side { width: 280px; flex-shrink: 0; border-right: 1px solid #e5e7eb; display: flex; flex-direction: column; padding: 12px; gap: 8px; }
			.ua-roles { overflow-y: auto; flex: 1; min-height: 0; }
			.ua-input { border: 1px solid #e5e7eb; background: #f9fafb; border-radius: 6px; padding: 6px 10px; font-size: 13px; width: 100%; outline: none; }
			.ua-input:focus { border-color: var(--er-brand-border); background: #fff; }
			:where(.ua) button { font-family: inherit; }
			.ua-role { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 8px; border: 0; background: none; padding: 8px 10px; border-radius: 6px; text-align: left; font-size: 13px; color: #374151; margin-bottom: 1px; }
			.ua-role:hover { background: #f9fafb; }
			.ua-role.active { background: var(--er-brand-softest); color: var(--er-brand-dark); font-weight: 700; box-shadow: inset 3px 0 0 var(--er-brand); }
			.ua-role-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
			.ua-role-meta { display: flex; align-items: center; gap: 6px; flex-shrink: 0; color: #9ca3af; }
			.ua-count { background: #f3f4f6; color: #4b5563; border-radius: 4px; padding: 0 6px; font-size: 11.5px; }
			.ua-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
			.ua-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 20px; border-bottom: 1px solid #e5e7eb; }
			.ua-head-text { min-width: 0; flex: 1; }
			.ua-title { font-weight: 700; font-size: 15px; }
			.ua-sub { font-size: 12px; color: #6b7280; margin-top: 2px; }
			.ua-head-actions { display: flex; align-items: center; gap: 12px; }
			.ua-tabs { display: inline-flex; background: #f3f4f6; border-radius: 7px; padding: 2px; }
			.ua-tab { border: 0; background: none; padding: 4px 12px; border-radius: 5px; font-size: 13px; color: #6b7280; }
			.ua-tab.active { background: #fff; color: #111827; box-shadow: 0 1px 2px rgba(0,0,0,.08); }
			.ua-link-danger { border: 0; background: none; color: var(--er-brand); font-size: 13px; padding: 4px 6px; }
			.ua-link-danger:hover { text-decoration: underline; }
			.ua-body { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 16px 20px; overflow-y: auto; }
			.ua-tools { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 10px; }
			.ua-tools .ua-dt-q { width: 280px; }
			.ua-tools .ua-module { width: 160px; }
			.ua-tools .ua-item-q { width: 280px; }
			.ua-tools .ua-item-type { width: 180px; }
			.ua-check { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #4b5563; margin: 0 0 0 auto; font-weight: 400; }
			.ua-info { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; border-radius: 6px; padding: 8px 12px; font-size: 12px; margin-bottom: 10px; }
			.ua-info a { color: #1e40af; text-decoration: underline; }
			.ua-table-wrap { flex: 1; min-height: 0; overflow: auto; border: 1px solid #e5e7eb; border-radius: 8px; position: relative; }
			.ua-table-plain { flex: none; }
			.ua-table { width: 100%; font-size: 13px; border-collapse: separate; border-spacing: 0; }
			.ua-table th { position: sticky; top: 0; z-index: 1; background: #f9fafb; text-transform: uppercase; font-size: 11px; letter-spacing: .03em; color: #6b7280; padding: 9px 10px; border-bottom: 1px solid #e5e7eb; text-align: left; white-space: nowrap; }
			.ua-table td { padding: 8px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }
			.ua-table tr:last-child td { border-bottom: 0; }
			.ua-table .c { text-align: center; }
			.ua-table .r { text-align: right; }
			.ua-table input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; }
			.ua-table input[type="checkbox"]:disabled { opacity: .4; cursor: default; }
			.ua-dt-name { color: #111827 !important; font-weight: 700; }
			.ua-dt-name:hover { color: var(--er-brand) !important; }
			.ua-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 3px; }
			.ua-tag { background: #f3f4f6; color: #4b5563; border-radius: 4px; padding: 1px 6px; font-size: 11px; }
			.ua-tag-amber { background: #fffbeb; color: #b45309; }
			.ua-tag-blue { background: #eff6ff; color: #1d4ed8; cursor: help; }
			.ua-na { color: #d1d5db; }
			.ua-indent { padding-left: 22px; }
			.ua-second { color: #4b5563; font-size: 12.5px; }
			.ua-chip { display: inline-block; background: #f3f4f6; border-radius: 4px; padding: 1px 6px; font-size: 11.5px; margin: 1px 0; }
			.ua-chip.me { background: var(--er-brand-softest); color: var(--er-brand-dark); font-weight: 700; }
			.ua-tabs { flex-wrap: wrap; }
			.ua-btn-ghost { border: 0; background: none; font-size: 13px; padding: 3px 8px; border-radius: 5px; color: #374151; }
			.ua-btn-ghost:hover { background: #f3f4f6; }
			.ua-muted { color: #6b7280; font-size: 13px; padding: 6px; }
			.ua-empty { color: #6b7280; text-align: center; padding: 40px 10px; font-size: 13px; }
			.ua-add-user { margin-bottom: 14px; }
			.ua-add-label { font-size: 13px; color: #374151; margin-bottom: 4px; }
			.ua-add-row { display: flex; gap: 8px; align-items: center; }
			.ua-user-field .control-label, .ua-user-field .help-box { display: none; }
			.ua-user-field .form-group { margin-bottom: 0; }
			.ua-user-field { width: 340px; }
			.ua-user-field .frappe-control { margin-bottom: 0; }
			.ua .btn-primary { background: var(--er-brand); border-color: var(--er-brand); }
			@media (max-width: 767px) {
				.ua-card { flex-direction: column; height: auto; }
				.ua-side { width: auto; border-right: 0; border-bottom: 1px solid #e5e7eb; max-height: 240px; }
				.ua-table-wrap { max-height: 70vh; }
				.ua-tools .ua-dt-q, .ua-tools .ua-item-q, .ua-user-field { width: 100%; }
			}
		</style>`);
	}
}
