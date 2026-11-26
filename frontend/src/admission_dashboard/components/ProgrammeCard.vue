<template>
	<div
		role="button"
		tabindex="0"
		class="group flex h-full min-w-0 cursor-pointer flex-col gap-5 rounded-[10px] border bg-surface-elevation-2 p-4 text-left transition hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-outline-gray-4"
		:class="selected ? 'border-[var(--adm-brand)] ring-1 ring-[var(--adm-brand)]' : 'border-outline-gray-1 hover:border-outline-gray-3'"
		:aria-label="`Open ${programme.label} overview`"
		@click="emit('open')"
		@keydown.enter.self.prevent="emit('open')"
		@keydown.space.self.prevent="emit('open')"
	>
		<!-- Name and level; select box and arrow centred on the block -->
		<div class="flex items-center gap-3">
			<span class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-gray-2 text-ink-gray-7">
				<span :class="programmeIcon(programme)" class="size-5" />
			</span>
			<span class="min-w-0 flex-1">
				<span class="block truncate text-lg-semibold text-ink-gray-9" :title="programme.label">{{ programme.label }}</span>
				<span class="block truncate text-p-sm text-ink-gray-5">{{ programme.level_label }}</span>
			</span>
			<label
				class="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md hover:bg-surface-gray-2"
				:title="`Select ${programme.label} to view with other programmes`"
				@click.stop
			>
				<input
					type="checkbox"
					class="size-4 cursor-pointer accent-[var(--adm-brand)]"
					:checked="selected"
					:aria-label="`Select ${programme.label}`"
					@change="emit('toggle', $event.target.checked)"
				/>
			</label>
			<span class="lucide-chevron-right size-5 shrink-0 text-ink-gray-5 transition group-hover:translate-x-0.5" />
		</div>

		<!-- Two rows of four figures, on the same column lanes -->
		<div v-for="group in groups" :key="group.title" class="flex flex-col gap-2">
			<h4 class="text-p-sm font-medium text-ink-gray-6">{{ group.title }}</h4>
			<div class="grid grid-cols-4 gap-3">
				<div v-for="f in group.figures" :key="f.label" class="min-w-0" :title="f.title || undefined">
					<span class="block truncate text-p-sm text-ink-gray-5">{{ f.label }}</span>
					<span class="block truncate text-lg-semibold tabular-nums" :class="figureClass(f)">{{ f.value }}</span>
				</div>
			</div>
		</div>

		<!-- Footer, pinned to the bottom so every card lines up -->
		<div class="mt-auto">
			<div class="h-1.5 overflow-hidden rounded-full bg-surface-gray-2">
				<div class="h-full rounded-full bg-[var(--adm-success)]" :style="{ width: `${submittedPct}%` }" />
			</div>
			<div class="mt-1.5 flex justify-between gap-2 text-p-sm text-ink-gray-5">
				<span>{{ s.total ? `${submittedPct}% submitted` : "No applications yet" }}</span>
				<span v-if="s.awaiting_count" class="text-[var(--adm-warning)]">
					{{ formatNumber(s.awaiting_count) }} awaiting settlement
				</span>
				<span v-else-if="s.paid_count">All payments settled</span>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue";
import { programmeIcon } from "../icons";
import { formatINR, formatNumber, percent } from "../format";

const props = defineProps({
	programme: { type: Object, required: true },
	selected: { type: Boolean, default: false },
	feesLoading: { type: Boolean, default: false },
});
const emit = defineEmits(["open", "toggle"]);

const s = computed(() => props.programme.stats);
const submittedPct = computed(() => percent(s.value.submitted, s.value.total));

// Empty figures print "—"; fee figures print "…" while the fees are still on their way.
const count = (n) => (n ? formatNumber(n) : "—");
const money = (n) => (n ? formatINR(n) : "—");
const fee = (n, fmt) => (props.feesLoading ? "…" : fmt(n));

const groups = computed(() => [
	{
		title: "Applications",
		figures: [
			{ label: "Total", value: count(s.value.total) },
			{ label: "Draft", value: count(s.value.draft) },
			{
				label: "Submitted",
				value: count(s.value.submitted),
				title: "Applications that reached Submitted, including ones later rejected, offered or withdrawn",
			},
			{ label: "Enrolled", value: count(s.value.enrolled) },
		],
	},
	{
		title: "Application fee",
		figures: [
			{ label: "Paid", value: fee(s.value.paid_count, count) },
			{ label: "Collected", value: fee(s.value.collected, money) },
			{ label: "Settled", value: fee(s.value.settled_amount, money) },
			{
				label: "Awaiting",
				value: fee(s.value.awaiting_amount, money),
				warning: Boolean(s.value.awaiting_count),
				title: s.value.awaiting_count ? `${s.value.awaiting_count} paid, not settled yet` : "",
			},
		],
	},
]);

function figureClass(f) {
	if (f.value === "—") return "text-ink-gray-4";
	return f.warning ? "text-[var(--adm-warning)]" : "text-ink-gray-9";
}
</script>
