import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { toast } from '@/components/ui/toast'
import skillsService from '@/services/skills.service'
import type { Skill, SkillCreatePayload, SkillMarketplaceListing, SkillsBootstrap, SkillUpdatePayload, ViewerRole } from '@/types/skill.type'

export const useSkillsStore = defineStore('skills', () => {
	const skills = ref<Skill[]>([])
	const marketplace = ref<SkillMarketplaceListing[]>([])
	const reviewQueue = ref<SkillMarketplaceListing[]>([])
	const viewerRole = ref<ViewerRole>('user')
	const isLoading = ref(false)
	const isBusy = ref(false)
	const hasLoaded = ref(false)

	const availableSkills = computed(() => skills.value.filter(skill => !skill.archived && skill.enabled))
	const isAdmin = computed(() => viewerRole.value === 'admin' || viewerRole.value === 'superuser')

	function applyBootstrap(payload: SkillsBootstrap) {
		skills.value = payload.skills
		marketplace.value = payload.marketplace
		reviewQueue.value = payload.review_queue
		viewerRole.value = payload.viewer_role
		hasLoaded.value = true
	}

	async function loadBootstrap(force = false) {
		if (hasLoaded.value && !force) return
		isLoading.value = true
		try {
			const response = await skillsService.getBootstrap()
			applyBootstrap(response.data)
		} catch {
			toast({ title: 'Unable to load skills data', variant: 'destructive' })
		} finally {
			isLoading.value = false
		}
	}

	async function createSkill(payload: SkillCreatePayload): Promise<Skill | null> {
		isBusy.value = true
		try {
			const response = await skillsService.createSkill(payload)
			skills.value.unshift(response.data)
			return response.data
		} catch (error: any) {
			const detail = String(error?.response?.data?.detail ?? '')
			if (detail === 'skill_name_already_exists') {
				toast({ title: 'A skill with this name already exists', variant: 'destructive' })
				return null
			}
			toast({ title: 'Unable to create skill', variant: 'destructive' })
			return null
		} finally {
			isBusy.value = false
		}
	}

	async function updateSkill(skillId: number, payload: SkillUpdatePayload): Promise<Skill | null> {
		isBusy.value = true
		try {
			const response = await skillsService.updateSkill(skillId, payload)
			const idx = skills.value.findIndex(item => item.id === skillId)
			if (idx !== -1) skills.value[idx] = response.data
			await loadBootstrap(true)
			return response.data
		} catch (error: any) {
			const detail = String(error?.response?.data?.detail ?? '')
			if (detail === 'skill_name_already_exists') {
				toast({ title: 'A skill with this name already exists', variant: 'destructive' })
				return null
			}
			toast({ title: 'Unable to update skill', variant: 'destructive' })
			return null
		} finally {
			isBusy.value = false
		}
	}

	async function deleteSkill(skillId: number): Promise<boolean> {
		isBusy.value = true
		try {
			await skillsService.deleteSkill(skillId)
			skills.value = skills.value.filter(skill => skill.id !== skillId)
			marketplace.value = marketplace.value.filter(listing => listing.owner_skill_id !== skillId)
			reviewQueue.value = reviewQueue.value.filter(listing => listing.owner_skill_id !== skillId)
			return true
		} catch {
			toast({ title: 'Unable to delete skill', variant: 'destructive' })
			return false
		} finally {
			isBusy.value = false
		}
	}

	async function requestShare(skillId: number): Promise<Skill | null> {
		isBusy.value = true
		try {
			const response = await skillsService.requestShare(skillId)
			const idx = skills.value.findIndex(item => item.id === skillId)
			if (idx !== -1) skills.value[idx] = response.data
			await loadBootstrap(true)
			return response.data
		} catch {
			toast({ title: 'Unable to submit skill for marketplace review', variant: 'destructive' })
			return null
		} finally {
			isBusy.value = false
		}
	}

	async function installMarketplaceSkill(listingId: number): Promise<Skill | null> {
		isBusy.value = true
		try {
			const response = await skillsService.installMarketplaceSkill(listingId)
			skills.value.unshift(response.data)
			return response.data
		} catch {
			toast({ title: 'Unable to add skill from marketplace', variant: 'destructive' })
			return null
		} finally {
			isBusy.value = false
		}
	}

	async function approveMarketplaceSkill(listingId: number): Promise<boolean> {
		isBusy.value = true
		try {
			await skillsService.approveMarketplaceSkill(listingId)
			await loadBootstrap(true)
			return true
		} catch {
			toast({ title: 'Unable to approve marketplace skill', variant: 'destructive' })
			return false
		} finally {
			isBusy.value = false
		}
	}

	async function rejectMarketplaceSkill(listingId: number): Promise<boolean> {
		isBusy.value = true
		try {
			await skillsService.rejectMarketplaceSkill(listingId)
			await loadBootstrap(true)
			return true
		} catch {
			toast({ title: 'Unable to reject marketplace skill', variant: 'destructive' })
			return false
		} finally {
			isBusy.value = false
		}
	}

	return {
		skills,
		marketplace,
		reviewQueue,
		viewerRole,
		isLoading,
		isBusy,
		hasLoaded,
		availableSkills,
		isAdmin,
		loadBootstrap,
		createSkill,
		updateSkill,
		deleteSkill,
		requestShare,
		installMarketplaceSkill,
		approveMarketplaceSkill,
		rejectMarketplaceSkill,
	}
})
