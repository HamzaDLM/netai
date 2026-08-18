<script setup lang="ts">
import { computed } from 'vue'
import type { ArtifactEnvelope } from '../artifact.types'
import ArtifactViewerShell from '../ArtifactViewerShell.vue'
import { tracerouteArtifactDataSchema } from './traceroute.schema'

const props = defineProps<{
	artifact: ArtifactEnvelope
}>()

const parsed = computed(() => tracerouteArtifactDataSchema.safeParse(props.artifact.data))
const data = computed(() => (parsed.value.success ? parsed.value.data : null))

function latency(values: number[]): string {
	return values.length ? values.map(value => `${value.toFixed(1)} ms`).join('  ') : '*  *  *'
}
</script>

<template>
	<ArtifactViewerShell title="Traceroute">
		<template #icon>
			<svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<circle cx="5" cy="6" r="2" />
				<circle cx="19" cy="18" r="2" />
				<path d="M7 6h4a3 3 0 0 1 3 3v6a3 3 0 0 0 3 3" />
				<path d="m9 4 2 2-2 2" />
			</svg>
		</template>

		<template #default="{ zoomed }">
			<template v-if="data">
				<div class="border-b border-stone-900 bg-stone-950 px-4 py-2 text-xs text-stone-300">
					<div class="flex flex-wrap gap-x-6 gap-y-1">
						<p>Target: <span class="font-semibold">{{ data.target }}</span></p>
						<p>Hops: <span class="font-semibold">{{ data.hops.length }}/{{ data.max_hops }}</span></p>
					</div>
				</div>

				<div class="overflow-auto p-4" :class="zoomed ? 'max-h-[calc(90vh-6rem)]' : 'max-h-[28rem]'">
					<div class="relative grid gap-1">
						<div class="absolute bottom-4 left-[1.12rem] top-4 w-px bg-stone-900" />
						<div v-for="hop in data.hops" :key="hop.hop" class="relative grid grid-cols-[2.25rem_minmax(0,1fr)] items-center gap-3 rounded-md px-1 py-2 hover:bg-stone-900/40">
							<span class="z-10 inline-flex h-8 w-8 items-center justify-center rounded-full border bg-stone-950 text-xs font-medium" :class="hop.status === 'destination' ? 'border-emerald-500/50 text-emerald-300' : hop.status === 'timeout' ? 'border-amber-500/40 text-amber-300' : 'border-stone-700 text-stone-300'">{{ hop.hop }}</span>
							<div class="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-1">
								<div class="min-w-0">
									<p class="truncate text-sm text-stone-200">{{ hop.hostname || 'No response' }}</p>
									<p class="text-xs text-stone-500">{{ hop.address || '—' }}</p>
								</div>
								<p class="text-xs" :class="hop.status === 'timeout' ? 'text-amber-300' : 'text-stone-400'">{{ latency(hop.latencies_ms) }}</p>
							</div>
						</div>
						<div v-if="artifact.status === 'running'" class="grid grid-cols-[2.25rem_minmax(0,1fr)] items-center gap-3 px-1 py-2">
							<span class="z-10 inline-flex h-8 w-8 animate-pulse items-center justify-center rounded-full border border-sky-500/40 bg-stone-950 text-sky-300">…</span>
							<p class="animate-pulse text-sm text-stone-500">Discovering the next hop…</p>
						</div>
					</div>
				</div>
			</template>
			<div v-else class="p-4 text-sm text-red-300">The traceroute artifact did not match schema version {{ artifact.schema_version }}.</div>
		</template>
	</ArtifactViewerShell>
</template>
