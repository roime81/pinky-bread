# Pinky Bread 2.0 — AI Company Operating System

**Status:** Alpha 4 — durable workforce runtime, document-aware React composer, agent collaboration and MCP v2  
**Product direction:** a founder-led virtual company whose goals, AI workers, work, collaboration and outcomes are represented as one living graph.

## Product model

Pinky Bread is evolving from a request-oriented multi-agent workflow demo into a goal-oriented company operating system.

The founder defines the company charter:

- Vision and mission
- Business goals and measurable key results
- Operating principles and risk boundaries
- Budget and approval limits
- Desired outcomes and time horizons

The founder should not have to manually coordinate every task. The founder creates the company's agents and assigns one active agent **Coordinator** authority. That user-defined agent translates goals into workstreams, coordinates the configured team, convenes meetings, tracks commitments and reports exceptions. There is no mandatory Head of Agents persona or pre-defined department roster. The founder remains accountable for strategic decisions and any action requiring human approval.

An agent is a persistent organisational identity, not a disposable chat session. The same agent may contribute to multiple goals, and a goal may be served by multiple agents. The graph therefore supports many-to-many relationships.

## Living graph interaction model

The graph is the primary workspace. It is not a decorative dashboard and it is not a fixed organisation chart.

### Node types

| Node | Purpose |
|---|---|
| Company | Company charter, vision, mission and operating principles |
| Goal | Business objective or strategic outcome |
| KPI | A measurable result with target, actual, unit and reporting period |
| Agent | Persistent AI employee identity, role, skills and runtime state |
| Department | Functional grouping and management ownership |
| Work | Task, project, milestone or recurring responsibility |
| Meeting | Stand-up, scrum, planning, alignment, review or retrospective |
| Decision | Recorded decision, rationale summary, owner and approval |
| Deliverable | Report, code, campaign, design, document or other output |
| Document | Company knowledge and reference material |
| Customer | Customer or stakeholder relationship |
| Integration | Connected business system or tool provider |

The current alpha stores flexible node attributes in a JSON column while keeping node identity, type, state and timestamps as relational columns. More specialised tables can be introduced when the behaviours stabilise.

### Relationship types

Relationships are first-class records, not fields buried in an agent prompt.

- `owns`: company or department ownership
- `reports_to`: organisational reporting line
- `contributes_to`: work or agent contributes to a goal
- `assigned_to`: work is assigned to an agent
- `depends_on`: execution dependency
- `collaborates_with`: peer collaboration
- `participates_in`: agent or stakeholder attends a meeting
- `produces`: work or agent produced a deliverable
- `measures`: KPI measures a goal or activity
- `blocks`: a node is blocked by another node
- `informs`: evidence or document informs a decision
- `approved_by`: action or decision has an approval record

A stable agent node can have edges to multiple goals and multiple work items. It is never duplicated merely because it has several assignments.

### Traceability chain

The founder should be able to follow:

`Company → Goal → KPI → Agent → Assignment → Meeting / Decision → Work → Deliverable → Result`

The UI must also support reverse tracing: from a KPI or deliverable back to the originating goal, the contributing agents, the assignments and the evidence.

The graph layout is a visual projection of the stored graph. Selecting a node opens an inspector with its properties, connected nodes, ownership, status and event history. The graph can be filtered by Goals, Agents, Work, Meetings, Results or all relationships.

## Runtime architecture

