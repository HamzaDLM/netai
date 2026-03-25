<script setup lang="ts">
import { VNetworkGraph } from "v-network-graph"
import "v-network-graph/lib/style.css"
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { Nodes, Edges, Layouts, defineConfigs } from "v-network-graph"

interface TopologyDevice {
    hostname: string
    mgmt_ip: string
    site: string
    role: string
    status: string
}

interface TopologyLink {
    link_id: string
    a_device: string
    a_interface: string
    b_device: string
    b_interface: string
    status: string
    bandwidth_mbps: number
    metric: number
    last_change: string
}

interface TopologyPayload {
    scope: string
    device_count: number
    link_count: number
    link_status_counts?: Record<string, number>
    devices: TopologyDevice[]
    links: TopologyLink[]
}

type NodeStatus = "up" | "down" | "degraded" | "maintenance"
type EdgeStatus = "up" | "down" | "degraded" | "maintenance"

const props = defineProps<{
    topology?: TopologyPayload | Record<string, unknown> | null
}>()
const isZoomed = ref(false)

const topology = computed<TopologyPayload | null>(() => {
    const raw = props.topology
    if (!raw || typeof raw !== "object") return null
    const candidate = raw as Partial<TopologyPayload>
    if (!Array.isArray(candidate.devices) || !Array.isArray(candidate.links)) {
        return null
    }
    return {
        scope: String(candidate.scope ?? "all_sites"),
        device_count: Number(candidate.device_count ?? candidate.devices.length ?? 0),
        link_count: Number(candidate.link_count ?? candidate.links.length ?? 0),
        link_status_counts: candidate.link_status_counts ?? {},
        devices: candidate.devices as TopologyDevice[],
        links: candidate.links as TopologyLink[],
    }
})

const nodes = computed<Nodes>(() => {
    const data = topology.value
    if (!data) return {}

    const mapped: Nodes = {}
    for (const device of data.devices) {
        mapped[device.hostname] = {
            name: device.hostname,
            site: device.site,
            role: device.role,
            status: String(device.status || "up").toLowerCase() as NodeStatus,
        }
    }
    return mapped
})

const edges = computed<Edges>(() => {
    const data = topology.value
    if (!data) return {}

    const mapped: Edges = {}
    for (const link of data.links) {
        mapped[link.link_id] = {
            source: link.a_device,
            target: link.b_device,
            status: String(link.status || "up").toLowerCase() as EdgeStatus,
            label: `${link.a_interface} ↔ ${link.b_interface}`,
        }
    }
    return mapped
})

const layouts = computed<Layouts>(() => {
    const data = topology.value
    if (!data) return { nodes: {} }

    const bySite = new Map<string, TopologyDevice[]>()
    for (const device of data.devices) {
        const bucket = bySite.get(device.site) ?? []
        bucket.push(device)
        bySite.set(device.site, bucket)
    }

    const roleOrder: Record<string, number> = {
        "core-router": 0,
        "distribution-router": 1,
        spine: 2,
        leaf: 3,
        "edge-firewall": 4,
        "core-switch": 5,
        "vpn-gateway": 6,
        "wireless-controller": 7,
    }
    const positions: Layouts["nodes"] = {}

    const sites = [...bySite.keys()].sort()
    sites.forEach((site, siteIndex) => {
        const siteDevices = (bySite.get(site) ?? []).sort((a, b) => {
            const aRole = roleOrder[a.role] ?? 99
            const bRole = roleOrder[b.role] ?? 99
            if (aRole !== bRole) return aRole - bRole
            return a.hostname.localeCompare(b.hostname)
        })

        const laneCounters: Record<number, number> = {}
        for (const device of siteDevices) {
            const lane = roleOrder[device.role] ?? 99
            laneCounters[lane] = (laneCounters[lane] ?? 0) + 1
            const laneIndex = laneCounters[lane] - 1
            positions[device.hostname] = {
                x: siteIndex * 460 + laneIndex * 180 + 100,
                y: lane * 90 + 80,
            }
        }
    })

    return { nodes: positions }
})

