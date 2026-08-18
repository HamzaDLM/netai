# Frontend Audit Findings

Audit date: 2026-08-14

Scope: frontend routing and authorization, Pinia state, API and streaming behavior, asynchronous race conditions, attachments, tool visualizations, rendering and security, responsive behavior, settings, skills, admin views, and frontend quality gates. The audit itself was read-only; this file records the findings.

## Severity summary

- Critical: 1
- High: 7
- Medium: 8
- Lower severity: 5 grouped findings

The most urgent problems are authorization, stream state leaking across conversations, attachment misplacement, and overlapping requests.

## Critical

### 1. Authorization and role enforcement are effectively absent

Routes marked `requiresAuth` still always continue through the no-op guard in [ui/src/router.ts:65](ui/src/router.ts#L65). The Admin section is shown unconditionally in [ui/src/components/chat/ChatSidebar.vue:363](ui/src/components/chat/ChatSidebar.vue#L363) and immediately requests cross-user feedback in [ui/src/components/chat/ChatAdminPanel.vue:19](ui/src/components/chat/ChatAdminPanel.vue#L19).

The frontend computes an administrative role in [ui/src/stores/skills.store.ts:17](ui/src/stores/skills.store.ts#L17), but that value is not used to gate the Admin navigation or panel.

More importantly, the current backend identity dependency always returns a test administrator in [backend/app/core/security.py:15](backend/app/core/security.py#L15). Unless another upstream layer independently enforces authorization, every user who can reach the application is effectively an administrator. Frontend gating should be added for UX, but the backend identity implementation is the real security boundary.

Impact:

- Protected routes are not actually protected.
- Every reachable user can see the Admin entry point.
- The current backend role stub makes every caller an administrator.
- The live feedback view can expose conversations and feedback belonging to other users.

## High

### 2. Changing conversations during streaming can permanently hang the request

Stream callbacks locate their assistant message inside the *currently selected* conversation in [ui/src/stores/chat.store.ts:376](ui/src/stores/chat.store.ts#L376). After switching chats, the token flush cannot find that message, clears its timer, but leaves buffered text pending in [ui/src/stores/chat.store.ts:381](ui/src/stores/chat.store.ts#L381).

The completion path then waits forever for that buffer in [ui/src/stores/chat.store.ts:547](ui/src/stores/chat.store.ts#L547), so the `finally` block never clears `isStreamingResponse` or `streamingAssistantMessageId`.

Likely symptoms:

- The response spinner never finishes.
- The answer stops updating in the UI.
- Switching back does not necessarily recover the stream.
- Reloading restores the backend-persisted answer and clears the stuck UI state.

Any operation that clears or replaces `selectedConversation` during a stream can trigger this, including selecting another chat and the sidebar reset behavior described below.

### 3. Conversation, search, attachment, and prompt-preview requests have stale-response races

Rapidly selecting conversation A and then conversation B starts two uncancelled requests. Whichever finishes last overwrites `selectedConversation` in [ui/src/stores/chat.store.ts:212](ui/src/stores/chat.store.ts#L212), even if it is the older A request.

Related races:

- Attachment loading blindly replaces the global attachment list in [ui/src/stores/chat.store.ts:283](ui/src/stores/chat.store.ts#L283).
- Older search requests can overwrite newer search results in [ui/src/stores/chat.store.ts:173](ui/src/stores/chat.store.ts#L173).
- The single `isSyncing` boolean can become false when an earlier request completes while a newer request is still pending.
- Prompt previews accept late results without confirming that the originating conversation is still selected in [ui/src/views/pages/Chat.vue:171](ui/src/views/pages/Chat.vue#L171).
- Background title-refresh requests use the same unsequenced conversation loader and can race with user searches.

Impact:

- The wrong chat can appear selected.
- Attachments from one chat can appear under another chat.
- Search results can jump back to an older query.
- Prompt preview can show the wrong conversation or draft.
- Reloading appears to fix the problem because the persisted backend data is correct.

### 4. An attachment can be persisted into the wrong conversation

The selected conversation is checked before `await file.text()`, but its ID is read only afterward in [ui/src/stores/chat.store.ts:299](ui/src/stores/chat.store.ts#L299). If the user switches conversations while the browser is reading the file, the upload is sent to the newly selected conversation rather than the conversation where the upload began.

If the switch happens after the request starts, its response is still appended to whichever global attachment list is currently displayed.

There is also no client-side size check before reading the entire file into memory. The backend limit is 256 KiB in [backend/app/core/config.py:70](backend/app/core/config.py#L70), but a user can select a much larger file and make the browser load it completely before the backend rejects it.

Impact:

- Sensitive document contents can be attached to the wrong chat.
- The visible attachment list can temporarily represent a different conversation.
- Very large files can freeze or exhaust the tab before validation occurs.
- Sending while the upload is pending submits the question without the expected document context.

### 5. The composer permits overlapping or invalid sends

`askLLM` does not reject a call when another response is already streaming in [ui/src/stores/chat.store.ts:362](ui/src/stores/chat.store.ts#L362). The send button is disabled only for blank text in [ui/src/views/pages/Chat.vue:1747](ui/src/views/pages/Chat.vue#L1747).

A second request overwrites the global `isStreamingResponse` and `streamingAssistantMessageId`. The first request can then clear those flags while the second request is still active, and streamed state, context metrics, and feedback IDs can point at the wrong response.

The composer also remains logically available when:

- No conversation has finished loading.
- A conversation selection is syncing.
- An attachment is uploading.
- Another answer is streaming.
- The store has just been reset by a sidebar operation.

The submit handler clears the draft before `askLLM` verifies that a conversation exists in [ui/src/views/pages/Chat.vue:1193](ui/src/views/pages/Chat.vue#L1193). A send during initial loading or after a reset can therefore silently discard the user's text.

### 6. The SSE pipeline can silently accept incomplete answers

The stream reader treats any clean EOF as success without requiring a `done` event. It silently discards malformed events and never flushes the decoder or remaining buffer in [ui/src/services/chat.service.ts:109](ui/src/services/chat.service.ts#L109) and [ui/src/services/chat.service.ts:147](ui/src/services/chat.service.ts#L147).

A proxy or network truncation can therefore be treated as a successful partial response. The store can drain the partial tokens, schedule a title refresh, and finish without ever receiving a valid persisted message ID.

Additional problems:

- `message_id` is converted with `Number(...)` without checking that it is finite.
- There is no `AbortController` for obsolete streams after navigation or conversation changes.
- A 200 response containing non-SSE content can end without producing an explicit error.
- Streaming fetch bypasses the shared Axios interceptor and any future centralized authentication handling.

Both production proxy configurations omit SSE-specific settings such as `proxy_buffering off`, cache disabling, and a suitable read timeout:

- [ui/nginx.conf:8](ui/nginx.conf#L8)
- [ansible/roles/netai/templates/netai-nginx.conf.j2:8](ansible/roles/netai/templates/netai-nginx.conf.j2#L8)

The backend `StreamingResponse` also does not send an `X-Accel-Buffering: no` header in [backend/app/api/endpoints/chat.py:1064](backend/app/api/endpoints/chat.py#L1064). Default proxy behavior can batch tokens or terminate a long-running agent request after a sufficiently long quiet period.

### 7. Config-diff and topology visualizations do not match the backend tool contract

The frontend only recognizes dotted names such as `bitbucket.get_recent_device_config_diff` and `datamodel.get_topology` in:

- [ui/src/views/pages/Chat.vue:810](ui/src/views/pages/Chat.vue#L810)
- [ui/src/views/pages/Chat.vue:844](ui/src/views/pages/Chat.vue#L844)

The current backend emits underscore-separated names:

- `bitbucket_get_recent_device_config_diff` in [backend/app/tools/bitbucket_tools.py:612](backend/app/tools/bitbucket_tools.py#L612)
- `datamodel_get_topology` in [backend/app/tools/datamodel_tools.py:584](backend/app/tools/datamodel_tools.py#L584)

The older `ChatListTool` component checks a third obsolete name, `bitbucket.get_device_config_diff`, in [ui/src/components/chat/ChatListTool.vue:66](ui/src/components/chat/ChatListTool.vue#L66).

Consequences:

- Config-diff markers remain unresolved text.
- Config diffs are not converted into the specialized viewer.
- Topology results are not rendered as graphs.
- The generic tool output may still appear, hiding the fact that the specialized feature is broken.

Live event output has a second shape mismatch. `specialist_evidence` stores output as `{ result, evidence }` in [ui/src/views/pages/Chat.vue:599](ui/src/views/pages/Chat.vue#L599), while the diff and topology parsers look for fields such as `config_diff`, `devices`, and `links` at the top level.

### 8. The local/server message ID scheme has a production-scale failure point

Optimistic IDs begin at 1001 in [ui/src/stores/chat.store.ts:7](ui/src/stores/chat.store.ts#L7). `ChatActions` assumes every ID greater than or equal to 1000 is an unsynchronized local message in [ui/src/components/chat/ChatActions.vue:46](ui/src/components/chat/ChatActions.vue#L46).

Once real database message IDs reach 1000, feedback becomes unavailable for valid persisted messages. This is a deterministic scale-dependent failure, not merely a theoretical collision.

The assistant ID is also mutated from its temporary value to the server value in [ui/src/stores/chat.store.ts:526](ui/src/stores/chat.store.ts#L526), while that ID is used as the Vue DOM key in [ui/src/views/pages/Chat.vue:1390](ui/src/views/pages/Chat.vue#L1390). The associated optimistic user ID is never reconciled.

Impact:

- Feedback is disabled for every valid server message with ID 1000 or greater.
- Changing a row's key can remount the message and lose component-local UI state.
- Temporary and database ID ranges can collide and create duplicate Vue keys.
- Concurrent streams make those collisions and remounts more difficult to reason about.

## Medium

### 9. The diff viewer shows fabricated change provenance

Every diff displays the same commit message, author, and timestamp in [ui/src/components/chat/ConfigDiffViewer.vue:224](ui/src/components/chat/ConfigDiffViewer.vue#L224):

- Commit message: `Restrict management ACL on VTY`
- Author: `DELLAM Hamza`
- Date: `2026-03-12 at 13:55:39`

The backend already returns genuine `last_commit` metadata in [backend/app/tools/bitbucket_tools.py:420](backend/app/tools/bitbucket_tools.py#L420), but the frontend discards it when constructing the viewer data.

This is particularly risky in a network-operations interface because users may treat the displayed provenance as real audit information. The bug is currently partly masked by the tool-name mismatch above.

The viewer also aggregates added and removed counts across every file and then displays those totals inside each individual file header. Its wheel handler stops propagation and can trap scrolling at the top or bottom in [ui/src/components/chat/ConfigDiffViewer.vue:159](ui/src/components/chat/ConfigDiffViewer.vue#L159).

### 10. Failed streams leave ghost or partial optimistic messages

The store adds the user message and a blank assistant message before making the request in [ui/src/stores/chat.store.ts:365](ui/src/stores/chat.store.ts#L365). The error handler only displays a toast in [ui/src/stores/chat.store.ts:564](ui/src/stores/chat.store.ts#L564).

It does not:

- Remove an assistant draft that was never persisted.
- Mark the message as failed.
- Offer a retry action.
- Reconcile the conversation with the backend.
- Distinguish a partial response from a completed response.

The current session can consequently show a blank or partial assistant answer that changes or disappears after reload.

### 11. Login and signup routes are nonfunctional against the current API

The frontend calls `/login`, `/users`, `/profile`, and `/logout` in [ui/src/services/auth.service.ts:28](ui/src/services/auth.service.ts#L28). None of those routers are registered by [backend/app/api/router.py:3](backend/app/api/router.py#L3).

Even if those endpoints were added, both successful paths redirect to nonexistent `/Home` rather than `/` in:

- [ui/src/views/pages/Login.vue:24](ui/src/views/pages/Login.vue#L24)
- [ui/src/views/pages/Signup.vue:26](ui/src/views/pages/Signup.vue#L26)

Signup also never compares or sends `password_verify`, and both password inputs use the same DOM ID in [ui/src/views/pages/Signup.vue:101](ui/src/views/pages/Signup.vue#L101).

Separately, the Axios response interceptor contains no 401/session-expiry behavior in [ui/src/services/axios.ts:10](ui/src/services/axios.ts#L10). Expired users remain on a stale application shell and receive feature-specific generic errors instead of being redirected or reauthenticated.

### 12. Rename, rename-cancel, and delete unnecessarily tear down the entire chat state

Even cancelling a rename calls `resetState()` in [ui/src/components/chat/ChatSidebar.vue:71](ui/src/components/chat/ChatSidebar.vue#L71). That function clears the selected conversation, streaming flags, attachments, settings, and title-refresh timers before reloading all conversations.

Delete does the same in [ui/src/components/chat/ChatSidebar.vue:89](ui/src/components/chat/ChatSidebar.vue#L89), even when the store operation failed because store methods catch their own errors and return normally.

During a stream, this reset can trigger the permanent-buffer wait described in issue 2. Outside streaming, it still unexpectedly loses the current selection and returns the user to whichever conversation is auto-selected first.

The New Chat action also has no busy guard and does not await creation in [ui/src/components/chat/ChatSidebar.vue:128](ui/src/components/chat/ChatSidebar.vue#L128). Rapid clicks can create multiple empty conversations and race their selection requests.

### 13. Conversation history is inaccessible on mobile

Below the large-screen breakpoint, the sidebar is forced closed in [ui/src/views/pages/Chat.vue:240](ui/src/views/pages/Chat.vue#L240). The toggle then explicitly does nothing on smaller screens in [ui/src/views/pages/Chat.vue:1159](ui/src/views/pages/Chat.vue#L1159).

Because conversation history is rendered only in expanded mode in [ui/src/components/chat/ChatSidebar.vue:381](ui/src/components/chat/ChatSidebar.vue#L381), mobile users cannot reopen previous conversations.

Additional responsive risks include:

- Large fixed horizontal paddings on the conversation and composer.
- A fixed 24-rem left column in the Admin feedback layout.
- Desktop-oriented modal and graph dimensions.
- A fixed `h-screen` shell that may be clipped by mobile browser chrome.

### 14. Long streamed responses can become increasingly expensive to render

Each token update reconstructs MarkdownIt, parses the entire accumulated answer, applies syntax highlighting, and sanitizes all generated HTML in [ui/src/components/MarkdownRenderer.vue:14](ui/src/components/MarkdownRenderer.vue#L14).

Updates occur approximately every 16 milliseconds in [ui/src/stores/chat.store.ts:391](ui/src/stores/chat.store.ts#L391). A subtree-wide `MutationObserver` also reacts to character changes in [ui/src/views/pages/Chat.vue:1136](ui/src/views/pages/Chat.vue#L1136).

This produces increasingly expensive repeated work as an answer grows, particularly for long code blocks, tables, or tool output. The likely symptoms are input lag, high CPU use, scroll jank, and delayed rendering late in a response.

The app additionally waits for Shiki initialization before mounting at all in [ui/src/main.ts:9](ui/src/main.ts#L9). If highlighter initialization or a required chunk fails, `bootstrap()` rejects and the application remains blank instead of mounting with plain-code fallback rendering.

The current production build also warns about a roughly 1.10 MB minified main bundle, before the many syntax-language chunks.

### 15. Several operational statuses are hardcoded and may lie to users

Connector enabled and connected states are fixed constants in [ui/src/components/chat/ChatConnectorsPanel.vue:31](ui/src/components/chat/ChatConnectorsPanel.vue#L31). The `loadConnectorStatus` function is an empty TODO in [ui/src/views/pages/Chat.vue:1188](ui/src/views/pages/Chat.vue#L1188).

Other fixed information includes:

- The model is always displayed as `Gemini Flash 2.5` in [ui/src/views/pages/Chat.vue:1745](ui/src/views/pages/Chat.vue#L1745).
- The sidebar always shows `DELLAM Hamza` and `Admin` in [ui/src/components/chat/ChatSidebar.vue:423](ui/src/components/chat/ChatSidebar.vue#L423).
- Admin overview, user, and skill pages contain frontend sample data rather than live data.

The mock Admin pages label themselves as frontend examples, but they coexist with the live Feedback tab and an ungated Admin entry point. This makes it easy to mistake sample operational data for actual system state.

### 16. The full prompt-stack debugger is exposed to every user

The Debug button is always visible in [ui/src/views/pages/Chat.vue:1326](ui/src/views/pages/Chat.vue#L1326). Its drawer exposes and copies the current prompt snapshot in [ui/src/views/pages/Chat.vue:1770](ui/src/views/pages/Chat.vue#L1770), including system prompts, tool context, custom instructions, summaries, and attachment-derived context.

This may be intentional for development, but if it is an internal diagnostic feature it needs an explicit environment, administrative-role, or capability gate. Exposing system and tool instructions also makes prompt-injection discovery easier.

### 17. Failed quick feedback remains visually selected

Quick feedback changes `rating` before the API request in [ui/src/components/chat/ChatActions.vue:78](ui/src/components/chat/ChatActions.vue#L78). If the request fails, the error handler shows a toast but does not restore the previous value.

The interface consequently shows a successful thumbs-up or thumbs-down state even though nothing was persisted.

### 18. Unkeyed conversation rows can reuse the wrong child-component state

The active conversation `v-for` lacks a Vue key in [ui/src/components/chat/ChatSidebar.vue:382](ui/src/components/chat/ChatSidebar.vue#L382). When conversations are inserted, removed, reordered, or replaced by search results, Vue can patch rows by position and reuse dropdown/component state for a different conversation.

`ChatListTool.vue` has three additional missing-key errors, although that component does not appear to be part of the primary current chat path.

## Lower-severity issues

### 19. Topology layout has unsafe fallback positioning

Unknown device roles use lane 99 in [ui/src/components/chat/TopologyMapper.vue:104](ui/src/components/chat/TopologyMapper.vue#L104), which places them around `y = 8990`. A single future or unexpected role can cause graph fitting to shrink all normal nodes into near invisibility.

The graph also renders its empty wrapper even after displaying `No topology available`, and duplicate hostnames or link IDs overwrite entries in plain object maps.

### 20. Appearance preference is not persisted

The selected code-highlighting theme lives only in a non-persisted Pinia ref in [ui/src/stores/generic.store.ts:9](ui/src/stores/generic.store.ts#L9). Although it is presented as an application setting, it resets after a reload.

### 21. Toast removal is delayed for roughly 16.7 minutes

Closed toasts use a removal delay of `1_000_000` milliseconds in [ui/src/components/ui/toast/use-toast.ts:5](ui/src/components/ui/toast/use-toast.ts#L5). Visible toast count is bounded, but dismissed toast objects and timers can accumulate during an error-heavy session.

### 22. The root application runs an unnecessary permanent interval

`intro` starts as `false`, but [ui/src/App.vue:19](ui/src/App.vue#L19) still starts a 500-millisecond interval that continually updates the unused loading dots for the lifetime of the application.

### 23. Routing and form polish issues

- Two catch-all routes are declared, making the second redundant in [ui/src/router.ts:46](ui/src/router.ts#L46).
- Login and signup fields lack useful required/minimum validation.
- Several labels target the wrong field IDs.
- Signup password confirmation is unused.
- Authentication error paths log generic values to the browser console.
- The persisted user store starts with a fake profile and expired timestamp in [ui/src/stores/user.store.ts:4](ui/src/stores/user.store.ts#L4).

## Verification and quality gates

### Build

`npm run build` passes, including `vue-tsc` and the Vite production build.

The build reports:

- A main JavaScript bundle of roughly 1.10 MB minified and 365 KiB gzip.
- Multiple large Shiki language chunks.
- A chunk-size warning.
- An outdated Browserslist database warning.

### Lint

`npm run lint` fails with 67 errors and zero warnings.

Most errors are generated UI-wrapper unused-destructure or explicit-`any` findings, but behaviorally relevant errors include:

- Missing conversation-row key in `ChatSidebar.vue`.
- Three missing keys in `ChatListTool.vue`.
- Unsafe `any` usage in stream parsing and state error handling.
- Constant-loop lint failures in the SSE parser.

### Tests

There is no frontend test script or checked-in component/E2E test suite in [ui/package.json:6](ui/package.json#L6). The identified races therefore have no automated regression coverage.

High-value missing tests include:

- Switching conversations during a stream.
- Two concurrent sends.
- Out-of-order conversation and search responses.
- Switching conversations during attachment upload.
- Truncated SSE without a `done` event.
- Database message IDs greater than 1000.
- Tool-name and tool-result normalization.
- Mobile sidebar/history access.

### Rendering security

Markdown rendering is comparatively well protected. Raw HTML is disabled and output passes through DOMPurify in [ui/src/lib/markdown.ts:57](ui/src/lib/markdown.ts#L57), so the audit did not find an obvious assistant-message XSS path.

A live third-party dependency/CVE audit was not performed as part of this application-logic review.

## Recommended remediation order

1. Replace the backend placeholder identity and enforce authorization server-side; add matching frontend route and Admin capability gates.
2. Give each stream immutable conversation/request ownership and add cancellation when switching conversations.
3. Sequence or cancel conversation, search, prompt-preview, and attachment requests; reject stale responses.
4. Capture the initiating conversation ID before attachment reads and validate file size before `file.text()`.
5. Disable the composer while no conversation is ready, while syncing/uploading, or while the single supported stream is active.
6. Require a valid SSE `done` event, surface malformed/truncated streams, add abort support, and configure nginx for SSE.
7. Normalize tool names and output shapes at one frontend boundary, then remove fabricated diff metadata.
8. Replace numeric temporary-ID heuristics with explicit stable client IDs and persisted-state flags.
9. Add regression tests for the high-severity races before broader UI cleanup.
10. Address mobile navigation, rendering performance, hardcoded status data, and the remaining lint failures.

# Backend Audit Findings

Audit date: 2026-08-14

Scope: FastAPI routing and authorization, chat and skill persistence, agent orchestration, streaming and cancellation, context management, connector tools, observability, migrations, SQLite behavior, Docker/Ansible deployment, dependency security, and backend quality gates. The backend review was read-only; only this audit file was changed.

## Severity summary

- Critical: 4
- High: 12
- Medium: 9
- Lower severity: 5 grouped findings

The most urgent problems are the placeholder administrator identity, missing conversation ownership checks, unrestricted infrastructure-tool access, and a migration graph that prevents the documented deployment commands from starting the backend.

## Critical

### 1. Authentication is a hardcoded administrator stub

The authentication dependency ignores the request and always returns user ID `0` with the `admin` role in [backend/app/core/security.py:15](backend/app/core/security.py#L15). Startup then creates that same demo administrator in [backend/app/db/init_db.py:64](backend/app/db/init_db.py#L64).

There is no token, session, SSO assertion, trusted-header, or upstream identity validation in the backend. Consequently, every endpoint using `CheckUserSSODep` treats every reachable caller as the same administrator. Role checks on admin feedback and skill-marketplace moderation therefore provide no security.

Impact:

- Every reachable caller is an administrator.
- All callers share one conversation, settings, feedback, and skill identity.
- Admin-only feedback and marketplace operations are public in practice.
- Adding frontend route guards cannot fix this because the missing boundary is server-side.

### 2. Conversation and message operations do not enforce ownership

The shared conversation lookup filters only by conversation ID and archive state in [backend/app/api/endpoints/chat.py:167](backend/app/api/endpoints/chat.py#L167); it never checks `Conversation.user_id`.

The authorization gap covers nearly the entire chat lifecycle:

- `GET /conversation/{id}` has no user dependency and returns messages, feedback, agent runs, prompts, tool inputs, and tool outputs in [backend/app/api/endpoints/chat.py:542](backend/app/api/endpoints/chat.py#L542).
- Attachment listing has no user dependency in [backend/app/api/endpoints/chat.py:658](backend/app/api/endpoints/chat.py#L658); upload and delete accept a user but explicitly ignore it in [backend/app/api/endpoints/chat.py:674](backend/app/api/endpoints/chat.py#L674) and [backend/app/api/endpoints/chat.py:737](backend/app/api/endpoints/chat.py#L737).
- Synchronous asks, prompt previews, and streaming asks call the ownership-blind helper in [backend/app/api/endpoints/chat.py:755](backend/app/api/endpoints/chat.py#L755), [backend/app/api/endpoints/chat.py:874](backend/app/api/endpoints/chat.py#L874), and [backend/app/api/endpoints/chat.py:903](backend/app/api/endpoints/chat.py#L903).
- Feedback checks only the message ID and role in [backend/app/api/endpoints/chat.py:1070](backend/app/api/endpoints/chat.py#L1070).
- Rename and both delete aliases have no user dependency at all in [backend/app/api/endpoints/chat.py:1123](backend/app/api/endpoints/chat.py#L1123), [backend/app/api/endpoints/chat.py:1136](backend/app/api/endpoints/chat.py#L1136), and [backend/app/api/endpoints/chat.py:1148](backend/app/api/endpoints/chat.py#L1148).

Random URL-safe IDs reduce guessing but are not authorization. Anyone who obtains a conversation or message ID can read it, archive it, rename it, add or remove attachments, submit feedback, preview its full prompt stack, or run an expensive agent against it. The public metrics issue below also discloses these otherwise-random IDs.

### 3. Agent tools have no user authorization boundary and can expose infrastructure secrets

`POST /agent/ask` has no authentication dependency in [backend/app/api/endpoints/agent.py:11](backend/app/api/endpoints/agent.py#L11). The normal chat workflow passes no user or entitlement information into `run_agent` in [backend/app/workflows/agent_runner.py:567](backend/app/workflows/agent_runner.py#L567), while the orchestrator always receives every specialist in [backend/app/agents/orchestrator_agent.py:53](backend/app/agents/orchestrator_agent.py#L53). The intended [backend/app/policy_engine.py](backend/app/policy_engine.py) is empty.

When live integrations are enabled, all users therefore operate shared service credentials for Zabbix, ServiceNow, Bitbucket, SuzieQ, ClickHouse, and Qdrant. There is no per-user connector entitlement, host/site scope, purpose check, approval flow, or output classification.

One concrete secret path is `zabbix_get_host_details`: it requests host macros and returns each raw macro value in [backend/app/tools/zabbix_tools.py:732](backend/app/tools/zabbix_tools.py#L732). Zabbix macros frequently contain communities, passwords, tokens, or other sensitive configuration. The values can then be sent to Gemini, persisted in `ToolCall.output`, exposed through the conversation API, and copied into traces.

The tools are predominantly read-only, which limits integrity impact, but the confidentiality and credential-exposure impact is still critical.

### 4. The migration graph has two heads, so official startup commands fail

The repository currently has two Alembic heads:

- `9f1c2d4a6b77`, branched from the attachment migration in [backend/alembic/versions/9f1c2d4a6b77_add_tool_call_latency_ms.py:17](backend/alembic/versions/9f1c2d4a6b77_add_tool_call_latency_ms.py#L17)
- `d4b2a7f3c981`, reached through the marketplace branch in [backend/alembic/versions/d4b2a7f3c981_add_user_custom_instructions.py:17](backend/alembic/versions/d4b2a7f3c981_add_user_custom_instructions.py#L17)

Both supported deployment paths run `alembic upgrade head`:

- Docker Compose: [docker-compose.yaml:83](docker-compose.yaml#L83)
- Ansible: [ansible/roles/netai/tasks/main.yml:97](ansible/roles/netai/tasks/main.yml#L97)

Alembic rejects that command with `Multiple head revisions are present for given argument 'head'`. This was reproduced with an offline `upgrade head --sql`, so a fresh Compose start enters a restart loop and an Ansible deployment aborts before starting the API. A merge revision is required; changing the command to `heads` would apply both branches but would not repair the migration graph.

## High

### 5. Public request insights disclose conversation IDs and provide a memory-DoS path

FastAPI Insights is mounted without authentication at `/insights` in [backend/app/main.py:44](backend/app/main.py#L44). In the installed `fastapi-insights 0.1.2`, the middleware records the literal `request.url.path`, and its public routes expose the collected JSON/table data and a `DELETE /insights/reset` operation.

This creates two linked problems:

- Paths such as `/api/v1/llm/conversation/<random-id>` place the conversation ID in a public metrics feed. Combined with issue 2, the feed becomes a directory of readable conversations.
- Metrics are keyed by raw path rather than the route template. An attacker can generate arbitrary unique 404 paths, creating four sets of per-path latency buckets until hourly cleanup. The installed store's memory-safety helper is not called by request recording.

The separate Prometheus `/metrics` endpoint is also public in [backend/app/main.py:62](backend/app/main.py#L62), although its default process metrics are less sensitive.

### 6. Synchronous agent runs block the only application event loop

The non-streaming workflow calls the synchronous Haystack `Agent.run` directly from an `async` endpoint: `_run_agent` only offloads when `run_in_thread=True` in [backend/app/workflows/agent_runner.py:87](backend/app/workflows/agent_runner.py#L87), while `run_agent` uses the default `False` in [backend/app/workflows/agent_runner.py:567](backend/app/workflows/agent_runner.py#L567). The public `/agent/ask` endpoint also invokes it directly in [backend/app/api/endpoints/agent.py:23](backend/app/api/endpoints/agent.py#L23).

Both Docker and Ansible start one Uvicorn worker. A single slow LLM call, connector timeout, mock-tool sleep, or ten-step agent run can therefore stop every chat, API, metric, and readiness request handled by that process.

There is also no application-level rate limit, per-user concurrency limit, LLM timeout, request budget, or token/spend quota. The unauthenticated agent endpoint makes both event-loop denial of service and uncontrolled model spend straightforward.

### 7. Slow or disconnected streams can leak workers, memory, traces, and incomplete turns

Streaming starts a synchronous agent in a thread and feeds an unbounded `asyncio.Queue` in [backend/app/workflows/agent_runner.py:617](backend/app/workflows/agent_runner.py#L617). A slow network consumer applies backpressure to the response generator while the worker thread continues using `put_nowait`, so queued tokens can grow without a bound.

Cancellation is incomplete:

- Cancelling an `asyncio.to_thread` task does not stop the underlying LLM/tool thread.
- The runner's `finally` resets context variables but does not stop or drain that thread in [backend/app/workflows/agent_runner.py:623](backend/app/workflows/agent_runner.py#L623).
- The endpoint commits the user message before starting the generator in [backend/app/api/endpoints/chat.py:925](backend/app/api/endpoints/chat.py#L925).
- The generator catches `Exception`, but cancellation uses `CancelledError`, so the trace/span and assistant persistence paths can be skipped in [backend/app/api/endpoints/chat.py:943](backend/app/api/endpoints/chat.py#L943).

After a disconnect, the backend can continue paying for the agent and filling an unconsumed queue while leaving a user message with no assistant response. Synchronous agent failures create the same incomplete persisted turn because they also commit the user message before running the agent.

### 8. Full prompt and tool content is traced to a local file that can be baked into images

Haystack content tracing is enabled unconditionally in [backend/app/llm.py:21](backend/app/llm.py#L21), with component inputs and outputs written to `backend/haystack_tracing.log` through a rotating handler configured in [backend/app/llm.py:16](backend/app/llm.py#L16). The streaming runner additionally prints the full run map to stdout in [backend/app/workflows/agent_runner.py:653](backend/app/workflows/agent_runner.py#L653).

At audit time, the trace file was approximately 1.1 MB, mode `0664`, and already contained dozens of component input/output records. Those records can include user prompts, custom instructions, attachment contents, summaries, infrastructure configuration, incidents, syslogs, tool arguments, tool results, and macro values.

The file is Git-ignored but not Docker-ignored: [backend/.dockerignore:1](backend/.dockerignore#L1) omits `.env`, the database, and the virtual environment, but not `*.log`; [backend/Dockerfile:17](backend/Dockerfile#L17) then copies the whole backend context. A locally built production image can therefore permanently contain historical trace data in an image layer.

### 9. Plausible mock infrastructure data is the default, and topology is always fake

`TOOLS_USE_MOCK_DATA` defaults to `True` in [backend/app/core/config.py:82](backend/app/core/config.py#L82), and the supplied environment skeleton explicitly enables it in [backend/.env.skeleton:29](backend/.env.skeleton#L29). The Ansible backend defaults do not override it. Zabbix, ServiceNow, SuzieQ, Bitbucket, and syslog specialists can consequently return realistic but fabricated incidents, devices, metrics, changes, and configurations in a deployment that appears operational.

The datamodel specialist is never switched to a live source. It imports `get_known_fake_devices` directly in [backend/app/agents/datamodel_agent.py:7](backend/app/agents/datamodel_agent.py#L7), backed by the static `_FAKE_DEVICES` inventory in [backend/app/tools/datamodel_tools.py:5](backend/app/tools/datamodel_tools.py#L5), even when global mock mode is disabled.

The console banner is not a reliable safeguard: it is evaluated against the class-body default before environment settings are instantiated in [backend/app/core/config.py:84](backend/app/core/config.py#L84), so it prints `USING MOCK DATA` even when live mode is configured.

For a network-operations product, unlabeled mock evidence can cause incorrect operational decisions and should fail closed outside an explicit demo environment.

### 10. Normal-length conversations silently lose all context older than ten messages

`build_conversation_context` loads every active message, then immediately keeps only the last `RECENT_MESSAGE_WINDOW` (10) messages in [backend/app/workflows/context_manager.py:192](backend/app/workflows/context_manager.py#L192). It estimates tokens from that truncated tail and triggers summarization only if the tail itself exceeds 80% of the context window in [backend/app/workflows/context_manager.py:228](backend/app/workflows/context_manager.py#L228).

For a typical conversation whose last ten messages are below 80, messages 11 and older are omitted without ever being summarized. The assistant therefore begins forgetting context after roughly five user/assistant turns even though the UI still displays the complete history and the configured window is 100,000 tokens.

If the last ten messages do exceed the threshold, compaction occurs, but the rebuilt prompt is not checked or reduced again after adding the summary, attachments, custom instructions, skill instructions, formatting instructions, and tool schemas.

### 11. LLM configuration is internally inconsistent and breaks clean setups

The documented local setup tells users to place `GEMINI_API_KEY` in `backend/.env` and launch with `uv run uvicorn` in [README.md:83](README.md#L83). Pydantic reads that value into `project_settings`, but [backend/app/llm.py:32](backend/app/llm.py#L32) does not pass it to `GoogleGenAIChatGenerator`; the generator reads only the process environment. `uv run` does not export values from this `.env`, so a clean documented startup fails while importing the app with a missing-key `ValueError`.

The tests mask this by inserting a fake process-environment key before importing the application in [backend/tests/conftest.py:12](backend/tests/conftest.py#L12).

Additional configuration failures:

- The default main model is literally `GEMINI_MODEL` in [backend/app/core/config.py:61](backend/app/core/config.py#L61).
- Neither [backend/.env.skeleton](backend/.env.skeleton) nor [ansible/roles/netai/defaults/main.yml:24](ansible/roles/netai/defaults/main.yml#L24) defines the actual `GEMINI_MODEL`, so environment-file deployments reach the invalid literal unless operators discover and add it.
- `LOG_QA_PROVIDER`, `LOG_QA_MODEL`, and `OPENAI_API_KEY` are presented as supported settings, but the application always constructs the global Google generator; selecting OpenAI has no effect.
- The skeleton duplicates `GEMINI_API_KEY` in [backend/.env.skeleton:24](backend/.env.skeleton#L24).

### 12. Request, prompt, context, and stored-output sizes are not bounded end to end

Core request schemas have no useful length limits: `MessageCreate.content`, custom instructions, attachment JSON fields, feedback comments, and conversation titles are unrestricted in [backend/app/api/schemas/chat.py:19](backend/app/api/schemas/chat.py#L19). The `/agent/ask` question has a minimum but no maximum in [backend/app/api/schemas/agent.py:4](backend/app/api/schemas/agent.py#L4).

Attachment byte limits are applied only after FastAPI/Pydantic has parsed the full JSON body and Python has normalized and encoded the content in [backend/app/services/chat_attachments.py:75](backend/app/services/chat_attachments.py#L75). Direct access to port 8000 has no body-size middleware.

Prompt construction compounds the problem:

- A user can invoke many enabled skills, each allowing 50,000 instruction characters.
- Custom instructions have no maximum.
- The context window is reported as a metric, not enforced after runtime additions.
- Tool schemas and tool outputs are not included accurately in the preflight limit.
- Tool outputs are persisted without a size cap and returned again through conversation/admin APIs.

This permits memory pressure, context-overflow errors, unexpectedly expensive model calls, oversized SQLite rows, and very large API/SSE responses.

### 13. The installed backend environment has many known dependency vulnerabilities

`pip-audit` against the installed `.venv` reported 85 vulnerability records across 17 packages. Affected runtime packages include Starlette, `python-multipart`, MCP, `aiohttp`, Authlib, `cryptography`, PyJWT, Requests, urllib3, `pydantic-settings`, and transitive parsing/network packages.

Examples from the audit include:

- `starlette 0.52.1`
- `mcp 1.27.0`
- `python-multipart 0.0.26`
- `aiohttp 3.13.2`
- `cryptography 46.0.5`
- `pydantic-settings 2.13.1`

The result needs applicability and compatibility triage rather than blind upgrades, but it is not safe to ship the current lock without review. `pytest` is also declared as a production dependency in [backend/pyproject.toml:7](backend/pyproject.toml#L7), increasing the runtime image surface unnecessarily.

### 14. Concurrent writes can mix turns, exceed quotas, and create duplicate data

There is no per-conversation lock, request idempotency key, message sequence, or active-run constraint. Two sends can both commit their user messages, then each build context containing an unpredictable combination of both requests, and finally persist assistant replies in completion order. The frontend currently permits overlapping sends, so this is reachable behavior rather than a theoretical multi-client case.

Other check-then-write races include:

- Attachment count/total checks followed by a separate insert in [backend/app/api/endpoints/chat.py:695](backend/app/api/endpoints/chat.py#L695).
- Skill name and slug lookups followed by inserts, while the associated indexes are non-unique in [backend/app/api/models/skills.py:15](backend/app/api/models/skills.py#L15).
- Marketplace listing creation with no unique owner-skill constraint.
- Feedback delete-then-insert replacement in [backend/app/api/endpoints/chat.py:1092](backend/app/api/endpoints/chat.py#L1092).
- Concurrent title generation and context compaction with last-writer-wins behavior.

The default SQLite connections also do not enable `PRAGMA foreign_keys`; the audit observed `foreign_keys=0`. Even declared message/run/attachment foreign keys are therefore unenforced. `Conversation.user_id`, `Feedback.user_id`, and `Skill.installed_from_listing_id` have no foreign key in the model at all in [backend/app/api/models/chat.py:56](backend/app/api/models/chat.py#L56), [backend/app/api/models/chat.py:309](backend/app/api/models/chat.py#L309), and [backend/app/api/models/skills.py:35](backend/app/api/models/skills.py#L35).

### 15. Live connector boundaries contain transport, injection, and hanging-operation risks

Several connector-specific defects become important as soon as mock mode is disabled:

- SuzieQ TLS verification defaults to `False` in [backend/app/tools/suzieq_tools.py:60](backend/app/tools/suzieq_tools.py#L60), even though its fallback URL is HTTPS. Its API token is placed in the URL query string in [backend/app/tools/suzieq_tools.py:90](backend/app/tools/suzieq_tools.py#L90); HTTP errors can then copy the full token-bearing URL into tool output and traces.
- ServiceNow encoded queries interpolate user/LLM-controlled strings directly, for example in [backend/app/tools/servicenow_tools.py:631](backend/app/tools/servicenow_tools.py#L631). Characters such as `^`, `^OR`, and `^NQ` can alter the intended query and broaden record access unless values are encoded or allowlisted.
- `BITBUCKET_ENABLED` exists in settings but is never checked by the live Bitbucket tools. Every tool call performs a fetch/pull against the same checkout in [backend/app/tools/bitbucket_tools.py:155](backend/app/tools/bitbucket_tools.py#L155), and `subprocess.run` has no timeout or non-interactive credential environment in [backend/app/tools/bitbucket_tools.py:42](backend/app/tools/bitbucket_tools.py#L42). Expired credentials can hang a worker, and concurrent calls can contend on Git locks.

The Zabbix, ServiceNow, SuzieQ, and syslog HTTP clients otherwise do set finite per-request timeouts, which limits some failure modes.

### 16. The supplied deployment profile is unsafe on an untrusted host network

The root Compose file publishes Kafka, Qdrant, ClickHouse, Redis, the backend, and the UI on all host interfaces in [docker-compose.yaml:1](docker-compose.yaml#L1). Kafka is plaintext, Redis and Qdrant have no configured authentication, and ClickHouse uses `admin/admin` in [docker-compose.yaml:42](docker-compose.yaml#L42). The Qdrant image is also unpinned as `latest`.

The Ansible nginx template listens on plain HTTP and contains no TLS configuration in [ansible/roles/netai/templates/netai-nginx.conf.j2:1](ansible/roles/netai/templates/netai-nginx.conf.j2#L1). If TLS and network controls are not supplied externally, chat content, connector evidence, and future authentication material cross the network in cleartext.

This Compose profile may be intended for local development, but it is the primary root deployment file and is not guarded against use on a remotely reachable machine.

## Medium

### 17. Conversation recency and message ordering are not maintained reliably

Conversations are sorted by `Conversation.updated_at` in [backend/app/api/endpoints/chat.py:505](backend/app/api/endpoints/chat.py#L505), but adding a message or attachment does not update the parent conversation row. After the initial title generation, subsequent activity does not move a chat to the top unless the title, archive flag, or another conversation column happens to change.

The `Conversation.messages` relationship has no `order_by` in [backend/app/api/models/chat.py:60](backend/app/api/models/chat.py#L60), and `get_conversation` does not explicitly sort loaded messages. SQLite often returns insertion order by accident, but SQL does not guarantee it. A different query plan or database can return a scrambled transcript.

### 18. API validation disagrees with normalization and database column sizes

Several values pass schema validation and become invalid only after `.strip()` or at commit time:

- Skill names and instructions accept whitespace-only strings because Pydantic validates before endpoint code strips them in [backend/app/api/endpoints/skills.py:332](backend/app/api/endpoints/skills.py#L332).
- Skill descriptions allow 5,000 characters in [backend/app/api/schemas/skills.py:13](backend/app/api/schemas/skills.py#L13), while both database columns are `String(240)` in [backend/app/api/models/skills.py:29](backend/app/api/models/skills.py#L29) and [backend/app/api/models/skills.py:60](backend/app/api/models/skills.py#L60).
- Conversation titles, attachment filenames, and content types have no schema maximum despite `String(255)`/`String(120)` columns.
- Slug and imported-name suffixes are appended after taking an 80-character base, so collision handling can exceed the `String(80)` columns.

SQLite does not enforce declared `VARCHAR` lengths, which is why tests pass; PostgreSQL/MySQL-style databases can reject these writes with 500 errors.

### 19. `/agent/ask` extracts the wrong result shape and can return a dump of the entire run

The endpoint looks for a top-level `replies` list in [backend/app/api/endpoints/agent.py:27](backend/app/api/endpoints/agent.py#L27). The installed Haystack `Agent.run` returns `messages` and `last_message`, so that branch normally misses and the endpoint falls back to `str(result)` in [backend/app/api/endpoints/agent.py:33](backend/app/api/endpoints/agent.py#L33).

The client can receive a Python representation of the full execution state and tool messages instead of the final answer. That response can be very large and expose intermediate evidence. `top_k` is accepted and traced but never used, while capability, confidence, and fallback fields are hardcoded.

### 20. Live prompts do not match their advertised roles or prompt preview

Runtime skill and formatting prompts are appended as additional system messages after the current question in [backend/app/workflows/agent_runner.py:482](backend/app/workflows/agent_runner.py#L482). The installed Google generator treats only the first system message as the real system instruction; later system messages are converted to user messages. Selected-skill instructions and formatting rules therefore have different precedence and ordering than the snapshot reports.

There is a second mismatch when a leading `/skill` command is removed. The stored message contains the original slash command, but attachment/custom-instruction insertion compares it with the normalized question. On mismatch, `_insert_before_latest_question` leaves the raw message and appends a second normalized copy in [backend/app/workflows/agent_runner.py:169](backend/app/workflows/agent_runner.py#L169). Without an attachment or custom instruction, the normalized version may not be inserted at all.

Prompt preview builds from an unpersisted normalized draft, so it does not reproduce this live shape. Debugging the preview can therefore show a different prompt from the one sent to Gemini.

### 21. Conversation-title generation has race, lifecycle, and size problems

Streaming schedules title generation with an untracked bare `asyncio.create_task` in [backend/app/api/endpoints/chat.py:1056](backend/app/api/endpoints/chat.py#L1056). The task is not retained, drained during shutdown, or tied to application lifecycle. Its database lookup and trace creation occur before its internal `try`, so early failures can become unobserved task exceptions in [backend/app/api/endpoints/chat.py:388](backend/app/api/endpoints/chat.py#L388).

Concurrent first responses can both observe a missing title and overwrite each other. The LLM output is stored without enforcing the database's 255-character limit. The synchronous chat endpoint waits for this second LLM call before returning even though the assistant message is already committed, adding latency and another unbounded failure point.

### 22. Delete endpoints retain all user and attachment content indefinitely

Both conversation delete routes only set `archived=True` in [backend/app/api/endpoints/chat.py:1136](backend/app/api/endpoints/chat.py#L1136). Attachment deletion only sets `active=False` in [backend/app/api/endpoints/chat.py:733](backend/app/api/endpoints/chat.py#L733).

Messages, summaries, raw attachment text, feedback, prompts, agent runs, and tool results remain in plaintext storage with no purge endpoint or retention policy. Soft deletion can be intentional, but the public API calls the operation `DELETE`, so the retention semantics should be explicit and a real erasure path should exist where privacy requirements demand it.

### 23. Full-history and admin responses have no practical pagination boundary

`get_conversation` loads the complete message history and every nested agent run, child run, tool call, and feedback record in [backend/app/api/endpoints/chat.py:549](backend/app/api/endpoints/chat.py#L549). Conversation lists, skills, and marketplace listings are also unpaginated.

Admin feedback has a row limit, but each feedback row reserializes the associated assistant graph and tool outputs in [backend/app/api/endpoints/chat.py:576](backend/app/api/endpoints/chat.py#L576). Multiple feedback types are stored as separate rows for the same message, so the same large graph can be repeated several times in one response.

Long conversations or output-heavy tools can consequently create multi-megabyte responses and large serialization/query spikes.

### 24. Database configuration claims portability but contains SQLite-only behavior and schema drift

The engine always passes `check_same_thread=False` in [backend/app/db/session.py:15](backend/app/db/session.py#L15). That option is SQLite-specific and will be rejected by other drivers, while no production database driver such as `asyncpg` is declared. `SQLALCHEMY_URL` therefore appears generic but the runtime is effectively SQLite-only.

`alembic check` also fails: model metadata expects an `ix_skill_marketplace_listing_owner_user_id` index that the migrations do not create. This drift is smaller than the two-head failure but confirms the migration state is not clean.

### 25. Readiness and SSE transport behavior are not production-hardened

There is no backend healthcheck in Compose, and the UI waits only for `service_started` in [docker-compose.yaml:135](docker-compose.yaml#L135). The system version endpoint does not verify the database, model configuration, or required dependencies.

The streaming response sets only `text/event-stream` in [backend/app/api/endpoints/chat.py:1064](backend/app/api/endpoints/chat.py#L1064). It sends no heartbeat, `Cache-Control: no-cache`, or `X-Accel-Buffering: no`. Neither nginx template disables proxy buffering or sets a suitable long read timeout. A long specialist/tool phase before the first token can therefore be buffered or terminated by an intermediary even when the backend is still working.

## Lower-severity issues

### 26. Stale routes, entrypoints, and documentation obscure real behavior

- Five public `/example` routes are registered but return `null` in [backend/app/api/endpoints/items.py:3](backend/app/api/endpoints/items.py#L3).
- README API examples still advertise an unregistered `/logs/ask` route in [README.md:192](README.md#L192).
- `make cli` points to a nonexistent root `cli.py`, while [backend/app/cli.py](backend/app/cli.py) is empty.
- [backend/app/OpenAILLM.py:213](backend/app/OpenAILLM.py#L213) performs an LLM call at import time if that otherwise-dead module is ever imported.
- Several configuration fields, including the documented OpenAI/log-QA provider selection, are dead code.

### 27. The unused scoped-session factory would share one session across every task

`AsyncScopedSession` uses `scopefunc=lambda: None` in [backend/app/db/session.py:23](backend/app/db/session.py#L23). If any future code starts using it, all requests resolve to the same scope and therefore the same async session, causing cross-request transaction corruption. It is currently unused, so this is latent rather than active.

### 28. The security specialist claims advisory/CVE capability without evidence tools

The security specialist says it can assess obsolete versions, CVEs, vendor advisories, and standards in [backend/app/agents/security_agent.py:6](backend/app/agents/security_agent.py#L6), but its tool list is empty. It can only answer from model memory, which is not a reliable source for current security exposure. Responses should either be constrained to general hardening guidance or backed by a current advisory source.

### 29. Context compaction can archive system messages it explicitly excludes from summaries

Compaction excludes system messages when choosing and formatting the summary input, but its archive update filters only by conversation and message ID in [backend/app/workflows/context_manager.py:169](backend/app/workflows/context_manager.py#L169). Any persisted system message below the cutoff is archived without being represented in the summary.

No current endpoint creates persisted system messages, so this becomes active only if that feature is added or existing data contains them.

### 30. Passing tests omit the highest-risk boundaries

The suite does not cover:

- Real authentication or role resolution.
- Cross-user conversation, message, attachment, prompt-preview, and feedback access.
- The unauthenticated agent endpoint's real result shape.
- Clean-database `alembic upgrade head`.
- Application import using only the documented `.env` setup.
- Client disconnects, slow SSE consumers, queue bounds, or worker cancellation.
- Two simultaneous sends or concurrent attachment/skill writes.
- Automatic context compaction across an ordinary long conversation.
- Live connector authorization, redaction, TLS, query injection, and timeouts.
- Production behavior with mock mode disabled.

The live ServiceNow, SuzieQ, and datamodel test modules contain TODO placeholders rather than connector-behavior tests.

## Verification and quality gates

### Tests

`uv run pytest -q` passes: 77 tests passed in approximately 82 seconds.

The run emits one FastAPI deprecation warning for `HTTP_422_UNPROCESSABLE_ENTITY`.

### Lint and type checking

- `uv run ruff check .` passes with the repository's current/default rule selection.
- `.venv/bin/mypy app --check-untyped-defs` passes all 73 backend source files.
- A supplemental `ruff check app --select S` reports 10 security-rule findings, including string-built ClickHouse queries, the Git subprocess call, all-interface binding, and swallowed exceptions. The ClickHouse values inspected in this audit are escaped and the database name comes from configuration, so the static warning is not by itself proof of exploitable SQL injection.

### Migrations and database

- `alembic heads` reports two heads: `9f1c2d4a6b77` and `d4b2a7f3c981`.
- Offline `alembic upgrade head --sql` fails because of the two heads.
- `alembic check` fails because the owner-user marketplace index is absent from migrations.
- The default SQLite database reports `PRAGMA foreign_keys = 0`.

### Dependency audit

`uvx pip-audit --path .venv/lib/python3.13/site-packages` reports 85 known-vulnerability records across 17 installed packages. `pip-audit --locked` could not audit `uv.lock` directly, so the checked installed environment is the authoritative result for this workspace.

### Startup configuration probe

A child launched with the documented `uv run` path does not receive `GEMINI_API_KEY` from `backend/.env`. Importing `app.llm` without separately exporting the key fails during `GoogleGenAIChatGenerator` construction. The test suite does not reveal this because `tests/conftest.py` injects a test key first.

## Recommended remediation order

1. Implement real backend authentication, remove the production demo administrator, and enforce conversation/message ownership in one shared authorization helper.
2. Disable or authenticate `/agent/ask` and `/insights`; add per-user connector entitlements, least-privilege service accounts, and secret/output redaction before enabling live tools.
3. Add an Alembic merge revision, make `alembic check` clean, and add a clean-database migration test to CI.
4. Repair LLM configuration: pass the resolved secret explicitly, define a valid model in every template, and either implement or remove the advertised provider switch.
5. Turn mock mode into an explicit demo-only profile, label mock responses, and remove the permanently fake production topology path.
6. Offload all synchronous agent work, add timeouts/rate and spend limits, bound stream queues, and design cooperative cancellation/disconnect cleanup.
7. Disable content tracing by default, redact sensitive fields, remove the run-map print, protect trace files, and exclude all logs from Docker build contexts.
8. Fix context compaction so all omitted messages are summarized, then enforce the final prompt budget after skills, attachments, tool schemas, and custom instructions are included.
9. Add request/body/output limits, pagination, stable message sequencing, per-conversation concurrency control, database uniqueness constraints, and SQLite foreign-key enforcement or a production database.
10. Harden connectors and deployment networking, then add regression tests for ownership, concurrency, cancellation, migrations, live-mode configuration, and data redaction.
