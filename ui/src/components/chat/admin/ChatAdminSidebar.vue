<script setup lang="ts">
import { BarChart3, Gauge, MessageSquareWarning, Plug, Sparkles, Users } from 'lucide-vue-next'
import type { AdminSection } from './types'

defineProps<{
	activeSection: AdminSection
}>()

const emit = defineEmits<{
	(event: 'select', section: AdminSection): void
}>()

const sections: Array<{ id: AdminSection; label: string; icon: typeof BarChart3 }> = [
	{ id: 'overview', label: 'Overview', icon: BarChart3 },
	{ id: 'feedbacks', label: 'Feedbacks', icon: MessageSquareWarning },
	{ id: 'connectors', label: 'Connectors', icon: Plug },
	{ id: 'skills', label: 'Skills', icon: Sparkles },
	{ id: 'users', label: 'Users', icon: Users },
	{ id: 'latency', label: 'Latency', icon: Gauge },
]
</script>

<template>
	<aside class="flex w-56 shrink-0 flex-col border-r border-stone-900 bg-black/20 px-3 py-4">
		<p class="px-2 text-xs font-medium uppercase tracking-[0.24em] text-stone-500">Admin</p>
		<div class="mt-4 space-y-1">
			<button
				v-for="section in sections"
				:key="section.id"
				type="button"
				@click="emit('select', section.id)"
				class="flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm transition"
				:class="activeSection === section.id ? 'bg-stone-900 text-stone-100' : 'text-stone-400 hover:bg-stone-900/60 hover:text-stone-200'">
				<component :is="section.icon" class="h-4 w-4" />
				<span>{{ section.label }}</span>
			</button>
		</div>
	</aside>
</template>
