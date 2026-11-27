<template>
	<!-- Candidate accounts of this tab's NLSAT portal and whether they applied in the cycle.
	     Same four-column grid as the fee cards below, with the total twice as wide. -->
	<SectionTitle :title="`${applicantType} registrations`" :hint="hint" />
	<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
		<StatCard
			v-for="card in cards"
			:key="card.key"
			v-bind="card"
			:loading="loading"
			:clickable="clickable"
			@open="openRegistrations(card.reportCase)"
		/>
	</div>
</template>

<script setup>
import { computed } from "vue";
import SectionTitle from "./SectionTitle.vue";
import StatCard from "./StatCard.vue";
import { formatDate, formatNumber, percent } from "../format";
import { openReport } from "../navigate";

const props = defineProps({
	// get_cycle_overview's `registrations`: { filters, total, applied, not_applied, daily }
	data: { type: Object, default: null },
	applicantType: { type: String, required: true },
	// A date range is picked: the trend caption can't say "last 7 days".
	customRange: { type: Boolean, default: false },
	loading: { type: Boolean, default: false },
	clickable: { type: Boolean, default: false },
});

const REPORT = "Applicant Registration Status";
const TREND_DAYS = 7;

const filters = computed(() => props.data?.filters || {});
const daily = computed(() => props.data?.daily || []);
// Running totals: a few sign-ups a day draw isolated spikes, a running total draws the growth.
function runningTotal(key) {
	let sum = 0;
	return daily.value.map((d) => (sum += d[key]));
}

const hint = computed(() => {
	const { from_date: from, to_date: to } = filters.value;
	const parts = ["Candidate accounts by sign-up date"];
	if (from && to) parts.push(`${formatDate(from)} – ${formatDate(to)}`);
	if (props.applicantType === "Domestic") parts.push("includes accounts with no portal set");
	return parts.join(" · ");
});

const cards = computed(() => {
	const d = props.data || {};
	const total = d.total || 0;
	// Nobody registered: every card shows the empty state rather than three zeros.
	const v = (n) => (total ? n || 0 : null);
	const recent = daily.value.slice(-TREND_DAYS).reduce((sum, day) => sum + day.total, 0);
	const share = (n) => `${percent(n, total)}% of registrations`;
	return [
		{
			key: "total",
			title: "Total Registered",
			value: v(total),
			caption: props.customRange ? "Sign-ups over this period" : `${formatNumber(recent)} in the last ${TREND_DAYS} days`,
			sparkline: runningTotal("total"),
			wide: true,
			hint: "Open these accounts in the Applicant Registration Status report",
			reportCase: "All",
		},
		{
			key: "applied",
			title: "Registered and Applied",
			value: v(d.applied),
			caption: share(d.applied),
			progress: percent(d.applied, total),
			tone: "success",
			sparkline: runningTotal("applied"),
			hint: "Accounts with an application in this cycle, Draft included",
			reportCase: "Any Application",
		},
		{
			key: "not_applied",
			title: "Registered, Not Applied",
			value: v(d.not_applied),
			caption: share(d.not_applied),
			progress: percent(d.not_applied, total),
			tone: d.not_applied ? "warning" : "",
			sparkline: runningTotal("not_applied"),
			hint: "Accounts with no application in this cycle",
			reportCase: "Without Application",
		},
	];
});

function openRegistrations(reportCase) {
	// "" clears a filter the report may still hold from an earlier visit.
	openReport(REPORT, { user: "", ...filters.value, case: reportCase });
}
</script>
