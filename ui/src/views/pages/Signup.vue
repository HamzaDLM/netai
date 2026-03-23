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
const username = ref('')
const password = ref('')
const password_verify = ref('')

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

	AuthServices.registerUser({ username: username.value, email: email.value, password: password.value })
		.then(response => {
			authError.value = ''
			isLoading.value = false
			console.log(response.status)
			if (response.status === 201) {
				getUserDetails()
			} else {
				authError.value = 'Unexpected issue'
			}
		})
		.catch(error => {
			try {
				if (error.request.status === 409) {
					authError.value = 'User already exist, try login in'
				} else {
					authError.value = 'Unexpected issue'
				}
			} catch (_) {
				authError.value = 'Unexpected issue'
			}
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
			Blue Container
		</div>

		<div class="p-8">
			<div class="mx-auto flex w-full flex-col justify-center space-y-6 sm:w-[350px]">
				<div class="flex flex-col space-y-2 text-center">
					<h1 class="text-2xl font-semibold tracking-tight text-zinc-300">Sign up for an account</h1>
					<p class="text-sm text-zinc-400">Enter an email and a password to create an account</p>
				</div>
				<div :class="cn('grid gap-6', $attrs.class ?? '')">
					<form autocomplete="off" @submit="onSubmit">
						<div class="grid gap-2">
							<p v-if="authError" class="ml-4 text-sm text-red-400">{{ authError }}</p>
							<div class="grid gap-1">
								<Label class="sr-only" for="email"> Username </Label>
								<Input id="username" v-model="username" placeholder="john doe" type="text"
									auto-capitalize="none" auto-complete="none" auto-correct="off"
									:disabled="isLoading" />
							</div>
							<div class="grid gap-1">
								<Label class="sr-only" for="email"> Email </Label>
								<Input id="email" v-model="email" placeholder="example@example.com" type="email"
									auto-capitalize="none" auto-complete="none" auto-correct="off"
									:disabled="isLoading" />
							</div>
							<div class="grid gap-1">
								<Label class="sr-only" for="email"> Password </Label>
								<Input id="password" placeholder="password" v-model="password" type="password"
									auto-capitalize="none" autocomplete="off" auto-correct="off"
									:disabled="isLoading" />
							</div>
							<div class="grid gap-1">
								<Label class="sr-only" for="email"> Password </Label>
								<Input id="password" placeholder="password" v-model="password_verify" type="password"
									auto-capitalize="none" autocomplete="off" auto-correct="off"
									:disabled="isLoading" />
							</div>
							<!-- <LucideSpinner v-if="isLoading" class="w-4 h-4 mr-2 animate-spin" /> -->
							<Button class="mt-3" :disabled="isLoading">
								Sign Up with Email
							</Button>
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
						@click="router.push('/login')" :disabled="isLoading">
						Login
					</Button>
					<!-- <Button variant="outline" type="button" :disabled="isLoading" class="gap-4 text-zinc-300">
                        <svg xmlns="http://www.w3.org/2000/svg" x="0px" y="0px" width="1.4em" height="1.4em"
                            viewBox="0 0 48 48">
                            <path fill="#fbc02d"
                                d="M43.611,20.083H42V20H24v8h11.303c-1.649,4.657-6.08,8-11.303,8c-6.627,0-12-5.373-12-12	s5.373-12,12-12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C12.955,4,4,12.955,4,24s8.955,20,20,20	s20-8.955,20-20C44,22.659,43.862,21.35,43.611,20.083z">
                            </path>
                            <path fill="#e53935"
                                d="M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039	l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z">
                            </path>
                            <path fill="#4caf50"
                                d="M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.211,35.091,26.715,36,24,36	c-5.202,0-9.619-3.317-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z">
                            </path>
                            <path fill="#1565c0"
                                d="M43.611,20.083L43.595,20L42,20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.571	c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C36.971,39.205,44,34,44,24C44,22.659,43.862,21.35,43.611,20.083z">
                            </path>
                        </svg>
                        Google
                    </Button> -->
				</div>
				<!-- <p class="px-8 text-sm text-center text-muted-foreground">
                    By clicking continue, you agree to our
                    <a href="/terms" class="underline underline-offset-4 hover:text-primary"> Terms of Service </a>
                    and
                    <a href="/privacy" class="underline underline-offset-4 hover:text-primary"> Privacy Policy </a>
                    .
                </p> -->
			</div>
		</div>
	</div>
</template>