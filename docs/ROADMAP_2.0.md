# Pinky Bread 2.0 — Delivery Roadmap

**Release objective:** complete the founder-led, local-first AI Company Operating System on the architecture already present in the 2.0 Alpha line.

Pinky Bread 2.0 is the product foundation: a founder-owned company graph, persistent AI employees, accountable work, agent collaboration, meetings, company knowledge, controlled tools and recoverable execution. The priority is to make those capabilities safe, predictable, observable and useful before adding another layer of AI infrastructure.

## Version boundary

Pinky Bread 2.0 continues with the current stack:

- FastAPI and the existing React/TypeScript workspace
- PostgreSQL as the authoritative company, job, membership and event store
- LangGraph with PostgreSQL checkpoints for durable workforce orchestration
- Valkey for best-effort notifications and worker wake-ups
- SeaweedFS / S3-compatible object storage for source files and deliverables
- Ollama by default, with vLLM, OpenAI-compatible endpoints, OpenAI and Gemini as configurable model providers
- Official MCP Python SDK v2 for tool discovery and execution
- Existing company graph, agent profiles, workforce queue, meetings and A2A conversation capabilities

**Do not introduce LiteLLM, Langfuse, DSPy, CopilotKit, CrewAI, Agno, AgentScope or AutoGPT as 2.0 runtime dependencies.** They belong to the separately documented [Pinky Bread 3.0 future pipeline](ROADMAP_3.0.md). OpenTelemetry, Prometheus and Grafana remain appropriate 2.0 operational foundations because they address platform reliability rather than replacing the current agent and model architecture.

## Current baseline — 2.0 Alpha 4

Already implemented on the 2.0 line:

- Company graph with persisted nodes, typed relationships and hash-linked event history
- Founder-defined AI employee profiles, role, skills, responsibilities, model settings, seniority, authority and reporting lines
- Goal planning, delegated assignments, meetings, KPI measurement history and stored deliverables
- PostgreSQL-backed durable jobs, idempotency, worker leases, heartbeat, bounded retries and expired-lease recovery
- LangGraph StateGraph execution with PostgreSQL checkpoint persistence
- Valkey worker wake-up and live graph notifications, with PostgreSQL remaining authoritative
- Founder-controlled recurring coordination in PLAN_ONLY and explicitly enabled AUTO_EXECUTE modes
- MCP v2 Streamable HTTP server/client with role allow-lists and runtime-injected company/agent context
- Agent-to-agent conversations with each participant's own persona and model configuration
- React founder composer with multi-file document uploads and public cloud-share link ingestion
- Ollama-backed local inference by default in Docker Compose; configurable hosted model providers
- PostgreSQL, Valkey, SeaweedFS, API, worker, MCP and model services in Docker Compose

These features are an Alpha foundation, not a production security claim. The README's security boundaries remain authoritative until the relevant release gates below have passed.

## Programme principles

1. PostgreSQL is the source of truth for company state, membership, workflow records, relationships, jobs and event history.
2. Valkey is an acceleration and notification service, never the only copy of important work.
3. Object storage contains file bytes; PostgreSQL stores metadata, owner, company scope, checksum and retention references.
4. Company and agent identity must be established by the authenticated runtime, not trusted from model-generated arguments or caller-supplied tenant/actor fields.
5. Agents act against explicitly granted company goals, tasks and tools; a prompt is not an authorization mechanism.
6. Human approval is required for spending, legal commitments, consequential external communications and other irreversible actions.
7. Every meaningful runtime action must be traceable to a principal, company, goal/task, agent, model configuration, tool, result and timestamp.
8. Agent collaboration must be durable, bounded, attributable and recoverable.
9. Local inference must remain a first-class operating mode; commercial model providers remain optional.
10. Existing functionality must remain backward-compatible where practical and be covered by automated regression tests.

## Delivery workstreams

### 1. Identity, company boundaries and access governance — P0

This is the first engineering priority. The current development login and signed browser session are not a substitute for company membership authorization; request-supplied tenant and actor identifiers must not decide access.

