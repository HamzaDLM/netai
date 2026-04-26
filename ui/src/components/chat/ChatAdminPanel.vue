<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { MessageSquareWarning, RefreshCw } from 'lucide-vue-next'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { toast } from '@/components/ui/toast'
import { formatDatetime } from '@/lib/utils'
import chatService from '@/services/chat.service'
import type { AdminFeedbackItem, AgentRun } from '@/types/chat.type'

type AdminSection = 'feedbacks'
type PersistedToolCall = {
	id: number
	tool_name: string
	input_params?: Record<string, unknown>
	output?: Record<string, unknown> | null
	status?: string
	error_type?: string | null
	error_message?: string | null
	created_at?: string
}
type RunWithPersistedTools = AgentRun & {
	agent_name?: string
	tool_calls?: PersistedToolCall[]
	child_runs?: RunWithPersistedTools[]
}
type DisplayToolCall = PersistedToolCall & {
	agentName: string
}

const activeSection = ref<AdminSection>('feedbacks')
const feedbackItems = ref<AdminFeedbackItem[]>([])
const selectedFeedbackId = ref<number | null>(null)
const isLoading = ref(false)

const selectedItem = computed(() => {
	if (!feedbackItems.value.length) return null
	return feedbackItems.value.find(item => item.feedback.id === selectedFeedbackId.value) ?? feedbackItems.value[0]
})

const toolCalls = computed<DisplayToolCall[]>(() => {
	const runs = (selectedItem.value?.assistant_message.agent_runs ?? []) as RunWithPersistedTools[]
	const calls: DisplayToolCall[] = []

	const collectRun = (run: RunWithPersistedTools) => {
		const agentName = run.agent_name || 'orchestrator'
		for (const call of run.tool_calls ?? []) {
			calls.push({ ...call, agentName })
		}
		for (const childRun of run.child_runs ?? []) {
			collectRun(childRun)
		}
	}

	for (const run of runs) collectRun(run)
	return calls
})

function formatFeedbackType(value?: string | null): string {
	if (!value) return 'No type'
	return value
		.replace(/[_-]+/g, ' ')
		.replace(/\b\w/g, char => char.toUpperCase())
}

function truncate(value: string | undefined | null, maxLength = 110): string {
	const normalized = (value ?? '').replace(/\s+/g, ' ').trim()
	if (!normalized) return 'No content'
	return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized
}

function formatJson(value: unknown): string {
	if (value == null) return 'null'
	try {
		return JSON.stringify(value, null, 2)
	} catch {
		return String(value)
	}
}

async function loadFeedbacks() {
	isLoading.value = true
	try {
		const response = await chatService.getAdminFeedbacks()
		feedbackItems.value = response.data
		selectedFeedbackId.value = response.data[0]?.feedback.id ?? null
	} catch {
		toast({ title: 'Unable to load feedbacks', variant: 'destructive' })
	} finally {
		isLoading.value = false
	}
}

onMounted(async () => {
	await loadFeedbacks()
})
</script>

