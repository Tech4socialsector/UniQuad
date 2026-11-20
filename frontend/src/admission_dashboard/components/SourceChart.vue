<template>
	<!-- "Where did you hear about the programme?" as a radar, the way frappe-ui's Charts docs draw
	     their custom "Plan satisfaction" chart: one spoke per answer, one shape per series
	     (Domestic / International), and a legend that shows or hides each shape. -->
	<ChartCard class="min-w-0" :class="cardClass" :style="{ height }">
		<ChartContainer
			title="Where did you hear about the programme?"
			:subtitle="subtitle"
			:loading="loading"
			:empty="!loading && !hasData"
		>
			<div ref="plotEl" class="h-full w-full" />
			<template #empty>
				<ChartEmpty kind="ring" message="No data for this selection" />
			</template>
			<template v-if="hasData" #legend>
				<ChartLegend :items="legendItems" @change="toggleSeries" />
			</template>
		</ChartContainer>
	</ChartCard>
</template>

<script setup>
import { computed, ref } from "vue";
import { RadarChart } from "echarts/charts";
import { RadarComponent, TooltipComponent } from "echarts/components";
import {
	ChartCard,
	ChartContainer,
	ChartLegend,
	paletteColors,
	registerChartModules,
	useChart,
	useChartTokens,
} from "frappe-ui/charts";
import ChartEmpty from "./ChartEmpty.vue";
import { formatNumber } from "../format";

registerChartModules([RadarChart, RadarComponent, TooltipComponent]);

const props = defineProps({
	// One row per answer: { label, <series key>: count, ... }, in spoke order.
	rows: { type: Array, default: () => [] },
	// The shapes to draw: [{ key, label }], e.g. Domestic and International.
	series: { type: Array, required: true },
	loading: { type: Boolean, default: false },
	subtitle: { type: String, default: "Number of applications by answer" },
	cardClass: { type: [String, Array, Object], default: "" },
	height: { type: String, default: "460px" },
});

const plotEl = ref();
// Resolved against the plot element, so the colours follow the light / dark theme.
const { tokens } = useChartTokens(plotEl);
const hidden = ref([]);

const hasData = computed(() => props.rows.some((r) => props.series.some((s) => r[s.key])));
// A series may pin its palette slot (`colorIndex`), so International keeps its colour when it's
// drawn alone on the overview.
const colors = computed(() => {
	const slots = props.series.map((s, i) => s.colorIndex ?? i);
	const palette = paletteColors("categorical", tokens.value, Math.max(...slots, 0) + 1);
	return slots.map((slot) => palette[slot]);
});

const legendItems = computed(() =>
	props.series.map((s, i) => ({
		name: s.key,
		label: s.label,
		color: colors.value[i],
		hidden: hidden.value.includes(s.key),
	}))
);
function toggleSeries(name) {
	hidden.value = hidden.value.includes(name) ? hidden.value.filter((k) => k !== name) : [...hidden.value, name];
}

// The scale runs to a round number just above the largest count, so the shapes fill the web.
function niceMax(n) {
	if (n <= 4) return 4;
	const step = 10 ** Math.floor(Math.log10(n));
	return Math.ceil((n * 1.1) / step) * step;
}

const option = computed(() => {
	if (!hasData.value) return null;
	const t = tokens.value;
	const visible = props.series.map((s, i) => ({ ...s, color: colors.value[i] })).filter((s) => !hidden.value.includes(s.key));
	const max = niceMax(Math.max(1, ...props.rows.flatMap((r) => visible.map((s) => r[s.key] || 0))));

	return {
		tooltip: {
			trigger: "item",
			confine: true,
			backgroundColor: "var(--surface-modal, #fff)",
			borderColor: "var(--outline-gray-2, #e2e2e2)",
			textStyle: { color: "var(--ink-gray-8, #333)", fontSize: 12 },
			formatter: (p) => {
				const lines = props.rows
					.map((r, i) => [r.label, p.value[i]])
					.filter(([, v]) => v)
					.sort((a, b) => b[1] - a[1])
					.map(([label, v]) => `<div style="display:flex;justify-content:space-between;gap:16px"><span>${label}</span><b>${formatNumber(v)}</b></div>`);
				return `<div style="font-weight:600;margin-bottom:4px">${p.marker}${p.name}</div>${lines.join("") || "No answers"}`;
			},
		},
		radar: {
			indicator: props.rows.map((r) => ({ name: r.label, max })),
			center: ["50%", "50%"],
			radius: "68%",
			splitNumber: 4,
			axisName: { color: t.axisLabel, fontSize: 11 },
			axisLine: { lineStyle: { color: t.gridline } },
			splitLine: { lineStyle: { color: t.gridline, type: "dashed" } },
			splitArea: { show: false },
		},
		series: [
			{
				type: "radar",
				symbol: "circle",
				symbolSize: 5,
				data: visible.map((s) => ({
					name: s.label,
					value: props.rows.map((r) => r[s.key] || 0),
					itemStyle: { color: s.color },
					lineStyle: { color: s.color, width: 2 },
					areaStyle: { color: s.color, opacity: 0.15 },
				})),
			},
		],
	};
});

useChart({ container: plotEl, option: () => option.value });
</script>
