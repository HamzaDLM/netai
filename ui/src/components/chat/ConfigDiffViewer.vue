<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

type DiffLineType = 'context' | 'added' | 'removed' | 'meta'

interface DiffLine {
    type: DiffLineType
    old_lineno: number | null
    new_lineno: number | null
    content: string
}

interface DiffHunk {
    header: string
    old_start: number
    old_lines: number
    new_start: number
    new_lines: number
    lines: DiffLine[]
}

interface DiffFile {
    old_path: string
    new_path: string
    hunks: DiffHunk[]
}

interface DiffCell {
    lineNo: number | null
    content: string
    tone: 'neutral' | 'added' | 'removed'
}

interface DiffRow {
    key: string
    left: DiffCell
    right: DiffCell
}

type DiffStats = Record<DiffLineType, number>

const props = defineProps<{
    diffFiles?: DiffFile[]
}>()

const isZoomed = ref(false)
const files = computed(() => props.diffFiles ?? [])
const counters = computed(() => {
    const stats: DiffStats = {
        context: 0,
        added: 0,
        removed: 0,
        meta: 0
    }

    if (!props.diffFiles) return stats

    for (const file of props.diffFiles) {
        for (const hunk of file.hunks) {
            for (const line of hunk.lines) {
                stats[line.type]++
            }
        }
    }

    return stats
})

function blankCell(): DiffCell {
    return { lineNo: null, content: '', tone: 'neutral' }
}

function mapHunkRows(lines: DiffLine[]): DiffRow[] {
    const rows: DiffRow[] = []
    let i = 0
    let rowCounter = 0

    while (i < lines.length) {
        const line = lines[i]

        if (line.type === 'context' || line.type === 'meta') {
            rows.push({
                key: `row-${rowCounter++}`,
                left: {
                    lineNo: line.old_lineno,
                    content: line.content,
                    tone: 'neutral',
                },
                right: {
                    lineNo: line.new_lineno,
                    content: line.content,
                    tone: 'neutral',
                },
            })
            i += 1
            continue
        }

        if (line.type === 'removed') {
            const removed: DiffLine[] = []
            while (i < lines.length && lines[i].type === 'removed') {
                removed.push(lines[i])
                i += 1
            }

            const added: DiffLine[] = []
            while (i < lines.length && lines[i].type === 'added') {
                added.push(lines[i])
                i += 1
            }

            const maxLen = Math.max(removed.length, added.length)
            for (let idx = 0; idx < maxLen; idx += 1) {
                const r = removed[idx]
                const a = added[idx]
                rows.push({
                    key: `row-${rowCounter++}`,
                    left: r
                        ? { lineNo: r.old_lineno, content: r.content, tone: 'removed' }
                        : blankCell(),
                    right: a
                        ? { lineNo: a.new_lineno, content: a.content, tone: 'added' }
                        : blankCell(),
                })
            }
            continue
        }

        // added with no adjacent removed block
        rows.push({
            key: `row-${rowCounter++}`,
            left: blankCell(),
            right: {
                lineNo: line.new_lineno,
                content: line.content,
                tone: 'added',
            },
        })
        i += 1
    }

    return rows
}

function openZoom(): void {
    isZoomed.value = true
}

function closeZoom(): void {
    isZoomed.value = false
}

function onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape' && isZoomed.value) {
        closeZoom()
    }
}

function onDiffBodyWheel(event: WheelEvent): void {
    const container = event.currentTarget as HTMLElement | null
    if (!container) return

    event.stopPropagation()

    const canScrollVertically = container.scrollHeight > container.clientHeight
    const canScrollHorizontally = container.scrollWidth > container.clientWidth

    if (event.shiftKey && canScrollHorizontally) {
        container.scrollLeft += event.deltaY + event.deltaX
        event.preventDefault()
        return
    }

    if (canScrollVertically) {
        const atTop = container.scrollTop <= 0
        const atBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 1
        if ((event.deltaY < 0 && atTop) || (event.deltaY > 0 && atBottom)) {
            event.preventDefault()
        }
        return
    }

    if (canScrollHorizontally && event.deltaY !== 0) {
        container.scrollLeft += event.deltaY
        event.preventDefault()
    }
}

