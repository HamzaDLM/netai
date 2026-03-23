<script setup lang="ts">
import Main from '../layout/Main.vue'
import router from '@/router';
</script>

<template>
    <Main title="Home">
        <div class="home-shell">
            <div class="home-bg" aria-hidden="true"></div>
            <div class="flex flex-col items-center justify-between h-full mx-10 my-10 font-mono home-content">
                <div class="flex items-center gap-1 text-stone-500">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-6" viewBox="0 0 24 24">
                        <path fill="currentColor"
                            d="M5 22v-4q0-.575.3-1.037t.8-.738L11 13.75V12l-3.475 1.725q-.3.15-.625.225t-.65.075q-.775 0-1.463-.4t-1.062-1.15q-.35-.675-.3-1.437T3.9 9.625L7 5L5 2h6q3.325 0 5.663 2.325T19 10v12zm2-2h10V10q0-2.5-1.75-4.25T11 4H8.75l.65 1l-3.825 5.75q-.125.2-.137.413t.087.412q.125.275.338.363t.412.087q.075 0 .375-.075L13 8.75V15l-6 3zm4-8" />
                    </svg>
                    NetAI
                </div>
                <div class="text-center">
                    <h1 class="text-5xl font-semibold">Your Network AI Assistant...</h1>
                    <p class="mt-3 text-lg text-stone-400">Capable of answering questions about your infra.</p>
                    <button class="px-4 py-3 mt-6 text-lg text-black bg-white rounded-lg"
                        @click="router.push('/chat')">Start chatting!</button>
                </div>
                <div class="text-lg text-white">
                    ...
                </div>
            </div>
        </div>
    </Main>
</template>

<style scoped>
.home-shell {
    position: relative;
    min-height: 100%;
    overflow: hidden;
    border-radius: 24px;
}

.home-content {
    position: relative;
    z-index: 2;
}

.home-bg {
    opacity: 60%;
    position: absolute;
    inset: -10% -10%;
    background:
        radial-gradient(1200px 600px at 20% 10%, rgba(29, 77, 90, 0.16), transparent 60%),
        radial-gradient(900px 500px at 85% 20%, rgba(220, 38, 38, 0.12), transparent 65%),
        radial-gradient(700px 700px at 50% 85%, rgba(185, 28, 28, 0.1), transparent 65%),
        linear-gradient(135deg, rgba(12, 10, 9, 0.96), rgba(28, 25, 23, 0.88) 40%, rgba(18, 16, 14, 0.95));
    filter: saturate(0.9);
}

.home-bg::before,
.home-bg::after {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
}

.home-bg::before {
    background:
        linear-gradient(transparent 95%, rgba(223, 202, 202, 0.12) 96%, transparent 97%) 0 0 / 100% 38px,
        linear-gradient(90deg, transparent 95%, rgba(196, 170, 170, 0.1) 96%, transparent 97%) 0 0 / 38px 100%;
    opacity: 0.4;
    mask-image: radial-gradient(circle at 50% 50%, black 0%, transparent 70%);
}

.home-bg::after {
    background:
        radial-gradient(2px 2px at 15% 30%, rgba(255, 255, 255, 0.166), transparent 70%),
        radial-gradient(2px 2px at 35% 60%, rgba(36, 36, 36, 0.6), transparent 70%),
        radial-gradient(1px 1px at 60% 40%, rgba(255, 255, 255, 0.5), transparent 70%),
        radial-gradient(2px 2px at 80% 70%, rgba(35, 35, 35, 0.5), transparent 70%),
        radial-gradient(1px 1px at 45% 20%, rgb(255, 255, 255), transparent 70%);
    opacity: 0.45;
    mix-blend-mode: screen;
    animation: star-drift 22s linear infinite;
}

@keyframes star-drift {
    0% {
        transform: translate3d(0, 0, 0);
    }

    100% {
        transform: translate3d(-3%, 2%, 0);
    }
}

@media (max-width: 768px) {
    .home-shell {
        border-radius: 16px;
    }

    .home-bg::before {
        opacity: 0.4;
    }
}
</style>
