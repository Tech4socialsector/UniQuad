<template>
	<!-- Shown while the dashboard is fetching. With `steps`, the percentage is real: the share of
	     the page's requests that have come back. Without, it is a plain spinner. -->
	<Transition
		enter-from-class="opacity-0 -translate-y-1"
		leave-to-class="opacity-0 -translate-y-1"
		enter-active-class="transition duration-150"
		leave-active-class="transition duration-300"
	>
		<div
			v-if="active"
			class="sticky top-2 z-10 mx-auto mt-4 flex w-full max-w-md items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-elevation-2 px-3 py-2 shadow-sm"
			role="status"
			aria-live="polite"
		>
			<LoadingIndicator class="size-4 shrink-0 text-ink-gray-6" />
			<div class="min-w-0 flex-1">
				<div class="flex items-baseline justify-between gap-2 text-p-sm">
					<span class="truncate text-ink-gray-8">{{ message }}</span>
					<span v-if="steps" class="shrink-0 tabular-nums text-ink-gray-6">{{ pct }}%</span>
				</div>
				<div v-if="steps" class="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-gray-3">
					<div class="h-full rounded-full bg-surface-gray-7 transition-[width] duration-300" :style="{ width: `${pct}%` }" />
				</div>
			</div>
		</div>
	</Transition>
</template>

<script setup>
import { computed } from "vue";
import { LoadingIndicator } from "frappe-ui";

const props = defineProps({
	// [{ label, done }] — one per request; omit for a single request (spinner only).
	steps: { type: Array, default: null },
	loading: { type: Boolean, default: false },
	label: { type: String, default: "Loading data" },
});

const done = computed(() => (props.steps || []).filter((s) => s.done).length);
const active = computed(() => (props.steps ? done.value < props.steps.length : props.loading));
const pct = computed(() => (props.steps?.length ? Math.round((done.value / props.steps.length) * 100) : 0));
const message = computed(() => {
	if (!props.steps) return `${props.label}…`;
	const next = props.steps.find((s) => !s.done);
	return next ? `Loading ${next.label.toLowerCase()}…` : props.label;
});
</script>
