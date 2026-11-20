<template>
	<div ref="root" class="relative mx-auto max-w-[1400px] px-5 pb-10 pt-5 sm:px-8">
		<BuildingArt v-if="!programmes" class="pointer-events-none absolute right-8 top-16 h-28 w-60 max-lg:!hidden" />

		<!-- Sidebar toggle and breadcrumbs -->
		<nav class="relative flex h-8 items-center gap-1.5" data-print-hide>
			<Button
				v-if="hasDeskSidebar"
				variant="ghost"
				:icon="sidebarOpen ? 'lucide-panel-left-close' : 'lucide-panel-left-open'"
				:aria-label="sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'"
				:title="sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'"
				@click="toggleSidebar"
			/>
			<span v-if="hasDeskSidebar" class="mx-1 h-4 w-px bg-outline-gray-2" />
			<a
				href="/desk"
				class="flex size-7 items-center justify-center rounded-md text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
				aria-label="Home"
				title="Home"
				@click="goHome"
			>
				<span class="lucide-house size-4" />
			</a>
			<span class="text-ink-gray-4" aria-hidden="true">/</span>
			<Breadcrumbs :items="breadcrumbs" />
		</nav>

		<!-- Header: title, Admission Cycle, Settings -->
		<header class="relative mt-3 flex flex-wrap items-center justify-between gap-4">
			<h1 class="min-w-0 truncate text-2xl-semibold text-ink-gray-9">
				{{ programmes ? `${overviewTitle} · Admission Overview` : "Admission Dashboard" }}
			</h1>

			<div class="flex flex-wrap items-center gap-3">
				<span class="text-base-medium text-ink-gray-7">Admission Cycle</span>
				<Select v-model="cycle" class="w-72" :options="cycleOptions" placeholder="Select cycle" />
				<Button
					v-if="cycle"
					data-print-hide
					label="Export"
					icon-left="lucide-printer"
					variant="outline"
					title="Print this page, or save it as a PDF from the print dialog"
					:loading="exporting"
					@click="exportPage"
				/>
				<Button
					v-if="programmes && boot.can_edit_settings"
					data-print-hide
					label="Settings"
					icon-left="lucide-settings"
					variant="outline"
					@click="settingsOpen = true"
				/>
			</div>
		</header>

		<!-- Printed only: what the export shows and when it was taken -->
		<div data-print-only class="mt-2 text-p-sm text-ink-gray-6">
			{{ printCaption }}
		</div>

		<div
			v-if="!cycle"
			class="mt-8 rounded-xl border border-dashed border-outline-gray-2 p-10 text-center text-base text-ink-gray-5"
		>
			No Admission Cycle has been created yet.
		</div>

		<ProgrammeList
			v-else-if="!programmes"
			v-model:applicant-type="applicantType"
			v-model:range="range"
			v-model:selected="selected"
			:api="api"
			:cycle="cycle"
			:cycle-label="cycleLabel"
			:today="boot.today"
			@open="openProgrammes"
		/>
		<ProgrammeOverview
			v-else
			v-model:programmes="programmes"
			:api="api"
			:cycle="cycle"
			:cycle-info="cycleInfo"
			:applicant-type="applicantType"
			:all-programmes="openProgrammeList"
			:settings="settings"
			:today="boot.today"
		/>

		<SettingsDialog
			v-if="boot.can_edit_settings"
			v-model:open="settingsOpen"
			:api="api"
			:settings="settings"
			@saved="settings = $event"
		/>
	</div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { Breadcrumbs, Button, Select } from "frappe-ui";
import BuildingArt from "./components/BuildingArt.vue";
import ProgrammeList from "./components/ProgrammeList.vue";
import ProgrammeOverview from "./components/ProgrammeOverview.vue";
import SettingsDialog from "./components/SettingsDialog.vue";

const props = defineProps({
	api: { type: String, required: true },
	boot: { type: Object, required: true },
});

const cycle = ref(props.boot.cycles.default);
const applicantType = ref("Domestic");
const range = ref([]); // [] = entire cycle
const selected = ref([]); // programme names ticked on the list
const programmes = ref(null); // programmes open in the overview (null = list view)
const openProgrammeList = ref([]); // every programme of the current tab, for the overview chips
const settings = ref(props.boot.settings);
const settingsOpen = ref(false);

const cycleInfo = computed(() => props.boot.cycles.options.find((c) => c.value === cycle.value) || {});
const cycleLabel = computed(() => cycleInfo.value.label || cycle.value);
const cycleOptions = computed(() =>
	props.boot.cycles.options.map((c) => ({
		value: c.value,
		label: [c.label, c.academic_year, c.status === "Active" ? "Active" : null].filter(Boolean).join(" · "),
	}))
);

