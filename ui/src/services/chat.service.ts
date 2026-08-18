import { AxiosResponse } from 'axios'
import API from './axios'
import { AdminFeedbackItem, ChatAttachment, ChatUserSettings, ContextMetrics, Conversation, ConversationMessages, Message, PromptSnapshot } from '@/types/chat.type'

export const agentUiEventTypes = [
	'tool_started',
	'tool_completed',
	'tool_failed',
	'artifact_snapshot',
	'artifact_delta',
] as const

export type AgentUiEventType = (typeof agentUiEventTypes)[number]

export type AgentUiStreamEvent = {
	type: AgentUiEventType
	event_id?: string
	event_sequence?: number
	run_id?: string
	conversation_id?: string
	emitted_at?: string
	assistant_offset?: number
	[key: string]: unknown
}

const agentUiEventTypeSet = new Set<string>(agentUiEventTypes)

function isAgentUiEventType(value: string): value is AgentUiEventType {
	return agentUiEventTypeSet.has(value)
}

export type StreamEvent =
	| { type: 'assistant_token'; token: string }
	| ({ type: 'context_metrics' } & ContextMetrics)
	| { type: 'orchestrator_decision'; specialists?: string[]; reasoning?: string }
	| { type: 'orchestrator_plan'; plan?: string; specialists?: string[] }
	| { type: 'specialist_plan'; specialist: string; plan?: string }
	| { type: 'specialist_prompt'; specialist: string; prompt?: Record<string, unknown> }
	| {
			type: 'specialist_tool_call'
			specialist: string
			tool_name: string
			arguments?: Record<string, unknown>
	  }
	| { type: 'specialist_evidence'; specialist: string; tool_name: string; result?: Record<string, unknown>; evidence?: unknown[] }
	| { type: 'specialist_tool_result'; specialist: string; tool_name: string; result?: Record<string, unknown> }
	| { type: 'leader_conclusion'; answer?: string }
	| AgentUiStreamEvent
	| { type: 'done'; message_id: number; duration_ms?: number | null }

export type StreamHandlers = {
	onToken?: (token: string) => void
	onContextMetrics?: (payload: ContextMetrics) => void
	onOrchestratorDecision?: (payload: { specialists?: string[]; reasoning?: string }) => void
	onOrchestratorPlan?: (payload: { plan?: string; specialists?: string[] }) => void
	onSpecialistPlan?: (payload: { specialist: string; plan?: string }) => void
	onSpecialistPrompt?: (payload: { specialist: string; prompt?: Record<string, unknown> }) => void
	onSpecialistToolCall?: (payload: { specialist: string; tool_name: string; arguments?: Record<string, unknown> }) => void
	onSpecialistEvidence?: (payload: { specialist: string; tool_name: string; result?: Record<string, unknown>; evidence?: unknown[] }) => void
	onSpecialistToolResult?: (payload: { specialist: string; tool_name: string; result?: Record<string, unknown> }) => void
	onLeaderConclusion?: (payload: { answer?: string }) => void
	onAgentUiEvent?: (event: AgentUiStreamEvent) => void
	onDone?: (payload: { messageId: number; durationMs?: number | null }) => void
}

class ChatService {
	// Conversations
	getConversations(search?: string): Promise<AxiosResponse<Conversation[]>> {
		const normalizedSearch = search?.trim() ?? ''
		return API.get(`/llm/conversations`, {
			params: normalizedSearch ? { search: normalizedSearch } : undefined,
		})
	}
	getConversation(conversation_id: string): Promise<AxiosResponse<ConversationMessages>> {
		return API.get(`/llm/conversation/${conversation_id}`)
	}
	getAdminFeedbacks(limit = 100): Promise<AxiosResponse<AdminFeedbackItem[]>> {
		return API.get(`/llm/admin/feedbacks`, { params: { limit } })
	}
	getChatSettings(): Promise<AxiosResponse<ChatUserSettings>> {
		return API.get(`/llm/settings/chat`)
	}
	updateChatSettings(params: { custom_instructions: string }): Promise<AxiosResponse<ChatUserSettings>> {
		return API.patch(`/llm/settings/chat`, params)
	}
	createConversation(): Promise<AxiosResponse<Conversation>> {
		return API.post(`/llm/conversation`, { title: '' })
	}
	renameConversation(conversation_id: string, title: string): Promise<AxiosResponse<Conversation>> {
		return API.patch(`/llm/conversation/${conversation_id}`, { title: title })
	}
	deleteConversation(conversation_id: string): Promise<AxiosResponse<Conversation>> {
		return API.delete(`/llm/conversation/${conversation_id}`)
	}
	// Chatting
	askLLM(conversation_id: string, params: { content: string }): Promise<AxiosResponse<Message>> {
		return API.post(`/llm/conversation/${conversation_id}/message`, params)
	}
	getPromptPreview(conversation_id: string, params: { content: string }): Promise<AxiosResponse<PromptSnapshot>> {
		return API.post(`/llm/conversation/${conversation_id}/prompt-preview`, params)
	}

	listAttachments(conversation_id: string): Promise<AxiosResponse<ChatAttachment[]>> {
		return API.get(`/llm/conversation/${conversation_id}/attachments`)
	}

	createAttachment(
		conversation_id: string,
		params: { filename: string; content: string; content_type?: string | null },
	): Promise<AxiosResponse<ChatAttachment>> {
		return API.post(`/llm/conversation/${conversation_id}/attachments`, params)
	}

