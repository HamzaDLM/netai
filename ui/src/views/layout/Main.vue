<script setup lang="ts">
</script>

<template>
    <div class="flex flex-col w-screen h-screen overflow-hidden">
        <slot></slot>
    </div>
    <div class="absolute bottom-0 z-20 w-full h-2 from-black via-stone-950 to-red-700 bg-gradient-to-r"></div>
</template>
