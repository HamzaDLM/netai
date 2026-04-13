/// <reference types="vite/client" />
import { ComponentCustomProperties } from 'vue'

interface ImportMetaEnv {
	readonly VITE_BASE_URL: string
	readonly VITE_UI_VERSION?: string
	readonly VITE_UI_GIT_SHA?: string
}

interface ImportMeta {
	readonly env: ImportMetaEnv
}

declare module '@vue/runtime-core' {
	interface ComponentCustomProperties {
		$capitalize: (str: string) => string
	}
}
