# Pinky Bread

**Pinky Bread 2.0 — Local-first AI Company Operating System**

Pinky Bread is evolving from a multi-agent workflow prototype into a founder-led virtual company. A founder defines the company vision, mission, goals and KPIs; a persistent company graph connects AI employees, assignments, meetings, decisions, deliverables and business outcomes. The graph is the primary workspace and a live projection of database records and company events.

Pinky Bread 2.0 Alpha 3 advances the virtual company into a durable workforce platform. PostgreSQL stores jobs and LangGraph checkpoints; worker leases, heartbeats and recovery allow execution to resume after process loss. Valkey coordinates worker wake-ups, the founder can enable recurring Head-of-Agents coordination, and the official MCP Python SDK v2 connects role-scoped tools to self-hosted Ollama/vLLM-compatible model APIs.

> **Versioning:** the complete Pinky Bread 2.0 Alpha 3 stack is now merged into the default `main` branch. The [Alpha 1 company graph](https://github.com/roime81/pinky-bread/pull/1), [Alpha 2 workforce runtime](https://github.com/roime81/pinky-bread/pull/2) and [Alpha 3 durable runtime](https://github.com/roime81/pinky-bread/pull/3) were delivered as a stacked sequence. This README describes the current `main` branch. Check the [2.0 architecture](docs/ARCHITECTURE_2.0.md), [open-source stack](docs/OPEN_SOURCE_STACK_2.0.md) and [delivery roadmap](docs/ROADMAP_2.0.md) for implemented scope and remaining work.

> [!IMPORTANT]
> **MVP / demonstration software.** The included refund/ledger action is simulated and never contacts a real banking system or transfers money. Mock inference is enabled by default and does not inspect image pixels. Authentication, enterprise RBAC, tenant isolation, Keycloak/OIDC identity, production RBAC/tenant isolation, production MCP OAuth/JWT verification, production-grade PII detection and independently immutable audit storage are not implemented. Do not use this build for production, regulated decisions, or real financial/clinical operations.

---

## Contents

- [Pinky Bread 2.0 Alpha 3](#pinky-bread-20-alpha-3)
- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Requirements](#requirements)
- [Install and run locally](#install-and-run-locally)
- [Run with Docker Compose](#run-with-docker-compose)
- [Configure a self-hosted local model](#configure-a-self-hosted-local-model)
- [Try the demo workflow](#try-the-demo-workflow)
- [API reference](#api-reference)
- [Configure specialist agents](#configure-specialist-agents)
- [Run tests](#run-tests)
- [Project structure](#project-structure)
- [Security and operational boundaries](#security-and-operational-boundaries)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)

## Pinky Bread 2.0 Alpha 3

### What is new

- **Living Company Graph:** the default workspace visualises the company, goals, KPI nodes, agent identities, work, meetings, decisions and deliverables as connected dots.
- **Persistent company data model:** PostgreSQL-backed node, relationship and event records. A single agent identity can connect to multiple goals and assignments.
- **Founder-first onboarding:** create a company with its vision and mission; the persistent Head of Agents and six reusable specialist identities are provisioned in the graph.
- **Interactive graph:** add goal, KPI, agent, work and meeting records; connect dots; select any node to inspect its data and relationships. Upload company documents and deliverables, link them to goals/work and download them through company-scoped artifact endpoints.
- **Company event history:** append-only hash-linked records, paginated history and a hash-chain verification endpoint.
- **Live graph notifications:** Valkey Pub/Sub pushes committed graph events to connected clients; PostgreSQL remains the durable source of truth.
- **Open object storage path:** workflow attachments and company documents/deliverables use a local or S3-compatible adapter. PostgreSQL catalogs ownership, company/tenant scope, checksum, type, size and object key; SeaweedFS stores the bytes in Compose.
- **Open-source Compose stack:** PostgreSQL 16 with pgvector, Valkey and SeaweedFS.
- **Working AI workforce:** idempotent bootstrap of Head of Agents and six specialist roles; role identities are reused across goals.
- **Goal-to-work execution:** Head of Agents creates validated, dependency-aware assignments. Specialists run sequentially through the configured local model endpoint, or through an explicitly labelled development simulation.
- **Stored work products:** each successful assignment writes a Markdown deliverable to local/S3 object storage; PostgreSQL records metadata, ownership and checksum, and the graph links work to its output.
- **Virtual meetings:** turn-based text discussions with participant edges, contributions, facilitator summary and stored minutes.
- **KPI history:** founder-recorded numeric measurements with source, evidence, timestamp and a bounded snapshot history.
- **Durable jobs:** PostgreSQL job rows with idempotency, worker ownership leases, heartbeats, retries/backoff, cancellation and expired-lease recovery.
- **LangGraph checkpoints:** each durable job runs through a LangGraph StateGraph with PostgreSQL AsyncPostgresSaver checkpoints keyed by job ID.
- **Valkey coordination:** best-effort wake-up notifications; workers poll PostgreSQL as a loss-safe fallback.
- **Continuous Head of Agents:** founder-controlled recurring PLAN_ONLY or AUTO_EXECUTE company schedule; disabled by default.
- **Official MCP v2:** Streamable HTTP MCP server/client, tool discovery, per-role allow-list and runtime-injected company/tenant/agent identity.
- **Self-hosted local models:** Ollama (optional Compose profile) or vLLM-compatible OpenAI chat-completions endpoints. No hosted LLM is required.
- **Durable worker service:** separate worker process that can be scaled horizontally.

### What still needs to be built

Alpha 3 is a durable workforce increment, not yet a production-ready company. Job execution is checkpointed and recovers expired leases, but cancellation is cooperative at safe boundaries rather than interrupting an in-flight model generation. Meetings remain text-based; calendar scheduling and voice/video are not implemented. KPI measurements remain manual. No external MCP side-effect tools are enabled.

Keycloak/OIDC JWT validation, company-scoped RBAC, OpenBao secrets, OPA policy enforcement, pgvector retrieval, model/prompt rollback, token/cost budgets, OpenTelemetry/Prometheus/Grafana and production backup/restore remain future work. Tenant and actor identifiers in current APIs are caller-supplied and are not an authorization boundary. The MCP static bearer verifier is for private development only. Do not expose this alpha to untrusted users.

See:
- [Pinky Bread 2.0 architecture](docs/ARCHITECTURE_2.0.md)
- [Pinky Bread 2.0 open-source stack](docs/OPEN_SOURCE_STACK_2.0.md)
- [Pinky Bread 2.0 roadmap](docs/ROADMAP_2.0.md)

## Overview

Pinky Bread explores a controlled multi-agent execution pattern:

1. A user submits a request through the web console or REST API, optionally with a PDF, PNG, or JPEG artifact.
2. The API stores the artifact, extracts text from text-based PDFs, and applies a local regex-based PII masking pass to the prompt and extracted text before model inference.
3. A router selects an initial specialist using an explicitly requested domain or basic request-keyword routing.
4. The specialist executes using either the built-in mock inference mode or an OpenAI-compatible local model endpoint.
5. Specialists can hand work to a configured downstream specialist. In the included aviation-to-refund example, the refund specialist prepares a proposal and pauses the workflow.
6. A human submits an approval or rejection decision. Approval can invoke only the configured allow-listed demo tool; rejection ends the workflow without invoking it.
7. Workflow state and hash-linked audit entries are persisted to SQLite by default or PostgreSQL when running the Compose stack.

## Features

| Capability | MVP implementation | Current boundary |
|---|---|---|
| Web operations console | Company graph, company onboarding, node inspector, relationships, event activity, legacy workflow/approval/agent/audit views | Development UI; no login or authenticated tenant boundary |
| Company graph and workforce | Company, goals, KPIs, reusable agents, assignments, meetings and deliverables with typed edges | Durable PostgreSQL job queue, LangGraph checkpoints and worker recovery; authenticated tenant boundary remains future work |
| Company event history | PostgreSQL append-only company events with SHA-256 chaining and verification API | Tamper-evident, not independently immutable or WORM protected |
| Live graph updates | Valkey Pub/Sub notifications and SSE | Database event history is authoritative; Valkey notifications are best-effort |
| Object storage | Local filesystem or S3-compatible SeaweedFS for source documents, generated deliverables and meeting minutes | PostgreSQL catalogues owner, company/tenant, checksum and object key; auth/retention policies remain planned |
| Declarative agent registry | YAML manifests, Pydantic validation, reload endpoint | Registry reload is local configuration, not a governed deployment pipeline |
| Deterministic routing | Router plus explicit specialist hand-off logic | Lightweight Python state machine, not LangGraph |
| Local LLM integration | OpenAI-compatible chat completions adapter | Endpoint compatibility depends on the selected model/server |
| Mock inference | GPU-free deterministic development response | Does not understand or OCR image contents |
| Multimodal artifact intake | PNG/JPEG/PDF uploads, artifact persistence, PDF text extraction, image forwarding to configured vision endpoint | Scanned PDF OCR is not included; mock mode does not inspect images |
| Human-in-the-loop | Pending approval state, approve/reject API, approver ID and notes in audit | Approver ID is supplied by the caller; not authenticated |
| Tool access control | Agent manifest allow-list checked before simulated refund tool execution | Local MCP-style adapter only; no MCP protocol transport |
| Audit trail | SHA-256 input hashes and previous-event hash links | Tamper-evident linkage, not WORM/immutable storage or signed audit |
| Persistence | SQLAlchemy workflow state stored in SQLite or PostgreSQL | No LangGraph checkpointing or migration framework |
| Container deployment | Dockerfile and Compose with PostgreSQL/pgvector, Valkey and SeaweedFS | Development credentials are in the sample Compose file; replace them before shared deployment |

## Architecture

```text
+-------------------------------+
| Browser operations console    |
+---------------+---------------+
                | HTTP / JSON
+---------------v---------------+
| FastAPI application           |
|                               |
|  +-------------------------+  |
|  | YAML agent registry     |  |
|  +-------------------------+  |
|  | Workflow router/engine  |  |
|  | Human approval gate     |  |
|  | Artifact ingestion      |  |
|  | PII masking             |  |
|  +-----------+-------------+  |
+--------------+----------------+
               |
       +-------+---------+
       |                 |
+------v-------+  +------v----------------+
| Local model  |  | SQLAlchemy persistence|
| adapter      |  | SQLite / PostgreSQL   |
| mock or vLLM |  +-----------------------+
+--------------+
       |
+------v------------------+
| MCP-style demo gateway  |
| allow-list + simulated  |
| refund tool             |
+-------------------------+
```

### Included example workflow

```text
Request
  |
  v
Router
  |
  v
Airline Operations Agent
  |  detects possible disruption from request/document text
  v
Banking Refund Agent
  |  creates proposal; does not execute a credit
  v
Human Approval Gate
  |-----------------------|
  | Approve               | Reject
  v                       v
Allow-listed simulated   Rejected
refund tool               |
  |                       |
  +-----------+-----------+
              v
       Persisted audit trail
```

The included example is intentionally a workflow demonstration. Keyword detection and mock responses are not a reliable eligibility, fraud, refund, or risk decision process.

## Technology stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.11+ | Application runtime |
| API | FastAPI, Uvicorn | REST API, OpenAPI docs, SSE response endpoint |
| Data validation/configuration | Pydantic v2, pydantic-settings, PyYAML | Request validation, environment settings, agent manifests |
| Workflow orchestration | LangGraph StateGraph + PostgreSQL AsyncPostgresSaver | Durable job execution and checkpointed recovery |
| Job coordination | PostgreSQL queue/leases + Valkey Pub/Sub | Idempotent jobs, worker leases, retry/backoff and worker wake-up |
| Model adapter | HTTPX, OpenAI-compatible chat completions contract | Goal planning, specialist work, meetings and MCP function calls |
| Inference server (optional) | Ollama 0.40.16 or vLLM-compatible endpoint | Self-hosted open-weight model serving; weights supplied separately |
| Tool protocol | MCP Python SDK v2, Streamable HTTP | Official MCP server/client with role-scoped tools and trusted identity injection |
| Persistence | SQLAlchemy 2, SQLite / PostgreSQL | Workflow state plus company graph nodes, typed edges and event history |
| Vector extension image | pgvector PostgreSQL image | Extension enabled; embeddings and semantic retrieval are not yet implemented |
| Cache/event service | Valkey 9.1 (Redis protocol compatible) | Best-effort graph event notifications; PostgreSQL remains durable |
| PDF processing | PyMuPDF | Text extraction from text-based PDFs |
| Frontend | HTML, CSS, vanilla JavaScript | Browser-based console without a frontend build toolchain |
| Object storage | SeaweedFS S3 API + boto3 | S3-compatible company documents, deliverables, meeting minutes and workflow artifacts |
| Containers | Docker, Docker Compose | Local container deployment |
| Tests | pytest, FastAPI TestClient | API and workflow behavior tests |

## Requirements

### For local Python execution

- Python **3.11 or newer**
- `pip`
- A supported Windows, macOS, or Linux environment
- Internet access to install Python packages for the first setup, unless dependencies are available from an internal package mirror

No GPU is required when `MOCK_INFERENCE=true` (the default).

### For Docker Compose

- Docker Engine or Docker Desktop with Compose v2
- Sufficient memory and disk for API, PostgreSQL, Valkey, SeaweedFS and the worker; local models require additional RAM/VRAM and model storage

### For local model inference (optional)

- A running OpenAI-compatible local inference server, for example vLLM
- The model weights and tokenizer already available to that inference server
- A reasoning model endpoint and, when image understanding is required, a vision-capable endpoint
- Network connectivity from Pinky Bread to those internal endpoints

Pinky Bread does not download model weights automatically.

## Install and run locally

### Windows PowerShell

From the directory where you want the source checked out or extracted:

```powershell
cd pinky-bread

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env

uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

If PowerShell blocks activation, use the Python executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

### macOS / Linux

```bash
cd pinky-bread

python3.11 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env

uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

### Open the application

- Web console: <http://127.0.0.1:8080>
- Interactive API docs: <http://127.0.0.1:8080/docs>
- OpenAPI JSON: <http://127.0.0.1:8080/openapi.json>
- Health endpoint: <http://127.0.0.1:8080/api/healthz>

The default local Python configuration uses SQLite, local filesystem object storage and mock inference. Durable workers and LangGraph PostgreSQL checkpoints require PostgreSQL. Docker Compose runs PostgreSQL/pgvector, Valkey, SeaweedFS, API, worker and internal MCP; Ollama is an optional profile. A GPU is not required for mock mode.

## Run with Docker Compose

Start the full local container stack:

```bash
docker compose up --build
```

Open <http://localhost:8080>.

Useful commands:

```bash
# Follow application logs
docker compose logs -f api

# Show service state
docker compose ps

# Scale durable job workers (PostgreSQL coordinates the replicas)
docker compose up -d --scale worker=3

# Stop containers and preserve named volumes
docker compose down

# Stop containers and remove database/cache volumes (destructive)
docker compose down --volumes
```

The Compose stack contains:

- `api`: FastAPI web console and company/workforce API
- `worker`: LangGraph worker process; scale by adding replicas
- `mcp`: internal MCP v2 Streamable HTTP server (port 8090 is not published to the host)
- `postgres`: PostgreSQL 16 using the pgvector image; durable queue and checkpoints
- `valkey`: Valkey with append-only persistence enabled; worker wake-up only
- `seaweedfs`: SeaweedFS S3-compatible object storage
- `ollama`: optional `local-llm` profile for self-hosted models

The default application network is configured as `internal: true`, which restricts container egress. The optional Ollama profile is attached to a separate model-download network so it can pull the model explicitly; remove that egress path after preloading models for an air-gapped deployment. **Compose is not proof of a fully air-gapped deployment.** Host firewall rules, ingress, routing, DNS, secrets, image sources and infrastructure controls must be reviewed independently. PostgreSQL owns durable job/checkpoint state; Valkey only wakes workers and publishes live graph notifications. SeaweedFS stores documents and outputs while PostgreSQL keeps object metadata and checksums. The extension init script for pgvector runs only on a fresh PostgreSQL data directory; an existing volume needs a manual extension migration.

The PostgreSQL password and SeaweedFS S3 keys are development-only values. Replace them with managed secrets and restrict the S3 identity before any shared or non-development deployment.

## Configure a self-hosted local model

Mock mode is enabled by default. To use a local OpenAI-compatible endpoint, edit `.env`. vLLM and Ollama can both be used when configured with the compatible chat-completions API:

```dotenv
MOCK_INFERENCE=false
REASONING_API_URL=http://127.0.0.1:8001/v1
REASONING_MODEL=your-reasoning-model
MULTIMODAL_API_URL=http://127.0.0.1:8002/v1
MULTIMODAL_MODEL=your-vision-model
VLLM_API_KEY=local-development-key
```

For a local Ollama container instead of vLLM, start the optional profile and pull your chosen model:

```bash
docker compose --profile local-llm up -d
docker compose exec ollama ollama pull <model-name>
```

Set `REASONING_API_URL=http://ollama:11434/v1`, `REASONING_MODEL=<model-name>` and `MOCK_INFERENCE=false` in `.env`, then recreate the API and worker. Pinky Bread uses the local model's OpenAI-compatible chat-completions endpoint; when `MCP_ENABLED=true`, model tool calls are routed through the internal MCP server.

For a local Ollama container instead of vLLM, start the optional profile and pull your chosen model:

```bash
docker compose --profile local-llm up -d
docker compose exec ollama ollama pull <model-name>
```

Set `REASONING_API_URL=http://ollama:11434/v1`, `REASONING_MODEL=<model-name>` and `MOCK_INFERENCE=false` in `.env`, then recreate the API and worker. Pinky Bread uses the local model's OpenAI-compatible chat-completions endpoint; when `MCP_ENABLED=true`, model tool calls are routed through the internal MCP server.

Then restart the application. The adapter sends requests to:

```text
{REASONING_API_URL}/chat/completions
{MULTIMODAL_API_URL}/chat/completions
```

Reasoning uses the `model_name` and optional `endpoint` configured in the selected agent manifest. Image requests use the configured multimodal endpoint/model and an OpenAI-compatible `image_url` content part. Verify that the chosen inference server and model support this request format.

For containerized execution, `127.0.0.1` inside the API container refers to that container itself. Use an appropriate Docker network service name or reachable internal hostname for the model server.

Example agent-specific model configuration:

```yaml
model_configuration:
  provider: local_vllm
  endpoint: http://vllm-reasoning:8000/v1
  model_name: local-reasoning-model
  temperature: 0.05
  max_tokens: 1200
```

### Multimodal notes

- Text-based PDF content is extracted locally with PyMuPDF.
- Scanned PDFs do not receive OCR in this MVP. Add a local OCR/VLM processing pipeline for scanned documents.
- PNG and JPEG bytes are accepted as artifacts and passed to the multimodal endpoint only when mock mode is disabled.
- Mock mode records that images were attached but does not inspect their pixels.
- The current masking implementation is regex-based and should not be considered a complete PII/PHI detector.

## Try the demo workflow

1. Start the application and open <http://127.0.0.1:8080>.
2. In **Start a workflow**, enter:

   ```text
   Review this cancelled flight and prepare a refund proposal for RM450.
   ```

3. Leave routing on **Automatic routing** (or select **Aviation operations**).
4. Click **Run workflow**.
5. The example should execute `airline_ops_agent`, hand off to `banking_refund_agent`, and pause with status `PENDING_APPROVAL`.
6. Choose **Approve & simulate** and enter an approver identifier.
7. The workflow should complete with a `SIMULATED_CREDIT_POSTED` result and a `SIM-...` transaction reference.
8. Open **Audit trail** to inspect the linked event hashes.

No real ledger is connected and no money is moved. To test the rejection path, choose **Reject** at the approval gate; the simulated tool must not execute.

The simple routing and disruption checks are illustrative keyword logic. They do not verify a flight booking, airline status, refund entitlement, or customer identity.

## API reference

The service publishes an interactive OpenAPI document at `/docs` when running. The company/workforce API is versioned under `/v2`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/healthz` | Health, application name, environment and inference mode |
| `GET` | `/v1/agents` | List active YAML agent manifests |
| `POST` | `/v1/agents/reload` | Reload and validate agent configuration files |
| `POST` | `/v1/artifacts` | Upload one PNG, JPEG or PDF artifact and return its base64 representation |
| `POST` | `/v1/workflows/invoke` | Start and execute a workflow |
| `POST` | `/v1/workflows/stream` | Return workflow audit events as SSE after execution; this is not token-by-token live streaming |
| `GET` | `/v1/workflows` | List the latest 50 workflow records |
| `GET` | `/v1/workflows/{thread_id}` | Retrieve workflow state and result |
| `POST` | `/v1/workflows/{thread_id}/approve` | Approve or reject a pending workflow action |
| `GET` | `/v1/audit/{thread_id}` | Retrieve the workflow audit trail |
| `GET` | `/v2/capabilities` | Discover graph and workforce capabilities |
| `POST` | `/v2/companies` | Create a company charter |
| `GET` | `/v2/companies` | List companies in a tenant context |
| `GET` | `/v2/companies/{company_id}/graph` | Read the persisted company graph |
| `POST` | `/v2/companies/{company_id}/workforce/bootstrap` | Provision or reconcile the starter AI workforce |
| `POST` | `/v2/companies/{company_id}/goals/{goal_id}/plan` | Ask Head of Agents to decompose a goal into assignments |
| `POST` | `/v2/companies/{company_id}/goals/{goal_id}/execute` | Execute goal assignments in dependency order |
| `POST` | `/v2/companies/{company_id}/work/{work_id}/execute` | Execute or retry one work assignment |
| `POST` | `/v2/companies/{company_id}/meetings/{meeting_id}/convene` | Convene a turn-based agent meeting and store minutes |
| `POST` | `/v2/companies/{company_id}/kpis/{kpi_id}/measure` | Record a KPI measurement and provenance |
| `POST` | `/v2/companies/{company_id}/goals/{goal_id}/jobs` | Queue a durable goal-plan or execution job |
| `POST` | `/v2/companies/{company_id}/work/{work_id}/jobs` | Queue one durable assignment |
| `POST` | `/v2/companies/{company_id}/meetings/{meeting_id}/jobs` | Queue a meeting job |
| `GET` | `/v2/companies/{company_id}/jobs` | List durable jobs |
| `GET` | `/v2/companies/{company_id}/jobs/{job_id}` | Read a job's state/result/retries |
| `POST` | `/v2/companies/{company_id}/jobs/{job_id}/cancel` | Request cooperative cancellation |
| `GET` / `PUT` | `/v2/companies/{company_id}/coordination` | Read/configure recurring Head-of-Agents coordination |
| `POST` | `/v2/companies/{company_id}/goals/{goal_id}/jobs` | Queue a durable goal-plan or execution job |
| `POST` | `/v2/companies/{company_id}/work/{work_id}/jobs` | Queue one durable assignment |
| `POST` | `/v2/companies/{company_id}/meetings/{meeting_id}/jobs` | Queue a meeting job |
| `GET` | `/v2/companies/{company_id}/jobs` | List durable jobs |
| `GET` | `/v2/companies/{company_id}/jobs/{job_id}` | Read a job's state/result/retries |
| `POST` | `/v2/companies/{company_id}/jobs/{job_id}/cancel` | Request cooperative cancellation |
| `GET` / `PUT` | `/v2/companies/{company_id}/coordination` | Read/configure recurring Head-of-Agents coordination |
| `GET` | `/v2/companies/{company_id}/events` | Read company event history |
| `GET` | `/v2/companies/{company_id}/events/verify` | Verify the company event hash chain |
| `POST` | `/v2/companies/{company_id}/artifacts` | Store a company document or deliverable |
| `GET` | `/v2/companies/{company_id}/artifacts/{object_id}` | Download a company artifact |

### Invoke a workflow with curl

```bash
curl -X POST http://127.0.0.1:8080/v1/workflows/invoke \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Review a cancelled flight and prepare a refund proposal for RM450."}'
```

### Approve a pending workflow

Replace `<THREAD_ID>` with the `thread_id` returned by the invoke endpoint:

```bash
curl -X POST http://127.0.0.1:8080/v1/workflows/<THREAD_ID>/approve \
  -H 'Content-Type: application/json' \
  -d '{"approver_id":"finance.manager","decision":"APPROVED","notes":"Reviewed for MVP simulation"}'
```

Use `"decision":"REJECTED"` to test the rejection path.

### Invoke with an artifact

The workflow request accepts an `artifacts` array. Each entry uses a MIME type supported by the API and base64-encoded file bytes:

```json
{
  "prompt": "Review this cancelled boarding pass and summarize the evidence.",
  "artifacts": [
    {
      "filename": "boarding-pass.png",
      "mime_type": "image/png",
      "base64_data": "<BASE64_ENCODED_FILE_BYTES>"
    }
  ]
}
```

Each artifact is subject to the configured upload size limit (`MAX_UPLOAD_MB`, default 12 MB).

## Configure specialist agents

Agent manifests are loaded from `config/agents/*.yaml` (and `*.yml`). Each manifest includes these top-level sections:

- `agent_metadata`: `agent_id`, `display_name`, `domain`, `version`
- `model_configuration`: `provider`, `model_name`, `temperature`, `max_tokens`, and optional `endpoint`
- `persona_and_guardrails`: `system_prompt` and `require_human_approval_above_risk_score`
- `capabilities`: `allowed_mcp_tools` and `rag_collections`
- `workflow_wiring`: `can_handoff_to` and `default_next_job`

Example:

```yaml
agent_metadata:
  agent_id: operations_agent
  display_name: Operations Specialist
  domain: operations
  version: 1.0.0

model_configuration:
  provider: local_vllm
  endpoint: http://vllm-reasoning:8000/v1
  model_name: local-reasoner
  temperature: 0.05
  max_tokens: 1200

persona_and_guardrails:
  system_prompt: >-
    You are an operations specialist. State assumptions and do not execute
    consequential actions without the required approval step.
  require_human_approval_above_risk_score: 0.85

capabilities:
  allowed_mcp_tools: []
  rag_collections: []

workflow_wiring:
  can_handoff_to: []
  default_next_job: END
```

After saving a manifest, call `POST /v1/agents/reload` or click **Reload manifests** in the console. Validation errors reject the reload and preserve the last known-good registry. Current workflow execution contains explicit logic for the included example agents; arbitrary new manifests can appear in the registry but may require corresponding workflow node behavior before they can execute specialized tasks.

## Configuration reference

The application reads environment variables from the environment and `.env` file. See `.env.example` for the complete sample configuration.

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `Pinky Bread` | Application display/API title |
| `APP_ENV` | `development` | Environment label shown by health endpoint and UI |
| `DEV_MODE` | `true` | Development setting; does not enable authentication |
| `MOCK_INFERENCE` | `true` | Use GPU-free mock responses instead of HTTP model calls |
| `DATABASE_URL` | `sqlite:///./data/pinky_bread.db` | SQLAlchemy database connection URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Valkey/Redis-compatible URL used for best-effort company graph notifications |
| `AGENT_CONFIG_DIR` | `./config/agents` | Directory containing YAML agent manifests |
| `UPLOAD_DIR` | `./data/uploads` | Local object and upload storage directory |
| `MAX_UPLOAD_MB` | `12` | Maximum size per artifact |
| `STORAGE_BACKEND` | `local` | `local` filesystem or `s3` compatible object storage |
| `S3_ENDPOINT_URL` | `http://localhost:8333` | S3 endpoint, such as SeaweedFS |
| `S3_REGION` | `us-east-1` | S3 signing region |
| `S3_BUCKET` | `pinky-bread` | Bucket for workflow artifacts |
| `S3_ACCESS_KEY` | development value | S3-compatible access key; replace before shared deployment |
| `S3_SECRET_KEY` | development value | S3-compatible secret; replace before shared deployment |
| `REASONING_API_URL` | `http://localhost:8001/v1` | OpenAI-compatible local reasoning endpoint base URL |
| `REASONING_MODEL` | `local-reasoner` | Default reasoning model setting; agent manifest `model_name` is used for reasoning calls |
| `MULTIMODAL_API_URL` | `http://localhost:8002/v1` | OpenAI-compatible local vision endpoint base URL |
| `MULTIMODAL_MODEL` | `local-vision` | Vision model identifier |
| `VLLM_API_KEY` | `local-dev-key` | Bearer token passed to local inference endpoint |

Do not commit a real `.env` file, API key, password, certificate, or private model credential.

## Connect the local model to MCP

The Compose stack starts an internal MCP v2 Streamable HTTP server. The local model client discovers its tools dynamically and then filters those tools by the active agent role. The model cannot choose its own company, tenant or agent ID; those values are injected by the runtime.

Before using non-mock inference, set `MCP_ENABLED=true` and replace `MCP_API_TOKEN` and `MCP_READ_TOKEN` in `.env` with separate long random values. The MCP port is internal to Compose and is not published to the host. The current verifier is for private development, not production OIDC; see [the durable runtime guide](docs/DURABLE_WORKFORCE_RUNTIME_2.0.md) before exposing it.

From the Company Graph workspace, **Enable planning loop** lets the Head of Agents create plans on its schedule. **Enable auto-execution** requires explicit founder confirmation and lets the worker execute ready work. The default is disabled. Stop coordination at any time with **Pause coordination**.

## Run tests

Create and activate the virtual environment, install requirements, then run:

```bash
pytest -q
```

Or use the Makefile on macOS/Linux or systems with `make`:

```bash
make install
make test
```

The test suite covers the original workflow and company graph, workforce planning/execution, artifact storage, meetings, KPI measurements, PostgreSQL job de-duplication and leases, lease-expiry recovery, recurring coordination, LangGraph PostgreSQL checkpoint replay and MCP SDK v2 tool discovery/identity scoping.

## Project structure

```text
pinky-bread/
├── app/
│   ├── database.py       # SQLAlchemy models and persistence helpers
│   ├── engine.py         # Legacy workflow routing, execution and approval flow
│   ├── workforce.py      # Head of Agents, goal planning, task execution, meetings and KPIs
│   ├── durable_runtime.py # PostgreSQL jobs, LangGraph checkpoints, worker leases and coordination
│   ├── worker.py          # Durable workforce worker entrypoint
│   ├── mcp_server.py      # Internal MCP v2 server with scoped tools
│   ├── mcp_client.py      # Role-scoped MCP client for local model tool calls
│   ├── company_graph.py  # Company graph nodes, edges, updates and hash-linked events
│   ├── company_api.py    # Versioned /v2 company and workforce endpoints
│   ├── object_store.py   # Local and S3-compatible object storage adapter
│   ├── inference.py      # Mock and OpenAI-compatible local inference adapter
│   ├── main.py           # FastAPI application and REST endpoints
│   ├── mcp_gateway.py    # Allow-listed simulated tool gateway
│   ├── privacy.py        # Regex-based PII masking demonstration
│   ├── registry.py       # YAML manifest loading and validation
│   ├── schemas.py        # Pydantic request and agent schemas
│   └── settings.py       # Environment-based application settings
├── config/
│   └── agents/           # Specialist agent YAML manifests
├── data/
│   └── uploads/          # Runtime artifact storage (not committed)
├── docs/
│   ├── ARCHITECTURE_2.0.md       # Company OS architecture
│   ├── OPEN_SOURCE_STACK_2.0.md  # Open-source components and status
│   ├── ROADMAP_2.0.md            # Phased delivery programme
│   ├── WORKFORCE_RUNTIME_2.0.md  # Goal-to-result workforce runtime guide
│   ├── DURABLE_WORKFORCE_RUNTIME_2.0.md # Durable jobs, checkpoints, MCP and local models
│   └── ARCHITECTURE.md           # Legacy MVP architecture
├── tests/
│   ├── test_engine.py            # Legacy API/workflow behavior tests
│   ├── test_company_graph.py     # Company graph and storage tests
│   └── test_workforce.py         # Planning, execution, meetings and KPI tests
├── web/
│   ├── app.js            # Dashboard behavior
│   ├── index.html        # Dashboard markup
│   └── styles.css        # Dashboard styling
├── .env.example          # Sample local environment settings
├── AGENTS.md             # Instructions for AI coding agents
├── CODEX_TASK.md         # Suggested next engineering task
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── requirements.txt
```

## Security and operational boundaries

Pinky Bread is a prototype. Before any enterprise or regulated deployment, address at least the following:

- **Identity and access:** implement OIDC/JWT validation, user and tenant authorization, role-based tool scopes, and authenticated approver identity. The current `approver_id` is user-supplied and is not verified.
- **Tenant isolation:** enforce tenant ownership on every workflow, artifact and approval request. The `tenant_id` field is stored but is not an authorization boundary.
- **Privacy:** replace regex-only masking with tested local PII/PHI detection, controlled tokenization, secure re-identification policy, encrypted sensitive state, retention controls and data minimization. Original prompts are persisted in workflow records.
- **MCP identity:** replace the internal static bearer verifier with Keycloak/OIDC JWT/JWKS or token introspection, company membership checks and per-agent tool grants. The current MCP v2 server is internal-development only.
- **Workflow durability:** LangGraph + PostgreSQL checkpoints, lease recovery and bounded retries are implemented in Alpha 3. Add budget enforcement, richer concurrency controls, prompt/model rollback and backup/restore drills.
- **Audit integrity:** add WORM or independently protected storage, signed records, external anchoring, controlled access, and audit-chain verification tooling. Hash-linked database rows alone are not immutable.
- **Network security:** enforce egress control, ingress restrictions, mTLS, DNS policy, registry controls and host firewall rules outside this application. A Compose `internal` network is only one deployment control.
- **Secrets and supply chain:** use a secrets manager, trusted internal registries, image scanning, dependency pinning/SBOM, vulnerability scanning and signed artifacts.
- **Observability and resilience:** add OpenTelemetry traces/metrics/logs, alerting, runbooks, load testing, backup/restore and disaster recovery validation.
- **Document safety:** add upload scanning, content validation, storage encryption, retention and size/format limits appropriate to the target environment.

No regulatory certification, security assurance, production air-gap verification, or immutable-audit claim is made by this repository.

## Roadmap

See [the Alpha 2 workforce runtime guide](docs/WORKFORCE_RUNTIME_2.0.md) for the goal-to-result workflow and [Alpha 3 durable runtime guide](docs/DURABLE_WORKFORCE_RUNTIME_2.0.md) for checkpoints, worker recovery, coordination, MCP v2 and local models. Remaining roadmap increments:

1. **Durable orchestration:** LangGraph `StateGraph`, PostgreSQL checkpoints, restart recovery, bounded retries and idempotent workflow resume.
2. **Real MCP integration:** MCP SDK server/client transport, structured tool schemas, authenticated tool identities and tool-level policy checks.
3. **Approval security:** authenticated approvers, role/tenant checks, separation of duties and replay protection.
4. **Multimodal processing:** local OCR for scanned PDFs, image validation, vision-model integration tests and safer artifact lifecycle controls.
5. **Privacy and governance:** local NER/Presidio, secure token vault, prompt/model manifest versioning, audit export and retention policy.
6. **Platform operations:** OIDC, mTLS, OpenTelemetry, Valkey-backed coordination, policy enforcement, deployment hardening and security/load testing.

## Troubleshooting

### `ModuleNotFoundError` when starting the API

Confirm the virtual environment is activated and install dependencies again:

```bash
python -m pip install -r requirements.txt
```

### Port 8080 is already in use

Choose another port, for example:

```bash
uvicorn app.main:app --reload --port 8090
```

### The dashboard shows the API as offline

Check that the server process is still running and that the browser is using the same host/port displayed in the terminal. Inspect `/api/healthz` for the service response.

### A local model call fails

Check `MOCK_INFERENCE=false`, model endpoint reachability from the API process/container, the `/v1` base path, model identifier, bearer token configuration, and whether the server supports the expected OpenAI-compatible chat completion payload.

### Docker cannot connect to a model running on the host

Do not use the container's `localhost` address for a model server running on the host. Configure a hostname/address reachable from the container network, and verify the host's firewall policy.

### Agent reload reports validation errors

Review the reported YAML filename and schema error. Ensure each manifest includes the required sections and valid field types. A failed reload leaves the active last-known-good registry unchanged.

---

## License

This repository includes the Apache License, Version 2.0 in [`LICENSE`](LICENSE). Review the full license text for the permissions, conditions, limitations, and attribution requirements that apply to this project.
