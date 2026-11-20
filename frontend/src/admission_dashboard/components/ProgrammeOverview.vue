<template>
	<section class="relative mt-4">
		<div class="flex flex-wrap gap-2">
			<Badge size="lg" theme="gray" :label="applicantType">
				<template #prefix>
					<span :class="applicantType === 'International' ? 'lucide-globe' : 'lucide-users'" class="size-3.5" />
				</template>
			</Badge>
			<Badge size="lg" theme="gray" :label="`Admission Cycle: ${cycleInfo.label || cycle}`" />
			<Badge v-if="cycleInfo.academic_year" size="lg" theme="gray" :label="cycleInfo.academic_year" />
			<Badge v-if="programmes.length === 1" size="lg" theme="gray" :label="programmes[0].level_label" />
		</div>

		<!-- Programmes in view -->
		<div v-if="allProgrammes.length > 1" class="mt-5 flex flex-wrap items-center gap-2">
			<span class="w-20 text-p-sm text-ink-gray-5">Programmes</span>
			<Button
				v-for="p in allProgrammes"
				:key="p.name"
				:label="p.label"
				:icon-left="inView(p) ? 'lucide-check' : undefined"
				:variant="inView(p) ? 'solid' : 'outline'"
				:aria-pressed="inView(p)"
				@click="toggleProgramme(p)"
			/>
		</div>

		<!-- Period (category, gender and fee status each have their own chart below) -->
		<div class="mt-3 flex flex-wrap items-center gap-2">
			<span class="w-20 text-p-sm text-ink-gray-5">Period</span>
			<DateRange v-model="range" :today="today" />
			<Button
				data-print-hide
				icon="lucide-rotate-cw"
				variant="outline"
				title="Refresh: fetch the latest figures (they are otherwise kept for up to 5 minutes)"
				aria-label="Refresh"
				:loading="overview.loading"
				@click="reload(true)"
			/>
		</div>

		<LoadProgress :loading="overview.loading" label="Loading programme data" />
		<LoadError v-if="overview.error" :error="overview.error" :retrying="overview.loading" @retry="reload(false)" />

		<template v-else>
			<!-- Number cards (order and visibility from Dashboard Settings) -->
			<h2 v-if="cards.length" class="mb-3 mt-8 text-lg-semibold text-ink-gray-9">Key numbers</h2>
			<div v-if="cards.length" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
				<StatCard v-for="card in cards" :key="card.key" v-bind="card" :loading="loading" @open="card.open()" />
			</div>

			<!-- Charts (order and visibility from Dashboard Settings) -->
			<h2 v-if="charts.length" class="mb-3 mt-8 text-lg-semibold text-ink-gray-9">Analysis</h2>
			<div class="grid gap-4 lg:grid-cols-2">
				<template v-for="chart in charts" :key="chart.key">
					<ChartCard v-if="chart.key === 'compare'" class="min-w-0" :class="span(chart.key)">
						<div class="text-p-base text-ink-gray-8">Programme comparison</div>
						<div class="text-p-sm text-ink-gray-5">Click a row to open that programme on its own</div>
						<div v-if="loading" class="mt-3 h-40"><Skeleton class="h-full w-full rounded-4" /></div>
						<div v-else class="mt-3 overflow-x-auto">
							<table class="w-full text-base tabular-nums">
								<thead>
									<tr class="border-b border-outline-gray-2 text-p-sm text-ink-gray-5">
										<th class="py-2 pr-3 text-left font-normal">Programme</th>
										<th v-for="col in COMPARE_COLUMNS" :key="col.key" class="whitespace-nowrap px-3 py-2 text-right font-normal">
											{{ col.label }}
										</th>
									</tr>
								</thead>
								<tbody>
									<tr
										v-for="row in data?.compare || []"
										:key="row.name"
										class="cursor-pointer border-b border-outline-gray-1 hover:bg-surface-gray-1"
										@click="openOnly(row.name)"
									>
										<td class="py-2.5 pr-3 font-medium text-ink-gray-9">{{ row.label }}</td>
										<td
											v-for="col in COMPARE_COLUMNS"
											:key="col.key"
											class="px-3 py-2.5 text-right"
											:class="row[col.key] ? 'text-ink-gray-8' : 'text-ink-gray-4'"
										>
											{{ dash(row[col.key]) }}
										</td>
									</tr>
									<tr class="font-semibold text-ink-gray-9">
										<td class="py-2.5 pr-3">All selected</td>
										<td v-for="col in COMPARE_COLUMNS" :key="col.key" class="px-3 py-2.5 text-right">
											{{ dash(data?.cards?.[col.key]) }}
										</td>
									</tr>
								</tbody>
							</table>
						</div>
					</ChartCard>

					<DashChart
						v-else-if="chart.key === 'funnel'"
						:chart="FunnelChart"
						:card-class="span(chart.key)"
						height="300px"
						title="Admission Funnel"
						subtitle="Applications that reached each stage, including those that later exited"
						:data="rows('funnel')"
						category="stage"
						value="count"
						:format="formatNumber"
						:loading="loading"
						@select="(e) => drill(stageFilter(e.name))"
					/>

					<DashChart
						v-else-if="chart.key === 'trend'"
						:chart="trendMode === 'daily' ? BarChart : AreaChart"
						:card-class="span(chart.key)"
						title="Applications over time"
						subtitle="By application created date"
						:data="rows('trend')"
						x="date"
						:y="trendMode === 'daily' ? 'applications' : 'running_total'"
						:x-axis="{ type: 'category', format: formatDate }"
						:y-axis="{ format: formatNumber }"
						:series-config="{ applications: { label: 'Applications' }, running_total: { label: 'Running total' } }"
						:loading="loading"
					>
						<template #actions>
							<TabButtons
								v-model="trendMode"
								:options="[
									{ label: 'Daily', value: 'daily' },
									{ label: 'Running total', value: 'running' },
								]"
							/>
						</template>
					</DashChart>

					<DashChart
						v-else-if="chart.key === 'status'"
						:chart="DonutChart"
						:card-class="span(chart.key)"
						:height="HALF"
						empty-kind="ring"
						title="Status breakdown"
						subtitle="Top statuses, the rest grouped as Others"
						:data="rows('status')"
						category="label"
						value="count"
						center-label="Applications"
						:max-slices="9"
						:format="formatNumber"
						:loading="loading"
						@select="(e) => drill({ status: e.name === OTHERS_KEY ? statusIn(e.rows.map((r) => r.label)) : e.name })"
					/>

					<DashChart
						v-else-if="chart.key === 'fee'"
						:chart="PercentageBarChart"
						:card-class="span(chart.key)"
						:height="HALF"
						empty-kind="strip"
						title="Application fee status"
						:subtitle="data?.fee?.collected ? `${formatINR(data.fee.collected)} collected` : 'Share of applications by fee status'"
						:data="rows('fee.split')"
						category="label"
						value="count"
						order="rows"
						:colors="FEE_COLORS"
						:format="formatNumber"
						:loading="loading"
						@select="(e) => drill(feeFilter(e.name))"
					/>

					<DashChart
						v-else-if="chart.key === 'category'"
						:chart="BarChart"
						:card-class="span(chart.key)"
						:height="HALF"
						title="Category"
						subtitle="Candidate category"
						:data="rows('category')"
						x="label"
						y="count"
						:series-config="{ count: { label: 'Applications' } }"
						show-data-labels
						:loading="loading"
						@select="(e) => drill({ whether_scstobc_ncl: notSetOr(e.row.label) })"
					/>

					<DashChart
						v-else-if="chart.key === 'gender'"
						:chart="DonutChart"
						:card-class="span(chart.key)"
						:height="HALF"
						empty-kind="ring"
						title="Gender"
						subtitle="Gender of applicants"
						:data="rows('gender')"
						category="label"
						value="count"
						order="rows"
						variant="half"
						show-data-labels
						center-label="Applications"
						:format="formatNumber"
						:loading="loading"
						@select="(e) => drill({ gender: notSetOr(e.name) })"
					/>

					<DashChart
						v-else-if="chart.key === 'geo'"
						:chart="BarChart"
						:card-class="span(chart.key)"
						height="400px"
						empty-kind="rows"
						:title="applicantType === 'Domestic' ? 'Top states' : 'Top countries'"
						:subtitle="applicantType === 'Domestic' ? 'State of residence, top 10' : 'Country of residence, top 10'"
						:data="rows('geo')"
						x="label"
						y="count"
						horizontal
						show-data-labels
						:series-config="{ count: { label: 'Applications' } }"
						:loading="loading"
						@select="(e) => drill({ [applicantType === 'Domestic' ? 'state' : 'country']: e.row.label })"
					/>

					<DashChart
						v-else-if="chart.key === 'city'"
						:chart="BarChart"
						:card-class="span(chart.key)"
						height="400px"
						empty-kind="rows"
						title="Entrance test city"
						subtitle="1st preference of submitted applications, top 10"
						:data="rows('city')"
						x="label"
						y="count"
						horizontal
						show-data-labels
						:series-config="{ count: { label: 'Submitted applications' } }"
						:loading="loading"
						@select="(e) => drill({ first_preference: e.row.label, status: statusIn(groups.submitted) })"
					/>

					<DashChart
						v-else-if="chart.key === 'kapwd'"
						:chart="BarChart"
						:card-class="span(chart.key)"
						:height="applicantType === 'Domestic' ? '220px' : '180px'"
						empty-kind="strip"
						:title="applicantType === 'Domestic' ? 'Karnataka Category and PWD' : 'Persons with disability'"
						subtitle="Share of applications"
						:data="rows('kapwd')"
						x="label"
						:y="['yes', 'no']"
						horizontal
						stacked="normalized"
						palette="categorical"
						:series-config="{ yes: { label: 'Yes' }, no: { label: 'No / not set', color: 'var(--surface-gray-4)' } }"
						:loading="loading"
						@select="(e) => drill({ [e.row.field]: e.name === 'yes' ? 'Yes' : ['!=', 'Yes'] })"
					/>

					<SourceChart
						v-else-if="chart.key === 'source'"
						:card-class="span(chart.key)"
						:rows="rows('source').map((r) => ({ label: r.label, applications: r.count }))"
						:series="[{ key: 'applications', label: applicantType, colorIndex: applicantType === 'International' ? 1 : 0 }]"
						:subtitle="`Number of ${applicantType.toLowerCase()} applications by answer`"
						:loading="loading"
					/>
				</template>
			</div>
		</template>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { Badge, Button, Skeleton, TabButtons, createResource } from "frappe-ui";
