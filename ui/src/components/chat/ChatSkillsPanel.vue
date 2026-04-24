<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { toast } from '@/components/ui/toast'
import skillsService from '@/services/skills.service'
import type { Skill } from '@/types/skill.type'
import {
    Dialog,
    DialogClose,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog'

const skills = ref<Skill[]>([])
const skillsLoading = ref(false)
const skillsBusy = ref(false)
const skillDialogOpen = ref(false)
const skillDialogMode = ref<'create' | 'edit'>('create')
const activeSkillId = ref<number | null>(null)

const skillFormName = ref('')
const skillFormDescription = ref('')
const skillFormInstructions = ref('')
const skillFormEnabled = ref(true)

const isEditMode = () => skillDialogMode.value === 'edit' && activeSkillId.value !== null

const resetSkillForm = () => {
    skillDialogMode.value = 'create'
    activeSkillId.value = null
    skillFormName.value = ''
    skillFormDescription.value = ''
    skillFormInstructions.value = ''
    skillFormEnabled.value = true
}

const openCreateSkillDialog = () => {
    resetSkillForm()
    skillDialogOpen.value = true
}

const openEditSkillDialog = (skill: Skill) => {
    skillDialogMode.value = 'edit'
    activeSkillId.value = skill.id
    skillFormName.value = skill.name
    skillFormDescription.value = skill.description ?? ''
    skillFormInstructions.value = skill.instructions
    skillFormEnabled.value = skill.enabled
    skillDialogOpen.value = true
}

const loadSkillsData = async () => {
    skillsLoading.value = true
    try {
        const response = await skillsService.getSkills()
        skills.value = response.data
    } catch {
        toast({ title: 'Unable to load skills data', variant: 'destructive' })
    } finally {
        skillsLoading.value = false
    }
}

const saveSkill = async () => {
    const name = skillFormName.value.trim()
    const description = skillFormDescription.value.trim()
    const instructions = skillFormInstructions.value.trim()

    if (!name || !instructions) {
        toast({ title: 'Title and instructions are required', variant: 'destructive' })
        return
    }

    skillsBusy.value = true
    try {
        if (isEditMode() && activeSkillId.value !== null) {
            const response = await skillsService.updateSkill(activeSkillId.value, {
                name,
                description,
                instructions,
                enabled: skillFormEnabled.value,
            })
            const idx = skills.value.findIndex(item => item.id === activeSkillId.value)
            if (idx !== -1) skills.value[idx] = response.data
        } else {
            const response = await skillsService.createSkill({
                name,
                description,
                instructions,
                enabled: skillFormEnabled.value,
            })
            skills.value.unshift(response.data)
        }

        skillDialogOpen.value = false
        resetSkillForm()
    } catch (error: any) {
        const detail = String(error?.response?.data?.detail ?? '')
        if (detail === 'skill_name_already_exists') {
            toast({ title: 'A skill with this name already exists', variant: 'destructive' })
            return
        }
        toast({
            title: isEditMode() ? 'Unable to update skill' : 'Unable to create skill',
            variant: 'destructive',
        })
    } finally {
        skillsBusy.value = false
    }
}

watch(skillDialogOpen, isOpen => {
    if (isOpen) return
    resetSkillForm()
})

const removeSkill = async (skillId: number) => {
    skillsBusy.value = true
    try {
        await skillsService.deleteSkill(skillId)
        skills.value = skills.value.filter(skill => skill.id !== skillId)
        if (activeSkillId.value === skillId) resetSkillForm()
    } catch {
        toast({ title: 'Unable to delete skill', variant: 'destructive' })
    } finally {
        skillsBusy.value = false
    }
}

onMounted(async () => {
    await loadSkillsData()
})
</script>

<template>
    <div class="flex flex-col h-full min-h-0">
        <div class="flex-1 min-h-0 overflow-y-auto">
            <div class="flex flex-col w-full h-full gap-8 px-10 py-10 mx-auto max-w-7xl lg:px-16">
                <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div class="space-y-2">
                        <p class="text-3xl font-semibold text-stone-200">Skills</p>
                        <p class="max-w-2xl text-sm text-stone-400">
                            Create reusable instructions that shape how NetAI responds to recurring workflows.
                        </p>
                    </div>

                    <Dialog v-model:open="skillDialogOpen">
                        <DialogTrigger as-child>
                            <button type="button"
                                class="inline-flex items-center self-start gap-3 px-4 text-sm font-medium transition rounded-full h-11 text-stone-200 hover:border-stone-500 hover:bg-stone-800"
                                @click="openCreateSkillDialog">
                                <span class="inline-flex items-center justify-center w-6 h-6 text-stone-200">
                                    <Icon icon="fluent-emoji-high-contrast:plus" class="h-3.5 w-3.5" />
                                </span>
                                Create Skill
                            </button>
                        </DialogTrigger>
                        <DialogContent class="border-stone-800 bg-stone-950 text-stone-200 sm:max-w-2xl">
                            <DialogHeader>
                                <DialogTitle>{{ isEditMode() ? 'Edit Skill' : 'Create Skill' }}</DialogTitle>
                                <DialogDescription class="text-stone-400">
                                    Define the title, short description, and end-to-end instructions for this skill.
                                </DialogDescription>
                            </DialogHeader>

                            <div class="grid gap-4 py-2">
                                <div class="grid gap-2">
                                    <label class="pl-1 text-sm tracking-wide text-stone-400" for="skill-name">
                                        Title
                                    </label>
                                    <input id="skill-name" v-model="skillFormName" type="text"
                                        placeholder="Branch WAN Flap Triage"
                                        class="w-full px-4 py-3 text-sm border rounded-md outline-none border-stone-900 bg-black/30 text-stone-200 placeholder:text-stone-500 focus:border-stone-800" />
                                </div>

                                <div class="grid gap-2">
                                    <label class="pl-1 text-sm tracking-wide text-stone-400" for="skill-description">
                                        Description
                                    </label>
                                    <textarea id="skill-description" v-model="skillFormDescription" rows="3"
                                        placeholder="A short summary of when this skill should be used and what outcome it should drive."
                                        class="w-full px-4 py-3 text-sm border rounded-md outline-none border-stone-900 bg-black/30 text-stone-200 placeholder:text-stone-500 focus:border-stone-800" />
                                </div>

                                <div class="grid gap-2">
                                    <label class="pl-1 text-sm tracking-wide text-stone-400" for="skill-instructions">
                                        Instructions
                                    </label>
                                    <textarea id="skill-instructions" v-model="skillFormInstructions" rows="10"
                                        placeholder="When user mentions packet loss, drops, flaps, or unstable WAN:

- Prioritize zabbix_specialist and syslog_specialist first.
- Ask for the last 60 minutes of host problems, trigger history, interface events, and BGP adjacency log patterns.
- Return the likely root cause, exact timestamps, and the top three evidence points."
                                        class="w-full px-4 py-3 text-sm border rounded-md outline-none border-stone-900 bg-black/30 text-stone-200 placeholder:text-stone-500 focus:border-stone-800" />
                                </div>
                            </div>

                            <DialogFooter class="gap-2">
                                <DialogClose as-child>
                                    <button type="button"
                                        class="rounded-md border border-stone-700 bg-transparent px-3 py-1.5 text-sm text-stone-300 hover:bg-stone-800/40">
                                        Cancel
                                    </button>
                                </DialogClose>
                                <button :disabled="skillsBusy"
                                    class="rounded-md border border-stone-700 bg-stone-800 px-3 py-1.5 text-sm text-stone-200 hover:bg-stone-700 disabled:opacity-50"
                                    @click="saveSkill">
                                    {{ isEditMode() ? 'Save' : 'Create' }}
                                </button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                </div>

                <div class="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(18rem,0.8fr)]">
                    <div class="p-6 border rounded-2xl border-stone-800 bg-zinc-900/30">
                        <div class="flex items-center justify-between gap-3">
                            <div>
                                <p class="text-lg font-semibold text-stone-300">Your Skills</p>
                                <p class="mt-1 text-sm text-stone-500">
                                    Manage the custom playbooks available to your chat experience.
                                </p>
                            </div>
                            <p v-if="skills.length > 0" class="text-xs uppercase tracking-[0.24em] text-stone-500">
                                {{ skills.length }} total
                            </p>
                        </div>
                    </div>

                    <div class="p-6 border border-dashed rounded-2xl border-stone-700 bg-zinc-900/20">
                        <p class="text-sm font-medium text-stone-300">Marketplace</p>
                        <p class="mt-2 text-sm leading-6 text-stone-500">
                            Reserved space for a future skills marketplace so discovery can sit beside your custom
                            library.
                        </p>
                    </div>
                </div>

                <div v-if="skillsLoading" class="text-sm text-stone-500">
                    Loading skills...
                </div>
                <div v-else-if="skills.length === 0"
                    class="px-5 py-10 text-sm border border-dashed rounded-2xl border-stone-700 bg-zinc-900/20 text-stone-500">
                    No skills yet. Use the <span class="font-medium text-stone-300">+</span> button to create your first
                    one.
                </div>
                <div v-else class="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                    <article v-for="skill in skills" :key="skill.id"
                        class="flex min-h-[14rem] flex-col rounded-xl border border-stone-800 bg-stone-950/50 p-4">
                        <div class="flex items-center justify-between space-y-1">
                            <p class="text-base font-medium text-stone-200">{{ skill.name }}</p>
                            <span class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-wide"
                                :class="skill.enabled
                                    ? 'border-emerald-700/50 text-emerald-300'
                                    : 'border-stone-700 text-stone-400'">
                                {{ skill.enabled ? 'Enabled' : 'Disabled' }}
                            </span>
                        </div>
                        <p v-if="skill.description" class="pt-5 text-sm text-stone-500">
                            {{ skill.description }}
                        </p>

                        <div class="flex flex-col flex-1">
                            <div class="flex justify-end gap-2 mt-auto">
                                <button class="px-3 py-1.5 text-sm text-stone-300 hover:bg-stone-800/40"
                                    @click="openEditSkillDialog(skill)">
                                    Edit
                                </button>
                                <button :disabled="skillsBusy"
                                    class="rounded-md px-3 py-1.5 text-sm text-red-300 hover:bg-red-500/10 hover:text-red-200 disabled:opacity-50"
                                    @click="removeSkill(skill.id)">
                                    Delete
                                </button>
                            </div>
                        </div>
                    </article>
                </div>
            </div>
        </div>
    </div>
</template>