<template>
	<div class="flex h-full min-h-0 bg-stone-950 text-stone-200">
		<aside class="flex w-56 shrink-0 flex-col border-r border-stone-900 bg-black/20 px-3 py-4">
			<p class="px-2 text-xs font-medium uppercase tracking-[0.24em] text-stone-500">Admin</p>
			<div class="mt-4 space-y-1">
				<button
					type="button"
					@click="activeSection = 'feedbacks'"
					class="flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm transition"
					:class="activeSection === 'feedbacks' ? 'bg-stone-900 text-stone-100' : 'text-stone-400 hover:bg-stone-900/60 hover:text-stone-200'">
					<MessageSquareWarning class="h-4 w-4" />
					<span>Feedbacks</span>
				</button>
			</div>
		</aside>

		<section class="flex min-w-0 flex-1 flex-col">
			<div class="flex items-center justify-between border-b border-stone-900 px-6 py-4">
				<div>
					<p class="text-xl font-semibold text-stone-100">Feedbacks</p>
					<p class="mt-1 text-sm text-stone-500">Conversations with typed feedback, comments, or bad ratings.</p>
				</div>
				<button
					type="button"
					:disabled="isLoading"
					@click="loadFeedbacks"
					class="inline-flex h-9 items-center gap-2 rounded-md border border-stone-800 px-3 text-sm text-stone-300 transition hover:border-stone-600 hover:bg-stone-900 disabled:opacity-50">
					<RefreshCw class="h-4 w-4" :class="isLoading ? 'animate-spin' : ''" />
					Refresh
				</button>
			</div>

			<div class="grid min-h-0 flex-1 grid-cols-[24rem_minmax(0,1fr)]">
				<div class="min-h-0 overflow-y-auto border-r border-stone-900">
					<div v-if="isLoading" class="p-5 text-sm text-stone-500">Loading feedbacks...</div>
					<div v-else-if="feedbackItems.length === 0" class="p-5 text-sm text-stone-500">No feedbacks match the admin review filter.</div>
					<button
						v-for="item in feedbackItems"
						:key="item.feedback.id"
						type="button"
						@click="selectedFeedbackId = item.feedback.id"
						class="block w-full border-b border-stone-900 px-5 py-4 text-left transition hover:bg-stone-900/50"
						:class="selectedItem?.feedback.id === item.feedback.id ? 'bg-stone-900/70' : ''">
						<div class="flex items-center justify-between gap-3">
							<p class="truncate text-sm font-medium text-stone-200">{{ item.conversation.title || 'Unnamed conversation' }}</p>
							<span class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-wide" :class="item.feedback.rating === 'bad' ? 'border-red-700/60 text-red-300' : 'border-emerald-700/50 text-emerald-300'">
								{{ item.feedback.rating }}
							</span>
						</div>
						<p class="mt-2 text-xs text-stone-500">{{ formatDatetime(item.feedback.updated_at || item.feedback.created_at) }}</p>
						<p class="mt-3 text-sm leading-5 text-stone-400">{{ truncate(item.user_message?.content) }}</p>
						<p v-if="item.feedback.feedback_type" class="mt-3 text-xs uppercase tracking-[0.18em] text-stone-500">
							{{ formatFeedbackType(item.feedback.feedback_type) }}
						</p>
					</button>
				</div>

				<div class="min-h-0 overflow-y-auto">
					<div v-if="selectedItem" class="mx-auto flex w-full max-w-5xl flex-col gap-6 px-8 py-7">
						<div class="flex flex-wrap items-center gap-2 text-xs">
							<span class="rounded-full border border-stone-800 px-2.5 py-1 text-stone-400">{{ selectedItem.conversation.id }}</span>
							<span class="rounded-full border px-2.5 py-1 uppercase tracking-wide" :class="selectedItem.feedback.rating === 'bad' ? 'border-red-700/60 text-red-300' : 'border-emerald-700/50 text-emerald-300'">
								{{ selectedItem.feedback.rating }}
							</span>
							<span class="rounded-full border border-stone-800 px-2.5 py-1 text-stone-400">{{ formatFeedbackType(selectedItem.feedback.feedback_type) }}</span>
							<span class="text-stone-600">{{ formatDatetime(selectedItem.feedback.updated_at || selectedItem.feedback.created_at) }}</span>
						</div>

						<div v-if="selectedItem.feedback.comment" class="rounded-md border border-stone-800 bg-black/20 p-4">
							<p class="text-xs font-medium uppercase tracking-[0.2em] text-stone-500">Feedback Comment</p>
							<p class="mt-3 whitespace-pre-wrap text-sm leading-6 text-stone-300">{{ selectedItem.feedback.comment }}</p>
						</div>

						<section class="space-y-3">
							<p class="text-sm font-semibold uppercase tracking-[0.2em] text-stone-500">Question</p>
							<div class="rounded-md border border-stone-800 bg-black/20 p-4">
								<p class="whitespace-pre-wrap text-sm leading-6 text-stone-200">{{ selectedItem.user_message?.content || 'No linked user message found.' }}</p>
							</div>
						</section>

						<section class="space-y-3">
							<p class="text-sm font-semibold uppercase tracking-[0.2em] text-stone-500">Response</p>
							<div class="rounded-md border border-stone-800 bg-black/20 p-4">
								<MarkdownRenderer :content="selectedItem.assistant_message.content || 'No response content.'" />
							</div>
						</section>

						<section class="space-y-3">
							<div class="flex items-center justify-between">
								<p class="text-sm font-semibold uppercase tracking-[0.2em] text-stone-500">Tools Called</p>
								<p class="text-xs text-stone-600">{{ toolCalls.length }} total</p>
							</div>
							<div v-if="toolCalls.length === 0" class="rounded-md border border-dashed border-stone-800 p-4 text-sm text-stone-500">
								No tool calls were recorded for this response.
							</div>
							<div v-else class="space-y-3">
								<div v-for="call in toolCalls" :key="`${call.agentName}-${call.id}`" class="rounded-md border border-stone-800 bg-black/20">
									<div class="flex flex-wrap items-center justify-between gap-3 border-b border-stone-800 px-4 py-3">
										<div>
											<p class="text-sm font-medium text-stone-200">{{ call.tool_name }}</p>
											<p class="mt-1 text-xs text-stone-500">{{ call.agentName }} · {{ call.status || 'unknown' }}</p>
										</div>
										<p v-if="call.error_message" class="text-xs text-red-300">{{ call.error_message }}</p>
									</div>
									<div class="grid gap-0 lg:grid-cols-2">
										<div class="border-b border-stone-800 p-4 lg:border-b-0 lg:border-r">
											<p class="text-xs font-medium uppercase tracking-[0.2em] text-stone-500">Input</p>
											<pre class="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs leading-5 text-stone-300">{{ formatJson(call.input_params ?? {}) }}</pre>
										</div>
										<div class="p-4">
											<p class="text-xs font-medium uppercase tracking-[0.2em] text-stone-500">Output</p>
											<pre class="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs leading-5 text-stone-300">{{ formatJson(call.output ?? null) }}</pre>
										</div>
									</div>
								</div>
							</div>
						</section>
					</div>
				</div>
			</div>
		</section>
	</div>
</template>
