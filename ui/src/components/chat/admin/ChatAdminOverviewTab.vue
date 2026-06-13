<script setup lang="ts">
import { computed } from 'vue'
import ChatAdminStatCard from './ChatAdminStatCard.vue'
import {
	AlertTriangle,
	Clock3,
	MessageSquare,
	MessagesSquare,
	ThumbsDown,
} from 'lucide-vue-next'

type OverviewCard = {
	title: string
	value: string
	helper: string
	icon: typeof MessageSquare
	spanClass: string
}

type UsagePoint = {
	label: string
	messages: number
}

const overviewCards: OverviewCard[] = [
	{
		title: 'Conversations',
		value: '324',
		helper: 'this week',
		icon: MessageSquare,
		spanClass: 'xl:col-span-4',
	},
	{
		title: 'Messages',
		value: '4,982',
		helper: 'user questions this week',
		icon: MessagesSquare,
		spanClass: 'xl:col-span-4',
	},
	{
		title: 'Failed Toolcalls',
		value: '30/100',
		helper: 'this week',
		icon: AlertTriangle,
		spanClass: 'xl:col-span-4',
	},
	{
		title: 'Avg Latency',
		value: '3.2s',
		helper: 'weekly average',
		icon: Clock3,
		spanClass: 'xl:col-span-6',
	},
	{
		title: 'Negative Feedback',
		value: '2.3%',
		helper: 'of rated answers',
		icon: ThumbsDown,
		spanClass: 'xl:col-span-6',
	},
]

const usageSeries: UsagePoint[] = [
	{ label: 'Mon', messages: 582 },
	{ label: 'Tue', messages: 701 },
	{ label: 'Wed', messages: 668 },
	{ label: 'Thu', messages: 742 },
	{ label: 'Fri', messages: 809 },
	{ label: 'Sat', messages: 633 },
	{ label: 'Sun', messages: 847 },
]

const weeklyMessageTotal = computed(() =>
	usageSeries.reduce((total, point) => total + point.messages, 0).toLocaleString()
)
const averageDailyMessages = computed(() =>
	Math.round(usageSeries.reduce((total, point) => total + point.messages, 0) / usageSeries.length).toLocaleString()
)
</script>

<template>
	<section class="relative flex min-w-0 flex-1 flex-col overflow-auto">
		<div class="absolute inset-0 overflow-hidden pointer-events-none">
			<div class="absolute left-[-8%] top-[-8%] h-72 w-72 rounded-full bg-cyan-500/8 blur-3xl" />
			<div class="absolute bottom-[-12%] right-[-6%] h-80 w-80 rounded-full bg-emerald-500/8 blur-3xl" />
		</div>

		<div class="relative px-6 py-4 border-b border-stone-900">
			<p class="text-xl font-semibold text-stone-100">Overview</p>
			<p class="mt-1 text-sm text-stone-500">
				Mock operational summary for the last 7 days. Frontend example data only.
			</p>
		</div>

		<div class="relative px-8 py-8 space-y-8">
			<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-12">
				<ChatAdminStatCard
					v-for="card in overviewCards"
					:key="card.title"
					:class="card.spanClass"
					:title="card.title"
					:value="card.value"
					:helper="card.helper"
					:icon="card.icon" />
			</div>

			<div class="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,0.95fr)]">
				<article class="rounded-[8px] border border-white/7 bg-[#0b0b0b]/90 p-6 shadow-[0_20px_70px_rgba(0,0,0,0.35)]">
					<div class="flex flex-col gap-5 pb-5 border-b border-white/6 lg:flex-row lg:items-end lg:justify-between">
						<div>
							<p class="text-[11px] font-semibold uppercase tracking-[0.28em] text-stone-500">Usage per Time</p>
							<h2 class="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-100">Message volume over the last week</h2>
						</div>
						<div class="grid grid-cols-2 gap-6 text-sm">
							<div>
								<p class="text-stone-500">Weekly total</p>
								<p class="mt-1 text-lg font-semibold text-stone-100">{{ weeklyMessageTotal }}</p>
							</div>
							<div>
								<p class="text-stone-500">Daily average</p>
								<p class="mt-1 text-lg font-semibold text-stone-100">{{ averageDailyMessages }}</p>
							</div>
						</div>
					</div>
				</article>

				<article class="rounded-[8px] border border-white/7 bg-[#0b0b0b]/90 p-6 shadow-[0_20px_70px_rgba(0,0,0,0.35)]">
					<div class="pb-5 border-b border-white/6">
						<p class="text-[11px] font-semibold uppercase tracking-[0.28em] text-stone-500">Usage per Region</p>
						<h2 class="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-100">Regional distribution</h2>
					</div>
				</article>
			</div>
		</div>
	</section>
</template>
