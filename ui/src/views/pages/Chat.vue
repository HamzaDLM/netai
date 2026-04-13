<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Main from '../layout/Main.vue'
import ChatSidebar from '@/components/chat/ChatSidebar.vue';
import ChatListTool from '@/components/chat/ChatListTool.vue';
import ConfigDiffViewer from '@/components/chat/ConfigDiffViewer.vue';
import ChatActions from '@/components/chat/ChatActions.vue';
import Button from '@/components/ui/button/Button.vue';
import { ButtonGroup } from '@/components/ui/button-group'
import MarkdownRenderer from "@/components/MarkdownRenderer.vue"
import { useChatStore } from '@/stores/chat.store';
import type { AgentRun, Evidence, Message, ToolCall } from '@/types/chat.type';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip'
import TopologyMapper from '@/components/chat/TopologyMapper.vue';

const chatStore = useChatStore()

const chatDialogueRef = ref<HTMLElement | null>(null)
let contentObserver: MutationObserver | null = null
const showScrollToBottomButton = ref(false)
const nearBottomThreshold = 120
const showButtonThreshold = 320
// const historySearchQuery = ref('')
const chatInputValue = ref('')
const chatTextareaRef = ref<HTMLTextAreaElement | null>(null)
const maxChatInputHeight = 220
const isSidebarCollapsed = ref(false)
const debugMode = ref(false)

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

function extractToolCallsFromRuns(runs: AgentRun[] | undefined): ToolCall[] {
    if (!Array.isArray(runs) || runs.length === 0) return []

    const calls: ToolCall[] = []
    const pendingByKey = new Map<string, ToolCall>()

    for (const run of runs) {
        const events = [...(run.events ?? [])].sort(
            (a, b) => (a.event_sequence ?? 0) - (b.event_sequence ?? 0)
        )
        for (const event of events) {
            const payload = (event.payload ?? {}) as Record<string, unknown>
            if (event.event_type === 'specialist_tool_call') {
                const specialist = String(payload.specialist ?? 'unknown')
                const toolName = String(payload.tool_name ?? 'unknown_tool')
                const call: ToolCall = {
                    id: Number(event.id ?? -1),
                    tool_name: toolName,
                    tool_source: specialist,
                    arguments: (payload.arguments as Record<string, unknown>) ?? {},
                    result: undefined,
                    evidence_items: Array.isArray(payload.evidence)
                        ? (payload.evidence as Evidence[]).map((item, index) => {
                            const row = item as unknown as Record<string, unknown>
                            return {
                                id: Number(row.id ?? (index + 1)),
                                source_type: String(row.type ?? row.source_type ?? 'tool_result'),
                                source_ref: row.ref ? String(row.ref) : row.source_ref ? String(row.source_ref) : undefined,
                                content_snippet: String(row.content ?? row.content_snippet ?? ''),
                                score: typeof row.score === 'number' ? row.score : undefined,
                                timestamp: row.timestamp ? String(row.timestamp) : undefined,
                            }
                        })
                        : [],
                }
                calls.push(call)
                pendingByKey.set(`${specialist}:${toolName}`, call)
                continue
            }

            if (event.event_type === 'specialist_tool_result') {
                const specialist = String(payload.specialist ?? 'unknown')
                const toolName = String(payload.tool_name ?? 'unknown_tool')
                const key = `${specialist}:${toolName}`
                const existing = pendingByKey.get(key)
                if (existing) {
                    existing.result = (payload.result as Record<string, unknown>) ?? {}
                    pendingByKey.delete(key)
                }
            }
        }
    }

    return calls
}

function getMessageToolCalls(message: Message): ToolCall[] {
    return extractToolCallsFromRuns(message.agent_runs)
}

