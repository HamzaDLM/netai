<script setup lang="ts">
</script>

<template>
    <div class="relative flex flex-col w-screen h-screen overflow-hidden">
        <slot></slot>
        <div class="absolute bottom-0 z-20 w-full h-2 from-transparent via-transparent to-red-700 bg-gradient-to-r"></div>
    </div>
</template>