- Implement a persistent user/principal record keyed by verified identity-provider issuer and subject.
- Retain local development sign-in for private single-user development, but make its limitations explicit and prevent it from being enabled in production configuration.
- Complete Google OAuth identity persistence and define the OIDC integration contract for additional identity providers.
- Persist company memberships and roles: founder/owner, administrator, department lead, agent, reviewer and read-only/auditor.
- Derive the current actor from the authenticated session or validated service identity.
- Enforce company membership and role checks on every company graph, chat, agent, job, meeting, KPI, event, artifact and approval endpoint.
- Enforce tenant/company isolation in MCP tool discovery and execution, not only in the UI.
- Authenticate approvers and enforce separation of duties for consequential actions.
- Add CSRF protection, secure cookie settings, session revocation/rotation, login throttling and credential-safe error handling.
- Add negative tests for cross-company reads, writes, downloads, event streams, job operations and approvals.

**Exit gate:** an authenticated user cannot read or change another company's graph, history, files, jobs, agents or approvals by altering request fields or URLs. The authorization decision is derived from verified identity and persisted membership.

### 2. Durable agent collaboration and workflow correctness — P1

The goal is for agents to collaborate like accountable employees, not transient chat personas.

- Move agent-to-agent conversations from request-bound streaming into durable workforce jobs.
- Persist conversation state, participants, messages, turn budget, checkpoints, retries, cancellation and final summary.
- Recover a conversation after API/worker restart without duplicating completed messages or losing the conversation timeline.
- Support explicit agent mentions, relevance-based workforce participation and bounded peer discussions.
- Persist meeting turns as they complete and resume interrupted meetings safely.
- Add meeting templates for stand-up, planning, review, retrospective and alignment sessions.
- Convert proposed decisions and action items into reviewable graph records; do not silently execute proposals.
- Add dependency-aware work scheduling, blocker propagation, deadlines and workload visibility.
- Add replay/idempotency tests for messages, meetings, generated deliverables and retries.

**Exit gate:** interrupted agent conversations, meetings and work can be recovered from durable state with no duplicate side effects or missing attributable messages.

### 3. Agent and model governance — P1

Use the existing provider adapter in 2.0; improve control and accountability without introducing a new model gateway.

- Add per-company, per-agent and per-job token and cost budgets.
- Add concurrency quotas, request limits, timeouts, retry limits and model fallback policy.
- Persist model provider, model identifier, endpoint reference, generation settings and model configuration version for every execution.
- Version agent instructions, tool grants and reusable skills.
- Support reviewed promotion and rollback of agent configuration and prompts.
- Record model latency, token usage where available, failures, retries and estimated cost.
- Prevent API keys and bearer tokens from appearing in graph payloads, logs, traces or browser responses.
- Expose provider readiness and capacity without revealing credentials.

**Exit gate:** a founder can set spending and concurrency limits, inspect the configuration used for an execution, and roll an agent back to a known-good profile.

### 4. Company knowledge and memory — P2

Turn company documents and previous work into governed, source-grounded knowledge.

- Implement the pgvector-backed embedding and retrieval pipeline using a configurable local embedding model.
- Parse, chunk and index supported documents with source metadata, checksum, company scope and retention policy.
- Support retrieval filters by company, department, goal, project, agent permission and document visibility.
- Separate durable company facts, episodic meetings/work history and short-lived task context.
- Return filename, page/section and source references with retrieved evidence.
- Add document versioning, re-indexing, deletion, expiry and correction workflows.
- Treat retrieved documents as untrusted source material; defend against prompt injection and cross-company retrieval.
- Add retrieval evaluation datasets for relevance, citation correctness and isolation.

**Exit gate:** an agent can answer from authorized company knowledge with source references, and automated tests prove that it cannot retrieve another company's documents.

### 5. Tool ecosystem and approvals — P2

Extend MCP carefully while preserving the current role-scoped model.

