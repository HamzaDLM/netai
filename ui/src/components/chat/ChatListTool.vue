<script setup lang="ts">
import { ToolCall } from '@/types/chat.type';
import { computed } from 'vue';
import { ChevronsUpDown } from 'lucide-vue-next'
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from '@/components/ui/collapsible'

const isOpen = ref(false)

const props = defineProps<{
    toolCalls?: ToolCall[]
}>()

const normalizedToolCalls = computed(() => props.toolCalls ?? [])

function safeParse<T>(value: string): T | null {
    try {
        return JSON.parse(value
            .replace(/'/g, '"')
            .replace(/\bFalse\b/g, "false")
            .replace(/\bTrue\b/g, "true")) as T
    } catch {
        return null
    }
}

type ConnectorEnum = 'zabbix' | 'bitbucket'

function connectorColorStyle(connector: ConnectorEnum | string | undefined): string {
    if (!connector) return 'text-zinc-500'
    switch (connector) {
        case 'zabbix':
            return 'text-red-500'
        case 'bitbucket':
            return 'text-blue-400'
        case 'syslog':
            return 'text-yellow-400'
        case 'easynet':
            return 'text-green-400'
        default:
            return 'text-zinc-500'
    }
}
function connectorBorderColorStyle(connector: ConnectorEnum | string | undefined): string {
    if (!connector) return ''
    switch (connector) {
        case 'zabbix':
            return 'border-red-500'
        case 'bitbucket':
            return 'border-blue-400'
        case 'syslog':
            return 'border-yellow-400'
        case 'easynet':
            return 'border-green-400'
        default:
            return 'border-zinc-500'
    }
}

function isBitbucketDiffTool(toolName: string): boolean {
    return toolName === 'bitbucket.get_device_config_diff'
}
</script>

<template>
    <Collapsible v-if="normalizedToolCalls.length > 0" v-model:open="isOpen" class="flex flex-col w-full gap-2 mb-10">
        <CollapsibleTrigger as-child>
            <div class="flex items-center justify-between gap-4 px-4 py-2 rounded-lg cursor-pointer bg-stone-900/50">
                <h4 class="text-sm font-semibold">
                    {{ normalizedToolCalls.length }} tool {{ normalizedToolCalls.length == 1 ? 'call' : 'calls' }} made
                </h4>
                <Button variant="ghost" size="icon" class="size-8">
                    <ChevronsUpDown />
                    <span class="sr-only">Toggle</span>
                </Button>
            </div>
        </CollapsibleTrigger>
        <CollapsibleContent v-for="toolcall of normalizedToolCalls" class="flex flex-col gap-2 border-l-4 rounded-lg"
            :class="connectorBorderColorStyle(toolcall.tool_source)">
            <div class="flex flex-col gap-4 px-4 py-2 font-mono text-sm border-2 rounded-md border-stone-900">
                <!-- Title -->
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-4">
                        <p class="text-lg font-bold uppercase" :class="connectorColorStyle(toolcall.tool_source)">{{
                            toolcall.tool_source }}</p>
                        <p class="px-2 font-semibold text-black rounded bg-stone-300">{{
                            toolcall.tool_name.split(".").slice(1).toString() }}
                        </p>
                    </div>
                    <p v-if="toolcall.latency_ms">{{ toolcall.latency_ms }}ms</p>
                </div>
                <div>
                    <p class="mb-1 ml-4 text-base">Arguments</p>
                    <div class="flex flex-col gap-2 p-2 px-4 border rounded border-stone-900 bg-stone-950">
                        <div v-for="val, key of toolcall.arguments">
                            <span class="text-stone-400">{{ key }}</span>:
                            <span>{{ val }}</span>
                        </div>
                    </div>
                </div>
                <div>
                    <p class="mb-1 ml-4 text-base">Results</p>
                    <div class="flex flex-col gap-2 p-2 px-4 border rounded border-stone-900 bg-stone-950">
                        <p v-if="isBitbucketDiffTool(toolcall.tool_name)" class="text-stone-400">
                            Diff rendered in assistant response.
                        </p>
                        <div v-else v-for="val, key of safeParse(toolcall.result?.['value'])">
                            <span class="text-stone-400">{{ key }}</span>:
                            <span>{{ val }}</span>
                        </div>
                    </div>
                </div>
            </div>
        </CollapsibleContent>
    </Collapsible>
</template>
