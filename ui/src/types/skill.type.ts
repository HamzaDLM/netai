export interface Skill {
	id: number
	user_id: number
	name: string
	description: string
	instructions: string
	enabled: boolean
	archived: boolean
	created_at: string
	updated_at: string
}

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

export interface SkillsBootstrap {
	skills: Skill[]
	catalog: ToolCatalogAgent[]
}
