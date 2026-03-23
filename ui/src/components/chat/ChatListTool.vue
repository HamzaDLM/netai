<script setup lang="ts">
import { computed } from 'vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

type Evidence = {
    id?: number
    source_type?: string
    source_ref?: string
    content_snippet?: string
    score?: number
    timestamp?: string
}

type ToolCall = {
    id?: number
    tool_name?: string
    tool_source?: string
    arguments?: unknown
    result?: unknown
    latency_ms?: number
    evidence?: Evidence[]
    evidence_items?: Evidence[]
}

const props = defineProps<{
    toolCalls?: ToolCall[]
}>()

const normalizedToolCalls = computed(() => props.toolCalls ?? [])

const distinctEvidence = computed(() => {
    const all = normalizedToolCalls.value.flatMap((tool) => tool.evidence_items ?? tool.evidence ?? [])
    const seen = new Set<string>()
    const unique: Evidence[] = []

    for (const evidence of all) {
        const key = `${evidence.source_type ?? ''}|${evidence.source_ref ?? ''}|${evidence.content_snippet ?? ''}`
        if (seen.has(key)) continue
        seen.add(key)
        unique.push(evidence)
    }

    return unique
})

const toolSources = computed(() => {
    const values = normalizedToolCalls.value.map(tool => {
        if (tool.tool_source && tool.tool_source.trim().length > 0) {
            return tool.tool_source.trim()
        }
        if (tool.tool_name && tool.tool_name.includes('.')) {
            return tool.tool_name.split('.', 1)[0]
        }
        return 'Unnamed'
    })
    return [...new Set(values)]
})

function toPrettyJson(value: unknown): string {
    if (value == null) return 'null'
    if (typeof value === 'string') return value
    try {
        return JSON.stringify(value, null, 2)
    } catch {
        return String(value)
    }
}
</script>

<template>
    <Collapsible v-if="normalizedToolCalls.length > 0" class="mb-4 border rounded-lg border-stone-700 bg-stone-900/40">
        <div class="flex items-center justify-between px-3 py-2 border-b border-stone-800">
            <div class="flex items-center gap-2">
                <span class="text-xs font-semibold tracking-wide text-stone-300">Tool Activity</span>
                <span v-for="source in toolSources" :key="source"
                    class="px-2 py-0.5 text-[11px] rounded border border-yellow-500/40 bg-yellow-500/15 text-yellow-300">
                    {{ source }}
                </span>
            </div>
            <CollapsibleTrigger
                class="px-2 py-1 text-xs border rounded border-stone-700 text-stone-300 hover:bg-stone-800/70">
                Toggle details
            </CollapsibleTrigger>
        </div>

        <CollapsibleContent>
            <div class="grid gap-3 p-3">
                <Collapsible class="border rounded border-stone-800 bg-stone-950/30">
                    <div class="flex items-center justify-between px-3 py-2">
                        <p class="text-xs font-medium text-stone-200">Tool calls ({{ normalizedToolCalls.length }})</p>
                        <CollapsibleTrigger class="text-xs text-stone-400 hover:text-stone-200">Show/Hide
                        </CollapsibleTrigger>
                    </div>
                    <CollapsibleContent>
                        <div class="px-3 pb-3 space-y-3">
                            <div v-for="(tool, index) in normalizedToolCalls" :key="`tool-${tool.id ?? index}`"
                                class="p-2 border rounded border-stone-800">
                                <div class="flex items-center justify-between mb-2">
                                    <p class="text-xs font-semibold text-stone-100">{{ tool.tool_name || 'Unnamed' }}
                                    </p>
                                    <p v-if="tool.latency_ms != null" class="text-[11px] text-stone-400">{{
                                        tool.latency_ms }} ms</p>
                                </div>
                                <p class="mb-1 text-[11px] text-stone-400">Arguments</p>
                                <pre
                                    class="p-2 mb-2 overflow-x-auto text-xs border rounded border-stone-800 bg-stone-950/60 text-stone-200">
                                    {{ toPrettyJson(tool.arguments) }}
                                </pre>
                                <p class="mb-1 text-[11px] text-stone-400">Result</p>
                                <pre
                                    class="p-2 overflow-x-auto text-xs border rounded border-stone-800 bg-stone-950/60 text-stone-200">
                                    {{ toPrettyJson(tool.result) }}
                                </pre>
                            </div>
                        </div>
                    </CollapsibleContent>
                </Collapsible>

                <Collapsible class="border rounded border-stone-800 bg-stone-950/30">
                    <div class="flex items-center justify-between px-3 py-2">
                        <p class="text-xs font-medium text-stone-200">Distinct evidence ({{ distinctEvidence.length }})</p>
                        <CollapsibleTrigger class="text-xs text-stone-400 hover:text-stone-200">Show/Hide
                        </CollapsibleTrigger>
                    </div>
                    <CollapsibleContent>
                        <div v-if="distinctEvidence.length === 0" class="px-3 pb-3 text-xs text-stone-400">
                            No evidence captured.
                        </div>
                        <div v-else class="px-3 pb-3 space-y-3">
                            <div v-for="(evidence, index) in distinctEvidence" :key="`ev-${evidence.id ?? index}`"
                                class="p-2 border rounded border-stone-800">
                                <div class="flex items-center gap-2 mb-1 text-[11px] text-stone-400">
                                    <span>{{ evidence.source_type || 'tool_result' }}</span>
                                    <span v-if="evidence.source_ref">• {{ evidence.source_ref }}</span>
                                    <span v-if="evidence.score != null">• score {{ evidence.score }}</span>
                                </div>
                                <p class="text-xs whitespace-pre-wrap text-stone-200">{{ evidence.content_snippet || '-' }}</p>
                            </div>
                        </div>
                    </CollapsibleContent>
                </Collapsible>
            </div>
        </CollapsibleContent>
    </Collapsible>
</template>
