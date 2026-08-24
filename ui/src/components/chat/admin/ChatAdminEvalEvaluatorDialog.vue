<script setup lang="ts">
import { computed, reactive } from 'vue'
import { Bot, BrainCircuit, ShieldCheck } from 'lucide-vue-next'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { EvalEvaluatorKind, NewEvalEvaluator } from './evals.types'

defineProps<{ open: boolean }>()

const emit = defineEmits<{
	(event: 'update:open', open: boolean): void
	(event: 'create', evaluator: NewEvalEvaluator): void
}>()

const form = reactive({
	name: '',
	kind: 'llm_judge' as EvalEvaluatorKind,
	rule: 'llm_judge' as NewEvalEvaluator['rule'],
	description: '',
	criteria: '',
	threshold: 85,
})

const canCreate = computed(() => Boolean(form.name.trim() && form.description.trim() && form.criteria.trim() && form.threshold >= 0 && form.threshold <= 100))

function resetForm() {
	form.name = ''
	form.kind = 'llm_judge'
	form.rule = 'llm_judge'
	form.description = ''
	form.criteria = ''
	form.threshold = 85
}

function createEvaluator() {
	if (!canCreate.value) return
	emit('create', {
		name: form.name.trim(),
		kind: form.kind,
		rule: form.rule,
		description: form.description.trim(),
		criteria: form.criteria.trim(),
		threshold: Number(form.threshold),
	})
	resetForm()
	emit('update:open', false)
}
</script>

<template>
	<Dialog :open="open" @update:open="emit('update:open', $event)">
		<DialogContent class="max-w-2xl border-stone-800 bg-stone-950 p-0 text-stone-200">
			<DialogHeader class="border-b border-white/7 px-7 py-6">
				<div class="flex items-center gap-3">
					<div class="flex h-10 w-10 items-center justify-center rounded-lg border border-violet-500/20 bg-violet-500/[0.06] text-violet-400"><BrainCircuit class="h-5 w-5" /></div>
					<div><DialogTitle class="text-xl text-stone-100">Create evaluator</DialogTitle><DialogDescription class="mt-1 text-stone-500">Add a deterministic architecture gate or a structured LLM judge.</DialogDescription></div>
				</div>
			</DialogHeader>

			<form class="space-y-6 px-7 py-6" @submit.prevent="createEvaluator">
				<label class="block space-y-2"><span class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Evaluator name</span><input v-model="form.name" class="h-10 w-full rounded-md border border-stone-800 bg-black/30 px-3 text-sm text-stone-200 outline-none transition placeholder:text-stone-700 focus:border-stone-600" placeholder="Evidence completeness" /></label>

				<div>
					<p class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Evaluator type</p>
					<div class="mt-3 grid gap-3 sm:grid-cols-2">
						<button type="button" class="rounded-lg border p-4 text-left transition" :class="form.kind === 'llm_judge' ? 'border-violet-500/30 bg-violet-500/[0.06]' : 'border-white/7 bg-white/[0.02]'" @click="form.kind = 'llm_judge'; form.rule = 'llm_judge'"><Bot class="h-4 w-4 text-violet-400" /><p class="mt-3 text-sm font-medium text-stone-200">LLM as evaluator</p><p class="mt-1 text-xs leading-5 text-stone-600">Semantic scoring against the answer, expected facts, and recorded evidence.</p></button>
						<button type="button" class="rounded-lg border p-4 text-left transition" :class="form.kind === 'deterministic' ? 'border-emerald-500/30 bg-emerald-500/[0.06]' : 'border-white/7 bg-white/[0.02]'" @click="form.kind = 'deterministic'; form.rule = 'tool_trajectory'"><ShieldCheck class="h-4 w-4 text-emerald-400" /><p class="mt-3 text-sm font-medium text-stone-200">Deterministic gate</p><p class="mt-1 text-xs leading-5 text-stone-600">Exact checks over tools, statuses, artifacts, budgets, or policies.</p></button>
					</div>
				</div>

				<label v-if="form.kind === 'deterministic'" class="block space-y-2"><span class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Gate implementation</span><select v-model="form.rule" class="h-10 w-full rounded-md border border-stone-800 bg-black/30 px-3 text-sm text-stone-200 outline-none transition focus:border-stone-600"><option value="tool_trajectory">Required / forbidden tool trajectory</option><option value="completion_safety">Completion and execution budget</option></select></label>

				<label class="block space-y-2"><span class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Description</span><textarea v-model="form.description" rows="2" class="w-full resize-none rounded-md border border-stone-800 bg-black/30 px-3 py-2 text-sm leading-6 text-stone-200 outline-none transition placeholder:text-stone-700 focus:border-stone-600" placeholder="What quality or architecture behavior does this evaluator measure?" /></label>
				<label class="block space-y-2"><span class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">{{ form.kind === 'llm_judge' ? 'Judge rubric' : 'Gate criteria' }}</span><textarea v-model="form.criteria" rows="4" class="w-full resize-none rounded-md border border-stone-800 bg-black/30 px-3 py-2 text-sm leading-6 text-stone-200 outline-none transition placeholder:text-stone-700 focus:border-stone-600" :placeholder="form.kind === 'llm_judge' ? 'Compare every material claim with successful tool evidence. Return a structured score and concise reasoning.' : 'Pass only when all expected artifacts are completed and no mutating tool was invoked.'" /></label>

				<label class="block space-y-2"><span class="flex items-center justify-between text-xs font-semibold uppercase tracking-[0.18em] text-stone-500"><span>Pass threshold</span><span class="text-stone-300">{{ form.threshold }}/100</span></span><input v-model.number="form.threshold" type="range" min="0" max="100" step="1" class="w-full accent-red-500" /></label>

				<div class="flex justify-end gap-3 border-t border-white/7 pt-5"><button type="button" class="rounded-md border border-stone-800 px-4 py-2 text-sm text-stone-400 transition hover:bg-stone-900" @click="emit('update:open', false)">Cancel</button><button type="submit" :disabled="!canCreate" class="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40">Create evaluator</button></div>
			</form>
		</DialogContent>
	</Dialog>
</template>
