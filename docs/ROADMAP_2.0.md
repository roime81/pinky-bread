# Pinky Bread 2.0 — Delivery Roadmap

Pinky Bread 2.0 is a product upgrade delivered in testable increments. Alpha 1 introduced the persisted company graph; Alpha 2 adds a request-driven workforce that plans goals, assigns and executes specialist work, convenes text meetings and records KPI measurements. Durable autonomous operations, authenticated multi-company governance and a production-ready company are still future milestones.

## Programme principles

1. PostgreSQL is canonical for company state, workflow records, relationships and events.
2. Valkey distributes notifications and supports coordination; it is never the only copy of important work.
3. Object storage contains files and deliverables; PostgreSQL holds metadata, ownership, checksums and retention references.
4. Agents operate against explicit company goals and permissions, not just the latest prompt.
5. An agent can contribute to many goals, and each assignment remains independently traceable.
6. Human approval is required for spending, legal commitments, external communications with material impact and other consequential actions.
7. Every runtime action must have an actor, timestamp, goal/task context, tool identity, result and trace reference.
8. The UI graph is generated from persisted state and event history, not from fabricated visual data.

## Phase 1 — Company graph foundation (Alpha 1)

- [x] Company charter and root graph node
- [x] Generic graph node and typed relationship persistence
- [x] Hash-linked append-only company events
- [x] Graph snapshot and event verification APIs
- [x] Valkey-backed graph notifications and SSE endpoint
- [x] Company graph as the default UI view
- [x] Goal / agent / work / meeting node creation
- [x] Node inspector and interactive relationship creation
- [x] Local and S3-compatible workflow artifact storage adapter
- [x] PostgreSQL pgvector extension enabled for future semantic memory
- [x] CI verification of Alpha 1 code branch (Compose runtime smoke test remains pending)

## Phase 2 — Identity, company boundaries and governance

- Integrate Keycloak OIDC login and secure session/token validation.
- Replace caller-supplied tenant and actor identifiers with claims from the authenticated identity.
- Enforce company membership and role-based access at every graph, workflow, artifact, event and approval endpoint.
- Add founder, company administrator, department lead, agent, reviewer and auditor permissions.
- Add agent capability grants and scoped credentials; agents receive only tools required for their assigned work.
- Integrate OpenBao or another open-source secrets manager; no credentials in YAML manifests or UI payloads.
- Add approval policies, separation of duties, policy decisions and immutable approval references.
- Add CSRF protections for browser-originated state changes and rate limiting for model/tool calls.

**Exit criteria:** cross-company access tests pass; unauthorized users cannot view or mutate graph records, artifacts or approvals; a human approver is an authenticated principal.

## Phase 3 — Durable agent workforce

- [x] Replace the request-driven dispatcher with LangGraph StateGraph job workflows.
- [x] Use PostgreSQL-backed `AsyncPostgresSaver` checkpoints keyed by durable job ID and test restart/resume semantics.
- [x] Persist reusable AI employee identities with role, persona, skills, local model selection, runtime mode, health/status and version in the company graph.
- [x] Implement a Head of Agents planning service using a local model API (or explicit mock planner) to decompose goals into validated work.
- [x] Bootstrap specialist agents for Strategy, Product, Technology, Marketing, Operations and Finance under the Head of Agents.
- [x] Persist assigned work nodes, owners, acceptance criteria, dependencies and many-to-many agent-to-goal relationships.
- [x] Add PostgreSQL queue rows with idempotency and one-active-job constraints, worker leases, heartbeats, fencing, retry/backoff and cancellation.
- [x] Recover expired worker leases and resume job execution through the same LangGraph checkpoint thread.
- [x] Add founder-controlled recurring `PLAN_ONLY` and explicitly enabled `AUTO_EXECUTE` coordination.
- [x] Store replay-safe deliverables and meeting minutes in the local/S3 object-store adapter.
- [ ] Add token/cost budgets, tenant/agent concurrency quotas, model/prompt/skill rollback and capacity-aware scheduling.

**Exit criteria:** a durable end-to-end goal is decomposed, assigned, executed, resumed after process loss, and reconciled without duplicate jobs, outputs or graph nodes.
## Phase 4 — Official tools and open integrations

- [x] Replace the workforce demo adapter with the official MCP Python SDK v2 and Streamable HTTP server/client.
- [x] Discover MCP tools dynamically and filter by agent role allow-list before exposing them to the local model API.
- [x] Inject company, tenant and agent identity from the runtime rather than model-generated tool arguments.
- [x] Require workforce:enqueue for MCP job submission; require founder-enabled AUTO_EXECUTE before MCP goal execution.
- [ ] Replace the static internal development bearer verifier with Keycloak/OIDC JWT/JWKS or introspection validation.
- [ ] Store tool definitions, grants, versions, approvals and execution receipts in the company database.
- [ ] Add sandboxed external connectors for email, calendar, documents, CRM and issue/work tracking.
- [ ] Keep commercial APIs optional behind pluggable interfaces; add integration health and credential rotation.