function nodeStatusColor(status: NodeStatus): string {
    switch (status) {
        case "up":
            return "#16a34a"
        case "degraded":
            return "#f59e0b"
        case "down":
            return "#ef4444"
        case "maintenance":
            return "#a3a3a3"
        default:
            return "#52525b"
    }
}

function edgeStatusColor(status: EdgeStatus): string {
    switch (status) {
        case "up":
            return "#22c55e"
        case "degraded":
            return "#f59e0b"
        case "down":
            return "#ef4444"
        case "maintenance":
            return "#9ca3af"
        default:
            return "#6b7280"
    }
}

function openZoom(): void {
    isZoomed.value = true
}

function closeZoom(): void {
    isZoomed.value = false
}

function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape" && isZoomed.value) {
        closeZoom()
    }
}

onMounted(() => {
    window.addEventListener("keydown", onKeydown)
})

onBeforeUnmount(() => {
    window.removeEventListener("keydown", onKeydown)
})

const configs = defineConfigs({
    view: {
        panEnabled: true,
        zoomEnabled: true,
        minZoomLevel: 0.1,
        maxZoomLevel: 3,
        fit: true,
    },
    node: {
        normal: {
            type: "rect",
            width: 30,
            height: 30,
            borderRadius: 6,
            color: (node) => {
                const status = (nodes.value[String(node)]?.status ?? "up") as NodeStatus
                return nodeStatusColor(status)
            },
            strokeWidth: 1,
            strokeColor: "#18181b",
        },
        hover: {
            color: "#eeeeee",
        },
        label: {
            color: "#fff",
            fontSize: 12,
        }
    },
    edge: {
        normal: {
            width: 2.5,
            color: (edge) => {
                const status = (edges.value[String(edge)]?.status ?? "up") as EdgeStatus
                return edgeStatusColor(status)
            },
        },
        hover: {
            color: "#e5e7eb",
        },
        marker: {
            source: {
                type: "none",
            },
            target: {
                type: "none",
            },
        },
    },
})
</script>

