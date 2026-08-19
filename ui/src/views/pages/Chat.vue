<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import Main from '../layout/Main.vue'
import ChatSidebar from '@/components/chat/ChatSidebar.vue';
import ChatSkillsPanel from '@/components/chat/ChatSkillsPanel.vue';
import ChatConnectorsPanel from '@/components/chat/ChatConnectorsPanel.vue';
import ChatAdminPanel from '@/components/chat/ChatAdminPanel.vue';
import ConfigDiffViewer from '@/components/chat/ConfigDiffViewer.vue';
import ChatActions from '@/components/chat/ChatActions.vue';
import ChatAttachmentBar from '@/components/chat/ChatAttachmentBar.vue';
import MessageArtifactTimeline from '@/features/artifacts/MessageArtifactTimeline.vue'
import AgentActivity from '@/features/execution/AgentActivity.vue'
import { getMessageToolActivities } from '@/features/execution/execution.normalize'
import { hasArtifactEvents, hasArtifactKind } from '@/features/artifacts/artifact.timeline'
import { parseUnifiedPatchToDiffFile } from '@/features/artifacts/config-diff/config-diff.adapter'
import type { DiffFile } from '@/features/artifacts/config-diff/config-diff.schema'
import Button from '@/components/ui/button/Button.vue';
import MarkdownRenderer from "@/components/MarkdownRenderer.vue"
import { Bug, Clipboard, RefreshCw } from 'lucide-vue-next';
import { useChatStore } from '@/stores/chat.store';
import { useSkillsStore } from '@/stores/skills.store';
import chatService from '@/services/chat.service';
import type { AgentRun, ContextBreakdown, Message, PromptSnapshot, PromptSnapshotMessage } from '@/types/chat.type';
import type { Skill } from '@/types/skill.type';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip'
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
    AlertDialog,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import TopologyMapper from '@/components/chat/TopologyMapper.vue';

const chatStore = useChatStore()
const skillsStore = useSkillsStore()
const disclaimerStorageKey = 'netai-chat-beta-disclaimer-acknowledged-v1'

const chatDialogueRef = ref<HTMLElement | null>(null)
let contentObserver: MutationObserver | null = null
const showScrollToBottomButton = ref(false)
const nearBottomThreshold = 120
const showButtonThreshold = 320
// const historySearchQuery = ref('')
const chatInputValue = ref('')
const chatTextareaRef = ref<HTMLTextAreaElement | null>(null)
const attachmentInputRef = ref<HTMLInputElement | null>(null)
const slashQuery = ref('')
const slashActiveIndex = ref(0)
const slashReplaceRange = ref<{ start: number; end: number } | null>(null)
const maxChatInputHeight = 220
const isSidebarCollapsed = ref(false)
const largeScreenBreakpoint = '(min-width: 1024px)'
const isLargeScreen = ref(true)
let largeScreenMediaQuery: MediaQueryList | null = null
let handleLargeScreenChange: ((event: MediaQueryListEvent) => void) | null = null
type ChatWorkspaceView = 'chat' | 'skills' | 'connectors' | 'admin'

const activePage = ref<ChatWorkspaceView>('chat')
const historySearchQuery = computed(() => chatStore.conversationSearchQuery)
const isDisclaimerOpen = ref(false)
const hasAcknowledgedDisclaimer = ref(false)
const userMessageAnchors = ref<Record<number, HTMLElement>>({})
const attachmentAccept = '.conf,.cfg,.csv,.ini,.json,.log,.md,.txt,.yaml,.yml'
const isPromptDrawerOpen = ref(false)
const isPromptPreviewLoading = ref(false)
const promptPreview = ref<PromptSnapshot | null>(null)
const promptPreviewError = ref<string | null>(null)

type MessageRenderSegment =
    | { id: string; type: 'markdown'; content: string }
    | { id: string; type: 'diff'; diffFiles: DiffFile[] }
type TopologyPayload = {
    scope: string
    device_count: number
    link_count: number
    link_status_counts?: Record<string, number>
    devices: Array<Record<string, unknown>>
    links: Array<Record<string, unknown>>
}
type QuestionNavItem = {
    messageId: number
    preview: string
}
type ContextBreakdownSegment = {
    key: keyof ContextBreakdown
    label: string
    tokens: number
    width: number
    swatchClass: string
}
type SlashSuggestion = Pick<Skill, 'id' | 'name' | 'slug' | 'description'>

function sourceLabel(source: string): string {
    const labels: Record<string, string> = {
        conversation_summary: 'Summary',
        conversation_message: 'Message',
        conversation_context: 'Context',
        agent_system_prompt: 'NetAI system',
        orchestrator_system_prompt: 'Orchestrator system (legacy)',
        available_tools: 'Available tools',
        current_question: 'Draft question',
        attachments: 'Attachments',
        custom_instructions: 'Custom instructions',
        selected_skills: 'Skills',
        formatting_prompt: 'Formatting',
    }
    return labels[source] ?? source.replace(/_/g, ' ')
}

function roleClass(role: string): string {
    if (role === 'system') return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
    if (role === 'assistant') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
    if (role === 'user') return 'border-sky-500/30 bg-sky-500/10 text-sky-200'
    return 'border-stone-600 bg-stone-900 text-stone-200'
}

function promptMessageMeta(message: PromptSnapshotMessage): string {
    if (message.message_id) return `message ${message.message_id}`
    if (message.summary_id) return `summary ${message.summary_id}`
    return `item ${message.index + 1}`
}

function promptPreviewQuestion(): string {
    const draft = chatInputValue.value.trim()
    if (draft) return draft
    const lastUserMessage = [...chatStore.messages].reverse().find(message => message.role === 'user' && message.content.trim())
    return lastUserMessage?.content ?? ''
}

async function loadPromptPreview(): Promise<void> {
    if (!chatStore.selectedConversation) return
    const content = promptPreviewQuestion()
    if (!content.trim()) {
        promptPreview.value = null
        promptPreviewError.value = 'Enter a question to preview the prompt stack.'
        return
    }

    isPromptPreviewLoading.value = true
    promptPreviewError.value = null
    try {
        const result = await chatService.getPromptPreview(chatStore.selectedConversation.id, { content })
        promptPreview.value = result.data
    } catch (err) {
        promptPreview.value = null
        promptPreviewError.value = 'Failed to load prompt preview.'
    } finally {
        isPromptPreviewLoading.value = false
    }
}

