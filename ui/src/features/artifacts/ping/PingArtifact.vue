<script setup lang="ts">
import { computed } from 'vue'
import type { ArtifactEnvelope } from '../artifact.types'
import ArtifactViewerShell from '../ArtifactViewerShell.vue'
import { pingArtifactDataSchema } from './ping.schema'

const props = defineProps<{
	artifact: ArtifactEnvelope
}>()

const parsed = computed(() => pingArtifactDataSchema.safeParse(props.artifact.data))
const data = computed(() => (parsed.value.success ? parsed.value.data : null))
const progress = computed(() => {
	if (!data.value || data.value.count <= 0) return 0
	return Math.min(100, Math.round((data.value.sent / data.value.count) * 100))
})

function metric(value: number | null | undefined): string {
	return typeof value === 'number' ? `${value.toFixed(2)} ms` : '—'
}
</script>

<template>
	<ArtifactViewerShell title="Ping test">
		<template #icon>
			<svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M3 12h3l2.2-6 4.2 12 2.2-6H21" />
			</svg>
		</template>

		<template #default="{ zoomed }">
			<template v-if="data">
				<div class="border-b border-stone-900 bg-stone-950 px-4 py-2 text-xs text-stone-300">
					<p>Target: <span class="font-semibold">{{ data.target }}</span></p>
				</div>

				<div class="grid gap-4 p-4">
					<div>
						<div class="mb-1 flex justify-between text-xs text-stone-500">
							<span>{{ data.sent }} / {{ data.count }} probes</span>
							<span>{{ progress }}%</span>
						</div>
						<div class="h-1.5 overflow-hidden rounded-full bg-stone-900">
							<div class="h-full rounded-full bg-red-500 transition-all duration-200" :style="{ width: `${progress}%` }" />
						</div>
					</div>

					<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
						<div class="rounded-md border border-stone-900 bg-stone-900/30 p-3">
							<p class="text-xs text-stone-500">Received</p>
							<p class="mt-1 text-lg font-semibold text-stone-200">{{ data.received }}/{{ data.sent }}</p>
						</div>
						<div class="rounded-md border border-stone-900 bg-stone-900/30 p-3">
							<p class="text-xs text-stone-500">Packet loss</p>
							<p class="mt-1 text-lg font-semibold" :class="data.loss_percent > 0 ? 'text-amber-300' : 'text-emerald-300'">{{ data.loss_percent }}%</p>
						</div>
						<div class="rounded-md border border-stone-900 bg-stone-900/30 p-3">
							<p class="text-xs text-stone-500">Average</p>
							<p class="mt-1 text-lg font-semibold text-stone-200">{{ metric(data.avg_ms) }}</p>
						</div>
						<div class="rounded-md border border-stone-900 bg-stone-900/30 p-3">
							<p class="text-xs text-stone-500">Jitter</p>
							<p class="mt-1 text-lg font-semibold text-stone-200">{{ metric(data.jitter_ms) }}</p>
						</div>
					</div>

					<div class="overflow-auto rounded-md border border-stone-900 bg-stone-950 font-mono text-xs" :class="zoomed ? 'max-h-[calc(90vh-18rem)]' : 'max-h-56'">
						<div v-if="data.samples.length === 0" class="animate-pulse px-3 py-4 text-stone-500">Waiting for the first reply…</div>
						<div v-for="sample in data.samples" :key="sample.sequence" class="flex items-center justify-between gap-3 border-b border-stone-900 px-3 py-2 last:border-b-0">
							<span class="text-stone-500">icmp_seq={{ sample.sequence }}</span>
							<span v-if="sample.status === 'reply'" class="text-emerald-300">{{ sample.bytes }} bytes · ttl={{ sample.ttl }} · time={{ metric(sample.latency_ms) }}</span>
							<span v-else class="text-amber-300">request timeout</span>
						</div>
					</div>
				</div>
			</template>
			<div v-else class="p-4 text-sm text-red-300">The ping artifact did not match schema version {{ artifact.schema_version }}.</div>
		</template>
	</ArtifactViewerShell>
</template>
