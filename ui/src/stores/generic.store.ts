// Store for things that don't deserve their own store
import { defineStore } from 'pinia'

// themes can be found in https://shiki.style/themes
export const CODE_HIGHLIGHTER_OPTIONS = ['kanagawa-dragon', 'nord', 'one-dark-pro'] as const
export type CodeHighlighterOption = (typeof CODE_HIGHLIGHTER_OPTIONS)[number]

export const useGenericStore = defineStore('generic', {
	state: () => ({
		codeHighlighter: 'one-dark-pro' as CodeHighlighterOption,
	}),
	getters: {},
	actions: {},
	persist: true,
})
