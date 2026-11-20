<template>
	<section class="relative mt-5">
		<!-- Domestic / International, date range -->
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div class="inline-flex gap-1 rounded-lg bg-surface-gray-2 p-1">
				<Button
					v-for="t in types"
					:key="t.value"
					size="lg"
					:icon-left="t.icon"
					:label="t.label"
					:variant="applicantType === t.value ? 'solid' : 'ghost'"
					class="min-w-[150px] !text-base"
					:class="
						applicantType === t.value
							? '!bg-[var(--adm-brand)] !text-white hover:!bg-[var(--adm-brand-hover)]'
							: '!text-ink-gray-8'
					"
					@click="setType(t.value)"
				/>
			</div>
			<div class="flex flex-wrap items-center gap-2">
				<DateRange :model-value="range" :today="today" @update:model-value="emit('update:range', $event)" />
				<Button
					data-print-hide
					icon="lucide-rotate-cw"
					variant="outline"
					title="Refresh: fetch the latest figures (they are otherwise kept for up to 5 minutes)"
					aria-label="Refresh"
					:loading="anyLoading"
					@click="reloadAll(true)"
				/>
			</div>
		</div>

		<LoadProgress :steps="steps" label="Dashboard loaded" />
		<LoadError :error="error" :retrying="anyLoading" @retry="reloadAll(false)" />

		<!-- Applications and NLSAT fee -->
		<SectionTitle
			:title="`${applicantType} applications and NLSAT fee`"
			hint="Payments by payment date · settlements by settlement date"
		/>
		<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
			<StatCard
				title="Total Applications"
				:value="totals.total ? totals.total : null"
				:caption="`${formatNumber(totals.submitted)} submitted · ${formatNumber(totals.draft)} in draft`"
				:progress="percent(totals.submitted, totals.total)"
				tone="success"
				:loading="loading"
				hint="Open these applications"
				@open="openApplicants(scope(programmes.map((p) => p.name)))"
			/>
			<StatCard
				title="Application Fee Paid"
				:value="hasPayments ? totals.paid_count : null"
				:caption="`${formatINR(totals.collected)} collected`"
				:loading="feesLoading"
				hint="Open the NLSAT Fee Collection Report"
				@open="openFeeReport({ status: 'Paid' })"
			/>
			<StatCard
				title="Settled"
				:value="hasPayments ? formatINR(totals.settled_amount) : null"
				:caption="`${formatNumber(totals.settled_count)} payments settled`"
				:progress="percent(totals.settled_amount, totals.collected)"
				tone="success"
				:loading="feesLoading"
				hint="Open the NLSAT Fee Collection Report"
				@open="openFeeReport({ status: 'Paid', settlement_status: 'Settled', date_based_on: 'Settlement Date' })"
			/>
			<StatCard
				title="Awaiting Settlement"
				:value="hasPayments ? formatINR(totals.awaiting_amount) : null"
				:caption="totals.awaiting_count ? `${formatNumber(totals.awaiting_count)} paid, not settled yet` : 'Everything paid is settled'"
				:tone="totals.awaiting_count ? 'warning' : ''"
				:loading="feesLoading"
				hint="Open the NLSAT Fee Collection Report"
				@open="openFeeReport({ status: 'Paid', settlement_status: 'Not settled yet' })"
			/>
		</div>

		<!-- Programme cards -->
		<SectionTitle
			title="Programmes"
			:hint="`${programmes.length} open for ${applicantType.toLowerCase()} applicants in the ${cycleLabel} cycle`"
		>
			<div class="ml-auto flex items-center gap-2 text-p-sm text-ink-gray-6">
				<template v-if="selected.length">
					<span><b class="text-ink-gray-9">{{ selected.length }}</b> of {{ programmes.length }} selected</span>
					<Button label="Clear" variant="ghost" @click="emit('update:selected', [])" />
					<Button
						label="View selected"
						icon-right="lucide-arrow-right"
						variant="solid"
						class="!bg-[var(--adm-brand)] !text-white hover:!bg-[var(--adm-brand-hover)]"
						@click="openSelected"
					/>
				</template>
				<template v-else-if="programmes.length > 1">
					<span class="max-sm:hidden">Tick programmes to view them together</span>
					<Button label="Select all" variant="ghost" @click="emit('update:selected', programmes.map((p) => p.name))" />
				</template>
			</div>
		</SectionTitle>

		<!-- Applicants no programme card counts: their programme isn't one of the cycle's, or is blank -->
		<div
			v-if="unlisted.count"
			class="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-outline-amber-3 bg-surface-amber-2 px-4 py-2.5 text-p-sm text-ink-gray-8"
			role="status"
		>
			<span class="lucide-triangle-alert size-4 shrink-0 text-ink-amber-5" />
			<span class="min-w-0 flex-1">
				<b>{{ formatNumber(unlisted.count) }}</b>
				{{ applicantType.toLowerCase() }} {{ unlisted.count === 1 ? "applicant is" : "applicants are" }} in this cycle
				under a programme that isn't on its programme list, so the cards and charts don't count
				{{ unlisted.count === 1 ? "it" : "them" }}:
				{{ unlisted.programmes.map((p) => `${p.label} (${p.count})`).join(", ") }}.
			</span>
			<Button label="View applicants" variant="ghost" icon-right="lucide-arrow-right" @click="openUnlisted" />
		</div>

		<div v-if="loading" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
			<div v-for="i in 3" :key="i" class="h-[300px] animate-pulse rounded-[10px] bg-surface-gray-2" />
		</div>
		<div
			v-else-if="!programmes.length"
			class="flex h-[300px] flex-col items-center justify-center gap-1 rounded-[10px] border border-outline-gray-1 bg-surface-elevation-2 text-center"
		>
			<span class="text-3xl-semibold text-ink-gray-4">—</span>
			<span class="text-p-sm text-ink-gray-5">
				No {{ applicantType.toLowerCase() }} programmes are open in the {{ cycleLabel }} cycle.
			</span>
		</div>
		<!-- auto-rows-fr: every card takes the tallest card's height, in every row -->
		<div v-else class="grid auto-rows-fr gap-4 md:grid-cols-2 xl:grid-cols-3">
			<div
				v-for="p in programmes"
				:key="p.name"
				role="button"
				tabindex="0"
				class="group flex h-full min-w-0 cursor-pointer flex-col rounded-[10px] border bg-surface-elevation-2 px-4 py-3.5 text-left transition hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-outline-gray-4"
				:class="
					isSelected(p)
						? 'border-[var(--adm-brand)] ring-1 ring-[var(--adm-brand)]'
						: 'border-outline-gray-1 hover:border-outline-gray-3'
				"
				:aria-label="`Open ${p.label} overview`"
				@click="openOne(p)"
				@keydown.enter.self.prevent="openOne(p)"
				@keydown.space.self.prevent="openOne(p)"
			>
				<!-- Header: one line each for name and level, controls centred on the block -->
				<div class="flex items-center gap-3">
					<span class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-gray-2 text-ink-gray-7">
						<span :class="programmeIcon(p)" class="size-5" />
					</span>
					<span class="min-w-0 flex-1">
						<span class="block truncate text-lg-semibold text-ink-gray-9" :title="p.label">{{ p.label }}</span>
						<span class="block truncate text-p-sm text-ink-gray-5">{{ p.level_label }}</span>
					</span>
					<label
						class="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md hover:bg-surface-gray-2"
						:title="`Select ${p.label} to view with other programmes`"
						@click.stop
					>
						<input
							type="checkbox"
							class="size-4 cursor-pointer accent-[var(--adm-brand)]"
							:checked="isSelected(p)"
							:aria-label="`Select ${p.label}`"
							@change="toggle(p, $event.target.checked)"
						/>
					</label>
					<span class="lucide-chevron-right size-5 shrink-0 text-ink-gray-5 transition group-hover:translate-x-0.5" />
				</div>

				<!-- Applications -->
				<div class="mt-3.5 border-t border-outline-gray-1 pt-3">
					<h4 class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-gray-5">Applications</h4>
					<div class="grid grid-cols-4 gap-3">
						<Stat label="Total" :value="count(p.stats.total)" />
						<Stat label="Draft" :value="count(p.stats.draft)" />
						<Stat
							label="Submitted"
							:value="count(p.stats.submitted)"
							title="Applications that reached Submitted, including ones later rejected, offered or withdrawn"
						/>
						<Stat label="Enrolled" :value="count(p.stats.enrolled)" />
					</div>
				</div>

				<!-- Application fee -->
				<div class="mt-3 border-t border-outline-gray-1 pt-3">
					<h4 class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-gray-5">Application fee</h4>
					<div class="grid grid-cols-4 gap-3">
						<Stat label="Paid" :value="fee(p.stats.paid_count, count)" />
						<Stat label="Collected" :value="fee(p.stats.collected, money)" />
						<Stat label="Settled" :value="fee(p.stats.settled_amount, money)" />
						<Stat
							label="Awaiting"
							:value="fee(p.stats.awaiting_amount, money)"
							:tone="p.stats.awaiting_count ? 'warning' : ''"
							:title="p.stats.awaiting_count ? `${p.stats.awaiting_count} paid, not settled yet` : ''"
						/>
					</div>
				</div>

				<!-- Footer, pinned to the bottom so every card lines up -->
				<div class="mt-auto pt-4">
					<div class="h-1.5 overflow-hidden rounded-full bg-surface-gray-2">
						<div
							class="h-full rounded-full bg-[var(--adm-success)]"
							:style="{ width: `${percent(p.stats.submitted, p.stats.total)}%` }"
						/>
					</div>
					<div class="mt-1.5 flex justify-between text-p-sm text-ink-gray-5">
						<span>{{ p.stats.total ? `${percent(p.stats.submitted, p.stats.total)}% submitted` : "No applications yet" }}</span>
						<span v-if="p.stats.awaiting_count" class="text-[var(--adm-warning)]">
							{{ formatNumber(p.stats.awaiting_count) }} awaiting settlement
						</span>
						<span v-else-if="p.stats.paid_count">All payments settled</span>
					</div>
				</div>
			</div>
		</div>

		<!-- Charts across every programme of the tab -->
		<SectionTitle title="Programme summary" />
		<div class="grid gap-4 lg:grid-cols-2">
			<DashChart
				:chart="BarChart"
				title="Applications by programme"
				:subtitle="`Domestic and International · ${rangeLabel}`"
				empty-kind="rows"
				:data="byProgramme"
				x="programme"
				:y="['domestic', 'international']"
				horizontal
				stacked
				palette="categorical"
				:series-config="{ domestic: { label: 'Domestic' }, international: { label: 'International' } }"
				:loading="loading"
				@select="onProgrammeBar"
			/>
			<DashChart
				:chart="BarChart"
				title="Fee collected and settled"
				:subtitle="`${applicantType} · ${rangeLabel} · by payment and settlement date`"
				:data="hasPayments ? feeDaily : []"
				x="date"
				:y="['collected', 'settled']"
				palette="sequential"
				:x-axis="{ type: 'category', format: formatDate }"
				:y-axis="{ format: formatINR }"
				:series-config="{ collected: { label: 'Collected' }, settled: { label: 'Settled' } }"
				:tooltip-columns="[
					{ name: 'collected_count', label: 'Payments collected' },
					{ name: 'settled_count', label: 'Payments settled' },
				]"
				:loading="feesLoading"
			/>
			<SourceChart
				card-class="lg:col-span-2"
				:rows="apps.data?.source || []"
				:series="SOURCE_SERIES"
				:subtitle="`Number of applications by answer · Domestic and International · ${rangeLabel}`"
				:loading="loading"
			/>
		</div>
	</section>
