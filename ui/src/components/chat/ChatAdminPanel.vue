<script setup lang="ts">
import { onMounted, ref } from 'vue'
import ChatAdminFeedbacksTab from '@/components/chat/admin/ChatAdminFeedbacksTab.vue'
import ChatAdminOverviewTab from '@/components/chat/admin/ChatAdminOverviewTab.vue'
import ChatAdminPlaceholderTab from '@/components/chat/admin/ChatAdminPlaceholderTab.vue'
import ChatAdminSidebar from '@/components/chat/admin/ChatAdminSidebar.vue'
import { toast } from '@/components/ui/toast'
import chatService from '@/services/chat.service'
import type { AdminFeedbackItem } from '@/types/chat.type'
import type { AdminSection } from '@/components/chat/admin/types'

const activeSection = ref<AdminSection>('overview')
const feedbackItems = ref<AdminFeedbackItem[]>([])
const selectedFeedbackId = ref<number | null>(null)
const isLoading = ref(false)

async function loadFeedbacks() {
	isLoading.value = true
	try {
		const response = await chatService.getAdminFeedbacks()
		feedbackItems.value = response.data
		selectedFeedbackId.value = response.data[0]?.feedback.id ?? null
	} catch {
		toast({ title: 'Unable to load feedbacks', variant: 'destructive' })
	} finally {
		isLoading.value = false
	}
}

onMounted(async () => {
	await loadFeedbacks()
})
</script>

<template>
	<div class="flex h-full min-h-0 bg-stone-950 text-stone-200">
		<ChatAdminSidebar :active-section="activeSection" @select="activeSection = $event" />
		<ChatAdminOverviewTab v-if="activeSection === 'overview'" />
		<ChatAdminPlaceholderTab
			v-else-if="activeSection === 'connectors'"
			title="Connectors"
			description="Connector health, configuration, and integration summaries will live here."
			coming-soon-label="Connector admin is not wired yet"
			empty-state-copy="This section is reserved for connector-level admin views once those workflows are designed for the new tab system." />
		<ChatAdminPlaceholderTab
			v-else-if="activeSection === 'skills'"
			title="Skills"
			description="Skill inventory, review, and publishing summaries will live here."
			coming-soon-label="Skill admin is not wired yet"
			empty-state-copy="This section is reserved for skill-level admin views once those workflows are redesigned for this panel." />
		<ChatAdminPlaceholderTab
			v-else-if="activeSection === 'users'"
			title="Users"
			description="User-facing activity, account state, and adoption summaries will live here."
			coming-soon-label="User admin is not wired yet"
			empty-state-copy="This section is reserved for user management and engagement views once the backend surfaces the required data." />
		<ChatAdminPlaceholderTab
			v-else-if="activeSection === 'latency'"
			title="Latency"
			description="Model, tool, and orchestration timing views will live here."
			coming-soon-label="Latency dashboards coming next"
			empty-state-copy="This section is reserved for response-time breakdowns and performance trends once those metrics are exposed to the UI." />
		<ChatAdminFeedbacksTab
			v-else
			:feedback-items="feedbackItems"
			:selected-feedback-id="selectedFeedbackId"
			:is-loading="isLoading"
			@refresh="loadFeedbacks"
			@select-feedback="selectedFeedbackId = $event" />
	</div>
</template>
