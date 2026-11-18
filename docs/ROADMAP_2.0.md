# Pinky Bread 2.0 — Delivery Roadmap

Pinky Bread 2.0 is a product upgrade delivered in testable increments. Alpha 1 lays down the persisted company graph and makes it the main UI. It does not claim that the Head of Agents, autonomous meetings or complete business operations are already implemented.

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
- [ ] CI verification of the feature branch and runtime Compose smoke test

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

- Replace the demo dispatcher with LangGraph StateGraph workflows.
- Use PostgreSQL-backed checkpoints and tested restart/resume semantics.
- Introduce a persistent Agent Runtime record: agent identity, role, persona, skills, model selection, memory scope, current assignments, schedule, health and version.
- Implement the Head of Agents as an actual orchestrator with its own model policy, planning cycle and delegated authority.
- Introduce specialist agents for Strategy, Product, Technology, Marketing, Sales, Operations, Finance and Administration.
- Build a goal decomposition service that creates proposed work items, dependencies, owners and acceptance criteria.
- Support an agent being assigned to multiple goals without copying or forking the agent identity.
- Add bounded retries, cancellation, timeout, concurrency limits, budget limits and idempotent execution.
- Add model, prompt, agent, skill and tool version pinning with rollback.

**Exit criteria:** an end-to-end goal is decomposed into persisted assignments, independently executed, resumed after restart and reconciled into the graph without duplicate work.

## Phase 4 — Official tools and open integrations

- Replace the MCP-style demo adapter with the official MCP Python SDK.
- Support MCP stdio and Streamable HTTP transports with authenticated server identities.
- Store tool definitions, scopes, versions, grants and execution receipts.
- Add a tool sandbox and approval policy for external side effects.
- Add open-source connectors for email, calendar, documents, CRM and issue/work tracking.
- Keep commercial APIs optional behind pluggable interfaces.
- Add integration health, credential rotation and audit trails.

**Exit criteria:** an agent can discover only its granted tools, call an approved tool, record evidence and recover safely from timeout or duplicate submission.

## Phase 5 — Virtual workplace and meetings

- Add real meeting records with agenda, meeting type, participants, facilitator, scheduled time, attendance, minutes and outcome.
- Implement turn-based multi-agent discussion; each contribution is linked to the meeting, speaker agent, agenda item and referenced evidence.
- Support daily stand-up, scrum planning, review, retrospective, alignment and urgent meetings.
- Allow the founder to join by text first; add optional local speech-to-text and text-to-speech later.
- Convert decisions into assignments with explicit owners, due dates and acceptance criteria.
- Support cross-department meetings and conflict escalation to the Head of Agents.
- Add meeting summaries, action-item tracking and commitment follow-up.

**Exit criteria:** a meeting produces reviewable decisions and traceable tasks; the meeting itself does not silently execute consequential actions.

## Phase 6 — Goal, KPI and work management

- Add goal hierarchy and alignment across company, department and team objectives.
- Add KPI definitions: formula, unit, target, threshold, reporting period, source and accountable owner.
- Store time-series KPI snapshots and explain changes from source events.
- Implement task states, dependencies, blocker propagation, due dates and recurrence.
- Add workload and capacity views for agents.
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
- Add Valkey persistence/HA configuration where needed; PostgreSQL remains the durable event source.
- Add load testing, security tests, SBOM, dependency scanning and signed images.
- Support worker pools and scale-out agent execution.

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

After Alpha 1 CI is green, implement **Phase 2 identity and company boundaries** before giving the Head of Agents broad autonomy. Then add durable LangGraph orchestration and official MCP tools. This avoids building a large autonomous workforce on top of unauthenticated development endpoints.
