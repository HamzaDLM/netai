<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
	Activity,
	ArrowRight,
	Bot,
	BrainCircuit,
	Check,
	CheckCircle2,
	ChevronRight,
	CircleDashed,
	FlaskConical,
	Gauge,
	History,
	LockKeyhole,
	LockOpen,
	Pencil,
	Play,
	Plus,
	Search,
	ShieldCheck,
	Sparkles,
	TriangleAlert,
	Trash2,
	Wrench,
	XCircle,
} from 'lucide-vue-next'
import ChatAdminEvalScenarioDialog from './ChatAdminEvalScenarioDialog.vue'
import ChatAdminEvalEvaluatorDialog from './ChatAdminEvalEvaluatorDialog.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import type { EvalCheckStatus, EvalEvaluator, EvalRun, EvalRunStatus, EvalScenario, EvalView, NewEvalEvaluator, NewEvalScenario } from './evals.types'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import { toast } from '@/components/ui/toast'
import evalsService from '@/services/evals.service'

const activeView = ref<EvalView>('scenarios')
const scenarioSearch = ref('')
const scenarioDialogOpen = ref(false)
const evaluatorDialogOpen = ref(false)
const editingScenario = ref<EvalScenario | null>(null)
const editingEvaluator = ref<EvalEvaluator | null>(null)
const evaluators = ref<EvalEvaluator[]>([])
const scenarios = ref<EvalScenario[]>([])
const runs = ref<EvalRun[]>([])
const selectedScenarioId = ref('')
const loading = ref(true)
const suiteRunning = ref(false)
const scenarioMutationId = ref('')

const filteredScenarios = computed(() => {
	const query = scenarioSearch.value.trim().toLowerCase()
	if (!query) return scenarios.value
	return scenarios.value.filter(scenario => [scenario.name, scenario.description, scenario.owner, scenario.fixture, ...scenario.tags].join(' ').toLowerCase().includes(query))
})

const selectedScenario = computed(() => scenarios.value.find(scenario => scenario.id === selectedScenarioId.value) ?? scenarios.value[0] ?? null)
const selectedRun = computed(() => {
	if (!selectedScenario.value?.lastRunId) return null
	return runs.value.find(run => run.id === selectedScenario.value?.lastRunId) ?? null
})
const completedRuns = computed(() => runs.value.filter(run => run.status === 'passed' || run.status === 'failed'))
const passedRuns = computed(() => completedRuns.value.filter(run => run.status === 'passed').length)
const passRate = computed(() => completedRuns.value.length ? Math.round((passedRuns.value / completedRuns.value.length) * 100) : 0)
const averageScore = computed(() => {
	const scored = completedRuns.value.filter(run => run.score !== null)
	if (!scored.length) return 0
	return Math.round(scored.reduce((total, run) => total + (run.score ?? 0), 0) / scored.length)
})
const runningCount = computed(() => runs.value.filter(run => run.status === 'running').length)
const failedChecks = computed(() => runs.value.flatMap(run => run.checks).filter(check => check.status === 'failed').length)

const views: Array<{ id: EvalView; label: string; icon: typeof FlaskConical }> = [
	{ id: 'scenarios', label: 'Scenarios', icon: FlaskConical },
	{ id: 'runs', label: 'Runs', icon: History },
	{ id: 'evaluators', label: 'Evaluators', icon: BrainCircuit },
]

function statusClass(status: EvalRunStatus | EvalCheckStatus): string {
	if (status === 'passed') return 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
	if (status === 'failed') return 'border-red-500/25 bg-red-500/10 text-red-300'
	if (status === 'running') return 'border-sky-500/25 bg-sky-500/10 text-sky-300'
	if (status === 'warning') return 'border-amber-500/25 bg-amber-500/10 text-amber-300'
	return 'border-stone-700 bg-stone-900 text-stone-500'
}

function statusIcon(status: EvalRunStatus | EvalCheckStatus) {
	if (status === 'passed') return CheckCircle2
	if (status === 'failed') return XCircle
	if (status === 'running') return CircleDashed
	if (status === 'warning') return TriangleAlert
	return CircleDashed
}

function scenarioRun(scenario: EvalScenario): EvalRun | null {
	return scenario.lastRunId ? runs.value.find(run => run.id === scenario.lastRunId) ?? null : null
}

function scenarioScoreClass(scenario: EvalScenario): string {
	const status = scenarioRun(scenario)?.status
	if (status === 'passed') return 'text-emerald-400'
	if (status === 'failed') return 'text-red-400'
	if (status === 'running') return 'text-sky-400'
	return 'text-stone-700'
}

function scenarioIsActive(scenarioId: string): boolean {
	return scenarios.value.some(scenario => scenario.id === scenarioId)
}

