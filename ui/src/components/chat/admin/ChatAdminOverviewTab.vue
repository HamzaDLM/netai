<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ChatAdminStatCard from './ChatAdminStatCard.vue'
import { AlertTriangle, Clock3, MessageSquare, MessagesSquare, RefreshCw, ThumbsDown } from 'lucide-vue-next'
import { toast } from '@/components/ui/toast'
import chatService from '@/services/chat.service'
import type { AdminOverview } from '@/types/chat.type'

type OverviewCard = {
	title: string
	value: string
	helper: string
	icon: typeof MessageSquare
	spanClass: string
}

const EMPTY_OVERVIEW: AdminOverview = {
	window_started_at: '',
	generated_at: '',
	conversations: 0,
	user_messages: 0,
	tool_calls_total: 0,
	tool_calls_failed: 0,
	average_latency_ms: null,
	feedback_total: 0,
	negative_feedback: 0,
	message_volume: [],
}

const overview = ref<AdminOverview>({ ...EMPTY_OVERVIEW })
const isLoading = ref(true)

function formatLatency(milliseconds: number | null | undefined): string {
	if (milliseconds == null) return '—'
	if (milliseconds < 1000) return `${Math.round(milliseconds)}ms`
	return `${(milliseconds / 1000).toFixed(1)}s`
}

const overviewCards = computed<OverviewCard[]>(() => [
	{
		title: 'Conversations',
		value: overview.value.conversations.toLocaleString(),
		helper: 'last 7 days',
		icon: MessageSquare,
		spanClass: 'xl:col-span-4',
	},
	{
		title: 'Messages',
		value: overview.value.user_messages.toLocaleString(),
		helper: 'user questions · last 7 days',
		icon: MessagesSquare,
		spanClass: 'xl:col-span-4',
	},
	{
		title: 'Failed Toolcalls',
		value: `${overview.value.tool_calls_failed.toLocaleString()}/${overview.value.tool_calls_total.toLocaleString()}`,
		helper: 'failed / total · last 7 days',
		icon: AlertTriangle,
		spanClass: 'xl:col-span-4',
	},
	{
		title: 'Avg Latency',
		value: formatLatency(overview.value.average_latency_ms),
		helper: 'average response · last 7 days',
		icon: Clock3,
		spanClass: 'xl:col-span-6',
	},
	{
		title: 'Negative Feedback',
		value: overview.value.feedback_total === 0 ? '0%' : `${((overview.value.negative_feedback / overview.value.feedback_total) * 100).toFixed(1)}%`,
		helper: `${overview.value.negative_feedback.toLocaleString()} of ${overview.value.feedback_total.toLocaleString()} rated answers`,
		icon: ThumbsDown,
		spanClass: 'xl:col-span-6',
	},
])

const weeklyMessageTotal = computed(() => overview.value.user_messages.toLocaleString())
const averageDailyMessages = computed(() => Math.round(overview.value.user_messages / 7).toLocaleString())
const heatmapDays = computed(() => {
	const grouped = new Map<string, Array<{ hour: number; count: number }>>()
	for (const point of overview.value.message_volume) {
		const cells = grouped.get(point.date) ?? []
		cells.push({ hour: point.hour, count: point.count })
		grouped.set(point.date, cells)
	}
	return [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([date, cells]) => ({
		date,
		label: new Intl.DateTimeFormat(undefined, { weekday: 'short' }).format(new Date(`${date}T12:00:00`)),
		cells: cells.sort((left, right) => left.hour - right.hour),
	}))
})
const maxHourlyMessages = computed(() => Math.max(0, ...overview.value.message_volume.map(point => point.count)))
const HEATMAP_CLASSES = [
	'border-stone-800/70 bg-stone-900/70',
	'border-red-500/20 bg-red-500/15',
	'border-red-500/40 bg-red-500/30',
	'border-red-500/60 bg-red-500/50',
	'border-red-500/80 bg-red-500/75',
] as const

function heatmapClass(count: number): string {
	if (!count || !maxHourlyMessages.value) return HEATMAP_CLASSES[0]
	const ratio = count / maxHourlyMessages.value
	if (ratio <= 0.25) return HEATMAP_CLASSES[1]
	if (ratio <= 0.5) return HEATMAP_CLASSES[2]
	if (ratio <= 0.75) return HEATMAP_CLASSES[3]
	return HEATMAP_CLASSES[4]
}

async function loadOverview(): Promise<void> {
	isLoading.value = true
	try {
		const { data } = await chatService.getAdminOverview()
		overview.value = data
	} catch {
		toast({ title: 'Unable to load admin overview', variant: 'destructive' })
	} finally {
		isLoading.value = false
	}
}

onMounted(loadOverview)
</script>

<template>
	<section class="relative flex min-w-0 flex-1 flex-col overflow-auto">
		<div class="absolute inset-0 overflow-hidden pointer-events-none">
			<div class="absolute left-[-8%] top-[-8%] h-72 w-72 rounded-full bg-cyan-500/8 blur-3xl" />
			<div class="absolute bottom-[-12%] right-[-6%] h-80 w-80 rounded-full bg-emerald-500/8 blur-3xl" />
		</div>

		<div class="relative flex items-center justify-between gap-4 px-6 py-4 border-b border-stone-900">
			<div>
				<p class="text-xl font-semibold text-stone-100">Overview</p>
				<p class="mt-1 text-sm text-stone-500">Operational summary for the last 7 days.</p>
			</div>
			<button type="button" class="inline-flex h-9 items-center gap-2 rounded-md border border-stone-800 px-3 text-sm text-stone-400 transition hover:border-stone-600 hover:text-stone-200 disabled:opacity-40" :disabled="isLoading" @click="loadOverview"><RefreshCw class="h-3.5 w-3.5" :class="isLoading ? 'animate-spin' : ''" />Refresh</button>
		</div>

		<div class="relative px-8 py-8 space-y-8">
			<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-12" :class="isLoading ? 'animate-pulse opacity-60' : ''">
				<ChatAdminStatCard v-for="card in overviewCards" :key="card.title" :class="card.spanClass" :title="card.title" :value="card.value" :helper="card.helper" :icon="card.icon" />
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
					<div class="mt-6 overflow-x-auto pb-2">
						<div class="min-w-[720px]">
							<div class="mb-2 grid grid-cols-[42px_repeat(24,minmax(0,1fr))] gap-1 text-[9px] text-stone-700">
								<span />
								<span v-for="hour in 24" :key="hour" class="text-center">{{ [1, 7, 13, 19, 24].includes(hour) ? String(hour - 1).padStart(2, '0') : '' }}</span>
							</div>
							<div class="space-y-1">
								<div v-for="day in heatmapDays" :key="day.date" class="grid grid-cols-[42px_repeat(24,minmax(0,1fr))] gap-1">
									<span class="self-center text-[10px] font-medium text-stone-600">{{ day.label }}</span>
									<div v-for="cell in day.cells" :key="cell.hour" class="aspect-square rounded-[3px] border transition hover:ring-1 hover:ring-stone-500" :class="heatmapClass(cell.count)" :title="`${day.date} ${String(cell.hour).padStart(2, '0')}:00 · ${cell.count} message${cell.count === 1 ? '' : 's'}`" />
								</div>
							</div>
							<div class="mt-4 flex items-center justify-end gap-1.5 text-[10px] text-stone-600"><span>Less</span><span v-for="level in HEATMAP_CLASSES" :key="level" class="h-3 w-3 rounded-[3px] border" :class="level" /><span>More</span></div>
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
