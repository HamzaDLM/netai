<script setup lang="ts">
	import {computed, onMounted, ref, watch} from 'vue'
	import {useSkillsStore} from '@/stores/skills.store'
	import type {Skill} from '@/types/skill.type'
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
	import {toast} from '@/components/ui/toast'

	const skillsStore = useSkillsStore()

	const skillDialogOpen = ref(false)
	const marketplaceDialogOpen = ref(false)
	const skillDialogMode = ref < 'create' | 'edit' > ('create')
	const activeSkillId = ref < number | null > (null)
	const skillFormName = ref('')
	const skillFormDescription = ref('')
	const skillFormInstructions = ref('')
	const skillFormEnabled = ref(true)

	const isEditMode = computed(() => skillDialogMode.value === 'edit' && activeSkillId.value !== null)
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

	function marketplaceStatusLabel(skill: Skill): string {
		if (!skill.marketplace_status) return 'Private'
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

	onMounted(async () => {
		await skillsStore.loadBootstrap()
	})
</script>

<template>
	<div class="flex h-full min-h-0 flex-col">
		<div class="flex-1 min-h-0 overflow-y-auto">
			<div class="mx-auto flex h-full w-full max-w-7xl flex-col gap-8 px-10 py-10 lg:px-16">
				<div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
					<div class="space-y-2">
						<p class="text-3xl font-semibold text-stone-200">Skills</p>
						<p class="max-w-3xl text-sm leading-6 text-stone-400">
							Skills are now explicit chat commands. Create or install them here, then invoke them inside
							chat with
							<span class="font-medium text-stone-200">`/skill-slug`</span>.
						</p>
					</div>
					<div class="flex gap-2">
						<Dialog v-model:open="marketplaceDialogOpen">
							<DialogTrigger as-child>
								<button type="button"
									class="inline-flex h-11 items-center gap-3 self-start rounded-full px-4 text-sm font-medium text-stone-200 transition hover:bg-stone-800">
									<span class="inline-flex h-6 w-6 items-center justify-center text-stone-200">
										<Icon icon="solar:shop-2-linear" class="h-4 w-4" />
									</span>
									Marketplace
								</button>
							</DialogTrigger>
							<DialogContent class="border-stone-800 bg-stone-950 text-stone-200 sm:max-w-4xl">
								<DialogHeader>
									<DialogTitle>Skills Marketplace</DialogTitle>
									<DialogDescription class="text-stone-400">
										Browse approved shared skills, add them to your setup, and invoke them in chat
										with
										<span class="font-medium text-stone-200">`/skill-slug`</span>.
									</DialogDescription>
								</DialogHeader>

								<div class="max-h-[70vh] overflow-y-auto pr-1">
									<div v-if="skillsStore.marketplace.length === 0"
										class="rounded-2xl border border-dashed border-stone-700 bg-zinc-900/20 px-5 py-10 text-sm text-stone-500">
										No approved marketplace skills yet.
									</div>
									<div v-else class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
										<article v-for="listing in skillsStore.marketplace" :key="listing.id"
											class="rounded-xl border border-stone-800 bg-stone-950/40 p-4">
											<div class="flex items-start justify-between gap-3">
												<div>
													<p class="text-base font-medium text-stone-200">{{ listing.name }}
													</p>
													<p class="mt-1 text-xs uppercase tracking-[0.18em] text-stone-500">
														/{{ listing.slug }}</p>
												</div>
												<span
													class="rounded-full border border-emerald-700/50 px-2 py-0.5 text-[11px] uppercase tracking-wide text-emerald-300">Approved</span>
											</div>
											<p v-if="listing.description" class="mt-4 text-sm leading-6 text-stone-400">
												{{ listing.description }}</p>
											<div class="mt-4 flex justify-end">
												<button type="button" :disabled="skillsStore.isBusy"
													class="rounded-md border border-stone-700 bg-stone-900/70 px-3 py-1.5 text-sm text-stone-200 transition hover:border-stone-500 hover:bg-stone-800 disabled:opacity-50"
													@click="skillsStore.installMarketplaceSkill(listing.id)">
													Add to My Skills
												</button>
											</div>
										</article>
									</div>
								</div>
							</DialogContent>
						</Dialog>

						<Dialog v-model:open="skillDialogOpen">
							<DialogTrigger as-child>
								<button type="button"
									class="inline-flex h-11 items-center gap-3 self-start rounded-full px-4 text-sm font-medium text-stone-200 transition hover:bg-stone-800"
									@click="openCreateSkillDialog">
									<span class="inline-flex h-6 w-6 items-center justify-center text-stone-200">
										<Icon icon="fluent-emoji-high-contrast:plus" class="h-3.5 w-3.5" />
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
											class="w-full rounded-md border border-stone-900 bg-black/30 px-4 py-3 text-sm text-stone-200 outline-none placeholder:text-stone-500 focus:border-stone-800" />
									</div>

									<div class="grid gap-2">
										<label class="pl-1 text-sm tracking-wide text-stone-400"
											for="skill-description">Description</label>
										<textarea id="skill-description" v-model="skillFormDescription" rows="3"
											placeholder="A short summary of when this skill should be used and what outcome it should drive."
											class="w-full rounded-md border border-stone-900 bg-black/30 px-4 py-3 text-sm text-stone-200 outline-none placeholder:text-stone-500 focus:border-stone-800" />
									</div>

									<div class="grid gap-2">
										<label class="pl-1 text-sm tracking-wide text-stone-400"
											for="skill-instructions">Instructions</label>
										<textarea id="skill-instructions" v-model="skillFormInstructions" rows="10"
											placeholder="When the user asks about WAN instability: prioritize zabbix, syslog, and SuzieQ, correlate the timeline, and return the exact evidence."
											class="w-full rounded-md border border-stone-900 bg-black/30 px-4 py-3 text-sm text-stone-200 outline-none placeholder:text-stone-500 focus:border-stone-800" />
									</div>

									<label
										class="flex items-center gap-3 rounded-lg border border-stone-800 bg-stone-900/40 px-4 py-3 text-sm text-stone-300">
										<input v-model="skillFormEnabled" type="checkbox"
											class="h-4 w-4 accent-red-500" />
										<span>Available in slash autocomplete and chat invocation</span>
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

				<div v-if="skillsStore.isAdmin && skillsStore.reviewQueue.length > 0"
					class="rounded-2xl border border-amber-700/40 bg-amber-950/20 p-6">
					<div class="flex items-center justify-between gap-4">
						<div>
							<p class="text-lg font-semibold text-stone-200">Marketplace Review Queue</p>
							<p class="mt-1 text-sm text-stone-400">Approve or reject submitted skills before they become
								installable.</p>
						</div>
						<p class="text-xs uppercase tracking-[0.22em] text-amber-300">{{ skillsStore.reviewQueue.length
							}} pending</p>
					</div>
					<div class="mt-5 grid gap-3 lg:grid-cols-2">
						<article v-for="listing in skillsStore.reviewQueue" :key="listing.id"
							class="rounded-xl border border-stone-800 bg-stone-950/60 p-4">
							<div class="flex items-start justify-between gap-3">
								<div>
									<p class="text-base font-medium text-stone-200">{{ listing.name }}</p>
									<p class="mt-1 text-xs uppercase tracking-[0.18em] text-stone-500">/{{ listing.slug
										}}</p>
								</div>
								<span
									class="rounded-full border border-amber-700/50 px-2 py-0.5 text-[11px] uppercase tracking-wide text-amber-300">Pending</span>
							</div>
							<p v-if="listing.description" class="mt-4 text-sm leading-6 text-stone-400">{{
								listing.description }}</p>
							<div class="mt-4 flex justify-end gap-2">
								<button type="button" :disabled="skillsStore.isBusy"
									class="rounded-md px-3 py-1.5 text-sm text-red-300 transition hover:bg-red-500/10 hover:text-red-200 disabled:opacity-50"
									@click="skillsStore.rejectMarketplaceSkill(listing.id)">
									Reject
								</button>
								<button type="button" :disabled="skillsStore.isBusy"
									class="rounded-md border border-emerald-700/50 bg-emerald-950/20 px-3 py-1.5 text-sm text-emerald-200 transition hover:bg-emerald-900/40 disabled:opacity-50"
									@click="skillsStore.approveMarketplaceSkill(listing.id)">
									Approve
								</button>
							</div>
						</article>
					</div>
				</div>

				<div class="rounded-2xl border border-stone-800 bg-zinc-900/30 p-6">
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
						class="rounded-2xl border border-dashed border-stone-700 bg-zinc-900/20 px-5 py-10 text-sm text-stone-500">
						No skills yet. Use the <span class="font-medium text-stone-300">+</span> button to create your
						first one.
					</div>
					<div v-else class="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
						<article v-for="skill in skillsStore.skills" :key="skill.id"
							class="flex min-h-[15rem] flex-col rounded-xl border border-stone-800 bg-stone-950/50 p-4">
							<div class="flex items-start justify-between gap-3">
								<div>
									<p class="text-base font-medium text-stone-200">{{ skill.name }}</p>
									<p class="mt-1 text-xs tracking-[0.18em] text-stone-500">/{{ skill.slug }}</p>
								</div>
								<span
									class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-wide"
									:class="skill.enabled ? 'border-emerald-700/50 text-emerald-300' : 'border-stone-700 text-stone-400'">
									{{ skill.enabled ? 'Available' : 'Hidden' }}
								</span>
							</div>

							<div class="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-wide">
								<span class="rounded-full border border-stone-700 px-2 py-0.5 text-stone-400">{{
									marketplaceStatusLabel(skill) }}</span>
								<span v-if="skill.installed_from_listing_id"
									class="rounded-full border border-sky-700/40 px-2 py-0.5 text-sky-300">Marketplace
									Install</span>
							</div>

							<p v-if="skill.description" class="pt-5 text-sm leading-6 text-stone-500">{{
								skill.description }}</p>
							<p v-if="skill.marketplace_review_notes"
								class="mt-3 rounded-md border border-stone-800 bg-black/20 px-3 py-2 text-xs leading-5 text-stone-400">
								{{ skill.marketplace_review_notes }}
							</p>

							<div class="mt-auto flex text-xs flex-wrap justify-end gap-2 pt-5">
								<Button type="button"
									class="px-3 py-1.5 text-sm text-stone-300 transition hover:bg-stone-800/40"
									@click="openEditSkillDialog(skill)">
									Edit
								</Button>
								<Button v-if="!skill.installed_from_listing_id" type="button"
									:disabled="skillsStore.isBusy || skill.marketplace_status === 'pending'"
									class="rounded-md flex items-center gap-2 px-3 py-1.5 text-sm text-stone-400 transition hover:text-sky-200 disabled:opacity-50"
									@click="skillsStore.requestShare(skill.id)">
									{{ shareButtonLabel(skill) }} 

			                        <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6" viewBox="0 0 24 24"><!-- Icon from Material Symbols Light by Google - https://github.com/google/material-design-icons/blob/master/LICENSE --><path fill="currentColor" d="M6.616 21q-.691 0-1.153-.462T5 19.385v-8.77q0-.69.463-1.152T6.616 9H8.73v1H6.616q-.231 0-.424.192T6 10.616v8.769q0 .23.192.423t.423.192h10.77q.23 0 .423-.192t.192-.423v-8.77q0-.23-.192-.423T17.384 10H15.27V9h2.115q.691 0 1.153.463T19 10.616v8.769q0 .69-.463 1.153T17.385 21zm4.884-5.5V4.614l-2.1 2.1L8.692 6L12 2.692L15.308 6l-.708.714l-2.1-2.1V15.5z"/></svg>
								</Button>
								<Button type="button" :disabled="skillsStore.isBusy"
									class="rounded-md px-3 py-1.5 text-sm text-red-300 transition hover:bg-red-500/10 hover:text-red-200 disabled:opacity-50"
									@click="skillsStore.deleteSkill(skill.id)">
									Delete
								</Button>
							</div>
						</article>
					</div>
				</section>
			</div>
		</div>
	</div>
</template>
