import { createApp } from 'vue'
import './assets/index.css'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import { Icon } from '@iconify/vue'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import { initHighlighter } from '@/lib/markdown'

async function bootstrap(): Promise<void> {
	await initHighlighter()

	const app = createApp(App)
	const pinia = createPinia()
	pinia.use(piniaPluginPersistedstate)

	app.config.globalProperties.$capitalize = (str: string) => {
		return str.charAt(0).toUpperCase() + str.slice(1)
	}

	app.component('Icon', Icon)
	app.use(router)
	app.use(pinia)
	app.mount('#app')
}

bootstrap()
