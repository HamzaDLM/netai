// Store for things that don't deserve their own store
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { CodeHighlighterOption } from '@/lib/markdown'
import { fetchBackendVersion } from '@/services/version.service'

const VERSION_CACHE_TTL_MS = 5 * 60 * 1000

export const useGenericStore = defineStore('generic', () => {
	const codeHighlighter = ref<CodeHighlighterOption>('one-dark-pro') 
	const uiVersion = ref(import.meta.env.VITE_UI_VERSION || 'unknown')
	const uiGitSha = ref(import.meta.env.VITE_UI_GIT_SHA || 'dev')
	const backendVersion = ref('unknown')
	const backendGitSha = ref('dev')
	const backendVersionStatus = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
	const backendVersionLastFetchedAt = ref<number | null>(null)
	let versionRequestPromise: Promise<void> | null = null

	async function ensureBackendVersion(force = false): Promise<void> {
		const now = Date.now()
		const hasFreshCache =
			backendVersionLastFetchedAt.value != null &&
			now - backendVersionLastFetchedAt.value < VERSION_CACHE_TTL_MS

		if (!force && hasFreshCache && backendVersionStatus.value === 'ready') {
			return
		}

		if (versionRequestPromise) {
			await versionRequestPromise
			return
		}

		backendVersionStatus.value = 'loading'
		versionRequestPromise = (async () => {
			try {
				const data = await fetchBackendVersion()
				backendVersion.value = data.backend_version || 'unknown'
				backendGitSha.value = data.backend_git_sha || 'dev'
				backendVersionStatus.value = 'ready'
				backendVersionLastFetchedAt.value = Date.now()
			} catch {
				backendVersion.value = 'unreachable'
				backendGitSha.value = 'n/a'
				backendVersionStatus.value = 'error'
				backendVersionLastFetchedAt.value = Date.now()
			} finally {
				versionRequestPromise = null
			}
		})()

		await versionRequestPromise
	}

	return {
		codeHighlighter,
		uiVersion,
		uiGitSha,
		backendVersion,
		backendGitSha,
		backendVersionStatus,
		backendVersionLastFetchedAt,
		ensureBackendVersion,
	}
})
