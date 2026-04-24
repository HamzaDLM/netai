<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { toast } from '@/components/ui/toast'
import skillsService from '@/services/skills.service'
import type { ToolCatalogAgent, ToolCatalogTool } from '@/types/skill.type'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog'

type ConnectorDefinition = {
    id: string
    name: string
    enabled: boolean
    connected: boolean
    toolAgentKeys: string[]
    description: string
}

type ConnectorWithTools = ConnectorDefinition & {
    tools: ToolCatalogTool[]
}

const connectorsLoading = ref(false)
const toolCatalog = ref<ToolCatalogAgent[]>([])

const connectors: ConnectorDefinition[] = [
    {
        id: 'easynet',
        name: 'Easynet',
        enabled: true,
        connected: false,
        toolAgentKeys: ['datamodel'],
        description: 'Internal topology and infrastructure context available through the data model.',
    },
    {
        id: 'zabbix',
        name: 'Zabbix',
        enabled: true,
        connected: true,
        toolAgentKeys: ['zabbix'],
        description: 'Monitoring, telemetry, events, and diagnostics from Zabbix.',
    },
    {
        id: 'bitbucket',
        name: 'Bitbucket',
        enabled: false,
        connected: false,
        toolAgentKeys: ['bitbucket'],
        description: 'Repository, config history, and change provenance for network assets.',
    },
    {
        id: 'ansible',
        name: 'Ansible',
        enabled: false,
        connected: false,
        toolAgentKeys: [],
        description: 'Automation connector reserved for future operational tooling.',
    },
    {
        id: 'syslogs',
        name: 'Syslogs',
        enabled: false,
        connected: false,
        toolAgentKeys: ['syslog'],
        description: 'Log evidence and raw event retrieval for troubleshooting workflows.',
    },
    {
        id: 'servicenow',
        name: 'ServiceNow',
        enabled: false,
        connected: false,
        toolAgentKeys: ['servicenow'],
        description: 'Incidents, CMDB records, changes, and operational process context.',
    },
]

const loadToolCatalog = async () => {
    connectorsLoading.value = true
    try {
        const response = await skillsService.getToolCatalog()
        toolCatalog.value = response.data
    } catch {
        toast({ title: 'Unable to load connector tools', variant: 'destructive' })
    } finally {
        connectorsLoading.value = false
    }
}

const connectorCards = computed<ConnectorWithTools[]>(() => {
    const catalogByKey = new Map(toolCatalog.value.map(agent => [agent.agent_key, agent]))

    return connectors.map(connector => ({
        ...connector,
        tools: connector.toolAgentKeys.flatMap(agentKey => catalogByKey.get(agentKey)?.tools ?? []),
    }))
})

const availableToolCount = computed(() =>
    connectorCards.value.reduce((count, connector) => count + connector.tools.length, 0)
)

onMounted(async () => {
    await loadToolCatalog()
})
</script>

