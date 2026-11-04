// Desk sidebar on dashboard pages (routes like "exam-dashboard"): hidden whenever one
// opens, with a button before the breadcrumbs to show or hide it. Every other page keeps
// the normal sidebar and has no button. Phones keep Frappe's own menu (see sidebar_toggle.css).
(function () {
	const ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
		stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/></svg>`;

	let shown = true;
	let last_route = null;

	const is_dashboard = () => {
		// /desk/<first>/...; read from the URL because frappe.get_route() is null during startup
		const first = (window.location.pathname.split("/")[2] || "").toLowerCase();
		return /(^|-)dashboard$/.test(first);
	};

	function apply(show) {
		shown = show;
		document.body.classList.toggle("slcm-sidebar-hidden", !show);
		document.querySelectorAll(".slcm-sb-toggle").forEach((b) => {
			b.setAttribute("aria-pressed", String(show));
			b.title = show ? __("Hide sidebar") : __("Show sidebar");
			b.setAttribute("aria-label", b.title);
		});
	}

	// one button per page header; pages keep their DOM, so this only adds to new ones
	function add_buttons() {
		document.querySelectorAll(".page-head .title-area").forEach((area) => {
			if (area.querySelector(":scope > .slcm-sb-toggle")) return;
			const b = document.createElement("button");
			b.type = "button";
			b.className = "slcm-sb-toggle";
			b.innerHTML = ICON;
			area.prepend(b);
		});
		apply(shown);
	}

	// opening a dashboard starts with the sidebar hidden; anything else shows it
	function on_route() {
		const route = window.location.pathname + window.location.search;
		if (route !== last_route) {
			last_route = route;
			const dash = is_dashboard();
			document.body.classList.toggle("slcm-sb-dashboard", dash);
			apply(!dash);
		}
		setTimeout(add_buttons, 0);
	}

	$(document).on("click", ".slcm-sb-toggle", (e) => {
		e.preventDefault();
		apply(!shown);
		if (shown && frappe.app && frappe.app.sidebar && !frappe.app.sidebar.sidebar_expanded) {
			frappe.app.sidebar.open();
		}
	});

	$(document).on("page-change", on_route);
	$(() => {
		if (frappe.router && frappe.router.on) frappe.router.on("change", on_route);
		on_route();
	});
	// a page's header can be filled in after page-change (workspaces, reports)
	let queued = false;
	new MutationObserver(() => {
		if (queued) return;
		queued = true;
		requestAnimationFrame(() => {
			queued = false;
			if (document.querySelector(".page-head .title-area:not(:has(> .slcm-sb-toggle))")) add_buttons();
		});
	}).observe(document.body, { childList: true, subtree: true });
})();
