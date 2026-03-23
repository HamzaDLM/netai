import { defineStore } from 'pinia'
import { Role, UserProfile } from '../services/auth.service'

export const useUserStore = defineStore('user', {
	state: () => ({
		profile: {
			username: '',
			email: 'test@test.com',
			role: Role.User,
			exp: 1,
		} as UserProfile,
	}),
	persist: {
		key: 'user',
		storage: localStorage,
	},
})

export const useStore = defineStore('main', {
	state: () => {
		return {
			someState: 'hello pinia',
		}
	},
	persist: true,
})
