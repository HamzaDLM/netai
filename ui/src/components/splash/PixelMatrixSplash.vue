<script setup lang="ts">
const glyphs: Record<string, string[]> = {
	N: ['10001', '11001', '11001', '10101', '10011', '10011', '10001'],
	E: ['11111', '10000', '10000', '11110', '10000', '10000', '11111'],
	T: ['11111', '00100', '00100', '00100', '00100', '00100', '00100'],
	A: ['01110', '10001', '10001', '11111', '10001', '10001', '10001'],
	I: ['11111', '00100', '00100', '00100', '00100', '00100', '11111'],
}

const letters = 'NETAI'.split('')
const pixelScale = 2
const logicalColumns = letters.length * 5 + letters.length - 1
const logicalPixels = Array.from({ length: 7 }, (_, row) =>
	letters.flatMap((letter, letterIndex) => [...(glyphs[letter]?.[row] ?? '00000').split('').map(value => value === '1'), ...(letterIndex < letters.length - 1 ? [false] : [])])
)
const columns = logicalColumns * pixelScale
const pixels = logicalPixels.flatMap(row =>
	Array.from({ length: pixelScale }, () => row.flatMap(active => Array.from({ length: pixelScale }, () => active)))
)

function pixelAnimation(row: number, column: number, active: boolean) {
	if (!active) {
		return {
			animationDelay: `${0.35 + ((row * 5 + column * 3) % 11) * 0.035}s`,
		}
	}
	const disorder = ((row * 11 + column * 7) % 9) * 0.03
	return {
		animationDelay: `${column * (0.025 / pixelScale) + disorder}s`,
		animationDuration: `${0.82 + ((row * 3 + column) % 5) * 0.04}s`,
	}
}
</script>

<template>
	<div class="pixel-concept relative grid min-h-[100dvh] w-full content-center place-items-center gap-[clamp(1.35rem,3vw,2.2rem)] overflow-hidden bg-[#070707]">
		<div class="ambient-grid absolute inset-0 opacity-0 motion-reduce:animate-none motion-reduce:opacity-100" aria-hidden="true" />
		<div class="relative z-10 grid w-[min(44vw,29rem)] gap-[clamp(0.5px,0.15vw,2px)]" :style="{ gridTemplateColumns: `repeat(${columns}, 1fr)` }" role="img" aria-label="NetAI">
			<template v-for="(row, rowIndex) in pixels" :key="rowIndex">
				<span
					v-for="(active, columnIndex) in row"
					:key="`${rowIndex}-${columnIndex}`"
					class="pixel aspect-square rounded-[1px] bg-[#121212] opacity-0 shadow-[inset_0_0_0_1px_rgb(255_255_255_/_1.5%)] motion-reduce:animate-none motion-reduce:opacity-100"
					:class="{ active }"
					:style="pixelAnimation(rowIndex, columnIndex, active)"
				/>
			</template>
		</div>
		<p class="motto relative z-10 m-0 flex translate-y-1 items-center gap-3 text-center text-[clamp(0.625rem,1.1vw,0.75rem)] font-medium uppercase tracking-[0.24em] text-stone-500 opacity-0 motion-reduce:translate-y-0 motion-reduce:animate-none motion-reduce:opacity-100">
			<span class="h-px w-6 bg-gradient-to-r from-transparent to-red-900/70 sm:w-10" aria-hidden="true" />
			<span>Your network infrastructure assistant</span>
			<span class="h-px w-6 bg-gradient-to-l from-transparent to-red-900/70 sm:w-10" aria-hidden="true" />
		</p>
	</div>
</template>

<style scoped>
.pixel-concept {
	background: radial-gradient(circle at center, rgb(127 29 29 / 9%), transparent 34rem), #070707;
}

.ambient-grid {
	background-image: linear-gradient(rgb(255 255 255 / 1.3%) 1px, transparent 1px), linear-gradient(90deg, rgb(255 255 255 / 1.3%) 1px, transparent 1px);
	background-size: 32px 32px;
	mask-image: radial-gradient(circle at center, black, transparent 72%);
	animation: grid-arrival 1.8s 0.25s ease forwards;
}

.pixel {
	animation: dormant-pixel 1.1s ease forwards;
}

.pixel.active {
	background: #171717;
	box-shadow: none;
	animation-name: pixel-reconstruct;
	animation-timing-function: steps(1, end);
	animation-fill-mode: forwards;
}

.motto {
	animation: motto-arrival 0.35s 1.1s ease forwards;
}

@keyframes pixel-reconstruct {
	0% { background: #171717; opacity: 0; box-shadow: none; }
	14% { background: #991b1b; opacity: 0.55; box-shadow: 0 0 8px rgb(220 38 38 / 18%); }
	25% { background: #171717; opacity: 0.18; box-shadow: none; }
	39% { background: #ef4444; opacity: 1; box-shadow: 0 0 14px rgb(239 68 68 / 42%); }
	51% { background: #1f1f1f; opacity: 0.32; box-shadow: none; }
	67% { background: #b91c1c; opacity: 0.7; box-shadow: 0 0 7px rgb(220 38 38 / 22%); }
	78% { background: #262626; opacity: 0.45; box-shadow: none; }
	100% { background: #dc2626; opacity: 1; box-shadow: 0 0 10px rgb(220 38 38 / 28%); }
}

@keyframes dormant-pixel {
	to { opacity: 0.62; }
}

@keyframes motto-arrival {
	to { opacity: 1; transform: none; }
}

@keyframes grid-arrival {
	to { opacity: 0.62; }
}

@media (prefers-reduced-motion: reduce) {
	.ambient-grid, .pixel, .pixel.active, .motto {
		animation: none;
	}

	.pixel.active {
		background: #dc2626;
		box-shadow: 0 0 10px rgb(220 38 38 / 28%);
	}
}
</style>
