<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import PixelMatrixSplash from '@/components/splash/PixelMatrixSplash.vue'
import router from '@/router'

const SPLASH_DURATION_MS = 2000
let redirectTimer: number | null = null

onMounted(() => {
	redirectTimer = window.setTimeout(() => {
		router.replace('/chat')
	}, SPLASH_DURATION_MS)
})

onBeforeUnmount(() => {
	if (redirectTimer !== null) {
		window.clearTimeout(redirectTimer)
	}
})
</script>

<template>
	<main class="min-h-[100dvh] w-full overflow-hidden bg-[#070707]">
		<PixelMatrixSplash />
	</main>
</template>
