<script setup lang="ts">
import Button from '@/components/ui/button/Button.vue'
import type { ChatAttachment } from '@/types/chat.type'

const props = defineProps<{
    attachments: ChatAttachment[]
    isUploading?: boolean
}>()

const emit = defineEmits<{
    add: []
    remove: [attachmentId: number]
}>()

function formatBytes(value: number): string {
    if (value < 1024) return `${value} B`
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
    return `${(value / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<template>
    <div class="flex items-center min-w-0 gap-2">
        <Button type="button" variant="ghost" size="icon"
            class="w-8 h-8 shrink-0 text-stone-300 hover:bg-stone-800 hover:text-stone-100" @click="emit('add')"
            :disabled="props.isUploading" :title="props.isUploading ? 'Attaching document...' : 'Attach document'"
            aria-label="Attach document">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24">
                <path fill="currentColor"
                    d="M16.346 11.385V6.769h1v4.616zm-5.538 5.457q-.452-.269-.726-.734q-.274-.466-.274-1.031V6.769h1zM11.96 21q-2.271 0-3.846-1.595t-1.575-3.867v-8.73q0-1.587 1.09-2.697Q8.722 3 10.309 3t2.678 1.11t1.091 2.698V14h-1V6.789q-.006-1.166-.802-1.977T10.308 4q-1.163 0-1.966.821q-.804.821-.804 1.987v8.73q-.005 1.853 1.283 3.157Q10.11 20 11.961 20q.556 0 1.056-.124t.945-.372v1.11q-.468.2-.972.293q-.505.093-1.03.093m4.386-1v-2.616h-2.615v-1h2.615V13.77h1v2.615h2.616v1h-2.616V20z" />
            </svg>
        </Button>

        <div v-if="props.attachments.length > 0" class="flex flex-wrap min-w-0 gap-2">
            <div v-for="attachment in props.attachments" :key="`attachment-${attachment.id}`"
                class="inline-flex items-center gap-2 rounded-full border border-stone-700 bg-stone-900/70 px-3 py-1.5 text-xs text-stone-300">
                <span class="font-medium text-stone-200">{{ attachment.filename }}</span>
                <span class="text-stone-500">{{ formatBytes(attachment.size_bytes) }}</span>
                <span v-if="attachment.truncated" class="text-amber-400">truncated</span>
                <button type="button" class="transition text-stone-500 hover:text-stone-100"
                    @click="emit('remove', attachment.id)">
                    Remove
                </button>
            </div>
        </div>
    </div>
</template>
