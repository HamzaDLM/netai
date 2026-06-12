<script setup lang="ts">
import { Search } from 'lucide-vue-next'

const model = defineModel<string>({ default: '' })

defineProps<{
	placeholder: string
	maxWidthClass?: string
}>()
</script>

<template>
	<label class="relative block w-full" :class="maxWidthClass">
		<span class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-stone-500">
			<Search class="w-4 h-4" />
		</span>
		<input
			v-model="model"
			type="text"
			:placeholder="placeholder"
			class="h-11 w-full bg-transparent border-b border-zinc-800 pl-10 pr-4 text-sm text-stone-200 outline-none transition placeholder:text-stone-500 focus:border-white/16 focus:bg-white/[0.020]" />
	</label>
</template>
