<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useGenericStore } from '@/stores/generic.store'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

const genericStore = useGenericStore()
const { codeHighlighter } = storeToRefs(genericStore)

const connectors = ref([
    { id: 'easynet', name: 'Easynet', enabled: true, connected: false },
    { id: 'zabbix', name: 'Zabbix', enabled: true, connected: true },
    { id: 'bitbucket', name: 'Bitbucket', enabled: false, connected: false },
    { id: 'ansible', name: 'Ansible', enabled: false, connected: false },
    { id: 'syslogs', name: 'Syslogs', enabled: false, connected: false },
    { id: 'servicenow', name: 'ServiceNow', enabled: false, connected: false },
])

const appearancePreviewMarkdown = `
\`\`\`ts
type ConnectorStatus = {
    id: string
    enabled: boolean
    connected: boolean
}

const connectors: ConnectorStatus[] = [
    { id: 'easynet', enabled: true, connected: false },
]

const connectedCount = connectors.filter((item) => item.connected).length
console.log(\`Connected: \${connectedCount}\`)
\`\`\`
`

const loadConnectorStatus = async () => {
    // TODO: Replace with backend healthcheck endpoint when available.
    // Example: const data = await api.get('/connectors/health')
}

onMounted(async () => {
    await loadConnectorStatus()
})
</script>

<template>
    <Dialog>
        <DialogTrigger as-child>
            <button
                class="flex items-center gap-2 px-3 py-2 text-sm text-left transition border rounded-md w-min border-stone-800 text-stone-200 hover:border-stone-600 hover:bg-stone-900/60">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                    <path fill="currentColor"
                        d="m9.25 22l-.4-3.2q-.325-.125-.612-.3t-.563-.375L4.7 19.375l-2.75-4.75l2.575-1.95Q4.5 12.5 4.5 12.338v-.675q0-.163.025-.338L1.95 9.375l2.75-4.75l2.975 1.25q.275-.2.575-.375t.6-.3l.4-3.2h5.5l.4 3.2q.325.125.613.3t.562.375l2.975-1.25l2.75 4.75l-2.575 1.95q.025.175.025.338v.674q0 .163-.05.338l2.575 1.95l-2.75 4.75l-2.95-1.25q-.275.2-.575.375t-.6.3l-.4 3.2zM11 20h1.975l.35-2.65q.775-.2 1.438-.587t1.212-.938l2.475 1.025l.975-1.7l-2.15-1.625q.125-.35.175-.737T17.5 12t-.05-.787t-.175-.738l2.15-1.625l-.975-1.7l-2.475 1.05q-.55-.575-1.212-.962t-1.438-.588L13 4h-1.975l-.35 2.65q-.775.2-1.437.588t-1.213.937L5.55 7.15l-.975 1.7l2.15 1.6q-.125.375-.175.75t-.05.8q0 .4.05.775t.175.75l-2.15 1.625l.975 1.7l2.475-1.05q.55.575 1.213.963t1.437.587zm1.05-4.5q1.45 0 2.475-1.025T15.55 12t-1.025-2.475T12.05 8.5q-1.475 0-2.488 1.025T8.55 12t1.013 2.475T12.05 15.5M12 12" />
                </svg>
            </button>
        </DialogTrigger>
        <DialogContent
            class="flex flex-col border-stone-800 bg-stone-950 text-stone-200 w-[820px] max-w-[92vw] h-[620px] max-h-[85vh] overflow-hidden gap-0 p-0">
            <DialogHeader class="px-6 pt-6 pb-4 h-min">
                <DialogTitle>Settings</DialogTitle>
                <DialogDescription class="text-stone-400">
                    Configure your preferences here.
                </DialogDescription>
            </DialogHeader>
            <Tabs default-value="general" class="flex w-full h-full min-h-0 gap-4 px-6 pb-6">
                <TabsList
                    class="flex flex-col items-start justify-start w-40 h-full gap-1 p-2 rounded-md shrink-0 bg-stone-900 text-stone-300">
                    <TabsTrigger value="general" class="justify-start w-full text-sm">General</TabsTrigger>
                    <TabsTrigger value="connectors" class="justify-start w-full text-sm">Connectors</TabsTrigger>
                    <TabsTrigger value="appearance" class="justify-start w-full text-sm">Appearance</TabsTrigger>
                </TabsList>
                <div class="flex-1 min-h-0 overflow-hidden">
                    <TabsContent value="appearance" class="h-full pr-2 space-y-3 overflow-y-auto">
                        <div class="text-sm text-stone-300">Code highlighter</div>
                        <Select v-model="codeHighlighter">
                            <SelectTrigger class="w-full border-stone-700 bg-zinc-900 text-stone-200">
                                <SelectValue placeholder="Select a highlighter" />
                            </SelectTrigger>
                            <SelectContent class="border-stone-700 bg-zinc-900 text-stone-200">
                                <SelectItem value="kanagawa-dragon">Kanagawa Dragon</SelectItem>
                                <SelectItem value="nord">Nord</SelectItem>
                                <SelectItem value="one-dark-pro">One Dark Pro</SelectItem>
                            </SelectContent>
                        </Select>
                        <div class="pt-2 text-sm text-stone-300">Preview (Typescript)</div>
                        <MarkdownRenderer :content="appearancePreviewMarkdown" />
                    </TabsContent>
                    <TabsContent value="general" class="h-full pr-2 overflow-y-auto text-sm text-stone-400">
                        General settings placeholder.
                    </TabsContent>
                    <TabsContent value="connectors" class="h-full pr-2 space-y-3 overflow-y-auto">
                        <div class="text-sm text-stone-300">
                            Enabled connectors and live connection status.
                        </div>
                        <div class="space-y-2">
                            <div v-for="connector in connectors" :key="connector.id"
                                class="flex items-center justify-between px-3 py-2 border rounded-md border-stone-800 bg-zinc-900/30">
                                <div class="text-sm text-stone-200">
                                    {{ connector.name }}
                                </div>
                                <div class="flex items-center gap-2 text-xs">
                                    <span
                                        :class="connector.enabled ? 'border-emerald-700/50 text-emerald-300' : 'border-stone-700 text-stone-400'"
                                        class="rounded-full border px-2 py-0.5">
                                        {{ connector.enabled ? 'Enabled' : 'Disabled' }}
                                    </span>
                                    <span
                                        :class="connector.connected ? 'border-emerald-700/50 text-emerald-300' : 'border-red-700/50 text-red-300'"
                                        class="rounded-full border px-2 py-0.5">
                                        {{ connector.connected ? 'Connected' : 'Not connected' }}
                                    </span>
                                </div>
                            </div>
                        </div>
                        <div class="text-xs text-stone-500">
                            Status data will be loaded from the backend healthcheck endpoint.
                        </div>
                    </TabsContent>
                </div>
            </Tabs>
        </DialogContent>
    </Dialog>
</template>
