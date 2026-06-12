<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{
	title: string
	value: string
	helper?: string
	icon: Component
	extraLines?: string[]
	valueClass?: string
}>()
</script>

<template>
	<article class="rounded-lg border border-white/7 bg-white/[0.005] p-5 shadow-[0_18px_60px_rgba(0,0,0,0.28)] backdrop-blur-sm">
		<div class="flex items-start justify-between gap-5">
			<div class="min-w-0">
				<div class="flex items-center gap-2 text-stone-500">
					<component :is="icon" class="w-4 h-4" />
					<p class="text-[11px] font-semibold uppercase tracking-[0.24em]">{{ title }}</p>
				</div>
				<p class="mt-2 text-[2rem] font-semibold tracking-[-0.05em] text-stone-100" :class="valueClass">
					{{ value }}
				</p>
				<p v-if="helper" class="mt-2 text-sm break-words text-stone-500">{{ helper }}</p>
				<div v-if="extraLines && extraLines.length > 0" class="mt-4 space-y-1.5">
					<p v-for="line in extraLines" :key="line" class="text-sm font-medium text-stone-300">
						{{ line }}
					</p>
				</div>
			</div>
			<div class="mt-0.5 h-px flex-1 bg-gradient-to-r from-white/10 to-transparent" />
		</div>
	</article>
</template>
