<script setup>
const props = defineProps({
    modelValue: Boolean
})

const emit = defineEmits(['update:modelValue'])

const closeModal = () => {
    emit('update:modelValue', false)
}
</script>

<template>
    <Teleport to="body">
        <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0"
            enter-to-class="opacity-100" leave-active-class="transition duration-150 ease-in"
            leave-from-class="opacity-100" leave-to-class="opacity-0">
            <div v-if="modelValue" class="fixed inset-0 z-50 overflow-y-auto" aria-labelledby="modal-title"
                role="dialog" aria-modal="true">
                <div class="flex items-end justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
                    <div class="fixed inset-0 transition-opacity bg-opacity-50 bg-gray-900/30 backdrop-blur-sm"
                        aria-hidden="true" @click="closeModal"></div>
                    <span class="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
                    <div class="inline-block overflow-hidden text-left align-bottom transition-all transform rounded-lg shadow-xl bg-zinc-900 sm:my-8 sm:align-middle sm:max-w-lg sm:w-full"
                        @click.stop>
                        <div class="px-4 pt-5 pb-4 bg-zinc-900 sm:p-6 sm:pb-4">
                            <slot></slot>
                        </div>

                    </div>
                </div>
            </div>
        </Transition>
    </Teleport>
</template>