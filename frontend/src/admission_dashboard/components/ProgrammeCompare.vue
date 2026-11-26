<template>
	<ChartCard class="min-w-0" :class="cardClass">
		<div class="text-p-base text-ink-gray-8">Programme comparison</div>
		<div class="text-p-sm text-ink-gray-5">Click a row to open that programme on its own</div>
		<div v-if="loading" class="mt-3 h-40"><Skeleton class="h-full w-full rounded-4" /></div>
		<div v-else class="mt-3 overflow-x-auto">
			<table class="w-full text-base tabular-nums">
				<thead>
					<tr class="border-b border-outline-gray-2 text-p-sm text-ink-gray-5">
						<th class="py-2 pr-3 text-left font-normal">Programme</th>
						<th v-for="col in COLUMNS" :key="col.key" class="whitespace-nowrap px-3 py-2 text-right font-normal">
							{{ col.label }}
						</th>
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="row in rows"
						:key="row.name"
						class="cursor-pointer border-b border-outline-gray-1 hover:bg-surface-gray-1"
						@click="emit('open', row.name)"
					>
						<td class="py-2.5 pr-3 font-medium text-ink-gray-9">{{ row.label }}</td>
						<td
							v-for="col in COLUMNS"
							:key="col.key"
							class="px-3 py-2.5 text-right"
							:class="row[col.key] ? 'text-ink-gray-8' : 'text-ink-gray-4'"
						>
							{{ dash(row[col.key]) }}
						</td>
					</tr>
					<tr class="font-semibold text-ink-gray-9">
						<td class="py-2.5 pr-3">All selected</td>
						<td v-for="col in COLUMNS" :key="col.key" class="px-3 py-2.5 text-right">{{ dash(totals[col.key]) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</ChartCard>
</template>

<script setup>
import { Skeleton } from "frappe-ui";
import { ChartCard } from "frappe-ui/charts";
import { formatNumber } from "../format";

defineProps({
	rows: { type: Array, default: () => [] }, // one per programme: { name, label, total, draft, ... }
	totals: { type: Object, default: () => ({}) },
	loading: { type: Boolean, default: false },
	cardClass: { type: [String, Array, Object], default: "" },
});
const emit = defineEmits(["open"]);

const COLUMNS = [
	{ key: "total", label: "Total" },
	{ key: "draft", label: "Draft" },
	{ key: "submitted", label: "Submitted" },
	{ key: "fee_paid", label: "Fee paid" },
	{ key: "selected", label: "Selected" },
	{ key: "offer_accepted", label: "Offer accepted" },
	{ key: "enrolled", label: "Enrolled" },
	{ key: "rejected", label: "Rejected" },
];
const dash = (n) => (n ? formatNumber(n) : "—");
</script>
