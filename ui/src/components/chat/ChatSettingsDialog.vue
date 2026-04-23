<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
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
import skillsService from '@/services/skills.service'
import type { Skill, ToolCatalogAgent } from '@/types/skill.type'
import { toast } from '@/components/ui/toast'

const genericStore = useGenericStore()
const {
    codeHighlighter,
    uiVersion,
    uiGitSha,
    backendVersion,
    backendGitSha,
    backendVersionStatus,
} = storeToRefs(genericStore)

const connectors = ref([
    { id: 'easynet', name: 'Easynet', enabled: true, connected: false },
    { id: 'zabbix', name: 'Zabbix', enabled: true, connected: true },
    { id: 'bitbucket', name: 'Bitbucket', enabled: false, connected: false },
    { id: 'ansible', name: 'Ansible', enabled: false, connected: false },
    { id: 'syslogs', name: 'Syslogs', enabled: false, connected: false },
    { id: 'servicenow', name: 'ServiceNow', enabled: false, connected: false },
])

const skills = ref<Skill[]>([])
const toolCatalog = ref<ToolCatalogAgent[]>([])
const skillsLoading = ref(false)
const skillsBusy = ref(false)

const newSkillName = ref('')
const newSkillInstructions = ref('')
const newSkillEnabled = ref(true)

const editingSkillId = ref<number | null>(null)
const editSkillName = ref('')
const editSkillInstructions = ref('')

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

const loadSkillsData = async () => {
    skillsLoading.value = true
    try {
        const response = await skillsService.getBootstrap()
        skills.value = response.data.skills
        toolCatalog.value = response.data.catalog
    } catch {
        toast({ title: 'Unable to load skills data', variant: 'destructive' })
    } finally {
        skillsLoading.value = false
    }
}

const createSkill = async () => {
    const name = newSkillName.value.trim()
    const instructions = newSkillInstructions.value.trim()
    if (!name || !instructions) {
        toast({ title: 'Name and instructions are required', variant: 'destructive' })
        return
    }

    skillsBusy.value = true
    try {
        const response = await skillsService.createSkill({
            name,
            instructions,
            enabled: newSkillEnabled.value,
        })
        skills.value.push(response.data)
        newSkillName.value = ''
        newSkillInstructions.value = ''
        newSkillEnabled.value = true
    } catch (error: any) {
        const detail = String(error?.response?.data?.detail ?? '')
        if (detail === 'skill_name_already_exists') {
            toast({ title: 'A skill with this name already exists', variant: 'destructive' })
            return
        }
        toast({ title: 'Unable to create skill', variant: 'destructive' })
    } finally {
        skillsBusy.value = false
    }
}

const startEditSkill = (skill: Skill) => {
    editingSkillId.value = skill.id
    editSkillName.value = skill.name
    editSkillInstructions.value = skill.instructions
}

const cancelEditSkill = () => {
    editingSkillId.value = null
    editSkillName.value = ''
    editSkillInstructions.value = ''
}

const saveEditSkill = async (skill: Skill) => {
    const name = editSkillName.value.trim()
    const instructions = editSkillInstructions.value.trim()
    if (!name || !instructions) {
        toast({ title: 'Name and instructions are required', variant: 'destructive' })
        return
    }

    skillsBusy.value = true
    try {
        const response = await skillsService.updateSkill(skill.id, {
            name,
            instructions,
        })
        const idx = skills.value.findIndex(item => item.id === skill.id)
        if (idx !== -1) skills.value[idx] = response.data
        cancelEditSkill()
    } catch (error: any) {
        const detail = String(error?.response?.data?.detail ?? '')
        if (detail === 'skill_name_already_exists') {
            toast({ title: 'A skill with this name already exists', variant: 'destructive' })
            return
        }
        toast({ title: 'Unable to update skill', variant: 'destructive' })
    } finally {
        skillsBusy.value = false
    }
}

const toggleSkill = async (skill: Skill) => {
    skillsBusy.value = true
    const previous = skill.enabled
    skill.enabled = !skill.enabled
    try {
        const response = await skillsService.toggleSkill(skill.id, skill.enabled)
        const idx = skills.value.findIndex(item => item.id === skill.id)
        if (idx !== -1) skills.value[idx] = response.data
    } catch {
        skill.enabled = previous
        toast({ title: 'Unable to toggle skill', variant: 'destructive' })
    } finally {
        skillsBusy.value = false
    }
}