</template>

<script setup>
import { computed, h, watch } from "vue";
import { Button, createResource } from "frappe-ui";
import { BarChart } from "frappe-ui/charts";
import DashChart from "./DashChart.vue";
import DateRange from "./DateRange.vue";
import LoadError from "./LoadError.vue";
import LoadProgress from "./LoadProgress.vue";
import SourceChart from "./SourceChart.vue";
import StatCard from "./StatCard.vue";
import { programmeIcon } from "../icons";
import { formatDate, formatINR, formatNumber, percent } from "../format";
import { openApplicants, openReport } from "../navigate";

const props = defineProps({
	api: { type: String, required: true },
	cycle: { type: String, required: true },
	cycleLabel: { type: String, default: "" },
	applicantType: { type: String, required: true },
	range: { type: Array, default: () => [] },
	selected: { type: Array, default: () => [] },
	today: { type: String, required: true },
});
const emit = defineEmits(["open", "update:applicantType", "update:range", "update:selected"]);

const SectionTitle = (p, { slots }) =>
	h("div", { class: "mb-3 mt-8 flex min-h-8 flex-wrap items-center gap-x-3 gap-y-1" }, [
		h("h2", { class: "text-lg-semibold text-ink-gray-9" }, p.title),
		p.hint ? h("span", { class: "text-p-sm text-ink-gray-5" }, p.hint) : null,
		slots.default?.(),
	]);