import { AreaChart, BarChart, ChartCard, DonutChart, FunnelChart, OTHERS_KEY, PercentageBarChart } from "frappe-ui/charts";
import DashChart from "./DashChart.vue";
import DateRange from "./DateRange.vue";
import LoadError from "./LoadError.vue";
import LoadProgress from "./LoadProgress.vue";
import SourceChart from "./SourceChart.vue";
import StatCard from "./StatCard.vue";
import { formatDate, formatINR, formatNumber, percent } from "../format";
import { openApplicants, statusIn } from "../navigate";

const props = defineProps({
	api: { type: String, required: true },
	cycle: { type: String, required: true },
	cycleInfo: { type: Object, default: () => ({}) },
	applicantType: { type: String, required: true },
	programmes: { type: Array, required: true },
	allProgrammes: { type: Array, default: () => [] },
	settings: { type: Object, required: true },
	today: { type: String, required: true },
});
const emit = defineEmits(["update:programmes"]);

const FEE_COLORS = {
	Paid: "var(--chart-categorical-3)",
	Waived: "var(--chart-categorical-1)",
	Requested: "var(--chart-categorical-7)",
	Pending: "var(--surface-gray-4)",
};
const COMPARE_COLUMNS = [
	{ key: "total", label: "Total" },
	{ key: "draft", label: "Draft" },
	{ key: "submitted", label: "Submitted" },
	{ key: "fee_paid", label: "Fee paid" },
	{ key: "selected", label: "Selected" },
	{ key: "offer_accepted", label: "Offer accepted" },
	{ key: "enrolled", label: "Enrolled" },
	{ key: "rejected", label: "Rejected" },
];
// Card colour by status: the number turns warning/danger only when it isn't 0.
const STATUS_TONES = {
	draft: "warning",
	waitlisted: "warning",
	offer_issued: "warning",
	rejected: "danger",
	offer_expired: "danger",
	offer_declined: "danger",
	withdrawn: "danger",
	fee_paid: "success",
	selected: "success",
	offer_accepted: "success",
	confirmation_fee_paid: "success",
	full_fee_paid: "success",
	enrolled: "success",
	submitted: "success",
};
const HALF = "340px"; // every half-width chart, so the two in a row line up
const dash = (n) => (n ? formatNumber(n) : "—");
const STAGES = ["Started", "Submitted", "Fee Paid", "Under Evaluation", "Selected / Offered", "Offer Accepted", "Enrolled"];

