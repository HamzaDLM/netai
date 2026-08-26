<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { MessageSquare, RefreshCw, UserPlus, Users } from 'lucide-vue-next'
import ChatAdminSearchBar from './ChatAdminSearchBar.vue'
import ChatAdminStatCard from './ChatAdminStatCard.vue'
import { toast } from '@/components/ui/toast'
import usersService from '@/services/users.service'
import type { AdminUser, AdminUserRole, AdminUserStats } from '@/types/user.type'

type SummaryCard = {
	title: string
	value: string
	helper: string
	icon: typeof Users
}

const EMPTY_STATS: AdminUserStats = {
	registered_users: 0,
	new_users_last_7_days: 0,
}

const searchQuery = ref('')
const users = ref<AdminUser[]>([])
const stats = ref<AdminUserStats>({ ...EMPTY_STATS })
const isLoading = ref(true)

const summaryCards = computed<SummaryCard[]>(() => [
	{
		title: 'Registered Users',
		value: stats.value.registered_users.toLocaleString(),
		helper: 'NetAI application accounts',
		icon: Users,
	},
	{
		title: 'New Users',
		value: stats.value.new_users_last_7_days.toLocaleString(),
		helper: 'last 7 days',
		icon: UserPlus,
	},
])

const filteredUsers = computed(() => {
	const query = searchQuery.value.trim().toLowerCase()
	if (!query) return users.value
	return users.value.filter(user => [user.username, String(user.id), user.role, roleLabel(user.role)].join(' ').toLowerCase().includes(query))
})

function roleLabel(role: AdminUserRole): string {
	if (role === 'superuser') return 'Superuser'
	if (role === 'admin') return 'Admin'
	return 'User'
}

function roleClass(role: AdminUserRole): string {
	if (role === 'superuser') return 'border-red-500/25 bg-red-500/10 text-red-300'
	if (role === 'admin') return 'border-amber-500/25 bg-amber-500/10 text-amber-300'
	return 'border-white/8 bg-white/[0.04] text-stone-300'
}

function formattedDate(value: string): string {
	return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
}

function formattedActivity(value: string | null | undefined): string {
	if (!value) return 'No activity yet'
	return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

async function loadUsers(): Promise<void> {
	isLoading.value = true
	try {
		const { data } = await usersService.getAdminBootstrap()
		users.value = data.users
		stats.value = data.stats
	} catch {
		toast({ title: 'Unable to load users', variant: 'destructive' })
	} finally {
		isLoading.value = false
	}
}

onMounted(loadUsers)
</script>

<template>
	<section class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
		<div class="flex items-center justify-between gap-4 border-b border-stone-900 px-6 py-4">
			<div>
				<p class="text-xl font-semibold text-stone-100">Users</p>
				<p class="mt-1 text-sm text-stone-500">NetAI accounts, application roles, and recorded conversation activity.</p>
			</div>
			<button type="button" class="inline-flex h-9 items-center gap-2 rounded-md border border-stone-800 px-3 text-sm text-stone-400 transition hover:border-stone-600 hover:text-stone-200 disabled:opacity-40" :disabled="isLoading" @click="loadUsers"><RefreshCw class="h-3.5 w-3.5" :class="isLoading ? 'animate-spin' : ''" />Refresh</button>
		</div>

		<div class="flex min-h-0 flex-1 flex-col gap-6 p-6">
			<div class="grid gap-4 lg:grid-cols-2" :class="isLoading ? 'animate-pulse opacity-60' : ''">
				<ChatAdminStatCard v-for="card in summaryCards" :key="card.title" :title="card.title" :value="card.value" :helper="card.helper" :icon="card.icon" />
			</div>

			<div class="flex min-h-0 flex-1 flex-col">
				<div class="mx-2 flex flex-col gap-4 border-b border-white/6 py-3 lg:flex-row lg:items-end lg:justify-between">
					<div>
						<h2 class="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-100">User Directory</h2>
						<p class="mt-1 text-sm text-stone-500">{{ filteredUsers.length.toLocaleString() }} users shown</p>
					</div>
					<ChatAdminSearchBar v-model="searchQuery" placeholder="Search by username, ID, or application role" max-width-class="max-w-md" />
				</div>

				<div class="min-h-0 flex-1 overflow-y-auto py-6">
					<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
						<article v-for="user in filteredUsers" :key="user.id" class="rounded-lg border border-white/7 bg-white/[0.025] p-4 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
							<div class="flex items-start justify-between gap-3 border-b border-white/6 pb-3">
								<div class="min-w-0">
									<p class="truncate text-base font-semibold tracking-[-0.03em] text-stone-100">{{ user.username }}</p>
									<p class="mt-1 font-mono text-xs text-stone-500">User #{{ user.id }}</p>
								</div>
								<span class="shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium" :class="roleClass(user.role)">{{ roleLabel(user.role) }}</span>
							</div>

							<div class="mt-4 grid grid-cols-2 gap-4">
								<div class="col-span-2">
									<p class="text-[10px] font-semibold uppercase tracking-[0.22em] text-stone-500">Last Activity</p>
									<p class="mt-1.5 text-sm text-stone-200">{{ formattedActivity(user.last_activity_at) }}</p>
								</div>
								<div>
									<p class="text-[10px] font-semibold uppercase tracking-[0.22em] text-stone-500">Joined</p>
									<p class="mt-1.5 text-sm text-stone-200">{{ formattedDate(user.created_at) }}</p>
								</div>
								<div>
									<p class="text-[10px] font-semibold uppercase tracking-[0.22em] text-stone-500">Usage</p>
									<p class="mt-1.5 flex items-center gap-1.5 text-sm text-stone-200"><MessageSquare class="h-3.5 w-3.5 text-stone-500" />{{ user.user_message_count.toLocaleString() }} questions</p>
								</div>
							</div>
							<p class="mt-4 border-t border-white/6 pt-3 text-xs text-stone-500">{{ user.conversation_count.toLocaleString() }} conversations</p>
						</article>

						<div v-if="filteredUsers.length === 0" class="rounded-2xl border border-dashed border-white/8 bg-white/[0.02] px-5 py-10 text-center text-sm text-stone-500 xl:col-span-3">
							{{ isLoading ? 'Loading users…' : 'No users match that search.' }}
						</div>
					</div>
				</div>
			</div>
		</div>
	</section>
</template>