function evaluatorName(evaluatorId: string): string {
	return evaluators.value.find(evaluator => evaluator.id === evaluatorId)?.name ?? evaluatorId
}

function selectScenario(id: string) {
	selectedScenarioId.value = id
}

function inspectRun(run: EvalRun) {
	if (!scenarioIsActive(run.scenarioId)) return
	selectedScenarioId.value = run.scenarioId
	activeView.value = 'scenarios'
}

function errorText(error: unknown): string {
	if (error instanceof Error) return error.message
	return 'The evaluation request failed.'
}

function failureToast(title: string, error: unknown): void {
	toast({ title, description: errorText(error), variant: 'destructive' })
}

async function loadData() {
	loading.value = true
	try {
		const [loadedScenarios, loadedEvaluators, loadedRuns] = await Promise.all([
			evalsService.getScenarios(),
			evalsService.getEvaluators(),
			evalsService.getRuns(),
		])
		scenarios.value = loadedScenarios
		evaluators.value = loadedEvaluators
		runs.value = loadedRuns
		if (!selectedScenarioId.value || !loadedScenarios.some(item => item.id === selectedScenarioId.value)) selectedScenarioId.value = loadedScenarios[0]?.id ?? ''
	} catch (error) {
		failureToast('Unable to load evaluations', error)
	} finally {
		loading.value = false
	}
}

async function createScenario(payload: NewEvalScenario) {
	try {
		const scenario = await evalsService.createScenario(payload)
		scenarios.value = [scenario, ...scenarios.value]
		for (const evaluator of evaluators.value) {
			if (scenario.evaluatorIds.includes(evaluator.id)) evaluator.usedBy += 1
		}
		selectedScenarioId.value = scenario.id
		activeView.value = 'scenarios'
		toast({ title: 'Evaluation scenario created', description: scenario.name })
	} catch (error) {
		failureToast('Unable to create evaluation scenario', error)
	}
}

async function createEvaluator(payload: NewEvalEvaluator) {
	try {
		const evaluator = await evalsService.createEvaluator(payload)
		evaluators.value = [evaluator, ...evaluators.value]
		activeView.value = 'evaluators'
		toast({ title: 'Evaluator created', description: evaluator.name })
	} catch (error) {
		failureToast('Unable to create evaluator', error)
	}
}

function openNewScenario(): void {
	editingScenario.value = null
	scenarioDialogOpen.value = true
}

function openScenarioEditor(scenario: EvalScenario): void {
	editingScenario.value = scenario
	scenarioDialogOpen.value = true
}

function openNewEvaluator(): void {
	editingEvaluator.value = null
	evaluatorDialogOpen.value = true
}

function openEvaluatorEditor(evaluator: EvalEvaluator): void {
	editingEvaluator.value = evaluator
	evaluatorDialogOpen.value = true
}

async function updateScenario(scenarioId: string, payload: NewEvalScenario): Promise<void> {
	try {
		const previous = scenarios.value.find(item => item.id === scenarioId)
		const updated = await evalsService.updateScenario(scenarioId, payload)
		const index = scenarios.value.findIndex(item => item.id === scenarioId)
		if (index >= 0) scenarios.value[index] = updated
		if (previous) {
			for (const evaluator of evaluators.value) {
				if (previous.evaluatorIds.includes(evaluator.id) && !updated.evaluatorIds.includes(evaluator.id)) evaluator.usedBy = Math.max(0, evaluator.usedBy - 1)
				if (!previous.evaluatorIds.includes(evaluator.id) && updated.evaluatorIds.includes(evaluator.id)) evaluator.usedBy += 1
			}
		}
		toast({ title: 'Evaluation scenario updated', description: updated.name })
	} catch (error) {
		failureToast('Unable to update evaluation scenario', error)
	}
}

async function updateEvaluator(evaluatorId: string, payload: NewEvalEvaluator): Promise<void> {
	try {
		const updated = await evalsService.updateEvaluator(evaluatorId, payload)
		const index = evaluators.value.findIndex(item => item.id === evaluatorId)
		if (index >= 0) evaluators.value[index] = updated
		toast({ title: 'Evaluator updated', description: updated.name })
	} catch (error) {
		failureToast('Unable to update evaluator', error)
	}
}

