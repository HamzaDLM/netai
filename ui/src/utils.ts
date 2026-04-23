// Converts a timestamp to a human-readable format
export function formatTimestamp(timestamp: Date): string {
	const date = new Date(timestamp)
	return date
		.toLocaleString('en-US', {
			year: 'numeric',
			month: 'short',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit',
			hour12: false,
		})
		.replace(',', '')
}

// Checks if a timestamp is from today
export function isToday(timestamp: Date): boolean {
	const date = new Date(timestamp)
	const today = new Date()

	return date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth() && date.getDate() === today.getDate()
}

// Replaces the webpage title with NetAI as prefix
export function setPageTitle(newTitle: string) {
	document.title = `NetAI | ${newTitle}`
}
