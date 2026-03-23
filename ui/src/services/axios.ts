import axios from 'axios'

const URL = import.meta.env.VITE_BASE_URL

const API = axios.create({
	baseURL: URL,
	withCredentials: true, // should be disabled to use wildcard in CORS.
})

API.interceptors.response.use(
	function (response) {
		return response
	},
	function (error) {
		// TODO
		// const originalRequest = error.config
		// if (error.response.status === 401 && !originalRequest._retry) {
		// 	console.log('refresh asked')
		// 	// after logic done
		// 	return API(originalRequest)
		// }
		return Promise.reject(error)
	}
)

export default API
