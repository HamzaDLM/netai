import type { AgentEvent, AgentRun, Message, ToolCall } from '../../types/chat.type.ts'
import type { AgentActivity, ConnectorIdentity, ExecutionStatus, ToolActivity, ToolActivityGroup } from './execution.types.ts'

const CONNECTORS: Record<string, string> = {
	zabbix: 'Zabbix',
	suzieq: 'SuzieQ',
	bitbucket: 'Bitbucket',
	servicenow: 'ServiceNow',
	datamodel: 'Topology',
	topology: 'Topology',
	syslog: 'Syslog',
	network: 'Network diagnostics',
	infrahub: 'Infrahub',
}

function asRecord(value: unknown): Record<string, unknown> | null {
	if (!value || typeof value !== 'object' || Array.isArray(value)) return null
	return value as Record<string, unknown>
}

function displayName(value: string): string {
	if (value.trim().toLowerCase() === 'netai') return 'NetAI'
	return value
		.replace(/[._-]+/g, ' ')
		.trim()
		.split(/\s+/)
		.filter(Boolean)
		.map(part => part.charAt(0).toUpperCase() + part.slice(1))
		.join(' ')
}

function connectorKeyFromAgent(agentName: string | undefined): string | null {
	const normalized = (agentName ?? '')
		.toLowerCase()
		.replace(/\b(agent|specialist|orchestrator)\b/g, '')
		.replace(/[^a-z0-9]/g, '')
	for (const key of Object.keys(CONNECTORS)) {
		if (normalized.includes(key)) return key
	}
	return null
}

export function connectorForTool(toolName: string, agentName?: string): ConnectorIdentity {
	const normalized = toolName.toLowerCase()
	const prefix = normalized.split(/[._-]/, 1)[0]
	const inferredKey = prefix in CONNECTORS ? prefix : connectorKeyFromAgent(agentName)
	const key = inferredKey ?? 'external'
	return {
		key,
		label: CONNECTORS[key] ?? displayName(agentName || key || 'External'),
	}
}

function connectorFromEvent(value: unknown, toolName: string, agentName?: string): ConnectorIdentity {
	if (typeof value !== 'string' || !value.trim()) return connectorForTool(toolName, agentName)
	const key = value.trim().toLowerCase()
	return { key, label: CONNECTORS[key] ?? displayName(value) }
}

export function toolLabel(toolName: string): string {
	const connector = connectorForTool(toolName)
	const prefixPattern = new RegExp(`^${connector.key}[._-]+`, 'i')
	const concise = toolName.replace(prefixPattern, '')
	return displayName(concise || toolName) || 'Unknown tool'
}

function executionStatus(value: unknown): ExecutionStatus {
	const normalized = String(value ?? '').toLowerCase()
	if (normalized === 'running') return 'running'
	if (normalized === 'blocked') return 'blocked'
	if (normalized === 'timeout' || normalized === 'timed_out') return 'timeout'
	if (['error', 'failed', 'failure'].includes(normalized)) return 'error'
	return 'success'
}

function primaryRun(message: Message): AgentRun | null {
	const runs = message.agent_runs ?? []
	if (runs.length === 0) return null
	const roots = runs.filter(run => run.parent_run_id == null || run.depth === 0)
	return roots.at(-1) ?? runs.at(-1) ?? null
}

function runDuration(run: AgentRun): number | null {
	if (typeof run.duration_ms === 'number' && Number.isFinite(run.duration_ms)) {
		return Math.max(0, Math.round(run.duration_ms))
	}
	const started = Date.parse(run.started_at || run.created_at)
	const ended = Date.parse(run.ended_at || run.events?.at(-1)?.created_at || '')
	if (!Number.isFinite(started) || !Number.isFinite(ended)) return null
	return Math.max(0, Math.round(ended - started))
}

function persistedActivity(call: ToolCall, agentName: string): ToolActivity {
	const connector = connectorForTool(call.tool_name, agentName)
	return {
		id: String(call.id),
		name: call.tool_name,
		label: toolLabel(call.tool_name),
		connector,
		input: call.input_params ?? call.arguments ?? {},
		output: call.output ?? call.result ?? null,
		status: executionStatus(call.status),
		durationMs: typeof call.latency_ms === 'number' ? call.latency_ms : null,
		error: call.error_message ?? null,
	}
}

function collectPersistedActivities(run: AgentRun): ToolActivity[] {
	const direct = (run.tool_calls ?? [])
		.filter(call => !call.tool_name.endsWith('_specialist'))
		.map(call => persistedActivity(call, run.agent_name ?? 'netai'))
	const children = (run.child_runs ?? []).flatMap(child => collectPersistedActivities(child))
	return [...direct, ...children]
}

