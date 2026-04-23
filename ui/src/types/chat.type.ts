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

export interface AgentEvent {
	id: number
	event_sequence: number
	event_type: string
	actor_type?: string
	actor_name?: string
	correlation_id?: string
	payload?: Record<string, unknown>
	created_at: string
}

export interface AgentRun {
	id: number
	user_message_id: number
	assistant_message_id?: number
	status: 'running' | 'completed' | 'failed'
	final_answer?: string
	context_metrics?: Record<string, unknown>
	error?: string
	ended_at?: string
	created_at: string
	events: AgentEvent[]
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
export type FeedbackRating = 'good' | 'bad'
export type FeedbackType =
	| 'wrong_diagnosis'
	| 'hallucination'
	| 'correct_but_incomplete'
	| 'irrelevant_specialist'
	| 'wrong_toolcall_use'
	| 'other'

export interface Feedback {
	id: number
	rating: FeedbackRating
	feedback_type?: FeedbackType | null
	comment?: string | null
	created_at: string
	updated_at: string
}

export interface Message {
	id: number
	role: MessageRole
	content: string
	created_at: string
	agent_runs: AgentRun[]
	feedback: Feedback[]
}

export interface Conversation {
	id: string
	title: string
	created_at: string
}

export interface ConversationMessages {
	id: string
	title: string
	messages: Message[]
	created_at: string
}
