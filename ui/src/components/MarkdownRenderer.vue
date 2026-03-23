<script setup lang="ts">
import { computed } from "vue"
import { useGenericStore } from '@/stores/generic.store'
import { createMarkdown, renderMarkdown } from "@/lib/markdown"

const props = defineProps<{
    content: string
}>()

const genericStore = useGenericStore()

const safeHtml = computed<string>(() =>
    renderMarkdown(createMarkdown(genericStore.codeHighlighter), props.content)
)
</script>

<template>
    <div class="llm-content" v-html="safeHtml" />
</template>

<style>
.llm-content {
    @apply text-base leading-relaxed text-zinc-200;
}

.llm-content p {
    @apply pb-4;
}

.llm-content pre {
    @apply bg-stone-900/20 border border-zinc-900 p-4 my-4 rounded-lg overflow-x-auto !important;
    white-space: pre;
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
