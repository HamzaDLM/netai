<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps<{
	title: string
}>()

const isZoomed = ref(false)

function openZoom(): void {
	isZoomed.value = true
}

function closeZoom(): void {
	isZoomed.value = false
}

function onKeydown(event: KeyboardEvent): void {
	if (event.key === 'Escape' && isZoomed.value) closeZoom()
}

onMounted(() => {
	window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
	window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
	<div class="flex flex-col gap-4 py-4">
		<section class="overflow-hidden rounded-md border border-stone-900 bg-stone-950">
			<header class="grid w-full grid-cols-[1.5rem_minmax(0,1fr)_1.5rem] items-center gap-2 border-b border-stone-900 bg-stone-900/40 px-4 py-2 text-sm font-semibold text-stone-300">
				<span aria-hidden="true" />
				<div class="flex min-w-0 items-center justify-center gap-2 text-center">
					<span class="inline-flex h-5 w-5 shrink-0 items-center justify-center text-red-500">
						<slot name="icon" />
					</span>
					<span class="truncate uppercase">{{ title }}</span>
				</div>
				<button type="button" class="inline-flex h-6 w-6 items-center justify-center text-stone-400 transition-colors hover:text-stone-200" :aria-label="`Expand ${title}`" :title="`Expand ${title}`" @click="openZoom">
					<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" viewBox="0 0 24 24" aria-hidden="true">
						<path fill="currentColor" d="M6.4 19H8q.425 0 .713.288T9 20t-.288.713T8 21H4q-.425 0-.712-.288T3 20v-4q0-.425.288-.712T4 15t.713.288T5 16v1.6l2.4-2.4q.275-.275.7-.275t.7.275t.275.7t-.275.7zm11.2 0l-2.4-2.4q-.275-.275-.275-.7t.275-.7t.7-.275t.7.275l2.4 2.4V16q0-.425.288-.712T20 15t.713.288T21 16v4q0 .425-.288.713T20 21h-4q-.425 0-.712-.288T15 20t.288-.712T16 19zM5 6.4V8q0 .425-.288.713T4 9t-.712-.288T3 8V4q0-.425.288-.712T4 3h4q.425 0 .713.288T9 4t-.288.713T8 5H6.4l2.4 2.4q.275.275.275.7t-.275.7t-.7.275t-.7-.275zm14 0l-2.4 2.4q-.275.275-.7.275t-.7-.275t-.275-.7t.275-.7L17.6 5H16q-.425 0-.712-.287T15 4t.288-.712T16 3h4q.425 0 .713.288T21 4v4q0 .425-.288.713T20 9t-.712-.288T19 8z" />
					</svg>
				</button>
			</header>
			<div class="bg-stone-950">
				<slot :zoomed="false" />
			</div>
		</section>

		<Teleport to="body">
			<div v-if="isZoomed" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70" role="dialog" aria-modal="true" :aria-label="title">
				<section class="h-[90vh] w-[90vw] overflow-hidden rounded-lg border border-stone-800 bg-stone-950">
					<header class="grid w-full grid-cols-[1.5rem_minmax(0,1fr)_1.5rem] items-center gap-2 border-b border-stone-800 bg-stone-900/50 px-4 py-2 text-sm font-semibold text-stone-200">
						<span aria-hidden="true" />
						<div class="flex min-w-0 items-center justify-center gap-2 text-center">
							<span class="inline-flex h-5 w-5 shrink-0 items-center justify-center text-red-500">
								<slot name="icon" />
							</span>
							<span class="truncate uppercase">{{ title }}</span>
						</div>
						<button type="button" class="inline-flex h-6 w-6 items-center justify-center text-stone-400 transition-colors hover:text-stone-200" :aria-label="`Close ${title}`" title="Close" @click="closeZoom">
							<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" aria-hidden="true">
								<path fill="currentColor" d="m12 13.4l-4.9 4.9q-.275.275-.7.275t-.7-.275t-.275-.7t.275-.7l4.9-4.9l-4.9-4.9q-.275-.275-.275-.7t.275-.7t.7-.275t.7.275l4.9 4.9l4.9-4.9q.275-.275.7-.275t.7.275t.275.7t-.275.7L13.4 12l4.9 4.9q.275.275.7.275t.7-.275t.275-.7t-.275-.7z" />
							</svg>
						</button>
					</header>
					<div class="h-[calc(90vh-41px)] overflow-auto bg-stone-950">
						<slot :zoomed="true" />
					</div>
				</section>
			</div>
		</Teleport>
	</div>
</template>
