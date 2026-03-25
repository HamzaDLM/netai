// Store for things that don't deserve their own store
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { CodeHighlighterOption } from '@/lib/markdown'

export const useGenericStore = defineStore('generic', () => {
	const codeHighlighter = ref<CodeHighlighterOption>('one-dark-pro') 

	return { codeHighlighter }
})
