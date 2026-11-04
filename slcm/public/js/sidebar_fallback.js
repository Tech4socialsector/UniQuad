// Frappe v16 shows an empty sidebar after a refresh when a DocType is linked from
// several sidebars and none of them is its module's main workspace (e.g. Student RFID
// Card is in both "IT Team" and "Attendance"). When Frappe picks nothing, fall back to
// the sidebar last used (if it lists this route), else the first sidebar that does.
(function () {
	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	if (!Sidebar || Sidebar.prototype._slcm_sidebar_fallback) return;
	Sidebar.prototype._slcm_sidebar_fallback = true;

	const KEY = "slcm_last_sidebar";
	const read_last = () => {
		try { return localStorage.getItem(KEY); } catch (e) { return null; }
	};

	const setup = Sidebar.prototype.setup;
	Sidebar.prototype.setup = function () {
		const result = setup.apply(this, arguments);
		if (this.sidebar_title) {
			try { localStorage.setItem(KEY, this.sidebar_title); } catch (e) { /* storage blocked */ }
		}
		return result;
	};

	// sidebars that link the List / Form / Report in the current route, same app first
	function candidates(sidebar, router) {
		const route = frappe.get_route() || [];
		if (route.length < 2 || route[0] === "Workspaces") return [];
		const items = frappe.boot.workspace_sidebar_item || {};
		const all = [...new Set(sidebar.get_workspace_sidebars(route[1]))].filter((s) => items[(s || "").toLowerCase()]);
		const module = router && router.meta && router.meta.module;
		const app = module && (frappe.boot.module_app || {})[module.toLowerCase()];
		const same_app = app ? all.filter((s) => items[s.toLowerCase()].app === app) : [];
		return same_app.length ? same_app : all;
	}

	const set_workspace_sidebar = Sidebar.prototype.set_workspace_sidebar;
	Sidebar.prototype.set_workspace_sidebar = function (router) {
		const before = this.sidebar_title;
		const result = set_workspace_sidebar.apply(this, arguments);
		try {
			if (this.sidebar_title !== before) return result; // Frappe chose a sidebar itself
			const options = candidates(this, router);
			if (!options.length || options.includes(this.sidebar_title)) return result;
			const last = read_last();
			this.setup(options.includes(last) ? last : options[0]);
			this.set_active_workspace_item();
		} catch (e) {
			console.log(e);
		}
		return result;
	};
})();
