<script setup lang="ts">
import { onMounted, ref } from 'vue'
import ChatAdminFeedbacksTab from '@/components/chat/admin/ChatAdminFeedbacksTab.vue'
import ChatAdminOverviewTab from '@/components/chat/admin/ChatAdminOverviewTab.vue'
import ChatAdminPlaceholderTab from '@/components/chat/admin/ChatAdminPlaceholderTab.vue'
import ChatAdminSidebar from '@/components/chat/admin/ChatAdminSidebar.vue'
import ChatAdminSkillsTab from '@/components/chat/admin/ChatAdminSkillsTab.vue'
import ChatAdminUsersTab from '@/components/chat/admin/ChatAdminUsersTab.vue'
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
		<ChatAdminSkillsTab v-else-if="activeSection === 'skills'" />
		<ChatAdminUsersTab v-else-if="activeSection === 'users'" />
		<ChatAdminPlaceholderTab
			v-else-if="activeSection === 'latency'"
			title="Latency"
			description="Model, tool, and orchestration timing views will live here."
			coming-soon-label="Latency dashboards coming next"
			empty-state-copy="This section is reserved for response-time breakdowns and performance trends once those metrics are exposed to the UI." />
		<ChatAdminPlaceholderTab
			v-else-if="activeSection === 'evals'"
			title="Evals"
			description="Model evaluation workflows will live here."
			coming-soon-label="Evaluation tooling is not wired yet"
			empty-state-copy="This section is reserved for admin workflows that run question, context, and expected-answer sets against the multi-agent setup." />
		<ChatAdminPlaceholderTab
			v-else-if="activeSection === 'documents'"
			title="Documents"
			description="RAG document management workflows will live here."
			coming-soon-label="Document ingestion is not wired yet"
			empty-state-copy="This section is reserved for admin workflows that add baseline documents, network configs, runbooks, and other reference material for retrieval-augmented answers." />
		<ChatAdminFeedbacksTab
			v-else
			:feedback-items="feedbackItems"
			:selected-feedback-id="selectedFeedbackId"
			:is-loading="isLoading"
			@refresh="loadFeedbacks"
			@select-feedback="selectedFeedbackId = $event" />
	</div>
</template>
