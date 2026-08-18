import { z } from 'zod'

export const pingSampleSchema = z.object({
	sequence: z.number(),
	status: z.enum(['reply', 'timeout']),
	bytes: z.number().optional(),
	ttl: z.number().optional(),
	latency_ms: z.number().optional(),
	received_at: z.string().optional(),
})

export const pingArtifactDataSchema = z
	.object({
		target: z.string(),
		simulated: z.boolean().default(false),
		count: z.number(),
		sent: z.number(),
		received: z.number(),
		loss_percent: z.number(),
		min_ms: z.number().nullable().optional(),
		avg_ms: z.number().nullable().optional(),
		max_ms: z.number().nullable().optional(),
		jitter_ms: z.number().nullable().optional(),
		samples: z.array(pingSampleSchema),
	})
	.passthrough()

export type PingArtifactData = z.infer<typeof pingArtifactDataSchema>
