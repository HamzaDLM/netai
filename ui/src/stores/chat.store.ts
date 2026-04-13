import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { AgentRun, ContextMetrics, Conversation, ConversationMessages, Message, MessageRole } from '@/types/chat.type'
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
		agent_runs: [],
	}
}

function normalizeConversationMessages(data: ConversationMessages): ConversationMessages {
	return {
		...data,
		messages: (data.messages ?? []).map(message => ({
			...message,
			agent_runs: message.agent_runs ?? [],
		})),
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
				await selectConversation(conversations.value[0].id)
			} else {
				await createConversation()
				await selectConversation(conversations.value[0].id)
			}
		} catch (err) {
			errorMessage.value = 'Failed to load conversations'
			toast({ title: errorMessage.value, variant: 'destructive' })
		} finally {
			isLoading.value = false
		}
	}

	async function selectConversation(conversationId: string): Promise<void> {
		isSyncing.value = true
		errorMessage.value = null

		try {
			const existing = selectedConversation.value?.id === conversationId
			if (existing) return

			const result = await chatService.getConversation(conversationId)
			selectedConversation.value = normalizeConversationMessages(result.data)
		} catch (err) {
			errorMessage.value = 'Failed to load conversation'
			toast({ title: errorMessage.value, variant: 'destructive' })
		} finally {
			isSyncing.value = false
		}
	}

	function setSelectedConversation(conversation: ConversationMessages | null): void {
		selectedConversation.value = conversation
			? normalizeConversationMessages(conversation)
			: null
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

	async function renameConversation(conversation_id: string, title: string): Promise<void> {
		try {
			await chatService.renameConversation(conversation_id, title)
			conversations.value.map(convo => (convo.id === conversation_id ? { ...convo, title: title } : convo))
		} catch (err) {
			errorMessage.value = 'Failed to rename conversation'
			toast({ title: errorMessage.value, variant: 'destructive' })
		}
	}

	async function deleteConversation(conversation_id: string): Promise<void> {
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

			const ensureDraftRun = (assistant: Message): AgentRun => {
				const existing = assistant.agent_runs.at(-1)
				if (existing) return existing

				const run: AgentRun = {
					id: nextId(),
					user_message_id: 0,
					assistant_message_id: assistant.id,
					status: 'running',
					final_answer: undefined,
					context_metrics: undefined,
					error: undefined,
					ended_at: undefined,
					created_at: new Date().toISOString(),
					events: [],
				}
				assistant.agent_runs.push(run)
				return run
			}

			const pushRunEvent = (
				assistant: Message,
				eventType: string,
				payload: Record<string, unknown>,
				actorName?: string
			) => {
				const run = ensureDraftRun(assistant)
				const event_sequence = (run.events.at(-1)?.event_sequence ?? 0) + 1
				run.events.push({
					id: nextId(),
					event_sequence,
					event_type: eventType,
					actor_type: actorName ? 'specialist' : 'orchestrator',
					actor_name: actorName,
					correlation_id: undefined,
					payload,
					created_at: new Date().toISOString(),
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
					onThinking: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(assistant, 'thinking', {
							agent: payload.agent,
							status: payload.status,
							message: payload.message,
						}, payload.agent)
					},
					onOrchestratorPlan: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(assistant, 'orchestrator_plan', {
							plan: payload.plan,
							specialists: payload.specialists,
						})
					},
					onSpecialistPrompt: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(
							assistant,
							'specialist_prompt',
							{ prompt: payload.prompt },
							payload.specialist
						)
					},
					onSpecialistThought: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(
							assistant,
							'specialist_thought',
							{ thought: payload.thought },
							payload.specialist
						)
					},
					onSpecialistToolCall: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(assistant, 'specialist_tool_call', {
							specialist: payload.specialist,
							tool_name: payload.tool_name,
							arguments: payload.arguments ?? {},
							evidence: payload.evidence ?? [],
						})
					},
					onSpecialistToolResult: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(assistant, 'specialist_tool_result', {
							specialist: payload.specialist,
							tool_name: payload.tool_name,
							result: payload.result,
						})
					},
					onLeaderConclusion: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(assistant, 'leader_conclusion', {
							answer: payload.answer,
						})
						if (!assistant.content && payload.answer) {
							assistant.content = payload.answer
						}
					},
					onDone: messageId => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						assistant.id = messageId
						for (const run of assistant.agent_runs) {
							run.assistant_message_id = messageId
							if (run.status === 'running') run.status = 'completed'
							if (!run.ended_at) run.ended_at = new Date().toISOString()
						}
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
