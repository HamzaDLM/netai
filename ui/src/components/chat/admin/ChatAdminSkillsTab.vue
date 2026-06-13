<script setup lang="ts">
import { computed, ref } from 'vue'
import ChatAdminStatCard from './ChatAdminStatCard.vue'
import ChatAdminSearchBar from './ChatAdminSearchBar.vue'
import { Check, ChevronDown, Sparkles, TriangleAlert, WandSparkles, X } from 'lucide-vue-next'

type SummaryCard = {
	title: string
	value: string
	helper: string
	icon: typeof Sparkles
	spanClass: string
}

type ApprovalSkill = {
	id: number
	name: string
	slug: string
	description: string
	owner: string
}

type AdminSkill = {
	id: number
	name: string
	slug: string
	description: string
	owner: string
	inMarketplace: boolean
	createdAt: string
}

const searchQuery = ref('')
const approvalSearchQuery = ref('')
const approvalExpanded = ref(false)

const summaryCards: SummaryCard[] = [
	{
		title: 'Registered Skills',
		value: '1,239',
		helper: 'active skills',
		icon: Sparkles,
		spanClass: 'xl:col-span-3',
	},
	{
		title: 'Newly Created Skills',
		value: '52',
		helper: 'this week',
		icon: WandSparkles,
		spanClass: 'xl:col-span-3',
	},
	{
		title: 'Skills Requiring Approval',
		value: '129',
		helper: 'pending review',
		icon: TriangleAlert,
		spanClass: 'xl:col-span-3',
	},
]

const topSkills = ['/skill-slug1', '/skill-slug2', '/skill-slug3', '/skill-slug4', '/skill-slug5']

const approvalQueue: ApprovalSkill[] = [
	{
		id: 1,
		name: 'WAN Incident Summarizer',
		slug: 'wan-incident-summary',
		description: 'Condenses noisy incident threads into a concise outage summary for on-call handoff.',
		owner: 'Maya Patel',
	},
	{
		id: 2,
		name: 'BGP Drift Watcher',
		slug: 'bgp-drift-watcher',
		description: 'Flags route-policy and neighbor drift patterns before they become customer-facing.',
		owner: 'Daniel Kim',
	},
	{
		id: 3,
		name: 'Change Window Prep',
		slug: 'change-window-prep',
		description: 'Builds a pre-change checklist with config, incident, and monitoring context.',
		owner: 'Julien Moreau',
	},
]

const skills: AdminSkill[] = [
	{
		id: 1,
		name: 'Edge Rollback Guide',
		slug: 'edge-rollback-guide',
		description: 'Provides rollback steps and dependency checks for failed edge deployments.',
		owner: 'Maya Patel',
		inMarketplace: true,
		createdAt: 'May 14, 2026',
	},
	{
		id: 2,
		name: 'BGP Session Audit',
		slug: 'bgp-session-audit',
		description: 'Audits peer state, timer mismatches, and route-policy discrepancies.',
		owner: 'Noah Fischer',
		inMarketplace: false,
		createdAt: 'May 13, 2026',
	},
	{
		id: 3,
		name: 'Incident Timeline Builder',
		slug: 'incident-timeline-builder',
		description: 'Builds an investigation timeline from incidents, alerts, and syslog evidence.',
		owner: 'Amina Hassan',
		inMarketplace: true,
		createdAt: 'May 11, 2026',
	},
	{
		id: 4,
		name: 'Config Drift Lens',
		slug: 'config-drift-lens',
		description: 'Compares candidate and running config snapshots for operationally relevant drift.',
		owner: 'Daniel Kim',
		inMarketplace: false,
		createdAt: 'May 9, 2026',
	},
	{
		id: 5,
		name: 'Service Blast Radius',
		slug: 'service-blast-radius',
		description: 'Maps impacted devices and downstream services when an incident is in flight.',
		owner: 'Camila Torres',
		inMarketplace: true,
		createdAt: 'May 8, 2026',
	},
	{
		id: 6,
		name: 'Maintenance Comms Draft',
		slug: 'maintenance-comms-draft',
		description: 'Drafts stakeholder-facing maintenance notes from change request context.',
		owner: 'Julien Moreau',
		inMarketplace: false,
		createdAt: 'May 7, 2026',
	},
]