async function openPromptPreview(): Promise<void> {
    isPromptDrawerOpen.value = true
    await loadPromptPreview()
}

async function copyPromptPreview(): Promise<void> {
    if (!promptPreview.value || typeof navigator === 'undefined' || !navigator.clipboard) return
    await navigator.clipboard.writeText(JSON.stringify(promptPreview.value, null, 2))
}

function getQuestionPreview(content: string, maxWords = 6): string {
    const normalized = content.replace(/\s+/g, ' ').trim()
    if (!normalized) return 'Untitled question'
    const words = normalized.split(' ')
    const clipped = words.slice(0, maxWords).join(' ')
    return words.length > maxWords ? `${clipped}...` : clipped
}

const questionNavItems = computed<QuestionNavItem[]>(() =>
    chatStore.messages
        .filter((message): message is Message => message.role === 'user' && message.content.trim().length > 0)
        .map(message => ({
            messageId: message.id,
            preview: getQuestionPreview(message.content),
        }))
)

const slashSuggestions = computed<SlashSuggestion[]>(() => {
    const query = slashQuery.value.trim().toLowerCase()
    const available = skillsStore.availableSkills
        .map(skill => ({
            id: skill.id,
            name: skill.name,
            slug: skill.slug,
            description: skill.description,
        }))
        .sort((left, right) => left.name.localeCompare(right.name))

    if (!query) return available.slice(0, 8)

    return available
        .filter(skill => skill.slug.includes(query) || skill.name.toLowerCase().includes(query))
        .slice(0, 8)
})

const showSlashSuggestions = computed(() => slashReplaceRange.value !== null && slashSuggestions.value.length > 0)

function syncSidebarWithViewport(matchesLargeScreen: boolean) {
    isLargeScreen.value = matchesLargeScreen
    if (!matchesLargeScreen) {
        isSidebarCollapsed.value = true
        return
    }

    if (activePage.value === 'chat') {
        isSidebarCollapsed.value = false
    }
}

function setUserMessageAnchor(
    messageId: number,
    element: Element | ComponentPublicInstance | null
) {
    const domElement =
        element instanceof HTMLElement
            ? element
            : element &&
                typeof element === 'object' &&
                '$el' in element &&
                (element.$el as unknown) instanceof HTMLElement
                ? (element.$el as HTMLElement)
                : null

    if (domElement) {
        userMessageAnchors.value[messageId] = domElement
        return
    }
    delete userMessageAnchors.value[messageId]
}

async function jumpToQuestion(messageId: number) {
    await nextTick()
    const container = chatDialogueRef.value
    const target = userMessageAnchors.value[messageId]
    if (!container || !target) return

    const containerRect = container.getBoundingClientRect()
    const targetRect = target.getBoundingClientRect()
    const nextTop = Math.max(0, targetRect.top - containerRect.top + container.scrollTop - 24)

    container.scrollTo({
        top: nextTop,
        behavior: 'smooth',
    })
}

function getPrimaryRun(message: Message): AgentRun | null {
    const runs = message.agent_runs ?? []
    if (!runs.length) return null
    const roots = runs.filter(run => run.parent_run_id == null || run.depth === 0)
    return roots.at(-1) ?? runs.at(-1) ?? null
}

function getLatestFeedbackRating(message: Message): 'good' | 'bad' | null {
    const entries = message.feedback ?? []
    if (!entries.length) return null
    const latest = [...entries].sort((a, b) => {
        const left = Date.parse(a.updated_at || a.created_at || '')
        const right = Date.parse(b.updated_at || b.created_at || '')
        return right - left
    })[0]
    return latest?.rating ?? null
}

function hasSubmittedFeedbackReport(message: Message): boolean {
    return (message.feedback ?? []).some(entry => {
        if (entry.feedback_type) return true
        return Boolean((entry.comment ?? '').trim())
    })
}

function isRunActive(message: Message): boolean {
    if (chatStore.isMessageStreaming(message.id)) return true
    return getPrimaryRun(message)?.status === 'running'
}

function asRecord(value: unknown): Record<string, unknown> | null {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null
    return value as Record<string, unknown>
}

