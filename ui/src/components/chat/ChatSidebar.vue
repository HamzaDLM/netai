<script setup lang="ts">
import ChatSettingsDialog from '@/components/chat/ChatSettingsDialog.vue'
import { formatDatetime } from '@/lib/utils';
import router from '@/router';
import Button from '../ui/button/Button.vue';
import { useChatStore } from '@/stores/chat.store';
import { onBeforeUnmount, ref, watch } from 'vue';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Trash2Icon } from 'lucide-vue-next';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle
} from '@/components/ui/dialog'

type ChatWorkspaceView = 'chat' | 'skills' | 'connectors' | 'admin'

const chatStore = useChatStore()
const renderedTitles = ref<Record<string, string>>({})
const typingStates = ref<Record<string, boolean>>({})
const typingTimers = new Map<string, ReturnType<typeof setInterval>>()

const props = defineProps<{
    collapsed?: boolean
    activeView?: ChatWorkspaceView
    historySearchQuery?: string
}>()

const emit = defineEmits<{
    (event: 'update:historySearchQuery', value: string): void
    (event: 'toggle'): void
    (event: 'navigate', value: ChatWorkspaceView): void
}>()

// Rename logic

const renameDialogOpen = ref(false)
const pendingRenameId = ref<string | null>(null)
const newTitle = ref("")

function openRenameDialog(conversation_id: string, title: string) {
    renameDialogOpen.value = true
    pendingRenameId.value = conversation_id
    newTitle.value = title
}

async function renameConversation() {
    if (!pendingRenameId.value) return
    await chatStore.renameConversation(pendingRenameId.value, newTitle.value)
    resetRename()
}

function resetRename() {
    pendingRenameId.value = null
    renameDialogOpen.value = false
    newTitle.value = ""
    resetState()
}


// Deletion logic

const deleteDialogOpen = ref(false)
const pendingDeleteId = ref<string | null>(null)

function openDeleteDialog(conversation_id: string) {
    pendingDeleteId.value = conversation_id
    deleteDialogOpen.value = true
}

async function confirmDelete() {
    if (pendingDeleteId.value === null) return
    await chatStore.deleteConversation(pendingDeleteId.value)
    deleteDialogOpen.value = false
    pendingDeleteId.value = null
    resetState()
}

// Search logic

const historySearchQuery = ref(props.historySearchQuery ?? '')
let historySearchDebounceTimer: ReturnType<typeof setTimeout> | null = null

const onSearchInput = (event: Event) => {
    const target = event.target as HTMLInputElement | null
    historySearchQuery.value = target?.value ?? ''
    if (historySearchDebounceTimer) clearTimeout(historySearchDebounceTimer)
    historySearchDebounceTimer = setTimeout(() => {
        emit('update:historySearchQuery', historySearchQuery.value)
    }, 220)
}

watch(
    () => props.historySearchQuery,
    value => {
        historySearchQuery.value = value ?? ''
    }
)

onBeforeUnmount(() => {
    if (historySearchDebounceTimer) clearTimeout(historySearchDebounceTimer)
})

function resetState() {
    emit('navigate', 'chat')
    chatStore.resetChatState()
    chatStore.loadConversations()
}

function handleChatClick() {
    emit('navigate', 'chat')
    chatStore.createConversation()
}

function handleSkillsClick() {
    emit('navigate', 'skills')
}

function handleConnectorsClick() {
    emit('navigate', 'connectors')
}

function handleAdminClick() {
    emit('navigate', 'admin')
}

async function selectConversation(conversationId: string) {
    emit('navigate', 'chat')
    await chatStore.selectConversation(conversationId)

    if (!historySearchQuery.value?.trim()) return

    if (historySearchDebounceTimer) {
        clearTimeout(historySearchDebounceTimer)
        historySearchDebounceTimer = null
    }
    historySearchQuery.value = ''
    emit('update:historySearchQuery', '')
}

function getConversationTitle(title: string): string {
    return title.trim() ? title : 'Unnamed'
}