SectionTitle.props = ["title", "hint"];

// One figure in a programme card. Empty figures print "—".
const Stat = (p) =>
	h("div", { class: "min-w-0", title: p.title || undefined }, [
		h("span", { class: "block truncate text-p-sm text-ink-gray-5" }, p.label),
		h(
			"span",
			{
				class: [
					"block truncate text-lg-semibold tabular-nums",
					p.value === "—" ? "text-ink-gray-4" : p.tone === "warning" ? "text-[var(--adm-warning)]" : "text-ink-gray-9",
				],
			},
			p.value
		),
	]);
Stat.props = ["label", "value", "tone", "title"];

const count = (n) => (n ? formatNumber(n) : "—");
const money = (n) => (n ? formatINR(n) : "—");

const types = [
	{ value: "Domestic", label: "Domestic", icon: "lucide-users" },
	{ value: "International", label: "International", icon: "lucide-globe" },
];

// The page loads in three parallel requests, so each section fills in as soon as its own data
// arrives and the progress bar can show a real percentage. The server keeps the figures for a
// few minutes; `fresh` (the Refresh button) asks it to recompute them.
let fresh = false;
const part = (name) =>
	createResource({
		url: `${props.api}.get_cycle_overview`,
		makeParams: () => ({
			admission_cycle: props.cycle,
			applicant_type: props.applicantType,
			from_date: props.range[0] || null,
			to_date: props.range[1] || null,
			part: name,
			refresh: fresh ? 1 : 0,
		}),
		auto: true,
	});
