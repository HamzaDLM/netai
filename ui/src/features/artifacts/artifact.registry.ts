import { defineAsyncComponent, type Component } from 'vue'

const GenericArtifact = defineAsyncComponent(() => import('./generic/GenericArtifact.vue'))

const artifactRenderers: Record<string, Component> = {
	'network.ping.v1': defineAsyncComponent(() => import('./ping/PingArtifact.vue')),
	'network.traceroute.v1': defineAsyncComponent(() => import('./traceroute/TracerouteArtifact.vue')),
	'network.latency-chart.v1': defineAsyncComponent(() => import('./latency-chart/LatencyChartArtifact.vue')),
	'config.diff.v1': defineAsyncComponent(() => import('./config-diff/ConfigDiffArtifact.vue')),
	'network.topology.v1': defineAsyncComponent(() => import('./topology/TopologyArtifact.vue')),
}

export function resolveArtifactRenderer(kind: string): Component {
	return artifactRenderers[kind] ?? GenericArtifact
}
