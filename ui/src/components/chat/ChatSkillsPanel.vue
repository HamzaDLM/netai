<script setup lang="ts">
import {computed, onMounted, ref, watch} from 'vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import {useSkillsStore} from '@/stores/skills.store'
import type {Skill, SkillMarketplaceListing} from '@/types/skill.type'
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
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {toast} from '@/components/ui/toast'

const skillsStore = useSkillsStore()

const skillDialogOpen = ref(false)
const marketplaceDialogOpen = ref(false)
const skillViewerOpen = ref(false)
const deleteDialogOpen = ref(false)
const skillDialogMode = ref < 'create' | 'edit' > ('create')
const activeSkillId = ref < number | null > (null)
const selectedSkill = ref < Skill | null > (null)
const selectedMarketplaceListing = ref < SkillMarketplaceListing | null > (null)
const pendingDeleteSkill = ref < Skill | null > (null)
const marketplaceSearch = ref('')
const skillFormName = ref('')
const skillFormDescription = ref('')
const skillFormInstructions = ref('')
const skillFormEnabled = ref(true)
const isEditMode = computed(() => skillDialogMode.value === 'edit' && activeSkillId.value !== null)
const filteredMarketplace = computed(() => {
    const query = marketplaceSearch.value.trim().toLowerCase()
    if (!query) return skillsStore.marketplace

    return skillsStore.marketplace.filter(listing => {
        const haystack = [
            listing.name,
            listing.slug,
            listing.description,
            listing.instructions,
        ]
            .filter(Boolean)
            .join(' ')
            .toLowerCase()
        return haystack.includes(query)
    })
})
function resetSkillForm() {
    skillDialogMode.value = 'create'
    activeSkillId.value = null
    skillFormName.value = ''
    skillFormDescription.value = ''
    skillFormInstructions.value = ''
    skillFormEnabled.value = true
}

function openCreateSkillDialog() {
    resetSkillForm()
    skillDialogOpen.value = true
}

function openEditSkillDialog(skill: Skill) {
    skillDialogMode.value = 'edit'
    activeSkillId.value = skill.id
    skillFormName.value = skill.name
    skillFormDescription.value = skill.description ?? ''
    skillFormInstructions.value = skill.instructions
    skillFormEnabled.value = skill.enabled
    skillDialogOpen.value = true
}

function openSkillViewer(skill: Skill) {
    selectedSkill.value = skill
    skillViewerOpen.value = true
}

function openDeleteDialog(skill: Skill) {
    pendingDeleteSkill.value = skill
    deleteDialogOpen.value = true
}

function openMarketplaceViewer(listing: SkillMarketplaceListing) {
    selectedMarketplaceListing.value = listing
}

function isMarketplaceListingInstalled(listingId: number): boolean {
    return skillsStore.skills.some(skill => skill.installed_from_listing_id === listingId)
}

async function confirmDeleteSkill() {
    if (!pendingDeleteSkill.value) return
    const deleted = await skillsStore.deleteSkill(pendingDeleteSkill.value.id)
    if (!deleted) return

    if (selectedSkill.value?.id === pendingDeleteSkill.value.id) {
        skillViewerOpen.value = false
    }

    deleteDialogOpen.value = false
    pendingDeleteSkill.value = null
}

function marketplaceStatusLabel(skill: Skill): string {
    if (!skill.marketplace_status) return ''
    if (skill.marketplace_status === 'approved') return 'Marketplace Live'
    if (skill.marketplace_status === 'pending') return 'Pending Review'
    return 'Rejected'
}

function shareButtonLabel(skill: Skill): string {
    if (!skill.marketplace_status) return 'Share'
    if (skill.marketplace_status === 'approved') return 'Submit Update'
    if (skill.marketplace_status === 'pending') return 'Pending Review'
    return 'Resubmit'
}

async function saveSkill() {
    const name = skillFormName.value.trim()
    const description = skillFormDescription.value.trim()
    const instructions = skillFormInstructions.value.trim()

    if (!name || !instructions) {
        toast({title: 'Title and instructions are required', variant: 'destructive'})
        return
    }

    if (isEditMode.value && activeSkillId.value !== null) {
        const updated = await skillsStore.updateSkill(activeSkillId.value, {
            name,
            description,
            instructions,
            enabled: skillFormEnabled.value,
        })
        if (updated) skillDialogOpen.value = false
        return
    }

    const created = await skillsStore.createSkill({
        name,
        description,
        instructions,
        enabled: skillFormEnabled.value,
    })
    if (created) skillDialogOpen.value = false
}

