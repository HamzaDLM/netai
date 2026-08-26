<script setup lang="ts">
import { computed } from 'vue'
import { GitCompareArrows } from 'lucide-vue-next'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { SystemPromptVersion } from './prompts.types'

type DiffLine = {
	type: 'same' | 'added' | 'removed'
	content: string
	oldNumber: number | null
	newNumber: number | null
}

const props = defineProps<{
	open: boolean
	promptName: string
	left: SystemPromptVersion | null
	right: SystemPromptVersion | null
}>()

const emit = defineEmits<{ (event: 'update:open', value: boolean): void }>()

const diffLines = computed<DiffLine[]>(() => {
	if (!props.right) return []
	const before = props.left?.content.split('\n') ?? []
	const after = props.right.content.split('\n')
	const lengths = Array.from({ length: before.length + 1 }, () => Array<number>(after.length + 1).fill(0))

	for (let leftIndex = before.length - 1; leftIndex >= 0; leftIndex -= 1) {
		for (let rightIndex = after.length - 1; rightIndex >= 0; rightIndex -= 1) {
			lengths[leftIndex][rightIndex] = before[leftIndex] === after[rightIndex] ? lengths[leftIndex + 1][rightIndex + 1] + 1 : Math.max(lengths[leftIndex + 1][rightIndex], lengths[leftIndex][rightIndex + 1])
		}
	}

	const lines: DiffLine[] = []
	let leftIndex = 0
	let rightIndex = 0
	while (leftIndex < before.length || rightIndex < after.length) {
		if (leftIndex < before.length && rightIndex < after.length && before[leftIndex] === after[rightIndex]) {
			lines.push({ type: 'same', content: before[leftIndex], oldNumber: leftIndex + 1, newNumber: rightIndex + 1 })
			leftIndex += 1
			rightIndex += 1
		} else if (rightIndex < after.length && (leftIndex >= before.length || lengths[leftIndex][rightIndex + 1] >= lengths[leftIndex + 1][rightIndex])) {
			lines.push({ type: 'added', content: after[rightIndex], oldNumber: null, newNumber: rightIndex + 1 })
			rightIndex += 1
		} else {
			lines.push({ type: 'removed', content: before[leftIndex], oldNumber: leftIndex + 1, newNumber: null })
			leftIndex += 1
		}
	}
	return lines
})

const changeCount = computed(() => diffLines.value.filter(line => line.type !== 'same').length)
</script>

<template>
	<Dialog :open="open" @update:open="emit('update:open', $event)">
		<DialogContent class="max-h-[88vh] max-w-5xl overflow-hidden border-stone-800 bg-stone-950 p-0 text-stone-200">
			<DialogHeader class="border-b border-stone-800 px-6 py-5">
				<div class="flex items-center gap-3">
					<div class="flex h-9 w-9 items-center justify-center rounded-lg border border-red-500/20 bg-red-500/10 text-red-300"><GitCompareArrows class="h-4 w-4" /></div>
					<div>
						<DialogTitle>{{ promptName }} · v{{ right?.version }}</DialogTitle>
						<DialogDescription class="mt-1 text-stone-500">{{ left ? `Changes from v${left.version}` : 'Initial version' }} · {{ changeCount }} changed lines</DialogDescription>
					</div>
				</div>
			</DialogHeader>

			<div v-if="right" class="min-h-0 overflow-auto bg-[#090909] py-3 font-mono text-xs leading-6">
				<div
					v-for="(line, index) in diffLines"
					:key="`${index}-${line.type}`"
					class="grid grid-cols-[42px_42px_24px_minmax(0,1fr)] border-l-2 px-3"
					:class="{
						'border-transparent text-stone-500': line.type === 'same',
						'border-emerald-500 bg-emerald-500/10 text-emerald-200': line.type === 'added',
						'border-red-500 bg-red-500/10 text-red-200': line.type === 'removed',
					}"
				>
					<span class="select-none text-right text-stone-700">{{ line.oldNumber ?? '' }}</span>
					<span class="select-none text-right text-stone-700">{{ line.newNumber ?? '' }}</span>
					<span class="select-none text-center" :class="line.type === 'added' ? 'text-emerald-400' : line.type === 'removed' ? 'text-red-400' : 'text-stone-700'">{{ line.type === 'added' ? '+' : line.type === 'removed' ? '−' : ' ' }}</span>
					<span class="whitespace-pre-wrap break-words pl-2">{{ line.content || ' ' }}</span>
				</div>
			</div>
		</DialogContent>
	</Dialog>
</template>
