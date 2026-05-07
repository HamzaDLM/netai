<script setup lang="ts">
import { computed, ref } from "vue"
import { useGenericStore } from '@/stores/generic.store'
import { createMarkdown, renderMarkdown } from "@/lib/markdown"
import { toast } from '@/components/ui/toast'

const props = defineProps<{
    content: string
}>()

const genericStore = useGenericStore()
const rootRef = ref<HTMLElement | null>(null)

const safeHtml = computed<string>(() =>
    renderMarkdown(createMarkdown(genericStore.codeHighlighter), props.content)
)

async function handleContentClick(event: MouseEvent): Promise<void> {
    const target = event.target as HTMLElement | null
    const button = target?.closest('[data-copy-code]') as HTMLButtonElement | null
    if (!button) return

    const container = button.closest('.code-block') as HTMLElement | null
    const codeElement = container?.querySelector('pre code')
    const code = codeElement?.textContent ?? ''
    if (!code) return

    try {
        await navigator.clipboard.writeText(code)
        button.textContent = 'Copied'
        window.setTimeout(() => {
            if (button.isConnected) button.textContent = 'Copy'
        }, 1200)
    } catch {
        toast({ title: 'Failed to copy code', variant: 'destructive' })
    }
}
</script>

<template>
    <div ref="rootRef" class="llm-content" v-html="safeHtml" @click="handleContentClick" />
</template>

<style>
.llm-content {
    @apply text-base leading-relaxed text-zinc-200;
}

.llm-content p {
    @apply pb-4;
}

.llm-content .code-block {
    @apply my-4 overflow-hidden rounded-lg bg-stone-900/20;
}

.llm-content .code-block__header {
    @apply flex items-center justify-between px-4 py-2 text-[11px] uppercase tracking-[0.18em] text-stone-500;
}

.llm-content .code-block__lang {
    @apply truncate;
}

.llm-content .code-block__copy {
    @apply rounded px-0 py-0 text-[11px] tracking-[0.12em] text-stone-400 transition hover:text-stone-100;
}

.llm-content pre {
    @apply m-0 overflow-x-auto px-4 pb-4 pt-1 !important;
    white-space: pre;
}

.llm-content .code-block .shiki {
    background: transparent !important;
}

.llm-content code {
    @apply font-mono text-xs;
}

.llm-content :not(pre)>code {
    @apply rounded-md border border-stone-800 bg-stone-900/60 px-1.5 py-0.5 text-stone-100;
}

.llm-content table {
    @apply w-min whitespace-nowrap border-collapse text-xs my-6;
}

.llm-content th,
.llm-content td {
    @apply border border-stone-900 px-2 py-2;
}

.llm-content hr {
    @apply py-2
}

.llm-content h1 {
    @apply text-3xl font-bold mt-6 mb-2;
}

.llm-content h2 {
    @apply text-xl font-semibold mt-6 mb-2;
}

.llm-content h3 {
    @apply text-lg font-semibold mt-6 mb-2;
}

.llm-content ul {
    @apply list-disc pl-6 my-4;
}

.llm-content ol {
    @apply list-decimal pl-6 my-4;
}

.llm-content li {
    @apply mb-2;
}
</style>
