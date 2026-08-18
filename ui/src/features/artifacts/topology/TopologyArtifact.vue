<script setup lang="ts">
import { computed } from 'vue'
import TopologyMapper from '@/components/chat/TopologyMapper.vue'
import type { ArtifactEnvelope } from '../artifact.types'
import ArtifactViewerShell from '../ArtifactViewerShell.vue'
import { topologyArtifactDataSchema, type TopologyPayload } from './topology.schema'

const props = defineProps<{
	artifact: ArtifactEnvelope
}>()

const parsed = computed(() => topologyArtifactDataSchema.safeParse(props.artifact.data))
const data = computed(() => (parsed.value.success ? parsed.value.data : null))
const topology = computed<TopologyPayload | null>(() => {
	const value = data.value
	if (!value?.devices?.length || !value.links) return null
	return {
		...value,
		scope: value.scope ?? 'all_sites',
		device_count: value.device_count ?? value.devices.length,
		link_count: value.link_count ?? value.links.length,
		devices: value.devices,
		links: value.links,
	}
})
const requestedScope = computed(() => {
	const site = data.value?.arguments?.site
	return typeof site === 'string' && site ? site : 'all sites'
})
const error = computed(() => data.value?.error ?? (props.artifact.status === 'failed' ? 'The topology could not be loaded.' : null))
</script>

<template>
	<div class="min-w-0">
		<TopologyMapper v-if="topology" :topology="topology" />
		<ArtifactViewerShell v-else title="Topology mapper">
			<template #icon>
				<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" aria-hidden="true">
					<path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19a2 2 0 1 0-4 0a2 2 0 0 0 4 0m8-14a2 2 0 1 0-4 0a2 2 0 0 0 4 0m-8 0a2 2 0 1 0-4 0a2 2 0 0 0 4 0m-4 7a2 2 0 1 0-4 0a2 2 0 0 0 4 0m12 7a2 2 0 1 0-4 0a2 2 0 0 0 4 0m-4-7a2 2 0 1 0-4 0a2 2 0 0 0 4 0m8 0a2 2 0 1 0-4 0a2 2 0 0 0 4 0M6 12h4m4 0h4m-3-5l-2 3M9 7l2 3m0 4l-2 3m4-3l2 3" />
				</svg>
			</template>
			<template #default>
				<div v-if="error" class="p-4 text-sm text-red-300">{{ error }}</div>
				<div v-else-if="!parsed.success" class="p-4 text-sm text-red-300">The topology artifact did not match schema version {{ artifact.schema_version }}.</div>
				<div v-else-if="artifact.status === 'running' || artifact.status === 'pending'" class="animate-pulse p-4 text-sm text-stone-400">
					Loading topology for <span class="font-semibold text-stone-300">{{ requestedScope }}</span>…
				</div>
				<div v-else class="p-4 text-sm text-stone-400">No topology data is available for <span class="font-semibold text-stone-300">{{ requestedScope }}</span>.</div>
			</template>
		</ArtifactViewerShell>
	</div>
</template>
