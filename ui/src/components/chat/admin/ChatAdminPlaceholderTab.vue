<script setup lang="ts">
defineProps<{
	title: string
	description: string
	comingSoonLabel: string
	emptyStateCopy: string
}>()
</script>

<template>
	<section class="flex min-w-0 flex-1 flex-col">
		<div class="border-b border-stone-900 px-6 py-4">
			<p class="text-xl font-semibold text-stone-100">{{ title }}</p>
			<p class="mt-1 text-sm text-stone-500">{{ description }}</p>
		</div>

		<div class="flex min-h-0 flex-1 items-center justify-center p-8">
			<div class="w-full max-w-2xl rounded-2xl border border-dashed border-stone-800 bg-black/20 p-10 text-center">
				<p class="text-sm font-semibold uppercase tracking-[0.2em] text-stone-500">Empty State</p>
				<p class="mt-4 text-2xl font-semibold text-stone-100">{{ comingSoonLabel }}</p>
				<p class="mt-3 text-sm leading-6 text-stone-400">{{ emptyStateCopy }}</p>
			</div>
		</div>
	</section>
</template>
