<script setup lang="ts">
import ChatSettingsDialog from '@/components/chat/ChatSettingsDialog.vue'
import { formatDatetime } from '@/lib/utils';
import router from '@/router';
import Button from '../ui/button/Button.vue';
import { useChatStore } from '@/stores/chat.store';
import { ref } from 'vue';
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

const chatStore = useChatStore()

const props = defineProps<{
    collapsed?: boolean
}>()

const emit = defineEmits<{
    (event: 'update:historySearchQuery', value: string): void
    (event: 'toggle'): void
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

const historySearchQuery = ref()

const onSearchInput = (event: Event) => {
    const target = event.target as HTMLInputElement | null
    emit('update:historySearchQuery', target?.value ?? '')
}

function resetState() {
    chatStore.resetChatState()
    chatStore.loadConversations()
}
</script>

<template>
    <div class="flex flex-col h-full min-h-0 overflow-hidden transition-all duration-200 border-r border-stone-900/50 bg-stone-950"
        :class="props.collapsed ? 'col-span-1 py-4 w-min' : 'col-span-2 py-5'">
        <div class="px-4 shrink-0" :class="props.collapsed ? 'h-full' : ''">
            <div class="flex items-center justify-between gap-2 text-stone-300"
                :class="props.collapsed ? 'flex-col w-min h-full justify-between' : ''">
                <!-- Logo -->
                <div class="flex flex-col items-center gap-4">
                    <button @click="router.push('/')" class="flex items-center gap-1"
                        :class="props.collapsed ? ' pb-5 border-b border-stone-700' : ''">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-stone-200" viewBox="1 0 24 24">
                            <path fill="currentColor"
                                d="M5 22v-4q0-.575.3-1.037t.8-.738L11 13.75V12l-3.475 1.725q-.3.15-.625.225t-.65.075q-.775 0-1.463-.4t-1.062-1.15q-.35-.675-.3-1.437T3.9 9.625L7 5L5 2h6q3.325 0 5.663 2.325T19 10v12zm2-2h10V10q0-2.5-1.75-4.25T11 4H8.75l.65 1l-3.825 5.75q-.125.2-.137.413t.087.412q.125.275.338.363t.412.087q.075 0 .375-.075L13 8.75V15l-6 3zm4-8" />
                        </svg>
                        <span class="text-xl font-semibold text-stone-200" v-if="!props.collapsed">NetAI</span>
                    </button>
                    <Button v-if="props.collapsed" @click="chatStore.createConversation()" variant="outline"
                        class="flex w-full gap-2 text-stone-300" size="sm">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                            <path fill="currentColor"
                                d="M15.275 12.475L11.525 8.7L14.3 5.95l-.725-.725L8.1 10.7L6.7 9.3l5.45-5.475q.6-.6 1.413-.6t1.412.6l.725.725l1.25-1.25q.3-.3.713-.3t.712.3L20.7 5.625q.3.3.3.713t-.3.712zM6.75 21H3v-3.75l7.1-7.125l3.775 3.75z" />
                        </svg>
                    </Button>
                    <Button v-if="props.collapsed" @click="resetState" variant="outline" class="w-min text-stone-300"
                        size="sm">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                            <path fill="currentColor"
                                d="M5.53 17.506q-.978-1.142-1.504-2.558T3.5 12q0-3.616 2.664-6.058T12.5 3.5V2l3.673 2.75L12.5 7.5V6Q9.86 6 7.93 7.718T6 12q0 1.13.399 2.15t1.13 1.846zM11.5 22l-3.673-2.75L11.5 16.5V18q2.64 0 4.57-1.718T18 12q0-1.13-.399-2.16q-.399-1.028-1.13-1.855l1.998-1.51q.979 1.142 1.505 2.558T20.5 12q0 3.616-2.664 6.058T11.5 20.5z" />
                        </svg>
                    </Button>
                </div>
                <!-- Collapse sidebar -->
                <button
                    class="p-1 transition border rounded-md border-stone-900 text-stone-400 hover:border-stone-600 hover:bg-stone-900/60"
                    @click="emit('toggle')" :aria-label="props.collapsed ? 'Expand sidebar' : 'Collapse sidebar'">
                    <svg v-if="props.collapsed" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                        <path fill="currentColor" d="m9 18l6-6l-6-6l-1.4 1.4L12.2 12l-4.6 4.6z" />
                    </svg>
                    <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                        <path fill="currentColor" d="m15 18l-6-6l6-6l1.4 1.4L11.8 12l4.6 4.6z" />
                    </svg>
                </button>
            </div>
            <!-- Search chat history -->
            <div v-if="!props.collapsed" class="mt-4">
                <input :value="historySearchQuery" @input="onSearchInput"
                    class="w-full px-3 py-2 text-sm border rounded-md outline-none bg-black/30 border-stone-900 text-stone-200 placeholder:text-stone-500 focus:border-stone-800"
                    placeholder="Search history..." type="text" />
            </div>
        </div>
        <div class="flex justify-center gap-2 mx-4 my-4">
            <Button @click="chatStore.createConversation()" variant="outline" class="flex w-full gap-2 text-stone-300"
                size="sm">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                    <path fill="currentColor" d="M11 13H5v-2h6V5h2v6h6v2h-6v6h-2z" />
                </svg>
                Chat
            </Button>
            <!-- <Button @click="resetState" variant="outline" class="w-min text-stone-300" size="sm">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24">
                    <path fill="currentColor"
                        d="M5.53 17.506q-.978-1.142-1.504-2.558T3.5 12q0-3.616 2.664-6.058T12.5 3.5V2l3.673 2.75L12.5 7.5V6Q9.86 6 7.93 7.718T6 12q0 1.13.399 2.15t1.13 1.846zM11.5 22l-3.673-2.75L11.5 16.5V18q2.64 0 4.57-1.718T18 12q0-1.13-.399-2.16q-.399-1.028-1.13-1.855l1.998-1.51q.979 1.142 1.505 2.558T20.5 12q0 3.616-2.664 6.058T11.5 20.5z" />
                </svg>
            </Button> -->
        </div>
        <div v-if="!props.collapsed" class="flex-1 min-h-0 pr-1 space-y-2 overflow-y-auto text-sm">
            <div v-for="conversation in chatStore.conversations" @click="chatStore.selectConversation(conversation.id)"
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
                    {{ conversation.title === '' ? 'Unnamed' : conversation.title }}
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