const apps = part("applications");
const fees = part("fees");
const parts = [apps, fees];
// Retry only re-asks for the parts that failed; Refresh reloads everything from the database.
function reloadAll(refresh) {
	fresh = refresh;
	parts.filter((r) => refresh || r.error || !r.data).forEach((r) => r.reload());
	fresh = false;
}
watch(
	() => [props.cycle, props.applicantType, props.range.join()],
	() => parts.forEach((r) => r.reload())
);
const anyLoading = computed(() => parts.some((r) => r.loading));

const isDone = (r) => !r.loading && (r.data != null || r.error != null);
const steps = computed(() => [
	{ label: "Applications", done: isDone(apps) },
	{ label: "Application fees", done: isDone(fees) },
]);
const error = computed(() => parts.map((r) => r.error).find(Boolean));
const firstLoad = (r) => r.loading && !r.data;
const loading = computed(() => firstLoad(apps));
const feesLoading = computed(() => firstLoad(fees));

const EMPTY_FEES = { paid_count: 0, collected: 0, settled_count: 0, settled_amount: 0, awaiting_count: 0, awaiting_amount: 0 };
const programmes = computed(() =>
	(apps.data?.programmes || []).map((p) => ({
		...p,
		stats: { ...EMPTY_FEES, ...p.stats, ...(fees.data?.fee_stats?.[p.name] || {}) },
	}))
);
const rangeLabel = computed(() =>
	props.range.length === 2 ? `${formatDate(props.range[0])} – ${formatDate(props.range[1])}` : "entire cycle"
);

const totals = computed(() => {
	const t = {};
	for (const p of programmes.value) for (const [k, v] of Object.entries(p.stats)) t[k] = (t[k] || 0) + v;
	return t;
});
const hasPayments = computed(() => Boolean(totals.value.paid_count || totals.value.settled_count));

const byProgramme = computed(() => apps.data?.by_programme || []);
const unlisted = computed(() => apps.data?.unlisted || { count: 0, programmes: [], listed: [] });
// Both shapes on the list page, whichever tab is open (the overview draws only its own type).
const SOURCE_SERIES = [
	{ key: "domestic", label: "Domestic" },
	{ key: "international", label: "International" },
];

function openUnlisted() {
	const listed = unlisted.value.listed;
	openApplicants(scope([]), listed.length ? { program: ["not in", listed] } : {});
}
const feeDaily = computed(() => fees.data?.fee_daily || []);
// A fee figure on a programme card while the fees are still on their way.
const fee = (n, fmt) => (feesLoading.value ? "…" : fmt(n));

// ---- selection
const isSelected = (p) => props.selected.includes(p.name);
function toggle(p, on) {
	const next = props.selected.filter((n) => n !== p.name);
	if (on) next.push(p.name);
	emit("update:selected", next);
}
function setType(type) {
	emit("update:applicantType", type);
	emit("update:selected", []);
}
function openOne(p) {
	emit("open", { open: [p], all: programmes.value });
}
function openSelected() {
	emit("open", { open: programmes.value.filter(isSelected), all: programmes.value });
}
function onProgrammeBar(event) {
	const p = programmes.value.find((x) => x.label === event.row?.programme);
	if (p) openOne(p);
}

// ---- drill-downs
const scope = (programs) => ({
	cycle: props.cycle,
	applicantType: props.applicantType,
	programs,
	range: props.range,
});

function openFeeReport(extra) {
	// "" clears the report's month-to-date default when the dashboard shows the entire cycle.
	openReport("NLSAT Fee Collection Report", {
		admission_cycle: props.cycle,
		from_date: props.range[0] || "",
		to_date: props.range[1] || "",
		date_based_on: "Payment Date",
		settlement_status: "",
		...extra,
	});
}
</script>
