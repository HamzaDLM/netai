export interface Skill {
	id: number
	user_id: number
	name: string
	slug: string
	description: string
	instructions: string
	enabled: boolean
	archived: boolean
	installed_from_listing_id: number | null
	marketplace_listing_id: number | null
	marketplace_status: SkillMarketplaceStatus | null
	marketplace_review_notes: string
	created_at: string
	updated_at: string
}

export type SkillMarketplaceStatus = 'pending' | 'approved' | 'rejected'

export type ViewerRole = 'user' | 'admin' | 'superuser'

export interface SkillCreatePayload {
	name: string
	description: string
	instructions: string
	enabled?: boolean
}

export interface SkillUpdatePayload {
	name?: string
	description?: string
	instructions?: string
	enabled?: boolean
}

export interface ToolCatalogTool {
	python_name: string
	runtime_name?: string | null
	summary: string
}

export interface ToolCatalogAgent {
	agent_key: string
	agent_name: string
	specialist_tool?: string | null
	tools: ToolCatalogTool[]
}

export interface SkillMarketplaceListing {
	id: number
	owner_user_id: number
	owner_skill_id: number
	name: string
	slug: string
	description: string
	instructions: string
	status: SkillMarketplaceStatus
	review_notes: string
	reviewed_by_user_id: number | null
	archived: boolean
	created_at: string
	updated_at: string
}

export interface SkillsBootstrap {
	viewer_role: ViewerRole
	skills: Skill[]
	catalog: ToolCatalogAgent[]
	marketplace: SkillMarketplaceListing[]
	review_queue: SkillMarketplaceListing[]
}