async function runScenario(scenario: EvalScenario | null, notify = true): Promise<EvalRun | null> {
	if (!scenario?.enabled || scenarioRun(scenario)?.status === 'running') return null
	const runId = `pending-${scenario.id}-${Date.now()}`
	const run: EvalRun = {
		id: runId,
		scenarioId: scenario.id,
		scenarioName: scenario.name,
		status: 'running',
		score: null,
		startedAt: 'Just now',
		duration: 'Running',
		model: 'Current production model',
		version: 'working tree',
		answer: '',
		toolCalls: [],
		checks: [],
		error: null,
	}
	runs.value = [run, ...runs.value]
	scenario.lastRunId = runId
	try {
		const completed = await evalsService.runScenario(scenario.id)
		runs.value = [completed, ...runs.value.filter(item => item.id !== runId)]
		scenario.lastRunId = completed.id
		if (notify) {
			toast({
				title: completed.status === 'passed' ? 'Evaluation passed' : 'Evaluation failed',
				description: `${scenario.name} scored ${completed.score ?? 0}/100.`,
				variant: completed.status === 'failed' ? 'destructive' : 'default',
			})
		}
		return completed
	} catch (error) {
		run.status = 'failed'
		run.duration = 'Failed'
		run.error = errorText(error)
		run.answer = 'The evaluation could not be completed.'
		if (notify) failureToast('Unable to run evaluation scenario', error)
		return null
	}
}

async function runSuite() {
	if (suiteRunning.value) return
	suiteRunning.value = true
	try {
		const runnable = scenarios.value.filter(item => item.enabled && scenarioRun(item)?.status !== 'running')
		if (!runnable.length) {
			toast({ title: 'No runnable evaluation scenarios' })
			return
		}
		const completed: EvalRun[] = []
		for (const scenario of runnable) {
			const result = await runScenario(scenario, false)
			if (result) completed.push(result)
		}
		const passed = completed.filter(run => run.status === 'passed').length
		const failed = completed.filter(run => run.status === 'failed').length
		const errors = runnable.length - completed.length
		toast({
			title: failed || errors ? 'Evaluation suite completed with failures' : 'Evaluation suite passed',
			description: `${passed} passed, ${failed} failed${errors ? `, ${errors} could not run` : ''}.`,
			variant: failed || errors ? 'destructive' : 'default',
		})
	} finally {
		suiteRunning.value = false
	}
}

async function toggleScenario(scenario: EvalScenario): Promise<void> {
	if (scenarioMutationId.value || scenarioRun(scenario)?.status === 'running') return
	scenarioMutationId.value = scenario.id
	try {
		const updated = await evalsService.setScenarioEnabled(scenario.id, !scenario.enabled)
		const index = scenarios.value.findIndex(item => item.id === scenario.id)
		if (index >= 0) scenarios.value[index] = updated
		toast({ title: updated.enabled ? 'Evaluation scenario enabled' : 'Evaluation scenario disabled', description: updated.name })
	} catch (error) {
		failureToast(`Unable to ${scenario.enabled ? 'disable' : 'enable'} evaluation scenario`, error)
	} finally {
		scenarioMutationId.value = ''
	}
}

async function deleteScenario(scenario: EvalScenario): Promise<void> {
	if (scenarioMutationId.value || scenarioRun(scenario)?.status === 'running') return
	scenarioMutationId.value = scenario.id
	try {
		await evalsService.deleteScenario(scenario.id)
		scenarios.value = scenarios.value.filter(item => item.id !== scenario.id)
		for (const evaluator of evaluators.value) {
			if (scenario.evaluatorIds.includes(evaluator.id)) evaluator.usedBy = Math.max(0, evaluator.usedBy - 1)
		}
		selectedScenarioId.value = scenarios.value[0]?.id ?? ''
		toast({ title: 'Evaluation scenario deleted', description: scenario.name })
	} catch (error) {
		failureToast('Unable to delete evaluation scenario', error)
	} finally {
		scenarioMutationId.value = ''
	}
}

onMounted(loadData)
</script>

