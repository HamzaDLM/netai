export type ArtifactStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface ArtifactProvenance {
	source?: string
	target?: string
	started_at?: string
	finished_at?: string
	duration_ms?: number
	simulated?: boolean
	truncated?: boolean
	redacted?: boolean
	[key: string]: unknown
}

export interface ArtifactEnvelope {
	id: string
	kind: string
	schema_version: number
	status: ArtifactStatus
	title: string
	data: Record<string, unknown>
	provenance: ArtifactProvenance
}

export type TimelineBlock =
	| {
			id: string
			type: 'markdown'
			content: string
	  }
	| {
			id: string
			type: 'artifact'
			artifact: ArtifactEnvelope
	  }