<template>
    <div class="flex flex-col h-full min-h-0">
        <div class="flex-1 min-h-0 overflow-y-auto">
            <div class="flex flex-col w-full h-full gap-8 px-10 py-10 mx-auto max-w-7xl lg:px-16">
                <div class="space-y-2">
                    <p class="text-3xl font-semibold text-stone-200">Connectors</p>
                    <p class="max-w-2xl text-sm text-stone-400">
                        Read-only overview of the connectors available in NetAI and the tools each one can expose.
                    </p>
                </div>

                <div class="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(18rem,0.8fr)]">
                    <div class="p-6 border rounded-2xl border-stone-800 bg-zinc-900/30">
                        <div class="flex items-center justify-between gap-3">
                            <div>
                                <p class="text-lg font-semibold text-stone-300">Available Connectors</p>
                                <p class="mt-1 text-sm text-stone-500">
                                    Status and tool coverage for the integrations currently surfaced in the chat
                                    workspace.
                                </p>
                            </div>
                            <p class="text-xs uppercase tracking-[0.24em] text-stone-500">
                                {{ connectorCards.length }} total
                            </p>
                        </div>
                    </div>

                    <div class="p-6 border rounded-2xl border-stone-800 bg-zinc-900/20">
                        <p class="text-sm font-medium text-stone-300">Tool Coverage</p>
                        <p class="mt-2 text-sm leading-6 text-stone-500">
                            {{ availableToolCount }} tool{{ availableToolCount === 1 ? '' : 's' }} are currently mapped
                            to these connectors.
                        </p>
                    </div>
                </div>

                <div v-if="connectorsLoading" class="text-sm text-stone-500">
                    Loading connectors...
                </div>
                <div v-else class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    <Dialog v-for="connector in connectorCards" :key="connector.id">
                        <DialogTrigger as-child>
                            <button type="button"
                                class="flex min-h-[18rem] flex-col rounded-xl border border-stone-800 bg-stone-950/50 p-5 text-left transition hover:border-stone-600 hover:bg-stone-900/60">
                                <div class="flex items-start justify-between gap-3">
                                    <p class="text-base font-medium text-stone-200">{{ connector.name }}</p>
                                    <div class="flex items-end gap-2 text-[11px] uppercase tracking-wide">
                                        <span class="rounded-full border px-2 py-0.5" :class="connector.enabled
                                            ? 'border-emerald-700/50 text-emerald-300'
                                            : 'border-stone-700 text-stone-400'">
                                            {{ connector.enabled ? 'Enabled' : 'Disabled' }}
                                        </span>
                                        <span class="whitespace-nowrap rounded-full border px-2 py-0.5" :class="connector.connected
                                            ? 'border-emerald-700/50 text-emerald-300'
                                            : 'border-red-700/50 text-red-300'">
                                            {{ connector.connected ? 'Connected' : 'Not Connected' }}
                                        </span>
                                    </div>
                                </div>
                                <p class="pt-4 text-sm text-stone-400">
                                    {{ connector.description }}
                                </p>

                                <div
                                    class="flex items-center justify-between pt-5 mt-auto border-t border-stone-800/80">
                                    <p class="text-sm text-stone-500">
                                        Click to view tools
                                    </p>
                                    <p class="text-xs uppercase tracking-[0.24em] text-stone-500">
                                        {{ connector.tools.length }} tool{{ connector.tools.length === 1 ? '' : 's' }}
                                    </p>
                                </div>
                            </button>
                        </DialogTrigger>

                        <DialogContent
                            class="flex h-[80vh] max-h-[80vh] w-[min(96vw,56rem)] flex-col overflow-hidden border-stone-800 bg-stone-950 text-stone-200 sm:max-w-none">
                            <DialogHeader>
                                <DialogTitle>{{ connector.name }}</DialogTitle>
                                <DialogDescription class="text-stone-400">
                                    {{ connector.description }}
                                </DialogDescription>
                            </DialogHeader>

                            <div class="flex-1 min-h-0 overflow-y-auto pr-1">
                                <div class="flex flex-wrap gap-2 pt-1 text-[11px] uppercase tracking-wide">
                                    <span class="rounded-full border px-2 py-0.5" :class="connector.enabled
                                        ? 'border-emerald-700/50 text-emerald-300'
                                        : 'border-stone-700 text-stone-400'">
                                        {{ connector.enabled ? 'Enabled' : 'Disabled' }}
                                    </span>
                                    <span class="rounded-full border px-2 py-0.5" :class="connector.connected
                                        ? 'border-emerald-700/50 text-emerald-300'
                                        : 'border-red-700/50 text-red-300'">
                                        {{ connector.connected ? 'Connected' : 'Not Connected' }}
                                    </span>
                                </div>

                                <div v-if="connector.tools.length === 0" class="py-6 text-sm text-stone-500">
                                    No tools are exposed for this connector yet.
                                </div>

                                <div v-else class="grid gap-3 py-2 md:grid-cols-2 xl:grid-cols-3">
                                    <div v-for="tool in connector.tools" :key="`${connector.id}-${tool.python_name}`"
                                        class="px-3 py-3 border rounded-lg border-stone-800 bg-black/20">
                                        <p class="text-sm font-medium text-stone-200">
                                            {{ tool.runtime_name || tool.python_name }}
                                        </p>
                                        <p class="mt-1 text-xs leading-5 text-stone-500">
                                            {{ tool.summary || 'No description available.' }}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </DialogContent>
                    </Dialog>
                </div>
            </div>
        </div>
    </div>
</template>
