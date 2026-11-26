<template>
	<!-- "Where did you hear about the programme?": one bar per answer, most common first, one
	     segment per series (Domestic / International). Bars compare more exactly than a radar,
	     and the answers' long names fit on phones. -->
	<DashChart
		:chart="BarChart"
		:card-class="cardClass"
		:height="height"
		empty-kind="rows"
		title="Where did you hear about the programme?"
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
	subtitle: { type: String, default: "Number of applications by answer" },
	cardClass: { type: [String, Array, Object], default: "" },
});

const total = (r) => props.series.reduce((n, s) => n + (r[s.key] || 0), 0);
// Nothing answered at all -> no rows, so the chart shows its empty state.
const sorted = computed(() =>
	props.rows.some((r) => total(r)) ? [...props.rows].sort((a, b) => total(b) - total(a)) : []
);
const height = computed(() => `${Math.max(260, 120 + 36 * sorted.value.length)}px`);
const seriesConfig = computed(() =>
	Object.fromEntries(
		props.series.map((s, i) => [s.key, { label: s.label, color: `var(--chart-categorical-${(s.colorIndex ?? i) + 1})` }])
	)
);
</script>
