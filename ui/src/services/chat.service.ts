import { AxiosResponse } from 'axios'
import API from './axios'
import { ContextMetrics, Conversation, ConversationMessages, Message } from '@/types/chat.type'

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
	| { type: 'done'; message_id: number }

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
	onDone?: (messageId: number) => void
}

class ChatService {
	// Conversations
	getConversations(): Promise<AxiosResponse<Conversation[]>> {
		return API.get(`/llm/conversations`)
	}
	getConversation(conversation_id: string): Promise<AxiosResponse<ConversationMessages>> {
		return API.get(`/llm/conversation/${conversation_id}`)
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

			let payload: any = null
			try {
				payload = JSON.parse(dataValue)
			} catch {
				return null
			}

			if (eventName === 'assistant_token') return { type: eventName, token: String(payload?.token ?? '') }
			if (eventName === 'context_metrics') return { type: eventName, ...payload }
			if (eventName === 'orchestrator_decision') return { type: eventName, ...payload }
			if (eventName === 'orchestrator_plan') return { type: eventName, ...payload }
			if (eventName === 'specialist_plan') return { type: eventName, ...payload }
			if (eventName === 'specialist_prompt') return { type: eventName, ...payload }
			if (eventName === 'specialist_tool_call') return { type: eventName, ...payload }
			if (eventName === 'specialist_evidence') return { type: eventName, ...payload }
			if (eventName === 'specialist_tool_result') return { type: eventName, ...payload }
			if (eventName === 'leader_conclusion') return { type: eventName, ...payload }
			if (eventName === 'done') return { type: eventName, message_id: Number(payload?.message_id) }
			return null
		}

		while (true) {
			const { done, value } = await reader.read()
			if (done) break
			buffer += decoder.decode(value, { stream: true })

			while (true) {
				const separatorIndex = buffer.indexOf('\n\n')
				if (separatorIndex === -1) break
				const rawEvent = buffer.slice(0, separatorIndex)
				buffer = buffer.slice(separatorIndex + 2)
				const parsed = parseEvent(rawEvent)
				if (!parsed) continue

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
				if (parsed.type === 'done') handlers.onDone?.(parsed.message_id)
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
