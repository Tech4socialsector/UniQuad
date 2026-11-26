<template>
	<div class="mb-3 mt-8 flex min-h-8 flex-wrap items-center gap-x-3 gap-y-1">
		<h2 class="text-lg-semibold text-ink-gray-9">{{ title }}</h2>
		<span v-if="hint" class="text-p-sm text-ink-gray-5">{{ hint }}</span>
		<slot />
	</div>
</template>

<script setup>
defineProps({
	title: { type: String, required: true },
	hint: { type: String, default: "" },
});
</script>
