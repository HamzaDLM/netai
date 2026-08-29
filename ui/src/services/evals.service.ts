import API from './axios'
import type { EvalCheck, EvalEvaluator, EvalRun, EvalScenario, EvalToolCall, NewEvalEvaluator, NewEvalScenario } from '@/components/chat/admin/evals.types'

type ApiEvaluator = {
	id: string
	name: string
	kind: EvalEvaluator['kind']
	rule: EvalEvaluator['rule']
	description: string
	criteria: string
	threshold: number
	builtin: boolean
	used_by: number
}

type ApiScenario = {
	id: string
	name: string
	description: string
	owner: string
	tags: string[]
	prompt: string
	fixture: string
	required_tools: string[]
	forbidden_tools: string[]
	expected_facts: string[]
	evaluator_ids: string[]
	enabled: boolean
	last_run_id: string | null
}

type ApiToolCall = {
	id: string
	name: string
	connector: string
	status: string
	expectation: string
	duration_ms: number
	summary: string
}

type ApiCheck = {
	id: string
	name: string
	kind: EvalCheck['kind']
	status: string
	score: number
	detail: string
}

type ApiRun = {
	id: string
	scenario_id: string
	scenario_name: string
	status: EvalRun['status']
	score: number | null
	started_at: string
	ended_at: string | null
	duration_ms: number | null
	model: string
	version: string
	answer: string
	tool_calls: ApiToolCall[]
	checks: ApiCheck[]
	error: string | null
}

function normalizeEvaluator(value: ApiEvaluator): EvalEvaluator {
	return { ...value, usedBy: value.used_by }
}

function normalizeScenario(value: ApiScenario): EvalScenario {
	return {
		id: value.id,
		name: value.name,
		description: value.description,
		owner: value.owner,
		tags: value.tags,
		prompt: value.prompt,
		fixture: value.fixture,
		requiredTools: value.required_tools,
		forbiddenTools: value.forbidden_tools,
		expectedFacts: value.expected_facts,
		evaluatorIds: value.evaluator_ids,
		enabled: value.enabled,
		lastRunId: value.last_run_id,
	}
}

function normalizeToolCall(value: ApiToolCall): EvalToolCall {
	return {
		id: value.id,
		name: value.name,
		connector: value.connector,
		status: value.status === 'success' ? 'success' : 'error',
		expectation: value.expectation === 'required' || value.expectation === 'unexpected' ? value.expectation : 'allowed',
		durationMs: value.duration_ms,
		summary: value.summary,
	}
}

function normalizeCheck(value: ApiCheck): EvalCheck {
	return {
		...value,
		status: value.status === 'passed' || value.status === 'failed' ? value.status : 'warning',
	}
}

function normalizeRun(value: ApiRun): EvalRun {
	return {
		id: value.id,
		scenarioId: value.scenario_id,
		scenarioName: value.scenario_name,
		status: value.status,
		score: value.score,
		startedAt: new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value.started_at)),
		duration: value.duration_ms === null ? 'Running' : `${(value.duration_ms / 1000).toFixed(1)}s`,
		model: value.model,
		version: value.version,
		answer: value.answer,
		toolCalls: value.tool_calls.map(normalizeToolCall),
		checks: value.checks.map(normalizeCheck),
		error: value.error,
	}
}

class EvalsService {
	async getScenarios(): Promise<EvalScenario[]> {
		const { data } = await API.get<ApiScenario[]>('/evals/scenarios')
		return data.map(normalizeScenario)
	}

	async getEvaluators(): Promise<EvalEvaluator[]> {
		const { data } = await API.get<ApiEvaluator[]>('/evals/evaluators')
		return data.map(normalizeEvaluator)
	}

	async getRuns(): Promise<EvalRun[]> {
		const { data } = await API.get<ApiRun[]>('/evals/runs')
		return data.map(normalizeRun)
	}

	async createScenario(payload: NewEvalScenario): Promise<EvalScenario> {
		const { data } = await API.post<ApiScenario>('/evals/scenarios', {
			name: payload.name,
			description: payload.description,
			prompt: payload.prompt,
			fixture: payload.fixture,
			tags: payload.tags,
			required_tools: payload.requiredTools,
			forbidden_tools: payload.forbiddenTools,
			expected_facts: payload.expectedFacts,
			evaluator_ids: payload.evaluatorIds,
		})
		return normalizeScenario(data)
	}

	async updateScenario(scenarioId: string, payload: NewEvalScenario): Promise<EvalScenario> {
		const { data } = await API.put<ApiScenario>(`/evals/scenarios/${scenarioId}`, {
			name: payload.name,
			description: payload.description,
			prompt: payload.prompt,
			fixture: payload.fixture,
			tags: payload.tags,
			required_tools: payload.requiredTools,
			forbidden_tools: payload.forbiddenTools,
			expected_facts: payload.expectedFacts,
			evaluator_ids: payload.evaluatorIds,
		})
		return normalizeScenario(data)
	}

	async createEvaluator(payload: NewEvalEvaluator): Promise<EvalEvaluator> {
		const { data } = await API.post<ApiEvaluator>('/evals/evaluators', payload)
		return normalizeEvaluator(data)
	}

	async updateEvaluator(evaluatorId: string, payload: NewEvalEvaluator): Promise<EvalEvaluator> {
		const { data } = await API.put<ApiEvaluator>(`/evals/evaluators/${evaluatorId}`, payload)
		return normalizeEvaluator(data)
	}

	async runScenario(scenarioId: string): Promise<EvalRun> {
		const { data } = await API.post<ApiRun>(`/evals/scenarios/${scenarioId}/runs`)
		return normalizeRun(data)
	}

	async setScenarioEnabled(scenarioId: string, enabled: boolean): Promise<EvalScenario> {
		const { data } = await API.patch<ApiScenario>(`/evals/scenarios/${scenarioId}/enabled`, { enabled })
		return normalizeScenario(data)
	}

	async deleteScenario(scenarioId: string): Promise<void> {
		await API.delete(`/evals/scenarios/${scenarioId}`)
	}
}

export default new EvalsService()