onMounted(() => {
    window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
    window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
    <div class="flex flex-col gap-4 py-4">
        <div v-if="files.length === 0"
            class="p-4 text-sm border rounded-md border-stone-900 text-stone-400 bg-stone-950">
            No diff available.
        </div>
        <div v-for="file in files" :key="`${file.old_path}-${file.new_path}`"
            class="overflow-hidden border rounded-md border-stone-900">
            <div
                class="flex items-center justify-between w-full gap-2 px-4 py-2 text-sm font-semibold text-center border-b bg-stone-900/40 border-stone-900 text-stone-300">
                <div></div>
                <div class="flex items-center justify-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-red-500" viewBox="0 0 24 24">
                        <path fill="currentColor"
                            d="M4 2h8a3 3 0 0 1 3 3v1h-1V5a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h1v1H4a3 3 0 0 1-3-3V5a3 3 0 0 1 3-3m11 6v3h-1V9h-2V8zm3 0a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3h-8a3 3 0 0 1-3-3v-1h1v1a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V8zM7 15v-2h1v2h2v1H7zm8-2a3 3 0 0 1-3 3v-1a2 2 0 0 0 2-2zm-5-4a2 2 0 0 0-2 2H7a3 3 0 0 1 3-3z" />
                    </svg>
                    DIFF VIEWER
                </div>
                <button class="p-1 text-xs" @click="openZoom">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-stone-400 hover:text-stone-200"
                        viewBox="0 0 24 24">
                        <path fill="currentColor"
                            d="M6.4 19H8q.425 0 .713.288T9 20t-.288.713T8 21H4q-.425 0-.712-.288T3 20v-4q0-.425.288-.712T4 15t.713.288T5 16v1.6l2.4-2.4q.275-.275.7-.275t.7.275t.275.7t-.275.7zm11.2 0l-2.4-2.4q-.275-.275-.275-.7t.275-.7t.7-.275t.7.275l2.4 2.4V16q0-.425.288-.712T20 15t.713.288T21 16v4q0 .425-.288.713T20 21h-4q-.425 0-.712-.288T15 20t.288-.712T16 19zM5 6.4V8q0 .425-.288.713T4 9t-.712-.288T3 8V4q0-.425.288-.712T4 3h4q.425 0 .713.288T9 4t-.288.713T8 5H6.4l2.4 2.4q.275.275.275.7t-.275.7t-.7.275t-.7-.275zm14 0l-2.4 2.4q-.275.275-.7.275t-.7-.275t-.275-.7t.275-.7L17.6 5H16q-.425 0-.712-.287T15 4t.288-.712T16 3h4q.425 0 .713.288T21 4v4q0 .425-.288.713T20 9t-.712-.288T19 8z" />
                    </svg>
                </button>
            </div>
            <div class="flex justify-between px-4 py-2 text-sm border-b bg-stone-950 border-stone-900 text-stone-300">
                <p>Commit Message: <span class="font-semibold">Restrict management ACL on VTY</span></p>
                <p><span class="text-green-500">+{{ counters.added }}</span> <span class="text-red-500">-{{
                    counters.removed }}</span></p>
            </div>
            <div class="flex justify-between px-4 py-2 text-sm border-b bg-stone-950 border-stone-900 text-stone-300">
                <p>Author: <span class="font-semibold">DELLAM Hamza</span></p>
                <p><span class="font-semibold">2026-03-12 at 13:55:39</span></p>
            </div>

            <div class="px-4 py-2 text-sm border-b bg-stone-950 border-stone-900 text-stone-300">
                <span class="text-stone-400">{{ file.old_path }}</span> -> <span class="text-stone-400">{{ file.new_path
                    }}</span>
            </div>

            <div class="max-h-[28rem] overflow-auto" @wheel="onDiffBodyWheel">
                <div v-for="(hunk, hunkIndex) in file.hunks" :key="`${hunk.header}-${hunkIndex}`"
                    class="border-b border-stone-900 last:border-b-0">

                    <div class="grid grid-cols-2 font-mono text-xs">
                        <div
                            class="px-3 py-1 text-sm font-semibold border-r text-stone-400 border-stone-900 bg-stone-950/70">
                            Before
                        </div>
                        <div class="px-3 py-1 text-sm font-semibold text-stone-400 bg-stone-950/70">
                            After
                        </div>

                        <template v-for="row in mapHunkRows(hunk.lines)"
                            :key="`${hunk.header}-${hunkIndex}-${row.key}`">
                            <div class="flex min-w-0 gap-3 px-3 py-1 border-r border-stone-900" :class="{
                                'border-x-2 border-dotted border-red-500 bg-red-500/15': row.left.tone === 'removed',
                                'bg-stone-950/20': row.left.tone === 'neutral'
                            }">
                                <span v-if="row.left.tone === 'removed'" class="text-red-500">-</span>
                                <span v-else class="w-2"></span>
                                <span class="w-4 text-right select-none shrink-0 text-stone-500">{{ row.left.lineNo ??
                                    ''
                                }}</span>
                                <pre class="m-0 overflow-x-auto whitespace-pre text-stone-200">{{ row.left.content }}
                                </pre>
                            </div>

                            <div class="flex min-w-0 gap-3 px-3 py-1 border-r border-stone-900" :class="{
                                'border-x-2 border-dotted border-green-500 bg-green-500/15': row.right.tone === 'added',
                                'bg-stone-950/20': row.right.tone === 'neutral'
                            }">
                                <span v-if="row.right.tone === 'added'" class="w-2 text-green-500">+</span>
                                <span v-else class="w-2"></span>
                                <span class="w-4 text-right select-none shrink-0 text-stone-500">{{ row.right.lineNo ??
                                    ''
                                }}</span>
                                <pre class="m-0 overflow-x-auto whitespace-pre text-stone-200">{{ row.right.content }}
                                </pre>
                            </div>
                        </template>
                    </div>
                </div>
            </div>
        </div>

        <Teleport to="body">
            <div v-if="isZoomed" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
                <div class="w-[90vw] h-[90vh] overflow-hidden border rounded-lg border-stone-800 bg-stone-950">
                    <div
                        class="flex items-center justify-between w-full gap-2 px-4 py-2 text-sm font-semibold border-b bg-stone-900/50 border-stone-800 text-stone-200">
                        <div></div>
                        <div class="flex items-center gap-2">
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-red-500" viewBox="0 0 24 24">
                                <path fill="currentColor"
                                    d="M4 2h8a3 3 0 0 1 3 3v1h-1V5a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h1v1H4a3 3 0 0 1-3-3V5a3 3 0 0 1 3-3m11 6v3h-1V9h-2V8zm3 0a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3h-8a3 3 0 0 1-3-3v-1h1v1a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V8zM7 15v-2h1v2h2v1H7zm8-2a3 3 0 0 1-3 3v-1a2 2 0 0 0 2-2zm-5-4a2 2 0 0 0-2 2H7a3 3 0 0 1 3-3z" />
                            </svg>
                            DIFF VIEWER
                        </div>
                        <button @click="closeZoom">
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-stone-400 hover:text-stone-200"
                                viewBox="0 0 24 24">
                                <path fill="currentColor"
                                    d="m12 13.4l-4.9 4.9q-.275.275-.7.275t-.7-.275t-.275-.7t.275-.7l4.9-4.9l-4.9-4.9q-.275-.275-.275-.7t.275-.7t.7-.275t.7.275l4.9 4.9l4.9-4.9q.275-.275.7-.275t.7.275t.275.7t-.275.7L13.4 12l4.9 4.9q.275.275.275.7t-.275.7t-.7.275t-.7-.275z" />
                            </svg>
                        </button>
                    </div>

                    <div class="h-[calc(90vh-40px)] overflow-auto">
                        <div v-for="file in files" :key="`zoom-${file.old_path}-${file.new_path}`"
                            class="border-b border-stone-800 last:border-b-0">
                            <div
                                class="flex justify-between px-4 py-2 text-sm border-b bg-stone-950 border-stone-800 text-stone-300">
                                <p>Commit Message: <span class="font-semibold">Restrict management ACL on VTY</span></p>
                                <p><span class="text-green-500">+{{ counters.added }}</span> <span
                                        class="text-red-500">-{{
                                            counters.removed }}</span></p>
                            </div>
                            <div
                                class="flex justify-between px-4 py-2 text-sm border-b bg-stone-950 border-stone-800 text-stone-300">
                                <p>Author: <span class="font-semibold">DELLAM Hamza</span></p>
                                <p><span class="font-semibold">2026-03-12 at 13:55:39</span></p>
                            </div>
                            <div class="px-4 py-2 text-sm border-b bg-stone-950 border-stone-800 text-stone-300">
                                <span class="text-stone-400">{{ file.old_path }}</span> -> <span
                                    class="text-stone-400">{{
                                        file.new_path }}</span>
                            </div>

                            <div class="max-h-[calc(90vh-180px)] overflow-auto" @wheel="onDiffBodyWheel">
                                <div v-for="(hunk, hunkIndex) in file.hunks" :key="`zoom-${hunk.header}-${hunkIndex}`"
                                    class="border-b border-stone-800 last:border-b-0">
                                    <div class="grid grid-cols-2 font-mono text-xs">
                                        <div
                                            class="px-3 py-1 text-sm font-semibold border-r text-stone-400 border-stone-800 bg-stone-950/70">
                                            Before
                                        </div>
                                        <div class="px-3 py-1 text-sm font-semibold text-stone-400 bg-stone-950/70">
                                            After
                                        </div>

                                        <template v-for="row in mapHunkRows(hunk.lines)"
                                            :key="`zoom-${hunk.header}-${hunkIndex}-${row.key}`">
                                            <div class="flex min-w-0 gap-3 px-3 py-1 border-r border-stone-800" :class="{
                                                'border-x-2 border-dotted border-red-500 bg-red-500/15': row.left.tone === 'removed',
                                                'bg-stone-950/20': row.left.tone === 'neutral'
                                            }">
                                                <span v-if="row.left.tone === 'removed'" class="text-red-500">-</span>
                                                <span v-else class="w-2"></span>
                                                <span class="w-4 text-right select-none shrink-0 text-stone-500">{{
                                                    row.left.lineNo ?? ''
                                                }}</span>
                                                <pre class="m-0 overflow-x-auto whitespace-pre text-stone-200">{{
                                                    row.left.content }}</pre>
                                            </div>
                                            <div class="flex min-w-0 gap-3 px-3 py-1 border-r border-stone-800" :class="{
                                                'border-x-2 border-dotted border-green-500 bg-green-500/15': row.right.tone === 'added',
                                                'bg-stone-950/20': row.right.tone === 'neutral'
                                            }">
                                                <span v-if="row.right.tone === 'added'"
                                                    class="w-2 text-green-500">+</span>
                                                <span v-else class="w-2"></span>
                                                <span class="w-4 text-right select-none shrink-0 text-stone-500">{{
                                                    row.right.lineNo ?? ''
                                                }}</span>
                                                <pre class="m-0 overflow-x-auto whitespace-pre text-stone-200">{{
                                                    row.right.content }}</pre>
                                            </div>
                                        </template>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </Teleport>
    </div>
</template>
