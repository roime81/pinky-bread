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

## Founder-defined agent model

A new company starts with **zero preloaded agents**. The founder designs the workforce to fit the company instead of choosing from a fixed set of roles.

Each agent is a persistent company graph node with a user-authored profile:

- Name and position title
- Free-form role / business function
- Description and scope
- Skills and capabilities
- Responsibilities
- Optional custom system instructions
- Seniority level from 1 to 10
- Authority: `SPECIALIST` or `COORDINATOR`
- Optional reporting manager

The founder may create, edit, promote, demote and remove agents in the Agent Directory. Promotion and demotion change seniority by one level; the title and responsibilities remain editable independently. A company may have only one active `COORDINATOR`. The first agent created in the workspace is suggested as the coordinator, but the founder can choose a different person before saving.

Reporting lines are graph edges (`reports_to`) and are validated to prevent self-management, cross-company managers and circular hierarchies. Agent removal is a soft archive: old assignments, deliverables and event history remain available. Direct reports are reassigned to the removed agent's manager when possible. An agent cannot be archived while it has a running assignment.

The old `/workforce/bootstrap` endpoint remains for compatibility but is now a read-only discovery operation; it does not create default staff.

### Coordinator and specialist execution

The agent selected with `COORDINATOR` authority plans goals and delegates assignments. All other active agents are available for delegation. When only the coordinator exists, it can receive a self-assignment so a founder can still validate the workflow while building the team.

The planner receives a catalogue of the company's actual agent IDs, titles, functions, skills and responsibilities. It must assign each task to one of those IDs. The server validates every assignment against the active roster before creating work. No predefined Strategy, Product, Technology, Marketing, Operations or Finance roles are required.

## Goal planning

The Head of Agents receives company vision, mission and goal context. In local-model mode it asks the configured local reasoning endpoint to return a bounded JSON task plan. The response is validated before any task is written. Unknown agent IDs, duplicate task keys, malformed data and invalid dependencies are rejected.

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
| GET | `/companies/{company_id}/agents` | List user-defined agents |\n| POST | `/companies/{company_id}/agents` | Create a custom agent profile |\n| PATCH | `/companies/{company_id}/agents/{agent_id}` | Edit profile, authority, seniority and manager |\n| POST | `/companies/{company_id}/agents/{agent_id}/promote` | Promote one seniority level |\n| POST | `/companies/{company_id}/agents/{agent_id}/demote` | Demote one seniority level |\n| DELETE | `/companies/{company_id}/agents/{agent_id}` | Archive an agent and preserve history |\n| POST | `/companies/{company_id}/workforce/bootstrap` | Legacy-compatible discovery only; no predefined roster is created |
| POST | `/companies/{company_id}/goals/{goal_id}/plan` | Decompose a goal into persisted assignments |
| POST | `/companies/{company_id}/goals/{goal_id}/execute` | Execute assignments in dependency order |
| POST | `/companies/{company_id}/work/{work_id}/execute` | Execute or explicitly retry one assignment |
| POST | `/companies/{company_id}/meetings/{meeting_id}/convene` | Run a turn-based agent meeting and store minutes |
| POST | `/companies/{company_id}/kpis/{kpi_id}/measure` | Record a KPI value with provenance |

The existing graph, events, verification, artifacts and SSE endpoints remain available.

## Run modes

### Development simulation

Historical Alpha 2 note: this release initially used `MOCK_INFERENCE=true` for GPU-free simulation. From Alpha 4, the recommended Compose deployment defaults to live Ollama inference (`MOCK_INFERENCE=false`); use mock mode only when explicitly requested.

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

The test suite exercises the no-predefined-roster behaviour, custom agent CRUD, promotion/demotion, coordinator uniqueness, reporting-line cycle prevention, archive and direct-report reassignment, dynamic goal delegation, mock execution, object storage download, meeting persistence, KPI measurement history and event-chain verification. The precise CI result is recorded on the associated GitHub Actions run; do not treat a pushed commit as verified until the run is green.
