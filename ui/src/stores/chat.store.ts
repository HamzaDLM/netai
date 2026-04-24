import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type {
	AgentRun,
	ChatAttachment,
	ContextBreakdown,
	ContextMetrics,
	Conversation,
	ConversationMessages,
	Message,
	MessageRole,
} from '@/types/chat.type'
import chatService from '@/services/chat.service'
import { toast } from '@/components/ui/toast'

let localIdCounter = 1000
const supportedAttachmentExtensions = new Set(['conf', 'cfg', 'csv', 'ini', 'json', 'log', 'md', 'txt', 'yaml', 'yml'])

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
		feedback: [],
	}
}

function normalizeConversationMessages(data: ConversationMessages): ConversationMessages {
	return {
		...data,
		messages: (data.messages ?? []).map(message => ({
			...message,
			agent_runs: message.agent_runs ?? [],
			feedback: message.feedback ?? [],
		})),
	}
}

function asContextBreakdown(value: unknown): ContextBreakdown | undefined {
	if (!value || typeof value !== 'object') return undefined
	const row = value as Record<string, unknown>
	const readBucket = (key: string) => {
		const bucket = row[key]
		if (!bucket || typeof bucket !== 'object') return null
		const bucketRow = bucket as Record<string, unknown>
		return typeof bucketRow.tokens === 'number' ? { tokens: bucketRow.tokens } : null
	}

	const system = readBucket('system')
	const user = readBucket('user')
	const assistant = readBucket('assistant')
	const tools = readBucket('tools')
	const documents = readBucket('documents')

	if (!system || !user || !assistant || !tools || !documents) return undefined

	return {
		system,
		user,
		assistant,
		tools,
		documents,
	}
}

function asContextMetrics(value: unknown): ContextMetrics | null {
	if (!value || typeof value !== 'object') return null
	const row = value as Record<string, unknown>
	if (
		typeof row.context_window !== 'number' ||
		typeof row.used_tokens !== 'number' ||
		typeof row.used_percent !== 'number' ||
		typeof row.left_tokens !== 'number' ||
		typeof row.left_percent !== 'number' ||
		typeof row.compacted !== 'boolean'
	) {
		return null
	}
	return {
		context_window: row.context_window,
		used_tokens: row.used_tokens,
		used_percent: row.used_percent,
		left_tokens: row.left_tokens,
		left_percent: row.left_percent,
		compacted: row.compacted,
		summary_id: typeof row.summary_id === 'number' || row.summary_id === null ? row.summary_id : undefined,
		breakdown: asContextBreakdown(row.breakdown),
	}
}

function extractLatestContextMetrics(conversation: ConversationMessages | null): ContextMetrics | null {
	if (!conversation) return null
	for (let i = conversation.messages.length - 1; i >= 0; i -= 1) {
		const message = conversation.messages[i]
		for (let j = (message.agent_runs?.length ?? 0) - 1; j >= 0; j -= 1) {
			const metrics = asContextMetrics(message.agent_runs[j]?.context_metrics)
			if (metrics) return metrics
		}
	}
	return null
}

