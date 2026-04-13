import API from '@/services/axios'

export type BackendVersionPayload = {
	backend_version: string
	backend_git_sha: string
}

export async function fetchBackendVersion(): Promise<BackendVersionPayload> {
	const response = await API.get<BackendVersionPayload>('/system/version')
	return response.data
}
