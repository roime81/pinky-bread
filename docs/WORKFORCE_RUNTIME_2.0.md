# Pinky Bread 2.0 — Workforce Runtime (Alpha 2)

## Purpose

Alpha 2 turns the persisted company graph into a first working virtual-company loop:

`Company charter → Goal → Head of Agents plan → Agent assignments → Execution → Stored deliverables → Goal progress`

The same graph also supports a turn-based agent meeting and auditable KPI measurements. This is an operational vertical slice, not a claim that every company function is autonomous or production-ready.

## Open-source runtime path

| Component | Role in this increment |
|---|---|
| FastAPI | Versioned workforce and company APIs |
| SQLAlchemy + PostgreSQL | Company nodes, typed edges, work states, meeting state, KPI snapshots and event history |
| Valkey | Best-effort live graph notifications after committed database events |
| SeaweedFS S3 API | Generated deliverables and meeting minutes when `STORAGE_BACKEND=s3` |
| Local filesystem adapter | Lightweight development storage when `STORAGE_BACKEND=local` |
| vLLM-compatible local endpoint | Head-of-Agents planning, specialist assignment execution and meeting contributions when mock mode is disabled |
| Browser SVG graph | Live projection of persisted company nodes and relationships |

Commercial hosted LLMs are not required. The inference contract remains OpenAI-compatible so a local vLLM-compatible service can be used. No model weights are bundled or downloaded by Pinky Bread.

## Workforce model

The idempotent bootstrap endpoint creates seven persistent role identities:

- Head of Agents — planning, delegation, facilitation and escalation
- Strategy & Growth
- Product
- Technology
- Marketing
- Operations
- Finance & Governance

These are company graph agent nodes, not ephemeral chat sessions. Their role, skills, system prompt, model selection, runtime mode and status are persisted in the node data. Re-running bootstrap does not duplicate roles.

Specialist identities are reusable. Planning a second goal creates new work assignments connected to the existing agent node; it does not clone the agent.

## Goal planning

The Head of Agents receives company vision, mission and goal context. In local-model mode it asks the configured local reasoning endpoint to return a bounded JSON task plan. The response is validated before any task is written. Unsupported roles, duplicate keys, malformed data and invalid dependencies are rejected.

In mock mode, Pinky Bread uses a clearly labelled deterministic planning template. This lets the graph and workflow be tested without a GPU, inference server or external SaaS model.

Each planned assignment is a `work` node with:

- Goal ID and unique task key
- Assigned agent ID and role
- Description and acceptance criteria
- Sequence and prerequisite keys
- Planner identity and planning mode
- Persistent status and execution attempt count

Typed edges express `work → assigned_to → agent`, `work → contributes_to → goal`, `agent → contributes_to → goal`, and `work → depends_on → prerequisite work`.

Planning is idempotent for a goal with an existing non-cancelled plan; it does not silently create duplicates.

## Assignment execution

An explicit goal-execution request runs the planned tasks in dependency order. Each task moves through persisted states:

`READY → RUNNING → COMPLETED` or `FAILED`

Prerequisites must be complete before a dependent task can run. A failed task is visible and may be retried explicitly. Already completed tasks are idempotent and are not called again.

The specialist receives the company charter, goal, assignment, acceptance criteria and completed prerequisite summaries. In local-model mode, the request goes to the configured local OpenAI-compatible model endpoint. In mock mode, the system writes a labelled development placeholder; mock output is not represented as genuine AI reasoning.

A successful assignment creates a Markdown deliverable. The bytes are written through the object-storage adapter. PostgreSQL stores its object ID, ownership, company/tenant, object key, content type, byte size, SHA-256 checksum and graph reference. The assignment is connected to the deliverable with a `produces` edge. The goal's work-completion percentage is recalculated from persisted assignments.

No financial, legal, customer-facing or other external side effect is performed by this execution endpoint. MCP tools and approval-gated external actions remain separate future work.

