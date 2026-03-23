import { AxiosResponse } from 'axios'
import API from './axios'

export enum Role {
	Guest,
	Admin,
	User,
}

interface Token {
	token: string
}

interface UserIn {
	username: string
	email: string
	password: string
	role?: Role
}

export interface UserProfile {
	email: string
	username: string
	role: Role
	exp: number
}

class AuthService {
	login(params: { email: string; password: string }): Promise<AxiosResponse<Token>> {
		return API.post('/login', params)
	}
	registerUser(params: UserIn): Promise<AxiosResponse<{ id: number }>> {
		return API.post('/users', params)
	}
	profile(): Promise<AxiosResponse<UserProfile>> {
		return API.get('/profile')
	}
	logout(): Promise<AxiosResponse<{ message: string }>> {
		return API.post('/logout')
	}
}

export default new AuthService()
