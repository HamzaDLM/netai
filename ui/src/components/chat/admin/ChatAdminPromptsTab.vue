<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, Clock3, Edit3, Eye, FileClock, RotateCcw, Save, ShieldCheck, X } from 'lucide-vue-next'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { toast } from '@/components/ui/toast'
import ChatAdminPromptDiffDialog from './ChatAdminPromptDiffDialog.vue'
import type { SystemPromptVersion } from './prompts.types'

const INITIAL_PROMPT = `You are NetAI, a network infrastructure operations assistant.

Own the investigation from the user's question through the final answer. Use the minimum evidence needed and distinguish observed facts from assumptions. Never invent tool output.

Tools are read-only and progressively disclosed. Search for connector and operation keywords, then call the returned tool directly. Apply dynamically injected tool-group guidance only to the corresponding tools.

Keep answers concise, explain material uncertainty, and cite the infrastructure evidence used to reach a conclusion.`

const versions = ref<SystemPromptVersion[]>([
	{
		id: 'netai-system-v4',
		version: 4,
		content: INITIAL_PROMPT,
		author: 'Maya Chen',
		createdAt: '2026-08-25T14:42:00Z',
		changeSummary: 'Clarify evidence rules and response expectations',
	},
	{
		id: 'netai-system-v3',
		version: 3,
		content: INITIAL_PROMPT.replace('\n\nKeep answers concise, explain material uncertainty, and cite the infrastructure evidence used to reach a conclusion.', ''),
		author: 'Noah Williams',
		createdAt: '2026-08-12T09:18:00Z',
		changeSummary: 'Adopt progressive tool discovery',
	},
	{
		id: 'netai-system-v2',
		version: 2,
		content: `You are NetAI, a network infrastructure operations assistant.

Investigate the user's question using the available read-only tools. Clearly distinguish evidence returned by tools from assumptions, and never invent tool output.

Provide a concise final answer with the most important findings first.`,
		author: 'Lina Patel',
		createdAt: '2026-07-29T16:05:00Z',
		changeSummary: 'Strengthen evidence and safety guidance',
	},
	{
		id: 'netai-system-v1',
		version: 1,
		content: `You are NetAI, a network infrastructure assistant. Use the available tools to help network engineers investigate infrastructure questions and explain your findings clearly.`,
		author: 'Alex Morgan',
		createdAt: '2026-07-10T10:20:00Z',
		changeSummary: 'Initial NetAI system prompt',
	},
])

const editorContent = ref(versions.value[0].content)
const changeSummary = ref('')
const isEditing = ref(false)
const diffOpen = ref(false)
const diffBefore = ref<SystemPromptVersion | null>(null)
const diffAfter = ref<SystemPromptVersion | null>(null)

const currentVersion = computed(() => versions.value[0])
const hasChanges = computed(() => editorContent.value !== currentVersion.value.content)
const canSave = computed(() => hasChanges.value && changeSummary.value.trim().length > 0)

