<script setup lang="ts">
import { computed } from 'vue'

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

const props = defineProps<{
    diffFiles?: DiffFile[]
}>()

const files = computed(() => props.diffFiles ?? [])

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
                class="flex items-center justify-center w-full gap-2 px-4 py-2 text-sm font-semibold text-center border-b bg-stone-900/40 border-stone-900 text-stone-300">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-red-500" viewBox="0 0 24 24">
                    <path fill="currentColor"
                        d="M4 2h8a3 3 0 0 1 3 3v1h-1V5a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h1v1H4a3 3 0 0 1-3-3V5a3 3 0 0 1 3-3m11 6v3h-1V9h-2V8zm3 0a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3h-8a3 3 0 0 1-3-3v-1h1v1a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V8zM7 15v-2h1v2h2v1H7zm8-2a3 3 0 0 1-3 3v-1a2 2 0 0 0 2-2zm-5-4a2 2 0 0 0-2 2H7a3 3 0 0 1 3-3z" />
                </svg>
                DIFF VIEWER
            </div>
            <div class="flex justify-between px-4 py-2 text-sm border-b bg-stone-950 border-stone-900 text-stone-300">
                <p>Edited by: <span class="font-semibold">DELLAM Hamza</span></p>
                <p>Edited the: <span class="font-semibold">2026-03-12 at 13:55:39</span></p>
            </div>

            <div class="px-4 py-2 text-sm border-b bg-stone-950 border-stone-900 text-stone-300">
                <span class="text-stone-400">{{ file.old_path }}</span> -> <span class="text-stone-400">{{ file.new_path
                    }}</span>
            </div>

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

                    <template v-for="row in mapHunkRows(hunk.lines)" :key="`${hunk.header}-${hunkIndex}-${row.key}`">
                        <div class="flex min-w-0 gap-3 px-3 py-1 border-r border-stone-900" :class="{
                            'border-x-2 border-dotted border-red-500 bg-red-500/15': row.left.tone === 'removed',
                            'bg-stone-950/20': row.left.tone === 'neutral'
                        }">
                            <span v-if="row.left.tone === 'removed'" class="text-red-500">-</span>
                            <span v-else class="w-2"></span>
                            <span class="w-4 text-right select-none shrink-0 text-stone-500">{{ row.left.lineNo ?? ''
                            }}</span>
                            <pre class="m-0 overflow-x-auto whitespace-pre text-stone-200">{{ row.left.content }}</pre>
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
                            <pre class="m-0 overflow-x-auto whitespace-pre text-stone-200">{{ row.right.content }}</pre>
                        </div>
                    </template>
                </div>
            </div>
        </div>
    </div>
</template>
