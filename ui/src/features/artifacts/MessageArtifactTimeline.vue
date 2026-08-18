<script setup lang="ts">
import { computed } from 'vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import type { Message } from '@/types/chat.type'
import ArtifactHost from './ArtifactHost.vue'
import { buildArtifactTimeline } from './artifact.timeline'

const props = defineProps<{
	message: Message
}>()

const blocks = computed(() => buildArtifactTimeline(props.message))
</script>

<template>
	<div class="flex min-w-0 flex-col gap-4">
		<template v-for="block in blocks" :key="block.id">
			<MarkdownRenderer v-if="block.type === 'markdown' && block.content" class="min-w-0" :content="block.content" />
			<ArtifactHost v-else-if="block.type === 'artifact'" :artifact="block.artifact" />
		</template>
	</div>
</template>
