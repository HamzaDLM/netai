export type ExecutionStatus = 'running' | 'success' | 'error' | 'blocked' | 'timeout'

export type ConnectorIdentity = {
	key: string
	label: string
}

export type ToolActivity = {
	id: string
	name: string
	label: string
	connector: ConnectorIdentity
	input: unknown
	output: unknown | null
	status: ExecutionStatus
	durationMs: number | null
	error: string | null
}

export type ToolActivityGroup = {
	connector: ConnectorIdentity
	calls: ToolActivity[]
}

export type AgentActivity = {
	runId: string
	agentName: string
	status: 'running' | 'completed' | 'failed'
	durationMs: number | null
	error: string | null
	tools: ToolActivity[]
	groups: ToolActivityGroup[]
}