const removeSkill = async (skillId: number) => {
    skillsBusy.value = true
    try {
        await skillsService.deleteSkill(skillId)
        skills.value = skills.value.filter(skill => skill.id !== skillId)
        if (editingSkillId.value === skillId) cancelEditSkill()
    } catch {
        toast({ title: 'Unable to delete skill', variant: 'destructive' })
    } finally {
        skillsBusy.value = false
    }
}

const backendStatusLabel = computed(() => {
    if (backendVersionStatus.value === 'loading') return 'Refreshing...'
    if (backendVersionStatus.value === 'error') return 'Last check failed'
    if (backendVersionStatus.value === 'ready') return 'Up to date'
    return 'Not checked yet'
})

onMounted(async () => {
    await genericStore.ensureBackendVersion()
    await loadConnectorStatus()
    await loadSkillsData()
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
            class="flex flex-col border-stone-800 bg-stone-950 text-stone-200 w-[70vw] max-w-[92vw] h-[70vh] max-h-[85vh] overflow-hidden gap-0 p-0">
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
                    <TabsTrigger value="skills" class="justify-start w-full text-sm">Skills</TabsTrigger>
                    <TabsTrigger value="appearance" class="justify-start w-full text-sm">Appearance</TabsTrigger>
                    <TabsTrigger value="about" class="justify-start w-full text-sm">About</TabsTrigger>
                </TabsList>
                <div class="flex-1 min-h-0 overflow-hidden">
                    <TabsContent value="general" class="h-full pr-2 overflow-y-auto text-sm text-stone-400">
                        <div>General</div>
                    </TabsContent>

                    <TabsContent value="connectors" class="h-full pr-2 space-y-3 overflow-y-auto">
                        <div class="text-sm text-stone-300">Enabled connectors and live connection status.</div>
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

                    <TabsContent value="skills" class="h-full pr-2 space-y-4 overflow-y-auto">
                        <div class="text-sm text-stone-300">
                            Create behavior skills and toggle them on/off before running questions.
                        </div>

                        <div class="grid gap-2 p-3 border rounded-md border-stone-800 bg-zinc-900/30">
                            <p class="text-xs uppercase tracking-wide text-stone-400">Create skill</p>
                            <input v-model="newSkillName" type="text" placeholder="Skill name"
                                class="w-full px-3 py-2 text-sm border rounded-md outline-none bg-black/30 border-stone-900 text-stone-200 placeholder:text-stone-500 focus:border-stone-800" />
                            <textarea v-model="newSkillInstructions" rows="4"
                                placeholder="Example: Always start by asking datamodel for device + neighbor context before any root-cause analysis."
                                class="w-full px-3 py-2 text-sm border rounded-md outline-none resize-y bg-black/30 border-stone-900 text-stone-200 placeholder:text-stone-500 focus:border-stone-800" />
                            <label class="flex items-center gap-2 text-xs text-stone-400">
                                <input v-model="newSkillEnabled" type="checkbox" class="accent-red-500" />
                                Enabled by default
                            </label>
                            <div class="flex justify-end">
                                <button @click="createSkill" :disabled="skillsBusy"
                                    class="px-3 py-1.5 text-sm border rounded-md border-stone-700 bg-stone-800 text-stone-200 hover:bg-stone-700 disabled:opacity-50">
                                    Add skill
                                </button>
                            </div>
                        </div>

                        <div class="space-y-2">
                            <p class="text-xs uppercase tracking-wide text-stone-400">Your skills</p>
                            <div v-if="skillsLoading" class="text-sm text-stone-500">Loading skills...</div>
                            <div v-else-if="skills.length === 0" class="text-sm text-stone-500">No skills yet.</div>
                            <div v-else v-for="skill in skills" :key="skill.id"
                                class="grid gap-2 p-3 border rounded-md border-stone-800 bg-zinc-900/30">
                                <div class="flex items-center justify-between gap-2">
                                    <p class="font-medium text-stone-200">{{ skill.name }}</p>
                                    <label class="flex items-center gap-2 text-xs text-stone-400">
                                        <input :checked="skill.enabled" @change="toggleSkill(skill)" :disabled="skillsBusy"
                                            type="checkbox" class="accent-red-500" />
                                        {{ skill.enabled ? 'Enabled' : 'Disabled' }}
                                    </label>
                                </div>

                                <div v-if="editingSkillId === skill.id" class="grid gap-2">
                                    <input v-model="editSkillName" type="text"
                                        class="w-full px-3 py-2 text-sm border rounded-md outline-none bg-black/30 border-stone-900 text-stone-200 placeholder:text-stone-500 focus:border-stone-800" />
                                    <textarea v-model="editSkillInstructions" rows="4"
                                        class="w-full px-3 py-2 text-sm border rounded-md outline-none resize-y bg-black/30 border-stone-900 text-stone-200 placeholder:text-stone-500 focus:border-stone-800" />
                                    <div class="flex justify-end gap-2">
                                        <button @click="cancelEditSkill"
                                            class="px-3 py-1.5 text-sm border rounded-md border-stone-700 bg-transparent text-stone-300 hover:bg-stone-800/40">
                                            Cancel
                                        </button>
                                        <button @click="saveEditSkill(skill)" :disabled="skillsBusy"
                                            class="px-3 py-1.5 text-sm border rounded-md border-stone-700 bg-stone-800 text-stone-200 hover:bg-stone-700 disabled:opacity-50">
                                            Save
                                        </button>
                                    </div>
                                </div>

                                <div v-else>
                                    <p class="text-sm whitespace-pre-wrap text-stone-300">{{ skill.instructions }}</p>
                                    <div class="flex justify-end gap-2 mt-2">
                                        <button @click="startEditSkill(skill)"
                                            class="px-3 py-1.5 text-sm border rounded-md border-stone-700 bg-transparent text-stone-300 hover:bg-stone-800/40">
                                            Edit
                                        </button>
                                        <button @click="removeSkill(skill.id)" :disabled="skillsBusy"
                                            class="px-3 py-1.5 text-sm border rounded-md border-red-700/50 bg-red-950/30 text-red-300 hover:bg-red-900/40 disabled:opacity-50">
                                            Delete
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="space-y-2">
                            <p class="text-xs uppercase tracking-wide text-stone-400">Available agents and tools</p>
                            <div class="text-xs text-stone-500">
                                Use these names when writing skills (for example: "Always call datamodel.get_topology first").
                            </div>
                            <div v-for="agent in toolCatalog" :key="agent.agent_key"
                                class="p-3 border rounded-md border-stone-800 bg-zinc-900/30">
                                <p class="text-sm font-semibold text-stone-200">
                                    {{ agent.agent_name }}
                                    <span class="font-normal text-stone-500">
                                        ({{ agent.specialist_tool || 'specialist tool unknown' }})
                                    </span>
                                </p>
                                <div class="mt-2 space-y-1">
                                    <p v-for="tool in agent.tools" :key="`${agent.agent_key}-${tool.python_name}`"
                                        class="text-xs text-stone-300">
                                        <span class="font-medium text-stone-200">{{ tool.runtime_name || tool.python_name }}</span>
                                        <span class="text-stone-500"> · {{ tool.summary || 'No description' }}</span>
                                    </p>
                                </div>
                            </div>
                        </div>
                    </TabsContent>

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

                    <TabsContent value="about" class="h-full pr-2 overflow-y-auto text-sm text-stone-400">
                        <div class="flex flex-col gap-5">
                            <p class="flex gap-5 text-stone-200">
                                <span class="text-stone-400">Developer</span>
                                HamzaDLM (hamzadlm@email.com)
                            </p>
                            <p class="flex gap-5 text-stone-200">
                                <span class="text-stone-400">UI</span>
                                {{ uiVersion }} ({{ uiGitSha }})
                            </p>
                            <p class="flex gap-5 text-stone-200">
                                <span class="text-stone-400">API</span>
                                {{ backendVersion }} ({{ backendGitSha }})
                            </p>
                            <p class="flex gap-5 text-stone-200">
                                <span class="text-stone-400">Status</span>
                                {{ backendStatusLabel }}
                            </p>
                        </div>
                    </TabsContent>
                </div>
            </Tabs>
        </DialogContent>
    </Dialog>
</template>
