# Pinky Bread 2.0 — AI Company Operating System

**Status:** Alpha 2 — company graph plus request-driven workforce runtime  
**Product direction:** a founder-led virtual company whose goals, AI workers, work, collaboration and outcomes are represented as one living graph.

## Product model

Pinky Bread is evolving from a request-oriented multi-agent workflow demo into a goal-oriented company operating system.

The founder defines the company charter:

- Vision and mission
- Business goals and measurable key results
- Operating principles and risk boundaries
- Budget and approval limits
- Desired outcomes and time horizons

The founder should not have to manually coordinate every task. A future **Head of Agents** (Chief of Staff role) will translate goals into workstreams, coordinate specialist agents, convene meetings, track commitments and report exceptions. The founder remains accountable for strategic decisions and any action requiring human approval.

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
       +-------------------- Workforce Runtime (Alpha 2)
       |                       - Head of Agents goal planning
       |                       - persistent specialist identities
       |                       - graph-linked assignments and dependencies
       |                       - request-driven local model execution
       |                       - object-store deliverables and meeting minutes
       |                       - provenance-backed KPI measurements
       |
       +-------------------- Durable Agent Runtime (planned)
                               - LangGraph PostgreSQL checkpoints
                               - background workers and restart recovery
                               - official MCP tools and policy enforcement
                               - authenticated approval gates
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

The graph snapshot is rebuilt from these tables. The UI must never be the only place a goal, assignment or relationship exists.

The current event chain is tamper-evident when verified, but it is **not immutable storage**. A database administrator could alter rows and hashes. Independent WORM retention, signed events and external anchoring remain hardening work.

### Valkey is a notification layer

A graph mutation is committed to PostgreSQL first. The application then publishes a best-effort notification to Valkey Pub/Sub for connected graph clients. If Valkey is unavailable, the database record remains committed and can be replayed from the event API. Valkey is not the authoritative audit store.

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
| Local LLM inference | vLLM-compatible OpenAI API | Existing adapter; external model server must be configured |
| Durable multi-agent orchestration | LangGraph + PostgreSQL checkpointer | Planned |
| Tool protocol | Official MCP Python SDK | Planned; current gateway remains a demo adapter |
| Identity and SSO | Keycloak / OIDC | Planned |
| Secrets | OpenBao | Planned |
| Policy | Open Policy Agent (OPA) or equivalent | Planned |
| Telemetry | OpenTelemetry, Prometheus, Grafana | Planned |
| Document processing | PyMuPDF; local OCR/VLM pipeline | PDF text extraction exists; OCR pipeline pending |

No proprietary hosted LLM, vector database, object storage or workflow service is required by the target architecture. External model providers may be added later as optional adapters, never as a hard dependency.

## Alpha 2 implementation

The current feature branch implements:

- Company creation with vision, mission and values.
- Persistent graph nodes and typed edges, including many-to-many agent-to-goal relationships.
- Tenant-filtered graph snapshots and append-only SHA-256 hash-linked event history with verification.
- Valkey Pub/Sub notifications and server-sent events for connected graph clients.
- Company Graph as the primary UI, with an inspector that exposes node-specific workforce actions.
- Idempotent bootstrap of Head of Agents and six reusable specialist identities.
- Goal decomposition into persisted assignments, acceptance criteria, assigned-agent edges and prerequisite dependencies.
- Request-driven execution through a configured local OpenAI-compatible inference endpoint, with explicitly labelled mock mode for GPU-free development.
- Stored Markdown work products, object metadata/checksums and graph-linked deliverables.
- Turn-based multi-agent text meetings with participant edges, timestamped contributions and stored minutes.
- KPI measurement history with source, evidence, timestamp and target comparison.
- PostgreSQL/pgvector, Valkey and SeaweedFS Compose services, with PostgreSQL as the durable source of truth.

### Explicit Alpha 2 boundaries

The Head of Agents can plan goal assignments and specialists can execute bounded work through the configured local model endpoint. Execution is request-driven and sequential; there is no LangGraph PostgreSQL checkpoint, background worker pool or restart recovery yet. A process interruption can leave work in RUNNING state. Meetings are turn-based text sessions, not live voice/video conferencing or calendar scheduling. KPI values can be recorded with evidence, but automatic metric collection and formula evaluation are not implemented. The default MOCK_INFERENCE mode creates clearly labelled development placeholders, not genuine AI output.

Authentication, OIDC, tenant authorisation, RBAC, production approvals, durable LangGraph checkpoints, official MCP transport, pgvector retrieval and production telemetry are not complete. Development defaults and demo credentials must be replaced before a shared deployment.

## API surface added in Alpha 1 and Alpha 2

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
| `POST` | `/v2/companies/{id}/workforce/bootstrap` | Create or reconcile the persistent starter workforce |
| `POST` | `/v2/companies/{id}/goals/{goal_id}/plan` | Head of Agents decomposes a goal into assignments |
| `POST` | `/v2/companies/{id}/goals/{goal_id}/execute` | Execute assignments sequentially in dependency order |
| `POST` | `/v2/companies/{id}/work/{work_id}/execute` | Execute or explicitly retry one assignment |
| `POST` | `/v2/companies/{id}/meetings/{meeting_id}/convene` | Convene agents and persist meeting minutes |
| `POST` | `/v2/companies/{id}/kpis/{kpi_id}/measure` | Record a source-backed KPI measurement |
| `POST` | `/v2/companies/{id}/artifacts` | Store a company document or deliverable in object storage |
| `GET` | `/v2/companies/{id}/artifacts/{object_id}` | Download an authorised-by-tenant-context object record (OIDC authorization is not implemented yet) |

## Security and operational caveats

Alpha 2 remains a development build. Tenant IDs and actor IDs in the current APIs are request-supplied values, not authenticated identities. The graph API must not be exposed to untrusted users until identity, authorisation and company-scoped access checks are implemented. Valkey Pub/Sub is best-effort, and the durable event history remains in PostgreSQL. The hash chain is not a WORM control. Development S3 credentials in Compose are examples only. The internal Docker network does not prove a fully air-gapped or production-secure environment.
