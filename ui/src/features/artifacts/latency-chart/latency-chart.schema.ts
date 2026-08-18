import { z } from 'zod'

export const latencyChartArtifactDataSchema = z
	.object({
		target: z.string(),
		simulated: z.boolean().default(false),
		unit: z.string().default('ms'),
		latest_ms: z.number().optional(),
		min_ms: z.number().optional(),
		avg_ms: z.number().optional(),
		max_ms: z.number().optional(),
		points: z.array(
			z.object({
				timestamp: z.string(),
				value: z.number(),
			})
		),
	})
	.passthrough()
