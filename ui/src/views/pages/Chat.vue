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
import Button from '@/components/ui/button/Button.vue';
import MarkdownRenderer from "@/components/MarkdownRenderer.vue"
import { useChatStore } from '@/stores/chat.store';
import type { AgentEvent, AgentRun, ContextBreakdown, Message, ToolCall } from '@/types/chat.type';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip'
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
const maxChatInputHeight = 220
const isSidebarCollapsed = ref(false)
type ChatWorkspaceView = 'chat' | 'skills' | 'connectors' | 'admin'

const activePage = ref<ChatWorkspaceView>('chat')
const historySearchQuery = computed(() => chatStore.conversationSearchQuery)
const isDisclaimerOpen = ref(false)
const hasAcknowledgedDisclaimer = ref(false)
const userMessageAnchors = ref<Record<number, HTMLElement>>({})
const attachmentAccept = '.conf,.cfg,.csv,.ini,.json,.log,.md,.txt,.yaml,.yml'

type DiffLineType = 'context' | 'added' | 'removed' | 'meta'
type DiffLine = {
    type: DiffLineType
    old_lineno: number | null
    new_lineno: number | null
    content: string
}
type DiffHunk = {
    header: string
    old_start: number
    old_lines: number
    new_start: number
    new_lines: number
    lines: DiffLine[]
}
type DiffFile = {
    old_path: string
    new_path: string
    hunks: DiffHunk[]
}
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
type ToolCallDetail = {
    id: string | number
    specialist: string
    toolName: string
    input: unknown
    output: unknown
}
type SpecialistToolGroup = {
    specialist: string
    calls: ToolCallDetail[]
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

function toDisplayName(value: string): string {
    const safe = (value || '').replace(/[_-]+/g, ' ').trim()
    if (!safe) return 'Unknown'
    return safe
        .split(/\s+/)
        .filter(Boolean)
        .map(part => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
}

function extractDelegatedPrompt(argumentsPayload: unknown): string | undefined {
    if (!argumentsPayload || typeof argumentsPayload !== 'object') return undefined
    const args = argumentsPayload as Record<string, unknown>
    const messages = args.messages
    if (!Array.isArray(messages) || messages.length === 0) return undefined
    const first = messages[0]
    if (!first || typeof first !== 'object') return undefined
    const content = (first as Record<string, unknown>).content
    if (typeof content !== 'string' || !content.trim()) return undefined
    return content.trim()
}

function inferToolNameFromSpecialist(
    specialistRaw: string,
    originalToolName: string,
    argumentsPayload: unknown
): string {
    if (!originalToolName.endsWith('_specialist')) return originalToolName

    const specialist = specialistRaw.toLowerCase().trim()
    const delegatedPrompt = extractDelegatedPrompt(argumentsPayload)?.toLowerCase() ?? ''

    if (specialist === 'syslog') {
        if (
            delegatedPrompt.includes('critical') ||
            delegatedPrompt.includes('error') ||
            delegatedPrompt.includes('severity') ||
            delegatedPrompt.includes('host')
        ) {
            return 'syslog.get_logs'
        }
        return 'syslog.get_evidence'
    }

    if (specialist === 'zabbix') return 'zabbix.diagnose_host'
    if (specialist === 'datamodel') return 'datamodel.get_topology'
    if (specialist === 'servicenow') return 'servicenow.list_incidents'
    if (specialist === 'suzieq') return 'suzieq.infrastructure_summary'

    return `${specialist}.tool`
}

function getPrimaryRun(message: Message): AgentRun | null {
    const runs = message.agent_runs ?? []
    if (!runs.length) return null
    return runs[runs.length - 1]
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
    const entries = message.feedback ?? []
    return entries.some(entry => {
        if (entry.feedback_type) return true
        return Boolean((entry.comment ?? '').trim())
    })
}

function getSortedEvents(message: Message): AgentEvent[] {
    const run = getPrimaryRun(message)
    if (!run) return []
    return [...(run.events ?? [])].sort(
        (a, b) => (a.event_sequence ?? 0) - (b.event_sequence ?? 0)
    )
}

function isRunActive(message: Message): boolean {
    if (chatStore.isMessageStreaming(message.id)) return true
    const run = getPrimaryRun(message)
    return run?.status === 'running'
}

function stringifyForThoughts(value: unknown): string {
    if (value == null) return ''
    if (typeof value === 'string') return value
    try {
        return JSON.stringify(value, null, 2)
    } catch {
        return String(value)
    }
}

function toThinkingCodeBlock(value: unknown): string {
    const text = stringifyForThoughts(value) || '{}'
    const lang = typeof value === 'string' ? 'txt' : 'json'
    // Use four backticks so regular triple-backticks inside payload won't break fences.
    return `\`\`\`\`${lang}\n${text}\n\`\`\`\``
}

function normalizeSpecialistName(value: string): string {
    const clean = (value || '')
        .replace(/[_-]+/g, ' ')
        .replace(/\bspecialist\b/gi, '')
        .trim()
    return toDisplayName(clean || value)
}

function withAgentSuffix(value: string): string {
    const normalized = normalizeSpecialistName(value)
    return normalized.toLowerCase().endsWith('agent') ? normalized : `${normalized} Agent`
}

const SPECIALIST_COLORS = {
    zabbix: {
        text: 'text-red-500',
        bg: 'bg-red-500/5',
        border: 'border-red-500/35',
    },
    syslog: {
        text: 'text-amber-400',
        bg: 'bg-amber-400/5',
        border: 'border-amber-400/35',
    },
    datamodel: {
        text: 'text-blue-400',
        bg: 'bg-blue-400/5',
        border: 'border-blue-400/35',
    },
    servicenow: {
        text: 'text-emerald-400',
        bg: 'bg-emerald-400/5',
        border: 'border-emerald-400/35',
    },
    suzieq: {
        text: 'text-purple-400',
        bg: 'bg-purple-400/5',
        border: 'border-purple-400/35',
    },
    orchestrator: {
        text: 'text-stone-300',
        bg: 'bg-stone-300/5',
        border: 'border-stone-300/35',
    },
    unknown: {
        text: 'text-stone-300',
        bg: 'bg-stone-300/5',
        border: 'border-stone-300/35',
    },
} as const

type SpecialistColorKey = keyof typeof SPECIALIST_COLORS
type SpecialistColorVariant = keyof (typeof SPECIALIST_COLORS)[SpecialistColorKey]

function getSpecialistColorKey(value: string): SpecialistColorKey {
    const cleaned = normalizeSpecialistName(value)
        .toLowerCase()
        .replace(/\bagent\b/g, '')
        .replace(/\s+/g, '')
        .trim()

    if (cleaned in SPECIALIST_COLORS) {
        return cleaned as SpecialistColorKey
    }
    return 'unknown'
}

function getSpecialistColorClass(
    value: string,
    variant: SpecialistColorVariant = 'text'
): string {
    return SPECIALIST_COLORS[getSpecialistColorKey(value)][variant]
}

function asRecord(value: unknown): Record<string, unknown> | null {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null
    return value as Record<string, unknown>
}

function toToolLabel(toolName: string): string {
    const normalized = (toolName || 'unknown_tool').trim()
    if (!normalized) return 'unknown_tool'
    if (!normalized.includes('.')) return normalized
    return normalized.split('.').at(-1) || normalized
}

function formatList(items: string[]): string {
    if (items.length === 0) return ''
    if (items.length === 1) return items[0]
    if (items.length === 2) return `${items[0]} and ${items[1]}`
    return `${items.slice(0, -1).join(', ')}, and ${items.at(-1)}`
}

function getChosenSpecialists(message: Message): string[] {
    const events = getSortedEvents(message)
    const names: string[] = []
    for (const event of events) {
        if (event.event_type !== 'orchestrator_decision') continue
        const payload = (event.payload ?? {}) as Record<string, unknown>
        const specialists = payload.specialists
        if (!Array.isArray(specialists)) continue
        for (const item of specialists) {
            const normalized = withAgentSuffix(String(item ?? ''))
            if (!normalized || names.includes(normalized)) continue
            names.push(normalized)
        }
    }
    return names
}

function getGatheringContextStep(message: Message): string | null {
    const specialistLabels = getChosenSpecialists(message)
    if (specialistLabels.length === 0) return null
    return `Gathering context from ${formatList(specialistLabels)}...`
}

function getRunDurationMs(message: Message): number | null {
    const run = getPrimaryRun(message)
    if (!run) return null

    const createdAtMs = Date.parse(run.created_at)
    if (!Number.isFinite(createdAtMs)) return null

    const fallbackEndAt = run.events?.at(-1)?.created_at
    const endedAtCandidate = run.ended_at || fallbackEndAt
    if (!endedAtCandidate) return null

    const endedAtMs = Date.parse(endedAtCandidate)
    if (!Number.isFinite(endedAtMs)) return null

    return Math.max(0, Math.round(endedAtMs - createdAtMs))
}

function getThoughtsSummary(message: Message): string {
    const durationMs = getRunDurationMs(message)
    if (durationMs == null || durationMs == 0) return 'Thoughts.'
    return `Thoughts (${durationMs} ms)`
}

function getToolCallDetailsFromEvents(message: Message): ToolCallDetail[] {
    const events = getSortedEvents(message)
    const calls: ToolCallDetail[] = []
    const pendingByKey = new Map<string, ToolCallDetail[]>()

    for (const event of events) {
        const payload = (event.payload ?? {}) as Record<string, unknown>
        if (event.event_type === 'specialist_tool_call') {
            const specialistRaw = String(payload.specialist ?? event.actor_name ?? 'specialist')
            const originalToolName = String(payload.tool_name ?? 'unknown_tool')
            const toolName = inferToolNameFromSpecialist(
                specialistRaw,
                originalToolName,
                payload.arguments
            )
            const call: ToolCallDetail = {
                id: event.id,
                specialist: normalizeSpecialistName(specialistRaw),
                toolName,
                input: payload.arguments ?? {},
                output: null,
            }
            calls.push(call)
            const key = `${specialistRaw}:${toolName}`
            const queue = pendingByKey.get(key) ?? []
            queue.push(call)
            pendingByKey.set(key, queue)
            continue
        }

        if (event.event_type !== 'specialist_evidence' && event.event_type !== 'specialist_tool_result') {
            continue
        }

        const specialistRaw = String(payload.specialist ?? event.actor_name ?? 'specialist')
        const originalToolName = String(payload.tool_name ?? 'unknown_tool')
        const toolName = inferToolNameFromSpecialist(
            specialistRaw,
            originalToolName,
            payload.arguments
        )
        const key = `${specialistRaw}:${toolName}`
        const queue = pendingByKey.get(key)
        const call = queue?.shift()
        if (!call) continue

        if (event.event_type === 'specialist_evidence') {
            call.output = {
                result: payload.result ?? {},
                evidence: payload.evidence ?? [],
            }
        } else {
            call.output = payload.result ?? {}
        }
    }
    return calls
}

function getToolCallDetailsFromPersistedRuns(message: Message): ToolCallDetail[] {
    const run = getPrimaryRun(message)
    if (!run) return []
    const runRecord = run as unknown as Record<string, unknown>
    const details: ToolCallDetail[] = []

    const addPersistedCalls = (callsRaw: unknown, specialistRaw: string, prefix: string) => {
        if (!Array.isArray(callsRaw)) return
        const specialist = normalizeSpecialistName(specialistRaw)
        callsRaw.forEach((call, index) => {
            const row = asRecord(call)
            if (!row) return
            const toolName = String(row.tool_name ?? 'unknown_tool')
            details.push({
                id: String(row.id ?? `${prefix}-${index}`),
                specialist,
                toolName,
                input: row.input_params ?? {},
                output: row.output ?? {},
            })
        })
    }

    addPersistedCalls(runRecord.tool_calls, String(runRecord.agent_name ?? 'orchestrator'), 'root')

    const childRuns = runRecord.child_runs
    if (Array.isArray(childRuns)) {
        childRuns.forEach((childRun, index) => {
            const child = asRecord(childRun)
            if (!child) return
            addPersistedCalls(
                child.tool_calls,
                String(child.agent_name ?? child.specialist_name ?? 'specialist'),
                `child-${index}`
            )
        })
    }

    return details
}

function getMessageToolCallDetails(message: Message): ToolCallDetail[] {
    const fromEvents = getToolCallDetailsFromEvents(message)
    if (fromEvents.length > 0) return fromEvents
    return getToolCallDetailsFromPersistedRuns(message)
}

function getSpecialistToolGroups(message: Message): SpecialistToolGroup[] {
    const calls = getMessageToolCallDetails(message)
    if (calls.length === 0) return []

    const groupsBySpecialist = new Map<string, SpecialistToolGroup>()
    for (const call of calls) {
        const key = call.specialist || 'Unknown'
        const existing = groupsBySpecialist.get(key)
        if (existing) {
            existing.calls.push(call)
            continue
        }
        groupsBySpecialist.set(key, {
            specialist: key,
            calls: [call],
        })
    }

    return [...groupsBySpecialist.values()]
}

function hasSpecialistToolCalls(message: Message): boolean {
    return getMessageToolCallDetails(message).length > 0
}

function hasLeaderConclusion(message: Message): boolean {
    return getSortedEvents(message).some(event => event.event_type === 'leader_conclusion')
}

function shouldShowSynthesizing(message: Message): boolean {
    if (!isRunActive(message)) return true
    if (hasLeaderConclusion(message)) return true
    return hasSpecialistToolCalls(message) && message.content.trim().length > 0
}

function parseToolResult(toolcall: ToolCall): Record<string, unknown> | null {
    const resultObj = toolcall.result as Record<string, unknown> | undefined
    const raw = resultObj?.['value'] ?? resultObj
    if (!raw) return null

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

    if (typeof raw === 'object') {
        return raw as Record<string, unknown>
    }

    return null
}

function getMessageToolCalls(message: Message): ToolCall[] {
    return getMessageToolCallDetails(message).map((call, index) => {
        const outputRecord = asRecord(call.output)
        return {
            id: typeof call.id === 'number' ? call.id : index + 1,
            tool_name: call.toolName,
            tool_source: call.specialist,
            arguments: asRecord(call.input) ?? {},
            result: outputRecord ?? ({ value: call.output } as object),
            evidence_items: [],
        }
    })
}

function parseUnifiedPatchToDiffFile(
    patch: string,
    oldPath: string,
    newPath: string
): DiffFile {
    const hunkHeaderRegex = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/
    const lines = patch.split('\n')
    const hunks: DiffHunk[] = []

    let currentHunk: DiffHunk | null = null
    let oldLine = 0
    let newLine = 0

    for (const rawLine of lines) {
        if (rawLine.startsWith('@@')) {
            const match = rawLine.match(hunkHeaderRegex)
            if (!match) continue

            const oldStart = Number(match[1] ?? 0)
            const oldLines = Number(match[2] ?? 1)
            const newStart = Number(match[3] ?? 0)
            const newLines = Number(match[4] ?? 1)

            currentHunk = {
                header: rawLine,
                old_start: oldStart,
                old_lines: oldLines,
                new_start: newStart,
                new_lines: newLines,
                lines: [],
            }
            hunks.push(currentHunk)
            oldLine = oldStart
            newLine = newStart
            continue
        }

        if (!currentHunk) continue
        if (rawLine.startsWith('\\ No newline at end of file')) continue

        if (rawLine.startsWith('+')) {
            currentHunk.lines.push({
                type: 'added',
                old_lineno: null,
                new_lineno: newLine,
                content: rawLine.slice(1),
            })
            newLine += 1
            continue
        }

        if (rawLine.startsWith('-')) {
            currentHunk.lines.push({
                type: 'removed',
                old_lineno: oldLine,
                new_lineno: null,
                content: rawLine.slice(1),
            })
            oldLine += 1
            continue
        }

        currentHunk.lines.push({
            type: 'context',
            old_lineno: oldLine,
            new_lineno: newLine,
            content: rawLine.startsWith(' ') ? rawLine.slice(1) : rawLine,
        })
        oldLine += 1
        newLine += 1
    }

    return {
        old_path: oldPath,
        new_path: newPath,
        hunks,
    }
}

function getMessageDiffFiles(toolCalls: ToolCall[] | undefined): DiffFile[] {
    if (!toolCalls?.length) return []

    const files: DiffFile[] = []
    for (const toolcall of toolCalls) {
        if (toolcall.tool_name !== 'bitbucket.get_recent_device_config_diff') continue
        const result = parseToolResult(toolcall)
        if (!result) continue

        const configDiff = result['config_diff']
        if (
            configDiff &&
            typeof configDiff === 'object' &&
            typeof (configDiff as Record<string, unknown>).patch === 'string'
        ) {
            const diffMeta = configDiff as Record<string, unknown>
            files.push(
                parseUnifiedPatchToDiffFile(
                    String(diffMeta.patch),
                    String(diffMeta.old_path ?? result.file_path ?? 'a/config'),
                    String(diffMeta.new_path ?? result.file_path ?? 'b/config')
                )
            )
            continue
        }

        const legacyDiffFiles = result['diff_files']
        if (Array.isArray(legacyDiffFiles)) {
            files.push(...(legacyDiffFiles as DiffFile[]))
        }
    }
    return files
}

function getMessageTopology(toolCalls: ToolCall[] | undefined): TopologyPayload | null {
    if (!toolCalls?.length) return null

    for (let i = toolCalls.length - 1; i >= 0; i -= 1) {
        const toolcall = toolCalls[i]
        if (toolcall.tool_name !== 'datamodel.get_topology') continue
        const result = parseToolResult(toolcall)
        if (!result) continue
        if (!Array.isArray(result.devices) || !Array.isArray(result.links)) continue
        return result as TopologyPayload
    }
    return null
}

function getMessageRenderSegments(message: Message): MessageRenderSegment[] {
    const content = message.content || ''
    const diffFiles = getMessageDiffFiles(getMessageToolCalls(message))
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
    await resizeChatTextarea()
    await chatStore.askLLM(message)
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
    isDisclaimerOpen.value = !readDisclaimerAcknowledgement()
    await chatStore.loadConversations()
    await loadConnectorStatus()
    await scrollToBottom()
    await resizeChatTextarea()
    await setupContentObserver()
})

onBeforeUnmount(() => {
    disconnectContentObserver()
})
</script>

<template>
    <Main title="Chat">
        <div class="grid w-full h-full min-h-0 grid-cols-12 overflow-hidden">
            <ChatSidebar :collapsed="isSidebarCollapsed" :active-view="activePage"
                :history-search-query="historySearchQuery" @toggle="toggleSidebar" @navigate="handleSidebarNavigate"
                @update:history-search-query="handleHistorySearchQueryUpdate" />
            <!-- Main section -->
            <div class="relative flex flex-col h-full min-h-0"
                :class="isSidebarCollapsed ? 'col-span-11' : 'col-span-10'">
                <!-- Question Navbar -->
                <div v-if="activePage === 'chat' && questionNavItems.length > 1"
                    class="absolute top-0 bottom-0 z-20 items-center hidden pointer-events-none right-2 lg:flex">
                    <div class="relative flex items-center pointer-events-auto group">
                        <div
                            class="flex flex-col gap-2 px-2 py-2 transition-colors border rounded-lg w-min h-min bg-stone-900/20 border-stone-800 group-hover:border-stone-700">
                            <div v-for="n in 5" :key="n" class="w-1 h-1 text-transparent rounded-lg bg-stone-600" />
                        </div>
                        <div
                            class="absolute w-64 p-2 text-xs transition-all duration-300 translate-x-2 -translate-y-1/2 border rounded-lg shadow-xl opacity-0 right-4 top-1/2 border-stone-700/70 bg-stone-950/95 backdrop-blur group-hover:translate-x-0 group-hover:opacity-100">
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
                <!-- Title -->
                <!-- <button
                    class="absolute p-3 px-8 text-xl font-semibold transition shadow-lg rounded-xl left-6 top-3 bg-stone-950/60 backdrop-blur-sm text-stone-300 ">
                    Zabbix and syslog for edge-fw-par-01
                </button> -->
                <template v-if="activePage === 'chat'">
                    <!-- Chat dialogue -->
                    <div ref="chatDialogueRef" @scroll="updateScrollState"
                        class="flex flex-col flex-1 min-h-0 p-10 px-20 overflow-x-hidden overflow-y-auto">
                        <!-- v-if="!selectedConversation || selectedConversation.messages.length < 1" -->
                        <div v-if="chatStore.messages.length == 0"
                            class="flex flex-col items-center justify-center h-full gap-2">
                            <h2
                                class="pb-2 text-3xl font-semibold tracking-wide transition-colors text-stone-500 scroll-m-20 first:mt-0">
                                What would you like to talk about today?
                            </h2>
                            <!-- <p class="text-3xl text-stone-400">What would you like to talk about today?</p> -->
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
                                    <!-- Rendering streamed events -->
                                    <div v-if="isRunActive(message)" class="relative grid gap-2 text-sm leading-6">
                                        <p class="animate-pulse text-stone-400">Thinking...</p>
                                        <div v-if="getGatheringContextStep(message)"
                                            class="relative flex items-start gap-2">
                                            <span
                                                class="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center text-stone-400">
                                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
                                                    class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.8"
                                                    stroke-linecap="round" stroke-linejoin="round">
                                                    <circle cx="11" cy="11" r="7" />
                                                    <path d="m21 21-4.3-4.3" />
                                                </svg>
                                            </span>
                                            <p class="text-stone-400">
                                                {{ getGatheringContextStep(message) }}
                                            </p>
                                        </div>

                                        <div v-if="hasSpecialistToolCalls(message)" class="flex flex-col gap-2">
                                            <div class="relative flex items-start gap-2">
                                                <span
                                                    class="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center text-stone-400">
                                                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
                                                        class="w-4 h-4" fill="none" stroke="currentColor"
                                                        stroke-width="1.8" stroke-linecap="round"
                                                        stroke-linejoin="round">
                                                        <path
                                                            d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.2 2.2l-2.8-2.8z" />
                                                    </svg>
                                                </span>
                                                <p class="text-stone-400">Gathering context...</p>
                                            </div>
                                            <details v-for="toolCall in getMessageToolCallDetails(message)"
                                                :key="`stream-tool-${message.id}-${toolCall.id}-${toolCall.toolName}`"
                                                class="pl-5 ml-2 border-l border-stone-600">
                                                <summary
                                                    class="flex items-center gap-2 cursor-pointer select-none animate-in text-stone-400">
                                                    <span class="inline-flex items-center gap-1">Called tool</span>
                                                    <span class="text-stone-200">
                                                        {{ toToolLabel(toolCall.toolName) }}
                                                    </span>
                                                    <span class="text-stone-500">via</span>
                                                    <span class="inline-flex items-center">
                                                        <span :class="[
                                                            'inline-flex items-center rounded px-1.5 py-0.5',
                                                            getSpecialistColorClass(toolCall.specialist, 'text'),
                                                        ]">{{
                                                            withAgentSuffix(toolCall.specialist) }}</span>
                                                    </span>
                                                </summary>
                                                <div class="grid gap-2 py-2 pl-2">
                                                    <div>
                                                        <p class="pl-3 -mb-2 text-xs tracking-wide text-stone-500">
                                                            Input
                                                        </p>
                                                        <MarkdownRenderer class="thinking-code"
                                                            :content="toThinkingCodeBlock(toolCall.input)" />
                                                    </div>
                                                    <div>
                                                        <p class="pl-3 -mb-2 text-xs tracking-wide text-stone-500">
                                                            Output
                                                        </p>
                                                        <MarkdownRenderer class="thinking-code"
                                                            :content="toThinkingCodeBlock(toolCall.output)" />
                                                    </div>
                                                </div>
                                            </details>
                                        </div>

                                        <div v-if="shouldShowSynthesizing(message)"
                                            class="relative flex items-start gap-2">
                                            <span
                                                class="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center text-stone-400">
                                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
                                                    class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.8"
                                                    stroke-linecap="round" stroke-linejoin="round">
                                                    <path d="M12 3l1.9 4.1L18 9l-4.1 1.9L12 15l-1.9-4.1L6 9l4.1-1.9z" />
                                                    <path d="M5 16l.9 1.9L8 19l-2.1 1L5 22l-1-2l-2-1l2-1.1z" />
                                                    <path d="M19 14l.7 1.4L21 16l-1.3.6L19 18l-.6-1.4L17 16l1.4-.6z" />
                                                </svg>
                                            </span>
                                            <p class="text-stone-400 animate-pulse">
                                                Synthesizing...
                                            </p>
                                        </div>

                                        <div v-if="message.content.trim().length > 0" class="grid min-w-0 gap-2">
                                            <MarkdownRenderer class="min-w-0" :content="message.content" />
                                        </div>
                                    </div>

                                    <!-- Rendering conversation from DB -->
                                    <div v-else class="grid gap-4 text-xs">
                                        <details v-if="getSpecialistToolGroups(message).length > 0" class="leading-6">
                                            <summary
                                                class="inline-flex items-center gap-2 cursor-pointer select-none text-stone-400">
                                                <span>
                                                    {{ getThoughtsSummary(message) }}
                                                </span>
                                                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4"
                                                    viewBox="0 0 24 24">
                                                    <path fill="currentColor"
                                                        d="M12.6 12L8 7.4L9.4 6l6 6l-6 6L8 16.6z" />
                                                </svg>
                                            </summary>
                                            <div class="relative grid gap-3 pt-2 pl-8">
                                                <div class="absolute left-[10px] top-1 bottom-1 w-px bg-stone-700/70" />
                                                <div v-for="group in getSpecialistToolGroups(message)"
                                                    :key="`thoughts-group-${message.id}-${group.specialist}`"
                                                    class="grid gap-2">
                                                    <p class="relative flex items-center gap-2 text-stone-400">
                                                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
                                                            class="w-4 h-4" fill="none" stroke="currentColor"
                                                            stroke-width="1.8" stroke-linecap="round"
                                                            stroke-linejoin="round">
                                                            <circle cx="11" cy="11" r="7" />
                                                            <path d="m21 21-4.3-4.3" />
                                                        </svg>
                                                        <span>Gathered context from </span>
                                                        <span :class="[
                                                            'inline-flex items-center rounded px-1.5 py-0.5 border',
                                                            getSpecialistColorClass(group.specialist, 'text'),
                                                            getSpecialistColorClass(group.specialist, 'bg'),
                                                            getSpecialistColorClass(group.specialist, 'border'),
                                                        ]">{{
                                                            withAgentSuffix(group.specialist) }}</span>
                                                    </p>
                                                    <div v-for="(toolCall, toolIndex) in group.calls"
                                                        :key="`thought-tool-${message.id}-${group.specialist}-${toolCall.id}-${toolIndex}`"
                                                        class="grid gap- pl-7">
                                                        <p
                                                            class="flex items-center gap-2 mb-3 tracking-wide text-stone-400">
                                                            <span class="inline-flex items-center gap-1">
                                                                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4"
                                                                    viewBox="0 0 24 24">
                                                                    <path fill="currentColor"
                                                                        d="M15.6 5.29c-1.1-.1-2.07.71-2.17 1.82L13.18 10H16v2h-3l-.44 5.07a3.986 3.986 0 0 1-4.33 3.63a4 4 0 0 1-3.06-1.87l1.5-1.5c.24.74.9 1.31 1.73 1.38c1.1.1 2.07-.71 2.17-1.82L11 12H8v-2h3.17l.27-3.07c.19-2.2 2.13-3.83 4.33-3.63c1.31.11 2.41.84 3.06 1.87l-1.5 1.5c-.24-.74-.9-1.31-1.73-1.38" />
                                                                </svg>
                                                                <span>Called tool</span>
                                                            </span>
                                                            <span class="font-semibold text-stone-200">
                                                                {{ toToolLabel(toolCall.toolName) }}
                                                            </span>
                                                        </p>
                                                        <div>
                                                            <p class="pl-3 -mb-2 text-xs tracking-wide text-stone-500">
                                                                Input
                                                            </p>
                                                            <MarkdownRenderer class="thinking-code"
                                                                :content="toThinkingCodeBlock(toolCall.input)" />
                                                        </div>
                                                        <div>
                                                            <p class="pl-3 -mb-2 text-xs tracking-wide text-stone-500">
                                                                Output
                                                            </p>
                                                            <MarkdownRenderer class="thinking-code"
                                                                :content="toThinkingCodeBlock(toolCall.output)" />
                                                        </div>
                                                    </div>
                                                </div>
                                                <p
                                                    class="relative flex items-center gap-2 font-semibold text-stone-400">
                                                    <span
                                                        class="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center">
                                                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
                                                            class="w-4 h-4" fill="none" stroke="currentColor"
                                                            stroke-width="1.8" stroke-linecap="round"
                                                            stroke-linejoin="round">
                                                            <path d="M20 6L9 17l-5-5" />
                                                        </svg>
                                                    </span>
                                                    Done.
                                                </p>
                                            </div>
                                        </details>

                                        <div class="flex flex-col min-w-0 gap-4">
                                            <template v-for="segment in getMessageRenderSegments(message)"
                                                :key="segment.id">
                                                <MarkdownRenderer v-if="segment.type === 'markdown'" class="min-w-0"
                                                    :content="segment.content" />
                                                <ConfigDiffViewer v-else :diff-files="segment.diffFiles" />
                                            </template>
                                        </div>
                                    </div>
                                    <TopologyMapper
                                        v-if="!isRunActive(message) && getMessageTopology(getMessageToolCalls(message))"
                                        :topology="getMessageTopology(getMessageToolCalls(message)) || undefined" />
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
                                        class="w-fit max-w-[75%] px-4 py-2 text-left rounded-2xl bg-stone-800  border border-stone-600 break-words">
                                        {{ message.content }}
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                    <!-- Scroll button -->
                    <button v-if="showScrollToBottomButton" @click="scrollToBottom('smooth')"
                        class="absolute p-1 text-sm transition border rounded-full shadow-lg right-14 bottom-40 border-stone-700 bg-zinc-900/95 text-stone-100 hover:bg-stone-800">
                        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"
                            viewBox="0 0 24 24"><!-- Icon from Material Symbols by Google - https://github.com/google/material-design-icons/blob/master/LICENSE -->
                            <path fill="currentColor"
                                d="m12 18l-6-6l1.4-1.4l3.6 3.575V6h2v8.175l3.6-3.575L18 12l-6 6Z" />
                        </svg>
                    </button>
                    <!-- Chat box -->
                    <div class="grid w-full px-10 pb-6 shrink-0">
                        <div
                            class="flex justify-between px-2 pb-2 rounded-t-lg shadow-2xl shadow-stone-600 bg-stone-900/20">
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
                            class="border bg-stone-900/60 rounded-md  focus:border-stone-800 border-stone-800 px-3 py-2.5">
                            <textarea ref="chatTextareaRef" v-model="chatInputValue" @input="resizeChatTextarea"
                                @keydown.ctrl.enter.prevent="submit" rows="1" data-slot="input-group-control"
                                class="min-h-15 w-full flex resize-none bg-transparent placeholder:text-stone-600  text-base transition-[color,box-shadow] outline-none md:text-sm"
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
                </template>
                <ChatSkillsPanel v-else-if="activePage === 'skills'" class="flex-1 min-h-0" />
                <ChatConnectorsPanel v-else-if="activePage === 'connectors'" class="flex-1 min-h-0" />
                <ChatAdminPanel v-else class="flex-1 min-h-0" />
            </div>
        </div>
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
.step-fade-enter-active,
.step-fade-leave-active {
    transition: opacity 0.25s ease;
}

.step-fade-enter-from,
.step-fade-leave-to {
    opacity: 0;
}

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
