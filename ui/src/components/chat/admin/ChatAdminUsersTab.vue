<script setup lang="ts">
import { computed, ref } from 'vue'
import ChatAdminStatCard from './ChatAdminStatCard.vue'
import ChatAdminSearchBar from './ChatAdminSearchBar.vue'
import { UserPlus, Users } from 'lucide-vue-next'

type UserCard = {
	id: number
	name: string
	ssoNumber: string
	entitlements: string[]
	lastConnection: string
	role: string
	country: string
}

type SummaryCard = {
	title: string
	value: string
	helper: string
	icon: typeof Users
}

const registeredUsers = '1,284'
const newUsersThisWeek = '47'
const searchQuery = ref('')

const summaryCards: SummaryCard[] = [
	{
		title: 'Registered Users',
		value: registeredUsers,
		helper: 'active directory accounts',
		icon: Users,
	},
	{
		title: 'New Users',
		value: newUsersThisWeek,
		helper: 'this week',
		icon: UserPlus,
	},
]

const users: UserCard[] = [
	{
		id: 1,
		name: 'Maya Patel',
		ssoNumber: 'SSO-10482',
		entitlements: ['NetOps', 'Zabbix', 'Bitbucket'],
		lastConnection: 'Today, 09:42',
		role: 'Network Engineer',
		country: 'United Kingdom',
	},
	{
		id: 2,
		name: 'Julien Moreau',
		ssoNumber: 'SSO-11807',
		entitlements: ['Servicenow', 'Syslog'],
		lastConnection: 'Today, 08:11',
		role: 'Support Lead',
		country: 'France',
	},
	{
		id: 3,
		name: 'Camila Torres',
		ssoNumber: 'SSO-12091',
		entitlements: ['NetOps', 'Topology', 'Datamodel'],
		lastConnection: 'Yesterday, 18:27',
		role: 'Infrastructure Architect',
		country: 'Brazil',
	},
	{
		id: 4,
		name: 'Daniel Kim',
		ssoNumber: 'SSO-12344',
		entitlements: ['Bitbucket', 'Config Diff'],
		lastConnection: 'Yesterday, 16:05',
		role: 'Platform Engineer',
		country: 'Singapore',
	},
	{
		id: 5,
		name: 'Amina Hassan',
		ssoNumber: 'SSO-12713',
		entitlements: ['Servicenow', 'Zabbix', 'Incidents'],
		lastConnection: 'May 14, 21:14',
		role: 'NOC Analyst',
		country: 'United Arab Emirates',
	},
	{
		id: 6,
		name: 'Noah Fischer',
		ssoNumber: 'SSO-13022',
		entitlements: ['Syslog', 'NetOps'],
		lastConnection: 'May 14, 14:32',
		role: 'SRE',
		country: 'Germany',
	},
]

const filteredUsers = computed(() => {
	const query = searchQuery.value.trim().toLowerCase()
	if (!query) return users

	return users.filter(user =>
		[
			user.name,
			user.ssoNumber,
			user.role,
			user.country,
			...user.entitlements,
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
			<p class="text-xl font-semibold text-stone-100">Users</p>
			<p class="mt-1 text-sm text-stone-500">
				Frontend mock of user activity and account summaries.
			</p>
		</div>

		<div class="flex flex-col flex-1 min-h-0 gap-6 p-6">
			<div class="grid gap-4 lg:grid-cols-2">
				<ChatAdminStatCard
					v-for="card in summaryCards"
					:key="card.title"
					:title="card.title"
					:value="card.value"
					:helper="card.helper"
					:icon="card.icon" />
			</div>

			<div class="flex flex-col flex-1 min-h-0">
				<div class="flex flex-col gap-4 py-3 mx-2 border-b border-white/6 lg:flex-row lg:items-end lg:justify-between">
					<div>
						<h2 class="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-100">User Directory</h2>
					</div>

					<ChatAdminSearchBar
						v-model="searchQuery"
						placeholder="Search by name, SSO, entitlement, role, or country"
						max-width-class="max-w-md" />
				</div>

				<div class="flex-1 min-h-0 py-6 overflow-y-auto">
					<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
						<article
							v-for="user in filteredUsers"
							:key="user.id"
							class="rounded-lg border border-white/7 bg-white/[0.025] p-4 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
							<div class="flex items-start justify-between gap-3 pb-3 border-b border-white/6">
								<div class="min-w-0">
									<p class="truncate text-base font-semibold tracking-[-0.03em] text-stone-100">{{ user.name }}</p>
									<p class="mt-1 text-xs text-stone-500">{{ user.ssoNumber }}</p>
								</div>
								<span class="shrink-0 rounded-full border border-white/8 bg-white/[0.04] px-2.5 py-1 text-[11px] font-medium text-stone-300">
									{{ user.country }}
								</span>
							</div>

							<div class="grid gap-3 mt-4">
								<div class="flex justify-between">
									<div>
										<p class="text-[10px] font-semibold uppercase tracking-[0.22em] text-stone-500">Role</p>
										<p class="mt-1.5 text-sm text-stone-200">{{ user.role }}</p>
									</div>
									<div>
										<p class="text-[10px] font-semibold uppercase tracking-[0.22em] text-stone-500">Last Connection</p>
										<p class="mt-1.5 text-sm text-stone-200">{{ user.lastConnection }}</p>
									</div>
								</div>

								<div>
									<p class="text-[10px] font-semibold uppercase tracking-[0.22em] text-stone-500">Entitlements</p>
									<div class="flex flex-wrap gap-2 mt-2">
										<span
											v-for="entitlement in user.entitlements"
											:key="`${user.id}-${entitlement}`"
											class="rounded-full border border-white/8 bg-white/[0.04] px-2.5 py-1 text-[11px] text-stone-300">
											{{ entitlement }}
										</span>
									</div>
								</div>
							</div>
						</article>

						<div
							v-if="filteredUsers.length === 0"
							class="rounded-2xl border border-dashed border-white/8 bg-white/[0.02] px-5 py-10 text-center text-sm text-stone-500 xl:col-span-3">
							No users match that search.
						</div>
					</div>
				</div>
			</div>
		</div>
	</section>
</template>
