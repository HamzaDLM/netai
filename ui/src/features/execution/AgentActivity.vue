<script setup lang="ts">
import { computed } from 'vue'
import { Check, CircleX, LoaderCircle, Wrench } from 'lucide-vue-next'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import type { Message } from '@/types/chat.type'
import { getMessageAgentActivity } from './execution.normalize'
import type { ExecutionStatus } from './execution.types'

const props = defineProps<{
	message: Message
	active?: boolean
}>()

const activity = computed(() => getMessageAgentActivity(props.message))

const connectorColors: Record<string, { text: string; border: string; background: string }> = {
	zabbix: { text: 'text-red-400', border: 'border-red-500/35', background: 'bg-red-500/5' },
	suzieq: { text: 'text-purple-400', border: 'border-purple-500/35', background: 'bg-purple-500/5' },
	bitbucket: { text: 'text-sky-400', border: 'border-sky-500/35', background: 'bg-sky-500/5' },
	servicenow: { text: 'text-emerald-400', border: 'border-emerald-500/35', background: 'bg-emerald-500/5' },
	datamodel: { text: 'text-blue-400', border: 'border-blue-500/35', background: 'bg-blue-500/5' },
	topology: { text: 'text-blue-400', border: 'border-blue-500/35', background: 'bg-blue-500/5' },
	syslog: { text: 'text-amber-400', border: 'border-amber-500/35', background: 'bg-amber-500/5' },
	network: { text: 'text-rose-400', border: 'border-rose-500/35', background: 'bg-rose-500/5' },
	infrahub: { text: 'text-cyan-400', border: 'border-cyan-500/35', background: 'bg-cyan-500/5' },
	external: { text: 'text-stone-300', border: 'border-stone-600', background: 'bg-stone-500/5' },
}

function connectorClass(key: string, part: 'text' | 'border' | 'background'): string {
	return (connectorColors[key] ?? connectorColors.external)[part]
}

function formatDuration(durationMs: number | null): string {
	if (durationMs == null) return ''
	if (durationMs < 1000) return `${Math.round(durationMs)} ms`
	const seconds = durationMs / 1000
	return `${seconds >= 10 ? Math.round(seconds) : Math.round(seconds * 10) / 10} s`
}

function statusLabel(status: ExecutionStatus): string {
	if (status === 'running') return 'Running'
	if (status === 'success') return 'Succeeded'
	if (status === 'blocked') return 'Blocked'
	if (status === 'timeout') return 'Timed out'
	return 'Failed'
}

function stringify(value: unknown): string {
	if (value == null) return ''
	if (typeof value === 'string') return value
	try {
		return JSON.stringify(value, null, 2)
	} catch {
		return String(value)
	}
}

function codeBlock(value: unknown): string {
	const content = stringify(value) || '{}'
	const language = typeof value === 'string' ? 'txt' : 'json'
	return `\`\`\`\`${language}\n${content}\n\`\`\`\``
}

const summary = computed(() => {
	const duration = formatDuration(activity.value?.durationMs ?? null)
	return duration ? `Thoughts (${duration})` : 'Thoughts'
})

const activeMessage = computed(() => {
	if (!activity.value?.tools.length) return 'Analyzing the request...'
	if (activity.value.tools.some(call => call.status === 'running')) return 'Waiting for infrastructure data...'
	return 'Synthesizing the response...'
})
</script>

<template>
	<details v-if="activity" :open="active || undefined" class="group leading-6">
		<summary class="inline-flex cursor-pointer select-none items-center gap-2 text-xs text-stone-400">
			<span>{{ summary }}</span>
			<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 transition-transform group-open:rotate-90" viewBox="0 0 24 24">
				<path fill="currentColor" d="M12.6 12L8 7.4L9.4 6l6 6l-6 6L8 16.6z" />
			</svg>
		</summary>

		<div class="relative grid gap-3 pt-3 pl-8 text-xs">
			<div class="absolute bottom-1 left-[10px] top-1 w-px bg-stone-700/70" />

			<section v-for="group in activity.groups" :key="group.connector.key" class="relative grid gap-2">
				<p class="flex items-center gap-2 text-stone-400">
					<Wrench class="h-4 w-4" />
					<span>Queried</span>
					<span
						class="inline-flex items-center rounded border px-1.5 py-0.5"
						:class="[
							connectorClass(group.connector.key, 'text'),
							connectorClass(group.connector.key, 'border'),
							connectorClass(group.connector.key, 'background'),
						]">
						{{ group.connector.label }}
					</span>
				</p>

				<details v-for="call in group.calls" :key="call.id" class="ml-6 border-l border-stone-700/80 pl-3">
					<summary class="flex cursor-pointer select-none flex-wrap items-center gap-2 text-stone-400">
						<LoaderCircle v-if="call.status === 'running'" class="h-3.5 w-3.5 animate-spin" />
						<Check v-else-if="call.status === 'success'" class="h-3.5 w-3.5 text-emerald-400" />
						<CircleX v-else class="h-3.5 w-3.5 text-red-400" />
						<span class="font-medium text-stone-200">{{ call.label }}</span>
						<span class="text-stone-600">{{ statusLabel(call.status) }}</span>
						<span v-if="call.durationMs != null" class="text-stone-600">· {{ formatDuration(call.durationMs) }}</span>
					</summary>

					<div class="grid gap-2 py-2 pl-1">
						<div>
							<p class="pl-3 text-[11px] uppercase tracking-wide text-stone-500">Input</p>
							<MarkdownRenderer class="execution-code" :content="codeBlock(call.input)" />
						</div>
						<div v-if="call.output != null">
							<p class="pl-3 text-[11px] uppercase tracking-wide text-stone-500">Output</p>
							<MarkdownRenderer class="execution-code" :content="codeBlock(call.output)" />
						</div>
						<p v-else-if="call.status === 'running'" class="pl-3 text-stone-500">Waiting for the result...</p>
						<p v-if="call.error" class="pl-3 text-red-300">{{ call.error }}</p>
					</div>
				</details>
			</section>

			<p v-if="active" class="relative flex items-center gap-2 text-stone-400">
				<LoaderCircle class="h-4 w-4 animate-spin" />
				<span>{{ activeMessage }}</span>
			</p>
			<p v-else-if="activity.status === 'failed'" class="relative flex items-center gap-2 text-red-300">
				<CircleX class="h-4 w-4" />
				<span>{{ activity.error || 'The Agent run failed.' }}</span>
			</p>
			<p v-else class="relative flex items-center gap-2 font-medium text-stone-400">
				<Check class="h-4 w-4" />
				<span>Done.</span>
			</p>
		</div>
	</details>
</template>

<style scoped>
:deep(.execution-code.llm-content) {
	@apply text-xs leading-5 text-stone-300;
}

:deep(.execution-code.llm-content p) {
	@apply pb-0;
}

:deep(.execution-code.llm-content pre) {
	@apply my-1 max-h-80 overflow-auto rounded-md border-stone-700/70 bg-stone-950/30 p-2;
}

:deep(.execution-code.llm-content code) {
	@apply text-[11px];
}
</style>