```text
Founder / Browser
       |
       v
Pinky Bread Company Graph UI
  - Living node-and-edge canvas
  - Goal / agent / work inspectors
  - Company command surface
       |
       v
FastAPI API / Control Plane
  - Company and goal services
  - Agent registry and policy service
  - Workflow and meeting APIs
  - Artifact metadata and access control
       |
       +-------------------- PostgreSQL 16 + pgvector
       |                       - company graph
       |                       - workflow state
       |                       - event / audit log
       |                       - KPI snapshots
       |                       - future semantic memory
       |
       +-------------------- Valkey
       |                       - live graph notifications
       |                       - queue / cache primitives
       |
       +-------------------- SeaweedFS S3 API
       |                       - documents
       |                       - meeting recordings and notes
       |                       - deliverables and uploads
       |
       +-------------------- Durable Workforce Runtime (Alpha 3)
       |                       - PostgreSQL job queue and worker leases
       |                       - LangGraph StateGraph per durable job
       |                       - AsyncPostgresSaver checkpoints
       |                       - heartbeat and expired-lease recovery
       |                       - founder-controlled recurring coordination
       |                       - cooperative cancellation and bounded retries
       |
       +-------------------- MCP v2 / Local Model Gateway
                               - Streamable HTTP MCP server and client
                               - role-scoped tools and trusted identity injection
                               - Ollama / vLLM-compatible local model API
                               - no mandatory hosted model provider
       |
       +-------------------- OpenTelemetry / Prometheus / Grafana (planned)
```

## Persistence and storage rules

### PostgreSQL is the source of truth

The company graph uses relational persistence:

- `company_graph_nodes`: stable node identity, type, state and data
- `company_graph_edges`: typed directed relationships
- `company_graph_events`: append-only activity events with a previous-hash link
- `stored_objects`: object metadata, tenant/company ownership, content type, byte size, checksum, storage key/backend and retention metadata
- `workflows`: existing workflow state and workflow audit data
- `workforce_jobs`: durable job state, idempotency key, lease, retries, cancellation and result
- `company_coordination`: founder-enabled PLAN_ONLY/AUTO_EXECUTE schedule
- LangGraph checkpoint tables: durable StateGraph thread snapshots and pending writes

The graph snapshot is rebuilt from these tables. The UI must never be the only place a goal, assignment or relationship exists.

The current event chain is tamper-evident when verified, but it is **not immutable storage**. A database administrator could alter rows and hashes. Independent WORM retention, signed events and external anchoring remain hardening work.

### Valkey is a notification layer

A graph mutation or workforce job is committed to PostgreSQL first. The application then publishes a best-effort notification to Valkey Pub/Sub for connected graph clients or idle workers. If Valkey is unavailable, database events remain readable and workers poll the durable job queue. Valkey is not the job store, checkpoint store or authoritative audit store.

### SeaweedFS is the S3-compatible object store

Docker Compose uses SeaweedFS for workflow artifact bytes through its S3-compatible API. The application also retains a local filesystem storage mode for development. PostgreSQL stores the `stored_objects` catalogue for workflow artifacts and company documents/deliverables, including owner, company and tenant scope, object key, backend, storage URI, filename, content type, checksum, size and creation metadata. Company document and deliverable uploads create graph nodes and optional `informs` / `produces` relationships; download and listing APIs resolve metadata from PostgreSQL before reading the bytes from the recorded object backend.

Do not store large file bytes in graph JSON fields. Store object keys and metadata in the database and the bytes in the object store.

### pgvector

The Compose PostgreSQL image enables the `vector` extension. The extension is reserved for semantic company memory, retrieval and knowledge grounding. **Embedding generation, vector tables and retrieval are not implemented in Alpha 1**, so the current build must not claim to provide RAG or vector memory.

## Open-source agent stack — target architecture

| Capability | Open-source component | Status |
|---|---|---|
| API and control plane | FastAPI, SQLAlchemy, Pydantic | Existing and extended |
| Relational persistence | PostgreSQL 16 | Existing Compose service; now includes company graph |
| Semantic memory | pgvector | Extension enabled; retrieval pending |
| Live event distribution | Valkey | Compose service and graph event notifications |
| Object storage | SeaweedFS S3 API | Compose service and S3-compatible workflow artifact adapter |
| Local LLM inference | Ollama or vLLM-compatible OpenAI API | Alpha 3 supports self-hosted `/v1/chat/completions`; Ollama is an optional Compose profile |
| Durable multi-agent orchestration | LangGraph + `AsyncPostgresSaver` | Implemented for job-level StateGraph checkpoints |
| Durable job coordination | PostgreSQL jobs/leases + Valkey Pub/Sub | Implemented; PostgreSQL authoritative, Valkey wake-up only |
| Tool protocol | Official MCP Python SDK v2, Streamable HTTP | Internal Alpha 3 server/client, role allow-list and scoped development bearer tokens |
| Identity and SSO | Keycloak / OIDC | Planned |
| Secrets | OpenBao | Planned |
| Policy | Open Policy Agent (OPA) or equivalent | Planned |
| Telemetry | OpenTelemetry, Prometheus, Grafana | Planned |
| Document processing | PyMuPDF; local OCR/VLM pipeline | PDF text extraction exists; OCR pipeline pending |

