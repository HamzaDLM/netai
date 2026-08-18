<script setup lang="ts">
import { computed } from 'vue'
import VueApexCharts from 'vue3-apexcharts'
import type { ApexOptions } from 'apexcharts'
import type { ArtifactEnvelope } from '../artifact.types'
import ArtifactViewerShell from '../ArtifactViewerShell.vue'
import { latencyChartArtifactDataSchema } from './latency-chart.schema'

const props = defineProps<{
	artifact: ArtifactEnvelope
}>()

const parsed = computed(() => latencyChartArtifactDataSchema.safeParse(props.artifact.data))
const data = computed(() => (parsed.value.success ? parsed.value.data : null))
const series = computed(() => [
	{
		name: 'Latency',
		data: (data.value?.points ?? []).map(point => [new Date(point.timestamp).getTime(), point.value]),
	},
])
const options = computed<ApexOptions>(() => ({
	chart: {
		type: 'area',
		animations: { enabled: true, dynamicAnimation: { speed: 180 } },
		toolbar: { show: false },
		background: 'transparent',
		foreColor: '#a8a29e',
	},
	colors: ['#ef4444'],
	dataLabels: { enabled: false },
	stroke: { curve: 'smooth', width: 2 },
	fill: {
		type: 'gradient',
		gradient: { opacityFrom: 0.35, opacityTo: 0.02 },
	},
	grid: { borderColor: '#1c1917', strokeDashArray: 3 },
	xaxis: {
		type: 'datetime',
		labels: { style: { colors: '#78716c' }, datetimeUTC: false },
		axisBorder: { color: '#292524' },
		axisTicks: { color: '#292524' },
	},
	yaxis: {
		labels: {
			style: { colors: '#78716c' },
			formatter: value => `${value.toFixed(0)} ms`,
		},
	},
	tooltip: { theme: 'dark', x: { format: 'HH:mm:ss' } },
	theme: { mode: 'dark' },
}))

function metric(value: number | undefined): string {
	return typeof value === 'number' ? `${value.toFixed(2)} ms` : '—'
}
</script>

<template>
	<ArtifactViewerShell title="Latency chart">
		<template #icon>
			<svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M4 19V5" />
				<path d="M4 19h16" />
				<path d="m7 15 3-4 3 2 4-6" />
				<path d="M17 7h3v3" />
			</svg>
		</template>

		<template #default="{ zoomed }">
			<template v-if="data">
				<div class="border-b border-stone-900 bg-stone-950 px-4 py-2 text-xs text-stone-300">
					<div class="flex flex-wrap gap-x-6 gap-y-1">
						<p>Target: <span class="font-semibold">{{ data.target }}</span></p>
						<p>Samples: <span class="font-semibold">{{ data.points.length }}</span></p>
					</div>
				</div>

				<div class="p-4">
					<div class="mb-2 grid grid-cols-3 gap-2 text-center">
						<div class="rounded-md border border-stone-900 bg-stone-900/30 p-2"><p class="text-xs text-stone-500">Min</p><p class="text-sm font-medium text-stone-200">{{ metric(data.min_ms) }}</p></div>
						<div class="rounded-md border border-stone-900 bg-stone-900/30 p-2"><p class="text-xs text-stone-500">Average</p><p class="text-sm font-medium text-stone-200">{{ metric(data.avg_ms ?? data.latest_ms) }}</p></div>
						<div class="rounded-md border border-stone-900 bg-stone-900/30 p-2"><p class="text-xs text-stone-500">Max</p><p class="text-sm font-medium text-stone-200">{{ metric(data.max_ms) }}</p></div>
					</div>
					<VueApexCharts v-if="data.points.length" type="area" :height="zoomed ? 'calc(90vh - 12rem)' : 260" :options="options" :series="series" />
					<div v-else class="flex h-64 animate-pulse items-center justify-center text-sm text-stone-500">Waiting for samples…</div>
				</div>
			</template>
			<div v-else class="p-4 text-sm text-red-300">The chart artifact did not match schema version {{ artifact.schema_version }}.</div>
		</template>
	</ArtifactViewerShell>
</template>
