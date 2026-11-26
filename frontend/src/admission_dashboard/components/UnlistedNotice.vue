<template>
	<!-- Applicants no programme card counts: their programme isn't one of the cycle's, or is blank -->
	<div
		class="mb-4 flex flex-col items-start gap-2 rounded-lg bg-surface-amber-2 px-4 py-3 text-p-sm text-ink-gray-8 sm:flex-row sm:items-center sm:gap-3"
		role="status"
	>
		<span class="flex min-w-0 flex-1 gap-2.5">
			<span class="lucide-triangle-alert mt-0.5 size-4 shrink-0 text-ink-amber-5" />
			<span>
				<b>{{ formatNumber(count) }}</b>
				{{ applicantType.toLowerCase() }} {{ count === 1 ? "applicant is" : "applicants are" }} in this cycle
				under a programme that isn't on its programme list, so the cards and charts don't count
				{{ count === 1 ? "it" : "them" }}:
				{{ programmes.map((p) => `${p.label} (${p.count})`).join(", ") }}.
			</span>
		</span>
		<Button label="View applicants" variant="ghost" icon-right="lucide-arrow-right" @click="emit('open')" />
	</div>
</template>

<script setup>
import { Button } from "frappe-ui";
import { formatNumber } from "../format";

defineProps({
	count: { type: Number, required: true },
	programmes: { type: Array, default: () => [] },
	applicantType: { type: String, required: true },
});
const emit = defineEmits(["open"]);
</script>
