import { Base } from '@/types/generic.type'
import authService from './auth.service'

export default class BaseService {
	protected async request<T>(fn: Promise<{ data: T }>): Promise<Base<T>> {
		try {
			const response = await fn
			return { success: true, data: response.data }
		} catch (error: any) {
			console.error('API Error:', error.response?.data || error.message)
			return { success: false, message: error.response?.data?.message || 'Request failed' }
		}
	}
}

export async function isAuthed(): Promise<boolean> {
	try {
		const response = await authService.profile()
		return response.status == 200
	} catch (_) {
		return false
	}
}

/**
 * Represents a time interval with its duration in seconds and unit name
 */
interface TimeInterval {
	seconds: number
	unit: 'year' | 'month' | 'day' | 'hour' | 'minute' | 'second'
}

/**
 * Converts a date into a human-readable relative time string
 * @param date - The date to convert (Date object or timestamp)
 * @returns A string representing the relative time (e.g., "2 hours ago")
 *
 * @example
 * ```typescript
 * const date = new Date(Date.now() - 7200000); // 2 hours ago
 * getRelativeTime(date); // returns "2 hours ago"
 *
 * getRelativeTime(new Date('2023-01-01')); // returns "1 year ago"
 * ```
 */
export function getRelativeTime(date: Date | string | number): string {
	const now = new Date()
	const targetDate = new Date(date)
	const diff = Math.floor((now.getTime() - targetDate.getTime()) / 1000) // difference in seconds

	// Array of time intervals in seconds and their corresponding units
	const intervals: TimeInterval[] = [
		{ seconds: 31536000, unit: 'year' },
		{ seconds: 2592000, unit: 'month' },
		{ seconds: 86400, unit: 'day' },
		{ seconds: 3600, unit: 'hour' },
		{ seconds: 60, unit: 'minute' },
		{ seconds: 1, unit: 'second' },
	]

	// Handle invalid dates
	if (isNaN(targetDate.getTime())) {
		throw new Error('Invalid date provided')
	}

	// Handle future dates
	if (diff < 0) {
		return 'in the future'
	}

	// Find the appropriate interval
	for (const interval of intervals) {
		const count = Math.floor(diff / interval.seconds)
		if (count >= 1) {
			// Handle plural forms
			const plural = count === 1 ? '' : 's'
			return `${count} ${interval.unit}${plural} ago`
		}
	}

	return 'just now'
}
