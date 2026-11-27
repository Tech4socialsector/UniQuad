<template>
	<section class="relative mt-5">
		<!-- Domestic / International, period -->
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div class="inline-flex gap-1 rounded-lg bg-surface-gray-2 p-1">
				<Button
					v-for="t in TYPES"
					:key="t.value"
					size="lg"
					:icon-left="t.icon"
					:label="t.label"
					:variant="applicantType === t.value ? 'solid' : 'ghost'"
					class="min-w-[150px] !text-base"
					:class="applicantType === t.value ? BRAND_BUTTON : '!text-ink-gray-8'"
					@click="setType(t.value)"
				/>
			</div>
			<PeriodPicker
				:model-value="range"
				:today="today"
				:loading="anyLoading"
				@update:model-value="emit('update:range', $event)"
				@refresh="reloadAll(true)"
			/>
		</div>

		<LoadProgress :steps="steps" label="Dashboard loaded" />
		<LoadError :error="error" :retrying="anyLoading" @retry="reloadAll(false)" />

		<RegistrationCards
			:data="regs.data?.registrations"
			:applicant-type="applicantType"
			:custom-range="range.length === 2"
			:loading="regsLoading"
			:clickable="canOpenRegistrations"
		/>

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
						:class="BRAND_BUTTON"
						@click="openSelected"
					/>
				</template>
				<template v-else-if="programmes.length > 1">
					<span class="max-sm:hidden">Tick programmes to view them together</span>
					<Button label="Select all" variant="ghost" @click="emit('update:selected', programmes.map((p) => p.name))" />
				</template>
			</div>
		</SectionTitle>

		<UnlistedNotice
			v-if="unlisted.count"
			:count="unlisted.count"
			:programmes="unlisted.programmes"
			:applicant-type="applicantType"
			@open="openUnlisted"
		/>

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
			<ProgrammeCard
				v-for="p in programmes"
				:key="p.name"
				:programme="p"
				:selected="isSelected(p)"
				:fees-loading="feesLoading"
				@open="openOne(p)"
				@toggle="toggle(p, $event)"
			/>
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
				:subtitle="`Domestic and International · ${rangeLabel}`"
				:loading="loading"
			/>
		</div>
	</section>
</template>

<script setup>
import { computed, watch } from "vue";
import { Button, createResource } from "frappe-ui";
import { BarChart } from "frappe-ui/charts";
import DashChart from "./DashChart.vue";
import LoadError from "./LoadError.vue";
import LoadProgress from "./LoadProgress.vue";
import PeriodPicker from "./PeriodPicker.vue";
import ProgrammeCard from "./ProgrammeCard.vue";
import RegistrationCards from "./RegistrationCards.vue";
import SectionTitle from "./SectionTitle.vue";
import SourceChart from "./SourceChart.vue";
import StatCard from "./StatCard.vue";
import UnlistedNotice from "./UnlistedNotice.vue";
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
	canOpenRegistrations: { type: Boolean, default: false },
});
const emit = defineEmits(["open", "update:applicantType", "update:range", "update:selected"]);

const BRAND_BUTTON = "!bg-[var(--adm-brand)] !text-white hover:!bg-[var(--adm-brand-hover)]";
const TYPES = [
	{ value: "Domestic", label: "Domestic", icon: "lucide-users" },
	{ value: "International", label: "International", icon: "lucide-globe" },
];
// Both types on the list page, whichever tab is open (the overview draws only its own type).
const SOURCE_SERIES = [
	{ key: "domestic", label: "Domestic" },
	{ key: "international", label: "International" },
];
const EMPTY_FEES = { paid_count: 0, collected: 0, settled_count: 0, settled_amount: 0, awaiting_count: 0, awaiting_amount: 0 };

// The page loads in parallel requests, so each section fills in as soon as its own data
// arrives and the progress bar shows real steps. The server keeps the figures for a few
// minutes; `fresh` (the Refresh button) asks it to recompute them.
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
const regs = part("registrations");
const parts = [apps, fees, regs];
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
	{ label: "Registrations", done: isDone(regs) },
]);
const error = computed(() => parts.map((r) => r.error).find(Boolean));
const firstLoad = (r) => r.loading && !r.data;
const loading = computed(() => firstLoad(apps));
const feesLoading = computed(() => firstLoad(fees));
const regsLoading = computed(() => firstLoad(regs));

const programmes = computed(() =>
	(apps.data?.programmes || []).map((p) => ({
		...p,
		stats: { ...EMPTY_FEES, ...p.stats, ...(fees.data?.fee_stats?.[p.name] || {}) },
	}))
);
const totals = computed(() => {
	const t = {};
	for (const p of programmes.value) for (const [k, v] of Object.entries(p.stats)) t[k] = (t[k] || 0) + v;
	return t;
});
const hasPayments = computed(() => Boolean(totals.value.paid_count || totals.value.settled_count));
const byProgramme = computed(() => apps.data?.by_programme || []);
const feeDaily = computed(() => fees.data?.fee_daily || []);
const unlisted = computed(() => apps.data?.unlisted || { count: 0, programmes: [], listed: [] });
const rangeLabel = computed(() =>
	props.range.length === 2 ? `${formatDate(props.range[0])} – ${formatDate(props.range[1])}` : "entire cycle"
);

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
const scope = (programs) => ({ cycle: props.cycle, applicantType: props.applicantType, programs, range: props.range });
function openUnlisted() {
	const listed = unlisted.value.listed;
	openApplicants(scope([]), listed.length ? { program: ["not in", listed] } : {});
}
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
