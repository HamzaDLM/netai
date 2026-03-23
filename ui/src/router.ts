import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/pages/Home.vue'
// import { isAuthed } from './services/utils.service'
// import { a } from 'shiki/dist/langs-bundle-full-C-zczmvu.mjs'
import Chat from './views/pages/Chat.vue'

export const routes = [
	{
		name: 'Home',
		path: '/',
		component: Home,
		meta: {
			requiresAuth: true,
			inSidebar: true,
			icon: 'solar:home-smile-bold',
		},
	},
	{
		name: 'Chat',
		path: '/chat',
		component: Chat,
		meta: {
			requiresAuth: true,
			inSidebar: true,
			icon: 'solar:home-smile-bold',
		},
	},
	{
		name: 'Cooking',
		path: '/cooking',
		component: () => import('./views/pages/Cooking.vue'),
		meta: { redirectIfAuthed: true },
	},
	{
		name: 'Login',
		path: '/login',
		component: () => import('./views/pages/Login.vue'),
		meta: { redirectIfAuthed: true },
	},
	{
		name: 'Signup',
		path: '/signup',
		component: () => import('./views/pages/Signup.vue'),
		meta: { redirectIfAuthed: true },
	},
	{
		path: '/:pathMatch(.*)*',
		name: 'not-found',
		component: () => import('./views/pages/NotFound.vue'),
		meta: {},
	},
	{
		path: '/:pathMatch(.*)',
		name: 'bad-not-found',
		component: () => import('./views/pages/NotFound.vue'),
		meta: {},
	},
]

const router = createRouter({
	history: createWebHistory(),
	routes: routes,
})

// TODO: to.meta.redirectIfAuthed logic
router.beforeEach(async (to, _, next) => {
	if (to.meta.requiresAuth) {
		// const authed = await isAuthed()
		// if (!authed) {
		// 	next('/login')
		// }
	}
	next()
})

export default router
