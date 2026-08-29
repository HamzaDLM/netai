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
	run_id?: number
	conversation_id?: string
	tool_name: string
	input_params?: Record<string, unknown>
	output?: Record<string, unknown> | null
	status?: string
	error_type?: string | null
	error_message?: string | null
	latency_ms?: number | null
	created_at?: string
	// Compatibility aliases used by conversations created before the Haystack 3 migration.
	tool_source?: string
	arguments?: Record<string, unknown>
	result?: Record<string, unknown>
	evidence?: Evidence[]
	evidence_items?: Evidence[]
}

export interface SubAgentCall {
	id: number
	parent_run_id: number
	child_run_id?: number | null
	specialist_name: string
	call_sequence: number
	task_prompt: string
	result_summary?: string | null
	status: string
	created_at: string
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
	conversation_id?: string
	user_message_id: number
	assistant_message_id?: number
	parent_run_id?: number | null
	agent_type?: string
	agent_name?: string
	depth?: number
	status: 'running' | 'completed' | 'failed'
	started_at?: string
	final_answer?: string
	context_metrics?: Record<string, unknown>
	error?: string
	ended_at?: string
	duration_ms?: number | null
	created_at: string
	updated_at?: string
	events: AgentEvent[]
	sub_agent_calls?: SubAgentCall[]
	child_runs?: AgentRun[]
	tool_calls?: ToolCall[]
}

export interface ContextBreakdownBucket {
	tokens: number
}

export interface ContextBreakdown {
	system: ContextBreakdownBucket
	user: ContextBreakdownBucket
	assistant: ContextBreakdownBucket
	tools: ContextBreakdownBucket
	documents: ContextBreakdownBucket
}

export interface ContextMetrics {
	context_window: number
	used_tokens: number
	used_percent: number
	left_tokens: number
	left_percent: number
	compacted: boolean
	summary_id?: number | null
	breakdown?: ContextBreakdown
}

export interface PromptSnapshotMessage {
	index: number
	role: string
	source: string
	text: string
	estimated_tokens: number
	message_id?: number | null
	summary_id?: number | null
	up_to_message_id?: number | null
}

export interface PromptSnapshot {
	messages: PromptSnapshotMessage[]
	metrics: ContextMetrics
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

export interface ChatAttachment {
	id: number
	conversation_id: string
	filename: string
	content_type?: string | null
	size_bytes: number
	estimated_tokens: number
	truncated: boolean
	active: boolean
	created_at: string
	updated_at: string
}

export interface ChatUserSettings {
	custom_instructions: string
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

export interface AdminFeedbackConversation {
	id: string
	title?: string | null
	created_at: string
	updated_at: string
}

export interface AdminFeedbackItem {
	feedback: Feedback & { feedback_types: FeedbackType[] }
	conversation: AdminFeedbackConversation
	user_message?: Message | null
	assistant_message: Message
}

export interface AdminOverview {
	window_started_at: string
	generated_at: string
	conversations: number
	user_messages: number
	tool_calls_total: number
	tool_calls_failed: number
	average_latency_ms?: number | null
	feedback_total: number
	negative_feedback: number
	message_volume: Array<{ date: string; hour: number; count: number }>
}
