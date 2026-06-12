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

type RegionPoint = {
	label: string
	value: number
	color: string
	dotClass: string
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

const regionSeries: RegionPoint[] = [
	{
		label: 'EMEA',
		value: 46,
		color: '#22d3ee',
		dotClass: 'bg-cyan-400',
	},
	{
		label: 'AMER',
		value: 34,
		color: '#34d399',
		dotClass: 'bg-emerald-400',
	},
	{
		label: 'APAC',
		value: 20,
		color: '#f59e0b',
		dotClass: 'bg-amber-400',
	},
]

const usageMax = computed(() => Math.max(...usageSeries.map(point => point.messages), 1))
const usageBars = computed(() =>
	usageSeries.map(point => ({
		...point,
		height: Math.max(14, Math.round((point.messages / usageMax.value) * 220)),
	}))
)
const weeklyMessageTotal = computed(() =>
	usageSeries.reduce((total, point) => total + point.messages, 0).toLocaleString()
)
const averageDailyMessages = computed(() =>
	Math.round(usageSeries.reduce((total, point) => total + point.messages, 0) / usageSeries.length).toLocaleString()
)
const chartGuides = [25, 50, 75, 100]

const donutSegments = computed(() => {
	const radius = 54
	const circumference = 2 * Math.PI * radius
	let offset = 0

	return regionSeries.map(region => {
		const segmentLength = (region.value / 100) * circumference
		const segment = {
			...region,
			radius,
			circumference,
			dashArray: `${segmentLength} ${circumference - segmentLength}`,
			dashOffset: -offset,
		}
		offset += segmentLength
		return segment
	})
})
</script>

<template>
	<section class="relative flex min-w-0 flex-1 flex-col overflow-auto bg-[#050505]">
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
				<article class="rounded-[28px] border border-white/7 bg-[#0b0b0b]/90 p-6 shadow-[0_20px_70px_rgba(0,0,0,0.35)]">
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

					<div class="mt-6 rounded-[24px] border border-white/6 bg-gradient-to-b from-white/[0.03] to-white/[0.015] p-5">
						<div class="relative h-[340px]">
							<div
								v-for="guide in chartGuides"
								:key="guide"
								class="absolute inset-x-0 border-t border-dashed border-white/6"
								:style="{ bottom: `${guide}%` }" />
							<div class="absolute inset-0 grid grid-cols-7 gap-4">
								<div
									v-for="bar in usageBars"
									:key="bar.label"
									class="flex flex-col justify-end min-w-0">
									<div class="mb-3 text-center text-[11px] text-stone-500">{{ bar.messages }}</div>
									<div
										class="relative overflow-hidden rounded-[14px] border border-white/6 bg-gradient-to-t from-cyan-500 via-sky-400 to-emerald-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.18)]"
										:style="{ height: `${bar.height}px` }">
										<div class="absolute h-12 rounded-full inset-x-2 top-2 bg-white/15 blur-lg" />
									</div>
									<div class="mt-3 text-sm font-medium text-center text-stone-300">{{ bar.label }}</div>
								</div>
							</div>
						</div>
					</div>
				</article>

				<article class="rounded-[28px] border border-white/7 bg-[#0b0b0b]/90 p-6 shadow-[0_20px_70px_rgba(0,0,0,0.35)]">
					<div class="pb-5 border-b border-white/6">
						<p class="text-[11px] font-semibold uppercase tracking-[0.28em] text-stone-500">Usage per Region</p>
						<h2 class="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-100">Regional distribution</h2>
					</div>

					<div class="grid gap-6 mt-6">
						<div class="relative w-56 h-56 mx-auto">
							<svg viewBox="0 0 140 140" class="w-full h-full -rotate-90">
								<circle
									cx="70"
									cy="70"
									r="54"
									fill="none"
									stroke="rgba(255,255,255,0.08)"
									stroke-width="14" />
								<circle
									v-for="segment in donutSegments"
									:key="segment.label"
									cx="70"
									cy="70"
									:r="segment.radius"
									fill="none"
									:stroke="segment.color"
									stroke-linecap="round"
									stroke-width="14"
									:stroke-dasharray="segment.dashArray"
									:stroke-dashoffset="segment.dashOffset" />
							</svg>
							<div class="absolute inset-[22%] rounded-full border border-white/6 bg-black/40 backdrop-blur-md" />
							<div class="absolute inset-0 flex flex-col items-center justify-center">
								<p class="text-[11px] font-semibold uppercase tracking-[0.24em] text-stone-500">7 day split</p>
								<p class="mt-2 text-3xl font-semibold tracking-[-0.05em] text-stone-100">EMEA</p>
								<p class="mt-1 text-sm text-stone-400">largest region this week</p>
							</div>
						</div>

						<div class="grid w-full gap-3">
							<div
								v-for="region in regionSeries"
								:key="region.label"
								class="rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-4">
								<div class="flex items-center justify-between gap-4">
									<div class="flex items-center gap-3">
										<span class="h-2.5 w-2.5 rounded-full" :class="region.dotClass" />
										<div>
											<p class="text-sm font-medium text-stone-200">{{ region.label }}</p>
											<p class="text-xs text-stone-500">share of weekly messages</p>
										</div>
									</div>
									<p class="text-lg font-semibold tracking-[-0.03em] text-stone-100">{{ region.value }}%</p>
								</div>
								<div class="h-2 mt-4 overflow-hidden rounded-full bg-white/6">
									<div
										class="h-full rounded-full"
										:class="region.dotClass"
										:style="{ width: `${region.value}%` }" />
								</div>
							</div>
						</div>

						<div class="grid grid-cols-3 gap-3 pt-2 text-center border-t border-white/6">
							<div v-for="region in regionSeries" :key="`${region.label}-stat`" class="py-2">
								<p class="text-[11px] font-semibold uppercase tracking-[0.24em] text-stone-500">{{ region.label }}</p>
								<p class="mt-2 text-xl font-semibold tracking-[-0.04em] text-stone-100">{{ region.value }}%</p>
							</div>
						</div>
					</div>
				</article>
			</div>
		</div>
	</section>
</template>