// ---- period
const range = ref([]);
const trendMode = ref("daily");

// The server keeps the figures for a few minutes; `fresh` (the Refresh button) asks it to recompute.
let fresh = false;
function reload(refresh) {
	fresh = refresh;
	overview.reload();
	fresh = false;
}
const overview = createResource({
	url: `${props.api}.get_programme_overview`,
	makeParams: () => ({
		refresh: fresh ? 1 : 0,
		admission_cycle: props.cycle,
		programs: JSON.stringify(props.programmes.map((p) => p.name)),
		applicant_type: props.applicantType,
		from_date: range.value[0] || null,
		to_date: range.value[1] || null,
	}),
	auto: true,
});
watch(
	() => [props.cycle, props.applicantType, props.programmes.map((p) => p.name).join(), range.value.join()],
	() => overview.reload()
);

const data = computed(() => overview.data);
const loading = computed(() => overview.loading && !overview.data);
const groups = computed(() => data.value?.status_groups || { stages: [] });

// ---- programmes in view
const inView = (p) => props.programmes.some((x) => x.name === p.name);
function toggleProgramme(p) {
	const next = inView(p) ? props.programmes.filter((x) => x.name !== p.name) : [...props.programmes, p];
	if (!next.length) return; // keep at least one
	emit("update:programmes", props.allProgrammes.filter((x) => next.some((y) => y.name === x.name)));
}
function openOnly(name) {
	const p = props.allProgrammes.find((x) => x.name === name) || props.programmes.find((x) => x.name === name);
	if (p) emit("update:programmes", [p]);
}

