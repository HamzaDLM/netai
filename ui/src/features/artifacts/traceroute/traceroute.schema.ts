import { z } from 'zod'

export const tracerouteHopSchema = z.object({
	hop: z.number(),
	status: z.enum(['reply', 'timeout', 'destination']),
	address: z.string().nullable(),
	hostname: z.string().nullable(),
	latencies_ms: z.array(z.number()),
})

export const tracerouteArtifactDataSchema = z
	.object({
		target: z.string(),
		simulated: z.boolean().default(false),
		max_hops: z.number(),
		complete: z.boolean(),
		reached_destination: z.boolean().optional(),
		hop_count: z.number().optional(),
		hops: z.array(tracerouteHopSchema),
	})
	.passthrough()
