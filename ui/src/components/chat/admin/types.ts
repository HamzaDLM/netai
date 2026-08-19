import type { AgentRun } from '@/types/chat.type'

export type AdminSection = 'overview' | 'feedbacks' | 'connectors' | 'skills' | 'users' | 'latency' | 'evals' | 'documents'

export type PersistedToolCall = {
	id: number
	tool_name: string
	input_params?: Record<string, unknown>
	output?: Record<string, unknown> | null
	status?: string
	error_type?: string | null
	error_message?: string | null
	created_at?: string
}

export type RunWithPersistedTools = AgentRun & {
	agent_name?: string
	tool_calls?: PersistedToolCall[]
	child_runs?: RunWithPersistedTools[]
}

export type DisplayToolCall = PersistedToolCall & {
	connectorLabel: string
}