export const useChatStore = defineStore('chat', function chatStore() {
	const conversations = ref<Conversation[]>([])
	const selectedConversation = ref<ConversationMessages | null>(null)
	const conversationSearchQuery = ref('')
	const isLoading = ref(false)
	const isSyncing = ref(false)
	const isStreamingResponse = ref(false)
	const streamingAssistantMessageId = ref<number | null>(null)
	const errorMessage = ref<string | null>(null)
	const contextWindow = ref<ContextMetrics | null>(null)
	const attachments = ref<ChatAttachment[]>([])
	const isUploadingAttachment = ref(false)

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

	type LoadConversationsOptions = {
		searchQuery?: string
		autoSelectFirst?: boolean
		createIfEmpty?: boolean
		preserveSelection?: boolean
	}

	async function loadConversations(options: LoadConversationsOptions = {}): Promise<void> {
		const nextSearchQuery = options.searchQuery ?? conversationSearchQuery.value
		const normalizedSearchQuery = nextSearchQuery.trim()
		conversationSearchQuery.value = nextSearchQuery
		isLoading.value = true
		errorMessage.value = null

		try {
			const result = await chatService.getConversations(normalizedSearchQuery)
			conversations.value = result.data
			const preserveSelection = options.preserveSelection ?? true
			const shouldAutoSelectFirst = options.autoSelectFirst ?? normalizedSearchQuery.length === 0
			const shouldCreateIfEmpty = options.createIfEmpty ?? normalizedSearchQuery.length === 0
			const selectedConversationId = selectedConversation.value?.id ?? null
			const hasVisibleSelection =
				selectedConversationId !== null &&
				conversations.value.some(conversation => conversation.id === selectedConversationId)

			if (hasVisibleSelection && preserveSelection) {
				return
			}

			if (conversations.value.length > 0) {
				if (shouldAutoSelectFirst) {
					await selectConversation(conversations.value[0].id)
				}
			} else if (shouldCreateIfEmpty) {
				await createConversation()
				if (conversations.value.length > 0) {
					await selectConversation(conversations.value[0].id)
				}
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
			contextWindow.value = extractLatestContextMetrics(selectedConversation.value)
			await loadAttachments(conversationId)
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
		contextWindow.value = extractLatestContextMetrics(selectedConversation.value)
		if (!conversation) attachments.value = []
	}

	async function createConversation(): Promise<void> {
		try {
			const result = await chatService.createConversation()
			if (!conversationSearchQuery.value.trim()) {
				conversations.value.unshift(result.data)
			}
			await selectConversation(result.data.id)
		} catch (err) {
			errorMessage.value = 'Failed to create conversation'
			toast({ title: errorMessage.value, variant: 'destructive' })
		}
	}

	async function setConversationSearchQuery(searchQuery: string): Promise<void> {
		await loadConversations({
			searchQuery,
			autoSelectFirst: false,
			createIfEmpty: false,
			preserveSelection: true,
		})
	}

	async function renameConversation(conversation_id: string, title: string): Promise<void> {
		try {
			await chatService.renameConversation(conversation_id, title)
			conversations.value = conversations.value.map(convo => (convo.id === conversation_id ? { ...convo, title: title } : convo))
		} catch (err) {
			errorMessage.value = 'Failed to rename conversation'
			toast({ title: errorMessage.value, variant: 'destructive' })
		}
	}

	async function deleteConversation(conversation_id: string): Promise<void> {
		try {
			await chatService.deleteConversation(conversation_id)
			conversations.value = conversations.value.filter(convo => convo.id !== conversation_id)
		} catch (err) {
			errorMessage.value = 'Failed to archive conversation'
			toast({ title: errorMessage.value, variant: 'destructive' })
		}
	}

	async function loadAttachments(conversationId?: string): Promise<void> {
		const targetConversationId = conversationId ?? selectedConversation.value?.id
		if (!targetConversationId) {
			attachments.value = []
			return
		}

		try {
			const result = await chatService.listAttachments(targetConversationId)
			attachments.value = result.data
		} catch (err) {
			attachments.value = []
			toast({ title: 'Failed to load attachments', variant: 'destructive' })
		}
	}

	async function uploadAttachment(file: File): Promise<void> {
		if (!selectedConversation.value) return
		const extension = file.name.includes('.') ? file.name.split('.').pop()?.toLowerCase() ?? '' : ''
		if (!supportedAttachmentExtensions.has(extension)) {
			toast({ title: 'Unsupported file type', variant: 'destructive' })
			return
		}

		isUploadingAttachment.value = true
		try {
			const content = await file.text()
			const result = await chatService.createAttachment(selectedConversation.value.id, {
				filename: file.name,
				content,
				content_type: file.type || null,
			})
			attachments.value = [...attachments.value, result.data]
			toast({ title: `${file.name} attached` })
		} catch (err: any) {
			const detail = err?.response?.data?.detail
			const title = typeof detail === 'string' && detail.length > 0 ? detail : 'Failed to attach document'
			toast({ title, variant: 'destructive' })
		} finally {
			isUploadingAttachment.value = false
		}
	}

	async function deleteAttachment(attachmentId: number): Promise<void> {
		if (!selectedConversation.value) return
		try {
			await chatService.deleteAttachment(selectedConversation.value.id, attachmentId)
			attachments.value = attachments.value.filter(attachment => attachment.id !== attachmentId)
		} catch (err) {
			toast({ title: 'Failed to remove attachment', variant: 'destructive' })
		}
	}

	async function askLLM(userQuestion: string): Promise<void> {
		if (!selectedConversation.value) return
		if (!userQuestion.trim()) return
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
					onOrchestratorDecision: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(assistant, 'orchestrator_decision', {
							specialists: payload.specialists ?? [],
							reasoning: payload.reasoning ?? '',
						})
					},
					onOrchestratorPlan: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(assistant, 'orchestrator_plan', {
							plan: payload.plan,
							specialists: payload.specialists,
						})
					},
					onSpecialistPlan: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(
							assistant,
							'specialist_plan',
							{ specialist: payload.specialist, plan: payload.plan ?? '' },
							payload.specialist
						)
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
					onSpecialistToolCall: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(
							assistant,
							'specialist_tool_call',
							{
								specialist: payload.specialist,
								tool_name: payload.tool_name,
								arguments: payload.arguments ?? {},
							},
							payload.specialist
						)
					},
					onSpecialistEvidence: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(
							assistant,
							'specialist_evidence',
							{
								specialist: payload.specialist,
								tool_name: payload.tool_name,
								result: payload.result ?? {},
								evidence: payload.evidence ?? [],
							},
							payload.specialist
						)
					},
					onSpecialistToolResult: payload => {
						const assistant = getAssistantMessage()
						if (!assistant) return
						pushRunEvent(
							assistant,
							'specialist_tool_result',
							{
								specialist: payload.specialist,
								tool_name: payload.tool_name,
								result: payload.result,
							},
							payload.specialist
						)
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
		contextWindow.value = null
		attachments.value = []
	}

	function resetChatState(): void {
		conversations.value = []
		selectedConversation.value = null
		conversationSearchQuery.value = ''
		isLoading.value = false
		isSyncing.value = false
		isStreamingResponse.value = false
		streamingAssistantMessageId.value = null
		errorMessage.value = null
		contextWindow.value = null
		attachments.value = []
		isUploadingAttachment.value = false
	}

	return {
		conversations,
		selectedConversation,
		conversationSearchQuery,
		isLoading,
		isSyncing,
		isStreamingResponse,
		streamingAssistantMessageId,
		errorMessage,
		hasConversations,
		messages,
		isMessageStreaming,
		contextWindow,
		attachments,
		isUploadingAttachment,
		loadConversations,
		setConversationSearchQuery,
		selectConversation,
		setSelectedConversation,
		renameConversation,
		deleteConversation,
		createConversation,
		loadAttachments,
		uploadAttachment,
		deleteAttachment,
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
