<script setup lang="ts">
</script>

<template>
    <div class="flex flex-col w-screen h-screen overflow-hidden">
        <slot></slot>
    </div>
    <div class="absolute bottom-0 z-20 w-full h-2 to-red-500 from-black bg-gradient-to-r"></div>
</template>
