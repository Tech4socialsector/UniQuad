<template>
	<!-- Headline cards: the first enabled cards (Settings order) that fill one row of four
	     columns. Every other enabled status is a compact row below, so a dozen zeros don't
	     each get a box. -->
	<template v-if="cards.length">
		<SectionTitle title="Key numbers" />
		<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
			<StatCard v-for="card in headline" :key="card.key" v-bind="card" :loading="loading" @open="card.open()" />
		</div>

		<div v-if="statuses.length" class="mt-6">
			<h3 class="mb-1 text-base-medium text-ink-gray-8">Applications by status</h3>
			<div v-if="loading" class="h-24"><Skeleton class="h-full w-full rounded-4" /></div>
			<ul v-else class="grid gap-x-10 sm:grid-cols-2 xl:grid-cols-3">
				<li v-for="s in statuses" :key="s.key">
					<button
						type="button"
						class="flex h-10 w-full items-center gap-3 border-b border-outline-gray-1 px-1 text-left text-base hover:bg-surface-gray-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-outline-gray-4"
						:title="s.hint"
						@click="s.open()"
					>
						<span class="min-w-0 flex-1 truncate" :class="s.value ? 'text-ink-gray-8' : 'text-ink-gray-5'">{{ s.title }}</span>
						<span class="w-14 shrink-0 text-right font-medium tabular-nums" :class="valueClass(s)">
							{{ s.value == null ? "—" : formatNumber(s.value) }}
						</span>
						<span class="w-12 shrink-0 text-right text-p-sm tabular-nums text-ink-gray-5">
							{{ s.value ? `${s.progress}%` : "" }}
						</span>
					</button>
				</li>
			</ul>
		</div>
	</template>
</template>

<script setup>
import { computed } from "vue";
import { Skeleton } from "frappe-ui";
import SectionTitle from "./SectionTitle.vue";
import StatCard from "./StatCard.vue";
import { formatNumber } from "../format";

const props = defineProps({
	// Every enabled card, Settings order: { key, title, value, progress, tone, wide, hint, open }.
	cards: { type: Array, required: true },
	loading: { type: Boolean, default: false },
});

const COLUMNS = 4;
const split = computed(() => {
	let used = 0;
	const headline = [];
	const rest = [];
	for (const card of props.cards) {
		const width = card.wide ? 2 : 1;
		if (rest.length === 0 && used + width <= COLUMNS) {
			headline.push(card);
			used += width;
		} else rest.push(card);
	}
	return { headline, rest };
});
const headline = computed(() => split.value.headline);
const statuses = computed(() => split.value.rest);

// Written out in full so Tailwind finds the classes.
const TONE_TEXT = { warning: "text-[var(--adm-warning)]", danger: "text-[var(--adm-danger)]" };
function valueClass(s) {
	if (!s.value) return "text-ink-gray-4";
	return TONE_TEXT[s.tone] || "text-ink-gray-9";
}
</script>