**Exit criteria:** an agent can discover only its granted tools, call an approved tool, record evidence and recover safely from timeout or duplicate submission.

## Phase 5 — Virtual workplace and meetings

- [x] Persist meeting agenda, meeting type, selected participants, facilitator, state, turn-by-turn contributions and completion timestamps.
- [x] Run a turn-based multi-agent text discussion and persist Markdown minutes in object storage with graph references.
- [ ] Add calendar scheduling, recurring stand-ups, scrum planning/review/retrospective templates and reminders.
- [ ] Allow the founder to join live by text; add optional local speech-to-text and text-to-speech later.
- [ ] Extract proposed decisions and action items into reviewable graph nodes and assignments.
- [ ] Add cross-department conflict escalation, commitment tracking and follow-up.

**Exit criteria:** a meeting produces reviewable decisions and traceable tasks; the meeting itself does not silently execute consequential actions.

## Phase 6 — Goal, KPI and work management

- Add goal hierarchy and alignment across company, department and team objectives.
- [x] Record KPI measurements with numeric value, target comparison, source, evidence, timestamp and a bounded measurement history.
- [x] Derive goal work-completion percentage from persisted assignment states.
- [ ] Add validated KPI definitions: formula, unit, target, threshold, reporting period, source and accountable owner.
- [ ] Add automated KPI collectors and time-series snapshots explainable from source events.
- [ ] Add due dates, recurrence, automatic blocker propagation, workload and agent capacity views.
- Support project plans, milestones, release gates and deliverable acceptance.
- Trace every result to its goal and the work and agents that produced it.
- Add planned-vs-actual budget and operational cost tracking.

**Exit criteria:** founder can inspect a goal, see agent contribution and delivery evidence, and explain KPI progress from persisted events.

## Phase 7 — Company memory and knowledge

- Build semantic memory using pgvector and a local embedding model.
- Scope memory by company, goal, project, agent and access policy.
- Add document ingestion, parsing, chunking, provenance and retention.
- Add citation-bearing retrieval for agent decisions and deliverables.
- Separate durable company facts, episodic meeting/work memory and short-lived task context.
- Add memory correction, expiry, export and deletion workflows.

**Exit criteria:** agents can retrieve relevant authorised company knowledge with provenance and cannot cross company boundaries.

## Phase 8 — Observability, resilience and operations

- Instrument APIs, agent runs, tools, meetings and model calls with OpenTelemetry traces.
- Publish operational metrics and logs to Prometheus and Grafana.
- Add alerts, dashboards, service-level objectives and runbooks.
- Add database migration management, backup/restore tests and disaster-recovery procedures.
- Add SeaweedFS lifecycle, replication and recovery policy for retained deliverables.
- [x] Add a separate workforce worker service with PostgreSQL-backed job state and Valkey wake-up coordination.
- [x] Configure Compose for horizontally scalable workers; PostgreSQL leases coordinate replicas.
- [ ] Add OpenTelemetry traces for job, graph, model and MCP calls; Prometheus metrics and Grafana dashboards.
- [ ] Add alerts, runbooks, backup/restore tests and disaster-recovery procedures.
- [ ] Add Valkey HA/persistence and SeaweedFS replication/retention policy where required.
- [ ] Add load testing, security tests, SBOM, dependency scanning and signed images.

**Exit criteria:** recovery and observability are tested under service, queue, model and storage failures.

## Definition of done for the 2.0 release

Pinky Bread 2.0 should not be called complete until:

- A founder can create a company charter and measurable goals.
- The Head of Agents can plan and delegate work across specialist agents.
- Agent identities and responsibilities persist across sessions and restarts.
- One agent can contribute to several goals with distinct assignments and progress.
- Agents can run meetings and create decisions and action items with attributable history.
- Workflows persist and resume safely after restart.
- The graph updates from real database events and supports reverse traceability.
- KPIs are calculated from defined, auditable sources.
- Documents and deliverables are stored as objects with database metadata and access controls.
- OIDC, company isolation, RBAC, approvals and tool scopes pass security tests.
- Local inference, memory retrieval and MCP tools work with documented open-source components.
- CI, Compose smoke tests, backup/restore and operational runbooks pass.

## Suggested next engineering slice

Alpha 3 adds durable job execution and a standards-based internal MCP boundary. The next priority is **Phase 2 identity and company boundaries**: replace caller-supplied tenant/actor IDs and static MCP tokens with Keycloak/OIDC, membership checks, RBAC and per-agent grants before exposing Pinky Bread to untrusted users or enabling consequential external tools. Then add budget/policy enforcement, operational telemetry and the first sandboxed MCP connectors.