function formattedDate(value: string): string {
	return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function startEditing(): void {
	editorContent.value = currentVersion.value.content
	changeSummary.value = ''
	isEditing.value = true
}

function cancelEditing(): void {
	editorContent.value = currentVersion.value.content
	changeSummary.value = ''
	isEditing.value = false
}

function saveVersion(): void {
	if (!canSave.value) return

	const version: SystemPromptVersion = {
		id: `netai-system-v${currentVersion.value.version + 1}-${Date.now()}`,
		version: currentVersion.value.version + 1,
		content: editorContent.value,
		author: 'Current admin',
		createdAt: new Date().toISOString(),
		changeSummary: changeSummary.value.trim(),
	}

	versions.value.unshift(version)
	changeSummary.value = ''
	isEditing.value = false
	toast({
		title: `System prompt v${version.version} saved locally`,
		description: 'This frontend concept is not connected to the running NetAI agent.',
	})
}

function showVersionDiff(version: SystemPromptVersion): void {
	const index = versions.value.findIndex(candidate => candidate.id === version.id)
	diffAfter.value = version
	diffBefore.value = index >= 0 ? (versions.value[index + 1] ?? null) : null
	diffOpen.value = true
}
</script>

<template>
	<section class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-stone-950">
		<header class="flex flex-wrap items-center justify-between gap-4 border-b border-stone-900 px-6 py-4">
			<div>
				<h1 class="text-xl font-semibold text-stone-100">NetAI System Prompt</h1>
				<p class="mt-1 text-sm text-stone-500">Manage the main instruction that defines NetAI's identity and general behavior.</p>
			</div>
			<div class="flex items-center gap-2 rounded-lg border border-emerald-500/15 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-300">
				<ShieldCheck class="h-4 w-4" />
				Active version v{{ currentVersion.version }}
			</div>
		</header>

		<div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_320px]">
			<main class="flex min-h-0 min-w-0 flex-col border-r border-stone-900">
				<div class="flex min-h-[65px] flex-wrap items-center justify-between gap-4 border-b border-stone-900 px-8 py-3">
					<div class="flex items-center gap-3">
						<h2 class="text-sm font-medium text-stone-200">System instruction</h2>
						<span class="font-mono text-xs text-stone-600">v{{ currentVersion.version }}</span>
						<span v-if="isEditing" class="text-xs text-amber-400">Editing a new version</span>
					</div>
					<button v-if="!isEditing" type="button" class="inline-flex h-9 items-center gap-2 rounded-md bg-red-600 px-3 text-sm font-medium text-white transition hover:bg-red-500" @click="startEditing"><Edit3 class="h-4 w-4" />Modify prompt</button>
				</div>

				<div v-if="!isEditing" class="min-h-0 flex-1 overflow-y-auto px-10 py-8">
					<article class="mx-auto max-w-4xl">
						<MarkdownRenderer :content="currentVersion.content" />
					</article>
				</div>

				<div v-else class="flex min-h-0 flex-1 flex-col p-6">
					<textarea v-model="editorContent" spellcheck="false" class="min-h-[360px] flex-1 resize-none rounded-lg border border-red-500/30 bg-[#090909] p-5 font-mono text-sm leading-7 text-stone-200 outline-none ring-2 ring-red-500/5 transition focus:border-red-500/50" />
					<label class="mt-4 block">
						<span class="text-xs font-medium text-stone-400">Change summary</span>
						<input v-model="changeSummary" type="text" placeholder="Briefly explain what changed and why" class="mt-2 h-10 w-full rounded-md border border-stone-800 bg-stone-950 px-3 text-sm text-stone-200 outline-none placeholder:text-stone-700 focus:border-red-500/40" />
					</label>
					<div class="mt-4 flex flex-wrap items-center justify-between gap-3">
						<p class="flex items-center gap-2 text-xs" :class="hasChanges ? 'text-amber-300' : 'text-stone-600'">
							<Check v-if="hasChanges" class="h-3.5 w-3.5" />
							<RotateCcw v-else class="h-3.5 w-3.5" />
							{{ hasChanges ? 'Changes ready to save' : 'Make a change to create a new version' }}
						</p>
						<div class="flex items-center gap-2">
							<button type="button" class="inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm text-stone-500 transition hover:bg-stone-900 hover:text-stone-300" @click="cancelEditing"><X class="h-4 w-4" />Cancel</button>
							<button type="button" :disabled="!canSave" class="inline-flex h-9 items-center gap-2 rounded-md bg-red-600 px-3 text-sm font-medium text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40" @click="saveVersion"><Save class="h-4 w-4" />Save new version</button>
						</div>
					</div>
				</div>
			</main>

			<aside class="min-h-0 overflow-y-auto bg-black/15">
				<div class="sticky top-0 z-10 border-b border-stone-900 bg-stone-950/95 px-5 py-5 backdrop-blur">
					<div class="flex items-center gap-2 text-stone-200">
						<FileClock class="h-4 w-4 text-red-400" />
						<h2 class="text-sm font-semibold">Change history</h2>
					</div>
					<p class="mt-1 text-xs text-stone-600">{{ versions.length }} saved versions</p>
				</div>

				<ol class="relative ml-6 mr-4 mt-5 border-l border-stone-800 pb-6">
					<li v-for="(version, index) in versions" :key="version.id" class="relative pb-6 pl-5 last:pb-0">
						<span class="absolute -left-[5px] top-1 h-2.5 w-2.5 rounded-full border-2 border-stone-950" :class="index === 0 ? 'bg-red-500' : 'bg-stone-700'" />
						<article>
							<div class="flex items-start justify-between gap-3">
								<div class="min-w-0">
									<div class="flex items-center gap-2">
										<span class="font-mono text-sm font-semibold text-stone-300">v{{ version.version }}</span>
										<span v-if="index === 0" class="text-[10px] uppercase tracking-wider text-emerald-400">Active</span>
									</div>
									<p class="mt-1.5 text-xs leading-5 text-stone-400">{{ version.changeSummary }}</p>
								</div>
								<button type="button" class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-stone-600 transition hover:bg-stone-900 hover:text-stone-200" :aria-label="`View changes in v${version.version}`" :title="`View v${version.version} diff`" @click="showVersionDiff(version)"><Eye class="h-3.5 w-3.5" /></button>
							</div>
							<div class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-stone-600">
								<span>{{ version.author }}</span>
								<span class="text-stone-800">·</span>
								<span class="flex items-center gap-1"><Clock3 class="h-3 w-3" />{{ formattedDate(version.createdAt) }}</span>
							</div>
						</article>
					</li>
				</ol>
			</aside>
		</div>

		<ChatAdminPromptDiffDialog v-model:open="diffOpen" prompt-name="NetAI System Prompt" :left="diffBefore" :right="diffAfter" />
	</section>
</template>
