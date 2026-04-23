import { AxiosResponse } from 'axios'
import API from './axios'
import type { Skill, SkillCreatePayload, SkillsBootstrap, SkillUpdatePayload, ToolCatalogAgent } from '@/types/skill.type'

class SkillsService {
	getSkills(): Promise<AxiosResponse<Skill[]>> {
		return API.get('/skills')
	}

	getToolCatalog(): Promise<AxiosResponse<ToolCatalogAgent[]>> {
		return API.get('/skills/catalog')
	}

	getBootstrap(): Promise<AxiosResponse<SkillsBootstrap>> {
		return API.get('/skills/bootstrap')
	}

	createSkill(payload: SkillCreatePayload): Promise<AxiosResponse<Skill>> {
		return API.post('/skills', payload)
	}

	updateSkill(skillId: number, payload: SkillUpdatePayload): Promise<AxiosResponse<Skill>> {
		return API.patch(`/skills/${skillId}`, payload)
	}

	toggleSkill(skillId: number, enabled: boolean): Promise<AxiosResponse<Skill>> {
		return API.patch(`/skills/${skillId}/enabled`, { enabled })
	}

	deleteSkill(skillId: number): Promise<AxiosResponse<void>> {
		return API.delete(`/skills/${skillId}`)
	}
}

export default new SkillsService()