<template>
	<section class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[#070707]">
		<header class="border-b border-stone-900 px-6 py-4">
			<div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
				<div>
					<div class="flex items-center gap-3">
						<div>
							<p class="text-xl font-semibold text-stone-100">Agent evaluations</p>
							<p class="mt-1 text-sm text-stone-500">Create end-to-end use cases and score NetAI's tool trajectory, evidence, safety, and final answer.</p>
						</div>
					</div>
				</div>
				<div class="flex flex-wrap items-center gap-2">
					<button type="button" class="inline-flex h-9 items-center gap-2 rounded-md border border-stone-800 px-3 text-sm text-stone-300 transition hover:border-stone-600 hover:bg-stone-900 disabled:cursor-not-allowed disabled:opacity-50" :disabled="suiteRunning || loading || !scenarios.length" @click="runSuite"><CircleDashed v-if="suiteRunning" class="h-3.5 w-3.5 animate-spin" /><Play v-else class="h-3.5 w-3.5" /> {{ suiteRunning ? 'Running suite…' : 'Run suite' }}</button>
					<button type="button" class="inline-flex h-9 items-center gap-2 rounded-md bg-red-600 px-3 text-sm font-medium text-white transition hover:bg-red-500" @click="openNewScenario"><Plus class="h-4 w-4" /> New scenario</button>
				</div>
			</div>
		</header>

		<div class="border-b border-stone-900 px-6">
			<nav class="flex gap-1" aria-label="Evaluation views">
				<button v-for="view in views" :key="view.id" type="button" class="relative inline-flex h-11 items-center gap-2 px-3 text-sm transition" :class="activeView === view.id ? 'text-stone-100' : 'text-stone-500 hover:text-stone-300'" @click="activeView = view.id">
					<component :is="view.icon" class="h-4 w-4" />{{ view.label }}
					<span v-if="activeView === view.id" class="absolute inset-x-2 bottom-0 h-px bg-red-500" />
				</button>
			</nav>
		</div>
		<div class="min-h-0 flex-1 overflow-y-auto p-6">
			<div v-if="loading" class="flex min-h-[420px] items-center justify-center rounded-lg border border-white/7 bg-[#0a0a0a]"><CircleDashed class="h-5 w-5 animate-spin text-red-400" /><span class="ml-3 text-sm text-stone-500">Loading evaluation workspace…</span></div>
			<template v-else>
			<div class="mb-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
				<article class="rounded-lg border border-white/7 bg-white/[0.02] p-4">
					<div class="flex items-center justify-between text-stone-500"><span class="text-[11px] font-semibold uppercase tracking-[0.2em]">Pass rate</span><Gauge class="h-4 w-4" /></div>
					<div class="mt-3 flex items-end justify-between"><p class="text-2xl font-semibold text-stone-100">{{ passRate }}%</p><p class="text-xs text-stone-600">{{ passedRuns }}/{{ completedRuns.length }} runs</p></div>
				</article>
				<article class="rounded-lg border border-white/7 bg-white/[0.02] p-4">
					<div class="flex items-center justify-between text-stone-500"><span class="text-[11px] font-semibold uppercase tracking-[0.2em]">Average score</span><Sparkles class="h-4 w-4" /></div>
					<div class="mt-3 flex items-end justify-between"><p class="text-2xl font-semibold text-stone-100">{{ averageScore }}</p><p class="text-xs text-stone-600">out of 100</p></div>
				</article>
				<article class="rounded-lg border border-white/7 bg-white/[0.02] p-4">
					<div class="flex items-center justify-between text-stone-500"><span class="text-[11px] font-semibold uppercase tracking-[0.2em]">Running</span><Activity class="h-4 w-4" :class="runningCount ? 'animate-pulse text-sky-400' : ''" /></div>
					<div class="mt-3 flex items-end justify-between"><p class="text-2xl font-semibold text-stone-100">{{ runningCount }}</p><p class="text-xs text-stone-600">active evaluations</p></div>
				</article>
				<article class="rounded-lg border border-white/7 bg-white/[0.02] p-4">
					<div class="flex items-center justify-between text-stone-500"><span class="text-[11px] font-semibold uppercase tracking-[0.2em]">Failed checks</span><TriangleAlert class="h-4 w-4" /></div>
					<div class="mt-3 flex items-end justify-between"><p class="text-2xl font-semibold" :class="failedChecks ? 'text-red-400' : 'text-stone-100'">{{ failedChecks }}</p><p class="text-xs text-stone-600">need review</p></div>
				</article>
			</div>

			<div v-if="activeView === 'scenarios'" class="grid min-h-[680px] overflow-hidden rounded-lg border border-white/7 bg-[#0a0a0a] xl:grid-cols-[360px_minmax(0,1fr)]">
				<aside class="border-b border-white/7 xl:border-b-0 xl:border-r">
					<div class="border-b border-white/7 p-4">
						<label class="flex h-9 items-center gap-2 rounded-md border border-stone-800 bg-black/30 px-3 text-stone-500 focus-within:border-stone-600"><Search class="h-4 w-4" /><input v-model="scenarioSearch" class="min-w-0 flex-1 bg-transparent text-sm text-stone-200 outline-none placeholder:text-stone-700" placeholder="Search scenarios" /></label>
					</div>
					<div class="max-h-[760px] overflow-y-auto">
						<button v-for="scenario in filteredScenarios" :key="scenario.id" type="button" class="block w-full border-b border-white/6 px-4 py-4 text-left transition hover:bg-white/[0.025]" :class="[selectedScenario?.id === scenario.id ? 'bg-white/[0.04]' : '', !scenario.enabled ? 'opacity-30' : '']" @click="selectScenario(scenario.id)">
							<div class="flex items-start justify-between gap-3">
								<div class="flex min-w-0 items-center gap-2"><p class="truncate text-sm font-medium leading-5" :class="selectedScenario?.id === scenario.id ? 'text-stone-100' : 'text-stone-300'">{{ scenario.name }}</p><span v-if="!scenario.enabled" class="rounded border border-stone-700 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-stone-500">Disabled</span></div>
								<span class="shrink-0 text-xs font-semibold" :class="scenarioScoreClass(scenario)">{{ scenarioRun(scenario)?.score ?? '—' }}<span v-if="scenarioRun(scenario)?.score !== null && scenarioRun(scenario)?.score !== undefined" class="font-normal opacity-60">/100</span></span>
							</div>
							<p class="mt-2 line-clamp-2 text-xs leading-5 text-stone-600">{{ scenario.description }}</p>
						</button>
						<div v-if="!filteredScenarios.length" class="p-8 text-center text-sm text-stone-600">No scenarios match your search.</div>
					</div>
				</aside>

				<main v-if="selectedScenario" class="min-w-0">
					<div class="flex flex-col gap-4 border-b border-white/7 px-6 py-5 lg:flex-row lg:items-start lg:justify-between">
						<div>
							<div class="flex flex-wrap items-center gap-2"><h2 class="text-xl font-semibold tracking-[-0.03em] text-stone-100">{{ selectedScenario.name }}</h2><span class="text-xs text-stone-700">Owned by {{ selectedScenario.owner }}</span><span class="rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]" :class="statusClass(selectedRun?.status ?? 'not_run')">{{ (selectedRun?.status ?? 'not run').replace('_', ' ') }}</span></div>
							<p class="mt-2 max-w-3xl text-sm leading-6 text-stone-500">{{ selectedScenario.description }}</p>
						</div>
						<div class="flex shrink-0 flex-wrap items-center gap-2 self-start">
							<button type="button" class="inline-flex h-9 items-center gap-2 rounded-md border border-stone-800 px-3 text-sm text-stone-400 transition hover:border-stone-600 hover:text-stone-200 disabled:cursor-not-allowed disabled:opacity-40" :disabled="selectedRun?.status === 'running' || scenarioMutationId === selectedScenario.id" @click="openScenarioEditor(selectedScenario)"><Pencil class="h-3.5 w-3.5" /></button>
							<button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-stone-800 text-stone-400 transition hover:border-stone-600 hover:text-stone-200 disabled:cursor-not-allowed disabled:opacity-40" :title="selectedScenario.enabled ? 'Disable scenario' : 'Enable scenario'" :aria-label="selectedScenario.enabled ? 'Disable scenario' : 'Enable scenario'" :disabled="selectedRun?.status === 'running' || scenarioMutationId === selectedScenario.id" @click="toggleScenario(selectedScenario)"><LockKeyhole v-if="selectedScenario.enabled" class="h-3.5 w-3.5" /><LockOpen v-else class="h-3.5 w-3.5" /></button>
							<AlertDialog><AlertDialogTrigger as-child><button type="button" class="inline-flex h-9 items-center gap-2 rounded-md border border-red-500/20 px-3 text-sm text-red-400 transition hover:border-red-500/40 hover:bg-red-500/[0.06] disabled:cursor-not-allowed disabled:opacity-40" :disabled="selectedRun?.status === 'running' || scenarioMutationId === selectedScenario.id"><Trash2 class="h-3.5 w-3.5" /></button></AlertDialogTrigger><AlertDialogContent class="border-stone-800 bg-stone-950 text-stone-200"><AlertDialogHeader><AlertDialogTitle>Delete evaluation scenario?</AlertDialogTitle><AlertDialogDescription class="text-stone-500">“{{ selectedScenario.name }}” will be removed from the active scenario catalogue. Existing run history and evidence will be preserved.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel class="border-stone-800 bg-transparent text-stone-300 hover:bg-stone-900">Cancel</AlertDialogCancel><AlertDialogAction class="bg-red-600 text-white hover:bg-red-500" @click="deleteScenario(selectedScenario)">Delete scenario</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
							<button type="button" class="inline-flex h-9 items-center gap-2 rounded-md bg-red-600 px-3 text-sm font-medium text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-50" :disabled="!selectedScenario.enabled || selectedRun?.status === 'running'" @click="runScenario(selectedScenario)"><Play class="h-3.5 w-3.5" /> {{ !selectedScenario.enabled ? 'Disabled' : selectedRun?.status === 'running' ? 'Running…' : 'Run scenario' }}</button>
						</div>
					</div>

					<div class="space-y-6 p-6">
						<div class="grid gap-4 lg:grid-cols-2">
							<article class="rounded-lg border border-white/7 bg-black/20 p-4"><p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600">User request</p><p class="mt-3 text-sm leading-6 text-stone-300">{{ selectedScenario.prompt }}</p></article>
							<article class="rounded-lg border border-white/7 bg-black/20 p-4"><p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600">Evaluator reference state</p><p class="mt-3 text-sm leading-6 text-stone-300">{{ selectedScenario.fixture }}</p><p class="mt-3 text-[11px] leading-5 text-stone-700">Used by evaluators as expected context; never shown to the Agent.</p></article>
						</div>

						<div class="grid gap-4 xl:grid-cols-3">
							<article class="rounded-lg border border-white/7 p-4"><div class="flex items-center gap-2 text-stone-500"><Wrench class="h-4 w-4" /><p class="text-[10px] font-semibold uppercase tracking-[0.2em]">Tools</p></div><div class="mt-3 space-y-2"><div v-for="tool in selectedScenario.requiredTools" :key="`required-${tool}`" class="flex items-center justify-between gap-2 rounded bg-white/[0.025] px-2.5 py-2"><p class="min-w-0 truncate font-mono text-xs text-stone-400">{{ tool }}</p><span class="shrink-0 rounded border border-emerald-500/20 bg-emerald-500/[0.05] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-500">Required</span></div><div v-for="tool in selectedScenario.forbiddenTools" :key="`forbidden-${tool}`" class="flex items-center justify-between gap-2 rounded bg-red-500/[0.04] px-2.5 py-2"><p class="min-w-0 truncate font-mono text-xs text-red-300/70">{{ tool }}</p><span class="shrink-0 rounded border border-red-500/20 bg-red-500/[0.05] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-red-400">Forbidden</span></div><p v-if="!selectedScenario.requiredTools.length && !selectedScenario.forbiddenTools.length" class="text-xs text-stone-700">No tool constraints configured</p></div></article>
							<article class="rounded-lg border border-white/7 p-4"><div class="flex items-center gap-2 text-stone-500"><Check class="h-4 w-4" /><p class="text-[10px] font-semibold uppercase tracking-[0.2em]">Expected facts</p></div><div class="mt-3 space-y-2"><div v-for="fact in selectedScenario.expectedFacts" :key="fact" class="flex gap-2 text-xs leading-5 text-stone-400"><Check class="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" /><span>{{ fact }}</span></div><p v-if="!selectedScenario.expectedFacts.length" class="text-xs text-stone-700">No reference facts configured</p></div></article>
							<article class="rounded-lg border border-white/7 p-4"><p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600">Evaluation suite</p><div class="mt-3 flex flex-wrap gap-2"><span v-for="evaluatorId in selectedScenario.evaluatorIds" :key="evaluatorId" class="inline-flex items-center gap-2 rounded-full border border-white/7 bg-white/[0.025] px-3 py-1.5 text-xs text-stone-400"><Bot v-if="evaluators.find(item => item.id === evaluatorId)?.kind === 'llm_judge'" class="h-3.5 w-3.5 text-violet-400" /><ShieldCheck v-else class="h-3.5 w-3.5 text-emerald-500" />{{ evaluatorName(evaluatorId) }}</span></div></article>
						</div>

						<section v-if="selectedRun" class="space-y-4 border-t border-white/7 pt-6">
							<div class="flex flex-wrap items-end justify-between gap-4"><div><p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600">Latest execution</p><div class="mt-2 flex items-center gap-3"><p class="text-lg font-semibold text-stone-200">{{ selectedRun.id }}</p><span class="text-xs text-stone-600">{{ selectedRun.startedAt }} · {{ selectedRun.duration }}</span></div></div><div v-if="selectedRun.score !== null" class="text-right"><p class="text-3xl font-semibold tracking-[-0.05em]" :class="selectedRun.status === 'passed' ? 'text-emerald-400' : 'text-red-400'">{{ selectedRun.score }}</p><p class="text-[10px] uppercase tracking-[0.18em] text-stone-600">overall score</p></div></div>

							<div v-if="selectedRun.status === 'running'" class="rounded-lg border border-sky-500/20 bg-sky-500/[0.04] p-5"><div class="flex items-center gap-3"><CircleDashed class="h-5 w-5 animate-spin text-sky-400" /><div><p class="text-sm font-medium text-sky-200">Running the scenario through NetAI</p><p class="mt-1 text-xs text-stone-500">Tool events and evaluator results will appear after the Agent reaches a final answer.</p></div></div><div class="mt-4 h-1 overflow-hidden rounded-full bg-stone-900"><div class="h-full w-2/3 animate-pulse rounded-full bg-sky-500" /></div></div>

							<template v-else>
								<article class="rounded-lg border border-white/7 bg-black/20 p-4"><p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-600">Final answer</p><MarkdownRenderer class="mt-3 text-sm leading-6 text-stone-300" :content="selectedRun.answer || 'No final answer was produced.'" /></article>

								<div class="grid gap-4 xl:grid-cols-2">
									<article class="overflow-hidden rounded-lg border border-white/7"><div class="flex items-center justify-between border-b border-white/7 px-4 py-3"><p class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Tool trajectory</p></div><div class="divide-y divide-white/6"><div v-for="(call, index) in selectedRun.toolCalls" :key="call.id" class="flex gap-3 p-4"><div class="flex flex-col items-center"><span class="flex h-6 w-6 items-center justify-center rounded-full border text-[10px]" :class="call.status === 'success' ? 'border-emerald-500/25 text-emerald-400' : 'border-red-500/25 text-red-400'">{{ index + 1 }}</span><span v-if="index < selectedRun.toolCalls.length - 1" class="mt-1 h-full w-px bg-stone-800" /></div><div class="min-w-0 flex-1"><div class="flex flex-wrap items-center justify-between gap-2"><p class="font-mono text-xs text-stone-300">{{ call.name }}</p><span class="text-[10px] uppercase tracking-wide" :class="call.expectation === 'required' ? 'text-emerald-500' : call.expectation === 'unexpected' ? 'text-red-400' : 'text-stone-600'">{{ call.expectation }}</span></div><p class="mt-1 text-[11px] text-stone-600">{{ call.connector }} · {{ call.durationMs }}ms</p><p class="mt-2 text-xs leading-5 text-stone-500">{{ call.summary }}</p></div></div><div v-if="!selectedRun.toolCalls.length" class="p-5 text-sm text-stone-600">No tool calls recorded.</div></div></article>

									<article class="overflow-hidden rounded-lg border border-white/7"><div class="border-b border-white/7 px-4 py-3"><p class="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Evaluator results</p></div><div class="divide-y divide-white/6"><div v-for="check in selectedRun.checks" :key="check.id" class="p-4"><div class="flex items-start justify-between gap-4"><div class="flex min-w-0 gap-3"><component :is="statusIcon(check.status)" class="mt-0.5 h-4 w-4 shrink-0" :class="check.status === 'passed' ? 'text-emerald-400' : check.status === 'failed' ? 'text-red-400' : 'text-amber-400'" /><div><div class="flex flex-wrap items-center gap-2"><p class="text-sm font-medium text-stone-300">{{ check.name }}</p><span class="rounded border border-stone-800 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-stone-600">{{ check.kind === 'llm_judge' ? 'LLM judge' : 'Deterministic' }}</span></div><p class="mt-2 text-xs leading-5 text-stone-500">{{ check.detail }}</p></div></div><span class="shrink-0 text-sm font-semibold" :class="check.status === 'passed' ? 'text-emerald-400' : 'text-red-400'">{{ check.score }}</span></div><div class="mt-3 h-1 overflow-hidden rounded-full bg-stone-900"><div class="h-full rounded-full" :class="check.status === 'passed' ? 'bg-emerald-500' : 'bg-red-500'" :style="{ width: `${check.score}%` }" /></div></div><div v-if="!selectedRun.checks.length" class="p-5 text-sm text-stone-600">No evaluator results recorded.</div></div></article>
								</div>
							</template>
						</section>
						<div v-else class="rounded-lg border border-dashed border-stone-800 px-6 py-10 text-center"><FlaskConical class="mx-auto h-6 w-6 text-stone-700" /><p class="mt-3 text-sm text-stone-500">{{ selectedScenario.enabled ? 'This scenario has not been run yet.' : 'This scenario is disabled and excluded from suite runs.' }}</p><button type="button" class="mt-4 text-sm text-red-400 transition hover:text-red-300" @click="selectedScenario.enabled ? runScenario(selectedScenario) : toggleScenario(selectedScenario)">{{ selectedScenario.enabled ? 'Run the first evaluation' : 'Enable scenario' }}</button></div>
					</div>
				</main>
				<div v-else class="flex min-h-[680px] items-center justify-center xl:col-span-2"><div class="text-center"><FlaskConical class="mx-auto h-7 w-7 text-stone-700" /><p class="mt-3 text-sm text-stone-500">No evaluation scenarios yet.</p><button type="button" class="mt-3 text-sm text-red-400 hover:text-red-300" @click="openNewScenario">Create the first scenario</button></div></div>
			</div>

			<div v-else-if="activeView === 'runs'" class="overflow-hidden rounded-lg border border-white/7 bg-[#0a0a0a]">
				<div class="flex flex-col gap-3 border-b border-white/7 px-5 py-4 md:flex-row md:items-center md:justify-between"><div><p class="text-base font-semibold text-stone-200">Evaluation history</p><p class="mt-1 text-xs text-stone-600">Compare architecture versions and scenario outcomes.</p></div><span class="text-xs text-stone-600">{{ runs.length }} runs</span></div>
				<div class="overflow-x-auto"><table class="w-full min-w-[820px] text-left"><thead class="border-b border-white/7 bg-black/20 text-[10px] uppercase tracking-[0.18em] text-stone-600"><tr><th class="px-5 py-3 font-medium">Run</th><th class="px-5 py-3 font-medium">Scenario</th><th class="px-5 py-3 font-medium">Status</th><th class="px-5 py-3 font-medium">Score</th><th class="px-5 py-3 font-medium">Version</th><th class="px-5 py-3 font-medium">Duration</th><th class="px-5 py-3" /></tr></thead><tbody class="divide-y divide-white/6"><tr v-for="run in runs" :key="run.id" class="transition hover:bg-white/[0.02]"><td class="px-5 py-4"><p class="font-mono text-xs text-stone-300">{{ run.id }}</p><p class="mt-1 text-[11px] text-stone-700">{{ run.startedAt }}</p></td><td class="px-5 py-4 text-sm text-stone-300">{{ run.scenarioName }}</td><td class="px-5 py-4"><span class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide" :class="statusClass(run.status)"><component :is="statusIcon(run.status)" class="h-3 w-3" :class="run.status === 'running' ? 'animate-spin' : ''" />{{ run.status }}</span></td><td class="px-5 py-4 text-sm font-semibold" :class="run.status === 'failed' ? 'text-red-400' : 'text-stone-300'">{{ run.score ?? '—' }}</td><td class="px-5 py-4 font-mono text-[10px] text-stone-600">{{ run.version }}</td><td class="px-5 py-4 text-xs text-stone-500">{{ run.duration }}</td><td class="px-5 py-4 text-right"><button type="button" class="inline-flex items-center gap-1 text-xs text-stone-500 transition hover:text-stone-200 disabled:cursor-not-allowed disabled:text-stone-800" :disabled="!scenarioIsActive(run.scenarioId)" @click="inspectRun(run)">{{ scenarioIsActive(run.scenarioId) ? 'Inspect' : 'Archived' }} <ChevronRight v-if="scenarioIsActive(run.scenarioId)" class="h-3.5 w-3.5" /></button></td></tr></tbody></table></div>
			</div>

			<div v-else class="grid gap-4 lg:grid-cols-2">
				<article v-for="evaluator in evaluators" :key="evaluator.id" class="rounded-lg border border-white/7 bg-[#0a0a0a] p-5">
					<div class="flex items-start justify-between gap-4"><div class="flex items-start gap-3"><div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border" :class="evaluator.kind === 'llm_judge' ? 'border-violet-500/20 bg-violet-500/[0.06] text-violet-400' : 'border-emerald-500/20 bg-emerald-500/[0.06] text-emerald-400'"><Bot v-if="evaluator.kind === 'llm_judge'" class="h-4 w-4" /><ShieldCheck v-else class="h-4 w-4" /></div><div><p class="text-base font-semibold text-stone-200">{{ evaluator.name }}</p><p class="mt-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-stone-600">{{ evaluator.kind === 'llm_judge' ? 'LLM as evaluator' : 'Deterministic gate' }}</p></div></div><span class="rounded-full border border-stone-800 px-2.5 py-1 text-xs text-stone-500">≥ {{ evaluator.threshold }}</span></div>
					<p class="mt-5 text-sm leading-6 text-stone-500">{{ evaluator.description }}</p>
					<div class="mt-5 rounded-md border border-white/6 bg-black/20 p-3"><p class="text-[10px] font-semibold uppercase tracking-[0.18em] text-stone-700">Criteria</p><p class="mt-2 text-xs leading-5 text-stone-500">{{ evaluator.criteria }}</p></div>
					<div class="mt-4 flex items-center justify-between text-xs text-stone-700"><span>Used by {{ evaluator.usedBy }} scenarios</span><button type="button" class="inline-flex items-center gap-1 text-stone-500 transition hover:text-stone-300" @click="openEvaluatorEditor(evaluator)">Configure <ArrowRight class="h-3.5 w-3.5" /></button></div>
				</article>
				<button type="button" class="flex min-h-56 flex-col items-center justify-center rounded-lg border border-dashed border-stone-800 text-stone-600 transition hover:border-stone-700 hover:bg-white/[0.015] hover:text-stone-400" @click="openNewEvaluator"><Plus class="h-6 w-6" /><span class="mt-3 text-sm">Add evaluator</span><span class="mt-1 text-xs text-stone-700">Deterministic rule or LLM judge</span></button>
			</div>
			</template>
		</div>

		<ChatAdminEvalScenarioDialog v-model:open="scenarioDialogOpen" :evaluators="evaluators" :scenario="editingScenario" @create="createScenario" @update="updateScenario" />
		<ChatAdminEvalEvaluatorDialog v-model:open="evaluatorDialogOpen" :evaluator="editingEvaluator" @create="createEvaluator" @update="updateEvaluator" />
	</section>
</template>
