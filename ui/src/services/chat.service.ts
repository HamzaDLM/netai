import { AxiosResponse } from 'axios'
import API from './axios'
import { ContextMetrics, Conversation, ConversationMessages, Message } from '@/types/chat.type'

export type StreamEvent =
	| { type: 'assistant_token'; token: string }
	| ({ type: 'context_metrics' } & ContextMetrics)
	| { type: 'tool_call'; name: string; arguments?: Record<string, unknown>; result?: Record<string, unknown>; evidence?: unknown[] }
	| { type: 'tool_result'; name: string; result?: Record<string, unknown> }
	| { type: 'done'; message_id: number }

export type StreamHandlers = {
	onToken?: (token: string) => void
	onContextMetrics?: (payload: ContextMetrics) => void
	onToolCall?: (payload: { name: string; arguments?: Record<string, unknown>; result?: Record<string, unknown>; evidence?: unknown[] }) => void
	onToolResult?: (payload: { name: string; result?: Record<string, unknown> }) => void
	onDone?: (messageId: number) => void
}

class ChatService {
	// Conversations
	getConversations(): Promise<AxiosResponse<Conversation[]>> {
		return API.get(`/llm/conversations`)
	}
	getConversation(conversation_id: number): Promise<AxiosResponse<ConversationMessages>> {
		return API.get(`/llm/conversation/${conversation_id}`)
	}
	createConversation(): Promise<AxiosResponse<Conversation>> {
		return API.post(`/llm/conversation`, { title: '' })
	}
	renameConversation(conversation_id: number, title: string): Promise<AxiosResponse<Conversation>> {
		return API.patch(`/llm/conversation/${conversation_id}`, { title: title })
	}
	deleteConversation(conversation_id: number): Promise<AxiosResponse<Conversation>> {
		return API.delete(`/llm/conversation/${conversation_id}`)
	}
	// Chatting
	askLLM(conversation_id: number, params: { content: string }): Promise<AxiosResponse<Message>> {
		return API.post(`/llm/conversation/${conversation_id}/message`, params)
	}

	async askLLMStream(conversation_id: number, params: { content: string }, handlers: StreamHandlers = {}): Promise<void> {
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

			if (eventName === 'assistant_token') return { type: 'assistant_token', token: String(payload?.token ?? '') }
			if (eventName === 'context_metrics') return { type: 'context_metrics', ...payload }
			if (eventName === 'tool_call') return { type: 'tool_call', ...payload }
			if (eventName === 'tool_result') return { type: 'tool_result', ...payload }
			if (eventName === 'done') return { type: 'done', message_id: Number(payload?.message_id) }
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
				if (parsed.type === 'tool_call') handlers.onToolCall?.(parsed)
				if (parsed.type === 'tool_result') handlers.onToolResult?.(parsed)
				if (parsed.type === 'done') handlers.onDone?.(parsed.message_id)
			}
		}
	}

	submitFeedback(messageId: number, params: { rating?: 'good' | 'bad'; comment?: string | null }): Promise<AxiosResponse<void>> {
		return API.post(`/llm/messages/${messageId}/feedback`, params)
	}
}

export default new ChatService()