function stopTyping(conversationId: string) {
    const timer = typingTimers.get(conversationId)
    if (timer) clearInterval(timer)
    typingTimers.delete(conversationId)
    delete typingStates.value[conversationId]
}

function startTypingTitle(conversationId: string, nextTitle: string) {
    stopTyping(conversationId)
    renderedTitles.value[conversationId] = ''
    typingStates.value[conversationId] = true

    let index = 0
    const timer = setInterval(() => {
        index += 1
        renderedTitles.value[conversationId] = nextTitle.slice(0, index)
        if (index >= nextTitle.length) {
            stopTyping(conversationId)
        }
    }, 28)

    typingTimers.set(conversationId, timer)
}

watch(
    () => chatStore.conversations.map(conversation => ({
        id: conversation.id,
        title: conversation.title,
    })),
    (nextConversations, previousConversations = []) => {
        const previousTitles = new Map(
            previousConversations.map(conversation => [
                conversation.id,
                getConversationTitle(conversation.title),
            ])
        )

        const activeIds = new Set(nextConversations.map(conversation => conversation.id))
        for (const conversationId of Object.keys(renderedTitles.value)) {
            if (activeIds.has(conversationId)) continue
            delete renderedTitles.value[conversationId]
            stopTyping(conversationId)
        }

        for (const conversation of nextConversations) {
            const nextTitle = getConversationTitle(conversation.title)
            const previousTitle = previousTitles.get(conversation.id)
            const wasUntitled = previousTitle === undefined || previousTitle === 'Unnamed'
            const becameGeneratedTitle =
                nextTitle !== 'Unnamed' && previousTitle === 'Unnamed'

            if (becameGeneratedTitle) {
                startTypingTitle(conversation.id, nextTitle)
                continue
            }

            if (wasUntitled && nextTitle === 'Unnamed') {
                renderedTitles.value[conversation.id] = nextTitle
                continue
            }

            if (renderedTitles.value[conversation.id] !== nextTitle) {
                stopTyping(conversation.id)
                renderedTitles.value[conversation.id] = nextTitle
            }
        }
    },
    { immediate: true }
)

onBeforeUnmount(() => {
    for (const timer of typingTimers.values()) clearInterval(timer)
    typingTimers.clear()
})
</script>

