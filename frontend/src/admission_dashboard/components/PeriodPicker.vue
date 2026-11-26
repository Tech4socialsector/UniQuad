<template>
	<!-- The period box and Refresh, in the same place on the list and the overview. -->
	<div class="flex items-center gap-2">
		<DateRange :model-value="modelValue" :today="today" @update:model-value="emit('update:modelValue', $event)" />
		<Button
			data-print-hide
			icon="lucide-rotate-cw"
			variant="outline"
			title="Refresh: fetch the latest figures (they are otherwise kept for up to 5 minutes)"
			aria-label="Refresh"
			:loading="loading"
			@click="emit('refresh')"
		/>
	</div>
</template>

<script setup>
import { Button } from "frappe-ui";
import DateRange from "./DateRange.vue";

defineProps({
	modelValue: { type: Array, default: () => [] },
	today: { type: String, required: true },
	loading: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue", "refresh"]);
</script>
