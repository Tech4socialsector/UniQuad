<template>
	<SectionTitle v-if="charts.length" title="Analysis" />
	<div class="grid gap-4 lg:grid-cols-2">
		<template v-for="chart in charts" :key="chart.key">
			<ProgrammeCompare
				v-if="chart.key === 'compare'"
				:card-class="span(chart.key)"
				:rows="data?.compare || []"
				:totals="data?.cards || {}"
				:loading="loading"
				@open="emit('open-only', $event)"
			/>

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
				:chart="BarChart"
				:card-class="span(chart.key)"
				:height="HALF"
				empty-kind="rows"
				title="Application fee status"
				:subtitle="data?.fee?.collected ? `${formatINR(data.fee.collected)} collected` : 'Applications by fee status'"
				:data="feeRows"
				x="label"
				y="count"
				horizontal
				show-data-labels
				:series-config="{ count: { label: 'Applications' } }"
				:loading="loading"
				@select="(e) => drill(feeFilter(e.row.label))"
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
				:title="domestic ? 'Top states' : 'Top countries'"
				:subtitle="domestic ? 'State of residence, top 10' : 'Country of residence, top 10'"
				:data="rows('geo')"
				x="label"
				y="count"
				horizontal
				show-data-labels
				:series-config="{ count: { label: 'Applications' } }"
				:loading="loading"
				@select="(e) => drill({ [domestic ? 'state' : 'country']: e.row.label })"
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
				:height="domestic ? '220px' : '180px'"
				empty-kind="strip"
				:title="domestic ? 'Karnataka Category and PWD' : 'Persons with disability'"
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
				:series="[{ key: 'applications', label: applicantType, colorIndex: domestic ? 0 : 1 }]"
				:subtitle="`Number of ${applicantType.toLowerCase()} applications by answer`"
				:loading="loading"
			/>
		</template>
	</div>
</template>

<script setup>
import { computed, ref } from "vue";
import { TabButtons } from "frappe-ui";
import { AreaChart, BarChart, DonutChart, FunnelChart, OTHERS_KEY } from "frappe-ui/charts";
import DashChart from "./DashChart.vue";
import ProgrammeCompare from "./ProgrammeCompare.vue";
import SectionTitle from "./SectionTitle.vue";
import SourceChart from "./SourceChart.vue";
import { formatDate, formatINR, formatNumber } from "../format";
import { statusIn } from "../navigate";

const props = defineProps({
	data: { type: Object, default: null }, // get_programme_overview's response
	settings: { type: Object, required: true },
	applicantType: { type: String, required: true },
	programmeCount: { type: Number, required: true },
	loading: { type: Boolean, default: false },
});
// drill: open the Applicant list with these extra filters; open-only: show one programme alone.
const emit = defineEmits(["drill", "open-only"]);

const HALF = "340px"; // every half-width chart, so the two in a row line up
const STAGES = ["Started", "Submitted", "Fee Paid", "Under Evaluation", "Selected / Offered", "Offer Accepted", "Enrolled"];
// The wide ones span both columns, and so does a half-width chart left alone on its row.
const WIDE = new Set(["compare", "funnel", "trend", "kapwd", "source"]);

const trendMode = ref("daily");
const domestic = computed(() => props.applicantType === "Domestic");
const groups = computed(() => props.data?.status_groups || { stages: [] });

const charts = computed(() =>
	props.settings.charts.filter((item) => {
		if (!item.enabled) return false;
		if (item.key === "compare") return props.programmeCount > 1;
		if (item.key === "category" || item.key === "city") return domestic.value;
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

// Chart rows; none at all when nothing is in view, so each chart shows its empty state
// rather than axes full of zeros.
function rows(path) {
	if (!props.data?.cards?.total) return [];
	return path.split(".").reduce((o, k) => o?.[k], props.data) || [];
}

// Every standard fee state, 0s included (the server sends only non-zero ones), then any other.
const FEE_ORDER = ["Paid", "Waived", "Requested", "Pending"];
const feeRows = computed(() => {
	const split = rows("fee.split");
	if (!split.length) return [];
	const count = Object.fromEntries(split.map((r) => [r.label, r.count]));
	return [
		...FEE_ORDER.map((label) => ({ label, count: count[label] || 0 })),
		...split.filter((r) => !FEE_ORDER.includes(r.label)),
	];
});

// ---- drill-down filters
const drill = (extra) => emit("drill", extra);
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
</script>
