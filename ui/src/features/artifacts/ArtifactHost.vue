<script setup lang="ts">
import { computed } from 'vue'
import type { ArtifactEnvelope } from './artifact.types'
import { resolveArtifactRenderer } from './artifact.registry'

const props = defineProps<{
	artifact: ArtifactEnvelope
}>()

const renderer = computed(() => resolveArtifactRenderer(props.artifact.kind))
</script>

<template>
	<component :is="renderer" :artifact="artifact" />
</template>
