// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.listview_settings["SLCM Batch"] = {
	onload(listview) {
		hide_batch_list_sidebar(listview);
	},
	refresh(listview) {
		hide_batch_list_sidebar(listview);
	},
};

function hide_batch_list_sidebar(listview) {
	// Method 1: Use Frappe's built-in method (most reliable)
	if (listview && listview.page) {
		listview.page.hide_sidebar();
	}

	// Method 2: CSS reinforcement with more specific selectors
	if (!document.getElementById("batch-hide-sidebar-css")) {
		const style = document.createElement("style");
		style.id = "batch-hide-sidebar-css";
		style.innerHTML = `
			/* Target the specific page container for Batch list */
			[data-page-route*="Batch"] .layout-side-section,
			body[data-route*="Batch"] .layout-side-section,
			.page-container .layout-side-section {
				display: none !important;
			}

			[data-page-route*="Batch"] .layout-main-section,
			body[data-route*="Batch"] .layout-main-section,
			.page-container .layout-main-section {
				width: 100% !important;
				margin-left: 0 !important;
				flex: 1 !important;
			}

			/* Handle the container wrapper */
			[data-page-route*="Batch"] .layout-main-section-wrapper,
			body[data-route*="Batch"] .layout-main-section-wrapper {
				width: 100% !important;
			}
		`;
		document.head.appendChild(style);
	}

	// Method 3: Direct DOM manipulation with retry mechanism
	function hideSidebarDOM(attempts = 0) {
		const maxAttempts = 10;
		const sidebar = document.querySelector(".layout-side-section");
		const mainSection = document.querySelector(".layout-main-section");

		if (sidebar && mainSection) {
			sidebar.style.display = "none";
			mainSection.style.width = "100%";
			mainSection.style.marginLeft = "0";
		} else if (attempts < maxAttempts) {
			// Retry if elements not found yet
			setTimeout(() => hideSidebarDOM(attempts + 1), 100);
		}
	}

	// Execute with slight delay to ensure DOM is ready
	setTimeout(hideSidebarDOM, 50);
}
