export type EvalView = 'scenarios' | 'runs' | 'evaluators'
export type EvalRunStatus = 'passed' | 'failed' | 'running' | 'not_run'
export type EvalCheckStatus = 'passed' | 'failed' | 'warning'
export type EvalEvaluatorKind = 'deterministic' | 'llm_judge'
export type EvalEvaluatorRule = 'tool_trajectory' | 'completion_safety' | 'llm_judge'

export type EvalToolCall = {
	id: string
	name: string
	connector: string
	status: 'success' | 'error'
	expectation: 'required' | 'allowed' | 'unexpected'
	durationMs: number
	summary: string
}

export type EvalCheck = {
	id: string
	name: string
	kind: EvalEvaluatorKind
	status: EvalCheckStatus
	score: number
	detail: string
}

export type EvalRun = {
	id: string
	scenarioId: string
	scenarioName: string
	status: EvalRunStatus
	score: number | null
	startedAt: string
	duration: string
	model: string
	version: string
	answer: string
	toolCalls: EvalToolCall[]
	checks: EvalCheck[]
	error: string | null
}

export type EvalScenario = {
	id: string
	name: string
	description: string
	owner: string
	tags: string[]
	prompt: string
	fixture: string
	requiredTools: string[]
	forbiddenTools: string[]
	expectedFacts: string[]
	evaluatorIds: string[]
	enabled: boolean
	lastRunId: string | null
}

export type EvalEvaluator = {
	id: string
	name: string
	kind: EvalEvaluatorKind
	rule: EvalEvaluatorRule
	description: string
	criteria: string
	usedBy: number
	threshold: number
	builtin: boolean
}

export type NewEvalScenario = {
	name: string
	description: string
	tags: string[]
	prompt: string
	fixture: string
	requiredTools: string[]
	forbiddenTools: string[]
	expectedFacts: string[]
	evaluatorIds: string[]
}

export type EvalScenarioUpdate = NewEvalScenario

export type NewEvalEvaluator = {
	name: string
	kind: EvalEvaluatorKind
	rule: EvalEvaluatorRule
	description: string
	criteria: string
	threshold: number
}

export type EvalEvaluatorUpdate = NewEvalEvaluator