- Replace development static bearer validation with validated JWT/JWKS or a suitable OIDC authorization service.
- Persist MCP servers, tool metadata, versions, grants, execution receipts and approval requirements.
- Add sandboxed connectors for selected business systems, initially read-only where possible.
- Enforce per-agent and per-company tool grants at execution time.
- Require human approval for write actions with material business consequences.
- Add idempotency keys, timeout handling, rate limits and replay protection to external tool calls.
- Keep the existing simulated refund/ledger example simulated; never connect it to a real financial system.

**Exit gate:** an agent can discover and call only authorized tools, every call is attributable and replay-safe, and consequential actions require authenticated approval.

### 6. Platform observability and operational readiness — P2

Use portable open standards for 2.0 operations.

- Add OpenTelemetry traces across API requests, workforce jobs, LangGraph nodes, LLM calls, MCP calls and object storage operations.
- Propagate correlation IDs across founder request, company, goal, job, conversation and agent activity.
- Export service and worker metrics for queue depth, lease expiry, throughput, latency, errors and model usage.
- Add Prometheus collection and Grafana dashboards/alerts.
- Add structured logs with secret and sensitive-data redaction.
- Add runbooks for model outage, worker recovery, PostgreSQL/Valkey/object-store outage and job replay.
- Add PostgreSQL and SeaweedFS backup/restore drills; document retention and recovery objectives.
- Add dependency scanning, SBOM generation, image scanning and deployment configuration checks.
- Add load, soak, failure-injection and security tests for the Compose deployment.

**Exit gate:** operators can trace a user request end-to-end, identify failure location, recover durable work and restore data from tested backups.

## Recommended implementation sequence

| Increment | Work | Expected outcome |
|---|---|---|
| 2.0.1 | Identity, company membership, RBAC and tenant isolation | Secure company boundaries |
| 2.0.2 | Durable A2A conversations and meeting recovery | Resilient virtual workforce |
| 2.0.3 | Agent/model budgets, configuration versions and rollback | Governed AI employees |
| 2.0.4 | pgvector memory, document retrieval and citations | Company knowledge layer |
| 2.0.5 | MCP identity, grants, approvals and sandboxed connectors | Controlled tool ecosystem |
| 2.0.6 | OpenTelemetry, Prometheus, Grafana, backup/restore and release hardening | Operationally supportable 2.0 |

The increments may overlap where dependencies allow, but the identity and company-boundary release gate must precede multi-user exposure or consequential external integrations.

## Definition of done for Pinky Bread 2.0

Pinky Bread 2.0 is ready for a production-readiness review only when:

- A founder can create a company and define goals, KPIs, departments and a custom workforce.
- Agent identities and reporting relationships persist across sessions and restarts.
- The coordinator can plan, delegate, track dependencies and report progress.
- Agents can collaborate directly and hold meetings with durable, attributable transcripts.
- Workflows and conversations recover safely after API or worker failure.
- The graph updates from real persisted events and supports reverse traceability from outcomes to source work.
- Company documents are indexed and retrieved with provenance and access controls.
- Model and agent versions, budgets, costs, tools and approvals are visible and governed.
- OIDC-backed identity, company membership, RBAC and tenant isolation pass negative security tests.
- MCP grants and consequential approvals are enforced server-side.
- End-to-end tracing, operational dashboards, alerts, runbooks and backup/restore tests pass.
- The full CI suite and Docker Compose smoke tests pass; known limitations and deployment assumptions are documented.

Passing these gates does not by itself constitute regulatory certification or independent security assurance.

## Explicitly deferred to Pinky Bread 3.0

The following are future-pipeline items, not 2.0 prerequisites:

- LiteLLM as a dedicated multi-provider model gateway
- Langfuse as a dedicated LLM tracing, prompt-management and evaluation platform
- DSPy for systematic prompt/program optimisation
- CopilotKit for a deeper generative UI and agent interaction framework
- Comparative evaluation of CrewAI, Agno and AgentScope as alternative/specialist agent runtimes
- AutoGPT-inspired visual workflow/agent builder capabilities

See [Pinky Bread 3.0 — Future Pipeline](ROADMAP_3.0.md). The 2.0 codebase should preserve clean adapters and interfaces so these tools can be evaluated later without rewriting company data, identity, jobs or business rules.