## Agent meetings

A founder can convene a meeting node. The meeting runtime selects its configured participants (or a small default leadership group), creates `participates_in` edges and collects one turn from each agent in sequence.

The meeting stores:
- Agenda, meeting type and lifecycle state
- Participant agent IDs
- Timestamped speaker contributions
- Facilitator summary
- A Markdown minutes deliverable in object storage

Meeting state changes and each turn are recorded in the company event history. Re-convening a completed meeting returns its existing persisted result rather than generating duplicate minutes.

This is a turn-based text meeting, not voice/video conferencing or calendar scheduling. In mock mode, each contribution is a transparent development simulation.

## KPI measurements

KPI nodes accept measured numeric values with source, evidence, timestamp and recording actor. Each update appends a measurement snapshot (retaining the latest 100 snapshots on the node) and emits a company event.

A target comparison marks a KPI as `TARGET_MET` or `TRACKING`. This release does not infer business metrics from third-party systems; automatic metric collectors and formulas are future work.

## APIs

All paths are under `/v2`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/companies/{company_id}/workforce/bootstrap` | Create or reconcile the starter AI team |
| POST | `/companies/{company_id}/goals/{goal_id}/plan` | Decompose a goal into persisted assignments |
| POST | `/companies/{company_id}/goals/{goal_id}/execute` | Execute assignments in dependency order |
| POST | `/companies/{company_id}/work/{work_id}/execute` | Execute or explicitly retry one assignment |
| POST | `/companies/{company_id}/meetings/{meeting_id}/convene` | Run a turn-based agent meeting and store minutes |
| POST | `/companies/{company_id}/kpis/{kpi_id}/measure` | Record a KPI value with provenance |

The existing graph, events, verification, artifacts and SSE endpoints remain available.

## Run modes

### Development simulation

The default `MOCK_INFERENCE=true` works without a GPU or model server. It exercises state transitions, graph persistence, artifact storage and API behavior while clearly labelling generated text as a mock.

### Local model inference

Set `MOCK_INFERENCE=false`, configure `REASONING_API_URL`, `REASONING_MODEL` and `VLLM_API_KEY`, then ensure the API container can reach the local inference service. The endpoint must implement the OpenAI-compatible `/chat/completions` contract.

### Storage

- `STORAGE_BACKEND=local`: files are stored below the configured upload directory.
- `STORAGE_BACKEND=s3`: files are stored through the S3-compatible adapter, suitable for the SeaweedFS S3 service in Compose.

PostgreSQL metadata remains the catalogue and authorization lookup. Never expose raw object-store credentials to agents or the browser.

## Current limits and security boundary

Alpha 2 materially improves the runtime but is not a production multi-tenant system yet:

- Company API tenant and actor IDs are still supplied by the caller. Keycloak/OIDC identity validation, membership enforcement and company-scoped RBAC are not implemented.
- There is no LangGraph PostgreSQL checkpointer or worker queue yet. Goal execution is request-driven and sequential; a process interruption can leave a task in `RUNNING`.
- MCP is still the original in-process demo gateway. This workforce slice does not execute external tools.
- There is no autonomous calendar scheduler, voice meeting, email/CRM connector, automatic KPI ingestion or budget enforcement.
- pgvector is enabled in PostgreSQL but semantic embedding generation and retrieval are not implemented.
- Valkey notifications are best-effort. PostgreSQL is the durable source of truth.
- The hash-linked event table is tamper-evident when verified, not WORM or independently immutable.
- Replace development credentials and do not expose this alpha to untrusted users.

## Verification

The Alpha 2 test suite exercises team bootstrap idempotency, goal decomposition, assignment relationships, dependency handling, mock execution, object storage download, meeting persistence, KPI measurement history and event-chain verification. The precise CI result is recorded on the associated GitHub Actions run; do not treat a pushed commit as verified until the run is green.
