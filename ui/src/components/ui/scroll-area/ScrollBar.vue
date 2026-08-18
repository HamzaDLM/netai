<script setup lang="ts">
import { cn } from '@/lib/utils'
import { ScrollAreaScrollbar, type ScrollAreaScrollbarProps, ScrollAreaThumb } from 'radix-vue'
import { computed, type HTMLAttributes } from 'vue'

const props = withDefaults(defineProps<ScrollAreaScrollbarProps & { class?: HTMLAttributes['class'] }>(), {
  orientation: 'vertical',
})

const delegatedProps = computed(() => {
  const delegated = { ...props }
  delete delegated.class

  return delegated
})
</script>

<template>
  <ScrollAreaScrollbar
    v-bind="delegatedProps"
    :class="
      cn('flex touch-none select-none bg-[var(--scrollbar-track)] transition-colors',
         orientation === 'vertical'
           && 'h-full w-[var(--scrollbar-size)] border-l border-l-transparent p-px',
         orientation === 'horizontal'
           && 'h-[var(--scrollbar-size)] flex-col border-t border-t-transparent p-px',
         props.class)"
  >
    <ScrollAreaThumb class="relative flex-1 rounded-full bg-[var(--scrollbar-thumb)] transition-colors hover:bg-[var(--scrollbar-thumb-hover)]" />
  </ScrollAreaScrollbar>
</template>
