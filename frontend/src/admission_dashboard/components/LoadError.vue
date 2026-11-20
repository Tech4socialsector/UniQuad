<template>
	<!-- A failed dashboard request, in words an admissions user can act on, with a Retry button.
	     The server's own message stays available under "Details" for whoever reports it. -->
	<div
		v-if="error"
		class="mt-6 flex flex-wrap items-start gap-3 rounded-lg border border-outline-red-1 bg-surface-red-2 px-4 py-3"
		role="alert"
	>
		<span class="lucide-circle-alert mt-0.5 size-4 shrink-0 text-ink-red-4" />
		<div class="min-w-0 flex-1">
			<div class="text-p-base font-medium text-ink-gray-9">{{ text.title }}</div>
			<div class="mt-0.5 text-p-sm text-ink-gray-7">{{ text.body }}</div>
			<details v-if="text.detail" class="mt-1 text-p-sm text-ink-gray-5">
				<summary class="cursor-pointer select-none">Details</summary>
				<div class="mt-1 break-words">{{ text.detail }}</div>
			</details>
		</div>
		<Button label="Retry" icon-left="lucide-rotate-cw" :loading="retrying" @click="emit('retry')" />
	</div>
</template>

<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";

const props = defineProps({
	error: { type: [Object, String, Error], default: null },
	retrying: { type: Boolean, default: false },
});
const emit = defineEmits(["retry"]);

const TIMEOUT_STATUSES = [408, 502, 503, 504];

const text = computed(() => {
	const e = props.error;
	if (!e) return {};
	const status = Number(e.status) || 0;
	const raw = typeof e === "string" ? e : (e.messages || []).join(" ") || e.message || "";
	const detail = [status ? `HTTP ${status}` : "", e.exc_type || "", raw].filter(Boolean).join(" · ");

	if (TIMEOUT_STATUSES.includes(status) || /time(d)?\s?out/i.test(raw)) {
		return {
			title: "The server took too long to answer",
			body: "It may be busy. Try again in a moment. Narrowing the date range also makes the dashboard load faster.",
			detail,
		};
	}
	if (!status && /failed to fetch|network/i.test(raw)) {
		return {
			title: "Could not reach the server",
			body: "Check your connection and try again.",
			detail,
		};
	}
	if (status === 403 || e.exc_type === "PermissionError") {
		return { title: "Not permitted", body: raw || "You don't have access to this data.", detail: "" };
	}
	if (status >= 500) {
		return {
			title: "The server hit an error while loading the dashboard",
			body: "Try again. If it keeps happening, send the details below to your system administrator.",
			detail,
		};
	}
	return { title: "Could not load the dashboard", body: raw || "Try again.", detail: "" };
});
</script>