No proprietary hosted LLM, vector database, object storage or workflow service is required by the target architecture. External model providers may be added later as optional adapters, never as a hard dependency.

## Alpha 4 implementation

The current Alpha 4 baseline includes:

- Company creation with vision, mission and values; persistent graph nodes, typed edges and hash-linked company event history.
- Valkey-backed graph updates, plus PostgreSQL-backed job submission and worker wake-up notifications.
- Founder-defined agent lifecycle: create, edit, promote/demote, change authority and reporting lines, and archive while retaining history.
- Dynamic coordinator planning: the selected company coordinator delegates only to the active agent IDs configured by the founder.
- LangGraph StateGraph job execution with PostgreSQL `AsyncPostgresSaver` checkpoints keyed by durable job ID.
- PostgreSQL job leases, worker heartbeats, fencing, bounded retries/backoff, expired-lease recovery and cooperative cancellation.
- Founder-controlled recurring company coordination in PLAN_ONLY or explicitly enabled AUTO_EXECUTE mode.
- Local OpenAI-compatible model API through Ollama or vLLM-compatible runtimes; Ollama-backed live inference is the default in Docker Compose; set `MOCK_INFERENCE=true` for deliberate simulation.
- Official MCP Python SDK v2 Streamable HTTP client/server, role tool allow-lists, runtime identity context and scoped internal development bearer credentials.
- Agent-to-agent conversations with persistent message history and a React collaboration workspace; the initial streaming execution is request-bound and still needs durable job/checkpoint recovery.
- React 19 + TypeScript founder composer with multi-file upload, public HTTPS cloud-share ingestion and company-scoped document context; private cloud OAuth connectors and image OCR remain pending.
- Per-agent provider configuration for Ollama, vLLM/OpenAI-compatible endpoints, OpenAI and Gemini; credentials remain server-side.
- Replay-safe assignment deliverables and meeting minutes in the existing local/S3 object-storage adapter.
- Turn-based multi-agent meetings and KPI measurement history.
- Compose services for API, horizontally scalable workers, internal MCP server, PostgreSQL/pgvector, Valkey, SeaweedFS and default local Ollama inference.

### Explicit Alpha 4 boundaries

Alpha 3 introduced long-running work in a PostgreSQL-backed job queue and LangGraph checkpoint thread. Workers claim jobs with renewable leases, recover expired leases after process loss, and use replay-safe writes for task/meeting outputs. Valkey is a wake-up and notification service, not the source of truth. The founder can enable recurring PLAN_ONLY coordination or explicitly confirm AUTO_EXECUTE for scheduled assignment execution.

The MCP v2 service and client use Streamable HTTP and per-agent role allow-lists. The current bearer-token verifier is a private-development mechanism; it is not a Keycloak/OIDC identity integration. Company tenant/actor IDs are still caller-supplied, so the APIs and MCP endpoint are not a production multi-tenant security boundary. External side-effect tools remain unavailable. The React composer supports supported document uploads and public HTTPS cloud-share links; authenticated private-drive connectors and scanned-document OCR are not included. Docker Compose defaults to live local Ollama inference (`MOCK_INFERENCE=false`); mock inference is an explicit development option and produces labelled placeholders, not genuine model output.

