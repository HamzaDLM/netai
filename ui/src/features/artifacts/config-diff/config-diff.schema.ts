import { z } from 'zod'

export const diffLineSchema = z.object({
	type: z.enum(['context', 'added', 'removed', 'meta']),
	old_lineno: z.number().nullable(),
	new_lineno: z.number().nullable(),
	content: z.string(),
})

export const diffHunkSchema = z.object({
	header: z.string(),
	old_start: z.number(),
	old_lines: z.number(),
	new_start: z.number(),
	new_lines: z.number(),
	lines: z.array(diffLineSchema),
})

export const diffFileSchema = z.object({
	old_path: z.string(),
	new_path: z.string(),
	hunks: z.array(diffHunkSchema),
})

const commitSchema = z
	.object({
		hash: z.string().optional(),
		author: z.string().optional(),
		email: z.string().optional(),
		date: z.string().optional(),
		message: z.string().optional(),
	})
	.passthrough()

const unifiedDiffSchema = z
	.object({
		format: z.string().optional(),
		old_path: z.string().optional(),
		new_path: z.string().optional(),
		patch: z.string(),
	})
	.passthrough()

export const configDiffArtifactDataSchema = z
	.object({
		tool_name: z.string().optional(),
		arguments: z.record(z.unknown()).optional(),
		device: z.string().optional(),
		file_path: z.string().optional(),
		last_commit: commitSchema.optional(),
		config_diff: unifiedDiffSchema.optional(),
		diff_files: z.array(diffFileSchema).optional(),
		error: z.string().optional(),
	})
	.passthrough()

export type DiffLineType = z.infer<typeof diffLineSchema>['type']
export type DiffLine = z.infer<typeof diffLineSchema>
export type DiffHunk = z.infer<typeof diffHunkSchema>
export type DiffFile = z.infer<typeof diffFileSchema>
export type ConfigDiffArtifactData = z.infer<typeof configDiffArtifactDataSchema>
