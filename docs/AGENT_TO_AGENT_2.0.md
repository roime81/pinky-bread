# Agent-to-agent conversations

Pinky Bread supports explicit colleague-to-colleague conversations between the founder-defined agents in a company. The A2A runtime preserves each agent's own profile, system instructions, role, model configuration and company context. It does not collapse participants into one shared chatbot persona.

## User experience

Open **Agent Conversations** from the workspace navigation. Enter a natural-language instruction in the composer.

Examples:

- \`Mira, say hello to Jamal.\`
- \`Mira, please discuss our marketing strategy with Jamal.\`
- \`Mira, ask Jamal to review the launch assumptions and report back.\`

When both participants are named, the first named agent initiates the conversation. When a single colleague is named in an instruction such as \`Please discuss with Jamal\`, the company's active \`COORDINATOR\` is used as the initiating agent. A coordinator is not silently invented: the request is rejected when no configured coordinator is available.

Greeting requests are intentionally bounded to one peer reply. Other discussions alternate between the initiating agent and the first recipient, up to the requested turn cap. The initiating agent then prepares a founder-facing summary. A future extension can add more participants and a meeting facilitator using the same conversation/message records.

## Runtime sequence

1. The API loads the company's active workforce and resolves named participants against real agent IDs in that company.
2. The conversation and the founder instruction are persisted before inference starts.
3. The initiating agent receives a bounded runtime context and returns an acknowledgement to the founder.
4. The initiating agent generates a message addressed to the colleague.
5. The recipient agent is invoked through the existing \`chat_with_agent\` adapter with its own role, instructions, responsibilities, model configuration and the peer transcript.
6. The agents exchange bounded messages. Each message is persisted and streamed to the browser using Server-Sent Events (SSE).
7. The initiating agent writes a founder-facing summary. The conversation is marked complete and the full transcript is available through the read APIs.

The message router controls who is invoked and when. An LLM proposes message content; it does not choose arbitrary agent IDs, execute direct network requests or bypass company scoping.

## Persistence and visibility

Two PostgreSQL tables are introduced:

- \`agent_conversations\`: company/tenant scope, initiator, participants, status, turn budget, summary, timestamps and error state.
- \`agent_conversation_messages\`: ordered messages, sender and recipient identity, message kind, content, SHA-256 content checksum, metadata and timestamp.

Conversation lifecycle and message-created events are appended to the existing hash-linked company event history. Conversation APIs are scoped by both company ID and tenant ID. Valkey is not required to deliver the SSE response; PostgreSQL is the durable source for listing and reloading completed or partially written conversations.

This initial delivery persists each completed message and streams the generation in the API request. It does not yet checkpoint an in-flight peer turn into the existing LangGraph worker queue, so a process restart during an LLM call may leave a conversation in \`RUNNING\`. A future durable conversation worker should add leases, resumable turn checkpoints, retry policy and cancellation.

## API

All paths are under \`/v2\`.

| Method | Path | Purpose |
|---|---|---|
| POST | \`/companies/{company_id}/conversations/stream\` | Resolve a natural-language instruction and stream conversation events |
| GET | \`/companies/{company_id}/conversations\` | List company conversations |
| GET | \`/companies/{company_id}/conversations/{conversation_id}\` | Load a conversation and ordered transcript |
| POST | \`/companies/{company_id}/chat\` | Existing chat endpoint; routes detected explicit A2A instructions through the new service for backwards compatibility |

The streaming endpoint emits JSON \`data:\` events. The \`type\` field is one of \`conversation_started\`, \`message\`, \`complete\` or \`error\`. Messages include sender, recipient, message kind and sequence number. The React frontend consumes the stream incrementally.

## Frontend

The collaboration experience is a React 18 application bundled with Vite and TypeScript. Framer Motion handles lightweight message/list transitions; Lucide React supplies consistent icons. It is built into \`web/a2a\`, then served by the existing FastAPI static mount. The company graph and other Alpha 4 screens remain available in the current application shell.

Run the frontend build locally before starting the Python API outside Docker:

\`\`\`bash
cd frontend
npm install
npm run build
\`\`\`

The Dockerfile performs the same build in a Node 22 build stage and copies the generated static assets into the Python image. The application remains served on the existing host port 8888.

## Controls and current boundaries

- Maximum configured discussion length is 12 turns; the default is 6.
- Greeting instructions are limited to a single peer reply.
- The initial flow supports one initiating agent and one recipient per discussion.
- Only active agents in the selected company can be resolved.
- Agent messages are persisted individually; the founder can reload the transcript.
- The runtime does not enable external tools or irreversible side effects merely because two agents are talking.
- Authentication and true company membership authorization remain subject to the existing Alpha 4 security boundary. Tenant IDs in current APIs are caller supplied and must not be treated as production authorization.
- The initial SSE execution is request-bound, not yet a checkpointed LangGraph conversation job.