function sortedEvents(run: AgentRun): AgentEvent[] {
	return [...(run.events ?? []), ...(run.child_runs ?? []).flatMap(child => sortedEvents(child))].sort(
		(left, right) => (left.event_sequence ?? 0) - (right.event_sequence ?? 0)
	)
}

function eventActivities(run: AgentRun): ToolActivity[] {
	const calls: ToolActivity[] = []
	const byId = new Map<string, ToolActivity>()
	const legacyPending = new Map<string, ToolActivity[]>()

	for (const event of sortedEvents(run)) {
		const payload = asRecord(event.payload) ?? {}
		if (event.event_type === 'tool_started') {
			const name = String(payload.tool_name ?? event.actor_name ?? 'unknown_tool')
			const id = String(payload.tool_call_id ?? event.correlation_id ?? event.id)
			const call: ToolActivity = {
				id,
				name,
				label: toolLabel(name),
				connector: connectorFromEvent(payload.connector, name),
				input: payload.arguments ?? {},
				output: null,
				status: 'running',
				durationMs: null,
				error: null,
			}
			calls.push(call)
			byId.set(id, call)
			continue
		}

		if (event.event_type === 'tool_completed' || event.event_type === 'tool_failed') {
			const id = String(payload.tool_call_id ?? event.correlation_id ?? '')
			const call = byId.get(id)
			if (!call) continue
			call.connector = connectorFromEvent(payload.connector, call.name)
			call.status = event.event_type === 'tool_failed' ? 'error' : 'success'
			call.durationMs = typeof payload.duration_ms === 'number' ? payload.duration_ms : null
			call.error = typeof payload.error === 'string' ? payload.error : null
			continue
		}

		// Compatibility for conversations persisted by the former specialist architecture.
		if (event.event_type === 'specialist_tool_call') {
			const specialist = String(payload.specialist ?? event.actor_name ?? '')
			const name = String(payload.tool_name ?? 'unknown_tool')
			const call: ToolActivity = {
				id: String(event.id),
				name,
				label: toolLabel(name),
				connector: connectorForTool(name, specialist),
				input: payload.arguments ?? {},
				output: null,
				status: 'running',
				durationMs: null,
				error: null,
			}
			calls.push(call)
			const key = `${specialist}:${name}`
			legacyPending.set(key, [...(legacyPending.get(key) ?? []), call])
			continue
		}

		if (event.event_type === 'specialist_tool_result' || event.event_type === 'specialist_evidence') {
			const specialist = String(payload.specialist ?? event.actor_name ?? '')
			const name = String(payload.tool_name ?? 'unknown_tool')
			const call = legacyPending.get(`${specialist}:${name}`)?.shift()
			if (!call) continue
			call.status = 'success'
			call.output =
				event.event_type === 'specialist_evidence'
					? { result: payload.result ?? {}, evidence: payload.evidence ?? [] }
					: payload.result ?? {}
		}
	}

	return calls
}

function groupTools(tools: ToolActivity[]): ToolActivityGroup[] {
	const groups = new Map<string, ToolActivityGroup>()
	for (const call of tools) {
		const current = groups.get(call.connector.key)
		if (current) {
			current.calls.push(call)
			continue
		}
		groups.set(call.connector.key, { connector: call.connector, calls: [call] })
	}
	return [...groups.values()]
}

export function getMessageAgentActivity(message: Message): AgentActivity | null {
	const run = primaryRun(message)
	if (!run) return null
	const persistedTools = collectPersistedActivities(run)
	const streamedTools = eventActivities(run)
	if (persistedTools.length > 0 && streamedTools.length > 0) {
		const streamedByName = new Map<string, ToolActivity[]>()
		for (const call of streamedTools) {
			streamedByName.set(call.name, [...(streamedByName.get(call.name) ?? []), call])
		}
		for (const call of persistedTools) {
			const streamed = streamedByName.get(call.name)?.shift()
			if (streamed) call.connector = streamed.connector
		}
	}
	const tools = persistedTools.length > 0 ? persistedTools : streamedTools
	return {
		runId: String(run.id),
		agentName: displayName(run.agent_name || 'NetAI'),
		status: run.status,
		durationMs: runDuration(run),
		error: run.error ?? null,
		tools,
		groups: groupTools(tools),
	}
}

export function getMessageToolActivities(message: Message): ToolActivity[] {
	return getMessageAgentActivity(message)?.tools ?? []
}