	deleteAttachment(conversation_id: string, attachment_id: number): Promise<AxiosResponse<ChatAttachment>> {
		return API.delete(`/llm/conversation/${conversation_id}/attachments/${attachment_id}`)
	}

	async askLLMStream(conversation_id: string, params: { content: string }, handlers: StreamHandlers = {}): Promise<void> {
		const url = `${API.defaults.baseURL ?? ''}/llm/conversation/${conversation_id}/message/stream`
		const response = await fetch(url, {
			method: 'POST',
			credentials: 'include',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(params),
		})

		if (!response.ok) {
			throw new Error(`Streaming request failed with status ${response.status}`)
		}
		if (!response.body) {
			throw new Error('Streaming response has no body')
		}

		const reader = response.body.getReader()
		const decoder = new TextDecoder()
		let buffer = ''

		const parseEvent = (raw: string): StreamEvent | null => {
			const lines = raw.split('\n')
			let eventName = ''
			let dataValue = ''
			for (const line of lines) {
				if (line.startsWith('event:')) eventName = line.slice(6).trim()
				if (line.startsWith('data:')) dataValue += line.slice(5).trim()
			}
			if (!eventName || !dataValue) return null

			let decodedPayload: unknown
			try {
				decodedPayload = JSON.parse(dataValue)
			} catch {
				return null
			}
			if (!decodedPayload || typeof decodedPayload !== 'object' || Array.isArray(decodedPayload)) return null
			const payload = decodedPayload as Record<string, unknown>

			if (eventName === 'assistant_token') return { type: eventName, token: String(payload.token ?? '') }
			if (eventName === 'context_metrics') return { ...payload, type: eventName } as StreamEvent
			if (eventName === 'orchestrator_decision') return { ...payload, type: eventName } as StreamEvent
			if (eventName === 'orchestrator_plan') return { ...payload, type: eventName } as StreamEvent
			if (eventName === 'specialist_plan') return { ...payload, type: eventName } as StreamEvent
			if (eventName === 'specialist_prompt') return { ...payload, type: eventName } as StreamEvent
			if (eventName === 'specialist_tool_call') return { ...payload, type: eventName } as StreamEvent
			if (eventName === 'specialist_evidence') return { ...payload, type: eventName } as StreamEvent
			if (eventName === 'specialist_tool_result') return { ...payload, type: eventName } as StreamEvent
			if (eventName === 'leader_conclusion') return { ...payload, type: eventName } as StreamEvent
			if (isAgentUiEventType(eventName)) {
				return { ...payload, type: eventName } as AgentUiStreamEvent
			}
			if (eventName === 'done') {
				return {
					type: eventName,
					message_id: Number(payload.message_id),
					duration_ms:
						typeof payload.duration_ms === 'number' ? Number(payload.duration_ms) : null,
				}
			}
			return null
		}

		const dispatchEvent = (parsed: StreamEvent) => {
			if (parsed.type === 'assistant_token') handlers.onToken?.(parsed.token)
			if (parsed.type === 'context_metrics') handlers.onContextMetrics?.(parsed)
			if (parsed.type === 'orchestrator_decision') handlers.onOrchestratorDecision?.(parsed)
			if (parsed.type === 'orchestrator_plan') handlers.onOrchestratorPlan?.(parsed)
			if (parsed.type === 'specialist_plan') handlers.onSpecialistPlan?.(parsed)
			if (parsed.type === 'specialist_prompt') handlers.onSpecialistPrompt?.(parsed)
			if (parsed.type === 'specialist_tool_call') handlers.onSpecialistToolCall?.(parsed)
			if (parsed.type === 'specialist_evidence') handlers.onSpecialistEvidence?.(parsed)
			if (parsed.type === 'specialist_tool_result') handlers.onSpecialistToolResult?.(parsed)
			if (parsed.type === 'leader_conclusion') handlers.onLeaderConclusion?.(parsed)
			if (isAgentUiEventType(parsed.type)) handlers.onAgentUiEvent?.(parsed as AgentUiStreamEvent)
			if (parsed.type === 'done') {
				handlers.onDone?.({
					messageId: parsed.message_id,
					durationMs: parsed.duration_ms ?? null,
				})
			}
		}

		let streamDone = false
		while (!streamDone) {
			const { done, value } = await reader.read()
			streamDone = done
			buffer += decoder.decode(value, { stream: !done })
			buffer = buffer.replace(/\r\n/g, '\n')

			let separatorIndex = buffer.indexOf('\n\n')
			while (separatorIndex !== -1) {
				const rawEvent = buffer.slice(0, separatorIndex)
				buffer = buffer.slice(separatorIndex + 2)
				const parsed = parseEvent(rawEvent)
				if (parsed) dispatchEvent(parsed)
				separatorIndex = buffer.indexOf('\n\n')
			}
		}
	}

	submitFeedback(
		messageId: number,
		params: {
			rating: 'good' | 'bad'
			feedback_type?:
				| 'wrong_diagnosis'
				| 'hallucination'
				| 'correct_but_incomplete'
				| 'irrelevant_specialist'
				| 'wrong_toolcall_use'
				| 'other'
			feedback_types?: Array<
				| 'wrong_diagnosis'
				| 'hallucination'
				| 'correct_but_incomplete'
				| 'irrelevant_specialist'
				| 'wrong_toolcall_use'
				| 'other'
			>
			comment?: string | null
		},
	): Promise<AxiosResponse<void>> {
		return API.post(`/llm/messages/${messageId}/feedback`, params)
	}
}

export default new ChatService()
