export interface Evidence {
	id: number
	source_type: string
	source_ref?: string
	content_snippet: string
	score?: number
	timestamp?: string
}

export interface ToolCall {
	id: number
	tool_name: string
	tool_source?: string
	arguments: object
	result?: object
	latency_ms?: number
	evidence?: Evidence[]
	evidence_items?: Evidence[]
}

export interface ContextMetrics {
	context_window: number
	used_tokens: number
	used_percent: number
	left_tokens: number
	left_percent: number
	compacted: boolean
	summary_id?: number | null
}

export type MessageRole = 'user' | 'assistant' | 'system'

export interface Message {
	id: number
	role: MessageRole
	content: string
	created_at: string
	tool_calls: ToolCall[]
}

export interface Conversation {
	id: number
	title: string
	created_at: string
}

export interface ConversationMessages {
	id: number
	title: string
	messages: Message[]
	created_at: string
}
