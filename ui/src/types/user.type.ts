export type AdminUserRole = 'user' | 'admin' | 'superuser'

export interface AdminUser {
	id: number
	username: string
	role: AdminUserRole
	created_at: string
	updated_at: string
	last_activity_at?: string | null
	conversation_count: number
	user_message_count: number
}

export interface AdminUserStats {
	registered_users: number
	new_users_last_7_days: number
}

export interface AdminUsersBootstrap {
	users: AdminUser[]
	stats: AdminUserStats
}
