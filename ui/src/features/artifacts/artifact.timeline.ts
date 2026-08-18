import type { AgentEvent, Message } from '@/types/chat.type'
import type { ArtifactEnvelope, ArtifactStatus, TimelineBlock } from './artifact.types'
import { replaceRenderedUnifiedDiffFences } from './config-diff/config-diff.markdown'

type ArtifactWithPosition = {
	artifact: ArtifactEnvelope
	offset: number
	sequence: number
}

function asRecord(value: unknown): Record<string, unknown> | null {
	if (!value || typeof value !== 'object' || Array.isArray(value)) return null
	return value as Record<string, unknown>
}

function asStatus(value: unknown, fallback: ArtifactStatus = 'running'): ArtifactStatus {
	if (value === 'pending' || value === 'running' || value === 'completed' || value === 'failed' || value === 'cancelled') return value
	return fallback
}

function eventOffset(payload: Record<string, unknown>, contentLength: number): number {
	const value = payload.assistant_offset
	if (typeof value !== 'number' || !Number.isFinite(value)) return contentLength
	return Math.max(0, Math.min(contentLength, Math.floor(value)))
}

function sortedEvents(message: Message): AgentEvent[] {
	return (message.agent_runs ?? [])
		.flatMap(run => run.events ?? [])
		.sort((left, right) => left.event_sequence - right.event_sequence)
}

function collectArtifacts(message: Message): ArtifactWithPosition[] {
	const artifacts = new Map<string, ArtifactWithPosition>()
	const contentLength = message.content.length

	for (const event of sortedEvents(message)) {
		const payload = asRecord(event.payload) ?? {}
		if (event.event_type === 'artifact_snapshot') {
			const rawArtifact = asRecord(payload.artifact)
			if (!rawArtifact) continue
			const id = String(rawArtifact.id ?? '')
			const kind = String(rawArtifact.kind ?? '')
			if (!id || !kind) continue
			const existing = artifacts.get(id)
			artifacts.set(id, {
				artifact: {
					id,
					kind,
					schema_version: Number(rawArtifact.schema_version ?? 1),
					status: asStatus(rawArtifact.status),
					title: String(rawArtifact.title ?? kind),
					data: { ...(asRecord(rawArtifact.data) ?? {}) },
					provenance: { ...(asRecord(rawArtifact.provenance) ?? {}) },
				},
				offset: existing?.offset ?? eventOffset(payload, contentLength),
				sequence: existing?.sequence ?? event.event_sequence,
			})
			continue
		}

		if (event.event_type !== 'artifact_delta') continue
		const artifactId = String(payload.artifact_id ?? '')
		const current = artifacts.get(artifactId)
		if (!current) continue

		const setValues = asRecord(payload.set) ?? {}
		const appendValues = asRecord(payload.append) ?? {}
		const nextData: Record<string, unknown> = {
			...current.artifact.data,
			...setValues,
		}
		for (const [key, value] of Object.entries(appendValues)) {
			if (!Array.isArray(value)) continue
			const existing = nextData[key]
			nextData[key] = [...(Array.isArray(existing) ? existing : []), ...value]
		}

		current.artifact = {
			...current.artifact,
			status: asStatus(payload.status, current.artifact.status),
			data: nextData,
		}
	}

	return [...artifacts.values()].sort((left, right) => left.offset - right.offset || left.sequence - right.sequence)
}

export function hasArtifactEvents(message: Message): boolean {
	return sortedEvents(message).some(event => event.event_type === 'artifact_snapshot')
}

export function hasArtifactKind(message: Message, kind: string): boolean {
	return sortedEvents(message).some(event => {
		if (event.event_type !== 'artifact_snapshot') return false
		const payload = asRecord(event.payload)
		const artifact = asRecord(payload?.artifact)
		return artifact?.kind === kind
	})
}

export function buildArtifactTimeline(message: Message): TimelineBlock[] {
	const artifacts = collectArtifacts(message)
	if (artifacts.length === 0) {
		return [{ id: `message-${message.id}-text`, type: 'markdown', content: message.content }]
	}

	const blocks: TimelineBlock[] = []
	const renderedConfigDiffPatches = artifacts.flatMap(entry => {
		if (entry.artifact.kind !== 'config.diff.v1') return []
		const configDiff = asRecord(entry.artifact.data.config_diff)
		return typeof configDiff?.patch === 'string' ? [configDiff.patch] : []
	})
	const renderMarkdown = (content: string): string => replaceRenderedUnifiedDiffFences(content, renderedConfigDiffPatches)
	let cursor = 0
	artifacts.forEach((entry, index) => {
		if (entry.offset > cursor) {
			const content = renderMarkdown(message.content.slice(cursor, entry.offset))
			if (content.trim()) {
				blocks.push({
					id: `message-${message.id}-text-${cursor}-${entry.offset}`,
					type: 'markdown',
					content,
				})
			}
		}
		blocks.push({
			id: `message-${message.id}-artifact-${entry.artifact.id}-${index}`,
			type: 'artifact',
			artifact: entry.artifact,
		})
		cursor = Math.max(cursor, entry.offset)
	})

	if (cursor < message.content.length) {
		const content = renderMarkdown(message.content.slice(cursor))
		if (content.trim()) {
			blocks.push({
				id: `message-${message.id}-text-${cursor}-tail`,
				type: 'markdown',
				content,
			})
		}
	}

	return blocks
}
