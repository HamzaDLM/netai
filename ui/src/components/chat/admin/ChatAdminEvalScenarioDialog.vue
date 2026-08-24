<script setup lang="ts">
import { computed, reactive } from 'vue'
import { BrainCircuit, Check, ShieldCheck, Wrench } from 'lucide-vue-next'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { EvalEvaluator, NewEvalScenario } from './evals.types'

defineProps<{
	open: boolean
	evaluators: EvalEvaluator[]
}>()

const emit = defineEmits<{
	(event: 'update:open', open: boolean): void
	(event: 'create', scenario: NewEvalScenario): void
}>()

const form = reactive({
	name: '',
	description: '',
	prompt: '',
	fixture: '',
	requiredTools: '',
	forbiddenTools: '',
	expectedFacts: '',
	evaluatorIds: ['tool-trajectory', 'answer-groundedness', 'completion-safety'] as string[],
})

const canCreate = computed(() => Boolean(form.name.trim() && form.prompt.trim() && form.fixture.trim() && form.evaluatorIds.length))

function lines(value: string): string[] {
	return value
		.split(/[,\n]/)
		.map(item => item.trim())
		.filter(Boolean)
}

function toggleEvaluator(id: string) {
	form.evaluatorIds = form.evaluatorIds.includes(id) ? form.evaluatorIds.filter(value => value !== id) : [...form.evaluatorIds, id]
}

function resetForm() {
	form.name = ''
	form.description = ''
	form.prompt = ''
	form.fixture = ''
	form.requiredTools = ''
	form.forbiddenTools = ''
	form.expectedFacts = ''
	form.evaluatorIds = ['tool-trajectory', 'answer-groundedness', 'completion-safety']
}

function createScenario() {
	if (!canCreate.value) return
	emit('create', {
		name: form.name.trim(),
		description: form.description.trim(),
		prompt: form.prompt.trim(),
		fixture: form.fixture.trim(),
		requiredTools: lines(form.requiredTools),
		forbiddenTools: lines(form.forbiddenTools),
		expectedFacts: lines(form.expectedFacts),
		evaluatorIds: [...form.evaluatorIds],
	})
	resetForm()
	emit('update:open', false)
}
</script>

