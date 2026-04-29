<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import router from '@/router'

let redirectTimer: number | null = null

onMounted(() => {
    redirectTimer = window.setTimeout(() => {
        router.replace('/chat')
    }, 1400)
})

onBeforeUnmount(() => {
    if (redirectTimer !== null) {
        window.clearTimeout(redirectTimer)
    }
})
</script>

<template>
	<section class="flex items-center justify-center w-full h-full bg-['#09090b'] splash-screen">
        <h1 class="splash-title">NetAI</h1>
    </section>
</template>

<style scoped>
.splash-title {
    margin: 0;
    color: #fff;
    font-size: clamp(3.5rem, 12vw, 8rem);
    font-weight: 800;
    letter-spacing: 0.08em;
    animation: splash-flash 1.4s ease-in-out forwards;
}

@keyframes splash-flash {
    0% {
        opacity: 0;
        transform: scale(0.96);
    }

    10% {
        opacity: 1;
    }

    55% {
        opacity: 0.92;
    }

    100% {
        opacity: 0;
        transform: scale(1.04);
    }
}
</style>
