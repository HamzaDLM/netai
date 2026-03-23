import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs))
}

dayjs.extend(relativeTime)

export function formatDatetime(isoString: string): string {
	const date = dayjs(isoString)
	const now = dayjs()
	const diffMins = now.diff(date, 'minute')

	if (diffMins < 1) return 'Just now'
	if (diffMins < 60) return date.fromNow()
	if (diffMins < 1440) return date.fromNow()
	if (diffMins < 2880) return 'Yesterday'

	if (date.year() === now.year()) return date.format('MMM D')
	return date.format('MMM D, YYYY')
}