<template>
	<Dialog :open="open" @update:open="emit('update:open', $event)">
		<DialogContent class="max-h-[90vh] max-w-4xl overflow-y-auto border-stone-800 bg-stone-950 p-0 text-stone-200">
			<DialogHeader class="border-b border-white/7 px-7 py-6">
				<div class="flex items-center gap-3">
					<div class="flex h-10 w-10 items-center justify-center rounded-lg border border-red-500/20 bg-red-500/8 text-red-400">
						<BrainCircuit class="h-5 w-5" />
					</div>
					<div>
						<DialogTitle class="text-xl text-stone-100">Create evaluation scenario</DialogTitle>
						<DialogDescription class="mt-1 text-stone-500">Define the use case, simulated infrastructure state, expected tool behavior, and scoring suite.</DialogDescription>
					</div>
				</div>
			</DialogHeader>

			<form class="space-y-7 px-7 py-6" @submit.prevent="createScenario">
				<div class="grid gap-5 md:grid-cols-2">
					<label class="space-y-2">
						<span class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Scenario name</span>
						<input v-model="form.name" class="h-10 w-full rounded-md border border-stone-800 bg-black/30 px-3 text-sm text-stone-200 outline-none transition placeholder:text-stone-700 focus:border-stone-600" placeholder="OSPF adjacency regression" />
					</label>
					<label class="space-y-2">
						<span class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Fixture / environment state</span>
						<input v-model="form.fixture" class="h-10 w-full rounded-md border border-stone-800 bg-black/30 px-3 text-sm text-stone-200 outline-none transition placeholder:text-stone-700 focus:border-stone-600" placeholder="OSPF neighbor down · interface up" />
					</label>
				</div>

				<label class="block space-y-2">
					<span class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Purpose</span>
					<textarea v-model="form.description" rows="2" class="w-full resize-none rounded-md border border-stone-800 bg-black/30 px-3 py-2 text-sm leading-6 text-stone-200 outline-none transition placeholder:text-stone-700 focus:border-stone-600" placeholder="What architecture behavior should this scenario protect?" />
				</label>

				<label class="block space-y-2">
					<span class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">User request</span>
					<textarea v-model="form.prompt" rows="3" class="w-full resize-none rounded-md border border-stone-800 bg-black/30 px-3 py-2 text-sm leading-6 text-stone-200 outline-none transition placeholder:text-stone-700 focus:border-stone-600" placeholder="Enter the exact message that will be sent through NetAIService.run()" />
				</label>

				<div class="grid gap-5 md:grid-cols-3">
					<label class="space-y-2">
						<span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500"><Wrench class="h-3.5 w-3.5" /> Required tools</span>
						<textarea v-model="form.requiredTools" rows="4" class="w-full resize-none rounded-md border border-stone-800 bg-black/30 px-3 py-2 font-mono text-xs leading-5 text-stone-300 outline-none transition placeholder:text-stone-700 focus:border-stone-600" placeholder="suzieq_get_bgp&#10;zabbix_get_problems" />
					</label>
					<label class="space-y-2">
						<span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500"><ShieldCheck class="h-3.5 w-3.5" /> Forbidden tools</span>
						<textarea v-model="form.forbiddenTools" rows="4" class="w-full resize-none rounded-md border border-stone-800 bg-black/30 px-3 py-2 font-mono text-xs leading-5 text-stone-300 outline-none transition placeholder:text-stone-700 focus:border-stone-600" placeholder="bitbucket_commit_changes" />
					</label>
					<label class="space-y-2">
						<span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500"><Check class="h-3.5 w-3.5" /> Expected facts</span>
						<textarea v-model="form.expectedFacts" rows="4" class="w-full resize-none rounded-md border border-stone-800 bg-black/30 px-3 py-2 text-xs leading-5 text-stone-300 outline-none transition placeholder:text-stone-700 focus:border-stone-600" placeholder="Peer is down&#10;Interface remains up" />
					</label>
				</div>

				<div>
					<div class="flex items-center justify-between gap-4">
						<div>
							<p class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Evaluation suite</p>
							<p class="mt-1 text-sm text-stone-600">Select at least one evaluator. Hard safety checks should remain deterministic.</p>
						</div>
						<span class="text-xs text-stone-500">{{ form.evaluatorIds.length }} selected</span>
					</div>
					<div class="mt-4 grid gap-3 md:grid-cols-2">
						<button v-for="evaluator in evaluators" :key="evaluator.id" type="button" class="rounded-lg border p-4 text-left transition" :class="form.evaluatorIds.includes(evaluator.id) ? 'border-red-500/30 bg-red-500/[0.06]' : 'border-white/7 bg-white/[0.02] hover:border-white/12'" @click="toggleEvaluator(evaluator.id)">
							<div class="flex items-start justify-between gap-3">
								<div>
									<p class="text-sm font-medium text-stone-200">{{ evaluator.name }}</p>
									<p class="mt-1 text-xs uppercase tracking-[0.14em] text-stone-600">{{ evaluator.kind === 'llm_judge' ? 'LLM judge' : 'Deterministic' }}</p>
								</div>
								<span class="flex h-5 w-5 items-center justify-center rounded-full border" :class="form.evaluatorIds.includes(evaluator.id) ? 'border-red-400 bg-red-500 text-white' : 'border-stone-700 text-transparent'">
									<Check class="h-3 w-3" />
								</span>
							</div>
							<p class="mt-3 text-xs leading-5 text-stone-500">{{ evaluator.description }}</p>
						</button>
					</div>
				</div>

				<div class="flex justify-end gap-3 border-t border-white/7 pt-5">
					<button type="button" class="rounded-md border border-stone-800 px-4 py-2 text-sm text-stone-400 transition hover:bg-stone-900" @click="emit('update:open', false)">Cancel</button>
					<button type="submit" :disabled="!canCreate" class="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40">Create scenario</button>
				</div>
			</form>
		</DialogContent>
	</Dialog>
</template>