const overviewTitle = computed(() => {
	const list = programmes.value || [];
	if (list.length === 1) return list[0].label;
	if (list.length === 2) return `${list[0].label} + ${list[1].label}`;
	return `${list.length} programmes`;
});

// ---- breadcrumbs: (home icon) / Admission Dashboard / <programme(s)>
// A plain click routes inside desk; a ctrl/cmd/middle click opens /desk the usual way.
function goHome(e) {
	if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0 || !window.frappe?.router) return;
	e.preventDefault();
	window.frappe.router.push_state("/desk");
}
const breadcrumbs = computed(() => {
	const items = [{ label: "Admission Dashboard", onClick: programmes.value ? backToList : undefined }];
	if (programmes.value) items.push({ label: overviewTitle.value });
	return items;
});

// ---- desk sidebar. On every "*-dashboard" page slcm's sidebar_toggle.js hides the sidebar
// (body.slcm-sidebar-hidden) and puts a show/hide button in desk's page header. This page draws
// its own header, so its button drives that same toggle through `window.slcm_sidebar`.
const sidebarApi = () => window.slcm_sidebar;
const deskSidebar = () => window.frappe?.app?.sidebar;
const hasDeskSidebar = Boolean(sidebarApi() || deskSidebar());
const sidebarOpen = ref(readSidebar());
function readSidebar() {
	const api = sidebarApi();
	return api ? api.is_shown() : Boolean(deskSidebar()?.sidebar_expanded);
}
function toggleSidebar() {
	const api = sidebarApi();
	if (api) {
		api.toggle();
	} else {
		// Without slcm's toggle (shouldn't happen): fold / unfold desk's own sidebar, on screen only.
		const sidebar = deskSidebar();
		if (!sidebar?.apply_expanded_state) return;
		sidebar.sidebar_expanded = !sidebar.sidebar_expanded;
		sidebar.apply_expanded_state();
	}
	sidebarOpen.value = readSidebar();
}
// The toggle can also change elsewhere (opening this page hides it again): keep the icon honest.
document.addEventListener("slcm-sidebar-change", (e) => (sidebarOpen.value = Boolean(e.detail?.shown)));

// ---- scroll: the overview opens at the top; going back returns to where the list was.
const root = ref(null);
let listScroll = 0;
// Whatever scrolls the page: desk's own container if it has one, else the document.
function scroller() {
	for (let el = root.value?.parentElement; el; el = el.parentElement) {
		const { overflowY } = getComputedStyle(el);
		if (/(auto|scroll)/.test(overflowY) && el.scrollHeight > el.clientHeight) return el;
	}
	return document.scrollingElement || document.documentElement;
}
function scrollToY(top) {
	nextTick(() => scroller().scrollTo({ top, behavior: "instant" }));
}

function openProgrammes({ open, all }) {
	listScroll = scroller().scrollTop;
	openProgrammeList.value = all;
	programmes.value = open;
	scrollToY(0);
}

function backToList() {
	// Coming back from a combined view keeps those programmes ticked.
	if (programmes.value?.length > 1) selected.value = programmes.value.map((p) => p.name);
	programmes.value = null;
	scrollToY(listScroll);
}

// ---- export: the browser's print dialog ("Save as PDF" is one of its printers).
// The page is first laid out at the printed width (A4 landscape) so the charts, which size
// themselves to their box, redraw for paper before the dialog takes its snapshot.
const exporting = ref(false);
const printCaption = computed(() => {
	// The period is printed by the page's own date-range box, so it isn't repeated here.
	const scope = programmes.value ? overviewTitle.value : `${applicantType.value} programmes`;
	const when = new Date().toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
	return `Admission Cycle ${cycleLabel.value} · ${scope} · exported ${when}`;
});
const frame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
async function exportPage() {
	if (exporting.value) return;
	exporting.value = true;
	const html = document.documentElement;
	html.classList.add("slcm-printing");
	try {
		await nextTick();
		await frame();
		await frame();
		await new Promise((resolve) => setTimeout(resolve, 400)); // charts redraw on resize
		window.print(); // blocks until the dialog closes
	} finally {
		html.classList.remove("slcm-printing");
		exporting.value = false;
	}
}

// Ctrl+P on the page gets the same clean layout (the charts just don't get the redraw first).
// Only while this page is on screen: desk keeps it alive in the background on other pages.
const onScreen = () => root.value?.offsetParent !== null;
window.addEventListener("beforeprint", () => {
	if (onScreen()) document.documentElement.classList.add("slcm-printing");
});
window.addEventListener("afterprint", () => {
	if (!exporting.value) document.documentElement.classList.remove("slcm-printing");
});

// Another cycle has its own programmes and dates: start over on the list.
watch(cycle, () => {
	programmes.value = null;
	selected.value = [];
	range.value = [];
});
</script>
