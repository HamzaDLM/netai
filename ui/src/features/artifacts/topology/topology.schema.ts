import { z } from 'zod'

export const topologyDeviceSchema = z
	.object({
		hostname: z.string(),
		mgmt_ip: z.string(),
		site: z.string(),
		role: z.string(),
		status: z.string(),
	})
	.passthrough()

export const topologyLinkSchema = z
	.object({
		link_id: z.string(),
		a_device: z.string(),
		a_interface: z.string(),
		b_device: z.string(),
		b_interface: z.string(),
		status: z.string(),
		bandwidth_mbps: z.number().default(0),
		metric: z.number().default(0),
		last_change: z.string().default(''),
	})
	.passthrough()

export const topologyArtifactDataSchema = z
	.object({
		tool_name: z.string().optional(),
		arguments: z.record(z.unknown()).optional(),
		scope: z.string().optional(),
		device_count: z.number().optional(),
		link_count: z.number().optional(),
		link_status_counts: z.record(z.number()).optional(),
		devices: z.array(topologyDeviceSchema).optional(),
		links: z.array(topologyLinkSchema).optional(),
		error: z.string().optional(),
	})
	.passthrough()

export type TopologyDevice = z.infer<typeof topologyDeviceSchema>
export type TopologyLink = z.infer<typeof topologyLinkSchema>
export type TopologyArtifactData = z.infer<typeof topologyArtifactDataSchema>
export type TopologyPayload = TopologyArtifactData & {
	scope: string
	device_count: number
	link_count: number
	devices: TopologyDevice[]
	links: TopologyLink[]
}
