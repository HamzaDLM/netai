<script setup lang="ts">
import { ref } from 'vue'
import Button from '@/components/ui/button/Button.vue'
import chatService from '@/services/chat.service'
import { toast } from '@/components/ui/toast'
import {
    Dialog,
    DialogClose,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const props = defineProps<{
    messageId: number
    content: string
}>()

const rating = ref<'good' | 'bad' | null>(null)
const comment = ref('')
const copied = ref(false)
const isSubmitting = ref(false)
const submitted = ref(false)

const localOnlyThreshold = 1000

async function copyMessage(): Promise<void> {
    try {
        await navigator.clipboard.writeText(props.content || '')
        copied.value = true
        toast({ title: 'Assistant message copied' })
        setTimeout(() => {
            copied.value = false
        }, 1200)
    } catch {
        toast({ title: 'Failed to copy message', variant: 'destructive' })
    }
}

async function submitFeedback(): Promise<void> {
    if (props.messageId >= localOnlyThreshold) {
        toast({ title: 'Feedback unavailable before message sync', variant: 'destructive' })
        return
    }

    isSubmitting.value = true
    try {
        const params = {}
        if (comment) params["comment"] = comment.value.trim()
        if (rating) params["rating"] = rating.value
        await chatService.submitFeedback(props.messageId, params)
        submitted.value = true
        toast({ title: 'Feedback sent. Thanks!' })
    } catch {
        toast({ title: 'Failed to submit feedback', variant: 'destructive' })
    } finally {
        isSubmitting.value = false
    }
}
</script>

<template>
    <div class="flex flex-col gap-2 mt-3 mb-4">
        <div class="flex items-center gap-2">
            <Button variant="link" size="xs" @click="copyMessage">
                <!-- {{ copied ? 'Copied' : 'Copy' }} -->
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24">
                    <g fill="none" stroke="currentColor" stroke-width="1.5">
                        <path
                            d="M6 11c0-2.828 0-4.243.879-5.121C7.757 5 9.172 5 12 5h3c2.828 0 4.243 0 5.121.879C21 6.757 21 8.172 21 11v5c0 2.828 0 4.243-.879 5.121C19.243 22 17.828 22 15 22h-3c-2.828 0-4.243 0-5.121-.879C6 20.243 6 18.828 6 16z" />
                        <path d="M6 19a3 3 0 0 1-3-3v-6c0-3.771 0-5.657 1.172-6.828S7.229 2 11 2h4a3 3 0 0 1 3 3"
                            opacity=".5" />
                    </g>
                </svg>
            </Button>
            <Button variant="link" size="xs" :class="rating === 'good' ? 'border-emerald-500 text-emerald-300' : ''"
                @click="rating = 'good'">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24">
                    <g fill="none" fill-rule="evenodd">
                        <path
                            d="m12.593 23.258l-.011.002l-.071.035l-.02.004l-.014-.004l-.071-.035q-.016-.005-.024.005l-.004.01l-.017.428l.005.02l.01.013l.104.074l.015.004l.012-.004l.104-.074l.012-.016l.004-.017l-.017-.427q-.004-.016-.017-.018m.265-.113l-.013.002l-.185.093l-.01.01l-.003.011l.018.43l.005.012l.008.007l.201.093q.019.005.029-.008l.004-.014l-.034-.614q-.005-.018-.02-.022m-.715.002a.02.02 0 0 0-.027.006l-.006.014l-.034.614q.001.018.017.024l.015-.002l.201-.093l.01-.008l.004-.011l.017-.43l-.003-.012l-.01-.01z" />
                        <path fill="currentColor"
                            d="M8.993 5.163c.169 1.423-.062 2.907-.576 4.239c-.569 1.474-1.325 3.07-1.419 4.657c-.079 1.337.224 2.919 1.032 4.002C8.915 19.247 10.368 20 11.967 20h1.512a5 5 0 0 0 4.983-4.585l.361-4.332A1 1 0 0 0 17.826 10H12.5a1.503 1.503 0 0 1-1.501-1.492c-.008-.97.053-2.167-.393-3.06c-.4-.8-.774-.948-1.106-.948c-.3 0-.54.393-.507.663M9.5 2.5c1.356 0 2.294.852 2.895 2.053c.522 1.045.571 2.3.597 3.447h4.834a3 3 0 0 1 2.99 3.25l-.361 4.331A7 7 0 0 1 13.479 22h-1.512A6.94 6.94 0 0 1 6.9 19.822A5.5 5.5 0 0 1 5.5 20c-1.108 0-2.028-.62-2.624-1.608C2.296 17.432 2 16.107 2 14.5s.297-2.931.876-3.891C3.472 9.62 4.392 9 5.5 9c.281 0 .579.05.877.134c.458-1.2.784-2.437.63-3.735C6.835 3.954 8.016 2.5 9.5 2.5m-3.804 8.524c-.485-.1-.865.216-1.107.618C4.263 12.182 4 13.106 4 14.5s.263 2.319.588 2.859c.31.512.64.641.912.641q.096 0 .19-.005c-.536-1.208-.766-2.74-.688-4.054c.047-.805.361-1.918.694-2.917" />
                    </g>
                </svg>
            </Button>
            <Button variant="link" size="xs" :class="rating === 'bad' ? 'border-rose-500 text-rose-300' : ''"
                @click="rating = 'bad'">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24">
                    <g fill="none" fill-rule="evenodd">
                        <path
                            d="m12.593 23.258l-.011.002l-.071.035l-.02.004l-.014-.004l-.071-.035q-.016-.005-.024.005l-.004.01l-.017.428l.005.02l.01.013l.104.074l.015.004l.012-.004l.104-.074l.012-.016l.004-.017l-.017-.427q-.004-.016-.017-.018m.265-.113l-.013.002l-.185.093l-.01.01l-.003.011l.018.43l.005.012l.008.007l.201.093q.019.005.029-.008l.004-.014l-.034-.614q-.005-.018-.02-.022m-.715.002a.02.02 0 0 0-.027.006l-.006.014l-.034.614q.001.018.017.024l.015-.002l.201-.093l.01-.008l.004-.011l.017-.43l-.003-.012l-.01-.01z" />
                        <path fill="currentColor"
                            d="M8.993 18.837c.169-1.423-.062-2.907-.576-4.239c-.569-1.474-1.325-3.07-1.419-4.657c-.079-1.337.224-2.919 1.032-4.002C8.915 4.753 10.368 4 11.967 4h1.512a5 5 0 0 1 4.983 4.585l.361 4.332A1 1 0 0 1 17.826 14H12.5c-.831 0-1.495.673-1.501 1.492c-.008.97.053 2.167-.393 3.06c-.4.8-.774.948-1.106.948c-.3 0-.54-.393-.507-.663M9.5 21.5c1.356 0 2.294-.852 2.895-2.053c.522-1.044.571-2.3.597-3.447h4.834a3 3 0 0 0 2.99-3.25l-.361-4.331A7 7 0 0 0 13.479 2h-1.512A6.94 6.94 0 0 0 6.9 4.179a5.5 5.5 0 0 0-1.4-.18c-1.108 0-2.028.622-2.624 1.61c-.58.96-.876 2.284-.876 3.89s.297 2.932.876 3.892C3.472 14.38 4.392 15 5.5 15c.281 0 .579-.05.877-.134c.458 1.2.784 2.437.63 3.735C6.835 20.046 8.016 21.5 9.5 21.5m-3.804-8.524c-.485.1-.865-.216-1.107-.618C4.263 11.818 4 10.894 4 9.5s.263-2.319.588-2.859c.31-.512.64-.641.912-.641q.096 0 .19.005c-.536 1.208-.766 2.74-.688 4.054c.047.805.361 1.918.694 2.917" />
                    </g>
                </svg>
            </Button>
            <div class="flex w-full gap-2">
                <!-- <input v-model="comment" rows="2"
                    class="w-full px-3 py-2 text-xs rounded outline-none resize-y bg-stone-900/50 text-stone-200 placeholder:text-stone-500"
                    placeholder="Let us know if you think something is wrong..." />
                <div class="flex justify-end">
                    <Button variant="link" size="xs" :disabled="isSubmitting || submitted" @click="submitFeedback">
                        {{ submitted ? 'Submitted' : isSubmitting ? 'Submitting...' : 'Send feedback' }}
                    </Button>
                </div> -->
                <Dialog>
                    <form>
                        <DialogTrigger as-child>
                            <Button variant="ghost">
                                Send Feedback
                            </Button>
                        </DialogTrigger>
                        <DialogContent class="sm:max-w-[625px]">
                            <DialogHeader>
                                <DialogTitle>Send feedback</DialogTitle>
                                <DialogDescription>
                                    Your feedback is essential to improving NetAI.
                                </DialogDescription>
                            </DialogHeader>
                            <div class="grid gap-4">
                                <div class="grid gap-3">
                                    <Input id="name-1" name="name" default-value="Pedro Duarte" />
                                </div>
                            </div>
                            <DialogFooter>
                                <DialogClose as-child>
                                    <Button variant="outline">
                                        Cancel
                                    </Button>
                                </DialogClose>
                                <Button type="submit">
                                    Save changes
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </form>
                </Dialog>
            </div>
        </div>
    </div>
</template>
