import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'
import fs from 'node:fs'

import tailwind from 'tailwindcss'
import autoprefixer from 'autoprefixer'

function readUiVersionFromPackageJson(): string {
	try {
		const packageJsonPath = path.resolve(__dirname, 'package.json')
		const raw = fs.readFileSync(packageJsonPath, 'utf-8')
		const parsed = JSON.parse(raw) as { version?: string }
		if (typeof parsed.version === 'string' && parsed.version.trim()) {
			return parsed.version.trim()
		}
	} catch {
		// Fall through to unknown.
	}
	return 'unknown'
}

function nonEmpty(value: string | undefined): string | undefined {
	if (!value) return undefined
	const trimmed = value.trim()
	return trimmed.length > 0 ? trimmed : undefined
}

const uiVersion = nonEmpty(process.env.VITE_UI_VERSION) || readUiVersionFromPackageJson()
const uiGitSha = nonEmpty(process.env.VITE_UI_GIT_SHA) || 'dev'

export default defineConfig({
	define: {
		'import.meta.env.VITE_UI_VERSION': JSON.stringify(uiVersion),
		'import.meta.env.VITE_UI_GIT_SHA': JSON.stringify(uiGitSha),
	},
	css: {
		postcss: {
			plugins: [tailwind(), autoprefixer()],
		},
	},
	plugins: [vue()],
	// : {
	// 	host: '127.0.0.1',
	// 	port: 5173,
	// },
	server: {
		host: '0.0.0.0',
		port: 5173,
	},
	resolve: {
		alias: {
			'@': path.resolve(__dirname, './src'),
		},
	},
})
