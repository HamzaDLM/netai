<script setup lang="ts">
import Toaster from '@/components/ui/toast/Toaster.vue'

</script>

<template>
    <main class="w-screen h-screen bg-stone-950/50">
        <router-view v-slot="{ Component }">
            <transition mode="out-in" appear enter-active-class="transform-gpu transition-all duration-500 ease-out motion-reduce:transition-none" enter-from-class="translate-y-4 opacity-0 blur-sm" enter-to-class="translate-y-0 opacity-100 blur-0" leave-active-class="transform-gpu transition-all duration-300 ease-in motion-reduce:transition-none" leave-from-class="translate-y-0 opacity-100 blur-0" leave-to-class="-translate-y-2 opacity-0 blur-sm">
                <component :is="Component" :key="$route.fullPath" />
            </transition>
        </router-view>
    </main>
    <Toaster />
</template>