function getMessageDiffFiles(toolCalls: ToolCall[] | undefined): DiffFile[] {
    if (!toolCalls?.length) return []

    const files: DiffFile[] = []
    for (const toolcall of toolCalls) {
        if (toolcall.tool_name !== 'bitbucket.get_device_config_diff') continue
        const result = parseToolResult(toolcall)
        const diffFiles = result?.['diff_files']
        if (!Array.isArray(diffFiles)) continue
        files.push(...(diffFiles as DiffFile[]))
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

function toggleSidebar() {
    isSidebarCollapsed.value = !isSidebarCollapsed.value
}

async function loadConnectorStatus() {
    // TODO: Replace with backend healthcheck endpoint when available.
    // Example: const data = await api.get('/connectors/health')
}

async function submit() {
    const message = chatInputValue.value
    chatInputValue.value = ""
    await resizeChatTextarea()
    await chatStore.askLLM(message)
}

// Context percentage
const dashOffset = computed(() => {
    if (!chatStore.contextWindow) return 0
    const circumference = 2 * Math.PI * 16; // 2πr
    return circumference * (1 - chatStore.contextWindow.used_percent / 100);
});

watch(() => chatStore.selectedConversation,
    async () => { await scrollToBottom() }
)

onMounted(async () => {
    await chatStore.loadConversations()
    await loadConnectorStatus()
    await scrollToBottom()
    await resizeChatTextarea()

    const container = chatDialogueRef.value
    if (!container) return

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
})

onBeforeUnmount(() => {
    contentObserver?.disconnect()
    contentObserver = null
})
</script>

<template>
    <Main title="Chat">
        <div class="grid w-full h-full min-h-0 grid-cols-12 overflow-hidden">
            <ChatSidebar :collapsed="isSidebarCollapsed" @toggle="toggleSidebar" />
            <!-- Main section -->
            <div class="relative flex flex-col h-full min-h-0"
                :class="isSidebarCollapsed ? 'col-span-11' : 'col-span-10'">
                <div class="absolute z-20 flex items-center gap-2 top-4 right-6">
                    <ButtonGroup>
                        <ButtonGroup>
                            <Button variant="outline" @click="debugMode = !debugMode">Debug ({{ debugMode ? 'on' : 'off'
                                }})</Button>
                        </ButtonGroup>
                    </ButtonGroup>

                </div>
                <!-- Chat dialogue -->
                <div ref="chatDialogueRef" @scroll="updateScrollState"
                    class="flex flex-col flex-1 min-h-0 p-10 px-20 overflow-y-auto">
                    <!-- v-if="!selectedConversation || selectedConversation.messages.length < 1" -->
                    <div v-if="chatStore.messages.length == 0"
                        class="flex flex-col items-center justify-center h-full gap-2">
                        <p class="text-2xl text-stone-200">What would you like to talk about today?</p>
                        <div class="flex items-center gap-1 text-stone-500">
                            <svg xmlns="http://www.w3.org/2000/svg" class="text-red-500 w-9 h-9" viewBox="0 0 24 24">
                                <path fill="currentColor"
                                    d="M5 22v-4q0-.575.3-1.037t.8-.738L11 13.75V12l-3.475 1.725q-.3.15-.625.225t-.65.075q-.775 0-1.463-.4t-1.062-1.15q-.35-.675-.3-1.437T3.9 9.625L7 5L5 2h6q3.325 0 5.663 2.325T19 10v12zm2-2h10V10q0-2.5-1.75-4.25T11 4H8.75l.65 1l-3.825 5.75q-.125.2-.137.413t.087.412q.125.275.338.363t.412.087q.075 0 .375-.075L13 8.75V15l-6 3zm4-8" />
                            </svg>
                            <p class="text-xl font-medium">NetAI</p>
                        </div>
                    </div>
                    <div v-else class="flex flex-col gap-6 mt-auto">
                        <div v-if="debugMode" v-for="message in chatStore.messages">
                            <pre>
                                {{ message }}
                            </pre>
                        </div>
                        <div v-else v-for="message in chatStore.messages" class="">
                            <!-- Assistant message -->
                            <div v-if="message.role == 'assistant'">
                                <!-- Toolcalls -->
                                <ChatListTool :tool-calls="getMessageToolCalls(message)" />
                                <!-- Response -->
                                <div class="flex flex-col gap-4">
                                    <template v-for="segment in getMessageRenderSegments(message)" :key="segment.id">
                                        <MarkdownRenderer v-if="segment.type === 'markdown'"
                                            :content="segment.content" />
                                        <ConfigDiffViewer v-else :diff-files="segment.diffFiles" />
                                    </template>
                                </div>
                                <TopologyMapper v-if="getMessageTopology(getMessageToolCalls(message))"
                                    :topology="getMessageTopology(getMessageToolCalls(message)) || undefined" />
                                <!-- Feedback -->
                                <ChatActions v-if="!chatStore.isMessageStreaming(message.id)" :message-id="message.id"
                                    :content="message.content" />
                            </div>
                            <!-- User message -->
                            <div v-if="message.role == 'user'" class="flex justify-end">
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
                        <path fill="currentColor" d="m12 18l-6-6l1.4-1.4l3.6 3.575V6h2v8.175l3.6-3.575L18 12l-6 6Z" />
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
                    <div class="border rounded-md bg-stone-900/60 focus:border-stone-800 border-stone-800 px-3 py-2.5">
                        <textarea ref="chatTextareaRef" v-model="chatInputValue" @input="resizeChatTextarea"
                            @keydown.ctrl.enter.prevent="submit" rows="1" data-slot="input-group-control"
                            class="min-h-15 w-full flex  resize-none bg-transparent placeholder:text-stone-600  text-base transition-[color,box-shadow] outline-none md:text-sm"
                            placeholder="How can I help you today?" />
                        <div class="flex items-center justify-end gap-4 py-1">
                            <!-- <Button variant="default" size="xs">deep investigation</Button> -->
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
                                        <TooltipContent>
                                            <div class="p-2">
                                                <p class="font-semibold">Context window:</p>
                                                <p>{{ chatStore.contextWindow.used_percent }}% used ({{
                                                    chatStore.contextWindow.left_percent }}% left)</p>
                                                <p>{{ chatStore.contextWindow.used_tokens }} / {{
                                                    chatStore.contextWindow.left_tokens }} tokens left</p>
                                                {{ chatStore.contextWindow.compacted ? 'Compacted' : 'Not Compacted' }}
                                            </div>
                                        </TooltipContent>
                                    </Tooltip>
                                </TooltipProvider>
                                <p class="text-xs text-stone-400">Gemini Flash 2.5 </p>
                            </div>
                            <Button @click="submit" v-if="chatInputValue"
                                class="text-white bg-red-500 hover:bg-red-500/50" variant="default" size="xs">
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
    </Main>
</template>
