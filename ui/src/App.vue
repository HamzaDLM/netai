<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import Toaster from '@/components/ui/toast/Toaster.vue'

const mode = import.meta.env.MODE
const intro = ref(false)
const dots = ref('')
let interval: number | null = null

function createDots() {
    dots.value = dots.value.length < 3 ? `${dots.value}.` : ''
}

onMounted(() => {
    interval = window.setInterval(createDots, 500)
    window.setTimeout(() => {
        intro.value = false
    }, 2000)
})

onBeforeUnmount(() => {
    if (interval !== null) {
        window.clearInterval(interval)
    }
})
</script>

<template>
    <div v-if="intro && mode !== 'development'"
        class="flex items-center justify-center h-screen text-white bg-zinc-900">
        <div class="text-center">
            <h1 class="flex items-center gap-6 text-4xl font-bold text-sky-300">
                <svg xmlns="http://www.w3.org/2000/svg" width="1.4em" height="1.4em" viewBox="0 0 256 256">
                    <path fill="currentColor"
                        d="M236.4 70.65L130.2 40.31a8 8 0 0 0-3.33-.23L21.74 55.1A16.08 16.08 0 0 0 8 70.94v114.12a16.08 16.08 0 0 0 13.74 15.84l105.13 15a8.5 8.5 0 0 0 1.13.1a8 8 0 0 0 2.2-.31l106.2-30.34A16.07 16.07 0 0 0 248 170V86a16.07 16.07 0 0 0-11.6-15.35M64 120H48a8 8 0 0 0 0 16h16v54.78l-40-5.72V70.94l40-5.72Zm56 78.78l-40-5.72V136h16a8 8 0 0 0 0-16H80V62.94l40-5.72Z" />
                </svg>
                NetAI
            </h1>
            <p class="mt-4 text-lg">You will be redirected in a moment{{ dots }}</p>
        </div>
    </div>

    <main v-else class="w-screen h-screen bg-stone-950/50">
        <router-view v-slot="{ Component }">
            <transition mode="out-in" appear enter-active-class="transform-gpu transition-all duration-500 ease-out motion-reduce:transition-none" enter-from-class="translate-y-4 opacity-0 blur-sm" enter-to-class="translate-y-0 opacity-100 blur-0" leave-active-class="transform-gpu transition-all duration-300 ease-in motion-reduce:transition-none" leave-from-class="translate-y-0 opacity-100 blur-0" leave-to-class="-translate-y-2 opacity-0 blur-sm">
                <component :is="Component" :key="$route.fullPath" />
            </transition>
        </router-view>
    </main>
    <Toaster />
</template>