const filteredApprovalQueue = computed(() => {
	const query = approvalSearchQuery.value.trim().toLowerCase()
	if (!query) return approvalQueue

	return approvalQueue.filter(skill =>
		[skill.name, skill.slug, skill.description, skill.owner].join(' ').toLowerCase().includes(query)
	)
})

const filteredSkills = computed(() => {
	const query = searchQuery.value.trim().toLowerCase()
	if (!query) return skills

	return skills.filter(skill =>
		[
			skill.name,
			skill.slug,
			skill.description,
			skill.owner,
			skill.inMarketplace ? 'marketplace' : 'private',
			skill.createdAt,
		]
			.join(' ')
			.toLowerCase()
			.includes(query)
	)
})
</script>

<template>
	<section class="flex min-w-0 min-h-0 flex-1 flex-col overflow-hidden">
		<div class="px-6 py-4 border-b border-stone-900">
			<p class="text-xl font-semibold text-stone-100">Skills</p>
			<p class="mt-1 text-sm text-stone-500">
				Frontend mock of skill inventory, approvals, and marketplace state.
			</p>
		</div>

		<div class="flex flex-col flex-1 min-h-0 gap-4 p-6">
			<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-9">
				<ChatAdminStatCard
					v-for="card in summaryCards"
					:key="card.title"
					:class="card.spanClass"
					:title="card.title"
					:value="card.value"
					:helper="card.helper"
					:icon="card.icon"
					:extra-lines="card.title === 'Top 5 Skills' ? topSkills : undefined"
					:value-class="card.title === 'Top 5 Skills' ? 'text-[1.2rem]' : ''" />
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
									<p class="mt-1 text-sm text-stone-200">{{ skill.owner }}</p>
									<div class="flex justify-end gap-2 mt-5">
										<button
											type="button"
											class="inline-flex items-center gap-1.5 rounded-full border border-white/8 bg-white/[0.04] px-3 py-1.5 text-sm text-red-500 transition hover:bg-white/[0.06]">
											<X class="h-3.5 w-3.5" />
											Reject
										</button>
										<button
											type="button"
											class="inline-flex items-center gap-1.5 rounded-full border border-white/8 bg-white/[0.04] px-3 py-1.5 text-sm text-emerald-500 transition hover:bg-white/[0.06]">
											<Check class="h-3.5 w-3.5" />
											Approve
										</button>
									</div>
								</article>

								<div
									v-if="filteredApprovalQueue.length === 0"
									class="rounded-2xl border border-dashed border-white/8 bg-white/[0.02] px-5 py-10 text-center text-sm text-stone-500 xl:col-span-3">
									No pending skills match that search.
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
									:class="skill.inMarketplace ? 'border-sky-700/30 bg-sky-500/10 text-sky-200' : 'border-white/8 bg-white/[0.04] text-stone-300'">
									{{ skill.inMarketplace ? 'Marketplace' : 'Private' }}
								</span>
							</div>

							<p class="mt-4 text-sm leading-6 text-stone-400">{{ skill.description }}</p>

							<div class="grid gap-3 mt-4 sm:grid-cols-2">
								<div>
									<p class="text-[10px] font-semibold uppercase tracking-[0.22em] text-stone-500">Owner</p>
									<p class="mt-1.5 text-sm text-stone-200">{{ skill.owner }}</p>
								</div>
								<div>
									<p class="text-[10px] font-semibold uppercase tracking-[0.22em] text-stone-500">Created At</p>
									<p class="mt-1.5 text-sm text-stone-200">{{ skill.createdAt }}</p>
								</div>
							</div>
						</article>

						<div
							v-if="filteredSkills.length === 0"
							class="rounded-2xl border border-dashed border-white/8 bg-white/[0.02] px-5 py-10 text-center text-sm text-stone-500 xl:col-span-3">
							No skills match that search.
						</div>
					</div>
				</div>
			</div>
		</div>
	</section>
</template>
