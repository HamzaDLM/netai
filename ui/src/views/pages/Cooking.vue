<script setup lang="ts">
import { VNetworkGraph } from "v-network-graph"
import "v-network-graph/lib/style.css"
import { reactive, ref } from "vue"
import { Nodes, Edges, Layouts, Layers, defineConfigs } from "v-network-graph"
import * as vNG from "v-network-graph"

const nodes = reactive<Nodes>({
    node1: { name: "Node 1", active: true },
    node2: { name: "Node 2", active: false },
    node3: { name: "Node 3", active: true },
    node4: { name: "Node 4", active: false },
})

const edges = ref<Edges>({
    edge1: { source: "node1", target: "node2" },
    edge2: { source: "node2", target: "node3" },
    edge3: { source: "node3", target: "node4" },
})

const layouts = ref<Layouts>({
    nodes: {
        node1: { x: 0, y: 0 },
        node2: { x: 80, y: 80 },
        node3: { x: 160, y: 0 },
        node4: { x: 240, y: 80 },
    },
})

const configs = defineConfigs({
    node: {
        normal: {
            type: "rect",
            width: 32,
            height: 32,
            borderRadius: 6,
            color: "#ffffff",
            strokeWidth: 1,
            strokeColor: "#888888",
        },
        hover: {
            color: "#eeeeee",
        },
    },
    edge: {
        normal: {
            width: 1,
            color: "#666666",
        },
        hover: {
            color: "#666666",
        },
    },
})

// additional layers definition
const layers = ref<Layers>({
    // {layername}: {position}
    badge: "nodes",
})

const eventHandlers: vNG.EventHandlers = {
    "node:click": ({ node }) => {
        // toggle
        nodes[node].active = !nodes[node].active
    },
}
</script>

<template>
    <div class="w-screen h-screen p-10">
        <p class="text-xl font-bold">Cooking</p>
        <div class="w-full h-full border border-zinc-800">
            <v-network-graph class="w-full text-white bg-zinc-100" :nodes="nodes" :edges="edges" :layouts="layouts"
                :configs="configs" :layers="layers" :event-handlers="eventHandlers">
                <!-- Additional layer -->
                <template #badge="{ scale }">
                    <!--
                        If the `view.scalingObjects` config is `false`(default),
                        scaling does not change the display size of the nodes/edges.
                        The `scale` is passed as a scaling factor to implement
                        this behavior. 
                    -->
                    <button v-for="(pos, node) in layouts.nodes" :key="node"
                        :class="nodes[node].active ? 'text-red-400' : 'text-green-400'" :cx="pos.x + 9 * scale"
                        :cy="pos.y - 9 * scale" :r="4 * scale">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-10 h-10"
                            viewBox="0 0 24 24"><!-- Icon from Material Design Icons by Pictogrammers - https://github.com/Templarian/MaterialDesign/blob/master/LICENSE -->
                            <path fill="currentColor"
                                d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10s10-4.5 10-10S17.5 2 12 2m0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8s8 3.58 8 8s-3.58 8-8 8m1-7v3h2l-3 3l-3-3h2v-3m-6 0h3v2l3-3l-3-3v2H5m6 0V8H9l3-3l3 3h-2v3m6 0h-3V9l-3 3l3 3v-2h3" />
                        </svg>
                    </button>
                    <!-- <circle v-for="(pos, node) in layouts.nodes" :key="node" :cx="pos.x + 9 * scale"
                        :cy="pos.y - 9 * scale" :r="4 * scale" :fill="nodes[node].active ? '#00cc00' : '#ff5555'"
                        style="pointer-events: none" /> -->
                </template>
            </v-network-graph>
        </div>
    </div>
</template>