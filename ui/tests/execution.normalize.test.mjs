import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { before, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { transformWithEsbuild } from 'vite'

let getMessageAgentActivity

before(async () => {
	const moduleUrl = new URL('../src/features/execution/execution.normalize.ts', import.meta.url)
	const transformed = await transformWithEsbuild(
		await readFile(fileURLToPath(moduleUrl), 'utf8'),
		fileURLToPath(moduleUrl),
		{ loader: 'ts', format: 'esm', target: 'es2020' }
	)
	const module = await import(
		`data:text/javascript;base64,${Buffer.from(transformed.code).toString('base64')}`
	)
	getMessageAgentActivity = module.getMessageAgentActivity
})

function messageWithRun(run) {
	return {
		id: 10,
		role: 'assistant',
		content: 'Investigation complete.',
		created_at: '2026-08-19T10:00:00Z',
		feedback: [],
		agent_runs: [
			{
				id: 20,
				user_message_id: 9,
				agent_name: 'netai',
				status: 'completed',
				duration_ms: 1250,
				created_at: '2026-08-19T10:00:00Z',
				events: [],
				tool_calls: [],
				child_runs: [],
				...run,
			},
		],
	}
}

test('normalizes direct tools from a flat NetAI run', () => {
	const message = messageWithRun({
		tool_calls: [
			{
				id: 31,
				tool_name: 'zabbix_get_host_problems',
				input_params: { hostname: 'edge-fw-par-01' },
				output: { problems: [] },
				status: 'success',
				latency_ms: 42,
			},
		],
	})

	const activity = getMessageAgentActivity(message)
	assert.equal(activity.agentName, 'NetAI')
	assert.equal(activity.durationMs, 1250)
	assert.equal(activity.groups[0].connector.label, 'Zabbix')
	assert.equal(activity.tools[0].label, 'Get Host Problems')
	assert.deepEqual(activity.tools[0].output, { problems: [] })
})

test('normalizes live lifecycle events before the durable response is reloaded', () => {
	const message = messageWithRun({
		status: 'running',
		duration_ms: null,
		events: [
			{
				id: 1,
				event_sequence: 1,
				event_type: 'tool_started',
				correlation_id: 'call-1',
				payload: {
					tool_call_id: 'call-1',
					tool_name: 'query_nodes',
					connector: 'infrahub',
					arguments: { kind: 'Device' },
				},
				created_at: '2026-08-19T10:00:00Z',
			},
			{
				id: 2,
				event_sequence: 2,
				event_type: 'tool_completed',
				correlation_id: 'call-1',
				payload: {
					tool_call_id: 'call-1',
					tool_name: 'query_nodes',
					connector: 'infrahub',
					duration_ms: 18,
				},
				created_at: '2026-08-19T10:00:00Z',
			},
		],
	})

	const activity = getMessageAgentActivity(message)
	assert.equal(activity.tools[0].connector.label, 'Infrahub')
	assert.equal(activity.tools[0].status, 'success')
	assert.equal(activity.tools[0].durationMs, 18)
	assert.deepEqual(activity.tools[0].input, { kind: 'Device' })
})

test('keeps an activity history when the Agent answers without tools', () => {
	const activity = getMessageAgentActivity(messageWithRun({ tool_calls: [] }))
	assert.equal(activity.status, 'completed')
	assert.equal(activity.tools.length, 0)
	assert.equal(activity.durationMs, 1250)
})

test('enriches persisted MCP calls with connector identity from durable events', () => {
	const message = messageWithRun({
		tool_calls: [
			{
				id: 33,
				tool_name: 'query_nodes',
				input_params: { kind: 'Device' },
				output: { nodes: [{ name: 'edge-fw-par-01' }] },
				status: 'success',
			},
		],
		events: [
			{
				id: 3,
				event_sequence: 1,
				event_type: 'tool_started',
				correlation_id: 'call-remote',
				payload: {
					tool_call_id: 'call-remote',
					tool_name: 'query_nodes',
					connector: 'infrahub',
					arguments: { kind: 'Device' },
				},
				created_at: '2026-08-19T10:00:00Z',
			},
		],
	})

	const activity = getMessageAgentActivity(message)
	assert.equal(activity.tools[0].connector.label, 'Infrahub')
	assert.deepEqual(activity.tools[0].output, { nodes: [{ name: 'edge-fw-par-01' }] })
})

test('continues to read specialist child runs from historical conversations', () => {
	const message = messageWithRun({
		agent_name: 'orchestrator',
		child_runs: [
			{
				id: 21,
				user_message_id: 9,
				agent_name: 'SuzieQ Specialist',
				status: 'completed',
				created_at: '2026-08-19T10:00:00Z',
				events: [],
				child_runs: [],
				tool_calls: [
					{
						id: 32,
						tool_name: 'suzieq_get_interfaces',
						input_params: { hostname: 'leaf-01' },
						output: { interfaces: [] },
						status: 'success',
					},
				],
			},
		],
	})

	const activity = getMessageAgentActivity(message)
	assert.equal(activity.groups[0].connector.label, 'SuzieQ')
	assert.equal(activity.tools[0].label, 'Get Interfaces')
})
