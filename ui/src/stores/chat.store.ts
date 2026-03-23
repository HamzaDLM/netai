import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ContextMetrics, Conversation, ConversationMessages, Evidence, Message, MessageRole, ToolCall } from '@/types/chat.type'
import chatService from '@/services/chat.service'
import { toast } from '@/components/ui/toast'

let localIdCounter = 1000

function nextId(): number {
	localIdCounter += 1
	return localIdCounter
}

function createMessage(role: MessageRole, content: string): Message {
	return {
		id: nextId(),
		role,
		content,
		created_at: new Date().toISOString(),
		tool_calls: [],
	}
}

export const useChatStore = defineStore('chat', function chatStore() {
	const conversations = ref<Conversation[]>([])
	const selectedConversation = ref<ConversationMessages | null>(null)
	const isLoading = ref(false)
	const isSyncing = ref(false)
	const isStreamingResponse = ref(false)
	const streamingAssistantMessageId = ref<number | null>(null)
	const errorMessage = ref<string | null>(null)
	const contextWindow = ref<ContextMetrics | null>()

	const hasConversations = computed(function () {
		return conversations.value.length > 0
	})

	const messages = computed(function () {
		return selectedConversation.value?.messages ?? []
	})

	const isMessageStreaming = computed(function () {
		return function (messageId: number): boolean {
			return isStreamingResponse.value && streamingAssistantMessageId.value === messageId
		}
	})

	async function loadConversations(): Promise<void> {
		isLoading.value = true
		errorMessage.value = null

		try {
			const result = await chatService.getConversations()
			conversations.value = result.data
			if (conversations.value.length > 0) {
				selectConversation(conversations.value[0].id)
			}
		} catch (err) {
			errorMessage.value = 'Failed to load conversations'
			toast({ title: errorMessage.value, variant: 'destructive' })
		} finally {
			isLoading.value = false
		}
	}

	async function selectConversation(conversationId: number): Promise<void> {
		isSyncing.value = true
		errorMessage.value = null

		try {
			const existing = selectedConversation.value?.id === conversationId
			if (existing) return

			const result = await chatService.getConversation(conversationId)
			selectedConversation.value = result.data
		} catch (err) {
			errorMessage.value = 'Failed to load conversation'
			toast({ title: errorMessage.value, variant: 'destructive' })
		} finally {
			isSyncing.value = false
		}
	}

	function setSelectedConversation(conversation: ConversationMessages | null): void {
		selectedConversation.value = conversation
	}

	async function createConversation(): Promise<void> {
		try {
			const result = await chatService.createConversation()
			conversations.value.unshift(result.data)
			selectConversation(result.data.id)
		} catch (err) {
			errorMessage.value = 'Failed to create conversation'
			toast({ title: errorMessage.value, variant: 'destructive' })
		}
	}

	async function renameConversation(conversation_id: number, title: string): Promise<void> {
		try {
			await chatService.renameConversation(conversation_id, title)
			conversations.value.map(convo => (convo.id === conversation_id ? { ...convo, title: title } : convo))
		} catch (err) {
			errorMessage.value = 'Failed to rename conversation'
			toast({ title: errorMessage.value, variant: 'destructive' })
		}
	}

	async function deleteConversation(conversation_id: number): Promise<void> {
		try {
			await chatService.deleteConversation(conversation_id)
			conversations.value.filter(convo => convo.id !== conversation_id)
		} catch (err) {
			errorMessage.value = 'Failed to delete conversation'
			toast({ title: errorMessage.value, variant: 'destructive' })
		}
	}

	async function askLLM(userQuestion: string): Promise<void> {
		if (!selectedConversation.value) return
		try {
			addUserMessage(userQuestion)
			const assistantDraft = createMessage('assistant', '')
			addMessage(assistantDraft)
			let trackedAssistantId = assistantDraft.id
			isStreamingResponse.value = true
			streamingAssistantMessageId.value = trackedAssistantId
			let pendingTokenText = ''
			let flushTimer: ReturnType<typeof setTimeout> | null = null

			const getAssistantMessage = () => {
				if (!selectedConversation.value) return null
				return selectedConversation.value.messages.find(message => message.id === trackedAssistantId && message.role === 'assistant') ?? null
			}

			const flushPendingTokens = () => {
				const assistant = getAssistantMessage()
				if (!assistant) {
					flushTimer = null
					return
				}
				if (!pendingTokenText) {
					flushTimer = null
					return
				}

				// Render progressively (typewriter feel) while adapting speed when the buffer grows.
				const charsPerTick = Math.min(14, Math.max(2, Math.ceil(pendingTokenText.length / 40)))
				assistant.content += pendingTokenText.slice(0, charsPerTick)
				pendingTokenText = pendingTokenText.slice(charsPerTick)
				flushTimer = setTimeout(flushPendingTokens, 16)
			}

			const ensureFlushLoop = () => {
				if (flushTimer != null) return
				flushTimer = setTimeout(flushPendingTokens, 16)
			}

			const extractSource = (toolName?: string): string | undefined => {
				if (!toolName || !toolName.includes('.')) return undefined
				const source = toolName.split('.', 1)[0]
				return source || undefined
			}

			const toEvidence = (items: unknown[] | undefined): Evidence[] => {
				if (!Array.isArray(items)) return []
				return items.map((item, index) => {
					const row = item as Record<string, unknown>
					return {
						id: Number(row.id ?? nextId() + index),
						source_type: String(row.type ?? row.source_type ?? 'tool_result'),
						source_ref: row.ref ? String(row.ref) : row.source_ref ? String(row.source_ref) : undefined,
						content_snippet: String(row.content ?? row.content_snippet ?? ''),
						score: typeof row.score === 'number' ? row.score : undefined,
						timestamp: row.timestamp ? String(row.timestamp) : undefined,
					}
				})
			}

			await chatService.askLLMStream(
				selectedConversation.value.id,
				{ content: userQuestion },
				{
					onToken: token => {
						pendingTokenText += token
						ensureFlushLoop()
					},
					onToolCall: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						const toolCall: ToolCall = {
							id: nextId(),
							tool_name: payload.name ?? 'Unnamed',
							tool_source: extractSource(payload.name),
							arguments: payload.arguments ?? {},
							result: payload.result,
							evidence_items: toEvidence(payload.evidence),
						}
						assistant.tool_calls.push(toolCall)
					},
					onToolResult: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						const existing = [...assistant.tool_calls].reverse().find(tool => tool.tool_name === payload.name)
						if (existing) {
							existing.result = payload.result
							return
						}
						assistant.tool_calls.push({
							id: nextId(),
							tool_name: payload.name ?? 'Unnamed',
							tool_source: extractSource(payload.name),
							arguments: {},
							result: payload.result,
							evidence_items: [],
						})
					},
					onDone: messageId => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						assistant.id = messageId
						trackedAssistantId = messageId
						streamingAssistantMessageId.value = messageId
					},
					onContextMetrics: payload => {
						contextWindow.value = payload
					},
				}
			)

			// Ensure all buffered text is rendered before ending this action.
			while (pendingTokenText.length > 0 || flushTimer !== null) {
				await new Promise(resolve => setTimeout(resolve, 20))
			}
		} catch (err) {
			errorMessage.value = 'Something went wrong'
			toast({ title: errorMessage.value, variant: 'destructive' })
		} finally {
			isStreamingResponse.value = false
			streamingAssistantMessageId.value = null
		}
	}

	function addMessage(message: Message): void {
		if (!selectedConversation.value) return
		selectedConversation.value.messages.push(message)
	}

	function addUserMessage(content: string): void {
		addMessage(createMessage('user', content))
	}

	function addAssistantMessage(content: string): void {
		addMessage(createMessage('assistant', content))
	}

	function appendAssistantToken(token: string): void {
		if (!selectedConversation.value) return
		const last = selectedConversation.value.messages.at(-1)
		if (!last || last.role !== 'assistant') {
			addAssistantMessage(token)
			return
		}
		last.content += token
	}

	function replaceAssistantMessage(messageId: number, content: string): void {
		if (!selectedConversation.value) return
		const message = selectedConversation.value.messages.find(item => item.id === messageId)
		if (!message || message.role !== 'assistant') return
		message.content = content
	}

	function clearSelectedConversation(): void {
		selectedConversation.value = null
	}

	function resetChatState(): void {
		conversations.value = []
		selectedConversation.value = null
		isLoading.value = false
		isSyncing.value = false
		isStreamingResponse.value = false
		streamingAssistantMessageId.value = null
		errorMessage.value = null
	}

	return {
		conversations,
		selectedConversation,
		isLoading,
		isSyncing,
		isStreamingResponse,
		streamingAssistantMessageId,
		errorMessage,
		hasConversations,
		messages,
		isMessageStreaming,
		contextWindow,
		loadConversations,
		selectConversation,
		setSelectedConversation,
		renameConversation,
		deleteConversation,
		createConversation,
		addMessage,
		addUserMessage,
		addAssistantMessage,
		appendAssistantToken,
		replaceAssistantMessage,
		clearSelectedConversation,
		resetChatState,
		askLLM,
		askLLMStream: askLLM,
	}
})
