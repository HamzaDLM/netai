export const latencyDiagnosticMarkdown: string = `
# Latency Investigation Summary

## Overview

Intermittent latency spikes (250-350 ms) observed between:

- app-01 (10.10.40.12)
- db-01 (10.10.50.8)
- core-sw-01
- fw-01

Normal latency: 2-4 ms.

---

## Ping Test

\`\`\`bash
ping 10.10.50.8 -c 5
\`\`\`

\`\`\`log
64 bytes from 10.10.50.8: icmp_seq=1 ttl=62 time=2.3 ms
64 bytes from 10.10.50.8: icmp_seq=2 ttl=62 time=310.4 ms
64 bytes from 10.10.50.8: icmp_seq=3 ttl=62 time=2.1 ms
\`\`\`

Latency spike confirmed.

---

## MTR Output

\`\`\`log
HOST: app-01
 1.|-- access-sw-03   0.0%   0.5 ms
 2.|-- core-sw-01     0.0% 320.4 ms
 3.|-- fw-01          0.0% 330.7 ms
 4.|-- db-01          0.0% 340.9 ms
\`\`\`

Latency begins at **core-sw-01**.

---

## Core Switch Interface

\`\`\`bash
show interface TenGig1/0/24
\`\`\`

\`\`\`log
5 minute input rate 8.9 Gbits/sec
5 minute output rate 9.2 Gbits/sec
Output queue depth: 82
Total output drops: 84213
\`\`\`

High utilization + queue drops detected.

---

## Zabbix Event

\`\`\`json
{
  "host": "core-sw-01",
  "trigger": "Interface utilization > 90%",
  "value": "92%",
  "severity": "High"
}
\`\`\`

---

## Syslog Extract

\`\`\`log
Mar 05 14:15:22 core-sw-01 %ETHPORT-5-IF_DOWN_LINK_FAILURE: Interface TenGig1/0/48 down
Mar 05 14:15:24 core-sw-01 %QOS-4-QUEUE_DROP: Output queue threshold exceeded
\`\`\`

Uplink flap coincides with queue drops.

---

## Metrics Comparison

| Metric | Normal | Incident |
|--------|--------|----------|
| Latency | 3 ms | 320 ms |
| Utilization | 40% | 92% |
| Queue Depth | <10 | 80+ |

---

## Likely Cause

Temporary uplink instability caused traffic congestion on a single 10G link, leading to queue saturation and latency spikes.

---

## Recommended Actions

1. Check uplink stability:
   \`\`\`bash
   show logging | include TenGig1/0/48
   \`\`\`

2. Verify LACP configuration.
3. Consider additional uplink capacity or QoS prioritization.
`
interface ChatMessage {}

export const chatHistory: ChatMessage[] = [
	{
		role: 'user',
		content: 'My internet connection keeps dropping every few hours. How do I diagnose this?',
		title: 'Intermittent Connection Drops',
		preview: 'My internet connection keeps dropping every few hours...',
		datetime: '2026-03-04T09:12:00Z',
	},
	{
		role: 'assistant',
		content:
			"Let's systematically diagnose your intermittent connection drops. Start by running `ping -t 8.8.8.8` in your terminal to monitor packet loss over time. Also check your router logs for disconnection events, and note whether the drops affect all devices or just one.",
		title: 'Initial Diagnosis Steps',
		preview: "Let's systematically diagnose your intermittent connection drops...",
		datetime: '2026-03-04T09:12:45Z',
	},
	{
		role: 'user',
		content: "I ran the ping and I'm seeing occasional 'Request timed out' messages. What does that mean?",
		title: 'Ping Timeout Observed',
		preview: "I ran the ping and I'm seeing occasional 'Request timed out' messages...",
		datetime: '2026-03-04T09:18:22Z',
	},
	{
		role: 'assistant',
		content:
			"Yes, the 2nd hop is typically your ISP's first point of presence — meaning the issue is on their infrastructure or the line between your modem and their network. Document your findings with timestamps and contact your ISP — ask them to check line signal levels and run a diagnostic from their end.",
		title: 'ISP Infrastructure Confirmed',
		preview: "Yes, the 2nd hop is typically your ISP's first point of presence...",
		datetime: '2026-03-04T09:32:44Z',
	},
	{
		role: 'user',
		content: 'How do I check if my DNS is causing any of these issues?',
		title: 'DNS Troubleshooting Query',
		preview: 'How do I check if my DNS is causing any of these issues?',
		datetime: '2026-03-04T09:40:11Z',
	},
	{
		role: 'assistant',
		content:
			"Good thinking — DNS issues can mimic connectivity problems. Run `nslookup google.com` and `nslookup google.com 8.8.8.8` to compare your default DNS vs. Google's. To fix it, switch to a public DNS like 8.8.8.8 / 8.8.4.4 (Google) or 1.1.1.1 (Cloudflare) in your router or network adapter settings.",
		title: 'DNS Diagnosis & Fix',
		preview: 'Good thinking — DNS issues can mimic connectivity problems. Run `nslookup`...',
		datetime: '2026-03-04T09:41:02Z',
	},
]
