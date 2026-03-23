// import { ref, onMounted } from 'vue'
// import API from '@/services/axios'
// import type { Base } from '@/types/generic.type'

// export function useFetch<T>(endpoint: string, autoFetch = true) {
// 	const isOpen = ref(false)
// 	const data = ref<T | null>(null)
// 	const error = ref<string | null>(null)
// 	const loading = ref<boolean>(false)

// 	const fetchData = async () => {
// 		loading.value = true
// 		try {
// 			const response = await API.get<Base<T>>(endpoint)
// 			if (response.data.success) {
// 				data.value = response.data.data
// 			} else {
// 				error.value = response.data.message
// 			}
// 		} catch (err: any) {
// 			error.value = 'Failed to fetch data'
// 			console.error(err)
// 		} finally {
// 			loading.value = false
// 		}
// 	}

// 	if (autoFetch) {
// 		onMounted(fetchData)
// 	}

// 	return { data, error, loading, fetchData }
// }
