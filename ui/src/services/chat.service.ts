import { AxiosResponse } from 'axios'
import API from './axios'
import { AdminFeedbackItem, AdminOverview, ChatAttachment, ChatUserSettings, ContextMetrics, Conversation, ConversationMessages, Message, PromptSnapshot } from '@/types/chat.type'

export const agentRuntimeEventTypes = [
	'run_started',
	'run_finished',
	'run_error',
	'tool_started',
	'tool_completed',
	'tool_failed',
	'artifact_snapshot',
	'artifact_delta',
] as const

export type AgentRuntimeEventType = (typeof agentRuntimeEventTypes)[number]

export type AgentRuntimeStreamEvent = {
	type: AgentRuntimeEventType
	event_id?: string
	event_sequence?: number
	run_id?: string
	conversation_id?: string
	emitted_at?: string
	assistant_offset?: number
	[key: string]: unknown
}

const agentRuntimeEventTypeSet = new Set<string>(agentRuntimeEventTypes)

function isAgentRuntimeEventType(value: string): value is AgentRuntimeEventType {
	return agentRuntimeEventTypeSet.has(value)
}

export type StreamEvent =
	| { type: 'assistant_token'; token: string }
	| ({ type: 'context_metrics' } & ContextMetrics)
	| AgentRuntimeStreamEvent
	| { type: 'run_accepted'; run_id: number; user_message_id: number; assistant_message_id: number }
	| { type: 'done'; message_id: number; run_id: number; duration_ms?: number | null; status: 'completed' | 'failed' }

export type StreamHandlers = {
	onToken?: (token: string) => void
	onContextMetrics?: (payload: ContextMetrics) => void
	onAgentEvent?: (event: AgentRuntimeStreamEvent) => void
	onAccepted?: (payload: { runId: number; userMessageId: number; assistantMessageId: number }) => void
	onDone?: (payload: { messageId: number; runId: number; durationMs?: number | null; status: 'completed' | 'failed' }) => void
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
	getAdminOverview(): Promise<AxiosResponse<AdminOverview>> {
		return API.get(`/llm/admin/overview`)
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
	getPromptPreview(conversation_id: string, params: { content: string; include_draft: boolean; user_message_id?: number }): Promise<AxiosResponse<PromptSnapshot>> {
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
			if (eventName === 'run_accepted') {
				return {
					type: eventName,
					run_id: Number(payload.run_id),
					user_message_id: Number(payload.user_message_id),
					assistant_message_id: Number(payload.assistant_message_id),
				}
			}
			if (isAgentRuntimeEventType(eventName)) {
				return { ...payload, type: eventName } as AgentRuntimeStreamEvent
			}
			if (eventName === 'done') {
				return {
					type: eventName,
					message_id: Number(payload.message_id),
					run_id: Number(payload.run_id),
					duration_ms: typeof payload.duration_ms === 'number' ? Number(payload.duration_ms) : null,
					status: payload.status === 'failed' ? 'failed' : 'completed',
				}
			}
			return null
		}

		const dispatchEvent = (parsed: StreamEvent) => {
			if (parsed.type === 'assistant_token') handlers.onToken?.(parsed.token)
			if (parsed.type === 'context_metrics') handlers.onContextMetrics?.(parsed)
			if (isAgentRuntimeEventType(parsed.type)) handlers.onAgentEvent?.(parsed as AgentRuntimeStreamEvent)
			if (parsed.type === 'run_accepted') {
				handlers.onAccepted?.({
					runId: parsed.run_id,
					userMessageId: parsed.user_message_id,
					assistantMessageId: parsed.assistant_message_id,
				})
			}
			if (parsed.type === 'done') {
				handlers.onDone?.({
					messageId: parsed.message_id,
					runId: parsed.run_id,
					durationMs: parsed.duration_ms ?? null,
					status: parsed.status,
				})
			}
		}

		let streamDone = false
		let receivedDone = false
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
				if (parsed) {
					dispatchEvent(parsed)
					if (parsed.type === 'done') receivedDone = true
				}
				separatorIndex = buffer.indexOf('\n\n')
			}
		}
		if (!receivedDone) throw new Error('Streaming connection closed before the agent run finished')
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
