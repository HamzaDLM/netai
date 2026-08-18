import type { ConfigDiffArtifactData, DiffFile, DiffHunk } from './config-diff.schema'

export function normalizeUnifiedPatch(patch: string): string {
	const normalizedLineEndings = patch.replace(/\r\n?/g, '\n')
	if (normalizedLineEndings.includes('\n')) return normalizedLineEndings

	// Older mock payloads were persisted with literal "\\n" separators.
	return normalizedLineEndings.replace(/\\r\\n|\\n|\\r/g, '\n')
}

export function isUnifiedDiffText(value: string): boolean {
	const patch = normalizeUnifiedPatch(value)
	return /(^|\n)---\s+\S+/.test(patch) && /(^|\n)\+\+\+\s+\S+/.test(patch) && /(^|\n)@@\s+-\d+/.test(patch)
}

export function parseUnifiedPatchToDiffFile(patch: string, oldPath: string, newPath: string): DiffFile {
	const hunkHeaderRegex = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/
	const hunks: DiffHunk[] = []
	let currentHunk: DiffHunk | null = null
	let oldLine = 0
	let newLine = 0

	for (const rawLine of normalizeUnifiedPatch(patch).split('\n')) {
		if (rawLine.startsWith('@@')) {
			const match = rawLine.match(hunkHeaderRegex)
			if (!match) continue

			const oldStart = Number(match[1] ?? 0)
			const newStart = Number(match[3] ?? 0)
			currentHunk = {
				header: rawLine,
				old_start: oldStart,
				old_lines: Number(match[2] ?? 1),
				new_start: newStart,
				new_lines: Number(match[4] ?? 1),
				lines: [],
			}
			hunks.push(currentHunk)
			oldLine = oldStart
			newLine = newStart
			continue
		}

		if (!currentHunk || rawLine.startsWith('\\ No newline at end of file')) continue

		if (rawLine.startsWith('+')) {
			currentHunk.lines.push({ type: 'added', old_lineno: null, new_lineno: newLine, content: rawLine.slice(1) })
			newLine += 1
			continue
		}

		if (rawLine.startsWith('-')) {
			currentHunk.lines.push({ type: 'removed', old_lineno: oldLine, new_lineno: null, content: rawLine.slice(1) })
			oldLine += 1
			continue
		}

		currentHunk.lines.push({
			type: 'context',
			old_lineno: oldLine,
			new_lineno: newLine,
			content: rawLine.startsWith(' ') ? rawLine.slice(1) : rawLine,
		})
		oldLine += 1
		newLine += 1
	}

	return { old_path: oldPath, new_path: newPath, hunks }
}

export function diffFilesFromArtifactData(data: ConfigDiffArtifactData): DiffFile[] {
	if (data.diff_files?.length) return data.diff_files
	if (!data.config_diff) return []

	const fallbackPath = data.file_path ?? data.device ?? 'config'
	const file = parseUnifiedPatchToDiffFile(data.config_diff.patch, data.config_diff.old_path ?? fallbackPath, data.config_diff.new_path ?? fallbackPath)
	return file.hunks.length > 0 ? [file] : []
}