<template>
    <div class="flex h-full min-h-0 shrink-0 flex-col overflow-hidden border-r border-stone-900/50 bg-stone-950 transition-[width,padding] duration-200"
        :class="props.collapsed ? 'w-20 py-4' : 'w-80 py-5'">
        <div class="px-4 shrink-0" :class="props.collapsed ? 'h-full' : ''">
            <div class="flex items-center justify-between gap-2 text-stone-300"
                :class="props.collapsed ? 'flex-col w-min h-full justify-between' : ''">
                <!-- Logo -->
                <div class="flex flex-col items-center gap-3">
                    <button @click="router.push('/chat')" class="flex items-center gap-1"
                        :class="props.collapsed ? ' pb-5 border-b border-stone-700' : ''">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-stone-200" viewBox="1 0 24 24">
                            <path fill="currentColor"
                                d="M5 22v-4q0-.575.3-1.037t.8-.738L11 13.75V12l-3.475 1.725q-.3.15-.625.225t-.65.075q-.775 0-1.463-.4t-1.062-1.15q-.35-.675-.3-1.437T3.9 9.625L7 5L5 2h6q3.325 0 5.663 2.325T19 10v12zm2-2h10V10q0-2.5-1.75-4.25T11 4H8.75l.65 1l-3.825 5.75q-.125.2-.137.413t.087.412q.125.275.338.363t.412.087q.075 0 .375-.075L13 8.75V15l-6 3zm4-8" />
                        </svg>
                        <span class="text-xl font-semibold tracking-wide text-stone-200"
                            v-if="!props.collapsed">NetAI <span class="text-xs">beta</span></span>
                    </button>
                    <Button v-if="props.collapsed" @click="emit('navigate', 'chat')" variant="ghost"
                        class="flex w-full gap-2 text-stone-300" size="default" title="Messages"
                        aria-label="Messages">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24">
                            <path fill="currentColor"
                                d="M4 19h12V5H4zm0 2q-.825 0-1.412-.587T2 19V5q0-.825.588-1.412T4 3h12q.825 0 1.413.588T18 5v14q0 .825-.587 1.413T16 21zm16-4v-8h2v8zm0-10V5h2v2zM4 21V3z" />
                        </svg>
                    </Button>
                    <Button v-if="props.collapsed" @click="handleConnectorsClick" variant="ghost"
                        class="flex w-full gap-2 text-stone-300" size="default" title="Connectors"
                        aria-label="Connectors">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24">
                            <path fill="currentColor"
                                d="M7 19q-.825 0-1.412-.587T5 17v-2H3q-.825 0-1.412-.587T1 13t.588-1.412T3 11h2V9q0-.825.588-1.412T7 7h3V5H9q-.825 0-1.412-.587T7 3t.588-1.412T9 1h6q.825 0 1.413.588T17 3t-.587 1.413T15 5h-1v2h3q.825 0 1.413.588T19 9v2h2q.825 0 1.413.588T23 13t-.587 1.413T21 15h-2v2q0 .825-.587 1.413T17 19zm0-2h10V9H7zm4-10h2V5h-2z" />
                        </svg>
                    </Button>
                    <Button v-if="props.collapsed" @click="handleSkillsClick" variant="ghost"
                        class="flex w-full gap-2 text-stone-300" size="default" title="Skills"
                        aria-label="Skills">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24">
                            <path fill="currentColor"
                                d="M5 20q-1.25 0-2.125-.875T2 17v-5h14.025q.125-.85.675-1.487t1.35-.913l4.625-1.55l.625 1.9l-4.625 1.55q-.3.1-.488.363T18 12.45V17q0 1.25-.875 2.125T15 20zm-.575-10q.35-.9.113-1.6T3.725 7Q2.9 6 2.637 5.112T2.55 3H4.5q-.2.95-.062 1.55t.712 1.3Q6.1 7 6.363 7.888T6.375 10zm4 0q.35-.9.125-1.6T7.75 7q-.825-1-1.1-1.888T6.55 3H8.5q-.2.95-.062 1.55t.712 1.3Q10.1 7 10.363 7.888T10.375 10zm4 0q.35-.9.125-1.6t-.8-1.4q-.825-1-1.1-1.888T10.55 3h1.95q-.2.95-.062 1.55t.712 1.3Q14.1 7 14.363 7.888T14.375 10z" />
                        </svg>
                    </Button>
                    <Button v-if="props.collapsed" @click="handleAdminClick" variant="ghost"
                        class="flex w-full gap-2 text-stone-300" size="default" title="Admin"
                        aria-label="Admin">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24">
                            <path fill="currentColor"
                                d="m5 19l-2-9l5.5 3L12 6l3.5 7L21 10l-2 9zm2.4-2h9.2l.8-3.55l-2.7 1.45L12 9.5l-2.7 5.4l-2.7-1.45z" />
                        </svg>
                    </Button>
                </div>
                <!-- Collapse sidebar -->
                <Button
                    class="p-1 transition text-stone-400 hover:bg-stone-900/60" variant="ghost"
                    @click="emit('toggle')" :aria-label="props.collapsed ? 'Expand sidebar' : 'Collapse sidebar'">
                    <svg v-if="props.collapsed" xmlns="http://www.w3.org/2000/svg" class="w-6 h-6"
                        viewBox="0 0 24 24"><!-- Icon from MingCute Icon by MingCute Design - https://github.com/Richard9394/MingCute/blob/main/LICENSE -->
                        <g fill="none" fill-rule="evenodd">
                            <path
                                d="M24 0v24H0V0zM12.594 23.258l-.012.002l-.071.035l-.02.004l-.014-.004l-.071-.036q-.016-.004-.024.006l-.004.01l-.017.428l.005.02l.01.013l.104.074l.015.004l.012-.004l.104-.074l.012-.016l.004-.017l-.017-.427q-.004-.016-.016-.018m.264-.113l-.014.002l-.184.093l-.01.01l-.003.011l.018.43l.005.012l.008.008l.201.092q.019.005.029-.008l.004-.014l-.034-.614q-.005-.018-.02-.022m-.715.002a.02.02 0 0 0-.027.006l-.006.014l-.034.614q.001.018.017.024l.015-.002l.201-.093l.01-.008l.003-.011l.018-.43l-.003-.012l-.01-.01z" />
                            <path fill="currentColor"
                                d="M6.293 6.293a1 1 0 0 1 1.414 0l5 5a1 1 0 0 1 0 1.414l-5 5a1 1 0 0 1-1.414-1.414L10.586 12L6.293 7.707a1 1 0 0 1 0-1.414m6 0a1 1 0 0 1 1.414 0l5 5a1 1 0 0 1 0 1.414l-5 5a1 1 0 0 1-1.414-1.414L16.586 12l-4.293-4.293a1 1 0 0 1 0-1.414" />
                        </g>
                    </svg>
                    <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-6 h-6"
                        viewBox="0 0 24 24">
                        <g fill="none" fill-rule="evenodd">
                            <path
                                d="M24 0v24H0V0zM12.594 23.258l-.012.002l-.071.035l-.02.004l-.014-.004l-.071-.036q-.016-.004-.024.006l-.004.01l-.017.428l.005.02l.01.013l.104.074l.015.004l.012-.004l.104-.074l.012-.016l.004-.017l-.017-.427q-.004-.016-.016-.018m.264-.113l-.014.002l-.184.093l-.01.01l-.003.011l.018.43l.005.012l.008.008l.201.092q.019.005.029-.008l.004-.014l-.034-.614q-.005-.018-.02-.022m-.715.002a.02.02 0 0 0-.027.006l-.006.014l-.034.614q.001.018.017.024l.015-.002l.201-.093l.01-.008l.003-.011l.018-.43l-.003-.012l-.01-.01z" />
                            <path fill="currentColor"
                                d="M11.707 6.293a1 1 0 0 1 0 1.414L7.414 12l4.293 4.293a1 1 0 0 1-1.414 1.414l-5-5a1 1 0 0 1 0-1.414l5-5a1 1 0 0 1 1.414 0m6 0a1 1 0 0 1 0 1.414L13.414 12l4.293 4.293a1 1 0 0 1-1.414 1.414l-5-5a1 1 0 0 1 0-1.414l5-5a1 1 0 0 1 1.414 0" />
                        </g>
                    </svg>
                </Button>
            </div>
            <!-- Search chat history -->
            <div v-if="!props.collapsed" class="mt-4">
                <input :value="historySearchQuery" @input="onSearchInput"
                    class="w-full px-3 py-2 text-sm border rounded-md outline-none bg-black/30 border-stone-900 text-stone-200 placeholder:text-stone-500 focus:border-stone-800"
                    placeholder="Search conversations..." type="text" />
            </div>
        </div>
        <div v-if="!props.collapsed" class="mx-4 my-4 flex flex-col gap-2">
            <Button @click="handleChatClick" variant="outline" size="sm" :class="[
                'flex gap-2 text-stone-300',
                'w-full']">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                    <path fill="currentColor" d="M11 13H5v-2h6V5h2v6h6v2h-6v6h-2z" />
                </svg>
                <span>Chat</span>
            </Button>
            <div class="flex gap-2">
                <Button @click="handleConnectorsClick" variant="outline" size="sm" :class="[
                    'flex gap-2 text-stone-300 bg-stone-900/40 border-stone-800',
                    'w-full',
                    props.activeView === 'connectors' ? 'border-red-500/40 bg-stone-900/70 text-stone-100' : '',
                ]">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                        <path fill="currentColor"
                            d="M7 19q-.825 0-1.412-.587T5 17v-2H3q-.825 0-1.412-.587T1 13t.588-1.412T3 11h2V9q0-.825.588-1.412T7 7h3V5H9q-.825 0-1.412-.587T7 3t.588-1.412T9 1h6q.825 0 1.413.588T17 3t-.587 1.413T15 5h-1v2h3q.825 0 1.413.588T19 9v2h2q.825 0 1.413.588T23 13t-.587 1.413T21 15h-2v2q0 .825-.587 1.413T17 19zm0-2h10V9H7zm4-10h2V5h-2z" />
                    </svg>
                    <span v-if="!props.collapsed">Connectors</span>
                </Button>
                <Button @click="handleSkillsClick" variant="outline" size="sm" :class="[
                    'flex gap-2 text-stone-300 bg-stone-900/40 border-stone-800',
                    'w-full',
                    props.activeView === 'skills' ? 'border-red-500/40 bg-stone-900/70 text-stone-100' : '',
                ]">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4"
                        viewBox="0 0 24 24"><!-- Icon from Material Symbols by Google - https://github.com/google/material-design-icons/blob/master/LICENSE -->
                        <path fill="currentColor"
                            d="M5 20q-1.25 0-2.125-.875T2 17v-5h14.025q.125-.85.675-1.487t1.35-.913l4.625-1.55l.625 1.9l-4.625 1.55q-.3.1-.488.363T18 12.45V17q0 1.25-.875 2.125T15 20zm-.575-10q.35-.9.113-1.6T3.725 7Q2.9 6 2.637 5.112T2.55 3H4.5q-.2.95-.062 1.55t.712 1.3Q6.1 7 6.363 7.888T6.375 10zm4 0q.35-.9.125-1.6T7.75 7q-.825-1-1.1-1.888T6.55 3H8.5q-.2.95-.062 1.55t.712 1.3Q10.1 7 10.363 7.888T10.375 10zm4 0q.35-.9.125-1.6t-.8-1.4q-.825-1-1.1-1.888T10.55 3h1.95q-.2.95-.062 1.55t.712 1.3Q14.1 7 14.363 7.888T14.375 10z" />
                    </svg>
                    <span v-if="!props.collapsed">Skills</span>
                </Button>
            </div>
            <Button @click="handleAdminClick" variant="outline" size="sm" :class="[
                'flex gap-2 text-stone-300 bg-stone-900/40 border-stone-800',
                'w-full',
                props.activeView === 'admin' ? 'border-red-500/40 bg-stone-900/70 text-stone-100' : '',
            ]">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                    <path fill="currentColor"
                        d="m5 19l-2-9l5.5 3L12 6l3.5 7L21 10l-2 9zm2.4-2h9.2l.8-3.55l-2.7 1.45L12 9.5l-2.7 5.4l-2.7-1.45z" />
                </svg>
                <span>Admin</span>
            </Button>
            <!-- <Button @click="resetState" variant="outline" class="w-min text-stone-300" size="sm">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                    <path fill="currentColor"
                        d="M5.53 17.506q-.978-1.142-1.504-2.558T3.5 12q0-3.616 2.664-6.058T12.5 3.5V2l3.673 2.75L12.5 7.5V6Q9.86 6 7.93 7.718T6 12q0 1.13.399 2.15t1.13 1.846zM11.5 22l-3.673-2.75L11.5 16.5V18q2.64 0 4.57-1.718T18 12q0-1.13-.399-2.16q-.399-1.028-1.13-1.855l1.998-1.51q.979 1.142 1.505 2.558T20.5 12q0 3.616-2.664 6.058T11.5 20.5z" />
                </svg>
            </Button> -->
        </div>
        <div v-if="!props.collapsed" class="flex-1 min-h-0 pr-1 space-y-2 overflow-y-auto text-sm">
            <div v-for="conversation in chatStore.conversations" @click="selectConversation(conversation.id)"
                class="flex flex-col gap-2 px-4 py-2 border-l-4 border-dotted cursor-pointer"
                :class="conversation.id == chatStore.selectedConversation?.id ? 'border-red-500/40 opacity-100 bg-stone-900/30' : 'border-transparent opacity-50 hover:opacity-80'">
                <div class="flex items-center justify-between">
                    <p class="text-xs text-stone-500">{{ formatDatetime(conversation.created_at) }}</p>
                    <DropdownMenu>
                        <DropdownMenuTrigger>
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-stone-400 hover:text-stone-200"
                                viewBox="0 0 24 24">
                                <path fill="currentColor"
                                    d="M16 12a2 2 0 0 1 2-2a2 2 0 0 1 2 2a2 2 0 0 1-2 2a2 2 0 0 1-2-2m-6 0a2 2 0 0 1 2-2a2 2 0 0 1 2 2a2 2 0 0 1-2 2a2 2 0 0 1-2-2m-6 0a2 2 0 0 1 2-2a2 2 0 0 1 2 2a2 2 0 0 1-2 2a2 2 0 0 1-2-2" />
                            </svg>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                            <DropdownMenuItem @click="openRenameDialog(conversation.id, conversation.title)">
                                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24">
                                    <path fill="currentColor"
                                        d="m12.25 10.825l.925.925L18.6 6.325l-.925-.925zM5 19h.925l5.825-5.825l-.925-.925L5 18.075zm8.875-5.125l-3.75-3.75L14.3 5.95l-.725-.725L8.1 10.7L6.7 9.3l5.45-5.475q.6-.6 1.413-.6t1.412.6l.725.725l1.25-1.25q.3-.3.713-.3t.712.3L20.7 5.625q.3.3.3.712t-.3.713zM6.75 21H3v-3.75l7.125-7.125l3.75 3.75z" />
                                </svg>
                                Rename
                            </DropdownMenuItem>
                            <DropdownMenuItem class="text-red-500 hover:text-white hover:bg-red-500"
                                @click="openDeleteDialog(conversation.id)">
                                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24">
                                    <path fill="currentColor"
                                        d="M7 21q-.825 0-1.412-.587T5 19V6H4V4h5V3h6v1h5v2h-1v13q0 .825-.587 1.413T17 21zM17 6H7v13h10zM9 17h2V8H9zm4 0h2V8h-2zM7 6v13z" />
                                </svg>
                                Delete
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
                <p class="text-sm text-stone-300">
                    <span>{{ renderedTitles[conversation.id] ?? getConversationTitle(conversation.title) }}</span>
                    <span v-if="typingStates[conversation.id]"
                        class="ml-0.5 inline-block h-4 w-px animate-pulse bg-stone-300 align-middle" />
                </p>
                <!-- <p class="text-sm text-stone-500">{{ conversation.content.slice(0, 100) }}...</p> -->
            </div>
        </div>
        <div v-if="!props.collapsed"
            class="flex items-center justify-between px-4 pt-4 mt-4 text-sm border-t text-stone-400 hover:text-stone-200 shrink-0 border-stone-900">
            <div class="flex items-center gap-3 cursor-pointer">
                <div class="flex items-center justify-center w-8 h-8 border rounded-full border-stone-700 bg-stone-800">
                    TE
                </div>
                <div>
                    <p class="font-bold">DELLAM Hamza</p>
                    <p class="text-xs">Admin</p>
                </div>
            </div>
            <ChatSettingsDialog />
            <!-- <button
                class="w-full px-3 py-2 mt-2 text-sm text-left transition border rounded-md border-stone-800 text-stone-200 hover:border-stone-600 hover:bg-stone-900/60">
                User Profile
            </button> -->
        </div>
        <AlertDialog v-model:open="deleteDialogOpen">
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle class="flex gap-2">
                        <Trash2Icon class="text-red-500" />
                        Delete conversation?
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                        This will permanently delete this chat conversation.
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction @click="confirmDelete">Delete
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>

        <Dialog v-model:open="renameDialogOpen">
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>Rename the conversation</DialogTitle>
                    <DialogDescription>
                        <input v-model="newTitle"
                            class="w-full px-3 py-2 my-5 text-sm border rounded-md outline-none bg-black/30 border-stone-900 text-stone-200 placeholder:text-stone-500 focus:border-stone-800"
                            placeholder="Search history..." type="text" />
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button @click="resetRename" variant="outline">Cancel</Button>
                    <Button @click="renameConversation">Rename</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    </div>
</template>
