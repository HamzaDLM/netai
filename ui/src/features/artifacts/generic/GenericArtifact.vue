<script setup lang="ts">
import type { ArtifactEnvelope } from '../artifact.types'
import ArtifactViewerShell from '../ArtifactViewerShell.vue'

defineProps<{
	artifact: ArtifactEnvelope
}>()
</script>

<template>
	<ArtifactViewerShell :title="artifact.title">
		<template #icon>
			<svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="m8 9-3 3 3 3" />
				<path d="m16 9 3 3-3 3" />
				<path d="m14 5-4 14" />
			</svg>
		</template>
		<template #default="{ zoomed }">
			<div class="border-b border-stone-900 bg-stone-950 px-4 py-2 text-xs text-stone-300">
				<p>{{ artifact.kind }}</p>
			</div>
			<pre class="overflow-auto p-4 text-xs text-stone-300" :class="zoomed ? 'max-h-[calc(90vh-6rem)]' : 'max-h-80'">{{ JSON.stringify(artifact.data, null, 2) }}</pre>
		</template>
	</ArtifactViewerShell>
</template>