watch(skillDialogOpen, isOpen => {
    if (isOpen) return
    resetSkillForm()
})

watch(skillViewerOpen, isOpen => {
    if (isOpen) return
    selectedSkill.value = null
})

watch(marketplaceDialogOpen, isOpen => {
    if (!isOpen) {
        marketplaceSearch.value = ''
        selectedMarketplaceListing.value = null
        return
    }

    selectedMarketplaceListing.value = skillsStore.marketplace[0] ?? null
})

watch(deleteDialogOpen, isOpen => {
    if (isOpen) return
    pendingDeleteSkill.value = null
})

watch(filteredMarketplace, listings => {
    if (listings.length === 0) {
        selectedMarketplaceListing.value = null
        return
    }

    if (!selectedMarketplaceListing.value) {
        selectedMarketplaceListing.value = listings[0]
        return
    }

    const stillVisible = listings.some(listing => listing.id === selectedMarketplaceListing.value?.id)
    if (!stillVisible) selectedMarketplaceListing.value = listings[0]
})

onMounted(async () => {
    await skillsStore.loadBootstrap()
})
</script>

<template>
	<div class="flex flex-col h-full min-h-0">
		<div class="flex-1 min-h-0 overflow-y-auto">
			<div class="flex flex-col w-full h-full gap-8 px-10 py-10 mx-auto max-w-7xl lg:px-16">
				<div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
					<div class="space-y-2">
						<p class="text-3xl font-semibold text-stone-200">Skills</p>
						<p class="max-w-3xl text-sm leading-6 text-stone-400">
							Skills are now explicit chat commands. Create or install them here, then invoke them inside
							chat with
							<span class="font-medium text-stone-200">`/skill-name`</span>.
						</p>
					</div>
					<div class="flex gap-2">
						<Dialog v-model:open="marketplaceDialogOpen">
							<DialogTrigger as-child>
								<button type="button"
									class="inline-flex items-center self-start gap-3 px-4 text-sm font-medium transition rounded-full h-11 text-stone-200 hover:bg-stone-800">
									<span class="inline-flex items-center justify-center w-6 h-6 text-stone-200">
										<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor"
											stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
											aria-hidden="true">
											<path d="M3 7.5h18" />
											<path
												d="M6 7.5V6a2 2 0 0 1 2-2h2.5a1.5 1.5 0 0 1 3 0H16a2 2 0 0 1 2 2v1.5" />
											<path d="M5 7.5V18a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7.5" />
											<path d="M9 11h6" />
											<path d="M12 8.5V14" />
										</svg>
									</span>
									Marketplace
								</button>
							</DialogTrigger>
							<DialogContent class="flex h-[84vh] max-h-[84vh] flex-col border-stone-800 bg-stone-950 text-stone-200 sm:max-w-[90vw]">
								<DialogHeader>
									<DialogTitle>Skills Marketplace</DialogTitle>
									<DialogDescription class="text-stone-400">
										Browse approved shared skills, add them to your setup, and invoke them in chat
										with
										<span class="font-medium text-stone-200">`/skill-slug`</span>.
									</DialogDescription>
								</DialogHeader>

								<div class="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
									<div class="flex flex-col min-h-0 p-4 border rounded-2xl border-stone-800 bg-stone-950/40">
										<label class="relative block">
											<span class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-stone-500">
												<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor"
													stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
													aria-hidden="true">
													<circle cx="11" cy="11" r="7" />
													<path d="m20 20-3.5-3.5" />
												</svg>
											</span>
											<input v-model="marketplaceSearch" type="text" placeholder="Search marketplace skills"
												class="w-full pl-10 pr-4 text-sm border rounded-md outline-none h-11 border-stone-800 bg-stone-950/70 text-stone-200 placeholder:text-stone-500 focus:border-stone-700" />
										</label>

										<div class="flex-1 min-h-0 pr-1 mt-4 overflow-y-auto">
											<div v-if="skillsStore.marketplace.length === 0"
												class="px-5 py-10 text-sm border border-dashed rounded-2xl border-stone-700 bg-zinc-900/20 text-stone-500">
												No approved skills yet.
											</div>
											<div v-else-if="filteredMarketplace.length === 0"
												class="px-5 py-10 text-sm border border-dashed rounded-2xl border-stone-700 bg-zinc-900/20 text-stone-500">
												No skills match this search.
											</div>
											<div v-else class="grid grid-cols-3 gap-3">
                                                <article v-for="listing in filteredMarketplace" :key="listing.id"
                                                    class="p-4 transition border rounded-xl border-stone-800 bg-stone-950/40"
                                                    :class="selectedMarketplaceListing?.id === listing.id ? 'border-stone-600 bg-stone-900/50' : 'hover:border-stone-700 hover:bg-stone-900/30'">
                                                    <div class="flex items-start justify-between gap-3">
                                                        <p class="text-base font-medium text-stone-200">{{ listing.name }}</p>
                                                    </div>
                                                    <p v-if="listing.description" class="mt-4 text-sm leading-6 text-stone-400">
                                                        {{ listing.description }}
                                                    </p>
                                                    <div class="flex justify-end gap-2 mt-4">
                                                        <button type="button"
                                                            :disabled="skillsStore.isBusy || isMarketplaceListingInstalled(listing.id)"
                                                            class="rounded-md border border-stone-700 bg-stone-900/70 px-3 py-1.5 text-sm text-stone-200 transition hover:border-stone-500 hover:bg-stone-800 disabled:opacity-50"
                                                            @click="skillsStore.installMarketplaceSkill(listing.id)">
                                                            {{ isMarketplaceListingInstalled(listing.id) ? 'Added' : '+' }}
                                                        </button>
                                                        <button type="button"
                                                            class="rounded-md border border-stone-700 bg-stone-900/70 px-3 py-1.5 text-sm text-stone-200 transition hover:border-stone-500 hover:bg-stone-800"
                                                            @click="openMarketplaceViewer(listing)">
                                                            View
                                                        </button>
                                                    </div>
                                                </article>
											</div>
										</div>
									</div>

									<div class="flex flex-col min-h-0 p-4 border rounded-2xl border-stone-800 bg-black/20">
										<div v-if="selectedMarketplaceListing" class="flex flex-col flex-1 min-h-0">
											<div class="pb-4 border-b border-stone-800">
												<p class="text-lg font-semibold text-stone-200">{{ selectedMarketplaceListing.name }}</p>
												<p v-if="selectedMarketplaceListing.description" class="mt-2 text-sm leading-6 text-stone-400">
													{{ selectedMarketplaceListing.description }}
												</p>
											</div>
											<div class="flex-1 min-h-0 pr-1 mt-4 overflow-y-auto">
												<MarkdownRenderer
													:content="selectedMarketplaceListing.instructions?.trim() || '_No instructions available for this skill._'" />
											</div>
										</div>
										<div v-else
											class="flex items-center justify-center flex-1 text-sm border border-dashed rounded-xl border-stone-800 text-stone-500">
											Select a marketplace skill to preview it.
										</div>
									</div>
								</div>
							</DialogContent>
						</Dialog>

						<Dialog v-model:open="skillDialogOpen">
							<DialogTrigger as-child>
								<button type="button"
									class="inline-flex items-center self-start gap-3 px-4 text-sm font-medium transition rounded-full h-11 text-stone-200 hover:bg-stone-800"
									@click="openCreateSkillDialog">
									<span class="inline-flex items-center justify-center w-6 h-6 text-stone-200">
										<svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor"
											stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
											aria-hidden="true">
											<path d="M12 5v14" />
											<path d="M5 12h14" />
										</svg>
									</span>
									Create Skill
								</button>
							</DialogTrigger>
							<DialogContent class="border-stone-800 bg-stone-950 text-stone-200 sm:max-w-2xl">
								<DialogHeader>
									<DialogTitle>{{ isEditMode ? 'Edit Skill' : 'Create Skill' }}</DialogTitle>
									<DialogDescription class="text-stone-400">
										Define the title, description, and instructions. The slash command will be
										derived automatically from the title.
									</DialogDescription>
								</DialogHeader>

								<div class="grid gap-4 py-2">
									<div class="grid gap-2">
										<label class="pl-1 text-sm tracking-wide text-stone-400"
											for="skill-name">Title</label>
										<input id="skill-name" v-model="skillFormName" type="text"
											placeholder="Branch WAN Flap Triage"
											class="w-full px-4 py-3 text-sm border rounded-md outline-none border-stone-900 bg-black/30 text-stone-200 placeholder:text-stone-500 focus:border-stone-800" />
									</div>

									<div class="grid gap-2">
										<label class="pl-1 text-sm tracking-wide text-stone-400"
											for="skill-description">Description</label>
										<textarea id="skill-description" v-model="skillFormDescription" rows="3"
											placeholder="A short summary of when this skill should be used and what outcome it should drive."
											class="w-full px-4 py-3 text-sm border rounded-md outline-none border-stone-900 bg-black/30 text-stone-200 placeholder:text-stone-500 focus:border-stone-800" />
									</div>

									<div class="grid gap-2">
										<label class="pl-1 text-sm tracking-wide text-stone-400"
											for="skill-instructions">Instructions</label>
										<textarea id="skill-instructions" v-model="skillFormInstructions" rows="10"
											placeholder="When the user asks about WAN instability: prioritize zabbix, syslog, and SuzieQ, correlate the timeline, and return the exact evidence."
											class="w-full px-4 py-3 text-sm border rounded-md outline-none border-stone-900 bg-black/30 text-stone-200 placeholder:text-stone-500 focus:border-stone-800" />
									</div>

									<label
										class="flex items-center gap-3 px-4 py-3 text-sm border rounded-lg border-stone-800 bg-stone-900/40 text-stone-300">
										<input v-model="skillFormEnabled" type="checkbox"
											class="w-4 h-4 accent-red-500" />
										<span>Enabled</span>
									</label>
								</div>

								<DialogFooter class="gap-2">
									<DialogClose as-child>
										<button type="button"
											class="rounded-md border border-stone-700 bg-transparent px-3 py-1.5 text-sm text-stone-300 hover:bg-stone-800/40">
											Cancel
										</button>
									</DialogClose>
									<button :disabled="skillsStore.isBusy"
										class="rounded-md border border-stone-700 bg-stone-800 px-3 py-1.5 text-sm text-stone-200 hover:bg-stone-700 disabled:opacity-50"
										@click="saveSkill">
										{{ isEditMode ? 'Save' : 'Create' }}
									</button>
								</DialogFooter>
							</DialogContent>
						</Dialog>
					</div>
				</div>

				<div>
					<div class="flex items-center justify-between gap-3">
						<div>
							<p class="text-lg font-semibold text-stone-300">Your Skills</p>
							<p class="mt-1 text-sm text-stone-500">Local skills available from chat via slash commands.
							</p>
						</div>
						<p v-if="skillsStore.skills.length > 0"
							class="text-xs uppercase tracking-[0.24em] text-stone-500">
							{{ skillsStore.skills.length }} total
						</p>
					</div>
				</div>

				<section>
					<div v-if="skillsStore.isLoading" class="text-sm text-stone-500">Loading skills...</div>
					<div v-else-if="skillsStore.skills.length === 0"
						class="px-5 py-10 text-sm border border-dashed rounded-2xl border-stone-700 bg-zinc-900/20 text-stone-500">
						No skills yet. Use the <span class="font-medium text-stone-300">+</span> button to create your
						first one.
					</div>
					<div v-else class="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-3">
						<article v-for="skill in skillsStore.skills" :key="skill.id"
							class="group relative flex min-h-[15rem] flex-col overflow-hidden rounded-xl border border-stone-800 bg-stone-950/50 p-4 transition hover:border-stone-700 hover:bg-stone-950/70">
							<button type="button"
								class="absolute inset-0 z-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-inset focus:ring-stone-700/80"
								aria-label="View skill details"
								@click="openSkillViewer(skill)" />

							<div class="relative z-10 flex flex-col flex-1 pointer-events-none">
								<div class="flex items-center justify-end gap-2 mb-3">
									<div class="flex flex-wrap gap-2 text-xs tracking-wide">
										<span v-if="marketplaceStatusLabel(skill) !== ''" class="rounded-full border border-stone-700 px-2 py-0.5 text-stone-400">{{
											marketplaceStatusLabel(skill) }}</span>
										<span v-if="skill.installed_from_listing_id"
											class="rounded-full border border-sky-700/40 px-2 py-0.5 text-sky-300">Marketplace
											Install</span>
									</div>
									<div class="w-min shrink-0 rounded-full border px-2 py-0.5 text-xs tracking-wide"
										:class="skill.enabled ? 'border-emerald-700/50 text-emerald-300' : 'border-stone-700 text-stone-400'">
										{{ skill.enabled ? 'Enabled' : 'Disabled' }}
									</div>
								</div>
								<div>
									<p class="text-sm font-medium text-stone-200">{{ skill.name }}</p>
									<p class="mt-1 text-xs tracking-[0.18em] text-stone-500">/{{ skill.slug }}</p>
								</div>

								<p v-if="skill.description" class="pt-5 text-sm leading-6 text-stone-500">{{
									skill.description }}</p>
								<p v-if="skill.marketplace_review_notes"
									class="px-3 py-2 mt-3 text-xs leading-5 border rounded-md border-stone-800 bg-black/20 text-stone-400">
									{{ skill.marketplace_review_notes }}
								</p>
							</div>

							<div class="relative z-20 flex flex-wrap justify-end gap-2 pt-5 mt-auto text-xs">
								<Button v-if="!skill.installed_from_listing_id" type="button"
									:disabled="skillsStore.isBusy || skill.marketplace_status === 'pending'"
									class="rounded-md flex items-center gap-2 px-3 py-1.5 text-stone-300 transition disabled:opacity-50"
									:class="skill.marketplace_status === 'pending' ? '' : 'hover:bg-sky-500/10'"
									@click.stop="skillsStore.requestShare(skill.id)">
									{{ shareButtonLabel(skill) }}
								</Button>
								<Button type="button"
									class="px-3 py-1.5 text-stone-300 transition rounded-md hover:bg-stone-800/40"
									@click.stop="openEditSkillDialog(skill)">
									Edit
								</Button>
								<Button type="button" :disabled="skillsStore.isBusy"
									class="rounded-md px-3 py-1.5 text-red-300 transition hover:bg-red-500/10 hover:text-red-200 disabled:opacity-50"
									@click="openDeleteDialog(skill)">
									Delete
								</Button>
							</div>
						</article>
					</div>
				</section>
			</div>
		</div>
		<Dialog v-model:open="skillViewerOpen">
			<DialogContent class="flex h-[80vh] max-h-[80vh] flex-col border-stone-800 bg-stone-950 text-stone-200 sm:max-w-4xl">
				<DialogHeader>
					<DialogTitle>{{ selectedSkill?.name ?? 'Skill' }}</DialogTitle>
					<DialogDescription class="space-y-2 text-stone-400">
						<p class="text-xs uppercase tracking-[0.18em] text-stone-500">
							/{{ selectedSkill?.slug ?? 'skill' }}
						</p>
						<p v-if="selectedSkill?.description">{{ selectedSkill.description }}</p>
					</DialogDescription>
				</DialogHeader>

				<div class="flex-1 min-h-0 p-5 overflow-y-auto border rounded-xl border-stone-800 bg-black/20">
					<MarkdownRenderer
						:content="selectedSkill?.instructions?.trim() || '_No instructions available for this skill._'" />
				</div>
			</DialogContent>
		</Dialog>

		<AlertDialog v-model:open="deleteDialogOpen">
			<AlertDialogContent class="border-stone-800 bg-stone-950 text-stone-200 sm:max-w-md">
				<AlertDialogHeader>
					<AlertDialogTitle>Delete skill?</AlertDialogTitle>
					<AlertDialogDescription class="text-stone-400">
						This will permanently delete
						<span class="font-medium text-stone-200">{{ pendingDeleteSkill?.name ?? 'this skill' }}</span>.
					</AlertDialogDescription>
				</AlertDialogHeader>
				<AlertDialogFooter>
					<AlertDialogCancel class="bg-transparent border-stone-700 text-stone-300 hover:bg-stone-800/40 hover:text-stone-200">
						Cancel
					</AlertDialogCancel>
					<AlertDialogAction class="text-white bg-red-600 hover:bg-red-500" @click="confirmDeleteSkill">
						Delete
					</AlertDialogAction>
				</AlertDialogFooter>
			</AlertDialogContent>
		</AlertDialog>
	</div>
</template>
