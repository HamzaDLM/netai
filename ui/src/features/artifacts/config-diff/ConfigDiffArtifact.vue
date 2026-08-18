<script setup lang="ts">
import { computed } from 'vue'
import ConfigDiffViewer from '@/components/chat/ConfigDiffViewer.vue'
import type { ArtifactEnvelope } from '../artifact.types'
import ArtifactViewerShell from '../ArtifactViewerShell.vue'
import { diffFilesFromArtifactData } from './config-diff.adapter'
import { configDiffArtifactDataSchema } from './config-diff.schema'

const props = defineProps<{
	artifact: ArtifactEnvelope
}>()

const parsed = computed(() => configDiffArtifactDataSchema.safeParse(props.artifact.data))
const data = computed(() => (parsed.value.success ? parsed.value.data : null))
const diffFiles = computed(() => (data.value ? diffFilesFromArtifactData(data.value) : []))
const target = computed(() => {
	const requested = data.value?.arguments?.device
	return data.value?.device ?? (typeof requested === 'string' ? requested : null)
})
const error = computed(() => data.value?.error ?? (props.artifact.status === 'failed' ? 'The configuration diff could not be loaded.' : null))
</script>

<template>
	<div class="min-w-0">
		<ConfigDiffViewer
			v-if="diffFiles.length > 0"
			:diff-files="diffFiles"
			:commit-message="data?.last_commit?.message"
			:commit-author="data?.last_commit?.author"
			:commit-date="data?.last_commit?.date"
		/>
		<ArtifactViewerShell v-else title="Diff viewer">
			<template #icon>
				<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" aria-hidden="true">
					<path fill="currentColor" d="M4 2h8a3 3 0 0 1 3 3v1h-1V5a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h1v1H4a3 3 0 0 1-3-3V5a3 3 0 0 1 3-3m11 6v3h-1V9h-2V8zm3 0a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3h-8a3 3 0 0 1-3-3v-1h1v1a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V8zM7 15v-2h1v2h2v1H7zm8-2a3 3 0 0 1-3 3v-1a2 2 0 0 0 2-2zm-5-4a2 2 0 0 0-2 2H7a3 3 0 0 1 3-3z" />
				</svg>
			</template>
			<template #default>
				<div v-if="error" class="p-4 text-sm text-red-300">{{ error }}</div>
				<div v-else-if="!parsed.success" class="p-4 text-sm text-red-300">The configuration diff artifact did not match schema version {{ artifact.schema_version }}.</div>
				<div v-else-if="artifact.status === 'running' || artifact.status === 'pending'" class="animate-pulse p-4 text-sm text-stone-400">
					Loading configuration diff<span v-if="target"> for <span class="font-semibold text-stone-300">{{ target }}</span></span>…
				</div>
				<div v-else class="p-4 text-sm text-stone-400">No configuration changes were returned.</div>
			</template>
		</ArtifactViewerShell>
	</div>
</template>
