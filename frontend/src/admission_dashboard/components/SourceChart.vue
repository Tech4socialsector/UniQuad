<template>
	<!-- Counts by answer ("Where did you hear about the programme?", "Device used to submit"):
	     one bar per answer, most common first, one segment per series (Domestic / International).
	     Bars compare more exactly than a radar, and long answers fit on phones. -->
	<DashChart
		:chart="BarChart"
		:card-class="cardClass"
		:height="height"
		empty-kind="rows"
		:empty-message="emptyMessage"
		:title="title"
		:subtitle="subtitle"
		:data="sorted"
		x="label"
		:y="series.map((s) => s.key)"
		horizontal
		:stacked="series.length > 1"
		:show-data-labels="series.length === 1"
		:series-config="seriesConfig"
		:loading="loading"
	/>
</template>

<script setup>
import { computed } from "vue";
import { BarChart } from "frappe-ui/charts";
import DashChart from "./DashChart.vue";

const props = defineProps({
	// One row per answer: { label, <series key>: count, ... }.
	rows: { type: Array, default: () => [] },
	// [{ key, label, colorIndex? }]. colorIndex pins the palette slot, so International keeps
	// its colour when it's drawn alone on the overview.
	series: { type: Array, required: true },
	loading: { type: Boolean, default: false },
	title: { type: String, default: "Where did you hear about the programme?" },
	subtitle: { type: String, default: "Number of applications by answer" },
	emptyMessage: { type: String, default: "No data for this selection" },
	keepLast: { type: Array, default: () => [] },
	cardClass: { type: [String, Array, Object], default: "" },
});

const total = (r) => props.series.reduce((n, s) => n + (r[s.key] || 0), 0);
// Most common first; rows named in `keepLast` (e.g. "Not recorded") stay at the bottom.
const rank = (r) => (props.keepLast.includes(r.label) ? -1 : total(r));
// Nothing answered at all -> no rows, so the chart shows its empty state.
const sorted = computed(() =>
	props.rows.some((r) => total(r)) ? [...props.rows].sort((a, b) => rank(b) - rank(a)) : []
);
const height = computed(() => `${Math.max(260, 120 + 36 * sorted.value.length)}px`);
const seriesConfig = computed(() =>
	Object.fromEntries(
		props.series.map((s, i) => [s.key, { label: s.label, color: `var(--chart-categorical-${(s.colorIndex ?? i) + 1})` }])
	)
);
</script>
