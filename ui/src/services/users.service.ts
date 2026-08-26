import type { AxiosResponse } from 'axios'
import API from './axios'
import type { AdminUsersBootstrap } from '@/types/user.type'

class UsersService {
	getAdminBootstrap(): Promise<AxiosResponse<AdminUsersBootstrap>> {
		return API.get('/users/admin/bootstrap')
	}
}

export default new UsersService()