function parseToolResult(value: unknown): Record<string, unknown> | null {
    const valueRecord = asRecord(value)
    const raw = valueRecord?.value ?? value
    if (raw == null) return null

    if (typeof raw === 'string') {
        try {
            return JSON.parse(raw
                .replace(/'/g, '"')
                .replace(/\bNone\b/g, 'null')
                .replace(/\bFalse\b/g, 'false')
                .replace(/\bTrue\b/g, 'true')) as Record<string, unknown>
        } catch {
            return null
        }
    }

    return asRecord(raw)
}

function getMessageDiffFiles(message: Message): DiffFile[] {
    const files: DiffFile[] = []
    for (const call of getMessageToolActivities(message)) {
        if (!['bitbucket.get_recent_device_config_diff', 'bitbucket_get_recent_device_config_diff'].includes(call.name)) continue
        const result = parseToolResult(call.output)
        if (!result) continue

        const configDiff = asRecord(result.config_diff)
        if (typeof configDiff?.patch === 'string') {
            files.push(
                parseUnifiedPatchToDiffFile(
                    configDiff.patch,
                    String(configDiff.old_path ?? result.file_path ?? 'a/config'),
                    String(configDiff.new_path ?? result.file_path ?? 'b/config')
                )
            )
            continue
        }

        if (Array.isArray(result.diff_files)) {
            files.push(...(result.diff_files as DiffFile[]))
        }
    }
    return files
}

function getMessageTopology(message: Message): TopologyPayload | null {
    const calls = getMessageToolActivities(message)
    for (let index = calls.length - 1; index >= 0; index -= 1) {
        const call = calls[index]
        if (!['datamodel.get_topology', 'datamodel_get_topology'].includes(call.name)) continue
        const result = parseToolResult(call.output)
        if (!result || !Array.isArray(result.devices) || !Array.isArray(result.links)) continue
        return result as TopologyPayload
    }
    return null
}

function getMessageRenderSegments(message: Message): MessageRenderSegment[] {
    const content = message.content || ''
    const diffFiles = getMessageDiffFiles(message)
    const segments: MessageRenderSegment[] = []
    const markerRegex = /\[\[\s*CONFIG_DIFF(?:\s*:\s*(\d+))?\s*\]\]/gi

    let cursor = 0
    let markerCount = 0
    let sequentialDiffIndex = 0
    let matchedAnyMarker = false
    let match: RegExpExecArray | null

    while ((match = markerRegex.exec(content)) !== null) {
        matchedAnyMarker = true
        const markerStart = match.index
        const markerEnd = markerStart + match[0].length
        const beforeText = content.slice(cursor, markerStart)
        if (beforeText.trim().length > 0) {
            segments.push({
                id: `m-${message.id}-md-${markerCount}`,
                type: 'markdown',
                content: beforeText,
            })
        }

        const explicitIndexRaw = match[1]
        const explicitIndex = explicitIndexRaw ? Number(explicitIndexRaw) - 1 : null
        const selectedIndex = explicitIndex !== null ? explicitIndex : sequentialDiffIndex

        if (selectedIndex >= 0 && selectedIndex < diffFiles.length) {
            segments.push({
                id: `m-${message.id}-diff-${markerCount}`,
                type: 'diff',
                diffFiles: [diffFiles[selectedIndex]],
            })
            if (explicitIndex === null) {
                sequentialDiffIndex += 1
            }
        } else {
            // Keep unresolved marker visible in markdown to aid debugging prompt/tool mismatches.
            segments.push({
                id: `m-${message.id}-missing-marker-${markerCount}`,
                type: 'markdown',
                content: match[0],
            })
        }

        cursor = markerEnd
        markerCount += 1
    }

    const trailing = content.slice(cursor)
    if (trailing.trim().length > 0) {
        segments.push({
            id: `m-${message.id}-md-tail`,
            type: 'markdown',
            content: trailing,
        })
    }

    if (!matchedAnyMarker && diffFiles.length > 0) {
        // Automatic inline fallback:
        // If LLM pasted unified diff in a fenced code block, replace that block with ConfigDiffViewer.
        const fallbackSegments: MessageRenderSegment[] = []
        const fenceRegex = /```[a-zA-Z0-9_-]*\n[\s\S]*?```/g
        let blockCursor = 0
        let fenceIndex = 0
        let diffIndex = 0
        let fenceMatch: RegExpExecArray | null
        let replacedAnyFence = false

        const isLikelyUnifiedDiffBlock = (block: string): boolean => {
            return (
                block.includes('--- a/') &&
                block.includes('+++ b/') &&
                block.includes('@@ ')
            )
        }

        while ((fenceMatch = fenceRegex.exec(content)) !== null) {
            const start = fenceMatch.index
            const end = start + fenceMatch[0].length
            const before = content.slice(blockCursor, start)

            if (before.trim().length > 0) {
                fallbackSegments.push({
                    id: `m-${message.id}-md-fallback-before-${fenceIndex}`,
                    type: 'markdown',
                    content: before,
                })
            }

            const fenceBlock = fenceMatch[0]
            if (diffIndex < diffFiles.length && isLikelyUnifiedDiffBlock(fenceBlock)) {
                fallbackSegments.push({
                    id: `m-${message.id}-diff-fallback-inline-${fenceIndex}`,
                    type: 'diff',
                    diffFiles: [diffFiles[diffIndex]],
                })
                diffIndex += 1
                replacedAnyFence = true
            } else {
                fallbackSegments.push({
                    id: `m-${message.id}-md-fallback-fence-${fenceIndex}`,
                    type: 'markdown',
                    content: fenceBlock,
                })
            }

            blockCursor = end
            fenceIndex += 1
        }

        const afterFences = content.slice(blockCursor)
        if (afterFences.trim().length > 0) {
            fallbackSegments.push({
                id: `m-${message.id}-md-fallback-tail`,
                type: 'markdown',
                content: afterFences,
            })
        }

        if (replacedAnyFence) {
            for (let i = diffIndex; i < diffFiles.length; i += 1) {
                fallbackSegments.push({
                    id: `m-${message.id}-diff-fallback-extra-${i}`,
                    type: 'diff',
                    diffFiles: [diffFiles[i]],
                })
            }
            return fallbackSegments
        }

        // Final fallback: append diff(s) after markdown if no marker and no diff block was found.
        for (let i = 0; i < diffFiles.length; i += 1) {
            segments.push({
                id: `m-${message.id}-diff-fallback-${i}`,
                type: 'diff',
                diffFiles: [diffFiles[i]],
            })
        }
    }

    // Ensure we always render markdown when no segments are produced.
    if (segments.length === 0) {
        segments.push({
            id: `m-${message.id}-md-empty`,
            type: 'markdown',
            content,
        })
    }
    return segments
}

// ========== Resizing logic ===============
async function resizeChatTextarea() {
    await nextTick()
    const textarea = chatTextareaRef.value
    if (!textarea) return

    textarea.style.height = 'auto'
    const nextHeight = Math.min(textarea.scrollHeight, maxChatInputHeight)
    textarea.style.height = `${nextHeight}px`
    textarea.style.overflowY = textarea.scrollHeight > maxChatInputHeight ? 'auto' : 'hidden'
}

function updateSlashSuggestions() {
    const textarea = chatTextareaRef.value
    if (!textarea) {
        slashReplaceRange.value = null
        slashQuery.value = ''
        return
    }

    const previousRange = slashReplaceRange.value
    const previousQuery = slashQuery.value
    const cursor = textarea.selectionStart ?? chatInputValue.value.length
    const beforeCursor = chatInputValue.value.slice(0, cursor)
    const match = beforeCursor.match(/^\s*\/([a-z0-9-]*)$/i)
    if (!match) {
        slashReplaceRange.value = null
        slashQuery.value = ''
        return
    }

    const query = match[1] ?? ''
    const start = cursor - query.length - 1
    slashReplaceRange.value = {
        start,
        end: cursor,
    }
    slashQuery.value = query

    const rangeChanged =
        previousRange?.start !== slashReplaceRange.value.start ||
        previousRange?.end !== slashReplaceRange.value.end

    if (rangeChanged || previousQuery !== query) {
        slashActiveIndex.value = 0
    }
}

async function selectSlashSuggestion(skill: SlashSuggestion) {
    const textarea = chatTextareaRef.value
    const range = slashReplaceRange.value
    if (!textarea || !range) return

    const nextValue = `${chatInputValue.value.slice(0, range.start)}/${skill.slug} ${chatInputValue.value.slice(range.end)}`
    chatInputValue.value = nextValue
    slashReplaceRange.value = null
    slashQuery.value = ''

    await nextTick()
    const nextCursor = range.start + skill.slug.length + 2
    textarea.focus()
    textarea.setSelectionRange(nextCursor, nextCursor)
    await resizeChatTextarea()
}

function handleChatKeydown(event: KeyboardEvent) {
    if (showSlashSuggestions.value) {
        if (event.key === 'ArrowDown') {
            event.preventDefault()
            slashActiveIndex.value = (slashActiveIndex.value + 1) % slashSuggestions.value.length
            return
        }
        if (event.key === 'ArrowUp') {
            event.preventDefault()
            slashActiveIndex.value =
                (slashActiveIndex.value - 1 + slashSuggestions.value.length) % slashSuggestions.value.length
            return
        }
        if ((event.key === 'Enter' || event.key === 'Tab') && !event.ctrlKey) {
            event.preventDefault()
            const selected = slashSuggestions.value[slashActiveIndex.value]
            if (selected) {
                void selectSlashSuggestion(selected)
            }
            return
        }
        if (event.key === 'Escape') {
            slashReplaceRange.value = null
            slashQuery.value = ''
            return
        }
    }

    if (event.key === 'Enter' && event.ctrlKey) {
        event.preventDefault()
        void submit()
    }
}

function getDistanceFromBottom() {
    const container = chatDialogueRef.value
    if (!container) return 0
    return container.scrollHeight - (container.scrollTop + container.clientHeight)
}

function updateScrollState() {
    const distanceFromBottom = getDistanceFromBottom()
    showScrollToBottomButton.value = distanceFromBottom > showButtonThreshold
    return distanceFromBottom <= nearBottomThreshold
}

async function scrollToBottom(behavior: ScrollBehavior = 'auto') {
    await nextTick()
    const container = chatDialogueRef.value
    if (!container) return
    container.scrollTo({ top: container.scrollHeight, behavior })
}
// ========== End of resizing logic ===============

function disconnectContentObserver() {
    contentObserver?.disconnect()
    contentObserver = null
}

async function setupContentObserver() {
    if (activePage.value !== 'chat') return

    await nextTick()
    const container = chatDialogueRef.value
    if (!container) return

    disconnectContentObserver()
    contentObserver = new MutationObserver(() => {
        if (updateScrollState()) {
            void scrollToBottom()
            return
        }
        updateScrollState()
    })
    contentObserver.observe(container, {
        childList: true,
        subtree: true,
        characterData: true,
    })
    updateScrollState()
}

function toggleSidebar() {
    if (!isLargeScreen.value) return
    isSidebarCollapsed.value = !isSidebarCollapsed.value
}

function handleSidebarNavigate(nextPage: ChatWorkspaceView) {
    activePage.value = nextPage
    if (nextPage !== 'chat' && !isSidebarCollapsed.value) {
        isSidebarCollapsed.value = true
    }
}

function handleHistorySearchQueryUpdate(value: string) {
    void chatStore.setConversationSearchQuery(value)
}

function readDisclaimerAcknowledgement(): boolean {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(disclaimerStorageKey) === 'true'
}

function acknowledgeDisclaimer() {
    if (!hasAcknowledgedDisclaimer.value) return
    if (typeof window !== 'undefined') {
        window.localStorage.setItem(disclaimerStorageKey, 'true')
    }
    isDisclaimerOpen.value = false
}

async function loadConnectorStatus() {
    // TODO: Replace with backend healthcheck endpoint when available.
    // Example: const data = await api.get('/connectors/health')
}

async function submit() {
    const message = chatInputValue.value.trim()
    if (!message) return
    chatInputValue.value = ""
    slashReplaceRange.value = null
    slashQuery.value = ''
    await resizeChatTextarea()

    // Start the request immediately, then position the viewport on the newly
    // inserted user message before waiting for the Agent response. This keeps
    // the submitted question visible even when the user was reading older
    // messages above the bottom of the conversation.
    const responsePromise = chatStore.askLLM(message)
    await nextTick()
    const submittedMessage = [...chatStore.messages]
        .reverse()
        .find(item => item.role === 'user' && item.content === message)
    if (submittedMessage) {
        await jumpToQuestion(submittedMessage.id)
    } else {
        await scrollToBottom('smooth')
    }
    await responsePromise
}

function openAttachmentPicker() {
    attachmentInputRef.value?.click()
}

async function handleAttachmentChange(event: Event) {
    const input = event.target as HTMLInputElement | null
    const files = input?.files
    const file = files && files.length > 0 ? files[0] : null
    if (!file) return

    await chatStore.uploadAttachment(file)
    if (!input) return
    input.value = ''
}

async function removeAttachment(attachmentId: number) {
    await chatStore.deleteAttachment(attachmentId)
}

// Context percentage
const dashOffset = computed(() => {
    if (!chatStore.contextWindow) return 0
    const circumference = 2 * Math.PI * 16; // 2πr
    return circumference * (1 - chatStore.contextWindow.used_percent / 100);
});

const contextBreakdownSegments = computed<ContextBreakdownSegment[]>(() => {
    const metrics = chatStore.contextWindow
    const breakdown = metrics?.breakdown
    if (!metrics || !breakdown || metrics.context_window <= 0) return []

    const segmentConfig: Array<Omit<ContextBreakdownSegment, 'tokens' | 'width'>> = [
        { key: 'system', label: 'System prompts', swatchClass: 'bg-amber-400' },
        { key: 'user', label: 'User prompts', swatchClass: 'bg-sky-400' },
        { key: 'assistant', label: 'Assistant replies', swatchClass: 'bg-emerald-400' },
        { key: 'tools', label: 'Tools', swatchClass: 'bg-rose-400' },
        { key: 'documents', label: 'Attached documents', swatchClass: 'bg-teal-400' },
    ]

    return segmentConfig
        .map(segment => {
            const tokens = breakdown[segment.key]?.tokens ?? 0
            return {
                ...segment,
                tokens,
                width: (tokens / metrics.context_window) * 100,
            }
        })
        .filter(segment => segment.tokens > 0)
})

const contextAvailableWidth = computed(() => {
    if (!chatStore.contextWindow?.context_window) return 0
    return (chatStore.contextWindow.left_tokens / chatStore.contextWindow.context_window) * 100
})

function formatContextPercent(tokens: number, total: number) {
    if (!total || tokens <= 0) return '0%'
    const percent = (tokens / total) * 100
    return `${percent >= 10 ? Math.round(percent) : percent.toFixed(1)}%`
}

watch(() => chatStore.selectedConversation,
    async () => { await scrollToBottom() }
)

watch(slashSuggestions, suggestions => {
    if (!suggestions.length) {
        slashActiveIndex.value = 0
        return
    }
    if (slashActiveIndex.value >= suggestions.length) {
        slashActiveIndex.value = 0
    }
})

watch(activePage, async page => {
    if (page !== 'chat') {
        disconnectContentObserver()
        showScrollToBottomButton.value = false
        return
    }

    await resizeChatTextarea()
    await scrollToBottom()
    await setupContentObserver()
})

onMounted(async () => {
    if (typeof window !== 'undefined') {
        largeScreenMediaQuery = window.matchMedia(largeScreenBreakpoint)
        syncSidebarWithViewport(largeScreenMediaQuery.matches)
        handleLargeScreenChange = event => {
            syncSidebarWithViewport(event.matches)
        }
        largeScreenMediaQuery.addEventListener('change', handleLargeScreenChange)
    }

    isDisclaimerOpen.value = !readDisclaimerAcknowledgement()
    await chatStore.loadConversations()
    await skillsStore.loadBootstrap()
    await loadConnectorStatus()
    await scrollToBottom()
    await resizeChatTextarea()
    await setupContentObserver()
})

onBeforeUnmount(() => {
    if (largeScreenMediaQuery && handleLargeScreenChange) {
        largeScreenMediaQuery.removeEventListener('change', handleLargeScreenChange)
    }
    disconnectContentObserver()
})
</script>

<template>
    <Main>
        <div class="flex w-full h-full min-h-0 overflow-hidden">
            <ChatSidebar :collapsed="isSidebarCollapsed" :active-view="activePage"
                :history-search-query="historySearchQuery" @toggle="toggleSidebar" @navigate="handleSidebarNavigate"
                @update:history-search-query="handleHistorySearchQueryUpdate" />
            <!-- Main section -->
            <div class="relative flex flex-col flex-1 h-full min-w-0 min-h-0">
                <Button v-if="activePage === 'chat'" type="button" variant="outline" size="sm" @click="openPromptPreview"
                    class="absolute top-5 right-5 z-30 gap-2 border-stone-700/80 bg-stone-950/80 text-stone-300 shadow-lg backdrop-blur hover:bg-stone-900 hover:text-stone-100"
                    aria-label="Debug">
                    <Bug class="w-4 h-4" />
                    <span>Debug</span>
                </Button>
                <!-- Question Navbar -->
                <div v-if="activePage === 'chat' && questionNavItems.length > 1"
                    class="absolute top-0 bottom-0 z-20 items-center hidden pointer-events-none right-2 lg:flex">
                    <div class="relative flex items-center pointer-events-auto group">
                        <div
                            class="flex flex-col gap-2 px-2 py-2 transition-colors border rounded-lg w-min h-min bg-stone-900/20 border-stone-800 group-hover:border-stone-700">
                            <div v-for="n in 5" :key="n" class="w-1 h-1 text-transparent rounded-lg bg-stone-600" />
                        </div>
                        <div
                            class="absolute w-64 p-2 text-xs transition-all duration-300 translate-x-2 -translate-y-1/2 border rounded-lg shadow-xl opacity-0 pointer-events-none right-4 top-1/2 border-stone-700/70 bg-stone-950/95 backdrop-blur group-hover:pointer-events-auto group-hover:translate-x-0 group-hover:opacity-100">
                            <div class="max-h-[30vh] space-y-1 overflow-y-auto pr-1">
                                <button v-for="item in questionNavItems" :key="`jump-question-${item.messageId}`"
                                    type="button" @click="jumpToQuestion(item.messageId)"
                                    class="w-full rounded-md border border-transparent px-2 py-1.5 text-left text-stone-500 transition hover:text-white">
                                    {{ item.preview }}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                <Button v-if="isSidebarCollapsed && activePage !== 'chat' && activePage !== 'admin'" @click="handleSidebarNavigate('chat')"
                    variant="link"
                    class="absolute z-20 inline-flex items-center gap-2 px-3 py-2 pl-10 transition top-5 text-stone-200 hover:text-stone-200">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                        <path fill="currentColor" d="m10 17l-5-5l5-5l1.4 1.4L8.8 11H20v2H8.8l2.6 2.6z" />
                    </svg>
                    Messages
                </Button>
                <!-- Title -->
                <!-- <button
                    class="absolute p-3 px-8 text-xl font-semibold transition shadow-lg rounded-xl left-6 top-3 bg-stone-950/60 backdrop-blur-sm text-stone-300 ">
                    Zabbix and syslog for edge-fw-par-01
                </button> -->
                <Transition mode="out-in" enter-active-class="transition-all duration-300 ease-out transform-gpu motion-reduce:transition-none" enter-from-class="translate-y-3 opacity-0 blur-sm" enter-to-class="translate-y-0 opacity-100 blur-0" leave-active-class="transition-all duration-200 ease-in transform-gpu motion-reduce:transition-none" leave-from-class="translate-y-0 opacity-100 blur-0" leave-to-class="-translate-y-2 opacity-0 blur-sm">
                    <div v-if="activePage === 'chat'" key="chat" class="flex flex-col flex-1 min-h-0">
                        <!-- Chat dialogue -->
                        <div
                            class="flex flex-col flex-1 min-h-0 overflow-hidden transition-all duration-300 ease-out motion-reduce:transition-none"
                            :class="chatStore.isSyncing ? 'translate-y-2 opacity-0' : 'translate-y-0 opacity-100'">
                            <div ref="chatDialogueRef" @scroll="updateScrollState"
                                class="flex flex-col flex-1 min-h-0 p-10 px-20 overflow-x-hidden overflow-y-auto">
                        <!-- v-if="!selectedConversation || selectedConversation.messages.length < 1" -->
                                <div v-if="chatStore.messages.length == 0"
                                    class="flex flex-col items-center justify-center h-full gap-2">
                                    <h2
                                        class="pb-2 text-3xl font-semibold tracking-wide transition-colors scroll-m-20 text-stone-500 first:mt-0">
                                        What would you like to talk about today?
                                    </h2>
                                    <div class="flex items-center gap-1 text-stone-500">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-stone-400"
                                            viewBox="0 0 24 24">
                                            <path fill="currentColor"
                                                d="M5 22v-4q0-.575.3-1.037t.8-.738L11 13.75V12l-3.475 1.725q-.3.15-.625.225t-.65.075q-.775 0-1.463-.4t-1.062-1.15q-.35-.675-.3-1.437T3.9 9.625L7 5L5 2h6q3.325 0 5.663 2.325T19 10v12zm2-2h10V10q0-2.5-1.75-4.25T11 4H8.75l.65 1l-3.825 5.75q-.125.2-.137.413t.087.412q.125.275.338.363t.412.087q.075 0 .375-.075L13 8.75V15l-6 3zm4-8" />
                                        </svg>
                                        <p class="text-2xl font-medium">NetAI</p>
                                    </div>
                                </div>
                                <div v-else class="flex flex-col min-w-0 gap-6 mt-auto text-sm">
                                    <div v-for="message in chatStore.messages" :key="`message-${message.id}`" class="min-w-0">
                                <!-- Assistant message -->
                                        <div v-if="message.role == 'assistant'" class="flex flex-col min-w-0 gap-4">
                                            <p v-if="isRunActive(message) && !getPrimaryRun(message)" class="animate-pulse text-sm text-stone-400">Thinking...</p>
                                            <AgentActivity :message="message" :active="isRunActive(message)" />
                                            <MessageArtifactTimeline v-if="hasArtifactEvents(message)" :message="message" />
                                            <div v-else class="flex min-w-0 flex-col gap-4">
                                                <template v-for="segment in getMessageRenderSegments(message)" :key="segment.id">
                                                    <MarkdownRenderer v-if="segment.type === 'markdown'" class="min-w-0" :content="segment.content" />
                                                    <ConfigDiffViewer v-else :diff-files="segment.diffFiles" />
                                                </template>
                                            </div>
                                            <TopologyMapper
                                                v-if="!isRunActive(message) && !hasArtifactKind(message, 'network.topology.v1') && getMessageTopology(message)"
                                                :topology="getMessageTopology(message) || undefined" />

                                    <!-- Feedback -->
                                            <ChatActions v-if="!chatStore.isMessageStreaming(message.id)"
                                                :message-id="message.id" :content="message.content"
                                                :initial-rating="getLatestFeedbackRating(message)"
                                                :initial-report-submitted="hasSubmittedFeedbackReport(message)" />
                                        </div>
                                <!-- User message -->
                                        <div v-if="message.role == 'user'" :ref="(el) => setUserMessageAnchor(message.id, el)"
                                            class="flex justify-end">
                                            <p
                                                class="w-fit max-w-[75%] break-words whitespace-pre-wrap rounded-2xl border border-stone-800 bg-stone-900 px-4 py-2 text-left">
                                                {{ message.content }}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <!-- Scroll button -->
                        <button v-if="showScrollToBottomButton" @click="scrollToBottom('smooth')"
                            class="absolute p-1 text-sm transition border rounded-full shadow-lg bottom-40 right-14 border-stone-700 bg-zinc-900/95 text-stone-100 hover:bg-stone-800">
                            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"
                                viewBox="0 0 24 24"><!-- Icon from Material Symbols by Google - https://github.com/google/material-design-icons/blob/master/LICENSE -->
                                <path fill="currentColor"
                                    d="m12 18l-6-6l1.4-1.4l3.6 3.575V6h2v8.175l3.6-3.575L18 12l-6 6Z" />
                            </svg>
                        </button>
                        <!-- Chat box -->
                        <div class="grid w-full px-10 pb-6 shrink-0">
                            <div
                                class="flex justify-between px-2 pb-2 rounded-t-lg shadow-2xl bg-stone-900/20 shadow-stone-600">
                                <div>
                                    <p class="pt-2 text-sm text-zinc-500">Ctrl + Enter to quickly send.</p>
                                    <!-- <Button variant="ghost" size="xs">deep investigation</Button> -->
                                </div>
                                <p class="pt-2 text-xs text-center text-zinc-500">NetAI can make mistakes, Check
                                    important info.
                                </p>
                            </div>
                            <input ref="attachmentInputRef" type="file" class="hidden" :accept="attachmentAccept"
                                @change="handleAttachmentChange" />
                            <div
                                class="relative rounded-md border border-stone-800 bg-stone-900/60 px-3 py-2.5 focus:border-stone-800">
                                <div v-if="showSlashSuggestions"
                                    class="absolute bottom-[calc(100%+0.75rem)] left-0 right-0 z-30 overflow-hidden rounded-xl border border-stone-800 bg-stone-950/95 shadow-2xl shadow-black/40 backdrop-blur">
                                    <div class="border-b border-stone-800 px-3 py-2 text-[11px] uppercase tracking-[0.22em] text-stone-500">
                                        Skills
                                    </div>
                                    <button
                                        v-for="(skill, index) in slashSuggestions"
                                        :key="skill.id"
                                        type="button"
                                        class="flex items-start justify-between w-full gap-3 px-3 py-3 text-left transition"
                                        :class="index === slashActiveIndex ? 'bg-stone-900 text-stone-100' : 'text-stone-300 hover:bg-stone-900/70'"
                                        @mousedown.prevent="selectSlashSuggestion(skill)">
                                        <div>
                                            <p class="text-sm font-medium">/{{ skill.slug }}</p>
                                            <p class="mt-1 text-xs text-stone-500">{{ skill.name }}</p>
                                            <p v-if="skill.description" class="mt-2 text-xs leading-5 text-stone-400">
                                                {{ skill.description }}
                                            </p>
                                        </div>
                                    </button>
                                </div>
                                <textarea ref="chatTextareaRef" v-model="chatInputValue"
                                    @input="() => { resizeChatTextarea(); updateSlashSuggestions() }"
                                    @click="updateSlashSuggestions" @keyup="updateSlashSuggestions"
                                    @keydown="handleChatKeydown" rows="1" data-slot="input-group-control"
                                    class="min-h-15 flex w-full resize-none bg-transparent text-base outline-none transition-[color,box-shadow] placeholder:text-stone-600 md:text-sm"
                                    placeholder="How can I help you today?" />
                                <div class="flex items-end justify-between gap-4 py-1 pt-5">
                                    <ChatAttachmentBar :attachments="chatStore.attachments"
                                        :is-uploading="chatStore.isUploadingAttachment" @add="openAttachmentPicker"
                                        @remove="removeAttachment" />
                                    <div class="flex items-center gap-4">
                                        <div class="flex items-center gap-2">
                                            <TooltipProvider v-if="chatStore.contextWindow">
                                                <Tooltip>
                                                    <TooltipTrigger>
                                                        <div class="relative w-5 h-5">
                                                            <svg viewBox="0 0 36 36" class="w-full h-full">
                                                            <!-- Background circle -->
                                                                <circle class="text-stone-800" cx="18" cy="18" r="16"
                                                                    stroke-width="4" fill="none" stroke="currentColor" />
                                                            <!-- Progress circle -->
                                                                <circle class="text-stone-400" cx="18" cy="18" r="16"
                                                                    stroke-width="4" fill="none" stroke="currentColor"
                                                                    stroke-dasharray="100" :stroke-dashoffset="dashOffset"
                                                                    stroke-linecap="round" transform="rotate(-90 18 18)" />
                                                            </svg>
                                                        </div>
                                                    </TooltipTrigger>
                                                    <TooltipContent class="border-stone-800 bg-stone-950 text-stone-100">
                                                        <div class="w-72 space-y-3 p-1.5">
                                                        <div class="space-y-1">
                                                            <p class="font-semibold">Context window</p>
                                                            <p class="text-xs text-stone-400">
                                                                {{ chatStore.contextWindow.used_percent }}% used,
                                                                {{ chatStore.contextWindow.left_percent }}% left
                                                            </p>
                                                            <p class="text-xs text-stone-500">
                                                                {{ chatStore.contextWindow.used_tokens }} / {{
                                                                    chatStore.contextWindow.context_window
                                                                }} tokens
                                                            </p>
                                                        </div>

                                                        <div v-if="contextBreakdownSegments.length > 0"
                                                            class="space-y-2">
                                                            <div
                                                                class="overflow-hidden border rounded-full border-stone-800 bg-stone-900">
                                                                <div class="flex h-2.5 w-full overflow-hidden">
                                                                    <div v-for="segment in contextBreakdownSegments"
                                                                        :key="segment.key" :class="segment.swatchClass"
                                                                        :style="{ width: `${segment.width}%` }"
                                                                        :title="`${segment.label}: ${segment.tokens} tokens`" />
                                                                    <div v-if="contextAvailableWidth > 0"
                                                                        class="bg-stone-700/80"
                                                                        :style="{ width: `${contextAvailableWidth}%` }"
                                                                        title="Available context" />
                                                                </div>
                                                            </div>
                                                            <div class="space-y-1.5">
                                                                <div v-for="segment in contextBreakdownSegments"
                                                                    :key="`${segment.key}-legend`"
                                                                    class="flex items-center justify-between gap-3 text-xs">
                                                                    <div class="flex items-center gap-2 text-stone-300">
                                                                        <span class="h-2.5 w-2.5 rounded-full"
                                                                            :class="segment.swatchClass" />
                                                                        <span>{{ segment.label }}</span>
                                                                    </div>
                                                                    <span class="text-stone-400">
                                                                        {{ segment.tokens }} tokens
                                                                        ({{ formatContextPercent(segment.tokens,
                                                                            chatStore.contextWindow.used_tokens) }})
                                                                    </span>
                                                                </div>
                                                                <div
                                                                    class="flex items-center justify-between gap-3 text-xs">
                                                                    <div class="flex items-center gap-2 text-stone-300">
                                                                        <span
                                                                            class="h-2.5 w-2.5 rounded-full bg-stone-700" />
                                                                        <span>Available</span>
                                                                    </div>
                                                                    <span class="text-stone-400">
                                                                        {{ chatStore.contextWindow.left_tokens }} tokens
                                                                    </span>
                                                                </div>
                                                            </div>
                                                        </div>

                                                        <p v-else class="text-xs text-stone-500">
                                                            Detailed breakdown appears after a fresh run in this
                                                            conversation.
                                                        </p>

                                                        <p class="text-[11px] uppercase tracking-[0.22em] text-stone-600">
                                                            {{ chatStore.contextWindow.compacted ? 'Compacted' : 'Not compacted' }}
                                                        </p>
                                                        </div>
                                                    </TooltipContent>
                                                </Tooltip>
                                            </TooltipProvider>
                                            <p class="text-xs text-stone-400">Gemini Flash 2.5 </p>
                                        </div>
                                        <Button @click="submit" :disabled="!chatInputValue.trim()"
                                            :class="chatInputValue.trim() ? 'bg-red-500 hover:bg-red-500/50 text-white' : 'bg-stone-500 text-zinc-200'"
                                            variant="default" size="xs">
                                            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                                                <g fill="none" fill-rule="evenodd">
                                                    <path
                                                        d="m12.594 23.258l-.012.002l-.071.035l-.02.004l-.014-.004l-.071-.036q-.016-.004-.024.006l-.004.01l-.017.428l.005.02l.01.013l.104.074l.015.004l.012-.004l.104-.074l.012-.016l.004-.017l-.017-.427q-.004-.016-.016-.018m.264-.113l-.014.002l-.184.093l-.01.01l-.003.011l.018.43l.005.012l.008.008l.201.092q.019.005.029-.008l.004-.014l-.034-.614q-.005-.019-.02-.022m-.715.002a.02.02 0 0 0-.027.006l-.006.014l-.034.614q.001.018.017.024l.015-.002l.201-.093l.01-.008l.003-.011l.018-.43l-.003-.012l-.01-.01z" />
                                                    <path fill="currentColor"
                                                        d="M17.991 6.01L5.399 10.563l4.195 2.428l3.699-3.7a1 1 0 0 1 1.414 1.415l-3.7 3.7l2.43 4.194L17.99 6.01Zm.323-2.244c1.195-.433 2.353.725 1.92 1.92l-5.282 14.605c-.434 1.198-2.07 1.344-2.709.241l-3.217-5.558l-5.558-3.217c-1.103-.639-.957-2.275.241-2.709z" />
                                                </g>
                                            </svg>
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <ChatSkillsPanel v-else-if="activePage === 'skills'" key="skills" class="flex-1 min-h-0" />
                    <ChatConnectorsPanel v-else-if="activePage === 'connectors'" key="connectors" class="flex-1 min-h-0" />
                    <ChatAdminPanel v-else key="admin" class="flex-1 min-h-0" />
                </Transition>
            </div>
        </div>
        <Sheet v-model:open="isPromptDrawerOpen">
            <SheetContent side="right"
                class="flex w-full flex-col border-stone-800 bg-stone-950 p-0 text-stone-200 sm:max-w-3xl">
                <SheetHeader class="border-b border-stone-800 px-6 py-5">
                    <div class="flex items-start justify-between gap-4 pr-8">
                        <div>
                            <SheetTitle class="text-stone-100">Prompt Stack</SheetTitle>
                            <SheetDescription class="mt-1 text-stone-400">
                                Current conversation context, runtime prompts, and draft question.
                            </SheetDescription>
                        </div>
                        <div class="flex items-center gap-2">
                            <Button type="button" variant="outline" size="icon"
                                class="h-8 w-8 border-stone-700 bg-stone-900 text-stone-300 hover:bg-stone-800"
                                :disabled="isPromptPreviewLoading" @click="loadPromptPreview">
                                <RefreshCw class="h-4 w-4" :class="isPromptPreviewLoading ? 'animate-spin' : ''" />
                            </Button>
                            <Button type="button" variant="outline" size="icon"
                                class="h-8 w-8 border-stone-700 bg-stone-900 text-stone-300 hover:bg-stone-800"
                                :disabled="!promptPreview" @click="copyPromptPreview">
                                <Clipboard class="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                </SheetHeader>
                <div class="grid gap-3 border-b border-stone-800 px-6 py-4 text-xs text-stone-400 sm:grid-cols-4">
                    <div>
                        <p class="text-stone-500">Tokens</p>
                        <p class="mt-1 text-sm text-stone-100">
                            {{ promptPreview?.metrics.used_tokens ?? 0 }} / {{ promptPreview?.metrics.context_window ?? 0 }}
                        </p>
                    </div>
                    <div>
                        <p class="text-stone-500">Used</p>
                        <p class="mt-1 text-sm text-stone-100">{{ promptPreview?.metrics.used_percent ?? 0 }}%</p>
                    </div>
                    <div>
                        <p class="text-stone-500">State</p>
                        <p class="mt-1 text-sm text-stone-100">
                            {{ promptPreview?.metrics.compacted ? 'Compacted' : 'Not compacted' }}
                        </p>
                    </div>
                    <div>
                        <p class="text-stone-500">Summary</p>
                        <p class="mt-1 text-sm text-stone-100">
                            {{ promptPreview?.metrics.summary_id ?? 'None' }}
                        </p>
                    </div>
                </div>
                <ScrollArea class="min-h-0 flex-1">
                    <div class="space-y-4 px-6 py-5">
                        <div v-if="isPromptPreviewLoading" class="rounded-md border border-stone-800 bg-stone-900/50 p-4 text-sm text-stone-400">
                            Loading prompt stack...
                        </div>
                        <div v-else-if="promptPreviewError" class="rounded-md border border-red-900/60 bg-red-950/30 p-4 text-sm text-red-200">
                            {{ promptPreviewError }}
                        </div>
                        <div v-else-if="!promptPreview || promptPreview.messages.length === 0"
                            class="rounded-md border border-stone-800 bg-stone-900/50 p-4 text-sm text-stone-400">
                            No prompt messages available.
                        </div>
                        <article v-for="message in promptPreview?.messages ?? []" :key="`prompt-message-${message.index}`"
                            class="overflow-hidden rounded-md border border-stone-800 bg-stone-900/40">
                            <div class="flex flex-wrap items-center justify-between gap-2 border-b border-stone-800 px-3 py-2">
                                <div class="flex min-w-0 items-center gap-2">
                                    <span class="inline-flex h-6 min-w-6 items-center justify-center rounded bg-stone-800 px-1.5 text-xs text-stone-300">
                                        {{ message.index + 1 }}
                                    </span>
                                    <span class="rounded border px-2 py-0.5 text-xs capitalize" :class="roleClass(message.role)">
                                        {{ message.role || 'unknown' }}
                                    </span>
                                    <span class="text-xs text-stone-400">{{ sourceLabel(message.source) }}</span>
                                </div>
                                <div class="flex items-center gap-2 text-xs text-stone-500">
                                    <span>{{ promptMessageMeta(message) }}</span>
                                    <span>{{ message.estimated_tokens }} tokens</span>
                                </div>
                            </div>
                            <pre class="max-h-96 overflow-auto whitespace-pre-wrap break-words p-3 text-xs leading-5 text-stone-300">{{ message.text }}</pre>
                        </article>
                    </div>
                </ScrollArea>
            </SheetContent>
        </Sheet>
        <AlertDialog :open="isDisclaimerOpen">
            <AlertDialogContent class="border-stone-800 bg-stone-950 text-stone-200 sm:max-w-2xl">
                <AlertDialogHeader>
                    <AlertDialogTitle>Beta Disclaimer</AlertDialogTitle>
                    <AlertDialogDescription class="space-y-3 text-sm leading-6 text-stone-400">
                        <p>
                            NetAI is still in beta. It can misunderstand your request, make incorrect inferences,
                            or present false information with confidence.
                        </p>
                        <p>
                            Always cross-check important conclusions against the tool call results and raw source
                            data. Tool outputs come from deterministic API calls and should be treated as the
                            primary evidence when validating the assistant's answer.
                        </p>
                        <p>
                            Before acting on recommendations, especially operational or production-impacting ones,
                            verify timestamps, scope, commands, and any proposed remediation steps.
                        </p>
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <label
                    class="flex items-start gap-3 px-4 py-3 text-sm border rounded-lg border-stone-800 bg-stone-900/50 text-stone-300">
                    <input v-model="hasAcknowledgedDisclaimer" type="checkbox"
                        class="mt-0.5 h-4 w-4 rounded border-stone-700 bg-stone-950 text-red-500 accent-red-500" />
                    <span>I understood the disclaimer</span>
                </label>
                <AlertDialogFooter>
                    <Button type="button" variant="default"
                        class="text-white bg-red-500 hover:bg-red-500/80 disabled:bg-stone-700 disabled:text-stone-400"
                        :disabled="!hasAcknowledgedDisclaimer" @click="acknowledgeDisclaimer">
                        Continue to Chat
                    </Button>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    </Main>
</template>

<style scoped>
:deep(.thinking-code.llm-content) {
    @apply text-xs leading-5 text-stone-300;
}

:deep(.thinking-code.llm-content p) {
    @apply pb-0;
}

:deep(.thinking-code.llm-content pre) {
    @apply my-1 rounded-md border-stone-700/70 bg-stone-950/30 p-2;
}

:deep(.thinking-code.llm-content code) {
    @apply text-[11px];
}

:deep(.llm-content) {
    overflow-wrap: anywhere;
    word-break: break-word;
}

:deep(.llm-content pre) {
    white-space: pre-wrap;
}
</style>