// ---- drill-down into the Applicant list, with everything the page is filtered by
const scope = computed(() => ({
	cycle: props.cycle,
	applicantType: props.applicantType,
	programs: props.programmes.map((p) => p.name),
	range: range.value,
}));
const drill = (extra = {}) => openApplicants(scope.value, extra);
const notSetOr = (value) => (value === "Not set" ? ["is", "not set"] : value);
function stageFilter(name) {
	const i = Math.max(0, STAGES.indexOf(name));
	if (i === 0) return {};
	// Fee Paid is read from the fee status too (a "Rejected" applicant may have paid).
	if (name === "Fee Paid") return { application_fee_status: ["in", ["Paid", "Waived"]] };
	return { status: statusIn(groups.value.stages[i]) };
}
function feeFilter(name) {
	if (name === "Pending") return { application_fee_status: ["not in", ["Paid", "Waived", "Requested"]] };
	return { application_fee_status: name };
}

// ---- number cards
// Nothing in view -> every card is empty (null). Otherwise a 0 is a real reading.
const cards = computed(() => {
	const c = data.value?.cards || {};
	const statuses = groups.value.cards || {};
	const v = (n) => (c.total ? n || 0 : null);
	function card(key) {
		if (key === "total") {
			return {
				title: "Total Applications",
				value: v(c.total),
				caption: "Daily, last 30 days",
				sparkline: data.value?.sparkline,
				wide: true,
				open: () => drill(),
			};
		}
		const list = statuses[key];
		if (!list) return null;
		const n = c[key] || 0;
		const tone = STATUS_TONES[key] === "success" || n ? STATUS_TONES[key] || "" : "";
		return {
			value: v(n),
			progress: percent(n, c.total),
			tone,
			caption: `${percent(n, c.total)}% of applications`,
			hint: `Open applications with status: ${list.join(", ")}`,
			open: () => drill({ status: list.length === 1 ? list[0] : statusIn(list) }),
		};
	}
	return props.settings.cards
		.filter((item) => item.enabled)
		.map((item) => ({ item, def: card(item.key) }))
		.filter(({ def }) => def)
		.map(({ item, def }) => ({ key: item.key, title: item.label, hint: "Open these applications", ...def }));
});

// Chart rows; none at all when nothing is in view, so each chart shows its empty state
// rather than axes full of zeros.
function rows(path) {
	if (!data.value?.cards?.total) return [];
	return path.split(".").reduce((o, k) => o?.[k], data.value) || [];
}

// ---- charts: Settings order; the wide ones span both columns, and so does a half-width chart left alone on its row.
const WIDE = new Set(["compare", "funnel", "trend", "kapwd", "source"]);
const charts = computed(() =>
	props.settings.charts.filter((item) => {
		if (!item.enabled) return false;
		if (item.key === "compare") return props.programmes.length > 1;
		if (item.key === "category" || item.key === "city") return props.applicantType === "Domestic";
		return true;
	})
);
const loneHalf = computed(() => {
	let run = [];
	const lone = new Set();
	for (const c of [...charts.value, { key: "compare" }]) {
		if (WIDE.has(c.key)) {
			if (run.length % 2) lone.add(run[run.length - 1]);
			run = [];
		} else run.push(c.key);
	}
	return lone;
});
const span = (key) => (WIDE.has(key) || loneHalf.value.has(key) ? "lg:col-span-2" : "");
</script>