<template>
    <div class="flex flex-col gap-4 py-4">
        <div v-if="!topology || topology.device_count === 0"
            class="p-4 text-sm border rounded-md border-stone-900 text-stone-400 bg-stone-950">
            No topology available.
        </div>
        <div class="overflow-hidden border rounded-md border-stone-900">
            <div
                class="flex items-center justify-between w-full gap-2 px-4 py-2 text-sm font-semibold text-center border-b bg-stone-900/40 border-stone-900 text-stone-300">
                <div></div>
                <div class="flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-red-500" viewBox="0 0 24 24">
                        <path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"
                            stroke-width="2"
                            d="M10 19a2 2 0 1 0-4 0a2 2 0 0 0 4 0m8-14a2 2 0 1 0-4 0a2 2 0 0 0 4 0m-8 0a2 2 0 1 0-4 0a2 2 0 0 0 4 0m-4 7a2 2 0 1 0-4 0a2 2 0 0 0 4 0m12 7a2 2 0 1 0-4 0a2 2 0 0 0 4 0m-4-7a2 2 0 1 0-4 0a2 2 0 0 0 4 0m8 0a2 2 0 1 0-4 0a2 2 0 0 0 4 0M6 12h4m4 0h4m-3-5l-2 3M9 7l2 3m0 4l-2 3m4-3l2 3" />
                    </svg>
                    TOPOLOGY MAPPER
                </div>
                <button class="p-1 text-xs" @click="openZoom">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-stone-400 hover:text-stone-200"
                        viewBox="0 0 24 24">
                        <path fill="currentColor"
                            d="M6.4 19H8q.425 0 .713.288T9 20t-.288.713T8 21H4q-.425 0-.712-.288T3 20v-4q0-.425.288-.712T4 15t.713.288T5 16v1.6l2.4-2.4q.275-.275.7-.275t.7.275t.275.7t-.275.7zm11.2 0l-2.4-2.4q-.275-.275-.275-.7t.275-.7t.7-.275t.7.275l2.4 2.4V16q0-.425.288-.712T20 15t.713.288T21 16v4q0 .425-.288.713T20 21h-4q-.425 0-.712-.288T15 20t.288-.712T16 19zM5 6.4V8q0 .425-.288.713T4 9t-.712-.288T3 8V4q0-.425.288-.712T4 3h4q.425 0 .713.288T9 4t-.288.713T8 5H6.4l2.4 2.4q.275.275.275.7t-.275.7t-.7.275t-.7-.275zm14 0l-2.4 2.4q-.275.275-.7.275t-.7-.275t-.275-.7t.275-.7L17.6 5H16q-.425 0-.712-.287T15 4t.288-.712T16 3h4q.425 0 .713.288T21 4v4q0 .425-.288.713T20 9t-.712-.288T19 8z" />
                    </svg>
                </button>
            </div>
            <div v-if="topology"
                class="grid grid-cols-3 gap-2 px-4 py-2 text-xs border-b bg-stone-950 border-stone-900 text-stone-300">
                <p>Scope: <span class="font-semibold">{{ topology.scope }}</span></p>
                <p>Devices: <span class="font-semibold">{{ topology.device_count }}</span></p>
                <p>Links: <span class="font-semibold">{{ topology.link_count }}</span></p>
            </div>
            <div class="w-full h-full">
                <v-network-graph class="w-full h-[400px] text-white bg-stone-950" :nodes="nodes" :edges="edges"
                    :layouts="layouts" :configs="configs" />
            </div>
        </div>

        <Teleport to="body">
            <div v-if="isZoomed" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
                <div class="w-[90vw] h-[90vh] overflow-hidden border rounded-lg border-stone-800 bg-stone-950">
                    <div
                        class="flex items-center justify-between w-full gap-2 px-4 py-2 text-sm font-semibold border-b bg-stone-900/50 border-stone-800 text-stone-200">
                        <div class="flex items-center gap-2">
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-red-500" viewBox="0 0 24 24">
                                <path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"
                                    stroke-width="2"
                                    d="M10 19a2 2 0 1 0-4 0a2 2 0 0 0 4 0m8-14a2 2 0 1 0-4 0a2 2 0 0 0 4 0m-8 0a2 2 0 1 0-4 0a2 2 0 0 0 4 0m-4 7a2 2 0 1 0-4 0a2 2 0 0 0 4 0m12 7a2 2 0 1 0-4 0a2 2 0 0 0 4 0m-4-7a2 2 0 1 0-4 0a2 2 0 0 0 4 0m8 0a2 2 0 1 0-4 0a2 2 0 0 0 4 0M6 12h4m4 0h4m-3-5l-2 3M9 7l2 3m0 4l-2 3m4-3l2 3" />
                            </svg>
                            TOPOLOGY MAPPER
                        </div>
                        <button
                            class="px-3 py-1 text-xs border rounded border-stone-700 bg-stone-950 hover:bg-stone-900"
                            @click="closeZoom">
                            Close
                        </button>
                    </div>
                    <div v-if="topology"
                        class="grid grid-cols-3 gap-2 px-4 py-2 text-xs border-b bg-stone-950 border-stone-800 text-stone-300">
                        <p>Scope: <span class="font-semibold">{{ topology.scope }}</span></p>
                        <p>Devices: <span class="font-semibold">{{ topology.device_count }}</span></p>
                        <p>Links: <span class="font-semibold">{{ topology.link_count }}</span></p>
                    </div>
                    <v-network-graph class="w-full h-[calc(90vh-96px)] text-white bg-stone-950" :nodes="nodes"
                        :edges="edges" :layouts="layouts" :configs="configs" />
                </div>
            </div>
        </Teleport>
    </div>
</template>
