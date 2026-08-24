<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Check, ChevronDown, RefreshCw, Sparkles, TriangleAlert, WandSparkles, X } from 'lucide-vue-next'
import ChatAdminStatCard from './ChatAdminStatCard.vue'
import ChatAdminSearchBar from './ChatAdminSearchBar.vue'
import { toast } from '@/components/ui/toast'
import skillsService from '@/services/skills.service'
import type { AdminSkill, AdminSkillMarketplaceListing, AdminSkillStats, SkillMarketplaceStatus } from '@/types/skill.type'

type SummaryCard = {
	title: string
	value: string
	helper: string
	icon: typeof Sparkles
	spanClass: string
}

const EMPTY_STATS: AdminSkillStats = {
	registered_skills: 0,
	enabled_skills: 0,
	created_last_7_days: 0,
	pending_approvals: 0,
	marketplace_skills: 0,
}

const searchQuery = ref('')
const approvalSearchQuery = ref('')
const approvalExpanded = ref(false)
const skills = ref<AdminSkill[]>([])
const approvalQueue = ref<AdminSkillMarketplaceListing[]>([])
const stats = ref<AdminSkillStats>({ ...EMPTY_STATS })
const isLoading = ref(true)
const busyListingId = ref<number | null>(null)

const summaryCards = computed<SummaryCard[]>(() => [
	{
		title: 'Registered Skills',
		value: stats.value.registered_skills.toLocaleString(),
		helper: `${stats.value.enabled_skills.toLocaleString()} enabled`,
		icon: Sparkles,
		spanClass: 'xl:col-span-3',
	},
	{
		title: 'Newly Created Skills',
		value: stats.value.created_last_7_days.toLocaleString(),
		helper: 'last 7 days',
		icon: WandSparkles,
		spanClass: 'xl:col-span-3',
	},
	{
		title: 'Skills Requiring Approval',
		value: stats.value.pending_approvals.toLocaleString(),
		helper: 'pending review',
		icon: TriangleAlert,
		spanClass: 'xl:col-span-3',
	},
])

const filteredApprovalQueue = computed(() => {
	const query = approvalSearchQuery.value.trim().toLowerCase()
	if (!query) return approvalQueue.value
	return approvalQueue.value.filter(skill => [skill.name, skill.slug, skill.description, skill.owner_username].join(' ').toLowerCase().includes(query))
})

const filteredSkills = computed(() => {
	const query = searchQuery.value.trim().toLowerCase()
	if (!query) return skills.value
	return skills.value.filter(skill => [skill.name, skill.slug, skill.description, skill.owner_username, skill.marketplace_status ?? 'private', skill.enabled ? 'enabled' : 'disabled', skill.created_at].join(' ').toLowerCase().includes(query))
})

async function loadAdminSkills() {
	isLoading.value = true
	try {
		const { data } = await skillsService.getAdminBootstrap()
		skills.value = data.skills
		approvalQueue.value = data.review_queue
		stats.value = data.stats
	} catch {
		toast({ title: 'Unable to load admin skills data', variant: 'destructive' })
	} finally {
		isLoading.value = false
	}
}

async function reviewSkill(listingId: number, decision: 'approve' | 'reject') {
	if (busyListingId.value !== null) return
	busyListingId.value = listingId
	try {
		if (decision === 'approve') await skillsService.approveMarketplaceSkill(listingId)
		else await skillsService.rejectMarketplaceSkill(listingId)
		await loadAdminSkills()
		toast({ title: decision === 'approve' ? 'Skill approved' : 'Skill rejected' })
	} catch {
		toast({ title: `Unable to ${decision} skill`, variant: 'destructive' })
	} finally {
		busyListingId.value = null
	}
}

function marketplaceLabel(status: SkillMarketplaceStatus | null): string {
	if (status === 'approved') return 'Marketplace'
	if (status === 'pending') return 'Pending'
	if (status === 'rejected') return 'Rejected'
	return 'Private'
}

