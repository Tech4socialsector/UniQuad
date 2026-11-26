<template>
	<section class="relative mt-5">
		<!-- What is in view (the cycle is in the page header), and the period -->
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div class="flex flex-wrap gap-2">
				<Badge size="lg" theme="gray" :label="applicantType">
					<template #prefix>
						<span :class="applicantType === 'International' ? 'lucide-globe' : 'lucide-users'" class="size-3.5" />
					</template>
				</Badge>
				<Badge v-if="programmes.length === 1" size="lg" theme="gray" :label="programmes[0].level_label" />
			</div>
			<PeriodPicker v-model="range" :today="today" :loading="overview.loading" @refresh="reload(true)" />
		</div>

		<!-- Programmes in view -->
		<div v-if="allProgrammes.length > 1" class="mt-4 flex flex-wrap items-center gap-2" data-print-hide>
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

		<LoadProgress :loading="overview.loading" label="Loading programme data" />
		<LoadError v-if="overview.error" :error="overview.error" :retrying="overview.loading" @retry="reload(false)" />

		<template v-else>
			<OverviewNumbers :cards="cards" :loading="loading" />
			<OverviewCharts
				:data="data"
				:settings="settings"
				:applicant-type="applicantType"
				:programme-count="programmes.length"
				:loading="loading"
				@drill="drill"
				@open-only="openOnly"
			/>
		</template>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { Badge, Button, createResource } from "frappe-ui";
import LoadError from "./LoadError.vue";
import LoadProgress from "./LoadProgress.vue";
import OverviewCharts from "./OverviewCharts.vue";
import OverviewNumbers from "./OverviewNumbers.vue";
import PeriodPicker from "./PeriodPicker.vue";
import { percent } from "../format";
import { openApplicants, statusIn } from "../navigate";

const props = defineProps({
	api: { type: String, required: true },
	cycle: { type: String, required: true },
	applicantType: { type: String, required: true },
	programmes: { type: Array, required: true },
	allProgrammes: { type: Array, default: () => [] },
	settings: { type: Object, required: true },
	today: { type: String, required: true },
});
const emit = defineEmits(["update:programmes"]);

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

const range = ref([]);

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
function drill(extra = {}) {
	const scope = {
		cycle: props.cycle,
		applicantType: props.applicantType,
		programs: props.programmes.map((p) => p.name),
		range: range.value,
	};
	openApplicants(scope, extra);
}

// ---- number cards, Settings order. Nothing in view -> every card is empty (null);
// otherwise a 0 is a real reading.
const cards = computed(() => {
	const c = data.value?.cards || {};
	const statuses = data.value?.status_groups?.cards || {};
	const v = (n) => (c.total ? n || 0 : null);
	function card(key) {
		if (key === "total") {
			return {
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
		return {
			value: v(n),
			progress: percent(n, c.total),
			tone: STATUS_TONES[key] === "success" || n ? STATUS_TONES[key] || "" : "",
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
</script>
