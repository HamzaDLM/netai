# Agent UI Artifacts

NetAI renders live network diagnostics as typed artifacts embedded at the point where a tool runs in an assistant answer. Assistant prose remains ordinary Markdown; UI instructions never have to be encoded in model-generated text such as `|visual: ...|`.

## Design

```text
LLM token/tool call
        │
        ├── assistant_token ───────────────────────► Markdown timeline block
        ├── tool_started/completed/failed ─────────► Agent activity / thoughts
        │
        └── artifact_snapshot/delta ───────────────► typed artifact timeline block
                         │
                         └── persisted AgentEvent ─► identical rendering after reload
```

Each artifact has a stable envelope:

```json
{
  "id": "art_...",
  "kind": "network.ping.v1",
  "schema_version": 1,
  "status": "running",
  "title": "Ping edge-router.example.net",
  "data": {},
  "provenance": {
    "source": "netai_mock_probe",
    "simulated": true
  }
}
```

The first `artifact_snapshot` creates the artifact. Subsequent `artifact_delta` events either merge fields from `set` into `data` or append arrays from `append`. This keeps live updates small and makes the final state deterministic.

The API adds `assistant_offset` to each runtime event. The frontend places the artifact at that character offset, so a sequence can render as:

```text
I will check reachability.
[live ping card]
The host did not reply, so I will inspect its environment.
```

## Relevant Files

- `backend/app/services/agent_events.py`: request-scoped lifecycle and artifact observer.
- `backend/app/agents/netai.py`: Haystack hooks that publish tool lifecycle events.
- `backend/app/tools/probe_tools.py`: simulated ping, traceroute, and latency-series examples.
- `backend/app/services/netai.py`: maps native Haystack streaming chunks into ordered events.
- `backend/app/services/chat_agent.py`: sequences events for the conversation endpoint.
- `backend/app/api/endpoints/chat.py`: SSE transport, inline offsets, and durable event persistence.
- `backend/app/api/models/chat.py`: ordered `AgentEvent` records.
- `ui/src/features/artifacts/artifact.timeline.ts`: snapshot/delta reducer and inline timeline construction.
- `ui/src/features/artifacts/artifact.registry.ts`: artifact-kind-to-renderer registry.
- `ui/src/features/artifacts/ArtifactHost.vue`: lazy component host with a generic fallback.
- `ui/src/features/artifacts/ArtifactViewerShell.vue`: shared viewer header, icon slot, stone theme, and fullscreen zoom behavior.
- `ui/src/features/execution/execution.normalize.ts`: one normalized view of live events, flat persisted runs, and historical nested runs.
- `ui/src/features/execution/AgentActivity.vue`: connector-grouped thought/activity history.

After the SSE `done` event, the chat store reloads the committed conversation. This replaces the lightweight live lifecycle data with authoritative persisted tool inputs, outputs, errors, and timings without requiring a page refresh.

Every visual component lives in its own feature directory. ApexCharts is loaded only when a latency chart artifact is present.

## Adding an Artifact

1. Choose a versioned kind such as `network.packet-capture.v1`. Changing a payload incompatibly requires a new version.
2. For an incremental tool, accept Haystack's hidden `streaming_callback` and emit
   `StreamingChunk` metadata containing a `netai_event` snapshot/delta.
3. For a result-backed tool, set `auto_artifact: True` in its `netai_tool`
   presentation metadata; the Agent hooks create and complete the artifact.
4. Add a Zod payload schema and a Vue renderer under `ui/src/features/artifacts/<name>/`.
5. Register the lazy renderer in `artifact.registry.ts`.
6. Test event ordering, snapshot/delta reduction, reload persistence, and invalid payload fallback.

Unknown kinds render through `GenericArtifact.vue`, so deploying a backend artifact before its frontend renderer does not break the conversation.

## Result-backed Viewers

The existing viewers now participate in the same timeline through thin, typed adapters:

- `network.topology.v1` wraps `TopologyMapper.vue`.
- `config.diff.v1` wraps `ConfigDiffViewer.vue` and parses the sanitized unified patch.

These tools return one complete read-only result rather than many incremental samples. Their `@netai_tool` presentation metadata therefore sets `auto_artifact: True`: the Agent hooks emit a running placeholder before invocation and merge the tool result into that artifact afterward. Incremental tools such as ping and traceroute emit native streaming chunks directly.

The old `[[CONFIG_DIFF]]` parser and tool-result discovery remain only as a compatibility path for conversations persisted before typed artifacts were introduced. New prompts do not emit visual markers.

## Safety Boundary for Real Network Tools

The example probes are deliberately simulated and never execute a shell or send network traffic. Ping and traceroute would be active probes in a real runner even though they do not modify device configuration; they should not be described as purely passive commands.

A production runner should be a separate, least-privileged service rather than arbitrary command execution in the API process. It should:

- expose an allowlisted operation API, not a shell string;
- validate hostnames, addresses, interfaces, ports, counts, and capture filters;
- apply RBAC, target/environment policy, concurrency limits, deadlines, output caps, and cancellation;
- run with dropped capabilities and isolation appropriate to the operation;
- classify operations as passive, read-only query, active probe, or mutating;
- redact secrets and sensitive packet data before persistence or model access;
- audit requester, resolved target, normalized arguments, timing, result status, and truncation;
- keep packet captures bounded by interface, filter, duration, packet count, and byte count.

The artifact protocol does not depend on the mock implementation, so a sandboxed runner can replace it without changing the LLM-facing tool schema or Vue components.

## Recommended Next Components

- bounded packet-capture stream with summary-first rendering;
- tabular DNS, ARP, route, interface, BGP, and MAC lookup results;
- reusable time-series chart for latency, loss, bandwidth, and error counters;
- report artifact that snapshots evidence and exports a server-generated document.