function formattedDate(value: string): string {
	return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
}

onMounted(loadAdminSkills)
</script>

<template>
	<section class="flex min-w-0 min-h-0 flex-1 flex-col overflow-hidden">
		<div class="flex items-center justify-between gap-4 px-6 py-4 border-b border-stone-900">
			<div><p class="text-xl font-semibold text-stone-100">Skills</p><p class="mt-1 text-sm text-stone-500">Cross-user skill inventory, marketplace approvals, and live publication state.</p></div>
			<button type="button" class="inline-flex h-9 items-center gap-2 rounded-md border border-stone-800 px-3 text-sm text-stone-400 transition hover:border-stone-600 hover:text-stone-200 disabled:opacity-40" :disabled="isLoading" @click="loadAdminSkills"><RefreshCw class="h-3.5 w-3.5" :class="isLoading ? 'animate-spin' : ''" />Refresh</button>
		</div>

		<div class="flex flex-col flex-1 min-h-0 gap-4 p-6">
			<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-9" :class="isLoading ? 'animate-pulse opacity-60' : ''">
				<ChatAdminStatCard
					v-for="card in summaryCards"
					:key="card.title"
					:class="card.spanClass"
					:title="card.title"
					:value="card.value"
					:helper="card.helper"
					:icon="card.icon" />
			</div>

			<div class="flex flex-col flex-1 min-h-0">
				<div class="py-5 border-b border-white/6">
					<div class="flex flex-col gap-6">
						<div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
							<div>
								<p class="text-[11px] font-semibold uppercase tracking-[0.28em] text-stone-500">Marketplace Review Queue</p>
								<h2 class="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-100">Skill approvals</h2>
								<p class="mt-2 text-sm text-stone-500">{{ filteredApprovalQueue.length }} pending skills shown</p>
							</div>

							<button
								type="button"
								class="inline-flex items-center gap-2 self-start rounded-full border border-white/8 bg-white/[0.03] px-4 py-2 text-sm text-stone-300 transition hover:bg-white/[0.05]"
								@click="approvalExpanded = !approvalExpanded">
								<ChevronDown class="w-4 h-4 transition" :class="approvalExpanded ? 'rotate-180' : ''" />
								{{ approvalExpanded ? 'Hide approvals' : 'Show approvals' }}
							</button>
						</div>

						<div v-if="approvalExpanded" class="grid gap-5">
							<ChatAdminSearchBar
								v-model="approvalSearchQuery"
								placeholder="Search pending skills"
								max-width-class="max-w-md" />

							<div class="grid gap-4 xl:grid-cols-3">
								<article
									v-for="skill in filteredApprovalQueue"
									:key="skill.id"
									class="rounded-2xl border border-white/7 bg-white/[0.025] p-4">
									<div class="flex items-start justify-between gap-3">
										<div class="min-w-0">
											<p class="truncate text-base font-semibold tracking-[-0.03em] text-stone-100">{{ skill.name }}</p>
											<p class="mt-1 text-xs text-stone-500">/{{ skill.slug }}</p>
										</div>
										<span class="shrink-0 rounded-full border border-white/8 bg-white/[0.04] px-2.5 py-1 text-[11px] font-medium text-stone-300">
											Pending
										</span>
									</div>
									<p class="mt-4 text-sm leading-6 text-stone-400">{{ skill.description }}</p>
									<p class="mt-4 text-xs uppercase tracking-[0.18em] text-stone-500">Owner</p>
									<p class="mt-1 text-sm text-stone-200">{{ skill.owner_username }}</p>
									<div class="flex justify-end gap-2 mt-5">
										<button
											type="button"
											class="inline-flex items-center gap-1.5 rounded-full border border-white/8 bg-white/[0.04] px-3 py-1.5 text-sm text-red-500 transition hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-40"
											:disabled="busyListingId !== null"
											@click="reviewSkill(skill.id, 'reject')">
											<X class="h-3.5 w-3.5" />
											Reject
										</button>
										<button
											type="button"
											class="inline-flex items-center gap-1.5 rounded-full border border-white/8 bg-white/[0.04] px-3 py-1.5 text-sm text-emerald-500 transition hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-40"
											:disabled="busyListingId !== null"
											@click="reviewSkill(skill.id, 'approve')">
											<Check class="h-3.5 w-3.5" />
											Approve
										</button>
									</div>
								</article>

								<div
									v-if="filteredApprovalQueue.length === 0"
									class="rounded-2xl border border-dashed border-white/8 bg-white/[0.02] px-5 py-10 text-center text-sm text-stone-500 xl:col-span-3">
									{{ isLoading ? 'Loading pending skills…' : 'No pending skills match that search.' }}
								</div>
							</div>
						</div>
					</div>
				</div>

				<div class="flex-1 min-h-0 px-0 py-6 overflow-y-auto">
					<div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
						<div>
							<p class="text-[11px] font-semibold uppercase tracking-[0.28em] text-stone-500">Skill Directory</p>
							<h2 class="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-100">Published and private skills</h2>
							<p class="mt-2 text-sm text-stone-500">{{ filteredSkills.length }} skills shown</p>
						</div>

						<ChatAdminSearchBar
							v-model="searchQuery"
							placeholder="Search by name, owner, marketplace, or date"
							max-width-class="max-w-md" />
					</div>

					<div class="grid gap-4 mt-6 md:grid-cols-2 xl:grid-cols-3">
						<article
							v-for="skill in filteredSkills"
							:key="skill.id"
							class="rounded-2xl border border-white/7 bg-white/[0.025] p-4 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
							<div class="flex items-start justify-between gap-3 pb-3 border-b border-white/6">
								<div class="min-w-0">
									<p class="truncate text-base font-semibold tracking-[-0.03em] text-stone-100">{{ skill.name }}</p>
									<p class="mt-1 text-xs text-stone-500">/{{ skill.slug }}</p>
								</div>
								<span
									class="shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium"
									:class="skill.marketplace_status === 'approved' ? 'border-sky-700/30 bg-sky-500/10 text-sky-200' : skill.marketplace_status === 'pending' ? 'border-amber-700/30 bg-amber-500/10 text-amber-200' : skill.marketplace_status === 'rejected' ? 'border-red-700/30 bg-red-500/10 text-red-200' : 'border-white/8 bg-white/[0.04] text-stone-300'">
									{{ marketplaceLabel(skill.marketplace_status) }}
								</span>
							</div>

							<p class="mt-4 text-sm leading-6 text-stone-400">{{ skill.description }}</p>

							<div class="grid gap-3 mt-4 sm:grid-cols-2">
								<div>
									<p class="text-[10px] font-semibold uppercase tracking-[0.22em] text-stone-500">Owner</p>
									<p class="mt-1.5 text-sm text-stone-200">{{ skill.owner_username }}</p>
								</div>
								<div>
									<p class="text-[10px] font-semibold uppercase tracking-[0.22em] text-stone-500">Created At</p>
									<p class="mt-1.5 text-sm text-stone-200">{{ formattedDate(skill.created_at) }}</p>
								</div>
							</div>
							<div class="mt-4 flex items-center gap-2 text-xs"><span class="h-1.5 w-1.5 rounded-full" :class="skill.enabled ? 'bg-emerald-400' : 'bg-stone-600'" /><span :class="skill.enabled ? 'text-emerald-400' : 'text-stone-600'">{{ skill.enabled ? 'Enabled' : 'Disabled' }}</span></div>
						</article>

						<div
							v-if="filteredSkills.length === 0"
							class="rounded-2xl border border-dashed border-white/8 bg-white/[0.02] px-5 py-10 text-center text-sm text-stone-500 xl:col-span-3">
							{{ isLoading ? 'Loading skill inventory…' : 'No skills match that search.' }}
						</div>
					</div>
				</div>
			</div>
		</div>
	</section>
</template>
