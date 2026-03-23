<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { cn } from '@/lib/utils'

import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'

import AuthServices from '../../services/auth.service'
import { useUserStore } from '../../stores/user.store'

const router = useRouter()
const userStore = useUserStore()

const isLoading = ref(false)

const email = ref('')
const password = ref('')

const authError = ref('')

function getUserDetails() {
	AuthServices.profile()
		.then(response => {
			userStore.profile = response.data
			router.push('/Home')
		})
		.catch(_ => {
			console.log('error')
		})
}

function onSubmit(event: Event) {
	event.preventDefault()
	isLoading.value = true

	AuthServices.login({ email: email.value, password: password.value })
		.then(response => {
			authError.value = ''
			isLoading.value = false
			if (response.status === 200) {
				getUserDetails()
			} else {
				authError.value = 'Unexpected issue'
			}
		})
		.catch(error => {
			console.log(error)
			authError.value = 'Wrong credentials'
			isLoading.value = false
		})
}
</script>

<template>
	<div class="container relative grid items-center justify-center w-screen h-screen lg:max-w-none lg:px-0">
		<div class="absolute top-0 z-20 flex items-center gap-3 m-10 text-lg font-medium">
			<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 256 256">
				<path fill="currentColor"
					d="M236.4 70.65L130.2 40.31a8 8 0 0 0-3.33-.23L21.74 55.1A16.08 16.08 0 0 0 8 70.94v114.12a16.08 16.08 0 0 0 13.74 15.84l105.13 15a8.5 8.5 0 0 0 1.13.1a8 8 0 0 0 2.2-.31l106.2-30.34A16.07 16.07 0 0 0 248 170V86a16.07 16.07 0 0 0-11.6-15.35M64 120H48a8 8 0 0 0 0 16h16v54.78l-40-5.72V70.94l40-5.72Zm56 78.78l-40-5.72V136h16a8 8 0 0 0 0-16H80V62.94l40-5.72Z" />
			</svg>
			App
		</div>

		<div class="p-8">
			<div class="mx-auto flex w-full flex-col justify-center space-y-6 sm:w-[350px]">
				<div class="flex flex-col space-y-2 text-center">
					<h1 class="text-2xl font-semibold tracking-tight text-zinc-300">Login to your account</h1>
					<p class="text-sm text-zinc-400">Enter your email below to login to your account</p>
				</div>
				<div :class="cn('grid gap-6', $attrs.class ?? '')">
					<form @submit="onSubmit">
						<div class="grid gap-2">
							<p v-if="authError" class="ml-4 text-sm text-red-400">{{ authError }}</p>
							<div class="grid gap-1">
								<Label class="sr-only" for="email"> Email </Label>
								<Input id="email" v-model="email" placeholder="example@example.com" type="email"
									auto-capitalize="none" auto-complete="email" auto-correct="off"
									:disabled="isLoading" />
							</div>
							<div class="grid gap-1 mb-3">
								<Label class="sr-only" for="email"> Password </Label>
								<Input id="password" v-model="password" placeholder="password" type="password"
									auto-capitalize="none" auto-complete="password" auto-correct="off"
									:disabled="isLoading" />
							</div>
							<Button :disabled="isLoading">Login with Email</Button>
						</div>
					</form>
					<div class="relative">
						<div class="absolute inset-0 flex items-center">
							<span class="w-full border-t" />
						</div>
						<div class="relative flex justify-center text-xs uppercase">
							<span class="px-2 bg-zinc-900 text-muted-foreground"> Or </span>
						</div>
					</div>
					<Button
						class="text-white underline bg-transparent opacity-100 hover:text-zinc-200 hover:bg-transparent"
						@click="router.push('/signup')" :disabled="isLoading">Sign up</Button>
				</div>
			</div>
		</div>
	</div>
</template>