The checkpointed StateGraph covers durable workforce jobs. Agent-to-agent discussions are persisted and streamed, but their initial request-bound execution does not yet resume an in-flight turn through the durable worker queue. The checkpointed StateGraph does not provide automatic process-level cancellation of an in-flight model request. Cancellation is cooperative between tasks/meeting turns and after model responses. Calendar/voice meetings, automatic KPI collection, semantic retrieval, model/prompt rollback, budgets, rate limits and production observability remain future work.

## API surface added in Alpha 1–4

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/v2/capabilities` | Advertise graph node and relationship types |
| `POST` | `/v2/companies` | Create a company charter |
| `GET` | `/v2/companies` | List companies in the requested tenant context |
| `GET` | `/v2/companies/{id}/graph` | Read the complete company graph snapshot |
| `POST` | `/v2/companies/{id}/nodes` | Create a goal, KPI, agent, work, meeting or other graph node |
| `POST` | `/v2/companies/{id}/edges` | Connect two nodes with a typed relationship |
| `GET` | `/v2/companies/{id}/events` | Read durable company event history |
| `GET` | `/v2/companies/{id}/events/verify` | Verify the company event hash chain |
| `GET` | `/v2/companies/{id}/events/stream` | Receive Valkey-backed live graph notifications |
| `GET` | `/v2/companies/{id}/agents` | List the user-defined company workforce |
| `POST` | `/v2/companies/{id}/agents` | Create a custom agent profile and reporting line |
| `PATCH` | `/v2/companies/{id}/agents/{agent_id}` | Edit profile, instructions, seniority, authority or manager |
| `POST` | `/v2/companies/{id}/agents/{agent_id}/promote` | Increase seniority |
| `POST` | `/v2/companies/{id}/agents/{agent_id}/demote` | Decrease seniority |
| `DELETE` | `/v2/companies/{id}/agents/{agent_id}` | Archive an agent while preserving history |
| `POST` | `/v2/companies/{id}/workforce/bootstrap` | Legacy-compatible roster discovery; creates no predefined agents |
| `POST` | `/v2/companies/{id}/goals/{goal_id}/plan` | Head of Agents decomposes a goal into assignments |
| `POST` | `/v2/companies/{id}/goals/{goal_id}/execute` | Execute assignments sequentially in dependency order |
| `POST` | `/v2/companies/{id}/work/{work_id}/execute` | Execute or explicitly retry one assignment |
| `POST` | `/v2/companies/{id}/meetings/{meeting_id}/convene` | Convene agents and persist meeting minutes |
| `POST` | `/v2/companies/{id}/kpis/{kpi_id}/measure` | Record a source-backed KPI measurement |
| `POST` | `/v2/companies/{id}/artifacts` | Store a company document or deliverable in object storage |
| `GET` | `/v2/companies/{id}/artifacts/{object_id}` | Download an object after tenant-context lookup (OIDC authorization is not implemented yet) |
| `POST` | `/v2/companies/{id}/goals/{goal_id}/jobs` | Queue a goal-plan or goal-execution job |
| `POST` | `/v2/companies/{id}/work/{work_id}/jobs` | Queue one assignment |
| `POST` | `/v2/companies/{id}/meetings/{meeting_id}/jobs` | Queue a meeting |
| `GET` | `/v2/companies/{id}/jobs` | List durable workforce jobs |
| `GET` | `/v2/companies/{id}/jobs/{job_id}` | Read job status/result/retries |
| `POST` | `/v2/companies/{id}/jobs/{job_id}/cancel` | Request cooperative cancellation |
| `GET` / `PUT` | `/v2/companies/{id}/coordination` | Read/update recurring founder coordination policy |

## Security and operational caveats

Alpha 3 remains a development build. Tenant IDs and actor IDs in the current APIs are request-supplied values, not authenticated identities. The graph API must not be exposed to untrusted users until identity, authorisation and company-scoped access checks are implemented. Valkey Pub/Sub is best-effort, and the durable event history remains in PostgreSQL. The hash chain is not a WORM control. Development S3 credentials in Compose are examples only. The internal Docker network does not prove a fully air-gapped or production-secure environment.
